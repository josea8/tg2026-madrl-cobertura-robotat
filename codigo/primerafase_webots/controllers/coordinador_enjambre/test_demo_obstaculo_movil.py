"""
test_demo_obstaculo_movil.py
============================
Pruebas de `demo_obstaculo_movil.py` contra `SimuladorRobotat` con SEIS
robots (los agentes 1, 5, 8, 6, 9 y el obstáculo 7) y retardo de actuación
de 0.45 s, más pruebas unitarias sin simulador.

    python -m unittest test_demo_obstaculo_movil -v

Lo que comprueban (plan de la Fase 0, 2026-10-01):
  · una sola consulta de poses por decisión, con los 6 marcadores;
  · `detener_todo` (fin de episodio, latido, `atexit`) frena al obstáculo;
  · el marcador del obstáculo congelado, o su enlace caído, aborta la toma
    con motivo PROPIO (no "el entorno pidió terminar") y lo frena;
  · con v = 0 la fila F1 es bit a bit la del Exp O con r = 0.15;
  · el obstáculo queda quieto durante la rampa de arranque seguro;
  · el freno de respaldo se dispara (frente y retroceso) y se cuenta, y una
    toma con freno no es válida para la demo;
  · sin obstáculo, las barreras y el escape son los del coordinador original;
  · el predictor de F2 integra el uniciclo exactamente;
  · las sesiones L0, L1 y L2 completas corren contra el simulador.
  · (2026-10-03) las reglas de parada de la sesión —contacto, freno en dos
    tomas seguidas, aborto o caída del enlace del obstáculo, sin distancia—
    la detienen con los robots frenados, siguen frenando con un latido
    mientras espera, avisan si no se pudo confirmar la detención y sólo
    sigue con una "s"; con tomas REALES la regla se dispara;
    `intento_inicial` sigue semillas y numeración; la L0 escribe su resumen
    en todos los caminos (normal, sin conexión, aborto radial, Ctrl+C); el
    analizador junta una sesión reanudada.
  · (2026-10-07) colocación automática, Fase B: geometría (proyección,
    envolvente, blancos a 0.65 m, rodeo, fila fija del Exp O); el supervisor
    de la L1 con el obstáculo conectado; contra un simulador con ZONA
    MUERTA y retardos 0.45/0.85 (y todos 0.85), blanco detrás del
    obstáculo: llegan todos a > 0.15 m en la verdad; fallas inyectadas
    (enlace del obstáculo que cae, marcador perdido o congelado, obstáculo
    que se mueve, contacto, obstáculo invisible al empezar); sesiones L1 y
    L2 automáticas; el robot del obstáculo es obligatorio en la línea de
    comandos.

Aislamiento: puertos propios (25000+), salidas a un temporal. Nunca se toca
`resultados_sesion/`, `resultados_demo_obstaculo/` ni la calibración.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import ast
import contextlib
import io
import itertools
import math
import shutil
import tempfile
import time
import types
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

import config_robotat as cfg
import demo_obstaculo_movil as demo
from simulador_robotat import FallasSimulador, SimuladorRobotat

_PUERTOS = itertools.count()
RUTA_EXP_O = (Path(__file__).resolve().parents[2] / "experimentos"
              / "expO_obstaculos" / "correr_experimento_O.py")


def _silencio():
    return contextlib.redirect_stdout(io.StringIO())


# =============================================================================
# UNITARIAS (sin simulador)
# =============================================================================

class PruebaPredictor(unittest.TestCase):
    """`predecir_pose` contra una integración de Euler fina, independiente."""

    def _euler(self, pose, mandos, ahora, tau, dt=1e-4):
        x, y, th = (float(v) for v in pose)
        t = ahora
        while t < ahora + tau - 1e-12:
            v = w = 0.0
            for tj, vj, wj in mandos:
                if tj + tau <= t + 1e-12:
                    v, w = vj, wj
            paso = min(dt, ahora + tau - t)
            x += v * math.cos(th) * paso
            y += v * math.sin(th) * paso
            th += w * paso
            t += paso
        return np.array([x, y, math.atan2(math.sin(th), math.cos(th))])

    def test_coincide_con_euler_en_historiales_al_azar(self) -> None:
        rng = np.random.default_rng(7)
        for _ in range(20):
            ahora = 10.0
            n = int(rng.integers(1, 15))
            ts = np.sort(rng.uniform(ahora - 1.2, ahora, n))
            mandos = [(float(t), float(rng.uniform(-0.12, 0.12)),
                       float(rng.uniform(-2.5, 2.5))) for t in ts]
            pose = np.array([1.0, 2.0, float(rng.uniform(-3, 3))])
            for tau in (0.45, 0.65, 0.85):
                a = demo.predecir_pose(pose, mandos, ahora, tau)
                b = self._euler(pose, mandos, ahora, tau)
                self.assertLess(float(np.linalg.norm(a[:2] - b[:2])), 2e-4)
                self.assertLess(abs(demo._envolver(a[2] - b[2])), 2e-3)

    def test_sin_retardo_o_sin_ordenes_no_se_mueve(self) -> None:
        pose = np.array([1.0, 1.0, 0.3])
        np.testing.assert_array_equal(
            demo.predecir_pose(pose, [(0.0, 0.1, 0.0)], 1.0, 0.0), pose)
        np.testing.assert_allclose(
            demo.predecir_pose(pose, [], 1.0, 0.65), pose)


class PruebaFilaExpO(unittest.TestCase):
    """
    Con el obstáculo quieto (s = 0) y sin saturación, la fila F1 es la del
    Exp O con r = 0.15, BIT A BIT. Se compara contra el código del Exp O tal
    cual (`barreras_obstaculos`, extraído de su archivo con `ast`), que usa
    el mismo `lib/filtro_cbf.py` (sha256 idéntico).
    """

    @classmethod
    def setUpClass(cls) -> None:
        fuente = RUTA_EXP_O.read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        nodos = [n for n in arbol.body
                 if (isinstance(n, ast.FunctionDef)
                     and n.name == "barreras_obstaculos")
                 or (isinstance(n, ast.AnnAssign)
                     and getattr(n.target, "id", "") == "MARGEN_OBS")]
        modulo = ast.Module(body=nodos, type_ignores=[])
        cls.ns: Dict[str, Any] = {"np": np, "Sequence": list}
        import __future__
        # El archivo del Exp O tiene `from __future__ import annotations`: sin
        # él, `Sequence[Obstaculo]` se evaluaría al definir la función.
        exec(compile(modulo, str(RUTA_EXP_O), "exec",
                     flags=__future__.annotations.compiler_flag,
                     dont_inherit=True), cls.ns)
        from lib.filtro_cbf import FiltroCBFParedes, RestriccionLineal
        cls.filtro = FiltroCBFParedes(arena_size=(3.0, 3.0), ele_a=0.05,
                                      alfa=2.0, d_segura=0.18, w_omega=0.3,
                                      v_max=0.31, omega_max=6.2832)
        cls.R = RestriccionLineal

    def _coord_falso(self, p_o: np.ndarray, formulacion: str = "F1"):
        return types.SimpleNamespace(
            _obst=demo.InstantaneaObstaculo(
                p=p_o, theta=0.7, v_hat=np.zeros(2), v_cmd=np.zeros(2),
                k=0.4, t=0.0),
            formulacion=formulacion, _filtro_cbf=self.filtro,
            h_geom_obstaculo={}, h_pred_obstaculo={},
            decisiones_fila_saturada=[0] * 5, _RestriccionLineal=self.R,
            _d_robots=0.25)

    def test_margen_del_exp_o_es_el_mismo(self) -> None:
        self.assertEqual(self.ns["MARGEN_OBS"], demo.MARGEN_OBSTACULO_M)

    def test_fila_quieta_es_la_del_exp_o_bit_a_bit(self) -> None:
        rng = np.random.default_rng(3)
        comparadas = 0
        for _ in range(200):
            p_o = rng.uniform(0.8, 2.2, 2)
            ang = rng.uniform(-math.pi, math.pi)
            r = rng.uniform(0.40, 1.0)
            pose = np.array([p_o[0] + r * math.cos(ang),
                             p_o[1] + r * math.sin(ang),
                             rng.uniform(-math.pi, math.pi)])
            ref = self.ns["barreras_obstaculos"](
                self.filtro, pose, [(float(p_o[0]), float(p_o[1]), 0.15)])[0]
            nuestra = demo.CoordinadorConObstaculo._fila_obstaculo(
                self._coord_falso(p_o), 0, pose)
            np.testing.assert_array_equal(nuestra.c, ref.c)
            self.assertEqual(nuestra.h, ref.h)
            comparadas += 1
        self.assertEqual(comparadas, 200)

    def test_con_velocidad_el_lado_derecho_suma_s_sobre_k(self) -> None:
        p_o = np.array([1.5, 1.5])
        coord = self._coord_falso(p_o)
        coord._obst.v_cmd = np.array([0.05, 0.0])     # va hacia +x
        pose = np.array([1.5 + 0.45, 1.5, 0.0])       # agente en +x
        fila = demo.CoordinadorConObstaculo._fila_obstaculo(coord, 0, pose)
        h = coord.h_geom_obstaculo[0]
        # h_eq = h − s/(k·α), con s = n·v = 0.05
        self.assertAlmostEqual(fila.h, h - 0.05 / (0.4 * 2.0), places=12)


class PruebaFreno(unittest.TestCase):
    """La condición de freno, sin simulador."""

    def setUp(self) -> None:
        self.sup = demo.SupervisorObstaculo.__new__(demo.SupervisorObstaculo)

    def test_frente_y_no_detras(self) -> None:
        pose = np.array([1.0, 1.0, 0.0])                  # mira a +x
        cond = demo.SupervisorObstaculo._condicion_freno
        delante = {0: np.array([1.15, 1.0, 0.0])}
        detras = {0: np.array([0.85, 1.0, 0.0])}
        self.assertEqual(cond(self.sup, pose, delante, set(), 0.20, 0.60)
                         ["causa"], "frente")
        self.assertIsNone(cond(self.sup, pose, detras, set(), 0.20, 0.60))

    def test_retroceso_cercano_frena_aunque_este_detras(self) -> None:
        pose = np.array([1.0, 1.0, 0.0])
        cond = demo.SupervisorObstaculo._condicion_freno
        detras = {3: np.array([0.55, 1.0, 0.0])}          # a 0.45 m, atrás
        self.assertIsNone(cond(self.sup, pose, detras, set(), 0.20, 0.60))
        d = cond(self.sup, pose, detras, {3}, 0.20, 0.60)
        self.assertEqual((d["causa"], d["agente"]), ("retroceso", 3))


class PruebaCorteEstancamiento(unittest.TestCase):
    """Réplica fuera de línea de la regla de 10 s del lazo de evaluación."""

    def test_quieto_diez_segundos_y_despues_empujado(self) -> None:
        """Con la regla ARREGLADA (2026-10-02): el agente quieto y sin orden
        10.5 s al que después se le ordena moverse NO corta en la primera
        decisión con orden (la regla vieja cortaba en la 105: el falso
        positivo). Si sigue trabado con orden sostenida, corta a los 10 s
        del inicio de la orden + 1 s de margen: decisión 105 + 111 = 216."""
        reg = []
        for paso in range(260):
            v = 0.0 if paso < 105 else 0.05
            reg.append({"agente": 0, "paso": paso, "pose_env_x": 1.0,
                        "pose_env_y": 1.0, "v_ejecutada": v,
                        "en_retroceso": 0})
        self.assertNotEqual(demo.primer_corte_por_estancamiento(reg[:200]),
                            (105, 0))
        self.assertEqual(demo.primer_corte_por_estancamiento(reg[:200]),
                         ("", ""))
        self.assertEqual(demo.primer_corte_por_estancamiento(reg), (216, 0))

    def test_moviendose_no_corta(self) -> None:
        reg = [{"agente": 0, "paso": p, "pose_env_x": 1.0 + 0.01 * p,
                "pose_env_y": 1.0, "v_ejecutada": 0.1, "en_retroceso": 0}
               for p in range(200)]
        self.assertEqual(demo.primer_corte_por_estancamiento(reg), ("", ""))


class PruebaFuenteValidaciones(unittest.TestCase):

    def test_rechaza_marcador_de_agente_y_modo_individual(self) -> None:
        with self.assertRaises(ValueError):
            demo.FuentePosesConObstaculo(5, id_marcador_obstaculo=1)
        previo = cfg.MODO_CONSULTA_POSES
        cfg.MODO_CONSULTA_POSES = "individual"
        try:
            with self.assertRaises(ValueError):
                demo.FuentePosesConObstaculo(5)
        finally:
            cfg.MODO_CONSULTA_POSES = previo


# =============================================================================
# CONTRA EL SIMULADOR (6 robots, retardo 0.45 s)
# =============================================================================

class BaseSim(unittest.TestCase):
    """Simulador de 6 robots en puertos propios; salidas a un temporal."""

    TAU: float = 0.45

    def setUp(self) -> None:
        k = next(_PUERTOS)
        self.puerto_poses = 25000 + 40 * k
        self.puerto_ruedas = 26000 + 40 * k
        cfg.activar_simulador_local(puerto_poses=self.puerto_poses,
                                    puerto_base=self.puerto_ruedas)
        self.tmp = Path(tempfile.mkdtemp(prefix="demo_obst_test_"))
        self._dir_previo = demo.DIR_SALIDA_DEMO
        demo.DIR_SALIDA_DEMO = self.tmp
        self.robots = [cfg.MAPEO_AGENTES[i].id_robot for i in range(5)]
        self.sim: Optional[SimuladorRobotat] = None
        self.entorno = None

    def tearDown(self) -> None:
        import atexit
        for f in getattr(self, "_atexit", []):
            atexit.unregister(f)
        try:
            if self.entorno is not None:
                with _silencio():
                    self.entorno.finalizar()
        except Exception:                                     # noqa: BLE001
            pass
        if self.sim is not None:
            self.sim.detener()
        cfg.SIMULADOR_ACTIVO = False
        demo.DIR_SALIDA_DEMO = self._dir_previo
        shutil.rmtree(self.tmp, ignore_errors=True)

    def levantar_sim(self, poses_env: Dict[int, Tuple[float, float, float]],
                     obst: Tuple[float, float, float],
                     fallas: Optional[FallasSimulador] = None) -> None:
        mapeo = {r: cfg.MAPEO_AGENTES[i].id_marcador
                 for i, r in enumerate(self.robots)}
        mapeo[demo.ID_ROBOT_OBSTACULO] = demo.ID_MARCADOR_OBSTACULO
        tx, ty = cfg.TRASLACION_X_M, cfg.TRASLACION_Y_M
        lab = {self.robots[i]: (x - tx, y - ty, th)
               for i, (x, y, th) in poses_env.items()}
        lab[demo.ID_ROBOT_OBSTACULO] = (obst[0] - tx, obst[1] - ty, obst[2])
        fallas = fallas or FallasSimulador()
        fallas.retardo_actuacion_s = self.TAU
        self.sim = SimuladorRobotat(mapeo, lab, fallas,
                                    puerto_poses=self.puerto_poses,
                                    puerto_base=self.puerto_ruedas)
        self.sim.iniciar()

    def armar(self, formulacion: str = "F2", freno_activo: bool = True,
              vigilar: Optional[bool] = None, modo: str = "movil",
              conectar_obstaculo: bool = True):
        with _silencio():
            fuente, canal, entorno = demo.construir_con_obstaculo(
                5, conectar_obstaculo=conectar_obstaculo)
            sup = demo.SupervisorObstaculo(fuente, canal, modo=modo,
                                           freno_activo=freno_activo,
                                           vigilar_congelamiento=vigilar)
            coord = demo.CoordinadorConObstaculo(
                fuente, canal, entorno, 5, 10, supervisor=sup,
                formulacion=formulacion)
        canal.factor_operativo = 0.40
        registro: List[Dict[str, Any]] = []
        coord._observador_paso = demo.crear_observador(
            coord, canal, registro, {"episodio": 1})
        self.entorno = entorno
        # El `atexit` del coordinador frenaría, al salir, contra los
        # endpoints REALES (el simulador ya no está activo): fuera.
        self._atexit = [coord._detener_seguro]
        return fuente, canal, entorno, sup, coord, registro

    @staticmethod
    def poses_lejos() -> Dict[int, Tuple[float, float, float]]:
        """Cinco agentes estacionados lejos del círculo."""
        return {0: (0.5, 0.5, 0.0), 1: (2.5, 0.5, 0.0), 2: (0.5, 2.5, 0.0),
                3: (2.5, 2.5, 0.0), 4: (1.5, 2.55, 0.0)}

    @staticmethod
    def quietos(i, pose_i, pose_o):
        return np.array([0.0, 0.0], dtype=np.float32)


class PruebaConsultaYRampa(BaseSim):

    def test_una_consulta_por_decision_y_quieto_en_la_rampa(self) -> None:
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        self.levantar_sim(self.poses_lejos(), (p0[0], p0[1], r0))
        fuente, canal, entorno, sup, coord, reg = self.armar()
        coord.instalar_nominal_forzada(self.quietos)
        x0, y0, _ = self.sim.pose_de_robot(demo.ID_ROBOT_OBSTACULO)
        with _silencio():
            res = demo.correr_toma(coord, canal, fuente, entorno, 420000, 80,
                                   reg, lazo="evaluacion")
        self.assertEqual(res["valido"], 1, res.get("motivo"))
        # Una consulta (con los 6 marcadores) por decisión, más las del
        # reinicio del episodio.
        self.assertEqual(self.sim.peticiones_pose, fuente.consultas)
        self.assertEqual(fuente.filas_obstaculo_validas, fuente.consultas)
        self.assertLessEqual(fuente.consultas, res["decisiones"] + 3)
        self.assertGreaterEqual(fuente.consultas, res["decisiones"])
        # Rampa: 50 decisiones con el obstáculo en (0, 0) y estado "espera".
        rampa = [f for f in sup.traza if f["paso"] < 50]
        self.assertEqual(len(rampa), 50)
        self.assertTrue(all(f["estado"] == "espera" and f["v_cmd"] == 0.0
                            for f in rampa))
        despues = [f for f in sup.traza if f["paso"] >= 50]
        self.assertTrue(any(f["estado"] in ("patada", "marcha")
                            for f in despues))
        self.assertAlmostEqual(despues[0]["v_cmd"], demo.V_PATADA_M_S,
                               places=9)
        # Y se movió recién después.
        x1, y1, _ = self.sim.pose_de_robot(demo.ID_ROBOT_OBSTACULO)
        self.assertGreater(math.hypot(x1 - x0, y1 - y0), 0.01)


class PruebaDetencion(BaseSim):

    def test_detener_todo_y_el_latido_frenan_al_obstaculo(self) -> None:
        self.levantar_sim(self.poses_lejos(), (1.5, 0.9, 0.0))
        fuente, canal, entorno, sup, coord, reg = self.armar()
        ro = demo.ID_ROBOT_OBSTACULO
        for silencioso in (False, True):
            canal.enviar_obstaculo(0.05, 0.0)
            time.sleep(0.05)
            self.assertNotEqual(self.sim.rpm_de_robot(ro), (0.0, 0.0))
            with _silencio():
                canal.detener_todo(silencioso=silencioso)
            time.sleep(0.05)
            self.assertEqual(self.sim.rpm_de_robot(ro), (0.0, 0.0))
            self.assertTrue(self.sim.todos_detenidos())
        # Y el cierre del canal también.
        canal.enviar_obstaculo(0.05, 0.0)
        time.sleep(0.05)
        with _silencio():
            canal.cerrar()
        time.sleep(0.05)
        self.assertEqual(self.sim.rpm_de_robot(ro), (0.0, 0.0))
        self.assertFalse(canal.tiene_sockets_abiertos())

    def test_el_historial_del_obstaculo_registra_el_freno(self) -> None:
        self.levantar_sim(self.poses_lejos(), (1.5, 0.9, 0.0))
        fuente, canal, entorno, sup, coord, reg = self.armar()
        canal.enviar_obstaculo(0.05, 0.0)
        canal.detener_obstaculo()
        self.assertEqual(canal.historial_mandos_obstaculo[-1][1:], (0.0, 0.0))


class PruebaAbortosDelObstaculo(BaseSim):

    def test_marcador_congelado_aborta_con_motivo_propio(self) -> None:
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        fallas = FallasSimulador(ruido_pos_m=0.0005,
                                 modo_marcador_perdido="congelado")
        self.levantar_sim(self.poses_lejos(), (p0[0], p0[1], r0), fallas)
        fuente, canal, entorno, sup, coord, reg = self.armar(vigilar=True)

        def congelar_tras_la_rampa(i, pose_i, pose_o):
            if coord._paso_episodio >= 60:
                self.sim.fallas.marcadores_perdidos = {
                    demo.ID_MARCADOR_OBSTACULO}
            return np.array([0.0, 0.0], dtype=np.float32)
        coord.instalar_nominal_forzada(congelar_tras_la_rampa)
        with _silencio():
            res = demo.correr_toma(coord, canal, fuente, entorno, 420000, 120,
                                   reg, lazo="evaluacion")
        self.assertEqual(res["valido"], 0)
        self.assertIn("OBSTÁCULO", res["motivo"])
        self.assertIn("CONGELADO", res["motivo"])
        self.assertLess(res["decisiones"], 70)
        time.sleep(0.05)
        self.assertEqual(self.sim.rpm_de_robot(demo.ID_ROBOT_OBSTACULO),
                         (0.0, 0.0))

    def _toma_con_enlace_caido(self, no_reacepta: bool):
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        fallas = FallasSimulador(
            robots_que_caen_tras={demo.ID_ROBOT_OBSTACULO: 70},
            caidos_no_reaceptan=no_reacepta)
        self.levantar_sim(self.poses_lejos(), (p0[0], p0[1], r0), fallas)
        fuente, canal, entorno, sup, coord, reg = self.armar()
        coord.instalar_nominal_forzada(self.quietos)
        with _silencio():
            res = demo.correr_toma(coord, canal, fuente, entorno, 420000, 150,
                                   reg, lazo="evaluacion")
        return res, canal

    def test_enlace_caido_robot_que_sigue_escuchando_queda_frenado(self) -> None:
        """El robot cerró el socket pero sigue en la red (el robot 3 del
        11-09): la toma se aborta con el motivo del obstáculo y, al reabrir
        el enlace en la detención, el 7 recibe (0, 0) y queda quieto."""
        res, canal = self._toma_con_enlace_caido(no_reacepta=False)
        self.assertEqual(res["valido"], 0)
        self.assertIn("enlace de ruedas del obstáculo", res["motivo"])
        with _silencio():
            canal.detener_todo()
        time.sleep(0.05)
        self.assertEqual(self.sim.rpm_de_robot(demo.ID_ROBOT_OBSTACULO),
                         (0.0, 0.0))
        x0, y0, _ = self.sim.pose_de_robot(demo.ID_ROBOT_OBSTACULO)
        time.sleep(self.TAU + 0.6)
        x1, y1, _ = self.sim.pose_de_robot(demo.ID_ROBOT_OBSTACULO)
        self.assertLess(math.hypot(x1 - x0, y1 - y0), 0.03)

    def test_enlace_caido_robot_inalcanzable_alarma(self) -> None:
        res, canal = self._toma_con_enlace_caido(no_reacepta=True)
        self.assertEqual(res["valido"], 0)
        self.assertIn("enlace de ruedas del obstáculo", res["motivo"])
        with _silencio():
            canal.detener_todo()
        self.assertTrue(canal.obstaculo_detencion_fallida)


class PruebaFrenoDeRespaldo(BaseSim):

    def test_frena_cuenta_y_la_toma_no_vale(self) -> None:
        """Sin barrera (formulación 'ninguna'), un agente que va derecho al
        obstáculo lo obliga a frenar: se cuenta y la toma no vale."""
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)    # (1.5, 0.9), +x
        poses = self.poses_lejos()
        delante = p0 + 0.55 * np.array([math.cos(r0), math.sin(r0)])
        poses[0] = (float(delante[0]), float(delante[1]), r0 + math.pi)
        self.levantar_sim(poses, (p0[0], p0[1], r0))
        fuente, canal, entorno, sup, coord, reg = self.armar(
            formulacion="ninguna", freno_activo=True)

        def kamikaze(i, pose_i, pose_o):
            if i != 0 or pose_o is None:
                return np.array([0.0, 0.0], dtype=np.float32)
            rumbo = math.atan2(pose_o[1] - pose_i[1], pose_o[0] - pose_i[0])
            err = demo._envolver(rumbo - float(pose_i[2]))
            return np.array([0.31 * max(0.0, math.cos(err)), 4.0 * err],
                            dtype=np.float32)
        rpm_en_freno: List[Tuple[float, float]] = []

        def kamikaze_que_mira(i, pose_i, pose_o):
            if i == 0 and sup.estado == "freno":
                rpm_en_freno.append(self.sim.rpm_de_robot(
                    demo.ID_ROBOT_OBSTACULO))
            return kamikaze(i, pose_i, pose_o)
        coord.instalar_nominal_forzada(kamikaze_que_mira)
        with _silencio():
            res = demo.correr_toma(coord, canal, fuente, entorno, 420000, 160,
                                   reg, lazo="medicion")
        self.assertEqual(res["valido"], 1, res.get("motivo"))
        self.assertGreaterEqual(res["frenos"], 1)
        self.assertEqual(sup.eventos_freno[0]["causa"], "frente")
        self.assertLess(sup.eventos_freno[0]["dist_m"],
                        demo.FRENO_DIST_FRENTE_M)
        self.assertGreater(res["decisiones_freno"], 0)
        self.assertEqual(res["valido_demo"], 0)
        self.assertIn("freno", res["motivo_demo"])
        # Lo que RECIBIÓ el robot 7 mientras el supervisor decía "freno".
        self.assertTrue(rpm_en_freno)
        self.assertTrue(all(r == (0.0, 0.0) for r in rpm_en_freno))

    def test_agente_en_retroceso_cerca_frena_al_obstaculo(self) -> None:
        """El camino real del retroceso: `canal.fijar_mando` (lo que usa el
        `GestorRetroceso`) deja al agente en `mandos_directos`, y el
        supervisor frena si está a < 0.60 m, aunque esté DETRÁS."""
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)    # (1.5, 0.9), +x
        poses = self.poses_lejos()
        detras = p0 - 0.55 * np.array([math.cos(r0), math.sin(r0)])
        poses[0] = (float(detras[0]), float(detras[1]), r0)
        self.levantar_sim(poses, (p0[0], p0[1], r0))
        fuente, canal, entorno, sup, coord, reg = self.armar()

        def retrocede_en_52(i, pose_i, pose_o):
            if i == 0 and coord._paso_episodio == 52:
                canal.fijar_mando(0, 0.0, 0.0, enviar_ya=True)
            return np.array([0.0, 0.0], dtype=np.float32)
        coord.instalar_nominal_forzada(retrocede_en_52)
        with _silencio():
            res = demo.correr_toma(coord, canal, fuente, entorno, 420000, 70,
                                   reg, lazo="medicion")
        self.assertGreaterEqual(res["frenos"], 1, res)
        self.assertEqual(sup.eventos_freno[0]["causa"], "retroceso")
        self.assertEqual(sup.eventos_freno[0]["agente"], 0)


class PruebaSinObstaculoEsElOriginal(BaseSim):
    """Sin instantánea del obstáculo, barreras y escape del original."""

    def test_barreras_y_normales_identicas(self) -> None:
        from coordinador_enjambre import CoordinadorEnjambre
        self.levantar_sim(self.poses_lejos(), (1.5, 0.9, 0.0))
        fuente, canal, entorno, sup, coord, reg = self.armar()
        rng = np.random.default_rng(11)
        for _ in range(50):
            poses = np.column_stack([rng.uniform(0.3, 2.7, 5),
                                     rng.uniform(0.3, 2.7, 5),
                                     rng.uniform(-math.pi, math.pi, 5)])
            coord._obst = None
            for i in range(5):
                a = coord._barreras_robot_robot(i, poses)
                b = CoordinadorEnjambre._barreras_robot_robot(coord, i, poses)
                self.assertEqual(len(a), len(b))
                for ra, rb in zip(a, b):
                    np.testing.assert_array_equal(ra.c, rb.c)
                    self.assertEqual((ra.h, ra.nombre), (rb.h, rb.nombre))
                da, ha = coord._normales_activas(i, poses)
                db, hb = CoordinadorEnjambre._normales_activas(coord, i, poses)
                self.assertEqual(ha, hb)
                if db is None:
                    self.assertIsNone(da)
                else:
                    np.testing.assert_array_equal(da, db)
            # Con el obstáculo LEJOS (h > umbral del escape), la copia de
            # `_normales_activas` da lo mismo que el original.
            coord._obst = demo.InstantaneaObstaculo(
                p=np.array([50.0, 50.0]), theta=0.0, v_hat=np.zeros(2),
                v_cmd=np.zeros(2), k=0.4, t=time.perf_counter())
            for i in range(5):
                da, ha = coord._normales_activas(i, poses)
                db, hb = CoordinadorEnjambre._normales_activas(coord, i, poses)
                self.assertEqual(ha, hb)
                if db is None:
                    self.assertIsNone(da)
                else:
                    np.testing.assert_array_equal(da, db)


class PruebaSesiones(BaseSim):
    """Las sesiones de laboratorio completas, contra el simulador."""

    def _ctx(self):
        import sesion_robotat as ses
        return ses.Contexto(sesion="prueba_demo",
                            id_robot=demo.ID_ROBOT_OBSTACULO,
                            marcador=demo.ID_MARCADOR_OBSTACULO,
                            simulador=True, preguntar=lambda _m: "")

    def _colocar_para(self, modo: str, semilla: int) -> None:
        objetivo, rumbo = demo.arranque_obstaculo(semilla, modo)
        blancos = demo.sortear_blancos_demo(5, semilla, objetivo)
        poses = {i: (float(b[0]), float(b[1]), 0.0)
                 for i, b in blancos.items()}
        # L1: el centro de la arena es el ORIGEN del laboratorio; con rumbo 0
        # el simulador publicaría exactamente el placeholder de "marcador no
        # trackeado" (origen + cuaternión identidad), que `pose_es_valida`
        # rechaza con razón. Un robot real nunca da eso: rumbo 0.3 rad.
        self.levantar_sim(poses, (float(objetivo[0]), float(objetivo[1]),
                                  rumbo if rumbo is not None else 0.3))

    def test_sesion_l2_una_toma(self) -> None:
        from coordinador_enjambre import SEMILLAS_LOTE
        self._colocar_para("L2", SEMILLAS_LOTE[0])
        with _silencio():
            r = demo.sesion_demo(self._ctx(), "L2", tomas=1, intentos_max=1,
                                 decisiones=90)
        self.assertEqual(r["veredicto"], "OK",
                         f"{r['detalle']} · {r['tomas'][0].get('motivo')}")
        t = r["tomas"][0]
        self.assertEqual(t["formulacion"], "F2")
        self.assertEqual(t["lazo"], "evaluacion")
        for patron in ("*L2_decisiones*.csv", "*L2_obstaculo*.csv",
                       "*L2_tomas*.csv"):
            self.assertTrue(list(self.tmp.glob(patron)), patron)
        time.sleep(0.05)
        self.assertTrue(self.sim.todos_detenidos())

    def test_sesion_l1_obstaculo_apagado(self) -> None:
        from coordinador_enjambre import SEMILLAS_LOTE
        self._colocar_para("L1", SEMILLAS_LOTE[0])
        with _silencio():
            r = demo.sesion_demo(self._ctx(), "L1", tomas=1, intentos_max=1,
                                 decisiones=60)
        self.assertEqual(r["veredicto"], "OK",
                         f"{r['detalle']} · {r['tomas'][0].get('motivo')}")
        self.assertEqual(r["tomas"][0]["obst_modo"], "quieto")
        # Nadie le mandó nada al 7.
        self.assertEqual(
            self.sim.robots[demo.ID_ROBOT_OBSTACULO].comandos_recibidos, 0)

    def test_sesion_l0(self) -> None:
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        self.levantar_sim(self.poses_lejos(), (p0[0], p0[1], r0))
        with _silencio():
            r = demo.sesion_l0(self._ctx(), arranques=2, marcha_s=3.0,
                               pausa_s=1.0)
        self.assertEqual(r["arranques_ok"], 2)
        self.assertLess(r["error_radial_max"], 0.05)
        # Con la pausa > τ, el movimiento detectado es el de ESTE arranque:
        # no puede aparecer antes del retardo. (En el simulador no hay
        # fricción de arranque: esto es una prueba de humo; el 10 de 10 se
        # valida en el laboratorio.)
        for a in r["arranques"]:
            self.assertGreaterEqual(float(a["t_movimiento_s"]), self.TAU)
        self.assertTrue(list(self.tmp.glob("*L0_traza*.csv")))


# =============================================================================
# AGREGADAS TRAS LA REVISIÓN ADVERSARIAL DE LA FASE 0
# =============================================================================

class _FuenteFalsa:
    def __init__(self, pose: np.ndarray, v: Optional[np.ndarray]) -> None:
        self.pose, self.v = pose, v
        self.repeticiones_obstaculo = 0

    def pose_obstaculo(self):
        return self.pose.copy()

    def antiguedad_obstaculo_s(self) -> float:
        return 0.0

    def velocidad_obstaculo(self):
        return None if self.v is None else self.v.copy()


class _CanalFalso:
    obstaculo_caido = False
    id_robot_obstaculo = 7

    def __init__(self) -> None:
        self.mandos: List[Tuple[float, float]] = []
        self.detenciones = 0

    def enviar_obstaculo(self, v: float, w: float) -> bool:
        self.mandos.append((v, w))
        return True

    def detener_obstaculo(self) -> bool:
        self.detenciones += 1
        return True


class PruebaObediencia(unittest.TestCase):
    """El supervisor compara lo comandado con lo medido (tiempo sintético)."""

    def _correr(self, v_medida, factor: float, segundos: float = 3.0,
                sin_estimacion_en=()):
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        fuente = _FuenteFalsa(np.array([p0[0], p0[1], r0]),
                              None if v_medida is None
                              else np.asarray(v_medida, dtype=float))
        canal = _CanalFalso()
        sup = demo.SupervisorObstaculo(fuente, canal, modo="movil",
                                       vigilar_congelamiento=False)
        v_ok = fuente.v
        for k in range(int(segundos / 0.1)):
            fuente.v = None if k in sin_estimacion_en else v_ok
            with _silencio():
                sup.paso({}, set(), factor, 100.0 + 0.1 * k, k)
            if sup.motivo_aborto:
                return sup, canal, 0.1 * k
        return sup, canal, None

    def test_obstaculo_que_no_se_mueve_aborta(self) -> None:
        sup, canal, t = self._correr([0.0, 0.0], factor=1.0)
        self.assertIn("NO SE MUEVE", sup.motivo_aborto)
        self.assertGreaterEqual(t, demo.T_VERIFICACION_OBEDIENCIA_S - 1e-9)
        self.assertGreaterEqual(canal.detenciones, 1)

    def test_obstaculo_que_no_frena_aborta(self) -> None:
        sup, canal, t = self._correr([0.05, 0.0], factor=0.5)   # en espera
        self.assertIn("NO FRENA", sup.motivo_aborto)

    def test_obstaculo_que_obedece_no_aborta(self) -> None:
        sup, canal, t = self._correr([0.05, 0.0], factor=1.0)
        self.assertIsNone(sup.motivo_aborto)

    def test_sin_estimacion_no_juzga(self) -> None:
        """2026-10-02: un hueco del lazo deja la ventana de v̂ vacía; sin
        estimación no se juzga (antes v̂ = 0 abortaba con el obstáculo
        andando)."""
        sup, canal, t = self._correr(None, factor=1.0)
        self.assertIsNone(sup.motivo_aborto)
        self.assertGreater(sup.decisiones_sin_estimacion, 0)

    def test_hace_falta_cinco_decisiones_seguidas(self) -> None:
        """Quieto con orden de marcha, pero sin estimación cada 4
        decisiones: la cuenta nunca llega a 5 y no aborta."""
        sup, canal, t = self._correr([0.0, 0.0], factor=1.0, segundos=4.0,
                                     sin_estimacion_en=set(range(0, 40, 4)))
        self.assertIsNone(sup.motivo_aborto)
        # Y sin huecos sí aborta, con la cuenta en el motivo.
        sup2, _c, _t = self._correr([0.0, 0.0], factor=1.0)
        self.assertIn("5 decisiones seguidas", sup2.motivo_aborto)


class PruebaVelocidadSinEstimacion(unittest.TestCase):
    """`velocidad_obstaculo` devuelve None, no cero, cuando no hay muestra en
    la ventana (el hipo de 0.374 s del 02-10)."""

    def test_hueco_mas_largo_que_la_ventana_da_none(self) -> None:
        f = demo.FuentePosesConObstaculo(5)
        self.assertIsNone(f.velocidad_obstaculo())            # sin historia
        f._obst_historial.extend([(10.0, 1.0, 1.0), (10.374, 1.0, 1.02)])
        self.assertIsNone(f.velocidad_obstaculo())            # hueco de 0.374 s
        f._obst_historial.clear()
        f._obst_historial.extend([(10.0, 1.0, 1.0), (10.1, 1.0, 1.005),
                                  (10.3, 1.0, 1.015)])
        v = f.velocidad_obstaculo()
        np.testing.assert_allclose(v, [0.0, 0.05], atol=1e-9)
        f._obst_historial.clear()
        f._obst_historial.extend([(10.0, 1.0, 1.0), (10.3, 1.0, 1.0)])
        np.testing.assert_array_equal(f.velocidad_obstaculo(), [0.0, 0.0])

    def test_la_barrera_recibe_cero_sin_estimacion(self) -> None:
        np.testing.assert_array_equal(demo._velocidad_o_cero(None), [0.0, 0.0])
        v = np.array([0.03, -0.01])
        self.assertIs(demo._velocidad_o_cero(v), v)


class PruebaFiltroConObstaculo(unittest.TestCase):
    """Peso de giro y rescate del QP (sólo actúan con la fila del obstáculo)."""

    def _filtro(self):
        return demo.FiltroConObstaculo(arena_size=(3.0, 3.0), ele_a=0.05,
                                       alfa=2.0, d_segura=0.18, w_omega=0.3,
                                       v_max=0.31, omega_max=6.2832)

    def test_rescate_evita_el_fallback(self) -> None:
        from lib.filtro_cbf import RestriccionLineal as R
        pose = np.array([1.5, 1.5, 0.0])
        filas = [R(c=np.array([1.0, 0.0]), h=-5.0, nombre="obstaculo"),
                 R(c=np.array([-1.0, 0.0]), h=0.0, nombre="robot_1")]
        sin = self._filtro()
        with _silencio(), contextlib.suppress(Warning):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                r0 = sin.filtrar(pose, np.array([0.2, 0.0]), filas)
        self.assertFalse(r0.exito_qp)                      # el de siempre
        con = self._filtro()
        con.rescate_obstaculo = True
        r1 = con.filtrar(pose, np.array([0.2, 0.0]), filas)
        self.assertTrue(r1.exito_qp)
        self.assertEqual(con.rescates["nivel_2"], 1)
        self.assertAlmostEqual(float(r1.u_seguro[0]), 0.0, places=6)

    def test_peso_de_giro_traslada_y_se_restaura(self) -> None:
        from lib.filtro_cbf import RestriccionLineal as R
        pose = np.array([1.5, 1.5, 0.0])
        fila = [R(c=np.array([0.3, 0.05]), h=-0.05, nombre="obstaculo")]
        base = self._filtro().filtrar(pose, np.zeros(2), fila)
        f = self._filtro()
        f.peso_giro_obstaculo = 3.0
        pes = f.filtrar(pose, np.zeros(2), fila)
        self.assertEqual(f.w_omega, 0.3)
        self.assertEqual(f.decisiones_peso_giro, 1)
        self.assertLess(abs(float(pes.u_seguro[1])), abs(float(base.u_seguro[1])))
        self.assertGreater(float(pes.u_seguro[0]), float(base.u_seguro[0]))

    def test_sin_fila_del_obstaculo_es_el_filtro_de_siempre(self) -> None:
        from lib.filtro_cbf import FiltroCBFParedes, RestriccionLineal as R
        pose = np.array([0.25, 1.5, math.pi])
        fila = [R(c=np.array([0.7, 0.01]), h=0.01, nombre="robot_2")]
        a = FiltroCBFParedes(arena_size=(3.0, 3.0), ele_a=0.05, alfa=2.0,
                             d_segura=0.18, w_omega=0.3, v_max=0.31,
                             omega_max=6.2832).filtrar(pose, np.array([0.3, 1.0]), fila)
        f = self._filtro()
        f.peso_giro_obstaculo = 3.0
        f.rescate_obstaculo = True
        b = f.filtrar(pose, np.array([0.3, 1.0]), fila)
        np.testing.assert_array_equal(a.u_seguro, b.u_seguro)


class PruebaEscapeConObstaculo(BaseSim):
    """La copia de `_normales_activas` con el obstáculo ACTIVO (h < 0.06)."""

    def test_normal_del_obstaculo_y_suma_con_la_pared(self) -> None:
        self.levantar_sim(self.poses_lejos(), (1.5, 0.9, 0.0))
        fuente, canal, entorno, sup, coord, reg = self.armar()
        poses = np.array([[1.5, 1.5, 0.0], [0.5, 0.5, 0.0], [2.5, 0.5, 0.0],
                          [0.5, 2.5, 0.0], [2.5, 2.5, 0.0]])
        # Sólo el obstáculo: a 0.36 m del punto de mira (h = 0.03), en −x.
        p_mira = poses[0, :2] + np.array([0.05, 0.0])
        coord._obst = demo.InstantaneaObstaculo(
            p=p_mira - np.array([0.36, 0.0]), theta=0.0, v_hat=np.zeros(2),
            v_cmd=np.zeros(2), k=0.4, t=time.perf_counter())
        d, h = coord._normales_activas(0, poses)
        np.testing.assert_allclose(d, [1.0, 0.0], atol=1e-12)
        self.assertAlmostEqual(h, 0.36 - demo.D_OBSTACULO_M, places=12)
        # Obstáculo + pared: el agente junto a la pared y = 0 (h_pared 0.01),
        # el obstáculo en −x: la dirección es la suma normalizada.
        poses[0] = [1.5, 0.19, 0.0]
        p_mira = poses[0, :2] + np.array([0.05, 0.0])
        coord._obst.p = p_mira - np.array([0.36, 0.0])
        d, h = coord._normales_activas(0, poses)
        np.testing.assert_allclose(d, np.array([1.0, 1.0]) / math.sqrt(2),
                                   atol=1e-12)
        # El obstáculo exactamente opuesto a la pared y = 3: sin salida.
        poses[0] = [1.5, 2.81, math.pi / 2]
        p_mira = poses[0, :2] + np.array([0.0, 0.05])
        coord._obst.p = p_mira - np.array([0.0, 0.36])
        d, h = coord._normales_activas(0, poses)
        self.assertIsNone(d)


class PruebaSeguimientoCirculoConRetardo(BaseSim):
    """Con τ = 0.85 s y el obstáculo colocado en el borde de la tolerancia
    (−6 cm, +25°), el seguimiento converge sin serpentear (revisión: con la
    ganancia de rumbo de antes, k·τ = 1.7 > π/2 y entraba en ciclo límite)."""

    TAU = 0.85

    def test_converge_desde_el_borde_de_la_tolerancia(self) -> None:
        fase = -math.pi / 2
        p0, r0 = demo.punto_del_circulo(fase)
        p0 = p0 - 0.06 * np.array([math.cos(fase), math.sin(fase)])
        self.levantar_sim(self.poses_lejos(),
                          (p0[0], p0[1], r0 + math.radians(25.0)))
        fuente, canal, entorno, sup, coord, reg = self.armar()
        coord.instalar_nominal_forzada(self.quietos)
        with _silencio():
            res = demo.correr_toma(coord, canal, fuente, entorno, 420000, 260,
                                   reg, lazo="medicion")
        self.assertEqual(res["valido"], 1, res.get("motivo"))
        self.assertLess(sup.error_radial_max_obs, demo.ERROR_RADIAL_MAX_M)
        marcha = [f for f in sup.traza if f["estado"] == "marcha"]
        ultimas = marcha[-100:]
        self.assertGreater(len(ultimas), 50)
        self.assertLess(max(abs(float(f["error_radial"])) for f in ultimas),
                        0.02)
        saturadas = sum(1 for f in marcha
                        if abs(float(f["w_cmd"])) >= demo.OMEGA_MAX_OBSTACULO - 1e-9)
        self.assertLess(saturadas / len(marcha), 0.10)


# =============================================================================
# REGLAS DE PARADA, REANUDACIÓN Y RESUMEN DE LA L0 (2026-10-03, OK de José)
# =============================================================================

def _toma_guion(**kw) -> Dict[str, Any]:
    """Una toma corrida, normal salvo lo que se indique."""
    t: Dict[str, Any] = {"valido": 1, "motivo": "", "d_min_obst_medida": 0.30,
                         "frenos": 0, "obst_motivo_aborto": "",
                         "obst_modo": "movil", "obst_recorrido_m": 2.4,
                         "obst_recorrido_comandado_m": 2.5, "decisiones": 500}
    t.update(kw)
    t["valido_demo"], t["motivo_demo"] = demo.validez_demo(t)
    return t


class PruebaReglaDeParada(unittest.TestCase):
    """`regla_de_parada` y `respuesta_sigue`, sin simulador."""

    def test_toma_normal_no_para(self) -> None:
        self.assertIsNone(demo.regla_de_parada(_toma_guion(), [_toma_guion()]))

    def test_contacto_para_valida_o_no(self) -> None:
        for valido in (1, 0):
            r = demo.regla_de_parada(
                _toma_guion(valido=valido, d_min_obst_medida=0.149), [])
            self.assertIsNotNone(r)
            self.assertIn("CONTACTO", r)
        # El umbral es estricto.
        self.assertIsNone(demo.regla_de_parada(
            _toma_guion(d_min_obst_medida=0.15), []))

    def test_sin_distancia_en_una_toma_que_corrio_para(self) -> None:
        for d in ("", float("nan")):
            r = demo.regla_de_parada(_toma_guion(d_min_obst_medida=d), [])
            self.assertIsNotNone(r)
            self.assertIn("SIN DISTANCIA MEDIDA", r)
        # Una toma que no llegó a correr (colocación o reinicio fallido) no.
        t = _toma_guion(d_min_obst_medida="")
        del t["decisiones"]
        self.assertIsNone(demo.regla_de_parada(t, []))

    def test_freno_en_dos_tomas_seguidas(self) -> None:
        f = _toma_guion(frenos=1)
        self.assertIsNone(demo.regla_de_parada(f, []))
        self.assertIsNone(demo.regla_de_parada(f, [f, _toma_guion()]))
        r = demo.regla_de_parada(f, [_toma_guion(), f])
        self.assertIsNotNone(r)
        self.assertIn("FRENO", r)
        # También si alguna de las dos no es válida para la medición.
        f_inv = _toma_guion(frenos=2, valido=0,
                            motivo="antigüedad de pose sobre el umbral")
        self.assertIn("FRENO", demo.regla_de_parada(f_inv, [f]))

    def test_aborto_por_el_obstaculo(self) -> None:
        for t in (_toma_guion(valido=0,
                              motivo="OBSTÁCULO: el obstáculo NO SE MUEVE: 1.5 s",
                              obst_motivo_aborto="el obstáculo NO SE MUEVE: 1.5 s"),
                  _toma_guion(valido=0,
                              motivo="OBSTÁCULO: el obstáculo NO FRENA: 1.5 s",
                              obst_motivo_aborto="el obstáculo NO FRENA: 1.5 s"),
                  _toma_guion(valido=0, motivo="OBSTÁCULO: enlace de ruedas "
                              "del obstáculo (robot 7) caído")):
            r = demo.regla_de_parada(t, [])
            self.assertIsNotNone(r)
            self.assertIn("ABORTO POR EL OBSTÁCULO", r)
        # Otra causa de invalidez (de la medición) no detiene la sesión.
        self.assertIsNone(demo.regla_de_parada(
            _toma_guion(valido=0, motivo="antigüedad de pose sobre el umbral"),
            []))

    def test_enlace_del_obstaculo_que_cayo_y_se_reabrio(self) -> None:
        r = demo.regla_de_parada(_toma_guion(obst_enlace_cayo=1), [])
        self.assertIsNotNone(r)
        self.assertIn("ENLACE DEL OBSTÁCULO", r)

    def test_hipo_del_servidor_de_poses_se_rotula_y_para(self) -> None:
        motivo = "pose del obstáculo vencida (1100 ms > 150 ms)"
        r = demo.regla_de_parada(_toma_guion(
            valido=0, motivo=f"OBSTÁCULO: {motivo}", obst_motivo_aborto=motivo,
            poses_fallidas=1), [])
        self.assertIsNotNone(r)
        self.assertIn("hipo del servidor de poses", r)
        # Sin consultas fallidas es del obstáculo (marcador perdido).
        r = demo.regla_de_parada(_toma_guion(
            valido=0, motivo=f"OBSTÁCULO: {motivo}", obst_motivo_aborto=motivo,
            poses_fallidas=0), [])
        self.assertIn("ABORTO POR EL OBSTÁCULO", r)

    def test_solo_una_s_sigue(self) -> None:
        for r in ("s", "S", " s ", "s\n"):
            self.assertTrue(demo.respuesta_sigue(r), repr(r))
        for r in ("", "n", "si", "sí", "seguir", "ss", "y"):
            self.assertFalse(demo.respuesta_sigue(r), repr(r))


class PruebaReglaConTomasReales(BaseSim):
    """
    Tomas REALES (`correr_toma` contra el simulador, sin barrera y con un
    agente que va derecho al obstáculo, como `PruebaFrenoDeRespaldo`): lo que
    devuelve el lazo llega a `regla_de_parada` y la dispara.
    """

    def test_contacto_y_dos_frenos_seguidos_reales(self) -> None:
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        poses = self.poses_lejos()
        delante = p0 + 0.55 * np.array([math.cos(r0), math.sin(r0)])
        poses[0] = (float(delante[0]), float(delante[1]), r0 + math.pi)
        self.levantar_sim(poses, (p0[0], p0[1], r0))
        fuente, canal, entorno, sup, coord, reg = self.armar(
            formulacion="ninguna", freno_activo=True)

        def kamikaze(i, pose_i, pose_o):
            if i != 0 or pose_o is None:
                return np.array([0.0, 0.0], dtype=np.float32)
            rumbo = math.atan2(pose_o[1] - pose_i[1], pose_o[0] - pose_i[0])
            err = demo._envolver(rumbo - float(pose_i[2]))
            return np.array([0.31 * max(0.0, math.cos(err)), 4.0 * err],
                            dtype=np.float32)
        coord.instalar_nominal_forzada(kamikaze)
        tx, ty = cfg.TRASLACION_X_M, cfg.TRASLACION_Y_M
        tomas: List[Dict[str, Any]] = []
        for k in range(2):
            with self.sim._lock:
                for i, r in enumerate(self.robots):
                    e = self.sim.robots[r]
                    x, y, th = poses[i]
                    e.x, e.y, e.yaw = x - tx, y - ty, th
                    e.rpm_izq = e.rpm_der = 0.0
                    e.rpm_izq_ruedas = e.rpm_der_ruedas = 0.0
                    e.en_camino.clear()
                e = self.sim.robots[demo.ID_ROBOT_OBSTACULO]
                e.x, e.y, e.yaw = p0[0] - tx, p0[1] - ty, r0
                e.rpm_izq = e.rpm_der = 0.0
                e.rpm_izq_ruedas = e.rpm_der_ruedas = 0.0
                e.en_camino.clear()
            time.sleep(0.6)
            with _silencio():
                tomas.append(demo.correr_toma(coord, canal, fuente, entorno,
                                              420000 + k, 160, reg,
                                              lazo="medicion"))
        for t in tomas:
            self.assertGreaterEqual(t["frenos"], 1)
            self.assertLess(float(t["d_min_obst_medida"]), 0.15)
        r1 = demo.regla_de_parada(tomas[0], [])
        self.assertIn("CONTACTO", r1)
        self.assertNotIn("FRENO", r1)
        r2 = demo.regla_de_parada(tomas[1], tomas[:1])
        self.assertIn("CONTACTO", r2)
        self.assertIn("FRENO DE RESPALDO en 2 tomas seguidas", r2)


class PruebaSesionReglasDeParada(BaseSim):
    """
    La sesión L2 COMPLETA contra el simulador —marcadores, enlaces,
    colocación con la guía, chequeos de arranque, CSV— con las tomas
    GUIONADAS: `correr_toma` devuelve resultados prefijados (y deja al
    obstáculo ANDANDO, como al final de una toma real que no frenó), para
    provocar cada regla de parada sin esperar a que ocurra. El "operador"
    pone a los robots en sus blancos antes de cada Enter y contesta la
    pregunta de la parada.
    """

    def setUp(self) -> None:
        super().setUp()
        from unittest import mock
        self._orig = (demo.correr_toma, demo.arranque_obstaculo,
                      demo.sortear_blancos_demo)
        self.actual: Dict[str, Any] = {}
        self.preguntas_parada: List[str] = []
        self.detenidos_al_preguntar: List[bool] = []
        self.semillas: List[int] = []
        self.sin_colocar: set = set()
        self.espera_s = 0.0
        self.n_detener = 0
        self.detener_durante_espera = 0

        def arranque(semilla, modo, par=None):
            self.actual["semilla"] = semilla
            self.actual["obst"] = self._orig[1](semilla, modo, par)
            return self.actual["obst"]

        def blancos(n, semilla, punto, intentos=200):
            self.actual["blancos"] = self._orig[2](n, semilla, punto, intentos)
            return self.actual["blancos"]

        demo.arranque_obstaculo = arranque
        demo.sortear_blancos_demo = blancos
        orig_detener = demo.CanalConObstaculo.detener_todo

        def espia(canal, *a, **k):
            self.n_detener += 1
            return orig_detener(canal, *a, **k)
        self._parches = [
            # Que la sesión no deje `atexit` contra los endpoints reales.
            mock.patch.object(demo.atexit, "register", lambda f, *a, **k: f),
            mock.patch.object(demo.CanalConObstaculo, "detener_todo", espia),
        ]
        for pa in self._parches:
            pa.start()
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        self.levantar_sim(self.poses_lejos(), (p0[0], p0[1], r0))

    def tearDown(self) -> None:
        for pa in self._parches:
            pa.stop()
        (demo.correr_toma, demo.arranque_obstaculo,
         demo.sortear_blancos_demo) = self._orig
        super().tearDown()

    def _guion(self, tomas: List[Dict[str, Any]], antes_de_volver=None) -> None:
        guion = iter(tomas)

        def falsa(coord, canal, fuente, entorno, semilla, decisiones,
                  registro, rpm_aborto=200.0, **_kw):
            self.semillas.append(int(semilla))
            canal.enviar_obstaculo(0.05, 0.0)       # queda andando
            if antes_de_volver is not None:
                antes_de_volver(canal)
            r = dict(next(guion))
            r["decisiones"] = decisiones
            return r

        demo.correr_toma = falsa

    def _ctx(self, respuesta_parada: str):
        import sesion_robotat as ses
        from colocacion_autonoma import sortear_rumbos
        from coordinador_enjambre import SEMILLAS_LOTE
        tx, ty = cfg.TRASLACION_X_M, cfg.TRASLACION_Y_M

        def preguntar(mensaje: str) -> str:
            if "¿Seguir con la sesión?" in mensaje:
                self.preguntas_parada.append(mensaje)
                self.detenidos_al_preguntar.append(self.sim.todos_detenidos())
                if self.espera_s:
                    n0 = self.n_detener
                    time.sleep(self.espera_s)
                    self.detener_durante_espera = self.n_detener - n0
                return respuesta_parada
            if "Colocá los agentes" in mensaje and "blancos" in self.actual:
                intento = SEMILLAS_LOTE.index(self.actual["semilla"]) + 1
                if intento in self.sin_colocar:
                    return ""
                rumbos = sortear_rumbos(5, self.actual["semilla"])
                objetivo, rumbo = self.actual["obst"]
                with self.sim._lock:
                    for i, r in enumerate(self.robots):
                        b = self.actual["blancos"][i]
                        e = self.sim.robots[r]
                        e.x, e.y, e.yaw = float(b[0]) - tx, float(b[1]) - ty, rumbos[i]
                        e.rpm_izq = e.rpm_der = 0.0
                        e.rpm_izq_ruedas = e.rpm_der_ruedas = 0.0
                        e.en_camino.clear()
                    e = self.sim.robots[demo.ID_ROBOT_OBSTACULO]
                    e.x, e.y = float(objetivo[0]) - tx, float(objetivo[1]) - ty
                    e.yaw = rumbo if rumbo is not None else 0.3
                    e.rpm_izq = e.rpm_der = 0.0
                    e.rpm_izq_ruedas = e.rpm_der_ruedas = 0.0
                    e.en_camino.clear()
                time.sleep(0.6)
            return ""

        return ses.Contexto(sesion="prueba_paradas",
                            id_robot=demo.ID_ROBOT_OBSTACULO,
                            marcador=demo.ID_MARCADOR_OBSTACULO,
                            simulador=True, preguntar=preguntar)

    def _sesion(self, respuesta: str, **kw) -> Tuple[Dict[str, Any], str]:
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            r = demo.sesion_demo(self._ctx(respuesta), "L2", decisiones=50, **kw)
        return r, salida.getvalue()

    def _tomas_csv(self) -> List[Dict[str, str]]:
        import csv as _csv
        ruta = sorted(self.tmp.glob("*L2_tomas*.csv"))[-1]
        with open(ruta, newline="", encoding="utf-8") as fh:
            return list(_csv.DictReader(fh))

    def test_contacto_detiene_la_sesion(self) -> None:
        self._guion([_toma_guion(d_min_obst_medida=0.12), _toma_guion()])
        # "si" NO es una "s": termina la sesión.
        r, salida = self._sesion("si", tomas=3, intentos_max=5)
        self.assertEqual(r["veredicto"], "DETENIDA", r["detalle"])
        self.assertEqual(len(r["tomas"]), 1)
        self.assertIn("CONTACTO", r["tomas"][0]["regla_parada"])
        self.assertEqual(r["tomas"][0]["parada_respuesta"], "detenida")
        self.assertEqual(len(self.preguntas_parada), 1)
        # El obstáculo quedó ANDANDO al terminar la toma: se pregunta con
        # todo frenado sólo si la regla mandó la detención.
        self.assertEqual(self.detenidos_al_preguntar, [True])
        self.assertIn("detención de los robots confirmada", salida)
        self.assertEqual(r["tomas"][0]["parada_detencion_sin_confirmar"], "")
        # La línea de la toma dice por qué no vale para la demo.
        self.assertIn("NO VÁLIDA PARA LA DEMO (agente a 0.120 m", salida)
        self.assertIn("⛔ REGLA DE PARADA", salida)
        # La regla y la respuesta quedan en el CSV.
        fila = self._tomas_csv()[0]
        self.assertIn("CONTACTO", fila["regla_parada"])
        self.assertEqual(fila["parada_respuesta"], "detenida")

    def test_la_espera_late_y_sigue_frenando(self) -> None:
        self._guion([_toma_guion(d_min_obst_medida=0.12)])
        self.espera_s = 2.6
        r, _ = self._sesion("", tomas=1, intentos_max=2)
        self.assertEqual(r["veredicto"], "DETENIDA", r["detalle"])
        # Latido de 1 s durante los 2.6 s de espera.
        self.assertGreaterEqual(self.detener_durante_espera, 2)

    def test_cartel_avisa_si_no_se_pudo_frenar_al_obstaculo(self) -> None:
        def sin_enlace(canal) -> None:
            # Enlace del 7 perdido y sin forma de reabrirlo.
            with canal._cerrojo_envio:
                canal._obst_cerrado_a_proposito = True
                if canal._sock_obst is not None:
                    canal._sock_obst.close()
                canal._sock_obst = None
        self._guion([_toma_guion(d_min_obst_medida=0.12)],
                    antes_de_volver=sin_enlace)
        r, salida = self._sesion("", tomas=1, intentos_max=2)
        self.assertEqual(r["veredicto"], "DETENIDA", r["detalle"])
        self.assertIn("NO SE PUDO CONFIRMAR LA DETENCIÓN: obstáculo (robot 7)",
                      salida)
        self.assertNotIn("detención de los robots confirmada", salida)
        self.assertIn("obstáculo", r["tomas"][0]["parada_detencion_sin_confirmar"])

    def test_freno_en_dos_tomas_seguidas_detiene_la_sesion(self) -> None:
        self._guion([_toma_guion(), _toma_guion(frenos=1),
                     _toma_guion(frenos=2), _toma_guion()])
        r, _ = self._sesion("", tomas=4, intentos_max=6)
        self.assertEqual(r["veredicto"], "DETENIDA", r["detalle"])
        self.assertEqual(len(r["tomas"]), 3)
        self.assertEqual(r["tomas"][1]["regla_parada"], "")
        self.assertIn("FRENO", r["tomas"][2]["regla_parada"])
        self.assertEqual(len(self.preguntas_parada), 1)
        self.assertEqual(self.detenidos_al_preguntar, [True])

    def test_freno_con_una_colocacion_fallida_en_medio(self) -> None:
        # Intento 2 sin colocar: no corre, y la cadena de frenos sigue
        # entre las tomas CORRIDAS 1 y 3.
        self.sin_colocar = {2}
        self._guion([_toma_guion(frenos=1), _toma_guion(frenos=1)])
        r, _ = self._sesion("", tomas=3, intentos_max=5)
        self.assertEqual(r["veredicto"], "DETENIDA", r["detalle"])
        self.assertEqual([t["toma"] for t in r["tomas"]], [1, 2, 3])
        self.assertNotIn("decisiones", r["tomas"][1])
        self.assertIn("FRENO", r["tomas"][2]["regla_parada"])

    def test_aborto_del_obstaculo_detiene_la_sesion(self) -> None:
        motivo = "el obstáculo NO SE MUEVE: 1.5 s con orden de marcha"
        self._guion([_toma_guion(valido=0, motivo=f"OBSTÁCULO: {motivo}",
                                 obst_motivo_aborto=motivo), _toma_guion()])
        r, salida = self._sesion("", tomas=2, intentos_max=4)
        self.assertEqual(r["veredicto"], "DETENIDA", r["detalle"])
        self.assertEqual(len(r["tomas"]), 1)
        self.assertIn("ABORTO POR EL OBSTÁCULO", r["tomas"][0]["regla_parada"])
        self.assertIn("NO VÁLIDA (medición: OBSTÁCULO:", salida)
        self.assertEqual(self.detenidos_al_preguntar, [True])

    def test_enlace_que_cayo_y_se_reabrio_detiene_la_sesion(self) -> None:
        def reconecto(canal) -> None:
            canal.obstaculo_reconexiones += 1
        self._guion([_toma_guion(), _toma_guion()], antes_de_volver=reconecto)
        r, _ = self._sesion("", tomas=2, intentos_max=3)
        self.assertEqual(r["veredicto"], "DETENIDA", r["detalle"])
        self.assertEqual(r["tomas"][0]["obst_enlace_cayo"], 1)
        self.assertIn("ENLACE DEL OBSTÁCULO", r["tomas"][0]["regla_parada"])

    def test_con_s_explicita_sigue(self) -> None:
        self._guion([_toma_guion(d_min_obst_medida=0.12), _toma_guion()])
        r, _ = self._sesion(" S ", tomas=1, intentos_max=3)
        self.assertEqual(r["veredicto"], "OK", r["detalle"])
        self.assertEqual(len(r["tomas"]), 2)
        self.assertEqual(r["tomas"][0]["parada_respuesta"], "siguió")
        self.assertEqual(r["tomas"][1]["regla_parada"], "")

    def test_intento_inicial_sigue_semillas_y_numeracion(self) -> None:
        from coordinador_enjambre import SEMILLAS_LOTE
        self._guion([_toma_guion(), _toma_guion()])
        r, salida = self._sesion("", tomas=1, intentos_max=5, intento_inicial=4)
        self.assertEqual(r["veredicto"], "OK", r["detalle"])
        self.assertEqual(r["tomas"][0]["toma"], 4)
        self.assertEqual(self.semillas, [SEMILLAS_LOTE[3]])
        self.assertIn("REANUDACIÓN", salida)
        # En el borde: el último intento permitido corre, uno solo.
        r, _ = self._sesion("", tomas=3, intentos_max=5, intento_inicial=5)
        self.assertEqual([t["toma"] for t in r["tomas"]], [5])
        self.assertEqual(self.semillas[-1], SEMILLAS_LOTE[4])
        for malo in (0, 6):
            with self.assertRaises(ValueError):
                demo.sesion_demo(self._ctx(""), "L2", intentos_max=5,
                                 intento_inicial=malo)


class PruebaResumenL0(BaseSim):
    """La L0 deja su resumen en un archivo, en todos los caminos."""

    def _ctx(self, preguntar=lambda _m: ""):
        import sesion_robotat as ses
        return ses.Contexto(sesion="prueba_l0", id_robot=demo.ID_ROBOT_OBSTACULO,
                            marcador=demo.ID_MARCADOR_OBSTACULO,
                            simulador=True, preguntar=preguntar)

    def _resumen(self) -> Dict[str, str]:
        import csv as _csv
        rutas = sorted(self.tmp.glob("*L0_resumen*.csv"))
        self.assertEqual(len(rutas), 1)
        with open(rutas[0], newline="", encoding="utf-8") as fh:
            filas = list(_csv.DictReader(fh))
        self.assertEqual(len(filas), 1)
        return filas[0]

    def _levantar(self) -> None:
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        self.levantar_sim(self.poses_lejos(), (p0[0], p0[1], r0))

    def test_l0_normal_escribe_resumen(self) -> None:
        self._levantar()
        with _silencio():
            r = demo.sesion_l0(self._ctx(), arranques=1, marcha_s=3.0,
                               pausa_s=0.5)
        f = self._resumen()
        self.assertEqual(f["veredicto"], r["veredicto"])
        self.assertEqual(int(f["arranques_ok"]), r["arranques_ok"])
        self.assertEqual(int(f["arranques_pedidos"]), 1)
        self.assertAlmostEqual(float(f["error_radial_max"]),
                               r["error_radial_max"], places=12)

    def test_l0_sin_conexion_de_ruedas_escribe_fallo(self) -> None:
        # Un robot que no es agente ni obstáculo no existe en este simulador:
        # el enlace de ruedas no abre.
        agentes = {a.id_robot for a in cfg.MAPEO_AGENTES.values()}
        libre = next(r for r in range(1, 17) if r not in agentes
                     and r not in (demo.ID_ROBOT_OBSTACULO, demo.ID_ROBOT_RESERVA))
        self._levantar()
        with _silencio():
            r = demo.sesion_l0(self._ctx(), arranques=1, id_robot=libre,
                               id_marcador=demo.ID_MARCADOR_OBSTACULO)
        self.assertEqual(r["veredicto"], "FALLO")
        self.assertIn(f"no se pudo conectar (ruedas del robot {libre})", r["detalle"])
        f = self._resumen()
        self.assertEqual(f["veredicto"], "FALLO")
        self.assertIn("no se pudo conectar", f["detalle"])
        self.assertEqual(int(f["arranques_corridos"]), 0)

    def test_l0_aborto_por_error_radial_lo_guarda(self) -> None:
        from unittest import mock
        self._levantar()
        with mock.patch.object(demo, "ley_seguimiento_circulo",
                               lambda p, par, v_ref: (0.0, 0.0, 0.2)), \
                _silencio():
            r = demo.sesion_l0(self._ctx(), arranques=2)
        self.assertEqual(r["veredicto"], "FALLO")
        self.assertIn("error radial", r["detalle"])
        f = self._resumen()
        self.assertEqual(f["veredicto"], "FALLO")
        self.assertAlmostEqual(float(f["error_radial_aborto"]), 0.2)
        time.sleep(0.05)
        self.assertTrue(self.sim.todos_detenidos())

    def test_l0_ctrl_c_escribe_resumen_y_propaga(self) -> None:
        self._levantar()

        def corta(_m):
            raise KeyboardInterrupt
        with _silencio(), self.assertRaises(KeyboardInterrupt):
            demo.sesion_l0(self._ctx(corta), arranques=1)
        f = self._resumen()
        self.assertEqual(f["veredicto"], "FALLO")
        self.assertIn("interrumpida (KeyboardInterrupt", f["detalle"])


class PruebaAnalizadorSesion(unittest.TestCase):
    """`analizar_sesion_demo` junta una sesión reanudada e informa paradas."""

    def test_junta_dos_csv_e_informa_paradas(self) -> None:
        import analizar_sesion_demo as A
        tmp = Path(tempfile.mkdtemp(prefix="demo_analizador_"))
        try:
            columnas = ["toma", "modo", "valido", "valido_demo", "decisiones",
                        "d_min_obst_medida", "frenos", "obst_recorrido_m",
                        "motivo", "motivo_demo", "regla_parada",
                        "parada_respuesta"]
            a = tmp / "s1_L2_tomas.csv"
            b = tmp / "s2_L2_tomas.csv"
            # La segunda sesión se pasa primero: el resumen ordena por toma.
            b.write_text(",".join(columnas) + "\n"
                         "3,L2,0,0,200,0.14,0,1.0,OBSTÁCULO: y,toma no válida,,\n"
                         "4,L1,1,1,500,0.33,0,2.5,,,,\n", encoding="utf-8")
            a.write_text(",".join(columnas) + "\n"
                         "1,L2,1,1,500,0.30,0,2.4,,,,\n"
                         "2,L2,1,0,500,0.12,0,2.4,,agente a 0.120 m,CONTACTO: x,detenida\n",
                         encoding="utf-8")
            with _silencio():
                r = A.resumir([b, a])
            self.assertEqual((r["corridas"], r["validas"], r["validas_demo"]),
                             (4, 3, 2))
            texto = (tmp / "s2_L2_combinado_resumen.txt").read_text(encoding="utf-8")
            self.assertIn("REGLAS DE PARADA DISPARADAS: 1", texto)
            self.assertIn("toma 2: CONTACTO: x → detenida", texto)
            self.assertIn("CONTACTO EN TOMAS NO VÁLIDAS PARA LA MEDICIÓN: toma 3",
                          texto)
            self.assertIn("los CSV mezclan modos", texto)
            # Una parada de la COLOCACIÓN (fila sin decisiones) también cuenta.
            c = tmp / "s3_L2_tomas.csv"
            c.write_text(",".join(columnas) + "\n"
                         "5,L2,0,0,,,,,colocación: CONTACTO x,,CONTACTO x,detenida\n",
                         encoding="utf-8")
            with _silencio():
                A.resumir([c])
            texto3 = (tmp / "s3_L2_resumen.txt").read_text(encoding="utf-8")
            self.assertIn("REGLAS DE PARADA DISPARADAS: 1", texto3)
            tabla = texto.split("toma válida demo")[1].splitlines()[1:5]
            self.assertEqual([ln.split()[0] for ln in tabla], ["1", "2", "3", "4"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

# =============================================================================
# COLOCACIÓN AUTOMÁTICA, FASE B (2026-10-07, OK de José)
# =============================================================================

import threading as _threading

import colocacion_con_obstaculo as C
from simulador_para_colocacion import (SimuladorZonaMuerta,
                                       fallas_con_retardo_por_robot)


class PruebaGeometriaColocacion(unittest.TestCase):
    """Funciones puras de `colocacion_con_obstaculo`."""

    def test_proyeccion_y_envolvente(self) -> None:
        p, r = demo.punto_del_circulo(0.7)
        pr = C.proyeccion_al_circulo((p[0], p[1], r))
        np.testing.assert_allclose(pr[0], p, atol=1e-12)
        self.assertAlmostEqual(pr[2], 0.0, places=12)
        self.assertAlmostEqual(pr[3], 0.0, places=9)
        self.assertIsNone(C.proyeccion_al_circulo((1.55, 1.5, 0.0)))
        self.assertEqual(C.problemas_envolvente_obstaculo("L2", (p[0], p[1], r)), [])
        afuera = p + 0.07 * (p - np.array(demo.CENTRO_CIRCULO_ENV)) / 0.6
        self.assertTrue(C.problemas_envolvente_obstaculo("L2", (afuera[0], afuera[1], r)))
        self.assertTrue(C.problemas_envolvente_obstaculo(
            "L2", (p[0], p[1], r + math.radians(30))))
        self.assertEqual(C.problemas_envolvente_obstaculo("L1", (1.55, 1.5, 0.3)), [])
        self.assertTrue(C.problemas_envolvente_obstaculo("L1", (1.6, 1.5, 0.3)))

    def test_objetivo_del_obstaculo(self) -> None:
        o, r, origen = C.objetivo_obstaculo("L1", (2.0, 2.0, 0.0), 420000)
        self.assertEqual((origen, r), ("centro", None))
        p, rr = demo.punto_del_circulo(2.0)
        o, r, origen = C.objetivo_obstaculo("L2", (p[0], p[1], rr), 420000)
        self.assertEqual(origen, "proyeccion")
        np.testing.assert_allclose(o, p, atol=1e-12)
        o, r, origen = C.objetivo_obstaculo("L2", (1.5, 1.5, 0.0), 420000)
        self.assertEqual(origen, "semilla")
        p2, r2 = demo.arranque_obstaculo(420000, "L2")
        np.testing.assert_allclose(o, p2, atol=1e-12)

    def test_blancos_a_065_del_obstaculo(self) -> None:
        for k in range(30):
            p, _r = demo.punto_del_circulo(0.3 * k)
            b = C.sortear_blancos_lejos(5, 420000 + k, p)
            self.assertTrue(all(float(np.linalg.norm(q - p)) >= 0.65
                                for q in b.values()))
            b2 = C.sortear_blancos_lejos(5, 420000 + k, p)
            for i in b:
                np.testing.assert_array_equal(b[i], b2[i])

    def test_rodeo(self) -> None:
        o = (1.5, 1.5)
        # Tramo que cruza el disco: rodeo por el arco corto, sobre 0.55 m.
        w, s, m = C.meta_de_rodeo((0.7, 1.45, 0.0), (2.3, 1.5), o)
        self.assertIsNotNone(w)
        self.assertAlmostEqual(float(np.linalg.norm(w - np.array(o))),
                               C.RADIO_RODEO_M, places=9)
        # Desde la izquierda y un poco abajo, el arco corto es el
        # antihorario, que pasa POR DEBAJO del obstáculo.
        self.assertEqual(s, 1)
        self.assertLess(float(w[1]), 1.5)
        # Pegajoso: si se le pide el otro sentido y es posible, lo respeta.
        w2, s2, _ = C.meta_de_rodeo((0.7, 1.45, 0.0), (2.3, 1.5), o, -1)
        self.assertEqual(s2, -1)
        self.assertGreater(float(w2[1]), 1.5)
        # La métrica baja mientras avanza alrededor.
        _w, _s, m2 = C.meta_de_rodeo((1.0, 1.2, 0.0), (2.3, 1.5), o, 1)
        self.assertLess(m2, m)
        # Tramo libre: sin rodeo, métrica = distancia.
        w3, s3, m3 = C.meta_de_rodeo((0.7, 0.4, 0.0), (2.3, 0.4), o)
        self.assertIsNone(w3)
        self.assertAlmostEqual(m3, 1.6, places=9)

    def test_fila_fija_es_la_del_exp_o(self) -> None:
        from colocacion_autonoma import FiltroColocacion
        f = FiltroColocacion()
        pose = np.array([1.0, 1.2, 0.4])
        p_o = np.array([1.5, 1.5])
        fila = C.fila_obstaculo_fijo(f, pose, p_o)
        mira = pose[:2] + 0.05 * np.array([math.cos(0.4), math.sin(0.4)])
        dist = float(np.linalg.norm(mira - p_o))
        self.assertAlmostEqual(fila.h, dist - 0.33, places=12)
        n = (mira - p_o) / dist
        G = f._matriz_G(0.4)
        np.testing.assert_allclose(fila.c, n @ G, atol=1e-12)
        # Ya violada: "no empeorar" (h recortado a 0).
        cerca = C.fila_obstaculo_fijo(f, np.array([1.3, 1.5, 0.0]), p_o)
        self.assertEqual(cerca.h, 0.0)

    def test_problemas_tras_colocar(self) -> None:
        inf = C.InformeColocacionObstaculo(quietos=True)
        blancos = {i: np.array([0.5 + 0.5 * i, 0.5]) for i in range(5)}
        poses = {i: np.array([b[0], b[1], 0.0]) for i, b in blancos.items()}
        p, r = demo.punto_del_circulo(1.0)
        self.assertEqual(C.problemas_tras_colocar(
            inf, poses, blancos, "L2", (p[0], p[1], r), 5), [])
        inf2 = C.InformeColocacionObstaculo(quietos=False,
                                            abandonados={2: "marcador congelado"})
        poses[3] = np.array([blancos[3][0] + 0.13, 0.5, 0.0])
        txt = " · ".join(C.problemas_tras_colocar(
            inf2, poses, blancos, "L2", (1.5, 1.5, 0.0), 5))
        for esperado in ("marcador congelado", "quedaron quietos",
                         "agente 3", "fuera del círculo"):
            self.assertIn(esperado, txt)


class PruebaSupervisorQuietoConectado(unittest.TestCase):
    """L1 con el obstáculo ENCENDIDO (opción (b)): frenado y vigilado."""

    def _correr(self, v, conectado: bool, caido: bool = False,
                segundos: float = 3.0):
        fuente = _FuenteFalsa(np.array([1.5, 1.5, 0.3]), np.asarray(v, float))
        canal = _CanalFalso()
        canal.obstaculo_caido = caido
        sup = demo.SupervisorObstaculo(fuente, canal, modo="quieto",
                                       vigilar_congelamiento=False,
                                       quieto_conectado=conectado)
        mandos = []
        for k in range(int(segundos / 0.1)):
            with _silencio():
                mandos.append(sup.paso({}, set(), 1.0, 100.0 + 0.1 * k, k))
            if sup.motivo_aborto:
                return sup, canal, mandos, 0.1 * k
        return sup, canal, mandos, None

    def test_quieto_conectado_que_se_mueve_es_no_frena(self) -> None:
        sup, canal, mandos, t = self._correr([0.05, 0.0], conectado=True)
        self.assertIn("NO FRENA", sup.motivo_aborto)
        self.assertGreaterEqual(t, demo.T_VERIFICACION_OBEDIENCIA_S - 1e-9)
        self.assertGreaterEqual(canal.detenciones, 1)
        self.assertTrue(all(m == (0.0, 0.0) for m in canal.mandos))

    def test_quieto_conectado_quieto_no_aborta_y_se_lo_frena(self) -> None:
        sup, canal, mandos, t = self._correr([0.0, 0.0], conectado=True)
        self.assertIsNone(sup.motivo_aborto)
        self.assertEqual(set(mandos), {(0.0, 0.0)})

    def test_quieto_conectado_enlace_caido_aborta(self) -> None:
        sup, *_ = self._correr([0.0, 0.0], conectado=True, caido=True)
        self.assertIn("enlace", sup.motivo_aborto)

    def test_quieto_apagado_es_el_de_siempre(self) -> None:
        sup, canal, mandos, t = self._correr([0.05, 0.0], conectado=False,
                                             caido=True)
        self.assertIsNone(sup.motivo_aborto)
        self.assertEqual(set(mandos), {None})
        self.assertEqual(canal.mandos, [])
        with self.assertRaises(ValueError):
            demo.SupervisorObstaculo(_FuenteFalsa(np.zeros(3), None),
                                     _CanalFalso(), modo="movil",
                                     quieto_conectado=True)


class BaseColocacion(BaseSim):
    """Simulador con zona muerta y retardo por robot; colocación directa."""

    def levantar_zm(self, poses_env, obst, tau_agentes: float,
                    tau_obstaculo: float, **kw_fallas) -> None:
        mapeo = {r: cfg.MAPEO_AGENTES[i].id_marcador
                 for i, r in enumerate(self.robots)}
        mapeo[demo.ID_ROBOT_OBSTACULO] = demo.ID_MARCADOR_OBSTACULO
        tx, ty = cfg.TRASLACION_X_M, cfg.TRASLACION_Y_M
        lab = {self.robots[i]: (x - tx, y - ty, th)
               for i, (x, y, th) in poses_env.items()}
        lab[demo.ID_ROBOT_OBSTACULO] = (obst[0] - tx, obst[1] - ty, obst[2])
        fallas = fallas_con_retardo_por_robot(
            {demo.ID_ROBOT_OBSTACULO: tau_obstaculo}, tau_agentes, **kw_fallas)
        self.sim = SimuladorZonaMuerta(mapeo, lab, fallas,
                                       puerto_poses=self.puerto_poses,
                                       puerto_base=self.puerto_ruedas)
        self.sim.iniciar()

    def armar_col(self, conectar: bool = True):
        with _silencio():
            fuente, canal, entorno = demo.construir_con_obstaculo(
                5, conectar_obstaculo=conectar)
        self.entorno = entorno
        return fuente, canal

    def colocar(self, fuente, canal, blancos, rumbos, **kw):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            inf = C.colocar_alrededor_del_obstaculo(fuente, canal, blancos,
                                                    rumbos, 5, **kw)
        return inf, salida.getvalue()

    def teletransportar(self, rid: int, x: float, y: float) -> None:
        tx, ty = cfg.TRASLACION_X_M, cfg.TRASLACION_Y_M
        with self.sim._lock:
            e = self.sim.robots[rid]
            e.x, e.y = x - tx, y - ty

    def mover_obstaculo_a(self, v: float) -> None:
        """Le pone al obstáculo rpm de avance directamente (desobedece)."""
        rpm = v / self.sim._r * 60.0 / (2.0 * math.pi)
        with self.sim._lock:
            e = self.sim.robots[demo.ID_ROBOT_OBSTACULO]
            e.en_camino.clear()
            e.rpm_izq = e.rpm_der = e.rpm_izq_ruedas = e.rpm_der_ruedas = rpm

    #: Agente 0 con su blanco justo DETRÁS del obstáculo (en el centro); los
    #: otros cuatro ya en su blanco.
    POSES = {0: (0.75, 1.5, 0.0), 1: (0.5, 0.5, 0.0), 2: (2.5, 0.5, 0.0),
             3: (0.5, 2.5, 0.0), 4: (2.5, 2.5, 0.0)}
    BLANCOS = {0: np.array([2.25, 1.5]), 1: np.array([0.5, 0.5]),
               2: np.array([2.5, 0.5]), 3: np.array([0.5, 2.5]),
               4: np.array([2.5, 2.5])}
    RUMBOS = {i: 0.0 for i in range(5)}
    CENTRO = (1.5, 1.5, 0.3)


class PruebaColocacionConRetardoYZonaMuerta(BaseColocacion):
    """
    Criterio de la propuesta (§8): blanco detrás del obstáculo, zona muerta
    de rueda y retardos de 0.45/0.85 s (también todos en 0.85 s). Llegan
    todos, con rodeo, a > 0.15 m en la VERDAD del simulador, y quietos.
    """

    def _una(self, tau_ag: float, tau_ob: float) -> None:
        from correr_fase0_obstaculo import MonitorVerdad
        self.levantar_zm(self.POSES, self.CENTRO, tau_ag, tau_ob)
        fuente, canal = self.armar_col(conectar=True)
        mon = MonitorVerdad(self.sim, self.robots, demo.ID_ROBOT_OBSTACULO)
        mon.iniciar()
        try:
            inf, salida = self.colocar(fuente, canal, self.BLANCOS, self.RUMBOS)
        finally:
            mon.detener()
        self.assertEqual(inf.motivo_fin, "todos listos", salida[-800:])
        self.assertEqual(sorted(inf.listos), [0, 1, 2, 3, 4])
        self.assertGreaterEqual(inf.rodeos.get(0, 0), 1)
        self.assertGreater(min(mon.d_min_obst), 0.15)
        self.assertGreater(mon.d_min_pares, 0.15)
        self.assertTrue(inf.quietos)
        self.assertEqual(inf.parada, "")
        time.sleep(0.05)
        self.assertTrue(self.sim.todos_detenidos())

    def test_agentes_045_obstaculo_085(self) -> None:
        self._una(0.45, 0.85)

    def test_todos_085(self) -> None:
        self._una(0.85, 0.85)


class PruebaColocacionBarreraYReintentos(BaseColocacion):
    """
    Revisión de la Fase B: la BARRERA del obstáculo protege aunque el rodeo
    no actúe (y con eso la zona muerta llega a retener), el reintento cambia
    de lado, y el que no avanzaba primero se aleja.
    """

    def test_sin_rodeo_la_barrera_sola_mantiene_la_distancia(self) -> None:
        from unittest import mock
        from correr_fase0_obstaculo import MonitorVerdad
        self.levantar_zm(self.POSES, self.CENTRO, 0.85, 0.85)
        fuente, canal = self.armar_col(conectar=True)
        mon = MonitorVerdad(self.sim, self.robots, demo.ID_ROBOT_OBSTACULO)
        mon.iniciar()
        try:
            with mock.patch.object(
                    C, "meta_de_rodeo",
                    lambda p, b, o, s=None, q=(): (None, None, float(
                        np.linalg.norm(np.asarray(b)[:2] - np.asarray(p)[:2])))):
                inf, salida = self.colocar(fuente, canal, self.BLANCOS,
                                           self.RUMBOS, t_max_s=25.0)
        finally:
            mon.detener()
        self.assertEqual(inf.parada, "", salida[-600:])
        self.assertEqual(inf.abandonados.get(0), "no avanza")
        self.assertGreater(min(mon.d_min_obst), 0.25)
        # Nota (2026-10-07): ni bloqueado el QP deja órdenes dentro de la
        # zona muerta (retenciones del agente 0 = 0): la zona muerta de la
        # colocación no queda demostrada; en el ensayo de la sesión sí actuó.

    def test_el_reintento_rodea_por_el_otro_lado(self) -> None:
        self.levantar_zm(self.POSES, self.CENTRO, 0.45, 0.85)
        fuente, canal = self.armar_col(conectar=True)
        inf1, _ = self.colocar(fuente, canal, self.BLANCOS, self.RUMBOS)
        s1 = inf1.sentidos[0]
        # Vuelve al arranque y rodea forzado por el lado contrario.
        self.teletransportar(self.robots[0], *self.POSES[0][:2])
        with self.sim._lock:
            self.sim.robots[self.robots[0]].yaw = 0.0
        time.sleep(0.3)
        inf2, salida = self.colocar(fuente, canal, self.BLANCOS, self.RUMBOS,
                                    sentidos_previos={0: -s1})
        self.assertEqual(inf2.sentidos[0], -s1)
        self.assertEqual(inf2.motivo_fin, "todos listos", salida[-600:])

    def test_el_que_no_avanzaba_primero_se_aleja(self) -> None:
        self.levantar_zm(self.POSES, self.CENTRO, 0.45, 0.85)
        fuente, canal = self.armar_col(conectar=True)
        inf, salida = self.colocar(fuente, canal, self.BLANCOS, self.RUMBOS,
                                   alejar=[0])
        self.assertEqual(inf.motivo_fin, "todos listos", salida[-600:])

    def test_rodeo_esquiva_a_un_agente_quieto(self) -> None:
        o = (1.5, 1.5)
        # Sin quietos, el arco corto (antihorario, por abajo).
        _w, s, _m = C.meta_de_rodeo((0.7, 1.45, 0.0), (2.3, 1.5), o)
        self.assertEqual(s, 1)
        # Un agente quieto justo debajo del obstáculo: va por arriba.
        _w, s, _m = C.meta_de_rodeo((0.7, 1.45, 0.0), (2.3, 1.5), o,
                                    quietos=[np.array([1.5, 0.95])])
        self.assertEqual(s, -1)


class PruebaFallasDelObstaculoEnLaColocacion(BaseColocacion):
    """Fallas inyectadas con el obstáculo presente (propuesta §8)."""

    def _con_falla(self, falla, despues_s: float = 2.0, conectar: bool = True,
                   **kw):
        fuente, canal = self.armar_col(conectar=conectar)
        if falla is not None:
            _threading.Timer(despues_s, falla).start()
        inf, salida = self.colocar(fuente, canal, self.BLANCOS, self.RUMBOS,
                                   **kw)
        time.sleep(0.05)
        return inf, salida

    def test_enlace_del_obstaculo_que_cae(self) -> None:
        self.levantar_zm(self.POSES, self.CENTRO, 0.45, 0.85,
                         robots_que_caen_tras={demo.ID_ROBOT_OBSTACULO: 25},
                         caidos_no_reaceptan=True)
        inf, salida = self._con_falla(None)
        self.assertIn("ABORTO POR EL OBSTÁCULO", inf.parada)
        self.assertIn("enlace de ruedas del obstáculo", inf.parada)
        self.assertNotEqual(inf.motivo_fin, "todos listos")
        self.assertTrue(self.sim.todos_detenidos())

    def test_marcador_del_obstaculo_perdido(self) -> None:
        self.levantar_zm(self.POSES, self.CENTRO, 0.45, 0.85)
        frenado: List[bool] = []

        def perder() -> None:
            self.sim.fallas.marcadores_perdidos.add(demo.ID_MARCADOR_OBSTACULO)
            # Con la pose vencida los agentes reciben (0,0) EN EL ACTO, mucho
            # antes de la parada por "sin pose" (2 s).
            _threading.Timer(0.6, lambda: frenado.append(
                self.sim.rpm_de_robot(self.robots[0]) == (0.0, 0.0))).start()
        inf, salida = self._con_falla(perder)
        self.assertIn("sin pose fresca del obstáculo", inf.parada)
        self.assertEqual(frenado, [True])
        self.assertTrue(self.sim.todos_detenidos())

    def test_marcador_del_obstaculo_congelado(self) -> None:
        self.levantar_zm(self.POSES, self.CENTRO, 0.45, 0.85,
                         ruido_pos_m=0.001, modo_marcador_perdido="congelado")
        inf, salida = self._con_falla(
            lambda: self.sim.fallas.marcadores_perdidos.add(
                demo.ID_MARCADOR_OBSTACULO), vigilar_congelamiento=True)
        self.assertIn("CONGELADO", inf.parada)
        self.assertTrue(self.sim.todos_detenidos())

    def test_obstaculo_que_se_mueve_es_no_frena(self) -> None:
        self.levantar_zm(self.POSES, self.CENTRO, 0.45, 0.85)
        inf, salida = self._con_falla(lambda: self.mover_obstaculo_a(0.05),
                                      conectar=False)
        self.assertIn("NO FRENA", inf.parada)
        self.assertIn("LEVANTARLO", salida)
        self.assertTrue(all(self.sim.rpm_de_robot(r) == (0.0, 0.0)
                            for r in self.robots))

    def test_obstaculo_conectado_que_no_obedece_es_no_frena(self) -> None:
        """Conectado (como en la sesión automática), recibe (0,0) en cada
        ciclo pero no obedece: un hilo le repone la marcha cada 50 ms."""
        self.levantar_zm(self.POSES, self.CENTRO, 0.45, 0.85)
        parar = _threading.Event()

        def desobedece() -> None:
            while not parar.is_set():
                self.mover_obstaculo_a(0.05)
                parar.wait(0.05)
        hilo = _threading.Thread(target=desobedece, daemon=True)
        try:
            inf, salida = self._con_falla(hilo.start, despues_s=2.0)
        finally:
            parar.set()
        self.assertIn("NO FRENA", inf.parada)
        self.assertTrue(all(self.sim.rpm_de_robot(r) == (0.0, 0.0)
                            for r in self.robots))

    def test_contacto_durante_la_colocacion(self) -> None:
        self.levantar_zm(self.POSES, self.CENTRO, 0.45, 0.85)
        rid = self.robots[1]
        inf, salida = self._con_falla(
            lambda: self.teletransportar(rid, 1.5, 1.38))
        self.assertIn("CONTACTO durante la colocación", inf.parada)
        self.assertTrue(self.sim.todos_detenidos())

    def test_contacto_entre_agentes_durante_la_colocacion(self) -> None:
        self.levantar_zm(self.POSES, self.CENTRO, 0.45, 0.85)
        r1, r2 = self.robots[1], self.robots[2]
        inf, salida = self._con_falla(
            lambda: self.teletransportar(r2, 0.5, 0.62))
        self.assertIn("CONTACTO durante la colocación", inf.parada)
        self.assertIn(f"robots {r1} y {r2}", inf.parada)

    def test_contacto_antes_de_mover_a_nadie(self) -> None:
        poses = dict(self.POSES)
        poses[1] = (1.5, 1.38, 0.0)            # pegado al obstáculo
        self.levantar_zm(poses, self.CENTRO, 0.45, 0.85)
        inf, salida = self._con_falla(None)
        self.assertIn("antes de mover a nadie", inf.parada)

    def test_enlace_de_un_agente_que_cae(self) -> None:
        self.levantar_zm(self.POSES, self.CENTRO, 0.45, 0.85,
                         robots_que_caen_tras={self.robots[0]: 30},
                         caidos_no_reaceptan=True)
        inf, salida = self._con_falla(None)
        self.assertIn("ENLACE DE RUEDAS CAÍDO durante la colocación",
                      inf.parada)
        self.assertIn(str(self.robots[0]), inf.parada)

    def test_obstaculo_invisible_al_empezar_nadie_se_mueve(self) -> None:
        self.levantar_zm(self.POSES, self.CENTRO, 0.45, 0.85,
                         marcadores_perdidos={demo.ID_MARCADOR_OBSTACULO})
        p0 = self.sim.pose_de_robot(self.robots[0])
        inf, salida = self._con_falla(None)
        self.assertIn("sin pose fresca del obstáculo", inf.parada)
        p1 = self.sim.pose_de_robot(self.robots[0])
        self.assertLess(math.hypot(p1[0] - p0[0], p1[1] - p0[1]), 1e-9)


class PruebaObstaculoQuietoAntesDeColocar(BaseColocacion):
    """
    Ensayo L2 con τ = 0.85 s (2026-10-07): al terminar una toma el obstáculo
    sigue andando hasta su retardo; sin esperar a que quede quieto, la
    colocación lo tomaba por "NO FRENA" (falso positivo).
    """

    def test_el_que_viene_andando_queda_quieto_y_no_es_no_frena(self) -> None:
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        self.levantar_zm(self.poses_lejos(), (p0[0], p0[1], r0), 0.85, 0.85)
        fuente, canal = self.armar_col(conectar=True)
        canal.enviar_obstaculo(0.05, 0.0)
        time.sleep(1.5)                   # andando (con 0.85 s de retardo)
        canal.enviar_obstaculo(0.0, 0.0)  # la orden de parada del fin de toma
        t0 = time.perf_counter()
        tipo, motivo, ref = C.esperar_obstaculo_quieto(fuente, canal, 5)
        self.assertIsNone(tipo, motivo)
        self.assertIsNotNone(ref)
        self.assertGreater(time.perf_counter() - t0, 0.5)   # esperó la inercia
        blancos = {i: np.array(q[:2]) for i, q in self.poses_lejos().items()}
        inf, salida = self.colocar(fuente, canal, blancos,
                                   {i: 0.0 for i in range(5)})
        self.assertEqual(inf.parada, "", salida[-600:])

    def test_el_que_no_frena_se_detecta(self) -> None:
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        self.levantar_zm(self.poses_lejos(), (p0[0], p0[1], r0), 0.45, 0.85)
        fuente, canal = self.armar_col(conectar=False)
        self.mover_obstaculo_a(0.05)
        tipo, motivo, _ = C.esperar_obstaculo_quieto(fuente, canal, 5,
                                                     t_max_s=2.0)
        self.assertEqual(tipo, "mueve")
        self.assertIn("NO FRENA", motivo)

    def test_lazo_lento_igual_confirma_la_quietud(self) -> None:
        """Revisión: con 0.1 s + costo de la vuelta, una ventana de
        0.30–0.35 s podía quedar sin muestras y dar NO FRENA con v = 0."""
        from unittest import mock
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        self.levantar_zm(self.poses_lejos(), (p0[0], p0[1], r0), 0.45, 0.85)
        fuente, canal = self.armar_col(conectar=True)
        orig = C._leer

        def lento(f, n):
            time.sleep(0.03)
            return orig(f, n)
        with mock.patch.object(C, "_leer", lento):
            tipo, motivo, _ = C.esperar_obstaculo_quieto(fuente, canal, 5)
        self.assertIsNone(tipo, motivo)

    def test_sin_pose_no_es_regla_de_parada(self) -> None:
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        self.levantar_zm(self.poses_lejos(), (p0[0], p0[1], r0), 0.45, 0.85,
                         marcadores_perdidos={demo.ID_MARCADOR_OBSTACULO})
        fuente, canal = self.armar_col(conectar=True)
        tipo, motivo, _ = C.esperar_obstaculo_quieto(fuente, canal, 5,
                                                     t_max_s=1.0)
        self.assertEqual(tipo, "sin_pose")


class PruebaSesionColocacionAutomatica(BaseColocacion):
    """`sesion_demo(colocacion="auto")` completa contra el simulador."""

    def setUp(self) -> None:
        super().setUp()
        from unittest import mock
        self._parche = mock.patch.object(demo.atexit, "register",
                                         lambda f, *a, **k: f)
        self._parche.start()
        self._orig_obj = C.objetivo_obstaculo
        self.ultimo_objetivo: Dict[str, Any] = {}

        def objetivo(modo, pose_o, semilla):
            r = self._orig_obj(modo, pose_o, semilla)
            self.ultimo_objetivo["r"] = r
            return r
        C.objetivo_obstaculo = objetivo
        self.manos = 0
        self.al_enter_solos = None

    def tearDown(self) -> None:
        C.objetivo_obstaculo = self._orig_obj
        self._parche.stop()
        super().tearDown()

    def _ctx(self, respuesta_parada: str = ""):
        import sesion_robotat as ses

        def preguntar(m: str) -> str:
            if "¿Seguir con la sesión?" in m:
                return respuesta_parada
            if "Corregí lo de arriba" in m and getattr(self, "_reponer_marcador", False):
                self.sim.fallas.marcadores_perdidos.discard(
                    demo.ID_MARCADOR_OBSTACULO)
                self._reponer_marcador = False
                time.sleep(0.4)
                return ""
            if "Corregí lo de arriba" in m and "r" in self.ultimo_objetivo:
                # El "operador" coloca al obstáculo a mano en su punto.
                o, rumbo, _orig = self.ultimo_objetivo["r"]
                self.manos += 1
                tx, ty = cfg.TRASLACION_X_M, cfg.TRASLACION_Y_M
                with self.sim._lock:
                    e = self.sim.robots[demo.ID_ROBOT_OBSTACULO]
                    e.x, e.y = float(o[0]) - tx, float(o[1]) - ty
                    e.yaw = rumbo if rumbo is not None else 0.3
                time.sleep(0.4)
            if "van a ir SOLOS" in m and self.al_enter_solos is not None:
                _threading.Timer(1.5, self.al_enter_solos).start()
                self.al_enter_solos = None
            return ""
        return ses.Contexto(sesion="prueba_col", id_robot=demo.ID_ROBOT_OBSTACULO,
                            marcador=demo.ID_MARCADOR_OBSTACULO, simulador=True,
                            preguntar=preguntar)

    def _sesion(self, modo: str, respuesta: str = "", **kw):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            r = demo.sesion_demo(self._ctx(respuesta), modo, decisiones=50,
                                 colocacion="auto", **kw)
        return r, salida.getvalue()

    def test_l2_automatica_una_toma(self) -> None:
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        self.levantar_zm(self.poses_lejos(), (p0[0], p0[1], r0), 0.45, 0.85)
        r, salida = self._sesion("L2", tomas=1, intentos_max=1)
        self.assertEqual(r["veredicto"], "OK", r["detalle"] + salida[-1500:])
        t = r["tomas"][0]
        self.assertEqual(t["colocacion"], "auto")
        self.assertEqual(t["col_motivo"], "todos listos")
        self.assertEqual(t["col_obst_origen"], "proyeccion")
        self.assertEqual(self.manos, 0)
        import csv as _csv
        ruta = sorted(self.tmp.glob("*L2_tomas*.csv"))[-1]
        with open(ruta, newline="", encoding="utf-8") as fh:
            fila = next(_csv.DictReader(fh))
        for col in ("col_d_min_obst_m", "col_listos", "blanco_th_a0",
                    "col_reintentos"):
            self.assertIn(col, fila)

    def test_l2_automatica_dos_tomas_seguidas(self) -> None:
        """La colocación que sigue a una toma REAL: el obstáculo viene
        andando y con 0.85 s de retardo (el falso NO FRENA del ensayo)."""
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        self.levantar_zm(self.poses_lejos(), (p0[0], p0[1], r0), 0.85, 0.85)
        r, salida = self._sesion("L2", tomas=2, intentos_max=2)
        self.assertEqual(r["veredicto"], "OK", r["detalle"] + salida[-1500:])
        self.assertNotIn("NO FRENA", salida)
        self.assertEqual([t["col_obst_origen"] for t in r["tomas"]],
                         ["proyeccion", "proyeccion"])

    def test_sin_pose_del_obstaculo_al_empezar_vuelve_al_operador(self) -> None:
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        self.levantar_zm(self.poses_lejos(), (p0[0], p0[1], r0), 0.45, 0.85,
                         marcadores_perdidos={demo.ID_MARCADOR_OBSTACULO})
        # El "operador" lo hace visible (y lo deja en su punto).
        self._reponer_marcador = True
        r, salida = self._sesion("L2", tomas=1, intentos_max=1)
        self.assertEqual(r["veredicto"], "OK", r["detalle"] + salida[-1500:])
        self.assertIn("obstáculo: sin pose fresca", salida)
        self.assertNotIn("REGLA DE PARADA", salida)

    def test_l1_automatica_con_el_obstaculo_conectado(self) -> None:
        self.levantar_zm(self.poses_lejos(), self.CENTRO, 0.45, 0.85)
        r, salida = self._sesion("L1", tomas=1, intentos_max=1)
        self.assertEqual(r["veredicto"], "OK", r["detalle"] + salida[-1500:])
        self.assertEqual(r["tomas"][0]["obst_modo"], "quieto")
        self.assertIn("ENCENDIDO, conectado", salida)
        # El supervisor de la toma es el de quieto_conectado: le manda (0,0)
        # en cada decisión (con el robot apagado, v_cmd queda vacío).
        import csv as _csv
        ruta = sorted(self.tmp.glob("*L1_obstaculo*.csv"))[-1]
        with open(ruta, newline="", encoding="utf-8") as fh:
            vs = {f["v_cmd"] for f in _csv.DictReader(fh)}
        self.assertEqual(vs, {"0.0"})
        self.assertGreater(
            self.sim.robots[demo.ID_ROBOT_OBSTACULO].comandos_recibidos, 0)
        self.assertEqual(self.sim.rpm_de_robot(demo.ID_ROBOT_OBSTACULO),
                         (0.0, 0.0))

    def test_obstaculo_fuera_de_la_envolvente_se_coloca_a_mano(self) -> None:
        self.levantar_zm(self.poses_lejos(), (1.5, 1.15, 0.0), 0.45, 0.85)
        r, salida = self._sesion("L2", tomas=1, intentos_max=1)
        self.assertEqual(r["veredicto"], "OK", r["detalle"] + salida[-1500:])
        self.assertEqual(self.manos, 1)
        self.assertIn("colocalo A MANO", salida)

    def test_contacto_en_la_colocacion_detiene_la_sesion(self) -> None:
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        self.levantar_zm(self.poses_lejos(), (p0[0], p0[1], r0), 0.45, 0.85)
        rid = self.robots[4]
        self.al_enter_solos = lambda: self.teletransportar(
            rid, float(p0[0]), float(p0[1]) + 0.12)
        r, salida = self._sesion("L2", tomas=2, intentos_max=3)
        self.assertEqual(r["veredicto"], "DETENIDA", r["detalle"])
        t = r["tomas"][0]
        self.assertIn("CONTACTO durante la colocación", t["regla_parada"])
        self.assertTrue(t["motivo"].startswith("colocación:"))
        self.assertEqual(t["parada_respuesta"], "detenida")


class PruebaOffsetDeLaL0(unittest.TestCase):
    """Decisión de José (2026-10-07): la L0 mide el offset del 4 y la L1/L2
    no arranca si difiere > 3° de la tabla."""

    @staticmethod
    def _filas(error_deg: float, n: int = 60):
        return [{"arranque": 0, "t": 2.0 + 0.1 * k, "x": 0.005 * k,
                 "y": 0.0, "th": -math.radians(error_deg), "v": 0.05,
                 "w": 0.0} for k in range(n)]

    def test_estima_la_diferencia_y_su_signo(self) -> None:
        d, n = demo.estimar_error_offset(self._filas(5.0))
        self.assertAlmostEqual(d, 5.0, places=6)
        self.assertGreaterEqual(n, demo.OFFSET_MUESTRAS_MIN)
        d, n = demo.estimar_error_offset(self._filas(-2.0))
        self.assertAlmostEqual(d, -2.0, places=6)
        # La patada y el enganche (t < 2 s) no cuentan.
        filas = self._filas(5.0, n=20)       # t de 0 a 1.9 s
        for f in filas:
            f["t"] -= 2.0
        self.assertEqual(demo.estimar_error_offset(filas)[1], 0)

    def test_l0_habilita_o_frena(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="demo_l0_"))
        try:
            ok, motivo = demo.l0_habilita(4, tmp)
            self.assertFalse(ok)
            self.assertIn("correr antes la L0", motivo)

            def resumen(nombre, veredicto, d, n):
                demo.escribir_csv(tmp / nombre, [{
                    "veredicto": veredicto, "detalle": "x", "robot": 4,
                    "marcador": 4, "offset_dif_deg": d, "offset_pares": n}])
            resumen("20261007_100000_L0_resumen.csv", "OK", 4.2, 40)
            ok, motivo = demo.l0_habilita(4, tmp)
            self.assertFalse(ok)
            self.assertIn("difiere +4.2°", motivo)
            self.assertIn("→", motivo)
            resumen("20261007_110000_L0_resumen.csv", "OK", 1.1, 40)
            self.assertTrue(demo.l0_habilita(4, tmp)[0])
            resumen("20261007_120000_L0_resumen.csv", "OK", 1.1, 5)
            self.assertFalse(demo.l0_habilita(4, tmp)[0])
            resumen("20261007_130000_L0_resumen.csv", "FALLO", 0.5, 40)
            self.assertFalse(demo.l0_habilita(4, tmp)[0])
            # Otro robot no cuenta.
            self.assertFalse(demo.l0_habilita(7, tmp)[0])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_main_no_arranca_la_l1_sin_l0(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="demo_l0_"))
        previo = demo.DIR_SALIDA_DEMO
        demo.DIR_SALIDA_DEMO = tmp
        try:
            with _silencio():
                codigo = demo.main(["--modo", "L1", "--robot-obstaculo", "4"])
            self.assertEqual(codigo, 6)
        finally:
            demo.DIR_SALIDA_DEMO = previo
            shutil.rmtree(tmp, ignore_errors=True)


class PruebaLineaDeComandos(unittest.TestCase):

    def test_robot_del_obstaculo_obligatorio(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit):
            demo.main(["--modo", "L0"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
