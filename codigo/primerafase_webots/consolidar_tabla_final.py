"""
consolidar_tabla_final.py
=========================
Consolida las 5 configuraciones evaluadas en Webots (5 agentes, 18 semillas
420000-420017, física real) en una sola tabla lista para citar en la tesis.

Lee los CSV por episodio que dejó `coordinador_enjambre` en modo lote y emite:
  resultados_consolidados/tabla_final_webots.csv   (una fila por configuración)
  resultados_consolidados/tabla_final_webots.txt   (misma tabla, legible)

No recalcula nada ni toca los CSV de origen: sólo agrega.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

_RAIZ: Path = Path(__file__).resolve().parent
_LOTES: Path = _RAIZ / "controllers" / "coordinador_enjambre" / "resultados"
_SALIDA: Path = _RAIZ / "resultados_consolidados"

N_AGENTES: int = 5

# (etiqueta, archivo, política, CBF)
CONFIGS: List[tuple] = [
    ("v2 sanidad",          "lote_multi_5agentes.csv",
     "modelo_sanidad", False),
    ("v2 sanidad + CBF",    "lote_multi_5agentes_cbf.csv",
     "modelo_sanidad", True),
    ("v3 radio (λ=0)",      "lote_multi_5agentes_modelo_v3_lp0.csv",
     "modelo_v3_lp0", False),
    ("v3 radio + CBF",      "lote_multi_5agentes_modelo_v3_lp0_cbf.csv",
     "modelo_v3_lp0", True),
    ("v4 contacto rígido",  "lote_multi_5agentes_modelo_v4_mejor.csv",
     "modelo_v4_mejor", False),
]


def agregar(etiqueta: str, archivo: str, politica: str,
            cbf: bool) -> Optional[Dict[str, object]]:
    """Agrega un CSV de lote a una fila de la tabla final."""
    ruta = _LOTES / archivo
    if not ruta.is_file():
        print(f"  FALTA: {archivo}")
        return None

    filas = list(csv.DictReader(open(ruta, encoding="utf-8")))
    n_eps = len(filas)

    cob  = np.array([float(r["cobertura_aoi_final"]) for r in filas])
    c015 = np.array([float(r["colisiones_015"])      for r in filas])
    c022 = np.array([float(r["colisiones_022"])      for r in filas])
    atas = np.array([int(r["agentes_atascados"])     for r in filas])

    # Distancia mínima a pared: mínimo y media sobre todos los agente-episodios.
    dists = [
        float(r[f"dist_min_pared_a{i}"])
        for r in filas for i in range(N_AGENTES)
        if float(r[f"dist_min_pared_a{i}"]) >= 0.0
    ]

    # Fracción de pasos-agente intervenidos por el CBF (0 si no está activo).
    if cbf and "cbf_frac_pasos_intervenidos" in filas[0]:
        frac = np.array([
            float(r["cbf_frac_pasos_intervenidos"]) for r in filas
        ])
        frac_media = float(np.mean(frac))
        # Correlación conflicto → atascos (el criterio operativo).
        corr = (float(np.corrcoef(frac, atas)[0, 1])
                if float(np.std(frac)) > 0 and float(np.std(atas)) > 0
                else float("nan"))
    else:
        frac_media = 0.0
        corr = float("nan")

    n_agente_eps = n_eps * N_AGENTES
    return {
        "configuracion":        etiqueta,
        "politica":             politica,
        "cbf":                  "ON" if cbf else "OFF",
        "episodios":            n_eps,
        "cobertura_media":      round(float(np.mean(cob)), 4),
        "cobertura_std":        round(float(np.std(cob)), 4),
        "atascos":              int(atas.sum()),
        "agente_episodios":     n_agente_eps,
        "atascos_pct":          round(100.0 * atas.sum() / n_agente_eps, 1),
        "colisiones_015_media": round(float(np.mean(c015)), 3),
        "colisiones_015_pct_eps": round(100.0 * float(np.mean(c015 > 0)), 1),
        "colisiones_022_media": round(float(np.mean(c022)), 3),
        "d_min_pared_min":      round(min(dists), 4) if dists else -1.0,
        "d_min_pared_media":    round(float(np.mean(dists)), 4) if dists else -1.0,
        "cbf_frac_intervenida": round(frac_media, 3),
        "corr_frac_vs_atascos": (round(corr, 3) if corr == corr else ""),
        "archivo_origen":       archivo,
    }


def main() -> None:
    """Genera la tabla consolidada en CSV y TXT."""
    _SALIDA.mkdir(parents=True, exist_ok=True)

    print("Consolidando lotes de Webots (5 agentes, 18 semillas)...")
    filas = [f for f in (agregar(*c) for c in CONFIGS) if f is not None]
    if not filas:
        print("No se encontró ningún lote.")
        return

    ruta_csv = _SALIDA / "tabla_final_webots.csv"
    with open(ruta_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    print(f"CSV → {ruta_csv}")

    # Orden de presentación: por tasa de atascos (mejor primero).
    ordenadas = sorted(filas, key=lambda r: float(r["atascos_pct"]))

    L: List[str] = []
    L.append("TABLA CONSOLIDADA — configuraciones evaluadas en Webots")
    L.append("5 agentes con física real · 18 semillas (420000-420017)")
    L.append("Arquitectura: 5 × controlador_agente + 1 coordinador (supervisor),")
    L.append("Emitter/Receiver canales 1 (poses, cada tick) / 2 (acciones, cada")
    L.append("10 ticks). deterministic=True en todas.")
    L.append("=" * 78)
    L.append("")
    L.append(f"{'configuración':<22s} {'cobertura':>16s} {'atascos':>14s} "
             f"{'col_015':>15s} {'d_min pared':>12s} {'CBF int.':>9s}")
    L.append("-" * 96)
    for r in ordenadas:
        L.append(
            f"{r['configuracion']:<22s} "
            f"{r['cobertura_media']:8.4f} ± {r['cobertura_std']:.4f} "
            f"{r['atascos']:5d}/{r['agente_episodios']:<3d} "
            f"({r['atascos_pct']:4.1f}%) "
            f"{r['colisiones_015_media']:6.3f} ({r['colisiones_015_pct_eps']:4.1f}%) "
            f"{r['d_min_pared_media']:12.4f} "
            f"{r['cbf_frac_intervenida']:9.3f}"
        )
    L.append("")
    L.append("COLUMNAS")
    L.append("  cobertura   : cobertura AoI final (media ± desv. sobre 18 eps).")
    L.append("  atascos     : agente-episodios con atasco / total. Detector:")
    L.append("                ‖Δpos‖<1 mm y |Δθ|<0.5° por 20 decisiones (2.0 s).")
    L.append("  col_015     : pares únicos a <0.15 m entre centros por episodio,")
    L.append("                y % de episodios con ≥1. 0.15 m = CONTACTO FÍSICO")
    L.append("                de los chasis (radio 0.075 m c/u) y es el D_SAFE")
    L.append("                del env — la columna comparable con todas las")
    L.append("                métricas previas (experimentos A-D y sanidad).")
    L.append("  d_min pared : distancia mínima del centro a una pared, promediada")
    L.append("                sobre agente-episodios. <0.075 implica contacto.")
    L.append("  CBF int.    : fracción de pasos-agente en que el filtro modificó")
    L.append("                la acción (0 si el filtro está desactivado).")
    L.append("")
    L.append("CONFIGURACIÓN FINAL ADOPTADA: v2 sanidad + CBF")
    L.append("  Única con CERO colisiones en ambos umbrales sobre las 18")
    L.append("  semillas, menor tasa de atascos (43.3%) y mayor cobertura")
    L.append("  (0.3199). Ninguna de las tres alternativas posteriores (v3 con")
    L.append("  radio, v3+CBF, v4 con contacto rígido) la superó.")
    L.append("")
    L.append("CRITERIO OPERATIVO — conflicto política-filtro")
    L.append("  La fracción intervenida por el CBF predice la tasa de atascos:")
    for r in filas:
        if r["corr_frac_vs_atascos"] != "":
            L.append(f"    {r['configuracion']:<22s} r = "
                     f"{r['corr_frac_vs_atascos']:+.3f}  "
                     f"(frac media {r['cbf_frac_intervenida']:.3f})")
    L.append("  Umbral práctico: si al activar el CBF la fracción intervenida")
    L.append("  supera ~0.5, política y filtro están en conflicto y los atascos")
    L.append("  serán altos. Es un test barato (un lote de 3 min) para descartar")
    L.append("  candidatos sin correr experimentos largos.")
    L.append("")
    L.append("REFERENCIAS DE CONTROL (Python, mismas 18 semillas)")
    L.append("  v2 sanidad, bordes bloqueantes : cobertura 0.4426")
    L.append("  v3 radio λ=0                   : cobertura 0.5114 · anillo 0.4565")
    L.append("  v4 contacto rígido             : cobertura 0.2279 · bloqueo 0.6869")
    L.append("  Ojo: cada versión se evalúa en SU propia dinámica de borde, así")
    L.append("  que las coberturas de Python NO son comparables entre versiones.")
    L.append("  La comparación limpia es esta tabla, donde las cinco corren en")
    L.append("  la MISMA física de Webots.")

    ruta_txt = _SALIDA / "tabla_final_webots.txt"
    ruta_txt.write_text("\n".join(L), encoding="utf-8")
    print(f"TXT → {ruta_txt}\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
