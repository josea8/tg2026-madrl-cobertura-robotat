"""
analizar_estudio_J.py — análisis y entregables del Experimento J.

Produce, a partir de la base del estudio y de los JSON por semilla:

  1. CSV con todas las pruebas (parámetros, cobertura media, CV, colisiones).
  2. Correlaciones de rango (Spearman) de los cuatro hiperparámetros contra
     la cobertura, con la figura en el estilo de `scatter_hparams.png`.
  3. Análisis de las 20 curvas: posición del máximo por prueba, CON la prueba
     de identificabilidad — si el máximo y el segundo mejor difieren en menos
     que el error estándar de la evaluación, esa curva NO tiene máximo
     identificable y queda excluida de las correlaciones de posición.
  4. Distribución de colisiones, para calibrar el umbral a posteriori en vez
     de fijarlo a priori.
  5. Tabla comparativa estudio original vs. estudio nuevo.

No lanza entrenamientos. Sólo lee artefactos ya producidos.

Uso
───
    python analizar_estudio_J.py

Autor: José — Tesis Mecatrónica UVG
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import optuna
from scipy.stats import spearmanr

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DIR_BASE:   Path = Path(__file__).resolve().parent
DIR_SALIDA: Path = DIR_BASE / "resultados" / "analisis"
DIR_ESTUDIO: Path = DIR_BASE / "resultados" / "estudio"
RUTA_DB:    Path = DIR_BASE / "optuna_studies" / "experimento_J.db"

PARAMS = ("lambda_cbf", "lambda_entropy", "n_epochs", "n_steps_exp")

# Referencias del estudio original y del modelo adoptado
COBERTURA_REFERENCIA:  float = 0.6813   # modelo_PRIMERO, 100 eps, UNA semilla
CV_TRIAL13_H05:        float = 0.589    # H-05, protocolo con episodios distintos
COLISIONES_REFERENCIA: float = 0.21     # política desnuda del modelo adoptado
# Correlaciones del estudio original — contra RECOMPENSA, no cobertura
RHO_ORIGINAL: Dict[str, float] = {
    "lambda_cbf": -0.76, "n_epochs": +0.48, "n_steps_exp": +0.33,
    "lambda_entropy": +0.28,
}


# ══════════════════════════════════════════════════════════════════════════════
#  CARGA
# ══════════════════════════════════════════════════════════════════════════════

def cargar_pruebas() -> List[Dict[str, Any]]:
    """
    Reúne, por prueba, los parámetros y todo lo medido.

    Incluye las pruebas podadas en la etapa 2: tienen cobertura de semilla 42
    y sirven para las correlaciones sobre esa cantidad, aunque no tengan valor
    objetivo promediado.
    """
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    estudio = optuna.load_study(study_name="experimento_J",
                                storage=f"sqlite:///{RUTA_DB}")
    filas: List[Dict[str, Any]] = []
    for t in estudio.trials:
        if not t.params:
            continue
        fila: Dict[str, Any] = {
            "prueba": t.number,
            "estado": t.state.name,
            **{p: t.params.get(p) for p in PARAMS},
            "n_steps": 2 ** t.params["n_steps_exp"] if "n_steps_exp" in t.params else None,
            "cobertura_media":  t.user_attrs.get("cobertura_media"),
            "cobertura_std":    t.user_attrs.get("cobertura_std"),
            "cobertura_cv":     t.user_attrs.get("cobertura_cv"),
            "colisiones_media": t.user_attrs.get("colisiones_media"),
            "cob_semilla_42":   t.user_attrs.get("cob_semilla_42"),
            "sesgo_retencion":  t.user_attrs.get("sesgo_retencion_medio"),
            "pasos_retenidos":  t.user_attrs.get("pasos_retenidos"),
        }
        filas.append(fila)
    return filas


def cargar_curvas() -> List[Dict[str, Any]]:
    """Lee las curvas de cobertura-contra-pasos de todas las semillas corridas."""
    curvas: List[Dict[str, Any]] = []
    for ruta in sorted(DIR_ESTUDIO.glob("cfg_*/semilla_*/resultado_semilla.json")):
        d = json.loads(ruta.read_text(encoding="utf-8"))
        cfg_ruta = ruta.parent.parent / "config_barridos.json"
        barridos = json.loads(cfg_ruta.read_text(encoding="utf-8")) if cfg_ruta.exists() else {}
        curvas.append({
            "cfg":            ruta.parent.parent.name,
            "semilla":        d["semilla"],
            "curva":          d["curva"],
            "paso_retenido":  d["paso_retenido"],
            "cobertura_final": d["cobertura_final"],
            "std_episodios":  d["agregados_final"]["cobertura_aoi_final"]["std"],
            "n_eps_final":    len(d["agregados_final"]) and 30,
            **barridos,
        })
    return curvas


# ══════════════════════════════════════════════════════════════════════════════
#  ANÁLISIS
# ══════════════════════════════════════════════════════════════════════════════

def correlaciones(filas: List[Dict[str, Any]], clave: str) -> Dict[str, Tuple[float, float]]:
    """Spearman ρ y valor p de cada hiperparámetro contra `clave`."""
    res: Dict[str, Tuple[float, float]] = {}
    for p in PARAMS:
        # Se descartan las filas sin el hiperparámetro: las curvas de pruebas
        # anteriores a la paralelización no tienen `config_barridos.json`.
        validas = [f for f in filas
                   if f.get(clave) is not None and f.get(p) is not None]
        x = np.array([f[p] for f in validas], dtype=float)
        y = np.array([f[clave] for f in validas], dtype=float)
        if len(x) < 3:
            res[p] = (float("nan"), float("nan"))
            continue
        rho, pval = spearmanr(x, y)
        res[p] = (float(rho), float(pval))
    return res


def metricas_a_paso_fijo(curvas: List[Dict[str, Any]], paso: int = 200_000) -> List[Dict[str, Any]]:
    """
    Cobertura y colisiones de cada semilla en un paso FIJO del entrenamiento.

    Por qué hace falta: la cifra de colisiones del punto retenido no describe a
    la configuración, sino dónde aterrizó la retención — que va por cobertura y
    cae en pasos distintos según la semilla. Como las colisiones varían mucho a
    lo largo del entrenamiento (se han visto curvas de 4.10 a 0.10 en una misma
    semilla), comparar configuraciones por su punto retenido mezcla el efecto de
    la configuración con el del criterio de selección.

    Comparar a paso fijo elimina esa contaminación. La información ya está en
    las curvas de las diez evaluaciones, así que no requiere reentrenar nada.
    """
    salida: List[Dict[str, Any]] = []
    for c in curvas:
        punto = next((p for p in c["curva"] if p["pasos"] == paso), None)
        if punto is None:
            continue
        salida.append({
            "cfg":        c["cfg"],
            "semilla":    c["semilla"],
            "paso":       paso,
            "cobertura":  punto["cobertura"],
            "colisiones": punto["colisiones"],
            **{p: c.get(p) for p in PARAMS},
        })
    return salida


def analizar_maximos(curvas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Para cada curva: posición del máximo y si ese máximo es IDENTIFICABLE.

    Criterio: el máximo y el segundo mejor deben diferir en más que el error
    estándar de la evaluación (std entre episodios / raíz de n). Si no, la curva
    no tiene máximo distinguible del ruido y no debe entrar en correlaciones de
    posición: sería correlacionar ruido.

    La posición tiene además resolución de 20 000 pasos por construcción, y no
    debe tratarse como estimación fina.
    """
    salida: List[Dict[str, Any]] = []
    for c in curvas:
        vals = np.array([p["cobertura"] for p in c["curva"]], dtype=float)
        pasos = np.array([p["pasos"] for p in c["curva"]], dtype=int)
        if len(vals) < 2:
            continue
        orden = np.argsort(vals)[::-1]
        mejor, segundo = vals[orden[0]], vals[orden[1]]
        err_estandar = c["std_episodios"] / np.sqrt(20)   # 20 eps de retención
        identificable = (mejor - segundo) > err_estandar
        salida.append({
            "cfg":            c["cfg"],
            "semilla":        c["semilla"],
            "paso_maximo":    int(pasos[orden[0]]),
            "cobertura_max":  float(mejor),
            "margen":         float(mejor - segundo),
            "error_estandar": float(err_estandar),
            "identificable":  bool(identificable),
            "degradacion":    float(mejor - vals[-1]),   # pico menos valor final
        })
    return salida


# ══════════════════════════════════════════════════════════════════════════════
#  FIGURA
# ══════════════════════════════════════════════════════════════════════════════

def figura_dispersion(filas: List[Dict[str, Any]], rhos: Dict[str, Tuple[float, float]],
                      ruta: Path) -> None:
    """Dispersión de los cuatro hiperparámetros contra la cobertura media."""
    fig, ejes = plt.subplots(2, 2, figsize=(12, 8))
    completas = [f for f in filas if f["cobertura_media"] is not None]
    podadas   = [f for f in filas if f["cobertura_media"] is None
                 and f["cob_semilla_42"] is not None]

    mejor = max((f["cobertura_media"] for f in completas), default=None)

    for eje, p in zip(ejes.ravel(), PARAMS):
        if completas:
            eje.scatter([f[p] for f in completas], [f["cobertura_media"] for f in completas],
                        c="tab:blue", edgecolors="k", s=55, label="COMPLETA (media de 3 semillas)")
        if podadas:
            eje.scatter([f[p] for f in podadas], [f["cob_semilla_42"] for f in podadas],
                        c="tab:red", edgecolors="k", s=45, alpha=0.75,
                        label="PODADA (sólo semilla 42)")
        eje.axhline(COBERTURA_REFERENCIA, ls="--", c="tab:green",
                    label=f"referencia = {COBERTURA_REFERENCIA:.4f}")
        if mejor is not None:
            eje.axhline(mejor, ls=":", c="tab:purple", label=f"mejor = {mejor:.4f}")
        rho, pval = rhos.get(p, (float("nan"), float("nan")))
        # El ρ se calcula SÓLO sobre las pruebas completas (puntos azules). Los
        # puntos rojos se dibujan como contexto pero NO entran en el cálculo:
        # su ordenada es la cobertura de una sola semilla, no la media de tres.
        eje.set_title(f"{p} (ρ = {rho:+.2f}, p = {pval:.3f}, n = {len(completas)})")
        eje.set_xlabel(p)
        eje.set_ylabel("cobertura AoI")
        eje.grid(alpha=0.3)

    ejes.ravel()[0].legend(fontsize=8, loc="best")
    fig.suptitle(
        "Experimento J — ANÁLISIS A: hiperparámetros vs cobertura AoI\n"
        "objetivo = media de 3 semillas EN SU PUNTO RETENIDO · ρ sobre las "
        f"{len(completas)} pruebas completas (azules); las podadas (rojas) no entran\n"
        "NO comparable con el análisis a paso fijo (ver reporte)",
        fontsize=11)
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def figura_curvas(curvas: List[Dict[str, Any]], ruta: Path) -> None:
    """Todas las curvas de cobertura-contra-pasos, una línea por semilla."""
    fig, eje = plt.subplots(figsize=(10, 6))
    for c in curvas:
        pasos = [p["pasos"] for p in c["curva"]]
        cob   = [p["cobertura"] for p in c["curva"]]
        eje.plot(pasos, cob, marker="o", ms=3, lw=1, alpha=0.65)
    eje.axhline(COBERTURA_REFERENCIA, ls="--", c="tab:green",
                label=f"referencia = {COBERTURA_REFERENCIA:.4f}")
    eje.axvline(100_000, ls=":", c="gray", label="presupuesto del estudio original")
    eje.set_xlabel("pasos de entrenamiento")
    eje.set_ylabel("cobertura AoI")
    eje.set_title("Experimento J: curvas de cobertura de todas las semillas\n"
                  "(¿la degradación más allá de 100k es universal o depende de la configuración?)")
    eje.grid(alpha=0.3)
    eje.legend()
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    filas  = cargar_pruebas()
    curvas = cargar_curvas()
    completas = [f for f in filas if f["cobertura_media"] is not None]

    print(f"pruebas en la base: {len(filas)}  —  completas: {len(completas)}  "
          f"—  curvas de semilla: {len(curvas)}\n")

    # ── CSV ────────────────────────────────────────────────────────────────
    import csv
    ruta_csv = DIR_SALIDA / "pruebas_experimento_J.csv"
    with ruta_csv.open("w", newline="", encoding="utf-8") as fh:
        campos = list(filas[0].keys()) if filas else []
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        for f in filas:
            w.writerow(f)
    print(f"CSV → {ruta_csv}")

    # ── Correlaciones ──────────────────────────────────────────────────────
    rho_media = correlaciones(completas, "cobertura_media")
    rho_s42   = correlaciones(filas,     "cob_semilla_42")
    rho_col   = correlaciones(completas, "colisiones_media")

    print("\nCORRELACIONES DE RANGO (Spearman)")
    print(f"{'parámetro':<16} {'ρ vs cobertura':>16} {'ρ vs cob s42':>14} "
          f"{'ρ vs colisiones':>16} {'ρ original (rew)':>18}")
    for p in PARAMS:
        print(f"{p:<16} {rho_media[p][0]:>+16.3f} {rho_s42[p][0]:>+14.3f} "
              f"{rho_col[p][0]:>+16.3f} {RHO_ORIGINAL.get(p, float('nan')):>+18.2f}")

    # ── Máximos ────────────────────────────────────────────────────────────
    maximos = analizar_maximos(curvas)
    ident = [m for m in maximos if m["identificable"]]
    print(f"\nMÁXIMOS: {len(ident)} de {len(maximos)} curvas tienen máximo identificable")
    print("  (resolución de la posición: 20 000 pasos — no es estimación fina)")
    if ident:
        pos = np.array([m["paso_maximo"] for m in ident])
        print(f"  posición del máximo: mediana {np.median(pos):.0f}, "
              f"rango [{pos.min()}, {pos.max()}]")
        print(f"  curvas con máximo antes de 200k: "
              f"{int((pos < 200_000).sum())} de {len(pos)}")
        deg = np.array([m["degradacion"] for m in ident])
        print(f"  degradación pico→final: mediana {np.median(deg):.6f}, "
              f"máxima {deg.max():.6f}")

    # ── Colisiones ─────────────────────────────────────────────────────────
    if completas:
        col = np.array([f["colisiones_media"] for f in completas], dtype=float)
        print(f"\nCOLISIONES (política desnuda, pares por episodio)")
        print(f"  referencia del modelo adoptado: {COLISIONES_REFERENCIA}")
        print(f"  estudio: mediana {np.median(col):.4f}, rango [{col.min():.4f}, {col.max():.4f}]")
        for q in (50, 75, 90):
            print(f"  percentil {q}: {np.percentile(col, q):.4f}")

    # ── Colisiones y cobertura a PASO FIJO (sin contaminación de retención) ─
    fijo = metricas_a_paso_fijo(curvas, paso=200_000)
    if fijo:
        col_f = np.array([f["colisiones"] for f in fijo], dtype=float)
        cob_f = np.array([f["cobertura"] for f in fijo], dtype=float)
        print(f"\nA PASO FIJO (200 000), {len(fijo)} semillas — sin sesgo del punto retenido")
        print(f"  colisiones: mediana {np.median(col_f):.4f}, "
              f"rango [{col_f.min():.4f}, {col_f.max():.4f}]")
        print(f"  cobertura : mediana {np.median(cob_f):.6f}, "
              f"rango [{cob_f.min():.6f}, {cob_f.max():.6f}]")
        rho_fijo = correlaciones(fijo, "colisiones")
        print("  ρ de los hiperparámetros contra colisiones a paso fijo:")
        for p in PARAMS:
            print(f"    {p:<16} {rho_fijo[p][0]:>+7.3f}  (p = {rho_fijo[p][1]:.3f})")
        rho_cob_fijo = correlaciones(fijo, "cobertura")
        print("  ρ de los hiperparámetros contra cobertura a paso fijo:")
        for p in PARAMS:
            print(f"    {p:<16} {rho_cob_fijo[p][0]:>+7.3f}  (p = {rho_cob_fijo[p][1]:.3f})")

    # ── Tabla comparativa ──────────────────────────────────────────────────
    mejor = max(completas, key=lambda f: f["cobertura_media"]) if completas else None
    comparativa = {
        "estudio_original": {
            "espacio":       "12 hiperparámetros",
            "objetivo":      "recompensa media de evaluación",
            "presupuesto":   100_000,
            "semillas":      1,
            "episodios_eval": 10,
            "retencion":     "ninguna (una sola evaluación, al final)",
            "cobertura":     COBERTURA_REFERENCIA,
            "cv_entre_semillas": CV_TRIAL13_H05,
        },
        "estudio_J": {
            "espacio":       "4 hiperparámetros",
            "objetivo":      "cobertura AoI",
            "presupuesto":   200_000,
            "semillas":      3,
            "episodios_eval": 20,
            "retencion":     "mejor punto de control por cobertura (10 evaluaciones)",
            "cobertura":     mejor["cobertura_media"] if mejor else None,
            "cv_entre_semillas": mejor["cobertura_cv"] if mejor else None,
            "mejor_config":  {p: mejor[p] for p in PARAMS} if mejor else None,
            "colisiones":    mejor["colisiones_media"] if mejor else None,
        },
    }
    ruta_json = DIR_SALIDA / "comparativa.json"
    ruta_json.write_text(json.dumps(
        {"comparativa": comparativa,
         "correlaciones": {"vs_cobertura": rho_media, "vs_cob_s42": rho_s42,
                           "vs_colisiones": rho_col},
         "maximos": maximos},
        indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\ncomparativa → {ruta_json}")

    # ── Figuras ────────────────────────────────────────────────────────────
    figura_dispersion(filas, rho_media, DIR_SALIDA / "scatter_hparams_J.png")
    figura_curvas(curvas, DIR_SALIDA / "curvas_cobertura_J.png")
    print(f"figuras → {DIR_SALIDA}")


if __name__ == "__main__":
    main()
