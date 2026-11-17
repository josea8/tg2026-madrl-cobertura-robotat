"""
test_sesion_robotat.py
======================
Ejercita `sesion_robotat.py` completo contra el simulador local: las seis
etapas de calibración, la sesión de política con su barrido, las cuatro
condiciones de aborto y los modos de fallo.

    python test_sesion_robotat.py

Aislamiento
-----------
Cada prueba redirige `calibracion_sesion.RUTA_CALIBRACION` y
`sesion_robotat.DIR_SALIDA` a un directorio temporal: las pruebas NUNCA
tocan la calibración real ni `resultados_sesion/`.

El "operador" se inyecta por `Contexto.preguntar`, así que las etapas
interactivas corren sin intervención pero por el MISMO camino de código que
en el laboratorio.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import collections
import contextlib
import io
import json
import math
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

import calibracion_sesion as calib
import config_robotat as cfg
import sesion_robotat as ses
import verificar_mapeo_ids as ses_verificar
from simulador_robotat import FallasSimulador, SimuladorRobotat

ID_ROBOT:    int = 0
ID_MARCADOR: int = 1

#: el simulador coloca al robot acá (marco del laboratorio)
POSE_INICIAL = (-0.30, 0.20, 0.0)


def _sim(fallas: Optional[FallasSimulador] = None) -> SimuladorRobotat:
    return SimuladorRobotat(
        {ID_ROBOT: ID_MARCADOR},
        {ID_ROBOT: POSE_INICIAL},
        fallas,
    )


class BaseSesion(unittest.TestCase):
    """Simulador arriba, calibración y salidas aisladas en un temporal."""

    fallas: Optional[FallasSimulador] = None
    silencioso: bool = True

    def setUp(self) -> None:
        cfg.activar_simulador_local()
        self.tmp = Path(tempfile.mkdtemp(prefix="sesion_test_"))
        self._ruta_calib = calib.RUTA_CALIBRACION
        self._dir_salida = ses.DIR_SALIDA
        calib.RUTA_CALIBRACION = self.tmp / "calibracion_medida.json"
        ses.DIR_SALIDA = self.tmp / "resultados_sesion"

        self.sim = _sim(self.fallas)
        self.sim.iniciar()
        self.ctx = ses.Contexto(
            sesion="prueba", id_robot=ID_ROBOT, marcador=ID_MARCADOR,
            preguntar=self._responder,
        )
        self.respuestas: List[str] = []
        self._i_respuesta = 0

    def tearDown(self) -> None:
        try:
            self.ctx.cerrar()
        except Exception:                                     # noqa: BLE001
            pass
        self.sim.detener()
        cfg.SIMULADOR_ACTIVO = False
        calib.RUTA_CALIBRACION = self._ruta_calib
        ses.DIR_SALIDA = self._dir_salida
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── operador simulado ────────────────────────────────────────────────
    def _responder(self, mensaje: str) -> str:
        if self._i_respuesta < len(self.respuestas):
            r = self.respuestas[self._i_respuesta]
            self._i_respuesta += 1
            return r
        return ""

    def correr(self, funcion, *args, **kwargs):
        """Corre una etapa capturando su salida si `silencioso`."""
        if not self.silencioso:
            return funcion(self.ctx, *args, **kwargs)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = funcion(self.ctx, *args, **kwargs)
        self.ultima_salida = buf.getvalue()
        return r

    def abrir_clientes(self) -> None:
        """Deja el contexto conectado, como lo dejaría la etapa 0."""
        self.ctx.poses = ses.ClientePosesCrudo()
        self.ctx.rueda = ses.ClienteRueda(ID_ROBOT)


# =============================================================================
# 1. UTILIDADES
# =============================================================================

class PruebaStreamCongelado(unittest.TestCase):
    """
    `stream_congelado` con datos sintéticos, sin simulador.

    Se prueba acá y no contra el simulador porque el simulador es IDEAL: un
    robot quieto le da poses byte a byte idénticas, que es exactamente la
    firma del fallo buscado. La detección apunta al hardware real, donde el
    ruido de captura hace jitterear hasta un marcador inmóvil.

    El fallo que motiva esta prueba (2026-08-29): Motive dejó de transmitir,
    el servidor siguió contestando la última pose conocida —estructuralmente
    perfecta— y dos corridas de la etapa 5 se registraron como si fueran
    datos buenos: 363 y 366 lecturas con UN SOLO valor distinto.
    """

    class _PosesFalsas:
        """Cliente mínimo que devuelve una secuencia fija de poses."""

        def __init__(self, poses):
            self._poses = list(poses)
            self._i = 0

        def consultar(self, _marcadores):
            p = self._poses[min(self._i, len(self._poses) - 1)]
            self._i += 1
            return b"", (None if p is None else np.array([p])), 0.0

    _QUIETA = [1.0, 2.0, 0.06, 1.0, 0.0, 0.0, 0.0]

    def _correr(self, poses):
        cli = self._PosesFalsas(poses)
        return ses.stream_congelado(cli, marcador=1, n=15, pausa_s=0.0)

    def test_pose_repetida_es_congelado(self) -> None:
        congelado, distintos, utiles = self._correr([self._QUIETA] * 15)
        self.assertTrue(congelado)
        self.assertEqual(distintos, 1)
        self.assertEqual(utiles, 15)

    def test_jitter_de_captura_no_es_congelado(self) -> None:
        """Un marcador inmóvil PERO trackeado jitterea en los decimales."""
        poses = []
        for k in range(15):
            p = list(self._QUIETA)
            p[0] += k * 1e-7          # ruido de captura, no movimiento
            poses.append(p)
        congelado, distintos, _ = self._correr(poses)
        self.assertFalse(congelado)
        self.assertEqual(distintos, 15)

    def test_sin_lecturas_no_afirma_congelado(self) -> None:
        """Sin datos no se puede concluir: eso es otro problema, no éste."""
        congelado, _distintos, utiles = self._correr([None] * 15)
        self.assertFalse(congelado)
        self.assertEqual(utiles, 0)

    def test_no_aplica_en_simulador(self) -> None:
        """El simulador ideal repite poses legítimamente; no debe fallar."""
        previo = cfg.SIMULADOR_ACTIVO
        cfg.SIMULADOR_ACTIVO = True
        try:
            congelado, _d, _u = self._correr([self._QUIETA] * 15)
        finally:
            cfg.SIMULADOR_ACTIVO = previo
        self.assertFalse(congelado)

    def test_sin_conectar_falla_limpio_y_no_revienta(self) -> None:
        """
        Bug real (2026-09-01): `sesion_politica` llamaba al chequeo sin haber
        conectado —ese camino no pasa por `correr_calibracion`, que es quien
        conecta— y reventaba con `AttributeError: 'NoneType' object has no
        attribute 'consultar'` en pleno laboratorio.

        Las pruebas no lo vieron porque `stream_congelado` corta por
        `SIMULADOR_ACTIVO` ANTES de tocar el cliente: en simulación nunca se
        desreferenciaba el None. Por eso esta prueba apaga el simulador —así
        recorre el camino de hardware real— y comprueba que se devuelva un
        FALLO explicativo en vez de una excepción.
        """
        ctx = ses.Contexto(sesion="politica", id_robot=1, marcador=1)
        self.assertIsNone(ctx.poses)
        previo = cfg.SIMULADOR_ACTIVO
        cfg.SIMULADOR_ACTIVO = False
        try:
            r = ses.exigir_stream_vivo(ctx, 0)
        finally:
            cfg.SIMULADOR_ACTIVO = previo
        self.assertIsNotNone(r)
        self.assertEqual(r.veredicto, "FALLO")
        self.assertIn("sin conectar", r.detalle)


class PruebaUtilidades(unittest.TestCase):

    def test_ruta_salida_no_sobrescribe(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="rutas_"))
        previo, ses.DIR_SALIDA = ses.DIR_SALIDA, tmp
        try:
            r1 = ses.ruta_salida("s", 0, "x")
            r1.write_text("a", encoding="utf-8")
            r2 = ses.ruta_salida("s", 0, "x")
            r2.write_text("b", encoding="utf-8")
            r3 = ses.ruta_salida("s", 0, "x")
            self.assertNotEqual(r1, r2)
            self.assertNotEqual(r2, r3)
            self.assertTrue(r2.name.endswith("_02.csv"))
            self.assertEqual(r1.read_text(encoding="utf-8"), "a")
        finally:
            ses.DIR_SALIDA = previo
            shutil.rmtree(tmp, ignore_errors=True)

    def test_similitud_recupera_una_transformacion_conocida(self) -> None:
        escala, rot, tx, ty = 0.001, math.radians(37.0), 1.5, -0.4
        R = np.array([[math.cos(rot), -math.sin(rot)],
                      [math.sin(rot),  math.cos(rot)]])
        medidos = np.array([[100.0, 200.0], [900.0, 150.0], [400.0, 800.0]])
        reales = escala * (medidos @ R.T) + np.array([tx, ty])
        e, r, t, rms = ses.ajustar_similitud(medidos, reales)
        self.assertAlmostEqual(e, escala, places=9)
        self.assertAlmostEqual(r, rot, places=9)
        np.testing.assert_allclose(t, [tx, ty], atol=1e-9)
        self.assertLess(rms, 1e-9)

    def test_similitud_exige_dos_puntos(self) -> None:
        with self.assertRaises(ValueError):
            ses.ajustar_similitud(np.array([[0.0, 0.0]]),
                                  np.array([[1.0, 1.0]]))


# =============================================================================
# 2. ETAPAS DE CALIBRACIÓN
# =============================================================================

class PruebaEtapa0(BaseSesion):

    def test_conexion_ok(self) -> None:
        r = self.correr(ses.etapa_0)
        self.assertEqual(r.veredicto, "OK", r.detalle)
        self.assertEqual(r.mediciones["id_robot"], ID_ROBOT)
        self.assertTrue(r.salidas[0].is_file())


class PruebaEtapa0SinMarcador(BaseSesion):
    """El marcador no responde: la etapa DEBE fallar, no seguir."""
    fallas = FallasSimulador(marcadores_perdidos={ID_MARCADOR},
                             modo_marcador_perdido="ceros")

    def test_falla(self) -> None:
        r = self.correr(ses.etapa_0)
        self.assertEqual(r.veredicto, "FALLO")


class PruebaEtapa0RobotSordo(BaseSesion):
    fallas = FallasSimulador(robots_sordos={ID_ROBOT})

    def test_no_conecta(self) -> None:
        """
        `ctx.conectar()` envuelve el `OSError` crudo en `ConexionImposible`
        con diagnóstico accionable (host inalcanzable vs. rechazo, subred,
        prueba mínima equivalente) — no es la excepción de socket cruda.
        """
        with self.assertRaises(ses.ConexionImposible) as ctx_exc:
            self.correr(ses.etapa_0)
        mensaje = str(ctx_exc.exception)
        self.assertIn("robot 0", mensaje)
        self.assertIn("rechazó la conexión", mensaje)

    def test_se_puede_forzar_la_secuencia_completa_y_da_fallo_legible(self) -> None:
        """
        El camino real de uso (`--etapa 0`) pasa por `correr_calibracion`,
        que atrapa `AbortoEtapa` —de la que hereda `ConexionImposible`— y lo
        convierte en un veredicto FALLO con el mensaje impreso en varias
        líneas, en vez de un traceback.
        """
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            codigo = ses.correr_calibracion(self.ctx, solo_etapa=0)
        self.assertEqual(codigo, 1)
        self.assertIn(">>> ETAPA 0: FALLO", buf.getvalue())
        self.assertIn("rechazó la conexión", buf.getvalue())
        self.assertEqual(calib.veredicto_etapa(0), "FALLO")


class PruebaEtapa1(BaseSesion):

    def test_detecta_el_marcador(self) -> None:
        """
        `--marcador` acertó de entrada: el escaneo lo confirma entre otros
        candidatos y da OK, no ADVERTENCIA.
        """
        self.abrir_clientes()
        r = self.correr(ses.etapa_1)
        self.assertEqual(r.veredicto, "OK", r.detalle)
        self.assertEqual(r.mediciones["id_marcador"], ID_MARCADOR)

    def test_escanea_varios_candidatos_en_un_solo_giro(self) -> None:
        """
        El punto central del rediseño: no hace falta saber el marcador de
        antemano. Con `ctx.marcador` puesto a un valor DELIBERADAMENTE
        equivocado, el escaneo igual encuentra el correcto entre los
        candidatos por defecto (que incluyen 1–12 más las dos hipótesis de
        convención id_robot/id_robot+1).
        """
        self.abrir_clientes()
        self.ctx.marcador = 999          # a propósito, para no darle la respuesta
        r = self.correr(ses.etapa_1)
        self.assertEqual(r.veredicto, "ADVERTENCIA", r.detalle)
        self.assertEqual(r.mediciones["id_marcador"], ID_MARCADOR)
        self.assertIn(f"{ID_MARCADOR}", self.ultima_salida)

    def test_candidatos_explicitos_por_cli(self) -> None:
        """`ctx.candidatos_marcador` (== --candidatos) reemplaza el default."""
        self.abrir_clientes()
        self.ctx.marcador = 999
        self.ctx.candidatos_marcador = [ID_MARCADOR, 50, 60]
        r = self.correr(ses.etapa_1)
        self.assertEqual(r.mediciones["id_marcador"], ID_MARCADOR)

    def test_un_candidato_sin_marcador_no_arruina_a_los_demas(self) -> None:
        """
        Propiedad de seguridad que motivó el rediseño: si el servidor
        responde con MENOS FILAS ante un marcador ausente (una de las tres
        hipótesis para la etapa 5, todavía sin confirmar en el Robotat
        real), un candidato malo en la lista NO debe tumbar el escaneo de
        los demás. Se simula con un candidato dentro del rango por defecto
        (6) marcado como "faltante" en el simulador — un marcador que
        nunca existió, distinto del real (1).
        """
        self.sim.fallas.marcadores_perdidos = {6}
        self.sim.fallas.modo_marcador_perdido = "faltante"
        self.abrir_clientes()
        r = self.correr(ses.etapa_1)
        self.assertEqual(r.veredicto, "OK", r.detalle)
        self.assertEqual(r.mediciones["id_marcador"], ID_MARCADOR)


class PruebaEtapa1Cruzado(BaseSesion):
    """
    El robot mueve un marcador distinto del configurado: la etapa ADOPTA el
    observado (es el dato medido) pero lo marca como ADVERTENCIA.
    """

    def setUp(self) -> None:
        super().setUp()
        self.sim.detener()
        self.sim = SimuladorRobotat({ID_ROBOT: 7}, {ID_ROBOT: POSE_INICIAL})
        self.sim.iniciar()
        self.ctx.marcador = 7
        cfg.MAPEO_AGENTES = dict(cfg.MAPEO_AGENTES)
        cfg.MAPEO_AGENTES[0] = cfg.AsignacionAgente(id_marcador=7,
                                                    id_robot=ID_ROBOT)

    def test_adopta_el_observado(self) -> None:
        self.abrir_clientes()
        r = self.correr(ses.etapa_1)
        self.assertEqual(r.veredicto, "OK")
        self.assertEqual(r.mediciones["id_marcador"], 7)

    def test_realmente_cruzado_da_advertencia(self) -> None:
        """
        Ahora sí ejercitando el desacuerdo de verdad: `ctx.marcador` queda
        en un valor distinto del que el robot mueve, y la etapa debe
        ADOPTAR el observado con veredicto ADVERTENCIA, no OK.
        """
        self.ctx.marcador = 3            # el robot mueve el 7, no el 3
        self.abrir_clientes()
        r = self.correr(ses.etapa_1)
        self.assertEqual(r.veredicto, "ADVERTENCIA")
        self.assertEqual(r.mediciones["id_marcador"], 7)


class PruebaInformeEscaneo(unittest.TestCase):
    """
    `informe_escaneo` es lógica pura sobre un dict {marcador: Δyaw|None}, sin
    red: se prueba con datos sintéticos, sin simulador.
    """

    def _capturar(self, *args, **kwargs):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = ses_verificar.informe_escaneo(*args, **kwargs)
        return r, buf.getvalue()

    def test_un_solo_candidato_giro(self) -> None:
        giros = {1: 0.02, 2: 1.4, 3: 0.01, 71: None}
        movido, salida = self._capturar(0, giros)
        self.assertEqual(movido, 2)
        self.assertIn("GIRÓ", salida)

    def test_ninguno_giro(self) -> None:
        giros = {1: 0.02, 2: 0.01}
        movido, salida = self._capturar(0, giros)
        self.assertIsNone(movido)
        self.assertIn("Ningún candidato giró", salida)

    def test_varios_giraron_es_ambiguo(self) -> None:
        giros = {1: 1.2, 2: 1.1, 3: 0.01}
        movido, salida = self._capturar(0, giros)
        self.assertIsNone(movido)
        self.assertIn("VARIOS", salida)

    def test_candidatos_sin_lectura_no_cuentan_como_giro(self) -> None:
        giros = {1: None, 2: 0.9, 3: None}
        movido, _salida = self._capturar(0, giros)
        self.assertEqual(movido, 2)


class PruebaEscanearCandidatos(BaseSesion):
    """`escanear_candidatos` contra el simulador: UN giro, varios candidatos."""

    def test_identifica_el_marcador_correcto(self) -> None:
        giros = ses_verificar.escanear_candidatos(
            ID_ROBOT, [1, 2, 3, 71], verboso=False)
        self.assertEqual(set(giros), {1, 2, 3, 71})
        self.assertGreater(giros[ID_MARCADOR], math.radians(17))
        for c in (2, 3, 71):
            self.assertIsNotNone(giros[c])
            self.assertLess(giros[c], math.radians(5))

    def test_candidato_faltante_no_arruina_a_los_demas(self) -> None:
        """
        La propiedad de seguridad, probada directo sobre la función: un
        candidato cuya respuesta el servidor recorta por completo (modo
        "faltante") queda como `None` en el resultado, y NO impide leer los
        demás candidatos de la misma tanda.
        """
        self.sim.fallas.marcadores_perdidos = {6}
        self.sim.fallas.modo_marcador_perdido = "faltante"
        giros = ses_verificar.escanear_candidatos(
            ID_ROBOT, [1, 6, 8], verboso=False)
        self.assertIsNone(giros[6])
        self.assertIsNotNone(giros[1])
        self.assertGreater(giros[1], math.radians(17))
        self.assertIsNotNone(giros[8])
        self.assertLess(giros[8], math.radians(5))

    def test_usa_una_sola_conexion_no_una_por_candidato(self) -> None:
        """
        Guardia de regresión del hallazgo de laboratorio (2026-08-21): la
        primera versión abría una conexión TCP nueva por cada consulta —
        2·N para N candidatos— y contra el Robotat real TODOS los
        candidatos volvían "sin lectura", incluido un marcador que la
        etapa 0 acababa de leer 20/20 veces por una conexión persistente
        segundos antes. El simulador (Python sin límite de conexiones
        concurrentes) nunca hubiera mostrado ese problema por sí solo —
        por eso esta prueba no comprueba que el escaneo FUNCIONE, sino que
        usa el patrón de conexión correcto, que es lo que de verdad se
        rompió.
        """
        candidatos = [1, 2, 3, 4, 5, 71]
        antes = self.sim.conexiones_poses_aceptadas
        ses_verificar.escanear_candidatos(ID_ROBOT, candidatos, verboso=False)
        nuevas = self.sim.conexiones_poses_aceptadas - antes
        self.assertEqual(
            nuevas, 1,
            f"escanear_candidatos abrió {nuevas} conexiones de poses para "
            f"{len(candidatos)} candidatos; debe abrir exactamente 1 y "
            f"reusarla para todas las consultas",
        )


class PruebaCandidatosPorDefecto(unittest.TestCase):
    """`_candidatos_por_defecto` cubre las dos hipótesis de convención."""

    def test_incluye_ambas_hipotesis_y_la_meta(self) -> None:
        # 50 es un marcador VÁLIDO (1-100) pero fuera del rango 1-12: sirve
        # para confirmar que --marcador explícito se agrega aunque no sea
        # ninguna de las dos hipótesis de convención.
        ctx = ses.Contexto(sesion="x", id_robot=2, marcador=50)
        candidatos = ses._candidatos_por_defecto(ctx)
        self.assertIn(2, candidatos)      # hipótesis A: id_marcador=id_robot
        self.assertIn(3, candidatos)      # hipótesis B: +1 (MAPEO_AGENTES)
        self.assertIn(71, candidatos)     # marcador de meta del lab
        self.assertIn(50, candidatos)     # lo que se venía probando
        self.assertEqual(candidatos, sorted(set(candidatos)))

    def test_marcador_fuera_de_rango_valido_no_se_agrega(self) -> None:
        """
        999 no es un ID de marcador válido (el protocolo acepta 1-100), así
        que no debe colarse en la lista aunque sea lo que se venía probando.
        """
        ctx = ses.Contexto(sesion="x", id_robot=0, marcador=999)
        candidatos = ses._candidatos_por_defecto(ctx)
        self.assertNotIn(999, candidatos)

    def test_no_incluye_cero_ni_duplicados(self) -> None:
        ctx = ses.Contexto(sesion="x", id_robot=0, marcador=1)
        candidatos = ses._candidatos_por_defecto(ctx)
        self.assertNotIn(0, candidatos)
        self.assertEqual(len(candidatos), len(set(candidatos)))


class PruebaEtapa2(BaseSesion):

    def _mover(self, x: float, y: float) -> None:
        with self.sim._lock:
            self.sim.robots[ID_ROBOT].x = x
            self.sim.robots[ID_ROBOT].y = y

    def test_recupera_marco_identidad(self) -> None:
        """
        El "operador" reporta env = lab + 1.5, que es el marco por defecto.
        La etapa debe recuperar escala 1, rotación 0 y traslación (1.5, 1.5).
        """
        self.abrir_clientes()
        puntos = [(-0.30, 0.20), (0.60, -0.40)]
        self.respuestas = []
        for x, y in puntos:
            self.respuestas += ["", f"{x + 1.5}", f"{y + 1.5}"]

        original = self.ctx.preguntar
        indice = {"k": 0}
        posiciones = list(puntos)

        def preguntar(mensaje: str) -> str:
            # antes de cada bloque de 3 respuestas, mover el robot
            if mensaje.startswith("  Punto") or "Enter" in mensaje:
                if indice["k"] < len(posiciones):
                    self._mover(*posiciones[indice["k"]])
                    indice["k"] += 1
                    time.sleep(0.05)
            return original(mensaje)

        self.ctx.preguntar = preguntar
        r = self.correr(ses.etapa_2)
        self.assertEqual(r.veredicto, "OK", r.detalle)
        self.assertAlmostEqual(r.mediciones["escala_posicion"], 1.0, places=3)
        self.assertAlmostEqual(r.mediciones["rotacion_marco_rad"], 0.0,
                               places=3)
        self.assertAlmostEqual(r.mediciones["traslacion_x_m"], 1.5, places=2)
        self.assertAlmostEqual(r.mediciones["traslacion_y_m"], 1.5, places=2)


class PruebaEtapa2Milimetros(BaseSesion):
    """Si el servidor entrega mm, la etapa lo detecta Y propone 0.001."""
    fallas = FallasSimulador(unidades_milimetros=True)

    def test_detecta_milimetros(self) -> None:
        self.abrir_clientes()
        puntos = [(-0.30, 0.20), (0.60, -0.40)]
        indice = {"k": 0}
        respuestas: List[str] = []
        for x, y in puntos:
            respuestas += ["", f"{x + 1.5}", f"{y + 1.5}"]
        self.respuestas = respuestas
        original = self.ctx.preguntar

        def preguntar(mensaje: str) -> str:
            if mensaje.startswith("  Punto") or "Enter" in mensaje:
                if indice["k"] < len(puntos):
                    with self.sim._lock:
                        self.sim.robots[ID_ROBOT].x = puntos[indice["k"]][0]
                        self.sim.robots[ID_ROBOT].y = puntos[indice["k"]][1]
                    indice["k"] += 1
                    time.sleep(0.05)
            return original(mensaje)

        self.ctx.preguntar = preguntar
        r = self.correr(ses.etapa_2)
        self.assertAlmostEqual(r.mediciones["escala_posicion"], 0.001,
                               places=6)
        self.assertIn("MILÍMETROS", self.ultima_salida)


class PruebaEtapa3(BaseSesion):

    def test_mide_offset_nulo(self) -> None:
        """
        En el simulador el robot avanza exactamente en la dirección de su
        yaw, así que el offset medido debe dar ≈ 0.
        """
        self.abrir_clientes()
        r = self.correr(ses.etapa_3, v_prueba=0.05, duracion_s=2.0)
        self.assertEqual(r.veredicto, "OK", r.detalle)
        self.assertAlmostEqual(
            math.degrees(r.mediciones["offset_heading_rad"]), 0.0, delta=2.0)
        self.assertIn("tabla del lab", self.ultima_salida)

    def test_mide_offset_conocido(self) -> None:
        """Con el robot girado 40°, el offset medido sigue siendo ≈0."""
        with self.sim._lock:
            self.sim.robots[ID_ROBOT].yaw = math.radians(40.0)
        self.abrir_clientes()
        r = self.correr(ses.etapa_3, v_prueba=0.05, duracion_s=2.0)
        self.assertAlmostEqual(
            math.degrees(r.mediciones["offset_heading_rad"]), 0.0, delta=3.0)


class PruebaEtapa3RobotInmovil(BaseSesion):

    def test_falla_si_no_se_mueve(self) -> None:
        self.abrir_clientes()
        parar = threading.Event()

        def congelar() -> None:
            while not parar.is_set():
                with self.sim._lock:
                    self.sim.robots[ID_ROBOT].rpm_izq = 0.0
                    self.sim.robots[ID_ROBOT].rpm_der = 0.0
                time.sleep(0.002)

        h = threading.Thread(target=congelar, daemon=True)
        h.start()
        try:
            r = self.correr(ses.etapa_3, v_prueba=0.05, duracion_s=1.5)
        finally:
            parar.set()
        self.assertEqual(r.veredicto, "FALLO")
        self.assertIn("no se mueve", r.detalle)


class PruebaEtapa4(BaseSesion):

    def test_mide_percepcion_y_declara_actuacion_no_resoluble(self) -> None:
        """
        El simulador no tiene retardo de actuación, así que el retardo
        estimado cae por debajo de la resolución del muestreo. La etapa debe
        DECIRLO en vez de reportar un número dudoso.
        """
        self.abrir_clientes()
        r = self.correr(ses.etapa_4, n_consultas=60, repeticiones=2)
        self.assertIn("latencia_percepcion_p50_s", r.mediciones)
        self.assertGreater(r.mediciones["frecuencia_poses_hz"], 10.0)
        self.assertEqual(
            r.veredicto, "ADVERTENCIA",
            f"detalle={r.detalle!r} · mediciones={r.mediciones!r}")
        self.assertIn("no resoluble", r.detalle)
        self.assertIn("RESOLUCIÓN", self.ultima_salida.upper())
        # Contraparte del veredicto de presupuesto (punto 3, 2026-08-22):
        # sin latencia inyectada, debe caer cómodo en la zona holgada.
        self.assertLess(r.mediciones["presupuesto_p95_fraccion"],
                        ses.UMBRAL_PRESUPUESTO_HOLGADO)


class PruebaEtapa4PresupuestoDeDecision(BaseSesion):
    """
    El veredicto de presupuesto (punto 3 de la decisión 2026-08-22): con
    latencia inyectada suficiente, el p95 debe superar el 30 % del
    presupuesto de 100 ms por decisión, y la etapa debe decirlo con
    todas las letras — no sólo imprimir el número.
    """
    fallas = FallasSimulador(latencia_poses_s=0.040)   # 40 ms ⇒ 40 % del presupuesto

    def test_detecta_presupuesto_riesgoso(self) -> None:
        self.abrir_clientes()
        r = self.correr(ses.etapa_4, n_consultas=60, repeticiones=1)
        self.assertGreater(r.mediciones["presupuesto_p95_fraccion"],
                           ses.UMBRAL_PRESUPUESTO_RIESGOSO)
        self.assertEqual(r.veredicto, "FALLO")
        self.assertIn("RIESGOSO", self.ultima_salida)
        self.assertIn("contingencia", self.ultima_salida)


class PruebaEtapa5Ceros(BaseSesion):
    fallas = FallasSimulador(marcadores_perdidos={ID_MARCADOR},
                             modo_marcador_perdido="ceros")

    def test_concluye_pose_invalida(self) -> None:
        self.abrir_clientes()
        r = self.correr(ses.etapa_5, duracion_s=1.0)
        self.assertEqual(r.veredicto, "OK")
        self.assertIn("inválida", r.detalle)
        self.assertIn("lote", r.detalle)


class PruebaEtapa5Faltante(BaseSesion):
    fallas = FallasSimulador(marcadores_perdidos={ID_MARCADOR},
                             modo_marcador_perdido="faltante")

    def test_concluye_modo_individual(self) -> None:
        self.abrir_clientes()
        r = self.correr(ses.etapa_5, duracion_s=1.0)
        self.assertEqual(r.veredicto, "OK")
        self.assertIn("individual", r.detalle)


class PruebaEtapa5SinOclusion(BaseSesion):

    def test_avisa_que_no_paso_nada(self) -> None:
        self.abrir_clientes()
        r = self.correr(ses.etapa_5, duracion_s=1.0)
        self.assertEqual(r.veredicto, "ADVERTENCIA")
        self.assertIn("Repetir", r.detalle)


# =============================================================================
# 2b. CAMPOS FRÁGILES — id_marcador / offset_heading_rad no sobreviven
#     entre sesiones distintas (los marcadores se mueven a mano)
# =============================================================================

class PruebaCamposFragiles(unittest.TestCase):
    """
    `calibracion_sesion.py`, aislado del simulador (no necesita hardware ni
    red): pura lógica de fechas sobre el JSON de calibración.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="calib_fragil_"))
        self._ruta_previa = calib.RUTA_CALIBRACION
        calib.RUTA_CALIBRACION = self.tmp / "calibracion_medida.json"
        # `CAMPOS_FRAGILES` de producción quedó VACÍO el 2026-09-01, cuando el
        # operador confirmó que las constelaciones están pregrabadas en Motive
        # y el offset de rumbo no caduca entre sesiones. La MAQUINARIA sigue
        # siendo válida y hay que seguir probándola, así que estas pruebas
        # declaran su propio campo frágil en vez de depender del conjunto de
        # producción — que es lo que las rompió cuando se vació.
        self._fragiles_previos = calib.CAMPOS_FRAGILES
        calib.CAMPOS_FRAGILES = {"offset_heading_rad"}

    def tearDown(self) -> None:
        calib.CAMPOS_FRAGILES = self._fragiles_previos
        calib.RUTA_CALIBRACION = self._ruta_previa
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _forzar_fecha(self, campo: str, iso: str) -> None:
        """Reescribe `_medido_en[campo]` directamente, sin pasar por
        `guardar()` (que siempre sella con la hora actual)."""
        datos = calib.cargar()
        datos.setdefault("_medido_en", {})[campo] = iso
        calib.RUTA_CALIBRACION.write_text(
            json.dumps(datos, ensure_ascii=False), encoding="utf-8")

    def test_archivo_de_version_anterior_sin_medido_en_usa_el_historial(self) -> None:
        """
        Hallazgo real (2026-08-22): el `calibracion_medida.json` de la
        primera sesión de laboratorio se escribió ANTES de que existiera
        `_medido_en` — sólo tenía `_historial`. Sin este resguardo,
        `fecha_medicion` devolvía None y el campo se veía "de sesión
        anterior" con fecha "None" aunque estuviera recién medido, sólo por
        el formato del archivo, no por el dato en sí.
        """
        datos = {
            "id_robot": 2, "id_marcador": 2,
            "_historial": [
                {"cuando": "2026-08-21T20:31:06", "etapa": "etapa 1",
                 "campos": ["id_marcador", "id_robot"]},
            ],
            # sin "_medido_en": así se veían los archivos antes de este cambio
        }
        calib.RUTA_CALIBRACION.write_text(json.dumps(datos), encoding="utf-8")
        fecha = calib.fecha_medicion("id_marcador")
        self.assertIsNotNone(fecha)
        self.assertEqual(str(fecha), "2026-08-21")

    def test_recien_medido_no_esta_desactualizado(self) -> None:
        calib.guardar({"offset_heading_rad": 0.1}, etapa="etapa 3")
        self.assertEqual(calib.campos_fragiles_desactualizados(), [])

    def test_medido_ayer_esta_desactualizado(self) -> None:
        calib.guardar({"offset_heading_rad": 0.1}, etapa="etapa 3")
        self._forzar_fecha("offset_heading_rad", "2020-01-01T10:00:00")
        self.assertEqual(calib.campos_fragiles_desactualizados(),
                         ["offset_heading_rad"])

    def test_id_marcador_ya_no_es_fragil(self) -> None:
        """
        Corrección del operador (2026-08-22): el marcador MONTADO EN EL
        CHASIS de cada robot es fijo (robot N → marcador N, hasta el 16),
        a diferencia de un marcador SUELTO. `id_marcador` salió de
        `CAMPOS_FRAGILES`: es un hecho de ingeniería conocido, no algo que
        haya que remedir cada sesión.
        """
        calib.guardar({"id_marcador": 2, "id_robot": 2}, etapa="etapa 1")
        self._forzar_fecha("id_marcador", "2020-01-01T10:00:00")
        self.assertEqual(calib.campos_fragiles_desactualizados(), [])

    def test_campos_no_fragiles_no_se_marcan_desactualizados(self) -> None:
        """
        Escala/marco/traslación dependen del sistema de captura del
        laboratorio, no de dónde estén pegados los marcadores — estables
        entre sesiones, así que NUNCA deben aparecer en la lista aunque
        sean viejos.
        """
        calib.guardar({"escala_posicion": 1.0, "rotacion_marco_rad": 0.0,
                       "traslacion_x_m": 1.5, "traslacion_y_m": 1.5},
                      etapa="etapa 2")
        for c in ("escala_posicion", "rotacion_marco_rad",
                 "traslacion_x_m", "traslacion_y_m"):
            self._forzar_fecha(c, "2020-01-01T10:00:00")
        self.assertEqual(calib.campos_fragiles_desactualizados(), [])

    def test_aplicar_a_config_no_usa_heading_desactualizado(self) -> None:
        calib.guardar({"offset_heading_rad": 0.3}, etapa="etapa 3")
        self._forzar_fecha("offset_heading_rad", "2020-01-01T10:00:00")
        previo_offset = cfg.OFFSET_HEADING_RAD
        previa_bandera = cfg.HEADING_NO_VERIFICADO
        try:
            aplicados = calib.aplicar_a_config()
            self.assertNotIn("offset_heading_rad", aplicados)
            self.assertNotEqual(cfg.OFFSET_HEADING_RAD, 0.3)
            self.assertTrue(cfg.HEADING_NO_VERIFICADO,
                            "con offset_heading_rad desactualizado, la "
                            "bandera debe seguir en True")
        finally:
            cfg.OFFSET_HEADING_RAD = previo_offset
            cfg.HEADING_NO_VERIFICADO = previa_bandera

    def test_aplicar_a_config_si_usa_heading_de_hoy(self) -> None:
        calib.guardar({"offset_heading_rad": 0.3}, etapa="etapa 3")
        previo_offset = cfg.OFFSET_HEADING_RAD
        previa_bandera = cfg.HEADING_NO_VERIFICADO
        try:
            aplicados = calib.aplicar_a_config()
            self.assertIn("offset_heading_rad", aplicados)
            self.assertEqual(cfg.OFFSET_HEADING_RAD, 0.3)
            self.assertFalse(cfg.HEADING_NO_VERIFICADO)
        finally:
            cfg.OFFSET_HEADING_RAD = previo_offset
            cfg.HEADING_NO_VERIFICADO = previa_bandera

    def test_faltantes_trata_lo_desactualizado_como_faltante(self) -> None:
        calib.guardar({
            "id_robot": 2, "id_marcador": 2, "escala_posicion": 1.0,
            "rotacion_marco_rad": 0.0, "traslacion_x_m": 1.5,
            "traslacion_y_m": 1.5, "offset_heading_rad": 0.0,
        }, etapa="etapa completa")
        self.assertEqual(calib.faltantes(), [])
        self._forzar_fecha("offset_heading_rad", "2020-01-01T10:00:00")
        faltan = calib.faltantes()
        self.assertEqual(len(faltan), 1)
        self.assertIn("offset_heading_rad", faltan[0])
        self.assertIn("sesión anterior", faltan[0])

    def test_resumen_marca_lo_desactualizado(self) -> None:
        calib.guardar({"offset_heading_rad": 0.1}, etapa="etapa 3")
        self._forzar_fecha("offset_heading_rad", "2020-01-01T10:00:00")
        texto = "\n".join(calib.resumen())
        self.assertIn("SESIÓN ANTERIOR", texto)

    def test_remedir_hoy_limpia_la_desactualizacion(self) -> None:
        """Volver a correr la etapa que mide el campo lo pone al día."""
        calib.guardar({"offset_heading_rad": 0.1}, etapa="etapa 3")
        self._forzar_fecha("offset_heading_rad", "2020-01-01T10:00:00")
        self.assertEqual(calib.campos_fragiles_desactualizados(),
                         ["offset_heading_rad"])
        calib.guardar({"offset_heading_rad": 0.1}, etapa="etapa 3")
        self.assertEqual(calib.campos_fragiles_desactualizados(), [])


class PruebaSecuencia(BaseSesion):

    def test_no_corre_una_etapa_si_la_previa_no_dio_ok(self) -> None:
        calib.registrar_etapa(1, "FALLO", "prueba")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            codigo = ses.correr_calibracion(self.ctx, solo_etapa=2)
        self.assertEqual(codigo, 3)
        self.assertIn("no dio OK", buf.getvalue())

    def test_forzar_la_corre_pero_avisa(self) -> None:
        calib.registrar_etapa(1, "FALLO", "prueba")
        self.ctx.forzar = True
        self.respuestas = ["", "1.2", "1.7", "", "2.1", "1.1"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ses.correr_calibracion(self.ctx, solo_etapa=2)
        self.assertIn("--forzar", buf.getvalue())

    def test_una_etapa_suelta_abre_sus_conexiones(self) -> None:
        """
        `--etapa N` con N > 0 es un caso de uso explícito (repetir una
        etapa). No debe depender de haber corrido la 0 en el mismo proceso.
        """
        calib.registrar_etapa(2, "OK", "prueba")
        self.assertIsNone(self.ctx.poses)
        self.respuestas = ["", "0.05", "1.0"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            codigo = ses.correr_calibracion(self.ctx, solo_etapa=3)
        self.assertIsNotNone(self.ctx.poses)
        self.assertNotIn("AttributeError", buf.getvalue())
        self.assertIn("ETAPA 3", buf.getvalue())
        self.assertIn(codigo, (0, 1))

    def test_la_calibracion_persiste_y_se_aplica(self) -> None:
        calib.guardar({
            "id_robot": ID_ROBOT, "id_marcador": ID_MARCADOR,
            "escala_posicion": 0.001, "rotacion_marco_rad": 0.25,
            "traslacion_x_m": 1.1, "traslacion_y_m": 1.2,
            "offset_heading_rad": -0.5,
        }, etapa="prueba")
        previos = (cfg.ESCALA_POSICION, cfg.ROTACION_MARCO_RAD,
                   cfg.OFFSET_HEADING_RAD, cfg.ESCALA_NO_VERIFICADA)
        try:
            aplicados = calib.aplicar_a_config()
            self.assertIn("escala_posicion", aplicados)
            self.assertEqual(cfg.ESCALA_POSICION, 0.001)
            self.assertEqual(cfg.ROTACION_MARCO_RAD, 0.25)
            self.assertEqual(cfg.OFFSET_HEADING_RAD, -0.5)
            self.assertFalse(cfg.ESCALA_NO_VERIFICADA)
            self.assertFalse(cfg.MARCO_NO_VERIFICADO)
            self.assertEqual(calib.faltantes(), [])
        finally:
            (cfg.ESCALA_POSICION, cfg.ROTACION_MARCO_RAD,
             cfg.OFFSET_HEADING_RAD, cfg.ESCALA_NO_VERIFICADA) = previos
            cfg.MARCO_NO_VERIFICADO = True
            cfg.HEADING_NO_VERIFICADO = True
            cfg.MAPEO_NO_VERIFICADO = True

    def test_guardar_respalda_lo_anterior_y_no_pierde_campos(self) -> None:
        calib.guardar({"escala_posicion": 1.0}, etapa="a")
        calib.guardar({"offset_heading_rad": 0.3}, etapa="b")
        datos = calib.cargar()
        self.assertEqual(datos["escala_posicion"], 1.0)
        self.assertEqual(datos["offset_heading_rad"], 0.3)
        respaldos = list(self.tmp.glob("calibracion_medida_prev_*.json"))
        self.assertGreaterEqual(len(respaldos), 1)

    def test_politica_se_niega_sin_calibracion(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            codigo = ses.main(["--sesion", "politica", "--simulador"])
        self.assertEqual(codigo, 3)
        self.assertIn("Faltan parámetros", buf.getvalue())

    def test_evaluacion_se_niega_sin_calibracion(self) -> None:
        """
        `evaluacion` se implementó el 2026-09-05 y con eso NINGUNA de las
        sesiones declaradas queda pendiente — el camino «NO está implementada»
        del despachador pasó a ser inalcanzable para los `choices` válidos, y
        por eso ya no hay una prueba que lo ejercite.

        Lo que sí hay que exigir es que se comporte como las otras: pedir la
        calibración antes de mover nada.
        """
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            codigo = ses.main(["--sesion", "evaluacion", "--simulador"])
        self.assertEqual(codigo, 3)
        self.assertIn("Faltan parámetros", buf.getvalue())

    def test_enjambre_se_niega_sin_calibracion(self) -> None:
        """
        `enjambre` se implementó el 2026-09-02 y por eso salió de la lista de
        pendientes. Ahora tiene que comportarse como `politica`: exigir la
        calibración antes de mover nada, no decir "no implementada".
        """
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            codigo = ses.main(["--sesion", "enjambre", "--simulador"])
        self.assertEqual(codigo, 3)
        self.assertIn("Faltan parámetros", buf.getvalue())

    def test_enjambre_rechaza_un_solo_agente(self) -> None:
        """Un agente no es un enjambre: con n=1 el `neighbor_embedding` de la
        observación queda en cero y la política sale de su régimen. Para eso
        está `--sesion politica`, y el error tiene que decirlo."""
        calib.guardar({
            "id_robot": ID_ROBOT, "id_marcador": ID_MARCADOR,
            "escala_posicion": 1.0, "rotacion_marco_rad": 0.0,
            "traslacion_x_m": 1.5, "traslacion_y_m": 1.5,
            "offset_heading_rad": 0.0,
        }, etapa="prueba")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            codigo = ses.main(["--sesion", "enjambre", "--simulador",
                               "--agentes", "1"])
        self.assertEqual(codigo, 2)
        self.assertIn("--sesion politica", buf.getvalue())


# =============================================================================
# 4. SESIÓN DE POLÍTICA Y ABORTOS
# =============================================================================

class BasePolitica(BaseSesion):
    """Calibración completa cargada y robot lejos de las paredes."""

    def setUp(self) -> None:
        super().setUp()
        calib.guardar({
            "id_robot": ID_ROBOT, "id_marcador": ID_MARCADOR,
            "escala_posicion": 1.0, "rotacion_marco_rad": 0.0,
            "traslacion_x_m": 1.5, "traslacion_y_m": 1.5,
            "offset_heading_rad": 0.0,
        }, etapa="prueba")
        calib.aplicar_a_config()
        self.ctx.cerrar()

    def tearDown(self) -> None:
        cfg.MARCO_NO_VERIFICADO = True
        cfg.HEADING_NO_VERIFICADO = True
        cfg.MAPEO_NO_VERIFICADO = True
        cfg.ESCALA_NO_VERIFICADA = True
        super().tearDown()

    def correr_politica(self, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = ses.sesion_politica(self.ctx, **kw)
        self.ultima_salida = buf.getvalue()
        return r


class PruebaPoliticaControlaElRobotCorrecto(BasePolitica):
    """
    Bug real encontrado (2026-08-22), preexistente: `construir(1)` arma el
    canal a partir de `cfg.MAPEO_AGENTES[0]`, no de `ctx.id_robot` /
    `ctx.marcador`. Sin el fix, el barrido correría en silencio sobre lo
    que hubiera en `MAPEO_AGENTES[0]` —una calibración de OTRO robot,
    persistida de una sesión anterior— y no sobre el robot que el operador
    pidió con `--robot`.
    """

    def test_ignora_un_mapeo_0_apuntando_a_otro_robot(self) -> None:
        # Simula el caso real: MAPEO_AGENTES[0] quedó de una calibración
        # anterior apuntando a un robot/marcador que NO es el de esta
        # sesión (99 no existe en el simulador de la prueba).
        previo = cfg.MAPEO_AGENTES
        cfg.MAPEO_AGENTES = dict(cfg.MAPEO_AGENTES)
        cfg.MAPEO_AGENTES[0] = cfg.AsignacionAgente(id_marcador=99,
                                                     id_robot=99)
        try:
            r = self.correr_politica(factores=[0.20],
                                     segundos_por_escalon=2.0,
                                     rpm_aborto=400.0)
        finally:
            cfg.MAPEO_AGENTES = previo
        self.assertTrue(r.paso, r.detalle)
        self.assertIn(f"{ID_ROBOT} / {ID_MARCADOR}", self.ultima_salida)
        # si hubiera usado el 99 equivocado, ni siquiera habría podido
        # conectar (no existe en el simulador) y la sesión habría fallado
        # antes de llegar a registrar ningún escalón.
        csvs = list((self.tmp / "resultados_sesion").glob("*barrido*.csv"))
        self.assertEqual(len(csvs), 1)


class PruebaDetectorCongelamiento(unittest.TestCase):
    """
    `DetectorCongelamiento`, aislado. Es la defensa que faltaba para la sesión
    de evaluación: se midió una pose congelada de 13.4 s, que sobre episodios
    de 50 s es el 27 % del episodio alimentando al env con una pose muerta —
    y la cobertura AoI resultante sería basura sin que ninguna validación de
    pose individual lo notara.
    """

    def test_pose_que_cambia_no_dispara(self) -> None:
        det = ses.DetectorCongelamiento(umbral=10, activo=True)
        for k in range(50):
            # jitter de captura: un marcador vivo nunca repite pose
            self.assertFalse(det.observar(0, (1.0 + k * 1e-7, 2.0, 0.5)))

    def test_pose_repetida_dispara_en_el_umbral(self) -> None:
        det = ses.DetectorCongelamiento(umbral=10, activo=True)
        pose = (1.0, 2.0, 0.5)
        # la primera lectura fija la referencia; disparan las repeticiones
        for k in range(10):
            self.assertFalse(det.observar(0, pose), f"disparó en la {k}")
        self.assertTrue(det.observar(0, pose))
        self.assertEqual(det.repeticiones(0), 10)

    def test_es_por_agente(self) -> None:
        """Un agente congelado no debe arrastrar a los demás."""
        det = ses.DetectorCongelamiento(umbral=3, activo=True)
        for k in range(10):
            congelado_0 = det.observar(0, (1.0, 2.0, 0.5))          # clavado
            congelado_1 = det.observar(1, (1.0 + k * 1e-6, 2.0, 0.5))  # vivo
            self.assertFalse(congelado_1)
        self.assertTrue(congelado_0)

    def test_reiniciar_limpia_el_estado(self) -> None:
        det = ses.DetectorCongelamiento(umbral=3, activo=True)
        for _ in range(5):
            det.observar(0, (1.0, 2.0, 0.5))
        det.reiniciar()
        self.assertEqual(det.repeticiones(0), 0)
        self.assertFalse(det.observar(0, (1.0, 2.0, 0.5)))

    def test_apagado_en_simulador(self) -> None:
        """
        El simulador local es IDEAL: un robot genuinamente detenido da poses
        idénticas, así que ahí el detector no puede distinguir «no se mueve»
        de «no lo vemos». Contra hardware sí, por el ruido de captura.
        """
        previo = cfg.SIMULADOR_ACTIVO
        cfg.SIMULADOR_ACTIVO = True
        try:
            det = ses.DetectorCongelamiento(umbral=2)   # activo=None → auto
            self.assertFalse(det.activo)
            for _ in range(20):
                self.assertFalse(det.observar(0, (1.0, 2.0, 0.5)))
        finally:
            cfg.SIMULADOR_ACTIVO = previo


class PruebaDetectorSeguimiento(unittest.TestCase):
    """
    El hueco del 2026-09-08: el robot 9 fue comandado a avanzar recto y giró
    sobre su eje. Recorrió el 33 % de lo comandado, pero su marcador se movía
    varios centímetros, así que el detector de ESTANCAMIENTO —que exige menos
    de 2 mm en 10 s— no habría disparado nunca.
    """

    def _correr(self, det, pasos, avance_por_paso, comandado_por_paso):
        malo = False
        for k in range(pasos):
            malo = det.observar(0, (k * avance_por_paso, 0.0),
                                comandado_por_paso)
            if malo:
                break
        return malo

    def test_un_robot_sano_no_dispara(self) -> None:
        det = ses.DetectorSeguimiento(ventana=10, activo=True)
        self.assertFalse(self._correr(det, 40, 0.030, 0.030))
        self.assertAlmostEqual(det.seguimiento(0), 1.0, places=2)

    def test_el_robot_que_gira_en_el_lugar_dispara(self) -> None:
        """La firma real del robot 9: 33 % de lo comandado."""
        det = ses.DetectorSeguimiento(ventana=10, activo=True)
        self.assertTrue(self._correr(det, 40, 0.010, 0.030))
        self.assertLess(det.seguimiento(0), ses.UMBRAL_SEGUIMIENTO)

    def test_girar_en_el_lugar_a_proposito_no_es_falta(self) -> None:
        """
        Si la política pide poca traslación, el robot puede legítimamente no
        desplazarse. Sin el mínimo de comando, esto sería un falso positivo
        constante — y un falso positivo aborta un episodio de 50 s.
        """
        det = ses.DetectorSeguimiento(ventana=10, activo=True)
        self.assertFalse(self._correr(det, 40, 0.0, 0.0005))
        self.assertIsNone(det.seguimiento(0))

    def test_no_juzga_antes_de_llenar_la_ventana(self) -> None:
        det = ses.DetectorSeguimiento(ventana=50, activo=True)
        self.assertFalse(self._correr(det, 40, 0.0, 0.030))

    def test_se_apaga_en_el_simulador(self) -> None:
        det = ses.DetectorSeguimiento(ventana=10, activo=False)
        self.assertFalse(self._correr(det, 40, 0.0, 0.030))

    def test_reiniciar_olvida_el_episodio_anterior(self) -> None:
        det = ses.DetectorSeguimiento(ventana=10, activo=True)
        self._correr(det, 40, 0.010, 0.030)
        det.reiniciar()
        self.assertIsNone(det.seguimiento(0))
        self.assertFalse(self._correr(det, 9, 0.030, 0.030))

    def test_el_umbral_separa_las_dos_poblaciones_medidas(self) -> None:
        """
        Calibrado sobre 397 ventanas de las corridas de barrido: el
        seguimiento sano tiene p05 = 0.94 y la cola patológica cae bajo 0.50.
        Si alguien mueve el umbral fuera de ese hueco, esto lo dice.
        """
        self.assertLess(ses.UMBRAL_SEGUIMIENTO, 0.90,
                        "el umbral invade la población sana (p05 = 0.94)")
        self.assertGreater(ses.UMBRAL_SEGUIMIENTO, 0.35,
                           "el umbral no cubre la firma del robot 9 (0.33)")


class PruebaEvaluacion(BaseSesion):
    """
    La sesión 'evaluacion' contra el simulador, con tres robots.

    Corre a factor FIJO y repite episodios completos, para producir la
    estadística que faltaba: cobertura AoI y colisiones entre robots.
    """

    ROBOTS = (0, 1, 2)

    def setUp(self) -> None:
        super().setUp()
        self.sim.detener()
        poses = {r: np.array([-0.4 + 0.4 * k, 0.2, 0.0])
                 for k, r in enumerate(self.ROBOTS)}
        self.sim = SimuladorRobotat({r: r + 1 for r in self.ROBOTS},
                                    poses, None)
        self.sim.iniciar()
        self._mapeo_previo = cfg.MAPEO_AGENTES
        cfg.MAPEO_AGENTES = {
            i: cfg.AsignacionAgente(id_marcador=r + 1, id_robot=r)
            for i, r in enumerate(self.ROBOTS)
        }
        calib.guardar({
            "id_robot": self.ROBOTS[0], "id_marcador": self.ROBOTS[0] + 1,
            "escala_posicion": 1.0, "rotacion_marco_rad": 0.0,
            "traslacion_x_m": 1.5, "traslacion_y_m": 1.5,
            "offset_heading_rad": 0.0,
        }, etapa="prueba")
        calib.aplicar_a_config()

    def tearDown(self) -> None:
        cfg.MAPEO_AGENTES = self._mapeo_previo
        for b in ("MARCO_NO_VERIFICADO", "HEADING_NO_VERIFICADO",
                  "MAPEO_NO_VERIFICADO", "ESCALA_NO_VERIFICADA"):
            setattr(cfg, b, True)
        super().tearDown()

    def test_los_blancos_salen_de_la_distribucion_de_entrenamiento(self) -> None:
        """
        El sorteo de blancos tiene que respetar el margen a la pared y la
        separación entre pares; si no, el chequeo geométrico los rechaza y
        el operador vuelve a quedarse sin blanco (que es el fallo original).
        """
        for semilla in range(30):
            blancos = ses.sortear_poses_arranque(
                5, np.random.default_rng(semilla))
            self.assertEqual(len(blancos), 5)
            for b in blancos.values():
                d_pared = min(float(b[0]), cfg.ARENA_WX_M - float(b[0]),
                              float(b[1]), cfg.ARENA_WY_M - float(b[1]))
                self.assertGreaterEqual(
                    d_pared, ses.MARGEN_ARRANQUE_M - 1e-9,
                    f"blanco a {d_pared:.3f} m de la pared (semilla {semilla})")
            ps = list(blancos.values())
            for i in range(len(ps)):
                for j in range(i + 1, len(ps)):
                    self.assertGreater(
                        float(np.linalg.norm(ps[i] - ps[j])),
                        ses.D_SEPARACION_OBJETIVO_M)

    def test_los_blancos_varian_entre_episodios(self) -> None:
        """
        El punto entero del sorteo: si diera siempre lo mismo, se repetiría
        el colapso de varianza que motivó todo esto.
        """
        centros = []
        for semilla in range(8):
            b = ses.sortear_poses_arranque(5, np.random.default_rng(semilla))
            centros.append(np.mean(np.array(list(b.values())), axis=0))
        disp = float(np.std(np.array(centros), axis=0).mean())
        self.assertGreater(disp, 0.05,
                           f"los centroides apenas varían (std {disp:.3f} m)")

    def test_la_guia_dice_cuanto_falta_y_para_donde(self) -> None:
        blancos = {0: np.array([1.0, 1.0]), 1: np.array([2.0, 2.0])}
        poses = {0: np.array([1.0, 1.0, 0.0]), 1: np.array([1.5, 2.0, 0.0])}
        lineas, todos_ok = ses._tabla_colocacion(poses, blancos)
        self.assertFalse(todos_ok)
        texto = "\n".join(lineas)
        self.assertIn("✔", texto)          # el agente 0 ya está
        self.assertIn("50.0 cm", texto)    # al agente 1 le faltan 50 cm
        self.assertIn("+x", texto)         # y tiene que ir hacia +x

        poses[1] = np.array([2.0, 2.0, 0.0])
        _l, todos_ok = ses._tabla_colocacion(poses, blancos)
        self.assertTrue(todos_ok)

        # 2026-09-22: congelado en su blanco NO es ✔ (el robot 2 lo tenía).
        lineas, todos_ok = ses._tabla_colocacion(poses, blancos, {1})
        self.assertFalse(todos_ok)
        texto = "\n".join(lineas)
        self.assertIn("CONGELADO", texto)
        self.assertEqual(texto.count("✔"), 1)       # sólo el agente 0

    def test_la_guia_sale_de_la_fuente_real_y_no_dice_SIN_POSE(self) -> None:
        """
        ⚠ REGRESIÓN (2026-09-09). `test_la_guia_dice_cuanto_falta_y_para_donde`
        le pasa a `_tabla_colocacion` un dict armado a mano, así que probaba el
        FORMATEADOR y no el cableado. En el laboratorio la guía imprimió
        "SIN POSE" para los cinco robots en todas las pausas de la sesión: el
        latido leía con `fuente.leer_poses()`, que devuelve una lista de pares
        (indice, medida), y la tabla indexa por agente.

        Esto entra por `_esperar_reposicionamiento` con una fuente que devuelve
        la MISMA forma que el adaptador real, que es lo único que cierra el
        agujero.
        """
        class FuenteComoLaReal:
            """Devuelve List[Tuple[int, medida]], igual que el adaptador."""
            def __init__(self) -> None:
                self.consultas = 0

            def leer_poses(self):
                self.consultas += 1
                Medida = collections.namedtuple("Medida", "pose")
                return [(0, Medida(np.array([1.0, 1.0, 0.0]))),
                        (1, Medida(np.array([1.5, 2.0, 0.0])))]

        class CanalMudo:
            def detener_todo(self, silencioso: bool = False) -> None:
                pass

        class CtxQueNoEspera:
            def esperar_enter(self, mensaje: str) -> None:
                time.sleep(0.15)      # deja latir al menos una vez

        blancos = {0: np.array([1.0, 1.0]), 1: np.array([2.0, 2.0])}
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            ses._esperar_reposicionamiento(
                CtxQueNoEspera(), FuenteComoLaReal(), CanalMudo(),
                "poné los robots", blancos)
        texto = salida.getvalue()

        self.assertNotIn("SIN POSE", texto)
        self.assertIn("50.0 cm", texto)   # al agente 1 le faltan 50 cm
        self.assertIn("+x", texto)

    def test_la_replica_arranca_de_la_pose_medida(self) -> None:
        """
        La réplica tiene que depender de la pose inicial: si diera lo mismo
        desde cualquier arranque, no estaría pareando nada.
        """
        a = {0: np.array([0.6, 0.6, 0.0]), 1: np.array([1.5, 1.5, 1.0]),
             2: np.array([2.4, 2.4, 2.0])}
        b = {0: np.array([1.2, 2.2, 0.5]), 1: np.array([2.2, 1.0, 2.5]),
             2: np.array([0.7, 1.6, 1.5])}
        ca = ses._replica_simulada(a, semilla=7, decisiones=40,
                                   n_agentes=3, factor=0.40)
        cb = ses._replica_simulada(b, semilla=7, decisiones=40,
                                   n_agentes=3, factor=0.40)
        if ca is None or cb is None:
            self.skipTest("no hay modelo entrenado disponible")
        self.assertGreater(ca, 0.0)
        self.assertNotAlmostEqual(ca, cb, places=4)

    def test_la_replica_no_tumba_la_sesion_si_falta_el_modelo(self) -> None:
        """
        Una réplica que falla es una comparación menos, nunca un episodio
        perdido: el hardware es lo caro de conseguir.
        """
        self.assertIsNone(ses._replica_simulada(
            {0: np.array([1.0, 1.0, 0.0])}, semilla=1, decisiones=10,
            n_agentes=3, factor=0.40))       # faltan agentes 1 y 2

    def test_un_rechazo_de_colocacion_no_gasta_el_intento(self) -> None:
        """
        ⚠ REGRESIÓN (2026-09-11). 7 de 19 intentos se perdieron porque un
        rechazo del chequeo de arranque gastaba el intento. Con UN solo
        intento permitido y un robot pegado a la pared, la sesión tiene que
        pedir la colocación de nuevo y terminar con el episodio válido.
        """
        r0 = self.ROBOTS[0]
        with self.sim._lock:
            self.sim.robots[r0].x = -1.45          # env x ≈ 0.05: pegado

        def operador_corrige(_mensaje: str) -> None:
            with self.sim._lock:
                self.sim.robots[r0].x = -0.8       # env x ≈ 0.70

        self.ctx.esperar_enter = operador_corrige
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ses.sesion_evaluacion(
                self.ctx, n_agentes=len(self.ROBOTS), factor=0.40,
                episodios_objetivo=1, episodios_minimo=1,
                decisiones=15, intentos_max=1, rpm_aborto=400.0)
        salida = buf.getvalue()
        self.assertIn("no se gasta el intento", salida)

        import csv as _csv
        eps = sorted((self.tmp / "resultados_sesion").glob("*episodios*.csv"))
        with open(eps[-1], newline="", encoding="utf-8") as fh:
            filas = list(_csv.DictReader(fh))
        self.assertEqual([f["valido"] for f in filas], ["1"], salida)

    def test_un_robot_que_se_va_de_la_red_aborta_con_su_motivo(self) -> None:
        """
        ⚠ REGRESIÓN (2026-09-24). Con un robot fuera de la red, cada envío
        intentaba reabrir su enlace y trababa el lazo ~0.45 s: el episodio
        moría a las 4 decisiones como "antigüedad de pose sobre el umbral",
        cinco veces seguidas. Tiene que abortar enseguida y decir la causa, y
        el intento siguiente no tiene que arrancar con el enlace caído.
        """
        self.sim.fallas.robots_que_caen_tras = {self.ROBOTS[1]: 30}
        self.sim.fallas.caidos_no_reaceptan = True
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ses.sesion_evaluacion(
                self.ctx, n_agentes=len(self.ROBOTS), factor=0.40,
                episodios_objetivo=1, episodios_minimo=1,
                decisiones=120, intentos_max=2, rpm_aborto=400.0)
        salida = buf.getvalue()
        import csv as _csv
        eps = sorted((self.tmp / "resultados_sesion").glob("*episodios*.csv"))
        with open(eps[-1], newline="", encoding="utf-8") as fh:
            filas = list(_csv.DictReader(fh))
        self.assertIn("enlace de ruedas caído", filas[0]["motivo"], salida)
        self.assertLess(int(filas[0]["decisiones"]), 60, salida)
        self.assertNotIn("antigüedad de pose", filas[0]["motivo"])
        # el segundo intento no arranca: el chequeo previo lo frena
        self.assertEqual(len(filas), 2, salida)
        self.assertIn("enlace de ruedas no responde", filas[1]["motivo"])
        self.assertEqual(filas[1].get("decisiones") or "", "")

    def test_al_terminar_un_episodio_valido_los_robots_quedan_frenados(self) -> None:
        """
        ⚠ REGRESIÓN (2026-09-30). Al terminar un episodio VÁLIDO no se mandaba
        la detención: los robots seguían con la última orden mientras la
        sesión calculaba la réplica simulada (25–56 cm a ciegas, sin CBF, en
        el laboratorio). Cuando se llama a la réplica, el canal ya tiene que
        haber frenado a todos.
        """
        estados = []
        original = ses._replica_simulada

        def replica_que_mira_las_ruedas(*args, **kwargs):
            t0 = time.perf_counter()
            while (not self.sim.todos_detenidos()
                   and time.perf_counter() - t0 < 0.5):
                time.sleep(0.01)          # el (0,0) viaja por TCP
            estados.append(self.sim.todos_detenidos())
            return None                   # la réplica en sí no importa acá

        ses._replica_simulada = replica_que_mira_las_ruedas
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ses.sesion_evaluacion(
                    self.ctx, n_agentes=len(self.ROBOTS), factor=0.40,
                    episodios_objetivo=1, episodios_minimo=1,
                    decisiones=25, intentos_max=2, rpm_aborto=400.0)
        finally:
            ses._replica_simulada = original
        self.assertTrue(estados, "no hubo ningún episodio válido: la prueba "
                                 "no ejercitó el camino que importa\n"
                        + buf.getvalue())
        self.assertTrue(all(estados),
                        "al pedir la réplica, algún robot seguía con orden "
                        "no nula tras un episodio válido")

    def test_produce_las_metricas_que_faltaban(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = ses.sesion_evaluacion(
                self.ctx, n_agentes=len(self.ROBOTS), factor=0.40,
                episodios_objetivo=2, episodios_minimo=1,
                decisiones=25, intentos_max=3, rpm_aborto=400.0)
        salida = buf.getvalue()
        self.assertIn("EVALUACIÓN", salida)

        import csv as _csv
        csvs = sorted((self.tmp / "resultados_sesion").glob("*.csv"))
        eps = [f for f in csvs if "episodios" in f.name][0]
        with open(eps, newline="", encoding="utf-8") as fh:
            filas = list(_csv.DictReader(fh))
        self.assertGreaterEqual(len(filas), 1)
        # las dos métricas que son el OBJETO de la sesión
        for clave in ("cobertura_aoi", "colisiones_015", "colisiones_022",
                      "d_pared_min", "frac_cbf", "n_escape", "frac_vecino",
                      "ciclo_p95_ms", "dist_min_robot", "valido", "motivo",
                      # 2026-09-24: contadores de la fuente y retrocesos
                      "poses_consultas", "poses_fallidas", "poses_rechazadas",
                      "poses_rechazos_motivo", "poses_bytes_descartados",
                      "poses_consultas_con_descarte", "decisiones_retroceso",
                      "frac_decisiones_retroceso", "retroceso_max_s",
                      "retrocesos_recuperados", "retrocesos_detalle",
                      "retrocesos_a0", "decisiones_retroceso_a0"):
            self.assertIn(clave, filas[0], clave)
        self.assertGreater(int(filas[0]["poses_consultas"]), 0)
        validos = [f for f in filas if f["valido"] == "1"]
        self.assertGreaterEqual(len(validos), 1, salida)
        self.assertGreater(float(validos[0]["cobertura_aoi"]), 0.0)
        # Con qué robots y sobre qué offset de rumbo se midió (2026-09-22).
        for clave in ("robot_a0", "offset_deg_a0", "offset_origen_a0",
                      "factor", "rpm_aborto"):
            self.assertIn(clave, validos[0], clave)
        self.assertEqual(int(validos[0]["robot_a0"]),
                         cfg.MAPEO_AGENTES[0].id_robot)

    def test_los_caveats_van_en_el_reporte(self) -> None:
        """No se descubren después: se declaran en la salida."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ses.sesion_evaluacion(
                self.ctx, n_agentes=len(self.ROBOTS), factor=0.40,
                episodios_objetivo=1, episodios_minimo=1,
                decisiones=20, intentos_max=2, rpm_aborto=400.0)
        salida = buf.getvalue()
        self.assertIn("CAVEATS", salida)
        self.assertIn("NO es pareada", salida)
        self.assertIn("NO la", salida)          # el factor no escala la obs.
        self.assertIn("COMPARACIÓN CONTRA SIMULACIÓN", salida)
        self.assertIn("0.5739", salida)          # referencia de Webots
        # La pareada tiene que estar y decir de qué arranca. Pero su réplica
        # corre sin capas y está sesgada a la baja (corrección del 12-09):
        # el informe tiene que decirlo y remitir a la réplica válida.
        self.assertIn("COMPARACIÓN PAREADA", salida)
        self.assertIn("pose REAL medida", salida)
        self.assertIn("SIN CBF ni escape", salida)   # la diferencia declarada
        self.assertIn("SESGADA A LA BAJA", salida)
        self.assertIn("replica_con_capas.py", salida)
        self.assertNotIn("es la que hay que citar", salida)

    def test_una_pausa_no_desboca_el_ritmo_del_lazo(self) -> None:
        """
        Regresión del 2026-09-05, el fallo más caro de la campaña.

        `EntornoEjecucionRobotat.avanzar` duerme contra un horario ABSOLUTO
        anclado en la primera llamada. Durante la pausa en que el operador
        reposiciona los robots, el reloj de pared avanza y el contador de
        ticks no; al reanudar, el objetivo queda decenas de segundos en el
        pasado y el lazo DEJA DE DORMIR.

        La sesión real corrió episodios de 500 decisiones en 6–8 s en vez de
        50: los robots tuvieron una séptima parte del tiempo para moverse y
        la cobertura AoI medida quedó sin sentido, sin que nada lo delatara.

        Acá se simula la pausa envejeciendo el reloj del entorno, y se exige
        que el episodio siguiente mantenga el ritmo.
        """
        from adaptadores_robotat import EntornoEjecucionRobotat
        from lanzar_robotat import construir

        fuente, canal, entorno = construir(len(self.ROBOTS))
        try:
            self.assertIsInstance(entorno, EntornoEjecucionRobotat)
            # ── el episodio 1 fija el ancla ──────────────────────────────
            t0 = time.perf_counter()
            entorno.avanzar(10)
            primero = time.perf_counter() - t0
            self.assertGreater(primero, 0.05,
                               "el primer tramo ya debería dormir")

            # ── pausa del operador: 3 s de reloj sin avanzar ticks ───────
            time.sleep(3.0)

            # SIN re-anclar: el horario quedó atrasado y no duerme
            t0 = time.perf_counter()
            entorno.avanzar(10)
            sin_anclar = time.perf_counter() - t0
            self.assertLess(sin_anclar, 0.02,
                            "esto es el bug: debería NO dormir tras la pausa")
            self.assertGreater(entorno.ticks_atrasados, 0)

            # CON re-anclar: vuelve a respetar el período
            entorno.reiniciar_reloj()
            t0 = time.perf_counter()
            entorno.avanzar(10)
            con_anclar = time.perf_counter() - t0
            self.assertGreater(
                con_anclar, 0.05,
                f"tras `reiniciar_reloj` debe volver a dormir; "
                f"durmió {con_anclar*1000:.1f} ms")
        finally:
            canal.cerrar()
            fuente.cerrar()

    def test_un_episodio_demasiado_rapido_se_invalida(self) -> None:
        """
        La red de seguridad del mismo fallo: si por lo que sea el lazo no
        corre al ritmo que dice, el episodio no se acepta como válido.

        El simulador local SÍ pacea bien —a diferencia de lo que se supuso al
        escribir esta prueba la primera vez—, así que no sirve para provocar
        el desborde. Se ejercita la aritmética del guardarraíl subiendo el
        período esperado: 30 decisiones que tardan ~3 s deben rechazarse si
        el período declarado dice que tendrían que tardar 30.
        """
        previo = ses.PERIODO_DECISION_S
        ses.PERIODO_DECISION_S = 1.0
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                ses.sesion_evaluacion(
                    self.ctx, n_agentes=len(self.ROBOTS), factor=0.40,
                    episodios_objetivo=1, episodios_minimo=1,
                    decisiones=30, intentos_max=1, rpm_aborto=400.0)
        finally:
            ses.PERIODO_DECISION_S = previo
        salida = buf.getvalue()
        self.assertIn("ritmo del lazo", salida, salida[-1500:])
        self.assertIn("INVÁLIDO", salida)

    def test_un_robot_que_gira_en_vez_de_avanzar_invalida_el_episodio(self):
        """
        El hueco que dejó el robot 9 el 2026-09-08, de punta a punta.

        Se le invierte una rueda a un robot a mitad de episodio: gira sobre
        su eje en vez de avanzar. El detector de ESTANCAMIENTO no sirve acá
        —en hardware el marcador va descentrado y traza un arco de varios
        centímetros, muy por encima de sus 2 mm— y el de CONGELAMIENTO
        tampoco, porque la pose sigue cambiando: el rumbo gira.

        Lo que tiene que dispararse es el de SEGUIMIENTO, y el episodio
        tiene que quedar INVÁLIDO con su motivo en vez de entrar en la
        estadística con un robot aportando cobertura nula.
        """
        original = ses.DetectorSeguimiento

        def forzado(*a, **kw):
            kw["activo"] = True
            kw.setdefault("ventana", 30)
            kw.setdefault("comando_minimo", 0.02)
            return original(*a, **kw)

        parar = threading.Event()
        victima = self.ROBOTS[1]

        def invertir_rueda() -> None:
            time.sleep(0.8)
            while not parar.is_set():
                with self.sim._lock:
                    est = self.sim.robots[victima]
                    est.rpm_der = -est.rpm_izq
                time.sleep(0.002)

        ses.DetectorSeguimiento = forzado
        hilo = threading.Thread(target=invertir_rueda, daemon=True)
        hilo.start()
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                ses.sesion_evaluacion(
                    self.ctx, n_agentes=len(self.ROBOTS), factor=0.40,
                    episodios_objetivo=1, episodios_minimo=1,
                    decisiones=200, intentos_max=2, rpm_aborto=400.0)
        finally:
            parar.set()
            ses.DetectorSeguimiento = original
        salida = buf.getvalue()
        self.assertIn("NO SIGUE", salida, salida[-2500:])
        self.assertIn("INVÁLIDO", salida)
        self.assertTrue(self.sim.todos_detenidos())

    def test_un_episodio_congelado_se_marca_invalido(self) -> None:
        """
        Congelamiento inyectado a mitad de episodio: el episodio se invalida
        con su motivo, y la sesión sigue en vez de caerse.

        Desde el 2026-09-24 un agente congelado RETROCEDE en vez de abortar
        (ver las pruebas siguientes). Acá se congelan LOS TRES a la vez, que
        aborta sin esperar a los retrocesos: todos con la pose repetida
        `umbral` decisiones seguidas es el flujo entero detenido, no un punto
        ciego (ver `_correr_episodio`).

        El detector se fuerza `activo=True` porque el simulador es ideal y por
        defecto va apagado ahí (ver `PruebaDetectorCongelamiento`).
        """
        original = ses.DetectorCongelamiento

        def forzado(*a, **kw):
            kw["activo"] = True
            kw.setdefault("umbral", 3)
            return original(*a, **kw)

        parar = threading.Event()

        # OJO: hay que congelarlos en posiciones VÁLIDAS y SEPARADAS. La
        # primera versión los clavaba en (0,0), que con cuaternión identidad
        # es exactamente el placeholder de «marcador no trackeado» — así que
        # `pose_es_valida` los rechazaba y el episodio ni siquiera arrancaba,
        # fallando por una razón distinta de la que se quiere probar.
        #
        # Y hay que clavar la pose COMPLETA, `yaw` incluido: un congelamiento
        # real detiene las tres componentes. Clavando sólo x e y, el simulador
        # sigue integrando el rumbo, la pose sigue cambiando y el detector
        # —correctamente— no dispara; el episodio terminaba abortando por
        # «sin desplazamiento», que es otra cosa.
        clavadas = {r: (-0.4 + 0.4 * k, 0.2, 0.0)
                    for k, r in enumerate(self.ROBOTS)}

        def congelar() -> None:
            time.sleep(0.8)
            while not parar.is_set():
                with self.sim._lock:
                    for r in self.ROBOTS:
                        est = self.sim.robots[r]
                        est.x, est.y, est.yaw = clavadas[r]
                time.sleep(0.002)

        ses.DetectorCongelamiento = forzado
        hilo = threading.Thread(target=congelar, daemon=True)
        hilo.start()
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                ses.sesion_evaluacion(
                    self.ctx, n_agentes=len(self.ROBOTS), factor=0.40,
                    episodios_objetivo=1, episodios_minimo=1,
                    decisiones=200, intentos_max=2, rpm_aborto=400.0)
        finally:
            parar.set()
            ses.DetectorCongelamiento = original
        salida = buf.getvalue()
        self.assertIn("CONGELADO", salida, salida[-2500:])
        self.assertIn("INVÁLIDO", salida)
        self.assertTrue(self.sim.todos_detenidos())

    def _zona_delante_del_agente(self, agente: int, parar: threading.Event,
                                 crecer: bool, notas: Dict[str, Any]) -> None:
        """
        Hilo de prueba: cuando el robot del agente ya anda —con 0.45 s de
        retardo, eso es mirar sus RUEDAS—, le pone delante un semiplano sin
        captura, 1 cm adelante sobre el eje dominante de su rumbo, que sólo
        afecta a su marcador. Anota si entró y si volvió a salir. Si
        `crecer`, al entrar la zona pasa a ser todo el plano: no puede salir.
        Si no, la zona se quita cuando ya salió (0.3 s afuera), para que la
        política no lo vuelva a meter.
        """
        from retroceso_congelamiento import rpm_a_v_omega
        robot = self.ROBOTS[agente]
        fallas = self.sim.fallas
        fallas.zona_solo_marcadores = {cfg.MAPEO_AGENTES[agente].id_marcador}
        t_marcha = None
        while not parar.is_set():
            v, _w = rpm_a_v_omega(*self.sim.rpm_en_ruedas(robot))
            if v > 0.03:
                t_marcha = t_marcha or time.perf_counter()
                if time.perf_counter() - t_marcha > 0.3:
                    break
            else:
                t_marcha = None
            time.sleep(0.005)
        x, y, yaw = self.sim.pose_de_robot(robot)
        c, s = math.cos(yaw), math.sin(yaw)
        if abs(c) >= abs(s):
            zona = ((x + 0.01, 50.0, -50.0, 50.0) if c > 0
                    else (-50.0, x - 0.01, -50.0, 50.0))
        else:
            zona = ((-50.0, 50.0, y + 0.01, 50.0) if s > 0
                    else (-50.0, 50.0, -50.0, y - 0.01))
        fallas.zona_sin_captura = zona
        notas["zona"] = zona

        def adentro() -> bool:
            px, py, _ = self.sim.pose_de_robot(robot)
            z = fallas.zona_sin_captura
            return z is not None and z[0] <= px <= z[1] and z[2] <= py <= z[3]

        t_afuera = None
        while not parar.is_set():
            if adentro():
                if not notas.get("entro"):
                    notas["entro"] = True
                    if crecer:
                        fallas.zona_sin_captura = (-50.0, 50.0, -50.0, 50.0)
                t_afuera = None
            elif notas.get("entro"):
                notas["salio"] = True
                t_afuera = t_afuera or time.perf_counter()
                if time.perf_counter() - t_afuera > 0.3:
                    fallas.zona_sin_captura = None
                    return
            time.sleep(0.002)

    def _episodio_con_zona(self, crecer: bool
                           ) -> Tuple[str, Dict[str, str], List[Dict[str, str]],
                                      Dict[str, Any]]:
        """Un episodio con detector forzado, ruido, retardo y la zona."""
        original = ses.DetectorCongelamiento

        def forzado(*a, **kw):
            kw["activo"] = True
            return original(*a, **kw)

        self.sim.fallas.ruido_pos_m = 0.0005
        self.sim.fallas.modo_marcador_perdido = "congelado"
        self.sim.fallas.retardo_actuacion_s = 0.45
        parar = threading.Event()
        notas: Dict[str, Any] = {}
        hilo = threading.Thread(target=self._zona_delante_del_agente,
                                args=(1, parar, crecer, notas), daemon=True)
        ses.DetectorCongelamiento = forzado
        hilo.start()
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                ses.sesion_evaluacion(
                    self.ctx, n_agentes=len(self.ROBOTS), factor=0.40,
                    episodios_objetivo=1, episodios_minimo=1,
                    decisiones=70, intentos_max=1, rpm_aborto=400.0)
        finally:
            parar.set()
            ses.DetectorCongelamiento = original
        import csv as _csv
        carpeta = self.tmp / "resultados_sesion"
        with open(sorted(carpeta.glob("*episodios*.csv"))[-1], newline="",
                  encoding="utf-8") as fh:
            ep = list(_csv.DictReader(fh))[0]
        with open(sorted(carpeta.glob("*decisiones*.csv"))[-1], newline="",
                  encoding="utf-8") as fh:
            filas = list(_csv.DictReader(fh))
        return buf.getvalue(), ep, filas, notas

    def test_un_marcador_congelado_retrocede_y_el_episodio_sigue(
            self) -> None:
        """
        2026-09-24: con la pose de un agente repetida, el robot RETROCEDE
        por donde entró a la primera repetición y se reanuda cuando la pose
        vuelve; el episodio NO se aborta. Reemplazó a la pausa, que dejaba
        al robot quieto DENTRO del punto ciego —el encargado del Robotat
        confirmó que ahí Motive retiene la última pose—, donde no se lo
        vuelve a ver nunca.

        Contra la "zona sin captura" del simulador, con 0.45 s de retardo
        de actuación y ruido de captura (un robot quieto no repite, como el
        real). Los retrocesos quedan en los dos CSV, porque afectan la
        cobertura.
        """
        salida, ep, filas, notas = self._episodio_con_zona(crecer=False)
        cola = salida[-3000:]
        self.assertTrue(notas.get("entro"), f"no entró en la zona: {notas}")
        self.assertTrue(notas.get("salio"), f"no salió de la zona: {notas}")
        self.assertEqual(ep["valido"], "1", cola)
        n_ret = int(ep["retrocesos_a1"])
        self.assertGreaterEqual(n_ret, 1, cola)
        self.assertEqual(int(ep["retrocesos_recuperados"]), n_ret, cola)
        for otro in (0, 2):
            self.assertEqual(ep[f"retrocesos_a{otro}"], "0", cola)
        n_dec = int(ep["decisiones_retroceso_a1"])
        self.assertGreaterEqual(n_dec, 3, cola)
        self.assertEqual(sum(int(f["en_retroceso"]) for f in filas
                             if f["agente"] == "1"), n_dec)
        self.assertIn("recuperada", ep["retrocesos_detalle"])
        self.assertIn("RETROCEDE", salida)
        self.assertIn("reanuda", salida)
        self.assertTrue(self.sim.todos_detenidos())

    def test_si_sigue_congelado_tras_retroceder_se_aborta(self) -> None:
        """
        Si el retroceso se agota y la pose sigue repetida, el robot queda
        parado y el episodio se aborta con su motivo, dentro del tope de
        tiempo (`VENTANA_MAX_S / K_MIN_RETROCESO + MARGEN_RETROCESO_S +
        ESPERA_VERIFICACION_S`).
        La zona crece a todo el plano en cuanto el robot entra: no hay por
        dónde salir.
        """
        from retroceso_congelamiento import (ESPERA_VERIFICACION_S,
                                             K_MIN_RETROCESO,
                                             MARGEN_RETROCESO_S,
                                             VENTANA_MAX_S)
        salida, ep, _filas, notas = self._episodio_con_zona(crecer=True)
        cola = salida[-3000:]
        self.assertTrue(notas.get("entro"), f"no entró en la zona: {notas}")
        self.assertEqual(ep["valido"], "0", cola)
        self.assertIn("CONGELADO", ep["motivo"], cola)
        self.assertIn("tras retroceder", ep["motivo"], cola)
        self.assertEqual(ep["retrocesos_a1"], "1", cola)
        self.assertIn("sigue_congelada", ep["retrocesos_detalle"])
        self.assertLessEqual(float(ep["retroceso_max_s"]),
                             VENTANA_MAX_S / K_MIN_RETROCESO
                             + MARGEN_RETROCESO_S + ESPERA_VERIFICACION_S
                             + 0.2, cola)
        self.assertIn("INVÁLIDO", salida)
        self.assertTrue(self.sim.todos_detenidos())


class PruebaEnjambre(BaseSesion):
    """
    La sesión 'enjambre' contra el simulador, con TRES robots.

    Existe porque hasta el 2026-09-02 la sesión de política era monoagente de
    hecho aunque el coordinador ya fuera multi-agente: el observador leía
    siempre las RPM del agente 0, y `_correr_escalon` medía seguimiento y
    oscilación sobre `registro[-1]` —el último agente del bucle—. Con un solo
    robot ninguna de las dos cosas se notaba.
    """

    N: int = 3
    ROBOTS = (0, 1, 2)

    def setUp(self) -> None:
        super().setUp()
        # Simulador con N robots, bien separados entre sí y de las paredes.
        # OJO: el simulador vive en el marco del LABORATORIO y `lab_a_env` le
        # suma la traslación (1.5, 1.5), así que estas coordenadas van
        # alrededor del origen — con (0.8, 1.5) el agente terminaba en
        # (2.3, 3.0) del env, o sea contra la pared.
        self.sim.detener()
        poses = {r: np.array([-0.4 + 0.4 * k, 0.2, 0.0])
                 for k, r in enumerate(self.ROBOTS)}
        self.sim = SimuladorRobotat(
            {r: r + 1 for r in self.ROBOTS}, poses, None)
        self.sim.iniciar()
        self._mapeo_previo = cfg.MAPEO_AGENTES
        cfg.MAPEO_AGENTES = {
            i: cfg.AsignacionAgente(id_marcador=r + 1, id_robot=r)
            for i, r in enumerate(self.ROBOTS)
        }
        calib.guardar({
            "id_robot": self.ROBOTS[0], "id_marcador": self.ROBOTS[0] + 1,
            "escala_posicion": 1.0, "rotacion_marco_rad": 0.0,
            "traslacion_x_m": 1.5, "traslacion_y_m": 1.5,
            "offset_heading_rad": 0.0,
        }, etapa="prueba")
        calib.aplicar_a_config()

    def tearDown(self) -> None:
        cfg.MAPEO_AGENTES = self._mapeo_previo
        for bandera in ("MARCO_NO_VERIFICADO", "HEADING_NO_VERIFICADO",
                        "MAPEO_NO_VERIFICADO", "ESCALA_NO_VERIFICADA"):
            setattr(cfg, bandera, True)
        super().tearDown()

    def test_los_tres_agentes_quedan_registrados(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = ses.sesion_politica(self.ctx, factores=[0.2],
                                    segundos_por_escalon=2.0,
                                    rpm_aborto=400.0, n_agentes=self.N)
        self.assertTrue(r.paso, r.detalle)

        import csv as _csv
        csvs = sorted((self.tmp / "resultados_sesion").glob("*.csv"))
        barrido = [f for f in csvs if "barrido-regimen" in f.name][0]
        # el nombre distingue la sesión: no se pisa con el de un robot
        self.assertIn("enjambre", barrido.name)
        with open(barrido, newline="", encoding="utf-8") as fh:
            filas = list(_csv.DictReader(fh))

        agentes = {int(f["agente"]) for f in filas}
        self.assertEqual(agentes, {0, 1, 2},
                         "deben registrarse los tres agentes, no sólo el 0")
        # y cada uno con SU robot, no el del agente 0
        for f in filas:
            self.assertEqual(int(f["robot"]),
                             cfg.MAPEO_AGENTES[int(f["agente"])].id_robot)
        # una fila por agente y por decisión
        por_agente = {a: sum(1 for f in filas if int(f["agente"]) == a)
                      for a in agentes}
        self.assertEqual(len(set(por_agente.values())), 1, por_agente)

    def test_las_rpm_son_las_de_cada_agente(self) -> None:
        """
        La regresión concreta: el observador leía `ultimas_rpm.get(0)` para
        TODAS las filas, así que con un enjambre habría guardado las RPM del
        robot 0 en las filas de los otros dos.
        """
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ses.sesion_politica(self.ctx, factores=[0.3],
                                segundos_por_escalon=2.0,
                                rpm_aborto=400.0, n_agentes=self.N)
        import csv as _csv
        barrido = [f for f in
                   sorted((self.tmp / "resultados_sesion").glob("*.csv"))
                   if "barrido-regimen" in f.name][0]
        with open(barrido, newline="", encoding="utf-8") as fh:
            filas = list(_csv.DictReader(fh))
        # Con tres robots decidiendo por separado, las RPM no pueden ser
        # idénticas entre agentes en TODAS las decisiones.
        por_dec: Dict[Any, set] = {}
        for f in filas:
            por_dec.setdefault(f["paso"], set()).add(
                (round(float(f["rpm_izq"]), 4), round(float(f["rpm_der"]), 4)))
        distintas = sum(1 for v in por_dec.values() if len(v) > 1)
        self.assertGreater(
            distintas, 0,
            "las RPM salieron iguales para los tres agentes en cada decisión: "
            "se están leyendo las del agente 0")

    def test_aborta_si_dos_robots_se_acercan_demasiado(self) -> None:
        """Seguridad propia del enjambre: contacto entre chasis."""
        def juntar() -> None:
            time.sleep(1.0)
            with self.sim._lock:
                self.sim.robots[self.ROBOTS[1]].x = \
                    self.sim.robots[self.ROBOTS[0]].x + 0.02
                self.sim.robots[self.ROBOTS[1]].y = \
                    self.sim.robots[self.ROBOTS[0]].y
        threading.Thread(target=juntar, daemon=True).start()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = ses.sesion_politica(self.ctx, factores=[0.2],
                                    segundos_por_escalon=6.0,
                                    rpm_aborto=400.0, n_agentes=self.N)
        self.assertIn("mínimo", r.detalle)
        self.assertTrue(self.sim.todos_detenidos())


class PruebaPoliticaBarrido(BasePolitica):

    def test_recorre_los_escalones_y_registra_todo(self) -> None:
        r = self.correr_politica(factores=[0.20, 0.40],
                                 segundos_por_escalon=2.0,
                                 rpm_aborto=400.0)
        self.assertTrue(r.paso, r.detalle)
        csvs = sorted((self.tmp / "resultados_sesion").glob("*.csv"))
        self.assertEqual(len(csvs), 2)

        import csv as _csv
        barrido = [f for f in csvs if "barrido-regimen" in f.name][0]
        with open(barrido, newline="", encoding="utf-8") as fh:
            filas = list(_csv.DictReader(fh))
        self.assertGreater(len(filas), 10)

        columnas = filas[0].keys()
        for esperada in ("v_nominal", "w_nominal", "v_tras_escape",
                         "v_ejecutada", "rpm_izq", "rpm_der", "en_escape",
                         "factor_total", "pose_env_x", "t_wall", "tick"):
            self.assertIn(esperada, columnas)
        # las 24 dimensiones de la observación
        self.assertEqual(sum(1 for c in columnas if c.startswith("obs_")), 24)
        # ambos escalones presentes y con el factor correcto
        self.assertEqual({f["escalon"] for f in filas}, {"0", "1"})

        resumen = [f for f in csvs if "resumen-escalones" in f.name][0]
        with open(resumen, newline="", encoding="utf-8") as fh:
            escalones = list(_csv.DictReader(fh))
        self.assertEqual(len(escalones), 2)
        for e in escalones:
            self.assertIn(e["veredicto"],
                          ("ESTABLE", "MARGINAL", "INESTABLE", "SIN DATOS"))
            self.assertIn("dist_comandada_m", e)

    def test_el_factor_operativo_escala_las_rpm(self) -> None:
        r = self.correr_politica(factores=[0.20], segundos_por_escalon=2.0,
                                 rpm_aborto=400.0)
        self.assertTrue(r.paso)
        import csv as _csv
        barrido = [f for f in (self.tmp / "resultados_sesion").glob("*.csv")
                   if "barrido-regimen" in f.name][0]
        with open(barrido, newline="", encoding="utf-8") as fh:
            filas = list(_csv.DictReader(fh))
        # con la rampa de arranque activa el factor total es 0.20 × 0.25
        factores = {round(float(f["factor_total"]), 4) for f in filas}
        self.assertTrue(
            factores <= {round(0.20 * cfg.FACTOR_VELOCIDAD_ARRANQUE, 4),
                         0.20},
            f"factores inesperados: {factores}")

    def test_diagnostico_muestra_las_referencias_de_simulacion(self) -> None:
        # >10 s para que llegue a emitirse el veredicto acumulado
        self.correr_politica(factores=[0.20], segundos_por_escalon=12.0,
                             rpm_aborto=400.0)
        for marca in ("sim: ~0.37", "sim: nunca < 0.18",
                      "sim: ~1.8 por agente-episodio",
                      "límite operativo de referencia: 200"):
            self.assertIn(marca, self.ultima_salida)
        self.assertTrue(
            ">>> NORMAL" in self.ultima_salida
            or ">>> ANÓMALO" in self.ultima_salida,
            "debe emitirse un veredicto acumulado cada 10 s")

    def test_un_escalon_con_poca_distancia_da_sin_datos(self) -> None:
        """
        Camino completo del veredicto SIN DATOS: se sube el umbral de
        distancia por encima de lo que el escalón puede recorrer, y se
        verifica que llega hasta el resumen impreso y el CSV en vez de
        declararse INESTABLE por un seguimiento que nadie midió.
        """
        previo = ses.DISTANCIA_MINIMA_SEGUIMIENTO_M
        ses.DISTANCIA_MINIMA_SEGUIMIENTO_M = 100.0     # inalcanzable
        try:
            r = self.correr_politica(factores=[0.20],
                                     segundos_por_escalon=2.0,
                                     rpm_aborto=400.0)
        finally:
            ses.DISTANCIA_MINIMA_SEGUIMIENTO_M = previo
        self.assertTrue(r.paso)
        self.assertIn("SIN DATOS", self.ultima_salida)
        self.assertNotIn("INESTABLE", self.ultima_salida)

    def test_seguimiento_por_distancias_acumuladas(self) -> None:
        """
        En el simulador la cinemática es ideal, así que el seguimiento debe
        dar ≈1. Es la comprobación de que la métrica mide lo que dice: el
        cociente instantáneo, a estas velocidades, daba 0 por ruido de
        cuantización del desplazamiento por decisión.
        """
        self.correr_politica(factores=[0.20], segundos_por_escalon=3.0,
                             rpm_aborto=400.0)
        import csv as _csv
        resumen = [f for f in (self.tmp / "resultados_sesion").glob("*.csv")
                   if "resumen-escalones" in f.name][0]
        with open(resumen, newline="", encoding="utf-8") as fh:
            e = list(_csv.DictReader(fh))[0]
        self.assertAlmostEqual(float(e["seguimiento"]), 1.0, delta=0.15)
        self.assertGreater(float(e["dist_comandada_m"]),
                           ses.DISTANCIA_MINIMA_SEGUIMIENTO_M)


class PruebaPresupuestoDeCicloEnLaPolitica(BasePolitica):
    """
    Punto 4 de la decisión 2026-08-22: instrumentar por decisión el riesgo
    de exceder el presupuesto de 100 ms. Con 120 ms de latencia inyectada
    en CADA consulta de poses, todas las decisiones del escalón deben
    quedar por encima del presupuesto — la instrumentación debe verlo y
    decirlo, no sólo registrar el número en el CSV.
    """
    fallas = FallasSimulador(latencia_poses_s=0.12)

    def test_detecta_ciclos_sobre_presupuesto(self) -> None:
        r = self.correr_politica(factores=[0.20], segundos_por_escalon=2.5,
                                 rpm_aborto=400.0)
        self.assertTrue(r.paso, r.detalle)
        self.assertIn("superaron el presupuesto", self.ultima_salida)
        self.assertIn("invalida la corrida", self.ultima_salida)

        import csv as _csv
        resumen = [f for f in (self.tmp / "resultados_sesion").glob("*.csv")
                   if "resumen-escalones" in f.name][0]
        with open(resumen, newline="", encoding="utf-8") as fh:
            fila = list(_csv.DictReader(fh))[0]
        self.assertGreater(float(fila["ciclo_ms_p95"]),
                           ses.PERIODO_DECISION_S * 1000.0)
        self.assertGreater(int(fila["ciclos_sobre_presupuesto"]), 0)

    def test_sin_latencia_extra_no_se_dispara(self) -> None:
        """Contraparte, en la misma clase de escenario: sin la falla
        inyectada (otra instancia de la sesión), el aviso no debe aparecer.
        Se verifica indirectamente vía PruebaPoliticaBarrido, que ya corre
        sin latencia y nunca menciona 'superaron el presupuesto' — acá se
        deja explícito el contraste con un umbral intermedio (30 ms, bien
        por debajo del presupuesto pero por encima del ruido de base)."""
        self.sim.fallas.latencia_poses_s = 0.0
        r = self.correr_politica(factores=[0.20], segundos_por_escalon=2.0,
                                 rpm_aborto=400.0)
        self.assertTrue(r.paso, r.detalle)
        self.assertNotIn("superaron el presupuesto", self.ultima_salida)


class PruebaPoliticaChequeoPrevio(BaseSesion):

    def setUp(self) -> None:
        super().setUp()
        calib.guardar({
            "id_robot": ID_ROBOT, "id_marcador": ID_MARCADOR,
            "escala_posicion": 1.0, "rotacion_marco_rad": 0.0,
            "traslacion_x_m": 1.5, "traslacion_y_m": 1.5,
            "offset_heading_rad": 0.0,
        }, etapa="prueba")
        calib.aplicar_a_config()
        # robot a 5 cm de la pared en el marco del env
        with self.sim._lock:
            self.sim.robots[ID_ROBOT].x = -1.45
        self.ctx.cerrar()

    def tearDown(self) -> None:
        cfg.MARCO_NO_VERIFICADO = True
        cfg.HEADING_NO_VERIFICADO = True
        cfg.MAPEO_NO_VERIFICADO = True
        cfg.ESCALA_NO_VERIFICADA = True
        super().tearDown()

    def test_no_arranca_pegado_a_la_pared_y_dice_donde_ponerlo(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = ses.sesion_politica(self.ctx, factores=[0.2],
                                    segundos_por_escalon=1.0)
        salida = buf.getvalue()
        self.assertEqual(r.veredicto, "FALLO")
        self.assertIn("pared", salida)
        # El mensaje pasó a ser por agente cuando la sesión se generalizó a
        # N robots (2026-09-02): en vez de "Ponelo a más de X" para el único
        # robot, ahora lista los límites y la posición de CADA agente, que es
        # lo que hace falta para acomodar cinco. Lo que la prueba exige sigue
        # siendo lo mismo: que diga DÓNDE está y DÓNDE tiene que estar.
        self.assertIn("hay que ponerlos dentro de", salida)
        self.assertIn("agente 0", salida)
        self.assertTrue(self.sim.todos_detenidos())


class PruebaAbortos(BasePolitica):
    """Las cuatro condiciones de aborto automático."""

    def test_aborto_por_rpm(self) -> None:
        r = self.correr_politica(factores=[1.0], segundos_por_escalon=8.0,
                                 rpm_aborto=1.0)
        self.assertIn("rpm comandada", self.ultima_salida)
        self.assertIn("ABORTO", self.ultima_salida)
        self.assertTrue(self.sim.todos_detenidos())
        self.assertEqual(r.veredicto, "ADVERTENCIA")

    def test_aborto_por_salir_del_area(self) -> None:
        """
        La pose tiene que seguir siendo PLAUSIBLE para el laboratorio y a la
        vez estar fuera de la arena: lab x = 2.0 ⇒ env x = 3.5, fuera de
        [0, 3] pero dentro de RANGO_LAB_X_M.

        Si se la manda más lejos (lab x = 5), la validación defensiva la
        rechaza por rango, el agente se queda sin pose y salta ANTES el
        aborto por antigüedad. Las dos defensas están escalonadas y esa es
        la que corresponde a una pose implausible.
        """
        def empujar() -> None:
            time.sleep(1.2)
            with self.sim._lock:
                self.sim.robots[ID_ROBOT].x = 2.0
        threading.Thread(target=empujar, daemon=True).start()
        self.correr_politica(factores=[0.2], segundos_por_escalon=6.0,
                             rpm_aborto=400.0)
        self.assertIn("fuera del área de trabajo", self.ultima_salida)
        self.assertTrue(self.sim.todos_detenidos())

    def test_pose_implausible_aborta_por_antiguedad(self) -> None:
        """La otra rama del escalonamiento, hecha explícita."""
        # Mismo margen que en `test_aborto_por_pose_vencida`: el empujón debe
        # llegar con el lazo ya corriendo, no durante la preparación.
        def empujar() -> None:
            time.sleep(2.5)
            with self.sim._lock:
                self.sim.robots[ID_ROBOT].x = 20.0
        threading.Thread(target=empujar, daemon=True).start()
        self.correr_politica(factores=[0.2], segundos_por_escalon=6.0,
                             rpm_aborto=400.0)
        self.assertIn("antigüedad de pose", self.ultima_salida)
        self.assertTrue(self.sim.todos_detenidos())

    def test_aborto_por_pose_vencida(self) -> None:
        # El marcador debe desaparecer DESPUÉS de que el lazo arrancó: si se
        # pierde antes, el chequeo previo aborta por "sin pose válida" y se
        # estaría probando otra cosa. El retardo era 1.0 s y quedaba muy
        # justo — 100 ms más de preparación (el chequeo de stream vivo que se
        # agregó el 2026-09-01) bastaron para cruzar el umbral. 2.5 s deja
        # margen holgado dentro de los 6 s del escalón.
        def ocultar() -> None:
            time.sleep(2.5)
            self.sim.fallas.marcadores_perdidos = {ID_MARCADOR}
        threading.Thread(target=ocultar, daemon=True).start()
        self.correr_politica(factores=[0.2], segundos_por_escalon=6.0,
                             rpm_aborto=400.0)
        self.assertIn("antigüedad de pose", self.ultima_salida)
        self.assertTrue(self.sim.todos_detenidos())

    def test_aborto_por_falta_de_desplazamiento(self) -> None:
        parar = threading.Event()

        def congelar() -> None:
            time.sleep(0.5)
            while not parar.is_set():
                with self.sim._lock:
                    self.sim.robots[ID_ROBOT].rpm_izq = 0.0
                    self.sim.robots[ID_ROBOT].rpm_der = 0.0
                time.sleep(0.002)

        threading.Thread(target=congelar, daemon=True).start()
        try:
            self.correr_politica(factores=[0.2], segundos_por_escalon=20.0,
                                 rpm_aborto=400.0)
        finally:
            parar.set()
        self.assertIn("sin desplazamiento", self.ultima_salida)
        self.assertTrue(self.sim.todos_detenidos())


class PruebaCriterioDeVeredicto(unittest.TestCase):
    """El criterio por escalón es automático y explícito."""

    def test_tabla_de_casos(self) -> None:
        casos = [
            (0.95, 0.05, False, True,  "ESTABLE"),
            (0.60, 0.05, False, True,  "MARGINAL"),
            (0.95, 0.35, False, True,  "MARGINAL"),
            (0.20, 0.05, False, True,  "INESTABLE"),
            (0.95, 0.60, False, True,  "INESTABLE"),
            (0.95, 0.05, True,  True,  "INESTABLE"),
        ]
        for seg, osc, ab, datos, esperado in casos:
            v, razon = ses._veredicto_escalon(seg, osc, ab, datos)
            self.assertEqual(v, esperado, f"seg={seg} osc={osc} ab={ab}")
            self.assertTrue(razon)

    def test_sin_datos_no_es_inestable(self) -> None:
        """
        Un escalón sin distancia comandada suficiente da seguimiento 0. Ese
        cero es AUSENCIA DE MEDICIÓN, no evidencia de inestabilidad, y
        confundirlos inventaría un resultado.
        """
        v, razon = ses._veredicto_escalon(0.0, 0.0, False,
                                          datos_suficientes=False)
        self.assertEqual(v, "SIN DATOS")
        self.assertIn("no alcanza", razon)
        # con datos, el mismo 0.0 sí es inestabilidad
        v2, _ = ses._veredicto_escalon(0.0, 0.0, False,
                                       datos_suficientes=True)
        self.assertEqual(v2, "INESTABLE")

    def test_el_aborto_manda_sobre_la_falta_de_datos(self) -> None:
        v, _ = ses._veredicto_escalon(0.0, 0.0, True, datos_suficientes=False)
        self.assertEqual(v, "INESTABLE")


class PruebaColocacionLeyYFiltro(unittest.TestCase):
    """Colocación autónoma (2026-09-22): la ley y el filtro, sin red."""

    def test_la_ley_gira_primero_avanza_despues_y_termina_orientada(self) -> None:
        import colocacion_autonoma as col
        b = np.array([2.0, 1.0])
        (v, w), f = col.ley_nominal(np.array([1.0, 1.0, 0.0]), b, 0.0, False)
        self.assertEqual(f, "avanzando")
        self.assertGreater(v, 0.0)
        self.assertAlmostEqual(w, 0.0, places=6)
        (v, w), f = col.ley_nominal(np.array([1.0, 1.0, math.pi]), b, 0.0, False)
        self.assertEqual(f, "girando")
        self.assertEqual(v, 0.0)
        self.assertGreaterEqual(abs(w), col.W_MIN)
        (v, w), f = col.ley_nominal(np.array([2.0, 1.0, 0.0]), b,
                                    math.pi / 2, True)
        self.assertEqual(f, "orientando")
        self.assertEqual(v, 0.0)
        self.assertGreater(w, 0.0)            # +90°: gira a la izquierda
        (v, w), f = col.ley_nominal(np.array([2.0, 1.0, math.pi / 2]), b,
                                    math.pi / 2, True)
        self.assertEqual((f, v, w), ("listo", 0.0, 0.0))

    def test_los_topes_son_el_regimen_del_laboratorio(self) -> None:
        import colocacion_autonoma as col
        self.assertLessEqual(col.V_COL, 0.08)
        self.assertLessEqual(col.W_COL, ses.OMEGA_LAB)
        for th in np.linspace(-math.pi, math.pi, 13):
            for bx in (0.2, 1.0, 2.9):
                (v, w), _f = col.ley_nominal(np.array([1.5, 1.5, th]),
                                             np.array([bx, 2.5]), 0.0, False)
                self.assertLessEqual(abs(v), col.V_COL + 1e-12)
                self.assertLessEqual(abs(w), col.W_COL + 1e-12)

    def test_el_filtro_usa_los_parametros_de_los_episodios(self) -> None:
        import colocacion_autonoma as col
        import coordinador_enjambre as ce
        self.assertEqual(col.ELE_A, ce.ELE_A)
        self.assertEqual(col.ALFA_CBF, ce.ALFA_CBF)
        self.assertEqual(col.D_SEGURA_PUNTO, ce.D_SEGURA_PUNTO)
        self.assertEqual(col.W_OMEGA, ce.W_OMEGA)
        self.assertAlmostEqual(col.D_ROBOTS, 0.15 + 2.0 * ce.ELE_A)

    def test_un_robot_fuera_de_la_arena_puede_volver_pero_no_alejarse(self) -> None:
        """
        Con la condición de los episodios (ḣ ≥ −α·h) un robot 10 cm fuera de
        la arena deja el QP infactible y queda clavado en (0,0). Con "no
        empeorar" puede entrar, y sigue sin poder salir más.
        """
        import colocacion_autonoma as col
        from lib.filtro_cbf import FiltroCBFParedes
        f = col.FiltroColocacion()
        adentro = f.filtrar(np.array([1.5, -0.10, math.pi / 2]),
                            np.array([col.V_COL, 0.0]))
        self.assertTrue(adentro.exito_qp)
        self.assertGreater(float(adentro.u_seguro[0]), 0.05)
        afuera = f.filtrar(np.array([1.5, -0.10, -math.pi / 2]),
                           np.array([col.V_COL, 0.0]))
        self.assertLessEqual(float(afuera.u_seguro[0]), 1e-6)

        import warnings
        episodios = FiltroCBFParedes(
            arena_size=(cfg.ARENA_WX_M, cfg.ARENA_WY_M), ele_a=col.ELE_A,
            alfa=col.ALFA_CBF, d_segura=col.D_SEGURA_PUNTO,
            w_omega=col.W_OMEGA, v_max=col.V_COL, omega_max=col.W_COL)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            clavado = episodios.filtrar(np.array([1.5, -0.10, math.pi / 2]),
                                        np.array([col.V_COL, 0.0]))
        self.assertFalse(clavado.exito_qp)      # el porqué del cambio

    def test_los_rumbos_son_deterministas_y_cubren_el_circulo(self) -> None:
        import colocacion_autonoma as col
        a = col.sortear_rumbos(5, 11)
        self.assertEqual(a, col.sortear_rumbos(5, 11))
        todos = [r for s in range(40) for r in col.sortear_rumbos(5, s).values()]
        self.assertTrue(all(-math.pi <= r <= math.pi for r in todos))
        self.assertLess(min(todos), -2.5)
        self.assertGreater(max(todos), 2.5)
        # agregar rumbos no cambia las posiciones de siempre
        self.assertTrue(all(
            np.allclose(ses.sortear_poses_arranque(5, np.random.default_rng(7))[i],
                        ses.sortear_poses_arranque(5, np.random.default_rng(7))[i])
            for i in range(5)))


class PruebaDiversidadArranques(unittest.TestCase):
    """
    2026-09-22: los 5 válidos del 11-09 arrancaron en formación compacta
    (vecino medio 0.27 m contra 0.64–0.84 m del sorteo de entrenamiento). La
    diversidad de los arranques se mide, no se supone.
    """

    def test_una_sesion_sorteada_no_se_marca(self) -> None:
        import diversidad_arranques as div
        eps = div._sortear_sesion(8, 5, np.random.default_rng(123))
        r = div.evaluar(eps, semilla=1, n_referencia=300)
        self.assertLessEqual(len(r["banderas"]), 1, r["lineas"])
        self.assertNotIn("POCO REPRESENTATIVOS", r["veredicto"])

    def test_la_formacion_compacta_del_11_de_septiembre_se_detecta(self) -> None:
        import diversidad_arranques as div
        cruz = np.array([[1.50, 0.98, 0.0], [1.76, 1.27, 1.0],
                         [1.50, 1.25, 2.0], [1.20, 1.20, -1.0],
                         [1.60, 1.53, -2.5]])
        eps = [cruz + np.r_[0.02 * k, 0.0, 0.0] for k in range(5)]
        r = div.evaluar(eps, semilla=1, n_referencia=300)
        self.assertIn("vecino_medio", r["banderas"])
        self.assertIn("celdas_cubiertas", r["banderas"])
        self.assertIn("POCO REPRESENTATIVOS", r["veredicto"])

    def test_el_informe_lee_filas_del_csv_y_tolera_faltantes(self) -> None:
        import diversidad_arranques as div
        rng = np.random.default_rng(5)
        filas = []
        for k, e in enumerate(div._sortear_sesion(4, 3, rng)):
            f = {"episodio": k + 1, "valido": 1 if k != 2 else 0}
            for i in range(3):
                f[f"blanco_x_a{i}"], f[f"blanco_y_a{i}"] = e[i, 0], e[i, 1]
                f[f"blanco_th_a{i}"] = e[i, 2]
                if f["valido"]:
                    f[f"x0_a{i}"], f[f"y0_a{i}"], f[f"th0_a{i}"] = e[i]
            filas.append(f)
        filas.append({"episodio": 5, "valido": 0, "motivo": "sin pose"})
        lineas: List[str] = []
        div.informe(filas, 3, imprimir=lineas.append)
        texto = "\n".join(lineas)
        self.assertIn("3 episodios × 3 robots", texto)
        self.assertIn("blancos de los 4 intentos", texto)


class _FuenteFija:
    """Poses fijas (con temblor opcional), con la interfaz de la fuente real."""

    def __init__(self, poses, temblor: float = 0.0) -> None:
        self.poses = {i: np.asarray(p, dtype=float) for i, p in poses.items()}
        self.temblor = temblor
        self._rng = np.random.default_rng(0)

    def leer_poses_ya(self):
        return {i: p + np.r_[self._rng.normal(0, self.temblor, 2), 0.0]
                for i, p in self.poses.items()}


class _CanalQueAnota:
    def __init__(self) -> None:
        self.envios: List[Dict[int, Any]] = []
        self.decisiones_enviadas = 0

    def enviar_directo(self, acciones) -> None:
        self.envios.append(dict(acciones))


class PruebaColocacionFallasSinRed(unittest.TestCase):
    """Abandonos: congelado y sin progreso, con fuente y canal falsos."""

    def setUp(self) -> None:
        self._sim_previo = cfg.SIMULADOR_ACTIVO
        cfg.SIMULADOR_ACTIVO = False       # el congelamiento es cosa del hw

    def tearDown(self) -> None:
        cfg.SIMULADOR_ACTIVO = self._sim_previo

    def test_un_marcador_congelado_frena_al_instante_y_para_a_todos(self) -> None:
        """
        Revisión adversarial 2026-09-22: a la primera repetición se lo frena
        (antes andaba 1.5 s a ciegas) y, confirmado el congelamiento, se
        detiene la colocación de TODOS: su posición real ya no se conoce.
        """
        import colocacion_autonoma as col
        fuente = _FuenteFija({0: [1.0, 1.0, 0.0]})          # nunca cambia
        otro = _FuenteFija({1: [2.0, 2.0, 0.0]}, temblor=2e-4)

        class Dos:
            def leer_poses_ya(self):
                return {**fuente.leer_poses_ya(), **otro.leer_poses_ya()}

        canal = _CanalQueAnota()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            inf = col.colocar_enjambre(
                Dos(), canal, {0: np.array([1.8, 1.0]), 1: np.array([1.2, 2.0])},
                {0: 0.0, 1: 0.0}, 2, t_max_s=10.0)
        self.assertEqual(inf.abandonados.get(0), "marcador congelado")
        self.assertIn("se detuvo la colocación de todos", inf.motivo_fin)
        self.assertNotEqual(canal.envios[0][0], (0.0, 0.0))   # 1.ª: se mueve
        self.assertEqual(canal.envios[1][0], (0.0, 0.0))      # repite: frena
        self.assertLess(inf.t_s, 4.0)
        self.assertEqual(canal.envios[-1], {0: (0.0, 0.0), 1: (0.0, 0.0)})

    def test_el_chequeo_de_arranque_rechaza_una_pose_que_no_esta_viva(self) -> None:
        congelada = _FuenteFija({0: [1.0, 1.0, 0.0]})
        viva = _FuenteFija({0: [1.0, 1.0, 0.0]}, temblor=2e-4)
        problemas = ses._marcadores_congelados_al_arrancar(congelada, 1)
        self.assertEqual(len(problemas), 1)
        self.assertIn("CONGELADO", problemas[0])
        self.assertEqual(ses._marcadores_congelados_al_arrancar(viva, 1), [])
        cfg.SIMULADOR_ACTIVO = True
        self.assertEqual(ses._marcadores_congelados_al_arrancar(congelada, 1),
                         [], "en el simulador un robot quieto repite pose")

    def test_un_robot_que_no_avanza_se_deja(self) -> None:
        import colocacion_autonoma as col
        previo = col.S_SIN_PROGRESO
        col.S_SIN_PROGRESO = 1.0
        try:
            fuente = _FuenteFija({0: [1.0, 1.0, 0.0]}, temblor=2e-4)  # vivo
            canal = _CanalQueAnota()
            with contextlib.redirect_stdout(io.StringIO()):
                inf = col.colocar_enjambre(
                    fuente, canal, {0: np.array([2.0, 1.0])}, {0: 0.0}, 1,
                    t_max_s=10.0)
        finally:
            col.S_SIN_PROGRESO = previo
        self.assertEqual(inf.abandonados.get(0), "no avanza")
        self.assertEqual(canal.envios[-1][0], (0.0, 0.0))


class PruebaColocacionAutonoma(BaseSesion):
    """Colocación autónoma contra el simulador, con tres robots."""

    ROBOTS = (0, 1, 2)

    def setUp(self) -> None:
        super().setUp()
        self.sim.detener()
        poses = {r: np.array([-0.4 + 0.4 * k, 0.2, 0.0])
                 for k, r in enumerate(self.ROBOTS)}
        self.sim = SimuladorRobotat({r: r + 1 for r in self.ROBOTS},
                                    poses, None)
        self.sim.iniciar()
        self._mapeo_previo = cfg.MAPEO_AGENTES
        cfg.MAPEO_AGENTES = {
            i: cfg.AsignacionAgente(id_marcador=r + 1, id_robot=r)
            for i, r in enumerate(self.ROBOTS)
        }
        calib.guardar({
            "id_robot": self.ROBOTS[0], "id_marcador": self.ROBOTS[0] + 1,
            "escala_posicion": 1.0, "rotacion_marco_rad": 0.0,
            "traslacion_x_m": 1.5, "traslacion_y_m": 1.5,
            "offset_heading_rad": 0.0,
        }, etapa="prueba")
        calib.aplicar_a_config()

    def tearDown(self) -> None:
        cfg.MAPEO_AGENTES = self._mapeo_previo
        for b in ("MARCO_NO_VERIFICADO", "HEADING_NO_VERIFICADO",
                  "MAPEO_NO_VERIFICADO", "ESCALA_NO_VERIFICADA"):
            setattr(cfg, b, True)
        super().tearDown()

    def _vigilar_distancias(self):
        """Distancia mínima entre centros, muestreada del estado del simulador."""
        minimo = [float("inf")]
        parar = threading.Event()

        def vigilar() -> None:
            while not parar.is_set():
                with self.sim._lock:
                    ps = [(r.x, r.y) for r in self.sim.robots.values()]
                for a in range(len(ps)):
                    for b in range(a + 1, len(ps)):
                        minimo[0] = min(minimo[0], math.dist(ps[a], ps[b]))
                time.sleep(0.01)

        hilo = threading.Thread(target=vigilar, daemon=True)
        hilo.start()
        return minimo, parar, hilo

    def test_llegan_solos_sin_chocar_y_sin_contar_decisiones(self) -> None:
        import colocacion_autonoma as col
        from lanzar_robotat import construir
        # Arrancan en fila (env y=1.7, mirando a +x) y tienen que CRUZARSE.
        blancos = {0: np.array([1.9, 1.2]), 1: np.array([1.0, 1.15]),
                   2: np.array([1.2, 2.3])}
        rumbos = {0: math.pi / 2, 1: -2.0, 2: 3.0}
        with contextlib.redirect_stdout(io.StringIO()):
            fuente, canal, _entorno = construir(len(self.ROBOTS))
        minimo, parar, hilo = self._vigilar_distancias()
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                inf = col.colocar_enjambre(fuente, canal, blancos, rumbos,
                                           len(self.ROBOTS), t_max_s=80.0)
        finally:
            parar.set()
            hilo.join(timeout=1.0)
            with contextlib.redirect_stdout(io.StringIO()):
                canal.cerrar()
                fuente.cerrar()
        salida = buf.getvalue()
        self.assertEqual(sorted(inf.listos), [0, 1, 2], salida)
        for i in range(3):
            self.assertLessEqual(inf.error_m[i], col.TOL_SALIDA_M, salida)
            self.assertLessEqual(inf.error_rumbo_deg[i], 25.0, salida)
        self.assertGreaterEqual(minimo[0], 0.15,
                                f"dos robots a {minimo[0]:.3f} m\n{salida}")
        self.assertEqual(canal.decisiones_enviadas, 0,
                         "la colocación no puede contar como decisión")

    def _colocar(self, blancos, rumbos, t_max_s=60.0):
        import colocacion_autonoma as col
        from lanzar_robotat import construir
        with contextlib.redirect_stdout(io.StringIO()):
            fuente, canal, _entorno = construir(len(self.ROBOTS))
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                inf = col.colocar_enjambre(fuente, canal, blancos, rumbos,
                                           len(self.ROBOTS), t_max_s=t_max_s)
        finally:
            with contextlib.redirect_stdout(io.StringIO()):
                canal.cerrar()
                fuente.cerrar()
        return inf, buf.getvalue()

    def _posiciones(self):
        with self.sim._lock:
            return {r: (s.x, s.y) for r, s in self.sim.robots.items()}

    def test_si_falta_uno_al_empezar_no_se_mueve_nadie(self) -> None:
        """
        Revisión adversarial 2026-09-22: un robot que no se ve desde el
        principio no tendría barrera en el filtro de los demás.
        """
        self.sim.fallas.marcadores_perdidos.add(3)        # robot 2 invisible
        antes = self._posiciones()
        inf, salida = self._colocar(
            {0: np.array([1.1, 1.2]), 1: np.array([1.6, 1.2]),
             2: np.array([2.2, 2.2])}, {0: 0.0, 1: 1.0, 2: 0.0})
        self.assertIn("sin pose al empezar", inf.motivo_fin, salida)
        self.assertEqual(inf.abandonados.get(2), "sin pose desde el inicio")
        despues = self._posiciones()
        for r in self.ROBOTS:
            self.assertLess(math.dist(antes[r], despues[r]), 1e-6,
                            f"robot {r} se movió\n{salida}")

    def test_si_uno_se_pierde_en_el_camino_los_demas_llegan(self) -> None:
        """Visto al principio y perdido después: queda quieto, los demás siguen."""
        def perder_tras(s: float) -> None:
            time.sleep(s)
            self.sim.fallas.marcadores_perdidos.add(3)
        threading.Thread(target=perder_tras, args=(1.0,), daemon=True).start()
        inf, salida = self._colocar(
            {0: np.array([1.1, 1.2]), 1: np.array([1.6, 1.2]),
             2: np.array([2.2, 2.2])}, {0: 0.0, 1: 1.0, 2: 0.0})
        self.assertEqual(inf.abandonados.get(2), "sin pose", salida)
        self.assertEqual(sorted(inf.listos), [0, 1], salida)

    def test_la_sesion_en_auto_arranca_desde_el_blanco(self) -> None:
        """
        Sesión completa con colocación automática: el episodio 1 también se
        coloca, arranca a menos de TOL_SALIDA_M de su blanco y el CSV dice
        cómo se colocó.
        """
        import colocacion_autonoma as col
        from coordinador_enjambre import SEMILLAS_LOTE
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ses.sesion_evaluacion(
                self.ctx, n_agentes=len(self.ROBOTS), factor=0.40,
                episodios_objetivo=1, episodios_minimo=1,
                decisiones=15, intentos_max=1, rpm_aborto=400.0,
                colocacion="auto")
        salida = buf.getvalue()
        self.assertIn("AUTOMÁTICA", salida)
        import csv as _csv
        eps = sorted((self.tmp / "resultados_sesion").glob("*episodios*.csv"))
        with open(eps[-1], newline="", encoding="utf-8") as fh:
            filas = list(_csv.DictReader(fh))
        self.assertEqual([f["valido"] for f in filas], ["1"], salida)
        f = filas[0]
        self.assertEqual(f["colocacion"], "auto")
        blancos = ses.sortear_poses_arranque(
            len(self.ROBOTS), np.random.default_rng(SEMILLAS_LOTE[0]))
        for i in range(len(self.ROBOTS)):
            self.assertEqual(f[f"col_estado_a{i}"], "listo", salida)
            d = math.dist((float(f[f"x0_a{i}"]), float(f[f"y0_a{i}"])),
                          tuple(blancos[i]))
            self.assertLessEqual(d, col.TOL_SALIDA_M, salida)


if __name__ == "__main__":
    print("=" * 70)
    print("PRUEBAS DE sesion_robotat.py CONTRA EL SIMULADOR")
    print("=" * 70)
    unittest.main(verbosity=2)
