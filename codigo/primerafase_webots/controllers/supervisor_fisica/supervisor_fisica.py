"""
supervisor_fisica.py
====================
Controlador único del demo CON FÍSICA REAL DE RUEDAS (Webots R2025a).
Paralelo a `supervisor_cobertura/`; NO comparte código directamente con
él (cada controlador es autocontenido — su propia copia de `lib/`).

Diferencias respecto al demo cinemático
---------------------------------------
  - El Robot Pololu del mundo lleva `supervisor TRUE`: es a la vez agente
    físico Y supervisor. Así el controlador puede acceder a sus motores y
    sensores (`getDevice`) Y mover los hotspots por DEF (`getFromDef`).
  - 1 SOLO robot. Validar la mecánica de calibración (signos, escalas) es
    el objetivo de esta corrida; escalar a 5 robots es paso posterior.
  - La pose del robot la produce la FÍSICA de Webots (GPS + Compass), NO
    el integrador del env. El env corre en `modo_poses_externas=True` y
    el supervisor le INYECTA la pose cada paso antes de `env.step(...)`.
  - Los hotspots siguen siendo virtuales y los mueve el env (idéntico al
    demo cinemático).

Loop por iteración
------------------
    1. acción = modelo.predict(obs_actual, deterministic=True).
    2. (v, ω) = acción → (φ̇_R, φ̇_L) por modelo diferencial inverso.
    3. motor_1.setVelocity(SIGNO_MOTOR_1 · φ̇_R · ...) y motor_2 igual.
    4. supervisor.step(N_TICKS) — Webots avanza la física N_TICKS ticks.
    5. Leer pose física: GPS → (x_w, y_w) y Compass → θ.
    6. Mapear a marco env: x_env = x_w + Wx/2, etc. + OFFSET_HEADING.
    7. inyectar_poses_externas({"robot_0": (x_env, y_env, θ_env)}).
    8. obs_actual, _, _, truncs, _ = env.step({"robot_0": acción}).
    9. Mover los nodos `obs1..obs3` de Webots a las posiciones que el env
       acaba de avanzar (env._field.posiciones_objetivos).
   10. Si truncs[robot_0]: reset y re-alinear poses.

Comportamiento esperado
-----------------------
Con 1 agente, el `neighbor_embedding` (dims 8–15 de la obs) va en ceros y
la penalización CBF también — la política no tiene "contexto social". El
robot NO va a exhibir coordinación; va a moverse hacia los hotspots
(reward de gradiente) y a explorar (AoI). El propósito del demo es
validar la MECÁNICA del loop (modelo de ruedas, signos, marcos), no el
comportamiento emergente.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
import sys
import warnings
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# sys.path: agregar carpeta del controlador para que el paquete `lib` resuelva
# ─────────────────────────────────────────────────────────────────────────────
_CARPETA_CONTROLADOR: Path = Path(__file__).resolve().parent
if str(_CARPETA_CONTROLADOR) not in sys.path:
    sys.path.insert(0, str(_CARPETA_CONTROLADOR))

from controller import Supervisor  # type: ignore  # provisto por Webots

from stable_baselines3 import PPO

from lib.swarm_env_skeleton import CyanobacteriaMonitoringEnv
from lib.concentration_dynamics import V_MAX, OMEGA_MAX


# =============================================================================
# MODO DE OPERACIÓN — instrumentación de calibración
# =============================================================================
# Cambiar este string a mano para alternar entre los modos. Recomendación de
# calibración (de menor a mayor acoplamiento):
#
#   "actuacion"  → Lazo ABIERTO. Comanda (V_TEST, OMEGA_TEST) fijo a los
#                  motores; no usa env ni política. Imprime (v,ω) → (φ̇_R, φ̇_L)
#                  y la pose leída. Valida SIGNO_MOTOR_1/2 y el mapeo de ruedas.
#
#   "pose"       → Solo LECTURA. Motores apagados. Imprime cada paso la pose
#                  (x_env, y_env, θ_env) leída desde GPS+Compass, junto con
#                  las lecturas crudas. Movés el robot a mano en el editor y
#                  validás OFFSET_HEADING_RAD y el offset de marco (+1.5).
#
#   "politica"   → LAZO CERRADO. Lo de producción: política → ruedas → física
#                  → pose → política. Requiere modelo cargado y env.
#
#   "lote"       → EXPERIMENTO A. Lazo cerrado idéntico a "politica", pero
#                  corre N_EPISODIOS_LOTE episodios con SEMILLAS_LOTE fijas,
#                  teletransporta el robot a la pose inicial del env en cada
#                  episodio, registra el detector de atasco (solo registro) y
#                  escribe resultados/experimento_A_atascos.csv + resumen.
#                  Al terminar cierra Webots (si SALIR_AL_TERMINAR_LOTE).
#
# Default arranca en "actuacion" para que el primer Play no dependa de signos
# correctos: el robot ejecuta un comando conocido y vos observás qué pasa.
MODO: str = "lote"

# ── Parámetros del modo "actuacion" (lazo abierto) ──────────────────────────
# Comando fijo en el marco del cuerpo: avanzar lento, sin girar. Cambiar a
# (0.0, 1.0) por ejemplo para verificar el sentido de giro con ω>0.
V_TEST:     float = 0.1    # [m/s]
OMEGA_TEST: float = 0.0    # [rad/s]

# Periodo de impresión del log [s]. A dt_env=0.1s, 1.0s ⇒ 1 print cada 10 iter.
PERIODO_LOG_S: float = 1.0

# ── Parámetros del modo "lote" (EXPERIMENTO A — corrida por lotes) ──────────
# Corre N episodios con semillas fijas (misma familia que el protocolo de
# evaluación de RESULTADO_PRIMERO: seed_ep = 42·10000 + i), registra el
# detector de atasco (SOLO REGISTRO, sin recovery) y escribe CSV + resumen.
# Al inicio de cada episodio, el supervisor TELETRANSPORTA su propio robot a
# la pose inicial sorteada por el env — sin esto, el episodio i+1 arrancaría
# con el robot donde quedó en el episodio i (p. ej. pegado a la pared) y el
# lote quedaría contaminado.
N_EPISODIOS_LOTE: int       = 18
SEMILLAS_LOTE:    List[int] = [42 * 10_000 + i for i in range(N_EPISODIOS_LOTE)]

# Detector de atasco: atascado si ‖Δpos‖ < 1 mm y |Δθ| < 0.5° durante
# N_PASOS_ATASCO pasos consecutivos del env (a dt=0.1 s → 2.0 s de quietud).
UMBRAL_ATASCO_POS_M:     float = 0.001
UMBRAL_ATASCO_THETA_RAD: float = math.radians(0.5)
N_PASOS_ATASCO:          int   = 20

# Si True, al terminar el lote cierra Webots (simulationQuit) — necesario
# para corridas headless (webots --batch). Si False, pausa la simulación.
SALIR_AL_TERMINAR_LOTE: bool = True


# =============================================================================
# FILTRO CBF DE EJECUCIÓN (safety shield) — ver lib/filtro_cbf.py
# =============================================================================
# NO es un MODO: aplica en "politica" y en "lote" cuando CBF_ACTIVO=True,
# para poder comparar con/sin CBF sobre las mismas semillas. Con el flag en
# False el módulo del filtro NI SIQUIERA se importa (regresión cero).
# En modo "lote", las salidas llevan sufijo "_cbf" para no pisar la corrida
# baseline sin filtro.
CBF_ACTIVO: bool = True

# Parámetros del filtro (calibrables).
ELE_A:          float = 0.05   # ℓa, adelanto del punto de mira [m]
ALFA_CBF:       float = 2.0    # α, ganancia clase-K [1/s]
D_SEGURA_PUNTO: float = 0.18   # margen del punto de mira a la pared [m]
                               # (r_chasis 0.075 + ℓa 0.05 + V_MAX·dt 0.031 + margen)
W_OMEGA:        float = 0.3    # peso de ω en el costo (preferir girar a frenar)


# =============================================================================
# CONFIGURACIÓN DEL DEMO (env)
# =============================================================================

# Idéntica a RESULTADO_PRIMERO salvo:
#   - n_agents = 1 (corrida de calibración; ver docstring del módulo).
#   - domain_rand = False (la fricción real la pone Webots; sumar fricción
#     simulada distorsionaría el delta sim-to-real que queremos observar).
#   - modo_poses_externas = True (poses provienen de GPS+Compass).
N_AGENTES:           int                 = 1
ARENA_SIZE:          Tuple[float, float] = (3.0, 3.0)
MAX_STEPS_EP:        int                 = 500
COMM_RADIUS:         float               = 1.0
DT_ENV:              float               = 0.1
N_HOTSPOTS:          int                 = 3
SEMILLA:             int                 = 42
DOMAIN_RAND_DEMO:    bool                = False
MODO_POSES_EXTERNAS: bool                = True

# Identificador del agente único (PettingZoo nombra "robot_0", "robot_1", ...).
AGENT_ID: str = "robot_0"


# =============================================================================
# MAPEO DE MARCOS (idéntico al demo cinemático)
# =============================================================================

# Origen del env en esquina (0,0); origen de Webots centrado.
OFFSET_X: float = ARENA_SIZE[0] / 2.0
OFFSET_Y: float = ARENA_SIZE[1] / 2.0

# Compensación angular: heading reportado por Compass → convención del env.
# El proto del robot tiene "adelante" en +Y local (ruedas en ±X). La fórmula
# `θ = atan2(mag[0], mag[1])` heredada del controlador MATLAB del lab ya
# reporta el heading respecto al eje Y del Compass rotado (rotation 0 0 1 π/2
# en el .wbt). Si la convención no calza con la del env (θ=0 ⇒ +X global), se
# corrige con este offset (calibración empírica al primer arranque: probar
# {0, ±π/2, π}).
OFFSET_HEADING_RAD: float = 0


# =============================================================================
# MODELO DIFERENCIAL DEL POLOLU 3pi+ (geometría Webots, NO hardware real)
# =============================================================================

# Radio de la rueda [m] — coincide con el Cylinder geometry del .wbt.
RADIO_RUEDA: float = 0.035

# Medio eje [m] — distancia centro→rueda. Coincide con anchor ±0.07 del .wbt.
MEDIO_EJE: float = 0.07

# Signos de motor (corrigen sentido de giro empírico al primer arranque).
# Default +1; el .m del lab usa signo negativo en su mapeo concreto, así que
# es probable que estos terminen en -1 después de la primera prueba visual.
SIGNO_MOTOR_1: int = -1   # rueda DERECHA (anchor +x en el .wbt)
SIGNO_MOTOR_2: int = -1   # rueda IZQUIERDA (anchor -x en el .wbt)

# Nombres de devices en el Robot.
NOMBRE_MOTOR_DERECHO:   str = "motor_1"
NOMBRE_MOTOR_IZQUIERDO: str = "motor_2"
NOMBRE_GPS:             str = "gps"
NOMBRE_COMPASS:         str = "compass"


# =============================================================================
# HOTSPOTS — DEFs en el .wbt para mover esferas virtuales
# =============================================================================

Z_OBJETIVO:    float     = 0.12
DEF_OBJETIVOS: List[str] = [f"obs{j+1}" for j in range(N_HOTSPOTS)]


# =============================================================================
# RUTA DEL MODELO
# =============================================================================

# Modelo a cargar. Cambiar esta constante para alternar entre políticas:
#   "modelo_PRIMERO" → política original (entrenada con reflexión elástica).
#   "modelo_sanidad" → política de la corrida de sanidad tesis_v2
#                      (entrenada CON bordes bloqueantes; ver
#                      experimentos/tesis_v2_sanidad/).
# El nombre se incorpora al de los archivos de salida del modo lote para no
# pisar corridas anteriores.
NOMBRE_MODELO: str = "modelo_sanidad"

RUTA_MODELO: Path = _CARPETA_CONTROLADOR / "modelos" / f"{NOMBRE_MODELO}.zip"

# Salidas del modo "lote" (Experimento A). Con CBF activo llevan sufijo
# "_cbf" para no sobreescribir la corrida baseline (dato de tesis).
DIR_RESULTADOS:    Path = _CARPETA_CONTROLADOR / "resultados"
# El sufijo combina modelo + estado del CBF. El modelo original sin CBF
# conserva el nombre histórico (sin sufijo) para no romper referencias.
_SUFIJO_CBF:   str = "_cbf" if CBF_ACTIVO else ""
_SUFIJO_MODEL: str = "" if NOMBRE_MODELO == "modelo_PRIMERO" else "_sanidad"
_SUFIJO_LOTE:  str = f"{_SUFIJO_MODEL}{_SUFIJO_CBF}"
RUTA_CSV_LOTE:     Path = DIR_RESULTADOS / f"experimento_A_atascos{_SUFIJO_LOTE}.csv"
RUTA_RESUMEN_LOTE: Path = DIR_RESULTADOS / f"resumen_experimento_A{_SUFIJO_LOTE}.txt"


# =============================================================================
# UTILIDADES DE TRANSFORMACIÓN
# =============================================================================

def webots_a_env_xy(x_w: float, y_w: float) -> Tuple[float, float]:
    """
    Traduce coordenadas del marco Webots (centrado en arena) al marco del env
    (origen en esquina inferior izquierda).

    x_env = x_webots + Wx/2,    y_env = y_webots + Wy/2.
    """
    return (x_w + OFFSET_X, y_w + OFFSET_Y)


def env_a_webots_xy(x_env: float, y_env: float) -> Tuple[float, float]:
    """Inversa de `webots_a_env_xy` — para publicar hotspots a Webots."""
    return (x_env - OFFSET_X, y_env - OFFSET_Y)


def compass_a_heading(componentes: List[float]) -> float:
    """
    Convierte los componentes del Compass (rotación 0 0 1 π/2 en el .wbt) al
    heading θ del marco del env, en radianes envueltos a (-π, π].

    Fórmula heredada del controlador MATLAB del lab (`pololu3pi_controller.m`):
        bearing = atan2d(mag(2), mag(1)) − 90
        theta   = deg2rad( atan2d(sin(-bearing), cos(-bearing)) )
    Que se simplifica a `theta = atan2(mag[0], mag[1])`.

    Después se aplica `OFFSET_HEADING_RAD` (calibrable) y se envuelve.
    """
    theta_crudo: float = math.atan2(componentes[0], componentes[1])
    theta:       float = theta_crudo + OFFSET_HEADING_RAD
    # Envolver a (-π, π].
    return math.atan2(math.sin(theta), math.cos(theta))


def convertir_velocidades_a_ruedas(
    v:         float,
    omega:     float,
    radio:     float = RADIO_RUEDA,
    medio_eje: float = MEDIO_EJE,
) -> Tuple[float, float]:
    """
    Convierte el comando del cuerpo (v, ω) a velocidades angulares de rueda
    (rad/s) usando el modelo cinemático INVERSO del diferencial:

        φ̇_R = (v + ℓ·ω) / r
        φ̇_L = (v − ℓ·ω) / r

    El modelo proviene de la derivación por restricciones de rodamiento /
    no-deslizamiento (metodología A⁺·B, clase MT3005 — Robótica 1, UVG), y
    es el INVERSO del modelo directo:
        v = (r/2) · (φ̇_R + φ̇_L)
        ω = (r / (2·ℓ)) · (φ̇_R − φ̇_L)

    Unidades
    --------
    Las salidas están en rad/s. Webots `RotationalMotor.setVelocity()` recibe
    rad/s DIRECTAMENTE; NO convertir a rpm.

    Parámetros
    ----------
    v, omega  : comandos del cuerpo (m/s, rad/s).
    radio     : radio de rueda [m] — geometría del .wbt.
    medio_eje : distancia centro → rueda [m] — geometría del .wbt.

    Retorna
    -------
    (phi_R, phi_L) : Tuple[float, float] — rad/s para motor DERECHO e
                     IZQUIERDO respectivamente (antes de aplicar signos).
    """
    phi_R: float = (v + medio_eje * omega) / radio
    phi_L: float = (v - medio_eje * omega) / radio
    return phi_R, phi_L


# =============================================================================
# CONTROLADOR PRINCIPAL
# =============================================================================

class SupervisorFisica:
    """
    Demo de un Pololu 3pi+ con FÍSICA REAL siguiendo la política
    `modelo_PRIMERO.zip`. El Robot es a la vez supervisor.
    """

    def __init__(self) -> None:
        """
        Inicializa Webots devices, env (modo_poses_externas=True), modelo
        PPO. Hace un primer reset del env y lo alinea con la pose física
        del robot leída por GPS+Compass.
        """
        # ── Handle del Supervisor (que es también Robot del Pololu) ─────────
        self.supervisor: Supervisor = Supervisor()
        self.timestep_ms: int = int(self.supervisor.getBasicTimeStep())

        pasos_float: float = DT_ENV * 1000.0 / float(self.timestep_ms)
        if not math.isclose(pasos_float, round(pasos_float), abs_tol=1e-6):
            raise ValueError(
                f"basicTimeStep={self.timestep_ms} ms no divide exactamente "
                f"dt_env={DT_ENV*1000:.0f} ms. Ajustar el .wbt."
            )
        self.pasos_webots_por_dt: int = int(round(pasos_float))

        # ── Motores: posición libre (velocity-control), velocidad inicial 0 ─
        self._motor_derecho   = self.supervisor.getDevice(NOMBRE_MOTOR_DERECHO)
        self._motor_izquierdo = self.supervisor.getDevice(NOMBRE_MOTOR_IZQUIERDO)
        if self._motor_derecho is None or self._motor_izquierdo is None:
            raise RuntimeError(
                f"No se encontraron los motores {NOMBRE_MOTOR_DERECHO!r}/"
                f"{NOMBRE_MOTOR_IZQUIERDO!r}. Revisar el .wbt."
            )
        for motor in (self._motor_derecho, self._motor_izquierdo):
            motor.setPosition(float("inf"))
            motor.setVelocity(0.0)

        # ── Sensores: GPS + Compass ─────────────────────────────────────────
        self._gps     = self.supervisor.getDevice(NOMBRE_GPS)
        self._compass = self.supervisor.getDevice(NOMBRE_COMPASS)
        if self._gps is None or self._compass is None:
            raise RuntimeError(
                f"No se encontraron GPS/Compass en el Robot. Revisar el .wbt."
            )
        self._gps.enable(self.timestep_ms)
        self._compass.enable(self.timestep_ms)

        # ── Localizar nodos de hotspots ─────────────────────────────────────
        self._campos_trans_obj: List = []
        for nombre_def in DEF_OBJETIVOS:
            nodo = self.supervisor.getFromDef(nombre_def)
            if nodo is None:
                raise RuntimeError(
                    f"No se encontró nodo con DEF {nombre_def!r}. "
                    f"Revisar lab_robotat_fisica.wbt."
                )
            self._campos_trans_obj.append(nodo.getField("translation"))

        # ── Validar MODO ────────────────────────────────────────────────────
        if MODO not in {"actuacion", "pose", "politica", "lote"}:
            raise ValueError(
                f"MODO={MODO!r} inválido. Use 'actuacion', 'pose', "
                f"'politica' o 'lote'."
            )

        # ── Contador de iteración (para logging periódico) ──────────────────
        self._contador_iteracion: int = 0
        self._iteraciones_por_log: int = max(
            1, int(round(PERIODO_LOG_S / DT_ENV))
        )

        # ── Contador de poses fuera de [0, arena_size] (modo politica) ──────
        # Se incrementa en _paso_de_rl cada vez que la pose leída cae fuera de
        # la arena lógica del env (replica la condición del warning interno).
        # Persistente entre episodios; se reporta en cada log de politica.
        self._contador_pose_fuera: int = 0

        # ── Flag de cierre de Webots (para abortar el lote limpiamente) ─────
        self._webots_cerrado: bool = False

        # ── Estado del detector de atasco (modo "lote", solo registro) ──────
        self._paso_episodio:             int             = 0
        self._atasco_pasos_consecutivos: int             = 0
        self._atasco_detectado:          bool            = False
        self._atasco_paso:               int             = -1
        self._atasco_pos:                Tuple[float, float] = (float("nan"), float("nan"))
        self._atasco_v_negativo:         bool            = False
        self._ventana_v_comandada:       Deque[float]    = deque(maxlen=N_PASOS_ATASCO)

        # ── Filtro CBF (safety shield) — solo si CBF_ACTIVO ─────────────────
        # Import perezoso: con el flag en False el módulo no se importa
        # (regresión cero garantizada, criterio de aceptación 1).
        self._filtro_cbf = None
        if CBF_ACTIVO and MODO in ("politica", "lote"):
            from lib.filtro_cbf import FiltroCBFParedes
            self._filtro_cbf = FiltroCBFParedes(
                arena_size = ARENA_SIZE,
                ele_a      = ELE_A,
                alfa       = ALFA_CBF,
                d_segura   = D_SEGURA_PUNTO,
                w_omega    = W_OMEGA,
                v_max      = V_MAX,
                omega_max  = OMEGA_MAX,
            )

        # ── Estadísticas CBF y de proximidad (por episodio y por ventana) ───
        # Se registran SIEMPRE en modo lote (con CBF off: intervenciones=0 y
        # la distancia mínima sirve de referencia para el A/B).
        self._cbf_intervenciones_episodio: int   = 0
        self._cbf_suma_magnitudes:         float = 0.0
        self._dist_min_centro_pared:       float = float("inf")
        self._cbf_intervenciones_ventana:  int   = 0
        self._cbf_ultimo_u_nom:            Optional[np.ndarray] = None
        self._cbf_ultimo_resultado                              = None

        # ── env y modelo: SOLO en modos de lazo cerrado ─────────────────────
        # Los modos de calibración no los necesitan; arrancarlos en frío
        # facilita el debug aún si el modelo no estuviera presente.
        self.env:    Optional[CyanobacteriaMonitoringEnv] = None
        self.modelo: Optional[PPO]                        = None

        if MODO in ("politica", "lote"):
            self.env = CyanobacteriaMonitoringEnv(
                n_agents             = N_AGENTES,
                arena_size           = ARENA_SIZE,
                max_steps            = MAX_STEPS_EP,
                comm_radius          = COMM_RADIUS,
                dt                   = DT_ENV,
                render_mode          = None,
                domain_rand          = DOMAIN_RAND_DEMO,
                n_hotspots           = N_HOTSPOTS,
                seed                 = SEMILLA,
                modo_poses_externas  = MODO_POSES_EXTERNAS,
            )
            if not RUTA_MODELO.is_file():
                raise FileNotFoundError(
                    f"No se encontró el modelo en {RUTA_MODELO!s}."
                )
            self.modelo = PPO.load(str(RUTA_MODELO), device="cpu")

        # ── Warm-up: avanzar Webots para que GPS+Compass tengan lectura ─────
        # Sin este step los sensores devuelven NaN en el primer tick.
        if self.supervisor.step(self.timestep_ms) == -1:
            raise RuntimeError("Webots cerró durante el warm-up.")

        # ── Primer reset del env + alineación (solo en modo "politica") ────
        # En modo "lote" el reset por episodio lo maneja _loop_lote.
        self._observaciones_actuales: Dict[str, np.ndarray] = {}
        if MODO == "politica":
            self._observaciones_actuales = self._reiniciar_episodio(SEMILLA)
            # Publicar hotspots iniciales (en modos de calibración los hotspots
            # se quedan donde el .wbt los puso; no se animan).
            self._publicar_hotspots_a_webots()

        # ── Log de arranque adaptado al modo ────────────────────────────────
        if MODO == "actuacion":
            print(
                f"[SupervisorFisica][MODO=actuacion] LAZO ABIERTO  "
                f"v_test={V_TEST:+.3f} m/s  ω_test={OMEGA_TEST:+.3f} rad/s  "
                f"timestep={self.timestep_ms} ms  "
                f"signos=({SIGNO_MOTOR_1:+d}, {SIGNO_MOTOR_2:+d})  "
                f"r={RADIO_RUEDA} m  ℓ={MEDIO_EJE} m"
            )
        elif MODO == "pose":
            print(
                f"[SupervisorFisica][MODO=pose] SOLO LECTURA  "
                f"motores apagados  timestep={self.timestep_ms} ms  "
                f"offset_heading={OFFSET_HEADING_RAD:.3f} rad  "
                f"offset_marco=(+{OFFSET_X:.2f}, +{OFFSET_Y:.2f})"
            )
        elif MODO == "lote":
            print(
                f"[SupervisorFisica][MODO=lote] EXPERIMENTO A  "
                f"modelo={NOMBRE_MODELO}  "
                f"episodios={N_EPISODIOS_LOTE}  "
                f"semillas={SEMILLAS_LOTE[0]}..{SEMILLAS_LOTE[-1]}  "
                f"detector=(dpos<{UMBRAL_ATASCO_POS_M*1000:.0f}mm, "
                f"dθ<{math.degrees(UMBRAL_ATASCO_THETA_RAD):.1f}°, "
                f"{N_PASOS_ATASCO} pasos)  "
                f"signos=({SIGNO_MOTOR_1:+d}, {SIGNO_MOTOR_2:+d})  "
                f"cbf={'ON' if CBF_ACTIVO else 'OFF'}"
            )
        else:  # politica
            print(
                f"[SupervisorFisica][MODO=politica] LAZO CERRADO  "
                f"timestep={self.timestep_ms} ms  "
                f"pasos_webots_por_dt={self.pasos_webots_por_dt}  "
                f"agentes={N_AGENTES}  hotspots={N_HOTSPOTS}  "
                f"r={RADIO_RUEDA} m  ℓ={MEDIO_EJE} m  "
                f"signos=({SIGNO_MOTOR_1:+d}, {SIGNO_MOTOR_2:+d})  "
                f"offset_heading={OFFSET_HEADING_RAD:.3f} rad"
            )

    # ──────────────────────────────────────────────────────────────────────

    def _leer_pose_fisica(self) -> np.ndarray:
        """
        Lee la pose actual del robot vía GPS (posición) y Compass (heading)
        y la convierte al marco del env.

        Retorna
        -------
        pose_env : np.ndarray shape (3,) — [x_env, y_env, θ_env].
        """
        pos_w: List[float] = list(self._gps.getValues())
        mag:   List[float] = list(self._compass.getValues())

        x_env, y_env = webots_a_env_xy(float(pos_w[0]), float(pos_w[1]))
        theta_env:    float = compass_a_heading(mag)

        return np.array([x_env, y_env, theta_env], dtype=np.float64)

    # ──────────────────────────────────────────────────────────────────────

    def _publicar_hotspots_a_webots(self) -> None:
        """
        Copia las posiciones actuales de los hotspots del env a los nodos
        de Webots. Z fija; los hotspots solo se mueven en (x, y).
        """
        posiciones_obj: np.ndarray = self.env._field.posiciones_objetivos
        for j in range(N_HOTSPOTS):
            x_env: float = float(posiciones_obj[j, 0])
            y_env: float = float(posiciones_obj[j, 1])
            x_w, y_w = env_a_webots_xy(x_env, y_env)
            self._campos_trans_obj[j].setSFVec3f([x_w, y_w, Z_OBJETIVO])

    # ──────────────────────────────────────────────────────────────────────

    def _comandar_motores(self, accion: np.ndarray) -> None:
        """
        Recibe la acción (v, ω) de la política, la convierte a velocidades
        de rueda usando el modelo diferencial inverso y la aplica a los
        `RotationalMotor` (rad/s).

        Aplica clipping defensivo a `maxVelocity` declarado en el .wbt (84
        rad/s) — debería ser un no-op para acciones legales (≤21.4 rad/s).
        """
        v:     float = float(accion[0])
        omega: float = float(accion[1])
        phi_R, phi_L = convertir_velocidades_a_ruedas(v, omega)

        # Signos configurables (calibración empírica de sentido de giro).
        phi_R_cmd: float = SIGNO_MOTOR_1 * phi_R
        phi_L_cmd: float = SIGNO_MOTOR_2 * phi_L

        # Saturación defensiva al límite del motor declarado en el .wbt.
        vmax_motor: float = 84.0
        phi_R_cmd = float(np.clip(phi_R_cmd, -vmax_motor, vmax_motor))
        phi_L_cmd = float(np.clip(phi_L_cmd, -vmax_motor, vmax_motor))

        self._motor_derecho.setVelocity(phi_R_cmd)
        self._motor_izquierdo.setVelocity(phi_L_cmd)

    # ──────────────────────────────────────────────────────────────────────

    def _reiniciar_episodio(
        self,
        semilla: int,
        teletransportar: bool = False,
    ) -> Dict[str, np.ndarray]:
        """
        Reinicia el env y lo alinea con la pose física actual del robot.

        Procedimiento
        -------------
        1. `env.reset(seed)`: limpia _estados (poses sorteadas), AoI, field.
        2. (opcional, modo lote) TELETRANSPORTAR el robot físico a la pose
           inicial sorteada por el env, para que los episodios del lote sean
           independientes (sin esto, el episodio arrancaría donde el robot
           quedó — p. ej. pegado a la pared del episodio anterior). Después
           del teleport se avanzan 2 ticks para que la física asiente y los
           sensores refresquen.
        3. Leer pose física (GPS+Compass).
        4. `inyectar_poses_externas` con la pose física.
        5. Hacer un step con acción cero — esto sobrescribe _estados con
           la pose inyectada, recalcula AoI/obs con la pose correcta y
           descarta cualquier obs "sucia" devuelta por el reset.
        6. Mover motores a velocidad 0 (defensiva) y reiniciar el estado del
           detector de atasco.

        Retorna las observaciones limpias post-alineación (dict vacío si
        Webots cerró durante el asentamiento).
        """
        # 1. Reset del env.
        self.env.reset(seed=semilla)

        # 2. Teletransporte a la pose inicial sorteada (modo lote).
        if teletransportar:
            pose_inicial: np.ndarray = self.env._estados[AGENT_ID][:3].copy()
            self._teletransportar_robot(pose_inicial)
            for _ in range(2):
                if self.supervisor.step(self.timestep_ms) == -1:
                    self._webots_cerrado = True
                    return {}

        # 3. Pose física.
        pose: np.ndarray = self._leer_pose_fisica()

        # 4. Inyectar y 5. step inicial con acción cero.
        self.env.inyectar_poses_externas({AGENT_ID: pose})
        accion_cero: np.ndarray = np.zeros(2, dtype=np.float32)
        obs, _rew, _term, _trunc, _info = self.env.step({AGENT_ID: accion_cero})

        # 6. Motores en cero y detector limpio.
        self._motor_derecho.setVelocity(0.0)
        self._motor_izquierdo.setVelocity(0.0)
        self._reiniciar_detector_atasco()

        return obs

    # ──────────────────────────────────────────────────────────────────────

    def _teletransportar_robot(self, pose_env: np.ndarray) -> None:
        """
        Coloca el robot físico (el propio nodo del supervisor) en la pose
        indicada, UNA vez, al inicio de un episodio del lote. Equivale a
        posicionar el robot a mano; después la física retoma el control.

        La rotación del nodo compensa el marco local del robot (forward =
        +Y local por la geometría de ruedas en ±X): angulo_nodo = θ − π/2.
        Cualquier error residual de esta constante es inocuo: la pose que
        el env recibe se lee SIEMPRE de los sensores (GPS+Compass), no de
        este teleport.

        Parámetros
        ----------
        pose_env : np.ndarray shape (3,) — [x, y, θ] en marco env.
        """
        nodo = self.supervisor.getSelf()
        x_w, y_w = env_a_webots_xy(float(pose_env[0]), float(pose_env[1]))
        nodo.getField("translation").setSFVec3f([x_w, y_w, 0.0])
        nodo.getField("rotation").setSFRotation(
            [0.0, 0.0, 1.0, float(pose_env[2]) - math.pi / 2.0]
        )
        # Anular velocidades/momentos residuales del episodio anterior.
        nodo.resetPhysics()

    # ──────────────────────────────────────────────────────────────────────

    def _reiniciar_detector_atasco(self) -> None:
        """
        Limpia el estado por-episodio: detector de atasco + estadísticas
        CBF y de proximidad a pared.
        """
        self._paso_episodio             = 0
        self._atasco_pasos_consecutivos = 0
        self._atasco_detectado          = False
        self._atasco_paso               = -1
        self._atasco_pos                = (float("nan"), float("nan"))
        self._atasco_v_negativo         = False
        self._ventana_v_comandada.clear()
        self._cbf_intervenciones_episodio = 0
        self._cbf_suma_magnitudes         = 0.0
        self._dist_min_centro_pared       = float("inf")

    # ──────────────────────────────────────────────────────────────────────

    def _actualizar_detector_atasco(
        self,
        accion:       np.ndarray,
        pose_antes:   np.ndarray,
        pose_despues: np.ndarray,
    ) -> None:
        """
        Detector de atasco — SOLO REGISTRO (no interviene en el control).

        Criterio: atascado si ‖Δpos‖ < UMBRAL_ATASCO_POS_M y
        |Δθ| < UMBRAL_ATASCO_THETA_RAD durante N_PASOS_ATASCO pasos
        consecutivos. Al dispararse por primera vez registra el paso, la
        posición y si la política comandó v<0 dentro de la ventana de
        quietud; después sigue monitoreando v<0 hasta el fin del episodio.

        Parámetros
        ----------
        accion       : np.ndarray (2,) — [v, ω] comandada este paso.
        pose_antes   : np.ndarray (3,) — pose física PRE-step.
        pose_despues : np.ndarray (3,) — pose física POST-step.
        """
        v_cmd: float = float(accion[0])
        self._ventana_v_comandada.append(v_cmd)

        d_pos: float = float(np.linalg.norm(pose_despues[:2] - pose_antes[:2]))
        d_theta: float = abs(math.atan2(
            math.sin(float(pose_despues[2]) - float(pose_antes[2])),
            math.cos(float(pose_despues[2]) - float(pose_antes[2])),
        ))

        quieto: bool = (
            d_pos < UMBRAL_ATASCO_POS_M and d_theta < UMBRAL_ATASCO_THETA_RAD
        )
        self._atasco_pasos_consecutivos = (
            self._atasco_pasos_consecutivos + 1 if quieto else 0
        )

        if not self._atasco_detectado:
            if self._atasco_pasos_consecutivos >= N_PASOS_ATASCO:
                self._atasco_detectado = True
                self._atasco_paso      = self._paso_episodio
                self._atasco_pos       = (
                    float(pose_despues[0]), float(pose_despues[1])
                )
                # ¿La política intentó retroceder dentro de la ventana?
                self._atasco_v_negativo = any(
                    v < 0.0 for v in self._ventana_v_comandada
                )
        else:
            # Ya atascado: seguir monitoreando si alguna vez comanda v<0.
            if v_cmd < 0.0:
                self._atasco_v_negativo = True

    # ──────────────────────────────────────────────────────────────────────

    def _paso_de_rl(self) -> bool:
        """
        Una iteración del loop principal. Ver docstring del módulo.

        Retorna
        -------
        episodio_terminado : bool — True si el agente truncó.
        """
        # 1. Predict (acción NOMINAL de la política).
        obs_agente: np.ndarray = self._observaciones_actuales[AGENT_ID]
        accion_nominal, _ = self.modelo.predict(obs_agente, deterministic=True)
        accion_nominal = np.asarray(accion_nominal, dtype=np.float32).flatten()

        # Pose ANTES de aplicar la acción (lectura del estado físico actual).
        pose_antes: np.ndarray = self._leer_pose_fisica()

        # 1b. Filtro CBF (safety shield): u_nom → u_seg. La acción EJECUTADA
        # es la filtrada; el env, el detector y el log operan sobre ella.
        if self._filtro_cbf is not None:
            resultado_cbf = self._filtro_cbf.filtrar(pose_antes, accion_nominal)
            accion = np.asarray(resultado_cbf.u_seguro, dtype=np.float32)
            if resultado_cbf.intervino:
                self._cbf_intervenciones_episodio += 1
                self._cbf_suma_magnitudes += resultado_cbf.magnitud_modificacion
                self._cbf_intervenciones_ventana += 1
                self._cbf_ultimo_u_nom     = accion_nominal.copy()
                self._cbf_ultimo_resultado = resultado_cbf
        else:
            accion = accion_nominal

        # 2-3. Comandar motores con (v, ω) → (φ̇_R, φ̇_L).
        self._comandar_motores(accion)

        # 4. Avanzar Webots N_TICKS ticks.
        n_ticks: int = self.timestep_ms * self.pasos_webots_por_dt
        if self.supervisor.step(n_ticks) == -1:
            self._webots_cerrado = True
            return True  # cierre solicitado por Webots

        # 5-6. Leer pose física DESPUÉS del step y mapear a marco env.
        pose_despues: np.ndarray = self._leer_pose_fisica()

        # 6b. Contar poses fuera de arena (replica la condición que dispara el
        # warning interno de `inyectar_poses_externas`). No suprime el warning;
        # solo lo tabula para reportarlo en el log periódico.
        Wx, Wy = float(ARENA_SIZE[0]), float(ARENA_SIZE[1])
        x_p, y_p = float(pose_despues[0]), float(pose_despues[1])
        if not (0.0 <= x_p <= Wx) or not (0.0 <= y_p <= Wy):
            self._contador_pose_fuera += 1

        # 6c. Distancia mínima del CENTRO a la pared más cercana (para el
        # criterio de no-contacto del lote: debe quedar > r_chasis 0.075 m).
        dist_pared: float = min(x_p, Wx - x_p, y_p, Wy - y_p)
        if dist_pared < self._dist_min_centro_pared:
            self._dist_min_centro_pared = dist_pared

        # 7. Inyectar al env.
        self.env.inyectar_poses_externas({AGENT_ID: pose_despues})

        # 8. Avanzar env (procesa la pose, mueve hotspots, devuelve obs).
        (
            self._observaciones_actuales,
            _rewards,
            _terminations,
            truncations,
            _infos,
        ) = self.env.step({AGENT_ID: accion})

        # 9. Publicar hotspots a Webots.
        self._publicar_hotspots_a_webots()

        # 9b. Detector de atasco (solo registro; solo en modo lote).
        self._paso_episodio += 1
        if MODO == "lote":
            self._actualizar_detector_atasco(accion, pose_antes, pose_despues)

        # 10. Logging periódico (mismo PERIODO_LOG_S que actuacion/pose).
        self._contador_iteracion += 1
        if self._contador_iteracion % self._iteraciones_por_log == 0:
            self._log_politica(accion, pose_antes, pose_despues)
            # Línea [cbf] si el filtro intervino durante la ventana de log.
            if self._cbf_intervenciones_ventana > 0 and \
                    self._cbf_ultimo_resultado is not None:
                u_n = self._cbf_ultimo_u_nom
                res = self._cbf_ultimo_resultado
                print(
                    f"[cbf] u_nom=({float(u_n[0]):+.2f},{float(u_n[1]):+.2f}) "
                    f"→ u_seg=({float(res.u_seguro[0]):+.2f},"
                    f"{float(res.u_seguro[1]):+.2f}) | "
                    f"h_min={res.h_minima:+.3f} | {res.barrera_activa} | "
                    f"intervenciones_ventana={self._cbf_intervenciones_ventana}"
                )
                self._cbf_intervenciones_ventana = 0

        return bool(truncations.get(AGENT_ID, False))

    # ──────────────────────────────────────────────────────────────────────

    def _log_politica(
        self,
        accion:       np.ndarray,
        pose_antes:   np.ndarray,
        pose_despues: np.ndarray,
    ) -> None:
        """
        Imprime una línea de log con la acción comandada, el cambio de heading
        entre pre/post step, la posición y la distancia al hotspot más cercano.
        Si el contador de poses fuera de arena es > 0, lo anexa al final.

        Parámetros
        ----------
        accion       : np.ndarray shape (2,) — [v, ω] de la política.
        pose_antes   : np.ndarray shape (3,) — [x, y, θ] PRE-step físico.
        pose_despues : np.ndarray shape (3,) — [x, y, θ] POST-step físico.
        """
        v:     float = float(accion[0])
        omega: float = float(accion[1])

        # Δθ envuelto a (-π, π] vía atan2(sin, cos).
        th_antes:    float = float(pose_antes[2])
        th_despues:  float = float(pose_despues[2])
        d_theta:     float = math.atan2(
            math.sin(th_despues - th_antes),
            math.cos(th_despues - th_antes),
        )

        # Distancia al hotspot más cercano (marco env).
        pos_robot:    np.ndarray = pose_despues[:2]
        pos_hotspots: np.ndarray = self.env._field.posiciones_objetivos  # (H, 2)
        distancias:   np.ndarray = np.linalg.norm(
            pos_hotspots - pos_robot[np.newaxis, :], axis=1,
        )
        d_min: float = float(distancias.min())

        # Sufijo opcional con conteo de fugas físicas.
        sufijo: str = (
            f" | poses_fuera={self._contador_pose_fuera}"
            if self._contador_pose_fuera > 0 else ""
        )

        print(
            f"[politica] "
            f"v={v:+.2f} ω={omega:+.2f} rad/s | "
            f"θ: {math.degrees(th_antes):+.1f}°→{math.degrees(th_despues):+.1f}° "
            f"(Δθ={math.degrees(d_theta):+.1f}°) | "
            f"pos=({pose_despues[0]:+.2f},{pose_despues[1]:+.2f}) | "
            f"d_hotspot={d_min:.2f}"
            f"{sufijo}"
        )

    # ──────────────────────────────────────────────────────────────────────

    def correr_loop_infinito(self) -> None:
        """
        Dispatcher de bucle según MODO.
          - "actuacion" → `_loop_actuacion()`  (lazo abierto, sin política)
          - "pose"      → `_loop_pose()`       (solo lectura)
          - "politica"  → `_loop_politica()`   (lazo cerrado con política)
          - "lote"      → `_loop_lote()`       (Experimento A, N episodios)
        """
        if MODO == "actuacion":
            self._loop_actuacion()
        elif MODO == "pose":
            self._loop_pose()
        elif MODO == "lote":
            self._loop_lote()
        else:
            self._loop_politica()

    # ──────────────────────────────────────────────────────────────────────

    def _loop_lote(self) -> None:
        """
        EXPERIMENTO A — corrida por lotes de N_EPISODIOS_LOTE episodios en
        lazo cerrado con la política, con detector de atasco SOLO REGISTRO.

        Por episodio: teletransporte a pose inicial seeded → rollout hasta
        truncar (max_steps) → registrar fila. Al final: CSV + resumen +
        cierre/pausa de la simulación según SALIR_AL_TERMINAR_LOTE.
        """
        resultados: List[Dict[str, object]] = []

        for indice, semilla in enumerate(SEMILLAS_LOTE):
            self._observaciones_actuales = self._reiniciar_episodio(
                semilla, teletransportar=True
            )
            if self._webots_cerrado:
                break
            self._publicar_hotspots_a_webots()

            episodio_terminado = False
            while not episodio_terminado and not self._webots_cerrado:
                episodio_terminado = self._paso_de_rl()

            if self._webots_cerrado:
                print(f"[lote] Webots cerró en el episodio {indice+1}; "
                      f"guardando resultados parciales.")
                break

            fila: Dict[str, object] = {
                "episodio":                  indice + 1,
                "semilla":                   semilla,
                "atascado":                  self._atasco_detectado,
                "paso_atasco":               self._atasco_paso,
                "t_atasco_s":                (
                    round(self._atasco_paso * DT_ENV, 1)
                    if self._atasco_detectado else -1.0
                ),
                "x_atasco_env":              (
                    round(self._atasco_pos[0], 4)
                    if self._atasco_detectado else -1.0
                ),
                "y_atasco_env":              (
                    round(self._atasco_pos[1], 4)
                    if self._atasco_detectado else -1.0
                ),
                "v_negativo_durante_atasco": self._atasco_v_negativo,
                "pasos_totales":             self._paso_episodio,
                "intervenciones_cbf":        self._cbf_intervenciones_episodio,
                "magnitud_media_modificacion": (
                    round(
                        self._cbf_suma_magnitudes
                        / self._cbf_intervenciones_episodio, 4,
                    )
                    if self._cbf_intervenciones_episodio > 0 else 0.0
                ),
                "distancia_minima_centro_a_pared": (
                    round(self._dist_min_centro_pared, 4)
                    if math.isfinite(self._dist_min_centro_pared) else -1.0
                ),
            }
            resultados.append(fila)
            print(
                f"[lote] ep {indice+1:2d}/{N_EPISODIOS_LOTE}  "
                f"semilla={semilla}  "
                f"atascado={'SI' if fila['atascado'] else 'no'}  "
                f"cbf_int={fila['intervenciones_cbf']}  "
                f"d_min={fila['distancia_minima_centro_a_pared']}"
                + (
                    f"  paso={fila['paso_atasco']}  "
                    f"pos=({fila['x_atasco_env']:.2f},{fila['y_atasco_env']:.2f})  "
                    f"v_neg={'SI' if fila['v_negativo_durante_atasco'] else 'no'}"
                    if fila["atascado"] else ""
                )
            )

        if resultados:
            self._escribir_resultados_lote(resultados)

        # Frenar motores y terminar según configuración.
        self._motor_derecho.setVelocity(0.0)
        self._motor_izquierdo.setVelocity(0.0)
        if SALIR_AL_TERMINAR_LOTE and not self._webots_cerrado:
            self.supervisor.simulationQuit(0)
        elif not self._webots_cerrado:
            self.supervisor.simulationSetMode(
                self.supervisor.SIMULATION_MODE_PAUSE
            )

    # ──────────────────────────────────────────────────────────────────────

    def _escribir_resultados_lote(
        self,
        resultados: List[Dict[str, object]],
    ) -> None:
        """
        Escribe el CSV por episodio y el resumen agregado del Experimento A.
        """
        DIR_RESULTADOS.mkdir(parents=True, exist_ok=True)

        campos = list(resultados[0].keys())
        with open(RUTA_CSV_LOTE, "w", newline="", encoding="utf-8") as f:
            escritor = csv.DictWriter(f, fieldnames=campos)
            escritor.writeheader()
            escritor.writerows(resultados)
        print(f"[lote] CSV escrito → {RUTA_CSV_LOTE}")

        # ── Resumen agregado ────────────────────────────────────────────
        n_eps       = len(resultados)
        atascados   = [r for r in resultados if r["atascado"]]
        n_atascados = len(atascados)
        tasa_pct    = 100.0 * n_atascados / n_eps if n_eps else 0.0
        t_medio     = (
            float(np.mean([float(r["t_atasco_s"]) for r in atascados]))
            if atascados else float("nan")
        )
        n_v_neg = sum(1 for r in atascados if r["v_negativo_durante_atasco"])

        # Estadísticas CBF y de proximidad (registradas siempre).
        intervenciones = [int(r["intervenciones_cbf"]) for r in resultados]
        dists_min      = [
            float(r["distancia_minima_centro_a_pared"]) for r in resultados
            if float(r["distancia_minima_centro_a_pared"]) >= 0.0
        ]
        magnitudes = [
            float(r["magnitud_media_modificacion"]) for r in resultados
            if int(r["intervenciones_cbf"]) > 0
        ]

        lineas: List[str] = []
        lineas.append("EXPERIMENTO A — Atascos de pared con física real (Webots)")
        lineas.append(f"1 robot, lazo cerrado con {NOMBRE_MODELO}, "
                      f"deterministic=True")
        lineas.append(f"Filtro CBF de ejecución     : "
                      f"{'ACTIVO' if CBF_ACTIVO else 'INACTIVO'}"
                      + (f"  (ℓa={ELE_A}, α={ALFA_CBF}, d_s={D_SEGURA_PUNTO}, "
                         f"w={W_OMEGA})" if CBF_ACTIVO else ""))
        lineas.append(f"Detector: dpos<{UMBRAL_ATASCO_POS_M*1000:.0f} mm y "
                      f"dθ<{math.degrees(UMBRAL_ATASCO_THETA_RAD):.1f}° por "
                      f"{N_PASOS_ATASCO} pasos consecutivos (solo registro)")
        lineas.append("=" * 66)
        lineas.append(f"Episodios ejecutados        : {n_eps}")
        lineas.append(f"Episodios con atasco        : {n_atascados}  "
                      f"(tasa = {tasa_pct:.1f}%)")
        lineas.append(f"Tiempo medio al atasco      : "
                      f"{t_medio:.1f} s" if atascados else
                      "Tiempo medio al atasco      : n/a (sin atascos)")
        lineas.append(f"Atascos donde política pidió v<0 : {n_v_neg}/{n_atascados}"
                      if atascados else
                      "Atascos donde política pidió v<0 : n/a")
        lineas.append(f"Intervenciones CBF por episodio  : "
                      f"media={float(np.mean(intervenciones)):.1f}  "
                      f"max={max(intervenciones)}")
        if magnitudes:
            lineas.append(f"Magnitud media de modificación   : "
                          f"{float(np.mean(magnitudes)):.4f} (adimensional)")
        if dists_min:
            lineas.append(f"Dist. mínima centro→pared [m]    : "
                          f"min={min(dists_min):.4f}  "
                          f"media={float(np.mean(dists_min)):.4f}  "
                          f"(sin contacto si > 0.075)")
        lineas.append("")
        if NOMBRE_MODELO == "modelo_PRIMERO":
            lineas.append("Interpretación: la política fue entrenada con reflexión")
            lineas.append("elástica de pared (rebote idealizado). Con paredes sólidas")
            lineas.append("la física bloquea al robot y la política no dispone de un")
            lineas.append("comportamiento de recuperación (ver Experimento B para la")
            lineas.append("frecuencia con la que el entrenamiento dependió del rebote).")
        else:
            lineas.append("Interpretación: esta política fue entrenada CON bordes")
            lineas.append("bloqueantes (modo_borde='bloqueante'), por lo que no")
            lineas.append("depende del rebote idealizado. Comparar contra la corrida")
            lineas.append("baseline con modelo_PRIMERO (mismas 18 semillas) para")
            lineas.append("cuantificar la transferencia de la evitación aprendida.")

        resumen = "\n".join(lineas)
        RUTA_RESUMEN_LOTE.write_text(resumen, encoding="utf-8")
        print(f"[lote] Resumen escrito → {RUTA_RESUMEN_LOTE}")
        print()
        print(resumen)

    # ──────────────────────────────────────────────────────────────────────

    def _loop_actuacion(self) -> None:
        """
        Modo CALIBRACIÓN — lazo abierto. Comanda (V_TEST, OMEGA_TEST) directo
        a las ruedas, sin política ni env. Cada PERIODO_LOG_S imprime el
        comando enviado y la pose actual.

        Útil para validar SIGNO_MOTOR_1/2 y el modelo diferencial inverso:
          - V_TEST=0.1, OMEGA_TEST=0.0 → debería avanzar en línea recta.
          - V_TEST=0.0, OMEGA_TEST=1.0 → debería girar in-situ (ω>0).
          - Si no avanza recto: signos descalibrados. Si gira en el sentido
            contrario al esperado: alguno de los signos invertido.
        """
        n_ticks: int = self.timestep_ms * self.pasos_webots_por_dt

        while True:
            # Convertir comando fijo y aplicar signos.
            phi_R_raw, phi_L_raw = convertir_velocidades_a_ruedas(
                V_TEST, OMEGA_TEST
            )
            phi_R_cmd: float = float(np.clip(
                SIGNO_MOTOR_1 * phi_R_raw, -84.0, 84.0,
            ))
            phi_L_cmd: float = float(np.clip(
                SIGNO_MOTOR_2 * phi_L_raw, -84.0, 84.0,
            ))
            self._motor_derecho.setVelocity(phi_R_cmd)
            self._motor_izquierdo.setVelocity(phi_L_cmd)

            # Avanzar Webots.
            if self.supervisor.step(n_ticks) == -1:
                break

            # Logging periódico.
            self._contador_iteracion += 1
            if self._contador_iteracion % self._iteraciones_por_log == 0:
                pose: np.ndarray = self._leer_pose_fisica()
                print(
                    f"[actuacion] "
                    f"cmd=(v={V_TEST:+.3f} m/s, ω={OMEGA_TEST:+.3f} rad/s)  "
                    f"ruedas=(φ̇_R={phi_R_cmd:+.3f}, φ̇_L={phi_L_cmd:+.3f}) rad/s  "
                    f"pose=(x={pose[0]:+.3f}, y={pose[1]:+.3f}, "
                    f"θ={math.degrees(pose[2]):+.1f}°)"
                )

    # ──────────────────────────────────────────────────────────────────────

    def _loop_pose(self) -> None:
        """
        Modo CALIBRACIÓN — solo lectura. Motores en 0; el robot queda quieto
        salvo que el usuario lo mueva manualmente desde el editor de Webots.
        Cada PERIODO_LOG_S imprime:
          - GPS crudo: (x_w, y_w, z_w) [m] en marco mundo.
          - Compass crudo: (mag_x, mag_y, mag_z) componentes del vector "norte".
          - Pose env derivada: (x_env, y_env, θ_env), θ en grados.

        Útil para validar:
          - El offset de marco (env = webots + 1.5): mover el robot al centro
            de Webots (0,0) debería leer (x_env, y_env) ≈ (1.5, 1.5).
          - OFFSET_HEADING_RAD: rotar el robot manualmente y verificar que θ_env
            se corresponde con la convención esperada (θ=0 ⇒ +x global).
        """
        # Motores apagados (defensivo: re-emitido en cada iteración por si
        # algún tick previo dejó residuo).
        self._motor_derecho.setVelocity(0.0)
        self._motor_izquierdo.setVelocity(0.0)

        n_ticks: int = self.timestep_ms * self.pasos_webots_por_dt

        while True:
            self._motor_derecho.setVelocity(0.0)
            self._motor_izquierdo.setVelocity(0.0)

            if self.supervisor.step(n_ticks) == -1:
                break

            # Logging periódico.
            self._contador_iteracion += 1
            if self._contador_iteracion % self._iteraciones_por_log == 0:
                pos_w: List[float] = list(self._gps.getValues())
                mag:   List[float] = list(self._compass.getValues())
                pose:  np.ndarray  = self._leer_pose_fisica()
                print(
                    f"[pose] "
                    f"GPS=(x_w={pos_w[0]:+.3f}, y_w={pos_w[1]:+.3f}, "
                    f"z_w={pos_w[2]:+.3f}) m  "
                    f"COMPASS=({mag[0]:+.3f}, {mag[1]:+.3f}, {mag[2]:+.3f})  "
                    f"ENV=(x={pose[0]:+.3f}, y={pose[1]:+.3f}, "
                    f"θ={math.degrees(pose[2]):+.1f}°)"
                )

    # ──────────────────────────────────────────────────────────────────────

    def _loop_politica(self) -> None:
        """
        Modo PRODUCCIÓN — lazo cerrado: política → ruedas → física → pose →
        política. Es el bucle "real" del demo. Idéntico al diseño original
        (sin instrumentación de calibración).
        """
        while True:
            episodio_terminado: bool = self._paso_de_rl()

            if episodio_terminado:
                # Frenar motores y reiniciar episodio. La semilla varía para
                # diversificar trayectorias de hotspots; la política sigue
                # siendo determinista.
                self._motor_derecho.setVelocity(0.0)
                self._motor_izquierdo.setVelocity(0.0)
                semilla_nueva: int = int(self.env.rng.integers(0, 2**31 - 1))
                self._observaciones_actuales = self._reiniciar_episodio(semilla_nueva)
                self._publicar_hotspots_a_webots()


# =============================================================================
# ENTRY-POINT
# =============================================================================

def main() -> None:
    """Punto de entrada que Webots invoca al cargar el controlador."""
    # Hacer visibles los warnings del env (poses fuera de arena, etc.) en la
    # consola de Webots. Default de Python suprime RuntimeWarning duplicadas.
    warnings.simplefilter("always", RuntimeWarning)

    supervisor = SupervisorFisica()
    supervisor.correr_loop_infinito()


if __name__ == "__main__":
    main()
