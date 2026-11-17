"""
replica_con_obstaculo.py
========================
Réplica PAREADA en simulación de cada toma incluida de la campaña L2 con el
obstáculo móvil (`tesis/PROPUESTA_campana_L2_obstaculo.md` §2, decisiones de
José del 2026-10-08; contrato de columnas en `tesis/PLAN_ANALISIS_campana_L2.md`
§9). Es la pareja de `replica_con_capas.py` (30-09), que no se toca.

  · La MISMA pila del laboratorio: `CoordinadorConObstaculo` con F2 y su
    predictor, `correr_toma` con el lazo de evaluación, contra un
    `SimuladorRobotat` con RETARDO CERO y calibración identidad (como
    `replica_con_capas`).
  · El 4 se REPRODUCE, no se simula:
      - `SimuladorReplay`: la física no integra al 4 (un dict cuyo
        `values()` lo omite); en cada decisión se lo pone en su pose medida;
      - `SupervisorReplay`: en cada decisión manda el (v_cmd, w_cmd) GRABADO
        (así el historial del predictor y la v_cmd de la barrera son los del
        hardware), coloca al 4 en hw[0] al reiniciar y en hw[k+1] al final
        de la decisión k (la fuente lo ve en la consulta de la decisión
        siguiente: sin desfase), y calcula el freno en SOMBRA con los
        agentes de la réplica.
  · Por toma incluida: 3 repeticiones con obstáculo (τ = 0), 3 sin obstáculo
    (τ = 0; el 4 estacionado fuera del alcance del mocap, sin fila) y 3 con
    obstáculo y τ = 0.45. `--suplementaria` corre sólo los grupos con 0
    válidas, desde la repetición 4 (regla del 30-09).
  · Cierre (b) por corrida, también en las inválidas: la trayectoria del 4
    que vio la pila coincide con la medida dentro de 1 mm, sin desfase, con
    el rumbo dentro de 1e-6 rad y los mandos idénticos.
  · Escritura incremental (una fila por corrida, con fsync) y `--reanudar`.
  · Se NIEGA a correr sobre una campaña de hardware que no esté cerrada
    (cegado, §8). Nunca en paralelo con el hardware ni con otro simulador.

Uso:
    python replica_con_obstaculo.py --campana NOMBRE [--reanudar] [--suplementaria]
    python replica_con_obstaculo.py --campana NOMBRE --verificar        (sin simulador)
    python replica_con_obstaculo.py --carpeta-vieja resultados_demo_obstaculo/ensayo_L2_auto_20261007_125313 --salida DIR
    python replica_con_obstaculo.py --episodios-3009 --salida DIR       (cierre a3)

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import argparse
import atexit
import csv
import hashlib
import json
import math
import os
import socket
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

_CARPETA = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import config_robotat as cfg                                      # noqa: E402

_TESIS = _CARPETA.parents[2]
DIR_DEMO = _CARPETA / "resultados_demo_obstaculo"
DIR_3009 = _TESIS / "REPORTE_2026-09-30_datos" / "csv"

ID_OBSTACULO: int = 4
N_AGENTES: int = 5
PUERTO_POR_DEFECTO: int = 48830
DESPLAZAMIENTO_RUEDAS: int = 260
#: env (−6.0, 1.5) = lab (−7.5, 0.0): fuera de ±5 m, la fuente lo rechaza.
ESTACIONAMIENTO_ENV: Tuple[float, float, float] = (-6.0, 1.5, 0.0)
UMBRAL_CIERRE_B_M: float = 1e-3
UMBRAL_RUMBO_RAD: float = 1e-6
UMBRAL_MOVIMIENTO_M: float = 1e-4
UMBRAL_POSE_INICIAL_M: float = 1e-3
UMBRAL_POSE_INICIAL_RAD: float = 1e-6
REPS_NORMALES: Tuple[int, ...] = (1, 2, 3)
CON, SIN = "con_obstaculo", "sin_obstaculo"
#: Orden por toma: las tres condiciones juntas en el tiempo.
CONDICIONES_ORDEN: Tuple[Tuple[str, float], ...] = ((CON, 0.0), (SIN, 0.0), (CON, 0.45))
ARCHIVOS_PILA_EXTRA: Tuple[str, ...] = ("simulador_robotat.py", "replica_con_obstaculo.py",
                                        "calibracion_medida.json")
#: Columnas informativas, después del contrato (el análisis las ignora).
EXTRAS: Tuple[str, ...] = (
    "formato", "error_pose_inicial_m", "error_rumbo_inicial_rad", "factor",
    "rpm_aborto", "tau_prediccion_s", "duracion_s", "ciclo_p95_ms",
    "ciclos_sobre_100ms", "frenos_sombra_detalle", "cierre_b_n", "cierre_b_n_mov",
)


class ErrorReplica(RuntimeError):
    """La réplica se niega o se detiene (con el motivo)."""


# ── funciones puras: COPIAS de replica_con_capas.py (prueba a1 por AST) ───
def imponer_identidad() -> None:
    """La calibración identidad de `replica_con_capas.py:120-125`, llamada
    DESPUÉS de `calibracion_sesion.aplicar_a_config()`."""
    cfg.ESCALA_POSICION = 1.0
    cfg.ROTACION_MARCO_RAD = 0.0
    cfg.TRASLACION_X_M = 1.5
    cfg.TRASLACION_Y_M = 1.5
    cfg.OFFSET_HEADING_RAD = 0.0
    cfg.offset_rumbo_de_robot = lambda _id_robot: 0.0


def env_a_lab(x, y, th, id_robot):
    """Inversa exacta de lab_a_env + heading del cuaternión del simulador."""
    c, s = math.cos(cfg.ROTACION_MARCO_RAD), math.sin(cfg.ROTACION_MARCO_RAD)
    dx, dy = x - cfg.TRASLACION_X_M, y - cfg.TRASLACION_Y_M
    xs, ys = c * dx + s * dy, -s * dx + c * dy
    yaw = th - cfg.ROTACION_MARCO_RAD - cfg.offset_rumbo_de_robot(id_robot)
    yaw = math.atan2(math.sin(yaw), math.cos(yaw))
    return xs / cfg.ESCALA_POSICION, ys / cfg.ESCALA_POSICION, yaw


def previas_por_suma(todas: Sequence[Dict[str, str]], clave: str, k: int) -> int:
    """La regla de `replica_con_capas.decisiones_previas`: suma `decisiones`
    de las filas anteriores (clave < k) de la MISMA sesión, salteando las
    vacías (colocación rechazada, toma que no arrancó)."""
    return sum(int(float(r["decisiones"])) for r in todas
               if int(float(r[clave])) < k
               and r.get("decisiones") not in (None, ""))


def aplicar_calibracion_identidad() -> None:
    """`aplicar_a_config()` (lee el JSON medido, por las banderas) y DESPUÉS
    la identidad: el orden de `replica_con_capas.py:109-125`."""
    import calibracion_sesion as calib
    calib.aplicar_a_config()
    imponer_identidad()


def verificar_ida_y_vuelta(tomas: Sequence["TomaReplica"]) -> float:
    """Ida y vuelta analítico env → lab → env (agentes y el 4), como
    `replica_con_capas.py:241-255`. Devuelve el error máximo."""
    from protocolo_robotat import heading_desde_cuaternion, lab_a_env
    peor = 0.0
    for t in tomas:
        objetivos = [(cfg.MAPEO_AGENTES[i].id_robot, t.poses_iniciales[i])
                     for i in range(N_AGENTES)]
        if t.traza_obstaculo:
            f0 = t.traza_obstaculo[0]
            objetivos.append((ID_OBSTACULO, (f0["x"], f0["y"], f0["th"])))
        for rid, obj in objetivos:
            xl, yl, yaw = env_a_lab(*obj, rid)
            yq, _ = heading_desde_cuaternion(math.cos(yaw / 2), 0.0, 0.0,
                                             math.sin(yaw / 2))
            e = lab_a_env(xl, yl, yq, cfg.offset_rumbo_de_robot(rid))
            dth = math.atan2(math.sin(e[2] - obj[2]), math.cos(e[2] - obj[2]))
            peor = max(peor, abs(e[0] - obj[0]), abs(e[1] - obj[1]), abs(dth))
    return peor


def _envolver(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


def _num(x: Any) -> Optional[float]:
    try:
        s = str(x).strip()
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


def _leer(ruta: Path) -> List[Dict[str, str]]:
    with open(ruta, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ── carga ────────────────────────────────────────────────────────────────
@dataclass
class TomaReplica:
    formato: str
    campana: str
    fuente_tomas: str
    id_sesion: str
    intento: int
    semilla: int
    decisiones: int
    decisiones_previas: int
    factor: float
    rpm_aborto: float
    tau_prediccion_s: float
    poses_iniciales: Dict[int, Tuple[float, float, float]]
    traza_obstaculo: Optional[List[Dict[str, Any]]]
    avisos: List[str] = field(default_factory=list)
    robots: Tuple[int, ...] = ()
    plataforma: str = ""
    #: |x0 de la fila − paso 0 de decisiones| y |obst_*_med − traza[0]| (m).
    dif_x0_paso0_m: Optional[float] = None
    dif_obst_traza0_m: Optional[float] = None


def _traza_de(filas: Sequence[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Normaliza la traza del 4 del hw, ordenada por paso."""
    out = []
    for r in sorted(filas, key=lambda r: int(float(r["paso"]))):
        out.append({"paso": int(float(r["paso"])), "x": _num(r["x"]), "y": _num(r["y"]),
                    "th": _num(r["th"]), "v_cmd": _num(r["v_cmd"]), "w_cmd": _num(r["w_cmd"]),
                    "estado": r.get("estado", ""), "error_radial": _num(r.get("error_radial"))})
    return out


def cargar_campana(base: Path, nombre: str, dir_hw: Optional[Path] = None,
                   permitir_abierta: bool = False) -> List[TomaReplica]:
    """Las tomas INCLUIDAS de una campaña, con el libro mandando (la misma
    carga y los mismos cruces que el análisis). Se niega con una campaña de
    hardware abierta (§8)."""
    import analizar_campana_l2 as A
    from campana_obstaculo import Campana
    campana = Campana(Campana.carpeta_de(base, nombre))
    hw_plat = campana.cabecera["plataforma"] == "hw"
    if hw_plat and not campana.estado()["cerrada"] and not permitir_abierta:
        raise ErrorReplica(f"la campaña de hardware {nombre!r} no está cerrada: "
                           f"la réplica corre sólo después del cierre (§8)")
    dir_hw = dir_hw or base
    hw = A.cargar_hw(campana, dir_hw, ensayo=not hw_plat)
    trazas: Dict[Tuple[str, int], List[Dict[str, str]]] = {}
    for ruta in sorted(dir_hw.glob("*_L2_obstaculo*.csv")):
        for r in _leer(ruta):
            trazas.setdefault((r.get("id_sesion", ""), int(float(r["toma"]))), []).append(r)
    paso0: Dict[Tuple[str, int, int], Tuple[float, float]] = {}
    for ruta in sorted(dir_hw.glob("*_L2_decisiones*.csv")):
        for x in _leer(ruta):
            if x.get("paso") == "0":
                paso0[(x.get("id_sesion", ""), int(float(x["episodio"])),
                       int(float(x["agente"])))] = (float(x["pose_env_x"]),
                                                    float(x["pose_env_y"]))
    tomas: List[TomaReplica] = []
    for k, f in sorted(hw["resultados"].items()):
        if not A._es_uno(f["incluida"]):
            continue
        r = hw["tomas"][k]
        sesion = r["id_sesion"]
        filas_sesion = [x for x in _leer(dir_hw / f["archivo_tomas"])
                        if x.get("id_sesion") == sesion]
        previas = int(float(r["decisiones_previas"]))
        previas_suma = previas_por_suma(filas_sesion, "toma", k)
        avisos = []
        if previas != previas_suma:
            raise ErrorReplica(f"intento {k}: decisiones_previas {previas} ≠ suma de "
                               f"las tomas anteriores de la sesión {previas_suma}")
        tr = trazas.get((sesion, k))
        if not tr:
            raise ErrorReplica(f"intento {k}: no está la traza del obstáculo")
        traza = _traza_de(tr)
        difs = [math.hypot(float(r[f"x0_a{i}"]) - paso0[(sesion, k, i)][0],
                           float(r[f"y0_a{i}"]) - paso0[(sesion, k, i)][1])
                for i in range(N_AGENTES) if (sesion, k, i) in paso0]
        dif_x0 = max(difs) if len(difs) == N_AGENTES else None
        dif_o = (math.hypot(float(r["obst_x0_med"]) - traza[0]["x"],
                            float(r["obst_y0_med"]) - traza[0]["y"])
                 if r.get("obst_x0_med") not in (None, "") else None)
        tomas.append(TomaReplica(
            formato="campana", campana=campana.nombre, fuente_tomas=f["archivo_tomas"],
            id_sesion=sesion, intento=k, semilla=int(float(r["semilla"])),
            decisiones=int(float(r["decisiones"])), decisiones_previas=previas,
            factor=float(r["factor"]), rpm_aborto=float(r["rpm_aborto"]),
            tau_prediccion_s=float(r["tau_prediccion_s"]),
            poses_iniciales={i: (float(r[f"x0_a{i}"]), float(r[f"y0_a{i}"]),
                                 float(r[f"th0_a{i}"])) for i in range(N_AGENTES)},
            traza_obstaculo=traza, avisos=avisos,
            robots=tuple(int(float(r[f"robot_a{i}"])) for i in range(N_AGENTES)),
            plataforma=campana.cabecera["plataforma"],
            dif_x0_paso0_m=dif_x0, dif_obst_traza0_m=dif_o))
    return tomas


def cargar_carpeta_vieja(carpeta: Path) -> List[TomaReplica]:
    """Ensayos L2 del 07-10 (formato viejo, sin libro): sólo para probar la
    tubería. Poses iniciales del paso 0 de decisiones; rampa por suma;
    rpm_aborto 200 y τ_c 0.65 (los del 07-10), con aviso."""
    from campana_obstaculo import inclusion_campana

    def uno(patron: str) -> Path:
        r = sorted(carpeta.glob(patron))
        if len(r) != 1:
            raise ErrorReplica(f"{carpeta}: {len(r)} archivos {patron}")
        return r[0]
    ruta_t = uno("*_L2_tomas*.csv")
    tomas_csv = _leer(ruta_t)
    dec = _leer(uno("*_L2_decisiones*.csv"))
    obst = _leer(uno("*_L2_obstaculo*.csv"))
    resumen = carpeta / "resumen_ensayo.json"
    rid_o = int(json.loads(resumen.read_text(encoding="utf-8")).get(
        "robot_obstaculo", ID_OBSTACULO)) if resumen.is_file() else ID_OBSTACULO
    if rid_o != ID_OBSTACULO:
        raise ErrorReplica(f"{carpeta}: el obstáculo fue el robot {rid_o}")
    out: List[TomaReplica] = []
    for r in tomas_csv:
        if r.get("decisiones") in (None, "") or not inclusion_campana(r)[0]:
            continue
        k = int(float(r["toma"]))
        poses = {}
        robots_k = []
        for i in range(N_AGENTES):
            d0 = [x for x in dec if x["episodio"] == str(k) and x["agente"] == str(i)
                  and x["paso"] == "0"]
            if len(d0) != 1:
                raise ErrorReplica(f"{carpeta.name} toma {k} agente {i}: sin paso 0")
            poses[i] = (float(d0[0]["pose_env_x"]), float(d0[0]["pose_env_y"]),
                        float(d0[0]["pose_env_th"]))
            robots_k.append(int(float(d0[0]["robot"])))
        out.append(TomaReplica(
            formato="vieja", campana=f"vieja_{carpeta.name}", fuente_tomas=ruta_t.name,
            id_sesion=ruta_t.name.split("_L2_")[0], intento=k,
            semilla=int(float(r["semilla"])), decisiones=int(float(r["decisiones"])),
            decisiones_previas=previas_por_suma(tomas_csv, "toma", k),
            factor=float(r.get("factor") or 0.40), rpm_aborto=200.0, tau_prediccion_s=0.65,
            poses_iniciales=poses,
            traza_obstaculo=_traza_de([x for x in obst if x["toma"] == str(k)]),
            avisos=["formato viejo: rpm_aborto 200 y τ_c 0.65 supuestos (los del 07-10)"],
            robots=tuple(robots_k), plataforma="simulador", dif_x0_paso0_m=0.0))
    return out


def cargar_episodios_3009(dir_3009: Path = DIR_3009,
                          episodios: Optional[Sequence[Tuple[str, int]]] = None
                          ) -> List[TomaReplica]:
    """Episodios válidos del 30-09 para el cierre (a3): sin obstáculo, con su
    semilla, x0 y rampa. `episodios` = [(sufijo de sesión, episodio)]."""
    out: List[TomaReplica] = []
    if episodios is not None and len({e for _s, e in episodios}) != len(episodios):
        raise ErrorReplica("episodios del 30-09 con el mismo número en dos sesiones: "
                           "la clave de la réplica los confundiría")
    for s in ("", "_02", "_03", "_04", "_05"):
        ruta = dir_3009 / f"20260930_sesion-evaluacion_etapa7_episodios{s}.csv"
        todas = _leer(ruta)
        for r in todas:
            if r["valido"] not in ("1", "True"):
                continue
            ep = int(r["episodio"])
            if episodios is not None and (s, ep) not in episodios:
                continue
            out.append(TomaReplica(
                formato="3009", campana="cierre_a3", fuente_tomas=ruta.name,
                id_sesion=f"30-09{s}", intento=ep, semilla=int(float(r["semilla"])),
                decisiones=int(float(r["decisiones"])),
                decisiones_previas=previas_por_suma(todas, "episodio", ep),
                factor=float(r.get("factor") or 0.40),
                rpm_aborto=float(r.get("rpm_aborto") or 200.0),
                tau_prediccion_s=0.65,
                poses_iniciales={i: (float(r[f"x0_a{i}"]), float(r[f"y0_a{i}"]),
                                     float(r[f"th0_a{i}"])) for i in range(N_AGENTES)},
                traza_obstaculo=None, plataforma="hw",
                robots=tuple(int(float(r[f"robot_a{i}"])) for i in range(N_AGENTES))
                if r.get("robot_a0") not in (None, "") else ()))
    return out


# ── cierre (a3): regla aprobada por José (2026-10-10) ────────────────────
#: Regla (aprobada por José el 2026-10-10): Δ_e = media de las reps válidas
#: nuevas − media de las reps válidas del 30-09 del mismo episodio; PASA si
#: el IC95 t (E − 1 gl) de la media de Δ_e queda dentro de ±δ, con δ = el
#: desvío dentro de episodio agrupado de la réplica del 30-09 (0.00827, 98
#: gl). Episodios: la última aparición válida de cada semilla (12). Corre
#: con la máquina libre; si no pasa, se investiga antes de correr la réplica
#: de la campaña, SIN cambiar el margen.
A3_ESTADO: str = "APROBADA por José (2026-10-10)"


def _reps_3009(dir_3009: Path) -> Dict[Tuple[str, int], List[float]]:
    por: Dict[Tuple[str, int], List[float]] = {}
    for s in ("", "_02", "_03", "_04", "_05"):
        rep = sorted(dir_3009.glob(f"*_sesion-replica_etapa7_capas-on_de-20260930{s}.csv"))[-1]
        for r in _leer(rep):
            if str(r.get("valido", "1")) in ("1", "True", "true"):
                por.setdefault((s, int(r["episodio"])), []).append(float(r["cobertura_aoi"]))
    return por


def delta_a3(dir_3009: Path = DIR_3009) -> float:
    """El desvío dentro de episodio agrupado (ddof = 1) de la réplica del
    30-09, sobre los episodios con ≥ 2 reps válidas."""
    grupos = [v for v in _reps_3009(dir_3009).values() if len(v) >= 2]
    num = sum(sum((x - float(np.mean(g))) ** 2 for x in g) for g in grupos)
    return math.sqrt(num / sum(len(g) - 1 for g in grupos))


def episodios_a3(dir_3009: Path = DIR_3009) -> List[Tuple[str, int]]:
    """La última aparición válida de cada semilla, en orden (sesión, episodio)."""
    ultima: Dict[int, Tuple[str, int]] = {}
    for s in ("", "_02", "_03", "_04", "_05"):
        for r in _leer(dir_3009 / f"20260930_sesion-evaluacion_etapa7_episodios{s}.csv"):
            if r["valido"] in ("1", "True"):
                ultima[int(float(r["semilla"]))] = (s, int(r["episodio"]))
    return [ultima[k] for k in sorted(ultima)]


def evaluar_cierre_a3(dir_a3: Path, dir_3009: Path = DIR_3009,
                      delta: Optional[float] = None) -> Dict[str, Any]:
    """Compara las reps nuevas (sin obstáculo, τ = 0) con las del 30-09."""
    from scipy import stats
    delta = delta_a3(dir_3009) if delta is None else delta
    ref = _reps_3009(dir_3009)
    nuevas: Dict[Tuple[str, int], List[float]] = {}
    invalidas = 0
    for ruta in sorted(dir_a3.glob("*_replica_tomas.csv")):
        for r in _leer(ruta):
            if r["condicion"] != SIN or float(r["tau_s"]) != 0.0:
                continue
            clave = (r["id_sesion"].replace("30-09", ""), int(float(r["intento_campana"])))
            if str(r["valido"]).strip() in ("1", "1.0"):
                nuevas.setdefault(clave, []).append(float(r["cobertura_aoi"]))
            else:
                invalidas += 1
    # Completa (los 12 episodios, reps 1–3 y la suplementaria si hizo falta)
    # y de una sola pila; si no, no hay veredicto (auditoría final, 10-10).
    hechas = claves_hechas(dir_a3)
    episodios = cargar_episodios_3009(dir_3009, episodios=episodios_a3(dir_3009))
    normales, suplementarias = completitud(episodios, {
        k: v for k, v in hechas.items() if k[1] == SIN and k[2] == 0.0}, ((SIN, 0.0),))
    pilas = sorted({r.get("sha256_pila", "") for r in hechas.values()})
    tabla = []
    for clave in sorted(nuevas):
        v, w = nuevas[clave], ref.get(clave, [])
        if not w:
            continue
        tabla.append({"sesion": clave[0] or "_01", "episodio": clave[1],
                      "n_nuevas": len(v), "media_nueva": float(np.mean(v)),
                      "media_3009": float(np.mean(w)), "delta": float(np.mean(v) - np.mean(w)),
                      "sd_nueva": float(np.std(v, ddof=1)) if len(v) > 1 else None})
    d = np.array([t["delta"] for t in tabla])
    out: Dict[str, Any] = {"estado": A3_ESTADO, "delta_umbral": delta, "E": len(d),
                           "corridas_invalidas": invalidas, "tabla": tabla,
                           "sha256_pila": pilas, "faltan": normales + suplementarias}
    if normales or suplementarias or len(d) != len(episodios) or len(pilas) != 1 \
            or "FALSA" in pilas:
        out["pasa"] = None
        out["motivo_sin_veredicto"] = (
            f"a3 incompleto o de más de una pila: E = {len(d)} de {len(episodios)}, "
            f"faltan {normales + suplementarias}, pilas {pilas}")
        return out
    if len(d) >= 2:
        w = float(stats.t.ppf(0.975, len(d) - 1) * d.std(ddof=1) / math.sqrt(len(d)))
        lo, hi = float(d.mean() - w), float(d.mean() + w)
        sds = [t["sd_nueva"] for t in tabla if t["sd_nueva"] is not None]
        out.update(media=float(d.mean()), ic95=[lo, hi], pasa=bool(-delta <= lo and hi <= delta),
                   sd_nueva_mediana=float(np.median(sds)) if sds else None,
                   sd_nueva_max=float(max(sds)) if sds else None,
                   referencia_3009={"sd_mediana": 0.0013, "sd_max": 0.0314})
    return out


def auditar(tomas: Sequence[TomaReplica]) -> List[str]:
    """Chequeos antes de levantar nada. Devuelve los problemas."""
    problemas: List[str] = []
    largos = {t.decisiones for t in tomas}
    if len(largos) > 1:
        problemas.append(f"tomas con largos distintos: {sorted(largos)}")
    mapeo = tuple(cfg.MAPEO_AGENTES[i].id_robot for i in range(N_AGENTES))
    for t in tomas:
        if t.robots and t.robots != mapeo:
            problemas.append(f"intento {t.intento}: robots del registro {t.robots} ≠ "
                             f"MAPEO_AGENTES {mapeo}")
        for nombre, dif in (("x0 contra el paso 0", t.dif_x0_paso0_m),
                            ("pose medida del 4 contra la traza", t.dif_obst_traza0_m)):
            if dif is None or dif <= UMBRAL_POSE_INICIAL_M:
                continue
            texto = f"intento {t.intento}: {nombre} difiere {dif * 1000:.2f} mm"
            if t.plataforma == "simulador":
                problemas.append(texto)
            elif texto not in t.avisos:
                t.avisos.append(texto + " (informativo en hw)")
        if t.traza_obstaculo is None:
            continue
        tr = t.traza_obstaculo
        if [f["paso"] for f in tr] != list(range(t.decisiones)):
            problemas.append(f"intento {t.intento}: la traza no tiene los pasos "
                             f"0..{t.decisiones - 1}")
            continue
        if any(f[c] is None for f in tr for c in ("x", "y", "th", "v_cmd", "w_cmd")):
            problemas.append(f"intento {t.intento}: traza con valores vacíos")
        rampa = max(0, cfg.DECISIONES_ARRANQUE - t.decisiones_previas) \
            if cfg.ARRANQUE_SEGURO else 0
        if any(f["estado"] not in ("espera", "freno") for f in tr[:rampa]) or (
                rampa < len(tr) and tr[rampa]["estado"] == "espera"):
            problemas.append(f"intento {t.intento}: la traza no muestra la rampa de "
                             f"{rampa} decisiones (previas {t.decisiones_previas})")
    return problemas


# ── simulador y supervisor de la réplica ─────────────────────────────────
class _RobotsSinReproducido(dict):
    """dict de estados cuyo `values()` omite al robot reproducido: la física
    (`SimuladorRobotat._fisica`) no lo integra; las poses y las ruedas, que
    acceden por clave, sí lo ven."""

    def __init__(self, base: Dict[int, Any], excluido: int) -> None:
        super().__init__(base)
        self.excluido = int(excluido)

    def values(self):                                  # type: ignore[override]
        return [v for k, v in self.items() if k != self.excluido]


def _clase_simulador_replay():
    from simulador_robotat import SimuladorRobotat

    class SimuladorReplay(SimuladorRobotat):
        """El simulador de siempre con el 4 fuera de la física."""

        def __init__(self, *a: Any, id_reproducido: int = ID_OBSTACULO, **kw: Any) -> None:
            super().__init__(*a, **kw)
            self.id_reproducido = int(id_reproducido)
            self.robots = _RobotsSinReproducido(self.robots, self.id_reproducido)
            self.colocaciones = 0

        def teletransportar_env(self, poses_env: Dict[int, Tuple[float, float, float]]) -> None:
            """Pone robots en poses del env y vacía TODAS las órdenes (también
            las en vuelo y las de las ruedas: al cambiar de τ no arrancan
            andando)."""
            with self._lock:
                for rid, (x, y, th) in poses_env.items():
                    est = dict.__getitem__(self.robots, rid)
                    est.x, est.y, est.yaw = env_a_lab(x, y, th, rid)
                for est in dict.values(self.robots):
                    est.rpm_izq = est.rpm_der = 0.0
                    est.rpm_izq_ruedas = est.rpm_der_ruedas = 0.0
                    est.en_camino.clear()

        def fijar_pose_env(self, rid: int, x: float, y: float, th: float) -> None:
            with self._lock:
                est = dict.__getitem__(self.robots, rid)
                est.x, est.y, est.yaw = env_a_lab(x, y, th, rid)
                est.en_camino.clear()
            self.colocaciones += 1

    return SimuladorReplay


def _clase_supervisor_replay():
    import demo_obstaculo_movil as demo

    class SupervisorReplay(demo.SupervisorObstaculo):
        """Reproduce al 4 decisión por decisión: manda el mando GRABADO y lo
        coloca en su pose medida (hw[0] al reiniciar, hw[k+1] al final de
        la decisión k). Freno en SOMBRA con los agentes de la réplica."""

        def __init__(self, fuente: Any, canal: Any,
                     colocar: Callable[[float, float, float], None]) -> None:
            self._colocar = colocar
            self._traza_hw: List[Dict[str, Any]] = []
            super().__init__(fuente, canal, modo="movil", freno_activo=False,
                             vigilar_congelamiento=False)

        def cargar_traza(self, traza: List[Dict[str, Any]]) -> None:
            if [f["paso"] for f in traza] != list(range(len(traza))):
                raise ErrorReplica("traza del 4 sin pasos densos")
            self._traza_hw = list(traza)

        def reiniciar_toma(self) -> None:
            super().reiniciar_toma()
            if self._traza_hw:
                f0 = self._traza_hw[0]
                self._colocar(f0["x"], f0["y"], f0["th"])

        def _verificar_obediencia(self, ahora: float) -> Optional[str]:
            return None                     # el 4 no obedece a la física

        def paso(self, poses_agentes, en_retroceso, factor_arranque, ahora, paso):
            self._ahora_paso = float(ahora)
            pose = self._fuente.pose_obstaculo()
            if self.estado == "abortado":
                mando = self._mandar(0.0, 0.0)
                self._anotar(paso, ahora, pose, mando, None, poses_agentes)
                return mando
            motivo = self._chequear(pose)
            if motivo is None and paso >= len(self._traza_hw):
                motivo = f"RÉPLICA: la traza del hardware no tiene la decisión {paso}"
            if motivo is not None:
                self._abortar(motivo, paso)
                mando = (0.0, 0.0)
                self.ultimo_mando = mando
                self._anotar(paso, ahora, pose, mando, None, poses_agentes)
                return mando
            # Freno en SOMBRA: la histéresis de la base, sin frenar.
            if not self._en_freno:
                det = self._condicion_freno(pose, poses_agentes, en_retroceso,
                                            self.freno_frente_m, self.freno_retroceso_m)
                if det is not None:
                    self._en_freno = True
                    det.update({"paso": int(paso), "activo": 0})
                    self.eventos_freno.append(det)
            elif self._condicion_freno(pose, poses_agentes, en_retroceso,
                                       self.reanuda_frente_m,
                                       self.reanuda_retroceso_m) is None:
                self._en_freno = False
            if self._en_freno:
                self.decisiones_freno += 1
            f = self._traza_hw[paso]
            self.estado = f["estado"] or "marcha"
            if self.estado == "patada":
                self.decisiones_patada += 1
            elif self.estado == "marcha":
                self.decisiones_marcha += 1
            e_rad = f["error_radial"]
            if e_rad is not None:
                self.error_radial_max_obs = max(self.error_radial_max_obs, abs(e_rad))
            mando = self._mandar(f["v_cmd"], f["w_cmd"])
            self._anotar(paso, ahora, pose, mando, e_rad, poses_agentes)
            if paso + 1 < len(self._traza_hw):
                g = self._traza_hw[paso + 1]
                self._colocar(g["x"], g["y"], g["th"])
            return mando

    return SupervisorReplay


# ── cierre (b) ───────────────────────────────────────────────────────────
def evaluar_cierre_b(traza_rep: Sequence[Dict[str, Any]],
                     traza_hw: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """La trayectoria del 4 que vio la PILA (traza del supervisor de la
    réplica) contra la medida, decisión por decisión."""
    n = len(traza_rep)
    if n == 0:
        # No arrancó: sin cierre (b) (plan §7); la corrida es una repetición
        # inválida y no excluye la toma.
        return {"ok": "", "err_max": "", "desfase": "", "err_th": "",
                "mandos_iguales": "", "n": 0, "n_mov": 0}
    pasos_ok = [int(f["paso"]) for f in traza_rep] == list(range(n)) and n <= len(traza_hw)

    def xy(f: Dict[str, Any]) -> Optional[np.ndarray]:
        x, y = _num(f.get("x")), _num(f.get("y"))
        return None if x is None or y is None else np.array([x, y])

    errs, ths = [], []
    for k in range(min(n, len(traza_hw))):
        a, b = xy(traza_rep[k]), xy(traza_hw[k])
        errs.append(float(np.linalg.norm(a - b)) if a is not None and b is not None
                    else float("inf"))
        t_a, t_b = _num(traza_rep[k].get("th")), _num(traza_hw[k].get("th"))
        ths.append(abs(_envolver(t_a - t_b)) if t_a is not None and t_b is not None
                   else float("inf"))
    err_max = max(errs) if errs else float("inf")
    err_th = max(ths) if ths else float("inf")
    mandos = all(
        (_num(traza_rep[k].get("v_cmd")), _num(traza_rep[k].get("w_cmd")))
        == (traza_hw[k]["v_cmd"], traza_hw[k]["w_cmd"])
        for k in range(min(n, len(traza_hw))) if traza_rep[k].get("estado") != "abortado")
    hw_xy = [xy(f) for f in traza_hw]
    mov = [k for k in range(1, min(n, len(traza_hw)))
           if hw_xy[k] is not None and hw_xy[k - 1] is not None
           and float(np.linalg.norm(hw_xy[k] - hw_xy[k - 1])) > UMBRAL_MOVIMIENTO_M]
    desfase = 0
    if mov:
        e_l = {}
        for lag in (-1, 0, 1):
            ds = []
            for k in mov:
                j = k + lag
                a = xy(traza_rep[k])
                if 0 <= j < len(traza_hw) and a is not None and hw_xy[j] is not None:
                    ds.append(float(np.linalg.norm(a - hw_xy[j])))
            e_l[lag] = float(np.mean(ds)) if ds else float("inf")
        mejor = min(e_l.values())
        desfase = 0 if e_l[0] <= mejor + 1e-12 else min(e_l, key=e_l.get)
    ok = int(pasos_ok and err_max <= UMBRAL_CIERRE_B_M and desfase == 0
             and err_th <= UMBRAL_RUMBO_RAD and mandos)
    return {"ok": ok, "err_max": err_max, "desfase": desfase, "err_th": err_th,
            "mandos_iguales": int(mandos), "n": n, "n_mov": len(mov)}


# ── pila ─────────────────────────────────────────────────────────────────
def _puerto_ocupado(puerto: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", puerto), timeout=0.2):
            return True
    except OSError:
        return False


def fabricar_coordinador(fuente: Any, canal: Any, entorno: Any) -> Any:
    """El coordinador del laboratorio (F2, τ_c por defecto), sin supervisor:
    la réplica lo cambia por corrida."""
    import demo_obstaculo_movil as demo
    return demo.CoordinadorConObstaculo(fuente, canal, entorno, N_AGENTES, 10,
                                        supervisor=None, formulacion="F2",
                                        tau_prediccion_s=demo.TAU_PREDICCION_S)


@dataclass
class Pila:
    sim: Any
    fuente: Any
    canal: Any
    entorno: Any
    coord: Any
    supervisor: Any
    registro: List[Dict[str, Any]]
    estado: Dict[str, Any]

    def cerrar(self) -> None:
        for paso in (self.canal.cerrar, self.fuente.cerrar, self.sim.detener):
            try:
                paso()
            except Exception:                                   # noqa: BLE001
                pass
        try:
            atexit.unregister(self.coord._detener_seguro)
        except Exception:                                       # noqa: BLE001
            pass


def armar_pila(puerto: int, poses_iniciales_env: Dict[int, Tuple[float, float, float]]) -> Pila:
    """Simulador con el 4 reproducido + la pila del laboratorio."""
    import coordinador_enjambre as ce
    import demo_obstaculo_movil as demo
    from simulador_robotat import FallasSimulador
    base = puerto + DESPLAZAMIENTO_RUEDAS
    ids = [cfg.MAPEO_AGENTES[i].id_robot for i in range(N_AGENTES)] + [ID_OBSTACULO]
    ocupados = [p for p in [puerto] + [base + r for r in ids] if _puerto_ocupado(p)]
    if ocupados:
        raise ErrorReplica(f"puertos ocupados {ocupados}: ¿otro simulador corriendo?")
    if not (ce.CBF_ACTIVO and ce.ESCAPE_ACTIVO):
        raise ErrorReplica("CBF y escape tienen que estar encendidos (como en el lab)")
    cfg.activar_simulador_local(puerto_poses=puerto, puerto_base=base)
    aplicar_calibracion_identidad()
    mapeo = {cfg.MAPEO_AGENTES[i].id_robot: cfg.MAPEO_AGENTES[i].id_marcador
             for i in range(N_AGENTES)}
    mapeo[ID_OBSTACULO] = ID_OBSTACULO
    poses_lab = {rid: env_a_lab(*p, rid) for rid, p in poses_iniciales_env.items()}
    sim = _clase_simulador_replay()(mapeo, poses_lab, FallasSimulador(),
                                    puerto_poses=puerto, puerto_base=base)
    sim.iniciar()
    try:
        fuente, canal, entorno = demo.construir_con_obstaculo(
            N_AGENTES, True, ID_OBSTACULO, ID_OBSTACULO)
        supervisor = _clase_supervisor_replay()(
            fuente, canal, lambda x, y, th: sim.fijar_pose_env(ID_OBSTACULO, x, y, th))
        coord = fabricar_coordinador(fuente, canal, entorno)
        registro: List[Dict[str, Any]] = []
        estado: Dict[str, Any] = {"episodio": 0}
        coord._observador_paso = demo.crear_observador(coord, canal, registro, estado)
    except BaseException:
        sim.detener()
        raise
    if getattr(fuente, "_intervalo_ticks", 10) != coord.pasos_por_decision:
        raise ErrorReplica("la fuente no consulta una vez por decisión")
    return Pila(sim, fuente, canal, entorno, coord, supervisor, registro, estado)


def poses_env_de(toma: TomaReplica, condicion: str) -> Dict[int, Tuple[float, float, float]]:
    poses = {cfg.MAPEO_AGENTES[i].id_robot: toma.poses_iniciales[i] for i in range(N_AGENTES)}
    if condicion == CON:
        f0 = toma.traza_obstaculo[0]
        poses[ID_OBSTACULO] = (f0["x"], f0["y"], f0["th"])
    else:
        poses[ID_OBSTACULO] = ESTACIONAMIENTO_ENV
    return poses


def correr_una(pila: Pila, toma: TomaReplica, condicion: str, tau: float, rep: int,
               pasada: str, sha_pila: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]],
                                                   List[Dict[str, Any]]]:
    """Una corrida: teletransporte, rampa, régimen, la toma por el lazo de
    evaluación y el cierre (b). Devuelve (fila del contrato, decisiones,
    traza del 4 de la réplica)."""
    import analizar_campana_l2 as A
    import demo_obstaculo_movil as demo
    from lanzar_robotat import leer_poses_estables
    if condicion == CON and not toma.traza_obstaculo:
        raise ErrorReplica(f"intento {toma.intento}: sin traza del 4")
    inicio = datetime.now().isoformat(timespec="seconds")
    pila.sim.fallas.retardo_actuacion_s = float(tau)
    pila.canal.detener_todo(silencioso=True)
    time.sleep(0.2)
    pila.sim.teletransportar_env(poses_env_de(toma, condicion))
    time.sleep(0.2)
    pila.fuente.reiniciar()
    medidas = leer_poses_estables(pila.fuente, N_AGENTES)
    if len(medidas) != N_AGENTES:
        raise ErrorReplica(f"intento {toma.intento}: la pila no ve a los {N_AGENTES} agentes")
    err_xy = max(float(np.linalg.norm(medidas[i][:2] - np.array(toma.poses_iniciales[i][:2])))
                 for i in range(N_AGENTES))
    err_th = max(abs(_envolver(float(medidas[i][2]) - toma.poses_iniciales[i][2]))
                 for i in range(N_AGENTES))
    if err_xy > UMBRAL_POSE_INICIAL_M or err_th > UMBRAL_POSE_INICIAL_RAD:
        raise ErrorReplica(f"intento {toma.intento}: pose inicial con error {err_xy:.2e} m / "
                           f"{err_th:.2e} rad: falla de la réplica, se detiene")
    pila.canal.historial_mandos_obstaculo.clear()
    pila.canal.ultimo_mando_obstaculo = (0.0, 0.0)
    pila.canal.decisiones_enviadas = int(toma.decisiones_previas)
    pila.canal.factor_operativo = float(toma.factor)
    pila.coord.tau_prediccion_s = float(toma.tau_prediccion_s)
    if condicion == CON:
        pila.supervisor.cargar_traza(toma.traza_obstaculo)
        pila.coord.supervisor = pila.supervisor
    else:
        pila.coord.supervisor = None
    pila.estado["episodio"] = toma.intento
    try:
        res = demo.correr_toma(pila.coord, pila.canal, pila.fuente, pila.entorno,
                               toma.semilla, toma.decisiones, pila.registro,
                               toma.rpm_aborto, lazo="evaluacion")
    except RuntimeError as exc:
        pila.canal.detener_todo(silencioso=True)
        res = {"valido": 0, "motivo": f"RÉPLICA: {exc}", "decisiones": 0}
    traza_rep = list(pila.supervisor.traza) if condicion == CON else []
    cierre = evaluar_cierre_b(traza_rep, toma.traza_obstaculo) if condicion == CON else None
    tau_s = A.TAU_PRINCIPAL if tau == 0.0 else A.TAU_SENSIBILIDAD
    fila: Dict[str, Any] = {
        "campana": toma.campana, "fuente_tomas": toma.fuente_tomas,
        "id_sesion": toma.id_sesion, "intento_campana": toma.intento,
        "semilla": toma.semilla, "condicion": condicion, "tau_s": tau_s, "rep": rep,
        "pasada": pasada, "inicio": inicio, "sha256_pila": sha_pila,
        "decisiones_previas": toma.decisiones_previas,
        "valido": int(res.get("valido", 0) or 0), "motivo": res.get("motivo", ""),
        "decisiones": res.get("decisiones", 0), "cobertura_aoi": res.get("cobertura_aoi", ""),
        "d_min_obst_medida": res.get("d_min_obst_medida", "") if condicion == CON else "",
        **{c: res.get(c, "") for c in A.SEGURIDAD},
        "frenos_sombra": res.get("frenos", "") if condicion == CON else "",
        "cierre_b_ok": cierre["ok"] if cierre else "",
        "cierre_b_err_max_m": cierre["err_max"] if cierre else "",
        "cierre_b_desfase": cierre["desfase"] if cierre else "",
        "formato": toma.formato, "error_pose_inicial_m": err_xy,
        "error_rumbo_inicial_rad": err_th, "factor": toma.factor,
        "rpm_aborto": toma.rpm_aborto, "tau_prediccion_s": toma.tau_prediccion_s,
        "duracion_s": res.get("duracion_s", ""), "ciclo_p95_ms": res.get("ciclo_p95_ms", ""),
        "ciclos_sobre_100ms": res.get("ciclos_sobre_100ms", ""),
        "frenos_sombra_detalle": res.get("frenos_detalle", "") if condicion == CON else "",
        "cierre_b_n": cierre["n"] if cierre else "",
        "cierre_b_n_mov": cierre["n_mov"] if cierre else "",
        "cierre_b_err_th_rad": cierre["err_th"] if cierre else "",
        "cierre_b_mandos_iguales": cierre["mandos_iguales"] if cierre else "",
    }
    clave = {"intento_campana": toma.intento, "condicion": condicion, "tau_s": tau_s,
             "rep": rep, "pasada": pasada, "inicio": inicio}
    decisiones = [{**clave, **d} for d in pila.registro]
    pila.registro.clear()
    traza = [{**clave, **f} for f in traza_rep]
    return fila, decisiones, traza


# ── escritura incremental y reanudación ──────────────────────────────────
def columnas_contrato() -> List[str]:
    import analizar_campana_l2 as A
    return list(A.COLUMNAS_REPLICA) + list(EXTRAS)


def sha256_de_pila() -> Tuple[str, Dict[str, str]]:
    from campana_obstaculo import ARCHIVOS_CONGELADOS, hashes_congelados
    huellas = hashes_congelados(tuple(ARCHIVOS_CONGELADOS) + ARCHIVOS_PILA_EXTRA)
    faltan = [a for a, h in huellas.items() if h == "FALTA"]
    if faltan:
        raise ErrorReplica(f"faltan archivos de la pila: {faltan}")
    return hashlib.sha256(json.dumps(huellas, sort_keys=True).encode("utf-8")).hexdigest(), huellas


class Escritor:
    """Tres CSV nuevos por lanzamiento (tomas, decisiones, traza del 4),
    fila a fila con fsync; la fila de tomas va AL FINAL de cada corrida."""

    def __init__(self, carpeta: Path) -> None:
        carpeta.mkdir(parents=True, exist_ok=True)
        sello = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.rutas = {n: carpeta / f"{sello}_replica_{n}.csv"
                      for n in ("tomas", "decisiones", "obstaculo")}
        for r in self.rutas.values():
            if r.exists():
                raise ErrorReplica(f"ya existe {r}")
        self._columnas: Dict[str, List[str]] = {"tomas": columnas_contrato()}

    def agregar(self, nombre: str, filas: Iterable[Dict[str, Any]]) -> None:
        filas = list(filas)
        if not filas:
            return
        ruta = self.rutas[nombre]
        cols = self._columnas.get(nombre)
        if cols is None:
            cols = []
            for f in filas:
                cols += [c for c in f if c not in cols]
            self._columnas[nombre] = cols
        nuevo = not ruta.exists()
        with open(ruta, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore",
                               lineterminator="\n")
            if nuevo:
                w.writeheader()
            for f in filas:
                w.writerow({c: (repr(v) if isinstance(v, float) else v)
                            for c, v in f.items()})
            fh.flush()
            os.fsync(fh.fileno())


def claves_hechas(carpeta: Path) -> Dict[Tuple[int, str, float, int], Dict[str, str]]:
    """(intento, condición, τ, rep) ya escritas en TODOS los *_replica_tomas."""
    hechas: Dict[Tuple[int, str, float, int], Dict[str, str]] = {}
    if not carpeta.is_dir():
        return hechas
    for ruta in sorted(carpeta.glob("*_replica_tomas.csv")):
        datos = ruta.read_bytes()
        if datos and not datos.endswith(b"\n"):
            raise ErrorReplica(f"{ruta.name} termina en una línea truncada: revisarlo a "
                               f"mano antes de reanudar (no se edita en silencio)")
        for r in _leer(ruta):
            clave = (int(float(r["intento_campana"])), r["condicion"], float(r["tau_s"]),
                     int(float(r["rep"])))
            if clave in hechas:
                raise ErrorReplica(f"clave repetida {clave} en {carpeta}")
            hechas[clave] = r
    return hechas


def validar_hechas(hechas: Dict[Tuple, Dict[str, str]], tomas: Sequence[TomaReplica],
                   sha_pila: str) -> None:
    """Las corridas ya escritas en la carpeta tienen que ser de ESTA pila,
    de esta campaña y de estas tomas (semilla y rampa): si no, reanudar
    mezclaría versiones del código o datos ajenos (revisión del 10-10)."""
    por_intento = {t.intento: t for t in tomas}
    campanas = {t.campana for t in tomas}
    malas = []
    for clave, r in hechas.items():
        if r.get("sha256_pila") != sha_pila:
            malas.append(f"{clave}: otra pila ({str(r.get('sha256_pila'))[:12]})")
        elif r.get("campana") not in campanas:
            malas.append(f"{clave}: de la campaña {r.get('campana')!r}")
        else:
            t = por_intento.get(clave[0])
            if t is not None and (int(float(r["semilla"])) != t.semilla or
                                  int(float(r["decisiones_previas"])) != t.decisiones_previas):
                malas.append(f"{clave}: semilla o rampa distintas de la toma")
    if malas:
        raise ErrorReplica(f"la carpeta tiene {len(malas)} corridas que no son de esta "
                           f"réplica (p. ej. {malas[0]}): usar otra --salida")


def completitud(tomas: Sequence[TomaReplica], hechas: Dict[Tuple, Dict[str, str]],
                condiciones: Sequence[Tuple[str, float]]) -> Tuple[List[str], List[str]]:
    """(grupos con la pasada normal incompleta, grupos con 0 válidas a los
    que les falta la pasada suplementaria completa)."""
    faltan_normales, faltan_suplementarias = [], []
    for t in tomas:
        for cond, tau in condiciones:
            normales = [hechas.get((t.intento, cond, tau, r)) for r in REPS_NORMALES]
            if any(x is None for x in normales):
                faltan_normales.append(f"intento {t.intento} {cond} τ={tau}")
                continue
            if any(str(x["valido"]).strip() in ("1", "1.0") for x in normales):
                continue
            if any((t.intento, cond, tau, r) not in hechas for r in (4, 5, 6)):
                faltan_suplementarias.append(f"intento {t.intento} {cond} τ={tau}")
    return faltan_normales, faltan_suplementarias


def plan_de_corridas(tomas: Sequence[TomaReplica], hechas: Dict[Tuple, Dict[str, str]],
                     suplementaria: bool, condiciones: Sequence[Tuple[str, float]]
                     ) -> List[Tuple[TomaReplica, str, float, int, str]]:
    """Lo que falta correr. Normal: reps 1–3 de cada (toma, condición, τ).
    Suplementaria: sólo los grupos con 0 válidas en la normal, reps 4–6."""
    plan = []
    if not suplementaria:
        for rep in REPS_NORMALES:
            for t in tomas:
                for cond, tau in condiciones:
                    if (t.intento, cond, tau, rep) not in hechas:
                        plan.append((t, cond, tau, rep, "normal"))
        return plan
    for t in tomas:
        for cond, tau in condiciones:
            normales = [hechas.get((t.intento, cond, tau, r)) for r in REPS_NORMALES]
            if any(x is None for x in normales):
                raise ErrorReplica(f"intento {t.intento} {cond} τ={tau}: la pasada normal "
                                   f"no está completa (correr --reanudar primero)")
            if any(str(x["valido"]).strip() in ("1", "1.0") for x in normales):
                continue
            for rep in (4, 5, 6):
                if (t.intento, cond, tau, rep) not in hechas:
                    plan.append((t, cond, tau, rep, "suplementaria"))
    return plan


# ── principal ────────────────────────────────────────────────────────────
def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Réplica pareada con el obstáculo reproducido")
    fuente = ap.add_mutually_exclusive_group(required=True)
    fuente.add_argument("--campana", help="nombre de la campaña (libro)")
    fuente.add_argument("--carpeta-vieja", type=Path,
                        help="un ensayo L2 del 07-10 (formato viejo), para probar")
    fuente.add_argument("--episodios-3009", action="store_true",
                        help="cierre (a3): episodios del 30-09, sólo sin obstáculo")
    fuente.add_argument("--evaluar-a3", type=Path, default=None, metavar="DIR",
                        help="evalúa el cierre (a3) sobre la salida de --episodios-3009")
    ap.add_argument("--base", type=Path, default=DIR_DEMO)
    ap.add_argument("--dir-hw", type=Path, default=None)
    ap.add_argument("--salida", type=Path, default=None,
                    help="por defecto <base>/replica_campana/<nombre> (campaña)")
    ap.add_argument("--puerto", type=int, default=PUERTO_POR_DEFECTO)
    ap.add_argument("--reanudar", action="store_true")
    ap.add_argument("--suplementaria", action="store_true")
    ap.add_argument("--verificar", action="store_true",
                    help="carga, auditoría e ida y vuelta, sin simulador")
    ap.add_argument("--solo-tomas", default=None,
                    help="intentos a correr, separados por coma (pruebas)")
    ap.add_argument("--reps", type=int, default=None,
                    help="sólo para probar la tubería: menos de 3 repeticiones")
    a = ap.parse_args(argv)
    if a.evaluar_a3 is not None:
        try:
            r = evaluar_cierre_a3(a.evaluar_a3)
        except ErrorReplica as exc:
            print(f"✘ [a3] {exc}")
            return 2
        sello = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta = a.evaluar_a3 / f"cierre_a3_{sello}.json"
        n = 2
        while ruta.exists():
            ruta = a.evaluar_a3 / f"cierre_a3_{sello}_{n}.json"
            n += 1
        ruta.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        resultado = {True: "PASA", False: "NO PASA", None: "SIN VEREDICTO"}[r.get("pasa")]
        print(f"[a3] regla {r['estado']} · resultado: {resultado} · E = {r['E']}, "
              f"δ = {r['delta_umbral']:.5f}, media Δ = {r.get('media')}, IC95 {r.get('ic95')}"
              + (f" · {r['motivo_sin_veredicto']}" if r.get("pasa") is None else "")
              + f" → {ruta.name}")
        return {True: 0, False: 1, None: 3}[r.get("pasa")]
    try:
        if a.campana:
            tomas = cargar_campana(a.base, a.campana, a.dir_hw)
            salida = a.salida or (a.base / "replica_campana" / a.campana)
            condiciones = CONDICIONES_ORDEN
        elif a.carpeta_vieja:
            tomas = cargar_carpeta_vieja(a.carpeta_vieja)
            if a.salida is None:
                raise ErrorReplica("con --carpeta-vieja hay que dar --salida")
            salida = a.salida
            condiciones = CONDICIONES_ORDEN
        else:
            tomas = cargar_episodios_3009(episodios=episodios_a3())
            print(f"[réplica] cierre (a3), {A3_ESTADO}: {len(tomas)} episodios del 30-09")
            if a.salida is None:
                raise ErrorReplica("con --episodios-3009 hay que dar --salida")
            salida = a.salida
            condiciones = ((SIN, 0.0),)
        if (a.solo_tomas or a.reps is not None) and (
                a.salida is None or (a.campana and a.salida.resolve() == (
                    a.base / "replica_campana" / a.campana).resolve())):
            raise ErrorReplica("--solo-tomas y --reps son para probar: exigen una "
                               "--salida propia, distinta de la de la campaña")
        if a.solo_tomas:
            quiero = {int(x) for x in a.solo_tomas.split(",")}
            tomas = [t for t in tomas if t.intento in quiero]
        print(f"[réplica] {len(tomas)} tomas: {[t.intento for t in tomas]}")
        for t in tomas:
            for av in t.avisos:
                print(f"  ⓘ intento {t.intento}: {av}")
        problemas = auditar(tomas)
        if problemas:
            raise ErrorReplica("auditoría: " + "; ".join(problemas))
        aplicar_calibracion_identidad()
        peor = verificar_ida_y_vuelta(tomas)
        print(f"[réplica] ida y vuelta env→lab→env: error máx {peor:.2e}")
        if peor >= 1e-9:
            raise ErrorReplica(f"ida y vuelta con error {peor}")
        sha_pila, huellas = sha256_de_pila()
        if a.verificar:
            print("[réplica] --verificar: chequeos OK; no se levanta el simulador.")
            return 0
        hechas = claves_hechas(salida)
        if hechas and not (a.reanudar or a.suplementaria):
            raise ErrorReplica(f"{salida} ya tiene {len(hechas)} corridas: usar --reanudar")
        validar_hechas(hechas, tomas, sha_pila)
        plan = plan_de_corridas(tomas, hechas, a.suplementaria, condiciones)
        if a.reps is not None:
            plan = [p for p in plan if p[3] <= a.reps]
        print(f"[réplica] {len(plan)} corridas por hacer (~{len(plan) * 51 / 60:.0f} min)")
        if not plan:
            return _informar_completitud(tomas, salida, condiciones)
        escritor = Escritor(salida)
        (salida / f"{escritor.rutas['tomas'].stem.replace('_replica_tomas', '')}"
         f"_replica_pila.json").write_text(json.dumps(
             {"sha256_pila": sha_pila, "huellas": huellas}, indent=1), encoding="utf-8")
        pila = armar_pila(a.puerto, poses_env_de(plan[0][0], plan[0][1]))
        try:
            for j, (t, cond, tau, rep, pasada) in enumerate(plan, 1):
                fila, dec, tr = correr_una(pila, t, cond, tau, rep, pasada, sha_pila)
                escritor.agregar("decisiones", dec)
                escritor.agregar("obstaculo", tr)
                escritor.agregar("tomas", [fila])
                print(f"[{j}/{len(plan)}] intento {t.intento} {cond} τ={tau} rep {rep}: "
                      f"válida {fila['valido']} cobertura {fila['cobertura_aoi']}"
                      + (f" cierre(b) {fila['cierre_b_ok']} err {fila['cierre_b_err_max_m']}"
                         if cond == CON else "") + f" {fila['motivo'] or ''}", flush=True)
                if sha256_de_pila()[0] != sha_pila:
                    raise ErrorReplica("cambió la pila durante la réplica: se detiene")
        finally:
            pila.cerrar()
        return _informar_completitud(tomas, salida, condiciones)
    except ErrorReplica as exc:
        print(f"✘ [réplica] {exc}")
        return 2


def _informar_completitud(tomas: Sequence[TomaReplica], salida: Path,
                          condiciones: Sequence[Tuple[str, float]]) -> int:
    """0 si la réplica está completa; 3 (y la lista) si falta la pasada
    normal de algún grupo o la suplementaria de un grupo con 0 válidas."""
    normales, suplementarias = completitud(tomas, claves_hechas(salida), condiciones)
    if normales:
        print(f"⚠ [réplica] INCOMPLETA: falta la pasada normal de {len(normales)} grupos "
              f"(p. ej. {normales[0]}): correr --reanudar")
    if suplementarias:
        print(f"⚠ [réplica] {len(suplementarias)} grupos con 0 válidas sin su pasada "
              f"suplementaria: correr --suplementaria → {suplementarias}")
    if normales or suplementarias:
        return 3
    print("[réplica] completa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
