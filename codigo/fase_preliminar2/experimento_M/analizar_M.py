"""
analizar_M.py — Experimento M: consolidación, punto de cruce y figura.

Lee todas las corridas válidas de `resultados/corridas/<condicion>_<sufijo>/`
(las del barrido principal `rep1`, `rep2` y las de refinamiento `refino_*`;
el piloto a batería se excluye) y produce:

  mediciones_M.csv            una fila por celda (condición × arquitectura ×
                              minilote × modo × corrida) y una fila agrupada
                              por celda con las corridas juntas
  cruce_M.csv                 el cruce GPU/CPU por arquitectura, en minilote
                              y en cardinal de enjambre equivalente
  descomposicion_M.csv        transferencia contra cómputo en la GPU
  fig_cruce_entrenamiento.png ms/paso contra B, log-log, un panel por
                              arquitectura, las tres condiciones, cruce marcado
  tabla_M.md, analisis_M.json

Definiciones (van también en cada tabla):
  t(B)      mediana del tiempo de pared de UN paso de gradiente de PPO sobre un
            minilote de B transiciones, en ms, calentamiento excluido;
            agrupada = mediana sobre los pasos de todas las corridas juntas.
  r(B)      t_gpu(B) / t_cpu_control(B), ambos en modo desde_sistema (el de
            SB3). r < 1 ⇔ la GPU es más rápida.
  cruce B*  el B donde log r cruza 0, por interpolación lineal en (log B, log r)
            entre los dos puntos medidos que lo encierran. Si r no cambia de
            signo en el rango medido: "ausente", con el sentido declarado.
  n*        B* / 12.8: cardinal equivalente con n_steps = 128, 4 entornos y
            40 pasos de gradiente por época fijos.

Uso:
  python analizar_M.py --proponer_refinamiento   # tras rep1+rep2: pares que encierran el cruce
  python analizar_M.py                           # análisis completo

Autor: José — Tesis Mecatrónica UVG
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

DIR_M: Path = Path(__file__).resolve().parent
DIR_RES: Path = DIR_M / "resultados"
DIR_CORRIDAS: Path = DIR_RES / "corridas"

CONDICIONES: Tuple[str, ...] = ("gpu", "cpu_control", "referencia")
ARQUITECTURAS: Tuple[str, ...] = ("256x256", "512x512", "1024x1024")
FACTOR_N: float = 12.8                      # B = 12.8 · n
N_CRUCE_INFERENCIA_EXP_L: int = 200         # bitácora, Exp L, barrido sintético
REFERENCIAS_EXP_L = {"cpu_control": 4.24, "gpu": 6.02}   # ms/minibatch mediana, mejor corrida

# Paleta de referencia validada (slots 1–3 en orden fijo) + codificación secundaria
ESTILO: Dict[str, Dict[str, Any]] = {
    "gpu":         {"color": "#2a78d6", "marker": "o", "ls": "-",  "etiqueta": "GPU (cu128, cuda)"},
    "cpu_control": {"color": "#eb6834", "marker": "s", "ls": "-",  "etiqueta": "CPU control (cu128, cpu)"},
    "referencia":  {"color": "#1baf7a", "marker": "^", "ls": "--", "etiqueta": "Referencia (2.10 cpu)"},
}
TINTA = {"primaria": "#0b0b0b", "secundaria": "#52514e", "rejilla": "#e4e3df", "fondo": "#fcfcfb"}


# ══════════════════════════════════════════════════════════════════════════════
#  Carga
# ══════════════════════════════════════════════════════════════════════════════

def corridas_validas() -> List[Path]:
    """Directorios de corrida del barrido y del refinamiento (excluye piloto y respaldos)."""
    if not DIR_CORRIDAS.exists():
        return []
    return sorted(d for d in DIR_CORRIDAS.iterdir()
                  if d.is_dir() and "piloto" not in d.name and "_respaldo_" not in d.name
                  and (d / "pasos.csv").exists())


def cargar_pasos(dirs: Sequence[Path]) -> Dict[Tuple[str, str, int, str, str], np.ndarray]:
    """(condicion, arquitectura, minilote, modo, sufijo) → tiempos medidos (ms), sin calentamiento."""
    acum: Dict[Tuple[str, str, int, str, str], List[float]] = defaultdict(list)
    for d in dirs:
        with open(d / "pasos.csv", newline="", encoding="utf-8") as f:
            for fila in csv.DictReader(f):
                if fila["calentamiento"] == "True":
                    continue
                clave = (fila["condicion"], fila["arquitectura"], int(fila["minilote"]),
                         fila["modo"], fila["sufijo"])
                acum[clave].append(float(fila["t_ms"]))
    return {k: np.asarray(v) for k, v in acum.items()}


def cargar_calentamiento(dirs: Sequence[Path]) -> Dict[Tuple[str, str, int, str, str], np.ndarray]:
    """Igual que `cargar_pasos` pero sólo los pasos de calentamiento (para declararlos)."""
    acum: Dict[Tuple[str, str, int, str, str], List[float]] = defaultdict(list)
    for d in dirs:
        with open(d / "pasos.csv", newline="", encoding="utf-8") as f:
            for fila in csv.DictReader(f):
                if fila["calentamiento"] != "True":
                    continue
                acum[(fila["condicion"], fila["arquitectura"], int(fila["minilote"]),
                      fila["modo"], fila["sufijo"])].append(float(fila["t_ms"]))
    return {k: np.asarray(v) for k, v in acum.items()}


def cargar_reportes(dirs: Sequence[Path]) -> Dict[str, Dict[str, Any]]:
    return {d.name: json.loads((d / "reporte.json").read_text(encoding="utf-8")) for d in dirs}


def agrupar(pasos: Dict[Tuple[str, str, int, str, str], np.ndarray],
            filtro_sufijo: Optional[str] = None) -> Dict[Tuple[str, str, int, str], np.ndarray]:
    """Junta las corridas: (condicion, arq, B, modo) → todos los pasos. `filtro_sufijo` restringe a una."""
    acum: Dict[Tuple[str, str, int, str], List[np.ndarray]] = defaultdict(list)
    for (c, a, b, m, s), t in pasos.items():
        if filtro_sufijo is not None and not s.endswith(filtro_sufijo):
            continue
        acum[(c, a, b, m)].append(t)
    return {k: np.concatenate(v) for k, v in acum.items()}


# ══════════════════════════════════════════════════════════════════════════════
#  Cruce
# ══════════════════════════════════════════════════════════════════════════════

def curva(grupo: Dict[Tuple[str, str, int, str], np.ndarray], cond: str, arq: str,
          modo: str = "desde_sistema") -> Dict[int, float]:
    return {b: float(np.median(t)) for (c, a, b, m), t in grupo.items()
            if c == cond and a == arq and m == modo}


def localizar_cruce(t_gpu: Dict[int, float], t_cpu: Dict[int, float]) -> Dict[str, Any]:
    """
    Cruce de r(B) = t_gpu / t_cpu sobre los B medidos en ambas curvas.
    Interpolación lineal de log r contra log B entre el último B con r > 1 y
    el primero con r ≤ 1. Si hay más de un cambio de signo se reportan todos
    (y el análisis lo declara como no monótono).
    """
    bs = sorted(set(t_gpu) & set(t_cpu))
    if not bs:
        return {"estado": "sin_datos"}
    r = {b: t_gpu[b] / t_cpu[b] for b in bs}
    cambios: List[Dict[str, Any]] = []
    for b0, b1 in zip(bs[:-1], bs[1:]):
        l0, l1 = math.log(r[b0]), math.log(r[b1])
        if (l0 > 0) != (l1 > 0):
            x0, x1 = math.log(b0), math.log(b1)
            x = x0 + (0.0 - l0) * (x1 - x0) / (l1 - l0)
            cambios.append({"B_inf": b0, "B_sup": b1, "r_inf": r[b0], "r_sup": r[b1],
                            "B_cruce": math.exp(x), "sentido": "gpu_gana_arriba" if l1 < 0 else "gpu_gana_abajo"})
    base = {"B_medidos": bs, "r": {str(b): r[b] for b in bs}}
    if not cambios:
        if all(r[b] > 1 for b in bs):
            return {**base, "estado": "ausente_cpu_gana_todo", "B_cruce": None,
                    "declaracion": f"GPU más lenta en todo el rango medido (B ∈ [{bs[0]}, {bs[-1]}]): cruce > {bs[-1]}"}
        return {**base, "estado": "ausente_gpu_gana_todo", "B_cruce": None,
                "declaracion": f"GPU más rápida en todo el rango medido: cruce < {bs[0]}"}
    principal = cambios[0]
    return {**base, "estado": "unico" if len(cambios) == 1 else "multiple_no_monotono",
            "cambios": cambios, "B_cruce": principal["B_cruce"],
            "n_cruce": principal["B_cruce"] / FACTOR_N,
            "B_inf": principal["B_inf"], "B_sup": principal["B_sup"]}


def proponer_intermedios(b_inf: int, b_sup: int, k: int = 3, multiplo: int = 64) -> List[int]:
    """k puntos geométricamente equiespaciados en (b_inf, b_sup), redondeados a múltiplos de 64."""
    pts = [b_inf * (b_sup / b_inf) ** (i / (k + 1)) for i in range(1, k + 1)]
    return sorted({int(round(p / multiplo) * multiplo) for p in pts} - {b_inf, b_sup})


# ══════════════════════════════════════════════════════════════════════════════
#  Salidas
# ══════════════════════════════════════════════════════════════════════════════

def fmt(x: Optional[float], d: int = 3) -> str:
    return "—" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:.{d}f}"


def escribir(ruta: Path, texto: str) -> None:
    ruta.write_bytes(texto.encode("utf-8"))


def escribir_csv(ruta: Path, filas: List[Dict[str, Any]]) -> None:
    if not filas:
        return
    campos: List[str] = []
    for f in filas:
        for k in f:
            if k not in campos:
                campos.append(k)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos, lineterminator="\n")
        w.writeheader()
        for fila in filas:
            w.writerow({k: (repr(v) if isinstance(v, float) else v) for k, v in fila.items()})


def figura(grupo, cruces: Dict[str, Dict[str, Any]], arqs: Sequence[str],
           params: Dict[str, int], ruta: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, NullLocator, FuncFormatter

    fig, ejes = plt.subplots(1, len(arqs), figsize=(5.0 * len(arqs), 4.8), sharey=True)
    ejes = np.atleast_1d(ejes)
    fig.patch.set_facecolor(TINTA["fondo"])
    for ax, arq in zip(ejes, arqs):
        ax.set_facecolor(TINTA["fondo"])
        for cond in CONDICIONES:
            cv = curva(grupo, cond, arq)
            if not cv:
                continue
            bs = sorted(cv)
            e = ESTILO[cond]
            ax.plot(bs, [cv[b] for b in bs], color=e["color"], ls=e["ls"], lw=2,
                    marker=e["marker"], ms=6, mec=TINTA["fondo"], mew=1.5, label=e["etiqueta"], zorder=3)
        cv_res = curva(grupo, "gpu", arq, "residente")
        if cv_res:
            bs = sorted(cv_res)
            ax.plot(bs, [cv_res[b] for b in bs], color=ESTILO["gpu"]["color"], ls=":", lw=2,
                    marker="o", ms=5, mfc=TINTA["fondo"], label="GPU, datos residentes", zorder=2)
        cr = cruces.get(arq, {})
        if cr.get("B_cruce"):
            bx = cr["B_cruce"]
            ax.axvline(bx, color=TINTA["secundaria"], lw=1, ls="--", zorder=1)
            ax.annotate(f"cruce\nB* ≈ {bx:,.0f}\nn* ≈ {bx / FACTOR_N:,.0f}",
                        xy=(bx, 0.97), xycoords=("data", "axes fraction"), ha="right", va="top",
                        fontsize=9, color=TINTA["primaria"],
                        xytext=(-6, 0), textcoords="offset points")
        else:
            ax.text(0.03, 0.97, "cruce ausente en el rango\n" + cr.get("declaracion", ""),
                    transform=ax.transAxes, ha="left", va="top", fontsize=8.5, color=TINTA["primaria"], wrap=True)
        ax.set_xscale("log", base=2)
        ax.set_yscale("log")
        ticks = [64, 128, 256, 512, 1024, 2048, 4096, 8192]
        ax.xaxis.set_major_locator(FixedLocator(ticks))
        ax.xaxis.set_minor_locator(NullLocator())
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v)}"))
        ax.tick_params(axis="x", labelrotation=45, labelsize=8, colors=TINTA["secundaria"])
        ax.tick_params(axis="y", labelsize=8, colors=TINTA["secundaria"])
        sec = ax.secondary_xaxis("top", functions=(lambda b: b / FACTOR_N, lambda n: n * FACTOR_N))
        sec.xaxis.set_major_locator(FixedLocator([t / FACTOR_N for t in ticks]))
        sec.xaxis.set_minor_locator(NullLocator())
        sec.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        sec.tick_params(labelsize=8, colors=TINTA["secundaria"])
        sec.set_xlabel("n equivalente (agentes)", fontsize=9, color=TINTA["secundaria"])
        ax.grid(True, which="major", color=TINTA["rejilla"], lw=0.8, zorder=0)
        for s in ("right",):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom", "top"):
            ax.spines[s].set_color(TINTA["rejilla"])
        ax.set_title(f"[{arq.replace('x', ', ')}] — {params.get(arq, 0):,} parámetros",
                     fontsize=10, color=TINTA["primaria"], pad=28)
        ax.set_xlabel("tamaño de minilote B (transiciones)", fontsize=9, color=TINTA["secundaria"])
    ejes[0].set_ylabel("tiempo por paso de gradiente [ms]\n(mediana, rep1+rep2)", fontsize=9,
                       color=TINTA["secundaria"])
    manejadores, etiquetas = ejes[0].get_legend_handles_labels()
    fig.legend(manejadores, etiquetas, loc="lower center", ncol=4, frameon=False, fontsize=9,
               bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Exp M — costo de un paso de PPO frente al tamaño de minilote "
                 "(n = B / 12.8 con n_steps=128, 4 entornos, 40 pasos/época)",
                 fontsize=11, color=TINTA["primaria"], y=1.0)
    fig.tight_layout(rect=(0, 0.06, 1, 0.97))
    fig.savefig(ruta, dpi=160, facecolor=TINTA["fondo"], bbox_inches="tight")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
#  Principal
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--proponer_refinamiento", action="store_true")
    args = ap.parse_args()

    dirs = corridas_validas()
    if not dirs:
        raise SystemExit("[M] no hay corridas válidas en resultados/corridas/")
    pasos = cargar_pasos(dirs)
    reportes = cargar_reportes(dirs)
    grupo = agrupar(pasos)
    arqs = [a for a in ARQUITECTURAS if any(k[1] == a for k in grupo)]
    params: Dict[str, int] = {}
    for rep in reportes.values():
        params.update(rep["diseno"]["parametros"])

    # ── Controles del banco: todos deben estar aprobados ──────────────────────
    controles = {n: r.get("control_banco") for n, r in reportes.items() if r.get("control_banco")}
    rechazados = [n for n, c in controles.items() if not c["aprobado"]]
    if rechazados:
        raise SystemExit(f"[M] PARADA: control del banco no aprobado en {rechazados}")

    cruces = {a: localizar_cruce(curva(grupo, "gpu", a), curva(grupo, "cpu_control", a)) for a in arqs}

    if args.proponer_refinamiento:
        for a, c in cruces.items():
            if c.get("B_cruce"):
                print(f"{a}: cruce entre B={c['B_inf']} y {c['B_sup']} (≈{c['B_cruce']:.0f}); "
                      f"intermedios propuestos: {proponer_intermedios(c['B_inf'], c['B_sup'])}")
            else:
                print(f"{a}: {c['estado']} — {c.get('declaracion', '')}; sin refinamiento")
        return

    # Regla permanente: NUNCA sobrescribir resultados. Respaldo con fecha antes de escribir.
    marca = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    for nombre in ("analisis_M.json", "tabla_M.md", "mediciones_M.csv", "fig_cruce_entrenamiento.png"):
        ruta = DIR_RES / nombre
        if ruta.exists():
            ruta.rename(ruta.with_name(f"{ruta.stem}_respaldo_{marca}{ruta.suffix}"))
            print(f"[M] respaldado {nombre}")

    # Robustez del cruce: con cada repetición por separado
    cruces_por_rep: Dict[str, Dict[str, Any]] = {}
    for rep in ("rep1", "rep2"):
        g = agrupar({k: v for k, v in pasos.items() if k[4] in (rep, f"refino_{rep}")})
        cruces_por_rep[rep] = {a: localizar_cruce(curva(g, "gpu", a), curva(g, "cpu_control", a)) for a in arqs}
    cruces_residente = {a: localizar_cruce(curva(grupo, "gpu", a, "residente"), curva(grupo, "cpu_control", a))
                        for a in arqs}
    cruces_vs_ref = {a: localizar_cruce(curva(grupo, "gpu", a), curva(grupo, "referencia", a)) for a in arqs}

    # ── mediciones_M.csv ──────────────────────────────────────────────────────
    filas: List[Dict[str, Any]] = []
    for (c, a, b, m, s), t in sorted(pasos.items()):
        filas.append({"nivel": "corrida", "condicion": c, "sufijo": s, "arquitectura": a,
                      "n_parametros": params.get(a), "minilote": b, "n_equivalente": b / FACTOR_N,
                      "modo": m, "n_pasos": int(len(t)), "t_ms_mediana": float(np.median(t)),
                      "t_ms_p10": float(np.percentile(t, 10)), "t_ms_p90": float(np.percentile(t, 90)),
                      "t_ms_min": float(np.min(t)), "t_ms_media": float(np.mean(t)),
                      "definicion": "tiempo de pared de un paso de gradiente PPO sobre B transiciones, "
                                    "calentamiento excluido, una corrida"})
    for (c, a, b, m), t in sorted(grupo.items()):
        filas.append({"nivel": "agrupado", "condicion": c, "sufijo": "todas", "arquitectura": a,
                      "n_parametros": params.get(a), "minilote": b, "n_equivalente": b / FACTOR_N,
                      "modo": m, "n_pasos": int(len(t)), "t_ms_mediana": float(np.median(t)),
                      "t_ms_p10": float(np.percentile(t, 10)), "t_ms_p90": float(np.percentile(t, 90)),
                      "t_ms_min": float(np.min(t)), "t_ms_media": float(np.mean(t)),
                      "definicion": "ídem, pasos de todas las corridas juntos"})
    escribir_csv(DIR_RES / "mediciones_M.csv", filas)

    # ── cruce_M.csv ───────────────────────────────────────────────────────────
    filas_cruce: List[Dict[str, Any]] = []
    for a in arqs:
        for base, dic in (("agrupado", cruces), ("rep1", cruces_por_rep["rep1"]),
                          ("rep2", cruces_por_rep["rep2"]), ("agrupado_residente", cruces_residente),
                          ("agrupado_vs_referencia", cruces_vs_ref)):
            c = dic[a]
            filas_cruce.append({"arquitectura": a, "base": base, "estado": c["estado"],
                                "B_inf": c.get("B_inf"), "B_sup": c.get("B_sup"),
                                "B_cruce": c.get("B_cruce"),
                                "n_cruce": (c["B_cruce"] / FACTOR_N) if c.get("B_cruce") else None,
                                "declaracion": c.get("declaracion", "")})
    escribir_csv(DIR_RES / "cruce_M.csv", filas_cruce)

    # ── descomposicion_M.csv (sólo GPU) ───────────────────────────────────────
    filas_desc: List[Dict[str, Any]] = []
    for a in arqs:
        sis, res = curva(grupo, "gpu", a), curva(grupo, "gpu", a, "residente")
        cpu = curva(grupo, "cpu_control", a)
        for b in sorted(set(sis) & set(res)):
            filas_desc.append({"arquitectura": a, "minilote": b, "n_equivalente": b / FACTOR_N,
                               "t_desde_sistema_ms": sis[b], "t_residente_ms": res[b],
                               "t_transferencia_ms": sis[b] - res[b],
                               "fraccion_transferencia": (sis[b] - res[b]) / sis[b],
                               "t_cpu_control_ms": cpu.get(b)})
    escribir_csv(DIR_RES / "descomposicion_M.csv", filas_desc)

    figura(grupo, cruces, arqs, params, DIR_RES / "fig_cruce_entrenamiento.png")

    # ── calentamiento declarado ───────────────────────────────────────────────
    cal = cargar_calentamiento(dirs)
    exceso_cal: Dict[str, float] = {}
    for c in CONDICIONES:
        razones = [float(np.median(cal[k][:10]) / np.median(pasos[k])) for k in cal
                   if k[0] == c and k in pasos and len(cal[k]) >= 10]
        if razones:
            exceso_cal[c] = float(np.median(razones))

    carga = {n: {"media": r["carga_cpu"]["ocupacion_sistema_pct_media"],
                 "p90": r["carga_cpu"]["ocupacion_sistema_pct_p90"],
                 "alimentacion": r["hardware"].get("alimentacion_BatteryStatus|carga"),
                 "gpu_ini": r["hardware"].get("gpu_nvidia_smi_al_arrancar"),
                 "gpu_fin": r["hardware"].get("gpu_nvidia_smi_al_terminar")}
             for n, r in reportes.items() if "carga_cpu" in r}

    analisis = {"corridas": [d.name for d in dirs], "parametros": params,
                "controles_banco": controles, "cruces": cruces, "cruces_por_rep": cruces_por_rep,
                "cruces_residente": cruces_residente, "cruces_vs_referencia": cruces_vs_ref,
                "calentamiento_mediana_primeros10_sobre_medido": exceso_cal, "carga": carga,
                "hardware": next(iter(reportes.values()))["hardware"]}
    escribir(DIR_RES / "analisis_M.json", json.dumps(analisis, indent=2, ensure_ascii=False, default=str))

    # ── tabla_M.md ────────────────────────────────────────────────────────────
    L: List[str] = ["# Exp M — tablas", ""]
    L += ["## Control del banco", "",
          "train()/520 = PPO.train() real de SB3, configuración de la tesis (2560 transiciones, B=64, "
          "13×40 minilotes), 10 llamadas tras 2 descartadas, mediana del ms/minilote. Banco B=64 = mediana "
          "de 200 pasos aislados, mismo proceso, mismo modelo. Tolerancia 20 %.", "",
          "| corrida | train()/520 [ms] | mín | banco B=64 [ms] | desvío | Exp L (ms/minibatch, mediana mejor corrida) | ¿aprobado? |",
          "|---|---|---|---|---|---|---|"]
    for n, c in sorted(controles.items()):
        cond = n.split("_rep")[0]
        L.append(f"| {n} | {fmt(c['ms_por_minilote_mediana'])} | {fmt(c['ms_por_minilote_min'])} | "
                 f"{fmt(c['banco_ms_mediana_B64'])} | {100*c['desvio_relativo']:.1f} % | "
                 f"{REFERENCIAS_EXP_L.get(cond, '—')} | {'sí' if c['aprobado'] else 'NO'} |")
    L += ["", "## Punto de cruce GPU / CPU control (modo desde_sistema = SB3 real)", "",
          "B* por interpolación log-log de r = t_gpu/t_cpu_control entre los dos B medidos que lo encierran; "
          "n* = B*/12.8 (supuesto: n_steps=128, 4 entornos, 40 pasos de gradiente por época fijos). "
          "t = mediana por paso, calentamiento excluido.", "",
          "| arquitectura | parámetros | base | B encerrado | B* | n* equivalente | estado |",
          "|---|---|---|---|---|---|---|"]
    for a in arqs:
        for base, dic in (("rep1+rep2", cruces), ("sólo rep1", cruces_por_rep["rep1"]),
                          ("sólo rep2", cruces_por_rep["rep2"]),
                          ("datos residentes", cruces_residente), ("GPU vs referencia", cruces_vs_ref)):
            c = dic[a]
            enc = f"[{c['B_inf']}, {c['B_sup']}]" if c.get("B_inf") else "—"
            bst = fmt(c.get("B_cruce"), 0) if c.get("B_cruce") else "—"
            nst = fmt(c["B_cruce"] / FACTOR_N, 0) if c.get("B_cruce") else "—"
            L.append(f"| {a} | {params.get(a, 0):,} | {base} | {enc} | {bst} | {nst} | "
                     f"{c['estado']}{(' — ' + c['declaracion']) if c.get('declaracion') else ''} |")
    L += ["", "## Descomposición transferencia contra cómputo (sólo GPU)", "",
          "La condición residente sólo tiene sentido en la GPU: en CPU los datos ya están en memoria "
          "del sistema y no hay transferencia que descontar. transferencia = t_desde_sistema − t_residente "
          "(copia anfitrión→dispositivo de los seis arreglos del minilote más el indexado NumPy, tal como "
          "lo hace SB3). Medianas agrupadas, ms por paso.", "",
          "| arquitectura | B | n equiv. | t desde sistema | t residente | transferencia | % transferencia | t CPU control |",
          "|---|---|---|---|---|---|---|---|"]
    for f in filas_desc:
        L.append(f"| {f['arquitectura']} | {f['minilote']} | {f['n_equivalente']:g} | "
                 f"{fmt(f['t_desde_sistema_ms'])} | {fmt(f['t_residente_ms'])} | "
                 f"{fmt(f['t_transferencia_ms'])} | {100*f['fraccion_transferencia']:.1f} % | "
                 f"{fmt(f['t_cpu_control_ms'])} |")
    L += ["", "## Tiempos por paso (mediana agrupada, ms; r = gpu/cpu_control)", ""]
    for a in arqs:
        L += [f"### {a} ({params.get(a, 0):,} parámetros)", "",
              "| B | n equiv. | gpu | gpu residente | cpu_control | referencia | r |", "|---|---|---|---|---|---|---|"]
        g_, gr, cc, rf = (curva(grupo, "gpu", a), curva(grupo, "gpu", a, "residente"),
                          curva(grupo, "cpu_control", a), curva(grupo, "referencia", a))
        for b in sorted(set(g_) | set(cc) | set(rf)):
            r = g_[b] / cc[b] if b in g_ and b in cc else None
            L.append(f"| {b} | {b / FACTOR_N:g} | {fmt(g_.get(b))} | {fmt(gr.get(b))} | {fmt(cc.get(b))} | "
                     f"{fmt(rf.get(b))} | {fmt(r)} |")
        L.append("")
    L += ["## Carga del sistema por corrida", "",
          "| corrida | ocupación media % (12 hilos) | p90 % | alimentación (2=CA) | GPU al arrancar | GPU al terminar |",
          "|---|---|---|---|---|---|"]
    for n, c in sorted(carga.items()):
        L.append(f"| {n} | {c['media']:.1f} | {c['p90']:.1f} | {c['alimentacion']} | {c['gpu_ini']} | {c['gpu_fin']} |")
    L += ["", f"Calentamiento: mediana, sobre celdas, de (mediana de los 10 primeros pasos descartados / "
              f"mediana medida): {json.dumps({k: round(v, 2) for k, v in exceso_cal.items()})}", ""]
    escribir(DIR_RES / "tabla_M.md", "\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
