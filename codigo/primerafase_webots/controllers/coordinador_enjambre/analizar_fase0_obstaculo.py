"""
analizar_fase0_obstaculo.py
===========================
Lee una carpeta de la campaña (`correr_fase0_obstaculo.py`), aplica el
criterio FIJADO ANTES de correr y escribe `analisis_fase0.txt` y
`analisis_fase0.json` en la misma carpeta. No corre nada ni pisa nada.

Criterio (José, 2026-10-01): distancia mínima CONTINUA entre centros
agente–obstáculo (`verdad_d_min_obst`, pose verdadera del simulador a
200 Hz) > 0.15 m en TODOS los casos guionados y en las 10 tomas, con
τ = 0.45 s y con τ = 0.85 s, con y sin rampa, para F2 (la formulación que
va al laboratorio). Desde el 2026-10-02 (decisión de José) el VEREDICTO lo
da el conjunto de CONFIRMACIÓN (`BLOQUES_QUE_DECIDEN`); el mismo criterio
sobre la campaña de diseño (`BLOQUES_DE_DISENO`) se informa aparte.

El conjunto ESPERADO se reconstruye con `construir_specs` —las mismas specs
que lanza la campaña—, no con lo que haya en la carpeta: una corrida que
falte, cuyo proceso se haya caído, que no sea válida o que no haya llegado a
sus decisiones hace que el criterio NO se cumpla (revisión de la Fase 0: la
versión anterior daba PASA sobre lo que hubiera). Advertencia aparte (no
criterio): < 0.185 m.

    python analizar_fase0_obstaculo.py <carpeta>

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

UMBRAL_M: float = 0.15
ADVERTENCIA_M: float = 0.185

Clave = Tuple[str, str, float, str]


def _f(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def clave(r: Dict[str, Any]) -> Clave:
    return (str(r["bloque"]), str(r["nombre"]), round(float(r["tau"]), 4),
            str(r["formulacion"]))


def cargar(carpeta: Path) -> Dict[Clave, Dict[str, Any]]:
    filas: Dict[Clave, Dict[str, Any]] = {}
    for ruta in sorted(carpeta.glob("*/resultado.json")):
        r = json.loads(ruta.read_text(encoding="utf-8"))
        r["carpeta"] = ruta.parent.name
        filas[clave(r)] = r
    return filas


def completa(r: Dict[str, Any]) -> Tuple[bool, str]:
    """¿La corrida cuenta para el criterio? (válida y con todas sus decisiones)."""
    if not int(r.get("valido", 0) or 0):
        return False, f"no válida: {r.get('motivo', '')}"
    if int(r.get("decisiones", -1)) != int(r.get("decisiones_pedidas", -2)):
        return False, (f"{r.get('decisiones')} de {r.get('decisiones_pedidas')}"
                       f" decisiones")
    d = _f(r.get("verdad_d_min_obst"))
    if math.isnan(d):
        return False, "sin distancia medida"
    return True, ""


def analizar(carpeta: Path) -> Dict[str, Any]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from correr_fase0_obstaculo import (BLOQUES_DE_DISENO, BLOQUES_QUE_DECIDEN,
                                        TAUS, construir_specs)
    filas = cargar(carpeta)
    lineas: List[str] = []
    out: Dict[str, Any] = {"carpeta": str(carpeta), "corridas": len(filas)}
    lineas.append(f"Carpeta: {carpeta}")
    lineas.append(f"Corridas con resultado.json: {len(filas)}")
    sin_res = [c.name for c in sorted(carpeta.iterdir())
               if c.is_dir() and not (c / "resultado.json").is_file()]
    out["sin_resultado"] = sin_res
    if sin_res:
        lineas.append(f"⚠ carpetas SIN resultado.json ({len(sin_res)}): {sin_res}")

    # ── Criterio: confirmación (decide) y diseño (se informa) ───────────
    def criterio(bloques: Tuple[str, ...], titulo: str) -> Dict[str, Any]:
        esperadas = [clave(e) for e in construir_specs(list(bloques),
                                                       list(TAUS))]
        faltan = [k for k in esperadas if k not in filas]
        incompletas = []
        d_crit: List[Tuple[float, Clave]] = []
        for k in esperadas:
            if k in filas:
                ok, motivo = completa(filas[k])
                if not ok:
                    incompletas.append((k, motivo))
                d_crit.append((_f(filas[k].get("verdad_d_min_obst")), k))
        bajo = [(d, k) for d, k in d_crit if not d > UMBRAL_M]
        adv = [(d, k) for d, k in d_crit if d < ADVERTENCIA_M]
        pasa = (not faltan and not incompletas and not bajo
                and len(d_crit) == len(esperadas) and len(esperadas) > 0)
        d_min, k_min = min(d_crit) if d_crit else (float("nan"), None)
        lineas.append("")
        lineas.append(f"{titulo} (F2; bloques {list(bloques)}; τ {list(TAUS)};"
                      f" con y sin rampa): {'PASA' if pasa else 'NO PASA'}")
        lineas.append(f"  esperadas {len(esperadas)} · presentes {len(d_crit)}"
                      f" · faltan {len(faltan)} · incompletas "
                      f"{len(incompletas)} · ≤ {UMBRAL_M} m: {len(bajo)} · "
                      f"< {ADVERTENCIA_M} m: {len(adv)}")
        if k_min:
            lineas.append(f"  mínimo {d_min:.6f} m en {k_min[1]} "
                          f"(τ = {k_min[2]})")
        for k in faltan:
            lineas.append(f"  ✘ FALTA {k}")
        for k, m in incompletas:
            lineas.append(f"  ✘ INCOMPLETA {k}: {m}")
        for d, k in bajo:
            lineas.append(f"  ✘ BAJO EL UMBRAL {d:.6f} m: {k}")
        for d, k in adv:
            lineas.append(f"  ⚠ advertencia {d:.6f} m: {k}")
        return {
            "pasa": pasa, "bloques": list(bloques),
            "esperadas": len(esperadas), "presentes": len(d_crit),
            "faltan": [list(k) for k in faltan],
            "incompletas": [[list(k), m] for k, m in incompletas],
            "bajo_015": [[d, list(k)] for d, k in bajo],
            "bajo_0185": [[d, list(k)] for d, k in adv],
            "d_min": d_min, "caso_min": list(k_min) if k_min else None,
        }
    out["criterio"] = criterio(tuple(BLOQUES_QUE_DECIDEN),
                               "VEREDICTO — CONJUNTO DE CONFIRMACIÓN")
    out["criterio_diseno"] = criterio(tuple(BLOQUES_DE_DISENO),
                                      "Campaña de DISEÑO (se informa, no decide)")

    # ── Tabla por grupo ──────────────────────────────────────────────────
    grupos: Dict[Tuple[str, str, float, bool], List[Dict[str, Any]]] = defaultdict(list)
    for r in filas.values():
        grupos[(str(r["bloque"]), str(r["formulacion"]), float(r["tau"]),
                bool(r.get("sin_rampa")))].append(r)
    lineas.append("")
    lineas.append("Distancia mínima CONTINUA (verdad, 200 Hz) agente–obstáculo, "
                  "entre centros, m")
    lineas.append(f"{'bloque':<10} {'form':<5} {'τ':>5} {'rampa':>5} {'n':>3} "
                  f"{'mín':>9} {'mediana':>8} {'caso del mínimo':<46} "
                  f"{'≤0.15':>5} {'<0.185':>6} {'pares<.15':>9} {'fbQP':>4} "
                  f"{'resc':>4} {'frenoS':>6} {'corte10s':>8} {'inval':>5}")
    out["grupos"] = {}
    for g in sorted(grupos):
        rs = sorted(grupos[g], key=lambda r: r["nombre"])
        d = [_f(r.get("verdad_d_min_obst")) for r in rs]
        i_min = min(range(len(rs)), key=lambda j: d[j])
        fila = {
            "n": len(rs), "d_min": d[i_min], "caso_min": rs[i_min]["nombre"],
            "d_mediana": sorted(d)[len(d) // 2],
            "bajo_015": sum(1 for x in d if not x > UMBRAL_M),
            "bajo_0185": sum(1 for x in d if x < ADVERTENCIA_M),
            "pares_bajo_015": sum(1 for r in rs
                                  if _f(r.get("verdad_d_min_pares")) < 0.15),
            "fallbacks_qp": sum(int(r.get("cbf_fallbacks", 0) or 0) for r in rs),
            "rescates_qp": sum(int(r.get("rescates_qp_n1", 0) or 0)
                               + int(r.get("rescates_qp_n2", 0) or 0) for r in rs),
            "frenos_sombra": sum(int(r.get("frenos", 0) or 0) for r in rs),
            "cortes_estancamiento": sum(
                1 for r in rs if r.get("corte_estancamiento_paso") not in ("", None)),
            "no_validas": sum(1 for r in rs if not int(r.get("valido", 0) or 0)),
        }
        out["grupos"][f"{g[0]}|{g[1]}|{g[2]:.2f}|{'sin' if g[3] else 'con'}"] = fila
        lineas.append(
            f"{g[0]:<10} {g[1]:<5} {g[2]:>5.2f} {'sin' if g[3] else 'con':>5} "
            f"{len(rs):>3} {fila['d_min']:>9.6f} {fila['d_mediana']:>8.4f} "
            f"{fila['caso_min']:<46} {fila['bajo_015']:>5} {fila['bajo_0185']:>6} "
            f"{fila['pares_bajo_015']:>9} {fila['fallbacks_qp']:>4} "
            f"{fila['rescates_qp']:>4} {fila['frenos_sombra']:>6} "
            f"{fila['cortes_estancamiento']:>8} {fila['no_validas']:>5}")

    # ── Comparación por caso: F0 / F1 / F2 sin peso / F2 (con rampa) ─────
    def base(nombre: str) -> str:
        for suf in ("_sinpeso", "_sinrampa"):
            nombre = nombre.replace(suf, "")
        return nombre
    por_caso: Dict[Tuple[str, float], Dict[str, float]] = defaultdict(dict)
    for r in filas.values():
        if r["bloque"] in ("guionada", "control", "propuesta", "ablacion") \
                and not r.get("sin_rampa"):
            etiqueta = {"guionada": "F2", "control": "F0", "propuesta": "F1",
                        "ablacion": "F2_sin_peso"}[r["bloque"]]
            por_caso[(base(r["nombre"]), float(r["tau"]))][etiqueta] = _f(
                r.get("verdad_d_min_obst"))
    if por_caso:
        lineas.append("")
        lineas.append("Por caso guionado (con rampa): distancia mínima verdad, m")
        lineas.append(f"{'caso':<36} {'τ':>5} {'F0':>8} {'F1':>8} "
                      f"{'F2s/peso':>9} {'F2':>8} {'F2−F0':>8}")
        out["por_caso"] = {}
        for (caso, tau) in sorted(por_caso):
            v = por_caso[(caso, tau)]
            def fmt(x: Any) -> str:
                return f"{x:8.4f}" if isinstance(x, float) and not math.isnan(x) else f"{'—':>8}"
            dif = (v["F2"] - v["F0"]) if "F2" in v and "F0" in v else float("nan")
            lineas.append(f"{caso:<36} {tau:>5.2f} {fmt(v.get('F0'))} "
                          f"{fmt(v.get('F1'))} {fmt(v.get('F2_sin_peso')):>9} "
                          f"{fmt(v.get('F2'))} {fmt(dif)}")
            out["por_caso"][f"{caso}|{tau:.2f}"] = v
    ctrl = [r for r in filas.values() if r["bloque"] == "control"]
    if ctrl:
        caen = [r for r in ctrl if _f(r["verdad_d_min_obst"]) < UMBRAL_M]
        out["control_n"] = len(ctrl)
        out["control_bajo_015"] = len(caen)
        out["control_detecta"] = len(caen) > 0
        lineas.append("")
        lineas.append(f"CONTROL NEGATIVO (F0): {len(caen)}/{len(ctrl)} corridas "
                      f"bajo {UMBRAL_M} m → la medición "
                      f"{'DETECTA' if caen else 'NO detecta'} una barrera que falla")

    # ── Ritmo y muestreo ─────────────────────────────────────────────────
    ritmo = [_f(r.get("ritmo_hz")) for r in filas.values()
             if r.get("ritmo_hz") not in (None, "")]
    hz = [_f(r.get("verdad_hz_efectivo")) for r in filas.values()]
    if ritmo:
        out["ritmo_min"], out["ritmo_max"] = min(ritmo), max(ritmo)
        lineas.append("")
        lineas.append(f"Ritmo del lazo de medición (decisiones/s): mín "
                      f"{min(ritmo):.3f} · máx {max(ritmo):.3f}")
    if hz:
        out["verdad_hz_min"] = min(hz)
        lineas.append(f"Muestreo de la verdad (Hz): mín {min(hz):.1f}")

    # ── Detalle ──────────────────────────────────────────────────────────
    lineas.append("")
    lineas.append("Detalle por corrida")
    lineas.append(f"{'carpeta':<86} {'verdad':>9} {'10Hz':>8} {'ag':>2} "
                  f"{'ángulo':>6} {'t_min':>6} {'enc':>3} {'sat':>4} "
                  f"{'pesoG':>5} {'fb':>3} {'resc':>4} {'esc':>3} {'frenoS':>6} "
                  f"{'corte':>5} {'v':>2}")
    for r in sorted(filas.values(), key=lambda x: x["carpeta"]):
        lineas.append(
            f"{r['carpeta']:<86} {_f(r.get('verdad_d_min_obst')):>9.6f} "
            f"{_f(r.get('d_min_obst_medida')):>8.4f} "
            f"{r.get('verdad_agente_min', ''):>2} "
            f"{_f(r.get('verdad_angulo_min_deg')):>6.0f} "
            f"{_f(r.get('verdad_t_min_s')):>6.1f} "
            f"{r.get('encuentros_045', ''):>3} "
            f"{r.get('decisiones_fila_saturada', ''):>4} "
            f"{r.get('decisiones_peso_giro', ''):>5} "
            f"{r.get('cbf_fallbacks', ''):>3} "
            f"{int(r.get('rescates_qp_n1', 0) or 0) + int(r.get('rescates_qp_n2', 0) or 0):>4} "
            f"{r.get('escapes', ''):>3} {r.get('frenos', ''):>6} "
            f"{str(r.get('corte_estancamiento_paso', '')):>5} "
            f"{r.get('valido', ''):>2}")
    texto = "\n".join(lineas) + "\n"
    (carpeta / "analisis_fase0.txt").write_bytes(texto.encode("utf-8"))
    (carpeta / "analisis_fase0.json").write_bytes(
        json.dumps(out, indent=1, ensure_ascii=False).encode("utf-8"))
    print("\n".join(lineas[:60]))
    return out


if __name__ == "__main__":
    analizar(Path(sys.argv[1]))
