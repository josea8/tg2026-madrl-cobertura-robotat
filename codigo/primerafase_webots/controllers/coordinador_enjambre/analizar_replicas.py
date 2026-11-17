"""
analizar_replicas.py — comparación pareada hardware vs réplica de UNA sesión
de evaluación física.

  hardware            : CSV de episodios de la sesión (`--sesion`; por
                        defecto la del 11-09-2026), sólo válidos
  réplica CON capas   : política + CBF + escape, pila del lab contra el
                        simulador (`replica_con_capas.py --capas on`)
  réplica SIN capas   : política sola, MISMO motor que la anterior
  réplica vieja       : `cobertura_replica` del propio CSV de la sesión
                        (`_replica_simulada`, env de entrenamiento, sin capas;
                        sesgada a la baja, se muestra sólo como referencia)

Pareo por episodio (misma semilla, misma pose inicial medida, misma rampa).
Cada réplica se corrió varias veces; se usa la media por episodio y se
reporta su dispersión, que es el ruido propio de la réplica.

Las réplicas se atan a SU sesión por la columna `fuente_episodios` que
escribe `replica_con_capas.py`, no por el nombre del archivo ni por "la más
reciente": así no se puede comparar una sesión contra la réplica de otra.
Las dos réplicas del 12-09 son anteriores a esa columna y son, por
construcción, de la sesión del 11-09. Si hay varias réplicas de la misma
sesión y condición, se usa la última (por nombre) y se avisa.

Uso:
    python analizar_replicas.py                     # sesión del 11-09
    python analizar_replicas.py --sesion AAAAMMDD_sesion-evaluacion_etapa7_episodios.csv
"""
import argparse
import csv
import glob
import sys
from math import sqrt
from pathlib import Path

import numpy as np
from scipy import stats

RES = Path(__file__).resolve().parent / "resultados_sesion"
SESION_LEGADO = "20260911_sesion-evaluacion_etapa7_episodios.csv"
T975_4 = 2.7764

ap = argparse.ArgumentParser()
ap.add_argument("--sesion", default=SESION_LEGADO,
                help="CSV de episodios de la sesión física: ruta, o nombre "
                     f"dentro de resultados_sesion/. Por defecto {SESION_LEGADO}.")
args = ap.parse_args()

_p = Path(args.sesion)
CSV_HW = next((c for c in (_p, RES / _p.name) if c.is_file()), None)
if CSV_HW is None:
    sys.exit(f"✘ no encuentro el CSV de la sesión: {args.sesion}")

filas_hw = list(csv.DictReader(open(CSV_HW, encoding="utf-8")))
hw = {int(r["episodio"]): r for r in filas_hw if r["valido"] == "1"}
EPS = sorted(hw)
print(f"sesión: {CSV_HW.name}  ({len(EPS)} válidos de {len(filas_hw)} "
      f"intentos: {EPS})")
comp = next((r for r in filas_hw if r.get("robot_a0") not in (None, "")), None)
if comp is None:
    print("composición: no registrada en el CSV (anterior al 2026-09-22; la "
          "sesión del 11-09 fue con los robots 1, 2, 3, 6, 9)")
else:
    i, robots = 0, []
    while comp.get(f"robot_a{i}") not in (None, ""):
        robots.append(f"r{int(float(comp[f'robot_a{i}']))} "
                      f"{float(comp[f'offset_deg_a{i}']):+.2f}°"
                      if comp.get(f"offset_deg_a{i}") not in (None, "")
                      else f"r{int(float(comp[f'robot_a{i}']))}")
        i += 1
    print("composición (robot y offset de rumbo por agente): " + ", ".join(robots))
print("⚠ n y composición son los de ESTA sesión: no se suman a otra sin "
      "declararlo.")
if not EPS:
    sys.exit("✘ la sesión no tiene episodios válidos")


def fuente_de(fila):
    return fila.get("fuente_episodios") or SESION_LEGADO


def cargar(cond):
    candidatos = []
    for f in sorted(glob.glob(str(RES / f"*sesion-replica_etapa7_capas-{cond}*.csv"))):
        filas = [r for r in csv.DictReader(open(f, encoding="utf-8"))
                 if fuente_de(r) == CSV_HW.name]
        if filas:
            candidatos.append((f, filas))
    if not candidatos:
        print(f"réplica {cond.upper():3}: ninguna para esta sesión")
        return []
    f, filas = candidatos[-1]
    extra = (f"  · se ignoran {len(candidatos) - 1} anteriores de la misma "
             f"sesión" if len(candidatos) > 1 else "")
    print(f"réplica {cond.upper():3}: {Path(f).name}  ({len(filas)} corridas)"
          f"{extra}")
    return filas


on, off = cargar("on"), cargar("off")


def es_valida(r):
    return r["valido"] in ("1", "True")


def por_ep(filas, clave="cobertura_aoi"):
    d = {}
    for r in filas:
        if es_valida(r) and r.get(clave) not in (None, ""):
            d.setdefault(int(r["episodio"]), []).append(float(r[clave]))
    return d


def validez(filas, nombre):
    if not filas:
        return
    inval = [r for r in filas if not es_valida(r)]
    print(f"  {nombre}: {len(filas) - len(inval)}/{len(filas)} válidas"
          + ("" if not inval else "  · inválidas: " + "; ".join(
              f"ep{r['episodio']} rep{r['rep']} {r['motivo']}" for r in inval)))


print()
validez(on, "CON capas")
validez(off, "SIN capas")


def abortos(filas, nombre):
    """Episodios que no llegaron a 500 decisiones: cuántos, por qué, cuándo."""
    if not filas:
        return
    inv = [r for r in filas if not es_valida(r)]
    if not inv:
        print(f"  {nombre}: 0 abortos")
        return
    t = np.array([float(r["duracion_s"]) for r in inv])
    motivos = {}
    for r in inv:
        m = r["motivo"] or ""
        clave = "fuera de la arena" if "fuera de la arena" in m else m[:40]
        motivos[clave] = motivos.get(clave, 0) + 1
    print(f"  {nombre}: {len(inv)}/{len(filas)} abortados · t hasta abortar "
          f"mediana {np.median(t):.1f} s (rango {t.min():.1f}-{t.max():.1f} s de 50)"
          f" · motivos {motivos}")


print()
print("abortos por condición")
abortos(on, "CON capas")
abortos(off, "SIN capas")

H = {e: float(hw[e]["cobertura_aoi"]) for e in EPS}
V = {e: float(hw[e]["cobertura_replica"]) for e in EPS
     if hw[e].get("cobertura_replica") not in (None, "")}
c_on, c_off = por_ep(on), por_ep(off)

print("\ncobertura por episodio (media de repeticiones ± desvío entre reps)")
print(f"{'ep':>3} {'hw':>8} {'CON capas':>18} {'SIN capas':>18} {'vieja':>8}")
for e in EPS:
    a, b = c_on.get(e, []), c_off.get(e, [])
    fa = f"{np.mean(a):.4f}±{np.std(a, ddof=1) if len(a) > 1 else 0:.4f}({len(a)})" if a else "—"
    fb = f"{np.mean(b):.4f}±{np.std(b, ddof=1) if len(b) > 1 else 0:.4f}({len(b)})" if b else "—"
    fv = f"{V[e]:8.4f}" if e in V else f"{'—':>8}"
    print(f"{e:>3} {H[e]:8.4f} {fa:>18} {fb:>18} {fv}")

ruido = [np.std(v, ddof=1) for v in list(c_on.values()) + list(c_off.values())
         if len(v) > 1]
if ruido:
    print(f"\nruido de la réplica (desvío entre repeticiones): mediana "
          f"{np.median(ruido):.4f}  máx {np.max(ruido):.4f}")


def pareada(nombre, x, y):
    comunes = [e for e in EPS if e in x and e in y]
    a = np.array([x[e] for e in comunes])
    b = np.array([y[e] for e in comunes])
    d = a - b
    n = len(d)
    print(f"\n{nombre}   (n={n}, episodios {comunes})")
    if n < 2:
        print("  n insuficiente")
        return None
    sd = d.std(ddof=1)
    ic = (T975_4 * sd / sqrt(n)) if n == 5 else stats.t.ppf(0.975, n - 1) * sd / sqrt(n)
    print(f"  media {a.mean():.4f} vs {b.mean():.4f}")
    print(f"  diferencia {d.mean():+.4f} ± {sd:.4f}   IC95 [{d.mean()-ic:+.4f}, "
          f"{d.mean()+ic:+.4f}]   positivas {int((d > 0).sum())}/{n}")
    print(f"  t pareado p = {stats.ttest_rel(a, b).pvalue:.4f}", end="")
    try:
        print(f"   Wilcoxon p = {stats.wilcoxon(a, b).pvalue:.4f}")
    except ValueError as exc:
        print(f"   Wilcoxon: {exc}")
    return d


def n_necesario(d):
    """
    Con la media y el desvío observados de las diferencias, cuántos episodios
    harían falta (t de Student, no z) para que el IC95 excluya el cero y para
    potencia 0.80 a α=0.05 bilateral (t no central).
    """
    m, sd = abs(float(d.mean())), float(d.std(ddof=1))
    if m == 0.0 or sd == 0.0:
        print("\ntamaño de muestra: diferencia o desvío nulos, no se calcula")
        return
    # Con |dif|/sd chico ninguna n razonable alcanza: sin default, `next`
    # lanzaba StopIteration y el informe se cortaba acá (revisión 2026-09-22).
    n_ic = next((n for n in range(3, 10000)
                 if stats.t.ppf(0.975, n - 1) * sd / sqrt(n) < m), None)

    def potencia(n):
        gl, nc = n - 1, m / sd * sqrt(n)
        tc = stats.t.ppf(0.975, gl)
        return 1 - stats.nct.cdf(tc, gl, nc) + stats.nct.cdf(-tc, gl, nc)

    n_80 = (next((n for n in range(3, 10000) if potencia(n) >= 0.80), None)
            if m / sd >= 0.02 else None)

    def fmt(v):
        return str(v) if v is not None else "> 9999 (indistinguible de cero)"

    print(f"\ntamaño de muestra (|dif| {m:.4f}, sd {sd:.4f}, supuestos fijos):")
    print(f"  IC95 excluye el cero desde n = {fmt(n_ic)}   ·   potencia 0.80 "
          f"desde n = {fmt(n_80)}")
    print("  potencia a n = " + "  ".join(
        f"{n}: {potencia(n):.2f}" for n in (5, 10, 20)))


M_on = {e: float(np.mean(v)) for e, v in c_on.items()}
M_off = {e: float(np.mean(v)) for e, v in c_off.items()}

d_valida = pareada("HARDWARE − réplica CON capas   ← la comparación válida",
                   H, M_on)
if d_valida is not None and len(d_valida) >= 2:
    n_necesario(d_valida)
pareada("réplica CON − SIN capas (mismo motor) ← aporte de las capas", M_on, M_off)
pareada("réplica SIN capas (pila) − réplica vieja (env) ← diferencia de motor", M_off, V)
pareada("HARDWARE − réplica vieja (la del informe, sesgada)", H, V)

print()
try:
    from diversidad_arranques import informe as _informe_diversidad
    # DictReader da el encabezado completo en cada fila: alcanza la primera.
    _n_ag = max((int(k[len("x0_a"):]) + 1 for k in filas_hw[0]
                 if k.startswith("x0_a")), default=0)
    _informe_diversidad(filas_hw, _n_ag)
except Exception as exc:                                      # noqa: BLE001
    print(f"DIVERSIDAD DE LOS ARRANQUES: no se pudo calcular ({exc})")

print("\nseguridad y ritmo (medias por corrida válida)")
claves = ("colisiones_015", "d_pared_min", "viola_018", "frac_cbf", "n_escape",
          "duracion_s", "ciclo_p95_ms")
print(f"{'':12}" + "".join(f"{k:>15}" for k in claves))
for nombre, filas in (("hardware", list(hw.values())), ("CON capas", on),
                      ("SIN capas", off)):
    ok = [r for r in filas if es_valida(r)]
    vals = []
    for k in claves:
        xs = [float(r[k]) for r in ok if r.get(k) not in (None, "")]
        vals.append(f"{np.mean(xs):15.4f}" if xs else f"{'—':>15}")
    print(f"{nombre:12}" + "".join(vals))
