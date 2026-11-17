"""
verificar_campana_l2.py
=======================
Verificador INDEPENDIENTE del análisis de la campaña L2
(`tesis/PLAN_ANALISIS_campana_L2.md`; congelado con su sha256 en el libro
antes de la primera toma, como el plan y `analizar_campana_l2.py`).

Recalcula desde el CRUDO, con código propio (NO importa
`analizar_campana_l2` ni `campana_obstaculo`), las cifras que el análisis
dejó en `analisis.json`, y compara cada una:

  · conteos (intentos, corridas, incluidas, con par);
  · principal: n, media, desvío, IC95 t, mediana; sensibilidades A–E;
  · seguridad: corridas, d_min mín/mediana/máx, contactos y frenos (con
    Clopper–Pearson), d_min y d_pared hw − réplica (media y mínimo de reps);
  · costo: n, media, IC95;
  · 30-09: cobertura hw, brecha por pares y por escenario, d_pared;
  · el criterio de cierre de seguridad: tomas corridas con contacto y si la
    campaña se cerró por él;
  · la d_k de cada toma de `pares.csv`;
  · el sha256 del plan, del script de análisis y de este verificador
    contra los vigentes del libro.

    python verificar_campana_l2.py <carpeta del análisis> [--base DIR]

Sale con 0 si todas las cifras coinciden (|Δ| ≤ 1e-9), 1 si alguna no.
Sólo lee.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scipy import stats

_CARPETA = Path(__file__).resolve().parent
_TESIS = _CARPETA.parents[2]
TOL = 1e-9
CONTACTO = 0.15
RAMPA = 50


def sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest() if ruta.is_file() else "FALTA"


def leer(ruta: Path) -> List[Dict[str, str]]:
    with open(ruta, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def num(x: Any) -> Optional[float]:
    try:
        s = str(x).strip()
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


def uno(x: Any) -> bool:
    return str(x).strip() in ("1", "1.0", "True", "true")


def ic_t(v: List[float]) -> Dict[str, Any]:
    n = len(v)
    out: Dict[str, Any] = {"n": n}
    if n == 0:
        return out
    m = sum(v) / n
    out["media"] = m
    out["mediana"] = statistics.median(v)
    if n >= 2:
        sd = statistics.stdev(v)
        w = stats.t.ppf(0.975, n - 1) * sd / math.sqrt(n)
        out.update(sd=sd, ic95=[m - w, m + w])
    return out


def cp(k: int, n: int) -> List[float]:
    # Clopper–Pearson exacto con la beta (otra vía que binomtest).
    lo = 0.0 if k == 0 else float(stats.beta.ppf(0.025, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(0.975, k + 1, n - k))
    return [lo, hi]


def libro(carpeta: Path) -> List[Dict[str, str]]:
    texto = (carpeta / "libro.csv").read_text(encoding="utf-8")
    if texto and not texto.endswith("\n"):
        texto = texto[: texto.rfind("\n") + 1]
    filas = list(csv.reader(io.StringIO(texto)))
    cab = filas[0]
    return [dict(zip(cab, f)) for f in filas[1:] if len(f) == len(cab)]


def soporte_ok(r: Dict[str, str]) -> bool:
    pts = []
    for i in range(5):
        est = (r.get(f"col_estado_a{i}") or "").strip()
        if est and est != "listo":
            return False
        try:
            x, y = float(r[f"x0_a{i}"]), float(r[f"y0_a{i}"])
        except (KeyError, ValueError, TypeError):
            continue
        pts.append((x, y))
        try:
            if math.hypot(x - float(r[f"blanco_x_a{i}"]), y - float(r[f"blanco_y_a{i}"])) > 0.12:
                return False
        except (KeyError, ValueError, TypeError):
            pass
    for a in range(len(pts)):
        for b in range(a + 1, len(pts)):
            if math.dist(pts[a], pts[b]) < 0.31:
                return False
    return True


def rep_de(filas: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    norm = [r for r in filas if (r.get("pasada") or "normal") == "normal" and uno(r["valido"])]
    if not norm:
        norm = [r for r in filas if r.get("pasada") == "suplementaria" and uno(r["valido"])]
    if not norm:
        return None
    cob = [float(r["cobertura_aoi"]) for r in norm]
    dm = [num(r["d_min_obst_medida"]) for r in norm]
    dm = [x for x in dm if x is not None]
    pa = [num(r["d_pared_min"]) for r in norm]
    pa = [x for x in pa if x is not None]
    return {"cob": sum(cob) / len(cob),
            "dmin_media": sum(dm) / len(dm) if dm else None,
            "dmin_min": min(dm) if dm else None,
            "pared_media": sum(pa) / len(pa) if pa else None,
            "pared_min": min(pa) if pa else None}


def falla_b(r: Dict[str, str]) -> bool:
    if (num(r.get("decisiones")) or 0) == 0:
        return False                      # no arrancó: sin cierre (b), plan §7
    e, d = num(r.get("cierre_b_err_max_m")), num(r.get("cierre_b_desfase"))
    th = num(r.get("cierre_b_err_th_rad"))
    return (not uno(r.get("cierre_b_ok")) or e is None or e > 0.001 or d is None or d != 0
            or th is None or th > 1e-6 or not uno(r.get("cierre_b_mandos_iguales")))


def recalcular(js: Dict[str, Any], base: Path, dir_hw: Optional[Path] = None,
               dir_rep: Optional[Path] = None, dir_3009: Optional[Path] = None
               ) -> Dict[str, Any]:
    nombre = js["campana"]
    filas = libro(base / "campanas" / nombre)
    # Por defecto, relativo a --base (el paquete se puede mover); las rutas
    # del análisis, sólo si ahí no hay nada.
    if dir_hw is None:
        dir_hw = base if any(base.glob("*_L2_tomas*.csv")) else Path(js["fuentes"]["dir_hw"])
    if dir_rep is None:
        dir_rep = base / "replica_campana" / nombre
        if not dir_rep.is_dir():
            dir_rep = Path(js["fuentes"]["dir_replica"])
    res: Dict[int, Dict[str, str]] = {}
    for f in filas:
        if f["tipo"] == "resultado":
            res[int(f["intento"])] = f
    reservas = {int(f["intento"]) for f in filas if f["tipo"] == "reserva"}
    for k in reservas - set(res):
        res[k] = {"estado": "interrumpida", "incluida": "0", "archivo_tomas": ""}
    sesiones = {f["id_sesion"] for f in filas if f["tipo"] == "apertura"}
    csvs: Dict[str, List[Dict[str, str]]] = {}
    for ruta in sorted(dir_hw.glob("*_L2_tomas*.csv")):
        d = leer(ruta)
        if any(r.get("id_sesion") in sesiones for r in d):
            csvs[ruta.name] = d
    hw: Dict[int, Dict[str, str]] = {}
    for k, f in res.items():
        if f["estado"] != "interrumpida":
            hw[k] = [r for r in csvs[f["archivo_tomas"]] if r.get("intento_campana") == str(k)][0]
    incl = sorted(k for k, f in res.items() if uno(f["incluida"]))
    corr = sorted(k for k, f in res.items() if f["estado"] == "corrida")
    interr = {k for k, f in res.items() if f["estado"] == "interrumpida"}
    extra = [r for d in csvs.values() for r in d
             if num(r.get("toma")) is not None and int(num(r["toma"])) in interr
             and r.get("id_sesion") in sesiones and num(r.get("decisiones")) is not None]

    rep: List[Dict[str, str]] = []
    if dir_rep.is_dir():
        for ruta in sorted(dir_rep.glob("*_replica_tomas.csv")):
            rep += leer(ruta)

    def grupo(k: int, c: str, t: float) -> List[Dict[str, str]]:
        return [r for r in rep if int(float(r["intento_campana"])) == k
                and r["condicion"] == c and abs(float(r["tau_s"]) - t) < 1e-9]

    fallas = {int(float(r["intento_campana"])) for r in rep
              if r["condicion"] == "con_obstaculo" and falla_b(r)} & set(incl)
    pares = []
    for k in incl:
        r = hw[k]
        rc = None if k in fallas else rep_de(grupo(k, "con_obstaculo", 0.0))
        rs = None if k in fallas else rep_de(grupo(k, "sin_obstaculo", 0.0))
        r45 = None if k in fallas else rep_de(grupo(k, "con_obstaculo", 0.45))
        h = float(r["cobertura_aoi"])
        pares.append({"k": k, "r": r, "hw": h, "rc": rc, "rs": rs, "r45": r45,
                      "d": h - rc["cob"] if rc else None,
                      "d45": h - r45["cob"] if r45 else None,
                      "costo": rc["cob"] - rs["cob"] if rc and rs else None})
    cp_ = [p for p in pares if p["d"] is not None]
    out: Dict[str, Any] = {
        "conteos.intentos": len(res), "conteos.corridas": len(corr),
        "conteos.incluidas": len(incl), "conteos.con_par": len(cp_),
    }

    def volcar(prefijo: str, r: Dict[str, Any]) -> None:
        out[f"{prefijo}.n"] = r["n"]
        for c in ("media", "sd", "mediana"):
            if c in r:
                out[f"{prefijo}.{c}"] = r[c]
        if "ic95" in r:
            out[f"{prefijo}.ic95.0"], out[f"{prefijo}.ic95.1"] = r["ic95"]

    volcar("principal", ic_t([p["d"] for p in cp_]))
    subs = {
        "A_sin_fuera_de_soporte": [p["d"] for p in cp_ if soporte_ok(p["r"])],
        "B_sin_retroceso": [p["d"] for p in cp_ if not (p["r"].get("retrocesos_detalle") or "").strip()],
        "C_sin_freno": [p["d"] for p in cp_ if (num(p["r"].get("frenos")) or 0) <= 0],
        "D_sin_rampa": [p["d"] for p in cp_ if float(p["r"]["decisiones_previas"]) >= RAMPA],
        "E_replica_tau_045": [p["d45"] for p in pares if p["d45"] is not None],
    }
    for k, v in subs.items():
        volcar(f"sensibilidades.{k}", ic_t(v))
    # Las tomas cortadas a mitad que el libro marcó interrumpidas y no tienen
    # fila de tomas: su seguridad sale de sus decisiones.
    con_fila_ex = {int(num(r["toma"])) for r in extra}
    cortadas: Dict[int, List[Dict[str, str]]] = {}
    for k in sorted(interr - con_fila_ex):
        ses_k = next((f["id_sesion"] for f in filas if f["tipo"] == "reserva"
                      and f["intento"] == str(k)), None)
        dec_k = [r for ruta in sorted(dir_hw.glob("*_L2_decisiones*.csv")) for r in leer(ruta)
                 if r.get("episodio") == str(k) and r.get("id_sesion") == ses_k]
        if dec_k:
            cortadas[k] = dec_k

    def seg_de_decisiones(dec_k: List[Dict[str, str]]) -> Dict[str, Any]:
        d_o = [num(r.get("d_obst_medida")) for r in dec_k]
        d_o = [x for x in d_o if x is not None]
        pasos_k: Dict[str, Dict[str, Tuple[float, float]]] = {}
        for r in dec_k:
            if num(r.get("pose_env_x")) is not None and num(r.get("pose_env_y")) is not None:
                pasos_k.setdefault(r["paso"], {})[r["agente"]] = (num(r["pose_env_x"]),
                                                                 num(r["pose_env_y"]))
        pares_k = {(a, b) for pts in pasos_k.values() for a in pts for b in pts
                   if a < b and math.dist(pts[a], pts[b]) < CONTACTO}
        return {"d_min_obst_medida": min(d_o) if d_o else "", "colisiones_015": len(pares_k),
                "frenos": ""}
    seg = [hw[k] for k in corr] + extra + [seg_de_decisiones(v) for v in cortadas.values()]
    dm = [num(r.get("d_min_obst_medida")) for r in seg]
    dm = [x for x in dm if x is not None]
    out["seguridad.corridas"] = len(seg)
    if dm:
        out["seguridad.d_min_obst_hw.min"] = min(dm)
        out["seguridad.d_min_obst_hw.mediana"] = statistics.median(dm)
        out["seguridad.d_min_obst_hw.max"] = max(dm)
    kc = sum(1 for x in dm if x < CONTACTO)
    out["seguridad.contacto_hw.k"] = kc
    if dm:
        out["seguridad.contacto_hw.ic95.0"], out["seguridad.contacto_hw.ic95.1"] = cp(kc, len(dm))
    kf = sum(1 for r in seg if (num(r.get("frenos")) or 0) > 0)
    out["seguridad.tomas_con_freno_hw.k"] = kf
    out["seguridad.frenos_eventos_hw"] = float(sum(num(r.get("frenos")) or 0 for r in seg))
    con_rep = [p for p in pares if p["rc"] and num(p["r"].get("d_min_obst_medida")) is not None
               and p["rc"]["dmin_media"] is not None]
    volcar("seguridad.d_min_hw_menos_replica_media",
           ic_t([num(p["r"]["d_min_obst_medida"]) - p["rc"]["dmin_media"] for p in con_rep]))
    volcar("seguridad.d_min_hw_menos_replica_minimo",
           ic_t([num(p["r"]["d_min_obst_medida"]) - p["rc"]["dmin_min"] for p in con_rep]))
    con_pa = [p for p in cp_ if num(p["r"].get("d_pared_min")) is not None
              and p["rc"]["pared_media"] is not None]
    volcar("seguridad.d_pared_hw_menos_replica_media",
           ic_t([num(p["r"]["d_pared_min"]) - p["rc"]["pared_media"] for p in con_pa]))
    volcar("seguridad.d_pared_hw_menos_replica_minimo",
           ic_t([num(p["r"]["d_pared_min"]) - p["rc"]["pared_min"] for p in con_pa]))
    volcar("costo", ic_t([p["costo"] for p in pares if p["costo"] is not None]))
    # Criterio de cierre (José, 09-10): contacto = obstáculo < 0.15 m o algún
    # par de agentes < 0.15 m, en las tomas corridas del libro.
    n_contacto = 0
    for k in corr:
        d_o = num(hw[k].get("d_min_obst_medida"))
        pares_ = num(hw[k].get("colisiones_015")) or 0
        if (d_o is not None and d_o < CONTACTO) or pares_ > 0:
            n_contacto += 1
    out["criterio_de_cierre.n_tomas_con_contacto"] = n_contacto
    # Recuento físico: más las interrumpidas que corrieron (fila de tomas o,
    # si la toma se cortó, sus decisiones).
    n_fis = n_contacto
    con_fila_ = {int(num(r["toma"])): r for r in extra}
    for k in sorted(interr):
        if k in con_fila_:
            r = con_fila_[k]
            d_o = num(r.get("d_min_obst_medida"))
            if (d_o is not None and d_o < CONTACTO) or (num(r.get("colisiones_015")) or 0) > 0:
                n_fis += 1
            continue
        ses = next((f["id_sesion"] for f in filas if f["tipo"] == "reserva"
                    and f["intento"] == str(k)), None)
        dec = [r for ruta in sorted(dir_hw.glob("*_L2_decisiones*.csv")) for r in leer(ruta)
               if r.get("episodio") == str(k) and r.get("id_sesion") == ses]
        if not dec:
            continue
        d_o = [num(r.get("d_obst_medida")) for r in dec]
        d_o = [x for x in d_o if x is not None]
        pasos: Dict[str, List[Tuple[float, float]]] = {}
        for r in dec:
            if num(r.get("pose_env_x")) is not None and num(r.get("pose_env_y")) is not None:
                pasos.setdefault(r["paso"], []).append((num(r["pose_env_x"]), num(r["pose_env_y"])))
        par = min((math.dist(p, q) for pts in pasos.values() for a, p in enumerate(pts)
                   for q in pts[a + 1:]), default=float("inf"))
        if (d_o and min(d_o) < CONTACTO) or par < CONTACTO:
            n_fis += 1
    out["criterio_de_cierre.n_contactos_fisicos"] = n_fis
    # El intento tras el que debió cerrar y el incumplimiento (intentos
    # reservados después), con el orden por intento.
    fis_k = sorted(
        [k for k in corr if ((num(hw[k].get("d_min_obst_medida")) or 9) < CONTACTO
                             or (num(hw[k].get("colisiones_015")) or 0) > 0)]
        + [k for k in sorted(interr) if k in con_fila_
           and ((num(con_fila_[k].get("d_min_obst_medida")) or 9) < CONTACTO
                or (num(con_fila_[k].get("colisiones_015")) or 0) > 0)]
        + [k for k, v in cortadas.items() if (
            (seg_de_decisiones(v)["d_min_obst_medida"] or 9) < CONTACTO
            or seg_de_decisiones(v)["colisiones_015"] > 0)])
    reservas_k = {int(f["intento"]) for f in filas if f["tipo"] == "reserva"}
    if len(fis_k) >= 2:
        out["criterio_de_cierre.debio_cerrar_tras_intento"] = fis_k[1]
    out["criterio_de_cierre.incumplimiento_del_criterio"] = int(
        len(fis_k) >= 2 and any(k > fis_k[1] for k in reservas_k))
    cierre = [f for f in filas if f["tipo"] == "cierre_campana"]
    out["criterio_de_cierre.cerro_por_criterio"] = int(
        bool(cierre) and cierre[0]["motivo"].startswith("CRITERIO DE SEGURIDAD"))
    out.update(recalcular_3009(dir_3009 or (_TESIS / "REPORTE_2026-09-30_datos" / "csv")))
    out["_d_por_toma"] = {p["k"]: p["d"] for p in pares}
    return out


def recalcular_3009(d: Path) -> Dict[str, Any]:
    hw_todos, pares = [], []
    for s in ("", "_02", "_03", "_04", "_05"):
        eps = leer(d / f"20260930_sesion-evaluacion_etapa7_episodios{s}.csv")
        rep_arch = sorted(d.glob(f"*_sesion-replica_etapa7_capas-on_de-20260930{s}.csv"))[-1]
        reps: Dict[int, List[Dict[str, str]]] = {}
        for r in leer(rep_arch):
            if str(r.get("valido", "1")) in ("1", "True", "true"):
                reps.setdefault(int(r["episodio"]), []).append(r)
        for r in eps:
            if r["valido"] not in ("1", "True"):
                continue
            hw_todos.append(float(r["cobertura_aoi"]))
            e = int(r["episodio"])
            if e in reps:
                sim = sum(float(x["cobertura_aoi"]) for x in reps[e]) / len(reps[e])
                psim = sum(float(x["d_pared_min"]) for x in reps[e]) / len(reps[e])
                pares.append((int(r["semilla"]), float(r["cobertura_aoi"]) - sim,
                              float(r["d_pared_min"]) - psim))
    out = {"comparacion_3009.cobertura_hw.n": len(hw_todos),
           "comparacion_3009.cobertura_hw.media": sum(hw_todos) / len(hw_todos),
           "comparacion_3009.cobertura_hw.sd": statistics.stdev(hw_todos)}
    porp = ic_t([p[1] for p in pares])
    por_sem: Dict[int, List[float]] = {}
    for s_, dd, _ in pares:
        por_sem.setdefault(s_, []).append(dd)
    pore = ic_t([sum(v) / len(v) for v in por_sem.values()])
    pared = ic_t([p[2] for p in pares])
    for nombre, r in (("brecha_por_pares", porp), ("brecha_por_escenario", pore),
                      ("d_pared_hw_menos_replica", pared)):
        out[f"comparacion_3009.{nombre}.n"] = r["n"]
        out[f"comparacion_3009.{nombre}.media"] = r["media"]
        out[f"comparacion_3009.{nombre}.ic95.0"], out[f"comparacion_3009.{nombre}.ic95.1"] = r["ic95"]
    return out


def valor_json(js: Dict[str, Any], clave: str) -> Any:
    x: Any = js
    for parte in clave.split("."):
        if isinstance(x, list):
            x = x[int(parte)]
        elif isinstance(x, dict) and parte in x:
            x = x[parte]
        else:
            return None
    return x


def hashes_vigentes(filas: List[Dict[str, str]]) -> Dict[str, str]:
    vig: Dict[str, str] = {}
    for f in filas:
        if f["tipo"] == "creacion" and not vig:
            vig = json.loads(f["detalle"]).get("cabecera", {}).get("archivos_congelados", {})
        elif f["tipo"] == "correccion":
            vig = json.loads(f["detalle"])["archivos_congelados"]
    return vig


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Verificador independiente del análisis L2")
    ap.add_argument("carpeta", type=Path, help="carpeta de salida del análisis")
    ap.add_argument("--base", type=Path, default=_CARPETA / "resultados_demo_obstaculo")
    ap.add_argument("--dir-hw", type=Path, default=None, help="por defecto --base")
    ap.add_argument("--dir-replica", type=Path, default=None,
                    help="por defecto <base>/replica_campana/<nombre>")
    ap.add_argument("--dir-3009", type=Path, default=None)
    a = ap.parse_args(argv)
    js = json.loads((a.carpeta / "analisis.json").read_text(encoding="utf-8"))
    calc = recalcular(js, a.base, a.dir_hw, a.dir_replica, a.dir_3009)
    ok, fallas = 0, []
    for clave, v in calc.items():
        if clave.startswith("_"):
            continue
        j = valor_json(js, clave)
        bien = (j is not None and isinstance(v, (int, float)) and isinstance(j, (int, float))
                and abs(float(v) - float(j)) <= TOL)
        if bien:
            ok += 1
        else:
            fallas.append(f"{clave}: recalculado {v!r} · análisis {j!r}")
    # La d_k de cada toma (pares.csv).
    for f in leer(a.carpeta / "pares.csv"):
        k = int(f["intento"])
        v, j = calc["_d_por_toma"].get(k), num(f.get("d"))
        if (v is None and j is None) or (v is not None and j is not None and abs(v - j) <= TOL):
            ok += 1
        else:
            fallas.append(f"pares.csv intento {k}: d recalculada {v!r} · análisis {j!r}")
    # Los sha256 congelados.
    vig = hashes_vigentes(libro(a.base / "campanas" / js["campana"]))
    for clave, ruta in (("TESIS/PLAN_ANALISIS_campana_L2.md", _TESIS / "PLAN_ANALISIS_campana_L2.md"),
                        ("analizar_campana_l2.py", _CARPETA / "analizar_campana_l2.py"),
                        ("verificar_campana_l2.py", Path(__file__).resolve())):
        if vig.get(clave) == sha(ruta):
            ok += 1
        else:
            fallas.append(f"sha256 de {clave}: ahora {sha(ruta)[:12]} · libro "
                          f"{str(vig.get(clave))[:12]}")
    total = ok + len(fallas)
    print(f"verificador independiente — campaña '{js['campana']}' ({js.get('rotulo')}): "
          f"{ok}/{total} coinciden")
    for f in fallas:
        print(f"  ✗ {f}")
    return 0 if not fallas else 1


if __name__ == "__main__":
    sys.exit(main())
