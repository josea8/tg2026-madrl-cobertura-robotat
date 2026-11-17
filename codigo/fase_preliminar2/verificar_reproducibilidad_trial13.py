"""
verificar_reproducibilidad_trial13.py
=====================================
Verificación de reproducibilidad del Trial 13 de Optuna (estudio tesis_v1).

Propósito:
    El Trial 13 obtuvo eval_rew_mean = -1.51, un valor aislado 16.7 puntos
    por encima del segundo mejor (-18.22). Trial 18, con hiperparámetros casi
    idénticos (lr≈3.6e-5 vs 6.9e-5, λ_cbf≈3.0, λ_ent≈1.7, λ_ibrm≈0.48) fue
    podado en step 10k con ep_rew ≈ -90. Esta evidencia sugiere que el valor
    del Trial 13 podría ser un outlier debido a la seed afortunada, no a los
    hiperparámetros en sí.

    Este script corre los hiperparámetros exactos del Trial 13 con 3 seeds
    independientes (42, 123, 777) a 100k steps cada uno, y aplica un criterio
    cuantitativo para decidir si proceder con la corrida de 5M o recalibrar.

Configuración de entrenamiento:
    Replica el flujo de trials de Optuna (sin VecNormalize) para que los
    resultados sean directamente comparables con el Trial 13 original.
    NOTA: en el comando original se pasó --n_envs 4, lo que internamente
    asignó n_envs_trial=2. Aquí se usa n_envs=4 siguiendo la especificación
    del plan del Día 1, lo cual incrementa la paralelización (5 × 4 = 20
    streams vs los 10 streams originales). Esto produce rollouts 2× mayores
    por actualización de PPO — es una prueba ligeramente más favorable que
    el trial original, no más estricta.

Salidas:
    modelos/tesis_v1/verificacion_seeds/
        seed_{SEED}/
            modelo_final.zip
            metricas.json
            curva_aprendizaje.csv
            tensorboard/
        curvas_3_seeds.png
        reporte_reproducibilidad.md
"""
from __future__ import annotations

import csv
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from stable_baselines3.common.callbacks import BaseCallback

# Reutilizar infraestructura de train.py
from train import (
    ConfigEntorno,
    ConfigEntrenamiento,
    HiperparametrosPPO,
    PesosRecompensa,
    construir_modelo_ppo,
    construir_vec_env_entrenamiento,
    construir_vec_env_evaluacion,
)


# ──────────────────────────────────────────────────────────────────────────────
# Configuración del experimento
# ──────────────────────────────────────────────────────────────────────────────
DIR_SALIDA:     Path      = Path("modelos/tesis_v1/verificacion_seeds")
TRIAL_13_JSON:  Path      = Path("modelos/tesis_v1/metadata_trials/trial_013.json")
SEEDS:          List[int] = [42, 123, 777]
N_PASOS:        int       = 100_000
N_EPS_EVAL:     int       = 20       # episodios deterministas por seed
FREQ_CURVA:     int       = 2_000    # cada cuántos steps muestrear ep_rew_mean

# Criterio de decisión (según spec del usuario)
UMBRAL_VERDE_RATIO:     float = 0.5   # σ/|μ| < 0.5 AND todas en [-20, +20]
UMBRAL_AMARILLO_RATIO:  float = 1.5   # σ/|μ| < 1.5 AND ninguna < -50
RANGO_VERDE:            tuple = (-20.0, 20.0)
COTA_ROJO:              float = -50.0  # alguna < -50 → ROJO

logger = logging.getLogger("verif_trial13")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(_h)


# ──────────────────────────────────────────────────────────────────────────────
# Carga de hiperparámetros del Trial 13
# ──────────────────────────────────────────────────────────────────────────────
def cargar_trial13() -> tuple[HiperparametrosPPO, PesosRecompensa, float]:
    """Carga los hiperparámetros exactos del Trial 13 desde su metadata JSON."""
    with open(TRIAL_13_JSON, encoding="utf-8") as f:
        meta = json.load(f)
    hparams = HiperparametrosPPO(**meta["hparams"])
    pesos   = PesosRecompensa(**meta["pesos_recompensa"])
    return hparams, pesos, float(meta["metrica"])


# ──────────────────────────────────────────────────────────────────────────────
# Callback de curva de aprendizaje
# ──────────────────────────────────────────────────────────────────────────────
class CallbackCurvaAprendizaje(BaseCallback):
    """
    Muestrea ep_rew_mean y ep_len_mean del buffer interno de SB3 cada
    `freq` timesteps. Los valores son el promedio rolling sobre los
    últimos ≤100 episodios (ventana de ep_info_buffer).

    Persiste los samples como lista de tuplas (step, rew, len) en
    `self.datos` para exportar a CSV después.
    """

    def __init__(self, freq: int = 2_000, verbose: int = 0) -> None:
        super().__init__(verbose=verbose)
        self.freq:    int                              = freq
        self.datos:   List[tuple[int, float, float]]   = []
        self._ultimo: int                              = 0

    def _on_step(self) -> bool:
        if self.num_timesteps - self._ultimo < self.freq:
            return True
        self._ultimo = self.num_timesteps

        buf = self.model.ep_info_buffer
        if buf is None or len(buf) == 0:
            return True

        rew = float(np.mean([ep["r"] for ep in buf]))
        lon = float(np.mean([ep["l"] for ep in buf]))
        self.datos.append((self.num_timesteps, rew, lon))
        return True


# ──────────────────────────────────────────────────────────────────────────────
# Evaluación determinista con métricas multi-eje
# ──────────────────────────────────────────────────────────────────────────────
def evaluar_modelo_multi_metrica(
    modelo,
    env_eval,
    n_episodios: int,
) -> Dict[str, Any]:
    """
    Evalúa el modelo de forma determinista sobre `n_episodios` stream-episodios.

    Métricas reportadas:
        eval_rew_mean         : recompensa episódica media
        eval_rew_std          : desviación estándar de la recompensa episódica
        ep_len_mean           : longitud media de episodio
        cobertura_aoi_mean    : cobertura AoI global promediada sobre todos
                                los steps de todos los episodios
        n_episodios_completados : cuántos episodios se completaron realmente

    Nota sobre n_streams:
        En este setup (PettingZoo + SuperSuit), n_streams = n_agentes × n_envs_eval.
        Un "episodio" aquí es un stream-episodio: cuando una (agente, env)
        termina. Como todos los agentes terminan simultáneamente por truncación,
        20 stream-eps ≈ 4 env-eps globales (con n_agentes=5).
    """
    n_streams   = env_eval.num_envs
    rew_acum    = np.zeros(n_streams, dtype=np.float64)
    len_acum    = np.zeros(n_streams, dtype=np.int64)
    cov_streams: List[List[float]] = [[] for _ in range(n_streams)]

    ep_rewards:  List[float] = []
    ep_lens:     List[int]   = []
    ep_cov:      List[float] = []
    completos:   int         = 0
    max_steps   = n_episodios * 2_000  # safety cap

    obs = env_eval.reset()
    for _ in range(max_steps):
        accion, _ = modelo.predict(obs, deterministic=True)
        obs, rewards, dones, infos = env_eval.step(accion)
        rew_acum += np.asarray(rewards, dtype=np.float64)
        len_acum += 1

        for i, info in enumerate(infos):
            if isinstance(info, dict) and "cobertura_aoi" in info:
                cov_streams[i].append(float(info["cobertura_aoi"]))

        for idx, done in enumerate(dones):
            if not done:
                continue
            ep_rewards.append(float(rew_acum[idx]))
            ep_lens.append(int(len_acum[idx]))
            if cov_streams[idx]:
                ep_cov.append(float(np.mean(cov_streams[idx])))
            rew_acum[idx]   = 0.0
            len_acum[idx]   = 0
            cov_streams[idx] = []
            completos += 1
            if completos >= n_episodios:
                break
        if completos >= n_episodios:
            break

    if not ep_rewards:
        logger.warning("Ningún episodio completado durante la evaluación.")
        return {
            "eval_rew_mean":           -1e9,
            "eval_rew_std":            0.0,
            "ep_len_mean":             0.0,
            "cobertura_aoi_mean":      None,
            "n_episodios_completados": 0,
        }

    return {
        "eval_rew_mean":           float(np.mean(ep_rewards)),
        "eval_rew_std":            float(np.std(ep_rewards)),
        "ep_len_mean":             float(np.mean(ep_lens)),
        "cobertura_aoi_mean":      (float(np.mean(ep_cov)) if ep_cov else None),
        "n_episodios_completados": completos,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Entrenamiento + evaluación para una seed
# ──────────────────────────────────────────────────────────────────────────────
def correr_seed(
    seed:    int,
    hparams: HiperparametrosPPO,
    pesos:   PesosRecompensa,
) -> Dict[str, Any]:
    """Entrena 100k steps con `seed` y evalúa en 20 episodios deterministas."""
    dir_seed = DIR_SALIDA / f"seed_{seed}"
    dir_seed.mkdir(parents=True, exist_ok=True)

    config_env = ConfigEntorno(
        n_agentes    = 5,
        max_steps_ep = 500,
        domain_rand  = True,   # realista durante entrenamiento
    )
    config_train = ConfigEntrenamiento(
        n_envs_entren = 4,
        n_envs_eval   = 2,
        seed          = seed,
    )

    env_train = None
    env_eval  = None
    modelo    = None
    metricas: Dict[str, Any]

    try:
        logger.info("━" * 60)
        logger.info("SEED %d — entrenando %d steps", seed, N_PASOS)
        logger.info("━" * 60)

        env_train = construir_vec_env_entrenamiento(
            config_env   = config_env,
            config_train = config_train,
            pesos_rew    = pesos,
            n_envs       = 4,
            seed         = seed,
        )
        env_eval = construir_vec_env_evaluacion(
            config_env   = config_env,
            config_train = config_train,
            pesos_rew    = pesos,
            seed         = seed + 500,
        )

        dir_tb = dir_seed / "tensorboard"
        modelo = construir_modelo_ppo(
            env             = env_train,
            hparams         = hparams,
            config_train    = config_train,
            dir_tensorboard = str(dir_tb),
            seed            = seed,
            verbose         = 0,
        )

        cb_curva = CallbackCurvaAprendizaje(freq=FREQ_CURVA)

        t_ini = time.time()
        modelo.learn(
            total_timesteps     = N_PASOS,
            callback            = cb_curva,
            reset_num_timesteps = True,
            tb_log_name         = f"seed_{seed}",
            progress_bar        = False,
        )
        dur_s = time.time() - t_ini

        # ── Guardar modelo entrenado ──────────────────────────────────────
        ruta_modelo = dir_seed / "modelo_final.zip"
        modelo.save(str(ruta_modelo))
        logger.info("  Modelo guardado: %s", ruta_modelo)

        # ── Exportar curva de aprendizaje a CSV ───────────────────────────
        ruta_csv = dir_seed / "curva_aprendizaje.csv"
        with open(ruta_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["timesteps", "ep_rew_mean", "ep_len_mean"])
            w.writerows(cb_curva.datos)
        logger.info("  Curva CSV: %s (%d samples)", ruta_csv, len(cb_curva.datos))

        # ── Evaluación determinista ───────────────────────────────────────
        metricas = evaluar_modelo_multi_metrica(modelo, env_eval, N_EPS_EVAL)
        metricas["seed"]                       = seed
        metricas["duracion_entrenamiento_s"]   = dur_s
        metricas["n_pasos_entrenamiento"]      = N_PASOS

        ruta_m = dir_seed / "metricas.json"
        with open(ruta_m, "w", encoding="utf-8") as f:
            json.dump(metricas, f, indent=2, ensure_ascii=False)

        logger.info(
            "SEED %d TERMINADA — eval_rew=%.3f ± %.3f  (entr. %.1fs)",
            seed, metricas["eval_rew_mean"], metricas["eval_rew_std"], dur_s,
        )

        return metricas

    finally:
        if env_train is not None:
            try: env_train.close()
            except Exception: pass
        if env_eval is not None:
            try: env_eval.close()
            except Exception: pass


# ──────────────────────────────────────────────────────────────────────────────
# Figura comparativa
# ──────────────────────────────────────────────────────────────────────────────
def generar_figura_comparativa(
    resultados:       List[Dict[str, Any]],
    metrica_original: float,
    ruta_png:         Path,
) -> None:
    """Grafica las 3 curvas de ep_rew_mean vs timesteps con línea de Trial 13."""
    fig, ax = plt.subplots(figsize=(10, 6))
    colores = {42: "tab:blue", 123: "tab:orange", 777: "tab:green"}

    for r in resultados:
        seed = r["seed"]
        ruta_csv = DIR_SALIDA / f"seed_{seed}" / "curva_aprendizaje.csv"
        if not ruta_csv.exists():
            continue
        with open(ruta_csv, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # header
            filas = [(int(row[0]), float(row[1])) for row in reader]
        if not filas:
            continue
        xs, ys = zip(*filas)
        ax.plot(
            xs, ys,
            label=f"seed={seed}  (final={r['eval_rew_mean']:.2f})",
            color=colores.get(seed, "gray"),
            linewidth=1.8,
            alpha=0.9,
        )

    ax.axhline(
        metrica_original,
        color="red", linestyle="--", linewidth=1.5, alpha=0.75,
        label=f"Trial 13 original ({metrica_original:.2f})",
    )
    ax.set_xlabel("Timesteps",  fontsize=12)
    ax.set_ylabel("ep_rew_mean (rolling SB3)", fontsize=12)
    ax.set_title(
        "Reproducibilidad Trial 13 — 3 seeds independientes",
        fontsize=13, pad=10,
    )
    ax.legend(loc="best", fontsize=10, framealpha=0.9)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    fig.savefig(ruta_png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logger.info("Figura guardada: %s", ruta_png)


# ──────────────────────────────────────────────────────────────────────────────
# Criterio de decisión y reporte
# ──────────────────────────────────────────────────────────────────────────────
def aplicar_criterio(resultados: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aplica el criterio VERDE/AMARILLO/ROJO sobre los eval_rew_mean de las seeds.

    VERDE    : σ/|μ| < 0.5  AND  todas en [-20, +20]
    AMARILLO : 0.5 ≤ σ/|μ| < 1.5  AND  ninguna < -50
    ROJO     : σ/|μ| ≥ 1.5  OR  alguna < -50
    """
    vals = [r["eval_rew_mean"] for r in resultados]
    mu   = float(np.mean(vals))
    sig  = float(np.std(vals))
    ratio = sig / abs(mu) if abs(mu) > 1e-9 else float("inf")

    todas_en_rango = all(RANGO_VERDE[0] <= v <= RANGO_VERDE[1] for v in vals)
    alguna_critica = any(v < COTA_ROJO for v in vals)

    if alguna_critica or ratio >= UMBRAL_AMARILLO_RATIO:
        crit = "ROJO"
        rec = (
            "La reproducibilidad es insuficiente. Trial 13 parece haber sido "
            "un outlier por seed. **No proceder al Día 2.** Recalibrar:\n"
            "  1. Relanzar Optuna (estudio `tesis_v2`) con 20 trials adicionales.\n"
            "  2. Restringir `λ_cbf ∈ [1.0, 5.0]` (por encima de 5 es veneno).\n"
            "  3. Restringir `n_steps_exp ∈ [7, 9]` (128–512, donde viven los mejores).\n"
            "  4. Considerar correr cada trial con 2 seeds y promediar para "
            "mitigar varianza inter-seed."
        )
    elif ratio >= UMBRAL_VERDE_RATIO or not todas_en_rango:
        crit = "AMARILLO"
        rec = (
            "Varianza alta pero tolerable. **Discutir antes de proceder al "
            "Día 2.** Opciones:\n"
            "  1. Proceder a 5M aceptando el riesgo (puede converger peor).\n"
            "  2. Correr 3 seeds más (2024, 2026, 1337) para n=6 y reevaluar.\n"
            "  3. Hacer una pasada Optuna corta (10 trials × 100k) con espacio "
            "reducido para buscar un régimen más estable."
        )
    else:
        crit = "VERDE"
        rec = (
            "Los hiperparámetros del Trial 13 son reproducibles. **Proceder al "
            "Día 2 (corrida 5M)** usando `python train.py --modo entrenar "
            "--nombre_estudio tesis_v1 --n_pasos 5000000 --n_agentes 5 "
            "--max_steps_ep 500 --n_envs 4 --seed 42`."
        )

    return {
        "media":          mu,
        "desv_std":       sig,
        "rango":          (float(min(vals)), float(max(vals))),
        "coef_variacion": ratio,
        "criterio":       crit,
        "recomendacion":  rec,
    }


def generar_reporte_markdown(
    resultados:       List[Dict[str, Any]],
    metrica_original: float,
    diagnostico:      Dict[str, Any],
    ruta_md:          Path,
) -> None:
    """Genera el reporte markdown consolidado."""
    vals = [r["eval_rew_mean"] for r in resultados]
    mu, sig = diagnostico["media"], diagnostico["desv_std"]
    rng = diagnostico["rango"]
    ratio = diagnostico["coef_variacion"]
    crit  = diagnostico["criterio"]

    lineas: List[str] = [
        "# Reporte de Reproducibilidad — Trial 13 (tesis_v1)",
        "",
        f"*Generado: {time.strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
        "## Contexto",
        "",
        (f"El Trial 13 del estudio Optuna `tesis_v1` obtuvo "
         f"`eval_rew_mean = {metrica_original:.4f}`, un outlier de 16.7 puntos "
         "por encima del segundo mejor (-18.22). Trial 18, con hiperparámetros "
         "casi idénticos, fue **podado** en step 10k con ep_rew ≈ -90. Este "
         "experimento verifica si el valor del Trial 13 es reproducible bajo "
         "3 seeds independientes (42, 123, 777)."),
        "",
        "## Configuración",
        "",
        "- **Hiperparámetros:** exactos del Trial 13 (`modelos/tesis_v1/metadata_trials/trial_013.json`)",
        "- **n_agentes:** 5 — **max_steps_ep:** 500 — **n_envs:** 4 — **domain_rand:** True (train) / False (eval)",
        f"- **Presupuesto por seed:** {N_PASOS:,} steps",
        f"- **Evaluación:** {N_EPS_EVAL} stream-episodios deterministas",
        "- **Arquitectura de env:** idéntica al flujo de trials de Optuna (sin VecNormalize) para comparabilidad directa",
        "",
        "## Resultados por seed",
        "",
        "| Seed | eval_rew_mean | eval_rew_std | ep_len_mean | cobertura_aoi_mean | Duración (s) |",
        "|-----:|--------------:|-------------:|------------:|-------------------:|-------------:|",
    ]
    for r in resultados:
        cov = r.get("cobertura_aoi_mean")
        cov_str = f"{cov:.4f}" if cov is not None else "N/A"
        lineas.append(
            f"| {r['seed']} | {r['eval_rew_mean']:.3f} | {r['eval_rew_std']:.3f} "
            f"| {r['ep_len_mean']:.1f} | {cov_str} | "
            f"{r['duracion_entrenamiento_s']:.1f} |"
        )

    lineas += [
        "",
        f"**Trial 13 original (referencia):** {metrica_original:.4f}",
        "",
        "## Estadísticos agregados",
        "",
        f"- **Media (μ):** {mu:.3f}",
        f"- **Desviación estándar (σ):** {sig:.3f}",
        f"- **Rango:** [{rng[0]:.3f}, {rng[1]:.3f}]",
        f"- **Coeficiente de variación (σ/|μ|):** {ratio:.3f}",
        "",
        "## Criterio de decisión",
        "",
        "| Criterio | Condición | Acción |",
        "|----------|-----------|--------|",
        f"| 🟢 VERDE | σ/|μ| < {UMBRAL_VERDE_RATIO} AND todas ∈ [{RANGO_VERDE[0]:.0f}, {RANGO_VERDE[1]:.0f}] | Proceder a 5M |",
        f"| 🟡 AMARILLO | {UMBRAL_VERDE_RATIO} ≤ σ/|μ| < {UMBRAL_AMARILLO_RATIO} AND ninguna < {COTA_ROJO:.0f} | Discutir |",
        f"| 🔴 ROJO | σ/|μ| ≥ {UMBRAL_AMARILLO_RATIO} OR alguna < {COTA_ROJO:.0f} | Recalibrar Optuna |",
        "",
        f"### Resultado: **{crit}**",
        "",
        diagnostico["recomendacion"],
        "",
        "## Figura",
        "",
        "![Curvas de aprendizaje](curvas_3_seeds.png)",
        "",
        "## Archivos generados",
        "",
    ]
    for r in resultados:
        d = f"seed_{r['seed']}/"
        lineas += [
            f"- `{d}modelo_final.zip` — checkpoint entrenado",
            f"- `{d}metricas.json` — métricas de evaluación",
            f"- `{d}curva_aprendizaje.csv` — curva ep_rew_mean vs timesteps",
            f"- `{d}tensorboard/` — logs para TensorBoard",
        ]

    ruta_md.write_text("\n".join(lineas), encoding="utf-8")
    logger.info("Reporte markdown: %s", ruta_md)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)

    hparams, pesos, metrica_original = cargar_trial13()
    logger.info("=" * 70)
    logger.info("VERIFICACIÓN DE REPRODUCIBILIDAD — TRIAL 13")
    logger.info("=" * 70)
    logger.info("Métrica original: %.4f", metrica_original)
    logger.info(
        "Hparams: lr=%.2e  γ=%.4f  clip=%.2f  n_steps=%d  batch=%d  "
        "ent=%.4f  epochs=%d",
        hparams.learning_rate, hparams.gamma, hparams.clip_range,
        hparams.n_steps, hparams.batch_size, hparams.ent_coef, hparams.n_epochs,
    )
    logger.info(
        "Pesos: λ_grad=%.3f  λ_ent=%.3f  λ_ibrm=%.3f  λ_cbf=%.3f",
        pesos.lambda_gradient, pesos.lambda_entropy,
        pesos.lambda_ibrm, pesos.lambda_cbf,
    )
    logger.info("Seeds a verificar: %s", SEEDS)
    logger.info("Presupuesto por seed: %d steps", N_PASOS)
    logger.info("")

    resultados: List[Dict[str, Any]] = []
    fallos: List[int] = []
    for seed in SEEDS:
        try:
            m = correr_seed(seed, hparams, pesos)
            resultados.append(m)
        except Exception as exc:
            logger.exception("Seed %d falló con excepción: %s", seed, exc)
            fallos.append(seed)

    if not resultados:
        logger.error("Todas las seeds fallaron. Abortando.")
        sys.exit(1)

    if fallos:
        logger.warning(
            "Seeds fallidas: %s — se aplicará el criterio con las %d seeds "
            "restantes.", fallos, len(resultados),
        )

    # ── Figura comparativa ────────────────────────────────────────────────
    ruta_png = DIR_SALIDA / "curvas_3_seeds.png"
    generar_figura_comparativa(resultados, metrica_original, ruta_png)

    # ── Criterio de decisión ──────────────────────────────────────────────
    diagnostico = aplicar_criterio(resultados)

    # ── Reporte markdown ──────────────────────────────────────────────────
    ruta_md = DIR_SALIDA / "reporte_reproducibilidad.md"
    generar_reporte_markdown(resultados, metrica_original, diagnostico, ruta_md)

    # ── Resumen en consola ────────────────────────────────────────────────
    logger.info("=" * 70)
    logger.info("RESULTADO FINAL")
    logger.info("=" * 70)
    for r in resultados:
        logger.info("  seed=%d → eval_rew = %.3f", r["seed"], r["eval_rew_mean"])
    logger.info("  μ = %.3f   σ = %.3f   σ/|μ| = %.3f",
                diagnostico["media"], diagnostico["desv_std"],
                diagnostico["coef_variacion"])
    logger.info("  CRITERIO: %s", diagnostico["criterio"])
    logger.info("  Reporte: %s", ruta_md)


if __name__ == "__main__":
    main()
