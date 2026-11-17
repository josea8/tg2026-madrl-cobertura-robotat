"""
correr_experimento_E.py
=======================
EXPERIMENTO E — Voronoi + PSO como CUARTA línea base.

Extiende el diseño del Experimento D agregando el `PyramidalHeuristicController`
(Voronoi acotado con recorte Sutherland-Hodgman + término tipo PSO), que estaba
implementado en `fase_preliminar2/baseline_heuristico/` pero nunca se había
evaluado bajo protocolo: su único script de uso corría UN episodio con render y
overlay de Voronoi — un visualizador, no un evaluador. Por eso esta línea base
no aparece en los diagramas de caja de RESULTADO_PRIMERO.

Diseño
------
4 estrategias × 2 condiciones de borde × 100 semillas = 800 episodios, pareado
por semilla. Protocolo estándar: 500 pasos, 5 agentes, deterministic=True,
domain_rand=False, pesos del Trial 13.

  Estrategias : MADRL · Voronoi+PSO · heurística NN · aleatoria
  Condiciones : "reflexion" (entrenamiento) · "bloqueante" (pared sólida)

NO sobrescribe nada del Experimento D: archivos y salidas propios.

Validación de control (obligatoria)
-----------------------------------
Bajo "reflexion", MADRL debe reproducir 0.681291 y la heurística NN 0.254349,
exactos a 6 decimales. Si no, el script ABORTA.

Métricas por episodio
---------------------
  - cobertura AoI final
  - colisiones a 0.15 m (D_SAFE del env; el comparable con todo lo previo) y
    a 0.22 m (margen operativo de la metodología)
  - reflexiones (condición "reflexion") · fracción agente-paso en el borde
    (condición "bloqueante")
  - TIEMPO DE CÓMPUTO POR DECISIÓN en ms. El cuadro de antecedentes de la
    tesis afirma O(n log n) para Voronoi frente a O(1) de la inferencia
    neuronal; esa afirmación no estaba respaldada por medición propia. Se mide
    con `perf_counter` alrededor de la llamada de decisión, que para las
    cuatro estrategias produce las acciones de los 5 agentes de una vez.

Limitaciones declaradas de la comparación (ver resumen)
-------------------------------------------------------
  a) Asimetría de INFORMACIÓN — favorece a la línea base.
  b) Asimetría de SINTONIZACIÓN — favorece a MADRL.
  c) Asimetría de ESPACIO DE ACCIÓN — favorece a MADRL.
  d) Diferencia de LEY DE BAJO NIVEL entre las dos heurísticas.

Salidas
-------
  resultados/experimento_E_completo.csv    (800 filas)
  resultados/resumen_experimento_E.txt
  resultados/fig_resultados_CUATRO.png     (4 grupos; NO pisa la de tesis)

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

from stable_baselines3 import PPO

from adaptador_piramidal import AdaptadorPiramidal
from correr_experimento_D import (
    ARENA,
    COMM_RADIUS,
    MAX_STEPS_EP,
    N_AGENTES,
    PESOS_TRIAL13,
    RUTA_MODELO,
    SEED_BASE,
    politica_aleatoria,
    politica_heuristica_NN,
    politica_madrl,
)
from lib.swarm_env_skeleton import make_env

# Umbrales de colisión.
UMBRAL_CONTACTO: float = 0.15   # D_SAFE del env = contacto de chasis
UMBRAL_MARGEN:   float = 0.22   # margen operativo de la metodología

N_EPISODIOS: int = 100
SEMILLAS: List[int] = [SEED_BASE * 10_000 + i for i in range(N_EPISODIOS)]

ESTRATEGIAS: Tuple[str, ...] = ("madrl", "piramidal", "heuristica", "aleatoria")
CONDICIONES: Tuple[str, ...] = ("reflexion", "bloqueante")

ETIQUETAS: Dict[str, str] = {
    "madrl":      "MADRL (200k)",
    "piramidal":  "Voronoi + PSO",
    "heuristica": "Heurística NN",
    "aleatoria":  "Aleatoria",
}

# Valores oficiales (RESULTADO_PRIMERO/metricas_100eps.json).
OFICIAL: Dict[str, float] = {
    "madrl":      0.681291,
    "heuristica": 0.254349,
    "aleatoria":  0.140186,
}
TOL: float = 0.01

DIR_SALIDA:   Path = _CARPETA / "resultados"
RUTA_CSV:     Path = DIR_SALIDA / "experimento_E_completo.csv"
RUTA_RESUMEN: Path = DIR_SALIDA / "resumen_experimento_E.txt"
RUTA_FIG:     Path = DIR_SALIDA / "fig_resultados_CUATRO.png"


# =============================================================================
# EPISODIO
# =============================================================================

def correr_episodio(
    env,
    accionar:  Callable,
    seed_ep:   int,
    adaptador: AdaptadorPiramidal = None,
) -> Dict[str, object]:
    """
    Ejecuta un episodio determinista y mide también el tiempo de decisión.

    El RNG se siembra por episodio (ver nota del Experimento D) para que la
    política aleatoria reciba la misma secuencia en ambas condiciones y el
    pareo sea válido.
    """
    rng = np.random.default_rng(seed_ep)
    obs, _ = env.reset(seed=seed_ep)
    agentes: List[str] = list(obs.keys())
    n_a = len(agentes)

    # Imprescindible: limpia la inercia PSO del episodio anterior.
    if adaptador is not None:
        adaptador.reset_episodio(agentes)

    pares_contacto: set = set()
    pares_margen:   set = set()
    n_pasos = 0
    suma_recortes_prev = 0
    tiempos_ms: List[float] = []
    done = False

    while not done:
        t0 = time.perf_counter()
        acciones = accionar(env, obs, rng)
        tiempos_ms.append((time.perf_counter() - t0) * 1000.0)

        obs, _, term, trunc, _ = env.step(acciones)
        n_pasos += 1
        suma_recortes_prev = sum(env.contador_recortes.values())

        pos = np.array([env._estados[a][:2] for a in agentes])
        for ii in range(n_a):
            for jj in range(ii + 1, n_a):
                d = float(np.linalg.norm(pos[ii] - pos[jj]))
                if d < UMBRAL_CONTACTO:
                    pares_contacto.add((ii, jj))
                if d < UMBRAL_MARGEN:
                    pares_margen.add((ii, jj))
        done = all(trunc.values()) or all(term.values())

    t = np.asarray(tiempos_ms)
    return {
        "cobertura_aoi_final": round(
            1.0 - float(np.mean(env._field._grid_aoi)), 6
        ),
        "colisiones_015":  len(pares_contacto),
        "colisiones_022":  len(pares_margen),
        "reflexiones":     sum(env.contador_reflexiones.values()),
        "frac_pasos_agente_recorte": round(
            suma_recortes_prev / (n_pasos * n_a), 6
        ) if n_pasos else 0.0,
        "t_decision_ms_media": round(float(np.mean(t)), 4),
        "t_decision_ms_std":   round(float(np.std(t, ddof=1)), 4),
        "pasos": n_pasos,
    }


def ic95(x: np.ndarray) -> Tuple[float, float, float, float]:
    """Media, desviación (ddof=1) e IC95 por aproximación normal."""
    n = len(x)
    m = float(np.mean(x))
    s = float(np.std(x, ddof=1))
    ee = s / math.sqrt(n)
    return m, s, m - 1.96 * ee, m + 1.96 * ee


# =============================================================================
# FIGURA
# =============================================================================

def figura_cuatro(datos: Dict[str, Dict[str, Dict[int, Dict]]]) -> None:
    """
    Diagramas de caja de cobertura y colisiones para las CUATRO estrategias,
    condición "reflexion" (la del protocolo original de RESULTADO_PRIMERO).

    Mantiene el estilo de `fig_resultados_PRIMERO.png`: dos paneles, cajas
    rellenas con alpha 0.7, grilla en Y, línea guía en 0.5 en el panel de
    cobertura, 300 dpi. Se agrega un cuarto color para Voronoi+PSO.
    """
    nombres = [ETIQUETAS[e] for e in ESTRATEGIAS]
    cob = [
        [float(datos[e]["reflexion"][s]["cobertura_aoi_final"]) for s in SEMILLAS]
        for e in ESTRATEGIAS
    ]
    col = [
        [float(datos[e]["reflexion"][s]["colisiones_015"]) for s in SEMILLAS]
        for e in ESTRATEGIAS
    ]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))
    colores = ["#2c7fb8", "#41ab5d", "#7fcdbb", "#d95f0e"]

    bp1 = ax1.boxplot(cob, tick_labels=nombres, patch_artist=True, widths=0.55)
    for patch, c in zip(bp1["boxes"], colores):
        patch.set_facecolor(c); patch.set_alpha(0.7)
    ax1.set_ylabel("Cobertura AoI final", fontsize=11)
    ax1.set_title(f"Cobertura sobre {N_EPISODIOS} eps deterministas", fontsize=11)
    ax1.grid(True, alpha=0.3, axis="y")
    ax1.axhline(0.5, color="gray", ls=":", lw=1, alpha=0.6)

    bp2 = ax2.boxplot(col, tick_labels=nombres, patch_artist=True, widths=0.55)
    for patch, c in zip(bp2["boxes"], colores):
        patch.set_facecolor(c); patch.set_alpha(0.7)
    ax2.set_ylabel("Pares en colisión / episodio", fontsize=11)
    ax2.set_title(f"Colisiones sobre {N_EPISODIOS} eps deterministas", fontsize=11)
    ax2.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    fig.savefig(RUTA_FIG, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Figura → {RUTA_FIG}")


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    """Corre el factorial 4×2×100 y emite CSV, resumen y figura."""
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)

    print("═" * 76)
    print("  EXPERIMENTO E — Voronoi+PSO como 4ª línea base (4×2×100 = 800 eps)")
    print("═" * 76)

    modelo = PPO.load(str(RUTA_MODELO), device="cpu")
    adaptador = AdaptadorPiramidal(arena_size=ARENA)

    accionadores: Dict[str, Callable] = {
        "madrl":      politica_madrl(modelo),
        "piramidal":  adaptador,
        "heuristica": politica_heuristica_NN,
        "aleatoria":  politica_aleatoria,
    }

    filas: List[Dict[str, object]] = []
    datos: Dict[str, Dict[str, Dict[int, Dict]]] = {
        e: {c: {} for c in CONDICIONES} for e in ESTRATEGIAS
    }

    for estrategia in ESTRATEGIAS:
        for condicion in CONDICIONES:
            env = make_env(
                n_agents       = N_AGENTES,
                arena_size     = ARENA,
                max_steps      = MAX_STEPS_EP,
                comm_radius    = COMM_RADIUS,
                reward_weights = PESOS_TRIAL13,
                domain_rand    = False,
                seed           = SEED_BASE,
                modo_borde     = condicion,
            )
            t0 = time.time()
            for semilla in SEMILLAS:
                m = correr_episodio(
                    env, accionadores[estrategia], semilla,
                    adaptador if estrategia == "piramidal" else None,
                )
                fila = {"estrategia": estrategia, "condicion": condicion,
                        "seed_ep": semilla, **m}
                filas.append(fila)
                datos[estrategia][condicion][semilla] = fila

            cob = np.array([
                float(datos[estrategia][condicion][s]["cobertura_aoi_final"])
                for s in SEMILLAS
            ])
            print(f"  {estrategia:11s} {condicion:11s} "
                  f"cob={float(np.mean(cob)):.4f} ± {float(np.std(cob)):.4f}  "
                  f"({time.time()-t0:.0f}s)")

        # ── Validación de control ────────────────────────────────────────
        if estrategia in OFICIAL:
            m_ctrl = float(np.mean([
                float(datos[estrategia]["reflexion"][s]["cobertura_aoi_final"])
                for s in SEMILLAS
            ]))
            delta = abs(m_ctrl - OFICIAL[estrategia])
            marca = "OK" if delta <= TOL else "DESVIACIÓN"
            print(f"    VALIDACIÓN {estrategia}: {m_ctrl:.6f} vs oficial "
                  f"{OFICIAL[estrategia]:.6f}  |Δ|={delta:.6f}  [{marca}]\n")
            if delta > TOL:
                print(f"  ABORTADO: '{estrategia}' no reproduce el protocolo.")
                sys.exit(1)
        else:
            print()

    # ── CSV ──────────────────────────────────────────────────────────────
    with open(RUTA_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    print(f"CSV escrito ({len(filas)} filas) → {RUTA_CSV}")

    figura_cuatro(datos)

    # ── Análisis ─────────────────────────────────────────────────────────
    def vec(e: str, c: str, campo: str) -> np.ndarray:
        return np.array([float(datos[e][c][s][campo]) for s in SEMILLAS])

    L: List[str] = []
    L.append("EXPERIMENTO E — Voronoi + PSO como cuarta línea base")
    L.append("4 estrategias × 2 condiciones de borde × 100 semillas (800 eps),")
    L.append("pareado por semilla. 5 agentes, 500 pasos, deterministic=True,")
    L.append("domain_rand=False, pesos del Trial 13.")
    L.append("=" * 74)
    L.append("")

    L.append("VALIDACIÓN DE CONTROL (condición 'reflexion')")
    for e in ESTRATEGIAS:
        if e in OFICIAL:
            m = float(np.mean(vec(e, "reflexion", "cobertura_aoi_final")))
            L.append(f"  {e:12s} {m:.6f} vs oficial {OFICIAL[e]:.6f}  "
                     f"|Δ| = {abs(m-OFICIAL[e]):.6f}")
    L.append("  (Voronoi+PSO no tiene valor oficial previo: es la línea base")
    L.append("   que este experimento incorpora por primera vez al protocolo.)")
    L.append("")

    # ── Tabla 1: cobertura y colisiones 4×2 ─────────────────────────────
    L.append("TABLA 1 — COBERTURA AoI FINAL (media ± desv.)")
    L.append(f"  {'estrategia':14s} {'reflexion':>18s} {'bloqueante':>18s}")
    for e in ESTRATEGIAS:
        r = vec(e, "reflexion", "cobertura_aoi_final")
        b = vec(e, "bloqueante", "cobertura_aoi_final")
        L.append(f"  {ETIQUETAS[e]:14s} "
                 f"{float(np.mean(r)):9.4f} ± {float(np.std(r,ddof=1)):.4f} "
                 f"{float(np.mean(b)):9.4f} ± {float(np.std(b,ddof=1)):.4f}")
    L.append("")
    L.append("  COLISIONES a 0.15 m (contacto de chasis; el comparable)")
    L.append(f"  {'estrategia':14s} {'reflexion':>18s} {'bloqueante':>18s}")
    for e in ESTRATEGIAS:
        r = vec(e, "reflexion", "colisiones_015")
        b = vec(e, "bloqueante", "colisiones_015")
        L.append(f"  {ETIQUETAS[e]:14s} "
                 f"{float(np.mean(r)):8.3f} ({100*float(np.mean(r>0)):5.1f}%) "
                 f"{float(np.mean(b)):8.3f} ({100*float(np.mean(b>0)):5.1f}%)")
    L.append("")
    L.append("  COLISIONES a 0.22 m (margen operativo)")
    for e in ESTRATEGIAS:
        r = vec(e, "reflexion", "colisiones_022")
        b = vec(e, "bloqueante", "colisiones_022")
        L.append(f"  {ETIQUETAS[e]:14s} "
                 f"{float(np.mean(r)):8.3f} ({100*float(np.mean(r>0)):5.1f}%) "
                 f"{float(np.mean(b)):8.3f} ({100*float(np.mean(b>0)):5.1f}%)")
    L.append("")

    # ── Tabla 2: degradación pareada ─────────────────────────────────────
    L.append("TABLA 2 — DEGRADACIÓN PAREADA POR CONDICIÓN DE BORDE")
    L.append("  Δ = bloqueante − reflexion (negativo = degradación)")
    degrad: Dict[str, np.ndarray] = {}
    for e in ESTRATEGIAS:
        d = (vec(e, "bloqueante", "cobertura_aoi_final")
             - vec(e, "reflexion", "cobertura_aoi_final"))
        degrad[e] = d
        m, s, lo, hi = ic95(d)
        base = float(np.mean(vec(e, "reflexion", "cobertura_aoi_final")))
        L.append(f"  {ETIQUETAS[e]}:")
        L.append(f"      absoluta : {m:+.4f} ± {s:.4f}  IC95 [{lo:+.4f}, {hi:+.4f}]")
        L.append(f"      relativa : {100.0*m/base:+.2f}%   "
                 f"episodios peor: {int(np.sum(d < 0))}/{N_EPISODIOS}")
    L.append("")

    # ── Tabla 3: diferencia de diferencias ───────────────────────────────
    L.append("TABLA 3 — DIFERENCIA DE DIFERENCIAS (pareada)")
    L.append("  DiD = Δ(MADRL) − Δ(línea base). DiD < 0 con IC95 que excluye")
    L.append("  el cero ⇒ MADRL se degrada MÁS que esa línea base.")
    for base in ("piramidal", "heuristica", "aleatoria"):
        did = degrad["madrl"] - degrad[base]
        m, s, lo, hi = ic95(did)
        excluye = "SÍ" if (lo < 0 and hi < 0) or (lo > 0 and hi > 0) else "NO"
        L.append(f"  MADRL vs {ETIQUETAS[base]}:")
        L.append(f"      DiD = {m:+.4f} ± {s:.4f}  IC95 [{lo:+.4f}, {hi:+.4f}]"
                 f"   ¿excluye 0? {excluye}")
    L.append("")

    # ── Tabla 4: comportamiento en el borde ──────────────────────────────
    L.append("TABLA 4 — COMPORTAMIENTO EN EL BORDE")
    L.append(f"  {'estrategia':14s} {'reflexiones/ep':>16s} "
             f"{'frac agente-paso en borde':>27s}")
    L.append(f"  {'':14s} {'(reflexion)':>16s} {'(bloqueante)':>27s}")
    for e in ESTRATEGIAS:
        refl = vec(e, "reflexion", "reflexiones")
        frac = vec(e, "bloqueante", "frac_pasos_agente_recorte")
        L.append(f"  {ETIQUETAS[e]:14s} "
                 f"{float(np.mean(refl)):8.2f} ± {float(np.std(refl,ddof=1)):5.2f} "
                 f"{float(np.mean(frac)):18.4f} ± {float(np.std(frac,ddof=1)):.4f}")
    L.append("")

    # ── Tabla 5: tiempo de decisión ──────────────────────────────────────
    L.append("TABLA 5 — TIEMPO DE CÓMPUTO POR DECISIÓN")
    L.append("  Una 'decisión' produce las acciones de los 5 agentes de una")
    L.append("  vez, para las cuatro estrategias. Medido con perf_counter.")
    L.append(f"  {'estrategia':14s} {'ms por decisión':>20s} {'×  vs MADRL':>14s}")
    t_madrl = float(np.mean(vec("madrl", "reflexion", "t_decision_ms_media")))
    for e in ESTRATEGIAS:
        t = vec(e, "reflexion", "t_decision_ms_media")
        L.append(f"  {ETIQUETAS[e]:14s} "
                 f"{float(np.mean(t)):10.4f} ± {float(np.std(t,ddof=1)):.4f} "
                 f"{float(np.mean(t))/t_madrl:13.2f}×")
    L.append("")
    L.append("  El cuadro de antecedentes de la tesis afirma O(n log n) para")
    L.append("  Voronoi frente a O(1) de la inferencia neuronal. Estos son los")
    L.append("  tiempos medidos con n = 5 agentes; la afirmación asintótica no")
    L.append("  se verifica con un solo tamaño de enjambre, pero el cociente")
    L.append("  entre estrategias sí es medición propia y sustituye a la cita.")
    L.append("")

    # ── Limitaciones declaradas ──────────────────────────────────────────
    L.append("LIMITACIONES DECLARADAS DE LA COMPARACIÓN")
    L.append("")
    L.append("  (a) ASIMETRÍA DE INFORMACIÓN — favorece a la línea base.")
    L.append("      La partición de Voronoi requiere las posiciones GLOBALES de")
    L.append("      todos los agentes; MADRL opera sólo con observación local")
    L.append("      dentro de comm_radius = 1.0 m. La comparación es por tanto")
    L.append("      CONSERVADORA respecto de MADRL.")
    L.append("")
    L.append("  (b) ASIMETRÍA DE SINTONIZACIÓN — favorece a MADRL.")
    L.append("      El controlador piramidal tiene ~13 parámetros fijados a")
    L.append("      mano (inertia_gain, hotspot_gain, centroid_gain,")
    L.append("      boundary_gain, k_v, k_omega, ...), sin sintonización")
    L.append("      automática, mientras la política MADRL pasó por 20 pruebas")
    L.append("      de optimización bayesiana (Optuna/TPE).")
    L.append("")
    L.append("  (c) ASIMETRÍA DE ESPACIO DE ACCIÓN — favorece a MADRL.")
    L.append("      MADRL puede comandar v < 0 (retroceso); el piramidal está")
    L.append("      acotado a v ∈ [0, v_max] por construcción de su ley de")
    L.append("      seguimiento. Ante un obstáculo frontal su única salida es")
    L.append("      girar, no retroceder.")
    L.append("")
    L.append("  (d) LEY DE BAJO NIVEL DISTINTA entre las dos heurísticas.")
    L.append("      Ambas usan control proporcional sobre el error de rumbo con")
    L.append("      v modulada por cos(error), pero con ganancias distintas:")
    L.append("        heurística NN : K_ω = 4.00 · v = V_MAX·max(0,cos e)")
    L.append("        piramidal     : k_ω = 2.20 · v = k_v·‖vec‖·max(0,cos e)")
    L.append("                        con k_v = 1.40 (escala por distancia)")
    L.append("      Se corrió el piramidal CON SUS GANANCIAS ORIGINALES: son")
    L.append("      parte de su diseño (frenar al aproximarse al punto deseado")
    L.append("      dentro de su celda es intencional) y homogeneizarlas")
    L.append("      evaluaría un controlador que nadie diseñó, además de anular")
    L.append("      el valor de replicar el trabajo previo de la UVG. En")
    L.append("      consecuencia, entre las dos heurísticas difiere tanto la")
    L.append("      DECISIÓN de destino como la ley de seguimiento.")
    L.append("      (Ω_MAX sí se unificó al valor canónico 6.2832 del proyecto,")
    L.append("      vía constructor, sin modificar el archivo original.)")

    resumen = "\n".join(L)
    RUTA_RESUMEN.write_text(resumen, encoding="utf-8")
    print(f"Resumen → {RUTA_RESUMEN}\n")
    print(resumen)


if __name__ == "__main__":
    main()
