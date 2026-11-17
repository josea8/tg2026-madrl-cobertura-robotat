"""
ensayo_campana_simulador.py
===========================
Ítem 1e de la campaña L2 (OK de José, 2026-10-08): un ensayo CORTO del modo
campaña contra el simulador, por el MISMO camino que en el laboratorio
(`demo_obstaculo_movil.main` con `--campana`), antes de la primera toma real.

  1. crea la campaña `ensayo` (plataforma simulador, meta corta) con los
     archivos congelados REALES y su sha256;
  2. sesión 1: el "operador" corta con Ctrl+C en el Enter de una colocación
     (la reserva queda interrumpida y su semilla gastada);
  3. sesión 2: reanuda hasta la meta; las semillas siguen sin repetirse;
  4. cierra la campaña con motivo;
  5. AUDITA el registro: libro (reservas, semillas, interrumpidas, aperturas
     y cierres) y columnas de cada toma corrida contra decisiones y traza
     (x0 vs paso 0 ≤ 1 mm, obst_*_med vs traza, decisiones_previas = rampa,
     id_sesion en los tres CSV, robots);
  6. corre `analizar_campana_l2.py --ensayo` con una RÉPLICA FALSA (contrato
     del §9 del plan; brecha sembrada −0.010) para probar el script sobre
     una salida real del modo campaña.

Simulador con zona muerta y retardo por robot (agentes `--tau`, obstáculo
`--tau-obstaculo`), `MonitorVerdad` a 200 Hz durante todo el ensayo.

    python ensayo_campana_simulador.py

Salida: `resultados_demo_obstaculo/ensayo_campana_<fecha>/` (la campaña, los
CSV de las sesiones, `auditoria_registro.json`, la réplica falsa, el
análisis y `resumen_ensayo.json`). No toca `campanas/` del laboratorio.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import argparse
import csv
import functools
import json
import math
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

_CARPETA = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import config_robotat as cfg

NOMBRE = "ensayo"


def _leer(ruta: Path) -> List[Dict[str, str]]:
    with open(ruta, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def auditar(salida: Path, campana: Any) -> Dict[str, Any]:
    """El registro contra el libro, las decisiones y la traza."""
    problemas: List[str] = []
    filas = campana.filas()
    reservas = [(int(f["intento"]), int(f["semilla"])) for f in filas if f["tipo"] == "reserva"]
    if [k for k, _ in reservas] != list(range(1, len(reservas) + 1)):
        problemas.append(f"intentos no consecutivos: {reservas}")
    if any(s != campana.semilla(k) for k, s in reservas):
        problemas.append("semilla fuera de la fórmula")
    if len({s for _, s in reservas}) != len(reservas):
        problemas.append("semillas repetidas")
    res = {int(f["intento"]): f for f in filas if f["tipo"] == "resultado"}
    if sorted(res) != [k for k, _ in reservas]:
        problemas.append("reservas sin resultado o resultados de más")
    aperturas = [f for f in filas if f["tipo"] == "apertura"]
    cierres = [f for f in filas if f["tipo"] == "cierre_sesion"]
    tomas_aud = []
    for nombre in sorted({f["archivo_tomas"] for f in res.values() if f["archivo_tomas"]}):
        tomas = _leer(salida / nombre)
        dec = _leer(salida / nombre.replace("_tomas", "_decisiones"))
        obst = _leer(salida / nombre.replace("_tomas", "_obstaculo"))
        ids = {f.get("id_sesion") for f in tomas + dec + obst}
        if len(ids) != 1 or "" in ids or None in ids:
            problemas.append(f"{nombre}: id_sesion {ids}")
        previas = 0
        for t in tomas:
            if t.get("decisiones") in (None, ""):
                continue
            k = t["toma"]
            err_x0 = 0.0
            for i in range(5):
                d0 = [f for f in dec if f["episodio"] == k and f["agente"] == str(i)
                      and f["paso"] == "0"]
                if len(d0) != 1:
                    problemas.append(f"{nombre} toma {k} a{i}: {len(d0)} filas paso 0")
                    continue
                e = math.hypot(float(t[f"x0_a{i}"]) - float(d0[0]["pose_env_x"]),
                               float(t[f"y0_a{i}"]) - float(d0[0]["pose_env_y"]))
                err_x0 = max(err_x0, e)
                if t[f"robot_a{i}"] != d0[0]["robot"]:
                    problemas.append(f"{nombre} toma {k} a{i}: robot distinto")
            o0 = [f for f in obst if f["toma"] == k and f["paso"] == "0"]
            err_o = (math.hypot(float(t["obst_x0_med"]) - float(o0[0]["x"]),
                                float(t["obst_y0_med"]) - float(o0[0]["y"]))
                     if len(o0) == 1 else float("nan"))
            if err_x0 > 0.001:
                problemas.append(f"{nombre} toma {k}: x0 vs paso 0 = {err_x0:.5f} m")
            if not err_o <= 0.001:
                problemas.append(f"{nombre} toma {k}: obst_med vs traza = {err_o}")
            if int(float(t["decisiones_previas"])) != previas:
                problemas.append(f"{nombre} toma {k}: decisiones_previas "
                                 f"{t['decisiones_previas']} ≠ {previas}")
            if t.get("obst_robot") != "4":
                problemas.append(f"{nombre} toma {k}: obst_robot {t.get('obst_robot')}")
            tomas_aud.append({"archivo": nombre, "toma": int(k), "semilla": t.get("semilla"),
                              "incluida": t.get("incluida"), "err_x0_m": err_x0,
                              "err_obst_m": err_o, "decisiones_previas": t["decisiones_previas"]})
            previas += int(float(t["decisiones"]))
    return {"problemas": problemas, "reservas": reservas,
            "estados": {k: f["estado"] for k, f in res.items()},
            "incluidas": [k for k, f in res.items() if f["incluida"] == "1"],
            "aperturas": len(aperturas),
            "cierres_sesion": [f["motivo"] for f in cierres],
            "tomas": tomas_aud}


def replica_falsa(salida: Path, campana: Any, brecha: float = -0.010) -> Path:
    """Réplica FALSA con el contrato del §9 (sólo para probar el script)."""
    import analizar_campana_l2 as A
    rng = np.random.default_rng(20261008)
    filas = []
    res = {int(f["intento"]): f for f in campana.filas() if f["tipo"] == "resultado"}
    for k, f in sorted(res.items()):
        if f["incluida"] != "1":
            continue
        t = [r for r in _leer(salida / f["archivo_tomas"])
             if r.get("intento_campana") == str(k)][0]
        hw = float(t["cobertura_aoi"])
        for cond, tau, delta in (("con_obstaculo", 0.0, 0.0), ("sin_obstaculo", 0.0, 0.02),
                                 ("con_obstaculo", 0.45, -0.004)):
            for rep in (1, 2, 3):
                con = cond == "con_obstaculo"
                filas.append({
                    "campana": NOMBRE, "fuente_tomas": f["archivo_tomas"],
                    "id_sesion": t["id_sesion"], "intento_campana": k,
                    "semilla": t["semilla"], "condicion": cond, "tau_s": tau, "rep": rep,
                    "pasada": "normal",
                    "inicio": datetime.now().isoformat(timespec="seconds"),
                    "sha256_pila": "FALSA", "decisiones_previas": t["decisiones_previas"],
                    "valido": 1, "motivo": "", "decisiones": 500,
                    "cobertura_aoi": hw + brecha + delta + rng.normal(0, 0.003),
                    "d_min_obst_medida": (float(t["d_min_obst_medida"]) + 0.02) if con else "",
                    **{c: t[c] for c in A.SEGURIDAD},
                    "frenos_sombra": 0 if con else "",
                    "cierre_b_ok": 1 if con else "", "cierre_b_err_max_m": 0.0003 if con else "",
                    "cierre_b_desfase": 0 if con else "",
                    "cierre_b_err_th_rad": 2e-16 if con else "",
                    "cierre_b_mandos_iguales": 1 if con else ""})
    carpeta = salida / "replica_campana" / NOMBRE
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{datetime.now():%Y%m%d_%H%M%S}_FALSA_replica_tomas.csv"
    if not filas:
        return ruta                      # sin incluidas: no hay nada que replicar
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(filas)
    return ruta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta", type=int, default=5)
    ap.add_argument("--corte-en", type=int, default=3,
                    help="Ctrl+C en el Enter de la colocación n.º (sesión 1)")
    ap.add_argument("--tau", type=float, default=0.45, help="agentes")
    ap.add_argument("--tau-obstaculo", type=float, default=0.85)
    args = ap.parse_args()

    cfg.activar_simulador_local()               # los puertos que usa main
    import analizar_campana_l2 as A
    import campana_obstaculo as CO
    import demo_obstaculo_movil as demo
    import sesion_robotat as ses
    from correr_fase0_obstaculo import MonitorVerdad
    from simulador_para_colocacion import (SimuladorZonaMuerta,
                                           fallas_con_retardo_por_robot)

    rid_o = 4
    salida = demo.DIR_SALIDA_DEMO / f"ensayo_campana_{datetime.now():%Y%m%d_%H%M%S}"
    salida.mkdir(parents=True)
    demo.DIR_SALIDA_DEMO = salida

    robots = [cfg.MAPEO_AGENTES[i].id_robot for i in range(5)]
    mapeo = {r: cfg.MAPEO_AGENTES[i].id_marcador for i, r in enumerate(robots)}
    mapeo[rid_o] = cfg.marcador_fijo_de_robot(rid_o)
    tx, ty = cfg.TRASLACION_X_M, cfg.TRASLACION_Y_M
    agentes = {robots[0]: (0.5, 0.5, 0.3), robots[1]: (2.5, 0.5, 2.0),
               robots[2]: (0.5, 2.5, -1.0), robots[3]: (2.5, 2.5, -2.5),
               robots[4]: (1.5, 2.6, 0.0)}
    p0, r0 = demo.punto_del_circulo(-math.pi / 2)
    inicial = {r: (x - tx, y - ty, th) for r, (x, y, th) in agentes.items()}
    inicial[rid_o] = (float(p0[0]) - tx, float(p0[1]) - ty, float(r0))
    fallas = fallas_con_retardo_por_robot({rid_o: args.tau_obstaculo}, args.tau)
    sim = SimuladorZonaMuerta(mapeo, inicial, fallas)
    sim.iniciar()

    cuenta = {"enters_colocacion": 0, "paradas": 0, "enters": 0, "manos": 0,
              "fase": "s1"}

    def operador(mensaje: str) -> str:
        cuenta["enters"] += 1
        if "¿Seguir con la sesión?" in mensaje:
            cuenta["paradas"] += 1
            return ""
        if "van a ir SOLOS" in mensaje:
            cuenta["enters_colocacion"] += 1
            if cuenta["fase"] == "s1" and cuenta["enters_colocacion"] == args.corte_en:
                cuenta["fase"] = "s2"
                raise KeyboardInterrupt
        if "Corregí lo de arriba" in mensaje and "r" in actual:
            o, rumbo, _origen = actual["r"]
            with sim._lock:
                e = sim.robots[rid_o]
                e.x, e.y = float(o[0]) - tx, float(o[1]) - ty
                e.yaw = rumbo if rumbo is not None else 0.3
            cuenta["manos"] += 1
            time.sleep(0.4)
        return ""

    contexto_orig = ses.Contexto
    ses.Contexto = functools.partial(contexto_orig, preguntar=operador)

    # `main` aplica la calibración GUARDADA del laboratorio (`_preparar`), que
    # no vale en el simulador: allí el marco lab es métrico y alineado y el
    # rumbo es el del chasis. Igual que `replica_con_capas`: se llama a
    # `_preparar` y después se impone la identidad.
    preparar_orig = ses._preparar

    def preparar_identidad(ctx: Any) -> None:
        preparar_orig(ctx)
        cfg.ESCALA_POSICION = 1.0
        cfg.ROTACION_MARCO_RAD = 0.0
        cfg.TRASLACION_X_M = 1.5
        cfg.TRASLACION_Y_M = 1.5
        cfg.OFFSET_HEADING_RAD = 0.0
        print("[ensayo 1e] calibración identidad impuesta (simulador)")
    ses._preparar = preparar_identidad

    # Lo último que pidió la sesión para el obstáculo: si pide colocarlo A
    # MANO, el "operador" lo pone en su punto (la Fase A no está).
    import colocacion_con_obstaculo as C
    actual: Dict[str, Any] = {}
    objetivo_orig = C.objetivo_obstaculo

    def objetivo(modo, pose_o, semilla):
        actual["r"] = objetivo_orig(modo, pose_o, semilla)
        return actual["r"]
    C.objetivo_obstaculo = objetivo
    fin = datetime.now() + timedelta(hours=2)
    if fin.date() != datetime.now().date():
        fin = datetime.now().replace(hour=23, minute=59)
    hora_fin = f"{fin:%H:%M}"
    base = ["--modo", "L2", "--robot-obstaculo", str(rid_o), "--simulador",
            "--campana", NOMBRE]
    mon = MonitorVerdad(sim, robots, rid_o)
    codigos: Dict[str, int] = {}
    t0 = time.perf_counter()
    mon.iniciar()
    try:
        codigos["crear"] = demo.main(base + ["--crear-campana", "--meta", str(args.meta),
                                             "--minimo", "3", "--tope-intentos",
                                             str(3 * args.meta)])
        codigos["sesion_1"] = demo.main(base + ["--hora-fin", hora_fin])
        codigos["sesion_2"] = demo.main(base + ["--hora-fin", hora_fin])
        codigos["cerrar"] = demo.main(base + ["--cerrar-campana", "fin del ensayo 1e"])
    finally:
        mon.detener()
        sim.detener()
        ses.Contexto = contexto_orig
        ses._preparar = preparar_orig
        C.objetivo_obstaculo = objetivo_orig
    dur = time.perf_counter() - t0

    campana = CO.Campana(CO.Campana.carpeta_de(salida, NOMBRE))
    aud = auditar(salida, campana)
    (salida / "auditoria_registro.json").write_bytes(
        json.dumps(aud, ensure_ascii=False, indent=1).encode("utf-8"))
    ruta_rep = replica_falsa(salida, campana)
    cod_analisis = A.main(["--campana", NOMBRE, "--base", str(salida), "--ensayo"])
    import verificar_campana_l2 as V
    salidas = sorted((salida / "analisis_campana").glob(f"{NOMBRE}_*"))
    cod_verificador = (V.main([str(salidas[-1]), "--base", str(salida)])
                       if cod_analisis == 0 and salidas else None)
    resumen = {
        "codigos": codigos, "codigo_analisis": cod_analisis,
        "codigo_verificador": cod_verificador,
        "veredicto_campana": campana.veredicto(), "estado_libro": campana.estado(),
        "problemas_registro": aud["problemas"], "reservas": aud["reservas"],
        "estados": aud["estados"], "cierres_sesion": aud["cierres_sesion"],
        "tau_agentes": args.tau, "tau_obstaculo": args.tau_obstaculo,
        "verdad_d_min_obst_m": min(mon.d_min_obst),
        "verdad_d_min_pares_m": mon.d_min_pares,
        "operador": cuenta, "duracion_s": dur, "replica_falsa": ruta_rep.name,
        "sha256_congelados_libro": campana.hashes_vigentes(),
    }
    (salida / "resumen_ensayo.json").write_bytes(
        json.dumps(resumen, ensure_ascii=False, indent=1).encode("utf-8"))
    print(f"\n[ensayo 1e] códigos {codigos} · análisis {cod_analisis} · "
          f"verificador {cod_verificador} · "
          f"{campana.veredicto()} · problemas del registro: {aud['problemas'] or 'ninguno'} · "
          f"verdad mín agente–obstáculo {resumen['verdad_d_min_obst_m']:.4f} m, "
          f"agente–agente {resumen['verdad_d_min_pares_m']:.4f} m · {dur:.0f} s")
    print(f"salida en {salida}")
    return 0 if not aud["problemas"] and cod_analisis == 0 and cod_verificador == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
