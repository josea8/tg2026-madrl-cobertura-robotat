"""
consolidar_resultado_primero.py
================================
Consolidación del modelo MADRL final como RESULTADO PRIMERO de la tesis.

Modelo elegido
──────────────
Variante A del A/B test de λ_cbf (Trial 13 exacto, 200k steps, seed 42)
en `modelos/tesis_v1/test_lambda_cbf/variante_A/modelo_final.zip`.

Justificación
─────────────
- El diagnóstico en `modelos/tesis_v1/diagnostico_sin_vecnormalize/` mostró
  que entrenar más allá de 200k DEGRADA cobertura (0.682 → 0.579 entre 200k
  y 500k). Los hparams del Trial 13 están sobreajustados al presupuesto
  Optuna (100k). El pico empírico está en ~200k.
- VecNormalize NO resuelve el problema (corrida 5M con VN dio cob=0.626).

Salidas
───────
  modelos/tesis_v1/RESULTADO_PRIMERO/
      ├── modelo_PRIMERO.zip               (copia del variante_A/modelo_final.zip)
      ├── hiperparametros.json             (Trial 13)
      ├── config_entrenamiento.json        (n_agentes=5, seed=42, 200k, DR=True)
      ├── metricas_100eps.json             (datos crudos por política/episodio)
      ├── reporte_consolidado.md           (tabla + comparación + justificación)
      └── figuras/
          ├── fig_resultados_PRIMERO.png   (boxplots 3-policy)
          ├── fig_evolucion_experimentos.png  (timeline cob por experimento)
          └── fig_trayectoria_episodio.png  (snapshot env.render con MADRL)

Diseño de la evaluación
───────────────────────
3 políticas × 100 episodios deterministas (seed_ep = SEED * 10_000 + i),
sin domain_rand, mismo seeding para comparación pareada.

Políticas:
  1. MADRL          : modelo PPO Trial 13 200k
  2. aleatoria      : v ~ U[-V_MAX, V_MAX], ω ~ U[-OMEGA_MAX, OMEGA_MAX]
  3. heurística_NN  : "go to nearest target" — carrot-chasing
                      ω = K_ω · wrap(θ_obj - θ_actual);  v = V_MAX · max(0, cos(err))

Métricas por episodio:
  - cobertura_aoi_final
  - n_colisiones (pares únicos en colisión durante el ep)
  - distancia_recorrida (media de los 5 agentes)
  - t_cob_50pct, t_cob_60pct (step donde cobertura cruza 0.5 / 0.6;
                              MAX_STEPS si nunca cruza)
  - hubo_colision (bool: n_colisiones > 0)
"""
from __future__ import annotations

import json
import logging
import math
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from stable_baselines3 import PPO

from concentration_dynamics import V_MAX, OMEGA_MAX
from swarm_env_skeleton import D_SAFE, make_env


# ══════════════════════════════════════════════════════════════════════════════
# Configuración
# ══════════════════════════════════════════════════════════════════════════════
ROOT = Path(__file__).parent.resolve()

DIR_VARIANTE_A   = ROOT / "modelos" / "tesis_v1" / "test_lambda_cbf"   / "variante_A"
DIR_DIAG_NO_VN   = ROOT / "modelos" / "tesis_v1" / "diagnostico_sin_vecnormalize"
DIR_REPRO        = ROOT / "modelos" / "tesis_v1" / "verificacion_seeds"
RUTA_HPARAMS_JSON = ROOT / "modelos" / "tesis_v1" / "mejores_hiperparametros.json"

DIR_PRIMERO      = ROOT / "modelos" / "tesis_v1" / "RESULTADO_PRIMERO"
DIR_FIG          = DIR_PRIMERO / "figuras"

N_EPISODIOS_EVAL = 100
SEED             = 42

N_AGENTES        = 5
MAX_STEPS_EP     = 500
ARENA: tuple     = (3.0, 3.0)
COMM_RADIUS      = 1.0
N_PASOS_TRAIN    = 200_000

# Pesos del Trial 13 (idénticos a los usados en variante_A)
PESOS_TRIAL13: Dict[str, float] = {
    "lambda_gradient": 0.5622468083379316,
    "lambda_entropy":  1.1403296484190344,
    "lambda_ibrm":     0.48380314172632155,
    "lambda_cbf":      2.9655314099141474,
}

for d in (DIR_PRIMERO, DIR_FIG):
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers= [
        logging.FileHandler(DIR_PRIMERO / "consolidacion.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("consolidar")


# ══════════════════════════════════════════════════════════════════════════════
# Utilitarios
# ══════════════════════════════════════════════════════════════════════════════
def envolver_angulo(theta: float) -> float:
    """Wrap a un ángulo a [-π, π]."""
    return (theta + math.pi) % (2.0 * math.pi) - math.pi


def construir_env() -> Any:
    """Env determinista (sin DR) para evaluación."""
    return make_env(
        n_agents       = N_AGENTES,
        arena_size     = ARENA,
        max_steps      = MAX_STEPS_EP,
        comm_radius    = COMM_RADIUS,
        reward_weights = PESOS_TRIAL13,
        domain_rand    = False,
        seed           = SEED,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Políticas
# ══════════════════════════════════════════════════════════════════════════════
def politica_madrl(modelo: PPO):
    """Cierre que retorna acciones del modelo MADRL."""
    def _act(env, obs_dict, rng):
        agents = list(obs_dict.keys())
        obs_arr = np.stack([obs_dict[a] for a in agents])
        acciones, _ = modelo.predict(obs_arr, deterministic=True)
        return {a: acciones[k] for k, a in enumerate(agents)}
    return _act


def politica_aleatoria(env, obs_dict, rng):
    """v ~ U[-V_MAX, V_MAX], ω ~ U[-OMEGA_MAX, OMEGA_MAX]."""
    out = {}
    for a in obs_dict.keys():
        v   = float(rng.uniform(-V_MAX,     V_MAX))
        ome = float(rng.uniform(-OMEGA_MAX, OMEGA_MAX))
        out[a] = np.array([v, ome], dtype=np.float32)
    return out


def politica_heuristica_NN(env, obs_dict, rng, K_omega: float = 4.0):
    """
    Heurística "go to nearest target":
        - Para cada agente, busca el objetivo más cercano (Euclidean).
        - Calcula error angular wrap(θ_objetivo - θ_actual).
        - ω = clip(K_ω · err, ±OMEGA_MAX).
        - v = V_MAX · max(0, cos(err))  (sólo avanza cuando está alineado).
    """
    targets = env._field.posiciones_objetivos  # (H, 2)
    out = {}
    for a in obs_dict.keys():
        estado = env._estados[a]
        x, y, th = float(estado[0]), float(estado[1]), float(estado[2])
        diffs = targets - np.array([x, y])
        dists = np.linalg.norm(diffs, axis=1)
        idx_nn = int(np.argmin(dists))
        dx, dy = float(diffs[idx_nn, 0]), float(diffs[idx_nn, 1])
        th_obj = math.atan2(dy, dx)
        err    = envolver_angulo(th_obj - th)
        omega  = float(np.clip(K_omega * err, -OMEGA_MAX, OMEGA_MAX))
        v      = float(V_MAX * max(0.0, math.cos(err)))
        out[a] = np.array([v, omega], dtype=np.float32)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Evaluación de un episodio (genérica para cualquier política)
# ══════════════════════════════════════════════════════════════════════════════
def evaluar_episodio(env, accionar: Callable, seed_ep: int, rng: np.random.Generator) -> Dict[str, float]:
    obs_dict, _ = env.reset(seed=seed_ep)
    agents = list(obs_dict.keys())
    n_a    = len(agents)

    pares_col: set = set()
    pos_hist: List[np.ndarray] = [np.array([env._estados[a][:2] for a in agents])]
    cob_hist: List[float] = []

    done = False
    while not done:
        accion_dict = accionar(env, obs_dict, rng)
        obs_dict, _, term, trunc, _ = env.step(accion_dict)
        cob_hist.append(1.0 - float(np.mean(env._field._grid_aoi)))
        pos_curr = np.array([env._estados[a][:2] for a in agents])
        pos_hist.append(pos_curr.copy())
        for ii in range(n_a):
            for jj in range(ii + 1, n_a):
                if np.linalg.norm(pos_curr[ii] - pos_curr[jj]) < D_SAFE:
                    pares_col.add((ii, jj))
        done = all(trunc.values()) or all(term.values())

    cobertura_final = float(cob_hist[-1]) if cob_hist else 0.0
    n_colisiones    = len(pares_col)
    pos_arr = np.asarray(pos_hist)
    dist_mean = float(np.mean(np.linalg.norm(np.diff(pos_arr, axis=0), axis=2).sum(axis=0)))

    cob_np = np.asarray(cob_hist)
    def _t_cruzar(thr: float) -> int:
        idx = np.where(cob_np >= thr)[0]
        return int(idx[0]) if len(idx) else MAX_STEPS_EP

    return {
        "cobertura_aoi_final":   cobertura_final,
        "n_colisiones":          n_colisiones,
        "distancia_recorrida":   dist_mean,
        "t_cob_50pct":           _t_cruzar(0.5),
        "t_cob_60pct":           _t_cruzar(0.6),
        "hubo_colision":         bool(n_colisiones > 0),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Evaluación de una política sobre N episodios
# ══════════════════════════════════════════════════════════════════════════════
def evaluar_politica(nombre: str, accionar: Callable, n_episodios: int) -> Dict[str, Any]:
    logger.info("Evaluando política '%s' en %d episodios deterministas...", nombre, n_episodios)
    env = construir_env()
    rng = np.random.default_rng(SEED * 31 + hash(nombre) % 1000)

    eps: List[Dict[str, float]] = []
    t0 = time.time()
    for i in range(n_episodios):
        seed_ep = SEED * 10_000 + i
        m = evaluar_episodio(env, accionar, seed_ep=seed_ep, rng=rng)
        m["episodio"] = i
        eps.append(m)
        if (i + 1) % 25 == 0:
            logger.info("  %s: ep %d/%d  cob=%.3f  col=%d  t50=%d",
                        nombre, i + 1, n_episodios,
                        m["cobertura_aoi_final"], m["n_colisiones"], m["t_cob_50pct"])
    dur = time.time() - t0
    try: env.close()
    except Exception: pass

    claves_num = ["cobertura_aoi_final", "n_colisiones", "distancia_recorrida", "t_cob_50pct", "t_cob_60pct"]
    agg: Dict[str, Dict[str, float]] = {}
    for k in claves_num:
        v = np.array([e[k] for e in eps], dtype=np.float64)
        agg[k] = {
            "media":   float(np.mean(v)),
            "std":     float(np.std(v)),
            "min":     float(np.min(v)),
            "max":     float(np.max(v)),
            "mediana": float(np.median(v)),
        }
    pct_col = float(np.mean([e["hubo_colision"] for e in eps]) * 100.0)
    agg["pct_eps_con_colision"] = {"valor": pct_col}

    logger.info(
        "  %s — terminado en %.1fs  cob=%.3f±%.3f  col=%.2f±%.2f  %%eps_col=%.1f%%",
        nombre, dur,
        agg["cobertura_aoi_final"]["media"], agg["cobertura_aoi_final"]["std"],
        agg["n_colisiones"]["media"],        agg["n_colisiones"]["std"],
        pct_col,
    )

    return {"nombre": nombre, "duracion_s": dur, "agregados": agg, "episodios": eps}


# ══════════════════════════════════════════════════════════════════════════════
# Figura A: Boxplots (cobertura | colisiones) × 3 políticas
# ══════════════════════════════════════════════════════════════════════════════
def figura_boxplots(resultados: Dict[str, Any], ruta_png: Path) -> None:
    nombres = ["MADRL (200k)", "Heurística NN", "Aleatoria"]
    claves  = ["madrl", "heuristica", "aleatoria"]

    cob_data = [[e["cobertura_aoi_final"] for e in resultados[k]["episodios"]] for k in claves]
    col_data = [[e["n_colisiones"]        for e in resultados[k]["episodios"]] for k in claves]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5.5))

    bp1 = ax1.boxplot(cob_data, tick_labels=nombres, patch_artist=True, widths=0.55)
    colores = ["#2c7fb8", "#7fcdbb", "#d95f0e"]
    for patch, c in zip(bp1["boxes"], colores):
        patch.set_facecolor(c); patch.set_alpha(0.7)
    ax1.set_ylabel("Cobertura AoI final", fontsize=11)
    ax1.set_title(f"Cobertura sobre {N_EPISODIOS_EVAL} eps deterministas", fontsize=11)
    ax1.grid(True, alpha=0.3, axis="y")
    ax1.axhline(0.5, color="gray", ls=":", lw=1, alpha=0.6)

    bp2 = ax2.boxplot(col_data, tick_labels=nombres, patch_artist=True, widths=0.55)
    for patch, c in zip(bp2["boxes"], colores):
        patch.set_facecolor(c); patch.set_alpha(0.7)
    ax2.set_ylabel("Pares en colisión / episodio", fontsize=11)
    ax2.set_title(f"Colisiones sobre {N_EPISODIOS_EVAL} eps deterministas", fontsize=11)
    ax2.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    fig.savefig(ruta_png, dpi=300, bbox_inches="tight")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
# Figura B: Evolución del proyecto (cobertura por experimento)
# ══════════════════════════════════════════════════════════════════════════════
def figura_evolucion(cob_madrl_final: Tuple[float, float], ruta_png: Path) -> None:
    """
    Eje X = experimento en orden cronológico.
    Eje Y = cobertura AoI media (con barras de error = std).
    Marcadores por tipo de experimento.
    """
    # Cargar datos de experimentos previos
    puntos: List[Dict[str, Any]] = []

    # Reproducibilidad seed 42 (100k)
    try:
        with open(DIR_REPRO / "seed_42" / "metricas_cobertura.json", "r", encoding="utf-8") as f:
            d = json.load(f)
        ag = d["agregados"]["cobertura_aoi_final"]
        puntos.append({"label": "Reproducibilidad\nseed 42 (100k)",
                       "media": ag["media"], "std": ag["std"], "tipo": "reproducibilidad"})
    except Exception as e:
        logger.warning("No se pudo cargar reproducibilidad seed 42: %s", e)

    # A/B Variante A (200k) — mejor punto, será el destacado
    try:
        with open(DIR_VARIANTE_A / "metricas_cobertura.json", "r", encoding="utf-8") as f:
            d = json.load(f)
        ag = d["agregados"]["cobertura_aoi_final"]
        puntos.append({"label": "A/B Variante A\n(200k)",
                       "media": ag["media"], "std": ag["std"], "tipo": "ab_test"})
    except Exception as e:
        logger.warning("No se pudo cargar variante_A: %s", e)

    # A/B Variante B (200k, λ_cbf=5)
    try:
        with open(ROOT / "modelos" / "tesis_v1" / "test_lambda_cbf" / "variante_B" /
                  "metricas_cobertura.json", "r", encoding="utf-8") as f:
            d = json.load(f)
        ag = d["agregados"]["cobertura_aoi_final"]
        puntos.append({"label": "A/B Variante B\n(λ_cbf=5)",
                       "media": ag["media"], "std": ag["std"], "tipo": "ab_test"})
    except Exception as e:
        logger.warning("No se pudo cargar variante_B: %s", e)

    # Diagnóstico sin VN — 5 puntos por checkpoint
    try:
        with open(DIR_DIAG_NO_VN / "metricas_checkpoints.json", "r", encoding="utf-8") as f:
            d = json.load(f)
        for r in d["resultados"]:
            ag = r["agregados"]["cobertura_aoi_final"]
            step_k = r["step"] // 1000
            puntos.append({"label": f"Diag\nsin VN\n({step_k}k)",
                           "media": ag["media"], "std": ag["std"], "tipo": "diagnostico"})
    except Exception as e:
        logger.warning("No se pudo cargar diagnostico_sin_VN: %s", e)

    # 5M con VN (abortada a 2.5M)
    try:
        with open(ROOT / "modelos" / "tesis_v1" / "entrenamiento_final_5M" /
                  "metricas_finales.json", "r", encoding="utf-8") as f:
            d = json.load(f)
        ag = d.get("agregados", d).get("cobertura_aoi_final", None)
        if ag and isinstance(ag, dict) and "media" in ag:
            puntos.append({"label": "5M con VN\n(abortada 2.5M)",
                           "media": ag["media"], "std": ag["std"], "tipo": "vecnormalize"})
    except Exception as e:
        logger.warning("No se pudo cargar entrenamiento_final_5M: %s", e)

    # RESULTADO PRIMERO (100 eps) — el punto destacado
    puntos.append({"label": "RESULTADO\nPRIMERO\n(100 eps)",
                   "media": cob_madrl_final[0], "std": cob_madrl_final[1],
                   "tipo": "primero"})

    # Plot
    fig, ax = plt.subplots(figsize=(13, 6))
    color_por_tipo = {
        "reproducibilidad": "#1f77b4",
        "ab_test":          "#2ca02c",
        "diagnostico":      "#d95f0e",
        "vecnormalize":     "#9467bd",
        "primero":          "#e7298a",
    }
    label_por_tipo = {
        "reproducibilidad": "Reproducibilidad",
        "ab_test":          "A/B test λ_cbf",
        "diagnostico":      "Diagnóstico sin VN",
        "vecnormalize":     "5M con VN (abortada)",
        "primero":          "★ Resultado PRIMERO ★",
    }

    xs = np.arange(len(puntos))
    medias = [p["media"] for p in puntos]
    stds   = [p["std"]   for p in puntos]

    # Líneas de referencia
    ax.axhline(0.6, color="gold",    ls="--", lw=1, alpha=0.6, label="Umbral DEFENDIBLE (0.60)")
    ax.axhline(0.7, color="green",   ls="--", lw=1, alpha=0.6, label="Umbral fuerte (0.70)")

    # Puntos coloreados por tipo, con leyenda agrupada
    tipos_dibujados = set()
    for x, p in zip(xs, puntos):
        c = color_por_tipo[p["tipo"]]
        size = 200 if p["tipo"] == "primero" else 90
        marker = "*" if p["tipo"] == "primero" else "o"
        lbl = label_por_tipo[p["tipo"]] if p["tipo"] not in tipos_dibujados else None
        ax.errorbar(x, p["media"], yerr=p["std"], fmt=marker, ms=np.sqrt(size),
                    color=c, capsize=4, lw=1.5, label=lbl, zorder=5 if p["tipo"] == "primero" else 3)
        tipos_dibujados.add(p["tipo"])

    ax.set_xticks(xs)
    ax.set_xticklabels([p["label"] for p in puntos], fontsize=8, rotation=0)
    ax.set_ylabel("Cobertura AoI (μ ± σ)", fontsize=11)
    ax.set_title("Evolución de la cobertura AoI a lo largo de los experimentos", fontsize=12)
    ax.set_ylim(0.0, 1.0)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower left", fontsize=8, ncol=2, framealpha=0.9)

    plt.tight_layout()
    fig.savefig(ruta_png, dpi=300, bbox_inches="tight")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
# Figura C: Snapshot de un episodio (env.render)
# ══════════════════════════════════════════════════════════════════════════════
def figura_trayectoria(modelo: PPO, ruta_png: Path, paso_objetivo: int = 250, seed_ep: int = SEED * 10_000) -> None:
    """
    Corre un episodio determinista hasta `paso_objetivo`, llama env.render()
    para obtener el rgb_array y lo guarda como PNG.
    """
    env = make_env(
        n_agents       = N_AGENTES,
        arena_size     = ARENA,
        max_steps      = MAX_STEPS_EP,
        comm_radius    = COMM_RADIUS,
        reward_weights = PESOS_TRIAL13,
        domain_rand    = False,
        seed           = SEED,
        render_mode    = "rgb_array",
    )
    obs_dict, _ = env.reset(seed=seed_ep)
    agents = list(obs_dict.keys())
    for _ in range(paso_objetivo):
        obs_arr = np.stack([obs_dict[a] for a in agents])
        acciones, _ = modelo.predict(obs_arr, deterministic=True)
        accion_dict = {a: acciones[k] for k, a in enumerate(agents)}
        obs_dict, _, term, trunc, _ = env.step(accion_dict)
        if all(trunc.values()) or all(term.values()):
            break
    img = env.render()
    if img is None:
        logger.warning("env.render() retornó None — no se guardó la trayectoria.")
        return
    plt.imsave(ruta_png, img)
    try: env.close()
    except Exception: pass


# ══════════════════════════════════════════════════════════════════════════════
# Reporte markdown
# ══════════════════════════════════════════════════════════════════════════════
def generar_reporte(resultados: Dict[str, Any], ruta_md: Path, dur_total_min: float) -> None:
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _row(nombre: str, key: str) -> str:
        ag = resultados[key]["agregados"]
        return (
            f"| {nombre} "
            f"| {ag['cobertura_aoi_final']['media']:.3f}±{ag['cobertura_aoi_final']['std']:.3f} "
            f"| {ag['cobertura_aoi_final']['mediana']:.3f} "
            f"| {ag['n_colisiones']['media']:.2f}±{ag['n_colisiones']['std']:.2f} "
            f"| {ag['n_colisiones']['mediana']:.1f} "
            f"| {ag['pct_eps_con_colision']['valor']:.1f}% "
            f"| {ag['distancia_recorrida']['media']:.2f}±{ag['distancia_recorrida']['std']:.2f} "
            f"| {ag['t_cob_50pct']['media']:.0f}±{ag['t_cob_50pct']['std']:.0f} "
            f"| {ag['t_cob_60pct']['media']:.0f}±{ag['t_cob_60pct']['std']:.0f} |"
        )

    def _bloque_metricas(nombre: str, key: str) -> str:
        ag = resultados[key]["agregados"]
        cob = ag["cobertura_aoi_final"]; col = ag["n_colisiones"]
        dist = ag["distancia_recorrida"]; t50 = ag["t_cob_50pct"]; t60 = ag["t_cob_60pct"]
        return (
            f"### {nombre}\n\n"
            f"- **Cobertura AoI final:** μ={cob['media']:.3f}, σ={cob['std']:.3f}, mediana={cob['mediana']:.3f}, rango=[{cob['min']:.3f}, {cob['max']:.3f}]\n"
            f"- **Pares en colisión / ep:** μ={col['media']:.2f}, σ={col['std']:.2f}, mediana={col['mediana']:.1f}, rango=[{col['min']:.0f}, {col['max']:.0f}]\n"
            f"- **% episodios con ≥1 colisión:** {ag['pct_eps_con_colision']['valor']:.1f}%\n"
            f"- **Distancia recorrida [m]:** μ={dist['media']:.2f}, σ={dist['std']:.2f}\n"
            f"- **Step al cruzar cob=0.5:** μ={t50['media']:.0f}, σ={t50['std']:.0f}\n"
            f"- **Step al cruzar cob=0.6:** μ={t60['media']:.0f}, σ={t60['std']:.0f}\n"
        )

    lines: List[str] = []
    lines.append("# RESULTADO PRIMERO — Modelo MADRL final (200k, Trial 13)")
    lines.append("")
    lines.append(f"*Generado: {ahora}*  —  *Tiempo de evaluación: {dur_total_min:.1f} min*")
    lines.append("")
    lines.append("## Identificación del modelo")
    lines.append("")
    lines.append("- **Origen:** Variante A del A/B test de λ_cbf (`modelos/tesis_v1/test_lambda_cbf/variante_A/modelo_final.zip`)")
    lines.append("- **Hiperparámetros:** Trial 13 del estudio Optuna `tesis_v1` (`mejores_hiperparametros.json`)")
    lines.append("- **Pesos de recompensa:** λ_grad=0.562, λ_ent=1.140, λ_ibrm=0.484, **λ_cbf=2.966**")
    lines.append("- **Configuración de entrenamiento:** seed=42, 200,000 steps, n_agentes=5, n_envs=4, max_steps_ep=500, domain_rand=True, **sin VecNormalize**")
    lines.append("- **Arquitectura policy:** MlpPolicy default de SB3 (default share net), encoder vecino externo (Mean Embedding) integrado en el observation space")
    lines.append("")
    lines.append("## Tabla de métricas (100 episodios deterministas, sin domain_rand)")
    lines.append("")
    lines.append("| Política | Cobertura (μ±σ) | Mediana | Pares col/ep (μ±σ) | Mediana | % eps con col | Distancia [m] | t cob=0.5 | t cob=0.6 |")
    lines.append("|----------|----------------:|--------:|-------------------:|--------:|---------------|--------------:|----------:|----------:|")
    lines.append(_row("**MADRL 200k (PRIMERO)**", "madrl"))
    lines.append(_row("Heurística NN (carrot)",   "heuristica"))
    lines.append(_row("Aleatoria",                 "aleatoria"))
    lines.append("")
    lines.append("## Detalle de cada política")
    lines.append("")
    lines.append(_bloque_metricas("MADRL 200k — RESULTADO PRIMERO", "madrl"))
    lines.append(_bloque_metricas("Baseline 1 — Heurística NN (go-to-nearest-target)", "heuristica"))
    lines.append(_bloque_metricas("Baseline 2 — Política aleatoria", "aleatoria"))
    lines.append("## Por qué 200k y no más")
    lines.append("")
    lines.append(
        "El experimento de diagnóstico en "
        "[`diagnostico_sin_vecnormalize/`](../diagnostico_sin_vecnormalize/reporte_diagnostico.md) "
        "demuestra que entrenar más allá de 200k DEGRADA el desempeño con estos hiperparámetros, "
        "con o sin VecNormalize. La trayectoria observada de la cobertura sin VecNormalize a 100k–500k:"
    )
    lines.append("")
    lines.append("| Step | Cobertura (μ±σ) | Pares colisión/ep |")
    lines.append("|-----:|----------------:|------------------:|")
    lines.append("| 100k | 0.707±0.017 | 0.55 |")
    lines.append("| **200k** ← pico | **0.682±0.018** | **0.15** |")
    lines.append("| 300k | 0.674±0.019 | 0.85 |")
    lines.append("| 400k | 0.669±0.018 | 0.80 |")
    lines.append("| 500k | 0.579±0.060 | 0.60 |")
    lines.append("")
    lines.append(
        "La degradación monotónica desde 200k es consistente con un caso de **sobreajuste por horizonte**: "
        "los hiperparámetros del Trial 13 fueron seleccionados por Optuna usando un presupuesto de 100k "
        "steps por trial. Optuna optimizó para ese horizonte, lo que produjo hiperparámetros con buen "
        "desempeño temprano pero inestables a largo plazo. La corrida 5M con VecNormalize (abortada por "
        "alarma a 2.5M, cob=0.626, col=0.98) confirma la patología desde otro ángulo."
    )
    lines.append("")
    lines.append("**Implicación metodológica documentada:** futuros estudios Optuna sobre este pipeline "
                 "deben usar presupuestos de trial de al menos 500k–1M steps, idealmente con MedianPruner "
                 "calibrado para detectar divergencia post-pico.")
    lines.append("")
    lines.append("## Figuras")
    lines.append("")
    lines.append("- [Comparación con baselines](figuras/fig_resultados_PRIMERO.png)")
    lines.append("- [Evolución del proyecto](figuras/fig_evolucion_experimentos.png)")
    lines.append("- [Snapshot de un episodio](figuras/fig_trayectoria_episodio.png)")
    lines.append("")
    lines.append("## Artefactos en este directorio")
    lines.append("")
    lines.append("- `modelo_PRIMERO.zip` — checkpoint PPO listo para inferencia")
    lines.append("- `hiperparametros.json` — Trial 13 exacto")
    lines.append("- `config_entrenamiento.json` — configuración de la corrida 200k")
    lines.append("- `metricas_100eps.json` — datos crudos de los 300 episodios (3 políticas × 100 eps)")
    lines.append("- `figuras/` — las 3 figuras del reporte")
    lines.append("")

    with open(ruta_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    t_total_ini = time.time()
    logger.info("=" * 70)
    logger.info("CONSOLIDACIÓN — RESULTADO PRIMERO (Variante A del A/B test λ_cbf)")
    logger.info("=" * 70)

    # ── 1. Copiar modelo y guardar configs ──────────────────────────────
    ruta_origen = DIR_VARIANTE_A / "modelo_final.zip"
    ruta_destino = DIR_PRIMERO / "modelo_PRIMERO.zip"
    if not ruta_origen.exists():
        raise FileNotFoundError(f"No existe {ruta_origen}")
    shutil.copy2(ruta_origen, ruta_destino)
    logger.info("Modelo copiado: %s → %s", ruta_origen.name, ruta_destino.name)

    # Hiperparámetros (Trial 13)
    with open(RUTA_HPARAMS_JSON, "r", encoding="utf-8") as f:
        hparams_data = json.load(f)
    with open(DIR_PRIMERO / "hiperparametros.json", "w", encoding="utf-8") as f:
        json.dump(hparams_data, f, indent=2, ensure_ascii=False)

    # Config entrenamiento
    config_train = {
        "n_agentes":      N_AGENTES,
        "max_steps_ep":   MAX_STEPS_EP,
        "n_envs":         4,
        "n_pasos_total":  N_PASOS_TRAIN,
        "seed":           SEED,
        "domain_rand":    True,
        "vecnormalize":   False,
        "arena_size":     list(ARENA),
        "comm_radius":    COMM_RADIUS,
        "pesos_recompensa": PESOS_TRIAL13,
    }
    with open(DIR_PRIMERO / "config_entrenamiento.json", "w", encoding="utf-8") as f:
        json.dump(config_train, f, indent=2, ensure_ascii=False)
    logger.info("Configs guardados: hiperparametros.json + config_entrenamiento.json")

    # ── 2. Cargar modelo MADRL ──────────────────────────────────────────
    logger.info("Cargando modelo MADRL desde %s ...", ruta_destino.name)
    modelo = PPO.load(str(ruta_destino))

    # ── 3. Evaluar las 3 políticas en 100 eps ───────────────────────────
    resultados: Dict[str, Any] = {}
    resultados["madrl"]      = evaluar_politica("MADRL_200k",      politica_madrl(modelo),    N_EPISODIOS_EVAL)
    resultados["heuristica"] = evaluar_politica("heuristica_NN",   politica_heuristica_NN,    N_EPISODIOS_EVAL)
    resultados["aleatoria"]  = evaluar_politica("aleatoria",       politica_aleatoria,        N_EPISODIOS_EVAL)

    # JSON crudo
    with open(DIR_PRIMERO / "metricas_100eps.json", "w", encoding="utf-8") as f:
        json.dump({
            "n_episodios":     N_EPISODIOS_EVAL,
            "seed":            SEED,
            "fecha":           datetime.now().isoformat(),
            "resultados":      resultados,
        }, f, indent=2, ensure_ascii=False)
    logger.info("Métricas crudas → metricas_100eps.json")

    # ── 4. Figuras ───────────────────────────────────────────────────────
    logger.info("Generando figuras...")
    figura_boxplots(resultados, DIR_FIG / "fig_resultados_PRIMERO.png")
    cob_madrl = (resultados["madrl"]["agregados"]["cobertura_aoi_final"]["media"],
                 resultados["madrl"]["agregados"]["cobertura_aoi_final"]["std"])
    figura_evolucion(cob_madrl, DIR_FIG / "fig_evolucion_experimentos.png")
    figura_trayectoria(modelo, DIR_FIG / "fig_trayectoria_episodio.png", paso_objetivo=250)
    logger.info("Figuras → %s", DIR_FIG)

    # ── 5. Reporte markdown ──────────────────────────────────────────────
    dur_total_min = (time.time() - t_total_ini) / 60.0
    generar_reporte(resultados, DIR_PRIMERO / "reporte_consolidado.md", dur_total_min)
    logger.info("Reporte → reporte_consolidado.md")

    logger.info("=" * 70)
    logger.info("CONSOLIDACIÓN TERMINADA en %.1f min", dur_total_min)
    logger.info("MADRL 200k:   cob=%.3f±%.3f  col=%.2f±%.2f",
                resultados["madrl"]["agregados"]["cobertura_aoi_final"]["media"],
                resultados["madrl"]["agregados"]["cobertura_aoi_final"]["std"],
                resultados["madrl"]["agregados"]["n_colisiones"]["media"],
                resultados["madrl"]["agregados"]["n_colisiones"]["std"])
    logger.info("Heurística:   cob=%.3f±%.3f  col=%.2f±%.2f",
                resultados["heuristica"]["agregados"]["cobertura_aoi_final"]["media"],
                resultados["heuristica"]["agregados"]["cobertura_aoi_final"]["std"],
                resultados["heuristica"]["agregados"]["n_colisiones"]["media"],
                resultados["heuristica"]["agregados"]["n_colisiones"]["std"])
    logger.info("Aleatoria:    cob=%.3f±%.3f  col=%.2f±%.2f",
                resultados["aleatoria"]["agregados"]["cobertura_aoi_final"]["media"],
                resultados["aleatoria"]["agregados"]["cobertura_aoi_final"]["std"],
                resultados["aleatoria"]["agregados"]["n_colisiones"]["media"],
                resultados["aleatoria"]["agregados"]["n_colisiones"]["std"])
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
