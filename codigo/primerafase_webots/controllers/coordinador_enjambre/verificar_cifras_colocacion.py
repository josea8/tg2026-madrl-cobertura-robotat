"""
verificar_cifras_colocacion.py
==============================
Recalcula desde los datos CRUDOS cada cifra del reporte de la colocación
automática de la demo del obstáculo (`REPORTE_2026-10-07_colocacion_automatica.md`)
y la compara con el valor TAL COMO APARECE en el texto. Una línea por cifra
(SÍ / NO); código 1 si alguna no coincide.

    python verificar_cifras_colocacion.py <carpeta con los ensayo_*_auto_*> <log de la suite>

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

#: Los ensayos del reporte, por su rótulo.
ENSAYOS = {
    "primero": "ensayo_L2_auto_20261007_120644",      # falso NO FRENA
    "intermedio": "ensayo_L2_auto_20261007_121157",   # antes de la revisión
    "L2_085": "ensayo_L2_auto_20261007_125313",
    "L1_085": "ensayo_L1_auto_20261007_130916",
    "L2_045": "ensayo_L2_auto_20261007_131335",
    "L1_045": None,                                   # se completa abajo
}


def _f(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def cifras_de(carpeta: Path) -> Dict[str, Any]:
    r = json.loads((carpeta / "resumen_ensayo.json").read_text(encoding="utf-8"))
    ruta = sorted(carpeta.glob("*_tomas*.csv"))[-1]
    with open(ruta, newline="", encoding="utf-8") as fh:
        tomas = list(csv.DictReader(fh))
    corridas = [t for t in tomas if t.get("decisiones") not in (None, "")]
    col_obst = [_f(t.get("col_d_min_obst_m")) for t in tomas
                if t.get("col_d_min_obst_m") not in (None, "")]
    col_pares = [_f(t.get("col_d_min_pares_m")) for t in tomas
                 if t.get("col_d_min_pares_m") not in (None, "")]
    col_t = [_f(t.get("col_t_s")) for t in tomas if t.get("col_t_s") not in (None, "")]
    # Agente–agente medido DURANTE LAS TOMAS (CSV de decisiones, 10 Hz).
    import math
    from collections import defaultdict
    por: Dict[Tuple[str, str], Dict[str, Tuple[float, float]]] = defaultdict(dict)
    with open(sorted(carpeta.glob("*_decisiones*.csv"))[-1], newline="",
              encoding="utf-8") as fh:
        for f in csv.DictReader(fh):
            por[(f["episodio"], f["paso"])][f["agente"]] = (
                float(f["pose_env_x"]), float(f["pose_env_y"]))
    pares_tomas = min((math.dist(ag[a], ag[b]) for ag in por.values()
                       for a in ag for b in ag if a < b), default=float("nan"))
    return {
        "veredicto": r["veredicto"],
        "intentos": len(tomas),
        "validas_demo": sum(1 for t in tomas if t.get("valido_demo") == "1"),
        "frenos": sum(1 for t in corridas if int(_f(t.get("frenos")) or 0) > 0),
        "paradas": sum(1 for t in tomas if t.get("regla_parada")),
        "verdad_obst": r["verdad_d_min_obst_m"],
        "verdad_pares": r["verdad_d_min_pares_m"],
        "a_mano": r["obstaculo_a_mano"],
        "retenciones": r["retenciones_zona_muerta"],
        "reintentos": sum(int(_f(t.get("col_reintentos")) or 0) for t in tomas),
        "col_obst_min": min(col_obst) if col_obst else float("nan"),
        "col_pares_min": min(col_pares) if col_pares else float("nan"),
        "col_t_min": min(col_t) if col_t else float("nan"),
        "col_t_max": max(col_t) if col_t else float("nan"),
        "toma_d_min": min((_f(t.get("d_min_obst_medida")) for t in corridas
                           if t.get("valido") == "1"), default=float("nan")),
        "duracion_s": r["duracion_s"],
        "pares_tomas": pares_tomas,
        "tau_agentes": r["tau_agentes"],
        "tau_obstaculo": r["tau_obstaculo"],
        "motivo_parada": next((t.get("regla_parada") for t in tomas
                               if t.get("regla_parada")), ""),
    }


#: (descripción, ensayo, clave, formato, valor en el reporte)
CIFRAS: List[Tuple[str, str, str, str, str]] = []


def _agregar(ens: str, filas: List[Tuple[str, str, str]]) -> None:
    for clave, fmt, valor in filas:
        CIFRAS.append((f"{ens}: {clave}", ens, clave, fmt, valor))


def _llenar() -> None:
    """Las cifras del reporte, con el formato con que se escribieron."""
    _agregar("primero", [("veredicto", "{}", "DETENIDA"),
                         ("intentos", "{}", "2"),
                         ("motivo_parada", "{}", "ABORTO POR EL OBSTÁCULO: el "
                          "obstáculo NO FRENA: se movió 1.9 cm durante la "
                          "colocación (v medida 0.046 m/s), debía estar quieto")])
    _agregar("intermedio", [("validas_demo", "{}", "10"), ("intentos", "{}", "11"),
                            ("frenos", "{}", "1"), ("toma_d_min", "{:.4f}", "0.2093"),
                            ("verdad_pares", "{:.4f}", "0.1693"),
                            ("retenciones", "{}", "1299")])
    for ens, (inten, val, reint, v_obst, v_par, ret, t0, t1) in {
            "L2_085": (10, 10, 3, "0.3052", "0.1763", 800, "26", "45"),
            "L1_085": (3, 3, 0, "0.3907", "0.1582", 0, "32", "36"),
            "L2_045": (11, 10, 7, "0.3055", "0.2154", 14399, "14", "44"),
            "L1_045": (3, 3, 4, "0.3257", "0.2468", 2400, "20", "29")}.items():
        _agregar(ens, [("veredicto", "{}", "OK"), ("intentos", "{}", str(inten)),
                       ("validas_demo", "{}", str(val)), ("frenos", "{}", "0"),
                       ("paradas", "{}", "0"), ("a_mano", "{}", "0"),
                       ("reintentos", "{}", str(reint)),
                       ("verdad_obst", "{:.4f}", v_obst),
                       ("verdad_pares", "{:.4f}", v_par),
                       ("retenciones", "{}", str(ret)),
                       ("col_t_min", "{:.0f}", t0), ("col_t_max", "{:.0f}", t1)])
    _agregar("L1_085", [("col_pares_min", "{:.4f}", "0.1582"),
                        ("pares_tomas", "{:.4f}", "0.2264")])
    for ens, val in (("L2_085", "0.2499"), ("L2_045", "0.2505"),
                     ("L1_045", "0.2604")):
        _agregar(ens, [("pares_tomas", "{:.4f}", val)])
    _agregar("suite", [("pruebas", "{}", "102"), ("ok", "{}", "OK")])


def main() -> int:
    raiz = Path(sys.argv[1])
    log = Path(sys.argv[2])
    l1_045 = [c for c in sorted(raiz.glob("ensayo_L1_auto_*"))
              if c.name != ENSAYOS["L1_085"]]
    ENSAYOS["L1_045"] = l1_045[-1].name if l1_045 else "ensayo_L1_auto_inexistente"
    datos = {k: cifras_de(raiz / v) for k, v in ENSAYOS.items()}
    texto = log.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"Ran (\d+) tests", texto)
    suite = {"pruebas": int(m.group(1)) if m else -1,
             "ok": "OK" if re.search(r"^OK", texto, re.M) else "FALLA"}
    _llenar()
    malas = 0
    for desc, ens, clave, fmt, reportado in CIFRAS:
        fuente = suite if ens == "suite" else datos[ens]
        try:
            calculado = fmt.format(fuente[clave])
        except (KeyError, TypeError, ValueError) as exc:
            calculado = f"ERROR {type(exc).__name__}: {exc}"
        ok = calculado == reportado
        malas += not ok
        print(f"{'SÍ' if ok else 'NO'}  {desc:<52} reporte {reportado:>12}  "
              f"calculado {calculado:>12}")
    print(f"\n{len(CIFRAS) - malas}/{len(CIFRAS)} cifras coinciden.")
    return 1 if malas else 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())
