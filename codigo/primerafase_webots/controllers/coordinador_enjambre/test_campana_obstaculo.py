"""
test_campana_obstaculo.py
=========================
Pruebas de la CAMPAÑA DE MEDICIÓN L2 con el obstáculo móvil (OK de José,
2026-10-08; `tesis/PROPUESTA_campana_L2_obstaculo.md`):

  · el libro (`campana_obstaculo.py`): semillas únicas también al cortar y
    reanudar, reservas interrumpidas, hash de los archivos congelados que
    bloquea y su corrección declarada, configuración del día que NO
    bloquea, candado, copias en conflicto, cierre con motivo, meta/tope/
    hora de fin, inclusión (frenos y contactos no excluyen);
  · el registro de la toma (`columnas_registro_toma`): igual BIT A BIT al
    bloque del 30-09 en `sesion_robotat.py` (extraído con `ast`), y en una
    sesión real contra el simulador, x0 = pose de la decisión 0, la pose
    medida del obstáculo = paso 0 de su traza, `decisiones_previas` = la
    rampa, `id_sesion` en los tres CSV;
  · la sesión de campaña contra el simulador: intentos y semillas del
    libro, corte y reanudación, cadena de frenos arrastrada del libro;
  · la línea de comandos: la campaña exige la L0 OK (--forzar no la
    saltea), la hora de fin y no acepta --tomas/--intentos/--intento-inicial.

    python -m unittest test_campana_obstaculo -v

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import ast
import contextlib
import csv
import io
import json
import math
import shutil
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

import numpy as np

import campana_obstaculo as CO
import config_robotat as cfg
import demo_obstaculo_movil as demo
import test_demo_obstaculo_movil as T

_CARPETA = Path(__file__).resolve().parent


def _silencio():
    return contextlib.redirect_stdout(io.StringIO())


class BaseLibro(unittest.TestCase):
    """Un directorio temporal y una lista de archivos congelados propia."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="campana_test_"))
        self.congelados = []
        for k in range(3):
            f = self.tmp / f"congelado_{k}.txt"
            f.write_text(f"contenido {k}", encoding="utf-8")
            self.congelados.append(str(f))
        self._p = mock.patch.object(CO, "ARCHIVOS_CONGELADOS",
                                    tuple(self.congelados))
        self._p.start()

    def tearDown(self) -> None:
        self._p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def crear(self, **kw) -> CO.Campana:
        kw.setdefault("meta", 3)
        kw.setdefault("minimo", 2)
        kw.setdefault("tope", 6)
        return CO.Campana.crear(self.tmp, "prueba", "simulador", 4, 4, **kw)

    def abrir(self, c: Optional[CO.Campana] = None,
              minutos: float = 30.0, sesion: str = "s1") -> CO.Campana:
        c = c or CO.Campana(CO.Campana.carpeta_de(self.tmp, "prueba"))
        c.abrir_sesion("simulador", 4, datetime.now() + timedelta(minutes=minutos),
                       sesion)
        return c

    @staticmethod
    def res(**kw) -> Dict[str, Any]:
        r = {"toma": 0, "valido": 1, "decisiones": 500, "frenos": 0,
             "obst_modo": "movil", "obst_recorrido_m": 2.4,
             "obst_recorrido_comandado_m": 2.5, "valido_demo": 1,
             "d_min_obst_medida": 0.3, "motivo": ""}
        r.update(kw)
        r["incluida"], r["motivo_inclusion"] = CO.inclusion_campana(r)
        return r


class PruebaInclusion(unittest.TestCase):

    def test_valida_y_en_marcha(self) -> None:
        self.assertEqual(CO.inclusion_campana(BaseLibro.res())[0], 1)

    def test_frenos_y_contactos_no_excluyen(self) -> None:
        r = BaseLibro.res(frenos=2, d_min_obst_medida=0.12, valido_demo=0)
        self.assertEqual(CO.inclusion_campana(r)[0], 1)

    def test_no_valida_no_entra(self) -> None:
        r = BaseLibro.res(valido=0, motivo="antigüedad de pose")
        incl, motivo = CO.inclusion_campana(r)
        self.assertEqual(incl, 0)
        self.assertIn("antigüedad", motivo)

    def test_recorrido_minimo_solo_con_020_comandados(self) -> None:
        self.assertEqual(CO.inclusion_campana(BaseLibro.res(
            obst_recorrido_m=1.0, obst_recorrido_comandado_m=2.5))[0], 0)
        # Comandado < 0.20 m (decisión 1 de José): no se exige recorrido.
        self.assertEqual(CO.inclusion_campana(BaseLibro.res(
            obst_recorrido_m=0.0, obst_recorrido_comandado_m=0.19))[0], 1)


class PruebaLibro(BaseLibro):

    def test_campana_vieja_conserva_su_bloque(self) -> None:
        """Una campaña creada con el bloque viejo (421000, como la descartada
        `L2_obstaculo`) sigue con el de su cabecera aunque la constante cambie."""
        with mock.patch.object(CO, "SEMILLA_BASE", 421000):
            self.crear()
        c = self.abrir()
        self.assertEqual(next(c.plan_de_intentos()), (1, 421000))
        c.cerrar_sesion("fin")

    def test_semillas_del_bloque_nuevo_y_reservas(self) -> None:
        c = self.abrir(self.crear())
        # Bloque nuevo por decisión de José (17-10).
        self.assertEqual((CO.SEMILLA_BASE, c.cabecera["semilla_base"]), (422000, 422000))
        plan = c.plan_de_intentos()
        k1, s1 = next(plan)
        c.registrar(k1, s1, self.res(toma=k1), "x.csv")
        k2, s2 = next(plan)
        self.assertEqual((k1, s1, k2, s2), (1, CO.SEMILLA_BASE, 2, CO.SEMILLA_BASE + 1))
        tipos = [f["tipo"] for f in c.filas()]
        self.assertEqual(tipos.count("reserva"), 2)
        c.cerrar_sesion("fin")
        # La 2.ª reserva quedó sin resultado: interrumpida, semilla gastada.
        fila2 = [f for f in c.filas() if f["tipo"] == "resultado"
                 and f["intento"] == "2"]
        self.assertEqual(fila2[0]["estado"], "interrumpida")
        # Reanudar: sigue en el intento 3, semilla base + 2.
        c2 = self.abrir(sesion="s2")
        k3, s3 = next(c2.plan_de_intentos())
        self.assertEqual((k3, s3), (3, CO.SEMILLA_BASE + 2))
        c2.cerrar_sesion("fin")

    def test_meta_tope_y_hora_de_fin(self) -> None:
        c = self.abrir(self.crear(meta=2, minimo=1, tope=3))
        plan = c.plan_de_intentos()
        for _ in range(2):
            k, s = next(plan)
            c.registrar(k, s, self.res(toma=k), "x.csv")
        self.assertIsNone(next(plan, None))
        self.assertIn("META", c.motivo_fin)
        self.assertEqual(c.veredicto(), "META")
        c.cerrar_sesion("fin")
        # Tope: 3 intentos sin incluir ninguno.
        shutil.rmtree(self.tmp / "campanas")
        c = self.abrir(self.crear(meta=2, minimo=1, tope=3))
        plan = c.plan_de_intentos()
        for _ in range(3):
            k, s = next(plan)
            c.registrar(k, s, self.res(toma=k, valido=0), "x.csv")
        self.assertIsNone(next(plan, None))
        self.assertIn("TOPE", c.motivo_fin)
        self.assertEqual(c.veredicto(), "INCOMPLETA")
        c.cerrar_sesion("fin")
        # Hora de fin: ya pasada no abre; vencida durante la sesión, corta.
        shutil.rmtree(self.tmp / "campanas")
        self.crear()
        with self.assertRaises(CO.ErrorCampana):
            self.abrir(minutos=-1)
        c = self.abrir(minutos=30)
        c.hora_fin = datetime.now() - timedelta(seconds=1)
        self.assertIsNone(next(c.plan_de_intentos(), None))
        self.assertIn("HORA DE FIN", c.motivo_fin)
        c.cerrar_sesion("fin")

    def test_hash_bloquea_y_la_correccion_declarada_destraba(self) -> None:
        self.crear()
        Path(self.congelados[1]).write_text("cambiado", encoding="utf-8")
        with self.assertRaises(CO.ErrorCampana) as e:
            self.abrir()
        self.assertIn("--corregir-campana", str(e.exception))
        with self.assertRaises(CO.ErrorCampana):
            CO.Campana.corregir(self.tmp, "prueba", "  ")
        cambiaron = CO.Campana.corregir(self.tmp, "prueba",
                                        "arreglo de un error menor")
        self.assertEqual(cambiaron, [self.congelados[1]])
        c = self.abrir()
        corr = [f for f in c.filas() if f["tipo"] == "correccion"][0]
        self.assertEqual(corr["motivo"], "arreglo de un error menor")
        self.assertIn(self.congelados[1], json.loads(corr["detalle"])["cambiaron"])
        c.cerrar_sesion("fin")

    def test_la_configuracion_del_dia_se_registra_y_no_bloquea(self) -> None:
        c = self.abrir(self.crear())
        ap = [f for f in c.filas() if f["tipo"] == "apertura"][0]
        conf = json.loads(ap["detalle"])["configuracion"]
        self.assertIn("4", conf["offsets_deg"])
        self.assertIn("config_robotat.py", conf["sha256"])
        c.cerrar_sesion("fin")
        # Un cambio de config_robotat no está en la lista: no bloquea.
        self.assertNotIn("config_robotat.py", CO.ARCHIVOS_CONGELADOS)
        self.assertIn("config_robotat.py", CO.ARCHIVOS_CONFIGURACION)

    def test_candado_conflictos_y_cierre(self) -> None:
        c = self.abrir(self.crear())
        with self.assertRaises(CO.ErrorCampana):
            self.abrir(sesion="s2")                 # candado
        c.cerrar_sesion("fin")
        # Candado huérfano: se libera con motivo, anotado.
        self.abrir(sesion="s3")                     # no se cierra
        CO.Campana.liberar_candado(self.tmp, "prueba", "la sesión murió")
        c4 = self.abrir(sesion="s4")
        c4.cerrar_sesion("fin")
        self.assertTrue(any(f["tipo"] == "candado_liberado" for f in c4.filas()))
        # Copia en conflicto de OneDrive: se niega.
        conflicto = c4.carpeta / "libro-PC.csv"
        conflicto.write_text("x", encoding="utf-8")
        with self.assertRaises(CO.ErrorCampana):
            self.abrir(sesion="s5")
        conflicto.unlink()
        # Cerrar la campaña exige motivo; cerrada, no abre.
        with self.assertRaises(CO.ErrorCampana):
            CO.Campana.cerrar(self.tmp, "prueba", "")
        CO.Campana.cerrar(self.tmp, "prueba", "fin del cuatrimestre")
        with self.assertRaises(CO.ErrorCampana):
            self.abrir(sesion="s6")

    def test_semilla_repetida_o_fuera_de_formula_se_niega(self) -> None:
        c = self.crear()
        c._agregar({"tipo": "reserva", "intento": 1, "semilla": CO.SEMILLA_BASE})
        c._agregar({"tipo": "reserva", "intento": 1, "semilla": CO.SEMILLA_BASE})
        with self.assertRaises(CO.ErrorCampana):
            self.abrir()
        shutil.rmtree(self.tmp / "campanas")
        c = self.crear()
        c._agregar({"tipo": "reserva", "intento": 1, "semilla": 420000})
        with self.assertRaises(CO.ErrorCampana):
            self.abrir()

    def test_plataforma_y_robot_deben_coincidir(self) -> None:
        c = self.crear()
        with self.assertRaises(CO.ErrorCampana):
            c.abrir_sesion("hw", 4, datetime.now() + timedelta(minutes=5), "x")
        with self.assertRaises(CO.ErrorCampana):
            c.abrir_sesion("simulador", 7, datetime.now() + timedelta(minutes=5), "x")

    def test_ultima_linea_truncada_y_frenos_de_la_ultima_corrida(self) -> None:
        c = self.abrir(self.crear())
        k, s = next(c.plan_de_intentos())
        c.registrar(k, s, self.res(toma=k, frenos=1, valido_demo=0), "x.csv")
        self.assertEqual(c.estado()["frenos_ultima_corrida"], 1)
        c.cerrar_sesion("fin")
        with open(c.ruta_libro, "ab") as fh:
            fh.write(b"reserva,2026-10-08T00:00:00,s,9")     # sin fin de línea
        self.assertEqual(c.estado()["frenos_ultima_corrida"], 1)

    def test_crear_exige_los_archivos_congelados(self) -> None:
        Path(self.congelados[0]).unlink()
        with self.assertRaises(CO.ErrorCampana) as e:
            self.crear()
        self.assertIn("faltan archivos congelados", str(e.exception))

    def test_lista_real_de_archivos_congelados(self) -> None:
        """La lista real: el código que carga una sesión, el modelo, el plan
        y el script de análisis; la configuración del día aparte."""
        self._p.stop()
        try:
            for a in ("demo_obstaculo_movil.py", "sesion_robotat.py",
                      "colocacion_con_obstaculo.py", "lib/filtro_cbf.py",
                      "modelos/modelo_sanidad.zip", "analizar_campana_l2.py",
                      "TESIS/PLAN_ANALISIS_campana_L2.md"):
                self.assertIn(a, CO.ARCHIVOS_CONGELADOS)
            self.assertNotIn("config_robotat.py", CO.ARCHIVOS_CONGELADOS)
        finally:
            self._p.start()


class PruebaFilaTomaCortada(unittest.TestCase):

    def test_fila_con_lo_que_alcanzo_a_correr(self) -> None:
        class Coord:
            def resumen_obstaculo(self):
                return {"d_min_obst_medida": 0.11, "formulacion": "F2"}
        registro = [{"paso": "x", "agente": 0, "pose_env_x": 9, "pose_env_y": 9}]
        for paso in range(3):
            for i in range(5):
                x = 0.5 + 0.5 * i if not (paso == 2 and i == 1) else 0.6
                registro.append({"paso": paso, "agente": i, "pose_env_x": x,
                                 "pose_env_y": 0.5})
        r = demo.fila_toma_cortada(Coord(), registro, 1, CO.SEMILLA_BASE, KeyboardInterrupt())
        self.assertEqual((r["valido"], r["decisiones"], r["colisiones_015"],
                          r["d_min_obst_medida"], r["lazo"]), (0, 3, 1, 0.11, "evaluacion"))
        self.assertIn("CORTADA", r["motivo"])
        self.assertEqual(CO.contacto_de_toma(r)[0], 1)
        self.assertEqual(demo.fila_toma_cortada(Coord(), registro, len(registro), 1,
                                                OSError("x"))["decisiones"], "")


class PruebaEscrituraAtomicaCSV(unittest.TestCase):

    def test_atomica_y_con_reintentos(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="csv_atomico_"))
        try:
            ruta = tmp / "x_L2_tomas.csv"
            real = demo.os.replace
            fallas = {"n": 2}

            def replace_bloqueado(a, b):
                if fallas["n"]:
                    fallas["n"] -= 1
                    raise PermissionError("abierto en Excel")
                return real(a, b)
            salida = io.StringIO()
            with mock.patch.object(demo.os, "replace", replace_bloqueado), \
                    mock.patch.object(demo, "ESPERA_REINTENTO_CSV_S", 0.01), \
                    contextlib.redirect_stdout(salida):
                demo.escribir_csv(ruta, [{"toma": 1, "d": 0.1234567890123}])
            self.assertIn("bloqueado", salida.getvalue())
            self.assertEqual(R_leer(ruta), [{"toma": "1", "d": "0.1234567890123"}])
            self.assertEqual(list(tmp.glob("*.tmp")), [])
            demo.escribir_csv(ruta, [])
            self.assertEqual(ruta.read_bytes(), b"")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def R_leer(ruta):
    with open(ruta, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class PruebaRegistroIgualAl3009(unittest.TestCase):
    """`columnas_registro_toma` da, por agente, lo MISMO que el bloque de
    `sesion_robotat.sesion_evaluacion` del 30-09 (extraído con `ast`)."""

    def _bloque_3009(self):
        fuente = (_CARPETA / "sesion_robotat.py").read_bytes().decode("utf-8")
        arbol = ast.parse(fuente)
        for nodo in ast.walk(arbol):
            if (isinstance(nodo, ast.For) and isinstance(nodo.target, ast.Name)
                    and nodo.target.id == "i"
                    and "robot_a" in ast.unparse(nodo)
                    and "x0_a" in ast.unparse(nodo)):
                return compile(ast.Module(body=[nodo], type_ignores=[]),
                               "bloque_3009", "exec")
        self.fail("no se encontró el bloque del 30-09 en sesion_robotat.py")

    def test_bit_a_bit(self) -> None:
        codigo = self._bloque_3009()
        poses = {0: np.array([0.51, 0.62, 1.1]), 1: np.array([2.4, 0.5, -2.0]),
                 3: np.array([0.7, 2.2, 0.3]), 4: np.array([1.9, 1.1, 3.0])}
        ns = {"cfg": cfg, "math": math, "n_agentes": 5, "poses_ini": poses,
              "res": {}}
        exec(codigo, ns)
        mio = demo.columnas_registro_toma(poses, None, 4, 4, 0, 200.0, 0.65, 5)
        agentes = {k: v for k, v in mio.items() if k.endswith(
            tuple(f"_a{i}" for i in range(5)))}
        self.assertEqual(list(agentes.items()), list(ns["res"].items()))

    def test_columnas_del_obstaculo_y_regimen(self) -> None:
        r = demo.columnas_registro_toma({}, np.array([1.5, 0.9, 0.1]), 4, 4,
                                        50, 200.0, 0.65, 5)
        self.assertEqual((r["obst_robot"], r["obst_marcador"]), (4, 4))
        self.assertEqual((r["obst_x0_med"], r["obst_y0_med"], r["obst_th0_med"]),
                         (1.5, 0.9, 0.1))
        self.assertEqual((r["rpm_aborto"], r["tau_prediccion_s"],
                          r["decisiones_previas"]), (200.0, 0.65, 50))
        self.assertAlmostEqual(r["obst_offset_deg"], round(math.degrees(
            cfg.offset_rumbo_de_robot(4)), 4))


class BaseSesionCampana(T.BaseColocacion):
    """Sesiones contra el simulador, con el libro en el temporal."""

    def setUp(self) -> None:
        super().setUp()
        self.congelados = []
        for k in range(2):
            f = self.tmp / f"congelado_{k}.txt"
            f.write_text(f"c{k}", encoding="utf-8")
            self.congelados.append(str(f))
        self._parches = [
            mock.patch.object(CO, "ARCHIVOS_CONGELADOS", tuple(self.congelados)),
            mock.patch.object(demo.atexit, "register", lambda f, *a, **k: f),
        ]
        for pa in self._parches:
            pa.start()

    def tearDown(self) -> None:
        for pa in self._parches:
            pa.stop()
        super().tearDown()

    def _ctx(self, preguntar=None):
        import sesion_robotat as ses
        return ses.Contexto(sesion="prueba_campana",
                            id_robot=demo.ID_ROBOT_OBSTACULO,
                            marcador=demo.ID_MARCADOR_OBSTACULO, simulador=True,
                            preguntar=preguntar or (lambda _m: ""))

    def _csv(self, patron: str) -> List[Dict[str, str]]:
        ruta = sorted(self.tmp.glob(patron))[-1]
        with open(ruta, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))


class PruebaRegistroEnSesion(BaseSesionCampana):
    """El registro en una sesión L2 real (2 tomas) contra el simulador."""

    def test_registro_de_dos_tomas(self) -> None:
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        self.levantar_zm(self.poses_lejos(), (p0[0], p0[1], r0), 0.45, 0.45)
        with _silencio():
            r = demo.sesion_demo(self._ctx(), "L2", tomas=2, intentos_max=2,
                                 decisiones=60, colocacion="auto")
        self.assertEqual(r["veredicto"], "OK", r["detalle"])
        tomas = self._csv("*L2_tomas*.csv")
        dec = self._csv("*L2_decisiones*.csv")
        obst = self._csv("*L2_obstaculo*.csv")
        ids = {f["id_sesion"] for f in tomas + dec + obst}
        self.assertEqual(ids, {r["id_sesion"]})
        for t in tomas:
            k = t["toma"]
            for i in range(5):
                d0 = [f for f in dec if f["episodio"] == k and f["agente"] == str(i)
                      and f["paso"] == "0"][0]
                dist = math.hypot(float(t[f"x0_a{i}"]) - float(d0["pose_env_x"]),
                                  float(t[f"y0_a{i}"]) - float(d0["pose_env_y"]))
                self.assertLess(dist, 0.001)
                self.assertEqual(t[f"robot_a{i}"], d0["robot"])
            o0 = [f for f in obst if f["toma"] == k and f["paso"] == "0"][0]
            self.assertLess(math.hypot(float(t["obst_x0_med"]) - float(o0["x"]),
                                       float(t["obst_y0_med"]) - float(o0["y"])),
                            0.001)
            self.assertEqual(t["obst_robot"], str(demo.ID_ROBOT_OBSTACULO))
        # La rampa: 0 decisiones previas en la 1.ª, las de la 1.ª en la 2.ª.
        self.assertEqual(tomas[0]["decisiones_previas"], "0")
        self.assertEqual(tomas[1]["decisiones_previas"], tomas[0]["decisiones"])


class PruebaSesionDeCampana(BaseSesionCampana):
    """La sesión de campaña: intentos y semillas del libro, corte y
    reanudación, CSV con los campos de la campaña."""

    def _campana(self, **kw) -> CO.Campana:
        kw.setdefault("meta", 2)
        kw.setdefault("minimo", 1)
        kw.setdefault("tope", 5)
        return CO.Campana.crear(self.tmp, "c", "simulador",
                                demo.ID_ROBOT_OBSTACULO,
                                demo.ID_MARCADOR_OBSTACULO, **kw)

    def _abrir(self, sesion: str) -> CO.Campana:
        c = CO.Campana(CO.Campana.carpeta_de(self.tmp, "c"))
        c.abrir_sesion("simulador", demo.ID_ROBOT_OBSTACULO,
                       datetime.now() + timedelta(minutes=30), sesion)
        return c

    def test_corte_y_reanudacion_sin_repetir_semillas(self) -> None:
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        self.levantar_zm(self.poses_lejos(), (p0[0], p0[1], r0), 0.45, 0.45)
        self._campana()
        # Sesión 1: Ctrl+C en el Enter de la colocación del 2.º intento.
        enters = {"n": 0}

        def corta(m: str) -> str:
            if "van a ir SOLOS" in m:
                enters["n"] += 1
                if enters["n"] == 2:
                    raise KeyboardInterrupt
            return ""
        c1 = self._abrir("s1")
        with _silencio(), self.assertRaises(KeyboardInterrupt):
            try:
                demo.sesion_demo(self._ctx(corta), "L2", decisiones=60,
                                 colocacion="auto", campana=c1, id_sesion="s1")
            finally:
                c1.cerrar_sesion("Ctrl+C")
        filas = c1.filas()
        res = {f["intento"]: f for f in filas if f["tipo"] == "resultado"}
        self.assertEqual(res["1"]["estado"], "corrida")
        self.assertEqual(res["2"]["estado"], "interrumpida")
        # Sesión 2: sigue en el intento 3 hasta la meta (2 incluidas).
        c2 = self._abrir("s2")
        try:
            with _silencio():
                r = demo.sesion_demo(self._ctx(), "L2", decisiones=60,
                                     colocacion="auto", campana=c2,
                                     id_sesion="s2")
        finally:
            c2.cerrar_sesion("fin")
        self.assertEqual(r["veredicto"], "META", r["detalle"])
        reservas = [(int(f["intento"]), int(f["semilla"]))
                    for f in c2.filas() if f["tipo"] == "reserva"]
        self.assertEqual(reservas, [(k, CO.SEMILLA_BASE + k - 1) for k in (1, 2, 3)])
        tomas2 = self._csv("*L2_tomas*.csv")
        self.assertEqual([t["intento_campana"] for t in tomas2], ["3"])
        self.assertEqual(tomas2[0]["semilla"], str(CO.SEMILLA_BASE + 2))
        self.assertEqual(tomas2[0]["incluida"], "1")
        self.assertEqual(tomas2[0]["campana"], "c")

    def test_la_cadena_de_frenos_se_arrastra_del_libro(self) -> None:
        """La última corrida del libro tuvo freno: la 1.ª toma de la sesión
        nueva con freno dispara 'FRENO en 2 tomas seguidas'."""
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        self.levantar_zm(self.poses_lejos(), (p0[0], p0[1], r0), 0.45, 0.45)
        c = self._campana(meta=3)
        c0 = self._abrir("s0")
        k, s = next(c0.plan_de_intentos())
        c0.registrar(k, s, BaseLibro.res(toma=k, frenos=1, valido_demo=0), "x")
        c0.cerrar_sesion("fin")
        orig = demo.correr_toma

        def con_freno(*a, **kw):
            r = orig(*a, **kw)
            r["frenos"] = 1
            r["valido_demo"], r["motivo_demo"] = demo.validez_demo(r)
            return r
        c1 = self._abrir("s1")
        try:
            with _silencio(), mock.patch.object(demo, "correr_toma", con_freno):
                r = demo.sesion_demo(self._ctx(), "L2", decisiones=40,
                                     colocacion="auto", campana=c1,
                                     id_sesion="s1")
        finally:
            c1.cerrar_sesion("fin")
        self.assertEqual(r["veredicto"], "DETENIDA", r["detalle"])
        self.assertIn("FRENO DE RESPALDO en 2 tomas seguidas",
                      r["tomas"][0]["regla_parada"])
        # Igual quedó incluida: los frenos son resultados.
        self.assertEqual(r["tomas"][0]["incluida"], 1)

    def test_ctrl_c_en_la_pausa_no_pierde_la_toma(self) -> None:
        """Una toma con contacto dispara la pausa y el operador corta con
        Ctrl+C en la pregunta: la toma igual queda en el libro (corrida,
        incluida, con la respuesta) y su fila del CSV con id_sesion."""
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        self.levantar_zm(self.poses_lejos(), (p0[0], p0[1], r0), 0.45, 0.45)
        self._campana()
        orig = demo.correr_toma

        def con_contacto(*a, **kw):
            r = orig(*a, **kw)
            r["d_min_obst_medida"] = 0.12
            r["valido_demo"], r["motivo_demo"] = demo.validez_demo(r)
            return r

        def corta(m: str) -> str:
            if "¿Seguir con la sesión?" in m:
                raise KeyboardInterrupt
            return ""
        c1 = self._abrir("s1")
        try:
            with _silencio(), mock.patch.object(demo, "correr_toma", con_contacto), \
                    self.assertRaises(KeyboardInterrupt):
                demo.sesion_demo(self._ctx(corta), "L2", decisiones=40,
                                 colocacion="auto", campana=c1, id_sesion="s1")
        finally:
            c1.cerrar_sesion("Ctrl+C")
        res = [f for f in c1.filas() if f["tipo"] == "resultado"]
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["estado"], "corrida")
        self.assertEqual(res[0]["incluida"], "1")
        self.assertIn("CONTACTO", res[0]["regla_parada"].upper())
        pausa = [f for f in c1.filas() if f["tipo"] == "pausa"]
        self.assertEqual([(f["intento"], f["parada_respuesta"]) for f in pausa],
                         [("1", "interrumpida (Ctrl+C) en la pausa")])
        # El resultado se anotó ANTES de la pausa (el criterio ya lo cuenta).
        tipos = [f["tipo"] for f in c1.filas()]
        self.assertLess(tipos.index("resultado"), tipos.index("pausa"))
        tomas = self._csv("*L2_tomas*.csv")
        self.assertEqual(tomas[0]["id_sesion"], "s1")
        self.assertEqual(tomas[0]["intento_campana"], "1")

    def test_criterio_de_seguridad_cierra_aunque_el_operador_siga(self) -> None:
        """Dos tomas con contacto; en cada pausa el operador contesta "s":
        igual, al anotar la segunda, el libro cierra la campaña y la sesión
        no corre ningún intento más."""
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        self.levantar_zm(self.poses_lejos(), (p0[0], p0[1], r0), 0.45, 0.45)
        self._campana(meta=5)
        orig = demo.correr_toma

        def con_contacto(*a, **kw):
            r = orig(*a, **kw)
            r["d_min_obst_medida"] = 0.12
            r["valido_demo"], r["motivo_demo"] = demo.validez_demo(r)
            return r

        def sigue(m: str) -> str:
            return "s" if "¿Seguir con la sesión?" in m else ""
        c1 = self._abrir("s1")
        try:
            with _silencio(), mock.patch.object(demo, "correr_toma", con_contacto):
                r = demo.sesion_demo(self._ctx(sigue), "L2", decisiones=40,
                                     colocacion="auto", campana=c1, id_sesion="s1")
        finally:
            c1.cerrar_sesion("fin")
        self.assertIn("CAMPAÑA CERRADA POR EL CRITERIO DE SEGURIDAD", r["detalle"])
        res = [f for f in c1.filas() if f["tipo"] == "resultado"]
        self.assertEqual([f["contacto"] for f in res], ["1", "1"])
        self.assertTrue(c1.estado()["cerrada"])
        self.assertEqual([f["parada_respuesta"] for f in c1.filas() if f["tipo"] == "pausa"],
                         ["siguió", "siguió"])

    def test_toma_cortada_a_mitad_cuenta_y_cierra(self) -> None:
        """Ya hay un contacto en el libro; la toma siguiente tiene contacto y
        el operador la corta con Ctrl+C A MITAD: la toma se anota como corrida
        (cortada, no válida) y el criterio cierra la campaña."""
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        self.levantar_zm(self.poses_lejos(), (p0[0], p0[1], r0), 0.45, 0.45)
        c = self._campana(meta=5)
        c0 = self._abrir("s0")
        k, s = next(c0.plan_de_intentos())
        c0.registrar(k, s, BaseLibro.res(toma=k, d_min_obst_medida=0.1), "x")
        c0.cerrar_sesion("fin")
        orig = demo.correr_toma

        def corta_a_mitad(coord, canal, fuente, entorno, semilla, decisiones, registro,
                          *a, **kw):
            orig(coord, canal, fuente, entorno, semilla, 20, registro, *a, **kw)
            coord.d_min_obst_medida[0] = 0.12
            raise KeyboardInterrupt
        c1 = self._abrir("s1")
        try:
            with _silencio(), mock.patch.object(demo, "correr_toma", corta_a_mitad), \
                    self.assertRaises(KeyboardInterrupt):
                demo.sesion_demo(self._ctx(), "L2", decisiones=40, colocacion="auto",
                                 campana=c1, id_sesion="s1")
        finally:
            c1.cerrar_sesion("Ctrl+C")
        res = [f for f in c1.filas() if f["tipo"] == "resultado"]
        self.assertEqual([(f["estado"], f["contacto"]) for f in res],
                         [("corrida", "1"), ("corrida", "1")])
        self.assertIn("CORTADA", res[1]["motivo"])
        self.assertEqual(res[1]["incluida"], "0")
        self.assertTrue(c1.estado()["cerrada"])
        tomas = self._csv("*L2_tomas*.csv")
        self.assertEqual(tomas[-1]["toma_cortada"], "1")


class PruebaLineaDeComandosCampana(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="campana_cli_"))
        self.previo = demo.DIR_SALIDA_DEMO
        demo.DIR_SALIDA_DEMO = self.tmp
        # La calibración guardada del laboratorio NO se aplica al `cfg`
        # global en estas pruebas (contaminaría las del simulador).
        import calibracion_sesion as calib
        self._p_calib = mock.patch.object(calib, "aplicar_a_config", lambda: [])
        self._p_calib.start()

    def tearDown(self) -> None:
        self._p_calib.stop()
        demo.DIR_SALIDA_DEMO = self.previo
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _main(self, *args) -> int:
        with _silencio():
            return demo.main(["--modo", "L2", "--robot-obstaculo", "4", *args])

    def _l0_ok(self, **kw) -> None:
        fila = {"veredicto": "OK", "detalle": "x", "robot": 4, "marcador": 4,
                "offset_dif_deg": 0.5, "offset_pares": 40}
        fila.update(kw)
        demo.escribir_csv(demo.ruta_salida_demo("L0", "resumen", self.tmp), [fila])

    @staticmethod
    def _hora(delta_min: float) -> str:
        return f"{datetime.now() + timedelta(minutes=delta_min):%H:%M}"

    def test_la_campana_exige_la_l0_y_forzar_no_la_saltea(self) -> None:
        self.assertEqual(self._main("--campana", "x", "--crear-campana"), 6)
        self.assertEqual(self._main("--campana", "x", "--crear-campana",
                                    "--forzar"), 6)

    def test_l0_del_simulador_o_con_otro_offset_no_habilita(self) -> None:
        self._l0_ok(simulador=1)
        self.assertFalse(demo.l0_habilita(4, self.tmp)[0])
        tabla = round(math.degrees(cfg.offset_rumbo_de_robot(4)), 4)
        self._l0_ok(simulador=0, offset_tabla_deg=tabla + 2.0)
        ok, motivo = demo.l0_habilita(4, self.tmp)
        self.assertFalse(ok)
        self.assertIn("repetir la L0", motivo)
        self._l0_ok(simulador=0, offset_tabla_deg=tabla)
        self.assertTrue(demo.l0_habilita(4, self.tmp)[0])
        self.assertEqual(demo.ultima_l0(4, self.tmp)["offset_tabla_deg"], str(tabla))

    def test_hora_de_fin_y_banderas_que_fija_el_plan(self) -> None:
        self._l0_ok()
        with mock.patch.object(CO, "ARCHIVOS_CONGELADOS", ()):
            self.assertEqual(self._main("--campana", "x", "--crear-campana"), 0)
            self.assertEqual(self._main("--campana", "x"), 2)          # sin hora
            hora = self._hora(60)
            for bandera in (("--tomas", "5"), ("--tomas", "3"), ("--factor", "0.4"),
                            ("--decisiones", "300"), ("--colocacion", "auto"),
                            ("--intento-inicial", "1"), ("--forzar",)):
                self.assertEqual(self._main("--campana", "x", "--hora-fin", hora,
                                            *bandera), 2, bandera)
            # Una hora "pasada" se toma como de mañana; a más de 12 h, se niega.
            self.assertEqual(self._main("--campana", "x", "--hora-fin",
                                        self._hora(-60)), 2)
            self.assertEqual(self._main("--campana", "noexiste", "--hora-fin", hora), 7)
            self.assertEqual(self._main("--campana", "x", "--cerrar-campana",
                                        "prueba"), 0)
            self.assertEqual(self._main("--campana", "x", "--hora-fin", hora), 7)

    def test_liberar_sin_candado_lo_dice(self) -> None:
        self._l0_ok()
        with mock.patch.object(CO, "ARCHIVOS_CONGELADOS", ()):
            self._main("--campana", "x", "--crear-campana")
            salida = io.StringIO()
            with contextlib.redirect_stdout(salida):
                demo.main(["--modo", "L2", "--robot-obstaculo", "4", "--campana", "x",
                           "--liberar-candado", "prueba"])
        self.assertIn("no había candado", salida.getvalue())

    def test_la_calibracion_se_aplica_antes_de_abrir(self) -> None:
        """El libro anota los offsets EFECTIVOS (con la calibración ya
        aplicada), no los de la tabla."""
        import calibracion_sesion as calib
        import sesion_robotat as ses
        self._l0_ok()

        def calibrar():
            cfg.OFFSETS_RUMBO_POR_ROBOT[1] = math.radians(11.0)
            return ["offset_heading_rad"]
        with mock.patch.object(CO, "ARCHIVOS_CONGELADOS", ()), \
                mock.patch.dict(cfg.OFFSETS_RUMBO_POR_ROBOT), \
                mock.patch.object(calib, "aplicar_a_config", calibrar), \
                mock.patch.object(ses, "_preparar",
                                  side_effect=ConnectionError("fin de la prueba")):
            self._main("--campana", "x", "--crear-campana")
            self._main("--campana", "x", "--hora-fin", self._hora(60))
        c = CO.Campana(CO.Campana.carpeta_de(self.tmp, "x"))
        ap = [f for f in c.filas() if f["tipo"] == "apertura"][-1]
        conf = json.loads(ap["detalle"])["configuracion"]
        self.assertEqual(conf["offsets_deg"]["1"], 11.0)
        self.assertIn("ESCALA_POSICION", conf["marco"])

    def test_un_error_al_preparar_no_deja_el_candado(self) -> None:
        """Con la sesión de campaña abierta, un error de enlace al preparar o
        una calibración faltante cierran la sesión y liberan el candado."""
        self._l0_ok()
        import calibracion_sesion as calib
        import sesion_robotat as ses
        hora = self._hora(60)
        with mock.patch.object(CO, "ARCHIVOS_CONGELADOS", ()):
            self.assertEqual(self._main("--campana", "x", "--crear-campana"), 0)
            c = CO.Campana(CO.Campana.carpeta_de(self.tmp, "x"))
            with mock.patch.object(ses, "_preparar",
                                   side_effect=ConnectionError("enlace del robot 9")):
                self.assertEqual(self._main("--campana", "x", "--hora-fin", hora), 5)
            self.assertFalse(c.ruta_candado.exists())
            cierre = [f for f in c.filas() if f["tipo"] == "cierre_sesion"][-1]
            self.assertIn("enlace del robot 9", cierre["motivo"])
            with mock.patch.object(ses, "_preparar", lambda ctx: None), \
                    mock.patch.object(calib, "faltantes", lambda: ["escala"]):
                self.assertEqual(self._main("--campana", "x", "--hora-fin", hora), 3)
            self.assertFalse(c.ruta_candado.exists())
            cierre = [f for f in c.filas() if f["tipo"] == "cierre_sesion"][-1]
            self.assertEqual(cierre["motivo"], "faltan parámetros de calibración")


class PruebaLibroRevision(BaseLibro):
    """Lo que encontró la revisión adversarial del 08-10."""

    def test_huella_de_config_sin_calibracion(self) -> None:
        original = (_CARPETA / "config_robotat.py").read_text(encoding="utf-8")
        ruta = self.tmp / "config_copia.py"
        ruta.write_text(original, encoding="utf-8")
        h0 = CO.huella_sin_calibracion(ruta)
        # Un offset de la tabla, el marco, un comentario: no la mueven.
        for viejo, nuevo in (("TRASLACION_X_M:     float = 1.5",
                              "TRASLACION_X_M:     float = 1.6"),
                             ("OFFSET_HEADING_RAD: float = 0.0",
                              "OFFSET_HEADING_RAD: float = 0.1"),
                             ("DECISIONES_ARRANQUE:       int   = 50",
                              "DECISIONES_ARRANQUE:       int   = 50  # comentario")):
            self.assertEqual(original.count(viejo), 1, viejo)
            ruta.write_text(original.replace(viejo, nuevo), encoding="utf-8")
            self.assertEqual(CO.huella_sin_calibracion(ruta), h0, viejo)
        tabla = "OFFSETS_RUMBO_POR_ROBOT: Dict[int, float] = {"
        self.assertEqual(original.count(tabla), 1)
        ruta.write_text(original.replace(tabla, tabla + "\n    99: 0.5,"), encoding="utf-8")
        self.assertEqual(CO.huella_sin_calibracion(ruta), h0)
        # La rampa sí.
        ruta.write_text(original.replace("DECISIONES_ARRANQUE:       int   = 50",
                                         "DECISIONES_ARRANQUE:       int   = 40"),
                        encoding="utf-8")
        self.assertNotEqual(CO.huella_sin_calibracion(ruta), h0)
        self.assertIn("config_robotat.py#sin_calibracion", self._lista_real())

    def _lista_real(self):
        self._p.stop()
        try:
            return tuple(CO.ARCHIVOS_CONGELADOS)
        finally:
            self._p.start()

    def test_linea_truncada_y_escritura_siguiente(self) -> None:
        c = self.abrir(self.crear())
        with open(c.ruta_libro, "ab") as fh:
            fh.write(b"reserva,2026-10-08T00:00:00,s1,1,4210")   # corte de luz
        c._agregar({"tipo": "candado_liberado", "motivo": "corte"})
        filas = c.filas()
        self.assertEqual(filas[-1]["tipo"], "candado_liberado")
        self.assertEqual(len(c.filas_descartadas), 1)
        c.estado()
        c.cerrar_sesion("fin")

    def test_cabecera_editada_se_nota(self) -> None:
        c = self.crear()
        cab = json.loads(c.ruta_cabecera.read_text(encoding="utf-8"))
        cab["tope_intentos"] = 200
        c.ruta_cabecera.write_text(json.dumps(cab), encoding="utf-8")
        with self.assertRaises(CO.ErrorCampana):
            CO.Campana(c.carpeta)

    def test_cerrar_y_corregir_con_sesion_abierta_se_niegan(self) -> None:
        c = self.abrir(self.crear())
        next(c.plan_de_intentos())
        with self.assertRaises(CO.ErrorCampana):
            CO.Campana.cerrar(self.tmp, "prueba", "x")
        with self.assertRaises(CO.ErrorCampana):
            CO.Campana.corregir(self.tmp, "prueba", "x")
        c.cerrar_sesion("fin")
        CO.Campana.cerrar(self.tmp, "prueba", "x")
        estados = [f["estado"] for f in c.filas() if f["tipo"] == "resultado"]
        self.assertEqual(estados, ["interrumpida"])

    def test_liberar_marca_las_reservas_y_dice_si_habia_candado(self) -> None:
        c = self.crear()
        self.assertFalse(CO.Campana.liberar_candado(self.tmp, "prueba", "x"))
        c = self.abrir(c)
        next(c.plan_de_intentos())
        self.assertTrue(CO.Campana.liberar_candado(self.tmp, "prueba", "murió"))
        res = [f for f in c.filas() if f["tipo"] == "resultado"]
        self.assertEqual(res[0]["estado"], "interrumpida")
        # La sesión "viva" ya no puede anotar, ni borra un candado ajeno.
        with self.assertRaises(CO.ErrorCampana):
            c.registrar(1, CO.SEMILLA_BASE, self.res(toma=1), "x.csv")
        otra = self.abrir(sesion="s2")
        c.cerrar_sesion("fin")
        self.assertTrue(otra.ruta_candado.exists())
        otra.cerrar_sesion("fin")
        self.assertFalse(otra.ruta_candado.exists())

    def test_falla_al_abrir_suelta_el_candado(self) -> None:
        c = self.crear()
        with mock.patch.object(CO, "configuracion_del_dia",
                               side_effect=PermissionError("libro abierto en Excel")):
            with self.assertRaises(CO.ErrorCampana) as e:
                self.abrir(c)
        self.assertIn("Excel", str(e.exception))
        self.assertFalse(c.ruta_candado.exists())

    def test_libro_bloqueado_reintenta_con_aviso(self) -> None:
        import os
        import stat
        c = self.crear()
        os.chmod(c.ruta_libro, stat.S_IREAD)
        try:
            salida = io.StringIO()
            with mock.patch.object(CO, "REINTENTOS_ESCRITURA", 2), \
                    mock.patch.object(CO, "ESPERA_REINTENTO_S", 0.01), \
                    contextlib.redirect_stdout(salida), \
                    self.assertRaises(PermissionError):
                c._agregar({"tipo": "apertura"})
            self.assertIn("bloqueado", salida.getvalue())
        finally:
            os.chmod(c.ruta_libro, stat.S_IREAD | stat.S_IWRITE)

    def test_resultado_repetido_y_campana_cerrada_en_curso(self) -> None:
        c = self.abrir(self.crear())
        plan = c.plan_de_intentos()
        k, s = next(plan)
        c.registrar(k, s, self.res(toma=k), "x.csv")
        with self.assertRaises(CO.ErrorCampana):
            c.registrar(k, s, self.res(toma=k), "x.csv")
        c._agregar({"tipo": "cierre_campana", "motivo": "otra consola"})
        self.assertIsNone(next(plan, None))
        self.assertEqual(c.motivo_fin, "CAMPAÑA CERRADA")
        c.cerrar_sesion("fin")


class PruebaCriterioDeSeguridad(BaseLibro):
    """Criterio de José (09-10): dos tomas CORRIDAS con contacto medido
    (obstáculo < 0.15 m o algún par de agentes < 0.15 m) cierran la campaña
    solas; los contactos de la colocación no cuentan."""

    def test_que_cuenta_como_contacto(self) -> None:
        self.assertEqual(CO.contacto_de_toma({"d_min_obst_medida": 0.149})[0], 1)
        self.assertEqual(CO.contacto_de_toma({"d_min_obst_medida": 0.15})[0], 0)
        self.assertEqual(CO.contacto_de_toma({"d_min_obst_medida": ""})[0], 0)
        # Sin distancia medida, los pares de agentes sí cuentan (José, 10-10).
        self.assertEqual(CO.contacto_de_toma({"d_min_obst_medida": "",
                                              "colisiones_015": 1})[0], 1)
        self.assertEqual(CO.contacto_de_toma({"d_min_obst_medida": 0.3,
                                              "colisiones_015": 1})[0], 1)
        self.assertEqual(CO.contacto_de_toma({"d_min_obst_medida": 0.3,
                                              "colisiones_015": 0})[0], 0)

    def test_dos_contactos_en_sesiones_distintas_cierran_la_campana(self) -> None:
        c = self.abrir(self.crear(meta=10, tope=20))
        plan = c.plan_de_intentos()
        for d in (0.12, 0.3, 0.3):                       # 1 contacto
            k, s = next(plan)
            c.registrar(k, s, self.res(toma=k, d_min_obst_medida=d), "x.csv")
        self.assertFalse(c.estado()["cerrada"])
        self.assertEqual(c.estado()["tomas_con_contacto"], 1)
        c.cerrar_sesion("fin")
        c2 = self.abrir(sesion="s2")
        plan = c2.plan_de_intentos()
        k, s = next(plan)                                 # colocación con contacto: no cuenta
        c2.registrar(k, s, {"toma": k, "valido": 0, "motivo": "colocación: CONTACTO",
                            "d_min_obst_medida": 0.05}, "x.csv")
        k, s = next(plan)                                 # sin correr: no cuenta
        c2.registrar(k, s, {"toma": k, "valido": 0, "motivo": "no arrancó"}, "x.csv")
        self.assertFalse(c2.estado()["cerrada"])
        k, s = next(plan)                                 # 2.º contacto: entre agentes
        c2.registrar(k, s, self.res(toma=k, colisiones_015=1), "x.csv")
        est = c2.estado()
        self.assertTrue(est["cerrada"])
        self.assertTrue(c2.cierre_por_seguridad.startswith(CO.PREFIJO_CIERRE_SEGURIDAD))
        cierre = [f for f in c2.filas() if f["tipo"] == "cierre_campana"][0]
        self.assertIn("intentos 1, 6", cierre["motivo"])
        self.assertEqual([x["intento"] for x in json.loads(cierre["detalle"])["contactos"]],
                         [1, 6])
        self.assertIsNone(next(plan, None))
        self.assertEqual(c2.motivo_fin, "CAMPAÑA CERRADA POR EL CRITERIO DE SEGURIDAD")
        c2.cerrar_sesion("fin")
        with self.assertRaises(CO.ErrorCampana):
            self.abrir(sesion="s3")
    def test_corte_entre_la_segunda_toma_y_su_cierre(self) -> None:
        """Un corte deja el resultado de la 2.ª toma con contacto sin su fila
        de cierre: la sesión siguiente no abre, y el cierre queda escrito."""
        c = self.abrir(self.crear(meta=10, tope=20))
        plan = c.plan_de_intentos()
        k, s = next(plan)
        c.registrar(k, s, self.res(toma=k, d_min_obst_medida=0.1), "x")
        k, s = next(plan)
        with mock.patch.object(CO.Campana, "_aplicar_criterio_de_seguridad",
                               lambda self_: None):       # el "corte"
            c.registrar(k, s, self.res(toma=k, colisiones_015=1), "x")
        c.ruta_candado.unlink()                           # la sesión murió
        with self.assertRaises(CO.ErrorCampana) as e:
            self.abrir(sesion="s2")
        self.assertIn("criterio de seguridad", str(e.exception))
        filas = CO.Campana(c.carpeta).filas()
        self.assertEqual([f["tipo"] for f in filas][-2:], ["resultado", "cierre_campana"])
        with self.assertRaises(CO.ErrorCampana) as e:
            CO.Campana.cerrar(self.tmp, "prueba", "fin")
        self.assertIn("CERRADA", str(e.exception).upper())


    def test_respuesta_de_pausa_formato_viejo_y_prefijo_reservado(self) -> None:
        c = self.abrir(self.crear())
        k, s = next(c.plan_de_intentos())
        c.registrar(k, s, self.res(toma=k), "x")
        c.anotar_respuesta_pausa(k, "siguió")
        self.assertEqual([f["tipo"] for f in c.filas()][-1], "pausa")
        c.cerrar_sesion("fin")
        with self.assertRaises(CO.ErrorCampana):
            CO.Campana.cerrar(self.tmp, "prueba", "criterio de seguridad: a mano")
        # Un libro con las columnas de una versión anterior: no se escribe.
        texto = c.ruta_libro.read_text(encoding="utf-8").split("\n", 1)
        c.ruta_libro.write_text(",".join(CO.COLUMNAS_LIBRO[:-2]) + "\n" + texto[1],
                                encoding="utf-8")
        with self.assertRaises(CO.ErrorCampana) as e:
            c._agregar({"tipo": "apertura"})
        self.assertIn("formato", str(e.exception))

    def test_sesion_de_hardware_exige_la_demo_congelada(self) -> None:
        demo_real = _CARPETA / "demo_obstaculo_movil.py"
        respaldo = sorted(_CARPETA.glob("demo_obstaculo_movil_respaldo_*.py"))[0]
        with mock.patch.object(CO, "ARCHIVOS_CONGELADOS", ("demo_obstaculo_movil.py",)):
            c = CO.Campana.crear(self.tmp, "hwdemo", "hw", 4, 4)
        fin = datetime.now() + timedelta(minutes=30)
        with mock.patch.object(CO, "ARCHIVOS_CONGELADOS", ("demo_obstaculo_movil.py",)):
            with self.assertRaises(CO.ErrorCampana):
                c.abrir_sesion("hw", 4, fin, "s1")                        # sin script
            with self.assertRaises(CO.ErrorCampana):
                c.abrir_sesion("hw", 4, fin, "s1", script=respaldo)       # un respaldo
            c.abrir_sesion("hw", 4, fin, "s1", script=demo_real)
            c.cerrar_sesion("fin")

    def test_un_solo_contacto_no_cierra(self) -> None:
        c = self.abrir(self.crear())
        k, s = next(c.plan_de_intentos())
        c.registrar(k, s, self.res(toma=k, d_min_obst_medida=0.1, colisiones_015=2), "x")
        self.assertFalse(c.estado()["cerrada"])
        fila = [f for f in c.filas() if f["tipo"] == "resultado"][0]
        self.assertEqual((fila["contacto"], fila["colisiones_015"]), ("1", "2"))
        c.cerrar_sesion("fin")


if __name__ == "__main__":
    unittest.main(verbosity=2)
