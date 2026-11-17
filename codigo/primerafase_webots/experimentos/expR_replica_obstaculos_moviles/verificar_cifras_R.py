"""
verificar_cifras_R.py
=====================
Verificador del resumen del Exp R: NÚCLEO FIJO del §4 de `PREREGISTRO_R.md`.
No lleva literales de resultados y entra al manifiesto pre. Recalcula desde
los CSV CRUDOS, con código propio, cada cifra y cada palabra de veredicto.

Cómo verifica.
- Arma el resumen ESPERADO completo, línea por línea, y lo compara texto
  contra texto con el real. Cada valor recalculado se redondea con el mismo
  formato que imprime el resumen («< 0.0001» incluido), sin tolerancias.
- La completitud vale en los dos sentidos: una línea que sobra, una que
  falta o una cifra distinta es una diferencia, y cada posición se compara
  con la suya (un valor que aparece en otro lugar del resumen no sirve).
- La sección VERIFICACIÓN (sólo en modo resultado) se coteja aparte contra
  los registros. Cada línea tiene que ser copia exacta de su registro, en
  orden, y no puede faltar ninguna verificación al empezar ni al terminar,
  ni los veredictos. Las cifras que se pueden rehacer desde el crudo se
  recalculan: filas, trazas, autochequeos, la prueba física, el control bit
  a bit, la firma de las semillas y las huellas. El resto (horas, sha256 de
  las copias, stack) son hechos de la corrida y se verifican como copias
  exactas.

Independencia.
- No importa `analizar_experimento_R.py`, `correr_experimento_R.py` ni nada
  del Exp Q.
- Las reglas de lectura del §2.4 se reimplementan desde el texto del
  prerregistro. Los casos con trampa están calculados a mano en
  `test_verificar_cifras_R.py`, con los esperados derivados del texto del
  §2.4 por revisores que no vieron el código.
- La Parte B se recalcula desde las TRAZAS (§3.2: mínimo con la regla de
  1e-9, ventana W = 5), no desde las columnas que escribió el código de
  corrida, y se compara con esas columnas. En las filas sin traza, que no
  tienen fallback, sale por identidad de las columnas del Exp Q.
- Clopper-Pearson (bisección sobre la binomial) y McNemar exacta (aritmética
  entera) van con código propio. Si scipy está instalado, cada valor se
  contrasta con el suyo a 10 decimales (|Δ| < 5e-11).
- Las Δ pareadas usan media ± 1,96·EE, con EE de ddof = 1.
- En todos los modos se comprueban, fila por fila, los autochequeos del §3.3.
  En las filas con traza salen de la traza; en las demás, de su identidad
  sin fallback.

Sin literales de resultados de R. Sólo hay constantes de diseño fijadas
antes de correr: sha256 del prerregistro y de la adenda, huellas, semillas,
umbrales, W y la tolerancia de empate. El texto fijo del resumen se copia
del análisis. Eso incluye la frase de la sensibilidad de H6 con «23/100
vistos», que es un dato del exploratorio fijado en el §2.1 del
prerregistro, no un resultado de R.

Modos:

    python -B verificar_cifras_R.py --prueba-sustituto   resumen_R_prueba_sobre_Q.txt
    python -B verificar_cifras_R.py --prueba-control     resumen_R_prueba_sobre_control.txt
    python -B verificar_cifras_R.py                      resumen_R.txt (EL RESULTADO)

Termina con 0 si todo coincide y con 1 si no, y lista cada diferencia. El
archivo de literales de la bitácora (resultados) es aparte y posterior a la
corrida (§4).

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import difflib
import hashlib
import math
import re
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

_CARPETA: Path = Path(__file__).resolve().parent
_CARPETA_Q: Path = (_CARPETA.parent / "expQ_obstaculos_moviles").resolve()
DIR_RES: Path = _CARPETA / "resultados"
DIR_FIG: Path = _CARPETA / "figuras"
DIR_TRAZAS: Path = DIR_RES / "trazas"
RUTA_PREREG: Path = _CARPETA / "PREREGISTRO_R.md"
RUTA_ADENDA: Path = _CARPETA / "ADENDA_PREREGISTRO_R_20261109.md"
RUTA_CSV_R: Path = DIR_RES / "experimento_R_completo.csv"
RUTA_CONTROL_CSV: Path = DIR_RES / "control_bit_a_bit_R.csv"
RUTA_CSV_Q_S1: Path = _CARPETA_Q / "resultados" / "experimento_Q_completo.csv"
RUTA_CSV_EXPL_Q: Path = _CARPETA_Q / "resultados" / "experimento_Q_EXPLORATORIO_S2_S3.csv"

# --- Constantes de DISEÑO (fijadas antes de correr; no son resultados) -------
SHA256_PREREG: str = "a4635806cd2540cd44207224de25640b5040d4be76d2d04d8250f2f06ca67cdd"
SHA256_ADENDA: str = "8dcddafdc9c4a885e0a627d9fa5806edd58709869a9e83010425f7369c5b01df"
HUELLA_Q: str = "e265b6cd31e8d443977027b1bf1d4671c002b06c3ecbdc45a275521e49c24a29"
HUELLA_R: str = "c31f8cd6f4524804e51be7807bdd8a75e1a07885615791e251214708379f5a80"
SEMILLAS_R: Tuple[int, ...] = tuple(range(420110, 420510))   # §1: 42·10 000 + 110…509
SEMILLAS_VISTAS: Tuple[int, ...] = tuple(range(420000, 420100))
NIVELES: Tuple[str, ...] = ("S1", "S2", "S3")
TIPOS: Tuple[str, ...] = ("din", "quieto", "ctrl", "sinvel")
ALFA: float = 0.05
Z95: float = 1.96
W: int = 5                          # §3.2: W = 1/(α·dt)
VENTANAS: Tuple[int, ...] = (3, 5, 10)
UMBRAL_H6: float = 0.10
UMBRAL_COTA: float = 0.13
TOL_EMPATE: float = 1e-9            # §3.2: primera (t, k) con d ≤ d_min + 1e-9
N_AGENTES: int = 5
TOL_SCIPY: float = 5e-11            # "a 10 decimales"
AVISO_PRUEBA: str = "PRUEBA DEL ANÁLISIS SOBRE DATOS VISTOS, NO ES EL RESULTADO DE R"

#: §2.1: (nombre, columna, umbral, "mayor"/"menor", ¿no aplica en ctrl?).
EVENTOS: Tuple[Tuple[str, str, float, str, bool], ...] = (
    ("fallback", "qp_fallbacks", 0.0, "mayor", False),
    ("agotado", "escape_agotados", 0.0, "mayor", False),
    ("contacto", "contactos_obst_eventos", 0.0, "mayor", True),
    ("bajo 0,13 m", "viol_cota_obst_agente_eps", 0.0, "mayor", True),
    ("bajo 0,10 m", "d_min_obst_superficie", UMBRAL_H6, "menor", True),
    ("infactible activo", "escape_infactibles_junto_obst", 0.0, "mayor", True),
)
#: §2.3: las pruebas con p, con A y B del prerregistro (b = sólo en A). El
#: orden de la tupla es la familia de Holm del §2.4.
PRUEBAS: Tuple[Tuple[str, str, str, str, str, str], ...] = (
    ("H1-S3", "fallback", "S3", "din", "quieto", "primaria"),
    ("H1-S2", "fallback", "S2", "din", "quieto", "secundaria"),
    ("H2-S2", "bajo 0,13 m", "S2", "sinvel", "din", "primaria"),
    ("H2-S3", "bajo 0,13 m", "S3", "sinvel", "din", "primaria"),
    ("H3a", "agotado", "S3", "din", "ctrl", "primaria"),
    ("H3b", "agotado", "S3", "din", "quieto", "secundaria"),
    ("H5b", "contacto", "S3", "sinvel", "din", "secundaria"),
)

#: Texto fijo del resumen (enunciados y encabezados): no lleva cifras de resultados.
ENUNCIADO: Dict[str, str] = {
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
COLUMNAS_PARTE_B: Tuple[str, ...] = (
    "pasos_agente_fallback", "d_min_sin_fallback", "d_min_en_fallback",
    "d_min_fuera_ventana_3", "d_min_fuera_ventana_5", "d_min_fuera_ventana_10",
    "pasos_bajo_010", "pasos_bajo_010_fuera_ventana_5", "paso_d_min", "agente_d_min",
    "fallback_en_d_min", "racha_fallback_d_min", "fallback_ventana_d_min_5",
    "pasos_agente_intervino", "pasos_agente_escape_intervino", "contactos_registrados",
    "fb_desplazado", "xy_discontinuo", "fb_desplazado_corrido")
#: Las que usa el resumen (H6 y la sensibilidad); el análisis exige éstas.
COLUMNAS_H6: Tuple[str, ...] = ("d_min_fuera_ventana_5", "fallback_ventana_d_min_5",
                                "d_min_sin_fallback", "d_min_fuera_ventana_3",
                                "d_min_fuera_ventana_10")
REGISTROS: Tuple[str, ...] = ("comparar_ast_R.txt", "control_bit_a_bit_R.txt",
                              "pasabilidad_R.txt", "registro_R.txt")

Fila = Dict[str, str]
Datos = Dict[str, Dict[int, Fila]]


# =============================================================================
# ESTADÍSTICA PROPIA (sin scipy)
# =============================================================================

_CACHE_CP: Dict[Tuple[int, int], Tuple[float, float]] = {}


def _log_pmf(i: int, n: int, p: float) -> float:
    return math.log(math.comb(n, i)) + i * math.log(p) + (n - i) * math.log1p(-p)


def cola_superior(k: int, n: int, p: float) -> float:
    """P(X ≥ k) para X ~ Bin(n, p), 0 < p < 1."""
    return math.fsum(math.exp(_log_pmf(i, n, p)) for i in range(k, n + 1))


def cola_inferior(k: int, n: int, p: float) -> float:
    """P(X ≤ k) para X ~ Bin(n, p), 0 < p < 1."""
    return math.fsum(math.exp(_log_pmf(i, n, p)) for i in range(0, k + 1))


def _raiz(f, creciente: bool) -> float:
    """Bisección en (0, 1) hasta floats contiguos: el p con f(p) = 0."""
    a, b = 0.0, 1.0
    while True:
        m = (a + b) / 2
        if m <= a or m >= b:
            return m
        if (f(m) < 0) == creciente:
            a = m
        else:
            b = m


def clopper_pearson(k: int, n: int) -> Tuple[float, float]:
    """IC95 exacto: lo con P(X ≥ k; lo) = α/2, hi con P(X ≤ k; hi) = α/2."""
    if (k, n) not in _CACHE_CP:
        lo = 0.0 if k == 0 else _raiz(lambda p: cola_superior(k, n, p) - ALFA / 2, True)
        hi = 1.0 if k == n else _raiz(lambda p: cola_inferior(k, n, p) - ALFA / 2, False)
        _CACHE_CP[(k, n)] = (lo, hi)
    return _CACHE_CP[(k, n)]


def mcnemar(b: int, c: int) -> float:
    """p bilateral exacta con p = 1/2 sobre los b + c discordantes (enteros exactos)."""
    n = b + c
    if n == 0:
        return 1.0
    cola = sum(math.comb(n, i) for i in range(0, min(b, c) + 1))
    return float(min(Fraction(1), Fraction(2 * cola, 2 ** n)))


def holm(ps: Sequence[float]) -> List[float]:
    """Holm paso a paso hacia abajo, monótona y con tope en 1, en el orden de entrada."""
    m = len(ps)
    orden = sorted(range(m), key=lambda i: ps[i])
    salida = [0.0] * m
    acumulado = 0.0
    for j, i in enumerate(orden):
        acumulado = max(acumulado, min(1.0, (m - j) * ps[i]))
        salida[i] = acumulado
    return salida


def ic95(x: Sequence[float]) -> Tuple[float, float, float]:
    """Media ± 1,96·EE, EE = sd(ddof = 1)/√n."""
    n = len(x)
    m = math.fsum(x) / n
    ee = math.sqrt(math.fsum((v - m) ** 2 for v in x) / (n - 1)) / math.sqrt(n) if n > 1 else 0.0
    return m, m - Z95 * ee, m + Z95 * ee


# --- Formatos del resumen (texto contra texto) --------------------------------

def fmt_p(p: float) -> str:
    return "< 0.0001" if p < 0.0001 else f"{p:.4f}"


def fmt_kn(k: int, n: int) -> str:
    lo, hi = clopper_pearson(k, n)
    return f"{k}/{n} [{lo:.4f}, {hi:.4f}]"


def fmt_delta(m: float, lo: float, hi: float, marca: bool = True) -> str:
    texto = f"{m:+.8f} [{lo:+.8f}, {hi:+.8f}]"
    return texto + ("*" if lo * hi > 0 else " ") if marca else texto


# =============================================================================
# REGLAS DE LECTURA (§2.4, reimplementadas desde el texto del prerregistro)
# =============================================================================

def regla_p(b: int, c: int, p: float) -> str:
    """'sostenida' si p < 0,05 y b > c; si no, 'no sostenida', con '(dirección
    contraria)' si p < 0,05 con c > b y '(sin discordantes)' si b + c = 0."""
    if b + c == 0:
        return "no sostenida (sin discordantes)"
    if p < ALFA and b > c:
        return "sostenida"
    if p < ALFA and c > b:
        return "no sostenida (dirección contraria)"
    return "no sostenida"


def regla_h4(lo_piezas: Sequence[float]) -> str:
    """'sostenida' si las dos piezas tienen el límite inferior estrictamente > 0."""
    return "sostenida" if all(lo > 0 for lo in lo_piezas) else "no sostenida"


def regla_pieza_h4(lo: float) -> str:
    return "cumple" if lo > 0 else "no cumple"


def regla_h5a(contactos: Sequence[int]) -> str:
    """'cumplida' si los tres niveles dan 0; si no, 'no cumplida'."""
    return "cumplida" if all(k == 0 for k in contactos) else "no cumplida"


def regla_h6a(m: int, k: int) -> str:
    """Por nivel: 'no evaluable en el nivel' si m = 0; 'cumplida' si k = m ≥ 1."""
    if m == 0:
        return "no evaluable en el nivel"
    return "cumplida" if k == m else "no cumplida"


def regla_h6b(fuera: int) -> str:
    return "cumplida" if fuera == 0 else "no cumplida"


def frase_holm(p_holm: float, b: int, c: int) -> str:
    return ("p Holm < 0,05 en la dirección predicha" if p_holm < ALFA and b > c
            else "p Holm ≥ 0,05 o dirección contraria")


def motivo_parte_b(registros: Sequence[Path]) -> Optional[str]:
    """§2.4: si el control o el experimento registran «PARTE B: NO», H6 no es evaluable."""
    for ruta in registros:
        if ruta.exists() and "PARTE B: NO" in ruta.read_text(encoding="utf-8"):
            return f"no evaluable: {ruta.name} dice PARTE B: NO (§7 del prerregistro)"
    return None


# =============================================================================
# DATOS
# =============================================================================

def cargar(rutas: Sequence[Path], diferencias: List[str]) -> Tuple[Datos, Set[str]]:
    """datos[condición][semilla] = fila de texto; las filas repetidas son diferencias."""
    datos: Datos = {}
    columnas: Set[str] = set()
    for ruta in rutas:
        with open(ruta, encoding="utf-8", newline="") as f:
            lector = csv.DictReader(f)
            columnas |= set(lector.fieldnames or [])
            for r in lector:
                celda = datos.setdefault(r["condicion"], {})
                s = int(r["seed_ep"])
                if s in celda:
                    diferencias.append(f"DATOS: fila repetida {r['condicion']}/{s} en {ruta.name}")
                celda[s] = r
    return datos, columnas


def num(fila: Fila, col: str) -> float:
    return float(fila[col])


def tiene(fila: Fila, evento: str) -> bool:
    _n, col, umbral, modo, _ctrl = next(e for e in EVENTOS if e[0] == evento)
    v = num(fila, col)
    return v > umbral if modo == "mayor" else v < umbral


def con_evento(datos: Datos, celda: str, evento: str, sem: Sequence[int]) -> Set[int]:
    return {s for s in sem if tiene(datos[celda][s], evento)}


def requiere_traza(tipo: str, fila: Fila) -> bool:
    """§3.4: celdas con obstáculo físico con fallback, contacto o d_min < 0,10 m."""
    return tipo != "ctrl" and (num(fila, "qp_fallbacks") > 0
                               or num(fila, "contactos_obst_eventos") > 0
                               or num(fila, "d_min_obst_superficie") < UMBRAL_H6)


# =============================================================================
# PARTE B DESDE LAS TRAZAS (§3.2 y §3.3)
# =============================================================================

def leer_traza(ruta: Path) -> List[Dict[str, str]]:
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _en_ventana(fb: List[List[int]], t: int, k: int, w: int) -> bool:
    """¿El agente k tuvo fallback en alguna decisión t − w + 1 … t?"""
    return any(fb[s][k] for s in range(max(0, t - w + 1), t + 1))


def parte_b_de_traza(filas: List[Dict[str, str]], pasos: int
                     ) -> Tuple[Dict[str, float], List[str]]:
    """Las 19 columnas de la Parte B desde una traza, con la definición del §3.2."""
    problemas: List[str] = []
    if len(filas) != pasos * N_AGENTES:
        return {}, [f"la traza tiene {len(filas)} filas, no {pasos * N_AGENTES}"]
    fb = [[0] * N_AGENTES for _ in range(pasos)]
    do = [[0.0] * N_AGENTES for _ in range(pasos)]
    esc = [[0] * N_AGENTES for _ in range(pasos)]
    inter = [[0] * N_AGENTES for _ in range(pasos)]
    nuevo = [[0] * N_AGENTES for _ in range(pasos)]
    xa = [[(0.0, 0.0)] * N_AGENTES for _ in range(pasos)]
    xd = [[(0.0, 0.0)] * N_AGENTES for _ in range(pasos)]
    for i, r in enumerate(filas):
        t, k = int(r["paso"]), int(r["agente"])
        if (t, k) != (i // N_AGENTES, i % N_AGENTES):
            return {}, [f"fila {i + 2} de la traza fuera de orden (paso {t}, agente {k})"]
        fb[t][k], do[t][k] = int(r["fallback"]), float(r["d_obst"])
        esc[t][k], inter[t][k], nuevo[t][k] = (int(r["en_escape"]), int(r["intervino"]),
                                               int(r["contacto_nuevo"]))
        xa[t][k] = (float(r["x_antes"]), float(r["y_antes"]))
        xd[t][k] = (float(r["x_despues"]), float(r["y_despues"]))
    inf = math.inf
    d_min = d_sin = d_en = inf
    fuera = {w: inf for w in VENTANAS}
    bajo = bajo_fuera = 0
    for t in range(pasos):
        for k in range(N_AGENTES):
            d = do[t][k]
            d_min = min(d_min, d)
            if fb[t][k]:
                d_en = min(d_en, d)
            else:
                d_sin = min(d_sin, d)
            for w in VENTANAS:
                if not _en_ventana(fb, t, k, w):
                    fuera[w] = min(fuera[w], d)
            if d < UMBRAL_H6:
                bajo += 1
                bajo_fuera += int(not _en_ventana(fb, t, k, W))
    paso = agente = -1
    if d_min < inf:
        paso, agente = next((t, k) for t in range(pasos) for k in range(N_AGENTES)
                            if do[t][k] <= d_min + TOL_EMPATE)
    fb_en = fb[paso][agente] if paso >= 0 else 0
    racha = 0
    if fb_en:
        s = paso
        while s >= 0 and fb[s][agente]:
            racha += 1
            s -= 1
    desplazado = corrido = discontinuo = 0
    for t in range(pasos):
        for k in range(N_AGENTES):
            movido = xd[t][k] != xa[t][k]
            if nuevo[t][k] == 0 and movido:
                desplazado += fb[t][k]
                if t > 0:
                    corrido += fb[t - 1][k]
            if t > 0 and xa[t][k] != xd[t - 1][k]:
                discontinuo += 1
    salida: Dict[str, float] = {
        "pasos_agente_fallback": sum(map(sum, fb)), "d_min_sin_fallback": d_sin,
        "d_min_en_fallback": d_en, "pasos_bajo_010": bajo,
        "pasos_bajo_010_fuera_ventana_5": bajo_fuera, "paso_d_min": paso,
        "agente_d_min": agente, "fallback_en_d_min": fb_en, "racha_fallback_d_min": racha,
        "fallback_ventana_d_min_5": int(_en_ventana(fb, paso, agente, W)) if paso >= 0 else 0,
        "pasos_agente_intervino": sum(map(sum, inter)),
        "pasos_agente_escape_intervino": sum(esc[t][k] * inter[t][k] for t in range(pasos)
                                             for k in range(N_AGENTES)),
        "contactos_registrados": sum(map(sum, nuevo)), "fb_desplazado": desplazado,
        "xy_discontinuo": discontinuo, "fb_desplazado_corrido": corrido,
        "_d_min": d_min,
    }
    for w in VENTANAS:
        salida[f"d_min_fuera_ventana_{w}"] = fuera[w]
    return salida, problemas


def contactos_de_traza(filas: List[Dict[str, str]]) -> Tuple[int, int]:
    """(agente-pasos con contacto nuevo, cuántos en la ventana de W de un fallback propio)."""
    fb = {(int(r["paso"]), int(r["agente"])): int(r["fallback"]) for r in filas}
    total = en_v = 0
    for r in filas:
        if int(r["contacto_nuevo"]) > 0:
            t, a = int(r["paso"]), int(r["agente"])
            total += 1
            en_v += int(any(fb.get((s, a), 0) for s in range(max(0, t - W + 1), t + 1)))
    return total, en_v


def parte_b_recalculada(datos: Datos, prefijo: str, dir_trazas: Path,
                        diferencias: List[str], cuenta: Dict[str, int],
                        exigir_trazas: bool = True) -> Dict[str, Dict[int, Dict[str, float]]]:
    """
    Para cada fila de celdas con obstáculo físico: con traza, las 19 columnas de
    la Parte B recalculadas desde la traza y comparadas EXACTAS con las del
    CSV; sin traza (no hay fallback, contacto ni d_min < 0,10), las que usa H6
    salen por identidad de las columnas del Exp Q. Devuelve lo recalculado.
    """
    pb: Dict[str, Dict[int, Dict[str, float]]] = {}
    esperadas: Set[str] = set()
    for celda, filas in datos.items():
        tipo = celda.split("_", 1)[1]
        if tipo == "ctrl":
            continue
        for s, f in filas.items():
            nombre = f"{prefijo}_{celda}_{s}.csv"
            ruta = dir_trazas / nombre
            if requiere_traza(tipo, f):
                esperadas.add(nombre)
                if not ruta.exists():
                    if exigir_trazas:
                        diferencias.append(f"PARTE B: falta la traza {nombre}")
                    # Sin traza no se puede recalcular: H6 sigue con las columnas del
                    # CSV para poder listar el resto de las diferencias.
                    rec = {c: float(f[c]) for c in COLUMNAS_H6}
                    rec["_d_min"] = num(f, "d_min_obst_superficie")
                    pb.setdefault(celda, {})[s] = rec
                    continue
                rec, probl = parte_b_de_traza(leer_traza(ruta), int(num(f, "pasos")))
                diferencias += [f"PARTE B: {nombre}: {p}" for p in probl]
                if not rec:
                    continue
                cuenta["filas_con_traza"] = cuenta.get("filas_con_traza", 0) + 1
                for col in COLUMNAS_PARTE_B:
                    if col in f and float(f[col]) != rec[col]:
                        diferencias.append(f"PARTE B: {celda}/{s} {col}: CSV {f[col]} ≠ traza "
                                           f"{rec[col]!r}")
                # Contra las columnas del Exp Q (autochequeos del §3.3, desde la traza).
                for col_q, valor in (("d_min_obst_superficie", rec["_d_min"]),
                                     ("qp_fallbacks", rec["pasos_agente_fallback"]),
                                     ("contactos_obst_eventos", rec["contactos_registrados"]),
                                     ("escape_filtro_modifico",
                                      rec["pasos_agente_escape_intervino"])):
                    if float(f[col_q]) != valor:
                        diferencias.append(f"PARTE B: {celda}/{s} {col_q}: CSV {f[col_q]} ≠ "
                                           f"traza {valor!r}")
                ap = int(num(f, "pasos")) * N_AGENTES
                if repr(rec["pasos_agente_intervino"] / ap) != f["cbf_frac_interv"]:
                    diferencias.append(f"PARTE B: {celda}/{s} intervención de la traza ≠ "
                                       f"cbf_frac_interv")
                pb.setdefault(celda, {})[s] = rec
            else:
                if ruta.exists():
                    diferencias.append(f"PARTE B: traza que no corresponde {nombre}")
                d = num(f, "d_min_obst_superficie")
                rec = {"d_min_sin_fallback": d, "d_min_en_fallback": math.inf,
                       "fallback_ventana_d_min_5": 0, "fallback_en_d_min": 0,
                       "racha_fallback_d_min": 0, "pasos_agente_fallback": 0,
                       "pasos_bajo_010": 0, "pasos_bajo_010_fuera_ventana_5": 0,
                       "contactos_registrados": 0, "_d_min": d}
                for w in VENTANAS:
                    rec[f"d_min_fuera_ventana_{w}"] = d
                # Sin fallback, ningún agente en fallback se mueve: fb_desplazado y el
                # corrido son 0; xy_discontinuo es 0 en toda fila (§3.3).
                rec.update({"fb_desplazado": 0, "fb_desplazado_corrido": 0, "xy_discontinuo": 0})
                cuenta["filas_por_identidad"] = cuenta.get("filas_por_identidad", 0) + 1
                for col, v in rec.items():
                    if col in f and float(f[col]) != v:
                        diferencias.append(f"PARTE B: {celda}/{s} {col}: CSV {f[col]} ≠ "
                                           f"identidad sin fallback {v!r}")
                if "paso_d_min" in f and not (0 <= int(f["paso_d_min"]) < int(num(f, "pasos"))
                                              and 0 <= int(f["agente_d_min"]) < N_AGENTES):
                    diferencias.append(f"PARTE B: {celda}/{s} paso_d_min/agente_d_min fuera "
                                       f"de rango")
                pb.setdefault(celda, {})[s] = rec
    if exigir_trazas and dir_trazas.exists():
        sobran = sorted(p.name for p in dir_trazas.glob(f"{prefijo}_*.csv")
                        if p.name not in esperadas and celda_de(p.name, prefijo) in datos)
        diferencias += [f"PARTE B: traza sin fila que la requiera {x}" for x in sobran]
    return pb


def celda_de(nombre: str, prefijo: str) -> str:
    m = re.match(rf"^{re.escape(prefijo)}_(S\d_\w+?)_(\d+)\.csv$", nombre)
    return m.group(1) if m else ""


# =============================================================================
# EL RESUMEN ESPERADO
# =============================================================================

def lineas_prerregistro(sem: Sequence[int], ruta_prereg: Path) -> List[str]:
    texto = ruta_prereg.read_bytes()
    fijado = next((x for x in texto.decode("utf-8").splitlines() if x.startswith("Fijado: ")),
                  "Fijado: (sin línea de fijación)")
    return ["PRERREGISTRO",
            f"  PREREGISTRO_R.md sha256 {hashlib.sha256(texto).hexdigest()}; {fijado}",
            f"  semillas {sem[0]}–{sem[-1]}, n = {len(sem)} por celda, 12 celdas"]


def no_sustenta(ruta_prereg: Path) -> List[str]:
    """Los puntos del §6 del prerregistro, tal cual."""
    puntos, dentro = [], False
    for linea in ruta_prereg.read_text(encoding="utf-8").splitlines():
        if linea.startswith("## "):
            dentro = linea.startswith("## 6.")
            continue
        if dentro and linea.startswith("- "):
            puntos.append(f"  - {linea[2:]}")
    return puntos


def mcnemar_celdas(datos: Datos, sem: Sequence[int], evento: str, k: str, a: str, b: str
                   ) -> Tuple[int, int, int, int, float]:
    """(k_A, k_B, b, c, p); b = episodios con el evento sólo en A = Sk_a."""
    ea = con_evento(datos, f"{k}_{a}", evento, sem)
    eb = con_evento(datos, f"{k}_{b}", evento, sem)
    bb, cc = len(ea - eb), len(eb - ea)
    return len(ea), len(eb), bb, cc, mcnemar(bb, cc)


def columna(datos: Datos, celda: str, col: str, sem: Sequence[int]) -> List[float]:
    return [num(datos[celda][s], col) for s in sem]


def lineas_hipotesis(datos: Datos, sem: Sequence[int], pb: Optional[Dict], motivo: Optional[str],
                     prefijo: str, con_trazas: bool, dir_trazas: Path
                     ) -> Tuple[List[str], Dict[str, str], Dict[str, Tuple]]:
    n = len(sem)
    V: Dict[str, str] = {}
    res = {pid: mcnemar_celdas(datos, sem, ev, k, a, b) for pid, ev, k, a, b, _c in PRUEBAS}

    def linea(pid: str) -> str:
        _p, _ev, k, a, b, clase = next(x for x in PRUEBAS if x[0] == pid)
        ka, kb, bb, cc, p = res[pid]
        V[pid] = regla_p(bb, cc, p)
        return (f"    {k} ({clase}): A = {k}_{a} {fmt_kn(ka, n)}; B = {k}_{b} {fmt_kn(kb, n)}; "
                f"b/c = {bb}/{cc}; p = {fmt_p(p)} → {V[pid]}")

    L = ["RESULTADOS POR HIPÓTESIS (α = 0,05 bilateral, sin ajuste; reglas de lectura del "
         "prerregistro: con p, 'sostenida' sólo si p < 0,05 y b > c; H1, H2 y H6 se leen por "
         "nivel, sin veredicto conjunto)"]
    L.append(f"  H1  {ENUNCIADO['H1']}: episodios con fallback, A = Sk_din, B = Sk_quieto; "
             f"McNemar; predicción A > B")
    L += [linea("H1-S3"), linea("H1-S2")]
    ka, kb, bb, cc, p = mcnemar_celdas(datos, sem, "fallback", "S1", "din", "quieto")
    L.append(f"    S1 (descriptiva, sin veredicto): A = S1_din {fmt_kn(ka, n)}; B = S1_quieto "
             f"{fmt_kn(kb, n)}; b/c = {bb}/{cc}; p = {fmt_p(p)}")
    L.append("    necesidad (descriptiva, sin veredicto): con obstáculos quietos, fallback en "
             + "; ".join(f"{k} {fmt_kn(len(con_evento(datos, f'{k}_quieto', 'fallback', sem)), n)}"
                         for k in NIVELES))
    L.append(f"  H2  {ENUNCIADO['H2']}: episodios bajo 0,13 m, A = Sk_sinvel, B = Sk_din; "
             f"McNemar; predicción A > B")
    L += [linea("H2-S2"), linea("H2-S3")]
    ka, kb, bb, cc, p = mcnemar_celdas(datos, sem, "bajo 0,13 m", "S1", "sinvel", "din")
    L.append(f"    S1 (descriptiva, sin veredicto): A = S1_sinvel {fmt_kn(ka, n)}; B = S1_din "
             f"{fmt_kn(kb, n)}; b/c = {bb}/{cc}; p = {fmt_p(p)}")
    L.append(f"  H3a {ENUNCIADO['H3a']}: episodios con agotado, A = S3_din, B = S3_ctrl; "
             f"McNemar; predicción A > B")
    L.append(linea("H3a"))
    L.append(f"  H3b {ENUNCIADO['H3b']}: episodios con agotado, A = S3_din, B = S3_quieto; "
             f"McNemar; predicción A > B")
    L.append(linea("H3b"))
    dif = [float(tiene(datos["S3_din"][s], "agotado")) - float(tiene(datos["S3_quieto"][s], "agotado"))
           for s in sem]
    L.append("    Δ de tasas pareada (din − quieto), media ± 1,96·EE (ddof = 1), descriptiva "
             f"(el veredicto es sólo el de la McNemar): {fmt_delta(*ic95(dif), marca=False)}")
    # H4
    dk = {k: [a - b for a, b in zip(columna(datos, f"{k}_din", "cobertura_accesible", sem),
                                    columna(datos, f"{k}_ctrl", "cobertura_accesible", sem))]
          for k in NIVELES}
    L.append(f"  H4  {ENUNCIADO['H4']} (secundaria, compuesta): Δ_k = cobertura_accesible "
             f"din − ctrl, pareada por semilla; piezas Δ_S1 − Δ_S3 > 0 y Δ_S2 − Δ_S3 > 0 (IC95 "
             f"con lo > 0); 'sostenida' sólo si se cumplen las dos")
    los = []
    for k1 in ("S1", "S2"):
        m, lo, hi = ic95([a - b for a, b in zip(dk[k1], dk["S3"])])
        los.append(lo)
        L.append(f"    Δ_{k1} − Δ_S3: {fmt_delta(m, lo, hi)} → {regla_pieza_h4(lo)}")
    V["H4"] = regla_h4(los)
    L.append("    Δ_k (descriptivas): " + "; ".join(f"{k} {fmt_delta(*ic95(dk[k]))}"
                                                     for k in NIVELES))
    L.append(f"    → {V['H4']}")
    # H5a
    cont = {k: sorted(con_evento(datos, f"{k}_din", "contacto", sem)) for k in NIVELES}
    V["H5a"] = regla_h5a([len(cont[k]) for k in NIVELES])
    L.append(f"  H5a {ENUNCIADO['H5a']} (primaria): episodios con contacto en Sk_din, "
             f"Clopper-Pearson → " + "; ".join(f"{k} {fmt_kn(len(cont[k]), n)}" for k in NIVELES)
             + f" → {V['H5a']}")
    if any(cont.values()):
        L.append("    lectura (§2.4): k ≥ 1 se reporta como tasa k/400 con su IC95 y se discute "
                 "con la traza de cada episodio (si el contacto cayó en la ventana de un "
                 "fallback del agente o no); no se lee como 'el filtro falla'")
        for k in NIVELES:
            for s in cont[k]:
                ruta = dir_trazas / f"{prefijo}_{k}_din_{s}.csv"
                if motivo is not None:
                    L.append(f"    {k}_din {s}: ubicación del contacto {motivo}")
                elif con_trazas and ruta.exists():
                    total, en_v = contactos_de_traza(leer_traza(ruta))
                    L.append(f"    {k}_din {s}: {total} contactos nuevos, {en_v} en la ventana "
                             f"de un fallback del agente")
                else:
                    L.append(f"    {k}_din {s}: sin traza para ubicar el contacto")
    L.append(f"  H5b {ENUNCIADO['H5b']}: episodios con contacto, A = S3_sinvel, B = S3_din; "
             f"McNemar; predicción A > B (potencia acoplada a H5a: cada contacto en din sube c)")
    L.append(linea("H5b"))
    # H6
    L.append(f"  H6  Parte B (secundarias, descriptivas), ventana de W = {W} decisiones "
             f"(t−{W - 1} … t) del mismo agente, W = 1/(α·dt); umbral 0,10 m; en Sk_din")
    if motivo is not None:
        for k in NIVELES:
            V[f"H6a-{k}"] = V[f"H6b-{k}"] = motivo
        L.append(f"    {motivo}")
    else:
        assert pb is not None
        for k in NIVELES:
            celda = f"{k}_din"
            bajo = [s for s in sem if pb[celda][s]["_d_min"] < UMBRAL_H6]
            en_v = sum(int(pb[celda][s]["fallback_ventana_d_min_5"]) for s in bajo)
            fuera = sum(pb[celda][s]["d_min_fuera_ventana_5"] < UMBRAL_H6 for s in sem)
            V[f"H6a-{k}"] = regla_h6a(len(bajo), en_v)
            V[f"H6b-{k}"] = regla_h6b(fuera)
            ic = f" {fmt_kn(en_v, len(bajo))}" if bajo else ""
            L.append(f"    {k}: H6a ({ENUNCIADO['H6a']}) {en_v} de {len(bajo)} episodios bajo "
                     f"0,10 m con el mínimo en la ventana{ic} → {V[f'H6a-{k}']}; "
                     f"H6b ({ENUNCIADO['H6b']}) {fmt_kn(fuera, n)} episodios bajo 0,10 m "
                     f"fuera de la ventana → {V[f'H6b-{k}']}")
        L.append("    sensibilidad declarada (rotulada, sin veredicto), del tipo H6b: episodios "
                 "de Sk_din bajo el umbral fuera de la ventana; en 0,13 se espera ≥ ~23 % en S3 "
                 "por los episodios sin fallback (23/100 vistos)")
        for k in NIVELES:
            celda = f"{k}_din"
            partes = []
            for nom, col, u in (("W=1", "d_min_sin_fallback", UMBRAL_H6),
                                ("W=3", "d_min_fuera_ventana_3", UMBRAL_H6),
                                ("W=10", "d_min_fuera_ventana_10", UMBRAL_H6),
                                ("W=5 umbral 0,13", "d_min_fuera_ventana_5", UMBRAL_COTA)):
                partes.append(f"{nom} {sum(pb[celda][s][col] < u for s in sem)}/{n}")
            L.append(f"    {k}: " + "; ".join(partes))
    return L, V, res


def lineas_holm(res: Dict[str, Tuple], V: Dict[str, str]) -> List[str]:
    ids = [x[0] for x in PRUEBAS]
    aj = holm([res[i][4] for i in ids])
    L = [f"SENSIBILIDAD — p ajustada por Holm sobre la familia cerrada de {len(ids)} "
         f"(no cambia la palabra del veredicto)"]
    for i, a in zip(ids, aj):
        bb, cc, p = res[i][2], res[i][3], res[i][4]
        L.append(f"  {i}: p = {fmt_p(p)}; p Holm = {fmt_p(a)} → {frase_holm(a, bb, cc)} "
                 f"(veredicto: {V[i]})")
    return L


def lineas_eventos(datos: Datos, sem: Sequence[int]) -> List[str]:
    n = len(sem)
    L = ["EVENTOS RAROS — episodios con al menos un evento (k de n) e IC95 de "
         "Clopper-Pearson; en el control, los que exigen obstáculo físico 'no aplica'"]
    for k in NIVELES:
        for t in TIPOS:
            c = f"{k}_{t}"
            partes = [f"{nom} no aplica" if (t == "ctrl" and fisico) else
                      f"{nom} {fmt_kn(len(con_evento(datos, c, nom, sem)), n)}"
                      for nom, _col, _u, _m, fisico in EVENTOS]
            L.append(f"  {c}: " + "; ".join(partes))
    L.append("INFACTIBLE CON OBSTÁCULO ACTIVO, din − quieto (McNemar, descriptiva, sin "
             "predicción, fuera de Holm):")
    for k in NIVELES:
        ka, kb, bb, cc, p = mcnemar_celdas(datos, sem, "infactible activo", k, "din", "quieto")
        L.append(f"  {k}: din {ka}, quieto {kb}; b/c = {bb}/{cc}; p = {fmt_p(p)}")
    L.append("AGOTADOS de S1 y S2 (descriptivo): " + "; ".join(
        f"{k}_{t} {len(con_evento(datos, f'{k}_{t}', 'agotado', sem))}"
        for k in ("S1", "S2") for t in TIPOS))
    return L


def _resta(datos: Datos, k: str, a: str, b: str, col: str, sem: Sequence[int]) -> List[float]:
    return [x - y for x, y in zip(columna(datos, f"{k}_{a}", col, sem),
                                  columna(datos, f"{k}_{b}", col, sem))]


def lineas_costo(datos: Datos, sem: Sequence[int]) -> List[str]:
    L = ["COSTO EN TAREA — Δ pareadas por semilla, IC95 (denominadores del §3.6 de la "
         "propuesta: din − ctrl sobre cobertura_accesible; din − quieto sobre cob_acc_arranque)"]
    for k in NIVELES:
        L.append(f"  {k}: din − ctrl "
                 f"{fmt_delta(*ic95(_resta(datos, k, 'din', 'ctrl', 'cobertura_accesible', sem)))}"
                 f"; din − quieto "
                 f"{fmt_delta(*ic95(_resta(datos, k, 'din', 'quieto', 'cob_acc_arranque', sem)))}"
                 f"; intervención din − ctrl "
                 f"{fmt_delta(*ic95(_resta(datos, k, 'din', 'ctrl', 'cbf_frac_interv', sem)))}")
    return L


def lineas_intervencion(datos: Datos, sem: Sequence[int]) -> List[str]:
    L = ["INTERVENCIÓN — fracción de agente-decisión (media por celda) y filas F1 saturadas "
         "(suma)"]
    for k in NIVELES:
        for t in TIPOS:
            c = f"{k}_{t}"
            m = {x: math.fsum(columna(datos, c, x, sem)) / len(sem)
                 for x in ("cbf_frac_interv", "cbf_frac_lig_pared", "cbf_frac_lig_robot",
                           "cbf_frac_lig_obst")}
            sat = int(math.fsum(columna(datos, c, "f1_filas_saturadas", sem)))
            L.append(f"  {c}: total {m['cbf_frac_interv']:.8f}; ligante pared "
                     f"{m['cbf_frac_lig_pared']:.8f}, robot {m['cbf_frac_lig_robot']:.8f}, "
                     f"obstáculo {m['cbf_frac_lig_obst']:.8f}; filas F1 saturadas {sat}")
    return L


def lineas_diagnostico(vistos: Datos, pb_vistos: Dict) -> List[str]:
    sv = sorted(vistos["S1_din"])
    L = ["DIAGNÓSTICO RETROSPECTIVO SOBRE SEMILLAS VISTAS (420000–420099; control bit a bit de "
         "R; descriptivo, NO cuenta como prueba de H6)"]
    for k in NIVELES:
        for t in ("din", "sinvel"):
            c = f"{k}_{t}"
            bajo = [s for s in sv if pb_vistos[c][s]["_d_min"] < UMBRAL_H6]
            en_v = sum(int(pb_vistos[c][s]["fallback_ventana_d_min_5"]) for s in bajo)
            fuera = sum(pb_vistos[c][s]["d_min_fuera_ventana_5"] < UMBRAL_H6 for s in sv)
            fb = len(con_evento(vistos, c, "fallback", sv))
            L.append(f"  {c}: {fb} episodios con fallback; {len(bajo)} bajo 0,10 m, {en_v} con "
                     f"el mínimo en la ventana; {fuera} bajo 0,10 m fuera de la ventana")
    return L


def figuras_esperadas(modo: str, sufijo: str, evaluable: bool, datos: Datos,
                      sem: Sequence[int]) -> List[str]:
    hechas = [f"fig_R_costo{sufijo}.png", f"fig_R_intervencion{sufijo}.png"]
    casos = any(num(datos[f"{k}_din"][s], "d_min_obst_superficie") < UMBRAL_H6
                for k in NIVELES for s in sem)
    if evaluable and modo != "prueba-sustituto" and casos:
        hechas.append(f"fig_R_fallback_distancia{sufijo}.png")
    return hechas


# =============================================================================
# VERIFICACIÓN (modo resultado): copias exactas + cifras recalculables
# =============================================================================

#: Comienzos de las líneas que tienen que estar sí o sí (veredictos, firmas y
#: resultados de las verificaciones), además del bloque de inicio y el de fin.
REQUERIDAS: Dict[str, Tuple[str, ...]] = {
    "comparar_ast_R.txt": ("COMPROBACIÓN", "NOMBRES LIBRES", "HUELLA_R"),
    "control_bit_a_bit_R.txt": ("CONTROL: ", "CONTROL bit a bit", "de los 1200", "AUTOCHEQUEOS",
                                "la prueba física", "TRAZAS:", "PARTE B:"),
    "pasabilidad_R.txt": ("S1:", "S2:", "S3:", "PASABILIDAD:", "SEMILLAS_R"),
    "registro_R.txt": ("FILAS:", "AUTOCHEQUEOS", "la prueba física", "TRAZAS:", "PARTE B:",
                       "semillas", "manifiestos pre"),
}
_RE_RESULTADO_CELDA = re.compile(r"^S\d_(din|quieto|ctrl|sinvel): cob_acc=")


def bloque_inicio_fin(lineas: Sequence[str]) -> List[int]:
    """Índices desde la línea 2 hasta «congelados … al empezar» y desde «AL TERMINAR:»
    hasta el final (la definición de la adenda 1)."""
    i = next((j for j, x in enumerate(lineas)
              if x.startswith("congelados de la campaña al empezar")), None)
    f = next((j for j, x in enumerate(lineas) if x == "AL TERMINAR:"), None)
    if i is None or f is None:
        return []
    return list(range(1, i + 1)) + list(range(f, len(lineas)))


def cifras_registro_control(texto: Sequence[str], ruta_control_csv: Path, rutas_q: Sequence[Path],
                            dir_trazas: Path) -> List[str]:
    """Recalcula las líneas del control que salen del crudo."""
    dif: List[str] = []
    d: List[str] = []
    datos, _cols = cargar([ruta_control_csv], d)
    filas_r = [f for c in datos.values() for f in c.values()]
    refs: List[Tuple[str, Dict[Tuple[str, int], Fila], List[str]]] = []
    for ruta, excluir in ((rutas_q[0], ("t_episodio_s",)), (rutas_q[1], ("t_episodio_s", "exploratorio"))):
        with open(ruta, encoding="utf-8", newline="") as f:
            lector = csv.DictReader(f)
            cols = [c for c in (lector.fieldnames or []) if c not in excluir]
            refs.append((ruta.name, {(r["condicion"], int(r["seed_ep"])): r for r in lector}, cols))
    partes = []
    for nombre, ref, cols in refs:
        iguales = sum(1 for clave, r in ref.items()
                      if clave[1] in datos.get(clave[0], {})
                      and all(datos[clave[0]][clave[1]][c] == r[c] for c in cols))
        partes.append((iguales, len(ref), len(cols)))
    distintos = sum(len(c) for c in datos.values())
    (i1, n1, c1), (i2, n2, c2) = partes
    esperada = (f"CONTROL bit a bit (correr_episodio_R, semillas 420000–420099): {distintos} "
                f"episodios distintos; {i1}/{n1} filas idénticas en las {c1} columnas de "
                f"experimento_Q_completo.csv (S1) y {i2}/{n2} en las {c2} de "
                f"experimento_Q_EXPLORATORIO_S2_S3.csv (S2, S3); todas salvo t_episodio_s y "
                f"exploratorio; texto idéntico, repr de cada float")
    if esperada not in texto:
        dif.append(f"VERIFICACIÓN: control_bit_a_bit_R.txt no tiene la línea recalculada «{esperada}»")
    dif += cifras_autochequeos(texto, filas_r, "control_bit_a_bit_R.txt")
    n_traz = sum(1 for c, fs in datos.items() for f in fs.values()
                 if requiere_traza(c.split("_", 1)[1], f))
    if not any(x.startswith(f"TRAZAS: {n_traz} episodios con traza") for x in texto):
        dif.append(f"VERIFICACIÓN: control_bit_a_bit_R.txt no dice «TRAZAS: {n_traz} episodios "
                   f"con traza»")
    return dif


def autochequeos_fila(f: Fila) -> List[str]:
    """Los autochequeos del §3.3 de UNA fila (toda fila, con o sin traza, ctrl incluido)."""
    ap = int(f["pasos"]) * N_AGENTES
    fallas = []
    if int(f["pasos_agente_fallback"]) != int(float(f["qp_fallbacks"])):
        fallas.append("pasos_agente_fallback ≠ qp_fallbacks")
    if (min(float(f["d_min_sin_fallback"]), float(f["d_min_en_fallback"]))
            != float(f["d_min_obst_superficie"])):
        fallas.append("mín(sin, en fallback) ≠ d_min_obst_superficie")
    if int(f["fb_desplazado"]) != 0:
        fallas.append("fb_desplazado ≠ 0")
    if int(f["xy_discontinuo"]) != 0:
        fallas.append("xy_discontinuo ≠ 0")
    if int(f["contactos_registrados"]) != int(float(f["contactos_obst_eventos"])):
        fallas.append("contactos_registrados ≠ contactos_obst_eventos")
    if repr(int(f["pasos_agente_intervino"]) / ap) != f["cbf_frac_interv"]:
        fallas.append("pasos_agente_intervino/(pasos·n_a) ≠ cbf_frac_interv (texto)")
    if int(f["pasos_agente_escape_intervino"]) != int(float(f["escape_filtro_modifico"])):
        fallas.append("escape∧intervino ≠ escape_filtro_modifico")
    return fallas


def autochequeos_corrida(filas: Sequence[Fila]) -> Tuple[int, int, int, int]:
    """(problemas, Σ fb_desplazado_corrido, filas con fallback, de ellas con corrido 0)."""
    problemas = corrido = con_fb = cero = 0
    for f in filas:
        problemas += len(autochequeos_fila(f))
        if int(float(f["qp_fallbacks"])) > 0:
            con_fb += 1
            corrido += int(f["fb_desplazado_corrido"])
            cero += int(int(f["fb_desplazado_corrido"]) == 0)
    return problemas, corrido, con_fb, cero


def cifras_autochequeos(texto: Sequence[str], filas: Sequence[Fila], nombre: str) -> List[str]:
    """Las líneas AUTOCHEQUEOS y «la prueba física», recalculadas desde las filas (§3.3)."""
    problemas, corrido, con_fb, cero = autochequeos_corrida(filas)
    dif = []
    a = (f"AUTOCHEQUEOS de la Parte B en {len(filas)} filas: pasos_agente_fallback = "
         f"qp_fallbacks; mín(d_min_sin_fallback, d_min_en_fallback) = d_min_obst_superficie; "
         f"contactos_registrados = contactos_obst_eventos; intervención y escape∧intervino = los "
         f"contadores de Q; continuidad de las posiciones; fb_desplazado = 0 (prueba física del "
         f"pareo) → {problemas} problemas")
    b = (f"la prueba física discrimina: con la bandera corrida un paso, {corrido} agente-pasos "
         f"en fallback se mueven sin contacto, en {con_fb} episodios con fallback ({cero} de "
         f"ellos con 0, descriptivo)")
    for esperada in (a, b):
        if esperada not in texto:
            dif.append(f"VERIFICACIÓN: {nombre} no tiene la línea recalculada «{esperada}»")
    return dif


def verificar_seccion_verificacion(actual: Sequence[str], dir_registros: Path, datos: Datos,
                                   ruta_control_csv: Path, rutas_q: Sequence[Path],
                                   dir_trazas: Path) -> List[str]:
    """
    Cada línea «  <registro>: <x>» tiene que ser copia exacta de una línea de su
    registro, en el orden del registro y de REGISTROS. No puede faltar ninguna
    del bloque de inicio y de fin ni ninguna REQUERIDA, y no se cuela ninguna
    línea de resultados por celda. Además se recalculan las cifras que salen
    del crudo.
    """
    dif: List[str] = []
    contenido: Dict[str, List[str]] = {}
    for nombre in REGISTROS:
        ruta = dir_registros / nombre
        if not ruta.exists():
            dif.append(f"VERIFICACIÓN: falta el registro {nombre}")
            contenido[nombre] = []
        else:
            contenido[nombre] = [x.strip() for x in ruta.read_text(encoding="utf-8").splitlines()]
            if not any(contenido[nombre]):
                dif.append(f"VERIFICACIÓN: el registro {nombre} está vacío")
    vistas: Dict[str, List[str]] = {n: [] for n in REGISTROS}
    pos = {n: 0 for n in REGISTROS}
    orden_actual = -1
    for x in actual:
        m = re.match(r"^  (\S+?\.txt): (.*)$", x)
        if not m or m.group(1) not in REGISTROS:
            dif.append(f"VERIFICACIÓN: línea no reconocida «{x}»")
            continue
        nombre, linea = m.groups()
        j = REGISTROS.index(nombre)
        if j < orden_actual:
            dif.append(f"VERIFICACIÓN: {nombre} fuera de orden")
        orden_actual = j
        try:
            k = contenido[nombre].index(linea, pos[nombre])
        except ValueError:
            dif.append(f"VERIFICACIÓN: «{linea}» no está en {nombre} (o está fuera de orden)")
            continue
        pos[nombre] = k + 1
        vistas[nombre].append(linea)
        if nombre == "registro_R.txt" and _RE_RESULTADO_CELDA.match(linea):
            dif.append(f"VERIFICACIÓN: se coló una línea de resultados «{linea}»")
    for nombre in REGISTROS:
        lineas = contenido[nombre]
        indices = {j for j, x in enumerate(lineas) if x.startswith(REQUERIDAS[nombre])}
        if nombre != "comparar_ast_R.txt":
            bloque = bloque_inicio_fin(lineas)
            if lineas and not bloque:
                dif.append(f"VERIFICACIÓN: {nombre} no tiene el bloque de inicio y de fin")
            indices |= set(bloque)
        # Con multiplicidad: una línea que se repite en el registro (la energía al
        # empezar y al terminar) tiene que estar las dos veces.
        faltan = Counter(lineas[j] for j in indices if lineas[j]) - Counter(vistas[nombre])
        dif += [f"VERIFICACIÓN: falta en el resumen «{nombre}: {x}» ({n} vez/veces)"
                for x, n in faltan.items()]
    # Firmas y veredictos que no pueden ser otros.
    reg = contenido["registro_R.txt"]
    ctl = contenido["control_bit_a_bit_R.txt"]
    pas = contenido["pasabilidad_R.txt"]
    ast = contenido["comparar_ast_R.txt"]
    for nombre, lineas, exigidas in (
            ("comparar_ast_R.txt", ast, [f"HUELLA_R {HUELLA_R}"]),
            ("control_bit_a_bit_R.txt", ctl, ["CONTROL: OK", f"HUELLA_Q {HUELLA_Q}",
                                              f"HUELLA_R {HUELLA_R}"]),
            ("pasabilidad_R.txt", pas, ["PASABILIDAD: OK", f"HUELLA_Q {HUELLA_Q}",
                                        linea_semillas(SEMILLAS_R)]),
            ("registro_R.txt", reg, [f"HUELLA_Q {HUELLA_Q}", f"HUELLA_R {HUELLA_R}"])):
        dif += [f"VERIFICACIÓN: {nombre} no tiene «{x}»" for x in exigidas
                if lineas and x not in lineas]
    # Cifras recalculadas desde el crudo.
    filas = [f for c in datos.values() for f in c.values()]
    distintas = len({(f["condicion"], f["seed_ep"]) for f in filas})
    if reg and f"FILAS: {len(filas)} ({distintas} distintas; esperadas {12 * len(SEMILLAS_R)})" not in reg:
        dif.append("VERIFICACIÓN: la línea FILAS de registro_R.txt no coincide con el CSV")
    if reg:
        dif += cifras_autochequeos(reg, filas, "registro_R.txt")
        n_traz = sum(1 for c, fs in datos.items() for f in fs.values()
                     if requiere_traza(c.split("_", 1)[1], f))
        if f"TRAZAS: {n_traz} episodios con traza; biyección y tamaño → 0 problemas" not in reg:
            dif.append(f"VERIFICACIÓN: registro_R.txt no dice «TRAZAS: {n_traz} episodios con "
                       f"traza; biyección y tamaño → 0 problemas»")
    if ctl:
        dif += cifras_registro_control(ctl, ruta_control_csv, rutas_q, dir_trazas)
    return dif


def linea_semillas(sem: Sequence[int]) -> str:
    h = hashlib.sha256(",".join(str(s) for s in sem).encode("utf-8")).hexdigest()
    return f"SEMILLAS_R {h} {sem[0]}-{sem[-1]} n {len(sem)}"


# =============================================================================
# CONTRASTE CON SCIPY (a 10 decimales)
# =============================================================================

def contraste_scipy(pares_mcnemar: Set[Tuple[int, int]]) -> Tuple[List[str], int, float]:
    """(diferencias, valores contrastados, máx |Δ|); sin scipy, una diferencia."""
    try:
        from scipy.stats import beta, binomtest
    except ImportError:
        return ["CONTRASTE: scipy no está instalado; no se contrastó"], 0, 0.0
    dif, n_val, maximo = [], 0, 0.0
    for (k, n), (lo, hi) in sorted(_CACHE_CP.items()):
        lo_s = 0.0 if k == 0 else float(beta.ppf(ALFA / 2, k, n - k + 1))
        hi_s = 1.0 if k == n else float(beta.ppf(1 - ALFA / 2, k + 1, n - k))
        for propio, ref in ((lo, lo_s), (hi, hi_s)):
            n_val += 1
            maximo = max(maximo, abs(propio - ref))
            if abs(propio - ref) >= TOL_SCIPY:
                dif.append(f"CONTRASTE: Clopper-Pearson {k}/{n}: propio {propio!r}, scipy {ref!r}")
    for b, c in sorted(pares_mcnemar):
        ref = 1.0 if b + c == 0 else float(binomtest(min(b, c), b + c, 0.5).pvalue)
        propio = mcnemar(b, c)
        n_val += 1
        maximo = max(maximo, abs(propio - ref))
        if abs(propio - ref) >= TOL_SCIPY:
            dif.append(f"CONTRASTE: McNemar {b}/{c}: propio {propio!r}, scipy {ref!r}")
    return dif, n_val, maximo


# =============================================================================
# VERIFICACIÓN COMPLETA
# =============================================================================

MODOS: Dict[str, Tuple[str, str, str]] = {
    # modo: (resumen, prefijo de trazas, sufijo de figuras)
    "prueba-sustituto": ("resumen_R_prueba_sobre_Q.txt", "", "_PRUEBA_sobre_Q"),
    "prueba-control": ("resumen_R_prueba_sobre_control.txt", "controlR", "_PRUEBA_sobre_control"),
    "resultado": ("resumen_R.txt", "R", ""),
}


def verificar(modo: str, *, ruta_resumen: Optional[Path] = None,
              rutas_csv: Optional[Sequence[Path]] = None, dir_trazas: Path = DIR_TRAZAS,
              dir_registros: Path = DIR_RES, ruta_prereg: Path = RUTA_PREREG,
              ruta_adenda: Path = RUTA_ADENDA, dir_fig: Path = DIR_FIG,
              ruta_control_csv: Path = RUTA_CONTROL_CSV,
              rutas_q: Sequence[Path] = (RUTA_CSV_Q_S1, RUTA_CSV_EXPL_Q),
              contrastar: bool = True, semillas_resultado: Sequence[int] = SEMILLAS_R
              ) -> Tuple[List[str], Dict[str, object]]:
    """(diferencias, cuentas). Sin diferencias, el resumen está verificado."""
    nombre_res, prefijo, sufijo = MODOS[modo]
    ruta_resumen = ruta_resumen or DIR_RES / nombre_res
    if rutas_csv is None:
        rutas_csv = {"prueba-sustituto": list(rutas_q), "prueba-control": [ruta_control_csv],
                     "resultado": [RUTA_CSV_R]}[modo]
    dif: List[str] = []
    cuenta: Dict[str, object] = {}
    _CACHE_CP.clear()
    # Fijos.
    if hashlib.sha256(ruta_prereg.read_bytes()).hexdigest() != SHA256_PREREG:
        dif.append("FIJOS: PREREGISTRO_R.md no es el fijado (sha256 distinto)")
    if not ruta_adenda.exists() or hashlib.sha256(ruta_adenda.read_bytes()).hexdigest() != SHA256_ADENDA:
        dif.append("FIJOS: la adenda 1 no está o no es la fijada (sha256 distinto)")
    datos, columnas = cargar(rutas_csv, dif)
    celdas = [f"{k}_{t}" for k in NIVELES for t in TIPOS]
    faltan = [c for c in celdas if c not in datos]
    if faltan:
        return dif + [f"DATOS: faltan las celdas {faltan}"], cuenta
    conjuntos = {c: frozenset(datos[c]) for c in celdas}
    if len(set(conjuntos.values())) != 1:
        return dif + ["DATOS: las 12 celdas no tienen las mismas semillas"], cuenta
    sem = sorted(next(iter(conjuntos.values())))
    filas = [f for c in datos.values() for f in c.values()]
    if modo == "resultado":
        if sem != list(semillas_resultado):
            dif.append("FIJOS: las semillas no son las del prerregistro")
        if len(filas) != 12 * len(semillas_resultado):
            dif.append(f"FIJOS: {len(filas)} filas, no {12 * len(semillas_resultado)}")
        if any(f.get("prerregistrado") != "1" for f in filas):
            dif.append("FIJOS: hay filas sin prerregistrado = 1")
    cuenta["filas"] = len(filas)
    # Parte B.
    registros_pb = {"prueba-sustituto": [],
                    "prueba-control": [dir_registros / "control_bit_a_bit_R.txt"],
                    "resultado": [dir_registros / "control_bit_a_bit_R.txt",
                                  dir_registros / "registro_R.txt"]}[modo]
    motivo = motivo_parte_b(registros_pb)
    if motivo is None and not all(c in columnas for c in COLUMNAS_H6):
        motivo = "no evaluable: faltan las columnas de la Parte B"
        if modo != "prueba-sustituto":
            # §2.4: sólo «PARTE B: NO» vuelve H6 no evaluable; un CSV de R sin las
            # columnas, con registros en OK, es una falla.
            dif.append("FIJOS: el CSV no tiene las columnas de la Parte B")
    pb = None
    if motivo is None and all(c in columnas for c in COLUMNAS_PARTE_B):
        # §3.3: los autochequeos de cada fila y el agregado de la corrida (con
        # «PARTE B: NO» ya declarado, sus fallas son las que el registro lista).
        for f in filas:
            dif += [f"AUTOCHEQUEO: {f['condicion']}/{f['seed_ep']}: {x}"
                    for x in autochequeos_fila(f)]
        _p, corrido, con_fb, _c = autochequeos_corrida(filas)
        if con_fb and corrido == 0:
            dif.append("AUTOCHEQUEO: la prueba física no discrimina (Σ fb_desplazado_corrido = 0)")
    if all(c in columnas for c in COLUMNAS_H6):
        pb = parte_b_recalculada(datos, prefijo, dir_trazas, dif, cuenta,
                                 exigir_trazas=motivo is None)
    con_trazas = modo != "prueba-sustituto"
    # El resumen esperado.
    E: List[str] = []
    if modo == "resultado":
        E.append("EXPERIMENTO R — réplica prerregistrada de los obstáculos móviles (S1–S3, "
                 "semillas nuevas) — RESULTADO")
    else:
        E.append(AVISO_PRUEBA)
        fuente = ("experimento_Q_completo.csv + experimento_Q_EXPLORATORIO_S2_S3.csv"
                  if modo == "prueba-sustituto" else "control_bit_a_bit_R.csv")
        E.append(f"  (modo {modo}: {fuente})")
    E += ["ENCUADRE: no prueba adaptabilidad de la política (la observación no codifica "
          "obstáculos); prueba la generalidad de la capa de seguridad y su costo, con "
          "semillas de episodio que no generaron las hipótesis.", ""]
    E += lineas_prerregistro(sem, ruta_prereg) + [""]
    crudo = ruta_resumen.read_bytes()
    if b"\r" in crudo:
        dif.append("RESUMEN: tiene CR; el análisis escribe LF")
    texto = crudo.decode("utf-8")
    if not texto.endswith("\n"):
        dif.append("RESUMEN: no termina en un salto de línea")
    A = texto.split("\n")[:-1] if texto.endswith("\n") else texto.split("\n")
    if modo == "resultado":
        cab = "VERIFICACIÓN (de los registros de la corrida)"
        E.append(cab)
        i = A.index(cab) if cab in A else -1
        sec: List[str] = []
        if i >= 0:
            j = i + 1
            while j < len(A) and A[j] != "":
                sec.append(A[j])
                j += 1
        else:
            dif.append("RESUMEN: falta la sección VERIFICACIÓN")
        dif += verificar_seccion_verificacion(sec, dir_registros, datos, ruta_control_csv,
                                              rutas_q, dir_trazas)
        E += sec  # cotejada aparte, línea por línea, contra los registros
    else:
        E.append("VERIFICACIÓN — no aplica (prueba del análisis sobre datos vistos)")
    E.append("")
    lh, V, res = lineas_hipotesis(datos, sem, pb, motivo, prefijo, con_trazas, dir_trazas)
    E += lh + [""] + lineas_holm(res, V) + [""]
    E += lineas_eventos(datos, sem) + [""] + lineas_costo(datos, sem) + [""]
    E += lineas_intervencion(datos, sem)
    if modo == "resultado":
        dv: List[str] = []
        vistos, cols_v = cargar([ruta_control_csv], dv)
        dif += [f"VISTOS: {x}" for x in dv]
        pb_v = parte_b_recalculada(vistos, "controlR", dir_trazas, dif, {})
        E += [""] + lineas_diagnostico(vistos, pb_v)
    E += ["", "LO QUE R NO SUSTENTA (el §6 del prerregistro, escrito antes de correr):"]
    E += no_sustenta(ruta_prereg)
    evaluable = motivo is None
    figs = figuras_esperadas(modo, sufijo, evaluable, datos, sem)
    E += ["", "FIGURAS: " + ", ".join(figs)]
    dif += [f"FIGURAS: falta {x}" for x in figs if not (dir_fig / x).exists()]
    # Texto contra texto, línea por línea.
    if A != E:
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=E, b=A, autojunk=False).get_opcodes():
            if op == "equal":
                continue
            for k in range(max(i2 - i1, j2 - j1)):
                esp = E[i1 + k] if i1 + k < i2 else "(no se espera ninguna línea)"
                act = A[j1 + k] if j1 + k < j2 else "(falta en el resumen)"
                dif.append(f"RESUMEN línea {j1 + k + 1}: esperado «{esp}» | resumen «{act}»")
    cuenta["lineas_resumen"] = len(A)
    cuenta["lineas_esperadas"] = len(E)
    cuenta["veredictos"] = dict(V)
    # Contraste con scipy.
    if contrastar:
        pares = {(r[2], r[3]) for r in res.values()}
        for k in NIVELES:
            pares.add(mcnemar_celdas(datos, sem, "infactible activo", k, "din", "quieto")[2:4])
            pares.add(mcnemar_celdas(datos, sem, "fallback", k, "din", "quieto")[2:4])
            pares.add(mcnemar_celdas(datos, sem, "bajo 0,13 m", k, "sinvel", "din")[2:4])
        d_s, n_s, maximo = contraste_scipy(pares)
        dif += d_s
        cuenta["contrastes_scipy"] = n_s
        cuenta["max_dif_scipy"] = maximo
    cuenta["sha256_resumen"] = hashlib.sha256(ruta_resumen.read_bytes()).hexdigest()
    cuenta["sha256_csv"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in rutas_csv}
    return dif, cuenta


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    modo = {"": "resultado", "--prueba-sustituto": "prueba-sustituto",
            "--prueba-control": "prueba-control"}.get(arg)
    if modo is None or len(sys.argv) > 2:
        print("uso: python -B verificar_cifras_R.py [--prueba-sustituto | --prueba-control]")
        return 2
    dif, cuenta = verificar(modo)
    print(f"verificar_cifras_R.py — modo {modo}")
    print(f"  resumen: {MODOS[modo][0]} (sha256 {cuenta.get('sha256_resumen', '?')})")
    for nombre, h in dict(cuenta.get("sha256_csv", {})).items():
        print(f"  CSV: {nombre} (sha256 {h})")
    print(f"  filas: {cuenta.get('filas')}; líneas del resumen: {cuenta.get('lineas_resumen')}; "
          f"líneas esperadas: {cuenta.get('lineas_esperadas')}")
    print(f"  Parte B: {cuenta.get('filas_con_traza', 0)} filas recalculadas desde su traza, "
          f"{cuenta.get('filas_por_identidad', 0)} por identidad (sin fallback)")
    print(f"  contraste con scipy: {cuenta.get('contrastes_scipy', 0)} valores, máx |Δ| = "
          f"{cuenta.get('max_dif_scipy', 0.0):.3e}")
    for k, v in dict(cuenta.get("veredictos", {})).items():
        print(f"  veredicto {k}: {v}")
    if dif:
        print(f"DIFERENCIAS: {len(dif)}")
        for x in dif:
            print("  " + x)
        return 1
    print("TODO COINCIDE: cada línea del resumen es la recalculada, texto contra texto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
