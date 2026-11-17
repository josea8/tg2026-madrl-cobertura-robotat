"""
diagnostico_sin_vecnormalize.py
===============================
Experimento de diagnóstico para aislar el efecto de VecNormalize.

Hipótesis que se prueba
───────────────────────
La corrida 5M con VecNormalize produjo un modelo PEOR (cob=0.626, col=0.98)
que la corrida 200k SIN VecNormalize (cob=0.680, col=0.20). Hipotesizamos
que VecNormalize con `norm_reward=True` es inestable frente a recompensas
multiobjetivo con penalizaciones discretas grandes (p_cbf por colisión).

Este script entrena 500k steps con los hparams del Trial 13 exactamente,
semilla 42, SIN VecNormalize. Guarda un checkpoint cada 100k y al final
evalúa cada uno en 20 episodios deterministas (sin domain_rand).

Diseño
──────
- Reutiliza `construir_vec_env_entrenamiento` (que ya aplica los fixes
  Bug A/B: num_cpus=1, seed monkey-patch).
- NO envuelve el VecMonitor con VecNormalize.
- CheckpointCallback.save_freq dividido por num_envs (Bug C descubierto en
  entrenar_5M.py: freq se compara contra n_calls, no num_timesteps).
- Evaluación determinista via env PettingZoo crudo → acceso directo a
  estados para métricas finas (cobertura final, pares colisión, distancia).

Salidas
───────
  modelos/tesis_v1/diagnostico_sin_vecnormalize/
      ├── checkpoints/                 (cada 100k)
      ├── tensorboard/
      ├── curva_diagnostico.png        (2 subplots: cobertura, colisiones)
      ├── metricas_checkpoints.json    (datos crudos por checkpoint y episodio)
      ├── reporte_diagnostico.md       (tabla + criterio)
      └── diagnostico.log

Criterio de decisión automático
───────────────────────────────
- OPCION_A_VALIDADA     : cob@500k > 0.75 AND tendencia creciente en 300k-500k
- TECHO_DETECTADO       : cob plana en [0.65, 0.75] entre 300k-500k (Δ<0.03)
- PROBLEMA_NO_DIAGNOST  : cob@500k < 0.60
- (advertencia ortogonal) : col cruza 0.30 en algún checkpoint
"""
from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback

from train import (
    ConfigEntorno, ConfigEntrenamiento, HiperparametrosPPO, PesosRecompensa,
    construir_vec_env_entrenamiento, construir_modelo_ppo,
)
from swarm_env_skeleton import D_SAFE, make_env


# ══════════════════════════════════════════════════════════════════════════════
# Configuración
# ══════════════════════════════════════════════════════════════════════════════
ROOT       = Path(__file__).parent.resolve()
DIR_BASE   = ROOT / "modelos" / "tesis_v1" / "diagnostico_sin_vecnormalize"
DIR_CKPT   = DIR_BASE / "checkpoints"
DIR_TB     = DIR_BASE / "tensorboard"
RUTA_HPARAMS_JSON = ROOT / "modelos" / "tesis_v1" / "mejores_hiperparametros.json"

N_PASOS_TOTAL        = 500_000
FREQ_CHECKPOINT_TS   = 100_000      # en timesteps globales
N_EPISODIOS_EVAL     = 20
SEED                 = 42

N_AGENTES            = 5
MAX_STEPS_EP         = 500
N_ENVS_ENTREN        = 4

ARENA: tuple         = (3.0, 3.0)
COMM_RADIUS          = 1.0

# Umbrales de criterio
COB_OPCION_A         = 0.75
COB_BANDA_TECHO      = (0.65, 0.75)
COB_PROBLEMA         = 0.60
DELTA_TECHO          = 0.03
COL_ADVERTENCIA      = 0.30

# Crear directorios
for d in (DIR_BASE, DIR_CKPT, DIR_TB):
    d.mkdir(parents=True, exist_ok=True)

# Logging
logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers= [
        logging.FileHandler(DIR_BASE / "diagnostico.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("diagnostico")


# ══════════════════════════════════════════════════════════════════════════════
# Carga de hiperparámetros Trial 13
# ══════════════════════════════════════════════════════════════════════════════
def cargar_trial_13() -> Tuple[HiperparametrosPPO, PesosRecompensa]:
    with open(RUTA_HPARAMS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    hp = data["hparams"]
    pw = data["pesos_recompensa"]
    hparams = HiperparametrosPPO(
        learning_rate = hp["learning_rate"],
        gamma         = hp["gamma"],
        clip_range    = hp["clip_range"],
        n_steps       = hp["n_steps"],
        batch_size    = hp["batch_size"],
        n_epochs      = hp["n_epochs"],
        ent_coef      = hp["ent_coef"],
        gae_lambda    = hp["gae_lambda"],
        vf_coef       = hp["vf_coef"],
        max_grad_norm = hp["max_grad_norm"],
    )
    pesos = PesosRecompensa(
        lambda_gradient = pw["lambda_gradient"],
        lambda_entropy  = pw["lambda_entropy"],
        lambda_ibrm     = pw["lambda_ibrm"],
        lambda_cbf      = pw["lambda_cbf"],
    )
    return hparams, pesos


# ══════════════════════════════════════════════════════════════════════════════
# Entrenamiento
# ══════════════════════════════════════════════════════════════════════════════
def entrenar(hparams: HiperparametrosPPO, pesos: PesosRecompensa) -> Path:
    """
    Entrena 500k steps SIN VecNormalize, guarda checkpoints cada 100k.
    Retorna la ruta al modelo final (último checkpoint).
    """
    config_env = ConfigEntorno(
        n_agentes    = N_AGENTES,
        max_steps_ep = MAX_STEPS_EP,
        domain_rand  = True,
    )
    config_train = ConfigEntrenamiento(
        n_envs_entren = N_ENVS_ENTREN,
        n_envs_eval   = 2,
        seed          = SEED,
    )

    # VecMonitor envoltorio (SIN VecNormalize — ése es el cambio clave)
    env_train = construir_vec_env_entrenamiento(
        config_env   = config_env,
        config_train = config_train,
        pesos_rew    = pesos,
        n_envs       = N_ENVS_ENTREN,
        seed         = SEED,
    )
    logger.info(
        "Entrenamiento construido: %d agentes × %d envs = %d streams  [SIN VecNormalize]",
        N_AGENTES, N_ENVS_ENTREN, env_train.num_envs,
    )

    # Modelo PPO (el construir_modelo_ppo de train.py acepta el env y escribe TB)
    modelo = construir_modelo_ppo(
        env             = env_train,
        hparams         = hparams,
        config_train    = config_train,
        dir_tensorboard = str(DIR_TB),
        seed            = SEED,
        verbose         = 1,
    )

    # Bug fix callback freq: save_freq se compara contra n_calls
    num_envs = env_train.num_envs
    save_freq_calls = max(1, FREQ_CHECKPOINT_TS // num_envs)  # 100k/20 = 5000
    logger.info(
        "CheckpointCallback: num_envs=%d → save_freq=%d n_calls (≈%d timesteps)",
        num_envs, save_freq_calls, save_freq_calls * num_envs,
    )

    cb_ckpt = CheckpointCallback(
        save_freq  = save_freq_calls,
        save_path  = str(DIR_CKPT),
        name_prefix= "ppo_diag",
        verbose    = 0,
    )

    t_ini = time.time()
    try:
        modelo.learn(
            total_timesteps     = N_PASOS_TOTAL,
            callback            = cb_ckpt,
            progress_bar        = False,
            reset_num_timesteps = True,
            tb_log_name         = "diagnostico",
        )
    finally:
        try: env_train.close()
        except Exception: pass

    dur_min = (time.time() - t_ini) / 60.0
    logger.info("Entrenamiento terminado en %.1f min (%d steps)", dur_min, N_PASOS_TOTAL)

    # El último checkpoint se nombra ppo_diag_{N_PASOS_TOTAL}_steps.zip
    ruta_final = DIR_CKPT / f"ppo_diag_{N_PASOS_TOTAL}_steps.zip"
    if not ruta_final.exists():
        # fallback: último existente
        candidatos = sorted(DIR_CKPT.glob("ppo_diag_*_steps.zip"))
        if not candidatos:
            raise FileNotFoundError("No se guardó ningún checkpoint.")
        ruta_final = candidatos[-1]
        logger.warning("Último checkpoint esperado no existe, usando %s", ruta_final.name)
    return ruta_final


# ══════════════════════════════════════════════════════════════════════════════
# Evaluación determinista de un checkpoint (raw PZ env)
# ══════════════════════════════════════════════════════════════════════════════
def evaluar_checkpoint(
    ruta_modelo: Path,
    pesos:       PesosRecompensa,
    n_episodios: int,
) -> Dict[str, Any]:
    """
    Carga un checkpoint y lo evalúa en n_episodios episodios deterministas
    sin domain_rand. Retorna agregados y lista de episodios crudos.
    """
    modelo = PPO.load(str(ruta_modelo))

    pesos_dict = {
        "lambda_gradient": pesos.lambda_gradient,
        "lambda_entropy":  pesos.lambda_entropy,
        "lambda_ibrm":     pesos.lambda_ibrm,
        "lambda_cbf":      pesos.lambda_cbf,
    }

    env = make_env(
        n_agents       = N_AGENTES,
        arena_size     = ARENA,
        max_steps      = MAX_STEPS_EP,
        comm_radius    = COMM_RADIUS,
        reward_weights = pesos_dict,
        domain_rand    = False,
        seed           = SEED,
    )

    resultados: List[Dict[str, float]] = []
    t_ini = time.time()
    for i in range(n_episodios):
        seed_ep = SEED * 10_000 + i
        obs_dict, _ = env.reset(seed=seed_ep)
        agents = list(obs_dict.keys())
        n_a    = len(agents)

        pares_col: set = set()
        pos_hist: List[np.ndarray] = [np.array([env._estados[a][:2] for a in agents])]
        cob_hist: List[float] = []

        done = False
        while not done:
            obs_arr   = np.stack([obs_dict[a] for a in agents])
            acciones, _ = modelo.predict(obs_arr, deterministic=True)
            accion_dict = {a: acciones[k] for k, a in enumerate(agents)}
            obs_dict, _, term, trunc, _ = env.step(accion_dict)

            cob_hist.append(1.0 - float(np.mean(env._field._grid_aoi)))

            pos_curr = np.array([env._estados[a][:2] for a in agents])
            pos_hist.append(pos_curr.copy())
            for ii in range(n_a):
                for jj in range(ii + 1, n_a):
                    if np.linalg.norm(pos_curr[ii] - pos_curr[jj]) < D_SAFE:
                        pares_col.add((ii, jj))

            done = all(trunc.values()) or all(term.values())

        cobertura_final = cob_hist[-1] if cob_hist else 0.0
        pos_arr = np.asarray(pos_hist)
        dist_mean = float(np.mean(np.linalg.norm(np.diff(pos_arr, axis=0), axis=2).sum(axis=0)))

        resultados.append({
            "episodio":              i,
            "cobertura_aoi_final":   cobertura_final,
            "n_colisiones":          len(pares_col),
            "distancia_recorrida":   dist_mean,
        })

    dur = time.time() - t_ini

    try: env.close()
    except Exception: pass

    claves = ["cobertura_aoi_final", "n_colisiones", "distancia_recorrida"]
    agg: Dict[str, Dict[str, float]] = {}
    for k in claves:
        vals = np.array([r[k] for r in resultados], dtype=np.float64)
        agg[k] = {
            "media": float(np.mean(vals)),
            "std":   float(np.std(vals)),
            "min":   float(np.min(vals)),
            "max":   float(np.max(vals)),
        }
    return {"agregados": agg, "episodios": resultados, "duracion_s": dur}


# ══════════════════════════════════════════════════════════════════════════════
# Figura 2-paneles
# ══════════════════════════════════════════════════════════════════════════════
def generar_figura(resultados_por_ckpt: List[Dict[str, Any]], ruta_png: Path) -> None:
    steps = np.array([r["step"] for r in resultados_por_ckpt], dtype=np.float64)
    cob_m = np.array([r["agregados"]["cobertura_aoi_final"]["media"] for r in resultados_por_ckpt])
    cob_s = np.array([r["agregados"]["cobertura_aoi_final"]["std"]   for r in resultados_por_ckpt])
    col_m = np.array([r["agregados"]["n_colisiones"]["media"]        for r in resultados_por_ckpt])
    col_s = np.array([r["agregados"]["n_colisiones"]["std"]          for r in resultados_por_ckpt])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 7), sharex=True)

    ax1.errorbar(steps / 1000, cob_m, yerr=cob_s, marker="o", capsize=4, color="tab:blue", lw=2)
    ax1.axhline(COB_OPCION_A, color="green", ls="--", lw=1, alpha=0.7, label=f"Umbral OPCION_A ({COB_OPCION_A})")
    ax1.axhline(COB_BANDA_TECHO[0], color="gold", ls="--", lw=1, alpha=0.7, label=f"Banda techo [{COB_BANDA_TECHO[0]}, {COB_BANDA_TECHO[1]}]")
    ax1.axhline(COB_BANDA_TECHO[1], color="gold", ls="--", lw=1, alpha=0.7)
    ax1.axhline(COB_PROBLEMA, color="red", ls="--", lw=1, alpha=0.7, label=f"Umbral problema ({COB_PROBLEMA})")
    ax1.set_ylabel("Cobertura AoI final")
    ax1.set_title("Diagnóstico SIN VecNormalize — Trial 13, seed 42, 20 eps det por checkpoint")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="lower right", fontsize=8)

    ax2.errorbar(steps / 1000, col_m, yerr=col_s, marker="s", capsize=4, color="tab:red", lw=2)
    ax2.axhline(COL_ADVERTENCIA, color="red", ls="--", lw=1, alpha=0.7, label=f"Advertencia ({COL_ADVERTENCIA})")
    ax2.set_xlabel("Timesteps (k)")
    ax2.set_ylabel("Pares en colisión / ep")
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc="upper right", fontsize=8)

    plt.tight_layout()
    fig.savefig(ruta_png, dpi=300, bbox_inches="tight")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
# Criterio de decisión
# ══════════════════════════════════════════════════════════════════════════════
def aplicar_criterio(resultados_por_ckpt: List[Dict[str, Any]]) -> Dict[str, str]:
    cob_por_step = {r["step"]: r["agregados"]["cobertura_aoi_final"]["media"] for r in resultados_por_ckpt}
    col_por_step = {r["step"]: r["agregados"]["n_colisiones"]["media"] for r in resultados_por_ckpt}

    cob_500 = cob_por_step.get(500_000, None)
    cob_400 = cob_por_step.get(400_000, None)
    cob_300 = cob_por_step.get(300_000, None)

    if cob_500 is None:
        return {"categoria": "ERROR", "mensaje": "Falta checkpoint 500k"}

    # Criterio principal
    if cob_500 > COB_OPCION_A and cob_500 > cob_400 and cob_400 > cob_300:
        categoria = "OPCION_A_VALIDADA"
        mensaje = (
            f"cob@500k={cob_500:.3f} > {COB_OPCION_A} y tendencia estrictamente creciente "
            f"300k→400k→500k ({cob_300:.3f}→{cob_400:.3f}→{cob_500:.3f}). "
            "**Proceder a 5M SIN VecNormalize** con alta confianza."
        )
    elif cob_500 > COB_OPCION_A:
        categoria = "OPCION_A_VALIDADA_CON_OSCILACION"
        mensaje = (
            f"cob@500k={cob_500:.3f} > {COB_OPCION_A} pero la trayectoria 300k-500k no es "
            f"estrictamente creciente ({cob_300:.3f}→{cob_400:.3f}→{cob_500:.3f}). "
            "Proceder a 5M es razonable pero esperar oscilaciones."
        )
    elif cob_500 < COB_PROBLEMA:
        categoria = "PROBLEMA_NO_DIAGNOSTICADO"
        mensaje = (
            f"cob@500k={cob_500:.3f} < {COB_PROBLEMA}. VecNormalize NO era el único culpable. "
            "Investigar más antes de cualquier corrida larga."
        )
    else:
        # Zona [COB_PROBLEMA, COB_OPCION_A]. Chequear si plana.
        if cob_300 is not None and cob_400 is not None:
            delta_max = max(abs(cob_500 - cob_400), abs(cob_400 - cob_300), abs(cob_500 - cob_300))
            plana = delta_max < DELTA_TECHO
            en_banda = (COB_BANDA_TECHO[0] <= cob_500 <= COB_BANDA_TECHO[1])
            if plana and en_banda:
                categoria = "TECHO_DETECTADO"
                mensaje = (
                    f"Cobertura plana en banda [{COB_BANDA_TECHO[0]}, {COB_BANDA_TECHO[1]}] "
                    f"(Δmax={delta_max:.3f} < {DELTA_TECHO} entre 300k-500k). "
                    "Aceptar 200k o pasar a tesis_v2."
                )
            else:
                categoria = "PROGRESO_MARGINAL"
                mensaje = (
                    f"cob@500k={cob_500:.3f} en zona intermedia pero con movimiento "
                    f"(Δmax={delta_max:.3f}). Trayectoria: {cob_300:.3f}→{cob_400:.3f}→{cob_500:.3f}. "
                    "Decisión humana requerida."
                )
        else:
            categoria = "DATOS_INCOMPLETOS"
            mensaje = f"cob@500k={cob_500:.3f} pero faltan checkpoints intermedios."

    # Advertencia ortogonal por colisiones
    cols_altas = {s: c for s, c in col_por_step.items() if c > COL_ADVERTENCIA}
    advertencia = ""
    if cols_altas:
        pares = ", ".join(f"{s//1000}k={c:.2f}" for s, c in sorted(cols_altas.items()))
        advertencia = f"⚠ Colisiones > {COL_ADVERTENCIA} en: {pares}"

    return {"categoria": categoria, "mensaje": mensaje, "advertencia_col": advertencia}


# ══════════════════════════════════════════════════════════════════════════════
# Reporte markdown
# ══════════════════════════════════════════════════════════════════════════════
def generar_reporte(
    resultados_por_ckpt: List[Dict[str, Any]],
    criterio:            Dict[str, str],
    dur_train_min:       float,
    dur_eval_s:          float,
    ruta_md:             Path,
) -> None:
    from datetime import datetime
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: List[str] = []
    lines.append("# Diagnóstico SIN VecNormalize — Trial 13, seed 42, 500k steps")
    lines.append("")
    lines.append(f"*Generado: {ahora}*")
    lines.append("")
    lines.append("## Objetivo")
    lines.append("")
    lines.append(
        "Aislar el efecto de VecNormalize. La corrida 5M con VecNormalize dio un "
        "modelo peor (cob=0.626, col=0.98) que el 200k del A/B test SIN VecNormalize "
        "(cob=0.680, col=0.20). Este experimento entrena 500k steps con idéntica "
        "configuración EXCEPTO que omitimos VecNormalize, y evalúa cada 100k."
    )
    lines.append("")
    lines.append("## Configuración")
    lines.append("")
    lines.append(f"- **Steps totales:** {N_PASOS_TOTAL:,}")
    lines.append(f"- **Checkpoints cada:** {FREQ_CHECKPOINT_TS:,} timesteps")
    lines.append(f"- **Episodios de eval por checkpoint:** {N_EPISODIOS_EVAL} (deterministas, SIN domain_rand)")
    lines.append(f"- **n_agentes:** {N_AGENTES}  —  **max_steps_ep:** {MAX_STEPS_EP}  —  **n_envs:** {N_ENVS_ENTREN}  —  **seed:** {SEED}")
    lines.append(f"- **Duración entrenamiento:** {dur_train_min:.1f} min")
    lines.append(f"- **Duración evaluación total:** {dur_eval_s/60:.1f} min")
    lines.append("")
    lines.append("## Tabla por checkpoint")
    lines.append("")
    lines.append("| Step | Cobertura AoI (μ±σ) | Pares colisión/ep (μ±σ) | Distancia (μ) |")
    lines.append("|-----:|--------------------:|------------------------:|--------------:|")
    for r in resultados_por_ckpt:
        ag = r["agregados"]
        lines.append(
            f"| {r['step']//1000}k "
            f"| {ag['cobertura_aoi_final']['media']:.3f}±{ag['cobertura_aoi_final']['std']:.3f} "
            f"| {ag['n_colisiones']['media']:.2f}±{ag['n_colisiones']['std']:.2f} "
            f"| {ag['distancia_recorrida']['media']:.2f} |"
        )
    lines.append("")
    lines.append("## Comparación cruzada con experimentos previos")
    lines.append("")
    lines.append("| Presupuesto | Config | Cobertura | Colisiones/ep |")
    lines.append("|------------:|--------|----------:|--------------:|")
    lines.append("| 100k (seed 42, reproducibilidad) | sin VN | 0.698 ± 0.018 | 0.53 ± 0.72 |")
    lines.append("| 200k (variante A, A/B test) | sin VN | 0.680 ± 0.021 | 0.20 ± 0.48 |")
    ckpt_500 = next((r for r in resultados_por_ckpt if r["step"] == 500_000), None)
    if ckpt_500:
        ag = ckpt_500["agregados"]
        lines.append(
            f"| **500k (este diagnóstico)** | sin VN | "
            f"**{ag['cobertura_aoi_final']['media']:.3f} ± {ag['cobertura_aoi_final']['std']:.3f}** | "
            f"**{ag['n_colisiones']['media']:.2f} ± {ag['n_colisiones']['std']:.2f}** |"
        )
    lines.append("| 2.5M (corrida 5M abortada) | CON VN | 0.626 ± 0.028 | 0.98 ± 1.05 |")
    lines.append("")
    lines.append("## Criterio de decisión")
    lines.append("")
    lines.append(f"### Resultado: **{criterio['categoria']}**")
    lines.append("")
    lines.append(criterio["mensaje"])
    lines.append("")
    if criterio.get("advertencia_col"):
        lines.append(f"{criterio['advertencia_col']}")
        lines.append("")
    lines.append("## Figura")
    lines.append("")
    lines.append("![Curva diagnóstico](curva_diagnostico.png)")
    lines.append("")
    lines.append("## Archivos generados")
    lines.append("")
    lines.append("- `checkpoints/ppo_diag_{100000,200000,300000,400000,500000}_steps.zip`")
    lines.append("- `tensorboard/` — logs de entrenamiento")
    lines.append("- `curva_diagnostico.png` — figura de 2 paneles")
    lines.append("- `metricas_checkpoints.json` — datos crudos por episodio")
    lines.append("- `diagnostico.log` — log completo")
    lines.append("")

    with open(ruta_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    logger.info("=" * 70)
    logger.info("DIAGNÓSTICO SIN VecNormalize — Trial 13 — seed %d — %d steps", SEED, N_PASOS_TOTAL)
    logger.info("=" * 70)

    hparams, pesos = cargar_trial_13()
    logger.info("Hparams:  lr=%.2e  γ=%.4f  n_steps=%d  batch=%d  ent_coef=%.4f",
                hparams.learning_rate, hparams.gamma, hparams.n_steps,
                hparams.batch_size, hparams.ent_coef)
    logger.info("Pesos:    λ_grad=%.3f  λ_ent=%.3f  λ_ibrm=%.3f  λ_cbf=%.3f",
                pesos.lambda_gradient, pesos.lambda_entropy,
                pesos.lambda_ibrm, pesos.lambda_cbf)

    # ── FASE 1: ENTRENAMIENTO (short-circuit si checkpoints ya existen) ─
    checkpoints_esperados = [DIR_CKPT / f"ppo_diag_{s}_steps.zip"
                             for s in (100_000, 200_000, 300_000, 400_000, 500_000)]
    if all(p.exists() for p in checkpoints_esperados):
        logger.info("FASE 1: checkpoints ya existen, saltando entrenamiento.")
        dur_train_min = 0.0
    else:
        t0 = time.time()
        entrenar(hparams, pesos)
        dur_train_min = (time.time() - t0) / 60.0
        logger.info("FASE 1 terminada: %.1f min", dur_train_min)

    # ── FASE 2: EVALUACIÓN DE CADA CHECKPOINT ────────────────────────────
    logger.info("=" * 70)
    logger.info("FASE 2: evaluación de 5 checkpoints × %d eps det", N_EPISODIOS_EVAL)
    logger.info("=" * 70)

    resultados_por_ckpt: List[Dict[str, Any]] = []
    t1 = time.time()
    for step in (100_000, 200_000, 300_000, 400_000, 500_000):
        ruta_ck = DIR_CKPT / f"ppo_diag_{step}_steps.zip"
        if not ruta_ck.exists():
            logger.error("Checkpoint %d no existe en %s — saltando.", step, ruta_ck)
            continue
        logger.info("Evaluando checkpoint %dk...", step // 1000)
        res = evaluar_checkpoint(ruta_ck, pesos, N_EPISODIOS_EVAL)
        res["step"] = step
        ag = res["agregados"]
        logger.info(
            "  step=%dk  cob=%.3f±%.3f  col=%.2f±%.2f  dist=%.2f  (dur=%.1fs)",
            step // 1000,
            ag["cobertura_aoi_final"]["media"], ag["cobertura_aoi_final"]["std"],
            ag["n_colisiones"]["media"],        ag["n_colisiones"]["std"],
            ag["distancia_recorrida"]["media"],
            res["duracion_s"],
        )
        resultados_por_ckpt.append(res)
    dur_eval_s = time.time() - t1

    if not resultados_por_ckpt:
        logger.error("Ningún checkpoint evaluable. Abortando reporte.")
        return

    # ── FASE 3: ARTEFACTOS ────────────────────────────────────────────────
    logger.info("=" * 70)
    logger.info("FASE 3: generando artefactos")
    logger.info("=" * 70)

    # JSON crudo
    ruta_json = DIR_BASE / "metricas_checkpoints.json"
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump({
            "config": {
                "n_pasos_total":     N_PASOS_TOTAL,
                "freq_checkpoint":   FREQ_CHECKPOINT_TS,
                "n_episodios_eval":  N_EPISODIOS_EVAL,
                "seed":              SEED,
                "vecnormalize":      False,
            },
            "dur_train_min": dur_train_min,
            "dur_eval_s":    dur_eval_s,
            "resultados":    resultados_por_ckpt,
        }, f, indent=2, ensure_ascii=False)
    logger.info("JSON → %s", ruta_json.name)

    # Figura
    ruta_png = DIR_BASE / "curva_diagnostico.png"
    generar_figura(resultados_por_ckpt, ruta_png)
    logger.info("Figura → %s", ruta_png.name)

    # Criterio
    criterio = aplicar_criterio(resultados_por_ckpt)
    logger.info("=" * 70)
    logger.info("CRITERIO: %s", criterio["categoria"])
    logger.info("%s", criterio["mensaje"])
    if criterio.get("advertencia_col"):
        logger.info("%s", criterio["advertencia_col"])
    logger.info("=" * 70)

    # Reporte
    ruta_md = DIR_BASE / "reporte_diagnostico.md"
    generar_reporte(resultados_por_ckpt, criterio, dur_train_min, dur_eval_s, ruta_md)
    logger.info("Reporte → %s", ruta_md)


if __name__ == "__main__":
    main()
