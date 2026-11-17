"""
analizar_experimento_O.py
=========================
Análisis del Exp O desde `resultados/experimento_O_completo.csv`. Analiza los
escenarios que hayan corrido (el criterio de parada puede haber cortado antes).

Comparación principal: Sk − Sk_ctrl, PAREADA por semilla (mismas poses
iniciales y mismos objetivos iniciales; el control no tiene obstáculos).
IC95 = media ± 1,96·EE (convención de los Exp C–N).

Definiciones de cobertura
-------------------------
  cobertura_accesible      : 1 − media del AoI sobre las celdas NO ocupadas
                             por los obstáculos del escenario (en el control,
                             sobre esas mismas celdas). Es la comparación justa.
  cobertura_sin_enmascarar : sobre toda la cuadrícula, contando las celdas
                             ocupadas como nunca cubiertas (en Sk) o con su
                             valor real (en el control). Incluye el área perdida.

Salidas: resultados/resumen_experimento_O.txt,
figuras/fig_obstaculos_intervencion.png, figuras/fig_obstaculos_costo.png

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

_CARPETA: Path = Path(__file__).resolve().parent
RUTA_CSV: Path = _CARPETA / "resultados" / "experimento_O_completo.csv"
RUTA_REG: Path = _CARPETA / "resultados" / "registro_O.txt"
RUTA_RES: Path = _CARPETA / "resultados" / "resumen_experimento_O.txt"
DIR_FIG: Path = _CARPETA / "figuras"
DPI_FIG: int = 300

# Área de la región factible del punto de mira (h ≥ 0), de verificar_pasabilidad
# (registro_O.txt); S0 = (3,0 − 0,36)².
AREA_LIBRE: Dict[str, float] = {"S0": 6.9696, "S1": 6.2454, "S2": 5.8078,
                                "S3": 4.5719}

METRICAS: Tuple[Tuple[str, str], ...] = (
    ("cobertura_accesible", "cobertura AoI (celdas accesibles)"),
    ("cobertura_sin_enmascarar", "cobertura AoI (cuadrícula completa)"),
    ("cobertura_por_agente", "cobertura accesible por agente"),
    ("colisiones_015", "pares en colisión <0,15 m"),
    ("colisiones_022", "pares en colisión <0,22 m"),
    ("contactos_obst_eventos", "contactos con obstáculo (agente-paso)"),
    ("contactos_obst_agente_eps", "agente-eps con contacto con obstáculo"),
    ("d_min_obst_superficie", "d_min centro→superficie obst. [m]"),
    ("viol_cota_obst_agente_eps", "agente-eps centro <0,13 m de obst."),
    ("frac_agente_paso_banda_018", "frac. agente-paso centro <0,18 m pared"),
    ("frac_agente_paso_periferia_050", "frac. agente-paso centro <0,5 m pared"),
    ("d_min_pared_centro", "d_min centro→pared [m]"),
    ("violaciones_margen", "agente-eps centro <0,18 m de pared"),
    ("contacto_pared", "agente-eps centro <0,075 m de pared"),
    ("cbf_frac_interv", "frac. intervención del filtro"),
    ("cbf_frac_hmin_pared", "  … h mín. = pared"),
    ("cbf_frac_hmin_robot", "  … h mín. = robot"),
    ("cbf_frac_hmin_obst", "  … h mín. = obstáculo"),
    ("cbf_frac_lig_pared", "  … pared ligante en el óptimo"),
    ("cbf_frac_lig_robot", "  … robot ligante en el óptimo"),
    ("cbf_frac_lig_obst", "  … obstáculo ligante en el óptimo"),
    ("cbf_frac_lig_multitipo", "  … ≥2 tipos ligantes a la vez"),
    ("cbf_magnitud_media", "magnitud media de la modificación"),
    ("qp_fallbacks", "fallbacks del QP por episodio"),
    ("escape_n", "activaciones del escape por episodio"),
    ("escape_n_junto_obst", "  … con obstáculo activo al disparar"),
    ("escape_frac_ciclo", "frac. de ciclo en escape"),
    ("escape_infactibles", "escapes infactibles por episodio"),
    ("escape_infactibles_junto_obst", "  … con obstáculo activo"),
    ("escape_agotados", "escapes agotados por episodio"),
    ("agentes_reubicados", "agentes reubicados al inicio"),
    ("objetivos_reubicados", "objetivos reubicados al inicio"),
    ("rebotes_objetivo_obst", "rebotes de objetivos en obstáculos"),
    ("frac_mascara", "fracción de celdas enmascaradas"),
)


def cargar() -> Dict[str, Dict[int, Dict[str, float]]]:
    datos: Dict[str, Dict[int, Dict[str, float]]] = {}
    with open(RUTA_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            fila = {}
            for k, v in r.items():
                try:
                    fila[k] = float(v)
                except ValueError:
                    pass
            datos.setdefault(r["condicion"], {})[int(r["seed_ep"])] = fila
    return datos


def vec(datos, c: str, m: str, sem: List[int]) -> np.ndarray:
    return np.array([datos[c][s][m] for s in sem], dtype=np.float64)


def ic95(x: np.ndarray) -> Tuple[float, float, float]:
    m = float(np.mean(x))
    ee = float(np.std(x, ddof=1)) / math.sqrt(len(x)) if len(x) > 1 else 0.0
    return m, m - 1.96 * ee, m + 1.96 * ee


def sig(lo: float, hi: float) -> str:
    return "*" if lo * hi > 0 else " "


def main() -> None:
    datos = cargar()
    sem = sorted(datos["S0"].keys())
    escenarios = [k for k in ("S1", "S2", "S3") if k in datos]
    L: List[str] = []
    L.append("EXPERIMENTO O — Obstáculos estáticos como barreras de ejecución")
    L.append("ENCUADRE: mide la GENERALIDAD DE LA CAPA DE SEGURIDAD, no la")
    L.append("adaptabilidad de la política (la observación no codifica obstáculos).")
    L.append("Configuración final (modelo_sanidad, bloqueante, CBF + escape de tres")
    L.append("términos), arena 3,0, n=5, 100 semillas 420000–420099.")
    L.append("Pareo: Sk − Sk_ctrl por semilla (mismas poses y objetivos iniciales).")
    L.append("=" * 78)
    L.append("")
    if RUTA_REG.exists():
        L += ["REGISTRO DE CORRIDA"] + ["  " + x for x in
                                       RUTA_REG.read_text(encoding="utf-8").splitlines()[1:]]
        L.append("")

    conds = ["S0"] + [c for k in escenarios for c in (f"{k}_ctrl", k)]
    L.append("TABLA — medias sobre 100 episodios")
    L.append(f"  {'métrica':42s}" + "".join(f"{c:>13s}" for c in conds))
    for m, etiq in METRICAS:
        vals = []
        for c in conds:
            v = vec(datos, c, m, sem)
            v = v[np.isfinite(v)]
            vals.append(float(np.mean(v)) if len(v) else float("nan"))
        L.append(f"  {etiq:42s}" + "".join(f"{v:13.8f}" for v in vals))
    for m, etiq in (("d_min_obst_superficie", "d_min obst., mínimo global [m]"),
                    ("d_min_pared_centro", "d_min pared, mínimo global [m]")):
        vals = []
        for c in conds:
            v = vec(datos, c, m, sem)
            v = v[np.isfinite(v)]
            vals.append(float(np.min(v)) if len(v) else float("nan"))
        L.append(f"  {etiq:42s}" + "".join(f"{v:13.8f}" for v in vals))
    L.append("")

    for k in escenarios:
        L.append(f"COMPARACIÓN PAREADA {k} − {k}_ctrl (100 semillas)")
        L.append(f"  {'métrica':42s} {'Δ':>13s} {'IC95':>30s}  {'>0':>4s} {'<0':>4s}")
        for m, etiq in METRICAS:
            if m in ("d_min_obst_superficie", "frac_mascara"):
                continue
            d = vec(datos, k, m, sem) - vec(datos, f"{k}_ctrl", m, sem)
            mm, lo, hi = ic95(d)
            L.append(f"  {etiq:42s} {mm:+13.8f} [{lo:+13.8f}, {hi:+13.8f}]{sig(lo, hi)}"
                     f" {int(np.sum(d > 0)):4d} {int(np.sum(d < 0)):4d}")
        c_rel = vec(datos, k, "cobertura_accesible", sem) / vec(datos, f"{k}_ctrl",
                                                                "cobertura_accesible", sem) - 1
        mm, lo, hi = ic95(c_rel)
        L.append(f"  costo relativo en cobertura accesible: {100*mm:+.4f} % "
                 f"[{100*lo:+.4f}, {100*hi:+.4f}]")
        L.append("")

    L.append("CRITERIO DE PARADA POR FALLA REAL (sumas sobre los 100 episodios)")
    for k in escenarios:
        L.append(f"  {k}: " + "; ".join(
            f"{e} {int(vec(datos, k, c, sem).sum())}" for c, e in (
                ("contactos_obst_eventos", "contactos obst."),
                ("escape_agotados", "escapes agotados"),
                ("qp_fallbacks", "fallbacks QP"),
                ("escape_infactibles_junto_obst", "infactibles junto a obst."))))
    L.append("INDICADOR ADELANTADO (intervención > 0,5; calibrado en Webots, fuera de")
    L.append("su dominio en Python — se reporta, no detiene)")
    for k in escenarios:
        f = vec(datos, k, "cbf_frac_interv", sem)
        L.append(f"  {k}: media {np.mean(f):.8f}; episodios > 0,5: "
                 f"{int(np.sum(f > 0.5))}/100; máx. {np.max(f):.8f}")
    L.append("")

    # ── Mecanismo: costo directo (obstáculo) vs indirecto (pared) ─────────
    L.append("MECANISMO — intervención directa (h mín. = obstáculo) vs indirecta")
    L.append("(h mín. = pared), pareada Sk − Sk_ctrl. Área libre del punto de mira")
    L.append("(h ≥ 0) según registro_O.txt; sin obstáculos 6,969600 m².")
    L.append("Contraste central/periférico LIMPIO: S1 (1 central) vs S2 (2 a 0,75 m")
    L.append("de las paredes). S3 mezcla 1 central + 4 junto a las esquinas.")
    L.append(f"  {'':3s} {'Δ total':>11s} {'Δ obst.':>11s} {'Δ pared':>11s} "
             f"{'indirecta':>10s} {'ΔA libre':>9s} {'Δint/m²':>9s} "
             f"{'Δescapes':>9s} {'% junto obst':>12s} {'Δ periferia':>24s}")
    for k in escenarios:
        def dd(m: str) -> np.ndarray:
            return vec(datos, k, m, sem) - vec(datos, f"{k}_ctrl", m, sem)
        dt, do, dp_ = (float(np.mean(dd(m))) for m in (
            "cbf_frac_interv", "cbf_frac_hmin_obst", "cbf_frac_hmin_pared"))
        de = float(np.mean(dd("escape_n")))
        eo = float(np.mean(vec(datos, k, "escape_n_junto_obst", sem)))
        mp, lop, hip = ic95(dd("frac_agente_paso_periferia_050"))
        da = AREA_LIBRE["S0"] - AREA_LIBRE[k]
        L.append(f"  {k:3s} {dt:+11.6f} {do:+11.6f} {dp_:+11.6f} "
                 f"{dp_ / dt:10.4f} {da:9.4f} {dt / da:+9.5f} {de:+9.3f} "
                 f"{(100 * eo / de) if de > 0 else float('nan'):11.2f}% "
                 f"{mp:+.5f}[{lop:+.4f},{hip:+.4f}]{sig(lop, hip)}")
    L.append("  indirecta = Δ pared / Δ total. % junto obst = escapes con obstáculo")
    L.append("  activo al disparar / Δ escapes. Δ periferia = cambio de la fracción de")
    L.append("  agente-paso con el centro a < 0,5 m de una pared (anillo de 5 m²).")
    L.append("")
    L.append("SEGURIDAD — totales sobre los 100 episodios de cada escenario")
    for k in escenarios:
        L.append(f"  {k}: contactos con obstáculo {int(vec(datos, k, 'contactos_obst_eventos', sem).sum())}"
                 f" eventos; colisiones <0,15 m {int(vec(datos, k, 'colisiones_015', sem).sum())};"
                 f" contacto con pared {int(vec(datos, k, 'contacto_pared', sem).sum())};"
                 f" fallbacks del QP {int(vec(datos, k, 'qp_fallbacks', sem).sum())}")
    texto = "\n".join(L) + "\n"
    RUTA_RES.write_bytes(texto.encode("utf-8"))
    print(texto)

    # ── Figuras ───────────────────────────────────────────────────────────
    DIR_FIG.mkdir(parents=True, exist_ok=True)
    fmt = FuncFormatter(lambda v, _: f"{v:g}".replace(".", ","))
    etiquetas = ["S0"] + [e for k in escenarios for e in (f"{k}\ncontrol", k)]
    fig, ax = plt.subplots(figsize=(6.8, 4.2))
    base = np.zeros(len(conds))
    for m, color, nom in (("cbf_frac_hmin_pared", "#1f77b4", "pared"),
                          ("cbf_frac_hmin_robot", "#ff7f0e", "robot-robot"),
                          ("cbf_frac_hmin_obst", "#2ca02c", "obstáculo")):
        v = np.array([np.mean(vec(datos, c, m, sem)) for c in conds])
        ax.bar(range(len(conds)), v, bottom=base, color=color, label=nom)
        base += v
    ax.axhline(0.5, color="#d62728", linestyle="--", linewidth=1.0,
               label="umbral operativo 0,5")
    ax.set_xticks(range(len(conds)))
    ax.set_xticklabels(etiquetas, fontsize=9)
    ax.set_ylabel("Fracción de agente-decisión intervenida\n(por barrera de h mínimo)",
                  fontsize=10)
    ax.yaxis.set_major_formatter(fmt)
    ax.grid(alpha=0.3, axis="y", linestyle="--", linewidth=0.5)
    ax.legend(fontsize=8, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(DIR_FIG / "fig_obstaculos_intervencion.png", dpi=DPI_FIG,
                bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.0, 3.8))
    for j, (m, color, nom) in enumerate(
            (("cobertura_accesible", "#333333", "celdas accesibles"),
             ("cobertura_sin_enmascarar", "#999999", "cuadrícula completa"))):
        for i, k in enumerate(escenarios):
            d = vec(datos, k, m, sem) - vec(datos, f"{k}_ctrl", m, sem)
            mm, lo, hi = ic95(d)
            ax.errorbar([i + (j - 0.5) * 0.2], [mm], yerr=[[mm - lo], [hi - mm]],
                        fmt="o", color=color, capsize=3, label=nom if i == 0 else None)
    ax.axhline(0.0, color="grey", linewidth=0.8)
    ax.set_xticks(range(len(escenarios)))
    ax.set_xticklabels(escenarios)
    ax.set_xlim(-0.6, len(escenarios) - 0.4)
    ax.set_xlabel("Escenario", fontsize=10)
    ax.set_ylabel("Δ cobertura AoI pareada\n(con obstáculos − control), IC95", fontsize=10)
    ax.yaxis.set_major_formatter(fmt)
    ax.grid(alpha=0.3, axis="y", linestyle="--", linewidth=0.5)
    ax.legend(fontsize=8, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(DIR_FIG / "fig_obstaculos_costo.png", dpi=DPI_FIG, bbox_inches="tight")
    plt.close(fig)
    print(f"Figuras → {DIR_FIG}")


if __name__ == "__main__":
    main()
