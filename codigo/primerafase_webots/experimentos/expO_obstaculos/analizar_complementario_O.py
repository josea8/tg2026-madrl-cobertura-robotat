"""
analizar_complementario_O.py
============================
Análisis de la corrida complementaria del Exp O (13/sep/2026) desde
`resultados/experimento_O_complementario.csv`.

1. ATRIBUCIÓN DE LAS INFACTIBILIDADES. El contador `escape_infactibles` suma
   dos cosas distintas, heredadas del coordinador:
     opuestas    — había barreras activas (h < 0,06) pero la suma de sus
                   normales tiene norma < 0,20: infactibilidad REAL.
     sin_activas — durante el escape, antes de ESC_MIN_DECISIONES, ya no
                   quedaba ninguna barrera activa: el escape SALIÓ; no es falla.
   "Junto a obstáculo" ya era obstáculo ACTIVO (h < 0,06), no el de h mínimo.
   Para las opuestas se cuenta qué tipos de barrera estaban activos (un evento
   puede tener varios).

2. CONTROL FANTASMA de la cobertura. Sk_fant: los objetivos rebotan en los
   obstáculos EXACTAMENTE como en Sk (la dinámica de objetivos no depende de
   los agentes), pero los agentes no tienen barrera, contacto ni máscara.
     Sk − Sk_fant   : efecto del SISTEMA con la dinámica de objetivos fija.
     Sk_fant − ctrl : efecto de la DINÁMICA DE OBJETIVOS sola.
   Todas pareadas por semilla, cobertura sobre las celdas accesibles del
   escenario. IC95 = media ± 1,96·EE.

Salida: resultados/resumen_complementario_O.txt

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

_CARPETA: Path = Path(__file__).resolve().parent
RUTA_CSV: Path = _CARPETA / "resultados" / "experimento_O_complementario.csv"
RUTA_REG: Path = _CARPETA / "resultados" / "registro_O_complementario.txt"
RUTA_TXT: Path = _CARPETA / "resultados" / "resumen_complementario_O.txt"


def ic95(x: np.ndarray) -> Tuple[float, float, float]:
    m = float(np.mean(x))
    ee = float(np.std(x, ddof=1)) / math.sqrt(len(x))
    return m, m - 1.96 * ee, m + 1.96 * ee


def sig(lo: float, hi: float) -> str:
    return "*" if lo * hi > 0 else " "


def main() -> None:
    d: Dict[str, Dict[int, Dict[str, float]]] = {}
    with open(RUTA_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d.setdefault(r["condicion"], {})[int(r["seed_ep"])] = {
                k: float(v) for k, v in r.items() if k not in ("condicion", "escenario")}
    sem = sorted(d["S1"].keys())

    def v(c: str, m: str) -> np.ndarray:
        return np.array([d[c][s][m] for s in sem])

    L: List[str] = ["EXP O — CORRIDA COMPLEMENTARIA (13/sep/2026)"]
    if RUTA_REG.exists():
        L.append("  " + RUTA_REG.read_text(encoding="utf-8").strip())
    L.append("")
    L.append("1. MOTIVO DE LAS INFACTIBILIDADES (sumas sobre 100 episodios)")
    L.append("   opuestas = infactibilidad real; sin_activas = el escape ya salió")
    L.append(f"  {'condición':10s} {'total':>6s} {'opuestas':>9s} {'sin_act.':>9s} "
             f"{'op+pared':>9s} {'op+robot':>9s} {'op+obst':>8s} {'junto obst':>11s} "
             f"{'agotados':>9s}")
    for k in ("S1", "S2", "S3"):
        for c in (f"{k}_ctrl", f"{k}_fant", k):
            L.append(f"  {c:10s} {int(v(c, 'escape_infactibles').sum()):6d} "
                     f"{int(v(c, 'escape_infact_opuestas').sum()):9d} "
                     f"{int(v(c, 'escape_infact_sin_activas').sum()):9d} "
                     f"{int(v(c, 'escape_infact_op_con_pared').sum()):9d} "
                     f"{int(v(c, 'escape_infact_op_con_robot').sum()):9d} "
                     f"{int(v(c, 'escape_infact_op_con_obst').sum()):8d} "
                     f"{int(v(c, 'escape_infactibles_junto_obst').sum()):11d} "
                     f"{int(v(c, 'escape_agotados').sum()):9d}")
    L.append("")
    L.append("  Pareado Sk − Sk_ctrl, por episodio:")
    for k in ("S1", "S2", "S3"):
        for m, e in (("escape_infact_opuestas", "opuestas (reales)"),
                     ("escape_infact_sin_activas", "sin_activas (salida)"),
                     ("escape_infact_op_con_obst", "opuestas con obstáculo")):
            mm, lo, hi = ic95(v(k, m) - v(f"{k}_ctrl", m))
            L.append(f"    {k} {e:24s} Δ {mm:+.4f} [{lo:+.4f}, {hi:+.4f}]{sig(lo, hi)}")
    L.append("")

    L.append("2. CONTROL FANTASMA — cobertura sobre celdas accesibles, pareada")
    L.append(f"  {'':3s} {'ctrl':>11s} {'fant':>11s} {'Sk':>11s}   "
             f"{'Sk − ctrl':>32s}   {'fant − ctrl (objetivos)':>32s}   "
             f"{'Sk − fant (sistema)':>32s}")
    for k in ("S1", "S2", "S3"):
        c, f_, s_ = (v(x, "cobertura_accesible") for x in (f"{k}_ctrl", f"{k}_fant", k))
        partes = []
        for a, b in ((s_, c), (f_, c), (s_, f_)):
            mm, lo, hi = ic95(a - b)
            partes.append(f"{mm:+.5f} [{lo:+.5f},{hi:+.5f}]{sig(lo, hi)}")
        L.append(f"  {k:3s} {c.mean():11.8f} {f_.mean():11.8f} {s_.mean():11.8f}   "
                 + "   ".join(f"{p:>32s}" for p in partes))
    L.append("  Lectura: si fant − ctrl ≈ Sk − ctrl, la subida de cobertura es de la")
    L.append("  dinámica de objetivos y no del sistema; si Sk − fant ≈ 0, idem.")
    L.append("")
    L.append("  Intervención del filtro (el fantasma no tiene barrera de obstáculo):")
    for k in ("S1", "S2", "S3"):
        L.append(f"    {k}: ctrl {v(f'{k}_ctrl', 'cbf_frac_interv').mean():.6f}  "
                 f"fant {v(f'{k}_fant', 'cbf_frac_interv').mean():.6f}  "
                 f"Sk {v(k, 'cbf_frac_interv').mean():.6f}")
    texto = "\n".join(L) + "\n"
    RUTA_TXT.write_bytes(texto.encode("utf-8"))
    print(texto)


if __name__ == "__main__":
    main()
