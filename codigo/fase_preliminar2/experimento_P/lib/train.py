"""
train.py
========
Script de entrenamiento para el enjambre de robots Pololu 3pi+ con MADRL-PPO.

Pipeline completo:
  1. Optimización Bayesiana (Optuna/TPE) sobre hiperparámetros de PPO
     y pesos de la función de recompensa multiobjetivo.
  2. Entrenamiento final con los mejores hiperparámetros encontrados.
  3. Logging a TensorBoard, CSV y SQLite (para reanudar estudios).

Arquitectura de entornos vectorizados (SuperSuit → SB3):
  ┌─────────────────────────────────────────────────────────────┐
  │  PettingZoo ParallelEnv (N_AGENTES agentes/episodio)        │
  │    → ss.pettingzoo_env_to_vec_env_v1()                      │
  │      Trata cada agente como una "sub-env" independiente      │
  │      → N_AGENTES streams de (obs, act, rew, done)           │
  │    → ss.concat_vec_envs_v1(N_ENVS_PARALELOS)               │
  │      Replica el env en N_ENVS_PARALELOS procesos paralelos   │
  │      → N_AGENTES × N_ENVS_PARALELOS streams totales         │
  │    → VecMonitor()                                            │
  │      Envuelve para logging de episodio (ep_rew_mean, etc.)   │
  └─────────────────────────────────────────────────────────────┘

  PPO ve N_AGENTES × N_ENVS_PARALELOS environments paralelos.
  El buffer rollout acumula n_steps × (N_AGENTES × N_ENVS_PARALELOS)
  transiciones antes de cada actualización de la política.

Nota sobre CTDE en entrenamiento:
  Durante el entrenamiento SB3, el Crítico (Centralizado) recibe
  observaciones de TODOS los agentes via VecEnv — esto es correcto.
  En ejecución, solo el Actor (Descentralizado) corre en el servidor
  Robotat por agente.

Uso
───
  # Fase 1: Optimización Bayesiana (20 trials, 30 min máx por trial)
  python train.py --modo optimizar --n_trials 20 --presupuesto_trial 200_000

  # Fase 2: Entrenamiento final con mejores hiperparámetros
  python train.py --modo entrenar --n_pasos 5_000_000

  # Reanudar un estudio existente de Optuna
  python train.py --modo optimizar --nombre_estudio mi_estudio --n_trials 40

Autores / Tesis: José — Mecatrónica UVG
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import optuna
from optuna.pruners import MedianPruner
from optuna.samplers import TPESampler
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import (
    BaseCallback,
    CallbackList,
    CheckpointCallback,
    EvalCallback,
)
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import VecEnv, VecMonitor, VecNormalize

# SuperSuit: convierte PettingZoo ↔ SB3 VecEnv
import supersuit as ss

# Módulos propios del proyecto
# NOTA: cuando el entorno esté implementado, reemplazar estas líneas:
from swarm_env_skeleton import (
    CyanobacteriaMonitoringEnv,
    D_OBS,
    make_env,
)

# ──────────────────────────────────────────────────────────────────────────────
# Configuración de logging del proceso
# ──────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("train_swarm")

# Silenciar warnings de gymnasium sobre espacios no normalizados
warnings.filterwarnings("ignore", category=UserWarning, module="gymnasium")


# ══════════════════════════════════════════════════════════════════════════════
#  DATACLASSES DE CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ConfigEntorno:
    """
    Parámetros fijos del entorno de simulación.
    NO son sujeto de optimización bayesiana (son restricciones del problema).
    """
    n_agentes:        int               = 5
    arena_size:       Tuple[float, float] = (3.0, 3.0)
    max_steps_ep:     int               = 500          # steps por episodio
    radio_com:        float             = 1.0          # radio de comm [m]
    dt:               float             = 0.1          # paso de tiempo [s]
    domain_rand:      bool              = True         # Domain Randomization
    grid_resolution:  int               = 64           # AoI grid (64×64)
    n_hotspots:       int               = 3


@dataclass
class ConfigEntrenamiento:
    """
    Parámetros del proceso de entrenamiento (no optimizados por Optuna).
    """
    # Paralelismo
    n_envs_entren:    int   = 8           # envs paralelos durante entrenamiento
    n_envs_eval:      int   = 2           # envs paralelos durante evaluación
    n_envs_trial:     int   = 4           # envs paralelos durante trials de Optuna

    # Arquitectura de la red neuronal (MLP compartida Actor-Crítico)
    # Ambas sub-redes tienen la misma arquitectura para simplificar
    capas_red:        List[int] = field(default_factory=lambda: [256, 256])

    # Evaluación periódica
    frecuencia_eval:  int   = 20_000      # cada cuántos steps evaluar
    n_episodios_eval: int   = 10          # episodios por evaluación

    # Checkpointing
    frecuencia_ckpt:  int   = 100_000     # cada cuántos steps guardar modelo

    # TensorBoard
    dir_logs:         str   = "./logs"
    dir_modelos:      str   = "./modelos"

    # Semilla base
    seed:             int   = 42


@dataclass
class HiperparametrosPPO:
    """
    Hiperparámetros de PPO sujetos a optimización bayesiana.
    Los rangos de búsqueda están definidos en EspacioBusqueda.
    """
    learning_rate:  float = 3e-4
    gamma:          float = 0.99
    clip_range:     float = 0.2
    n_steps:        int   = 512     # steps por env antes de actualizar
    batch_size:     int   = 256     # minibatch size para las épocas PPO
    n_epochs:       int   = 10      # épocas PPO por actualización
    ent_coef:       float = 0.01    # coeficiente de entropía (exploración)
    gae_lambda:     float = 0.95    # GAE lambda (bias-variance en ventaja)
    vf_coef:        float = 0.5     # peso del loss del value function
    max_grad_norm:  float = 0.5     # clipping del gradiente


@dataclass
class PesosRecompensa:
    """
    Pesos de la función de recompensa multiobjetivo.
    Sujetos a optimización bayesiana.
    """
    lambda_gradient: float = 1.0   # ∇C: moverse hacia hotspots
    lambda_entropy:  float = 0.5   # AoI: exploración de zonas nuevas
    lambda_ibrm:     float = 0.3   # IBRM: penalizar jitter/estancamiento
    lambda_cbf:      float = 5.0   # CBF: penalizar colisiones


@dataclass
class ConfigOptuna:
    """Configuración del estudio de Optuna."""
    nombre_estudio:      str  = "swarm_cyano_v1"
    n_trials:            int  = 30
    presupuesto_trial:   int  = 200_000  # steps de env por trial
    timeout_total_s:     Optional[float] = None  # None = sin límite de tiempo
    n_jobs:              int  = 1        # trials en paralelo (1 = secuencial)
    n_startup_trials:    int  = 5        # trials random antes de Bayesian
    # `MedianPruner.n_warmup_steps` se compara contra el `step` REPORTADO, que
    # es `num_timesteps` (10 000, 20 000, ...). Con el valor 5 anterior el
    # warmup nunca protegía nada y los trials morían en el primer reporte, al
    # 10% del presupuesto. Se expresa en PASOS DE ENTORNO. Ver Exp J.
    n_warmup_steps:      int  = 100_000  # pasos de entorno antes de poder podar
    intervalo_poda:      int  = 1        # cada cuántos reports evaluar poda
    dir_almacenamiento:  str  = "./optuna_studies"


# ══════════════════════════════════════════════════════════════════════════════
#  ESPACIO DE BÚSQUEDA DE OPTUNA
# ══════════════════════════════════════════════════════════════════════════════

class EspacioBusqueda:
    """
    Define y muestrea el espacio de hiperparámetros para Optuna.

    Separamos la definición del espacio de su uso para mantener un punto
    único de verdad. Si cambias un rango, cambia aquí y en ningún otro lugar.

    Justificación de rangos
    ───────────────────────
    learning_rate  : rango log-uniform [1e-5, 5e-4] — PPO típico para control
    gamma          : [0.95, 0.9997] — descuento para horizonte ~500 steps
    clip_range     : [0.10, 0.40]  — mayor rango para exploración inicial
    n_steps        : {64,128,256,512,1024} — múltiplos de 2 (vectorización)
    batch_size     : derivado de n_steps (debe dividirlo exactamente)
    n_epochs       : [3, 15]  — más épocas = más uso de datos, riesgo overfitting
    ent_coef       : log-uniform [1e-4, 5e-2] — exploración en espacio continuo
    gae_lambda     : [0.90, 0.99] — standard para robótica
    lambda_gradient: [0.5, 3.0]  — dominante en la recompensa
    lambda_entropy : [0.1, 2.0]  — exploración vs explotación de información
    lambda_ibrm    : [0.05, 1.0] — penalización suave-moderada por jitter
    lambda_cbf     : [1.0, 15.0] — seguridad debe ser siempre significativa
    """

    @staticmethod
    def sugerir(trial: optuna.Trial) -> Tuple[HiperparametrosPPO, PesosRecompensa]:
        """
        Pide a Optuna sugerencias para todos los hiperparámetros.

        Parámetros
        ----------
        trial : optuna.Trial

        Retorna
        -------
        (HiperparametrosPPO, PesosRecompensa) — instancias con valores sugeridos
        """
        # ── Hiperparámetros PPO ───────────────────────────────────────────
        lr = trial.suggest_float("learning_rate", 1e-5, 5e-4, log=True)
        gamma = trial.suggest_float("gamma", 0.95, 0.9997)
        clip_range = trial.suggest_float("clip_range", 0.10, 0.40)

        # n_steps: potencias de 2 entre 64 y 1024
        n_steps_exp = trial.suggest_int("n_steps_exp", 6, 10)  # 2^6=64 ... 2^10=1024
        n_steps = 2 ** n_steps_exp

        # batch_size: divisor de n_steps; muestrear como fracción
        batch_divisor = trial.suggest_categorical("batch_divisor", [1, 2, 4, 8])
        batch_size = max(32, n_steps // batch_divisor)

        n_epochs = trial.suggest_int("n_epochs", 3, 15)
        ent_coef = trial.suggest_float("ent_coef", 1e-4, 5e-2, log=True)
        gae_lambda = trial.suggest_float("gae_lambda", 0.90, 0.99)

        hparams = HiperparametrosPPO(
            learning_rate = lr,
            gamma         = gamma,
            clip_range    = clip_range,
            n_steps       = n_steps,
            batch_size    = batch_size,
            n_epochs      = n_epochs,
            ent_coef      = ent_coef,
            gae_lambda    = gae_lambda,
        )

        # ── Pesos de la recompensa ────────────────────────────────────────
        pesos = PesosRecompensa(
            lambda_gradient = trial.suggest_float("lambda_gradient", 0.5, 3.0),
            lambda_entropy  = trial.suggest_float("lambda_entropy",  0.1, 2.0),
            lambda_ibrm     = trial.suggest_float("lambda_ibrm",     0.05, 1.0),
            lambda_cbf      = trial.suggest_float("lambda_cbf",      1.0, 15.0),
        )

        return hparams, pesos


# ══════════════════════════════════════════════════════════════════════════════
#  FÁBRICAS DE ENTORNOS VECTORIZADOS
# ══════════════════════════════════════════════════════════════════════════════

def _fabrica_env(
    config_env:     ConfigEntorno,
    pesos_rew:      PesosRecompensa,
    seed:           int,
    es_eval:        bool = False,
) -> CyanobacteriaMonitoringEnv:
    """
    Función de bajo nivel: crea UNA instancia del entorno PettingZoo.

    Esta función es llamada por SuperSuit internamente en cada proceso
    del VecEnv. Debe ser serializable (sin lambdas con closures complejos).

    Parámetros
    ----------
    config_env  : ConfigEntorno
    pesos_rew   : PesosRecompensa
    seed        : int  — semilla para este worker
    es_eval     : bool — si True, desactiva domain randomization

    Retorna
    -------
    CyanobacteriaMonitoringEnv  (con wrappers de PettingZoo aplicados)
    """
    reward_weights_dict: Dict[str, float] = {
        "lambda_gradient": pesos_rew.lambda_gradient,
        "lambda_entropy":  pesos_rew.lambda_entropy,
        "lambda_ibrm":     pesos_rew.lambda_ibrm,
        "lambda_cbf":      pesos_rew.lambda_cbf,
    }
    env = make_env(
        n_agents      = config_env.n_agentes,
        arena_size    = config_env.arena_size,
        max_steps     = config_env.max_steps_ep,
        comm_radius   = config_env.radio_com,
        reward_weights= reward_weights_dict,
        domain_rand   = config_env.domain_rand and not es_eval,
        seed          = seed,
    )
    return env


def construir_vec_env_entrenamiento(
    config_env:     ConfigEntorno,
    config_train:   ConfigEntrenamiento,
    pesos_rew:      PesosRecompensa,
    n_envs:         Optional[int] = None,
    seed:           int = 42,
) -> VecMonitor:
    """
    Construye el VecEnv de entrenamiento con SuperSuit.

    Cadena de wrappers:
      1. _fabrica_env()                              → instancia PettingZoo
      2. ss.pettingzoo_env_to_vec_env_v1()           → N_AGENTES sub-envs
      3. ss.concat_vec_envs_v1(n_envs)               → N_AGENTES × N_ENVS streams
      4. PATCH seed()                                → fix compat SuperSuit + SB3 2.8
      5. VecMonitor()                                → logging para SB3
    """
    n_envs_efectivos = n_envs or config_train.n_envs_entren

    # Crear la primera instancia para derivar los espacios
    env_base = _fabrica_env(config_env, pesos_rew, seed=seed, es_eval=False)

    # Paso 2: PettingZoo → VecEnv (N_AGENTES sub-envs por instancia)
    env_vec = ss.pettingzoo_env_to_vec_env_v1(env_base)

    # Paso 3: Concatenar N_ENVS copias en paralelo
    env_concat = ss.concat_vec_envs_v1(
        env_vec,
        num_vec_envs  = n_envs_efectivos,
        num_cpus      = min(n_envs_efectivos, os.cpu_count() or 1),
        base_class    = "stable_baselines3",
    )

    # ── Paso 4: PATCH de compatibilidad SuperSuit 3.10 + SB3 2.8 ────────
    # ConcatVecEnv.seed() llama recursivamente a self.venv.seed() sobre
    # MarkovVectorEnv (interno de SuperSuit) que no expone ese método,
    # causando AttributeError durante PPO.__init__ → set_random_seed().
    # Sobrescribimos con no-op (el seeding ya se hace al crear env_base).
    env_concat.seed = lambda seed=None: [None] * env_concat.num_envs

    # Paso 5: VecMonitor para logging de SB3
    env_monitoreado = VecMonitor(env_concat)

    logger.info(
        "VecEnv entrenamiento construido: %d agentes × %d envs = %d streams totales",
        config_env.n_agentes, n_envs_efectivos,
        config_env.n_agentes * n_envs_efectivos,
    )
    return env_monitoreado


def construir_vec_env_evaluacion(
    config_env:     ConfigEntorno,
    config_train:   ConfigEntrenamiento,
    pesos_rew:      PesosRecompensa,
    seed:           int = 100,
) -> VecMonitor:
    """
    Construye el VecEnv de evaluación.

    Diferencias con entrenamiento:
      - domain_rand=False (eval determinista sobre entorno nominal)
      - n_envs reducido (config_train.n_envs_eval)
      - Semillas distintas a las de entrenamiento
      - Aplica el mismo PATCH de seed()
    """
    env_base = _fabrica_env(config_env, pesos_rew, seed=seed, es_eval=True)
    env_vec  = ss.pettingzoo_env_to_vec_env_v1(env_base)
    env_concat = ss.concat_vec_envs_v1(
        env_vec,
        num_vec_envs = config_train.n_envs_eval,
        num_cpus     = min(config_train.n_envs_eval, os.cpu_count() or 1),
        base_class   = "stable_baselines3",
    )

    # ── PATCH idéntico al de entrenamiento ──────────────────────────────
    env_concat.seed = lambda seed=None: [None] * env_concat.num_envs

    return VecMonitor(env_concat)


# ══════════════════════════════════════════════════════════════════════════════
#  CALLBACKS PERSONALIZADOS
# ══════════════════════════════════════════════════════════════════════════════

class CallbackOptunaPoda(BaseCallback):
    """
    Callback de SB3 que reporta la métrica de cobertura a Optuna y solicita
    poda (early stopping) si el trial está rindiendo por debajo de la mediana.

    Cómo funciona la poda de Optuna (MedianPruner):
      - En cada `report()`, Optuna compara el valor actual del trial contra
        la mediana de los trials completados en el mismo step.
      - Si el trial está significativamente por debajo → `should_prune()` = True
        → el callback lanza TrialPruned para abortar el trial.

    Parámetros
    ----------
    trial              : optuna.Trial
    n_steps_evaluacion : int — cada cuántos steps hacer un report a Optuna
    verbose            : int
    """

    def __init__(
        self,
        trial:               optuna.Trial,
        n_steps_evaluacion:  int = 10_000,
        verbose:             int = 0,
    ) -> None:
        super().__init__(verbose=verbose)
        self.trial                = trial
        self.n_steps_evaluacion   = n_steps_evaluacion
        self._ultimo_reporte_step = 0
        self._mejor_metrica       = -np.inf

    def _on_step(self) -> bool:
        """
        Llamado en cada step del VecEnv.

        Retorna False si el trial debe podarse (aborta el entrenamiento del trial).
        """
        steps_transcurridos = self.num_timesteps - self._ultimo_reporte_step

        if steps_transcurridos < self.n_steps_evaluacion:
            return True  # continuar

        self._ultimo_reporte_step = self.num_timesteps

        # ── Extraer métricas del buffer de SB3 ──────────────────────────
        # ep_rew_mean: recompensa media del episodio (últimos N episodios)
        # Si no hay episodios completados aún → None
        metrica = self._extraer_ep_rew_mean()

        if metrica is None:
            return True  # aún no hay episodios completos, esperar

        self._mejor_metrica = max(self._mejor_metrica, metrica)

        # Reportar a Optuna (step = timesteps acumulados)
        self.trial.report(metrica, step=self.num_timesteps)

        if self.verbose >= 1:
            logger.debug(
                "  Trial %d — step %d — ep_rew_mean=%.4f",
                self.trial.number, self.num_timesteps, metrica,
            )

        # Solicitar poda si el trial es malo
        if self.trial.should_prune():
            logger.info(
                "Trial %d podado en step %d (ep_rew_mean=%.4f)",
                self.trial.number, self.num_timesteps, metrica,
            )
            raise optuna.exceptions.TrialPruned()

        return True  # continuar

    def _extraer_ep_rew_mean(self) -> Optional[float]:
        """
        Extrae ep_rew_mean del logger interno de SB3.
        Retorna None si no hay datos disponibles aún.
        """
        if self.model is None or self.model.ep_info_buffer is None:
            return None
        if len(self.model.ep_info_buffer) == 0:
            return None
        recompensas = [ep["r"] for ep in self.model.ep_info_buffer]
        return float(np.mean(recompensas))


class CallbackMetricasPersonalizadas(BaseCallback):
    """
    Registra métricas adicionales en TensorBoard que SB3 no registra
    por defecto, específicas de nuestro entorno multi-agente.

    Métricas registradas:
      - train/cobertura_aoi_media : fracción del grid visitada en el episodio
      - train/colisiones_por_step : colisiones inter-agente / step
      - train/n_agentes_activos   : promedio de agentes activos por step

    El entorno debe proponer estas métricas en el dict `info` de cada agente
    usando las claves: 'cobertura_aoi', 'colision', 'n_agentes'.
    """

    def __init__(self, verbose: int = 0) -> None:
        super().__init__(verbose=verbose)
        self._buffer_cobertura: List[float]   = []
        self._buffer_colisiones: List[float]  = []
        self._buffer_n_agentes: List[float]   = []

    def _on_step(self) -> bool:
        """Recolecta métricas de los dicts `info` del VecEnv."""
        # self.locals['infos'] es una lista de dicts, uno por stream (agente×env)
        infos: List[Dict[str, Any]] = self.locals.get("infos", [])

        for info in infos:
            if "cobertura_aoi" in info:
                self._buffer_cobertura.append(float(info["cobertura_aoi"]))
            if "colision" in info:
                self._buffer_colisiones.append(float(info["colision"]))
            if "n_agentes" in info:
                self._buffer_n_agentes.append(float(info["n_agentes"]))

        # Registrar en TensorBoard cada 1000 steps
        if self.num_timesteps % 1_000 == 0 and self.logger is not None:
            if self._buffer_cobertura:
                self.logger.record(
                    "train/cobertura_aoi_media",
                    float(np.mean(self._buffer_cobertura))
                )
                self._buffer_cobertura.clear()
            if self._buffer_colisiones:
                self.logger.record(
                    "train/colisiones_por_step",
                    float(np.mean(self._buffer_colisiones))
                )
                self._buffer_colisiones.clear()
            if self._buffer_n_agentes:
                self.logger.record(
                    "train/n_agentes_activos",
                    float(np.mean(self._buffer_n_agentes))
                )
                self._buffer_n_agentes.clear()

        return True


# ══════════════════════════════════════════════════════════════════════════════
#  CONSTRUCTOR DEL MODELO PPO
# ══════════════════════════════════════════════════════════════════════════════

def construir_modelo_ppo(
    env:            VecEnv,
    hparams:        HiperparametrosPPO,
    config_train:   ConfigEntrenamiento,
    dir_tensorboard: str,
    seed:           int = 42,
    verbose:        int = 0,
) -> PPO:
    """
    Construye e instancia el modelo PPO de Stable-Baselines3.

    Arquitectura de la red:
      MlpPolicy con redes independientes para Actor y Crítico.
      net_arch = [{"pi": capas_red, "vf": capas_red}]
      Donde "pi" = policy (Actor) y "vf" = value function (Crítico).

      Activación: Tanh (default de SB3 para control continuo).
      No usamos ReLU porque los gradientes pueden explotar con acciones
      en el límite del espacio de acción (los límites son suaves con Tanh).

    Parámetros
    ----------
    env             : VecEnv — entorno de entrenamiento ya construido
    hparams         : HiperparametrosPPO — hiperparámetros sugeridos por Optuna
    config_train    : ConfigEntrenamiento
    dir_tensorboard : str — directorio para logs de TensorBoard
    seed            : int
    verbose         : int — 0 = silencioso, 1 = progreso, 2 = debug

    Retorna
    -------
    PPO  — modelo listo para .learn()
    """
    # Definición de la arquitectura de red
    arquitectura_red: List[Dict[str, Any]] = [
        {
            "pi": config_train.capas_red,   # Actor
            "vf": config_train.capas_red,   # Crítico
        }
    ]

    # Verificar que batch_size divide a n_steps × n_envs_efectivos
    # (SB3 lanzará error si no, mejor detectarlo antes)
    n_streams = env.num_envs  # = N_AGENTES × N_ENVS_PARALELOS
    buffer_total = hparams.n_steps * n_streams
    if buffer_total % hparams.batch_size != 0:
        # Ajustar batch_size al mayor divisor válido ≤ batch_size original
        for bs in range(hparams.batch_size, 0, -1):
            if buffer_total % bs == 0:
                hparams.batch_size = bs
                break
        logger.warning(
            "batch_size ajustado a %d para dividir el buffer de %d transacciones.",
            hparams.batch_size, buffer_total,
        )

    modelo = PPO(
        policy          = "MlpPolicy",
        env             = env,
        learning_rate   = hparams.learning_rate,
        n_steps         = hparams.n_steps,
        batch_size      = hparams.batch_size,
        n_epochs        = hparams.n_epochs,
        gamma           = hparams.gamma,
        gae_lambda      = hparams.gae_lambda,
        clip_range      = hparams.clip_range,
        ent_coef        = hparams.ent_coef,
        vf_coef         = hparams.vf_coef,
        max_grad_norm   = hparams.max_grad_norm,
        policy_kwargs   = {
            "net_arch":   arquitectura_red,
            "activation_fn": __import__("torch").nn.Tanh,
        },
        tensorboard_log = dir_tensorboard,
        verbose         = verbose,
        seed            = seed,
    )

    return modelo


# ══════════════════════════════════════════════════════════════════════════════
#  FUNCIÓN OBJETIVO DE OPTUNA
# ══════════════════════════════════════════════════════════════════════════════

def objetivo_optuna(
    trial:           optuna.Trial,
    config_env:      ConfigEntorno,
    config_train:    ConfigEntrenamiento,
    config_optuna:   ConfigOptuna,
    dir_salida:      Path,
) -> float:
    """
    Función objetivo que Optuna maximiza.

    Cada llamada a esta función:
      1. Pide a Optuna sugerencias de hiperparámetros.
      2. Construye los entornos (train + eval) con esos parámetros.
      3. Entrena PPO por `presupuesto_trial` steps.
      4. Evalúa el modelo en el entorno de evaluación.
      5. Retorna la métrica objetivo (a maximizar): ep_rew_mean.

    Métrica objetivo:
      Se usa ep_rew_mean (recompensa episódica media) del entorno de evaluación
      con domain_rand=False. Esto garantiza que la métrica sea reproducible
      entre trials (no afectada por la varianza de domain randomization).

    Gestión de recursos:
      Los entornos se cierran explícitamente al final de cada trial para
      liberar procesos de SubprocVecEnv.

    Parámetros
    ----------
    trial          : optuna.Trial
    config_env     : ConfigEntorno
    config_train   : ConfigEntrenamiento
    config_optuna  : ConfigOptuna
    dir_salida     : Path — directorio donde guardar logs del trial

    Retorna
    -------
    float — valor de la métrica (mayor = mejor)
    """
    # ── 1. Sugerir hiperparámetros ─────────────────────────────────────────
    hparams, pesos_rew = EspacioBusqueda.sugerir(trial)

    logger.info(
        "Trial %d — lr=%.2e, gamma=%.4f, clip=%.2f, n_steps=%d, "
        "λ_grad=%.2f, λ_ent=%.2f, λ_ibrm=%.2f, λ_cbf=%.2f",
        trial.number,
        hparams.learning_rate, hparams.gamma, hparams.clip_range, hparams.n_steps,
        pesos_rew.lambda_gradient, pesos_rew.lambda_entropy,
        pesos_rew.lambda_ibrm, pesos_rew.lambda_cbf,
    )

    # ── 2. Construir entornos ──────────────────────────────────────────────
    semilla_trial = config_train.seed + trial.number * 1000

    env_train = None
    env_eval  = None

    try:
        env_train = construir_vec_env_entrenamiento(
            config_env   = config_env,
            config_train = config_train,
            pesos_rew    = pesos_rew,
            n_envs       = config_train.n_envs_trial,
            seed         = semilla_trial,
        )
        env_eval = construir_vec_env_evaluacion(
            config_env   = config_env,
            config_train = config_train,
            pesos_rew    = pesos_rew,
            seed         = semilla_trial + 500,
        )

        # ── 3. Construir modelo ────────────────────────────────────────────
        dir_tb_trial = str(dir_salida / "tensorboard" / f"trial_{trial.number:03d}")
        modelo = construir_modelo_ppo(
            env          = env_train,
            hparams      = hparams,
            config_train = config_train,
            dir_tensorboard = dir_tb_trial,
            seed         = semilla_trial,
            verbose      = 0,
        )

        # ── 4. Callbacks del trial ─────────────────────────────────────────
        # Intervalo de poda: cada ~10% del presupuesto
        n_steps_reporte = max(5_000, config_optuna.presupuesto_trial // 10)

        cb_poda = CallbackOptunaPoda(
            trial              = trial,
            n_steps_evaluacion = n_steps_reporte,
            verbose            = 0,
        )
        # EvalCallback: evalúa periódicamente y guarda el mejor modelo del trial
        dir_mejor_trial = dir_salida / "mejores_trials" / f"trial_{trial.number:03d}"
        dir_mejor_trial.mkdir(parents=True, exist_ok=True)

        # `EvalCallback` compara `n_calls % eval_freq`: cuenta LLAMADAS al
        # callback, no pasos de entorno. Cada llamada avanza `num_envs` pasos,
        # así que hay que convertir. Sin esto, el callback se disparaba una sola
        # vez por trial (al final) o ninguna. Ver Exp J en la bitácora.
        eval_freq_llamadas = max(1, n_steps_reporte // env_train.num_envs)

        cb_eval = EvalCallback(
            eval_env            = env_eval,
            best_model_save_path= str(dir_mejor_trial),
            log_path            = str(dir_mejor_trial),
            eval_freq           = eval_freq_llamadas,
            n_eval_episodes     = config_train.n_episodios_eval,
            deterministic       = True,
            render              = False,
            verbose             = 0,
        )

        lista_callbacks = CallbackList([cb_poda, cb_eval])

        # ── 5. Entrenamiento del trial ─────────────────────────────────────
        t_inicio = time.time()
        modelo.learn(
            total_timesteps = config_optuna.presupuesto_trial,
            callback        = lista_callbacks,
            reset_num_timesteps = True,
            tb_log_name     = f"trial_{trial.number:03d}",
            progress_bar    = False,
        )
        duracion_s = time.time() - t_inicio

        # ── 6. Métricas finales del trial ──────────────────────────────────
        # Evaluación final determinista en env_eval (domain_rand=False)
        rew_media_eval = _evaluar_modelo(
            modelo       = modelo,
            env_eval     = env_eval,
            n_episodios  = config_train.n_episodios_eval * 2,
        )

        logger.info(
            "Trial %d completado en %.1fs — eval_rew_mean=%.4f",
            trial.number, duracion_s, rew_media_eval,
        )

        # Guardar metadata del trial en JSON para análisis posterior
        _guardar_metadata_trial(
            trial_number  = trial.number,
            hparams       = hparams,
            pesos_rew     = pesos_rew,
            metrica       = rew_media_eval,
            duracion_s    = duracion_s,
            dir_salida    = dir_salida,
        )

        return rew_media_eval

    except optuna.exceptions.TrialPruned:
        # Re-lanzar para que Optuna registre el trial como podado
        raise

    except Exception as exc:
        logger.error("Trial %d falló con excepción: %s", trial.number, exc, exc_info=True)
        # Retornar el peor valor posible para que Optuna no elija estos params
        return -1e9

    finally:
        # Siempre cerrar los entornos para liberar SubprocVecEnv workers
        if env_train is not None:
            try:
                env_train.close()
            except Exception:
                pass
        if env_eval is not None:
            try:
                env_eval.close()
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRENAMIENTO FINAL CON MEJORES HIPERPARÁMETROS
# ══════════════════════════════════════════════════════════════════════════════

def entrenar_modelo_final(
    config_env:      ConfigEntorno,
    config_train:    ConfigEntrenamiento,
    hparams:         HiperparametrosPPO,
    pesos_rew:       PesosRecompensa,
    n_pasos_total:   int,
    dir_salida:      Path,
) -> PPO:
    """
    Entrena el modelo PPO final con los mejores hiperparámetros encontrados.

    A diferencia de los trials de Optuna (cortos, muchos), este entrenamiento:
      - Usa el máximo de paralelismo (config_train.n_envs_entren)
      - Guarda checkpoints periódicos
      - Registra métricas de cobertura adicionales (CallbackMetricasPersonalizadas)
      - Normaliza las observaciones con VecNormalize (mejora convergencia de PPO)

    VecNormalize:
      Normaliza obs y rewards a varianza unitaria durante el entrenamiento.
      Las estadísticas se guardan junto al modelo para aplicarlas en inferencia
      (crítico para sim-to-real: el servidor Robotat debe usar los mismos stats).

    Parámetros
    ----------
    config_env     : ConfigEntorno
    config_train   : ConfigEntrenamiento
    hparams        : HiperparametrosPPO  — del estudio Optuna
    pesos_rew      : PesosRecompensa     — del estudio Optuna
    n_pasos_total  : int  — steps totales de entrenamiento
    dir_salida     : Path

    Retorna
    -------
    PPO  — modelo entrenado
    """
    logger.info("=" * 60)
    logger.info("ENTRENAMIENTO FINAL — %d steps", n_pasos_total)
    logger.info("  lr=%.2e  gamma=%.4f  clip=%.2f", hparams.learning_rate,
                hparams.gamma, hparams.clip_range)
    logger.info("  λ_grad=%.2f  λ_ent=%.2f  λ_ibrm=%.2f  λ_cbf=%.2f",
                pesos_rew.lambda_gradient, pesos_rew.lambda_entropy,
                pesos_rew.lambda_ibrm, pesos_rew.lambda_cbf)
    logger.info("=" * 60)

    # ── Directorios ────────────────────────────────────────────────────────
    dir_ckpt     = dir_salida / "checkpoints_final"
    dir_mejor    = dir_salida / "mejor_modelo_final"
    dir_tb       = dir_salida / "tensorboard" / "entrenamiento_final"
    dir_vecnorm  = dir_salida / "vecnormalize"

    for d in [dir_ckpt, dir_mejor, dir_tb, dir_vecnorm]:
        d.mkdir(parents=True, exist_ok=True)

    # ── Construir entornos ─────────────────────────────────────────────────
    env_train = construir_vec_env_entrenamiento(
        config_env   = config_env,
        config_train = config_train,
        pesos_rew    = pesos_rew,
        seed         = config_train.seed,
    )
    env_eval = construir_vec_env_evaluacion(
        config_env   = config_env,
        config_train = config_train,
        pesos_rew    = pesos_rew,
        seed         = config_train.seed + 999,
    )

    # ── VecNormalize (normalización de obs y recompensas) ──────────────────
    # clip_obs=10.0: recorta observaciones a ±10σ (evita outliers de OptiTrack)
    # clip_reward=10.0: recorta recompensas (estabiliza la política al inicio)
    env_train_norm = VecNormalize(
        env_train,
        norm_obs    = True,
        norm_reward = True,
        clip_obs    = 10.0,
        clip_reward = 10.0,
        gamma       = hparams.gamma,
    )
    # El env de evaluación comparte las estadísticas pero NO actualiza
    env_eval_norm = VecNormalize(
        env_eval,
        norm_obs    = True,
        norm_reward = False,  # no normalizar rewards en eval
        clip_obs    = 10.0,
        training    = False,  # no actualizar estadísticas durante eval
    )

    # ── Construir modelo ───────────────────────────────────────────────────
    modelo = construir_modelo_ppo(
        env             = env_train_norm,
        hparams         = hparams,
        config_train    = config_train,
        dir_tensorboard = str(dir_tb),
        seed            = config_train.seed,
        verbose         = 1,
    )

    # ── Callbacks ─────────────────────────────────────────────────────────
    cb_eval = EvalCallback(
        eval_env            = env_eval_norm,
        best_model_save_path= str(dir_mejor),
        log_path            = str(dir_mejor),
        # Misma conversión de unidades que en los trials (ver Exp J).
        eval_freq           = max(1, config_train.frecuencia_eval // env_train_norm.num_envs),
        n_eval_episodes     = config_train.n_episodios_eval,
        deterministic       = True,
        render              = False,
        verbose             = 1,
    )
    cb_ckpt = CheckpointCallback(
        # Misma conversión de unidades que en `cb_eval` (ver Exp J, bug D):
        # `CheckpointCallback` compara `n_calls % save_freq`, que cuenta
        # LLAMADAS al callback, no pasos de entorno. Cada llamada avanza
        # `num_envs` pasos, así que sin dividir se guardarían `num_envs`
        # checkpoints por cada uno pedido y el espaciado real NO sería el
        # que declara `frecuencia_ckpt`.
        save_freq   = max(1, config_train.frecuencia_ckpt // env_train_norm.num_envs),
        save_path   = str(dir_ckpt),
        name_prefix = "swarm_ppo",
        verbose     = 0,
    )
    cb_metricas = CallbackMetricasPersonalizadas(verbose=0)

    # VecNormalize sync callback: sincroniza estadísticas eval ← train
    cb_vecnorm_sync = _CallbackSyncVecNormalize(
        env_eval    = env_eval_norm,
        dir_vecnorm = dir_vecnorm,
        freq        = config_train.frecuencia_eval,
    )

    lista_callbacks = CallbackList([
        cb_eval, cb_ckpt, cb_metricas, cb_vecnorm_sync
    ])

    # ── Entrenar ───────────────────────────────────────────────────────────
    t_inicio = time.time()
    try:
        modelo.learn(
            total_timesteps     = n_pasos_total,
            callback            = lista_callbacks,
            reset_num_timesteps = True,
            tb_log_name         = "final",
            progress_bar        = True,
        )
    except KeyboardInterrupt:
        logger.warning("Entrenamiento interrumpido por el usuario. Guardando modelo...")
    finally:
        # Guardar modelo + estadísticas VecNormalize (SIEMPRE, incluso si interrumpido)
        ruta_modelo_final = dir_salida / "modelo_final.zip"
        ruta_vecnorm_final = dir_vecnorm / "vecnorm_final.pkl"
        modelo.save(str(ruta_modelo_final))
        env_train_norm.save(str(ruta_vecnorm_final))
        logger.info("Modelo guardado → %s", ruta_modelo_final)
        logger.info("VecNormalize guardado → %s", ruta_vecnorm_final)

    duracion_min = (time.time() - t_inicio) / 60.0
    logger.info("Entrenamiento final completado en %.1f minutos.", duracion_min)

    # ── Evaluación final ───────────────────────────────────────────────────
    rew_final = _evaluar_modelo(modelo, env_eval_norm, n_episodios=30)
    logger.info("Recompensa media final (eval): %.4f", rew_final)

    env_train_norm.close()
    env_eval_norm.close()

    return modelo


class _CallbackSyncVecNormalize(BaseCallback):
    """
    Sincroniza las estadísticas de normalización del entorno de entrenamiento
    al de evaluación periódicamente.

    Esto es necesario porque VecNormalize mantiene una media y varianza en
    movimiento. El env de evaluación debe usar las mismas estadísticas que
    el de entrenamiento para que las observaciones sean comparables.
    """

    def __init__(
        self,
        env_eval:    VecNormalize,
        dir_vecnorm: Path,
        freq:        int = 20_000,
    ) -> None:
        super().__init__(verbose=0)
        self.env_eval    = env_eval
        self.dir_vecnorm = dir_vecnorm
        self.freq        = freq

    def _on_step(self) -> bool:
        if self.num_timesteps % self.freq == 0:
            # Sincronizar estadísticas
            assert isinstance(self.training_env, VecNormalize), \
                "El entorno de entrenamiento debe ser VecNormalize."
            self.env_eval.obs_rms    = self.training_env.obs_rms
            self.env_eval.ret_rms    = self.training_env.ret_rms
            self.env_eval.clip_obs   = self.training_env.clip_obs

            # Guardar snapshot de VecNormalize
            ruta = self.dir_vecnorm / f"vecnorm_step_{self.num_timesteps}.pkl"
            self.training_env.save(str(ruta))
        return True


# ══════════════════════════════════════════════════════════════════════════════
#  UTILIDADES DE EVALUACIÓN Y ANÁLISIS
# ══════════════════════════════════════════════════════════════════════════════

def _evaluar_modelo(
    modelo:      PPO,
    env_eval:    VecEnv,
    n_episodios: int = 10,
) -> float:
    """
    Evalúa el modelo de forma determinista y retorna la recompensa episódica media.

    Usa el env_eval como está (puede ser VecNormalize o VecMonitor).
    Ejecuta n_episodios episodios y promedia la recompensa total por episodio.

    Parámetros
    ----------
    modelo      : PPO
    env_eval    : VecEnv
    n_episodios : int

    Retorna
    -------
    float — ep_rew_mean (promedio sobre n_episodios)
    """
    all_rewards: List[float] = []
    obs          = env_eval.reset()
    ep_rewards   = np.zeros(env_eval.num_envs, dtype=np.float32)
    eps_completos = 0

    # Límite de steps para evitar bucles infinitos si el entorno no termina
    max_steps_eval = n_episodios * 1000

    for _ in range(max_steps_eval):
        accion, _ = modelo.predict(obs, deterministic=True)
        obs, rewards, dones, _ = env_eval.step(accion)
        ep_rewards += np.asarray(rewards)

        for idx, done in enumerate(dones):
            if done:
                all_rewards.append(float(ep_rewards[idx]))
                ep_rewards[idx] = 0.0
                eps_completos += 1
                if eps_completos >= n_episodios:
                    break

        if eps_completos >= n_episodios:
            break

    if not all_rewards:
        logger.warning("_evaluar_modelo: ningún episodio completado.")
        return -1e9

    return float(np.mean(all_rewards))


def _guardar_metadata_trial(
    trial_number: int,
    hparams:      HiperparametrosPPO,
    pesos_rew:    PesosRecompensa,
    metrica:      float,
    duracion_s:   float,
    dir_salida:   Path,
) -> None:
    """
    Guarda un JSON con la metadata de un trial para análisis post-Optuna.

    Parámetros
    ----------
    trial_number : int
    hparams      : HiperparametrosPPO
    pesos_rew    : PesosRecompensa
    metrica      : float — valor de la métrica objetivo
    duracion_s   : float — duración del trial en segundos
    dir_salida   : Path
    """
    dir_meta = dir_salida / "metadata_trials"
    dir_meta.mkdir(parents=True, exist_ok=True)

    metadata = {
        "trial_number": trial_number,
        "metrica":      metrica,
        "duracion_s":   duracion_s,
        "hparams":      asdict(hparams),
        "pesos_recompensa": asdict(pesos_rew),
        "timestamp":    time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    ruta = dir_meta / f"trial_{trial_number:03d}.json"
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


def analizar_estudio(
    estudio:    optuna.Study,
    dir_salida: Path,
) -> Tuple[HiperparametrosPPO, PesosRecompensa]:
    """
    Extrae y registra los mejores hiperparámetros del estudio de Optuna.

    Reporta:
      - Mejor trial y su métrica.
      - Top-5 trials.
      - Importancia de hiperparámetros (si el estudio tiene ≥10 trials).
      - Guarda un JSON con los mejores params.

    Parámetros
    ----------
    estudio    : optuna.Study
    dir_salida : Path

    Retorna
    -------
    (HiperparametrosPPO, PesosRecompensa) — mejores hiperparámetros encontrados
    """
    mejor_trial = estudio.best_trial

    logger.info("=" * 60)
    logger.info("RESULTADO DE OPTIMIZACIÓN BAYESIANA")
    logger.info("  Trials completados : %d", len(estudio.trials))
    logger.info("  Mejor trial        : #%d", mejor_trial.number)
    logger.info("  Mejor métrica      : %.6f", mejor_trial.value)
    logger.info("  Parámetros:")
    for nombre, valor in mejor_trial.params.items():
        logger.info("    %-25s = %s", nombre, valor)
    logger.info("=" * 60)

    # Top-5 trials
    trials_completos = [
        t for t in estudio.trials
        if t.state == optuna.trial.TrialState.COMPLETE
    ]
    trials_ordenados = sorted(
        trials_completos, key=lambda t: t.value or -1e9, reverse=True
    )
    logger.info("Top-5 trials:")
    for i, t in enumerate(trials_ordenados[:5], 1):
        logger.info("  %d. Trial #%d — métrica=%.4f", i, t.number, t.value)

    # Importancia de hiperparámetros (requiere ≥10 trials completados)
    if len(trials_completos) >= 10:
        try:
            importancias = optuna.importance.get_param_importances(estudio)
            logger.info("Importancia de hiperparámetros:")
            for nombre, imp in sorted(
                importancias.items(), key=lambda x: x[1], reverse=True
            ):
                logger.info("  %-25s: %.4f", nombre, imp)
        except Exception as exc:
            logger.warning("No se pudo calcular importancia de params: %s", exc)

    # Reconstruir objetos dataclass desde los parámetros del mejor trial
    p = mejor_trial.params
    n_steps = 2 ** p.get("n_steps_exp", 9)
    batch_divisor = p.get("batch_divisor", 2)
    batch_size = max(32, n_steps // batch_divisor)

    mejores_hparams = HiperparametrosPPO(
        learning_rate = p["learning_rate"],
        gamma         = p["gamma"],
        clip_range    = p["clip_range"],
        n_steps       = n_steps,
        batch_size    = batch_size,
        n_epochs      = p.get("n_epochs", 10),
        ent_coef      = p["ent_coef"],
        gae_lambda    = p["gae_lambda"],
    )
    mejores_pesos = PesosRecompensa(
        lambda_gradient = p["lambda_gradient"],
        lambda_entropy  = p["lambda_entropy"],
        lambda_ibrm     = p["lambda_ibrm"],
        lambda_cbf      = p["lambda_cbf"],
    )

    # Guardar mejores params como JSON
    mejor_config = {
        "trial_number":      mejor_trial.number,
        "metrica":           mejor_trial.value,
        "hparams":           asdict(mejores_hparams),
        "pesos_recompensa":  asdict(mejores_pesos),
        "timestamp":         time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    ruta_mejor = dir_salida / "mejores_hiperparametros.json"
    with open(ruta_mejor, "w", encoding="utf-8") as f:
        json.dump(mejor_config, f, indent=2, ensure_ascii=False)
    logger.info("Mejores hiperparámetros guardados → %s", ruta_mejor)

    return mejores_hparams, mejores_pesos


def cargar_mejores_hiperparametros(ruta_json: str) -> Tuple[HiperparametrosPPO, PesosRecompensa]:
    """
    Carga los mejores hiperparámetros desde el JSON guardado por `analizar_estudio`.

    Útil para reanudar el entrenamiento final sin re-ejecutar Optuna.

    Parámetros
    ----------
    ruta_json : str — ruta al archivo JSON

    Retorna
    -------
    (HiperparametrosPPO, PesosRecompensa)
    """
    with open(ruta_json, "r", encoding="utf-8") as f:
        datos = json.load(f)

    hparams   = HiperparametrosPPO(**datos["hparams"])
    pesos_rew = PesosRecompensa(**datos["pesos_recompensa"])
    logger.info("Hiperparámetros cargados desde %s (trial #%d, métrica=%.4f)",
                ruta_json, datos["trial_number"], datos["metrica"])
    return hparams, pesos_rew


# ══════════════════════════════════════════════════════════════════════════════
#  FUNCIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def main(args: argparse.Namespace) -> None:
    """
    Orquesta el flujo completo de optimización + entrenamiento.

    Modos de operación
    ──────────────────
    'optimizar' → Ejecuta el estudio de Optuna y guarda los mejores params.
    'entrenar'  → Carga los mejores params y ejecuta el entrenamiento final.
    'completo'  → Ejecuta Optuna primero, luego entrenamiento final
                  (pipeline de una sola ejecución).

    Persistencia del estudio de Optuna
    ────────────────────────────────────
    Se usa almacenamiento SQLite en dir_salida/optuna_studies/<nombre>.db.
    Si el archivo existe, Optuna REANUDA el estudio (agrega trials).
    Si no existe, crea un nuevo estudio.
    Esto permite interrumpir y reanudar la optimización en cualquier momento.
    """
    # ── Configuraciones ────────────────────────────────────────────────────
    config_env = ConfigEntorno(
        n_agentes     = args.n_agentes,
        arena_size    = (args.arena_w, args.arena_h),
        max_steps_ep  = args.max_steps_ep,
        radio_com     = args.radio_com,
        domain_rand   = not args.sin_domain_rand,
    )
    config_train = ConfigEntrenamiento(
        n_envs_entren    = args.n_envs,
        n_envs_trial     = max(2, args.n_envs // 2),
        dir_logs         = args.dir_logs,
        dir_modelos      = args.dir_modelos,
        seed             = args.seed,
    )
    config_optuna = ConfigOptuna(
        nombre_estudio   = args.nombre_estudio,
        n_trials         = args.n_trials,
        presupuesto_trial= args.presupuesto_trial,
        n_jobs           = args.n_jobs,
    )

    dir_salida = Path(args.dir_modelos) / args.nombre_estudio
    dir_salida.mkdir(parents=True, exist_ok=True)

    # Logging a archivo también
    fh = logging.FileHandler(dir_salida / "entrenamiento.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)

    logger.info("Modo: %s", args.modo)
    logger.info("Directorio de salida: %s", dir_salida)

    # ── Fase 1: Optimización Bayesiana ─────────────────────────────────────
    if args.modo in ("optimizar", "completo"):

        # Configurar Optuna (silenciar logs de Optuna, usar nuestro logger)
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        # Almacenamiento persistente SQLite
        dir_db = Path(config_optuna.dir_almacenamiento)
        dir_db.mkdir(parents=True, exist_ok=True)
        url_storage = f"sqlite:///{dir_db / config_optuna.nombre_estudio}.db"

        estudio = optuna.create_study(
            study_name  = config_optuna.nombre_estudio,
            storage     = url_storage,
            direction   = "maximize",       # queremos maximizar ep_rew_mean
            sampler     = TPESampler(
                n_startup_trials = config_optuna.n_startup_trials,
                seed             = config_train.seed,
            ),
            pruner      = MedianPruner(
                n_startup_trials = config_optuna.n_startup_trials,
                n_warmup_steps   = config_optuna.n_warmup_steps,
                interval_steps   = config_optuna.intervalo_poda,
            ),
            load_if_exists = True,  # reanudar si existe el estudio
        )

        # Closure que captura los configs (Optuna llama con un solo argumento: trial)
        def _objetivo(trial: optuna.Trial) -> float:
            return objetivo_optuna(
                trial        = trial,
                config_env   = config_env,
                config_train = config_train,
                config_optuna= config_optuna,
                dir_salida   = dir_salida,
            )

        trials_previos = len(estudio.trials)
        logger.info(
            "Iniciando estudio Optuna '%s' — %d trials previos, %d nuevos",
            config_optuna.nombre_estudio, trials_previos, config_optuna.n_trials,
        )

        estudio.optimize(
            _objetivo,
            n_trials    = config_optuna.n_trials,
            timeout     = config_optuna.timeout_total_s,
            n_jobs      = config_optuna.n_jobs,
            show_progress_bar = True,
        )

        mejores_hparams, mejores_pesos = analizar_estudio(estudio, dir_salida)

    # ── Carga de parámetros existentes (modo 'entrenar') ───────────────────
    elif args.modo == "entrenar":
        ruta_json = dir_salida / "mejores_hiperparametros.json"
        if not ruta_json.exists():
            logger.error(
                "No se encontró '%s'. Ejecuta primero con --modo optimizar.",
                ruta_json,
            )
            sys.exit(1)
        mejores_hparams, mejores_pesos = cargar_mejores_hiperparametros(str(ruta_json))

    else:
        logger.error("Modo desconocido: %s", args.modo)
        sys.exit(1)

    # ── Fase 2: Entrenamiento final ────────────────────────────────────────
    if args.modo in ("entrenar", "completo"):
        entrenar_modelo_final(
            config_env    = config_env,
            config_train  = config_train,
            hparams       = mejores_hparams,
            pesos_rew     = mejores_pesos,
            n_pasos_total = args.n_pasos,
            dir_salida    = dir_salida,
        )

    logger.info("Pipeline completado exitosamente ✓")


# ══════════════════════════════════════════════════════════════════════════════
#  PARSING DE ARGUMENTOS CLI
# ══════════════════════════════════════════════════════════════════════════════

def _construir_parser() -> argparse.ArgumentParser:
    """
    Construye el parser de argumentos de línea de comandos.

    Separa los argumentos en grupos lógicos para mayor legibilidad.
    """
    parser = argparse.ArgumentParser(
        description="Entrenamiento MADRL-PPO para enjambre de robots Pololu 3pi+",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Modo de operación
    parser.add_argument(
        "--modo",
        choices=["optimizar", "entrenar", "completo"],
        default="completo",
        help=(
            "'optimizar': solo fase Optuna  |  "
            "'entrenar': solo fase final  |  "
            "'completo': ambas fases en secuencia"
        ),
    )

    # ── Entorno ──────────────────────────────────────────────────────────
    grp_env = parser.add_argument_group("Entorno")
    grp_env.add_argument("--n_agentes",       type=int,   default=5)
    grp_env.add_argument("--arena_w",         type=float, default=3.0,
                         help="Ancho del arena [m]")
    grp_env.add_argument("--arena_h",         type=float, default=3.0,
                         help="Alto del arena [m]")
    grp_env.add_argument("--max_steps_ep",    type=int,   default=500)
    grp_env.add_argument("--radio_com",       type=float, default=1.0,
                         help="Radio de comunicación inter-agente [m]")
    grp_env.add_argument("--sin_domain_rand", action="store_true",
                         help="Desactiva Domain Randomization (debugging)")

    # ── Entrenamiento ────────────────────────────────────────────────────
    grp_train = parser.add_argument_group("Entrenamiento")
    grp_train.add_argument("--n_envs",   type=int, default=8,
                            help="Entornos paralelos durante entrenamiento final")
    grp_train.add_argument("--n_pasos",  type=int, default=5_000_000,
                            help="Steps totales de entrenamiento final")
    grp_train.add_argument("--seed",     type=int, default=42)
    grp_train.add_argument("--dir_logs",    default="./logs")
    grp_train.add_argument("--dir_modelos", default="./modelos")

    # ── Optuna ────────────────────────────────────────────────────────────
    grp_optuna = parser.add_argument_group("Optimización Bayesiana (Optuna)")
    grp_optuna.add_argument("--nombre_estudio",    default="swarm_cyano_v1")
    grp_optuna.add_argument("--n_trials",          type=int,   default=30)
    grp_optuna.add_argument("--presupuesto_trial", type=int,   default=200_000,
                             help="Steps de entrenamiento por trial de Optuna")
    grp_optuna.add_argument("--n_jobs",            type=int,   default=1,
                             help="Trials de Optuna en paralelo (1=secuencial)")

    return parser


if __name__ == "__main__":
    parser = _construir_parser()
    args = parser.parse_args()
    main(args)
