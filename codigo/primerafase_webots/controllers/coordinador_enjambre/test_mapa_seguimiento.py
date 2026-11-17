"""
test_mapa_seguimiento.py
========================
Pruebas del modo de MAPEO de la sonda (2026-09-24): `mapa_seguimiento.py` y
su integración en `sonda_seguimiento.py`. Corren SIN hardware:

    python test_mapa_seguimiento.py

Lo que más importa:
  1. un tramo sin captura queda en el mapa donde ocurrió: celda de entrada y
     de salida como "borde", las del medio que nunca se vieron como "ciega";
     una retención corta NO cuenta como congelamiento (mismo umbral que la
     alarma);
  2. el contraste de la predicción separa bordes de la dimensión corta y de
     la larga, y la prueba de Fisher da lo que tiene que dar;
  3. contra la "zona sin captura" del simulador, con la sonda de verdad;
  4. nada se pisa: el CSV y el PNG del mapa se crean en modo exclusivo;
  5. (2026-09-25) el ANCHO DE LA FRANJA por lado —el estadístico que ahora
     más informa— sale donde está la franja, con la sonda de verdad contra
     una franja inyectada de 0.30 m; el recorrido en peine cruza cada pared
     en perpendicular; y todo PNG que no es dato del Robotat lleva la marca
     "SIMULADOR — no es dato del Robotat" (o "SINTÉTICO").

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Tuple

_CARPETA = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import config_robotat as cfg
import sonda_seguimiento as sonda
from mapa_seguimiento import (
    LLEGO_A_LA_PARED_M,
    PEINE_DESDE_M,
    SEGMENTO_LADO_M,
    MapaSeguimiento,
    Rejilla,
    arena_en_lab,
    borde_mas_cercano,
    env_a_lab_xy,
    fisher_unilateral,
    franja,
    lab_a_env_xy,
    lado_mas_cercano,
    orden_de_recorrido,
    pases_peine,
    plataforma_por_defecto,
    resumen_congelamientos,
    rotulo_origen,
)
from mapa_seguimiento import (
    clase_de_transicion,
    direccion_en_entorno,
    reduccion_exp_n,
)
from simulador_robotat import FallasSimulador, SimuladorRobotat
from test_diagnostico_poses import ConfigAislada, eventos, puerto_libre


def _mapa_linea(umbral: int = 2) -> MapaSeguimiento:
    """Rejilla de 2 × 1 m con celdas de 0.25 m: 8 × 4."""
    return MapaSeguimiento(Rejilla(-1.0, 1.0, -0.5, 0.5, 0.25), umbral=umbral)


def _recorrer_con_tramo_ciego(mapa: MapaSeguimiento, x_ciego: Tuple[float, float],
                              y: float = 0.1, marcador: int = 1) -> List[str]:
    """
    Un marcador recorre y = `y` de x = −0.95 a +0.95 en pasos de 1 cm. En
    [x_ciego) no se lo ve: la muestra es la última pose viva, repetida.
    """
    eventos_: List[str] = []
    retenida = None
    for j in range(191):
        x = round(-0.95 + 0.01 * j, 6)
        t = 0.05 * j
        if x_ciego[0] <= x < x_ciego[1]:
            ev = mapa.observar(marcador, t, *retenida, repite=True)
        else:
            retenida = (x, y)
            ev = mapa.observar(marcador, t, x, y, repite=False)
        if ev:
            eventos_.append(ev)
    return eventos_


# =============================================================================
# 1. REJILLA Y RECORRIDO
# =============================================================================

class PruebaRejilla(unittest.TestCase):

    def test_la_plataforma_por_defecto(self) -> None:
        r = Rejilla(*plataforma_por_defecto(), celda=0.25)
        self.assertEqual((r.n_x, r.n_y, r.total), (19, 14, 266))
        # La última celda se recorta al borde de la plataforma.
        x0, x1, _y0, _y1 = r.limites(r.n_x - 1, 0)
        self.assertAlmostEqual(x1, cfg.AREA_UTIL_X_M / 2.0)
        self.assertLess(x1 - x0, 0.25)

    def test_indice(self) -> None:
        r = Rejilla(-1.0, 1.0, -0.5, 0.5, 0.25)
        self.assertEqual(r.indice(-1.0, -0.5), (0, 0))
        self.assertEqual(r.indice(1.0, 0.5), (7, 3))       # el borde, adentro
        self.assertEqual(r.indice(0.26, 0.01), (5, 2))
        self.assertIsNone(r.indice(1.01, 0.0))
        self.assertIsNone(r.indice(0.0, -0.51))

    def test_celdas_del_segmento(self) -> None:
        r = Rejilla(-1.0, 1.0, -0.5, 0.5, 0.25)
        self.assertEqual(r.celdas_del_segmento((0.1, 0.1), (0.6, 0.1)),
                         [(4, 2), (5, 2), (6, 2)])
        self.assertEqual(r.celdas_del_segmento((0.1, 0.1), (0.1, 0.1)),
                         [(4, 2)])
        # Lo que cae afuera no cuenta.
        self.assertEqual(r.celdas_del_segmento((0.8, 0.1), (1.4, 0.1)),
                         [(7, 2)])


class PruebaOrdenDeRecorrido(unittest.TestCase):

    def test_cada_celda_una_vez_en_los_dos_modos(self) -> None:
        for nx, ny in ((19, 14), (5, 3), (1, 4), (4, 1), (1, 1)):
            r = Rejilla(0.0, nx * 0.25, 0.0, ny * 0.25, 0.25)
            for modo in ("anillos", "serpentina"):
                with self.subTest(nx=nx, ny=ny, modo=modo):
                    orden = orden_de_recorrido(r, modo)
                    self.assertEqual(len(orden), nx * ny)
                    self.assertEqual(set(orden), {(i, j) for i in range(nx)
                                                  for j in range(ny)})

    def test_los_anillos_empiezan_por_el_perimetro(self) -> None:
        r = Rejilla(0.0, 19 * 0.25, 0.0, 14 * 0.25, 0.25)
        orden = orden_de_recorrido(r, "anillos")
        perimetro = 2 * (19 + 14) - 4
        for ix, iy in orden[:perimetro]:
            self.assertTrue(ix in (0, 18) or iy in (0, 13))
        ix, iy = orden[perimetro]
        self.assertFalse(ix in (0, 18) or iy in (0, 13))

    def test_la_serpentina_alterna_el_sentido(self) -> None:
        r = Rejilla(0.0, 1.0, 0.0, 0.5, 0.25)
        self.assertEqual(orden_de_recorrido(r, "serpentina"),
                         [(0, 0), (1, 0), (2, 0), (3, 0),
                          (3, 1), (2, 1), (1, 1), (0, 1)])

    def test_un_orden_desconocido_no_pasa_callado(self) -> None:
        with self.assertRaises(ValueError):
            orden_de_recorrido(Rejilla(0, 1, 0, 1, 0.25), "espiral")


# =============================================================================
# 2. EL MAPA
# =============================================================================

class PruebaMapa(unittest.TestCase):

    def test_un_tramo_sin_captura_queda_donde_ocurrio(self) -> None:
        mapa = _mapa_linea()
        eventos_ = _recorrer_con_tramo_ciego(mapa, (0.30, 0.80))
        self.assertEqual(eventos_, ["inicio", "fin"])
        (k,) = mapa.congelamientos
        self.assertAlmostEqual(k.x0, 0.29, places=6)     # la última viva
        self.assertAlmostEqual(k.x1, 0.80, places=6)     # la primera al volver
        self.assertAlmostEqual(k.tramo_m, 0.51, places=6)
        self.assertEqual(k.celdas, [(5, 2), (6, 2), (7, 2)])
        self.assertEqual(mapa.estado((5, 2)), "borde")   # entró acá
        self.assertEqual(mapa.estado((6, 2)), "ciega")   # nunca se la vio
        self.assertEqual(mapa.estado((7, 2)), "borde")   # volvió acá
        self.assertEqual(mapa.estado((2, 2)), "viva")
        self.assertEqual(mapa.estado((2, 0)), "sin_visitar")
        self.assertEqual(mapa.celdas[(5, 2)].inicios, 1)
        self.assertEqual(mapa.celdas[(7, 2)].fines, 1)
        self.assertEqual(mapa.congelamientos_de(1), [k])

    def test_una_retencion_corta_no_es_un_congelamiento(self) -> None:
        """Mismo umbral que la alarma: una repetición con umbral 2 no cuenta."""
        mapa = _mapa_linea(umbral=2)
        mapa.observar(1, 0.0, 0.1, 0.1, repite=False)
        mapa.observar(1, 0.05, 0.1, 0.1, repite=True)
        mapa.observar(1, 0.10, 0.12, 0.1, repite=False)
        self.assertEqual(mapa.congelamientos, [])
        self.assertEqual(mapa.celdas[(4, 2)].retenciones_cortas, 1)
        self.assertEqual(mapa.estado((4, 2)), "viva")
        # Con umbral 1, la misma repetición sí es un congelamiento.
        mapa1 = _mapa_linea(umbral=1)
        mapa1.observar(1, 0.0, 0.1, 0.1, repite=False)
        self.assertEqual(mapa1.observar(1, 0.05, 0.1, 0.1, repite=True),
                         "inicio")

    def test_un_congelamiento_sin_volver_queda_abierto(self) -> None:
        mapa = _mapa_linea()
        mapa.observar(1, 0.0, 0.1, 0.1, repite=False)
        for j in range(5):
            mapa.observar(1, 0.05 * (j + 1), 0.1, 0.1, repite=True)
        (k,) = mapa.congelamientos
        self.assertIsNone(k.t_fin)
        self.assertIsNone(k.tramo_m)
        self.assertEqual(mapa.contraste()["sin_terminar"], 1)
        self.assertEqual(mapa.estado((4, 2)), "borde")

    def test_la_proxima_celda_sigue_el_recorrido(self) -> None:
        mapa = _mapa_linea()
        self.assertEqual(mapa.proxima_sin_visitar(), mapa.orden[0])
        x, y = mapa.rejilla.centro(*mapa.orden[0])
        mapa.observar(1, 0.0, x, y, repite=False)
        self.assertEqual(mapa.proxima_sin_visitar(), mapa.orden[1])
        self.assertEqual(mapa.visitadas(), 1)

    def test_ascii(self) -> None:
        mapa = _mapa_linea()
        _recorrer_con_tramo_ciego(mapa, (0.30, 0.80))
        lineas = mapa.ascii({1: (-0.9, 0.1)})
        self.assertEqual(len(lineas), mapa.rejilla.n_y + 1)
        filas = [l.split("|")[1] for l in lineas[:-1]]
        self.assertTrue(all(len(f) == mapa.rejilla.n_x for f in filas))
        texto = "\n".join(filas)
        self.assertEqual(texto.count("█"), 1)
        self.assertEqual(texto.count("◐"), 2)
        self.assertEqual(texto.count("@"), 1)
        self.assertEqual(texto.count("→"), 1)
        # y crece hacia arriba: la fila de abajo es iy = 0, donde empieza el
        # recorrido (→); el robot anda por iy = 2, la segunda desde arriba.
        self.assertEqual(filas[-1][0], "→")
        self.assertEqual(filas[1][0], "@")

    def test_csv_por_celda(self) -> None:
        mapa = _mapa_linea()
        _recorrer_con_tramo_ciego(mapa, (0.30, 0.80))
        buf = io.StringIO()
        self.assertEqual(mapa.escribir_csv(buf), mapa.rejilla.total)
        import csv as _csv
        filas = list(_csv.DictReader(io.StringIO(buf.getvalue())))
        self.assertEqual(len(filas), 32)
        ciega = [f for f in filas if f["estado"] == "ciega"]
        self.assertEqual([(f["ix"], f["iy"]) for f in ciega], [("6", "2")])
        self.assertEqual(ciega[0]["cruces"], "1")
        self.assertEqual(ciega[0]["vivas"], "0")


# =============================================================================
# 3. EL CONTRASTE
# =============================================================================

class PruebaContraste(unittest.TestCase):

    PLATAFORMA = (-2.335, 2.335, -1.725, 1.725)       # 4.67 × 3.45

    def test_borde_mas_cercano_y_dimension(self) -> None:
        d, borde, dim = borde_mas_cercano(0.0, 1.60, self.PLATAFORMA)
        self.assertEqual((borde, dim), ("y+", "corta"))
        self.assertAlmostEqual(d, 0.125)
        d, borde, dim = borde_mas_cercano(-2.20, 0.0, self.PLATAFORMA)
        self.assertEqual((borde, dim), ("x-", "larga"))
        self.assertAlmostEqual(d, 0.135)
        self.assertLess(borde_mas_cercano(0.0, 1.8, self.PLATAFORMA)[0], 0.0)

    def test_franjas(self) -> None:
        self.assertEqual(franja(0.10), "0.00-0.25")
        self.assertEqual(franja(0.25), "0.25-0.50")
        self.assertEqual(franja(0.99), "0.50-1.00")
        self.assertEqual(franja(1.50), ">=1.00")
        self.assertEqual(franja(-0.01), "fuera")

    def test_fisher(self) -> None:
        self.assertAlmostEqual(fisher_unilateral(5, 0, 0, 5), 1 / 252)
        self.assertAlmostEqual(fisher_unilateral(0, 5, 5, 0), 1.0)
        self.assertAlmostEqual(fisher_unilateral(0, 0, 0, 0), 1.0)
        # Un caso a mano: [[3, 1], [1, 3]] → P(X ≥ 3) = (16 + 1) / 70.
        self.assertAlmostEqual(fisher_unilateral(3, 1, 1, 3), 17 / 70)

    def _mapa_con_ciegos(self, filas_iy: List[int],
                         x_ciego: Tuple[float, float]) -> MapaSeguimiento:
        """
        Recorre la plataforma entera, fila por fila por el centro de cada
        una; en las filas `filas_iy`, el tramo `x_ciego` no se ve.
        """
        mapa = MapaSeguimiento(Rejilla(*self.PLATAFORMA, celda=0.25),
                               umbral=2, plataforma=self.PLATAFORMA)
        t = 0.0
        for iy in range(mapa.rejilla.n_y):
            _x, y = mapa.rejilla.centro(0, iy)
            retenida = None
            for j in range(231):
                x = round(-2.30 + 0.02 * j, 6)
                t += 0.05
                if iy in filas_iy and x_ciego[0] <= x < x_ciego[1]:
                    mapa.observar(1, t, *retenida, repite=True)
                else:
                    retenida = (x, y)
                    mapa.observar(1, t, x, y, repite=False)
        return mapa

    def test_ciegos_junto_a_la_dimension_corta(self) -> None:
        # Las dos filas extremas en y (a ~0.1 m del borde y) casi enteras
        # sin captura; los bordes x quedan vistos.
        mapa = self._mapa_con_ciegos([0, 13], (-2.0, 2.0))
        r = mapa.contraste()
        t = r["tabla_cerca"]
        self.assertGreater(t["corta_con"], 0)
        self.assertEqual(t["larga_con"], 0)
        self.assertLess(r["p_fisher_corta_mayor"], 0.001)
        self.assertEqual(r["celdas_visitadas"], r["celdas_total"])
        texto = "\n".join(mapa.lineas_contraste())
        self.assertIn("Fisher", texto)
        self.assertIn("corta", texto)

    def test_sin_las_dos_dimensiones_no_hay_contraste(self) -> None:
        """Sólo se recorrió junto a un borde y: p = None, no un p = 1."""
        mapa = MapaSeguimiento(Rejilla(*self.PLATAFORMA, celda=0.25),
                               umbral=2, plataforma=self.PLATAFORMA)
        for j in range(60):
            mapa.observar(1, 0.05 * j, round(-0.6 + 0.02 * j, 6), 1.6,
                          repite=False)
        r = mapa.contraste()
        self.assertIsNone(r["p_fisher_corta_mayor"])
        self.assertIn("SIN CONTRASTE", "\n".join(mapa.lineas_contraste()))

    def test_ciegos_en_el_centro_no_dan_la_prediccion(self) -> None:
        mapa = self._mapa_con_ciegos([6, 7], (-1.0, -0.3))
        r = mapa.contraste()
        self.assertEqual(r["tabla_cerca"]["corta_con"], 0)
        self.assertAlmostEqual(r["p_fisher_corta_mayor"], 1.0)
        filas = resumen_congelamientos(mapa)
        self.assertEqual(len(filas), 2)
        self.assertTrue(all(f["d_borde_plataforma_m"] > 1.0 for f in filas))


# =============================================================================
# 4. LA SONDA CON MAPA, CONTRA EL SIMULADOR
# =============================================================================

class PruebaSondaConMapa(unittest.TestCase):
    """
    La sonda de verdad contra el simulador: un robot "empujado" en línea
    recta —el hilo mueve su pose, como el dedo del operador— cruza una zona
    sin captura; el mapa tiene que registrar el tramo donde ocurrió.
    """

    def test_el_mapa_registra_el_tramo_sin_captura(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="sonda_mapa_"))
        try:
            with ConfigAislada():
                pp, pb = puerto_libre(), puerto_libre()
                cfg.activar_simulador_local(puerto_poses=pp, puerto_base=pb)
                cfg.MAPEO_AGENTES = {0: cfg.AsignacionAgente(id_marcador=1,
                                                             id_robot=1)}
                cfg.ESCALA_POSICION, cfg.ROTACION_MARCO_RAD = 1.0, 0.0
                cfg.TRASLACION_X_M = cfg.TRASLACION_Y_M = 1.5
                cfg.OFFSET_HEADING_RAD = 0.0
                # Zona x ∈ [0.20, 0.70]: con la rejilla por defecto la celda
                # x ∈ [0.415, 0.665) queda entera adentro.
                fallas = FallasSimulador(
                    modo_marcador_perdido="congelado", ruido_pos_m=0.0005,
                    semilla=5, zona_sin_captura=(0.20, 0.70, -2.0, 2.0))
                sim = SimuladorRobotat({1: 1}, {1: (-0.3, 1.6, 0.0)}, fallas,
                                       puerto_poses=pp, puerto_base=pb)
                parar = threading.Event()

                def empujar() -> None:
                    t0 = time.perf_counter()
                    while not parar.is_set():
                        x = -0.3 + 0.5 * (time.perf_counter() - t0)
                        with sim._lock:
                            sim.robots[1].x = min(x, 1.2)
                        time.sleep(0.005)

                with sim, contextlib.redirect_stdout(io.StringIO()):
                    fuente = sonda.FuenteSonda(1)
                    reg = sonda.crear_registro(tmp / "m.jsonl", [1], [1],
                                               alarma=2)
                    fuente.activar_diagnostico(reg)
                    fuente.conectar()
                    mapa = MapaSeguimiento(
                        Rejilla(*plataforma_por_defecto(), celda=0.25),
                        umbral=2)
                    hilo = threading.Thread(target=empujar, daemon=True)
                    hilo.start()
                    lineas: List[str] = []
                    try:
                        sonda.correr_sonda(fuente, reg, io.StringIO(), 2.6,
                                           hz=20, alarma=2,
                                           imprimir=lineas.append, mapa=mapa,
                                           intervalo_mapa_s=1.0)
                    finally:
                        parar.set()
                        hilo.join(timeout=1.0)
                        fuente.cerrar()
                        reg.cerrar()
            self.assertEqual(len(mapa.congelamientos), 1, lineas)
            k = mapa.congelamientos[0]
            self.assertLess(k.x0, 0.20)                  # la última viva
            self.assertGreater(k.x0, 0.10)
            self.assertGreaterEqual(k.x1, 0.70)          # la primera al volver
            self.assertLess(k.x1, 0.80)
            # La celda x ∈ [0.415, 0.665) nunca se vio viva; las de entrada
            # y salida sí, y quedan como borde.
            self.assertEqual(mapa.estado(mapa.rejilla.indice(0.54, 1.6)),
                             "ciega")
            self.assertEqual(mapa.estado(mapa.rejilla.indice(0.30, 1.6)),
                             "borde")
            self.assertEqual(mapa.estado(mapa.rejilla.indice(0.79, 1.6)),
                             "borde")
            self.assertTrue(any("▣" in l for l in lineas), lineas)
            # Con mapa, todo en el marco del laboratorio: la alarma y la
            # línea de estado dicen la pose lab.
            self.assertTrue(any("REPITE" in l and "[lab (" in l
                                for l in lineas), lineas)
            self.assertTrue(any(" lab(" in l for l in lineas), lineas)
            self.assertTrue(any("mapa " in l and "próxima" in l
                                for l in lineas))
            self.assertTrue(any("█" in l for l in lineas))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_la_sonda_exige_el_mismo_umbral_en_el_mapa(self) -> None:
        mapa = _mapa_linea(umbral=3)
        with self.assertRaises(ValueError):
            sonda.correr_sonda(None, None, io.StringIO(), 0.1, alarma=2,
                               mapa=mapa)


# =============================================================================
# 5. SALIDAS: NADA SE PISA
# =============================================================================

class PruebaSalidasDelMapa(unittest.TestCase):

    def test_cerrar_mapa_escribe_y_no_pisa(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="mapa_salidas_"))
        try:
            mapa = _mapa_linea()
            _recorrer_con_tramo_ciego(mapa, (0.30, 0.80))
            ruta_csv, ruta_png = tmp / "x_mapa.csv", tmp / "x_mapa.png"
            with contextlib.redirect_stdout(io.StringIO()) as out:
                reg = sonda.crear_registro(tmp / "x.jsonl", [1], [1], alarma=2)
                sonda._cerrar_mapa(mapa, reg, ruta_csv, ruta_png, True)
                reg.cerrar()
            self.assertTrue(ruta_csv.exists())
            self.assertIn("CONTRASTE", out.getvalue())
            self.assertIn("SUPUESTA", out.getvalue())
            tipos = [e["tipo"] for e in eventos(tmp / "x.jsonl")]
            self.assertIn("mapa_resumen", tipos)
            resumen = [e for e in eventos(tmp / "x.jsonl")
                       if e["tipo"] == "mapa_resumen"][0]
            self.assertEqual(len(resumen["congelamientos"]), 1)
            # Otra vez a las mismas rutas: no pisa y lo dice.
            antes = ruta_csv.read_bytes()
            with contextlib.redirect_stdout(io.StringIO()) as out2:
                reg2 = sonda.crear_registro(tmp / "y.jsonl", [1], [1],
                                            alarma=2)
                sonda._cerrar_mapa(mapa, reg2, ruta_csv, ruta_png, False)
                reg2.cerrar()
            self.assertIn("no se pudo escribir el mapa", out2.getvalue())
            self.assertEqual(ruta_csv.read_bytes(), antes)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_el_png_no_pisa(self) -> None:
        try:
            import matplotlib  # noqa: F401
        except Exception:                                   # noqa: BLE001
            self.skipTest("no hay matplotlib en este Python")
        tmp = Path(tempfile.mkdtemp(prefix="mapa_png_"))
        try:
            mapa = _mapa_linea()
            _recorrer_con_tramo_ciego(mapa, (0.30, 0.80))
            ruta = tmp / "m.png"
            self.assertTrue(mapa.guardar_png(ruta))
            self.assertGreater(ruta.stat().st_size, 1000)
            antes = ruta.read_bytes()
            with self.assertRaises(FileExistsError):
                mapa.guardar_png(ruta)
            self.assertEqual(ruta.read_bytes(), antes)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_las_rutas_de_la_sonda_no_pisan_el_mapa(self) -> None:
        from datetime import datetime
        tmp = Path(tempfile.mkdtemp(prefix="mapa_rutas_"))
        try:
            ahora = datetime(2026, 9, 24, 12, 0, 0)
            a_csv, _a = sonda.rutas_salida(ahora, tmp)
            sonda.rutas_mapa(a_csv)[1].write_bytes(b"png")   # sólo el PNG
            b_csv, _b = sonda.rutas_salida(ahora, tmp)
            self.assertNotEqual(a_csv, b_csv)
            self.assertTrue(b_csv.name.endswith("_02.csv"))
            self.assertEqual(sonda.rutas_mapa(b_csv)[0].name,
                             b_csv.stem + "_mapa.csv")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_main_rechaza_una_plataforma_invalida_sin_conectar(self) -> None:
        with ConfigAislada(), contextlib.redirect_stdout(io.StringIO()) as out:
            codigo = sonda.main(["--mapeo", "--plataforma", "1", "0", "0",
                                 "1"])
        self.assertEqual(codigo, 2)
        self.assertIn("--plataforma", out.getvalue())


# =============================================================================
# 6. REVISIÓN DEL 2026-09-25: ORIGEN, ANCHO DE LA FRANJA, PEINE, VIGENCIA
# =============================================================================

def _marco_identidad() -> None:
    """Calibración de prueba: entorno = laboratorio + 1.5 m en x e y."""
    cfg.ESCALA_POSICION, cfg.ROTACION_MARCO_RAD = 1.0, 0.0
    cfg.TRASLACION_X_M = cfg.TRASLACION_Y_M = 1.5
    cfg.OFFSET_HEADING_RAD = 0.0


def _pase_perpendicular(mapa: MapaSeguimiento, x_env: float,
                        pared_y3_ciega_desde: float, marcador: int = 1,
                        t0: float = 0.0) -> float:
    """
    Un pase del peine sobre la pared y = 3, en x = `x_env` (marco del
    entorno): de d = 0.90 hasta d = 0.05 y de vuelta, en pasos de 1 cm, con
    la captura perdida a menos de `pared_y3_ciega_desde` m de la pared.
    Devuelve el reloj al terminar.
    """
    t = t0
    retenida = None
    ida = [round(0.90 - 0.01 * j, 6) for j in range(86)]
    for d in ida + ida[::-1]:
        x_lab, y_lab = env_a_lab_xy(x_env, 3.0 - d)
        t += 0.05
        if d < pared_y3_ciega_desde:
            mapa.observar(marcador, t, *retenida, repite=True)
        else:
            retenida = (x_lab, y_lab)
            mapa.observar(marcador, t, x_lab, y_lab, repite=False)
    return t


class PruebaOrigenYVigencia(unittest.TestCase):

    def test_rotulos(self) -> None:
        self.assertEqual(rotulo_origen("robotat"), "")
        self.assertEqual(rotulo_origen("simulador"),
                         "SIMULADOR — no es dato del Robotat")
        self.assertIn("SINTÉTICO", rotulo_origen("sintetico"))
        with self.assertRaises(ValueError):
            rotulo_origen("laboratorio")

    def _textos(self, fig) -> str:
        partes = [t.get_text() for t in fig.texts]
        partes += [ax.get_title() for ax in fig.axes]
        return "\n".join(partes)

    def test_la_figura_del_simulador_lleva_la_marca(self) -> None:
        try:
            import matplotlib.pyplot as plt
        except Exception:                                   # noqa: BLE001
            self.skipTest("no hay matplotlib en este Python")
        mapa = _mapa_linea()
        _recorrer_con_tramo_ciego(mapa, (0.30, 0.80))
        for origen, marca in (("simulador", "SIMULADOR — no es dato del "
                               "Robotat"),
                              ("sintetico", "SINTÉTICO — no es dato del "
                               "Robotat")):
            with self.subTest(origen=origen):
                fig = mapa.figura("sesión 2026-09-25 10:00", origen)
                texto = self._textos(fig)
                plt.close(fig)
                self.assertIn(marca, texto)                 # cruzada y título
                self.assertGreaterEqual(texto.count(marca), 2)
                self.assertIn("sesión 2026-09-25 10:00", texto)
        fig = mapa.figura("x", "robotat")
        texto = self._textos(fig)
        plt.close(fig)
        self.assertNotIn("no es dato del Robotat", texto)

    def test_el_origen_por_defecto_sale_de_la_configuracion(self) -> None:
        try:
            import matplotlib.pyplot as plt
        except Exception:                                   # noqa: BLE001
            self.skipTest("no hay matplotlib en este Python")
        mapa = _mapa_linea()
        with ConfigAislada():
            cfg.SIMULADOR_ACTIVO = True
            fig = mapa.figura()
            texto = self._textos(fig)
            plt.close(fig)
            buf = io.StringIO()
            mapa.escribir_csv(buf)
        self.assertIn("SIMULADOR — no es dato del Robotat", texto)
        import csv as _csv
        filas = list(_csv.DictReader(io.StringIO(buf.getvalue())))
        self.assertEqual({f["origen"] for f in filas}, {"simulador"})

    def test_cerrar_mapa_del_simulador_rotula_todo(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="mapa_origen_"))
        try:
            mapa = _mapa_linea()
            _recorrer_con_tramo_ciego(mapa, (0.30, 0.80))
            with contextlib.redirect_stdout(io.StringIO()) as out:
                reg = sonda.crear_registro(tmp / "x.jsonl", [1], [1], alarma=2)
                sonda._cerrar_mapa(mapa, reg, tmp / "x_mapa.csv",
                                   tmp / "x_mapa.png", True,
                                   sesion="2026-09-25 10:00",
                                   origen="simulador")
                reg.cerrar()
            texto = out.getvalue()
            self.assertIn("⚠ SIMULADOR — no es dato del Robotat", texto)
            self.assertIn("sesión 2026-09-25 10:00, vale sólo para esta "
                          "sesión", texto)
            self.assertIn("ANCHO DE LA FRANJA POR LADO", texto)
            resumen = [e for e in eventos(tmp / "x.jsonl")
                       if e["tipo"] == "mapa_resumen"][0]
            self.assertEqual(resumen["origen"], "simulador")
            self.assertEqual(resumen["sesion"], "2026-09-25 10:00")
            self.assertIn("libre", resumen["franja_arena"])
            self.assertIn("lados", resumen["franja_plataforma"])
            import csv as _csv
            with open(tmp / "x_mapa.csv", newline="", encoding="utf-8") as fh:
                self.assertEqual({f["origen"] for f in _csv.DictReader(fh)},
                                 {"simulador"})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class PruebaGeometriaDeLados(unittest.TestCase):

    def test_lado_mas_cercano(self) -> None:
        rect = (0.0, 3.0, 0.0, 3.0)
        nombres = ("x=0", "x=3", "y=0", "y=3")
        lado, d, u, largo = lado_mas_cercano(1.2, 2.8, rect, nombres)
        self.assertEqual((lado, largo), ("y=3", 3.0))
        self.assertAlmostEqual(d, 0.2)
        self.assertAlmostEqual(u, 1.2)
        lado, d, u, largo = lado_mas_cercano(0.1, 2.0, rect, nombres)
        self.assertEqual((lado, largo), ("x=0", 3.0))
        self.assertAlmostEqual(d, 0.1)
        self.assertAlmostEqual(u, 2.0)
        self.assertLess(lado_mas_cercano(3.2, 1.0, rect, nombres)[1], 0.0)

    def test_lab_y_entorno_ida_y_vuelta_con_la_calibracion_real(self) -> None:
        with ConfigAislada():
            cfg.ESCALA_POSICION = 1.0166876
            cfg.ROTACION_MARCO_RAD = 0.00847
            cfg.TRASLACION_X_M, cfg.TRASLACION_Y_M = 1.50615, 1.25634
            for x, y in ((0.0, 0.0), (1.47, -1.2), (-2.3, 1.7)):
                xe, ye = lab_a_env_xy(x, y)
                xl, yl = env_a_lab_xy(xe, ye)
                self.assertAlmostEqual(xl, x, places=12)
                self.assertAlmostEqual(yl, y, places=12)


class PruebaAnchoDeLaFranja(unittest.TestCase):

    def setUp(self) -> None:
        self._cfg = ConfigAislada()
        self._cfg.__enter__()
        _marco_identidad()

    def tearDown(self) -> None:
        self._cfg.__exit__(None, None, None)

    def _mapa(self, orden: str = "peine") -> MapaSeguimiento:
        return MapaSeguimiento(Rejilla(*plataforma_por_defecto(), celda=0.25),
                               umbral=2, orden=orden)

    def test_el_ancho_sale_donde_esta_la_franja(self) -> None:
        mapa = self._mapa()
        t = 0.0
        # Tramos 1, 2 y 3 de y = 3: lejos de las esquinas, donde un punto
        # cuenta para la pared más cercana (ver `franja_por_lado`).
        for x_env in (0.75, 1.25, 1.75):
            t = _pase_perpendicular(mapa, x_env, 0.30, t0=t)
        r = mapa.franja_por_lado("arena")
        (y3,) = [l for l in r["lados"] if l["lado"] == "y=3"]
        self.assertEqual(y3["transiciones"], 6)   # entrada y salida por pase
        self.assertAlmostEqual(y3["ancho_max_m"], 0.30, places=6)
        self.assertAlmostEqual(y3["ancho_mediano_m"], 0.30, places=6)
        self.assertEqual(y3["tramos_con_franja"], 3)
        self.assertEqual([tr["k"] for tr in y3["tramos"]
                          if tr["franja_m"] is not None], [1, 2, 3])
        # Los otros lados no tienen datos: la arena libre queda incompleta.
        lib = r["libre"]
        self.assertAlmostEqual(lib["ancho_y_m"], 3.0 - 0.30, places=6)
        self.assertAlmostEqual(lib["ancho_x_m"], 3.0, places=6)
        self.assertIn("y=0", lib["lados_sin_datos"])
        self.assertAlmostEqual(lib["exp_n_area_m2"], 7.29)
        texto = "\n".join(mapa.lineas_franja())
        self.assertIn("INCOMPLETO", texto)
        self.assertIn("Exp N rechazó 2.7 × 2.7", texto)

    def test_franja_en_los_cuatro_lados_da_la_arena_libre(self) -> None:
        """Una franja de 0.35 m en todo el perímetro: 2.30 × 2.30 m."""
        mapa = self._mapa("anillos")
        wx = wy = 3.0

        def puntos(lado: str, u: float, d: float) -> Tuple[float, float]:
            return {"y=0": (u, d), "y=3": (u, wy - d),
                    "x=0": (d, u), "x=3": (wx - d, u)}[lado]

        t = 0.0
        for lado in ("y=0", "y=3", "x=0", "x=3"):
            for k in range(6):
                u = (k + 0.5) * SEGMENTO_LADO_M
                retenida = None
                ida = [round(0.9 - 0.01 * j, 6) for j in range(86)]
                for d in ida + ida[::-1]:
                    x_lab, y_lab = env_a_lab_xy(*puntos(lado, u, d))
                    t += 0.05
                    if d < 0.35:
                        mapa.observar(1, t, *retenida, repite=True)
                    else:
                        retenida = (x_lab, y_lab)
                        mapa.observar(1, t, x_lab, y_lab, repite=False)
        r = mapa.franja_por_lado("arena")
        for l in r["lados"]:
            with self.subTest(lado=l["lado"]):
                self.assertAlmostEqual(l["ancho_max_m"], 0.35, places=6)
                self.assertEqual(l["tramos_con_franja"], 6)
                self.assertEqual(l["tramos_con_datos"], 6)
        lib = r["libre"]
        self.assertAlmostEqual(lib["ancho_x_m"], 2.30, places=6)
        self.assertAlmostEqual(lib["ancho_y_m"], 2.30, places=6)
        self.assertAlmostEqual(lib["area_m2"], 5.29, places=6)
        self.assertEqual(lib["lados_sin_datos"], [])
        self.assertNotIn("INCOMPLETO", "\n".join(mapa.lineas_franja()))
        self.assertLess(lib["area_m2"], lib["exp_n_area_m2"])
        # Convención del Exp N: 3 − 2·(0.35 + 0.05 − 0.18) = 2.56 m.
        self.assertAlmostEqual(lib["equivalente_exp_n_x_m"], 2.56, places=6)
        self.assertAlmostEqual(lib["equivalente_exp_n_y_m"], 2.56, places=6)

    def test_visto_vivo_junto_a_la_pared_es_franja_cero(self) -> None:
        mapa = self._mapa()
        _pase_perpendicular(mapa, 1.25, -1.0)      # nunca se pierde
        r = mapa.franja_por_lado("arena")
        (y3,) = [l for l in r["lados"] if l["lado"] == "y=3"]
        self.assertEqual(y3["transiciones"], 0)
        self.assertEqual(y3["ancho_m"], 0.0)
        (tr,) = [tr for tr in y3["tramos"] if tr["k"] == 2]
        self.assertAlmostEqual(tr["vivo_min_m"], 0.05, places=6)
        self.assertIn("vivo a 0.05", "\n".join(mapa.lineas_franja()))


class PruebaPeine(unittest.TestCase):

    def setUp(self) -> None:
        self._cfg = ConfigAislada()
        self._cfg.__enter__()
        _marco_identidad()

    def tearDown(self) -> None:
        self._cfg.__exit__(None, None, None)

    def test_un_pase_por_tramo_y_perpendicular_a_su_pared(self) -> None:
        pases = pases_peine(plataforma_por_defecto())
        self.assertEqual(len(pases), 24)
        self.assertEqual([p.lado for p in pases[::6]],
                         ["y=0", "x=3", "y=3", "x=0"])
        for p in pases:
            with self.subTest(lado=p.lado, k=p.k):
                xe0, ye0 = lab_a_env_xy(*p.desde_lab)
                xe1, ye1 = lab_a_env_xy(*p.hasta_lab)
                # arranca a 0.90 m de SU pared, en el centro de su tramo
                d, u = {"y=0": (ye0, xe0), "y=3": (3 - ye0, xe0),
                        "x=0": (xe0, ye0), "x=3": (3 - xe0, ye0)}[p.lado]
                self.assertAlmostEqual(d, PEINE_DESDE_M, places=9)
                self.assertAlmostEqual(u, (p.k + 0.5) * SEGMENTO_LADO_M,
                                       places=9)
                # y va derecho hacia ella: se mueve sólo en la normal
                if p.lado in ("y=0", "y=3"):
                    self.assertAlmostEqual(xe1, xe0, places=9)
                else:
                    self.assertAlmostEqual(ye1, ye0, places=9)

    def test_el_pase_no_sale_de_la_plataforma(self) -> None:
        # Con entorno = lab + 1.5, la pared y = 3 está en y lab = 1.5; una
        # plataforma que termina en y = 1.52 obliga a recortar el pase.
        plataforma = (-2.335, 2.335, -1.725, 1.52)
        for p in pases_peine(plataforma):
            if p.lado == "y=3":
                self.assertTrue(p.recortado)
                self.assertLessEqual(p.hasta_lab[1], 1.52 - 0.05 + 1e-9)
            else:
                self.assertFalse(p.recortado, p)

    def test_la_guia_avanza_y_un_pase_se_cumple_con_una_transicion(self) -> None:
        mapa = MapaSeguimiento(Rejilla(*plataforma_por_defecto(), celda=0.25),
                               umbral=2, orden="peine")
        primero = mapa.proximo_pase()
        self.assertEqual((primero.lado, primero.k), ("y=0", 0))
        self.assertIn("0/24 pases", mapa.destino())
        self.assertEqual(mapa.celda_destino(),
                         mapa.rejilla.indice(*primero.desde_lab))
        # Visto vivo a ≤ 2 cm de la pared y = 0 en su primer tramo: hecho.
        x_lab, y_lab = env_a_lab_xy(0.25, LLEGO_A_LA_PARED_M / 2)
        mapa.observar(1, 0.0, x_lab, y_lab, repite=False)
        self.assertEqual((mapa.proximo_pase().lado, mapa.proximo_pase().k),
                         ("y=0", 1))
        # Una transición en el tramo 1 de y = 0: hecho también. (A 0.60 m de
        # la pared: más cerca de la esquina, el punto caería también sobre el
        # pase de esquina de x = 0 —los pases se cruzan ahí— y contaría para
        # los dos, que es lo geométricamente correcto.)
        xa, ya = env_a_lab_xy(0.75, 0.60)
        mapa.observar(1, 1.0, xa, ya, repite=False)
        mapa.observar(1, 1.05, xa, ya, repite=True)
        mapa.observar(1, 1.10, xa, ya, repite=True)
        self.assertEqual((mapa.proximo_pase().lado, mapa.proximo_pase().k),
                         ("y=0", 2))
        self.assertIn("2/24 pases", mapa.destino())

    def test_el_pase_de_esquina_se_cumple_con_su_transicion(self) -> None:
        """
        Pase y=0 tramo 0 (x del entorno 0.25) con una franja de 0.35 m: el
        borde interior está más cerca de la pared x=0 (0.25) que de la y=0
        (0.35). Contra la pared más cercana, la guía quedaba trabada ahí.
        """
        mapa = MapaSeguimiento(Rejilla(*plataforma_por_defecto(), celda=0.25),
                               umbral=2, orden="peine")
        xa, ya = env_a_lab_xy(0.25, 0.35)
        mapa.observar(1, 0.0, xa, ya, repite=False)
        mapa.observar(1, 0.05, xa, ya, repite=True)
        mapa.observar(1, 0.10, xa, ya, repite=True)
        self.assertTrue(mapa.pase_hecho(mapa.pases[0]))
        self.assertEqual((mapa.proximo_pase().lado, mapa.proximo_pase().k),
                         ("y=0", 1))

    def test_orden_desconocido(self) -> None:
        with self.assertRaises(ValueError):
            MapaSeguimiento(Rejilla(0, 1, 0, 1, 0.25), umbral=2,
                            orden="espiral")


class PruebaSondaMideElAncho(unittest.TestCase):
    """
    La sonda de verdad contra el simulador, con una FRANJA inyectada de
    0.30 m junto a la pared y = 3 de la arena: un robot "empujado" en
    perpendicular hacia la pared y de vuelta, como pide el peine. El ancho
    medido tiene que ser 0.30 m, dentro del paso de consulta.
    """

    def test_el_ancho_medido_es_el_de_la_franja(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="sonda_franja_"))
        try:
            with ConfigAislada():
                pp, pb = puerto_libre(), puerto_libre()
                cfg.activar_simulador_local(puerto_poses=pp, puerto_base=pb)
                cfg.MAPEO_AGENTES = {0: cfg.AsignacionAgente(id_marcador=1,
                                                             id_robot=1)}
                _marco_identidad()
                # Pared y = 3 del entorno = y 1.5 del laboratorio: franja
                # ciega en y lab ≥ 1.2.
                fallas = FallasSimulador(
                    modo_marcador_perdido="congelado", ruido_pos_m=0.0005,
                    semilla=6, zona_sin_captura=(-5.0, 5.0, 1.2, 5.0))
                sim = SimuladorRobotat({1: 1}, {1: (-0.25, 0.6, 1.5708)},
                                       fallas, puerto_poses=pp,
                                       puerto_base=pb)
                parar = threading.Event()

                def empujar() -> None:
                    # 0.6 → 1.45 a 0.4 m/s y de vuelta: un pase del peine.
                    t0 = time.perf_counter()
                    while not parar.is_set():
                        s = 0.4 * (time.perf_counter() - t0)
                        y = 0.6 + (s if s <= 0.85 else max(0.0, 1.7 - s))
                        with sim._lock:
                            sim.robots[1].y = y
                        time.sleep(0.005)

                with sim, contextlib.redirect_stdout(io.StringIO()):
                    fuente = sonda.FuenteSonda(1)
                    reg = sonda.crear_registro(tmp / "f.jsonl", [1], [1],
                                               alarma=2)
                    fuente.activar_diagnostico(reg)
                    fuente.conectar()
                    mapa = MapaSeguimiento(
                        Rejilla(*plataforma_por_defecto(), celda=0.25),
                        umbral=2, orden="peine")
                    hilo = threading.Thread(target=empujar, daemon=True)
                    hilo.start()
                    lineas: List[str] = []
                    try:
                        sonda.correr_sonda(fuente, reg, io.StringIO(), 4.8,
                                           hz=20, alarma=2,
                                           imprimir=lineas.append, mapa=mapa,
                                           intervalo_mapa_s=100.0)
                    finally:
                        parar.set()
                        hilo.join(timeout=1.0)
                        fuente.cerrar()
                        reg.cerrar()
            r = mapa.franja_por_lado("arena")
            (y3,) = [l for l in r["lados"] if l["lado"] == "y=3"]
            self.assertEqual(y3["transiciones"], 2, lineas)
            # A 0.4 m/s y 20 Hz, 2 cm por consulta: la última viva antes de
            # entrar y la primera al salir quedan a ≤ 2 cm del borde.
            # (0.5 mm de ruido de captura en la pose publicada)
            self.assertGreater(y3["ancho_max_m"], 0.295, lineas)
            self.assertLess(y3["ancho_max_m"], 0.33, lineas)
            # x lab −0.25 → x del entorno 1.25: tramo 2 de y = 3.
            self.assertEqual([tr["k"] for tr in y3["tramos"]
                              if tr["transiciones"]], [2])
            self.assertTrue(any("pases" in l for l in lineas), lineas)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)



class PruebaDireccionYCota(unittest.TestCase):
    """
    Revisión del 2026-09-25: sólo una transición PERPENDICULAR a la pared
    mide el ancho; una paralela mide el carril por donde iba el robot y da
    sólo una cota inferior (la auditoría: 6 de 10 inicios del 24-09 entraron
    paralelos a la pared).
    """

    def setUp(self) -> None:
        self._cfg = ConfigAislada()
        self._cfg.__enter__()
        _marco_identidad()

    def tearDown(self) -> None:
        self._cfg.__exit__(None, None, None)

    def test_clase_de_transicion(self) -> None:
        afuera = (0.0, 1.0)                              # normal de y = 3
        self.assertEqual(clase_de_transicion("entrada", (0.0, 1.0), afuera)[0],
                         "perpendicular")                # hacia la pared
        self.assertEqual(clase_de_transicion("salida", (0.0, -1.0), afuera)[0],
                         "perpendicular")                # alejándose
        clase, ang = clase_de_transicion("entrada", (1.0, 0.0), afuera)
        self.assertEqual(clase, "oblicua")
        self.assertAlmostEqual(ang, 90.0)
        s = math.sin(math.radians(25.0))
        c = math.cos(math.radians(25.0))
        self.assertEqual(clase_de_transicion("entrada", (s, c), afuera)[0],
                         "perpendicular")                # 25° ≤ 30°
        self.assertEqual(clase_de_transicion("entrada", None, afuera)[0],
                         "sin_direccion")

    def test_la_direccion_se_rota_al_entorno(self) -> None:
        cfg.ROTACION_MARCO_RAD = math.pi / 2
        vx, vy = direccion_en_entorno((1.0, 0.0))
        self.assertAlmostEqual(vx, 0.0)
        self.assertAlmostEqual(vy, 1.0)

    def test_una_entrada_paralela_da_cota_y_no_ancho(self) -> None:
        mapa = MapaSeguimiento(Rejilla(*plataforma_por_defecto(), celda=0.25),
                               umbral=2, orden="peine")
        retenida = None
        for j in range(200):                    # a lo largo de y = 3, d = 0.22
            x_env = round(0.9 + 0.01 * j, 6)
            x_lab, y_lab = env_a_lab_xy(x_env, 3.0 - 0.22)
            if 1.40 <= x_env < 1.80:
                mapa.observar(1, 0.05 * j, *retenida, repite=True)
            else:
                retenida = (x_lab, y_lab)
                mapa.observar(1, 0.05 * j, x_lab, y_lab, repite=False)
        r = mapa.franja_por_lado("arena")
        (y3,) = [l for l in r["lados"] if l["lado"] == "y=3"]
        self.assertEqual((y3["transiciones"], y3["perpendiculares"]), (2, 0))
        self.assertIsNone(y3["ancho_max_m"])
        self.assertAlmostEqual(y3["cota_inferior_m"], 0.22, places=6)
        self.assertTrue(y3["ancho_es_cota"])
        self.assertEqual({d["clase"] for d in y3["detalle"]}, {"oblicua"})
        texto = "\n".join(mapa.lineas_franja())
        self.assertIn("≥0.22", texto)
        self.assertIn("COTA inferior", texto)
        (fila,) = resumen_congelamientos(mapa)
        self.assertEqual(fila["clase_entrada"], "oblicua")
        self.assertAlmostEqual(fila["angulo_entrada_deg"], 90.0, places=3)

    def test_esquinas_contra_tramo_medio_y_marcadores(self) -> None:
        mapa = MapaSeguimiento(Rejilla(*plataforma_por_defecto(), celda=0.25),
                               umbral=2, orden="peine")
        t = 0.0
        # Marcador 1: pases perpendiculares a y = 0 en los tramos de los
        # extremos (x 0.25 y 2.75), con franja de 0.30 m; en el medio (x
        # 1.25 y 1.75) llega vivo a la pared.
        for marcador, x_env, ciega in ((1, 0.25, 0.30), (1, 2.75, 0.30),
                                       (1, 1.25, -1.0), (1, 1.75, -1.0),
                                       (6, 0.25, -1.0)):
            retenida = None
            ida = [round(0.9 - 0.01 * j, 6) for j in range(86)]
            for d in ida + ida[::-1]:
                x_lab, y_lab = env_a_lab_xy(x_env, d)
                t += 0.05
                if d < ciega:
                    mapa.observar(marcador, t, *retenida, repite=True)
                else:
                    retenida = (x_lab, y_lab)
                    mapa.observar(marcador, t, x_lab, y_lab, repite=False)
        r = mapa.franja_por_lado("arena")
        em = r["esquinas_vs_medio"]
        self.assertGreater(em["esquinas"]["inicios"], 0)
        self.assertEqual(em["medio"]["inicios"], 0)
        self.assertGreater(em["medio"]["vivas_cerca"], 0)
        # El marcador 6 pasó por la esquina (x 0.25) vivo hasta la pared.
        todos = {}
        for l in r["lados"]:
            for m, n in l["inicios_por_marcador"].items():
                todos[m] = todos.get(m, 0) + n
        self.assertEqual(set(todos), {"1"})
        self.assertIn("esquinas vs tramo medio", "\n".join(mapa.lineas_franja()))

    def test_una_entrada_de_esquina_cuenta_para_la_pared_hacia_la_que_iba(
            self) -> None:
        """
        El caso de la auditoría: a 0.22 m de y = 3 (la más cercana) pero
        avanzando de frente hacia x = 0, a 0.55 m. Es una entrada por la
        esquina: mide 0.55 m de franja en x = 0, no una cota de y = 3.
        """
        mapa = MapaSeguimiento(Rejilla(*plataforma_por_defecto(), celda=0.25),
                               umbral=2, orden="peine")
        retenida = None
        for j in range(60):
            x_env = round(1.10 - 0.01 * j, 6)      # hacia −x, a y = 2.78
            x_lab, y_lab = env_a_lab_xy(x_env, 2.78)
            if x_env < 0.55:
                mapa.observar(9, 0.05 * j, *retenida, repite=True)
            else:
                retenida = (x_lab, y_lab)
                mapa.observar(9, 0.05 * j, x_lab, y_lab, repite=False)
        r = mapa.franja_por_lado("arena")
        (x0,) = [l for l in r["lados"] if l["lado"] == "x=0"]
        (y3,) = [l for l in r["lados"] if l["lado"] == "y=3"]
        self.assertEqual((x0["transiciones"], x0["perpendiculares"]), (1, 1))
        self.assertAlmostEqual(x0["ancho_max_m"], 0.55, places=6)
        self.assertEqual(x0["inicios_por_marcador"], {"9": 1})
        self.assertEqual(y3["transiciones"], 0)
        # u = y = 2.78: el último tramo de x = 0
        (tr,) = [tr for tr in x0["tramos"] if tr["transiciones"]]
        self.assertEqual(tr["k"], 5)

    def test_arena_equivalente_en_la_convencion_del_exp_n(self) -> None:
        self.assertAlmostEqual(reduccion_exp_n(0.35), 0.22)
        self.assertAlmostEqual(reduccion_exp_n(0.229), 0.099)
        self.assertEqual(reduccion_exp_n(0.10), 0.0)
        self.assertEqual(reduccion_exp_n(None), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
