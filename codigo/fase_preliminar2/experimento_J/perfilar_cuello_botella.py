"""
perfilar_cuello_botella.py — ¿dónde se va el tiempo del entrenamiento?

Antes de decidir si conviene mover el entrenamiento a GPU hay que saber qué
fracción del tiempo se gasta en la red neuronal (que la GPU acelera) y qué
fracción en la simulación del entorno (que la GPU NO acelera, porque es código
Python/NumPy que corre en CPU).

La cota la pone la ley de Amdahl: si la red es el 20 % del tiempo, aunque la
GPU la hiciera instantánea el ahorro máximo es el 20 %.

Mide cuatro cosas por separado:
  1. Simulación pura del entorno, sin política (acciones aleatorias).
  2. Inferencia de la política, lote de `num_envs` observaciones (rollout).
  3. Inferencia de la política, UNA observación (como en la evaluación).
  4. Entrenamiento PPO completo, para contrastar con la suma de las partes.

No modifica nada ni entrena ningún modelo que se guarde.

Autor: José — Tesis Mecatrónica UVG
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Dict

import numpy as np
import torch

DIR_PADRE = Path(__file__).resolve().parent.parent
if str(DIR_PADRE) not in sys.path:
    sys.path.insert(0, str(DIR_PADRE))

from swarm_env_skeleton import make_env
from train import (
    ConfigEntorno,
    ConfigEntrenamiento,
    HiperparametrosPPO,
    PesosRecompensa,
    construir_modelo_ppo,
    construir_vec_env_entrenamiento,
)

PESOS = PesosRecompensa(
    lambda_gradient = 0.5622468083379316,
    lambda_entropy  = 1.1403296484190344,
    lambda_ibrm     = 0.48380314172632155,
    lambda_cbf      = 2.9655314099141474,
)
HPARAMS = HiperparametrosPPO(
    learning_rate = 6.855028382061343e-05,
    gamma         = 0.9844980522475681,
    clip_range    = 0.20631649325745388,
    n_steps       = 128,
    batch_size    = 64,
    n_epochs      = 13,
    ent_coef      = 0.022872258876193912,
    gae_lambda    = 0.9608422073341644,
)

N_PASOS_PRUEBA: int = 20_000


def medir_entorno_puro(n_pasos: int) -> Dict[str, float]:
    """Simulación del entorno con acciones aleatorias: sin red neuronal."""
    env = make_env(
        n_agents=5, arena_size=(3.0, 3.0), max_steps=500,
        comm_radius=1.0,
        reward_weights={
            "lambda_gradient": PESOS.lambda_gradient,
            "lambda_entropy":  PESOS.lambda_entropy,
            "lambda_ibrm":     PESOS.lambda_ibrm,
            "lambda_cbf":      PESOS.lambda_cbf,
        },
        domain_rand=False, seed=42,
    )
    obs, _ = env.reset(seed=420_000)
    agentes = list(obs.keys())
    espacio = env.action_space(agentes[0])

    n_transiciones = 0
    t_ini = time.perf_counter()
    while n_transiciones < n_pasos:
        acciones = {a: espacio.sample() for a in agentes}
        obs, _, term, trunc, _ = env.step(acciones)
        n_transiciones += len(agentes)
        if all(trunc.values()) or all(term.values()):
            obs, _ = env.reset(seed=420_000 + n_transiciones)
    dur = time.perf_counter() - t_ini
    return {"segundos": dur, "transiciones": n_transiciones,
            "transiciones_por_s": n_transiciones / dur}


def medir_inferencia(modelo, d_obs: int, lote: int, n_llamadas: int) -> Dict[str, float]:
    """Inferencia determinista de la política sobre un lote de observaciones."""
    obs = np.random.randn(lote, d_obs).astype(np.float32)
    modelo.predict(obs, deterministic=True)          # calentamiento
    t_ini = time.perf_counter()
    for _ in range(n_llamadas):
        modelo.predict(obs, deterministic=True)
    dur = time.perf_counter() - t_ini
    return {"segundos": dur, "llamadas": n_llamadas,
            "us_por_llamada": dur / n_llamadas * 1e6,
            "transiciones_por_s": n_llamadas * lote / dur}


def main() -> None:
    print(f"torch {torch.__version__} — CUDA disponible: {torch.cuda.is_available()}")
    print(f"hilos de torch: {torch.get_num_threads()}\n")

    print(f"[1] Entorno puro, {N_PASOS_PRUEBA} transiciones, sin red...")
    r_env = medir_entorno_puro(N_PASOS_PRUEBA)
    print(f"    {r_env['segundos']:.1f} s — {r_env['transiciones_por_s']:.0f} transiciones/s\n")

    config_env = ConfigEntorno(n_agentes=5, arena_size=(3.0, 3.0),
                               max_steps_ep=500, radio_com=1.0, domain_rand=True)
    config_train = ConfigEntrenamiento(seed=42)
    env_train = construir_vec_env_entrenamiento(
        config_env=config_env, config_train=config_train,
        pesos_rew=PESOS, n_envs=4, seed=42,
    )
    modelo = construir_modelo_ppo(
        env=env_train, hparams=HPARAMS, config_train=config_train,
        dir_tensorboard=None, seed=42, verbose=0,
    )
    d_obs = env_train.observation_space.shape[0]

    print(f"[2] Inferencia, lote de {env_train.num_envs} (como en el rollout)...")
    r_lote = medir_inferencia(modelo, d_obs, env_train.num_envs, 2_000)
    print(f"    {r_lote['us_por_llamada']:.0f} us/llamada — "
          f"{r_lote['transiciones_por_s']:.0f} transiciones/s\n")

    print("[3] Inferencia, lote de 5 (como en la evaluación, un episodio)...")
    r_uno = medir_inferencia(modelo, d_obs, 5, 2_000)
    print(f"    {r_uno['us_por_llamada']:.0f} us/llamada — "
          f"{r_uno['transiciones_por_s']:.0f} transiciones/s\n")

    print(f"[4] PPO.learn completo, {N_PASOS_PRUEBA} pasos...")
    t_ini = time.perf_counter()
    modelo.learn(total_timesteps=N_PASOS_PRUEBA, progress_bar=False)
    dur_learn = time.perf_counter() - t_ini
    print(f"    {dur_learn:.1f} s — {N_PASOS_PRUEBA / dur_learn:.0f} transiciones/s\n")

    # ── Descomposición ────────────────────────────────────────────────────
    seg_env  = N_PASOS_PRUEBA / r_env["transiciones_por_s"]
    seg_inf  = N_PASOS_PRUEBA / r_lote["transiciones_por_s"]
    seg_grad = dur_learn - seg_env - seg_inf

    print("=" * 62)
    print(f"DESCOMPOSICIÓN de {dur_learn:.1f} s de entrenamiento ({N_PASOS_PRUEBA} pasos)")
    print("=" * 62)
    for etiqueta, seg in (
        ("Simulación del entorno (CPU, no acelerable)", seg_env),
        ("Inferencia de la política (acelerable)",      seg_inf),
        ("Retropropagación y resto (acelerable)",       seg_grad),
    ):
        print(f"  {etiqueta:<45} {seg:7.1f} s  {100*seg/dur_learn:5.1f} %")
    frac_red = (seg_inf + seg_grad) / dur_learn
    print("-" * 62)
    print(f"  Fracción acelerable por GPU: {100*frac_red:.1f} %")
    print(f"  Cota de Amdahl si la GPU fuera INFINITAMENTE rápida:")
    print(f"    aceleración máxima = {1/(1-frac_red):.2f}x")
    print("=" * 62)

    env_train.close()


if __name__ == "__main__":
    main()
