"""
test_verificar_cifras_R.py
==========================
Pruebas del verificador del Exp R (`verificar_cifras_R.py`). Es un archivo
aparte: cambiar `test_experimento_R.py` sería otra desviación con adenda.

- Estadística propia: Clopper-Pearson y McNemar contra valores conocidos y
  contra scipy a 10 decimales; Holm; EE con ddof = 1; formatos.
- Reglas de lectura: los casos con trampa (C1–C13). Sus esperados los
  derivaron A CIEGAS, desde el texto del §2 del prerregistro y sin ver el
  código, dos revisores independientes (workflow wf_0a273517-2d1, 09-11), y
  coincidieron entre sí.
- Parte B: una traza calculada a mano, con el empate de 1e-9 y la ventana de
  5, y las 11 trazas reales del control.
- Las dos pruebas reales del análisis, que tienen que dar 0 diferencias.
- Mutaciones, que tienen que detectarse todas:
  - una cifra cambiada;
  - un veredicto invertido;
  - una línea con cifras agregada;
  - una línea borrada;
  - una cifra cambiada por otro valor que ya aparece en otro lugar del resumen;
  - una celda del CSV cambiada, con el resumen intacto;
  - una columna de la Parte B del CSV cambiada;
  - una traza alterada.
- El modo resultado sobre un experimento sintético (las semillas vistas
  relabeladas a 420110–420509), con su VERIFICACIÓN, «PARTE B: OK» y
  «PARTE B: NO». El resumen lo genera el análisis prerregistrado.

    python -B -m unittest test_verificar_cifras_R -v

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List

if not sys.flags.dont_write_bytecode:
    raise SystemExit("PARAR: correr con python -B (si no, se escribe __pycache__).")

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import verificar_cifras_R as VC  # noqa: E402

try:
    from scipy.stats import beta, binomtest  # noqa: F401
    HAY_SCIPY = True
except ImportError:
    HAY_SCIPY = False

COLUMNAS_TRAZA = ("paso", "agente", "fallback", "d_obst", "en_escape", "intervino",
                  "x_antes", "y_antes", "x_despues", "y_despues", "contacto_nuevo")
BASE: Dict[str, str] = {
    "qp_fallbacks": "0", "escape_agotados": "0", "contactos_obst_eventos": "0",
    "viol_cota_obst_agente_eps": "0", "d_min_obst_superficie": "0.3",
    "escape_infactibles_junto_obst": "0", "cobertura_accesible": "0.5",
    "cob_acc_arranque": "0.5", "cbf_frac_interv": "0.5", "cbf_frac_lig_pared": "0.1",
    "cbf_frac_lig_robot": "0.1", "cbf_frac_lig_obst": "0.1", "f1_filas_saturadas": "0",
    "pasos": "500"}


def datos_sinteticos(sem: List[int]) -> VC.Datos:
    return {f"{k}_{t}": {s: dict(BASE, condicion=f"{k}_{t}", seed_ep=str(s)) for s in sem}
            for k in VC.NIVELES for t in VC.TIPOS}


def pb_sin_fallback(d: VC.Datos, sem: List[int]) -> Dict:
    """La Parte B de filas sin fallback (identidad del §3.2)."""
    pb: Dict = {}
    for c, filas in d.items():
        for s in sem:
            x = float(filas[s]["d_min_obst_superficie"])
            pb.setdefault(c, {})[s] = {"_d_min": x, "fallback_ventana_d_min_5": 0,
                                       "d_min_sin_fallback": x, "d_min_fuera_ventana_3": x,
                                       "d_min_fuera_ventana_5": x, "d_min_fuera_ventana_10": x}
    return pb


def escribir_traza(ruta: Path, pasos: int, d: Dict, fb: set, contacto: set,
                   movido: set = frozenset()) -> List[Dict[str, str]]:
    filas = []
    x = [1.0] * VC.N_AGENTES        # la posición se acumula: cada (t, k) de `movido` avanza 0,5
    for t in range(pasos):
        for k in range(VC.N_AGENTES):
            x_a = x[k]
            if (t, k) in movido:
                x[k] += 0.5
            filas.append({"paso": str(t), "agente": str(k), "fallback": str(int((t, k) in fb)),
                          "d_obst": repr(d.get((t, k), 0.5)), "en_escape": "0", "intervino": "0",
                          "x_antes": repr(x_a), "y_antes": "1.0", "x_despues": repr(x[k]),
                          "y_despues": "1.0", "contacto_nuevo": str(int((t, k) in contacto))})
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS_TRAZA, lineterminator="\n")
        w.writeheader()
        w.writerows(filas)
    return filas


# =============================================================================
# ESTADÍSTICA PROPIA
# =============================================================================

class PruebaEstadistica(unittest.TestCase):

    def test_clopper_pearson_conocidos(self) -> None:
        lo, hi = VC.clopper_pearson(0, 100)
        self.assertEqual((lo, f"{hi:.4f}"), (0.0, "0.0362"))
        lo, hi = VC.clopper_pearson(0, 400)
        self.assertEqual(f"{100 * hi:.3f}", "0.918")       # §2.3: 0/400 → cota 0,918 %
        lo, hi = VC.clopper_pearson(400, 400)
        self.assertEqual(hi, 1.0)

    @unittest.skipUnless(HAY_SCIPY, "sin scipy")
    def test_clopper_pearson_contra_scipy(self) -> None:
        for n in (4, 100, 400):
            for k in sorted({0, 1, 2, 3, 4, 5, n // 2, n - 1, n} & set(range(n + 1))):
                lo, hi = VC.clopper_pearson(k, n)
                lo_s = 0.0 if k == 0 else float(beta.ppf(0.025, k, n - k + 1))
                hi_s = 1.0 if k == n else float(beta.ppf(0.975, k + 1, n - k))
                self.assertLess(abs(lo - lo_s), VC.TOL_SCIPY, (k, n))
                self.assertLess(abs(hi - hi_s), VC.TOL_SCIPY, (k, n))

    def test_mcnemar_conocidos(self) -> None:
        self.assertEqual(VC.mcnemar(3, 0), 0.25)
        self.assertEqual(VC.mcnemar(6, 0), 0.03125)
        self.assertEqual(VC.mcnemar(8, 3), 0.2265625)
        self.assertEqual(VC.mcnemar(0, 0), 1.0)
        self.assertEqual(VC.mcnemar(5, 5), 1.0)
        self.assertEqual(round(VC.mcnemar(28, 9), 4), 0.0026)

    @unittest.skipUnless(HAY_SCIPY, "sin scipy")
    def test_mcnemar_contra_scipy(self) -> None:
        for b in range(0, 13):
            for c in range(0, 13):
                if b + c:
                    ref = float(binomtest(min(b, c), b + c, 0.5).pvalue)
                    self.assertLess(abs(VC.mcnemar(b, c) - ref), VC.TOL_SCIPY, (b, c))

    def test_C11_holm(self) -> None:
        # Orden de la familia del §2.4; esperados derivados a ciegas.
        ps = [0.0625, 0.5, 0.001953125, 0.0026, 0.0078125, 0.2265625, 0.25]
        esperado = [0.25, 0.6796875, 0.013671875, 0.0156, 0.0390625, 0.6796875, 0.6796875]
        for a, e in zip(VC.holm(ps), esperado):
            self.assertAlmostEqual(a, e, places=12)
        self.assertEqual(VC.frase_holm(0.0137, 6, 0), "p Holm < 0,05 en la dirección predicha")
        self.assertEqual(VC.frase_holm(0.0137, 0, 6), "p Holm ≥ 0,05 o dirección contraria")
        self.assertEqual(VC.frase_holm(0.25, 5, 0), "p Holm ≥ 0,05 o dirección contraria")

    def test_holm_con_tope_en_1(self) -> None:
        self.assertEqual(VC.holm([0.5, 0.6, 0.9]), [1.0, 1.0, 1.0])

    def test_ee_ddof_1(self) -> None:
        m, lo, hi = VC.ic95([1.0, 2.0, 3.0, 4.0])
        ee = math.sqrt(5.0 / 3.0) / 2.0               # sd con ddof = 1: √(5/3)
        self.assertEqual(m, 2.5)
        self.assertAlmostEqual(lo, 2.5 - 1.96 * ee, places=15)
        self.assertAlmostEqual(hi, 2.5 + 1.96 * ee, places=15)
        self.assertNotAlmostEqual(lo, 2.5 - 1.96 * math.sqrt(1.25) / 2.0, places=6)  # ddof = 0

    def test_formatos(self) -> None:
        self.assertEqual(VC.fmt_p(0.00009), "< 0.0001")
        self.assertEqual(VC.fmt_p(0.0001), "0.0001")
        self.assertEqual(VC.fmt_p(0.2265625), "0.2266")
        self.assertEqual(VC.fmt_delta(0.1, 0.05, 0.15), "+0.10000000 [+0.05000000, +0.15000000]*")
        self.assertEqual(VC.fmt_delta(0.0, -0.1, 0.1), "+0.00000000 [-0.10000000, +0.10000000] ")
        self.assertEqual(VC.fmt_delta(0.1, 0.05, 0.15, marca=False),
                         "+0.10000000 [+0.05000000, +0.15000000]")
        self.assertEqual(VC.fmt_kn(0, 100), "0/100 [0.0000, 0.0362]")


# =============================================================================
# REGLAS DE LECTURA (casos C1–C13, esperados derivados a ciegas del §2.4)
# =============================================================================

class PruebaReglasDeLectura(unittest.TestCase):

    SEM = list(range(1, 21))

    def _hipotesis(self, d, motivo=None, pb=None, dir_trazas=Path("."), con_trazas=True):
        pb = pb if pb is not None else (None if motivo else pb_sin_fallback(d, self.SEM))
        return VC.lineas_hipotesis(d, self.SEM, pb, motivo, "R", con_trazas, dir_trazas)

    def test_C1_C2_direccion_b_c_en_H2(self) -> None:
        # H2: A = Sk_sinvel (primer término), B = Sk_din; b = sólo en A.
        d = datos_sinteticos(self.SEM)
        for s in self.SEM[:6]:
            d["S2_sinvel"][s]["viol_cota_obst_agente_eps"] = "1"
        self.assertEqual(VC.mcnemar_celdas(d, self.SEM, "bajo 0,13 m", "S2", "sinvel", "din"),
                         (6, 0, 6, 0, 0.03125))
        L, V, _ = self._hipotesis(d)
        self.assertEqual(V["H2-S2"], "sostenida")                                  # C1
        self.assertTrue(any("A = S2_sinvel 6/20" in x and "b/c = 6/0" in x for x in L))
        d = datos_sinteticos(self.SEM)
        for s in self.SEM[:6]:
            d["S2_din"][s]["viol_cota_obst_agente_eps"] = "1"
        L, V, _ = self._hipotesis(d)
        self.assertEqual(V["H2-S2"], "no sostenida (dirección contraria)")         # C2
        self.assertTrue(any("b/c = 0/6" in x for x in L))

    def test_direccion_contraria_exige_p(self) -> None:
        # §2.4: «(dirección contraria)» sólo si p < 0,05 con c > b.
        self.assertEqual(VC.regla_p(0, 3, 0.25), "no sostenida")
        self.assertEqual(VC.regla_p(1, 6, 0.125), "no sostenida")

    def test_umbrales_estrictos(self) -> None:
        # §2.1: «bajo 0,10 m» es d_min < 0,10 (estricto); igual la traza (§3.4) y H6.
        f = dict(BASE, d_min_obst_superficie="0.1")
        self.assertFalse(VC.tiene(f, "bajo 0,10 m"))
        self.assertFalse(VC.requiere_traza("din", f))
        self.assertTrue(VC.tiene(dict(BASE, d_min_obst_superficie="0.0999"), "bajo 0,10 m"))
        d = datos_sinteticos(self.SEM)
        pb = pb_sin_fallback(d, self.SEM)
        pb["S3_din"][self.SEM[0]].update({"_d_min": 0.1, "d_min_fuera_ventana_5": 0.1})
        _L, V, _ = self._hipotesis(d, pb=pb)
        self.assertEqual((V["H6a-S3"], V["H6b-S3"]), ("no evaluable en el nivel", "cumplida"))

    def test_sensibilidad_columnas_por_ventana(self) -> None:
        d = datos_sinteticos(self.SEM)
        pb = pb_sin_fallback(d, self.SEM)
        pb["S3_din"][self.SEM[0]].update({"d_min_fuera_ventana_3": 0.09})
        pb["S3_din"][self.SEM[1]].update({"d_min_fuera_ventana_5": 0.12})
        L, _V, _ = self._hipotesis(d, pb=pb)
        self.assertIn("    S3: W=1 0/20; W=3 1/20; W=10 0/20; W=5 umbral 0,13 1/20", L)

    def test_C3_C4_C5(self) -> None:
        self.assertEqual(VC.regla_p(5, 0, 0.0625), "no sostenida")                 # C3
        self.assertEqual(VC.regla_p(0, 0, 1.0), "no sostenida (sin discordantes)")  # C4
        self.assertEqual(VC.regla_p(3, 3, 1.0), "no sostenida")                    # C5

    def test_C6_H3b_direccional(self) -> None:
        h3b = next(p for p in VC.PRUEBAS if p[0] == "H3b")
        self.assertEqual(h3b[1:5], ("agotado", "S3", "din", "quieto"))             # A > B
        self.assertEqual(VC.regla_p(8, 0, 0.0078125), "sostenida")
        self.assertEqual(VC.regla_p(8, 3, 0.2265625), "no sostenida")
        self.assertEqual(VC.regla_p(0, 8, 0.0078125), "no sostenida (dirección contraria)")

    def test_C7_H4_compuesta(self) -> None:
        self.assertEqual(VC.regla_h4([0.0150, 0.0197]), "sostenida")
        self.assertEqual(VC.regla_h4([0.0100, -0.0010]), "no sostenida")
        self.assertEqual(VC.regla_h4([0.0, 0.0100]), "no sostenida")               # > 0 estricto
        # De punta a punta, con Δ constantes (EE = 0, lo = media).
        d = datos_sinteticos(self.SEM)
        for s in self.SEM:
            d["S1_din"][s]["cobertura_accesible"] = "0.6"
        L, V, _ = self._hipotesis(d)
        self.assertEqual(V["H4"], "no sostenida")      # Δ_S2 − Δ_S3 = 0: la pieza no cumple
        self.assertTrue(any(x.startswith("    Δ_S2 − Δ_S3:") and x.endswith("→ no cumple")
                            for x in L))
        for s in self.SEM:
            d["S2_din"][s]["cobertura_accesible"] = "0.6"
        _L, V, _ = self._hipotesis(d)
        self.assertEqual(V["H4"], "sostenida")

    def test_C8_H5a(self) -> None:
        self.assertEqual(VC.regla_h5a([0, 0, 0]), "cumplida")
        self.assertEqual(VC.regla_h5a([0, 0, 1]), "no cumplida")
        d = datos_sinteticos(self.SEM)
        s = self.SEM[3]
        d["S3_din"][s]["contactos_obst_eventos"] = "2"
        with tempfile.TemporaryDirectory() as t:
            # Contacto en (100, 2) con fallback propio en 97: en la ventana (96…100);
            # contacto en (200, 0) sin fallback: fuera.
            escribir_traza(Path(t) / f"R_S3_din_{s}.csv", 500, {}, {(97, 2)},
                           {(100, 2), (200, 0)})
            L, V, _ = self._hipotesis(d, dir_trazas=Path(t))
        self.assertEqual(V["H5a"], "no cumplida")
        self.assertIn("    lectura (§2.4): k ≥ 1 se reporta como tasa k/400 con su IC95 y se "
                      "discute con la traza de cada episodio (si el contacto cayó en la ventana "
                      "de un fallback del agente o no); no se lee como 'el filtro falla'", L)
        self.assertIn(f"    S3_din {s}: 2 contactos nuevos, 1 en la ventana de un fallback del "
                      f"agente", L)

    def test_C9_H6(self) -> None:
        self.assertEqual(VC.regla_h6a(0, 0), "no evaluable en el nivel")
        self.assertEqual(VC.regla_h6a(4, 4), "cumplida")
        self.assertEqual(VC.regla_h6a(4, 3), "no cumplida")
        self.assertEqual(VC.regla_h6b(0), "cumplida")
        self.assertEqual(VC.regla_h6b(2), "no cumplida")
        d = datos_sinteticos(self.SEM)
        pb = pb_sin_fallback(d, self.SEM)
        for s in self.SEM[:4]:
            pb["S3_din"][s].update({"_d_min": 0.09, "fallback_ventana_d_min_5": 1})
        _L, V, _ = self._hipotesis(d, pb=pb)
        self.assertEqual((V["H6a-S3"], V["H6b-S3"]), ("cumplida", "cumplida"))
        self.assertEqual(V["H6a-S1"], "no evaluable en el nivel")
        pb["S3_din"][self.SEM[0]].update({"fallback_ventana_d_min_5": 0,
                                          "d_min_fuera_ventana_5": 0.09})
        _L, V, _ = self._hipotesis(d, pb=pb)
        self.assertEqual((V["H6a-S3"], V["H6b-S3"]), ("no cumplida", "no cumplida"))

    def test_C10_parte_b_no(self) -> None:
        d = datos_sinteticos(self.SEM)
        d["S3_din"][self.SEM[0]]["contactos_obst_eventos"] = "1"
        with tempfile.TemporaryDirectory() as t:
            reg = Path(t) / "control_bit_a_bit_R.txt"
            reg.write_bytes("CONTROL: OK\nPARTE B: NO (H6 y la ubicación …)\n".encode("utf-8"))
            motivo = VC.motivo_parte_b([reg])
            reg.write_bytes(b"CONTROL: OK\nPARTE B: OK\n")
            self.assertIsNone(VC.motivo_parte_b([reg]))
        self.assertEqual(motivo, "no evaluable: control_bit_a_bit_R.txt dice PARTE B: NO "
                                 "(§7 del prerregistro)")
        L, V, _ = self._hipotesis(d, motivo=motivo)
        _L2, V2, _ = self._hipotesis(d)
        for k in VC.NIVELES:
            self.assertEqual((V[f"H6a-{k}"], V[f"H6b-{k}"]), (motivo, motivo))
            self.assertTrue(V[f"H6a-{k}"].startswith("no evaluable:"))
        for clave in ("H1-S3", "H1-S2", "H2-S2", "H2-S3", "H3a", "H3b", "H4", "H5a", "H5b"):
            self.assertEqual(V[clave], V2[clave], clave)        # H1–H5 se leen igual
        self.assertIn(f"    S3_din {self.SEM[0]}: ubicación del contacto {motivo}", L)

    def test_C12_S1_sin_veredicto(self) -> None:
        L, V, _ = self._hipotesis(datos_sinteticos(self.SEM))
        s1 = [x for x in L if x.startswith("    S1 (descriptiva, sin veredicto)")]
        self.assertEqual(len(s1), 2)
        self.assertTrue(all("→" not in x for x in s1))
        self.assertFalse(any(k.endswith("-S1") and k.startswith(("H1", "H2")) for k in V))

    def test_C13_familia_de_holm(self) -> None:
        self.assertEqual([p[0] for p in VC.PRUEBAS],
                         ["H1-S3", "H1-S2", "H2-S2", "H2-S3", "H3a", "H3b", "H5b"])


# =============================================================================
# PARTE B DESDE LAS TRAZAS
# =============================================================================

class PruebaParteB(unittest.TestCase):

    def test_traza_a_mano(self) -> None:
        # 10 pasos. Fallback del agente 0 en las decisiones 3 y 4.
        # (2, 1) = 0.0750000010000001 y (5, 0) = 0.075000001: el mínimo estricto es
        # (5, 0), pero la regla del 1e-9 toma la PRIMERA (t, k) con d ≤ d_min + 1e-9,
        # recorriendo t y k ascendentes, o sea (2, 1). (7, 0) = 0.09.
        d = {(2, 1): 0.0750000010000001, (5, 0): 0.075000001, (7, 0): 0.09}
        with tempfile.TemporaryDirectory() as t:
            filas = escribir_traza(Path(t) / "x.csv", 10, d, {(3, 0), (4, 0)}, set())
        r, probl = VC.parte_b_de_traza(filas, 10)
        self.assertEqual(probl, [])
        self.assertEqual(r["_d_min"], 0.075000001)
        self.assertEqual((r["paso_d_min"], r["agente_d_min"]), (2, 1))
        self.assertEqual((r["fallback_en_d_min"], r["racha_fallback_d_min"],
                          r["fallback_ventana_d_min_5"]), (0, 0, 0))
        self.assertEqual(r["d_min_sin_fallback"], 0.075000001)
        self.assertEqual(r["d_min_en_fallback"], 0.5)
        # Agente 0 en la ventana: W=3 en t = 3…6; W=5 en t = 3…8; W=10 en t = 3…9.
        self.assertEqual(r["d_min_fuera_ventana_3"], 0.0750000010000001)
        self.assertEqual(r["d_min_fuera_ventana_5"], 0.0750000010000001)
        self.assertEqual(r["d_min_fuera_ventana_10"], 0.0750000010000001)
        self.assertEqual((r["pasos_bajo_010"], r["pasos_bajo_010_fuera_ventana_5"]), (3, 1))
        self.assertEqual(r["pasos_agente_fallback"], 2)
        self.assertEqual((r["fb_desplazado"], r["xy_discontinuo"]), (0, 0))

    def test_minimo_en_fallback_y_racha(self) -> None:
        d = {(6, 2): 0.08}
        with tempfile.TemporaryDirectory() as t:
            filas = escribir_traza(Path(t) / "x.csv", 10, d, {(4, 2), (5, 2), (6, 2)}, set())
        r, _ = VC.parte_b_de_traza(filas, 10)
        self.assertEqual((r["paso_d_min"], r["agente_d_min"]), (6, 2))
        self.assertEqual((r["fallback_en_d_min"], r["racha_fallback_d_min"],
                          r["fallback_ventana_d_min_5"]), (1, 3, 1))
        self.assertEqual(r["d_min_fuera_ventana_5"], 0.5)

    def test_movido_sin_contacto(self) -> None:
        # El agente 1 está en fallback en t = 5 y se mueve sin contacto: fb_desplazado = 1;
        # con la bandera de t − 1 (sin fallback en 4), corrido = 0.
        with tempfile.TemporaryDirectory() as t:
            filas = escribir_traza(Path(t) / "x.csv", 10, {}, {(5, 1)}, set(), {(5, 1)})
        r, _ = VC.parte_b_de_traza(filas, 10)
        self.assertEqual((r["fb_desplazado"], r["fb_desplazado_corrido"]), (1, 0))

    def test_ventana_de_los_contactos(self) -> None:
        # Contacto en t = 10: un fallback propio en 6 (= t − 4) está en la ventana; en 5, no.
        with tempfile.TemporaryDirectory() as t:
            dentro = escribir_traza(Path(t) / "a.csv", 20, {}, {(6, 0)}, {(10, 0)})
            fuera = escribir_traza(Path(t) / "b.csv", 20, {}, {(5, 0)}, {(10, 0)})
            otro = escribir_traza(Path(t) / "c.csv", 20, {}, {(8, 1)}, {(10, 0)})
        self.assertEqual(VC.contactos_de_traza(dentro), (1, 1))
        self.assertEqual(VC.contactos_de_traza(fuera), (1, 0))
        self.assertEqual(VC.contactos_de_traza(otro), (1, 0))      # el fallback es de otro agente

    def test_trazas_reales_del_control(self) -> None:
        dif: List[str] = []
        datos, _cols = VC.cargar([VC.RUTA_CONTROL_CSV], dif)
        cuenta: Dict = {}
        pb = VC.parte_b_recalculada(datos, "controlR", VC.DIR_TRAZAS, dif, cuenta)
        self.assertEqual(dif, [])
        self.assertEqual(cuenta["filas_con_traza"], 11)
        self.assertEqual(cuenta["filas_por_identidad"], 900 - 11)
        self.assertEqual(pb["S3_din"][420025]["racha_fallback_d_min"], 33)


# =============================================================================
# LAS DOS PRUEBAS REALES
# =============================================================================

class PruebaResumenesReales(unittest.TestCase):

    def test_prueba_sobre_Q(self) -> None:
        dif, cuenta = VC.verificar("prueba-sustituto")
        self.assertEqual(dif, [])
        self.assertEqual(cuenta["lineas_resumen"], cuenta["lineas_esperadas"])

    def test_prueba_sobre_el_control(self) -> None:
        dif, cuenta = VC.verificar("prueba-control")
        self.assertEqual(dif, [])
        if HAY_SCIPY:
            self.assertGreater(cuenta["contrastes_scipy"], 0)


# =============================================================================
# MUTACIONES (todas sobre copias temporales)
# =============================================================================

class PruebaMutaciones(unittest.TestCase):

    RUTA = VC.DIR_RES / "resumen_R_prueba_sobre_control.txt"

    def _mutar(self, viejo: str, nuevo: str) -> List[str]:
        texto = self.RUTA.read_text(encoding="utf-8")
        self.assertEqual(texto.count(viejo), 1, viejo)
        with tempfile.TemporaryDirectory() as t:
            ruta = Path(t) / "resumen.txt"
            ruta.write_bytes(texto.replace(viejo, nuevo).encode("utf-8"))
            dif, _ = VC.verificar("prueba-control", ruta_resumen=ruta, contrastar=False)
        return dif

    def _detectada(self, dif: List[str]) -> None:
        self.assertTrue(any(x.startswith("RESUMEN línea") for x in dif), dif)

    def test_cifra_cambiada(self) -> None:
        self._detectada(self._mutar("b/c = 5/0; p = 0.0625 →", "b/c = 5/0; p = 0.0626 →"))

    def test_veredicto_invertido(self) -> None:
        self._detectada(self._mutar("\n    → sostenida\n", "\n    → no sostenida\n"))
        self._detectada(self._mutar("b/c = 10/0; p = 0.0020 → sostenida",
                                    "b/c = 10/0; p = 0.0020 → no sostenida"))

    def test_linea_con_cifras_agregada(self) -> None:
        viejo = "AGOTADOS de S1 y S2"
        texto = self.RUTA.read_text(encoding="utf-8")
        linea = next(x for x in texto.splitlines() if x.startswith(viejo))
        self._detectada(self._mutar(linea + "\n", linea + "\n  nota: 3/100 [0.0062, 0.0852]\n"))

    def test_linea_borrada(self) -> None:
        texto = self.RUTA.read_text(encoding="utf-8")
        linea = next(x for x in texto.splitlines() if x.startswith("  S2_ctrl: fallback"))
        self._detectada(self._mutar(linea + "\n", ""))

    def test_cifra_cambiada_por_otra_que_ya_aparece(self) -> None:
        # El hueco del exploratorio del 24-10: un valor que existe en otro lugar del
        # resumen no tiene que pasar; cada posición se compara con la suya.
        texto = self.RUTA.read_text(encoding="utf-8")
        self.assertGreater(texto.count("0.2500"), 1)
        self._detectada(self._mutar("  H1-S3: p = 0.0625; p Holm = 0.2500",
                                    "  H1-S3: p = 0.2500; p Holm = 0.2500"))

    def test_celda_del_csv_cambiada(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            ruta = Path(t) / "control.csv"
            with open(VC.RUTA_CONTROL_CSV, encoding="utf-8", newline="") as f:
                lector = csv.DictReader(f)
                campos, filas = lector.fieldnames, list(lector)
            f0 = next(f for f in filas if f["condicion"] == "S1_din" and f["seed_ep"] == "420000")
            f0["cobertura_accesible"] = repr(float(f0["cobertura_accesible"]) + 0.01)
            with open(ruta, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=campos, lineterminator="\n")
                w.writeheader()
                w.writerows(filas)
            dif, _ = VC.verificar("prueba-control", rutas_csv=[ruta], contrastar=False)
        self._detectada(dif)       # el resumen intacto ya no coincide con el crudo

    def test_columna_parte_b_del_csv_cambiada(self) -> None:
        # H6 no confía en la columna: la recalcula desde la traza.
        with tempfile.TemporaryDirectory() as t:
            ruta = Path(t) / "control.csv"
            with open(VC.RUTA_CONTROL_CSV, encoding="utf-8", newline="") as f:
                lector = csv.DictReader(f)
                campos, filas = lector.fieldnames, list(lector)
            f0 = next(f for f in filas if f["condicion"] == "S3_din" and f["seed_ep"] == "420025")
            self.assertEqual(f0["fallback_ventana_d_min_5"], "1")
            f0["fallback_ventana_d_min_5"] = "0"
            with open(ruta, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=campos, lineterminator="\n")
                w.writeheader()
                w.writerows(filas)
            dif, _ = VC.verificar("prueba-control", rutas_csv=[ruta], contrastar=False)
        self.assertTrue(any("S3_din/420025 fallback_ventana_d_min_5" in x for x in dif), dif)

    def _copia_csv(self, t: str, cambiar) -> Path:
        with open(VC.RUTA_CONTROL_CSV, encoding="utf-8", newline="") as f:
            lector = csv.DictReader(f)
            campos, filas = list(lector.fieldnames), list(lector)
        campos, filas = cambiar(campos, filas)
        ruta = Path(t) / "control.csv"
        with open(ruta, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=campos, lineterminator="\n", extrasaction="ignore")
            w.writeheader()
            w.writerows(filas)
        return ruta

    def test_crlf(self) -> None:
        texto = self.RUTA.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as t:
            ruta = Path(t) / "resumen.txt"
            ruta.write_bytes(texto.replace("\n", "\r\n").encode("utf-8"))
            dif, _ = VC.verificar("prueba-control", ruta_resumen=ruta, contrastar=False)
        self.assertTrue(any("tiene CR" in x for x in dif), dif)

    def test_autochequeo_en_fila_sin_traza(self) -> None:
        def romper(campos, filas):
            for f in filas:
                if f["condicion"] == "S1_ctrl" and f["seed_ep"] == "420000":
                    f["xy_discontinuo"] = "1"
                if f["condicion"] == "S1_din" and f["seed_ep"] == "420001":
                    f["fb_desplazado"] = "1"
            return campos, filas
        with tempfile.TemporaryDirectory() as t:
            dif, _ = VC.verificar("prueba-control", rutas_csv=[self._copia_csv(t, romper)],
                                  contrastar=False)
        self.assertTrue(any("S1_ctrl/420000: xy_discontinuo ≠ 0" in x for x in dif), dif)
        self.assertTrue(any("S1_din/420001: fb_desplazado ≠ 0" in x for x in dif), dif)

    def test_columnas_de_la_parte_b_faltantes(self) -> None:
        def quitar(campos, filas):
            return [c for c in campos if c != "d_min_fuera_ventana_3"], filas
        with tempfile.TemporaryDirectory() as t:
            dif, _ = VC.verificar("prueba-control", rutas_csv=[self._copia_csv(t, quitar)],
                                  contrastar=False)
        self.assertTrue(any("no tiene las columnas de la Parte B" in x for x in dif), dif)

    def test_traza_faltante_no_corta_el_diagnostico(self) -> None:
        def con_fallback(campos, filas):
            for f in filas:
                if f["condicion"] == "S2_din" and f["seed_ep"] == "420000":
                    f["qp_fallbacks"] = "1"
            return campos, filas
        with tempfile.TemporaryDirectory() as t:
            dif, _ = VC.verificar("prueba-control", rutas_csv=[self._copia_csv(t, con_fallback)],
                                  contrastar=False)
        self.assertTrue(any("falta la traza controlR_S2_din_420000.csv" in x for x in dif), dif)
        self.assertTrue(any(x.startswith("RESUMEN línea") for x in dif), dif)

    def test_traza_alterada(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            dir_t = Path(t)
            for p in VC.DIR_TRAZAS.glob("controlR_*.csv"):
                shutil.copy2(p, dir_t / p.name)
            ruta = dir_t / "controlR_S3_din_420025.csv"
            with open(ruta, encoding="utf-8", newline="") as f:
                filas = list(csv.DictReader(f))
            for r in filas:
                if r["paso"] == "439" and r["agente"] == "2":
                    self.assertEqual(r["fallback"], "1")
                    r["fallback"] = "0"
            with open(ruta, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=COLUMNAS_TRAZA, lineterminator="\n")
                w.writeheader()
                w.writerows(filas)
            dif, _ = VC.verificar("prueba-control", dir_trazas=dir_t, contrastar=False)
        self.assertTrue(any(x.startswith("PARTE B: S3_din/420025") for x in dif), dif)


# =============================================================================
# MODO RESULTADO, SOBRE UN EXPERIMENTO SINTÉTICO
# =============================================================================

class PruebaModoResultado(unittest.TestCase):
    """
    Un experimento sintético: las 1200 filas del control relabeladas a las
    semillas 420110–420509 (cada semilla vista 4 veces), con sus trazas, los
    registros reales del control, la pasabilidad y el comparador, y un
    registro_R.txt armado con las funciones de la corrida. El resumen lo
    genera el análisis prerregistrado.
    """

    @classmethod
    def setUpClass(cls) -> None:
        import analizar_experimento_R as A
        import correr_experimento_R as R
        cls.A, cls.R = A, R
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.dir_trazas = base / "trazas"
        cls.dir_fig = base / "figuras"
        for d in (cls.dir_trazas, cls.dir_fig):
            d.mkdir()
        with open(VC.RUTA_CONTROL_CSV, encoding="utf-8", newline="") as f:
            lector = csv.DictReader(f)
            campos, filas_c = lector.fieldnames, list(lector)
        por_clave = {(f["condicion"], int(f["seed_ep"])): f for f in filas_c}
        celdas = [f"{k}_{t}" for k in VC.NIVELES for t in VC.TIPOS]
        filas = []
        for c in celdas:
            for j in range(400):
                src, nueva = 420000 + j % 100, 420110 + j
                f = dict(por_clave[(c, src)], seed_ep=str(nueva), prerregistrado="1")
                filas.append(f)
                if VC.requiere_traza(c.split("_", 1)[1], f):
                    shutil.copy2(VC.DIR_TRAZAS / f"controlR_{c}_{src}.csv",
                                 cls.dir_trazas / f"R_{c}_{nueva}.csv")
        for p in VC.DIR_TRAZAS.glob("controlR_*.csv"):
            shutil.copy2(p, cls.dir_trazas / p.name)
        cls.csv = base / "experimento_R_completo.csv"
        with open(cls.csv, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["prerregistrado"] + list(campos),
                               lineterminator="\n")
            w.writeheader()
            w.writerows(filas)
        cls.filas = filas
        cls.celdas = celdas

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    @classmethod
    def _registros(cls, parte_b: List[str]) -> Path:
        """Un directorio con los tres registros reales y un registro_R.txt sintético."""
        self = cls
        dir_reg = Path(tempfile.mkdtemp(dir=self.tmp.name))
        for nombre in ("comparar_ast_R.txt", "control_bit_a_bit_R.txt", "pasabilidad_R.txt"):
            shutil.copy2(VC.DIR_RES / nombre, dir_reg / nombre)
        ctl = (VC.DIR_RES / "control_bit_a_bit_R.txt").read_text(encoding="utf-8").splitlines()
        i_c = next(i for i, x in enumerate(ctl) if x.startswith("congelados de la campaña al empezar"))
        i_t = ctl.index("AL TERMINAR:")
        i_f = next(i for i, x in enumerate(ctl) if i > i_t and x.startswith("  fin "))
        prereg = next(x for x in ctl if x.startswith("PREREGISTRO_R.md sha256"))
        _auto, resumen_auto = self.R.autochequeos_filas_R(self.filas)
        n_traz = sum(1 for f in self.filas if VC.requiere_traza(f["condicion"].split("_", 1)[1], f))
        reg = ([self.R.ENCABEZADO_R] + ctl[1:i_c + 1]
               + [prereg, "manifiestos pre: manifiesto_R_pre_x.txt (vale el último, "
                          "manifiesto_R_pre_x.txt: todas sus entradas con el sha256 actual)",
                  "semillas 420110–420509 (n = 400), las mismas en las 12 celdas; orden S1, "
                  "S2, S3 y din, quieto, ctrl, sinvel", "modo: con la Parte B"]
               + [f"{c}: cob_acc=0.50000000 interv=0.500000 t/ep=5.00 s; criterios (se miden, "
                  f"no detienen) — x 0" for c in self.celdas]
               + ["FILAS: 4800 (4800 distintas; esperadas 4800)"] + resumen_auto
               + [f"TRAZAS: {n_traz} episodios con traza; biyección y tamaño → 0 problemas"]
               + parte_b + ctl[i_t:i_f]
               + ["  manifiesto pre: todas sus entradas con el sha256 actual", ctl[i_f],
                  "logs de los tramos: corrida_R_experimento_x.log",
                  f"HUELLA_Q {VC.HUELLA_Q}", f"HUELLA_R {VC.HUELLA_R}", prereg])
        (dir_reg / "registro_R.txt").write_bytes(("\n".join(reg) + "\n").encode("utf-8"))
        return dir_reg

    @classmethod
    def _resumen(cls, dir_reg: Path) -> Path:
        """El resumen que escribe el análisis prerregistrado con esos registros."""
        self = cls
        A = self.A
        datos, cols = A.cargar([self.csv])
        vistos, _ = A.cargar([A.RUTA_CONTROL_CSV])
        motivo = A.estado_parte_b([dir_reg / "control_bit_a_bit_R.txt",
                                   dir_reg / "registro_R.txt"])
        L, _V = A.resumen(datos, cols, "resultado", "R", vistos, self.dir_trazas, motivo)
        i = L.index("VERIFICACIÓN (de los registros de la corrida)")
        j = L.index("", i)
        L[i:j] = A.seccion_verificacion("resultado", dir_reg)
        hechas = A.figuras(datos, "resultado", "R",
                           motivo is None and all(c in cols for c in A.COLUMNAS_PARTE_B), "",
                           self.dir_trazas, self.dir_fig)
        ruta = dir_reg / "resumen_R.txt"
        ruta.write_bytes(("\n".join(L + ["", "FIGURAS: " + ", ".join(hechas)]) + "\n")
                         .encode("utf-8"))
        return ruta

    def _verificar(self, dir_reg: Path, ruta: Path, **kw) -> List[str]:
        args = dict(ruta_resumen=ruta, rutas_csv=[self.csv], dir_trazas=self.dir_trazas,
                    dir_registros=dir_reg, dir_fig=self.dir_fig, contrastar=False)
        args.update(kw)
        dif, _ = VC.verificar("resultado", **args)
        return dif

    def _ok(self):
        if not hasattr(type(self), "reg_ok"):
            type(self).reg_ok = self._registros(["PARTE B: OK"])
            type(self).res_ok = self._resumen(type(self).reg_ok)
        return type(self).reg_ok, type(self).res_ok

    def _copia_resumen(self, viejo: str, nuevo: str, n: int = 1) -> Path:
        _reg, ruta = self._ok()
        texto = ruta.read_text(encoding="utf-8")
        self.assertIn(viejo, texto)
        copia = Path(tempfile.mkdtemp(dir=self.tmp.name)) / "resumen_R.txt"
        copia.write_bytes(texto.replace(viejo, nuevo, n).encode("utf-8"))
        return copia

    def _copia_csv(self, cambiar) -> Path:
        with open(self.csv, encoding="utf-8", newline="") as f:
            lector = csv.DictReader(f)
            campos, filas = list(lector.fieldnames), list(lector)
        campos, filas = cambiar(campos, filas)
        ruta = Path(tempfile.mkdtemp(dir=self.tmp.name)) / "experimento_R_completo.csv"
        with open(ruta, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=campos, lineterminator="\n")
            w.writeheader()
            w.writerows(filas)
        return ruta

    def test_mutaciones_de_los_datos(self) -> None:
        reg, res = self._ok()

        def sin_prerregistrado(campos, filas):
            filas[7]["prerregistrado"] = "0"
            return campos, filas

        def repetida(campos, filas):
            return campos, filas + [dict(filas[3])]

        self.assertTrue(any("sin prerregistrado" in x for x in self._verificar(
            reg, res, rutas_csv=[self._copia_csv(sin_prerregistrado)])))
        self.assertTrue(any("fila repetida" in x for x in self._verificar(
            reg, res, rutas_csv=[self._copia_csv(repetida)])))
        self.assertTrue(any("las semillas no son" in x for x in self._verificar(
            reg, res, semillas_resultado=range(420111, 420511))))
        # Una traza de más y una figura de menos.
        dir_t = Path(tempfile.mkdtemp(dir=self.tmp.name))
        for p in self.dir_trazas.glob("*.csv"):
            shutil.copy2(p, dir_t / p.name)
        shutil.copy2(dir_t / "controlR_S3_din_420025.csv", dir_t / "R_S1_din_420110.csv")
        self.assertTrue(any("traza que no corresponde R_S1_din_420110.csv" in x
                            for x in self._verificar(reg, res, dir_trazas=dir_t)))
        dir_f = Path(tempfile.mkdtemp(dir=self.tmp.name))
        for p in self.dir_fig.glob("*.png"):
            shutil.copy2(p, dir_f / p.name)
        (dir_f / "fig_R_costo.png").unlink()
        self.assertTrue(any("FIGURAS: falta fig_R_costo.png" in x
                            for x in self._verificar(reg, res, dir_fig=dir_f)))

    def test_mutaciones_de_verificacion(self) -> None:
        reg, _res = self._ok()
        # Orden: dos líneas consecutivas del mismo registro, intercambiadas.
        a = "  pasabilidad_R.txt: sin reinicio pendiente de Windows\n"
        b = ("  pasabilidad_R.txt: congelados de la campaña al empezar (PROTOCOLO_L0_L2.md:210): "
             "IGUAL a lo probado\n")
        copia = self._copia_resumen(a + b, b + a)
        self.assertTrue(any("fuera de orden" in x for x in self._verificar(reg, copia)))
        # Multiplicidad: la energía al terminar (la línea se repite en el registro).
        e = "  control_bit_a_bit_R.txt: energía: enchufada, batería 100 %\n"
        _reg, ruta = self._ok()
        texto = ruta.read_text(encoding="utf-8")
        self.assertEqual(texto.count(e), 2)
        i = texto.index(e, texto.index(e) + 1)
        copia = Path(tempfile.mkdtemp(dir=self.tmp.name)) / "resumen_R.txt"
        copia.write_bytes((texto[:i] + texto[i + len(e):]).encode("utf-8"))
        self.assertTrue(any("falta en el resumen «control_bit_a_bit_R.txt: energía" in x
                            for x in self._verificar(reg, copia)))
        # La constancia de las 1100 primeras reproducciones (§5.3).
        de1200 = next(x for x in texto.splitlines()
                      if x.startswith("  control_bit_a_bit_R.txt: de los 1200"))
        copia = self._copia_resumen(de1200 + "\n", "")
        self.assertTrue(any("falta en el resumen «control_bit_a_bit_R.txt: de los 1200" in x
                            for x in self._verificar(reg, copia)))

    def test_registros_alterados(self) -> None:
        _reg, res = self._ok()
        # Un control que no dice «CONTROL: OK» y una pasabilidad vacía.
        dir_reg = self._registros(["PARTE B: OK"])
        ctl = dir_reg / "control_bit_a_bit_R.txt"
        ctl.write_bytes(ctl.read_text(encoding="utf-8").replace(
            "CONTROL: OK", "CONTROL: NO REPRODUCE").encode("utf-8"))
        dif = self._verificar(dir_reg, res)
        self.assertTrue(any("no tiene «CONTROL: OK»" in x for x in dif))
        dir_reg = self._registros(["PARTE B: OK"])
        (dir_reg / "pasabilidad_R.txt").write_bytes(b"")
        self.assertTrue(any("pasabilidad_R.txt está vacío" in x
                            for x in self._verificar(dir_reg, res)))

    def test_parte_b_ok(self) -> None:
        dir_reg, ruta = self._ok()
        self.assertEqual(self._verificar(dir_reg, ruta), [])
        ruta = self._copia_resumen("FIGURAS:", "FIGURAS:")  # una copia, sin cambios
        self.assertEqual(self._verificar(dir_reg, ruta), [])
        texto = ruta.read_text(encoding="utf-8")
        # Mutación en VERIFICACIÓN: falta una verificación al terminar.
        quitada = "  pasabilidad_R.txt: AL TERMINAR:\n"
        self.assertIn(quitada, texto)
        ruta.write_bytes(texto.replace(quitada, "", 1).encode("utf-8"))
        self.assertTrue(any("falta en el resumen «pasabilidad_R.txt: AL TERMINAR:»" in x
                            for x in self._verificar(dir_reg, ruta)))
        # Mutación en VERIFICACIÓN: se cuela una línea de resultados por celda.
        ancla = "  registro_R.txt: modo: con la Parte B\n"
        self.assertIn(ancla, texto)
        colada = ("  registro_R.txt: S1_din: cob_acc=0.50000000 interv=0.500000 t/ep=5.00 s; "
                  "criterios (se miden, no detienen) — x 0\n")
        ruta.write_bytes(texto.replace(ancla, ancla + colada, 1).encode("utf-8"))
        self.assertTrue(any("se coló una línea de resultados" in x
                            for x in self._verificar(dir_reg, ruta)))

    def test_parte_b_no(self) -> None:
        dir_reg = self._registros(
            ["PARTE B: NO (H6 y la ubicación de los contactos de H5a quedan 'no evaluable')",
             "  autochequeo que falló — S3_din/420135: ejemplo"])
        ruta = self._resumen(dir_reg)
        texto = ruta.read_text(encoding="utf-8")
        self.assertIn("    no evaluable: registro_R.txt dice PARTE B: NO (§7 del prerregistro)",
                      texto)
        self.assertEqual(self._verificar(dir_reg, ruta), [])


if __name__ == "__main__":
    unittest.main()
