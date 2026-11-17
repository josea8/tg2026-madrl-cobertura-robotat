"""
figura_fase0_obstaculo.py
=========================
Figuras de la Fase 0: distancia mínima CONTINUA agente–obstáculo por caso
guionado, con τ = 0.45 s y 0.85 s. Cada punto es el MÍNIMO entre la corrida
con rampa y la sin rampa cuando existen las dos (F2); F0 y F1 sólo se
corrieron con rampa.

  diseno        tres paneles: F0 (control negativo, la barrera actual),
                F1 (la propuesta) y F2 (la que va al laboratorio).
  confirmacion  un panel: F2 sobre el conjunto de confirmación.

Lee los `resultado.json` de la carpeta de la campaña; escribe PNG a 300 dpi,
en castellano, sin título (convención de las figuras de la tesis).

    python figura_fase0_obstaculo.py <carpeta> <salida_diseno.png> <salida_confirmacion.png>

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker

# Paleta de referencia (slots 1 y 2: validan todos los pares en claro).
AZUL, NARANJA = "#2a78d6", "#eb6834"
TINTA, TINTA_2, GRILLA, CRITICO = "#0b0b0b", "#52514e", "#e4e3df", "#c62828"

PANELES_DISENO: List[Tuple[str, str]] = [
    ("control", "F0 (barrera actual, control)"),
    ("propuesta", "F1 (propuesta)"),
    ("guionada", "F2 (laboratorio)"),
]
PANELES_CONF: List[Tuple[str, str]] = [
    ("conf_guionada", "F2 — conjunto de confirmación"),
]


def cargar(carpeta: Path) -> Dict[Tuple[str, str, float], float]:
    """(bloque, caso, τ) → distancia mínima verdad (mínimo con/sin rampa)."""
    datos: Dict[Tuple[str, str, float], float] = {}
    for ruta in sorted(carpeta.glob("*/resultado.json")):
        r = json.loads(ruta.read_text(encoding="utf-8"))
        clave = (r["bloque"], r["nombre"].replace("_sinrampa", ""),
                 float(r["tau"]))
        d = float(r["verdad_d_min_obst"])
        datos[clave] = min(d, datos.get(clave, d))
    return datos


def dibujar(datos: Dict[Tuple[str, str, float], float],
            paneles: List[Tuple[str, str]], salida: Path) -> None:
    casos = sorted({k[1] for k in datos if k[0] == paneles[0][0]})
    fig, ejes = plt.subplots(1, len(paneles),
                             figsize=(3.6 * len(paneles) + 1.6, 0.36 * len(casos) + 1.6),
                             sharey=True, squeeze=False)
    y = {c: i for i, c in enumerate(reversed(casos))}
    for eje, (bloque, titulo) in zip(ejes[0], paneles):
        for tau, color, marca, dy in ((0.45, AZUL, "o", 0.17),
                                      (0.85, NARANJA, "s", -0.17)):
            pares = [(datos[(bloque, c, tau)], y[c] + dy) for c in casos
                     if (bloque, c, tau) in datos]
            eje.scatter([p[0] for p in pares], [p[1] for p in pares], s=34,
                        color=color, marker=marca, zorder=3,
                        edgecolors="white", linewidths=1.0,
                        label=f"τ = {tau:.2f} s".replace(".", ","))
        eje.axvline(0.15, color=CRITICO, lw=1.2, zorder=2)
        eje.axvline(0.185, color=TINTA_2, lw=1.0, ls=(0, (4, 3)), zorder=2)
        eje.text(0.147, len(casos) - 0.25, "0,15 colisión ", color=CRITICO,
                 fontsize=7, va="bottom", ha="right")
        eje.text(0.188, len(casos) - 0.25, " 0,185", color=TINTA_2,
                 fontsize=7, va="bottom", ha="left")
        eje.set_xlim(0.0, 0.66)
        eje.set_ylim(-0.7, len(casos) + 0.6)
        eje.set_xlabel("distancia mínima entre centros (m)", color=TINTA,
                       fontsize=8.5)
        eje.set_title(titulo, fontsize=9, color=TINTA, loc="left")
        eje.grid(axis="x", color=GRILLA, lw=0.8, zorder=0)
        for lado in ("top", "right"):
            eje.spines[lado].set_visible(False)
        for lado in ("left", "bottom"):
            eje.spines[lado].set_color(TINTA_2)
        eje.tick_params(colors=TINTA_2, labelsize=7.5)
        eje.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
            lambda v, _p: f"{v:.2f}".replace(".", ",")))
    ejes[0][0].set_yticks(list(y.values()))
    ejes[0][0].set_yticklabels([c.replace("_", " ") for c in y], fontsize=7)
    manejadores, etiquetas = ejes[0][0].get_legend_handles_labels()
    fig.legend(manejadores, etiquetas, loc="upper right", ncol=2, fontsize=8,
               frameon=False, bbox_to_anchor=(0.99, 1.0))
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(salida, dpi=300)
    print(f"figura: {salida}")


if __name__ == "__main__":
    carpeta = Path(sys.argv[1])
    datos = cargar(carpeta)
    dibujar(datos, PANELES_DISENO, Path(sys.argv[2]))
    dibujar(datos, PANELES_CONF, Path(sys.argv[3]))
