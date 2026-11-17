"""
analizar_experimento_N.py
=========================
Análisis del Experimento N (arena 2,7 vs 3,0) a partir de
`resultados/experimento_N_completo.csv`. No corre episodios.

Qué produce
-----------
  resultados/resumen_experimento_N.txt
  figuras/fig_arena_densidad_cobertura.png   (cobertura vs densidad)
  figuras/fig_arena_residuos.png             (residuo sobre la predicción)

Estadística
-----------
Todas las diferencias son PAREADAS POR SEMILLA (mismas 100 semillas del
protocolo en todas las celdas). IC95 = media ± 1,96·EE, la misma convención
de los Exp C–K.

Predicción por densidad
-----------------------
5 agentes en W=2,7 tienen la densidad de n_eq = 5·9/7,29 = 6,17284 agentes en
W=3,0 (nominal; 6,36423 con el área libre del punto de mira). Para cada semilla
se predice la métrica a 2,7 interpolando entre las celdas W=3,0 con n=6 y n=7
de la MISMA semilla (lineal), y como sensibilidad con el polinomio de Lagrange
por n=5,6,7. Residuo = observado(2,7) − predicho. Si el IC95 del residuo
excluye el cero, hay un efecto que la densidad no explica.

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
RUTA_CSV: Path = _CARPETA / "resultados" / "experimento_N_completo.csv"
RUTA_RESUMEN: Path = _CARPETA / "resultados" / "resumen_experimento_N.txt"
DIR_FIG: Path = _CARPETA / "figuras"
RUTA_CSV_EXP_I: Path = (_CARPETA.parent / "expI_escalabilidad" / "resultados"
                        / "experimento_I_completo.csv")
RUTA_CSV_FACTORIAL: Path = (_CARPETA.parent / "tesis_v2_sanidad" / "resultados"
                            / "verificacion_cbf_python.csv")
DPI_FIG: int = 300

N_EQ_NOMINAL:  float = 5.0 * 9.0 / 7.29
N_EQ_EFECTIVA: float = 5.0 * (3.0 - 0.36) ** 2 / (2.7 - 0.36) ** 2

METRICAS: Tuple[Tuple[str, str], ...] = (
    ("cobertura_aoi_final",        "cobertura AoI final"),
    ("cobertura_por_agente",       "cobertura por agente"),
    ("colisiones_015",             "pares en colisión <0,15 m"),
    ("colisiones_022",             "pares en colisión <0,22 m"),
    ("frac_agente_paso_banda_018", "frac. agente-paso centro <0,18 m de pared"),
    ("frac_pasos_agente_recorte",  "frac. agente-paso recortado (bloq.)"),
    ("reflexiones_total",          "reflexiones por episodio (refl.)"),
    ("d_min_pared_centro",         "d_min centro→pared [m]"),
    ("violaciones_margen",         "agente-eps con centro <0,18 m"),
    ("contacto_pared",             "agente-eps con centro <0,075 m"),
    ("cbf_frac_interv",            "frac. intervención del filtro"),
    ("cbf_frac_interv_pared_hmin", "  … atribuida a pared (h mín.)"),
    ("cbf_frac_interv_robot_hmin", "  … atribuida a robot (h mín.)"),
    ("cbf_frac_ligante_pared",     "  … con pared ligante en el óptimo"),
    ("cbf_frac_ligante_robot",     "  … con robot ligante en el óptimo"),
    ("cbf_magnitud_media",         "magnitud media de la modificación"),
    ("qp_fallbacks",               "fallbacks del QP por episodio"),
    ("escape_n",                   "activaciones del escape por episodio"),
    ("escape_frac_ciclo",          "frac. de ciclo en escape"),
    ("escape_infactibles",         "escapes infactibles por episodio"),
    ("escape_agotados",            "escapes agotados por episodio"),
    ("frac_embedding_activo",      "frac. agente-decisión con vecino visible"),
    ("dist_media_agentes",         "distancia media entre agentes [m]"),
    ("uso_grid_fallback",          "episodios con sorteo de respaldo"),
)
METRICAS_PREDICCION: Tuple[str, ...] = (
    "cobertura_aoi_final", "colisiones_015_por_par", "colisiones_022_por_par",
    "frac_agente_paso_banda_018", "cbf_frac_interv",
    "cbf_frac_interv_pared_hmin", "cbf_frac_interv_robot_hmin",
    "escape_n_por_agente", "violaciones_margen_por_agente",
    "frac_embedding_activo",
)


# =============================================================================
# CARGA Y UTILIDADES
# =============================================================================

def cargar() -> Dict[str, Dict[int, Dict[str, float]]]:
    """datos[condicion][seed_ep][metrica] = valor (float)."""
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


def vec(datos, cond: str, met: str, sem: List[int]) -> np.ndarray:
    """
    Vector de la métrica en el orden de `sem`.

    Métricas derivadas (necesarias para la predicción por densidad, porque
    los conteos crudos crecen con n y no sólo con la densidad):
      `<m>_por_par`    : m / (n·(n−1)/2)   — colisiones, pares únicos.
      `<m>_por_agente` : m / n             — conteos sumados sobre agentes.
    """
    if met.endswith("_por_par"):
        base = met[: -len("_por_par")]
        return np.array([datos[cond][s][base]
                         / (datos[cond][s]["n"] * (datos[cond][s]["n"] - 1) / 2)
                         for s in sem], dtype=np.float64)
    if met.endswith("_por_agente") and met != "cobertura_por_agente":
        base = met[: -len("_por_agente")]
        return np.array([datos[cond][s][base] / datos[cond][s]["n"]
                         for s in sem], dtype=np.float64)
    return np.array([datos[cond][s][met] for s in sem], dtype=np.float64)


def ic95(x: np.ndarray) -> Tuple[float, float, float, float]:
    """Media, desviación (ddof=1), IC95 inferior y superior."""
    n = len(x)
    m = float(np.mean(x))
    sd = float(np.std(x, ddof=1)) if n > 1 else 0.0
    ee = sd / math.sqrt(n)
    return m, sd, m - 1.96 * ee, m + 1.96 * ee


def sig(lo: float, hi: float) -> str:
    """Marca si el IC95 excluye el cero."""
    return "*" if (lo > 0 and hi > 0) or (lo < 0 and hi < 0) else " "


def lagrange(n_eval: float, xs: Tuple[float, ...], ys: List[np.ndarray]) -> np.ndarray:
    """Polinomio de Lagrange por (xs, ys) evaluado en n_eval, por semilla."""
    total = np.zeros_like(ys[0])
    for i, (xi, yi) in enumerate(zip(xs, ys)):
        peso = 1.0
        for j, xj in enumerate(xs):
            if j != i:
                peso *= (n_eval - xj) / (xi - xj)
        total += peso * yi
    return total


def coma(x: float, dec: int) -> str:
    """Número con separador decimal coma."""
    return f"{x:.{dec}f}".replace(".", ",")


# =============================================================================
# ANÁLISIS
# =============================================================================

def main() -> None:
    """Genera el resumen y las figuras."""
    datos = cargar()
    sem = sorted(datos["a_W30_n5"].keys())
    sem18 = sorted(datos["b2_W30_n5_puente"].keys())
    L: List[str] = []
    L.append("EXPERIMENTO N — Costo de reducir la arena de 3,0 a 2,7 m")
    L.append(f"100 semillas del protocolo (420000–420099), 500 pasos, "
             f"deterministic=True, domain_rand=False, comm_radius=1,0.")
    L.append("(a) política aislada: modelo_PRIMERO, reflexión, sin filtro ni escape.")
    L.append("(b) configuración final: modelo_sanidad, bloqueante, CBF + escape de")
    L.append("    TRES términos (como el coordinador desplegado).")
    L.append("Diferencias PAREADAS por semilla; IC95 = media ± 1,96·EE; "
             "* = IC95 excluye 0.")
    L.append("=" * 78)
    L.append("")

    # ── Controles ──────────────────────────────────────────────────────────
    L.append("VERIFICACIÓN DE CONTROL")
    m_a = float(np.mean(vec(datos, "a_W30_n5", "cobertura_aoi_final", sem)))
    L.append(f"  C1 (a) W=3,0 n=5: {m_a:.10f} vs oficial 0,681291 "
             f"|Δ|={abs(m_a - 0.681291):.2e}")
    exp_i: Dict[Tuple[int, int], float] = {}
    with open(RUTA_CSV_EXP_I, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["condicion"] == "reflexion":
                exp_i[(int(r["n"]), int(r["seed_ep"]))] = float(
                    r["cobertura_aoi_final"])
    for n_c, cond in ((5, "a_W30_n5"), (7, "a_W30_n7")):
        iguales = sum(
            round(datos[cond][s]["cobertura_aoi_final"], 6) == exp_i[(n_c, s)]
            for s in sem)
        L.append(f"  cruce por semilla (a) n={n_c} vs Exp I: {iguales}/100 "
                 f"idénticas a 6 dec.")
        if iguales != 100:
            L.append("  PARAR: el cruce no reproduce.")
            RUTA_RESUMEN.write_bytes("\n".join(L).encode("utf-8"))
            raise SystemExit(1)
    m_b2 = float(np.mean([round(x, 6) for x in
                          vec(datos, "b2_W30_n5_puente", "cobertura_aoi_final", sem18)]))
    L.append(f"  C2 (b) dos términos, 18 sem.: {m_b2:.10f} vs factorial (d) "
             f"0,5779647222")
    L.append("")

    # ── Geometría ─────────────────────────────────────────────────────────
    L.append("GEOMETRÍA (calculada a priori)")
    L.append("                         W=3,0          W=2,7")
    L.append("  área [m²]              9,000000       7,290000")
    L.append("  área libre punto mira  6,969600       5,475600   (W−0,36)²")
    L.append("  densidad nominal       0,55555556     0,68587106  (+23,46 %)")
    L.append("  densidad efectiva      0,71740129     0,91314194  (+27,28 %)")
    L.append("  celda AoI (64×64) [m]  0,04687500     0,04218750")
    L.append("  huella / área          0,00785398     0,00969627")
    L.append(f"  n equivalente a W=3,0: nominal {N_EQ_NOMINAL:.6f}, "
             f"efectiva {N_EQ_EFECTIVA:.6f}")
    L.append("")

    # ── Tabla por condición ───────────────────────────────────────────────
    conds_a = ["a_W30_n5", "a_W27_n5", "a_W30_n6", "a_W30_n7"]
    conds_b = ["b3_W30_n5", "b3_W27_n5", "b3_W30_n6", "b3_W30_n7"]
    for titulo, conds in (("(a) POLÍTICA AISLADA, reflexión", conds_a),
                          ("(b) CONFIGURACIÓN FINAL, bloqueante", conds_b)):
        L.append(f"TABLA — {titulo} (media sobre 100 episodios)")
        L.append(f"  {'métrica':44s}" + "".join(f"{c:>15s}" for c in conds))
        for met, etiq in METRICAS:
            vals = [float(np.mean(vec(datos, c, met, sem))) for c in conds]
            L.append(f"  {etiq:44s}" + "".join(f"{v:15.8f}" for v in vals))
        dm = [float(np.min(vec(datos, c, "d_min_pared_centro", sem))) for c in conds]
        L.append(f"  {'d_min centro→pared, mínimo global [m]':44s}"
                 + "".join(f"{v:15.8f}" for v in dm))
        L.append("")

    # ── Comparación pareada 2,7 − 3,0 (n=5) ───────────────────────────────
    for titulo, c30, c27 in (("(a)", "a_W30_n5", "a_W27_n5"),
                             ("(b)", "b3_W30_n5", "b3_W27_n5")):
        L.append(f"COMPARACIÓN PAREADA {titulo}: W=2,7 − W=3,0, n=5, 100 semillas")
        L.append(f"  {'métrica':44s} {'Δ':>13s} {'IC95':>30s}  {'>0':>4s} {'<0':>4s}")
        for met, etiq in METRICAS:
            d = vec(datos, c27, met, sem) - vec(datos, c30, met, sem)
            m, _, lo, hi = ic95(d)
            L.append(f"  {etiq:44s} {m:+13.8f} [{lo:+13.8f}, {hi:+13.8f}]{sig(lo, hi)}"
                     f" {int(np.sum(d > 0)):4d} {int(np.sum(d < 0)):4d}")
        L.append("")

    # ── Predicción por densidad ───────────────────────────────────────────
    L.append("CONTRASTE CONTRA LA PREDICCIÓN POR DENSIDAD")
    L.append("  Predicción por semilla desde las celdas W=3,0 de la MISMA semilla.")
    L.append("  lin: interpolación lineal n=6→7 en n_eq nominal (6,172840)")
    L.append("  lag: Lagrange por n=5,6,7 en n_eq nominal (sensibilidad)")
    L.append("  efe: interpolación lineal n=6→7 en n_eq efectiva (6,364234)")
    L.append("  Residuo = observado(2,7) − predicho. * = IC95 excluye 0.")
    residuos: Dict[str, Dict[str, Tuple[float, float, float]]] = {}
    for cfg, pref in (("a", "a_W"), ("b", "b3_W")):
        L.append(f"  --- configuración ({cfg}) ---")
        L.append(f"  {'métrica':30s} {'obs 2,7':>12s} {'pred lin':>12s} "
                 f"{'residuo lin':>12s} {'IC95':>28s}  {'res lag':>11s} {'res efe':>11s}")
        residuos[cfg] = {}
        for met in METRICAS_PREDICCION:
            y5 = vec(datos, f"{pref}30_n5", met, sem)
            y6 = vec(datos, f"{pref}30_n6", met, sem)
            y7 = vec(datos, f"{pref}30_n7", met, sem)
            obs = vec(datos, f"{pref}27_n5", met, sem)
            p_lin = y6 + (N_EQ_NOMINAL - 6.0) * (y7 - y6)
            p_lag = lagrange(N_EQ_NOMINAL, (5.0, 6.0, 7.0), [y5, y6, y7])
            p_efe = y6 + (N_EQ_EFECTIVA - 6.0) * (y7 - y6)
            m, _, lo, hi = ic95(obs - p_lin)
            ml, _, lol, hil = ic95(obs - p_lag)
            me, _, loe, hie = ic95(obs - p_efe)
            residuos[cfg][met] = (m, lo, hi)
            L.append(f"  {met[:30]:30s} {np.mean(obs):12.8f} {np.mean(p_lin):12.8f} "
                     f"{m:+12.8f} [{lo:+12.8f},{hi:+12.8f}]{sig(lo, hi)} "
                     f"{ml:+10.6f}{sig(lol, hil)} {me:+10.6f}{sig(loe, hie)}")
    L.append("")

    # ── Brazo de densidad de la configuración de tres capas ───────────────
    L.append("BRAZO DE DENSIDAD — configuración final a W=3,0 con n=5,6,7")
    L.append("  (la configuración de tres capas nunca se había medido a otro cardinal)")
    L.append(f"  {'n':>3s} {'cob. total':>12s} {'cob./agente':>12s} {'col015':>8s} "
             f"{'col022':>8s} {'CBF frac':>10s} {'escapes':>9s} {'fallback':>9s} "
             f"{'banda018':>10s}")
    for n in (5, 6, 7):
        c = f"b3_W30_n{n}"
        L.append(f"  {n:3d} "
                 f"{np.mean(vec(datos, c, 'cobertura_aoi_final', sem)):12.8f} "
                 f"{np.mean(vec(datos, c, 'cobertura_por_agente', sem)):12.8f} "
                 f"{np.mean(vec(datos, c, 'colisiones_015', sem)):8.3f} "
                 f"{np.mean(vec(datos, c, 'colisiones_022', sem)):8.3f} "
                 f"{np.mean(vec(datos, c, 'cbf_frac_interv', sem)):10.6f} "
                 f"{np.mean(vec(datos, c, 'escape_n', sem)):9.3f} "
                 f"{np.mean(vec(datos, c, 'qp_fallbacks', sem)):9.3f} "
                 f"{np.mean(vec(datos, c, 'frac_agente_paso_banda_018', sem)):10.6f}")
    L.append("  Política aislada (a) a W=3,0, mismo formato:")
    for n in (5, 6, 7):
        c = f"a_W30_n{n}"
        L.append(f"  {n:3d} "
                 f"{np.mean(vec(datos, c, 'cobertura_aoi_final', sem)):12.8f} "
                 f"{np.mean(vec(datos, c, 'cobertura_por_agente', sem)):12.8f} "
                 f"{np.mean(vec(datos, c, 'colisiones_015', sem)):8.3f} "
                 f"{np.mean(vec(datos, c, 'colisiones_022', sem)):8.3f}")
    L.append("")

    # ── Puente dos vs tres términos ───────────────────────────────────────
    L.append("PUENTE — detección del escape: TRES términos (desplegado) vs DOS")
    L.append("  (factorial 2×2), configuración final, W=3,0, n=5, 18 semillas")
    L.append("  420000–420017. Δ = tres − dos, pareado.")
    for met, etiq in (("cobertura_aoi_final", "cobertura"),
                      ("escape_n", "activaciones del escape"),
                      ("escape_frac_ciclo", "frac. de ciclo en escape"),
                      ("cbf_frac_interv", "frac. intervención filtro"),
                      ("colisiones_015", "col. <0,15 m"),
                      ("colisiones_022", "col. <0,22 m"),
                      ("violaciones_margen", "violaciones de margen"),
                      ("d_min_pared_centro", "d_min centro→pared")):
        x3 = vec(datos, "b3_W30_n5", met, sem18)
        x2 = vec(datos, "b2_W30_n5_puente", met, sem18)
        m, _, lo, hi = ic95(x3 - x2)
        L.append(f"  {etiq:28s} tres={np.mean(x3):12.8f} dos={np.mean(x2):12.8f} "
                 f"Δ={m:+.8f} [{lo:+.8f}, {hi:+.8f}]{sig(lo, hi)} "
                 f"distintas: {int(np.sum(x3 != x2))}/18")
    ref_a: Dict[int, float] = {}
    with open(RUTA_CSV_FACTORIAL, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["condicion"] == "a_sin_cbf_sin_esc":
                ref_a[int(r["semilla"])] = float(r["cobertura_aoi_final"])
    a_fact = np.array([ref_a[s] for s in sem18])
    for etiq, cond in (("dos (factorial original)", "b2_W30_n5_puente"),
                       ("tres (desplegado)", "b3_W30_n5")):
        m, _, lo, hi = ic95(vec(datos, cond, "cobertura_aoi_final", sem18) - a_fact)
        L.append(f"  efecto conjunto (d − a) con escape de {etiq:26s}: "
                 f"{m:+.8f} [{lo:+.8f}, {hi:+.8f}]{sig(lo, hi)}")
    L.append("")

    # ── Criterio operativo ────────────────────────────────────────────────
    L.append("CRITERIO OPERATIVO (fracción de intervención > 0,5 ⇒ atascos altos)")
    for c in conds_b:
        f = vec(datos, c, "cbf_frac_interv", sem)
        L.append(f"  {c:12s} media {np.mean(f):.8f}  máx. episodio {np.max(f):.8f}"
                 f"  episodios > 0,5: {int(np.sum(f > 0.5))}/100")
    L.append("")

    resumen = "\n".join(L) + "\n"
    RUTA_RESUMEN.write_bytes(resumen.encode("utf-8"))
    print(resumen)

    # =========================================================================
    # FIGURAS (sin título, 300 dpi, es-ES, coma decimal)
    # =========================================================================
    DIR_FIG.mkdir(parents=True, exist_ok=True)
    fmt = FuncFormatter(lambda v, _: f"{v:g}".replace(".", ","))

    # Figura 1 — cobertura vs densidad nominal.
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    for cfg, pref, color, etiq in (
            ("a", "a_W", "#1f77b4", "(a) política aislada, reflexión"),
            ("b", "b3_W", "#d62728", "(b) configuración final, bloqueante")):
        xs, ms, es = [], [], []
        for n in (5, 6, 7):
            y = vec(datos, f"{pref}30_n{n}", "cobertura_aoi_final", sem)
            m, sd, lo, hi = ic95(y)
            xs.append(n / 9.0); ms.append(m); es.append(m - lo)
        ax.errorbar(xs, ms, yerr=es, color=color, marker="o", capsize=3,
                    label=f"{etiq}: W=3,0, n=5,6,7")
        y = vec(datos, f"{pref}27_n5", "cobertura_aoi_final", sem)
        m, sd, lo, hi = ic95(y)
        ax.errorbar([5 / 7.29], [m], yerr=[m - lo], color=color, marker="*",
                    markersize=13, capsize=3, linestyle="none",
                    label=f"{etiq}: W=2,7, n=5")
    ax.set_xlabel("Densidad nominal de agentes [agentes/m²]", fontsize=11)
    ax.set_ylabel("Cobertura AoI final (media, IC95)", fontsize=11)
    ax.xaxis.set_major_formatter(fmt); ax.yaxis.set_major_formatter(fmt)
    ax.grid(alpha=0.3, linestyle="--", linewidth=0.5)
    ax.legend(fontsize=8, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(DIR_FIG / "fig_arena_densidad_cobertura.png", dpi=DPI_FIG,
                bbox_inches="tight")
    plt.close(fig)

    # Figura 2 — residuos sobre la predicción por densidad (escala relativa).
    etiquetas = {
        "cobertura_aoi_final": "Cobertura AoI",
        "colisiones_015_por_par": "Colisiones <0,15 m por par",
        "colisiones_022_por_par": "Colisiones <0,22 m por par",
        "frac_agente_paso_banda_018": "Tiempo en banda <0,18 m",
        "cbf_frac_interv": "Intervención del filtro",
        "cbf_frac_interv_pared_hmin": "  … por pared",
        "cbf_frac_interv_robot_hmin": "  … por robot",
        "escape_n_por_agente": "Escapes por agente",
        "violaciones_margen_por_agente": "Violación de margen por agente",
        "frac_embedding_activo": "Vecino visible",
    }
    # Cada panel lleva SUS métricas y SUS etiquetas (sin eje y compartido:
    # con sharey las etiquetas del segundo panel pisaban las del primero).
    solo_b = ("cbf_frac_interv", "cbf_frac_interv_pared_hmin",
              "cbf_frac_interv_robot_hmin", "escape_n_por_agente",
              "violaciones_margen_por_agente")
    mets_a = [m for m in METRICAS_PREDICCION if m not in solo_b]
    mets_b = [m for m in METRICAS_PREDICCION if not m.startswith("colisiones")]
    fig, axs = plt.subplots(1, 2, figsize=(10.4, 4.4))
    for ax, cfg, pref, titulo, mets in (
            (axs[0], "a", "a_W", "(a) política aislada", mets_a),
            (axs[1], "b", "b3_W", "(b) configuración final", mets_b)):
        for k, met in enumerate(mets):
            y6 = vec(datos, f"{pref}30_n6", met, sem)
            y7 = vec(datos, f"{pref}30_n7", met, sem)
            pred = y6 + (N_EQ_NOMINAL - 6.0) * (y7 - y6)
            base = abs(float(np.mean(pred))) or 1.0
            m, _, lo, hi = ic95((vec(datos, f"{pref}27_n5", met, sem) - pred) / base)
            ax.errorbar([100 * m], [k], xerr=[[100 * (m - lo)], [100 * (hi - m)]],
                        fmt="o", color="#333333", capsize=3)
        ax.set_yticks(range(len(mets)))
        ax.set_yticklabels([etiquetas[m] for m in mets], fontsize=9)
        ax.axvline(0.0, color="grey", linewidth=0.8)
        ax.set_xlabel(f"Residuo sobre la predicción por densidad [%]\n{titulo}",
                      fontsize=10)
        ax.xaxis.set_major_formatter(fmt)
        ax.grid(alpha=0.3, axis="x", linestyle="--", linewidth=0.5)
        ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(DIR_FIG / "fig_arena_residuos.png", dpi=DPI_FIG,
                bbox_inches="tight")
    plt.close(fig)
    print(f"Figuras → {DIR_FIG}")


if __name__ == "__main__":
    main()
