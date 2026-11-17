"""
analizar_sesion_demo.py
=======================
Resumen de una sesión de laboratorio de la demo del obstáculo móvil (L1 o
L2), con el criterio FIJADO ANTES de la sesión (`tesis/PROTOCOLO_L0_L2.md`).
Sólo lee: los CSV que escribió `demo_obstaculo_movil.sesion_demo`
(`<fecha>_<modo>_tomas.csv`, `_decisiones.csv`, `_obstaculo.csv`) y escribe
`<prefijo>_resumen.txt` y `<prefijo>_distancias.png` junto a ellos.

Dos validez, separadas:
  · de la MEDICIÓN: la toma corrió completa por el lazo del laboratorio
    (`_correr_episodio`, todas sus reglas) — `valido`.
  · de la DEMO: válida Y sin intervención del freno de respaldo Y ningún
    agente a < 0.15 m del obstáculo Y (L2) el obstáculo recorrió al menos la
    mitad de lo comandado — `valido_demo`.
Métrica principal: distancia mínima agente–obstáculo por toma, entre
centros, medida por el mocap a 10 Hz (`d_min_obst_medida`). Informa además
las REGLAS DE PARADA que se dispararon (y qué respondió el operador) y los
contactos en tomas no válidas para la medición.

    python analizar_sesion_demo.py <CSV de tomas> [<CSV de tomas> ...]

Con varios CSV (una sesión reanudada con `--intento-inicial`) los junta en
un solo resumen, `<prefijo del primero>_combinado_resumen.txt`.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Union

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker

UMBRAL_CONTACTO_M = 0.15
ADVERTENCIA_M = 0.185
AZUL, GRIS, CRITICO, TINTA, TINTA_2, GRILLA = (
    "#2a78d6", "#a3a29c", "#c62828", "#0b0b0b", "#52514e", "#e4e3df")


def _f(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def resumir(rutas: Union[Path, Sequence[Path]]) -> Dict[str, Any]:
    rutas = [Path(rutas)] if isinstance(rutas, (str, Path)) else [Path(r) for r in rutas]
    tomas: List[Dict[str, Any]] = []
    for ruta in rutas:
        with open(ruta, newline="", encoding="utf-8") as fh:
            tomas.extend(csv.DictReader(fh))
    ruta_tomas = rutas[0]
    # En orden de toma (una sesión reanudada sigue la numeración).
    tomas.sort(key=lambda t: _f(t.get("toma")))
    modos = sorted({t.get("modo") for t in tomas if t.get("modo")})
    numeros = [t.get("toma") for t in tomas]
    repetidas = sorted({n for n in numeros if numeros.count(n) > 1})
    corridas = [t for t in tomas if t.get("decisiones") not in (None, "")]
    validas = [t for t in corridas if int(_f(t.get("valido", 0)) or 0) == 1]
    demo = [t for t in validas if int(_f(t.get("valido_demo", 0)) or 0) == 1]
    con_freno = [t for t in corridas if int(_f(t.get("frenos", 0)) or 0) > 0]
    d_val = sorted(_f(t["d_min_obst_medida"]) for t in validas
                   if math.isfinite(_f(t.get("d_min_obst_medida"))))
    lineas: List[str] = []
    lineas.append("Sesión: " + " + ".join(r.name for r in rutas))
    if repetidas:
        lineas.append(f"⚠ números de toma repetidos entre archivos: {repetidas} "
                      f"(se cuentan todas; revisar)")
    if len(modos) > 1:
        lineas.append(f"⚠ los CSV mezclan modos: {modos}")
    lineas.append(f"Intentos: {len(tomas)} · corridos: {len(corridas)} · "
                  f"sin arrancar (colocación): {len(tomas) - len(corridas)}")
    lineas.append(f"VALIDEZ DE LA MEDICIÓN (lazo completo): {len(validas)}/{len(corridas)}")
    for t in corridas:
        if t not in validas:
            lineas.append(f"  ✘ toma {t.get('toma')}: {t.get('motivo')}")
    lineas.append(f"VALIDEZ DE LA DEMO (válida y sin freno, sin contacto, "
                  f"obstáculo en marcha): {len(demo)}/{len(validas)}")
    for t in validas:
        if t not in demo:
            lineas.append(f"  · toma {t.get('toma')}: {t.get('motivo_demo')}")
    lineas.append(f"INTERVENCIONES DEL FRENO DE RESPALDO: {len(con_freno)} toma(s)"
                  + "".join(f"\n  · toma {t.get('toma')}: {t.get('frenos_detalle')}"
                            for t in con_freno))
    # Todas las filas: una parada de la COLOCACIÓN no tiene decisiones.
    paradas = [t for t in tomas if t.get("regla_parada")]
    lineas.append(f"REGLAS DE PARADA DISPARADAS: {len(paradas)}"
                  + "".join(f"\n  · toma {t.get('toma')}: {t.get('regla_parada')} "
                            f"→ {t.get('parada_respuesta') or 'sin respuesta'}"
                            for t in paradas))
    contacto_invalidas = [t for t in corridas if t not in validas
                          and _f(t.get("d_min_obst_medida")) < UMBRAL_CONTACTO_M]
    if contacto_invalidas:
        lineas.append("⚠ CONTACTO EN TOMAS NO VÁLIDAS PARA LA MEDICIÓN: "
                      + ", ".join(f"toma {t.get('toma')} "
                                  f"({_f(t.get('d_min_obst_medida')):.3f} m)"
                                  for t in contacto_invalidas))
    if d_val:
        lineas.append(f"MÉTRICA PRINCIPAL — distancia mínima agente–obstáculo "
                      f"(10 Hz), tomas válidas (n = {len(d_val)}): "
                      f"mín {d_val[0]:.4f} · mediana {statistics.median(d_val):.4f} "
                      f"· máx {d_val[-1]:.4f} m")
        lineas.append(f"  < {ADVERTENCIA_M} m: {sum(1 for d in d_val if d < ADVERTENCIA_M)}"
                      f" · < {UMBRAL_CONTACTO_M} m (contacto): "
                      f"{sum(1 for d in d_val if d < UMBRAL_CONTACTO_M)}")
    lineas.append("")
    lineas.append(f"{'toma':>4} {'válida':>6} {'demo':>4} {'d_min (m)':>9} "
                  f"{'frenos':>6} {'recorrido obst (m)':>18} motivo")
    for t in tomas:
        lineas.append(f"{t.get('toma', ''):>4} {t.get('valido', ''):>6} "
                      f"{t.get('valido_demo', ''):>4} "
                      f"{_f(t.get('d_min_obst_medida')):>9.4f} "
                      f"{t.get('frenos', ''):>6} "
                      f"{_f(t.get('obst_recorrido_m')):>18.2f} "
                      f"{(t.get('motivo') or t.get('motivo_demo') or '')[:70]}")
    texto = "\n".join(lineas) + "\n"
    prefijo = str(ruta_tomas).replace("_tomas.csv", "").replace(".csv", "")
    if len(rutas) > 1:
        prefijo += "_combinado"
    Path(prefijo + "_resumen.txt").write_bytes(texto.encode("utf-8"))
    print(texto)
    # Figura: distancia mínima por toma
    if corridas:
        fig, eje = plt.subplots(figsize=(6.4, 3.2))
        xs = [int(_f(t["toma"])) for t in corridas]
        ys = [_f(t.get("d_min_obst_medida")) for t in corridas]
        for sel, color, rotulo in ((True, AZUL, "válida para la demo"),
                                   (False, GRIS, "no válida para la demo")):
            pares = [(x, y) for x, y, t in zip(xs, ys, corridas) if (t in demo) == sel]
            if pares:
                eje.scatter(*zip(*pares), c=color, s=40, zorder=3,
                            edgecolors="white", label=rotulo)
        eje.axhline(UMBRAL_CONTACTO_M, color=CRITICO, lw=1.2)
        eje.axhline(ADVERTENCIA_M, color=TINTA_2, lw=1.0, ls=(0, (4, 3)))
        eje.legend(loc="upper right", fontsize=7.5, frameon=False, ncol=2)
        eje.set_xlabel("toma", color=TINTA, fontsize=9)
        eje.set_ylabel("distancia mínima (m)", color=TINTA, fontsize=9)
        eje.set_ylim(0.0, max(0.5, max((y for y in ys if math.isfinite(y)),
                                       default=0.5) + 0.05))
        eje.grid(axis="y", color=GRILLA, lw=0.8, zorder=0)
        for lado in ("top", "right"):
            eje.spines[lado].set_visible(False)
        eje.tick_params(colors=TINTA_2, labelsize=8)
        eje.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
            lambda v, _p: f"{v:.2f}".replace(".", ",")))
        eje.set_xlim(min(xs) - 0.6, max(xs) + 0.6)
        eje.text(min(xs) - 0.5, UMBRAL_CONTACTO_M - 0.008, "0,15 contacto",
                 color=CRITICO, fontsize=7.5, va="top")
        eje.text(min(xs) - 0.5, ADVERTENCIA_M + 0.008, "0,185",
                 color=TINTA_2, fontsize=7.5, va="bottom")
        fig.tight_layout()
        fig.savefig(prefijo + "_distancias.png", dpi=300)
    return {"validas": len(validas), "corridas": len(corridas),
            "validas_demo": len(demo), "con_freno": len(con_freno),
            "d_min": d_val[0] if d_val else float("nan")}


if __name__ == "__main__":
    resumir([Path(a) for a in sys.argv[1:]])
