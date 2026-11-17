"""
test_lambda_cbf.py
==================
Comparación A/B entre dos valores de λ_cbf a 200k steps con seed=42.

Motivación:
    La seed=42 del test de reproducibilidad alcanzó cobertura AoI final 0.70
    pero con 0.5 pares-colisión por episodio — inaceptable para la demo
    física en Pololus reales, donde una colisión puede dañar hardware.
    ¿Conviene subir λ_cbf a 5.0 antes de 5M o confiar en que 5M reducirá
    colisiones por la mayor experiencia? Este script responde con datos.

Variantes:
    A: Hiperparámetros exactos del Trial 13 (λ_cbf = 2.9655)
    B: Hiperparámetros del Trial 13 + λ_cbf = 5.0 (↑ penalización proximidad)

Protocolo por variante:
    1. Entrenar 200k steps, seed=42, n_agentes=5, max_steps_ep=500, n_envs=4,
       domain_rand=True (mismo setup que verificacion_seeds).
    2. Evaluar modelo final en 30 episodios deterministas con domain_rand=False.
    3. Recolectar: cobertura_aoi_final, colisiones_pares, distancia_recorrida,
       step_primera_cobertura_50.

Criterio de decisión:
    - cob_B > 0.6 AND col_B < 0.2          → 5M con λ_cbf=5.0
    - cob_B < 0.5                          → 5M con λ_cbf=2.97 + filtrar demo
    - |cob_A-cob_B| < 0.05 AND similar col → 5M con λ_cbf=2.97 (simplicidad)
    - otro                                 → decisión matizada según trade-off

Salidas:
    modelos/tesis_v1/test_lambda_cbf/
        variante_A/
            modelo_final.zip
            metricas_cobertura.json
            tensorboard/
        variante_B/
            modelo_final.zip
            metricas_cobertura.json
            tensorboard/
        comparacion.md
        comparacion.png
"""
from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from stable_baselines3 import PPO

from train import (
    ConfigEntorno,
    ConfigEntrenamiento,
    HiperparametrosPPO,
    PesosRecompensa,
    construir_modelo_ppo,
    construir_vec_env_entrenamiento,
    construir_vec_env_evaluacion,
)
from swarm_env_skeleton import D_SAFE, make_env


# ──────────────────────────────────────────────────────────────────────────────
# Configuración del experimento
# ──────────────────────────────────────────────────────────────────────────────
DIR_BASE:      Path = Path("modelos/tesis_v1/test_lambda_cbf")
TRIAL_13_JSON: Path = Path("modelos/tesis_v1/metadata_trials/trial_013.json")

SEED:        int = 42
N_STEPS:     int = 200_000
N_EPS_EVAL:  int = 30
MAX_STEPS:   int = 500
N_AGENTES:   int = 5
ARENA:       tuple = (3.0, 3.0)
COMM_RADIUS: float = 1.0
N_ENVS:      int = 4

VARIANTES: List[Dict[str, Any]] = [
    {"nombre": "A", "lambda_cbf": 2.9655314099141474, "descripcion": "Trial 13 exacto"},
    {"nombre": "B", "lambda_cbf": 5.0,                 "descripcion": "Trial 13 + λ_cbf ↑"},
]

# Umbrales del criterio
COB_OBJETIVO:     float = 0.60   # cobertura mínima para considerar viable
COL_OBJETIVO:     float = 0.20   # pares-colisión máximos aceptables (demo física)
COB_COLAPSO:      float = 0.50   # si cobertura cae por debajo → B colapsó
SIMILITUD_COB:    float = 0.05   # diferencia máxima para considerar "similar"
SIMILITUD_COL:    float = 0.5    # diferencia máxima para considerar "similar"

logger = logging.getLogger("test_lambda")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(_h)


# ──────────────────────────────────────────────────────────────────────────────
# Carga de hiperparámetros del Trial 13
# ──────────────────────────────────────────────────────────────────────────────
def cargar_trial13() -> tuple[HiperparametrosPPO, PesosRecompensa]:
    with open(TRIAL_13_JSON, encoding="utf-8") as f:
        meta = json.load(f)
    return (
        HiperparametrosPPO(**meta["hparams"]),
        PesosRecompensa(**meta["pesos_recompensa"]),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Entrenamiento por variante
# ──────────────────────────────────────────────────────────────────────────────
def entrenar_variante(
    nombre:     str,
    hparams:    HiperparametrosPPO,
    pesos:      PesosRecompensa,
) -> Path:
    """Entrena PPO 200k steps con `pesos` y guarda modelo_final.zip."""
    dir_var = DIR_BASE / f"variante_{nombre}"
    dir_var.mkdir(parents=True, exist_ok=True)

    config_env = ConfigEntorno(
        n_agentes    = N_AGENTES,
        max_steps_ep = MAX_STEPS,
        domain_rand  = True,
    )
    config_train = ConfigEntrenamiento(
        n_envs_entren = N_ENVS,
        n_envs_eval   = 2,
        seed          = SEED,
    )

    env_train = None
    env_eval  = None
    try:
        logger.info("━" * 70)
        logger.info(
            "VARIANTE %s — entrenando %d steps (λ_cbf=%.4f)",
            nombre, N_STEPS, pesos.lambda_cbf,
        )
        logger.info("━" * 70)

        env_train = construir_vec_env_entrenamiento(
            config_env, config_train, pesos,
            n_envs=N_ENVS, seed=SEED,
        )
        # Env de eval durante entrenamiento (para callback interno de SB3 si se quisiera)
        env_eval = construir_vec_env_evaluacion(
            config_env, config_train, pesos, seed=SEED + 500,
        )

        dir_tb = dir_var / "tensorboard"
        modelo = construir_modelo_ppo(
            env_train, hparams, config_train,
            dir_tensorboard = str(dir_tb),
            seed            = SEED,
            verbose         = 0,
        )

        t_ini = time.time()
        modelo.learn(
            total_timesteps     = N_STEPS,
            reset_num_timesteps = True,
            tb_log_name         = f"variante_{nombre}",
            progress_bar        = False,
        )
        dur_s = time.time() - t_ini

        ruta_modelo = dir_var / "modelo_final.zip"
        modelo.save(str(ruta_modelo))

        logger.info(
            "VARIANTE %s — entrenamiento terminado (%.1fs, %.0f steps/s)",
            nombre, dur_s, N_STEPS / dur_s,
        )
        return ruta_modelo
    finally:
        if env_train is not None:
            try: env_train.close()
            except Exception: pass
        if env_eval is not None:
            try: env_eval.close()
            except Exception: pass


# ──────────────────────────────────────────────────────────────────────────────
# Evaluación determinista multi-métrica
# ──────────────────────────────────────────────────────────────────────────────
def evaluar_episodio(modelo: PPO, env, seed_ep: int) -> Dict[str, float]:
    """Corre UN episodio determinista y retorna las 4 métricas."""
    obs_dict, _ = env.reset(seed=seed_ep)
    agents = list(obs_dict.keys())
    n_a = len(agents)

    cob_hist:   List[float]     = []
    pos_hist:   List[np.ndarray] = []
    pares_col:  set             = set()

    pos_init = np.array([env._estados[a][:2] for a in agents])
    pos_hist.append(pos_init.copy())

    done = False
    while not done:
        obs_array = np.stack([obs_dict[a] for a in agents])
        acciones, _ = modelo.predict(obs_array, deterministic=True)
        accion_dict = {a: acciones[i] for i, a in enumerate(agents)}
        obs_dict, _, term, trunc, _ = env.step(accion_dict)

        cob_hist.append(1.0 - float(np.mean(env._field._grid_aoi)))
        pos_curr = np.array([env._estados[a][:2] for a in agents])
        pos_hist.append(pos_curr.copy())

        for i in range(n_a):
            for j in range(i + 1, n_a):
                if np.linalg.norm(pos_curr[i] - pos_curr[j]) < D_SAFE:
                    pares_col.add((i, j))

        done = all(trunc.values()) or all(term.values())

    cob_final = cob_hist[-1] if cob_hist else 0.0

    pos_arr = np.asarray(pos_hist)  # (T+1, n_a, 2)
    deltas = np.linalg.norm(np.diff(pos_arr, axis=0), axis=2)
    dist_mean = float(np.mean(deltas.sum(axis=0)))

    cob_np = np.asarray(cob_hist)
    idx_cross = np.where(cob_np >= 0.5)[0]
    t_50pct = int(idx_cross[0]) if len(idx_cross) > 0 else MAX_STEPS

    return {
        "cobertura_aoi_final":            cob_final,
        "n_colisiones":                   len(pares_col),
        "distancia_total_recorrida":      dist_mean,
        "tiempo_primera_cobertura_50pct": t_50pct,
    }


def evaluar_variante(
    nombre:      str,
    ruta_modelo: Path,
    pesos:       PesosRecompensa,
    n_episodios: int = N_EPS_EVAL,
) -> Dict[str, Any]:
    """Evalúa la variante en n_episodios deterministas y agrega métricas."""
    dir_var = DIR_BASE / f"variante_{nombre}"

    logger.info("VARIANTE %s — evaluando %d episodios deterministas", nombre, n_episodios)
    modelo = PPO.load(str(ruta_modelo))

    # Env raw con pesos de la variante (mismos usados en entrenamiento)
    env = make_env(
        n_agents       = N_AGENTES,
        arena_size     = ARENA,
        max_steps      = MAX_STEPS,
        comm_radius    = COMM_RADIUS,
        reward_weights = {
            "lambda_gradient": pesos.lambda_gradient,
            "lambda_entropy":  pesos.lambda_entropy,
            "lambda_ibrm":     pesos.lambda_ibrm,
            "lambda_cbf":      pesos.lambda_cbf,
        },
        domain_rand    = False,
        seed           = SEED,
    )

    eps_datos: List[Dict[str, Any]] = []
    t_ini = time.time()
    for i in range(n_episodios):
        seed_ep = SEED * 10_000 + i
        m = evaluar_episodio(modelo, env, seed_ep=seed_ep)
        m["episodio"] = i
        eps_datos.append(m)
    dur_s = time.time() - t_ini

    # Agregados
    claves = [
        "cobertura_aoi_final",
        "n_colisiones",
        "distancia_total_recorrida",
        "tiempo_primera_cobertura_50pct",
    ]
    agregados: Dict[str, Dict[str, float]] = {}
    for k in claves:
        vals = np.array([ep[k] for ep in eps_datos], dtype=np.float64)
        agregados[k] = {
            "media": float(np.mean(vals)),
            "std":   float(np.std(vals)),
            "min":   float(np.min(vals)),
            "max":   float(np.max(vals)),
        }

    # Persistir
    ruta_json = dir_var / "metricas_cobertura.json"
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump({
            "variante":       nombre,
            "lambda_cbf":     pesos.lambda_cbf,
            "n_episodios":    n_episodios,
            "duracion_s":     dur_s,
            "agregados":      agregados,
            "episodios":      eps_datos,
        }, f, indent=2, ensure_ascii=False)

    logger.info(
        "VARIANTE %s — eval terminada (%.1fs): cob=%.3f±%.3f  col=%.1f±%.1f  "
        "dist=%.2f  t50=%.0f",
        nombre, dur_s,
        agregados["cobertura_aoi_final"]["media"],
        agregados["cobertura_aoi_final"]["std"],
        agregados["n_colisiones"]["media"],
        agregados["n_colisiones"]["std"],
        agregados["distancia_total_recorrida"]["media"],
        agregados["tiempo_primera_cobertura_50pct"]["media"],
    )

    try:
        env.close()
    except Exception:
        pass

    return {
        "variante":    nombre,
        "lambda_cbf":  pesos.lambda_cbf,
        "agregados":   agregados,
        "episodios":   eps_datos,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Figura comparativa
# ──────────────────────────────────────────────────────────────────────────────
def generar_figura(resultados: List[Dict[str, Any]], ruta_png: Path) -> None:
    """1×2: boxplot cobertura | boxplot colisiones."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    colores = ["tab:blue", "tab:orange"]

    # Subplot 1: Cobertura
    datos_cob = [[ep["cobertura_aoi_final"] for ep in r["episodios"]] for r in resultados]
    labels = [f"Var {r['variante']}\n(λ_cbf={r['lambda_cbf']:.2f})" for r in resultados]

    bp1 = axes[0].boxplot(
        datos_cob, tick_labels=labels, patch_artist=True, widths=0.5,
        showmeans=True,
        meanprops={"marker": "D", "markerfacecolor": "white",
                   "markeredgecolor": "black", "markersize": 7},
    )
    for patch, color in zip(bp1["boxes"], colores):
        patch.set_facecolor(color); patch.set_alpha(0.5)
    for i, vals in enumerate(datos_cob):
        xs = np.random.normal(i + 1, 0.04, size=len(vals))
        axes[0].scatter(xs, vals, alpha=0.5, s=16, color=colores[i],
                        edgecolors="k", linewidths=0.4, zorder=3)
    axes[0].axhline(COB_OBJETIVO, color="green", ls="--", lw=1.2, alpha=0.65)
    axes[0].text(0.02, COB_OBJETIVO + 0.005, f"cob objetivo = {COB_OBJETIVO}",
                 color="green", fontsize=9, transform=axes[0].get_yaxis_transform())
    axes[0].axhline(COB_COLAPSO, color="red", ls=":", lw=1.0, alpha=0.55)
    axes[0].text(0.02, COB_COLAPSO - 0.015, f"colapso < {COB_COLAPSO}",
                 color="red", fontsize=9, transform=axes[0].get_yaxis_transform())
    axes[0].set_title("Cobertura AoI final (30 eps deterministas)", fontsize=12, pad=8)
    axes[0].set_ylabel("cobertura_aoi_final", fontsize=10)
    axes[0].grid(alpha=0.3, axis="y")

    # Subplot 2: Colisiones
    datos_col = [[ep["n_colisiones"] for ep in r["episodios"]] for r in resultados]
    bp2 = axes[1].boxplot(
        datos_col, tick_labels=labels, patch_artist=True, widths=0.5,
        showmeans=True,
        meanprops={"marker": "D", "markerfacecolor": "white",
                   "markeredgecolor": "black", "markersize": 7},
    )
    for patch, color in zip(bp2["boxes"], colores):
        patch.set_facecolor(color); patch.set_alpha(0.5)
    for i, vals in enumerate(datos_col):
        xs = np.random.normal(i + 1, 0.04, size=len(vals))
        axes[1].scatter(xs, vals, alpha=0.5, s=16, color=colores[i],
                        edgecolors="k", linewidths=0.4, zorder=3)
    axes[1].axhline(COL_OBJETIVO, color="green", ls="--", lw=1.2, alpha=0.65)
    axes[1].text(0.02, COL_OBJETIVO + 0.05, f"col objetivo < {COL_OBJETIVO}",
                 color="green", fontsize=9, transform=axes[1].get_yaxis_transform())
    axes[1].set_title("Pares en colisión por episodio", fontsize=12, pad=8)
    axes[1].set_ylabel("n_colisiones", fontsize=10)
    axes[1].grid(alpha=0.3, axis="y")

    fig.suptitle(
        f"Comparación λ_cbf — {N_STEPS:,} steps, seed={SEED}, "
        f"{N_EPS_EVAL} episodios eval",
        fontsize=13, y=1.02,
    )
    plt.tight_layout()
    fig.savefig(ruta_png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logger.info("Figura: %s", ruta_png)


# ──────────────────────────────────────────────────────────────────────────────
# Criterio de decisión
# ──────────────────────────────────────────────────────────────────────────────
def aplicar_criterio(resultados: List[Dict[str, Any]]) -> Dict[str, Any]:
    r_A = next(r for r in resultados if r["variante"] == "A")
    r_B = next(r for r in resultados if r["variante"] == "B")

    cob_A = r_A["agregados"]["cobertura_aoi_final"]["media"]
    col_A = r_A["agregados"]["n_colisiones"]["media"]
    cob_B = r_B["agregados"]["cobertura_aoi_final"]["media"]
    col_B = r_B["agregados"]["n_colisiones"]["media"]

    # Caso 1: B mantiene cobertura y reduce colisiones fuertemente
    if cob_B > COB_OBJETIVO and col_B < COL_OBJETIVO:
        return {
            "caso":         "B_GANA",
            "variante_5M":  "B",
            "lambda_cbf":   5.0,
            "razon": (
                f"Variante B mantiene cobertura ({cob_B:.3f} > {COB_OBJETIVO}) "
                f"Y reduce colisiones a un nivel aceptable para demo física "
                f"({col_B:.2f} < {COL_OBJETIVO})."
            ),
        }

    # Caso 2: B colapsa cobertura
    if cob_B < COB_COLAPSO:
        return {
            "caso":         "B_COLAPSA",
            "variante_5M":  "A",
            "lambda_cbf":   r_A["lambda_cbf"],
            "razon": (
                f"Variante B colapsó la cobertura ({cob_B:.3f} < {COB_COLAPSO}). "
                f"Proceder con Variante A (λ_cbf={r_A['lambda_cbf']:.2f}, "
                f"cobertura {cob_A:.3f}, colisiones {col_A:.2f}) y filtrar "
                f"episodios con colisiones para la demo física."
            ),
        }

    # Caso 3: resultados similares
    if abs(cob_A - cob_B) < SIMILITUD_COB and abs(col_A - col_B) < SIMILITUD_COL:
        return {
            "caso":         "SIMILARES",
            "variante_5M":  "A",
            "lambda_cbf":   r_A["lambda_cbf"],
            "razon": (
                f"Ambas variantes dan resultados comparables "
                f"(Δcob={cob_A-cob_B:+.3f}, Δcol={col_A-col_B:+.2f}). "
                f"Proceder con Variante A por simplicidad (un solo hiperparámetro "
                f"de Optuna, sin ajustes manuales)."
            ),
        }

    # Caso 4: matizado — B bajó colisiones algo pero no hasta 0.2, o bajó cobertura algo
    # Evaluar el trade-off explícitamente
    mejora_col = col_A - col_B  # >0 si B tiene menos colisiones
    perdida_cob = cob_A - cob_B  # >0 si B perdió cobertura
    if mejora_col > 0.3 and perdida_cob < 0.10 and cob_B > COB_OBJETIVO:
        return {
            "caso":         "B_MEJORA_MARGINAL",
            "variante_5M":  "B",
            "lambda_cbf":   5.0,
            "razon": (
                f"B reduce colisiones en {mejora_col:.2f} con pérdida de "
                f"cobertura solo {perdida_cob:.3f} y aún > {COB_OBJETIVO}. "
                "Vale la pena para la demo."
            ),
        }
    return {
        "caso":         "SIN_DECISION_CLARA",
        "variante_5M":  "A",
        "lambda_cbf":   r_A["lambda_cbf"],
        "razon": (
            f"Trade-off ambiguo: cob_A={cob_A:.3f} col_A={col_A:.2f} vs "
            f"cob_B={cob_B:.3f} col_B={col_B:.2f}. Default a A "
            f"por ser el óptimo de Optuna; revisar datos a mano."
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Reporte markdown
# ──────────────────────────────────────────────────────────────────────────────
def generar_reporte(
    resultados:  List[Dict[str, Any]],
    diagnostico: Dict[str, Any],
    ruta_md:     Path,
) -> None:
    r_A = next(r for r in resultados if r["variante"] == "A")
    r_B = next(r for r in resultados if r["variante"] == "B")

    lineas: List[str] = [
        "# Comparación A/B de λ_cbf — seed=42, 200k steps",
        "",
        f"*Generado: {time.strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
        "## Motivación",
        "",
        "La seed 42 del test de reproducibilidad alcanzó cobertura 0.698 pero "
        "con 0.5 pares-colisión por episodio — demasiado para la demo física "
        "en Pololus. ¿Conviene subir λ_cbf a 5.0 antes del 5M o confiar en que "
        "5M reducirá colisiones por mayor experiencia?",
        "",
        "## Variantes",
        "",
        "| Variante | λ_cbf | Descripción |",
        "|----------|------:|-------------|",
        f"| A | {r_A['lambda_cbf']:.4f} | Hiperparámetros Trial 13 exactos |",
        f"| B | {r_B['lambda_cbf']:.4f} | Trial 13 + λ_cbf elevado |",
        "",
        "Resto de hiperparámetros idénticos (Trial 13): "
        "lr=6.86e-05, γ=0.9845, n_steps=128, λ_grad=0.562, λ_ent=1.140, λ_ibrm=0.484.",
        "",
        f"- **Seed:** {SEED}",
        f"- **Steps entrenamiento:** {N_STEPS:,}",
        f"- **Eval:** {N_EPS_EVAL} episodios deterministas sin domain_rand",
        "",
        "## Tabla comparativa",
        "",
        "| Métrica | Variante A (μ±σ) | Variante B (μ±σ) | Δ (B − A) |",
        "|---------|-----------------:|-----------------:|----------:|",
    ]

    claves = [
        ("cobertura_aoi_final",            "Cobertura AoI final",        "{:.3f}±{:.3f}"),
        ("n_colisiones",                   "Pares en colisión",          "{:.2f}±{:.2f}"),
        ("distancia_total_recorrida",      "Distancia recorrida [m]",    "{:.2f}±{:.2f}"),
        ("tiempo_primera_cobertura_50pct", "Step al cruzar cob. 0.5",    "{:.0f}±{:.0f}"),
    ]
    for clave, nombre, fmt in claves:
        ag_A = r_A["agregados"][clave]
        ag_B = r_B["agregados"][clave]
        delta = ag_B["media"] - ag_A["media"]
        delta_str = f"{delta:+.3f}" if abs(delta) < 10 else f"{delta:+.1f}"
        lineas.append(
            f"| {nombre} | {fmt.format(ag_A['media'], ag_A['std'])} "
            f"| {fmt.format(ag_B['media'], ag_B['std'])} | {delta_str} |"
        )

    # Rangos
    lineas += [
        "",
        "### Rangos (min – max)",
        "",
        "| Métrica | Variante A | Variante B |",
        "|---------|-----------:|-----------:|",
    ]
    for clave, nombre, _ in claves:
        ag_A = r_A["agregados"][clave]
        ag_B = r_B["agregados"][clave]
        lineas.append(
            f"| {nombre} | {ag_A['min']:.2f} – {ag_A['max']:.2f} "
            f"| {ag_B['min']:.2f} – {ag_B['max']:.2f} |"
        )

    # Criterio
    lineas += [
        "",
        "## Criterio de decisión",
        "",
        "| Caso | Condición | Variante 5M |",
        "|------|-----------|:----------:|",
        f"| 🟢 B_GANA         | cob_B > {COB_OBJETIVO} AND col_B < {COL_OBJETIVO} | B (λ_cbf=5.0) |",
        f"| 🔴 B_COLAPSA      | cob_B < {COB_COLAPSO} | A + filtrar demo |",
        f"| 🟡 SIMILARES      | Δcob < {SIMILITUD_COB} AND Δcol < {SIMILITUD_COL} | A (simplicidad) |",
        f"| 🟡 B_MEJORA_MARGINAL | Δcol > 0.3 AND Δcob < 0.10 AND cob_B > {COB_OBJETIVO} | B (trade-off favorable) |",
        "",
        f"### Resultado: **{diagnostico['caso']}** → Variante **{diagnostico['variante_5M']}** "
        f"(λ_cbf = {diagnostico['lambda_cbf']:.4f})",
        "",
        diagnostico["razon"],
        "",
        "## Comando para el 5M",
        "",
    ]

    if diagnostico["variante_5M"] == "B":
        lineas += [
            "La Variante B requiere modificar manualmente `λ_cbf=5.0` antes de entrenar. ",
            "Ya está serializada en `modelos/tesis_v1/test_lambda_cbf/variante_B/metricas_cobertura.json`. ",
            "Antes del 5M, editar la forma como se cargan los pesos en `train.py` o pasar "
            "los nuevos pesos explícitamente.",
        ]
    else:
        lineas += [
            "```powershell",
            "python train.py --modo entrenar --nombre_estudio tesis_v1 "
            "--n_pasos 5000000 --n_agentes 5 --max_steps_ep 500 --n_envs 4 --seed 42",
            "```",
            "",
            "(Usa `mejores_hiperparametros.json` que tiene λ_cbf=2.97 del Trial 13.)",
        ]

    lineas += [
        "",
        "## Figura",
        "",
        "![Comparación boxplots](comparacion.png)",
    ]

    ruta_md.write_text("\n".join(lineas), encoding="utf-8")
    logger.info("Reporte: %s", ruta_md)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    DIR_BASE.mkdir(parents=True, exist_ok=True)
    hparams_base, pesos_base = cargar_trial13()

    logger.info("=" * 70)
    logger.info("TEST λ_cbf — A vs B")
    logger.info("=" * 70)
    logger.info(
        "Hparams base (Trial 13): lr=%.2e  γ=%.4f  n_steps=%d  batch=%d  epochs=%d",
        hparams_base.learning_rate, hparams_base.gamma,
        hparams_base.n_steps, hparams_base.batch_size, hparams_base.n_epochs,
    )
    logger.info(
        "Pesos base: λ_grad=%.3f  λ_ent=%.3f  λ_ibrm=%.3f  λ_cbf=%.3f",
        pesos_base.lambda_gradient, pesos_base.lambda_entropy,
        pesos_base.lambda_ibrm, pesos_base.lambda_cbf,
    )

    resultados: List[Dict[str, Any]] = []
    for var in VARIANTES:
        nombre  = var["nombre"]
        pesos_v = replace(pesos_base, lambda_cbf=var["lambda_cbf"])

        ruta_modelo = entrenar_variante(nombre, hparams_base, pesos_v)
        r = evaluar_variante(nombre, ruta_modelo, pesos_v)
        resultados.append(r)

    # Figura
    ruta_png = DIR_BASE / "comparacion.png"
    generar_figura(resultados, ruta_png)

    # Criterio
    diagnostico = aplicar_criterio(resultados)

    # Reporte
    ruta_md = DIR_BASE / "comparacion.md"
    generar_reporte(resultados, diagnostico, ruta_md)

    # Resumen consola
    logger.info("=" * 70)
    logger.info("RESULTADO FINAL")
    logger.info("=" * 70)
    for r in resultados:
        ag = r["agregados"]
        logger.info(
            "  Variante %s (λ_cbf=%.3f) → cob=%.3f±%.3f  col=%.2f±%.2f  "
            "dist=%.2f  t50=%.0f",
            r["variante"], r["lambda_cbf"],
            ag["cobertura_aoi_final"]["media"], ag["cobertura_aoi_final"]["std"],
            ag["n_colisiones"]["media"],        ag["n_colisiones"]["std"],
            ag["distancia_total_recorrida"]["media"],
            ag["tiempo_primera_cobertura_50pct"]["media"],
        )
    logger.info(
        "  CASO: %s → usar Variante %s (λ_cbf=%.4f) para el 5M",
        diagnostico["caso"], diagnostico["variante_5M"], diagnostico["lambda_cbf"],
    )
    logger.info("  Reporte: %s", ruta_md)


if __name__ == "__main__":
    main()
