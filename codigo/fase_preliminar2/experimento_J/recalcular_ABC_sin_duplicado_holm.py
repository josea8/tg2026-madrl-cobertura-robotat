"""
recalcular_ABC_sin_duplicado_holm.py — recálculo de los análisis de correlación A, B y C del
Exp J sin la configuración duplicada (0≡2), con corrección de Holm.

Qué hace
────────
1. Lee `experimento_J.db` en SÓLO LECTURA (sqlite3, URI `mode=ro&immutable=1`)
   y reconstruye, prueba por prueba, exactamente las mismas filas que
   `analizar_estudio_J.py::cargar_pruebas` (se salta las pruebas sin
   parámetros; parámetros en representación externa de Optuna; atributos de
   usuario decodificados de JSON).
2. Reproduce los tres análisis tal como los arma `analizar_estudio_J.py::main`:
      A: completas (cobertura_media no nula) vs `cobertura_media`
      B: todas las filas con parámetros   vs `cob_semilla_42`
      C: completas                          vs `colisiones_media`
   con `scipy.stats.spearmanr` por hiperparámetro (4).
3. CONTROL: con el duplicado incluido debe reproducir BIT A BIT los ρ y p de
   `resultados/analisis/comparativa.json` y, redondeados, la tabla de la
   bitácora (`BITACORA_TECNICA.md:1184-1187`). Si un análisis no reproduce, se
   PARA ese análisis (no se reporta su versión sin duplicado).
4. Sin el duplicado: se quita la prueba 2 (repite a la 0; la reutilizó del
   caché por hash) y se conserva la 0. Se verifica que la 3 (repite a la
   huérfana 1) no produce doble conteo.
5. Holm step-down con monotonicidad, familia = los 4 hiperparámetros de cada
   análisis; sensibilidad con la familia de 8 (A∪B). Verificación independiente
   de los p ajustados por prueba cerrada con Bonferroni local (fuerza bruta).
6. (Opcional, si Optuna está instalado) verificación cruzada del decodificado:
   copia la base con la API de respaldo de sqlite a un directorio temporal
   temporal del sistema y la carga con `optuna.load_study`, para comparar con
   el camino exacto de `cargar_pruebas`. Nunca abre la base del proyecto con
   Optuna.

Única salida en disco: `resultados/analisis/correlaciones_ABC_sin_duplicado_holm.json`
(archivo NUEVO; aborta si ya existe). No modifica la base ni ningún otro artefacto.
Agregado el 2026-09-24 como artefacto de la revisión de la bitácora (Exp J,
Resultado 3); verificado por una reproducción independiente.

Uso
───
    PYTHONDONTWRITEBYTECODE=1 python3 -B recalcular_ABC_sin_duplicado_holm.py
"""

from __future__ import annotations

import itertools
import json
import math
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import scipy
from scipy.stats import spearmanr, t as dist_t

# ══════════════════════════════════════════════════════════════════════════════
#  RUTAS Y CONSTANTES
# ══════════════════════════════════════════════════════════════════════════════

DIR_J: Path = Path(__file__).resolve().parent
RUTA_DB: Path = DIR_J / "optuna_studies" / "experimento_J.db"
RUTA_COMPARATIVA: Path = DIR_J / "resultados" / "analisis" / "comparativa.json"
DIR_ESTUDIO: Path = DIR_J / "resultados" / "estudio"
RUTA_SALIDA: Path = DIR_J / "resultados" / "analisis" / "correlaciones_ABC_sin_duplicado_holm.json"

PARAMS: Tuple[str, ...] = ("lambda_cbf", "lambda_entropy", "n_epochs", "n_steps_exp")
ALFA: float = 0.05

# Prueba que se retira: la 2 repite a la 0 (reutilizada del caché por hash).
PRUEBA_DUPLICADA: int = 2
PRUEBA_ORIGINAL: int = 0
# La 3 repite a la huérfana RUNNING 1.
PRUEBA_HUERFANA: int = 1
PRUEBA_REPITE_HUERFANA: int = 3

# Definición de los análisis, idéntica a `analizar_estudio_J.py::main`:
#   (nombre, conjunto, clave de la variable dependiente, clave en comparativa.json)
ANALISIS: Tuple[Tuple[str, str, str, str], ...] = (
    ("A", "completas", "cobertura_media",  "vs_cobertura"),
    ("B", "filas",     "cob_semilla_42",   "vs_cob_s42"),
    ("C", "completas", "colisiones_media", "vs_colisiones"),
)

# Valores publicados en la bitácora (texto tal cual, BITACORA_TECNICA.md:1184-1187)
PUBLICADO_BITACORA: Dict[str, Dict[str, Tuple[str, str]]] = {
    "A": {"lambda_cbf": ("+0.695", "0.026"), "lambda_entropy": ("-0.427", "0.219"),
          "n_epochs": ("+0.344", "0.331"),   "n_steps_exp": ("-0.895", "0.0005")},
    "B": {"lambda_cbf": ("+0.607", "0.036"), "lambda_entropy": ("-0.670", "0.017"),
          "n_epochs": ("+0.071", "0.827"),   "n_steps_exp": ("-0.832", "0.0008")},
    "C": {"lambda_cbf": ("+0.671", "0.034"), "lambda_entropy": ("-0.768", "0.009"),
          "n_epochs": ("-0.282", "0.430"),   "n_steps_exp": ("-0.712", "0.021")},
}
N_PUBLICADO: Dict[str, int] = {"A": 10, "B": 12, "C": 10}   # BITACORA_TECNICA.md:1176-1178


# ══════════════════════════════════════════════════════════════════════════════
#  CARGA EN SÓLO LECTURA
# ══════════════════════════════════════════════════════════════════════════════

def conectar_solo_lectura(ruta: Path) -> sqlite3.Connection:
    """Abre la base con URI `mode=ro&immutable=1`: sin escritura ni bloqueos."""
    uri = "file:" + ruta.as_posix() + "?mode=ro&immutable=1"
    return sqlite3.connect(uri, uri=True)


def a_representacion_externa(valor_interno: float, distribucion_json: str) -> Any:
    """
    Convierte el valor interno de `trial_params.param_value` a la representación
    externa que Optuna devuelve en `t.params`.

    Sólo se admiten las dos distribuciones presentes en la base
    (FloatDistribution e IntDistribution); cualquier otra aborta, para no
    reproducir mal el camino de Optuna en silencio.
    """
    dist = json.loads(distribucion_json)
    nombre = dist["name"]
    if nombre == "FloatDistribution":
        return float(valor_interno)
    if nombre == "IntDistribution":
        return int(valor_interno)
    raise ValueError(f"distribución no prevista: {nombre}")


def cargar_pruebas_sqlite(ruta: Path) -> List[Dict[str, Any]]:
    """
    Réplica de `analizar_estudio_J.py::cargar_pruebas` sobre sqlite3 en sólo
    lectura. Mismo orden (por número de prueba), mismo filtro (`if not
    t.params: continue`) y mismas claves.
    """
    con = conectar_solo_lectura(ruta)
    try:
        estudios = con.execute("SELECT study_id FROM studies WHERE study_name = ?",
                               ("experimento_J",)).fetchall()
        if len(estudios) != 1:
            raise RuntimeError(f"se esperaba un estudio 'experimento_J', hay {len(estudios)}")
        sid = estudios[0][0]
        pruebas = con.execute(
            "SELECT trial_id, number, state FROM trials WHERE study_id = ? ORDER BY number",
            (sid,)).fetchall()
        filas: List[Dict[str, Any]] = []
        for trial_id, numero, estado in pruebas:
            params: Dict[str, Any] = {
                nombre: a_representacion_externa(valor, dist)
                for nombre, valor, dist in con.execute(
                    "SELECT param_name, param_value, distribution_json "
                    "FROM trial_params WHERE trial_id = ?", (trial_id,))
            }
            if not params:
                continue
            attrs: Dict[str, Any] = {
                clave: json.loads(valor_json)
                for clave, valor_json in con.execute(
                    "SELECT key, value_json FROM trial_user_attributes WHERE trial_id = ?",
                    (trial_id,))
            }
            filas.append({
                "prueba": numero,
                "estado": estado,
                **{p: params.get(p) for p in PARAMS},
                "n_steps": 2 ** params["n_steps_exp"] if "n_steps_exp" in params else None,
                "cobertura_media":  attrs.get("cobertura_media"),
                "cobertura_std":    attrs.get("cobertura_std"),
                "cobertura_cv":     attrs.get("cobertura_cv"),
                "colisiones_media": attrs.get("colisiones_media"),
                "cob_semilla_42":   attrs.get("cob_semilla_42"),
                "sesgo_retencion":  attrs.get("sesgo_retencion_medio"),
                "pasos_retenidos":  attrs.get("pasos_retenidos"),
                "_attrs_crudos":    attrs,
            })
        return filas
    finally:
        con.close()


def verificacion_cruzada_optuna(filas_sqlite: List[Dict[str, Any]]) -> str:
    """
    Carga una COPIA de la base (hecha con la API de respaldo de sqlite desde la
    conexión de sólo lectura, dentro del scratchpad) con `optuna.load_study` y
    ejecuta el cuerpo exacto de `cargar_pruebas`. Compara campo por campo.
    """
    try:
        import optuna
    except Exception as exc:   # pragma: no cover - depende del entorno
        return f"OMITIDA (optuna no importable: {exc!r})"
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    # ignore_cleanup_errors: en Windows el pool de SQLAlchemy puede retener el
    # archivo de la COPIA un instante tras `dispose()`; no afecta al resultado.
    with tempfile.TemporaryDirectory(prefix="recalculo_AB_holm_",
                                     ignore_cleanup_errors=True) as tmp:
        copia = Path(tmp) / "copia_experimento_J.db"
        origen = conectar_solo_lectura(RUTA_DB)
        destino = sqlite3.connect(str(copia))
        try:
            origen.backup(destino)
        finally:
            destino.close()
            origen.close()
        almacen = optuna.storages.RDBStorage(f"sqlite:///{copia.as_posix()}")
        estudio = optuna.load_study(study_name="experimento_J", storage=almacen)
        filas_opt: List[Dict[str, Any]] = []
        for t in estudio.trials:
            if not t.params:
                continue
            filas_opt.append({
                "prueba": t.number,
                "estado": t.state.name,
                **{p: t.params.get(p) for p in PARAMS},
                "n_steps": 2 ** t.params["n_steps_exp"] if "n_steps_exp" in t.params else None,
                "cobertura_media":  t.user_attrs.get("cobertura_media"),
                "cobertura_std":    t.user_attrs.get("cobertura_std"),
                "cobertura_cv":     t.user_attrs.get("cobertura_cv"),
                "colisiones_media": t.user_attrs.get("colisiones_media"),
                "cob_semilla_42":   t.user_attrs.get("cob_semilla_42"),
                "sesgo_retencion":  t.user_attrs.get("sesgo_retencion_medio"),
                "pasos_retenidos":  t.user_attrs.get("pasos_retenidos"),
            })
        del estudio
        almacen.engine.dispose()
        del almacen
    claves = [k for k in filas_opt[0].keys()] if filas_opt else []
    a = [{k: f[k] for k in claves} for f in filas_sqlite]
    if a != filas_opt:
        raise RuntimeError("el decodificado sqlite NO coincide con optuna.load_study")
    tipos_ok = all(type(x[p]) is type(y[p]) for x, y in zip(a, filas_opt) for p in PARAMS)
    return (f"OK: {len(filas_opt)} filas idénticas a optuna.load_study "
            f"(optuna {optuna.__version__}), tipos de parámetros idénticos: {tipos_ok}")


# ══════════════════════════════════════════════════════════════════════════════
#  ANÁLISIS
# ══════════════════════════════════════════════════════════════════════════════

def correlaciones(filas: List[Dict[str, Any]], clave: str
                  ) -> Dict[str, Tuple[float, float, int, List[int]]]:
    """
    Igual que `analizar_estudio_J.py::correlaciones` (Spearman de scipy, filas
    con la variable y el parámetro no nulos, NaN si n < 3), devolviendo además
    n y los números de prueba que entraron.
    """
    res: Dict[str, Tuple[float, float, int, List[int]]] = {}
    for p in PARAMS:
        validas = [f for f in filas if f.get(clave) is not None and f.get(p) is not None]
        x = np.array([f[p] for f in validas], dtype=float)
        y = np.array([f[clave] for f in validas], dtype=float)
        pruebas = [int(f["prueba"]) for f in validas]
        if len(x) < 3:
            res[p] = (float("nan"), float("nan"), len(x), pruebas)
            continue
        rho, pval = spearmanr(x, y)
        res[p] = (float(rho), float(pval), len(x), pruebas)
    return res


def holm(pvals: Sequence[float]) -> List[float]:
    """
    p ajustados de Holm (step-down) con monotonicidad forzada:
        p̃_(k) = max_{j ≤ k} min(1, (m − j + 1) · p_(j)),  k = 1..m
    en el orden creciente de los p crudos. Rechazar H_i ⇔ p̃_i ≤ α.
    """
    m = len(pvals)
    orden = sorted(range(m), key=lambda i: pvals[i])
    ajust = [0.0] * m
    acumulado = 0.0
    for k, i in enumerate(orden):
        acumulado = max(acumulado, min(1.0, (m - k) * pvals[i]))
        ajust[i] = acumulado
    return ajust


def holm_decisiones_secuenciales(pvals: Sequence[float], alfa: float) -> List[bool]:
    """Procedimiento step-down literal: se detiene en el primer p_(k) > α/(m−k+1)."""
    m = len(pvals)
    orden = sorted(range(m), key=lambda i: pvals[i])
    rechaza = [False] * m
    for k, i in enumerate(orden):
        if pvals[i] <= alfa / (m - k):
            rechaza[i] = True
        else:
            break
    return rechaza


def holm_por_prueba_cerrada(pvals: Sequence[float]) -> List[float]:
    """
    Verificación independiente: Holm ≡ prueba cerrada con Bonferroni local.
    p̃_i = max_{S ∋ i} min(1, |S| · min_{j∈S} p_j), por fuerza bruta.
    """
    m = len(pvals)
    salida = []
    for i in range(m):
        peor = 0.0
        otros = [j for j in range(m) if j != i]
        for r in range(0, m):
            for sub in itertools.combinations(otros, r):
                S = (i,) + sub
                peor = max(peor, min(1.0, len(S) * min(pvals[j] for j in S)))
        salida.append(peor)
    return salida


def rho_critico(n: int, alfa: float) -> float:
    """|ρ| mínimo con p bilateral ≤ α bajo la aproximación t de scipy (df = n−2)."""
    tc = float(dist_t.ppf(1.0 - alfa / 2.0, n - 2))
    return tc / math.sqrt(n - 2 + tc * tc)


def fmt_bitacora_rho(r: float) -> str:
    return f"{r:+.3f}"


def coincide_bitacora(r: float, p: float, pub: Tuple[str, str]) -> bool:
    """El valor recalculado redondeado al número de decimales publicado."""
    rho_txt, p_txt = pub
    dec_p = len(p_txt.split(".")[1])
    return fmt_bitacora_rho(r) == rho_txt and f"{p:.{dec_p}f}" == p_txt


# ══════════════════════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    print(f"python {sys.version.split()[0]} · numpy {np.__version__} · scipy {scipy.__version__}")
    print(f"base (sólo lectura, immutable): {RUTA_DB}\n")

    filas = cargar_pruebas_sqlite(RUTA_DB)
    completas = [f for f in filas if f["cobertura_media"] is not None]
    print(f"filas con parámetros: {len(filas)} · completas: {len(completas)}")
    print("estados:", {e: sum(f["estado"] == e for f in filas)
                       for e in sorted({f["estado"] for f in filas})})

    # ── Verificación cruzada con Optuna (sobre copia en scratch) ────────────
    print("verificación cruzada optuna:", verificacion_cruzada_optuna(filas))

    # ── Caracterización de los duplicados ──────────────────────────────────
    por_num = {f["prueba"]: f for f in filas}
    d0, d2 = por_num[PRUEBA_ORIGINAL], por_num[PRUEBA_DUPLICADA]
    h1, h3 = por_num[PRUEBA_HUERFANA], por_num[PRUEBA_REPITE_HUERFANA]
    mismos_params_02 = all(d0[p] == d2[p] for p in PARAMS)
    mismos_attrs_02 = d0["_attrs_crudos"] == d2["_attrs_crudos"]
    mismos_params_13 = all(h1[p] == h3[p] for p in PARAMS)
    print(f"\nDUPLICADO 0≡2: parámetros idénticos bit a bit = {mismos_params_02}; "
          f"atributos de usuario idénticos = {mismos_attrs_02}; estados {d0['estado']}/{d2['estado']}")
    print(f"DUPLICADO 1≡3: parámetros idénticos bit a bit = {mismos_params_13}; "
          f"estado 1 = {h1['estado']}; atributos de la 1 = {sorted(h1['_attrs_crudos'])}")
    # Todas las colisiones de configuración entre filas con parámetros
    grupos: Dict[Tuple[Any, ...], List[int]] = {}
    for f in filas:
        grupos.setdefault(tuple(f[p] for p in PARAMS), []).append(f["prueba"])
    repetidas = {k: v for k, v in grupos.items() if len(v) > 1}
    print(f"configuraciones distintas: {len(grupos)} en {len(filas)} filas; "
          f"grupos repetidos: {list(repetidas.values())}")
    if not (mismos_params_02 and mismos_params_13):
        print("ABORTO: los duplicados declarados no son idénticos en la base.")
        return 2

    filas_sin = [f for f in filas if f["prueba"] != PRUEBA_DUPLICADA]
    completas_sin = [f for f in completas if f["prueba"] != PRUEBA_DUPLICADA]
    conjuntos = {"filas": (filas, filas_sin), "completas": (completas, completas_sin)}

    # ── Control y recálculo ────────────────────────────────────────────────
    publicado_json = json.loads(RUTA_COMPARATIVA.read_text(encoding="utf-8"))["correlaciones"]

    salida: Dict[str, Any] = {"versiones": {"python": sys.version.split()[0],
                                            "numpy": np.__version__, "scipy": scipy.__version__},
                              "analisis": {}}
    reproducen: Dict[str, bool] = {}
    for nombre, conj, clave, clave_json in ANALISIS:
        con_dup, sin_dup = conjuntos[conj]
        r_con = correlaciones(con_dup, clave)
        r_sin = correlaciones(sin_dup, clave)

        print(f"\n══ ANÁLISIS {nombre}: {clave} sobre '{conj}' ══")
        ok_json = all(r_con[p][0] == publicado_json[clave_json][p][0]
                      and r_con[p][1] == publicado_json[clave_json][p][1] for p in PARAMS)
        ok_bit = all(coincide_bitacora(r_con[p][0], r_con[p][1], PUBLICADO_BITACORA[nombre][p])
                     for p in PARAMS)
        ok_n = all(r_con[p][2] == N_PUBLICADO[nombre] for p in PARAMS)
        reproducen[nombre] = ok_json and ok_bit and ok_n
        print(f"CONTROL con duplicado: bit a bit vs comparativa.json = {ok_json}; "
              f"redondeo vs bitácora = {ok_bit}; n = {r_con[PARAMS[0]][2]} "
              f"(publicado {N_PUBLICADO[nombre]}) → {'REPRODUCE' if reproducen[nombre] else 'NO REPRODUCE'}")
        print(f"  pruebas con duplicado: {r_con[PARAMS[0]][3]}")
        if not reproducen[nombre]:
            print(f"  PARADA: el análisis {nombre} no reproduce; no se reporta su versión sin duplicado.")
            salida["analisis"][nombre] = {"reproduce": False}
            continue

        # Doble conteo: dentro de lo que entra, ninguna configuración repetida
        entra = r_sin[PARAMS[0]][3]
        cfgs = [tuple(por_num[n][p] for p in PARAMS) for n in entra]
        sin_repetir = len(set(cfgs)) == len(cfgs)
        print(f"  pruebas sin duplicado: {entra}  (n = {len(entra)}); "
              f"configuraciones repetidas dentro del conjunto: {not sin_repetir}; "
              f"¿entra la 1? {PRUEBA_HUERFANA in entra} · ¿entra la 3? {PRUEBA_REPITE_HUERFANA in entra}")
        tenia_dup = PRUEBA_DUPLICADA in r_con[PARAMS[0]][3] and PRUEBA_ORIGINAL in r_con[PARAMS[0]][3]
        print(f"  ¿el conjunto publicado contenía 0 y 2 a la vez? {tenia_dup}")

        p_con = [r_con[p][1] for p in PARAMS]
        p_sin = [r_sin[p][1] for p in PARAMS]
        hc, hs = holm(p_con), holm(p_sin)
        # Verificaciones independientes de Holm
        assert all(abs(a - b) <= 1e-15 for a, b in zip(hs, holm_por_prueba_cerrada(p_sin)))
        assert all(abs(a - b) <= 1e-15 for a, b in zip(hc, holm_por_prueba_cerrada(p_con)))
        assert [h <= ALFA for h in hs] == holm_decisiones_secuenciales(p_sin, ALFA)
        assert [h <= ALFA for h in hc] == holm_decisiones_secuenciales(p_con, ALFA)

        print(f"  {'parámetro':<15} | {'ρ con dup':>22} {'p con dup':>24} {'pHolm4 con dup':>24} | "
              f"{'ρ SIN dup':>22} {'p SIN dup':>24} {'pHolm4 SIN dup':>24} {'dec α=0.05':>10} n")
        detalle: Dict[str, Any] = {}
        for i, p in enumerate(PARAMS):
            print(f"  {p:<15} | {r_con[p][0]!r:>22} {r_con[p][1]!r:>24} {hc[i]!r:>24} | "
                  f"{r_sin[p][0]!r:>22} {r_sin[p][1]!r:>24} {hs[i]!r:>24} "
                  f"{('RECHAZA' if hs[i] <= ALFA else 'no rech.'):>10} {r_sin[p][2]}")
            detalle[p] = {
                "con_duplicado": {"rho": r_con[p][0], "p": r_con[p][1], "p_holm_fam4": hc[i],
                                  "rechaza_holm4": hc[i] <= ALFA, "n": r_con[p][2]},
                "sin_duplicado": {"rho": r_sin[p][0], "p": r_sin[p][1], "p_holm_fam4": hs[i],
                                  "rechaza_holm4": hs[i] <= ALFA, "rechaza_crudo": r_sin[p][1] <= ALFA,
                                  "n": r_sin[p][2], "pruebas": r_sin[p][3]},
            }
        salida["analisis"][nombre] = {"reproduce": True, "clave": clave, "conjunto": conj,
                                      "tenia_duplicado": tenia_dup, "detalle": detalle}

    # ── Sensibilidad: familia de 8 (A ∪ B) ─────────────────────────────────
    if reproducen.get("A") and reproducen.get("B"):
        etiquetas = [f"{a}-{p}" for a in ("A", "B") for p in PARAMS]
        for version in ("con_duplicado", "sin_duplicado"):
            p8 = [salida["analisis"][a]["detalle"][p][version]["p"] for a in ("A", "B") for p in PARAMS]
            h8 = holm(p8)
            assert all(abs(x - y) <= 1e-15 for x, y in zip(h8, holm_por_prueba_cerrada(p8)))
            assert [h <= ALFA for h in h8] == holm_decisiones_secuenciales(p8, ALFA)
            print(f"\nSENSIBILIDAD Holm familia de 8 (A∪B), {version}:")
            for e, pv, hv in zip(etiquetas, p8, h8):
                print(f"  {e:<18} p = {pv!r:<24} pHolm8 = {hv!r:<24} "
                      f"{'RECHAZA' if hv <= ALFA else 'no rech.'}")
                a, p = e.split("-", 1)
                salida["analisis"][a]["detalle"][p][version]["p_holm_fam8_AuB"] = hv
                salida["analisis"][a]["detalle"][p][version]["rechaza_holm8"] = hv <= ALFA

    # ── Referencia de potencia: |ρ| crítico ────────────────────────────────
    print("\n|ρ| CRÍTICO (aprox. t de scipy, bilateral):")
    salida["rho_critico"] = {}
    for n in (9, 10, 11, 12):
        fila = {f"alfa_{a}": rho_critico(n, a) for a in (0.05, 0.05 / 4, 0.05 / 8)}
        salida["rho_critico"][str(n)] = fila
        print(f"  n = {n:>2}: α=0.05 → {fila['alfa_0.05']:.4f} · α/4 → {fila['alfa_0.0125']:.4f} "
              f"· α/8 → {fila['alfa_0.00625']:.4f}")

    # ── Informativo: D y E (paso fijo) no dependen de la base ──────────────
    # Las curvas se leen por directorio de hash de configuración, así que 0≡2
    # comparten un único directorio. Se cuenta además cuántas curvas tienen los
    # parámetros (config_barridos.json), que es lo que exige `correlaciones`.
    rutas = sorted(DIR_ESTUDIO.glob("cfg_*/semilla_*/resultado_semilla.json"))
    con_paso = sin_barridos = 0
    for ruta in rutas:
        d = json.loads(ruta.read_text(encoding="utf-8"))
        if any(pt["pasos"] == 200_000 for pt in d["curva"]):
            con_paso += 1
            if not (ruta.parent.parent / "config_barridos.json").exists():
                sin_barridos += 1
    print(f"\nD/E (informativo): curvas {len(rutas)}, con punto a 200k {con_paso}, "
          f"de ellas sin config_barridos.json (descartadas por `correlaciones`) {sin_barridos} "
          f"→ n efectivo de D/E = {con_paso - sin_barridos}")
    salida["DE_informativo"] = {"curvas": len(rutas), "con_200k": con_paso,
                                "sin_config_barridos": sin_barridos,
                                "n_efectivo": con_paso - sin_barridos}

    if RUTA_SALIDA.exists():
        sys.exit(f"ABORTADO: {RUTA_SALIDA} ya existe (nunca sobrescribir resultados)")
    RUTA_SALIDA.write_bytes((json.dumps(salida, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    print(f"\nsalida → {RUTA_SALIDA}")
    return 0 if all(reproducen.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
