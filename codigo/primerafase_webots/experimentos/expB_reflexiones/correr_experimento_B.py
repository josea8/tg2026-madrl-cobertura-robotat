"""
correr_experimento_B.py
=======================
EXPERIMENTO B — Cuantificación de la dependencia de la política entrenada
respecto a la REFLEXIÓN ELÁSTICA de paredes (dinámica idealizada que NO
existe en Webots ni en el Robotat físico).

Protocolo
---------
Réplica EXACTA del protocolo de evaluación de RESULTADO_PRIMERO
(`fase_preliminar2/consolidar_resultado_primero.py`):
  - 100 episodios deterministas, seed_ep = 42·10_000 + i  (i = 0..99).
  - env: n_agents=5, arena (3,3), max_steps=500, comm_radius=1.0,
    pesos Trial 13, domain_rand=False, seed base 42.
  - Política MADRL: obs apiladas → modelo.predict(batch, deterministic=True).
  - Fin de episodio: all(trunc) or all(term).

Instrumentación
---------------
La copia del env en `lib/` cuenta, por agente y episodio, cuántas veces se
ejecuta una rama de reflexión elástica en `_integrate_kinematics` (ver
`lib/__init__.py`). La cobertura final por episodio se registra también,
como CROSS-CHECK contra el valor oficial de RESULTADO_PRIMERO
(media 0.6813 ± 0.0200) — si coincide, la réplica del protocolo es fiel.

Salidas
-------
  resultados/experimento_B_reflexiones.csv   (una fila por episodio)
  resultados/resumen_experimento_B.txt       (números listos para citar)

Uso
---
  python correr_experimento_B.py

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path
from typing import Dict, List

import numpy as np

# ── sys.path: carpeta del script para que `lib` resuelva ────────────────────
_CARPETA_SCRIPT: Path = Path(__file__).resolve().parent
if str(_CARPETA_SCRIPT) not in sys.path:
    sys.path.insert(0, str(_CARPETA_SCRIPT))

from stable_baselines3 import PPO

from lib.swarm_env_skeleton import make_env


# =============================================================================
# CONFIGURACIÓN — idéntica a consolidar_resultado_primero.py
# =============================================================================

N_EPISODIOS:  int   = 100
SEED_BASE:    int   = 42
N_AGENTES:    int   = 5
MAX_STEPS_EP: int   = 500
ARENA:        tuple = (3.0, 3.0)
COMM_RADIUS:  float = 1.0

# Pesos del Trial 13 (RESULTADO_PRIMERO/config_entrenamiento.json).
PESOS_TRIAL13: Dict[str, float] = {
    "lambda_gradient": 0.5622468083379316,
    "lambda_entropy":  1.1403296484190344,
    "lambda_ibrm":     0.48380314172632155,
    "lambda_cbf":      2.9655314099141474,
}

RUTA_MODELO:  Path = _CARPETA_SCRIPT / "modelos" / "modelo_PRIMERO.zip"
DIR_SALIDA:   Path = _CARPETA_SCRIPT / "resultados"
RUTA_CSV:     Path = DIR_SALIDA / "experimento_B_reflexiones.csv"
RUTA_RESUMEN: Path = DIR_SALIDA / "resumen_experimento_B.txt"

# Valor oficial para el cross-check (RESULTADO_PRIMERO/metricas_100eps.json).
COBERTURA_OFICIAL_MEDIA: float = 0.6813


# =============================================================================
# EJECUCIÓN
# =============================================================================

def correr_episodio(env, modelo: PPO, seed_ep: int) -> Dict[str, object]:
    """
    Ejecuta un episodio determinista completo y retorna las métricas.

    Retorna
    -------
    dict con: seed_ep, reflexiones por agente, total, cobertura final,
    pasos ejecutados.
    """
    obs_dict, _ = env.reset(seed=seed_ep)
    agentes: List[str] = list(obs_dict.keys())

    done = False
    n_pasos = 0
    while not done:
        obs_arr = np.stack([obs_dict[a] for a in agentes])
        acciones, _ = modelo.predict(obs_arr, deterministic=True)
        accion_dict = {a: acciones[k] for k, a in enumerate(agentes)}
        obs_dict, _, term, trunc, _ = env.step(accion_dict)
        n_pasos += 1
        done = all(trunc.values()) or all(term.values())

    reflexiones: Dict[str, int] = env.contador_reflexiones
    cobertura_final = 1.0 - float(np.mean(env._field._grid_aoi))

    fila: Dict[str, object] = {
        "seed_ep":         seed_ep,
        "pasos":           n_pasos,
        "cobertura_final": round(cobertura_final, 6),
        "reflexiones_total": sum(reflexiones.values()),
    }
    for a in agentes:
        fila[f"reflexiones_{a}"] = reflexiones[a]
    return fila


def main() -> None:
    """Corre los 100 episodios, escribe CSV y resumen."""
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)

    print("═" * 70)
    print("  EXPERIMENTO B — Conteo de reflexiones de pared (100 eps, MADRL)")
    print("═" * 70)

    env = make_env(
        n_agents       = N_AGENTES,
        arena_size     = ARENA,
        max_steps      = MAX_STEPS_EP,
        comm_radius    = COMM_RADIUS,
        reward_weights = PESOS_TRIAL13,
        domain_rand    = False,
        seed           = SEED_BASE,
    )
    modelo = PPO.load(str(RUTA_MODELO), device="cpu")
    print(f"Modelo cargado: {RUTA_MODELO.name}")

    t0 = time.time()
    filas: List[Dict[str, object]] = []
    for i in range(N_EPISODIOS):
        seed_ep = SEED_BASE * 10_000 + i
        fila = correr_episodio(env, modelo, seed_ep)
        filas.append(fila)
        if (i + 1) % 10 == 0:
            print(
                f"  ep {i+1:3d}/{N_EPISODIOS}  "
                f"refl_total={fila['reflexiones_total']:3d}  "
                f"cob={fila['cobertura_final']:.4f}  "
                f"({time.time()-t0:.0f}s)"
            )

    # ── CSV ──────────────────────────────────────────────────────────────
    campos = list(filas[0].keys())
    with open(RUTA_CSV, "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=campos)
        escritor.writeheader()
        escritor.writerows(filas)
    print(f"\nCSV escrito → {RUTA_CSV}")

    # ── Estadísticas ─────────────────────────────────────────────────────
    refl_totales = np.array([f["reflexiones_total"] for f in filas], dtype=float)
    coberturas   = np.array([f["cobertura_final"]   for f in filas], dtype=float)
    agentes      = [f"robot_{k}" for k in range(N_AGENTES)]
    refl_por_agente = {
        a: np.array([f[f"reflexiones_{a}"] for f in filas], dtype=float)
        for a in agentes
    }

    pct_eps_con_reflexion = 100.0 * float(np.mean(refl_totales >= 1))
    media_total   = float(np.mean(refl_totales))
    std_total     = float(np.std(refl_totales))
    mediana_total = float(np.median(refl_totales))
    max_total     = int(np.max(refl_totales))
    media_por_agente_global = media_total / N_AGENTES

    cob_media = float(np.mean(coberturas))
    cob_std   = float(np.std(coberturas))
    delta_crosscheck = abs(cob_media - COBERTURA_OFICIAL_MEDIA)

    lineas: List[str] = []
    lineas.append("EXPERIMENTO B — Reflexiones de pared bajo el protocolo de")
    lineas.append("evaluación de RESULTADO_PRIMERO (100 eps deterministas,")
    lineas.append("5 agentes, sin domain_rand, seed_ep = 420000+i)")
    lineas.append("=" * 66)
    lineas.append("")
    lineas.append(f"Episodios ejecutados             : {N_EPISODIOS}")
    lineas.append(f"Reflexiones por episodio (TOTAL) : media={media_total:.2f}  "
                  f"std={std_total:.2f}  mediana={mediana_total:.1f}  max={max_total}")
    lineas.append(f"Reflexiones por episodio/agente  : media={media_por_agente_global:.2f}")
    lineas.append(f"Episodios con ≥1 reflexión       : {pct_eps_con_reflexion:.1f}%")
    lineas.append("")
    lineas.append("Por agente (media de reflexiones/episodio):")
    for a in agentes:
        lineas.append(f"  {a}: {float(np.mean(refl_por_agente[a])):.2f}")
    lineas.append("")
    lineas.append("CROSS-CHECK de fidelidad del protocolo:")
    lineas.append(f"  cobertura media replicada : {cob_media:.4f} ± {cob_std:.4f}")
    lineas.append(f"  cobertura media oficial   : {COBERTURA_OFICIAL_MEDIA:.4f}")
    lineas.append(f"  |delta|                   : {delta_crosscheck:.4f}  "
                  f"({'OK — réplica fiel' if delta_crosscheck < 0.01 else 'REVISAR — protocolo difiere'})")
    lineas.append("")
    lineas.append("Interpretación: cada reflexión es un evento en el que la política")
    lineas.append("dependió de la dinámica idealizada de rebote en pared — dinámica")
    lineas.append("inexistente en Webots (paredes sólidas) y en el Robotat físico.")

    resumen = "\n".join(lineas)
    RUTA_RESUMEN.write_text(resumen, encoding="utf-8")
    print(f"Resumen escrito → {RUTA_RESUMEN}\n")
    print(resumen)


if __name__ == "__main__":
    main()
