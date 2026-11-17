"""
ensayo_l2_simulador.py
======================
Ensayo, contra `SimuladorRobotat` con 6 robots y 0.45 s de retardo, de la
sesión L2 COMPLETA de la demo del obstáculo móvil, por el MISMO camino que
en el laboratorio (`demo_obstaculo_movil.sesion_demo`, lazo de evaluación,
freno de respaldo activo, colocación manual con la guía), con 10 tomas.

El "operador" es un gancho de `Contexto.preguntar`: antes de cada Enter
teletransporta a los 5 agentes a los blancos de esa toma y al obstáculo a su
punto de arranque (los toma de las mismas funciones que usa la sesión). No es
un resultado: verifica el procedimiento antes de ir al laboratorio.

    python ensayo_l2_simulador.py [--tomas 10] [--tau 0.45]

Salida: `resultados_demo_obstaculo/ensayo_l2_<fecha>/` (CSV de la sesión y el
resumen de `analizar_sesion_demo.py`).

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

_CARPETA = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import config_robotat as cfg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tomas", type=int, default=10)
    ap.add_argument("--tau", type=float, default=0.45)
    args = ap.parse_args()

    cfg.activar_simulador_local(puerto_poses=27000, puerto_base=27100)
    import demo_obstaculo_movil as demo
    import sesion_robotat as ses
    from analizar_sesion_demo import resumir
    from colocacion_autonoma import sortear_rumbos
    from simulador_robotat import FallasSimulador, SimuladorRobotat

    salida = demo.DIR_SALIDA_DEMO / f"ensayo_l2_{datetime.now():%Y%m%d_%H%M%S}"
    salida.mkdir(parents=True, exist_ok=True)
    demo.DIR_SALIDA_DEMO = salida

    robots = [cfg.MAPEO_AGENTES[i].id_robot for i in range(5)]
    mapeo = {r: cfg.MAPEO_AGENTES[i].id_marcador for i, r in enumerate(robots)}
    mapeo[demo.ID_ROBOT_OBSTACULO] = demo.ID_MARCADOR_OBSTACULO
    tx, ty = cfg.TRASLACION_X_M, cfg.TRASLACION_Y_M

    # Lo último que calculó la sesión para la toma en curso.
    actual: Dict[str, Any] = {}
    _arranque = demo.arranque_obstaculo
    _blancos = demo.sortear_blancos_demo

    def arranque(semilla, modo, par=None):
        actual["semilla"] = semilla
        actual["obst"] = _arranque(semilla, modo, par)
        return actual["obst"]

    def blancos(n, semilla, punto, intentos=200):
        actual["blancos"] = _blancos(n, semilla, punto, intentos)
        return actual["blancos"]
    demo.arranque_obstaculo = arranque
    demo.sortear_blancos_demo = blancos

    p_ini, r_ini = demo.punto_del_circulo(-math.pi / 2)
    sim = SimuladorRobotat(
        mapeo,
        {**{r: (0.5 + 0.5 * k - tx, 0.5 - ty, 0.0) for k, r in enumerate(robots)},
         demo.ID_ROBOT_OBSTACULO: (p_ini[0] - tx, p_ini[1] - ty, r_ini)},
        FallasSimulador(retardo_actuacion_s=args.tau),
        puerto_poses=27000, puerto_base=27100)
    sim.iniciar()
    colocaciones = []

    def operador(mensaje: str) -> str:
        if "Colocá los agentes" in mensaje and "blancos" in actual:
            rumbos = sortear_rumbos(5, actual["semilla"])
            objetivo, rumbo = actual["obst"]
            with sim._lock:
                for i, r in enumerate(robots):
                    b = actual["blancos"][i]
                    e = sim.robots[r]
                    e.x, e.y, e.yaw = float(b[0]) - tx, float(b[1]) - ty, rumbos[i]
                    e.rpm_izq = e.rpm_der = e.rpm_izq_ruedas = e.rpm_der_ruedas = 0.0
                    e.en_camino.clear()
                e = sim.robots[demo.ID_ROBOT_OBSTACULO]
                e.x, e.y = float(objetivo[0]) - tx, float(objetivo[1]) - ty
                e.yaw = rumbo if rumbo is not None else 0.3
                e.rpm_izq = e.rpm_der = e.rpm_izq_ruedas = e.rpm_der_ruedas = 0.0
                e.en_camino.clear()
            colocaciones.append(actual["semilla"])
            time.sleep(0.6)
        return ""

    ctx = ses.Contexto(sesion="ensayo_l2", id_robot=demo.ID_ROBOT_OBSTACULO,
                       marcador=demo.ID_MARCADOR_OBSTACULO, simulador=True,
                       preguntar=operador)
    t0 = time.perf_counter()
    try:
        r = demo.sesion_demo(ctx, "L2", tomas=args.tomas,
                             intentos_max=2 * args.tomas)
    finally:
        sim.detener()
    print(f"\n[ensayo] {r['veredicto']} — {r['detalle']} · colocaciones "
          f"{len(colocaciones)} · {time.perf_counter() - t0:.0f} s")
    tomas_csv = sorted(salida.glob("*_L2_tomas*.csv"))[-1]
    resumir(tomas_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
