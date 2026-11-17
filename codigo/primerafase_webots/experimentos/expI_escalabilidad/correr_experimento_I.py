"""
correr_experimento_I.py
=======================
EXPERIMENTO I — Generalización de la política a un número de agentes distinto
del de entrenamiento, SIN reentrenamiento.

Pregunta
--------
La metodología de la tesis afirma que el esquema de parámetros compartidos
(parameter sharing) "favorece la generalización a distintos números de agentes
sin reentrenamiento adicional", apoyándose sólo en una cita. Este experimento
produce evidencia propia sobre esa afirmación evaluando `modelo_PRIMERO` (la
política entrenada con 5 agentes) sobre enjambres de 2, 3, 5, 7 y 10 agentes.

Por qué en Python y no en Webots
--------------------------------
En Webots con física, variar el número de agentes mezcla dos efectos —la
generalización de la política y la degradación por densidad—. Ya está medido
que la densidad domina (atascos 16.7 % con 1 agente, 25.0 % con 2, 56.7 % con
5). En el entorno de entrenamiento la única variable es el número de agentes,
así que el efecto de generalización queda aislado.

Diseño
------
n_agentes ∈ {2, 3, 5, 7, 10}
  × 2 condiciones de borde ("reflexion" = entrenamiento, "bloqueante" = pared
    sólida)
  × 100 semillas del protocolo estándar (SEED_BASE*10000 + i, i = 0..99)
= 1000 episodios, pareado por semilla.

  Política     : modelo_PRIMERO, predict(deterministic=True)
  domain_rand  : False
  max_steps    : 500
  arena        : 3.0 × 3.0
  comm_radius  : 1.0
  n_hotspots   : 3 (fijo — NO escala con n; ese es justamente el punto)
  pesos        : Trial 13

n = 5 se incluye aunque ya esté medido: es la VERIFICACIÓN DE CONTROL. Bajo
"reflexion" debe reproducir 0.6812908187508583 (RESULTADO_PRIMERO/
metricas_100eps.json; el Exp E lo replicó exacto a 6 decimales). Si |Δ| supera
`TOL_ABORTO`, el script ABORTA sin escribir resultados.

Invarianza al cardinal — verificada por lectura del código antes de asumirla
--------------------------------------------------------------------------------
  - `CyanobacteriaMonitoringEnv` deriva todo de `n_agents`; `n_hotspots` es un
    parámetro independiente.
  - `MeanEmbeddingEncoder.encode` promedia sobre |N_i| vecinos y devuelve el
    vector CERO si |N_i| = 0 → dimensión de salida fija (8) para cualquier n.
  - `politica_madrl` hace `predict` sobre un batch (n, 24): parámetros
    compartidos aplicados por-agente, sin dependencia de n.
  - `_sortear_poses_iniciales` es genérico en N (rejection sampling con
    fallback a grilla). El uso del fallback se CUENTA y se reporta: si n = 10
    lo usa mucho, las poses iniciales dejan de ser comparables con las de n = 5
    y hay que saberlo.

Métricas por episodio
---------------------
  - cobertura_aoi_final
  - colisiones_015 / colisiones_022 (pares únicos a < 0.15 m y < 0.22 m)
  - reflexiones (condición "reflexion")
  - frac_pasos_agente_recorte (fracción de agente-paso contra el borde;
    condición "bloqueante")
  - frac_embedding_activo — CLAVE PARA LA PREGUNTA. Fracción de agente-decisión
    en las que el `neighbor_embedding` de la observación es NO NULO, es decir,
    en las que el agente ve al menos un vecino. Métrica EXACTA (no aproximada):
    la componente 5 de φ(j) es distancia/comm_radius, siempre > 0 para un
    vecino visible, así que el embedding es exactamente 0^8 si y sólo si no hay
    vecinos. Mide cuánto del "camino multiagente" de la política se ejercita
    realmente en cada densidad.

Salidas
-------
  resultados/experimento_I_completo.csv     (1000 filas)
  resultados/resumen_experimento_I.txt      (5 tablas + cuadro LaTeX)
  figuras/fig_escalabilidad_cobertura.png
  figuras/fig_escalabilidad_embedding.png
  figuras/fig_escalabilidad_seguridad.png

NO sobrescribe ningún artefacto previo: la carpeta expI_escalabilidad/ es nueva.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
import sys
import time
import warnings
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

from correr_experimento_D import (
    ARENA,
    COMM_RADIUS,
    MAX_STEPS_EP,
    PESOS_TRIAL13,
    SEED_BASE,
    ic95,
    politica_madrl,
)
from lib.swarm_env_skeleton import D_ENV, D_NEIGHBOR, D_OWN, make_env

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

N_VALORES:   Tuple[int, ...] = (2, 3, 5, 7, 10)
CONDICIONES: Tuple[str, ...] = ("reflexion", "bloqueante")
N_EPISODIOS: int = 100
SEMILLAS:    List[int] = [SEED_BASE * 10_000 + i for i in range(N_EPISODIOS)]

N_CONTROL: int = 5  # el valor de n cuya cobertura bajo "reflexion" se valida

# Umbrales de colisión (idénticos al Exp E).
UMBRAL_CONTACTO: float = 0.15   # D_SAFE del env = contacto de chasis
UMBRAL_MARGEN:   float = 0.22   # margen operativo de la metodología

# Rebanada del vector de observación que ocupa el neighbor_embedding.
_EMB_INI: int = D_OWN + D_ENV               # 5 + 3 = 8
_EMB_FIN: int = D_OWN + D_ENV + D_NEIGHBOR  # 8 + 8 = 16

# Valor oficial de control (RESULTADO_PRIMERO/metricas_100eps.json, n = 5,
# condición "reflexion", 100 episodios deterministas).
COBERTURA_OFICIAL_N5: float = 0.6812908187508583
TOL_ABORTO: float = 1.0e-3

RUTA_MODELO:  Path = _CARPETA / "modelos" / "modelo_PRIMERO.zip"
DIR_RESULT:   Path = _CARPETA / "resultados"
DIR_FIGURAS:  Path = _CARPETA / "figuras"
RUTA_CSV:     Path = DIR_RESULT / "experimento_I_completo.csv"
RUTA_RESUMEN: Path = DIR_RESULT / "resumen_experimento_I.txt"

# Estilo de figura — replica fig_resultados_CUATRO.png del Exp E.
COLOR_REFLEXION:  str = "#2c7fb8"
COLOR_BLOQUEANTE: str = "#d95f0e"
COLOR_U015:       str = "#2c7fb8"
COLOR_U022:       str = "#41ab5d"
DPI_FIG: int = 300


# =============================================================================
# EPISODIO
# =============================================================================

def correr_episodio(
    env,
    accionar: Callable,
    seed_ep:  int,
) -> Dict[str, object]:
    """
    Ejecuta un episodio determinista y devuelve sus métricas.

    El RNG se siembra por episodio (ver nota del Exp D): así el pareo por
    semilla comparte la dinámica de los hotspots entre valores de n.

    `frac_embedding_activo` se mide inspeccionando la OBSERVACIÓN que la
    política realmente usa, justo antes de cada llamada a `accionar`. Un
    agente-decisión cuenta como "activo" si algún componente del
    neighbor_embedding es distinto de cero (equivalente exacto a "el agente ve
    al menos un vecino", por el argumento de la componente de distancia).
    """
    rng = np.random.default_rng(seed_ep)

    # El uso del fallback de grilla en el sorteo de poses iniciales emite un
    # RuntimeWarning; lo capturamos para saber si las poses de este episodio
    # son comparables con las de otros n.
    with warnings.catch_warnings(record=True) as capturadas:
        warnings.simplefilter("always")
        obs, _ = env.reset(seed=seed_ep)
        uso_grid_fallback = any(
            issubclass(w.category, RuntimeWarning)
            and "grid fallback" in str(w.message)
            for w in capturadas
        )

    agentes: List[str] = list(obs.keys())
    n_a: int = len(agentes)

    pares_contacto: set = set()
    pares_margen:   set = set()
    n_pasos: int = 0
    emb_activos: int = 0
    emb_total:   int = 0
    done = False

    while not done:
        # ── Activación del embedding sobre la obs que ve la política ────────
        for a in agentes:
            emb = obs[a][_EMB_INI:_EMB_FIN]
            emb_activos += int(bool(np.any(emb != 0.0)))
            emb_total   += 1

        acciones = accionar(env, obs, rng)
        obs, _, term, trunc, _ = env.step(acciones)
        n_pasos += 1

        pos = np.array([env._estados[a][:2] for a in agentes])
        for ii in range(n_a):
            for jj in range(ii + 1, n_a):
                d = float(np.linalg.norm(pos[ii] - pos[jj]))
                if d < UMBRAL_CONTACTO:
                    pares_contacto.add((ii, jj))
                if d < UMBRAL_MARGEN:
                    pares_margen.add((ii, jj))

        done = all(trunc.values()) or all(term.values())

    suma_recortes = sum(env.contador_recortes.values())

    return {
        "cobertura_aoi_final": round(
            1.0 - float(np.mean(env._field._grid_aoi)), 6
        ),
        "colisiones_015": len(pares_contacto),
        "colisiones_022": len(pares_margen),
        "reflexiones":    sum(env.contador_reflexiones.values()),
        "frac_pasos_agente_recorte": round(
            suma_recortes / (n_pasos * n_a), 6
        ) if n_pasos else 0.0,
        "frac_embedding_activo": round(emb_activos / emb_total, 6)
        if emb_total else 0.0,
        "uso_grid_fallback": int(uso_grid_fallback),
        "pasos": n_pasos,
    }


# =============================================================================
# FIGURAS  (estilo fig_resultados_CUATRO.png: sin título, 300 dpi, es-ES)
# =============================================================================

def _media_ic95(m: np.ndarray) -> Tuple[float, float]:
    """Media y semiancho del IC95 (aprox. normal) de una muestra."""
    n = len(m)
    s = float(np.std(m, ddof=1))
    return float(np.mean(m)), 1.96 * s / math.sqrt(n)


def figura_cobertura(datos: Dict) -> None:
    """
    Dos paneles: cobertura AoI TOTAL y cobertura POR AGENTE contra n, con
    barras de error IC95 y las dos condiciones de borde. La de por-agente es
    la que responde la pregunta de generalización.
    """
    ns = list(N_VALORES)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))

    for cond, color, marca in (
        ("reflexion",  COLOR_REFLEXION,  "o"),
        ("bloqueante", COLOR_BLOQUEANTE, "s"),
    ):
        tot_m, tot_e, ag_m, ag_e = [], [], [], []
        for n in ns:
            c = np.array([
                float(datos[n][cond][s]["cobertura_aoi_final"]) for s in SEMILLAS
            ])
            m, e = _media_ic95(c)
            tot_m.append(m); tot_e.append(e)
            m2, e2 = _media_ic95(c / n)
            ag_m.append(m2); ag_e.append(e2)

        etq = "Reflexión elástica" if cond == "reflexion" else "Borde bloqueante"
        ax1.errorbar(ns, tot_m, yerr=tot_e, marker=marca, capsize=4,
                     color=color, label=etq, lw=1.8, ms=7)
        ax2.errorbar(ns, ag_m, yerr=ag_e, marker=marca, capsize=4,
                     color=color, label=etq, lw=1.8, ms=7)

    ax1.axvline(N_CONTROL, color="gray", ls=":", lw=1, alpha=0.7)
    ax1.set_xlabel("Número de agentes $n$", fontsize=11)
    ax1.set_ylabel("Cobertura AoI final (total)", fontsize=11)
    ax1.set_xticks(ns)
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=9, framealpha=0.9)

    ax2.axvline(N_CONTROL, color="gray", ls=":", lw=1, alpha=0.7)
    ax2.set_xlabel("Número de agentes $n$", fontsize=11)
    ax2.set_ylabel("Cobertura AoI por agente (cobertura $/\\, n$)", fontsize=11)
    ax2.set_xticks(ns)
    ax2.grid(True, alpha=0.3)
    ax2.legend(fontsize=9, framealpha=0.9)

    plt.tight_layout()
    ruta = DIR_FIGURAS / "fig_escalabilidad_cobertura.png"
    fig.savefig(ruta, dpi=DPI_FIG, bbox_inches="tight")
    plt.close(fig)
    print(f"Figura → {ruta}")


def figura_embedding(datos: Dict) -> None:
    """Fracción de activación del embedding contra n, ambas condiciones."""
    ns = list(N_VALORES)
    fig, ax = plt.subplots(figsize=(7.5, 5.5))

    for cond, color, marca in (
        ("reflexion",  COLOR_REFLEXION,  "o"),
        ("bloqueante", COLOR_BLOQUEANTE, "s"),
    ):
        ms, es = [], []
        for n in ns:
            f = np.array([
                float(datos[n][cond][s]["frac_embedding_activo"]) for s in SEMILLAS
            ])
            m, e = _media_ic95(f)
            ms.append(m); es.append(e)
        etq = "Reflexión elástica" if cond == "reflexion" else "Borde bloqueante"
        ax.errorbar(ns, ms, yerr=es, marker=marca, capsize=4,
                    color=color, label=etq, lw=1.8, ms=7)

    ax.axvline(N_CONTROL, color="gray", ls=":", lw=1, alpha=0.7)
    ax.set_xlabel("Número de agentes $n$", fontsize=11)
    ax.set_ylabel("Fracción de agente-decisión con vecino visible", fontsize=11)
    ax.set_xticks(ns)
    ax.set_ylim(0.0, 1.0)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9, framealpha=0.9)

    plt.tight_layout()
    ruta = DIR_FIGURAS / "fig_escalabilidad_embedding.png"
    fig.savefig(ruta, dpi=DPI_FIG, bbox_inches="tight")
    plt.close(fig)
    print(f"Figura → {ruta}")


def figura_seguridad(datos: Dict) -> None:
    """
    Colisiones por episodio contra n, ambos umbrales (0.15 y 0.22). Se grafica
    la condición "reflexion" (la del protocolo original); el CSV trae ambas.
    """
    ns = list(N_VALORES)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5), sharey=True)

    for ax, cond in ((ax1, "reflexion"), (ax2, "bloqueante")):
        for campo, color, marca, etq in (
            ("colisiones_015", COLOR_U015, "o", "Contacto de chasis (< 0,15 m)"),
            ("colisiones_022", COLOR_U022, "s", "Margen operativo (< 0,22 m)"),
        ):
            ms, es = [], []
            for n in ns:
                c = np.array([
                    float(datos[n][cond][s][campo]) for s in SEMILLAS
                ])
                m, e = _media_ic95(c)
                ms.append(m); es.append(e)
            ax.errorbar(ns, ms, yerr=es, marker=marca, capsize=4,
                        color=color, label=etq, lw=1.8, ms=7)
        ax.axvline(N_CONTROL, color="gray", ls=":", lw=1, alpha=0.7)
        sub = "Reflexión elástica" if cond == "reflexion" else "Borde bloqueante"
        ax.set_xlabel(f"Número de agentes $n$\n({sub})", fontsize=11)
        ax.set_xticks(ns)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=9, framealpha=0.9)
    ax1.set_ylabel("Pares en colisión por episodio", fontsize=11)

    plt.tight_layout()
    ruta = DIR_FIGURAS / "fig_escalabilidad_seguridad.png"
    fig.savefig(ruta, dpi=DPI_FIG, bbox_inches="tight")
    plt.close(fig)
    print(f"Figura → {ruta}")


# =============================================================================
# CUADRO LaTeX
# =============================================================================

def _num(x: float, dec: int) -> str:
    """Formatea un número con separador decimal COMA."""
    return f"{x:.{dec}f}".replace(".", ",")


def cuadro_latex(datos: Dict) -> List[str]:
    """
    Cuadro principal en formato LaTeX, listo para pegar en el documento:
    cobertura total, cobertura por agente, colisiones (ambos umbrales) y
    activación del embedding, por n, condición "reflexion".

    Usa `threeparttable` para las notas (`\\begin{tablenotes}`). Si la
    plantilla de la tesis define otra macro de nota, sólo hay que sustituir
    ese bloque; los datos y la estructura de columnas quedan.
    """
    L: List[str] = []
    L.append(r"% --- Cuadro principal del Exp I (generado por correr_experimento_I.py) ---")
    L.append(r"% Requiere: \usepackage{booktabs}, \usepackage{threeparttable}")
    L.append(r"\begin{table}[htbp]")
    L.append(r"  \centering")
    L.append(r"  \begin{threeparttable}")
    L.append(r"  \caption{Generalización de la política entrenada con cinco "
             r"agentes a enjambres de distinto tamaño, sin reentrenamiento. "
             r"Cien episodios deterministas por celda, condición de reflexión "
             r"elástica (la del entrenamiento).}")
    L.append(r"  \label{tab:exp-i-escalabilidad}")
    L.append(r"  \begin{tabular}{rccccc}")
    L.append(r"    \toprule")
    L.append(r"    $n$ & Cobertura & Cobertura & Colisiones & Colisiones & "
             r"Activación \\")
    L.append(r"        & total     & por agente & $<0{,}15$\,m & $<0{,}22$\,m & "
             r"embedding \\")
    L.append(r"    \midrule")
    for n in N_VALORES:
        c   = np.array([float(datos[n]["reflexion"][s]["cobertura_aoi_final"])
                        for s in SEMILLAS])
        c15 = np.array([float(datos[n]["reflexion"][s]["colisiones_015"])
                        for s in SEMILLAS])
        c22 = np.array([float(datos[n]["reflexion"][s]["colisiones_022"])
                        for s in SEMILLAS])
        emb = np.array([float(datos[n]["reflexion"][s]["frac_embedding_activo"])
                        for s in SEMILLAS])
        marca = r"\,$\star$" if n == N_CONTROL else ""
        L.append(
            f"    {n}{marca} & "
            f"{_num(float(np.mean(c)), 3)} $\\pm$ {_num(float(np.std(c, ddof=1)), 3)} & "
            f"{_num(float(np.mean(c / n)), 3)} & "
            f"{_num(float(np.mean(c15)), 2)} & "
            f"{_num(float(np.mean(c22)), 2)} & "
            f"{_num(float(np.mean(emb)), 3)} \\\\"
        )
    L.append(r"    \bottomrule")
    L.append(r"  \end{tabular}")
    L.append(r"  \begin{tablenotes}\footnotesize")
    L.append(r"    \item Valores: media sobre 100 episodios; $\pm$ desviación "
             r"muestral. Separador decimal: coma.")
    L.append(r"    \item $\star$ $n=5$ es la verificación de control: reproduce "
             r"la cobertura oficial de \texttt{modelo\_PRIMERO} "
             f"({_num(COBERTURA_OFICIAL_N5, 4)}).")
    L.append(r"    \item «Cobertura por agente» = cobertura total $/\,n$. Si la "
             r"política generaliza, se degrada de forma suave con $n$.")
    L.append(r"    \item «Activación embedding» = fracción de agente-decisión "
             r"en las que el agente ve al menos un vecino (\emph{neighbor "
             r"embedding} no nulo).")
    L.append(r"  \end{tablenotes}")
    L.append(r"  \end{threeparttable}")
    L.append(r"\end{table}")
    return L


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    """Corre el factorial 5×2×100 = 1000 episodios y emite CSV, resumen y figuras."""
    DIR_RESULT.mkdir(parents=True, exist_ok=True)
    DIR_FIGURAS.mkdir(parents=True, exist_ok=True)

    print("═" * 78)
    print("  EXPERIMENTO I — generalización a distinto n (5×2×100 = 1000 eps)")
    print("═" * 78)

    modelo = PPO.load(str(RUTA_MODELO), device="cpu")
    accionar = politica_madrl(modelo)

    filas: List[Dict[str, object]] = []
    # datos[n][condicion][seed_ep] = fila
    datos: Dict[int, Dict[str, Dict[int, Dict]]] = {
        n: {c: {} for c in CONDICIONES} for n in N_VALORES
    }

    for n in N_VALORES:
        for cond in CONDICIONES:
            env = make_env(
                n_agents       = n,
                arena_size     = ARENA,
                max_steps      = MAX_STEPS_EP,
                comm_radius    = COMM_RADIUS,
                reward_weights = PESOS_TRIAL13,
                domain_rand    = False,
                seed           = SEED_BASE,
                modo_borde     = cond,
            )
            t0 = time.time()
            for seed_ep in SEMILLAS:
                m = correr_episodio(env, accionar, seed_ep)
                fila = {"n": n, "condicion": cond, "seed_ep": seed_ep, **m}
                filas.append(fila)
                datos[n][cond][seed_ep] = fila

            cob = np.array([
                float(datos[n][cond][s]["cobertura_aoi_final"]) for s in SEMILLAS
            ])
            emb = np.array([
                float(datos[n][cond][s]["frac_embedding_activo"]) for s in SEMILLAS
            ])
            nfb = int(np.sum([datos[n][cond][s]["uso_grid_fallback"]
                              for s in SEMILLAS]))
            print(f"  n={n:2d}  {cond:11s}  cob={float(np.mean(cob)):.4f}"
                  f"  cob/n={float(np.mean(cob))/n:.4f}"
                  f"  emb_activo={float(np.mean(emb)):.3f}"
                  f"  grid_fallback={nfb:3d}/100  ({time.time()-t0:.0f}s)")

        # ── Verificación de control tras completar n = 5 ──────────────────
        if n == N_CONTROL:
            m_ctrl = float(np.mean([
                float(datos[N_CONTROL]["reflexion"][s]["cobertura_aoi_final"])
                for s in SEMILLAS
            ]))
            delta = abs(m_ctrl - COBERTURA_OFICIAL_N5)
            marca = "OK" if delta <= TOL_ABORTO else "DESVIACIÓN"
            print(f"\n  VERIFICACIÓN DE CONTROL (n=5, reflexion):")
            print(f"    replicado {m_ctrl:.10f}  vs oficial "
                  f"{COBERTURA_OFICIAL_N5:.10f}  |Δ|={delta:.2e}  [{marca}]\n")
            if delta > TOL_ABORTO:
                print("  ABORTADO: n=5 bajo 'reflexion' NO reproduce el valor "
                      "oficial del protocolo. La comparación no sería válida. "
                      "No se escriben resultados.")
                sys.exit(1)

    # ── CSV ──────────────────────────────────────────────────────────────
    with open(RUTA_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    print(f"CSV escrito ({len(filas)} filas) → {RUTA_CSV}")

    # ── Figuras ──────────────────────────────────────────────────────────
    figura_cobertura(datos)
    figura_embedding(datos)
    figura_seguridad(datos)

    # ── Resumen ──────────────────────────────────────────────────────────
    def vec(n: int, cond: str, campo: str) -> np.ndarray:
        return np.array([float(datos[n][cond][s][campo]) for s in SEMILLAS])

    L: List[str] = []
    L.append("EXPERIMENTO I — generalización a distinto número de agentes sin")
    L.append("reentrenamiento (parameter sharing).")
    L.append("modelo_PRIMERO (entrenado con 5 agentes) evaluado sobre n ∈ "
             "{2,3,5,7,10}.")
    L.append("5 valores de n × 2 condiciones de borde × 100 semillas = 1000 eps,")
    L.append("pareado por semilla. deterministic=True, domain_rand=False,")
    L.append("500 pasos, arena 3.0×3.0, comm_radius=1.0, n_hotspots=3 (fijo).")
    L.append("=" * 74)
    L.append("")

    # ── Verificación de control ─────────────────────────────────────────
    m_ctrl = float(np.mean(vec(N_CONTROL, "reflexion", "cobertura_aoi_final")))
    L.append("VERIFICACIÓN DE CONTROL (n = 5, condición 'reflexion')")
    L.append(f"  replicado : {m_ctrl:.10f}")
    L.append(f"  oficial   : {COBERTURA_OFICIAL_N5:.10f}  "
             f"(RESULTADO_PRIMERO/metricas_100eps.json)")
    L.append(f"  |Δ|       : {abs(m_ctrl - COBERTURA_OFICIAL_N5):.2e}   "
             f"(umbral de aborto {TOL_ABORTO:.0e})")
    L.append("")

    # ── Uso del fallback de grilla ─────────────────────────────────────
    L.append("USO DEL FALLBACK DE GRILLA EN EL SORTEO DE POSES INICIALES")
    L.append("  (si es alto para n grande, las poses iniciales NO son")
    L.append("   comparables con las de n = 5 y la comparación pareada de ese")
    L.append("   n queda condicionada)")
    L.append(f"  {'n':>3s} {'reflexion':>12s} {'bloqueante':>12s}")
    for n in N_VALORES:
        a = int(np.sum(vec(n, "reflexion",  "uso_grid_fallback")))
        b = int(np.sum(vec(n, "bloqueante", "uso_grid_fallback")))
        L.append(f"  {n:3d} {a:9d}/100 {b:9d}/100")
    L.append("")

    # ── TABLA 1 ─────────────────────────────────────────────────────────
    L.append("TABLA 1 — COBERTURA AoI Y COLISIONES POR n Y CONDICIÓN")
    L.append(f"  {'n':>3s} {'cond':11s} {'cobertura (media±sd)':>24s} "
             f"{'IC95':>20s} {'col<0.15':>10s} {'col<0.22':>10s}")
    for n in N_VALORES:
        for cond in CONDICIONES:
            c = vec(n, cond, "cobertura_aoi_final")
            m, s, lo, hi = ic95(c)
            c15 = float(np.mean(vec(n, cond, "colisiones_015")))
            c22 = float(np.mean(vec(n, cond, "colisiones_022")))
            L.append(f"  {n:3d} {cond:11s} {m:10.4f} ± {s:8.4f}   "
                     f"[{lo:+.4f},{hi:+.4f}] {c15:10.3f} {c22:10.3f}")
    L.append("")

    # ── TABLA 2 ─────────────────────────────────────────────────────────
    L.append("TABLA 2 — COBERTURA POR AGENTE (cobertura / n)")
    L.append("  Si la política generaliza, debería degradarse SUAVEMENTE con n.")
    L.append("  Un colapso fuera de n = 5 se ve acá; la cobertura total")
    L.append("  creciente con n es trivial y no es evidencia de generalización.")
    L.append(f"  {'n':>3s} {'reflexion':>22s} {'bloqueante':>22s}")
    for n in N_VALORES:
        r = vec(n, "reflexion",  "cobertura_aoi_final") / n
        b = vec(n, "bloqueante", "cobertura_aoi_final") / n
        L.append(f"  {n:3d} {float(np.mean(r)):10.4f} ± {float(np.std(r,ddof=1)):7.4f} "
                 f"{float(np.mean(b)):10.4f} ± {float(np.std(b,ddof=1)):7.4f}")
    L.append("")

    # ── TABLA 3 ─────────────────────────────────────────────────────────
    L.append("TABLA 3 — COMPARACIÓN PAREADA DE CADA n CONTRA n = 5")
    L.append("  Δ = cobertura(n) − cobertura(5), pareado por semilla, misma")
    L.append("  condición. El pareo cancela la varianza entre semillas y la")
    L.append("  dinámica común de hotspots. (n = 5 vs 5 da 0 por construcción.)")
    for cond in CONDICIONES:
        L.append(f"  Condición '{cond}':")
        base = vec(N_CONTROL, cond, "cobertura_aoi_final")
        for n in N_VALORES:
            d = vec(n, cond, "cobertura_aoi_final") - base
            m, s, lo, hi = ic95(d) if n != N_CONTROL else (0.0, 0.0, 0.0, 0.0)
            n_peor = int(np.sum(d < 0))
            L.append(f"      n={n:2d}:  Δ = {m:+.4f} ± {s:.4f}  "
                     f"IC95 [{lo:+.4f}, {hi:+.4f}]  peor en {n_peor:3d}/100")
    L.append("")

    # ── TABLA 4 ─────────────────────────────────────────────────────────
    L.append("TABLA 4 — FRACCIÓN DE ACTIVACIÓN DEL EMBEDDING POR n")
    L.append("  Fracción de agente-decisión con al menos un vecino visible")
    L.append("  (neighbor_embedding no nulo). Es el MECANISMO detrás de")
    L.append("  cualquier degradación observada: cuánto del camino multiagente")
    L.append("  de la política se ejercita en cada densidad.")
    L.append(f"  {'n':>3s} {'reflexion':>22s} {'bloqueante':>22s}")
    for n in N_VALORES:
        r = vec(n, "reflexion",  "frac_embedding_activo")
        b = vec(n, "bloqueante", "frac_embedding_activo")
        L.append(f"  {n:3d} {float(np.mean(r)):10.4f} ± {float(np.std(r,ddof=1)):7.4f} "
                 f"{float(np.mean(b)):10.4f} ± {float(np.std(b,ddof=1)):7.4f}")
    L.append("")

    # ── TABLA 5 ─────────────────────────────────────────────────────────
    L.append("TABLA 5 — DEGRADACIÓN POR BORDE BLOQUEANTE, POR CADA n")
    L.append("  Δ = cobertura(bloqueante) − cobertura(reflexion), pareado por")
    L.append("  semilla. Referencia n = 5 (Exp C/D/E): Δ = −0.2297,")
    L.append("  IC95 [−0.2385, −0.2208], −33.7 %, 100/100 episodios peor.")
    L.append(f"  {'n':>3s} {'Δ pareada (media±sd)':>24s} {'IC95':>22s} "
             f"{'rel.':>9s} {'peor':>9s}")
    for n in N_VALORES:
        d = (vec(n, "bloqueante", "cobertura_aoi_final")
             - vec(n, "reflexion", "cobertura_aoi_final"))
        m, s, lo, hi = ic95(d)
        base_refl = float(np.mean(vec(n, "reflexion", "cobertura_aoi_final")))
        rel = 100.0 * m / base_refl if base_refl else 0.0
        n_peor = int(np.sum(d < 0))
        L.append(f"  {n:3d} {m:12.4f} ± {s:8.4f}  [{lo:+.4f},{hi:+.4f}] "
                 f"{rel:+7.1f}% {n_peor:6d}/100")
    L.append("")

    # ── Interpretación ─────────────────────────────────────────────────
    L.append("INTERPRETACIÓN — dos cosas que no hay que confundir")
    L.append("  - Cobertura TOTAL creciente con n es esperable y trivial (más")
    L.append("    agentes cubren más). No es evidencia de generalización.")
    L.append("  - Lo informativo es si la cobertura POR AGENTE se sostiene y si")
    L.append("    el comportamiento cualitativo (colisiones, uso del borde) se")
    L.append("    mantiene fuera del régimen de entrenamiento (n = 5).")
    L.append("  - Con n grande en una arena de 3×3, parte de la degradación por")
    L.append("    agente será por SATURACIÓN ESPACIAL, no por fallo de la")
    L.append("    política. Es una confusión no resuelta por este diseño: no")
    L.append("    puede separar «la política no generaliza» de «no cabe más")
    L.append("    cobertura útil en 9 m²». El dato de activación del embedding")
    L.append("    (Tabla 4) y el de colisiones (Tabla 1) ayudan a discriminar,")
    L.append("    pero no lo cierran.")
    L.append("")

    # ── Cuadro LaTeX ───────────────────────────────────────────────────
    L.append("=" * 74)
    L.append("CUADRO EN FORMATO LaTeX (separador decimal COMA) — listo para pegar")
    L.append("=" * 74)
    L.extend(cuadro_latex(datos))
    L.append("")

    resumen = "\n".join(L)
    RUTA_RESUMEN.write_text(resumen, encoding="utf-8")
    print(f"Resumen → {RUTA_RESUMEN}\n")
    print(resumen)


if __name__ == "__main__":
    main()
