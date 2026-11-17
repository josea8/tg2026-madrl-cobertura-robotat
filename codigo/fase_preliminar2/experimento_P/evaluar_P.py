"""
evaluar_P.py — Evaluación auxiliar de los modelos del Experimento P.

El JSON del trabajador de `estudio_J` sólo trae el punto RETENIDO sobre el
conjunto final (30 episodios, offset 1000). Aquí se evalúan, con el MISMO
evaluador paralelo de la copia de `estudio_J.py`:

  punto retenido  (`mejor_punto_control.zip`)   × {conjunto nuevo, conjunto final}
  paso fijo 200k  (`_punto_control_actual.zip`) × {conjunto nuevo, conjunto final}

Conjunto nuevo: 100 episodios con semillas 42·10000 + 2000 + i (422000–422099),
disjunto de la retención (offset 0, 20 eps) y del conjunto final (offset 1000,
30 eps), que fue el objetivo de TPE en el Exp J.

Verificaciones: el `_punto_control_actual.zip` debe declarar
`num_timesteps = 200000`, y el retenido sobre el conjunto final debe coincidir
EXACTAMENTE con `cobertura_final` del JSON del trabajador (misma función,
mismos episodios). Si algo no coincide, se aborta.

Se guarda el detalle POR EPISODIO, con precisión completa. Reanudable: un
modelo ya evaluado no se reevalúa.

Uso:  python3 -B evaluar_P.py [--humo]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from typing import Any, Dict

import comun_P as C

J = C.importar_estudio_j_copia()   # a nivel de módulo, por spawn

EVALUACIONES = (
    ("retenido", "mejor_punto_control.zip",   "nuevo", C.CONJUNTO_NUEVO),
    ("retenido", "mejor_punto_control.zip",   "final", C.CONJUNTO_FINAL),
    ("fijo200k", "_punto_control_actual.zip", "nuevo", C.CONJUNTO_NUEVO),
    ("fijo200k", "_punto_control_actual.zip", "final", C.CONJUNTO_FINAL),
)


def pesos_de_brazo(brazo: str) -> Dict[str, float]:
    cfg = json.loads(C.CONFIGS[brazo].read_text(encoding="utf-8"))
    _, pesos, _ = J.materializar_configuracion(
        cfg["lambda_cbf"], cfg["lambda_entropy"], cfg["n_epochs"], cfg["n_steps_exp"])
    return {"lambda_gradient": pesos.lambda_gradient, "lambda_entropy": pesos.lambda_entropy,
            "lambda_ibrm": pesos.lambda_ibrm, "lambda_cbf": pesos.lambda_cbf}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--humo", action="store_true")
    args = parser.parse_args()
    base = C.dir_base(args.humo)
    semillas = C.SEMILLAS[:1] if args.humo else C.SEMILLAS[:C.N_POR_BRAZO]

    for brazo in C.BRAZOS:
        pendientes = [s for s in semillas
                      if (base / brazo / f"semilla_{s}" / "resultado_semilla.json").exists()
                      and not (base / "evaluacion" / f"{brazo}_s{s}.json").exists()]
        if not pendientes:
            continue
        with ProcessPoolExecutor(max_workers=C.N_TRABAJADORES_EVAL,
                                 initializer=J._iniciar_trabajador_eval,
                                 initargs=(pesos_de_brazo(brazo),)) as pool:
            for s in pendientes:
                dir_s = base / brazo / f"semilla_{s}"
                trabajador = json.loads((dir_s / "resultado_semilla.json").read_text(encoding="utf-8"))
                paso_actual = C.num_timesteps_zip(dir_s / "_punto_control_actual.zip")
                if not args.humo and paso_actual != C.PASO_FIJO:
                    print(f"ABORTADO: {dir_s}/_punto_control_actual.zip tiene "
                          f"num_timesteps={paso_actual}, no {C.PASO_FIJO}")
                    return 1
                salida: Dict[str, Any] = {
                    "brazo": brazo, "semilla": s, "fecha": datetime.now().isoformat(timespec="seconds"),
                    "paso_retenido": trabajador["paso_retenido"],
                    "num_timesteps_retenido": C.num_timesteps_zip(dir_s / "mejor_punto_control.zip"),
                    "num_timesteps_fijo": paso_actual,
                    "sha256_policy": {
                        "retenido": C.sha256_miembro_zip(dir_s / "mejor_punto_control.zip", "policy.pth"),
                        "fijo200k": C.sha256_miembro_zip(dir_s / "_punto_control_actual.zip", "policy.pth"),
                    },
                    "evaluaciones": {},
                }
                t0 = time.time()
                for punto, archivo, conjunto, (offset, n) in EVALUACIONES:
                    res = J.evaluar_modelo_en_paralelo(dir_s / archivo, pool, n, offset=offset)
                    salida["evaluaciones"][f"{punto}@{conjunto}"] = {
                        "offset": offset, "n_episodios": n,
                        "agregados": res["agregados"], "episodios": res["episodios"],
                    }
                salida["segundos"] = time.time() - t0
                # Coherencia con el trabajador: misma función, mismos episodios.
                cob_ret_final = salida["evaluaciones"]["retenido@final"]["agregados"]["cobertura_aoi_final"]["media"]
                if cob_ret_final != trabajador["cobertura_final"]:
                    print(f"ABORTADO: {brazo} s{s}: retenido@final {cob_ret_final!r} "
                          f"!= cobertura_final del trabajador {trabajador['cobertura_final']!r}")
                    return 1
                C.escribir_json(base / "evaluacion" / f"{brazo}_s{s}.json", salida)
                print(f"{brazo} s{s}: retenido@nuevo "
                      f"{salida['evaluaciones']['retenido@nuevo']['agregados']['cobertura_aoi_final']['media']:.8f} "
                      f"({salida['segundos']:.0f} s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
