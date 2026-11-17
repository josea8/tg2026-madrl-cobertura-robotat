"""
analizar_campana_l2.py
======================
Análisis FIJADO ANTES de la campaña L2 con el obstáculo móvil. Aplica
`tesis/PLAN_ANALISIS_campana_L2.md` (las secciones se citan como §n); su
sha256 y el de este archivo quedan en el libro al crear la campaña.

  PRINCIPAL  (§3): d_k = cobertura hw − media de las réplicas válidas con el 4
             reproducido y τ = 0; media de d_k con IC95 t (n − 1 gl).
             Referencias: Wilcoxon y bootstrap percentil. Sin δ: si el IC
             contiene el 0, "no hay brecha detectable" y la cota (95 %).
  SENSIB.    (§3a): A sin arranques fuera del soporte (criterio del 30-09),
             B sin retroceso, C sin freno, D sin rampa, E réplica τ = 0.45.
  SEGURIDAD  (§4): sobre TODAS las tomas corridas; pareada hw − réplica
             (media y mínimo de las repeticiones) en las incluidas.
  COSTO      (§5): réplica con obstáculo − sin obstáculo, pareado.
  30-09      (§6): descriptivo, recalculado del crudo empaquetado.
  CIERRE     (§2): el criterio de seguridad (dos tomas corridas con contacto
             medido cierran la campaña solas) se recalcula del crudo y se
             verifica contra el libro.

Se niega (§8) si la campaña no está cerrada, no es de hardware o cambió el
sha256 del plan, de este script o de `campana_obstaculo.py`, salvo
`--desvio "motivo"`. `--ensayo` corre sobre datos de PRUEBA (nunca sobre
una campaña de hardware) y rotula todo como ENSAYO. Integridad (§0, §9):
el libro manda; el régimen de cada toma, el cruce libro↔CSV, el contrato
de la réplica, su completitud y su cegado se comprueban y, si fallan, el
análisis se detiene con su código.

    python analizar_campana_l2.py --campana NOMBRE
    python analizar_campana_l2.py --campana NOMBRE --ensayo --base DIR

Salida en `resultados_demo_obstaculo/analisis_campana/<nombre>_<fecha>/`
(§10), nunca sobre una previa. Sólo lee los datos. Desvíos con ddof = 1.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
from scipy import stats

from campana_obstaculo import (PREFIJO_CIERRE_SEGURIDAD, TOMAS_CON_CONTACTO_PARA_CERRAR,
                               Campana, ErrorCampana, contacto_de_toma,
                               inclusion_campana, sha256_archivo)

_CARPETA = Path(__file__).resolve().parent
_TESIS = _CARPETA.parents[2]
DIR_DEMO = _CARPETA / "resultados_demo_obstaculo"
DIR_3009 = _TESIS / "REPORTE_2026-09-30_datos" / "csv"
RUTA_PLAN = _TESIS / "PLAN_ANALISIS_campana_L2.md"
CLAVE_PLAN = "TESIS/PLAN_ANALISIS_campana_L2.md"
CLAVE_SCRIPT = "analizar_campana_l2.py"
CLAVE_LIBRO = "campana_obstaculo.py"

UMBRAL_CONTACTO_M = 0.15            # §4a, el del protocolo
META_PLAN, MINIMO_PLAN, TOPE_PLAN = 50, 30, 100   # §2 (decisión 2)
DECISIONES_ARRANQUE = 50            # §3a D (cfg.DECISIONES_ARRANQUE al fijar)
TAU_PRINCIPAL = 0.0
TAU_SENSIBILIDAD = 0.45
CONDICIONES_PLAN = {("con_obstaculo", TAU_PRINCIPAL), ("sin_obstaculo", TAU_PRINCIPAL),
                    ("con_obstaculo", TAU_SENSIBILIDAD)}
REPS_NORMALES = {1, 2, 3}           # decisión 6
CIERRE_B_ERR_MAX_M = 0.001          # §7: ≤ 1 mm y sin desfase
CIERRE_B_RUMBO_MAX_RAD = 1e-6       # §7: rumbo y mandos (José, 10-10)
CIERRE_B_FALLAS_MAX = 2             # decisión 8: más de 2 → error de la réplica
BOOT_N = 10_000
BOOT_SEMILLA = 20261008
#: "Qué se mide" (encabezado del plan): el régimen de cada toma corrida.
#: El 2 en lugar del 6 (el 6 dejó de girar bien y el 3 no respondió el 16-10):
#: composición aprobada por José el 17-10; mismo orden que MAPEO_AGENTES.
ROBOTS_AGENTES = ("1", "5", "8", "2", "9")
REGIMEN = {"factor": 0.40, "tau_prediccion_s": 0.65}
REGIMEN_TEXTO = {"formulacion": "F2", "colocacion": "auto", "lazo": "evaluacion"}
SEGURIDAD = ("d_pared_min", "viola_018", "colisiones_015", "colisiones_022",
             "frac_cbf", "n_escape")
COLUMNAS_REPLICA = (
    "campana", "fuente_tomas", "id_sesion", "intento_campana", "semilla",
    "condicion", "tau_s", "rep", "pasada", "inicio", "sha256_pila",
    "decisiones_previas", "valido", "motivo", "decisiones",
    "cobertura_aoi", "d_min_obst_medida", *SEGURIDAD, "frenos_sombra",
    "cierre_b_ok", "cierre_b_err_max_m", "cierre_b_desfase",
    "cierre_b_err_th_rad", "cierre_b_mandos_iguales",
)
CONDICIONES = ("con_obstaculo", "sin_obstaculo")
COSTO_CONDICIONAL = ("El costo es condicional a los arranques de la campaña (blancos "
                     "a ≥ 0.65 m del 4 medido, chequeo de arranque a 0.50 m) y a la "
                     "trayectoria medida del 4, que incluye los frenos del hw.")

#: Exit codes.
SALIDA_NEGADO = 2          # requisito del §8 sin cumplir
SALIDA_REPLICA = 3         # error de la réplica (contrato, completitud, cegado, cierre b)
SALIDA_INTEGRIDAD = 4      # el libro y los CSV del hw no coinciden, o el régimen


class ErrorAnalisis(RuntimeError):
    def __init__(self, mensaje: str, codigo: int) -> None:
        super().__init__(mensaje)
        self.codigo = codigo


def _f(x: Any) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _es_uno(x: Any) -> bool:
    return str(x).strip() in ("1", "1.0", "True", "true")


def _entero(x: Any, que: str, codigo: int) -> int:
    try:
        return int(float(str(x).strip()))
    except (TypeError, ValueError):
        raise ErrorAnalisis(f"{que}: {x!r} no es un entero", codigo) from None


def leer_csv(ruta: Path) -> List[Dict[str, str]]:
    with open(ruta, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ── estadística ──────────────────────────────────────────────────────────
def semiancho_t(sd: float, n: int) -> float:
    return float(stats.t.ppf(0.975, n - 1) * sd / math.sqrt(n))


def bootstrap_media(d: np.ndarray, n_boot: int = BOOT_N,
                    semilla: int = BOOT_SEMILLA) -> Tuple[float, float]:
    rng = np.random.default_rng(semilla)
    medias = d[rng.integers(0, len(d), size=(n_boot, len(d)))].mean(axis=1)
    return float(np.percentile(medias, 2.5)), float(np.percentile(medias, 97.5))


def wilcoxon_p(d: np.ndarray) -> Optional[float]:
    if len(d) < 2 or not np.any(d != 0):
        return None
    try:
        return float(stats.wilcoxon(d, method="exact" if len(d) <= 25
                                    else "approx").pvalue)
    except ValueError:
        return None


def resumen_pareado(d: Sequence[float], bootstrap: bool = False) -> Dict[str, Any]:
    """Media con IC95 t (n − 1 gl), mediana, Wilcoxon, signos y, si se
    pide, bootstrap percentil de la media."""
    d = np.asarray(d, dtype=float)
    n = len(d)
    out: Dict[str, Any] = {"n": n}
    if n == 0:
        return out
    out.update(media=float(d.mean()), mediana=float(np.median(d)),
               positivas=int((d > 0).sum()), negativas=int((d < 0).sum()),
               ceros=int((d == 0).sum()))
    if n >= 2:
        sd = float(d.std(ddof=1))
        w = semiancho_t(sd, n)
        out.update(sd=sd, semiancho=w, ic95=[out["media"] - w, out["media"] + w],
                   t_p=(float(stats.ttest_1samp(d, 0).pvalue) if sd > 0 else None),
                   wilcoxon_p=wilcoxon_p(d))
        if bootstrap:
            out["bootstrap_ic95"] = list(bootstrap_media(d))
    return out


def clopper_pearson(k: int, n: int) -> Dict[str, Any]:
    if n == 0:
        return {"k": k, "n": n}
    ic = stats.binomtest(k, n).proportion_ci(confidence_level=0.95, method="exact")
    return {"k": k, "n": n, "proporcion": k / n, "ic95": [float(ic.low), float(ic.high)]}


def conclusion(r: Dict[str, Any]) -> str:
    """§3: la redacción fijada antes (decisión 5, sin δ)."""
    if r.get("n", 0) < 2:
        return f"n = {r.get('n', 0)}: sin IC."
    a, b = r["ic95"]
    txt = (f"hw − réplica = {r['media']:+.4f}, IC95 [{a:+.4f}, {b:+.4f}] "
           f"(n = {r['n']})")
    if a <= 0 <= b:
        return (f"No hay brecha detectable: {txt}; con esta precisión, la "
                f"brecha está acotada, con 95 % de confianza, a |brecha| ≤ "
                f"{max(abs(a), abs(b)):.4f}. No se afirma equivalencia.")
    return f"Brecha detectable: {txt}."


# ── criterios (§3a) ──────────────────────────────────────────────────────
def fuera_de_soporte(r, n=5, tol=0.12, sep=0.31):
    """El criterio del 30-09, sin cambios (`pareo_final_0930.py`; una
    prueba compara los dos con `ast`)."""
    motivos = []
    pts = []
    for i in range(n):
        est = (r.get(f"col_estado_a{i}") or "").strip()
        try:
            x0, y0 = float(r[f"x0_a{i}"]), float(r[f"y0_a{i}"])
            pts.append((x0, y0))
            dist = math.hypot(x0 - float(r[f"blanco_x_a{i}"]), y0 - float(r[f"blanco_y_a{i}"]))
        except (KeyError, ValueError, TypeError):
            dist = float("nan")
        if (est and est != "listo") or (dist == dist and dist > tol):
            motivos.append(f"a{i} {est or '-'} {dist:.2f} m")
    dmin = min((math.dist(p, q) for k, p in enumerate(pts) for q in pts[k + 1:]), default=float("inf"))
    if dmin < sep:
        motivos.append(f"par a {dmin:.2f} m")
    return motivos


def con_retroceso(r: Dict[str, str]) -> bool:
    return bool((r.get("retrocesos_detalle") or "").strip())


def con_freno(r: Dict[str, str]) -> bool:
    return (_f(r.get("frenos")) or 0.0) > 0


def con_rampa(r: Dict[str, str]) -> bool:
    previas = _f(r.get("decisiones_previas"))
    if previas is None:
        raise ErrorAnalisis(f"toma {r.get('toma')}: falta decisiones_previas",
                            SALIDA_INTEGRIDAD)
    return previas < DECISIONES_ARRANQUE


def problemas_regimen(r: Dict[str, str], robot_obstaculo: int) -> List[str]:
    """'Qué se mide' del plan, por toma corrida: factor, F2, τ_c, colocación
    automática, lazo de evaluación, los robots del enjambre y el del 4."""
    p = []
    for c, v in REGIMEN.items():
        x = _f(r.get(c))
        if x is None or abs(x - v) > 1e-9:
            p.append(f"{c} {r.get(c)!r} (plan {v})")
    for c, v in REGIMEN_TEXTO.items():
        if (r.get(c) or "") != v:
            p.append(f"{c} {r.get(c)!r} (plan {v!r})")
    robots = tuple(str(r.get(f"robot_a{i}", "")).strip() for i in range(5))
    if robots != ROBOTS_AGENTES:
        p.append(f"robots {robots} (plan {ROBOTS_AGENTES})")
    if str(r.get("obst_robot", "")).strip() != str(robot_obstaculo):
        p.append(f"obst_robot {r.get('obst_robot')!r} (plan {robot_obstaculo})")
    return p


# ── hardware: el libro manda (§0) ────────────────────────────────────────
def cargar_hw(campana: Campana, dir_hw: Path, ensayo: bool = False) -> Dict[str, Any]:
    filas = campana.filas()
    cerrada = any(f["tipo"] == "cierre_campana" for f in filas)
    if cerrada:
        i_cierre = next(i for i, f in enumerate(filas) if f["tipo"] == "cierre_campana")
        tardias = [f for f in filas[i_cierre + 1:] if f["tipo"] in ("reserva", "resultado")]
        if tardias:
            raise ErrorAnalisis(f"el libro tiene {len(tardias)} reservas/resultados "
                                f"DESPUÉS del cierre de la campaña", SALIDA_INTEGRIDAD)
    resultados: Dict[int, Dict[str, str]] = {}
    for f in filas:
        if f["tipo"] != "resultado":
            continue
        k = int(f["intento"])
        if k in resultados:
            raise ErrorAnalisis(f"el libro tiene dos resultados del intento {k}",
                                SALIDA_INTEGRIDAD)
        resultados[k] = f
    reservas = {int(f["intento"]): int(f["semilla"]) for f in filas
                if f["tipo"] == "reserva"}
    marcadas_por_el_analisis = []
    for k in sorted(set(reservas) - set(resultados)):
        if not (cerrada or ensayo):
            raise ErrorAnalisis(f"reservas sin resultado en el libro: intento {k} "
                                f"(¿sesión abierta?)", SALIDA_INTEGRIDAD)
        # Campaña cerrada: la reserva colgada vale "interrumpida" (regla del
        # libro) y se declara.
        resultados[k] = {"tipo": "resultado", "intento": str(k), "semilla": str(reservas[k]),
                         "estado": "interrumpida", "incluida": "0", "valido": "",
                         "motivo_inclusion": "reserva sin resultado",
                         "motivo": "marcada por el análisis", "archivo_tomas": "",
                         "regla_parada": "", "parada_respuesta": "", "frenos": "",
                         "d_min_obst_medida": ""}
        marcadas_por_el_analisis.append(k)
    sesiones = {f["id_sesion"] for f in filas if f["tipo"] == "apertura"}
    # Todos los CSV de tomas de las sesiones de la campaña (no sólo los que
    # nombra el libro: una sesión que sólo dejó interrumpidas también cuenta).
    csv_sesiones: Dict[str, List[Dict[str, str]]] = {}
    sha_csv: Dict[str, str] = {}
    for ruta in sorted(dir_hw.glob("*_L2_tomas*.csv")):
        datos = leer_csv(ruta)
        if any(r.get("id_sesion") in sesiones for r in datos):
            csv_sesiones[ruta.name] = datos
            sha_csv[ruta.name] = sha256_archivo(ruta)
    tomas: Dict[int, Dict[str, str]] = {}
    robot_o = int(campana.cabecera["robot_obstaculo"])
    for k, f in sorted(resultados.items()):
        if int(f["semilla"]) != reservas.get(k):
            raise ErrorAnalisis(f"intento {k}: semilla del resultado distinta de "
                                f"la reserva", SALIDA_INTEGRIDAD)
        if f["estado"] == "interrumpida":
            continue
        nombre = f["archivo_tomas"]
        if nombre not in csv_sesiones:
            raise ErrorAnalisis(f"falta el CSV de tomas {dir_hw / nombre}", SALIDA_INTEGRIDAD)
        cand = [r for r in csv_sesiones[nombre]
                if str(r.get("intento_campana", "")).strip() == str(k)]
        if len(cand) != 1:
            raise ErrorAnalisis(f"intento {k}: {len(cand)} filas en {nombre}",
                                SALIDA_INTEGRIDAD)
        r = cand[0]
        if (_f(r.get("semilla")) != float(f["semilla"])
                or r.get("campana") != campana.nombre):
            raise ErrorAnalisis(f"intento {k}: semilla o campaña de {nombre} "
                                f"distinta del libro", SALIDA_INTEGRIDAD)
        incl_csv = _es_uno(r.get("incluida"))
        incl_libro = _es_uno(f["incluida"])
        incl_codigo = bool(inclusion_campana(r)[0]) if f["estado"] == "corrida" else False
        if not (incl_csv == incl_libro == incl_codigo):
            raise ErrorAnalisis(f"intento {k}: inclusión libro {incl_libro}, CSV "
                                f"{incl_csv}, código {incl_codigo}", SALIDA_INTEGRIDAD)
        # El libro también guardó validez, frenos y distancia: deben coincidir.
        for c in ("valido", "frenos", "d_min_obst_medida"):
            a, b = _f(f.get(c)), _f(r.get(c))
            if a is not None and b is not None and a != b:
                raise ErrorAnalisis(f"intento {k}: {c} libro {f.get(c)} ≠ CSV "
                                    f"{r.get(c)}", SALIDA_INTEGRIDAD)
        if f["estado"] == "corrida":
            reg = problemas_regimen(r, robot_o)
            if reg:
                raise ErrorAnalisis(f"intento {k} fuera del régimen del plan: "
                                    + "; ".join(reg), SALIDA_INTEGRIDAD)
        tomas[k] = r
    # Criterio de seguridad (§2, José 09-10): contacto recalculado del CSV
    # en cada toma corrida, contra lo que anotó el libro; el cierre tiene
    # que venir después de la segunda sin ninguna reserva ni resultado en
    # el medio (ni antes ni después).
    contactos: List[Dict[str, Any]] = []
    for i, f in enumerate(filas):
        if f["tipo"] != "resultado" or f["estado"] != "corrida":
            continue
        k = int(f["intento"])
        c, que = contacto_de_toma(tomas[k])
        anotado = (f.get("contacto") or "").strip()
        if anotado and int(float(anotado)) != c:
            raise ErrorAnalisis(f"intento {k}: contacto libro {anotado} ≠ CSV {c}",
                                SALIDA_INTEGRIDAD)
        if c:
            contactos.append({"intento": k, "que": que, "indice": i})
    cierres = [(i, f) for i, f in enumerate(filas) if f["tipo"] == "cierre_campana"]
    por_criterio = bool(cierres) and _es_cierre_por_criterio(cierres[0][1])
    if len(contactos) >= TOMAS_CON_CONTACTO_PARA_CERRAR:
        i_n = contactos[TOMAS_CON_CONTACTO_PARA_CERRAR - 1]["indice"]
        entre = ([f for f in filas[i_n + 1:cierres[0][0]]
                  if f["tipo"] in ("reserva", "resultado")] if cierres else [])
        if not (por_criterio and cierres[0][0] > i_n and not entre):
            raise ErrorAnalisis(f"el criterio de seguridad no cerró la campaña al "
                                f"registrar la toma {contactos[TOMAS_CON_CONTACTO_PARA_CERRAR - 1]['intento']}, "
                                f"la {TOMAS_CON_CONTACTO_PARA_CERRAR}.ª con contacto",
                                SALIDA_INTEGRIDAD)
    elif por_criterio:
        raise ErrorAnalisis("cierre por el criterio de seguridad sin "
                            f"{TOMAS_CON_CONTACTO_PARA_CERRAR} tomas con contacto",
                            SALIDA_INTEGRIDAD)
    # Tomas que CORRIERON pero el libro marcó interrumpidas (corte entre el
    # fin de la toma y su anotación): entran a la seguridad, declaradas (§4a).
    interrumpidas = {k for k, f in resultados.items() if f["estado"] == "interrumpida"}
    corridas_sin_libro: List[Dict[str, Any]] = []
    for nombre, filas_csv in csv_sesiones.items():
        for r in filas_csv:
            k = _f(r.get("toma"))
            if (k is not None and int(k) in interrumpidas
                    and r.get("id_sesion") in sesiones
                    and _f(r.get("decisiones")) is not None):
                corridas_sin_libro.append({"intento": int(k), "archivo": nombre, "fila": r})
    # Recuento FÍSICO (§2): el criterio habla de tomas que CORRIERON con
    # contacto medido; el libro cuenta las que pudo anotar. Se suman las que
    # corrieron y el libro marcó interrumpidas: con fila en el CSV de tomas,
    # por su fila; cortadas a mitad (sin fila), por el CSV de decisiones.
    sesion_de_reserva = {int(f["intento"]): f["id_sesion"] for f in filas
                         if f["tipo"] == "reserva"}
    con_fila = {c["intento"]: c["fila"] for c in corridas_sin_libro}
    cortadas = _decisiones_de_intentos(dir_hw, interrumpidas - set(con_fila),
                                       sesion_de_reserva)
    fisicos = [(c["intento"], c["que"]) for c in contactos]
    for k in sorted(interrumpidas):
        if k in con_fila:
            c_, que_ = contacto_de_toma(con_fila[k])
            origen = "fila de tomas"
        elif k in cortadas:
            c_, que_ = _contacto_de_decisiones(cortadas[k])
            origen = "decisiones de una toma cortada"
        else:
            continue
        if c_:
            fisicos.append((k, f"{que_} [{origen}; el libro la marcó interrumpida]"))
    fisicos.sort()
    n_c = TOMAS_CON_CONTACTO_PARA_CERRAR
    debio = fisicos[n_c - 1][0] if len(fisicos) >= n_c else None
    # Incumplimiento: hubo intentos (reservas) DESPUÉS del cierre debido.
    despues = sorted(k for k in reservas if debio is not None and k > debio)
    incumplimiento = bool(despues)
    criterio = {
        "umbral_contacto_m": 0.15, "tomas_para_cerrar": TOMAS_CON_CONTACTO_PARA_CERRAR,
        "contactos_fisicos": [{"intento": k, "que": q} for k, q in fisicos],
        "n_contactos_fisicos": len(fisicos),
        "debio_cerrar_tras_intento": debio,
        "incumplimiento_del_criterio": incumplimiento,
        "intentos_despues_del_cierre_debido": [
            {"intento": k, "estado": resultados.get(k, {}).get("estado", "")}
            for k in despues],
        "tomas_con_contacto": [{"intento": c["intento"], "que": c["que"]} for c in contactos],
        "n_tomas_con_contacto": len(contactos),
        "cerro_por_criterio": por_criterio,
        "motivo_del_cierre": cierres[0][1]["motivo"] if cierres else "",
        "contactos_en_corridas_marcadas_interrumpidas": [
            {"intento": c["intento"], "que": contacto_de_toma(c["fila"])[1]}
            for c in corridas_sin_libro if contacto_de_toma(c["fila"])[0]],
    }
    return {"resultados": resultados, "tomas": tomas, "sha256_csv": sha_csv,
            "corridas_sin_libro": corridas_sin_libro, "filas_libro": filas,
            "marcadas_por_el_analisis": marcadas_por_el_analisis, "cerrada": cerrada,
            "criterio": criterio, "cortadas": cortadas}


# ── réplica (§7, §9) ─────────────────────────────────────────────────────
def cargar_replica(dir_rep: Path, campana: Campana, semillas: Dict[int, int],
                   incluidas: Set[int], tomas: Dict[int, Dict[str, str]],
                   fecha_cierre: Optional[str], ensayo: bool) -> Dict[str, Any]:
    archivos = sorted(dir_rep.glob("*_replica_tomas.csv")) if dir_rep.is_dir() else []
    filas: List[Dict[str, str]] = []
    sha: Dict[str, str] = {}
    for ruta in archivos:
        datos = leer_csv(ruta)
        if datos:
            faltan = [c for c in COLUMNAS_REPLICA if c not in datos[0]]
            if faltan:
                raise ErrorAnalisis(f"{ruta.name}: faltan columnas del contrato "
                                    f"(§9): {faltan}", SALIDA_REPLICA)
        sha[ruta.name] = sha256_archivo(ruta)
        filas.extend(datos)
    vistas: Dict[Tuple[int, str, float], Dict[str, Set[int]]] = {}
    antes_del_cierre = 0
    for r in filas:
        if r["campana"] != campana.nombre:
            raise ErrorAnalisis(f"fila de réplica de otra campaña: {r['campana']!r}",
                                SALIDA_REPLICA)
        k = _entero(r["intento_campana"], "intento_campana", SALIDA_REPLICA)
        rep = _entero(r["rep"], "rep", SALIDA_REPLICA)
        tau = _f(r["tau_s"])
        if (r["condicion"], tau) not in CONDICIONES_PLAN:
            raise ErrorAnalisis(f"intento {k}: condición {r['condicion']!r} con τ = "
                                f"{r['tau_s']!r} fuera del plan", SALIDA_REPLICA)
        if k not in incluidas:
            raise ErrorAnalisis(f"réplica del intento {k}, que no es una toma "
                                f"incluida", SALIDA_REPLICA)
        if _entero(r["semilla"], "semilla", SALIDA_REPLICA) != semillas[k]:
            raise ErrorAnalisis(f"réplica del intento {k}: semilla {r['semilla']} "
                                f"≠ libro {semillas[k]}", SALIDA_REPLICA)
        if _f(r["decisiones_previas"]) != _f(tomas[k].get("decisiones_previas")):
            raise ErrorAnalisis(f"réplica del intento {k}: decisiones_previas "
                                f"{r['decisiones_previas']} ≠ hw "
                                f"{tomas[k].get('decisiones_previas')} (otra rampa)",
                                SALIDA_REPLICA)
        if r["condicion"] == "con_obstaculo" and (_f(r.get("decisiones")) or 0) > 0 and any(
                str(r.get(c, "")).strip() == "" for c in
                ("cierre_b_ok", "cierre_b_err_max_m", "cierre_b_desfase",
                 "cierre_b_err_th_rad", "cierre_b_mandos_iguales")):
            raise ErrorAnalisis(f"réplica del intento {k}: cierre (b) sin evaluar "
                                f"(el §9 lo exige en toda corrida con obstáculo, "
                                f"también en las inválidas)", SALIDA_REPLICA)
        if fecha_cierre and str(r["inicio"]) < fecha_cierre:
            antes_del_cierre += 1
        pasada = r.get("pasada") or "normal"
        if pasada not in ("normal", "suplementaria"):
            raise ErrorAnalisis(f"pasada {pasada!r}", SALIDA_REPLICA)
        grupo = vistas.setdefault((k, r["condicion"], tau), {"normal": set(),
                                                             "suplementaria": set()})
        if rep in grupo["normal"] | grupo["suplementaria"]:
            raise ErrorAnalisis(f"clave repetida en la réplica: {(k, r['condicion'], tau, rep)}",
                                SALIDA_REPLICA)
        grupo[pasada].add(rep)
    for (k, cond, tau), g in vistas.items():
        if not g["normal"] <= REPS_NORMALES or any(x <= max(REPS_NORMALES)
                                                   for x in g["suplementaria"]):
            raise ErrorAnalisis(f"réplica del intento {k} {cond} τ={tau}: reps "
                                f"normales {sorted(g['normal'])}, suplementarias "
                                f"{sorted(g['suplementaria'])} (el plan pide 1–3 "
                                f"normales y la suplementaria desde la 4)", SALIDA_REPLICA)
    if antes_del_cierre and not ensayo:
        raise ErrorAnalisis(f"{antes_del_cierre} corridas de réplica empezaron ANTES "
                            f"del cierre de la campaña (§8, cegado)", SALIDA_REPLICA)
    return {"filas": filas, "archivos": [a.name for a in archivos], "sha256": sha,
            "pilas": sorted({r["sha256_pila"] for r in filas}),
            "antes_del_cierre": antes_del_cierre}


def completitud_replica(filas: List[Dict[str, str]], tomas: Set[int]) -> List[str]:
    """Lo que le falta a la réplica de esas tomas: una condición del plan,
    alguna de las reps normales 1–3, o la suplementaria 4–6 de un grupo cuya
    pasada normal dio 0 válidas."""
    grupos: Dict[Tuple[int, str, float], Dict[int, bool]] = {}
    for r in filas:
        k = int(float(r["intento_campana"]))
        if k in tomas:
            grupos.setdefault((k, r["condicion"], float(r["tau_s"])), {})[
                int(float(r["rep"]))] = _es_uno(r["valido"])
    faltan = []
    for k in sorted(tomas):
        for cond, tau in sorted(CONDICIONES_PLAN):
            g = grupos.get((k, cond, tau), {})
            if not REPS_NORMALES <= set(g):
                faltan.append(f"intento {k} {cond} τ={tau}: reps normales "
                              f"{sorted(x for x in g if x <= 3)}")
            elif not any(g[x] for x in REPS_NORMALES) and not {4, 5, 6} <= set(g):
                faltan.append(f"intento {k} {cond} τ={tau}: 0 válidas y sin la "
                              f"pasada suplementaria completa")
    return faltan


def fallas_cierre_b(filas: List[Dict[str, str]]) -> Dict[int, str]:
    """Tomas cuya reproducción del 4 no pasó el cierre (b) en alguna corrida
    con obstáculo (§7): bandera en 0, error > 1 mm, desfase ≠ 0, rumbo >
    1e-6 rad o mandos distintos de los grabados."""
    fallas: Dict[int, str] = {}
    for r in filas:
        # Una corrida con 0 decisiones (no arrancó) no tiene cierre (b): es
        # una repetición inválida y no excluye la toma (plan §7).
        if r["condicion"] != "con_obstaculo" or (_f(r.get("decisiones")) or 0) == 0:
            continue
        err, desf = _f(r.get("cierre_b_err_max_m")), _f(r.get("cierre_b_desfase"))
        th = _f(r.get("cierre_b_err_th_rad"))
        if (not _es_uno(r.get("cierre_b_ok")) or err is None or err > CIERRE_B_ERR_MAX_M
                or desf is None or desf != 0 or th is None or th > CIERRE_B_RUMBO_MAX_RAD
                or not _es_uno(r.get("cierre_b_mandos_iguales"))):
            k = int(float(r["intento_campana"]))
            fallas.setdefault(k, (
                f"cierre (b) en {r['condicion']} τ={r['tau_s']} rep {r['rep']}: "
                f"bandera {r.get('cierre_b_ok')}, error máx {r.get('cierre_b_err_max_m')} m, "
                f"desfase {r.get('cierre_b_desfase')}, rumbo {r.get('cierre_b_err_th_rad')} "
                f"rad, mandos iguales {r.get('cierre_b_mandos_iguales')}"))
    return fallas


def media_replica(filas: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """La réplica de UNA toma en UNA condición: media de las repeticiones
    VÁLIDAS de la pasada normal; si no hay ninguna, las de la suplementaria
    (regla del 30-09). None si no queda ninguna válida."""
    normales = [r for r in filas if (r.get("pasada") or "normal") == "normal"]
    suplem = [r for r in filas if r.get("pasada") == "suplementaria"]
    val = [r for r in normales if _es_uno(r["valido"])]
    pasada = "normal"
    advertencia = ""
    if not val:
        val = [r for r in suplem if _es_uno(r["valido"])]
        pasada = "suplementaria"
    elif suplem:
        advertencia = "pasada suplementaria con válidas en la normal: no cuenta"
    if not val:
        return None
    cob = np.array([float(r["cobertura_aoi"]) for r in val])
    out: Dict[str, Any] = {
        "n_validas": len(val),
        "n_corridas": len(normales) + (len(suplem) if pasada == "suplementaria" else 0),
        "pasada": pasada, "advertencia": advertencia,
        "cobertura": float(cob.mean()),
        "sd": float(cob.std(ddof=1)) if len(cob) > 1 else None,
    }
    dmin = [_f(r["d_min_obst_medida"]) for r in val]
    dmin = [x for x in dmin if x is not None]
    out["d_min_media"] = float(np.mean(dmin)) if dmin else None
    out["d_min_min"] = float(np.min(dmin)) if dmin else None
    for c in (*SEGURIDAD, "frenos_sombra"):
        v = [_f(r[c]) for r in val]
        v = [x for x in v if x is not None]
        out[c] = float(np.mean(v)) if v else None
    pared = [_f(r["d_pared_min"]) for r in val]
    pared = [x for x in pared if x is not None]
    out["d_pared_min_min"] = float(np.min(pared)) if pared else None
    return out


# ── 30-09 (§6, descriptivo) ──────────────────────────────────────────────
def comparacion_3009(dir_3009: Path = DIR_3009) -> Dict[str, Any]:
    """Recalcula del crudo empaquetado, con las reglas de pareo_final_0930."""
    pares = []
    hw_todos = []
    sha: Dict[str, str] = {}
    for s in ("", "_02", "_03", "_04", "_05"):
        ruta_eps = dir_3009 / f"20260930_sesion-evaluacion_etapa7_episodios{s}.csv"
        eps = leer_csv(ruta_eps)
        sha[ruta_eps.name] = sha256_archivo(ruta_eps)
        rep_arch = sorted(dir_3009.glob(f"*_sesion-replica_etapa7_capas-on_de-20260930{s}.csv"))
        if not rep_arch:
            raise ErrorAnalisis(f"falta la réplica del 30-09{s}", SALIDA_INTEGRIDAD)
        sha[rep_arch[-1].name] = sha256_archivo(rep_arch[-1])
        reps: Dict[int, List[Dict[str, str]]] = {}
        for r in leer_csv(rep_arch[-1]):
            if str(r.get("valido", "1")) in ("1", "True", "true"):
                reps.setdefault(int(r["episodio"]), []).append(r)
        for r in eps:
            if r["valido"] not in ("1", "True"):
                continue
            hw_todos.append(float(r["cobertura_aoi"]))
            e = int(r["episodio"])
            if e not in reps:
                continue
            pares.append({
                "semilla": int(r["semilla"]), "hw": float(r["cobertura_aoi"]),
                "sim": float(np.mean([float(x["cobertura_aoi"]) for x in reps[e]])),
                "pared_hw": float(r["d_pared_min"]),
                "pared_sim": float(np.mean([float(x["d_pared_min"]) for x in reps[e]])),
            })
    d = [p["hw"] - p["sim"] for p in pares]
    por_semilla: Dict[int, List[float]] = {}
    for p in pares:
        por_semilla.setdefault(p["semilla"], []).append(p["hw"] - p["sim"])
    return {
        "cobertura_hw": {"n": len(hw_todos), "media": float(np.mean(hw_todos)),
                         "sd": float(np.std(hw_todos, ddof=1))},
        "brecha_por_pares": resumen_pareado(d),
        "brecha_por_escenario": resumen_pareado([np.mean(v) for v in por_semilla.values()]),
        "d_pared_hw_menos_replica": resumen_pareado(
            [p["pared_hw"] - p["pared_sim"] for p in pares]),
        "sha256_csv": sha,
    }


# ── el análisis ──────────────────────────────────────────────────────────
def chequear_requisitos(campana: Campana, ensayo: bool,
                        desvio: Optional[str]) -> Dict[str, Any]:
    """§8. Devuelve lo comprobado; sin --ensayo ni --desvio, se niega."""
    if ensayo and campana.cabecera["plataforma"] == "hw":
        raise ErrorAnalisis("--ensayo es para datos de prueba, no para una campaña "
                            "de hardware: para analizarla fuera de los requisitos, "
                            "--desvio \"motivo\"", SALIDA_NEGADO)
    vig = campana.hashes_vigentes()
    hashes = {}
    for clave, ruta in ((CLAVE_PLAN, RUTA_PLAN), (CLAVE_SCRIPT, Path(__file__).resolve()),
                        (CLAVE_LIBRO, _CARPETA / CLAVE_LIBRO)):
        ahora = sha256_archivo(ruta)
        hashes[clave] = {"ahora": ahora, "libro": vig.get(clave),
                         "igual": vig.get(clave) == ahora}
    est = campana.estado()
    problemas = []
    if not est["cerrada"]:
        problemas.append("la campaña no está cerrada")
    plan_tamano = (META_PLAN, MINIMO_PLAN, TOPE_PLAN)
    cab_tamano = (int(campana.cabecera["meta"]), int(campana.cabecera["minimo"]),
                  int(campana.cabecera["tope_intentos"]))
    if campana.cabecera["plataforma"] == "hw" and cab_tamano != plan_tamano:
        problemas.append(f"meta/mínimo/tope de la campaña {cab_tamano} ≠ los del plan "
                         f"{plan_tamano}")
    if campana.cabecera["plataforma"] != "hw":
        problemas.append(f"la campaña es de plataforma {campana.cabecera['plataforma']!r}")
    for clave, h in hashes.items():
        if not h["igual"]:
            problemas.append(f"el sha256 de {clave} no es el del libro")
    if problemas and not ensayo and not (desvio and desvio.strip()):
        raise ErrorAnalisis("; ".join(problemas) + ". Para analizar igual, "
                            "declarar --desvio \"motivo\" (queda en la salida).",
                            SALIDA_NEGADO)
    return {"hashes": hashes, "problemas": problemas, "ensayo": ensayo,
            "desvio": (desvio or "").strip(), "estado_libro": est,
            "veredicto_campana": campana.veredicto()}


def analizar(campana: Campana, dir_hw: Path, dir_rep: Path, ensayo: bool = False,
             desvio: Optional[str] = None, dir_3009: Path = DIR_3009) -> Dict[str, Any]:
    req = chequear_requisitos(campana, ensayo, desvio)
    hw = cargar_hw(campana, dir_hw, ensayo=ensayo)
    resultados, tomas = hw["resultados"], hw["tomas"]
    semillas = {k: int(f["semilla"]) for k, f in resultados.items()}
    incluidas = sorted(k for k, f in resultados.items() if _es_uno(f["incluida"]))
    corridas = sorted(k for k, f in resultados.items() if f["estado"] == "corrida")
    fecha_cierre = next((f["fecha"] for f in hw["filas_libro"]
                         if f["tipo"] == "cierre_campana"), None)
    rep = cargar_replica(dir_rep, campana, semillas, set(incluidas), tomas,
                         fecha_cierre, ensayo)

    # Cierre (b) — decisión 8.
    fallas_b = {k: m for k, m in fallas_cierre_b(rep["filas"]).items() if k in incluidas}
    if len(fallas_b) > CIERRE_B_FALLAS_MAX:
        raise ErrorAnalisis(f"el cierre (b) falló en {len(fallas_b)} tomas "
                            f"({sorted(fallas_b)}): es un error de la réplica — "
                            f"se corrige, no se excluye", SALIDA_REPLICA)

    # Réplica COMPLETA y de una sola pila (§7, revisión del 10-10): cada
    # toma incluida (salvo las que excluye el cierre b) tiene las tres
    # condiciones con las reps 1–3, y la suplementaria 4–6 si la normal dio
    # 0 válidas. Sin --ensayo, si no, se detiene (con --desvio, se declara).
    incompletas = completitud_replica(rep["filas"], set(incluidas) - set(fallas_b))
    pilas_malas = (len(rep["pilas"]) > 1) or ("FALSA" in rep["pilas"])
    if (incompletas or pilas_malas) and not ensayo and not (desvio and desvio.strip()):
        raise ErrorAnalisis("réplica incompleta o de más de una pila: "
                            + "; ".join(incompletas[:5])
                            + (f" · pilas {rep['pilas']}" if pilas_malas else ""),
                            SALIDA_REPLICA)

    def grupo(k: int, condicion: str, tau: float) -> List[Dict[str, str]]:
        return [r for r in rep["filas"] if int(float(r["intento_campana"])) == k
                and r["condicion"] == condicion and abs(float(r["tau_s"]) - tau) < 1e-9]

    pares: List[Dict[str, Any]] = []
    for k in incluidas:
        r = tomas[k]
        p: Dict[str, Any] = {
            "intento": k, "semilla": semillas[k], "id_sesion": r.get("id_sesion"),
            "fuente_tomas": resultados[k]["archivo_tomas"],
            "hw": float(r["cobertura_aoi"]),
            "fuera_de_soporte": fuera_de_soporte(r),
            "retroceso": con_retroceso(r), "freno": con_freno(r), "rampa": con_rampa(r),
            "col_obst_origen": r.get("col_obst_origen", ""),
            "d_min_hw": _f(r.get("d_min_obst_medida")),
            "frenos_hw": _f(r.get("frenos")),
            **{f"{c}_hw": _f(r.get(c)) for c in SEGURIDAD},
            "cierre_b": fallas_b.get(k, ""),
        }
        if k in fallas_b:
            p["rep_con"] = p["rep_sin"] = p["rep_045"] = None
        else:
            p["rep_con"] = media_replica(grupo(k, "con_obstaculo", TAU_PRINCIPAL))
            p["rep_sin"] = media_replica(grupo(k, "sin_obstaculo", TAU_PRINCIPAL))
            p["rep_045"] = media_replica(grupo(k, "con_obstaculo", TAU_SENSIBILIDAD))
        p["d"] = p["hw"] - p["rep_con"]["cobertura"] if p["rep_con"] else None
        p["d_045"] = p["hw"] - p["rep_045"]["cobertura"] if p["rep_045"] else None
        p["costo"] = (p["rep_con"]["cobertura"] - p["rep_sin"]["cobertura"]
                      if p["rep_con"] and p["rep_sin"] else None)
        pares.append(p)

    con_par = [p for p in pares if p["d"] is not None]
    if incluidas and not con_par and not ensayo:
        raise ErrorAnalisis("ninguna toma incluida tiene réplica con obstáculo "
                            "válida: no hay principal", SALIDA_REPLICA)
    semillas_par = [p["semilla"] for p in con_par]

    def brecha(sub: List[Dict[str, Any]], clave: str = "d") -> Dict[str, Any]:
        return resumen_pareado([p[clave] for p in sub if p[clave] is not None],
                               bootstrap=True)

    principal = brecha(con_par)
    principal["conclusion"] = conclusion(principal)
    principal["hw"] = resumen_pareado([p["hw"] for p in con_par])
    principal["replica"] = resumen_pareado([p["rep_con"]["cobertura"] for p in con_par])
    respaldo = None
    if len(set(semillas_par)) < len(semillas_par):          # §3, no debería pasar
        por: Dict[int, List[float]] = {}
        for p in con_par:
            por.setdefault(p["semilla"], []).append(p["d"])
        respaldo = resumen_pareado([np.mean(v) for v in por.values()])
    sd_reps = [p["rep_con"]["sd"] for p in con_par if p["rep_con"]["sd"] is not None]
    sensibilidades = {
        "A_sin_fuera_de_soporte": brecha([p for p in con_par if not p["fuera_de_soporte"]]),
        "B_sin_retroceso": brecha([p for p in con_par if not p["retroceso"]]),
        "C_sin_freno": brecha([p for p in con_par if not p["freno"]]),
        "D_sin_rampa": brecha([p for p in con_par if not p["rampa"]]),
        "E_replica_tau_045": brecha([p for p in pares if p["d_045"] is not None], "d_045"),
    }
    for s in sensibilidades.values():
        s["conclusion"] = conclusion(s)

    # Seguridad (§4) — TODAS las corridas, también las que el libro marcó
    # interrumpidas aunque corrieron (declaradas).
    seg_tomas = []
    cortadas_seg = [(k, _seguridad_de_decisiones(filas_k), 2)
                    for k, filas_k in sorted(hw["cortadas"].items())]
    for k, r, marcada in ([(k, tomas[k], 0) for k in corridas]
                          + [(c["intento"], c["fila"], 1) for c in hw["corridas_sin_libro"]]
                          + cortadas_seg):
        seg_tomas.append({
            "intento": k, "semilla": semillas[k], "incluida": int(k in incluidas),
            "marcada_interrumpida": marcada,
            "d_min_obst_medida": _f(r.get("d_min_obst_medida")),
            "frenos": _f(r.get("frenos")) or 0.0,
            "decisiones_freno": _f(r.get("decisiones_freno")) or 0.0,
            "regla_parada": (resultados[k].get("regla_parada", "") if not marcada
                             else r.get("regla_parada", "")),
            "parada_respuesta": (resultados[k].get("parada_respuesta", "") if not marcada
                                 else r.get("parada_respuesta", "")),
            **{c: _f(r.get(c)) for c in SEGURIDAD},
        })
    dmins = [t["d_min_obst_medida"] for t in seg_tomas if t["d_min_obst_medida"] is not None]
    contactos = [t for t in seg_tomas if t["d_min_obst_medida"] is not None
                 and t["d_min_obst_medida"] < UMBRAL_CONTACTO_M]
    con_rep = [p for p in pares if p["rep_con"] and p["d_min_hw"] is not None
               and p["rep_con"]["d_min_media"] is not None]
    con_pared = [p for p in con_par if p["d_pared_min_hw"] is not None
                 and p["rep_con"]["d_pared_min"] is not None]
    seguridad = {
        "corridas": len(seg_tomas),
        "corridas_marcadas_interrumpidas": sum(t["marcada_interrumpida"] for t in seg_tomas),
        "d_min_obst_hw": ({"n": len(dmins), "min": float(min(dmins)),
                           "mediana": float(np.median(dmins)), "max": float(max(dmins))}
                          if dmins else {"n": 0}),
        "contacto_hw": clopper_pearson(len(contactos), len(dmins)),
        "contactos_no_incluidas": [t["intento"] for t in contactos if not t["incluida"]],
        "tomas_con_freno_hw": clopper_pearson(sum(1 for t in seg_tomas if t["frenos"] > 0),
                                              len(seg_tomas)),
        "frenos_eventos_hw": float(sum(t["frenos"] for t in seg_tomas)),
        "decisiones_freno_hw": float(sum(t["decisiones_freno"] for t in seg_tomas)),
        "d_min_hw_menos_replica_media": resumen_pareado(
            [p["d_min_hw"] - p["rep_con"]["d_min_media"] for p in con_rep]),
        "d_min_hw_menos_replica_minimo": resumen_pareado(
            [p["d_min_hw"] - p["rep_con"]["d_min_min"] for p in con_rep]),
        "contacto_replica_por_media": clopper_pearson(
            sum(1 for p in con_rep if p["rep_con"]["d_min_media"] < UMBRAL_CONTACTO_M),
            len(con_rep)),
        "contacto_replica_por_minimo": clopper_pearson(
            sum(1 for p in con_rep if p["rep_con"]["d_min_min"] < UMBRAL_CONTACTO_M),
            len(con_rep)),
        "frenos_sombra_replica_media": (
            float(np.mean([p["rep_con"]["frenos_sombra"] for p in con_rep
                           if p["rep_con"]["frenos_sombra"] is not None]))
            if any(p["rep_con"]["frenos_sombra"] is not None for p in con_rep) else None),
        "d_pared_hw_menos_replica_media": resumen_pareado(
            [p["d_pared_min_hw"] - p["rep_con"]["d_pared_min"] for p in con_pared]),
        "d_pared_hw_menos_replica_minimo": resumen_pareado(
            [p["d_pared_min_hw"] - p["rep_con"]["d_pared_min_min"] for p in con_pared]),
        "descriptivos": {
            c: {"hw_corridas": _media([t[c] for t in seg_tomas]),
                "hw_pareadas": _media([p[f"{c}_hw"] for p in con_par]),
                "replica_pareadas": _media([p["rep_con"][c] for p in con_par])}
            for c in SEGURIDAD},
        "alcance": "durante la toma y sobre poses observadas",
    }

    # Costo (§5).
    con_costo = [p for p in pares if p["costo"] is not None]
    costo = resumen_pareado([p["costo"] for p in con_costo])
    costo["condicional"] = COSTO_CONDICIONAL
    costo["descriptivos"] = {
        "d_pared_con_menos_sin": _media([p["rep_con"]["d_pared_min"] - p["rep_sin"]["d_pared_min"]
                                         for p in con_costo
                                         if p["rep_con"]["d_pared_min"] is not None
                                         and p["rep_sin"]["d_pared_min"] is not None]),
        "frac_cbf_con_menos_sin": _media([p["rep_con"]["frac_cbf"] - p["rep_sin"]["frac_cbf"]
                                          for p in con_costo
                                          if p["rep_con"]["frac_cbf"] is not None
                                          and p["rep_sin"]["frac_cbf"] is not None]),
        "hw_menos_replica_sin": _media([p["hw"] - p["rep_sin"]["cobertura"] for p in con_costo]),
    }

    # Tablas y declaraciones (§1, §2, §8).
    no_incluidas = [{"intento": k, "semilla": semillas[k], "estado": f["estado"],
                     "motivo_inclusion": f["motivo_inclusion"], "motivo": f["motivo"]}
                    for k, f in sorted(resultados.items()) if not _es_uno(f["incluida"])]
    por_motivo: Dict[str, int] = {}
    for t in no_incluidas:
        clave = t["estado"] if t["estado"] != "corrida" else (
            "recorrido corto" if t["motivo_inclusion"].startswith("el obstáculo")
            else "no válida")
        por_motivo[clave] = por_motivo.get(clave, 0) + 1
    filas_libro = hw["filas_libro"]
    declaraciones = {
        "col_obst_origen_incluidas": _contar([p["col_obst_origen"] for p in pares]),
        "tomas_obstaculo_no_proyeccion": [p["intento"] for p in pares
                                          if p["col_obst_origen"] != "proyeccion"],
        "tomas_con_rampa": [p["intento"] for p in pares if p["rampa"]],
        "pausas_de_seguridad": [{"intento": k, "regla": f["regla_parada"],
                                 "respuesta": _respuesta_pausa(filas_libro, k)
                                 or f.get("parada_respuesta", "")}
                                for k, f in sorted(resultados.items()) if f.get("regla_parada")],
        "correcciones": [{"fecha": f["fecha"], "motivo": f["motivo"],
                          "cambiaron": json.loads(f["detalle"]).get("cambiaron")}
                         for f in filas_libro if f["tipo"] == "correccion"],
        "candados_liberados": [{"fecha": f["fecha"], "motivo": f["motivo"]}
                               for f in filas_libro if f["tipo"] == "candado_liberado"],
        "sesiones": [{"id_sesion": f["id_sesion"], "fecha": f["fecha"], "tipo": f["tipo"],
                      "motivo": f["motivo"]}
                     for f in filas_libro if f["tipo"] in ("apertura", "cierre_sesion")],
        "cierre_campana": [{"fecha": f["fecha"], "motivo": f["motivo"]}
                           for f in filas_libro if f["tipo"] == "cierre_campana"],
        "reservas_marcadas_por_el_analisis": hw["marcadas_por_el_analisis"],
        "filas_descartadas_del_libro": campana.filas_descartadas,
        "corridas_marcadas_interrumpidas": [{"intento": c["intento"], "archivo": c["archivo"]}
                                            for c in hw["corridas_sin_libro"]],
        "cierre_b_excluidas": fallas_b,
        "incluidas_sin_par": [p["intento"] for p in pares if p["d"] is None],
        "incluidas_sin_replica_sin_obstaculo": [p["intento"] for p in pares
                                                if p["rep_sin"] is None],
        "incluidas_sin_replica_tau_045": [p["intento"] for p in pares if p["rep_045"] is None],
        "advertencias_replica": [f"intento {p['intento']}: {p[c]['advertencia']}"
                                 for p in pares for c in ("rep_con", "rep_sin", "rep_045")
                                 if p[c] and p[c]["advertencia"]],
        "pasadas_suplementarias": [f"intento {p['intento']} {c}" for p in pares
                                   for c in ("rep_con", "rep_sin", "rep_045")
                                   if p[c] and p[c]["pasada"] == "suplementaria"],
        "replica_sha256_pila": rep["pilas"],
        "replica_corridas_antes_del_cierre": rep["antes_del_cierre"],
        "configuracion_por_sesion": _configuracion_por_sesion(filas_libro),
        "replica_incompleta": incompletas,
        "replica_pilas_invalidas": rep["pilas"] if pilas_malas else [],
    }

    tres = comparacion_3009(dir_3009)
    return {
        "campana": campana.nombre, "fecha_analisis": datetime.now().isoformat(timespec="seconds"),
        "rotulo": "ENSAYO — no es el resultado" if ensayo else "RESULTADO",
        "requisitos": req,
        "conteos": {"intentos": len(resultados), "corridas": len(corridas),
                    "incluidas": len(incluidas), "con_par": len(con_par),
                    "no_incluidas_por_motivo": por_motivo},
        "principal": principal, "respaldo_por_semilla": respaldo,
        "ruido_replica_entre_reps": ({"n": len(sd_reps), "mediana": float(np.median(sd_reps)),
                                      "max": float(max(sd_reps))} if sd_reps else {"n": 0}),
        "sensibilidades": sensibilidades, "seguridad": seguridad, "costo": costo,
        "criterio_de_cierre": hw["criterio"],
        "comparacion_3009": {k: v for k, v in tres.items() if k != "sha256_csv"},
        "declaraciones": declaraciones,
        "fuentes": {"sha256_libro": sha256_archivo(campana.ruta_libro),
                    "sha256_cabecera": sha256_archivo(campana.ruta_cabecera),
                    "sha256_csv_hw": hw["sha256_csv"], "sha256_replica": rep["sha256"],
                    "sha256_csv_3009": tres["sha256_csv"],
                    "dir_hw": str(dir_hw), "dir_replica": str(dir_rep)},
        "_pares": pares, "_seguridad_tomas": seg_tomas, "_no_incluidas": no_incluidas,
    }


def _es_cierre_por_criterio(f: Dict[str, str]) -> bool:
    """El cierre que escribe el libro por el criterio: el prefijo (que
    `Campana.cerrar` rechaza en un cierre manual) y su detalle."""
    if not f["motivo"].startswith(PREFIJO_CIERRE_SEGURIDAD):
        return False
    try:
        return "criterio" in json.loads(f.get("detalle") or "{}")
    except ValueError:
        return False


def _seguridad_de_decisiones(filas: List[Dict[str, str]]) -> Dict[str, Any]:
    """d_min al obstáculo y pares < 0.15 m de una toma cortada, desde sus
    decisiones (para la seguridad del §4a, con la misma regla del §2)."""
    d_o = [x for x in (_f(r.get("d_obst_medida")) for r in filas) if x is not None]
    por_paso: Dict[str, Dict[str, Tuple[float, float]]] = {}
    for r in filas:
        x, y = _f(r.get("pose_env_x")), _f(r.get("pose_env_y"))
        if x is not None and y is not None:
            por_paso.setdefault(r.get("paso", ""), {})[r.get("agente", "")] = (x, y)
    pares = set()
    for pts in por_paso.values():
        ids = sorted(pts)
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                if math.dist(pts[ids[a]], pts[ids[b]]) < UMBRAL_CONTACTO_M:
                    pares.add((ids[a], ids[b]))
    return {"d_min_obst_medida": min(d_o) if d_o else None,
            "colisiones_015": len(pares), "decisiones": len(por_paso)}


def _decisiones_de_intentos(dir_hw: Path, intentos: Set[int],
                            sesion_de_reserva: Dict[int, str]) -> Dict[int, List[Dict[str, str]]]:
    """Las filas del CSV de decisiones de esos intentos, de la sesión que los
    reservó (para recontar el contacto de una toma cortada a mitad)."""
    out: Dict[int, List[Dict[str, str]]] = {}
    if not intentos:
        return out
    for ruta in sorted(dir_hw.glob("*_L2_decisiones*.csv")):
        for r in leer_csv(ruta):
            k = _f(r.get("episodio"))
            if (k is not None and int(k) in intentos
                    and r.get("id_sesion") == sesion_de_reserva.get(int(k))):
                out.setdefault(int(k), []).append(r)
    return out


def _contacto_de_decisiones(filas: List[Dict[str, str]]) -> Tuple[int, str]:
    """Contacto en las decisiones de una toma: distancia medida al obstáculo
    < 0.15 m, o algún par de agentes < 0.15 m en la misma decisión."""
    partes = []
    d_o = [x for x in (_f(r.get("d_obst_medida")) for r in filas) if x is not None]
    if d_o and min(d_o) < UMBRAL_CONTACTO_M:
        partes.append(f"obstáculo a {min(d_o):.3f} m")
    por_paso: Dict[str, List[Tuple[float, float]]] = {}
    for r in filas:
        x, y = _f(r.get("pose_env_x")), _f(r.get("pose_env_y"))
        if x is not None and y is not None:
            por_paso.setdefault(r.get("paso", ""), []).append((x, y))
    d_par = min((math.dist(p, q) for pts in por_paso.values()
                 for a, p in enumerate(pts) for q in pts[a + 1:]), default=float("inf"))
    if d_par < UMBRAL_CONTACTO_M:
        partes.append(f"par de agentes a {d_par:.3f} m")
    return (1 if partes else 0), "; ".join(partes)


def _respuesta_pausa(filas_libro: List[Dict[str, str]], k: int) -> str:
    """La respuesta a la pausa del intento k (fila 'pausa' del libro)."""
    r = [f.get("parada_respuesta", "") for f in filas_libro
         if f["tipo"] == "pausa" and f["intento"] == str(k)]
    return r[-1] if r else ""


def _configuracion_por_sesion(filas_libro: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """La configuración del día de cada apertura (offsets efectivos y sha256
    de config_robotat.py y de la calibración): no bloquea, se declara (§8)."""
    out = []
    for f in filas_libro:
        if f["tipo"] != "apertura":
            continue
        try:
            conf = json.loads(f["detalle"] or "{}").get("configuracion", {})
        except ValueError:
            conf = {}
        out.append({"id_sesion": f["id_sesion"], "offsets_deg": conf.get("offsets_deg"),
                    "sha256": conf.get("sha256")})
    return out


def _media(v: Sequence[Optional[float]]) -> Optional[float]:
    v = [x for x in v if x is not None]
    return float(np.mean(v)) if v else None


def _contar(v: Sequence[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for x in v:
        out[x or "-"] = out.get(x or "-", 0) + 1
    return out


# ── salidas (§10) ────────────────────────────────────────────────────────
def _linea_ic(r: Dict[str, Any]) -> str:
    if r.get("n", 0) < 2:
        return f"n = {r.get('n', 0)}"
    txt = (f"{r['media']:+.4f} ± {r['sd']:.4f}, IC95 [{r['ic95'][0]:+.4f}, "
           f"{r['ic95'][1]:+.4f}] (n = {r['n']}), mediana {r['mediana']:+.4f}, "
           f"positivas {r['positivas']}/{r['n']}")
    if r.get("wilcoxon_p") is not None:
        txt += f", Wilcoxon p = {r['wilcoxon_p']:.4f}"
    if r.get("bootstrap_ic95"):
        b = r["bootstrap_ic95"]
        txt += f", bootstrap [{b[0]:+.4f}, {b[1]:+.4f}]"
    return txt


def _linea_cp(r: Dict[str, Any]) -> str:
    if not r.get("n"):
        return f"{r.get('k', 0)}/0"
    return f"{r['k']}/{r['n']} = {r['proporcion']:.3f}, IC95 [{r['ic95'][0]:.3f}, {r['ic95'][1]:.3f}]"


def texto_salida(res: Dict[str, Any]) -> str:
    req, c, p = res["requisitos"], res["conteos"], res["principal"]
    s = [f"ANÁLISIS DE LA CAMPAÑA L2 '{res['campana']}' — {res['rotulo']}",
         f"fecha {res['fecha_analisis']} · veredicto de la campaña: {req['veredicto_campana']}",
         "sha256 igual al libro: "
         + ", ".join(f"{k} {'sí' if h['igual'] else 'NO'}" for k, h in req["hashes"].items())]
    if req["problemas"]:
        s.append("⚠ requisitos sin cumplir: " + "; ".join(req["problemas"]))
    if req["desvio"]:
        s.append(f"⚠ DESVÍO DECLARADO: {req['desvio']}")
    s += ["", f"intentos {c['intentos']} · corridas {c['corridas']} · incluidas "
          f"{c['incluidas']} · con par {c['con_par']}",
          f"no incluidas por motivo: {c['no_incluidas_por_motivo'] or 'ninguna'}", "",
          "PRINCIPAL (§3): brecha de cobertura hw − réplica (τ = 0)",
          f"  hw {p['hw'].get('media', float('nan')):.4f} · réplica "
          f"{p['replica'].get('media', float('nan')):.4f}",
          f"  {_linea_ic(p)}", f"  {p['conclusion']}"]
    if res["respaldo_por_semilla"]:
        s.append(f"  respaldo por semilla: {_linea_ic(res['respaldo_por_semilla'])}")
    r = res["ruido_replica_entre_reps"]
    if r.get("n"):
        s.append(f"  ruido de la réplica entre reps: mediana {r['mediana']:.4f}, máx {r['max']:.4f}")
    s += ["", "SENSIBILIDADES (§3a, no deciden)"]
    for k, v in res["sensibilidades"].items():
        s.append(f"  {k}: {_linea_ic(v)}")
    g = res["seguridad"]
    s += ["", f"SEGURIDAD (§4) — {g['alcance']}",
          f"  corridas {g['corridas']} (de ellas marcadas interrumpidas en el libro: "
          f"{g['corridas_marcadas_interrumpidas']}) · d_min al obstáculo hw: "
          + (f"mín {g['d_min_obst_hw']['min']:.4f}, mediana {g['d_min_obst_hw']['mediana']:.4f}, "
             f"máx {g['d_min_obst_hw']['max']:.4f} m" if g["d_min_obst_hw"]["n"] else "sin datos"),
          f"  contacto < {UMBRAL_CONTACTO_M} m hw: {_linea_cp(g['contacto_hw'])}"
          + (f" (en no incluidas: {g['contactos_no_incluidas']})" if g["contactos_no_incluidas"] else ""),
          f"  tomas con freno hw: {_linea_cp(g['tomas_con_freno_hw'])} · eventos "
          f"{g['frenos_eventos_hw']:.0f} · decisiones en freno {g['decisiones_freno_hw']:.0f}",
          f"  d_min hw − réplica (media de reps): {_linea_ic(g['d_min_hw_menos_replica_media'])}",
          f"  d_min hw − réplica (mínimo de reps): {_linea_ic(g['d_min_hw_menos_replica_minimo'])}",
          f"  contacto réplica: por la media {_linea_cp(g['contacto_replica_por_media'])}; "
          f"por el mínimo {_linea_cp(g['contacto_replica_por_minimo'])}",
          f"  d_pared hw − réplica (media de reps): {_linea_ic(g['d_pared_hw_menos_replica_media'])}",
          f"  d_pared hw − réplica (mínimo de reps): {_linea_ic(g['d_pared_hw_menos_replica_minimo'])}"]
    for k, v in g["descriptivos"].items():
        s.append(f"  {k}: " + " · ".join(f"{a} {b:.4f}" if b is not None else f"{a} -"
                                         for a, b in v.items()))
    cr = res["criterio_de_cierre"]
    s += ["", "CRITERIO DE CIERRE DE SEGURIDAD (§2; no mira la cobertura)",
          f"  tomas corridas con contacto (< {cr['umbral_contacto_m']} m, obstáculo o "
          f"entre agentes): {cr['n_tomas_con_contacto']} "
          + (str([(c['intento'], c['que']) for c in cr['tomas_con_contacto']])
             if cr["tomas_con_contacto"] else ""),
          f"  cerró la campaña por el criterio: {'SÍ' if cr['cerro_por_criterio'] else 'no'}"
          + (f" — {cr['motivo_del_cierre']}" if cr["motivo_del_cierre"] else "")]
    if cr["n_contactos_fisicos"] != cr["n_tomas_con_contacto"]:
        s.append(f"  recuento físico (con las tomas que el libro no pudo anotar): "
                 f"{cr['n_contactos_fisicos']} "
                 f"{[(c['intento'], c['que']) for c in cr['contactos_fisicos']]}")
    if cr["incumplimiento_del_criterio"]:
        s.append(f"  ⚠ INCUMPLIMIENTO: el criterio debió cerrar la campaña tras el "
                 f"intento {cr['debio_cerrar_tras_intento']}; intentos después: "
                 f"{cr['intentos_despues_del_cierre_debido']}")
    if cr["contactos_en_corridas_marcadas_interrumpidas"]:
        s.append(f"  ⚠ contactos en corridas que el libro marcó interrumpidas: "
                 f"{cr['contactos_en_corridas_marcadas_interrumpidas']}")
    co = res["costo"]
    s += ["", "COSTO DEL OBSTÁCULO (§5): réplica con − sin obstáculo", f"  {_linea_ic(co)}",
          "  " + " · ".join(f"{a} {b:+.4f}" if b is not None else f"{a} -"
                            for a, b in co["descriptivos"].items()),
          f"  {co['condicional']}"]
    t = res["comparacion_3009"]
    s += ["", "30-09 (§6, sólo descriptivo)",
          f"  cobertura hw {t['cobertura_hw']['media']:.4f} ± {t['cobertura_hw']['sd']:.4f} "
          f"(n = {t['cobertura_hw']['n']})",
          f"  brecha por pares: {_linea_ic(t['brecha_por_pares'])}",
          f"  brecha por escenario: {_linea_ic(t['brecha_por_escenario'])}",
          f"  d_pared hw − réplica: {_linea_ic(t['d_pared_hw_menos_replica'])}",
          "", "DECLARACIONES (§8)"]
    for k, v in res["declaraciones"].items():
        s.append(f"  {k}: {v if v else '-'}")
    return "\n".join(s) + "\n"


def _aplanar(p: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in p.items() if not isinstance(v, (dict, list))}
    out["fuera_de_soporte"] = "; ".join(p["fuera_de_soporte"])
    for c in ("rep_con", "rep_sin", "rep_045"):
        for k, v in (p[c] or {}).items():
            out[f"{c}_{k}"] = v
    return out


def _escribir_csv(ruta: Path, filas: List[Dict[str, Any]]) -> None:
    columnas: List[str] = []
    for f in filas:
        for k in f:
            if k not in columnas:
                columnas.append(k)
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columnas, lineterminator="\n")
        w.writeheader()
        w.writerows(filas)


def escribir_salidas(res: Dict[str, Any], base: Path) -> Path:
    sufijo = "_ENSAYO" if res["requisitos"]["ensayo"] else ""
    nombre = f"{res['campana']}_{datetime.now():%Y%m%d_%H%M%S}{sufijo}"
    carpeta = base / nombre
    n = 1
    while carpeta.exists():
        n += 1
        carpeta = base / f"{nombre}_{n}"
    carpeta.mkdir(parents=True)
    publico = {k: v for k, v in res.items() if not k.startswith("_")}
    (carpeta / "analisis.json").write_bytes(
        json.dumps(publico, ensure_ascii=False, indent=1).encode("utf-8"))
    (carpeta / "salida.txt").write_bytes(texto_salida(res).encode("utf-8"))
    _escribir_csv(carpeta / "pares.csv", [_aplanar(p) for p in res["_pares"]])
    _escribir_csv(carpeta / "seguridad_tomas.csv", res["_seguridad_tomas"])
    _escribir_csv(carpeta / "no_incluidas.csv", res["_no_incluidas"])
    return carpeta


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--campana", required=True)
    ap.add_argument("--base", type=Path, default=DIR_DEMO,
                    help="carpeta con campanas/ (por defecto resultados_demo_obstaculo)")
    ap.add_argument("--dir-hw", type=Path, default=None,
                    help="carpeta de los CSV de tomas (por defecto --base)")
    ap.add_argument("--dir-replica", type=Path, default=None,
                    help="por defecto <base>/replica_campana/<nombre>")
    ap.add_argument("--salida", type=Path, default=None,
                    help="por defecto <base>/analisis_campana")
    ap.add_argument("--ensayo", action="store_true",
                    help="datos de PRUEBA (nunca una campaña de hw): no exige "
                         "cierre ni hash; rotula ENSAYO")
    ap.add_argument("--desvio", default=None,
                    help="analizar aunque falle un requisito del §8, con motivo escrito")
    a = ap.parse_args(argv)
    try:
        campana = Campana(Campana.carpeta_de(a.base, a.campana))
        res = analizar(campana, a.dir_hw or a.base,
                       a.dir_replica or (a.base / "replica_campana" / a.campana),
                       ensayo=a.ensayo, desvio=a.desvio)
    except ErrorAnalisis as e:
        print(f"✗ {e}")
        return e.codigo
    except ErrorCampana as e:
        print(f"✗ {e}")
        return SALIDA_NEGADO
    carpeta = escribir_salidas(res, a.salida or (a.base / "analisis_campana"))
    print(texto_salida(res))
    print(f"salida en {carpeta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
