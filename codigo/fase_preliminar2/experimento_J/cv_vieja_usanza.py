"""
cv_vieja_usanza.py — CV entre semillas con el protocolo de `verificacion_seeds`.

El CV que reporta el Experimento J (0.0126 para la prueba 7) evalúa las TRES
semillas sobre el MISMO conjunto de episodios: mide variabilidad de
entrenamiento pura. `verificacion_seeds` evaluó cada semilla sobre SU PROPIO
conjunto (`seed·10000+i`), de modo que su CV mezcla variabilidad de
entrenamiento con variabilidad de episodios.

Este script recalcula el CV de la mejor configuración del Exp J a la vieja
usanza, sobre los MISMOS modelos ya entrenados, para separar ambas
contribuciones sin reentrenar nada.

Truco: `evaluar_modelo_en_paralelo` construye las semillas de episodio como
`SEMILLA_EPISODIOS·10000 + offset + i` con `SEMILLA_EPISODIOS = 42`. Pasando
`offset = (semilla − 42)·10000` se obtiene exactamente `semilla·10000 + i`, que
es el conjunto que usó `verificacion_seeds`.
"""
from __future__ import annotations
import json, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np

DIR_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR_BASE))
import estudio_J as J

CFG_MEJOR = "cfg_eb1d01e59b"          # prueba 7
SEMILLAS  = (42, 123, 777)
N_EPS     = 30

def main() -> None:
    dir_cfg = DIR_BASE / "resultados" / "estudio" / CFG_MEJOR
    barridos = json.loads((dir_cfg / "config_barridos.json").read_text(encoding="utf-8"))
    _, pesos, _ = J.materializar_configuracion(
        barridos["lambda_cbf"], barridos["lambda_entropy"],
        barridos["n_epochs"], barridos["n_steps_exp"])
    pesos_dict = {"lambda_gradient": pesos.lambda_gradient,
                  "lambda_entropy":  pesos.lambda_entropy,
                  "lambda_ibrm":     pesos.lambda_ibrm,
                  "lambda_cbf":      pesos.lambda_cbf}

    mismos, propios = [], []
    with ProcessPoolExecutor(max_workers=J.N_TRABAJADORES_EVAL,
                             initializer=J._iniciar_trabajador_eval,
                             initargs=(pesos_dict,)) as pool:
        for s in SEMILLAS:
            ruta = dir_cfg / f"semilla_{s}" / "mejor_punto_control.zip"
            # (a) mismo conjunto para las tres — protocolo del Exp J
            a = J.evaluar_modelo_en_paralelo(ruta, pool, N_EPS,
                                             offset=J.OFFSET_SEMILLAS_FINAL)
            # (b) conjunto propio de cada semilla — protocolo viejo
            b = J.evaluar_modelo_en_paralelo(ruta, pool, N_EPS,
                                             offset=(s - J.SEMILLA_EPISODIOS) * 10_000)
            mismos.append(a["agregados"]["cobertura_aoi_final"]["media"])
            propios.append(b["agregados"]["cobertura_aoi_final"]["media"])
            print(f"semilla {s:3d}:  mismos episodios {mismos[-1]:.8f}   "
                  f"episodios propios {propios[-1]:.8f}", flush=True)

    salida = {}
    for nombre, vals in (("mismos_episodios_expJ", mismos),
                         ("episodios_propios_vieja_usanza", propios)):
        v = np.array(vals)
        salida[nombre] = {"coberturas": list(map(float, v)),
                          "media": float(v.mean()),
                          "std":   float(v.std(ddof=1)),
                          "cv":    float(v.std(ddof=1) / v.mean())}
        print(f"\n{nombre}\n  media {v.mean():.8f}  σ {v.std(ddof=1):.8f}  "
              f"CV {v.std(ddof=1)/v.mean():.6f}")

    # Referencias del Trial 13 bajo los dos protocolos viejos documentados
    for nombre, vals in (("trial13_reproducibilidad", [0.5546, 0.5269, 0.4509]),
                         ("trial13_multimetrica",     [0.698, 0.679, 0.532])):
        v = np.array(vals)
        salida[nombre] = {"coberturas": vals, "media": float(v.mean()),
                          "std": float(v.std(ddof=1)),
                          "cv": float(v.std(ddof=1)/v.mean())}
        print(f"{nombre}: CV {v.std(ddof=1)/v.mean():.6f}")

    ruta = DIR_BASE / "resultados" / "analisis" / "cv_vieja_usanza.json"
    ruta.write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n→ {ruta}")

if __name__ == "__main__":
    main()
