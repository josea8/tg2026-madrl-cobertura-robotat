"""
potencia_R.py
=============
Potencia A PRIORI de las pruebas del Exp R a n = 400, estimada ANTES de correr
sobre las 100 semillas vistas (S1 del Exp Q y el exploratorio de S2/S3). Es la
fuente de las cifras de potencia de `PREREGISTRO_R.md` (§8).

Método: bootstrap pareado por semilla (cada réplica toma 400 semillas de las
100, con todas sus 12 celdas juntas), dos variantes:
  plug-in      pesos ~ Multinomial(400, 1/100);
  predictiva   pesos de Dirichlet(1) sobre las 100 y después la multinomial
               (agrega la incertidumbre de las tasas del exploratorio).
En cada réplica se aplican las MISMAS reglas de lectura del prerregistro
(McNemar exacta bilateral, 'sostenida' si p < 0,05 y b > c; H4: IC95 con
lo > 0 en las dos piezas). Además, la potencia en el punto P(b ≥ 6) con
b ~ Binomial(n, tasa) y c = 0, y la cota de Clopper-Pearson de 0/n.

    python -B potencia_R.py          (resultados/potencia_R.txt)

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from scipy.special import betaln
from scipy.stats import binom, poisson

_CARPETA: Path = Path(__file__).resolve().parent
_CARPETA_Q: Path = (_CARPETA.parent / "expQ_obstaculos_moviles").resolve()
RUTAS: Tuple[Path, ...] = (_CARPETA_Q / "resultados" / "experimento_Q_completo.csv",
                           _CARPETA_Q / "resultados" / "experimento_Q_EXPLORATORIO_S2_S3.csv")
RUTA_SALIDA: Path = _CARPETA / "resultados" / "potencia_R.txt"
N_R: int = 400
REPLICAS: int = 20_000
SEMILLA_RNG: int = 20261024
ALFA: float = 0.05
#: (id, columna, umbral, modo, nivel, A, B): la predicción es A > B.
PRUEBAS: Tuple[Tuple[str, str, float, str, str, str, str], ...] = (
    ("H1-S3", "qp_fallbacks", 0.0, "mayor", "S3", "din", "quieto"),
    ("H1-S2", "qp_fallbacks", 0.0, "mayor", "S2", "din", "quieto"),
    ("H2-S2", "viol_cota_obst_agente_eps", 0.0, "mayor", "S2", "sinvel", "din"),
    ("H2-S3", "viol_cota_obst_agente_eps", 0.0, "mayor", "S3", "sinvel", "din"),
    ("H3a", "escape_agotados", 0.0, "mayor", "S3", "din", "ctrl"),
    ("H3b", "escape_agotados", 0.0, "mayor", "S3", "din", "quieto"),
    ("H5b", "contactos_obst_eventos", 0.0, "mayor", "S3", "sinvel", "din"),
)


def cargar() -> Tuple[Dict[str, Dict[int, Dict[str, float]]], List[int]]:
    datos: Dict[str, Dict[int, Dict[str, float]]] = {}
    for ruta in RUTAS:
        with open(ruta, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                fila = {}
                for k, v in r.items():
                    try:
                        fila[k] = float(v)
                    except (TypeError, ValueError):
                        pass
                datos.setdefault(r["condicion"], {})[int(r["seed_ep"])] = fila
    sem = sorted(datos["S1_din"])
    return datos, sem


def p_mcnemar(b: np.ndarray, c: np.ndarray) -> np.ndarray:
    n = b + c
    p = np.minimum(1.0, 2.0 * binom.cdf(np.minimum(b, c), n, 0.5))
    return np.where(n == 0, 1.0, p)


def main() -> None:
    if not sys.flags.dont_write_bytecode:
        raise SystemExit("PARAR: correr con python -B.")
    datos, sem = cargar()
    rng = np.random.default_rng(SEMILLA_RNG)
    w_plug = rng.multinomial(N_R, np.full(len(sem), 1.0 / len(sem)), size=REPLICAS)
    w_pred = np.array([rng.multinomial(N_R, rng.dirichlet(np.ones(len(sem))))
                       for _ in range(REPLICAS)])
    L = [f"POTENCIA A PRIORI del Exp R a n = {N_R} (bootstrap pareado por semilla sobre las "
         f"{len(sem)} semillas vistas {sem[0]}–{sem[-1]}; {REPLICAS} réplicas; rng "
         f"default_rng({SEMILLA_RNG}); reglas de lectura del prerregistro)"]
    for pid, col, u, modo, k, a, b in PRUEBAS:
        xa = np.array([datos[f"{k}_{a}"][s][col] > u for s in sem])
        xb = np.array([datos[f"{k}_{b}"][s][col] > u for s in sem])
        solo_a, solo_b = (xa & ~xb).astype(float), (~xa & xb).astype(float)
        partes = []
        for nombre, w in (("plug-in", w_plug), ("predictiva", w_pred)):
            bb, cc = w @ solo_a, w @ solo_b
            ok = (p_mcnemar(bb, cc) < ALFA) & (bb > cc)
            partes.append(f"{nombre} {ok.mean():.4f}")
        L.append(f"  {pid} ({k}_{a} > {k}_{b}; discordantes vistos {int(solo_a.sum())}/"
                 f"{int(solo_b.sum())} de {len(sem)}): " + "; ".join(partes))
    d = {k: np.array([datos[f"{k}_din"][s]["cobertura_accesible"]
                      - datos[f"{k}_ctrl"][s]["cobertura_accesible"] for s in sem])
         for k in ("S1", "S2", "S3")}
    piezas = {"Δ_S1 − Δ_S3": d["S1"] - d["S3"], "Δ_S2 − Δ_S3": d["S2"] - d["S3"]}
    for nombre, w in (("plug-in", w_plug), ("predictiva", w_pred)):
        ok_todas = np.ones(REPLICAS, dtype=bool)
        partes = []
        for pn, x in piezas.items():
            m = (w @ x) / N_R
            var = (w * (x[None, :] - m[:, None]) ** 2).sum(axis=1) / (N_R - 1)
            lo = m - 1.96 * np.sqrt(var / N_R)
            ok_todas &= lo > 0
            partes.append(f"{pn} {np.mean(lo > 0):.4f}")
        L.append(f"  H4 {nombre}: " + "; ".join(partes) + f"; las dos {ok_todas.mean():.4f}")
    L.append("POTENCIA EN EL PUNTO, P(b ≥ 6) con b ~ Binomial(n, tasa) y c = 0 (con c = 0 la "
             "McNemar exacta bilateral da p ≤ 0,05 sólo con b ≥ 6: 2·0,5^5 = 0,0625; "
             "2·0,5^6 = 0,03125)")
    for n in (200, 300, 400, 500):
        L.append(f"  n = {n}: " + "; ".join(
            f"tasa {t:.0%} {1 - binom.cdf(5, n, t):.4f}" for t in (0.01, 0.02, 0.03, 0.05, 0.08)))
    L.append("COTA SUPERIOR de Clopper-Pearson (95 % bilateral) de 0/n = 1 − 0,025^(1/n): " +
             "; ".join(f"n = {n} {1 - 0.025 ** (1 / n):.6f}" for n in (100, 200, 300, 400, 500)))
    L.append("ACOPLAMIENTO H5a–H5b, potencia de H5b en el punto (tasa 3 % en sinvel) según los "
             "contactos c de din: " + "; ".join(
                 f"c = {c}: {1 - binom.cdf(_umbral_b(c) - 1, N_R, 0.03):.4f} (b ≥ {_umbral_b(c)})"
                 for c in (0, 1, 2)))
    # H5a: con 0/100 vistos y previa de Jeffreys, p ~ Beta(0,5; 100,5) y
    # P(0/400) = E[(1 − p)^400] = B(0,5; 500,5) / B(0,5; 100,5).
    p0 = math.exp(betaln(0.5, 100.5 + N_R) - betaln(0.5, 100.5))
    L.append(f"H5a: P(0/{N_R} en un nivel | 0/100 vistos), previa de Jeffreys: {p0:.4f}; en los "
             f"tres niveles (independientes): {p0 ** 3:.4f}")
    # Trazas: el criterio de requiere_traza_R (celdas con obstáculo físico, con
    # fallback, contacto o d_min < 0,10) sobre las semillas vistas, × 4.
    vistos = sum(1 for c, filas in datos.items() if not c.endswith("_ctrl")
                 for f in filas.values()
                 if f["qp_fallbacks"] > 0 or f["contactos_obst_eventos"] > 0
                 or f["d_min_obst_superficie"] < 0.10)
    esperadas = vistos * N_R / len(sem)
    L.append(f"TRAZAS esperadas a n = {N_R}: {vistos} episodios con traza en las {len(sem)} "
             f"semillas vistas (9 celdas con obstáculo físico) × {N_R // len(sem)} = "
             f"{esperadas:.0f}; Poisson al 95 % [{poisson.ppf(0.025, esperadas):.0f}, "
             f"{poisson.ppf(0.975, esperadas):.0f}]")
    RUTA_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    RUTA_SALIDA.write_bytes(("\n".join(L) + "\n").encode("utf-8"))
    print("\n".join(L))


def _umbral_b(c: int) -> int:
    """El menor b con p < 0,05 (McNemar exacta bilateral) y b > c."""
    b = c + 1
    while not (min(1.0, 2.0 * float(binom.cdf(c, b + c, 0.5))) < ALFA):
        b += 1
    return b


if __name__ == "__main__":
    main()
