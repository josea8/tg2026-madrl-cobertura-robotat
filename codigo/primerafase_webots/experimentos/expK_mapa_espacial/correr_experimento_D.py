"""
correr_experimento_D.py
=======================
EXPERIMENTO D — ¿La degradación por bordes bloqueantes es específica de la
política APRENDIDA, o afecta por igual a cualquier estrategia?

Contexto
--------
El Experimento C mostró que la política MADRL pierde 33.7% de cobertura
(IC95 [−0.2385, −0.2208], 100/100 episodios peor) cuando el borde deja de
reflejar y pasa a bloquear. Pero esa cifra sola no distingue dos hipótesis:

  H1) La política APRENDIÓ a explotar el rebote → la degradación es
      específica de MADRL y refleja sobreajuste a la dinámica de borde.
  H2) Bloquear el borde perjudica a CUALQUIER estrategia por igual → la
      degradación es una propiedad del entorno, no del aprendizaje.

Este experimento discrimina H1 vs H2 con un diseño factorial completo:
3 estrategias × 2 condiciones de borde × 100 semillas (600 episodios), todo
pareado por semilla. El estadístico decisivo es la DIFERENCIA DE DIFERENCIAS
(difference-in-differences):

    DiD = (MADRL_bloq − MADRL_refl) − (linea_base_bloq − linea_base_refl)

Si DiD ≈ 0, el borde afecta a todos igual (H2). Si DiD < 0 con IC95 que
excluye el cero, MADRL pierde significativamente MÁS que la línea base (H1).
El pareo por semilla en ambos términos cancela tanto la varianza entre
semillas como el efecto común del entorno.

Estrategias (implementación PORTADA del protocolo original)
-----------------------------------------------------------
  a) MADRL       : modelo_PRIMERO, predict(deterministic=True).
  b) heuristica_NN: "go to nearest target" — carrot chasing.
                   ω = clip(K_ω·wrap(θ_obj − θ), ±Ω_MAX); v = V_MAX·max(0,cos(err)).
                   K_ω = 4.0. NO usa RNG (es determinista).
  c) aleatoria   : v ~ U[−V_MAX, V_MAX], ω ~ U[−Ω_MAX, Ω_MAX].

NOTA SOBRE EL RNG DE LA POLÍTICA ALEATORIA
-------------------------------------------
El protocolo original sembraba el RNG con `SEED*31 + hash(nombre) % 1000`.
`hash()` de strings en Python está ALEATORIZADO POR PROCESO (PYTHONHASHSEED),
por lo que la semilla exacta de la corrida original es IRRECUPERABLE. Además,
aquel RNG era un stream continuo a lo largo de los 100 episodios: si se
corrieran las dos condiciones de borde en loops separados, la política
aleatoria recibiría secuencias de acciones DISTINTAS en cada condición y la
diferencia pareada mezclaría ruido de RNG con el efecto de borde.

Decisión: se siembra `default_rng(seed_ep)` al inicio de CADA episodio. La
implementación de la política es idéntica (misma distribución, mismos
límites); solo cambia el esquema de siembra, que era irreproducible de todos
modos. Así ambas condiciones reciben la MISMA secuencia de acciones y el
pareo es válido. Consecuencia: la validación de control de la aleatoria es
estadística (tolerancia 0.01), no bit-exacta. MADRL y NN sí son exactas.

Validación de control (obligatoria)
-----------------------------------
Bajo modo_borde="reflexion", las tres estrategias deben reproducir los
valores de RESULTADO_PRIMERO/metricas_100eps.json:
    MADRL      0.681291 ± 0.019996
    heuristica 0.254349 ± 0.046259
    aleatoria  0.140186 ± 0.011193
Si alguna se desvía más que la tolerancia, el script ABORTA.

Salidas
-------
  resultados/experimento_D_completo.csv   (600 filas)
  resultados/resumen_experimento_D.txt

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

_CARPETA_SCRIPT: Path = Path(__file__).resolve().parent
if str(_CARPETA_SCRIPT) not in sys.path:
    sys.path.insert(0, str(_CARPETA_SCRIPT))

from stable_baselines3 import PPO

from lib.concentration_dynamics import V_MAX, OMEGA_MAX
from lib.swarm_env_skeleton import D_SAFE, make_env


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

N_EPISODIOS:  int   = 100
SEED_BASE:    int   = 42
N_AGENTES:    int   = 5
MAX_STEPS_EP: int   = 500
ARENA:        tuple = (3.0, 3.0)
COMM_RADIUS:  float = 1.0
K_OMEGA_NN:   float = 4.0

PESOS_TRIAL13: Dict[str, float] = {
    "lambda_gradient": 0.5622468083379316,
    "lambda_entropy":  1.1403296484190344,
    "lambda_ibrm":     0.48380314172632155,
    "lambda_cbf":      2.9655314099141474,
}

ESTRATEGIAS: Tuple[str, ...] = ("madrl", "heuristica", "aleatoria")
CONDICIONES: Tuple[str, ...] = ("reflexion", "bloqueante")

# Valores oficiales de RESULTADO_PRIMERO/metricas_100eps.json.
OFICIAL_COBERTURA: Dict[str, float] = {
    "madrl":      0.681291,
    "heuristica": 0.254349,
    "aleatoria":  0.140186,
}
TOL_VALIDACION: float = 0.01

RUTA_MODELO:  Path = _CARPETA_SCRIPT / "modelos" / "modelo_PRIMERO.zip"
DIR_SALIDA:   Path = _CARPETA_SCRIPT / "resultados"
RUTA_CSV:     Path = DIR_SALIDA / "experimento_D_completo.csv"
RUTA_RESUMEN: Path = DIR_SALIDA / "resumen_experimento_D.txt"


# =============================================================================
# POLÍTICAS — portadas literalmente del protocolo original
# =============================================================================

def envolver_angulo(theta: float) -> float:
    """Wrap de un ángulo a [-π, π] (idéntica al protocolo original)."""
    return (theta + math.pi) % (2.0 * math.pi) - math.pi


def politica_madrl(modelo: PPO) -> Callable:
    """Cierre que retorna acciones del modelo MADRL (deterministic=True)."""
    def _act(env, obs_dict, rng):
        agentes = list(obs_dict.keys())
        obs_arr = np.stack([obs_dict[a] for a in agentes])
        acciones, _ = modelo.predict(obs_arr, deterministic=True)
        return {a: acciones[k] for k, a in enumerate(agentes)}
    return _act


def politica_heuristica_NN(env, obs_dict, rng, K_omega: float = K_OMEGA_NN):
    """
    Heurística "go to nearest target" (carrot chasing) — portada literal:
      - objetivo más cercano (euclídeo) para cada agente,
      - err = wrap(θ_objetivo − θ_actual),
      - ω = clip(K_ω · err, ±Ω_MAX),
      - v = V_MAX · max(0, cos(err))   (solo avanza si está alineado).
    NO usa `rng` (se recibe por compatibilidad de firma).
    """
    objetivos = env._field.posiciones_objetivos            # (H, 2)
    salida: Dict[str, np.ndarray] = {}
    for a in obs_dict.keys():
        estado = env._estados[a]
        x, y, th = float(estado[0]), float(estado[1]), float(estado[2])
        difs  = objetivos - np.array([x, y])
        dists = np.linalg.norm(difs, axis=1)
        idx   = int(np.argmin(dists))
        dx, dy = float(difs[idx, 0]), float(difs[idx, 1])
        th_obj = math.atan2(dy, dx)
        err    = envolver_angulo(th_obj - th)
        omega  = float(np.clip(K_omega * err, -OMEGA_MAX, OMEGA_MAX))
        v      = float(V_MAX * max(0.0, math.cos(err)))
        salida[a] = np.array([v, omega], dtype=np.float32)
    return salida


def politica_aleatoria(env, obs_dict, rng):
    """v ~ U[−V_MAX, V_MAX], ω ~ U[−Ω_MAX, Ω_MAX] (portada literal)."""
    salida: Dict[str, np.ndarray] = {}
    for a in obs_dict.keys():
        v   = float(rng.uniform(-V_MAX,     V_MAX))
        ome = float(rng.uniform(-OMEGA_MAX, OMEGA_MAX))
        salida[a] = np.array([v, ome], dtype=np.float32)
    return salida


# =============================================================================
# EPISODIO
# =============================================================================

def correr_episodio(env, accionar: Callable, seed_ep: int) -> Dict[str, object]:
    """
    Ejecuta un episodio determinista y retorna sus métricas.

    El RNG se siembra POR EPISODIO con `seed_ep` (ver nota del módulo): así
    la política aleatoria recibe la misma secuencia de acciones en ambas
    condiciones de borde, y el pareo es válido.
    """
    rng = np.random.default_rng(seed_ep)
    obs_dict, _ = env.reset(seed=seed_ep)
    agentes: List[str] = list(obs_dict.keys())
    n_a: int = len(agentes)

    pares_colision: set = set()
    n_pasos: int = 0
    pasos_con_recorte: int = 0
    suma_recortes_prev: int = 0
    done = False

    while not done:
        accion_dict = accionar(env, obs_dict, rng)
        obs_dict, _, term, trunc, _ = env.step(accion_dict)
        n_pasos += 1

        suma_recortes_actual = sum(env.contador_recortes.values())
        if suma_recortes_actual > suma_recortes_prev:
            pasos_con_recorte += 1
        suma_recortes_prev = suma_recortes_actual

        pos = np.array([env._estados[a][:2] for a in agentes])
        for ii in range(n_a):
            for jj in range(ii + 1, n_a):
                if float(np.linalg.norm(pos[ii] - pos[jj])) < D_SAFE:
                    pares_colision.add((ii, jj))

        done = all(trunc.values()) or all(term.values())

    return {
        "cobertura_final": round(
            1.0 - float(np.mean(env._field._grid_aoi)), 6
        ),
        "n_colisiones":      len(pares_colision),
        "pasos":             n_pasos,
        "reflexiones_total": sum(env.contador_reflexiones.values()),
        "recortes_total":    suma_recortes_prev,
        "frac_pasos_con_recorte": round(
            pasos_con_recorte / n_pasos, 6
        ) if n_pasos else 0.0,
        "frac_pasos_agente_recorte": round(
            suma_recortes_prev / (n_pasos * n_a), 6
        ) if n_pasos else 0.0,
    }


# =============================================================================
# ESTADÍSTICA
# =============================================================================

def ic95(muestra: np.ndarray) -> Tuple[float, float, float, float]:
    """
    Media, desviación (ddof=1), IC95 inferior y superior (media ± 1.96·EE).
    Con n=100 la aproximación normal es adecuada (t_0.975,99 = 1.984).
    """
    n     = len(muestra)
    media = float(np.mean(muestra))
    std   = float(np.std(muestra, ddof=1))
    ee    = std / math.sqrt(n)
    return media, std, media - 1.96 * ee, media + 1.96 * ee


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    """Corre el factorial 3×2×100 y reporta."""
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)

    print("═" * 74)
    print("  EXPERIMENTO D — 3 estrategias × 2 bordes × 100 semillas (pareado)")
    print("═" * 74)

    modelo = PPO.load(str(RUTA_MODELO), device="cpu")
    accionadores: Dict[str, Callable] = {
        "madrl":      politica_madrl(modelo),
        "heuristica": politica_heuristica_NN,
        "aleatoria":  politica_aleatoria,
    }

    filas: List[Dict[str, object]] = []
    # datos[estrategia][condicion][seed_ep] = fila
    datos: Dict[str, Dict[str, Dict[int, Dict[str, object]]]] = {
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
            for i in range(N_EPISODIOS):
                seed_ep = SEED_BASE * 10_000 + i
                m = correr_episodio(env, accionadores[estrategia], seed_ep)
                fila: Dict[str, object] = {
                    "estrategia": estrategia,
                    "condicion":  condicion,
                    "seed_ep":    seed_ep,
                    **m,
                }
                filas.append(fila)
                datos[estrategia][condicion][seed_ep] = fila
            cob = np.array([
                float(f["cobertura_final"])
                for f in datos[estrategia][condicion].values()
            ])
            print(f"  {estrategia:11s} {condicion:11s} "
                  f"cob={float(np.mean(cob)):.4f} ± {float(np.std(cob)):.4f}  "
                  f"({time.time()-t0:.0f}s)")

        # ── Validación de control tras completar la estrategia ────────────
        cob_ctrl = np.array([
            float(f["cobertura_final"])
            for f in datos[estrategia]["reflexion"].values()
        ])
        media_ctrl = float(np.mean(cob_ctrl))
        oficial    = OFICIAL_COBERTURA[estrategia]
        delta      = abs(media_ctrl - oficial)
        marca      = "OK" if delta <= TOL_VALIDACION else "DESVIACIÓN"
        print(f"    VALIDACIÓN {estrategia}: {media_ctrl:.6f} vs oficial "
              f"{oficial:.6f}  |Δ|={delta:.6f}  [{marca}]\n")
        if delta > TOL_VALIDACION:
            print(f"  ABORTADO: la estrategia '{estrategia}' bajo 'reflexion' "
                  f"NO reproduce el valor oficial. La implementación no es la "
                  f"misma; la comparación no sería válida.")
            sys.exit(1)

    # ── CSV ──────────────────────────────────────────────────────────────
    campos = list(filas[0].keys())
    with open(RUTA_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)
    print(f"CSV escrito ({len(filas)} filas) → {RUTA_CSV}")

    # ── Análisis ─────────────────────────────────────────────────────────
    semillas = [SEED_BASE * 10_000 + i for i in range(N_EPISODIOS)]

    def vec(estrategia: str, condicion: str, campo: str) -> np.ndarray:
        return np.array([
            float(datos[estrategia][condicion][s][campo]) for s in semillas
        ])

    L: List[str] = []
    L.append("EXPERIMENTO D — ¿La degradación por bordes bloqueantes es")
    L.append("específica de la política aprendida?")
    L.append("3 estrategias × 2 condiciones de borde × 100 semillas (600 eps),")
    L.append("pareado por semilla. 5 agentes, domain_rand=False.")
    L.append("=" * 72)
    L.append("")

    # ── Validación ────────────────────────────────────────────────────────
    L.append("VALIDACIÓN DE CONTROL (condición 'reflexion' vs protocolo original)")
    L.append(f"  {'estrategia':12s} {'replicado':>12s} {'oficial':>12s} {'|Δ|':>9s}")
    for e in ESTRATEGIAS:
        m = float(np.mean(vec(e, "reflexion", "cobertura_final")))
        L.append(f"  {e:12s} {m:12.6f} {OFICIAL_COBERTURA[e]:12.6f} "
                 f"{abs(m-OFICIAL_COBERTURA[e]):9.6f}")
    L.append("  (aleatoria: validación estadística — su RNG original es")
    L.append("   irreproducible por PYTHONHASHSEED; ver docstring del script)")
    L.append("")

    # ── Tabla 1: cobertura 3×2 ───────────────────────────────────────────
    L.append("TABLA 1 — COBERTURA AoI FINAL (media ± desv.)")
    L.append(f"  {'estrategia':12s} {'reflexion':>18s} {'bloqueante':>18s}")
    for e in ESTRATEGIAS:
        r = vec(e, "reflexion",  "cobertura_final")
        b = vec(e, "bloqueante", "cobertura_final")
        L.append(f"  {e:12s} {float(np.mean(r)):9.4f} ± {float(np.std(r,ddof=1)):.4f}"
                 f"  {float(np.mean(b)):9.4f} ± {float(np.std(b,ddof=1)):.4f}")
    L.append("")

    # ── Tabla 2: degradación por estrategia ──────────────────────────────
    L.append("TABLA 2 — DEGRADACIÓN POR ESTRATEGIA (diferencia pareada por semilla)")
    L.append("  Δ = bloqueante − reflexion   (negativo = degradación)")
    L.append("")
    degradaciones: Dict[str, np.ndarray] = {}
    for e in ESTRATEGIAS:
        r = vec(e, "reflexion",  "cobertura_final")
        b = vec(e, "bloqueante", "cobertura_final")
        d = b - r
        degradaciones[e] = d
        md, sd, lo, hi = ic95(d)
        rel = 100.0 * md / float(np.mean(r))
        n_peor = int(np.sum(d < 0))
        L.append(f"  {e}:")
        L.append(f"      ABSOLUTA : {md:+.4f} ± {sd:.4f}   "
                 f"IC95 [{lo:+.4f}, {hi:+.4f}]")
        L.append(f"      RELATIVA : {rel:+.2f}%")
        L.append(f"      episodios peor: {n_peor}/{N_EPISODIOS}")
    L.append("")

    # ── Tabla 3: diferencia de diferencias (RESULTADO PRINCIPAL) ─────────
    L.append("TABLA 3 — DIFERENCIA DE DIFERENCIAS (resultado principal)")
    L.append("  DiD = Δ(MADRL) − Δ(línea base), pareado por semilla.")
    L.append("  DiD < 0 con IC95 que excluye 0 ⇒ MADRL se degrada MÁS que")
    L.append("  la línea base ⇒ la degradación es específica de lo aprendido.")
    L.append("")
    for base in ("heuristica", "aleatoria"):
        did = degradaciones["madrl"] - degradaciones[base]
        md, sd, lo, hi = ic95(did)
        excluye = "SÍ (significativo)" if (lo < 0 and hi < 0) or (lo > 0 and hi > 0) \
                  else "NO (no significativo)"
        L.append(f"  MADRL vs {base}:")
        L.append(f"      DiD = {md:+.4f} ± {sd:.4f}   IC95 [{lo:+.4f}, {hi:+.4f}]")
        L.append(f"      ¿IC95 excluye 0? {excluye}")
    L.append("")

    # ── Tabla 4: reflexiones bajo 'reflexion' ────────────────────────────
    L.append("TABLA 4 — REFLEXIONES POR EPISODIO (condición 'reflexion')")
    L.append("  Cruce con el Experimento B: MADRL debe dar 45.74 ± 5.54")
    for e in ESTRATEGIAS:
        v = vec(e, "reflexion", "reflexiones_total")
        L.append(f"  {e:12s} {float(np.mean(v)):8.2f} ± {float(np.std(v,ddof=1)):.2f}")
    L.append("")

    # ── Tabla 5: tiempo contra el borde ──────────────────────────────────
    L.append("TABLA 5 — TIEMPO CONTRA EL BORDE (condición 'bloqueante')")
    L.append(f"  {'estrategia':12s} {'frac agente-paso':>20s} {'frac pasos ≥1':>16s}")
    for e in ESTRATEGIAS:
        fa = vec(e, "bloqueante", "frac_pasos_agente_recorte")
        fp = vec(e, "bloqueante", "frac_pasos_con_recorte")
        L.append(f"  {e:12s} {float(np.mean(fa)):11.4f} ± {float(np.std(fa,ddof=1)):.4f}"
                 f"  {float(np.mean(fp)):8.4f} ± {float(np.std(fp,ddof=1)):.4f}")
    L.append("")

    # ── Tabla 6: colisiones ──────────────────────────────────────────────
    L.append("TABLA 6 — COLISIONES (pares únicos por episodio)")
    L.append(f"  {'estrategia':12s} {'reflexion':>16s} {'bloqueante':>16s} "
             f"{'Δ pareada':>22s}")
    for e in ESTRATEGIAS:
        r = vec(e, "reflexion",  "n_colisiones")
        b = vec(e, "bloqueante", "n_colisiones")
        d = b - r
        md, sd, lo, hi = ic95(d)
        L.append(f"  {e:12s} {float(np.mean(r)):7.3f} ± {float(np.std(r,ddof=1)):.3f}"
                 f"  {float(np.mean(b)):7.3f} ± {float(np.std(b,ddof=1)):.3f}"
                 f"  {md:+.3f} [{lo:+.3f},{hi:+.3f}]")
    L.append("")
    L.append("  % de episodios con ≥1 colisión:")
    for e in ESTRATEGIAS:
        pr = 100.0 * float(np.mean(vec(e, "reflexion",  "n_colisiones") > 0))
        pb = 100.0 * float(np.mean(vec(e, "bloqueante", "n_colisiones") > 0))
        L.append(f"    {e:12s} reflexion={pr:5.1f}%   bloqueante={pb:5.1f}%")

    resumen = "\n".join(L)
    RUTA_RESUMEN.write_text(resumen, encoding="utf-8")
    print(f"Resumen escrito → {RUTA_RESUMEN}\n")
    print(resumen)


if __name__ == "__main__":
    main()
