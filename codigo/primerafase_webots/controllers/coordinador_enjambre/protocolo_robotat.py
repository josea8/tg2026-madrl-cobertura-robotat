"""
protocolo_robotat.py
====================
Formato en el cable del Robotat, relevado de `robotat/*.m`, más las
conversiones de unidades y de marco. NO abre sockets: es puro
serializar/deserializar y transformar, para que sea testeable sin hardware.

Dos protocolos distintos
------------------------
  POSES (servidor 192.168.50.200:1883) — JSON sobre TCP.
      petición : {"dst":1,"cmd":1,"pld":[<ids de marcador>]}   (ASCII, sin
                 terminador explícito)
      respuesta: array JSON PLANO, agente-major, 7 valores por agente:
                 [x, y, z, qw, qx, qy, qz]  (cuaternión ESCALAR PRIMERO)

  RUEDAS (cada robot, 192.168.50.10<id>:9090) — CBOR binario, 11 bytes:
      0x82            array(2)
      0xFA + 4 bytes  float32 BIG-ENDIAN  → dphiL
      0xFA + 4 bytes  float32 BIG-ENDIAN  → dphiR
  El original hace `fliplr(typecast(single(x),'uint8'))`, que invierte el
  little-endian nativo de MATLAB: el cable es big-endian (network order).

No hay handshake ni autenticación en ninguno de los dos. La desconexión del
servidor de poses es el literal ASCII 'EXIT'.

⚠ ORDEN DE RUEDAS — ver `codificar_velocidades_rueda`.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import json
import math
import struct
from typing import Dict, List, Optional, Tuple

import numpy as np

import config_robotat as cfg

# =============================================================================
# COMANDO DE RUEDAS — EL ÚNICO PUNTO DONDE SE FIJA EL ORDEN
# =============================================================================

def codificar_velocidades_rueda(rpm_izq: float, rpm_der: float) -> bytes:
    """
    Codifica el comando CBOR de 11 bytes para un robot.

    ⚠ ORDEN DE ARGUMENTOS — ÚNICO PUNTO DE VERDAD DEL PROYECTO ⚠

    `robotat_3pi_set_wheel_velocities(robot, dphiL, dphiR)` recibe la rueda
    IZQUIERDA PRIMERO. Nuestro modelo diferencial, en cambio, produce
    `(φ̇_R, φ̇_L)` — derecha primero (ver `convertir_velocidades_a_ruedas`
    en `protocolo.py`). Los dos órdenes son opuestos.

    Toda inversión de ruedas del proyecto debe pasar por acá y por
    `accion_a_rpm`. En Webots un error equivalente de asignación de motor
    costó dos sesiones de depuración; el test `test_robotat.py` falla si
    alguien invierte este orden.

    Parámetros
    ----------
    rpm_izq, rpm_der : velocidades de rueda en RPM (no rad/s), ya saturadas.

    Retorna
    -------
    bytes — 11 bytes exactos, big-endian.
    """
    return (
        b"\x82"
        + b"\xfa" + struct.pack(">f", float(rpm_izq))
        + b"\xfa" + struct.pack(">f", float(rpm_der))
    )


def decodificar_velocidades_rueda(datos: bytes) -> Tuple[float, float]:
    """
    Inversa de `codificar_velocidades_rueda`. La usa el simulador del
    laboratorio para leer lo que el cliente envía.

    Retorna
    -------
    (rpm_izq, rpm_der)

    Raises
    ------
    ValueError : si el mensaje no tiene la forma esperada.
    """
    if len(datos) != 11:
        raise ValueError(f"Comando de rueda de {len(datos)} B, esperado 11.")
    if datos[0] != 0x82 or datos[1] != 0xFA or datos[6] != 0xFA:
        raise ValueError("Cabeceras CBOR inválidas en comando de rueda.")
    rpm_izq = struct.unpack(">f", datos[2:6])[0]
    rpm_der = struct.unpack(">f", datos[7:11])[0]
    return float(rpm_izq), float(rpm_der)


def rad_s_a_rpm(rad_s: float) -> float:
    """rad/s → RPM. rpm = rad/s · 60/(2π)."""
    return float(rad_s) * 60.0 / (2.0 * math.pi)


def accion_a_rpm(
    v: float, omega: float, radio: float, medio_eje: float,
) -> Tuple[float, float, bool]:
    """
    (v, ω) del cuerpo → RPM de rueda IZQUIERDA y DERECHA, saturadas.

    Aplica el modelo diferencial inverso ya validado en Webots:
        φ̇_R = (v + ℓ·ω) / r      φ̇_L = (v − ℓ·ω) / r     [rad/s]
    y convierte a RPM. Devuelve además si hubo saturación, para que el
    llamador pueda registrarla (el original de MATLAB emite `warning`).

    Retorna
    -------
    (rpm_izq, rpm_der, saturo)
        ⚠ IZQUIERDA PRIMERO, igual que el comando en el cable.
    """
    phi_der = (v + medio_eje * omega) / radio
    phi_izq = (v - medio_eje * omega) / radio
    rpm_der = rad_s_a_rpm(phi_der)
    rpm_izq = rad_s_a_rpm(phi_izq)
    saturo = (abs(rpm_der) > cfg.RPM_MAX) or (abs(rpm_izq) > cfg.RPM_MAX)
    rpm_der = max(-cfg.RPM_MAX, min(cfg.RPM_MAX, rpm_der))
    rpm_izq = max(-cfg.RPM_MAX, min(cfg.RPM_MAX, rpm_izq))
    return rpm_izq, rpm_der, saturo


# =============================================================================
# PETICIÓN Y RESPUESTA DE POSES
# =============================================================================

def codificar_peticion_poses(ids_marcadores: List[int]) -> bytes:
    """
    Petición JSON de poses, con el mismo esquema y orden de campos que
    `robotat_get_pose.m`: {"dst":1,"cmd":1,"pld":[...]}.

    Raises
    ------
    ValueError : si algún ID sale del rango 1–100 que valida el original.
    """
    if not ids_marcadores:
        raise ValueError("Lista de marcadores vacía.")
    if min(ids_marcadores) < 1 or max(ids_marcadores) > 100:
        raise ValueError(
            f"IDs de marcador fuera de 1–100: {ids_marcadores}"
        )
    cuerpo = {"dst": 1, "cmd": 1, "pld": [int(i) for i in ids_marcadores]}
    return json.dumps(cuerpo, separators=(",", ":")).encode("ascii")


VALORES_POR_AGENTE: int = 7   # x, y, z, qw, qx, qy, qz

#: Tolerancia para reconocer el placeholder de "marcador no trackeado".
#: Deliberadamente diminuta: el servidor manda ceros y unos EXACTOS, así
#: que no hace falta margen, y uno amplio empezaría a rechazar poses reales
#: cerca del origen. Ver `pose_es_valida`.
TOL_PLACEHOLDER: float = 1e-9


def decodificar_respuesta_poses(
    datos: bytes, n_esperados: int,
) -> Optional[np.ndarray]:
    """
    Decodifica la respuesta del servidor a un array (N, 7).

    El original hace `reshape(mocap_data, [7, N])'`, y como el `reshape` de
    MATLAB es column-major, eso equivale a interpretar el array plano como
    AGENTE-MAJOR: los 7 primeros valores son del primer agente, etc.

    VALIDACIÓN DEFENSIVA: no sabemos qué devuelve el servidor cuando un
    marcador no está visible —el código de referencia no lo maneja—, así que
    se valida la forma y se devuelve None ante cualquier cosa inesperada. El
    llamador trata ese caso como "no llegó pose", que entra en la lógica de
    pose vieja ya existente y validada.

    ⚠ CAMBIO SEPARADO (2026-09-24), no relacionado con los congelamientos
    de borde: `np.asarray` lanza `ValueError` o `TypeError` si la lista trae
    algo que no es número (un texto, un objeto, listas de largos distintos).
    Antes esa excepción subía por la fuente y tiraba la sesión; ahora es una
    respuesta no utilizable más, que el llamador cuenta como consulta
    fallida. Nunca se observó en el laboratorio: lo encontró la auditoría.

    Retorna
    -------
    np.ndarray (N, 7) o None si la respuesta no es utilizable.
    """
    try:
        plano = json.loads(datos.decode("ascii", errors="strict"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(plano, list):
        return None
    try:
        arreglo = np.asarray(plano, dtype=np.float64).ravel()
    except (ValueError, TypeError):
        return None
    if arreglo.size != n_esperados * VALORES_POR_AGENTE:
        return None
    return arreglo.reshape(n_esperados, VALORES_POR_AGENTE)


# =============================================================================
# CUATERNIÓN → HEADING PLANO (sin pasar por Euler completo)
# =============================================================================

def heading_desde_cuaternion(
    qw: float, qx: float, qy: float, qz: float,
) -> Tuple[float, float]:
    """
    Extrae el heading plano (yaw) directamente del cuaternión, y la
    inclinación del cuerpo rígido.

    Por qué NO se usa `q2eul`: esa función emite `warning` en singularidades
    de la secuencia de Euler y **devuelve un valor igualmente**, con una
    componente forzada a cero. Si el robot pasa por esa configuración el
    heading sale mal sin error. Extraer el yaw por atan2 evita la
    parametrización de Euler completa:

        yaw = atan2( 2(qw·qz + qx·qy),  1 − 2(qy² + qz²) )

    Esta fórmula no tiene singularidad en yaw para un cuerpo cercano al
    plano. Sí deja de ser interpretable si el rígido está muy inclinado, así
    que se devuelve también la inclinación para que el llamador la valide
    (es la comprobación que reemplaza al `warning` del original).

    Retorna
    -------
    (yaw_rad, inclinacion_rad)
        inclinacion = ángulo entre el eje Z del cuerpo y el Z del mundo.
    """
    # Yaw por atan2 — sin singularidad para cuerpos cercanos al plano.
    yaw = math.atan2(
        2.0 * (qw * qz + qx * qy),
        1.0 - 2.0 * (qy * qy + qz * qz),
    )
    # Inclinación: el eje Z del cuerpo rotado, contra el Z del mundo.
    # z_cuerpo·z_mundo = 1 − 2(qx² + qy²)
    coseno = max(-1.0, min(1.0, 1.0 - 2.0 * (qx * qx + qy * qy)))
    inclinacion = math.acos(coseno)
    return yaw, inclinacion


# =============================================================================
# VALIDACIÓN DEFENSIVA Y TRANSFORMACIÓN DE MARCO
# =============================================================================

def es_placeholder_no_trackeado(fila: np.ndarray) -> bool:
    """
    ¿Es el placeholder de "marcador no trackeado"? Origen + cuaternión
    identidad, medido contra el Robotat real: `[0, -0, 0, 1, 0, -0, 0]`.

    Existe aparte de `pose_es_valida` porque hay un caso —la etapa 2— donde
    hace falta rechazar ESTO y sólo esto. Esa etapa detecta a propósito
    posiciones de magnitud enorme, que es la firma de un servidor que
    entrega MILÍMETROS en vez de metros; `pose_es_valida` las rechaza por
    fuera de rango y le taparía ese diagnóstico.
    """
    if fila.shape != (VALORES_POR_AGENTE,) or not np.all(np.isfinite(fila)):
        return False
    x, y, z, qw, qx, qy, qz = (float(v) for v in fila)
    return (abs(x) <= TOL_PLACEHOLDER and abs(y) <= TOL_PLACEHOLDER
            and abs(z) <= TOL_PLACEHOLDER
            and abs(qw - 1.0) <= TOL_PLACEHOLDER
            and abs(qx) <= TOL_PLACEHOLDER and abs(qy) <= TOL_PLACEHOLDER
            and abs(qz) <= TOL_PLACEHOLDER)


def pose_es_valida(fila: np.ndarray) -> Tuple[bool, str]:
    """
    Valida una fila `[x, y, z, qw, qx, qy, qz]` del servidor.

    MEDIDO EN EL LABORATORIO (2026-08-25): un marcador NO trackeado
    devuelve `[0, -0, 0, 1, 0, -0, 0]` — posición en el origen y cuaternión
    IDENTIDAD. No son NaN, no es un error, y no son menos filas.

    Ese placeholder pasaba TODAS las comprobaciones anteriores: la norma
    del cuaternión identidad es exactamente 1.0, y el origen cae dentro del
    rango del laboratorio. Una etapa 0 contra un marcador invisible
    reportaba "20/20 poses válidas" con veinte filas idénticas de ceros, y
    casi se calibra una sesión entera sobre eso. Por eso se rechaza
    explícitamente abajo: es el ÚNICO caso donde una pose formalmente
    impecable no es un dato.

    El riesgo de rechazarlo es un falso positivo si un robot estuviera
    justo en el origen del laboratorio Y perfectamente alineado. Se acota
    exigiendo las DOS cosas a la vez, con tolerancia mínima: el origen
    exacto con orientación exacta no es una pose que ocurra midiendo.

    Validando además forma, finitud, rango plausible y norma del
    cuaternión, el cliente sigue siendo correcto aunque otra versión del
    servidor conteste ceros totales o NaN.

    Retorna
    -------
    (es_valida, motivo)
    """
    if fila.shape != (VALORES_POR_AGENTE,):
        return False, f"forma {fila.shape}"
    if not np.all(np.isfinite(fila)):
        return False, "valores no finitos"

    x, y, z = float(fila[0]), float(fila[1]), float(fila[2])

    # Placeholder de marcador NO trackeado: origen + cuaternión identidad.
    # Se comprueba ANTES del rango, porque el origen está DENTRO del rango
    # y por eso pasaba inadvertido. Ver la nota del docstring.
    en_el_origen = (abs(x) <= TOL_PLACEHOLDER and abs(y) <= TOL_PLACEHOLDER
                    and abs(z) <= TOL_PLACEHOLDER)
    if en_el_origen:
        qw, qx, qy, qz = (float(c) for c in fila[3:7])
        if (abs(qw - 1.0) <= TOL_PLACEHOLDER and abs(qx) <= TOL_PLACEHOLDER
                and abs(qy) <= TOL_PLACEHOLDER
                and abs(qz) <= TOL_PLACEHOLDER):
            return False, "marcador no trackeado (origen + cuaternión identidad)"

    xe = x * cfg.ESCALA_POSICION
    ye = y * cfg.ESCALA_POSICION
    ze = z * cfg.ESCALA_POSICION
    if not (cfg.RANGO_LAB_X_M[0] <= xe <= cfg.RANGO_LAB_X_M[1]):
        return False, f"x={xe:.3f} fuera de rango"
    if not (cfg.RANGO_LAB_Y_M[0] <= ye <= cfg.RANGO_LAB_Y_M[1]):
        return False, f"y={ye:.3f} fuera de rango"
    if not (cfg.RANGO_LAB_Z_M[0] <= ze <= cfg.RANGO_LAB_Z_M[1]):
        return False, f"z={ze:.3f} fuera de rango"

    q = fila[3:7]
    norma = float(np.linalg.norm(q))
    if abs(norma - 1.0) > cfg.TOL_NORMA_CUATERNION:
        return False, f"cuaternión de norma {norma:.4f}"

    _, inclinacion = heading_desde_cuaternion(*(float(c) for c in q))
    if inclinacion > cfg.INCLINACION_MAX_RAD:
        return False, f"inclinación {math.degrees(inclinacion):.1f}°"

    return True, ""


def lab_a_env(x_lab: float, y_lab: float, yaw_lab: float,
              offset_heading_rad: Optional[float] = None) -> np.ndarray:
    """
    Transforma una pose del marco del laboratorio al marco del env.

    Aplica, en orden: escala → rotación del marco → traslación; y suma el
    offset de heading. Los cuatro parámetros salen de `config_robotat` y
    están marcados NO VERIFICADO hasta calibrarlos (README §C1–C3).

    Parámetros
    ----------
    offset_heading_rad :
        Offset de rumbo de ESTE robot. El offset describe cómo quedó montada
        la constelación sobre un chasis concreto y **varía de robot a
        robot**: la tabla del laboratorio le da al robot 10 un valor que se
        aparta 127° de los demás. Con un enjambre hay que pasar el de cada
        uno (`config_robotat.offset_rumbo_de_robot`).

        `None` usa el escalar global `cfg.OFFSET_HEADING_RAD`, que es lo
        correcto para una sesión de UN robot —ahí ese escalar ES el del
        robot calibrado— y mantiene el comportamiento de siempre para todos
        los llamadores que no lo pasan.

    Retorna
    -------
    np.ndarray (3,) — [x_env, y_env, θ_env]
    """
    if offset_heading_rad is None:
        offset_heading_rad = cfg.OFFSET_HEADING_RAD
    xs = x_lab * cfg.ESCALA_POSICION
    ys = y_lab * cfg.ESCALA_POSICION
    c, s = math.cos(cfg.ROTACION_MARCO_RAD), math.sin(cfg.ROTACION_MARCO_RAD)
    x_env = c * xs - s * ys + cfg.TRASLACION_X_M
    y_env = s * xs + c * ys + cfg.TRASLACION_Y_M
    th = yaw_lab + cfg.ROTACION_MARCO_RAD + offset_heading_rad
    th = math.atan2(math.sin(th), math.cos(th))
    return np.array([x_env, y_env, th], dtype=np.float64)
