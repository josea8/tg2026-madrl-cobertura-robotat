"""
diagnostico_presupuesto_J.py — verificación de la hipótesis (1) del Experimento J.

Replica el diagnóstico de puntos de control del estudio original
(`diagnostico_sin_vecnormalize/`) sobre la MEJOR configuración del estudio J:
entrena 500 000 pasos y evalúa a 100k, 200k, 300k, 400k y 500k bajo el
protocolo único.

La hipótesis a verificar
────────────────────────
El estudio original observó degradación monótona más allá de 200k y la atribuyó
—sin comprobarlo— al desajuste entre el presupuesto de sintonización (100k) y el
horizonte de uso. Si con una configuración sintonizada A 200k la degradación
desaparece o se atenúa, la hipótesis queda confirmada. Si persiste, queda
refutada y la causa es otra.

Diferencia con el diagnóstico original: se corren TRES semillas, no una. El
diagnóstico original usó una sola, y este proyecto ya sabe lo que eso vale.

`CheckpointCallback` compara `save_freq` contra `n_calls`, no contra pasos de
entorno; la conversión es explícita, igual que en `estudio_J.py`.

Uso
───
    python diagnostico_presupuesto_J.py                # las 3 semillas en serie
    python diagnostico_presupuesto_J.py --semilla 42   # una sola (trabajador)

Autor: José — Tesis Mecatrónica UVG
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

DIR_BASE = Path(__file__).resolve().parent
if str(DIR_BASE) not in sys.path:
    sys.path.insert(0, str(DIR_BASE))

from stable_baselines3.common.callbacks import CheckpointCallback

import estudio_J as J
from train import ConfigEntorno, ConfigEntrenamiento, construir_vec_env_entrenamiento
from train import construir_modelo_ppo

PASOS_TOTAL:   int = 500_000
PASOS_CKPT:    int = 100_000          # → 100k, 200k, 300k, 400k, 500k
SEMILLAS:      tuple = (42, 123, 777)
DIR_SALIDA:    Path = DIR_BASE / "resultados" / "diagnostico_presupuesto"


def cargar_mejor_configuracion() -> Dict[str, Any]:
    """Lee la mejor configuración del estudio J desde la base de Optuna."""
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    estudio = optuna.load_study(
        study_name="experimento_J",
        storage=f"sqlite:///{DIR_BASE / 'optuna_studies' / 'experimento_J.db'}",
    )
    mejor = estudio.best_trial
    return {
        "prueba":         mejor.number,
        "valor":          mejor.value,
        "lambda_cbf":     mejor.params["lambda_cbf"],
        "lambda_entropy": mejor.params["lambda_entropy"],
        "n_epochs":       mejor.params["n_epochs"],
        "n_steps_exp":    mejor.params["n_steps_exp"],
    }


def correr_semilla(cfg: Dict[str, Any], semilla: int) -> Dict[str, Any]:
    """Entrena 500k pasos guardando puntos de control y los evalúa todos."""
    dir_semilla = DIR_SALIDA / f"semilla_{semilla}"
    dir_semilla.mkdir(parents=True, exist_ok=True)
    ruta_json = dir_semilla / "resultado.json"
    if ruta_json.exists():
        print(f"[diag] semilla {semilla} REUTILIZADA", flush=True)
        return json.loads(ruta_json.read_text(encoding="utf-8"))

    hparams, pesos, _ = J.materializar_configuracion(
        cfg["lambda_cbf"], cfg["lambda_entropy"], cfg["n_epochs"], cfg["n_steps_exp"]
    )
    config_env = ConfigEntorno(n_agentes=J.N_AGENTES, arena_size=J.ARENA,
                               max_steps_ep=J.MAX_STEPS_EP, radio_com=J.COMM_RADIUS,
                               domain_rand=True)
    config_train = ConfigEntrenamiento(seed=semilla)

    env_train = construir_vec_env_entrenamiento(
        config_env=config_env, config_train=config_train, pesos_rew=pesos,
        n_envs=J.N_ENVS_ENTREN, seed=semilla,
    )
    # Conversión de unidades explícita (ver docstring).
    save_freq_llamadas = max(1, PASOS_CKPT // env_train.num_envs)
    print(f"[diag] semilla {semilla}: num_envs={env_train.num_envs} → "
          f"save_freq={save_freq_llamadas} llamadas = {PASOS_CKPT} pasos", flush=True)

    modelo = construir_modelo_ppo(env=env_train, hparams=hparams,
                                  config_train=config_train, dir_tensorboard=None,
                                  seed=semilla, verbose=0)
    cb = CheckpointCallback(save_freq=save_freq_llamadas,
                            save_path=str(dir_semilla / "checkpoints"),
                            name_prefix="ppo_J")
    t_ini = time.time()
    modelo.learn(total_timesteps=PASOS_TOTAL, callback=cb, progress_bar=False)
    seg_entren = time.time() - t_ini
    env_train.close()

    # ── Evaluar cada punto de control con el protocolo único ───────────────
    pesos_dict = {"lambda_gradient": pesos.lambda_gradient,
                  "lambda_entropy":  pesos.lambda_entropy,
                  "lambda_ibrm":     pesos.lambda_ibrm,
                  "lambda_cbf":      pesos.lambda_cbf}
    puntos: List[Dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=J.N_TRABAJADORES_EVAL,
                             initializer=J._iniciar_trabajador_eval,
                             initargs=(pesos_dict,)) as pool:
        for ruta in sorted((dir_semilla / "checkpoints").glob("*.zip")):
            pasos = int(ruta.stem.split("_")[-2])
            res = J.evaluar_modelo_en_paralelo(
                ruta, pool, J.N_EPS_FINAL, offset=J.OFFSET_SEMILLAS_FINAL)
            ag = res["agregados"]
            puntos.append({
                "pasos":      pasos,
                "cobertura":  ag["cobertura_aoi_final"]["media"],
                "std":        ag["cobertura_aoi_final"]["std"],
                "colisiones": ag["n_colisiones"]["media"],
            })
            print(f"[diag] semilla {semilla} — {pasos:6d}: "
                  f"cob={puntos[-1]['cobertura']:.8f}  col={puntos[-1]['colisiones']:.3f}",
                  flush=True)

    puntos.sort(key=lambda p: p["pasos"])
    resultado = {"semilla": semilla, "config": cfg, "puntos": puntos,
                 "segundos_entrenamiento": seg_entren}
    ruta_json.write_text(json.dumps(resultado, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    return resultado


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--semilla", type=int, default=None)
    args = parser.parse_args()

    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    cfg = cargar_mejor_configuracion()
    print(f"[diag] mejor configuración (prueba {cfg['prueba']}, "
          f"valor {cfg['valor']:.8f}):", flush=True)
    print(f"       λ_cbf={cfg['lambda_cbf']:.4f}  λ_ent={cfg['lambda_entropy']:.4f}  "
          f"n_epochs={cfg['n_epochs']}  n_steps={2**cfg['n_steps_exp']}", flush=True)

    semillas = (args.semilla,) if args.semilla else SEMILLAS
    resultados = [correr_semilla(cfg, s) for s in semillas]

    if len(resultados) == len(SEMILLAS):
        (DIR_SALIDA / "resumen.json").write_text(
            json.dumps({"config": cfg, "semillas": resultados}, indent=2,
                       ensure_ascii=False), encoding="utf-8")
        print("\nCURVA DE PUNTOS DE CONTROL (media de 3 semillas)")
        for i, p in enumerate(resultados[0]["puntos"]):
            cobs = [r["puntos"][i]["cobertura"] for r in resultados]
            cols = [r["puntos"][i]["colisiones"] for r in resultados]
            print(f"  {p['pasos']:6d}:  cob = {np.mean(cobs):.8f} ± {np.std(cobs, ddof=1):.8f}"
                  f"   col = {np.mean(cols):.3f}")


if __name__ == "__main__":
    main()
