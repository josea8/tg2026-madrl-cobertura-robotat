"""
estudio_J.py — Experimento J: sintonización con presupuesto y semillas corregidos.

Estudio de Optuna que corrige los cuatro desajustes metodológicos del estudio
original (`optuna_studies/tesis_v1.db`):

  1. Espacio reducido a 4 dimensiones (las de |ρ| > 0.30 más λ_entropy), en
     vez de 12, para que el estimador de Parzen tenga con qué modelar.
  2. Objetivo = cobertura AoI bajo el protocolo único, no recompensa media.
  3. Objetivo promediado sobre 3 semillas de entrenamiento (42, 123, 777).
  4. Presupuesto igual al horizonte de uso: 200 000 pasos, no 100 000.

Y dos correcciones de implementación descubiertas en la Fase 0:

  5. `eval_freq` y `n_warmup_steps` convertidos a las unidades correctas.
     En `train.py` ambos comparan contra magnitudes de unidades distintas;
     el efecto fue que el EvalCallback del estudio original se disparó UNA
     sola vez por trial (al final) y el warmup del pruner nunca protegió nada.
  6. Retención del mejor punto de control POR COBERTURA, no por recompensa.
     En la Fase 0 el punto retenido por recompensa (160k) dio cobertura
     0.6677 contra 0.6836 del punto final: seleccionar por recompensa da un
     modelo peor en la métrica objetivo.

Esquema de poda en dos etapas
─────────────────────────────
  Etapa 1 — la semilla 42 se entrena con poda intermedia por cobertura,
            activa sólo a partir de los 100 000 pasos (n_warmup_steps).
  Etapa 2 — si sobrevive, su cobertura se compara contra la mediana de las
            coberturas de semilla 42 de las pruebas ya completadas
            (`user_attr` "cob_semilla_42"). Si no la supera, la prueba se poda
            sin gastar las semillas restantes.
  Sólo las pruebas que pasan ambas etapas corren las semillas 123 y 777.

La mediana de la etapa 2 se calcula SÓLO sobre coberturas de semilla 42, nunca
sobre el valor objetivo promediado, para que la comparación sea entre
cantidades homogéneas.

Limitaciones declaradas (van al reporte, no sólo al código)
───────────────────────────────────────────────────────────
  · MUESTREO ASIMÉTRICO. Sólo la semilla 42 reporta a Optuna y sólo ella decide
    la criba. Una configuración con mala suerte en esa semilla muere sin que se
    sepa si era buena en promedio: el estudio NO explora el espacio de forma
    uniforme. Es el precio de la criba de dos etapas y es aceptable, pero sesga
    el muestreo hacia configuraciones afortunadas en la semilla 42 y hay que
    reportarlo como limitación del diseño.
  · RESOLUCIÓN DE LA POSICIÓN DEL MÁXIMO. Con retención cada 20 000 pasos, la
    ubicación del punto retenido tiene resolución de 20k y NO es una estimación
    fina. Además, si el máximo y el segundo mejor de una curva difieren en menos
    que el error estándar de la evaluación, esa curva no tiene máximo
    identificable y no debe entrar en correlaciones contra hiperparámetros:
    sería correlacionar ruido.
  · CV NO COMPARABLE CON H-05. Las tres semillas se evalúan sobre el MISMO
    conjunto de episodios, así que el CV mide variabilidad de entrenamiento
    pura. El 0.589 de H-05 se calculó con episodios distintos por semilla. Para
    comparar, recalcular el CV a la vieja usanza sobre estos mismos modelos
    (no requiere reentrenar).

Sesgo declarado
───────────────
Retener el máximo sobre diez evaluaciones sesga la cobertura al alza: con diez
muestras ruidosas de la misma cantidad el máximo excede al valor esperado aun
sin mejora real. Por eso el punto retenido se re-evalúa con 30 episodios de
semillas DISJUNTAS de las 20 usadas para retenerlo, y ese valor disjunto es el
que entra al objetivo.

CUIDADO al interpretar `sesgo_retencion` (cobertura de retención menos cobertura
final): NO es el sesgo de selección puro. Es la suma de dos efectos —
  (a) el sesgo de selección, que sólo puede ser POSITIVO, y
  (b) la diferencia de dificultad entre los dos conjuntos de episodios, que
      tiene signo propio y es común a todas las pruebas.
De hecho se observan valores negativos, lo que sólo (b) puede explicar. El
componente (a) se acota promediando sobre las pruebas, donde (b) actúa como
desplazamiento común. Reportarlo como "estimación directa del sesgo" sería
incorrecto.

Protocolo de evaluación (único en todo el experimento)
──────────────────────────────────────────────────────
Réplica de `evaluar_cobertura_multimetrica.evaluar_episodio`: episodios
deterministas, `domain_rand=False`, cobertura = 1 − mean(grid_aoi) al final del
episodio. Las TRES semillas de entrenamiento se evalúan sobre el MISMO conjunto
de episodios (semillas 42·10000 + i), de modo que la comparación entre semillas
es pareada — a diferencia de `verificacion_seeds`, donde cada semilla se evaluó
sobre episodios distintos.

Condición de borde: reflexión elástica, igual que el estudio original, para
aislar el efecto de los cambios metodológicos.

No modifica ningún archivo existente ni escribe en `optuna_studies/tesis_v1.db`.

Uso
───
    python estudio_J.py --n_trials 20
    python estudio_J.py --n_trials 20 --reanudar

Autor: José — Tesis Mecatrónica UVG
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from concurrent.futures import ProcessPoolExecutor

import numpy as np
import optuna
from optuna.pruners import MedianPruner
from optuna.samplers import TPESampler

DIR_PADRE = Path(__file__).resolve().parent.parent
if str(DIR_PADRE) not in sys.path:
    sys.path.insert(0, str(DIR_PADRE))

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback

from swarm_env_skeleton import D_SAFE, make_env
from train import (
    ConfigEntorno,
    ConfigEntrenamiento,
    HiperparametrosPPO,
    PesosRecompensa,
    construir_modelo_ppo,
    construir_vec_env_entrenamiento,
)

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════════

# Gancho de prueba: EXPJ_PRESUPUESTO permite correr el flujo completo con un
# presupuesto diminuto para verificar la fontanería sin gastar una corrida real.
PRESUPUESTO_PASOS:   int = int(os.environ.get("EXPJ_PRESUPUESTO", 200_000))
FRECUENCIA_EVAL_TS:  int = int(os.environ.get("EXPJ_FREQ_EVAL", 20_000))  # → 10 evaluaciones
N_EPS_RETENCION:     int = 20            # episodios por evaluación de retención
N_EPS_FINAL:         int = 30            # episodios de la evaluación final
OFFSET_SEMILLAS_FINAL: int = 1_000       # hace disjuntos los episodios finales
N_ENVS_ENTREN:       int = 4
WARMUP_PODA_TS:      int = 100_000       # no podar antes de 100k pasos
N_STARTUP_TRIALS:    int = 5
MIN_TRIALS_CRIBA:    int = 5             # mínimo para aplicar la etapa 2
# Trabajadores del pool de evaluación. 5 es el óptimo medido (3.08x sobre
# secuencial); más procesos empeoran por contención. Se baja a 3 en los
# trabajadores de confirmación, que corren de a dos a la vez.
N_TRABAJADORES_EVAL: int = int(os.environ.get("EXPJ_WORKERS_EVAL", 5))

SEMILLAS_ENTREN: Tuple[int, ...] = (42, 123, 777)
SEMILLA_PRIMARIA: int = SEMILLAS_ENTREN[0]
SEMILLA_EPISODIOS: int = 42              # base del conjunto de episodios de eval

MAX_STEPS_EP: int   = 500
N_AGENTES:    int   = 5
ARENA:        tuple = (3.0, 3.0)
COMM_RADIUS:  float = 1.0

DIR_BASE:    Path = Path(__file__).resolve().parent
DIR_SALIDA:  Path = DIR_BASE / "resultados" / "estudio"
DIR_STORAGE: Path = DIR_BASE / "optuna_studies"
NOMBRE_ESTUDIO: str = "experimento_J"

# ── Valores fijos, tomados del Trial 13 ───────────────────────────────────────
# (modelos/tesis_v1/RESULTADO_PRIMERO/hiperparametros.json)
HPARAMS_FIJOS: Dict[str, float] = {
    "learning_rate": 6.855028382061343e-05,
    "gamma":         0.9844980522475681,
    "clip_range":    0.20631649325745388,
    "batch_size":    64,
    "ent_coef":      0.022872258876193912,
    "gae_lambda":    0.9608422073341644,
    "vf_coef":       0.5,
    "max_grad_norm": 0.5,
}
PESOS_FIJOS: Dict[str, float] = {
    "lambda_gradient": 0.5622468083379316,
    "lambda_ibrm":     0.48380314172632155,
}

logger = logging.getLogger("estudio_J")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
    ))
    logger.addHandler(_h)


# ══════════════════════════════════════════════════════════════════════════════
#  ESPACIO DE BÚSQUEDA (4 dimensiones)
# ══════════════════════════════════════════════════════════════════════════════

def sugerir_configuracion(
    trial: optuna.Trial,
) -> Tuple[HiperparametrosPPO, PesosRecompensa, Dict[str, Any]]:
    """
    Sugiere los cuatro hiperparámetros barridos y completa el resto con los
    valores del Trial 13.

    Los rangos son idénticos a los del estudio original para que las
    correlaciones de rango de ambos estudios sean comparables.

    Retorna
    -------
    (hparams, pesos, dict con los cuatro valores barridos)
    """
    lambda_cbf   = trial.suggest_float("lambda_cbf", 1.0, 15.0)
    lambda_ent   = trial.suggest_float("lambda_entropy", 0.1, 2.0)
    n_epochs     = trial.suggest_int("n_epochs", 3, 15)
    n_steps_exp  = trial.suggest_int("n_steps_exp", 6, 10)

    return materializar_configuracion(lambda_cbf, lambda_ent, n_epochs, n_steps_exp)


def materializar_configuracion(
    lambda_cbf:  float,
    lambda_ent:  float,
    n_epochs:    int,
    n_steps_exp: int,
) -> Tuple[HiperparametrosPPO, PesosRecompensa, Dict[str, Any]]:
    """
    Construye la configuración completa a partir de los cuatro valores barridos.

    Separada de `sugerir_configuracion` porque los procesos trabajadores que
    corren las semillas de confirmación en paralelo reciben los cuatro valores
    por archivo, no un `optuna.Trial`, y deben reconstruir EXACTAMENTE la misma
    configuración.
    """
    hparams = HiperparametrosPPO(
        learning_rate = HPARAMS_FIJOS["learning_rate"],
        gamma         = HPARAMS_FIJOS["gamma"],
        clip_range    = HPARAMS_FIJOS["clip_range"],
        n_steps       = 2 ** n_steps_exp,
        batch_size    = int(HPARAMS_FIJOS["batch_size"]),
        n_epochs      = n_epochs,
        ent_coef      = HPARAMS_FIJOS["ent_coef"],
        gae_lambda    = HPARAMS_FIJOS["gae_lambda"],
        vf_coef       = HPARAMS_FIJOS["vf_coef"],
        max_grad_norm = HPARAMS_FIJOS["max_grad_norm"],
    )
    pesos = PesosRecompensa(
        lambda_gradient = PESOS_FIJOS["lambda_gradient"],
        lambda_entropy  = lambda_ent,
        lambda_ibrm     = PESOS_FIJOS["lambda_ibrm"],
        lambda_cbf      = lambda_cbf,
    )
    barridos = {
        "lambda_cbf":     lambda_cbf,
        "lambda_entropy": lambda_ent,
        "n_epochs":       n_epochs,
        "n_steps_exp":    n_steps_exp,
        "n_steps":        2 ** n_steps_exp,
    }
    return hparams, pesos, barridos


# ══════════════════════════════════════════════════════════════════════════════
#  PROTOCOLO ÚNICO DE EVALUACIÓN
# ══════════════════════════════════════════════════════════════════════════════

def evaluar_episodio(modelo: PPO, env, seed_ep: int) -> Dict[str, float]:
    """
    Corre UN episodio determinista y devuelve las métricas del protocolo único.

    `n_colisiones` es el número de PARES distintos que estuvieron a menos de
    `D_SAFE` en algún instante del episodio (0..10 con 5 agentes). Se mide sobre
    la política DESNUDA, sin filtro CBF de ejecución ni comportamiento de escape;
    no es el criterio de viabilidad del sistema desplegado, que se mide sobre la
    configuración completa.
    """
    obs_dict, _ = env.reset(seed=seed_ep)
    agents = list(obs_dict.keys())
    n_agents = len(agents)

    cobertura_hist: List[float] = []
    pares_colision: set = set()

    done = False
    while not done:
        obs_array   = np.stack([obs_dict[a] for a in agents])
        acciones, _ = modelo.predict(obs_array, deterministic=True)
        accion_dict = {a: acciones[i] for i, a in enumerate(agents)}
        obs_dict, _, term, trunc, _ = env.step(accion_dict)

        cobertura_hist.append(1.0 - float(np.mean(env._field._grid_aoi)))

        pos_curr = np.array([env._estados[a][:2] for a in agents])
        for i in range(n_agents):
            for j in range(i + 1, n_agents):
                if np.linalg.norm(pos_curr[i] - pos_curr[j]) < D_SAFE:
                    pares_colision.add((i, j))

        done = all(trunc.values()) or all(term.values())

    cob_np    = np.asarray(cobertura_hist)
    idx_cross = np.where(cob_np >= 0.5)[0]

    return {
        "cobertura_aoi_final":            cobertura_hist[-1] if cobertura_hist else 0.0,
        "n_colisiones":                   float(len(pares_colision)),
        "tiempo_primera_cobertura_50pct": float(idx_cross[0]) if len(idx_cross) else float(MAX_STEPS_EP),
    }


def crear_env_evaluacion(pesos: PesosRecompensa):
    """Entorno crudo de PettingZoo para el protocolo de evaluación."""
    return make_env(
        n_agents       = N_AGENTES,
        arena_size     = ARENA,
        max_steps      = MAX_STEPS_EP,
        comm_radius    = COMM_RADIUS,
        reward_weights = {
            "lambda_gradient": pesos.lambda_gradient,
            "lambda_entropy":  pesos.lambda_entropy,
            "lambda_ibrm":     pesos.lambda_ibrm,
            "lambda_cbf":      pesos.lambda_cbf,
        },
        domain_rand    = False,
        seed           = SEMILLA_EPISODIOS,
    )


def evaluar_modelo(
    modelo:      PPO,
    env,
    n_episodios: int,
    offset:      int = 0,
) -> Dict[str, Any]:
    """
    Evalúa `modelo` sobre `n_episodios` episodios deterministas con semillas
    `SEMILLA_EPISODIOS·10000 + offset + i`.

    El `offset` permite hacer disjuntos los episodios de la evaluación final
    respecto de los usados para retener el punto de control.
    """
    episodios = [
        evaluar_episodio(modelo, env, seed_ep=SEMILLA_EPISODIOS * 10_000 + offset + i)
        for i in range(n_episodios)
    ]
    return _agregar_episodios(episodios)


# ── Evaluación repartida entre procesos ───────────────────────────────────────
# Los episodios son independientes: cada uno queda determinado por su semilla,
# `env.reset(seed=...)`. Repartirlos entre procesos no cambia ningún número, sólo
# quién los ejecuta. (Verificado contra el resultado secuencial de la prueba 0.)
#
# El pool se crea UNA vez por semilla y se reutiliza en las once evaluaciones,
# porque levantar procesos en Windows cuesta varios segundos: crearlo en cada
# evaluación se comería el ahorro.

_ENV_TRABAJADOR = None          # entorno propio de cada proceso trabajador
_MODELO_TRABAJADOR: Dict[str, Any] = {}   # caché {ruta: (mtime, modelo)}


def _iniciar_trabajador_eval(pesos_dict: Dict[str, float]) -> None:
    """Inicializador del pool: crea el entorno de evaluación una sola vez."""
    global _ENV_TRABAJADOR
    import logging as _logging
    _logging.disable(_logging.INFO)
    # Un hilo por trabajador. Sin esto cada proceso abre 8 hilos de torch y se
    # pelean por los mismos núcleos: con 5 trabajadores serían 40 hilos en 12
    # núcleos, y la contención se come casi toda la ganancia del paralelismo.
    # La inferencia es una MLP 256×256 sobre lotes de 5: no necesita hilos.
    import torch as _torch
    _torch.set_num_threads(1)
    _ENV_TRABAJADOR = make_env(
        n_agents=N_AGENTES, arena_size=ARENA, max_steps=MAX_STEPS_EP,
        comm_radius=COMM_RADIUS, reward_weights=pesos_dict,
        domain_rand=False, seed=SEMILLA_EPISODIOS,
    )


def _evaluar_lote(tarea: Tuple[str, int, List[int]]) -> List[Dict[str, float]]:
    """
    Corre un lote de episodios en el proceso trabajador.

    El modelo se cachea por (ruta, mtime): durante una misma evaluación todos
    los lotes comparten el archivo, así que se carga una vez por trabajador.
    """
    ruta_modelo, offset, indices = tarea
    mtime = Path(ruta_modelo).stat().st_mtime
    cacheado = _MODELO_TRABAJADOR.get(ruta_modelo)
    if cacheado is None or cacheado[0] != mtime:
        _MODELO_TRABAJADOR[ruta_modelo] = (mtime, PPO.load(ruta_modelo, device="cpu"))
    modelo = _MODELO_TRABAJADOR[ruta_modelo][1]

    return [
        evaluar_episodio(modelo, _ENV_TRABAJADOR,
                         seed_ep=SEMILLA_EPISODIOS * 10_000 + offset + i)
        for i in indices
    ]


def evaluar_modelo_en_paralelo(
    ruta_modelo: Path,
    pool,
    n_episodios: int,
    offset:      int = 0,
) -> Dict[str, Any]:
    """
    Igual que `evaluar_modelo`, pero repartiendo los episodios entre los
    procesos de `pool`. Devuelve los episodios en el ORDEN original, para que
    el JSON por semilla sea idéntico al de la versión secuencial.
    """
    n_trabajadores = pool._max_workers
    lotes: List[List[int]] = [[] for _ in range(n_trabajadores)]
    for i in range(n_episodios):
        lotes[i % n_trabajadores].append(i)   # reparto round-robin

    tareas = [(str(ruta_modelo), offset, lote) for lote in lotes if lote]
    resultados_por_lote = list(pool.map(_evaluar_lote, tareas))

    # Reordenar: el lote k contiene los índices k, k+n, k+2n, ...
    episodios: List[Optional[Dict[str, float]]] = [None] * n_episodios
    for lote, resultados in zip([l for l in lotes if l], resultados_por_lote):
        for indice, metrica in zip(lote, resultados):
            episodios[indice] = metrica

    return _agregar_episodios([e for e in episodios if e is not None])


def _agregar_episodios(episodios: List[Dict[str, float]]) -> Dict[str, Any]:
    """Agrega las métricas por episodio, sin redondear."""
    agregados: Dict[str, Any] = {}
    for clave in ("cobertura_aoi_final", "n_colisiones", "tiempo_primera_cobertura_50pct"):
        v = np.array([e[clave] for e in episodios], dtype=float)
        agregados[clave] = {
            "media": float(v.mean()),
            "std":   float(v.std(ddof=1)) if len(v) > 1 else 0.0,
            "min":   float(v.min()),
            "max":   float(v.max()),
        }
    return {"agregados": agregados, "episodios": episodios}


# ══════════════════════════════════════════════════════════════════════════════
#  CALLBACK DE RETENCIÓN Y PODA POR COBERTURA
# ══════════════════════════════════════════════════════════════════════════════

class CallbackCoberturaJ(BaseCallback):
    """
    Cada `FRECUENCIA_EVAL_TS` pasos de entorno:

      1. Evalúa la cobertura AoI con el protocolo único (`N_EPS_RETENCION`
         episodios deterministas).
      2. Retiene el punto de control si supera al mejor visto — retención POR
         COBERTURA, que es la métrica objetivo, no por recompensa.
      3. Si es la semilla primaria, reporta a Optuna y solicita poda.

    La conversión de unidades es explícita: `EvalCallback`/`BaseCallback` cuentan
    LLAMADAS (`n_calls`), y cada llamada avanza `num_envs` pasos de entorno.
    """

    def __init__(
        self,
        env_eval,
        pool,
        ruta_mejor:      Path,
        frecuencia_ts:   int,
        num_envs:        int,
        trial:           Optional[optuna.Trial] = None,
        verbose:         int = 0,
    ) -> None:
        super().__init__(verbose=verbose)
        self.env_eval        = env_eval
        self.pool            = pool
        self.ruta_mejor      = ruta_mejor
        # El modelo vive en memoria, pero los trabajadores necesitan un archivo.
        # Se vuelca a esta ruta antes de cada evaluación y, si resulta ser el
        # mejor, se copia a `ruta_mejor`.
        self.ruta_tmp        = ruta_mejor.parent / "_punto_control_actual.zip"
        self.frecuencia_lla  = max(1, frecuencia_ts // num_envs)
        self.trial           = trial
        self.mejor_cobertura: float = -np.inf
        self.mejor_paso:      int   = 0
        self.curva:      List[Dict[str, float]] = []
        self.segundos_evaluando: float = 0.0

    def _on_step(self) -> bool:
        if self.n_calls % self.frecuencia_lla != 0:
            return True

        t_ini = time.time()
        self.ruta_tmp.parent.mkdir(parents=True, exist_ok=True)
        self.model.save(str(self.ruta_tmp))
        res = evaluar_modelo_en_paralelo(self.ruta_tmp, self.pool, N_EPS_RETENCION, offset=0)
        self.segundos_evaluando += time.time() - t_ini

        cobertura  = res["agregados"]["cobertura_aoi_final"]["media"]
        colisiones = res["agregados"]["n_colisiones"]["media"]

        self.curva.append({
            "pasos":      int(self.num_timesteps),
            "cobertura":  cobertura,
            "colisiones": colisiones,
        })

        if cobertura > self.mejor_cobertura:
            self.mejor_cobertura = cobertura
            self.mejor_paso      = int(self.num_timesteps)
            self.ruta_mejor.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.ruta_tmp, self.ruta_mejor)

        if self.verbose >= 1:
            logger.info(
                "    paso %6d — cob=%.8f  col=%.3f%s",
                self.num_timesteps, cobertura, colisiones,
                "  ← retenido" if self.mejor_paso == self.num_timesteps else "",
            )

        # ── Poda intermedia: sólo la semilla primaria reporta ──────────────
        if self.trial is not None:
            self.trial.report(cobertura, step=int(self.num_timesteps))
            if self.trial.should_prune():
                logger.info(
                    "  Prueba %d podada (etapa 1) en el paso %d, cobertura %.8f",
                    self.trial.number, self.num_timesteps, cobertura,
                )
                raise optuna.exceptions.TrialPruned()

        return True


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRENAMIENTO Y EVALUACIÓN DE UNA SEMILLA
# ══════════════════════════════════════════════════════════════════════════════

def correr_semilla(
    hparams:      HiperparametrosPPO,
    pesos:        PesosRecompensa,
    semilla:      int,
    dir_semilla:  Path,
    trial:        Optional[optuna.Trial],
) -> Dict[str, Any]:
    """
    Entrena una semilla por `PRESUPUESTO_PASOS`, reteniendo el punto de control
    de mayor cobertura, y lo re-evalúa con episodios disjuntos.

    `trial` distinto de None activa la poda intermedia (sólo semilla primaria).
    """
    dir_semilla.mkdir(parents=True, exist_ok=True)

    # ── Reanudación fina: una semilla ya terminada no se repite ────────────
    # El directorio de la prueba se nombra por el HASH de la configuración, no
    # por el número de prueba, porque al reanudar Optuna asigna números nuevos.
    # Así, una interrupción a mitad de la semilla 123 no obliga a rehacer la 42.
    ruta_json = dir_semilla / "resultado_semilla.json"
    if ruta_json.exists():
        resultado = json.loads(ruta_json.read_text(encoding="utf-8"))
        logger.info(
            "  semilla %d — REUTILIZADA de %s (cob_final=%.8f)",
            semilla, ruta_json, resultado["cobertura_final"],
        )
        return resultado

    config_env = ConfigEntorno(
        n_agentes    = N_AGENTES,
        arena_size   = ARENA,
        max_steps_ep = MAX_STEPS_EP,
        radio_com    = COMM_RADIUS,
        domain_rand  = True,
    )
    config_train = ConfigEntrenamiento(seed=semilla)

    env_train = construir_vec_env_entrenamiento(
        config_env   = config_env,
        config_train = config_train,
        pesos_rew    = pesos,
        n_envs       = N_ENVS_ENTREN,
        seed         = semilla,
    )
    env_eval = crear_env_evaluacion(pesos)
    ruta_mejor = dir_semilla / "mejor_punto_control.zip"

    # Pool de evaluación: se crea UNA vez por semilla y se reutiliza en las once
    # evaluaciones. Levantar procesos en Windows cuesta segundos; crearlo en
    # cada evaluación se comería el ahorro.
    pesos_dict = {
        "lambda_gradient": pesos.lambda_gradient,
        "lambda_entropy":  pesos.lambda_entropy,
        "lambda_ibrm":     pesos.lambda_ibrm,
        "lambda_cbf":      pesos.lambda_cbf,
    }
    pool = ProcessPoolExecutor(
        max_workers = N_TRABAJADORES_EVAL,
        initializer = _iniciar_trabajador_eval,
        initargs    = (pesos_dict,),
    )

    try:
        modelo = construir_modelo_ppo(
            env             = env_train,
            hparams         = hparams,
            config_train    = config_train,
            dir_tensorboard = None,
            seed            = semilla,
            verbose         = 0,
        )
        cb = CallbackCoberturaJ(
            env_eval      = env_eval,
            pool          = pool,
            ruta_mejor    = ruta_mejor,
            frecuencia_ts = FRECUENCIA_EVAL_TS,
            num_envs      = env_train.num_envs,
            trial         = trial,
            verbose       = 1,
        )
        t_ini = time.time()
        modelo.learn(
            total_timesteps     = PRESUPUESTO_PASOS,
            callback            = cb,
            reset_num_timesteps = True,
            progress_bar        = False,
        )
        seg_total = time.time() - t_ini

        # ── Evaluación final con episodios DISJUNTOS (des-sesgo) ───────────
        res_final = evaluar_modelo_en_paralelo(
            ruta_mejor, pool, N_EPS_FINAL, offset=OFFSET_SEMILLAS_FINAL
        )
        cob_final = res_final["agregados"]["cobertura_aoi_final"]["media"]

        resultado = {
            "semilla":              semilla,
            "curva":                cb.curva,
            "paso_retenido":        cb.mejor_paso,
            "cobertura_retencion":  cb.mejor_cobertura,
            "cobertura_final":      cob_final,
            "sesgo_retencion":      cb.mejor_cobertura - cob_final,
            "colisiones_final":     res_final["agregados"]["n_colisiones"]["media"],
            "agregados_final":      res_final["agregados"],
            "segundos_total":       seg_total,
            "segundos_evaluando":   cb.segundos_evaluando,
        }
        (dir_semilla / "resultado_semilla.json").write_text(
            json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info(
            "  semilla %d — retenido en %d, cob_ret=%.8f, cob_final=%.8f (sesgo %+.8f), col=%.3f",
            semilla, cb.mejor_paso, cb.mejor_cobertura, cob_final,
            resultado["sesgo_retencion"], resultado["colisiones_final"],
        )
        return resultado

    finally:
        pool.shutdown(wait=True)
        try:
            env_train.close()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
#  FUNCIÓN OBJETIVO
# ══════════════════════════════════════════════════════════════════════════════

def correr_semillas_en_paralelo(
    barridos:    Dict[str, Any],
    semillas:    Tuple[int, ...],
    dir_prueba:  Path,
) -> None:
    """
    Lanza una semilla por proceso y espera a que todas terminen.

    Por qué subprocesos y no un pool de hilos o `multiprocessing`: cada semilla
    ya levanta su propio `ProcConcatVec` con 4 procesos de entorno, y anidar
    pools sobre Windows (que usa `spawn`, no `fork`) es frágil. Un subproceso
    por semilla es la forma más simple que no puede corromper el estado del
    padre: cada trabajador escribe su `resultado_semilla.json` y el padre lo
    recoge con el mismo mecanismo de reanudación que ya existía.

    Si un trabajador falla, no se lanza excepción aquí: el JSON no existirá y
    `correr_semilla` reentrenará esa semilla en el padre, en serie. Se degrada
    en lentitud, no en corrección.
    """
    ruta_config = dir_prueba / "config_barridos.json"
    ruta_config.write_text(json.dumps(barridos, indent=2), encoding="utf-8")

    procesos: List[Tuple[int, Any]] = []
    for semilla in semillas:
        dir_semilla = dir_prueba / f"semilla_{semilla}"
        if (dir_semilla / "resultado_semilla.json").exists():
            continue  # ya estaba hecha (reanudación)
        cmd = [
            sys.executable, "-u", str(Path(__file__).resolve()),
            "--worker_semilla", str(semilla),
            "--worker_dir",     str(dir_semilla),
            "--worker_config",  str(ruta_config),
        ]
        registro = open(dir_prueba / f"worker_semilla_{semilla}.log", "w", encoding="utf-8")
        entorno = dict(os.environ)
        # Dos semillas a la vez, cada una con su pool: se reparte el presupuesto
        # de núcleos para no sobresuscribir la máquina.
        entorno["EXPJ_WORKERS_EVAL"] = str(max(2, N_TRABAJADORES_EVAL // len(semillas)))
        procesos.append((semilla, subprocess.Popen(
            cmd, stdout=registro, stderr=subprocess.STDOUT, env=entorno)))
        logger.info("  lanzado trabajador para la semilla %d (PID %d)",
                    semilla, procesos[-1][1].pid)

    for semilla, proc in procesos:
        codigo = proc.wait()
        if codigo != 0:
            logger.warning(
                "  el trabajador de la semilla %d terminó con código %d; "
                "se reintentará en serie", semilla, codigo,
            )


def clave_configuracion(barridos: Dict[str, Any]) -> str:
    """
    Hash estable de los cuatro hiperparámetros barridos.

    Nombra el directorio de la prueba. Al reanudar, Optuna asigna números de
    prueba nuevos, de modo que nombrar por `trial.number` rompería la
    reutilización de semillas ya terminadas; el hash de la configuración no
    depende de la numeración.
    """
    canonico = json.dumps(
        {k: barridos[k] for k in sorted(("lambda_cbf", "lambda_entropy",
                                         "n_epochs", "n_steps_exp"))},
        sort_keys=True,
    )
    return hashlib.sha1(canonico.encode("utf-8")).hexdigest()[:10]


def mediana_semilla_primaria(estudio: optuna.Study) -> Optional[float]:
    """
    Mediana de las coberturas de la semilla primaria entre las pruebas ya
    completadas. Devuelve None si aún no hay suficientes para cribar.

    Se calcula SÓLO sobre `cob_semilla_42` — nunca sobre el valor objetivo
    promediado — para comparar cantidades homogéneas.
    """
    valores = [
        t.user_attrs["cob_semilla_42"]
        for t in estudio.get_trials(deepcopy=False)
        if t.state == optuna.trial.TrialState.COMPLETE
        and "cob_semilla_42" in t.user_attrs
    ]
    if len(valores) < MIN_TRIALS_CRIBA:
        return None
    return float(np.median(valores))


def objetivo(trial: optuna.Trial) -> float:
    """
    Valor objetivo: media de la cobertura AoI final sobre las semillas corridas.

    Las colisiones NO se usan como restricción dura: se registran como
    `user_attr` y el umbral de descarte se calibra a posteriori sobre la
    distribución observada. La política desnuda de referencia da ~0.21
    colisiones/episodio; la seguridad del sistema desplegado la aporta la capa
    de filtrado CBF + escape, no la sintonización.
    """
    hparams, pesos, barridos = sugerir_configuracion(trial)
    dir_prueba = DIR_SALIDA / f"cfg_{clave_configuracion(barridos)}"
    dir_prueba.mkdir(parents=True, exist_ok=True)

    for clave, valor in barridos.items():
        trial.set_user_attr(clave, valor)

    logger.info(
        "Prueba %d — λ_cbf=%.4f  λ_ent=%.4f  n_epochs=%d  n_steps=%d",
        trial.number, barridos["lambda_cbf"], barridos["lambda_entropy"],
        barridos["n_epochs"], barridos["n_steps"],
    )

    resultados: List[Dict[str, Any]] = []

    # ── Etapa 1: semilla primaria, con poda intermedia ─────────────────────
    res = correr_semilla(
        hparams, pesos, SEMILLA_PRIMARIA,
        dir_prueba / f"semilla_{SEMILLA_PRIMARIA}", trial=trial,
    )
    resultados.append(res)
    trial.set_user_attr("cob_semilla_42", res["cobertura_final"])

    # ── Etapa 2: criba por mediana antes de gastar las demás semillas ──────
    mediana = mediana_semilla_primaria(trial.study)
    if mediana is not None and res["cobertura_final"] < mediana:
        logger.info(
            "  Prueba %d podada (etapa 2): cob semilla 42 %.8f < mediana %.8f",
            trial.number, res["cobertura_final"], mediana,
        )
        _guardar_resultado_prueba(dir_prueba, trial, barridos, resultados, podada="etapa_2")
        raise optuna.exceptions.TrialPruned()

    # ── Semillas de confirmación, EN PARALELO ──────────────────────────────
    # Se lanzan como procesos independientes: no se comunican entre sí ni con
    # el padre durante la corrida, así que el escalado es casi lineal. La criba
    # queda intacta porque esto ocurre DESPUÉS de que la semilla 42 sobrevivió
    # a las dos etapas.
    correr_semillas_en_paralelo(barridos, SEMILLAS_ENTREN[1:], dir_prueba)
    for semilla in SEMILLAS_ENTREN[1:]:
        # Ya terminadas por los trabajadores: `correr_semilla` las reutiliza
        # del JSON en vez de reentrenar.
        resultados.append(
            correr_semilla(hparams, pesos, semilla, dir_prueba / f"semilla_{semilla}", trial=None)
        )

    coberturas = np.array([r["cobertura_final"] for r in resultados], dtype=float)
    colisiones = np.array([r["colisiones_final"] for r in resultados], dtype=float)
    media = float(coberturas.mean())
    desv  = float(coberturas.std(ddof=1)) if len(coberturas) > 1 else 0.0

    trial.set_user_attr("cobertura_media",     media)
    trial.set_user_attr("cobertura_std",       desv)
    trial.set_user_attr("cobertura_cv",        desv / media if media > 0 else float("nan"))
    trial.set_user_attr("colisiones_media",    float(colisiones.mean()))
    trial.set_user_attr("sesgo_retencion_medio",
                        float(np.mean([r["sesgo_retencion"] for r in resultados])))
    trial.set_user_attr("pasos_retenidos",
                        [r["paso_retenido"] for r in resultados])

    _guardar_resultado_prueba(dir_prueba, trial, barridos, resultados, podada=None)

    logger.info(
        "Prueba %d COMPLETA — cobertura %.8f ± %.8f (CV %.4f), colisiones %.3f",
        trial.number, media, desv, desv / media if media > 0 else float("nan"),
        float(colisiones.mean()),
    )
    return media


def _guardar_resultado_prueba(
    dir_prueba:  Path,
    trial:       optuna.Trial,
    barridos:    Dict[str, Any],
    resultados:  List[Dict[str, Any]],
    podada:      Optional[str],
) -> None:
    """Vuelca a JSON todo lo medido en la prueba, podada o no."""
    payload = {
        "prueba":      trial.number,
        "barridos":    barridos,
        "hparams_fijos": HPARAMS_FIJOS,
        "pesos_fijos":   PESOS_FIJOS,
        "podada":      podada,
        "semillas":    resultados,
    }
    (dir_prueba / "resultado_prueba.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="Experimento J — estudio de sintonización")
    parser.add_argument("--n_trials", type=int, default=20)
    parser.add_argument("--reanudar", action="store_true",
                        help="Continuar un estudio existente en vez de crearlo")
    # Modo trabajador: corre UNA semilla de confirmación y termina. No toca la
    # base de Optuna ni participa de la poda.
    parser.add_argument("--worker_semilla", type=int, default=None)
    parser.add_argument("--worker_dir",     type=str, default=None)
    parser.add_argument("--worker_config",  type=str, default=None)
    args = parser.parse_args()

    if args.worker_semilla is not None:
        barridos = json.loads(Path(args.worker_config).read_text(encoding="utf-8"))
        hparams, pesos, _ = materializar_configuracion(
            lambda_cbf  = barridos["lambda_cbf"],
            lambda_ent  = barridos["lambda_entropy"],
            n_epochs    = barridos["n_epochs"],
            n_steps_exp = barridos["n_steps_exp"],
        )
        correr_semilla(hparams, pesos, args.worker_semilla,
                       Path(args.worker_dir), trial=None)
        return

    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    DIR_STORAGE.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{DIR_STORAGE / (NOMBRE_ESTUDIO + '.db')}"

    estudio = optuna.create_study(
        study_name = NOMBRE_ESTUDIO,
        storage    = url,
        direction  = "maximize",
        sampler    = TPESampler(n_startup_trials=N_STARTUP_TRIALS, seed=SEMILLA_PRIMARIA),
        pruner     = MedianPruner(
            n_startup_trials = N_STARTUP_TRIALS,
            # En las MISMAS unidades que el `step` reportado (pasos de entorno).
            n_warmup_steps   = WARMUP_PODA_TS,
            interval_steps   = 1,
        ),
        load_if_exists = args.reanudar,
    )

    logger.info("Estudio %s — %d pruebas, %d semillas, %d pasos por semilla",
                NOMBRE_ESTUDIO, args.n_trials, len(SEMILLAS_ENTREN), PRESUPUESTO_PASOS)
    t_ini = time.time()
    estudio.optimize(objetivo, n_trials=args.n_trials, gc_after_trial=True)
    horas = (time.time() - t_ini) / 3600.0

    logger.info("Estudio terminado en %.2f h — mejor valor %.8f", horas, estudio.best_value)
    logger.info("Mejores parámetros: %s", estudio.best_params)

    estudio.trials_dataframe().to_csv(DIR_SALIDA / "pruebas.csv", index=False)
    (DIR_SALIDA / "mejor_configuracion.json").write_text(
        json.dumps({
            "mejor_valor":  estudio.best_value,
            "mejores_params": estudio.best_params,
            "user_attrs":   estudio.best_trial.user_attrs,
            "horas":        horas,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
