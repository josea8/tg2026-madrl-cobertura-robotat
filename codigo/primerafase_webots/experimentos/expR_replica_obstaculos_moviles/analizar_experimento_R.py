"""
analizar_experimento_R.py
=========================
Análisis PRERREGISTRADO del Exp R (§4 de `PREREGISTRO_R.md`). Se escribió y
se probó ANTES de correr; después de la corrida se ejecuta SIN CAMBIOS.

Modos (el script es el mismo en los tres):

    python -B analizar_experimento_R.py                    EL RESULTADO DE R
        resultados/experimento_R_completo.csv (12 celdas × 400) → resumen_R.txt,
        figuras/fig_R_*.png; agrega el DIAGNÓSTICO RETROSPECTIVO sobre las
        semillas vistas (control_bit_a_bit_R.csv), rotulado aparte.
    python -B analizar_experimento_R.py --prueba-sustituto
        experimento_Q_completo.csv + experimento_Q_EXPLORATORIO_S2_S3.csv (sin
        columnas de la Parte B) → resumen_R_prueba_sobre_Q.txt.
    python -B analizar_experimento_R.py --prueba-control
        control_bit_a_bit_R.csv (semillas vistas, con la Parte B y sus trazas)
        → resumen_R_prueba_sobre_control.txt: prueba del pipeline completo.

Los modos de prueba llevan en la primera línea y en las figuras "PRUEBA DEL
ANÁLISIS SOBRE DATOS VISTOS, NO ES EL RESULTADO DE R".

Estadística (la del Exp Q): eventos por episodio con IC95 de Clopper-Pearson;
McNemar exacta bilateral sobre los discordantes (b = sólo en A, c = sólo en
B); Δ pareadas por semilla con media ± 1,96·EE (ddof = 1); α = 0,05 sin
ajuste, y Holm sobre la familia cerrada de 7 como sensibilidad (no cambia la
palabra del veredicto). Las funciones estadísticas se importan del Exp Q
(`analizar_exploratorio_Q.py`, `analizar_experimento_Q.py`), no se copian.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import sys

if not sys.flags.dont_write_bytecode:
    raise SystemExit("PARAR: correr con python -B (importa módulos del Exp Q).")

import csv
import hashlib
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

_CARPETA: Path = Path(__file__).resolve().parent
_CARPETA_Q: Path = (_CARPETA.parent / "expQ_obstaculos_moviles").resolve()
if str(_CARPETA_Q) not in sys.path:
    sys.path.insert(0, str(_CARPETA_Q))

from analizar_experimento_Q import ic95_pareado, marca_sig
from analizar_exploratorio_Q import clopper_pearson, formato_p, mcnemar_exacta

DIR_RES: Path = _CARPETA / "resultados"
DIR_FIG: Path = _CARPETA / "figuras"
DIR_TRAZAS: Path = DIR_RES / "trazas"
RUTA_PREREG: Path = _CARPETA / "PREREGISTRO_R.md"
RUTA_CSV_R: Path = DIR_RES / "experimento_R_completo.csv"
RUTA_CONTROL_CSV: Path = DIR_RES / "control_bit_a_bit_R.csv"
RUTA_CSV_Q_S1: Path = _CARPETA_Q / "resultados" / "experimento_Q_completo.csv"
RUTA_CSV_EXPL_Q: Path = _CARPETA_Q / "resultados" / "experimento_Q_EXPLORATORIO_S2_S3.csv"
DPI_FIG: int = 300
NIVELES: Tuple[str, ...] = ("S1", "S2", "S3")
TIPOS: Tuple[str, ...] = ("din", "quieto", "ctrl", "sinvel")
ALFA: float = 0.05
#: Parte B: la ventana y el umbral del prerregistro (W = 1/(α·dt) = 5).
W_VENTANA: int = 5
UMBRAL_H6: float = 0.10
UMBRAL_COTA: float = 0.13
AVISO_PRUEBA: str = "PRUEBA DEL ANÁLISIS SOBRE DATOS VISTOS, NO ES EL RESULTADO DE R"

#: Eventos por episodio: (nombre, columna, umbral, "mayor" (> umbral) o
#: "menor" (< umbral), ¿exige obstáculo físico?). Contra el control, los que
#: exigen obstáculo físico son "no aplica" (el del control no es físico).
EVENTOS: Tuple[Tuple[str, str, float, str, bool], ...] = (
    ("fallback", "qp_fallbacks", 0.0, "mayor", False),
    ("agotado", "escape_agotados", 0.0, "mayor", False),
    ("contacto", "contactos_obst_eventos", 0.0, "mayor", True),
    ("bajo 0,13 m", "viol_cota_obst_agente_eps", 0.0, "mayor", True),
    ("bajo 0,10 m", "d_min_obst_superficie", UMBRAL_H6, "menor", True),
    ("infactible activo", "escape_infactibles_junto_obst", 0.0, "mayor", True),
)
EVENTO = {e[0]: e for e in EVENTOS}

#: Pruebas con p: (id, enunciado corto, evento, nivel, A, B, clase). La
#: predicción es SIEMPRE A > B (b > c). Las 7 forman la familia de Holm.
PRUEBAS: Tuple[Tuple[str, str, str, str, str, str, str], ...] = (
    ("H1-S3", "fallback, din > quieto", "fallback", "S3", "din", "quieto", "primaria"),
    ("H1-S2", "fallback, din > quieto", "fallback", "S2", "din", "quieto", "secundaria"),
    ("H2-S2", "bajo 0,13 m, sinvel > din", "bajo 0,13 m", "S2", "sinvel", "din", "primaria"),
    ("H2-S3", "bajo 0,13 m, sinvel > din", "bajo 0,13 m", "S3", "sinvel", "din", "primaria"),
    ("H3a", "agotado, din > ctrl", "agotado", "S3", "din", "ctrl", "primaria"),
    ("H3b", "agotado, din > quieto", "agotado", "S3", "din", "quieto", "secundaria"),
    ("H5b", "contacto, sinvel > din", "contacto", "S3", "sinvel", "din", "secundaria"),
)
ENUNCIADOS: Dict[str, str] = {
    "H1": "El encierro (fallback del QP) aparece con el movimiento",
    "H2": "El término de velocidad conserva margen",
    "H3a": "Los agotados de S3 son del obstáculo",
    "H3b": "El movimiento agrega agotados en S3",
    "H4": ("En S3 el efecto del obstáculo móvil (din − ctrl) sobre la cobertura accesible "
           "es menor, con signo, que en S1 y que en S2"),
    "H5a": "Cero contactos con F1 en los tres niveles",
    "H5b": "El término de velocidad reduce los contactos en S3",
    "H6a": "El acercamiento bajo 0,10 m ocurre en, o justo después de, un fallback del agente",
    "H6b": ("Fuera de la ventana de un fallback ningún agente baja de 0,10 m (R no afirma "
            "la cota de 0,13)"),
}
SEMILLAS_R: List[int] = list(range(420110, 420510))
COLUMNAS_PARTE_B: Tuple[str, ...] = ("d_min_fuera_ventana_5", "fallback_ventana_d_min_5",
                                     "d_min_sin_fallback", "d_min_fuera_ventana_3",
                                     "d_min_fuera_ventana_10")


# =============================================================================
# DATOS
# =============================================================================

Datos = Dict[str, Dict[int, Dict[str, float]]]


def cargar(rutas: Sequence[Path]) -> Tuple[Datos, Set[str]]:
    """datos[condición][semilla][columna] (floats) y el conjunto de columnas. Una
    fila repetida (misma condición y semilla) es un error, no se pisa."""
    datos: Datos = {}
    columnas: Set[str] = set()
    for ruta in rutas:
        with open(ruta, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                fila: Dict[str, float] = {}
                for k, v in r.items():
                    try:
                        fila[k] = float(v)
                    except (TypeError, ValueError):
                        pass
                columnas |= set(fila)
                celda = datos.setdefault(r["condicion"], {})
                if int(r["seed_ep"]) in celda:
                    raise SystemExit(f"PARAR: fila repetida {r['condicion']}/{r['seed_ep']} "
                                     f"en {ruta.name}.")
                celda[int(r["seed_ep"])] = fila
    return datos, columnas


def semillas_comunes(datos: Datos) -> List[int]:
    """Las semillas, que tienen que ser las mismas en las 12 celdas."""
    conjuntos = {c: frozenset(datos[c]) for c in (f"{k}_{t}" for k in NIVELES for t in TIPOS)}
    if len(set(conjuntos.values())) != 1:
        raise SystemExit("PARAR: las 12 celdas no tienen las mismas semillas.")
    return sorted(next(iter(conjuntos.values())))


def tiene(datos: Datos, celda: str, evento: str, s: int) -> bool:
    _n, col, umbral, modo, _f = EVENTO[evento]
    v = datos[celda][s][col]
    return v > umbral if modo == "mayor" else v < umbral


def con_evento(datos: Datos, celda: str, evento: str, sem: Sequence[int]) -> Set[int]:
    return {s for s in sem if tiene(datos, celda, evento, s)}


def columna(datos: Datos, celda: str, m: str, sem: Sequence[int]) -> np.ndarray:
    return np.array([datos[celda][s][m] for s in sem], dtype=np.float64)


def kn(k: int, n: int) -> str:
    lo, hi = clopper_pearson(k, n)
    return f"{k}/{n} [{lo:.4f}, {hi:.4f}]"


def delta(m: float, lo: float, hi: float) -> str:
    return f"{m:+.8f} [{lo:+.8f}, {hi:+.8f}]{marca_sig(lo, hi)}"


def delta_sin_marca(m: float, lo: float, hi: float) -> str:
    """Una Δ descriptiva, sin la estrella de significación (H3b: el veredicto es
    sólo el de la McNemar)."""
    return f"{m:+.8f} [{lo:+.8f}, {hi:+.8f}]"


# =============================================================================
# REGLAS DE LECTURA (fijadas en el prerregistro)
# =============================================================================

def veredicto_p(b: int, c: int, p: float) -> str:
    """'sostenida' sólo con p < 0,05 Y b > c (la dirección predicha, A > B)."""
    if b + c == 0:
        return "no sostenida (sin discordantes)"
    if p < ALFA and b > c:
        return "sostenida"
    if p < ALFA and c > b:
        return "no sostenida (dirección contraria)"
    return "no sostenida"


def holm(ps: Sequence[float]) -> List[float]:
    """p ajustadas de Holm (paso a paso hacia abajo), en el orden de entrada."""
    m = len(ps)
    orden = sorted(range(m), key=lambda i: ps[i])
    ajust = [0.0] * m
    previo = 0.0
    for j, i in enumerate(orden):
        previo = max(previo, min(1.0, (m - j) * ps[i]))
        ajust[i] = previo
    return ajust


def prueba(datos: Datos, sem: Sequence[int], evento: str, k: str, a: str, b: str
           ) -> Tuple[int, int, int, int, float]:
    """(k_A, k_B, b, c, p) de la McNemar exacta, A = Sk_a, B = Sk_b."""
    ea = con_evento(datos, f"{k}_{a}", evento, sem)
    eb = con_evento(datos, f"{k}_{b}", evento, sem)
    solo_a, solo_b, p = mcnemar_exacta(ea, eb)
    return len(ea), len(eb), solo_a, solo_b, p


def h6_nivel(datos: Datos, celda: str, sem: Sequence[int], col_fuera: str,
             umbral: float) -> Tuple[int, int, int]:
    """(m bajo el umbral, k con el mínimo en la ventana, episodios fuera de la ventana)."""
    bajo = [s for s in sem if datos[celda][s]["d_min_obst_superficie"] < umbral]
    en_v = sum(int(datos[celda][s]["fallback_ventana_d_min_5"]) for s in bajo)
    fuera = sum(datos[celda][s][col_fuera] < umbral for s in sem)
    return len(bajo), en_v, fuera


def veredicto_h6a(m: int, k: int) -> str:
    if m == 0:
        return "no evaluable en el nivel"
    return "cumplida" if k == m else "no cumplida"


# =============================================================================
# TRAZAS
# =============================================================================

def leer_traza(ruta: Path) -> Dict[str, np.ndarray]:
    with open(ruta, encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    return {c: np.array([float(r[c]) for r in filas]) for c in filas[0]}


def contactos_en_ventana(ruta: Path) -> List[Tuple[int, int, bool]]:
    """(paso, agente, ¿en la ventana de un fallback del agente?) de cada contacto nuevo."""
    tr = leer_traza(ruta)
    pasos, agentes = tr["paso"].astype(int), tr["agente"].astype(int)
    fb = {(t, a): int(f) for t, a, f in zip(pasos, agentes, tr["fallback"])}
    salida = []
    for t, a, nuevo in zip(pasos, agentes, tr["contacto_nuevo"]):
        if nuevo > 0:
            en_v = any(fb.get((s, a), 0) for s in range(max(0, t - W_VENTANA + 1), t + 1))
            salida.append((int(t), int(a), en_v))
    return salida


# =============================================================================
# RESUMEN
# =============================================================================

def seccion_hipotesis(datos: Datos, sem: Sequence[int], parte_b: Optional[str],
                      prefijo: str, con_trazas: bool, dir_trazas: Path = DIR_TRAZAS,
                      estricto: bool = False
                      ) -> Tuple[List[str], Dict[str, str], Dict[str, tuple]]:
    """
    Las líneas de RESULTADOS POR HIPÓTESIS y el veredicto de cada pieza. H1, H2
    y H6 se leen POR NIVEL, sin veredicto conjunto. `parte_b` es None si la
    Parte B es evaluable, o el motivo por el que no lo es. Con `estricto`
    (modo resultado), una traza que falta detiene el análisis.
    """
    n = len(sem)
    L: List[str] = ["RESULTADOS POR HIPÓTESIS (α = 0,05 bilateral, sin ajuste; reglas de "
                    "lectura del prerregistro: con p, 'sostenida' sólo si p < 0,05 y b > c; "
                    "H1, H2 y H6 se leen por nivel, sin veredicto conjunto)"]
    V: Dict[str, str] = {}
    res = {}
    for pid, corto, ev, k, a, b, clase in PRUEBAS:
        res[pid] = prueba(datos, sem, ev, k, a, b)

    def linea(pid: str) -> str:
        _pid, corto, ev, k, a, b, clase = next(x for x in PRUEBAS if x[0] == pid)
        ka, kb, bb, cc, p = res[pid]
        V[pid] = veredicto_p(bb, cc, p)
        return (f"    {k} ({clase}): A = {k}_{a} {kn(ka, n)}; B = {k}_{b} {kn(kb, n)}; "
                f"b/c = {bb}/{cc}; p = {formato_p(p)} → {V[pid]}")

    L.append(f"  H1  {ENUNCIADOS['H1']}: episodios con fallback, A = Sk_din, B = Sk_quieto; "
             f"McNemar; predicción A > B")
    L += [linea("H1-S3"), linea("H1-S2")]
    ka, kb, bb, cc, p = prueba(datos, sem, "fallback", "S1", "din", "quieto")
    L.append(f"    S1 (descriptiva, sin veredicto): A = S1_din {kn(ka, n)}; B = S1_quieto "
             f"{kn(kb, n)}; b/c = {bb}/{cc}; p = {formato_p(p)}")
    L.append("    necesidad (descriptiva, sin veredicto): con obstáculos quietos, fallback en " + "; ".join(
        f"{k} {kn(len(con_evento(datos, f'{k}_quieto', 'fallback', sem)), n)}" for k in NIVELES))
    L.append(f"  H2  {ENUNCIADOS['H2']}: episodios bajo 0,13 m, A = Sk_sinvel, B = Sk_din; "
             f"McNemar; predicción A > B")
    L += [linea("H2-S2"), linea("H2-S3")]
    ka, kb, bb, cc, p = prueba(datos, sem, "bajo 0,13 m", "S1", "sinvel", "din")
    L.append(f"    S1 (descriptiva, sin veredicto): A = S1_sinvel {kn(ka, n)}; B = S1_din "
             f"{kn(kb, n)}; b/c = {bb}/{cc}; p = {formato_p(p)}")
    L.append(f"  H3a {ENUNCIADOS['H3a']}: episodios con agotado, A = S3_din, B = S3_ctrl; "
             f"McNemar; predicción A > B")
    L.append(linea("H3a"))
    L.append(f"  H3b {ENUNCIADOS['H3b']}: episodios con agotado, A = S3_din, B = S3_quieto; "
             f"McNemar; predicción A > B")
    L.append(linea("H3b"))
    d = (columna(datos, "S3_din", "escape_agotados", sem) > 0).astype(float) - (
        columna(datos, "S3_quieto", "escape_agotados", sem) > 0).astype(float)
    L.append(f"    Δ de tasas pareada (din − quieto), media ± 1,96·EE (ddof = 1), descriptiva "
             f"(el veredicto es sólo el de la McNemar): {delta_sin_marca(*ic95_pareado(d))}")
    # H4
    dk = {k: columna(datos, f"{k}_din", "cobertura_accesible", sem)
          - columna(datos, f"{k}_ctrl", "cobertura_accesible", sem) for k in NIVELES}
    L.append(f"  H4  {ENUNCIADOS['H4']} (secundaria, compuesta): Δ_k = cobertura_accesible "
             f"din − ctrl, pareada por semilla; piezas Δ_S1 − Δ_S3 > 0 y Δ_S2 − Δ_S3 > 0 (IC95 "
             f"con lo > 0); 'sostenida' sólo si se cumplen las dos")
    piezas = []
    for k1 in ("S1", "S2"):
        m, lo, hi = ic95_pareado(dk[k1] - dk["S3"])
        piezas.append(lo > 0)
        L.append(f"    Δ_{k1} − Δ_S3: {delta(m, lo, hi)} → {'cumple' if lo > 0 else 'no cumple'}")
    V["H4"] = "sostenida" if all(piezas) else "no sostenida"
    L.append("    Δ_k (descriptivas): " + "; ".join(
        f"{k} {delta(*ic95_pareado(dk[k]))}" for k in NIVELES))
    L.append(f"    → {V['H4']}")
    # H5a
    cont = {k: len(con_evento(datos, f"{k}_din", "contacto", sem)) for k in NIVELES}
    V["H5a"] = "cumplida" if not any(cont.values()) else "no cumplida"
    L.append(f"  H5a {ENUNCIADOS['H5a']} (primaria): episodios con contacto en Sk_din, Clopper-Pearson "
             f"→ " + "; ".join(f"{k} {kn(cont[k], n)}" for k in NIVELES) + f" → {V['H5a']}")
    if any(cont.values()):
        L.append("    lectura (§2.4): k ≥ 1 se reporta como tasa k/400 con su IC95 y se discute con "
                 "la traza de cada episodio (si el contacto cayó en la ventana de un fallback del "
                 "agente o no); no se lee como 'el filtro falla'")
        for k in NIVELES:
            for s in sorted(con_evento(datos, f"{k}_din", "contacto", sem)):
                ruta = dir_trazas / f"{prefijo}_{k}_din_{s}.csv"
                if parte_b is not None:
                    L.append(f"    {k}_din {s}: ubicación del contacto {parte_b}")
                elif con_trazas and ruta.exists():
                    cs = contactos_en_ventana(ruta)
                    L.append(f"    {k}_din {s}: {len(cs)} contactos nuevos, "
                             f"{sum(v for *_x, v in cs)} en la ventana de un fallback del agente")
                elif estricto:
                    raise SystemExit(f"PARAR: falta la traza {ruta.name}.")
                else:
                    L.append(f"    {k}_din {s}: sin traza para ubicar el contacto")
    L.append(f"  H5b {ENUNCIADOS['H5b']}: episodios con contacto, A = S3_sinvel, B = S3_din; "
             f"McNemar; predicción A > B (potencia acoplada a H5a: cada contacto en din sube c)")
    L.append(linea("H5b"))
    # H6
    L.append(f"  H6  Parte B (secundarias, descriptivas), ventana de W = {W_VENTANA} decisiones "
             f"(t−{W_VENTANA - 1} … t) del mismo agente, W = 1/(α·dt); umbral 0,10 m; en Sk_din")
    if parte_b is not None:
        for k in NIVELES:
            V[f"H6a-{k}"] = V[f"H6b-{k}"] = parte_b
        L.append(f"    {parte_b}")
    else:
        for k in NIVELES:
            m, en_v, fuera = h6_nivel(datos, f"{k}_din", sem, "d_min_fuera_ventana_5", UMBRAL_H6)
            V[f"H6a-{k}"] = veredicto_h6a(m, en_v)
            V[f"H6b-{k}"] = "cumplida" if fuera == 0 else "no cumplida"
            ic = f" {kn(en_v, m)}" if m else ""
            L.append(f"    {k}: H6a ({ENUNCIADOS['H6a']}) {en_v} de {m} episodios bajo "
                     f"0,10 m con el mínimo en la ventana{ic} → {V[f'H6a-{k}']}; "
                     f"H6b ({ENUNCIADOS['H6b']}) {kn(fuera, n)} episodios bajo 0,10 m "
                     f"fuera de la ventana → {V[f'H6b-{k}']}")
        L.append("    sensibilidad declarada (rotulada, sin veredicto), del tipo H6b: episodios de "
                 "Sk_din bajo el umbral fuera de la ventana; en 0,13 se espera ≥ ~23 % en S3 por los "
                 "episodios sin fallback (23/100 vistos)")
        for k in NIVELES:
            partes = []
            for nom, col, u in (("W=1", "d_min_sin_fallback", UMBRAL_H6),
                                ("W=3", "d_min_fuera_ventana_3", UMBRAL_H6),
                                ("W=10", "d_min_fuera_ventana_10", UMBRAL_H6),
                                ("W=5 umbral 0,13", "d_min_fuera_ventana_5", UMBRAL_COTA)):
                fuera = sum(datos[f"{k}_din"][s][col] < u for s in sem)
                partes.append(f"{nom} {fuera}/{n}")
            L.append(f"    {k}: " + "; ".join(partes))
    return L, V, res


def seccion_holm(res: Dict[str, Tuple[int, int, int, int, float]], V: Dict[str, str]
                 ) -> List[str]:
    ids = [x[0] for x in PRUEBAS]
    aj = holm([res[i][4] for i in ids])
    L = [f"SENSIBILIDAD — p ajustada por Holm sobre la familia cerrada de {len(ids)} "
         f"(no cambia la palabra del veredicto)"]
    for i, a in zip(ids, aj):
        bb, cc = res[i][2], res[i][3]
        L.append(f"  {i}: p = {formato_p(res[i][4])}; p Holm = {formato_p(a)} → "
                 f"{'p Holm < 0,05 en la dirección predicha' if a < ALFA and bb > cc else 'p Holm ≥ 0,05 o dirección contraria'}"
                 f" (veredicto: {V[i]})")
    return L


def seccion_eventos(datos: Datos, sem: Sequence[int]) -> List[str]:
    n = len(sem)
    L = ["EVENTOS RAROS — episodios con al menos un evento (k de n) e IC95 de "
         "Clopper-Pearson; en el control, los que exigen obstáculo físico 'no aplica'"]
    for k in NIVELES:
        for t in TIPOS:
            c = f"{k}_{t}"
            partes = [f"{nom} no aplica" if (t == "ctrl" and fis) else
                      f"{nom} {kn(len(con_evento(datos, c, nom, sem)), n)}"
                      for nom, _c, _u, _m, fis in EVENTOS]
            L.append(f"  {c}: " + "; ".join(partes))
    L.append("INFACTIBLE CON OBSTÁCULO ACTIVO, din − quieto (McNemar, descriptiva, sin "
             "predicción, fuera de Holm):")
    for k in NIVELES:
        ka, kb, bb, cc, p = prueba(datos, sem, "infactible activo", k, "din", "quieto")
        L.append(f"  {k}: din {ka}, quieto {kb}; b/c = {bb}/{cc}; p = {formato_p(p)}")
    L.append("AGOTADOS de S1 y S2 (descriptivo): " + "; ".join(
        f"{k}_{t} {len(con_evento(datos, f'{k}_{t}', 'agotado', sem))}"
        for k in ("S1", "S2") for t in TIPOS))
    return L


def seccion_costo(datos: Datos, sem: Sequence[int]) -> List[str]:
    L = ["COSTO EN TAREA — Δ pareadas por semilla, IC95 (denominadores del §3.6 de la "
         "propuesta: din − ctrl sobre cobertura_accesible; din − quieto sobre cob_acc_arranque)"]
    for k in NIVELES:
        d1 = (columna(datos, f"{k}_din", "cobertura_accesible", sem)
              - columna(datos, f"{k}_ctrl", "cobertura_accesible", sem))
        d2 = (columna(datos, f"{k}_din", "cob_acc_arranque", sem)
              - columna(datos, f"{k}_quieto", "cob_acc_arranque", sem))
        di = (columna(datos, f"{k}_din", "cbf_frac_interv", sem)
              - columna(datos, f"{k}_ctrl", "cbf_frac_interv", sem))
        L.append(f"  {k}: din − ctrl {delta(*ic95_pareado(d1))}; din − quieto "
                 f"{delta(*ic95_pareado(d2))}; intervención din − ctrl {delta(*ic95_pareado(di))}")
    return L


def seccion_intervencion(datos: Datos, sem: Sequence[int]) -> List[str]:
    L = ["INTERVENCIÓN — fracción de agente-decisión (media por celda) y filas F1 saturadas "
         "(suma)"]
    for k in NIVELES:
        for t in TIPOS:
            c = f"{k}_{t}"
            m = {x: float(np.mean(columna(datos, c, x, sem)))
                 for x in ("cbf_frac_interv", "cbf_frac_lig_pared", "cbf_frac_lig_robot",
                           "cbf_frac_lig_obst")}
            sat = int(np.sum(columna(datos, c, "f1_filas_saturadas", sem)))
            L.append(f"  {c}: total {m['cbf_frac_interv']:.8f}; ligante pared "
                     f"{m['cbf_frac_lig_pared']:.8f}, robot {m['cbf_frac_lig_robot']:.8f}, "
                     f"obstáculo {m['cbf_frac_lig_obst']:.8f}; filas F1 saturadas {sat}")
    return L


#: Las verificaciones al empezar y al terminar (`previos_R` y `finales_R` de
#: correr_experimento_R.py) y las firmas, comunes a los registros de las tres
#: corridas: el §4 del prerregistro las pide todas en VERIFICACIÓN (adenda del
#: 09-11: faltaban las copias del Exp O, «AL TERMINAR» y, en la pasabilidad,
#: casi todo el bloque).
VERIFICACION_INICIO_FIN: Tuple[str, ...] = (
    "inicio", "huella", "HUELLA_", "ENTORNO_R", "procesos", "PREREGISTRO_R.md", "COPIAS",
    "IGUAL", "STACK", "RESULTADOS DEL EXP Q", "ÁRBOL", "energía", "sin reinicio",
    "congelados", "AL TERMINAR", "copias del Exp O", "manifiesto", "fin")

#: Las líneas de cada registro que pasan a VERIFICACIÓN (por su comienzo).
PREFIJOS_VERIFICACION: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("comparar_ast_R.txt", ("COMPROBACIÓN", "NOMBRES LIBRES", "HUELLA_R")),
    ("control_bit_a_bit_R.txt", VERIFICACION_INICIO_FIN + (
        "CONTROL", "de los 1200", "AUTOCHEQUEOS", "la prueba física", "TRAZAS", "PARTE B")),
    ("pasabilidad_R.txt", VERIFICACION_INICIO_FIN + (
        "S1:", "S2:", "S3:", "PASABILIDAD:", "SEMILLAS_R")),
    ("registro_R.txt", VERIFICACION_INICIO_FIN + (
        "PRERREGISTRADO", "semillas", "modo", "AUTOCHEQUEOS", "la prueba física", "TRAZAS",
        "FILAS", "PARTE B", "logs de los tramos")),
)


def seccion_verificacion(modo: str, dir_res: Path = DIR_RES) -> List[str]:
    if modo != "resultado":
        return ["VERIFICACIÓN — no aplica (prueba del análisis sobre datos vistos)"]
    L = ["VERIFICACIÓN (de los registros de la corrida)"]
    for nombre, prefijos in PREFIJOS_VERIFICACION:
        ruta = dir_res / nombre
        if not ruta.exists():
            L.append(f"  falta {nombre}")
            continue
        L += [f"  {nombre}: {x.strip()}" for x in ruta.read_text(encoding="utf-8").splitlines()
              if x.strip().startswith(prefijos)]
    return L


def estado_parte_b(rutas: Sequence[Path]) -> Optional[str]:
    """None si la Parte B es evaluable según los registros; si no, el motivo."""
    for ruta in rutas:
        if ruta.exists() and "PARTE B: NO" in ruta.read_text(encoding="utf-8"):
            return f"no evaluable: {ruta.name} dice PARTE B: NO (§7 del prerregistro)"
    return None


def no_sustenta_del_prerregistro() -> List[str]:
    """Los puntos del §6 del prerregistro, palabra por palabra."""
    if not RUTA_PREREG.exists():
        return ["(falta PREREGISTRO_R.md)"]
    puntos, dentro = [], False
    for linea in RUTA_PREREG.read_text(encoding="utf-8").splitlines():
        if linea.startswith("## "):
            dentro = linea.startswith("## 6.")
            continue
        if dentro and linea.startswith("- "):
            puntos.append(linea[2:])
    return puntos or ["(el §6 del prerregistro no tiene puntos)"]


def seccion_prerregistro(sem: Sequence[int]) -> List[str]:
    if not RUTA_PREREG.exists():
        return ["PRERREGISTRO — falta PREREGISTRO_R.md"]
    texto = RUTA_PREREG.read_bytes()
    fijado = next((x for x in texto.decode("utf-8").splitlines() if x.startswith("Fijado: ")),
                  "Fijado: (sin línea de fijación)")
    return ["PRERREGISTRO",
            f"  PREREGISTRO_R.md sha256 {hashlib.sha256(texto).hexdigest()}; {fijado}",
            f"  semillas {sem[0]}–{sem[-1]}, n = {len(sem)} por celda, 12 celdas"]




def resumen(datos: Datos, columnas: Set[str], modo: str, prefijo: str,
            datos_vistos: Optional[Datos] = None, dir_trazas: Path = DIR_TRAZAS,
            motivo_parte_b: Optional[str] = None) -> Tuple[List[str], Dict[str, str]]:
    sem = semillas_comunes(datos)
    if modo == "resultado" and sem != SEMILLAS_R:
        raise SystemExit("PARAR: las semillas no son 420110–420509 (n = 400).")
    parte_b = (motivo_parte_b if motivo_parte_b is not None else
               None if all(c in columnas for c in COLUMNAS_PARTE_B) else
               "no evaluable: faltan las columnas de la Parte B")
    con_trazas = modo != "prueba-sustituto"
    L: List[str] = []
    if modo == "resultado":
        L.append("EXPERIMENTO R — réplica prerregistrada de los obstáculos móviles (S1–S3, "
                 "semillas nuevas) — RESULTADO")
    else:
        L.append(AVISO_PRUEBA)
        L.append(f"  (modo {modo}: {'experimento_Q_completo.csv + experimento_Q_EXPLORATORIO_S2_S3.csv' if modo == 'prueba-sustituto' else 'control_bit_a_bit_R.csv'})")
    L += ["ENCUADRE: no prueba adaptabilidad de la política (la observación no codifica "
          "obstáculos); prueba la generalidad de la capa de seguridad y su costo, con "
          "semillas de episodio que no generaron las hipótesis.", ""]
    L += seccion_prerregistro(sem) + [""] + seccion_verificacion(modo) + [""]
    lh, V, res = seccion_hipotesis(datos, sem, parte_b, prefijo, con_trazas, dir_trazas,
                                   estricto=modo == "resultado")
    L += lh + [""] + seccion_holm(res, V) + [""]
    L += seccion_eventos(datos, sem) + [""] + seccion_costo(datos, sem) + [""]
    L += seccion_intervencion(datos, sem)
    if datos_vistos is not None:
        sv = semillas_comunes(datos_vistos)
        L += ["", "DIAGNÓSTICO RETROSPECTIVO SOBRE SEMILLAS VISTAS (420000–420099; control "
              "bit a bit de R; descriptivo, NO cuenta como prueba de H6)"]
        for k in NIVELES:
            for t in ("din", "sinvel"):
                c = f"{k}_{t}"
                m, en_v, fuera = h6_nivel(datos_vistos, c, sv, "d_min_fuera_ventana_5",
                                          UMBRAL_H6)
                fb = len(con_evento(datos_vistos, c, "fallback", sv))
                L.append(f"  {c}: {fb} episodios con fallback; {m} bajo 0,10 m, "
                         f"{en_v} con el mínimo en la ventana; {fuera} bajo 0,10 m "
                         f"fuera de la ventana")
    L += ["", "LO QUE R NO SUSTENTA (el §6 del prerregistro, escrito antes de correr):"]
    L += [f"  - {x}" for x in no_sustenta_del_prerregistro()]
    return L, V


# =============================================================================
# FIGURAS
# =============================================================================

def figuras(datos: Datos, modo: str, prefijo: str, parte_b: bool, sufijo: str,
            dir_trazas: Path = DIR_TRAZAS, dir_fig: Path = DIR_FIG) -> List[str]:
    sem = semillas_comunes(datos)
    rotulo = ("Exp R — réplica prerregistrada (semillas 420110–420509)" if modo == "resultado"
              else AVISO_PRUEBA)
    dir_fig.mkdir(parents=True, exist_ok=True)
    fmt = FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",").replace("-", "−"))
    hechas = []

    # Costo
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    for j, (a, b, m, color, nom) in enumerate(
            (("din", "ctrl", "cobertura_accesible", "#333333",
              "móvil − control (fuera de la máscara permanente)"),
             ("din", "quieto", "cob_acc_arranque", "#999999",
              "móvil − quieto (fuera de la máscara de arranque)"))):
        for i, k in enumerate(NIVELES):
            d = columna(datos, f"{k}_{a}", m, sem) - columna(datos, f"{k}_{b}", m, sem)
            mm, lo, hi = ic95_pareado(d)
            ax.errorbar([i + (j - 0.5) * 0.2], [mm], yerr=[[mm - lo], [hi - mm]], fmt="o",
                        color=color, capsize=3, label=nom if i == 0 else None)
    ax.axhline(0.0, color="grey", linewidth=0.8)
    ax.set_xticks(range(len(NIVELES)))
    ax.set_xticklabels(NIVELES)
    ax.set_xlim(-0.6, len(NIVELES) - 0.4)
    ax.set_xlabel("Nivel", fontsize=10)
    ax.set_ylabel("Δ cobertura AoI pareada, IC95\n(denominador de cada comparación)",
                  fontsize=10)
    ax.yaxis.set_major_formatter(fmt)
    ax.grid(alpha=0.3, axis="y", linestyle="--", linewidth=0.5)
    ax.legend(fontsize=7, framealpha=0.9, loc="upper center", bbox_to_anchor=(0.5, -0.22),
              ncol=1)
    ax.text(0.0, 1.02, rotulo, transform=ax.transAxes, ha="left", va="bottom", fontsize=7,
            color="#d62728")
    fig.tight_layout()
    ruta = dir_fig / f"fig_R_costo{sufijo}.png"
    fig.savefig(ruta, dpi=DPI_FIG, bbox_inches="tight")
    plt.close(fig)
    hechas.append(ruta.name)

    # Intervención
    nombres = {"ctrl": "control", "quieto": "quieto", "din": "móvil", "sinvel": "sin\nvelocidad"}
    conds = [f"{k}_{t}" for k in NIVELES for t in TIPOS]
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
    ax.axhline(0.5, color="#d62728", linestyle="--", linewidth=1.0, label="umbral operativo 0,5")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{c.split('_')[0]}\n{nombres[c.split('_', 1)[1]]}" for c in conds],
                       fontsize=8)
    ax.set_ylabel("Fracción de agente-decisión\n(por restricción ligante en el óptimo)",
                  fontsize=10)
    ax.yaxis.set_major_formatter(fmt)
    ax.grid(alpha=0.3, axis="y", linestyle="--", linewidth=0.5)
    ax.legend(fontsize=8, framealpha=0.9, loc="upper center", bbox_to_anchor=(0.5, -0.20),
              ncol=3)
    ax.text(0.0, 1.02, rotulo, transform=ax.transAxes, ha="left", va="bottom", fontsize=8,
            color="#d62728")
    fig.tight_layout()
    ruta = dir_fig / f"fig_R_intervencion{sufijo}.png"
    fig.savefig(ruta, dpi=DPI_FIG, bbox_inches="tight")
    plt.close(fig)
    hechas.append(ruta.name)

    # Fallback y distancia, en el tiempo (sólo con la Parte B y sus trazas)
    if parte_b and modo != "prueba-sustituto":
        casos = sorted(((k, s) for k in NIVELES for s in sem
                        if datos[f"{k}_din"][s]["d_min_obst_superficie"] < UMBRAL_H6),
                       key=lambda ks: datos[f"{ks[0]}_din"][ks[1]]["d_min_obst_superficie"])
        if casos:
            cols = min(4, len(casos))
            filas = -(-len(casos) // cols)
            fig, ejes = plt.subplots(filas, cols, figsize=(3.0 * cols, 2.3 * filas + 0.6),
                                     squeeze=False, sharey=True)
            for ax, (k, s) in zip(ejes.flat, casos):
                f = datos[f"{k}_din"][s]
                a = int(f["agente_d_min"])
                tr = leer_traza(dir_trazas / f"{prefijo}_{k}_din_{s}.csv")
                sel = tr["agente"] == a
                paso, dist, fb = tr["paso"][sel], tr["d_obst"][sel], tr["fallback"][sel] > 0
                ax.plot(paso, dist, color="#333333", linewidth=0.8, label="distancia del agente")
                ax.scatter(paso[fb], dist[fb], s=6, color="#d62728", zorder=3,
                           label="decisión en fallback")
                ax.axhline(UMBRAL_H6, color="#1f77b4", linestyle="--", linewidth=0.8,
                           label="0,10 m")
                ax.axhline(0.075, color="grey", linestyle=":", linewidth=0.8,
                           label="contacto (0,075 m)")
                ax.set_title(f"{k}_din {s}, agente {a}", fontsize=7)
                ax.set_xlabel("paso", fontsize=6)
                ax.set_ylabel("distancia al obstáculo [m]", fontsize=6)
                ax.tick_params(labelsize=6)
                ax.set_ylim(0.0, 0.6)
            for ax in list(ejes.flat)[len(casos):]:
                ax.axis("off")
            mano, etiq = ejes.flat[0].get_legend_handles_labels()
            fig.legend(mano, etiq, loc="lower center", ncol=4, fontsize=7,
                       bbox_to_anchor=(0.5, -0.02))
            fig.text(0.01, 1.0, f"{rotulo} — episodios din bajo 0,10 m ({len(casos)}): "
                     f"distancia del agente que alcanza el mínimo contra el paso",
                     ha="left", va="bottom", fontsize=7, color="#d62728")
            fig.tight_layout(rect=(0, 0.06, 1, 1))
            ruta = dir_fig / f"fig_R_fallback_distancia{sufijo}.png"
            fig.savefig(ruta, dpi=DPI_FIG, bbox_inches="tight")
            plt.close(fig)
            hechas.append(ruta.name)
    return hechas


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "":
        modo, rutas, prefijo = "resultado", [RUTA_CSV_R], "R"
        salida, sufijo = DIR_RES / "resumen_R.txt", ""
    elif arg == "--prueba-sustituto":
        modo, rutas, prefijo = "prueba-sustituto", [RUTA_CSV_Q_S1, RUTA_CSV_EXPL_Q], ""
        salida, sufijo = DIR_RES / "resumen_R_prueba_sobre_Q.txt", "_PRUEBA_sobre_Q"
    elif arg == "--prueba-control":
        modo, rutas, prefijo = "prueba-control", [RUTA_CONTROL_CSV], "controlR"
        salida, sufijo = DIR_RES / "resumen_R_prueba_sobre_control.txt", "_PRUEBA_sobre_control"
    else:
        raise SystemExit("uso: python -B analizar_experimento_R.py "
                         "[--prueba-sustituto | --prueba-control]")
    datos, columnas = cargar(rutas)
    if modo == "resultado":
        fijado = next((x for x in RUTA_PREREG.read_text(encoding="utf-8").splitlines()
                       if x.startswith("Fijado: ")), "")
        if not re.match(r"^Fijado: \d{4}-\d{2}-\d{2} \d{2}:\d{2}", fijado):
            raise SystemExit(f"PARAR: PREREGISTRO_R.md no está fijado ({fijado or 'sin línea'}).")
        if any(f.get("prerregistrado") != 1.0 for c in datos.values() for f in c.values()):
            raise SystemExit("PARAR: hay filas sin prerregistrado = 1.")
    registros = {"resultado": [DIR_RES / "control_bit_a_bit_R.txt", DIR_RES / "registro_R.txt"],
                 "prueba-control": [DIR_RES / "control_bit_a_bit_R.txt"]}.get(modo, [])
    motivo = estado_parte_b(registros)
    vistos = cargar([RUTA_CONTROL_CSV])[0] if modo == "resultado" else None
    L, _V = resumen(datos, columnas, modo, prefijo, vistos, motivo_parte_b=motivo)
    hechas = figuras(datos, modo, prefijo,
                     motivo is None and all(c in columnas for c in COLUMNAS_PARTE_B), sufijo)
    L += ["", "FIGURAS: " + ", ".join(hechas)]
    texto = "\n".join(L) + "\n"
    if salida.exists():
        from datetime import datetime
        salida.rename(salida.with_name(f"{salida.stem}_respaldo_{datetime.now():%Y%m%d_%H%M%S}"
                                       f"{salida.suffix}"))
    salida.write_bytes(texto.encode("utf-8"))
    print(texto)


if __name__ == "__main__":
    main()
