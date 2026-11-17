"""
entrenar_v3.py
==============
VÍA A — Reentrenamiento con DOS cambios respecto a tesis_v2 (sanidad):

  1. RADIO DEL CHASIS: el borde recorta la posición del centro a [r, W−r]
     con r = 0.075 m, en vez de [0, W]. Alinea la geometría de entrenamiento
     con la de Webots y la del Robotat (el agente deja de ser un punto).

  2. PENALIZACIÓN DE PROXIMIDAD A PARED (p_pared), con peso configurable.

Por qué los dos juntos
----------------------
Con bordes bloqueantes puros (tesis_v2), tocar la pared cuesta UN paso: la
rotación sigue libre y el agente escapa al paso siguiente. En Webots el
contacto bloquea también la rotación (fricción del chasis contra un cuerpo
rígido) y puede costar el EPISODIO. El radio corrige DÓNDE está la pared; la
penalización corrige CUÁNTO cuesta acercarse. Uno sin el otro deja la mitad
del gap sin cerrar.

Evidencia que motiva esto (Fase 2 multi-robot en Webots):
  atascos por agente-episodio: 1 ag 16.7% · 2 ag 25.0% · 5 ag 56.7%
  y el diagnóstico mostró que 71% de los atascos NO tenían vecino cerca, con
  acción previa v = +0.31 m/s (V_MAX) contra la pared ⇒ gap chasis-vs-punto.

Barrido del peso
----------------
Se entrenan tres modelos con lambda_pared ∈ {0.0, 1.0, 3.0}:
  - 0.0 : SÓLO el radio. Aísla la contribución del cambio geométrico.
  - 1.0 : penalización moderada (comparable a lambda_entropy = 1.14).
  - 3.0 : penalización fuerte (comparable a lambda_cbf = 2.97).
El resto de los hiperparámetros es el Trial 13, sin cambios.

Riesgo a vigilar: ANILLO PERIMETRAL SIN CUBRIR. Una penalización alta puede
enseñar al enjambre a no acercarse nunca al borde, dejando una franja sin
explorar. Por eso se reporta `cobertura_anillo` (cobertura del AoI restringida
a la banda de ANCHO_ANILLO junto a las paredes) además de la global: es la
métrica que delata ese modo de fallo.

Salidas (por cada peso)
-----------------------
  modelo_v3_lp<peso>.zip
  resultados/curvas_v3_lp<peso>.csv
  resultados/eval_v3_lp<peso>.csv
  resultados/resumen_v3.txt          (comparativa de los tres)

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

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
MODO_BORDE:   str   = "bloqueante_radio"
RADIO_CHASIS: float = 0.075

# Barrido del peso de la penalización de pared.
PESOS_PARED: List[float] = [0.0, 1.0, 3.0]

# Hiperparámetros del Trial 13 (sin cambios).
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

PESOS_BASE: Dict[str, float] = {
    "lambda_gradient": 0.5622468083379316,
    "lambda_entropy":  1.1403296484190344,
    "lambda_ibrm":     0.48380314172632155,
    "lambda_cbf":      2.9655314099141474,
}

CAPAS_RED: List[int] = [256, 256]

# Curvas de entrenamiento (semillas separadas de las de evaluación).
FRECUENCIA_CURVA: int = 20_000
N_EPS_CURVA:      int = 3
SEED_CURVA:       int = 990_000

# Evaluación final: mismas 18 semillas de los lotes de Webots.
N_EPS_FINAL: int = 18

# Banda perimetral para detectar el "anillo sin cubrir".
ANCHO_ANILLO: float = 0.30

# Referencias (mismas 18 semillas, control Python de tesis_v2).
REF_V2_COBERTURA: float = 0.4426
REF_V2_BORDE:     float = 0.0599

DIR_SALIDA: Path = _CARPETA / "resultados"


# =============================================================================
# ENTORNOS
# =============================================================================

def construir_env_eval(lambda_pared: float):
    """Env determinista de evaluación (sin domain_rand), con radio y p_pared."""
    pesos = dict(PESOS_BASE)
    pesos["lambda_pared"] = lambda_pared
    return make_env(
        n_agents       = N_AGENTES,
        arena_size     = ARENA,
        max_steps      = MAX_STEPS_EP,
        comm_radius    = COMM_RADIUS,
        reward_weights = pesos,
        domain_rand    = False,
        seed           = SEED,
        modo_borde     = MODO_BORDE,
        radio_chasis   = RADIO_CHASIS,
    )


def construir_vec_env(lambda_pared: float) -> VecMonitor:
    """VecEnv de entrenamiento con parameter sharing (parches Bug A y B)."""
    pesos = dict(PESOS_BASE)
    pesos["lambda_pared"] = lambda_pared
    env_base = make_env(
        n_agents       = N_AGENTES,
        arena_size     = ARENA,
        max_steps      = MAX_STEPS_EP,
        comm_radius    = COMM_RADIUS,
        reward_weights = pesos,
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
    """
    Cobertura del AoI restringida a la banda perimetral de ANCHO_ANILLO.

    Detecta el modo de fallo de una penalización demasiado alta: el enjambre
    aprende a no acercarse al borde y deja una franja sin explorar. La
    cobertura GLOBAL puede verse bien mientras el anillo queda vacío.
    """
    xx = env._field._grid_xx
    yy = env._field._grid_yy
    Wx, Wy = ARENA
    dist_pared = np.minimum.reduce([xx, Wx - xx, yy, Wy - yy])
    mascara = dist_pared <= ANCHO_ANILLO
    if not np.any(mascara):
        return 0.0
    return 1.0 - float(np.mean(env._field._grid_aoi[mascara]))


def evaluar_episodio(env, modelo: PPO, seed_ep: int) -> Dict[str, float]:
    """Episodio determinista: cobertura global y de anillo, borde, colisiones."""
    obs, _ = env.reset(seed=seed_ep)
    agentes: List[str] = list(obs.keys())
    n_a = len(agentes)

    pares_col: set = set()
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
                    pares_col.add((ii, jj))
        done = all(trunc.values()) or all(term.values())

    recortes = sum(env.contador_recortes.values())
    return {
        "cobertura_final": round(
            1.0 - float(np.mean(env._field._grid_aoi)), 6
        ),
        "cobertura_anillo": round(cobertura_anillo(env), 6),
        "frac_pasos_agente_recorte": round(
            recortes / (n_pasos * n_a), 6
        ) if n_pasos else 0.0,
        "n_colisiones": len(pares_col),
        "pasos": n_pasos,
    }


class CallbackCurvas(BaseCallback):
    """Registra cobertura, anillo y fracción en borde durante el entrenamiento."""

    def __init__(self, lambda_pared: float, verbose: int = 0):
        super().__init__(verbose)
        self.lambda_pared = lambda_pared
        self.registros: List[Dict[str, float]] = []
        self._env = None
        self._proximo = FRECUENCIA_CURVA

    def _on_training_start(self) -> None:
        self._env = construir_env_eval(self.lambda_pared)
        self._medir(0)

    def _medir(self, pasos: int) -> None:
        cobs, anillos, bordes = [], [], []
        for i in range(N_EPS_CURVA):
            m = evaluar_episodio(self._env, self.model, SEED_CURVA + i)
            cobs.append(m["cobertura_final"])
            anillos.append(m["cobertura_anillo"])
            bordes.append(m["frac_pasos_agente_recorte"])
        r = {
            "pasos":            pasos,
            "cobertura":        round(float(np.mean(cobs)), 6),
            "cobertura_anillo": round(float(np.mean(anillos)), 6),
            "frac_borde":       round(float(np.mean(bordes)), 6),
        }
        self.registros.append(r)
        print(f"    [curva λ={self.lambda_pared}] pasos={pasos:7d} "
              f"cob={r['cobertura']:.4f} anillo={r['cobertura_anillo']:.4f} "
              f"borde={r['frac_borde']:.4f}")

    def _on_step(self) -> bool:
        if self.num_timesteps >= self._proximo:
            self._medir(self.num_timesteps)
            self._proximo += FRECUENCIA_CURVA
        return True


# =============================================================================
# MAIN
# =============================================================================

def entrenar_uno(lambda_pared: float) -> Dict[str, object]:
    """Entrena y evalúa un modelo para el peso dado. Retorna sus agregados."""
    etiqueta = f"lp{lambda_pared:g}".replace(".", "p")
    print(f"\n{'─'*72}\n  λ_pared = {lambda_pared}  ({etiqueta})\n{'─'*72}")

    env_train = construir_vec_env(lambda_pared)
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

    cb = CallbackCurvas(lambda_pared)
    t0 = time.time()
    modelo.learn(total_timesteps=N_PASOS, callback=cb, progress_bar=False)
    dur = time.time() - t0

    ruta_modelo = _CARPETA / f"modelo_v3_{etiqueta}.zip"
    modelo.save(str(ruta_modelo))
    print(f"    entrenado en {dur/60:.1f} min → {ruta_modelo.name}")

    with open(DIR_SALIDA / f"curvas_v3_{etiqueta}.csv", "w",
              newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(cb.registros[0].keys()))
        w.writeheader()
        w.writerows(cb.registros)

    # ── Evaluación final sobre las 18 semillas de los lotes de Webots ────
    env_eval = construir_env_eval(lambda_pared)
    filas: List[Dict[str, object]] = []
    for i in range(N_EPS_FINAL):
        seed_ep = SEED * 10_000 + i
        filas.append({"seed_ep": seed_ep,
                      **evaluar_episodio(env_eval, modelo, seed_ep)})

    with open(DIR_SALIDA / f"eval_v3_{etiqueta}.csv", "w",
              newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)

    cob    = np.array([float(r["cobertura_final"])           for r in filas])
    anillo = np.array([float(r["cobertura_anillo"])          for r in filas])
    borde  = np.array([float(r["frac_pasos_agente_recorte"]) for r in filas])
    col    = np.array([float(r["n_colisiones"])              for r in filas])

    agregado = {
        "lambda_pared":  lambda_pared,
        "etiqueta":      etiqueta,
        "cob_media":     float(np.mean(cob)),
        "cob_std":       float(np.std(cob)),
        "anillo_media":  float(np.mean(anillo)),
        "anillo_std":    float(np.std(anillo)),
        "borde_media":   float(np.mean(borde)),
        "borde_std":     float(np.std(borde)),
        "col_media":     float(np.mean(col)),
        "col_pct":       100.0 * float(np.mean(col > 0)),
        "minutos":       dur / 60.0,
        "curvas":        cb.registros,
    }
    print(f"    EVAL: cob={agregado['cob_media']:.4f} "
          f"anillo={agregado['anillo_media']:.4f} "
          f"borde={agregado['borde_media']:.4f} "
          f"col={agregado['col_media']:.3f}")
    return agregado


def main() -> None:
    """Entrena los tres modelos y emite la comparativa."""
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)

    print("═" * 72)
    print("  TESIS V3 — radio de chasis + penalización de pared")
    print("═" * 72)
    print(f"  modo_borde={MODO_BORDE}  r={RADIO_CHASIS} m  "
          f"barrido λ_pared={PESOS_PARED}")
    print(f"  {N_PASOS:,} pasos c/u · Trial 13 sin cambios · seed {SEED}")

    agregados = [entrenar_uno(lp) for lp in PESOS_PARED]

    L: List[str] = []
    L.append("TESIS V3 — radio de chasis + penalización de proximidad a pared")
    L.append(f"modo_borde={MODO_BORDE} (recorte a [r, W−r], r={RADIO_CHASIS} m)")
    L.append(f"{N_PASOS:,} pasos por modelo · Trial 13 sin cambios · "
             f"{N_AGENTES} agentes · seed {SEED}")
    L.append(f"Evaluación: {N_EPS_FINAL} semillas (las mismas de los lotes "
             f"de Webots)")
    L.append("=" * 72)
    L.append("")
    L.append("COMPARATIVA DEL BARRIDO")
    L.append(f"  {'λ_pared':>8s} {'cobertura':>17s} {'anillo perim.':>17s} "
             f"{'frac borde':>16s} {'colisiones':>11s}")
    for a in agregados:
        L.append(f"  {a['lambda_pared']:8.1f} "
                 f"{a['cob_media']:9.4f} ± {a['cob_std']:.4f} "
                 f"{a['anillo_media']:9.4f} ± {a['anillo_std']:.4f} "
                 f"{a['borde_media']:8.4f} ± {a['borde_std']:.4f} "
                 f"{a['col_media']:7.3f} ({a['col_pct']:.0f}%)")
    L.append("")
    L.append("REFERENCIA — tesis_v2 (sanidad, bordes bloqueantes SIN radio),")
    L.append("control Python sobre las mismas 18 semillas:")
    L.append(f"  cobertura {REF_V2_COBERTURA:.4f} · "
             f"frac borde {REF_V2_BORDE:.4f}")
    L.append("")
    L.append("LECTURA")
    L.append("  λ_pared = 0.0 aísla el efecto del RADIO solo (el borde pasa de")
    L.append("  [0,W] a [r,W−r]); los otros dos suman la penalización graduada.")
    L.append("  'anillo perim.' es la cobertura del AoI en la banda de")
    L.append(f"  {ANCHO_ANILLO} m junto a las paredes: si cae mucho al subir")
    L.append("  λ_pared, el enjambre está evitando el borde de más y deja una")
    L.append("  franja sin explorar (el modo de fallo a vigilar).")
    L.append("")
    L.append("CURVAS DE ENTRENAMIENTO")
    for a in agregados:
        L.append(f"  λ_pared = {a['lambda_pared']}:")
        L.append(f"    {'pasos':>8s} {'cobertura':>11s} {'anillo':>9s} "
                 f"{'borde':>9s}")
        for r in a["curvas"]:
            L.append(f"    {int(r['pasos']):8d} {r['cobertura']:11.4f} "
                     f"{r['cobertura_anillo']:9.4f} {r['frac_borde']:9.4f}")

    resumen = "\n".join(L)
    (DIR_SALIDA / "resumen_v3.txt").write_text(resumen, encoding="utf-8")
    print(f"\nResumen → {DIR_SALIDA / 'resumen_v3.txt'}\n")
    print(resumen)


if __name__ == "__main__":
    main()
