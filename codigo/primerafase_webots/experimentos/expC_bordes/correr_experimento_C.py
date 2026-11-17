"""
correr_experimento_C.py
=======================
EXPERIMENTO C — Degradación de cobertura bajo BORDES BLOQUEANTES.

Pregunta
--------
El Experimento B mostró que la política depende de la reflexión elástica de
pared (45.74 ± 5.54 eventos por episodio, 100% de episodios). El Experimento A
mostró que con paredes sólidas (Webots) el robot se atasca. Este experimento
aísla el efecto en SIMULACIÓN PURA: ¿cuánta cobertura pierde la política
cuando el borde deja de reflejar y pasa a bloquear?

Diseño PAREADO
--------------
Las MISMAS 100 semillas del protocolo de RESULTADO_PRIMERO
(seed_ep = 42·10_000 + i) se corren en dos condiciones:

  A) modo_borde = "reflexion"   → condición de entrenamiento (control).
  B) modo_borde = "bloqueante"  → posición recortada a [0,W], θ SIN invertir.

Todo lo demás es idéntico: mismo modelo, deterministic=True, 5 agentes,
domain_rand=False, mismos pesos de reward, hotspots con reflexión elástica en
ambas condiciones (solo cambia el borde de los AGENTES).

El pareo por semilla permite estimar la diferencia con mucha más precisión que
comparar dos medias independientes: la varianza entre semillas (que es grande:
std ≈ 0.02 en cobertura) se cancela al restar dentro de cada par.

VALIDACIÓN OBLIGATORIA: la condición "reflexion" debe reproducir la cobertura
oficial 0.6813 ± 0.0200. Si no, el script ABORTA (la instrumentación habría
alterado el comportamiento y ninguna comparación sería válida).

Métricas por episodio y condición
---------------------------------
  - cobertura_final           : 1 − mean(grid_aoi) al final del episodio.
  - n_colisiones              : pares únicos (i,j) que estuvieron a < D_SAFE
                                en algún paso (mismo criterio del protocolo).
  - frac_pasos_con_recorte    : pasos con ≥1 agente recortado / pasos totales.
  - frac_pasos_agente_recorte : Σ_agentes recortes / (pasos × n_agentes).
  - reflexiones_total         : contador del Experimento B (cruce de datos).

Salidas
-------
  resultados/experimento_C_pareado.csv    (1 fila por semilla × condición)
  resultados/resumen_experimento_C.txt    (números listos para citar)

Uso
---
  python correr_experimento_C.py

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

_CARPETA_SCRIPT: Path = Path(__file__).resolve().parent
if str(_CARPETA_SCRIPT) not in sys.path:
    sys.path.insert(0, str(_CARPETA_SCRIPT))

from stable_baselines3 import PPO

from lib.swarm_env_skeleton import D_SAFE, make_env


# =============================================================================
# CONFIGURACIÓN — idéntica al protocolo de RESULTADO_PRIMERO
# =============================================================================

N_EPISODIOS:  int   = 100
SEED_BASE:    int   = 42
N_AGENTES:    int   = 5
MAX_STEPS_EP: int   = 500
ARENA:        tuple = (3.0, 3.0)
COMM_RADIUS:  float = 1.0

PESOS_TRIAL13: Dict[str, float] = {
    "lambda_gradient": 0.5622468083379316,
    "lambda_entropy":  1.1403296484190344,
    "lambda_ibrm":     0.48380314172632155,
    "lambda_cbf":      2.9655314099141474,
}

CONDICIONES: Tuple[str, ...] = ("reflexion", "bloqueante")

RUTA_MODELO:  Path = _CARPETA_SCRIPT / "modelos" / "modelo_PRIMERO.zip"
DIR_SALIDA:   Path = _CARPETA_SCRIPT / "resultados"
RUTA_CSV:     Path = DIR_SALIDA / "experimento_C_pareado.csv"
RUTA_RESUMEN: Path = DIR_SALIDA / "resumen_experimento_C.txt"

# Validación de fidelidad (RESULTADO_PRIMERO/metricas_100eps.json).
COBERTURA_OFICIAL_MEDIA: float = 0.6813
COBERTURA_OFICIAL_STD:   float = 0.0200
TOL_VALIDACION:          float = 0.01


# =============================================================================
# EJECUCIÓN DE UN EPISODIO
# =============================================================================

def correr_episodio(env, modelo: PPO, seed_ep: int) -> Dict[str, object]:
    """
    Ejecuta un episodio determinista y retorna sus métricas.

    Las colisiones se cuentan con el mismo criterio del protocolo oficial:
    pares únicos (i, j) que estuvieron a distancia < D_SAFE en algún paso.
    """
    obs_dict, _ = env.reset(seed=seed_ep)
    agentes: List[str] = list(obs_dict.keys())
    n_a: int = len(agentes)

    pares_colision: set = set()
    n_pasos: int = 0
    pasos_con_recorte: int = 0
    suma_recortes_prev: int = 0
    done = False

    while not done:
        obs_arr = np.stack([obs_dict[a] for a in agentes])
        acciones, _ = modelo.predict(obs_arr, deterministic=True)
        accion_dict = {a: acciones[k] for k, a in enumerate(agentes)}
        obs_dict, _, term, trunc, _ = env.step(accion_dict)
        n_pasos += 1

        # Recortes de ESTE paso: delta del contador acumulado. Si creció,
        # al menos un agente fue recortado en el paso (medición exacta).
        suma_recortes_actual = sum(env.contador_recortes.values())
        if suma_recortes_actual > suma_recortes_prev:
            pasos_con_recorte += 1
        suma_recortes_prev = suma_recortes_actual

        pos = np.array([env._estados[a][:2] for a in agentes])
        for ii in range(n_a):
            for jj in range(ii + 1, n_a):
                if float(np.linalg.norm(pos[ii] - pos[jj])) < D_SAFE:
                    pares_colision.add((ii, jj))

        done = all(trunc.values()) or all(term.values())

    suma_recortes: int = suma_recortes_prev
    reflexiones: Dict[str, int] = env.contador_reflexiones

    return {
        "cobertura_final":  round(
            1.0 - float(np.mean(env._field._grid_aoi)), 6
        ),
        "n_colisiones":     len(pares_colision),
        "pasos":            n_pasos,
        "recortes_total":   suma_recortes,
        "pasos_con_recorte": pasos_con_recorte,
        "frac_pasos_con_recorte": round(
            pasos_con_recorte / n_pasos, 6
        ) if n_pasos else 0.0,
        "frac_pasos_agente_recorte": round(
            suma_recortes / (n_pasos * n_a), 6
        ) if n_pasos else 0.0,
        "reflexiones_total": sum(reflexiones.values()),
    }


# =============================================================================
# ESTADÍSTICA
# =============================================================================

def ic95_media(muestra: np.ndarray) -> Tuple[float, float, float, float]:
    """
    Media, desviación (ddof=1), error estándar e IC95 (media ± 1.96·EE).

    Con n=100 la aproximación normal es adecuada (t_0.975,99 = 1.984 vs
    z = 1.960; diferencia < 1.3%, irrelevante frente al tamaño del efecto).

    Retorna (media, std, ic_inf, ic_sup).
    """
    n     = len(muestra)
    media = float(np.mean(muestra))
    std   = float(np.std(muestra, ddof=1))
    ee    = std / math.sqrt(n)
    return media, std, media - 1.96 * ee, media + 1.96 * ee


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    """Corre las dos condiciones sobre las mismas semillas y reporta."""
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)

    print("═" * 72)
    print("  EXPERIMENTO C — Bordes bloqueantes vs reflexión (diseño pareado)")
    print("═" * 72)

    modelo = PPO.load(str(RUTA_MODELO), device="cpu")
    print(f"Modelo: {RUTA_MODELO.name}   semillas: "
          f"{SEED_BASE*10_000}..{SEED_BASE*10_000 + N_EPISODIOS - 1}\n")

    filas: List[Dict[str, object]] = []
    por_condicion: Dict[str, List[Dict[str, object]]] = {}

    for condicion in CONDICIONES:
        print(f"── Condición: {condicion} ─────────────────────────────────")
        env = make_env(
            n_agents       = N_AGENTES,
            arena_size     = ARENA,
            max_steps      = MAX_STEPS_EP,
            comm_radius    = COMM_RADIUS,
            reward_weights = PESOS_TRIAL13,
            domain_rand    = False,
            seed           = SEED_BASE,
            modo_borde     = condicion,
        )
        resultados_cond: List[Dict[str, object]] = []
        t0 = time.time()

        for i in range(N_EPISODIOS):
            seed_ep = SEED_BASE * 10_000 + i
            metricas = correr_episodio(env, modelo, seed_ep)
            fila: Dict[str, object] = {
                "condicion": condicion,
                "seed_ep":   seed_ep,
                **metricas,
            }
            filas.append(fila)
            resultados_cond.append(fila)
            if (i + 1) % 25 == 0:
                print(f"  ep {i+1:3d}/{N_EPISODIOS}  "
                      f"cob={metricas['cobertura_final']:.4f}  "
                      f"({time.time()-t0:.0f}s)")

        por_condicion[condicion] = resultados_cond

        # ── Validación de fidelidad en la condición de control ────────────
        if condicion == "reflexion":
            cob = np.array([float(r["cobertura_final"]) for r in resultados_cond])
            media_ctrl = float(np.mean(cob))
            delta = abs(media_ctrl - COBERTURA_OFICIAL_MEDIA)
            print(f"  VALIDACIÓN control: cobertura={media_ctrl:.4f} "
                  f"(oficial {COBERTURA_OFICIAL_MEDIA:.4f}, |Δ|={delta:.4f})")
            if delta > TOL_VALIDACION:
                print("\n  ABORTADO: la condición 'reflexion' NO reproduce la "
                      "cobertura oficial. La instrumentación alteró el "
                      "comportamiento; ninguna comparación sería válida.")
                sys.exit(1)
            print("  → OK, la instrumentación no alteró el comportamiento.\n")

    # ── CSV pareado ──────────────────────────────────────────────────────
    campos = list(filas[0].keys())
    with open(RUTA_CSV, "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=campos)
        escritor.writeheader()
        escritor.writerows(filas)
    print(f"CSV escrito → {RUTA_CSV}")

    # ── Análisis pareado ─────────────────────────────────────────────────
    refl = por_condicion["reflexion"]
    bloq = por_condicion["bloqueante"]
    # Alinear por semilla (ambas listas van en el mismo orden, pero se
    # indexa explícitamente para no depender de ello).
    idx_bloq = {int(r["seed_ep"]): r for r in bloq}

    cob_r = np.array([float(r["cobertura_final"]) for r in refl])
    cob_b = np.array([
        float(idx_bloq[int(r["seed_ep"])]["cobertura_final"]) for r in refl
    ])
    col_r = np.array([float(r["n_colisiones"]) for r in refl])
    col_b = np.array([
        float(idx_bloq[int(r["seed_ep"])]["n_colisiones"]) for r in refl
    ])
    frac_recorte = np.array([
        float(idx_bloq[int(r["seed_ep"])]["frac_pasos_agente_recorte"])
        for r in refl
    ])
    frac_pasos_rec = np.array([
        float(idx_bloq[int(r["seed_ep"])]["frac_pasos_con_recorte"])
        for r in refl
    ])
    refl_total = np.array([float(r["reflexiones_total"]) for r in refl])

    d_cob = cob_b - cob_r          # negativo = degradación
    d_col = col_b - col_r

    m_r, s_r, _, _ = ic95_media(cob_r)
    m_b, s_b, _, _ = ic95_media(cob_b)
    md_c, sd_c, ic_inf_c, ic_sup_c = ic95_media(d_cob)
    mcol_r, scol_r, _, _ = ic95_media(col_r)
    mcol_b, scol_b, _, _ = ic95_media(col_b)
    md_col, sd_col, ic_inf_col, ic_sup_col = ic95_media(d_col)

    degradacion_pct = 100.0 * md_c / m_r
    n_peor = int(np.sum(d_cob < 0))

    # Correlación caída de cobertura vs fracción de tiempo recortado.
    # Se usa −d_cob (caída positiva) para que el signo sea intuitivo.
    caida = -d_cob
    if float(np.std(caida)) > 0 and float(np.std(frac_recorte)) > 0:
        r_pearson = float(np.corrcoef(caida, frac_recorte)[0, 1])
    else:
        r_pearson = float("nan")
    if float(np.std(caida)) > 0 and float(np.std(refl_total)) > 0:
        r_refl = float(np.corrcoef(caida, refl_total)[0, 1])
    else:
        r_refl = float("nan")

    # ── Resumen ──────────────────────────────────────────────────────────
    L: List[str] = []
    L.append("EXPERIMENTO C — Degradación de cobertura bajo bordes bloqueantes")
    L.append("Diseño pareado por semilla, 100 episodios × 2 condiciones,")
    L.append("5 agentes, deterministic=True, domain_rand=False, modelo PRIMERO.")
    L.append("Solo cambian los bordes de los AGENTES; los hotspots conservan")
    L.append("reflexión elástica en ambas condiciones.")
    L.append("=" * 70)
    L.append("")
    L.append("VALIDACIÓN DE FIDELIDAD (condición control)")
    L.append(f"  cobertura 'reflexion' : {m_r:.4f} ± {s_r:.4f}")
    L.append(f"  cobertura oficial     : {COBERTURA_OFICIAL_MEDIA:.4f} ± "
             f"{COBERTURA_OFICIAL_STD:.4f}")
    L.append(f"  |Δ|                   : {abs(m_r - COBERTURA_OFICIAL_MEDIA):.4f}"
             f"  (OK — réplica fiel)")
    L.append("")
    L.append("COBERTURA AoI FINAL")
    L.append(f"  reflexion   : {m_r:.4f} ± {s_r:.4f}")
    L.append(f"  bloqueante  : {m_b:.4f} ± {s_b:.4f}")
    L.append(f"  DIFERENCIA PAREADA (bloqueante − reflexion):")
    L.append(f"      media  = {md_c:+.4f}   desv. = {sd_c:.4f}")
    L.append(f"      IC95   = [{ic_inf_c:+.4f}, {ic_sup_c:+.4f}]")
    L.append(f"      degradación relativa = {degradacion_pct:+.2f}%")
    L.append(f"      episodios con cobertura menor: {n_peor}/{N_EPISODIOS}")
    L.append("")
    L.append("COLISIONES (pares únicos por episodio)")
    L.append(f"  reflexion   : {mcol_r:.3f} ± {scol_r:.3f}")
    L.append(f"  bloqueante  : {mcol_b:.3f} ± {scol_b:.3f}")
    L.append(f"  DIFERENCIA PAREADA:")
    L.append(f"      media  = {md_col:+.3f}   desv. = {sd_col:.3f}")
    L.append(f"      IC95   = [{ic_inf_col:+.3f}, {ic_sup_col:+.3f}]")
    L.append("")
    L.append("TIEMPO CONTRA EL BORDE (condición bloqueante)")
    L.append(f"  fracción de pasos con ≥1 agente recortado : "
             f"{float(np.mean(frac_pasos_rec)):.4f} ± "
             f"{float(np.std(frac_pasos_rec, ddof=1)):.4f}")
    L.append(f"  fracción agente-paso recortado            : "
             f"{float(np.mean(frac_recorte)):.4f} ± "
             f"{float(np.std(frac_recorte, ddof=1)):.4f}")
    L.append(f"  (equivale a ~{float(np.mean(frac_recorte))*MAX_STEPS_EP:.0f} "
             f"pasos de {MAX_STEPS_EP} por agente)")
    L.append("")
    L.append("CORRELACIONES (n=100)")
    L.append(f"  caída de cobertura vs fracción recortada : r = {r_pearson:+.3f}")
    L.append(f"  caída de cobertura vs reflexiones (exp B): r = {r_refl:+.3f}")
    L.append("")
    L.append("Interpretación: la diferencia pareada aísla el efecto del cambio")
    L.append("de dinámica de borde, cancelando la varianza entre semillas")
    L.append("(std ≈ 0.02 en cobertura absoluta). El IC95 de la diferencia es")
    L.append("la cifra a citar para afirmar que la degradación es real.")

    resumen = "\n".join(L)
    RUTA_RESUMEN.write_text(resumen, encoding="utf-8")
    print(f"Resumen escrito → {RUTA_RESUMEN}\n")
    print(resumen)


if __name__ == "__main__":
    main()
