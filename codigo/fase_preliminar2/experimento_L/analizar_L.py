"""
analizar_L.py — Experimento L: consolidación, tablas, figura y contraste de Amdahl.

Lee TODAS las corridas disponibles por condición (`resultados/regimen1/<cond>`
y `<cond>_<sufijo>`; ídem `regimen2/`) y produce:

  resultados/mediciones_L.csv           — todas las mediciones en formato largo,
                                          cada una con su definición, conjunto y n
  resultados/tabla_comparativa.md       — tablas de los dos regímenes
  resultados/fig_cpu_gpu_inferencia.png — ms/decisión contra n, tres condiciones,
                                          eje de tiempo logarítmico
  resultados/analisis_L.json            — Amdahl, punto de cruce, equivalencia

POR QUÉ MEDIANAS POR ITERACIÓN Y NO SÓLO TOTALES. La máquina del autor corre
otras aplicaciones y no se pudo aislar; los totales de pared de una corrida
arrastran valores atípicos (una iteración PPO llegó a 105 s de entorno contra
una mediana de 1.25 s). La mediana por iteración es estable entre corridas y
el mínimo aproxima el costo sin contención. Se reportan las tres cosas: totales
crudos, medianas y mínimos, con la carga de CPU medida durante cada corrida.

Contraste de Amdahl. Con f = fracción de `learn` que es red neuronal en la
condición de control (inferencia del rollout + actualización) y s_red = la
aceleración que la GPU logra SOBRE ESA FRACCIÓN (medida, no supuesta),

    S_pred = 1 / ((1 − f) + f / s_red)

se compara con la observada S_obs = learn_cpu / learn_gpu. El techo 1/(1 − f)
es lo que el Exp J llamó "1.20×" con f = 0.17. Se calcula con totales crudos
(corrida 1) y con medianas por iteración agrupando corridas.

No corre ningún experimento: sólo lee resultados.

Autor: José — Tesis Mecatrónica UVG
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from comun_L import CONDICIONES, DIR_RESULTADOS, escribir_csv

# ── Cifras publicadas con las que se contrasta (bitácora, Exp E y Exp J) ──────
EXP_E_MADRL_MS:   float = 0.757   # ms/decisión, media de ambas condiciones de borde, n=5
EXP_E_MADRL_MS_REFLEX: float = 0.734  # sólo condición reflexión (Tabla 5 del resumen)
EXP_E_VORONOI_MS: float = 8.039   # ms/decisión Voronoi+PSO, n=5
EXP_J_FRAC_RED:   float = 0.17    # reparto 83/17 del perfilador del Exp J
COBERTURA_OFICIAL: float = 0.681291
COBERTURA_FASE0_FRESCA: float = 0.68359383   # Exp J Fase 0, 200k semilla 42, 20 eps
# Dispersión entre semillas del Trial 13 bajo el protocolo multimétrico
# (bitácora Exp J: 0.698 / 0.679 / 0.532)
COBERTURAS_SEMILLAS_TRIAL13: Tuple[float, ...] = (0.698, 0.679, 0.532)

ETIQUETA: Dict[str, str] = {
    "gpu":         "GPU (torch 2.11+cu128, cuda)",
    "cpu_control": "CPU control (torch 2.11+cu128, cpu)",
    "referencia":  "Referencia (torch 2.10+cpu, cpu)",
}
# Color por ENTIDAD, orden fijo (paleta de referencia validada del skill dataviz)
COLOR: Dict[str, str] = {"referencia": "#2a78d6", "cpu_control": "#eb6834", "gpu": "#1baf7a"}


def cargar_json(ruta: Path) -> Optional[Dict[str, Any]]:
    """Devuelve el JSON o None si el archivo no existe todavía."""
    return json.loads(ruta.read_bytes().decode("utf-8")) if ruta.exists() else None


def cargar_csv(ruta: Path) -> List[Dict[str, str]]:
    """Lee un CSV como lista de diccionarios de texto (sin conversión)."""
    if not ruta.exists():
        return []
    with open(ruta, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def corridas_de(regimen: str, condicion: str) -> List[Path]:
    """Directorios de corridas válidas de una condición (excluye respaldos e incompletas)."""
    base = DIR_RESULTADOS / regimen
    return [d for d in sorted(base.glob(f"{condicion}*"))
            if d.is_dir() and (d / "reporte.json").exists()
            and "respaldo" not in d.name and "INCOMPLETO" not in d.name]


# ══════════════════════════════════════════════════════════════════════════════
#  Régimen 1
# ══════════════════════════════════════════════════════════════════════════════

def _iteraciones(d: Path) -> Dict[str, np.ndarray]:
    it = cargar_csv(d / "tiempos_por_iteracion.csv")
    return {
        "entorno":       np.array([float(x["seg_entorno"]) for x in it]),
        "inferencia":    np.array([float(x["seg_inferencia"]) for x in it]),
        "actualizacion": np.array([float(x["seg_actualizacion"]) for x in it if x["seg_actualizacion"] != "nan"]),
    }


def analizar_regimen1() -> Tuple[List[str], Dict[str, Any], List[Dict[str, Any]]]:
    """Tablas, Amdahl (crudo y por medianas), equivalencia y filas largas."""
    lineas: List[str] = []
    filas: List[Dict[str, Any]] = []
    corridas: Dict[str, List[Path]] = {c: corridas_de("regimen1", c) for c in CONDICIONES}
    disponibles = [c for c in CONDICIONES if corridas[c]]
    if not disponibles:
        return ["(régimen 1 sin resultados)"], {}, filas
    rep1 = {c: cargar_json(corridas[c][0] / "reporte.json") for c in disponibles}
    n_iter = rep1[disponibles[0]]["configuracion"]["n_iteraciones_ppo"]
    nmb = rep1[disponibles[0]]["configuracion"]["n_minibatches_por_actualizacion"]

    lineas.append("### Régimen 1 — entrenamiento (Trial 13, semilla 42, 200 000 pasos, 4 envs = 20 flujos)")
    lineas.append("")
    lineas.append(f"Una corrida = {n_iter} iteraciones PPO; cada iteración = rollout de 2560 transiciones "
                  f"(128 pasos × 20 flujos) + actualización de {nmb} minibatches de 64 (13 épocas × 40). "
                  "`entorno` = `step_async`+`step_wait` del VecEnv (4 procesos, incluye IPC); "
                  "`inferencia` = `collect_rollouts` − entorno (forward de la política + buffer); "
                  "`actualización` = `train()`; `red` = inferencia + actualización.")
    lineas.append("")
    lineas.append("**Tabla 1a — totales crudos de la corrida 1** (segundos de pared; cobertura AoI final "
                  "media ± σ sobre 100 episodios deterministas del protocolo, semillas 42·10000+i, "
                  "reflexión, n = 5, sobre el modelo entrenado en la condición):")
    lineas.append("")
    lineas.append("| Condición | learn total | entorno | inferencia | actualización | red | pasos/s | cobertura (100 eps) | colisiones <0.15 m |")
    lineas.append("|---|---|---|---|---|---|---|---|---|")
    for c in disponibles:
        r = rep1[c]; t = r["tiempos_s"]; p = r["reparto_pct_de_learn"]
        cob = r["protocolo_cobertura"]["cobertura_aoi_final"]; col = r["protocolo_cobertura"]["colisiones_015"]
        lineas.append(
            f"| {ETIQUETA[c]} | {t['learn_total']:.1f} | {t['entorno']:.1f} ({p['entorno']:.1f} %) | "
            f"{t['inferencia_rollout']:.1f} ({p['inferencia_rollout']:.1f} %) | "
            f"{t['actualizacion']:.1f} ({p['actualizacion']:.1f} %) | {t['red_total']:.1f} ({p['red_total']:.1f} %) | "
            f"{r['pasos_por_segundo_learn']:.0f} | {cob['media']:.6f} ± {cob['std']:.6f} | {col['media']:.3f} |"
        )
        for clave, val in t.items():
            filas.append({"regimen": 1, "condicion": corridas[c][0].name, "variable": f"tiempo_{clave}", "n_agentes": 5,
                          "valor": val, "unidad": "s", "definicion": "tiempo de pared total, corrida 1, 200k pasos"})
        for clave, val in p.items():
            filas.append({"regimen": 1, "condicion": corridas[c][0].name, "variable": f"reparto_{clave}", "n_agentes": 5,
                          "valor": val, "unidad": "% de learn_total", "definicion": "fracción del tiempo de learn, corrida 1"})

    # ── Tabla 1b: todas las corridas, medianas y mínimos por iteración ───────
    lineas.append("")
    lineas.append("**Tabla 1b — todas las corridas, por iteración PPO** (mediana y mínimo sobre las "
                  f"{n_iter} iteraciones; ms/minibatch = actualización/{nmb}; carga = ocupación media "
                  "de CPU de todo el sistema durante la corrida, % de 12 hilos lógicos; `propio` = "
                  "núcleos medios del proceso principal, sin los 4 trabajadores):")
    lineas.append("")
    lineas.append("| Corrida | learn total [s] | entorno/iter med (mín) [s] | inferencia/iter med (mín) [s] | actualización/iter med (mín) [s] | ms/minibatch med (mín) | carga % | propio núcleos | cobertura 100 eps | colisiones |")
    lineas.append("|---|---|---|---|---|---|---|---|---|---|")
    med: Dict[str, Dict[str, float]] = {}     # por condición, mediana agrupando corridas
    minimo: Dict[str, Dict[str, float]] = {}
    equivalencia: Dict[str, Any] = {"banda_semillas_trial13": [min(COBERTURAS_SEMILLAS_TRIAL13), max(COBERTURAS_SEMILLAS_TRIAL13)],
                                    "oficial_modelo_PRIMERO_100eps": COBERTURA_OFICIAL,
                                    "fase0_fresca_20eps": COBERTURA_FASE0_FRESCA, "por_corrida": {}}
    for c in disponibles:
        agrupado: Dict[str, List[np.ndarray]] = {"entorno": [], "inferencia": [], "actualizacion": []}
        for d in corridas[c]:
            rep = cargar_json(d / "reporte.json"); it = _iteraciones(d)
            for k in agrupado:
                agrupado[k].append(it[k])
            carga = rep.get("carga_cpu_durante_corrida", {})
            cob = rep["protocolo_cobertura"]["cobertura_aoi_final"]; col = rep["protocolo_cobertura"]["colisiones_015"]
            lineas.append(f"| {d.name} | {rep['tiempos_s']['learn_total']:.1f} | "
                          f"{np.median(it['entorno']):.2f} ({it['entorno'].min():.2f}) | "
                          f"{np.median(it['inferencia']):.3f} ({it['inferencia'].min():.3f}) | "
                          f"{np.median(it['actualizacion']):.2f} ({it['actualizacion'].min():.2f}) | "
                          f"{1e3*np.median(it['actualizacion'])/nmb:.2f} ({1e3*it['actualizacion'].min()/nmb:.2f}) | "
                          f"{carga.get('ocupacion_sistema_pct_media', float('nan')):.1f} | "
                          f"{carga.get('proceso_principal_nucleos_medios', float('nan')):.2f} | "
                          f"{cob['media']:.6f} | {col['media']:.3f} |")
            banda = equivalencia["banda_semillas_trial13"]
            equivalencia["por_corrida"][d.name] = {
                "condicion": c, "media": cob["media"], "std": cob["std"], "ic95": [cob["ic95_inf"], cob["ic95_sup"]],
                "colisiones_015": col["media"], "delta_vs_oficial": cob["media"] - COBERTURA_OFICIAL,
                "identico_a_modelo_PRIMERO_6dec": abs(cob["media"] - COBERTURA_OFICIAL) < 1e-6,
                "dentro_banda_semillas": banda[0] <= cob["media"] <= banda[1]}
            for nombre in ("entorno", "inferencia", "actualizacion"):
                for est, val in (("mediana", float(np.median(it[nombre]))), ("min", float(it[nombre].min()))):
                    filas.append({"regimen": 1, "condicion": d.name, "variable": f"iter_{nombre}_{est}", "n_agentes": 5,
                                  "valor": val, "unidad": "s por iteración PPO",
                                  "definicion": f"{est} sobre {len(it[nombre])} iteraciones de 2560 transiciones"})
            filas.append({"regimen": 1, "condicion": d.name, "variable": "carga_sistema_media", "n_agentes": 5,
                          "valor": carga.get("ocupacion_sistema_pct_media", float("nan")), "unidad": "% de 12 hilos",
                          "definicion": "ocupación media de CPU de todo el sistema durante la corrida"})
            filas.append({"regimen": 1, "condicion": d.name, "variable": "cobertura_aoi_final_media", "n_agentes": 5,
                          "valor": cob["media"], "unidad": "adimensional",
                          "definicion": "media sobre 100 episodios del protocolo único, modelo entrenado en la corrida"})
            filas.append({"regimen": 1, "condicion": d.name, "variable": "colisiones_015_media", "n_agentes": 5,
                          "valor": col["media"], "unidad": "pares/episodio", "definicion": "media sobre 100 episodios"})
        med[c] = {k: float(np.median(np.concatenate(v))) for k, v in agrupado.items()}
        minimo[c] = {k: float(np.min(np.concatenate(v))) for k, v in agrupado.items()}
        med[c]["n_corridas"] = len(corridas[c])

    # ── Amdahl ────────────────────────────────────────────────────────────────
    amdahl: Dict[str, Any] = {}

    def contraste(tc: Dict[str, float], tg: Dict[str, float]) -> Dict[str, float]:
        red_c = tc["inferencia"] + tc["actualizacion"]; red_g = tg["inferencia"] + tg["actualizacion"]
        tot_c = tc["entorno"] + red_c; tot_g = tg["entorno"] + red_g
        f = red_c / tot_c; s_red = red_c / red_g
        return {"f_red_cpu_control": f, "techo_amdahl_medido": 1 / (1 - f),
                "s_red_gpu_vs_cpu": s_red, "s_inferencia": tc["inferencia"] / tg["inferencia"],
                "s_actualizacion": tc["actualizacion"] / tg["actualizacion"], "s_entorno": tc["entorno"] / tg["entorno"],
                "S_pred_amdahl": 1 / ((1 - f) + f / s_red), "S_obs": tot_c / tot_g}

    if "gpu" in disponibles and "cpu_control" in disponibles:
        t1c = rep1["cpu_control"]["tiempos_s"]; t1g = rep1["gpu"]["tiempos_s"]
        crudo = contraste({"entorno": t1c["entorno"], "inferencia": t1c["inferencia_rollout"], "actualizacion": t1c["actualizacion"]},
                          {"entorno": t1g["entorno"], "inferencia": t1g["inferencia_rollout"], "actualizacion": t1g["actualizacion"]})
        mediana = contraste(med["cpu_control"], med["gpu"])
        minimos = contraste(minimo["cpu_control"], minimo["gpu"])
        amdahl = {"techo_amdahl_expJ_f017": 1 / (1 - EXP_J_FRAC_RED),
                  "totales_crudos_corrida1": crudo, "medianas_por_iteracion_todas_las_corridas": mediana,
                  "minimos_por_iteracion_todas_las_corridas": minimos}
        if "referencia" in disponibles:
            amdahl["version_torch_referencia_vs_control_medianas"] = {
                "S_total": (med["referencia"]["entorno"] + med["referencia"]["inferencia"] + med["referencia"]["actualizacion"]) /
                           (med["cpu_control"]["entorno"] + med["cpu_control"]["inferencia"] + med["cpu_control"]["actualizacion"]),
                "S_red": (med["referencia"]["inferencia"] + med["referencia"]["actualizacion"]) /
                         (med["cpu_control"]["inferencia"] + med["cpu_control"]["actualizacion"])}
        lineas.append("")
        lineas.append("**Contraste con Amdahl** (f y s_red MEDIDOS; control = misma rueda cu128 en CPU):")
        lineas.append("")
        lineas.append("| Base de cálculo | f_red (control) | techo 1/(1−f) | s_red GPU/CPU | s_inferencia | s_actualización | s_entorno | S_pred Amdahl | S_obs |")
        lineas.append("|---|---|---|---|---|---|---|---|---|")
        for nombre, a in (("totales crudos, corrida 1", crudo),
                          (f"medianas por iteración, {med['cpu_control']['n_corridas']}+{med['gpu']['n_corridas']} corridas", mediana),
                          ("mínimos por iteración (sin contención)", minimos)):
            lineas.append(f"| {nombre} | {a['f_red_cpu_control']:.3f} | {a['techo_amdahl_medido']:.2f}× | "
                          f"{a['s_red_gpu_vs_cpu']:.3f}× | {a['s_inferencia']:.3f}× | {a['s_actualizacion']:.3f}× | "
                          f"{a['s_entorno']:.3f}× | {a['S_pred_amdahl']:.3f}× | {a['S_obs']:.3f}× |")
        lineas.append("")
        lineas.append(f"- Exp J suponía f = {EXP_J_FRAC_RED:.2f} (techo {1/(1-EXP_J_FRAC_RED):.2f}×). La f medida dentro de la corrida "
                      "es mucho mayor porque los cuatro trabajadores simulan el entorno EN PARALELO y el proceso "
                      "principal sólo espera; el perfilador del Exp J midió el entorno en serie.")
        lineas.append("- S_pred y S_obs coinciden por construcción cuando s_entorno ≈ 1; la diferencia entre ambos mide "
                      "cuánto cambió el tiempo de entorno entre condiciones (contención, no dispositivo).")
        if "referencia" in disponibles:
            v = amdahl["version_torch_referencia_vs_control_medianas"]
            lineas.append(f"- Efecto de la VERSIÓN de torch (referencia 2.10 → control 2.11, ambas CPU, medianas): "
                          f"{v['S_total']:.3f}× total, {v['S_red']:.3f}× en la fracción de red.")
        for grupo, a in amdahl.items():
            if isinstance(a, dict):
                for k, v in a.items():
                    filas.append({"regimen": 1, "condicion": "gpu_vs_cpu_control", "variable": f"amdahl_{grupo}_{k}", "n_agentes": 5,
                                  "valor": v, "unidad": "adimensional", "definicion": "ver analizar_L.py, contraste()"})

    # ── Equivalencia ─────────────────────────────────────────────────────────
    lineas.append("")
    lineas.append("**Verificación de equivalencia** (cobertura del modelo entrenado en cada corrida, 100 eps del protocolo):")
    lineas.append("")
    banda = equivalencia["banda_semillas_trial13"]
    for nombre, e in equivalencia["por_corrida"].items():
        lineas.append(f"- {nombre}: {e['media']:.8f} (IC95 [{e['ic95'][0]:.4f}, {e['ic95'][1]:.4f}]), colisiones {e['colisiones_015']:.3f}; "
                      f"Δ vs oficial {e['delta_vs_oficial']:+.8f} → "
                      + ("**idéntico a `modelo_PRIMERO` a 6 decimales**" if e["identico_a_modelo_PRIMERO_6dec"] else
                         ("dentro" if e["dentro_banda_semillas"] else "FUERA") + f" de la banda entre semillas [{banda[0]:.3f}, {banda[1]:.3f}]") + ".")
    return lineas, {"amdahl": amdahl, "equivalencia": equivalencia, "medianas_por_condicion": med, "minimos_por_condicion": minimo}, filas


# ══════════════════════════════════════════════════════════════════════════════
#  Régimen 2
# ══════════════════════════════════════════════════════════════════════════════

def analizar_regimen2() -> Tuple[List[str], Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    """Tablas, cruce y filas largas del régimen de inferencia; agrupa corridas."""
    lineas: List[str] = []
    filas: List[Dict[str, Any]] = []
    corridas: Dict[str, List[Path]] = {c: corridas_de("regimen2", c) for c in CONDICIONES}
    disponibles = [c for c in CONDICIONES if corridas[c]]
    if not disponibles:
        return ["(régimen 2 sin resultados)"], {}, filas, {}
    rep0 = cargar_json(corridas[disponibles[0]][0] / "reporte.json")
    lista_n = [int(k) for k in rep0["protocolo_por_n"].keys()]

    # Agrupar decisiones de todas las corridas por (condición, n)
    agrupado: Dict[str, Dict[int, np.ndarray]] = {}
    for c in disponibles:
        agrupado[c] = {}
        for n in lista_n:
            partes = [np.load(d / f"tiempos_decision_n{n}.npy") for d in corridas[c] if (d / f"tiempos_decision_n{n}.npy").exists()]
            agrupado[c][n] = np.concatenate(partes)

    lineas.append("### Régimen 2 — inferencia (`modelo_PRIMERO`, protocolo del Exp E)")
    lineas.append("")
    lineas.append("ms por decisión = tiempo de la llamada completa (apilar n observaciones, `predict` "
                  "determinista, desempaquetar), `perf_counter`, dentro de episodios reales del entorno "
                  "del protocolo (reflexión, sin domain randomization). Por (condición, n) se agrupan las "
                  "decisiones de TODAS las corridas; se reporta la mediana agrupada y, entre corchetes, la "
                  "media. Conjunto por corrida: "
                  + "; ".join(f"n={n}: {rep0['protocolo_por_n'][str(n)]['n_episodios']} eps × "
                              f"{rep0['protocolo_por_n'][str(n)]['pasos_por_episodio']} pasos" for n in lista_n)
                  + ". Para n ≥ 50 los episodios están truncados y el sorteo de poses cae a la grilla: "
                  "sólo la latencia es válida ahí, no la cobertura.")
    lineas.append("")
    lineas.append("**Tabla 2a — protocolo, mediana agrupada [media], ms** (corridas por condición: "
                  + ", ".join(f"{c} {len(corridas[c])}" for c in disponibles) + "):")
    lineas.append("")
    lineas.append("| n agentes | decisiones/cond. | " + " | ".join(ETIQUETA[c] for c in disponibles) + " | GPU / CPU control (medianas) |")
    lineas.append("|---|---|" + "---|" * (len(disponibles) + 1))
    cruce: Dict[str, Any] = {"protocolo_razon_medianas": {}, "sintetico_razon_medianas": {}}
    resumen_fig: Dict[str, Any] = {"protocolo": {}, "sintetico": {}}
    for n in lista_n:
        celdas = []
        for c in disponibles:
            t = agrupado[c][n]
            celdas.append(f"{np.median(t):.4f} [{np.mean(t):.4f}]")
            resumen_fig["protocolo"].setdefault(c, {})[n] = {"mediana": float(np.median(t)), "p25": float(np.percentile(t, 25)),
                                                             "p75": float(np.percentile(t, 75)), "media": float(np.mean(t)), "n": int(len(t))}
            for est, val in (("mediana", float(np.median(t))), ("media", float(np.mean(t))), ("p95", float(np.percentile(t, 95)))):
                filas.append({"regimen": 2, "condicion": c, "variable": f"t_decision_ms_{est}", "n_agentes": n,
                              "valor": val, "unidad": "ms", "definicion": f"{est} sobre {len(t)} decisiones agrupando {len(corridas[c])} corridas, episodios reales"})
        razon = ""
        if "gpu" in disponibles and "cpu_control" in disponibles:
            r = float(np.median(agrupado["gpu"][n]) / np.median(agrupado["cpu_control"][n]))
            cruce["protocolo_razon_medianas"][n] = r; razon = f"{r:.2f}×"
        lineas.append(f"| {n} | {len(agrupado[disponibles[0]][n])} | " + " | ".join(celdas) + f" | {razon} |")

    # Por corrida (variabilidad entre corridas)
    lineas.append("")
    lineas.append("**Tabla 2b — por corrida, mediana [media] a n = 5 y n = 100, ms**, con carga media de CPU del sistema:")
    lineas.append("")
    lineas.append("| Corrida | n=5 | n=100 | sintético n=5 | sintético n=5000 | carga % | control n=5 (cobertura 100 eps) |")
    lineas.append("|---|---|---|---|---|---|---|")
    control: Dict[str, Any] = {}
    for c in disponibles:
        for d in corridas[c]:
            rep = cargar_json(d / "reporte.json")
            t5 = np.load(d / "tiempos_decision_n5.npy"); t100 = np.load(d / "tiempos_decision_n100.npy")
            s = {int(f["n_agentes"]): f for f in rep.get("sintetico", [])}
            k = rep["control_n5"]; control[d.name] = k
            lineas.append(f"| {d.name} | {np.median(t5):.4f} [{np.mean(t5):.4f}] | {np.median(t100):.4f} [{np.mean(t100):.4f}] | "
                          f"{s[5]['t_decision_ms_mediana']:.4f} | {s[5000]['t_decision_ms_mediana']:.4f} | "
                          f"{rep.get('carga_cpu_durante_corrida', {}).get('ocupacion_sistema_pct_media', float('nan')):.1f} | "
                          f"{k['cobertura_media_100eps']:.8f} (Δ {k['delta']:+.1e}, {'reproduce' if k['reproduce_6_decimales'] else 'NO reproduce'}) |")
            filas.append({"regimen": 2, "condicion": d.name, "variable": "control_cobertura_n5_100eps", "n_agentes": 5,
                          "valor": k["cobertura_media_100eps"], "unidad": "adimensional",
                          "definicion": "cobertura AoI final media, modelo_PRIMERO, 100 episodios del protocolo único"})
            filas.append({"regimen": 2, "condicion": d.name, "variable": "t_decision_ms_media_n5", "n_agentes": 5,
                          "valor": float(np.mean(t5)), "unidad": "ms", "definicion": "media sobre 50 000 decisiones de la corrida (comparable con Exp E 0.757)"})
    lineas.append("")
    lineas.append(f"Publicado en Exp E (n = 5, CPU, torch 2.10): MADRL {EXP_E_MADRL_MS} ms de media "
                  f"({EXP_E_MADRL_MS_REFLEX} sólo reflexión); Voronoi+PSO {EXP_E_VORONOI_MS} ms.")

    # Sintético
    lineas.append("")
    lineas.append("**Tabla 2c — barrido sintético (complementario, NO protocolo)**: `predict` sobre lotes `(n, 24)` "
                  "aleatorios fijos; mediana de 300 repeticiones (100 para n > 1000), promediada entre corridas, ms:")
    lineas.append("")
    lineas.append("| n | " + " | ".join(ETIQUETA[c] for c in disponibles) + " | GPU / CPU control |")
    lineas.append("|---|" + "---|" * (len(disponibles) + 1))
    sint_med: Dict[str, Dict[int, float]] = {}
    for c in disponibles:
        acum: Dict[int, List[float]] = {}
        for d in corridas[c]:
            for f in cargar_json(d / "reporte.json").get("sintetico", []):
                acum.setdefault(int(f["n_agentes"]), []).append(f["t_decision_ms_mediana"])
        sint_med[c] = {n: float(np.mean(v)) for n, v in acum.items()}
        resumen_fig["sintetico"][c] = sint_med[c]
    for n in sorted(sint_med[disponibles[0]]):
        celdas = [f"{sint_med[c][n]:.4f}" for c in disponibles]
        for c in disponibles:
            filas.append({"regimen": 2, "condicion": c, "variable": "sintetico_t_ms_mediana", "n_agentes": n,
                          "valor": sint_med[c][n], "unidad": "ms", "definicion": "mediana de predict sobre lote sintético (n,24), promedio de corridas"})
        razon = ""
        if "gpu" in disponibles and "cpu_control" in disponibles:
            r = sint_med["gpu"][n] / sint_med["cpu_control"][n]
            cruce["sintetico_razon_medianas"][n] = r; razon = f"{r:.2f}×"
        lineas.append(f"| {n} | " + " | ".join(celdas) + f" | {razon} |")

    def primer_cruce(d: Dict[int, float]) -> Optional[int]:
        for n in sorted(d):
            if d[n] < 1.0:
                return n
        return None

    cp = primer_cruce(cruce["protocolo_razon_medianas"]); cs = primer_cruce(cruce["sintetico_razon_medianas"])
    cruce["primer_n_gpu_mas_rapida_protocolo"] = cp; cruce["primer_n_gpu_mas_rapida_sintetico"] = cs
    lineas.append("")
    lineas.append("**Punto de cruce:** "
                  + (f"en el protocolo la GPU es más rápida (mediana) desde n = {cp}." if cp else
                     "AUSENTE en el rango protocolar n ∈ {5..100}: la GPU es más lenta en todos los cardinales.")
                  + (f" En el barrido sintético, desde n = {cs}." if cs else " Tampoco aparece en el sintético hasta n = 5000."))
    return lineas, {"cruce": cruce, "control_n5": control}, filas, resumen_fig


# ══════════════════════════════════════════════════════════════════════════════
#  Figura
# ══════════════════════════════════════════════════════════════════════════════

def figura(resumen: Dict[str, Any], ruta: Path) -> None:
    """ms/decisión contra n, tres condiciones, eje de tiempo logarítmico; mediana y banda p25–p75."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    prot = resumen.get("protocolo", {}); sint = resumen.get("sintetico", {})
    disponibles = [c for c in CONDICIONES if c in prot]
    if not disponibles:
        return
    tiene_sint = all(c in sint and sint[c] for c in disponibles)
    fig, ejes = plt.subplots(1, 2 if tiene_sint else 1, figsize=(11.5 if tiene_sint else 6.5, 4.8), dpi=200)
    ejes = np.atleast_1d(ejes)
    superficie, tinta, tinta2, grilla = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
    fig.patch.set_facecolor(superficie)
    nombre_corto = {"gpu": "GPU", "cpu_control": "CPU control", "referencia": "referencia"}

    def etiquetar_extremos(ax, puntos: List[Tuple[str, float, float]], sep_log: float = 0.07) -> None:
        """Etiquetas directas al final de cada serie, separadas en log10 para que no se pisen."""
        orden = sorted(puntos, key=lambda p: p[2])
        ys = [np.log10(p[2]) for p in orden]
        for i in range(1, len(ys)):
            if ys[i] - ys[i - 1] < sep_log:
                ys[i] = ys[i - 1] + sep_log
        for (nombre, x, _y), yl in zip(orden, ys):
            ax.annotate(nombre, (x, 10 ** yl), xytext=(6, 0), textcoords="offset points",
                        fontsize=8, color=tinta2, va="center")

    def estilo(ax, titulo: str, xlabel: str) -> None:
        ax.set_facecolor(superficie)
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.grid(True, which="major", color=grilla, linewidth=0.6); ax.grid(False, which="minor")
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)
        for lado in ("left", "bottom"):
            ax.spines[lado].set_color(grilla)
        ax.tick_params(colors=tinta2, labelsize=8.5)
        ax.set_title(titulo, fontsize=10, color=tinta, loc="left")
        ax.set_xlabel(xlabel, fontsize=9, color=tinta2)
        ax.set_ylabel("tiempo por decisión [ms]", fontsize=9, color=tinta2)

    ax = ejes[0]
    extremos: List[Tuple[str, float, float]] = []
    for c in disponibles:
        ns = sorted(prot[c]); med = [prot[c][n]["mediana"] for n in ns]
        p25 = [prot[c][n]["p25"] for n in ns]; p75 = [prot[c][n]["p75"] for n in ns]
        ax.fill_between(ns, p25, p75, color=COLOR[c], alpha=0.12, linewidth=0)
        ax.plot(ns, med, color=COLOR[c], linewidth=1.8, marker="o", markersize=5.5,
                markeredgecolor=superficie, markeredgewidth=1.0, label=ETIQUETA[c], zorder=3)
        extremos.append((nombre_corto[c], ns[-1], med[-1]))
    etiquetar_extremos(ax, extremos)
    ax.plot([5], [EXP_E_MADRL_MS], marker="D", markersize=6, color=tinta2, linestyle="none",
            markerfacecolor=superficie, label=f"Exp E publicado, MADRL {EXP_E_MADRL_MS} ms (CPU)", zorder=4)
    ax.plot([5], [EXP_E_VORONOI_MS], marker="x", markersize=7, color=tinta2, linestyle="none",
            label=f"Exp E publicado, Voronoi+PSO {EXP_E_VORONOI_MS} ms", zorder=4)
    ax.set_xticks([5, 10, 20, 50, 100]); ax.set_xticklabels(["5", "10", "20", "50", "100"])
    ax.set_xlim(4, 140)
    estilo(ax, "A. Protocolo del Exp E: episodios reales; mediana y banda p25–p75", "número de agentes n")
    ax.legend(fontsize=7.5, frameon=False, loc="upper right", labelcolor=tinta2)

    if tiene_sint:
        ax = ejes[1]
        extremos_b: List[Tuple[str, float, float]] = []
        for c in disponibles:
            ns = sorted(sint[c]); ys = [sint[c][n] for n in ns]
            ax.plot(ns, ys, color=COLOR[c], linewidth=1.8, marker="o", markersize=5.5,
                    markeredgecolor=superficie, markeredgewidth=1.0, label=ETIQUETA[c], zorder=3)
            extremos_b.append((nombre_corto[c], ns[-1], ys[-1]))
        etiquetar_extremos(ax, extremos_b)
        ax.set_xticks([5, 10, 100, 1000, 5000]); ax.set_xticklabels(["5", "10", "100", "1000", "5000"])
        ax.set_xlim(4, 8000)
        estilo(ax, "B. Complementario: lotes sintéticos (n, 24), fuera del protocolo; mediana", "número de agentes n (tamaño del lote)")
        ax.legend(fontsize=7.5, frameon=False, loc="upper left", labelcolor=tinta2)

    fig.suptitle("Experimento L — tiempo de inferencia por decisión de modelo_PRIMERO, CPU frente a GPU",
                 fontsize=10.5, color=tinta, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 0.98, 0.95))
    fig.savefig(ruta, facecolor=superficie)
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
#  Principal
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    lineas: List[str] = ["# Experimento L — costo computacional, CPU frente a GPU", ""]
    hw = None; hw_gpu = None
    for reg in ("regimen1", "regimen2"):
        for c in CONDICIONES:
            for d in corridas_de(reg, c):
                r = cargar_json(d / "reporte.json")
                hw = hw or r["hardware"]
                if c == "gpu":
                    hw_gpu = hw_gpu or r["hardware"]
    hw_gpu = hw_gpu or hw
    if hw:
        lineas += ["## Hardware declarado", "",
                   f"- CPU: {hw['cpu']['nombre']}, {hw['cpu']['nucleos_fisicos']} núcleos físicos / "
                   f"{hw['cpu']['nucleos_logicos']} lógicos; RAM {hw['ram_GiB']} GiB; {hw['so']}.",
                   f"- GPU: {hw_gpu['gpu'].get('nombre')}, {hw_gpu['gpu'].get('memoria_total_nvidia_smi')} "
                   f"(torch: {hw_gpu['gpu'].get('memoria_total_MiB_torch')} MiB), driver {hw_gpu['gpu'].get('driver')}, "
                   f"CUDA runtime de la rueda {hw_gpu['gpu'].get('cuda_runtime_torch')}, cuDNN {hw_gpu['gpu'].get('cudnn')}, "
                   f"capacidad de cómputo {hw_gpu['gpu'].get('capacidad_computo')}.",
                   f"- Hilos de torch en el proceso principal: {hw['torch_hilos']} (OMP_NUM_THREADS={hw['OMP_NUM_THREADS']}).",
                   "- La máquina NO estaba aislada: corrían otras aplicaciones del autor. La ocupación de CPU del "
                   "sistema se muestreó durante cada corrida y se reporta al lado de cada cifra.",
                   ""]
        lineas += ["## Condiciones", ""] + [f"- **{c}**: {ETIQUETA[c]}" for c in CONDICIONES] + [""]

    l1, a1, f1 = analizar_regimen1()
    l2, a2, f2, resumen_fig = analizar_regimen2()
    lineas += l1 + [""] + l2 + [""]

    (DIR_RESULTADOS / "tabla_comparativa.md").write_bytes(("\n".join(lineas) + "\n").encode("utf-8"))
    escribir_csv(DIR_RESULTADOS / "mediciones_L.csv", f1 + f2,
                 ("regimen", "condicion", "variable", "n_agentes", "valor", "unidad", "definicion"))
    (DIR_RESULTADOS / "analisis_L.json").write_bytes(
        json.dumps({**a1, **a2}, indent=2, ensure_ascii=False, default=str).encode("utf-8"))
    figura(resumen_fig, DIR_RESULTADOS / "fig_cpu_gpu_inferencia.png")
    print("\n".join(lineas))


if __name__ == "__main__":
    main()
