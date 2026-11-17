"""
test_exploratorio_Q.py
======================
EXPLORATORIO — pruebas de lo nuevo de S2 y S3 que no necesita correr
episodios: la atribución por semilla (la del análisis y la del verificador,
escritas por separado, tienen que coincidir), el "no aplica" del control, el
rótulo y la columna `exploratorio`.

    python -B -m unittest test_exploratorio_Q -v

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_CARPETA = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import analizar_exploratorio_Q as A
import correr_exploratorio_Q as O
import verificar_cifras_exploratorio_Q as V

COLS = ("contactos_obst_eventos", "escape_agotados", "qp_fallbacks",
        "escape_infactibles_junto_obst")


def _datos():
    """S2 con 4 semillas: el evento en din y su presencia en los otros."""
    base = {c: 0.0 for c in COLS}
    d = {f"S2_{t}": {s: dict(base) for s in (1, 2, 3, 4)}
         for t in ("din", "ctrl", "quieto", "sinvel")}
    d["S2_din"][2]["escape_agotados"] = 1.0
    d["S2_ctrl"][2]["escape_agotados"] = 1.0
    d["S2_quieto"][3]["escape_agotados"] = 2.0        # otra semilla: no cuenta
    d["S2_din"][4]["contactos_obst_eventos"] = 3.0
    d["S2_quieto"][4]["contactos_obst_eventos"] = 1.0
    d["S2_din"][1]["qp_fallbacks"] = 2.0
    d["S2_sinvel"][1]["qp_fallbacks"] = 1.0
    return d


class PruebaAtribucion(unittest.TestCase):

    def test_analisis(self) -> None:
        d = _datos()
        sem = [1, 2, 3, 4]
        self.assertEqual(A.atribucion(d, "S2", "escape_agotados", sem),
                         [(2, "sí", "no", "no")])
        self.assertEqual(A.atribucion(d, "S2", "contactos_obst_eventos", sem),
                         [(4, "no aplica", "sí", "no")])
        self.assertEqual(A.atribucion(d, "S2", "qp_fallbacks", sem),
                         [(1, "no", "no", "sí")])
        self.assertEqual(A.atribucion(d, "S2", "escape_infactibles_junto_obst", sem), [])

    def test_verificador_coincide_con_el_analisis(self) -> None:
        d = _datos()
        texto = {c: {s: {k: repr(v) for k, v in f.items()} for s, f in por.items()}
                 for c, por in d.items()}
        sem = [1, 2, 3, 4]
        for m in COLS:
            a = A.atribucion(d, "S2", m, sem)
            v = V.atribucion(texto, "S2", m, sem)
            self.assertEqual([(x[0],) + x[1:] for x in a], [(x[0],) + x[2:] for x in v], m)


class PruebaRotulos(unittest.TestCase):

    def test_encabezado_y_columna(self) -> None:
        self.assertTrue(O.ENCABEZADO.startswith("EXPLORATORIO —"))
        filas = O.filas_marcadas([{"condicion": "S2_din", "seed_ep": 420000}])
        self.assertEqual(list(filas[0])[0], "exploratorio")
        self.assertEqual(filas[0]["exploratorio"], 1)
        for p in (O.RUTA_REPRO_CSV, O.RUTA_CSV_EXPL, O.RUTA_REG_EXPL):
            self.assertIn("EXPLORATORIO", p.name)

    def test_las_constantes_comprometidas_coinciden(self) -> None:
        self.assertEqual(O.HUELLA_ESPERADA, V.HUELLA_S1)
        self.assertEqual(O.SHA256_S1, V.SHA256_S1)
        self.assertEqual(O.NIVELES_EXPLORATORIOS, V.NIVELES_EXPL)


class PruebaEventosRaros(unittest.TestCase):
    """(24-10) El IC y la prueba exacta: la del análisis (scipy) y la del
    verificador (propia, sin scipy) tienen que coincidir, y con valores
    conocidos."""

    def test_clopper_pearson_propio_igual_a_scipy(self) -> None:
        for n in (10, 100):
            for k in range(0, n + 1, max(1, n // 25)):
                a = A.clopper_pearson(k, n)
                v = V.clopper_pearson_propio(k, n)
                self.assertAlmostEqual(a[0], v[0], places=9, msg=(k, n))
                self.assertAlmostEqual(a[1], v[1], places=9, msg=(k, n))
        self.assertEqual(f"{V.clopper_pearson_propio(0, 100)[1]:.4f}", "0.0362")
        self.assertEqual(V.clopper_pearson_propio(0, 100)[0], 0.0)
        self.assertEqual(V.clopper_pearson_propio(100, 100)[1], 1.0)

    def test_mcnemar_propia_igual_a_scipy_y_conocidos(self) -> None:
        for sa in range(0, 12):
            for sb in range(0, 12):
                a_set = set(range(sa))
                b_set = set(range(100, 100 + sb))
                pa = A.mcnemar_exacta(a_set, b_set)
                pv = V.mcnemar_propia(a_set, b_set)
                self.assertEqual(pa[:2], pv[:2])
                self.assertAlmostEqual(pa[2], pv[2], places=12, msg=(sa, sb))
        conocidos = {(0, 3): 0.25, (8, 3): 232 / 1024, (2, 0): 0.5, (0, 0): 1.0, (8, 0): 2 / 256}
        for (sa, sb), p in conocidos.items():
            _, _, pv = V.mcnemar_propia(set(range(sa)), set(range(100, 100 + sb)))
            self.assertAlmostEqual(pv, p, places=15, msg=(sa, sb))

    def test_concordantes_no_cuentan(self) -> None:
        """Episodios con el evento en las dos condiciones no entran en la prueba."""
        sa, sb, p = V.mcnemar_propia({1, 2, 3, 4}, {1, 2, 3, 9})
        self.assertEqual((sa, sb, p), (1, 1, 1.0))

    def test_formato_p(self) -> None:
        for f in (A.formato_p, V.formato_p):
            self.assertEqual(f(7.45e-09), "< 0.0001")
            self.assertEqual(f(0.0625), "0.0625")
            self.assertEqual(f(0.2265625), "0.2266")


if __name__ == "__main__":
    unittest.main()
