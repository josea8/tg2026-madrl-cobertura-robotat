"""
entrenar_v4.py
==============
TESIS V4 — Entrenamiento con CONTACTO QUE BLOQUEA LA ROTACIÓN.

Diagnóstico que motiva este modo
--------------------------------
En v2 ("bloqueante") y v3 ("bloqueante_radio") el contacto con la pared sólo
recorta la posición: θ sigue integrando libre, así que el agente se pega,
rota y sigue. Meterse contra el muro NO CUESTA NADA en el entrenamiento.

En Webots la fricción del chasis contra un cuerpo rígido bloquea también la
rotación — lo medimos: durante los atascos Δθ = 0.0° EXACTO — y el robot
queda clavado el resto del episodio.

v3 corrigió DÓNDE está la pared (recorte a [r, W−r]) pero no QUÉ SE SIENTE
tocarla, y el resultado en Webots fue peor que v2: 85/90 atascos (94.4%) vs
51/90 (56.7%). El diagnóstico fue inequívoco: la acción previa al atasco era
v = −0.3100 m/s (V_MAX en REVERSA) en 85 de 85 casos. No es que la política
"roce la pared para cubrir el anillo" —eso sería avanzar A LO LARGO del
muro—: es que meterse CONTRA él sale gratis.

Modo "contacto_rigido"
----------------------
  1. Recorte de posición a [r, W−r] con r = 0.075 (igual que v3).
  2. ADEMÁS: si el agente está en contacto Y la componente de su velocidad en
     la normal de esa pared apunta hacia afuera, θ NO se integra ese paso.
  3. Si la acción no empuja contra la pared, θ se integra normal: la salida
     está SIEMPRE disponible (invertir v o girar hacia adentro libera), así
     que no se crean estados absorbentes.

Es aprendible desde una sola observación —posición y rumbo bastan para saber
si la acción empuja contra el muro—, así que no requiere memoria.

λ_pared = 0
-----------
La penalización de proximidad queda DESCARTADA por lo medido en v3: empujaba
a los agentes al centro y disparaba las colisiones (0.17 → 3.72 → 9.44 pares
por episodio para λ = 0 / 1 / 3, con 100% de episodios con colisión en los
dos últimos).

Selección del mejor modelo
--------------------------
`CallbackMejorModelo` evalúa cada FRECUENCIA_EVAL pasos sobre N_EPS_EVAL = 20
episodios deterministas y guarda el mejor por cobertura. Esto ya nos mordió
dos veces: v2 picó en 170k y se guardó el de 200k (0.6242 → 0.4530), y en v3
λ=3 colapsó en los últimos 40k (0.4483 → 0.1595). Con 5 episodios la
selección elegía ruido; con 20 el error estándar cae a la mitad.

Salidas
-------
  modelo_v4_mejor.zip     — mejor checkpoint por cobertura
  modelo_v4_final.zip     — último checkpoint (para comparar)
  resultados/curvas_v4.csv
  resultados/eval_v4.csv
  resultados/resumen_v4.txt

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import supersuit as ss
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.vec_env import VecMonitor

from lib.swarm_env_skeleton import D_SAFE, make_env


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

N_AGENTES:    int   = 5
ARENA:        Tuple[float, float] = (3.0, 3.0)
MAX_STEPS_EP: int   = 500
COMM_RADIUS:  float = 1.0
SEED:         int   = 42
N_ENVS:       int   = 4
N_PASOS:      int   = 200_000
MODO_BORDE:   str   = "contacto_rigido"
RADIO_CHASIS: float = 0.075
LAMBDA_PARED: float = 0.0          # descartada en v3 (ver docstring)

HPARAMS: Dict[str, float] = {
    "learning_rate": 6.855028382061343e-05,
    "gamma":         0.9844980522475681,
    "clip_range":    0.20631649325745388,
    "n_steps":       128,
    "batch_size":    64,
    "n_epochs":      13,
    "ent_coef":      0.022872258876193912,
    "gae_lambda":    0.9608422073341644,
    "vf_coef":       0.5,
    "max_grad_norm": 0.5,
}

PESOS: Dict[str, float] = {
    "lambda_gradient": 0.5622468083379316,
    "lambda_entropy":  1.1403296484190344,
    "lambda_ibrm":     0.48380314172632155,
    "lambda_cbf":      2.9655314099141474,
    "lambda_pared":    LAMBDA_PARED,
}

CAPAS_RED: List[int] = [256, 256]

# ── Selección del mejor modelo ───────────────────────────────────────────
FRECUENCIA_EVAL: int = 20_000
N_EPS_EVAL:      int = 20          # 20, no 5: con 5 la selección elige ruido
SEED_EVAL_CB:    int = 990_000     # separada de las semillas de evaluación

# ── Evaluación final: las 18 semillas de los lotes de Webots ─────────────
N_EPS_FINAL: int = 18

ANCHO_ANILLO: float = 0.30

# Referencias sobre las mismas 18 semillas.
REF_V2_PY_COBERTURA: float = 0.4426   # sanidad (bloqueante), control Python
REF_V3_PY_COBERTURA: float = 0.5114   # radio, λ=0
REF_V3_PY_ANILLO:    float = 0.4565

DIR_SALIDA:      Path = _CARPETA / "resultados"
RUTA_MEJOR:      Path = _CARPETA / "modelo_v4_mejor.zip"
RUTA_FINAL:      Path = _CARPETA / "modelo_v4_final.zip"


# =============================================================================
# ENTORNOS
# =============================================================================

def construir_env_eval():
    """Env determinista de evaluación con contacto rígido."""
    return make_env(
        n_agents       = N_AGENTES,
        arena_size     = ARENA,
        max_steps      = MAX_STEPS_EP,
        comm_radius    = COMM_RADIUS,
        reward_weights = PESOS,
        domain_rand    = False,
        seed           = SEED,
        modo_borde     = MODO_BORDE,
        radio_chasis   = RADIO_CHASIS,
    )


def construir_vec_env() -> VecMonitor:
    """VecEnv de entrenamiento (parameter sharing + parches Bug A y B)."""
    env_base = make_env(
        n_agents       = N_AGENTES,
        arena_size     = ARENA,
        max_steps      = MAX_STEPS_EP,
        comm_radius    = COMM_RADIUS,
        reward_weights = PESOS,
        domain_rand    = True,
        seed           = SEED,
        modo_borde     = MODO_BORDE,
        radio_chasis   = RADIO_CHASIS,
    )
    env_vec = ss.pettingzoo_env_to_vec_env_v1(env_base)
    env_concat = ss.concat_vec_envs_v1(
        env_vec, num_vec_envs=N_ENVS, num_cpus=1,
        base_class="stable_baselines3",
    )
    env_concat.seed = lambda seed=None: [None] * env_concat.num_envs
    return VecMonitor(env_concat)


# =============================================================================
# MÉTRICAS
# =============================================================================

def cobertura_anillo(env) -> float:
    """Cobertura del AoI en la banda perimetral de ANCHO_ANILLO."""
    xx, yy = env._field._grid_xx, env._field._grid_yy
    Wx, Wy = ARENA
    dist = np.minimum.reduce([xx, Wx - xx, yy, Wy - yy])
    mascara = dist <= ANCHO_ANILLO
    if not np.any(mascara):
        return 0.0
    return 1.0 - float(np.mean(env._field._grid_aoi[mascara]))


def evaluar_episodio(env, modelo: PPO, seed_ep: int) -> Dict[str, float]:
    """
    Episodio determinista. Devuelve cobertura global y de anillo, fracción de
    tiempo EN CONTACTO, fracción con la ROTACIÓN BLOQUEADA, y colisiones.
    """
    obs, _ = env.reset(seed=seed_ep)
    agentes: List[str] = list(obs.keys())
    n_a = len(agentes)

    pares: set = set()
    n_pasos = 0
    done = False

    while not done:
        acciones, _ = modelo.predict(
            np.stack([obs[a] for a in agentes]), deterministic=True
        )
        obs, _, term, trunc, _ = env.step(
            {a: acciones[k] for k, a in enumerate(agentes)}
        )
        n_pasos += 1
        pos = np.array([env._estados[a][:2] for a in agentes])
        for ii in range(n_a):
            for jj in range(ii + 1, n_a):
                if float(np.linalg.norm(pos[ii] - pos[jj])) < D_SAFE:
                    pares.add((ii, jj))
        done = all(trunc.values()) or all(term.values())

    denom = n_pasos * n_a if n_pasos else 1
    return {
        "cobertura_final":  round(1.0 - float(np.mean(env._field._grid_aoi)), 6),
        "cobertura_anillo": round(cobertura_anillo(env), 6),
        "frac_contacto":    round(sum(env.contador_recortes.values()) / denom, 6),
        "frac_bloqueo":     round(sum(env.contador_bloqueos.values()) / denom, 6),
        "n_colisiones":     len(pares),
        "pasos":            n_pasos,
    }


class CallbackMejorModelo(BaseCallback):
    """
    Evalúa periódicamente sobre N_EPS_EVAL episodios y guarda el MEJOR modelo
    por cobertura. Registra además anillo, contacto y bloqueo para las curvas.

    Con 5 episodios (como en v2/v3) la selección elegía ruido; con 20 el error
    estándar de la media cae a la mitad.
    """

    def __init__(self, verbose: int = 0):
        super().__init__(verbose)
        self.registros: List[Dict[str, float]] = []
        self.mejor_cobertura: float = -np.inf
        self.mejor_pasos: int = -1
        self._env = None
        self._proximo = FRECUENCIA_EVAL

    def _on_training_start(self) -> None:
        self._env = construir_env_eval()
        self._evaluar(0)

    def _evaluar(self, pasos: int) -> None:
        acum: Dict[str, List[float]] = {
            "cobertura_final": [], "cobertura_anillo": [],
            "frac_contacto": [], "frac_bloqueo": [], "n_colisiones": [],
        }
        for i in range(N_EPS_EVAL):
            m = evaluar_episodio(self._env, self.model, SEED_EVAL_CB + i)
            for k in acum:
                acum[k].append(float(m[k]))

        r = {
            "pasos":            pasos,
            "cobertura":        round(float(np.mean(acum["cobertura_final"])), 6),
            "cobertura_std":    round(float(np.std(acum["cobertura_final"])), 6),
            "cobertura_anillo": round(float(np.mean(acum["cobertura_anillo"])), 6),
            "frac_contacto":    round(float(np.mean(acum["frac_contacto"])), 6),
            "frac_bloqueo":     round(float(np.mean(acum["frac_bloqueo"])), 6),
            "colisiones":       round(float(np.mean(acum["n_colisiones"])), 4),
        }
        self.registros.append(r)

        marca = ""
        if r["cobertura"] > self.mejor_cobertura:
            self.mejor_cobertura = r["cobertura"]
            self.mejor_pasos = pasos
            self.model.save(str(RUTA_MEJOR))
            marca = "  ← MEJOR (guardado)"

        print(f"  [eval] pasos={pasos:7d}  cob={r['cobertura']:.4f}"
              f"±{r['cobertura_std']:.4f}  anillo={r['cobertura_anillo']:.4f}  "
              f"contacto={r['frac_contacto']:.4f}  "
              f"bloqueo={r['frac_bloqueo']:.4f}  "
              f"col={r['colisiones']:.2f}{marca}")

    def _on_step(self) -> bool:
        if self.num_timesteps >= self._proximo:
            self._evaluar(self.num_timesteps)
            self._proximo += FRECUENCIA_EVAL
        return True


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    """Entrena con contacto rígido y evalúa el mejor checkpoint."""
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)

    print("═" * 74)
    print("  TESIS V4 — contacto que BLOQUEA LA ROTACIÓN")
    print("═" * 74)
    print(f"  modo_borde={MODO_BORDE}  r={RADIO_CHASIS} m  "
          f"λ_pared={LAMBDA_PARED} (descartada en v3)")
    print(f"  {N_PASOS:,} pasos · eval cada {FRECUENCIA_EVAL:,} sobre "
          f"{N_EPS_EVAL} episodios · guarda el mejor por cobertura\n")

    env_train = construir_vec_env()
    buffer_total = int(HPARAMS["n_steps"]) * env_train.num_envs
    batch = int(HPARAMS["batch_size"])
    if buffer_total % batch != 0:
        for bs in range(batch, 0, -1):
            if buffer_total % bs == 0:
                batch = bs
                break

    modelo = PPO(
        policy        = "MlpPolicy",
        env           = env_train,
        learning_rate = HPARAMS["learning_rate"],
        n_steps       = int(HPARAMS["n_steps"]),
        batch_size    = batch,
        n_epochs      = int(HPARAMS["n_epochs"]),
        gamma         = HPARAMS["gamma"],
        gae_lambda    = HPARAMS["gae_lambda"],
        clip_range    = HPARAMS["clip_range"],
        ent_coef      = HPARAMS["ent_coef"],
        vf_coef       = HPARAMS["vf_coef"],
        max_grad_norm = HPARAMS["max_grad_norm"],
        policy_kwargs = {
            "net_arch":      [{"pi": CAPAS_RED, "vf": CAPAS_RED}],
            "activation_fn": torch.nn.Tanh,
        },
        verbose = 0,
        seed    = SEED,
    )

    cb = CallbackMejorModelo()
    t0 = time.time()
    modelo.learn(total_timesteps=N_PASOS, callback=cb, progress_bar=False)
    dur = time.time() - t0
    modelo.save(str(RUTA_FINAL))

    print(f"\n  Entrenamiento en {dur/60:.1f} min")
    print(f"  MEJOR checkpoint: {cb.mejor_pasos:,} pasos "
          f"(cobertura {cb.mejor_cobertura:.4f}) → {RUTA_MEJOR.name}")

    with open(DIR_SALIDA / "curvas_v4.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(cb.registros[0].keys()))
        w.writeheader()
        w.writerows(cb.registros)

    # ── Evaluación final: MEJOR modelo sobre las 18 semillas ─────────────
    print(f"\n  Evaluando el MEJOR modelo sobre {N_EPS_FINAL} semillas...")
    mejor = PPO.load(str(RUTA_MEJOR), device="cpu")
    env_eval = construir_env_eval()
    filas: List[Dict[str, object]] = []
    for i in range(N_EPS_FINAL):
        seed_ep = SEED * 10_000 + i
        filas.append({"seed_ep": seed_ep,
                      **evaluar_episodio(env_eval, mejor, seed_ep)})

    with open(DIR_SALIDA / "eval_v4.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)

    cob    = np.array([float(r["cobertura_final"])  for r in filas])
    anillo = np.array([float(r["cobertura_anillo"]) for r in filas])
    cont   = np.array([float(r["frac_contacto"])    for r in filas])
    bloq   = np.array([float(r["frac_bloqueo"])     for r in filas])
    col    = np.array([float(r["n_colisiones"])     for r in filas])

    L: List[str] = []
    L.append("TESIS V4 — contacto que BLOQUEA LA ROTACIÓN")
    L.append(f"modo_borde={MODO_BORDE} · r={RADIO_CHASIS} m · "
             f"λ_pared={LAMBDA_PARED}")
    L.append(f"{N_PASOS:,} pasos · Trial 13 sin cambios · {N_AGENTES} agentes")
    L.append(f"Mejor checkpoint: {cb.mejor_pasos:,} pasos "
             f"(seleccionado sobre {N_EPS_EVAL} episodios)")
    L.append(f"Evaluación: {N_EPS_FINAL} semillas (las de los lotes de Webots)")
    L.append("=" * 72)
    L.append("")
    L.append("EVALUACIÓN DEL MEJOR MODELO (Python)")
    L.append(f"  cobertura AoI          : {float(np.mean(cob)):.4f} ± "
             f"{float(np.std(cob)):.4f}")
    L.append(f"  cobertura anillo perim.: {float(np.mean(anillo)):.4f} ± "
             f"{float(np.std(anillo)):.4f}   "
             f"(razón anillo/global = {float(np.mean(anillo))/float(np.mean(cob)):.3f})")
    L.append(f"  fracción en CONTACTO   : {float(np.mean(cont)):.4f} ± "
             f"{float(np.std(cont)):.4f}")
    L.append(f"  fracción con ROTACIÓN BLOQUEADA : {float(np.mean(bloq)):.4f} ± "
             f"{float(np.std(bloq)):.4f}")
    L.append(f"  colisiones (pares)     : {float(np.mean(col)):.3f}   "
             f"({100.0*float(np.mean(col > 0)):.1f}% de eps con ≥1)")
    L.append("")
    L.append("REFERENCIAS (mismas 18 semillas, Python)")
    L.append(f"  v2 sanidad (bloqueante, sin radio) : "
             f"cobertura {REF_V2_PY_COBERTURA:.4f}")
    L.append(f"  v3 radio λ=0 (bloqueante_radio)    : "
             f"cobertura {REF_V3_PY_COBERTURA:.4f}  "
             f"anillo {REF_V3_PY_ANILLO:.4f}")
    L.append("")
    L.append("  OJO con la comparabilidad de 'frac_contacto': el contador se")
    L.append("  dispara cuando el CENTRO cruza el límite del dominio, y ese")
    L.append("  límite es [0,W] en v2 y [r,W−r] en v3/v4. Los valores NO son")
    L.append("  comparables entre modos; lo comparable es cobertura,")
    L.append("  colisiones y, sobre todo, lo que salga de Webots.")
    L.append("")
    L.append("  'frac_bloqueo' es exclusiva de v4: fracción de pasos-agente en")
    L.append("  que la rotación quedó bloqueada por empujar contra la pared.")
    L.append("  Es la señal que v2 y v3 NO tenían durante el entrenamiento.")
    L.append("")
    L.append("CURVAS (selección del mejor por cobertura)")
    L.append(f"  {'pasos':>8s} {'cobertura':>11s} {'anillo':>9s} "
             f"{'contacto':>10s} {'bloqueo':>9s} {'colis.':>8s}")
    for r in cb.registros:
        marca = "  ←" if int(r["pasos"]) == cb.mejor_pasos else ""
        L.append(f"  {int(r['pasos']):8d} {r['cobertura']:11.4f} "
                 f"{r['cobertura_anillo']:9.4f} {r['frac_contacto']:10.4f} "
                 f"{r['frac_bloqueo']:9.4f} {r['colisiones']:8.2f}{marca}")

    resumen = "\n".join(L)
    (DIR_SALIDA / "resumen_v4.txt").write_text(resumen, encoding="utf-8")
    print(f"\nResumen → {DIR_SALIDA / 'resumen_v4.txt'}\n")
    print(resumen)


if __name__ == "__main__":
    main()
