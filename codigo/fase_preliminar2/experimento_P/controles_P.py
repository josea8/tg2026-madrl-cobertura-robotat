"""
controles_P.py — Verificaciones de control del Experimento P, ANTES de las semillas nuevas.

Si cualquiera falla, el script termina con código 1 y `correr_P.py` se
detiene: no se ajusta nada (instrucción de Jose, 2026-09-24).

C1  `modelo_PRIMERO`, 100 episodios, semillas 42·10000+i, por el evaluador
    paralelo de la COPIA de `estudio_J.py`. Debe reproducir la cifra oficial
    0.6812908187508583 a seis decimales (regla de CLAUDE.md §5) y, además, los
    100 episodios uno a uno contra `metricas_100eps.json`.

C3  Heurística NN ("go to nearest target") sobre el entorno ORIGINAL (la copia
    de `lib/`, idéntica por sha256), 100 episodios, pesos del Trial 13.
    Debe reproducir 0.25434854030609133 a seis decimales y episodio a
    episodio. La función se copia TEXTUALMENTE de
    `consolidar_resultado_primero.py` (líneas 122-124 y 163-185) porque ese
    módulo no puede importarse: al importarlo trunca
    `RESULTADO_PRIMERO/consolidacion.log`. El texto copiado se verifica contra
    el original por sha256 antes de usarlo.

C2  Semilla 42 de la ganadora, reentrenada en `resultados/control/ganadora_s42`
    con el modo trabajador de la copia. Debe reproducir BIT A BIT la corrida
    del Exp J (`cfg_eb1d01e59b/semilla_42`): todas las claves de
    `resultado_semilla.json` salvo los tiempos, y el sha256 de `policy.pth` y
    `policy.optimizer.pth` en `mejor_punto_control.zip` (140k) y en
    `_punto_control_actual.zip` (200k). Es además el primer uso real del
    `train.py` corregido el 2026-09-08.

Uso:  python3 -B controles_P.py            (corre C1, C3 y C2)
      python3 -B controles_P.py --humo     (sólo fontanería; no es control)
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

import comun_P as C

# A nivel de módulo: con spawn, los hijos del pool re-importan este archivo y
# necesitan resolver `estudio_J` (la copia) para el inicializador.
J = C.importar_estudio_j_copia()
from concentration_dynamics import V_MAX, OMEGA_MAX  # noqa: E402  (copia de lib/)
from swarm_env_skeleton import make_env               # noqa: E402  (copia de lib/)

PESOS_T13: Dict[str, float] = {
    "lambda_gradient": 0.5622468083379316,
    "lambda_entropy":  1.1403296484190344,
    "lambda_ibrm":     0.48380314172632155,
    "lambda_cbf":      2.9655314099141474,
}


# ══════════════════════════════════════════════════════════════════════════════
#  Heurística NN — copia TEXTUAL de consolidar_resultado_primero.py
# ══════════════════════════════════════════════════════════════════════════════
# (inicio de la copia textual)
def envolver_angulo(theta: float) -> float:
    """Wrap a un ángulo a [-π, π]."""
    return (theta + math.pi) % (2.0 * math.pi) - math.pi
# (fin de la copia textual)


# (inicio de la copia textual)
def politica_heuristica_NN(env, obs_dict, rng, K_omega: float = 4.0):
    """
    Heurística "go to nearest target":
        - Para cada agente, busca el objetivo más cercano (Euclidean).
        - Calcula error angular wrap(θ_objetivo - θ_actual).
        - ω = clip(K_ω · err, ±OMEGA_MAX).
        - v = V_MAX · max(0, cos(err))  (sólo avanza cuando está alineado).
    """
    targets = env._field.posiciones_objetivos  # (H, 2)
    out = {}
    for a in obs_dict.keys():
        estado = env._estados[a]
        x, y, th = float(estado[0]), float(estado[1]), float(estado[2])
        diffs = targets - np.array([x, y])
        dists = np.linalg.norm(diffs, axis=1)
        idx_nn = int(np.argmin(dists))
        dx, dy = float(diffs[idx_nn, 0]), float(diffs[idx_nn, 1])
        th_obj = math.atan2(dy, dx)
        err    = envolver_angulo(th_obj - th)
        omega  = float(np.clip(K_omega * err, -OMEGA_MAX, OMEGA_MAX))
        v      = float(V_MAX * max(0.0, math.cos(err)))
        out[a] = np.array([v, omega], dtype=np.float32)
    return out
# (fin de la copia textual)


def _texto_funcion_original(nombre: str) -> str:
    """Extrae el texto de `def nombre` del original SIN importarlo (sólo lectura de texto)."""
    lineas = C.RUTA_CONSOLIDAR.read_text(encoding="utf-8").splitlines()
    ini = next(i for i, l in enumerate(lineas) if l.startswith(f"def {nombre}("))
    fin = ini + 1
    while fin < len(lineas) and (lineas[fin].startswith((" ", "\t")) or not lineas[fin].strip()):
        fin += 1
    while not lineas[fin - 1].strip():
        fin -= 1
    return "\n".join(lineas[ini:fin])


def verificar_copia_textual() -> Dict[str, str]:
    """El texto de las dos funciones copiadas debe ser idéntico al del original."""
    salida = {}
    for f in (envolver_angulo, politica_heuristica_NN):
        copia = inspect.getsource(f).rstrip("\n")
        original = _texto_funcion_original(f.__name__)
        h_c = hashlib.sha256(copia.encode("utf-8")).hexdigest()
        h_o = hashlib.sha256(original.encode("utf-8")).hexdigest()
        if h_c != h_o:
            raise SystemExit(f"C3 ABORTADO: la copia de {f.__name__} difiere del original")
        salida[f.__name__] = h_o
    return salida


def episodio_heuristica(env, seed_ep: int) -> float:
    """Réplica del bucle de `evaluar_episodio` de consolidar (sólo la cobertura final)."""
    obs_dict, _ = env.reset(seed=seed_ep)
    cob_hist: List[float] = []
    done = False
    while not done:
        accion_dict = politica_heuristica_NN(env, obs_dict, None)
        obs_dict, _, term, trunc, _ = env.step(accion_dict)
        cob_hist.append(1.0 - float(np.mean(env._field._grid_aoi)))
        done = all(trunc.values()) or all(term.values())
    return float(cob_hist[-1]) if cob_hist else 0.0


# ══════════════════════════════════════════════════════════════════════════════
#  C1, C3, C2
# ══════════════════════════════════════════════════════════════════════════════

def control_c1(oficial: Dict[str, Any]) -> Dict[str, Any]:
    with ProcessPoolExecutor(max_workers=C.N_TRABAJADORES_EVAL,
                             initializer=J._iniciar_trabajador_eval,
                             initargs=(PESOS_T13,)) as pool:
        res = J.evaluar_modelo_en_paralelo(C.RUTA_MODELO_PRIMERO, pool, 100, offset=0)
    media = res["agregados"]["cobertura_aoi_final"]["media"]
    ref_eps = [e["cobertura_aoi_final"] for e in oficial["madrl"]["episodios"]]
    obt_eps = [e["cobertura_aoi_final"] for e in res["episodios"]]
    difs = [abs(a - b) for a, b in zip(obt_eps, ref_eps)]
    return {
        "cobertura": media, "oficial": C.COB_OFICIAL_MADRL, "dif": media - C.COB_OFICIAL_MADRL,
        "seis_decimales": round(media, 6) == round(C.COB_OFICIAL_MADRL, 6),
        "episodios_identicos": obt_eps == ref_eps, "max_dif_episodio": max(difs),
        "aprobado": round(media, 6) == round(C.COB_OFICIAL_MADRL, 6),
    }


def control_c3(oficial: Dict[str, Any]) -> Dict[str, Any]:
    hashes = verificar_copia_textual()
    env = make_env(n_agents=J.N_AGENTES, arena_size=J.ARENA, max_steps=J.MAX_STEPS_EP,
                   comm_radius=J.COMM_RADIUS, reward_weights=PESOS_T13,
                   domain_rand=False, seed=42)
    obt_eps = [episodio_heuristica(env, 42 * 10_000 + i) for i in range(100)]
    media = float(np.mean(np.array(obt_eps, dtype=np.float64)))
    ref_eps = [e["cobertura_aoi_final"] for e in oficial["heuristica"]["episodios"]]
    difs = [abs(a - b) for a, b in zip(obt_eps, ref_eps)]
    return {
        "sha256_funciones_copiadas": hashes,
        "cobertura": media, "oficial": C.COB_OFICIAL_NN, "dif": media - C.COB_OFICIAL_NN,
        "seis_decimales": round(media, 6) == round(C.COB_OFICIAL_NN, 6),
        "episodios_identicos": obt_eps == ref_eps, "max_dif_episodio": max(difs),
        "aprobado": round(media, 6) == round(C.COB_OFICIAL_NN, 6),
    }


def _comparar_json(obtenido: Dict[str, Any], referencia: Dict[str, Any]) -> List[str]:
    """Diferencias exactas entre dos resultado_semilla.json, salvo los tiempos."""
    ignorar = {"segundos_total", "segundos_evaluando"}
    difs = []
    for clave in sorted(set(obtenido) | set(referencia)):
        if clave in ignorar:
            continue
        if obtenido.get(clave) != referencia.get(clave):
            difs.append(f"{clave}: obtenido={obtenido.get(clave)!r} referencia={referencia.get(clave)!r}")
    return difs


def control_c2(humo: bool) -> Dict[str, Any]:
    base = C.dir_base(humo)
    dir_ctrl = base / "control" / "ganadora_s42"
    reutilizado = (dir_ctrl / "resultado_semilla.json").exists()
    codigo, segundos = 0, 0.0
    if not reutilizado:
        humo_env = {"EXPJ_PRESUPUESTO": "6000", "EXPJ_FREQ_EVAL": "2000"} if humo else None
        codigo, segundos = C.correr_trabajador(
            C.SEMILLA_CONTROL, dir_ctrl, C.CONFIGS["ganadora"],
            base / "logs" / "control_ganadora_s42.log", humo=humo_env)
    if codigo != 0 or not (dir_ctrl / "resultado_semilla.json").exists():
        return {"aprobado": False, "codigo_salida": codigo, "motivo": "el trabajador falló"}
    if humo:
        return {"aprobado": True, "humo": True, "segundos": segundos}

    obtenido = json.loads((dir_ctrl / "resultado_semilla.json").read_text(encoding="utf-8"))
    referencia = json.loads((C.DIR_REF_S42 / "resultado_semilla.json").read_text(encoding="utf-8"))
    difs_json = _comparar_json(obtenido, referencia)
    hashes = {}
    for archivo in ("mejor_punto_control.zip", "_punto_control_actual.zip"):
        for miembro in ("policy.pth", "policy.optimizer.pth"):
            h_o = C.sha256_miembro_zip(dir_ctrl / archivo, miembro)
            h_r = C.sha256_miembro_zip(C.DIR_REF_S42 / archivo, miembro)
            hashes[f"{archivo}:{miembro}"] = {"obtenido": h_o, "referencia": h_r, "igual": h_o == h_r}
    aprobado = not difs_json and all(v["igual"] for v in hashes.values())
    return {
        "aprobado": aprobado, "reutilizado_de_corrida_previa": reutilizado,
        "segundos": segundos, "diferencias_json": difs_json, "hashes": hashes,
        "paso_retenido": obtenido.get("paso_retenido"),
        "cobertura_final": obtenido.get("cobertura_final"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--humo", action="store_true")
    args = parser.parse_args()

    if not args.humo and (J.PRESUPUESTO_PASOS != 200_000 or J.FRECUENCIA_EVAL_TS != 20_000):
        print("ABORTADO: hay variables EXPJ_* definidas en esta sesión")
        return 1

    oficial = json.loads(C.RUTA_METRICAS_100.read_text(encoding="utf-8"))["resultados"]
    informe: Dict[str, Any] = {"inicio": datetime.now().isoformat(timespec="seconds"),
                               "humo": args.humo}
    etapas = (("C2", lambda: control_c2(True)),) if args.humo else (
        ("C1", lambda: control_c1(oficial)),
        ("C3", lambda: control_c3(oficial)),
        ("C2", lambda: control_c2(False)),
    )
    ruta_informe = C.dir_base(args.humo) / "control" / "controles_P.json"
    if ruta_informe.exists():
        # Nunca sobrescribir: el informe previo se conserva con sufijo de fecha.
        ruta_informe.rename(ruta_informe.with_name(
            f"controles_P_respaldo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"))
    for nombre, funcion in etapas:
        informe[nombre] = funcion()
        print(f"{nombre}: {'APROBADO' if informe[nombre]['aprobado'] else 'FALLÓ'}", flush=True)
        if not informe[nombre]["aprobado"]:
            informe["fin"] = datetime.now().isoformat(timespec="seconds")
            informe["aprobado"] = False
            C.escribir_json(ruta_informe, informe)
            print(json.dumps(informe[nombre], indent=2, ensure_ascii=False))
            return 1
    informe["fin"] = datetime.now().isoformat(timespec="seconds")
    informe["aprobado"] = True
    C.escribir_json(ruta_informe, informe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
