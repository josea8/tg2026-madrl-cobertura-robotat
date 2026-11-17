"""
contraste_central_periferico.py
===============================
Contraste de la PREDICCIÓN del revisor (13/sep/2026): si casi la mitad del
costo del obstáculo central es indirecto —desplaza a los agentes al perímetro y
sube la intervención de PARED—, entonces obstáculos periféricos deberían costar
menos por el canal indirecto.

Contraste limpio disponible: S1 (1 obstáculo central, r=0,30) vs S2 (2
obstáculos a 0,75 m de las paredes, r=0,25). S3 mezcla un central con cuatro
junto a las esquinas y se reporta sólo como referencia.

Estadístico, por semilla s (mismas 100 semillas en ambos escenarios; cada
escenario pareado contra SU control con las mismas poses):
    D_k(s) = métrica(Sk, s) − métrica(Sk_ctrl, s)
    contraste(s) = D_S1(s) − D_S2(s)
IC95 = media ± 1,96·EE. Además, normalizado por el área libre perdida del
punto de mira (S1 0,7242 m²; S2 1,1618 m²), porque S2 quita más área.

Salida: resultados/contraste_central_periferico.txt

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

_CARPETA: Path = Path(__file__).resolve().parent
RUTA_CSV: Path = _CARPETA / "resultados" / "experimento_O_completo.csv"
RUTA_TXT: Path = _CARPETA / "resultados" / "contraste_central_periferico.txt"
AREA_PERDIDA: Dict[str, float] = {"S1": 6.9696 - 6.2454, "S2": 6.9696 - 5.8078,
                                  "S3": 6.9696 - 4.5719}
METRICAS: Tuple[Tuple[str, str], ...] = (
    ("cbf_frac_hmin_pared", "intervención de PARED (indirecta)"),
    ("cbf_frac_hmin_obst", "intervención de OBSTÁCULO (directa)"),
    ("cbf_frac_interv", "intervención total"),
    ("frac_agente_paso_periferia_050", "ocupación de la periferia (<0,5 m)"),
    ("frac_agente_paso_banda_018", "ocupación de la banda (<0,18 m)"),
    ("escape_n", "escapes por episodio"),
    ("cobertura_accesible", "cobertura accesible"),
)


def ic95(x: np.ndarray) -> Tuple[float, float, float]:
    m = float(np.mean(x))
    ee = float(np.std(x, ddof=1)) / math.sqrt(len(x))
    return m, m - 1.96 * ee, m + 1.96 * ee


def main() -> None:
    d: Dict[str, Dict[int, Dict[str, float]]] = {}
    with open(RUTA_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d.setdefault(r["condicion"], {})[int(r["seed_ep"])] = {
                k: float(v) for k, v in r.items()
                if k not in ("condicion", "escenario")}
    sem = sorted(d["S0"].keys())

    def delta(k: str, m: str) -> np.ndarray:
        return np.array([d[k][s][m] - d[f"{k}_ctrl"][s][m] for s in sem])

    L: List[str] = ["CONTRASTE CENTRAL vs DESCENTRADO — predicción del revisor",
                    "contraste = Δ(S1 − S1_ctrl) − Δ(S2 − S2_ctrl), por semilla, n=100",
                    "Predicción: el componente de PARED es MENOR con obstáculos "
                    "periféricos ⇒ contraste de pared > 0.", ""]
    L.append(f"  {'métrica':38s} {'Δ S1':>11s} {'Δ S2':>11s} {'Δ S3':>11s} "
             f"{'S1 − S2':>11s} {'IC95':>26s}")
    for m, etiq in METRICAS:
        a, b, c = delta("S1", m), delta("S2", m), delta("S3", m)
        mm, lo, hi = ic95(a - b)
        s = "*" if lo * hi > 0 else " "
        L.append(f"  {etiq:38s} {a.mean():+11.6f} {b.mean():+11.6f} {c.mean():+11.6f} "
                 f"{mm:+11.6f} [{lo:+.6f}, {hi:+.6f}]{s}")
    L.append("")
    L.append("NORMALIZADO por m² de área libre perdida (punto de mira, h ≥ 0)")
    for m, etiq in METRICAS[:3]:
        a = delta("S1", m) / AREA_PERDIDA["S1"]
        b = delta("S2", m) / AREA_PERDIDA["S2"]
        mm, lo, hi = ic95(a - b)
        s = "*" if lo * hi > 0 else " "
        L.append(f"  {etiq:38s} S1 {a.mean():+.6f}/m²  S2 {b.mean():+.6f}/m²  "
                 f"S3 {(delta('S3', m) / AREA_PERDIDA['S3']).mean():+.6f}/m²  "
                 f"S1−S2 {mm:+.6f} [{lo:+.6f}, {hi:+.6f}]{s}")
    L.append("")
    L.append("Salvedades declaradas:")
    L.append("  - S2 no es puramente periférico (superficies a 0,50 m de la pared);")
    L.append("    S1 y S2 difieren también en número de obstáculos y área quitada.")
    L.append("  - Los objetivos rebotan en los obstáculos sólo en Sk: la dinámica de")
    L.append("    objetivos difiere de la del control (confusión no resuelta en la")
    L.append("    cobertura, no en la intervención por barrera).")
    texto = "\n".join(L) + "\n"
    RUTA_TXT.write_bytes(texto.encode("utf-8"))
    print(texto)


if __name__ == "__main__":
    main()
