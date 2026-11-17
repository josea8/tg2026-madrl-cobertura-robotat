"""
diversidad_arranques.py — ¿los arranques de una sesión física son una muestra
razonable de la distribución de entrenamiento?

Por qué (2026-09-22): con n chico (5–10 episodios válidos) una muestra al azar
puede salir amontonada por mala suerte, y los episodios INVÁLIDOS pueden
sesgarla —si los arranques cerca del hueco de seguimiento (+x+y) fallan más,
los válidos quedan sin esa zona—. La cobertura de un enjambre depende de
dónde arranca, así que una sesión con arranques poco variados mide un caso
particular, no la política. Esto lo MIDE en vez de suponerlo.

Método: cada estadístico de los arranques de la sesión se ubica en su
distribución bajo el sorteo de entrenamiento con el MISMO número de episodios
y de agentes (Monte Carlo con `sesion_robotat.sortear_poses_arranque` y
rumbos uniformes en (−π, π], que es lo que hace el entorno de entrenamiento).
Se marca ⚠ lo que cae en la cola:

  · celdas_cubiertas  — fracción de una grilla 4×4 sobre el área de arranque
                        [0.45, 2.55]² que recibió al menos un robot (bajo =
                        amontonado);
  · disp_centroide    — desvío entre episodios del centroide del enjambre, en
                        m (bajo = el enjambre arranca siempre en el mismo lugar);
  · vecino_medio      — distancia media al vecino más cercano dentro de cada
                        episodio, en m (fuera de rango en cualquier sentido =
                        enjambre más apretado o más suelto que en
                        entrenamiento);
  · resultante_rumbo  — longitud de la resultante media de los rumbos (0 =
                        rumbos uniformes, 1 = todos iguales; alto = sesgado);
  · ks_x, ks_y        — estadístico de Kolmogorov–Smirnov de las coordenadas
                        contra la referencia (alto = distribución distinta).

Con seis estadísticos, uno fuera de rango al 5 % pasa por azar en ~26 % de
las sesiones sanas: un ⚠ aislado es un aviso, no un veredicto. Dos o más, o
uno muy extremo (percentil < 0.5 o > 99.5), sí piden mirar los arranques.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

LO: float = 0.45
HI: float = 2.55
GRILLA: int = 4
N_REFERENCIA: int = 1000

#: (nombre, cola): 'baja', 'alta' o 'ambas' — de qué lado es malo.
ESTADISTICOS: List[Tuple[str, str]] = [
    ("celdas_cubiertas", "baja"),
    ("disp_centroide", "baja"),
    ("vecino_medio", "ambas"),
    ("resultante_rumbo", "alta"),
    ("ks_x", "alta"),
    ("ks_y", "alta"),
]


def _ks(valores: np.ndarray, referencia: np.ndarray) -> float:
    """Estadístico D de KS de dos muestras (sin scipy)."""
    a, b = np.sort(valores), np.sort(referencia)
    todos = np.concatenate([a, b])
    fa = np.searchsorted(a, todos, side="right") / len(a)
    fb = np.searchsorted(b, todos, side="right") / len(b)
    return float(np.max(np.abs(fa - fb)))


def estadisticos(episodios: Sequence[np.ndarray],
                 ref_x: np.ndarray, ref_y: np.ndarray) -> Dict[str, float]:
    """
    `episodios`: una matriz (N, 3) por episodio con [x, y, θ] de cada robot,
    en el marco del env.
    """
    todos = np.concatenate([np.asarray(e, dtype=float) for e in episodios])
    x, y, th = todos[:, 0], todos[:, 1], todos[:, 2]
    celda = lambda v: np.clip(((v - LO) / (HI - LO) * GRILLA).astype(int),
                              0, GRILLA - 1)
    cubiertas = len(set(zip(celda(x).tolist(), celda(y).tolist())))
    centroides = np.array([np.asarray(e)[:, :2].mean(axis=0) for e in episodios])
    vecinos = []
    for e in episodios:
        p = np.asarray(e)[:, :2]
        d = np.linalg.norm(p[:, None, :] - p[None, :, :], axis=2)
        np.fill_diagonal(d, np.inf)
        vecinos.extend(d.min(axis=1).tolist())
    return {
        "celdas_cubiertas": cubiertas / GRILLA ** 2,
        "disp_centroide": float(centroides.std(axis=0).mean())
        if len(episodios) > 1 else 0.0,
        "vecino_medio": float(np.mean(vecinos)),
        "resultante_rumbo": float(abs(np.mean(np.exp(1j * th)))),
        "ks_x": _ks(x, ref_x),
        "ks_y": _ks(y, ref_y),
    }


def _sortear_sesion(n_episodios: int, n_agentes: int,
                    rng: np.random.Generator) -> List[np.ndarray]:
    from sesion_robotat import sortear_poses_arranque
    salida = []
    for _ in range(n_episodios):
        b = sortear_poses_arranque(n_agentes, rng)
        th = rng.uniform(-math.pi, math.pi, size=n_agentes)
        salida.append(np.array([[b[i][0], b[i][1], th[i]]
                                for i in range(n_agentes)]))
    return salida


def evaluar(episodios: Sequence[np.ndarray], semilla: int = 0,
            n_referencia: int = N_REFERENCIA) -> Dict[str, object]:
    """
    Ubica los estadísticos de la sesión en su distribución de referencia.

    Retorna {"valores", "percentiles", "banderas", "lineas"}.
    """
    episodios = [np.asarray(e, dtype=float) for e in episodios if len(e)]
    if len(episodios) < 2:
        return {"valores": {}, "percentiles": {}, "banderas": [],
                "lineas": ["  diversidad: hacen falta al menos 2 episodios"]}
    n_ep, n_ag = len(episodios), episodios[0].shape[0]
    rng = np.random.default_rng(semilla)
    # Marginales de referencia para KS: una muestra grande del mismo sorteo.
    grande = np.concatenate(_sortear_sesion(400, n_ag, rng))
    ref_x, ref_y = grande[:, 0], grande[:, 1]

    valores = estadisticos(episodios, ref_x, ref_y)
    sims = [estadisticos(_sortear_sesion(n_ep, n_ag, rng), ref_x, ref_y)
            for _ in range(n_referencia)]
    percentiles, banderas = {}, []
    for nombre, cola in ESTADISTICOS:
        dist = np.array([s[nombre] for s in sims])
        # percentil medio (empates repartidos): discreto en celdas_cubiertas
        pct = 100.0 * (np.mean(dist < valores[nombre])
                       + 0.5 * np.mean(dist == valores[nombre]))
        percentiles[nombre] = float(pct)
        malo = ((cola == "baja" and pct < 5.0)
                or (cola == "alta" and pct > 95.0)
                or (cola == "ambas" and (pct < 2.5 or pct > 97.5)))
        if malo:
            banderas.append(nombre)

    extremos = [n for n in banderas
                if percentiles[n] < 0.5 or percentiles[n] > 99.5]
    lineas = [f"  arranques de {n_ep} episodios × {n_ag} robots contra el "
              f"sorteo de entrenamiento (Monte Carlo, {n_referencia} sesiones "
              f"con el mismo n):"]
    unidades = {"celdas_cubiertas": "", "disp_centroide": " m",
                "vecino_medio": " m", "resultante_rumbo": "", "ks_x": "",
                "ks_y": ""}
    for nombre, cola in ESTADISTICOS:
        dist = np.array([s[nombre] for s in sims])
        lo, hi = np.percentile(dist, [2.5, 97.5])
        marca = "⚠" if nombre in banderas else " "
        lineas.append(
            f"   {marca} {nombre:<17} {valores[nombre]:7.3f}{unidades[nombre]:<2}"
            f"  percentil {percentiles[nombre]:5.1f}   (referencia 95 %: "
            f"{lo:.3f}–{hi:.3f})")
    if not banderas:
        veredicto = "compatible con el sorteo de entrenamiento"
    elif len(banderas) == 1 and not extremos:
        veredicto = ("un estadístico en la cola: aviso (con seis, pasa por "
                     "azar en ~1 de cada 4 sesiones sanas)")
    else:
        veredicto = ("⚠ arranques POCO REPRESENTATIVOS: revisar colocación "
                     "y exclusiones antes de citar la cobertura")
    lineas.append(f"   → {veredicto}")
    return {"valores": valores, "percentiles": percentiles,
            "banderas": banderas, "extremos": extremos, "veredicto": veredicto,
            "lineas": lineas}


def episodios_desde_filas(filas: Sequence[Dict[str, object]], n_agentes: int,
                          prefijo: Tuple[str, str, str] = ("x0", "y0", "th0"),
                          solo_validos: bool = True) -> List[np.ndarray]:
    """
    Matrices (N, 3) desde filas del CSV de episodios. `prefijo` elige qué
    columnas: ('x0','y0','th0') = pose medida al arrancar; ('blanco_x',
    'blanco_y','blanco_th') = el blanco sorteado.
    """
    salida = []
    for f in filas:
        if solo_validos and str(f.get("valido")) not in ("1", "True"):
            continue
        try:
            m = np.array([[float(f[f"{prefijo[0]}_a{i}"]),
                           float(f[f"{prefijo[1]}_a{i}"]),
                           float(f[f"{prefijo[2]}_a{i}"])]
                          for i in range(n_agentes)])
        except (KeyError, TypeError, ValueError):
            continue
        salida.append(m)
    return salida


def informe(filas: Sequence[Dict[str, object]], n_agentes: int,
            imprimir=print) -> Optional[Dict[str, object]]:
    """
    Sección del informe: arranques de los VÁLIDOS y, si el CSV trae los
    blancos, los de TODOS los intentos, para ver si las exclusiones sesgaron.
    """
    imprimir("DIVERSIDAD DE LOS ARRANQUES")
    validos = episodios_desde_filas(filas, n_agentes)
    res = evaluar(validos)
    for ln in res["lineas"]:
        imprimir(ln)
    blancos_todos = episodios_desde_filas(
        filas, n_agentes, ("blanco_x", "blanco_y", "blanco_th"),
        solo_validos=False)
    if len(blancos_todos) > len(validos) >= 2:
        todos = evaluar(blancos_todos)
        nuevas = sorted(set(res["banderas"]) - set(todos["banderas"]))
        imprimir(f"  blancos de los {len(blancos_todos)} intentos (válidos e "
                 f"inválidos): {todos['veredicto']}")
        if nuevas:
            imprimir(f"   ⚠ aparecen al quedarse sólo con los válidos: "
                     f"{', '.join(nuevas)} — las exclusiones sesgan los "
                     f"arranques; declararlo")
    return res
