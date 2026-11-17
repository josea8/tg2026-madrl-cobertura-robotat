"""
analizar_experimento_Q.py
=========================
Análisis del Exp Q desde `resultados/experimento_Q_completo.csv`. Analiza los
niveles que hayan corrido (la regla de parada puede haber cortado antes).
Todo lo de acá quedó fijado en `tesis/PROPUESTA_expO_dinamico.md` (§3.6, §5)
antes de correr; los cambios de presentación posteriores salen de la
revisión adversarial del 19-10 y están declarados abajo.

Comparaciones, PAREADAS por semilla (mismas poses y objetivos iniciales):
  1. Sk_din − Sk_ctrl     costo del obstáculo móvil (como el Exp O).
  2. Sk_din − Sk_quieto   lo que agrega el movimiento.
  3. Sk_quieto − Sk_ctrl  descriptiva: el efecto estático en el arranque
                          (puente al Exp O, no comparable 1 a 1).
  4. Sk_sinvel − Sk_din   descriptiva (decisión 9): sin el término de
                          velocidad.
IC95 = media ± 1,96·EE con ddof = 1 (convención de los Exp C–O); "*" si el
intervalo excluye el 0. Sin corrección por multiplicidad (como el Exp O).

Coberturas (cada comparación con el mismo denominador en los dos lados):
  cobertura_accesible  fuera de la máscara permanente de la condición (en el
                       control, la del obstáculo móvil del nivel): comp. 1 y 4.
  cob_acc_arranque     fuera de la máscara del punto de arranque: comp. 2 y 3.
  cobertura_sin_enmascarar  cuadrícula completa, con las celdas enmascaradas
                       de cada condición como nunca cubiertas (en la comp. 2
                       incluye un término contable: el quieto enmascara todo el
                       arranque y el móvil sólo la máscara permanente).
Fuera de la tabla, por la revisión: `cob_acc_din` y `cobertura_protocolo`,
que en Sk_quieto cuentan como cubiertas las celdas que el campo fuerza a
AoI = 0.

Intervención por tipo de barrera. En Sk_din la fila del obstáculo que se
acerca entra al filtro con h_eq = h − s/α: la clasificación por "h mínimo"
(la del Exp O) se inclina hacia "obstáculo" POR CONSTRUCCIÓN. Por eso el
mecanismo se lee por restricción LIGANTE en el óptimo (sin ese sesgo), y el
"h mínimo" se muestra al lado, rotulado.

Salidas: resultados/resumen_experimento_Q.txt,
figuras/fig_obstaculos_moviles_intervencion.png,
figuras/fig_obstaculos_moviles_costo.png. Lo verifica, con código propio,
`verificar_cifras_Q.py`.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

_CARPETA: Path = Path(__file__).resolve().parent
RUTA_CSV: Path = _CARPETA / "resultados" / "experimento_Q_completo.csv"
RUTA_REG: Path = _CARPETA / "resultados" / "registro_Q.txt"
RUTA_RES: Path = _CARPETA / "resultados" / "resumen_experimento_Q.txt"
DIR_FIG: Path = _CARPETA / "figuras"
DPI_FIG: int = 300
NIVELES: Tuple[str, ...] = ("S1", "S2", "S3")
TIPOS: Tuple[str, ...] = ("ctrl", "quieto", "din", "sinvel")

#: (columna, etiqueta). Las coberturas van aparte: dependen de la comparación.
METRICAS_COBERTURA: Tuple[Tuple[str, str], ...] = (
    ("cobertura_accesible", "cobertura AoI (accesible propia)"),
    ("cob_acc_arranque", "cobertura AoI (fuera de máscara de arranque)"),
    ("cobertura_sin_enmascarar", "cobertura AoI (cuadrícula completa)"),
)
METRICAS_COMUNES: Tuple[Tuple[str, str], ...] = (
    ("colisiones_015", "pares en colisión <0,15 m"),
    ("colisiones_022", "pares en colisión <0,22 m"),
    ("contactos_obst_eventos", "contactos con obstáculo (agente-paso)"),
    ("contactos_obst_empuje", "  … por empuje del obstáculo"),
    ("contactos_obst_avance", "  … por avance del agente"),
    ("contactos_obst_agente_eps", "agente-eps con contacto con obstáculo"),
    ("viol_cota_obst_agente_eps", "agente-eps centro <0,13 m de obst."),
    ("frac_agente_paso_banda_018", "frac. agente-paso centro <0,18 m pared"),
    ("frac_agente_paso_periferia_050", "frac. agente-paso centro <0,5 m pared"),
    ("d_min_pared_centro", "d_min centro→pared [m]"),
    ("violaciones_margen", "agente-eps centro <0,18 m de pared"),
    ("contacto_pared", "agente-eps centro <0,075 m de pared"),
    ("cbf_frac_interv", "frac. intervención del filtro"),
    ("cbf_frac_lig_pared", "  … pared ligante en el óptimo"),
    ("cbf_frac_lig_robot", "  … robot ligante en el óptimo"),
    ("cbf_frac_lig_obst", "  … obstáculo ligante en el óptimo"),
    ("cbf_frac_lig_multitipo", "  … ≥2 tipos ligantes a la vez"),
    ("cbf_frac_lig_obst_vel", "  … obstáculo acercándose ligante"),
    ("cbf_frac_hmin_pared", "  … h mín. = pared (din: h efectivo)"),
    ("cbf_frac_hmin_robot", "  … h mín. = robot (din: h efectivo)"),
    ("cbf_frac_hmin_obst", "  … h mín. = obstáculo (din: h efectivo)"),
    ("cbf_magnitud_media", "magnitud media de la modificación"),
    ("qp_fallbacks", "fallbacks del QP por episodio"),
    ("f1_filas_saturadas", "filas F1 saturadas por episodio"),
    ("escape_n", "activaciones del escape por episodio"),
    ("escape_n_junto_obst", "  … con obstáculo activo al disparar"),
    ("escape_frac_ciclo", "frac. de ciclo en escape"),
    ("escape_infactibles", "escapes infactibles por episodio"),
    ("escape_infactibles_junto_obst", "  … con obstáculo activo"),
    ("escape_infact_opuestas", "  … por normales opuestas"),
    ("escape_infact_sin_activas", "  … sin barreras activas"),
    ("escape_infact_op_con_pared", "  … opuestas con pared activa"),
    ("escape_infact_op_con_robot", "  … opuestas con robot activo"),
    ("escape_infact_op_con_obst", "  … opuestas con obstáculo activo"),
    ("escape_agotados", "escapes agotados por episodio"),
    ("expo_frac_obst_activo", "frac. agente-decisión obst. activo (h<0,06)"),
    ("expo_frac_activo_acercandose", "  … y acercándose (s>0)"),
)
METRICAS_SOLO_TABLA: Tuple[Tuple[str, str], ...] = (
    ("d_min_obst_superficie", "d_min centro→superficie obst. [m]"),
    ("f1_parte_omega_n", "filas ligantes acercándose (n)"),
    ("agentes_reubicados", "agentes reubicados al inicio"),
    ("objetivos_reubicados", "objetivos reubicados al inicio"),
    ("rebotes_objetivo_obst", "rebotes de objetivos en obstáculos"),
    ("frac_mascara", "fracción de celdas, máscara de la métrica"),
    ("frac_mascara_arranque", "fracción de celdas en la máscara de arranque"),
)
#: (minuendo, sustraendo, coberturas de la comparación, título).
COMPARACIONES: Tuple[Tuple[str, str, Tuple[str, ...], str], ...] = (
    ("din", "ctrl", ("cobertura_accesible", "cobertura_sin_enmascarar"),
     "comparación 1: costo del obstáculo móvil"),
    ("din", "quieto", ("cob_acc_arranque", "cobertura_sin_enmascarar"),
     "comparación 2: lo que agrega el movimiento"),
    ("quieto", "ctrl", ("cob_acc_arranque", "cobertura_sin_enmascarar"),
     "comparación 3 (descriptiva): obstáculo quieto en el arranque"),
    ("sinvel", "din", ("cobertura_accesible", "cobertura_sin_enmascarar"),
     "comparación 4 (descriptiva): sin el término de velocidad"),
)
CRITERIOS: Tuple[Tuple[str, str], ...] = (
    ("contactos_obst_eventos", "contactos obst."),
    ("escape_agotados", "escapes agotados"),
    ("qp_fallbacks", "fallbacks QP"),
    ("escape_infactibles_junto_obst", "infactibles junto a obst."),
)
#: Bases del mecanismo: (rótulo, columna obstáculo, pared, robot).
BASES_MECANISMO: Tuple[Tuple[str, str, str, str], ...] = (
    ("lig", "cbf_frac_lig_obst", "cbf_frac_lig_pared", "cbf_frac_lig_robot"),
    ("hmin", "cbf_frac_hmin_obst", "cbf_frac_hmin_pared", "cbf_frac_hmin_robot"),
)


def cargar_q() -> Dict[str, Dict[int, Dict[str, float]]]:
    datos: Dict[str, Dict[int, Dict[str, float]]] = {}
    with open(RUTA_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            fila: Dict[str, float] = {}
            for k, v in r.items():
                try:
                    fila[k] = float(v)
                except ValueError:
                    pass
            datos.setdefault(r["condicion"], {})[int(r["seed_ep"])] = fila
    return datos


def columna(datos, c: str, m: str, sem: Sequence[int]) -> np.ndarray:
    return np.array([datos[c][s][m] for s in sem], dtype=np.float64)


def ic95_pareado(x: np.ndarray) -> Tuple[float, float, float]:
    m = float(np.mean(x))
    ee = float(np.std(x, ddof=1)) / math.sqrt(len(x)) if len(x) > 1 else 0.0
    return m, m - 1.96 * ee, m + 1.96 * ee


def marca_sig(lo: float, hi: float) -> str:
    return "*" if lo * hi > 0 else " "


def main() -> None:
    datos = cargar_q()
    niveles = [k for k in NIVELES if f"{k}_din" in datos]
    sem = sorted(datos[f"{niveles[0]}_din"].keys())
    L: List[str] = []
    L.append("EXPERIMENTO Q — Obstáculos MÓVILES como barreras de ejecución")
    L.append("ENCUADRE: mide la GENERALIDAD DE LA CAPA DE SEGURIDAD, no la")
    L.append("adaptabilidad de la política (la observación no codifica obstáculos).")
    L.append("Configuración final (modelo_sanidad, bloqueante, CBF + escape de tres")
    L.append("términos) con la fila F1 de la campaña (k = 1), arena 3,0, n=5,")
    L.append(f"{len(sem)} semillas {sem[0]}–{sem[-1]}. Obstáculos a 0,05 m/s; objetivos")
    L.append("transparentes; pareo por semilla (mismas poses y objetivos iniciales).")
    L.append("ESTADÍSTICA: Δ pareada por semilla; IC95 = media ± 1,96·EE (ddof = 1);")
    L.append("'*' si el IC excluye el 0; sin corrección por multiplicidad.")
    L.append("H MÍNIMO: en Sk_din la fila del obstáculo que se acerca entra al filtro")
    L.append("con h_eq = h − s/α; el mecanismo se lee por restricción LIGANTE.")
    L.append("=" * 78)
    L.append("")
    if RUTA_REG.exists():
        L += ["REGISTRO DE CORRIDA"] + ["  " + x for x in
                                       RUTA_REG.read_text(encoding="utf-8").splitlines()[1:]]
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
            if f"{k}_{a}" not in datos or f"{k}_{b}" not in datos:
                continue
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

    L.append("CRITERIO DE PARADA POR FALLA REAL (sumas sobre los episodios; decide Sk_din)")
    for k in niveles:
        for t in ("din", "quieto", "sinvel"):
            c = f"{k}_{t}"
            if c not in datos:
                continue
            L.append(f"  {c}{' (DECIDE)' if t == 'din' else ''}: " + "; ".join(
                f"{e} {int(columna(datos, c, m, sem).sum())}" for m, e in CRITERIOS))
    L.append("INDICADOR ADELANTADO (intervención > 0,5; se reporta, no detiene)")
    for k in niveles:
        for t in TIPOS:
            c = f"{k}_{t}"
            if c not in datos:
                continue
            f = columna(datos, c, "cbf_frac_interv", sem)
            L.append(f"  {c}: media {np.mean(f):.8f}; episodios > 0,5: "
                     f"{int(np.sum(f > 0.5))}/{len(sem)}; máx. {np.max(f):.8f}")
    L.append("")

    L.append("SEGURIDAD — totales sobre los episodios de cada condición con obstáculos")
    for k in niveles:
        for t in ("din", "quieto", "sinvel"):
            c = f"{k}_{t}"
            if c not in datos:
                continue
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
                if ca not in datos or cb not in datos:
                    continue
                def dd(m: str) -> np.ndarray:
                    return columna(datos, ca, m, sem) - columna(datos, cb, m, sem)
                dt_, do, dp_, dr = (float(np.mean(dd(m))) for m in (
                    "cbf_frac_interv", c_obst, c_pared, c_robot))
                de = float(np.mean(dd("escape_n")))
                eo = float(np.mean(columna(datos, ca, "escape_n_junto_obst", sem)))
                mp, lop, hip = ic95_pareado(dd("frac_agente_paso_periferia_050"))
                # % junto obst: la definición del Exp O, sólo contra el control.
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
            if c not in datos:
                continue
            n = columna(datos, c, "f1_parte_omega_n", sem)
            p = columna(datos, c, "f1_parte_omega_media", sem)
            tot_n = float(np.sum(n))
            L.append(f"  {c}: {(float(np.sum(p * n)) / tot_n) if tot_n else float('nan'):.6f} "
                     f"sobre {int(tot_n)} filas")
    texto = "\n".join(L) + "\n"
    RUTA_RES.write_bytes(texto.encode("utf-8"))
    print(texto)

    # ── Figuras ───────────────────────────────────────────────────────────
    DIR_FIG.mkdir(parents=True, exist_ok=True)
    fmt = FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",").replace("-", "−"))
    nombres = {"ctrl": "control", "quieto": "quieto", "din": "móvil", "sinvel": "sin\nvelocidad"}
    conds = [f"{k}_{t}" for k in niveles for t in TIPOS if f"{k}_{t}" in datos]
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
    ax.legend(fontsize=8, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(DIR_FIG / "fig_obstaculos_moviles_intervencion.png", dpi=DPI_FIG,
                bbox_inches="tight")
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
    ax.legend(fontsize=7, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(DIR_FIG / "fig_obstaculos_moviles_costo.png", dpi=DPI_FIG,
                bbox_inches="tight")
    plt.close(fig)
    print(f"Figuras → {DIR_FIG}")


if __name__ == "__main__":
    main()
