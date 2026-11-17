"""
correr_experimento_Q.py
=======================
EXPERIMENTO Q — Obstáculos MÓVILES como barreras de ejecución: la versión
dinámica del Exp O. Diseño: `tesis/PROPUESTA_expO_dinamico.md`, aprobada por
José el 2026-10-19 con las nueve decisiones recomendadas.

Encuadre (leer antes de interpretar)
------------------------------------
Esto NO prueba adaptabilidad de la política: la observación (24 dims) no
codifica obstáculos y el agente es CIEGO a ellos. Prueba la GENERALIDAD DE LA
CAPA DE SEGURIDAD (filtro CBF con el término de velocidad, y escape) frente a
obstáculos que se mueven, y a qué costo en progreso de tarea.

Qué no cambia
-------------
La política (`modelo_sanidad.zip`), el filtro, el escape y TODOS sus
parámetros son los del Exp O: se importan de la copia byte-idéntica de
`correr_experimento_O.py`, junto con las copias de `lib/` (sha256 verificado
contra el Exp O al arrancar). Nada se reescribe.

Lo único nuevo
--------------
1. Los obstáculos se mueven (`entorno_obstaculos_moviles.py`): círculos
   antihorarios a 0,05 m/s, con la fase inicial sorteada por semilla.
2. La fila del obstáculo suma el término de velocidad de la campaña (F1, sin
   el predictor, el peso de giro ni el rescate de F2):

       rhs = −α·h + s/k,   s = max(0, n·v_o),   k = 1 (Python ejecuta lo
       comandado),  saturado al 90 % de |c_v|·V_MAX + |c_ω|·Ω_MAX,
       h_eq = −rhs/α.

   Con s = 0 la fila es LITERALMENTE la de `barreras_obstaculos` del Exp O
   (decisión 6: la saturación sólo actúa con s > 0).

Condiciones por nivel Sk (k = 1, 2, 3)
--------------------------------------
    Sk_din     obstáculos móviles, físicos, F1 con término de velocidad
    Sk_quieto  los mismos obstáculos, quietos en su punto de arranque
    Sk_ctrl    sin obstáculos; mismas poses y objetivos iniciales
    Sk_sinvel  móviles, con la fila del Exp O sin término de velocidad
               (decisión 9: descriptiva, no entra en la regla de parada)

En las cuatro los objetivos son TRANSPARENTES (decisión 3) y las poses y los
objetivos iniciales son idénticos (reubicación del Exp O respecto de la
posición inicial de cada obstáculo).

Control obligatorio (subcomando `control`)
------------------------------------------
Por el camino NUEVO (entorno, bucle, fila F1 y gestor nuevos) con
trayectorias QUIETAS en las posiciones del Exp O, rebote y máscara del Exp O,
tienen que salir idénticas bit a bit las 1000 corridas distintas del Exp O:
S0 y S1–S3 × {Sk, Sk_ctrl} contra `experimento_O_completo.csv` y S1–S3 ×
{Sk, Sk_ctrl, Sk_fant} contra `experimento_O_complementario.csv`, en todas
las columnas salvo `t_episodio_s`. Si no, PARAR. El subcomando `experimento`
se niega a correr sin un control y una pasabilidad aprobados con el MISMO
código (huella sha256, tomada al empezar y comprobada al escribir cada
registro). Cada condición terminada queda en `resultados/parciales/`: si la
sesión se corta, el mismo comando con el mismo código la reutiliza.

Regla de parada (la del Exp O, sin cambios): al primer nivel en que, sumado
sobre los 100 episodios de Sk_din, haya algún contacto con obstáculo, escape
agotado, fallback del QP o escape infactible con obstáculo activo, no se
corre el nivel siguiente. La intervención > 0,5 se reporta y no detiene.

Uso
---
    python correr_experimento_Q.py pasabilidad
    python correr_experimento_Q.py control
    python correr_experimento_Q.py negativo      (control de instrumentación)
    python correr_experimento_Q.py experimento

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import math
import os
import re
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

from correr_experimento_O import (ALFA_CBF, ANCHO_PERIFERIA, ARENA, COMM_RADIUS,
                                  COTA_CENTRO_OBST, CRITERIOS_FALLA, D_SEGURA,
                                  ELE_A, ESC_UMBRAL_ACTIVA, ESCENARIOS,
                                  MARGEN_CBF_M, MARGEN_OBS, MAX_STEPS, N_AGENTES,
                                  N_EPISODIOS, OMEGA_MAX, PESOS_TRIAL13,
                                  RADIO_CHASIS, RUTA_MODELO, SEED_BASE,
                                  TOL_LIGANTE, UMBRAL_INDICADOR, UMBRAL_PASO_ESC,
                                  V_MAX, W_OMEGA,
                                  GestorEscape, _inicializar_trabajador,
                                  barreras_obstaculos, barreras_robot_robot,
                                  escribir_csv, tipo_barrera,
                                  verificar_pasabilidad)
from entorno_obstaculos import Obstaculo, distancia_minima, mascara_ocupada
from entorno_obstaculos_moviles import (EntornoObstaculosMoviles, Trayectoria,
                                        TrayectoriaCircular, TrayectoriaQuieta,
                                        mascara_permanente, obstaculos_en)

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

#: Fila F1 de la campaña (`demo_obstaculo_movil.py:36-62, :1479-1519`).
FRACCION_CAPACIDAD: float = 0.90
#: k de s/k: en Python el entorno ejecuta la acción comandada
#: (`swarm_env_skeleton.py:847-866`, sin fricción con domain_rand=False).
K_FACTOR: float = 1.0
#: Flujo del generador de las fases iniciales: [semilla, 3]. El [semilla, 1]
#: (objetivos) y el [semilla, 2] (agentes) siguen siendo los del Exp O.
FLUJO_FASES: int = 3

#: Niveles: (cx, cy, r, ρ) por obstáculo. (cx, cy, r) son los del Exp O; ρ es
#: el radio de la órbita (S1: el círculo de la campaña, R 0,60). §3.1.
ESCENARIOS_Q: Dict[str, Tuple[Tuple[float, float, float, float], ...]] = {
    "S1": ((1.5, 1.5, 0.30, 0.60),),
    "S2": ((1.0, 1.0, 0.25, 0.20), (2.0, 2.0, 0.25, 0.20)),
    "S3": ((0.75, 0.75, 0.20, 0.06), (2.25, 0.75, 0.20, 0.06),
           (0.75, 2.25, 0.20, 0.06), (2.25, 2.25, 0.20, 0.06),
           (1.5, 1.5, 0.25, 0.06)),
}
for _k, _obs in ESCENARIOS_Q.items():
    if tuple((cx, cy, r) for cx, cy, r, _ in _obs) != ESCENARIOS[_k]:
        raise RuntimeError(f"ESCENARIOS_Q[{_k}] no usa los obstáculos del Exp O")

TIPOS_CONTROL: Tuple[str, ...] = ("expo_obst", "expo_ctrl", "expo_fant")
TIPOS_Q: Tuple[str, ...] = ("din", "quieto", "ctrl", "sinvel")
TIPO_NEGATIVO: str = "sinfila"

DIR_SALIDA_Q: Path = _CARPETA / "resultados"
RUTA_CONTROL_CSV: Path = DIR_SALIDA_Q / "control_bit_a_bit_Q.csv"
RUTA_CONTROL_TXT: Path = DIR_SALIDA_Q / "control_bit_a_bit_Q.txt"
RUTA_PASAB_TXT: Path = DIR_SALIDA_Q / "pasabilidad_Q.txt"
RUTA_NEGATIVO_CSV: Path = DIR_SALIDA_Q / "control_negativo_Q.csv"
RUTA_NEGATIVO_TXT: Path = DIR_SALIDA_Q / "control_negativo_Q.txt"
RUTA_CSV_Q: Path = DIR_SALIDA_Q / "experimento_Q_completo.csv"
RUTA_REG_Q: Path = DIR_SALIDA_Q / "registro_Q.txt"
#: Un CSV por condición terminada, con su firma: una sesión cortada se reanuda.
DIR_PARCIALES: Path = DIR_SALIDA_Q / "parciales"

DIR_EXP_O: Path = _CARPETA.parent / "expO_obstaculos"
RUTA_CSV_O: Path = DIR_EXP_O / "resultados" / "experimento_O_completo.csv"
RUTA_CSV_O_COMP: Path = DIR_EXP_O / "resultados" / "experimento_O_complementario.csv"

#: Copias byte a byte del Exp O y su sha256 (verificado el 2026-10-19).
COPIAS_SHA256: Dict[str, str] = {
    "lib/__init__.py": "65d6ab2d44a89aaec44671bb0adf8bfdf62ca2ae3e039cb3b59d6bf7d1895a0c",
    "lib/concentration_dynamics.py": "e707e79b216239e29754c71423305fd65df3fcf6c9ad61319f08906fb76e1211",
    "lib/filtro_cbf.py": "b2d94289a4031974b1d44428ac53b4fbf57896c442580cf74fc39e81e41cb787",
    "lib/swarm_env_skeleton.py": "f41b4c6e531cb0e98a2f9b742ccf3790bc88eddf66ed71b2e31c4865d4d194e3",
    "modelos/modelo_sanidad.zip": "34831589afd04593e70f8faf1cb51acaea7a7233063f4d2a43afbbe9ef1d0c27",
    "entorno_obstaculos.py": "c69b5e76d1bea4b6d7170640a2851f67978126c00e0385aad80af504823443c3",
    "correr_experimento_O.py": "67509b6032ab923a50e6afc3e157bc8fd6ef24f212d0d3020b79c9db69e68dfa",
}
#: Código nuevo que entra en la huella (el análisis corre después y no entra).
CODIGO_NUEVO: Tuple[str, ...] = ("entorno_obstaculos_moviles.py",
                                 "correr_experimento_Q.py")
#: Stack de `fase_preliminar2/requisitos_congelados_2026-09-09.txt`.
STACK_CONGELADO: Dict[str, str] = {
    "torch": "2.10.0", "stable-baselines3": "2.7.1", "numpy": "2.4.1",
    "scipy": "1.17.1", "gymnasium": "1.2.3", "pettingzoo": "1.24.3",
    "supersuit": "3.9.3",
}


@dataclass(frozen=True)
class CondicionQ:
    """Una celda: nombre de la fila, nivel del Exp O y tipo de condición."""
    nombre:    str
    escenario: str
    tipo:      str


@dataclass(frozen=True)
class Armado:
    """Lo que un episodio necesita de su condición y su semilla."""
    trayectorias:       Tuple[Trayectoria, ...]   # las del entorno
    trayectorias_nivel: Tuple[Trayectoria, ...]   # las del nivel (máscaras)
    fisicos:            bool
    rebote:             Tuple[Obstaculo, ...]
    filas_obstaculo:    bool
    termino_velocidad:  bool
    fases:              Tuple[float, ...]


# =============================================================================
# TRAYECTORIAS DE CADA CONDICIÓN
# =============================================================================

def fases_iniciales(semilla: int, m: int) -> np.ndarray:
    """Fase inicial de cada obstáculo, uniforme en (−π, π), flujo [semilla, 3]."""
    return np.random.default_rng([int(semilla), FLUJO_FASES]).uniform(
        -math.pi, math.pi, size=m)


def trayectorias_moviles(escenario: str, semilla: int
                         ) -> Tuple[TrayectoriaCircular, ...]:
    """Las trayectorias circulares del nivel para esta semilla."""
    obst = ESCENARIOS_Q[escenario]
    fases = fases_iniciales(semilla, len(obst))
    return tuple(TrayectoriaCircular(centro=(cx, cy), rho=rho,
                                     fase0=float(f), r=r)
                 for (cx, cy, r, rho), f in zip(obst, fases))


def trayectorias_quietas(obst: Sequence[Obstaculo]
                         ) -> Tuple[TrayectoriaQuieta, ...]:
    """Obstáculos quietos en los puntos dados."""
    return tuple(TrayectoriaQuieta(punto=(x, y), r=r) for x, y, r in obst)


def armar_condicion(cond: CondicionQ, semilla: int) -> Armado:
    """Trayectorias, fisicidad, rebote y fila del obstáculo de la condición."""
    if cond.tipo in TIPOS_CONTROL:
        quietas = trayectorias_quietas(ESCENARIOS[cond.escenario])
        obst = ESCENARIOS[cond.escenario]
        fisicos = cond.tipo == "expo_obst"
        rebote = obst if cond.tipo in ("expo_obst", "expo_fant") else ()
        return Armado(trayectorias=quietas, trayectorias_nivel=quietas,
                      fisicos=fisicos, rebote=tuple(rebote),
                      filas_obstaculo=True, termino_velocidad=True, fases=())
    moviles = trayectorias_moviles(cond.escenario, semilla)
    fases = tuple(tr.fase0 for tr in moviles)
    if cond.tipo == "quieto":
        return Armado(trayectorias=trayectorias_quietas(obstaculos_en(moviles, 0)),
                      trayectorias_nivel=moviles, fisicos=True, rebote=(),
                      filas_obstaculo=True, termino_velocidad=True, fases=fases)
    if cond.tipo in ("din", "ctrl", "sinvel", TIPO_NEGATIVO):
        return Armado(trayectorias=moviles, trayectorias_nivel=moviles,
                      fisicos=cond.tipo != "ctrl", rebote=(),
                      filas_obstaculo=cond.tipo != TIPO_NEGATIVO,
                      termino_velocidad=cond.tipo not in ("sinvel", TIPO_NEGATIVO),
                      fases=fases)
    raise ValueError(f"tipo de condición desconocido: {cond.tipo!r}")


# =============================================================================
# CAPA DE SEGURIDAD: LO NUEVO
# =============================================================================

def filas_obstaculo_f1(filtro, pose: np.ndarray, obst: Sequence[Obstaculo],
                       vel: Sequence[np.ndarray], termino_velocidad: bool
                       ) -> Tuple[list, List[Tuple[str, float, float]], int]:
    """
    Fila F1 de la campaña sobre las filas del Exp O.

    Llama a `barreras_obstaculos` del Exp O y, en cada fila con s > 0 (el
    obstáculo se acerca al punto de mira), reemplaza h por h_eq = −rhs/α con
    rhs = −α·h + s/k saturado al 90 % de la capacidad de la caja en esa fila.
    Con s = 0 (o sin término de velocidad) la fila queda como la devolvió el
    Exp O, el mismo objeto.

    Retorna (filas, info, n_saturadas); info = [(nombre, h geométrico, s)].
    """
    from lib.filtro_cbf import RestriccionLineal
    filas = barreras_obstaculos(filtro, pose, obst)
    p = filtro._punto_de_mira(pose)
    salida: list = []
    info: List[Tuple[str, float, float]] = []
    saturadas = 0
    for fila in filas:
        k = int(fila.nombre[len("obst_"):])
        ox, oy, _r = obst[k]
        delta = p - np.array([ox, oy])
        normal = delta / float(np.linalg.norm(delta))
        s = max(0.0, float(normal @ vel[k]))
        info.append((fila.nombre, float(fila.h), s))
        if not termino_velocidad or s == 0.0:
            salida.append(fila)
            continue
        capacidad = (abs(float(fila.c[0])) * filtro.v_max
                     + abs(float(fila.c[1])) * filtro.omega_max)
        rhs = -filtro.alfa * float(fila.h) + s / K_FACTOR
        if rhs > FRACCION_CAPACIDAD * capacidad:
            rhs = FRACCION_CAPACIDAD * capacidad
            saturadas += 1
        salida.append(RestriccionLineal(c=fila.c, h=-rhs / filtro.alfa,
                                        nombre=fila.nombre))
    return salida, info, saturadas


class GestorEscapeMovil(GestorEscape):
    """
    `GestorEscape` del Exp O (tres términos, normales de obstáculo con h
    geométrico < 0,06) cuyos obstáculos se actualizan en cada decisión. Con
    obstáculos quietos es el del Exp O.
    """

    def actualizar_obstaculos(self, obst: Sequence[Obstaculo]) -> None:
        """Posiciones de los obstáculos en la decisión actual."""
        self.obst = tuple(obst)


# =============================================================================
# EPISODIO
# =============================================================================

_MODELO = None


def correr_episodio_Q(cond: CondicionQ, seed_ep: int) -> Dict[str, object]:
    """
    Un episodio determinista, por el camino nuevo. Sigue paso a paso
    `correr_episodio` del Exp O; lo nuevo son las posiciones de los
    obstáculos en cada decisión, la fila F1 y las métricas agregadas.
    Métricas SIN redondear; las columnas del Exp O conservan su nombre.
    """
    global _MODELO
    from lib.filtro_cbf import FiltroCBFParedes
    if _MODELO is None:
        from stable_baselines3 import PPO
        _MODELO = PPO.load(str(RUTA_MODELO), device="cpu")

    t0 = time.perf_counter()
    arm = armar_condicion(cond, seed_ep)
    env = EntornoObstaculosMoviles(
        trayectorias=arm.trayectorias, fisicos=arm.fisicos,
        obstaculos_rebote=arm.rebote,
        n_agents=N_AGENTES, arena_size=(ARENA, ARENA), max_steps=MAX_STEPS,
        comm_radius=COMM_RADIUS, reward_weights=PESOS_TRIAL13,
        domain_rand=False, seed=SEED_BASE, modo_borde="bloqueante",
    )
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        obs, _ = env.reset(seed=seed_ep)
    uso_fallback = int(any("grid fallback" in str(a.message) for a in avisos))
    agentes = list(obs.keys())
    n_a = len(agentes)
    xx, yy = env._field._grid_xx, env._field._grid_yy
    # Máscara propia (la de la métrica, como en el Exp O también en el
    # control) y las dos del nivel, para que cada comparación tenga el mismo
    # denominador en los dos lados (§3.6).
    mascara = mascara_permanente(arm.trayectorias, xx, yy, MAX_STEPS)
    mascara_din = mascara_permanente(arm.trayectorias_nivel, xx, yy, MAX_STEPS)
    mascara_arr = mascara_ocupada(xx, yy, obstaculos_en(arm.trayectorias_nivel, 0))
    if arm.fisicos and not np.array_equal(mascara, env._field.mascara):
        raise RuntimeError("la máscara del campo no es la permanente")

    filtro = FiltroCBFParedes(arena_size=(ARENA, ARENA), ele_a=ELE_A, alfa=ALFA_CBF,
                              d_segura=D_SEGURA, w_omega=W_OMEGA,
                              v_max=V_MAX, omega_max=OMEGA_MAX)
    gestor = GestorEscapeMovil(n_a, ARENA,
                               env.posiciones_actuales() if arm.fisicos else ())

    pares15, pares22 = set(), set()
    n_pasos = pasos_banda = pasos_periferia = 0
    d_min_pared = float("inf")
    d_min_obst = float("inf")
    violo_margen = [False] * n_a
    contacto_pared = [False] * n_a
    viol_cota_obst = [False] * n_a
    cont = {"interv": 0, "hmin_pared": 0, "hmin_robot": 0, "hmin_obst": 0,
            "lig_pared": 0, "lig_robot": 0, "lig_obst": 0, "lig_ninguna": 0,
            "lig_multi": 0, "fallback": 0, "esc_mod": 0}
    q = {"saturadas": 0, "activo": 0, "activo_acerc": 0, "lig_obst_vel": 0,
         "omega_suma": 0.0, "omega_n": 0}
    suma_mag = 0.0
    done = False

    while not done:
        acciones, _ = _MODELO.predict(np.stack([obs[a] for a in agentes]),
                                      deterministic=True)
        acciones = np.asarray(acciones, dtype=np.float32)
        poses = np.array([env._estados[a][:3] for a in agentes])
        obst_t = env.posiciones_actuales()
        vel_t = env.velocidades_actuales()
        if arm.fisicos:
            gestor.actualizar_obstaculos(obst_t)
        for i in range(n_a):
            accion_i, en_escape = gestor.gestionar(i, poses, acciones[i])
            acciones[i] = accion_i
            extras = barreras_robot_robot(filtro, i, poses)
            info: List[Tuple[str, float, float]] = []
            if arm.fisicos and arm.filas_obstaculo and obst_t:
                filas, info, n_sat = filas_obstaculo_f1(
                    filtro, poses[i], obst_t, vel_t, arm.termino_velocidad)
                extras = extras + filas
                q["saturadas"] += n_sat
            res = filtro.filtrar(poses[i], acciones[i], restricciones_extra=extras)
            if res.intervino:
                cont["interv"] += 1
                suma_mag += res.magnitud_modificacion
                cont["hmin_" + tipo_barrera(res.barrera_activa)] += 1
                restr = filtro._barreras_paredes(filtro._punto_de_mira(poses[i]),
                                                 float(poses[i, 2])) + extras
                u = np.asarray(res.u_seguro, dtype=np.float64)
                tipos = {tipo_barrera(r.nombre) for r in restr
                         if abs(float(r.c @ u) + ALFA_CBF * r.h) <= TOL_LIGANTE}
                for t in ("pared", "robot", "obst"):
                    cont["lig_" + t] += int(t in tipos)
                cont["lig_ninguna"] += int(not tipos)
                cont["lig_multi"] += int(len(tipos) > 1)
                cont["esc_mod"] += int(en_escape)
                # [Q] filas del obstáculo ligantes con el obstáculo acercándose,
                # y la parte de ω en c·u (el mecanismo de giro de la Fase 0).
                acerc = {nombre for nombre, _h, s in info if s > 0.0}
                if acerc:
                    lig_vel = [r for r in restr if r.nombre in acerc and
                               abs(float(r.c @ u) + ALFA_CBF * r.h) <= TOL_LIGANTE]
                    q["lig_obst_vel"] += int(bool(lig_vel))
                    for r in lig_vel:
                        cv = abs(float(r.c[0]) * float(u[0]))
                        cw = abs(float(r.c[1]) * float(u[1]))
                        if cv + cw > 0.0:
                            q["omega_suma"] += cw / (cv + cw)
                            q["omega_n"] += 1
            q["activo"] += int(any(h < ESC_UMBRAL_ACTIVA for _n, h, _s in info))
            q["activo_acerc"] += int(any(h < ESC_UMBRAL_ACTIVA and s > 0.0
                                         for _n, h, s in info))
            cont["fallback"] += int(not res.exito_qp)
            gestor.intervino_prev[i] = bool(res.intervino)
            acciones[i] = np.asarray(res.u_seguro, dtype=np.float32)
        gestor.pose_previa = poses.copy()

        obs, _, term, trunc, _ = env.step({a: acciones[k] for k, a in enumerate(agentes)})
        n_pasos += 1
        pos = np.array([env._estados[a][:2] for a in agentes])
        obst_ahora = env.posiciones_actuales()
        for ii, jj in combinations(range(n_a), 2):
            d = float(np.linalg.norm(pos[ii] - pos[jj]))
            if d < 0.15:
                pares15.add((ii, jj))
            if d < 0.22:
                pares22.add((ii, jj))
        for k in range(n_a):
            x, y = float(pos[k, 0]), float(pos[k, 1])
            dp = min(x, ARENA - x, y, ARENA - y)
            d_min_pared = min(d_min_pared, dp)
            if dp < ANCHO_PERIFERIA:
                pasos_periferia += 1
            if dp < MARGEN_CBF_M:
                pasos_banda += 1
                violo_margen[k] = True
            if dp < RADIO_CHASIS:
                contacto_pared[k] = True
            if obst_ahora:
                do = distancia_minima(pos[k], obst_ahora)
                d_min_obst = min(d_min_obst, do)
                if do < COTA_CENTRO_OBST:
                    viol_cota_obst[k] = True
        done = all(trunc.values()) or all(term.values())

    grid = env._field._grid_aoi.astype(np.float64)
    acc = ~mascara
    ap = n_pasos * n_a
    cob_acc = 1.0 - float(np.mean(grid[acc]))
    if arm.fisicos:
        cob_sin = 1.0 - (float(np.sum(grid[acc])) + float(np.sum(mascara))) / grid.size
    else:
        cob_sin = 1.0 - float(np.mean(env._field._grid_aoi))
    return {
        "condicion": cond.nombre, "escenario": cond.escenario,
        "fisicos": int(arm.fisicos), "seed_ep": seed_ep,
        "cobertura_accesible": cob_acc,
        "cobertura_sin_enmascarar": cob_sin,
        "cobertura_protocolo": 1.0 - float(np.mean(env._field._grid_aoi)),
        "frac_mascara": float(np.mean(mascara)),
        "cobertura_por_agente": cob_acc / n_a,
        "colisiones_015": len(pares15), "colisiones_022": len(pares22),
        "frac_agente_paso_banda_018": pasos_banda / ap,
        "frac_agente_paso_periferia_050": pasos_periferia / ap,
        "d_min_pared_centro": d_min_pared,
        "violaciones_margen": sum(violo_margen),
        "contacto_pared": sum(contacto_pared),
        "contactos_obst_eventos": sum(env.contactos_obstaculo.values()),
        "contactos_obst_agente_eps": sum(v > 0 for v in env.contactos_obstaculo.values()),
        "d_min_obst_superficie": d_min_obst,
        "viol_cota_obst_agente_eps": sum(viol_cota_obst),
        "cbf_frac_interv": cont["interv"] / ap,
        "cbf_frac_hmin_pared": cont["hmin_pared"] / ap,
        "cbf_frac_hmin_robot": cont["hmin_robot"] / ap,
        "cbf_frac_hmin_obst": cont["hmin_obst"] / ap,
        "cbf_frac_lig_pared": cont["lig_pared"] / ap,
        "cbf_frac_lig_robot": cont["lig_robot"] / ap,
        "cbf_frac_lig_obst": cont["lig_obst"] / ap,
        "cbf_frac_lig_multitipo": cont["lig_multi"] / ap,
        "cbf_frac_interv_sin_ligante": cont["lig_ninguna"] / ap,
        "cbf_magnitud_media": suma_mag / cont["interv"] if cont["interv"] else 0.0,
        "qp_fallbacks": cont["fallback"],
        "escape_n": sum(gestor.n_escapes),
        "escape_n_junto_obst": sum(gestor.n_escapes_obst),
        "escape_frac_ciclo": sum(gestor.decisiones) / ap,
        "escape_infactibles": sum(gestor.infactibles),
        "escape_infactibles_junto_obst": sum(gestor.infactibles_obst),
        "escape_infact_opuestas": sum(gestor.infact_opuestas),
        "escape_infact_sin_activas": sum(gestor.infact_sin_activas),
        "escape_infact_op_con_pared": gestor.infact_op_tipos["pared"],
        "escape_infact_op_con_robot": gestor.infact_op_tipos["robot"],
        "escape_infact_op_con_obst": gestor.infact_op_tipos["obst"],
        "rebote_fantasma": int(cond.tipo == "expo_fant"),
        "escape_agotados": sum(gestor.agotados),
        "escape_filtro_modifico": cont["esc_mod"],
        "agentes_reubicados": env.n_agentes_reubicados,
        "objetivos_reubicados": env._field.n_objetivos_reubicados,
        "rebotes_objetivo_obst": env._field.n_rebotes_obstaculo,
        "uso_grid_fallback": uso_fallback,
        "pasos": n_pasos,
        # ── [Q] columnas nuevas ──────────────────────────────────────────
        "tipo": cond.tipo,
        "mueve": int(any(tr.mueve for tr in arm.trayectorias)),
        "filas_obstaculo": int(arm.filas_obstaculo),
        "termino_velocidad": int(arm.termino_velocidad),
        "fases": ";".join(repr(float(f)) for f in arm.fases),
        "cob_acc_din": 1.0 - float(np.mean(grid[~mascara_din])),
        "cob_acc_arranque": 1.0 - float(np.mean(grid[~mascara_arr])),
        "frac_mascara_din": float(np.mean(mascara_din)),
        "frac_mascara_arranque": float(np.mean(mascara_arr)),
        "contactos_obst_empuje": env.contactos_empuje,
        "contactos_obst_avance": env.contactos_avance,
        "f1_filas_saturadas": q["saturadas"],
        "expo_frac_obst_activo": q["activo"] / ap,
        "expo_frac_activo_acercandose": q["activo_acerc"] / ap,
        "cbf_frac_lig_obst_vel": q["lig_obst_vel"] / ap,
        "f1_parte_omega_media": (q["omega_suma"] / q["omega_n"]
                                 if q["omega_n"] else 0.0),
        "f1_parte_omega_n": q["omega_n"],
        "t_episodio_s": time.perf_counter() - t0,
    }


def _tarea_Q(args: Tuple[CondicionQ, int]) -> Dict[str, object]:
    return correr_episodio_Q(*args)


def semillas_protocolo() -> List[int]:
    """420000–420099."""
    return [SEED_BASE * 10_000 + i for i in range(N_EPISODIOS)]


def _leer_csv(ruta: Path) -> List[Dict[str, str]]:
    with open(ruta, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def correr_condiciones(conds: Sequence[CondicionQ], n_trab: int, prefijo: str,
                       huella: str, semillas: Optional[Sequence[int]] = None
                       ) -> List[Dict[str, str]]:
    """
    Corre condiciones × semillas en procesos (1 hilo de torch cada uno), una
    condición a la vez. Cada condición terminada queda en
    `resultados/parciales/<prefijo>_<condición>.csv` con su huella al lado:
    si la sesión se corta, la siguiente corrida con el MISMO código y las
    mismas semillas la reutiliza en lugar de repetirla. Devuelve las filas
    COMO TEXTO, tal como quedaron escritas (el CSV es el dato).
    """
    semillas = list(semillas) if semillas is not None else semillas_protocolo()
    DIR_PARCIALES.mkdir(parents=True, exist_ok=True)
    firma = f"{huella} semillas {semillas[0]}-{semillas[-1]} n {len(semillas)}"
    filas: List[Dict[str, str]] = []
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=n_trab, initializer=_inicializar_trabajador) as ex:
        for c in conds:
            ruta = DIR_PARCIALES / f"{prefijo}_{c.nombre}.csv"
            meta = ruta.with_suffix(".firma")
            reutilizada = (ruta.exists() and meta.exists()
                           and meta.read_text(encoding="utf-8").strip() == firma)
            if reutilizada:
                fc = _leer_csv(ruta)
                reutilizada = sorted(int(f["seed_ep"]) for f in fc) == sorted(semillas)
            if not reutilizada:
                t1 = time.perf_counter()
                nuevas = list(ex.map(_tarea_Q, [(c, s) for s in semillas], chunksize=1))
                escribir_csv(nuevas, ruta)
                meta.write_bytes((firma + "\n").encode("utf-8"))
                fc = _leer_csv(ruta)
                print(f"  {c.nombre:10s} corrida en {time.perf_counter() - t1:.1f} s", flush=True)
            print(f"  {c.nombre:10s} cob_acc="
                  f"{np.mean([float(f['cobertura_accesible']) for f in fc]):.8f} "
                  f"interv={np.mean([float(f['cbf_frac_interv']) for f in fc]):.6f} "
                  f"t/ep={np.mean([float(f['t_episodio_s']) for f in fc]):.2f} s"
                  f"{' (reutilizada)' if reutilizada else ''}", flush=True)
            filas += fc
    print(f"  tiempo de pared {time.perf_counter() - t0:.1f} s", flush=True)
    return filas


# =============================================================================
# VERIFICACIONES: COPIAS, STACK, HUELLA
# =============================================================================

def sha256_de(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def verificar_copias() -> List[str]:
    """Copias == sha256 esperado == original del Exp O. Si no, PARAR."""
    L, malas = [], []
    for rel, esperado in COPIAS_SHA256.items():
        h_copia = sha256_de(_CARPETA / rel)
        h_orig = sha256_de(DIR_EXP_O / rel)
        ok = h_copia == esperado == h_orig
        L.append(f"  {'IGUAL' if ok else 'DISTINTO'} {h_copia} {rel}")
        if not ok:
            malas.append(rel)
    if malas:
        raise SystemExit(f"PARAR: copias distintas del Exp O: {malas}")
    return ["COPIAS del Exp O (copia = esperado = original):"] + L


def verificar_stack() -> str:
    """Versiones instaladas contra los requisitos congelados (se registra)."""
    partes, distintos = [], []
    for p, v in STACK_CONGELADO.items():
        try:
            inst = importlib.metadata.version(p)
        except importlib.metadata.PackageNotFoundError:
            inst = "AUSENTE"
        partes.append(f"{p} {inst}")
        if inst != v:
            distintos.append(f"{p} {inst} (congelado {v})")
    return ("STACK: " + ", ".join(partes) + " — " +
            ("igual a requisitos_congelados_2026-09-09" if not distintos
             else "DISTINTO: " + "; ".join(distintos)))


def huella_codigo() -> str:
    """sha256 conjunto del código que decide la dinámica y las métricas."""
    h = hashlib.sha256()
    for rel in list(COPIAS_SHA256) + list(CODIGO_NUEVO):
        h.update(rel.encode("utf-8"))
        h.update(sha256_de(_CARPETA / rel).encode("utf-8"))
    return h.hexdigest()


def _escribir_registro(ruta: Path, lineas: Sequence[str], huella: str) -> None:
    """
    Escribe un registro con la huella con que EMPEZÓ la corrida, después de
    comprobar que el código no cambió mientras corría.
    """
    if huella_codigo() != huella:
        raise SystemExit("PARAR: el código cambió durante la corrida; no se escribe "
                         f"{ruta.name}.")
    ruta.write_bytes(("\n".join(list(lineas) + [f"HUELLA {huella}"]) + "\n").encode("utf-8"))


def _aprobado(ruta: Path, marca: str, huella: str) -> Optional[str]:
    """Motivo de rechazo, o None si el registro aprueba con esta huella."""
    if not ruta.exists():
        return f"falta {ruta.name}"
    texto = ruta.read_text(encoding="utf-8")
    if f"HUELLA {huella}" not in texto:
        return f"{ruta.name} se aprobó con OTRO código (huella distinta)"
    if marca not in texto:
        return f"{ruta.name} no dice '{marca}'"
    return None


# =============================================================================
# PASABILIDAD A LO LARGO DE LA TRAYECTORIA (§3.2)
# =============================================================================

#: Rejilla de la conexidad en TODOS los instantes; la de 0,005 del Exp O va en
#: el peor instante de cada semilla, con su propia función.
REJILLA_INSTANTES: float = 0.01
_REJILLAS: Dict[float, Tuple[np.ndarray, np.ndarray, Dict[float, np.ndarray]]] = {}
_RE_AREAS = re.compile(r"h≥0: ([0-9.]+) m², (\d+) comp\.; h≥0,06: ([0-9.]+) m², (\d+) comp\.")


def _rejilla(g: float) -> Tuple[np.ndarray, np.ndarray, Dict[float, np.ndarray]]:
    """Centros de la rejilla y el recorte por las paredes, como en el Exp O."""
    if g not in _REJILLAS:
        fx = np.arange(g / 2, ARENA, g)
        FX, FY = np.meshgrid(fx, fx, indexing="ij")
        bases = {extra: ((FX >= D_SEGURA + extra) & (FX <= ARENA - D_SEGURA - extra)
                         & (FY >= D_SEGURA + extra) & (FY <= ARENA - D_SEGURA - extra))
                 for extra in (0.0, ESC_UMBRAL_ACTIVA)}
        _REJILLAS[g] = (FX, FY, bases)
    return _REJILLAS[g]


def region_factible(obst: Sequence[Obstaculo], g: float, extra: float
                    ) -> Tuple[int, float]:
    """
    (componentes, área) de la región del punto de mira con h ≥ extra: la
    misma definición de `verificar_pasabilidad` del Exp O
    (`correr_experimento_O.py:554-559`), sobre la rejilla g.
    """
    from scipy.ndimage import label
    FX, FY, bases = _rejilla(g)
    m = bases[extra].copy()
    for ox, oy, r in obst:
        m &= (FX - ox) ** 2 + (FY - oy) ** 2 >= (r + MARGEN_OBS + extra) ** 2
    return int(label(m)[1]), float(m.sum()) * g * g


def huecos(obst: Sequence[Obstaculo]) -> Tuple[float, float]:
    """Huecos mínimos obstáculo–pared y obstáculo–obstáculo (las del Exp O)."""
    gw = min(min(ox - r, ARENA - ox - r, oy - r, ARENA - oy - r) for ox, oy, r in obst)
    go = min([math.hypot(a[0] - b[0], a[1] - b[1]) - a[2] - b[2]
              for k, a in enumerate(obst) for b in obst[k + 1:]] or [float("inf")])
    return gw, go


def _pasabilidad_semilla(args: Tuple[str, int]) -> Dict[str, object]:
    """
    Una semilla: en cada instante 0..500, huecos > 0,48 y región conexa con
    h ≥ 0 y h ≥ 0,06 en la rejilla de 0,01; en el peor instante (hueco
    mínimo), el chequeo exacto del Exp O (`verificar_pasabilidad`, 0,005).
    """
    escenario, semilla = args
    trays = trayectorias_moviles(escenario, semilla)
    fallos: List[str] = []
    gw_min = go_min = float("inf")
    peor, t_peor = float("inf"), 0
    a0 = [float("inf"), 0.0]
    a6 = [float("inf"), 0.0]
    for t in range(MAX_STEPS + 1):
        obst = obstaculos_en(trays, t)
        gw, go = huecos(obst)
        gw_min, go_min = min(gw_min, gw), min(go_min, go)
        if min(gw, go) < peor:
            peor, t_peor = min(gw, go), t
        if not min(gw, go) > UMBRAL_PASO_ESC:
            fallos.append(f"{semilla} t={t}: hueco {min(gw, go):.4f} ≤ {UMBRAL_PASO_ESC}")
        for extra, a in ((0.0, a0), (ESC_UMBRAL_ACTIVA, a6)):
            n, area = region_factible(obst, REJILLA_INSTANTES, extra)
            a[0], a[1] = min(a[0], area), max(a[1], area)
            if n != 1:
                fallos.append(f"{semilla} t={t}: h≥{extra}: {n} componentes")
    try:
        linea = verificar_pasabilidad(f"{escenario}/{semilla}/t{t_peor}",
                                      obstaculos_en(trays, t_peor))[0]
        ma = _RE_AREAS.search(linea)
        exacta = (float(ma.group(1)), float(ma.group(3)))
    except SystemExit as e:
        fallos.append(f"{semilla} t={t_peor}: {e}")
        exacta = (float("nan"), float("nan"))
    return {"semilla": semilla, "fallos": fallos, "gw": gw_min, "go": go_min,
            "a0": a0, "a6": a6, "t_peor": t_peor, "exacta": exacta}


def peor_caso_analitico(escenario: str) -> Tuple[float, float]:
    """Huecos mínimos sobre TODAS las fases (independientes)."""
    obst = ESCENARIOS_Q[escenario]
    gw = min(min(cx - rho, ARENA - cx - rho, cy - rho, ARENA - cy - rho) - r
             for cx, cy, r, rho in obst)
    go = min([math.hypot(a[0] - b[0], a[1] - b[1]) - a[3] - b[3] - a[2] - b[2]
              for k, a in enumerate(obst) for b in obst[k + 1:]] or [float("inf")])
    return gw, go


def pasabilidad(n_trab: int, huella: str) -> List[str]:
    """Pasabilidad de S1–S3 en las 100 semillas y los 501 instantes."""
    L = ["PASABILIDAD a lo largo de la trayectoria (huecos y conexidad, rejilla 0,01, "
         "en cada instante 0..500 de las 100 semillas; chequeo exacto del Exp O, "
         "rejilla 0,005, en el peor instante de cada semilla):"]
    malos: List[str] = []
    for k in ("S1", "S2", "S3"):
        t0 = time.perf_counter()
        with ProcessPoolExecutor(max_workers=n_trab) as ex:
            res = list(ex.map(_pasabilidad_semilla,
                              [(k, s) for s in semillas_protocolo()], chunksize=4))
        gw_an, go_an = peor_caso_analitico(k)
        fallos = [f for r in res for f in r["fallos"]]
        ok = not fallos and min(gw_an, go_an) > UMBRAL_PASO_ESC
        L.append(
            f"  {k}: peor caso analítico pared {gw_an:.4f} m, obst–obst {go_an:.4f} m; "
            f"en las semillas pared {min(r['gw'] for r in res):.4f} m, obst–obst "
            f"{min(r['go'] for r in res):.4f} m; área h≥0 (0,01) "
            f"{min(r['a0'][0] for r in res):.6f}–{max(r['a0'][1] for r in res):.6f} m², "
            f"h≥0,06 {min(r['a6'][0] for r in res):.6f}–{max(r['a6'][1] for r in res):.6f} m²; "
            f"exacta en el peor instante h≥0 "
            f"{min(r['exacta'][0] for r in res):.6f}–{max(r['exacta'][0] for r in res):.6f} m², "
            f"h≥0,06 {min(r['exacta'][1] for r in res):.6f}–{max(r['exacta'][1] for r in res):.6f} m²; "
            f"instantes evaluados {len(res) * (MAX_STEPS + 1)}, fallidos {len(fallos)} "
            f"→ {'PASABLE' if ok else 'NO PASABLE'} ({time.perf_counter() - t0:.0f} s)")
        print(L[-1], flush=True)
        if not ok:
            malos.append(k)
            L += ["    " + f for f in fallos[:10]]
    _escribir_registro(RUTA_PASAB_TXT, L + ["PASABILIDAD: " + ("NO PASA" if malos else "OK")],
                       huella)
    if malos:
        raise SystemExit(f"PARAR: {malos} no pasable por construcción.")
    return L


# =============================================================================
# CONTROL BIT A BIT
# =============================================================================

def _serial(v: object) -> str:
    """Como lo escribe `escribir_csv` del Exp O."""
    return repr(v) if isinstance(v, float) else str(v)


def comparar_con_csv(filas: Sequence[Dict[str, object]], ruta: Path
                     ) -> Tuple[int, int, int, List[str]]:
    """
    (filas iguales, filas del CSV, columnas comparadas, diferencias). ESTRICTO:
    el mismo texto que escribió `escribir_csv` (repr de cada float).
    """
    ref = {(r["condicion"], int(r["seed_ep"])): r for r in _leer_csv(ruta)}
    propias = {(str(f["condicion"]), int(f["seed_ep"])): f for f in filas}
    columnas = [c for c in next(iter(ref.values())).keys() if c != "t_episodio_s"]
    malas: List[str] = []
    iguales = 0
    for clave, r in ref.items():
        f = propias.get(clave)
        if f is None:
            malas.append(f"{clave}: falta")
            continue
        dif = [c for c in columnas if _serial(f[c]) != r[c]]
        if dif:
            malas.append(f"{clave}: {dif[:4]}")
        else:
            iguales += 1
    return iguales, len(ref), len(columnas), malas


def condiciones_control() -> List[CondicionQ]:
    """S0 y S1–S3 × {Sk, Sk_ctrl, Sk_fant} con los nombres del Exp O."""
    conds = [CondicionQ("S0", "S0", "expo_obst")]
    for k in ("S1", "S2", "S3"):
        conds += [CondicionQ(k, k, "expo_obst"),
                  CondicionQ(f"{k}_ctrl", k, "expo_ctrl"),
                  CondicionQ(f"{k}_fant", k, "expo_fant")]
    return conds


def control(n_trab: int, huella: str) -> List[str]:
    """Las 1000 corridas del Exp O por el camino nuevo, bit a bit."""
    print("  CONTROL bit a bit con velocidad cero (1000 corridas)…", flush=True)
    filas = correr_condiciones(condiciones_control(), n_trab, "control", huella)
    escribir_csv(filas, RUTA_CONTROL_CSV)
    i1, n1, c1, m1 = comparar_con_csv(filas, RUTA_CSV_O)
    i2, n2, c2, m2 = comparar_con_csv(filas, RUTA_CSV_O_COMP)
    distintas = len({(str(f["condicion"]), int(f["seed_ep"])) for f in filas})
    ok = not m1 and not m2 and i1 == n1 and i2 == n2
    L = [f"CONTROL bit a bit (camino nuevo, trayectorias quietas en las posiciones "
         f"del Exp O): {distintas} corridas distintas; {i1}/{n1} filas idénticas en "
         f"las {c1} columnas de experimento_O_completo.csv y {i2}/{n2} en las {c2} "
         f"de experimento_O_complementario.csv (todas salvo t_episodio_s; texto "
         f"idéntico, repr de cada float)"]
    L += [f"    principal: {m}" for m in m1[:10]] + [f"    complementario: {m}" for m in m2[:10]]
    L.append("CONTROL: OK" if ok else "CONTROL: NO REPRODUCE")
    _escribir_registro(RUTA_CONTROL_TXT, L, huella)
    for x in L:
        print("  " + x, flush=True)
    if not ok:
        raise SystemExit("PARAR: el camino nuevo no reproduce el Exp O bit a bit.")
    return L[:-1]


def negativo(n_trab: int, huella: str) -> List[str]:
    """
    Control de la INSTRUMENTACIÓN (no es un resultado): el obstáculo móvil de
    S1 sin su fila en el filtro, 10 semillas. Tiene que dar contactos: muestra
    que el contador ve los contactos con algo que se mueve.
    """
    conds = [CondicionQ("S1_sinfila", "S1", TIPO_NEGATIVO)]
    filas = correr_condiciones(conds, n_trab, "negativo", huella, semillas_protocolo()[:10])
    escribir_csv(filas, RUTA_NEGATIVO_CSV)
    ev = sum(int(f["contactos_obst_eventos"]) for f in filas)
    emp = sum(int(f["contactos_obst_empuje"]) for f in filas)
    eps = sum(int(f["contactos_obst_eventos"]) > 0 for f in filas)
    ok = ev > 0
    L = [f"CONTROL NEGATIVO (S1 móvil sin fila del obstáculo, 10 semillas): "
         f"contactos {ev} eventos ({emp} por empuje) en {eps}/10 episodios; "
         f"d_min centro→superficie mínimo "
         f"{min(float(f['d_min_obst_superficie']) for f in filas):.8f} m → "
         f"{'el contador DETECTA contactos con un obstáculo móvil' if ok else 'NO detecta: revisar'}",
         "NEGATIVO: OK" if ok else "NEGATIVO: FALLA"]
    _escribir_registro(RUTA_NEGATIVO_TXT, L, huella)
    print("  " + L[0], flush=True)
    if not ok:
        raise SystemExit("PARAR: el control negativo no detecta contactos.")
    return L[:1]


# =============================================================================
# EXPERIMENTO
# =============================================================================

def condiciones_nivel(k: str) -> List[CondicionQ]:
    return [CondicionQ(f"{k}_{t}", k, t) for t in TIPOS_Q]


def experimento(n_trab: int, informe: List[str], huella: str) -> None:
    """S1 → S2 → S3 con la regla de parada por falla real sobre Sk_din."""
    for ruta, marca in ((RUTA_PASAB_TXT, "PASABILIDAD: OK"),
                        (RUTA_CONTROL_TXT, "CONTROL: OK"),
                        (RUTA_NEGATIVO_TXT, "NEGATIVO: OK")):
        motivo = _aprobado(ruta, marca, huella)
        if motivo:
            raise SystemExit(f"PARAR: {motivo}. Correr antes ese subcomando "
                             f"con este código.")
        informe += [x for x in ruta.read_text(encoding="utf-8").splitlines()
                    if not x.startswith(("HUELLA", "PASABILIDAD:", "CONTROL:",
                                         "NEGATIVO:"))]
    filas: List[Dict[str, str]] = []
    for k in ("S1", "S2", "S3"):
        nuevas = correr_condiciones(condiciones_nivel(k), n_trab, "experimento", huella)
        filas += nuevas
        for tipo in TIPOS_Q:
            if tipo == "ctrl":
                continue
            fk = [f for f in nuevas if f["tipo"] == tipo]
            interv = float(np.mean([float(f["cbf_frac_interv"]) for f in fk]))
            fallas = [(e, int(sum(float(f[c]) for f in fk))) for c, e in CRITERIOS_FALLA]
            papel = "DECIDE" if tipo == "din" else "se reporta"
            informe.append(f"{k}_{tipo} ({papel}): intervención media {interv:.8f} "
                           f"({'sobre' if interv > UMBRAL_INDICADOR else 'bajo'} el "
                           f"indicador {UMBRAL_INDICADOR}; no detiene); criterios — " +
                           "; ".join(f"{e} {v}" for e, v in fallas))
            print("  " + informe[-1], flush=True)
        fdin = [f for f in nuevas if f["tipo"] == "din"]
        if any(int(sum(float(f[c]) for f in fdin)) > 0 for c, _ in CRITERIOS_FALLA):
            informe.append(f"{k}: CRITERIO DE PARADA POR FALLA REAL en {k}_din — no "
                           f"se corren niveles más difíciles.")
            print("  " + informe[-1], flush=True)
            break
    escribir_csv(filas, RUTA_CSV_Q)
    _escribir_registro(RUTA_REG_Q, informe, huella)
    print(f"  CSV → {RUTA_CSV_Q} ({len(filas)} filas)", flush=True)


def main() -> None:
    DIR_SALIDA_Q.mkdir(parents=True, exist_ok=True)
    n_trab = max(1, (os.cpu_count() or 2) - 1)
    modo = sys.argv[1] if len(sys.argv) > 1 else ""
    if modo not in ("pasabilidad", "control", "negativo", "experimento"):
        raise SystemExit("uso: python correr_experimento_Q.py "
                         "{pasabilidad|control|negativo|experimento}")
    # La huella se toma AL EMPEZAR; cada registro comprueba que no cambió.
    huella = huella_codigo()
    print("═" * 74)
    print(f"  EXPERIMENTO Q — obstáculos móviles ({modo})")
    print("═" * 74)
    informe: List[str] = ["EXPERIMENTO Q — registro de corrida"]
    informe += verificar_copias()
    informe.append(verificar_stack())
    informe.append(f"procesos: {n_trab}")
    for x in informe[1:]:
        print("  " + x, flush=True)
    print(f"  huella del código: {huella}", flush=True)
    if modo == "pasabilidad":
        pasabilidad(n_trab, huella)
    elif modo == "control":
        control(n_trab, huella)
    elif modo == "negativo":
        negativo(n_trab, huella)
    else:
        experimento(n_trab, informe, huella)


if __name__ == "__main__":
    main()
