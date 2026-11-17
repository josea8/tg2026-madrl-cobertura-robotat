"""
test_robotat.py
===============
Pruebas del formato en el cable y de las conversiones del puente al Robotat.
Corren SIN hardware y SIN Webots:

    python test_robotat.py

Por qué existe este archivo
---------------------------
Todo lo que se pueda equivocar silenciosamente —un orden de ruedas invertido,
un factor de unidades, un cuaternión mal interpretado— produce un robot que
NO falla: se mueve mal. En Webots, un error de asignación de motor
equivalente costó dos sesiones de depuración porque el síntoma (el robot no
llega a los hotspots) es indistinguible de "la política no sirve".

Cada prueba de acá está escrita para FALLAR si alguien invierte, reescala o
reinterpreta algo. En particular `PruebaOrdenDeRuedas`, que es el punto donde
se cruzan dos convenciones opuestas.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import math
import socket
import io
import contextlib
import struct
import time
import unittest
from typing import Tuple

import numpy as np

import config_robotat as cfg
from adaptadores_robotat import descartar_buffer_pendiente
from protocolo import convertir_velocidades_a_ruedas
from protocolo_robotat import (
    VALORES_POR_AGENTE,
    accion_a_rpm,
    codificar_peticion_poses,
    codificar_velocidades_rueda,
    decodificar_respuesta_poses,
    decodificar_velocidades_rueda,
    heading_desde_cuaternion,
    lab_a_env,
    pose_es_valida,
    rad_s_a_rpm,
)

# Geometría del robot físico (NO la de Webots; ver config_robotat).
R_M: float = cfg.RADIO_RUEDA_M
L_M: float = cfg.MEDIO_EJE_M

# Cotas de la política, para el caso peor de saturación.
V_MAX_POLITICA:     float = 0.31      # m/s   (concentration_dynamics.V_MAX)
OMEGA_MAX_POLITICA: float = 6.2832    # rad/s (concentration_dynamics.OMEGA_MAX)


def _cuaternion_desde_euler(
    roll: float, pitch: float, yaw: float,
) -> Tuple[float, float, float, float]:
    """
    Cuaternión (qw, qx, qy, qz) de una secuencia ZYX (yaw→pitch→roll).

    Implementación INDEPENDIENTE de `heading_desde_cuaternion`: se usa para
    verificar que el yaw extraído por atan2 recupera el yaw que se metió, sin
    reusar la misma fórmula que se está probando.
    """
    cr, sr = math.cos(roll / 2.0),  math.sin(roll / 2.0)
    cp, sp = math.cos(pitch / 2.0), math.sin(pitch / 2.0)
    cy, sy = math.cos(yaw / 2.0),   math.sin(yaw / 2.0)
    return (
        cr * cp * cy + sr * sp * sy,   # qw
        sr * cp * cy - cr * sp * sy,   # qx
        cr * sp * cy + sr * cp * sy,   # qy
        cr * cp * sy - sr * sp * cy,   # qz
    )


# =============================================================================
# 1. ORDEN DE RUEDAS — LA PRUEBA CRÍTICA
# =============================================================================

class PruebaOrdenDeRuedas(unittest.TestCase):
    """
    El Robotat recibe (dphiL, dphiR): IZQUIERDA PRIMERO.
    Nuestro modelo diferencial produce (φ̇_R, φ̇_L): DERECHA PRIMERO.

    Si alguien "simplifica" pasando la tupla de `convertir_velocidades_a_ruedas`
    directo al codificador, TODAS estas pruebas fallan.
    """

    def test_primer_float_del_cable_es_la_izquierda(self) -> None:
        """Prueba posicional pura: byte a byte, con valores distinguibles."""
        tramo = codificar_velocidades_rueda(rpm_izq=-100.0, rpm_der=+250.0)
        self.assertEqual(len(tramo), 11)
        self.assertEqual(tramo[0], 0x82)          # array(2)
        self.assertEqual(tramo[1], 0xFA)          # float32
        self.assertEqual(tramo[6], 0xFA)
        primero = struct.unpack(">f", tramo[2:6])[0]
        segundo = struct.unpack(">f", tramo[7:11])[0]
        self.assertAlmostEqual(primero, -100.0, places=4,
                               msg="El PRIMER float del cable debe ser la IZQUIERDA")
        self.assertAlmostEqual(segundo, +250.0, places=4,
                               msg="El SEGUNDO float del cable debe ser la DERECHA")

    def test_giro_puro_a_la_izquierda(self) -> None:
        """
        ω > 0 (antihorario) con v = 0 ⇒ la rueda izquierda va hacia ATRÁS y la
        derecha hacia ADELANTE. Si el orden estuviera invertido, el robot
        giraría al revés y esta prueba lo detecta por el SIGNO del primer float.
        """
        rpm_izq, rpm_der, _ = accion_a_rpm(0.0, +3.0, R_M, L_M)
        self.assertLess(rpm_izq, 0.0, "giro a la izquierda ⇒ rueda izq negativa")
        self.assertGreater(rpm_der, 0.0, "giro a la izquierda ⇒ rueda der positiva")
        self.assertAlmostEqual(rpm_izq, -rpm_der, places=6,
                               msg="giro puro ⇒ ruedas simétricas")

        leido_izq, leido_der = decodificar_velocidades_rueda(
            codificar_velocidades_rueda(rpm_izq, rpm_der)
        )
        self.assertLess(leido_izq, 0.0,
                        "tras el viaje por el cable, el primer valor sigue "
                        "siendo la izquierda (negativa en giro a izquierda)")
        self.assertGreater(leido_der, 0.0)

    def test_giro_puro_a_la_derecha(self) -> None:
        """ω < 0 ⇒ espejo exacto del caso anterior."""
        rpm_izq, rpm_der, _ = accion_a_rpm(0.0, -3.0, R_M, L_M)
        self.assertGreater(rpm_izq, 0.0, "giro a la derecha ⇒ rueda izq positiva")
        self.assertLess(rpm_der, 0.0, "giro a la derecha ⇒ rueda der negativa")

        leido_izq, leido_der = decodificar_velocidades_rueda(
            codificar_velocidades_rueda(rpm_izq, rpm_der)
        )
        self.assertGreater(leido_izq, 0.0)
        self.assertLess(leido_der, 0.0)

    def test_avance_puro(self) -> None:
        """
        v > 0, ω = 0 ⇒ ambas ruedas iguales y positivas. Este caso NO
        distingue el orden (es simétrico): está para verificar la magnitud, y
        para dejar explícito por qué no alcanza con probar sólo el avance.
        """
        rpm_izq, rpm_der, saturo = accion_a_rpm(0.20, 0.0, R_M, L_M)
        self.assertAlmostEqual(rpm_izq, rpm_der, places=9)
        self.assertGreater(rpm_izq, 0.0)
        self.assertFalse(saturo)
        esperado = rad_s_a_rpm(0.20 / R_M)
        self.assertAlmostEqual(rpm_izq, esperado, places=6)

    def test_es_opuesto_al_orden_del_modelo_diferencial(self) -> None:
        """
        Prueba de guardia sobre la relación entre las dos convenciones: la
        tupla de `convertir_velocidades_a_ruedas` es (R, L), la de
        `accion_a_rpm` es (izq, der). Deben quedar CRUZADAS.
        """
        v, omega = 0.10, 2.0
        phi_r, phi_l = convertir_velocidades_a_ruedas(v, omega, R_M, L_M)
        rpm_izq, rpm_der, _ = accion_a_rpm(v, omega, R_M, L_M)
        self.assertAlmostEqual(rpm_der, rad_s_a_rpm(phi_r), places=6)
        self.assertAlmostEqual(rpm_izq, rad_s_a_rpm(phi_l), places=6)
        self.assertNotAlmostEqual(rpm_izq, rpm_der, places=3,
                                  msg="el caso de prueba debe ser asimétrico "
                                      "para que el cruce sea detectable")


# =============================================================================
# 2. UNIDADES Y SATURACIÓN
# =============================================================================

class PruebaConversionDeUnidades(unittest.TestCase):

    def test_accion_nula(self) -> None:
        rpm_izq, rpm_der, saturo = accion_a_rpm(0.0, 0.0, R_M, L_M)
        self.assertEqual((rpm_izq, rpm_der, saturo), (0.0, 0.0, False))
        self.assertEqual(
            codificar_velocidades_rueda(0.0, 0.0),
            b"\x82\xfa\x00\x00\x00\x00\xfa\x00\x00\x00\x00",
        )

    def test_factor_rad_s_a_rpm(self) -> None:
        self.assertAlmostEqual(rad_s_a_rpm(2.0 * math.pi), 60.0, places=9)
        self.assertAlmostEqual(rad_s_a_rpm(0.0), 0.0, places=12)
        self.assertAlmostEqual(rad_s_a_rpm(-2.0 * math.pi), -60.0, places=9)

    def test_avance_maximo(self) -> None:
        """v = V_MAX, ω = 0."""
        rpm_izq, rpm_der, saturo = accion_a_rpm(V_MAX_POLITICA, 0.0, R_M, L_M)
        self.assertAlmostEqual(rpm_izq, rpm_der, places=9)
        self.assertFalse(saturo, f"avance máximo satura: {rpm_izq:.1f} rpm")
        self.assertLessEqual(abs(rpm_izq), cfg.RPM_MAX)

    def test_giro_maximo(self) -> None:
        """v = 0, ω = Ω_MAX."""
        rpm_izq, rpm_der, saturo = accion_a_rpm(0.0, OMEGA_MAX_POLITICA, R_M, L_M)
        self.assertFalse(saturo, f"giro máximo satura: {rpm_der:.1f} rpm")
        self.assertLessEqual(max(abs(rpm_izq), abs(rpm_der)), cfg.RPM_MAX)

    def test_peor_combinacion_reporta_saturacion(self) -> None:
        """
        Peor caso de la caja de acciones: |v| = V_MAX y |ω| = Ω_MAX del mismo
        signo. Se REPORTA el margen; no se afirma que no satura, porque eso
        depende de la geometría (marcada NO VERIFICADA en config_robotat) y
        cambiará al medir los robots reales.
        """
        rpm_izq, rpm_der, saturo = accion_a_rpm(
            V_MAX_POLITICA, OMEGA_MAX_POLITICA, R_M, L_M
        )
        pico = max(abs(rpm_izq), abs(rpm_der))
        print(f"\n    [peor caso] v={V_MAX_POLITICA} m/s, ω={OMEGA_MAX_POLITICA} "
              f"rad/s  con r={R_M} m, ℓ={L_M} m")
        print(f"    → izq {rpm_izq:+8.2f} rpm   der {rpm_der:+8.2f} rpm   "
              f"pico {pico:.2f} / {cfg.RPM_MAX:.0f} rpm  "
              f"({100.0 * pico / cfg.RPM_MAX:.1f} % del límite)"
              f"{'  ⚠ SATURA' if saturo else ''}")
        self.assertLessEqual(pico, cfg.RPM_MAX,
                             "la saturación debe estar aplicada a la salida")

    def test_saturacion_se_detecta_y_se_recorta(self) -> None:
        """Caso deliberadamente fuera de rango: debe recortar Y avisar."""
        rpm_izq, rpm_der, saturo = accion_a_rpm(10.0, 0.0, R_M, L_M)
        self.assertTrue(saturo)
        self.assertAlmostEqual(rpm_izq, cfg.RPM_MAX, places=6)
        self.assertAlmostEqual(rpm_der, cfg.RPM_MAX, places=6)

    def test_geometria_no_es_la_de_webots(self) -> None:
        """
        Guardia contra el error de reusar la geometría del PROTO. Si alguien
        copia RADIO_RUEDA = 0.035 acá, las velocidades salen mal por ~2.2×.
        """
        self.assertNotAlmostEqual(cfg.RADIO_RUEDA_M, 0.035, places=4)
        self.assertNotAlmostEqual(cfg.MEDIO_EJE_M, 0.07, places=4)


class PruebaEndianness(unittest.TestCase):
    """
    El original de MATLAB hace `fliplr` sobre el typecast little-endian, o sea
    que el cable es BIG-ENDIAN. Un error acá no produce un número apenas
    distinto: produce basura de varios órdenes de magnitud.
    """

    def test_un_float_conocido(self) -> None:
        tramo = codificar_velocidades_rueda(1.0, 1.0)
        self.assertEqual(tramo[2:6], b"\x3f\x80\x00\x00")   # 1.0f big-endian
        self.assertNotEqual(tramo[2:6], b"\x00\x00\x80\x3f")

    def test_ida_y_vuelta(self) -> None:
        for izq, der in [(0.0, 0.0), (400.0, -400.0), (12.5, -0.25),
                         (-1.0, 333.0)]:
            leido = decodificar_velocidades_rueda(
                codificar_velocidades_rueda(izq, der)
            )
            self.assertAlmostEqual(leido[0], izq, places=3)
            self.assertAlmostEqual(leido[1], der, places=3)

    def test_mensaje_corrupto_lanza(self) -> None:
        with self.assertRaises(ValueError):
            decodificar_velocidades_rueda(b"\x82\xfa\x00")
        with self.assertRaises(ValueError):
            decodificar_velocidades_rueda(b"\x00" * 11)


# =============================================================================
# 3. PETICIÓN Y RESPUESTA DE POSES
# =============================================================================

class PruebaProtocoloDePoses(unittest.TestCase):

    def test_peticion_tiene_el_esquema_del_original(self) -> None:
        import json
        cuerpo = json.loads(codificar_peticion_poses([1, 2, 3]).decode("ascii"))
        self.assertEqual(cuerpo, {"dst": 1, "cmd": 1, "pld": [1, 2, 3]})

    def test_peticion_valida_rango_de_marcadores(self) -> None:
        with self.assertRaises(ValueError):
            codificar_peticion_poses([])
        with self.assertRaises(ValueError):
            codificar_peticion_poses([0])
        with self.assertRaises(ValueError):
            codificar_peticion_poses([101])

    def test_respuesta_es_agente_major(self) -> None:
        """
        El original hace `reshape(datos, [7, N])'` y MATLAB reshapea
        column-major, así que los 7 PRIMEROS valores son del PRIMER agente.
        Si se interpretara como valor-major, el agente 1 recibiría x del
        agente 0 y todo el enjambre quedaría cruzado.
        """
        import json
        agente_0 = [1.0, 2.0, 0.0, 1.0, 0.0, 0.0, 0.0]
        agente_1 = [9.0, 8.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        crudo = json.dumps(agente_0 + agente_1).encode("ascii")
        m = decodificar_respuesta_poses(crudo, n_esperados=2)
        self.assertIsNotNone(m)
        self.assertEqual(m.shape, (2, VALORES_POR_AGENTE))
        np.testing.assert_allclose(m[0], agente_0)
        np.testing.assert_allclose(m[1], agente_1)

    def test_respuesta_incompleta_devuelve_none(self) -> None:
        """
        No sabemos qué manda el servidor con un marcador ocluido. Cualquier
        respuesta que no tenga exactamente 7·N valores se descarta, y el
        coordinador cae en su lógica ya validada de "pose vieja".
        """
        import json
        self.assertIsNone(decodificar_respuesta_poses(
            json.dumps([0.0] * 7).encode("ascii"), n_esperados=2))
        self.assertIsNone(decodificar_respuesta_poses(b"", n_esperados=1))
        self.assertIsNone(decodificar_respuesta_poses(b"no-json", n_esperados=1))
        self.assertIsNone(decodificar_respuesta_poses(
            b'{"error":"sin marcador"}', n_esperados=1))


# =============================================================================
# 4. CUATERNIÓN → HEADING
# =============================================================================

class PruebaHeading(unittest.TestCase):

    def test_identidad(self) -> None:
        yaw, inc = heading_desde_cuaternion(1.0, 0.0, 0.0, 0.0)
        self.assertAlmostEqual(yaw, 0.0, places=12)
        self.assertAlmostEqual(inc, 0.0, places=6)

    def test_recupera_el_yaw_metido(self) -> None:
        """
        Se construye el cuaternión con una implementación independiente y se
        verifica que el atan2 devuelve el mismo yaw, incluso con roll y pitch
        no nulos (que es donde la parametrización de Euler completa se pone
        delicada).
        """
        for yaw_ref in np.linspace(-math.pi + 0.05, math.pi - 0.05, 25):
            for roll, pitch in [(0.0, 0.0), (0.15, -0.10), (-0.25, 0.20)]:
                q = _cuaternion_desde_euler(roll, pitch, float(yaw_ref))
                yaw, _ = heading_desde_cuaternion(*q)
                self.assertAlmostEqual(
                    math.atan2(math.sin(yaw - yaw_ref),
                               math.cos(yaw - yaw_ref)),
                    0.0, places=9,
                    msg=f"yaw={yaw_ref:.3f} roll={roll} pitch={pitch}",
                )

    def test_giro_de_90_grados(self) -> None:
        q = _cuaternion_desde_euler(0.0, 0.0, math.pi / 2.0)
        yaw, inc = heading_desde_cuaternion(*q)
        self.assertAlmostEqual(yaw, math.pi / 2.0, places=9)
        self.assertAlmostEqual(inc, 0.0, places=6)

    def test_inclinacion_se_mide_bien(self) -> None:
        """La inclinación devuelta es el ángulo real entre z_cuerpo y z_mundo."""
        for angulo in [0.0, 0.1, 0.5, 1.0]:
            q = _cuaternion_desde_euler(angulo, 0.0, 0.0)   # roll puro
            _, inc = heading_desde_cuaternion(*q)
            self.assertAlmostEqual(inc, angulo, places=9)
            q = _cuaternion_desde_euler(0.0, angulo, 0.0)   # pitch puro
            _, inc = heading_desde_cuaternion(*q)
            self.assertAlmostEqual(inc, angulo, places=9)

    def test_singularidad_de_euler_no_rompe_el_yaw(self) -> None:
        """
        pitch = 90° es la singularidad ("gimbal lock") donde `q2eul` emite
        warning y devuelve un valor con una componente forzada. Acá el atan2
        sigue devolviendo un número finito, y la INCLINACIÓN (90°) es la que
        avisa que ese heading no debe usarse.
        """
        q = _cuaternion_desde_euler(0.0, math.pi / 2.0, 0.3)
        yaw, inc = heading_desde_cuaternion(*q)
        self.assertTrue(math.isfinite(yaw))
        self.assertAlmostEqual(inc, math.pi / 2.0, places=9)
        self.assertGreater(inc, cfg.INCLINACION_MAX_RAD,
                           "esta pose debe ser rechazada por la validación")


# =============================================================================
# 5. VALIDACIÓN DEFENSIVA DE POSES
# =============================================================================

class PruebaValidacionDePoses(unittest.TestCase):

    @staticmethod
    def _fila(x: float, y: float, z: float = 0.0,
              yaw: float = 0.0, roll: float = 0.0) -> np.ndarray:
        qw, qx, qy, qz = _cuaternion_desde_euler(roll, 0.0, yaw)
        return np.array([x, y, z, qw, qx, qy, qz], dtype=np.float64)

    def test_pose_razonable_pasa(self) -> None:
        ok, motivo = pose_es_valida(self._fila(0.5, -0.5, 0.02, yaw=1.0))
        self.assertTrue(ok, motivo)

    def test_nan_se_rechaza(self) -> None:
        fila = self._fila(0.5, 0.5)
        fila[0] = math.nan
        ok, motivo = pose_es_valida(fila)
        self.assertFalse(ok)
        self.assertIn("finitos", motivo)

    def test_todo_ceros_se_rechaza(self) -> None:
        """
        Un candidato plausible para "marcador no visible": el cuaternión nulo
        tiene norma 0 y no pasa la validación, aunque la posición (0,0,0) sí
        esté dentro del rango del laboratorio.
        """
        ok, motivo = pose_es_valida(np.zeros(7, dtype=np.float64))
        self.assertFalse(ok)
        self.assertIn("cuaternión", motivo)

    def test_placeholder_de_marcador_no_trackeado_se_rechaza(self) -> None:
        """
        Lo que el servidor REAL devuelve para un marcador no trackeado,
        medido en el laboratorio el 2026-08-25: origen + cuaternión
        IDENTIDAD. Es el caso traicionero, distinto de `todo_ceros`: acá la
        norma del cuaternión es exactamente 1.0 y la posición cae dentro
        del rango, así que pasaba TODAS las validaciones. Una etapa 0
        contra un marcador invisible informaba "20/20 poses válidas" con
        veinte filas idénticas de ceros.
        """
        fila = np.array([0.0, -0.0, 0.0, 1.0, 0.0, -0.0, 0.0],
                        dtype=np.float64)
        self.assertAlmostEqual(float(np.linalg.norm(fila[3:7])), 1.0,
                               msg="si esto falla, el caso ya no es el "
                                   "cuaternión unitario que hace de trampa")
        ok, motivo = pose_es_valida(fila)
        self.assertFalse(ok)
        self.assertIn("no trackeado", motivo)

    def test_origen_con_orientacion_real_sigue_siendo_valido(self) -> None:
        """
        Contraparte: el rechazo exige origen Y cuaternión identidad a la
        vez. Un robot realmente parado en el origen, pero girado, es una
        pose legítima y no debe descartarse.
        """
        ok, motivo = pose_es_valida(self._fila(0.0, 0.0, 0.0, yaw=0.7))
        self.assertTrue(ok, motivo)

    def test_posicion_absurda_se_rechaza(self) -> None:
        """Otro candidato: milímetros interpretados como metros, o basura."""
        ok, motivo = pose_es_valida(self._fila(1500.0, 0.0))
        self.assertFalse(ok)
        self.assertIn("x=", motivo)

    def test_robot_volcado_se_rechaza(self) -> None:
        ok, motivo = pose_es_valida(self._fila(0.5, 0.5, roll=math.radians(80.0)))
        self.assertFalse(ok)
        self.assertIn("inclinación", motivo)

    def test_forma_incorrecta_se_rechaza(self) -> None:
        ok, _ = pose_es_valida(np.zeros(3, dtype=np.float64))
        self.assertFalse(ok)


# =============================================================================
# 6. TRANSFORMACIÓN DE MARCO Y CONFIGURACIÓN
# =============================================================================

class PruebaMarco(unittest.TestCase):

    def test_traslacion_por_defecto_centra_la_arena(self) -> None:
        """Con la calibración por defecto, el origen del lab cae en (1.5, 1.5)."""
        p = lab_a_env(0.0, 0.0, 0.0)
        np.testing.assert_allclose(
            p, [cfg.TRASLACION_X_M, cfg.TRASLACION_Y_M, cfg.OFFSET_HEADING_RAD],
            atol=1e-12)

    def test_rotacion_de_marco(self) -> None:
        """Comprobación de la rotación con parámetros forzados a mano."""
        rot_orig, tx, ty = (cfg.ROTACION_MARCO_RAD,
                            cfg.TRASLACION_X_M, cfg.TRASLACION_Y_M)
        try:
            cfg.ROTACION_MARCO_RAD = math.pi / 2.0
            cfg.TRASLACION_X_M = 0.0
            cfg.TRASLACION_Y_M = 0.0
            p = lab_a_env(1.0, 0.0, 0.0)
            np.testing.assert_allclose(p[:2], [0.0, 1.0], atol=1e-12)
            self.assertAlmostEqual(p[2], math.pi / 2.0, places=12)
        finally:
            cfg.ROTACION_MARCO_RAD = rot_orig
            cfg.TRASLACION_X_M, cfg.TRASLACION_Y_M = tx, ty

    def test_heading_queda_envuelto(self) -> None:
        p = lab_a_env(0.0, 0.0, 3.0 * math.pi)
        self.assertLessEqual(abs(p[2]), math.pi + 1e-12)


class PruebaOffsetDeRumboPorRobot(unittest.TestCase):
    """
    El offset de rumbo es POR ROBOT, no global.

    Describe cómo quedó montada la constelación sobre un chasis concreto y
    varía de uno a otro: en la tabla del laboratorio el robot 10 se aparta
    127° de los demás. Con un escalar único, la política le diría "andá a la
    derecha" y el robot se iría casi en dirección opuesta, con el CBF
    calculando márgenes sobre un rumbo falso.
    """

    def setUp(self) -> None:
        self._sim = cfg.SIMULADOR_ACTIVO
        cfg.SIMULADOR_ACTIVO = False        # la tabla es del hardware real

    def tearDown(self) -> None:
        cfg.SIMULADOR_ACTIVO = self._sim

    def test_cada_robot_usa_el_suyo(self) -> None:
        self.assertAlmostEqual(
            math.degrees(cfg.offset_rumbo_de_robot(1)), +93.7618, places=4)
        self.assertAlmostEqual(
            math.degrees(cfg.offset_rumbo_de_robot(10)), -33.6573, places=4)

    def test_el_robot_10_no_recibe_el_del_robot_1(self) -> None:
        """La regresión concreta: 127° de diferencia entre esos dos."""
        d = abs(math.degrees(cfg.offset_rumbo_de_robot(1)
                             - cfg.offset_rumbo_de_robot(10)))
        self.assertGreater(d, 120.0)

    def test_robot_sin_entrada_cae_al_escalar(self) -> None:
        """Un robot fuera de la tabla usa el global, que es lo correcto
        para una sesión de UN robot."""
        previo = cfg.OFFSET_HEADING_RAD
        try:
            cfg.OFFSET_HEADING_RAD = 0.5
            self.assertAlmostEqual(cfg.offset_rumbo_de_robot(99), 0.5)
        finally:
            cfg.OFFSET_HEADING_RAD = previo

    def test_no_aplica_en_simulador(self) -> None:
        """Los robots simulados tienen la constelación alineada: offset 0.

        Sin esto, la prueba de lazo cerrado ve al robot avanzar pero
        proyectado sobre un rumbo girado 93.76°, y el avance sale negativo.
        """
        cfg.SIMULADOR_ACTIVO = True
        previo = cfg.OFFSET_HEADING_RAD
        try:
            cfg.OFFSET_HEADING_RAD = 0.0
            self.assertAlmostEqual(cfg.offset_rumbo_de_robot(1), 0.0)
            self.assertAlmostEqual(cfg.offset_rumbo_de_robot(10), 0.0)
        finally:
            cfg.OFFSET_HEADING_RAD = previo

    def test_lab_a_env_respeta_el_offset_que_se_le_pasa(self) -> None:
        sin_offset = lab_a_env(0.0, 0.0, 0.0, 0.0)
        con_offset = lab_a_env(0.0, 0.0, 0.0, math.pi / 2.0)
        self.assertAlmostEqual(sin_offset[2], 0.0, places=12)
        self.assertAlmostEqual(con_offset[2], math.pi / 2.0, places=12)


class PruebaConfiguracion(unittest.TestCase):

    def test_ip_de_robot(self) -> None:
        self.assertEqual(cfg.ip_de_robot(0), "192.168.50.100")
        self.assertEqual(cfg.ip_de_robot(9), "192.168.50.109")
        self.assertEqual(cfg.ip_de_robot(10), "192.168.50.110")
        self.assertEqual(cfg.ip_de_robot(19), "192.168.50.119")
        with self.assertRaises(ValueError):
            cfg.ip_de_robot(20)
        with self.assertRaises(ValueError):
            cfg.ip_de_robot(-1)

    def test_todas_las_ips_son_distintas(self) -> None:
        ips = {cfg.ip_de_robot(i) for i in range(20)}
        self.assertEqual(len(ips), 20)

    def test_mapeo_sin_duplicados(self) -> None:
        marcadores = [a.id_marcador for a in cfg.MAPEO_AGENTES.values()]
        robots     = [a.id_robot    for a in cfg.MAPEO_AGENTES.values()]
        self.assertEqual(len(set(marcadores)), len(marcadores),
                         "dos agentes comparten marcador")
        self.assertEqual(len(set(robots)), len(robots),
                         "dos agentes comparten robot")
        self.assertEqual(sorted(cfg.MAPEO_AGENTES), list(range(len(robots))),
                         "los índices de agente deben ser 0..N-1 sin huecos")

    def test_resumen_marca_lo_no_verificado(self) -> None:
        texto = "\n".join(cfg.resumen_calibracion())
        self.assertIn("NO VERIFICADO", texto)

    def test_el_offset_del_robot_8_es_el_medido_y_se_declara(self) -> None:
        """
        2026-09-22: el 8 usa +95.01° medido (tabla +89.99°) de UNA corrida.
        Tiene que quedar a la vista en cada arranque, no enterrado en config.
        """
        simulador = cfg.SIMULADOR_ACTIVO
        cfg.SIMULADOR_ACTIVO = False
        try:
            self.assertAlmostEqual(
                math.degrees(cfg.offset_rumbo_de_robot(8)), 95.01, places=2)
            self.assertIn(8, cfg.OFFSETS_RUMBO_MEDIDOS)
            self.assertIn("UNA sola corrida", cfg.origen_offset_rumbo(8))
            self.assertIn("tabla", cfg.origen_offset_rumbo(6))
            if any(a.id_robot == 8 for a in cfg.MAPEO_AGENTES.values()):
                texto = "\n".join(cfg.resumen_calibracion())
                self.assertIn("robot 8:  +95.01°", texto)
                self.assertIn("UNA sola corrida", texto)
        finally:
            cfg.SIMULADOR_ACTIVO = simulador


# =============================================================================
# 7. WEBOTS INVIERTE, EL ROBOTAT NO — LA FRONTERA QUE NADIE DEBE "UNIFICAR"
# =============================================================================

class PruebaSignosDeMotorNoCruzanLaFrontera(unittest.TestCase):
    """
    `SIGNO_MOTOR_1 = SIGNO_MOTOR_2 = -1` NO es un parche empírico: es la
    convención del modelo de Webots. El controlador de referencia del
    laboratorio (`pololu3pi_controller.m`, líneas 194-195) hace

        wb_motor_set_velocity(left_motor,  -rpm2rads(velsat(v_left)));
        wb_motor_set_velocity(right_motor, -rpm2rads(velsat(v_right)));

    con el comentario textual: *"La inversión de signo y la conversión a
    rad/s son específicas de la simulación (en el robot real se envían las
    rpm directamente)"*.

    Consecuencia operativa: **esos signos no deben llegar al cliente del
    Robotat**. Si alguien "unifica" los dos caminos de conversión, los cinco
    robots del laboratorio andarían en reversa — y como la política sí
    reacciona a las poses, el enjambre haría algo coherente pero equivocado,
    que es el modo de falla más caro de diagnosticar.

    Estas pruebas fijan la distinción en las dos direcciones: por
    comportamiento y por inspección del código fuente.
    """

    def test_webots_declara_la_inversion(self) -> None:
        import protocolo
        self.assertEqual(protocolo.SIGNO_MOTOR_1, -1)
        self.assertEqual(protocolo.SIGNO_MOTOR_2, -1)

    def test_el_robotat_no_invierte(self) -> None:
        """Avance puro ⇒ ambas ruedas POSITIVAS en el cable del Robotat."""
        rpm_izq, rpm_der, _ = accion_a_rpm(0.20, 0.0, R_M, L_M)
        self.assertGreater(rpm_izq, 0.0)
        self.assertGreater(rpm_der, 0.0)
        leido_izq, leido_der = decodificar_velocidades_rueda(
            codificar_velocidades_rueda(rpm_izq, rpm_der)
        )
        self.assertGreater(leido_izq, 0.0,
                           "si el cliente aplicara SIGNO_MOTOR, el robot real "
                           "andaría en reversa")
        self.assertGreater(leido_der, 0.0)

    def test_las_dos_convenciones_son_opuestas(self) -> None:
        """
        Deja explícito que aplicar el signo de Webots al Robotat invierte el
        sentido de marcha, para que la prueba anterior no parezca arbitraria.
        """
        import protocolo
        rpm_izq, _rpm_der, _ = accion_a_rpm(0.20, 0.0, R_M, L_M)
        con_signo_webots = protocolo.SIGNO_MOTOR_2 * rpm_izq
        self.assertLess(con_signo_webots, 0.0)
        self.assertAlmostEqual(con_signo_webots, -rpm_izq, places=9)

    def test_el_cliente_del_robotat_no_menciona_los_signos(self) -> None:
        """
        Guardia estática contra la "unificación": si alguien importa o aplica
        SIGNO_MOTOR_* en el camino del Robotat, esta prueba falla aunque el
        error no se manifieste en ninguna otra.
        """
        import inspect

        import adaptadores_robotat
        import protocolo_robotat

        for modulo in (protocolo_robotat, adaptadores_robotat):
            fuente = inspect.getsource(modulo)
            # Se ignoran las líneas de comentario: el módulo PUEDE explicar
            # por qué no los usa, pero no debe referenciarlos en código.
            codigo = "\n".join(
                l for l in fuente.splitlines()
                if not l.lstrip().startswith("#")
            )
            self.assertNotIn(
                "SIGNO_MOTOR", codigo,
                f"{modulo.__name__} referencia SIGNO_MOTOR: los signos de "
                f"motor son específicos de Webots y no van al robot real "
                f"(ver pololu3pi_controller.m:194-195)",
            )


class PruebaHeadingDesdeCompass(unittest.TestCase):
    """
    `compass_a_heading` debe dar lo MISMO que el controlador del laboratorio,
    que hace (líneas 115-116):

        bearing   = atan2d(mag(2), mag(1)) - 90
        theta_deg = atan2d(sind(-bearing), cosd(-bearing))

    OJO con la línea 116: no es sólo envolver, es envolver **−bearing**. La
    negación es la que hace que coincida con nuestra
    `atan2(mag[0], mag[1])`; sin ella las dos fórmulas son OPUESTAS. Vale la
    identidad atan2(x, y) = π/2 − atan2(y, x).

    El Compass está montado igual en los dos mundos
    (`rotation 0 0 1 1.5707996938995747`), así que la comparación es directa.
    """

    @staticmethod
    def _lab(mag) -> float:
        bearing = math.degrees(math.atan2(mag[1], mag[0])) - 90.0
        th = math.radians(-bearing)
        return math.atan2(math.sin(th), math.cos(th))

    def test_coincide_con_el_controlador_del_lab(self) -> None:
        from protocolo import compass_a_heading
        for a in np.linspace(-math.pi, math.pi, 361):
            mag = [math.cos(a), math.sin(a), 0.3]
            d = self._lab(mag) - compass_a_heading(mag)
            self.assertAlmostEqual(
                math.atan2(math.sin(d), math.cos(d)), 0.0, places=12,
                msg=f"ángulo {a:.4f}",
            )

    def test_sin_la_negacion_darian_opuestas(self) -> None:
        """Fija por qué la línea 116 no es cosmética."""
        from protocolo import compass_a_heading
        mag = [math.cos(0.7), math.sin(0.7), 0.0]
        solo_bearing = math.radians(
            math.degrees(math.atan2(mag[1], mag[0])) - 90.0
        )
        self.assertAlmostEqual(solo_bearing, -compass_a_heading(mag), places=12)


# =============================================================================
# 8. DESCARTE DE BUFFER PENDIENTE — hallazgo de laboratorio 2026-08-21
# =============================================================================
# `robotat_get_pose.m` hace `read(tcp_obj)` como primera línea, ANTES de
# escribir la petición. En el Robotat real esto se reprodujo: la primera
# consulta tras conectar al robot 1 daba "respuesta no parseable" dos veces
# seguidas (200-203 B), y las 19 siguientes de cada corrida funcionaban.
# `descartar_buffer_pendiente` es la réplica de ese vaciado.

class PruebaDescartarBufferPendiente(unittest.TestCase):
    """
    Usa `socket.socketpair()`: dos sockets conectados directo, sin red, para
    controlar exactamente qué bytes hay pendientes en cada momento.
    """

    def setUp(self) -> None:
        self.a, self.b = socket.socketpair()
        self.a.settimeout(1.0)

    def tearDown(self) -> None:
        self.a.close()
        self.b.close()

    def test_descarta_lo_pendiente_y_cuenta_los_bytes(self) -> None:
        carga = b"basura del servidor, empujada sin que se pida"
        self.b.sendall(carga)
        time.sleep(0.05)          # dar tiempo a que el kernel la entregue
        n = descartar_buffer_pendiente(self.a)
        self.assertEqual(n, len(carga))

    def test_buffer_vacio_no_bloquea(self) -> None:
        """
        El caso normal, en cada tick del lazo a 100 Hz: nada pendiente, y
        NO debe haber una espera de bloqueo — usa `select` con timeout 0.
        """
        t0 = time.perf_counter()
        n = descartar_buffer_pendiente(self.a)
        transcurrido = time.perf_counter() - t0
        self.assertEqual(n, 0)
        self.assertLess(transcurrido, 0.05,
                        "no debe bloquear cuando no hay nada pendiente")

    def test_segunda_llamada_no_encuentra_nada(self) -> None:
        self.b.sendall(b"x" * 10)
        time.sleep(0.05)
        primero = descartar_buffer_pendiente(self.a)
        segundo = descartar_buffer_pendiente(self.a)
        self.assertEqual(primero, 10)
        self.assertEqual(segundo, 0)

    def test_reproduce_el_patron_del_laboratorio(self) -> None:
        """
        El caso exacto que se vio en el Robotat: basura pegada delante de
        una respuesta real en la MISMA conexión. Sin descartar, esos bytes
        quedarían al frente de lo próximo que se lea y romperían el parseo
        de JSON (basura + JSON válido no es JSON válido). Con el descarte,
        la respuesta real llega intacta y aislada.
        """
        basura = b'{"ultimo_frame_en_cache": true, "stale": 1}'
        self.b.sendall(basura)
        time.sleep(0.05)

        n = descartar_buffer_pendiente(self.a)
        self.assertEqual(n, len(basura))

        respuesta_real = b"[1.0, 2.0, 3.0]"
        self.b.sendall(respuesta_real)
        time.sleep(0.05)
        recibido = self.a.recv(256)
        self.assertEqual(recibido, respuesta_real,
                         "tras el descarte, sólo debe llegar la respuesta "
                         "real, sin la basura pegada adelante")

    def test_sin_descarte_la_basura_rompe_el_parseo(self) -> None:
        """
        Guardia negativa: confirma que el problema es real si NO se
        descarta, para que quede claro qué evita el fix.
        """
        basura = b'{"stale": true}'
        respuesta_real = b"[1.0, 2.0, 3.0]"
        self.b.sendall(basura)
        self.b.sendall(respuesta_real)
        time.sleep(0.05)
        # SIN llamar a descartar_buffer_pendiente:
        recibido = self.a.recv(256)
        self.assertEqual(recibido, basura + respuesta_real)
        self.assertNotEqual(recibido, respuesta_real,
                            "sin descarte, la basura viaja pegada adelante")



class PruebaReconexionDeRuedas(unittest.TestCase):
    """
    ⚠ REGRESIÓN (2026-09-11). El robot 3 cerró su socket (WinError 10054)
    en una pausa y el canal nunca lo reabrió: cuatro episodios seguidos sin
    que el robot recibiera una orden (si aceptaba conexiones nuevas nunca se
    verificó). Se prueba contra un servidor TCP local de verdad.
    """

    def setUp(self) -> None:
        import threading
        import adaptadores_robotat as ad
        self.ad = ad
        self.servidor = socket.socket()
        self.servidor.bind(("127.0.0.1", 0))
        self.servidor.listen(4)
        self.puerto = self.servidor.getsockname()[1]
        self.recibido = bytearray()
        self.conexiones = 0
        self._parar = threading.Event()

        def atender() -> None:
            self.servidor.settimeout(0.1)
            while not self._parar.is_set():
                try:
                    c, _ = self.servidor.accept()
                except OSError:
                    continue
                self.conexiones += 1
                c.settimeout(0.1)
                while not self._parar.is_set():
                    try:
                        dato = c.recv(64)
                    except OSError:
                        continue
                    if not dato:
                        break
                    self.recibido.extend(dato)
                c.close()

        self.hilo = threading.Thread(target=atender, daemon=True)
        self.hilo.start()
        self._endpoint = cfg.endpoint_robot
        self._intervalo = ad.RECONEXION_INTERVALO_S
        cfg.endpoint_robot = lambda _id: ("127.0.0.1", self.puerto)
        ad.RECONEXION_INTERVALO_S = 0.0

    def tearDown(self) -> None:
        cfg.endpoint_robot = self._endpoint
        self.ad.RECONEXION_INTERVALO_S = self._intervalo
        self._parar.set()
        self.hilo.join(timeout=2.0)
        self.servidor.close()

    def _esperar(self, cond, plazo: float = 2.0) -> bool:
        import time as _t
        fin = _t.perf_counter() + plazo
        while _t.perf_counter() < fin:
            if cond():
                return True
            _t.sleep(0.01)
        return cond()

    def _canal_con_socket_roto(self):
        canal = self.ad.CanalActuacionRobotat(1)
        canal.conectar()
        self.assertTrue(self._esperar(lambda: self.conexiones == 1))

        class SocketMuerto:
            def sendall(self, _b):
                raise ConnectionResetError(10054, "cerrado por el robot")

            def close(self):
                pass

        canal._socks[0].close()
        canal._socks[0] = SocketMuerto()
        return canal

    def test_un_socket_caido_se_reabre_y_la_orden_llega(self) -> None:
        canal = self._canal_con_socket_roto()
        with contextlib.redirect_stdout(io.StringIO()):
            ok = canal._enviar_crudo(0, 30.0, 30.0)
        self.assertTrue(ok, "tras reconectar, la orden tiene que salir")
        self.assertEqual(canal.reconexiones.get(0), 1)
        self.assertTrue(self._esperar(lambda: self.conexiones == 2))
        self.assertTrue(self._esperar(lambda: len(self.recibido) > 0))
        with contextlib.redirect_stdout(io.StringIO()):
            canal.cerrar()

    def test_si_el_robot_no_contesta_se_sigue_intentando(self) -> None:
        canal = self._canal_con_socket_roto()
        self._parar.set()
        self.hilo.join(timeout=2.0)
        self.servidor.close()          # robot apagado: nadie escucha
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(canal._enviar_crudo(0, 30.0, 30.0))
            self.assertFalse(canal._enviar_crudo(0, 30.0, 30.0))
        self.assertIn(0, canal._caidos, "tiene que quedar pendiente de reabrir")
        self.assertNotIn(0, canal.reconexiones)

    def test_un_canal_cerrado_a_proposito_no_revive(self) -> None:
        canal = self._canal_con_socket_roto()
        with contextlib.redirect_stdout(io.StringIO()):
            canal._enviar_crudo(0, 0.0, 0.0)   # reconecta
            canal.cerrar()
            antes = self.conexiones
            self.assertFalse(canal._enviar_crudo(0, 30.0, 30.0))
        self.assertEqual(self.conexiones, antes,
                         "cerrar() es definitivo: no se reabre solo")

    def test_la_caida_queda_registrada_con_su_demora(self) -> None:
        """Reabrir al primer intento = el robot nunca dejó la red."""
        canal = self._canal_con_socket_roto()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertTrue(canal._enviar_crudo(0, 0.0, 0.0))
        self.assertEqual(len(canal.eventos_enlace), 1)
        ev = canal.eventos_enlace[0]
        self.assertIn("10054", ev["error"])
        self.assertEqual(ev["intentos"], [])
        self.assertIsNotNone(ev["demora_s"])
        self.assertIn("intentos fallidos: ninguno", buf.getvalue())
        self.assertTrue(any("reabierto a los" in l for l in canal.resumen()))
        with contextlib.redirect_stdout(io.StringIO()):
            canal.cerrar()

    def test_los_intentos_fallidos_quedan_en_el_mismo_evento(self) -> None:
        canal = self._canal_con_socket_roto()
        self._parar.set()
        self.hilo.join(timeout=2.0)
        self.servidor.close()          # robot fuera: nadie escucha
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(canal._enviar_crudo(0, 0.0, 0.0))
            self.assertFalse(canal._enviar_crudo(0, 0.0, 0.0))
        ev = canal.eventos_enlace[0]
        clases = [c for _t, c in ev["intentos"]]
        self.assertEqual(len(clases), 2)
        # Windows reporta el rechazo como timeout con 0.5 s (ver _reconectar)
        self.assertTrue(set(clases) <= {"sin respuesta", "rechazada"}, clases)
        self.assertIsNone(ev["demora_s"])
        self.assertTrue(any("NUNCA se reabrió" in l for l in canal.resumen()))

        # Vuelve el robot (otro puerto, mismo endpoint): se cierra ESE evento.
        nuevo = socket.socket()
        nuevo.bind(("127.0.0.1", 0))
        nuevo.listen(1)
        self.puerto = nuevo.getsockname()[1]
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertTrue(canal._enviar_crudo(0, 0.0, 0.0))
            self.assertEqual(len(canal.eventos_enlace), 1)
            self.assertIsNotNone(ev["demora_s"])
            self.assertIn("RECONECTADO", buf.getvalue())
            self.assertIn(f"2 {clases[0]}" if len(set(clases)) == 1
                          else clases[0], buf.getvalue())
            with contextlib.redirect_stdout(io.StringIO()):
                canal.cerrar()
        finally:
            nuevo.close()

    def test_reintentar_enlaces_dice_cuales_siguen_caidos(self) -> None:
        """
        2026-09-24: la sesión arrancó 5 episodios con el robot 5 fuera de la
        red. El chequeo previo necesita saber qué enlaces siguen caídos.
        """
        canal = self._canal_con_socket_roto()
        self._parar.set()
        self.hilo.join(timeout=2.0)
        self.servidor.close()                          # robot fuera de la red
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(canal._enviar_crudo(0, 0.0, 0.0))
        self.assertEqual(canal.enlaces_caidos(), [0])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canal.reintentar_enlaces(), [0])

        nuevo = socket.socket()                        # vuelve el robot
        nuevo.bind(("127.0.0.1", 0))
        nuevo.listen(1)
        self.puerto = nuevo.getsockname()[1]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(canal.reintentar_enlaces(), [])
            self.assertEqual(canal.enlaces_caidos(), [])
            with contextlib.redirect_stdout(io.StringIO()):
                canal.cerrar()
        finally:
            nuevo.close()

    def test_conectar_nombra_a_todos_los_que_no_responden(self) -> None:
        """
        2026-09-22: el robot 2 estaba fuera de la red y la sesión murió con un
        traceback que sólo nombraba al primero que falló. Ahora prueba todos,
        los nombra y no deja sockets abiertos.
        """
        muerto = socket.socket()
        muerto.bind(("127.0.0.1", 0))
        puerto_muerto = muerto.getsockname()[1]
        muerto.close()                            # nadie escucha ahí
        ids = [cfg.MAPEO_AGENTES[i].id_robot for i in range(2)]
        puertos = {ids[0]: self.puerto, ids[1]: puerto_muerto}
        cfg.endpoint_robot = lambda r: ("127.0.0.1", puertos[r])
        canal = self.ad.CanalActuacionRobotat(2)
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(self.ad.RobotsInalcanzables) as ctx:
                canal.conectar()
        self.assertEqual(len(ctx.exception.fallidos), 1)
        self.assertIn(f"robot {ids[1]}", str(ctx.exception))
        self.assertNotIn(f"robot {ids[0]} @", str(ctx.exception))
        self.assertEqual(canal._socks, {}, "los que sí conectaron se cierran")
        self.assertIsInstance(ctx.exception, OSError)   # compatibilidad

    def test_dos_hilos_mandando_a_la_vez_no_mezclan_comandos(self) -> None:
        """
        2026-09-22: con la colocación autónoma, el latido de la guía (otro
        hilo, `detener_todo`) puede solaparse con los envíos de marcha. Cada
        comando CBOR tiene que llegar entero: 11 bytes que decodifican a una
        de las dos órdenes, nunca a una mezcla.
        """
        import threading as _th
        from protocolo_robotat import decodificar_velocidades_rueda
        canal = self.ad.CanalActuacionRobotat(1)
        with contextlib.redirect_stdout(io.StringIO()):
            canal.conectar()
        n = 300

        def mandar(rpm: tuple) -> None:
            for _ in range(n):
                canal._enviar_crudo(0, *rpm)

        hilos = [_th.Thread(target=mandar, args=((11.0, 11.0),)),
                 _th.Thread(target=mandar, args=((22.0, -22.0),))]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=10.0)
        self.assertTrue(self._esperar(lambda: len(self.recibido) >= 2 * n * 11,
                                      plazo=5.0))
        datos = bytes(self.recibido[:2 * n * 11])
        ordenes = {decodificar_velocidades_rueda(datos[k:k + 11])
                   for k in range(0, len(datos), 11)}
        self.assertEqual(ordenes, {(11.0, 11.0), (22.0, -22.0)})
        with contextlib.redirect_stdout(io.StringIO()):
            canal.cerrar()

    def test_clasificacion_de_fallos(self) -> None:
        self.assertEqual(self.ad._clase_fallo_conexion(TimeoutError()),
                         "sin respuesta")
        self.assertEqual(self.ad._clase_fallo_conexion(socket.timeout()),
                         "sin respuesta")
        self.assertEqual(self.ad._clase_fallo_conexion(
            ConnectionRefusedError(10061, "x")), "rechazada")
        self.assertIn("10065", self.ad._clase_fallo_conexion(
            OSError(10065, "host inalcanzable")))


class PruebaRelojMonotonico(unittest.TestCase):
    """
    ⚠ REGRESIÓN (2026-09-11). `reiniciar_reloj()` volvía `_k` a cero, y `_k`
    es el tick con que la fuente sella las poses: desde el segundo episodio
    el coordinador veía cada pose con miles de ticks de antigüedad.
    """

    def _entorno(self):
        from adaptadores_robotat import EntornoEjecucionRobotat

        class FuenteStub:
            conexion_caida = False
            reloj = None

            def fijar_reloj(self, f):
                FuenteStub.reloj = f

            def fijar_intervalo_consulta(self, _ms):
                pass

        e = EntornoEjecucionRobotat(FuenteStub(), object(), 10)
        return e, FuenteStub

    def test_reanclar_no_reinicia_el_tick_de_las_poses(self) -> None:
        e, fuente = self._entorno()
        e.avanzar(5)
        antes = fuente.reloj()
        e.reiniciar_reloj()
        e.avanzar(1)
        self.assertEqual(fuente.reloj(), antes + 1,
                         "el tick que sella las poses tiene que seguir")

    def test_reanclar_sigue_devolviendo_el_ritmo(self) -> None:
        e, _ = self._entorno()
        e.avanzar(2)
        time.sleep(0.2)                  # una "pausa de reposicionamiento"
        e.reiniciar_reloj()
        t0 = time.perf_counter()
        e.avanzar(5)
        transcurrido = time.perf_counter() - t0
        self.assertGreater(transcurrido, 0.035,
                           "tras re-anclar tiene que volver a dormir")

if __name__ == "__main__":
    print("=" * 70)
    print("PRUEBAS DEL PUENTE AL ROBOTAT (sin hardware)")
    print("=" * 70)
    for linea in cfg.resumen_calibracion():
        print(linea)
    print("=" * 70)
    unittest.main(verbosity=2)
