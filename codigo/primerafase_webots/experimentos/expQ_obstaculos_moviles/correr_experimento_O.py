"""
correr_experimento_O.py
=======================
EXPERIMENTO O — Obstáculos estáticos como barreras de EJECUCIÓN.

Encuadre (leer antes de interpretar)
------------------------------------
Esto NO prueba adaptabilidad de la política: la observación (24 dims: estado
propio 5, campo 3, vecindad 8, mapa AoI 8) no codifica obstáculos; el agente es
CIEGO a ellos. Lo que se prueba es la GENERALIDAD DE LA CAPA DE SEGURIDAD: que
la capa de ejecución absorbe obstáculos que la política no percibe, y a qué
costo en progreso de tarea.

Formulación
-----------
Obstáculos circulares tratados como vecinos fantasma inmóviles, por el mismo
camino de código que la barrera robot-robot, con el otro punto fijo:

    h_obst = ‖p − p_obs‖ − (r_obs + 0,18),   c = n^T·G(θ),   n = (p − p_obs)/‖·‖

con RESPONSABILIDAD COMPLETA (h, no h/2: el obstáculo no se mueve). Margen 0,18
por la misma regla que el de pared (0,075 chasis + 0,05 punto de mira + 0,031
avance entre decisiones = 0,156 ≤ 0,18). El escape suma también las normales
de obstáculo activas (h < 0,06).

Configuración: la final desplegada (modelo_sanidad, bloqueante, CBF + escape de
TRES términos), arena 3,0, n = 5, 100 semillas del protocolo.

Condiciones
-----------
    S0          sin obstáculos — CONTROL: debe reproducir bit a bit
                b3_W30_n5 del Exp N, por semilla. Si no, PARAR.
    Sk          escenario k con obstáculos (k = 1, 2, 3)
    Sk_ctrl     mismas poses iniciales (reubicadas) y mismos objetivos
                iniciales que Sk, SIN obstáculos: pareo exacto

Criterio de parada (corregido el 13/sep/2026): por FALLA REAL — contacto con
obstáculo, escape agotado, fallback del QP o escape infactible con obstáculo
activo, en cualquier episodio de Sk. La intervención > 0,5 se reporta como
indicador adelantado, fuera de su dominio de calibración, y no detiene.

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
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

from entorno_obstaculos import (Obstaculo, EntornoObstaculos, distancia_minima,
                                mascara_ocupada)

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

SEED_BASE:   int   = 42
N_EPISODIOS: int   = 100
N_AGENTES:   int   = 5
ARENA:       float = 3.0
MAX_STEPS:   int   = 500
COMM_RADIUS: float = 1.0
PESOS_TRIAL13: Dict[str, float] = {
    "lambda_gradient": 0.5622468083379316,
    "lambda_entropy":  1.1403296484190344,
    "lambda_ibrm":     0.48380314172632155,
    "lambda_cbf":      2.9655314099141474,
}

ELE_A, ALFA_CBF, W_OMEGA = 0.05, 2.0, 0.3
D_SEGURA, D_ROBOTS = 0.18, 0.25
MARGEN_OBS: float = 0.18
V_MAX, OMEGA_MAX = 0.31, 6.2832

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

MARGEN_CBF_M:      float = 0.18
RADIO_CHASIS:      float = 0.075
COTA_CENTRO_OBST:  float = MARGEN_OBS - ELE_A   # 0,13: peor caso de diseño
TOL_LIGANTE:       float = 1e-6
UMBRAL_INDICADOR:  float = 0.5   # criterio operativo: SE REPORTA, no detiene
ANCHO_PERIFERIA:   float = 0.50  # anillo perimetral de 5 m² (55,6 % de la arena)

# Criterio de parada por FALLA REAL (corrección del revisor, 13/sep/2026). El
# criterio original (intervención > 0,5) era un indicador adelantado calibrado
# en Webots con física de contacto, fuera de su dominio en Python: S1 lo cruzó
# (0,575) sin una sola falla. Se detiene al primer escenario con obstáculos en
# que CUALQUIERA de estas sumas sobre sus 100 episodios sea > 0.
CRITERIOS_FALLA: Tuple[Tuple[str, str], ...] = (
    ("contactos_obst_eventos",        "contacto con obstáculo"),
    ("escape_agotados",               "escape agotado"),
    ("qp_fallbacks",                  "fallback del QP"),
    ("escape_infactibles_junto_obst", "escape infactible con obstáculo activo"),
)
UMBRAL_PASO_GEOM:  float = 2 * D_SEGURA            # 0,36
UMBRAL_PASO_ESC:   float = 2 * (D_SEGURA + ESC_UMBRAL_ACTIVA)   # 0,48

ESCENARIOS: Dict[str, Tuple[Obstaculo, ...]] = {
    "S0": (),
    "S1": ((1.5, 1.5, 0.30),),
    "S2": ((1.0, 1.0, 0.25), (2.0, 2.0, 0.25)),
    "S3": ((0.75, 0.75, 0.20), (2.25, 0.75, 0.20), (0.75, 2.25, 0.20),
           (2.25, 2.25, 0.20), (1.5, 1.5, 0.25)),
}

RUTA_MODELO: Path = _CARPETA / "modelos" / "modelo_sanidad.zip"
RUTA_CSV_EXP_N: Path = (_CARPETA.parent / "expN_arena" / "resultados"
                        / "experimento_N_completo.csv")
DIR_SALIDA: Path = _CARPETA / "resultados"


@dataclass(frozen=True)
class Condicion:
    """
    Una celda: escenario y si sus obstáculos son físicos o sólo de sorteo.
    `rebote_fantasma`: los objetivos rebotan en los obstáculos del escenario
    aunque no sean físicos (control FANTASMA, 13/sep/2026).
    """
    nombre:    str
    escenario: str
    fisicos:   bool
    rebote_fantasma: bool = False


# =============================================================================
# CAPA DE SEGURIDAD
# =============================================================================

def punto_de_mira(pose: np.ndarray) -> np.ndarray:
    """p = c + ℓa·(cosθ, senθ)."""
    return np.array([pose[0] + ELE_A * math.cos(pose[2]),
                     pose[1] + ELE_A * math.sin(pose[2])])


def barreras_robot_robot(filtro, i: int, poses: np.ndarray) -> list:
    """Robot-robot con reparto 50/50 (idéntica al Exp N)."""
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
        extras.append(RestriccionLineal(c=(delta / dist) @ G_i,
                                        h=0.5 * (dist - D_ROBOTS),
                                        nombre=f"robot_{j}"))
    return extras


def barreras_obstaculos(filtro, pose: np.ndarray,
                        obst: Sequence[Obstaculo]) -> list:
    """Vecino fantasma inmóvil: mismo camino que robot-robot, h completo."""
    from lib.filtro_cbf import RestriccionLineal
    extras = []
    p = filtro._punto_de_mira(pose)
    G = filtro._matriz_G(float(pose[2]))
    for k, (ox, oy, r) in enumerate(obst):
        delta = p - np.array([ox, oy])
        dist = float(np.linalg.norm(delta))
        if dist < 1e-9:
            continue
        extras.append(RestriccionLineal(c=(delta / dist) @ G,
                                        h=dist - (r + MARGEN_OBS),
                                        nombre=f"obst_{k}"))
    return extras


def tipo_barrera(nombre: str) -> str:
    """pared / robot / obst."""
    if nombre.startswith("robot_"):
        return "robot"
    if nombre.startswith("obst_"):
        return "obst"
    return "pared"


class GestorEscape:
    """
    Escape del Exp N (tres términos) con las normales de obstáculo agregadas.
    Con `obst=()` es idéntico al del Exp N.
    """

    def __init__(self, n: int, arena: float, obst: Sequence[Obstaculo]) -> None:
        self.n, self.arena, self.obst = n, float(arena), tuple(obst)
        self.reset()

    def reset(self) -> None:
        n = self.n
        self.estado = [0] * n
        self.contador_det = [0] * n
        self.en_curso = [0] * n
        self.refractario = [0] * n
        self.intervino_prev = [False] * n
        self.pose_previa: Optional[np.ndarray] = None
        self.n_escapes = [0] * n
        self.n_escapes_obst = [0] * n
        self.decisiones = [0] * n
        self.infactibles = [0] * n
        self.infactibles_obst = [0] * n
        self.agotados = [0] * n
        # [13/sep] Motivo de cada "infactible" (sólo contadores, no cambia la
        # dinámica): "opuestas" = normales activas con suma de norma < 0,20
        # (infactibilidad real); "sin_activas" = ninguna barrera con h < 0,06
        # antes de ESC_MIN_DECISIONES (el escape ya salió: NO es falla).
        self.infact_opuestas = [0] * n
        self.infact_sin_activas = [0] * n
        self.infact_op_tipos: Dict[str, int] = {"pared": 0, "robot": 0, "obst": 0}
        self._motivo: str = ""
        self._tipos_activos: set = set()

    def normales_activas(self, i: int, poses: np.ndarray
                         ) -> Tuple[Optional[np.ndarray], float, bool]:
        """(dirección, h_min, hay_obstáculo_activo)."""
        p_i = punto_de_mira(poses[i])
        W = self.arena
        cand = [
            (np.array([1.0, 0.0]),  float(p_i[0]) - D_SEGURA, "pared"),
            (np.array([-1.0, 0.0]), (W - float(p_i[0])) - D_SEGURA, "pared"),
            (np.array([0.0, 1.0]),  float(p_i[1]) - D_SEGURA, "pared"),
            (np.array([0.0, -1.0]), (W - float(p_i[1])) - D_SEGURA, "pared"),
        ]
        for j in range(len(poses)):
            if j == i:
                continue
            delta = p_i - punto_de_mira(poses[j])
            dist = float(np.linalg.norm(delta))
            if dist < 1e-9:
                continue
            cand.append((delta / dist, dist - D_ROBOTS, "robot"))
        for ox, oy, r in self.obst:
            delta = p_i - np.array([ox, oy])
            dist = float(np.linalg.norm(delta))
            if dist < 1e-9:
                continue
            cand.append((delta / dist, dist - (r + MARGEN_OBS), "obst"))

        # "Junto a obstáculo" = obstáculo ACTIVO (h < 0,06), no el de h mínimo.
        normales, h_min, tipos = [], float("inf"), set()
        for normal, h, tipo in cand:
            h_min = min(h_min, h)
            if h < ESC_UMBRAL_ACTIVA:
                normales.append(normal)
                tipos.add(tipo)
        obst_activo = "obst" in tipos
        self._tipos_activos = tipos
        if not normales:
            self._motivo = "sin_activas"
            return None, h_min, obst_activo
        suma = np.sum(np.asarray(normales), axis=0)
        norma = float(np.linalg.norm(suma))
        if norma < ESC_NORMA_MINIMA:
            self._motivo = "opuestas"
            return None, h_min, obst_activo
        self._motivo = ""
        return suma / norma, h_min, obst_activo

    def _registrar_infactible(self, i: int) -> None:
        """Clasifica un 'infactible' por motivo (sólo contadores)."""
        if self._motivo == "opuestas":
            self.infact_opuestas[i] += 1
            for t in self._tipos_activos:
                self.infact_op_tipos[t] += 1
        else:
            self.infact_sin_activas[i] += 1

    @staticmethod
    def accion_escape(direccion: np.ndarray, theta: float) -> np.ndarray:
        heading = np.array([math.cos(theta), math.sin(theta)])
        perp = np.array([-math.sin(theta), math.cos(theta)])
        return np.array([ESC_FRACCION_V * V_MAX * np.sign(float(direccion @ heading)),
                         ESC_FRACCION_OMEGA * OMEGA_MAX * np.sign(float(direccion @ perp))],
                        dtype=np.float32)

    def gestionar(self, i: int, poses: np.ndarray, u_nom: np.ndarray
                  ) -> Tuple[np.ndarray, bool]:
        direccion, h_min, obst_activo = self.normales_activas(i, poses)
        if self.estado[i] == 2:
            self.refractario[i] -= 1
            if self.refractario[i] <= 0:
                self.estado[i] = 0
            return u_nom, False
        if self.estado[i] == 1:
            self.en_curso[i] += 1
            if self.en_curso[i] >= ESC_MAX_DECISIONES:
                self.agotados[i] += 1
            termina = ((self.en_curso[i] >= ESC_MIN_DECISIONES and h_min > ESC_H_SALIDA)
                       or self.en_curso[i] >= ESC_MAX_DECISIONES)
            if termina or direccion is None:
                if direccion is None and not termina:
                    self.infactibles[i] += 1
                    self.infactibles_obst[i] += int(obst_activo)
                    self._registrar_infactible(i)
                self.estado[i] = 2
                self.refractario[i] = ESC_REFRACTARIO
                self.en_curso[i] = 0
                self.contador_det[i] = 0
                return u_nom, False
            self.decisiones[i] += 1
            return self.accion_escape(direccion, float(poses[i, 2])), True

        desp = float("inf")
        if self.pose_previa is not None:
            desp = float(np.linalg.norm(poses[i, :2] - self.pose_previa[i, :2]))
        estancado = (desp < ESC_UMBRAL_DESPLAZAMIENTO and h_min < ESC_H_ENTRADA
                     and self.intervino_prev[i])
        self.contador_det[i] = self.contador_det[i] + 1 if estancado else 0
        if self.contador_det[i] >= ESC_N_DETECCION:
            if direccion is None:
                self.infactibles[i] += 1
                self.infactibles_obst[i] += int(obst_activo)
                self._registrar_infactible(i)
                self.contador_det[i] = 0
                self.estado[i] = 2
                self.refractario[i] = ESC_REFRACTARIO
                return u_nom, False
            self.estado[i] = 1
            self.en_curso[i] = 1
            self.contador_det[i] = 0
            self.n_escapes[i] += 1
            self.n_escapes_obst[i] += int(obst_activo)
            self.decisiones[i] += 1
            return self.accion_escape(direccion, float(poses[i, 2])), True
        return u_nom, False


# =============================================================================
# EPISODIO
# =============================================================================

_MODELO = None


def _inicializar_trabajador() -> None:
    import torch
    torch.set_num_threads(1)
    warnings.filterwarnings("ignore", message=r"\[FiltroCBF\]")


def correr_episodio(cond: Condicion, seed_ep: int) -> Dict[str, object]:
    """Un episodio determinista. Métricas SIN redondear."""
    global _MODELO
    from lib.filtro_cbf import FiltroCBFParedes
    if _MODELO is None:
        from stable_baselines3 import PPO
        _MODELO = PPO.load(str(RUTA_MODELO), device="cpu")

    t0 = time.perf_counter()
    obst_esc = ESCENARIOS[cond.escenario]
    obst_fis = obst_esc if cond.fisicos else ()
    obst_reb = obst_esc if (cond.fisicos or cond.rebote_fantasma) else ()
    env = EntornoObstaculos(
        obstaculos_fisicos=obst_fis, obstaculos_sorteo=obst_esc,
        obstaculos_rebote=obst_reb,
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
    # Máscara del ESCENARIO (también en el control, sólo para la métrica).
    mascara = mascara_ocupada(env._field._grid_xx, env._field._grid_yy, obst_esc)

    filtro = FiltroCBFParedes(arena_size=(ARENA, ARENA), ele_a=ELE_A, alfa=ALFA_CBF,
                              d_segura=D_SEGURA, w_omega=W_OMEGA,
                              v_max=V_MAX, omega_max=OMEGA_MAX)
    gestor = GestorEscape(n_a, ARENA, obst_fis)

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
    suma_mag = 0.0
    done = False

    while not done:
        acciones, _ = _MODELO.predict(np.stack([obs[a] for a in agentes]),
                                      deterministic=True)
        acciones = np.asarray(acciones, dtype=np.float32)
        poses = np.array([env._estados[a][:3] for a in agentes])
        for i in range(n_a):
            accion_i, en_escape = gestor.gestionar(i, poses, acciones[i])
            acciones[i] = accion_i
            extras = barreras_robot_robot(filtro, i, poses)
            if obst_fis:
                extras = extras + barreras_obstaculos(filtro, poses[i], obst_fis)
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
            cont["fallback"] += int(not res.exito_qp)
            gestor.intervino_prev[i] = bool(res.intervino)
            acciones[i] = np.asarray(res.u_seguro, dtype=np.float32)
        gestor.pose_previa = poses.copy()

        obs, _, term, trunc, _ = env.step({a: acciones[k] for k, a in enumerate(agentes)})
        n_pasos += 1
        pos = np.array([env._estados[a][:2] for a in agentes])
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
            if obst_esc:
                do = distancia_minima(pos[k], obst_esc)
                d_min_obst = min(d_min_obst, do)
                if do < COTA_CENTRO_OBST:
                    viol_cota_obst[k] = True
        done = all(trunc.values()) or all(term.values())

    grid = env._field._grid_aoi.astype(np.float64)
    acc = ~mascara
    ap = n_pasos * n_a
    cob_acc = 1.0 - float(np.mean(grid[acc]))
    if cond.fisicos:
        cob_sin = 1.0 - (float(np.sum(grid[acc])) + float(np.sum(mascara))) / grid.size
    else:
        cob_sin = 1.0 - float(np.mean(env._field._grid_aoi))
    return {
        "condicion": cond.nombre, "escenario": cond.escenario,
        "fisicos": int(cond.fisicos), "seed_ep": seed_ep,
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
        "rebote_fantasma": int(cond.rebote_fantasma),
        "escape_agotados": sum(gestor.agotados),
        "escape_filtro_modifico": cont["esc_mod"],
        "agentes_reubicados": env.n_agentes_reubicados,
        "objetivos_reubicados": env._field.n_objetivos_reubicados,
        "rebotes_objetivo_obst": env._field.n_rebotes_obstaculo,
        "uso_grid_fallback": uso_fallback,
        "pasos": n_pasos,
        "t_episodio_s": time.perf_counter() - t0,
    }


def _tarea(args: Tuple[Condicion, int]) -> Dict[str, object]:
    return correr_episodio(*args)


# =============================================================================
# GEOMETRÍA, CONTROL, EJECUCIÓN
# =============================================================================

def verificar_pasabilidad(nombre: str, obst: Sequence[Obstaculo]) -> List[str]:
    """Huecos mínimos y conectividad del conjunto factible del punto de mira."""
    from scipy.ndimage import label
    L = []
    if not obst:
        return L
    gw = min(min(ox - r, ARENA - ox - r, oy - r, ARENA - oy - r) for ox, oy, r in obst)
    go = min([math.hypot(a[0] - b[0], a[1] - b[1]) - a[2] - b[2]
              for k, a in enumerate(obst) for b in obst[k + 1:]] or [float("inf")])
    g = 0.005
    fx = np.arange(g / 2, ARENA, g)
    FX, FY = np.meshgrid(fx, fx, indexing="ij")
    comps = {}
    for etiq, extra in (("h≥0", 0.0), ("h≥0,06", ESC_UMBRAL_ACTIVA)):
        m = ((FX >= D_SEGURA + extra) & (FX <= ARENA - D_SEGURA - extra)
             & (FY >= D_SEGURA + extra) & (FY <= ARENA - D_SEGURA - extra))
        for ox, oy, r in obst:
            m &= (FX - ox) ** 2 + (FY - oy) ** 2 >= (r + MARGEN_OBS + extra) ** 2
        comps[etiq] = (label(m)[1], float(m.sum()) * g * g)
    ok = (min(gw, go) > UMBRAL_PASO_ESC and comps["h≥0"][0] == 1
          and comps["h≥0,06"][0] == 1)
    L.append(f"{nombre}: hueco mín. obst–pared {gw:.4f} m, obst–obst {go:.4f} m "
             f"(umbral geométrico {UMBRAL_PASO_GEOM:.2f}, con escape "
             f"{UMBRAL_PASO_ESC:.2f}); región factible h≥0: {comps['h≥0'][1]:.6f} m², "
             f"{comps['h≥0'][0]} comp.; h≥0,06: {comps['h≥0,06'][1]:.6f} m², "
             f"{comps['h≥0,06'][0]} comp. → {'PASABLE' if ok else 'NO PASABLE'}")
    if not ok:
        raise SystemExit(f"PARAR: {nombre} no es pasable por construcción.")
    return L


def escribir_csv(filas: List[Dict[str, object]], ruta: Path) -> None:
    """CSV sin redondeo, con respaldo si ya existía."""
    if ruta.exists():
        sello = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta.rename(ruta.with_name(f"{ruta.stem}_respaldo_{sello}{ruta.suffix}"))
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()), lineterminator="\n")
        w.writeheader()
        for fila in filas:
            w.writerow({k: (repr(v) if isinstance(v, float) else v) for k, v in fila.items()})


def correr(conds: Sequence[Condicion], n_trab: int) -> List[Dict[str, object]]:
    semillas = [SEED_BASE * 10_000 + i for i in range(N_EPISODIOS)]
    tareas = [(c, s) for c in conds for s in semillas]
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=n_trab, initializer=_inicializar_trabajador) as ex:
        filas = list(ex.map(_tarea, tareas, chunksize=1))
    for c in conds:
        fc = [f for f in filas if f["condicion"] == c.nombre]
        print(f"  {c.nombre:9s} cob_acc={np.mean([f['cobertura_accesible'] for f in fc]):.8f} "
              f"interv={np.mean([f['cbf_frac_interv'] for f in fc]):.6f} "
              f"t/ep={np.mean([f['t_episodio_s'] for f in fc]):.2f} s")
    print(f"  tiempo de pared {time.perf_counter() - t0:.1f} s")
    return filas


def control_S0(filas: List[Dict[str, object]]) -> str:
    """S0 debe reproducir b3_W30_n5 del Exp N bit a bit, por semilla."""
    ref: Dict[int, Dict[str, str]] = {}
    with open(RUTA_CSV_EXP_N, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["condicion"] == "b3_W30_n5":
                ref[int(r["seed_ep"])] = r
    # cobertura_protocolo usa la MISMA fórmula que el Exp N (media en float32);
    # cobertura_accesible acumula en float64 y difiere en el 8.º decimal.
    campos = (("cobertura_protocolo", "cobertura_aoi_final"),
              ("cbf_frac_interv", "cbf_frac_interv"),
              ("escape_n", "escape_n"),
              ("d_min_pared_centro", "d_min_pared_centro"))
    malas = [f["seed_ep"] for f in filas
             if any(float(f[a]) != float(ref[f["seed_ep"]][b]) for a, b in campos)]
    linea = (f"CONTROL S0 vs Exp N b3_W30_n5: {len(filas) - len(malas)}/{len(filas)} "
             f"semillas idénticas bit a bit en cobertura, intervención, escapes y d_min")
    print("  " + linea)
    if malas:
        print(f"  PARAR: no reproduce ({malas[:5]}).")
        sys.exit(1)
    return linea


def complementario(n_trab: int) -> None:
    """
    [13/sep] Corrida complementaria: S1–S3 × {Sk, Sk_ctrl, Sk_fant} con los
    contadores de motivo de infactibilidad. CONTROL: las filas Sk y Sk_ctrl
    deben reproducir bit a bit experimento_O_completo.csv (los contadores
    nuevos no alteran la dinámica). No pisa el CSV principal.
    """
    conds = [c for k in ("S1", "S2", "S3") for c in (
        Condicion(k, k, True), Condicion(f"{k}_ctrl", k, False),
        Condicion(f"{k}_fant", k, False, rebote_fantasma=True))]
    filas = correr(conds, n_trab)
    ref: Dict[Tuple[str, int], Dict[str, str]] = {}
    with open(DIR_SALIDA / "experimento_O_completo.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ref[(r["condicion"], int(r["seed_ep"]))] = r
    campos = ("cobertura_protocolo", "cobertura_accesible", "cbf_frac_interv",
              "escape_n", "escape_infactibles", "escape_infactibles_junto_obst",
              "escape_agotados", "d_min_obst_superficie")
    malas = [(f["condicion"], f["seed_ep"]) for f in filas
             if not f["condicion"].endswith("_fant")
             and any(float(f[c]) != float(ref[(f["condicion"], f["seed_ep"])][c])
                     for c in campos)]
    suma_ok = all(f["escape_infact_opuestas"] + f["escape_infact_sin_activas"]
                  == f["escape_infactibles"] for f in filas)
    n_ref = sum(1 for f in filas if not f["condicion"].endswith("_fant"))
    linea = (f"CONTROL complementario vs CSV principal: {n_ref - len(malas)}/{n_ref} "
             f"filas Sk/Sk_ctrl idénticas bit a bit; opuestas + sin_activas = "
             f"infactibles en todas las filas: {suma_ok}")
    print("  " + linea)
    escribir_csv(filas, DIR_SALIDA / "experimento_O_complementario.csv")
    (DIR_SALIDA / "registro_O_complementario.txt").write_bytes(
        (linea + "\n").encode("utf-8"))
    if malas or not suma_ok:
        print(f"  PARAR: el control complementario no reproduce ({malas[:5]}).")
        sys.exit(1)


def main() -> None:
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    n_trab = max(1, (os.cpu_count() or 2) - 1)
    if len(sys.argv) > 1 and sys.argv[1] == "complementario":
        complementario(n_trab)
        return
    informe: List[str] = ["EXPERIMENTO O — registro de corrida"]
    print("═" * 74)
    print("  EXPERIMENTO O — obstáculos como barreras de ejecución")
    print("═" * 74)
    for k in ("S1", "S2", "S3"):
        informe += verificar_pasabilidad(k, ESCENARIOS[k])
    for linea in informe[1:]:
        print("  " + linea)

    filas = correr([Condicion("S0", "S0", True)], n_trab)
    informe.append(control_S0(filas))

    for k in ("S1", "S2", "S3"):
        nuevas = correr([Condicion(k, k, True), Condicion(f"{k}_ctrl", k, False)], n_trab)
        filas += nuevas
        fk = [f for f in nuevas if f["condicion"] == k]
        interv = float(np.mean([f["cbf_frac_interv"] for f in fk]))
        informe.append(f"{k}: intervención media {interv:.8f} "
                       f"({'sobre' if interv > UMBRAL_INDICADOR else 'bajo'} el "
                       f"indicador {UMBRAL_INDICADOR}; se reporta, no detiene)")
        fallas = [(etiq, int(sum(float(f[c]) for f in fk))) for c, etiq in CRITERIOS_FALLA]
        informe.append(f"{k}: criterios de falla — " +
                       "; ".join(f"{e} {v}" for e, v in fallas))
        for linea in informe[-2:]:
            print("  " + linea)
        if any(v > 0 for _, v in fallas):
            linea = (f"{k}: CRITERIO DE PARADA POR FALLA REAL — no se corren "
                     f"escenarios más difíciles.")
            informe.append(linea)
            print("  " + linea)
            break

    escribir_csv(filas, DIR_SALIDA / "experimento_O_completo.csv")
    (DIR_SALIDA / "registro_O.txt").write_bytes(("\n".join(informe) + "\n").encode("utf-8"))
    print(f"  CSV → {DIR_SALIDA / 'experimento_O_completo.csv'} ({len(filas)} filas)")


if __name__ == "__main__":
    main()
