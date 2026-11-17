"""
analizar_P.py — Análisis del Experimento P, según PREREGISTRO_P.md.

Propósito: ESTIMACIÓN, no prueba de superioridad. No se calculan valores p
para decidir nada: se reportan estimaciones con intervalos de confianza y la
potencia (a priori y con las dispersiones observadas) junto a los resultados.

Unidad de análisis: la SEMILLA de entrenamiento. Cada métrica por semilla es
la media sobre los episodios del conjunto correspondiente. Las semillas
42/123/777 del Exp J NO se mezclan.

Métricas (definidas a priori):
  PRIMARIA     cob_retenido_nuevo   cobertura AoI del punto retenido, conjunto
                                     nuevo (100 eps, offset 2000)
  SECUNDARIAS  cob_retenido_final   punto retenido, conjunto final (30 eps,
                                     offset 1000; el objetivo del Exp J)
               cob_fijo200k_nuevo   paso fijo 200k, conjunto nuevo
               cob_fijo200k_final   paso fijo 200k, conjunto final
  DESCRIPTIVAS colisiones (pares < D_SAFE, política desnuda) en esos cuatro
               cruces, paso retenido, y el CV entre semillas retenido vs paso
               fijo (pregunta abierta sobre el CV 0.0126 del Exp J).

Por brazo: n, media, DE (ddof=1), CV, mediana, IQM (media recortada al 25 %),
IC95 de la media (t y bootstrap percentil) e IC95 del IQM (bootstrap).
Diferencia ganadora − Trial 13: IC95 de Welch y bootstrap (remuestreo
independiente por brazo; compartir semilla no correlaciona las trayectorias
porque los hiperparámetros difieren). Bootstrap: B = 10 000, generador
`numpy.random.default_rng(20260924)`.

Potencia (Welch, bilateral, α = 0.05, aproximación t no central):
  a priori, escenarios fijados en el preregistro, n = 20 por brazo, δ = 0.0126;
  con las DE observadas: potencia para δ = 0.0126 y efecto mínimo detectable
  al 80 %. No es "potencia observada" con el efecto observado.

Uso:  python3 -B analizar_P.py [--humo]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import optimize, stats

import comun_P as C

DELTA_REFERENCIA: float = 0.0126     # el +0.0126 de la bitácora (no homogéneo; ver preregistro)
B_BOOTSTRAP: int = 10_000
SEMILLA_BOOTSTRAP: int = 20260924
ESCENARIOS_A_PRIORI: Tuple[Tuple[str, float, float], ...] = (
    ("optimista: σ 0.0086 en ambos brazos",                     0.0086, 0.0086),
    ("σ agrupada de las 5 mejores del J (0.0156) en ambos",     0.0156, 0.0156),
    ("ganadora 0.0086, Trial 13 con σ de H-05 reproducibilidad", 0.0086, 0.0537),
    ("ganadora 0.0086, Trial 13 con σ de H-05 multimétrica",     0.0086, 0.0909),
    ("paso fijo 200k: ganadora 0.0557, Trial 13 0.0909",         0.0557, 0.0909),
)
METRICAS: Tuple[Tuple[str, str, str], ...] = (
    ("cob_retenido_nuevo", "retenido@nuevo", "cobertura_aoi_final"),
    ("cob_retenido_final", "retenido@final", "cobertura_aoi_final"),
    ("cob_fijo200k_nuevo", "fijo200k@nuevo", "cobertura_aoi_final"),
    ("cob_fijo200k_final", "fijo200k@final", "cobertura_aoi_final"),
    ("col_retenido_nuevo", "retenido@nuevo", "n_colisiones"),
    ("col_retenido_final", "retenido@final", "n_colisiones"),
    ("col_fijo200k_nuevo", "fijo200k@nuevo", "n_colisiones"),
    ("col_fijo200k_final", "fijo200k@final", "n_colisiones"),
)


# ══════════════════════════════════════════════════════════════════════════════
#  Estadística
# ══════════════════════════════════════════════════════════════════════════════

def iqm(x: np.ndarray) -> float:
    return float(stats.trim_mean(x, 0.25))


def bootstrap_ic(x: np.ndarray, estadistico, rng: np.random.Generator) -> Tuple[float, float]:
    idx = rng.integers(0, len(x), size=(B_BOOTSTRAP, len(x)))
    valores = np.array([estadistico(x[fila]) for fila in idx])
    return float(np.percentile(valores, 2.5)), float(np.percentile(valores, 97.5))


def resumen_brazo(x: np.ndarray, rng: np.random.Generator) -> Dict[str, Any]:
    n = len(x)
    media = float(x.mean())
    de = float(x.std(ddof=1)) if n > 1 else float("nan")
    if n > 1:
        semi = float(stats.t.ppf(0.975, n - 1) * de / math.sqrt(n))
        ic_t = (media - semi, media + semi)
    else:
        semi, ic_t = float("nan"), (float("nan"), float("nan"))
    return {
        "n": n, "media": media, "de": de, "cv": de / media if media else float("nan"),
        "mediana": float(np.median(x)), "iqm": iqm(x) if n >= 4 else float("nan"),
        "min": float(x.min()), "max": float(x.max()),
        "ic95_media_t": ic_t, "semiamplitud_ic95_t": semi,
        "ic95_media_bootstrap": bootstrap_ic(x, np.mean, rng) if n > 1 else None,
        "ic95_iqm_bootstrap": bootstrap_ic(x, iqm, rng) if n >= 4 else None,
    }


def diferencia(a: np.ndarray, b: np.ndarray, rng: np.random.Generator) -> Dict[str, Any]:
    """ganadora (a) − Trial 13 (b): IC95 de Welch y bootstrap independiente."""
    d = float(a.mean() - b.mean())
    welch = stats.ttest_ind(a, b, equal_var=False)
    ic_w = welch.confidence_interval(0.95)
    ia = rng.integers(0, len(a), size=(B_BOOTSTRAP, len(a)))
    ib = rng.integers(0, len(b), size=(B_BOOTSTRAP, len(b)))
    boot = a[ia].mean(axis=1) - b[ib].mean(axis=1)
    boot_iqm = np.array([iqm(a[i]) - iqm(b[j]) for i, j in zip(ia, ib)])
    return {
        "dif_medias": d, "ic95_welch": (float(ic_w.low), float(ic_w.high)), "gl_welch": float(welch.df),
        "ic95_bootstrap": (float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))),
        "dif_iqm": iqm(a) - iqm(b),
        "ic95_dif_iqm_bootstrap": (float(np.percentile(boot_iqm, 2.5)), float(np.percentile(boot_iqm, 97.5))),
    }


def potencia_welch(delta: float, s1: float, s2: float, n1: int, n2: int, alfa: float = 0.05) -> float:
    """Potencia bilateral de Welch con t no central (gl de Welch-Satterthwaite)."""
    v1, v2 = s1 ** 2 / n1, s2 ** 2 / n2
    ee = math.sqrt(v1 + v2)
    gl = (v1 + v2) ** 2 / (v1 ** 2 / (n1 - 1) + v2 ** 2 / (n2 - 1))
    tc = stats.t.ppf(1 - alfa / 2, gl)
    ncp = delta / ee
    return float(1 - stats.nct.cdf(tc, gl, ncp) + stats.nct.cdf(-tc, gl, ncp))


def efecto_minimo_detectable(s1: float, s2: float, n1: int, n2: int, potencia: float = 0.80) -> float:
    """δ con potencia 0.80. El intervalo de búsqueda se escala al error estándar
    (hasta ncp = 8, donde la potencia ya es ~1) porque `nct.cdf` da NaN con
    parámetros de no centralidad muy grandes."""
    ee = math.sqrt(s1 ** 2 / n1 + s2 ** 2 / n2)
    return float(optimize.brentq(lambda d: potencia_welch(d, s1, s2, n1, n2) - potencia,
                                 1e-9 * ee, 8.0 * ee))


# ══════════════════════════════════════════════════════════════════════════════
#  Carga
# ══════════════════════════════════════════════════════════════════════════════

def cargar(base, semillas) -> Tuple[List[Dict[str, Any]], List[str]]:
    filas: List[Dict[str, Any]] = []
    faltantes: List[str] = []
    for brazo in C.BRAZOS:
        for s in semillas:
            ruta_t = base / brazo / f"semilla_{s}" / "resultado_semilla.json"
            ruta_e = base / "evaluacion" / f"{brazo}_s{s}.json"
            if not (ruta_t.exists() and ruta_e.exists()):
                faltantes.append(f"{brazo}_s{s}")
                continue
            t = json.loads(ruta_t.read_text(encoding="utf-8"))
            e = json.loads(ruta_e.read_text(encoding="utf-8"))
            fila: Dict[str, Any] = {"brazo": brazo, "semilla": s,
                                    "paso_retenido": t["paso_retenido"],
                                    "cobertura_final_trabajador": t["cobertura_final"],
                                    "segundos_entrenamiento": t["segundos_total"]}
            for nombre, clave_eval, metrica in METRICAS:
                fila[nombre] = e["evaluaciones"][clave_eval]["agregados"][metrica]["media"]
            filas.append(fila)
    return filas, faltantes


def tabla_csv(filas: List[Dict[str, Any]]) -> str:
    buf = io.StringIO()
    escritor = csv.DictWriter(buf, fieldnames=list(filas[0].keys()), lineterminator="\n")
    escritor.writeheader()
    for f in filas:
        escritor.writerow({k: repr(v) if isinstance(v, float) else v for k, v in f.items()})
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
#  Principal
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--humo", action="store_true")
    args = parser.parse_args()
    base = C.dir_base(args.humo)
    semillas = C.SEMILLAS[:1] if args.humo else C.SEMILLAS[:C.N_POR_BRAZO]

    filas, faltantes = cargar(base, semillas)
    if not filas:
        print("ABORTADO: no hay semillas evaluadas")
        return 1
    rng = np.random.default_rng(SEMILLA_BOOTSTRAP)
    salida: Dict[str, Any] = {
        "fecha": datetime.now().isoformat(timespec="seconds"), "humo": args.humo,
        "semillas_previstas": list(semillas), "faltantes": faltantes,
        "definiciones": {n: {"evaluacion": ce, "metrica": m} for n, ce, m in METRICAS},
        "brazos": {}, "diferencias_ganadora_menos_trial13": {}, "potencia": {},
    }
    for nombre, _, _ in METRICAS:
        for brazo in C.BRAZOS:
            x = np.array([f[nombre] for f in filas if f["brazo"] == brazo], dtype=float)
            if len(x):
                salida["brazos"].setdefault(brazo, {})[nombre] = resumen_brazo(x, rng)
        a = np.array([f[nombre] for f in filas if f["brazo"] == "ganadora"], dtype=float)
        b = np.array([f[nombre] for f in filas if f["brazo"] == "trial13"], dtype=float)
        if len(a) > 1 and len(b) > 1:
            salida["diferencias_ganadora_menos_trial13"][nombre] = diferencia(a, b, rng)

    for brazo in C.BRAZOS:
        pasos = [f["paso_retenido"] for f in filas if f["brazo"] == brazo]
        salida["brazos"].setdefault(brazo, {})["paso_retenido"] = {
            str(p): pasos.count(p) for p in sorted(set(pasos))}

    # ── Potencia ───────────────────────────────────────────────────────────
    n1 = sum(1 for f in filas if f["brazo"] == "ganadora")
    n2 = sum(1 for f in filas if f["brazo"] == "trial13")
    salida["potencia"]["a_priori_n20"] = [
        {"escenario": e, "s_ganadora": s1, "s_trial13": s2, "delta": DELTA_REFERENCIA,
         "potencia": potencia_welch(DELTA_REFERENCIA, s1, s2, C.N_POR_BRAZO, C.N_POR_BRAZO),
         "efecto_minimo_detectable_80": efecto_minimo_detectable(s1, s2, C.N_POR_BRAZO, C.N_POR_BRAZO)}
        for e, s1, s2 in ESCENARIOS_A_PRIORI
    ]
    if n1 > 1 and n2 > 1:
        for nombre in ("cob_retenido_nuevo", "cob_retenido_final", "cob_fijo200k_nuevo", "cob_fijo200k_final"):
            s1 = salida["brazos"]["ganadora"][nombre]["de"]
            s2 = salida["brazos"]["trial13"][nombre]["de"]
            salida["potencia"].setdefault("con_de_observadas", {})[nombre] = {
                "n_ganadora": n1, "n_trial13": n2, "s_ganadora": s1, "s_trial13": s2,
                "potencia_para_delta_0.0126": potencia_welch(DELTA_REFERENCIA, s1, s2, n1, n2),
                "efecto_minimo_detectable_80": efecto_minimo_detectable(s1, s2, n1, n2),
            }

    dir_an = base / "analisis"
    C.escribir_texto(dir_an / "tabla_semillas_P.csv", tabla_csv(filas))
    C.escribir_json(dir_an / "resumen_P.json", salida)
    print(json.dumps({"faltantes": faltantes,
                      "primaria": {b: {k: salida["brazos"][b]["cob_retenido_nuevo"][k]
                                       for k in ("n", "media", "de", "ic95_media_t")}
                                   for b in salida["brazos"] if "cob_retenido_nuevo" in salida["brazos"][b]}},
                     indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
