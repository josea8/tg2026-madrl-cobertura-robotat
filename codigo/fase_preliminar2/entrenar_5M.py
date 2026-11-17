"""
entrenar_5M.py
==============
Corrida FINAL de 5,000,000 steps con los hiperparámetros del Trial 13
(mejores_hiperparametros.json).

Diseño
──────
  - Reutiliza el pipeline de `train.py` (builders, modelo, callbacks base).
  - Directorios específicos para la corrida:
        modelos/tesis_v1/entrenamiento_final_5M/
            ├── checkpoints/        (cada 500k steps)
            ├── mejor_modelo/       (best_model.zip via EvalCallback, cada 100k)
            ├── vecnorm/            (snapshots de VecNormalize)
            ├── tensorboard/
            ├── curva_5M.csv        (snapshot cada 100k de cob, col, rewards)
            ├── entrenamiento_5M.log
            ├── metricas_finales.json
            ├── reporte_final.md
            └── curva_aprendizaje.png

Monitoreo en tiempo real
────────────────────────
  - Callback "CallbackMilestone5M" reporta a consola cada 1M steps el
    eval_rew, cobertura_train, colisiones_train de la ventana reciente.
  - Revisa alarma a 2.5M: si cob<0.55 O col>0.5 → raise → pausa.

Evaluación final
────────────────
  - 50 episodios deterministas sin domain_rand, usando env PettingZoo crudo
    para acceso directo a estados internos (pair-collisions, distancia).
  - Obs se normalizan manualmente con los stats de VecNormalize guardados
    (best_model se entrenó con obs normalizada).

Criterio de éxito
─────────────────
  - LISTO PARA SIM2REAL      : cob>0.80±<0.08 AND col<0.1
  - RESULTADO DEFENDIBLE      : 0.70≤cob≤0.80 (sin criterio duro en col)
  - NECESITA RECALIBRACIÓN    : cob<0.70 OR col>0.3
"""
from __future__ import annotations

import csv
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import (
    BaseCallback, CallbackList, CheckpointCallback, EvalCallback,
)
from stable_baselines3.common.vec_env import VecNormalize

# Módulos del proyecto
from train import (
    ConfigEntorno, ConfigEntrenamiento, HiperparametrosPPO, PesosRecompensa,
    construir_vec_env_entrenamiento, construir_vec_env_evaluacion,
    construir_modelo_ppo,
    CallbackMetricasPersonalizadas, _CallbackSyncVecNormalize,
    _fabrica_env,
)
from swarm_env_skeleton import D_SAFE, make_env


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURACIÓN DE RUTAS Y LOGGING
# ══════════════════════════════════════════════════════════════════════════════
ROOT = Path(__file__).parent.resolve()
DIR_BASE   = ROOT / "modelos" / "tesis_v1" / "entrenamiento_final_5M"
DIR_CKPT   = DIR_BASE / "checkpoints"
DIR_MEJOR  = DIR_BASE / "mejor_modelo"
DIR_VECNORM = DIR_BASE / "vecnorm"
DIR_TB     = DIR_BASE / "tensorboard"
for d in [DIR_BASE, DIR_CKPT, DIR_MEJOR, DIR_VECNORM, DIR_TB]:
    d.mkdir(parents=True, exist_ok=True)

_LOG_FMT = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=_LOG_FMT,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("entrenar_5M")
# Handler a fichero (persistente)
_fh = logging.FileHandler(DIR_BASE / "entrenamiento_5M.log", encoding="utf-8")
_fh.setFormatter(logging.Formatter(_LOG_FMT, datefmt="%Y-%m-%d %H:%M:%S"))
logger.addHandler(_fh)


# ══════════════════════════════════════════════════════════════════════════════
#  CARGA DE HIPERPARÁMETROS DEL TRIAL 13
# ══════════════════════════════════════════════════════════════════════════════
RUTA_HPARAMS = ROOT / "modelos" / "tesis_v1" / "mejores_hiperparametros.json"
with open(RUTA_HPARAMS, encoding="utf-8") as f:
    _best = json.load(f)

HPARAMS = HiperparametrosPPO(**_best["hparams"])
PESOS   = PesosRecompensa(**_best["pesos_recompensa"])

# Configuraciones del entorno y entrenamiento según CLI del usuario
CONFIG_ENV = ConfigEntorno(
    n_agentes=5, max_steps_ep=500, arena_size=(3.0, 3.0),
    radio_com=1.0, dt=0.1, domain_rand=True, grid_resolution=64, n_hotspots=3,
)
CONFIG_TRAIN = ConfigEntrenamiento(
    n_envs_entren=4,
    n_envs_eval=2,
    n_envs_trial=2,
    frecuencia_eval=100_000,     # EvalCallback cada 100k
    n_episodios_eval=10,         # 10 episodios det. por eval
    frecuencia_ckpt=500_000,     # Checkpoints cada 500k
    seed=42,
)
N_PASOS_TOTAL = 5_000_000


# ══════════════════════════════════════════════════════════════════════════════
#  CALLBACK DE MILESTONES + ALARMA (custom de esta corrida)
# ══════════════════════════════════════════════════════════════════════════════
class CallbackMilestone5M(BaseCallback):
    """
    Rastrea cobertura_final y n_colisiones por episodio de entrenamiento
    a partir de los infos que el env expone por cada stream (agente×env).

    Responsabilidades
    ─────────────────
      1. Mantener buffers rolling de episodios completados (stream-level).
      2. Cada 100k steps: escribir snapshot a CSV con mean/std ventana y
         el último eval_mean_reward del EvalCallback.
      3. Cada 1M steps: log INFO con resumen (se filtrará desde el monitor).
      4. A 2.5M: aplicar alarma — si cob_win < 0.55 O col_win > 0.5 →
         return False (SB3 detiene el entrenamiento limpiamente).

    Notas
    ─────
      - "cobertura_aoi" en info es fracción del grid visitada hasta ese
        step (monótona creciente en un episodio). El valor al step donde
        el env termina ≈ cobertura final del episodio para ese stream.
        Como los 5 agentes comparten el mismo env, los 5 streams que
        terminan juntos reportan el MISMO valor → sobre-muestreamos x5.
        Es aceptable: la media/std empírica se mantiene.
      - "colision" es bool per-step per-stream. El sumatorio por episodio
        es un conteo de stream-steps en colisión, no un conteo de pares
        únicos (como en evaluar_cobertura_multimetrica). Métrica ≈ más
        permisiva pero informativa para la ventana de entrenamiento.
    """

    VENTANA_EPS:      int   = 50     # tamaño del buffer rolling
    ALARMA_STEP:      int   = 2_500_000
    UMBRAL_ALARMA_COB: float = 0.55
    UMBRAL_ALARMA_COL: float = 0.50

    def __init__(
        self,
        cb_eval:    EvalCallback,
        csv_path:   Path,
        verbose:    int = 0,
    ) -> None:
        super().__init__(verbose=verbose)
        self.cb_eval  = cb_eval
        self.csv_path = csv_path

        # Acumuladores por stream (agente×env)
        self._ep_cob_last:  Dict[int, float] = {}
        self._ep_col_count: Dict[int, int]   = {}

        # Buffers rolling de episodios completados
        self._buf_cob: List[float] = []
        self._buf_col: List[float] = []

        # Control de milestones
        self._last_csv_ts:      int  = 0
        self._last_milestone_M: int  = 0
        self._alarma_revisada:  bool = False

        # Inicializar CSV
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                "timestep", "ep_rew_mean_train", "ep_len_mean",
                "cob_mean_win", "cob_std_win", "col_mean_win", "col_std_win",
                "n_eps_win", "eval_rew_mean",
            ])

    # ──────────────────────────────────────────────────────────────────────
    def _tail(self, buf: List[float]) -> Tuple[float, float, int]:
        """Media/std de los últimos VENTANA_EPS elementos."""
        if not buf:
            return (float("nan"), float("nan"), 0)
        v = np.asarray(buf[-self.VENTANA_EPS:], dtype=np.float64)
        return (float(v.mean()), float(v.std()), int(v.size))

    def _eval_rew(self) -> float:
        r = getattr(self.cb_eval, "last_mean_reward", None)
        return float(r) if r is not None and np.isfinite(r) else float("nan")

    # ──────────────────────────────────────────────────────────────────────
    def _on_step(self) -> bool:
        infos: List[Dict[str, Any]] = self.locals.get("infos", [])

        # ── Acumulación per-stream ───────────────────────────────────────
        for idx, info in enumerate(infos):
            if "cobertura_aoi" in info:
                self._ep_cob_last[idx] = float(info["cobertura_aoi"])
            if info.get("colision"):
                self._ep_col_count[idx] = self._ep_col_count.get(idx, 0) + 1

            # Episodio completado (VecMonitor inyecta "episode")
            if "episode" in info:
                self._buf_cob.append(self._ep_cob_last.get(idx, 0.0))
                self._buf_col.append(float(self._ep_col_count.get(idx, 0)))
                self._ep_cob_last[idx]  = 0.0
                self._ep_col_count[idx] = 0

        # ── Snapshot CSV cada 100k ───────────────────────────────────────
        if self.num_timesteps - self._last_csv_ts >= 100_000:
            self._last_csv_ts = self.num_timesteps

            cob_m, cob_s, n_win = self._tail(self._buf_cob)
            col_m, col_s, _     = self._tail(self._buf_col)

            # ep_rew_mean / ep_len_mean desde el buffer interno del modelo
            ep_rew = float("nan")
            ep_len = float("nan")
            if hasattr(self.model, "ep_info_buffer") and self.model.ep_info_buffer:
                rs = [ep["r"] for ep in self.model.ep_info_buffer]
                ls = [ep["l"] for ep in self.model.ep_info_buffer]
                if rs:
                    ep_rew = float(np.mean(rs))
                if ls:
                    ep_len = float(np.mean(ls))

            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    self.num_timesteps, ep_rew, ep_len,
                    cob_m, cob_s, col_m, col_s, n_win, self._eval_rew(),
                ])

            if self.logger is not None:
                self.logger.record("train/cobertura_ep_end_mean", cob_m)
                self.logger.record("train/colisiones_por_ep_mean", col_m)

        # ── Milestone cada 1M ────────────────────────────────────────────
        cur_M = self.num_timesteps // 1_000_000
        if cur_M > self._last_milestone_M:
            self._last_milestone_M = cur_M
            cob_m, _, n_win = self._tail(self._buf_cob)
            col_m, _, _     = self._tail(self._buf_col)
            logger.info(
                "[MILESTONE %dM/5M]  eval_rew=%.3f  cob_train=%.3f  "
                "col_train=%.2f  (n_ep_win=%d)",
                cur_M, self._eval_rew(), cob_m, col_m, n_win,
            )

        # ── Alarma a 2.5M ────────────────────────────────────────────────
        if (not self._alarma_revisada) and self.num_timesteps >= self.ALARMA_STEP:
            self._alarma_revisada = True
            cob_m, _, _ = self._tail(self._buf_cob)
            col_m, _, _ = self._tail(self._buf_col)
            logger.info(
                "[ALARMA-CHECK 2.5M]  cob=%.3f (umbral≥%.2f)  col=%.2f "
                "(umbral≤%.2f)",
                cob_m, self.UMBRAL_ALARMA_COB,
                col_m, self.UMBRAL_ALARMA_COL,
            )
            if (np.isfinite(cob_m) and cob_m < self.UMBRAL_ALARMA_COB) or \
               (np.isfinite(col_m) and col_m > self.UMBRAL_ALARMA_COL):
                logger.error(
                    "*** ALARMA ACTIVA ***  cob=%.3f  col=%.2f  — "
                    "pausando entrenamiento.",
                    cob_m, col_m,
                )
                return False
            logger.info("*** ALARMA NO ACTIVA ***  continuando hasta 5M.")

        return True


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRENAMIENTO
# ══════════════════════════════════════════════════════════════════════════════
def entrenar() -> Tuple[PPO, VecNormalize]:
    """Construye envs, modelo y callbacks; corre 5M steps."""
    logger.info("=" * 72)
    logger.info("ENTRENAMIENTO FINAL 5M — tesis_v1 — Trial 13")
    logger.info("  λ_cbf=%.4f  lr=%.2e  γ=%.4f  n_steps=%d",
                PESOS.lambda_cbf, HPARAMS.learning_rate,
                HPARAMS.gamma, HPARAMS.n_steps)
    logger.info("  n_agentes=%d  n_envs=%d  max_steps_ep=%d  seed=%d",
                CONFIG_ENV.n_agentes, CONFIG_TRAIN.n_envs_entren,
                CONFIG_ENV.max_steps_ep, CONFIG_TRAIN.seed)
    logger.info("=" * 72)

    # ── VecEnvs ──────────────────────────────────────────────────────────
    env_train = construir_vec_env_entrenamiento(
        config_env=CONFIG_ENV, config_train=CONFIG_TRAIN,
        pesos_rew=PESOS, seed=CONFIG_TRAIN.seed,
    )
    env_eval = construir_vec_env_evaluacion(
        config_env=CONFIG_ENV, config_train=CONFIG_TRAIN,
        pesos_rew=PESOS, seed=CONFIG_TRAIN.seed + 999,
    )

    # ── VecNormalize ─────────────────────────────────────────────────────
    env_train_n = VecNormalize(
        env_train,
        norm_obs=True, norm_reward=True,
        clip_obs=10.0, clip_reward=10.0,
        gamma=HPARAMS.gamma,
    )
    env_eval_n = VecNormalize(
        env_eval,
        norm_obs=True, norm_reward=False,
        clip_obs=10.0, training=False,
    )

    # ── Modelo ───────────────────────────────────────────────────────────
    modelo = construir_modelo_ppo(
        env=env_train_n, hparams=HPARAMS, config_train=CONFIG_TRAIN,
        dir_tensorboard=str(DIR_TB), seed=CONFIG_TRAIN.seed, verbose=1,
    )

    # ── FIX SB3 EvalCallback/CheckpointCallback: ambos usan `n_calls`
    #    (una vez por env.step del VecEnv), NO `num_timesteps`. Con
    #    num_envs = n_agentes × n_envs_entren = 5 × 4 = 20, las frecuencias
    #    que el usuario pide en timesteps deben dividirse por num_envs.
    num_envs = env_train_n.num_envs
    freq_eval_calls = max(1, CONFIG_TRAIN.frecuencia_eval  // num_envs)  # 100k/20 = 5000
    freq_ckpt_calls = max(1, CONFIG_TRAIN.frecuencia_ckpt  // num_envs)  # 500k/20 = 25000
    logger.info(
        "Callbacks SB3: num_envs=%d → eval_freq=%d n_calls (≈%d timesteps), "
        "save_freq=%d n_calls (≈%d timesteps)",
        num_envs, freq_eval_calls, freq_eval_calls * num_envs,
        freq_ckpt_calls, freq_ckpt_calls * num_envs,
    )

    # ── Callbacks ────────────────────────────────────────────────────────
    cb_eval = EvalCallback(
        eval_env=env_eval_n,
        best_model_save_path=str(DIR_MEJOR),
        log_path=str(DIR_MEJOR),
        eval_freq=freq_eval_calls,
        n_eval_episodes=CONFIG_TRAIN.n_episodios_eval,
        deterministic=True, render=False, verbose=1,
    )
    cb_ckpt = CheckpointCallback(
        save_freq=freq_ckpt_calls,
        save_path=str(DIR_CKPT),
        name_prefix="ppo_5M", verbose=0,
    )
    cb_metricas = CallbackMetricasPersonalizadas(verbose=0)
    cb_vecnorm_sync = _CallbackSyncVecNormalize(
        env_eval=env_eval_n, dir_vecnorm=DIR_VECNORM,
        freq=CONFIG_TRAIN.frecuencia_eval,
    )
    cb_milestone = CallbackMilestone5M(
        cb_eval=cb_eval, csv_path=DIR_BASE / "curva_5M.csv", verbose=0,
    )

    callbacks = CallbackList([
        cb_eval, cb_ckpt, cb_metricas, cb_vecnorm_sync, cb_milestone,
    ])

    # ── Learn ────────────────────────────────────────────────────────────
    t0 = time.time()
    try:
        modelo.learn(
            total_timesteps=N_PASOS_TOTAL,
            callback=callbacks,
            reset_num_timesteps=True,
            tb_log_name="5M_trial13",
            progress_bar=False,   # evita spam; usamos milestones
        )
    except KeyboardInterrupt:
        logger.warning("Interrumpido manualmente. Guardando...")
    finally:
        ruta_modelo = DIR_BASE / "modelo_final.zip"
        ruta_vn     = DIR_VECNORM / "vecnorm_final.pkl"
        modelo.save(str(ruta_modelo))
        env_train_n.save(str(ruta_vn))
        logger.info("Modelo guardado → %s", ruta_modelo)
        logger.info("VecNormalize guardado → %s", ruta_vn)

    dur_min = (time.time() - t0) / 60.0
    logger.info("Entrenamiento 5M completado en %.1f min.", dur_min)

    env_train_n.close()
    env_eval_n.close()
    return modelo, env_train_n


# ══════════════════════════════════════════════════════════════════════════════
#  EVALUACIÓN FINAL — 50 EPISODIOS DETERMINISTAS
# ══════════════════════════════════════════════════════════════════════════════
def _cargar_stats_vecnorm(ruta_pkl: Path) -> Tuple[np.ndarray, np.ndarray, float, float]:
    """
    Carga los stats de VecNormalize para aplicar normalización manual
    sobre observaciones del env PettingZoo crudo.

    Reconstruye un VecEnv dummy de la misma estructura para usar
    VecNormalize.load (que requiere un venv).
    """
    env_dummy = construir_vec_env_evaluacion(
        config_env=CONFIG_ENV, config_train=CONFIG_TRAIN,
        pesos_rew=PESOS, seed=CONFIG_TRAIN.seed + 5000,
    )
    vn = VecNormalize.load(str(ruta_pkl), env_dummy)
    obs_mean = np.asarray(vn.obs_rms.mean, dtype=np.float32).copy()
    obs_var  = np.asarray(vn.obs_rms.var,  dtype=np.float32).copy()
    clip_obs = float(vn.clip_obs)
    epsilon  = float(vn.epsilon)
    try:
        env_dummy.close()
    except Exception:
        pass
    return obs_mean, obs_var, clip_obs, epsilon


def evaluar_50_episodios(
    ruta_modelo:    Path,
    ruta_vecnorm:   Path,
    n_episodios:    int = 50,
) -> Dict[str, Any]:
    """
    Evalúa el modelo cargado en episodios deterministas usando env raw.
    """
    logger.info("─" * 72)
    logger.info("EVALUACIÓN FINAL — %d episodios deterministas", n_episodios)
    logger.info("  modelo:    %s", ruta_modelo)
    logger.info("  vecnorm:   %s", ruta_vecnorm)
    logger.info("─" * 72)

    modelo = PPO.load(str(ruta_modelo))
    obs_mean, obs_var, clip_obs, eps_vn = _cargar_stats_vecnorm(ruta_vecnorm)

    def normalizar(obs_arr: np.ndarray) -> np.ndarray:
        z = (obs_arr - obs_mean) / np.sqrt(obs_var + eps_vn)
        return np.clip(z, -clip_obs, clip_obs).astype(np.float32)

    env = make_env(
        n_agents=CONFIG_ENV.n_agentes,
        arena_size=CONFIG_ENV.arena_size,
        max_steps=CONFIG_ENV.max_steps_ep,
        comm_radius=CONFIG_ENV.radio_com,
        reward_weights={
            "lambda_gradient": PESOS.lambda_gradient,
            "lambda_entropy":  PESOS.lambda_entropy,
            "lambda_ibrm":     PESOS.lambda_ibrm,
            "lambda_cbf":      PESOS.lambda_cbf,
        },
        domain_rand=False,
        seed=CONFIG_TRAIN.seed,
    )

    resultados: List[Dict[str, float]] = []
    t0 = time.time()
    for i in range(n_episodios):
        seed_ep = CONFIG_TRAIN.seed * 10_000 + i
        obs_dict, _ = env.reset(seed=seed_ep)
        agents = list(obs_dict.keys())
        n_a = len(agents)

        cob_hist: List[float] = []
        pos_prev = np.array([env._estados[a][:2] for a in agents])
        pos_hist = [pos_prev.copy()]
        pares_col: set = set()

        done = False
        while not done:
            obs_arr  = np.stack([obs_dict[a] for a in agents])
            obs_norm = normalizar(obs_arr)
            acciones, _ = modelo.predict(obs_norm, deterministic=True)
            accion_dict = {a: acciones[k] for k, a in enumerate(agents)}
            obs_dict, _, term, trunc, _ = env.step(accion_dict)

            cob_hist.append(1.0 - float(np.mean(env._field._grid_aoi)))
            pos_curr = np.array([env._estados[a][:2] for a in agents])
            pos_hist.append(pos_curr.copy())
            for a1 in range(n_a):
                for a2 in range(a1 + 1, n_a):
                    if np.linalg.norm(pos_curr[a1] - pos_curr[a2]) < D_SAFE:
                        pares_col.add((a1, a2))

            done = (all(trunc.values()) if trunc else False) or \
                   (all(term.values()) if term else False)

        cob_final = cob_hist[-1] if cob_hist else 0.0
        n_col     = len(pares_col)
        pos_arr   = np.asarray(pos_hist)
        deltas    = np.linalg.norm(np.diff(pos_arr, axis=0), axis=2)
        dist_mean = float(np.mean(deltas.sum(axis=0)))
        cob_np    = np.asarray(cob_hist)
        idx_cross = np.where(cob_np >= 0.5)[0]
        t50       = int(idx_cross[0]) if len(idx_cross) else CONFIG_ENV.max_steps_ep

        resultados.append({
            "episodio": i,
            "cobertura_aoi_final": cob_final,
            "n_colisiones": n_col,
            "distancia_total_recorrida": dist_mean,
            "tiempo_primera_cobertura_50pct": t50,
        })

        if (i + 1) % 10 == 0:
            logger.info(
                "  ep %d/%d  cob=%.3f  col=%d  dist=%.2f  t50=%d",
                i + 1, n_episodios, cob_final, n_col, dist_mean, t50,
            )
    dur = time.time() - t0

    claves = [
        "cobertura_aoi_final",
        "n_colisiones",
        "distancia_total_recorrida",
        "tiempo_primera_cobertura_50pct",
    ]
    agregados: Dict[str, Dict[str, float]] = {}
    for k in claves:
        v = np.array([r[k] for r in resultados], dtype=np.float64)
        agregados[k] = {
            "media": float(v.mean()), "std": float(v.std()),
            "min":   float(v.min()),  "max": float(v.max()),
        }

    # Guardar JSON detallado
    salida = {
        "n_episodios": n_episodios,
        "duracion_s":  dur,
        "agregados":   agregados,
        "episodios":   resultados,
        "hiperparametros": asdict(HPARAMS),
        "pesos_recompensa": asdict(PESOS),
    }
    with open(DIR_BASE / "metricas_finales.json", "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)

    logger.info(
        "EVAL FINAL: cob=%.3f±%.3f  col=%.2f±%.2f  dist=%.2f  t50=%.0f  "
        "(duración %.1fs)",
        agregados["cobertura_aoi_final"]["media"],
        agregados["cobertura_aoi_final"]["std"],
        agregados["n_colisiones"]["media"],
        agregados["n_colisiones"]["std"],
        agregados["distancia_total_recorrida"]["media"],
        agregados["tiempo_primera_cobertura_50pct"]["media"],
        dur,
    )

    try:
        env.close()
    except Exception:
        pass
    return salida


# ══════════════════════════════════════════════════════════════════════════════
#  CRITERIO DE ÉXITO
# ══════════════════════════════════════════════════════════════════════════════
def aplicar_criterio_final(agregados: Dict[str, Dict[str, float]]) -> Dict[str, str]:
    """
    LISTO PARA SIM2REAL     : cob>0.80 AND std_cob<0.08 AND col<0.1
    RESULTADO DEFENDIBLE    : 0.70 ≤ cob ≤ 0.80 (intermedio)
    NECESITA RECALIBRACIÓN  : cob<0.70 OR col>0.3
    """
    cob_m = agregados["cobertura_aoi_final"]["media"]
    cob_s = agregados["cobertura_aoi_final"]["std"]
    col_m = agregados["n_colisiones"]["media"]

    if cob_m >= 0.80 and cob_s < 0.08 and col_m < 0.1:
        cat = "LISTO_PARA_SIM2REAL_EN_ROBOTAT"
        msg = (
            f"Cobertura {cob_m:.3f}±{cob_s:.3f} y colisiones {col_m:.2f}/ep "
            "cumplen los tres umbrales. **LISTO PARA SIM2REAL EN ROBOTAT.** "
            "Proceder a integración con OptiTrack+RF UDP."
        )
    elif cob_m < 0.70 or col_m > 0.3:
        cat = "NECESITA_RECALIBRACION"
        razon = []
        if cob_m < 0.70:
            razon.append(f"cobertura {cob_m:.3f} < 0.70")
        if col_m > 0.3:
            razon.append(f"colisiones {col_m:.2f} > 0.3")
        msg = (
            f"Falla significativa ({'; '.join(razon)}). "
            "**NECESITA RECALIBRACIÓN.** Considerar: tesis_v2 con "
            "espacio Optuna reducido y ajuste manual de λ_entropy/λ_cbf."
        )
    else:
        cat = "RESULTADO_DEFENDIBLE"
        msg = (
            f"Cobertura {cob_m:.3f}±{cob_s:.3f} y colisiones {col_m:.2f}/ep "
            "no cruzan el umbral de éxito pleno pero están en zona "
            "defendible. **RESULTADO DEFENDIBLE.** Documentar limitaciones "
            "en la tesis y considerar mejoras de baseline (Voronoi/PSO) "
            "para contextualizar."
        )
    return {"categoria": cat, "mensaje": msg}


# ══════════════════════════════════════════════════════════════════════════════
#  GENERACIÓN DE CURVA DE APRENDIZAJE
# ══════════════════════════════════════════════════════════════════════════════
def generar_figura_curvas(ruta_csv: Path, ruta_png: Path) -> None:
    """3 subplots: ep_rew_mean, cobertura, colisiones vs timestep."""
    if not ruta_csv.exists():
        logger.warning("No existe %s; no se genera figura.", ruta_csv)
        return
    data: Dict[str, List[float]] = {
        "timestep": [], "ep_rew_mean_train": [],
        "cob_mean_win": [], "cob_std_win": [],
        "col_mean_win": [], "col_std_win": [],
        "eval_rew_mean": [],
    }
    with open(ruta_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for k in data:
                try:
                    data[k].append(float(row[k]))
                except (ValueError, KeyError):
                    data[k].append(float("nan"))

    ts = np.array(data["timestep"]) / 1e6  # en millones

    fig, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True)

    ax = axes[0]
    ax.plot(ts, data["ep_rew_mean_train"], label="train ep_rew_mean",
            color="tab:blue", alpha=0.8)
    ax.plot(ts, data["eval_rew_mean"], label="eval_rew_mean (10 eps det.)",
            color="tab:orange", marker="o", markersize=3, ls="--")
    ax.set_ylabel("Reward"); ax.grid(alpha=0.3); ax.legend()
    ax.set_title("Curva de aprendizaje — entrenamiento final 5M (Trial 13)")

    ax = axes[1]
    cob_m = np.array(data["cob_mean_win"])
    cob_s = np.array(data["cob_std_win"])
    ax.plot(ts, cob_m, color="tab:green", label="cobertura_ep_end (ventana 50 eps)")
    ax.fill_between(ts, cob_m - cob_s, cob_m + cob_s,
                    color="tab:green", alpha=0.2)
    ax.axhline(0.80, color="red",    ls="--", lw=1, alpha=0.6, label="0.80 (éxito)")
    ax.axhline(0.55, color="orange", ls=":",  lw=1, alpha=0.6, label="0.55 (alarma)")
    ax.set_ylabel("Cobertura AoI"); ax.grid(alpha=0.3); ax.legend()
    ax.set_ylim(0, 1)

    ax = axes[2]
    col_m = np.array(data["col_mean_win"])
    col_s = np.array(data["col_std_win"])
    ax.plot(ts, col_m, color="tab:red", label="colisiones/ep (stream-steps, ventana 50 eps)")
    ax.fill_between(ts, np.clip(col_m - col_s, 0, None), col_m + col_s,
                    color="tab:red", alpha=0.2)
    ax.axhline(0.50, color="orange", ls=":", lw=1, alpha=0.6, label="0.50 (alarma)")
    ax.set_ylabel("Colisiones/ep"); ax.grid(alpha=0.3); ax.legend()
    ax.set_xlabel("Timesteps [millones]")

    plt.tight_layout()
    fig.savefig(ruta_png, dpi=200, bbox_inches="tight")
    plt.close(fig)
    logger.info("Figura guardada → %s", ruta_png)


# ══════════════════════════════════════════════════════════════════════════════
#  REPORTE MARKDOWN
# ══════════════════════════════════════════════════════════════════════════════
def cargar_metricas_previas() -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Carga 100k (seed 42 de verificacion_seeds) y 200k (variante_A)."""
    ruta_100k = ROOT / "modelos" / "tesis_v1" / "verificacion_seeds" / "seed_42" / "metricas_cobertura.json"
    ruta_200k = ROOT / "modelos" / "tesis_v1" / "test_lambda_cbf" / "variante_A" / "metricas_cobertura.json"
    m100k = m200k = None
    if ruta_100k.exists():
        with open(ruta_100k, encoding="utf-8") as f:
            m100k = json.load(f)
    if ruta_200k.exists():
        with open(ruta_200k, encoding="utf-8") as f:
            m200k = json.load(f)
    return m100k, m200k


def generar_reporte(
    salida_eval:   Dict[str, Any],
    criterio:      Dict[str, str],
    ruta_md:       Path,
) -> None:
    ag = salida_eval["agregados"]
    m100k, m200k = cargar_metricas_previas()

    lineas: List[str] = [
        "# Reporte Final — Entrenamiento 5M (tesis_v1, Trial 13)",
        "",
        f"*Generado: {time.strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
        "## Contexto",
        "",
        "Corrida final del pipeline tesis_v1 con los hiperparámetros del "
        "Trial 13 (mejores_hiperparametros.json) validados previamente:",
        "",
        f"- **λ_cbf = {PESOS.lambda_cbf:.4f}** (confirmado por A/B test: 5.0 degrada ambas métricas)",
        f"- **learning_rate = {HPARAMS.learning_rate:.2e}**",
        f"- **γ = {HPARAMS.gamma:.4f}**   **gae_λ = {HPARAMS.gae_lambda:.4f}**",
        f"- **n_steps = {HPARAMS.n_steps}**   **batch_size = {HPARAMS.batch_size}**   **n_epochs = {HPARAMS.n_epochs}**",
        f"- **ent_coef = {HPARAMS.ent_coef:.4f}**   **clip_range = {HPARAMS.clip_range:.3f}**",
        "",
        "## Configuración de entrenamiento",
        "",
        f"- **Steps totales:** 5,000,000",
        f"- **Agentes:** {CONFIG_ENV.n_agentes}  —  **max_steps_ep:** {CONFIG_ENV.max_steps_ep}  —  **n_envs:** {CONFIG_TRAIN.n_envs_entren}  —  **seed:** {CONFIG_TRAIN.seed}",
        f"- **EvalCallback:** cada {CONFIG_TRAIN.frecuencia_eval:,} steps × {CONFIG_TRAIN.n_episodios_eval} episodios deterministas",
        f"- **Checkpoints:** cada {CONFIG_TRAIN.frecuencia_ckpt:,} steps",
        "- **VecNormalize activo** (obs + reward) — stats guardados para inferencia",
        "",
        "## Métricas finales (50 episodios deterministas, sin domain_rand)",
        "",
        "| Métrica | Media ± σ | min | max |",
        "|---------|----------:|----:|----:|",
        f"| Cobertura AoI final | **{ag['cobertura_aoi_final']['media']:.3f}** ± {ag['cobertura_aoi_final']['std']:.3f} | {ag['cobertura_aoi_final']['min']:.3f} | {ag['cobertura_aoi_final']['max']:.3f} |",
        f"| Pares en colisión / ep | **{ag['n_colisiones']['media']:.2f}** ± {ag['n_colisiones']['std']:.2f} | {ag['n_colisiones']['min']:.0f} | {ag['n_colisiones']['max']:.0f} |",
        f"| Distancia recorrida [m] | {ag['distancia_total_recorrida']['media']:.2f} ± {ag['distancia_total_recorrida']['std']:.2f} | {ag['distancia_total_recorrida']['min']:.2f} | {ag['distancia_total_recorrida']['max']:.2f} |",
        f"| Step al cruzar cob=0.5 | {ag['tiempo_primera_cobertura_50pct']['media']:.0f} ± {ag['tiempo_primera_cobertura_50pct']['std']:.0f} | {ag['tiempo_primera_cobertura_50pct']['min']:.0f} | {ag['tiempo_primera_cobertura_50pct']['max']:.0f} |",
        "",
    ]

    # ── Tabla comparativa 100k/200k/5M ──────────────────────────────────
    lineas += [
        "## Evolución con el presupuesto de entrenamiento",
        "",
        "| Presupuesto | Cobertura AoI (μ±σ) | Pares colisión/ep (μ±σ) | Step a cob=0.5 (μ) | Distancia recorrida (μ) |",
        "|------------:|--------------------:|-----------------------:|-------------------:|------------------------:|",
    ]
    if m100k:
        a = m100k["agregados"]
        lineas.append(
            f"| 100k (seed 42) | {a['cobertura_aoi_final']['media']:.3f}±{a['cobertura_aoi_final']['std']:.3f} | "
            f"{a['n_colisiones']['media']:.2f}±{a['n_colisiones']['std']:.2f} | "
            f"{a['tiempo_primera_cobertura_50pct']['media']:.0f} | "
            f"{a['distancia_total_recorrida']['media']:.2f} |"
        )
    if m200k:
        a = m200k["agregados"]
        lineas.append(
            f"| 200k (variante A) | {a['cobertura_aoi_final']['media']:.3f}±{a['cobertura_aoi_final']['std']:.3f} | "
            f"{a['n_colisiones']['media']:.2f}±{a['n_colisiones']['std']:.2f} | "
            f"{a['tiempo_primera_cobertura_50pct']['media']:.0f} | "
            f"{a['distancia_total_recorrida']['media']:.2f} |"
        )
    lineas.append(
        f"| **5M (final)** | **{ag['cobertura_aoi_final']['media']:.3f}±{ag['cobertura_aoi_final']['std']:.3f}** | "
        f"**{ag['n_colisiones']['media']:.2f}±{ag['n_colisiones']['std']:.2f}** | "
        f"{ag['tiempo_primera_cobertura_50pct']['media']:.0f} | "
        f"{ag['distancia_total_recorrida']['media']:.2f} |"
    )

    # ── Criterio ────────────────────────────────────────────────────────
    lineas += [
        "",
        "## Criterio de éxito",
        "",
        "| Categoría | Condición |",
        "|-----------|-----------|",
        "| 🟢 LISTO PARA SIM2REAL | cob > 0.80 con std < 0.08 AND col < 0.1 |",
        "| 🟡 RESULTADO DEFENDIBLE | cobertura 0.70 – 0.80 |",
        "| 🔴 NECESITA RECALIBRACIÓN | cob < 0.70 OR col > 0.3 |",
        "",
        f"### Resultado: **{criterio['categoria']}**",
        "",
        criterio["mensaje"],
        "",
        "## Curva de aprendizaje",
        "",
        "![Curva 5M](curva_aprendizaje.png)",
        "",
        "## Artefactos generados",
        "",
        "- `modelo_final.zip` — modelo PPO al final de los 5M steps",
        "- `mejor_modelo/best_model.zip` — modelo con mejor eval_rew (EvalCallback)",
        "- `vecnorm/vecnorm_final.pkl` — estadísticas de normalización (críticas para sim2real)",
        "- `checkpoints/ppo_5M_{500000,1000000,...}.zip` — checkpoints cada 500k",
        "- `curva_5M.csv` — snapshot cada 100k (rewards, cobertura, colisiones)",
        "- `metricas_finales.json` — datos crudos de los 50 episodios de eval",
        "- `tensorboard/` — logs para `tensorboard --logdir`",
        "- `entrenamiento_5M.log` — log de la corrida",
        "",
        "## Próximos pasos",
        "",
        "```powershell",
        "# Visualizar curvas en TensorBoard",
        "python -m tensorboard.main --logdir .\\modelos\\tesis_v1\\entrenamiento_final_5M\\tensorboard --port 6006",
        "```",
    ]

    ruta_md.write_text("\n".join(lineas), encoding="utf-8")
    logger.info("Reporte: %s", ruta_md)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    # Fase 1 — Entrenamiento
    modelo, _ = entrenar()
    del modelo  # liberar; lo recargamos desde best_model.zip

    # Fase 2 — Eval final sobre best_model
    ruta_best = DIR_MEJOR / "best_model.zip"
    if not ruta_best.exists():
        logger.warning("best_model.zip no existe (¿eval no llegó a dispararse?). "
                       "Usando modelo_final.zip.")
        ruta_best = DIR_BASE / "modelo_final.zip"
    ruta_vn = DIR_VECNORM / "vecnorm_final.pkl"

    salida = evaluar_50_episodios(ruta_best, ruta_vn, n_episodios=50)

    # Fase 3 — Figura + criterio + reporte
    generar_figura_curvas(DIR_BASE / "curva_5M.csv", DIR_BASE / "curva_aprendizaje.png")
    criterio = aplicar_criterio_final(salida["agregados"])

    logger.info("=" * 72)
    logger.info("CRITERIO FINAL: %s", criterio["categoria"])
    logger.info("  %s", criterio["mensaje"])
    logger.info("=" * 72)

    generar_reporte(salida, criterio, DIR_BASE / "reporte_final.md")


if __name__ == "__main__":
    main()
