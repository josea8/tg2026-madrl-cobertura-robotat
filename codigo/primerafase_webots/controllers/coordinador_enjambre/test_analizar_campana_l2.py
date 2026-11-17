"""
test_analizar_campana_l2.py
===========================
Pruebas del análisis FIJADO de la campaña L2 (`analizar_campana_l2.py`,
`tesis/PLAN_ANALISIS_campana_L2.md`) y de su verificador independiente
(`verificar_campana_l2.py`), con una campaña SINTÉTICA de brecha conocida
armada en un temporal (libro + CSV de tomas + CSV de réplica con el
contrato del §9):

  · recupera la brecha, el costo y las sensibilidades sembradas;
  · el criterio "fuera del soporte" es el del 30-09 (comparado con `ast`);
  · el descriptivo del 30-09 reproduce las cifras del reporte;
  · réplicas inválidas, pasada suplementaria, cierre (b) (≤ 2 excluye,
    > 2 detiene, umbral de 1 mm aplicado por el script, vacío = contrato),
    completitud (reps 1–3), clave repetida, contrato incompleto, intento
    ajeno, condición fuera del plan, rampa distinta, corrida antes del
    cierre;
  · requisitos del §8 (cerrada, hw, sha256 del plan, del script y del
    libro) con --desvio; --ensayo nunca sobre una campaña de hardware;
  · integridad: libro ↔ CSV (inclusión, validez, frenos, distancia),
    régimen de cada toma, filas después del cierre, reservas colgadas;
  · seguridad sobre TODAS las corridas, también las marcadas interrumpidas;
  · la salida nunca pisa una previa; el verificador da N/N y detecta una
    cifra alterada.

    python -m unittest test_analizar_campana_l2 -v

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
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

import numpy as np
from scipy import stats

import analizar_campana_l2 as A
import campana_obstaculo as CO
import verificar_campana_l2 as V

_CARPETA = Path(__file__).resolve().parent
_PAREO_3009 = _CARPETA.parents[2] / "REPORTE_2026-09-30_datos" / "scripts" / "pareo_final_0930.py"
ROBOTS = tuple(int(r) for r in A.ROBOTS_AGENTES)     # el enjambre del plan


def _silencio():
    return contextlib.redirect_stdout(io.StringIO())


def fila_toma(k: int, nombre: str, cobertura: float, **kw) -> Dict[str, Any]:
    """Una fila de tomas con las columnas que lee el análisis."""
    f: Dict[str, Any] = {
        "toma": k, "intento_campana": k, "campana": nombre, "semilla": CO.SEMILLA_BASE + k - 1,
        "id_sesion": "s1", "valido": 1, "motivo": "", "decisiones": 500,
        "lazo": "evaluacion", "factor": 0.4, "formulacion": "F2",
        "tau_prediccion_s": 0.65, "colocacion": "auto", "obst_robot": 4,
        "obst_modo": "movil", "obst_recorrido_m": 2.4,
        "obst_recorrido_comandado_m": 2.5, "cobertura_aoi": cobertura,
        "d_min_obst_medida": 0.33, "frenos": 0, "decisiones_freno": 0,
        "decisiones_previas": 500 * (k - 1), "retrocesos_detalle": "",
        "col_obst_origen": "proyeccion", "d_pared_min": 0.20, "viola_018": 0,
        "colisiones_015": 0, "colisiones_022": 0, "frac_cbf": 0.1, "n_escape": 0,
        "valido_demo": 1,
    }
    for i in range(5):
        f.update({f"robot_a{i}": ROBOTS[i], f"col_estado_a{i}": "listo",
                  f"x0_a{i}": 0.5 + 0.5 * i, f"y0_a{i}": 0.5,
                  f"blanco_x_a{i}": 0.5 + 0.5 * i, f"blanco_y_a{i}": 0.5})
    f.update(kw)
    f["incluida"], f["motivo_inclusion"] = CO.inclusion_campana(f)
    return f


def fila_replica(k: int, nombre: str, condicion: str, tau: float, rep: int,
                 cobertura: float, **kw) -> Dict[str, Any]:
    con = condicion == "con_obstaculo"
    f = {"campana": nombre, "fuente_tomas": "x_L2_tomas.csv", "id_sesion": "s1",
         "intento_campana": k, "semilla": CO.SEMILLA_BASE + k - 1, "condicion": condicion,
         "tau_s": tau, "rep": rep, "pasada": "normal",
         "inicio": "2099-01-01T00:00:00", "sha256_pila": "pila_a",
         "decisiones_previas": 500 * (k - 1), "valido": 1, "motivo": "",
         "decisiones": 500, "cobertura_aoi": cobertura,
         "d_min_obst_medida": 0.35 if con else "", "d_pared_min": 0.21,
         "viola_018": 0, "colisiones_015": 0, "colisiones_022": 0, "frac_cbf": 0.12,
         "n_escape": 0, "frenos_sombra": 0 if con else "",
         "cierre_b_ok": 1 if con else "", "cierre_b_err_max_m": 0.0002 if con else "",
         "cierre_b_desfase": 0 if con else "",
         "cierre_b_err_th_rad": 2e-16 if con else "",
         "cierre_b_mandos_iguales": 1 if con else ""}
    f.update(kw)
    return f


def escribir(ruta: Path, filas: List[Dict[str, Any]]) -> None:
    cols: List[str] = []
    for f in filas:
        cols += [c for c in f if c not in cols]
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(filas)


class BaseSintetica(unittest.TestCase):
    """Campaña 'sint' de hardware con N tomas; brecha sembrada 0.010 ± ruido,
    costo −0.020, las tomas 1–2 con freno, la 1 con rampa."""

    N = 12
    BRECHA = 0.010
    COSTO = -0.020
    TOMAS_CSV = "20261010_100000_L2_tomas.csv"

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="analisis_test_"))
        self._p = mock.patch.object(CO, "ARCHIVOS_CONGELADOS",
                                    (A.CLAVE_SCRIPT, A.CLAVE_PLAN, A.CLAVE_LIBRO,
                                     "verificar_campana_l2.py"))
        self._p.start()
        self.dir_rep = self.tmp / "replica_campana" / "sint"
        self.dir_rep.mkdir(parents=True)
        rng = np.random.default_rng(7)
        self.ruido = rng.normal(0, 0.004, self.N)
        self.campana = CO.Campana.crear(self.tmp, "sint", "hw", 4, 4)
        self.tomas: List[Dict[str, Any]] = []
        self.replica: List[Dict[str, Any]] = []
        for k in range(1, self.N + 1):
            hw = 0.34 + 0.002 * k
            extra = {}
            if k <= 2:
                extra["frenos"] = 1
                extra["decisiones_freno"] = 12
            self.tomas.append(fila_toma(k, "sint", hw, **extra))
            rep_con = hw - self.BRECHA - self.ruido[k - 1]
            for r in (1, 2, 3):
                self.replica.append(fila_replica(k, "sint", "con_obstaculo", 0.0, r,
                                                 rep_con + (r - 2) * 0.001))
                self.replica.append(fila_replica(k, "sint", "sin_obstaculo", 0.0, r,
                                                 rep_con - self.COSTO + (r - 2) * 0.001))
                self.replica.append(fila_replica(k, "sint", "con_obstaculo", 0.45, r,
                                                 rep_con - 0.005))

    def tearDown(self) -> None:
        self._p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def volcar(self, cerrar: bool = True, extra_libro: Optional[List[Dict]] = None) -> None:
        """Escribe el libro (reserva + resultado por toma, como una sesión con
        su candado), el CSV de tomas y el de la réplica."""
        c = self.campana
        c.id_sesion = "s1"
        c.ruta_candado.write_text("s1 pid 0 desde prueba\n", encoding="utf-8")
        c._agregar({"tipo": "apertura", "id_sesion": "s1", "motivo": "x",
                    "detalle": "{}"})
        for t in self.tomas:
            k = t["toma"]
            c._agregar({"tipo": "reserva", "id_sesion": "s1",
                        "intento": k, "semilla": t["semilla"]})
            if t.get("_interrumpida"):
                c._agregar({"tipo": "resultado", "id_sesion": "s1", "intento": k,
                            "semilla": t["semilla"], "estado": "interrumpida",
                            "incluida": 0})
                continue
            c.registrar(k, t["semilla"], t, self.TOMAS_CSV)
        c.ruta_candado.unlink()
        for f in extra_libro or []:
            c._agregar(f)
        if cerrar:
            CO.Campana.cerrar(self.tmp, "sint", "fin")
        escribir(self.tmp / self.TOMAS_CSV,
                 [{c_: v for c_, v in t.items() if not c_.startswith("_")}
                  for t in self.tomas if not t.get("_interrumpida") or t.get("_corrio")])
        escribir(self.dir_rep / "20261011_replica_tomas.csv", self.replica)

    def reescribir_replica(self) -> None:
        escribir(self.dir_rep / "20261011_replica_tomas.csv", self.replica)

    def analizar(self, **kw) -> Dict[str, Any]:
        c = CO.Campana(CO.Campana.carpeta_de(self.tmp, "sint"))
        return A.analizar(c, self.tmp, self.dir_rep, **kw)

    def codigo(self, **kw) -> int:
        try:
            self.analizar(**kw)
        except A.ErrorAnalisis as e:
            return e.codigo
        return 0


class PruebaRecuperaLoSembrado(BaseSintetica):

    def test_brecha_costo_y_sensibilidades(self) -> None:
        self.volcar()
        r = self.analizar()
        p = r["principal"]
        d = np.array([t["cobertura_aoi"] for t in self.tomas]) - np.array(
            [t["cobertura_aoi"] - self.BRECHA - e for t, e in zip(self.tomas, self.ruido)])
        self.assertEqual(p["n"], self.N)
        self.assertAlmostEqual(p["media"], float(d.mean()), places=12)
        w = stats.t.ppf(0.975, self.N - 1) * d.std(ddof=1) / math.sqrt(self.N)
        self.assertAlmostEqual(p["ic95"][0], d.mean() - w, places=12)
        self.assertEqual(r["rotulo"], "RESULTADO")
        self.assertIn("Brecha detectable", p["conclusion"])
        self.assertAlmostEqual(r["costo"]["media"], self.COSTO, places=10)
        s = r["sensibilidades"]
        self.assertEqual(s["C_sin_freno"]["n"], self.N - 2)
        self.assertEqual(s["D_sin_rampa"]["n"], self.N - 1)
        self.assertEqual(s["A_sin_fuera_de_soporte"]["n"], self.N)
        self.assertEqual(s["B_sin_retroceso"]["n"], self.N)
        self.assertAlmostEqual(s["E_replica_tau_045"]["media"], float(d.mean()) + 0.005,
                               places=10)
        self.assertEqual(r["declaraciones"]["tomas_con_rampa"], [1])
        self.assertEqual(r["declaraciones"]["replica_sha256_pila"], ["pila_a"])
        self.assertIn("sha256_libro", r["fuentes"])
        self.assertEqual(len(r["fuentes"]["sha256_csv_3009"]), 10)
        # El bootstrap es determinista (semilla fija).
        self.assertEqual(p["bootstrap_ic95"], self.analizar()["principal"]["bootstrap_ic95"])

    def test_conclusion_sin_brecha_da_la_cota_y_no_afirma_equivalencia(self) -> None:
        txt = A.conclusion({"n": 30, "media": 0.002, "ic95": [-0.010, 0.014]})
        self.assertIn("No hay brecha detectable", txt)
        self.assertIn("con 95 % de confianza, a |brecha| ≤ 0.0140", txt)
        self.assertIn("No se afirma equivalencia", txt)

    def test_seguridad_sobre_todas_las_corridas(self) -> None:
        # La 12 no es válida: no entra al principal pero sí a la seguridad,
        # y su contacto se lista aparte. No tiene réplica (no es incluida).
        self.tomas[-1] = fila_toma(self.N, "sint", 0.30, valido=0, motivo="antigüedad",
                                   d_min_obst_medida=0.12)
        self.replica = [f for f in self.replica if f["intento_campana"] != self.N]
        self.volcar()
        r = self.analizar()
        self.assertEqual(r["principal"]["n"], self.N - 1)
        g = r["seguridad"]
        self.assertEqual(g["corridas"], self.N)
        self.assertEqual(g["contacto_hw"]["k"], 1)
        self.assertEqual(g["contactos_no_incluidas"], [self.N])
        ic = stats.binomtest(1, self.N).proportion_ci(method="exact")
        self.assertAlmostEqual(g["contacto_hw"]["ic95"][1], ic.high)
        self.assertEqual(g["tomas_con_freno_hw"]["k"], 2)
        self.assertEqual(g["frenos_eventos_hw"], 2)
        self.assertAlmostEqual(g["d_min_hw_menos_replica_media"]["media"], 0.33 - 0.35)
        self.assertAlmostEqual(g["d_pared_hw_menos_replica_minimo"]["media"], 0.20 - 0.21)
        self.assertEqual(r["conteos"]["no_incluidas_por_motivo"], {"no válida": 1})

    def test_salidas_sin_pisar_y_verificador(self) -> None:
        self.volcar()
        r = self.analizar()
        c1 = A.escribir_salidas(r, self.tmp / "analisis")
        c2 = A.escribir_salidas(r, self.tmp / "analisis")
        self.assertNotEqual(c1, c2)
        for a in ("analisis.json", "salida.txt", "pares.csv", "seguridad_tomas.csv",
                  "no_incluidas.csv"):
            self.assertTrue((c1 / a).is_file())
        js = json.loads((c1 / "analisis.json").read_text(encoding="utf-8"))
        self.assertNotIn("_pares", js)
        self.assertEqual(js["principal"]["n"], self.N)
        # El verificador independiente: todo coincide…
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self.assertEqual(V.main([str(c1), "--base", str(self.tmp)]), 0)
        self.assertNotIn("✗", salida.getvalue())
        # …y una cifra alterada se detecta.
        js["principal"]["media"] += 1e-6
        (c1 / "analisis.json").write_text(json.dumps(js), encoding="utf-8")
        with _silencio():
            self.assertEqual(V.main([str(c1), "--base", str(self.tmp)]), 1)


class PruebaReplica(BaseSintetica):

    def _de(self, k: int, cond: str = "con_obstaculo", tau: float = 0.0):
        return [f for f in self.replica if f["intento_campana"] == k
                and f["condicion"] == cond and f["tau_s"] == tau]

    def test_invalidas_y_pasada_suplementaria(self) -> None:
        self._de(3)[2].update(valido=0, cobertura_aoi=0.0)     # 2 válidas
        for f in self._de(4):                                   # 0 válidas
            f["valido"] = 0
        for rep in (4, 5, 6):
            self.replica.append(fila_replica(4, "sint", "con_obstaculo", 0.0, rep, 0.5,
                                             pasada="suplementaria"))
        self.volcar()
        r = self.analizar()
        pares = {p["intento"]: p for p in r["_pares"]}
        self.assertEqual(pares[3]["rep_con"]["n_validas"], 2)
        self.assertEqual(pares[4]["rep_con"]["pasada"], "suplementaria")
        self.assertAlmostEqual(pares[4]["rep_con"]["cobertura"], 0.5)
        self.assertIn("intento 4 rep_con", r["declaraciones"]["pasadas_suplementarias"])

    def test_suplementaria_con_validas_no_cuenta(self) -> None:
        self.replica.append(fila_replica(5, "sint", "con_obstaculo", 0.0, 4, 0.9,
                                         pasada="suplementaria"))
        self.volcar()
        p = {p["intento"]: p for p in self.analizar()["_pares"]}[5]
        self.assertEqual(p["rep_con"]["n_validas"], 3)
        self.assertNotAlmostEqual(p["rep_con"]["cobertura"], 0.9)
        self.assertTrue(p["rep_con"]["advertencia"])

    def test_cierre_b_hasta_dos_excluye_mas_detiene(self) -> None:
        self._de(2)[0]["cierre_b_ok"] = 0
        self._de(5, tau=0.45)[1]["cierre_b_err_max_m"] = 0.005  # bandera 1, error 5 mm
        self.volcar()
        r = self.analizar()
        self.assertEqual(sorted(r["declaraciones"]["cierre_b_excluidas"]), [2, 5])
        self.assertEqual(r["principal"]["n"], self.N - 2)
        self.assertEqual(r["costo"]["n"], self.N - 2)
        self._de(7)[0]["cierre_b_desfase"] = 1
        self.reescribir_replica()
        with self.assertRaises(A.ErrorAnalisis) as e:
            self.analizar()
        self.assertEqual(e.exception.codigo, A.SALIDA_REPLICA)
        self.assertIn("se corrige, no se excluye", str(e.exception))

    def test_cierre_b_exige_rumbo_y_mandos(self) -> None:
        """Decisión de José (10-10): rumbo > 1e-6 rad o mandos distintos de
        los grabados también son falla del cierre (b), aunque la bandera
        diga 1; el motivo lo nombra, y el verificador coincide."""
        self._de(3)[0]["cierre_b_err_th_rad"] = 2e-6
        self._de(8, tau=0.45)[2]["cierre_b_mandos_iguales"] = 0
        self.volcar()
        r = self.analizar()
        excl = r["declaraciones"]["cierre_b_excluidas"]
        self.assertEqual(sorted(excl), [3, 8])
        self.assertIn("rumbo 2e-06", excl[3])
        self.assertIn("mandos iguales 0", excl[8])
        carpeta = A.escribir_salidas(r, self.tmp / "analisis")
        with _silencio():
            self.assertEqual(V.main([str(carpeta), "--base", str(self.tmp)]), 0)

    def test_corrida_sin_decisiones_no_es_falla_de_b(self) -> None:
        """Una corrida con obstáculo que no arrancó (0 decisiones) no tiene
        cierre (b): es una repetición inválida y no excluye la toma."""
        self._de(4)[1].update(valido=0, decisiones=0, cierre_b_ok="",
                              cierre_b_err_max_m="", cierre_b_desfase="",
                              cierre_b_err_th_rad="", cierre_b_mandos_iguales="")
        self.volcar()
        r = self.analizar()
        self.assertEqual(r["declaraciones"]["cierre_b_excluidas"], {})
        self.assertEqual({p["intento"]: p for p in r["_pares"]}[4]["rep_con"]["n_validas"], 2)

    def test_verificador_con_el_paquete_movido(self) -> None:
        self.volcar()
        carpeta = A.escribir_salidas(self.analizar(), self.tmp / "analisis")
        otro = Path(tempfile.mkdtemp(prefix="paquete_movido_"))
        try:
            nuevo = otro / "paquete"
            shutil.copytree(self.tmp, nuevo)
            shutil.rmtree(self.tmp)                     # el original ya no está
            with _silencio():
                self.assertEqual(V.main([str(nuevo / "analisis" / carpeta.name),
                                         "--base", str(nuevo)]), 0)
        finally:
            shutil.copytree(otro / "paquete", self.tmp)
            shutil.rmtree(otro, ignore_errors=True)

    def test_cierre_b_sin_evaluar_viola_el_contrato(self) -> None:
        self._de(3)[1].update(valido=0, cierre_b_ok="")         # corrida abortada
        self.volcar()
        with self.assertRaises(A.ErrorAnalisis) as e:
            self.analizar()
        self.assertEqual(e.exception.codigo, A.SALIDA_REPLICA)
        self.assertIn("sin evaluar", str(e.exception))

    def test_completitud_de_las_repeticiones(self) -> None:
        self.replica.remove(self._de(6, "sin_obstaculo")[2])    # falta la rep 3
        self.volcar()
        self.assertEqual(self.codigo(), A.SALIDA_REPLICA)
        self.replica.append(fila_replica(6, "sint", "sin_obstaculo", 0.0, 3, 0.3))
        self.replica.append(fila_replica(6, "sint", "sin_obstaculo", 0.0, 4, 0.3))
        self.reescribir_replica()                                # rep 4 "normal"
        self.assertEqual(self.codigo(), A.SALIDA_REPLICA)

    def test_clave_repetida_contrato_y_filas_ajenas(self) -> None:
        self.replica.append(dict(self.replica[0]))
        self.volcar()
        with self.assertRaises(A.ErrorAnalisis) as e:
            self.analizar()
        self.assertIn("clave repetida", str(e.exception))
        self.replica.pop()
        for caso in ({"intento_campana": 99}, {"condicion": "sin_obstaculo", "tau_s": 0.45},
                     {"rep": "x"}, {"decisiones_previas": 7},
                     {"inicio": "2026-01-01T00:00:00"}):
            fila = dict(self.replica[0], **caso)
            self.replica.append(fila)
            if "rep" not in caso:
                self.replica.remove(self.replica[0])
            self.reescribir_replica()
            self.assertEqual(self.codigo(), A.SALIDA_REPLICA, caso)
            self.replica.remove(fila)
            if "rep" not in caso:
                self.replica.insert(0, fila_replica(1, "sint", "con_obstaculo", 0.0, 1,
                                                    self.tomas[0]["cobertura_aoi"] - 0.01))
        for f in self.replica:
            f.pop("sha256_pila")
        self.reescribir_replica()
        with self.assertRaises(A.ErrorAnalisis) as e:
            self.analizar()
        self.assertIn("sha256_pila", str(e.exception))

    def test_replica_incompleta_o_de_dos_pilas_se_detiene(self) -> None:
        """Falta una condición; o un grupo con 0 válidas sin su suplementaria;
        o corridas de dos pilas, o la FALSA: código 3 (con --desvio, pasa)."""
        base = [dict(f) for f in self.replica]
        casos = {
            "condicion": [f for f in base if not (f["intento_campana"] == 3
                                                  and f["condicion"] == "sin_obstaculo")],
            "suplementaria": [dict(f, valido=0) if (f["intento_campana"] == 5
                                                    and f["tau_s"] == 0.45) else f
                              for f in base],
            "dos_pilas": [dict(f, sha256_pila="pila_b") if f["rep"] == 3 else f for f in base],
            "falsa": [dict(f, sha256_pila="FALSA") for f in base],
        }
        self.volcar()
        for nombre, filas in casos.items():
            self.replica = filas
            self.reescribir_replica()
            self.assertEqual(self.codigo(), A.SALIDA_REPLICA, nombre)
        self.assertEqual(self.analizar(desvio="prueba")["conteos"]["incluidas"], self.N)

    def test_sin_replica_no_hay_principal(self) -> None:
        self.replica = []
        self.volcar()
        (self.dir_rep / "20261011_replica_tomas.csv").unlink()
        self.assertEqual(self.codigo(), A.SALIDA_REPLICA)


class PruebaRequisitosEIntegridad(BaseSintetica):

    def test_meta_minimo_y_tope_tienen_que_ser_los_del_plan(self) -> None:
        shutil.rmtree(self.tmp / "campanas")
        self.campana = CO.Campana.crear(self.tmp, "sint", "hw", 4, 4, meta=12, minimo=6)
        self.volcar()
        self.assertEqual(self.codigo(), A.SALIDA_NEGADO)
        r = self.analizar(desvio="campaña corta de prueba")
        self.assertTrue(any("meta/mínimo/tope" in p for p in r["requisitos"]["problemas"]))

    def test_desvio_con_replica_incompleta_la_declara(self) -> None:
        self.replica = [f for f in self.replica if not (
            f["intento_campana"] == 5 and f["condicion"] == "sin_obstaculo" and f["rep"] == 3)]
        self.volcar()
        self.assertEqual(self.codigo(), A.SALIDA_REPLICA)
        r = self.analizar(desvio="réplica cortada")
        self.assertTrue(r["declaraciones"]["replica_incompleta"])

    def test_abierta_se_niega_salvo_desvio(self) -> None:
        self.volcar(cerrar=False)
        self.assertEqual(self.codigo(), A.SALIDA_NEGADO)
        r = self.analizar(desvio="análisis intermedio pedido por José")
        self.assertIn("José", r["requisitos"]["desvio"])

    def test_ensayo_nunca_sobre_hardware(self) -> None:
        self.volcar()
        self.assertEqual(self.codigo(ensayo=True), A.SALIDA_NEGADO)

    def test_hash_distinto_se_niega(self) -> None:
        self.volcar()
        with mock.patch.object(A, "RUTA_PLAN", self.tmp / "otro_plan.md"):
            with self.assertRaises(A.ErrorAnalisis) as e:
                self.analizar()
        self.assertIn("sha256", str(e.exception))
        with mock.patch.object(A, "CLAVE_LIBRO", "otro_libro.py"):
            self.assertEqual(self.codigo(), A.SALIDA_NEGADO)

    def test_inclusion_validez_y_distancia_del_libro_contra_el_csv(self) -> None:
        self.volcar()
        ruta = self.tmp / self.TOMAS_CSV
        original = A.leer_csv(ruta)
        for campo, valor in (("obst_recorrido_m", "0.5"), ("d_min_obst_medida", "0.9")):
            filas = [dict(f) for f in original]
            filas[0][campo] = valor
            escribir(ruta, filas)
            self.assertEqual(self.codigo(), A.SALIDA_INTEGRIDAD, campo)

    def test_regimen_de_cada_toma(self) -> None:
        for cambio in ({"factor": 0.5}, {"robot_a2": 3}, {"colocacion": "manual"},
                       {"tau_prediccion_s": 0.45}, {"obst_robot": 7}):
            self.tomas[3] = fila_toma(4, "sint", 0.35, **cambio)
            shutil.rmtree(self.tmp / "campanas")
            self.campana = CO.Campana.crear(self.tmp, "sint", "hw", 4, 4)
            self.volcar()
            self.assertEqual(self.codigo(), A.SALIDA_INTEGRIDAD, cambio)

    def test_reserva_colgada_y_filas_despues_del_cierre(self) -> None:
        # Una reserva sin resultado y el cierre escritos "a la vieja" (sin
        # que cerrar() la marque): el análisis la marca y la declara.
        self.volcar(cerrar=False, extra_libro=[
            {"tipo": "reserva", "id_sesion": "s2", "intento": self.N + 1,
             "semilla": CO.SEMILLA_BASE + self.N},
            {"tipo": "cierre_campana", "motivo": "fin"}])
        r = self.analizar()
        self.assertEqual(r["declaraciones"]["reservas_marcadas_por_el_analisis"], [self.N + 1])
        self.assertEqual(r["conteos"]["no_incluidas_por_motivo"], {"interrumpida": 1})
        self.campana._agregar({"tipo": "reserva", "id_sesion": "s3",
                               "intento": self.N + 2, "semilla": CO.SEMILLA_BASE + self.N + 1})
        self.assertEqual(self.codigo(), A.SALIDA_INTEGRIDAD)

    def test_corrida_marcada_interrumpida_entra_a_la_seguridad(self) -> None:
        self.tomas[-1]["_interrumpida"] = True
        self.tomas[-1]["_corrio"] = True
        self.tomas[-1]["intento_campana"] = ""
        self.tomas[-1]["d_min_obst_medida"] = 0.11
        self.replica = [f for f in self.replica if f["intento_campana"] != self.N]
        self.volcar()
        r = self.analizar()
        self.assertEqual(r["conteos"]["incluidas"], self.N - 1)
        self.assertEqual(r["declaraciones"]["corridas_marcadas_interrumpidas"],
                         [{"intento": self.N, "archivo": self.TOMAS_CSV}])
        g = r["seguridad"]
        self.assertEqual(g["corridas"], self.N)
        self.assertEqual(g["corridas_marcadas_interrumpidas"], 1)
        self.assertEqual(g["contacto_hw"]["k"], 1)


class PruebaCriterioDeCierre(BaseSintetica):
    """El criterio de José (09-10) recalculado del crudo y contra el libro."""

    def test_cierre_por_criterio_se_reporta_y_verifica(self) -> None:
        self.tomas[-2] = fila_toma(self.N - 1, "sint", 0.36, d_min_obst_medida=0.12)
        self.tomas[-1] = fila_toma(self.N, "sint", 0.36, colisiones_015=1)
        self.volcar(cerrar=False)                      # el libro ya cerró solo
        r = self.analizar()
        cr = r["criterio_de_cierre"]
        self.assertEqual(cr["n_tomas_con_contacto"], 2)
        self.assertTrue(cr["cerro_por_criterio"])
        self.assertEqual([c["intento"] for c in cr["tomas_con_contacto"]],
                         [self.N - 1, self.N])
        carpeta = A.escribir_salidas(r, self.tmp / "analisis")
        with _silencio():
            self.assertEqual(V.main([str(carpeta), "--base", str(self.tmp)]), 0)
        self.assertIn("CRITERIO DE CIERRE", (carpeta / "salida.txt").read_text(encoding="utf-8"))

    def test_contacto_adulterado_o_cierre_faltante_se_detiene(self) -> None:
        self.tomas[-2] = fila_toma(self.N - 1, "sint", 0.36, d_min_obst_medida=0.12)
        self.tomas[-1] = fila_toma(self.N, "sint", 0.36, d_min_obst_medida=0.13)
        with mock.patch.object(CO, "TOMAS_CON_CONTACTO_PARA_CERRAR", 99):
            self.volcar(cerrar=True)                   # un libro "sin criterio"
        self.assertEqual(self.codigo(), A.SALIDA_INTEGRIDAD)

    def test_contacto_del_libro_contra_el_csv(self) -> None:
        """El contacto entre agentes que anotó el libro tiene que verse en el
        CSV (la distancia al obstáculo ya la cruza otro chequeo)."""
        self.tomas[3] = fila_toma(4, "sint", 0.35, colisiones_015=1)
        self.volcar()
        self.assertEqual(self.analizar()["criterio_de_cierre"]["n_tomas_con_contacto"], 1)
        ruta = self.tmp / self.TOMAS_CSV
        filas = A.leer_csv(ruta)
        filas[3]["colisiones_015"] = "0"
        escribir(ruta, filas)
        with self.assertRaises(A.ErrorAnalisis) as e:
            self.analizar()
        self.assertEqual(e.exception.codigo, A.SALIDA_INTEGRIDAD)
        self.assertIn("contacto libro", str(e.exception))


class PruebaRecuentoFisico(BaseSintetica):
    """El recuento físico del criterio (§2)."""

    def test_recuento_fisico_con_toma_no_anotada(self) -> None:
        """Una toma con contacto que corrió pero el libro marcó interrumpida
        (no se pudo anotar) más una anotada: el libro cuenta 1 y no cierra;
        el análisis cuenta 2 y declara el incumplimiento."""
        self.tomas[2] = fila_toma(3, "sint", 0.35, d_min_obst_medida=0.11)
        self.tomas[2].update({"_interrumpida": True, "_corrio": True,
                              "intento_campana": ""})
        self.tomas[5] = fila_toma(6, "sint", 0.35, colisiones_015=1)
        self.replica = [f for f in self.replica if f["intento_campana"] != 3]
        self.volcar()
        cr = self.analizar()["criterio_de_cierre"]
        self.assertEqual((cr["n_tomas_con_contacto"], cr["n_contactos_fisicos"]), (1, 2))
        self.assertFalse(cr["cerro_por_criterio"])
        self.assertTrue(cr["incumplimiento_del_criterio"])
        self.assertEqual(cr["debio_cerrar_tras_intento"], 6)
        self.assertEqual([x["intento"] for x in cr["intentos_despues_del_cierre_debido"]],
                         list(range(7, self.N + 1)))

    def test_sin_intentos_despues_del_cierre_debido_no_hay_incumplimiento(self) -> None:
        """El 2.º contacto físico es la última toma: el criterio no llegó a
        cerrar (el libro no la anotó), pero no se corrió nada más."""
        self.tomas[2] = fila_toma(3, "sint", 0.35, d_min_obst_medida=0.11)
        self.tomas[-1] = fila_toma(self.N, "sint", 0.35, colisiones_015=1)
        self.tomas[-1].update({"_interrumpida": True, "_corrio": True, "intento_campana": ""})
        self.replica = [f for f in self.replica if f["intento_campana"] != self.N]
        self.volcar()
        cr = self.analizar()["criterio_de_cierre"]
        self.assertEqual(cr["n_contactos_fisicos"], 2)
        self.assertEqual(cr["debio_cerrar_tras_intento"], self.N)
        self.assertFalse(cr["incumplimiento_del_criterio"])

    def test_la_toma_cortada_entra_a_la_seguridad(self) -> None:
        self.tomas[1]["_interrumpida"] = True
        self.replica = [f for f in self.replica if f["intento_campana"] != 2]
        self.volcar()
        filas = [{"episodio": 2, "agente": i, "paso": 0, "pose_env_x": 0.5 + 0.5 * i,
                  "pose_env_y": 0.5, "d_obst_medida": 0.13 if i == 0 else 0.5,
                  "id_sesion": "s1"} for i in range(5)]
        escribir(self.tmp / "20261010_100000_L2_decisiones.csv", filas)
        g = self.analizar()["seguridad"]
        self.assertEqual(g["corridas"], self.N)
        self.assertEqual(g["contacto_hw"]["k"], 1)

    def test_recuento_fisico_de_una_toma_cortada_a_mitad(self) -> None:
        """Ctrl+C a mitad de la toma 2: no hay fila de tomas, pero sus
        decisiones muestran un par de agentes a 0.10 m."""
        self.tomas[1]["_interrumpida"] = True               # sin fila de tomas
        self.replica = [f for f in self.replica if f["intento_campana"] != 2]
        self.volcar()
        filas = []
        for paso in range(3):
            for i in range(5):
                x = 0.5 + 0.5 * i if not (paso == 2 and i == 1) else 0.6
                filas.append({"episodio": 2, "agente": i, "paso": paso,
                              "pose_env_x": x if i != 0 else 0.5, "pose_env_y": 0.5,
                              "d_obst_medida": 0.4, "id_sesion": "s1"})
        escribir(self.tmp / "20261010_100000_L2_decisiones.csv", filas)
        cr = self.analizar()["criterio_de_cierre"]
        self.assertEqual(cr["n_contactos_fisicos"], 1)
        self.assertIn("decisiones de una toma cortada", cr["contactos_fisicos"][0]["que"])
        self.assertFalse(cr["incumplimiento_del_criterio"])

    def test_cierre_con_filas_que_no_son_reservas_en_el_medio(self) -> None:
        """El cierre puede venir después de un cierre de sesión (la sesión
        siguiente lo aplicó al abrir): vale si no hay reservas en el medio."""
        self.tomas[-2] = fila_toma(self.N - 1, "sint", 0.36, d_min_obst_medida=0.12)
        self.tomas[-1] = fila_toma(self.N, "sint", 0.36, d_min_obst_medida=0.12)
        with mock.patch.object(CO.Campana, "_aplicar_criterio_de_seguridad",
                               lambda self_: None):
            self.volcar(cerrar=False)
        self.campana._agregar({"tipo": "cierre_sesion", "motivo": "corte"})
        c = CO.Campana(CO.Campana.carpeta_de(self.tmp, "sint"))
        c._aplicar_criterio_de_seguridad()
        cr = self.analizar()["criterio_de_cierre"]
        self.assertTrue(cr["cerro_por_criterio"])
        self.assertFalse(cr["incumplimiento_del_criterio"])
        carpeta = A.escribir_salidas(self.analizar(), self.tmp / "analisis")
        with _silencio():
            self.assertEqual(V.main([str(carpeta), "--base", str(self.tmp)]), 0)


class PruebaCriteriosDel3009(unittest.TestCase):

    def test_fuera_de_soporte_igual_al_del_3009(self) -> None:
        def cuerpo(fuente: str):
            for n in ast.walk(ast.parse(fuente)):
                if isinstance(n, ast.FunctionDef) and n.name == "fuera_de_soporte":
                    n.body = [b for b in n.body if not (
                        isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant))]
                    return ast.dump(n)
            self.fail("sin fuera_de_soporte")
        self.assertEqual(cuerpo(_PAREO_3009.read_text(encoding="utf-8")),
                         cuerpo((_CARPETA / "analizar_campana_l2.py").read_text(encoding="utf-8")))

    def test_descriptivo_del_3009_reproduce_el_reporte(self) -> None:
        r = A.comparacion_3009()
        self.assertEqual(r["cobertura_hw"]["n"], 50)
        self.assertEqual(round(r["cobertura_hw"]["media"], 4), 0.3452)
        self.assertEqual(round(r["cobertura_hw"]["sd"], 4), 0.0428)
        b = r["brecha_por_pares"]
        self.assertEqual((round(b["media"], 4), round(b["ic95"][0], 4), round(b["ic95"][1], 4)),
                         (0.0077, -0.0046, 0.0200))
        e = r["brecha_por_escenario"]
        self.assertEqual((e["n"], round(e["media"], 4), round(e["ic95"][0], 4),
                          round(e["ic95"][1], 4)), (12, 0.0123, -0.0073, 0.0318))
        p = r["d_pared_hw_menos_replica"]
        self.assertEqual((round(p["media"], 4), round(p["ic95"][0], 4), round(p["ic95"][1], 4)),
                         (-0.0355, -0.0404, -0.0306))


if __name__ == "__main__":
    unittest.main(verbosity=2)
