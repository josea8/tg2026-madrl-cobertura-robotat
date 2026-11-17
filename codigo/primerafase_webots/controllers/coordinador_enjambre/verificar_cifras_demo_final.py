"""
verificar_cifras_demo_final.py
==============================
DEMOSTRACIÓN, NO CITABLE. Recalcula desde los crudos de las pruebas del
simulador cada cifra del reporte de la demostración final y comprueba que
el texto del reporte la diga igual. Corre dentro del zip de datos o desde la
carpeta del coordinador:

    python -B verificar_cifras_demo_final.py --pruebas <pruebas 1-6> --p7 <prueba 7 intercalada>
        [--diag <diagnóstico del panel>] --reporte <REPORTE.md>

Cada cifra se busca en el reporte con el formato con que se escribe. Sale 0
si todas están y coinciden; 1 si falta o difiere alguna.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def _leer(ruta: Path) -> List[Dict[str, str]]:
    with open(ruta, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _uno(carpeta: Path, patron: str) -> Path:
    r = sorted(carpeta.glob(patron))
    if len(r) != 1:
        raise SystemExit(f"esperaba 1 archivo {patron} en {carpeta}, hay {len(r)}")
    return r[0]


def cifras(pruebas: Path, p7: Path, diag: Path = None) -> List[Tuple[str, str]]:
    """(descripción, texto exacto que tiene que aparecer en el reporte)."""
    c: List[Tuple[str, str]] = []
    # Prueba 1: objetivos 2 × 100
    ep = _leer(_uno(pruebas / "p1_objetivos", "*_demo-objetivos_episodios.csv"))
    validos = sum(e["valido"] == "1" for e in ep)
    c.append(("p1 válidos", f"{validos}/{len(ep)} episodios válidos"))
    for k, e in enumerate(ep, 1):
        # El ciclo p95 de las pruebas 1 a 6 NO se cita: corrieron a batería.
        c.append((f"p1 cobertura ep {k}", f"{float(e['cobertura_aoi']):.4f}"))
    c.append(("p1 columnas episodios", f"{len(next(csv.reader(open(_uno(pruebas / 'p1_objetivos', '*_episodios.csv'), encoding='utf-8'))))} columnas"))
    # Prueba 2: mejorada 2 × 100
    tm = _leer(_uno(pruebas / "p2_mejorada", "*_demo-mejorada_tomas.csv"))
    c.append(("p2 válidas", f"{sum(t['valido'] == '1' for t in tm)}/{len(tm)} tomas válidas"))
    c.append(("p2 válidas video", f"{sum(t['valido_demo'] == '1' for t in tm)}/{len(tm)} para el video"))
    c.append(("p2 frenos", f"{sum(int(t['frenos'] or 0) for t in tm)} frenos"))
    dmin = min(float(t["d_min_obst_medida"]) for t in tm)
    c.append(("p2 d_min obstáculo", f"{dmin:.3f} m"))
    for k, t in enumerate(tm, 1):
        frac = float(t["obst_recorrido_m"]) / float(t["obst_recorrido_comandado_m"])
        c.append((f"p2 recorrido del 4, toma {k}", f"{100 * frac:.0f} %"))
    # Prueba 7 intercalada (enchufada, PC limpia): pareada por ronda
    res: Dict[str, List[float]] = {}
    for cond in ("sin_gui", "publica_sin_panel", "con_panel"):
        res[cond] = []
        for r in sorted(p7.glob(f"p7i_r*_{cond}")):
            fila = _leer(_uno(r, "*_demo-objetivos_episodios.csv"))[0]
            res[cond].append(float(fila["ciclo_p95_ms"]))
        c.append((f"p7 {cond} media", f"{statistics.mean(res[cond]):.2f} ms"))
    d_panel = [a - b for a, b in zip(res["con_panel"], res["sin_gui"])]
    d_pub = [a - b for a, b in zip(res["publica_sin_panel"], res["sin_gui"])]
    c.append(("p7 rondas", f"{len(d_panel)} rondas"))
    c.append(("p7 panel − sin GUI", f"{statistics.mean(d_panel):+.2f} ms"))
    c.append(("p7 panel − sin GUI, mín", f"{min(d_panel):+.2f}"))
    c.append(("p7 panel − sin GUI, máx", f"{max(d_panel):+.2f}"))
    c.append(("p7 publica − sin GUI", f"{statistics.mean(d_pub):+.2f} ms"))
    # Diagnóstico: diferencias pareadas contra A en cada corrida
    if diag is not None:
        import json
        for archivo in ("separar_ABCDE.json", "separar_AGH.json"):
            d = json.loads((diag / archivo).read_text(encoding="utf-8"))
            for cond, v in d.items():
                if cond == "A_sin_gui":
                    continue
                dif = statistics.mean(x - a for x, a in zip(v, d["A_sin_gui"]))
                c.append((f"diag {archivo} {cond} − A", f"{dif:+.2f} ms"))
    return c


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pruebas", required=True)
    ap.add_argument("--p7", required=True, help="carpeta de la prueba 7 intercalada")
    ap.add_argument("--diag", default=None, help="carpeta del diagnóstico del panel")
    ap.add_argument("--reporte", required=True)
    a = ap.parse_args(argv)
    texto = Path(a.reporte).read_text(encoding="utf-8")
    fallas = 0
    lista = cifras(Path(a.pruebas), Path(a.p7),
                   Path(a.diag) if a.diag else None)
    for desc, valor in lista:
        ok = valor in texto
        fallas += not ok
        print(f"  {'OK ' if ok else 'FALTA'}  {desc}: «{valor}»")
    print(f"{len(lista) - fallas}/{len(lista)} cifras verificadas")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
