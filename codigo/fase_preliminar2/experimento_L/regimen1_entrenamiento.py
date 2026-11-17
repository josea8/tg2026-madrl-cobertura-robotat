"""
regimen1_entrenamiento.py — Experimento L, régimen 1: ENTRENAMIENTO.

Entrena la configuración de referencia (Trial 13, semilla 42, 200 000 pasos,
4 entornos = 20 flujos, como el estudio original y la Fase 0 del Exp J) en UNA
condición de dispositivo, y cronometra por separado:

  - recolección de experiencia (`collect_rollouts`), y dentro de ella
      · el tiempo del entorno (`step_async` + `step_wait` del VecEnv, que con
        4 procesos incluye la comunicación entre procesos), y
      · el resto = inferencia de la política + llenado del buffer;
  - actualización de la política (`train`: 13 épocas × 40 minibatches de 64);
  - tiempo de pared total de `learn`.

El reparto porcentual medido acá es el que se contrasta con el 83/17 del
Exp J. Diferencia metodológica declarada: el perfilador del Exp J
(`perfilar_cuello_botella.py`) midió el entorno APARTE, en un solo proceso y
con acciones aleatorias; acá el reparto se mide DENTRO de la corrida real,
con los cuatro trabajadores del VecEnv.

Con CUDA se llama a `torch.cuda.synchronize()` antes de detener cada reloj,
para no contar como terminado un trabajo que la GPU aún tiene en cola.

Sin `EvalCallback`: las evaluaciones periódicas contaminarían el tiempo.
Al terminar corre el protocolo único (100 episodios deterministas, semillas
42·10000 + i, reflexión elástica) sobre el modelo final, en el mismo
dispositivo, para la verificación de equivalencia entre condiciones.

Uso (una condición por invocación; NUNCA correr dos a la vez, comparten CPU):
  venv_lab4 : python regimen1_entrenamiento.py --condicion gpu         --dispositivo cuda
  venv_lab4 : python regimen1_entrenamiento.py --condicion cpu_control --dispositivo cpu
  tesis     : python regimen1_entrenamiento.py --condicion referencia  --dispositivo cpu

No modifica `train.py`: importa la copia `train_L.py`.

Autor: José — Tesis Mecatrónica UVG
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

import numpy as np
import torch

from comun_L import (
    COBERTURA_OFICIAL_MADRL,
    DIR_RESULTADOS,
    HPARAMS_TRIAL13,
    MAX_STEPS_EP,
    MonitorCargaCPU,
    N_AGENTES,
    PESOS_TRIAL13,
    SEMILLA,
    ARENA,
    COMM_RADIUS,
    construir_env_protocolo,
    correr_episodio_cronometrado,
    declarar_hardware,
    escribir_csv,
    respaldar_si_existe,
    resumen_estadistico,
    validar_condicion,
)

from stable_baselines3.common.vec_env import VecEnvWrapper

from train_L import (
    ConfigEntorno,
    ConfigEntrenamiento,
    HiperparametrosPPO,
    PesosRecompensa,
    construir_modelo_ppo,
    construir_vec_env_entrenamiento,
)

PRESUPUESTO_PASOS: int = 200_000
N_ENVS:            int = 4
N_EPS_PROTOCOLO:   int = 100


# ══════════════════════════════════════════════════════════════════════════════
#  Cronómetros
# ══════════════════════════════════════════════════════════════════════════════

class EnvCronometrado(VecEnvWrapper):
    """
    Envoltura del VecEnv que acumula el tiempo de pared gastado entre
    `step_async` y el retorno de `step_wait`: la simulación del entorno vista
    desde el proceso principal (con `num_cpus=4` incluye el IPC).
    """

    def __init__(self, venv) -> None:
        super().__init__(venv)
        self.segundos_step: float = 0.0
        self.n_llamadas:    int   = 0
        self._t0:           float = 0.0

    def reset(self):
        return self.venv.reset()

    def step_async(self, actions) -> None:
        self._t0 = time.perf_counter()
        self.venv.step_async(actions)

    def step_wait(self):
        resultado = self.venv.step_wait()
        self.segundos_step += time.perf_counter() - self._t0
        self.n_llamadas += 1
        return resultado


def instalar_cronometros(modelo, env_cron: EnvCronometrado, es_cuda: bool) -> Dict[str, List[float]]:
    """
    Reemplaza `collect_rollouts` y `train` de la INSTANCIA por versiones
    cronometradas. `learn()` de SB3 los invoca como atributos de instancia,
    así que no hace falta subclasear ni tocar `train_L.py`.

    Devuelve el registro por iteración: segundos de rollout, de entorno
    dentro del rollout, y de actualización.
    """
    registro: Dict[str, List[float]] = {"rollout": [], "entorno": [], "actualizacion": []}
    collect_original: Callable = modelo.collect_rollouts
    train_original:   Callable = modelo.train

    def collect_rollouts_cronometrado(*args: Any, **kwargs: Any):
        env_antes = env_cron.segundos_step
        t0 = time.perf_counter()
        resultado = collect_original(*args, **kwargs)
        if es_cuda:
            torch.cuda.synchronize()
        registro["rollout"].append(time.perf_counter() - t0)
        registro["entorno"].append(env_cron.segundos_step - env_antes)
        return resultado

    def train_cronometrado() -> None:
        t0 = time.perf_counter()
        train_original()
        if es_cuda:
            torch.cuda.synchronize()
        registro["actualizacion"].append(time.perf_counter() - t0)

    modelo.collect_rollouts = collect_rollouts_cronometrado
    modelo.train = train_cronometrado
    return registro


# ══════════════════════════════════════════════════════════════════════════════
#  Protocolo de cobertura sobre el modelo entrenado
# ══════════════════════════════════════════════════════════════════════════════

def protocolo_cobertura(modelo, n_episodios: int, es_cuda: bool) -> Dict[str, Any]:
    """100 episodios deterministas del protocolo único, sobre el modelo dado."""
    env = construir_env_protocolo(N_AGENTES, seed=SEMILLA)
    filas: List[Dict[str, Any]] = []
    t_ini = time.perf_counter()
    for i in range(n_episodios):
        r = correr_episodio_cronometrado(
            modelo, env, seed_ep=SEMILLA * 10_000 + i, sincronizar_cuda=es_cuda,
        )
        r.pop("tiempos_ms")
        r["episodio"] = i
        r["seed_ep"] = SEMILLA * 10_000 + i
        filas.append(r)
    duracion = time.perf_counter() - t_ini
    cob = np.array([f["cobertura_aoi_final"] for f in filas])
    col = np.array([f["colisiones_015"] for f in filas], dtype=float)
    return {
        "n_episodios": n_episodios,
        "duracion_s":  duracion,
        "cobertura_aoi_final": resumen_estadistico(cob),
        "colisiones_015":      resumen_estadistico(col),
        "colisiones_022":      resumen_estadistico(np.array([f["colisiones_022"] for f in filas], dtype=float)),
        "t_decision_ms_media_de_medias": float(np.mean([f["t_decision_ms_media"] for f in filas])),
        "episodios": filas,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Principal
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--condicion", required=True, choices=("gpu", "cpu_control", "referencia"))
    parser.add_argument("--dispositivo", required=True, choices=("cpu", "cuda"))
    parser.add_argument("--pasos", type=int, default=PRESUPUESTO_PASOS)
    parser.add_argument("--n_envs", type=int, default=N_ENVS)
    parser.add_argument("--semilla", type=int, default=SEMILLA)
    parser.add_argument("--n_eps_protocolo", type=int, default=N_EPS_PROTOCOLO)
    parser.add_argument("--hilos_torch", type=int, default=None,
                        help="torch.set_num_threads en el proceso principal (por defecto no se toca: 8)")
    parser.add_argument("--sufijo", default="",
                        help="repetición: escribe en resultados/regimen1/<condicion>_<sufijo>")
    args = parser.parse_args()

    validar_condicion(args.condicion, args.dispositivo)
    es_cuda = args.dispositivo == "cuda"
    if args.hilos_torch is not None:
        torch.set_num_threads(args.hilos_torch)

    dir_salida = DIR_RESULTADOS / "regimen1" / (args.condicion + (f"_{args.sufijo}" if args.sufijo else ""))
    respaldo = respaldar_si_existe(dir_salida)
    if respaldo is not None:
        print(f"[L1] resultados previos respaldados en {respaldo}", flush=True)
    dir_salida.mkdir(parents=True, exist_ok=True)

    hardware = declarar_hardware()
    print(f"[L1] condición={args.condicion} dispositivo={args.dispositivo} "
          f"torch={hardware['torch']} hilos={hardware['torch_hilos']} "
          f"cpu_carga={hardware['cpu']['carga_pct_al_arrancar']}%", flush=True)

    config_env = ConfigEntorno(
        n_agentes=N_AGENTES, arena_size=ARENA, max_steps_ep=MAX_STEPS_EP,
        radio_com=COMM_RADIUS, domain_rand=True,
    )
    config_train = ConfigEntrenamiento(seed=args.semilla)
    hparams = HiperparametrosPPO(**HPARAMS_TRIAL13)
    pesos   = PesosRecompensa(**PESOS_TRIAL13)

    t_total_ini = time.perf_counter()
    monitor = MonitorCargaCPU(intervalo_s=2.0)
    monitor.iniciar()

    print("[L1] construyendo VecEnv de entrenamiento...", flush=True)
    t0 = time.perf_counter()
    env_train = construir_vec_env_entrenamiento(
        config_env=config_env, config_train=config_train,
        pesos_rew=pesos, n_envs=args.n_envs, seed=args.semilla,
    )
    env_cron = EnvCronometrado(env_train)
    seg_construccion_env = time.perf_counter() - t0

    t0 = time.perf_counter()
    modelo = construir_modelo_ppo(
        env=env_cron, hparams=hparams, config_train=config_train,
        dir_tensorboard=None, seed=args.semilla, verbose=0,
        dispositivo=args.dispositivo,
    )
    if es_cuda:
        torch.cuda.synchronize()
    seg_construccion_modelo = time.perf_counter() - t0
    dispositivo_real = str(modelo.policy.device)
    print(f"[L1] política en {dispositivo_real}; buffer={hparams.n_steps}×{env_cron.num_envs}"
          f"={hparams.n_steps * env_cron.num_envs}, batch={hparams.batch_size}, "
          f"epochs={hparams.n_epochs}", flush=True)

    registro = instalar_cronometros(modelo, env_cron, es_cuda)

    print(f"[L1] entrenando {args.pasos} pasos...", flush=True)
    t0 = time.perf_counter()
    modelo.learn(total_timesteps=args.pasos, reset_num_timesteps=True, progress_bar=False)
    if es_cuda:
        torch.cuda.synchronize()
    seg_learn = time.perf_counter() - t0
    pasos_reales = int(modelo.num_timesteps)

    # Los cronómetros son atributos de INSTANCIA que cierran sobre el VecEnv;
    # `save()` serializa `__dict__` con cloudpickle y se colgaría intentando
    # encurtir las tuberías de los trabajadores. Se retiran antes de guardar:
    # vuelven a regir los métodos de la clase.
    del modelo.collect_rollouts
    del modelo.train
    ruta_modelo = dir_salida / "modelo_final.zip"
    modelo.save(str(ruta_modelo))
    try:
        env_cron.close()
    except Exception:
        pass

    seg_rollout = float(np.sum(registro["rollout"]))
    seg_entorno = float(np.sum(registro["entorno"]))
    seg_infer   = seg_rollout - seg_entorno
    seg_update  = float(np.sum(registro["actualizacion"]))
    seg_resto   = seg_learn - seg_rollout - seg_update
    seg_red     = seg_infer + seg_update

    print(f"[L1] learn={seg_learn:.1f} s  entorno={seg_entorno:.1f} s  "
          f"inferencia={seg_infer:.1f} s  actualización={seg_update:.1f} s  "
          f"resto={seg_resto:.1f} s", flush=True)

    escribir_csv(
        dir_salida / "tiempos_por_iteracion.csv",
        (
            {"iteracion": k, "seg_rollout": registro["rollout"][k],
             "seg_entorno": registro["entorno"][k],
             "seg_inferencia": registro["rollout"][k] - registro["entorno"][k],
             "seg_actualizacion": registro["actualizacion"][k] if k < len(registro["actualizacion"]) else float("nan")}
            for k in range(len(registro["rollout"]))
        ),
        ("iteracion", "seg_rollout", "seg_entorno", "seg_inferencia", "seg_actualizacion"),
    )

    print(f"[L1] protocolo de cobertura, {args.n_eps_protocolo} episodios...", flush=True)
    protocolo = protocolo_cobertura(modelo, args.n_eps_protocolo, es_cuda)
    escribir_csv(
        dir_salida / "protocolo_episodios.csv",
        protocolo["episodios"],
        ("episodio", "seed_ep", "cobertura_aoi_final", "colisiones_015", "colisiones_022",
         "pasos", "episodio_completo", "t_decision_ms_media", "t_decision_ms_std",
         "t_decision_ms_mediana", "t_decision_ms_p95", "t_decision_ms_min"),
    )
    cob = protocolo["cobertura_aoi_final"]
    print(f"[L1] cobertura {cob['media']:.8f} ± {cob['std']:.8f}  "
          f"colisiones {protocolo['colisiones_015']['media']:.3f}  "
          f"(oficial modelo_PRIMERO {COBERTURA_OFICIAL_MADRL})", flush=True)

    seg_total = time.perf_counter() - t_total_ini
    carga = monitor.detener()
    print(f"[L1] carga de CPU del sistema durante la corrida: media {carga['ocupacion_sistema_pct_media']:.1f} % "
          f"(p90 {carga['ocupacion_sistema_pct_p90']:.1f} %), proceso principal {carga['proceso_principal_nucleos_medios']:.2f} núcleos", flush=True)
    reporte: Dict[str, Any] = {
        "experimento": "L", "regimen": 1,
        "carga_cpu_durante_corrida": carga,
        "condicion": args.condicion, "repeticion": args.sufijo or "1",
        "dispositivo_pedido": args.dispositivo,
        "dispositivo_real": dispositivo_real,
        "hardware": hardware,
        "configuracion": {
            "presupuesto_pasos": args.pasos, "pasos_reales": pasos_reales,
            "n_envs": args.n_envs, "n_streams": args.n_envs * N_AGENTES,
            "semilla": args.semilla, "condicion_borde": "reflexion_elastica",
            "domain_rand_entrenamiento": True,
            "hparams": HPARAMS_TRIAL13, "pesos_recompensa": PESOS_TRIAL13,
            "batch_size_efectivo": hparams.batch_size,
            "n_iteraciones_ppo": len(registro["rollout"]),
            "n_actualizaciones": len(registro["actualizacion"]),
            "n_minibatches_por_actualizacion": (hparams.n_steps * args.n_envs * N_AGENTES) // hparams.batch_size * hparams.n_epochs,
            "eval_callback": False,
        },
        "tiempos_s": {
            "construccion_env":      seg_construccion_env,
            "construccion_modelo":   seg_construccion_modelo,
            "learn_total":           seg_learn,
            "rollout_total":         seg_rollout,
            "entorno":               seg_entorno,
            "inferencia_rollout":    seg_infer,
            "actualizacion":         seg_update,
            "red_total":             seg_red,
            "resto_learn":           seg_resto,
            "protocolo_cobertura":   protocolo["duracion_s"],
            "total_script":          seg_total,
        },
        "reparto_pct_de_learn": {
            "entorno":            100.0 * seg_entorno / seg_learn,
            "inferencia_rollout": 100.0 * seg_infer / seg_learn,
            "actualizacion":      100.0 * seg_update / seg_learn,
            "red_total":          100.0 * seg_red / seg_learn,
            "resto":              100.0 * seg_resto / seg_learn,
        },
        "pasos_por_segundo_learn": pasos_reales / seg_learn,
        "protocolo_cobertura": {k: v for k, v in protocolo.items() if k != "episodios"},
    }
    ruta_reporte = dir_salida / "reporte.json"
    ruta_reporte.write_bytes(json.dumps(reporte, indent=2, ensure_ascii=False).encode("utf-8"))
    print(f"[L1] reporte -> {ruta_reporte}", flush=True)
    print(json.dumps(reporte["reparto_pct_de_learn"], indent=2), flush=True)


if __name__ == "__main__":
    main()
