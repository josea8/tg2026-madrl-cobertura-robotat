"""
test_experimento_Q.py
=====================
Pruebas del Exp Q (§4.2 de `tesis/PROPUESTA_expO_dinamico.md`), antes de las
1000 corridas del control bit a bit:

  · la fila F1 con v = 0 es la del Exp O bit a bit, y con v ≠ 0 es la fórmula
    de la campaña (`demo_obstaculo_movil.py:1498-1519`) con k = 1, reescrita
    acá sin importar nada del coordinador;
  · trayectorias exactas, antihorarias, a 0,05 m/s;
  · máscara permanente: con trayectorias quietas, la del Exp O;
  · entorno nuevo con trayectorias quietas == `EntornoObstaculos`, paso a paso;
  · objetivos transparentes: idénticos al control en los 500 pasos;
  · contacto por empuje y por avance;
  · dos episodios completos del camino nuevo == sus filas del Exp O.

    python -B -m unittest test_experimento_Q -v

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
import sys
import unittest
from pathlib import Path

import numpy as np

_CARPETA = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import correr_experimento_Q as Q
from correr_experimento_O import (ALFA_CBF, ARENA, COMM_RADIUS, D_SEGURA, ELE_A,
                                  ESCENARIOS, MARGEN_OBS, MAX_STEPS, N_AGENTES,
                                  OMEGA_MAX, PESOS_TRIAL13, SEED_BASE, V_MAX,
                                  W_OMEGA, GestorEscape, barreras_obstaculos)
from entorno_obstaculos import RADIO_CHASIS, EntornoObstaculos, mascara_ocupada
from entorno_obstaculos_moviles import (EntornoObstaculosMoviles,
                                        TrayectoriaCircular, TrayectoriaQuieta,
                                        mascara_permanente, obstaculos_en)
from lib.filtro_cbf import FiltroCBFParedes

KW_ENV = dict(n_agents=N_AGENTES, arena_size=(ARENA, ARENA), max_steps=MAX_STEPS,
              comm_radius=COMM_RADIUS, reward_weights=PESOS_TRIAL13,
              domain_rand=False, seed=SEED_BASE, modo_borde="bloqueante")


def _filtro() -> FiltroCBFParedes:
    return FiltroCBFParedes(arena_size=(ARENA, ARENA), ele_a=ELE_A, alfa=ALFA_CBF,
                            d_segura=D_SEGURA, w_omega=W_OMEGA,
                            v_max=V_MAX, omega_max=OMEGA_MAX)


def _fila_campana_k1(filtro, pose, obst_k, v_o):
    """`demo_obstaculo_movil.py:1498-1519` (F1) con k = 1 y D = r + 0,18."""
    ox, oy, r = obst_k
    p_i = filtro._punto_de_mira(pose)
    G_i = filtro._matriz_G(float(pose[2]))
    delta = p_i - np.array([ox, oy])
    dist = float(np.linalg.norm(delta))
    normal = delta / dist
    c = normal @ G_i
    h = dist - (r + MARGEN_OBS)
    s = max(0.0, float(normal @ v_o), float(normal @ v_o))
    alfa = filtro.alfa
    capacidad = abs(float(c[0])) * filtro.v_max + abs(float(c[1])) * filtro.omega_max
    rhs = -alfa * h + s / 1.0
    if s == 0.0 and rhs <= 0.9 * capacidad:
        return c, h, False
    saturada = False
    if rhs > 0.9 * capacidad:
        rhs = 0.9 * capacidad
        saturada = True
    return c, -rhs / alfa, saturada


class PruebaFilaF1(unittest.TestCase):

    def setUp(self) -> None:
        self.rng = np.random.default_rng(20261019)
        self.filtro = _filtro()

    def _pose(self) -> np.ndarray:
        return np.array([self.rng.uniform(0.2, 2.8), self.rng.uniform(0.2, 2.8),
                         self.rng.uniform(-math.pi, math.pi)])

    def test_con_v_cero_es_la_fila_del_exp_o(self) -> None:
        for k in ("S1", "S2", "S3"):
            obst = ESCENARIOS[k]
            for _ in range(400):
                pose = self._pose()
                ref = barreras_obstaculos(self.filtro, pose, obst)
                vel = [np.zeros(2) for _ in obst]
                filas, info, sat = Q.filas_obstaculo_f1(self.filtro, pose, obst,
                                                       vel, True)
                self.assertEqual(sat, 0)
                self.assertEqual(len(filas), len(ref))
                for a, b in zip(filas, ref):
                    self.assertEqual(a.nombre, b.nombre)
                    self.assertEqual(a.h, b.h)
                    self.assertTrue(np.array_equal(a.c, b.c))
                self.assertTrue(all(s == 0.0 for _n, _h, s in info))

    def test_sin_termino_es_la_fila_del_exp_o_aunque_se_mueva(self) -> None:
        obst = ESCENARIOS["S2"]
        for _ in range(200):
            pose = self._pose()
            vel = [self.rng.uniform(-0.05, 0.05, size=2) for _ in obst]
            ref = barreras_obstaculos(self.filtro, pose, obst)
            filas, _info, _sat = Q.filas_obstaculo_f1(self.filtro, pose, obst,
                                                     vel, False)
            for a, b in zip(filas, ref):
                self.assertEqual(a.h, b.h)
                self.assertTrue(np.array_equal(a.c, b.c))

    def test_con_v_es_la_formula_de_la_campana(self) -> None:
        n_mov = n_sat = 0
        for k in ("S1", "S2", "S3"):
            obst = ESCENARIOS[k]
            for _ in range(400):
                pose = self._pose()
                vel = [self.rng.uniform(-0.6, 0.6, size=2) for _ in obst]
                filas, info, sat = Q.filas_obstaculo_f1(self.filtro, pose, obst,
                                                       vel, True)
                n_sat_esperadas = 0
                for fila, (_n, _hg, s) in zip(filas, info):
                    kk = int(fila.nombre[len("obst_"):])
                    c, h_eq, saturada = _fila_campana_k1(self.filtro, pose,
                                                         obst[kk], vel[kk])
                    if s == 0.0:
                        continue   # decisión 6: s = 0 es la fila del Exp O
                    n_mov += 1
                    n_sat_esperadas += int(saturada)
                    self.assertTrue(np.array_equal(fila.c, c))
                    self.assertEqual(fila.h, h_eq)
                self.assertEqual(sat, n_sat_esperadas)
                n_sat += sat
        self.assertGreater(n_mov, 500)
        self.assertGreater(n_sat, 0)   # velocidades grandes: ejercita la saturación

    def test_decision_6_s_cero_no_satura(self) -> None:
        """Con s = 0 y violación profunda, la fila es la del Exp O (no satura)."""
        obst = ((1.5, 1.5, 0.30),)
        pose = np.array([1.5 + 0.30 + 0.18 - 0.20 - ELE_A, 1.5, 0.0])  # h = −0,20
        ref = barreras_obstaculos(self.filtro, pose, obst)
        filas, _info, sat = Q.filas_obstaculo_f1(self.filtro, pose, obst,
                                                [np.zeros(2)], True)
        self.assertEqual(sat, 0)
        self.assertAlmostEqual(ref[0].h, -0.20, places=12)
        self.assertEqual(filas[0].h, ref[0].h)


class PruebaTrayectorias(unittest.TestCase):

    def test_circular_exacta_antihoraria_y_a_005(self) -> None:
        for k, obs in Q.ESCENARIOS_Q.items():
            for tr in Q.trayectorias_moviles(k, 420007):
                for t in range(0, MAX_STEPS + 1):
                    x, y = tr.posicion(t)
                    self.assertLess(abs(math.hypot(x - tr.centro[0], y - tr.centro[1])
                                        - tr.rho), 1e-12)
                for t in (0, 137, 499):
                    v = tr.velocidad(t)
                    x0, y0 = tr.posicion(t)
                    rad = np.array([x0 - tr.centro[0], y0 - tr.centro[1]])
                    self.assertGreater(float(rad[0] * v[1] - rad[1] * v[0]), 0.0)
                    cuerda = 2 * tr.rho * math.sin(tr.omega * tr.dt / 2) / tr.dt
                    self.assertAlmostEqual(float(np.linalg.norm(v)), cuerda, places=12)
                    self.assertLess(abs(float(np.linalg.norm(v)) - 0.05) / 0.05, 1e-3)

    def test_quieta_devuelve_los_mismos_float(self) -> None:
        for k in ("S1", "S2", "S3"):
            quietas = Q.trayectorias_quietas(ESCENARIOS[k])
            self.assertEqual(obstaculos_en(quietas, 0), ESCENARIOS[k])
            self.assertEqual(obstaculos_en(quietas, 499), ESCENARIOS[k])
            for tr in quietas:
                self.assertFalse(np.any(tr.velocidad(3)))

    def test_fases_del_flujo_3(self) -> None:
        for s in (420000, 420099):
            f = np.random.default_rng([s, 3]).uniform(-math.pi, math.pi, size=5)
            trs = Q.trayectorias_moviles("S3", s)
            self.assertEqual(tuple(tr.fase0 for tr in trs), tuple(float(x) for x in f))

    def test_armado_comparte_el_arranque(self) -> None:
        for k in ("S1", "S2", "S3"):
            s = 420042
            arms = {t: Q.armar_condicion(Q.CondicionQ(f"{k}_{t}", k, t), s)
                    for t in Q.TIPOS_Q}
            p0 = obstaculos_en(arms["din"].trayectorias, 0)
            for t in Q.TIPOS_Q:
                self.assertEqual(obstaculos_en(arms[t].trayectorias, 0), p0)
                self.assertEqual(arms[t].rebote, ())
            self.assertFalse(any(tr.mueve for tr in arms["quieto"].trayectorias))
            self.assertFalse(arms["ctrl"].fisicos)
            self.assertFalse(arms["sinvel"].termino_velocidad)
            self.assertTrue(arms["din"].termino_velocidad)


class PruebaMascara(unittest.TestCase):

    def setUp(self) -> None:
        env = EntornoObstaculos(**KW_ENV)
        self.xx, self.yy = env._field._grid_xx, env._field._grid_yy

    def test_quieta_es_la_del_exp_o(self) -> None:
        for k in ("S1", "S2", "S3"):
            m = mascara_permanente(Q.trayectorias_quietas(ESCENARIOS[k]),
                                   self.xx, self.yy, MAX_STEPS)
            self.assertTrue(np.array_equal(m, mascara_ocupada(self.xx, self.yy,
                                                              ESCENARIOS[k])))
        self.assertEqual(int(mascara_permanente(Q.trayectorias_quietas(
            ESCENARIOS["S1"]), self.xx, self.yy, MAX_STEPS).sum()), 124)

    def test_moviles_las_de_la_propuesta(self) -> None:
        esperadas = {"S1": 0, "S2": 6, "S3": 180}
        for k, n in esperadas.items():
            for s in (420000, 420063):
                m = mascara_permanente(Q.trayectorias_moviles(k, s),
                                       self.xx, self.yy, MAX_STEPS)
                self.assertEqual(int(m.sum()), n, (k, s))


class PruebaEntorno(unittest.TestCase):

    def test_quieto_igual_a_entorno_obstaculos_paso_a_paso(self) -> None:
        for k in ("S1", "S2", "S3"):
            obst = ESCENARIOS[k]
            for seed in (420003, 420044):
                ref = EntornoObstaculos(obstaculos_fisicos=obst, obstaculos_sorteo=obst,
                                        obstaculos_rebote=obst, **KW_ENV)
                nue = EntornoObstaculosMoviles(
                    trayectorias=Q.trayectorias_quietas(obst), fisicos=True,
                    obstaculos_rebote=obst, **KW_ENV)
                o1, _ = ref.reset(seed=seed)
                o2, _ = nue.reset(seed=seed)
                rng = np.random.default_rng(seed)
                for _t in range(150):
                    acc = {a: np.array([rng.uniform(-V_MAX, V_MAX),
                                        rng.uniform(-OMEGA_MAX, OMEGA_MAX)])
                           for a in ref.agents}
                    o1, r1, *_ = ref.step(acc)
                    o2, r2, *_ = nue.step(acc)
                    for a in ref.agents:
                        self.assertTrue(np.array_equal(ref._estados[a], nue._estados[a]))
                        self.assertTrue(np.array_equal(o1[a], o2[a]))
                        self.assertEqual(r1[a], r2[a])
                    self.assertTrue(np.array_equal(ref._field._grid_aoi,
                                                   nue._field._grid_aoi))
                    self.assertTrue(np.array_equal(ref._field._obj_posiciones,
                                                   nue._field._obj_posiciones))
                self.assertEqual(ref.contactos_obstaculo, nue.contactos_obstaculo)
                self.assertEqual(ref._field.n_rebotes_obstaculo,
                                 nue._field.n_rebotes_obstaculo)

    def test_objetivos_transparentes_identicos_al_control(self) -> None:
        for k in ("S1", "S3"):
            for seed in (420000, 420071):
                envs = {}
                for t in ("din", "ctrl"):
                    arm = Q.armar_condicion(Q.CondicionQ(f"{k}_{t}", k, t), seed)
                    env = EntornoObstaculosMoviles(trayectorias=arm.trayectorias,
                                                   fisicos=arm.fisicos,
                                                   obstaculos_rebote=arm.rebote,
                                                   **KW_ENV)
                    env.reset(seed=seed)
                    envs[t] = env
                cero = {a: np.zeros(2) for a in envs["din"].agents}
                for _t in range(MAX_STEPS):
                    self.assertTrue(np.array_equal(envs["din"]._field._obj_posiciones,
                                                   envs["ctrl"]._field._obj_posiciones))
                    envs["din"].step(cero)
                    envs["ctrl"].step(cero)
                self.assertEqual(envs["din"]._field.n_rebotes_obstaculo, 0)

    def test_rebote_en_disco_movil_se_niega(self) -> None:
        trs = Q.trayectorias_moviles("S1", 420000)
        with self.assertRaises(ValueError):
            EntornoObstaculosMoviles(trayectorias=trs, fisicos=True,
                                     obstaculos_rebote=None, **KW_ENV)

    def _env_s1(self, tipo: str) -> EntornoObstaculosMoviles:
        arm = Q.armar_condicion(Q.CondicionQ(f"S1_{tipo}", "S1", tipo), 420000)
        env = EntornoObstaculosMoviles(trayectorias=arm.trayectorias, fisicos=True,
                                       obstaculos_rebote=(), **KW_ENV)
        env.reset(seed=420000)
        return env

    def test_contacto_por_empuje(self) -> None:
        env = self._env_s1("din")
        ox, oy, r = env.posiciones_actuales()[0]
        v = env.velocidades_actuales()[0]
        d = v / float(np.linalg.norm(v))
        R = r + RADIO_CHASIS
        a0 = env.agents[0]
        env._estados[a0][0] = ox + d[0] * (R + 0.002)
        env._estados[a0][1] = oy + d[1] * (R + 0.002)
        for a in env.agents[1:]:
            self.assertGreater(math.hypot(env._estados[a][0] - ox,
                                          env._estados[a][1] - oy), R + 0.05)
        env.step({a: np.zeros(2) for a in env.agents})
        x1, y1, _ = env.posiciones_actuales()[0]
        self.assertEqual(env.contactos_obstaculo[a0], 1)
        self.assertEqual((env.contactos_empuje, env.contactos_avance), (1, 0))
        self.assertGreaterEqual(math.hypot(env._estados[a0][0] - x1,
                                           env._estados[a0][1] - y1), R)

    def test_contacto_por_avance(self) -> None:
        env = self._env_s1("quieto")
        ox, oy, r = env.posiciones_actuales()[0]
        R = r + RADIO_CHASIS
        a0 = env.agents[0]
        env._estados[a0][0] = ox + R + 0.002
        env._estados[a0][1] = oy
        env._estados[a0][2] = math.pi          # de frente al obstáculo
        acc = {a: np.zeros(2) for a in env.agents}
        acc[a0] = np.array([V_MAX, 0.0])
        env.step(acc)
        self.assertEqual(env.contactos_obstaculo[a0], 1)
        self.assertEqual((env.contactos_empuje, env.contactos_avance), (0, 1))


class PruebaGestorUsaLasPosicionesActualizadas(unittest.TestCase):
    """(Revisión del 19-10: la prueba de abajo, sola, era tautológica.)"""

    def test_actualizado_es_el_del_exp_o_con_las_posiciones_nuevas(self) -> None:
        rng = np.random.default_rng(11)
        trs = Q.trayectorias_moviles("S2", 420003)
        obst_a, obst_b = obstaculos_en(trs, 0), obstaculos_en(trs, 150)
        movil = Q.GestorEscapeMovil(5, ARENA, obst_a)
        movil.actualizar_obstaculos(obst_b)
        ref_b, ref_a = GestorEscape(5, ARENA, obst_b), GestorEscape(5, ARENA, obst_a)
        distintas = 0
        for _ in range(500):
            poses = np.column_stack([rng.uniform(0.6, 2.4, 5), rng.uniform(0.6, 2.4, 5),
                                     rng.uniform(-math.pi, math.pi, 5)])
            for i in range(5):
                d1, h1, o1 = movil.normales_activas(i, poses)
                d2, h2, o2 = ref_b.normales_activas(i, poses)
                self.assertEqual((h1, o1), (h2, o2))
                self.assertTrue((d1 is None and d2 is None) or np.array_equal(d1, d2))
                distintas += int(h1 != ref_a.normales_activas(i, poses)[1])
        self.assertGreater(distintas, 0)


class PruebaTiemposDelBucle(unittest.TestCase):
    """
    (Revisión del 19-10.) Con obstáculos móviles, la decisión del paso t usa
    p_o(t) y v_o(t), y las distancias se miden contra p_o(t + 1). El control
    bit a bit no lo ve (con v = 0 las posiciones no cambian).
    """

    def test_decision_en_t_y_distancias_en_t_mas_1(self) -> None:
        from unittest import mock
        cond, seed = Q.CondicionQ("S2_din", "S2", "din"), 420001
        trs = Q.trayectorias_moviles("S2", seed)
        filas_orig, dist_orig = Q.filas_obstaculo_f1, Q.distancia_minima
        llamadas_f1, llamadas_d = [], []

        def f1(filtro, pose, obst, vel, termino):
            llamadas_f1.append((tuple(obst), [np.array(v) for v in vel]))
            return filas_orig(filtro, pose, obst, vel, termino)

        def dist(p, obst):
            llamadas_d.append(tuple(obst))
            return dist_orig(p, obst)
        with mock.patch.object(Q, "filas_obstaculo_f1", f1), \
                mock.patch.object(Q, "distancia_minima", dist):
            fila = Q.correr_episodio_Q(cond, seed)
        self.assertEqual(len(llamadas_f1), 5 * MAX_STEPS)
        self.assertEqual(len(llamadas_d), 5 * MAX_STEPS)
        for k, (obst, vel) in enumerate(llamadas_f1):
            t = k // 5
            self.assertEqual(obst, obstaculos_en(trs, t))
            for v, tr in zip(vel, trs):
                self.assertTrue(np.array_equal(v, tr.velocidad(t)))
        for k, obst in enumerate(llamadas_d):
            self.assertEqual(obst, obstaculos_en(trs, k // 5 + 1))
        self.assertEqual(fila["pasos"], MAX_STEPS)


class PruebaGestor(unittest.TestCase):

    def test_quieto_igual_al_del_exp_o(self) -> None:
        rng = np.random.default_rng(5)
        obst = ESCENARIOS["S3"]
        g1, g2 = GestorEscape(5, ARENA, obst), Q.GestorEscapeMovil(5, ARENA, obst)
        for _ in range(300):
            poses = np.column_stack([rng.uniform(0.1, 2.9, 5), rng.uniform(0.1, 2.9, 5),
                                     rng.uniform(-math.pi, math.pi, 5)])
            g2.actualizar_obstaculos(obst)
            for i in range(5):
                u = rng.uniform(-0.3, 0.3, 2).astype(np.float32)
                a1, e1 = g1.gestionar(i, poses, u)
                a2, e2 = g2.gestionar(i, poses, u)
                self.assertTrue(np.array_equal(a1, a2))
                self.assertEqual(e1, e2)
                g1.intervino_prev[i] = g2.intervino_prev[i] = bool(rng.random() < 0.5)
            g1.pose_previa = poses.copy()
            g2.pose_previa = poses.copy()


class PruebaPasabilidad(unittest.TestCase):

    def test_region_igual_a_la_del_exp_o_con_su_rejilla(self) -> None:
        """Con g = 0,005, `region_factible` da lo mismo que el chequeo del Exp O."""
        import re
        from correr_experimento_O import verificar_pasabilidad
        for k in ("S1", "S2", "S3"):
            obst = ESCENARIOS[k]
            linea = verificar_pasabilidad(k, obst)[0]
            m = re.search(r"h≥0: ([0-9.]+) m², (\d+) comp\.; h≥0,06: ([0-9.]+) m², (\d+) comp\.",
                          linea)
            n0, a0 = Q.region_factible(obst, 0.005, 0.0)
            n6, a6 = Q.region_factible(obst, 0.005, 0.06)
            self.assertEqual((n0, n6), (int(m.group(2)), int(m.group(4))))
            self.assertEqual(f"{a0:.6f}", m.group(1))
            self.assertEqual(f"{a6:.6f}", m.group(3))

    def test_una_semilla_pasa_y_un_caso_cerrado_falla(self) -> None:
        r = Q._pasabilidad_semilla(("S3", 420000))
        self.assertEqual(r["fallos"], [])
        self.assertAlmostEqual(r["gw"], 0.49, places=3)
        n, _ = Q.region_factible(((1.5, 1.5, 1.7),), 0.01, 0.0)   # disco que tapa todo
        self.assertEqual(n, 0)
        n, _ = Q.region_factible(((0.75, 1.5, 0.3), (2.25, 1.5, 0.3), (1.5, 1.5, 0.45)),
                                 0.01, 0.06)
        self.assertNotEqual(n, 1)


class PruebaReanudacion(unittest.TestCase):

    def test_condicion_terminada_se_reutiliza_sin_correr(self) -> None:
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(Q, "DIR_PARCIALES", Path(d)):
                cond = Q.CondicionQ("S1_quieto", "S1", "quieto")
                f1 = Q.correr_condiciones([cond], 2, "prueba", "h0", [420000, 420001])
                with mock.patch.object(Q, "_tarea_Q", side_effect=AssertionError("corrió")):
                    f2 = Q.correr_condiciones([cond], 2, "prueba", "h0", [420000, 420001])
                self.assertEqual(f1, f2)
                # Otra huella: no se reutiliza (se vuelve a correr y se respalda).
                f3 = Q.correr_condiciones([cond], 2, "prueba", "h1", [420000, 420001])
                self.assertEqual([{k: v for k, v in f.items() if k != "t_episodio_s"} for f in f1],
                                 [{k: v for k, v in f.items() if k != "t_episodio_s"} for f in f3])


class PruebaEpisodioCompleto(unittest.TestCase):
    """Dos episodios del camino nuevo contra sus filas del Exp O (las 1000
    corridas van en el subcomando `control`)."""

    def test_dos_episodios_reproducen_el_exp_o(self) -> None:
        with open(Q.RUTA_CSV_O_COMP, encoding="utf-8") as f:
            ref = {(r["condicion"], int(r["seed_ep"])): r for r in csv.DictReader(f)}
        for cond, seed in ((Q.CondicionQ("S3", "S3", "expo_obst"), 420012),
                           (Q.CondicionQ("S1_fant", "S1", "expo_fant"), 420005)):
            fila = Q.correr_episodio_Q(cond, seed)
            r = ref[(cond.nombre, seed)]
            dif = [c for c in r if c != "t_episodio_s" and Q._serial(fila[c]) != r[c]]
            self.assertEqual(dif, [], (cond.nombre, seed))

    def test_un_episodio_movil_corre_entero(self) -> None:
        fila = Q.correr_episodio_Q(Q.CondicionQ("S2_din", "S2", "din"), 420001)
        self.assertEqual(fila["pasos"], MAX_STEPS)
        self.assertEqual(fila["mueve"], 1)
        self.assertEqual(fila["frac_mascara"], 6 / 4096)
        self.assertGreater(fila["expo_frac_obst_activo"], 0.0)


if __name__ == "__main__":
    unittest.main()
