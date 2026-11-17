"""
analizar_regla_estancamiento.py
===============================
Análisis de SÓLO LECTURA de la regla "agente {ag} sin desplazamiento por
10 s" de `sesion_robotat._correr_episodio` (sesion_robotat.py:2957-2965)
sobre las evaluaciones físicas del 11-09, 26-09 y 30-09 (y, como extra, de
todas las sesiones de evaluación que haya en `resultados_sesion/`). No toca
ningún archivo existente: lee los CSV y escribe su salida en
`resultados_demo_obstaculo/`.

La regla, tal como está en el código:

    si |v_ejecutada| > 0.02  y  ahora − t_mov > 10 s  →  aborta

donde `t_mov` es el instante del ÚLTIMO desplazamiento > 2 mm entre
decisiones (o el de la primera decisión del agente). Los agentes en
retroceso se saltean.

⚠ Hallazgo de la Fase 0 del obstáculo móvil (2026-10-01): mide desde el
último desplazamiento, no desde que se le ORDENÓ moverse. Un agente quieto y
sin orden durante más de 10 s dispara el corte en la primera decisión con
|v| > 0.02, antes de que el retardo de actuación (0.45–0.85 s) le deje
moverse.

Arreglo PROPUESTO (no aplicado; espera el OK de José):

    t_ref = max(t_mov, t_inicio_orden + MARGEN_RETARDO_S)
    si la orden está sostenida  y  ahora − t_ref > 10 s  →  aborta

con `t_inicio_orden` = comienzo del período de orden vigente (|v| > 0.02),
que termina sólo tras `CORTE_ORDEN_S` seguidos sin orden (histéresis: un
filtro que parpadea no reinicia el reloj), y MARGEN_RETARDO_S = 1.0 s
(> 0.85 s de arranque a baja velocidad, medido el 29-08). Como
t_ref ≥ t_mov, el arreglo SÓLO puede quitar cortes, nunca agregar: lo que
hoy no corta, mañana tampoco. Se verifica igual, episodio por episodio.

Tiempo: la regla usa el reloj de pared, que no está en el CSV. Se usa el
período medio REAL de cada episodio (duracion_s / decisiones, del CSV de
episodios) y, como sensibilidad, el nominal de 0.1 s.

    python analizar_regla_estancamiento.py

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CARPETA = Path(__file__).resolve().parent
DIR_SESIONES = CARPETA / "resultados_sesion"
DIR_SALIDA = CARPETA / "resultados_demo_obstaculo"

V_MIN = 0.02
AVANCE_MIN_M = 0.002
T_UMBRAL_S = 10.0
MARGEN_RETARDO_S = 1.0
CORTE_ORDEN_S = 1.0
MOTIVO = "sin desplazamiento por 10 s"

#: (fecha, etiqueta, episodios, decisiones). El 30-09 son 5 sesiones; el
#: emparejamiento decisiones_k ↔ episodios_k es el de los scripts del
#: reporte del 30-09 (`a30f_metricas_comun.py`).
SESIONES_PEDIDAS: List[Tuple[str, str, str, str]] = [
    ("2026-09-11", "11-09", "20260911_sesion-evaluacion_etapa7_episodios.csv",
     "20260911_sesion-evaluacion_etapa7_decisiones.csv"),
    ("2026-09-26", "26-09", "20260926_sesion-evaluacion_etapa7_episodios.csv",
     "20260926_sesion-evaluacion_etapa7_decisiones.csv"),
    ("2026-09-30", "30-09 s1", "20260930_sesion-evaluacion_etapa7_episodios.csv",
     "20260930_sesion-evaluacion_etapa7_decisiones.csv"),
] + [("2026-09-30", f"30-09 s{k}",
      f"20260930_sesion-evaluacion_etapa7_episodios_0{k}.csv",
      f"20260930_sesion-evaluacion_etapa7_decisiones_0{k}.csv")
     for k in range(2, 6)]


def leer(ruta: Path) -> List[Dict[str, str]]:
    with open(ruta, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def replicar(filas: List[Dict[str, str]], periodo_s: float,
             arreglada: bool) -> Dict[str, Any]:
    """
    Recorre las filas de UN episodio (en orden) y devuelve el primer corte
    de la regla (vieja o arreglada) y la exposición: el máximo de
    (t − t_ref) en decisiones con orden, por agente.
    """
    previa: Dict[int, Tuple[float, float]] = {}
    t_mov: Dict[int, float] = {}
    t_orden: Dict[int, Optional[float]] = {}
    t_sin_orden: Dict[int, Optional[float]] = {}
    exposicion: Dict[int, float] = defaultdict(float)
    corte: Optional[Tuple[int, int, float]] = None
    for f in filas:
        ag = int(f["agente"])
        paso = int(f["paso"])
        t = paso * periodo_s
        p = (float(f["pose_env_x"]), float(f["pose_env_y"]))
        if ag in previa:
            if math.hypot(p[0] - previa[ag][0], p[1] - previa[ag][1]) > AVANCE_MIN_M:
                t_mov[ag] = t
        else:
            t_mov[ag] = t
        previa[ag] = p
        con_orden = abs(float(f["v_ejecutada"])) > V_MIN
        en_ret = int(float(f.get("en_retroceso", 0) or 0)) == 1
        # Período de orden con histéresis (sólo lo usa la regla arreglada).
        if con_orden:
            t_sin_orden[ag] = None
            if t_orden.get(ag) is None:
                t_orden[ag] = t
        else:
            if t_sin_orden.get(ag) is None:
                t_sin_orden[ag] = t
            if t_orden.get(ag) is not None and t - t_sin_orden[ag] >= CORTE_ORDEN_S:
                t_orden[ag] = None
        if en_ret or not con_orden:
            continue
        t_ref = t_mov[ag]
        if arreglada:
            inicio = t_orden[ag] if t_orden.get(ag) is not None else t
            t_ref = max(t_ref, inicio + MARGEN_RETARDO_S)
        exposicion[ag] = max(exposicion[ag], t - t_ref)
        if corte is None and t - t_ref > T_UMBRAL_S:
            corte = (paso, ag, t - t_ref)
    return {"corte": corte,
            "exposicion_max_s": max(exposicion.values()) if exposicion else 0.0,
            "exposicion": dict(exposicion)}


def analizar_sesion(fecha: str, etiqueta: str, ruta_ep: Path,
                    ruta_dec: Path) -> List[Dict[str, Any]]:
    episodios = {int(e["episodio"]): e for e in leer(ruta_ep)}
    por_ep: Dict[int, List[Dict[str, str]]] = defaultdict(list)
    for f in leer(ruta_dec):
        por_ep[int(f["episodio"])].append(f)
    out = []
    for n_ep in sorted(episodios):
        e = episodios[n_ep]
        filas = por_ep.get(n_ep, [])
        motivo = e.get("motivo", "") or ""
        fila: Dict[str, Any] = {
            "fecha": fecha, "sesion": etiqueta, "episodio": n_ep,
            "valido": int(float(e.get("valido", 0) or 0)),
            "motivo": motivo, "corte_real_por_regla": int(MOTIVO in motivo),
            "filas_decisiones": len(filas),
        }
        if filas:
            dec = float(e.get("decisiones", 0) or 0)
            dur = float(e.get("duracion_s", 0) or 0)
            periodo = dur / dec if dec > 0 and dur > 0 else 0.1
            for nombre, per in (("real", periodo), ("nominal", 0.1)):
                vieja = replicar(filas, per, arreglada=False)
                nueva = replicar(filas, per, arreglada=True)
                fila[f"periodo_{nombre}_s"] = per
                fila[f"vieja_corte_{nombre}"] = (
                    f"paso {vieja['corte'][0]} a{vieja['corte'][1]}"
                    if vieja["corte"] else "")
                fila[f"vieja_exposicion_max_{nombre}_s"] = vieja["exposicion_max_s"]
                fila[f"nueva_corte_{nombre}"] = (
                    f"paso {nueva['corte'][0]} a{nueva['corte'][1]}"
                    if nueva["corte"] else "")
                fila[f"nueva_exposicion_max_{nombre}_s"] = nueva["exposicion_max_s"]
        out.append(fila)
    return out


def main() -> int:
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    filas: List[Dict[str, Any]] = []
    for fecha, etiqueta, ep, dec in SESIONES_PEDIDAS:
        filas += analizar_sesion(fecha, etiqueta, DIR_SESIONES / ep,
                                 DIR_SESIONES / dec)
    # Extra: las demás sesiones de evaluación de la carpeta (no pedidas).
    pedidas = {ep for _f, _e, ep, _d in SESIONES_PEDIDAS}
    extras = []
    for ruta_ep in sorted(DIR_SESIONES.glob("*sesion-evaluacion_etapa7_episodios*.csv")):
        if ruta_ep.name in pedidas:
            continue
        ruta_dec = Path(str(ruta_ep).replace("_episodios", "_decisiones"))
        if ruta_dec.is_file():
            extras.append(ruta_ep.name)
            filas += analizar_sesion(ruta_ep.name[:8], f"extra {ruta_ep.name[:8]}"
                                     f"{ruta_ep.stem[-3:] if ruta_ep.stem[-3] == '_' else ''}",
                                     ruta_ep, ruta_dec)
    # ── resumen ──
    lineas: List[str] = []
    def bloque(sel: List[Dict[str, Any]], titulo: str) -> None:
        n = len(sel)
        val = [f for f in sel if f["valido"]]
        cortes_reales = [f for f in sel if f["corte_real_por_regla"]]
        vieja = [f for f in sel if f.get("vieja_corte_real")]
        nueva = [f for f in sel if f.get("nueva_corte_real")]
        exp_v = max((f.get("vieja_exposicion_max_real_s", 0.0) for f in sel), default=0.0)
        exp_n = max((f.get("nueva_exposicion_max_real_s", 0.0) for f in sel), default=0.0)
        # Cambio = el arreglo corta distinto que la regla actual (período
        # REAL). El nominal es sólo sensibilidad: en la sesión del 05-09 el
        # lazo corrió a ~70 Hz (reloj desbocado) y 0.1 s infla el tiempo 7×.
        val_cambia = [f for f in val
                      if f.get("nueva_corte_real") != f.get("vieja_corte_real")]
        agrega = [f for f in sel for k in ("real", "nominal")
                  if f.get(f"nueva_corte_{k}") and not f.get(f"vieja_corte_{k}")]
        lineas.append(f"{titulo}: {n} episodios ({len(val)} válidos)")
        lineas.append(f"  cortes REALES por la regla (motivo en el CSV): {len(cortes_reales)}"
                      + (f" → {[(f['sesion'], f['episodio']) for f in cortes_reales]}" if cortes_reales else ""))
        lineas.append(f"  réplica regla actual, período real: cortes {len(vieja)}"
                      + (f" → {[(f['sesion'], f['episodio'], f['vieja_corte_real']) for f in vieja]}" if vieja else "")
                      + f"; exposición máx {exp_v:.2f} s (umbral {T_UMBRAL_S:.0f} s)")
        lineas.append(f"  réplica regla ARREGLADA, período real: cortes {len(nueva)}"
                      + f"; exposición máx {exp_n:.2f} s")
        lineas.append(f"  válidos que el arreglo cambiaría (período real): {len(val_cambia)}")
        lineas.append(f"  episodios donde el arreglo corta y la regla actual no "
                      f"(real o nominal): {len(agrega)}")
    por_fecha: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for f in filas:
        por_fecha[f["sesion"].split(" s")[0] if f["sesion"].startswith("30-09") else f["sesion"]].append(f)
    for clave in ("11-09", "26-09", "30-09"):
        bloque(por_fecha.get(clave, []), clave)
    bloque([f for f in filas if not f["sesion"].startswith("extra")],
           "PEDIDAS (11-09 + 26-09 + 30-09)")
    bloque([f for f in filas if f["sesion"].startswith("extra")],
           f"EXTRA (otras sesiones: {extras})")
    # Los 50 válidos del 30-09, uno por uno
    v30 = [f for f in filas if f["sesion"].startswith("30-09") and f["valido"]]
    lineas.append("")
    lineas.append(f"30-09: {len(v30)} válidos. Regla arreglada corta "
                  f"{sum(1 for f in v30 if f.get('nueva_corte_real'))} (período real) y "
                  f"{sum(1 for f in v30 if f.get('nueva_corte_nominal'))} (nominal); "
                  f"regla actual (réplica) corta "
                  f"{sum(1 for f in v30 if f.get('vieja_corte_real'))} y "
                  f"{sum(1 for f in v30 if f.get('vieja_corte_nominal'))}")
    texto = "\n".join(lineas) + "\n"
    print(texto)
    (DIR_SALIDA / "regla_estancamiento_resumen.txt").write_bytes(texto.encode("utf-8"))
    columnas: List[str] = []
    for f in filas:
        for k in f:
            if k not in columnas:
                columnas.append(k)
    with open(DIR_SALIDA / "regla_estancamiento_episodios.csv", "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columnas, lineterminator="\n")
        w.writeheader()
        for f in filas:
            w.writerow({k: (repr(v) if isinstance(v, float) else v) for k, v in f.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
