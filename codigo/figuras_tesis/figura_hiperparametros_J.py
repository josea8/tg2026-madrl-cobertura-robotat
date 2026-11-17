"""
figura_hiperparametros_J.py
===========================
Figura de dispersión del estudio J (análisis A) sin la configuración duplicada.

La prueba 2 repitió la configuración de la prueba 0 (Optuna la reutilizó del
caché), así que el análisis A tiene 9 configuraciones distintas y no 10. Los
coeficientes de los subtítulos se leen de
`resultados/analisis/correlaciones_ABC_sin_duplicado_holm.json` (columna
"sin_duplicado"), que es la revisión del 2026-09-24 de la bitácora.

Lee la base de Optuna en sólo lectura con las mismas funciones de
`recalcular_ABC_sin_duplicado_holm.py` (se extraen con ast para no importar
scipy). Salida: material_complementario/fuente/scatter_hparams_J.png
"""
from __future__ import annotations

import ast
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

AQUI = Path(__file__).resolve().parent
DIR_J = AQUI.parent / "fase_preliminar2" / "experimento_J"  # codigo/fase_preliminar2/experimento_J
SALIDA = AQUI.parents[1] / "material_complementario" / "fuente"
SALIDA.mkdir(exist_ok=True)

fuente = (DIR_J / "recalcular_ABC_sin_duplicado_holm.py").read_text(encoding="utf-8")
arbol = ast.parse(fuente)
ns: Dict[str, Any] = {"json": json, "sqlite3": sqlite3, "Path": Path, "Any": Any, "Dict": Dict,
                      "List": List, "Sequence": Sequence, "Tuple": Tuple}
for nodo in arbol.body:
    if isinstance(nodo, ast.FunctionDef) and nodo.name in (
            "conectar_solo_lectura", "a_representacion_externa", "cargar_pruebas_sqlite"):
        exec(compile(ast.Module([nodo], []), "recalcular", "exec"), ns)
    if isinstance(nodo, ast.AnnAssign) and getattr(nodo.target, "id", "") == "PARAMS":
        exec(compile(ast.Module([nodo], []), "recalcular", "exec"), ns)
ns["PARAMS"] = ns.get("PARAMS", ("lambda_cbf", "lambda_entropy", "n_epochs", "n_steps_exp"))
filas = ns["cargar_pruebas_sqlite"](DIR_J / "optuna_studies" / "experimento_J.db")

completas = [f for f in filas if f["cobertura_media"] is not None and f["prueba"] != 2]
podadas = [f for f in filas if f["cobertura_media"] is None and f["cob_semilla_42"] is not None]
assert len(completas) == 9, len(completas)
corr = json.loads((DIR_J / "resultados" / "analisis" /
                   "correlaciones_ABC_sin_duplicado_holm.json").read_text(encoding="utf-8"))
det = corr["analisis"]["A"]["detalle"]

SERIE_A, SERIE_B, GRIS = "#2A78D6", "#EB6834", "#6B6B6B"
plt.rcParams.update({"font.size": 9, "axes.labelsize": 9, "xtick.labelsize": 8.5,
                     "ytick.labelsize": 8.5, "legend.fontsize": 7.5,
                     "axes.spines.top": False, "axes.spines.right": False})
etiquetas = {"lambda_cbf": r"$\lambda_{\mathrm{cbf}}$", "lambda_entropy": r"$\lambda_{\mathrm{ent}}$",
             "n_epochs": "Épocas por actualización", "n_steps_exp": "Exponente del horizonte"}
referencia = 68.13
mejor = 100 * max(f["cobertura_media"] for f in completas)
fig, ejes = plt.subplots(2, 2, figsize=(6.2, 4.6))
for ax, p in zip(ejes.ravel(), ("lambda_cbf", "lambda_entropy", "n_epochs", "n_steps_exp")):
    ax.scatter([f[p] for f in podadas], [100 * f["cob_semilla_42"] for f in podadas],
               c=SERIE_B, edgecolors="k", linewidths=0.5, s=26, alpha=0.85,
               label="prueba podada (solo semilla 42)")
    ax.scatter([f[p] for f in completas], [100 * f["cobertura_media"] for f in completas],
               c=SERIE_A, edgecolors="k", linewidths=0.5, s=32,
               label="configuración completa (media de 3 semillas)")
    ax.axhline(referencia, ls="--", c="black", lw=0.9, label=f"referencia ({referencia:.2f} %)")
    s = det[p]["sin_duplicado"]
    ax.set_title(f"$\\rho$ = {s['rho']:+.2f}, $p$ = {s['p']:.3f}".replace("-", "−"), fontsize=9)
    ax.set_xlabel(etiquetas[p])
    ax.set_ylabel("Cobertura AoI [%]")
    ax.grid(alpha=0.3)
    print(p, "rho", round(s["rho"], 3), "p", round(s["p"], 4), "n", s["n"])
manejadores, nombres = ejes[0, 0].get_legend_handles_labels()
fig.tight_layout(rect=(0, 0.07, 1, 1))
fig.legend(manejadores[::-1], nombres[::-1], loc="lower center", ncol=3, frameon=False,
           bbox_to_anchor=(0.5, 0.0))
fig.savefig(SALIDA / "scatter_hparams_J.png", dpi=300, bbox_inches="tight")
print("figura →", SALIDA / "scatter_hparams_J.png", "| completas", len(completas), "| podadas", len(podadas), "| mejor", round(mejor, 2))
