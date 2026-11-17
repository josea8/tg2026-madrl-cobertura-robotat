"""
protocolo.py
============
Protocolo de comunicación Emitter/Receiver del enjambre multi-robot, más las
utilidades de marco y el modelo cinemático de ruedas que ambos extremos
necesitan.

Este archivo se copia IDÉNTICO en `controlador_agente/` y en
`coordinador_enjambre/`. Webots no comparte módulos entre controladores sin
instalarlos en el PYTHONPATH global, así que la duplicación es deliberada:
el formato vive conceptualmente en un solo lugar y se replica byte a byte.
Si se modifica uno, DEBE copiarse al otro (ver README).

Por qué `struct` y no JSON
--------------------------
Los mensajes son de tamaño fijo, sin parseo ambiguo ni asignación dinámica, y
mapean directo a un datagrama UDP hacia los Pololu 3pi+ reales en la fase del
Robotat. JSON obligaría a serializar/deserializar texto en cada tick (10 ms)
y no aporta nada: el esquema es cerrado y conocido por ambos extremos.

Canales
-------
  Canal 1 (SUBIDA)  : agente → coordinador. Cada agente emite su pose en CADA
                      tick, sin esperar pedido. Emisión ciega ⇒ sin lógica de
                      bloqueo y robusta a pérdidas (el siguiente llega en 10 ms).
  Canal 2 (BAJADA)  : coordinador → todos. Difunde un único mensaje con las N
                      acciones cada 10 ticks (dt_env = 0.1 s), o un mensaje de
                      RESET entre episodios.

Formatos (little-endian, sin padding)
-------------------------------------
  POSE      "<Bidddi"          33 bytes
              B  tipo = 1
              i  id_agente
              d  x_env, y_env, theta_env
              i  tick_emision

  ACCIONES  "<Bi" + "dd"*N     5 + 16·N bytes
              B  tipo = 2
              i  tick_decision
              d  v_0, w_0, v_1, w_1, ...   (pares consecutivos por índice)
            El agente `i` lee su par en el offset 5 + 16·i.

  RESET     "<Bi"              5 bytes
              B  tipo = 3
              i  tick
            Ordena a los agentes frenar motores y descartar la acción vigente.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import math
import struct
from typing import List, Tuple

# =============================================================================
# CANALES Y TIPOS DE MENSAJE
# =============================================================================

CANAL_SUBIDA: int = 1   # agente → coordinador (poses)
CANAL_BAJADA: int = 2   # coordinador → agentes (acciones / reset)

TIPO_POSE:     int = 1
TIPO_ACCIONES: int = 2
TIPO_RESET:    int = 3

_FMT_POSE:     str = "<Bidddi"
_FMT_CABECERA: str = "<Bi"
_FMT_PAR:      str = "<dd"

TAM_POSE:     int = struct.calcsize(_FMT_POSE)      # 33
TAM_CABECERA: int = struct.calcsize(_FMT_CABECERA)  #  5
TAM_PAR:      int = struct.calcsize(_FMT_PAR)       # 16


# =============================================================================
# EMPAQUETADO / DESEMPAQUETADO
# =============================================================================

def empaquetar_pose(
    id_agente: int,
    x_env:     float,
    y_env:     float,
    theta_env: float,
    tick:      int,
) -> bytes:
    """
    Serializa un mensaje de POSE (canal de subida).

    Parámetros
    ----------
    id_agente : índice del agente (0..N-1).
    x_env, y_env, theta_env : pose en el marco del env (origen en esquina).
    tick : tick de Webots en el que se tomó la lectura.
    """
    return struct.pack(
        _FMT_POSE, TIPO_POSE, int(id_agente),
        float(x_env), float(y_env), float(theta_env), int(tick),
    )


def desempaquetar_pose(datos: bytes) -> Tuple[int, float, float, float, int]:
    """
    Deserializa un mensaje de POSE.

    Retorna
    -------
    (id_agente, x_env, y_env, theta_env, tick_emision)

    Raises
    ------
    ValueError : si el tamaño o el tipo no corresponden a un POSE.
    """
    if len(datos) != TAM_POSE:
        raise ValueError(
            f"Mensaje de pose con tamaño {len(datos)} B, esperado {TAM_POSE} B."
        )
    tipo, id_ag, x, y, th, tick = struct.unpack(_FMT_POSE, datos)
    if tipo != TIPO_POSE:
        raise ValueError(f"Tipo de mensaje {tipo} no es POSE ({TIPO_POSE}).")
    return int(id_ag), float(x), float(y), float(th), int(tick)


def empaquetar_acciones(
    tick:     int,
    acciones: List[Tuple[float, float]],
) -> bytes:
    """
    Serializa el mensaje de ACCIONES para los N agentes (canal de bajada).

    Parámetros
    ----------
    tick     : tick de la decisión.
    acciones : lista de N pares (v, ω) EN ORDEN DE ÍNDICE de agente.
    """
    partes = [struct.pack(_FMT_CABECERA, TIPO_ACCIONES, int(tick))]
    for v, w in acciones:
        partes.append(struct.pack(_FMT_PAR, float(v), float(w)))
    return b"".join(partes)


def empaquetar_reset(tick: int) -> bytes:
    """Serializa el mensaje de RESET (frenar motores, descartar acción)."""
    return struct.pack(_FMT_CABECERA, TIPO_RESET, int(tick))


def leer_tipo(datos: bytes) -> int:
    """
    Lee el byte de tipo de un mensaje del canal de bajada sin desempaquetar
    el resto. Retorna 0 si el mensaje es demasiado corto.
    """
    if len(datos) < 1:
        return 0
    return int(struct.unpack("<B", datos[:1])[0])


def extraer_accion(datos: bytes, id_agente: int) -> Tuple[int, float, float]:
    """
    Extrae el par (v, ω) del agente `id_agente` de un mensaje de ACCIONES.

    Lee sólo su propio offset (5 + 16·id), sin deserializar los demás pares.

    Retorna
    -------
    (tick_decision, v, omega)

    Raises
    ------
    ValueError : si el tipo no es ACCIONES o el mensaje no contiene el índice.
    """
    tipo, tick = struct.unpack(_FMT_CABECERA, datos[:TAM_CABECERA])
    if tipo != TIPO_ACCIONES:
        raise ValueError(f"Tipo {tipo} no es ACCIONES ({TIPO_ACCIONES}).")

    inicio = TAM_CABECERA + TAM_PAR * int(id_agente)
    fin    = inicio + TAM_PAR
    if len(datos) < fin:
        raise ValueError(
            f"Mensaje de acciones de {len(datos)} B no contiene el índice "
            f"{id_agente} (requiere ≥ {fin} B)."
        )
    v, w = struct.unpack(_FMT_PAR, datos[inicio:fin])
    return int(tick), float(v), float(w)


# =============================================================================
# MARCOS DE REFERENCIA
# =============================================================================
# El env vive en [0, Wx] × [0, Wy] con origen en la esquina inferior izquierda;
# Webots usa origen centrado. Estas constantes son las mismas validadas en
# supervisor_fisica (demo de 1 robot).

ARENA_WX: float = 3.0
ARENA_WY: float = 3.0
OFFSET_X: float = ARENA_WX / 2.0
OFFSET_Y: float = ARENA_WY / 2.0

# Compensación angular Compass → convención del env (θ=0 ⇒ +x global).
# Valor calibrado empíricamente en el demo de 1 robot.
OFFSET_HEADING_RAD: float = 0.0

# Offset del marco local del proto al escribir `rotation` de un nodo Robot:
# el "adelante" del Pololu es +Y local (ruedas en ±X).
OFFSET_PROTO_RAD: float = -math.pi / 2.0


def webots_a_env_xy(x_w: float, y_w: float) -> Tuple[float, float]:
    """Marco Webots (centrado) → marco env (origen en esquina)."""
    return (x_w + OFFSET_X, y_w + OFFSET_Y)


def env_a_webots_xy(x_env: float, y_env: float) -> Tuple[float, float]:
    """Marco env (origen en esquina) → marco Webots (centrado)."""
    return (x_env - OFFSET_X, y_env - OFFSET_Y)


def compass_a_heading(componentes: List[float]) -> float:
    """
    Convierte las componentes del Compass (rotado 0 0 1 π/2 en el .wbt) al
    heading θ del marco del env, envuelto a (-π, π].

    Fórmula heredada del controlador MATLAB del lab, simplificada a
    `θ = atan2(mag[0], mag[1])`, más OFFSET_HEADING_RAD.
    """
    theta = math.atan2(componentes[0], componentes[1]) + OFFSET_HEADING_RAD
    return math.atan2(math.sin(theta), math.cos(theta))


# =============================================================================
# MODELO CINEMÁTICO DEL DIFERENCIAL
# =============================================================================
# Geometría del .wbt (NO del hardware real): radio de rueda y medio eje.

RADIO_RUEDA: float = 0.035
MEDIO_EJE:   float = 0.07

# Signos de motor calibrados en el demo de 1 robot.
SIGNO_MOTOR_1: int = -1   # rueda DERECHA (anchor +x)
SIGNO_MOTOR_2: int = -1   # rueda IZQUIERDA (anchor -x)

# Cota del RotationalMotor declarada en el .wbt.
VELOCIDAD_MAX_RUEDA: float = 84.0


def convertir_velocidades_a_ruedas(
    v:         float,
    omega:     float,
    radio:     float = RADIO_RUEDA,
    medio_eje: float = MEDIO_EJE,
) -> Tuple[float, float]:
    """
    Modelo cinemático INVERSO del diferencial (política → ruedas):

        φ̇_R = (v + ℓ·ω) / r
        φ̇_L = (v − ℓ·ω) / r

    Derivado por restricciones de rodamiento / no-deslizamiento (metodología
    A⁺·B, clase MT3005 — Robótica 1, UVG). Es el inverso del modelo directo
    v = (r/2)(φ̇_R + φ̇_L), ω = (r/2ℓ)(φ̇_R − φ̇_L).

    Unidades: las salidas están en rad/s y van DIRECTO a
    `RotationalMotor.setVelocity()`. NO convertir a rpm.

    Retorna
    -------
    (phi_R, phi_L) : rad/s de las ruedas derecha e izquierda, antes de
                     aplicar SIGNO_MOTOR_*.
    """
    phi_R = (v + medio_eje * omega) / radio
    phi_L = (v - medio_eje * omega) / radio
    return phi_R, phi_L
