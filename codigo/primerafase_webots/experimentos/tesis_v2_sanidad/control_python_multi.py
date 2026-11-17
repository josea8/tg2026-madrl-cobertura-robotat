"""
control_python_multi.py
=======================
Control de Python del `modelo_sanidad` sobre las MISMAS 18 semillas del lote
de Webots (420000-420017), para 1, 2 y 5 agentes con bordes bloqueantes.

Propósito
---------
Dar la referencia pareada contra la que comparar los lotes multi-robot con
física real. Sin esto no se puede separar "lo que hace la política" de "lo que
agrega la física de Webots" (chasis con radio, fricción de contacto,
comunicación con latencia).

Las 3 semillas del sondeo anterior (0.5221 para 5 agentes) NO sirven como
referencia: la varianza entre semillas es grande y el lote de Webots usa 18.

Salidas
-------
  resultados/control_python_multi.csv   (1 fila por n_agentes × semilla)
  resultados/control_python_multi.txt   (agregados por n_agentes)

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np

_CARPETA: Path = Path(__file__).resolve().parent
_EXP_C: Path = _CARPETA.parent / "expC_bordes"
if str(_EXP_C) not in sys.path:
    sys.path.insert(0, str(_EXP_C))

from stable_baselines3 import PPO

from lib.swarm_env_skeleton import D_SAFE, make_env

# Umbrales de colisión (ver coordinador_enjambre para la justificación).
UMBRAL_CONTACTO: float = 0.15   # = D_SAFE del env; chasis en contacto
UMBRAL_MARGEN:   float = 0.22   # margen operativo de la metodología

N_EPISODIOS: int = 18
SEED_BASE:   int = 42
SEMILLAS: List[int] = [SEED_BASE * 10_000 + i for i in range(N_EPISODIOS)]
CONFIGS_AGENTES: List[int] = [1, 2, 5]

PESOS_TRIAL13: Dict[str, float] = {
    "lambda_gradient": 0.5622468083379316,
    "lambda_entropy":  1.1403296484190344,
    "lambda_ibrm":     0.48380314172632155,
    "lambda_cbf":      2.9655314099141474,
}

RUTA_MODELO:  Path = _CARPETA / "modelo_sanidad.zip"
DIR_SALIDA:   Path = _CARPETA / "resultados"
RUTA_CSV:     Path = DIR_SALIDA / "control_python_multi.csv"
RUTA_RESUMEN: Path = DIR_SALIDA / "control_python_multi.txt"


def correr_episodio(env, modelo: PPO, seed_ep: int) -> Dict[str, float]:
    """Ejecuta un episodio determinista y retorna cobertura y colisiones."""
    obs, _ = env.reset(seed=seed_ep)
    agentes: List[str] = list(obs.keys())
    n_a = len(agentes)

    pares_contacto: set = set()
    pares_margen:   set = set()
    done = False
    n_pasos = 0

    while not done:
        acciones, _ = modelo.predict(
            np.stack([obs[a] for a in agentes]), deterministic=True
        )
        obs, _, term, trunc, _ = env.step(
            {a: acciones[k] for k, a in enumerate(agentes)}
        )
        n_pasos += 1
        pos = np.array([env._estados[a][:2] for a in agentes])
        for ii in range(n_a):
            for jj in range(ii + 1, n_a):
                d = float(np.linalg.norm(pos[ii] - pos[jj]))
                if d < UMBRAL_CONTACTO:
                    pares_contacto.add((ii, jj))
                if d < UMBRAL_MARGEN:
                    pares_margen.add((ii, jj))
        done = all(trunc.values()) or all(term.values())

    return {
        "cobertura_aoi_final": round(
            1.0 - float(np.mean(env._field._grid_aoi)), 6
        ),
        "colisiones_015": len(pares_contacto),
        "colisiones_022": len(pares_margen),
        "recortes_total": sum(env.contador_recortes.values()),
        "frac_pasos_agente_recorte": round(
            sum(env.contador_recortes.values()) / (n_pasos * n_a), 6
        ) if n_pasos else 0.0,
        "pasos": n_pasos,
    }


def main() -> None:
    """Corre el control para cada configuración de agentes."""
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    modelo = PPO.load(str(RUTA_MODELO), device="cpu")

    print("═" * 72)
    print("  CONTROL PYTHON — modelo_sanidad, bordes bloqueantes, 18 semillas")
    print("═" * 72)

    filas: List[Dict[str, object]] = []
    agregados: Dict[int, Dict[str, float]] = {}

    for n_ag in CONFIGS_AGENTES:
        env = make_env(
            n_agents       = n_ag,
            arena_size     = (3.0, 3.0),
            max_steps      = 500,
            comm_radius    = 1.0,
            reward_weights = PESOS_TRIAL13,
            domain_rand    = False,
            seed           = SEED_BASE,
            modo_borde     = "bloqueante",
        )
        del_n: List[Dict[str, float]] = []
        for semilla in SEMILLAS:
            m = correr_episodio(env, modelo, semilla)
            filas.append({"n_agentes": n_ag, "semilla": semilla, **m})
            del_n.append(m)

        cob  = np.array([d["cobertura_aoi_final"] for d in del_n])
        c015 = np.array([float(d["colisiones_015"]) for d in del_n])
        c022 = np.array([float(d["colisiones_022"]) for d in del_n])
        frac = np.array([d["frac_pasos_agente_recorte"] for d in del_n])
        agregados[n_ag] = {
            "cob_media": float(np.mean(cob)),
            "cob_std":   float(np.std(cob)),
            "c015_media": float(np.mean(c015)),
            "c015_std":   float(np.std(c015)),
            "c015_pct":   100.0 * float(np.mean(c015 > 0)),
            "c022_media": float(np.mean(c022)),
            "c022_pct":   100.0 * float(np.mean(c022 > 0)),
            "frac_borde": float(np.mean(frac)),
        }
        a = agregados[n_ag]
        print(f"  n_agentes={n_ag}: cobertura={a['cob_media']:.4f} ± "
              f"{a['cob_std']:.4f}  col015={a['c015_media']:.3f} "
              f"({a['c015_pct']:.1f}% eps)  frac_borde={a['frac_borde']:.4f}")

    with open(RUTA_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    print(f"\nCSV → {RUTA_CSV}")

    L: List[str] = []
    L.append("CONTROL PYTHON — modelo_sanidad, bordes bloqueantes")
    L.append(f"{N_EPISODIOS} semillas ({SEMILLAS[0]}-{SEMILLAS[-1]}), "
             f"deterministic=True, domain_rand=False")
    L.append("Referencia pareada para los lotes multi-robot de Webots.")
    L.append("=" * 70)
    L.append(f"  {'n_ag':>5s} {'cobertura':>18s} {'col_015':>10s} "
             f"{'%eps_col':>9s} {'frac_borde':>11s}")
    for n_ag in CONFIGS_AGENTES:
        a = agregados[n_ag]
        L.append(f"  {n_ag:5d} {a['cob_media']:9.4f} ± {a['cob_std']:.4f}"
                 f" {a['c015_media']:10.3f} {a['c015_pct']:8.1f}%"
                 f" {a['frac_borde']:11.4f}")
    L.append("")
    L.append("UMBRALES: col_015 usa 0.15 m entre centros = contacto físico de")
    L.append("los chasis (radio 0.075 m c/u) y es el D_SAFE del env; es la")
    L.append("columna comparable con todas las métricas previas (exp A-D y")
    L.append("sanidad). 'frac_borde' = fracción agente-paso recortada por el")
    L.append("borde bloqueante en el env (no aplica en Webots, donde la pared")
    L.append("es un cuerpo rígido).")

    resumen = "\n".join(L)
    RUTA_RESUMEN.write_text(resumen, encoding="utf-8")
    print(f"Resumen → {RUTA_RESUMEN}\n")
    print(resumen)


if __name__ == "__main__":
    main()
