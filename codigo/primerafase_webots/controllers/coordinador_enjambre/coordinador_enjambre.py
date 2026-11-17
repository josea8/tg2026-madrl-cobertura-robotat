"""
coordinador_enjambre.py
=======================
Coordinador central del enjambre multi-robot con física real (Webots R2025a).
Corre en un nodo Robot SIN geometría, con `supervisor TRUE`.

Arquitectura (impuesta por Webots)
----------------------------------
Un controlador sólo puede comandar los motores de SU PROPIO robot, así que el
patrón de supervisor único del demo de 1 robot no escala. En su lugar:

  - N nodos Pololu, cada uno con `controlador_agente` (NO supervisores):
    publican su pose cada tick y ejecutan el (v, ω) que reciben.
  - 1 coordinador (este archivo, supervisor): corre el env, la política y
    mueve las esferas de hotspots.

El número de agentes se AUTODETECTA contando nodos `DEF p3pi_i`, de modo que
el mismo controlador sirve para los mundos de 2 y de 5 sin editar constantes
(elimina un punto de sincronización manual entre .wbt y controlador).

Responsabilidades
-----------------
  1. Mantener un CACHÉ con la última pose conocida de cada agente y su tick.
  2. Cada `pasos_por_decision` ticks: inyectar las poses al env, obtener las N
     acciones con la política y difundirlas en UN mensaje.
  3. Avanzar el env (mueve hotspots y AoI) y publicar las esferas a Webots.
  4. Instrumentar la sincronía (antigüedad de poses, latencia, decisiones con
     pose vieja) desde el arranque.
  5. Diagnosticar los atascos: al detectarse uno, registrar si había un vecino
     dentro de `comm_radius` y cuál era la acción comandada justo antes.
  6. Modo lote: N episodios headless con volcado a CSV.

El coordinador NUNCA se bloquea esperando poses dentro de un episodio: usa la
más reciente que tenga. Sólo espera —con tope— al reiniciar un episodio.

Política de poses faltantes o viejas
------------------------------------
  - Usa la pose más reciente de cada agente.
  - Antigüedad = tick_actual − tick_emision por agente.
  - Si supera UMBRAL_ANTIGUEDAD_TICKS, incrementa un contador y avisa.
  - Si NUNCA recibió pose de un agente, aborta con error explícito: es un
    fallo de configuración, no una condición de operación.

Nota sobre el lag estructural
-----------------------------
Webots no garantiza el orden de ejecución entre controladores dentro de un
tick, así que un mensaje emitido en el tick T se lee en T o T+1. Una
antigüedad de 0-1 ticks es NORMAL, no un fallo; por eso el umbral de aviso
está en 2. La misma estructura ("usá la última pose conocida") aplicará en el
Robotat con la latencia de OptiTrack + red.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import atexit
import csv
import math
import sys
import warnings
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

from stable_baselines3 import PPO

# `controller` y `adaptadores_webots` sólo existen dentro de Webots, y se
# importan de forma perezosa en `_construir_adaptadores_webots`. Fuera de
# Webots —el lanzador del Robotat, las pruebas del puente— este módulo debe
# poder importarse igual: el lazo de control no depende de Webots desde la
# Fase 1, y un import de nivel de módulo lo volvería a atar.
from interfaces import (
    CanalActuacion,
    EntornoEjecucion,
    FuentePoses,
    PoseMedida,
)
from lib.swarm_env_skeleton import CyanobacteriaMonitoringEnv
from protocolo import (
    CANAL_BAJADA,
    CANAL_SUBIDA,
    OFFSET_PROTO_RAD,
    desempaquetar_pose,
    empaquetar_acciones,
    empaquetar_reset,
    env_a_webots_xy,
)


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Tope de sondeo para autodetectar agentes (DEF p3pi_0, p3pi_1, ...).
MAX_AGENTES_SONDEO: int = 20

ARENA_SIZE:   Tuple[float, float] = (3.0, 3.0)
MAX_STEPS_EP: int   = 500
COMM_RADIUS:  float = 1.0
DT_ENV:       float = 0.1
N_HOTSPOTS:   int   = 3
SEMILLA:      int   = 42
DOMAIN_RAND:  bool  = False

# `modo_borde` NO aplica: el env corre con modo_poses_externas=True, donde la
# rama de bordes ni se ejecuta (las paredes las impone la física de Webots).
MODO_POSES_EXTERNAS: bool = True

NOMBRE_MODELO: str  = "modelo_sanidad"
RUTA_MODELO:   Path = _CARPETA / "modelos" / f"{NOMBRE_MODELO}.zip"

# ── Sincronía ────────────────────────────────────────────────────────────
UMBRAL_ANTIGUEDAD_TICKS: int   = 2
PERIODO_LOG_S:           float = 5.0

# ── Umbrales de colisión ─────────────────────────────────────────────────
# 0.15 m entre centros = CONTACTO FÍSICO de los chasis (radio 0.075 c/u).
#   Es el D_SAFE del env y el umbral con el que se midieron TODAS las
#   métricas previas (experimentos A-D y sanidad) ⇒ es el comparable.
# 0.22 m = margen operativo de la metodología de tesis (~7 cm de holgura).
UMBRAL_COLISION_CONTACTO: float = 0.15
UMBRAL_COLISION_MARGEN:   float = 0.22

# ── Filtro CBF de ejecución (safety shield) ──────────────────────────────
# Se interpone entre la política y los motores. Con el flag en False el
# módulo ni se importa (regresión cero). Barreras: 4 de pared (del módulo) +
# (N−1) robot-robot por agente, inyectadas vía `restricciones_extra`.
CBF_ACTIVO: bool = True

ELE_A:          float = 0.05   # ℓa, adelanto del punto de mira [m]
ALFA_CBF:       float = 2.0    # α, ganancia clase-K [1/s]
D_SEGURA_PUNTO: float = 0.18   # margen del punto de mira a la pared [m]
W_OMEGA:        float = 0.3    # peso de ω en el costo (girar antes que frenar)

# Distancia de seguridad ENTRE PUNTOS DE MIRA para la barrera robot-robot.
# Los puntos de mira están ℓa por delante de cada centro, así que en el peor
# caso (ambos robots enfrentados) la distancia entre centros es la distancia
# entre puntos de mira MÁS 2·ℓa... y en el caso contrario, MENOS 2·ℓa.
# Para garantizar centros ≥ 0.15 m (contacto de chasis) hay que exigir
# puntos de mira ≥ 0.15 + 2·ℓa = 0.25 m.
D_SEGURA_ROBOTS: float = 0.25

# =============================================================================
# EXPERIMENTO F — DEGRADACIÓN DE POSE (ruido + latencia)
# =============================================================================
# Objetivo: determinar el umbral de tolerancia del sistema ANTES de entrar al
# laboratorio, para saber si hace falta filtrado de pose y/o reducir la
# latencia del lazo.
#
# SEPARACIÓN CRÍTICA — poses degradadas vs poses reales:
#   - Las poses DEGRADADAS van al env y al filtro CBF. Es lo que el sistema
#     "cree" que está pasando, igual que en el laboratorio.
#   - TODAS las métricas físicas (colisiones, d_min a pared, detector de
#     atasco, violaciones del margen) se calculan con las poses REALES del
#     GPS, porque miden lo que efectivamente ocurrió.
#   Sin esta separación el experimento mediría el error de medición en vez de
#   la seguridad: con σ=20 mm dos robots realmente a 0.16 m podrían "verse" a
#   0.12 m y registrar una colisión que no existió.
#
# RUIDO. Gaussiano independiente por medición (cada tick), como un OptiTrack
# real, aplicado en `_drenar_poses`. El ruido de heading está ACOPLADO al de
# posición por la relación geométrica
#       σ_θ = σ_pos · √2 / L_MARCADORES
# porque OptiTrack no mide heading directamente: lo estima de la constelación
# de marcadores, así que el error angular queda determinado por el posicional
# dividido por la separación entre marcadores. Barrerlos por separado mediría
# un régimen que el laboratorio no produce (no existe 20 mm de error posicional
# con heading perfecto).
#
#   ATENCIÓN AL INTERPRETAR: los umbrales deben enunciarse como "σ_pos con
#   constelación L = 0.15 m", NO como σ_pos a secas — con otra constelación el
#   mismo error posicional produce otro error angular.
#
#   Esta escala es ~3× MÁS AGRESIVA en ángulo que la del DomainRandomizer del
#   entrenamiento (que a 10 mm usaba 0.030 rad = 1.7°; acá 10 mm → 5.4°). Es
#   deliberado: se busca el umbral de ruptura, no reproducir el entrenamiento.
#
# LATENCIA. Cola por agente de `retardo_extra + 1` poses tomadas en cada
# DECISIÓN; el coordinador usa la más vieja. Con 0 el comportamiento es
# idéntico al actual. Se suma al tick estructural ya existente, así que la
# latencia total es 10 ms + retardo_extra × 100 ms.
#
# Con SIGMA_POS_M = 0 y RETARDO_EXTRA = 0 la degradación es un no-op exacto.

SIGMA_POS_M:              float = 0.0     # σ del ruido de posición [m]
RETARDO_EXTRA_DECISIONES: int   = 0      # decisiones de retardo adicional
L_MARCADORES:             float = 0.15   # baseline de la constelación [m]

# Barrido factorial del Experimento F. Con MODO_BARRIDO=True, `correr_lote`
# recorre las 12 configuraciones (4 niveles de ruido × 3 de latencia) sobre
# las mismas 18 semillas, en UNA sola sesión de Webots.
#   "off"    → lote simple con la configuración vigente.
#   "ruido"  → Experimento F: 4 niveles de σ × 3 de retardo.
#   "filtro" → Experimento G: barrido de parámetros del CBF (ver abajo).
MODO_BARRIDO: str = "off"
BARRIDO_SIGMAS:   Tuple[float, ...] = (0.000, 0.005, 0.010, 0.020)
BARRIDO_RETARDOS: Tuple[int, ...]   = (0, 1, 3)

# ── EXPERIMENTO G — barrido de parámetros del filtro ─────────────────────
# Objetivo: encontrar una configuración del CBF que NO produzca bloqueo, para
# tener un sistema SANO sobre el cual medir robustez de verdad (el Exp F midió
# la perturbación de un equilibrio patológico, no tolerancia al ruido).
#
# Las palancas NO son d_s: los atascos ocurren EN el margen (33/39 a d≈0.18) y
# en esquinas (16/17), así que ampliar el margen sólo muda el equilibrio y
# agranda la región excluida en esquinas. Las palancas son:
#
#   ℓa  (adelanto del punto de mira) — el coeficiente de ω en la restricción
#       es proporcional a ℓa: c = (n·heading, ℓa·n·perp(heading)). Más ℓa =
#       más autoridad de giro, conjunto factible más ancho en la dirección ω.
#   w_ω (peso de ω en el costo) — menor w_ω hace que el QP prefiera GIRAR
#       antes que FRENAR. Ataca directamente el "se detiene de frente".
#
# α queda FIJO en 2.0: en el equilibrio (h ≈ 0) la condición es c·u ≥ 0
# independientemente de α, así que α no mueve el punto fijo (sólo la velocidad
# de aproximación con h > 0).
#
# CONSTANTES ACOPLADAS A ℓa (críticas para que la comparación sea limpia):
#
#   d_s = 0.13 + ℓa  → mantiene CONSTANTE la holgura del peor caso de
#       SEGURIDAD: mirando hacia adentro el punto de mira queda del lado lejano
#       y el centro queda en d_s − ℓa = 0.13 m, con 0.055 m de chasis libre en
#       las tres configuraciones.
#
#   D_robots = 0.15 + 2ℓa  → en el peor caso (ambos robots mirando en
#       direcciones opuestas) la distancia entre puntos de mira excede a la de
#       centros en 2ℓa, así que la garantía sobre centros es D_robots − 2ℓa.
#       Dejarla fija en 0.25 anularía la garantía con ℓa = 0.15
#       (0.25 − 0.30 < 0) y haría que las celdas de ℓa alto se vieran
#       artificialmente buenas por competir contra una restricción más floja.
#
# CONSECUENCIA CONOCIDA del acople de d_s: la holgura de seguridad queda
# constante, pero el límite para APROXIMARSE a una pared de frente crece con
# ℓa (centro ≥ d_s + ℓa = 0.13 + 2ℓa):
#       ℓa = 0.05 → 0.23 m   ℓa = 0.10 → 0.33 m   ℓa = 0.15 → 0.43 m
# Con ℓa alto el agente NO PUEDE acercarse al perímetro de frente, que es como
# se cubre la banda perimetral. Por eso se mide `cobertura_anillo` aparte: una
# caída de cobertura en esas celdas puede ser geométrica (esperable) y no de
# comportamiento, y hay que distinguirlas al reportar.
BARRIDO_ELE_A:   Tuple[float, ...] = (0.05, 0.10, 0.15)
BARRIDO_W_OMEGA: Tuple[float, ...] = (0.30, 0.10, 0.03)

# Banda perimetral para `cobertura_anillo` (misma que en tesis_v3_radio).
ANCHO_ANILLO: float = 0.30

# Umbral del margen de diseño del CBF, para contar violaciones.
MARGEN_CBF_M: float = 0.18


# =============================================================================
# COMPORTAMIENTO DE ESCAPE DEL DEADLOCK DEL CBF
# =============================================================================
# El Exp G mostró que el bloqueo NO se resuelve sintonizando el filtro (ninguna
# de 9 celdas mejoró la base; ver bitácora). La causa es estructural: el
# equilibrio vive en h ≈ 0, donde la condición es c·u ≥ 0 y existe un óptimo
# del QP con velocidad casi nula. Hay que atacarlo por DISEÑO.
#
# PRINCIPIO: el escape reemplaza u_nom, NO al filtro.
#
#     política → u_nom ──┐
#                        ├→ [selector] → u_deseado → FILTRO CBF → u_ejecutado
#     escape   → u_esc ──┘
#
# El QP sigue corriendo sobre la acción que se le pase, así que la garantía
# NUNCA se suspende y el escape no necesita ser perfecto, sólo usualmente
# factible. Además, si la maniobra se aleja de la barrera activa entonces
# ḣ > 0, la restricción se satisface con holgura y el filtro la deja pasar sin
# modificar: el escape CONVIVE con la garantía en vez de puentearla.
#
# LEY DE ESCAPE — ascenso máximo sobre h. Con ṗ = G(θ)u y n la normal interior
# de la barrera activa:
#     ḣ = n·ṗ = a·v + ℓa·b·ω     con a = n·heading, b = n·perp(heading)
# El máximo sobre la caja |v| ≤ V_esc, |ω| ≤ Ω_esc es cerrado:
#     v = V_esc·sign(a)      ω = Ω_esc·sign(b)
# Da ḣ = V_esc·|a| + ℓa·Ω_esc·|b| > 0 SIEMPRE, porque a²+b² = 1 y no pueden
# anularse a la vez. Casos notables:
#   - b = 0 (perpendicular a la pared, el degenerado nº2 del filtro que ninguna
#     sintonización arreglaba) → retroceso puro.
#   - a = 0 (paralelo a la pared) → giro puro.
#   - Usa v < 0, grado de libertad que la política aprendida nunca comanda
#     (0/18 en el Exp A) pese a tenerlo en su espacio de acción.
#
# DIRECCIÓN CON VARIAS BARRERAS ACTIVAS: suma normalizada de TODAS las normales
# activas (pared Y robot-robot) con h < UMBRAL_ACTIVA, no sólo la de menor h.
# Alejarse sólo del robot que bloquea podría meter al agente en una pared. Si
# la suma tiene norma casi nula (normales opuestas: sin dirección de escape
# disponible) se ABORTA y se registra como `escape_infactible` — es
# información, no un fallo a esconder.

ESCAPE_ACTIVO: bool = True

# Detección conjuntiva: los tres términos deben cumplirse simultáneamente
# durante N_DETECCION decisiones consecutivas.
#   - poco desplazamiento  → el síntoma
#   - el CBF intervino     → distingue "bloqueado por el filtro" de "la
#                            política decidió frenar", que es legítimo
#   - h_min pequeño        → confirma que está pegado a una barrera
# No se exige |Δθ| pequeño: en el equilibrio de esquina el robot puede girar
# en el lugar sin avanzar, y eso también es estancamiento.
ESC_UMBRAL_DESPLAZAMIENTO: float = 0.002   # 2 mm entre decisiones
ESC_N_DETECCION:           int   = 6       # 0.6 s sostenidos

# Histéresis (Schmitt trigger) sobre h_min.
ESC_H_ENTRADA: float = 0.03
ESC_H_SALIDA:  float = 0.05   # alternativa 0.08 si aparece chattering; 0.05
                              # evita empujar al enjambre al centro cada vez
                              # que alguien escapa (el mecanismo que disparó
                              # las colisiones con la penalización de v3).
ESC_MIN_DECISIONES: int = 4    # antes de poder salir (anti-chattering)
ESC_MAX_DECISIONES: int = 25   # válvula de seguridad (2.5 s)
ESC_REFRACTARIO:    int = 15   # decisiones sin poder re-disparar (1.5 s)

# Barrera considerada "activa" para componer la dirección de escape.
ESC_UMBRAL_ACTIVA: float = 0.06
# Norma mínima de la suma de normales para considerar el escape factible.
ESC_NORMA_MINIMA:  float = 0.20

# Autoridad de la maniobra (fracción de los límites del actuador).
ESC_FRACCION_V:     float = 0.5
ESC_FRACCION_OMEGA: float = 0.5

# [EXP H] Una activación se considera FALSO POSITIVO aparente si la distancia
# REAL (pose del GPS, no la degradada) a la barrera más cercana superaba este
# valor en el instante del disparo: no había nada de qué escapar.
ESC_UMBRAL_FALSO: float = 0.10


# ── Detector de atasco (mismo criterio del demo de 1 robot) ──────────────
UMBRAL_ATASCO_POS_M:     float = 0.001
UMBRAL_ATASCO_THETA_RAD: float = math.radians(0.5)
N_PASOS_ATASCO:          int   = 20

# Ventana de acciones previas guardada para el diagnóstico de atasco.
VENTANA_ACCIONES: int = N_PASOS_ATASCO

# ── Lote ─────────────────────────────────────────────────────────────────
N_EPISODIOS_LOTE: int = 18
SEMILLAS_LOTE: List[int] = [42 * 10_000 + i for i in range(N_EPISODIOS_LOTE)]
SALIR_AL_TERMINAR: bool = True

# ── Reset de episodio ────────────────────────────────────────────────────
TICKS_ASENTAR_FISICA:  int = 3
TICKS_MAX_ESPERA_POSE: int = 20

# ── Hotspots ─────────────────────────────────────────────────────────────
Z_OBJETIVO:    float     = 0.12
DEF_OBJETIVOS: List[str] = [f"obs{j+1}" for j in range(N_HOTSPOTS)]

DIR_RESULTADOS: Path = _CARPETA / "resultados"


# =============================================================================
# CACHÉ DE POSES
# =============================================================================

class PoseCacheada:
    """
    Última pose conocida de un agente, en sus DOS versiones.

    Atributos
    ---------
    x, y, theta              : pose DEGRADADA (con ruido si SIGMA_POS_M > 0).
                               Es la que consumen el env y el filtro CBF —
                               lo que el sistema "cree".
    x_real, y_real, th_real  : pose REAL del GPS/Compass, sin degradar. Es la
                               que consumen TODAS las métricas físicas, porque
                               miden lo que efectivamente ocurrió.
    tick_emision             : tick en que el agente tomó la lectura.
    tick_recepcion           : tick en que el coordinador la leyó.

    Con SIGMA_POS_M = 0 ambas versiones coinciden exactamente.
    """

    __slots__ = (
        "x", "y", "theta", "x_real", "y_real", "th_real",
        "tick_emision", "tick_recepcion",
    )

    def __init__(
        self,
        x: float, y: float, theta: float,
        tick_emision: int, tick_recepcion: int,
        x_real: float = None, y_real: float = None, th_real: float = None,
    ) -> None:
        self.x              = x
        self.y              = y
        self.theta          = theta
        self.x_real         = x if x_real  is None else x_real
        self.y_real         = y if y_real  is None else y_real
        self.th_real        = theta if th_real is None else th_real
        self.tick_emision   = tick_emision
        self.tick_recepcion = tick_recepcion

    def como_array(self) -> np.ndarray:
        """Pose DEGRADADA (3,) — para el env y el filtro CBF."""
        return np.array([self.x, self.y, self.theta], dtype=np.float64)

    def como_array_real(self) -> np.ndarray:
        """Pose REAL (3,) — para las métricas físicas."""
        return np.array(
            [self.x_real, self.y_real, self.th_real], dtype=np.float64
        )


# =============================================================================
# COORDINADOR
# =============================================================================

class CoordinadorEnjambre:
    """Supervisor central: env + política + comunicación + métricas."""

    def _construir_adaptadores_webots(self) -> None:
        """
        Arma el supervisor de Webots, autodetecta los agentes y construye los
        tres adaptadores de Webots.

        Es EXACTAMENTE el código que estaba en línea en `__init__`, movido sin
        cambios: la ruta de Webots debe seguir produciendo los mismos números
        (los CSV de los Exp A–H son artefactos citados en la tesis).
        """
        from controller import Supervisor      # type: ignore  # sólo en Webots

        from adaptadores_webots import (
            CanalActuacionWebots,
            EntornoEjecucionWebots,
            FuentePosesWebots,
        )
        self._EntornoEjecucionWebots = EntornoEjecucionWebots

        self.supervisor: Supervisor = Supervisor()
        self.timestep_ms: int = int(self.supervisor.getBasicTimeStep())

        self._nodos_robots: List = []
        for i in range(MAX_AGENTES_SONDEO):
            nodo = self.supervisor.getFromDef(f"p3pi_{i}")
            if nodo is None:
                break
            self._nodos_robots.append(nodo)
        self.n_agentes: int = len(self._nodos_robots)
        if self.n_agentes == 0:
            raise RuntimeError(
                "No se encontró ningún nodo DEF p3pi_0. Revisar el .wbt."
            )

        emitter  = self.supervisor.getDevice("emitter")
        receiver = self.supervisor.getDevice("receiver")
        if emitter is None or receiver is None:
            raise RuntimeError(
                "El coordinador necesita Emitter y Receiver en el .wbt."
            )
        self.fuente = FuentePosesWebots(
            receiver, self.n_agentes, self.timestep_ms
        )
        self.canal = CanalActuacionWebots(emitter, lambda: self._tick)

        self._campos_obj: List = []
        for nombre in DEF_OBJETIVOS:
            nodo = self.supervisor.getFromDef(nombre)
            if nodo is None:
                raise RuntimeError(f"No se encontró el nodo DEF {nombre}.")
            self._campos_obj.append(nodo.getField("translation"))

    def __init__(
        self,
        fuente:      Optional[FuentePoses]      = None,
        canal:       Optional[CanalActuacion]   = None,
        entorno:     Optional[EntornoEjecucion] = None,
        n_agentes:   Optional[int]              = None,
        timestep_ms: Optional[int]              = None,
    ) -> None:
        """
        Arma env, política, filtro y métricas sobre los adaptadores dados.

        Sin argumentos construye los adaptadores de Webots y se comporta
        EXACTAMENTE como antes de la Fase 2 — es la ruta que producen todos
        los lotes de los Exp A–H. Con adaptadores inyectados (Robotat,
        simulador del laboratorio) el mismo lazo corre fuera de Webots.

        Parámetros
        ----------
        fuente, canal, entorno : los tres adaptadores. O los tres, o ninguno.
        n_agentes, timestep_ms : obligatorios al inyectar; en Webots salen de
                                 la autodetección y del `basicTimeStep`.
        """
        inyectado = fuente is not None
        if inyectado != (canal is not None) or inyectado != (entorno is not None):
            raise ValueError(
                "Inyectá los tres adaptadores (fuente, canal, entorno) o "
                "ninguno."
            )

        if inyectado:
            if n_agentes is None or timestep_ms is None:
                raise ValueError(
                    "Al inyectar adaptadores hay que dar n_agentes y "
                    "timestep_ms: fuera de Webots no hay de dónde deducirlos."
                )
            self.fuente, self.canal, self.entorno = fuente, canal, entorno
            self.n_agentes = int(n_agentes)
            self.timestep_ms = int(timestep_ms)
            print(f"[coordinador] adaptadores: {self.fuente.nombre} / "
                  f"{self.canal.nombre} / {self.entorno.nombre}")
        else:
            self._construir_adaptadores_webots()

        pasos = DT_ENV * 1000.0 / float(self.timestep_ms)
        if not math.isclose(pasos, round(pasos), abs_tol=1e-6):
            raise ValueError(
                f"basicTimeStep={self.timestep_ms} ms no divide dt_env="
                f"{DT_ENV*1000:.0f} ms."
            )
        self.pasos_por_decision: int = int(round(pasos))

        # ── Rutas de salida (dependen de N y del CBF, por eso van acá) ───
        sufijo_cbf = "_cbf" if CBF_ACTIVO else ""
        if ESCAPE_ACTIVO:
            sufijo_cbf += "_escape"
        sufijo_mod = ("" if NOMBRE_MODELO == "modelo_sanidad"
                      else f"_{NOMBRE_MODELO.replace(chr(45), chr(95))}")
        # El origen de los datos va en el nombre. Sin esto, una corrida contra
        # el Robotat o contra el simulador escribiría sobre el CSV de Webots,
        # que es un artefacto citado en la tesis: mismo N y mismos flags ⇒
        # mismo nombre de archivo.
        nombre_entorno = entorno.nombre if inyectado else "webots"
        sufijo_ent = "" if nombre_entorno == "webots" else f"_{nombre_entorno}"

        # TRAZABILIDAD: el nombre codifica TODO lo que distingue una corrida.
        # Antes dependía sólo de N y de los flags, así que dos configuraciones
        # distintas escribían el mismo archivo: una corrida con σ=10 mm pisó
        # el CSV de σ=0 y la pérdida sólo se detectó al comparar columnas.
        # Los CSV ya citados en la tesis conservan su nombre viejo y ninguna
        # corrida nueva los toca: quedan congelados como artefactos.
        sufijo_deg = (f"_s{SIGMA_POS_M * 1000.0:g}"
                      f"_r{RETARDO_EXTRA_DECISIONES:d}")
        base = (f"{self.n_agentes}agentes{sufijo_mod}{sufijo_cbf}"
                f"{sufijo_ent}{sufijo_deg}")
        self.ruta_csv:     Path = DIR_RESULTADOS / f"lote_multi_{base}.csv"
        self.ruta_resumen: Path = DIR_RESULTADOS / f"resumen_multi_{base}.txt"

        # ── Env y política ───────────────────────────────────────────────
        self.env = CyanobacteriaMonitoringEnv(
            n_agents            = self.n_agentes,
            arena_size          = ARENA_SIZE,
            max_steps           = MAX_STEPS_EP,
            comm_radius         = COMM_RADIUS,
            dt                  = DT_ENV,
            render_mode         = None,
            domain_rand         = DOMAIN_RAND,
            n_hotspots          = N_HOTSPOTS,
            seed                = SEMILLA,
            modo_poses_externas = MODO_POSES_EXTERNAS,
        )
        self.ids_agentes: List[str] = list(self.env.possible_agents)

        if not RUTA_MODELO.is_file():
            raise FileNotFoundError(f"No se encontró el modelo {RUTA_MODELO}.")
        self.modelo: PPO = PPO.load(str(RUTA_MODELO), device="cpu")

        # ── Filtro CBF (import perezoso: con el flag off no se importa) ──
        # [EXP G] Los parámetros vigentes viven en atributos para poder
        # RECONSTRUIR el filtro por configuración durante el barrido.
        self._filtro_cbf = None
        self._ele_a:      float = ELE_A
        self._w_omega:    float = W_OMEGA
        self._d_segura:   float = D_SEGURA_PUNTO
        self._d_robots:   float = D_SEGURA_ROBOTS
        if CBF_ACTIVO:
            from lib.concentration_dynamics import OMEGA_MAX, V_MAX
            from lib.filtro_cbf import FiltroCBFParedes, RestriccionLineal
            self._RestriccionLineal = RestriccionLineal
            self._FiltroCBFParedes  = FiltroCBFParedes
            self._v_max     = V_MAX
            self._omega_max = OMEGA_MAX
            self._construir_filtro()

        # ── Estado ───────────────────────────────────────────────────────
        # Gancho opcional de observación por paso, para las sesiones de
        # laboratorio (`sesion_robotat.py`). Instalarlo NO cambia ningún
        # número: sólo copia y publica lo que el lazo ya calculó.
        self._observador_paso = None
        self._tick: int = 0
        self._cache: Dict[int, PoseCacheada] = {}
        self._webots_cerrado: bool = False
        self._observaciones: Dict[str, np.ndarray] = {}

        # [EXP F] Configuración de degradación vigente. Se sobreescribe por
        # configuración cuando MODO_BARRIDO=True.
        self._sigma_pos: float = SIGMA_POS_M
        self._retardo_extra: int = RETARDO_EXTRA_DECISIONES
        self._rng_ruido = np.random.default_rng(SEMILLA)

        # ── Entorno de ejecución (reloj, visualización, teletransporte) ──
        if not inyectado:
            self.entorno = self._EntornoEjecucionWebots(
                supervisor       = self.supervisor,
                fuente           = self.fuente,
                nodos_robots     = self._nodos_robots,
                campos_hotspots  = self._campos_obj,
                timestep_ms      = self.timestep_ms,
                z_hotspot        = Z_OBJETIVO,
                offset_proto_rad = OFFSET_PROTO_RAD,
            )

        # ── Watchdog: detener los robots ante CUALQUIER salida ───────────
        # En Webots es inofensivo; en el laboratorio es lo que evita que
        # cinco robots sigan andando si el programa muere. Se registra ya en
        # la Fase 1 para que quede ejercitado por todos los lotes.
        atexit.register(self._detener_seguro)

        self._reiniciar_metricas_episodio()

        # ── Log de qué implementación de cada interfaz está activa ───────
        # Trivial en simulación; en el laboratorio, saber de un vistazo que
        # se está en el canal correcto evita accidentes.
        print(f"[coordinador] INTERFACES  fuente={self.fuente.nombre}  "
              f"canal={self.canal.nombre}  entorno={self.entorno.nombre}")

        print(f"[coordinador] listo  agentes_detectados={self.n_agentes}  "
              f"modelo={NOMBRE_MODELO}  timestep={self.timestep_ms} ms  "
              f"pasos_por_decision={self.pasos_por_decision}  "
              f"umbral_antiguedad={UMBRAL_ANTIGUEDAD_TICKS} ticks  "
              f"cbf={'ON' if CBF_ACTIVO else 'OFF'}"
              + (f" (ℓa={ELE_A}, α={ALFA_CBF}, d_pared={D_SEGURA_PUNTO}, "
                 f"d_robots={D_SEGURA_ROBOTS})" if CBF_ACTIVO else ""))

    # ──────────────────────────────────────────────────────────────────────
    # MÉTRICAS
    # ──────────────────────────────────────────────────────────────────────

    def _construir_filtro(self) -> None:
        """
        [EXP G] (Re)construye el filtro CBF con los parámetros vigentes.

        Se llama en `__init__` y una vez por configuración del barrido.
        """
        self._filtro_cbf = self._FiltroCBFParedes(
            arena_size = ARENA_SIZE,
            ele_a      = self._ele_a,
            alfa       = ALFA_CBF,
            d_segura   = self._d_segura,
            w_omega    = self._w_omega,
            v_max      = self._v_max,
            omega_max  = self._omega_max,
        )

    def _aplicar_config_filtro(self, ele_a: float, w_omega: float) -> None:
        """
        [EXP G] Fija una celda del barrido, derivando las constantes acopladas.

            d_s      = 0.13 + ℓa    → holgura de seguridad constante (0.13 m
                                      de centro en el peor caso, mirando hacia
                                      adentro; 0.055 m de chasis libre).
            D_robots = 0.15 + 2ℓa   → garantía de 0.15 m entre CENTROS en el
                                      peor caso (ambos mirando en direcciones
                                      opuestas), que es el contacto de chasis.

        Sin estos acoples las celdas no serían comparables en seguridad.
        """
        self._ele_a    = float(ele_a)
        self._w_omega  = float(w_omega)
        self._d_segura = 0.13 + self._ele_a
        self._d_robots = 0.15 + 2.0 * self._ele_a
        self._construir_filtro()

    def _cobertura_anillo(self) -> float:
        """
        [EXP G] Cobertura del AoI restringida a la banda perimetral.

        Necesaria porque el acople `d_s = 0.13 + ℓa` deja constante la holgura
        de SEGURIDAD pero hace crecer el límite para APROXIMARSE de frente a
        una pared (centro ≥ d_s + ℓa = 0.13 + 2ℓa: 0.23 / 0.33 / 0.43 m). Con
        ℓa alto el agente no puede entrar al perímetro encarándolo, que es como
        se cubre esa banda. Permite distinguir si una caída de cobertura es
        GEOMÉTRICA (del anillo, esperable) o de COMPORTAMIENTO (global).
        """
        xx = self.env._field._grid_xx
        yy = self.env._field._grid_yy
        Wx, Wy = ARENA_SIZE
        dist = np.minimum.reduce([xx, Wx - xx, yy, Wy - yy])
        mascara = dist <= ANCHO_ANILLO
        if not np.any(mascara):
            return 0.0
        return 1.0 - float(np.mean(self.env._field._grid_aoi[mascara]))

    def _reiniciar_metricas_episodio(self) -> None:
        """Limpia acumuladores por episodio."""
        n = self.n_agentes
        self._paso_episodio: int = 0
        self._antiguedad_max: int = 0
        self._decisiones_pose_vieja: int = 0
        self._suma_latencia_ms: float = 0.0
        self._n_muestras_latencia: int = 0

        self._pares_col_contacto: set = set()
        self._pares_col_margen:   set = set()

        self._dist_min_pared: List[float] = [float("inf")] * n

        # [EXP F] Agente-episodios que violaron el margen de diseño del CBF.
        self._violo_margen: List[bool] = [False] * n

        # [EXP F] Cola de latencia por agente (se dimensiona con el retardo
        # de la configuración vigente). Se limpia en cada episodio para que
        # no arrastre poses del anterior.
        self._colas_latencia: List[Deque[np.ndarray]] = [
            deque(maxlen=self._retardo_extra + 1) for _ in range(n)
        ]

        # Detector de atasco por agente.
        self._atasco_consecutivos: List[int]  = [0] * n
        self._atasco_detectado:    List[bool] = [False] * n
        self._atasco_paso:         List[int]  = [-1] * n
        self._pose_previa: Optional[np.ndarray] = None

        # Diagnóstico del atasco (se llena al detectarlo).
        self._atasco_vecino_cerca:  List[bool]  = [False] * n
        self._atasco_dist_vecino:   List[float] = [-1.0] * n
        self._atasco_v_media:       List[float] = [0.0] * n
        self._atasco_w_media:       List[float] = [0.0] * n
        self._atasco_dist_pared:    List[float] = [-1.0] * n

        # [EXP G] Los DOS valores de h de pared más pequeños en el instante
        # del atasco. Permite derivar después la clasificación esquina/pared
        # con el umbral que se quiera, sin comprometerse ahora a uno arbitrario
        # (h_min2 pequeño ⇒ dos barreras activas ⇒ esquina).
        self._atasco_h_min1: List[float] = [float("nan")] * n
        self._atasco_h_min2: List[float] = [float("nan")] * n

        # Historial de acciones por agente (para el diagnóstico).
        self._hist_acciones: List[Deque[Tuple[float, float]]] = [
            deque(maxlen=VENTANA_ACCIONES) for _ in range(n)
        ]

        # ── Estado y estadísticas del ESCAPE (por agente) ────────────────
        # Estados: 0 = inactivo, 1 = en escape, 2 = refractario.
        self._esc_estado:      List[int] = [0] * n
        self._esc_deteccion:   List[int] = [0] * n   # decisiones consecutivas
        self._esc_en_curso:    List[int] = [0] * n   # decisiones del escape
        self._esc_refractario: List[int] = [0] * n
        self._esc_pose_previa: Optional[np.ndarray] = None
        self._esc_intervino_prev: List[bool] = [False] * n
        self._poses_reales_actual: Optional[np.ndarray] = None

        # Métricas por agente (ciclo de trabajo desagregado: el agregado no
        # distingue "5 robots escapando 1 vez" de "1 robot escapando 5 veces",
        # que son diagnósticos opuestos).
        self._esc_n_escapes:    List[int] = [0] * n
        self._esc_decisiones:   List[int] = [0] * n
        self._esc_infactibles:  List[int] = [0] * n
        self._esc_agotados:     List[int] = [0] * n   # llegaron a MAX
        # Instrumentación del recorte del filtro SOBRE la acción de escape:
        # el argumento ḣ>0 vale para la barrera que disparó el escape, pero
        # las otras siguen activas y pueden recortarlo. Si la magnitud media
        # es alta, el escape está peleando con el filtro y falla en silencio.
        self._esc_filtro_modifico: List[int]   = [0] * n
        self._esc_filtro_magnitud: List[float] = [0.0] * n
        # [EXP H] Falsos positivos aparentes: activaciones en las que la
        # distancia REAL a la barrera más cercana superaba ESC_UMBRAL_FALSO,
        # o sea que no había nada de qué escapar. El escape es un consumidor
        # más de la pose (su detección usa desplazamiento medido, intervención
        # del filtro y distancia a barrera; dos de los tres son sensibles al
        # ruido), así que con σ alto puede dispararse sin motivo.
        self._esc_falsos_positivos: List[int] = [0] * n

        # Estadísticas del filtro CBF (por agente).
        self._cbf_intervenciones: List[int]   = [0] * n
        self._cbf_suma_magnitud:  List[float] = [0.0] * n
        self._cbf_int_pared:      List[int]   = [0] * n
        self._cbf_int_robot:      List[int]   = [0] * n
        self._cbf_fallbacks:      List[int]   = [0] * n

    # ──────────────────────────────────────────────────────────────────────
    # COMUNICACIÓN
    # ──────────────────────────────────────────────────────────────────────

    def _procesar_mediciones(
        self, medidas: List[Tuple[int, "PoseMedida"]]
    ) -> None:
        """
        Actualiza el caché con las mediciones de la fuente. Se invoca POR
        TICK desde `entorno.avanzar` — no por decisión: mover el drenaje a
        cadencia de decisión cambiaría la antigüedad de las poses y con ella
        todo el rollout.

        El caché y la política de "usá la última pose conocida" viven acá y
        no en la fuente: esa política ya está validada (Exp F y H la
        ejercitaron con ruido y latencia) y duplicarla en cada implementación
        sería una fuente de divergencia.
        """
        for id_ag, medida in medidas:
            x, y, th = (
                float(medida.pose[0]), float(medida.pose[1]),
                float(medida.pose[2]),
            )
            tick_em = medida.tick
            anterior = self._cache.get(id_ag)
            if anterior is None or tick_em >= anterior.tick_emision:
                # [EXP F] Ruido independiente POR MEDICIÓN, como un OptiTrack
                # real: cada frame trae su propia realización. Se conserva la
                # pose real aparte, para las métricas físicas.
                xd, yd, thd = self._degradar_pose(x, y, th)
                self._cache[id_ag] = PoseCacheada(
                    xd, yd, thd, tick_em, self._tick,
                    x_real=x, y_real=y, th_real=th,
                )

    def _degradar_pose(
        self,
        x: float, y: float, theta: float,
    ) -> Tuple[float, float, float]:
        """
        [EXP F] Aplica ruido gaussiano a una medición de pose.

        El ruido de heading está acoplado al de posición por la relación
        geométrica σ_θ = σ_pos·√2/L_MARCADORES (ver bloque de constantes).

        Con `self._sigma_pos` = 0 devuelve la pose intacta (no-op exacto: ni
        siquiera consume el RNG, para no alterar la secuencia aleatoria).
        """
        if self._sigma_pos <= 0.0:
            return x, y, theta
        sigma_th = self._sigma_pos * math.sqrt(2.0) / L_MARCADORES
        xr = x + float(self._rng_ruido.normal(0.0, self._sigma_pos))
        yr = y + float(self._rng_ruido.normal(0.0, self._sigma_pos))
        thr = theta + float(self._rng_ruido.normal(0.0, sigma_th))
        return xr, yr, float(math.atan2(math.sin(thr), math.cos(thr)))

    def _difundir_acciones(self, acciones: List[Tuple[float, float]]) -> None:
        """Envía las N acciones por el canal de actuación."""
        self.canal.enviar_acciones({i: a for i, a in enumerate(acciones)})

    def _difundir_reset(self) -> None:
        """Ordena a los agentes frenar motores y descartar la acción vigente."""
        self.canal.detener_todo()

    def _detener_seguro(self) -> None:
        """
        Detiene los robots sin lanzar. Registrada en `atexit` y llamada desde
        el `finally` del bucle principal: cualquier salida —fin normal,
        excepción, Ctrl-C— deja los robots quietos.
        """
        try:
            self.canal.detener_todo()
        except Exception as exc:                      # noqa: BLE001
            print(f"[coordinador] parada de emergencia falló: {exc}")

    # ──────────────────────────────────────────────────────────────────────
    # WEBOTS
    # ──────────────────────────────────────────────────────────────────────

    def _avanzar(self, n_ticks: int = 1) -> bool:
        """
        Avanza `n_ticks` del reloj del entorno. El drenaje de poses ocurre
        POR TICK dentro de `entorno.avanzar`, vía el callback
        `_procesar_mediciones`. False si el entorno pidió cerrar.
        """
        for _ in range(n_ticks):
            if not self.entorno.avanzar(1):
                self._webots_cerrado = True
                return False
            # ORDEN CRÍTICO, idéntico al original: incrementar el tick ANTES
            # de procesar las mediciones (el caché registra `tick_recepcion`
            # con el valor ya incrementado), y drenar UNA VEZ POR TICK.
            self._tick += 1
            self._procesar_mediciones(self.fuente.leer_poses())
        return True

    def _publicar_hotspots(self) -> None:
        """Refleja las posiciones de los objetivos en la visualización."""
        self.entorno.publicar_visualizacion(
            self.env._field.posiciones_objetivos
        )

    # ──────────────────────────────────────────────────────────────────────
    # DECISIÓN
    # ──────────────────────────────────────────────────────────────────────

    def _poses_reales(self) -> Dict[str, np.ndarray]:
        """
        [EXP F] Poses REALES del GPS/Compass, sin degradar y sin retardo.

        Es la fuente de verdad para TODAS las métricas físicas (colisiones,
        d_min a pared, detector de atasco, violaciones del margen): miden lo
        que efectivamente ocurrió, no lo que el sistema creyó ver.
        """
        return {
            self.ids_agentes[i]: self._cache[i].como_array_real()
            for i in range(self.n_agentes)
            if i in self._cache
        }

    def _poses_actuales(self) -> Dict[str, np.ndarray]:
        """
        Arma el dict de poses DEGRADADAS que consumen el env y el filtro CBF.

        [EXP F] Aplica la cola de latencia: la pose cacheada se empuja a un
        deque por agente de `retardo_extra + 1` elementos y se usa el MÁS
        VIEJO. Con retardo 0 el deque tiene un solo elemento y el
        comportamiento es idéntico al original. Durante el arranque del
        episodio, mientras el deque no se llenó, se usa el más viejo
        disponible (comportamiento natural de un buffer llenándose).

        Raises
        ------
        RuntimeError : si algún agente nunca envió pose (fallo de config).
        """
        faltantes = [i for i in range(self.n_agentes) if i not in self._cache]
        if faltantes:
            raise RuntimeError(
                f"Nunca se recibió pose de los agentes {faltantes}. "
                f"Revisar en el .wbt: DEF p3pi_<i>, name 'p3pi_<i>', "
                f"controller 'controlador_agente', y que tengan Emitter "
                f"(canal {CANAL_SUBIDA}) + Receiver (canal {CANAL_BAJADA})."
            )

        poses: Dict[str, np.ndarray] = {}
        antiguedad_max = 0
        for i in range(self.n_agentes):
            cacheada = self._cache[i]

            # [EXP F] Cola de latencia: empujar la pose de esta decisión y
            # consumir la más vieja del deque.
            self._colas_latencia[i].append(cacheada.como_array())
            poses[self.ids_agentes[i]] = self._colas_latencia[i][0].copy()

            # La antigüedad de sincronía sigue midiendo el lag ESTRUCTURAL
            # (emisión → recepción). El retardo inyectado se contabiliza
            # aparte, en la columna `retardo_extra` del CSV.
            antiguedad = self._tick - cacheada.tick_emision
            antiguedad_max = max(antiguedad_max, antiguedad)
            self._suma_latencia_ms += antiguedad * self.timestep_ms
            self._n_muestras_latencia += 1

        self._antiguedad_max = max(self._antiguedad_max, antiguedad_max)
        if antiguedad_max > UMBRAL_ANTIGUEDAD_TICKS:
            self._decisiones_pose_vieja += 1
            warnings.warn(
                f"[sync] Decisión con pose vieja: antigüedad={antiguedad_max} "
                f"ticks (umbral {UMBRAL_ANTIGUEDAD_TICKS}) en tick {self._tick}.",
                RuntimeWarning, stacklevel=2,
            )
        return poses

    def _diagnosticar_atasco(self, i: int, pos: np.ndarray) -> None:
        """
        Registra el contexto del atasco recién detectado del agente `i`.

        Discrimina dos mecanismos posibles:
          - Si había un vecino dentro de comm_radius, la hipótesis es que la
            evitación inter-agente empujó al robot contra la pared (y en ese
            caso más densidad AGRAVA el problema).
          - Si no había vecino cerca, el mecanismo es el gap chasis-vs-punto
            (el env trata al agente como punto; Webots le da radio 0.075 m y
            fricción de contacto), y la densidad no debería agravarlo.

        Parámetros
        ----------
        i   : índice del agente atascado.
        pos : np.ndarray (N, 2) con las posiciones de todos en esta decisión.
        """
        # Vecino más cercano.
        if self.n_agentes > 1:
            otros = np.delete(np.arange(self.n_agentes), i)
            dists = np.linalg.norm(pos[otros] - pos[i], axis=1)
            d_min = float(np.min(dists))
            self._atasco_dist_vecino[i]  = round(d_min, 4)
            self._atasco_vecino_cerca[i] = bool(d_min <= COMM_RADIUS)
        else:
            self._atasco_dist_vecino[i]  = -1.0
            self._atasco_vecino_cerca[i] = False

        # Acción media comandada en la ventana previa al atasco.
        hist = self._hist_acciones[i]
        if hist:
            arr = np.array(hist, dtype=np.float64)
            self._atasco_v_media[i] = round(float(np.mean(arr[:, 0])), 4)
            self._atasco_w_media[i] = round(float(np.mean(arr[:, 1])), 4)

        # Distancia a la pared en el momento del atasco (sin redondear).
        Wx, Wy = ARENA_SIZE
        x, y = float(pos[i, 0]), float(pos[i, 1])
        self._atasco_dist_pared[i] = min(x, Wx - x, y, Wy - y)

        # [EXP G] Los dos h de pared más pequeños, evaluados sobre el punto de
        # mira con los parámetros vigentes del filtro. La clasificación
        # esquina/pared se deriva después: h_min2 pequeño ⇒ dos barreras
        # activas ⇒ esquina.
        if self._filtro_cbf is not None and self._pose_previa is not None:
            pose_i = self._pose_previa[i]
            p = self._filtro_cbf._punto_de_mira(pose_i)
            hs = sorted(
                r.h for r in self._filtro_cbf._barreras_paredes(
                    p, float(pose_i[2])
                )
            )
            self._atasco_h_min1[i] = float(hs[0])
            self._atasco_h_min2[i] = float(hs[1])

    def _actualizar_metricas(
        self,
        poses:    Dict[str, np.ndarray],
        acciones: Dict[str, np.ndarray],
    ) -> None:
        """
        Actualiza colisiones (ambos umbrales), distancia a pared, historial de
        acciones y el detector de atasco por agente.
        """
        n = self.n_agentes
        pos = np.array([poses[self.ids_agentes[i]][:2] for i in range(n)])

        # ── Historial de acciones (para el diagnóstico) ──────────────────
        for i in range(n):
            a = acciones[self.ids_agentes[i]]
            self._hist_acciones[i].append((float(a[0]), float(a[1])))

        # ── Colisiones: pares únicos bajo cada umbral ────────────────────
        for ii in range(n):
            for jj in range(ii + 1, n):
                d = float(np.linalg.norm(pos[ii] - pos[jj]))
                if d < UMBRAL_COLISION_CONTACTO:
                    self._pares_col_contacto.add((ii, jj))
                if d < UMBRAL_COLISION_MARGEN:
                    self._pares_col_margen.add((ii, jj))

        # ── Distancia mínima de cada centro a una pared ──────────────────
        Wx, Wy = ARENA_SIZE
        for i in range(n):
            x, y = float(pos[i, 0]), float(pos[i, 1])
            d_pared = min(x, Wx - x, y, Wy - y)
            self._dist_min_pared[i] = min(self._dist_min_pared[i], d_pared)
            # [EXP F] Violación del margen de diseño del CBF (poses REALES).
            if d_pared < MARGEN_CBF_M:
                self._violo_margen[i] = True

        # ── Detector de atasco por agente ────────────────────────────────
        actual = np.array([poses[self.ids_agentes[i]] for i in range(n)])
        if self._pose_previa is not None:
            for i in range(n):
                d_pos = float(np.linalg.norm(
                    actual[i, :2] - self._pose_previa[i, :2]
                ))
                dth  = actual[i, 2] - self._pose_previa[i, 2]
                d_th = abs(math.atan2(math.sin(dth), math.cos(dth)))
                quieto = (d_pos < UMBRAL_ATASCO_POS_M
                          and d_th < UMBRAL_ATASCO_THETA_RAD)
                self._atasco_consecutivos[i] = (
                    self._atasco_consecutivos[i] + 1 if quieto else 0
                )
                if (not self._atasco_detectado[i]
                        and self._atasco_consecutivos[i] >= N_PASOS_ATASCO):
                    self._atasco_detectado[i] = True
                    self._atasco_paso[i] = self._paso_episodio
                    self._diagnosticar_atasco(i, pos)
        self._pose_previa = actual.copy()

    def _barreras_robot_robot(
        self,
        i:     int,
        poses: np.ndarray,
    ) -> List:
        """
        Construye las barreras de colisión robot-robot para el agente `i`,
        ya proyectadas en su control u_i = (v_i, ω_i).

        Formulación
        -----------
        Sobre los PUNTOS DE MIRA p_k = c_k + ℓa·(cosθ_k, senθ_k), la barrera
        entre i y j es

            h_ij = ‖p_i − p_j‖ − d_segura_robots

        Su derivada depende de AMBOS controles:

            ḣ_ij = (p_i − p_j)/‖·‖ · (ṗ_i − ṗ_j)

        pero el agente i sólo controla u_i. Se usa el reparto de
        responsabilidad 50/50 del Robotarium: cada robot se hace cargo de la
        mitad de la condición,

            n_ij^T · G(θ_i) · u_i  ≥  −(α/2)·h_ij,   n_ij = (p_i−p_j)/‖·‖

        Como el filtro impone `c·u ≥ −α·h`, se pasa h = h_ij/2 para obtener
        exactamente el factor 1/2. (Consecuencia menor: el diagnóstico
        `h_minima` reporta el valor ya halveado para estas filas.)

        Parámetros
        ----------
        i     : índice del agente.
        poses : np.ndarray (N, 3) con [x, y, θ] de todos los agentes.

        Retorna
        -------
        Lista de RestriccionLineal (una por cada otro agente).
        """
        extras: List = []
        p_i = self._filtro_cbf._punto_de_mira(poses[i])
        G_i = self._filtro_cbf._matriz_G(float(poses[i, 2]))

        for j in range(self.n_agentes):
            if j == i:
                continue
            p_j = self._filtro_cbf._punto_de_mira(poses[j])
            delta = p_i - p_j
            dist = float(np.linalg.norm(delta))
            if dist < 1e-9:
                continue    # coincidencia numérica: sin dirección definida
            normal = delta / dist
            extras.append(self._RestriccionLineal(
                c      = normal @ G_i,
                h      = 0.5 * (dist - self._d_robots),
                nombre = f"robot_{j}",
            ))
        return extras

    def _normales_activas(
        self,
        i:     int,
        poses: np.ndarray,
    ) -> Tuple[Optional[np.ndarray], float]:
        """
        Reúne las normales interiores de TODAS las barreras activas del agente
        `i` (pared y robot-robot con h < ESC_UMBRAL_ACTIVA) y devuelve su suma
        normalizada, más el h mínimo global.

        Considerar sólo la barrera de menor h sería incorrecto: alejarse del
        robot que bloquea podría meter al agente en una pared. Si la suma tiene
        norma casi nula (normales opuestas), no hay dirección de escape
        disponible y se devuelve None → el llamador aborta y lo registra.

        Retorna
        -------
        (direccion, h_min) : direccion es None si el escape es infactible.
        """
        pose_i = poses[i]
        p_i = self._filtro_cbf._punto_de_mira(pose_i)

        normales: List[np.ndarray] = []
        h_min = float("inf")

        # ── Paredes: normales interiores fijas ───────────────────────────
        Wx, Wy = ARENA_SIZE
        candidatas = [
            (np.array([1.0, 0.0]),  float(p_i[0]) - self._d_segura),
            (np.array([-1.0, 0.0]), (Wx - float(p_i[0])) - self._d_segura),
            (np.array([0.0, 1.0]),  float(p_i[1]) - self._d_segura),
            (np.array([0.0, -1.0]), (Wy - float(p_i[1])) - self._d_segura),
        ]
        # ── Robot-robot: normal desde el vecino hacia el agente ──────────
        for j in range(self.n_agentes):
            if j == i:
                continue
            p_j = self._filtro_cbf._punto_de_mira(poses[j])
            delta = p_i - p_j
            dist = float(np.linalg.norm(delta))
            if dist < 1e-9:
                continue
            candidatas.append((delta / dist, dist - self._d_robots))

        for normal, h in candidatas:
            h_min = min(h_min, h)
            if h < ESC_UMBRAL_ACTIVA:
                normales.append(normal)

        if not normales:
            return None, h_min

        suma = np.sum(np.asarray(normales), axis=0)
        norma = float(np.linalg.norm(suma))
        if norma < ESC_NORMA_MINIMA:
            return None, h_min          # direcciones opuestas: sin salida
        return suma / norma, h_min

    def _accion_escape(
        self,
        direccion: np.ndarray,
        theta:     float,
    ) -> np.ndarray:
        """
        Ley de ascenso máximo sobre h (ver bloque de constantes):

            a = n·heading         b = n·perp(heading)
            v = V_esc·sign(a)     ω = Ω_esc·sign(b)

        Maximiza ḣ = a·v + ℓa·b·ω sobre la caja del actuador. Como a²+b² = 1,
        nunca se anulan a la vez, así que siempre da ḣ > 0.
        """
        heading = np.array([math.cos(theta), math.sin(theta)])
        perp    = np.array([-math.sin(theta), math.cos(theta)])
        a = float(direccion @ heading)
        b = float(direccion @ perp)
        return np.array([
            ESC_FRACCION_V * self._v_max * np.sign(a),
            ESC_FRACCION_OMEGA * self._omega_max * np.sign(b),
        ], dtype=np.float32)

    def _gestionar_escape(
        self,
        i:      int,
        poses:  np.ndarray,
        u_nom:  np.ndarray,
    ) -> Tuple[np.ndarray, bool]:
        """
        Máquina de estados del escape del agente `i`. Devuelve la acción
        DESEADA (que después pasa por el filtro CBF igual) y si está en escape.

        Estados: inactivo → (detección sostenida) → en escape → (histéresis o
        tope) → refractario → inactivo.
        """
        direccion, h_min = self._normales_activas(i, poses)

        # ── Refractario: descontar y salir ───────────────────────────────
        if self._esc_estado[i] == 2:
            self._esc_refractario[i] -= 1
            if self._esc_refractario[i] <= 0:
                self._esc_estado[i] = 0
            return u_nom, False

        # ── En escape: continuar o terminar ──────────────────────────────
        if self._esc_estado[i] == 1:
            self._esc_en_curso[i] += 1
            termina = (
                (self._esc_en_curso[i] >= ESC_MIN_DECISIONES
                 and h_min > ESC_H_SALIDA)
                or self._esc_en_curso[i] >= ESC_MAX_DECISIONES
            )
            if self._esc_en_curso[i] >= ESC_MAX_DECISIONES:
                self._esc_agotados[i] += 1
            if termina:
                self._esc_estado[i]      = 2
                self._esc_refractario[i] = ESC_REFRACTARIO
                self._esc_en_curso[i]    = 0
                self._esc_deteccion[i]   = 0
                return u_nom, False
            if direccion is None:
                # Perdió dirección de escape a mitad de la maniobra.
                self._esc_infactibles[i] += 1
                self._esc_estado[i]      = 2
                self._esc_refractario[i] = ESC_REFRACTARIO
                self._esc_en_curso[i]    = 0
                return u_nom, False
            self._esc_decisiones[i] += 1
            return self._accion_escape(direccion, float(poses[i, 2])), True

        # ── Inactivo: evaluar la detección conjuntiva ────────────────────
        desplazamiento = float("inf")
        if self._esc_pose_previa is not None:
            desplazamiento = float(np.linalg.norm(
                poses[i, :2] - self._esc_pose_previa[i, :2]
            ))
        estancado = (
            desplazamiento < ESC_UMBRAL_DESPLAZAMIENTO
            and self._esc_intervino_prev[i]
            and h_min < ESC_H_ENTRADA
        )
        self._esc_deteccion[i] = self._esc_deteccion[i] + 1 if estancado else 0

        if self._esc_deteccion[i] >= ESC_N_DETECCION:
            if direccion is None:
                # Estancado pero sin dirección de escape disponible.
                self._esc_infactibles[i] += 1
                self._esc_deteccion[i]   = 0
                self._esc_estado[i]      = 2
                self._esc_refractario[i] = ESC_REFRACTARIO
                return u_nom, False
            self._esc_estado[i]     = 1
            self._esc_en_curso[i]   = 1
            self._esc_deteccion[i]  = 0
            self._esc_n_escapes[i] += 1
            self._esc_decisiones[i] += 1
            # [EXP H] ¿Había realmente algo de qué escapar? Se evalúa con las
            # poses REALES, no con las degradadas que dispararon la detección.
            if self._poses_reales_actual is not None:
                _, h_real = self._normales_activas(
                    i, self._poses_reales_actual
                )
                if h_real > ESC_UMBRAL_FALSO:
                    self._esc_falsos_positivos[i] += 1
            return self._accion_escape(direccion, float(poses[i, 2])), True

        return u_nom, False

    def _decidir_y_actuar(self) -> bool:
        """
        Una decisión completa: poses → env → política → [CBF] → difusión →
        env.step. La acción que se difunde y que recibe el env es la
        EJECUTADA (filtrada), no la nominal.

        Retorna
        -------
        episodio_terminado : bool
        """
        # [EXP F] Dos vistas de la misma realidad:
        #   `poses`        → DEGRADADA (ruido + retardo): env y filtro CBF.
        #   `poses_reales` → REAL del GPS: TODAS las métricas físicas.
        poses = self._poses_actuales()
        poses_reales = self._poses_reales()
        self.env.inyectar_poses_externas(poses)

        arreglo_poses = np.array(
            [poses[self.ids_agentes[i]] for i in range(self.n_agentes)]
        )
        # [EXP H] Poses reales disponibles para el chequeo de falso positivo
        # del escape (que decide con las degradadas, como corresponde).
        self._poses_reales_actual = np.array(
            [poses_reales[self.ids_agentes[i]] for i in range(self.n_agentes)]
        ) if len(poses_reales) == self.n_agentes else None

        acciones_dict:  Dict[str, np.ndarray]     = {}
        acciones_lista: List[Tuple[float, float]] = []
        for i in range(self.n_agentes):
            agente = self.ids_agentes[i]
            accion, _ = self.modelo.predict(
                self._observaciones[agente], deterministic=True
            )
            accion = np.asarray(accion, dtype=np.float32).flatten()
            accion_nominal = accion.copy()

            # ── Escape: REEMPLAZA u_nom, no al filtro ────────────────────
            en_escape = False
            if ESCAPE_ACTIVO and self._filtro_cbf is not None:
                accion, en_escape = self._gestionar_escape(
                    i, arreglo_poses, accion
                )
            accion_tras_escape = accion.copy()

            # ── Filtro CBF: paredes (del módulo) + robot-robot (extras) ──
            if self._filtro_cbf is not None:
                extras = self._barreras_robot_robot(i, arreglo_poses)
                resultado = self._filtro_cbf.filtrar(
                    arreglo_poses[i], accion, restricciones_extra=extras,
                )
                if resultado.intervino:
                    self._cbf_intervenciones[i] += 1
                    self._cbf_suma_magnitud[i] += resultado.magnitud_modificacion
                    if resultado.barrera_activa.startswith("robot_"):
                        self._cbf_int_robot[i] += 1
                    else:
                        self._cbf_int_pared[i] += 1
                if not resultado.exito_qp:
                    self._cbf_fallbacks[i] += 1

                # ¿El filtro recortó la propia acción de ESCAPE? El argumento
                # ḣ>0 vale para la barrera que disparó el escape, pero las
                # otras siguen activas y pueden recortarlo. Magnitud media
                # alta ⇒ el escape pelea con el filtro y falla en silencio.
                if en_escape and resultado.intervino:
                    self._esc_filtro_modifico[i] += 1
                    self._esc_filtro_magnitud[i] += (
                        resultado.magnitud_modificacion
                    )

                self._esc_intervino_prev[i] = bool(resultado.intervino)
                accion = np.asarray(resultado.u_seguro, dtype=np.float32)

            acciones_dict[agente] = accion
            acciones_lista.append((float(accion[0]), float(accion[1])))

            # ── Gancho de observación (sesiones de laboratorio) ──────────
            # Sólo se invoca si alguien lo instaló. Con `None` —que es el
            # caso de TODOS los lotes de los Exp A–H— el costo es un `is
            # not None` por agente y por decisión, y no toca ningún número.
            if self._observador_paso is not None:
                self._observador_paso({
                    "agente":              i,
                    "pose_env":            arreglo_poses[i].copy(),
                    "pose_real":           (self._poses_reales_actual[i].copy()
                                            if self._poses_reales_actual
                                            is not None else None),
                    "observacion":         np.asarray(
                                               self._observaciones[agente]
                                           ).copy(),
                    "accion_nominal":      accion_nominal,
                    "accion_tras_escape":  accion_tras_escape,
                    "accion_ejecutada":    accion.copy(),
                    "en_escape":           bool(en_escape),
                    "cbf_intervino":       bool(
                        self._esc_intervino_prev[i]
                        if self._filtro_cbf is not None else False
                    ),
                    "paso":                self._paso_episodio,
                    "tick":                self._tick,
                })

        # Difundir ANTES de la contabilidad: los agentes ya pueden actuar.
        self._difundir_acciones(acciones_lista)

        # Pose previa para la detección de estancamiento del escape (usa la
        # DEGRADADA: es lo que el sistema ve, igual que el filtro).
        self._esc_pose_previa = arreglo_poses.copy()

        # Métricas SIEMPRE con las poses reales (ver [EXP F] arriba).
        self._actualizar_metricas(poses_reales, acciones_dict)

        (
            self._observaciones,
            _rew, _term, truncs, _infos,
        ) = self.env.step(acciones_dict)

        self._publicar_hotspots()
        self._paso_episodio += 1
        return bool(truncs) and all(truncs.values())

    # ──────────────────────────────────────────────────────────────────────
    # RESET DE EPISODIO
    # ──────────────────────────────────────────────────────────────────────

    def _reiniciar_episodio(self, semilla: int) -> bool:
        """
        Reinicia un episodio con N robots:

          1. Difundir RESET → los agentes frenan motores.
          2. Avanzar 1 tick para que el mensaje llegue.
          3. env.reset(seed) → poses iniciales sorteadas sin colisión.
          4. Teletransportar cada robot + resetPhysics().
          5. Avanzar TICKS_ASENTAR_FISICA ticks (física y sensores).
          6. Invalidar el caché (las poses previas son de posiciones viejas).
          7. Esperar poses frescas de los N agentes, con tope.
          8. Inyectar poses físicas y hacer un step con acción cero.

        El teletransporte ocurre SÓLO acá, entre episodios. Dentro del
        episodio manda la física, sin excepción.

        Retorna False si Webots cerró.
        """
        self._difundir_reset()
        if not self._avanzar(1):
            return False

        # [EXP F] RNG de ruido sembrado por (semilla, configuración) para que
        # cada celda del barrido sea reproducible. El pareo entre
        # configuraciones es por SEMILLA (mismas poses iniciales y misma
        # trayectoria de hotspots), no por realización de ruido.
        self._rng_ruido = np.random.default_rng(
            (semilla * 1000
             + int(round(self._sigma_pos * 1e5)) * 10
             + self._retardo_extra)
        )

        self.env.reset(seed=semilla)

        # Teletransporte SÓLO entre episodios, y sólo donde existe. En el
        # Robotat no existe: los robots arrancan donde quedaron, y el env se
        # sincroniza con ellos vía `inyectar_poses_externas` unas líneas más
        # abajo. Se consulta la capacidad en vez de atrapar la excepción (ver
        # `EntornoEjecucion.soporta_reposicionar`).
        if self.entorno.soporta_reposicionar:
            self.entorno.reposicionar({
                i: self.env._estados[self.ids_agentes[i]][:3]
                for i in range(self.n_agentes)
            })
        elif semilla == SEMILLAS_LOTE[0]:
            print("[coordinador] sin teletransporte: los robots arrancan "
                  "donde estén; el env se sincroniza con sus poses reales.")

        if not self._avanzar(TICKS_ASENTAR_FISICA):
            return False

        self._cache.clear()
        # `fuente.reiniciar()` invalida el estado de la fuente en el MISMO
        # punto en que se invalida el caché del coordinador — están
        # documentados como el mismo paso ("6. Invalidar el caché") y deben
        # ir juntos. Hallazgo (2026-08-22): esta llamada nunca se hacía, en
        # NINGÚN adaptador, pese a que la interfaz la declara para esto
        # exacto. Sin impacto en Webots (su `reiniciar()` sólo limpia un
        # `_vistos` de diagnóstico que nadie más lee); en el Robotat,
        # además, reinicia el limitador de tasa de `FuentePosesRobotat` para
        # que la próxima consulta sea inmediata, no que herede hasta
        # `_intervalo_ticks` llamadas de esperar del episodio anterior.
        self.fuente.reiniciar()

        esperados = 0
        while len(self._cache) < self.n_agentes:
            if not self._avanzar(1):
                return False
            esperados += 1
            if esperados > TICKS_MAX_ESPERA_POSE:
                faltan = [
                    i for i in range(self.n_agentes) if i not in self._cache
                ]
                raise RuntimeError(
                    f"Tras {esperados} ticks no llegaron poses de {faltan}. "
                    f"Revisar controladores y canales."
                )

        self._reiniciar_metricas_episodio()
        poses = {
            self.ids_agentes[i]: self._cache[i].como_array()
            for i in range(self.n_agentes)
        }
        self.env.inyectar_poses_externas(poses)
        acciones_cero = {
            a: np.zeros(2, dtype=np.float32) for a in self.ids_agentes
        }
        self._observaciones, _r, _t, _tr, _i = self.env.step(acciones_cero)
        self._publicar_hotspots()
        return True

    # ──────────────────────────────────────────────────────────────────────
    # LOTE
    # ──────────────────────────────────────────────────────────────────────

    def correr(self) -> None:
        """
        Punto de entrada, según MODO_BARRIDO:

          "off"    → lote simple con la configuración vigente.
          "ruido"  → Exp F: 4 niveles de σ × 3 de retardo (12 celdas).
          "filtro" → Exp G: 3 valores de ℓa × 3 de w_ω (9 celdas), con d_s y
                     D_robots derivados de ℓa.

        Los barridos recorren todas las celdas sobre las mismas 18 semillas en
        UNA sola sesión de Webots.
        """
        if MODO_BARRIDO == "filtro":
            self._correr_barrido_filtro()
        elif MODO_BARRIDO == "off":
            resultados = self._correr_configuracion()
            if resultados:
                self._escribir_resultados(resultados)
        else:
            todos: List[Dict[str, object]] = []
            n_cfg = len(BARRIDO_SIGMAS) * len(BARRIDO_RETARDOS)
            k = 0
            for sigma in BARRIDO_SIGMAS:
                for retardo in BARRIDO_RETARDOS:
                    k += 1
                    self._sigma_pos = float(sigma)
                    self._retardo_extra = int(retardo)
                    sigma_th = (
                        sigma * math.sqrt(2.0) / L_MARCADORES
                        if sigma > 0 else 0.0
                    )
                    print(f"\n[barrido {k}/{n_cfg}] σ_pos={sigma*1000:.0f} mm "
                          f"(σ_θ={math.degrees(sigma_th):.2f}°)  "
                          f"retardo_extra={retardo} decisiones")
                    filas = self._correr_configuracion()
                    todos.extend(filas)
                    if self._webots_cerrado:
                        break
                if self._webots_cerrado:
                    break
            if todos:
                self._escribir_barrido(todos)

        self._difundir_reset()
        if SALIR_AL_TERMINAR and not self._webots_cerrado:
            self.entorno.finalizar(0)

    def _correr_barrido_filtro(self) -> None:
        """
        [EXP G] Recorre las celdas (ℓa, w_ω), derivando d_s y D_robots, y
        vuelca CSV + resumen. Reporta el barrido COMPLETO aunque ninguna celda
        alcance el criterio de éxito: una mejora parcial también es informativa.
        """
        if self._filtro_cbf is None:
            raise RuntimeError(
                "MODO_BARRIDO='filtro' requiere CBF_ACTIVO=True."
            )
        todos: List[Dict[str, object]] = []
        n_cfg = len(BARRIDO_ELE_A) * len(BARRIDO_W_OMEGA)
        k = 0
        for ele_a in BARRIDO_ELE_A:
            for w_omega in BARRIDO_W_OMEGA:
                k += 1
                self._aplicar_config_filtro(ele_a, w_omega)
                print(f"\n[barrido G {k}/{n_cfg}] ℓa={ele_a:.2f} "
                      f"w_ω={w_omega:.2f}  →  d_s={self._d_segura:.2f} "
                      f"d_robots={self._d_robots:.2f}  "
                      f"(centro peor caso {self._d_segura - ele_a:.3f} m, "
                      f"aproximación de frente {self._d_segura + ele_a:.3f} m)")
                todos.extend(self._correr_configuracion())
                if self._webots_cerrado:
                    break
            if self._webots_cerrado:
                break
        if todos:
            self._escribir_barrido_filtro(todos)

        self._difundir_reset()
        if SALIR_AL_TERMINAR and not self._webots_cerrado:
            self.entorno.finalizar(0)

    def _escribir_barrido_filtro(self, filas: List[Dict[str, object]]) -> None:
        """[EXP G] Vuelca el CSV del barrido de filtro y su resumen."""
        DIR_RESULTADOS.mkdir(parents=True, exist_ok=True)
        n_ag = self.n_agentes
        ruta_csv = DIR_RESULTADOS / f"expG_barrido_filtro_{n_ag}agentes.csv"
        ruta_txt = DIR_RESULTADOS / f"expG_resumen_filtro_{n_ag}agentes.txt"

        with open(ruta_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
            w.writeheader()
            w.writerows(filas)
        print(f"\n[expG] CSV → {ruta_csv}")

        def K(r):
            return (float(r["cbf_ele_a"]), float(r["cbf_w_omega"]))

        cfgs = sorted({K(r) for r in filas})
        P = {c: [r for r in filas if K(r) == c] for c in cfgs}
        base = (0.05, 0.30)
        R_CHASIS = 0.075

        def col(c, campo):
            return np.array([float(r[campo]) for r in P[c]])

        def contacto(c):
            return sum(
                1 for r in P[c] for i in range(n_ag)
                if float(r[f"dist_min_pared_a{i}"]) < R_CHASIS
            )

        L: List[str] = []
        L.append("EXPERIMENTO G — barrido de parámetros del filtro CBF")
        L.append(f"{n_ag} agentes con física real · {len(SEMILLAS_LOTE)} "
                 f"semillas por celda · modelo={NOMBRE_MODELO} · "
                 f"SIN ruido ni latencia (σ=0, retardo=0)")
        L.append(f"{len(cfgs)} configuraciones × {len(SEMILLAS_LOTE)} = "
                 f"{len(filas)} episodios.")
        L.append("=" * 78)
        L.append("")
        L.append("OBJETIVO: encontrar una configuración que NO produzca bloqueo,")
        L.append("para tener un sistema SANO sobre el cual medir robustez de")
        L.append("verdad. El Exp F midió la perturbación de un equilibrio")
        L.append("patológico, no tolerancia al ruido.")
        L.append("")
        L.append("PALANCAS. Los atascos ocurren EN el margen (33/39 a d≈0.18) y")
        L.append("en esquinas (16/17), así que ampliar d_s sólo mudaría el")
        L.append("equilibrio. Se barren ℓa (autoridad de giro: el coeficiente")
        L.append("de ω en la restricción es proporcional a ℓa) y w_ω")
        L.append("(preferencia por girar sobre frenar). α=2.0 fijo: en h≈0 la")
        L.append("condición es c·u ≥ 0 sin α, así que no mueve el punto fijo.")
        L.append("")
        L.append("CONSTANTES ACOPLADAS (para que las celdas sean comparables):")
        L.append("  d_s      = 0.13 + ℓa   → holgura de SEGURIDAD constante:")
        L.append("                           centro a 0.13 m en el peor caso,")
        L.append("                           0.055 m de chasis libre.")
        L.append("  D_robots = 0.15 + 2ℓa  → 0.15 m entre CENTROS garantizados")
        L.append("                           en el peor caso (contacto chasis).")
        L.append("")
        L.append("  ⚠ CONSECUENCIA: el límite para APROXIMARSE de frente a una")
        L.append("    pared crece con ℓa (centro ≥ d_s + ℓa = 0.13 + 2ℓa):")
        L.append("      ℓa=0.05 → 0.23 m · ℓa=0.10 → 0.33 m · ℓa=0.15 → 0.43 m")
        L.append("    Con ℓa alto el agente NO PUEDE entrar al perímetro")
        L.append("    encarándolo. Por eso se reporta `anillo` aparte: una caída")
        L.append("    de cobertura puede ser GEOMÉTRICA (del anillo, esperable)")
        L.append("    y no de COMPORTAMIENTO (global).")
        L.append("")
        L.append("TABLA 1 — TODAS LAS CELDAS")
        L.append(f"  {'ℓa':>5s} {'w_ω':>5s} {'d_s':>5s} {'D_rob':>6s} "
                 f"{'atascos':>10s} {'cobertura':>16s} {'anillo':>16s} "
                 f"{'col015':>7s} {'contact':>8s} {'CBFfrac':>8s} {'fallb':>6s}")
        L.append("  " + "-" * 108)
        for c in cfgs:
            ele_a, w_om = c
            n_ae = len(P[c]) * n_ag
            at = col(c, "agentes_atascados").sum()
            cob = col(c, "cobertura_aoi_final")
            an  = col(c, "cobertura_anillo")
            marca = "  ← BASE" if c == base else ""
            L.append(
                f"  {ele_a:5.2f} {w_om:5.2f} {0.13+ele_a:5.2f} "
                f"{0.15+2*ele_a:6.2f} {at:5.0f}/{n_ae:<4d} "
                f"{cob.mean():8.4f} ± {cob.std():.4f} "
                f"{an.mean():8.4f} ± {an.std():.4f} "
                f"{col(c,'colisiones_015').mean():7.3f} "
                f"{contacto(c):5d}/{n_ae:<2d} "
                f"{col(c,'cbf_frac_pasos_intervenidos').mean():8.3f} "
                f"{col(c,'cbf_fallbacks').sum():6.0f}{marca}"
            )
        L.append("")
        L.append("  'contact' = agente-episodios con d_min < 0.075 m (radio del")
        L.append("  chasis) = contacto físico con la pared. 'anillo' = cobertura")
        L.append("  del AoI en la banda de 0.30 m junto a las paredes.")
        L.append("")

        # ── Comparación pareada contra la base ───────────────────────────
        L.append("TABLA 2 — COMPARACIÓN PAREADA CONTRA LA BASE (ℓa=0.05, w_ω=0.30)")
        L.append(f"  {'ℓa':>5s} {'w_ω':>5s} {'Δ atascados (IC95)':>30s} "
                 f"{'Δ cobertura (IC95)':>30s} {'Δ anillo':>12s}")
        L.append("  " + "-" * 84)
        idx_b = {int(r["semilla"]): r for r in P[base]}
        for c in cfgs:
            if c == base:
                continue
            idx_c = {int(r["semilla"]): r for r in P[c]}
            com = sorted(set(idx_b) & set(idx_c))

            def delta(campo):
                return np.array([
                    float(idx_c[s][campo]) - float(idx_b[s][campo])
                    for s in com
                ])

            def ic(x):
                n = len(x); m = x.mean()
                ee = x.std(ddof=1) / math.sqrt(n) if n > 1 else 0.0
                return m, m - 1.96 * ee, m + 1.96 * ee

            ma, la_, ha = ic(delta("agentes_atascados"))
            mc, lc, hc  = ic(delta("cobertura_aoi_final"))
            man, _, _   = ic(delta("cobertura_anillo"))
            sa = "*" if (la_ < 0 and ha < 0) or (la_ > 0 and ha > 0) else " "
            sc = "*" if (lc < 0 and hc < 0) or (lc > 0 and hc > 0) else " "
            L.append(f"  {c[0]:5.2f} {c[1]:5.2f} "
                     f"{ma:+7.3f} [{la_:+.3f}, {ha:+.3f}]{sa} "
                     f"{mc:+8.4f} [{lc:+.4f}, {hc:+.4f}]{sc} "
                     f"{man:+11.4f}")
        L.append("  (* = el IC95 excluye el cero)")
        L.append("")

        # ── Criterio de éxito ────────────────────────────────────────────
        n_ae_base = len(P[base]) * n_ag
        at_base = col(base, "agentes_atascados").sum()
        L.append("CRITERIO DE ÉXITO")
        L.append(f"  atascos ≤ 10/{n_ae_base} (base: {at_base:.0f}/{n_ae_base}),")
        L.append("  sin subir colisiones a 0.15 m ni contacto con pared.")
        col015_base = col(base, "colisiones_015").mean()
        ct_base = contacto(base)
        sanas = []
        for c in cfgs:
            at = col(c, "agentes_atascados").sum()
            ok = (at <= 10
                  and col(c, "colisiones_015").mean() <= col015_base + 1e-9
                  and contacto(c) <= ct_base)
            if ok:
                sanas.append((c, at))
        if sanas:
            L.append("  CELDAS QUE CUMPLEN:")
            for c, at in sorted(sanas, key=lambda t: t[1]):
                L.append(f"    ℓa={c[0]:.2f} w_ω={c[1]:.2f} → {at:.0f} atascos")
        else:
            L.append("  NINGUNA celda cumple. El bloqueo no se resuelve por")
            L.append("  sintonización del filtro: habría que atacarlo por diseño")
            L.append("  (comportamiento de escape explícito). NO se avanza a la")
            L.append("  Fase 2 (barrido de ruido sobre configuración sana).")
        L.append("")
        L.append("NOTA: `dist_min_pared_a*`, `atasco_dist_pared_a*`,")
        L.append("`atasco_h_min1_a*` y `atasco_h_min2_a*` se vuelcan con 8")
        L.append("decimales, SIN redondear. h_min1/h_min2 son los dos valores")
        L.append("de h de pared más pequeños en el instante del atasco: permiten")
        L.append("derivar la clasificación esquina/pared con el umbral que se")
        L.append("quiera (h_min2 pequeño ⇒ dos barreras activas ⇒ esquina).")

        resumen = "\n".join(L)
        ruta_txt.write_text(resumen, encoding="utf-8")
        print(f"[expG] Resumen → {ruta_txt}\n")
        print(resumen)

    def _correr_configuracion(self) -> List[Dict[str, object]]:
        """Corre las N_EPISODIOS_LOTE semillas con la configuración vigente."""
        resultados: List[Dict[str, object]] = []
        iteraciones_por_log = max(1, int(round(PERIODO_LOG_S / DT_ENV)))

        for indice, semilla in enumerate(SEMILLAS_LOTE):
            if not self._reiniciar_episodio(semilla):
                break

            terminado = False
            while not terminado and not self._webots_cerrado:
                if not self._avanzar(self.pasos_por_decision):
                    break
                terminado = self._decidir_y_actuar()

                if self._paso_episodio % iteraciones_por_log == 0:
                    print(f"  [sync] tick={self._tick} "
                          f"antiguedad_max={self._antiguedad_max} ticks | "
                          f"decisiones_con_pose_vieja="
                          f"{self._decisiones_pose_vieja}")

            if self._webots_cerrado:
                print("[lote] Webots cerró; guardando resultados parciales.")
                break

            cobertura = 1.0 - float(np.mean(self.env._field._grid_aoi))
            latencia = (
                self._suma_latencia_ms / self._n_muestras_latencia
                if self._n_muestras_latencia else 0.0
            )
            fila: Dict[str, object] = {
                "episodio":              indice + 1,
                "semilla":               semilla,
                "n_agentes":             self.n_agentes,
                # ── [EXP F] Configuración de degradación de pose ─────────
                "cobertura_anillo":      round(self._cobertura_anillo(), 6),
                # ── Escape (0 si ESCAPE_ACTIVO=False) ───────────────────
                "escape_activo":         ESCAPE_ACTIVO,
                "escape_n_total":        sum(self._esc_n_escapes),
                "escape_decisiones":     sum(self._esc_decisiones),
                "escape_frac_ciclo":     round(
                    sum(self._esc_decisiones)
                    / (self._paso_episodio * self.n_agentes), 4,
                ) if self._paso_episodio else 0.0,
                "escape_infactibles":    sum(self._esc_infactibles),
                "escape_agotados":       sum(self._esc_agotados),
                "escape_filtro_modifico": sum(self._esc_filtro_modifico),
                "escape_filtro_magnitud": round(
                    sum(self._esc_filtro_magnitud)
                    / sum(self._esc_filtro_modifico), 4,
                ) if sum(self._esc_filtro_modifico) > 0 else 0.0,
                "escape_falsos_positivos": sum(self._esc_falsos_positivos),
                # ── [EXP G] Parámetros vigentes del filtro ───────────────
                "cbf_ele_a":             round(self._ele_a, 4),
                "cbf_w_omega":           round(self._w_omega, 4),
                "cbf_d_segura":          round(self._d_segura, 4),
                "cbf_d_robots":          round(self._d_robots, 4),
                "sigma_pos_mm":          round(self._sigma_pos * 1000.0, 2),
                "sigma_theta_deg":       round(math.degrees(
                    self._sigma_pos * math.sqrt(2.0) / L_MARCADORES
                ), 3) if self._sigma_pos > 0 else 0.0,
                "retardo_extra":         self._retardo_extra,
                "violaciones_margen":    sum(self._violo_margen),
                "cobertura_aoi_final":   round(cobertura, 6),
                "colisiones_015":        len(self._pares_col_contacto),
                "colisiones_022":        len(self._pares_col_margen),
                "agentes_atascados":     sum(self._atasco_detectado),
                "pasos_totales":         self._paso_episodio,
                "antiguedad_max_ticks":  self._antiguedad_max,
                "decisiones_pose_vieja": self._decisiones_pose_vieja,
                "latencia_media_ms":     round(latencia, 3),
                # ── Filtro CBF (0 si CBF_ACTIVO=False) ──────────────────
                "cbf_activo":            CBF_ACTIVO,
                "cbf_intervenciones":    sum(self._cbf_intervenciones),
                "cbf_int_pared":         sum(self._cbf_int_pared),
                "cbf_int_robot":         sum(self._cbf_int_robot),
                "cbf_fallbacks":         sum(self._cbf_fallbacks),
                "cbf_frac_pasos_intervenidos": round(
                    sum(self._cbf_intervenciones)
                    / (self._paso_episodio * self.n_agentes), 4,
                ) if self._paso_episodio else 0.0,
                "cbf_magnitud_media": round(
                    sum(self._cbf_suma_magnitud)
                    / sum(self._cbf_intervenciones), 4,
                ) if sum(self._cbf_intervenciones) > 0 else 0.0,
            }
            for i in range(self.n_agentes):
                fila[f"atascado_a{i}"]        = self._atasco_detectado[i]
                fila[f"paso_atasco_a{i}"]     = self._atasco_paso[i]
                # [EXP G] SIN REDONDEO (8 decimales). El redondeo a 4 hizo que
                # una verificación diera 0/90 donde el contador interno decía
                # 9/90: valores como 0.179996 se mostraban como 0.1800.
                fila[f"dist_min_pared_a{i}"]  = (
                    f"{self._dist_min_pared[i]:.8f}"
                    if math.isfinite(self._dist_min_pared[i]) else "-1"
                )
                # Diagnóstico del atasco (−1 / False / NaN si no hubo).
                fila[f"atasco_vecino_cerca_a{i}"] = self._atasco_vecino_cerca[i]
                fila[f"atasco_dist_vecino_a{i}"]  = self._atasco_dist_vecino[i]
                fila[f"atasco_v_media_a{i}"]      = self._atasco_v_media[i]
                fila[f"atasco_w_media_a{i}"]      = self._atasco_w_media[i]
                fila[f"atasco_dist_pared_a{i}"]   = (
                    f"{self._atasco_dist_pared[i]:.8f}"
                )
                fila[f"atasco_h_min1_a{i}"] = f"{self._atasco_h_min1[i]:.8f}"
                fila[f"atasco_h_min2_a{i}"] = f"{self._atasco_h_min2[i]:.8f}"
                # Ciclo de trabajo del escape DESAGREGADO por agente: el
                # agregado no distingue "5 robots escapando 1 vez" de
                # "1 robot escapando 5 veces" (diagnósticos opuestos).
                fila[f"escape_n_a{i}"]          = self._esc_n_escapes[i]
                fila[f"escape_decisiones_a{i}"] = self._esc_decisiones[i]
                fila[f"escape_frac_a{i}"]       = round(
                    self._esc_decisiones[i] / self._paso_episodio, 4
                ) if self._paso_episodio else 0.0
                fila[f"escape_infactibles_a{i}"] = self._esc_infactibles[i]
                fila[f"escape_agotados_a{i}"]    = self._esc_agotados[i]
                fila[f"escape_falsos_a{i}"]      = self._esc_falsos_positivos[i]
            resultados.append(fila)

            print(f"[lote] ep {indice+1}/{N_EPISODIOS_LOTE} semilla={semilla} "
                  f"cob={cobertura:.4f} col015={fila['colisiones_015']} "
                  f"col022={fila['colisiones_022']} "
                  f"atascados={fila['agentes_atascados']}/{self.n_agentes} "
                  f"cbf_frac={fila['cbf_frac_pasos_intervenidos']} "
                  f"viol_margen={fila['violaciones_margen']}")

        return resultados

    def _escribir_barrido(self, filas: List[Dict[str, object]]) -> None:
        """
        [EXP F] Vuelca el CSV del barrido y el resumen con el análisis de
        umbral, comparación pareada contra la base e interacción.
        """
        DIR_RESULTADOS.mkdir(parents=True, exist_ok=True)
        n_ag = self.n_agentes
        # [EXP H] Con el escape activo la base es SANA y el barrido responde
        # una pregunta distinta a la del Exp F (que midió la perturbación de
        # un sistema bloqueado). Salidas separadas para que ambas tablas
        # convivan y sean comparables.
        pref = "expH" if ESCAPE_ACTIVO else "expF"
        ruta_csv = DIR_RESULTADOS / f"{pref}_barrido_{n_ag}agentes.csv"
        ruta_txt = DIR_RESULTADOS / f"{pref}_resumen_{n_ag}agentes.txt"

        with open(ruta_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
            w.writeheader()
            w.writerows(filas)
        print(f"\n[expF] CSV → {ruta_csv}")

        # ── Agrupar por configuración ────────────────────────────────────
        def clave(r):
            return (float(r["sigma_pos_mm"]), int(r["retardo_extra"]))

        cfgs = sorted({clave(r) for r in filas})
        por_cfg = {c: [r for r in filas if clave(r) == c] for c in cfgs}
        base = (0.0, 0)

        def agg(c, campo):
            return np.array([float(r[campo]) for r in por_cfg[c]])

        L: List[str] = []
        L.append("EXPERIMENTO F — robustez a ruido y latencia de pose")
        L.append(f"{n_ag} agentes con física real · {len(SEMILLAS_LOTE)} "
                 f"semillas por configuración · modelo={NOMBRE_MODELO} · "
                 f"CBF={'ON' if CBF_ACTIVO else 'OFF'}")
        L.append(f"Barrido factorial completo: {len(BARRIDO_SIGMAS)} niveles "
                 f"de ruido × {len(BARRIDO_RETARDOS)} de latencia = "
                 f"{len(cfgs)} configuraciones, {len(filas)} episodios.")
        L.append("=" * 78)
        L.append("")
        L.append("VALIDEZ DEL EXPERIMENTO — separación de poses")
        L.append("  Las poses DEGRADADAS (ruido + retardo) van ÚNICAMENTE al env")
        L.append("  y al filtro CBF: es lo que el sistema cree ver.")
        L.append("  TODAS las métricas físicas — colisiones (0.15 y 0.22 m),")
        L.append("  d_min a pared, detector de atasco y violaciones del margen —")
        L.append("  se calculan con las poses REALES del GPS/Compass, porque")
        L.append("  miden lo que efectivamente ocurrió. Sin esta separación el")
        L.append("  experimento mediría el error de medición, no la seguridad.")
        L.append("")
        L.append("ESCALA DEL RUIDO ANGULAR")
        L.append(f"  σ_θ = σ_pos·√2/L con L = {L_MARCADORES} m (constelación de")
        L.append("  marcadores). OptiTrack no mide heading: lo estima de la")
        L.append("  constelación, así que el error angular queda determinado por")
        L.append("  el posicional dividido por la separación entre marcadores.")
        L.append("  Es ~3× MÁS AGRESIVA que la del DomainRandomizer del")
        L.append("  entrenamiento (10 mm ↔ 5.4° acá vs 1.7° allá): se busca el")
        L.append("  umbral de ruptura, no reproducir el entrenamiento.")
        L.append("")
        L.append("  ⚠ Los umbrales de este reporte deben enunciarse como")
        L.append(f"    'σ_pos con constelación L = {L_MARCADORES} m', NO como")
        L.append("    σ_pos a secas: con otra constelación el mismo error")
        L.append("    posicional produce otro error angular.")
        L.append("")

        # ── Tabla principal ──────────────────────────────────────────────
        L.append("TABLA 1 — TODAS LAS CONFIGURACIONES")
        L.append(f"  {'σ_pos':>6s} {'σ_θ':>6s} {'ret':>4s} {'cobertura':>16s} "
                 f"{'atascos':>10s} {'col015':>7s} {'col022':>7s} "
                 f"{'CBF frac':>9s} {'viol.marg':>10s} {'fallb':>6s}")
        L.append(f"  {'[mm]':>6s} {'[°]':>6s} {'[dec]':>4s}")
        L.append("  " + "-" * 94)
        for c in cfgs:
            sp, ret = c
            sth = math.degrees(sp / 1000.0 * math.sqrt(2.0) / L_MARCADORES)
            cob = agg(c, "cobertura_aoi_final")
            at  = agg(c, "agentes_atascados")
            n_ae = len(por_cfg[c]) * n_ag
            marca = "  ← BASE" if c == base else ""
            L.append(
                f"  {sp:6.0f} {sth:6.2f} {ret:4d} "
                f"{cob.mean():8.4f} ± {cob.std():.4f} "
                f"{at.sum():5.0f}/{n_ae:<4d} "
                f"{agg(c,'colisiones_015').mean():7.3f} "
                f"{agg(c,'colisiones_022').mean():7.3f} "
                f"{agg(c,'cbf_frac_pasos_intervenidos').mean():9.3f} "
                f"{agg(c,'violaciones_margen').sum():6.0f}/{n_ae:<3d} "
                f"{agg(c,'cbf_fallbacks').sum():6.0f}{marca}"
            )
        L.append("")

        # ── Comparación pareada contra la base ───────────────────────────
        L.append("TABLA 2 — COMPARACIÓN PAREADA POR SEMILLA CONTRA LA BASE")
        L.append("  (base = 0 mm de ruido, 0 decisiones de retardo)")
        L.append(f"  {'σ_pos':>6s} {'ret':>4s} {'Δ cobertura (IC95)':>34s} "
                 f"{'Δ atascados (IC95)':>30s}")
        L.append("  " + "-" * 78)
        idx_base = {int(r["semilla"]): r for r in por_cfg[base]}
        for c in cfgs:
            if c == base:
                continue
            idx_c = {int(r["semilla"]): r for r in por_cfg[c]}
            comunes = sorted(set(idx_base) & set(idx_c))
            dc = np.array([
                float(idx_c[s]["cobertura_aoi_final"])
                - float(idx_base[s]["cobertura_aoi_final"]) for s in comunes
            ])
            da = np.array([
                float(idx_c[s]["agentes_atascados"])
                - float(idx_base[s]["agentes_atascados"]) for s in comunes
            ])
            def ic(x):
                n = len(x); m = x.mean()
                ee = x.std(ddof=1) / math.sqrt(n) if n > 1 else 0.0
                return m, m - 1.96 * ee, m + 1.96 * ee
            mc, lc, hc = ic(dc)
            ma, la, ha = ic(da)
            sig_c = "*" if (lc < 0 and hc < 0) or (lc > 0 and hc > 0) else " "
            sig_a = "*" if (la < 0 and ha < 0) or (la > 0 and ha > 0) else " "
            L.append(f"  {c[0]:6.0f} {c[1]:4d} "
                     f"{mc:+8.4f} [{lc:+.4f}, {hc:+.4f}]{sig_c} "
                     f"{ma:+7.3f} [{la:+.3f}, {ha:+.3f}]{sig_a}")
        L.append("  (* = el IC95 excluye el cero)")
        L.append("")

        # ── [EXP H] Comportamiento del escape bajo degradación ───────────
        if ESCAPE_ACTIVO:
            L.append("TABLA 2b — EL ESCAPE COMO CONSUMIDOR DE LA POSE")
            L.append("  Su detección usa desplazamiento medido, intervención")
            L.append("  del filtro y distancia a barrera: DOS de los tres son")
            L.append("  sensibles al ruido. Con σ alto podría (a) dejar de")
            L.append("  dispararse porque el ruido simula movimiento donde no")
            L.append("  lo hay, o (b) dispararse sin motivo.")
            L.append("")
            L.append(f"  {'σ_pos':>6s} {'ret':>4s} {'activ/ag-ep':>12s} "
                     f"{'ciclo':>8s} {'infact':>7s} {'agotad':>7s} "
                     f"{'falsos+':>8s}")
            L.append("  " + "-" * 56)
            n_ae_cfg = len(SEMILLAS_LOTE) * n_ag
            for c in cfgs:
                L.append(
                    f"  {c[0]:6.0f} {c[1]:4d} "
                    f"{agg(c,'escape_n_total').sum()/n_ae_cfg:12.2f} "
                    f"{agg(c,'escape_frac_ciclo').mean():8.4f} "
                    f"{agg(c,'escape_infactibles').sum():7.0f} "
                    f"{agg(c,'escape_agotados').sum():7.0f} "
                    f"{agg(c,'escape_falsos_positivos').sum():8.0f}"
                )
            L.append("")
            L.append(f"  'falsos+' = activaciones en que la distancia REAL a la")
            L.append(f"  barrera más cercana superaba {ESC_UMBRAL_FALSO} m: no")
            L.append("  había nada de qué escapar. Se evalúa con poses del GPS,")
            L.append("  no con las degradadas que dispararon la detección.")
            L.append("")
            L.append("  MECANISMO A CONTRASTAR: si las activaciones caen a cero")
            L.append("  con σ alto Y los atascos suben, el ruido está inhibiendo")
            L.append("  el escape (el ruido simula movimiento y la detección de")
            L.append("  estancamiento nunca acumula sus 6 decisiones).")
            L.append("")

        # ── Interacción ruido × latencia ─────────────────────────────────
        L.append("TABLA 3 — ¿HAY INTERACCIÓN ENTRE RUIDO Y LATENCIA?")
        L.append("  Si el efecto conjunto NO es la suma de los individuales,")
        L.append("  el margen tolerable en uno DEPENDE del otro y la")
        L.append("  recomendación operativa cambia.")
        L.append("")
        sigma_max = max(BARRIDO_SIGMAS) * 1000.0
        ret_max   = max(BARRIDO_RETARDOS)
        esquina   = (sigma_max, ret_max)
        solo_ruido    = (sigma_max, 0)
        solo_latencia = (0.0, ret_max)
        if all(c in por_cfg for c in (esquina, solo_ruido, solo_latencia)):
            def media(c, campo):
                return float(agg(c, campo).mean())
            for campo, etiqueta in (
                ("cobertura_aoi_final", "cobertura"),
                ("agentes_atascados",   "atascados"),
                ("cbf_frac_pasos_intervenidos", "CBF frac"),
            ):
                b  = media(base, campo)
                er = media(solo_ruido, campo) - b
                el = media(solo_latencia, campo) - b
                ec = media(esquina, campo) - b
                inter = ec - (er + el)
                L.append(f"  {etiqueta}:")
                L.append(f"      efecto sólo ruido ({sigma_max:.0f} mm)      = {er:+.4f}")
                L.append(f"      efecto sólo latencia ({ret_max} dec)     = {el:+.4f}")
                L.append(f"      suma de efectos individuales     = {er+el:+.4f}")
                L.append(f"      efecto conjunto medido           = {ec:+.4f}")
                L.append(f"      INTERACCIÓN (conjunto − suma)    = {inter:+.4f}")
        L.append("")

        resumen = "\n".join(L)
        ruta_txt.write_text(resumen, encoding="utf-8")
        print(f"[expF] Resumen → {ruta_txt}\n")
        print(resumen)

    def _escribir_resultados(self, resultados: List[Dict[str, object]]) -> None:
        """Vuelca el CSV por episodio y el resumen agregado."""
        DIR_RESULTADOS.mkdir(parents=True, exist_ok=True)
        n_ag = self.n_agentes

        with open(self.ruta_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(resultados[0].keys()))
            w.writeheader()
            w.writerows(resultados)
        print(f"[lote] CSV → {self.ruta_csv}")

        n = len(resultados)
        cob    = np.array([float(r["cobertura_aoi_final"])   for r in resultados])
        c015   = np.array([float(r["colisiones_015"])        for r in resultados])
        c022   = np.array([float(r["colisiones_022"])        for r in resultados])
        atas   = np.array([float(r["agentes_atascados"])     for r in resultados])
        antig  = np.array([float(r["antiguedad_max_ticks"])  for r in resultados])
        viejas = np.array([float(r["decisiones_pose_vieja"]) for r in resultados])
        lat    = np.array([float(r["latencia_media_ms"])     for r in resultados])
        dists  = [
            float(r[f"dist_min_pared_a{i}"])
            for r in resultados for i in range(n_ag)
            if float(r[f"dist_min_pared_a{i}"]) >= 0.0
        ]

        # ── Diagnóstico agregado de atascos ──────────────────────────────
        atascos: List[Dict[str, float]] = []
        for r in resultados:
            for i in range(n_ag):
                if r[f"atascado_a{i}"]:
                    atascos.append({
                        "vecino_cerca": bool(r[f"atasco_vecino_cerca_a{i}"]),
                        "dist_vecino":  float(r[f"atasco_dist_vecino_a{i}"]),
                        "v_media":      float(r[f"atasco_v_media_a{i}"]),
                        "w_media":      float(r[f"atasco_w_media_a{i}"]),
                        "dist_pared":   float(r[f"atasco_dist_pared_a{i}"]),
                    })
        n_atascos = len(atascos)
        n_agente_eps = n * n_ag

        L: List[str] = []
        L.append(f"LOTE MULTI-ROBOT — {n_ag} agentes con física real (Webots)")
        L.append(f"Política: {NOMBRE_MODELO} · deterministic=True")
        L.append(f"Arquitectura: {n_ag} × controlador_agente + 1 coordinador")
        L.append(f"(supervisor). Emitter/Receiver, canales "
                 f"{CANAL_SUBIDA} (subida) / {CANAL_BAJADA} (bajada).")
        L.append("=" * 70)
        L.append(f"Episodios ejecutados : {n}   (agente-episodios: {n_agente_eps})")
        L.append("")
        L.append("COBERTURA Y COLISIONES")
        L.append(f"  cobertura AoI final : {float(np.mean(cob)):.4f} ± "
                 f"{float(np.std(cob)):.4f}")
        L.append(f"  colisiones_015      : {float(np.mean(c015)):.3f} ± "
                 f"{float(np.std(c015)):.3f}   "
                 f"({100.0*float(np.mean(c015 > 0)):.1f}% de eps con ≥1)")
        L.append(f"  colisiones_022      : {float(np.mean(c022)):.3f} ± "
                 f"{float(np.std(c022)):.3f}   "
                 f"({100.0*float(np.mean(c022 > 0)):.1f}% de eps con ≥1)")
        L.append("")
        L.append("  UMBRALES: 'colisiones_015' usa 0.15 m entre centros, que es")
        L.append("  el CONTACTO FÍSICO de los chasis (radio 0.075 m cada uno) y")
        L.append("  es el D_SAFE del env — el umbral con el que se midieron")
        L.append("  TODAS las métricas previas (experimentos A-D y sanidad), por")
        L.append("  lo que es la columna COMPARABLE. 'colisiones_022' usa 0.22 m,")
        L.append("  que incluye ~7 cm de margen operativo sobre el contacto.")
        L.append("")
        L.append("ATASCOS")
        L.append(f"  agente-episodios con atasco : {n_atascos}/{n_agente_eps}  "
                 f"({100.0*n_atascos/n_agente_eps:.1f}%)")
        L.append(f"  episodios con ≥1 atascado   : "
                 f"{100.0*float(np.mean(atas > 0)):.1f}%")
        if dists:
            L.append(f"  dist. mín. centro→pared [m] : min={min(dists):.4f}  "
                     f"media={float(np.mean(dists)):.4f}")
        L.append("")
        if atascos:
            con_vecino = sum(1 for a in atascos if a["vecino_cerca"])
            L.append("DIAGNÓSTICO DE ATASCOS")
            L.append(f"  con vecino dentro de comm_radius ({COMM_RADIUS} m): "
                     f"{con_vecino}/{n_atascos}")
            ds = [a["dist_vecino"] for a in atascos if a["dist_vecino"] >= 0]
            if ds:
                L.append(f"  distancia al vecino más cercano [m] : "
                         f"min={min(ds):.3f}  media={float(np.mean(ds)):.3f}")
            L.append(f"  acción media previa al atasco : "
                     f"v={float(np.mean([a['v_media'] for a in atascos])):+.4f} m/s  "
                     f"ω={float(np.mean([a['w_media'] for a in atascos])):+.4f} rad/s")
            L.append(f"  distancia a pared al atascarse [m] : "
                     f"media={float(np.mean([a['dist_pared'] for a in atascos])):.4f}")
            L.append("")
            L.append("  HIPÓTESIS: si los atascos coinciden con vecino cerca, el")
            L.append("  mecanismo es que la evitación inter-agente empuja contra")
            L.append("  la pared (y más densidad AGRAVA). Si no hay vecino cerca,")
            L.append("  es el gap chasis-vs-punto (el env trata al agente como")
            L.append("  punto; Webots le da radio 0.075 m) y la densidad no")
            L.append("  debería agravarlo.")
            L.append("")
        if CBF_ACTIVO:
            interv = np.array([float(r["cbf_intervenciones"]) for r in resultados])
            frac   = np.array([
                float(r["cbf_frac_pasos_intervenidos"]) for r in resultados
            ])
            mag    = np.array([
                float(r["cbf_magnitud_media"]) for r in resultados
                if float(r["cbf_intervenciones"]) > 0
            ])
            n_par  = float(np.sum([float(r["cbf_int_pared"]) for r in resultados]))
            n_rob  = float(np.sum([float(r["cbf_int_robot"]) for r in resultados]))
            n_fb   = float(np.sum([float(r["cbf_fallbacks"]) for r in resultados]))
            L.append("FILTRO CBF (safety shield)")
            L.append(f"  parámetros : ℓa={ELE_A}, α={ALFA_CBF}, "
                     f"d_pared={D_SEGURA_PUNTO}, d_robots={D_SEGURA_ROBOTS}, "
                     f"w={W_OMEGA}")
            L.append(f"  intervenciones por episodio (todos los agentes) : "
                     f"{float(np.mean(interv)):.1f}  max={int(np.max(interv))}")
            L.append(f"  fracción de pasos-agente intervenidos           : "
                     f"{float(np.mean(frac)):.4f}")
            if mag.size:
                L.append(f"  magnitud media de la modificación              : "
                         f"{float(np.mean(mag)):.4f}")
            total_int = n_par + n_rob
            if total_int > 0:
                L.append(f"  barrera activa: pared {n_par:.0f} "
                         f"({100*n_par/total_int:.1f}%) · "
                         f"robot-robot {n_rob:.0f} "
                         f"({100*n_rob/total_int:.1f}%)")
            L.append(f"  fallbacks del QP (u=0)                          : "
                     f"{n_fb:.0f}")
            L.append("")
            L.append("  Barreras robot-robot: reparto de responsabilidad 50/50")
            L.append("  sobre los puntos de mira. d_robots=0.25 m entre puntos")
            L.append("  garantiza ≥0.15 m entre CENTROS en el peor caso (ambos")
            L.append("  enfrentados), que es el contacto de chasis.")
            L.append("")
        L.append("SINCRONÍA")
        L.append(f"  antigüedad máxima de pose  : {int(np.max(antig))} ticks "
                 f"(media por ep {float(np.mean(antig)):.1f})")
        L.append(f"  decisiones con pose vieja  : {int(np.sum(viejas))} "
                 f"(umbral > {UMBRAL_ANTIGUEDAD_TICKS} ticks)")
        L.append(f"  latencia media pose→acción : {float(np.mean(lat)):.2f} ms")
        L.append("")
        L.append("  NOTA: Webots no garantiza el orden de ejecución entre")
        L.append("  controladores dentro de un tick, así que una antigüedad de")
        L.append("  0-1 ticks es estructural y esperada, no un fallo.")

        resumen = "\n".join(L)
        self.ruta_resumen.write_text(resumen, encoding="utf-8")
        print(f"[lote] Resumen → {self.ruta_resumen}\n")
        print(resumen)


def main() -> None:
    """
    Punto de entrada que Webots invoca al cargar el controlador.

    El `finally` garantiza la parada de los robots ante CUALQUIER salida:
    fin normal, excepción no capturada o interrupción por teclado. Junto con
    el handler de `atexit` registrado en el constructor, es la red de
    seguridad que en el laboratorio evita que cinco robots sigan andando si
    el programa muere. En Webots es inofensivo, y queda ejercitado por todos
    los lotes.
    """
    warnings.simplefilter("always", RuntimeWarning)
    coordinador = None
    try:
        coordinador = CoordinadorEnjambre()
        coordinador.correr()
    except KeyboardInterrupt:
        print("\n[coordinador] interrupción por teclado — deteniendo robots.")
    finally:
        if coordinador is not None:
            coordinador._detener_seguro()


if __name__ == "__main__":
    main()
