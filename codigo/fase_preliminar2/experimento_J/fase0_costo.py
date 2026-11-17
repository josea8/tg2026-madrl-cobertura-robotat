"""
fase0_costo.py — Experimento J, Fase 0: medición del costo de una prueba.

Corre UNA prueba completa con la configuración prevista para el estudio nuevo
y cronometra por separado cada bloque de costo, para proyectar el diseño
completo antes de comprometerlo:

  1. Entrenamiento PPO de 200 000 pasos (hiperparámetros del Trial 13).
  2. Las evaluaciones periódicas del EvalCallback (20 episodios, retención
     del mejor punto de control).
  3. El protocolo de cobertura AoI sobre el mejor punto de control
     (20 episodios deterministas, semillas 42·10000 + i).
  4. El mismo protocolo sobre el punto de control FINAL, para contrastar
     retención-del-mejor contra evaluación-por-punto-final.

No modifica ningún archivo existente: importa `swarm_env_skeleton` y `train`
en modo de sólo lectura. No lanza ningún estudio de Optuna.

Condición de borde: reflexión elástica (la del entorno de `fase_preliminar2`).

Autor: José — Tesis Mecatrónica UVG
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

DIR_PADRE = Path(__file__).resolve().parent.parent
if str(DIR_PADRE) not in sys.path:
    sys.path.insert(0, str(DIR_PADRE))

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import EvalCallback

from swarm_env_skeleton import D_SAFE, make_env
from train import (
    ConfigEntorno,
    ConfigEntrenamiento,
    HiperparametrosPPO,
    PesosRecompensa,
    construir_modelo_ppo,
    construir_vec_env_entrenamiento,
    construir_vec_env_evaluacion,
)

# ── Configuración de la Fase 0 ────────────────────────────────────────────────
PRESUPUESTO_PASOS:  int = 200_000
N_EPISODIOS_EVAL:   int = 20        # ≥20 exigido por el diseño (antes: 10)
FRECUENCIA_EVAL:    int = 20_000    # 10 evaluaciones en el presupuesto
N_ENVS_PRUEBA:      int = 4
SEMILLA:            int = 42
MAX_STEPS_EP:       int = 500
N_AGENTES:          int = 5
ARENA:            tuple = (3.0, 3.0)
COMM_RADIUS:      float = 1.0

DIR_SALIDA: Path = Path(__file__).resolve().parent / "resultados" / "fase0"

# Hiperparámetros del Trial 13 (modelos/tesis_v1/RESULTADO_PRIMERO)
HPARAMS_TRIAL13 = HiperparametrosPPO(
    learning_rate = 6.855028382061343e-05,
    gamma         = 0.9844980522475681,
    clip_range    = 0.20631649325745388,
    n_steps       = 128,
    batch_size    = 64,
    n_epochs      = 13,
    ent_coef      = 0.022872258876193912,
    gae_lambda    = 0.9608422073341644,
    vf_coef       = 0.5,
    max_grad_norm = 0.5,
)
PESOS_TRIAL13 = PesosRecompensa(
    lambda_gradient = 0.5622468083379316,
    lambda_entropy  = 1.1403296484190344,
    lambda_ibrm     = 0.48380314172632155,
    lambda_cbf      = 2.9655314099141474,
)
PESOS_TRIAL13_DICT: Dict[str, float] = {
    "lambda_gradient": PESOS_TRIAL13.lambda_gradient,
    "lambda_entropy":  PESOS_TRIAL13.lambda_entropy,
    "lambda_ibrm":     PESOS_TRIAL13.lambda_ibrm,
    "lambda_cbf":      PESOS_TRIAL13.lambda_cbf,
}


class EvalCallbackCronometrado(EvalCallback):
    """
    `EvalCallback` idéntico al de `train.py` pero que acumula el tiempo de
    pared gastado dentro de sus propias evaluaciones.

    Sirve para separar, en la proyección de costo, el gasto de entrenamiento
    puro del gasto de la evaluación periódica — que sube al pasar de 10 a 20
    episodios por evaluación.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.segundos_evaluando: float = 0.0
        self.n_evaluaciones:     int   = 0

    def _on_step(self) -> bool:
        va_a_evaluar = self.eval_freq > 0 and self.n_calls % self.eval_freq == 0
        if not va_a_evaluar:
            return super()._on_step()

        t_ini = time.time()
        resultado = super()._on_step()
        self.segundos_evaluando += time.time() - t_ini
        self.n_evaluaciones += 1
        return resultado


def evaluar_episodio_cobertura(modelo: PPO, env, seed_ep: int) -> Dict[str, float]:
    """
    Corre UN episodio determinista y devuelve las métricas del protocolo único.

    Réplica exacta de `evaluar_cobertura_multimetrica.evaluar_episodio`, para
    que los números del experimento J sean comparables con los de la bitácora.

    Nota sobre `n_colisiones`: es el número de PARES distintos que estuvieron
    a menos de D_SAFE en algún instante del episodio (0..10 con 5 agentes),
    no un conteo de eventos. La restricción de colisiones del diseño se aplica
    sobre esta definición.
    """
    obs_dict, _ = env.reset(seed=seed_ep)
    agents = list(obs_dict.keys())
    n_agents = len(agents)

    cobertura_hist: List[float] = []
    pares_colision: set = set()

    done = False
    while not done:
        obs_array   = np.stack([obs_dict[a] for a in agents])
        acciones, _ = modelo.predict(obs_array, deterministic=True)
        accion_dict = {a: acciones[i] for i, a in enumerate(agents)}
        obs_dict, _, term, trunc, _ = env.step(accion_dict)

        cobertura_hist.append(1.0 - float(np.mean(env._field._grid_aoi)))

        pos_curr = np.array([env._estados[a][:2] for a in agents])
        for i in range(n_agents):
            for j in range(i + 1, n_agents):
                if np.linalg.norm(pos_curr[i] - pos_curr[j]) < D_SAFE:
                    pares_colision.add((i, j))

        done = all(trunc.values()) or all(term.values())

    cob_np    = np.asarray(cobertura_hist)
    idx_cross = np.where(cob_np >= 0.5)[0]

    return {
        "cobertura_aoi_final":            cobertura_hist[-1] if cobertura_hist else 0.0,
        "n_colisiones":                   float(len(pares_colision)),
        "tiempo_primera_cobertura_50pct": float(idx_cross[0]) if len(idx_cross) else float(MAX_STEPS_EP),
    }


def protocolo_cobertura(
    ruta_modelo: Path,
    n_episodios: int,
    seed_base:   int = SEMILLA,
) -> Dict[str, Any]:
    """
    Protocolo único de evaluación: `n_episodios` episodios deterministas con
    semillas `seed_base·10000 + i`, entorno sin domain randomization.

    Devuelve los agregados SIN redondear y el tiempo de pared del bloque.
    """
    modelo = PPO.load(str(ruta_modelo))
    env = make_env(
        n_agents       = N_AGENTES,
        arena_size     = ARENA,
        max_steps      = MAX_STEPS_EP,
        comm_radius    = COMM_RADIUS,
        reward_weights = PESOS_TRIAL13_DICT,
        domain_rand    = False,
        seed           = seed_base,
    )

    t_ini = time.time()
    episodios: List[Dict[str, float]] = []
    for i in range(n_episodios):
        episodios.append(
            evaluar_episodio_cobertura(modelo, env, seed_ep=seed_base * 10_000 + i)
        )
    duracion_s = time.time() - t_ini

    agregados: Dict[str, Any] = {}
    for clave in ("cobertura_aoi_final", "n_colisiones", "tiempo_primera_cobertura_50pct"):
        valores = np.array([e[clave] for e in episodios], dtype=float)
        agregados[clave] = {
            "media": float(valores.mean()),
            "std":   float(valores.std(ddof=1)) if len(valores) > 1 else 0.0,
            "min":   float(valores.min()),
            "max":   float(valores.max()),
        }

    return {
        "ruta_modelo": str(ruta_modelo),
        "n_episodios": n_episodios,
        "duracion_s":  duracion_s,
        "agregados":   agregados,
        "episodios":   episodios,
    }


def main() -> None:
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    print(f"[fase0] salida -> {DIR_SALIDA}", flush=True)

    config_env = ConfigEntorno(
        n_agentes    = N_AGENTES,
        arena_size   = ARENA,
        max_steps_ep = MAX_STEPS_EP,
        radio_com    = COMM_RADIUS,
        domain_rand  = True,
    )
    config_train = ConfigEntrenamiento(
        n_envs_eval      = 2,
        n_episodios_eval = N_EPISODIOS_EVAL,
        seed             = SEMILLA,
    )

    t_total_ini = time.time()

    print("[fase0] construyendo entornos...", flush=True)
    t_ini = time.time()
    env_train = construir_vec_env_entrenamiento(
        config_env   = config_env,
        config_train = config_train,
        pesos_rew    = PESOS_TRIAL13,
        n_envs       = N_ENVS_PRUEBA,
        seed         = SEMILLA,
    )
    env_eval = construir_vec_env_evaluacion(
        config_env   = config_env,
        config_train = config_train,
        pesos_rew    = PESOS_TRIAL13,
        seed         = SEMILLA + 500,
    )
    seg_construccion = time.time() - t_ini

    modelo = construir_modelo_ppo(
        env             = env_train,
        hparams         = HPARAMS_TRIAL13,
        config_train    = config_train,
        dir_tensorboard = str(DIR_SALIDA / "tensorboard"),
        seed            = SEMILLA,
        verbose         = 0,
    )

    # `EvalCallback` cuenta LLAMADAS al callback, no pasos de entorno: con un
    # VecEnv de `num_envs` streams, cada llamada avanza `num_envs` pasos. Hay
    # que dividir para que `FRECUENCIA_EVAL` signifique pasos de entorno.
    # Sin esta conversión el callback no se dispara nunca (ver bitácora Exp J).
    eval_freq_llamadas = max(1, FRECUENCIA_EVAL // env_train.num_envs)
    print(
        f"[fase0] num_envs={env_train.num_envs} -> eval_freq={eval_freq_llamadas} "
        f"llamadas = {FRECUENCIA_EVAL} pasos",
        flush=True,
    )

    cb_eval = EvalCallbackCronometrado(
        eval_env             = env_eval,
        best_model_save_path = str(DIR_SALIDA / "mejor_punto_control"),
        log_path             = str(DIR_SALIDA / "mejor_punto_control"),
        eval_freq            = eval_freq_llamadas,
        n_eval_episodes      = N_EPISODIOS_EVAL,
        deterministic        = True,
        render               = False,
        verbose              = 0,
    )

    print(f"[fase0] entrenando {PRESUPUESTO_PASOS} pasos...", flush=True)
    t_ini = time.time()
    modelo.learn(
        total_timesteps     = PRESUPUESTO_PASOS,
        callback            = cb_eval,
        reset_num_timesteps = True,
        progress_bar        = False,
    )
    seg_learn_total = time.time() - t_ini
    seg_entren_puro = seg_learn_total - cb_eval.segundos_evaluando

    ruta_final = DIR_SALIDA / "modelo_final.zip"
    modelo.save(str(ruta_final))

    for e in (env_train, env_eval):
        try:
            e.close()
        except Exception:
            pass

    print("[fase0] protocolo de cobertura sobre el MEJOR punto de control...", flush=True)
    ruta_mejor = DIR_SALIDA / "mejor_punto_control" / "best_model.zip"
    cob_mejor: Optional[Dict[str, Any]] = None
    if ruta_mejor.exists():
        cob_mejor = protocolo_cobertura(ruta_mejor, N_EPISODIOS_EVAL)
    else:
        print("[fase0] AVISO: no se guardo best_model.zip", flush=True)

    print("[fase0] protocolo de cobertura sobre el punto de control FINAL...", flush=True)
    cob_final = protocolo_cobertura(ruta_final, N_EPISODIOS_EVAL)

    seg_total = time.time() - t_total_ini

    reporte: Dict[str, Any] = {
        "configuracion": {
            "presupuesto_pasos": PRESUPUESTO_PASOS,
            "n_episodios_eval":  N_EPISODIOS_EVAL,
            "frecuencia_eval":   FRECUENCIA_EVAL,
            "n_envs":            N_ENVS_PRUEBA,
            "semilla":           SEMILLA,
            "condicion_borde":   "reflexion_elastica",
            "hparams":           HPARAMS_TRIAL13.__dict__,
            "pesos_recompensa":  PESOS_TRIAL13_DICT,
        },
        "costos_s": {
            "construccion_entornos":     seg_construccion,
            "learn_total":               seg_learn_total,
            "entrenamiento_puro":        seg_entren_puro,
            "evaluaciones_periodicas":   cb_eval.segundos_evaluando,
            "n_evaluaciones":            cb_eval.n_evaluaciones,
            "protocolo_cobertura_mejor": cob_mejor["duracion_s"] if cob_mejor else None,
            "protocolo_cobertura_final": cob_final["duracion_s"],
            "total_prueba":              seg_total,
        },
        "cobertura_mejor_punto_control": cob_mejor,
        "cobertura_punto_control_final": cob_final,
    }

    ruta_reporte = DIR_SALIDA / "reporte_fase0.json"
    ruta_reporte.write_text(json.dumps(reporte, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[fase0] reporte -> {ruta_reporte}", flush=True)
    print(json.dumps(reporte["costos_s"], indent=2), flush=True)


if __name__ == "__main__":
    main()
