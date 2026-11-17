"""
verificar_cifras_Q.py
=====================
Recalcula desde los CSV CRUDOS, con código propio (csv + math; numpy sólo
para REGENERAR las fases con su generador, nunca en una estadística), cada
cifra de:

  A. `resultados/resumen_experimento_Q.txt`: cada número de cada tabla y de
     cada línea de comparación, criterio, indicador, seguridad, mecanismo y
     registro, comparado con el recalculado y formateado igual. Además exige
     COMPLETITUD: todos los bloques y filas que el diseño (§3.6 de la
     propuesta) manda para cada nivel corrido, con la cobertura que
     corresponde a cada comparación, y ninguno de más. Una línea con cifras
     que nadie reconozca cuenta como falla (salvo encabezados y notas, en
     `PREFIJOS_SIN_CIFRAS`). También la regla de parada: la línea de parada
     está si y sólo si Sk_din del último nivel falló, y no hay niveles
     después.
  B. la entrada de la bitácora (lista `CIFRAS_BITACORA`, con el valor TAL
     COMO APARECE en el texto). Tiene que tener al menos una cifra.
  C. el pareo: por semilla, las cuatro condiciones de un nivel tienen las
     mismas fases (y son las de `default_rng([semilla, 3])`) y los mismos
     agentes y objetivos reubicados.

Lo que NO recalcula, y por qué: el área y la conexidad de la región del
punto de mira en la pasabilidad (las calcula el chequeo del Exp O en la
corrida: 50 100 instantes por nivel). Sí recalcula los huecos, con sus
propias posiciones.

    python -B verificar_cifras_Q.py

Termina con 0 si todo coincide y con 1 si no.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

_CARPETA: Path = Path(__file__).resolve().parent
DIR_RES: Path = _CARPETA / "resultados"
RUTA_CSV: Path = DIR_RES / "experimento_Q_completo.csv"
RUTA_RES: Path = DIR_RES / "resumen_experimento_Q.txt"
RUTA_CONTROL: Path = DIR_RES / "control_bit_a_bit_Q.csv"
RUTA_NEG: Path = DIR_RES / "control_negativo_Q.csv"
DIR_O: Path = _CARPETA.parent / "expO_obstaculos" / "resultados"
RUTA_O: Path = DIR_O / "experimento_O_completo.csv"
RUTA_O_COMP: Path = DIR_O / "experimento_O_complementario.csv"

ARENA: float = 3.0
PASOS: int = 500
V_OBST, DT = 0.05, 0.1
NIVELES: Tuple[str, ...] = ("S1", "S2", "S3")
TIPOS: Tuple[str, ...] = ("ctrl", "quieto", "din", "sinvel")
#: (cx, cy, r, ρ) por nivel: copia propia de la configuración de la corrida.
NIVELES_GEOM: Dict[str, Tuple[Tuple[float, float, float, float], ...]] = {
    "S1": ((1.5, 1.5, 0.30, 0.60),),
    "S2": ((1.0, 1.0, 0.25, 0.20), (2.0, 2.0, 0.25, 0.20)),
    "S3": ((0.75, 0.75, 0.20, 0.06), (2.25, 0.75, 0.20, 0.06),
           (0.75, 2.25, 0.20, 0.06), (2.25, 2.25, 0.20, 0.06),
           (1.5, 1.5, 0.25, 0.06)),
}

# ── Presentación (copia propia; columna → etiqueta) ──────────────────────
COBERTURAS: Dict[str, str] = {
    "cobertura_accesible": "cobertura AoI (accesible propia)",
    "cob_acc_arranque": "cobertura AoI (fuera de máscara de arranque)",
    "cobertura_sin_enmascarar": "cobertura AoI (cuadrícula completa)",
}
COMUNES: Dict[str, str] = {
    "colisiones_015": "pares en colisión <0,15 m",
    "colisiones_022": "pares en colisión <0,22 m",
    "contactos_obst_eventos": "contactos con obstáculo (agente-paso)",
    "contactos_obst_empuje": "… por empuje del obstáculo",
    "contactos_obst_avance": "… por avance del agente",
    "contactos_obst_agente_eps": "agente-eps con contacto con obstáculo",
    "viol_cota_obst_agente_eps": "agente-eps centro <0,13 m de obst.",
    "frac_agente_paso_banda_018": "frac. agente-paso centro <0,18 m pared",
    "frac_agente_paso_periferia_050": "frac. agente-paso centro <0,5 m pared",
    "d_min_pared_centro": "d_min centro→pared [m]",
    "violaciones_margen": "agente-eps centro <0,18 m de pared",
    "contacto_pared": "agente-eps centro <0,075 m de pared",
    "cbf_frac_interv": "frac. intervención del filtro",
    "cbf_frac_lig_pared": "… pared ligante en el óptimo",
    "cbf_frac_lig_robot": "… robot ligante en el óptimo",
    "cbf_frac_lig_obst": "… obstáculo ligante en el óptimo",
    "cbf_frac_lig_multitipo": "… ≥2 tipos ligantes a la vez",
    "cbf_frac_lig_obst_vel": "… obstáculo acercándose ligante",
    "cbf_frac_hmin_pared": "… h mín. = pared (din: h efectivo)",
    "cbf_frac_hmin_robot": "… h mín. = robot (din: h efectivo)",
    "cbf_frac_hmin_obst": "… h mín. = obstáculo (din: h efectivo)",
    "cbf_magnitud_media": "magnitud media de la modificación",
    "qp_fallbacks": "fallbacks del QP por episodio",
    "f1_filas_saturadas": "filas F1 saturadas por episodio",
    "escape_n": "activaciones del escape por episodio",
    "escape_n_junto_obst": "… con obstáculo activo al disparar",
    "escape_frac_ciclo": "frac. de ciclo en escape",
    "escape_infactibles": "escapes infactibles por episodio",
    "escape_infactibles_junto_obst": "… con obstáculo activo",
    "escape_infact_opuestas": "… por normales opuestas",
    "escape_infact_sin_activas": "… sin barreras activas",
    "escape_infact_op_con_pared": "… opuestas con pared activa",
    "escape_infact_op_con_robot": "… opuestas con robot activo",
    "escape_infact_op_con_obst": "… opuestas con obstáculo activo",
    "escape_agotados": "escapes agotados por episodio",
    "expo_frac_obst_activo": "frac. agente-decisión obst. activo (h<0,06)",
    "expo_frac_activo_acercandose": "… y acercándose (s>0)",
}
SOLO_TABLA: Dict[str, str] = {
    "d_min_obst_superficie": "d_min centro→superficie obst. [m]",
    "f1_parte_omega_n": "filas ligantes acercándose (n)",
    "agentes_reubicados": "agentes reubicados al inicio",
    "objetivos_reubicados": "objetivos reubicados al inicio",
    "rebotes_objetivo_obst": "rebotes de objetivos en obstáculos",
    "frac_mascara": "fracción de celdas, máscara de la métrica",
    "frac_mascara_arranque": "fracción de celdas en la máscara de arranque",
}
MINIMOS: Dict[str, str] = {"d_min obst., mínimo global [m]": "d_min_obst_superficie",
                           "d_min pared, mínimo global [m]": "d_min_pared_centro"}
ETIQUETAS: Dict[str, str] = {e: c for c, e in {**COBERTURAS, **COMUNES, **SOLO_TABLA}.items()}
#: §3.6: qué coberturas lleva cada comparación (la primera, el costo relativo).
DISENO_COMP: Dict[Tuple[str, str], Tuple[str, str]] = {
    ("din", "ctrl"): ("cobertura_accesible", "cobertura_sin_enmascarar"),
    ("din", "quieto"): ("cob_acc_arranque", "cobertura_sin_enmascarar"),
    ("quieto", "ctrl"): ("cob_acc_arranque", "cobertura_sin_enmascarar"),
    ("sinvel", "din"): ("cobertura_accesible", "cobertura_sin_enmascarar"),
}
MECANISMO: Dict[str, Tuple[str, str, str]] = {
    "lig": ("cbf_frac_lig_obst", "cbf_frac_lig_pared", "cbf_frac_lig_robot"),
    "hmin": ("cbf_frac_hmin_obst", "cbf_frac_hmin_pared", "cbf_frac_hmin_robot"),
}
PARES_MECANISMO: Tuple[Tuple[str, str], ...] = (("din", "ctrl"), ("din", "quieto"),
                                                ("sinvel", "din"))
CRIT: Tuple[str, ...] = ("contactos_obst_eventos", "escape_agotados", "qp_fallbacks",
                         "escape_infactibles_junto_obst")
#: Líneas del resumen con dígitos que no son cifras del experimento.
PREFIJOS_SIN_CIFRAS: Tuple[str, ...] = (
    "términos) con la fila F1", "100 semillas", "ESTADÍSTICA:", "'*' si el IC",
    "H MÍNIMO", "con h_eq", "  métrica", "  indirecta =", "  contra el control)",
    "  Δ periferia =", "PARTE DE ω", "MECANISMO —", "del Exp O (en Sk_din",
    "restricción ligante", "INDICADOR", "  COPIAS del Exp O", "    IGUAL ",
    "  procesos:", "  HUELLA", "  PASABILIDAD a lo largo",
)

# =============================================================================
# DATOS Y ESTADÍSTICA PROPIA
# =============================================================================


def cargar(ruta: Path) -> Dict[str, Dict[int, Dict[str, str]]]:
    datos: Dict[str, Dict[int, Dict[str, str]]] = {}
    with open(ruta, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            datos.setdefault(r["condicion"], {})[int(r["seed_ep"])] = r
    return datos


def col(datos, c: str, m: str, sem: Sequence[int]) -> List[float]:
    return [float(datos[c][s][m]) for s in sem]


def media(x: Sequence[float]) -> float:
    return math.fsum(x) / len(x)


def ic95(x: Sequence[float]) -> Tuple[float, float, float]:
    m = media(x)
    sd = math.sqrt(math.fsum((v - m) ** 2 for v in x) / (len(x) - 1))
    ee = sd / math.sqrt(len(x))
    return m, m - 1.96 * ee, m + 1.96 * ee


def f8(v: float, ancho: str = "") -> str:
    return format(v, f"{ancho}.8f").strip()


def _norm(s: str) -> str:
    """Un cero impreso es cero con cualquier signo (suma por pares vs fsum)."""
    s = s.strip()
    try:
        if float(s) == 0.0:
            return "0"
    except ValueError:
        pass
    return s


class Contador:
    def __init__(self) -> None:
        self.ok = 0
        self.malas: List[str] = []

    def comparar(self, desc: str, impreso: str, calculado: str) -> None:
        if _norm(impreso) == _norm(calculado):
            self.ok += 1
        else:
            self.malas.append(f"{desc}: impreso {impreso!r}, calculado {calculado!r}")

    def exigir(self, desc: str, condicion: bool) -> None:
        if condicion:
            self.ok += 1
        else:
            self.malas.append(desc)

    @property
    def total(self) -> int:
        return self.ok + len(self.malas)


def fases_regeneradas(nivel: str, s: int) -> List[float]:
    """Las fases de `default_rng([semilla, 3])` (numpy sólo como generador)."""
    import numpy as np
    m = len(NIVELES_GEOM[nivel])
    return [float(x) for x in np.random.default_rng([int(s), 3]).uniform(
        -math.pi, math.pi, size=m)]


def huecos_semilla(nivel: str, fases: Sequence[float]) -> Tuple[float, float]:
    """Huecos mínimos sobre los 501 instantes, con posiciones propias."""
    obs = NIVELES_GEOM[nivel]
    gw = go = math.inf
    for t in range(PASOS + 1):
        pos = []
        for (cx, cy, r, rho), f0 in zip(obs, fases):
            ph = f0 + (V_OBST / rho) * DT * float(t)
            x, y = cx + rho * math.cos(ph), cy + rho * math.sin(ph)
            pos.append((x, y, r))
            gw = min(gw, x - r, ARENA - x - r, y - r, ARENA - y - r)
        for a in range(len(pos)):
            for b in range(a + 1, len(pos)):
                go = min(go, math.hypot(pos[a][0] - pos[b][0], pos[a][1] - pos[b][1])
                         - pos[a][2] - pos[b][2])
    return gw, go


def comparar_control(control) -> Tuple[int, Tuple[int, int, int], Tuple[int, int, int]]:
    """El control bit a bit, recalculado: (corridas, principal, complementario)."""
    def contra(ruta: Path) -> Tuple[int, int, int]:
        ref = cargar(ruta)
        cols: List[str] = []
        iguales = n = 0
        for c, por_sem in ref.items():
            for s, r in por_sem.items():
                n += 1
                cols = [k for k in r if k != "t_episodio_s"]
                f = control.get(c, {}).get(s)
                if f is None:
                    continue
                # Estricto: el mismo TEXTO que escribió `escribir_csv` (repr de
                # cada float): distingue −0.0 de 0.0 y "3" de "3.0".
                iguales += all(f[k] == r[k] for k in cols)
        return iguales, n, len(cols)
    distintas = sum(len(v) for v in control.values())
    return distintas, contra(RUTA_O), contra(RUTA_O_COMP)


def falla_din(datos, k: str, sem: Sequence[int]) -> bool:
    return any(math.fsum(col(datos, f"{k}_din", m, sem)) > 0 for m in CRIT)


def esperado(datos, sem: Sequence[int]) -> Set[Tuple[str, ...]]:
    """Bloques y filas que el diseño manda imprimir para los niveles corridos."""
    niveles = [k for k in NIVELES if f"{k}_din" in datos]
    E: Set[Tuple[str, ...]] = {("reg_control",), ("reg_neg",), ("reg_stack",)}
    E |= {("reg_pasab", k) for k in NIVELES}
    for k in niveles:
        E |= {("tabla", k, e) for e in list(ETIQUETAS) + list(MINIMOS)}
        for (a, b), cobs in DISENO_COMP.items():
            E |= {("comp", f"{k}_{a}", f"{k}_{b}", COBERTURAS[c]) for c in cobs}
            E |= {("comp", f"{k}_{a}", f"{k}_{b}", e) for e in COMUNES.values()}
            E.add(("rel", f"{k}_{a}", f"{k}_{b}", cobs[0]))
            E.add(("titulo", f"{k}_{a}", f"{k}_{b}"))
        for t in ("din", "quieto", "sinvel"):
            E |= {("crit", f"{k}_{t}"), ("seg", f"{k}_{t}"), ("omega", f"{k}_{t}"),
                  ("reg_nivel", f"{k}_{t}")}
        E |= {("ind", f"{k}_{t}") for t in TIPOS}
        E |= {("mec", base, f"{k}_{a}", f"{k}_{b}") for base in MECANISMO
              for a, b in PARES_MECANISMO}
    if niveles and falla_din(datos, niveles[-1], sem):
        E.add(("reg_parada", niveles[-1]))
    return E


# =============================================================================
# A. RESUMEN
# =============================================================================

_RE_TABLA = re.compile(r"^TABLA (S\d) — medias sobre (\d+) episodios$")
_RE_COMP = re.compile(r"^COMPARACIÓN PAREADA (S\d_\w+) − (S\d_\w+) \(.*; (\d+) semillas\)$")
_RE_FILA_COMP = re.compile(r"^\s*([+-]\d+\.\d+) \[\s*([+-]\d+\.\d+), \s*([+-]\d+\.\d+)\]([* ])"
                           r"\s+(\d+)\s+(\d+)$")
_RE_REL = re.compile(r"^  costo relativo en (\w+): (\S+) % \[(\S+), (\S+)\]$")
_RE_CRIT = re.compile(r"^  (S\d_\w+)( \(DECIDE\))?: contactos obst\. (\d+); escapes "
                      r"agotados (\d+); fallbacks QP (\d+); infactibles junto a obst\. (\d+)$")
_RE_IND = re.compile(r"^  (S\d_\w+): media (\d+\.\d+); episodios > 0,5: (\d+)/(\d+); "
                     r"máx\. (\d+\.\d+)$")
_RE_SEG = re.compile(r"^  (S\d_\w+): contactos con obstáculo (\d+) \(empuje (\d+), avance "
                     r"(\d+)\); colisiones <0,15 m (\d+); <0,22 m (\d+); contacto con pared "
                     r"(\d+); fallbacks del QP (\d+); filas F1 saturadas (\d+); agente-eps "
                     r"bajo 0,13 m (\d+); d_min obst\. (-?\d+\.\d+) m$")
_RE_MEC = re.compile(r"^  \[(lig|hmin)\] (S\d_\w+) − (S\d_\w+)\s+([+-]\d+\.\d+)\s+([+-]\d+\.\d+)\s+"
                     r"([+-]\d+\.\d+)\s+([+-]\d+\.\d+)\s+(-?\d+\.\d+|nan)\s+([+-]\d+\.\d+)\s+"
                     r"(?:(-?\d+\.\d+|nan)%|(—)\s)\s([+-]\d+\.\d+)\[([+-]\d+\.\d+),"
                     r"([+-]\d+\.\d+)\]([* ])$")
_RE_OMEGA = re.compile(r"^  (S\d_\w+): (\d+\.\d+|nan) sobre (\d+) filas$")
_RE_REG_NIVEL = re.compile(r"^  (S\d_\w+) \((DECIDE|se reporta)\): intervención media "
                           r"(\d+\.\d+) \((sobre|bajo) el indicador 0\.5; no detiene\); "
                           r"criterios — contacto con obstáculo (\d+); escape agotado (\d+); "
                           r"fallback del QP (\d+); escape infactible con obstáculo activo (\d+)$")
_RE_REG_PARADA = re.compile(r"^  (S\d): CRITERIO DE PARADA POR FALLA REAL en (S\d)_din")
_RE_REG_CONTROL = re.compile(r"^  CONTROL bit a bit .*: (\d+) corridas distintas; (\d+)/(\d+) "
                             r"filas idénticas en las (\d+) columnas de experimento_O_completo"
                             r"\.csv y (\d+)/(\d+) en las (\d+) de experimento_O_complementario")
_RE_REG_NEG = re.compile(r"^  CONTROL NEGATIVO .*: contactos (\d+) eventos \((\d+) por "
                         r"empuje\) en (\d+)/(\d+) episodios; d_min centro→superficie mínimo "
                         r"(-?\d+\.\d+) m")
_RE_REG_PASAB = re.compile(r"^    (S\d): peor caso analítico pared (\d+\.\d+) m, obst–obst "
                           r"(\d+\.\d+|inf) m; en las semillas pared (\d+\.\d+) m, obst–obst "
                           r"(\d+\.\d+|inf) m; área .*; instantes evaluados (\d+), fallidos (\d+) "
                           r"→ PASABLE")
_RE_REG_STACK = re.compile(r"^  STACK: (.*)$")


def verificar_resumen(datos, cuenta: Contador) -> List[str]:
    """Recorre el resumen; devuelve las líneas con cifras no reconocidas."""
    sem = sorted(next(iter(datos.values())).keys())
    lineas = RUTA_RES.read_text(encoding="utf-8").splitlines()
    sin_verificar: List[str] = []
    vistos: List[Tuple[str, ...]] = []
    seccion: Optional[Tuple[str, ...]] = None
    conds: List[str] = []
    control = cargar(RUTA_CONTROL) if RUTA_CONTROL.exists() else {}
    negativo = cargar(RUTA_NEG) if RUTA_NEG.exists() else {}
    for i, linea in enumerate(lineas):
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
                if etiqueta in ETIQUETAS:
                    v = [x for x in col(datos, c, ETIQUETAS[etiqueta], sem) if math.isfinite(x)]
                    calc = format(media(v), "14.8f") if v else format(float("nan"), "14.8f")
                else:
                    v = [x for x in col(datos, c, MINIMOS[etiqueta], sem) if math.isfinite(x)]
                    calc = format(min(v), "14.8f") if v else format(float("nan"), "14.8f")
                cuenta.comparar(f"tabla {c} {etiqueta}", impreso, calc)
            reconocida = len(valores) == len(conds)
        elif seccion and seccion[0] == "comp" and etiqueta in ETIQUETAS:
            a, b = seccion[1], seccion[2]
            mm = _RE_FILA_COMP.match(linea[48:])
            if mm:
                vistos.append(("comp", a, b, etiqueta))
                d = [x - y for x, y in zip(col(datos, a, ETIQUETAS[etiqueta], sem),
                                           col(datos, b, ETIQUETAS[etiqueta], sem))]
                me, lo, hi = ic95(d)
                desc = f"{a} − {b} {etiqueta}"
                cuenta.comparar(desc + " Δ", mm.group(1), f8(me, "+13"))
                cuenta.comparar(desc + " lo", mm.group(2), f8(lo, "+13"))
                cuenta.comparar(desc + " hi", mm.group(3), f8(hi, "+13"))
                cuenta.comparar(desc + " *", mm.group(4), "*" if lo * hi > 0 else " ")
                cuenta.comparar(desc + " >0", mm.group(5), str(sum(x > 0 for x in d)))
                cuenta.comparar(desc + " <0", mm.group(6), str(sum(x < 0 for x in d)))
                reconocida = True
        elif seccion and seccion[0] == "comp" and _RE_REL.match(linea):
            mm = _RE_REL.match(linea)
            a, b, c0 = seccion[1], seccion[2], mm.group(1)
            vistos.append(("rel", a, b, c0))
            rel = [x / y - 1 for x, y in zip(col(datos, a, c0, sem), col(datos, b, c0, sem))]
            me, lo, hi = ic95(rel)
            for j, v in ((2, me), (3, lo), (4, hi)):
                cuenta.comparar(f"{a} − {b} costo relativo {c0} ({j})", mm.group(j),
                                format(100 * v, "+.4f"))
            reconocida = True
        elif _RE_CRIT.match(linea):
            mm = _RE_CRIT.match(linea)
            c = mm.group(1)
            vistos.append(("crit", c))
            cuenta.comparar(f"criterio {c} (DECIDE)", mm.group(2) or "",
                            " (DECIDE)" if c.endswith("_din") else "")
            for j, m_ in enumerate(CRIT, 3):
                cuenta.comparar(f"criterio {c} {m_}", mm.group(j),
                                str(int(math.fsum(col(datos, c, m_, sem)))))
            reconocida = True
        elif _RE_IND.match(linea):
            mm = _RE_IND.match(linea)
            c = mm.group(1)
            vistos.append(("ind", c))
            f = col(datos, c, "cbf_frac_interv", sem)
            cuenta.comparar(f"indicador {c} media", mm.group(2), format(media(f), ".8f"))
            cuenta.comparar(f"indicador {c} >0,5", mm.group(3), str(sum(x > 0.5 for x in f)))
            cuenta.comparar(f"indicador {c} n", mm.group(4), str(len(sem)))
            cuenta.comparar(f"indicador {c} máx", mm.group(5), format(max(f), ".8f"))
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
            dt_, do, dp_, dr = (media(dd(m_)) for m_ in (
                "cbf_frac_interv", c_obst, c_pared, c_robot))
            de = media(dd("escape_n"))
            eo = media(col(datos, ca, "escape_n_junto_obst", sem))
            mp, lop, hip = ic95(dd("frac_agente_paso_periferia_050"))
            contra_ctrl = cb.endswith("_ctrl")
            pares = [(mm.group(4), format(dt_, "+.6f")), (mm.group(5), format(do, "+.6f")),
                     (mm.group(6), format(dp_, "+.6f")), (mm.group(7), format(dr, "+.6f")),
                     (mm.group(8), format(dp_ / dt_ if dt_ != 0 else float("nan"), ".4f")),
                     (mm.group(9), format(de, "+.3f")),
                     (mm.group(12), format(mp, "+.5f")), (mm.group(13), format(lop, "+.4f")),
                     (mm.group(14), format(hip, "+.4f")),
                     (mm.group(15), "*" if lop * hip > 0 else " ")]
            if contra_ctrl:
                pares.append((mm.group(10) or "—",
                              format(100 * eo / de if de > 0 else float("nan"), ".2f")))
            else:
                pares.append((mm.group(11) or "(cifra)", "—"))
            for j, (impreso, calc) in enumerate(pares):
                cuenta.comparar(f"mecanismo [{base}] {ca} − {cb} ({j})", impreso, calc)
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
        elif _RE_REG_NIVEL.match(linea):
            mm = _RE_REG_NIVEL.match(linea)
            c = mm.group(1)
            vistos.append(("reg_nivel", c))
            f = col(datos, c, "cbf_frac_interv", sem)
            cuenta.comparar(f"registro {c} papel", mm.group(2),
                            "DECIDE" if c.endswith("_din") else "se reporta")
            cuenta.comparar(f"registro {c} intervención", mm.group(3), format(media(f), ".8f"))
            cuenta.comparar(f"registro {c} sobre/bajo", mm.group(4),
                            "sobre" if media(f) > 0.5 else "bajo")
            for j, m_ in enumerate(CRIT, 5):
                cuenta.comparar(f"registro {c} {m_}", mm.group(j),
                                str(int(math.fsum(col(datos, c, m_, sem)))))
            reconocida = True
        elif _RE_REG_PARADA.match(linea):
            mm = _RE_REG_PARADA.match(linea)
            vistos.append(("reg_parada", mm.group(1)))
            cuenta.comparar("registro parada: nivel", mm.group(2), mm.group(1))
            reconocida = True
        elif _RE_REG_CONTROL.match(linea):
            mm = _RE_REG_CONTROL.match(linea)
            vistos.append(("reg_control",))
            distintas, (i1, n1, c1), (i2, n2, c2) = comparar_control(control)
            for j, v in enumerate((distintas, i1, n1, c1, i2, n2, c2), 1):
                cuenta.comparar(f"registro control ({j})", mm.group(j), str(v))
            reconocida = True
        elif _RE_REG_NEG.match(linea):
            mm = _RE_REG_NEG.match(linea)
            vistos.append(("reg_neg",))
            filas = [r for por in negativo.values() for r in por.values()]
            ev = sum(int(r["contactos_obst_eventos"]) for r in filas)
            emp = sum(int(r["contactos_obst_empuje"]) for r in filas)
            eps = sum(int(r["contactos_obst_eventos"]) > 0 for r in filas)
            dmin = min(float(r["d_min_obst_superficie"]) for r in filas) if filas else math.nan
            for j, v in enumerate((str(ev), str(emp), str(eps), str(len(filas)),
                                   format(dmin, ".8f")), 1):
                cuenta.comparar(f"registro negativo ({j})", mm.group(j), v)
            reconocida = True
        elif _RE_REG_PASAB.match(linea):
            mm = _RE_REG_PASAB.match(linea)
            nivel = mm.group(1)
            vistos.append(("reg_pasab", nivel))
            obs = NIVELES_GEOM[nivel]
            gw_an = min(min(cx - rho, ARENA - cx - rho, cy - rho, ARENA - cy - rho) - r
                        for cx, cy, r, rho in obs)
            go_an = min([math.hypot(a[0] - b[0], a[1] - b[1]) - a[3] - b[3] - a[2] - b[2]
                         for k, a in enumerate(obs) for b in obs[k + 1:]] or [math.inf])
            hs = [huecos_semilla(nivel, fases_regeneradas(nivel, s)) for s in sem]
            gw_s = min(round(h[0], 4) for h in hs)
            go_s = min(round(h[1], 4) for h in hs) if len(obs) > 1 else math.inf
            for j, v in ((2, gw_an), (3, go_an), (4, gw_s), (5, go_s)):
                cuenta.comparar(f"pasabilidad {nivel} ({j})", mm.group(j), format(v, ".4f"))
            cuenta.comparar(f"pasabilidad {nivel} instantes", mm.group(6),
                            str(len(sem) * (PASOS + 1)))
            cuenta.comparar(f"pasabilidad {nivel} fallidos", mm.group(7), "0")
            reconocida = True
        elif _RE_REG_STACK.match(linea):
            vistos.append(("reg_stack",))
            cuenta.exigir("stack igual a los requisitos congelados",
                          _RE_REG_STACK.match(linea).group(1).endswith(
                              "igual a requisitos_congelados_2026-09-09"))
            reconocida = True
        if not reconocida and re.search(r"\d", linea) and not linea.startswith(PREFIJOS_SIN_CIFRAS):
            sin_verificar.append(linea)

    # Completitud contra el diseño
    E = esperado(datos, sem)
    V = set(vistos)
    for k in sorted(E - V):
        cuenta.exigir(f"FALTA en el resumen: {k}", False)
    for k in sorted(V - E):
        cuenta.exigir(f"SOBRA en el resumen: {k}", False)
    duplicados = sorted({v for v in vistos if vistos.count(v) > 1})
    for k in duplicados:
        cuenta.exigir(f"DUPLICADO en el resumen: {k}", False)
    cuenta.exigir(f"completitud: {len(E)} bloques y filas esperados, todos presentes, "
                  f"sin sobrantes ni duplicados", not (E - V) and not (V - E) and not duplicados)
    # Regla de parada: ningún nivel después de uno cuyo Sk_din falló.
    niveles = [k for k in NIVELES if f"{k}_din" in datos]
    for j, k in enumerate(niveles[:-1]):
        cuenta.exigir(f"parada: {k}_din no falla y por eso corrió {niveles[j + 1]}",
                      not falla_din(datos, k, sem))
    cuenta.exigir("parada: los niveles corridos son consecutivos desde S1",
                  niveles == list(NIVELES[:len(niveles)]))
    return sin_verificar


# =============================================================================
# C. PAREO
# =============================================================================

def verificar_pareo(datos, cuenta: Contador) -> None:
    sem = sorted(next(iter(datos.values())).keys())
    for k in NIVELES:
        if f"{k}_din" not in datos:
            continue
        for s in sem:
            fases = {t: datos[f"{k}_{t}"][s]["fases"] for t in TIPOS}
            regen = ";".join(repr(x) for x in fases_regeneradas(k, s))
            cuenta.exigir(f"pareo {k} {s}: fases iguales en las cuatro y = default_rng",
                          len(set(fases.values())) == 1 and fases["din"] == regen)
            for m_ in ("agentes_reubicados", "objetivos_reubicados"):
                vals = {datos[f"{k}_{t}"][s][m_] for t in TIPOS}
                cuenta.exigir(f"pareo {k} {s}: {m_} iguales", len(vals) == 1)


# =============================================================================
# B. ENTRADA DE LA BITÁCORA
# =============================================================================

def _d(datos, sem):
    """Atajos de cálculo para la lista de la bitácora."""
    def m(c: str, k: str) -> float:
        return media(col(datos, c, k, sem))

    def s(c: str, k: str) -> int:
        return int(math.fsum(col(datos, c, k, sem)))

    def mn(c: str, k: str) -> float:
        return min(col(datos, c, k, sem))

    def dif(a: str, b: str, k: str) -> Tuple[float, float, float]:
        return ic95([x - y for x, y in zip(col(datos, a, k, sem), col(datos, b, k, sem))])

    def n05(c: str) -> int:
        return sum(x > 0.5 for x in col(datos, c, "cbf_frac_interv", sem))
    return m, s, mn, dif, n05


RUTA_ENTRADA: Path = _CARPETA / "ENTRADA_BITACORA_expQ.md"
CODIGO_HUELLA: Tuple[str, ...] = (
    "lib/__init__.py", "lib/concentration_dynamics.py", "lib/filtro_cbf.py",
    "lib/swarm_env_skeleton.py", "modelos/modelo_sanidad.zip", "entorno_obstaculos.py",
    "correr_experimento_O.py", "entorno_obstaculos_moviles.py", "correr_experimento_Q.py")


def _huella_propia() -> str:
    """La huella del código, recalculada con código propio."""
    import hashlib
    h = hashlib.sha256()
    for rel in CODIGO_HUELLA:
        h.update(rel.encode("utf-8"))
        h.update(hashlib.sha256((_CARPETA / rel).read_bytes()).hexdigest().encode("utf-8"))
    return h.hexdigest()


def _huellas_de_registros() -> List[str]:
    salida = []
    for nombre in ("pasabilidad_Q.txt", "control_negativo_Q.txt", "control_bit_a_bit_Q.txt",
                   "registro_Q.txt"):
        for linea in (DIR_RES / nombre).read_text(encoding="utf-8").splitlines():
            if linea.startswith("HUELLA "):
                salida.append(linea.split()[1])
    return salida


def _semillas_con(datos, c: str, m: str, sem) -> List[int]:
    return [s for s in sem if float(datos[c][s][m]) > 0]


def _exp_o(c: str, m: str) -> List[float]:
    o = cargar(RUTA_O)
    return [float(o[c][s][m]) for s in sorted(o[c])]


def _hueco(nivel: str, j: int) -> float:
    return min(round(huecos_semilla(nivel, fases_regeneradas(nivel, s))[j], 4)
               for s in [420000 + i for i in range(100)])


def cifras_bitacora() -> List[Tuple[str, Callable, str, str]]:
    """(descripción, función(datos, sem) → valor, formato, valor en la entrada)."""
    def M(c, k):
        return lambda d, s: media(col(d, c, k, s))

    def S(c, k):
        return lambda d, s: int(math.fsum(col(d, c, k, s)))

    def MN(c, k):
        return lambda d, s: min(col(d, c, k, s))

    def D(a, b, k, j):
        return lambda d, s: ic95([x - y for x, y in zip(col(d, a, k, s), col(d, b, k, s))])[j]

    def N05(c):
        return lambda d, s: sum(x > 0.5 for x in col(d, c, "cbf_frac_interv", s))

    def ctl():
        return comparar_control(cargar(RUTA_CONTROL))

    def neg():
        return [r for por in cargar(RUTA_NEG).values() for r in por.values()]

    def omega(d, s):
        p = col(d, "S1_din", "f1_parte_omega_media", s)
        n = col(d, "S1_din", "f1_parte_omega_n", s)
        return math.fsum(a * b for a, b in zip(p, n)) / math.fsum(n)

    def dif_ag(d, s):
        return sum(x != y for x, y in zip(col(d, "S1_din", "escape_agotados", s),
                                          col(d, "S1_ctrl", "escape_agotados", s)))

    def dexp(k):
        return lambda d, s: media([a - b for a, b in zip(_exp_o(k, "cobertura_accesible"),
                                                         _exp_o(f"{k}_ctrl", "cobertura_accesible"))])

    def huellas_ok(d, s):
        hs = _huellas_de_registros()
        return len(hs) == 4 and sorted(set(hs)) == [_huella_propia()]

    L: List[Tuple[str, Callable, str, str]] = [
        ("control: corridas distintas", lambda d, s: ctl()[0], "{}", "1000"),
        ("control: principal iguales", lambda d, s: ctl()[1][0], "{}", "700"),
        ("control: principal filas", lambda d, s: ctl()[1][1], "{}", "700"),
        ("control: principal columnas", lambda d, s: ctl()[1][2], "{}", "43"),
        ("control: complementario iguales", lambda d, s: ctl()[2][0], "{}", "900"),
        ("control: complementario filas", lambda d, s: ctl()[2][1], "{}", "900"),
        ("control: complementario columnas", lambda d, s: ctl()[2][2], "{}", "49"),
        ("pasabilidad S1 pared", lambda d, s: _hueco("S1", 0), "{:.4f}", "0.6000"),
        ("pasabilidad S2 pared", lambda d, s: _hueco("S2", 0), "{:.4f}", "0.5500"),
        ("pasabilidad S2 obst-obst", lambda d, s: _hueco("S2", 1), "{:.4f}", "0.5142"),
        ("pasabilidad S3 pared", lambda d, s: _hueco("S3", 0), "{:.4f}", "0.4900"),
        ("pasabilidad S3 obst-obst", lambda d, s: _hueco("S3", 1), "{:.4f}", "0.4907"),
        ("pasabilidad instantes por nivel", lambda d, s: 100 * (PASOS + 1), "{}", "50100"),
        ("negativo: contactos",
         lambda d, s: sum(int(r["contactos_obst_eventos"]) for r in neg()), "{}", "628"),
        ("negativo: por empuje",
         lambda d, s: sum(int(r["contactos_obst_empuje"]) for r in neg()), "{}", "37"),
        ("negativo: episodios con contacto",
         lambda d, s: sum(int(r["contactos_obst_eventos"]) > 0 for r in neg()), "{}", "10"),
        ("filas del CSV del experimento", lambda d, s: sum(len(v) for v in d.values()), "{}", "400"),
        ("filas del negativo", lambda d, s: len(neg()), "{}", "10"),
    ]
    for c in ("S1_quieto", "S1_din", "S1_sinvel"):
        L += [(f"{c} contactos", S(c, "contactos_obst_eventos"), "{}", "0"),
              (f"{c} filas saturadas", S(c, "f1_filas_saturadas"), "{}", "0")]
    for c in ("S1_ctrl", "S1_quieto", "S1_din", "S1_sinvel"):
        L += [(f"{c} colisiones 0,15", S(c, "colisiones_015"), "{}", "0"),
              (f"{c} fallbacks", S(c, "qp_fallbacks"), "{}", "0")]
    L += [(f"{c} agotados", S(c, "escape_agotados"), "{}", v)
          for c, v in (("S1_ctrl", "1"), ("S1_quieto", "2"), ("S1_din", "1"), ("S1_sinvel", "2"))]
    L += [(f"{c} infactibles junto obst", S(c, "escape_infactibles_junto_obst"), "{}", v)
          for c, v in (("S1_quieto", "0"), ("S1_din", "0"), ("S1_sinvel", "1"))]
    L += [(f"{c} d_min", MN(c, "d_min_obst_superficie"), "{:.8f}", v)
          for c, v in (("S1_quieto", "0.16846609"), ("S1_din", "0.12495033"),
                       ("S1_sinvel", "0.12478619"))]
    L += [(f"{c} intervención", M(c, "cbf_frac_interv"), "{:.6f}", v)
          for c, v in (("S1_ctrl", "0.397176"), ("S1_quieto", "0.524344"),
                       ("S1_din", "0.547856"), ("S1_sinvel", "0.547556"))]
    L += [(f"{c} > 0,5", N05(c), "{}", v)
          for c, v in (("S1_ctrl", "15"), ("S1_quieto", "58"), ("S1_din", "73"),
                       ("S1_sinvel", "74"))]
    L += [
        ("semilla del agotado de S1_din",
         lambda d, s: _semillas_con(d, "S1_din", "escape_agotados", s), "{}", "[420001]"),
        ("420001 con agotado en las cuatro",
         lambda d, s: sum(420001 in _semillas_con(d, f"S1_{t}", "escape_agotados", s)
                          for t in TIPOS), "{}", "4"),
        ("Δ agotados din − ctrl", D("S1_din", "S1_ctrl", "escape_agotados", 0), "{:.1f}", "0.0"),
        ("semillas con Δ agotados ≠ 0", dif_ag, "{}", "0"),
        ("agentes reubicados en 420001",
         lambda d, s: d["S1_din"][420001]["agentes_reubicados"], "{}", "2"),
        ("Exp O S0 420001 agotados",
         lambda d, s: cargar(RUTA_O)["S0"][420001]["escape_agotados"], "{}", "0"),
        ("S1_din agente-eps bajo 0,13", S("S1_din", "viol_cota_obst_agente_eps"), "{}", "2"),
        ("S1_din a más de 4,9 cm del disco de contacto",
         lambda d, s: min(col(d, "S1_din", "d_min_obst_superficie", s)) - 0.075 > 0.049,
         "{}", "True"),
        ("Exp O S2 d_min", lambda d, s: min(_exp_o("S2", "d_min_obst_superficie")),
         "{:.8f}", "0.12876785"),
        ("Exp O S2 Δ cobertura accesible", dexp("S2"), "{:+.4f}", "+0.0288"),
        ("Exp O S3 Δ cobertura accesible", dexp("S3"), "{:+.4f}", "+0.0183"),
    ]
    for (a, b, k), vals in (
            (("S1_din", "S1_ctrl", "cobertura_accesible"),
             ("+0.03331428", "+0.02030114", "+0.04632743")),
            (("S1_din", "S1_quieto", "cob_acc_arranque"),
             ("+0.01298304", "+0.00209123", "+0.02387485")),
            (("S1_quieto", "S1_ctrl", "cob_acc_arranque"),
             ("+0.02106630", "+0.00793127", "+0.03420133")),
            (("S1_sinvel", "S1_din", "cobertura_accesible"),
             ("+0.00042739", "−0.00819487", "+0.00904964")),
            (("S1_din", "S1_ctrl", "cbf_frac_interv"),
             ("+0.15068000", "+0.12957251", "+0.17178749")),
            (("S1_din", "S1_ctrl", "cbf_frac_lig_pared"),
             ("+0.04834400", "+0.02882004", "+0.06786796")),
            (("S1_din", "S1_ctrl", "frac_agente_paso_periferia_050"),
             ("+0.05712000", "+0.04235515", "+0.07188485")),
            (("S1_din", "S1_quieto", "cbf_frac_interv"),
             ("+0.02351200", "+0.00371723", "+0.04330677")),
            (("S1_din", "S1_quieto", "cbf_frac_lig_obst"),
             ("+0.01441200", "+0.00548351", "+0.02334049")),
            (("S1_din", "S1_quieto", "cbf_frac_lig_pared"),
             ("+0.00577200", "−0.01286624", "+0.02441024")),
            (("S1_sinvel", "S1_din", "cbf_frac_interv"),
             ("−0.00030000", "−0.01184459", "+0.01124459"))):
        for j, v in enumerate(vals):
            L.append((f"{a} − {b} {k} ({('Δ', 'lo', 'hi')[j]})", D(a, b, k, j), "{:+.8f}", v))
    L += [
        ("din − ctrl obstáculo ligante", D("S1_din", "S1_ctrl", "cbf_frac_lig_obst", 0),
         "{:+.6f}", "+0.097652"),
        ("din − quieto periferia Δ",
         D("S1_din", "S1_quieto", "frac_agente_paso_periferia_050", 0), "{:+.5f}", "+0.00014"),
        ("din − quieto periferia lo",
         D("S1_din", "S1_quieto", "frac_agente_paso_periferia_050", 1), "{:+.4f}", "−0.0135"),
        ("din − quieto periferia hi",
         D("S1_din", "S1_quieto", "frac_agente_paso_periferia_050", 2), "{:+.4f}", "+0.0137"),
        ("S1_din exposición activo", M("S1_din", "expo_frac_obst_activo"), "{:.8f}", "0.10824800"),
        ("S1_din exposición acercándose", M("S1_din", "expo_frac_activo_acercandose"),
         "{:.8f}", "0.05749600"),
        ("S1_din parte de ω", omega, "{:.6f}", "0.369415"),
        ("S1_din filas ligantes acercándose", S("S1_din", "f1_parte_omega_n"), "{}", "12914"),
        ("semilla del infactible de sinvel",
         lambda d, s: _semillas_con(d, "S1_sinvel", "escape_infactibles_junto_obst", s),
         "{}", "[420042]"),
        ("huella igual en los cuatro registros y en el código", huellas_ok, "{}", "True"),
        ("huella abreviada", lambda d, s: _huella_propia()[:8] + "…" + _huella_propia()[-4:],
         "{}", "e265b6cd…4a29"),
    ]
    return L


def cifras_citadas_en_la_entrada() -> List[str]:
    """Cada valor numérico de la lista tiene que aparecer, tal cual, en la entrada."""
    texto = RUTA_ENTRADA.read_text(encoding="utf-8") if RUTA_ENTRADA.exists() else ""
    faltan = []
    for desc, _fn, _fmt, citado in cifras_bitacora():
        if citado in ("True", "0", "1", "2", "4", "0.0") or citado.startswith("["):
            continue   # verificaciones lógicas o recuentos sin un texto propio
        if citado not in texto:
            faltan.append(f"{desc}: {citado!r} no está en la entrada")
    return faltan


CIFRAS_BITACORA: List[Tuple[str, Callable, str, str]] = []


def verificar_bitacora(datos, cuenta: Contador) -> None:
    sem = sorted(next(iter(datos.values())).keys())
    for x in cifras_citadas_en_la_entrada():
        cuenta.exigir(x, False)
    for desc, fn, fmt, citado in CIFRAS_BITACORA or cifras_bitacora():
        try:
            calc = fmt.format(fn(datos, sem))
        except (KeyError, ValueError, ZeroDivisionError, TypeError) as e:
            calc = f"ERROR {type(e).__name__}: {e}"
        cuenta.comparar("bitácora: " + desc, citado.replace("−", "-"), calc)


def main() -> int:
    datos = cargar(RUTA_CSV)
    if any(len(e) + 2 > 46 for e in list(ETIQUETAS) + list(MINIMOS)):
        raise SystemExit("una etiqueta excede las 46 columnas del resumen")
    a = Contador()
    sin_verificar = verificar_resumen(datos, a)
    b = Contador()
    verificar_bitacora(datos, b)
    c = Contador()
    verificar_pareo(datos, c)
    for x in a.malas + b.malas + c.malas:
        print("NO  " + x)
    for x in sin_verificar:
        print("SIN VERIFICAR  " + x)
    print(f"A. resumen: {a.ok}/{a.total} cifras y chequeos coinciden; líneas con cifras "
          f"sin verificar: {len(sin_verificar)}")
    print(f"B. bitácora: {b.ok}/{b.total} cifras coinciden")
    print(f"C. pareo: {c.ok}/{c.total} chequeos coinciden")
    ok = (not a.malas and not b.malas and not c.malas and not sin_verificar
          and a.total > 0 and b.total > 0 and c.total > 0)
    print("VEREDICTO: " + ("TODAS LAS CIFRAS COINCIDEN" if ok else "HAY DIFERENCIAS"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
