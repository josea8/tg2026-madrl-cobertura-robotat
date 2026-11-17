"""
verificar_cbf_python.py
=======================
FACTORIAL 2×2 en Python — ¿de dónde viene el exceso de cobertura de Webots?

Contexto
--------
Webots con CBF + escape da 0.5739, por encima del control de Python sin CBF
(0.4426), pese a que la física no debería mejorar el desempeño respecto del
entorno idealizado.

La primera verificación (`verificar_escape_python.py`) intentó atribuirlo al
escape y NO CONCLUYE: el escape se disparó **2 veces en total** (2/18
episodios) contra ~9 por episodio en Webots. Es un nulo por DOSIS NULA, no por
ausencia de efecto. Y el dato apunta en la dirección contraria: las 2 semillas
que mejoraron (420008 +0.088, 420011 +0.004) son exactamente las 2 donde el
escape se disparó; las otras 16 quedaron idénticas bit a bit.

Causa de la no-activación: en Python el borde bloqueante recorta la posición
pero deja la ROTACIÓN LIBRE, así que el agente pegado a la pared gira y sale
solo sin llegar a 6 decisiones de estancamiento. En Webots el contacto físico
bloquea también la rotación. **El entorno de Python no produce el estado que el
escape resuelve.**

Hipótesis nueva
---------------
El exceso no es del escape sino del **filtro CBF**, que está activo en Webots y
ausente en el control de Python. Sus barreras robot-robot exigen 0.25 m entre
puntos de mira: es una fuerza de DISPERSIÓN permanente, y la dispersión mejora
la cobertura AoI. Evidencia previa: en Webots sin CBF 0.2168 → con CBF 0.3199,
que se había atribuido sólo a menos atascos.

Diseño
------
Mismas 18 semillas, modo_borde="bloqueante", 5 agentes, deterministic=True:

    (a) sin CBF, sin escape   → 0.4426 (ya medida; se recalcula como control)
    (b) con CBF, sin escape   → ?      ← la celda decisiva
    (c) sin CBF, con escape   → 0.4477 (ya medida)
    (d) con CBF, con escape   → ?      ← análogo exacto de Webots

En las condiciones con CBF se reportan además la **distancia media entre
agentes** (para medir la dispersión directamente) y la **fracción de
intervención**. Si (b) sube claramente sobre (a), el filtro es el contribuyente
y hay que declararlo.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
import sys
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

from stable_baselines3 import PPO

from lib.filtro_cbf import FiltroCBFParedes, RestriccionLineal
from lib.swarm_env_skeleton import make_env
from verificar_escape_python import (
    ARENA,
    COMM_RADIUS,
    D_ROBOTS,
    D_SEGURA,
    ELE_A,
    MAX_STEPS,
    N_AGENTES,
    N_EPISODIOS,
    OMEGA_MAX,
    PESOS_TRIAL13,
    RUTA_MODELO,
    SEED_BASE,
    SEMILLAS,
    V_MAX,
    GestorEscape,
)

ALFA_CBF: float = 2.0
W_OMEGA:  float = 0.3

DIR_SALIDA: Path = _CARPETA / "resultados"

# Referencias ya medidas.
REF_WEBOTS_SIN_CBF: float = 0.2168
REF_WEBOTS_CBF:     float = 0.3199
REF_WEBOTS_ESCAPE:  float = 0.5739


def barreras_robot_robot(
    filtro: FiltroCBFParedes, i: int, poses: np.ndarray,
) -> List[RestriccionLineal]:
    """Barreras robot-robot con reparto de responsabilidad 50/50 (h/2)."""
    extras: List[RestriccionLineal] = []
    p_i = filtro._punto_de_mira(poses[i])
    G_i = filtro._matriz_G(float(poses[i, 2]))
    for j in range(len(poses)):
        if j == i:
            continue
        p_j = filtro._punto_de_mira(poses[j])
        delta = p_i - p_j
        dist = float(np.linalg.norm(delta))
        if dist < 1e-9:
            continue
        extras.append(RestriccionLineal(
            c=(delta / dist) @ G_i,
            h=0.5 * (dist - D_ROBOTS),
            nombre=f"robot_{j}",
        ))
    return extras


def correr_episodio(
    env,
    modelo: PPO,
    seed_ep: int,
    filtro: Optional[FiltroCBFParedes],
    gestor: Optional[GestorEscape],
) -> Dict[str, float]:
    """Un episodio determinista bajo una de las cuatro condiciones."""
    obs, _ = env.reset(seed=seed_ep)
    agentes: List[str] = list(obs.keys())
    n_a = len(agentes)
    if gestor is not None:
        gestor.reset()

    pares15: set = set()
    pares22: set = set()
    n_pasos = 0
    n_interv = 0
    suma_dist_media = 0.0
    done = False

    while not done:
        acciones, _ = modelo.predict(
            np.stack([obs[a] for a in agentes]), deterministic=True
        )
        acciones = np.asarray(acciones, dtype=np.float32)
        poses = np.array([env._estados[a][:3] for a in agentes])

        for i in range(n_a):
            # El escape REEMPLAZA u_nom; el filtro corre igual después.
            if gestor is not None:
                acciones[i] = gestor.gestionar(i, poses, acciones[i])
            if filtro is not None:
                res = filtro.filtrar(
                    poses[i], acciones[i],
                    restricciones_extra=barreras_robot_robot(filtro, i, poses),
                )
                if res.intervino:
                    n_interv += 1
                acciones[i] = np.asarray(res.u_seguro, dtype=np.float32)

        if gestor is not None:
            gestor.pose_previa = poses.copy()

        obs, _, term, trunc, _ = env.step(
            {a: acciones[k] for k, a in enumerate(agentes)}
        )
        n_pasos += 1

        pos = np.array([env._estados[a][:2] for a in agentes])
        dists = [
            float(np.linalg.norm(pos[ii] - pos[jj]))
            for ii, jj in combinations(range(n_a), 2)
        ]
        suma_dist_media += float(np.mean(dists))
        for (ii, jj), d in zip(combinations(range(n_a), 2), dists):
            if d < 0.15:
                pares15.add((ii, jj))
            if d < 0.22:
                pares22.add((ii, jj))
        done = all(trunc.values()) or all(term.values())

    return {
        "cobertura_aoi_final": round(
            1.0 - float(np.mean(env._field._grid_aoi)), 6
        ),
        "colisiones_015":   len(pares15),
        "colisiones_022":   len(pares22),
        "dist_media_agentes": round(suma_dist_media / n_pasos, 6),
        "cbf_frac_interv":  round(n_interv / (n_pasos * n_a), 6),
        "escape_n":         sum(gestor.n_escapes) if gestor else 0,
        "escape_frac":      round(
            sum(gestor.decisiones) / (n_pasos * n_a), 6
        ) if gestor else 0.0,
        "pasos": n_pasos,
    }


def ic95(x: np.ndarray) -> Tuple[float, float, float]:
    """Media e IC95 por aproximación normal."""
    n = len(x); m = float(np.mean(x))
    ee = float(np.std(x, ddof=1)) / math.sqrt(n)
    return m, m - 1.96 * ee, m + 1.96 * ee


def main() -> None:
    """Corre el factorial 2×2 y reporta."""
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    modelo = PPO.load(str(RUTA_MODELO), device="cpu")

    print("═" * 74)
    print("  FACTORIAL 2×2 en Python — CBF × escape")
    print("═" * 74)

    condiciones = [
        ("a_sin_cbf_sin_esc", False, False),
        ("b_con_cbf_sin_esc", True,  False),
        ("c_sin_cbf_con_esc", False, True),
        ("d_con_cbf_con_esc", True,  True),
    ]
    filas: List[Dict[str, object]] = []
    datos: Dict[str, Dict[int, Dict]] = {}

    for etiqueta, usa_cbf, usa_esc in condiciones:
        env = make_env(
            n_agents=N_AGENTES, arena_size=ARENA, max_steps=MAX_STEPS,
            comm_radius=COMM_RADIUS, reward_weights=PESOS_TRIAL13,
            domain_rand=False, seed=SEED_BASE, modo_borde="bloqueante",
        )
        filtro = FiltroCBFParedes(
            arena_size=ARENA, ele_a=ELE_A, alfa=ALFA_CBF,
            d_segura=D_SEGURA, w_omega=W_OMEGA,
            v_max=V_MAX, omega_max=OMEGA_MAX,
        ) if usa_cbf else None
        gestor = GestorEscape(N_AGENTES) if usa_esc else None

        datos[etiqueta] = {}
        for s in SEMILLAS:
            m = correr_episodio(env, modelo, s, filtro, gestor)
            fila = {"condicion": etiqueta, "semilla": s, **m}
            filas.append(fila)
            datos[etiqueta][s] = fila

        cob = np.array([
            float(datos[etiqueta][s]["cobertura_aoi_final"]) for s in SEMILLAS
        ])
        dm = np.array([
            float(datos[etiqueta][s]["dist_media_agentes"]) for s in SEMILLAS
        ])
        print(f"  {etiqueta:20s} cob={cob.mean():.4f} ± {cob.std():.4f}  "
              f"dist_media={dm.mean():.4f}")

    ruta_csv = DIR_SALIDA / "verificacion_cbf_python.csv"
    with open(ruta_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)

    def v(et, campo):
        return np.array([float(datos[et][s][campo]) for s in SEMILLAS])

    L: List[str] = []
    L.append("FACTORIAL 2×2 en Python — ¿de dónde viene el exceso de Webots?")
    L.append(f"{N_EPISODIOS} semillas, {N_AGENTES} agentes, "
             f"modo_borde='bloqueante', modelo_sanidad, sin física.")
    L.append("=" * 72)
    L.append("")
    L.append("TABLA 1 — LAS CUATRO CONDICIONES")
    L.append(f"  {'condición':22s} {'cobertura':>17s} {'dist media':>11s} "
             f"{'CBF frac':>9s} {'escapes':>8s} {'col015':>7s}")
    for et, _, _ in condiciones:
        cob = v(et, "cobertura_aoi_final")
        L.append(f"  {et:22s} {cob.mean():8.4f} ± {cob.std():.4f} "
                 f"{v(et,'dist_media_agentes').mean():11.4f} "
                 f"{v(et,'cbf_frac_interv').mean():9.4f} "
                 f"{v(et,'escape_n').mean():8.2f} "
                 f"{v(et,'colisiones_015').mean():7.3f}")
    L.append("")
    L.append("  Referencias en Webots (mismas semillas, CON física):")
    L.append(f"    sin CBF {REF_WEBOTS_SIN_CBF:.4f} · con CBF "
             f"{REF_WEBOTS_CBF:.4f} · con CBF+escape {REF_WEBOTS_ESCAPE:.4f}")
    L.append("")
    L.append("TABLA 2 — EFECTOS PAREADOS POR SEMILLA")
    pares = [
        ("EFECTO DEL CBF (sin escape):    b − a",
         "b_con_cbf_sin_esc", "a_sin_cbf_sin_esc"),
        ("EFECTO DEL ESCAPE (sin CBF):    c − a",
         "c_sin_cbf_con_esc", "a_sin_cbf_sin_esc"),
        ("EFECTO DEL ESCAPE (con CBF):    d − b",
         "d_con_cbf_con_esc", "b_con_cbf_sin_esc"),
        ("EFECTO CONJUNTO:                d − a",
         "d_con_cbf_con_esc", "a_sin_cbf_sin_esc"),
    ]
    for titulo, x, y in pares:
        d = v(x, "cobertura_aoi_final") - v(y, "cobertura_aoi_final")
        m, lo, hi = ic95(d)
        sig = "*" if (lo < 0 and hi < 0) or (lo > 0 and hi > 0) else " "
        L.append(f"  {titulo}")
        L.append(f"      Δ = {m:+.4f}  IC95 [{lo:+.4f}, {hi:+.4f}]{sig}   "
                 f"mejores: {int(np.sum(d > 0))}/{N_EPISODIOS}")
    L.append("  (* = el IC95 excluye el cero)")
    L.append("")
    L.append("TABLA 3 — DISPERSIÓN (distancia media entre agentes)")
    for et, _, _ in condiciones:
        L.append(f"  {et:22s} {v(et,'dist_media_agentes').mean():.4f} m")
    d_disp = (v("b_con_cbf_sin_esc", "dist_media_agentes")
              - v("a_sin_cbf_sin_esc", "dist_media_agentes"))
    m, lo, hi = ic95(d_disp)
    L.append(f"  Δ dispersión por el CBF: {m:+.4f} m  IC95 [{lo:+.4f}, {hi:+.4f}]")
    L.append("")
    L.append("ACTIVACIÓN DEL ESCAPE")
    L.append(f"  sin CBF : {v('c_sin_cbf_con_esc','escape_n').sum():.0f} escapes "
             f"en {N_EPISODIOS} episodios")
    L.append(f"  con CBF : {v('d_con_cbf_con_esc','escape_n').sum():.0f} escapes "
             f"en {N_EPISODIOS} episodios")
    L.append("  (en Webots: ~9 por episodio; el entorno de Python no produce el")
    L.append("   estado que el escape resuelve porque la rotación queda libre)")

    resumen = "\n".join(L)
    (DIR_SALIDA / "verificacion_cbf_python.txt").write_text(
        resumen, encoding="utf-8"
    )
    print(f"\nCSV → {ruta_csv}\n")
    print(resumen)


if __name__ == "__main__":
    main()
