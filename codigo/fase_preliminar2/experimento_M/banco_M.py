"""
banco_M.py — Experimento M: punto de cruce CPU/GPU del ENTRENAMIENTO.

Banco de tiempos, no corrida de entrenamiento. Mide el costo de UN paso de
gradiente de PPO (la unidad de trabajo de `PPO.train()`) en función del tamaño
de minilote B y del ancho de la red, en una de las tres condiciones del Exp L:

  gpu          : venv_lab4, torch 2.11.0+cu128, device="cuda"
  cpu_control  : venv_lab4, torch 2.11.0+cu128, device="cpu"   ← el CONTROL
  referencia   : intérprete de la tesis, torch 2.10.0+cpu, device="cpu"

Por qué un paso aislado y no `train()` completo
-----------------------------------------------
El búfer de la configuración de la tesis es de 2560 transiciones
(128 pasos × 4 entornos × 5 agentes): los minilotes de 4096 y 8192 no existen
en él, y SB3 deja un último minilote truncado cuando B no divide al búfer, lo
que sesga cualquier promedio "por minilote" sacado de `train()`. El banco
cronometra pasos individuales sobre rebanadas de tamaño B de un búfer REAL de
10 240 transiciones (fase `poblar`), así que B es libre y cada punto del
barrido mide exactamente la misma operación.

Qué es "un paso" — réplica literal de `PPO.train()` de SB3 2.7.1
----------------------------------------------------------------
  1. `_get_samples`: indexado NumPy del búfer (vive en memoria del sistema) y
     `th.tensor(arr, device=...)` de los seis arreglos → copia anfitrión→
     dispositivo POR MINILOTE, síncrona y sin memoria anclada.
  2. `policy.evaluate_actions`, normalización de ventaja, pérdida recortada,
     pérdida de valor, entropía, KL aproximada.
  3. Las cinco sincronizaciones de SB3: cuatro `.item()` y un `.cpu().numpy()`.
  4. `zero_grad`, `backward`, `clip_grad_norm_`, `optimizer.step()`.

Dos modos de acceso a los datos (la descomposición mecanística):
  desde_sistema : el paso 1 dentro de la región cronometrada. Es lo que SB3
                  hace de verdad. Es el modo del barrido principal.
  residente     : los seis arreglos ya son tensores en la GPU; el paso 1 se
                  reduce a indexarlos allí. Contrafáctico. SÓLO TIENE SENTIDO
                  EN LA GPU: en CPU los datos ya están en memoria del sistema
                  y no hay transferencia que descontar, así que no se mide.

Verificación de control del banco (condición de PARADA)
-------------------------------------------------------
Con la arquitectura de la tesis, B = 64 y el búfer de 2560, se corre también
`PPO.train()` REAL (13 épocas × 40 = 520 minilotes) y se compara
train()/520 contra la mediana del banco a B = 64 en el mismo proceso. Si
difieren más de TOL_CONTROL_BANCO, el banco no mide lo que mide SB3 y el
proceso termina con código 3 sin escribir el barrido.

No modifica nada de `fase_preliminar2/` ni de `experimento_L/`: importa
`comun_L` y `train_L` en modo de sólo lectura.

Uso (una condición por invocación; NUNCA dos a la vez):
  tesis     : python banco_M.py --fase poblar --condicion referencia --dispositivo cpu
  venv_lab4 : python banco_M.py --fase medir  --condicion gpu         --dispositivo cuda --sufijo rep1
  venv_lab4 : python banco_M.py --fase medir  --condicion cpu_control --dispositivo cpu  --sufijo rep1
  tesis     : python banco_M.py --fase medir  --condicion referencia  --dispositivo cpu  --sufijo rep1
  refinamiento del cruce (sin control, puntos intermedios):
            python banco_M.py --fase medir ... --minilotes 2560 3072 3584 \
                              --arquitecturas 256x256 --sin_control --sufijo refino_rep1

Autor: José — Tesis Mecatrónica UVG
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

DIR_M: Path = Path(__file__).resolve().parent
DIR_L: Path = DIR_M.parent / "experimento_L"
if str(DIR_L) not in sys.path:
    sys.path.insert(0, str(DIR_L))

import torch                                   # noqa: E402
import torch.nn.functional as F                # noqa: E402

from comun_L import (                          # noqa: E402
    ARENA, COMM_RADIUS, HPARAMS_TRIAL13, MAX_STEPS_EP, N_AGENTES, PESOS_TRIAL13,
    SEMILLA, MonitorCargaCPU, declarar_hardware, escribir_csv,
    respaldar_si_existe, validar_condicion,
)
from train_L import (                          # noqa: E402
    ConfigEntorno, ConfigEntrenamiento, HiperparametrosPPO, PesosRecompensa,
    construir_modelo_ppo, construir_vec_env_entrenamiento,
)
from stable_baselines3.common.buffers import RolloutBuffer   # noqa: E402
from stable_baselines3.common.logger import configure         # noqa: E402

# ── Constantes del diseño ─────────────────────────────────────────────────────
DIR_RESULTADOS: Path = DIR_M / "resultados"
RUTA_BUFER:     Path = DIR_RESULTADOS / "bufer_poblado_10240.npz"

N_ENVS:          int = 4                      # como el Exp L y el estudio original
N_STEPS_TESIS:   int = int(HPARAMS_TRIAL13["n_steps"])      # 128
N_STEPS_POBLAR:  int = 512                    # 512 × 20 flujos = 10 240 transiciones
MB_POR_EPOCA:    int = 40                     # 2560 / 64: se mantiene fijo en la traducción
N_EPOCHS:        int = int(HPARAMS_TRIAL13["n_epochs"])     # 13

MINILOTES_BASE:   Tuple[int, ...] = (64, 128, 256, 512, 1024, 2048, 4096, 8192)
ARQUITECTURAS:    Tuple[str, ...] = ("256x256", "512x512", "1024x1024")
ARQ_TESIS:        str = "256x256"

CALENTAMIENTO:    int = 50      # pasos descartados por celda (kernels, cachés, relojes)
REPS_PEQUENO:     int = 200     # B ≤ 1024
REPS_GRANDE:      int = 60      # B > 1024
UMBRAL_GRANDE:    int = 1024

TRAIN_CALENTAMIENTO: int = 2    # llamadas a train() descartadas en el control
TRAIN_REPS:          int = 10   # llamadas a train() cronometradas en el control
TOL_CONTROL_BANCO:   float = 0.20   # |banco − train/520| / (train/520)

CAMPOS_BUFER: Tuple[str, ...] = ("observations", "actions", "values",
                                 "log_probs", "advantages", "returns")


def n_equivalente(minilote: int) -> float:
    """
    Cardinal de enjambre equivalente a un minilote B, bajo el supuesto de la
    traducción: n_steps = 128 y 4 entornos fijos, y 40 pasos de gradiente por
    época constantes ⇒ búfer = 128·4·n = 40·B ⇒ n = B·40/(128·4) = B/12.8.
    """
    return minilote * MB_POR_EPOCA / (N_STEPS_TESIS * N_ENVS)


def parsear_arquitectura(etiqueta: str) -> List[int]:
    """'512x512' → [512, 512]."""
    return [int(x) for x in etiqueta.lower().split("x")]


def estado_gpu_nvidia_smi() -> Optional[str]:
    """Utilización, estado P, reloj SM, potencia y temperatura (traza de throttling)."""
    try:
        s = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,pstate,clocks.sm,clocks.max.sm,"
             "power.draw,temperature.gpu", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=20)
        return s.stdout.strip() if s.returncode == 0 else None
    except Exception:
        return None


def estado_alimentacion() -> Optional[str]:
    """Estado de batería de Windows (BatteryStatus 2 = CA conectada, 1 = descargando)."""
    try:
        s = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$b=Get-CimInstance Win32_Battery; if($b){\"$($b.BatteryStatus)|$($b.EstimatedChargeRemaining)\"}"],
            capture_output=True, text=True, timeout=20)
        return s.stdout.strip() or None
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  Construcción de entorno y modelos
# ══════════════════════════════════════════════════════════════════════════════

def construir_env():
    """VecEnv de entrenamiento idéntico al del Exp L (4 entornos = 20 flujos)."""
    config_env = ConfigEntorno(
        n_agentes=N_AGENTES, arena_size=ARENA, max_steps_ep=MAX_STEPS_EP,
        radio_com=COMM_RADIUS, domain_rand=True,
    )
    return construir_vec_env_entrenamiento(
        config_env=config_env, config_train=ConfigEntrenamiento(seed=SEMILLA),
        pesos_rew=PesosRecompensa(**PESOS_TRIAL13), n_envs=N_ENVS, seed=SEMILLA,
    )


def construir_modelo(env, arquitectura: str, dispositivo: str,
                     n_steps: int = N_STEPS_TESIS, batch_size: int = 64):
    """PPO con los hiperparámetros del Trial 13 y la arquitectura pedida."""
    hparams = HiperparametrosPPO(**HPARAMS_TRIAL13)
    hparams = replace(hparams, n_steps=n_steps, batch_size=batch_size)
    config_train = ConfigEntrenamiento(seed=SEMILLA, capas_red=parsear_arquitectura(arquitectura))
    modelo = construir_modelo_ppo(
        env=env, hparams=hparams, config_train=config_train,
        dir_tensorboard=None, seed=SEMILLA, verbose=0, dispositivo=dispositivo,
    )
    modelo.set_logger(configure(folder=None, format_strings=[]))
    return modelo


def n_parametros(modelo) -> int:
    """Parámetros entrenables de la política completa (actor + crítico + log_std)."""
    return int(sum(p.numel() for p in modelo.policy.parameters() if p.requires_grad))


# ══════════════════════════════════════════════════════════════════════════════
#  Fase 1 — poblar el búfer (una sola vez, compartido por las tres condiciones)
# ══════════════════════════════════════════════════════════════════════════════

def fase_poblar() -> None:
    """
    Recolecta UN rollout real de 512 pasos × 20 flujos = 10 240 transiciones con
    la política SIN entrenar (arquitectura de la tesis, semilla 42, CPU) y lo
    guarda aplanado. Las tres condiciones cronometran sobre estos mismos datos.
    El contenido del búfer no influye en el costo de un paso de gradiente (las
    operaciones son de forma fija); se usa un rollout real y no ruido para que
    las pérdidas y la KL tengan los rangos de un entrenamiento de verdad.
    """
    if RUTA_BUFER.exists():
        raise SystemExit(f"[M] {RUTA_BUFER.name} ya existe; no se sobrescribe (regla permanente).")
    env = construir_env()
    modelo = construir_modelo(env, ARQ_TESIS, "cpu", n_steps=N_STEPS_POBLAR)
    t0 = time.perf_counter()
    _, callback = modelo._setup_learn(total_timesteps=N_STEPS_POBLAR * env.num_envs,
                                      callback=None, reset_num_timesteps=True,
                                      tb_log_name="M", progress_bar=False)
    callback.on_training_start(locals(), globals())
    ok = modelo.collect_rollouts(modelo.env, callback, modelo.rollout_buffer,
                                 n_rollout_steps=modelo.n_steps)
    seg = time.perf_counter() - t0
    if not ok or not modelo.rollout_buffer.full:
        raise SystemExit("[M] collect_rollouts no llenó el búfer.")
    rb = modelo.rollout_buffer
    datos = {c: RolloutBuffer.swap_and_flatten(getattr(rb, c)).astype(np.float32) for c in CAMPOS_BUFER}
    DIR_RESULTADOS.mkdir(parents=True, exist_ok=True)
    np.savez(RUTA_BUFER, **datos)
    try:
        env.close()
    except Exception:
        pass
    meta = {
        "transiciones": int(datos["observations"].shape[0]),
        "formas": {c: list(v.shape) for c, v in datos.items()},
        "n_steps": N_STEPS_POBLAR, "flujos": int(env.num_envs),
        "politica": f"sin entrenar, {ARQ_TESIS}, semilla {SEMILLA}, cpu",
        "segundos_rollout": seg, "torch": torch.__version__, "ejecutable": sys.executable,
    }
    (DIR_RESULTADOS / "bufer_poblado_meta.json").write_bytes(
        json.dumps(meta, indent=2, ensure_ascii=False).encode("utf-8"))
    print(f"[M] búfer poblado: {meta['transiciones']} transiciones en {seg:.1f} s", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  El paso de gradiente cronometrado
# ══════════════════════════════════════════════════════════════════════════════

class PasoPPO:
    """
    Un paso de gradiente de PPO, réplica literal del cuerpo del bucle interno de
    `stable_baselines3.ppo.PPO.train` (SB3 2.7.1), sobre el modelo dado.

    `datos_np` son los seis arreglos aplanados en memoria del sistema (así los
    guarda `RolloutBuffer` tras `swap_and_flatten`); `datos_dev`, si se pide el
    modo residente, son los mismos ya copiados al dispositivo.
    """

    def __init__(self, modelo, datos_np: Dict[str, np.ndarray], residente: bool) -> None:
        self.m = modelo
        self.pol = modelo.policy
        self.dev = modelo.policy.device
        self.es_cuda = self.dev.type == "cuda"
        self.clip = float(modelo.clip_range(1.0))
        self.ent_coef = float(modelo.ent_coef)
        self.vf_coef = float(modelo.vf_coef)
        self.max_grad_norm = float(modelo.max_grad_norm)
        self.np = {
            "observations": datos_np["observations"],
            "actions":      datos_np["actions"],
            "values":       datos_np["values"].reshape(-1),
            "log_probs":    datos_np["log_probs"].reshape(-1),
            "advantages":   datos_np["advantages"].reshape(-1),
            "returns":      datos_np["returns"].reshape(-1),
        }
        self.dev_t: Optional[Dict[str, torch.Tensor]] = None
        if residente:
            self.dev_t = {k: torch.tensor(v, device=self.dev) for k, v in self.np.items()}
        self.pol.set_training_mode(True)
        self.ultima_perdida: float = float("nan")

    def _muestras(self, idx: np.ndarray, idx_dev: Optional[torch.Tensor]) -> Tuple[torch.Tensor, ...]:
        """Equivalente de `RolloutBuffer._get_samples` (+ `to_torch`)."""
        orden = ("observations", "actions", "values", "log_probs", "advantages", "returns")
        if self.dev_t is not None:
            return tuple(self.dev_t[k][idx_dev] for k in orden)
        return tuple(torch.tensor(self.np[k][idx], device=self.dev) for k in orden)

    def __call__(self, idx: np.ndarray, idx_dev: Optional[torch.Tensor] = None) -> None:
        obs, actions, old_values, old_log_prob, advantages, returns = self._muestras(idx, idx_dev)
        values, log_prob, entropy = self.pol.evaluate_actions(obs, actions)
        values = values.flatten()
        if len(advantages) > 1:                                   # normalize_advantage=True
            advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        ratio = torch.exp(log_prob - old_log_prob)
        pl1 = advantages * ratio
        pl2 = advantages * torch.clamp(ratio, 1 - self.clip, 1 + self.clip)
        policy_loss = -torch.min(pl1, pl2).mean()
        _ = policy_loss.item()                                    # sincronización 1
        _ = torch.mean((torch.abs(ratio - 1) > self.clip).float()).item()   # 2
        value_loss = F.mse_loss(returns, values)
        _ = value_loss.item()                                     # 3
        entropy_loss = -torch.mean(-log_prob) if entropy is None else -torch.mean(entropy)
        _ = entropy_loss.item()                                   # 4
        loss = policy_loss + self.ent_coef * entropy_loss + self.vf_coef * value_loss
        with torch.no_grad():
            log_ratio = log_prob - old_log_prob
            _ = torch.mean((torch.exp(log_ratio) - 1) - log_ratio).cpu().numpy()   # 5
        self.pol.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.pol.parameters(), self.max_grad_norm)
        self.pol.optimizer.step()
        self.ultima_perdida = float(loss.detach())


def indices_minilotes(n_total: int, minilote: int, n_pasos: int,
                      rng: np.random.Generator) -> List[np.ndarray]:
    """
    Índices de `n_pasos` minilotes con el esquema de SB3: una permutación por
    "época" que se recorre en rebanadas consecutivas de tamaño B; al agotarse
    (sin dejar rebanadas truncadas) se permuta de nuevo. Se generan FUERA de la
    región cronometrada (SB3 paga una permutación por época, costo ~0.1 ms que
    el control del banco absorbe).
    """
    por_perm = n_total // minilote
    lista: List[np.ndarray] = []
    while len(lista) < n_pasos:
        perm = rng.permutation(n_total)
        for k in range(por_perm):
            lista.append(perm[k * minilote:(k + 1) * minilote])
            if len(lista) == n_pasos:
                break
    return lista


def cronometrar_celda(paso: PasoPPO, n_total: int, minilote: int, reps: int,
                      rng: np.random.Generator) -> Tuple[np.ndarray, np.ndarray]:
    """
    CALENTAMIENTO pasos descartados + `reps` pasos cronometrados, cada uno por
    separado con `perf_counter`, con `torch.cuda.synchronize()` antes de
    detener el reloj en CUDA (el último `optimizer.step()` es asíncrono).
    Devuelve (tiempos de calentamiento, tiempos medidos) en ms.
    """
    total = CALENTAMIENTO + reps
    idxs = indices_minilotes(n_total, minilote, total, rng)
    idxs_dev: List[Optional[torch.Tensor]] = [None] * total
    if paso.dev_t is not None:
        idxs_dev = [torch.as_tensor(i, device=paso.dev) for i in idxs]
    if paso.es_cuda:
        torch.cuda.synchronize()
    t = np.empty(total)
    for k in range(total):
        t0 = time.perf_counter()
        paso(idxs[k], idxs_dev[k])
        if paso.es_cuda:
            torch.cuda.synchronize()
        t[k] = (time.perf_counter() - t0) * 1000.0
    if not np.isfinite(paso.ultima_perdida):
        raise SystemExit(f"[M] pérdida no finita en B={minilote}: la celda no es válida.")
    return t[:CALENTAMIENTO], t[CALENTAMIENTO:]


# ══════════════════════════════════════════════════════════════════════════════
#  Control del banco: PPO.train() real contra el banco a B = 64
# ══════════════════════════════════════════════════════════════════════════════

def control_train_real(modelo, datos: Dict[str, np.ndarray]) -> Dict[str, Any]:
    """
    Carga las primeras 2560 transiciones del búfer poblado en el `rollout_buffer`
    de un modelo con la configuración EXACTA de la tesis (n_steps=128, 20
    flujos, B=64, 13 épocas) y cronometra `PPO.train()` completo. Devuelve
    ms/minilote = train()/520, que es la cantidad que el Exp L reportó.
    """
    rb = modelo.rollout_buffer
    n_flujos = rb.n_envs
    n_tesis = rb.buffer_size * n_flujos                           # 2560
    for c in CAMPOS_BUFER:
        destino = getattr(rb, c)
        plano = datos[c][:n_tesis].reshape((n_flujos, rb.buffer_size) + destino.shape[2:])
        setattr(rb, c, np.ascontiguousarray(np.swapaxes(plano, 0, 1)).astype(np.float32))
    rb.full, rb.pos, rb.generator_ready = True, rb.buffer_size, False
    es_cuda = modelo.policy.device.type == "cuda"
    n_mb = (n_tesis // modelo.batch_size) * modelo.n_epochs
    tiempos: List[float] = []
    for k in range(TRAIN_CALENTAMIENTO + TRAIN_REPS):
        t0 = time.perf_counter()
        modelo.train()
        if es_cuda:
            torch.cuda.synchronize()
        if k >= TRAIN_CALENTAMIENTO:
            tiempos.append((time.perf_counter() - t0) * 1000.0 / n_mb)
    t = np.asarray(tiempos)
    return {"transiciones": n_tesis, "minilotes_por_train": n_mb,
            "llamadas_descartadas": TRAIN_CALENTAMIENTO, "llamadas_medidas": TRAIN_REPS,
            "ms_por_minilote_por_llamada": t.tolist(),
            "ms_por_minilote_mediana": float(np.median(t)),
            "ms_por_minilote_min": float(np.min(t))}


# ══════════════════════════════════════════════════════════════════════════════
#  Fase 2 — medir
# ══════════════════════════════════════════════════════════════════════════════

def fase_medir(args: argparse.Namespace) -> None:
    validar_condicion(args.condicion, args.dispositivo)
    es_cuda = args.dispositivo == "cuda"
    if not RUTA_BUFER.exists():
        raise SystemExit(f"[M] falta {RUTA_BUFER.name}: correr antes --fase poblar.")
    datos = dict(np.load(RUTA_BUFER))
    n_total = int(datos["observations"].shape[0])

    etiqueta = args.condicion + (f"_{args.sufijo}" if args.sufijo else "")
    dir_salida = DIR_RESULTADOS / "corridas" / etiqueta
    respaldo = respaldar_si_existe(dir_salida)
    if respaldo is not None:
        print(f"[M] resultados previos respaldados en {respaldo}", flush=True)
    dir_salida.mkdir(parents=True, exist_ok=True)

    hardware = declarar_hardware()
    hardware["alimentacion_BatteryStatus|carga"] = estado_alimentacion()
    hardware["gpu_nvidia_smi_al_arrancar"] = estado_gpu_nvidia_smi()
    print(f"[M] {etiqueta}: torch={hardware['torch']} hilos={hardware['torch_hilos']} "
          f"alimentación={hardware['alimentacion_BatteryStatus|carga']} "
          f"gpu={hardware['gpu_nvidia_smi_al_arrancar']}", flush=True)

    monitor = MonitorCargaCPU(intervalo_s=2.0)
    monitor.iniciar()

    # Todos los modelos se construyen con el VecEnv vivo (sólo hace falta para
    # los espacios y el rollout_buffer); luego se cierra, y durante el
    # cronometraje NO hay procesos trabajadores.
    env = construir_env()
    modelos: Dict[str, Any] = {a: construir_modelo(env, a, args.dispositivo) for a in args.arquitecturas}
    modelo_control = None if args.sin_control else construir_modelo(env, ARQ_TESIS, args.dispositivo)
    try:
        env.close()
    except Exception:
        pass

    reporte: Dict[str, Any] = {
        "condicion": args.condicion, "sufijo": args.sufijo, "dispositivo": args.dispositivo,
        "hardware": hardware, "bufer": {"ruta": RUTA_BUFER.name, "transiciones": n_total},
        "diseno": {"calentamiento_por_celda": CALENTAMIENTO, "reps_B_le_1024": REPS_PEQUENO,
                   "reps_B_gt_1024": REPS_GRANDE, "minilotes": list(args.minilotes),
                   "arquitecturas": list(args.arquitecturas),
                   "parametros": {a: n_parametros(m) for a, m in modelos.items()},
                   "orden_celdas": "barajado con semilla fija por sufijo (anti deriva)"},
    }

    # ── Control del banco ─────────────────────────────────────────────────────
    if modelo_control is not None:
        print("[M] control: PPO.train() real, B=64, 2560 transiciones...", flush=True)
        ctrl = control_train_real(modelo_control, datos)
        # Mismo objeto modelo que acaba de correr train(): el contraste
        # banco ↔ SB3 no mezcla instancias ni pesos iniciales distintos.
        paso_ctrl = PasoPPO(modelo_control, datos, residente=False)
        _, t_banco = cronometrar_celda(paso_ctrl, n_total, 64, REPS_PEQUENO, np.random.default_rng(SEMILLA))
        ctrl["banco_ms_mediana_B64"] = float(np.median(t_banco))
        ctrl["desvio_relativo"] = abs(ctrl["banco_ms_mediana_B64"] - ctrl["ms_por_minilote_mediana"]) \
            / ctrl["ms_por_minilote_mediana"]
        ctrl["tolerancia"] = TOL_CONTROL_BANCO
        ctrl["aprobado"] = bool(ctrl["desvio_relativo"] <= TOL_CONTROL_BANCO)
        reporte["control_banco"] = ctrl
        print(f"[M] control: train()/520 = {ctrl['ms_por_minilote_mediana']:.4f} ms "
              f"(mín {ctrl['ms_por_minilote_min']:.4f}); banco B=64 = "
              f"{ctrl['banco_ms_mediana_B64']:.4f} ms; desvío {100*ctrl['desvio_relativo']:.1f} % "
              f"→ {'APROBADO' if ctrl['aprobado'] else 'NO APROBADO'}", flush=True)
        if not ctrl["aprobado"]:
            reporte["carga_cpu"] = monitor.detener()
            (dir_salida / "reporte.json").write_bytes(
                json.dumps(reporte, indent=2, ensure_ascii=False).encode("utf-8"))
            print("[M] PARADA: el banco no reproduce train()/520. No se mide el barrido.", flush=True)
            raise SystemExit(3)

    # ── Barrido ───────────────────────────────────────────────────────────────
    modos = ("desde_sistema", "residente") if es_cuda else ("desde_sistema",)
    celdas = [(a, b, m) for a in args.arquitecturas for b in args.minilotes for m in modos]
    # Semilla determinista derivada de la etiqueta (hash() de Python no lo es
    # entre procesos): rep1 y rep2 recorren las celdas en órdenes distintos.
    rng_orden = np.random.default_rng(int.from_bytes(etiqueta.encode("utf-8"), "little") % (2**32))
    rng_orden.shuffle(celdas)
    pasos_cache: Dict[Tuple[str, str], PasoPPO] = {}
    filas: List[Dict[str, Any]] = []
    t_barrido = time.perf_counter()
    for i, (arq, b, modo) in enumerate(celdas):
        if b > n_total:
            continue
        clave = (arq, modo)
        if clave not in pasos_cache:
            pasos_cache[clave] = PasoPPO(modelos[arq], datos, residente=(modo == "residente"))
        reps = REPS_PEQUENO if b <= UMBRAL_GRANDE else REPS_GRANDE
        rng = np.random.default_rng(SEMILLA + b)
        t_cal, t_med = cronometrar_celda(pasos_cache[clave], n_total, b, reps, rng)
        base = {"condicion": args.condicion, "sufijo": args.sufijo, "arquitectura": arq,
                "n_parametros": reporte["diseno"]["parametros"][arq], "minilote": b,
                "n_equivalente": n_equivalente(b), "modo": modo, "orden_celda": i}
        for k, v in enumerate(t_cal):
            filas.append({**base, "indice": k, "calentamiento": True, "t_ms": float(v)})
        for k, v in enumerate(t_med):
            filas.append({**base, "indice": CALENTAMIENTO + k, "calentamiento": False, "t_ms": float(v)})
        print(f"[M] {i+1:3d}/{len(celdas)} {arq:>9s} B={b:5d} {modo:13s} "
              f"mediana={np.median(t_med):9.4f} ms  (cal. {np.median(t_cal):9.4f})", flush=True)
    reporte["segundos_barrido"] = time.perf_counter() - t_barrido
    reporte["carga_cpu"] = monitor.detener()
    reporte["hardware"]["gpu_nvidia_smi_al_terminar"] = estado_gpu_nvidia_smi()

    escribir_csv(dir_salida / "pasos.csv", filas,
                 ("condicion", "sufijo", "arquitectura", "n_parametros", "minilote",
                  "n_equivalente", "modo", "orden_celda", "indice", "calentamiento", "t_ms"))
    (dir_salida / "reporte.json").write_bytes(
        json.dumps(reporte, indent=2, ensure_ascii=False).encode("utf-8"))
    print(f"[M] listo: {len(filas)} pasos en {dir_salida}; carga media del sistema "
          f"{reporte['carga_cpu']['ocupacion_sistema_pct_media']:.1f} %", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fase", required=True, choices=("poblar", "medir"))
    p.add_argument("--condicion", required=True, choices=("gpu", "cpu_control", "referencia"))
    p.add_argument("--dispositivo", required=True, choices=("cpu", "cuda"))
    p.add_argument("--sufijo", default="")
    p.add_argument("--minilotes", type=int, nargs="+", default=list(MINILOTES_BASE))
    p.add_argument("--arquitecturas", nargs="+", default=list(ARQUITECTURAS))
    p.add_argument("--sin_control", action="store_true",
                   help="omite el control del banco (sólo para el refinamiento del cruce)")
    args = p.parse_args()
    if args.fase == "poblar":
        validar_condicion(args.condicion, args.dispositivo)
        fase_poblar()
    else:
        fase_medir(args)


if __name__ == "__main__":
    main()
