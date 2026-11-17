"""
ensayo_sesion_simulador.py
==========================
Ensayo, contra el simulador, de una sesión L1 o L2 de la demo del obstáculo
móvil por el MISMO camino que en el laboratorio (`sesion_demo`, lazo de
evaluación, freno de respaldo activo), con la colocación AUTOMÁTICA
(2026-10-07): los robots se colocan SOLOS, sin teletransporte. Sucesor de
`ensayo_l2_simulador.py`, que se conserva tal cual (sus ensayos del 02 y
03-10 salieron de él).

  · el obstáculo es el robot 4 (marcador 4), como en el laboratorio;
  · simulador con ZONA MUERTA de rueda desde parado y retardo por robot
    (agentes `--tau`, obstáculo `--tau-obstaculo`);
  · `MonitorVerdad` (200 Hz) durante TODA la sesión, colocaciones incluidas:
    distancia mínima continua agente–obstáculo y agente–agente en la VERDAD
    del simulador. Criterio de la propuesta (§8): > 0.15 m;
  · el "operador" contesta los Enter y, si la sesión pide colocar el
    obstáculo A MANO (fuera de su envolvente; la Fase A todavía no está), lo
    pone en su punto y lo cuenta. Una regla de parada se contesta con Enter
    (la sesión se detiene: un ensayo no la puede revisar).

    python ensayo_sesion_simulador.py --modo L2 --tomas 10 --tau 0.85 --tau-obstaculo 0.85

Salida: `resultados_demo_obstaculo/ensayo_<modo>_auto_<fecha>/` (CSV de la
sesión, `resumen_ensayo.json` y el resumen de `analizar_sesion_demo.py`).

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import argparse
import json
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
    ap.add_argument("--modo", choices=("L1", "L2"), required=True)
    ap.add_argument("--tomas", type=int, default=10)
    ap.add_argument("--tau", type=float, default=0.45, help="agentes")
    ap.add_argument("--tau-obstaculo", type=float, default=0.85)
    ap.add_argument("--robot-obstaculo", type=int, default=4)
    ap.add_argument("--sin-zona-muerta", action="store_true")
    ap.add_argument("--puerto", type=int, default=27200)
    args = ap.parse_args()

    cfg.activar_simulador_local(puerto_poses=args.puerto,
                                puerto_base=args.puerto + 100)
    import colocacion_con_obstaculo as C
    import demo_obstaculo_movil as demo
    import sesion_robotat as ses
    from analizar_sesion_demo import resumir
    from correr_fase0_obstaculo import MonitorVerdad
    from simulador_para_colocacion import (SimuladorZonaMuerta,
                                           fallas_con_retardo_por_robot)
    from simulador_robotat import SimuladorRobotat

    rid_o = int(args.robot_obstaculo)
    mid_o = cfg.marcador_fijo_de_robot(rid_o)
    salida = demo.DIR_SALIDA_DEMO / (f"ensayo_{args.modo}_auto_"
                                     f"{datetime.now():%Y%m%d_%H%M%S}")
    salida.mkdir(parents=True, exist_ok=True)
    demo.DIR_SALIDA_DEMO = salida

    robots = [cfg.MAPEO_AGENTES[i].id_robot for i in range(5)]
    mapeo = {r: cfg.MAPEO_AGENTES[i].id_marcador for i, r in enumerate(robots)}
    mapeo[rid_o] = mid_o
    tx, ty = cfg.TRASLACION_X_M, cfg.TRASLACION_Y_M
    # Arranque: los agentes en las esquinas y el obstáculo donde termina
    # la etapa anterior (L1: el centro; L2: su punto de (1.5, 0.9), +x).
    agentes = {robots[0]: (0.5, 0.5, 0.3), robots[1]: (2.5, 0.5, 2.0),
               robots[2]: (0.5, 2.5, -1.0), robots[3]: (2.5, 2.5, -2.5),
               robots[4]: (1.5, 2.6, 0.0)}
    if args.modo == "L1":
        obst = (1.5, 1.5, 0.3)
    else:
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        obst = (float(p0[0]), float(p0[1]), float(r0))
    inicial = {r: (x - tx, y - ty, th) for r, (x, y, th) in agentes.items()}
    inicial[rid_o] = (obst[0] - tx, obst[1] - ty, obst[2])
    fallas = fallas_con_retardo_por_robot({rid_o: args.tau_obstaculo}, args.tau)
    clase = SimuladorRobotat if args.sin_zona_muerta else SimuladorZonaMuerta
    sim = clase(mapeo, inicial, fallas, puerto_poses=args.puerto,
                puerto_base=args.puerto + 100)
    sim.iniciar()

    # Lo último que pidió la sesión para el obstáculo (para el "operador").
    actual: Dict[str, Any] = {}
    _orig = C.objetivo_obstaculo

    def objetivo(modo, pose_o, semilla):
        actual["r"] = _orig(modo, pose_o, semilla)
        return actual["r"]
    C.objetivo_obstaculo = objetivo
    cuenta = {"manos": 0, "paradas": 0, "enters": 0}

    def operador(mensaje: str) -> str:
        if "¿Seguir con la sesión?" in mensaje:
            cuenta["paradas"] += 1
            return ""
        cuenta["enters"] += 1
        if "Corregí lo de arriba" in mensaje and "r" in actual:
            o, rumbo, _origen = actual["r"]
            with sim._lock:
                e = sim.robots[rid_o]
                e.x, e.y = float(o[0]) - tx, float(o[1]) - ty
                e.yaw = rumbo if rumbo is not None else 0.3
            cuenta["manos"] += 1
            time.sleep(0.4)
        return ""

    mon = MonitorVerdad(sim, robots, rid_o)
    ctx = ses.Contexto(sesion=f"ensayo_{args.modo}_auto", id_robot=rid_o,
                       marcador=mid_o, simulador=True, preguntar=operador)
    t0 = time.perf_counter()
    mon.iniciar()
    try:
        r = demo.sesion_demo(ctx, args.modo, tomas=args.tomas,
                             intentos_max=2 * args.tomas,
                             id_robot_obstaculo=rid_o,
                             id_marcador_obstaculo=mid_o, colocacion="auto")
    finally:
        mon.detener()
        sim.detener()
    dur = time.perf_counter() - t0
    resumen = {
        "modo": args.modo, "tomas": args.tomas, "tau_agentes": args.tau,
        "tau_obstaculo": args.tau_obstaculo, "robot_obstaculo": rid_o,
        "zona_muerta": not args.sin_zona_muerta,
        "veredicto": r["veredicto"], "detalle": r["detalle"],
        "verdad_d_min_obst_m": min(mon.d_min_obst),
        "verdad_d_min_pares_m": mon.d_min_pares,
        "obstaculo_a_mano": cuenta["manos"], "paradas": cuenta["paradas"],
        "enters": cuenta["enters"], "duracion_s": dur,
        "retenciones_zona_muerta": (sum(getattr(sim, "retenciones", {}).values())
                                    if hasattr(sim, "retenciones") else None),
    }
    (salida / "resumen_ensayo.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[ensayo] {r['veredicto']} — {r['detalle']} · verdad: mín "
          f"agente–obstáculo {resumen['verdad_d_min_obst_m']:.4f} m, "
          f"agente–agente {resumen['verdad_d_min_pares_m']:.4f} m · "
          f"obstáculo a mano {cuenta['manos']} · {dur:.0f} s")
    tomas_csv = sorted(salida.glob(f"*_{args.modo}_tomas*.csv"))[-1]
    resumir(tomas_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
