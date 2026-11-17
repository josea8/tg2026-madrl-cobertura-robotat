"""
test_experimento_R.py
=====================
Pruebas del Exp R que no necesitan corridas largas (§4 y §5 del prerregistro).
Ninguna escribe en `resultados/` ni en la carpeta del Exp Q: todo lo que
escriben va a directorios temporales del sistema. Las que corren un episodio
real sólo AFIRMAN INVARIANTES (columnas iguales a Q, autochequeos, tamaño de
la traza): no imprimen valores de la Parte B.

    python -B -m unittest test_experimento_R -v

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import hashlib
import os
import platform
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

if not sys.flags.dont_write_bytecode:
    raise SystemExit("PARAR: correr con python -B (si no, se escribe __pycache__ en el Exp Q).")

_CARPETA = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import analizar_experimento_R as A
import comparar_ast_R as C
import correr_experimento_R as R

INF = float("inf")


def _texto(ruta: Path) -> str:
    return ruta.read_bytes().decode("utf-8")


class PruebaSemillas(unittest.TestCase):

    def test_bloque_nuevo(self) -> None:
        s = R.semillas_R()
        self.assertEqual((len(s), s[0], s[-1], len(set(s))), (400, 420110, 420509, 400))
        usadas = set(range(420000, 420110)) | set(range(421000, 423000))
        self.assertFalse(set(s) & usadas)
        self.assertFalse(set(s) & set(R.Q.semillas_protocolo()))

    def test_firma_de_semillas(self) -> None:
        self.assertTrue(R.linea_semillas_R(R.semillas_R()).endswith("420110-420509 n 400"))
        self.assertNotEqual(R.linea_semillas_R([1, 2]), R.linea_semillas_R([2, 1]))


class PruebaColumnasDerivadas(unittest.TestCase):
    """Episodios inventados: T pasos, 2 agentes."""

    def _base(self, T: int = 8):
        fb = [[0, 0] for _ in range(T)]
        do = [[0.5, 0.5] for _ in range(T)]
        return fb, do

    def test_orden_de_las_columnas(self) -> None:
        fb, do = self._base()
        self.assertEqual(tuple(R.columnas_derivadas(fb, do)), R.DERIVADAS_R)

    def test_minimo_en_un_fallback(self) -> None:
        fb, do = self._base()
        fb[2][0] = fb[3][0] = 1
        do[3][0], do[6][1] = 0.08, 0.30
        c = R.columnas_derivadas(fb, do)
        self.assertEqual((c["paso_d_min"], c["agente_d_min"]), (3, 0))
        self.assertEqual((c["fallback_en_d_min"], c["racha_fallback_d_min"],
                          c["fallback_ventana_d_min_5"]), (1, 2, 1))
        self.assertEqual((c["d_min_en_fallback"], c["d_min_sin_fallback"]), (0.08, 0.30))
        self.assertEqual(c["pasos_agente_fallback"], 2)
        self.assertEqual((c["pasos_bajo_010"], c["pasos_bajo_010_fuera_ventana_5"]), (1, 0))
        # Fuera de la ventana de 5 del agente 0 (t ≥ 8) no hay nada: el mínimo
        # fuera de la ventana es el del agente 1.
        self.assertEqual(c["d_min_fuera_ventana_5"], 0.30)

    def test_minimo_justo_despues_del_fallback(self) -> None:
        fb, do = self._base()
        fb[2][0] = fb[3][0] = 1
        do[5][0] = 0.09                       # dos decisiones después del último fallback
        c = R.columnas_derivadas(fb, do)
        self.assertEqual((c["paso_d_min"], c["fallback_en_d_min"], c["racha_fallback_d_min"],
                          c["fallback_ventana_d_min_5"]), (5, 0, 0, 1))
        self.assertEqual(c["d_min_sin_fallback"], 0.09)         # W = 1 no lo cubre
        self.assertEqual(c["d_min_fuera_ventana_3"], 0.5)       # 3…5 incluye la 3
        self.assertEqual(c["d_min_fuera_ventana_5"], 0.5)
        self.assertEqual(c["pasos_bajo_010_fuera_ventana_5"], 0)
        do[7][0] = 0.07                       # t = 7: la ventana 3…7 incluye la 3
        self.assertEqual(R.columnas_derivadas(fb, do)["d_min_fuera_ventana_5"], 0.5)
        fb2 = [list(f) for f in fb]
        fb2[3][0] = 0                         # último fallback en t = 2: 3…7 ya no lo ve
        c2 = R.columnas_derivadas(fb2, do)
        self.assertEqual(c2["d_min_fuera_ventana_5"], 0.07)
        self.assertEqual(c2["d_min_fuera_ventana_10"], 0.5)

    def test_sin_obstaculos(self) -> None:
        fb = [[0, 0] for _ in range(4)]
        do = [[INF, INF] for _ in range(4)]
        c = R.columnas_derivadas(fb, do)
        self.assertEqual((c["d_min_sin_fallback"], c["d_min_en_fallback"],
                          c["d_min_fuera_ventana_5"]), (INF, INF, INF))
        self.assertEqual((c["paso_d_min"], c["agente_d_min"], c["fallback_en_d_min"],
                          c["racha_fallback_d_min"], c["fallback_ventana_d_min_5"]),
                         (-1, -1, 0, 0, 0))

    def test_sin_fallbacks(self) -> None:
        fb, do = self._base()
        do[4][1] = 0.2
        c = R.columnas_derivadas(fb, do)
        self.assertEqual((c["d_min_sin_fallback"], c["d_min_fuera_ventana_5"],
                          c["d_min_en_fallback"]), (0.2, 0.2, INF))

    def test_empate_de_contacto(self) -> None:
        """El paso del mínimo es el primero a menos de 1e-9: el primer contacto."""
        fb, do = self._base()
        do[1][0] = 0.07500000100000004
        do[4][1] = 0.07500000099999987        # el mínimo exacto, más tarde
        c = R.columnas_derivadas(fb, do)
        self.assertEqual((c["paso_d_min"], c["agente_d_min"]), (1, 0))


class PruebaAutochequeos(unittest.TestCase):

    def _hist(self):
        import numpy as np
        h = []
        cto = [0, 0]
        for t in range(4):
            xy_a = np.array([[1.0, 1.0], [2.0, 2.0 + 0.01 * t]])
            xy_d = np.array([[1.0, 1.0], [2.0, 2.0 + 0.01 * (t + 1)]])
            fb = [1 if t in (1, 2) else 0, 0]
            if t == 3:
                xy_d[0] = [1.05, 1.0]           # termina el fallback: se mueve
            h.append((fb, [0, 1], [1, int(t % 2)], [0.3, 0.4], xy_a, xy_d, list(cto)))
        return h

    def test_quieto_en_fallback(self) -> None:
        c = R.autochequeos_R(self._hist())
        self.assertEqual(c["fb_desplazado"], 0)
        self.assertEqual(c["fb_desplazado_corrido"], 1)   # la bandera de t = 2 en t = 3
        self.assertEqual(c["pasos_agente_intervino"], 4 + 2)
        self.assertEqual(c["pasos_agente_escape_intervino"], 2)
        self.assertEqual(c["contactos_registrados"], 0)

    def test_continuidad(self) -> None:
        import numpy as np
        h = self._hist()
        self.assertEqual(R.autochequeos_R(h)["xy_discontinuo"], 0)
        fb, esc, it, do, xy_a, xy_d, cto = h[2]
        xy_a = np.array(xy_a)
        xy_a[1] = [9.0, 9.0]                  # la posición "antes" no es la del paso anterior
        h[2] = (fb, esc, it, do, xy_a, xy_d, cto)
        self.assertEqual(R.autochequeos_R(h)["xy_discontinuo"], 1)

    def test_movido_sin_contacto_y_contacto(self) -> None:
        import numpy as np
        h = self._hist()
        fb, esc, it, do, xy_a, xy_d, cto = h[1]
        xy_d = np.array(xy_d)
        xy_d[0] = [1.0, 1.2]                  # en fallback y se mueve: el pareo falla
        h[1] = (fb, esc, it, do, xy_a, xy_d, cto)
        self.assertEqual(R.autochequeos_R(h)["fb_desplazado"], 1)
        h[1] = (fb, esc, it, do, xy_a, xy_d, [1, 0])     # …pero con un contacto nuevo
        h[2] = h[2][:6] + ([1, 0],)
        h[3] = h[3][:6] + ([1, 0],)
        c = R.autochequeos_R(h)
        self.assertEqual((c["fb_desplazado"], c["contactos_registrados"]), (0, 1))


class PruebaTrazas(unittest.TestCase):

    def test_criterio(self) -> None:
        base = {"tipo": "din", "qp_fallbacks": 0, "contactos_obst_eventos": 0,
                "d_min_obst_superficie": 0.2}
        self.assertFalse(R.requiere_traza_R(base))
        self.assertTrue(R.requiere_traza_R({**base, "qp_fallbacks": 3}))
        self.assertTrue(R.requiere_traza_R({**base, "tipo": "quieto",
                                            "d_min_obst_superficie": "0.09"}))
        self.assertTrue(R.requiere_traza_R({**base, "tipo": "sinvel",
                                            "contactos_obst_eventos": "2"}))
        self.assertFalse(R.requiere_traza_R({**base, "tipo": "ctrl", "qp_fallbacks": 3,
                                             "d_min_obst_superficie": -0.2}))

    def test_escritura(self) -> None:
        import numpy as np
        hist = [([0, 1], [0, 0], [1, 1], [0.5, INF], np.zeros((2, 2)), np.ones((2, 2)),
                 [0, t]) for t in range(3)]
        filas = R.filas_traza_R(hist)
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "R_S1_din_1.csv"
            R.escribir_traza_R(filas, ruta)
            with open(ruta, encoding="utf-8") as f:
                lineas = list(csv.reader(f))
            self.assertEqual(tuple(lineas[0]), R.COLUMNAS_TRAZA_R)
            self.assertEqual(len(lineas) - 1, 3 * 2)
            self.assertEqual(lineas[2][3], "inf")
            self.assertFalse((Path(d) / "R_S1_din_1.tmp").exists())
            self.assertNotIn(b"\r", ruta.read_bytes())
        self.assertEqual([f["contacto_nuevo"] for f in filas], [0, 0, 0, 1, 0, 1])


class PruebaEpisodioReal(unittest.TestCase):
    """S3_din 420057 (fallback y acercamiento en el exploratorio), por el pool."""

    @classmethod
    def setUpClass(cls) -> None:
        cond = R.CondicionQ("S3_din", "S3", "din")
        with ProcessPoolExecutor(max_workers=1, initializer=R._inicializar_trabajador) as ex:
            cls.fila = ex.submit(R._tarea_R, (cond, 420057)).result()
        cls.ref = next(r for r in R._leer_csv(R.RUTA_CSV_EXPL_Q)
                       if r["condicion"] == "S3_din" and r["seed_ep"] == "420057")

    def test_columnas_de_Q_identicas(self) -> None:
        cols = [c for c in self.ref if c not in ("t_episodio_s", "exploratorio")]
        self.assertEqual(len(cols), 66)
        self.assertEqual([c for c in cols if R._serial(self.fila[c]) != self.ref[c]], [])
        self.assertEqual(list(self.fila)[:67], R.claves_retorno_Q())

    def test_autochequeos(self) -> None:
        f = self.fila
        self.assertEqual(f["pasos_agente_fallback"], f["qp_fallbacks"])
        self.assertEqual(min(f["d_min_sin_fallback"], f["d_min_en_fallback"]),
                         f["d_min_obst_superficie"])
        self.assertEqual(f["fb_desplazado"], 0)
        self.assertGreater(f["fb_desplazado_corrido"], 0)
        self.assertEqual(f["contactos_registrados"], f["contactos_obst_eventos"])
        self.assertEqual(repr(f["pasos_agente_intervino"] / 2500), repr(f["cbf_frac_interv"]))
        self.assertEqual(f["pasos_agente_escape_intervino"], f["escape_filtro_modifico"])

    def test_traza(self) -> None:
        tr = self.fila["_traza_R"]
        self.assertIsNotNone(tr)
        self.assertEqual(len(tr), 500 * 5)
        self.assertEqual(tuple(tr[0]), R.COLUMNAS_TRAZA_R)
        self.assertEqual([(r["paso"], r["agente"]) for r in tr[:6]],
                         [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (1, 0)])
        self.assertEqual(sum(r["fallback"] for r in tr), self.fila["qp_fallbacks"])


class PruebaComparador(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.r = _texto(C.RUTA_R)
        cls.q = _texto(C.RUTA_Q)
        cls.esp = C.espacios_originales()

    def _veredicto(self, texto: str):
        return {k: not v[0] for k, v in C.comprobar(texto, self.q, self.esp).items()}

    def _mutar(self, viejo: str, nuevo: str) -> str:
        self.assertEqual(self.r.count(viejo), 1, viejo)
        return self.r.replace(viejo, nuevo)

    def test_archivo_real(self) -> None:
        self.assertEqual(self._veredicto(self.r), {"1": True, "2": True, "3": True, "4": True})
        self.assertEqual(C.identidad_en_ejecucion(C.nombres_libres_Q(self.q) - {"_MODELO"}), [])

    def test_cambio_sin_marca(self) -> None:
        t = self._mutar("    suma_mag = 0.0\n", "    suma_mag = 0.5\n")
        self.assertFalse(self._veredicto(t)["1"])

    def test_docstring(self) -> None:
        t = self._mutar("Un episodio determinista, por el camino nuevo.",
                        "Un episodio determinista, por el camino de R.")
        self.assertFalse(self._veredicto(t)["1"])

    def test_linea_R_que_modifica_Q(self) -> None:
        t = self._mutar("            int_t[i] = int(res.intervino)  # [R]\n",
                        "            int_t[i] = int(res.intervino)  # [R]\n"
                        "            acciones[i] = 0  # [R]\n")
        v = self._veredicto(t)
        self.assertTrue(v["1"])          # la comprobación 1 no la ve…
        self.assertFalse(v["3"])         # …la 3 sí

    def test_linea_R_que_llama_al_entorno(self) -> None:
        t = self._mutar("        do_t = [float(\"inf\")] * n_a  # [R]\n",
                        "        do_t = [float(\"inf\")] * n_a  # [R]\n"
                        "        fantasma_t = env.step({})  # [R]\n")
        self.assertFalse(self._veredicto(t)["3"])

    def test_marca_parcial(self) -> None:
        t = self._mutar("        hist_R.append((fb_t, esc_t, int_t, do_t, xy_antes_t, pos.copy(), cto_t))  # [R]\n",
                        "        hist_R.append((fb_t, esc_t, int_t, do_t, xy_antes_t,\n"
                        "                       pos.copy(), cto_t))  # [R]\n")
        v = self._veredicto(t)
        self.assertFalse(v["1"] and v["3"])

    def test_clave_R_repetida(self) -> None:
        t = self._mutar("        \"_hist_R\": hist_R,  # [R]\n",
                        "        \"_hist_R\": hist_R,  # [R]\n        \"pasos\": hist_R,  # [R]\n")
        self.assertFalse(self._veredicto(t)["3"])

    def test_marca_fuera_de_la_funcion(self) -> None:
        t = self._mutar("REINTENTOS_ESCRITURA_R: int = 60\n",
                        "REINTENTOS_ESCRITURA_R: int = 60  # [R]\n")
        self.assertFalse(self._veredicto(t)["1"])

    def test_sombra_por_asignacion(self) -> None:
        t = self._mutar("REINTENTOS_ESCRITURA_R: int = 60\n",
                        "REINTENTOS_ESCRITURA_R: int = 60\nARENA = 3.1\n")
        self.assertFalse(self._veredicto(t)["2"])

    def test_redefinicion(self) -> None:
        t = self._mutar("def semillas_R() -> List[int]:", "def huella_codigo() -> str:\n"
                        "    return ''\n\n\ndef semillas_R() -> List[int]:")
        self.assertFalse(self._veredicto(t)["2"])

    def test_parche(self) -> None:
        for linea in ("    Q.ARENA = 1.0\n", "    setattr(Q, 'ARENA', 1.0)\n",
                      "    ESCENARIOS = Q.ESCENARIOS_Q\n    ESCENARIOS.update({})\n",
                      "    Q.ESCENARIOS_Q.update({})\n"):
            t = self._mutar("    \"\"\"420110–420509.\"\"\"\n",
                            "    \"\"\"420110–420509.\"\"\"\n" + linea)
            self.assertFalse(self._veredicto(t)["2"], linea)

    def test_falta_un_nombre_libre(self) -> None:
        t = self._mutar("mascara_ocupada, mascara_permanente, np,",
                        "mascara_permanente, np,")
        self.assertFalse(self._veredicto(t)["4"])

    def test_def_duplicado_y_decorador(self) -> None:
        fin = 'if __name__ == "__main__":\n    main()\n'
        t = self._mutar(fin, "_copia_R = correr_episodio_R\n\n\ndef correr_episodio_R(cond, "
                        "seed_ep):\n    return _copia_R(cond, seed_ep)\n\n\n" + fin)
        self.assertFalse(self._veredicto(t)["1"])
        d = "def correr_episodio_R(cond: CondicionQ, seed_ep: int) -> Dict[str, object]:\n"
        t = self._mutar(d, "@staticmethod\n" + d)
        self.assertFalse(self._veredicto(t)["1"])

    def test_builtins_sombreados(self) -> None:
        ancla = "REINTENTOS_ESCRITURA_R: int = 60\n"
        for extra in ("min = max\n", "def abs(x):\n    return x\n",
                      "from numpy import sum\n"):
            t = self._mutar(ancla, ancla + extra)
            self.assertFalse(self._veredicto(t)["2"], extra)

    def test_alias_y_keywords_en_R(self) -> None:
        ancla = "        do_t = [float(\"inf\")] * n_a  # [R]\n"
        for extra in ("        al_t = acciones  # [R]\n        al_t[0] = 0  # [R]\n",
                      "        vm_t = violo_margen  # [R]\n        vm_t.append(True)  # [R]\n",
                      "        z_t = max([0], key=env.reset)  # [R]\n",
                      "        z_t = fb_t  # [R]\n        z_t[0][0] = 1  # [R]\n"):
            t = self._mutar(ancla, ancla + extra)
            self.assertFalse(self._veredicto(t)["3"], extra)

    def test_else_y_desempaque_en_R(self) -> None:
        t = self._mutar("        \"_hist_R\": hist_R,  # [R]\n",
                        "        \"_hist_R\": hist_R,  # [R]\n        **{},  # [R]\n")
        self.assertFalse(self._veredicto(t)["3"])
        ancla = "                    viol_cota_obst[k] = True\n"
        t = self._mutar(ancla, ancla + "                else: z_t = 0  # [R]\n")
        self.assertFalse(self._veredicto(t)["3"])

    def test_alias_fuera_de_la_copia(self) -> None:
        sem = "    \"\"\"420110–420509.\"\"\"\n"
        for linea in ("    x: dict = Q.ESCENARIOS_Q\n    x.update({})\n",
                      "    for x in (Q.ESCENARIOS_Q,):\n        x.update({})\n",
                      "    (x := Q.ESCENARIOS_Q).update({})\n",
                      "    getattr(Q, 'ESCENARIOS_Q').update({})\n",
                      "    x, y = Q.ESCENARIOS_Q, 0\n    x.update({})\n",
                      "    np.copyto(Q.PESOS_TRIAL13, 0)\n"):
            t = self._mutar(sem, sem + linea)
            self.assertFalse(self._veredicto(t)["2"], linea)
        t = self._mutar("def semillas_R() -> List[int]:",
                        "def _f_R(x=Q.ESCENARIOS_Q):\n    x.update({})\n\n\n"
                        "def semillas_R() -> List[int]:")
        self.assertFalse(self._veredicto(t)["2"])
        t = self._mutar("import csv\n", "import csv\nimport operator\n")
        self.assertFalse(self._veredicto(t)["2"])

    def test_carpeta_y_ruta_de_Q(self) -> None:
        t = self._mutar("    sys.path.insert(0, str(_CARPETA_Q))\n",
                        "    sys.path.insert(1, str(_CARPETA_Q))\n")
        self.assertFalse(self._veredicto(t)["2"])
        t = self._mutar('(_CARPETA_R.parent / "expQ_obstaculos_moviles").resolve()',
                        '(_CARPETA_R.parent / "copia_Q").resolve()')
        self.assertFalse(self._veredicto(t)["2"])

    def test_asname_y_religadura(self) -> None:
        t = self._mutar("(ALFA_CBF, ANCHO_PERIFERIA,",
                        "(ALFA_CBF as ANCHO_PERIFERIA, ANCHO_PERIFERIA as ALFA_CBF,")
        self.assertFalse(self._veredicto(t)["4"])
        t = self._mutar("from correr_experimento_O import CRITERIOS_FALLA, _inicializar_trabajador",
                        "from correr_experimento_O import CRITERIOS_FALLA, _inicializar_trabajador"
                        ", ARENA")
        self.assertFalse(self._veredicto(t)["4"])

    def test_crlf(self) -> None:
        v = C.comprobacion_1(self.r.replace("\n", "\r\n"), self.q)[0]
        self.assertTrue(any("CRLF" in x for x in v))

    def test_global_extra(self) -> None:
        t = self._mutar("    \"\"\"420110–420509.\"\"\"\n",
                        "    \"\"\"420110–420509.\"\"\"\n    global _MODELO\n")
        self.assertFalse(self._veredicto(t)["2"])


class PruebaEstadistica(unittest.TestCase):

    def test_valores_del_exploratorio(self) -> None:
        lo, hi = A.clopper_pearson(0, 100)
        self.assertEqual((lo, round(hi, 4)), (0.0, 0.0362))
        p = lambda b, c: A.mcnemar_exacta(set(range(b)), set(range(100, 100 + c)))[2]
        self.assertEqual(p(3, 0), 0.25)
        self.assertEqual(round(p(8, 3), 4), 0.2266)
        self.assertEqual(round(p(28, 9), 4), 0.0026)
        self.assertEqual(round(p(6, 0), 5), 0.03125)

    def test_reglas_de_lectura(self) -> None:
        self.assertEqual(A.veredicto_p(6, 0, 0.03125), "sostenida")
        self.assertEqual(A.veredicto_p(0, 6, 0.03125), "no sostenida (dirección contraria)")
        self.assertEqual(A.veredicto_p(5, 0, 0.0625), "no sostenida")
        self.assertEqual(A.veredicto_p(0, 0, 1.0), "no sostenida (sin discordantes)")
        self.assertEqual(A.veredicto_h6a(0, 0), "no evaluable en el nivel")
        self.assertEqual(A.veredicto_h6a(4, 3), "no cumplida")
        self.assertEqual(A.veredicto_h6a(4, 4), "cumplida")

    def test_holm(self) -> None:
        aj = A.holm([0.01, 0.04, 0.03, 0.5])
        self.assertEqual([round(x, 6) for x in aj], [0.04, 0.09, 0.09, 0.5])


class PruebaAnalisisSintetico(unittest.TestCase):
    """El análisis con columnas de la Parte B y trazas inventadas (datos de Q)."""

    def test_parte_b_y_figuras(self) -> None:
        datos, columnas = A.cargar([A.RUTA_CSV_Q_S1, A.RUTA_CSV_EXPL_Q])
        bajo = sorted(s for s in datos["S3_din"]
                      if datos["S3_din"][s]["d_min_obst_superficie"] < 0.10)
        self.assertEqual(len(bajo), 4)
        for c in datos.values():
            for f in c.values():
                d = f["d_min_obst_superficie"]
                f.update({"d_min_sin_fallback": d, "d_min_fuera_ventana_3": max(d, 0.11),
                          "d_min_fuera_ventana_5": max(d, 0.11),
                          "d_min_fuera_ventana_10": max(d, 0.11),
                          "fallback_ventana_d_min_5": 1.0, "agente_d_min": 0.0})
        datos["S3_din"][bajo[0]]["fallback_ventana_d_min_5"] = 0.0
        datos["S3_din"][bajo[0]]["d_min_fuera_ventana_5"] = 0.09
        datos["S1_din"][420000]["contactos_obst_eventos"] = 1.0
        columnas |= set(A.COLUMNAS_PARTE_B)
        with tempfile.TemporaryDirectory() as d:
            trz = Path(d) / "trazas"
            trz.mkdir()
            for k, s in [("S3", x) for x in bajo] + [("S1", 420000)]:
                filas = [{"paso": t, "agente": a, "fallback": int(a == 0 and t in (8, 9)),
                          "d_obst": 0.3 - 0.002 * min(t, 100), "en_escape": 0, "intervino": 0,
                          "x_antes": 1.0, "y_antes": 1.0, "x_despues": 1.0, "y_despues": 1.0,
                          "contacto_nuevo": int(a == 0 and t == 10)}
                         for t in range(500) for a in range(5)]
                R.escribir_traza_R(filas, trz / f"R_{k}_din_{s}.csv")
            L, V = A.resumen(datos, columnas, "prueba-control", "R", None, trz)
            self.assertEqual(V["H6a-S3"], "no cumplida")
            self.assertEqual(V["H6b-S3"], "no cumplida")
            self.assertEqual((V["H6a-S1"], V["H6b-S1"]), ("no evaluable en el nivel", "cumplida"))
            self.assertEqual(V["H5a"], "no cumplida")
            self.assertTrue(any("1 contactos nuevos, 1 en la ventana" in x for x in L))
            self.assertTrue(any("no se lee como 'el filtro falla'" in x for x in L))
            self.assertEqual(V["H3a"], "sostenida")
            L2, V2 = A.resumen(datos, columnas, "prueba-control", "R", None, trz,
                               "no evaluable: control_bit_a_bit_R.txt dice PARTE B: NO")
            self.assertTrue(V2["H6a-S3"].startswith("no evaluable"))
            self.assertTrue(any("ubicación del contacto no evaluable" in x for x in L2))
            reg = Path(d) / "control_bit_a_bit_R.txt"
            reg.write_bytes(b"CONTROL: OK\nPARTE B: NO\n")
            self.assertIn("PARTE B: NO", A.estado_parte_b([reg]) or "")
            reg.write_bytes(b"CONTROL: OK\nPARTE B: OK\n")
            self.assertIsNone(A.estado_parte_b([reg]))
            self.assertTrue(any(x.startswith("  - un cambio del veredicto del Exp Q") for x in L))
            hechas = A.figuras(datos, "prueba-control", "R", True, "_x", trz, Path(d) / "fig")
            self.assertEqual(len(hechas), 3)
            self.assertTrue(all((Path(d) / "fig" / h).exists() for h in hechas))


class PruebaVerificacion(unittest.TestCase):
    """VERIFICACIÓN del resumen: todas las verificaciones al empezar y al terminar
    de los tres registros (§4 del prerregistro; adenda del 09-11)."""

    INICIO = [
        "inicio 2026-11-09 09:55:12",
        "huella del Exp Q: e265 (la de S1 y el exploratorio)",
        "huella de R: c31f",
        "ENTORNO_R python 3.13.14 | Intel64",
        "procesos de trabajo: 11; -B sí",
        "PREREGISTRO_R.md sha256 a463 (Fijado: 2026-11-09 01:38)",
        "COPIAS del Exp O (copia = esperado = original):",
        "  IGUAL 65d6 lib/__init__.py",
        "STACK: torch 2.10.0 — igual a requisitos_congelados_2026-09-09",
        "RESULTADOS DEL EXP Q sin cambios (S1 y crudos exploratorios):",
        "  IGUAL ff55 resultados/registro_Q.txt",
        "ÁRBOL DEL EXP Q igual a la referencia: 97 archivos",
        "procesos: ninguna otra corrida, ni scripts del coordinador, ni MATLAB/Webots",
        "energía: enchufada, batería 100 %",
        "sin reinicio pendiente de Windows",
        "congelados de la campaña al empezar (PROTOCOLO_L0_L2.md:210): IGUAL a lo probado"]
    FIN = [
        "AL TERMINAR:",
        "  copias del Exp O iguales",
        "  STACK: torch 2.10.0 — igual a requisitos_congelados_2026-09-09",
        "  RESULTADOS DEL EXP Q sin cambios (S1 y crudos exploratorios):",
        "  ÁRBOL DEL EXP Q igual a la referencia: 97 archivos",
        "  congelados de la campaña al terminar: IGUAL a lo probado",
        "  procesos: ninguna otra corrida, ni scripts del coordinador, ni MATLAB/Webots",
        "  energía: enchufada, batería 100 %",
        "  manifiesto pre: todas sus entradas con el sha256 actual",
        "  fin 2026-11-09 10:07:08",
        "HUELLA_Q e265",
        "HUELLA_R c31f"]

    def test_inicio_y_fin_en_los_tres_registros(self) -> None:
        resultado = "S1_din: cob_acc=0.59930086 interv=0.547856 t/ep=5.46 s; criterios — x 0"
        registros = {
            "control_bit_a_bit_R.txt": ["CONTROL — Exp R"] + self.INICIO + ["CONTROL: OK"]
            + self.FIN,
            "pasabilidad_R.txt": ["PASABILIDAD — Exp R"] + self.INICIO
            + ["  S1: peor caso → PASABLE", "PASABILIDAD: OK"] + self.FIN,
            "registro_R.txt": [R.ENCABEZADO_R] + self.INICIO + [resultado] + self.FIN}
        with tempfile.TemporaryDirectory() as d:
            for nombre, lineas in registros.items():
                (Path(d) / nombre).write_bytes(("\n".join(lineas) + "\n").encode("utf-8"))
            L = A.seccion_verificacion("resultado", Path(d))
        for nombre in registros:
            for x in self.INICIO + self.FIN:
                self.assertIn(f"  {nombre}: {x.strip()}", L, (nombre, x))
        self.assertFalse(any(resultado in x for x in L))
        self.assertIn("  falta comparar_ast_R.txt", L)

    @unittest.skipUnless((A.DIR_RES / "control_bit_a_bit_R.txt").exists()
                         and (A.DIR_RES / "pasabilidad_R.txt").exists(),
                         "faltan los registros del control y de la pasabilidad")
    def test_registros_reales(self) -> None:
        L = A.seccion_verificacion("resultado")
        for nombre in ("control_bit_a_bit_R.txt", "pasabilidad_R.txt"):
            lineas = [x.strip() for x in
                      (A.DIR_RES / nombre).read_text(encoding="utf-8").splitlines()]
            fin_inicio = next(i for i, x in enumerate(lineas)
                              if x.startswith("congelados de la campaña al empezar"))
            esperadas = lineas[1:fin_inicio + 1] + lineas[lineas.index("AL TERMINAR:"):]
            self.assertEqual([x for x in esperadas if f"  {nombre}: {x}" not in L], [], nombre)


class PruebaCompuertaExperimento(unittest.TestCase):

    def test_lineas_parte_b(self) -> None:
        self.assertEqual(R.lineas_parte_b_R([], []), ["PARTE B: OK"])
        auto = ["S3_din/420117: 1 agente-pasos en fallback se movieron sin contacto",
                "S1_din/420200: contactos_registrados ≠ contactos_obst_eventos"]
        L = R.lineas_parte_b_R(auto, ["traza que falta: R_S3_din_420117.csv"])
        self.assertTrue(L[0].startswith("PARTE B: NO"))
        for p in auto:
            self.assertIn(f"  autochequeo que falló — {p}", L)
        self.assertIn("  trazas — traza que falta: R_S3_din_420117.csv", L)
        self.assertTrue(any("66 columnas" in x and "comprobación 3" in x for x in L))
        self.assertTrue(R.lineas_parte_b_R([], [], True)[0].startswith("PARTE B: NO"))

    def test_todos_los_motivos(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            carpeta = Path(d)
            res = carpeta / "resultados"
            res.mkdir()
            for nombre in R.REQUERIDOS_MANIFIESTO_R:
                (carpeta / nombre).write_bytes(nombre.encode("utf-8"))
            h = {n: hashlib.sha256(n.encode("utf-8")).hexdigest()
                 for n in R.REQUERIDOS_MANIFIESTO_R}
            h["PREREGISTRO_R.md"] = "0" * 64            # el prerregistro cambió después
            (res / "manifiesto_R_pre_20261025_0900.txt").write_bytes(
                ("\n".join(f"{v} *./{k}" for k, v in h.items()) + "\nHUELLA_R abc\n")
                .encode("utf-8"))
            m = R.motivos_experimento_R(res, carpeta, "hq", "abc", R.semillas_R(),
                                        "PREREGISTRO_R.md sha256 x (Fijado: 2026-10-26 14:00)",
                                        R.linea_entorno_R(), False)
            texto = " | ".join(m)
            self.assertIn("PREREGISTRO_R.md cambió después del manifiesto", texto)
            for falta in ("comparar_ast_R.txt", "control_bit_a_bit_R.txt", "pasabilidad_R.txt"):
                self.assertIn(f"falta {falta}", texto)
            self.assertEqual(len(m), 4)
            # Con otro código de R, el manifiesto tampoco vale.
            m2 = R.motivos_manifiesto_R(res, carpeta, "otra")
            self.assertTrue(any("OTRO código" in x for x in m2))
            # Un control con PARTE B: NO frena el experimento salvo --sin-parte-b.
            (res / "control_bit_a_bit_R.txt").write_bytes(b"CONTROL: OK\nPARTE B: NO\n")
            m3 = R.motivos_experimento_R(res, carpeta, "hq", "abc", R.semillas_R(), "p",
                                         "e", False)
            self.assertTrue(any("PARTE B: NO" in x for x in m3))
            m4 = R.motivos_experimento_R(res, carpeta, "hq", "abc", R.semillas_R(), "p",
                                         "e", True)
            self.assertFalse(any("PARTE B: NO" in x for x in m4))

    def test_prerregistro_fijado_y_manifiesto(self) -> None:
        self.assertTrue(R.RE_FIJADO_R.match("Fijado: 2026-10-26 14:05"))
        self.assertFalse(R.RE_FIJADO_R.match("Fijado: BORRADOR — sin fijar"))
        with tempfile.TemporaryDirectory() as d:
            res = Path(d)
            (res / "parciales").mkdir()
            (res / "trazas").mkdir()
            self.assertEqual(R.resultados_de_R_existentes(res), [])
            (res / "parciales" / "controlR_S1_din.csv").write_bytes(b"x")
            self.assertEqual(R.resultados_de_R_existentes(res), [])
            (res / "parciales" / "R_S1_din.csv").write_bytes(b"x")
            self.assertEqual(R.resultados_de_R_existentes(res), ["R_S1_din.csv"])

    def test_procesos(self) -> None:
        s = R.patrones_coordinador_R()
        self.assertTrue(R.proceso_bloquea_R("python.exe", "python replica_con_obstaculo.py "
                                            "--campana L2_obstaculo_2", s))
        self.assertTrue(R.proceso_bloquea_R("python.exe", "python panel_demo.py", s))
        self.assertTrue(R.proceso_bloquea_R("MATLAB.exe", "", s))
        self.assertTrue(R.proceso_bloquea_R("python.exe", "python -B correr_experimento_Q.py "
                                            "control", s))
        self.assertFalse(R.proceso_bloquea_R("python3.13.exe", "C:/x/servidor_inventor_mcp.py", s))
        self.assertFalse(R.proceso_bloquea_R("python.exe", "python -c from multiprocessing."
                                             "spawn import spawn_main", s))


class PruebaReanudacion(unittest.TestCase):
    """Dos semillas de S1_din con 2 procesos, en directorios temporales."""

    def test_reutiliza_y_rehace(self) -> None:
        cond = [R.CondicionQ("S1_din", "S1", "din")]
        sem = [420000, 420001]
        hq, hr = R.Q.huella_codigo(), R.huella_R()
        with tempfile.TemporaryDirectory() as d:
            par, trz = Path(d) / "parciales", Path(d) / "trazas"
            msgs = []
            f1 = R.correr_condiciones_R(cond, 2, "prueba", hq, hr, sem, par, trz, msgs.append)
            self.assertEqual(sorted(int(f["seed_ep"]) for f in f1), sem)
            self.assertTrue(all(isinstance(v, str) for v in f1[0].values()))
            firma, sha = R._leer_firma_R(par / "prueba_S1_din.firma")
            self.assertEqual(firma, f"{hr} semillas 420000-420001 n 2 python "
                                    f"{platform.python_version()}")
            self.assertEqual(sha, hashlib.sha256((par / "prueba_S1_din.csv").read_bytes())
                             .hexdigest())
            msgs.clear()
            f2 = R.correr_condiciones_R(cond, 2, "prueba", hq, hr, sem, par, trz, msgs.append)
            self.assertTrue(any("(reutilizada)" in x for x in msgs))
            self.assertEqual(f1, f2)
            ruta = par / "prueba_S1_din.csv"
            datos = ruta.read_bytes()
            ruta.write_bytes(datos[: datos.rstrip(b"\n").rfind(b",") + 1])   # corte
            msgs.clear()
            f3 = R.correr_condiciones_R(cond, 2, "prueba", hq, hr, sem, par, trz, msgs.append)
            self.assertTrue(any("se rehace: el CSV no es el que se firmó" in x for x in msgs))
            sin_t = lambda fs: [{k: v for k, v in f.items() if k != "t_episodio_s"} for f in fs]
            self.assertEqual(sin_t(f1), sin_t(f3))
            self.assertEqual(len(list(par.glob("prueba_S1_din_respaldo_*.csv"))), 1)
            self.assertEqual(len(list(par.glob("prueba_S1_din_respaldo_*.firma"))), 1)
            # Con el sha256 al día, un campo de más o un corte en la coma se detectan igual.
            ruta, meta = par / "prueba_S1_din.csv", par / "prueba_S1_din.firma"
            lineas = ruta.read_bytes().split(b"\n")
            for malo, motivo in ((b"\n".join(lineas[:-2] + [lineas[-2] + b",extra", b""]),
                                  "campos de más"),
                                 (ruta.read_bytes().rstrip(b"\n"), "no termina")):
                ruta.write_bytes(malo)
                meta.write_bytes(f"{firma}\ncsv {hashlib.sha256(malo).hexdigest()}\n"
                                 .encode("utf-8"))
                m = R.parcial_invalido_R(ruta, firma, sem, R.columnas_esperadas_R(), "prueba",
                                         "S1_din", trz)
                self.assertIn(motivo, m or "")


class PruebaSinEfectos(unittest.TestCase):

    def _listado(self):
        return sorted(str(p) for raiz in (_CARPETA, R._CARPETA_Q) for p in raiz.rglob("*"))

    def test_importar_no_escribe(self) -> None:
        antes = self._listado()
        r = subprocess.run([sys.executable, "-B", "-c", "import correr_experimento_R"],
                           cwd=str(_CARPETA), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._listado(), antes)

    def test_sin_B_se_niega(self) -> None:
        # Sin -B y sin PYTHONDONTWRITEBYTECODE; con un modo inválido, que no
        # escribiría nada aunque el chequeo fallara.
        antes = self._listado()
        entorno = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
        r = subprocess.run([sys.executable, str(_CARPETA / "correr_experimento_R.py"), "nada"],
                           cwd=tempfile.gettempdir(), capture_output=True, text=True,
                           env={**entorno, "PYTHONIOENCODING": "utf-8"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("python -B", r.stderr + r.stdout)
        self.assertEqual(self._listado(), antes)
        for script in ("analizar_experimento_R.py", "comparar_ast_R.py"):
            r = subprocess.run([sys.executable, str(_CARPETA / script)],
                               cwd=tempfile.gettempdir(), capture_output=True, text=True,
                               env={**entorno, "PYTHONIOENCODING": "utf-8"})
            self.assertNotEqual(r.returncode, 0, script)
            self.assertIn("python -B", r.stderr + r.stdout, script)
        self.assertEqual(self._listado(), antes)


if __name__ == "__main__":
    unittest.main()
