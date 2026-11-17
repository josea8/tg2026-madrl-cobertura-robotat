"""
regenerar_figuras_tesis.py
==========================
Regenera, a partir de los datos ya guardados, las siete figuras PNG de la tesis
que tenían la cobertura como fracción o comas decimales. No corre ningún
experimento: lee los CSV y JSON de cada carpeta de resultados.

Cambios respecto de las figuras originales:
  - cobertura en porcentaje y diferencias en puntos porcentuales (pp);
  - punto decimal;
  - sin títulos de trabajo dentro de la figura;
  - tamaño igual al ancho con que se imprimen en la tesis, para que la letra
    quede legible (unos 9 pt);
  - paleta de la tesis (serieA, serieB, serieC).

Salida: figuras_tesis/*.png en la raíz del repositorio (mismos nombres que en la tesis).
Requiere descomprimir antes los datos de datos_crudos/ dentro de codigo/.
"""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAIZ = Path(__file__).resolve().parents[1]  # carpeta codigo/ del repositorio
EXP = RAIZ / "primerafase_webots" / "experimentos"
SALIDA = Path(__file__).resolve().parents[2] / "figuras_tesis"
SALIDA.mkdir(exist_ok=True)

SERIE_A, SERIE_B, SERIE_C, GRIS = "#2A78D6", "#EB6834", "#1BAF7A", "#6B6B6B"
ANCHO_TEXTO = 6.0  # pulgadas
DPI = 300

plt.rcParams.update({
    "font.size": 9, "axes.labelsize": 9, "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5, "legend.fontsize": 8, "axes.spines.top": False,
    "axes.spines.right": False, "axes.formatter.use_locale": False,
})


def tam(fraccion_texto: float, razon: float):
    """Tamaño de figura igual al impreso: ancho = fracción del texto."""
    ancho = fraccion_texto * ANCHO_TEXTO
    return (ancho, ancho / razon)


def cargar_modulo(ruta: Path, nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def guardar(fig, nombre: str) -> None:
    fig.savefig(SALIDA / nombre, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print("figura →", SALIDA / nombre)


# ---------------------------------------------------------------------------
# 1. fig_resultados_CUATRO.png (Exp E, condición de reflexión)
# ---------------------------------------------------------------------------
def figura_cuatro() -> None:
    ruta = EXP / "expD_lineas_base" / "resultados" / "experimento_E_completo.csv"
    filas = list(csv.DictReader(open(ruta, encoding="utf-8")))
    orden = ("madrl", "piramidal", "heuristica", "aleatoria")
    nombres = ["MADRL\n(CTDE)", "Voronoi\n+ PSO", "Vecino más\ncercano", "Política\naleatoria"]
    colores = [SERIE_A, SERIE_C, GRIS, SERIE_B]
    cob = [[100 * float(f["cobertura_aoi_final"]) for f in filas
            if f["estrategia"] == e and f["condicion"] == "reflexion"] for e in orden]
    col = [[float(f["colisiones_015"]) for f in filas
            if f["estrategia"] == e and f["condicion"] == "reflexion"] for e in orden]
    assert all(len(c) == 100 for c in cob), [len(c) for c in cob]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=tam(0.95, 13 / 5.5))
    for ax, datos, etiqueta in ((a1, cob, "Cobertura AoI final [%]"),
                                (a2, col, "Pares en colisión por episodio")):
        bp = ax.boxplot(datos, tick_labels=nombres, patch_artist=True, widths=0.55,
                        medianprops={"color": "black", "linewidth": 1.0},
                        flierprops={"markersize": 3})
        for caja, c in zip(bp["boxes"], colores):
            caja.set_facecolor(c); caja.set_alpha(0.75)
        ax.set_ylabel(etiqueta)
        ax.tick_params(axis="x", labelsize=7)
        ax.grid(True, alpha=0.3, axis="y")
    a1.set_ylim(0, 80)
    fig.tight_layout()
    guardar(fig, "fig_resultados_CUATRO.png")
    print("  medias cobertura [%]:", [round(float(np.mean(c)), 2) for c in cob])


# ---------------------------------------------------------------------------
# 2. fig_mapa_espacial.png (Exp K)
# ---------------------------------------------------------------------------
def figura_mapa() -> None:
    ruta = EXP / "expK_mapa_espacial" / "resultados" / "expK_mapas.csv"
    filas = list(csv.DictReader(open(ruta, encoding="utf-8")))
    orden = ("madrl", "piramidal", "heuristica", "aleatoria")
    titulos = ["MADRL\n(CTDE)", "Voronoi\n+ PSO", "Vecino\nmás cercano", "Política\naleatoria"]
    R = 1 + max(int(f["ix"]) for f in filas)
    mapas = {}
    for e in orden:
        m = np.full((R, R), np.nan)
        for f in filas:
            if f["estrategia"] == e:
                m[int(f["ix"]), int(f["iy"])] = 100 * (1.0 - float(f["aoi_final"]))
        assert not np.isnan(m).any()
        mapas[e] = m
    vmax = max(float(np.max(m)) for m in mapas.values())
    W, anillo = 3.0, 0.30
    fig, ejes = plt.subplots(1, 4, figsize=(0.98 * ANCHO_TEXTO, 0.98 * ANCHO_TEXTO / 3.6))
    im = None
    for ax, e, t in zip(ejes, orden, titulos):
        im = ax.imshow(mapas[e].T, origin="lower", cmap="viridis", vmin=0, vmax=vmax,
                       extent=(0, W, 0, W), interpolation="nearest")
        ax.set_title(t, fontsize=9)
        ax.set_xlabel("$x$ [m]")
        ax.set_xticks([0.5, 1.5, 2.5]); ax.set_yticks([0.5, 1.5, 2.5])
        ax.plot([anillo, W - anillo, W - anillo, anillo, anillo],
                [anillo, anillo, W - anillo, W - anillo, anillo],
                color="white", ls="--", lw=0.9, alpha=0.9)
        ax.spines["top"].set_visible(True); ax.spines["right"].set_visible(True)
    ejes[0].set_ylabel("$y$ [m]")
    for ax in ejes[1:]:
        ax.set_yticklabels([])
    fig.subplots_adjust(right=0.89, wspace=0.08)
    cax = fig.add_axes([0.905, 0.2, 0.012, 0.62])
    cb = fig.colorbar(im, cax=cax)
    cb.set_label("Cobertura por celda [%]")
    guardar(fig, "fig_mapa_espacial.png")


# ---------------------------------------------------------------------------
# 3. curvas_cobertura_J.png (estudio J)
# ---------------------------------------------------------------------------
def figura_curvas_j() -> None:
    base = RAIZ / "fase_preliminar2" / "experimento_J" / "resultados" / "estudio"
    curvas = []
    for ruta in sorted(base.glob("cfg_*/semilla_*/resultado_semilla.json")):
        d = json.loads(ruta.read_text(encoding="utf-8"))
        curvas.append(d["curva"])
    assert curvas, "no se encontraron curvas del estudio J"
    referencia = 68.13
    fig, ax = plt.subplots(figsize=tam(0.95, 10 / 6))
    for c in curvas:
        pasos = [p["pasos"] / 1000 for p in c]
        cob = [100 * p["cobertura"] for p in c]
        ax.plot(pasos, cob, marker="o", ms=2.2, lw=0.8, alpha=0.6)
    ax.axhline(referencia, ls="--", c="black", lw=1.0,
               label=f"configuración de referencia ({referencia:.2f} %)")
    ax.axvline(100, ls=":", c=GRIS, lw=1.0, label="presupuesto del estudio original")
    ax.set_xlabel("Pasos de entrenamiento [miles]")
    ax.set_ylabel("Cobertura AoI [%]")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2, frameon=False)
    fig.tight_layout()
    guardar(fig, "curvas_cobertura_J.png")
    print(f"  curvas: {len(curvas)}")


# ---------------------------------------------------------------------------
# 4 y 5. fig_arena_densidad_cobertura.png y fig_arena_residuos.png (Exp N)
# ---------------------------------------------------------------------------
def figuras_arena() -> None:
    N = cargar_modulo(EXP / "expN_arena" / "analizar_experimento_N.py", "exp_n")
    datos = N.cargar()
    sem = sorted(datos["a_W30_n5"].keys())
    fig, ax = plt.subplots(figsize=tam(0.72, 6.4 / 4.4))
    for pref, color, etiq in (("a_W", SERIE_A, "(a) política aislada, reflexión"),
                              ("b3_W", SERIE_B, "(b) configuración final, bloqueante")):
        xs, ms, es = [], [], []
        for n in (5, 6, 7):
            y = 100 * N.vec(datos, f"{pref}30_n{n}", "cobertura_aoi_final", sem)
            m, sd, lo, hi = N.ic95(y)
            xs.append(n / 9.0); ms.append(m); es.append(m - lo)
        ax.errorbar(xs, ms, yerr=es, color=color, marker="o", ms=4, capsize=3,
                    label=etiq)
        y = 100 * N.vec(datos, f"{pref}27_n5", "cobertura_aoi_final", sem)
        m, sd, lo, hi = N.ic95(y)
        ax.errorbar([5 / 7.29], [m], yerr=[m - lo], color=color, marker="*", ms=10,
                    capsize=3, linestyle="none")
    ax.set_xlabel("Densidad nominal de agentes [agentes/m²]")
    ax.set_ylabel("Cobertura AoI final [%]")
    ax.grid(alpha=0.3, linestyle="--", linewidth=0.5)
    ax.plot([], [], "o", color=GRIS, ms=4, label="área de 3.0 m (5, 6 y 7 agentes)")
    ax.plot([], [], "*", color=GRIS, ms=9, label="área de 2.7 m (5 agentes)")
    ax.set_ylim(48, 78)
    ax.legend(loc="lower right", fontsize=7, framealpha=0.95)
    fig.tight_layout()
    guardar(fig, "fig_arena_densidad_cobertura.png")

    etiquetas = {
        "cobertura_aoi_final": "Cobertura AoI",
        "colisiones_015_por_par": "Colisiones < 0.15 m",
        "colisiones_022_por_par": "Colisiones < 0.22 m",
        "frac_agente_paso_banda_018": "Tiempo junto a la pared",
        "cbf_frac_interv": "Intervención del filtro",
        "cbf_frac_interv_pared_hmin": "   por pared",
        "cbf_frac_interv_robot_hmin": "   entre robots",
        "escape_n_por_agente": "Maniobras por agente",
        "violaciones_margen_por_agente": "Violaciones del margen",
        "frac_embedding_activo": "Vecino visible",
    }
    solo_b = ("cbf_frac_interv", "cbf_frac_interv_pared_hmin", "cbf_frac_interv_robot_hmin",
              "escape_n_por_agente", "violaciones_margen_por_agente")
    mets_a = [m for m in N.METRICAS_PREDICCION if m not in solo_b]
    mets_b = [m for m in N.METRICAS_PREDICCION if not m.startswith("colisiones")]
    fig, axs = plt.subplots(1, 2, figsize=tam(0.80, 10.4 / 4.4))
    for ax, pref, titulo, mets in ((axs[0], "a_W", "(a) política aislada", mets_a),
                                   (axs[1], "b3_W", "(b) configuración final", mets_b)):
        for k, met in enumerate(mets):
            y6 = N.vec(datos, f"{pref}30_n6", met, sem)
            y7 = N.vec(datos, f"{pref}30_n7", met, sem)
            pred = y6 + (N.N_EQ_NOMINAL - 6.0) * (y7 - y6)
            base = abs(float(np.mean(pred))) or 1.0
            m, _, lo, hi = N.ic95((N.vec(datos, f"{pref}27_n5", met, sem) - pred) / base)
            ax.errorbar([100 * m], [k], xerr=[[100 * (m - lo)], [100 * (hi - m)]],
                        fmt="o", ms=3.5, color="#333333", capsize=2.5)
        ax.set_yticks(range(len(mets)))
        ax.set_yticklabels([etiquetas[m] for m in mets], fontsize=8)
        ax.axvline(0.0, color="grey", linewidth=0.8)
        ax.set_xlabel("Residuo [%]")
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(3))
        ax.set_title(titulo, fontsize=9)
        ax.grid(alpha=0.3, axis="x", linestyle="--", linewidth=0.5)
        ax.invert_yaxis()
    fig.tight_layout()
    guardar(fig, "fig_arena_residuos.png")


# ---------------------------------------------------------------------------
# 6 y 7. fig_obstaculos_intervencion.png y fig_obstaculos_costo.png (Exp O)
# ---------------------------------------------------------------------------
def figuras_obstaculos() -> None:
    O = cargar_modulo(EXP / "expO_obstaculos" / "analizar_experimento_O.py", "exp_o")
    datos = O.cargar()
    sem = sorted(datos["S0"].keys())
    escenarios = [k for k in ("S1", "S2", "S3") if k in datos]
    nombres = {"S1": "Un obstáculo\ncentral", "S2": "Dos\ndescentrados", "S3": "Cinco\nperiféricos"}
    cortos = {"S1": "Central", "S2": "Descentrados", "S3": "Periféricos"}
    conds = ["S0"] + [c for k in escenarios for c in (f"{k}_ctrl", k)]
    etiq = ["sin\nobstáculos"] + [e for k in escenarios for e in ("control", "con\nobstáculos")]
    fig, ax = plt.subplots(figsize=tam(0.78, 6.8 / 4.2))
    base = np.zeros(len(conds))
    for m, color, nom in (("cbf_frac_hmin_pared", SERIE_A, "pared"),
                          ("cbf_frac_hmin_robot", SERIE_B, "entre robots"),
                          ("cbf_frac_hmin_obst", SERIE_C, "obstáculo")):
        v = np.array([np.mean(O.vec(datos, c, m, sem)) for c in conds])
        ax.bar(range(len(conds)), v, bottom=base, color=color, label=nom,
               edgecolor="white", linewidth=0.6)
        base += v
    ax.axhline(0.5, color="black", linestyle="--", linewidth=1.0, label="umbral operativo (0.5)")
    ax.set_xticks(range(len(conds)))
    ax.set_xticklabels(etiq, fontsize=7.5)
    for i, k in enumerate(escenarios):
        ax.text(1.5 + 2 * i, -0.2, cortos[k].lower(), transform=ax.get_xaxis_transform(),
                ha="center", va="top", fontsize=8.5, fontweight="bold")
    ax.set_ylabel("Fracción de decisiones\ncon intervención")
    ax.grid(alpha=0.3, axis="y", linestyle="--", linewidth=0.5)
    ax.legend(loc="upper left", framealpha=0.95, ncol=2)
    ax.set_ylim(0, 0.85)
    fig.tight_layout()
    guardar(fig, "fig_obstaculos_intervencion.png")

    fig, ax = plt.subplots(figsize=tam(0.72, 6.0 / 3.8))
    for j, (m, color, nom) in enumerate((("cobertura_accesible", "#222222", "celdas accesibles"),
                                         ("cobertura_sin_enmascarar", "#9A9A9A", "cuadrícula completa"))):
        for i, k in enumerate(escenarios):
            d = 100 * (O.vec(datos, k, m, sem) - O.vec(datos, f"{k}_ctrl", m, sem))
            mm, lo, hi = O.ic95(d)
            ax.errorbar([i + (j - 0.5) * 0.2], [mm], yerr=[[mm - lo], [hi - mm]], fmt="o",
                        ms=4, color=color, capsize=3, label=nom if i == 0 else None)
            print(f"  {k} {m}: {mm:+.2f} pp [{lo:+.2f}, {hi:+.2f}]")
    ax.axhline(0.0, color="grey", linewidth=0.8)
    ax.set_xticks(range(len(escenarios)))
    ax.set_xticklabels([nombres[k] for k in escenarios])
    ax.set_xlim(-0.6, len(escenarios) - 0.4)
    ax.set_ylabel("Diferencia de cobertura AoI [pp]")
    ax.grid(alpha=0.3, axis="y", linestyle="--", linewidth=0.5)
    ax.legend(framealpha=0.95)
    fig.tight_layout()
    guardar(fig, "fig_obstaculos_costo.png")


if __name__ == "__main__":
    figura_cuatro()
    figura_mapa()
    figura_curvas_j()
    figuras_arena()
    figuras_obstaculos()
