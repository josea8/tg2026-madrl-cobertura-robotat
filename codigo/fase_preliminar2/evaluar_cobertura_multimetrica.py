"""
evaluar_cobertura_multimetrica.py
=================================
Evaluación multi-métrica de los 3 modelos del test de reproducibilidad.

Hipótesis a validar:
    Las 3 seeds del Trial 13 mostraron cobertura AoI consistente (0.45–0.55)
    pese a rewards dispares (-10 a -59). Esto sugiere que están aprendiendo
    cobertura exploratoria similar, pero algunas colisionan más. La recompensa
    penaliza las colisiones (λ_cbf=2.97), por lo que el spread en rewards
    podría explicarse por diferencias en el comportamiento colisional más que
    por diferencias en la cobertura real.

Métricas por episodio:
    - cobertura_aoi_final         : 1 − mean(grid_aoi) al final del episodio
    - n_colisiones                : pares únicos (i,j) que tuvieron d_ij < D_SAFE
                                    en algún step del episodio (máx C(5,2)=10)
    - distancia_total_recorrida   : desplazamiento acumulado promedio por agente [m]
    - tiempo_primera_cobertura_50pct : step en que la cobertura cruza 0.5
                                       (max_steps si nunca cruza)

Salidas:
    modelos/tesis_v1/verificacion_seeds/
        comparacion_seeds_multimetrica.md   — tabla
        comparacion_seeds_multimetrica.png  — 4 subplots (boxplot por métrica)
        seed_{SEED}/metricas_cobertura.json — datos crudos por episodio
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from stable_baselines3 import PPO

from swarm_env_skeleton import D_SAFE, make_env


# ──────────────────────────────────────────────────────────────────────────────
# Configuración
# ──────────────────────────────────────────────────────────────────────────────
DIR_BASE:    Path      = Path("modelos/tesis_v1/verificacion_seeds")
SEEDS:       List[int] = [42, 123, 777]
N_EPISODIOS: int       = 30
MAX_STEPS:   int       = 500
N_AGENTES:   int       = 5
ARENA:       tuple     = (3.0, 3.0)
COMM_RADIUS: float     = 1.0

# Pesos de recompensa del Trial 13 (necesarios para instanciar el env)
PESOS_REWARD: Dict[str, float] = {
    "lambda_gradient": 0.5622468083379316,
    "lambda_entropy":  1.1403296484190344,
    "lambda_ibrm":     0.48380314172632155,
    "lambda_cbf":      2.9655314099141474,
}

# Criterio de decisión
UMBRAL_COBERTURA_REPORTABLE:  float = 0.6    # > 0.6 para REPORTABLE
UMBRAL_STD_COBERTURA_CONSIST: float = 0.10   # std entre seeds < 0.10

logger = logging.getLogger("eval_cobertura")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(_h)


# ──────────────────────────────────────────────────────────────────────────────
# Evaluación de una seed
# ──────────────────────────────────────────────────────────────────────────────
def evaluar_episodio(
    modelo:   PPO,
    env,
    seed_ep:  int,
) -> Dict[str, float]:
    """
    Corre UN episodio determinista y retorna las 4 métricas.

    Arquitectura:
        Las acciones del modelo entrenado con VecEnv se aplican a la env
        PettingZoo cruda extrayendo (obs, acción) por agente via stacking.
        Esto permite acceso directo al estado interno para métricas finas.
    """
    obs_dict, _ = env.reset(seed=seed_ep)
    agents = list(obs_dict.keys())
    n_agents = len(agents)

    # ── Estructuras de tracking ──────────────────────────────────────────
    cobertura_hist:   List[float]    = []
    posiciones_hist:  List[np.ndarray] = []
    pares_colision:   set             = set()  # conjunto de tuplas (i, j)

    # Posición inicial (antes del primer step)
    pos_inicial = np.array([env._estados[a][:2] for a in agents])
    posiciones_hist.append(pos_inicial.copy())

    # ── Bucle del episodio ───────────────────────────────────────────────
    done = False
    while not done:
        obs_array       = np.stack([obs_dict[a] for a in agents])
        acciones, _     = modelo.predict(obs_array, deterministic=True)
        accion_dict     = {a: acciones[i] for i, a in enumerate(agents)}
        obs_dict, _, term, trunc, _ = env.step(accion_dict)

        # Cobertura global post-step
        cobertura_hist.append(
            1.0 - float(np.mean(env._field._grid_aoi))
        )

        # Posiciones post-step
        pos_curr = np.array([env._estados[a][:2] for a in agents])
        posiciones_hist.append(pos_curr.copy())

        # Pares en colisión (simétrico, solo i<j)
        for i in range(n_agents):
            for j in range(i + 1, n_agents):
                if np.linalg.norm(pos_curr[i] - pos_curr[j]) < D_SAFE:
                    pares_colision.add((i, j))

        done = all(trunc.values()) or all(term.values())

    # ── Cálculo de métricas derivadas ────────────────────────────────────
    cobertura_final = cobertura_hist[-1] if cobertura_hist else 0.0
    n_colisiones    = len(pares_colision)

    pos_arr = np.asarray(posiciones_hist)   # (T+1, n_agents, 2)
    deltas  = np.linalg.norm(np.diff(pos_arr, axis=0), axis=2)  # (T, n_agents)
    dist_total_mean = float(np.mean(deltas.sum(axis=0)))

    cob_np   = np.asarray(cobertura_hist)
    idx_cross = np.where(cob_np >= 0.5)[0]
    t_50pct   = int(idx_cross[0]) if len(idx_cross) > 0 else MAX_STEPS

    return {
        "cobertura_aoi_final":           cobertura_final,
        "n_colisiones":                  n_colisiones,
        "distancia_total_recorrida":     dist_total_mean,
        "tiempo_primera_cobertura_50pct": t_50pct,
    }


def evaluar_seed(seed: int, n_episodios: int) -> Dict[str, Any]:
    """Carga el modelo de una seed y corre n_episodios episodios deterministas."""
    dir_seed     = DIR_BASE / f"seed_{seed}"
    ruta_modelo  = dir_seed / "modelo_final.zip"
    if not ruta_modelo.exists():
        raise FileNotFoundError(f"No existe: {ruta_modelo}")

    logger.info("━" * 60)
    logger.info("SEED %d — cargando %s", seed, ruta_modelo)
    modelo = PPO.load(str(ruta_modelo))

    env = make_env(
        n_agents       = N_AGENTES,
        arena_size     = ARENA,
        max_steps      = MAX_STEPS,
        comm_radius    = COMM_RADIUS,
        reward_weights = PESOS_REWARD,
        domain_rand    = False,   # eval determinista
        seed           = seed,
    )

    resultados_eps: List[Dict[str, float]] = []
    t_ini = time.time()
    for i in range(n_episodios):
        seed_ep = seed * 10_000 + i   # seed reproducible por episodio
        metrica_ep = evaluar_episodio(modelo, env, seed_ep=seed_ep)
        metrica_ep["episodio"] = i
        resultados_eps.append(metrica_ep)

        if (i + 1) % 10 == 0:
            logger.info(
                "  seed %d — ep %d/%d   cob=%.3f  col=%d  dist=%.2f  t50=%d",
                seed, i + 1, n_episodios,
                metrica_ep["cobertura_aoi_final"],
                metrica_ep["n_colisiones"],
                metrica_ep["distancia_total_recorrida"],
                metrica_ep["tiempo_primera_cobertura_50pct"],
            )
    dur = time.time() - t_ini

    # ── Agregados por seed ───────────────────────────────────────────────
    claves = [
        "cobertura_aoi_final",
        "n_colisiones",
        "distancia_total_recorrida",
        "tiempo_primera_cobertura_50pct",
    ]
    agregados: Dict[str, Dict[str, float]] = {}
    for k in claves:
        vals = np.array([ep[k] for ep in resultados_eps], dtype=np.float64)
        agregados[k] = {
            "media": float(np.mean(vals)),
            "std":   float(np.std(vals)),
            "min":   float(np.min(vals)),
            "max":   float(np.max(vals)),
        }

    # ── Persistir datos crudos ───────────────────────────────────────────
    ruta_json = dir_seed / "metricas_cobertura.json"
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(
            {
                "seed":         seed,
                "n_episodios":  n_episodios,
                "duracion_s":   dur,
                "agregados":    agregados,
                "episodios":    resultados_eps,
            },
            f, indent=2, ensure_ascii=False,
        )
    logger.info(
        "SEED %d terminada en %.1fs — cob=%.3f±%.3f  col=%.1f±%.1f",
        seed, dur,
        agregados["cobertura_aoi_final"]["media"],
        agregados["cobertura_aoi_final"]["std"],
        agregados["n_colisiones"]["media"],
        agregados["n_colisiones"]["std"],
    )

    try:
        env.close()
    except Exception:
        pass

    return {
        "seed":      seed,
        "agregados": agregados,
        "episodios": resultados_eps,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Figura comparativa (4 boxplots)
# ──────────────────────────────────────────────────────────────────────────────
def generar_figura_boxplots(
    resultados_por_seed: List[Dict[str, Any]],
    ruta_png:            Path,
) -> None:
    """Genera 4 subplots con boxplots lado-a-lado por seed."""
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    axes = axes.flatten()

    metricas = [
        ("cobertura_aoi_final",            "Cobertura AoI final",               ""),
        ("n_colisiones",                   "Pares únicos en colisión",          "conteo"),
        ("distancia_total_recorrida",      "Distancia total recorrida (prom. agente)", "m"),
        ("tiempo_primera_cobertura_50pct", "Step al cruzar cobertura 0.5",      "steps"),
    ]

    colores = ["tab:blue", "tab:orange", "tab:green"]

    for ax, (clave, titulo, unidad) in zip(axes, metricas):
        datos = []
        labels = []
        for r in resultados_por_seed:
            vals = [ep[clave] for ep in r["episodios"]]
            datos.append(vals)
            labels.append(f"seed={r['seed']}")

        bp = ax.boxplot(
            datos, labels=labels, patch_artist=True,
            widths=0.55, showmeans=True,
            meanprops={"marker": "D", "markerfacecolor": "white",
                       "markeredgecolor": "black", "markersize": 7},
        )
        for patch, color in zip(bp["boxes"], colores):
            patch.set_facecolor(color)
            patch.set_alpha(0.5)

        # Overlay scatter de puntos individuales
        for i, vals in enumerate(datos):
            xs = np.random.normal(i + 1, 0.04, size=len(vals))
            ax.scatter(xs, vals, alpha=0.45, s=14, color=colores[i], edgecolors="k",
                       linewidths=0.4, zorder=3)

        ax.set_title(titulo, fontsize=12, pad=8)
        if unidad:
            ax.set_ylabel(unidad, fontsize=10)
        ax.grid(alpha=0.3, axis="y")

        # Línea de referencia específica
        if clave == "cobertura_aoi_final":
            ax.axhline(UMBRAL_COBERTURA_REPORTABLE, color="red", ls="--", lw=1.2, alpha=0.6)
            ax.text(0.02, UMBRAL_COBERTURA_REPORTABLE + 0.005,
                    f"umbral reportable = {UMBRAL_COBERTURA_REPORTABLE}",
                    color="red", fontsize=8, transform=ax.get_yaxis_transform())

    fig.suptitle(
        "Comparación multi-métrica — 3 seeds del Trial 13 (30 episodios c/u)",
        fontsize=14, y=1.00,
    )
    plt.tight_layout()
    fig.savefig(ruta_png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logger.info("Figura guardada: %s", ruta_png)


# ──────────────────────────────────────────────────────────────────────────────
# Criterio de decisión
# ──────────────────────────────────────────────────────────────────────────────
def aplicar_criterio(resultados_por_seed: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Criterios (según spec del usuario):

      1. REPORTABLE: todas las seeds tienen cobertura_aoi_final > 0.6
                     AND std de las medias entre seeds < 0.1
         → proceder a 5M con seed=42.

      2. CONSISTENTE PERO BAJA: std entre seeds < 0.1 pero alguna media < 0.6
         → ajustar pesos manualmente (↑λ_ent, ↓λ_cbf), relanzar 100k.

      3. INCONSISTENTE: std entre seeds ≥ 0.1
         → tesis_v2 con espacio Optuna reducido.
    """
    medias = np.array([r["agregados"]["cobertura_aoi_final"]["media"]
                       for r in resultados_por_seed])
    mu_medias  = float(np.mean(medias))
    std_medias = float(np.std(medias))
    todas_sup  = bool(np.all(medias > UMBRAL_COBERTURA_REPORTABLE))
    consistente = bool(std_medias < UMBRAL_STD_COBERTURA_CONSIST)

    if todas_sup and consistente:
        categoria = "REPORTABLE"
        mejor = max(resultados_por_seed,
                    key=lambda r: r["agregados"]["cobertura_aoi_final"]["media"])
        rec = (
            f"Cobertura consistente y suficiente entre seeds. **Proceder a "
            f"corrida 5M con seed={mejor['seed']}** (mejor cobertura media: "
            f"{mejor['agregados']['cobertura_aoi_final']['media']:.3f}).\n\n"
            "Comando:\n"
            "```powershell\n"
            "python train.py --modo entrenar --nombre_estudio tesis_v1 "
            "--n_pasos 5000000 --n_agentes 5 --max_steps_ep 500 --n_envs 4 "
            f"--seed {mejor['seed']}\n"
            "```"
        )
    elif consistente and not todas_sup:
        categoria = "CONSISTENTE_PERO_BAJA"
        rec = (
            f"Cobertura consistente entre seeds (std={std_medias:.3f}) pero "
            f"insuficiente (media={mu_medias:.3f} < {UMBRAL_COBERTURA_REPORTABLE}). "
            "**Ajustar pesos manualmente antes de Optuna:**\n"
            "  - Subir `λ_entropy` de 1.140 → 1.80 (más presión por explorar AoI).\n"
            "  - Bajar `λ_cbf` de 2.966 → 1.50 (menos miedo a proximidad).\n"
            "  - Mantener `λ_gradient` y `λ_ibrm`.\n"
            "  - Relanzar `verificar_reproducibilidad_trial13.py` con estos "
            "pesos modificados y re-evaluar este script."
        )
    else:
        categoria = "INCONSISTENTE"
        rec = (
            f"Cobertura inconsistente entre seeds (std={std_medias:.3f} "
            f"≥ {UMBRAL_STD_COBERTURA_CONSIST}). El problema no es solo el "
            "trade-off exploración/colisión, es que la política misma no "
            "converge a un comportamiento estable. **Proceder con `tesis_v2`:**\n"
            "  1. Restringir `λ_cbf ∈ [1.0, 5.0]`.\n"
            "  2. Restringir `n_steps_exp ∈ [7, 9]`.\n"
            "  3. Evaluar cada trial con 2 seeds (promediar/tomar mediana).\n"
            "  4. 20 trials × 100k steps."
        )

    return {
        "medias_por_seed":   medias.tolist(),
        "mu_medias":         mu_medias,
        "std_medias":        std_medias,
        "todas_sup_umbral":  todas_sup,
        "consistente":       consistente,
        "categoria":         categoria,
        "recomendacion":     rec,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Reporte Markdown
# ──────────────────────────────────────────────────────────────────────────────
def generar_reporte(
    resultados_por_seed: List[Dict[str, Any]],
    diagnostico:         Dict[str, Any],
    ruta_md:             Path,
) -> None:
    """Genera la tabla comparativa markdown."""
    lineas: List[str] = [
        "# Comparación multi-métrica — 3 seeds del Trial 13",
        "",
        f"*Generado: {time.strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
        "## Hipótesis",
        "",
        "Las 3 seeds tuvieron rewards dispares (-10 a -59) pero cobertura AoI "
        "similar (0.45–0.55). ¿Están aprendiendo cobertura comparable y "
        "difieren solo en tasa de colisión? Esta evaluación mide cuatro ejes "
        "independientes sobre 30 episodios deterministas por seed.",
        "",
        "## Configuración",
        "",
        f"- **n_episodios por seed:** {N_EPISODIOS}",
        f"- **max_steps por episodio:** {MAX_STEPS}",
        f"- **domain_rand:** False (eval determinista)",
        f"- **Modelos evaluados:** `modelos/tesis_v1/verificacion_seeds/seed_{{42,123,777}}/modelo_final.zip`",
        "",
        "## Tabla comparativa",
        "",
        "| Métrica | seed=42 (μ±σ) | seed=123 (μ±σ) | seed=777 (μ±σ) |",
        "|---------|---------------:|----------------:|----------------:|",
    ]

    claves_nombres = [
        ("cobertura_aoi_final",            "Cobertura AoI final",            "{:.3f}±{:.3f}"),
        ("n_colisiones",                   "Pares en colisión",              "{:.1f}±{:.1f}"),
        ("distancia_total_recorrida",      "Distancia recorrida [m]",        "{:.2f}±{:.2f}"),
        ("tiempo_primera_cobertura_50pct", "Step al cruzar cob. 0.5",        "{:.0f}±{:.0f}"),
    ]
    for clave, nombre, fmt in claves_nombres:
        fila = f"| {nombre} "
        for r in resultados_por_seed:
            ag = r["agregados"][clave]
            fila += f"| {fmt.format(ag['media'], ag['std'])} "
        fila += "|"
        lineas.append(fila)

    # Rango (min-max) también útil
    lineas += [
        "",
        "### Rango (min – max) por métrica y seed",
        "",
        "| Métrica | seed=42 | seed=123 | seed=777 |",
        "|---------|--------:|---------:|---------:|",
    ]
    for clave, nombre, _ in claves_nombres:
        fila = f"| {nombre} "
        for r in resultados_por_seed:
            ag = r["agregados"][clave]
            fila += f"| {ag['min']:.2f} – {ag['max']:.2f} "
        fila += "|"
        lineas.append(fila)

    # Criterio
    lineas += [
        "",
        "## Análisis entre seeds",
        "",
        f"**Medias de cobertura por seed:** {[f'{m:.3f}' for m in diagnostico['medias_por_seed']]}",
        f"- Media de las medias: **{diagnostico['mu_medias']:.3f}**",
        f"- Desv. std entre seeds: **{diagnostico['std_medias']:.3f}**",
        f"- ¿Todas > {UMBRAL_COBERTURA_REPORTABLE}? **{diagnostico['todas_sup_umbral']}**",
        f"- ¿Consistente (std < {UMBRAL_STD_COBERTURA_CONSIST})? **{diagnostico['consistente']}**",
        "",
        "## Criterio de decisión",
        "",
        "| Categoría | Condición | Acción |",
        "|-----------|-----------|--------|",
        f"| 🟢 REPORTABLE            | todas las medias > {UMBRAL_COBERTURA_REPORTABLE} AND std < {UMBRAL_STD_COBERTURA_CONSIST} | Proceder a 5M con mejor seed |",
        f"| 🟡 CONSISTENTE_PERO_BAJA | std < {UMBRAL_STD_COBERTURA_CONSIST} pero alguna media ≤ {UMBRAL_COBERTURA_REPORTABLE} | Ajuste manual de pesos + relanzar 100k |",
        f"| 🔴 INCONSISTENTE         | std ≥ {UMBRAL_STD_COBERTURA_CONSIST} | tesis_v2 con espacio reducido |",
        "",
        f"### Resultado: **{diagnostico['categoria']}**",
        "",
        diagnostico["recomendacion"],
        "",
        "## Figura",
        "",
        "![Comparación boxplots](comparacion_seeds_multimetrica.png)",
    ]

    ruta_md.write_text("\n".join(lineas), encoding="utf-8")
    logger.info("Reporte markdown: %s", ruta_md)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    logger.info("=" * 70)
    logger.info("EVALUACIÓN MULTI-MÉTRICA — 3 SEEDS DEL TRIAL 13")
    logger.info("=" * 70)

    resultados: List[Dict[str, Any]] = []
    for seed in SEEDS:
        try:
            r = evaluar_seed(seed, N_EPISODIOS)
            resultados.append(r)
        except Exception as exc:
            logger.exception("Seed %d falló: %s", seed, exc)

    if len(resultados) < 2:
        logger.error("Menos de 2 seeds evaluadas. Abortando.")
        sys.exit(1)

    # ── Figura ───────────────────────────────────────────────────────────
    ruta_png = DIR_BASE / "comparacion_seeds_multimetrica.png"
    generar_figura_boxplots(resultados, ruta_png)

    # ── Diagnóstico ──────────────────────────────────────────────────────
    diagnostico = aplicar_criterio(resultados)

    # ── Reporte ──────────────────────────────────────────────────────────
    ruta_md = DIR_BASE / "comparacion_seeds_multimetrica.md"
    generar_reporte(resultados, diagnostico, ruta_md)

    # ── Resumen consola ──────────────────────────────────────────────────
    logger.info("=" * 70)
    logger.info("RESULTADO FINAL")
    logger.info("=" * 70)
    for r in resultados:
        ag = r["agregados"]
        logger.info(
            "  seed=%d → cob_aoi=%.3f±%.3f  colisiones=%.1f±%.1f  "
            "dist=%.2f±%.2f  t50=%.0f±%.0f",
            r["seed"],
            ag["cobertura_aoi_final"]["media"],        ag["cobertura_aoi_final"]["std"],
            ag["n_colisiones"]["media"],               ag["n_colisiones"]["std"],
            ag["distancia_total_recorrida"]["media"],  ag["distancia_total_recorrida"]["std"],
            ag["tiempo_primera_cobertura_50pct"]["media"],
            ag["tiempo_primera_cobertura_50pct"]["std"],
        )
    logger.info(
        "  μ(medias)=%.3f  σ(medias)=%.3f  → %s",
        diagnostico["mu_medias"],
        diagnostico["std_medias"],
        diagnostico["categoria"],
    )
    logger.info("  Reporte: %s", ruta_md)


if __name__ == "__main__":
    main()
