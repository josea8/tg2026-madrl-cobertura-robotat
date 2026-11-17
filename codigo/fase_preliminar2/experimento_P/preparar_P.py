"""
preparar_P.py — Prepara la copia propia del Experimento P y su manifiesto.

Qué hace, en orden:

1. Copia byte a byte los cuatro archivos del cierre de dependencias de
   `estudio_J.py` a `lib/` (y `lib/j/`) y verifica que cada copia tenga el
   MISMO sha256 que su original. Si una copia ya existe y difiere, aborta sin
   tocarla: nunca sobrescribe.
2. Escribe las dos configuraciones de brazo:
   - `config/ganadora.json`: copia byte a byte de
     `experimento_J/resultados/estudio/cfg_eb1d01e59b/config_barridos.json`.
   - `config/trial13.json`: los cuatro valores barridos del Trial 13, leídos
     de `RESULTADO_PRIMERO/hiperparametros.json`. Se verifica que
     `materializar_configuracion` reconstruya EXACTAMENTE los hiperparámetros
     y pesos de ese archivo.
3. Escribe `manifiesto_P.json`: sha256 de originales, copias, configuraciones
   y scripts de P; versiones del intérprete y de los paquetes; diseño fijado.

No entrena ni evalúa nada. Se corre una vez, antes de `correr_P.py`:

    python3 -B preparar_P.py
"""
from __future__ import annotations

import json
import math
import os
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import comun_P as C


def copiar_verificado(origen: Path, destino: Path) -> Dict[str, str]:
    """Copia `origen` → `destino` en bytes y verifica sha256. Nunca sobrescribe."""
    h_origen = C.sha256_archivo(origen)
    if destino.exists():
        h_destino = C.sha256_archivo(destino)
        if h_destino != h_origen:
            raise SystemExit(f"ABORTADO: {destino} existe y difiere de {origen}")
    else:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(origen.read_bytes())
        h_destino = C.sha256_archivo(destino)
    if h_destino != h_origen:
        raise SystemExit(f"ABORTADO: la copia {destino} no es idéntica a {origen}")
    return {"original": str(origen), "copia": str(destino), "sha256": h_origen}


def config_trial13() -> Dict[str, Any]:
    """Los cuatro valores barridos del Trial 13, desde hiperparametros.json."""
    datos = json.loads(C.RUTA_HPARAMS_T13.read_text(encoding="utf-8"))
    n_steps = int(datos["hparams"]["n_steps"])
    n_steps_exp = int(round(math.log2(n_steps)))
    if 2 ** n_steps_exp != n_steps:
        raise SystemExit(f"ABORTADO: n_steps={n_steps} no es potencia de 2")
    return {
        "lambda_cbf":     datos["pesos_recompensa"]["lambda_cbf"],
        "lambda_entropy": datos["pesos_recompensa"]["lambda_entropy"],
        "n_epochs":       int(datos["hparams"]["n_epochs"]),
        "n_steps_exp":    n_steps_exp,
        "n_steps":        n_steps,
    }


def verificar_trial13(J) -> None:
    """`materializar_configuracion(T13)` debe dar EXACTAMENTE hiperparametros.json."""
    datos = json.loads(C.RUTA_HPARAMS_T13.read_text(encoding="utf-8"))
    cfg = json.loads(C.CONFIGS["trial13"].read_text(encoding="utf-8"))
    hparams, pesos, _ = J.materializar_configuracion(
        cfg["lambda_cbf"], cfg["lambda_entropy"], cfg["n_epochs"], cfg["n_steps_exp"])
    for clave, valor in datos["hparams"].items():
        if getattr(hparams, clave) != valor:
            raise SystemExit(f"ABORTADO: T13 {clave}: {getattr(hparams, clave)!r} != {valor!r}")
    for clave, valor in datos["pesos_recompensa"].items():
        if getattr(pesos, clave) != valor:
            raise SystemExit(f"ABORTADO: T13 {clave}: {getattr(pesos, clave)!r} != {valor!r}")


def versiones() -> Dict[str, str]:
    import numpy, torch, stable_baselines3, supersuit, pettingzoo, gymnasium, optuna, scipy
    return {
        "python": sys.version.split()[0], "ejecutable": sys.executable,
        "so": f"{platform.system()} {platform.release()} ({platform.version()})",
        "torch": torch.__version__, "stable_baselines3": stable_baselines3.__version__,
        "supersuit": supersuit.__version__, "pettingzoo": pettingzoo.__version__,
        "gymnasium": gymnasium.__version__, "numpy": numpy.__version__,
        "optuna": optuna.__version__, "scipy": scipy.__version__,
    }


def main() -> None:
    copias = [copiar_verificado(orig, C.RAIZ_P / dest) for dest, orig in C.ORIGINALES.items()]

    # Configuración de la ganadora: copia byte a byte del config del Exp J.
    copias.append(copiar_verificado(C.RUTA_CFG_GANADORA_J, C.CONFIGS["ganadora"]))

    # Configuración del Trial 13: construida desde hiperparametros.json.
    cfg_t13 = config_trial13()
    texto_t13 = json.dumps(cfg_t13, indent=2) + "\n"
    if C.CONFIGS["trial13"].exists():
        if C.CONFIGS["trial13"].read_bytes() != texto_t13.encode("utf-8"):
            raise SystemExit("ABORTADO: config/trial13.json existe y difiere")
    else:
        C.escribir_texto(C.CONFIGS["trial13"], texto_t13)

    J = C.importar_estudio_j_copia()
    verificar_trial13(J)
    cfg_gan = json.loads(C.CONFIGS["ganadora"].read_text(encoding="utf-8"))
    for cfg in (cfg_gan, cfg_t13):
        for clave in ("n_epochs", "n_steps_exp"):
            if not isinstance(cfg[clave], int):
                raise SystemExit(f"ABORTADO: {clave} debe ser int en {cfg}")

    manifiesto = {
        "experimento": "P — confirmación de la ganadora del Exp J y del Trial 13",
        "preparado": datetime.now().isoformat(timespec="seconds"),
        "copias_propias": copias,
        "configs": {
            b: {"ruta": str(p), "sha256": C.sha256_archivo(p),
                "hash_estudio_J": J.clave_configuracion(json.loads(p.read_text(encoding="utf-8"))),
                "contenido": json.loads(p.read_text(encoding="utf-8"))}
            for b, p in C.CONFIGS.items()
        },
        "diseno": {
            "semillas": list(C.SEMILLAS), "n_por_brazo": C.N_POR_BRAZO,
            "brazos": list(C.BRAZOS),
            "conjunto_nuevo": {"offset": C.CONJUNTO_NUEVO[0], "n": C.CONJUNTO_NUEVO[1]},
            "conjunto_final": {"offset": C.CONJUNTO_FINAL[0], "n": C.CONJUNTO_FINAL[1]},
            "paso_fijo": C.PASO_FIJO, "semilla_control": C.SEMILLA_CONTROL,
            "presupuesto_pasos": J.PRESUPUESTO_PASOS, "frecuencia_eval": J.FRECUENCIA_EVAL_TS,
        },
        "versiones": versiones(),
        # Se registran, no se cambian: el Exp J corrió con el entorno de la sesión.
        "variables_hilos": {k: os.environ.get(k) for k in
                            ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                             "PYTHONHASHSEED", "CUDA_VISIBLE_DEVICES")},
        "scripts_P": {p.name: C.sha256_archivo(p) for p in sorted(C.RAIZ_P.glob("*.py"))},
        "preregistro_sha256": (C.sha256_archivo(C.RAIZ_P / "PREREGISTRO_P.md")
                               if (C.RAIZ_P / "PREREGISTRO_P.md").exists() else None),
    }
    if J.PRESUPUESTO_PASOS != 200_000 or J.FRECUENCIA_EVAL_TS != 20_000:
        raise SystemExit("ABORTADO: hay variables EXPJ_* definidas en esta sesión")
    C.escribir_json(C.RUTA_MANIFIESTO, manifiesto)
    print(json.dumps({"copias": [(c["copia"], c["sha256"][:16]) for c in copias],
                      "configs": {b: v["hash_estudio_J"] for b, v in manifiesto["configs"].items()}},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
