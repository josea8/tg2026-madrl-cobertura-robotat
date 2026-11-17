"""
verificar_cifras_exploratorio_Q.py
==================================
EXPLORATORIO — fuera de la regla de parada. Verificador de lo exploratorio
del Exp Q (S2 y S3), con la misma lógica que `verificar_cifras_Q.py`: código
propio (csv + math; numpy sólo para regenerar las fases con su generador)
que recalcula desde los CSV CRUDOS cada cifra de:

  A. `resultados/resumen_Q_EXPLORATORIO.txt`: tablas, comparaciones,
     criterios, ATRIBUCIÓN POR SEMILLA, HIPÓTESIS DEL ENCIERRO, indicador,
     seguridad, mecanismo, parte de ω y registro, con COMPLETITUD (S2 y S3
     completos, sin ninguna línea de parada) y ninguna línea con cifras sin
     reconocer;
  B. la subsección de la bitácora (`ENTRADA_BITACORA_expQ_EXPLORATORIO.md`):
     cada cifra recalculada y presente tal cual en el texto;
  C. lo que no puede cambiar ni faltar: la reproducción de S1_din (texto
     idéntico, de nuevo), el sha256 de los tres archivos de S1, la huella de
     `registro_Q_EXPLORATORIO.txt`, EXPLORATORIO en la primera línea de los
     textos y `exploratorio` = 1 en cada fila de los CSV, y el pareo.

No recalcula los segundos de pared de la reproducción (son una medición de la
corrida, no un dato).

    python -B verificar_cifras_exploratorio_Q.py

Termina con 0 si todo coincide y con 1 si no.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import hashlib
import math
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

from verificar_cifras_Q import (COBERTURAS, COMUNES, CRIT, DISENO_COMP, ETIQUETAS,
                                MECANISMO, MINIMOS, PARES_MECANISMO, TIPOS, Contador,
                                _RE_COMP, _RE_FILA_COMP, _RE_IND, _RE_MEC, _RE_OMEGA,
                                _RE_REL, _RE_SEG, _RE_TABLA, _huella_propia, cargar, col,
                                f8, fases_regeneradas, ic95, media)

DIR_RES: Path = _CARPETA / "resultados"
RUTA_CSV_EXPL: Path = DIR_RES / "experimento_Q_EXPLORATORIO_S2_S3.csv"
RUTA_REPRO: Path = DIR_RES / "reproduccion_S1_din_EXPLORATORIO.csv"
RUTA_REG_EXPL: Path = DIR_RES / "registro_Q_EXPLORATORIO.txt"
RUTA_RES_EXPL: Path = DIR_RES / "resumen_Q_EXPLORATORIO.txt"
RUTA_LOG_EXPL: Path = DIR_RES / "corrida_Q_EXPLORATORIO.log"
RUTA_CSV_S1: Path = DIR_RES / "experimento_Q_completo.csv"
RUTA_SUBSECCION: Path = _CARPETA / "ENTRADA_BITACORA_expQ_EXPLORATORIO.md"
NIVELES_EXPL: Tuple[str, ...] = ("S2", "S3")
#: Copia propia de lo comprometido el 19-10.
HUELLA_S1: str = "e265b6cd31e8d443977027b1bf1d4671c002b06c3ecbdc45a275521e49c24a29"
SHA256_S1: Dict[str, str] = {
    "resultados/registro_Q.txt":
        "ff553e66d06420ff1f7abcabb9f03070885f96be8b8856850c3a5dd249d8673a",
    "resultados/experimento_Q_completo.csv":
        "341562959d02b113e1585590425bc4f51918cb3d4ff6e944f46dc616a08d5dbf",
    "resultados/resumen_experimento_Q.txt":
        "f5f69c4ea9b667d5e4e62b91e25fd1087f09320c7f15f04e529293eaff672a43",
}
#: Etiquetas de los criterios en el resumen → columna.
CRIT_ETIQ: Dict[str, str] = {"contactos obst.": "contactos_obst_eventos",
                             "escapes agotados": "escape_agotados",
                             "fallbacks QP": "qp_fallbacks",
                             "infactibles junto a obst.": "escape_infactibles_junto_obst"}
SOLO_CON_OBSTACULO: Tuple[str, ...] = ("contactos_obst_eventos",
                                       "escape_infactibles_junto_obst")
ENCIERRO: Tuple[Tuple[str, str], ...] = (
    ("qp_fallbacks", "fallbacks del QP"),
    ("f1_filas_saturadas", "filas F1 saturadas"),
    ("escape_infact_op_con_obst", "infactibles opuestas con obstáculo activo"),
)
REGLA_EXPO: Tuple[str, ...] = ("contacto con obstáculo", "escape agotado",
                               "fallback del QP", "escape infactible con obstáculo activo")
PREFIJOS_SIN_CIFRAS: Tuple[str, ...] = (
    "NO cambian el veredicto", "Mismo análisis que S1", "la fila F1 (k = 1)", "100 semillas",
    "ESTADÍSTICA:", "'*' si el IC", "H MÍNIMO",
    "con h_eq", "  métrica", "  indirecta =", "  contra el control)", "  Δ periferia =",
    "PARTE DE ω", "MECANISMO —", "del Exp O (en Sk_din", "restricción ligante", "INDICADOR",
    "  COPIAS del Exp O", "  procesos:", "  HUELLA", "  RESULTADOS DE S1",
    "CRITERIOS DE FALLA", "ATRIBUCIÓN POR SEMILLA", "el mismo evento en Sk_ctrl",
    "exige un obstáculo físico", "HIPÓTESIS DEL ENCIERRO", "infactibles por normales",
    "EVENTOS RAROS", "Clopper-Pearson; contra el control", "PRUEBA EXACTA PAREADA",
    "FALLBACK Y DISTANCIA", "0,10 m, separando",
)
#: EVENTOS RAROS (24-10), copia propia: (nombre, columna, ¿exige obstáculo físico?).
EVENTOS_X: Tuple[Tuple[str, str, bool], ...] = (
    ("contacto", "contactos_obst_eventos", True),
    ("fallback", "qp_fallbacks", False),
    ("agotado", "escape_agotados", False),
    ("infactible con obst. activo", "escape_infactibles_junto_obst", True),
    ("bajo 0,13 m", "viol_cota_obst_agente_eps", True),
)
PARES_MCN: Tuple[Tuple[str, str], ...] = (("din", "quieto"), ("din", "ctrl"), ("sinvel", "din"))
_RE_RARO = re.compile(r"^  (S\d)_(ctrl|quieto|din|sinvel): (contacto .*)$")
_RE_RARO_ITEM = re.compile(r"^(.+?) (?:(\d+)/(\d+) \[(\d\.\d{4}), (\d\.\d{4})\]|(no aplica))$")
_RE_MCN = re.compile(r"^  (S\d) (contacto|fallback|agotado|infactible con obst\. activo|"
                     r"bajo 0,13 m): (din−quieto .*)$")
_RE_MCN_ITEM = re.compile(r"^(\w+)−(\w+) (?:(\d+)/(\d+) p (< 0\.0001|\d\.\d{4})|(no aplica))$")
_RE_FBD = re.compile(r"^  (S\d_(?:din|quieto|sinvel)): todos d_min (\d\.\d{8}|—), bajo 0,10 m "
                     r"(\d+)/(\d+); con fallback (\d+) episodios, d_min (\d\.\d{8}|—), bajo 0,10 m "
                     r"(\d+); sin fallback (\d+) episodios, d_min (\d\.\d{8}|—), bajo 0,10 m (\d+)$")


# =============================================================================
# ESTADÍSTICA EXACTA PROPIA (sin scipy)
# =============================================================================

def _pmf(i: int, n: int, p: float) -> float:
    return math.comb(n, i) * p ** i * (1.0 - p) ** (n - i)


def cola_inferior(k: int, n: int, p: float) -> float:
    """P(X ≤ k), X ~ Bin(n, p)."""
    return math.fsum(_pmf(i, n, p) for i in range(k + 1))


def cola_superior(k: int, n: int, p: float) -> float:
    """P(X ≥ k), X ~ Bin(n, p)."""
    return math.fsum(_pmf(i, n, p) for i in range(k, n + 1))


def _biseccion(f: Callable[[float], float], objetivo: float, creciente: bool) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(200):
        medio = 0.5 * (lo + hi)
        if (f(medio) < objetivo) == creciente:
            lo = medio
        else:
            hi = medio
    return 0.5 * (lo + hi)


def clopper_pearson_propio(k: int, n: int, alfa: float = 0.05) -> Tuple[float, float]:
    """IC de Clopper-Pearson invirtiendo las colas binomiales exactas (bisección)."""
    lo = 0.0 if k == 0 else _biseccion(lambda p: cola_superior(k, n, p), alfa / 2, True)
    hi = 1.0 if k == n else _biseccion(lambda p: cola_inferior(k, n, p), alfa / 2, False)
    return lo, hi


def mcnemar_propia(a: Set[int], b: Set[int]) -> Tuple[int, int, float]:
    """McNemar exacta bilateral: 2·P(X ≤ min(b, c)), X ~ Bin(b + c, 1/2), tope 1."""
    sa, sb = len(a - b), len(b - a)
    n = sa + sb
    if n == 0:
        return sa, sb, 1.0
    cola = sum(math.comb(n, i) for i in range(min(sa, sb) + 1))
    return sa, sb, min(1.0, 2 * cola / 2 ** n)


def formato_p(p: float) -> str:
    return "< 0.0001" if p < 0.0001 else f"{p:.4f}"


def episodios_con(datos, c: str, m: str, sem) -> Set[int]:
    return {s for s in sem if float(datos[c][s][m]) > 0}

_RE_CRIT_X = re.compile(r"^  (S\d_\w+)( \(decidiría\))?: contactos obst\. (\d+); escapes "
                        r"agotados (\d+); fallbacks QP (\d+); infactibles junto a obst\. (\d+)$")
_RE_AT_NINGUNA = re.compile(r"^  (S\d) (.+): ninguna semilla en (S\d)_din$")
_RE_AT_CABEZA = re.compile(r"^  (S\d) (.+): (\d+) semillas en (S\d)_din; con el mismo evento: "
                           r"ctrl (\d+|no aplica), quieto (\d+), sinvel (\d+)$")
_RE_AT_SEMILLA = re.compile(r"^    (\d+): (S\d)_din (\d+); ctrl (sí|no|no aplica); quieto (sí|no); "
                            r"sinvel (sí|no)$")
_RE_ENC = re.compile(r"^  (S\d_\w+): fallbacks del QP (\d+) en (\d+)/(\d+) episodios \(semillas: "
                     r"([^)]*)\); filas F1 saturadas (\d+) en (\d+)/(\d+) episodios \(semillas: "
                     r"([^)]*)\); infactibles opuestas con obstáculo activo (\d+) en (\d+)/(\d+) "
                     r"episodios \(semillas: ([^)]*)\)$")
_RE_REG_NIVEL_X = re.compile(r"^  (S\d_\w+) \(exploratorio\): intervención media (\d+\.\d+) "
                             r"\((sobre|bajo) el indicador 0\.5\); criterios — contacto con "
                             r"obstáculo (\d+); escape agotado (\d+); fallback del QP (\d+); "
                             r"escape infactible con obstáculo activo (\d+)$")
_RE_REG_REGLA = re.compile(r"^  (S\d): con la regla, (S\d)_din (la dispararía|no la dispararía); "
                           r"exploratorio: se sigue igual\.$")
_RE_REG_HUELLA = re.compile(r"^  huella del código: ([0-9a-f]{64}) \(la de S1\)$")
_RE_REG_REPRO = re.compile(r"^  REPRODUCCIÓN de S1_din sin parciales: (\d+)/(\d+) semillas "
                           r"idénticas en texto a experimento_Q_completo\.csv en las (\d+) "
                           r"columnas \(todas salvo t_episodio_s\), (\d+) s$")
_RE_REG_SHA = re.compile(r"^    IGUAL ([0-9a-f]{64}) (\S+)$")
_RE_REG_STACK = re.compile(r"^  STACK: (.*)$")


def sha256_de(rel: str) -> str:
    return hashlib.sha256((_CARPETA / rel).read_bytes()).hexdigest()


def comparar_reproduccion() -> Tuple[int, int, int]:
    """(iguales, filas de S1_din en el CSV de S1, columnas), por texto exacto."""
    ref = {s: r for s, r in cargar(RUTA_CSV_S1)["S1_din"].items()}
    rep = cargar(RUTA_REPRO).get("S1_din", {})
    cols = [c for c in next(iter(ref.values())) if c != "t_episodio_s"]
    iguales = sum(1 for s, r in ref.items()
                  if s in rep and all(rep[s][c] == r[c] for c in cols))
    return iguales, len(ref), len(cols)


def atribucion(datos, k: str, m: str, sem) -> List[Tuple[int, int, str, str, str]]:
    salida = []
    for s in sem:
        v = float(datos[f"{k}_din"][s][m])
        if v <= 0:
            continue

        def mismo(t: str) -> str:
            if t == "ctrl" and m in SOLO_CON_OBSTACULO:
                return "no aplica"
            return "sí" if float(datos[f"{k}_{t}"][s][m]) > 0 else "no"
        salida.append((s, int(v), mismo("ctrl"), mismo("quieto"), mismo("sinvel")))
    return salida


def _lista(xs: Sequence[int]) -> str:
    return ", ".join(str(x) for x in xs) if xs else "ninguna"


def esperado(datos, sem) -> Set[Tuple[str, ...]]:
    niveles = [k for k in NIVELES_EXPL if f"{k}_din" in datos]
    E: Set[Tuple[str, ...]] = {("reg_huella",), ("reg_repro",), ("reg_stack",)}
    E |= {("reg_sha", rel) for rel in SHA256_S1}
    for k in niveles:
        E |= {("tabla", k, e) for e in list(ETIQUETAS) + list(MINIMOS)}
        for (a, b), cobs in DISENO_COMP.items():
            E |= {("comp", f"{k}_{a}", f"{k}_{b}", COBERTURAS[c]) for c in cobs}
            E |= {("comp", f"{k}_{a}", f"{k}_{b}", e) for e in COMUNES.values()}
            E.add(("rel", f"{k}_{a}", f"{k}_{b}", cobs[0]))
            E.add(("titulo", f"{k}_{a}", f"{k}_{b}"))
        for t in ("din", "quieto", "sinvel"):
            E |= {("crit", f"{k}_{t}"), ("seg", f"{k}_{t}"), ("omega", f"{k}_{t}"),
                  ("reg_nivel", f"{k}_{t}"), ("enc", f"{k}_{t}"), ("fbd", f"{k}_{t}")}
        E |= {("ind", f"{k}_{t}") for t in TIPOS}
        E |= {("raro", f"{k}_{t}") for t in TIPOS}
        E |= {("mcn", k, nombre) for nombre, _m, _f in EVENTOS_X}
        E |= {("mec", base, f"{k}_{a}", f"{k}_{b}") for base in MECANISMO
              for a, b in PARES_MECANISMO}
        E.add(("reg_regla", k))
        for e, m in CRIT_ETIQ.items():
            E.add(("at", k, e))
            E |= {("at_s", k, e, s) for s, *_ in atribucion(datos, k, m, sem)}
    return E


def verificar_resumen(datos, cuenta: Contador) -> List[str]:
    sem = sorted(next(iter(datos.values())).keys())
    lineas = RUTA_RES_EXPL.read_text(encoding="utf-8").splitlines()
    cuenta.exigir("resumen: EXPLORATORIO en la primera línea", lineas[0].startswith("EXPLORATORIO —"))
    sin_verificar: List[str] = []
    vistos: List[Tuple[str, ...]] = []
    seccion: Optional[Tuple[str, ...]] = None
    conds: List[str] = []
    at_actual: Optional[Tuple[str, str]] = None
    for i, linea in enumerate(lineas):
        if i == 0:
            continue
        reconocida = False
        if not linea.strip():
            seccion = None if seccion and seccion[0] in ("tabla", "comp") else seccion
            continue
        m = _RE_TABLA.match(linea)
        if m:
            seccion = ("tabla", m.group(1))
            conds = lineas[i + 1].split()[1:]
            cuenta.comparar(f"tabla {m.group(1)}: episodios", m.group(2), str(len(sem)))
            cuenta.comparar(f"tabla {m.group(1)}: columnas", " ".join(conds),
                            " ".join(f"{m.group(1)}_{t}" for t in TIPOS))
            continue
        m = _RE_COMP.match(linea)
        if m:
            seccion = ("comp", m.group(1), m.group(2))
            vistos.append(("titulo", m.group(1), m.group(2)))
            cuenta.comparar(f"comparación {m.group(1)} − {m.group(2)}: semillas",
                            m.group(3), str(len(sem)))
            continue
        etiqueta = linea[2:48].strip()
        if seccion and seccion[0] == "tabla" and (etiqueta in ETIQUETAS or etiqueta in MINIMOS):
            vistos.append(("tabla", seccion[1], etiqueta))
            valores = linea[48:].split()
            for c, impreso in zip(conds, valores):
                fuente = ETIQUETAS.get(etiqueta) or MINIMOS[etiqueta]
                v = [x for x in col(datos, c, fuente, sem) if math.isfinite(x)]
                f = media if etiqueta in ETIQUETAS else min
                calc = format(f(v), "14.8f") if v else format(float("nan"), "14.8f")
                cuenta.comparar(f"tabla {c} {etiqueta}", impreso, calc)
            reconocida = len(valores) == len(conds)
        elif seccion and seccion[0] == "comp" and etiqueta in ETIQUETAS and _RE_FILA_COMP.match(linea[48:]):
            mm = _RE_FILA_COMP.match(linea[48:])
            a, b = seccion[1], seccion[2]
            vistos.append(("comp", a, b, etiqueta))
            d = [x - y for x, y in zip(col(datos, a, ETIQUETAS[etiqueta], sem),
                                       col(datos, b, ETIQUETAS[etiqueta], sem))]
            me, lo, hi = ic95(d)
            desc = f"{a} − {b} {etiqueta}"
            for j, calc in ((1, f8(me, "+13")), (2, f8(lo, "+13")), (3, f8(hi, "+13")),
                            (4, "*" if lo * hi > 0 else " "), (5, str(sum(x > 0 for x in d))),
                            (6, str(sum(x < 0 for x in d)))):
                cuenta.comparar(f"{desc} ({j})", mm.group(j), calc)
            reconocida = True
        elif seccion and seccion[0] == "comp" and _RE_REL.match(linea):
            mm = _RE_REL.match(linea)
            a, b, c0 = seccion[1], seccion[2], mm.group(1)
            vistos.append(("rel", a, b, c0))
            me, lo, hi = ic95([x / y - 1 for x, y in zip(col(datos, a, c0, sem),
                                                         col(datos, b, c0, sem))])
            for j, v in ((2, me), (3, lo), (4, hi)):
                cuenta.comparar(f"{a} − {b} costo relativo ({j})", mm.group(j),
                                format(100 * v, "+.4f"))
            reconocida = True
        elif _RE_CRIT_X.match(linea):
            mm = _RE_CRIT_X.match(linea)
            c = mm.group(1)
            vistos.append(("crit", c))
            cuenta.comparar(f"criterio {c} (decidiría)", mm.group(2) or "",
                            " (decidiría)" if c.endswith("_din") else "")
            for j, m_ in enumerate(CRIT, 3):
                cuenta.comparar(f"criterio {c} {m_}", mm.group(j),
                                str(int(math.fsum(col(datos, c, m_, sem)))))
            reconocida = True
        elif _RE_AT_NINGUNA.match(linea):
            mm = _RE_AT_NINGUNA.match(linea)
            k, e = mm.group(1), mm.group(2)
            vistos.append(("at", k, e))
            cuenta.comparar(f"atribución {k} {e}: nivel", mm.group(3), k)
            cuenta.exigir(f"atribución {k} {e}: ninguna semilla",
                          not atribucion(datos, k, CRIT_ETIQ[e], sem))
            reconocida = True
        elif _RE_AT_CABEZA.match(linea):
            mm = _RE_AT_CABEZA.match(linea)
            k, e = mm.group(1), mm.group(2)
            vistos.append(("at", k, e))
            at_actual = (k, e)
            at = atribucion(datos, k, CRIT_ETIQ[e], sem)
            cuenta.comparar(f"atribución {k} {e}: semillas", mm.group(3), str(len(at)))
            cuenta.comparar(f"atribución {k} {e}: nivel", mm.group(4), k)
            cuenta.comparar(f"atribución {k} {e}: ctrl", mm.group(5),
                            "no aplica" if CRIT_ETIQ[e] in SOLO_CON_OBSTACULO
                            else str(sum(x[2] == "sí" for x in at)))
            cuenta.comparar(f"atribución {k} {e}: quieto", mm.group(6),
                            str(sum(x[3] == "sí" for x in at)))
            cuenta.comparar(f"atribución {k} {e}: sinvel", mm.group(7),
                            str(sum(x[4] == "sí" for x in at)))
            reconocida = True
        elif _RE_AT_SEMILLA.match(linea) and at_actual:
            mm = _RE_AT_SEMILLA.match(linea)
            k, e = at_actual
            s = int(mm.group(1))
            vistos.append(("at_s", k, e, s))
            fila = {x[0]: x for x in atribucion(datos, k, CRIT_ETIQ[e], sem)}.get(s)
            if fila is None:
                cuenta.exigir(f"atribución {k} {e} {s}: la semilla no tiene el evento", False)
            else:
                for j, calc in ((2, k), (3, str(fila[1])), (4, fila[2]), (5, fila[3]),
                                (6, fila[4])):
                    cuenta.comparar(f"atribución {k} {e} {s} ({j})", mm.group(j), calc)
            reconocida = True
        elif _RE_ENC.match(linea):
            mm = _RE_ENC.match(linea)
            c = mm.group(1)
            vistos.append(("enc", c))
            for j0, (m_, _e) in zip((2, 6, 10), ENCIERRO):
                ss = [s for s in sem if float(datos[c][s][m_]) > 0]
                cuenta.comparar(f"encierro {c} {m_} total", mm.group(j0),
                                str(int(math.fsum(col(datos, c, m_, sem)))))
                cuenta.comparar(f"encierro {c} {m_} episodios", mm.group(j0 + 1), str(len(ss)))
                cuenta.comparar(f"encierro {c} {m_} n", mm.group(j0 + 2), str(len(sem)))
                cuenta.comparar(f"encierro {c} {m_} semillas", mm.group(j0 + 3), _lista(ss))
            reconocida = True
        elif _RE_RARO.match(linea):
            mm = _RE_RARO.match(linea)
            c = f"{mm.group(1)}_{mm.group(2)}"
            vistos.append(("raro", c))
            items = mm.group(3).split("; ")
            cuenta.comparar(f"raros {c}: eventos", str(len(items)), str(len(EVENTOS_X)))
            for item, (nombre, m_, fisico) in zip(items, EVENTOS_X):
                mi = _RE_RARO_ITEM.match(item)
                if not mi:
                    cuenta.exigir(f"raros {c} {nombre}: formato {item!r}", False)
                    continue
                cuenta.comparar(f"raros {c} {nombre}: nombre", mi.group(1), nombre)
                if mm.group(2) == "ctrl" and fisico:
                    cuenta.comparar(f"raros {c} {nombre}", mi.group(6) or "(cifra)", "no aplica")
                    continue
                k_ev = len(episodios_con(datos, c, m_, sem))
                lo, hi = clopper_pearson_propio(k_ev, len(sem))
                for j, calc in ((2, str(k_ev)), (3, str(len(sem))), (4, f"{lo:.4f}"),
                                (5, f"{hi:.4f}")):
                    cuenta.comparar(f"raros {c} {nombre} ({j})", mi.group(j) or "(no aplica)", calc)
            reconocida = True
        elif _RE_MCN.match(linea):
            mm = _RE_MCN.match(linea)
            k, nombre = mm.group(1), mm.group(2)
            vistos.append(("mcn", k, nombre))
            m_, fisico = {n: (c_, f_) for n, c_, f_ in EVENTOS_X}[nombre]
            items = mm.group(3).split("; ")
            cuenta.comparar(f"mcnemar {k} {nombre}: pares", str(len(items)), str(len(PARES_MCN)))
            for item, (a, b) in zip(items, PARES_MCN):
                mi = _RE_MCN_ITEM.match(item)
                if not mi:
                    cuenta.exigir(f"mcnemar {k} {nombre}: formato {item!r}", False)
                    continue
                cuenta.comparar(f"mcnemar {k} {nombre}: par", f"{mi.group(1)}−{mi.group(2)}",
                                f"{a}−{b}")
                if b == "ctrl" and fisico:
                    cuenta.comparar(f"mcnemar {k} {nombre} {a}−{b}", mi.group(6) or "(cifra)",
                                    "no aplica")
                    continue
                sa, sb, p = mcnemar_propia(episodios_con(datos, f"{k}_{a}", m_, sem),
                                           episodios_con(datos, f"{k}_{b}", m_, sem))
                for j, calc in ((3, str(sa)), (4, str(sb)), (5, formato_p(p))):
                    cuenta.comparar(f"mcnemar {k} {nombre} {a}−{b} ({j})",
                                    mi.group(j) or "(no aplica)", calc)
            reconocida = True
        elif _RE_FBD.match(linea):
            mm = _RE_FBD.match(linea)
            c = mm.group(1)
            vistos.append(("fbd", c))
            con_fb = episodios_con(datos, c, "qp_fallbacks", sem)
            dmin = {s: float(datos[c][s]["d_min_obst_superficie"]) for s in sem}

            def resumen_fb(grupo) -> Tuple[str, str]:
                grupo = list(grupo)
                if not grupo:
                    return "—", "0"
                return (f"{min(dmin[s] for s in grupo):.8f}",
                        str(sum(dmin[s] < 0.10 for s in grupo)))
            todos = resumen_fb(sem)
            con = resumen_fb(con_fb)
            sin = resumen_fb([s for s in sem if s not in con_fb])
            for j, calc in ((2, todos[0]), (3, todos[1]), (4, str(len(sem))),
                            (5, str(len(con_fb))), (6, con[0]), (7, con[1]),
                            (8, str(len(sem) - len(con_fb))), (9, sin[0]), (10, sin[1])):
                cuenta.comparar(f"fallback y distancia {c} ({j})", mm.group(j), calc)
            reconocida = True
        elif _RE_IND.match(linea):
            mm = _RE_IND.match(linea)
            c = mm.group(1)
            vistos.append(("ind", c))
            f = col(datos, c, "cbf_frac_interv", sem)
            for j, calc in ((2, format(media(f), ".8f")), (3, str(sum(x > 0.5 for x in f))),
                            (4, str(len(sem))), (5, format(max(f), ".8f"))):
                cuenta.comparar(f"indicador {c} ({j})", mm.group(j), calc)
            reconocida = True
        elif _RE_SEG.match(linea):
            mm = _RE_SEG.match(linea)
            c = mm.group(1)
            vistos.append(("seg", c))
            for j, m_ in enumerate(("contactos_obst_eventos", "contactos_obst_empuje",
                                    "contactos_obst_avance", "colisiones_015",
                                    "colisiones_022", "contacto_pared", "qp_fallbacks",
                                    "f1_filas_saturadas", "viol_cota_obst_agente_eps"), 2):
                cuenta.comparar(f"seguridad {c} {m_}", mm.group(j),
                                str(int(math.fsum(col(datos, c, m_, sem)))))
            cuenta.comparar(f"seguridad {c} d_min", mm.group(11),
                            format(min(col(datos, c, "d_min_obst_superficie", sem)), ".8f"))
            reconocida = True
        elif _RE_MEC.match(linea):
            mm = _RE_MEC.match(linea)
            base, ca, cb = mm.group(1), mm.group(2), mm.group(3)
            vistos.append(("mec", base, ca, cb))
            c_obst, c_pared, c_robot = MECANISMO[base]

            def dd(m_: str) -> List[float]:
                return [x - y for x, y in zip(col(datos, ca, m_, sem), col(datos, cb, m_, sem))]
            dt_, do, dp_, dr = (media(dd(m_)) for m_ in ("cbf_frac_interv", c_obst, c_pared, c_robot))
            de = media(dd("escape_n"))
            eo = media(col(datos, ca, "escape_n_junto_obst", sem))
            mp, lop, hip = ic95(dd("frac_agente_paso_periferia_050"))
            pares = [(4, format(dt_, "+.6f")), (5, format(do, "+.6f")), (6, format(dp_, "+.6f")),
                     (7, format(dr, "+.6f")),
                     (8, format(dp_ / dt_ if dt_ != 0 else float("nan"), ".4f")),
                     (9, format(de, "+.3f")), (12, format(mp, "+.5f")),
                     (13, format(lop, "+.4f")), (14, format(hip, "+.4f")),
                     (15, "*" if lop * hip > 0 else " ")]
            for j, calc in pares:
                cuenta.comparar(f"mecanismo [{base}] {ca} − {cb} ({j})", mm.group(j), calc)
            if cb.endswith("_ctrl"):
                cuenta.comparar(f"mecanismo [{base}] {ca} − {cb} % junto",
                                mm.group(10) or "—",
                                format(100 * eo / de if de > 0 else float("nan"), ".2f"))
            else:
                cuenta.comparar(f"mecanismo [{base}] {ca} − {cb} —", mm.group(11) or "(cifra)", "—")
            reconocida = True
        elif _RE_OMEGA.match(linea):
            mm = _RE_OMEGA.match(linea)
            c = mm.group(1)
            vistos.append(("omega", c))
            n = col(datos, c, "f1_parte_omega_n", sem)
            p = col(datos, c, "f1_parte_omega_media", sem)
            tot = math.fsum(n)
            cuenta.comparar(f"ω {c}", mm.group(2),
                            format(math.fsum(a * b for a, b in zip(p, n)) / tot
                                   if tot else float("nan"), ".6f"))
            cuenta.comparar(f"ω {c} n", mm.group(3), str(int(tot)))
            reconocida = True
        elif _RE_REG_NIVEL_X.match(linea):
            mm = _RE_REG_NIVEL_X.match(linea)
            c = mm.group(1)
            vistos.append(("reg_nivel", c))
            f = col(datos, c, "cbf_frac_interv", sem)
            cuenta.comparar(f"registro {c} intervención", mm.group(2), format(media(f), ".8f"))
            cuenta.comparar(f"registro {c} sobre/bajo", mm.group(3),
                            "sobre" if media(f) > 0.5 else "bajo")
            for j, m_ in enumerate(CRIT, 4):
                cuenta.comparar(f"registro {c} {m_}", mm.group(j),
                                str(int(math.fsum(col(datos, c, m_, sem)))))
            reconocida = True
        elif _RE_REG_REGLA.match(linea):
            mm = _RE_REG_REGLA.match(linea)
            k = mm.group(1)
            vistos.append(("reg_regla", k))
            dispara = any(math.fsum(col(datos, f"{k}_din", m_, sem)) > 0 for m_ in CRIT)
            cuenta.comparar(f"registro regla {k}: nivel", mm.group(2), k)
            cuenta.comparar(f"registro regla {k}", mm.group(3),
                            "la dispararía" if dispara else "no la dispararía")
            reconocida = True
        elif _RE_REG_HUELLA.match(linea):
            vistos.append(("reg_huella",))
            cuenta.comparar("registro: huella", _RE_REG_HUELLA.match(linea).group(1), HUELLA_S1)
            reconocida = True
        elif _RE_REG_REPRO.match(linea):
            mm = _RE_REG_REPRO.match(linea)
            vistos.append(("reg_repro",))
            ig, n, nc = comparar_reproduccion()
            for j, v in ((1, ig), (2, n), (3, nc)):
                cuenta.comparar(f"registro reproducción ({j})", mm.group(j), str(v))
            reconocida = True   # el grupo 4 son segundos de pared: no es un dato
        elif _RE_REG_SHA.match(linea):
            mm = _RE_REG_SHA.match(linea)
            rel = mm.group(2)
            if rel in SHA256_S1:
                vistos.append(("reg_sha", rel))
                cuenta.comparar(f"registro sha256 {rel}", mm.group(1), SHA256_S1[rel])
            cuenta.comparar(f"registro sha256 actual {rel}", mm.group(1), sha256_de(rel))
            reconocida = True
        elif _RE_REG_STACK.match(linea):
            vistos.append(("reg_stack",))
            cuenta.exigir("stack igual a los requisitos congelados",
                          _RE_REG_STACK.match(linea).group(1).endswith(
                              "igual a requisitos_congelados_2026-09-09"))
            reconocida = True
        if not reconocida and re.search(r"\d", linea) and not linea.startswith(PREFIJOS_SIN_CIFRAS):
            sin_verificar.append(linea)
        if "CRITERIO DE PARADA POR FALLA REAL" in linea:
            cuenta.exigir(f"no hay línea de parada en lo exploratorio: {linea.strip()}", False)
    E = esperado(datos, sem)
    V = set(vistos)
    for k in sorted(E - V, key=str):
        cuenta.exigir(f"FALTA en el resumen: {k}", False)
    for k in sorted(V - E, key=str):
        cuenta.exigir(f"SOBRA en el resumen: {k}", False)
    duplicados = sorted({v for v in vistos if vistos.count(v) > 1}, key=str)
    for k in duplicados:
        cuenta.exigir(f"DUPLICADO en el resumen: {k}", False)
    cuenta.exigir(f"completitud: {len(E)} bloques y filas esperados, todos presentes",
                  not (E - V) and not (V - E) and not duplicados)
    cuenta.exigir("S2 y S3 completos (cuatro condiciones, 100 semillas)",
                  all(len(datos.get(f"{k}_{t}", {})) == 100 for k in NIVELES_EXPL for t in TIPOS))
    return sin_verificar


def verificar_fijos(datos, cuenta: Contador) -> None:
    """C: lo que no puede cambiar ni faltar."""
    for rel, h in SHA256_S1.items():
        cuenta.comparar(f"sha256 de {rel}", sha256_de(rel), h)
    ig, n, nc = comparar_reproduccion()
    cuenta.exigir(f"reproducción de S1_din: {ig}/{n} en {nc} columnas", ig == n == 100)
    huellas = [l.split()[1] for l in RUTA_REG_EXPL.read_text(encoding="utf-8").splitlines()
               if l.startswith("HUELLA ")]
    cuenta.exigir("huella del registro exploratorio = la de S1 = la del código hoy",
                  huellas == [HUELLA_S1] and _huella_propia() == HUELLA_S1)
    for ruta in (RUTA_REG_EXPL, RUTA_LOG_EXPL):
        cuenta.exigir(f"{ruta.name}: EXPLORATORIO en la primera línea",
                      ruta.read_text(encoding="utf-8").splitlines()[0].startswith("EXPLORATORIO —"))
    for ruta in (RUTA_CSV_EXPL, RUTA_REPRO):
        filas = [r for por in cargar(ruta).values() for r in por.values()]
        cuenta.exigir(f"{ruta.name}: exploratorio = 1 en las {len(filas)} filas",
                      bool(filas) and all(r["exploratorio"] == "1" for r in filas))
    sem = sorted(next(iter(datos.values())).keys())
    for k in NIVELES_EXPL:
        for s in sem:
            fases = {t: datos[f"{k}_{t}"][s]["fases"] for t in TIPOS}
            regen = ";".join(repr(x) for x in fases_regeneradas(k, s))
            cuenta.exigir(f"pareo {k} {s}: fases", len(set(fases.values())) == 1
                          and fases["din"] == regen)
            for m_ in ("agentes_reubicados", "objetivos_reubicados"):
                cuenta.exigir(f"pareo {k} {s}: {m_}",
                              len({datos[f"{k}_{t}"][s][m_] for t in TIPOS}) == 1)


def cifras_subseccion() -> List[Tuple[str, Callable, str, str]]:
    """(descripción, función(datos, sem) → valor, formato, valor en la subsección).
    Corregida el 24-10 con la lectura nueva (eventos raros y fallback-distancia)."""
    def S(c, k):
        return lambda d, s: int(math.fsum(col(d, c, k, s)))

    def MN(c, k):
        return lambda d, s: min(col(d, c, k, s))

    def D(a, b, k, j):
        return lambda d, s: ic95([x - y for x, y in zip(col(d, a, k, s), col(d, b, k, s))])[j]

    def SEM(c, k):
        return lambda d, s: sorted(episodios_con(d, c, k, s))

    def EPS(c, k):
        return lambda d, s: len(episodios_con(d, c, k, s))

    def CP(c, k, j):
        return lambda d, s: clopper_pearson_propio(len(episodios_con(d, c, k, s)), len(s))[j]

    def MCN(k, a, b, col_, j):
        def f(d, s):
            sa, sb, p = mcnemar_propia(episodios_con(d, f"{k}_{a}", col_, s),
                                       episodios_con(d, f"{k}_{b}", col_, s))
            return (sa, sb, formato_p(p))[j]
        return f

    def comparte(k, m, t):
        return lambda d, s: [x[0] for x in atribucion(d, k, m, s)
                             if x[{"ctrl": 2, "quieto": 3, "sinvel": 4}[t]] == "sí"]

    def dmin_grupo(c, con_fallback: bool):
        def f(d, s):
            fb = episodios_con(d, c, "qp_fallbacks", s)
            grupo = [x for x in s if (x in fb) == con_fallback]
            return min(float(d[c][x]["d_min_obst_superficie"]) for x in grupo)
        return f

    def bajo(c, umbral, con_fallback=None):
        def f(d, s):
            fb = episodios_con(d, c, "qp_fallbacks", s)
            return sorted(x for x in s if float(d[c][x]["d_min_obst_superficie"]) < umbral
                          and (con_fallback is None or (x in fb) == con_fallback))
        return f

    L: List[Tuple[str, Callable, str, str]] = [
        ("reproducción S1_din iguales", lambda d, s: comparar_reproduccion()[0], "{}", "100"),
        ("reproducción S1_din columnas", lambda d, s: comparar_reproduccion()[2], "{}", "66"),
        ("filas exploratorias", lambda d, s: sum(len(v) for v in d.values()), "{}", "800"),
        ("semilla del agotado de S1 (en las cuatro)",
         lambda d, s: sum(cargar(RUTA_CSV_S1)[f"S1_{t}"][420001]["escape_agotados"] == "1"
                          for t in TIPOS), "{}", "4"),
        ("la semilla del agotado de S1_din", lambda d, s: ", ".join(
            str(x) for x, r in sorted(cargar(RUTA_CSV_S1)["S1_din"].items())
            if float(r["escape_agotados"]) > 0), "{}", "420001"),
        ("reproducción S1_din k/n", lambda d, s: "{}/{}".format(*comparar_reproduccion()[:2]),
         "{}", "100/100"),
        ("S2_din fallbacks en episodios", lambda d, s: (
            f"{S('S2_din', 'qp_fallbacks')(d, s)} en {EPS('S2_din', 'qp_fallbacks')(d, s)}/{len(s)}"),
         "{}", "5 en 2/100"),
        ("S3_din fallbacks en episodios", lambda d, s: (
            f"{S('S3_din', 'qp_fallbacks')(d, s)} en {EPS('S3_din', 'qp_fallbacks')(d, s)}/{len(s)}"),
         "{}", "154 en 5/100"),
        ("S3_sinvel fallbacks en episodios", lambda d, s: (
            f"{S('S3_sinvel', 'qp_fallbacks')(d, s)} en "
            f"{EPS('S3_sinvel', 'qp_fallbacks')(d, s)}/{len(s)}"), "{}", "79 en 3/100"),
    ]
    tabla = {
        "S2_din": ("0", "0", "5", "1", "0.12054343"),
        "S2_quieto": ("0", "1", "0", "0", "0.14718863"),
        "S2_sinvel": ("0", "0", "0", "0", "0.09768094"),
        "S3_din": ("0", "13", "154", "2", "0.07890187"),
        "S3_quieto": ("0", "3", "0", "2", "0.14020460"),
        "S3_sinvel": ("13", "5", "79", "3", "0.07500000"),
    }
    for c, (vc, va, vf, vi, vd) in tabla.items():
        L += [(f"{c} contactos", S(c, "contactos_obst_eventos"), "{}", vc),
              (f"{c} agotados", S(c, "escape_agotados"), "{}", va),
              (f"{c} fallbacks", S(c, "qp_fallbacks"), "{}", vf),
              (f"{c} infactibles junto obst", S(c, "escape_infactibles_junto_obst"), "{}", vi),
              (f"{c} d_min", MN(c, "d_min_obst_superficie"), "{:.8f}", vd),
              (f"{c} filas saturadas", S(c, "f1_filas_saturadas"), "{}", "0")]
    # Tabla de eventos raros: k de 100 y su IC (las celdas "no aplica" son del control).
    raros = {
        "S2_ctrl": {"qp_fallbacks": ("0", "0.0000", "0.0362"), "escape_agotados": ("0", "0.0000", "0.0362")},
        "S2_quieto": {"qp_fallbacks": ("0", "0.0000", "0.0362"), "escape_agotados": ("1", "0.0003", "0.0545"),
                      "contactos_obst_eventos": ("0", "0.0000", "0.0362"),
                      "viol_cota_obst_agente_eps": ("0", "0.0000", "0.0362")},
        "S2_din": {"qp_fallbacks": ("2", "0.0024", "0.0704"), "escape_agotados": ("0", "0.0000", "0.0362"),
                   "contactos_obst_eventos": ("0", "0.0000", "0.0362"),
                   "viol_cota_obst_agente_eps": ("1", "0.0003", "0.0545")},
        "S2_sinvel": {"qp_fallbacks": ("0", "0.0000", "0.0362"), "escape_agotados": ("0", "0.0000", "0.0362"),
                      "contactos_obst_eventos": ("0", "0.0000", "0.0362"),
                      "viol_cota_obst_agente_eps": ("11", "0.0562", "0.1883")},
        "S3_ctrl": {"qp_fallbacks": ("0", "0.0000", "0.0362"), "escape_agotados": ("0", "0.0000", "0.0362")},
        "S3_quieto": {"qp_fallbacks": ("0", "0.0000", "0.0362"), "escape_agotados": ("3", "0.0062", "0.0852"),
                      "contactos_obst_eventos": ("0", "0.0000", "0.0362"),
                      "viol_cota_obst_agente_eps": ("0", "0.0000", "0.0362")},
        "S3_din": {"qp_fallbacks": ("5", "0.0164", "0.1128"), "escape_agotados": ("8", "0.0352", "0.1516"),
                   "contactos_obst_eventos": ("0", "0.0000", "0.0362"),
                   "viol_cota_obst_agente_eps": ("28", "0.1948", "0.3787")},
        "S3_sinvel": {"qp_fallbacks": ("3", "0.0062", "0.0852"), "escape_agotados": ("5", "0.0164", "0.1128"),
                      "contactos_obst_eventos": ("3", "0.0062", "0.0852"),
                      "viol_cota_obst_agente_eps": ("47", "0.3694", "0.5724")},
    }
    for c, por_col in raros.items():
        for col_, (k_, lo, hi) in por_col.items():
            L += [(f"raros {c} {col_} k", EPS(c, col_), "{}", k_),
                  (f"raros {c} {col_} lo", CP(c, col_, 0), "{:.4f}", lo),
                  (f"raros {c} {col_} hi", CP(c, col_, 1), "{:.4f}", hi),
                  (f"raros {c} {col_} celda", lambda d, s, c=c, col_=col_: (
                      f"{len(episodios_con(d, c, col_, s))} "
                      f"[{clopper_pearson_propio(len(episodios_con(d, c, col_, s)), len(s))[0]:.4f}, "
                      f"{clopper_pearson_propio(len(episodios_con(d, c, col_, s)), len(s))[1]:.4f}]"),
                   "{}", f"{k_} [{lo}, {hi}]")]
    # Fallback y distancia.
    L += [
        ("S3_din episodios bajo 0,10 m", bajo("S3_din", 0.10), "{}", "[420025, 420048, 420057, 420099]"),
        ("S3_din bajo 0,10 m sin fallback", bajo("S3_din", 0.10, False), "{}", "[]"),
        ("S3_din d_min sin fallback (4 dec.)", dmin_grupo("S3_din", False), "{:.4f}", "0.1208"),
        ("S3_din episodios con fallback", EPS("S3_din", "qp_fallbacks"), "{}", "5"),
        ("S3_din episodios sin fallback", lambda d, s: len(s) - EPS("S3_din", "qp_fallbacks")(d, s),
         "{}", "95"),
        ("episodios con fallback a diagnosticar (din y sinvel)", lambda d, s: sum(
            EPS(f"{k}_{t}", "qp_fallbacks")(d, s) for k in NIVELES_EXPL for t in ("din", "sinvel")),
         "{}", "10"),
        ("S3_sinvel episodios con contacto", SEM("S3_sinvel", "contactos_obst_eventos"),
         "{}", "[420013, 420057, 420090]"),
        ("S3_sinvel contacto = fallback", lambda d, s: (
            sorted(episodios_con(d, "S3_sinvel", "contactos_obst_eventos", s))
            == sorted(episodios_con(d, "S3_sinvel", "qp_fallbacks", s))), "{}", "True"),
        ("S2_din d_min con fallback", dmin_grupo("S2_din", True), "{:.8f}", "0.13160467"),
        ("S2_din episodios con fallback", EPS("S2_din", "qp_fallbacks"), "{}", "2"),
        ("S3_din a 3,9 mm del disco de contacto",
         lambda d, s: round((min(col(d, "S3_din", "d_min_obst_superficie", s)) - 0.075) * 1000, 1),
         "{}", "3.9"),
        ("S3_din mínimo en un episodio con fallback", lambda d, s: (
            min(s, key=lambda x: float(d["S3_din"][x]["d_min_obst_superficie"]))
            in episodios_con(d, "S3_din", "qp_fallbacks", s)), "{}", "True"),
        ("S3_sinvel fallbacks", S("S3_sinvel", "qp_fallbacks"), "{}", "79"),
        ("S3_sinvel episodios con fallback", EPS("S3_sinvel", "qp_fallbacks"), "{}", "3"),
        ("S2_din episodios con fallback (encierro)", EPS("S2_din", "qp_fallbacks"), "{}", "2"),
        ("quietos sin fallback", lambda d, s: sum(len(episodios_con(d, f"{k}_quieto", "qp_fallbacks", s))
                                                  for k in NIVELES_EXPL), "{}", "0"),
    ]
    # McNemar exacta: (nivel, A, B, columna) → (b, c, p) como en el texto.
    for (k, a, b, col_), (vb, vc, vp) in (
            (("S2", "din", "quieto", "qp_fallbacks"), ("2", "0", "0.5000")),
            (("S3", "din", "quieto", "qp_fallbacks"), ("5", "0", "0.0625")),
            (("S3", "din", "ctrl", "escape_agotados"), ("8", "0", "0.0078")),
            (("S3", "din", "quieto", "escape_agotados"), ("8", "3", "0.2266")),
            (("S2", "din", "quieto", "escape_infactibles_junto_obst"), ("1", "0", "1.0000")),
            (("S3", "din", "quieto", "escape_infactibles_junto_obst"), ("2", "2", "1.0000")),
            (("S2", "sinvel", "din", "viol_cota_obst_agente_eps"), ("10", "0", "0.0020")),
            (("S3", "sinvel", "din", "viol_cota_obst_agente_eps"), ("28", "9", "0.0026")),
            (("S3", "sinvel", "din", "contactos_obst_eventos"), ("3", "0", "0.2500"))):
        L += [(f"mcnemar {k} {a}−{b} {col_} b", MCN(k, a, b, col_, 0), "{}", vb),
              (f"mcnemar {k} {a}−{b} {col_} c", MCN(k, a, b, col_, 1), "{}", vc),
              (f"mcnemar {k} {a}−{b} {col_} b/c", lambda d, s, k=k, a=a, b=b, col_=col_: (
                  f"{MCN(k, a, b, col_, 0)(d, s)}/{MCN(k, a, b, col_, 1)(d, s)}"),
               "{}", f"{vb}/{vc}"),
              (f"mcnemar {k} {a}−{b} {col_} p", MCN(k, a, b, col_, 2), "{}", vp)]
    L += [
        ("S2 bajo 0,13 m: din", EPS("S2_din", "viol_cota_obst_agente_eps"), "{}", "1"),
        ("S2 bajo 0,13 m: sinvel", EPS("S2_sinvel", "viol_cota_obst_agente_eps"), "{}", "11"),
        ("S3 bajo 0,13 m: din", EPS("S3_din", "viol_cota_obst_agente_eps"), "{}", "28"),
        ("S3 bajo 0,13 m: sinvel", EPS("S3_sinvel", "viol_cota_obst_agente_eps"), "{}", "47"),
        ("S3 contactos: episodios din", EPS("S3_din", "contactos_obst_eventos"), "{}", "0"),
        ("S3 contactos: episodios sinvel", EPS("S3_sinvel", "contactos_obst_eventos"), "{}", "3"),
        ("S3_sinvel contactos por empuje = todos",
         lambda d, s: S("S3_sinvel", "contactos_obst_empuje")(d, s)
         == S("S3_sinvel", "contactos_obst_eventos")(d, s), "{}", "True"),
        ("S3 agotados: episodios din", EPS("S3_din", "escape_agotados"), "{}", "8"),
        ("S3 agotados de din sin agotado en ctrl", lambda d, s: len(
            episodios_con(d, "S3_din", "escape_agotados", s)
            - episodios_con(d, "S3_ctrl", "escape_agotados", s)), "{}", "8"),
    ]
    for k in NIVELES_EXPL:
        for m in CRIT:
            for t in ("ctrl", "quieto"):
                L.append((f"{k} {m}: semillas de din compartidas con {t}",
                          comparte(k, m, t), "{}", "[]"))
    L += [
        ("S3 agotado compartido con sinvel", comparte("S3", "escape_agotados", "sinvel"),
         "{}", "[420057]"),
        ("S3 fallback compartido con sinvel", comparte("S3", "qp_fallbacks", "sinvel"),
         "{}", "[420057]"),
        ("S3_din ligante obstáculo din − ctrl",
         D("S3_din", "S3_ctrl", "cbf_frac_lig_obst", 0), "{:+.8f}", "+0.29051200"),
    ]
    for (a, b, k), vals in (
            (("S2_din", "S2_ctrl", "cobertura_accesible"),
             ("+0.03586702", "+0.02168296", "+0.05005108")),
            (("S2_din", "S2_quieto", "cob_acc_arranque"),
             ("+0.01406646", "+0.00052355", "+0.02760937")),
            (("S2_din", "S2_ctrl", "cbf_frac_interv"),
             ("+0.19288800", "+0.16916511", "+0.21661089")),
            (("S3_din", "S3_ctrl", "cobertura_accesible"),
             ("−0.00147768", "−0.01630747", "+0.01335211")),
            (("S3_din", "S3_quieto", "cob_acc_arranque"),
             ("−0.01027655", "−0.02445920", "+0.00390609")),
            (("S3_din", "S3_ctrl", "cbf_frac_interv"),
             ("+0.32190000", "+0.30038257", "+0.34341743")),
            (("S3_din", "S3_ctrl", "frac_agente_paso_periferia_050"),
             ("+0.10771200", "+0.08916852", "+0.12625548"))):
        for j, v in enumerate(vals):
            L.append((f"{a} − {b} {k} ({('Δ', 'lo', 'hi')[j]})", D(a, b, k, j), "{:+.8f}", v))
    L.append(("huella abreviada", lambda d, s: _huella_propia()[:8] + "…" + _huella_propia()[-4:],
              "{}", "e265b6cd…4a29"))
    return L


#: Cifras de la subsección que NO son datos: n, umbrales de diseño y números de
#: sección de la propuesta. Las fechas y los identificadores (S1, 420001 dentro de
#: nombres de archivo, la huella) no son cifras para el extractor.
CIFRAS_DE_DISENO: Tuple[str, ...] = ("100", "0.10", "0.13", "2.3", "3.6")
#: Desde aquí la subsección es metadato (conteos del propio verificador, número de
#: pruebas, tiempos del log): no entra en el extractor.
FIN_DE_LAS_CIFRAS: str = "**Verificación:**"
_RE_CIFRA = re.compile(r"(?<![\w.\-−+/])[−+]?\d+(?:\.\d+)?(?:/\d+)?(?![\w.\-/])")


def cifras_del_texto(texto: str) -> List[str]:
    """Toda cifra del texto antes de `FIN_DE_LAS_CIFRAS` (con su signo y su b/c)."""
    fin = texto.find(FIN_DE_LAS_CIFRAS)
    return _RE_CIFRA.findall(texto[:fin] if fin >= 0 else texto)


def verificar_subseccion(datos, cuenta: Contador) -> None:
    sem = sorted(next(iter(datos.values())).keys())
    texto = RUTA_SUBSECCION.read_text(encoding="utf-8") if RUTA_SUBSECCION.exists() else ""
    citadas: Set[str] = set(CIFRAS_DE_DISENO)
    for desc, fn, fmt, citado in cifras_subseccion():
        try:
            calc = fmt.format(fn(datos, sem))
        except (KeyError, ValueError, ZeroDivisionError, TypeError) as e:
            calc = f"ERROR {type(e).__name__}: {e}"
        malas_antes = len(cuenta.malas)
        cuenta.comparar("subsección: " + desc, citado.replace("−", "-"), calc)
        if len(cuenta.malas) == malas_antes:      # sólo lo que coincide cuenta como verificado
            citadas |= set(_RE_CIFRA.findall(citado))
        if not (citado in ("True", "0", "1", "2") or citado.startswith("[")):
            cuenta.exigir(f"subsección: {citado!r} está en el texto ({desc})", citado in texto)
    # (24-10) Cada cifra del texto tiene que ser un valor recalculado (o de diseño):
    # una cifra cambiada que coincida en otro lugar con un valor correcto no pasa.
    sueltas = [c for c in cifras_del_texto(texto) if c not in citadas]
    for c in sueltas:
        cuenta.exigir(f"subsección: cifra del texto sin verificar {c!r}", False)
    cuenta.exigir(f"subsección: las {len(cifras_del_texto(texto))} cifras del texto están "
                  f"recalculadas o son de diseño", not sueltas)


def main() -> int:
    datos = cargar(RUTA_CSV_EXPL)
    a, b, c = Contador(), Contador(), Contador()
    sin_verificar = verificar_resumen(datos, a)
    verificar_subseccion(datos, b)
    verificar_fijos(datos, c)
    for x in a.malas + b.malas + c.malas:
        print("NO  " + x)
    for x in sin_verificar:
        print("SIN VERIFICAR  " + x)
    print(f"A. resumen exploratorio: {a.ok}/{a.total} cifras y chequeos; líneas con cifras "
          f"sin verificar: {len(sin_verificar)}")
    print(f"B. subsección de la bitácora: {b.ok}/{b.total}")
    print(f"C. fijos (S1, reproducción, huella, rótulos, pareo): {c.ok}/{c.total}")
    ok = (not a.malas and not b.malas and not c.malas and not sin_verificar
          and a.total > 0 and b.total > 0 and c.total > 0)
    print("VEREDICTO: " + ("TODAS LAS CIFRAS COINCIDEN" if ok else "HAY DIFERENCIAS"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
