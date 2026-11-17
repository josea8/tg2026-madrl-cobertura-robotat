"""
verificar_cifras_campana_l2_20261022.py
=======================================
Recalcula desde los crudos del paquete, o coteja contra el archivo de donde
sale, las cifras del reporte `REPORTE_2026-10-22_campana_L2.md`, y comprueba
que el texto las diga IGUAL: cada cifra se busca literal en el reporte y se
compara con lo recalculado. Lo que no cubre está en el §11 del reporte.
Una línea por cifra (SÍ / NO); código 1 si alguna no coincide.

    python scripts/verificar_cifras_campana_l2_20261022.py <raíz del paquete> <reporte.md>

No importa código del proyecto: libro, sesiones, L0, cierre (a3), pruebas,
ensayo 1e y sha256 se recalculan con código propio (csv, json, hashlib, ast,
statistics; numpy y scipy sólo para el a3).

CEGADO: la campaña `L2_obstaculo_2` está abierta. Este script no lee ninguna
cobertura de las sesiones de campaña, y comprueba que las tablas de tomas de
`sesiones/` no traigan esa columna.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import itertools
import json
import math
import re
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

CIFRAS: List[Tuple[str, str, str, bool]] = []   # (descripción, reportado, calculado, en el texto)
TEXTO = ""
RAIZ = Path(".")


# ── utilidades ───────────────────────────────────────────────────────────
def leer(ruta: Path) -> List[Dict[str, str]]:
    if not ruta.is_file() or not ruta.read_bytes().strip():
        return []
    with open(ruta, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def menos(texto: str) -> str:
    """El signo menos tipográfico del reporte."""
    return texto.replace("-", "−")


def con_signo(x: float, dec: int) -> str:
    return menos(f"{x:+.{dec}f}")


def hhmmss(iso: str) -> str:
    return iso.split("T")[1][:8]


def segundos(a: str, b: str) -> int:
    fa = datetime.fromisoformat(a.replace(" ", "T"))
    fb = datetime.fromisoformat(b.replace(" ", "T"))
    return int(round((fb - fa).total_seconds()))


def lista_es(xs: Sequence[Any]) -> str:
    xs = [str(x) for x in xs]
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " y " + xs[-1]


def cifra(desc: str, reportado: str, calculado: Any, en_texto: bool = True) -> None:
    CIFRAS.append((desc, reportado, str(calculado), en_texto))


def fila(desc: str, prefijo: str, sufijo: str = "") -> None:
    """Una fila de tabla del reporte que empieza con `prefijo` y termina con `sufijo`."""
    ok = any(l.startswith(prefijo) and l.rstrip().endswith(sufijo)
             for l in TEXTO.splitlines())
    esperado = prefijo + (" … " + sufijo if sufijo else "")
    CIFRAS.append((desc, esperado, esperado if ok else "FILA AUSENTE O DISTINTA", False))


def sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest() if ruta.is_file() else "FALTA"


# ── 0. cegado ────────────────────────────────────────────────────────────
def cegado() -> None:
    con = []
    for ruta in sorted((RAIZ / "sesiones").glob("*_L2_tomas.csv")):
        texto = ruta.read_bytes()
        if texto.strip():
            cab = texto.decode("utf-8").splitlines()[0]
            if "cobertura" in cab.lower():
                con.append(ruta.name)
    cifra("tablas de tomas de campaña con columna de cobertura", "0", len(con), False)
    cifra("el reporte dice que van sin la columna", "sin la columna `cobertura_aoi`",
          "sin la columna `cobertura_aoi`" if not con else "CON cobertura")


# ── 1. libro de L2_obstaculo_2 ───────────────────────────────────────────
def libro_l2_2() -> Dict[str, Any]:
    base = RAIZ / "campanas" / "L2_obstaculo_2"
    cab = json.loads((base / "campana.json").read_text(encoding="utf-8"))
    libro = leer(base / "libro.csv")
    res = [f for f in libro if f["tipo"] == "resultado"]
    res.sort(key=lambda f: int(f["intento"]))
    k_max = len(res)
    incl = [int(f["intento"]) for f in res if f["incluida"] == "1"]
    corridas = [f for f in res if f["estado"] == "corrida"]
    cifra("creación de L2_obstaculo_2", "a las 13:17:55", f"a las {hhmmss(cab['creada'])}")
    cifra("cabecera", "meta 50, mínimo 30, tope 100",
          f"meta {cab['meta']}, mínimo {cab['minimo']}, tope {cab['tope_intentos']}")
    cifra("semilla base", "`semilla_base` 422000", f"`semilla_base` {cab['semilla_base']}")
    cifra("intentos usados", "17/100 intentos", f"{k_max}/{cab['tope_intentos']} intentos")
    cifra("incluidas", "7/50 incluidas", f"{len(incl)}/{cab['meta']} incluidas")
    cifra("corridas", "14 corridas", f"{len(corridas)} corridas")
    cifra("tomas con contacto", "0 tomas con contacto",
          f"{sum(f['contacto'] == '1' for f in res)} tomas con contacto")
    cifra("frenos de respaldo", "0 frenos de respaldo",
          f"{sum(int(float(f['frenos'] or 0)) > 0 for f in res)} frenos de respaldo")
    cifra("pares de agentes a < 0.15 m", "0 pares de agentes a < 0.15 m",
          f"{sum(int(float(f['colisiones_015'] or 0)) for f in res)} pares de agentes a < 0.15 m")
    sem_ok = all(int(f["semilla"]) == int(cab["semilla_base"]) + int(f["intento"]) - 1
                 for f in libro if f["tipo"] in ("reserva", "resultado"))
    cifra("regla de semillas", "422000 + intento − 1 en todos los intentos",
          f"{cab['semilla_base']} + intento − 1 en todos los intentos" if sem_ok else "FALLA")
    # Filas de la tabla de intentos.
    nombres = {"corrida": "corrida", "interrumpida": "interrumpida",
               "parada_colocacion": "parada en la colocación"}
    for f in res:
        k = int(f["intento"])
        if f["valido"] == "1":
            vi = "sí / **sí**" if f["incluida"] == "1" else "sí / no"
        elif f["valido"] == "0":
            vi = "no / no"
        else:
            vi = "— / no"
        dm = f"{float(f['d_min_obst_medida']):.4f}" if f["d_min_obst_medida"] else "—"
        fila(f"tabla de intentos, intento {k}",
             f"| {k} | {f['semilla']} | {nombres[f['estado']]} | {vi} |", f"| {dm} |")
    dmin_c = [float(f["d_min_obst_medida"]) for f in corridas]
    dmin_i = [float(f["d_min_obst_medida"]) for f in res if f["incluida"] == "1"]
    cifra("d_min en las corridas", "entre 0.3011 y 0.5648 m en las 14 corridas",
          f"entre {min(dmin_c):.4f} y {max(dmin_c):.4f} m en las {len(corridas)} corridas")
    cifra("d_min en las incluidas", "entre 0.3011 y 0.3870 m en las 7 incluidas",
          f"entre {min(dmin_i):.4f} y {max(dmin_i):.4f} m en las {len(dmin_i)} incluidas")
    # Motivos que el reporte cita.
    por_k = {int(f["intento"]): f for f in res}
    for k in (3, 11, 16):
        m = re.search(r"\(robot (\d+)\).*?en \(([\d.]+), ([\d.]+)\)", por_k[k]["motivo"])
        cifra(f"motivo del intento {k}", None or f"marcador {m.group(1)} congelado en ({m.group(2)}, {m.group(3)})",
              f"marcador {m.group(1)} congelado en ({m.group(2)}, {m.group(3)})")
    m5 = re.search(r"recorrió el (\d+) %", por_k[5]["motivo"])
    cifra("motivo del intento 5", "recorrió el 48 % de lo comandado",
          f"recorrió el {m5.group(1)} % de lo comandado")
    m7 = re.search(r"robots (\d+) y (\d+)", por_k[7]["regla_parada"])
    cifra("parada del intento 7", "contacto de colocación entre los robots 1 y 2",
          f"contacto de colocación entre los robots {m7.group(1)} y {m7.group(2)}")
    cifra("regla del intento 15", "ABORTO POR EL OBSTÁCULO (repetición simultánea",
          "ABORTO POR EL OBSTÁCULO (repetición simultánea"
          if por_k[15]["regla_parada"].startswith("ABORTO POR EL OBSTÁCULO") else "otra")
    pausas = {int(f["intento"]): f["parada_respuesta"] for f in libro if f["tipo"] == "pausa"}
    cifra("pausa del intento 7", 'pausa "detenida"', f'pausa "{pausas.get(7)}"')
    cifra("pausa del intento 15", 'pausa: "siguió"', f'pausa: "{pausas.get(15)}"')
    # Clasificación de los no incluidos.
    congelado = [k for k, f in por_k.items() if f["incluida"] != "1" and "marcador CONGELADO" in f["motivo"]]
    antig = [k for k, f in por_k.items() if f["incluida"] != "1" and "antigüedad de pose" in f["motivo"]]
    simult = [k for k, f in por_k.items() if f["incluida"] != "1" and "marcador del obstáculo CONGELADO" in f["motivo"]]
    robots = [k for k, f in por_k.items() if f["incluida"] != "1"
              and ("NO SIGUE" in f["motivo"] or "CONTACTO durante la colocación" in f["motivo"])]
    interr = [k for k, f in por_k.items() if f["estado"] == "interrumpida"]
    cifra("pérdidas del seguimiento", "**seguimiento, 6:**",
          f"**seguimiento, {len(congelado) + len(antig) + len(simult)}:**")
    cifra("marcador congelado", "marcador congelado: 3, 11 y 16;", f"marcador congelado: {lista_es(congelado)};")
    cifra("antigüedad de pose", "antigüedad de pose: 6 y 12;", f"antigüedad de pose: {lista_es(antig)};")
    cifra("repetición simultánea", "repetición simultánea: 15;", f"repetición simultánea: {lista_es(simult)};")
    cifra("pérdidas de los robots", "**robots, 2:** el 5", f"**robots, {len(robots)}:** el {robots[0]}")
    cifra("interrumpidos", "**interrumpidos con Ctrl+C, 2:**", f"**interrumpidos con Ctrl+C, {len(interr)}:**")
    cifra("interrumpidos (cuáles)", "el 1, con", f"el {interr[0]}, con")
    cifra("interrumpidos (cuáles) 2", "el 17, con", f"el {interr[1]}, con")
    # Ritmo.
    r = len(incl) / k_max
    z = 1.959963984540054
    centro = (r + z * z / (2 * k_max)) / (1 + z * z / k_max)
    semi = z * math.sqrt(r * (1 - r) / k_max + z * z / (4 * k_max * k_max)) / (1 + z * z / k_max)
    lo, hi = centro - semi, centro + semi
    quedan = int(cab["tope_intentos"]) - k_max
    cifra("IC95 de Wilson del ritmo", "el IC95 de Wilson de 7/17 es [0.216, 0.640]",
          f"el IC95 de Wilson de {len(incl)}/{k_max} es [{lo:.3f}, {hi:.3f}]")
    cifra("incluidas al tope con el IC", "Aplicado a los 83 intentos que quedan (7 + 83 · p), da entre unas 25 y unas 60",
          f"Aplicado a los {quedan} intentos que quedan ({len(incl)} + {quedan} · p), da entre unas "
          f"{round(len(incl) + quedan * lo)} y unas {round(len(incl) + quedan * hi)}")
    cifra("ritmo", "7/17 = 41 %", f"{len(incl)}/{k_max} = {round(100 * r)} %")
    cifra("ritmo (resumen)", "(41 %)", f"({round(100 * r)} %)")
    cifra("intento del mínimo", "30 · 17/7 ≈ 73", f"30 · {k_max}/{len(incl)} ≈ {round(30 / r)}")
    cifra("incluidas al tope", "100 · 7/17 ≈ 41", f"100 · {len(incl)}/{k_max} ≈ {round(100 * r)}")
    cifra("próximo intento", "desde el intento 18 (semilla 422017)",
          f"desde el intento {k_max + 1} (semilla {int(cab['semilla_base']) + k_max})")
    # Sesiones.
    ses: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"int": []})
    for f in libro:
        if f["tipo"] == "apertura":
            ses[f["id_sesion"]]["abre"] = f["fecha"]
            ses[f["id_sesion"]]["fin"] = f["motivo"][-5:]
            ses[f["id_sesion"]]["l0"] = json.loads(f["detalle"])["l0"]["archivo"]
            ses[f["id_sesion"]]["marco"] = json.loads(f["detalle"])["configuracion"]["marco"]
            ses[f["id_sesion"]]["sha"] = json.loads(f["detalle"])["configuracion"]["sha256"]
        elif f["tipo"] == "cierre_sesion":
            ses[f["id_sesion"]]["cierra"] = f["fecha"]
        elif f["tipo"] == "reserva":
            ses[f["id_sesion"]]["int"].append(int(f["intento"]))
    for sid, d in sorted(ses.items()):
        ks = d["int"]
        txt = "—" if not ks else (str(ks[0]) if len(ks) == 1 else f"{ks[0]}–{ks[-1]}")
        fila(f"sesión {sid}", f"| `{sid}` | {hhmmss(d['abre'])} | {hhmmss(d['cierra'])} | {d['fin']} | {txt} |")
    d1 = segundos(ses["L2_20261021_131821"]["abre"], ses["L2_20261021_131821"]["cierra"])
    cifra("primera sesión: no alcanzó a revisar el 8", "por la duración, < 2 s, fue el 1 o el 5, no el 8",
          "por la duración, < 2 s, fue el 1 o el 5, no el 8" if d1 < 2 else f"duró {d1} s")
    cifra("L0 citada en las 6 aperturas", "La L0 de las 13:09:48, la que habilitó la campaña",
          "La L0 de las 13:09:48, la que habilitó la campaña"
          if {d["l0"] for d in ses.values()} == {"20261021_130948_L0_resumen.csv"} else "otra")
    # Incluidas por sesión.
    inc_ses = defaultdict(list)
    sesion_de = {int(f["intento"]): f["id_sesion"] for f in libro if f["tipo"] == "reserva"}
    for k in incl:
        inc_ses[sesion_de[k]].append(k)
    a, b = inc_ses["L2_20261021_133444"], inc_ses["L2_20261021_134819"]
    cifra("incluidas de la sesión de las 13:34", "la 2 y la 4", f"la {a[0]} y la {a[1]}" if len(a) == 2 else a)
    cifra("incluidas de la sesión de las 13:48", "la 8, 9, 10, 13 y 14", f"la {lista_es(b)}")
    cifra("cierre del intento 5", "que se cerró a las 13:40:28", f"que se cerró a las {hhmmss(por_k[5]['fecha'])}")
    return {"ses": ses, "res": por_k}


# ── 2. libro de L2_obstaculo (descartada) ────────────────────────────────
def libro_l2_1() -> None:
    base = RAIZ / "campanas" / "L2_obstaculo"
    cab = json.loads((base / "campana.json").read_text(encoding="utf-8"))
    libro = leer(base / "libro.csv")
    res = [f for f in libro if f["tipo"] == "resultado"]
    cifra("creación de L2_obstaculo", "creada a las 20:31:08", f"creada a las {hhmmss(cab['creada'])}")
    corr = [f["fecha"] for f in libro if f["tipo"] == "correccion"]
    cifra("corrección 1", "declarada a las 20:42:59", f"declarada a las {hhmmss(corr[0])}")
    cifra("corrección 2", "declarada a las 20:48:51", f"declarada a las {hhmmss(corr[1])}")
    cierre = [f for f in libro if f["tipo"] == "cierre_campana"][0]
    cifra("cierre de la campaña", "Cerrada a las 21:07:22", f"Cerrada a las {hhmmss(cierre['fecha'])}")
    mot = "Campaña DESCARTADA para el documento: el Robotat estaba mal calibrado"
    cifra("motivo del cierre", mot, mot if cierre["motivo"].startswith(mot) else cierre["motivo"][:70])
    corridas = [f for f in res if f["estado"] == "corrida"]
    cifra("estado final", "Estado final: 7 intentos, 3 corridas, 0 incluidas, 0 tomas con contacto.",
          f"Estado final: {len(res)} intentos, {len(corridas)} corridas, "
          f"{sum(f['incluida'] == '1' for f in res)} incluidas, "
          f"{sum(f['contacto'] == '1' for f in res)} tomas con contacto.")
    sem = sorted(int(f["semilla"]) for f in res)
    cifra("semillas", "Semillas 421000–421006.", f"Semillas {sem[0]}–{sem[-1]}.")
    cifra("semilla base vieja", "conserva su 421000", f"conserva su {cab['semilla_base']}")
    ses = {}
    for f in libro:
        if f["tipo"] in ("apertura", "cierre_sesion"):
            ses.setdefault(f["id_sesion"], {})[f["tipo"]] = f["fecha"]
    d = ses["L2_20261016_204312"]
    cifra("sesión 2 de la descartada", "se cerró a los 11 s",
          f"se cerró a los {segundos(d['apertura'], d['cierre_sesion'])} s")
    m1 = re.search(r"robots (\d+) y (\d+)", [f for f in res if f["intento"] == "1"][0]["motivo"])
    cifra("intento 1 de la descartada", "los robots 8 y 9 habían quedado juntos",
          f"los robots {m1.group(1)} y {m1.group(2)} habían quedado juntos")
    rb = [re.search(r"\(robot (\d+)\)", f["motivo"]).group(1) for f in res
          if f["intento"] in ("3", "6")]
    cifra("intentos 3 y 6 de la descartada", "(el 5 y el 8, cerca de la pared)",
          f"(el {rb[0]} y el {rb[1]}, cerca de la pared)")


# ── 3. CSV de las sesiones del 21-10 ─────────────────────────────────────
def sesiones_csv() -> None:
    nombres = {"20261021_133444": "13:34", "20261021_134819": "13:48"}
    rachas = []         # (sesión, toma, robot, paso_ini, paso_fin, x, y, último paso de la toma)
    simultaneos = []
    parciales = 0
    for s, hora in nombres.items():
        obst = defaultdict(list)
        for f in leer(RAIZ / "sesiones" / f"{s}_L2_obstaculo.csv"):
            obst[int(f["toma"])].append((int(f["paso"]), float(f["t"]), (f["x"], f["y"], f["th"])))
        n = g150 = g250 = 0
        gmax = 0.0
        for toma, filas in obst.items():
            filas.sort()
            for (p0, t0, _), (p1, t1, _) in zip(filas, filas[1:]):
                dt = (t1 - t0) * 1000
                n += 1
                g150 += dt > 150
                g250 += dt > 250
                gmax = max(gmax, dt)
        extra = ", el de la toma 15" if s.endswith("134819") else ""
        cifra(f"huecos del lazo, sesión de las {hora}",
              {"13:34": "sesión de las 13:34: 3 de 1698 > 150 ms y 1 > 250 ms (270 ms)",
               "13:48": "sesión de las 13:48: 6 de 3743 > 150 ms y 1 > 250 ms (309 ms, el de la toma 15)"}[hora],
              f"sesión de las {hora}: {g150} de {n} > 150 ms y {g250} > 250 ms ({gmax:.0f} ms{extra})")
        # Repeticiones bit a bit.
        dec = defaultdict(dict)
        dobs = {}
        for f in leer(RAIZ / "sesiones" / f"{s}_L2_decisiones.csv"):
            clave = (int(f["episodio"]), int(f["paso"]))
            dec[clave][f["robot"]] = (f["pose_env_x"], f["pose_env_y"], f["pose_env_th"])
            dobs[(clave, f["robot"])] = float(f["d_obst_medida"]) if f["d_obst_medida"] else math.nan
        ultimo = defaultdict(int)
        for (toma, paso) in dec:
            ultimo[toma] = max(ultimo[toma], paso)
        obst_pose = {(toma, p): pose for toma, filas in obst.items() for p, _, pose in filas}
        for (toma, paso), poses in sorted(dec.items()):
            prev = dec.get((toma, paso - 1))
            if not prev:
                continue
            rep = [r for r in poses if prev.get(r) == poses[r]]
            if len(rep) == len(poses) == 5:
                simultaneos.append((s, toma, paso, obst_pose.get((toma, paso)) == obst_pose.get((toma, paso - 1))))
                continue
            if len(rep) in (3, 4):
                parciales += 1
            for r in rep:
                x, y = float(poses[r][0]), float(poses[r][1])
                if rachas and rachas[-1][:3] == (s, toma, r) and rachas[-1][4] == paso - 1:
                    rachas[-1] = rachas[-1][:4] + (paso,) + rachas[-1][5:]
                else:
                    rachas.append((s, toma, r, paso, paso, x, y, ultimo[toma],
                                   dobs.get(((toma, paso), r), math.nan)))
        if s.endswith("134819"):
            t = {p: tt for p, tt, _ in obst[15]}
            dts = [(t[p + 1] - t[p]) * 1000 for p in range(198, 203)]
            cifra("toma 15: intervalos previos", "100.9 ms y 100.9 ms", f"{dts[0]:.1f} ms y {dts[1]:.1f} ms")
            cifra("toma 15: hueco", "**308.7 ms**", f"**{dts[2]:.1f} ms**")
            cifra("toma 15: pasos rápidos", "**9.7 ms** y **11.1 ms**", f"**{dts[3]:.1f} ms** y **{dts[4]:.1f} ms**")
            tomas = leer(RAIZ / "sesiones" / f"{s}_L2_tomas.csv")
            incl = sum(int(float(f["poses_rechazadas"] or 0)) for f in tomas)
            cifra("poses rechazadas en las tomas (13:48)", "las tomas suman 3", f"las tomas suman {incl}")
        tomas = leer(RAIZ / "sesiones" / f"{s}_L2_tomas.csv")
        p95 = st.mean(float(f["ciclo_p95_ms"]) for f in tomas if f.get("ciclo_p95_ms"))
        CICLOS[hora] = p95
    cifra("ciclo p95 medio por toma", "23.4 ms y 23.6 ms", f"{CICLOS['13:34']:.1f} ms y {CICLOS['13:48']:.1f} ms")
    cifra("repetición simultánea: paso", "En el paso 203, **los 5 agentes y el obstáculo repiten bit a bit**",
          "En el paso 203, **los 5 agentes y el obstáculo repiten bit a bit**"
          if [(x[1], x[2], x[3]) for x in simultaneos] == [(15, 203, True)] else simultaneos)
    cifra("repetición simultánea: única", "Es el único paso de las dos sesiones con los 5 agentes repetidos.",
          "Es el único paso de las dos sesiones con los 5 agentes repetidos." if len(simultaneos) == 1 else len(simultaneos))
    cifra("pasos con 3 o 4 repetidos", "No hay ninguno con 3 o 4 repetidos a la vez.",
          "No hay ninguno con 3 o 4 repetidos a la vez." if parciales == 0 else parciales)

    def d_pared(x: float, y: float) -> float:
        return min(x, 3 - x, y, 3 - y)

    pared = defaultdict(list)
    interior = []
    for r in rachas:
        (interior if d_pared(r[5], r[6]) > 0.5 else pared[r[2]]).append(r)
    for robot, txt in (("8", "robot 8 en (2.62, 2.70), (0.19, 0.85), (0.47, 0.32) y (2.72, 0.17)"),
                       ("9", "robot 9 en (0.17, 0.25), (0.41, 2.34) y (2.83, 2.77)")):
        cifra(f"congelamientos cerca de la pared, robot {robot}", txt,
              f"robot {robot} en " + lista_es([f"({r[5]:.2f}, {r[6]:.2f})" for r in pared[robot]]))
    cifra("solo los robots 8 y 9 cerca de la pared", "8 y 9", " y ".join(sorted(pared)), False)
    t6 = [r for r in pared["9"] if r[1] == 6][0]
    cifra("intento 6: marcador repetido", "marcador 9 repetido en (0.17, 0.25)",
          f"marcador {t6[2]} repetido en ({t6[5]:.2f}, {t6[6]:.2f})")
    xs = [r[5] for r in interior]
    ys = [r[6] for r in interior]
    cifra("zona interior: x", "x entre 1.456 y 1.548", f"x entre {min(xs):.3f} y {max(xs):.3f}")
    cifra("zona interior: y", "y entre 1.213 y 1.281", f"y entre {min(ys):.3f} y {max(ys):.3f}")
    cifra("zona interior: distancia a las paredes", "> 1.2 m de las paredes",
          f"> {math.floor(min(d_pared(r[5], r[6]) for r in interior) * 10) / 10} m de las paredes")
    quien = defaultdict(list)
    for r in interior:
        if r[1] not in quien[r[2]]:
            quien[r[2]].append(r[1])
    cifra("zona interior: robots y tomas", "el 1 en las tomas 12 y 14, y el 9 en la 8",
          f"el 1 en las tomas {lista_es(quien['1'])}, y el 9 en la {lista_es(quien['9'])}")
    dmax = max(math.dist((a[5], a[6]), (b[5], b[6])) for a, b in itertools.combinations(interior, 2))
    cifra("zona interior: separación máxima", "a menos de 9.9 cm entre sí", f"a menos de {dmax * 100:.1f} cm entre sí")
    dob = [r[8] for r in interior]
    cifra("zona interior: distancia al obstáculo", "a 0.70–0.81 m", f"a {min(dob):.2f}–{max(dob):.2f} m")
    durs = [r[4] - r[3] + 1 for r in interior]
    cifra("zona interior: duración", "duraron 1–6 pasos", f"duraron {min(durs)}–{max(durs)} pasos")
    hasta_el_fin = [r[1] for r in interior if r[4] == r[7]]
    cifra("zona interior: la que no se recuperó", "salvo la de la toma 12",
          f"salvo la de la toma {lista_es(hasta_el_fin)}")
    t12 = [r for r in interior if r[1] == 12]
    cifra("intento 12: marcador en la zona interior", "marcador 1 en la zona interior",
          f"marcador {t12[0][2]} en la zona interior")
    # Duración de los retrocesos de la zona interior que el código marcó "recuperada".
    agente_de = {"1": "a0", "5": "a1", "8": "a2", "2": "a3", "9": "a4"}
    detalle = {}
    for f in leer(RAIZ / "sesiones" / "20261021_134819_L2_tomas.csv"):
        for m in re.finditer(r"(a\d):(\d+)-(\d+)\(([\d.]+)s,[\d.]+cm,(\w+)\)", f["retrocesos_detalle"]):
            detalle[(int(f["toma"]), m.group(1), int(m.group(2)))] = (float(m.group(4)), m.group(5))
    durs_r = [detalle[(r[1], agente_de[r[2]], r[3])] for r in interior]
    rec = [d for d, estado in durs_r if estado == "recuperada"]
    cifra("zona interior: retrocesos recuperados", "en 0.1–0.6 s (el código las marca \"recuperada\")",
          f"en {min(rec):.1f}–{max(rec):.1f} s (el código las marca \"recuperada\")"
          if len(rec) == len(interior) - 1 else durs_r)


CICLOS: Dict[str, float] = {}


# ── 4. consolas, chequeos de la PC y horas ───────────────────────────────
def consolas(info: Dict[str, Any]) -> None:
    c = (RAIZ / "consola" / "consola_20261021_1409.txt").read_text(encoding="utf-8")
    cifra("ticks fuera de plazo", "ticks que no alcanzaron su plazo: 1540 y 3041",
          "ticks que no alcanzaron su plazo: " + lista_es(re.findall(r"ticks que no alcanzaron su plazo: (\d+)", c)))
    lat = re.findall(r"latencia: p50 [\d.]+ ms · p95 ([\d.]+) ms", c)
    cifra("latencia p95 21-10", "latencia de poses p95: 16.8 ms y 17.8 ms",
          f"latencia de poses p95: {lat[0]} ms y {lat[1]} ms")
    l16 = [re.findall(r"latencia: p50 [\d.]+ ms · p95 ([\d.]+) ms",
                      (RAIZ / "consola" / n).read_text(encoding="utf-8"))[-1]
           for n in ("consola_20261016_2037.txt", "consola_20261016_2105.txt")]
    cifra("latencia p95 16-10", "El 16-10 había sido de 5.4 ms y 5.0 ms",
          f"El 16-10 había sido de {l16[0]} ms y {l16[1]} ms")
    inc = re.findall(r"rechazadas por motivo: \{'inclinación': (\d+)\}", c)
    cifra("rechazos por inclinación", "poses rechazadas por inclinación: 233 y 5",
          f"poses rechazadas por inclinación: {inc[0]} y {inc[1]}")
    for robot, txt_c, txt_v in (("9", "el robot 9 se cayó a las 13:40:59", "volvió a los 63.0 s"),
                                ("1", "el robot 1 se cayó a las 13:44:35", "volvió a los 56.2 s")):
        m = re.search(rf"caída robot {robot} a las (\S+) .*?reabierto a los ([\d.]+) s", c)
        cifra(f"caída del robot {robot}", txt_c, f"el robot {robot} se cayó a las {m.group(1)}")
        cifra(f"vuelta del robot {robot}", txt_v, f"volvió a los {m.group(2)} s")
    # Chequeos de la PC.
    chequeos = {}
    textos = sorted((RAIZ / "consola").glob("consola_*.txt"))
    for ruta in textos:
        lineas = ruta.read_text(encoding="utf-8").splitlines()
        for i, l in enumerate(lineas):
            m = re.match(r"chequeo previo de la PC: (\S+ \S+)$", l)
            if not m:
                continue
            bloque = lineas[i:i + 12]
            corr = next(x for x in bloque if x.strip().startswith("corriente:"))
            proc = next(x for x in bloque if x.strip().startswith("procesos:"))
            veredicto = next(x for x in bloque if x.startswith("CHEQUEO"))
            chequeos[m.group(1)] = (veredicto.startswith("CHEQUEO OK"), corr, proc)
    bit = (RAIZ / "documentos" / "BITACORA_extracto_20261008_20261021.md").read_text(encoding="utf-8")
    m = re.search(r"chequeo previo de la PC: (2026-10-10 15:07:38)\n(?:.*\n){3}(CHEQUEO \S+)", bit)
    chequeos[m.group(1)] = (m.group(2) == "OK", "", "")

    def omen(proc: str) -> int:
        return len(re.findall(r"(?i)omen|overlayhelper|systemoptimizer", proc))

    for ts, (ok, corr, proc) in sorted(chequeos.items()):
        corto = f"{ts[8:10]}-{ts[5:7]} {ts[11:]}"
        if ok:
            fila(f"chequeo {corto}", f"| {corto} | **OK** |")
            continue
        detalle = ""
        if "A BATERIA" in corr:
            detalle = f"a batería, {omen(proc)} procesos de OMEN y ChatGPT" if "ChatGPT" in proc \
                else f"a batería y {omen(proc)} procesos de OMEN"
        fila(f"chequeo {corto}", f"| {corto} | FALLA |" + (f" {detalle} |" if detalle else ""))
    ses = info["ses"]
    ok_1332 = "2026-10-21 13:32:16"
    cifra("OK compartido de la sesión de las 13:34", "148 s antes de abrir",
          f"{segundos(ok_1332, ses['L2_20261021_133444']['abre'])} s antes de abrir")
    cifra("sesión de las 13:48 sin chequeo", "el último OK, 963 s antes",
          f"el último OK, {segundos(ok_1332, ses['L2_20261021_134819']['abre'])} s antes")
    mt = {}
    for l in (RAIZ / "derivados" / "mtimes_bitacora.txt").read_text(encoding="utf-8").splitlines():
        if l and not l.startswith("#"):
            fecha, nombre = l.split("  ")
            mt[nombre.strip()] = fecha
    cifra("escritura de la bitácora antes de las 13:48", "40 s antes de abrir la sesión de las 13:48",
          f"{segundos(mt['BITACORA_TECNICA_respaldo_20261021_preSesion3.md'], ses['L2_20261021_134819']['abre'])}"
          " s antes de abrir la sesión de las 13:48")
    viejo = {}
    for f in leer(RAIZ / "campanas" / "L2_obstaculo" / "libro.csv"):
        if f["tipo"] == "apertura":
            viejo[f["id_sesion"]] = f["fecha"]
    dif = [segundos(mt[a], viejo[b]) for a, b in (
        ("BITACORA_TECNICA_respaldo_20261016_pre3por6.md", "L2_20261016_203129"),
        ("BITACORA_TECNICA_respaldo_20261016_pre2por3.md", "L2_20261016_204312"),
        ("BITACORA_TECNICA_respaldo_20261016_preDescarte.md", "L2_20261016_204859"))]
    cifra("escrituras de la bitácora antes de las sesiones del 16-10", "(10, 84 y 52 s)", f"({lista_es(dif)} s)")
    # El primer chequeo del 21-10, después de la L0 habilitante.
    d = segundos("2026-10-21 13:09:48", "2026-10-21 13:11:44")
    cifra("primer chequeo del 21-10 tras la L0", "a las 13:11:44 (1 min 56 s después de terminar esa L0)",
          f"a las 13:11:44 ({d // 60} min {d % 60} s después de terminar esa L0)"
          if min(k for k in chequeos if k.startswith("2026-10-21")) == "2026-10-21 13:11:44" else "otro")
    # El comando de una línea que revisa los marcadores.
    veces = {r.name: r.read_text(encoding="utf-8").count("stream_congelado(c, m)") for r in textos}
    veces = {k: v for k, v in veces.items() if v}
    cifra("revisión de marcadores en las consolas", "consta una sola vez, antes de la sesión de las 13:32",
          "consta una sola vez, antes de la sesión de las 13:32"
          if veces == {"consola_20261021_1409.txt": 1} else veces)
    # OMEN el 21-10: el comando de administrador no encontró los dos procesos.
    omen = (RAIZ / "consola" / "consola_20261021_1315.txt").read_text(encoding="utf-8")
    no_hallados = re.findall(r'Cannot find a process with the name "([^"]+)"', omen)
    cifra("OMEN el 21-10", "ya no existían cuando el comando de administrador los buscó",
          "ya no existían cuando el comando de administrador los buscó"
          if sorted(no_hallados) == ["HP.OMEN.VirtualCamHelper", "OmenCommandCenterBackground"] else no_hallados)


# ── 5. L0 ────────────────────────────────────────────────────────────────
def l0() -> None:
    S = RAIZ / "sesiones"

    def resumen(n: str) -> Dict[str, str]:
        return leer(S / f"{n}_L0_resumen.csv")[0]

    def desc(r: Dict[str, str]) -> str:
        return (f"{r['arranques_corridos']}/{r['arranques_pedidos']} arranques; error radial máximo "
                f"{float(r['error_radial_max']) * 100:.2f} cm")

    def off(r: Dict[str, str]) -> str:
        return f"offset {con_signo(float(r['offset_dif_deg']), 2)}° ({r['offset_pares']} pares)"

    for n in ("20261016_194827", "20261016_194902"):
        r = resumen(n)
        fila(f"L0 {n}", f"| {n[9:11]}:{n[11:13]}:{n[13:]} | {r['veredicto']} | "
             f"{r['detalle']}; {r['arranques_corridos']} arranques |")
    r = resumen("20261016_195542")
    fila("L0 19:55:42", f"| 19:55:42 | {r['veredicto']} | {desc(r)}, contra < 5 cm; {off(r)} |")
    r = resumen("20261016_202910")
    fila("L0 20:29:10", f"| 20:29:10 | **{r['veredicto']}** | {desc(r)}; {off(r)} |")
    r = resumen("20261021_125545")
    fila("L0 12:55:45", f"| 12:55:45 | {r['veredicto']} | \"{r['detalle']}\" |")
    r = resumen("20261021_125901")
    tz = leer(S / "20261021_125901_L0_traza.csv")
    fila("L0 12:59:01", f"| 12:59:01 | {r['veredicto']} | \"{r['detalle']}\", en "
         f"({float(tz[-1]['x']):.2f}, {float(tz[-1]['y']):.2f}).")
    r = resumen("20261021_130948")
    fila("L0 13:09:48", f"| 13:09:48 | **{r['veredicto']}** | {desc(r)}; {off(r)} |")
    offs = [con_signo(float(resumen(n)["offset_dif_deg"]), 2) + "°"
            for n in ("20261016_195542", "20261016_202910", "20261021_130948")]
    cifra("offset del 4 en tres L0", "(−0.34°, −0.14° y −0.27°)", f"({lista_es(offs)})")
    # Colocación de la L0 de las 19:55.
    tz = leer(S / "20261016_195542_L0_traza.csv")
    f0 = tz[0]
    d0 = math.dist((float(f0["x"]), float(f0["y"])), (1.5, 0.9))
    cifra("L0 19:55: distancia al punto de arranque", "arrancó a 7.6 cm del punto de arranque (1.50, 0.90)",
          f"arrancó a {d0 * 100:.1f} cm del punto de arranque (1.50, 0.90)")
    cifra("L0 19:55: error radial inicial", "Su error radial inicial era de −7.3 cm",
          f"Su error radial inicial era de {con_signo(float(f0['error_radial']) * 100, 1)} cm")

    def pendiente(filas: List[Dict[str, str]]) -> float:
        t = [float(f["t"]) for f in filas]
        e = [float(f["error_radial"]) for f in filas]
        mt, me = st.mean(t), st.mean(e)
        return sum((a - mt) * (b - me) for a, b in zip(t, e)) / sum((a - mt) ** 2 for a in t)

    a0 = [f for f in tz if f["arranque"] == "0"]
    pend = [pendiente([f for f in a0 if float(f["t"]) <= 2]), pendiente([f for f in a0 if float(f["t"]) >= 2]),
            pendiente(a0)]
    cifra("L0 19:55: velocidad de corrección", "a 0.4–0.6 cm/s",
          f"a {min(pend) * 100:.1f}–{max(pend) * 100:.1f} cm/s")
    sesgos = []
    for n in ("20261016_195542", "20261016_202910", "20261021_125901", "20261021_130948"):
        v = [float(f["error_radial"]) for f in leer(S / f"{n}_L0_traza.csv")
             if int(f["arranque"]) >= 3 and float(f["t"]) >= 2]
        sesgos.append(st.mean(v) * 100)
    cifra("sesgo del seguimiento", "entre −1.93 y −2.05 cm",
          f"entre {con_signo(max(sesgos), 2)} y {con_signo(min(sesgos), 2)} cm")
    # La zona de la pérdida de las 12:59, en la L0 de las 13:09.
    tz = leer(S / "20261021_130948_L0_traza.csv")
    huecos = repetidas = 0
    for a, b in zip(tz, tz[1:]):
        if a["arranque"] != b["arranque"]:
            continue
        en_zona = 1.75 <= float(b["x"]) <= 2.10 and 1.55 <= float(b["y"]) <= 2.05
        huecos += en_zona and float(b["t"]) - float(a["t"]) > 0.15
        repetidas += en_zona and (a["x"], a["y"]) == (b["x"], b["y"])
    cifra("zona de la pérdida en la L0 siguiente",
          "Esa zona tuvo huecos de decisión y poses repetidas también en la L0 siguiente.",
          "Esa zona tuvo huecos de decisión y poses repetidas también en la L0 siguiente."
          if huecos and repetidas else f"huecos {huecos}, repetidas {repetidas}")


# ── 6. cierre (a3) ───────────────────────────────────────────────────────
def a3() -> None:
    import numpy as np
    from scipy import stats
    ref_dir = RAIZ / "referencia_3009"
    sufijos = ("", "_02", "_03", "_04", "_05")
    ref = defaultdict(list)
    ref_fila = {}
    for s in sufijos:
        for f in leer(ref_dir / f"20260930_sesion-replica_etapa7_capas-on_de-20260930{s}.csv"):
            if str(f.get("valido", "1")) in ("1", "True", "true"):
                ref[(s, int(f["episodio"]))].append(float(f["cobertura_aoi"]))
            ref_fila[(s, int(f["episodio"]), int(f["rep"]))] = f
    grupos = [v for v in ref.values() if len(v) >= 2]
    gl = sum(len(g) - 1 for g in grupos)
    delta = math.sqrt(sum(sum((x - st.mean(g)) ** 2 for x in g) for g in grupos) / gl)
    cifra("δ del a3", "δ = 0.00827", f"δ = {delta:.5f}")
    cifra("gl de δ", "con 98 gl", f"con {gl} gl")
    ultima = {}
    for s in sufijos:
        for f in leer(ref_dir / f"20260930_sesion-evaluacion_etapa7_episodios{s}.csv"):
            if f["valido"] in ("1", "True"):
                ultima[int(float(f["semilla"]))] = (s, int(f["episodio"]))
    episodios = set(ultima.values())
    dir_b = RAIZ / "replica_campana" / "cierre_a3_20261010_b"
    tomas = leer(sorted(dir_b.glob("*_replica_tomas.csv"))[0])
    nuevas = defaultdict(list)
    p95_n, p95_v = [], []
    validas = 0
    for f in sorted(tomas, key=lambda f: (f["id_sesion"], int(f["intento_campana"]), int(f["rep"]))):
        if f["condicion"] != "sin_obstaculo" or float(f["tau_s"]) != 0.0:
            continue
        clave = (f["id_sesion"].replace("30-09", ""), int(f["intento_campana"]))
        if f["valido"].strip() in ("1", "1.0"):
            validas += 1
            nuevas[clave].append(float(f["cobertura_aoi"]))
        p95_n.append(float(f["ciclo_p95_ms"]))
        p95_v.append(float(ref_fila[clave + (int(f["rep"]),)]["ciclo_p95_ms"]))
    pilas = {f["sha256_pila"] for f in tomas}
    claves = sorted(k for k in nuevas if k in episodios)
    D = np.array([st.mean(nuevas[k]) - st.mean(ref[k]) for k in claves])
    E = len(D)
    m = float(D.mean())
    semi = stats.t.ppf(0.975, E - 1) * float(np.std(D, ddof=1)) / math.sqrt(E)
    cifra("corridas del a3", "36/36 corridas válidas", f"{validas}/{len(tomas)} corridas válidas")
    cifra("pilas del a3", "de una sola pila", "de una sola pila" if len(pilas) == 1 else f"{len(pilas)} pilas")
    cifra("episodios del a3", "E = 12", f"E = {E}")
    cifra("media e IC95 del a3", "media Δ −0.00252, IC95 [−0.01052, +0.00549]",
          f"media Δ {con_signo(m, 5)}, IC95 [{con_signo(m - semi, 5)}, {con_signo(m + semi, 5)}]")
    cifra("veredicto del a3", "NO PASA",
          "NO PASA" if not (m - semi >= -delta and m + semi <= delta) else "PASA")
    cifra("IC95 del a3 en la decisión de José", "su IC95 [−0.0105, +0.0055]",
          f"su IC95 [{con_signo(m - semi, 4)}, {con_signo(m + semi, 4)}]")
    dd = dict(zip(claves, D))
    for k, txt_d, txt_r in (
            (("_05", 2), "s05 ep 2, Δ = −0.0404", "el 30-09 dio 0.326, 0.329 y 0.332; las reps nuevas, 0.322, 0.277 y 0.268"),
            (("_05", 8), "s05 ep 8, Δ = +0.0129", "el 30-09 dio 0.404, 0.410 y **0.377**; las nuevas, 0.412, 0.410 y 0.409")):
        cifra(f"Δ de s{k[0][1:]} ep {k[1]}", txt_d, f"s{k[0][1:]} ep {k[1]}, Δ = {con_signo(dd[k], 4)}")
        v = [f"{x:.3f}" for x in ref[k]]
        n = [f"{x:.3f}" for x in nuevas[k]]
        if k[1] == 8:
            calc = f"el 30-09 dio {v[0]}, {v[1]} y **{v[2]}**; las nuevas, {lista_es(n)}"
        else:
            calc = f"el 30-09 dio {lista_es(v)}; las reps nuevas, {lista_es(n)}"
        cifra(f"reps de s{k[0][1:]} ep {k[1]}", txt_r, calc)
    otros = {k: d for k, d in dd.items() if k not in (("_05", 2), ("_05", 8))}
    chicos = [k for k, d in otros.items() if abs(d) <= 0.002]
    resto = [k for k in otros if k not in chicos]
    cifra("los otros 10", "De los otros 10, 9 tienen |Δ| ≤ 0.002; el décimo, s02 ep 12, tiene Δ = −0.0040.",
          f"De los otros {len(otros)}, {len(chicos)} tienen |Δ| ≤ 0.002; el décimo, "
          f"s{resto[0][0][1:]} ep {resto[0][1]}, tiene Δ = {con_signo(otros[resto[0]], 4)}.")
    sd_n = {k: float(np.std(nuevas[k], ddof=1)) for k in claves}
    sd_v = {k: float(np.std(ref[k], ddof=1)) for k in claves}
    cifra("desvío mediano", "0.0013 en las nuevas y 0.0015 en las del 30-09",
          f"{st.median(sd_n.values()):.4f} en las nuevas y {st.median(sd_v.values()):.4f} en las del 30-09")
    kn, kv = max(sd_n, key=sd_n.get), max(sd_v, key=sd_v.get)
    cifra("ruido en los mismos 12 (decisión de José)",
          "En los mismos 12, la mediana es 0.0013 contra 0.0015 y el máximo 0.0287 contra 0.0175",
          f"En los mismos 12, la mediana es {st.median(sd_n.values()):.4f} contra {st.median(sd_v.values()):.4f} "
          f"y el máximo {sd_n[kn]:.4f} contra {sd_v[kv]:.4f}")
    cifra("desvío máximo", "El máximo nuevo (0.0287, s05 ep 2) supera al del 30-09 en esos episodios (0.0175, s05 ep 8).",
          f"El máximo nuevo ({sd_n[kn]:.4f}, s{kn[0][1:]} ep {kn[1]}) supera al del 30-09 en esos episodios "
          f"({sd_v[kv]:.4f}, s{kv[0][1:]} ep {kv[1]}).")
    cifra("ciclo p95 del a3", "el ciclo p95 medio fue 25.3 ms, contra 20.8 ms",
          f"el ciclo p95 medio fue {st.mean(p95_n):.1f} ms, contra {st.mean(p95_v):.1f} ms")
    # Separación entre reps nuevas (CSV de decisiones del a3).
    P = defaultdict(dict)
    for f in leer(sorted(dir_b.glob("*_replica_decisiones.csv"))[0]):
        P[(int(f["intento_campana"]), int(f["rep"]))][(int(f["paso"]), int(f["agente"]))] = (
            float(f["pose_env_x"]), float(f["pose_env_y"]))

    def primera(ep: int, a: int, b: int, umbral: float) -> Optional[int]:
        pa, pb = P[(ep, a)], P[(ep, b)]
        for p in sorted({p for p, _ in pa}):
            if max(math.dist(pa[(p, i)], pb[(p, i)]) for i in range(5)) > umbral:
                return p
        return None

    sep1 = [primera(ep, a, b, 1e-3) for _s, ep in claves for a, b in ((1, 2), (1, 3), (2, 3))]
    cifra("separación > 1 mm", "entre los pasos 1 y 111", f"entre los pasos {min(sep1)} y {max(sep1)}")
    sep5 = [primera(2, a, b, 0.05) for a, b in ((1, 2), (1, 3), (2, 3))]
    cifra("separación > 5 cm en s05 ep 2", "hacia el paso 207", f"hacia el paso {min(x for x in sep5 if x)}")
    # Intercambiabilidad (el método del diagnóstico, reescrito).
    perm = []
    for k in claves:
        v = nuevas[k] + ref[k]
        perm.append(np.array([st.mean([v[i] for i in c]) - st.mean([v[i] for i in range(6) if i not in c])
                              for c in itertools.combinations(range(6), 3)]))
    rng = np.random.default_rng(20261010)
    idx = rng.integers(0, 20, size=(200000, E))
    Dm = np.stack([perm[j][idx[:, j]] for j in range(E)], axis=1)
    mm, ss = Dm.mean(1), Dm.std(1, ddof=1)
    se = stats.t.ppf(0.975, E - 1) * ss / math.sqrt(E)
    pasa = ((mm - se >= -delta) & (mm + se <= delta)).mean()
    cifra("P(PASA | intercambiables)", "la regla daría PASA con probabilidad 0.615",
          f"la regla daría PASA con probabilidad {pasa:.3f}")
    cifra("P(|media Δ| ≥ observada)", "aparece con probabilidad 0.261",
          f"aparece con probabilidad {np.mean(np.abs(mm) >= abs(m)):.3f}")
    cifra("Wilcoxon", "da p = 1.000, con mediana Δ = +0.00009",
          f"da p = {stats.wilcoxon(D).pvalue:.3f}, con mediana Δ = {con_signo(float(np.median(D)), 5)}")
    sd_todos = [float(np.std(v, ddof=1)) for v in ref.values() if len(v) >= 2]
    cifra("tomas del 30-09 con desvío > 0.01", "contra 6 de 50 del 30-09",
          f"contra {sum(x > 0.01 for x in sd_todos)} de {len(ref)} del 30-09")
    dir_a = RAIZ / "replica_campana" / "cierre_a3_20261010"
    n_a = len(leer(sorted(dir_a.glob("*_replica_tomas.csv"))[0]))
    js = json.loads(sorted(dir_a.glob("cierre_a3_*.json"))[0].read_text(encoding="utf-8"))
    cifra("a3 interrumpido", "se cortó a las 2 corridas", f"se cortó a las {n_a} corridas")
    cifra("a3 interrumpido: veredicto", "quedó SIN VEREDICTO", "quedó SIN VEREDICTO" if js.get("pasa") is None else js.get("pasa"))
    a1 = (dir_b / "diagnostico_20261010" / "a1_episodios_a3_salida.txt").read_text(encoding="utf-8")
    iguales = len(re.findall(r"filas 2500/2500 · distintas 0 · rpm iguales True", a1))
    cifra("decisión bit a bit en 3 episodios", "2500/2500 filas", "2500/2500 filas" if iguales == 3 else iguales)


# ── 7. pruebas, ensayo 1e y congelados ───────────────────────────────────
def pruebas_y_congelados() -> None:
    etiquetas = {"test_campana_obstaculo": "campaña", "test_analizar_campana_l2": "análisis",
                 "test_replica_con_obstaculo": "réplica", "test_demo_obstaculo_movil": "demo",
                 "test_regla_estancamiento": "estancamiento", "test_sesion_robotat": "sesión",
                 "test_cerrojo_fuente_poses": "cerrojo", "test_diagnostico_poses": "diagnóstico",
                 "test_mapa_seguimiento": "mapa", "test_respuesta_no_numerica": "respuesta",
                 "test_retroceso_congelamiento": "retroceso", "test_robotat": "robotat",
                 "test_integracion_robotat": "integración"}
    total = oks = 0
    for ruta in sorted((RAIZ / "pruebas" / "suites_20261017").glob("test_*.txt")):
        t = ruta.read_text(encoding="utf-8", errors="replace")
        n = int(re.search(r"Ran (\d+) tests", t).group(1))
        ok = bool(re.search(r"^OK\s*$", t, re.M))
        total += n
        oks += ok
        cifra(f"suite {ruta.stem}", f"| {etiquetas[ruta.stem]} | {n} |", f"| {etiquetas[ruta.stem]} | {n} |"
              if ok else "FALLÓ")
    cifra("total de pruebas", "**556, 13/13 OK**", f"**{total}, {oks}/{len(etiquetas)} OK**")
    cifra("total de pruebas (resumen)", "**556 pruebas OK**", f"**{total} pruebas OK**")
    e1 = RAIZ / "ensayo_1e" / "ensayo_campana_20261017_092424"
    r = json.loads((e1 / "resumen_ensayo.json").read_text(encoding="utf-8"))
    cifra("1e: veredicto", "- META;", f"- {r['veredicto_campana']};")
    cifra("1e: verdad", "verdad mínima agente–obstáculo 0.3265 m y agente–agente 0.2303 m",
          f"verdad mínima agente–obstáculo {r['verdad_d_min_obst_m']:.4f} m y agente–agente "
          f"{r['verdad_d_min_pares_m']:.4f} m")
    lib = leer(e1 / "campanas" / "ensayo" / "libro.csv")
    res = [f for f in lib if f["tipo"] == "resultado"]
    sem = sorted(int(f["semilla"]) for f in res)
    cifra("1e: intentos", "6 intentos, 5 incluidas y un corte con Ctrl+C reanudado",
          f"{len(res)} intentos, {sum(f['incluida'] == '1' for f in res)} incluidas y "
          f"{'un corte' if sum(f['estado'] == 'interrumpida' for f in res) == 1 else 'otros cortes'} con Ctrl+C reanudado")
    cifra("1e: semillas", "semillas 422000–422005", f"semillas {sem[0]}–{sem[-1]}")
    log = (RAIZ / "pruebas" / "ensayo_1e_20261017.log").read_text(encoding="utf-8", errors="replace")
    v = re.findall(r"(\d+)/(\d+) coinciden", log)[-1]
    cifra("1e: verificador", "**verificador independiente 106/106**", f"**verificador independiente {v[0]}/{v[1]}**")
    cifra("1e: códigos", "análisis y verificador con código 0",
          "análisis y verificador con código 0" if r["codigo_analisis"] == 0 and r["codigo_verificador"] == 0 else "≠ 0")
    # sha256 de los congelados, con código propio.
    nombres_dia = {"ESCALA_POSICION", "ESCALA_NO_VERIFICADA", "ROTACION_MARCO_RAD", "TRASLACION_X_M",
                   "TRASLACION_Y_M", "MARCO_NO_VERIFICADO", "OFFSET_HEADING_RAD", "HEADING_NO_VERIFICADO",
                   "MAPEO_NO_VERIFICADO", "OFFSETS_RUMBO_POR_ROBOT", "OFFSETS_RUMBO_MEDIDOS", "ORIGEN_OFFSET_RUMBO"}

    def huella(ruta: Path) -> str:
        partes = []
        for nodo in ast.parse(ruta.read_bytes().decode("utf-8")).body:
            if isinstance(nodo, ast.Expr) and isinstance(nodo.value, ast.Constant):
                continue
            if isinstance(nodo, (ast.Assign, ast.AnnAssign)):
                blancos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
                if all(isinstance(b, ast.Name) and b.id in nombres_dia for b in blancos):
                    continue
            partes.append(ast.dump(nodo, include_attributes=False))
        return hashlib.sha256("\n".join(partes).encode("utf-8")).hexdigest()

    def hash_de(nombre: str) -> str:
        if nombre.endswith("#sin_calibracion"):
            return huella(RAIZ / "codigo" / nombre.split("#")[0])
        if nombre.startswith("TESIS/"):
            return sha256(RAIZ / "documentos" / nombre[len("TESIS/"):])
        return sha256(RAIZ / "codigo" / nombre)

    c2 = json.loads((RAIZ / "campanas" / "L2_obstaculo_2" / "campana.json").read_text(encoding="utf-8"))["archivos_congelados"]
    ce = json.loads((e1 / "campanas" / "ensayo" / "campana.json").read_text(encoding="utf-8"))["archivos_congelados"]
    c1 = json.loads((RAIZ / "campanas" / "L2_obstaculo" / "campana.json").read_text(encoding="utf-8"))["archivos_congelados"]
    hoy = {n: hash_de(n) for n in c2}
    ig2 = sum(hoy[n] == c2[n] for n in c2)
    ige = sum(hoy.get(n) == ce.get(n) for n in ce)
    cifra("congelados de hoy contra L2_obstaculo_2 y el 1e", "a los de `L2_obstaculo_2` (22/22)",
          f"a los de `L2_obstaculo_2` ({ig2}/{len(c2)})" if ig2 == ige == len(c2) == len(ce) else f"{ig2}, {ige}")
    dif = sorted(n for n in c2 if c1.get(n) != c2[n])
    cifra("congelados que difieren entre las dos campañas", "difieren 5 de 22", f"difieren {len(dif)} de {len(c2)}")
    esperados = ["TESIS/PLAN_ANALISIS_campana_L2.md", "analizar_campana_l2.py", "campana_obstaculo.py",
                 "config_robotat.py#sin_calibracion", "demo_obstaculo_movil.py"]
    cifra("cuáles difieren", "plan, análisis, libro, demo y huella de config",
          "plan, análisis, libro, demo y huella de config" if dif == esperados else dif, False)
    cifra("congelados del coordinador en el paquete", "los 20 archivos congelados de la carpeta del coordinador",
          f"los {sum(1 for n in c2 if '#' not in n and not n.startswith('TESIS/'))} archivos congelados "
          "de la carpeta del coordinador")


# ── 8. calibración y citas de la bitácora ───────────────────────────────
def calibracion_y_bitacora(info: Dict[str, Any]) -> None:
    marcos = set()
    shas = {}
    for camp in ("L2_obstaculo", "L2_obstaculo_2"):
        for f in leer(RAIZ / "campanas" / camp / "libro.csv"):
            if f["tipo"] == "apertura":
                c = json.loads(f["detalle"])["configuracion"]
                mk = c["marco"]
                marcos.add((round(mk["ESCALA_POSICION"], 4), round(math.degrees(mk["ROTACION_MARCO_RAD"]), 2),
                            round(mk["TRASLACION_X_M"], 3), round(mk["TRASLACION_Y_M"], 3)))
                shas.setdefault(camp, set()).add(c["sha256"]["calibracion_medida.json"])
    (e, r, x, y), = marcos
    cifra("marco del mocap (igual en las dos campañas)", "escala 1.0167, rotación +0.49°, traslación (1.506, 1.256)",
          f"escala {e}, rotación {r:+.2f}°, traslación ({x}, {y})" if len(marcos) == 1 else marcos)
    cambio = shas["L2_obstaculo"] != shas["L2_obstaculo_2"] and \
        shas["L2_obstaculo_2"] == {sha256(RAIZ / "codigo" / "calibracion_medida.json")}
    cifra("calibracion_medida.json cambió sin cambiar el marco", "pero no cambió el marco",
          "pero no cambió el marco" if cambio and len(marcos) == 1 else "otra cosa")
    cal = json.loads((RAIZ / "codigo" / "calibracion_medida.json").read_text(encoding="utf-8"))
    hoy = [h for h in cal["_historial"] if h["cuando"].startswith("2026-10-21")]
    e0 = sorted({hhmmss(h["cuando"]) for h in hoy if h["etapa"] == "etapa 0"})
    e2 = sorted({hhmmss(h["cuando"]) for h in hoy if h["etapa"] == "etapa 2"})
    guardo = sorted({c for h in hoy for c in h["campos"]})
    cifra("escrituras de calibracion_medida.json el 21-10",
          "se escribió a las 13:03:26 (la etapa 0 guardó `id_robot` = 1), y a las 13:04:28 y 13:05:17",
          f"se escribió a las {lista_es(e0)} (la etapa 0 guardó `{lista_es(guardo)}` = {cal['id_robot']}), "
          f"y a las {lista_es(e2)}")
    cifra("la etapa 2 no guardó valores", "sin guardar ningún valor de calibración",
          "sin guardar ningún valor de calibración"
          if not any(h["campos"] for h in hoy if h["etapa"] == "etapa 2") else "guardó")
    # La demo contra su respaldo previo a la campaña, por AST.
    def definiciones(ruta: Path) -> Dict[str, str]:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        return {n.name: ast.dump(n, include_attributes=False) for n in arbol.body
                if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    antes = definiciones(RAIZ / "codigo" / "respaldos" / "demo_obstaculo_movil_respaldo_20261008_preCampana.py")
    ahora = definiciones(RAIZ / "codigo" / "demo_obstaculo_movil.py")
    cambian = [n for n in ("sesion_demo", "_colocar_toma_automatica", "main", "sesion_l0", "l0_habilita",
                           "escribir_csv") if n in antes and antes[n] != ahora.get(n)]
    todas_cambian = sorted(n for n in antes if n in ahora and antes[n] != ahora[n])
    nuevas = [n for n in ahora if n not in antes]
    cifra("AST: funciones que cambian", "cambian `sesion_demo`, `_colocar_toma_automatica`, `main`, `sesion_l0`, "
          "`l0_habilita` y `escribir_csv`, y hay 5 funciones nuevas",
          "cambian " + lista_es([f"`{n}`" for n in cambian]) + f", y hay {len(nuevas)} funciones nuevas"
          if sorted(cambian) == todas_cambian else todas_cambian)
    iguales = ["FiltroConObstaculo", "CoordinadorConObstaculo", "SupervisorObstaculo", "correr_toma",
               "validez_demo", "regla_de_parada", "aplicar_regla_de_parada", "estimar_error_offset"]
    distintas = [n for n in iguales if n not in antes or antes[n] != ahora.get(n)]
    cifra("AST: la barrera, el supervisor, correr_toma y la validez", "quedan idénticos la barrera",
          "quedan idénticos la barrera" if not distintas else f"distintas: {distintas}")
    bit = (RAIZ / "documentos" / "BITACORA_extracto_20261008_20261021.md").read_text(encoding="utf-8")
    citas = [
        ("revisión del 08-10", r"~45 hallazgos", "~45 hallazgos"),
        ("revisión de la réplica", r"10 confirmados, 2 refutados", "10 confirmados y 2 refutados"),
        ("auditoría final", r"27 hallazgos, 26 confirmados .*?y 1 refutado", "27 hallazgos: 26 confirmados y 1 refutado"),
        ("ronda 1 del a3", r"18 hallazgos, 8 confirmados \(4 problemas distintos\) y 10 refutados",
         "ronda 1: 18 hallazgos, 8 confirmados y 10 refutados"),
        ("ronda 2 del a3", r"13 hallazgos, 7 confirmados y 6 refutados", "ronda 2: 13, 7 y 6"),
        ("verificación del chequeo", r"12 hallazgos, 3 confirmados y 9 refutados", "12 hallazgos, 3 confirmados y 9 refutados"),
        ("verificación del 17-10", r"11 hallazgos, 7 confirmados, todos menores y aplicados, y 4 refutados",
         "11 hallazgos, 7 confirmados y 4 refutados"),
        ("cierre (b)", r"error 0\.0 m, desfase 0, rumbo 2\.2e-16 rad y mandos idénticos",
         "error 0.0 m, rumbo 2.2e-16 rad y mandos idénticos"),
        ("bitácora: '8 de ellos'", r"y 8 de ellos ≤ 0\.002", "\"8 de ellos ≤ 0.002\""),
        ("bitácora: máximo 0.029 contra 0.031", r"máximo 0\.029 contra 0\.031", "desvío máximo nuevo 0.029 contra 0.031"),
        ("bitácora: 44/44 más 2", r"campaña 44/44, más las 2 pruebas nuevas", "\"campaña 44/44, más las 2 pruebas nuevas\""),
        ("bitácora: 7.3 cm dentro de ±8", r"7\.3 cm hacia adentro.*?dentro de la tolerancia de ±8 cm",
         "\"7.3 cm hacia adentro, dentro de la tolerancia de ±8 cm\""),
        ("bitácora: enlace del 9", r"su enlace se había caído a las 13:40:59", "\"se había caído a las 13:40:59\""),
        ("bitácora: 7 del seguimiento", r"7 fueron del seguimiento", "\"7 fueron del seguimiento\""),
        ("bitácora: desvío mediano", r"Desvío mediano 0\.0013 en las dos réplicas", "\"Desvío mediano 0.0013 en las dos réplicas\""),
        ("bitácora: zona 1.42", r"\(1\.42–1\.55, 1\.21–1\.28\): el 1 en las tomas 12, 13 y 14",
         "\"(1.42–1.55, …), el 1 en las tomas 12, 13 y 14\""),
        ("bitácora: 8 en (2.76, 0.20)", r"\(2\.76, 0\.20\)", "en \"(2.76, 0.20)\""),
        ("bitácora: 5 poses", r"5 poses rechazadas por inclinación", "\"5 poses rechazadas por inclinación\""),
    ]
    for desc, patron, en_reporte in citas:
        cifra(f"cita de la bitácora: {desc}", en_reporte,
              en_reporte if re.search(patron, bit, re.S) else "NO ESTÁ EN LA BITÁCORA")


def main() -> int:
    global TEXTO, RAIZ
    RAIZ = Path(sys.argv[1])
    TEXTO = Path(sys.argv[2]).read_text(encoding="utf-8")
    cegado()
    info = libro_l2_2()
    libro_l2_1()
    sesiones_csv()
    consolas(info)
    l0()
    a3()
    pruebas_y_congelados()
    calibracion_y_bitacora(info)
    malas = 0
    for desc, reportado, calculado, en_texto in CIFRAS:
        esta = (not en_texto) or (reportado in TEXTO)
        ok = esta and calculado == reportado
        malas += not ok
        marca = "SÍ" if ok else "NO"
        extra = "" if esta else "   ← no aparece así en el reporte"
        print(f"{marca}  {desc}\n      reporte:   {reportado}\n      calculado: {calculado}{extra}")
    print(f"\n{len(CIFRAS) - malas}/{len(CIFRAS)} cifras coinciden.")
    return 1 if malas else 0


if __name__ == "__main__":
    sys.exit(main())
