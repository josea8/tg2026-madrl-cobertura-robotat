"""
verificar_cifras_campana_l2_20261107.py
=======================================
Recalcula desde los crudos del paquete, o coteja contra el archivo de donde
sale, las cifras del reporte `REPORTE_2026-11-07_campana_L2.md`, y comprueba
que el texto las diga IGUAL: cada cifra se busca literal en el reporte y se
compara con lo recalculado. Lo que no cubre está en el §11 del reporte.
Una línea por cifra (SÍ / NO); código 1 si alguna no coincide.

    python scripts/verificar_cifras_campana_l2_20261107.py <raíz del paquete> <reporte.md>

No importa código del proyecto ni paquetes externos: libro, sesiones,
consolas, derivados y sha256 se recalculan con código propio (csv, json,
hashlib, ast, re, math, statistics).

Hace falta Python 3.13: la huella sin calibración de `config_robotat.py` es
un sha256 de `ast.dump`, que cambió en 3.13 (ya no escribe las listas
vacías). Con 3.12 daría otra huella sin que el archivo haya cambiado, y 3.14 y
posteriores no se probaron (`ast.dump` puede volver a cambiar): el script sólo
corre con 3.13 y con otra versión se niega. La salida se escribe en UTF-8.

CEGADO: la campaña `L2_obstaculo_2` está abierta. Este script no lee ninguna
cobertura, y comprueba que las tablas de tomas de `sesiones/` no traigan
esa columna.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import math
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

CIFRAS: List[Tuple[str, str, str, bool]] = []   # (descripción, reportado, calculado, en el texto)
TEXTO = ""
RAIZ = Path(".")
SESIONES = {"23-10": "20261023_205008", "04-11": "20261104_120744", "06-11": "20261106_193852"}
PARES: Dict[str, str] = {}   # intervalos "entre las … y las …" que salen de los crudos


# ── utilidades ───────────────────────────────────────────────────────────
def leer(ruta: Path) -> List[Dict[str, str]]:
    if not ruta.is_file() or not ruta.read_bytes().strip():
        return []
    with open(ruta, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def texto_de(ruta: Path) -> str:
    return ruta.read_bytes().decode("utf-8")


def menos(texto: str) -> str:
    return texto.replace("-", "−")


def hhmmss(iso: str) -> str:
    return iso.split("T")[1][:8]


def lista_es(xs: Sequence[Any]) -> str:
    xs = [str(x) for x in xs]
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " y " + xs[-1]


def cifra(desc: str, reportado: str, calculado: Any, en_texto: bool = True) -> None:
    CIFRAS.append((desc, reportado, str(calculado), en_texto))


def fila(desc: str, esperado: str) -> None:
    """Una línea completa del reporte, igual a `esperado`."""
    ok = any(l.strip() == esperado for l in TEXTO.splitlines())
    CIFRAS.append((desc, esperado, esperado if ok else "FILA AUSENTE O DISTINTA", False))


def todas(desc: str, patron: str, esperado: str) -> None:
    """Todas las apariciones de `patron` en el reporte tienen que ser `esperado`."""
    hall = re.findall(patron, TEXTO)
    ok = bool(hall) and all(h == esperado for h in hall)
    CIFRAS.append((desc + f" ({len(hall)} apariciones)", esperado, esperado if ok else str(hall), False))


def todas_de(desc: str, patron: str, permitidos: Dict[str, str], cuantas: Dict[str, int]) -> None:
    """Cada aparición de `patron` (sin distinguir mayúsculas) es uno de los `permitidos`, y cada uno aparece `cuantas` veces."""
    hall = [h.lower() for h in re.findall(patron, TEXTO, re.I)]
    vals = {v.lower() for v in permitidos.values()}
    malos = sorted({h for h in hall if h not in vals})
    faltan = [f"{k}: {hall.count(v.lower())} en vez de {cuantas[k]}" for k, v in permitidos.items()
              if hall.count(v.lower()) != cuantas[k]]
    esperado = f"todas salen de los crudos ({len(permitidos)} intervalos, {sum(cuantas.values())} apariciones)"
    CIFRAS.append((desc + f" ({len(hall)} apariciones)", esperado,
                   esperado if hall and not malos and not faltan else f"distintas: {malos} · faltan: {faltan}", False))


def celda_motivo(k: int) -> str:
    linea = next((l for l in TEXTO.splitlines() if l.startswith(f"| {k} | ")), "")
    partes = [p.strip() for p in linea.split("|")]
    return partes[5] if len(partes) > 6 else ""


def sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest() if ruta.is_file() else "FALTA"


def d_pared(x: float, y: float) -> float:
    return min(x, 3 - x, y, 3 - y)


# ── 0. cegado ────────────────────────────────────────────────────────────
def cegado() -> None:
    con = []
    for ruta in sorted((RAIZ / "sesiones").glob("*_L2_tomas.csv")):
        crudo = ruta.read_bytes()
        if crudo.strip() and "cobertura" in crudo.decode("utf-8").splitlines()[0].lower():
            con.append(ruta.name)
    cifra("tablas de tomas con columna de cobertura", "0", len(con), False)
    cifra("el reporte dice que van sin la columna", "van sin la columna `cobertura_aoi`",
          "van sin la columna `cobertura_aoi`" if not con else "CON cobertura")


# ── 1. libro ─────────────────────────────────────────────────────────────
def libro() -> Dict[str, Any]:
    base = RAIZ / "campanas" / "L2_obstaculo_2"
    cab = json.loads((base / "campana.json").read_text(encoding="utf-8"))
    filas = leer(base / "libro.csv")
    res = sorted((f for f in filas if f["tipo"] == "resultado"), key=lambda f: int(f["intento"]))
    k_max = len(res)
    incl = [int(f["intento"]) for f in res if f["incluida"] == "1"]
    corr = [f for f in res if f["estado"] == "corrida"]
    cifra("intentos e incluidas", "**73/100 intentos y 30/50 incluidas**",
          f"**{k_max}/{cab['tope_intentos']} intentos y {len(incl)}/{cab['meta']} incluidas**")
    cifra("corridas", "con 56 corridas", f"con {len(corr)} corridas")
    cifra("contactos, frenos y pares",
          "**0 tomas con contacto, 0 frenos de respaldo y 0 pares de agentes a < 0.15 m**",
          f"**{sum(f['contacto'] == '1' for f in res)} tomas con contacto, "
          f"{sum(int(float(f['frenos'] or 0)) > 0 for f in res)} frenos de respaldo y "
          f"{sum(int(float(f['colisiones_015'] or 0)) for f in res)} pares de agentes a < 0.15 m**")
    todas("contactos en todo el texto", r"\d+ tomas con contacto", f"{sum(f['contacto'] == '1' for f in res)} tomas con contacto")
    todas("frenos de respaldo en todo el texto", r"\d+ frenos de respaldo", f"{sum(int(float(f['frenos'] or 0)) > 0 for f in res)} frenos de respaldo")
    todas("pares en todo el texto", r"\d+ pares de agentes a < 0\.15 m",
          f"{sum(int(float(f['colisiones_015'] or 0)) for f in res)} pares de agentes a < 0.15 m")
    todas("intentos en todo el texto", r"\d+/100 intentos", f"{k_max}/100 intentos")
    todas("incluidas en todo el texto", r"\d+/50 incluidas", f"{len(incl)}/50 incluidas")
    abierta = not any(f["tipo"] == "cierre_campana" for f in filas) and not (base / "campana.lock").exists()
    cifra("campaña abierta", "sigue ABIERTA", "sigue ABIERTA" if abierta else "CERRADA", False)
    sem_ok = all(int(f["semilla"]) == int(cab["semilla_base"]) + int(f["intento"]) - 1
                 for f in filas if f["tipo"] in ("reserva", "resultado"))
    cifra("regla de semillas", "semilla = 422000 + intento − 1 en todos los intentos",
          f"semilla = {cab['semilla_base']} + intento − 1 en todos los intentos" if sem_ok else "FALLA")
    # Período.
    per = [f for f in res if int(f["intento"]) >= 18]
    cifra("período: intentos", "se usaron los intentos 18–73", f"se usaron los intentos {per[0]['intento']}–{per[-1]['intento']}")
    cifra("período: totales", "56 intentos, 42 corridas y 23 incluidas",
          f"{len(per)} intentos, {sum(f['estado'] == 'corrida' for f in per)} corridas y "
          f"{sum(f['incluida'] == '1' for f in per)} incluidas")
    s0611 = [f for f in res if 38 <= int(f["intento"]) <= 73]
    i0611 = sum(f["incluida"] == "1" for f in s0611)
    cifra("06-11: incluidas y ritmo", "dio 18 incluidas en 36 intentos (50 %)",
          f"dio {i0611} incluidas en {len(s0611)} intentos ({100 * i0611 / len(s0611):.0f} %)")
    ritmos = {}
    for dia, (a, b) in {"21-10": (1, 17), "23-10": (18, 25), "04-11": (26, 37), "06-11": (38, 73)}.items():
        rr = [f for f in res if a <= int(f["intento"]) <= b]
        ritmos[dia] = sum(f["incluida"] == "1" for f in rr) / len(rr)
    cifra("06-11: el mejor día de la campaña", "el mejor día de la campaña", "el mejor día de la campaña"
          if max(ritmos, key=ritmos.get) == "06-11" else ritmos)
    por_ses = defaultdict(list)
    for f in res:
        por_ses[f["id_sesion"]].append(f)
    tasas = {sid: sum(f["incluida"] == "1" for f in ff) / len(ff) for sid, ff in por_ses.items()}
    iguales = [sid for sid, v in tasas.items() if abs(v - tasas["L2_20261106_193852"]) < 1e-12 and sid != "L2_20261106_193852"]
    otra = por_ses[iguales[0]] if len(iguales) == 1 and max(tasas.values()) <= tasas["L2_20261106_193852"] else []
    cifra("por sesión, el empate", "Por sesión, iguala a la de las 13:48 del 21-10, que dio 5 de 10",
          f"Por sesión, iguala a la de las {iguales[0][12:14]}:{iguales[0][14:16]} del 21-10, que dio "
          f"{sum(f['incluida'] == '1' for f in otra)} de {len(otra)}" if otra else iguales)
    # d_min.
    d_corr = [float(f["d_min_obst_medida"]) for f in corr]
    d_inc = [float(f["d_min_obst_medida"]) for f in res if f["incluida"] == "1"]
    cifra("d_min de las corridas", "en las 56 corridas de la campaña, entre 0.2648 y 0.6415 m",
          f"en las {len(d_corr)} corridas de la campaña, entre {min(d_corr):.4f} y {max(d_corr):.4f} m")
    cifra("d_min de las incluidas", "en las 30 incluidas, entre 0.2648 y 0.4217 m, con mediana 0.3177 m",
          f"en las {len(d_inc)} incluidas, entre {min(d_inc):.4f} y {max(d_inc):.4f} m, con mediana {st.median(d_inc):.4f} m")
    k_min = min(corr, key=lambda f: float(f["d_min_obst_medida"]))
    cifra("la menor", "La menor, 0.2648 m, fue en el intento 71, sin contacto",
          f"La menor, {float(k_min['d_min_obst_medida']):.4f} m, fue en el intento {k_min['intento']}, sin contacto")
    # Tabla de intentos 18–73: semilla, estado, válida/incluida y d_min por fila.
    estados = {"corrida": "corrida", "sin_correr": "sin correr", "parada_colocacion": "parada en la colocación",
               "interrumpida": "interrumpida"}
    for f in per:
        k = int(f["intento"])
        vi = ("sí / **sí**" if f["valido"] == "1" else "no / no") if f["estado"] == "corrida" else "— / no"
        d = f"{float(f['d_min_obst_medida']):.4f}" if f["d_min_obst_medida"] else "—"
        pref = f"| {k} | {f['semilla']} | {estados[f['estado']]} | {vi} | "
        ok = any(l.startswith(pref) and l.rstrip().endswith(f"| {d} |") for l in TEXTO.splitlines())
        CIFRAS.append((f"tabla de intentos, fila {k}", pref + "… " + d,
                       pref + "… " + d if ok else "FILA AUSENTE O DISTINTA", False))
    # Coordenadas de los congelamientos de la tabla y del §6, desde el motivo del libro.
    cong = []
    for f in per:
        m = re.search(r"agente (\d) \(robot (\d)\) sigue sin captura.*pose congelada en \(([\d.]+), ([\d.]+)\)", f["motivo"])
        if m:
            cong.append((int(f["intento"]), m.group(2), m.group(3), m.group(4)))
            esperado = f"marcador {m.group(2)} congelado en ({m.group(3)}, {m.group(4)})"
            cifra(f"motivo del {f['intento']}", esperado, esperado
                  if esperado in next(l for l in TEXTO.splitlines() if l.startswith(f"| {f['intento']} | ")) else "DISTINTO", False)
    # Motivos de los que no corrieron: los números del libro tienen que estar en la celda.
    for f in per:
        if f["estado"] not in ("sin_correr", "parada_colocacion"):
            continue
        k, m, celda = int(f["intento"]), f["motivo"], celda_motivo(int(f["intento"]))
        fichas = [menos(x) + " cm de su círculo" for x in re.findall(r"([+-]\d+(?:\.\d+)?) cm de su círculo", m)]
        fichas += [menos(x) + "° de la tangente" for x in re.findall(r"([+-]\d+)° de la tangente", m)]
        fichas += [f"el {r_} a {x} cm" for r_, x in re.findall(r"\(robot (\d)\): a (\d+) cm de su blanco", m)]
        fichas += [f"se movió {x} cm" for x in re.findall(r"se movió ([\d.]+) cm", m)]
        fichas += [f"(robot {x})" for x in re.findall(r"robot\(s\) (\d)", m)]
        fichas += [f"del {x} caído" for x in re.findall(r"obstáculo \(robot (\d)\) caído", m)]
        cifra(f"motivo del {k} contra el libro", " · ".join(fichas) or "(sin cifras)",
              " · ".join(fichas) if fichas and all(x in celda for x in fichas) else f"celda «{celda}»", False)
    # El 51 (corrida): el robot y el 0 % salen del libro. Agentes 0–4 = robots 1, 5, 8, 2, 9 (orden congelado).
    f51 = next(f for f in per if f["intento"] == "51")
    m51 = re.search(r"agente (\d) NO SIGUE el comando: recorrió el (\d+) % de lo comandado", f51["motivo"])
    robot_de = {"0": "1", "1": "5", "2": "8", "3": "2", "4": "9"}
    esp51 = f"el robot {robot_de[m51.group(1)]} no sigue el comando ({m51.group(2)} %)" if m51 else "SIN MOTIVO"
    cifra("motivo del 51 contra el libro", esp51, esp51 if esp51 in celda_motivo(51) else f"celda «{celda_motivo(51)}»", False)
    cifra("resumen: congelamientos que pararon tomas", "De los 14 congelamientos que pararon tomas",
          f"De los {len(cong)} congelamientos que pararon tomas")
    # Pausas.
    pausas = {int(f["intento"]): f["parada_respuesta"] for f in filas if f["tipo"] == "pausa"}
    cifra("pausas del período", 'se contestó "siguió" en el 24 y el 36, y "detenida" en el 37',
          f'se contestó "{pausas[24]}" en el 24 y el 36, y "{pausas[37]}" en el 37'
          if pausas.get(24) == pausas.get(36) == "siguió" else pausas)
    return {"cab": cab, "filas": filas, "res": res, "per": per, "cong": cong}


# ── 2. sesiones del período (libro) ──────────────────────────────────────
def sesiones_libro(info: Dict[str, Any]) -> None:
    filas = info["filas"]
    ap = {f["id_sesion"]: f for f in filas if f["tipo"] == "apertura" and f["fecha"] >= "2026-10-23"}
    ci = {f["id_sesion"]: f for f in filas if f["tipo"] == "cierre_sesion" and f["fecha"] >= "2026-10-23"}
    rango = defaultdict(list)
    for f in info["res"]:
        rango[f["id_sesion"]].append(int(f["intento"]))
    cifra("lanzamientos del período", "11", len(ap), False)
    for sid, a in ap.items():
        c = ci[sid]
        fin = a["motivo"].split()[-1]
        ks = rango.get(sid, [])
        intentos = f"{min(ks)}–{max(ks)}" if ks else "—"
        pref = f"| `{sid}` | {hhmmss(a['fecha'])} | {hhmmss(c['fecha'])} | {fin} | {intentos} | "
        ok = any(l.startswith(pref) for l in TEXTO.splitlines())
        CIFRAS.append((f"sesión {sid}", pref, pref if ok else "FILA AUSENTE O DISTINTA", False))
        motivo = c["motivo"]
        clave = ("timed out" if "timed out" in motivo else "robot 2" if "robot 2" in motivo else
                 "interrumpida (Ctrl+C)" if "Ctrl+C" in motivo else '"fin de la sesión"')
        linea = next((l for l in TEXTO.splitlines() if l.startswith(pref)), "")
        cifra(f"motivo de cierre de {sid}", clave, clave if clave in linea else "DISTINTO", False)
    cifra("CSV de la sesión del 23-10", "llevan el prefijo `20261023_205008`",
          "llevan el prefijo `20261023_205008`" if (RAIZ / "sesiones" / "20261023_205008_L2_tomas.csv").is_file() else "FALTA")
    # Minutos por intento el 06-11.
    a, c = ap["L2_20261106_193852"], ci["L2_20261106_193852"]
    mins = (datetime.fromisoformat(c["fecha"]) - datetime.fromisoformat(a["fecha"])).total_seconds() / 60
    cifra("06-11: intervalo de la sesión", "entre las 19:38:52 y las 20:48:09",
          f"entre las {hhmmss(a['fecha'])} y las {hhmmss(c['fecha'])}")
    PARES["sesión del 06-11"] = f"entre las {hhmmss(a['fecha'])} y las {hhmmss(c['fecha'])}"
    cifra("06-11: minutos por intento", "unos 1.9 min por intento", f"unos {mins / 36:.1f} min por intento")


# ── 3. pérdidas y ritmo ──────────────────────────────────────────────────
def perdidas_y_ritmo(info: Dict[str, Any]) -> None:
    res = info["res"]

    def causa(f: Dict[str, str]) -> str:
        m, e = f["motivo"], f["estado"]
        if e == "interrumpida":
            return "interrumpido"
        if e == "sin_correr":
            return "colocación del 4" if m.startswith("obstáculo a") else "colocación de agentes"
        if m.startswith("marcador CONGELADO"):
            return "congelado"
        if m.startswith("antigüedad de pose"):
            return "antigüedad"
        if e == "corrida" and m.startswith("OBSTÁCULO: marcador del obstáculo CONGELADO"):
            return "repetición simultánea"            # la toma 15 del 21-10 (reporte anterior, §8.5)
        return "robots/enlaces/obstáculo"

    no = [f for f in res if f["incluida"] != "1"]
    per = [f for f in no if int(f["intento"]) >= 18]
    c = defaultdict(list)
    for f in per:
        c[causa(f)].append(int(f["intento"]))
    cifra("período: no incluidos", "Los 33 intentos del período que no se incluyeron", f"Los {len(per)} intentos del período que no se incluyeron")
    cifra("seguimiento: congelado", f"marcador congelado, 14: {lista_es(c['congelado'])}",
          f"marcador congelado, {len(c['congelado'])}: {lista_es(c['congelado'])}")
    cifra("seguimiento: antigüedad", "antigüedad de pose, 4: 23, 30, 31 y 43",
          f"antigüedad de pose, {len(c['antigüedad'])}: {lista_es(c['antigüedad'])}")
    cifra("seguimiento total", "**seguimiento, 18:**", f"**seguimiento, {len(c['congelado']) + len(c['antigüedad'])}:**")
    cifra("colocación", "7 porque el 4 no quedó en su arranque (18, 26, 27, 28, 38, 39 y 40) y 1 por los agentes (41)",
          f"{len(c['colocación del 4'])} porque el 4 no quedó en su arranque ({lista_es(c['colocación del 4'])}) "
          f"y {len(c['colocación de agentes'])} por los agentes ({lista_es(c['colocación de agentes'])})")
    cifra("obstáculo, enlaces y batería", "**obstáculo, enlaces y batería, 4:**",
          f"**obstáculo, enlaces y batería, {len(c['robots/enlaces/obstáculo'])}:**")
    cifra("obstáculo, enlaces y batería: cuáles",
          'el 24 (el 4 "NO FRENA"), el 36 (enlace del 4), el 37 (enlace del 5) y el 51',
          'el 24 (el 4 "NO FRENA"), el 36 (enlace del 4), el 37 (enlace del 5) y el 51'
          if c["robots/enlaces/obstáculo"] == [24, 36, 37, 51] else c["robots/enlaces/obstáculo"])
    ns, nc = len(c["congelado"]) + len(c["antigüedad"]), len(c["colocación del 4"]) + len(c["colocación de agentes"])
    cifra("resumen: los 33", "18 por el seguimiento (14 por marcador congelado y 4 por antigüedad de pose), 8 sin correr por la colocación (7 por el 4 y 1 por los agentes), 4 por el obstáculo, los enlaces o la batería, y 3 interrumpidos",
          f"{ns} por el seguimiento ({len(c['congelado'])} por marcador congelado y {len(c['antigüedad'])} por antigüedad de pose), "
          f"{nc} sin correr por la colocación ({len(c['colocación del 4'])} por el 4 y {len(c['colocación de agentes'])} por los agentes), "
          f"{len(c['robots/enlaces/obstáculo'])} por el obstáculo, los enlaces o la batería, y {len(c['interrumpido'])} interrumpidos")
    cifra("interrumpidos", "**interrumpidos con Ctrl+C, 3:** 25, 35 y 73",
          f"**interrumpidos con Ctrl+C, {len(c['interrumpido'])}:** {lista_es(c['interrumpido'])}")
    ct = Counter(causa(f) for f in no)
    seg = ct["congelado"] + ct["antigüedad"] + ct["repetición simultánea"]
    col = ct["colocación del 4"] + ct["colocación de agentes"]
    cifra("campaña: no incluidos",
          "los 43 no incluidos se reparten así: 24 por el seguimiento, 8 por la colocación, 6 por los robots, los enlaces o el obstáculo, y 5 interrumpidos",
          f"los {len(no)} no incluidos se reparten así: {seg} por el seguimiento, {col} por la colocación, "
          f"{ct['robots/enlaces/obstáculo']} por los robots, los enlaces o el obstáculo, y {ct['interrumpido']} interrumpidos")
    # Por día.
    for dia, (a, b) in {"21-10 (reporte anterior)": (1, 17), "23-10": (18, 25), "04-11": (26, 37), "06-11": (38, 73)}.items():
        rr = [f for f in res if a <= int(f["intento"]) <= b]
        nc = sum(f["estado"] == "corrida" for f in rr)
        ni = sum(f["incluida"] == "1" for f in rr)
        fila(f"ritmo {dia}", f"| {dia} | {a}–{b} | {nc} | {ni} | {100 * ni / len(rr):.0f} % |")
    n, k = len(res), sum(f["incluida"] == "1" for f in res)
    fila("ritmo campaña", f"| **campaña** | **1–{n}** | **{sum(f['estado'] == 'corrida' for f in res)}** | **{k}** | **{100 * k / n:.0f} %** |")
    # Wilson y proyección.
    z = 1.959963984540054
    p = k / n
    d = 1 + z * z / n
    cen = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    lo, hi = cen - h, cen + h
    todas("IC de Wilson en todo el texto", r"IC95 de Wilson \[[\d.]+, [\d.]+\]", f"IC95 de Wilson [{lo:.3f}, {hi:.3f}]")
    cifra("ritmo e IC", "30/73 = 41 %, con IC95 de Wilson [0.305, 0.526]",
          f"{k}/{n} = {100 * p:.0f} %, con IC95 de Wilson [{lo:.3f}, {hi:.3f}]")
    todas("ritmo en todo el texto", r"\d+/\d+ = \d+ %", f"{k}/{n} = {100 * p:.0f} %")
    queda = 100 - n
    cifra("resumen: quedan", "Con los 27 intentos que quedan", f"Con los {queda} intentos que quedan")
    cifra("al tope", "los 27 intentos que quedan dan unas 11 incluidas más: unas 41 al tope. Con el IC, entre 38 y 44",
          f"los {queda} intentos que quedan dan unas {queda * p:.0f} incluidas más: unas {k + queda * p:.0f} al tope. "
          f"Con el IC, entre {k + queda * lo:.0f} y {k + queda * hi:.0f}")
    falta = 50 - k
    cifra("meta", "La meta de 50 pide 20 de 27 (74 %)", f"La meta de 50 pide {falta} de {queda} ({100 * falta / queda:.0f} %)")
    cifra("resumen: meta", "Llegar a 50 exige 20 de 27", f"Llegar a 50 exige {falta} de {queda}")
    def cola(q: float) -> float:          # P(X ≥ falta), X ~ Binomial(queda, q)
        return sum(math.comb(queda, j) * q ** j * (1 - q) ** (queda - j) for j in range(falta, queda + 1))
    p1, p2, p3 = cola(p), cola(0.5), cola(hi)
    cifra("binomial", "la probabilidad de llegar es 0.0005 al ritmo puntual, 0.010 con un ritmo de 50 % y 0.019 con el límite superior del IC",
          f"la probabilidad de llegar es {p1:.4f} al ritmo puntual, {p2:.3f} con un ritmo de 50 % y {p3:.3f} con el límite superior del IC")
    cifra("resumen: binomial", "Al ritmo de la campaña la probabilidad es 0.0005, y 0.019 con el límite superior del IC",
          f"Al ritmo de la campaña la probabilidad es {p1:.4f}, y {p3:.3f} con el límite superior del IC")
    cifra("resumen: tope", "el tope daría unas 41 incluidas (entre 38 y 44 con el IC)",
          f"el tope daría unas {k + queda * p:.0f} incluidas (entre {k + queda * lo:.0f} y {k + queda * hi:.0f} con el IC)")
    # Reintentos de colocación (col_reintentos de las tablas de tomas).
    reint = {}
    for s in SESIONES.values():
        for f in leer(RAIZ / "sesiones" / f"{s}_L2_tomas.csv"):
            reint[int(f["intento_campana"])] = int(f["col_reintentos"] or 0)
    obst = [int(f["intento"]) for f in res if f["estado"] == "sin_correr" and f["motivo"].startswith("obstáculo a")
            and int(f["intento"]) >= 18]
    cifra("los gastados por el 4 agotaron las 6 vueltas", "Los 7 intentos gastados por el 4 agotaron las 6 vueltas",
          f"Los {len(obst)} intentos gastados por el 4 agotaron las 6 vueltas" if all(reint.get(k_) == 5 for k_ in obst) else
          {k_: reint.get(k_) for k_ in obst})
    cifra("el 29", "El 29 entró en la última vuelta (`col_reintentos` = 5)",
          f"El 29 entró en la última vuelta (`col_reintentos` = {reint.get(29)})")
    cifra("el 41", "41 con col_reintentos 5", f"41 con col_reintentos {reint.get(41)}", False)


# ── 4. CSV: lazo, rachas y retrocesos ────────────────────────────────────
def csv_sesiones(info: Dict[str, Any]) -> None:
    rachas = []                     # [día, toma, robot, paso_ini, paso_fin, x, y, último paso de la toma]
    abierta: Dict[Tuple[str, int, str], List[Any]] = {}
    pos_parcial: Dict[str, Tuple[float, float]] = {}
    simult, parciales = [], []
    tabla7 = {}
    for dia, s in SESIONES.items():
        obst = defaultdict(list)
        for f in leer(RAIZ / "sesiones" / f"{s}_L2_obstaculo.csv"):
            obst[int(f["toma"])].append((int(f["paso"]), float(f["t"])))
        n = g150 = 0
        gmax = 0.0
        for filas in obst.values():
            filas.sort()
            for (_, t0), (_, t1) in zip(filas, filas[1:]):
                dt = (t1 - t0) * 1000
                n += 1
                g150 += dt > 150
                gmax = max(gmax, dt)
        tomas = leer(RAIZ / "sesiones" / f"{s}_L2_tomas.csv")
        p95 = st.mean(float(f["ciclo_p95_ms"]) for f in tomas if f.get("ciclo_p95_ms"))
        tabla7[dia] = (g150, n, gmax, p95)
        dec = defaultdict(dict)
        for f in leer(RAIZ / "sesiones" / f"{s}_L2_decisiones.csv"):
            dec[(int(f["episodio"]), int(f["paso"]))][f["robot"]] = (f["pose_env_x"], f["pose_env_y"], f["pose_env_th"])
        ultimo = defaultdict(int)
        for (toma, paso) in dec:
            ultimo[toma] = max(ultimo[toma], paso)
        for (toma, paso), poses in sorted(dec.items()):
            prev = dec.get((toma, paso - 1))
            if not prev:
                continue
            rep = [r for r in poses if prev.get(r) == poses[r]]
            if len(rep) == len(poses) == 5:
                simult.append((dia, toma, paso))
                continue
            if len(rep) >= 2:
                parciales.append((dia, toma, paso, tuple(sorted(rep))))
                for r in rep:
                    pos_parcial[r] = (float(poses[r][0]), float(poses[r][1]))
            for r in rep:
                x, y = float(poses[r][0]), float(poses[r][1])
                clave = (dia, toma, r)
                if clave in abierta and abierta[clave][4] == paso - 1:
                    abierta[clave][4] = paso
                else:
                    nueva = [dia, toma, r, paso, paso, x, y, ultimo[toma]]
                    rachas.append(nueva)
                    abierta[clave] = nueva
        # Retrocesos por estado.
        est = Counter()
        for f in tomas:
            for m in re.finditer(r"(a\d):(\d+)-(\d+)\(([\d.]+)s,([\d.]+)cm,(\w+)\)", f.get("retrocesos_detalle") or ""):
                est[m.group(6)] += 1
        fila(f"retrocesos {dia}", f"| {dia} | {est['recuperada']} | {est['sigue_congelada']} | "
                                  f"{est['episodio_abortado']} | {est['fin_del_episodio']} |")
    # Tabla del §7 (filas de los CSV).
    t = tabla7
    fila("intervalos > 150 ms", f"| intervalos del lazo > 150 ms | {t['23-10'][0]} de {t['23-10'][1]} | "
                                f"{t['04-11'][0]} de {t['04-11'][1]} | — | {t['06-11'][0]} de {t['06-11'][1]} |")
    fila("intervalo máximo", f"| intervalo máximo (ms) | {t['23-10'][2]:.1f} | {t['04-11'][2]:.1f} | — | {t['06-11'][2]:.1f} |")
    fila("ciclo p95 medio", f"| ciclo p95 medio por toma (ms) | {t['23-10'][3]:.1f} | {t['04-11'][3]:.1f} | — | {t['06-11'][3]:.1f} |")
    cifra("resumen: intervalos", "0 intervalos > 150 ms en las tres sesiones con tomas",
          f"{sum(v[0] for v in t.values())} intervalos > 150 ms en las tres sesiones con tomas")
    cifra("resumen: ciclo", "El ciclo p95 medio fue 11.8 ms el 23-10 y 12.1 ms el 06-11",
          f"El ciclo p95 medio fue {t['23-10'][3]:.1f} ms el 23-10 y {t['06-11'][3]:.1f} ms el 06-11")
    cifra("§7: ciclo 04-11", "36.2", f"{t['04-11'][3]:.1f}", False)
    # Repeticiones simultáneas.
    cifra("simultáneas de 5", "ningún paso del período con los 5 agentes repetidos a la vez",
          "ningún paso del período con los 5 agentes repetidos a la vez" if not simult else simult)
    par = [p for p in parciales]
    ok = (len(par) == 3 and all(p[0] == "04-11" and p[1] == 32 and p[3] == ("5", "9") for p in par))
    cifra("parciales", "El 04-11, en la toma 32, hubo 3 pasos con 2 agentes repetidos a la vez: el 5 en (2.36, 2.70) y el 9 en (0.24, 0.30)",
          f"El 04-11, en la toma 32, hubo 3 pasos con 2 agentes repetidos a la vez: el 5 en ({pos_parcial['5'][0]:.2f}, "
          f"{pos_parcial['5'][1]:.2f}) y el 9 en ({pos_parcial['9'][0]:.2f}, {pos_parcial['9'][1]:.2f})" if ok else par)
    tomas04 = leer(RAIZ / "sesiones" / "20261104_120744_L2_tomas.csv")
    fall04 = sum(int(float(f["poses_fallidas"] or 0)) for f in tomas04 if f.get("poses_fallidas") not in (None, ""))
    cifra("04-11: tomas sin consultas fallidas", "Sus 6 tomas terminaron antes del corte de las 12:31:59, sin consultas de pose fallidas",
          f"Sus {sum(1 for f in tomas04 if f.get('ciclo_p95_ms'))} tomas terminaron antes del corte de las 12:31:59, sin consultas de pose fallidas"
          if fall04 == 0 else fall04)
    # Interior (> 1.0 m de las paredes).
    inter = [r for r in rachas if d_pared(r[5], r[6]) > 1.0]
    xs, ys = [r[5] for r in inter], [r[6] for r in inter]
    cifra("zona interior del período", "En el período: x entre 1.462 y 1.685, y entre 1.058 y 1.328",
          f"En el período: x entre {min(xs):.3f} y {max(xs):.3f}, y entre {min(ys):.3f} y {max(ys):.3f}")
    x0, x1, y0, y1 = min(xs + [1.456]), max(xs + [1.548]), min(ys + [1.213]), max(ys + [1.281])
    cifra("zona interior con el 21-10", "**x entre 1.456 y 1.685, y entre 1.058 y 1.328**",
          f"**x entre {x0:.3f} y {x1:.3f}, y entre {y0:.3f} y {y1:.3f}**")
    cifra("resumen: zona interior", "x entre 1.456 y 1.685, y entre 1.058 y 1.328 (§6)",
          f"x entre {x0:.3f} y {x1:.3f}, y entre {y0:.3f} y {y1:.3f} (§6)")
    cifra("21-10 en el reporte anterior", "x 1.456–1.548, y 1.213–1.281",
          "x 1.456–1.548, y 1.213–1.281" if "x entre 1.456 y 1.548, y entre 1.213 y 1.281"
          in texto_de(RAIZ / "documentos" / "REPORTE_2026-10-22_campana_L2.md") else "NO COINCIDE")
    def a_caja(x: float, y: float) -> float:
        return math.hypot(max(1.456 - x, 0, x - 1.548), max(1.213 - y, 0, y - 1.281))
    g1 = [a_caja(r[5], r[6]) for r in inter if r[0] in ("23-10", "04-11")]
    g2 = [a_caja(r[5], r[6]) for r in inter if r[0] == "06-11"]
    d1 = f"{math.floor(min(g1) * 100)}–{math.ceil(max(g1) * 100)} cm"
    d2 = f"{math.floor(min(g2) * 100)}–{math.ceil(max(g2) * 100)} cm"
    cifra("grupos: 23-10 y 04-11", "el robot 8 quedó a 3–5 cm de la zona interior del 21-10", f"el robot 8 quedó a {d1} de la zona interior del 21-10")
    cifra("grupos: 06-11", "quedaron a 10–20 cm de esa zona", f"quedaron a {d2} de esa zona")
    cifra("resumen: grupos", "el 23-10 y el 04-11 a 3–5 cm de la zona interior del 21-10, y el 06-11 a 10–20 cm",
          f"el 23-10 y el 04-11 a {d1} de la zona interior del 21-10, y el 06-11 a {d2}")
    cifra("06-11 a menos de 1.2 m de la pared", "a menos de 1.2 m de la pared y = 0",
          "a menos de 1.2 m de la pared y = 0" if all(r[6] < 1.2 and r[6] == min(r[5], 3 - r[5], r[6], 3 - r[6])
                                                     for r in inter if r[0] == "06-11") else "NO")
    prev_txt = texto_de(RAIZ / "documentos" / "REPORTE_2026-10-22_campana_L2.md")
    m21 = re.search(r"Se congelaron dos marcadores distintos: el (\d) en las tomas [\d y]+, y el (\d) en la", prev_txt)
    robots = sorted({r[2] for r in inter} | ({m21.group(1), m21.group(2)} if m21 else set()))
    cifra("zona interior: robots", "con los robots 1, 8 y 9", f"con los robots {lista_es(robots)}")
    por_toma = defaultdict(list)
    for r in inter:
        por_toma[(r[0], r[1], r[2])].append(r)
    esperadas = {("23-10", 23, "8"): "(1.56, 1.31)", ("04-11", 30, "8"): "(1.46, 1.32) y (1.48, 1.33)",
                 ("06-11", 48, "1"): "(1.67, 1.07) y (1.67, 1.06)", ("06-11", 52, "8"): "(1.62, 1.14)",
                 ("06-11", 66, "9"): "(1.68, 1.08)"}
    for (dia, toma, robot), rr in sorted(por_toma.items()):
        pos = lista_es([f"({r[5]:.2f}, {r[6]:.2f})" for r in rr])
        fin = "en la parada por antigüedad de pose" if rr[-1][4] == rr[-1][7] else "recuperada"
        if dia == "04-11":
            fin = "la segunda, en la parada por antigüedad de pose"
        if len(rr) == 2 and dia == "06-11":
            fin = "recuperadas"
        fila(f"zona interior {dia} {toma}", f"| {dia} | {toma} | {robot} | {pos} | {fin} |")
    cifra("zona interior: tomas", "5 filas", f"{len(por_toma)} filas" if set(por_toma) == set(esperadas) else por_toma, False)
    # Antigüedad: rachas de 2 pasos hasta el fin.
    ant = {"23-10": 23, "04-11": None, "06-11": 43}
    fines = [(r[0], r[1], r[2], r[4] - r[3] + 1, round(r[5], 2), round(r[6], 2))
             for r in rachas if r[4] == r[7] and r[4] - r[3] + 1 == 2]
    esperado = [("23-10", 23, "8", 2, 1.56, 1.31), ("04-11", 30, "8", 2, 1.48, 1.33),
                ("04-11", 31, "9", 2, 0.59, 0.37), ("06-11", 43, "9", 2, 0.29, 0.46)]
    cifra("paradas por antigüedad y rachas de 2 pasos",
          "Las 4 paradas por antigüedad de pose del período** (23, 30, 31 y 43) terminaron con una racha de 2 pasos",
          "Las 4 paradas por antigüedad de pose del período** (23, 30, 31 y 43) terminaron con una racha de 2 pasos"
          if sorted(fines) == sorted(esperado) else fines)
    cifra("antigüedad: posiciones del 9", "en (0.59, 0.37) y (0.29, 0.46)", "en (0.59, 0.37) y (0.29, 0.46)"
          if ("04-11", 31, "9", 2, 0.59, 0.37) in fines and ("06-11", 43, "9", 2, 0.29, 0.46) in fines else "NO", True)
    d00 = [math.hypot(x, y) for (_, _, r_, _, x, y) in fines if r_ == "9"]
    cifra("antigüedad: distancia a (0, 0)", "a 0.5–0.7 m de ella", f"a {min(d00):.1f}–{max(d00):.1f} m de ella")
    for (_, toma, r_, _, x, y) in fines:
        esperado_m = f"marcador {r_} repetido en ({x:.2f}, {y:.2f})"
        cifra(f"motivo del {toma} contra los CSV", esperado_m, esperado_m if esperado_m in celda_motivo(toma) else f"celda «{celda_motivo(toma)}»", False)
    del ant
    # Punto (0.95, 2.80) y esquina, en el 06-11.
    pto = [r for r in rachas if r[0] == "06-11" and math.dist((r[5], r[6]), (0.95, 2.80)) <= 0.04]
    paran = sorted({r[1] for r in pto if r[4] == r[7]})
    recup = [r[1] for r in pto if r[4] != r[7]]
    robs = []
    for r in pto:
        if r[2] not in robs:
            robs.append(r[2])
    px, py = [r[5] for r in pto], [r[6] for r in pto]
    cifra("punto (0.95, 2.80)",
          "9 rachas con 3 robots (1, 9 y 2), en x entre 0.92 y 0.97 e y entre 2.78 y 2.82. 3 pararon la toma (49, 50 y 63) y 6 se recuperaron (en las tomas 45, 47, 55 ×2, 64 y 72)",
          f"{len(pto)} rachas con {len(robs)} robots ({lista_es(robs)}), en x entre {min(px):.2f} y {max(px):.2f} e y entre "
          f"{min(py):.2f} y {max(py):.2f}. {len(paran)} pararon la toma ({lista_es(paran)}) y {len(recup)} se recuperaron (en las tomas "
          f"{lista_es([str(x) if recup.count(x) == 1 else f'{x} ×{recup.count(x)}' for x in sorted(set(recup))])})")
    # 04-11: puntos repetidos de un solo robot.
    r5 = [r for r in rachas if r[0] == "04-11" and r[1] == 32 and r[2] == "5"]
    r9 = [r for r in rachas if r[0] == "04-11" and r[2] == "9" and r[1] in (32, 34) and d_pared(r[5], r[6]) < 0.4 and r[5] < 0.5]
    tramos5 = [[r[3], r[4]] for r in r5]
    cifra("04-11: el 5 en la toma 32", "el 5, cuatro veces en la toma 32 en (2.36–2.37, 2.70–2.72), todas recuperadas",
          f"el 5, {'cuatro' if len(tramos5) == 4 else len(tramos5)} veces en la toma 32 en ({min(r[5] for r in r5):.2f}–"
          f"{max(r[5] for r in r5):.2f}, {min(r[6] for r in r5):.2f}–{max(r[6] for r in r5):.2f}), todas recuperadas"
          if all(r[4] != r[7] for r in r5) else "alguna no se recuperó")
    p32 = [r for r in r9 if r[1] == 32]
    p34 = [r for r in r9 if r[1] == 34]
    cifra("04-11: el 9", "el 9 en (0.24, 0.30), donde paró la 32, y en (0.25, 0.31) en la 34, recuperada",
          f"el 9 en ({p32[-1][5]:.2f}, {p32[-1][6]:.2f}), donde paró la 32, y en ({p34[0][5]:.2f}, {p34[0][6]:.2f}) en la 34, recuperada"
          if p32 and p34 and p32[-1][4] == p32[-1][7] and p34[0][4] != p34[0][7] else (p32, p34))
    esq = [r for r in rachas if r[0] == "06-11" and 0.20 <= round(r[5], 2) <= 0.27 and 2.77 <= round(r[6], 2) <= 2.83]
    caja_esq = (f"({min(r[5] for r in esq):.2f}–{max(r[5] for r in esq):.2f}, "
                f"{min(r[6] for r in esq):.2f}–{max(r[6] for r in esq):.2f})")
    cifra("esquina: caja", "la esquina (0.20–0.27, 2.77–2.83)", f"la esquina {caja_esq}")
    cifra("resumen: puntos", "cerca de (0.95, 2.80) y la esquina (0.20–0.27, 2.77–2.83)", f"cerca de (0.95, 2.80) y la esquina {caja_esq}"
          if len(pto) >= 9 else pto)
    cifra("esquina", "pararon ahí 3 tomas (42 y 45 con el robot 1, 70 con el 9)",
          f"pararon ahí {len([r for r in esq if r[4] == r[7]])} tomas (42 y 45 con el robot 1, 70 con el 9)"
          if sorted((r[1], r[2]) for r in esq if r[4] == r[7]) == [(42, "1"), (45, "1"), (70, "9")] else esq)
    # Paradas por congelamiento (libro) en la franja alta.
    cong = info["cong"]
    for k, robot, x, y in cong:
        fecha = "23-10" if k <= 25 else "04-11" if k <= 37 else "06-11"
        fila(f"§6 parada {k}", f"| {fecha} | {k} | {robot} | ({x}, {y}) |")
    pared_y = [c for c in cong if 3 - float(c[3]) <= 0.30]
    esquina = [c for c in pared_y if min(float(c[2]), 3 - float(c[2])) <= 0.30]
    lat = [c for c in cong if c not in pared_y and float(c[3]) > 1.5]
    abajo = [c for c in cong if c not in pared_y and c not in lat]
    ys = [float(c[3]) for c in pared_y]
    cifra("pared +y", "10 de los 14 fueron a ≤ 0.30 m de la pared +y (y entre 2.71 y 2.83); 4 de ellos, en una esquina",
          f"{len(pared_y)} de los {len(cong)} fueron a ≤ 0.30 m de la pared +y (y entre {min(ys):.2f} y {max(ys):.2f}); "
          f"{len(esquina)} de ellos, en una esquina")
    cifra("laterales", "Otros 3 fueron en la mitad alta, junto a una pared lateral: (0.21, 2.56), (2.71, 2.51) y (0.25, 2.41)",
          f"Otros {len(lat)} fueron en la mitad alta, junto a una pared lateral: " + lista_es([f"({c[2]}, {c[3]})" for c in lat])
          if all(min(float(c[2]), 3 - float(c[2])) <= 0.30 for c in lat) else lat)
    cifra("abajo", "El restante, cerca de la esquina (0, 0)", "El restante, cerca de la esquina (0, 0)"
          if len(abajo) == 1 and float(abajo[0][2]) < 0.5 and float(abajo[0][3]) < 0.5 else abajo)
    cifra("resumen: reparto", "10 fueron junto a la pared +y (4 de ellos en una esquina), 3 en la mitad alta junto a una pared lateral y 1 cerca de la esquina (0, 0)",
          f"{len(pared_y)} fueron junto a la pared +y ({len(esquina)} de ellos en una esquina), {len(lat)} en la mitad alta junto a una pared lateral y {len(abajo)} cerca de la esquina (0, 0)")
    cifra("del robot 9", "8 son del robot 9", f"{sum(r == '9' for _, r, _, _ in cong)} son del robot 9")
    INFO_CSV.update(tabla7=tabla7)


INFO_CSV: Dict[str, Any] = {}


# ── 5. consolas ──────────────────────────────────────────────────────────
def consolas() -> None:
    con = RAIZ / "consola"
    archivos = {"23-10": "consola_20261023_2129_sesiones.txt", "04-11 (mañana)": "consola_20261104_1242_sesion_y_caida.txt",
                "04-11 (12:51)": "consola_20261104_1259_chequeo_y_sesion.txt", "06-11": "consola_20261106_2048_sesion.txt"}
    datos = {}
    for k, a in archivos.items():
        t = texto_de(con / a)
        m = re.search(r"\[poses\] consultas: (\d+)\s+omitidas por tasa: \d+\s+fallidas: (\d+)\s+latencia: p50 ([\d.]+) ms · p95 ([\d.]+) ms · máx ([\d.]+) ms", t)
        rech = re.search(r"\[poses\] poses rechazadas por motivo: (.*)", t).group(1)
        inc = re.search(r"'inclinación': (\d+)", rech)
        dec = int(re.search(r"\[ruedas\] decisiones: (\d+)", t).group(1))
        tk = re.search(r"ticks que no alcanzaron su plazo: (\d+)", t)
        env = re.search(r"\[ruedas\] saturaciones: \d+\s+envíos fallidos: (.*?)\s+reconexiones", t).group(1)
        n_env = sum(int(v) for v in re.findall(r": (\d+)", env)) if env.strip() != "—" else 0
        ob = re.search(r"obstáculo \(robot 4\): conectado\s+envíos fallidos (\d+)", t)
        fr = int(re.search(r"frenados por pose vencida: (\d+)", t).group(1))
        datos[k] = dict(c=int(m.group(1)), f=int(m.group(2)), p50=m.group(3), p95=m.group(4), mx=m.group(5),
                        inc=int(inc.group(1)) if inc else 0, dec=dec, tk=int(tk.group(1)) if tk else None,
                        env=n_env, ob=int(ob.group(1)), fr=fr)
    orden = list(archivos)
    fila("consultas", "| consultas de poses | " + " | ".join(str(datos[k]["c"]) for k in orden) + " |")
    fila("fallidas", "| consultas fallidas | " + " | ".join(str(datos[k]["f"]) for k in orden) + " |")
    fila("latencias", "| latencia de poses p50 / p95 / máx (ms) | " +
         " | ".join(f"{datos[k]['p50']} / {datos[k]['p95']} / {datos[k]['mx']}" for k in orden) + " |")
    fila("inclinación", "| poses rechazadas por inclinación | " + " | ".join(str(datos[k]["inc"]) for k in orden) + " |")
    fila("decisiones", "| decisiones | " + " | ".join(str(datos[k]["dec"]) for k in orden) + " |")
    fila("ticks", "| ticks que no alcanzaron su plazo | " +
         " | ".join("—" if datos[k]["tk"] is None else str(datos[k]["tk"]) for k in orden) + " |")
    fila("ticks por decisión", "| ticks fuera de plazo por decisión | " +
         " | ".join("—" if datos[k]["tk"] is None else f"{datos[k]['tk'] / datos[k]['dec']:.2f}" for k in orden) + " |")
    fila("resets", "| resets de enlace de los agentes / del 4 | " +
         " | ".join(f"{datos[k]['env']} / {datos[k]['ob']}" for k in orden) + " |")
    # 21-10, de la consola de referencia del reporte anterior.
    ref = texto_de(con / "referencia_consola_20261021_1409.txt")
    decs = [int(x) for x in re.findall(r"\[ruedas\] decisiones: (\d+)", ref)]
    tks = [int(x) for x in re.findall(r"ticks que no alcanzaron su plazo: (\d+)", ref)]
    cifra("21-10: ticks por decisión", "ticks por decisión 0.90 y 0.81",
          f"ticks por decisión {tks[0] / decs[0]:.2f} y {tks[1] / decs[1]:.2f}")
    prev = texto_de(RAIZ / "documentos" / "REPORTE_2026-10-22_campana_L2.md")
    cifra("21-10: intervalos y ciclo (reporte anterior)", "intervalos > 150 ms 3 y 6, y ciclo p95 medio 23.4 y 23.6 ms",
          "intervalos > 150 ms 3 y 6, y ciclo p95 medio 23.4 y 23.6 ms"
          if "3 de 1698 > 150 ms" in prev and "6 de 3743 > 150 ms" in prev and "23.4 ms y 23.6 ms" in prev else "NO COINCIDE")
    cifra("resumen: 21-10", "(el 21-10 hubo 3 y 6)", "(el 21-10 hubo 3 y 6)" if "3 de 1698" in prev else "NO")
    cifra("resumen: ciclo 21-10", "contra 23.4 y 23.6 ms el 21-10", "contra 23.4 y 23.6 ms el 21-10" if "23.4 ms y 23.6 ms" in prev else "NO")
    vals = sorted([tks[0] / decs[0], tks[1] / decs[1]] + [datos[k]["tk"] / datos[k]["dec"] for k in orden if datos[k]["tk"]])
    v06 = datos["06-11"]["tk"] / datos["06-11"]["dec"]
    cifra("06-11 por decisión", "Por decisión (0.77) es la segunda más baja de las cinco sesiones con tomas: sólo el 23-10 (0.58) quedó más abajo",
          f"Por decisión ({v06:.2f}) es la {'segunda' if vals.index(v06) == 1 else vals.index(v06) + 1} más baja de las "
          f"{'cinco' if len(vals) == 5 else len(vals)} sesiones con tomas: sólo el 23-10 ({vals[0]:.2f}) quedó más abajo"
          if abs(vals[0] - datos['23-10']['tk'] / datos['23-10']['dec']) < 1e-12 else vals)
    fila("frenados por pose vencida", "| frenados por pose vencida | " + " | ".join(str(datos[k]["fr"]) for k in orden) + " |")
    sesion_csv = {"23-10": "L2_20261023_205007", "04-11 (mañana)": "L2_20261104_120744",
                  "04-11 (12:51)": "L2_20261104_125102", "06-11": "L2_20261106_193852"}
    libro_l = leer(RAIZ / "campanas" / "L2_obstaculo_2" / "libro.csv")
    ant_ses = {k: sum(1 for f in libro_l if f["tipo"] == "resultado" and f["id_sesion"] == sesion_csv[k]
                      and f["motivo"].startswith("antigüedad de pose")) for k in orden}
    cifra("frenados = paradas por antigüedad, por sesión", "1 / 2 / 0 / 1 en las dos fuentes",
          " / ".join(str(datos[k]["fr"]) for k in orden) + " en las dos fuentes"
          if all(datos[k]["fr"] == ant_ses[k] for k in orden) else f"consola {[datos[k]['fr'] for k in orden]}, libro {ant_ses}", False)
    cifra("resumen: 04-11", "36.2 ms y 1.11 ticks fuera de plazo por decisión (el 21-10, 0.90 y 0.81)",
          f"{INFO_CSV['tabla7']['04-11'][3]:.1f} ms y {datos['04-11 (mañana)']['tk'] / datos['04-11 (mañana)']['dec']:.2f} "
          f"ticks fuera de plazo por decisión (el 21-10, {tks[0] / decs[0]:.2f} y {tks[1] / decs[1]:.2f})")
    no_av = {}
    for k in orden:
        no_av[k] = Counter(re.findall(r"colocación: robot (\d) queda para el operador \(no avanza\)", texto_de(con / archivos[k])))
    cifra("no avanza 23-10", "4 el 23-10 (el 5 ×3 y el 8 ×1)", f"{sum(no_av['23-10'].values())} el 23-10 (el 5 ×{no_av['23-10']['5']} y el 8 ×{no_av['23-10']['8']})")
    m = no_av["04-11 (mañana)"]
    cifra("no avanza 04-11", "8 el 04-11 por la mañana (el 1 ×3, el 5 ×3 y el 9 ×2)",
          f"{sum(m.values())} el 04-11 por la mañana (el 1 ×{m['1']}, el 5 ×{m['5']} y el 9 ×{m['9']})")
    cifra("no avanza 12:51", "8 a las 12:51", f"{sum(no_av['04-11 (12:51)'].values())} a las 12:51")
    m = no_av["06-11"]
    cifra("no avanza 06-11", "30 el 06-11, de los cinco robots (el 9 ×8, el 8 ×7, el 5 ×7, el 1 ×5 y el 2 ×3)",
          f"{sum(m.values())} el 06-11, de los {'cinco' if len(m) == 5 else len(m)} robots (el 9 ×{m['9']}, el 8 ×{m['8']}, "
          f"el 5 ×{m['5']}, el 1 ×{m['1']} y el 2 ×{m['2']})")
    totales = [1540, 3041, 1088, 2046, 9890]
    cifra("06-11: total más alto", "tiene el total de ticks más alto de la campaña",
          "tiene el total de ticks más alto de la campaña" if datos["06-11"]["tk"] == max(tks + [d["tk"] or 0 for d in datos.values()]) else "NO")
    del totales
    # Caída del 04-11 (mañana).
    t = texto_de(con / archivos["04-11 (mañana)"])
    caidas = re.findall(r"\[ruedas\] caída robot (\d) a las ([\d:]+) \(ConnectionResetError 10054\): (.*)", t)
    prim = [c for c in caidas if c[1] < "12:35"]
    cifra("caída: horas", "entre las 12:31:59 y las 12:32:09", f"entre las {min(c[1] for c in prim)} y las {max(c[1] for c in prim)}")
    PARES["corte del 04-11"] = f"entre las {min(c[1] for c in prim)} y las {max(c[1] for c in prim)}"
    volvieron = sorted([c for c in prim if "reabierto" in c[2]], key=lambda c: float(re.search(r"reabierto a los ([\d.]+) s", c[2]).group(1)))
    cifra("caída: quiénes volvieron", "los robots 5, 2, 8 y 9 y el 4 volvieron", f"los robots {lista_es([c[0] for c in volvieron])} y el 4 volvieron")
    vueltas = [float(re.search(r"reabierto a los ([\d.]+) s", c[2]).group(1)) for c in prim if "reabierto" in c[2]]
    ob_vuelta = "OBSTÁCULO (robot 4) RECONECTADO" in t
    cifra("caída: vuelta", "volvieron a los 234–291 s", f"volvieron a los {min(vueltas):.0f}–{max(vueltas):.0f} s"
          if ob_vuelta else "el 4 no volvió")
    nunca = [c for c in prim if "NUNCA" in c[2]]
    cifra("caída: robot 1", "**el robot 1 no volvió** (274 intentos sin respuesta)",
          f"**el robot {nunca[0][0]} no volvió** ({re.search(r'(\d+) sin respuesta', nunca[0][2]).group(1)} intentos sin respuesta)")
    seg = [c for c in caidas if c[1] >= "12:35"]
    vs = [float(re.search(r"reabierto a los ([\d.]+) s", c[2]).group(1)) for c in seg]
    lineas = t.splitlines()
    racha = mejor = 0
    for l in lineas:
        racha = racha + 1 if l.startswith("[poses] conexión perdida") else 0
        mejor = max(mejor, racha)
    obst2 = "OBSTÁCULO (robot 4) RECONECTADO y frenado (n.º 2)" in t
    cifra("segunda caída", "a las 12:40:24–26 se cortaron otra vez los cuatro agentes que habían vuelto y el 4. Los agentes regresaron en 18.5–22.2 s, y el 4 volvió frenado",
          f"a las {min(c[1] for c in seg)}–{max(c[1] for c in seg)[-2:]} se cortaron otra vez los {'cuatro' if len(seg) == 4 else len(seg)} agentes "
          f"que habían vuelto y el 4. Los agentes regresaron en {min(vs):.1f}–{max(vs):.1f} s, y el 4 volvió frenado" if obst2 else "el 4 no")
    perdidas = sum("[poses] conexión perdida" in l for l in lineas)
    cifra("racha de líneas de pérdida de poses", 'la consola imprime 14 líneas seguidas "[poses] conexión perdida"',
          f'la consola imprime {mejor} líneas seguidas "[poses] conexión perdida"')
    cifra("un solo conectado", '(hay un solo "[poses] conectado", al arrancar)',
          '(hay un solo "[poses] conectado", al arrancar)' if t.count("[poses] conectado a ") == 1 else "NO")
    cifra("líneas de pérdida de poses en toda la sesión", "la consola imprime 21 líneas de pérdida de la conexión con el servidor de poses",
          f"la consola imprime {perdidas} líneas de pérdida de la conexión con el servidor de poses")
    cifra("detención sin confirmar del 1", "La del robot 1 siguió sin confirmarse hasta el final de la sesión",
          "La del robot 1 siguió sin confirmarse hasta el final de la sesión"
          if "NO SE PUDO CONFIRMAR LA DETENCIÓN DE:\n    agente 0 → robot 1" in t[t.index("[demo] interrumpida por el usuario."):] else "NO")
    cifra("resets del 04-11 mañana", "los 9 resets de agentes son los de la caída (5 a las 12:31:59–12:32:09 y 4 a las 12:40:24–26)",
          f"los {len(caidas)} resets de agentes son los de la caída ({len(prim)} a las {min(c[1] for c in prim)}–"
          f"{max(c[1] for c in prim)} y {len(seg)} a las {min(c[1] for c in seg)}–{max(c[1] for c in seg)[-2:]})")
    # 04-11 a las 12:51.
    t = texto_de(con / archivos["04-11 (12:51)"])
    ca = re.findall(r"\[ruedas\] caída robot (\d) a las ([\d:]+)", t)
    cifra("12:51: resets", "Entre las 12:52:04 y las 12:58:13 hubo 16 resets de los enlaces de los agentes y 3 del 4",
          f"Entre las {min(c[1] for c in ca)} y las {max(c[1] for c in ca)} hubo {len(ca)} resets de los enlaces de los agentes "
          f"y {datos['04-11 (12:51)']['ob']} del 4")
    PARES["resets de las 12:51"] = f"entre las {min(c[1] for c in ca)} y las {max(c[1] for c in ca)}"
    mins = (int(max(c[1] for c in ca)[3:5]) * 60 + int(max(c[1] for c in ca)[6:8]) - int(min(c[1] for c in ca)[3:5]) * 60 - int(min(c[1] for c in ca)[6:8])) / 60
    cifra("resumen: 12:51", "16 resets de los agentes y 3 del 4 en 6 min",
          f"{len(ca)} resets de los agentes y {datos['04-11 (12:51)']['ob']} del 4 en {mins:.0f} min")
    cifra("12:51: chequeo", "a las 12:49:56: **OK**", "a las 12:49:56: **OK**"
          if "chequeo previo de la PC: 2026-11-04 12:49:56" in t and "\nCHEQUEO OK" in t else "NO")
    # Chequeos del 23-10 y del 06-11.
    t = texto_de(con / "consola_20261023_2033_chequeo.txt")
    procs = re.search(r"^\s+procesos: (.*\.exe.*)$", t, re.M).group(1).count(".exe")
    cifra("23-10: chequeo", "a las 20:32:35: FALLA, a batería y con 5 procesos de OMEN",
          f"a las 20:32:35: FALLA, a batería y con {procs} procesos de OMEN"
          if "2026-10-23 20:32:35" in t and "A BATERIA" in t and "CHEQUEO FALLA" in t else "NO")
    t = texto_de(con / "consola_20261106_1922_omen_y_chequeo.txt")
    chrome = t.split("chequeo previo de la PC: 2026-11-06 19:21:17")[1].split("CHEQUEO FALLA")[0].count("chrome.exe")
    cifra("06-11: chequeo", "a las 19:21:17: FALLA, por 58 procesos de Chrome", f"a las 19:21:17: FALLA, por {chrome} procesos de Chrome")
    # 06-11: robot 1.
    t = texto_de(con / archivos["06-11"])
    m = re.search(r"robot 1 RECONECTADO \(reconexión n.º 1\) a los ([\d.]+) s de la caída \(caída ([\d:]+)", t)
    cifra("06-11: robot 1", "a las 20:09:01, en la guía de la toma 52, se cortó su enlace (10054). Volvió a los 84.4 s",
          f"a las {m.group(2)}, en la guía de la toma 52, se cortó su enlace (10054). Volvió a los {m.group(1)} s")
    i52 = t.index("--- TOMA 52 ---")
    i10054 = t.index("fallo enviando al agente 0 (robot 1): [WinError 10054]")
    cifra("06-11: corte en la guía de la 52", "en la guía de la toma 52 (10054)", "en la guía de la toma 52 (10054)"
          if i52 < i10054 < t.index(">>> TOMA 52") else "NO", False)
    a_fin = info_fin = None
    cifra("06-11: 0 %", "0 % de lo comandado en 50 pasos", "0 % de lo comandado en 50 pasos"
          if "recorrió el 0 % de lo comandado en los últimos 50 pasos" in t else "NO")
    trozo = t[t.index("--- TOMA 52 ---"):t.index("RECONECTADO (reconexión n.º 1) a los 84.4 s")]
    antes = re.findall(r"robot 1: está \(([\d.]+), ([\d.]+)\)", trozo)
    despues = re.findall(r"robot 1: está \(([\d.]+), ([\d.]+)\)", t[t.index("a los 84.4 s"):t.index("[colocación    0 s]", t.index("a los 84.4 s"))])
    # La primera tabla impresa después de RECONECTADO se leyó ANTES de la reconexión (orden del latido, abajo).
    leidas = antes + despues[:1]
    cifra("06-11: posiciones del 1", "pasó de (2.26, 1.85) a (2.10, 1.36), donde quedó",
          f"pasó de ({leidas[0][0]}, {leidas[0][1]}) a ({leidas[-1][0]}, {leidas[-1][1]}), donde quedó"
          if len(set(despues)) == 1 else despues)
    cod = texto_de(RAIZ / "codigo" / "sesion_robotat.py")
    lat = cod[cod.index("    def latir() -> None:"):]
    lat = lat[:lat.index("parar.wait(PERIODO_LATIDO_S)")]
    i1, i2, i3 = (lat.find("leer_poses_estables(fuente"), lat.find("canal.detener_todo(silencioso=True)"),
                  lat.find("_tabla_colocacion(poses"))
    ada = texto_de(RAIZ / "codigo" / "adaptadores_robotat.py")
    rec = ada[ada.index("    def _reconectar(self, i: int) -> bool:"):]
    rec = rec[:rec.index("\n    def ", 10)]
    orden = "lee las poses, después frena a los robots (ahí se reabrió el enlace) y recién entonces imprime la tabla"
    cifra("06-11: orden del latido", orden, orden if -1 < i1 < i2 < i3 and "RECONECTADO" in rec else (i1, i2, i3))
    cifra("06-11: refrescos sin pose", "el robot estuvo 30 refrescos sin pose", f"el robot estuvo {trozo.count('robot 1: SIN POSE')} refrescos sin pose")
    col52 = t[t.index("[colocación    0 s]", t.index("a los 84.4 s")):t.index(">>> TOMA 52")]
    seg_r1 = [int(m.group(1)) for m in re.finditer(r"\[colocación\s+(\d+) s\] r1 ✔", col52)]
    cifra("06-11: el 1 llega a su blanco", "el robot 1 llegó a su blanco en 12 s", f"el robot 1 llegó a su blanco en {min(seg_r1)} s")
    # Calibración aplicada.
    calibs = set()
    for a in archivos.values():
        calibs |= set(re.findall(r"escala posición\s+: ([\d.]+).*\n\s+rotación de marco\s+: ([\d.]+)°\s+traslación \(([\d.]+), ([\d.]+)\)", texto_de(con / a)))
    (e, r, tx, ty), = calibs
    cal = json.loads((RAIZ / "codigo" / "calibracion_medida.json").read_text(encoding="utf-8"))
    med = cal["_medido_en"]
    iguales = (abs(cal["escala_posicion"] - float(e)) < 1e-12 and abs(math.degrees(cal["rotacion_marco_rad"]) - float(r)) < 0.005
               and abs(cal["traslacion_x_m"] - float(tx)) < 1e-12 and abs(cal["traslacion_y_m"] - float(ty)) < 1e-12)
    cifra("calibración: consola = JSON", "la guardada en `calibracion_medida.json`",
          "la guardada en `calibracion_medida.json`" if iguales else "DISTINTA")
    e2 = cal["_etapas"]["2"]
    h21 = [h for h in cal["_historial"] if str(h.get("cuando", "")).startswith("2026-10-21") and h.get("etapa") == "etapa 2"]
    cifra("calibración: etapa 2 del 21-10", "ese día la etapa 2 falló sin guardar valores", "ese día la etapa 2 falló sin guardar valores"
          if e2["veredicto"] == "FALLO" and e2["cuando"].startswith("2026-10-21") and h21 and all(not h.get("campos") for h in h21) else (e2, h21))
    def dm(clave: str) -> str:
        return f"{med[clave][8:10]}-{med[clave][5:7]}"
    cifra("calibración", "escala 1.0167 y rotación +0.49° (medidas el 28-08) y traslación (1.506, 1.256) (29-08)",
          f"escala {float(e):.4f} y rotación +{float(r):.2f}° (medidas el {dm('escala_posicion')}) y traslación "
          f"({float(tx):.3f}, {float(ty):.3f}) ({dm('traslacion_x_m')})" if dm("escala_posicion") == dm("rotacion_marco_rad") else med)
    INFO_CSV.update(datos=datos)


# ── 6. derivados: verificaciones de sólo lectura ─────────────────────────
def derivados() -> None:
    d = RAIZ / "derivados"
    t4 = texto_de(d / "diagnostico_solo_lectura_20261104.txt")
    cifra("04-11: hora de la verificación", "resultado a las 12:46:40", "resultado a las 12:46:40"
          if t4.startswith("=== 2026-11-04 12:46:40") else "NO")
    m = re.search(r"p50 ([\d.]+) ms · p95 ([\d.]+) ms · máx ([\d.]+) ms · fallas (\d+)/200", t4)
    cifra("04-11: latencia antes de lanzar", "p50 3.4 ms, p95 14.9 ms y máx 52.3 ms, sin fallas",
          f"p50 {m.group(1)} ms, p95 {m.group(2)} ms y máx {m.group(3)} ms, " + ("sin fallas" if m.group(4) == "0" else m.group(4)))
    vivos = len(re.findall(r"marcador \d: vivo", t4.split("=== 2026-11-04 13:00")[0]))
    cifra("04-11: marcadores vivos", "los 6 marcadores estaban vivos", f"los {vivos} marcadores estaban vivos")
    bloque1 = t4.split("=== 2026-11-04 13:00")[0]
    abiertos = len([l for l in bloque1.splitlines() if "ABIERTO" in l and "Lost = 0" in l])
    cifra("04-11: equipos", "los 7 equipos respondían", f"los {abiertos} equipos respondían")
    cifra("04-11: MAC", "en 12 vueltas cada IP dio siempre la misma MAC", "en 12 vueltas cada IP dio siempre la misma MAC"
          if "12 vueltas" in t4 and len(re.findall(r"-> [0-9a-f-]+ x12", t4)) == 7 else "NO")
    p50 = dict(re.findall(r"(router \.1|servidor \.200)\s+perdidos\s+0/60 \| p50\s+(\d+) ms", t4))
    cifra("04-11: ping", "router 8 ms de p50, servidor de poses 4 ms",
          f"router {p50.get('router .1')} ms de p50, servidor de poses {p50.get('servidor .200')} ms")
    ping = re.findall(r"^(router \.1|servidor \.200|robot \d)\s+perdidos\s+(\d+)/60 \| p50\s+(\d+) ms", t4, re.M)
    robots = [int(p50) for n, perd, p50 in ping if n.startswith("robot")]
    cifra("04-11: ping sin pérdidas", "ping de 60 s, sin pérdidas",
          "ping de 60 s, sin pérdidas" if len(ping) == 8 and not sum(int(p[1]) for p in ping) else "NO")
    cifra("04-11: ping a los robots", "los robots unos 210 ms", "los robots unos 210 ms"
          if len(robots) == 6 and 200 <= min(robots) and max(robots) <= 220 else robots)
    lap = re.search(r"^Wi-Fi 6\s+(192\.168\.50\.\d+)\s+24\s+Dhcp", t4, re.M)
    en_enlace = re.search(r"^Wi-Fi 6\s+192\.168\.50\.0/24\s+0\.0\.0\.0\s", t4, re.M)
    equipos = re.findall(r"^\s+(robot \d|servidor de poses)\s+(192\.168\.50\.\d+)\s+puerto", t4, re.M)
    rob = sorted(int(ip.split(".")[-1]) for n_, ip in equipos if n_.startswith("robot"))
    srv = [ip for n_, ip in equipos if n_.startswith("servidor")]
    cifra("04-11: direcciones",
          "la laptop (192.168.50.3) habla con cada robot (192.168.50.101–109) directo por el WiFi, sin pasar por el servidor de poses (192.168.50.200)",
          f"la laptop ({lap.group(1)}) habla con cada robot (192.168.50.{rob[0]}–{rob[-1]}) directo por el WiFi, "
          f"sin pasar por el servidor de poses ({srv[0]})" if lap and en_enlace and len(rob) == 6 and len(srv) == 1 else "NO")
    cortes = [int(x) for x in re.findall(r"robot \d: (\d+) corte\(s\)", t4)]
    cifra("04-11: 90 s", "durante 90 s, sin enviar datos: 0 cortes", "durante 90 s, sin enviar datos: 0 cortes"
          if "90 s con las conexiones abiertas" in t4 and len(cortes) == 6 and not any(cortes) else cortes)
    cifra("resumen: reposo", "en reposo, 90 s sin cortes", "en reposo, 90 s sin cortes" if len(cortes) == 6 and not any(cortes) else cortes)
    t6 = texto_de(d / "diagnostico_solo_lectura_20261106.txt")
    cifra("06-11: hora", "**Verificación de sólo lectura a las 19:34:58**", "**Verificación de sólo lectura a las 19:34:58**"
          if "=== 2026-11-06 19:34:58" in t6 else "NO")
    ms = re.search(r"conecta en (\d+) ms", t6).group(1)
    cifra("resumen: sin Motive conectaba", f"sin Motive el servidor conectaba en 24 ms", f"sin Motive el servidor conectaba en {ms} ms")
    horas6 = re.findall(r"^=== 2026-11-06 ([\d:]+)", t6, re.M)
    cifra("resumen: app abierta", "la app de Claude estaba abierta a las 19:34:58", f"la app de Claude estaba abierta a las {max(horas6)}")
    PARES["app de Claude"] = f"entre las {min(horas6)} y las {max(horas6)}"
    cifra("06-11: conecta", "el servidor de poses conectaba en 24 ms",
          f"el servidor de poses conectaba en {re.search(r'conecta en (\d+) ms', t6).group(1)} ms")
    n_cong = len(re.findall(r"marcador \d CONGELADO \| distintos 1 utiles 15", t6))
    cifra("06-11: congelados", "los 6 marcadores salieron CONGELADOS: 1 valor distinto en 15 lecturas",
          f"los {n_cong} marcadores salieron CONGELADOS: 1 valor distinto en 15 lecturas")
    cifra("06-11: lote", 'respondía "OK" en 4.6 ms', f'respondía "OK" en {re.search(r"consulta en lote: OK ([\d.]+) ms", t6).group(1)} ms')
    cifra("06-11: basura", "9.083e+223", "9.083e+223" if "9.083e+223" in t6 else "NO")
    # Primera corrida de verificar_red.py del 06-11 (salida literal, aparte).
    tr = texto_de(d / "verificar_red_20261106_1922_salida.txt")
    sin_resp = re.findall(r"^\s+(servidor de poses|robot (\d))\s+\d+\.\d+\.\d+\.\d+\s+puerto \d+ NO responde \(TimeoutError\)", tr, re.M)
    cien = re.findall(r"^\s+(servidor de poses|robot (\d))\s+.*\(100% loss\)", tr, re.M)
    n_rob = sum(1 for _n, r_ in sin_resp if r_)
    esp_red = (f"Ni el servidor de poses ni ninguno de los {n_rob} robots abrió conexión (TimeoutError); el servidor y los robots "
               f"{lista_es([r_ for _n, r_ in cien if r_])} perdieron el 100 % de los paquetes del ping")
    cifra("06-11: primera corrida de verificar_red",
          "Ni el servidor de poses ni ninguno de los 6 robots abrió conexión (TimeoutError); el servidor y los robots 1, 5 y 8 perdieron el 100 % de los paquetes del ping",
          esp_red if any(not r_ for _n, r_ in sin_resp) and any(not r_ for _n, r_ in cien) else "NO")
    cifra("06-11: la lectura de marcadores falló", '("no se pudo leer el servidor de poses")',
          '("no se pudo leer el servidor de poses")' if "no se pudo leer el servidor de poses" in tr else "NO")


# ── 7. congelados ────────────────────────────────────────────────────────
def congelados() -> None:
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

    cab = json.loads((RAIZ / "campanas" / "L2_obstaculo_2" / "campana.json").read_text(encoding="utf-8"))["archivos_congelados"]
    ig = sum(hash_de(n) == h for n, h in cab.items())
    cifra("congelados", "Los 22 sha256 de hoy son iguales a los de la cabecera de `L2_obstaculo_2` (22/22)",
          f"Los {len(cab)} sha256 de hoy son iguales a los de la cabecera de `L2_obstaculo_2` ({ig}/{len(cab)})")
    cifra("resumen: congelados", "siguen iguales a la cabecera de la campaña (22/22)",
          f"siguen iguales a la cabecera de la campaña ({ig}/{len(cab)})")
    cifra("constante de reintentos", "`REINTENTOS_COLOCACION` = 5 en `sesion_robotat.py`",
          f"`REINTENTOS_COLOCACION` = {re.search(r'^REINTENTOS_COLOCACION: int = (\d+)', texto_de(RAIZ / 'codigo' / 'sesion_robotat.py'), re.M).group(1)} en `sesion_robotat.py`")


# ── 8. declaraciones y citas de la bitácora ──────────────────────────────
def declaraciones(info: Dict[str, Any]) -> None:
    res = info["res"]
    sesion_de = {int(f["intento"]): f["id_sesion"] for f in res}
    incl = [int(f["intento"]) for f in res if f["incluida"] == "1"]
    estado = {"L2_20261021_133444": "compartido", "L2_20261106_193852": "declarado"}
    c = Counter(estado.get(sesion_de[k], "sin") for k in incl)
    cifra("clasificación de las incluidas", "**18** con `CHEQUEO OK` declarado sin salida, **2** con el OK compartido y **10** sin `CHEQUEO OK` propio",
          f"**{c['declarado']}** con `CHEQUEO OK` declarado sin salida, **{c['compartido']}** con el OK compartido y "
          f"**{c['sin']}** sin `CHEQUEO OK` propio")
    cifra("resumen: clasificación", "18 salen de una sesión con `CHEQUEO OK` declarado por el operador pero sin la salida pegada, 2 de una sesión con el OK compartido y 10 de sesiones sin `CHEQUEO OK` propio",
          f"{c['declarado']} salen de una sesión con `CHEQUEO OK` declarado por el operador pero sin la salida pegada, "
          f"{c['compartido']} de una sesión con el OK compartido y {c['sin']} de sesiones sin `CHEQUEO OK` propio")
    sin = Counter(sesion_de[k] for k in incl if estado.get(sesion_de[k], "sin") == "sin")
    cifra("las 10 sin OK propio", "5 son de la sesión de las 13:48 del 21-10, 3 del 23-10 (el último chequeo dio FALLA) y 2 del 04-11 por la mañana",
          f"{sin['L2_20261021_134819']} son de la sesión de las 13:48 del 21-10, {sin['L2_20261023_205007']} del 23-10 "
          f"(el último chequeo dio FALLA) y {sin['L2_20261104_120744']} del 04-11 por la mañana")
    # Rampa de arranque seguro: decisiones_previas = 0.
    rampa = []
    for s in SESIONES.values():
        for f in leer(RAIZ / "sesiones" / f"{s}_L2_tomas.csv"):
            if f.get("decisiones_previas") not in (None, "") and int(float(f["decisiones_previas"])) == 0:
                rampa.append((int(f["intento_campana"]), f["incluida"] == "1"))
    cifra("rampa", "En el período fueron la 19 y la 29, las dos incluidas, y la 42, no válida",
          "En el período fueron la 19 y la 29, las dos incluidas, y la 42, no válida"
          if sorted(rampa) == [(19, True), (29, True), (42, False)] else rampa)
    # Pausas: segundos entre el resultado y la respuesta.
    filas_l = info["filas"]
    def t_de(tipo: str, k: int) -> datetime:
        return datetime.fromisoformat(next(f["fecha"] for f in filas_l if f["tipo"] == tipo and f["intento"] == str(k)))
    d24 = (t_de("pausa", 24) - t_de("resultado", 24)).total_seconds()
    d36 = (t_de("pausa", 36) - t_de("resultado", 36)).total_seconds()
    d37 = (t_de("resultado", 37) - t_de("pausa", 36)).total_seconds()
    cifra("pausas: segundos", "la respuesta llegó a los 4 y 5 s", f"la respuesta llegó a los {d24:.0f} y {d36:.0f} s")
    cifra("el 37 después", "el 37 se perdió por lo mismo 32 s después", f"el 37 se perdió por lo mismo {d37:.0f} s después")
    cifra("pausas en el §9", "se contestaron \"s\" a los 4 y 5 s", f"se contestaron \"s\" a los {d24:.0f} y {d36:.0f} s")
    # Incluidas del 06-11 después del 51.
    pos = [k for k in incl if 52 <= k <= 72]
    cifra("incluidas después del 51", "Siguió en las tomas 52–72, con 14 de las incluidas", f"Siguió en las tomas 52–72, con {len(pos)} de las incluidas")
    # La app de Claude el 06-11 (derivados).
    t6 = texto_de(RAIZ / "derivados" / "diagnostico_solo_lectura_20261106.txt")
    horas = re.findall(r"^=== 2026-11-06 ([\d:]+)", t6, re.M)
    cifra("app de Claude", "entre las 19:33:47 y las 19:34:58", f"entre las {min(horas)} y las {max(horas)}")
    por_sesion = defaultdict(list)
    for k in incl:
        por_sesion[sesion_de[k]].append(k)
    cifra("incluidas por sesión (21-10 13:48)", "8, 9, 10, 13 y 14", lista_es(por_sesion["L2_20261021_134819"]))
    cifra("incluidas por sesión (21-10 13:34)", "| compartido: el OK de las 13:32:16 | 2 y 4 |",
          f"| compartido: el OK de las 13:32:16 | {lista_es(por_sesion['L2_20261021_133444'])} |")
    cifra("sesión de las 13:26", "| sí, pegado (13:25:56) | — |", "| sí, pegado (13:25:56) | — |"
          if not por_sesion.get("L2_20261021_132617") and "sesión de las 13:26 (intento 1) | sí (13:25:56)"
          in texto_de(RAIZ / "documentos" / "REPORTE_2026-10-22_campana_L2.md") else "NO")
    filas_l = info["filas"]
    ap = next(f for f in filas_l if f["tipo"] == "apertura" and f["id_sesion"] == "L2_20261106_193852")
    ci = next(f for f in filas_l if f["tipo"] == "cierre_sesion" and f["id_sesion"] == "L2_20261106_193852")
    fin = datetime.fromisoformat(ap["motivo"].split("hora de fin ")[1].replace(" ", "T") + ":00")
    antes = (fin - datetime.fromisoformat(ci["fecha"])).total_seconds() / 60
    cifra("06-11: minutos antes de la hora de fin", "12 min antes de la hora de fin", f"{antes:.0f} min antes de la hora de fin")
    ci_ult = next(f for f in filas_l if f["tipo"] == "cierre_sesion" and f["id_sesion"] == "L2_20261106_193330")
    cifra("06-11: cierre del último que no arrancó", "antes de las 19:33:31, cuando se cerró el último lanzamiento que no arrancó",
          f"antes de las {hhmmss(ci_ult['fecha'])}, cuando se cerró el último lanzamiento que no arrancó")
    falla = datetime.fromisoformat("2026-11-06T19:21:17")
    lanz = [f for f in filas_l if f["tipo"] == "apertura" and falla < datetime.fromisoformat(f["fecha"])
            < datetime.fromisoformat(ap["fecha"])]
    cifra("06-11: lanzamientos entre la FALLA y la sesión", "compartido con uno a cuatro de esos lanzamientos",
          f"compartido con uno a {'cuatro' if len(lanz) == 4 else len(lanz)} de esos lanzamientos")
    cifra("06-11: segundos antes de abrir la sesión", "entre 321 y 1055 s antes de abrir la sesión",
          f"entre {(datetime.fromisoformat(ap['fecha']) - datetime.fromisoformat(ci_ult['fecha'])).total_seconds():.0f} y "
          f"{(datetime.fromisoformat(ap['fecha']) - falla).total_seconds():.0f} s antes de abrir la sesión")
    cifra("06-11: último resultado de la app", "estaba en uso a las 19:34:58", f"estaba en uso a las {max(horas)}")
    primero = t6.split("=== 2026-11-06 " + min(horas), 1)[1].split("\n=== ", 1)[0]
    msg = "es el aviso de esa llamada cortada porque la sesión de la app terminó antes de registrar su resultado"
    cifra("06-11: primer registro de la app", msg,
          msg if "Tool call interrupted: the session ended before this call's result was recorded" in primero else "NO")
    # Los lanzamientos del 06-11 que no arrancaron (libro).
    sids06 = sorted({f["id_sesion"] for f in filas_l if f["fecha"].startswith("2026-11-06")} - {"L2_20261106_193852"})
    dur = {}
    for sid in sids06:
        a_ = next(f for f in filas_l if f["tipo"] == "apertura" and f["id_sesion"] == sid)
        c_ = next(f for f in filas_l if f["tipo"] == "cierre_sesion" and f["id_sesion"] == sid)
        dur[sid] = ((datetime.fromisoformat(c_["fecha"]) - datetime.fromisoformat(a_["fecha"])).total_seconds(), hhmmss(a_["fecha"]), c_["motivo"])
    n1s = sum(v[0] == 1 for v in dur.values())
    cifra("resumen: cuatro lanzamientos", "El 06-11 no arrancaron cuatro lanzamientos",
          f"El 06-11 no arrancaron {'cuatro' if len(dur) == 4 else len(dur)} lanzamientos")
    cifra("resumen: los que se cerraron en 1 s", "Tres se cerraron en 1 s", f"{'Tres' if n1s == 3 else n1s} se cerraron en 1 s")
    p1 = dur["L2_20261106_192946"]
    cifra("resumen: el primero", 'El primero, a las 19:29:46, dio "timed out"',
          f'El primero, a las {p1[1]}, dio "timed out"' if "timed out" in p1[2] else "NO")
    cifra("incluidas por sesión (23-10)", "19, 20 y 21", lista_es(por_sesion["L2_20261023_205007"]))
    cifra("incluidas por sesión (04-11)", "29 y 33", lista_es(por_sesion["L2_20261104_120744"]))
    k6 = por_sesion["L2_20261106_193852"]
    cifra("incluidas por sesión (06-11)", "las 18 del 44 al 72", f"las {len(k6)} del {min(k6)} al {max(k6)}")
    # Filas del §9.1 completas, atadas a los datos del libro.
    def inc(sid: str) -> str:
        return lista_es(por_sesion[sid]) if por_sesion.get(sid) else "—"
    for desc, fl in [
        ("21-10, 13:26", f"| 21-10, 13:26 (intento 1) | sí, pegado (13:25:56) | {inc('L2_20261021_132617')} |"),
        ("21-10, 13:34", f"| 21-10, 13:34 (intentos 2–7) | compartido: el OK de las 13:32:16 | {inc('L2_20261021_133444')} |"),
        ("21-10, 13:48", f"| 21-10, 13:48 (intentos 8–17) | no: el último OK, 963 s antes, era de otra sesión | {inc('L2_20261021_134819')} |"),
        ("23-10, 20:50", f"| 23-10, 20:50 (intentos 18–25) | no: el último chequeo, a las 20:32:35, dio FALLA | {inc('L2_20261023_205007')} |"),
        ("04-11, 12:07", f"| 04-11, 12:07 (intentos 26–35) | no consta | {inc('L2_20261104_120744')} |"),
        ("04-11, 12:51", f"| 04-11, 12:51 (intentos 36–37) | sí, pegado (12:49:56) | {inc('L2_20261104_125102')} |"),
        ("06-11, 19:38", "| 06-11, 19:38 (intentos 38–73) | sí según el operador, sin la salida pegada; el último pegado, a las 19:21:17, dio FALLA | "
                         f"las {len(k6)} del {min(k6)} al {max(k6)} |"),
    ]:
        fila(f"§9.1: fila {desc}", fl)
    # Citas de la bitácora (extracto).
    b = texto_de(RAIZ / "documentos" / "BITACORA_extracto_desde_20261023.md")
    citas = {
        "07-11: frase corregida": "Del 23-10 y del 04-11 no hay conteo de decisiones registrado",
        "04-11 12:51: hora de la verificación": "**Verificación antes de lanzar (12:48, sólo lectura, desde la laptop):**",
        "decisión de José del panel": '"Acepto el panel en la misma laptop: el lazo queda en ~12.5 ms de 100."',
        "respuesta del operador: batería": '"se fue la batería no fue intervención"',
        "respuesta del operador: Motive": '"solo corrí el motive"',
        "respuesta del operador: chequeo": '**Chequeo de la PC antes de la sesión de las 19:38:** "si", dio `CHEQUEO OK`.',
        "23-10: NO FRENA": "el obstáculo NO FRENA: se movió 51.1 cm durante la colocación (v medida 0.000 m/s)",
        "23-10: sin confirmar": "Falta confirmarlo con el operador.",
        "respuesta del operador: timed out": '"era que no estaba conectado al robotat"',
        "respuesta del operador: intento 24": '**Intento 24 (23-10), "ABORTO POR EL OBSTÁCULO: el obstáculo NO FRENA":** "si"',
        "respuesta del operador: 04-11": '"si, se lo quite, pero lo que pasó es que el server estaba fallando"',
        "respuesta del operador: cambio de batería": '"le cambié la batería, fué cuando se quedó sin ella"',
        "04-11 mañana: frase corregida": 'La red ya venía mal: el primer lanzamiento dio "timed out"',
        "respuesta del operador: pregunta doble": '"¿a qué hora te dio el `CHEQUEO OK`, y cerraste la app de Claude antes de lanzar a las 19:38?"',
        "07-11 (segunda): frase corregida": "Con la declaración del operador, 18 sí lo tienen",
    }
    MARCA = "\n## 11. Datos y verificación"
    cuerpo = TEXTO.split(MARCA)[0]          # el reporte sin el §11, que nombra estas citas
    cifra("el título del §11 aparece una vez", "1", str(TEXTO.count(MARCA)), False)
    en_reporte = {"decisión de José del panel", "respuesta del operador: Motive", "23-10: NO FRENA",
                  "07-11: frase corregida", "04-11 mañana: frase corregida",
                  "respuesta del operador: pregunta doble", "07-11 (segunda): frase corregida"}
    for desc, en_rep, en_bit in [("la hora (12:48)", 'figura "(12:48)"', "(12:48, sólo lectura"),
                                 ("no fue intervención", '"no fue intervención"', '"se fue la batería no fue intervención"')]:
        cifra(f"bitácora y reporte: {desc}", "en el extracto y en el reporte",
              "en el extracto y en el reporte" if en_bit in b and en_rep in cuerpo else "NO ESTÁ", False)
    for desc, cita in citas.items():
        ok = cita in b and (desc not in en_reporte or cita.strip('"') in cuerpo)
        cifra(f"bitácora: {desc}", "está en el extracto" + (" y en el reporte" if desc in en_reporte else ""),
              ("está en el extracto" + (" y en el reporte" if desc in en_reporte else "")) if ok else "NO ESTÁ", False)
    cifra("citas: «solo corrí el motive» en el cuerpo", "2 veces (§8 y §9.1)", f"{cuerpo.count('solo corrí el motive')} veces (§8 y §9.1)", False)
    datos = INFO_CSV["datos"]
    cifra("decisiones del 23-10 y del 04-11", "las consolas dan 1878 y 1850 decisiones, es decir 0.58 y 1.11 ticks fuera de plazo por decisión",
          f"las consolas dan {datos['23-10']['dec']} y {datos['04-11 (mañana)']['dec']} decisiones, es decir "
          f"{datos['23-10']['tk'] / datos['23-10']['dec']:.2f} y {datos['04-11 (mañana)']['tk'] / datos['04-11 (mañana)']['dec']:.2f} "
          "ticks fuera de plazo por decisión")


def main() -> int:
    global TEXTO, RAIZ
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    if sys.version_info[:2] != (3, 13):
        print("Hace falta Python 3.13: la huella sin calibración de config_robotat.py es un sha256 de "
              "ast.dump, que cambió en 3.13 y no se probó con 3.14 ni posteriores.")
        return 2
    RAIZ = Path(sys.argv[1])
    TEXTO = Path(sys.argv[2]).read_bytes().decode("utf-8")
    cegado()
    info = libro()
    sesiones_libro(info)
    perdidas_y_ritmo(info)
    csv_sesiones(info)
    consolas()
    derivados()
    congelados()
    declaraciones(info)
    todas_de("horas «entre las … y las …» en todo el texto", r"entre las \d\d:\d\d:\d\d y las \d\d:\d\d:\d\d", PARES,
             {"corte del 04-11": 2, "resets de las 12:51": 1, "app de Claude": 2, "sesión del 06-11": 1})
    malas = 0
    for desc, rep, calc, en_texto in CIFRAS:
        ok = (rep == calc) and (not en_texto or rep in TEXTO)
        malas += not ok
        print(f"{'SÍ' if ok else 'NO'}  {desc}: reportado «{rep}» · calculado «{calc}»"
              + ("" if not en_texto or rep in TEXTO else " · NO ESTÁ EN EL TEXTO"))
    print(f"\n{len(CIFRAS) - malas}/{len(CIFRAS)} cifras coinciden")
    return 1 if malas else 0


if __name__ == "__main__":
    sys.exit(main())
