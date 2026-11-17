"""
demo_obstaculo_movil.py
=======================
Un 6.º Pololu 3pi+ como OBSTÁCULO MÓVIL no cooperativo en el Robotat. Las
etapas sueltas (L0, L1, L2) son la demo para el video; desde el 2026-10-08
la L2 con `--campana` es además una CAMPAÑA DE MEDICIÓN, con su libro, su
plan de análisis fijado antes y su réplica pareada (`tesis/PLAN_ANALISIS_
campana_L2.md`, `tesis/PROTOCOLO_L0_L2.md`).

Encuadre — leer antes que nada
------------------------------
La política NO ve al obstáculo: su observación (24 dimensiones) no lo
codifica. Lo que se muestra es la GENERALIDAD DE LA CAPA DE SEGURIDAD —el
filtro CBF de ejecución, extendido con un término de velocidad del obstáculo,
absorbe algo que se mueve y que la política no percibe—, no adaptabilidad de
la política. Es la extensión dinámica del Exp O (obstáculos estáticos).

Por qué un archivo aparte (decisión de José, 2026-10-01)
--------------------------------------------------------
Nada de lo que existe se edita: los 50 episodios válidos del 30-09 y sus
pruebas quedan intactos. Todo entra por HERENCIA sobre la pila del Robotat:

  · `FuentePosesConObstaculo`  pide los 6 marcadores en la MISMA consulta de
    lote (una por decisión, como siempre) y le entrega al coordinador sólo
    los 5 agentes; la pose del obstáculo queda aparte.
  · `CanalConObstaculo`        el robot del obstáculo va por un socket PROPIO,
    no como "agente 5": así `enlaces_caidos` sigue viendo sólo a los agentes
    (con el índice 5, `_correr_episodio` daría KeyError en `MAPEO_AGENTES[5]`)
    y `detener_todo` lo frena PRIMERO y después a los cinco.
  · `CoordinadorConObstaculo`  agrega UNA fila al QP de cada agente y la
    normal del obstáculo al escape. El resto de `_decidir_y_actuar` es el de
    siempre.
  · `SupervisorObstaculo`      mueve al obstáculo por un círculo, lo frena y
    aborta la toma ante cualquier anomalía suya.

La barrera (formulación F1)
---------------------------
Sobre el punto de mira p_i del agente y el CENTRO p_o del obstáculo:

    h   = ‖p_i − p_o‖ − D_o,             D_o = 0.15 + 0.18 = 0.33 m
    ḣ   = n·(ṗ_i − v_o),                 n = (p_i − p_o)/‖·‖
    c   = n·G(θ_i)
    rhs = −α·h + s/k,   s = max(0, n·v̂_o, n·v_cmd)

El filtro impone c·u ≥ rhs sobre la acción COMANDADA u; el canal ejecuta
k·u (k = `factor_total()`, 0.40 en régimen), y por eso el término de
velocidad va dividido por k: el agente tiene que COMANDAR s/k para EJECUTAR
s. El término −α·h no se divide —igual que en las paredes—, lo que deja una
convergencia efectiva k·α hacia el borde, más lenta y del lado seguro.
`v̂_o` es la velocidad MEDIDA (ventana de 0.3 s) y `v_cmd` la COMANDADA al
obstáculo en esta decisión: con 0.45–0.85 s de retardo de actuación, la
comandada anticipa lo que la medida todavía no ve. `max(0, ·)` descarta el
alivio de un obstáculo que se aleja.

`rhs` se satura al 90 % de la capacidad de la caja en esa fila
(|c_v|·V_MAX + |c_ω|·Ω_MAX): pedir más es infactible y el QP caería al
fallback (0, 0), que frente a algo que se acerca es lo peor. Entra al
filtro, que impone c·u ≥ −α·h, como h_eq = −rhs/α.

Con v_o = 0 y sin saturación la fila es EXACTAMENTE la del Exp O con
r = 0.15 (`barreras_obstaculos`, `correr_experimento_O.py:181-196`): hay
prueba bit a bit.

La formulación F0 ("sumarlo como un robot más": barrera robot-robot de
siempre, 50/50, punto de mira del obstáculo, vecino supuesto quieto) existe
SÓLO como control negativo de las pruebas: el modelo 1D de la propuesta
predice colisión con ella.

Freno de respaldo y criterio de toma válida (decisión de José)
---------------------------------------------------------------
El obstáculo frena si un agente queda a < 0.25 m por delante, o si un agente
en RETROCESO por pose repetida (que va por mandos directos, sin CBF) queda a
< 0.60 m. Es una capa REDUNDANTE: la separación la sostiene el filtro de los
agentes con su rescate (en la Fase 0, con el freno en sombra, lo hizo solo).
Una toma en la que el obstáculo frenó NO cuenta para el video —ya no muestra
al filtro solo—: se cuenta aparte ("intervención del freno de respaldo") y la
toma válida para la demo exige CERO frenos. `freno_activo=False` lo deja en
SOMBRA: se cuenta cuándo habría frenado, pero no frena. Así corre la campaña
de seguridad de la Fase 0, para que la distancia medida sea la del filtro
solo.

Reglas de parada de la sesión (L1/L2; 2026-10-03, OK de José)
-------------------------------------------------------------
Después de cada toma corrida, válida o no, la sesión frena todo, se DETIENE
y pregunta antes de seguir si hubo CONTACTO (un agente a < 0.15 m del
obstáculo, medido), si hubo intervención del FRENO en dos tomas seguidas, o
si la toma se abortó POR EL OBSTÁCULO (no se mueve, no frena, enlace caído,
se salió del círculo, marcador perdido). Sólo una "s" explícita la continúa;
cualquier otra respuesta la termina. Antes dependía de que el operador
estuviera mirando la consola.

Etapas del laboratorio
----------------------
  L0  el obstáculo solo: marcador vivo, patada de arranque 10 de 10 y error
      radial < 5 cm siguiendo el círculo.
  L1  el obstáculo APAGADO y quieto en el centro: el Exp O en físico.
  L2  el obstáculo en movimiento: círculo antihorario de R = 0.60 m centrado
      en (1.5, 1.5) del env, a 0.05 m/s, con patada de 0.08 m/s ≤ 1 s.

⚠ La parada por software NO es una parada de emergencia (README §S1). Con el
obstáculo en marcha tiene que haber una persona junto a la arena que pueda
levantarlo.

Uso
---
    python demo_obstaculo_movil.py --modo L0 --robot-obstaculo 4
    python demo_obstaculo_movil.py --modo L1 --tomas 3 --intentos 6 --robot-obstaculo 4
    python demo_obstaculo_movil.py --modo L2 --tomas 10 --intentos 20 --robot-obstaculo 4
    # Campaña de medición (el protocolo tiene el detalle):
    python demo_obstaculo_movil.py --modo L2 --robot-obstaculo 4 --campana L2_obstaculo_2 --crear-campana
    python demo_obstaculo_movil.py --modo L2 --robot-obstaculo 4 --campana L2_obstaculo_2 --hora-fin 17:30

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import argparse
import atexit
import csv
import io
import math
import os
import socket
import sys
import time
import warnings
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import config_robotat as cfg
from adaptadores_robotat import (
    RECONEXION_INTERVALO_S,
    RECONEXION_TIMEOUT_S,
    CanalActuacionRobotat,
    EntornoEjecucionRobotat,
    FuentePosesRobotat,
    RobotsInalcanzables,
    _clase_fallo_conexion,
)
from coordinador_enjambre import (
    ALFA_CBF,
    ARENA_SIZE,
    ESC_NORMA_MINIMA,
    ESC_UMBRAL_ACTIVA,
    CoordinadorEnjambre,
)
from lib.filtro_cbf import FiltroCBFParedes, RestriccionLineal
from protocolo_robotat import (
    accion_a_rpm,
    codificar_peticion_poses,
    codificar_velocidades_rueda,
    heading_desde_cuaternion,
    lab_a_env,
    pose_es_valida,
)

# =============================================================================
# CONSTANTES
# =============================================================================

#: Robot y marcador del obstáculo. El 7 tiene offset en la tabla del
#: laboratorio (`config_robotat.OFFSETS_RUMBO_POR_ROBOT`); el 4 es la reserva.
#: Ninguno de los dos se probó nunca: la L0 no es opcional.
ID_ROBOT_OBSTACULO: int = 7
ID_MARCADOR_OBSTACULO: int = 7
ID_ROBOT_RESERVA: int = 4

#: Radio efectivo del obstáculo = umbral de colisión de la tesis entre
#: CENTROS (0.15 m, el `D_SAFE` del entorno; dos 3pi se tocan a ~0.10 m).
R_EFECTIVO_OBSTACULO_M: float = 0.15
#: Margen del punto de mira: el mismo de las paredes y del Exp O.
MARGEN_OBSTACULO_M: float = 0.18
#: D_o de la barrera, sobre punto de mira (agente) y centro (obstáculo).
D_OBSTACULO_M: float = R_EFECTIVO_OBSTACULO_M + MARGEN_OBSTACULO_M

#: Fracción de la capacidad de la caja a la que se satura el lado derecho.
FRACCION_CAPACIDAD: float = 0.90
#: Piso de k en s/k: durante la rampa k = 0.25 × 0.40 = 0.10, y el obstáculo
#: está quieto; esto sólo evita una división por cero si alguien fija 0.
FACTOR_MINIMO: float = 0.05

#: Ventana de la velocidad medida del obstáculo, y zona muerta (el ruido de
#: captura de un obstáculo quieto no debe pedirle nada a los agentes).
VENTANA_VELOCIDAD_S: float = 0.30
ZONA_MUERTA_VELOCIDAD_M_S: float = 0.01

# ── Trayectoria (L2) ──────────────────────────────────────────────────────
#: Centro del círculo en el env y radio: queda a 0.90 m de cada pared; el
#: corredor del punto de mira entre el obstáculo y la pared es
#: 0.90 − 0.33 − 0.18 = 0.39 m, así que nunca encierra a un agente contra ella.
CENTRO_CIRCULO_ENV: Tuple[float, float] = (1.5, 1.5)
RADIO_CIRCULO_M: float = 0.60
#: Crucero, y patada de arranque: a 0.05 m/s el 3pi tardó 849 ms en moverse
#: y 1 de 5 veces no se movió (memoria del 29-08). La patada usa `V_COL`.
V_CRUCERO_M_S: float = 0.05
V_PATADA_M_S: float = 0.08
T_PATADA_MAX_S: float = 1.0
#: La patada termina antes si ya se mide movimiento.
V_MOVIMIENTO_DETECTADO_M_S: float = 0.02
#: Tope de giro del obstáculo (`OMEGA_LAB` de laboratorio11.m).
OMEGA_MAX_OBSTACULO: float = 1.0
GANANCIA_RADIAL: float = 3.0      # 1/m: corrección de rumbo por error radial
#: 1/s. Era 2.0: con retardo puro τ el lazo de rumbo dθ/dt = −k·θ(t − τ) es
#: estable sólo si k·τ < π/2, y con τ = 0.85 s daba 1.7 (revisión de la
#: Fase 0: ciclo límite saturado en ±1 rad/s con un arranque fuera de rumbo).
#: Con 1.0, k·τ = 0.85.
GANANCIA_RUMBO: float = 1.0

# ── Freno de respaldo y abortos ───────────────────────────────────────────
#: Era 0.20: con τ = 0.85 s el obstáculo sigue 0.05·0.85 ≈ 4 cm después de
#: la orden de freno y quedaría a ~0.157 m de un agente quieto. Con 0.25, a
#: ~0.21. La barrera F2 mantiene el centro a ≥ 0.28 m en régimen, así que el
#: freno sólo actúa si ya la erosionó 3 cm o más.
FRENO_DIST_FRENTE_M: float = 0.25
FRENO_DIST_RETROCESO_M: float = 0.60
#: Histéresis: reanuda recién con todos más allá de estas distancias.
REANUDA_DIST_FRENTE_M: float = 0.33
REANUDA_DIST_RETROCESO_M: float = 0.70
#: Error radial a partir del cual el obstáculo "se salió de su círculo".
ERROR_RADIAL_MAX_M: float = 0.10
#: Obediencia del obstáculo (revisión de la Fase 0: nada comparaba lo
#: comandado con lo medido). Tras `T_VERIFICACION_OBEDIENCIA_S` con la misma
#: clase de orden (0.85 s de retardo + 0.30 s de ventana de v̂ + margen):
#: en marcha y quieto → "no se mueve"; parado y moviéndose → "no frena".
T_VERIFICACION_OBEDIENCIA_S: float = 1.5
#: ... y la condición tiene que cumplirse en estas decisiones SEGUIDAS con
#: estimación válida de la velocidad (arreglo del 2026-10-02, OK de José: un
#: hipo del lazo de 0.374 s dejó la ventana de v̂ vacía, la función devolvió
#: 0 como si "no sé" fuera "quieto", y se abortó una toma con el obstáculo
#: andando a 0.05 m/s; ver tesis/PROPUESTA_obediencia_obstaculo.md).
N_CONFIRMACION_OBEDIENCIA: int = 5
V_SIN_MOVIMIENTO_M_S: float = 0.01
V_NO_FRENA_M_S: float = 0.02
#: Orden "de marcha" a partir de esta velocidad.
V_ORDEN_MARCHA_M_S: float = 0.02
#: Toma válida para la demo: el obstáculo recorrió al menos esta fracción
#: de lo que se le comandó (si se le comandó al menos 0.20 m).
FRACCION_RECORRIDO_MIN: float = 0.5

# ── Reglas de parada de la sesión (L1/L2) ─────────────────────────────────
#: Contacto: un agente a menos de esto del obstáculo, entre centros, en la
#: distancia MEDIDA a 10 Hz (`d_min_obst_medida`; el mismo umbral que usa
#: `validez_demo`).
UMBRAL_CONTACTO_M: float = 0.15
#: Tomas corridas SEGUIDAS con intervención del freno de respaldo que
#: detienen la sesión (≥ 2).
TOMAS_CON_FRENO_SEGUIDAS: int = 2

# ── Colocación (L1/L2) ────────────────────────────────────────────────────
#: Separación mínima entre centros de agentes y obstáculo al arrancar. Con el
#: punto de mira a 0.05 m del centro, deja h ≥ 0.12 en cualquier rumbo.
SEPARACION_ARRANQUE_OBSTACULO_M: float = 0.50
TOL_COLOCACION_OBSTACULO_M: float = 0.08
TOL_RUMBO_OBSTACULO_RAD: float = math.radians(30.0)
#: Punto del obstáculo en la L1: el centro de la arena, como el S1 del Exp O.
PUNTO_L1_ENV: Tuple[float, float] = (1.5, 1.5)

#: Carpeta de salida propia: nada de esto se escribe en `resultados_sesion/`.
DIR_SALIDA_DEMO: Path = _CARPETA / "resultados_demo_obstaculo"

#: Formulaciones de la fila del obstáculo. F2 = F1 evaluada en el estado
#: PREDICHO al instante en que se ejecuta la orden (ver `predecir_pose`).
FORMULACIONES: Tuple[str, ...] = ("F2", "F1", "F0", "ninguna")

#: Retardo que compensa el predictor de F2, en segundos.
TAU_PREDICCION_S: float = 0.65

#: Peso de ω en el costo del QP del agente cuya fila del obstáculo está
#: cerca de ligar (h_eq < `UMBRAL_PESO_GIRO_M`). El de siempre es 0.3
#: (`W_OMEGA`): con él, el QP paga el término de velocidad del obstáculo
#: GIRANDO —mueve el punto de mira sobre un círculo de 5 cm, no el centro—,
#: y con un rumbo predicho bajo un τ distinto del real ω entra en un ciclo
#: bang-bang que deja h ≈ −4 cm sostenido (revisión de la Fase 0). Con 3.0
#: el QP prefiere trasladar. Sólo en F2; F1 y F0 quedan como se propusieron.
PESO_GIRO_OBSTACULO: float = 3.0
UMBRAL_PESO_GIRO_M: float = 0.15
#: ... pero SÓLO si ninguna otra fila (pared o robot) está a menos de esto
#: de ligar. Campaña de la Fase 0: con otra barrera activa —un vecino que
#: encierra al agente contra el obstáculo— girar es justamente la salida
#: lateral, y encarecerlo lo empujaba en línea recta contra el vecino (QP
#: infactible, rescates, 0.122 m con τ = 0.85 s, contra 0.294 m sin peso).
UMBRAL_OTRAS_ACTIVAS_M: float = 0.06


def _envolver(a: float) -> float:
    """Ángulo a (−π, π]."""
    return math.atan2(math.sin(a), math.cos(a))


def _velocidad_o_cero(v: Optional[np.ndarray]) -> np.ndarray:
    """La velocidad medida, o cero si no hay estimación (uso en la barrera)."""
    return np.zeros(2) if v is None else v


# =============================================================================
# PREDICTOR DEL RETARDO DE ACTUACIÓN (formulación F2)
# =============================================================================

def integrar_uniciclo(pose: np.ndarray,
                      tramos: Sequence[Tuple[float, float, float]]
                      ) -> np.ndarray:
    """Integra EXACTAMENTE el uniciclo por tramos (duración, v, ω) constantes."""
    x, y, th = float(pose[0]), float(pose[1]), float(pose[2])
    for dur, v, w in tramos:
        if dur <= 0.0:
            continue
        if abs(w) < 1e-9:
            x += v * math.cos(th) * dur
            y += v * math.sin(th) * dur
        else:
            th1 = th + w * dur
            x += (v / w) * (math.sin(th1) - math.sin(th))
            y -= (v / w) * (math.cos(th1) - math.cos(th))
            th = th1
    return np.array([x, y, _envolver(th)], dtype=np.float64)


def predecir_pose(pose: np.ndarray,
                  mandos: Sequence[Tuple[float, float, float]],
                  ahora: float, tau: float) -> np.ndarray:
    """
    Pose en `ahora + tau`, suponiendo un retardo de actuación PURO `tau`: la
    orden enviada en t_j rige en las ruedas desde t_j + tau. Se integra
    desde la pose medida con las órdenes YA ENVIADAS que se ejecutan en
    (ahora, ahora + tau] —las "en vuelo"—, que son exactamente lo que la
    orden nueva no puede cambiar.

    `mandos`: (instante de envío, v, ω) en orden de envío. Antes del primero
    se supone el robot quieto (el canal olvida su historial al empezar cada
    episodio, con los robots detenidos).

    Es la idea del predictor para barreras con retardo de entrada (Molnar,
    Kiss, Ames y Orosz, 2023), aplicada sólo a la fila del obstáculo.
    """
    if tau <= 0.0:
        return np.asarray(pose, dtype=np.float64).copy()
    inicio, fin = float(ahora), float(ahora) + float(tau)
    activo: Tuple[float, float] = (0.0, 0.0)
    cambios: List[Tuple[float, float, float]] = []
    for t, v, w in mandos:
        e = float(t) + float(tau)
        if e <= inicio:
            activo = (float(v), float(w))
        elif e < fin:
            cambios.append((e, float(v), float(w)))
    tramos: List[Tuple[float, float, float]] = []
    t_prev, actual = inicio, activo
    for e, v, w in cambios:
        tramos.append((e - t_prev, actual[0], actual[1]))
        t_prev, actual = e, (v, w)
    tramos.append((fin - t_prev, actual[0], actual[1]))
    return integrar_uniciclo(pose, tramos)


# =============================================================================
# FILTRO: PESO DE GIRO Y RESCATE ANTE INFACTIBILIDAD (sólo F2)
# =============================================================================

class FiltroConObstaculo(FiltroCBFParedes):
    """
    `FiltroCBFParedes` (lib/filtro_cbf.py, sin tocar) con dos agregados que
    sólo actúan cuando la fila "obstaculo" está entre las restricciones:

    1. **Peso de giro.** Si la fila está cerca de ligar, el QP de ESE agente
       usa `peso_giro_obstaculo` en lugar de `w_omega` (ver
       `PESO_GIRO_OBSTACULO`). Se restaura al volver.

    2. **Rescate.** Si el QP es infactible con la fila del obstáculo —la
       revisión encontró casos con la fila evaluada en el estado predicho y
       las robot-robot en el actual—, en vez de caer directamente a
       u = (0, 0), que frente a algo que se acerca es lo peor, se reintenta:
         nivel 1: el lado derecho de la fila, al 50 % de su capacidad;
         nivel 2: la fila sin término de velocidad ni deuda (c·u ≥ 0: por lo
                  menos no acercarse).
       Sólo si los dos fallan, el fallback de siempre (contado como tal).

    `None` / False en los dos atributos = el filtro de siempre, bit a bit.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.peso_giro_obstaculo: Optional[float] = None
        self.rescate_obstaculo: bool = False
        self.reiniciar_contadores()

    def reiniciar_contadores(self) -> None:
        self.decisiones_peso_giro: int = 0
        self.rescates: Dict[str, int] = {"nivel_1": 0, "nivel_2": 0,
                                         "sin_rescate": 0}

    def _filtrar_sin_aviso(self, pose: np.ndarray, u: np.ndarray,
                           extras: List[RestriccionLineal]):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return FiltroCBFParedes.filtrar(self, pose, u,
                                            restricciones_extra=extras)

    def filtrar(self, pose: np.ndarray, u_nominal: np.ndarray,
                restricciones_extra: Optional[List[RestriccionLineal]] = None):
        extras = list(restricciones_extra or [])
        indices = [k for k, r in enumerate(extras) if r.nombre == "obstaculo"]
        if not indices or (self.peso_giro_obstaculo is None
                           and not self.rescate_obstaculo):
            return super().filtrar(pose, u_nominal,
                                   restricciones_extra=restricciones_extra)
        k = indices[0]
        fila = extras[k]
        w_previo = self.w_omega
        if (self.peso_giro_obstaculo is not None
                and fila.h < UMBRAL_PESO_GIRO_M):
            otras = [r.h for j, r in enumerate(extras) if j != k]
            otras += [r.h for r in self._barreras_paredes(
                self._punto_de_mira(pose), float(pose[2]))]
            if all(h >= UMBRAL_OTRAS_ACTIVAS_M for h in otras):
                self.w_omega = float(self.peso_giro_obstaculo)
                self.decisiones_peso_giro += 1
        try:
            if not self.rescate_obstaculo:
                return super().filtrar(pose, u_nominal,
                                       restricciones_extra=extras)
            res = self._filtrar_sin_aviso(pose, u_nominal, extras)
            if res.exito_qp:
                return res
            cap = (abs(float(fila.c[0])) * self.v_max
                   + abs(float(fila.c[1])) * self.omega_max)
            for nivel, h_nuevo in (
                    ("nivel_1", max(float(fila.h), -0.5 * cap / self.alfa)),
                    ("nivel_2", max(float(fila.h), 0.0))):
                if h_nuevo == float(fila.h):
                    continue
                otras = list(extras)
                otras[k] = RestriccionLineal(c=fila.c, h=h_nuevo,
                                             nombre="obstaculo")
                res2 = self._filtrar_sin_aviso(pose, u_nominal, otras)
                if res2.exito_qp:
                    self.rescates[nivel] += 1
                    return res2
            self.rescates["sin_rescate"] += 1
            warnings.warn(
                f"[FiltroConObstaculo] QP infactible aun con rescate "
                f"(h_min={res.h_minima:.3f} m). Fallback u=(0,0).",
                RuntimeWarning, stacklevel=2)
            return res
        finally:
            self.w_omega = w_previo


# =============================================================================
# FUENTE: 6 MARCADORES EN UNA CONSULTA
# =============================================================================

class FuentePosesConObstaculo(FuentePosesRobotat):
    """
    `FuentePosesRobotat` que además lee el marcador del obstáculo en la MISMA
    consulta de lote.

    Al coordinador le entrega exactamente lo de siempre —las poses de los N
    agentes—, así que su caché, su política de "última pose conocida" y su
    medición de antigüedad no cambian. La fila del obstáculo se valida con la
    misma `pose_es_valida`, se transforma con el mismo `lab_a_env` (y el
    offset de rumbo de SU robot) y se guarda aparte, con su historial para la
    velocidad medida y un contador de repeticiones bit a bit (la firma del
    marcador congelado: Motive retiene la última pose en los puntos ciegos).

    Sólo modo "lote": en "individual" cada marcador sería otra consulta y la
    tasa dejaría de ser una por decisión.
    """

    nombre: str = "robotat_obstaculo"

    def __init__(
        self,
        n_agentes:             int,
        id_marcador_obstaculo: int = ID_MARCADOR_OBSTACULO,
        id_robot_obstaculo:    int = ID_ROBOT_OBSTACULO,
        obtener_tick:          Optional[Callable[[], int]] = None,
    ) -> None:
        super().__init__(n_agentes, obtener_tick)
        if self._modo_consulta != "lote":
            raise ValueError(
                "la demo del obstáculo exige MODO_CONSULTA_POSES = 'lote': "
                "en 'individual' el obstáculo sería una consulta más por "
                "decisión.")
        if int(id_marcador_obstaculo) in self._marcadores:
            raise ValueError(
                f"el marcador del obstáculo ({id_marcador_obstaculo}) ya es "
                f"de un agente: {self._marcadores}")
        self.id_marcador_obstaculo: int = int(id_marcador_obstaculo)
        self.id_robot_obstaculo: int = int(id_robot_obstaculo)
        # La petición de siempre, con el marcador del obstáculo AL FINAL: las
        # filas 0..N-1 siguen siendo las de los agentes, en el mismo orden.
        self._peticion = codificar_peticion_poses(
            self._marcadores + [self.id_marcador_obstaculo])

        self._obst_pose: Optional[np.ndarray] = None
        self._obst_instante: Optional[float] = None
        self._obst_tick: int = -1
        self._obst_fila_previa: Optional[np.ndarray] = None
        self._obst_historial: Deque[Tuple[float, float, float]] = deque(
            maxlen=64)
        #: Repeticiones CONSECUTIVAS de la fila completa (7 valores, bit a
        #: bit) del obstáculo. Con ruido de captura real nunca repite.
        self.repeticiones_obstaculo: int = 0
        self.max_repeticiones_obstaculo: int = 0
        self.filas_obstaculo_validas: int = 0
        self.rechazos_obstaculo: Dict[str, int] = {}

    # ── consulta ─────────────────────────────────────────────────────────
    def _consultar(self) -> Optional[np.ndarray]:
        """Una consulta con N + 1 filas; devuelve las N de los agentes."""
        m = self._un_viaje(self._peticion, self._n + 1)
        if m is None:
            return None
        self._procesar_fila_obstaculo(m[self._n])
        return m[: self._n]

    def _procesar_fila_obstaculo(self, fila: np.ndarray) -> None:
        """Valida y guarda la fila del obstáculo (cerrojo ya tomado)."""
        ok, motivo = pose_es_valida(fila)
        if not ok:
            clave = motivo.split("=")[0].split(" ")[0]
            self.rechazos_obstaculo[clave] = (
                self.rechazos_obstaculo.get(clave, 0) + 1)
            return
        if (self._obst_fila_previa is not None
                and np.array_equal(fila, self._obst_fila_previa)):
            self.repeticiones_obstaculo += 1
            self.max_repeticiones_obstaculo = max(
                self.max_repeticiones_obstaculo, self.repeticiones_obstaculo)
        else:
            self.repeticiones_obstaculo = 0
        self._obst_fila_previa = np.array(fila, dtype=np.float64, copy=True)
        yaw, _ = heading_desde_cuaternion(
            float(fila[3]), float(fila[4]), float(fila[5]), float(fila[6]))
        pose = lab_a_env(float(fila[0]), float(fila[1]), yaw,
                         cfg.offset_rumbo_de_robot(self.id_robot_obstaculo))
        ahora = time.perf_counter()
        self._obst_pose = pose
        self._obst_instante = ahora
        self._obst_tick = int(self._obtener_tick())
        self._obst_historial.append((ahora, float(pose[0]), float(pose[1])))
        self.filas_obstaculo_validas += 1

    # ── lectura del obstáculo ────────────────────────────────────────────
    def pose_obstaculo(self) -> Optional[np.ndarray]:
        """Última pose válida del obstáculo [x, y, θ] en el env, o None."""
        with self._cerrojo:
            return None if self._obst_pose is None else self._obst_pose.copy()

    def antiguedad_obstaculo_s(self) -> float:
        """Segundos desde la última fila válida del obstáculo (inf si nunca)."""
        with self._cerrojo:
            if self._obst_instante is None:
                return float("inf")
            return time.perf_counter() - self._obst_instante

    def velocidad_obstaculo(self) -> Optional[np.ndarray]:
        """
        Velocidad MEDIDA del obstáculo en el env (m/s), por diferencia sobre
        la muestra más cercana a `VENTANA_VELOCIDAD_S` atrás. Cero si cae en
        la zona muerta (la medición dice "quieto").

        `None` = SIN ESTIMACIÓN: menos de dos muestras, o ninguna en la
        ventana (un hipo del lazo más largo que la ventana). Hasta el
        2026-10-02 devolvía cero también acá, y la verificación de obediencia
        leía "no sé" como "quieto". Quien la usa decide: la barrera toma
        v̂ = 0 (le queda v_cmd, que anticipa: lo mismo que antes); la
        obediencia no juzga.
        """
        with self._cerrojo:
            hist = list(self._obst_historial)
        if len(hist) < 2:
            return None
        t1, x1, y1 = hist[-1]
        candidatas = [(t0, x0, y0) for t0, x0, y0 in hist[:-1]
                      if 0.05 <= t1 - t0 <= VENTANA_VELOCIDAD_S + 0.05]
        if not candidatas:
            return None
        t0, x0, y0 = min(candidatas,
                         key=lambda m: abs((t1 - m[0]) - VENTANA_VELOCIDAD_S))
        dt = t1 - t0
        v = np.array([(x1 - x0) / dt, (y1 - y0) / dt])
        if float(np.linalg.norm(v)) < ZONA_MUERTA_VELOCIDAD_M_S:
            return np.zeros(2)
        return v

    def olvidar_fila_obstaculo(self) -> None:
        """
        Olvida la fila previa del obstáculo (la base de "fila repetida"):
        la colocación automática empieza su propia cuenta (revisión: una
        fila del latido pegada a la primera consulta no es congelamiento).
        """
        with self._cerrojo:
            self._obst_fila_previa = None
            self.repeticiones_obstaculo = 0

    def reiniciar(self) -> None:
        """Lo de siempre, y además olvida el obstáculo: la toma arranca fresca."""
        with self._cerrojo:
            super().reiniciar()
            self._obst_pose = None
            self._obst_instante = None
            self._obst_tick = -1
            self._obst_fila_previa = None
            self._obst_historial.clear()
            self.repeticiones_obstaculo = 0

    def resumen(self) -> List[str]:
        return super().resumen() + [
            f"[poses] obstáculo (marcador {self.id_marcador_obstaculo}): "
            f"filas válidas {self.filas_obstaculo_validas}  rechazos "
            f"{self.rechazos_obstaculo or '—'}  repeticiones máx "
            f"{self.max_repeticiones_obstaculo}",
        ]


# =============================================================================
# CANAL: EL OBSTÁCULO POR SU PROPIO SOCKET
# =============================================================================

class CanalConObstaculo(CanalActuacionRobotat):
    """
    `CanalActuacionRobotat` con un socket aparte para el robot obstáculo.

    No es un agente más: no cuenta decisiones, no lleva rampa ni
    `factor_operativo` (su velocidad la fija el supervisor), no entra en
    `enlaces_caidos` ni en `ultimo_pico_rpm`. `detener_todo` —que llaman el
    final de cada episodio, el latido de las pausas, el `atexit` y el
    `finally`— lo frena PRIMERO.

    `conectar_obstaculo=False` es la L1: el robot está apagado y no hay a
    quién mandarle nada; frenarlo es trivialmente cierto.
    """

    nombre: str = "robotat_obstaculo"

    def __init__(
        self,
        n_agentes:          int,
        fuente:             Optional[FuentePosesRobotat] = None,
        id_robot_obstaculo: int = ID_ROBOT_OBSTACULO,
        conectar_obstaculo: bool = True,
    ) -> None:
        super().__init__(n_agentes, fuente)
        if int(id_robot_obstaculo) in self._robots:
            raise ValueError(
                f"el robot obstáculo ({id_robot_obstaculo}) ya es un agente: "
                f"{self._robots}")
        self.id_robot_obstaculo: int = int(id_robot_obstaculo)
        self.con_obstaculo: bool = bool(conectar_obstaculo)
        self._sock_obst: Optional[socket.socket] = None
        self._obst_ultimo_intento: float = 0.0
        self.obstaculo_envios_fallidos: int = 0
        self.obstaculo_reconexiones: int = 0
        #: (v, ω) de la última orden al obstáculo: la `v_cmd` de la barrera.
        self.ultimo_mando_obstaculo: Tuple[float, float] = (0.0, 0.0)
        self.historial_mandos_obstaculo: Deque[Tuple[float, float, float]] = (
            deque(maxlen=2048))
        self.obstaculo_detencion_fallida: bool = False
        self._obst_cerrado_a_proposito: bool = False

    # ── conexión ─────────────────────────────────────────────────────────
    def conectar(self) -> None:
        """Los N agentes (como siempre) y después el obstáculo."""
        super().conectar()
        if not self.con_obstaculo:
            return
        host, puerto = cfg.endpoint_robot(self.id_robot_obstaculo)
        try:
            s = socket.create_connection((host, puerto),
                                         timeout=cfg.TIMEOUT_CONEXION_S)
        except OSError as exc:
            for s_ in self._socks.values():
                try:
                    s_.close()
                except OSError:
                    pass
            self._socks.clear()
            raise RobotsInalcanzables([
                f"OBSTÁCULO → robot {self.id_robot_obstaculo} @ {host}:"
                f"{puerto}: {_clase_fallo_conexion(exc)}"]) from None
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock_obst = s
        print(f"[ruedas] OBSTÁCULO → robot {self.id_robot_obstaculo} @ "
              f"{host}:{puerto}")

    def _reconectar_obstaculo(self, forzar: bool = False) -> bool:
        """
        Reabre el enlace del obstáculo, espaciado como el de los agentes, y
        le manda (0, 0) EN EL ACTO: el robot que cerró el socket pero siguió
        escuchando (el robot 3 del 11-09) conserva su última orden, y reabrir
        sin frenarlo lo dejaba andando (revisión de la Fase 0). Nunca reabre
        un canal cerrado a propósito. Con el cerrojo de envío tomado.
        """
        if self._obst_cerrado_a_proposito:
            return False
        ahora = time.perf_counter()
        if not forzar and ahora - self._obst_ultimo_intento < RECONEXION_INTERVALO_S:
            return False
        self._obst_ultimo_intento = ahora
        host, puerto = cfg.endpoint_robot(self.id_robot_obstaculo)
        try:
            s = socket.create_connection((host, puerto),
                                         timeout=RECONEXION_TIMEOUT_S)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.sendall(codificar_velocidades_rueda(0.0, 0.0))
        except OSError:
            return False
        self._sock_obst = s
        self.obstaculo_reconexiones += 1
        print(f"[ruedas] OBSTÁCULO (robot {self.id_robot_obstaculo}) "
              f"RECONECTADO y frenado (n.º {self.obstaculo_reconexiones})")
        return True

    def _enviar_obstaculo_rpm(self, rpm_izq: float, rpm_der: float) -> bool:
        """
        Un comando de rueda al obstáculo. False si el enlace falló.

        NO reabre el enlace: una caída del obstáculo a mitad de toma ABORTA
        la toma (el supervisor lo ve en `obstaculo_caido`), y reabrir en
        línea bloquearía el lazo hasta `RECONEXION_TIMEOUT_S` —el mismo
        hallazgo del 2026-09-24 con los agentes, que acá además dejaba la
        pose de los cinco vencida y escondía el motivo real—. Se reabre
        ENTRE tomas, con `reintentar_enlace_obstaculo`.
        """
        if not self.con_obstaculo:
            return True
        with self._cerrojo_envio:
            s = self._sock_obst
            if s is None:
                return False
            try:
                s.sendall(codificar_velocidades_rueda(rpm_izq, rpm_der))
                return True
            except OSError as exc:
                self.obstaculo_envios_fallidos += 1
                if self.obstaculo_envios_fallidos <= 3:
                    print(f"[ruedas] fallo enviando al OBSTÁCULO (robot "
                          f"{self.id_robot_obstaculo}): {exc}")
                try:
                    s.close()
                except OSError:
                    pass
                self._sock_obst = None
                return False

    def reintentar_enlace_obstaculo(self) -> bool:
        """Entre tomas: reabre el enlace del obstáculo si está caído."""
        if not self.obstaculo_caido:
            return True
        with self._cerrojo_envio:
            return self._reconectar_obstaculo(forzar=True)

    # ── mando ────────────────────────────────────────────────────────────
    def enviar_obstaculo(self, v: float, omega: float) -> bool:
        """(v, ω) TAL CUAL al obstáculo: sin rampa, sin factor, sin contar."""
        rpm_izq, rpm_der, _sat = accion_a_rpm(
            float(v), float(omega), cfg.RADIO_RUEDA_M, cfg.MEDIO_EJE_M)
        self.ultimo_mando_obstaculo = (float(v), float(omega))
        self.historial_mandos_obstaculo.append(
            (time.perf_counter(), float(v), float(omega)))
        return self._enviar_obstaculo_rpm(rpm_izq, rpm_der)

    def detener_obstaculo(self) -> bool:
        """
        Frena al obstáculo, con los mismos reintentos que la detención. Si el
        enlace está caído, intenta REABRIRLO (espaciado por
        `RECONEXION_INTERVALO_S`; la reapertura ya manda (0, 0)), igual que
        `detener_todo` hace con los agentes. La detención no corre por
        decisión, así que el bloqueo de hasta `RECONEXION_TIMEOUT_S` se paga.
        """
        # También al historial: el predictor de F2 integra lo que se le
        # mandó, y un freno que no figure lo dejaría "en marcha".
        if self.con_obstaculo and self.ultimo_mando_obstaculo != (0.0, 0.0):
            self.historial_mandos_obstaculo.append(
                (time.perf_counter(), 0.0, 0.0))
        self.ultimo_mando_obstaculo = (0.0, 0.0)
        if self.con_obstaculo and self._sock_obst is None:
            with self._cerrojo_envio:
                self._reconectar_obstaculo()
        for intento in range(cfg.INTENTOS_DETENCION):
            if self._enviar_obstaculo_rpm(0.0, 0.0):
                return True
            if intento + 1 < cfg.INTENTOS_DETENCION:
                time.sleep(cfg.ESPERA_REINTENTO_DETENCION_S)
        return False

    @property
    def obstaculo_caido(self) -> bool:
        """True si el enlace del obstáculo está caído y no se reabrió."""
        return self.con_obstaculo and self._sock_obst is None

    # ── detención y cierre ───────────────────────────────────────────────
    def detener_todo(self, silencioso: bool = False) -> None:
        """Frena PRIMERO al obstáculo y después a los N agentes."""
        if self._cerrado_ordenadamente:
            return
        ok = self.detener_obstaculo()
        cambio = (not ok) != self.obstaculo_detencion_fallida
        self.obstaculo_detencion_fallida = not ok
        if not ok and (not silencioso or cambio):
            host, puerto = cfg.endpoint_robot(self.id_robot_obstaculo)
            print("=" * 68)
            print(f"⚠ NO SE PUDO CONFIRMAR LA DETENCIÓN DEL OBSTÁCULO: robot "
                  f"{self.id_robot_obstaculo} @ {host}:{puerto}")
            print("  MANTIENE SU ÚLTIMA ORDEN. LEVANTARLO / CORTAR "
                  "ALIMENTACIÓN A MANO.")
            print("=" * 68)
        super().detener_todo(silencioso=silencioso)

    def cerrar(self) -> None:
        """Detiene todo, cierra los N sockets y el del obstáculo."""
        ok = self.detener_obstaculo()
        super().cerrar()
        with self._cerrojo_envio:
            self._obst_cerrado_a_proposito = True
            if self._sock_obst is not None:
                try:
                    self._sock_obst.close()
                except OSError:
                    pass
                self._sock_obst = None
        if not ok or self.obstaculo_detencion_fallida:
            self._cerrado_ordenadamente = False

    def tiene_sockets_abiertos(self) -> bool:
        return super().tiene_sockets_abiertos() or self._sock_obst is not None

    def resumen(self) -> List[str]:
        return super().resumen() + [
            f"[ruedas] obstáculo (robot {self.id_robot_obstaculo}): "
            f"{'conectado' if self.con_obstaculo else 'sin enlace (L1)'}  "
            f"envíos fallidos {self.obstaculo_envios_fallidos}  "
            f"reconexiones {self.obstaculo_reconexiones}",
        ]


def construir_con_obstaculo(
    n_agentes:          int,
    conectar_obstaculo: bool = True,
    id_robot_obstaculo: int = ID_ROBOT_OBSTACULO,
    id_marcador_obstaculo: int = ID_MARCADOR_OBSTACULO,
    timestep_ms:        int = 10,
) -> Tuple[FuentePosesConObstaculo, CanalConObstaculo, EntornoEjecucionRobotat]:
    """
    `lanzar_robotat.construir` con las dos subclases. Poses primero: si la
    mocap no responde, no se abre ningún socket hacia un robot.
    """
    fuente = FuentePosesConObstaculo(
        n_agentes, id_marcador_obstaculo=id_marcador_obstaculo,
        id_robot_obstaculo=id_robot_obstaculo)
    fuente.conectar()
    canal = CanalConObstaculo(n_agentes, fuente,
                              id_robot_obstaculo=id_robot_obstaculo,
                              conectar_obstaculo=conectar_obstaculo)
    try:
        canal.conectar()
    except OSError:
        fuente.cerrar()
        raise
    entorno = EntornoEjecucionRobotat(fuente, canal, timestep_ms)
    return fuente, canal, entorno


# =============================================================================
# TRAYECTORIA Y SUPERVISOR DEL OBSTÁCULO
# =============================================================================

@dataclass
class ParametrosTrayectoria:
    """Círculo antihorario que sigue el obstáculo en la L2."""
    centro:      Tuple[float, float] = CENTRO_CIRCULO_ENV
    radio:       float = RADIO_CIRCULO_M
    v_crucero:   float = V_CRUCERO_M_S
    v_patada:    float = V_PATADA_M_S
    t_patada_max_s: float = T_PATADA_MAX_S
    omega_max:   float = OMEGA_MAX_OBSTACULO
    k_radial:    float = GANANCIA_RADIAL
    k_rumbo:     float = GANANCIA_RUMBO


def punto_del_circulo(fase_rad: float,
                      par: Optional[ParametrosTrayectoria] = None
                      ) -> Tuple[np.ndarray, float]:
    """Punto del círculo en la fase dada y el rumbo tangente antihorario."""
    par = par or ParametrosTrayectoria()
    cx, cy = par.centro
    p = np.array([cx + par.radio * math.cos(fase_rad),
                  cy + par.radio * math.sin(fase_rad)])
    return p, _envolver(fase_rad + math.pi / 2.0)


def ley_seguimiento_circulo(
    pose: np.ndarray, par: ParametrosTrayectoria, v_ref: float,
) -> Tuple[float, float, float]:
    """
    Seguimiento de un círculo antihorario: rumbo deseado = tangente + una
    corrección atan(k·e) hacia adentro si está afuera (e > 0) y viceversa.

        ω = v/R + k_rumbo·(ψ_d − θ),   |ω| ≤ omega_max
        v = v_ref·max(0, cos(ψ_d − θ))   (frena si está mal orientado)

    Retorna (v, ω, error_radial).
    """
    x, y, th = float(pose[0]), float(pose[1]), float(pose[2])
    dx, dy = x - par.centro[0], y - par.centro[1]
    rho = math.hypot(dx, dy)
    fase = math.atan2(dy, dx)
    error_radial = rho - par.radio
    psi_d = fase + math.pi / 2.0 + math.atan(par.k_radial * error_radial)
    err = _envolver(psi_d - th)
    omega = v_ref / par.radio + par.k_rumbo * err
    omega = max(-par.omega_max, min(par.omega_max, omega))
    v = v_ref * max(0.0, math.cos(err))
    return v, omega, error_radial


class SupervisorObstaculo:
    """
    Decide, una vez por decisión, qué hace el obstáculo: quieto durante la
    rampa de arranque seguro, patada, crucero por el círculo, freno de
    respaldo o aborto. Lo llama `CoordinadorConObstaculo` antes de filtrar
    las acciones de los agentes, para que la `v_cmd` de la barrera sea la de
    esta misma decisión.

    Parámetros
    ----------
    modo : "movil" (L2) o "quieto" (L1: robot apagado, no se le manda nada;
           igual se vigila su marcador).
    freno_activo : False = SOMBRA, se cuenta cuándo habría frenado pero no
           frena (campaña de seguridad de la Fase 0).
    vigilar_congelamiento : None = encendido contra hardware y apagado en el
           simulador (que es ideal: un obstáculo quieto repite bit a bit),
           igual que `DetectorCongelamiento`.
    quieto_conectado : sólo con `modo="quieto"`. La L1 con colocación
           automática (opción (b) de José, 2026-10-07): el obstáculo está
           ENCENDIDO y conectado. Se le manda (0, 0) en cada decisión, que
           mantiene vivo su enlace, y se lo vigila: enlace caído y "NO FRENA"
           (la obediencia de siempre con orden de parada) abortan la toma.
           Con False —el default— la L1 es la de siempre, con el robot
           apagado.
    """

    def __init__(
        self,
        fuente:   FuentePosesConObstaculo,
        canal:    CanalConObstaculo,
        modo:     str = "movil",
        parametros: Optional[ParametrosTrayectoria] = None,
        freno_activo: bool = True,
        vigilar_congelamiento: Optional[bool] = None,
        error_radial_max_m: float = ERROR_RADIAL_MAX_M,
        freno_frente_m: float = FRENO_DIST_FRENTE_M,
        freno_retroceso_m: float = FRENO_DIST_RETROCESO_M,
        reanuda_frente_m: float = REANUDA_DIST_FRENTE_M,
        reanuda_retroceso_m: float = REANUDA_DIST_RETROCESO_M,
        quieto_conectado: bool = False,
    ) -> None:
        if modo not in ("movil", "quieto"):
            raise ValueError(f"modo {modo!r}: 'movil' o 'quieto'")
        if quieto_conectado and modo != "quieto":
            raise ValueError("quieto_conectado sólo con modo='quieto'")
        self.quieto_conectado = bool(quieto_conectado)
        self._fuente = fuente
        self._canal = canal
        self.modo = modo
        self.par = parametros or ParametrosTrayectoria()
        self.freno_activo = bool(freno_activo)
        self.vigilar_congelamiento = (
            (not cfg.SIMULADOR_ACTIVO) if vigilar_congelamiento is None
            else bool(vigilar_congelamiento))
        self.error_radial_max_m = float(error_radial_max_m)
        self.freno_frente_m = float(freno_frente_m)
        self.freno_retroceso_m = float(freno_retroceso_m)
        self.reanuda_frente_m = float(reanuda_frente_m)
        self.reanuda_retroceso_m = float(reanuda_retroceso_m)
        self.reiniciar_toma()

    @property
    def movil(self) -> bool:
        return self.modo == "movil"

    def reiniciar_toma(self) -> None:
        """Estado limpio al empezar una toma."""
        self.estado: str = "espera"
        self.motivo_aborto: Optional[str] = None
        self._t_inicio_marcha: Optional[float] = None
        self._en_patada: bool = False
        self._en_freno: bool = False
        self.eventos_freno: List[Dict[str, Any]] = []
        self.decisiones_freno: int = 0
        self.decisiones_patada: int = 0
        self.decisiones_marcha: int = 0
        self.error_radial_max_obs: float = 0.0
        self.ultimo_mando: Optional[Tuple[float, float]] = None
        self.traza: List[Dict[str, Any]] = []
        self._clase_mando: Optional[str] = None
        self._t_cambio_mando: float = time.perf_counter()
        self._ahora_paso: float = time.perf_counter()
        self._decisiones_desobediencia: int = 0
        self.decisiones_sin_estimacion: int = 0

    # ── abortos ──────────────────────────────────────────────────────────
    def _abortar(self, motivo: str, paso: int) -> None:
        if self.estado != "abortado":
            print(f"  ⛔ OBSTÁCULO: {motivo} (decisión {paso}) — se frena y "
                  f"se aborta la toma")
        self.estado = "abortado"
        self.motivo_aborto = motivo
        if self.movil or self.quieto_conectado:
            self._canal.detener_obstaculo()

    def _chequear(self, pose: Optional[np.ndarray]) -> Optional[str]:
        """Motivo de aborto del obstáculo, o None si está todo en orden."""
        if pose is None:
            return "sin pose válida del obstáculo"
        edad = self._fuente.antiguedad_obstaculo_s()
        if edad > cfg.ANTIGUEDAD_MAX_POSE_S:
            return (f"pose del obstáculo vencida ({edad * 1000:.0f} ms > "
                    f"{cfg.ANTIGUEDAD_MAX_POSE_S * 1000:.0f} ms)")
        if (self.vigilar_congelamiento
                and self._fuente.repeticiones_obstaculo >= 1):
            return (f"marcador del obstáculo CONGELADO (fila repetida bit a "
                    f"bit) en ({pose[0]:.2f}, {pose[1]:.2f}): el CBF estaría "
                    f"esquivando una pose fantasma")
        if ((self.movil or self.quieto_conectado)
                and self._canal.obstaculo_caido):
            return (f"enlace de ruedas del obstáculo (robot "
                    f"{self._canal.id_robot_obstaculo}) caído")
        x, y = float(pose[0]), float(pose[1])
        if not (0.0 <= x <= ARENA_SIZE[0] and 0.0 <= y <= ARENA_SIZE[1]):
            return f"obstáculo fuera de la arena ({x:.2f}, {y:.2f})"
        return None

    # ── freno de respaldo ────────────────────────────────────────────────
    def _condicion_freno(
        self, pose: np.ndarray, poses_agentes: Dict[int, np.ndarray],
        en_retroceso: Set[int], d_frente: float, d_retroceso: float,
    ) -> Optional[Dict[str, Any]]:
        """Detalle de la primera condición de freno que se cumple, o None."""
        p_o = np.asarray(pose[:2], dtype=np.float64)
        rumbo = np.array([math.cos(float(pose[2])), math.sin(float(pose[2]))])
        for i in sorted(poses_agentes):
            d_vec = np.asarray(poses_agentes[i][:2], dtype=np.float64) - p_o
            d = float(np.linalg.norm(d_vec))
            if d < d_frente and float(d_vec @ rumbo) > 0.0:
                return {"agente": int(i), "dist_m": d, "causa": "frente"}
            if i in en_retroceso and d < d_retroceso:
                return {"agente": int(i), "dist_m": d, "causa": "retroceso"}
        return None

    # ── decisión ─────────────────────────────────────────────────────────
    def paso(
        self,
        poses_agentes:   Dict[int, np.ndarray],
        en_retroceso:    Set[int],
        factor_arranque: float,
        ahora:           float,
        paso:            int,
    ) -> Optional[Tuple[float, float]]:
        """
        Una decisión del obstáculo. Devuelve el mando ENVIADO (v, ω), o None
        si al obstáculo no se le manda nada (modo quieto: robot apagado).
        """
        self._ahora_paso = float(ahora)
        pose = self._fuente.pose_obstaculo()
        if self.estado == "abortado":
            mando = self._mandar(0.0, 0.0)
            self._anotar(paso, ahora, pose, mando, None, poses_agentes)
            return mando
        motivo = self._chequear(pose)
        if motivo is None and (self.movil or self.quieto_conectado):
            motivo = self._verificar_obediencia(ahora)
        if motivo is not None:
            self._abortar(motivo, paso)
            mando = ((0.0, 0.0) if (self.movil or self.quieto_conectado)
                     else None)
            self.ultimo_mando = mando
            self._anotar(paso, ahora, pose, mando, None, poses_agentes)
            return mando
        if not self.movil:
            self.estado = "quieto"
            mando = self._mandar(0.0, 0.0) if self.quieto_conectado else None
            self.ultimo_mando = mando
            self._anotar(paso, ahora, pose, mando, None, poses_agentes)
            return mando

        # ── freno de respaldo (con histéresis) ───────────────────────────
        if not self._en_freno:
            det = self._condicion_freno(pose, poses_agentes, en_retroceso,
                                        self.freno_frente_m,
                                        self.freno_retroceso_m)
            if det is not None:
                self._en_freno = True
                det.update({"paso": int(paso),
                            "activo": int(self.freno_activo)})
                self.eventos_freno.append(det)
                print(f"  ✋ OBSTÁCULO: freno de respaldo "
                      f"{'' if self.freno_activo else '(SOMBRA, no frena) '}"
                      f"— agente {det['agente']} a {det['dist_m']:.3f} m "
                      f"({det['causa']}), decisión {paso}")
        elif self._condicion_freno(pose, poses_agentes, en_retroceso,
                                   self.reanuda_frente_m,
                                   self.reanuda_retroceso_m) is None:
            self._en_freno = False
            if self.freno_activo:
                self._t_inicio_marcha = None    # vuelve a arrancar con patada
        if self._en_freno:
            self.decisiones_freno += 1
        if self._en_freno and self.freno_activo:
            self.estado = "freno"
            mando = self._mandar(0.0, 0.0)
            self._anotar(paso, ahora, pose, mando, None, poses_agentes)
            return mando

        # ── quieto mientras dure la rampa de arranque seguro ─────────────
        # Con k = 0.10, s/k superaría V_MAX: el obstáculo no se mueve hasta
        # que los agentes tienen su velocidad de régimen.
        if factor_arranque < 1.0 - 1e-12:
            self.estado = "espera"
            self._t_inicio_marcha = None
            mando = self._mandar(0.0, 0.0)
            self._anotar(paso, ahora, pose, mando, None, poses_agentes)
            return mando

        if self._t_inicio_marcha is None:
            self._t_inicio_marcha = ahora
            self._en_patada = True
        if self._en_patada:
            v_med = self._fuente.velocidad_obstaculo()
            rapidez = float(np.linalg.norm(v_med)) if v_med is not None else 0.0
            if (ahora - self._t_inicio_marcha >= self.par.t_patada_max_s
                    or rapidez >= V_MOVIMIENTO_DETECTADO_M_S):
                self._en_patada = False
        v_ref = self.par.v_patada if self._en_patada else self.par.v_crucero
        v, omega, e_rad = ley_seguimiento_circulo(pose, self.par, v_ref)
        self.error_radial_max_obs = max(self.error_radial_max_obs, abs(e_rad))
        if abs(e_rad) > self.error_radial_max_m:
            self._abortar(f"el obstáculo se salió de su círculo (error radial "
                          f"{e_rad:+.3f} m > ±{self.error_radial_max_m:.2f})",
                          paso)
            mando = (0.0, 0.0)
            self.ultimo_mando = mando
            self._anotar(paso, ahora, pose, mando, e_rad, poses_agentes)
            return mando
        if self._en_patada:
            self.estado = "patada"
            self.decisiones_patada += 1
        else:
            self.estado = "marcha"
            self.decisiones_marcha += 1
        mando = self._mandar(v, omega)
        self._anotar(paso, ahora, pose, mando, e_rad, poses_agentes)
        return mando

    def _verificar_obediencia(self, ahora: float) -> Optional[str]:
        """
        ¿El obstáculo hace lo que se le manda? Compara la clase de la orden
        vigente (marcha / parado), sostenida `T_VERIFICACION_OBEDIENCIA_S`,
        con la velocidad MEDIDA. Sin esto, un robot con la rueda trabada (o
        un enlace que acepta bytes pero no llega) daba una toma "VÁLIDA" con
        el obstáculo inmóvil, y uno que no frena pasaba sin alarma.
        """
        if self._clase_mando is None:
            return None
        v = self._fuente.velocidad_obstaculo()
        if v is None:
            # Sin estimación no se juzga, y la cuenta vuelve a cero.
            self.decisiones_sin_estimacion += 1
            self._decisiones_desobediencia = 0
            return None
        rapidez = float(np.linalg.norm(v))
        desobedece = ((self._clase_mando == "marcha"
                       and rapidez < V_SIN_MOVIMIENTO_M_S)
                      or (self._clase_mando == "parado"
                          and rapidez > V_NO_FRENA_M_S))
        self._decisiones_desobediencia = (
            self._decisiones_desobediencia + 1 if desobedece else 0)
        if (ahora - self._t_cambio_mando < T_VERIFICACION_OBEDIENCIA_S
                or self._decisiones_desobediencia < N_CONFIRMACION_OBEDIENCIA):
            return None
        if self._clase_mando == "marcha":
            return (f"el obstáculo NO SE MUEVE: {ahora - self._t_cambio_mando:.1f}"
                    f" s con orden de marcha y v medida {rapidez:.3f} m/s en "
                    f"{self._decisiones_desobediencia} decisiones seguidas "
                    f"(¿rueda trabada, batería, enlace?)")
        print("=" * 68)
        print("⚠ EL OBSTÁCULO NO FRENA: LEVANTARLO / CORTAR ALIMENTACIÓN.")
        print("=" * 68)
        return (f"el obstáculo NO FRENA: {ahora - self._t_cambio_mando:.1f}"
                f" s con orden de parada y v medida {rapidez:.3f} m/s en "
                f"{self._decisiones_desobediencia} decisiones seguidas")

    def _mandar(self, v: float, omega: float) -> Optional[Tuple[float, float]]:
        if not self.movil and not self.quieto_conectado:
            self.ultimo_mando = None
            return None
        self._canal.enviar_obstaculo(v, omega)
        self.ultimo_mando = (float(v), float(omega))
        clase = "marcha" if abs(float(v)) >= V_ORDEN_MARCHA_M_S else "parado"
        if clase != self._clase_mando:
            self._clase_mando = clase
            # El reloj de la DECISIÓN, el mismo que usa `_verificar_obediencia`.
            self._t_cambio_mando = self._ahora_paso
        return self.ultimo_mando

    def recorrido(self) -> Tuple[float, float]:
        """(recorrido medido, recorrido comandado) del obstáculo en la toma, m."""
        medido, comandado = 0.0, 0.0
        previa: Optional[Tuple[float, float]] = None
        for f in self.traza:
            if f["x"] != "" and f["y"] != "":
                p = (float(f["x"]), float(f["y"]))
                if previa is not None:
                    medido += math.hypot(p[0] - previa[0], p[1] - previa[1])
                previa = p
            if f["v_cmd"] != "":
                comandado += abs(float(f["v_cmd"])) * 0.1
        return medido, comandado

    def _anotar(self, paso: int, ahora: float, pose: Optional[np.ndarray],
                mando: Optional[Tuple[float, float]],
                e_rad: Optional[float],
                poses_agentes: Dict[int, np.ndarray]) -> None:
        """Una fila de traza por decisión (va al CSV del obstáculo)."""
        d_min, quien = float("inf"), -1
        if pose is not None:
            for i, p in poses_agentes.items():
                d = float(np.linalg.norm(np.asarray(p[:2]) - pose[:2]))
                if d < d_min:
                    d_min, quien = d, int(i)
        vh = self._fuente.velocidad_obstaculo()
        if vh is None:
            vh = np.array([float("nan"), float("nan")])
        self.traza.append({
            "paso": int(paso), "t": ahora, "estado": self.estado,
            "x": float(pose[0]) if pose is not None else "",
            "y": float(pose[1]) if pose is not None else "",
            "th": float(pose[2]) if pose is not None else "",
            "v_cmd": mando[0] if mando else "",
            "w_cmd": mando[1] if mando else "",
            "v_hat_x": float(vh[0]) if math.isfinite(vh[0]) else "",
            "v_hat_y": float(vh[1]) if math.isfinite(vh[1]) else "",
            "error_radial": e_rad if e_rad is not None else "",
            "en_freno": int(self._en_freno),
            "d_min_agente_medida": d_min if quien >= 0 else "",
            "agente_mas_cercano": quien,
        })

    def resumen(self) -> Dict[str, Any]:
        """Lo que va a la fila de la toma."""
        return {
            "obst_modo": self.modo,
            "obst_freno_activo": int(self.freno_activo),
            "frenos": len(self.eventos_freno),
            "frenos_detalle": ";".join(
                f"a{e['agente']}@{e['paso']}:{e['dist_m']:.3f}:{e['causa']}"
                for e in self.eventos_freno),
            "decisiones_freno": self.decisiones_freno,
            "obst_recorrido_m": self.recorrido()[0],
            "obst_recorrido_comandado_m": self.recorrido()[1],
            "decisiones_patada": self.decisiones_patada,
            "decisiones_marcha": self.decisiones_marcha,
            "obst_error_radial_max": self.error_radial_max_obs,
            "obst_decisiones_sin_estimacion_v": self.decisiones_sin_estimacion,
            "obst_motivo_aborto": self.motivo_aborto or "",
        }


# =============================================================================
# COORDINADOR: UNA FILA MÁS EN EL QP Y UNA NORMAL MÁS EN EL ESCAPE
# =============================================================================

@dataclass
class InstantaneaObstaculo:
    """Lo que la barrera sabe del obstáculo en ESTA decisión."""
    p:     np.ndarray            # centro (2,)
    theta: float
    v_hat: np.ndarray            # velocidad medida (2,)
    v_cmd: np.ndarray            # velocidad comandada en esta decisión (2,)
    k:     float                 # factor_total() con que se ejecuta
    t:     float = 0.0           # instante de la decisión (perf_counter)
    # ── F2: el obstáculo en t + τ_c ──
    p_pred:     Optional[np.ndarray] = None
    v_cmd_pred: Optional[np.ndarray] = None


class _ModeloConNominalForzada:
    """
    SÓLO PARA LAS PRUEBAS DE PEOR CASO: envuelve a la política y reemplaza su
    acción por la de una función guionada (p. ej. "andá derecho al obstáculo
    a V_MAX"). `_decidir_y_actuar` llama a `predict` una vez por agente y en
    orden 0..N-1; el índice lo cuenta este envoltorio y lo reinicia el
    coordinador al empezar cada decisión. La acción forzada entra por el
    MISMO camino que la de la política: escape, filtro, canal.
    """

    def __init__(self, modelo: Any, coordinador: "CoordinadorConObstaculo",
                 funcion: Callable[[int, np.ndarray, Optional[np.ndarray]],
                                   Optional[np.ndarray]]) -> None:
        self._modelo = modelo
        self._coord = coordinador
        self._funcion = funcion
        self.indice = 0

    def predict(self, observacion: Any, deterministic: bool = True):
        i = self.indice
        self.indice += 1
        accion, estado = self._modelo.predict(observacion,
                                              deterministic=deterministic)
        cache = self._coord._cache.get(i)
        pose_i = cache.como_array() if cache is not None else None
        forzada = (self._funcion(i, pose_i, self._coord.fuente.pose_obstaculo())
                   if pose_i is not None else None)
        if forzada is None:
            return accion, estado
        return np.asarray(forzada, dtype=np.float32), estado


class CoordinadorConObstaculo(CoordinadorEnjambre):
    """
    El coordinador de siempre, con el obstáculo:

    · antes de cada decisión, el supervisor decide y manda la orden del
      obstáculo, y se toma una instantánea (pose medida, velocidad medida,
      velocidad comandada, k);
    · `_barreras_robot_robot` agrega la fila del obstáculo (F1 o F0);
    · `_normales_activas` suma la normal del obstáculo al escape;
    · `_avanzar` devuelve False si el supervisor abortó, para que
      `_correr_episodio` corte la toma; el motivo lo repone `correr_toma`.

    Con `supervisor=None` o `formulacion="ninguna"` no agrega nada: es el
    coordinador original (hay prueba de que las barreras y el escape son los
    del original).
    """

    def __init__(
        self,
        fuente:      FuentePosesConObstaculo,
        canal:       CanalConObstaculo,
        entorno:     Any,
        n_agentes:   int,
        timestep_ms: int,
        supervisor:  Optional[SupervisorObstaculo] = None,
        formulacion: str = "F2",
        tau_prediccion_s: float = TAU_PREDICCION_S,
        peso_giro_obstaculo: Optional[float] = PESO_GIRO_OBSTACULO,
        rescate_qp: bool = True,
    ) -> None:
        if formulacion not in FORMULACIONES:
            raise ValueError(f"formulación {formulacion!r}: {FORMULACIONES}")
        super().__init__(fuente=fuente, canal=canal, entorno=entorno,
                         n_agentes=n_agentes, timestep_ms=timestep_ms)
        if self._filtro_cbf is None:
            raise RuntimeError("la demo necesita el filtro CBF encendido")
        self.supervisor = supervisor
        self.formulacion = formulacion
        self.tau_prediccion_s = float(tau_prediccion_s)
        # Peso de giro y rescate: parte de F2. F1 y F0 (propuesta y control
        # negativo) quedan con el filtro de siempre.
        es_f2 = formulacion == "F2"
        self.peso_giro_obstaculo = peso_giro_obstaculo if es_f2 else None
        self.rescate_qp = bool(rescate_qp) and es_f2
        self._filtro_cbf.peso_giro_obstaculo = self.peso_giro_obstaculo
        self._filtro_cbf.rescate_obstaculo = self.rescate_qp
        #: h de la fila en el estado PREDICHO (sólo F2), por agente.
        self.h_pred_obstaculo: Dict[int, float] = {}
        self._obst: Optional[InstantaneaObstaculo] = None
        #: Fila del obstáculo usada en ESTA decisión, por agente.
        self.filas_obstaculo: Dict[int, Any] = {}
        #: h geométrico (sin el término de velocidad) por agente, ídem.
        self.h_geom_obstaculo: Dict[int, float] = {}
        self.motivo_aborto_obstaculo: Optional[str] = None
        self._proxy_nominal: Optional[_ModeloConNominalForzada] = None
        self._reiniciar_metricas_obstaculo()

    def _construir_filtro(self) -> None:
        """El filtro de siempre, como `FiltroConObstaculo` (mismos parámetros)."""
        self._filtro_cbf = FiltroConObstaculo(
            arena_size = ARENA_SIZE,
            ele_a      = self._ele_a,
            alfa       = ALFA_CBF,
            d_segura   = self._d_segura,
            w_omega    = self._w_omega,
            v_max      = self._v_max,
            omega_max  = self._omega_max,
        )

    # ── pruebas de peor caso ─────────────────────────────────────────────
    def instalar_nominal_forzada(
        self, funcion: Callable[[int, np.ndarray, Optional[np.ndarray]],
                                Optional[np.ndarray]]) -> None:
        """Reemplaza la acción nominal de los agentes que `funcion` decida."""
        self._proxy_nominal = _ModeloConNominalForzada(self.modelo, self,
                                                       funcion)
        self.modelo = self._proxy_nominal

    # ── métricas ─────────────────────────────────────────────────────────
    def _reiniciar_metricas_obstaculo(self) -> None:
        n = self.n_agentes
        self.d_min_obst_medida: List[float] = [float("inf")] * n
        self.h_geom_min: List[float] = [float("inf")] * n
        self.decisiones_obst_015: int = 0
        self.decisiones_obst_022: int = 0
        self.decisiones_fila_activa: List[int] = [0] * n
        self.decisiones_fila_saturada: List[int] = [0] * n
        self.decisiones_obstaculo: int = 0
        if isinstance(self._filtro_cbf, FiltroConObstaculo):
            self._filtro_cbf.reiniciar_contadores()

    def resumen_obstaculo(self) -> Dict[str, Any]:
        """Métricas del obstáculo de la toma (más las del supervisor)."""
        d = [x for x in self.d_min_obst_medida if math.isfinite(x)]
        res: Dict[str, Any] = {
            "formulacion": self.formulacion,
            "d_min_obst_medida": min(d) if d else "",
            "h_geom_min_obst": (min(x for x in self.h_geom_min
                                    if math.isfinite(x))
                                if any(math.isfinite(x)
                                       for x in self.h_geom_min) else ""),
            "decisiones_obst_015": self.decisiones_obst_015,
            "decisiones_obst_022": self.decisiones_obst_022,
            "decisiones_fila_activa": int(sum(self.decisiones_fila_activa)),
            "decisiones_fila_saturada": int(sum(self.decisiones_fila_saturada)),
            "cbf_fallbacks": int(np.sum(self._cbf_fallbacks)),
            "peso_giro_obstaculo": (self.peso_giro_obstaculo
                                    if self.peso_giro_obstaculo is not None
                                    else ""),
            "decisiones_peso_giro": getattr(self._filtro_cbf,
                                            "decisiones_peso_giro", 0),
            "rescates_qp_n1": getattr(self._filtro_cbf, "rescates",
                                      {}).get("nivel_1", 0),
            "rescates_qp_n2": getattr(self._filtro_cbf, "rescates",
                                      {}).get("nivel_2", 0),
            "rescates_qp_fallidos": getattr(self._filtro_cbf, "rescates",
                                            {}).get("sin_rescate", 0),
            "escapes": int(np.sum(self._esc_n_escapes)),
            "escapes_infactibles": int(np.sum(self._esc_infactibles)),
            "escapes_agotados": int(np.sum(self._esc_agotados)),
        }
        for i in range(self.n_agentes):
            v = self.d_min_obst_medida[i]
            res[f"d_min_obst_a{i}"] = v if math.isfinite(v) else ""
        if self.supervisor is not None:
            res.update(self.supervisor.resumen())
        return res

    # ── la fila del obstáculo ────────────────────────────────────────────
    def _fila_obstaculo(self, i: int, pose_i: np.ndarray) -> Optional[Any]:
        """RestriccionLineal del obstáculo para el agente i, o None."""
        o = self._obst
        if o is None or self.formulacion == "ninguna":
            return None
        filtro = self._filtro_cbf
        p_i = filtro._punto_de_mira(pose_i)
        G_i = filtro._matriz_G(float(pose_i[2]))
        if self.formulacion == "F0":
            # "Un robot más": la barrera robot-robot de siempre, con el punto
            # de mira del obstáculo, 50/50 y vecino supuesto quieto.
            p_o = filtro._punto_de_mira(np.array([o.p[0], o.p[1], o.theta]))
            delta = p_i - p_o
            dist = float(np.linalg.norm(delta))
            if dist < 1e-9:
                return None
            self.h_geom_obstaculo[i] = dist - self._d_robots
            return self._RestriccionLineal(
                c=(delta / dist) @ G_i, h=0.5 * (dist - self._d_robots),
                nombre="robot_obstaculo")
        # ── F1 y F2 ──
        d_actual = float(np.linalg.norm(p_i - o.p))
        self.h_geom_obstaculo[i] = d_actual - D_OBSTACULO_M
        if self.formulacion == "F2":
            # La orden que sale ahora rige en t + τ_c: la fila se evalúa en
            # el estado de ESE instante. Agente: pose medida + sus órdenes en
            # vuelo (lo que RECIBIÓ cada robot, en rpm de rueda, ya con el
            # factor). Obstáculo: ídem con las suyas.
            from retroceso_congelamiento import rpm_a_v_omega
            mandos = [(t, *rpm_a_v_omega(izq, der))
                      for t, izq, der in self.canal.historial_mandos(i)]
            pose_pred = predecir_pose(pose_i, mandos, o.t,
                                      self.tau_prediccion_s)
            p_i = filtro._punto_de_mira(pose_pred)
            G_i = filtro._matriz_G(float(pose_pred[2]))
            p_o = o.p_pred if o.p_pred is not None else o.p
            v_o = o.v_cmd_pred if o.v_cmd_pred is not None else o.v_cmd
        else:
            p_o, v_o = o.p, o.v_cmd
        delta = p_i - p_o
        dist = float(np.linalg.norm(delta))
        if dist < 1e-9:
            return None
        normal = delta / dist
        c = normal @ G_i
        h = dist - D_OBSTACULO_M
        if self.formulacion == "F2":
            self.h_pred_obstaculo[i] = h
        s = max(0.0, float(normal @ o.v_hat), float(normal @ v_o))
        alfa = filtro.alfa
        capacidad = (abs(float(c[0])) * filtro.v_max
                     + abs(float(c[1])) * filtro.omega_max)
        rhs = -alfa * h + s / o.k
        if s == 0.0 and rhs <= FRACCION_CAPACIDAD * capacidad:
            h_eq = h          # obstáculo quieto: la fila del Exp O, tal cual
        else:
            if rhs > FRACCION_CAPACIDAD * capacidad:
                rhs = FRACCION_CAPACIDAD * capacidad
                self.decisiones_fila_saturada[i] += 1
            h_eq = -rhs / alfa
        return self._RestriccionLineal(c=c, h=h_eq, nombre="obstaculo")

    def _barreras_robot_robot(self, i: int, poses: np.ndarray) -> List:
        extras = super()._barreras_robot_robot(i, poses)
        fila = self._fila_obstaculo(i, poses[i])
        if fila is not None:
            extras.append(fila)
            self.filas_obstaculo[i] = fila
            if self.h_geom_obstaculo.get(i, float("inf")) < ESC_UMBRAL_ACTIVA:
                self.decisiones_fila_activa[i] += 1
        return extras

    def _normales_activas(
        self, i: int, poses: np.ndarray,
    ) -> Tuple[Optional[np.ndarray], float]:
        """
        `CoordinadorEnjambre._normales_activas` (coordinador_enjambre.py:
        1122-1178) con UNA candidata más: la normal del obstáculo, desde él
        hacia el agente, con su h geométrico. Sin obstáculo, delega en el
        original (hay prueba de igualdad).
        """
        o = self._obst
        if o is None or self.formulacion == "ninguna":
            return super()._normales_activas(i, poses)
        filtro = self._filtro_cbf
        pose_i = poses[i]
        p_i = filtro._punto_de_mira(pose_i)

        normales: List[np.ndarray] = []
        h_min = float("inf")
        Wx, Wy = ARENA_SIZE
        candidatas = [
            (np.array([1.0, 0.0]),  float(p_i[0]) - self._d_segura),
            (np.array([-1.0, 0.0]), (Wx - float(p_i[0])) - self._d_segura),
            (np.array([0.0, 1.0]),  float(p_i[1]) - self._d_segura),
            (np.array([0.0, -1.0]), (Wy - float(p_i[1])) - self._d_segura),
        ]
        for j in range(self.n_agentes):
            if j == i:
                continue
            p_j = filtro._punto_de_mira(poses[j])
            delta = p_i - p_j
            dist = float(np.linalg.norm(delta))
            if dist < 1e-9:
                continue
            candidatas.append((delta / dist, dist - self._d_robots))
        # ── el obstáculo ──
        if self.formulacion == "F0":
            p_o = filtro._punto_de_mira(np.array([o.p[0], o.p[1], o.theta]))
            margen = self._d_robots
        else:
            p_o = o.p
            margen = D_OBSTACULO_M
        delta = p_i - p_o
        dist = float(np.linalg.norm(delta))
        if dist >= 1e-9:
            candidatas.append((delta / dist, dist - margen))

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

    # ── lazo ─────────────────────────────────────────────────────────────
    def _avanzar(self, n_ticks: int = 1) -> bool:
        if self.motivo_aborto_obstaculo is not None:
            return False
        return super()._avanzar(n_ticks)

    def _reiniciar_episodio(self, semilla: int) -> bool:
        self.motivo_aborto_obstaculo = None
        self._obst = None
        self.filas_obstaculo = {}
        self.h_geom_obstaculo = {}
        if self.supervisor is not None:
            self.supervisor.reiniciar_toma()
        self._reiniciar_metricas_obstaculo()
        return super()._reiniciar_episodio(semilla)

    def _decidir_y_actuar(self) -> bool:
        ahora = time.perf_counter()
        self._obst = None
        self.filas_obstaculo = {}
        self.h_geom_obstaculo = {}
        self.h_pred_obstaculo = {}
        mando: Optional[Tuple[float, float]] = None
        if self.supervisor is not None:
            poses_ag = {i: c.como_array() for i, c in self._cache.items()}
            en_retroceso = set(getattr(self.canal, "mandos_directos", {}))
            mando = self.supervisor.paso(poses_ag, en_retroceso,
                                         self.canal.factor_arranque(), ahora,
                                         self._paso_episodio)
            if self.supervisor.motivo_aborto is not None:
                self.motivo_aborto_obstaculo = self.supervisor.motivo_aborto
            pose_o = self.fuente.pose_obstaculo()
            if pose_o is not None and self.formulacion != "ninguna":
                th = float(pose_o[2])
                v_cmd = (mando[0] if mando is not None else 0.0)
                p_pred = v_pred = None
                if self.formulacion == "F2":
                    pose_o_pred = predecir_pose(
                        pose_o, list(self.canal.historial_mandos_obstaculo),
                        ahora, self.tau_prediccion_s)
                    th_p = float(pose_o_pred[2])
                    p_pred = np.array(pose_o_pred[:2], dtype=np.float64)
                    v_pred = v_cmd * np.array([math.cos(th_p), math.sin(th_p)])
                self._obst = InstantaneaObstaculo(
                    p=np.array([pose_o[0], pose_o[1]], dtype=np.float64),
                    theta=th,
                    v_hat=_velocidad_o_cero(self.fuente.velocidad_obstaculo()),
                    v_cmd=v_cmd * np.array([math.cos(th), math.sin(th)]),
                    k=max(float(self.canal.factor_total()), FACTOR_MINIMO),
                    t=ahora, p_pred=p_pred, v_cmd_pred=v_pred,
                )
        if self._proxy_nominal is not None:
            self._proxy_nominal.indice = 0
        terminado = super()._decidir_y_actuar()
        self._actualizar_metricas_obstaculo()
        return terminado

    def _actualizar_metricas_obstaculo(self) -> None:
        """Distancias REALES (caché real) de cada agente al obstáculo medido."""
        if self._obst is None and self.supervisor is None:
            return
        pose_o = self.fuente.pose_obstaculo()
        if pose_o is None:
            return
        self.decisiones_obstaculo += 1
        bajo_015 = bajo_022 = False
        for i in range(self.n_agentes):
            c = self._cache.get(i)
            if c is None:
                continue
            d = float(np.linalg.norm(c.como_array_real()[:2] - pose_o[:2]))
            self.d_min_obst_medida[i] = min(self.d_min_obst_medida[i], d)
            bajo_015 = bajo_015 or d < 0.15
            bajo_022 = bajo_022 or d < 0.22
            h = self.h_geom_obstaculo.get(i)
            if h is not None:
                self.h_geom_min[i] = min(self.h_geom_min[i], h)
        self.decisiones_obst_015 += int(bajo_015)
        self.decisiones_obst_022 += int(bajo_022)


# =============================================================================
# REGISTRO Y TOMA
# =============================================================================

def crear_observador(coord: CoordinadorConObstaculo, canal: CanalConObstaculo,
                     registro: List[Dict[str, Any]], estado: Dict[str, Any]
                     ) -> Callable[[Dict[str, Any]], None]:
    """
    El observador por agente y decisión de `sesion_evaluacion` (mismas
    columnas: `_correr_episodio` las lee), más las del obstáculo:
    `d_obst_medida` (centro real del agente al centro medido del obstáculo),
    `h_obst_geom`, `h_obst_eq` y `obst_viola_nominal` (la acción tras el
    escape violaba la fila: el filtro intervino POR el obstáculo).
    """
    def observador(d: Dict[str, Any]) -> None:
        ag = int(d["agente"])
        fila = coord.filas_obstaculo.get(ag)
        pose_o = coord.fuente.pose_obstaculo()
        d_obst: Any = ""
        if pose_o is not None and d.get("pose_real") is not None:
            d_obst = float(np.linalg.norm(
                np.asarray(d["pose_real"])[:2] - pose_o[:2]))
        viola = ""
        if fila is not None:
            u = np.asarray(d["accion_tras_escape"], dtype=np.float64)
            u = np.array([np.clip(u[0], -coord._v_max, coord._v_max),
                          np.clip(u[1], -coord._omega_max, coord._omega_max)])
            viola = int(float(fila.c @ u) + coord._filtro_cbf.alfa * fila.h
                        < -1e-9)
        registro.append({
            "episodio":      estado["episodio"],
            "agente":        ag,
            "robot":         cfg.MAPEO_AGENTES[ag].id_robot,
            "paso":          d["paso"],
            "pose_env_x":    float(d["pose_env"][0]),
            "pose_env_y":    float(d["pose_env"][1]),
            "pose_env_th":   float(d["pose_env"][2]),
            "v_ejecutada":   float(d["accion_ejecutada"][0]),
            "w_ejecutada":   float(d["accion_ejecutada"][1]),
            "v_nominal":     float(d["accion_nominal"][0]),
            "w_nominal":     float(d["accion_nominal"][1]),
            "en_escape":     int(d["en_escape"]),
            "cbf_intervino": int(d["cbf_intervino"]),
            "rpm_pico":      canal.ultimo_pico_rpm,
            "con_vecino":    int(any(abs(float(v)) > 1e-9 for v in
                                     np.asarray(d["observacion"])[8:16])),
            "en_retroceso":  int(ag in getattr(canal, "mandos_directos", {})),
            "d_obst_medida": d_obst,
            "h_obst_geom":   coord.h_geom_obstaculo.get(ag, ""),
            "h_obst_eq":     float(fila.h) if fila is not None else "",
            "h_obst_pred":   coord.h_pred_obstaculo.get(ag, ""),
            "obst_viola_nominal": viola,
        })
    return observador


#: Regla de estancamiento de `_correr_episodio` (sesion_robotat.py), replicada
#: FUERA de línea por `primer_corte_por_estancamiento`.
ESTANC_V_MIN: float = 0.02
ESTANC_AVANCE_MIN_M: float = 0.002
ESTANC_T_S: float = 10.0
#: La regla ARREGLADA (2026-10-02, en `sesion_robotat.py`).
ESTANC_MARGEN_S: float = 1.0
ESTANC_CORTE_ORDEN_S: float = 1.0


def primer_corte_por_estancamiento(registro: Sequence[Dict[str, Any]],
                                   marca: int = 0) -> Tuple[Any, Any]:
    """
    ¿En qué decisión habría cortado la toma la regla "sin desplazamiento por
    10 s" del lazo de evaluación, en su versión ARREGLADA del 2026-10-02
    (reloj desde el inicio de la orden sostenida + 1 s)? Devuelve
    (paso, agente) o ("", "").

    ⚠ HALLAZGO de la Fase 0 (2026-10-01): la regla mide el tiempo desde el
    ÚLTIMO desplazamiento > 2 mm, no desde que se le ORDENÓ moverse. Un
    agente quieto y sin filtrar más de 10 s al que de pronto el filtro le pide
    huir del obstáculo dispara el corte en la primera decisión con
    |v| > 0.02, antes de que el retardo de actuación le deje moverse. Se usa
    el tiempo NOMINAL (paso × 0.1 s); el lazo real usa el reloj de pared.
    """
    previa: Dict[int, np.ndarray] = {}
    t_mov: Dict[int, float] = {}
    t_orden: Dict[int, Optional[float]] = {}
    t_sin_orden: Dict[int, Optional[float]] = {}
    for f in registro[marca:]:
        ag = int(f["agente"])
        t = 0.1 * int(f["paso"])
        p = np.array([float(f["pose_env_x"]), float(f["pose_env_y"])])
        if ag in previa:
            if float(np.linalg.norm(p - previa[ag])) > ESTANC_AVANCE_MIN_M:
                t_mov[ag] = t
        else:
            t_mov[ag] = t
        previa[ag] = p
        con_orden = abs(float(f["v_ejecutada"])) > ESTANC_V_MIN
        if con_orden:
            t_sin_orden[ag] = None
            if t_orden.get(ag) is None:
                t_orden[ag] = t
        else:
            if t_sin_orden.get(ag) is None:
                t_sin_orden[ag] = t
            if (t_orden.get(ag) is not None
                    and t - t_sin_orden[ag] >= ESTANC_CORTE_ORDEN_S):
                t_orden[ag] = None
        if int(f.get("en_retroceso", 0) or 0) or not con_orden:
            continue
        t_ref = max(t_mov[ag], t_orden[ag] + ESTANC_MARGEN_S)
        if t - t_ref > ESTANC_T_S:
            return int(f["paso"]), ag
    return "", ""


def _correr_episodio_medicion(coord: CoordinadorConObstaculo,
                              canal: CanalConObstaculo,
                              registro: List[Dict[str, Any]], marca: int,
                              decisiones: int, semilla: int) -> Dict[str, Any]:
    """
    Lazo de MEDICIÓN, sólo para la campaña en el simulador: el mismo
    `_avanzar` + `_decidir_y_actuar` del coordinador con obstáculo, sin las
    reglas del lazo de evaluación que cortarían un encuentro antes de
    medirlo (ver `primer_corte_por_estancamiento`). Conserva los cortes que
    no son de juicio: enlace caído, agente fuera de la arena, aborto del
    supervisor del obstáculo, fin del episodio del env.
    """
    n = coord.n_agentes
    t0 = time.perf_counter()
    tiempos: List[float] = []
    abortado, motivo = False, ""
    col_015: set = set()
    col_022: set = set()
    for _paso in range(decisiones):
        if not coord._avanzar(coord.pasos_por_decision):
            abortado, motivo = True, "el entorno pidió terminar"
            break
        t_d = time.perf_counter()
        terminado = coord._decidir_y_actuar()
        tiempos.append((time.perf_counter() - t_d) * 1000.0)
        caidos = canal.enlaces_caidos()
        if caidos:
            abortado, motivo = True, f"enlace de ruedas caído: agentes {caidos}"
            break
        filas = registro[-n:] if len(registro) >= marca + n else []
        poses = {int(f["agente"]): np.array([f["pose_env_x"], f["pose_env_y"]])
                 for f in filas}
        fuera = [a for a, p in poses.items()
                 if not (0 <= p[0] <= ARENA_SIZE[0] and 0 <= p[1] <= ARENA_SIZE[1])]
        if fuera:
            abortado, motivo = True, f"agente {fuera[0]} fuera de la arena"
            break
        ids = sorted(poses)
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                d = float(np.linalg.norm(poses[ids[a]] - poses[ids[b]]))
                if d < 0.15:
                    col_015.add((ids[a], ids[b]))
                if d < 0.22:
                    col_022.add((ids[a], ids[b]))
        # Sin cortar en el fin del env (`terminado`): `_correr_episodio`
        # tampoco lo hace, y la toma tiene que tener sus `decisiones`.
        del terminado
    canal.detener_todo()
    duracion = time.perf_counter() - t0
    return {
        "valido": int(not abortado), "motivo": motivo, "semilla": semilla,
        "decisiones": len(tiempos), "duracion_s": duracion,
        "cobertura_aoi": 1.0 - float(np.mean(coord.env._field._grid_aoi)),
        "colisiones_015": len(col_015), "colisiones_022": len(col_022),
        "ciclo_p95_ms": float(np.percentile(tiempos, 95)) if tiempos else 0.0,
        "ritmo_hz": len(tiempos) / max(duracion, 1e-9),
    }


def correr_toma(
    coord:      CoordinadorConObstaculo,
    canal:      CanalConObstaculo,
    fuente:     FuentePosesConObstaculo,
    entorno:    Any,
    semilla:    int,
    decisiones: int,
    registro:   List[Dict[str, Any]],
    rpm_aborto: float = 200.0,
    detector:   Any = None,
    seguimiento: Any = None,
    diag:       Any = None,
    lazo:       str = "evaluacion",
) -> Dict[str, Any]:
    """
    Una toma. Con `lazo="evaluacion"` (el del laboratorio) es
    `_correr_episodio` de la evaluación —con TODAS sus protecciones: enlaces
    caídos, rpm, fuera de la arena, pose vencida, retroceso por pose
    repetida, seguimiento, estancamiento, ritmo del lazo— sobre el
    coordinador con obstáculo. Si el que cortó fue el supervisor, se repone
    su motivo (`_correr_episodio` sólo vería "el entorno pidió terminar").

    `lazo="medicion"` es el de la campaña del simulador
    (`_correr_episodio_medicion`). En los dos se informa en qué decisión
    habría cortado la regla de estancamiento (`corte_estancamiento_paso`).

    `valido_demo` = válida para el video, según `validez_demo`: válida Y
    cero frenos de respaldo Y sin contacto Y (L2) el obstáculo en marcha.
    """
    import sesion_robotat as ses
    if lazo not in ("evaluacion", "medicion"):
        raise ValueError(f"lazo {lazo!r}")
    detector = detector or ses.DetectorCongelamiento()
    seguimiento = seguimiento or ses.DetectorSeguimiento()
    marca = len(registro)
    detector.reiniciar()
    seguimiento.reiniciar()
    if hasattr(entorno, "reiniciar_reloj"):
        entorno.reiniciar_reloj()
    antes = ses._contadores_fuente(fuente)
    if not coord._reiniciar_episodio(semilla):
        res: Dict[str, Any] = {"valido": 0, "semilla": semilla,
                               "motivo": (coord.motivo_aborto_obstaculo
                                          or "no se pudo iniciar la toma")}
        res.update(coord.resumen_obstaculo())
        res["valido_demo"] = 0
        return res
    if lazo == "evaluacion":
        res = ses._correr_episodio(coord, canal, fuente, registro, marca,
                                   decisiones, rpm_aborto, coord.n_agentes,
                                   detector, semilla, seguimiento, diag=diag)
    else:
        res = _correr_episodio_medicion(coord, canal, registro, marca,
                                        decisiones, semilla)
    res["lazo"] = lazo
    res.update(ses._delta_contadores_fuente(antes, fuente))
    if (coord.motivo_aborto_obstaculo is None
            and getattr(canal, "obstaculo_caido", False)):
        # El lazo de evaluación pudo cortar por otra regla en la misma
        # decisión en que se cayó el enlace del obstáculo: ése es el motivo.
        coord.motivo_aborto_obstaculo = (
            f"enlace de ruedas del obstáculo (robot "
            f"{canal.id_robot_obstaculo}) caído")
    if coord.motivo_aborto_obstaculo is not None:
        res["valido"] = 0
        res["motivo"] = f"OBSTÁCULO: {coord.motivo_aborto_obstaculo}"
    res.update(coord.resumen_obstaculo())
    paso_corte, ag_corte = primer_corte_por_estancamiento(registro, marca)
    res["corte_estancamiento_paso"] = paso_corte
    res["corte_estancamiento_agente"] = ag_corte
    res["valido_demo"], res["motivo_demo"] = validez_demo(res)
    return res


def validez_demo(res: Dict[str, Any]) -> Tuple[int, str]:
    """
    ¿La toma vale para el video? Válida, Y cero frenos de respaldo (decisión
    de José: con freno la toma ya no muestra al filtro de los agentes solo;
    el freno es una capa redundante), Y ningún agente a < 0.15 m del
    obstáculo (revisión: el freno sólo mira por delante), Y —en L2— el
    obstáculo recorrió al menos la mitad de lo comandado, si se le comandó
    al menos 0.20 m (revisión: un obstáculo inmóvil no es una demo de
    obstáculo MÓVIL). Devuelve (0/1, motivo).
    """
    if not int(res.get("valido", 0) or 0):
        return 0, "toma no válida"
    if int(res.get("frenos", 0) or 0):
        return 0, f"intervención del freno de respaldo ({res['frenos']})"
    d = res.get("d_min_obst_medida", "")
    if d != "" and float(d) < 0.15:
        return 0, f"agente a {float(d):.3f} m del obstáculo (< 0.15)"
    if res.get("obst_modo") == "movil":
        med = float(res.get("obst_recorrido_m", 0.0) or 0.0)
        com = float(res.get("obst_recorrido_comandado_m", 0.0) or 0.0)
        if com >= 0.20 and med < FRACCION_RECORRIDO_MIN * com:
            return 0, (f"el obstáculo recorrió {med:.2f} m de {com:.2f} m "
                       f"comandados")
    return 1, ""


def regla_de_parada(res: Dict[str, Any],
                    anteriores: Sequence[Dict[str, Any]]) -> Optional[str]:
    """
    ¿Esta toma DETIENE la sesión? Las reglas de parada de
    `tesis/PROTOCOLO_L0_L2.md`, que hasta el 2026-10-03 aplicaba sólo el
    operador. Se mira en TODA toma corrida, válida o no; `anteriores` son
    las tomas corridas antes de ésta, en orden. Devuelve el texto de la(s)
    regla(s) que se cumplen, o None.

      · CONTACTO: `d_min_obst_medida` < `UMBRAL_CONTACTO_M`.
      · FRENO en `TOMAS_CON_FRENO_SEGUIDAS` tomas corridas seguidas.
      · ABORTO POR EL OBSTÁCULO: la toma la cortó el supervisor o el enlace
        del obstáculo (obediencia, enlace caído, error radial, marcador), o
        el enlace del obstáculo falló durante la toma aunque se haya
        reabierto al frenar (`obst_enlace_cayo`, lo anota `sesion_demo`).
      · SIN DISTANCIA MEDIDA en una toma que corrió: no se puede descartar
        el contacto.
    """
    reglas: List[str] = []
    try:
        d = float(res.get("d_min_obst_medida", ""))
    except (TypeError, ValueError):
        d = float("nan")
    if math.isfinite(d) and d < UMBRAL_CONTACTO_M:
        reglas.append(f"CONTACTO: un agente quedó a {d:.3f} m del obstáculo "
                      f"(< {UMBRAL_CONTACTO_M:.2f} m)")
    try:
        corrio = int(res.get("decisiones", 0) or 0) > 0
    except (TypeError, ValueError):
        corrio = False
    if corrio and not math.isfinite(d):
        reglas.append("SIN DISTANCIA MEDIDA al obstáculo: no se puede "
                      "descartar un contacto")
    n = max(2, TOMAS_CON_FRENO_SEGUIDAS)
    ultimas = list(anteriores)[-(n - 1):] + [res]
    if len(ultimas) == n and all(int(t.get("frenos", 0) or 0) > 0
                                 for t in ultimas):
        reglas.append(f"FRENO DE RESPALDO en {n} tomas seguidas")
    motivo = str(res.get("motivo", "") or "")
    motivo_obst = str(res.get("obst_motivo_aborto", "") or "")
    if motivo_obst or motivo.startswith("OBSTÁCULO:"):
        detalle = motivo_obst or motivo[len("OBSTÁCULO:"):].strip()
        try:
            fallidas = int(res.get("poses_fallidas", 0) or 0)
        except (TypeError, ValueError):
            fallidas = 0
        if detalle.startswith("pose del obstáculo vencida") and fallidas > 0:
            # Una consulta de lote fallida vence las SEIS poses a la vez; el
            # supervisor corre primero y se queda con el motivo. Se detiene
            # igual (lado seguro), pero con la causa probable a la vista.
            reglas.append(f"ABORTO POR POSE VENCIDA DEL OBSTÁCULO con "
                          f"{fallidas} consulta(s) de poses fallida(s): "
                          f"probable hipo del servidor de poses (vencen todos "
                          f"los marcadores), no del robot del obstáculo — "
                          f"revisar red y mocap antes de seguir")
        else:
            reglas.append(f"ABORTO POR EL OBSTÁCULO: {detalle} — revisar el "
                          f"robot del obstáculo antes de seguir")
    elif int(res.get("obst_enlace_cayo", 0) or 0):
        reglas.append("ENLACE DEL OBSTÁCULO caído durante la toma (se reabrió "
                      "al frenar) — revisar el robot del obstáculo antes de "
                      "seguir")
    return " · ".join(reglas) if reglas else None


def respuesta_sigue(respuesta: Any) -> bool:
    """¿El operador pidió seguir? SÓLO una "s" (sin importar mayúsculas ni
    espacios); cualquier otra cosa, Enter incluido, termina la sesión."""
    return str(respuesta).strip().lower() == "s"


def _preguntar_con_latido(ctx: Any, fuente: Any, canal: Any,
                          mensaje: str) -> str:
    """
    Pregunta al operador SIN dejar morir los enlaces ni dejar de frenar: el
    mismo latido de la colocación (`sesion_robotat._esperar_reposicionamiento`,
    hallazgo del 2026-09-05: con los sockets minutos sin tráfico, el servidor
    de poses y los robots los descartan). Cada `PERIODO_LATIDO_S`, una
    lectura de poses y un `detener_todo(silencioso=True)`, que además reabre
    y frena al obstáculo si su enlace vuelve (revisión 2026-10-03: sin esto,
    un 7 sin WiFi que recupera la red seguía con su última orden mientras se
    esperaba la respuesta).
    """
    import threading
    import sesion_robotat as ses
    from lanzar_robotat import leer_poses_estables
    parar = threading.Event()

    def latir() -> None:
        while not parar.is_set():
            try:
                leer_poses_estables(fuente, len(cfg.MAPEO_AGENTES), plazo_s=0.5)
            except Exception:                                # noqa: BLE001
                pass
            try:
                canal.detener_todo(silencioso=True)
            except Exception:                                # noqa: BLE001
                pass
            parar.wait(ses.PERIODO_LATIDO_S)

    hilo = threading.Thread(target=latir, daemon=True)
    hilo.start()
    try:
        return str(ctx.preguntar(mensaje))
    finally:
        parar.set()
        hilo.join(timeout=2.0)


def aplicar_regla_de_parada(ctx: Any, fuente: Any, canal: Any, regla: str,
                            res: Dict[str, Any]) -> bool:
    """
    Frena todo, avisa (con lo que no se pudo confirmar frenado), pregunta
    con latido y devuelve True sólo si el operador escribió "s". Anota en
    `res` lo que no se confirmó y la respuesta. Es el bloque que
    `sesion_demo` usaba después de cada toma (2026-10-03), sin cambios;
    desde el 2026-10-07 lo usa también la colocación automática.
    """
    canal.detener_todo()
    faltan = detencion_sin_confirmar(canal, regla)
    print("=" * 72)
    print(f"⛔ REGLA DE PARADA — {regla}")
    if faltan:
        print("   ⚠ NO SE PUDO CONFIRMAR LA DETENCIÓN: "
              + "; ".join(faltan)
              + ". LEVANTARLO / CORTAR ALIMENTACIÓN A MANO.")
        print("   Sesión DETENIDA. Se sigue intentando frenar "
              "mientras espera.")
    else:
        print("   Sesión DETENIDA, con la detención de los robots "
              "confirmada.")
    print("   Revisá antes de seguir (PROTOCOLO_L0_L2.md).")
    print("=" * 72)
    res["parada_detencion_sin_confirmar"] = "; ".join(faltan)
    resp = _preguntar_con_latido(
        ctx, fuente, canal,
        "  ¿Seguir con la sesión? Escribí s y Enter para seguir; "
        "cualquier otra cosa la termina: ")
    seguir = respuesta_sigue(resp)
    res["parada_respuesta"] = "siguió" if seguir else "detenida"
    return seguir


def detencion_sin_confirmar(canal: Any, regla: str) -> List[str]:
    """Lo que NO se pudo confirmar frenado después de `detener_todo`."""
    faltan: List[str] = []
    if getattr(canal, "obstaculo_detencion_fallida", False):
        faltan.append(f"obstáculo (robot {getattr(canal, 'id_robot_obstaculo', '?')})")
    fallos = list(getattr(canal, "ultimos_fallos_detencion", []) or [])
    if fallos:
        faltan.append(f"agentes {fallos}")
    if "NO FRENA" in regla:
        faltan.append("el obstáculo abortó por NO FRENAR")
    return faltan


# =============================================================================
# ARRANQUES
# =============================================================================

def fase_arranque_obstaculo(semilla: int) -> float:
    """Fase del círculo donde arranca el obstáculo en la toma (L2)."""
    rng = np.random.default_rng([int(semilla), ID_ROBOT_OBSTACULO])
    return float(rng.uniform(-math.pi, math.pi))


def arranque_obstaculo(semilla: int, modo: str,
                       par: Optional[ParametrosTrayectoria] = None
                       ) -> Tuple[np.ndarray, Optional[float]]:
    """Punto (y rumbo, en L2) donde se coloca el obstáculo en esta toma."""
    if modo == "L1":
        return np.array(PUNTO_L1_ENV, dtype=np.float64), None
    p, rumbo = punto_del_circulo(fase_arranque_obstaculo(semilla), par)
    return p, rumbo


def sortear_blancos_demo(n_agentes: int, semilla: int,
                         punto_obstaculo: np.ndarray,
                         intentos: int = 200) -> Dict[int, np.ndarray]:
    """
    Blancos de los agentes de la distribución de entrenamiento
    (`sortear_poses_arranque`), por rechazo hasta que todos queden a
    ≥ `SEPARACION_ARRANQUE_OBSTACULO_M` del punto de arranque del obstáculo.
    """
    import sesion_robotat as ses
    rng = np.random.default_rng(int(semilla))
    for _ in range(intentos):
        b = ses.sortear_poses_arranque(n_agentes, rng)
        if all(float(np.linalg.norm(p - punto_obstaculo[:2]))
               >= SEPARACION_ARRANQUE_OBSTACULO_M for p in b.values()):
            return b
    raise RuntimeError("no se pudieron sortear blancos lejos del obstáculo")


def problemas_obstaculo_al_arrancar(
    fuente: FuentePosesConObstaculo,
    poses_agentes: Dict[int, np.ndarray],
    objetivo: np.ndarray,
    rumbo_objetivo: Optional[float],
) -> List[str]:
    """Chequeos del obstáculo antes de arrancar una toma (L1 y L2)."""
    problemas: List[str] = []
    pose = fuente.pose_obstaculo()
    if pose is None or fuente.antiguedad_obstaculo_s() > 1.0:
        return [f"obstáculo (marcador {fuente.id_marcador_obstaculo}): sin "
                f"pose viva"]
    if not cfg.SIMULADOR_ACTIVO and fuente.repeticiones_obstaculo >= 1:
        problemas.append("obstáculo: marcador CONGELADO (pose repetida) — "
                         "movelo hasta que la pose cambie")
    d = float(np.linalg.norm(pose[:2] - objetivo[:2]))
    if d > TOL_COLOCACION_OBSTACULO_M:
        problemas.append(f"obstáculo a {d * 100:.1f} cm de su punto "
                         f"({objetivo[0]:.2f}, {objetivo[1]:.2f}); tolerancia "
                         f"{TOL_COLOCACION_OBSTACULO_M * 100:.0f} cm")
    if rumbo_objetivo is not None:
        e = abs(_envolver(float(pose[2]) - rumbo_objetivo))
        if e > TOL_RUMBO_OBSTACULO_RAD:
            problemas.append(f"obstáculo mal orientado: {math.degrees(e):.0f}° "
                             f"de la tangente antihoraria (máx "
                             f"{math.degrees(TOL_RUMBO_OBSTACULO_RAD):.0f}°)")
    for i, p in sorted(poses_agentes.items()):
        dd = float(np.linalg.norm(np.asarray(p[:2]) - pose[:2]))
        if dd < SEPARACION_ARRANQUE_OBSTACULO_M:
            problemas.append(f"agente {i}: a {dd:.2f} m del obstáculo (mínimo "
                             f"{SEPARACION_ARRANQUE_OBSTACULO_M:.2f} m)")
    return problemas


def ruta_salida_demo(etiqueta: str, descripcion: str,
                     carpeta: Optional[Path] = None) -> Path:
    """Ruta nueva con fecha; nunca pisa un archivo existente."""
    carpeta = carpeta or DIR_SALIDA_DEMO
    carpeta.mkdir(parents=True, exist_ok=True)
    base = f"{datetime.now():%Y%m%d_%H%M%S}_{etiqueta}_{descripcion}"
    ruta = carpeta / f"{base}.csv"
    k = 2
    while ruta.exists():
        ruta = carpeta / f"{base}_{k:02d}.csv"
        k += 1
    return ruta


#: Un CSV bloqueado (Excel, OneDrive): reintentos con aviso, como el libro.
REINTENTOS_ESCRITURA_CSV: int = 60
ESPERA_REINTENTO_CSV_S: float = 0.5


def escribir_csv(ruta: Path, filas: Sequence[Dict[str, Any]]) -> None:
    """
    CSV con la unión de las columnas, sin redondeo, en LF. Escritura ATÓMICA
    (un temporal en la misma carpeta, fsync y `os.replace`) con reintentos
    si el archivo está bloqueado: un corte o un Excel abierto nunca dejan el
    crudo a medias (auditoría final, 10-10).
    """
    buf = io.StringIO()
    if filas:
        columnas: List[str] = []
        for f in filas:
            for k in f:
                if k not in columnas:
                    columnas.append(k)
        w = csv.DictWriter(buf, fieldnames=columnas, lineterminator="\n")
        w.writeheader()
        for f in filas:
            # repr(float(·)): precisión completa y sin el "np.float64(...)"
            # que numpy 2 pone en el repr de sus escalares.
            w.writerow({k: (repr(float(v))
                            if isinstance(v, (float, np.floating)) else v)
                        for k, v in f.items()})
    datos = buf.getvalue().encode("utf-8")
    temporal = ruta.with_name(ruta.name + ".tmp")
    avisado = False
    for intento in range(REINTENTOS_ESCRITURA_CSV):
        try:
            with open(temporal, "wb") as fh:
                fh.write(datos)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temporal, ruta)
            return
        except PermissionError:
            if intento == REINTENTOS_ESCRITURA_CSV - 1:
                raise
            if not avisado:
                print(f"⚠ {ruta.name} está bloqueado (¿abierto en Excel?): cerralo; "
                      f"reintento {REINTENTOS_ESCRITURA_CSV * ESPERA_REINTENTO_CSV_S:.0f} s…")
                avisado = True
            time.sleep(ESPERA_REINTENTO_CSV_S)


# =============================================================================
# SESIONES DE LABORATORIO
# =============================================================================

#: Offset de rumbo del robot obstáculo (decisión de José, 2026-10-07): si la
#: L0 lo mide a más de esto de la tabla, NO se sigue con la L1 y se propone
#: la corrección de `config_robotat.py`.
OFFSET_MAX_DIFERENCIA_DEG: float = 3.0
#: Pares de muestras mínimos para dar por medida la diferencia.
OFFSET_MUESTRAS_MIN: int = 20


def estimar_error_offset(filas: Sequence[Dict[str, Any]],
                         separacion: int = 3) -> Tuple[float, int]:
    """
    Diferencia entre el rumbo REAL y el MEDIDO del robot de la L0, en grados,
    con los tramos de crucero de la traza: en cada par de muestras separadas
    `separacion` decisiones del mismo arranque (t ≥ 2 s, v ≥ 0.04 m/s,
    |ω| < 0.3 rad/s, ≥ 5 mm recorridos), la dirección del desplazamiento
    menos el rumbo medido medio. Sin patinamiento, el robot avanza hacia
    donde mira, así que la mediana es (offset verdadero − offset usado): el
    offset corregido sería el de la tabla MÁS este valor. Devuelve
    (diferencia en grados, pares usados); NaN si no hay pares.
    """
    dif: List[float] = []
    for k in range(len(filas) - separacion):
        a, b = filas[k], filas[k + separacion]
        if a["arranque"] != b["arranque"] or a["t"] < 2.0:
            continue
        if not all(f["v"] >= 0.04 and abs(f["w"]) < 0.3 for f in (a, b)):
            continue
        dx, dy = b["x"] - a["x"], b["y"] - a["y"]
        if math.hypot(dx, dy) < 0.005:
            continue
        th = math.atan2(math.sin(a["th"]) + math.sin(b["th"]),
                        math.cos(a["th"]) + math.cos(b["th"]))
        dif.append(math.degrees(_envolver(math.atan2(dy, dx) - th)))
    if not dif:
        return float("nan"), 0
    return float(np.median(dif)), len(dif)


def _metricas_l0(filas: Sequence[Dict[str, Any]],
                 resultados: Sequence[Dict[str, Any]],
                 par: ParametrosTrayectoria) -> Dict[str, Any]:
    """Arranques logrados, error radial máximo (t ≥ 2 s), ω saturado y la
    diferencia del offset de rumbo contra la tabla."""
    errores = [abs(f["error_radial"]) for f in filas if f["t"] >= 2.0]
    d_off, n_off = estimar_error_offset(filas)
    return {
        "arranques_corridos": len(resultados),
        "arranques_ok": sum(r["arranco"] for r in resultados),
        "error_radial_max": max(errores) if errores else float("nan"),
        "fraccion_omega_saturado": (
            sum(1 for f in filas if abs(f["w"]) >= par.omega_max - 1e-9)
            / len(filas) if filas else float("nan")),
        "offset_dif_deg": d_off,
        "offset_pares": n_off,
    }


def _l0_del_simulador(fila: Dict[str, str]) -> bool:
    """¿Esa fila de `_L0_resumen.csv` salió del simulador? (las previas al
    08-10 no tienen la columna: eran todas de hardware o de pruebas)."""
    return str(fila.get("simulador", "")).strip() in ("1", "True", "true")


def l0_habilita(id_robot: int, carpeta: Optional[Path] = None
                ) -> Tuple[bool, str]:
    """
    ¿La última L0 del robot habilita la L1/L2? (decisión de José del
    2026-10-07: si el offset medido difiere > 3° de la tabla, se frena antes
    de la L1 y se propone la corrección). Exige el `_L0_resumen.csv` más
    reciente de ese robot con veredicto OK y |diferencia| ≤ 3° medida con
    ≥ OFFSET_MUESTRAS_MIN pares.
    """
    carpeta = carpeta or DIR_SALIDA_DEMO
    filas: List[Dict[str, str]] = []
    for ruta in sorted(carpeta.glob("*_L0_resumen*.csv")):
        try:
            with open(ruta, newline="", encoding="utf-8") as fh:
                filas += [f for f in csv.DictReader(fh)
                          if str(f.get("robot")) == str(int(id_robot))
                          and not _l0_del_simulador(f)]
        except OSError:
            continue
    if not filas:
        return False, (f"no hay L0 del robot {id_robot} en {carpeta}: "
                       f"correr antes la L0")
    f = filas[-1]
    if f.get("veredicto") != "OK":
        return False, (f"la última L0 del robot {id_robot} dio "
                       f"{f.get('veredicto')}: {f.get('detalle', '')}")
    ref = f.get("offset_tabla_deg")
    tabla_hoy = math.degrees(cfg.offset_rumbo_de_robot(int(id_robot)))
    if ref not in (None, "") and abs(float(ref) - tabla_hoy) > 0.01:
        return False, (f"el offset de rumbo del robot {id_robot} cambió desde "
                       f"la última L0 ({float(ref):+.2f}° → {tabla_hoy:+.2f}°): "
                       f"repetir la L0")
    try:
        d = float(f.get("offset_dif_deg", "nan"))
        n = int(float(f.get("offset_pares", 0) or 0))
    except ValueError:
        d, n = float("nan"), 0
    if not math.isfinite(d) or n < OFFSET_MUESTRAS_MIN:
        return False, (f"la última L0 del robot {id_robot} no pudo medir el "
                       f"offset de rumbo ({n} pares)")
    tabla = math.degrees(cfg.offset_rumbo_de_robot(int(id_robot)))
    if abs(d) > OFFSET_MAX_DIFERENCIA_DEG:
        return False, (f"el offset de rumbo del robot {id_robot} difiere "
                       f"{d:+.1f}° de la tabla (> {OFFSET_MAX_DIFERENCIA_DEG:.0f}°):"
                       f" NO seguir; corrección propuesta para config_robotat.py:"
                       f" {tabla:+.2f}° → {tabla + d:+.2f}°")
    return True, f"L0 OK, offset a {d:+.1f}° de la tabla ({n} pares)"


def sesion_l0(ctx: Any, arranques: int = 10, marcha_s: float = 6.0,
              pausa_s: float = 2.0,
              par: Optional[ParametrosTrayectoria] = None,
              id_robot: int = ID_ROBOT_OBSTACULO,
              id_marcador: int = ID_MARCADOR_OBSTACULO,
              umbral_mov_m: float = 0.003,
              plazo_arranque_s: float = 1.5,
              fase_arranque_rad: float = -math.pi / 2) -> Dict[str, Any]:
    """
    L0: el obstáculo SOLO. Marcador vivo; colocación guiada en el punto del
    círculo de `fase_arranque_rad` (por defecto (1.5, 0.9) del env, rumbo
    +x); después `arranques` arranques desde parado. Cada arranque dura
    `marcha_s` desde el primer mando, patada incluida (0.08 m/s ≤ 1 s,
    después crucero por el círculo), y lo sigue una pausa de `pausa_s`.

    Criterio: arranques 10 de 10 (se movió ≥ 3 mm antes de
    `plazo_arranque_s`) y error radial máximo < 5 cm (sin los primeros 2 s
    de cada arranque, que son el transitorio de enganche). Aborta en el
    acto, frenando, si el error radial pasa de `ERROR_RADIAL_MAX_M` en
    cualquier decisión (enganche incluido), si se pierde la pose, si el
    marcador está congelado o si no se logra colocar el robot. Se informa
    además la fracción de decisiones con ω saturado (todas, patada incluida;
    revisión de la Fase 0: con un retardo grande el seguimiento puede
    serpentear dentro de los 5 cm).

    Escribe SIEMPRE —también si aborta, si no se puede conectar o ante
    Ctrl+C— `<fecha>_L0_resumen.csv`: una fila con el veredicto, el detalle,
    los arranques, el error radial y el ω saturado (2026-10-03: antes sólo
    salían por consola). La L0 no habilita sola a la L1/L2: si da FALLO
    (código de salida 1), no seguir es decisión del operador.
    """
    import sesion_robotat as ses
    par = par or ParametrosTrayectoria()
    filas: List[Dict[str, Any]] = []
    resultados: List[Dict[str, Any]] = []
    resultado: Dict[str, Any] = {}
    poses: Any = None
    rueda: Any = None
    # Sin `atexit`: el `finally` de abajo frena y cierra (también ante Ctrl+C);
    # un `atexit` sobre el socket ya cerrado gritaría "NO SE PUDO FRENAR".
    try:
        # Los enlaces se abren DENTRO del try (revisión 2026-10-03: un
        # timeout al abrir las ruedas dejaba abierto el cliente de poses y
        # salía con traceback, sin resumen).
        try:
            poses = ses.ClientePosesCrudo()
            rueda = ses.ClienteRueda(id_robot)
        except OSError as exc:
            que = ("servidor de poses" if poses is None
                   else f"ruedas del robot {id_robot}")
            resultado = {"veredicto": "FALLO",
                         "detalle": f"no se pudo conectar ({que}): {exc}"}
            return resultado
        congelado, distintos, utiles = ses.stream_congelado(poses, id_marcador)
        if not utiles or congelado:
            resultado = {"veredicto": "FALLO",
                         "detalle": f"marcador {id_marcador} "
                                    f"{'congelado' if utiles else 'sin respuesta'}"}
            return resultado

        def pose_env() -> Optional[np.ndarray]:
            fila = poses.pose(id_marcador)
            if fila is None or not pose_es_valida(fila)[0]:
                return None
            yaw, _ = heading_desde_cuaternion(*(float(c) for c in fila[3:7]))
            return lab_a_env(float(fila[0]), float(fila[1]), yaw,
                             cfg.offset_rumbo_de_robot(id_robot))

        # Colocación guiada (revisión: sin esto la L0 fallaba en el primer
        # ciclo, por error radial, salvo que el robot ya estuviera ahí).
        objetivo, rumbo_obj = punto_del_circulo(fase_arranque_rad, par)
        for intento in range(6):
            print(f"  L0: colocá el robot {id_robot} en ({objetivo[0]:.2f}, "
                  f"{objetivo[1]:.2f}) del env, mirando "
                  f"{math.degrees(rumbo_obj):+.0f}° (tangente antihoraria), "
                  f"±{TOL_COLOCACION_OBSTACULO_M * 100:.0f} cm y "
                  f"±{math.degrees(TOL_RUMBO_OBSTACULO_RAD):.0f}°.")
            ctx.esperar_enter("  Robot colocado y arena despejada.")
            pc = pose_env()
            if pc is None:
                print("  ✘ sin pose del marcador; reintentá.")
                continue
            d = float(np.linalg.norm(pc[:2] - objetivo[:2]))
            e = abs(_envolver(float(pc[2]) - rumbo_obj))
            if d <= TOL_COLOCACION_OBSTACULO_M and e <= TOL_RUMBO_OBSTACULO_RAD:
                break
            print(f"  ✘ está a {d * 100:.1f} cm y {math.degrees(e):.0f}° del "
                  f"punto de arranque; corregí y dale Enter.")
        else:
            resultado = {"veredicto": "FALLO",
                         "detalle": "no se logró colocar el robot en su punto"}
            return resultado

        for k in range(arranques):
            p0 = pose_env()
            if p0 is None:
                resultado = {"veredicto": "FALLO",
                             "detalle": "sin pose al arrancar"}
                return resultado
            t0 = time.perf_counter()
            t_mov: Optional[float] = None
            en_patada = True
            while True:
                ahora = time.perf_counter()
                tau = ahora - t0
                if tau > marcha_s:
                    break
                p = pose_env()
                if p is None:
                    rueda.detener()
                    resultado = {"veredicto": "FALLO",
                                 "detalle": f"pose perdida en el arranque {k}"}
                    return resultado
                if t_mov is None and float(np.linalg.norm(p[:2] - p0[:2])) \
                        >= umbral_mov_m:
                    t_mov = tau
                if en_patada and (tau >= par.t_patada_max_s
                                  or t_mov is not None):
                    en_patada = False
                v_ref = par.v_patada if en_patada else par.v_crucero
                v, w, e = ley_seguimiento_circulo(p, par, v_ref)
                if abs(e) > ERROR_RADIAL_MAX_M:
                    rueda.detener()
                    resultado = {"veredicto": "FALLO",
                                 "detalle": f"error radial {e:+.3f} m en el "
                                            f"arranque {k}",
                                 "error_radial_aborto": abs(e)}
                    return resultado
                rueda.enviar(v, w)
                filas.append({"arranque": k, "t": tau, "x": float(p[0]),
                              "y": float(p[1]), "th": float(p[2]),
                              "v": v, "w": w, "error_radial": e,
                              "patada": int(en_patada)})
                time.sleep(max(0.0, 0.1 - (time.perf_counter() - ahora)))
            rueda.detener()
            resultados.append({"arranque": k,
                               "t_movimiento_s": t_mov if t_mov is not None
                               else "",
                               "arranco": int(t_mov is not None
                                              and t_mov <= plazo_arranque_s)})
            time.sleep(pausa_s)

        m = _metricas_l0(filas, resultados, par)
        e_max = m["error_radial_max"]
        ok = (m["arranques_ok"] == arranques and math.isfinite(e_max)
              and e_max < 0.05)
        detalle = (f"arranques {m['arranques_ok']}/{arranques} · error radial "
                   f"máx {e_max * 100:.1f} cm (sin los 2 s de enganche) · ω "
                   f"saturado en el {100 * m['fraccion_omega_saturado']:.0f} % "
                   f"de las decisiones · offset de rumbo a "
                   f"{m['offset_dif_deg']:+.1f}° de la tabla "
                   f"({m['offset_pares']} pares)")
        if (math.isfinite(m["offset_dif_deg"])
                and abs(m["offset_dif_deg"]) > OFFSET_MAX_DIFERENCIA_DEG):
            tabla = math.degrees(cfg.offset_rumbo_de_robot(id_robot))
            print("=" * 68)
            print(f"⛔ OFFSET DE RUMBO del robot {id_robot}: difiere "
                  f"{m['offset_dif_deg']:+.1f}° de la tabla (> "
                  f"{OFFSET_MAX_DIFERENCIA_DEG:.0f}°). NO seguir con la L1.")
            print(f"   Corrección propuesta (config_robotat.py, con OK): "
                  f"{tabla:+.2f}° → {tabla + m['offset_dif_deg']:+.2f}°")
            print("=" * 68)
        resultado = {"veredicto": "OK" if ok else "FALLO", "detalle": detalle,
                     **m, "arranques": resultados}
        return resultado
    except BaseException as exc:
        if not resultado:
            resultado = {"veredicto": "FALLO",
                         "detalle": f"interrumpida ({type(exc).__name__}: {exc})"}
        raise
    finally:
        if rueda is not None:
            rueda.cerrar()
        if poses is not None:
            poses.cerrar()
        escribir_csv(ruta_salida_demo("L0", "traza"), filas)
        escribir_csv(ruta_salida_demo("L0", "arranques"), resultados)
        m = _metricas_l0(filas, resultados, par)
        escribir_csv(ruta_salida_demo("L0", "resumen"), [{
            "veredicto": resultado.get("veredicto", "FALLO"),
            "detalle": resultado.get("detalle", "sin resultado"),
            "robot": id_robot, "marcador": id_marcador,
            "arranques_pedidos": arranques, **m,
            # La campaña en hardware no acepta una L0 del simulador ni una
            # medida contra otro offset (revisión del 08-10).
            "simulador": int(bool(getattr(ctx, "simulador", False))),
            "offset_tabla_deg": round(math.degrees(
                cfg.offset_rumbo_de_robot(int(id_robot))), 4),
            # El error de la decisión que abortó (no entra en
            # `error_radial_max`, que es el de las filas enviadas con t ≥ 2 s).
            "error_radial_aborto": resultado.get("error_radial_aborto", "")}])
        print(f"\n>>> L0: {resultado.get('veredicto', 'FALLO')} — "
              f"{resultado.get('detalle', 'sin resultado')}")


def sesion_demo(ctx: Any, modo: str, tomas: int = 3,
                intentos_max: int = 6, decisiones: int = 500,
                factor: float = 0.40, rpm_aborto: float = 200.0,
                freno_activo: bool = True,
                id_robot_obstaculo: int = ID_ROBOT_OBSTACULO,
                id_marcador_obstaculo: int = ID_MARCADOR_OBSTACULO,
                formulacion: str = "F2",
                tau_prediccion_s: float = TAU_PREDICCION_S,
                intento_inicial: int = 1,
                colocacion: str = "manual",
                campana: Any = None,
                id_sesion: Optional[str] = None,
                ) -> Dict[str, Any]:
    """
    L1 (obstáculo apagado en el centro) o L2 (obstáculo en el círculo).

    Colocación MANUAL con la guía de siempre: la colocación autónoma no ve
    al obstáculo (`colocar_enjambre` filtra sólo contra los agentes) y podría
    llevar un agente a través de él. Busca `tomas` tomas válidas para el
    video (`validez_demo`) en los intentos `intento_inicial` … `intentos_max`.

    Después de cada toma corrida aplica las REGLAS DE PARADA
    (`regla_de_parada`): si se cumple una, frena todo, se detiene y sólo
    sigue con una "s" explícita del operador; si no, termina con veredicto
    DETENIDA. La regla y la respuesta quedan en el CSV de tomas.

    `intento_inicial` > 1 reanuda una sesión cortada: la numeración, las
    semillas y la cuenta contra `intentos_max` siguen desde ahí. La rampa
    de arranque seguro vuelve en la 1.ª toma de esta sesión (cuenta por
    canal) y la cuenta de frenos seguidos arranca de cero.

    `colocacion="auto"` (2026-10-07, OK de José; ver
    `colocacion_con_obstaculo.py`): los agentes van SOLOS a sus blancos
    alrededor del obstáculo QUIETO, con un Enter por toma. En la L2 el
    obstáculo arranca de la proyección de su pose sobre el círculo; si no
    está dentro de la envolvente de la Fase 0, se lo coloca a mano (la Fase
    A, que lo mueve solo, todavía no está). En la L1 el obstáculo va
    ENCENDIDO y conectado, frenado y vigilado (opción (b) de José). Un
    contacto o una falla del obstáculo durante la colocación es una regla
    de parada. Con "manual" —el default de la función— todo es como antes.

    `campana` (una `campana_obstaculo.Campana` con la sesión ya abierta;
    2026-10-08, OK de José): CAMPAÑA DE MEDICIÓN. Los intentos y las
    semillas los da el libro (únicas en toda la campaña); se cuentan las
    tomas INCLUIDAS (válidas para la medición y con el obstáculo en marcha)
    hasta la meta, el tope de intentos o la hora de fin; los frenos y los
    contactos son resultados, no exclusiones; la cadena de frenos seguidos
    se arrastra del libro; los CSV se reescriben después de cada intento.
    La consola NO muestra la cobertura (el operador queda ciego al resultado
    principal). Siempre (con o sin campaña) cada toma registra lo que la
    réplica necesita (`columnas_registro_toma`) y un `id_sesion` común a los
    tres CSV.
    """
    import sesion_robotat as ses
    from adaptadores_robotat import revisar_poses_iniciales
    from lanzar_robotat import leer_poses_estables
    from coordinador_enjambre import SEMILLAS_LOTE
    if modo not in ("L1", "L2"):
        raise ValueError(f"modo {modo!r}: 'L1' o 'L2'")
    if not 1 <= intento_inicial <= intentos_max:
        raise ValueError(f"intento_inicial {intento_inicial}: entre 1 e "
                         f"intentos_max ({intentos_max})")
    if colocacion not in ("manual", "auto"):
        raise ValueError(f"colocacion {colocacion!r}: 'manual' o 'auto'")
    if campana is not None and modo != "L2":
        raise ValueError("la campaña de medición es de la L2")
    automatica = colocacion == "auto"
    id_sesion = id_sesion or f"{modo}_{datetime.now():%Y%m%d_%H%M%S}"
    rutas = {d: ruta_salida_demo(modo, d)
             for d in ("decisiones", "obstaculo", "tomas")}
    n = len(cfg.MAPEO_AGENTES)
    print("=" * 72)
    print(f"DEMO OBSTÁCULO MÓVIL — {modo} — {n} agentes + robot "
          f"{id_robot_obstaculo} "
          f"({('ENCENDIDO, conectado, frenado y quieto' if automatica else 'APAGADO, quieto') if modo == 'L1' else 'en movimiento'})")
    print("=" * 72)
    print(f"  barrera: {formulacion}"
          + (f" (predictor τ_c = {tau_prediccion_s:.2f} s)"
             if formulacion == "F2" else "")
          + f", D_o = {D_OBSTACULO_M:.2f} m, término s/k; factor "
          f"{factor:.2f}; freno de respaldo "
          f"{'ACTIVO' if freno_activo else 'en SOMBRA'}")
    print("  ⚠ Una persona junto a la arena, lista para levantar al obstáculo.")
    if automatica:
        host_o, puerto_o = cfg.endpoint_robot(id_robot_obstaculo)
        print(f"  Colocación AUTOMÁTICA: los agentes van solos alrededor del "
              f"obstáculo quieto (robot {id_robot_obstaculo}, marcador "
              f"{id_marcador_obstaculo}, {host_o}:{puerto_o})"
              + ("; en la L1 va ENCENDIDO, conectado y frenado"
                 if modo == "L1" else "") + ".")
    print(f"  Reglas de parada AUTOMÁTICAS: contacto (< {UMBRAL_CONTACTO_M:.2f} m),"
          f" freno en {TOMAS_CON_FRENO_SEGUIDAS} tomas seguidas, aborto por el "
          f"obstáculo.")
    if campana is not None:
        est_c = campana.estado()
        print(f"  CAMPAÑA {campana.nombre!r}: {est_c['incluidas']}/{campana.meta} "
              f"tomas incluidas (mínimo {campana.minimo}), "
              f"{est_c['intentos_usados']}/{campana.tope} intentos usados; "
              f"hora de fin {campana.hora_fin:%H:%M}. La cobertura no se muestra.")
    if intento_inicial > 1:
        print(f"  REANUDACIÓN: arranca en el intento {intento_inicial} de "
              f"{intentos_max}; meta de esta sesión: {tomas} toma(s) válida(s). "
              f"La rampa vuelve en la 1.ª toma y la cuenta de frenos seguidos "
              f"arranca de cero.")

    # Marcadores vivos ANTES de abrir ningún enlace de ruedas. No se usa
    # `ctx.conectar()`: abriría las ruedas de `ctx.id_robot`, y en la L1 el
    # obstáculo está apagado.
    crudo = ses.ClientePosesCrudo()
    try:
        for marc in [cfg.MAPEO_AGENTES[i].id_marcador for i in range(n)] + [
                id_marcador_obstaculo]:
            congelado, _d, utiles = ses.stream_congelado(crudo, marc)
            if not utiles or congelado:
                return {"veredicto": "FALLO",
                        "detalle": f"marcador {marc} "
                                   f"{'congelado' if utiles else 'sin respuesta'}"}
    finally:
        crudo.cerrar()

    fuente, canal, entorno = construir_con_obstaculo(
        n, conectar_obstaculo=(modo == "L2" or automatica),
        id_robot_obstaculo=id_robot_obstaculo,
        id_marcador_obstaculo=id_marcador_obstaculo)
    atexit.register(canal.detener_todo)
    supervisor = SupervisorObstaculo(
        fuente, canal, modo="movil" if modo == "L2" else "quieto",
        freno_activo=freno_activo,
        quieto_conectado=(modo == "L1" and automatica))
    coord = CoordinadorConObstaculo(fuente, canal, entorno, n, 10,
                                    supervisor=supervisor,
                                    formulacion=formulacion,
                                    tau_prediccion_s=tau_prediccion_s)
    canal.factor_operativo = factor
    registro: List[Dict[str, Any]] = []
    trazas: List[Dict[str, Any]] = []
    estado: Dict[str, Any] = {"episodio": 0}
    coord._observador_paso = crear_observador(coord, canal, registro, estado)
    tomas_res: List[Dict[str, Any]] = []
    corridas: List[Dict[str, Any]] = []
    if campana is not None:
        # La cadena "freno en dos tomas seguidas" se arrastra con el libro.
        frenos_prev = campana.estado()["frenos_ultima_corrida"]
        if frenos_prev:
            corridas.append({"frenos": frenos_prev, "desde_el_libro": 1})
    detenida: Optional[str] = None

    def escribir_todo() -> None:
        for f in (*registro, *trazas, *tomas_res):
            f.setdefault("id_sesion", id_sesion)
        escribir_csv(rutas["decisiones"], registro)
        escribir_csv(rutas["obstaculo"], trazas)
        escribir_csv(rutas["tomas"], tomas_res)

    def cerrar_intento(fila: Dict[str, Any], semilla_: int) -> None:
        """Identifica la fila y, en campaña, la incluye o no y la anota."""
        fila.setdefault("id_sesion", id_sesion)
        fila.setdefault("semilla", semilla_)
        if campana is None:
            return
        incl, motivo_i = campana_inclusion(fila)
        fila.update({"campana": campana.nombre, "intento_campana": fila["toma"],
                     "incluida": incl, "motivo_inclusion": motivo_i})
        # El crudo de la toma va a disco ANTES de anotarla en el libro: el
        # libro nunca tiene un resultado sin su fila (auditoría final, 10-10).
        escribir_todo()
        previo_cierre = campana.cierre_por_seguridad
        campana.registrar(fila["toma"], semilla_, fila, rutas["tomas"].name)
        if campana.cierre_por_seguridad and not previo_cierre:
            # Criterio de seguridad de José (09-10): el libro cerró la
            # CAMPAÑA al anotar la segunda toma corrida con contacto.
            print("\n" + "⛔" * 3 + f" CAMPAÑA CERRADA — {campana.cierre_por_seguridad}")
            print("  Lo decidió el criterio fijado en el plan; no se corre ningún "
                  "intento más. Revisar los robots; lo ocurrido va a la "
                  "bitácora y al reporte.")

    def parar_y_cerrar(fila: Dict[str, Any], regla_: str,
                       semilla_: int) -> bool:
        """Anota el intento ANTES de la pausa de seguridad (el criterio de
        cierre lo cuenta aunque el proceso muera esperando la respuesta) y
        después pausa; la respuesta, también un Ctrl+C, va al libro en una
        fila aparte (revisiones del 08 y 10-10)."""
        cerrar_intento(fila, semilla_)
        try:
            seguir = aplicar_regla_de_parada(ctx, fuente, canal, regla_, fila)
        except BaseException:
            fila["parada_respuesta"] = "interrumpida (Ctrl+C) en la pausa"
            if campana is not None:
                campana.anotar_respuesta_pausa(fila["toma"], fila["parada_respuesta"])
            escribir_todo()
            raise
        if campana is not None:
            campana.anotar_respuesta_pausa(fila["toma"],
                                           fila.get("parada_respuesta", ""))
        escribir_todo()
        return seguir

    if campana is not None:
        from campana_obstaculo import inclusion_campana as campana_inclusion
        plan_intentos = campana.plan_de_intentos()
    else:
        plan_intentos = (
            (k, (SEMILLAS_LOTE[k - 1] if k <= len(SEMILLAS_LOTE)
                 else SEMILLAS_LOTE[0] + k - 1))
            for k in range(intento_inicial, intentos_max + 1))
    try:
        for intento, semilla in plan_intentos:
            if (campana is None
                    and sum(t.get("valido_demo", 0) for t in tomas_res) >= tomas):
                break
            if automatica:
                print(f"\n--- TOMA {intento} ---")
                col = _colocar_toma_automatica(
                    ctx, fuente, canal, n, modo, semilla, id_robot_obstaculo,
                    id_marcador_obstaculo)
                objetivo, rumbo = col["objetivo"], col["rumbo"]
                if col["parada"]:
                    fila = {"toma": intento, "semilla": semilla,
                            "id_sesion": id_sesion, "valido": 0,
                            "valido_demo": 0,
                            "motivo": f"colocación: {col['parada']}",
                            "regla_parada": col["parada"], **col["info"]}
                    tomas_res.append(fila)
                    seguir_ = parar_y_cerrar(fila, col["parada"], semilla)
                    if not seguir_:
                        detenida = col["parada"]
                        break
                    continue
                if col["problemas"]:
                    print("  ✘ no se arranca esta toma:")
                    for p_ in col["problemas"]:
                        print(f"      · {p_}")
                    tomas_res.append({"toma": intento, "valido": 0,
                                      "valido_demo": 0,
                                      "motivo": "; ".join(col["problemas"]),
                                      **col["info"]})
                    cerrar_intento(tomas_res[-1], semilla)
                    continue
                info_col = col["info"]
                poses_reg, pose_o_reg = col["poses_ini"], col["pose_o"]
            else:
                info_col = {"colocacion": "manual"}
                objetivo, rumbo = arranque_obstaculo(semilla, modo)
                blancos = sortear_blancos_demo(n, semilla, objetivo)
                print(f"\n--- TOMA {intento} ---")
                print(f"  OBSTÁCULO (robot {id_robot_obstaculo}): "
                      f"({objetivo[0]:.2f}, {objetivo[1]:.2f})"
                      + (f", rumbo {math.degrees(rumbo):+.0f}° (antihorario)"
                         if rumbo is not None else "")
                      + f" ±{TOL_COLOCACION_OBSTACULO_M * 100:.0f} cm")
                problemas = ["(sin colocar)"]
                for reintento in range(ses.REINTENTOS_COLOCACION + 1):
                    ses._esperar_reposicionamiento(
                        ctx, fuente, canal,
                        "  Colocá los agentes en sus blancos y el obstáculo en su "
                        "punto, y dale Enter.", blancos)
                    poses_ini = leer_poses_estables(fuente, n)
                    enlace_obst = ([] if canal.reintentar_enlace_obstaculo() else
                                   [f"enlace de ruedas del obstáculo (robot "
                                    f"{id_robot_obstaculo}) caído: ¿apagado o "
                                    f"sin batería?"])
                    problemas = (enlace_obst
                                 + revisar_poses_iniciales(poses_ini, n)
                                 + ses._marcadores_congelados_al_arrancar(fuente, n)
                                 + ses._enlaces_caidos_al_arrancar(canal)
                                 + problemas_obstaculo_al_arrancar(
                                     fuente, poses_ini, objetivo, rumbo))
                    if not problemas:
                        break
                    print("  ✘ no se arranca todavía:")
                    for p in problemas:
                        print(f"      · {p}")
                if problemas:
                    tomas_res.append({"toma": intento, "valido": 0,
                                      "valido_demo": 0,
                                      "motivo": "; ".join(problemas)})
                    cerrar_intento(tomas_res[-1], semilla)
                    continue
                poses_reg, pose_o_reg = poses_ini, fuente.pose_obstaculo()
            estado["episodio"] = intento
            decisiones_previas = canal.decisiones_enviadas
            enlace_antes = (canal.obstaculo_envios_fallidos,
                            canal.obstaculo_reconexiones)
            marca_toma = len(registro)
            try:
                res = correr_toma(coord, canal, fuente, entorno, semilla,
                                  decisiones, registro, rpm_aborto)
            except BaseException as exc:
                # Toma CORTADA A MITAD (Ctrl+C, caída): se frena, se arma su
                # fila con lo que alcanzó a correr y se ANOTA antes de
                # relanzar, para que el criterio de seguridad la cuente como
                # corrida (revisión del 10-10).
                canal.detener_todo(silencioso=True)
                res = fila_toma_cortada(coord, registro, marca_toma, semilla, exc)
                res.update({"toma": intento, "modo": modo, "factor": factor,
                            "obst_x0": float(objetivo[0]),
                            "obst_y0": float(objetivo[1]), **info_col})
                res.update(columnas_registro_toma(
                    poses_reg, pose_o_reg, id_robot_obstaculo,
                    id_marcador_obstaculo, decisiones_previas, rpm_aborto,
                    tau_prediccion_s, n))
                for f in supervisor.traza:
                    trazas.append({"toma": intento, **f})
                tomas_res.append(res)
                if res.get("decisiones") not in (None, ""):
                    corridas.append(res)
                res["regla_parada"] = ""
                cerrar_intento(res, semilla)
                raise
            # Una caída del enlace del obstáculo en la ÚLTIMA decisión, o en
            # la misma en que cortó otra regla, la tapa la reapertura de la
            # detención final (revisión 2026-10-03): se mira el contador.
            res["obst_enlace_cayo"] = int(
                (canal.obstaculo_envios_fallidos,
                 canal.obstaculo_reconexiones) != enlace_antes)
            res.update({"toma": intento, "modo": modo, "factor": factor,
                        "obst_x0": float(objetivo[0]),
                        "obst_y0": float(objetivo[1]), **info_col})
            res.update(columnas_registro_toma(
                poses_reg, pose_o_reg, id_robot_obstaculo,
                id_marcador_obstaculo, decisiones_previas, rpm_aborto,
                tau_prediccion_s, n))
            for f in supervisor.traza:
                trazas.append({"toma": intento, **f})
            tomas_res.append(res)
            # La línea de la toma dice POR QUÉ no vale: el motivo de la
            # medición si no es válida, el de la demo si lo es pero no sirve
            # para el video (antes un contacto salía "NO VÁLIDA" sin motivo).
            if res["valido_demo"]:
                rotulo = "VÁLIDA"
            elif not int(res.get("valido", 0) or 0):
                rotulo = f"NO VÁLIDA (medición: {res.get('motivo', '')})"
            else:
                rotulo = (f"NO VÁLIDA PARA LA DEMO "
                          f"({res.get('motivo_demo', '')})")
            try:
                d_txt = f"{float(res.get('d_min_obst_medida', '')):.4f} m"
            except (TypeError, ValueError):
                d_txt = "—"
            if campana is not None:
                incl_, motivo_i_ = campana_inclusion(res)
                ya = campana.estado()["incluidas"] + incl_
                rotulo += (f"  · INCLUIDA {ya}/{campana.meta}" if incl_
                           else f"  · NO INCLUIDA ({motivo_i_})")
                rotulo += f"  · video {'sí' if res['valido_demo'] else 'no'}"
            print(f"  >>> TOMA {intento}: {rotulo}  d_min obstáculo {d_txt}  "
                  f"frenos {res.get('frenos', 0)}")
            regla = regla_de_parada(res, corridas)
            # La cadena de frenos cuenta sólo las tomas que CORRIERON, con el
            # mismo criterio que el libro (`registrar`).
            if res.get("decisiones") not in (None, ""):
                corridas.append(res)
            res["regla_parada"] = regla or ""
            seguir_ = True
            if regla:
                seguir_ = parar_y_cerrar(res, regla, semilla)
            else:
                cerrar_intento(res, semilla)
            if not seguir_:
                detenida = regla
                break
    finally:
        canal.detener_todo()
        escribir_todo()
        entorno.finalizar()
    validas = sum(t.get("valido_demo", 0) for t in tomas_res)
    frenadas = sum(1 for t in tomas_res if t.get("frenos", 0))
    if campana is not None:
        est_c = campana.estado()
        detalle = (f"campaña {campana.nombre!r}: {est_c['incluidas']}/"
                   f"{campana.meta} incluidas (mínimo {campana.minimo}), "
                   f"{est_c['intentos_usados']}/{campana.tope} intentos; esta "
                   f"sesión {len(tomas_res)} intentos, {frenadas} con freno de "
                   f"respaldo; fin de sesión: "
                   f"{getattr(campana, 'motivo_fin', '') or ('regla de parada' if detenida else '')}")
    else:
        detalle = (f"{validas}/{tomas} tomas válidas en {len(tomas_res)} "
                   f"intentos; {frenadas} con intervención del freno de "
                   f"respaldo")
    if detenida:
        detalle += f"; DETENIDA por regla de parada: {detenida}"
    print(f"\n>>> {modo}: {detalle}")
    if campana is not None:
        veredicto = "DETENIDA" if detenida else campana.veredicto()
    else:
        veredicto = ("DETENIDA" if detenida
                     else "OK" if validas >= tomas else "INCOMPLETA")
    return {"veredicto": veredicto, "detalle": detalle, "tomas": tomas_res,
            "id_sesion": id_sesion, "rutas": {k: str(v) for k, v in rutas.items()}}


def fila_toma_cortada(coord: Any, registro: Sequence[Dict[str, Any]],
                      marca: int, semilla: int, exc: BaseException) -> Dict[str, Any]:
    """
    La fila de una toma CORTADA A MITAD (una excepción dentro de
    `correr_toma`: Ctrl+C, enlace, etapa), con lo que alcanzó a correr:
    las decisiones del registro, la distancia mínima al obstáculo que el
    coordinador fue midiendo y los pares de agentes a < 0.15 m por decisión.
    No válida para la medición; para el criterio de cierre es una toma
    corrida (revisión del 10-10).
    """
    por_paso: Dict[Any, Dict[int, Tuple[float, float]]] = {}
    for f in registro[marca:]:
        por_paso.setdefault(f["paso"], {})[int(f["agente"])] = (
            float(f["pose_env_x"]), float(f["pose_env_y"]))
    pares: Set[Tuple[int, int]] = set()
    for pts in por_paso.values():
        ids = sorted(pts)
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                if math.dist(pts[ids[a]], pts[ids[b]]) < 0.15:
                    pares.add((ids[a], ids[b]))
    res: Dict[str, Any] = {
        "valido": 0, "semilla": semilla, "lazo": "evaluacion",
        "motivo": f"toma CORTADA a mitad ({type(exc).__name__}: {exc})"[:300],
        "decisiones": len(por_paso) or "", "colisiones_015": len(pares),
        "toma_cortada": 1,
    }
    res.update(coord.resumen_obstaculo())
    res["valido_demo"], res["motivo_demo"] = 0, "toma cortada a mitad"
    return res


def columnas_registro_toma(poses_ini: Dict[int, Any], pose_o: Optional[Any],
                           id_robot_obstaculo: int, id_marcador_obstaculo: int,
                           decisiones_previas: int, rpm_aborto: float,
                           tau_prediccion_s: float, n: int) -> Dict[str, Any]:
    """
    Lo que la RÉPLICA pareada necesita de una toma, como en los episodios del
    30-09 (campaña L2, OK de José del 2026-10-08). Por agente, el MISMO
    bloque de `sesion_robotat.sesion_evaluacion` (sesion_robotat.py:
    2209-2222), con las mismas llamadas y el mismo redondeo (hay prueba por
    `ast` de que da lo mismo bit a bit): robot, offset de rumbo y su origen,
    y la pose inicial MEDIDA (la que validaron los chequeos de arranque).
    Del obstáculo: robot, marcador, offset, origen y su pose inicial MEDIDA
    (`obst_x0/obst_y0` son el OBJETIVO). Del régimen: `rpm_aborto`,
    `tau_prediccion_s` y `decisiones_previas` (el contador del canal antes de
    la toma: la rampa). Sólo registro.
    """
    res: Dict[str, Any] = {}
    for i in range(n):
        rid = cfg.MAPEO_AGENTES[i].id_robot
        res[f"robot_a{i}"] = rid
        res[f"offset_deg_a{i}"] = round(
            math.degrees(cfg.offset_rumbo_de_robot(rid)), 4)
        res[f"offset_origen_a{i}"] = cfg.origen_offset_rumbo(rid)
        if i in poses_ini:
            res[f"x0_a{i}"] = float(poses_ini[i][0])
            res[f"y0_a{i}"] = float(poses_ini[i][1])
            res[f"th0_a{i}"] = float(poses_ini[i][2])
    res["obst_robot"] = int(id_robot_obstaculo)
    res["obst_marcador"] = int(id_marcador_obstaculo)
    res["obst_offset_deg"] = round(
        math.degrees(cfg.offset_rumbo_de_robot(id_robot_obstaculo)), 4)
    res["obst_offset_origen"] = cfg.origen_offset_rumbo(id_robot_obstaculo)
    if pose_o is not None:
        res["obst_x0_med"] = float(pose_o[0])
        res["obst_y0_med"] = float(pose_o[1])
        res["obst_th0_med"] = float(pose_o[2])
    res["rpm_aborto"] = rpm_aborto
    res["tau_prediccion_s"] = tau_prediccion_s
    res["decisiones_previas"] = int(decisiones_previas)
    return res


def _vaciar_teclado() -> None:
    """
    Descarta lo que se haya tecleado de más antes de un Enter que AUTORIZA
    movimiento autónomo (revisión: un Enter de más dejado en el búfer lo
    contestaba solo). Sólo con una consola real.
    """
    try:
        if not sys.stdin.isatty():
            return
        if sys.platform.startswith("win"):
            import msvcrt
            while msvcrt.kbhit():
                msvcrt.getwch()
        else:
            import termios
            termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception:                                          # noqa: BLE001
        pass


def _colocar_toma_automatica(ctx: Any, fuente: Any, canal: Any, n: int,
                             modo: str, semilla: int, id_robot_obstaculo: int,
                             id_marcador_obstaculo: int) -> Dict[str, Any]:
    """
    La colocación AUTOMÁTICA de una toma (Fase B de la propuesta), con los
    reintentos de `sesion_robotat` (no gastan el intento). Devuelve
    `objetivo`, `rumbo`, `info` (columnas del CSV), `problemas` (vacía si se
    arranca) y `parada` (texto de la regla de parada, o "").
    """
    import sesion_robotat as ses
    import colocacion_con_obstaculo as C
    from adaptadores_robotat import revisar_poses_iniciales
    from colocacion_autonoma import sortear_rumbos
    from lanzar_robotat import leer_poses_estables
    host, puerto = cfg.endpoint_robot(id_robot_obstaculo)
    rumbos = sortear_rumbos(n, semilla)
    info: Dict[str, Any] = {"colocacion": "auto", "col_reintentos": 0}
    sentidos: Dict[int, int] = {}
    alejar: List[int] = []
    objetivo: np.ndarray = np.array(PUNTO_L1_ENV, dtype=np.float64)
    rumbo: Optional[float] = None
    problemas: List[str] = ["(sin colocar)"]
    for reintento in range(ses.REINTENTOS_COLOCACION + 1):
        info["col_reintentos"] = reintento
        # ── antes de mover a nadie: enlaces vivos ──────────────────────
        previos = (([] if canal.reintentar_enlace_obstaculo() else
                    [f"enlace de ruedas del obstáculo (robot "
                     f"{id_robot_obstaculo}) caído: ¿apagado o sin batería?"])
                   + ses._enlaces_caidos_al_arrancar(canal))
        # ── el obstáculo: QUIETO (al terminar una toma sigue andando hasta
        # su retardo), dónde está y dónde arranca ──────────────────────
        pose_ref: Optional[np.ndarray] = None
        fuera: List[str] = []
        if not previos:
            tipo_q, motivo_q, pose_ref = C.esperar_obstaculo_quieto(
                fuente, canal, n)
            if tipo_q in ("mueve", "enlace"):
                parada = f"ABORTO POR EL OBSTÁCULO: {motivo_q}"
                return {"objetivo": objetivo, "rumbo": rumbo, "info": info,
                        "problemas": [parada], "parada": parada}
            if tipo_q is not None:
                fuera.append(motivo_q)
        pose_o = pose_ref
        objetivo, rumbo, origen = C.objetivo_obstaculo(modo, pose_o, semilla)
        if not fuera and not previos:
            fuera = C.problemas_envolvente_obstaculo(modo, pose_o)
        if previos or fuera:
            for p_ in previos + fuera:
                print(f"      · {p_}")
            if fuera:
                # Sin la Fase A, el obstáculo fuera de su envolvente se
                # coloca A MANO (los agentes, después, solos).
                print(f"  OBSTÁCULO (robot {id_robot_obstaculo}): colocalo A "
                      f"MANO en ({objetivo[0]:.2f}, {objetivo[1]:.2f})"
                      + (f", rumbo {math.degrees(rumbo):+.0f}° (tangente "
                         f"antihoraria) ±{math.degrees(C.ENVOLVENTE_RUMBO_RAD):.0f}°, "
                         f"a ±{C.ENVOLVENTE_RADIAL_M * 100:.0f} cm del círculo"
                         if rumbo is not None else
                         f" ±{TOL_COLOCACION_OBSTACULO_M * 100:.0f} cm")
                      + ".")
            problemas = previos + fuera
            if reintento < ses.REINTENTOS_COLOCACION:
                ses._esperar_reposicionamiento(
                    ctx, fuente, canal,
                    "  Corregí lo de arriba y dale Enter (Ctrl+C corta).", None)
            continue
        # Separación desde el punto MEDIDO del obstáculo, no del objetivo.
        blancos = C.sortear_blancos_lejos(n, semilla, pose_o[:2])
        info.update({"col_obst_origen": origen,
                     "col_obst_x": round(float(objetivo[0]), 4),
                     "col_obst_y": round(float(objetivo[1]), 4)})
        for i in range(n):
            info[f"blanco_x_a{i}"] = round(float(blancos[i][0]), 4)
            info[f"blanco_y_a{i}"] = round(float(blancos[i][1]), 4)
            info[f"blanco_th_a{i}"] = round(float(rumbos[i]), 4)
        print(f"  OBSTÁCULO (robot {id_robot_obstaculo}) QUIETO en "
              f"({objetivo[0]:.2f}, {objetivo[1]:.2f})"
              + (f", rumbo {math.degrees(rumbo):+.0f}°" if rumbo is not None
                 else "") + f" ({origen}).")
        _vaciar_teclado()
        ses._esperar_reposicionamiento(
            ctx, fuente, canal,
            f"  Los agentes van a ir SOLOS a estos blancos, alrededor del "
            f"obstáculo (robot {id_robot_obstaculo}, marcador "
            f"{id_marcador_obstaculo}, {host}:{puerto}). Una persona junto a "
            f"la arena: despejala y dale Enter (Ctrl+C corta).", blancos)
        inf = C.colocar_alrededor_del_obstaculo(
            fuente, canal, blancos, rumbos, n, sentidos_previos=sentidos,
            alejar=alejar, pose_obstaculo_ref=pose_ref)
        info.update(inf.como_fila(n))
        if inf.parada:
            return {"objetivo": objetivo, "rumbo": rumbo, "info": info,
                    "problemas": [inf.parada], "parada": inf.parada}
        # El reintento tiene que cambiar algo: el que no avanzó rodea por
        # el otro lado o, si no rodeaba, primero se aleja 10 cm.
        alejar = []
        for i, m in inf.abandonados.items():
            if m == "no avanza":
                if i in inf.sentidos:
                    sentidos[i] = -inf.sentidos[i]
                else:
                    alejar.append(i)
        poses_ini = leer_poses_estables(fuente, n)
        pose_o = fuente.pose_obstaculo()
        problemas = (([] if canal.reintentar_enlace_obstaculo() else
                      [f"enlace de ruedas del obstáculo (robot "
                       f"{id_robot_obstaculo}) caído"])
                     + revisar_poses_iniciales(poses_ini, n)
                     + ses._marcadores_congelados_al_arrancar(fuente, n)
                     + ses._enlaces_caidos_al_arrancar(canal)
                     + problemas_obstaculo_al_arrancar(fuente, poses_ini,
                                                       objetivo, rumbo)
                     + C.problemas_tras_colocar(inf, poses_ini, blancos, modo,
                                                pose_o, n))
        if not problemas:
            return {"objetivo": objetivo, "rumbo": rumbo, "info": info,
                    "problemas": [], "parada": "", "poses_ini": poses_ini,
                    "pose_o": pose_o}
        print("  ✘ no se arranca todavía:")
        for p_ in problemas:
            print(f"      · {p_}")
        if reintento < ses.REINTENTOS_COLOCACION:
            print(f"  (no se gasta el intento: corregí lo que impide moverse "
                  f"y dale Enter; después se vuelven a colocar solos — "
                  f"reintento {reintento + 1}/{ses.REINTENTOS_COLOCACION})")
    return {"objetivo": objetivo, "rumbo": rumbo, "info": info,
            "problemas": problemas, "parada": ""}


#: Banderas cuyo valor fija el plan de la campaña: sin campaña, estos son
#: los valores por defecto; con campaña, darlas (aunque sea con este valor)
#: se rechaza, igual que --forzar (revisión del 08-10).
BANDERAS_DEL_PLAN: Dict[str, Any] = {
    "tomas": 3, "intentos": 6, "intento_inicial": 1, "decisiones": 500,
    "factor": 0.40, "colocacion": "auto",
}
#: Una sesión de campaña dura a lo sumo esto (la hora de fin puede cruzar la
#: medianoche, pero no es "mañana a la tarde" por error).
HORA_FIN_MAX_H: float = 12.0


def main(argv: Optional[List[str]] = None) -> int:
    import calibracion_sesion as calib
    import sesion_robotat as ses
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--modo", choices=("L0", "L1", "L2"), required=True)
    # Default None: así se sabe si se DIERON (el modo campaña las rechaza;
    # sin campaña toman los valores de BANDERAS_DEL_PLAN).
    ap.add_argument("--tomas", type=int, default=None, help="por defecto 3")
    ap.add_argument("--intentos", type=int, default=None, help="por defecto 6")
    ap.add_argument("--decisiones", type=int, default=None,
                    help="por defecto 500")
    ap.add_argument("--factor", type=float, default=None,
                    help="por defecto 0.40")
    ap.add_argument("--arranques", type=int, default=10, help="L0")
    # Obligatorio desde el 2026-10-07: el 7 lo usa otro compañero y la
    # colocación automática mueve robots; un default no puede elegirlo.
    ap.add_argument("--robot-obstaculo", type=int, required=True,
                    help="robot del obstáculo, OBLIGATORIO (hoy el 4; "
                         "marcador = robot)")
    ap.add_argument("--colocacion", choices=("auto", "manual"),
                    default=None,
                    help="L1/L2: los agentes van solos alrededor del "
                         "obstáculo quieto (auto, por defecto) o a mano")
    # ── campaña de medición L2 (2026-10-08, OK de José) ──
    ap.add_argument("--campana", default=None,
                    help="L2: nombre de la campaña de medición (libro en "
                         "resultados_demo_obstaculo/campanas/<nombre>/)")
    ap.add_argument("--crear-campana", action="store_true",
                    help="crea la campaña (congela el sha256 de los archivos)")
    ap.add_argument("--hora-fin", default=None,
                    help="campaña: HH:MM, fijada ANTES de empezar la sesión")
    ap.add_argument("--meta", type=int, default=50, help="al crear: incluidas")
    ap.add_argument("--minimo", type=int, default=30, help="al crear")
    ap.add_argument("--tope-intentos", type=int, default=100, help="al crear")
    ap.add_argument("--corregir-campana", default=None, metavar="MOTIVO",
                    help="deja en el libro el hash nuevo de los archivos "
                         "congelados, con el motivo")
    ap.add_argument("--cerrar-campana", default=None, metavar="MOTIVO")
    ap.add_argument("--liberar-candado", default=None, metavar="MOTIVO")
    ap.add_argument("--intento-inicial", type=int, default=None,
                    help="L1/L2: reanudar una sesión cortada en este intento "
                         "(siguen sus semillas y la cuenta contra --intentos)")
    ap.add_argument("--simulador", action="store_true")
    ap.add_argument("--forzar", action="store_true")
    args = ap.parse_args(argv)
    args.dadas = [b for b in BANDERAS_DEL_PLAN if getattr(args, b) is not None]
    for b, v in BANDERAS_DEL_PLAN.items():
        if getattr(args, b) is None:
            setattr(args, b, v)

    # Marcador N ↔ robot N, la asignación de la plataforma (config_robotat).
    robot_obst = int(args.robot_obstaculo)
    marcador_obst = cfg.marcador_fijo_de_robot(robot_obst)
    if args.simulador:
        cfg.activar_simulador_local()
        print("[demo] modo SIMULADOR: no hay hardware involucrado.")
    campana = None
    if args.campana is not None:
        r_c = _preparar_campana(args, robot_obst, marcador_obst)
        if not isinstance(r_c, tuple):
            return r_c                    # comando de libro o error: código
        campana, id_sesion = r_c
    # Con la sesión de campaña ya abierta (candado tomado), lo que sigue va
    # dentro del try/finally que la cierra: un error al preparar (enlace de
    # un robot, calibración faltante) no puede dejar el candado huérfano.
    motivo_cierre = "fin de la sesión"
    try:
        ctx = ses.Contexto(sesion=f"demo_{args.modo}", id_robot=robot_obst,
                           marcador=marcador_obst, forzar=args.forzar,
                           simulador=args.simulador)
    except BaseException:
        if campana is not None:
            campana.cerrar_sesion("error al crear el contexto")
        raise
    if (args.modo != "L0" and not args.simulador and not args.forzar
            and campana is None):
        ok_l0, motivo_l0 = l0_habilita(robot_obst)
        print(f"[demo] L0 del robot {robot_obst}: {motivo_l0}")
        if not ok_l0:
            print("\n✘ No se arranca: la L1/L2 exige una L0 OK del robot del "
                  "obstáculo con el offset de rumbo a ≤ 3° de la tabla "
                  "(--forzar lo saltea).")
            return 6
    try:
        ses._preparar(ctx)
        faltan = calib.faltantes()
        if faltan and not args.forzar and args.modo != "L0":
            print("\n✘ Faltan parámetros de calibración:", faltan)
            motivo_cierre = "faltan parámetros de calibración"
            return 3
        if args.modo == "L0":
            r = sesion_l0(ctx, arranques=args.arranques,
                          id_robot=robot_obst, id_marcador=marcador_obst)
        else:
            r = sesion_demo(ctx, args.modo, tomas=args.tomas,
                            intentos_max=args.intentos,
                            decisiones=args.decisiones, factor=args.factor,
                            id_robot_obstaculo=robot_obst,
                            id_marcador_obstaculo=marcador_obst,
                            intento_inicial=args.intento_inicial,
                            colocacion=args.colocacion,
                            campana=campana,
                            id_sesion=(id_sesion if campana is not None
                                       else None))
        if campana is not None:
            return 0 if r["veredicto"] in ("META", "MÍNIMO", "INCOMPLETA") else 1
        return 0 if r["veredicto"] == "OK" else 1
    except KeyboardInterrupt:
        print("\n[demo] interrumpida por el usuario.")
        motivo_cierre = "interrumpida (Ctrl+C)"
        return 130
    except (OSError, ses.AbortoEtapa) as exc:
        # OSError cubre ConnectionError y los timeouts de socket, al abrir o
        # con la sesión en marcha: el traceback queda para diagnosticar.
        import traceback
        traceback.print_exc()
        print(f"\n[demo] ✘ error de conexión o de etapa: {exc}")
        motivo_cierre = f"error de conexión o de etapa: {exc}"[:300]
        return 5
    finally:
        try:
            ctx.detener_todo()
            ctx.cerrar()
        finally:
            if campana is not None:
                campana.cerrar_sesion(motivo_cierre)


def ultima_l0(id_robot: int, carpeta: Optional[Path] = None) -> Dict[str, Any]:
    """La fila del último `_L0_resumen.csv` del robot (para el libro)."""
    carpeta = carpeta or DIR_SALIDA_DEMO
    ultima: Dict[str, Any] = {}
    for ruta in sorted(carpeta.glob("*_L0_resumen*.csv")):
        try:
            with open(ruta, newline="", encoding="utf-8") as fh:
                for f in csv.DictReader(fh):
                    if (str(f.get("robot")) == str(int(id_robot))
                            and not _l0_del_simulador(f)):
                        ultima = {"archivo": ruta.name, **f}
        except OSError:
            continue
    return ultima


def _preparar_campana(args: Any, robot_obst: int,
                      marcador_obst: int) -> Any:
    """
    Los comandos del libro (crear, corregir, cerrar, liberar el candado) y la
    apertura de la sesión de campaña. Devuelve un código de salida (int) si
    no hay que correr la sesión, o (campana, id_sesion).
    """
    import campana_obstaculo as CO
    plataforma = "simulador" if args.simulador else "hw"
    base = DIR_SALIDA_DEMO
    try:
        if args.corregir_campana is not None:
            cambiaron = CO.Campana.corregir(base, args.campana,
                                            args.corregir_campana)
            print(f"[campaña] corrección anotada en el libro; cambiaron: "
                  f"{', '.join(cambiaron) or 'ninguno'}")
            return 0
        if args.cerrar_campana is not None:
            CO.Campana.cerrar(base, args.campana, args.cerrar_campana)
            print(f"[campaña] {args.campana!r} CERRADA: {args.cerrar_campana}")
            return 0
        if args.liberar_candado is not None:
            if CO.Campana.liberar_candado(base, args.campana, args.liberar_candado):
                print("[campaña] candado liberado (anotado en el libro, con "
                      "las reservas sin resultado marcadas interrumpidas)")
            else:
                print("[campaña] no había candado: no se anotó nada")
            return 0
        if args.modo != "L2":
            print("✘ La campaña de medición es de la L2.")
            return 2
        # La calibración guardada se aplica ANTES de mirar la L0 y de abrir:
        # así el libro anota los offsets EFECTIVOS (`_preparar` la vuelve a
        # aplicar; es idempotente).
        import calibracion_sesion as calib
        calib.aplicar_a_config()
        # La L0 OK y la corrección del offset del 4 van ANTES de abrir la
        # campaña (decisión de José): sin L0 OK no se crea ni se abre. Sólo
        # el simulador la saltea; --forzar NO.
        l0 = {}
        if not args.simulador:
            ok_l0, motivo_l0 = l0_habilita(robot_obst)
            print(f"[campaña] L0 del robot {robot_obst}: {motivo_l0}")
            if not ok_l0:
                print("✘ La campaña exige una L0 OK del robot del obstáculo "
                      "con el offset a ≤ 3° de la tabla.")
                return 6
            l0 = ultima_l0(robot_obst)
        if args.crear_campana:
            c = CO.Campana.crear(base, args.campana, plataforma, robot_obst,
                                 marcador_obst, meta=args.meta,
                                 minimo=args.minimo, tope=args.tope_intentos)
            print(f"[campaña] creada {c.nombre!r} en {c.carpeta} (meta "
                  f"{c.meta}, mínimo {c.minimo}, tope {c.tope}); archivos "
                  f"congelados con su sha256 en campana.json")
            return 0
        dadas = getattr(args, "dadas", [])
        if dadas or args.forzar:
            nombres = [f"--{b.replace('_', '-')}" for b in dadas]
            nombres += ["--forzar"] if args.forzar else []
            print(f"✘ Con --campana no se usa {', '.join(nombres)}: los intentos "
                  f"los decide el libro y el régimen (500 decisiones, factor "
                  f"0.40, colocación automática) lo fija el plan.")
            return 2
        if not args.hora_fin:
            print("✘ La campaña exige --hora-fin HH:MM, fijada antes de empezar.")
            return 2
        try:
            hh, mm = (int(x) for x in args.hora_fin.split(":"))
            ahora = datetime.now()
            hora_fin = ahora.replace(hour=hh, minute=mm, second=0, microsecond=0)
        except ValueError:
            print(f"✘ --hora-fin {args.hora_fin!r}: formato HH:MM")
            return 2
        if hora_fin <= ahora:                     # cruza la medianoche
            hora_fin += timedelta(days=1)
        if (hora_fin - ahora).total_seconds() > HORA_FIN_MAX_H * 3600:
            cuando = f"{hora_fin:%Y-%m-%d %H:%M}"
            print(f"✘ --hora-fin {args.hora_fin}: sería el {cuando}, a más de "
                  f"{HORA_FIN_MAX_H:.0f} h; ¿es la hora correcta?")
            return 2
        print(f"[campaña] hora de fin de la sesión: {hora_fin:%Y-%m-%d %H:%M}")
        c = CO.Campana(CO.Campana.carpeta_de(base, args.campana))
        id_sesion = f"L2_{datetime.now():%Y%m%d_%H%M%S}"
        c.abrir_sesion(plataforma, robot_obst, hora_fin, id_sesion, l0=l0,
                       script=Path(__file__).resolve())
        return c, id_sesion
    except CO.ErrorCampana as exc:
        print(f"✘ [campaña] {exc}")
        return 7


if __name__ == "__main__":
    sys.exit(main())
