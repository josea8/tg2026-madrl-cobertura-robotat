"""
test_replica_con_obstaculo.py
=============================
Pruebas de `replica_con_obstaculo.py` que no levantan el simulador:

  · (a1) las funciones copiadas de `replica_con_capas.py` (inversa de marcos,
    calibración identidad, regla de la rampa) son iguales a las originales,
    extraídas con `ast` (el original no se puede importar: es un script);
  · (b) la función pura del cierre: desfase de ±1 decisión, error > 1 mm,
    rumbo, mandos, filas abortadas, 4 quieto, corrida vacía;
  · la carga en los dos formatos (campaña nueva y ensayos del 07-10), la
    negativa con una campaña de hardware abierta, la auditoría de la traza;
  · el plan de corridas (normal, suplementaria), `--reanudar` (claves hechas,
    línea truncada, clave repetida) y el orden del contrato de columnas.

    python -m unittest test_replica_con_obstaculo -v

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import io
import math
import random
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import analizar_campana_l2 as A
import campana_obstaculo as CO
import config_robotat as cfg
import replica_con_obstaculo as R

_CARPETA = Path(__file__).resolve().parent
_CAPAS = _CARPETA / "replica_con_capas.py"
_ENSAYO_NUEVO = _CARPETA / "resultados_demo_obstaculo" / "ensayo_campana_20261009_185745"
_ENSAYO_VIEJO = _CARPETA / "resultados_demo_obstaculo" / "ensayo_L2_auto_20261007_125313"

#: Los datos de prueba (ensayos del 07 y 09-10, episodios del 30-09) se
#: grabaron con el enjambre 1, 5, 8, 6, 9; desde el 16-10 el mapeo tiene el
#: 2 en lugar del 6 (aprobado por José el 17-10). Estas pruebas corren con el mapeo de sus datos.
_PARCHE_MAPEO = mock.patch.object(cfg, "MAPEO_AGENTES", {
    i: cfg.AsignacionAgente(id_marcador=r, id_robot=r)
    for i, r in enumerate((1, 5, 8, 6, 9))})
_PARCHE_REGIMEN = mock.patch.object(A, "ROBOTS_AGENTES", ("1", "5", "8", "6", "9"))


def setUpModule() -> None:
    _PARCHE_MAPEO.start()
    _PARCHE_REGIMEN.start()


def tearDownModule() -> None:
    _PARCHE_REGIMEN.stop()
    _PARCHE_MAPEO.stop()


def _arbol_capas() -> ast.Module:
    return ast.parse(_CAPAS.read_text(encoding="utf-8"))


def _funcion(arbol: ast.Module, nombre: str) -> ast.FunctionDef:
    for n in arbol.body:
        if isinstance(n, ast.FunctionDef) and n.name == nombre:
            return n
    raise AssertionError(f"sin {nombre}")


def _sin_docstring(f: ast.FunctionDef) -> str:
    f = copy.deepcopy(f)
    f.body = [b for b in f.body
              if not (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant))]
    return ast.dump(f.args) + "".join(ast.dump(b) for b in f.body)


class PruebaA1CopiasDelOriginal(unittest.TestCase):

    def setUp(self) -> None:
        self._previo = {k: getattr(cfg, k) for k in (
            "ESCALA_POSICION", "ROTACION_MARCO_RAD", "TRASLACION_X_M", "TRASLACION_Y_M",
            "OFFSET_HEADING_RAD", "offset_rumbo_de_robot")}

    def tearDown(self) -> None:
        for k, v in self._previo.items():
            setattr(cfg, k, v)

    def test_env_a_lab_es_el_del_original(self) -> None:
        nuevo = _funcion(ast.parse((_CARPETA / "replica_con_obstaculo.py").read_text(
            encoding="utf-8")), "env_a_lab")
        self.assertEqual(_sin_docstring(nuevo), _sin_docstring(_funcion(_arbol_capas(),
                                                                         "env_a_lab")))

    def test_identidad_son_las_seis_asignaciones_del_original(self) -> None:
        asign = [ast.dump(n) for n in _arbol_capas().body
                 if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Attribute)
                 and isinstance(n.targets[0].value, ast.Name)
                 and n.targets[0].value.id == "cfg"]
        cuerpo = _funcion(ast.parse((_CARPETA / "replica_con_obstaculo.py").read_text(
            encoding="utf-8")), "imponer_identidad").body
        nuevas = [ast.dump(b) for b in cuerpo
                  if not (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant))]
        self.assertEqual(len(asign), 6)
        self.assertEqual(nuevas, asign)

    def test_calibracion_y_despues_identidad(self) -> None:
        import calibracion_sesion as calib
        orden = []
        with mock.patch.object(calib, "aplicar_a_config", lambda: orden.append("calib")), \
                mock.patch.object(R, "imponer_identidad", lambda: orden.append("identidad")):
            R.aplicar_calibracion_identidad()
        self.assertEqual(orden, ["calib", "identidad"])
        fuente_pila = ast.unparse(_funcion(ast.parse((_CARPETA / "replica_con_obstaculo.py")
                                                     .read_text(encoding="utf-8")), "armar_pila"))
        self.assertIn("aplicar_calibracion_identidad()", fuente_pila)
        self.assertNotIn("calib.aplicar_a_config()", fuente_pila)

    def test_regla_de_la_rampa_igual_a_la_original(self) -> None:
        fuente = ast.unparse(_funcion(_arbol_capas(), "decisiones_previas"))
        ns: dict = {}
        ruta = R.DIR_3009 / "20260930_sesion-evaluacion_etapa7_episodios_02.csv"
        todas = R._leer(ruta)
        ns["todas"] = todas
        exec(fuente, ns)
        for r in todas:
            ep = int(r["episodio"])
            self.assertEqual(ns["decisiones_previas"](ep),
                             R.previas_por_suma(todas, "episodio", ep), ep)

    def test_ida_y_vuelta_con_identidad(self) -> None:
        R.imponer_identidad()
        rng = random.Random(7)
        ids = [cfg.MAPEO_AGENTES[i].id_robot for i in range(R.N_AGENTES)] + [R.ID_OBSTACULO]
        for j in range(300):
            x, y, th = rng.uniform(0, 3), rng.uniform(0, 3), rng.uniform(-math.pi, math.pi)
            xl, yl, yaw = R.env_a_lab(x, y, th, ids[j % len(ids)])
            self.assertAlmostEqual(xl + 1.5, x, places=12)
            self.assertAlmostEqual(yl + 1.5, y, places=12)
            self.assertAlmostEqual(math.remainder(yaw - th, 2 * math.pi), 0.0, places=12)


def _traza(n: int = 40, quieto_hasta: int = 10):
    out = []
    for k in range(n):
        s = max(0, k - quieto_hasta) * 0.005
        out.append({"paso": k, "x": 1.5 + s, "y": 0.9, "th": 0.01 * k,
                    "v_cmd": 0.0 if k < quieto_hasta else 0.05, "w_cmd": 0.083,
                    "estado": "espera" if k < quieto_hasta else "marcha",
                    "error_radial": None})
    return out


class PruebaCierreB(unittest.TestCase):

    def test_iguales_dan_ok(self) -> None:
        hw = _traza()
        r = R.evaluar_cierre_b(copy.deepcopy(hw), hw)
        self.assertEqual((r["ok"], r["desfase"], r["err_max"]), (1, 0, 0.0))
        self.assertGreater(r["n_mov"], 0)

    def test_desfase_de_una_decision(self) -> None:
        hw = _traza()
        for lag in (-1, 1):
            rep = copy.deepcopy(hw)
            for k, f in enumerate(rep):
                j = min(max(k + lag, 0), len(hw) - 1)
                f["x"], f["y"], f["th"] = hw[j]["x"], hw[j]["y"], hw[j]["th"]
            r = R.evaluar_cierre_b(rep, hw)
            self.assertEqual((r["ok"], r["desfase"]), (0, lag), lag)

    def test_error_rumbo_y_mandos(self) -> None:
        hw = _traza()
        rep = copy.deepcopy(hw)
        rep[20]["x"] += 0.002
        self.assertEqual(R.evaluar_cierre_b(rep, hw)["ok"], 0)
        rep = copy.deepcopy(hw)
        rep[20]["th"] += 1e-5
        self.assertEqual(R.evaluar_cierre_b(rep, hw)["ok"], 0)
        rep = copy.deepcopy(hw)
        rep[20]["v_cmd"] = 0.049
        r = R.evaluar_cierre_b(rep, hw)
        self.assertEqual((r["ok"], r["mandos_iguales"]), (0, 0))

    def test_fila_abortada_no_rompe_los_mandos_y_4_quieto(self) -> None:
        hw = _traza()
        rep = copy.deepcopy(hw[:25])
        rep[-1].update(estado="abortado", v_cmd=0.0, w_cmd=0.0)
        r = R.evaluar_cierre_b(rep, hw)
        self.assertEqual((r["ok"], r["mandos_iguales"], r["n"]), (1, 1, 25))
        quieto = _traza(n=20, quieto_hasta=40)
        r = R.evaluar_cierre_b(copy.deepcopy(quieto), quieto)
        self.assertEqual((r["ok"], r["desfase"], r["n_mov"]), (1, 0, 0))

    def test_desfase_con_un_4_lento_y_bordes(self) -> None:
        lento = [{"paso": k, "x": 1.5 + 0.0005 * k, "y": 0.9, "th": 0.0, "v_cmd": 0.05,
                  "w_cmd": 0.0, "estado": "marcha", "error_radial": None} for k in range(40)]
        rep = copy.deepcopy(lento)
        for k, f in enumerate(rep):
            f["x"] = lento[max(k - 1, 0)]["x"]
        r = R.evaluar_cierre_b(rep, lento)
        self.assertLessEqual(r["err_max"], R.UMBRAL_CIERRE_B_M)
        self.assertEqual((r["ok"], r["desfase"]), (0, -1))
        hw = _traza()
        rep = copy.deepcopy(hw)
        rep[3]["paso"] = 2                                 # paso repetido
        self.assertEqual(R.evaluar_cierre_b(rep, hw)["ok"], 0)
        for dx, ok in ((0.0009, 1), (0.0011, 0)):
            rep = copy.deepcopy(hw)
            rep[5]["x"] += dx
            self.assertEqual(R.evaluar_cierre_b(rep, hw)["ok"], ok, dx)
        for dth, ok in ((0.9e-6, 1), (1.1e-6, 0)):
            rep = copy.deepcopy(hw)
            rep[5]["th"] += dth
            self.assertEqual(R.evaluar_cierre_b(rep, hw)["ok"], ok, dth)

    def test_corrida_vacia_y_pose_faltante(self) -> None:
        # Sin decisiones (no arrancó): sin cierre (b), no una falla (plan §7).
        r = R.evaluar_cierre_b([], _traza())
        self.assertEqual((r["ok"], r["err_max"], r["desfase"], r["n"]), ("", "", "", 0))
        rep = copy.deepcopy(_traza())
        rep[5]["x"] = ""
        self.assertEqual(R.evaluar_cierre_b(rep, _traza())["ok"], 0)


class PruebaCarga(unittest.TestCase):

    def test_campana_nueva(self) -> None:
        tomas = R.cargar_campana(_ENSAYO_NUEVO, "ensayo")
        self.assertEqual([t.intento for t in tomas], [1, 2, 5, 6, 7])
        t = tomas[0]
        self.assertEqual((t.decisiones_previas, t.semilla, t.decisiones), (0, 421000, 500))
        self.assertEqual(len(t.traza_obstaculo), 500)
        self.assertEqual(R.auditar(tomas), [])

    def test_carpeta_vieja(self) -> None:
        tomas = R.cargar_carpeta_vieja(_ENSAYO_VIEJO)
        self.assertEqual(len(tomas), 10)
        self.assertEqual(tomas[0].decisiones_previas, 0)
        self.assertEqual(tomas[1].decisiones_previas, 500)
        self.assertTrue(tomas[0].avisos)
        self.assertEqual(R.auditar(tomas), [])

    def test_auditoria_detecta_traza_rota(self) -> None:
        tomas = R.cargar_carpeta_vieja(_ENSAYO_VIEJO)
        t = copy.deepcopy(tomas[1])
        del t.traza_obstaculo[100]
        self.assertTrue(any("pasos" in p for p in R.auditar([t])))
        t = copy.deepcopy(tomas[0])                       # rampa: espera 0..49
        t.traza_obstaculo[10]["estado"] = "marcha"
        self.assertTrue(any("rampa" in p for p in R.auditar([t])))

    def test_auditoria_rampa_larga_y_robots(self) -> None:
        tomas = R.cargar_carpeta_vieja(_ENSAYO_VIEJO)
        t = copy.deepcopy(tomas[0])
        t.traza_obstaculo[50]["estado"] = "espera"          # rampa de 51
        self.assertTrue(any("rampa" in p for p in R.auditar([t])))
        t = copy.deepcopy(tomas[1])
        t.robots = (1, 5, 8, 6, 3)
        self.assertTrue(any("MAPEO" in p for p in R.auditar([t])))
        t = copy.deepcopy(tomas[1])
        t.dif_obst_traza0_m = 0.002
        self.assertTrue(any("4 contra la traza" in p for p in R.auditar([t])))
        t.plataforma = "hw"
        self.assertEqual(R.auditar([t]), [])
        self.assertTrue(t.avisos[-1].endswith("(informativo en hw)"))

    def test_previas_adulteradas_se_detectan(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="replica_prev_"))
        try:
            shutil.copytree(_ENSAYO_NUEVO, tmp / "e", ignore=shutil.ignore_patterns(
                "replica_campana", "analisis_campana"))
            ruta = sorted((tmp / "e").glob("*_L2_tomas*.csv"))[-1]
            filas = R._leer(ruta)
            for f in filas:
                if f.get("decisiones_previas") not in (None, "", "0"):
                    f["decisiones_previas"] = str(int(float(f["decisiones_previas"])) + 7)
                    break
            import test_analizar_campana_l2 as T
            T.escribir(ruta, filas)
            with self.assertRaises(R.ErrorReplica):
                R.cargar_campana(tmp / "e", "ensayo")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_campana_de_hardware_abierta_se_niega(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="replica_test_"))
        try:
            with mock.patch.object(CO, "ARCHIVOS_CONGELADOS", ()):
                CO.Campana.crear(tmp, "hw_abierta", "hw", 4, 4)
            with self.assertRaises(R.ErrorReplica) as e:
                R.cargar_campana(tmp, "hw_abierta")
            self.assertIn("no está cerrada", str(e.exception))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class PruebaPlanYEscritura(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="replica_plan_"))
        self.tomas = R.cargar_carpeta_vieja(_ENSAYO_VIEJO)[:2]

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fila(self, t, cond, tau, rep, valido=1, pasada="normal"):
        f = {c: "" for c in R.columnas_contrato()}
        f.update(intento_campana=t.intento, condicion=cond, tau_s=tau, rep=rep,
                 valido=valido, pasada=pasada)
        return f

    def test_plan_normal_y_reanudacion(self) -> None:
        plan = R.plan_de_corridas(self.tomas, {}, False, R.CONDICIONES_ORDEN)
        self.assertEqual(len(plan), 2 * 3 * 3)
        self.assertEqual([(p[0].intento, p[1], p[2], p[3]) for p in plan[:4]],
                         [(self.tomas[0].intento, R.CON, 0.0, 1),
                          (self.tomas[0].intento, R.SIN, 0.0, 1),
                          (self.tomas[0].intento, R.CON, 0.45, 1),
                          (self.tomas[1].intento, R.CON, 0.0, 1)])
        esc = R.Escritor(self.tmp)
        esc.agregar("tomas", [self._fila(*p[:4]) for p in plan[:5]])
        hechas = R.claves_hechas(self.tmp)
        self.assertEqual(len(hechas), 5)
        self.assertEqual(len(R.plan_de_corridas(self.tomas, hechas, False,
                                                R.CONDICIONES_ORDEN)), 13)
        cab = esc.rutas["tomas"].read_text(encoding="utf-8").splitlines()[0].split(",")
        self.assertEqual(cab[:len(A.COLUMNAS_REPLICA)], list(A.COLUMNAS_REPLICA))

    def test_suplementaria_solo_grupos_sin_validas(self) -> None:
        esc = R.Escritor(self.tmp)
        filas = []
        for t in self.tomas:
            for cond, tau in R.CONDICIONES_ORDEN:
                for rep in R.REPS_NORMALES:
                    invalida = (t is self.tomas[0] and cond == R.SIN)
                    filas.append(self._fila(t, cond, tau, rep, valido=0 if invalida else 1))
        esc.agregar("tomas", filas)
        plan = R.plan_de_corridas(self.tomas, R.claves_hechas(self.tmp), True,
                                  R.CONDICIONES_ORDEN)
        self.assertEqual([(p[0].intento, p[1], p[3], p[4]) for p in plan],
                         [(self.tomas[0].intento, R.SIN, r, "suplementaria")
                          for r in (4, 5, 6)])

    def test_grupo_mixto_no_va_a_la_suplementaria_y_completitud(self) -> None:
        esc = R.Escritor(self.tmp)
        filas = []
        for t in self.tomas:
            for cond, tau in R.CONDICIONES_ORDEN:
                for rep in R.REPS_NORMALES:
                    mixto = (t is self.tomas[1] and cond == R.CON and tau == 0.0)
                    filas.append(self._fila(t, cond, tau, rep, valido=1 if (not mixto or rep == 1)
                                            else 0))
        esc.agregar("tomas", filas)
        hechas = R.claves_hechas(self.tmp)
        self.assertEqual(R.plan_de_corridas(self.tomas, hechas, True, R.CONDICIONES_ORDEN), [])
        self.assertEqual(R.completitud(self.tomas, hechas, R.CONDICIONES_ORDEN), ([], []))
        hechas2 = {k: (dict(v, valido=0) if k[1] == R.SIN and k[0] == self.tomas[0].intento
                       else v) for k, v in hechas.items()}
        normales, suplementarias = R.completitud(self.tomas, hechas2, R.CONDICIONES_ORDEN)
        self.assertEqual((normales, len(suplementarias)), ([], 1))
        del hechas2[(self.tomas[1].intento, R.CON, 0.45, 2)]
        self.assertEqual(len(R.completitud(self.tomas, hechas2, R.CONDICIONES_ORDEN)[0]), 1)

    def test_validar_hechas_pila_campana_y_toma(self) -> None:
        t = self.tomas[0]
        base = self._fila(t, R.CON, 0.0, 1)
        base.update(sha256_pila="P", campana=t.campana, semilla=t.semilla,
                    decisiones_previas=t.decisiones_previas)
        R.validar_hechas({(t.intento, R.CON, 0.0, 1): base}, self.tomas, "P")
        for cambio in ({"sha256_pila": "FALSA"}, {"sha256_pila": "otra"},
                       {"campana": "otra"}, {"semilla": t.semilla + 1},
                       {"decisiones_previas": t.decisiones_previas + 1}):
            with self.assertRaises(R.ErrorReplica, msg=str(cambio)):
                R.validar_hechas({(t.intento, R.CON, 0.0, 1): dict(base, **cambio)},
                                 self.tomas, "P")

    def test_solo_tomas_exige_salida_propia(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(R.main(["--campana", "ensayo", "--base", str(_ENSAYO_NUEVO),
                                     "--solo-tomas", "1", "--verificar"]), 2)

    def test_linea_truncada_y_clave_repetida(self) -> None:
        esc = R.Escritor(self.tmp)
        esc.agregar("tomas", [self._fila(self.tomas[0], R.CON, 0.0, 1)])
        with open(esc.rutas["tomas"], "ab") as fh:
            fh.write(b"vieja_x,y,")
        with self.assertRaises(R.ErrorReplica):
            R.claves_hechas(self.tmp)
        shutil.rmtree(self.tmp)
        esc = R.Escritor(self.tmp)
        esc.agregar("tomas", [self._fila(self.tomas[0], R.CON, 0.0, 1)] * 2)
        with self.assertRaises(R.ErrorReplica):
            R.claves_hechas(self.tmp)

    def test_verificar_sin_simulador(self) -> None:
        nombres = ("ESCALA_POSICION", "ROTACION_MARCO_RAD", "TRASLACION_X_M",
                   "TRASLACION_Y_M", "OFFSET_HEADING_RAD", "offset_rumbo_de_robot",
                   "OFFSETS_RUMBO_POR_ROBOT", "OFFSETS_RUMBO_MEDIDOS")
        previo = {k: getattr(cfg, k) for k in nombres}
        try:
            with contextlib.redirect_stdout(io.StringIO()) as salida:
                codigo = R.main(["--carpeta-vieja", str(_ENSAYO_VIEJO), "--salida",
                                 str(self.tmp), "--verificar"])
        finally:
            for k, v in previo.items():
                setattr(cfg, k, v)
        self.assertEqual(codigo, 0)
        self.assertIn("chequeos OK", salida.getvalue())


class _EntornoSinReloj:
    """Mixin: `avanzar` sólo cuenta ticks (sin dormir ni reloj de pared)."""

    def avanzar(self, n_ticks: int) -> bool:
        for _ in range(int(n_ticks)):
            self._k += 1
        return True


class PruebaA1Decision(unittest.TestCase):
    """
    (a1) La variante SIN obstáculo de la réplica decide EXACTAMENTE como la
    pila de `replica_con_capas` ante las mismas observaciones: pila A =
    `CoordinadorEnjambre` sobre `FuentePosesRobotat`/`CanalActuacionRobotat`
    (la del 30-09); pila B = `fabricar_coordinador` sobre las subclases con
    obstáculo, con el 4 estacionado fuera del alcance del mocap y
    `supervisor=None`. Sin red ni tiempo real: la fuente recibe la matriz de
    poses de cada decisión de un episodio del 30-09 (s1, ep 5, semilla
    420004), el canal registra los rpm y el entorno sólo cuenta ticks. Se
    comparan bit a bit, por decisión y agente, la observación, las acciones
    (nominal, tras el escape, ejecutada), el escape, la intervención del CBF
    y los rpm enviados, y al final la cobertura.
    """

    EPISODIO, SEMILLA = 5, 420004

    def setUp(self) -> None:
        self._previo = {k: getattr(cfg, k) for k in (
            "ESCALA_POSICION", "ROTACION_MARCO_RAD", "TRASLACION_X_M", "TRASLACION_Y_M",
            "OFFSET_HEADING_RAD", "offset_rumbo_de_robot")}
        R.imponer_identidad()

    def tearDown(self) -> None:
        for k, v in self._previo.items():
            setattr(cfg, k, v)

    def _matrices(self, sufijo: str = "", episodio: int = 0):
        episodio = episodio or self.EPISODIO
        filas = [r for r in R._leer(
            R.DIR_3009 / f"20260930_sesion-evaluacion_etapa7_decisiones{sufijo}.csv")
            if r["episodio"] == str(episodio)]
        pasos = sorted({int(r["paso"]) for r in filas})
        out = []
        for k in pasos:
            m = []
            for i in range(R.N_AGENTES):
                r = [x for x in filas if x["paso"] == str(k) and x["agente"] == str(i)][0]
                rid = cfg.MAPEO_AGENTES[i].id_robot
                xl, yl, yaw = R.env_a_lab(float(r["pose_env_x"]), float(r["pose_env_y"]),
                                          float(r["pose_env_th"]), rid)
                m.append([xl, yl, 0.0, math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)])
            out.append(m)
        return out

    def _correr(self, pila: str, matrices, previas: int, semilla: int = 0):
        semilla = semilla or self.SEMILLA
        import numpy as np
        import adaptadores_robotat as ad
        import coordinador_enjambre as ce
        import demo_obstaculo_movil as demo

        class Entorno(_EntornoSinReloj, ad.EntornoEjecucionRobotat):
            pass
        estacionado = list(R.env_a_lab(*R.ESTACIONAMIENTO_ENV, R.ID_OBSTACULO))
        if pila == "A":
            fuente = ad.FuentePosesRobotat(R.N_AGENTES)
            canal = ad.CanalActuacionRobotat(R.N_AGENTES, fuente)
        else:
            fuente = demo.FuentePosesConObstaculo(R.N_AGENTES, R.ID_OBSTACULO, R.ID_OBSTACULO)
            canal = demo.CanalConObstaculo(R.N_AGENTES, fuente, R.ID_OBSTACULO,
                                           conectar_obstaculo=False)
        entorno = Entorno(fuente, canal, 10)
        actual = {"k": 0}

        def un_viaje(_peticion, n_filas):
            m = [list(f) for f in matrices[min(actual["k"], len(matrices) - 1)]]
            if n_filas == R.N_AGENTES + 1:
                yaw = estacionado[2]
                m.append([estacionado[0], estacionado[1], 0.0,
                          math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)])
            return np.array(m, dtype=np.float64)
        fuente._un_viaje = un_viaje
        fuente.agentes_vencidos = lambda: []
        rpm = []
        canal._enviar_crudo = lambda i, a, b: rpm.append((actual["k"], i, a, b)) or True
        if pila == "A":
            coord = ce.CoordinadorEnjambre(fuente=fuente, canal=canal, entorno=entorno,
                                           n_agentes=R.N_AGENTES, timestep_ms=10)
        else:
            coord = R.fabricar_coordinador(fuente, canal, entorno)
            espias = {"predecir": 0}
            original = demo.predecir_pose

            def espia(*a, **kw):
                espias["predecir"] += 1
                return original(*a, **kw)
        obs = []

        def observador(d):
            obs.append((actual["k"], int(d["agente"]),
                        np.asarray(d["observacion"]).copy(),
                        np.asarray(d["accion_nominal"]).copy(),
                        np.asarray(d["accion_tras_escape"]).copy(),
                        np.asarray(d["accion_ejecutada"]).copy(),
                        int(d["en_escape"]), int(d["cbf_intervino"])))
        coord._observador_paso = observador
        canal.factor_operativo = 0.40
        canal.decisiones_enviadas = previas
        try:
            with mock.patch.object(demo, "predecir_pose",
                                   espia if pila == "B" else demo.predecir_pose):
                self.assertTrue(coord._reiniciar_episodio(semilla))
                for k in range(len(matrices)):
                    actual["k"] = k
                    coord._avanzar(coord.pasos_por_decision)
                    coord._decidir_y_actuar()
            cobertura = 1.0 - float(np.mean(coord.env._field._grid_aoi))
            if pila == "B":
                self.assertEqual(espias["predecir"], 0)
                self.assertEqual(coord.filas_obstaculo, {})
                self.assertIsNone(fuente.pose_obstaculo())
        finally:
            import atexit
            atexit.unregister(coord._detener_seguro)
        self.limitadas = canal.decisiones_limitadas
        return obs, rpm, cobertura

    def test_mismas_acciones_tambien_con_rampa(self) -> None:
        """s2 ep 1 del 30-09 (semilla 420000) arranca con 0 decisiones
        previas: las dos pilas pasan por las 50 decisiones de la rampa."""
        import numpy as np
        matrices = self._matrices("_02", 1)
        eps = R._leer(R.DIR_3009 / "20260930_sesion-evaluacion_etapa7_episodios_02.csv")
        previas = R.previas_por_suma(eps, "episodio", 1)
        self.assertEqual(previas, 0)
        with contextlib.redirect_stdout(io.StringIO()):
            obs_a, rpm_a, cob_a = self._correr("A", matrices, previas, 420000)
            lim_a = self.limitadas
            obs_b, rpm_b, cob_b = self._correr("B", matrices, previas, 420000)
            lim_b = self.limitadas
        self.assertEqual((lim_a, lim_b), (cfg.DECISIONES_ARRANQUE, cfg.DECISIONES_ARRANQUE))
        for fa, fb in zip(obs_a, obs_b):
            for xa, xb in zip(fa[2:6], fb[2:6]):
                self.assertTrue(np.array_equal(xa, xb), fa[:2])
            self.assertEqual(fa[6:], fb[6:])
        self.assertEqual(rpm_a, rpm_b)
        self.assertEqual(cob_a, cob_b)

    def test_mismas_acciones_ante_mismas_observaciones(self) -> None:
        import numpy as np
        matrices = self._matrices()
        eps = R._leer(R.DIR_3009 / "20260930_sesion-evaluacion_etapa7_episodios.csv")
        previas = R.previas_por_suma(eps, "episodio", self.EPISODIO)
        with contextlib.redirect_stdout(io.StringIO()):
            obs_a, rpm_a, cob_a = self._correr("A", matrices, previas)
            obs_b, rpm_b, cob_b = self._correr("B", matrices, previas)
        self.assertEqual(len(obs_a), len(matrices) * R.N_AGENTES)
        self.assertEqual(len(obs_a), len(obs_b))
        for fa, fb in zip(obs_a, obs_b):
            self.assertEqual(fa[:2], fb[:2])
            for xa, xb in zip(fa[2:6], fb[2:6]):
                self.assertTrue(np.array_equal(xa, xb), (fa[:2], xa, xb))
            self.assertEqual(fa[6:], fb[6:])
        self.assertEqual(rpm_a, rpm_b)
        self.assertEqual(cob_a, cob_b)
        self.assertTrue(any(f[6] for f in obs_a), "el episodio tiene que ejercitar el escape")


class PruebaA1CaminoDeLaToma(unittest.TestCase):
    """`demo.correr_toma` llega al lazo de evaluación como `replica_con_capas`:
    los mismos 11 argumentos posicionales a `ses._correr_episodio` (y diag
    None, el default que usa el 30-09), y sin obstáculo devuelve la validez y
    el motivo del lazo sin tocarlos."""

    def test_mismos_argumentos_que_el_3009(self) -> None:
        import types
        import demo_obstaculo_movil as demo
        import sesion_robotat as ses
        llamada = [n for n in ast.walk(_arbol_capas()) if isinstance(n, ast.Call)
                   and ast.unparse(n.func) == "ses._correr_episodio"]
        self.assertEqual(len(llamada), 1)
        self.assertEqual([ast.unparse(x) for x in llamada[0].args],
                         ["coord", "canal", "fuente", "registro", "marca", "DECISIONES",
                          "RPM_ABORTO", "N", "detector", "semilla", "seguimiento"])
        self.assertEqual(llamada[0].keywords, [])
        capt = {}

        def espia(*a, **kw):
            capt["a"], capt["kw"] = a, kw
            return {"valido": 1, "motivo": "", "decisiones": 7}

        class Coord:
            n_agentes = 5
            motivo_aborto_obstaculo = None
            supervisor = None

            def _reiniciar_episodio(self, _s):
                return True

            def resumen_obstaculo(self):
                return {}
        coord, registro = Coord(), []
        canal = types.SimpleNamespace(obstaculo_caido=False)
        fuente = __import__("demo_obstaculo_movil").FuentePosesConObstaculo(5, 4, 4)
        entorno = types.SimpleNamespace(reiniciar_reloj=lambda: None)
        with mock.patch.object(ses, "_correr_episodio", espia):
            res = demo.correr_toma(coord, canal, fuente, entorno, 421000, 500, registro,
                                   200.0, lazo="evaluacion")
        a = capt["a"]
        self.assertEqual(len(a), 11)
        self.assertTrue(a[0] is coord and a[1] is canal and a[2] is fuente and a[3] is registro)
        self.assertEqual((a[4], a[5], a[6], a[7], a[9]), (0, 500, 200.0, 5, 421000))
        self.assertIsInstance(a[8], ses.DetectorCongelamiento)
        self.assertIsInstance(a[10], ses.DetectorSeguimiento)
        self.assertEqual(capt["kw"], {"diag": None})
        self.assertEqual((res["valido"], res["motivo"], res["lazo"]), (1, "", "evaluacion"))


class PruebaCorrerUna(unittest.TestCase):
    """`correr_una` fija, en cada corrida, la rampa, el factor, τ_c, el
    retardo, el supervisor (o ninguno) y el lazo de evaluación, y vacía el
    historial del predictor (sin simulador: la pila es de utilería)."""

    def test_regimen_de_cada_corrida(self) -> None:
        import types
        import numpy as np
        import demo_obstaculo_movil as demo
        import lanzar_robotat
        t = R.cargar_carpeta_vieja(_ENSAYO_VIEJO)[1]
        canal = demo.CanalConObstaculo(5, None, 4, conectar_obstaculo=False)
        canal.detener_todo = lambda silencioso=False: None
        canal.decisiones_enviadas, canal.factor_operativo = 9999, 1.0
        canal.historial_mandos_obstaculo.append((0.0, 0.1, 0.1))

        class Sim:
            fallas = types.SimpleNamespace(retardo_actuacion_s=None)

            def teletransportar_env(self, p):
                self.p = p
        sup = types.SimpleNamespace(traza=[], cargar_traza=lambda tr: None)
        coord = types.SimpleNamespace(supervisor="otro", tau_prediccion_s=0.0)
        pila = R.Pila(Sim(), types.SimpleNamespace(reiniciar=lambda: None), canal, None,
                      coord, sup, [], {"episodio": 0})
        capt = []

        def correr_toma(coord_, canal_, fuente_, entorno_, semilla, decisiones, registro,
                        rpm_aborto, lazo):
            capt.append({"sup": coord_.supervisor, "previas": canal_.decisiones_enviadas,
                         "factor": canal_.factor_operativo, "tau_c": coord_.tau_prediccion_s,
                         "lazo": lazo, "rpm": rpm_aborto, "semilla": semilla,
                         "retardo": pila.sim.fallas.retardo_actuacion_s,
                         "hist": list(canal_.historial_mandos_obstaculo),
                         "estacionado": pila.sim.p[R.ID_OBSTACULO]})
            return {"valido": 1, "motivo": "", "decisiones": decisiones,
                    "cobertura_aoi": 0.3, "frenos": 0, "d_min_obst_medida": 0.3}
        poses = {i: np.array(t.poses_iniciales[i]) for i in range(5)}
        with mock.patch.object(demo, "correr_toma", correr_toma), \
                mock.patch.object(lanzar_robotat, "leer_poses_estables", lambda f, n: poses), \
                mock.patch.object(R.time, "sleep", lambda _s: None), \
                contextlib.redirect_stdout(io.StringIO()):
            con, _, _ = R.correr_una(pila, t, R.CON, 0.45, 1, "normal", "P")
            sin, _, _ = R.correr_una(pila, t, R.SIN, 0.0, 2, "normal", "P")
        c, s_ = capt
        self.assertIs(c["sup"], sup)
        self.assertIsNone(s_["sup"])
        for x in capt:
            self.assertEqual((x["previas"], x["factor"], x["tau_c"], x["lazo"], x["rpm"],
                              x["semilla"], x["hist"]),
                             (t.decisiones_previas, t.factor, t.tau_prediccion_s,
                              "evaluacion", t.rpm_aborto, t.semilla, []))
        self.assertEqual((c["retardo"], s_["retardo"]), (0.45, 0.0))
        self.assertEqual(s_["estacionado"], R.ESTACIONAMIENTO_ENV)
        f0 = t.traza_obstaculo[0]
        self.assertEqual(c["estacionado"], (f0["x"], f0["y"], f0["th"]))
        self.assertEqual((con["tau_s"], sin["tau_s"]), (0.45, 0.0))
        self.assertEqual((sin["d_min_obst_medida"], sin["cierre_b_ok"], sin["frenos_sombra"]),
                         ("", "", ""))
        self.assertEqual(con["frenos_sombra"], 0)
        self.assertEqual([c_ for c_ in A.COLUMNAS_REPLICA if c_ not in con], [])


class PruebaCierreA3(unittest.TestCase):
    """El camino del cierre (a3) con una salida sintética (regla aprobada
    por José el 2026-10-10)."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="replica_a3_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _salida(self, corrimiento: float) -> None:
        import test_analizar_campana_l2 as T
        ref = R._reps_3009(R.DIR_3009)
        filas = []
        for s, ep in R.episodios_a3():
            media = sum(ref[(s, ep)]) / len(ref[(s, ep)])
            for rep, ruido in ((1, -0.001), (2, 0.0), (3, 0.001)):
                f = {c: "" for c in R.columnas_contrato()}
                f.update(id_sesion=f"30-09{s}", intento_campana=ep, condicion=R.SIN,
                         tau_s=0.0, rep=rep, valido=1, cobertura_aoi=media + ruido + corrimiento)
                filas.append(f)
            filas.append(dict(filas[-1], condicion=R.CON, rep=1, cobertura_aoi=0.99))
            filas.append(dict(filas[-1], condicion=R.SIN, tau_s=0.45, rep=1,
                              cobertura_aoi=0.99))
        T.escribir(self.tmp / "x_replica_tomas.csv", filas)

    def test_sin_corrimiento_pasa_y_con_dos_delta_no(self) -> None:
        self._salida(0.0)
        r = R.evaluar_cierre_a3(self.tmp)
        self.assertEqual(r["E"], 12)
        self.assertAlmostEqual(r["media"], 0.0, places=12)
        self.assertTrue(r["pasa"])
        self.assertIn("APROBADA", r["estado"])
        self._salida(2 * R.delta_a3())
        r = R.evaluar_cierre_a3(self.tmp)
        self.assertFalse(r["pasa"])

    def test_incompleto_sin_veredicto_y_codigos(self) -> None:
        import test_analizar_campana_l2 as T
        self._salida(0.0)
        filas = R._leer(self.tmp / "x_replica_tomas.csv")
        T.escribir(self.tmp / "x_replica_tomas.csv",
                   [f for f in filas if f["intento_campana"] != "12"])
        r = R.evaluar_cierre_a3(self.tmp)
        self.assertIsNone(r["pasa"])
        self.assertTrue(r["faltan"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(R.main(["--evaluar-a3", str(self.tmp)]), 3)
        self._salida(2 * R.delta_a3())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(R.main(["--evaluar-a3", str(self.tmp)]), 1)
        self._salida(0.0)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(R.main(["--evaluar-a3", str(self.tmp)]), 0)
        # Cada evaluación en su archivo: nada se pisa.
        self.assertEqual(len(list(self.tmp.glob("cierre_a3_*.json"))), 3)
        # Dos pilas: sin veredicto.
        filas = R._leer(self.tmp / "x_replica_tomas.csv")
        filas[0]["sha256_pila"] = "otra"
        T.escribir(self.tmp / "x_replica_tomas.csv", filas)
        self.assertIsNone(R.evaluar_cierre_a3(self.tmp)["pasa"])

    def test_seleccion_y_delta(self) -> None:
        sel = R.episodios_a3()
        self.assertEqual(len(sel), 12)
        self.assertEqual(len({e for _s, e in sel}), 12)
        self.assertEqual(round(R.delta_a3(), 5), 0.00827)


if __name__ == "__main__":
    unittest.main(verbosity=2)
