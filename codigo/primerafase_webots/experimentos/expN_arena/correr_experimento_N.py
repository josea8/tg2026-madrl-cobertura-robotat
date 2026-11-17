"""
correr_experimento_N.py
=======================
EXPERIMENTO N — Costo de reducir la arena de 3,0 × 3,0 m a 2,7 × 2,7 m.

Pregunta
--------
El asesor recomendó reducir el área porque el centro del volumen de captura
del Robotat resuelve mejor. La observación normaliza la posición por las
dimensiones de la arena, así que la política vería un mundo comprimido. Este
experimento mide el COSTO del cambio antes de comprometer una sesión de
laboratorio. El BENEFICIO (mejor seguimiento en el centro) no lo cuantifica
nadie todavía; queda como medición pendiente de laboratorio.

Por qué la comparación directa 2,7 vs 3,0 NO decide
---------------------------------------------------
La huella del sensor (0,15 m), la rapidez de los agentes y la edad máxima del
AoI son absolutas. En una arena menor la cobertura SUBE de forma mecánica aunque
la política empeore. La comparación que decide es lo observado a 2,7 contra lo
que predice la DENSIDAD: 5 agentes en 7,29 m² equivalen a n = 6,17 agentes en
9 m² (mismo cociente área barrida / área). Por eso hay un BRAZO DE DENSIDAD
(n = 6 y 7 a 3,0) en ambas configuraciones. Ese brazo además llena un hueco: el
Exp I midió sólo la política aislada, así que la configuración de tres capas
nunca se había medido a otro cardinal.

Condiciones
-----------
    (a) política aislada — modelo_PRIMERO, modo_borde="reflexion", sin filtro,
        sin escape. Es la del control del protocolo.
    (b) configuración final — modelo_sanidad, modo_borde="bloqueante", filtro
        CBF (paredes + robot-robot 50/50) + escape. Detección del escape de
        TRES términos, como el coordinador desplegado
        (coordinador_enjambre.py:1257-1261).

    Principal : {a, b} × {W=3,0 n=5 ; W=2,7 n=5} × 100 semillas
    Brazo     : {a, b} × {W=3,0 n=6 ; W=3,0 n=7} × 100 semillas
    Puente    : (b) con detección de DOS términos, W=3,0 n=5, 18 semillas

Controles (PARAR si no reproducen)
----------------------------------
    C1 (a) W=3,0 n=5  → 0,681291 a seis decimales (metricas_100eps.json),
                        y por semilla contra el CSV del Exp I (n=5 y n=7).
    C2 (b) dos términos, 18 semillas → 0,577965 a seis decimales y por
                        semilla contra verificacion_cbf_python.csv (celda d).

Uso
---
    python correr_experimento_N.py control    # sólo C1 + C2, con tiempos
    python correr_experimento_N.py completo   # controles primero, luego todo

Ningún archivo existente se pisa: si el CSV de salida ya existe se respalda con
sufijo de fecha antes de escribir.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
import os
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

SEED_BASE:   int   = 42
N_EPISODIOS: int   = 100
N_PUENTE:    int   = 18
MAX_STEPS:   int   = 500
COMM_RADIUS: float = 1.0

PESOS_TRIAL13: Dict[str, float] = {
    "lambda_gradient": 0.5622468083379316,
    "lambda_entropy":  1.1403296484190344,
    "lambda_ibrm":     0.48380314172632155,
    "lambda_cbf":      2.9655314099141474,
}

# Filtro CBF (idéntico a verificar_cbf_python.py y al coordinador).
ELE_A:     float = 0.05
ALFA_CBF:  float = 2.0
W_OMEGA:   float = 0.3
D_SEGURA:  float = 0.18
D_ROBOTS:  float = 0.25
V_MAX:     float = 0.31
OMEGA_MAX: float = 6.2832

# Escape (idénticos al coordinador, coordinador_enjambre.py:307-327).
ESC_UMBRAL_DESPLAZAMIENTO: float = 0.002
ESC_N_DETECCION:           int   = 6
ESC_H_ENTRADA:             float = 0.03
ESC_H_SALIDA:              float = 0.05
ESC_MIN_DECISIONES:        int   = 4
ESC_MAX_DECISIONES:        int   = 25
ESC_REFRACTARIO:           int   = 15
ESC_UMBRAL_ACTIVA:         float = 0.06
ESC_NORMA_MINIMA:          float = 0.20
ESC_FRACCION_V:            float = 0.5
ESC_FRACCION_OMEGA:        float = 0.5

# Umbrales de métricas.
UMBRAL_COL_CONTACTO: float = 0.15   # D_SAFE, el comparable
UMBRAL_COL_MARGEN:   float = 0.22   # margen operativo
MARGEN_CBF_M:        float = 0.18   # violación de margen: CENTRO a pared
RADIO_CHASIS:        float = 0.075
TOL_LIGANTE:         float = 1e-6   # restricción activa en el óptimo del QP

# Referencias de control.
OFICIAL_A:          float = 0.681291
OFICIAL_B_DOS:      float = 0.577965          # media 0.5779647222 (18 sem.)
TOL_SEIS_DECIMALES: float = 5e-7

RUTA_MODELO_A: Path = _CARPETA / "modelos" / "modelo_PRIMERO.zip"
RUTA_MODELO_B: Path = _CARPETA / "modelos" / "modelo_sanidad.zip"
RUTA_CSV_EXP_I: Path = (_CARPETA.parent / "expI_escalabilidad" / "resultados"
                        / "experimento_I_completo.csv")
RUTA_CSV_FACTORIAL: Path = (_CARPETA.parent / "tesis_v2_sanidad" / "resultados"
                            / "verificacion_cbf_python.csv")
DIR_SALIDA: Path = _CARPETA / "resultados"


@dataclass(frozen=True)
class Condicion:
    """Una celda del diseño."""
    nombre:    str
    config:    str             # "a" o "b"
    arena:     float           # lado W [m]
    n:         int
    deteccion: Optional[str]   # "dos", "tres" o None (config a)
    n_semillas: int = N_EPISODIOS


CONTROLES: Tuple[Condicion, ...] = (
    Condicion("a_W30_n5", "a", 3.0, 5, None),
    Condicion("b2_W30_n5_puente", "b", 3.0, 5, "dos", N_PUENTE),
)
PRINCIPALES: Tuple[Condicion, ...] = (
    Condicion("a_W27_n5", "a", 2.7, 5, None),
    Condicion("a_W30_n6", "a", 3.0, 6, None),
    Condicion("a_W30_n7", "a", 3.0, 7, None),
    Condicion("b3_W30_n5", "b", 3.0, 5, "tres"),
    Condicion("b3_W27_n5", "b", 2.7, 5, "tres"),
    Condicion("b3_W30_n6", "b", 3.0, 6, "tres"),
    Condicion("b3_W30_n7", "b", 3.0, 7, "tres"),
)


# =============================================================================
# ESCAPE — puerto del coordinador, con la arena como parámetro
# =============================================================================

def punto_de_mira(pose: np.ndarray) -> np.ndarray:
    """p = c + ℓa·(cosθ, senθ)."""
    return np.array([
        pose[0] + ELE_A * math.cos(pose[2]),
        pose[1] + ELE_A * math.sin(pose[2]),
    ])


class GestorEscape:
    """
    Máquina de estados del escape para todo el enjambre.

    Difiere del puerto de `verificar_escape_python.py` en dos cosas, ambas
    declaradas:
      1. La arena es un parámetro (allí era un global fijo en 3,0).
      2. `deteccion="tres"` agrega el término "el CBF intervino en la
         decisión anterior", como el coordinador desplegado. Con
         `deteccion="dos"` el comportamiento es idéntico al del factorial 2×2.
    """

    def __init__(self, n: int, arena: float, deteccion: str) -> None:
        if deteccion not in ("dos", "tres"):
            raise ValueError(f"deteccion inválida: {deteccion!r}")
        self.n = n
        self.arena = float(arena)
        self.deteccion = deteccion
        self.reset()

    def reset(self) -> None:
        """Estado inicial de un episodio."""
        n = self.n
        self.estado:        List[int]  = [0] * n   # 0 inact., 1 escape, 2 refr.
        self.contador_det:  List[int]  = [0] * n
        self.en_curso:      List[int]  = [0] * n
        self.refractario:   List[int]  = [0] * n
        self.intervino_prev: List[bool] = [False] * n
        self.pose_previa: Optional[np.ndarray] = None
        self.n_escapes:   List[int] = [0] * n
        self.decisiones:  List[int] = [0] * n
        self.infactibles: List[int] = [0] * n
        self.agotados:    List[int] = [0] * n

    def normales_activas(
        self, i: int, poses: np.ndarray,
    ) -> Tuple[Optional[np.ndarray], float]:
        """Suma normalizada de las normales activas (pared y robot-robot)."""
        p_i = punto_de_mira(poses[i])
        W = self.arena
        candidatas = [
            (np.array([1.0, 0.0]),  float(p_i[0]) - D_SEGURA),
            (np.array([-1.0, 0.0]), (W - float(p_i[0])) - D_SEGURA),
            (np.array([0.0, 1.0]),  float(p_i[1]) - D_SEGURA),
            (np.array([0.0, -1.0]), (W - float(p_i[1])) - D_SEGURA),
        ]
        for j in range(len(poses)):
            if j == i:
                continue
            p_j = punto_de_mira(poses[j])
            delta = p_i - p_j
            dist = float(np.linalg.norm(delta))
            if dist < 1e-9:
                continue
            candidatas.append((delta / dist, dist - D_ROBOTS))

        normales, h_min = [], float("inf")
        for normal, h in candidatas:
            h_min = min(h_min, h)
            if h < ESC_UMBRAL_ACTIVA:
                normales.append(normal)
        if not normales:
            return None, h_min
        suma = np.sum(np.asarray(normales), axis=0)
        norma = float(np.linalg.norm(suma))
        if norma < ESC_NORMA_MINIMA:
            return None, h_min
        return suma / norma, h_min

    @staticmethod
    def accion_escape(direccion: np.ndarray, theta: float) -> np.ndarray:
        """Ley de ascenso máximo sobre h: v = V·sign(a), ω = Ω·sign(b)."""
        heading = np.array([math.cos(theta), math.sin(theta)])
        perp    = np.array([-math.sin(theta), math.cos(theta)])
        a = float(direccion @ heading)
        b = float(direccion @ perp)
        return np.array([
            ESC_FRACCION_V * V_MAX * np.sign(a),
            ESC_FRACCION_OMEGA * OMEGA_MAX * np.sign(b),
        ], dtype=np.float32)

    def gestionar(
        self, i: int, poses: np.ndarray, u_nom: np.ndarray,
    ) -> Tuple[np.ndarray, bool]:
        """Devuelve (acción deseada, está_en_escape) para el agente `i`."""
        direccion, h_min = self.normales_activas(i, poses)

        if self.estado[i] == 2:
            self.refractario[i] -= 1
            if self.refractario[i] <= 0:
                self.estado[i] = 0
            return u_nom, False

        if self.estado[i] == 1:
            self.en_curso[i] += 1
            if self.en_curso[i] >= ESC_MAX_DECISIONES:
                self.agotados[i] += 1
            termina = (
                (self.en_curso[i] >= ESC_MIN_DECISIONES and h_min > ESC_H_SALIDA)
                or self.en_curso[i] >= ESC_MAX_DECISIONES
            )
            if termina or direccion is None:
                if direccion is None and not termina:
                    self.infactibles[i] += 1
                self.estado[i]       = 2
                self.refractario[i]  = ESC_REFRACTARIO
                self.en_curso[i]     = 0
                self.contador_det[i] = 0
                return u_nom, False
            self.decisiones[i] += 1
            return self.accion_escape(direccion, float(poses[i, 2])), True

        desplazamiento = float("inf")
        if self.pose_previa is not None:
            desplazamiento = float(np.linalg.norm(
                poses[i, :2] - self.pose_previa[i, :2]
            ))
        estancado = (
            desplazamiento < ESC_UMBRAL_DESPLAZAMIENTO
            and h_min < ESC_H_ENTRADA
        )
        if self.deteccion == "tres":
            estancado = estancado and self.intervino_prev[i]
        self.contador_det[i] = self.contador_det[i] + 1 if estancado else 0

        if self.contador_det[i] >= ESC_N_DETECCION:
            if direccion is None:
                self.infactibles[i] += 1
                self.contador_det[i] = 0
                self.estado[i]       = 2
                self.refractario[i]  = ESC_REFRACTARIO
                return u_nom, False
            self.estado[i]       = 1
            self.en_curso[i]     = 1
            self.contador_det[i] = 0
            self.n_escapes[i]   += 1
            self.decisiones[i]  += 1
            return self.accion_escape(direccion, float(poses[i, 2])), True

        return u_nom, False


# =============================================================================
# FILTRO — barreras robot-robot (idénticas a verificar_cbf_python.py)
# =============================================================================

def barreras_robot_robot(filtro, i: int, poses: np.ndarray) -> list:
    """Barreras robot-robot con reparto de responsabilidad 50/50 (h/2)."""
    from lib.filtro_cbf import RestriccionLineal
    extras = []
    p_i = filtro._punto_de_mira(poses[i])
    G_i = filtro._matriz_G(float(poses[i, 2]))
    for j in range(len(poses)):
        if j == i:
            continue
        p_j = filtro._punto_de_mira(poses[j])
        delta = p_i - p_j
        dist = float(np.linalg.norm(delta))
        if dist < 1e-9:
            continue
        extras.append(RestriccionLineal(
            c=(delta / dist) @ G_i,
            h=0.5 * (dist - D_ROBOTS),
            nombre=f"robot_{j}",
        ))
    return extras


# =============================================================================
# EPISODIO (se ejecuta en procesos trabajadores)
# =============================================================================

_MODELOS: Dict[str, object] = {}


def _inicializar_trabajador() -> None:
    """Un hilo de torch por trabajador (lección del Exp L)."""
    import torch
    torch.set_num_threads(1)
    warnings.filterwarnings("ignore", message=r"\[FiltroCBF\]")


def _modelo(ruta: Path):
    """Carga perezosa del modelo, una vez por proceso."""
    clave = str(ruta)
    if clave not in _MODELOS:
        from stable_baselines3 import PPO
        _MODELOS[clave] = PPO.load(clave, device="cpu")
    return _MODELOS[clave]


def correr_episodio(cond: Condicion, seed_ep: int) -> Dict[str, object]:
    """
    Un episodio determinista de la condición `cond`. Todas las métricas se
    vuelcan SIN redondear.
    """
    from lib.filtro_cbf import FiltroCBFParedes
    from lib.swarm_env_skeleton import make_env

    t0 = time.perf_counter()
    es_b = cond.config == "b"
    W = cond.arena
    modelo = _modelo(RUTA_MODELO_B if es_b else RUTA_MODELO_A)

    env = make_env(
        n_agents=cond.n, arena_size=(W, W), max_steps=MAX_STEPS,
        comm_radius=COMM_RADIUS, reward_weights=PESOS_TRIAL13,
        domain_rand=False, seed=SEED_BASE,
        modo_borde="bloqueante" if es_b else "reflexion",
    )
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        obs, _ = env.reset(seed=seed_ep)
    uso_fallback = int(any("grid fallback" in str(a.message) for a in avisos))

    agentes: List[str] = list(obs.keys())
    n_a = len(agentes)

    filtro = FiltroCBFParedes(
        arena_size=(W, W), ele_a=ELE_A, alfa=ALFA_CBF, d_segura=D_SEGURA,
        w_omega=W_OMEGA, v_max=V_MAX, omega_max=OMEGA_MAX,
    ) if es_b else None
    gestor = GestorEscape(n_a, W, cond.deteccion) if es_b else None

    pares15: set = set()
    pares22: set = set()
    n_pasos = 0
    emb_activo = 0
    suma_dist_media = 0.0
    pasos_banda = 0
    d_min_pared = float("inf")
    violo_margen = [False] * n_a
    contacto_pared = [False] * n_a
    # Filtro
    n_interv = n_int_pared = n_int_robot = 0
    n_lig_pared = n_lig_robot = n_lig_ninguna = 0
    suma_magnitud = 0.0
    n_fallbacks = 0
    esc_filtro_modifico = 0
    done = False

    while not done:
        obs_arr = np.stack([obs[a] for a in agentes])
        emb_activo += int(np.sum(np.any(obs_arr[:, 8:16] != 0.0, axis=1)))
        acciones, _ = modelo.predict(obs_arr, deterministic=True)
        acciones = np.asarray(acciones, dtype=np.float32)

        if es_b:
            poses = np.array([env._estados[a][:3] for a in agentes])
            for i in range(n_a):
                accion_i, en_escape = gestor.gestionar(i, poses, acciones[i])
                acciones[i] = accion_i
                extras = barreras_robot_robot(filtro, i, poses)
                res = filtro.filtrar(poses[i], acciones[i],
                                     restricciones_extra=extras)
                if res.intervino:
                    n_interv += 1
                    suma_magnitud += res.magnitud_modificacion
                    if res.barrera_activa.startswith("robot_"):
                        n_int_robot += 1
                    else:
                        n_int_pared += 1
                    # Conjunto ligante en el óptimo (puede tener varios tipos).
                    p_i = filtro._punto_de_mira(poses[i])
                    restr = filtro._barreras_paredes(p_i, float(poses[i, 2]))
                    restr = restr + extras
                    u = np.asarray(res.u_seguro, dtype=np.float64)
                    lig = [r for r in restr
                           if abs(float(r.c @ u) + ALFA_CBF * r.h) <= TOL_LIGANTE]
                    tipos = {("robot" if r.nombre.startswith("robot_") else "pared")
                             for r in lig}
                    n_lig_pared += int("pared" in tipos)
                    n_lig_robot += int("robot" in tipos)
                    n_lig_ninguna += int(not tipos)
                    if en_escape:
                        esc_filtro_modifico += 1
                if not res.exito_qp:
                    n_fallbacks += 1
                gestor.intervino_prev[i] = bool(res.intervino)
                acciones[i] = np.asarray(res.u_seguro, dtype=np.float32)
            gestor.pose_previa = poses.copy()

        obs, _, term, trunc, _ = env.step(
            {a: acciones[k] for k, a in enumerate(agentes)}
        )
        n_pasos += 1

        pos = np.array([env._estados[a][:2] for a in agentes])
        dists = [float(np.linalg.norm(pos[ii] - pos[jj]))
                 for ii, jj in combinations(range(n_a), 2)]
        suma_dist_media += float(np.mean(dists))
        for (ii, jj), d in zip(combinations(range(n_a), 2), dists):
            if d < UMBRAL_COL_CONTACTO:
                pares15.add((ii, jj))
            if d < UMBRAL_COL_MARGEN:
                pares22.add((ii, jj))
        for k in range(n_a):
            x, y = float(pos[k, 0]), float(pos[k, 1])
            dp = min(x, W - x, y, W - y)
            d_min_pared = min(d_min_pared, dp)
            if dp < MARGEN_CBF_M:
                pasos_banda += 1
                violo_margen[k] = True
            if dp < RADIO_CHASIS:
                contacto_pared[k] = True
        done = all(trunc.values()) or all(term.values())

    ap = n_pasos * n_a
    fila: Dict[str, object] = {
        "condicion": cond.nombre, "config": cond.config, "arena": W,
        "n": n_a, "deteccion": cond.deteccion or "", "seed_ep": seed_ep,
        "cobertura_aoi_final": 1.0 - float(np.mean(env._field._grid_aoi)),
        "cobertura_por_agente": (1.0 - float(np.mean(env._field._grid_aoi))) / n_a,
        "colisiones_015": len(pares15),
        "colisiones_022": len(pares22),
        "frac_agente_paso_banda_018": pasos_banda / ap,
        "reflexiones_total": sum(env.contador_reflexiones.values()),
        "frac_pasos_agente_recorte": sum(env.contador_recortes.values()) / ap,
        "d_min_pared_centro": d_min_pared,
        "violaciones_margen": sum(violo_margen),
        "contacto_pared": sum(contacto_pared),
        "frac_embedding_activo": emb_activo / ap,
        "dist_media_agentes": suma_dist_media / n_pasos,
        "cbf_frac_interv": n_interv / ap,
        "cbf_frac_interv_pared_hmin": n_int_pared / ap,
        "cbf_frac_interv_robot_hmin": n_int_robot / ap,
        "cbf_frac_ligante_pared": n_lig_pared / ap,
        "cbf_frac_ligante_robot": n_lig_robot / ap,
        "cbf_frac_interv_sin_ligante": n_lig_ninguna / ap,
        "cbf_magnitud_media": (suma_magnitud / n_interv) if n_interv else 0.0,
        "qp_fallbacks": n_fallbacks,
        "escape_n": sum(gestor.n_escapes) if gestor else 0,
        "escape_decisiones": sum(gestor.decisiones) if gestor else 0,
        "escape_frac_ciclo": (sum(gestor.decisiones) / ap) if gestor else 0.0,
        "escape_infactibles": sum(gestor.infactibles) if gestor else 0,
        "escape_agotados": sum(gestor.agotados) if gestor else 0,
        "escape_filtro_modifico": esc_filtro_modifico,
        "uso_grid_fallback": uso_fallback,
        "pasos": n_pasos,
        "t_episodio_s": time.perf_counter() - t0,
    }
    return fila


def _tarea(args: Tuple[Condicion, int]) -> Dict[str, object]:
    return correr_episodio(*args)


# =============================================================================
# EJECUCIÓN, CONTROLES Y ESCRITURA
# =============================================================================

def semillas(n: int) -> List[int]:
    """Semillas del protocolo estándar."""
    return [SEED_BASE * 10_000 + i for i in range(n)]


def correr_condiciones(
    conds: Tuple[Condicion, ...], n_trab: int,
) -> List[Dict[str, object]]:
    """Reparte todos los episodios de `conds` entre procesos."""
    tareas = [(c, s) for c in conds for s in semillas(c.n_semillas)]
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=n_trab,
                             initializer=_inicializar_trabajador) as ex:
        filas = list(ex.map(_tarea, tareas, chunksize=1))
    pared = time.perf_counter() - t0
    for c in conds:
        t = [float(f["t_episodio_s"]) for f in filas if f["condicion"] == c.nombre]
        cob = [float(f["cobertura_aoi_final"]) for f in filas
               if f["condicion"] == c.nombre]
        print(f"  {c.nombre:20s} eps={len(t):3d}  cob={np.mean(cob):.8f}  "
              f"t/ep={np.mean(t):6.2f} s (en paralelo, {n_trab} trab.)")
    print(f"  tiempo de pared: {pared:.1f} s para {len(tareas)} episodios")
    return filas


def escribir_csv(filas: List[Dict[str, object]], ruta: Path) -> None:
    """Escribe el CSV sin redondear; respalda si ya existía."""
    if ruta.exists():
        sello = datetime.now().strftime("%Y%m%d_%H%M%S")
        respaldo = ruta.with_name(f"{ruta.stem}_respaldo_{sello}{ruta.suffix}")
        ruta.rename(respaldo)
        print(f"  respaldo del CSV previo → {respaldo.name}")
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()),
                           lineterminator="\n")
        w.writeheader()
        for fila in filas:
            w.writerow({k: (repr(v) if isinstance(v, float) else v)
                        for k, v in fila.items()})


def verificar_controles(filas: List[Dict[str, object]]) -> List[str]:
    """Aplica C1 y C2. Devuelve las líneas del informe; aborta si fallan."""
    L: List[str] = []
    ok = True

    def de(cond: str) -> Dict[int, Dict[str, object]]:
        return {int(f["seed_ep"]): f for f in filas if f["condicion"] == cond}

    # ── C1 ────────────────────────────────────────────────────────────────
    a5 = de("a_W30_n5")
    m = float(np.mean([float(f["cobertura_aoi_final"]) for f in a5.values()]))
    d = abs(m - OFICIAL_A)
    L.append(f"C1 (a) W=3,0 n=5: media {m:.10f} vs oficial {OFICIAL_A:.6f}  "
             f"|Δ|={d:.2e}  {'OK' if d < TOL_SEIS_DECIMALES else 'FALLA'}")
    ok &= d < TOL_SEIS_DECIMALES
    exp_i: Dict[Tuple[int, int], float] = {}
    with open(RUTA_CSV_EXP_I, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["condicion"] == "reflexion":
                exp_i[(int(r["n"]), int(r["seed_ep"]))] = float(
                    r["cobertura_aoi_final"])
    for n_cruce, nombre in ((5, "a_W30_n5"), (7, "a_W30_n7")):
        filas_c = de(nombre)
        if not filas_c:
            continue
        dif = [s for s, fl in filas_c.items()
               if round(float(fl["cobertura_aoi_final"]), 6) != exp_i[(n_cruce, s)]]
        L.append(f"   cruce por semilla vs Exp I n={n_cruce}: "
                 f"{len(filas_c) - len(dif)}/{len(filas_c)} idénticas a 6 dec."
                 f"  {'OK' if not dif else 'FALLA ' + str(dif[:5])}")
        ok &= not dif

    # ── C2 ────────────────────────────────────────────────────────────────
    b2 = de("b2_W30_n5_puente")
    ref: Dict[int, float] = {}
    with open(RUTA_CSV_FACTORIAL, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["condicion"] == "d_con_cbf_con_esc":
                ref[int(r["semilla"])] = float(r["cobertura_aoi_final"])
    red = [round(float(fl["cobertura_aoi_final"]), 6) for fl in b2.values()]
    m2 = float(np.mean(red))
    d2 = abs(round(m2, 6) - OFICIAL_B_DOS)
    L.append(f"C2 (b) dos términos, {len(b2)} sem.: media {m2:.10f} vs "
             f"{OFICIAL_B_DOS:.6f}  {'OK' if d2 < TOL_SEIS_DECIMALES else 'FALLA'}")
    ok &= d2 < TOL_SEIS_DECIMALES
    dif2 = [s for s, fl in b2.items()
            if round(float(fl["cobertura_aoi_final"]), 6) != ref[s]]
    L.append(f"   cruce por semilla vs factorial (d): "
             f"{len(b2) - len(dif2)}/{len(b2)} idénticas a 6 dec."
             f"  {'OK' if not dif2 else 'FALLA ' + str(dif2[:5])}")
    ok &= not dif2

    for linea in L:
        print("  " + linea)
    if not ok:
        print("\n  PARAR: algún control no reproduce. No se reporta nada.")
        sys.exit(1)
    return L


def main() -> None:
    """Punto de entrada."""
    fase = sys.argv[1] if len(sys.argv) > 1 else "control"
    if fase not in ("control", "completo"):
        raise SystemExit("uso: correr_experimento_N.py {control|completo}")
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    n_trab = max(1, (os.cpu_count() or 2) - 1)

    print("═" * 74)
    print(f"  EXPERIMENTO N — fase '{fase}' — {n_trab} trabajadores")
    print("═" * 74)
    filas = correr_condiciones(CONTROLES, n_trab)
    lineas = verificar_controles(filas)
    if fase == "control":
        escribir_csv(filas, DIR_SALIDA / "experimento_N_control.csv")
        (DIR_SALIDA / "control_N.txt").write_bytes(
            ("\n".join(lineas) + "\n").encode("utf-8"))
        return

    filas += correr_condiciones(PRINCIPALES, n_trab)
    escribir_csv(filas, DIR_SALIDA / "experimento_N_completo.csv")
    (DIR_SALIDA / "control_N.txt").write_bytes(
        ("\n".join(lineas) + "\n").encode("utf-8"))
    print(f"  CSV → {DIR_SALIDA / 'experimento_N_completo.csv'} "
          f"({len(filas)} filas)")


if __name__ == "__main__":
    main()
