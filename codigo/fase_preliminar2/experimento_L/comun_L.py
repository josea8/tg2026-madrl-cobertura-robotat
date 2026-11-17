"""
comun_L.py — Experimento L: costo computacional, CPU frente a GPU.

Constantes, declaración de hardware y protocolo de episodio compartidos por
los dos regímenes del experimento (entrenamiento e inferencia).

Las TRES condiciones del diseño, y por qué son tres y no dos:

  gpu          : venv_lab4, torch 2.11.0+cu128, device="cuda"
  cpu_control  : venv_lab4, torch 2.11.0+cu128, device="cpu"   ← el CONTROL
  referencia   : intérprete de la tesis, torch 2.10.0+cpu, device="cpu"

Comparar `gpu` contra `referencia` mediría versión de torch Y dispositivo a la
vez. El contraste limpio es `gpu` contra `cpu_control` (mismo intérprete, misma
rueda, sólo cambia el dispositivo). `referencia` es un tercer punto que dice si
la versión de torch importa por sí sola.

Este módulo valida en tiempo de ejecución que la condición declarada por línea
de comandos coincide con el intérprete y la rueda de torch que realmente están
corriendo, para que una etiqueta equivocada no pase inadvertida.

No modifica nada de `fase_preliminar2/`: importa `swarm_env_skeleton` en modo
de sólo lectura.

Autor: José — Tesis Mecatrónica UVG
"""

from __future__ import annotations

import csv
import datetime as _dt
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import torch

DIR_EXPERIMENTO: Path = Path(__file__).resolve().parent
DIR_PADRE:       Path = DIR_EXPERIMENTO.parent          # fase_preliminar2
DIR_RESULTADOS:  Path = DIR_EXPERIMENTO / "resultados"
RUTA_MODELO_PRIMERO: Path = (
    DIR_PADRE / "modelos" / "tesis_v1" / "RESULTADO_PRIMERO" / "modelo_PRIMERO.zip"
)

if str(DIR_PADRE) not in sys.path:
    sys.path.insert(0, str(DIR_PADRE))
if str(DIR_EXPERIMENTO) not in sys.path:
    sys.path.insert(0, str(DIR_EXPERIMENTO))

from swarm_env_skeleton import D_SAFE, make_env  # noqa: E402

# ── Protocolo único de evaluación (CLAUDE.md §5) ──────────────────────────────
N_AGENTES:      int   = 5
ARENA:          Tuple[float, float] = (3.0, 3.0)
MAX_STEPS_EP:   int   = 500
COMM_RADIUS:    float = 1.0
SEMILLA:        int   = 42
UMBRAL_CONTACTO: float = 0.15   # D_SAFE: contacto físico, el comparable
UMBRAL_MARGEN:   float = 0.22   # margen operativo de la metodología

# ── Trial 13 (modelos/tesis_v1/RESULTADO_PRIMERO/hiperparametros.json) ────────
HPARAMS_TRIAL13: Dict[str, float] = {
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
PESOS_TRIAL13: Dict[str, float] = {
    "lambda_gradient": 0.5622468083379316,
    "lambda_entropy":  1.1403296484190344,
    "lambda_ibrm":     0.48380314172632155,
    "lambda_cbf":      2.9655314099141474,
}

# ── Cifras oficiales contra las que se verifica el control ────────────────────
COBERTURA_OFICIAL_MADRL: float = 0.681291   # RESULTADO_PRIMERO, 100 eps, reflexión
TOL_CONTROL:             float = 1e-6       # a seis decimales (CLAUDE.md §5)

CONDICIONES: Tuple[str, ...] = ("gpu", "cpu_control", "referencia")


# ══════════════════════════════════════════════════════════════════════════════
#  Validación de la condición declarada contra el intérprete real
# ══════════════════════════════════════════════════════════════════════════════

def validar_condicion(condicion: str, dispositivo: str) -> None:
    """
    Aborta si la etiqueta de condición no coincide con lo que realmente corre.

    Reglas:
      gpu         → torch con sufijo "+cu128", CUDA disponible, dispositivo "cuda"
      cpu_control → torch con sufijo "+cu128", dispositivo "cpu"
      referencia  → torch 2.10.0 (rueda cpu de la tesis), dispositivo "cpu"
    """
    version = torch.__version__
    if condicion == "gpu":
        ok = ("+cu128" in version) and torch.cuda.is_available() and dispositivo == "cuda"
    elif condicion == "cpu_control":
        ok = ("+cu128" in version) and dispositivo == "cpu"
    elif condicion == "referencia":
        ok = version.startswith("2.10.0") and ("+cu" not in version) and dispositivo == "cpu"
    else:
        raise ValueError(f"Condición desconocida: {condicion!r}")
    if not ok:
        raise SystemExit(
            f"[Exp L] La condición '{condicion}' no coincide con el intérprete: "
            f"torch {version}, cuda={torch.cuda.is_available()}, "
            f"dispositivo pedido={dispositivo}, ejecutable={sys.executable}"
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Declaración de hardware
# ══════════════════════════════════════════════════════════════════════════════

def _powershell(comando: str) -> Optional[str]:
    """Ejecuta un comando de PowerShell y devuelve su salida, o None si falla."""
    try:
        salida = subprocess.run(
            ["powershell", "-NoProfile", "-Command", comando],
            capture_output=True, text=True, timeout=30,
        )
        return salida.stdout.strip() if salida.returncode == 0 else None
    except Exception:
        return None


def _nvidia_smi() -> Dict[str, Optional[str]]:
    """Versión de driver y memoria total según nvidia-smi (None si no está)."""
    try:
        salida = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=30,
        )
        if salida.returncode != 0:
            return {"nombre": None, "driver": None, "memoria_total": None}
        campos = [c.strip() for c in salida.stdout.strip().splitlines()[0].split(",")]
        return {"nombre": campos[0], "driver": campos[1], "memoria_total": campos[2]}
    except Exception:
        return {"nombre": None, "driver": None, "memoria_total": None}


def declarar_hardware() -> Dict[str, Any]:
    """
    Recoge todo lo que hace interpretables las cifras de tiempo: CPU (modelo,
    núcleos físicos y lógicos), GPU (modelo, memoria, driver, CUDA, cuDNN),
    versiones de Python y torch, hilos de torch y carga de CPU al arrancar.
    """
    cpu_ps = _powershell(
        "Get-CimInstance Win32_Processor | Select-Object -First 1 | "
        "ForEach-Object { $_.Name + '|' + $_.NumberOfCores + '|' + "
        "$_.NumberOfLogicalProcessors + '|' + $_.MaxClockSpeed + '|' + $_.LoadPercentage }"
    )
    cpu: Dict[str, Any] = {"nombre": platform.processor(), "nucleos_fisicos": None,
                           "nucleos_logicos": os.cpu_count(), "mhz_nominal": None,
                           "carga_pct_al_arrancar": None}
    if cpu_ps and "|" in cpu_ps:
        partes = cpu_ps.split("|")
        cpu.update({
            "nombre": partes[0].strip(),
            "nucleos_fisicos": int(partes[1]),
            "nucleos_logicos": int(partes[2]),
            "mhz_nominal": int(partes[3]),
            "carga_pct_al_arrancar": int(partes[4]) if partes[4].strip() else None,
        })
    ram_ps = _powershell(
        "(Get-CimInstance Win32_PhysicalMemory | Measure-Object Capacity -Sum).Sum"
    )
    ram_gib = round(int(ram_ps) / 2**30, 1) if ram_ps and ram_ps.isdigit() else None

    gpu: Dict[str, Any] = {"disponible": torch.cuda.is_available()}
    smi = _nvidia_smi()
    gpu.update({"driver": smi["driver"], "memoria_total_nvidia_smi": smi["memoria_total"]})
    if torch.cuda.is_available():
        prop = torch.cuda.get_device_properties(0)
        gpu.update({
            "nombre": prop.name,
            "memoria_total_MiB_torch": round(prop.total_memory / 2**20, 1),
            "capacidad_computo": f"{prop.major}.{prop.minor}",
            "multiprocesadores": prop.multi_processor_count,
            "cuda_runtime_torch": torch.version.cuda,
            "cudnn": torch.backends.cudnn.version(),
        })
    else:
        gpu["nombre"] = smi["nombre"]

    return {
        "fecha":            _dt.datetime.now().isoformat(timespec="seconds"),
        "so":               f"{platform.system()} {platform.release()} ({platform.version()})",
        "python":           sys.version.split()[0],
        "ejecutable":       sys.executable,
        "torch":            torch.__version__,
        "torch_hilos":      torch.get_num_threads(),
        "torch_hilos_interop": torch.get_num_interop_threads(),
        "OMP_NUM_THREADS":  os.environ.get("OMP_NUM_THREADS"),
        "MKL_NUM_THREADS":  os.environ.get("MKL_NUM_THREADS"),
        "cpu":              cpu,
        "ram_GiB":          ram_gib,
        "gpu":              gpu,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Monitor de carga de CPU durante la corrida
# ══════════════════════════════════════════════════════════════════════════════

class MonitorCargaCPU:
    """
    Muestrea la ocupación de CPU de TODO el sistema mientras corre el
    experimento, con `GetSystemTimes` de kernel32 (costo despreciable).

    Motivo: la máquina del autor corre otras aplicaciones (videollamada,
    MATLAB, navegador) que consumían entre 3 y 4 núcleos al momento de
    diseñar el experimento. No se pueden cerrar desde acá, así que la carga
    de fondo se MIDE y se declara junto a cada condición, en vez de suponer
    una máquina ociosa. Reporta la ocupación media y máxima del sistema
    (en % de los 12 hilos lógicos) y, restando lo que este proceso usó, una
    estimación de la carga AJENA al experimento. Los trabajadores del VecEnv
    son procesos hijos y cuentan como "ajenos" en esa resta; se reporta por
    separado la ocupación propia del proceso principal.
    """

    def __init__(self, intervalo_s: float = 2.0) -> None:
        import threading
        self._intervalo = intervalo_s
        self._muestras: List[float] = []
        self._detener = threading.Event()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._t_pared_ini = 0.0
        self._t_proc_ini = 0.0

    @staticmethod
    def _tiempos_sistema() -> Optional[Tuple[float, float]]:
        """(ocioso, total) en unidades de 100 ns sumadas sobre todos los hilos lógicos."""
        try:
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.windll.kernel32
            idle, kern, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
            if not k32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
                return None
            conv = lambda ft: (ft.dwHighDateTime << 32) | ft.dwLowDateTime
            i, k, u = conv(idle), conv(kern), conv(user)
            return float(i), float(k + u)      # kernel incluye idle
        except Exception:
            return None

    def _bucle(self) -> None:
        prev = self._tiempos_sistema()
        while not self._detener.wait(self._intervalo):
            act = self._tiempos_sistema()
            if prev and act and act[1] > prev[1]:
                ocupado = 1.0 - (act[0] - prev[0]) / (act[1] - prev[1])
                self._muestras.append(100.0 * ocupado)
            prev = act

    def iniciar(self) -> None:
        self._t_pared_ini = time.perf_counter()
        self._t_proc_ini = time.process_time()
        self._hilo.start()

    def detener(self) -> Dict[str, Any]:
        self._detener.set()
        self._hilo.join(timeout=self._intervalo * 2)
        pared = time.perf_counter() - self._t_pared_ini
        proc = time.process_time() - self._t_proc_ini
        n_log = os.cpu_count() or 1
        propio_pct_sistema = 100.0 * proc / (pared * n_log) if pared > 0 else float("nan")
        m = np.asarray(self._muestras) if self._muestras else np.array([float("nan")])
        return {
            "n_muestras": int(len(self._muestras)),
            "intervalo_s": self._intervalo,
            "ocupacion_sistema_pct_media": float(np.nanmean(m)),
            "ocupacion_sistema_pct_max": float(np.nanmax(m)),
            "ocupacion_sistema_pct_p90": float(np.nanpercentile(m, 90)),
            "proceso_principal_nucleos_medios": proc / pared if pared > 0 else float("nan"),
            "proceso_principal_pct_sistema": propio_pct_sistema,
            "ajena_mas_hijos_pct_sistema_media": float(np.nanmean(m)) - propio_pct_sistema,
            "nucleos_logicos": n_log,
        }


# ══════════════════════════════════════════════════════════════════════════════
#  Protocolo de episodio — réplica del Exp E (correr_experimento_E.correr_episodio)
# ══════════════════════════════════════════════════════════════════════════════

def construir_env_protocolo(n_agentes: int, seed: int = SEMILLA):
    """
    Entorno del protocolo único: reflexión elástica (la nativa de
    `fase_preliminar2`), sin domain randomization, pesos del Trial 13.
    """
    return make_env(
        n_agents       = n_agentes,
        arena_size     = ARENA,
        max_steps      = MAX_STEPS_EP,
        comm_radius    = COMM_RADIUS,
        reward_weights = PESOS_TRIAL13,
        domain_rand    = False,
        seed           = seed,
    )


def correr_episodio_cronometrado(
    modelo,
    env,
    seed_ep:    int,
    max_pasos:  Optional[int] = None,
    sincronizar_cuda: bool = False,
) -> Dict[str, Any]:
    """
    Un episodio determinista con cronómetro por decisión, como en el Exp E.

    El cronómetro envuelve la LLAMADA DE DECISIÓN COMPLETA: apilar las
    observaciones de los n agentes en un lote `(n, 24)`, `modelo.predict`
    determinista y desempaquetar las acciones. Es exactamente lo que el Exp E
    midió para reportar 0.757 ms/decisión, y es lo que un despliegue pagaría
    por ciclo de control (la observación llega en CPU y la acción se consume
    en CPU: la transferencia a la GPU y de vuelta es parte del costo real).

    `max_pasos` permite truncar el episodio (necesario para n ≥ 50, donde el
    entorno tarda del orden de un segundo por paso): la latencia por decisión
    no depende de cuántos pasos se den, pero la cobertura de un episodio
    truncado NO es comparable con la del protocolo y se marca como tal.

    Retorna métricas del episodio y el vector completo de tiempos (ms).
    """
    obs, _ = env.reset(seed=seed_ep)
    agentes: List[str] = list(obs.keys())
    n_a = len(agentes)

    pares_contacto: set = set()
    pares_margen:   set = set()
    tiempos_ms: List[float] = []
    n_pasos = 0
    done = False

    while not done:
        t0 = time.perf_counter()
        obs_arr = np.stack([obs[a] for a in agentes])
        acciones, _ = modelo.predict(obs_arr, deterministic=True)
        accion_dict = {a: acciones[k] for k, a in enumerate(agentes)}
        if sincronizar_cuda:
            torch.cuda.synchronize()
        tiempos_ms.append((time.perf_counter() - t0) * 1000.0)

        obs, _, term, trunc, _ = env.step(accion_dict)
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
        if max_pasos is not None and n_pasos >= max_pasos:
            break

    t = np.asarray(tiempos_ms, dtype=float)
    return {
        "cobertura_aoi_final": 1.0 - float(np.mean(env._field._grid_aoi)),
        "colisiones_015":      len(pares_contacto),
        "colisiones_022":      len(pares_margen),
        "pasos":               n_pasos,
        "episodio_completo":   n_pasos >= MAX_STEPS_EP,
        "t_decision_ms_media": float(np.mean(t)),
        "t_decision_ms_std":   float(np.std(t, ddof=1)) if len(t) > 1 else 0.0,
        "t_decision_ms_mediana": float(np.median(t)),
        "t_decision_ms_p95":   float(np.percentile(t, 95)),
        "t_decision_ms_min":   float(np.min(t)),
        "tiempos_ms":          t,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Utilidades de archivo
# ══════════════════════════════════════════════════════════════════════════════

def respaldar_si_existe(ruta: Path) -> Optional[Path]:
    """
    Regla permanente: NUNCA sobrescribir resultados. Si `ruta` existe, la
    renombra con sufijo de fecha y hora y devuelve la ruta del respaldo.
    """
    if not ruta.exists():
        return None
    marca = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = ruta.with_name(f"{ruta.name}_respaldo_{marca}")
    ruta.rename(destino)
    return destino


def escribir_csv(ruta: Path, filas: Iterable[Dict[str, Any]], campos: Sequence[str]) -> None:
    """Escribe un CSV con LF, precisión completa (repr de float) y cabecera."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(campos), lineterminator="\n")
        w.writeheader()
        for fila in filas:
            w.writerow({k: (repr(v) if isinstance(v, float) else v) for k, v in fila.items()})


def resumen_estadistico(x: np.ndarray) -> Dict[str, float]:
    """Media, desviación (ddof=1), IC95 normal, mediana, min y max."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    m = float(np.mean(x))
    s = float(np.std(x, ddof=1)) if n > 1 else 0.0
    ee = s / np.sqrt(n) if n > 0 else 0.0
    return {"n": n, "media": m, "std": s, "ic95_inf": m - 1.96 * ee,
            "ic95_sup": m + 1.96 * ee, "mediana": float(np.median(x)),
            "min": float(np.min(x)), "max": float(np.max(x))}
