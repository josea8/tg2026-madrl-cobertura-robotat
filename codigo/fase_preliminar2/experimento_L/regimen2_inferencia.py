"""
regimen2_inferencia.py — Experimento L, régimen 2: INFERENCIA.

Mide el tiempo por decisión de `modelo_PRIMERO` (la política de referencia,
la misma del Exp E) con el protocolo del Exp E, en una condición de
dispositivo, barriendo el tamaño del enjambre n ∈ {5, 10, 20, 50, 100}.

Dos bloques:

  A) PROTOCOLO (comparable con el Exp E). Episodios reales del entorno del
     protocolo único, cronómetro `perf_counter` alrededor de la llamada de
     decisión completa (apilar observaciones + `predict` determinista +
     desempaquetar). Diseño por n:
        n=5   : 100 episodios × 500 pasos  — réplica exacta del Exp E; además
                verifica el control (cobertura oficial 0.681291) en cada
                condición, o sea, si el dispositivo cambia las decisiones.
        n=10  :  20 episodios × 500 pasos
        n=20  :  10 episodios × 500 pasos
        n=50  :   4 episodios × 200 pasos  (entorno ~0.4 s/paso)
        n=100 :   2 episodios × 100 pasos  (entorno ~1.2 s/paso)
     Para n ≥ 50 el sorteo de poses cae al fallback de grilla y los episodios
     se truncan: la cobertura de esas filas NO es del protocolo y queda
     marcada (`episodio_completo=False`). La latencia por decisión sí es
     válida: depende del lote `(n, 24)`, no del estado del entorno.

  B) SINTÉTICO (complementario, NO protocolo). `predict` sobre lotes
     `(n, 24)` de observaciones aleatorias fijas, n hasta 5000, para ubicar el
     punto de cruce CPU/GPU si no aparece en el rango protocolar. Se reporta
     aparte y etiquetado.

Uso (una condición por invocación, nunca dos a la vez):
  venv_lab4 : python regimen2_inferencia.py --condicion gpu         --dispositivo cuda
  venv_lab4 : python regimen2_inferencia.py --condicion cpu_control --dispositivo cpu
  tesis     : python regimen2_inferencia.py --condicion referencia  --dispositivo cpu

Autor: José — Tesis Mecatrónica UVG
"""

from __future__ import annotations

import argparse
import json
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import torch
from stable_baselines3 import PPO

from comun_L import (
    COBERTURA_OFICIAL_MADRL,
    DIR_RESULTADOS,
    MonitorCargaCPU,
    RUTA_MODELO_PRIMERO,
    SEMILLA,
    TOL_CONTROL,
    construir_env_protocolo,
    correr_episodio_cronometrado,
    declarar_hardware,
    escribir_csv,
    respaldar_si_existe,
    resumen_estadistico,
    validar_condicion,
)

# (episodios, pasos por episodio) por tamaño de enjambre — bloque A
DISENO_PROTOCOLO: Dict[int, Tuple[int, int]] = {
    5:   (100, 500),
    10:  (20, 500),
    20:  (10, 500),
    50:  (4, 200),
    100: (2, 100),
}
# Bloque B
N_SINTETICO: Tuple[int, ...] = (5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000)
REPETICIONES_SINTETICO: int = 300
CALENTAMIENTO: int = 200
D_OBS: int = 24


def calentar(modelo, es_cuda: bool) -> None:
    """Descarta la primera tanda de llamadas (carga de kernels, cachés)."""
    obs = np.zeros((5, D_OBS), dtype=np.float32)
    for _ in range(CALENTAMIENTO):
        modelo.predict(obs, deterministic=True)
    if es_cuda:
        torch.cuda.synchronize()


def bloque_protocolo(modelo, condicion: str, es_cuda: bool, dir_salida: Path) -> List[Dict[str, Any]]:
    """Bloque A: episodios reales, cronómetro del Exp E, barrido de n."""
    filas: List[Dict[str, Any]] = []
    for n, (n_eps, max_pasos) in DISENO_PROTOCOLO.items():
        env = construir_env_protocolo(n, seed=SEMILLA)
        tiempos_todos: List[np.ndarray] = []
        t_bloque = time.perf_counter()
        for i in range(n_eps):
            with warnings.catch_warnings(record=True) as avisos:
                warnings.simplefilter("always")
                r = correr_episodio_cronometrado(
                    modelo, env, seed_ep=SEMILLA * 10_000 + i,
                    max_pasos=None if max_pasos >= 500 else max_pasos,
                    sincronizar_cuda=es_cuda,
                )
                fallback = any("fallback" in str(a.message) for a in avisos)
            tiempos_todos.append(r.pop("tiempos_ms"))
            r.update({"condicion": condicion, "n_agentes": n, "episodio": i,
                      "seed_ep": SEMILLA * 10_000 + i, "fallback_grilla": fallback})
            filas.append(r)
        seg = time.perf_counter() - t_bloque
        t = np.concatenate(tiempos_todos)
        np.save(dir_salida / f"tiempos_decision_n{n}.npy", t)
        print(f"[L2A] n={n:3d}  {len(t):6d} decisiones  media={np.mean(t):.4f} ms  "
              f"mediana={np.median(t):.4f}  p95={np.percentile(t, 95):.4f}  "
              f"({seg:.0f} s de pared)", flush=True)
    return filas


def bloque_sintetico(modelo, condicion: str, es_cuda: bool) -> List[Dict[str, Any]]:
    """Bloque B: lotes sintéticos `(n, 24)`, para ubicar el cruce."""
    rng = np.random.default_rng(SEMILLA)
    filas: List[Dict[str, Any]] = []
    for n in N_SINTETICO:
        obs = rng.standard_normal((n, D_OBS)).astype(np.float32)
        for _ in range(20):
            modelo.predict(obs, deterministic=True)
        if es_cuda:
            torch.cuda.synchronize()
        reps = REPETICIONES_SINTETICO if n <= 1000 else 100
        tiempos = np.empty(reps)
        for k in range(reps):
            t0 = time.perf_counter()
            modelo.predict(obs, deterministic=True)
            if es_cuda:
                torch.cuda.synchronize()
            tiempos[k] = (time.perf_counter() - t0) * 1000.0
        res = resumen_estadistico(tiempos)
        filas.append({"condicion": condicion, "n_agentes": n, "repeticiones": reps,
                      "t_decision_ms_media": res["media"], "t_decision_ms_std": res["std"],
                      "t_decision_ms_mediana": res["mediana"],
                      "t_decision_ms_p95": float(np.percentile(tiempos, 95)),
                      "t_decision_ms_min": res["min"]})
        print(f"[L2B] n={n:5d}  media={res['media']:.4f} ms  mediana={res['mediana']:.4f}", flush=True)
    return filas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--condicion", required=True, choices=("gpu", "cpu_control", "referencia"))
    parser.add_argument("--dispositivo", required=True, choices=("cpu", "cuda"))
    parser.add_argument("--sin_sintetico", action="store_true")
    parser.add_argument("--sufijo", default="",
                        help="repetición: escribe en resultados/regimen2/<condicion>_<sufijo>")
    parser.add_argument("--rapido", action="store_true",
                        help="prueba de humo: 1 episodio × 20 pasos por n y 30 repeticiones sintéticas")
    args = parser.parse_args()
    if args.rapido:
        for n in list(DISENO_PROTOCOLO):
            DISENO_PROTOCOLO[n] = (1, 20)
        globals()["REPETICIONES_SINTETICO"] = 30
        globals()["N_SINTETICO"] = (5, 100, 5000)

    validar_condicion(args.condicion, args.dispositivo)
    es_cuda = args.dispositivo == "cuda"

    dir_salida = DIR_RESULTADOS / "regimen2" / (args.condicion + (f"_{args.sufijo}" if args.sufijo else ""))
    respaldo = respaldar_si_existe(dir_salida)
    if respaldo is not None:
        print(f"[L2] resultados previos respaldados en {respaldo}", flush=True)
    dir_salida.mkdir(parents=True, exist_ok=True)

    hardware = declarar_hardware()
    print(f"[L2] condición={args.condicion} dispositivo={args.dispositivo} "
          f"torch={hardware['torch']} hilos={hardware['torch_hilos']} "
          f"cpu_carga={hardware['cpu']['carga_pct_al_arrancar']}%", flush=True)

    modelo = PPO.load(str(RUTA_MODELO_PRIMERO), device=args.dispositivo)
    dispositivo_real = str(modelo.policy.device)
    print(f"[L2] modelo_PRIMERO en {dispositivo_real}", flush=True)
    calentar(modelo, es_cuda)

    t_ini = time.perf_counter()
    monitor = MonitorCargaCPU(intervalo_s=2.0)
    monitor.iniciar()
    filas_A = bloque_protocolo(modelo, args.condicion, es_cuda, dir_salida)
    escribir_csv(
        dir_salida / "protocolo_episodios.csv", filas_A,
        ("condicion", "n_agentes", "episodio", "seed_ep", "cobertura_aoi_final",
         "colisiones_015", "colisiones_022", "pasos", "episodio_completo", "fallback_grilla",
         "t_decision_ms_media", "t_decision_ms_std", "t_decision_ms_mediana",
         "t_decision_ms_p95", "t_decision_ms_min"),
    )

    # Verificación de control: n=5, 100 episodios completos → cobertura oficial
    cob5 = np.array([f["cobertura_aoi_final"] for f in filas_A if f["n_agentes"] == 5])
    media5 = float(np.mean(cob5))
    delta5 = media5 - COBERTURA_OFICIAL_MADRL
    reproduce = abs(round(media5, 6) - COBERTURA_OFICIAL_MADRL) < TOL_CONTROL
    print(f"[L2] CONTROL n=5: cobertura {media5:.8f}  Δ={delta5:+.8f}  "
          f"{'REPRODUCE' if reproduce else 'NO reproduce a 6 decimales'}", flush=True)

    filas_B: List[Dict[str, Any]] = []
    if not args.sin_sintetico:
        filas_B = bloque_sintetico(modelo, args.condicion, es_cuda)
        escribir_csv(
            dir_salida / "sintetico.csv", filas_B,
            ("condicion", "n_agentes", "repeticiones", "t_decision_ms_media",
             "t_decision_ms_std", "t_decision_ms_mediana", "t_decision_ms_p95", "t_decision_ms_min"),
        )

    resumen_por_n: Dict[str, Any] = {}
    for n in DISENO_PROTOCOLO:
        t = np.load(dir_salida / f"tiempos_decision_n{n}.npy")
        eps = [f for f in filas_A if f["n_agentes"] == n]
        resumen_por_n[str(n)] = {
            "n_decisiones": int(len(t)),
            "n_episodios": len(eps),
            "pasos_por_episodio": eps[0]["pasos"],
            "episodios_completos": all(f["episodio_completo"] for f in eps),
            "fallback_grilla": any(f["fallback_grilla"] for f in eps),
            "t_decision_ms": {**resumen_estadistico(t), "p95": float(np.percentile(t, 95))},
            "t_decision_ms_media_de_medias_por_episodio": float(np.mean([f["t_decision_ms_media"] for f in eps])),
            "cobertura_aoi_final": resumen_estadistico(np.array([f["cobertura_aoi_final"] for f in eps])),
            "colisiones_015": resumen_estadistico(np.array([f["colisiones_015"] for f in eps], dtype=float)),
        }

    carga = monitor.detener()
    print(f"[L2] carga de CPU del sistema durante la corrida: media {carga['ocupacion_sistema_pct_media']:.1f} % "
          f"(p90 {carga['ocupacion_sistema_pct_p90']:.1f} %)", flush=True)
    reporte = {
        "experimento": "L", "regimen": 2,
        "modo_rapido_NO_VALIDO": args.rapido,
        "carga_cpu_durante_corrida": carga,
        "condicion": args.condicion, "repeticion": args.sufijo or "1",
        "dispositivo_pedido": args.dispositivo,
        "dispositivo_real": dispositivo_real,
        "modelo": str(RUTA_MODELO_PRIMERO),
        "hardware": hardware,
        "diseno_protocolo": {str(k): {"episodios": v[0], "pasos": v[1]} for k, v in DISENO_PROTOCOLO.items()},
        "control_n5": {"cobertura_media_100eps": media5, "oficial": COBERTURA_OFICIAL_MADRL,
                       "delta": delta5, "reproduce_6_decimales": reproduce,
                       "colisiones_015_media": float(np.mean([f["colisiones_015"] for f in filas_A if f["n_agentes"] == 5]))},
        "protocolo_por_n": resumen_por_n,
        "sintetico": filas_B,
        "duracion_total_s": time.perf_counter() - t_ini,
    }
    ruta = dir_salida / "reporte.json"
    ruta.write_bytes(json.dumps(reporte, indent=2, ensure_ascii=False).encode("utf-8"))
    print(f"[L2] reporte -> {ruta}", flush=True)


if __name__ == "__main__":
    main()
