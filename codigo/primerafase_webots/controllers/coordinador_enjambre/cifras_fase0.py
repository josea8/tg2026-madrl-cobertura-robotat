"""
cifras_fase0.py
===============
Calcula, desde los datos CRUDOS, todas las cifras del reporte de la Fase 0
de la demo del obstáculo móvil. Lo usan el reporte (para no copiar números a
mano) y `verificar_cifras.py` (para comprobarlos).

Entradas:
  <campaña>/<corrida>/resultado.json y decisiones.csv
  resultados_demo_obstaculo/regla_estancamiento_episodios.csv

    python cifras_fase0.py <carpeta_campaña> [salida.json]

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

CARPETA = Path(__file__).resolve().parent
UMBRAL = 0.15
ADVERTENCIA = 0.185


def _f(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def cargar(carpeta: Path) -> List[Dict[str, Any]]:
    filas = []
    for ruta in sorted(carpeta.glob("*/resultado.json")):
        r = json.loads(ruta.read_text(encoding="utf-8"))
        r["carpeta"] = ruta.parent.name
        filas.append(r)
    return filas


def _grupo(filas: List[Dict[str, Any]], bloque: str, tau: Optional[float] = None,
           sin_rampa: Optional[bool] = None) -> List[Dict[str, Any]]:
    return [r for r in filas if r["bloque"] == bloque
            and (tau is None or abs(float(r["tau"]) - tau) < 1e-9)
            and (sin_rampa is None or bool(r.get("sin_rampa")) == sin_rampa)]


def resumen_grupo(rs: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rs:
        return {"n": 0}
    d = [_f(r["verdad_d_min_obst"]) for r in rs]
    i = min(range(len(rs)), key=lambda j: d[j])
    return {
        "n": len(rs), "d_min": d[i], "caso_min": rs[i]["nombre"],
        "tau_min": float(rs[i]["tau"]),
        "d_mediana": sorted(d)[len(d) // 2],
        "bajo_015": sum(1 for x in d if not x > UMBRAL),
        "bajo_0185": sum(1 for x in d if x < ADVERTENCIA),
        "validas": sum(1 for r in rs if int(r.get("valido", 0) or 0)),
        "completas": sum(1 for r in rs
                         if int(r.get("decisiones", -1)) == int(r.get("decisiones_pedidas", -2))),
        "fallbacks_qp": sum(int(r.get("cbf_fallbacks", 0) or 0) for r in rs),
        "rescates_qp": sum(int(r.get("rescates_qp_n1", 0) or 0)
                           + int(r.get("rescates_qp_n2", 0) or 0) for r in rs),
        "corridas_con_rescate": sum(1 for r in rs
                                    if int(r.get("rescates_qp_n1", 0) or 0)
                                    + int(r.get("rescates_qp_n2", 0) or 0) > 0),
        "frenos_sombra": sum(int(r.get("frenos", 0) or 0) for r in rs),
        "corridas_con_freno_sombra": sum(1 for r in rs if int(r.get("frenos", 0) or 0)),
        "pares_bajo_015": sum(1 for r in rs if _f(r.get("verdad_d_min_pares")) < 0.15),
        "d_min_pares": min(_f(r.get("verdad_d_min_pares")) for r in rs),
        "cortes_regla_10s": sum(1 for r in rs
                                if r.get("corte_estancamiento_paso") not in ("", None)),
        "encuentros_045": sum(int(r.get("encuentros_045", 0) or 0) for r in rs),
        "d_min_medida_10hz": min(_f(r.get("d_min_obst_medida")) for r in rs),
        "ritmo_min": min((_f(r.get("ritmo_hz")) for r in rs
                          if r.get("ritmo_hz") not in (None, "")), default=float("nan")),
        "verdad_hz_min": min(_f(r.get("verdad_hz_efectivo")) for r in rs),
        "validas_demo": sum(1 for r in rs if int(r.get("valido_demo", 0) or 0)),
    }


def cortes_regla_arreglada(carpeta: Path, filas: List[Dict[str, Any]]
                           ) -> Dict[str, int]:
    """Réplica de la regla de 10 s ARREGLADA sobre cada corrida (período 0.1 s)."""
    sys.path.insert(0, str(CARPETA))
    import analizar_regla_estancamiento as A
    por_bloque: Dict[str, int] = defaultdict(int)
    for r in filas:
        ruta = carpeta / r["carpeta"] / "decisiones.csv"
        with open(ruta, newline="", encoding="utf-8") as fh:
            dec = list(csv.DictReader(fh))
        if A.replicar(dec, 0.1, arreglada=True)["corte"] is not None:
            por_bloque[r["bloque"]] += 1
    return dict(por_bloque)


def _rango(xs: List[float]) -> List[float]:
    return [min(xs), max(xs)] if xs else [float("nan"), float("nan")]


def cifras_extra(carpeta: Path, filas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Cifras puntuales del reporte que no son resúmenes de grupo."""
    e: Dict[str, Any] = {}
    por = {(r["bloque"], r["nombre"], round(float(r["tau"]), 2)): r for r in filas}
    conf = [r for r in filas if r["bloque"] == "conf_guionada"]
    e["angulo_laterales_conf"] = _rango([_f(r["verdad_angulo_min_deg"]) for r in conf
                                         if r["nombre"].startswith("C4_")])
    e["angulo_cruces_conf"] = _rango([_f(r["verdad_angulo_min_deg"]) for r in conf
                                      if r["nombre"].startswith("C6_")])
    # La corrida inválida de la confirmación
    inv = por[("conf_tomas", "toma_05_s420105", 0.45)]
    e["invalida_d_min_parcial"] = _f(inv["verdad_d_min_obst"])
    e["invalida_decisiones"] = int(inv["decisiones"])
    with open(carpeta / inv["carpeta"] / "obstaculo.csv", newline="",
              encoding="utf-8") as fh:
        tr = list(csv.DictReader(fh))
    t = [float(f["t"]) for f in tr]
    e["invalida_hueco_max_s"] = max(t[i] - t[i - 1] for i in range(1, len(t)))
    e["invalida_paso_aborto"] = int(tr[-1]["paso"])
    # La misma toma con τ = 0.85: decisiones con la fila del obstáculo activa
    r85 = por[("conf_tomas", "toma_05_s420105", 0.85)]
    with open(carpeta / r85["carpeta"] / "decisiones.csv", newline="",
              encoding="utf-8") as fh:
        dec = list(csv.DictReader(fh))
    activas: Dict[str, int] = defaultdict(int)
    for f in dec:
        if f["h_obst_geom"] not in ("", None) and float(f["h_obst_geom"]) < 0.06:
            activas[f["agente"]] += 1
    e["toma05_085_decisiones_fila_activa_max"] = max(activas.values())
    e["toma05_085_fallbacks"] = int(r85["cbf_fallbacks"])
    # Freno de respaldo en sombra, en diseño + confirmación
    frenos = [ev for r in filas if r["bloque"] in ("guionada", "tomas",
                                                   "conf_guionada", "conf_tomas")
              for ev in str(r.get("frenos_detalle", "")).split(";") if ev]
    e["frenos_sombra_corridas_dc"] = sum(
        1 for r in filas if r["bloque"] in ("guionada", "tomas", "conf_guionada",
                                            "conf_tomas") and int(r.get("frenos", 0) or 0))
    e["frenos_sombra_todos_encierro"] = all(
        "encierro" in r["nombre"] for r in filas
        if r["bloque"] in ("guionada", "tomas", "conf_guionada", "conf_tomas")
        and int(r.get("frenos", 0) or 0))
    e["frenos_sombra_dist"] = _rango([float(ev.split(":")[1]) for ev in frenos])
    # Tomas: colocación del obstáculo y error radial
    tm = [r for r in filas if r["bloque"] in ("tomas", "conf_tomas")]
    e["tomas_perturbacion_radial"] = _rango([float(r["obst_perturbacion"][0]) for r in tm])
    e["tomas_perturbacion_rumbo_deg"] = _rango([math.degrees(float(r["obst_perturbacion"][1]))
                                                for r in tm])
    e["tomas_perturbacion_radial_abs_cm"] = 100 * max(abs(float(r["obst_perturbacion"][0]))
                                                      for r in tm)
    e["tomas_error_radial_max"] = max(_f(r["obst_error_radial_max"]) for r in tm)
    e["tomas_todas_d_min"] = min(_f(r["verdad_d_min_obst"]) for r in tm)
    e["tomas_pares_bajo_015"] = sum(1 for r in tm if _f(r["verdad_d_min_pares"]) < 0.15)
    e["tomas_frenos_sombra"] = sum(int(r.get("frenos", 0) or 0) for r in tm)
    e["tomas_n"] = len(tm)
    e["e6_d_min"] = _rango([_f(r["verdad_d_min_obst"]) for r in filas
                            if r["nombre"].startswith("E6_")])
    e["corridas_interrumpidas"] = sum(1 for c_ in carpeta.iterdir()
                                      if c_.is_dir() and "_interrumpida_" in c_.name)
    e["ritmo_min_todas"] = min(_f(r.get("ritmo_hz")) for r in filas
                               if r.get("ritmo_hz") not in (None, ""))
    e["ritmo_max_todas"] = max(_f(r.get("ritmo_hz")) for r in filas
                               if r.get("ritmo_hz") not in (None, ""))
    e["verdad_hz_min_todas"] = min(_f(r.get("verdad_hz_efectivo")) for r in filas)
    # Campaña de diseño previa (peso de giro incondicional)
    previa = carpeta.parent / "fase0_20261001_134427"
    if previa.is_dir():
        pr = {(r["bloque"], r["nombre"], round(float(r["tau"]), 2)): r
              for r in cargar(previa)}
        e["previa_E5_AyB_085"] = _f(pr[("guionada", "E5_encierro_A_y_B_hacia_obstaculo",
                                       0.85)]["verdad_d_min_obst"])
        e["previa_ablacion_E5_AyB_085"] = _f(pr[("ablacion",
                                                 "E5_encierro_A_y_B_hacia_obstaculo_sinpeso",
                                                 0.85)]["verdad_d_min_obst"])
    # Barrido exploratorio de τ_c (5 casos × 2 τ por τ_c)
    barrido = carpeta.parent / "exploracion_fase0" / "barrido_tc"
    if barrido.is_dir():
        peor: Dict[str, float] = {}
        for r in cargar(barrido):
            tc = f"{float(r['tau_prediccion']):.2f}"
            peor[tc] = min(peor.get(tc, float("inf")), _f(r["verdad_d_min_obst"]))
        e["barrido_peor_por_tc"] = peor
    # Batería existente: la corrida después de los dos arreglos (02-10); si
    # no está, la del 01-10.
    log = carpeta.parent / "bateria_existente_post_arreglos_20261002.log"
    if not log.is_file():
        log = carpeta.parent / "exploracion_fase0" / "bateria_existente.log"
    if log.is_file():
        texto = log.read_text(encoding="utf-8", errors="replace")
        import re
        m = re.search(r"Ran (\d+) tests", texto)
        f_ = re.search(r"FAILED \(failures=(\d+)\)", texto)
        e["bateria_total"] = int(m.group(1)) if m else -1
        e["bateria_fallas"] = int(f_.group(1)) if f_ else 0
    return e


def comparar_confirmaciones(primera: Path, segunda: Path) -> Dict[str, Any]:
    """
    Corrida por corrida, la 2.ª confirmación (tras el arreglo de la
    obediencia, que NO toca la barrera) contra la 1.ª: la diferencia es la
    variabilidad del simulador en tiempo real.
    """
    def conf(c: Path) -> Dict[tuple, Dict[str, Any]]:
        return {(r["bloque"], r["nombre"], round(float(r["tau"]), 2)): r
                for r in cargar(c) if r["bloque"].startswith("conf_")}
    a, b = conf(primera), conf(segunda)
    pares = [(a[k], b[k]) for k in a if k in b and int(a[k].get("valido", 0) or 0)
             and int(b[k].get("valido", 0) or 0)]
    d = [_f(y["verdad_d_min_obst"]) - _f(x["verdad_d_min_obst"]) for x, y in pares]
    ad = sorted(abs(v) for v in d)
    k_inv = ("conf_tomas", "toma_05_s420105", 0.45)
    return {
        "pares": len(pares),
        "delta_media": sum(d) / len(d),
        "abs_delta_mediana": ad[len(ad) // 2],
        "abs_delta_p90": ad[int(0.9 * len(ad))],
        "abs_delta_max": ad[-1],
        "antes_invalida_ahora_valida": int(b[k_inv]["valido"]),
        "antes_invalida_ahora_decisiones": int(b[k_inv]["decisiones"]),
        "antes_invalida_ahora_d_min": _f(b[k_inv]["verdad_d_min_obst"]),
        "decisiones_sin_estimacion_v_2a": sum(int(r.get("obst_decisiones_sin_estimacion_v", 0) or 0)
                                              for r in b.values()),
        "abs_delta_mediana_mm": 1000 * ad[len(ad) // 2],
        "abs_delta_p90_cm": 100 * ad[int(0.9 * len(ad))],
        "abs_delta_max_cm": 100 * ad[-1],
        **_tres_corridas(primera, segunda),
        **_mecanismo_encierro(primera, segunda),
        **_ensayo_l2(primera.parent / "ensayo_l2_20261002_201318", "ensayo"),
        **_ensayo_l2(primera.parent / "ensayo_l2_20261003_093317", "ensayo_intermedio"),
        **_ensayo_l2(_ensayo_posterior(primera.parent), "ensayo_final"),
        **_humo_conf(primera.parent),
    }


def _primera_carpeta(c: Path, sufijo: str) -> Path:
    return next(x for x in sorted(c.iterdir())
                if x.is_dir() and x.name.endswith(sufijo) and "_interrumpida_" not in x.name)


def _mecanismo_encierro(primera: Path, segunda: Path) -> Dict[str, Any]:
    """
    El mecanismo del encierro, de los crudos: quién marca el mínimo en el
    trío, cuántos rescates de cada nivel, y cuándo llega el primer escape del
    agente encerrado respecto de su mínimo (decisiones, a 10 Hz).
    """
    e: Dict[str, Any] = {}
    trio = _primera_carpeta(segunda, "_conf_guionada_C5_encierro_trio_sinrampa_tau0.85_F2")
    r = json.loads((trio / "resultado.json").read_text(encoding="utf-8"))
    e["trio_agente_min"] = int(r["verdad_agente_min"])
    e["trio_d_min_agente_0"] = _f(r["d_min_obst_a0"])
    e["trio_rescates_n1"] = int(r["rescates_qp_n1"])
    e["trio_rescates_n2"] = int(r["rescates_qp_n2"])
    e["trio_rescates_fallidos"] = int(r["rescates_qp_fallidos"])
    e["trio_rescates_total"] = (e["trio_rescates_n1"] + e["trio_rescates_n2"]
                                + e["trio_rescates_fallidos"])
    for clave, c in (("e5", _primera_carpeta(
                         primera, "_guionada_E5_encierro_A_quieto_B_hacia_A_sinrampa_tau0.85_F2")),
                     ("mixto", _primera_carpeta(
                         primera, "_mixto_E5_encierro_A_quieto_B_hacia_A_tob0.45_tau0.85_F2"))):
        with open(c / "decisiones.csv", newline="", encoding="utf-8") as fh:
            filas = [f for f in csv.DictReader(fh) if int(f["agente"]) == 0]
        d = [(int(f["paso"]), _f(f["d_obst_medida"])) for f in filas
             if f["d_obst_medida"] not in ("", "nan")]
        e[f"{clave}_paso_min_a0"] = min(d, key=lambda x: x[1])[0]
        e[f"{clave}_primer_escape_a0"] = min(int(f["paso"]) for f in filas
                                             if f["en_escape"] in ("1", "True"))
    return e


def _ensayo_posterior(raiz: Path) -> Path:
    """
    El ensayo de la L2 con el código FINAL de las reglas de parada
    (2026-10-03, tras la revisión): el último, sin contar el intermedio
    (093317), que corrió con la primera versión.
    """
    cand = [c for c in sorted(raiz.glob("ensayo_l2_20261003_*"))
            if c.name != "ensayo_l2_20261003_093317"]
    return cand[-1] if cand else raiz / "ensayo_l2_inexistente"


def _ensayo_l2(carpeta: Path, pref: str) -> Dict[str, Any]:
    """Un ensayo de la sesión L2 en el simulador (§8 del reporte)."""
    import statistics
    rutas = sorted(carpeta.glob("*_L2_tomas.csv")) if carpeta.is_dir() else []
    if not rutas:
        return {}
    ruta = rutas[-1]
    with open(ruta, newline="", encoding="utf-8") as fh:
        tomas = list(csv.DictReader(fh))
    validas = [t for t in tomas if int(t["valido"] or 0)]
    d = sorted(_f(t["d_min_obst_medida"]) for t in validas)
    invalidas = [t for t in tomas if not int(t["valido"] or 0)]
    return {
        f"{pref}_intentos": len(tomas),
        f"{pref}_validas": len(validas),
        f"{pref}_validas_demo": sum(1 for t in tomas if int(t["valido_demo"] or 0)),
        f"{pref}_frenos": sum(int(t["frenos"] or 0) for t in tomas),
        f"{pref}_d_min": d[0],
        f"{pref}_d_mediana": statistics.median(d),
        f"{pref}_d_max": d[-1],
        f"{pref}_bajo_0185": sum(1 for x in d if x < 0.185),
        f"{pref}_invalida_toma": int(invalidas[0]["toma"]) if invalidas else -1,
        f"{pref}_invalida_decisiones": int(invalidas[0]["decisiones"]) if invalidas else -1,
        f"{pref}_invalida_motivo": invalidas[0]["motivo"] if invalidas else "",
        f"{pref}_ciclos_100ms_por_toma": [int(t["ciclos_sobre_100ms"] or 0) for t in tomas],
        f"{pref}_duracion_tomas_s": sum(_f(t["duracion_s"]) for t in tomas),
        f"{pref}_recorrido_toma1": _f(tomas[0]["obst_recorrido_m"]),
        f"{pref}_recorrido_resto_min": min((_f(t["obst_recorrido_m"]) for t in tomas[1:]
                                           if int(t["valido"] or 0)), default=float("nan")),
        f"{pref}_paradas": sum(1 for t in tomas if t.get("regla_parada")),
        f"{pref}_invalidas": [[int(t["toma"]), int(t["decisiones"])] for t in invalidas],
        f"{pref}_ciclo_p95_max_ms": max(_f(t["ciclo_p95_ms"]) for t in tomas),
        f"{pref}_freno_activo": all(int(t["obst_freno_activo"] or 0) for t in tomas),
    }


def _tres_corridas(primera: Path, segunda: Path) -> Dict[str, Any]:
    """
    Freno de respaldo (en sombra) y tomas con política sobre las TRES
    corridas: diseño y 1.ª confirmación (campaña final) más la 2.ª.
    """
    bloques = ("guionada", "tomas", "conf_guionada", "conf_tomas")
    filas = [r for c in (primera, segunda) for r in cargar(c) if r["bloque"] in bloques]
    con_freno = [r for r in filas if int(r.get("frenos", 0) or 0)]
    dist = [float(ev.split(":")[1]) for r in con_freno
            for ev in str(r.get("frenos_detalle", "")).split(";") if ev]
    tm = [r for r in filas if r["bloque"] in ("tomas", "conf_tomas")]
    return {
        "tres_frenos_corridas": len(con_freno),
        "tres_frenos_en_guionadas": sum(1 for r in con_freno
                                        if r["bloque"] in ("guionada", "conf_guionada")),
        "tres_frenos_todos_encierro": all("encierro" in r["nombre"] for r in con_freno),
        "tres_frenos_dist": _rango(dist),
        "tres_tomas_n": len(tm),
        "tres_tomas_frenos": sum(int(r.get("frenos", 0) or 0) for r in tm),
        "tres_tomas_d_min": min(_f(r["verdad_d_min_obst"]) for r in tm
                                if int(r.get("valido", 0) or 0)),
    }


def calcular(carpeta: Path) -> Dict[str, Any]:
    filas = cargar(carpeta)
    c: Dict[str, Any] = {"carpeta": carpeta.name, "corridas": len(filas)}
    for bloque in sorted({r["bloque"] for r in filas}):
        c[f"{bloque}"] = resumen_grupo(_grupo(filas, bloque))
        for tau in (0.45, 0.85):
            c[f"{bloque}|{tau:.2f}"] = resumen_grupo(_grupo(filas, bloque, tau))
            for sr in (False, True):
                g = _grupo(filas, bloque, tau, sr)
                if g:
                    c[f"{bloque}|{tau:.2f}|{'sin' if sr else 'con'}"] = resumen_grupo(g)
    # Decide: conf_guionada + conf_tomas
    decide = [r for r in filas if r["bloque"] in ("conf_guionada", "conf_tomas")]
    c["confirmacion"] = resumen_grupo(decide)
    # Validez de la DEMO, aparte de la de la medición: las tomas no válidas
    # para el video y por qué.
    for nombre, sel in (("confirmacion", decide),
                        ("diseno", [r for r in filas if r["bloque"] in ("guionada", "tomas")])):
        c[f"{nombre}_demo"] = {
            "validas_medicion": sum(1 for r in sel if int(r.get("valido", 0) or 0)),
            "validas_demo": sum(1 for r in sel if int(r.get("valido_demo", 0) or 0)),
            "no_demo_por_freno": sum(1 for r in sel if int(r.get("valido", 0) or 0)
                                     and int(r.get("frenos", 0) or 0)),
            "no_demo_por_freno_en_guionadas": sum(
                1 for r in sel if r["bloque"] in ("guionada", "conf_guionada")
                and int(r.get("valido", 0) or 0) and int(r.get("frenos", 0) or 0)),
            "no_demo_por_freno_en_tomas": sum(
                1 for r in sel if r["bloque"] in ("tomas", "conf_tomas")
                and int(r.get("frenos", 0) or 0)),
            "frenos_todos_en_encierros": all(
                "encierro" in r["nombre"] for r in sel if int(r.get("frenos", 0) or 0)),
        }
    diseno = [r for r in filas if r["bloque"] in ("guionada", "tomas")]
    c["diseno"] = resumen_grupo(diseno)
    c["regla_10s_arreglada_cortes"] = cortes_regla_arreglada(carpeta, filas)
    c["regla_10s_arreglada_total"] = sum(c["regla_10s_arreglada_cortes"].values())
    # Por caso, con rampa: F0 / F1 / F2 sin peso / F2
    por_caso: Dict[str, Dict[str, float]] = defaultdict(dict)
    for r in filas:
        if r.get("sin_rampa") or r["bloque"] not in ("guionada", "control",
                                                     "propuesta", "ablacion"):
            continue
        base = r["nombre"].replace("_sinpeso", "")
        etiqueta = {"guionada": "F2", "control": "F0", "propuesta": "F1",
                    "ablacion": "F2_sin_peso"}[r["bloque"]]
        por_caso[f"{base}|{float(r['tau']):.2f}"][etiqueta] = _f(r["verdad_d_min_obst"])
    c["por_caso"] = dict(por_caso)
    c["por_caso_conf"] = {f"{r['nombre']}|{float(r['tau']):.2f}": _f(r["verdad_d_min_obst"])
                          for r in filas if r["bloque"] == "conf_guionada"}
    c.update(cifras_extra(carpeta, filas))
    # Regla de 10 s en los episodios reales (junto a la carpeta de la campaña:
    # en el repositorio, `resultados_demo_obstaculo/`; en el paquete, la raíz)
    ruta = carpeta.parent / "regla_estancamiento_episodios.csv"
    if ruta.is_file():
        with open(ruta, newline="", encoding="utf-8") as fh:
            ep = list(csv.DictReader(fh))
        pedidas = [e for e in ep if not e["sesion"].startswith("extra")]
        extra = [e for e in ep if e["sesion"].startswith("extra")]
        def resumen_ep(sel: List[Dict[str, str]]) -> Dict[str, Any]:
            val = [e for e in sel if e["valido"] == "1"]
            return {
                "episodios": len(sel), "validos": len(val),
                "cortes_reales": sum(int(e["corte_real_por_regla"]) for e in sel),
                "replica_actual_cortes": sum(1 for e in sel if e.get("vieja_corte_real")),
                "replica_arreglada_cortes": sum(1 for e in sel if e.get("nueva_corte_real")),
                "exposicion_max_actual": max(_f(e.get("vieja_exposicion_max_real_s"))
                                             for e in sel if e.get("vieja_exposicion_max_real_s")),
                "exposicion_max_arreglada": max(_f(e.get("nueva_exposicion_max_real_s"))
                                                for e in sel if e.get("nueva_exposicion_max_real_s")),
                "exposicion_max_validos_actual": max((_f(e.get("vieja_exposicion_max_real_s"))
                                                      for e in val if e.get("vieja_exposicion_max_real_s")),
                                                     default=float("nan")),
                "validos_que_cambian": sum(1 for e in val
                                           if e.get("nueva_corte_real") != e.get("vieja_corte_real")),
            }
        c["regla_real_pedidas"] = resumen_ep(pedidas)
        c["regla_real_extra"] = resumen_ep(extra)
        v30 = [e for e in ep if e["sesion"].startswith("30-09") and e["valido"] == "1"]
        c["regla_real_30_09_validos"] = len(v30)
        c["regla_real_30_09_validos_que_cambian"] = sum(
            1 for e in v30 if e.get("nueva_corte_real") or e.get("nueva_corte_nominal"))
    return c


def main() -> int:
    carpeta = Path(sys.argv[1])
    c = calcular(carpeta)
    texto = json.dumps(c, indent=1, ensure_ascii=False)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_bytes(texto.encode("utf-8"))
    print(texto[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())


def _humo_conf(raiz: Path) -> Dict[str, Any]:
    """La prueba de humo del conjunto de confirmación, antes de la 1.ª corrida."""
    carpeta = raiz / "exploracion_fase0" / "humo_conf"
    if not carpeta.is_dir():
        return {}
    filas = cargar(carpeta)
    trio = [r for r in filas if r["nombre"] == "C5_encierro_trio_sinrampa"]
    return {"humo_corridas": len(filas),
            "humo_trio_sinrampa_d_min": _f(trio[0]["verdad_d_min_obst"]) if trio else float("nan")}
