"""
analizar_exploratorio_Q.py
==========================
EXPLORATORIO — fuera de la regla de parada. Análisis de S2 y S3 del Exp Q
desde `resultados/experimento_Q_EXPLORATORIO_S2_S3.csv`.

Es el MISMO análisis que el de S1 (`analizar_experimento_Q.py`: tablas, las
cuatro comparaciones pareadas con su denominador del §3.6, criterios,
indicador, seguridad, mecanismo por restricción ligante y parte de ω), con
sus listas de métricas y sus funciones importadas, y dos secciones más:

  ATRIBUCIÓN POR SEMILLA  para cada criterio de falla de Sk_din, las semillas
                          con el evento y si la MISMA semilla lo tiene en
                          Sk_ctrl, Sk_quieto y Sk_sinvel ("no aplica" en el
                          control para los criterios que exigen obstáculo).
  HIPÓTESIS DEL ENCIERRO  fallbacks del QP, filas F1 saturadas e infactibles
  (§2.3 de la propuesta)  por normales opuestas con obstáculo activo, con sus
                          semillas, en din, quieto y sinvel.

Agregado el 24-10 (pedido de José; los datos no cambian):

  EVENTOS RAROS           episodios con al menos un contacto, fallback,
                          agotado, infactible con obstáculo activo y
                          acercamiento bajo 0,13 m, con IC95 de
                          Clopper-Pearson, y McNemar exacta pareada para
                          din−quieto, din−ctrl y sinvel−din.
  FALLBACK Y DISTANCIA    d_min mínimo y episodios bajo 0,10 m, separando los
                          episodios con fallback del QP de los demás.

Salidas: resultados/resumen_Q_EXPLORATORIO.txt,
figuras/fig_EXPLORATORIO_obstaculos_moviles_intervencion.png,
figuras/fig_EXPLORATORIO_obstaculos_moviles_costo.png. Lo verifica, con
código propio, `verificar_cifras_exploratorio_Q.py`.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

import sys
_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

from analizar_experimento_Q import (BASES_MECANISMO, COMPARACIONES, CRITERIOS,
                                    METRICAS_COBERTURA, METRICAS_COMUNES,
                                    METRICAS_SOLO_TABLA, TIPOS, columna,
                                    ic95_pareado, marca_sig)

RUTA_CSV_EXPL: Path = _CARPETA / "resultados" / "experimento_Q_EXPLORATORIO_S2_S3.csv"
RUTA_REG_EXPL: Path = _CARPETA / "resultados" / "registro_Q_EXPLORATORIO.txt"
RUTA_RES_EXPL: Path = _CARPETA / "resultados" / "resumen_Q_EXPLORATORIO.txt"
DIR_FIG: Path = _CARPETA / "figuras"
DPI_FIG: int = 300
NIVELES_EXPL: Tuple[str, ...] = ("S2", "S3")
ROTULO_FIG: str = "EXPLORATORIO (fuera de la regla de parada)"
#: Criterios que exigen un obstáculo físico: en el control "no aplica".
SOLO_CON_OBSTACULO: Tuple[str, ...] = ("contactos_obst_eventos",
                                       "escape_infactibles_junto_obst")
#: Hipótesis del encierro (§2.3): (columna, etiqueta).
ENCIERRO: Tuple[Tuple[str, str], ...] = (
    ("qp_fallbacks", "fallbacks del QP"),
    ("f1_filas_saturadas", "filas F1 saturadas"),
    ("escape_infact_op_con_obst", "infactibles opuestas con obstáculo activo"),
)
#: EVENTOS RAROS (24-10): (nombre, columna, ¿exige obstáculo físico?). Un
#: episodio "tiene" el evento si la columna es > 0. Contra el control, los que
#: exigen obstáculo físico son "no aplica": el obstáculo del control no es
#: físico (los agentes lo atraviesan y "bajo 0,13 m" da 100/100).
EVENTOS: Tuple[Tuple[str, str, bool], ...] = (
    ("contacto", "contactos_obst_eventos", True),
    ("fallback", "qp_fallbacks", False),
    ("agotado", "escape_agotados", False),
    ("infactible con obst. activo", "escape_infactibles_junto_obst", True),
    ("bajo 0,13 m", "viol_cota_obst_agente_eps", True),
)
#: Pares de la prueba exacta pareada: (A, B).
PARES_MCNEMAR: Tuple[Tuple[str, str], ...] = (("din", "quieto"), ("din", "ctrl"),
                                              ("sinvel", "din"))
UMBRAL_DISTANCIA_M: float = 0.10


def episodios_con(datos, c: str, m: str, sem: Sequence[int]) -> set:
    """Semillas de la condición con al menos un evento (columna > 0)."""
    return {s for s in sem if datos[c][s][m] > 0}


def clopper_pearson(k: int, n: int, alfa: float = 0.05) -> Tuple[float, float]:
    """IC exacto de Clopper-Pearson para k de n (cuantiles de la beta)."""
    from scipy.stats import beta
    lo = 0.0 if k == 0 else float(beta.ppf(alfa / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - alfa / 2, k + 1, n - k))
    return lo, hi


def mcnemar_exacta(a: set, b: set) -> Tuple[int, int, float]:
    """(sólo en A, sólo en B, p bilateral exacta de la binomial con p = 1/2)."""
    from scipy.stats import binomtest
    solo_a, solo_b = len(a - b), len(b - a)
    n = solo_a + solo_b
    if n == 0:
        return solo_a, solo_b, 1.0
    return solo_a, solo_b, float(binomtest(min(solo_a, solo_b), n, 0.5).pvalue)


def formato_p(p: float) -> str:
    return "< 0.0001" if p < 0.0001 else f"{p:.4f}"


def cargar_expl() -> Dict[str, Dict[int, Dict[str, float]]]:
    datos: Dict[str, Dict[int, Dict[str, float]]] = {}
    with open(RUTA_CSV_EXPL, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            fila: Dict[str, float] = {}
            for k, v in r.items():
                try:
                    fila[k] = float(v)
                except ValueError:
                    pass
            datos.setdefault(r["condicion"], {})[int(r["seed_ep"])] = fila
    return datos


def semillas_con(datos, c: str, m: str, sem: Sequence[int]) -> List[int]:
    return [s for s in sem if datos[c][s][m] > 0]


def atribucion(datos, k: str, m: str, sem: Sequence[int]) -> List[Tuple[int, str, str, str]]:
    """(semilla, ctrl, quieto, sinvel) para cada semilla de Sk_din con el evento."""
    salida = []
    for s in semillas_con(datos, f"{k}_din", m, sem):
        def mismo(t: str) -> str:
            if t == "ctrl" and m in SOLO_CON_OBSTACULO:
                return "no aplica"
            return "sí" if datos[f"{k}_{t}"][s][m] > 0 else "no"
        salida.append((s, mismo("ctrl"), mismo("quieto"), mismo("sinvel")))
    return salida


def _lista(xs: Sequence[int]) -> str:
    return ", ".join(str(x) for x in xs) if xs else "ninguna"


def main() -> None:
    datos = cargar_expl()
    niveles = [k for k in NIVELES_EXPL if f"{k}_din" in datos]
    sem = sorted(datos[f"{niveles[0]}_din"].keys())
    L: List[str] = []
    L.append("EXPLORATORIO — fuera de la regla de parada: S2 y S3 del Exp Q, corridos "
             "después de la parada de S1.")
    L.append("NO cambian el veredicto del Exp Q (S1 detiene por la regla del Exp O).")
    L.append("Mismo análisis que S1 (resumen_experimento_Q.txt): configuración final con")
    L.append("la fila F1 (k = 1), arena 3,0, n=5,")
    L.append(f"{len(sem)} semillas {sem[0]}–{sem[-1]}. Obstáculos a 0,05 m/s; objetivos")
    L.append("transparentes; pareo por semilla (mismas poses y objetivos iniciales).")
    L.append("ESTADÍSTICA: Δ pareada por semilla; IC95 = media ± 1,96·EE (ddof = 1);")
    L.append("'*' si el IC excluye el 0; sin corrección por multiplicidad.")
    L.append("H MÍNIMO: en Sk_din la fila del obstáculo que se acerca entra al filtro")
    L.append("con h_eq = h − s/α; el mecanismo se lee por restricción LIGANTE.")
    L.append("=" * 78)
    L.append("")
    if RUTA_REG_EXPL.exists():
        L += ["REGISTRO DE CORRIDA"] + ["  " + x for x in
                                       RUTA_REG_EXPL.read_text(encoding="utf-8").splitlines()[1:]]
        L.append("")

    todas = METRICAS_COBERTURA + METRICAS_COMUNES + METRICAS_SOLO_TABLA
    for k in niveles:
        conds = [f"{k}_{t}" for t in TIPOS if f"{k}_{t}" in datos]
        L.append(f"TABLA {k} — medias sobre {len(sem)} episodios")
        L.append(f"  {'métrica':46s}" + "".join(f"{c:>14s}" for c in conds))
        for m, etiq in todas:
            vals = []
            for c in conds:
                v = columna(datos, c, m, sem)
                v = v[np.isfinite(v)]
                vals.append(float(np.mean(v)) if len(v) else float("nan"))
            L.append(f"  {etiq:46s}" + "".join(f"{v:14.8f}" for v in vals))
        for m, etiq in (("d_min_obst_superficie", "d_min obst., mínimo global [m]"),
                        ("d_min_pared_centro", "d_min pared, mínimo global [m]")):
            vals = []
            for c in conds:
                v = columna(datos, c, m, sem)
                v = v[np.isfinite(v)]
                vals.append(float(np.min(v)) if len(v) else float("nan"))
            L.append(f"  {etiq:46s}" + "".join(f"{v:14.8f}" for v in vals))
        L.append("")
        for a, b, cobs, titulo in COMPARACIONES:
            L.append(f"COMPARACIÓN PAREADA {k}_{a} − {k}_{b} ({titulo}; {len(sem)} semillas)")
            L.append(f"  {'métrica':46s} {'Δ':>13s} {'IC95':>30s}  {'>0':>4s} {'<0':>4s}")
            etiquetas = dict(METRICAS_COBERTURA)
            for m, etiq in tuple((c, etiquetas[c]) for c in cobs) + METRICAS_COMUNES:
                d = columna(datos, f"{k}_{a}", m, sem) - columna(datos, f"{k}_{b}", m, sem)
                mm, lo, hi = ic95_pareado(d)
                L.append(f"  {etiq:46s} {mm:+13.8f} [{lo:+13.8f}, {hi:+13.8f}]{marca_sig(lo, hi)}"
                         f" {int(np.sum(d > 0)):4d} {int(np.sum(d < 0)):4d}")
            c0 = cobs[0]
            rel = (columna(datos, f"{k}_{a}", c0, sem) / columna(datos, f"{k}_{b}", c0, sem) - 1)
            mm, lo, hi = ic95_pareado(rel)
            L.append(f"  costo relativo en {c0}: {100*mm:+.4f} % [{100*lo:+.4f}, {100*hi:+.4f}]")
            L.append("")

    L.append("CRITERIOS DE FALLA (sumas sobre los episodios; EXPLORATORIO: no detienen)")
    for k in niveles:
        for t in ("din", "quieto", "sinvel"):
            c = f"{k}_{t}"
            L.append(f"  {c}{' (decidiría)' if t == 'din' else ''}: " + "; ".join(
                f"{e} {int(columna(datos, c, m, sem).sum())}" for m, e in CRITERIOS))
    L.append("ATRIBUCIÓN POR SEMILLA — criterios de falla de Sk_din: ¿la MISMA semilla tiene")
    L.append("el mismo evento en Sk_ctrl, Sk_quieto y Sk_sinvel? ('no aplica': el criterio")
    L.append("exige un obstáculo físico y el control no lo tiene)")
    for k in niveles:
        for m, e in CRITERIOS:
            at = atribucion(datos, k, m, sem)
            if not at:
                L.append(f"  {k} {e}: ninguna semilla en {k}_din")
                continue
            n_ctrl = sum(x[1] == "sí" for x in at)
            n_q = sum(x[2] == "sí" for x in at)
            n_sv = sum(x[3] == "sí" for x in at)
            L.append(f"  {k} {e}: {len(at)} semillas en {k}_din; con el mismo evento: "
                     f"ctrl {n_ctrl if m not in SOLO_CON_OBSTACULO else 'no aplica'}, "
                     f"quieto {n_q}, sinvel {n_sv}")
            for s, a_c, a_q, a_s in at:
                L.append(f"    {s}: {k}_din {int(datos[f'{k}_din'][s][m])}; ctrl {a_c}; "
                         f"quieto {a_q}; sinvel {a_s}")
    L.append("HIPÓTESIS DEL ENCIERRO (§2.3) — fallbacks del QP, filas F1 saturadas e")
    L.append("infactibles por normales opuestas con obstáculo activo, con sus semillas")
    for k in niveles:
        for t in ("din", "quieto", "sinvel"):
            c = f"{k}_{t}"
            partes = []
            for m, e in ENCIERRO:
                v = columna(datos, c, m, sem)
                ss = semillas_con(datos, c, m, sem)
                partes.append(f"{e} {int(v.sum())} en {len(ss)}/{len(sem)} episodios "
                              f"(semillas: {_lista(ss)})")
            L.append(f"  {c}: " + "; ".join(partes))
    L.append("INDICADOR ADELANTADO (intervención > 0,5; se reporta, no detiene)")
    for k in niveles:
        for t in TIPOS:
            c = f"{k}_{t}"
            f = columna(datos, c, "cbf_frac_interv", sem)
            L.append(f"  {c}: media {np.mean(f):.8f}; episodios > 0,5: "
                     f"{int(np.sum(f > 0.5))}/{len(sem)}; máx. {np.max(f):.8f}")
    L.append("")

    L.append("SEGURIDAD — totales sobre los episodios de cada condición con obstáculos")
    for k in niveles:
        for t in ("din", "quieto", "sinvel"):
            c = f"{k}_{t}"

            def tot(m: str) -> int:
                return int(columna(datos, c, m, sem).sum())
            dmin = columna(datos, c, "d_min_obst_superficie", sem)
            L.append(f"  {c}: contactos con obstáculo {tot('contactos_obst_eventos')} "
                     f"(empuje {tot('contactos_obst_empuje')}, avance "
                     f"{tot('contactos_obst_avance')}); colisiones <0,15 m "
                     f"{tot('colisiones_015')}; <0,22 m {tot('colisiones_022')}; "
                     f"contacto con pared {tot('contacto_pared')}; fallbacks del QP "
                     f"{tot('qp_fallbacks')}; filas F1 saturadas {tot('f1_filas_saturadas')}; "
                     f"agente-eps bajo 0,13 m {tot('viol_cota_obst_agente_eps')}; "
                     f"d_min obst. {np.min(dmin):.8f} m")
    L.append("")

    L.append("MECANISMO — intervención por tipo de barrera, pareada (Δ medias). [lig] =")
    L.append("restricción ligante en el óptimo (se lee ésta); [hmin] = barrera de h mínimo")
    L.append("del Exp O (en Sk_din, con el h efectivo de la fila F1: sesgo por construcción).")
    L.append(f"  {'':29s} {'Δ total':>11s} {'Δ obst.':>11s} {'Δ pared':>11s} "
             f"{'Δ robot':>11s} {'indirecta':>10s} {'Δescapes':>9s} {'% junto obst':>12s} "
             f"{'Δ periferia':>27s}")
    for base, c_obst, c_pared, c_robot in BASES_MECANISMO:
        for k in niveles:
            for a, b in (("din", "ctrl"), ("din", "quieto"), ("sinvel", "din")):
                ca, cb = f"{k}_{a}", f"{k}_{b}"

                def dd(m: str) -> np.ndarray:
                    return columna(datos, ca, m, sem) - columna(datos, cb, m, sem)
                dt_, do, dp_, dr = (float(np.mean(dd(m))) for m in (
                    "cbf_frac_interv", c_obst, c_pared, c_robot))
                de = float(np.mean(dd("escape_n")))
                eo = float(np.mean(columna(datos, ca, "escape_n_junto_obst", sem)))
                mp, lop, hip = ic95_pareado(dd("frac_agente_paso_periferia_050"))
                junto = (f"{(100 * eo / de) if de > 0 else float('nan'):11.2f}%"
                         if b == "ctrl" else f"{'—':>11s} ")
                rot = f"[{base}] {ca} − {cb}"
                L.append(f"  {rot:29s} {dt_:+11.6f} {do:+11.6f} {dp_:+11.6f} "
                         f"{dr:+11.6f} {(dp_ / dt_) if dt_ != 0 else float('nan'):10.4f} "
                         f"{de:+9.3f} {junto} "
                         f"{mp:+.5f}[{lop:+.4f},{hip:+.4f}]{marca_sig(lop, hip)}")
    L.append("  indirecta = Δ pared / Δ total (inestable si Δ total ≈ 0). % junto obst (sólo")
    L.append("  contra el control) = escapes con obstáculo activo al disparar / Δ escapes.")
    L.append("  Δ periferia = cambio de la fracción de agente-paso a < 0,5 m de una pared.")
    L.append("PARTE DE ω EN c·u, filas del obstáculo ligantes con s > 0 (ponderada por fila)")
    for k in niveles:
        for t in ("din", "quieto", "sinvel"):
            c = f"{k}_{t}"
            n = columna(datos, c, "f1_parte_omega_n", sem)
            p = columna(datos, c, "f1_parte_omega_media", sem)
            tot_n = float(np.sum(n))
            L.append(f"  {c}: {(float(np.sum(p * n)) / tot_n) if tot_n else float('nan'):.6f} "
                     f"sobre {int(tot_n)} filas")

    # ── EVENTOS RAROS (24-10) ─────────────────────────────────────────────
    L.append("")
    L.append("EVENTOS RAROS — episodios con al menos un evento (k de n) e IC95 exacto de")
    L.append("Clopper-Pearson; contra el control, los eventos que exigen un obstáculo físico")
    L.append("son 'no aplica'")
    for k in niveles:
        for t in TIPOS:
            c = f"{k}_{t}"
            partes = []
            for nombre, m, fisico in EVENTOS:
                if t == "ctrl" and fisico:
                    partes.append(f"{nombre} no aplica")
                    continue
                n_ev = len(episodios_con(datos, c, m, sem))
                lo, hi = clopper_pearson(n_ev, len(sem))
                partes.append(f"{nombre} {n_ev}/{len(sem)} [{lo:.4f}, {hi:.4f}]")
            L.append(f"  {c}: " + "; ".join(partes))
    L.append("PRUEBA EXACTA PAREADA (McNemar exacta, bilateral, sobre episodios discordantes):")
    L.append("'b/c' = episodios con el evento sólo en el primero / sólo en el segundo")
    for k in niveles:
        for nombre, m, fisico in EVENTOS:
            partes = []
            for a, b in PARES_MCNEMAR:
                if b == "ctrl" and fisico:
                    partes.append(f"{a}−{b} no aplica")
                    continue
                sa, sb, p = mcnemar_exacta(episodios_con(datos, f"{k}_{a}", m, sem),
                                           episodios_con(datos, f"{k}_{b}", m, sem))
                partes.append(f"{a}−{b} {sa}/{sb} p {formato_p(p)}")
            L.append(f"  {k} {nombre}: " + "; ".join(partes))

    # ── FALLBACK Y DISTANCIA (24-10) ──────────────────────────────────────
    L.append("FALLBACK Y DISTANCIA — d_min centro→superficie del obstáculo y episodios bajo")
    L.append("0,10 m, separando los episodios con fallback del QP de los demás")
    for k in niveles:
        for t in ("din", "quieto", "sinvel"):
            c = f"{k}_{t}"
            con_fb = episodios_con(datos, c, "qp_fallbacks", sem)
            dmin = {s: datos[c][s]["d_min_obst_superficie"] for s in sem}

            def resumen(grupo: Sequence[int]) -> Tuple[str, int]:
                if not grupo:
                    return "—", 0
                return (f"{min(dmin[s] for s in grupo):.8f}",
                        sum(dmin[s] < UMBRAL_DISTANCIA_M for s in grupo))
            todos, b_todos = resumen(sem)
            con, b_con = resumen(sorted(con_fb))
            sin, b_sin = resumen([s for s in sem if s not in con_fb])
            L.append(f"  {c}: todos d_min {todos}, bajo 0,10 m {b_todos}/{len(sem)}; con fallback "
                     f"{len(con_fb)} episodios, d_min {con}, bajo 0,10 m {b_con}; sin fallback "
                     f"{len(sem) - len(con_fb)} episodios, d_min {sin}, bajo 0,10 m {b_sin}")
    texto = "\n".join(L) + "\n"
    RUTA_RES_EXPL.write_bytes(texto.encode("utf-8"))
    print(texto)

    # ── Figuras (las de S1, con el rótulo EXPLORATORIO adentro) ───────────
    DIR_FIG.mkdir(parents=True, exist_ok=True)
    fmt = FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",").replace("-", "−"))
    nombres = {"ctrl": "control", "quieto": "quieto", "din": "móvil", "sinvel": "sin\nvelocidad"}
    conds = [f"{k}_{t}" for k in niveles for t in TIPOS]
    etiquetas = [f"{c.split('_')[0]}\n{nombres[c.split('_', 1)[1]]}" for c in conds]
    fig, ax = plt.subplots(figsize=(max(6.8, 0.75 * len(conds) + 1.5), 4.2))
    x = np.arange(len(conds))
    ancho = 0.26
    for j, (m, color, nom) in enumerate((("cbf_frac_lig_pared", "#1f77b4", "pared ligante"),
                                         ("cbf_frac_lig_robot", "#ff7f0e", "robot ligante"),
                                         ("cbf_frac_lig_obst", "#2ca02c", "obstáculo ligante"))):
        v = np.array([np.mean(columna(datos, c, m, sem)) for c in conds])
        ax.bar(x + (j - 1) * ancho, v, width=ancho, color=color, label=nom)
    tot = np.array([np.mean(columna(datos, c, "cbf_frac_interv", sem)) for c in conds])
    ax.plot(x, tot, "k_", markersize=14, markeredgewidth=2, label="intervención total")
    ax.axhline(0.5, color="#d62728", linestyle="--", linewidth=1.0,
               label="umbral operativo 0,5")
    ax.set_xticks(x)
    ax.set_xticklabels(etiquetas, fontsize=8)
    ax.set_ylabel("Fracción de agente-decisión\n(por restricción ligante en el óptimo)",
                  fontsize=10)
    ax.yaxis.set_major_formatter(fmt)
    ax.grid(alpha=0.3, axis="y", linestyle="--", linewidth=0.5)
    # Leyenda FUERA del área de datos (24-10: tapaba la intervención total).
    ax.legend(fontsize=8, framealpha=0.9, loc="upper center",
              bbox_to_anchor=(0.5, -0.20), ncol=3)
    # Rótulo ARRIBA del área de datos (24-10): nada lo tapa.
    ax.text(0.0, 1.02, ROTULO_FIG, transform=ax.transAxes, ha="left", va="bottom",
            fontsize=8, color="#d62728")
    fig.tight_layout()
    fig.savefig(DIR_FIG / "fig_EXPLORATORIO_obstaculos_moviles_intervencion.png",
                dpi=DPI_FIG, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    for j, (a, b, m, color, nom) in enumerate(
            (("din", "ctrl", "cobertura_accesible", "#333333",
              "móvil − control (fuera de la máscara permanente)"),
             ("din", "quieto", "cob_acc_arranque", "#999999",
              "móvil − quieto (fuera de la máscara de arranque)"))):
        for i, k in enumerate(niveles):
            d = columna(datos, f"{k}_{a}", m, sem) - columna(datos, f"{k}_{b}", m, sem)
            mm, lo, hi = ic95_pareado(d)
            ax.errorbar([i + (j - 0.5) * 0.2], [mm], yerr=[[mm - lo], [hi - mm]],
                        fmt="o", color=color, capsize=3, label=nom if i == 0 else None)
    ax.axhline(0.0, color="grey", linewidth=0.8)
    ax.set_xticks(range(len(niveles)))
    ax.set_xticklabels(niveles)
    ax.set_xlim(-0.6, len(niveles) - 0.4)
    ax.set_xlabel("Nivel", fontsize=10)
    ax.set_ylabel("Δ cobertura AoI pareada, IC95\n(denominador de cada comparación)",
                  fontsize=10)
    ax.yaxis.set_major_formatter(fmt)
    ax.grid(alpha=0.3, axis="y", linestyle="--", linewidth=0.5)
    # Leyenda FUERA del área de datos (24-10: tapaba el rótulo EXPLORATORIO).
    ax.legend(fontsize=7, framealpha=0.9, loc="upper center",
              bbox_to_anchor=(0.5, -0.22), ncol=1)
    # Rótulo ARRIBA del área de datos (24-10): nada lo tapa.
    ax.text(0.0, 1.02, ROTULO_FIG, transform=ax.transAxes, ha="left", va="bottom",
            fontsize=8, color="#d62728")
    fig.tight_layout()
    fig.savefig(DIR_FIG / "fig_EXPLORATORIO_obstaculos_moviles_costo.png",
                dpi=DPI_FIG, bbox_inches="tight")
    plt.close(fig)
    print(f"Figuras → {DIR_FIG}")


if __name__ == "__main__":
    main()
