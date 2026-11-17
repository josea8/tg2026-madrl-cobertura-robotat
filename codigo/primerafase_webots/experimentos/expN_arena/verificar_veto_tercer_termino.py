"""
verificar_veto_tercer_termino.py
================================
Verificación del PUENTE del Exp N: la detección de tres términos (desplegada)
y la de dos (factorial 2×2) dieron resultados idénticos bit a bit en las 18
semillas. Antes de afirmar que el +0,135 del factorial describe el escape
desplegado, se verifica que no sea un defecto de implementación: se cuenta
cuántas veces el tercer término ("el CBF intervino en la decisión anterior")
VETA una detección que la versión de dos términos sí habría contado.

Si los vetos son cero, la igualdad es un hecho del sistema (en Python, estar
quieto con h_min < 0,03 implica que el filtro intervino) y no un error.

Corre la configuración (b) de tres términos, n=5, W ∈ {3,0; 2,7}, 100 semillas,
y además verifica que la cobertura coincide con el CSV principal (el
instrumento no debe alterar la dinámica).

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import correr_experimento_N as N


class GestorConConteo(N.GestorEscape):
    """GestorEscape que cuenta los vetos del tercer término sin alterar nada."""

    vetos_totales: int = 0
    evaluaciones_dos: int = 0   # veces que la condición de dos términos se cumplió

    def gestionar(self, i, poses, u_nom):
        if self.estado[i] == 0 and self.pose_previa is not None:
            _, h_min = self.normales_activas(i, poses)
            desp = float(np.linalg.norm(poses[i, :2] - self.pose_previa[i, :2]))
            if desp < N.ESC_UMBRAL_DESPLAZAMIENTO and h_min < N.ESC_H_ENTRADA:
                GestorConConteo.evaluaciones_dos += 1
                if not self.intervino_prev[i]:
                    GestorConConteo.vetos_totales += 1
        return super().gestionar(i, poses, u_nom)


def _tarea(args: Tuple[N.Condicion, int]) -> Tuple[str, int, float, int, int]:
    cond, s = args
    N.GestorEscape = GestorConConteo        # parche local al proceso
    GestorConConteo.vetos_totales = 0
    GestorConConteo.evaluaciones_dos = 0
    fila = N.correr_episodio(cond, s)
    return (cond.nombre, s, float(fila["cobertura_aoi_final"]),
            GestorConConteo.evaluaciones_dos, GestorConConteo.vetos_totales)


def main() -> None:
    """Cuenta vetos y compara la cobertura con el CSV principal."""
    conds = (N.Condicion("b3_W30_n5", "b", 3.0, 5, "tres"),
             N.Condicion("b3_W27_n5", "b", 2.7, 5, "tres"))
    tareas = [(c, s) for c in conds for s in N.semillas(100)]
    with ProcessPoolExecutor(max_workers=11,
                             initializer=N._inicializar_trabajador) as ex:
        res = list(ex.map(_tarea, tareas, chunksize=1))

    ref: Dict[Tuple[str, int], float] = {}
    with open(N.DIR_SALIDA / "experimento_N_completo.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ref[(r["condicion"], int(r["seed_ep"]))] = float(r["cobertura_aoi_final"])

    L: List[str] = ["VETOS DEL TERCER TÉRMINO — configuración (b), n=5, 100 semillas"]
    for c in conds:
        filas = [r for r in res if r[0] == c.nombre]
        iguales = sum(r[2] == ref[(c.nombre, r[1])] for r in filas)
        ev = sum(r[3] for r in filas)
        ve = sum(r[4] for r in filas)
        eps_veto = sum(r[4] > 0 for r in filas)
        L.append(f"  {c.nombre}: condición de dos términos cumplida {ev} veces "
                 f"(agente-decisión); vetada por el tercero {ve} veces, en "
                 f"{eps_veto}/100 episodios. Cobertura idéntica al CSV "
                 f"principal: {iguales}/100.")
    texto = "\n".join(L) + "\n"
    (N.DIR_SALIDA / "verificacion_veto_tercer_termino.txt").write_bytes(
        texto.encode("utf-8"))
    print(texto)


if __name__ == "__main__":
    main()
