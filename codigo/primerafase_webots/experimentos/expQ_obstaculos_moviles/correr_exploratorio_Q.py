"""
correr_exploratorio_Q.py
========================
EXPLORATORIO — fuera de la regla de parada. Exp Q, niveles S2 y S3.

El Exp Q se detuvo en S1 por la regla del Exp O: 1 escape agotado en S1_din
(semilla 420001, que también lo tiene en S1_ctrl, S1_quieto y S1_sinvel).
ESE VEREDICTO QUEDA TAL CUAL. José decidió el 19-10 correr S2 y S3 como
exploratorio, después de la parada y fuera de la regla.

Este script SÓLO ORQUESTA: importa y llama a `correr_experimento_Q.py`; no
redefine ni parchea nada del código que entra en la huella. En orden:

  1. la huella del código tiene que ser `HUELLA_ESPERADA` (e265b6cd…4a29),
     la de la corrida de S1, y pasabilidad, control y negativo tienen que
     estar aprobados con ella; los tres archivos de resultados de S1 tienen
     que tener el sha256 de `SHA256_S1` (y lo vuelven a tener al final);
  2. S1_din se RECALCULA (100 semillas, con `_tarea_Q` en un pool propio:
     sin leer ni escribir parciales) y tiene que salir idéntico en texto
     (repr de cada float, todas las columnas salvo `t_episodio_s`) a sus
     filas de `experimento_Q_completo.csv`; si no, PARAR;
  3. S2 y S3, las cuatro condiciones y las 100 semillas, SIN detenerse por
     ningún criterio (parciales propios `exploratorio_*`: reanudable).

Salidas, todas aparte y con EXPLORATORIO en el nombre (los CSV llevan además
la columna `exploratorio` = 1; los textos, EXPLORATORIO en la primera línea):
  resultados/reproduccion_S1_din_EXPLORATORIO.csv
  resultados/experimento_Q_EXPLORATORIO_S2_S3.csv
  resultados/registro_Q_EXPLORATORIO.txt

    python -B correr_exploratorio_Q.py > resultados/corrida_Q_EXPLORATORIO.log

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import correr_experimento_Q as Q
from correr_experimento_O import CRITERIOS_FALLA, UMBRAL_INDICADOR, escribir_csv
from correr_experimento_O import _inicializar_trabajador

ENCABEZADO: str = ("EXPLORATORIO — fuera de la regla de parada: S2 y S3 del Exp Q, corridos "
                   "después de la parada de S1 por decisión de José (19-10); no cambian el "
                   "veredicto del Exp Q.")
#: La huella con que corrió S1 (registros de pasabilidad, control, negativo y S1).
HUELLA_ESPERADA: str = "e265b6cd31e8d443977027b1bf1d4671c002b06c3ecbdc45a275521e49c24a29"
#: Los resultados de S1, que no pueden cambiar (sha256 del 19-10).
SHA256_S1: Dict[str, str] = {
    "resultados/registro_Q.txt":
        "ff553e66d06420ff1f7abcabb9f03070885f96be8b8856850c3a5dd249d8673a",
    "resultados/experimento_Q_completo.csv":
        "341562959d02b113e1585590425bc4f51918cb3d4ff6e944f46dc616a08d5dbf",
    "resultados/resumen_experimento_Q.txt":
        "f5f69c4ea9b667d5e4e62b91e25fd1087f09320c7f15f04e529293eaff672a43",
}
NIVELES_EXPLORATORIOS: tuple = ("S2", "S3")
PREFIJO_PARCIALES: str = "exploratorio"
RUTA_REPRO_CSV: Path = Q.DIR_SALIDA_Q / "reproduccion_S1_din_EXPLORATORIO.csv"
RUTA_CSV_EXPL: Path = Q.DIR_SALIDA_Q / "experimento_Q_EXPLORATORIO_S2_S3.csv"
RUTA_REG_EXPL: Path = Q.DIR_SALIDA_Q / "registro_Q_EXPLORATORIO.txt"


def sha256_s1() -> List[str]:
    """Los tres archivos de S1 con su sha256 registrado; si no, PARAR."""
    L, malos = [], []
    for rel, esperado in SHA256_S1.items():
        actual = hashlib.sha256((_CARPETA / rel).read_bytes()).hexdigest()
        L.append(f"  {'IGUAL' if actual == esperado else 'DISTINTO'} {actual} {rel}")
        if actual != esperado:
            malos.append(rel)
    if malos:
        raise SystemExit(f"PARAR: cambiaron resultados de S1: {malos}")
    return ["RESULTADOS DE S1 sin cambios (sha256 del 19-10):"] + L


def prerrequisitos() -> str:
    """Huella e265b6cd…4a29 y los tres registros aprobados con ella."""
    huella = Q.huella_codigo()
    if huella != HUELLA_ESPERADA:
        raise SystemExit(f"PARAR: la huella del código es {huella}, no la de S1 "
                         f"({HUELLA_ESPERADA}).")
    for ruta, marca in ((Q.RUTA_PASAB_TXT, "PASABILIDAD: OK"),
                        (Q.RUTA_CONTROL_TXT, "CONTROL: OK"),
                        (Q.RUTA_NEGATIVO_TXT, "NEGATIVO: OK")):
        motivo = Q._aprobado(ruta, marca, huella)
        if motivo:
            raise SystemExit(f"PARAR: {motivo}.")
    return huella


def filas_marcadas(filas: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    """Cada fila con la columna `exploratorio` = 1 al principio."""
    return [{"exploratorio": 1, **f} for f in filas]


def reproducir_s1_din(n_trab: int) -> List[str]:
    """S1_din recalculado sin parciales, contra `experimento_Q_completo.csv`."""
    cond = Q.CondicionQ("S1_din", "S1", "din")
    semillas = Q.semillas_protocolo()
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=n_trab, initializer=_inicializar_trabajador) as ex:
        filas = list(ex.map(Q._tarea_Q, [(cond, s) for s in semillas], chunksize=1))
    ref = {int(r["seed_ep"]): r for r in Q._leer_csv(Q.RUTA_CSV_Q)
           if r["condicion"] == "S1_din"}
    columnas = [c for c in next(iter(ref.values())) if c != "t_episodio_s"]
    iguales, malas = 0, []
    for f in filas:
        r = ref.get(int(f["seed_ep"]))
        dif = ["(falta en el CSV)"] if r is None else [
            c for c in columnas if Q._serial(f[c]) != r[c]]
        if dif:
            malas.append(f"{f['seed_ep']}: {dif[:4]}")
        else:
            iguales += 1
    escribir_csv(filas_marcadas(filas), RUTA_REPRO_CSV)
    L = [f"REPRODUCCIÓN de S1_din sin parciales: {iguales}/{len(ref)} semillas idénticas "
         f"en texto a experimento_Q_completo.csv en las {len(columnas)} columnas (todas "
         f"salvo t_episodio_s), {time.perf_counter() - t0:.0f} s"]
    L += [f"    {m}" for m in malas[:10]]
    for x in L:
        print("  " + x, flush=True)
    if malas or iguales != len(ref) or len(filas) != len(ref):
        Q._escribir_registro(RUTA_REG_EXPL, [ENCABEZADO] + L + ["REPRODUCCIÓN: NO"],
                             HUELLA_ESPERADA)
        raise SystemExit("PARAR: S1_din no se reproduce; no se corren S2 ni S3.")
    return L


def resumen_nivel(k: str, filas: Sequence[Dict[str, str]]) -> List[str]:
    """Intervención y criterios por condición; la regla NO detiene."""
    L = []
    for tipo in ("din", "quieto", "sinvel"):
        fk = [f for f in filas if f["tipo"] == tipo]
        interv = sum(float(f["cbf_frac_interv"]) for f in fk) / len(fk)
        fallas = [(e, int(sum(float(f[c]) for f in fk))) for c, e in CRITERIOS_FALLA]
        L.append(f"{k}_{tipo} (exploratorio): intervención media {interv:.8f} "
                 f"({'sobre' if interv > UMBRAL_INDICADOR else 'bajo'} el indicador "
                 f"{UMBRAL_INDICADOR}); criterios — " +
                 "; ".join(f"{e} {v}" for e, v in fallas))
    fdin = [f for f in filas if f["tipo"] == "din"]
    dispara = any(sum(float(f[c]) for f in fdin) > 0 for c, _ in CRITERIOS_FALLA)
    L.append(f"{k}: con la regla, {k}_din {'la dispararía' if dispara else 'no la dispararía'}; "
             f"exploratorio: se sigue igual.")
    return L


def main() -> None:
    print(ENCABEZADO, flush=True)
    print(f"inicio {datetime.now():%Y-%m-%d %H:%M:%S}", flush=True)
    n_trab = max(1, (os.cpu_count() or 2) - 1)
    huella = prerrequisitos()
    informe: List[str] = [ENCABEZADO, f"huella del código: {huella} (la de S1)",
                          "prerrequisitos: pasabilidad_Q.txt, control_bit_a_bit_Q.txt y "
                          "control_negativo_Q.txt aprobados con esa huella"]
    informe += sha256_s1()
    informe += Q.verificar_copias()
    informe.append(Q.verificar_stack())
    informe.append(f"procesos: {n_trab}")
    for x in informe[1:]:
        print("  " + x, flush=True)
    informe += reproducir_s1_din(n_trab)
    filas: List[Dict[str, str]] = []
    for k in NIVELES_EXPLORATORIOS:
        nuevas = Q.correr_condiciones(Q.condiciones_nivel(k), n_trab, PREFIJO_PARCIALES, huella)
        filas += nuevas
        lineas = resumen_nivel(k, nuevas)
        informe += lineas
        for x in lineas:
            print("  " + x, flush=True)
    sha256_s1()
    escribir_csv(filas_marcadas(filas), RUTA_CSV_EXPL)
    Q._escribir_registro(RUTA_REG_EXPL, informe, huella)
    print(f"  CSV → {RUTA_CSV_EXPL} ({len(filas)} filas)", flush=True)
    print(f"fin {datetime.now():%Y-%m-%d %H:%M:%S}", flush=True)


if __name__ == "__main__":
    main()
