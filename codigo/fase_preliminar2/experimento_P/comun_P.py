"""
comun_P.py — Constantes y utilidades compartidas del Experimento P.

Experimento P: confirmación de la configuración ganadora del Exp J (prueba 7,
`cfg_eb1d01e59b`) y del Trial 13 con 20 semillas de entrenamiento nuevas por
brazo, con el MISMO código del Exp J (`estudio_J.py` en modo trabajador).
Propósito declarado: ESTIMACIÓN, no prueba de superioridad (ver
`PREREGISTRO_P.md`).

Reglas que este módulo hace cumplir:

- Copia propia de las libs del proyecto en `lib/`, verificada idéntica por
  sha256 contra los originales (regla de CLAUDE.md §7). `estudio_J.py` va en
  `lib/j/` porque agrega a `sys.path` la carpeta padre de su propia carpeta.
- Nada se escribe fuera de `experimento_P/`.
- Los archivos se escriben en bytes con LF (regla de CLAUDE.md §7).
- Los subprocesos corren con `-B` y sin variables `EXPJ_*` heredadas.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ══════════════════════════════════════════════════════════════════════════════
#  RUTAS
# ══════════════════════════════════════════════════════════════════════════════

RAIZ_P:      Path = Path(__file__).resolve().parent
DIR_FP2:     Path = RAIZ_P.parent                       # fase_preliminar2
DIR_LIB:     Path = RAIZ_P / "lib"
DIR_LIB_J:   Path = DIR_LIB / "j"
RUTA_ESTUDIO_J_COPIA: Path = DIR_LIB_J / "estudio_J.py"
DIR_CONFIG:  Path = RAIZ_P / "config"
DIR_RES:     Path = RAIZ_P / "resultados"
DIR_CONTROL: Path = DIR_RES / "control"
DIR_LOGS:    Path = DIR_RES / "logs"
DIR_EVAL:    Path = DIR_RES / "evaluacion"
DIR_ANALISIS: Path = DIR_RES / "analisis"
RUTA_MANIFIESTO: Path = RAIZ_P / "manifiesto_P.json"


def dir_base(humo: bool) -> Path:
    """
    Carpeta de salida. La prueba de fontanería (`--humo`) NUNCA escribe en
    `resultados/`: usa `P_DIR_HUMO` si está definida (p. ej. el scratchpad) o,
    si no, `resultados_humo/`, que no es parte del experimento.
    """
    if not humo:
        return DIR_RES
    return Path(os.environ.get("P_DIR_HUMO", str(RAIZ_P / "resultados_humo")))

# Originales → copia propia (destino relativo a RAIZ_P)
ORIGINALES: Dict[str, Path] = {
    "lib/train.py":                  DIR_FP2 / "train.py",
    "lib/swarm_env_skeleton.py":     DIR_FP2 / "swarm_env_skeleton.py",
    "lib/concentration_dynamics.py": DIR_FP2 / "concentration_dynamics.py",
    "lib/j/estudio_J.py":            DIR_FP2 / "experimento_J" / "estudio_J.py",
}

# Referencias de sólo lectura
DIR_J_ESTUDIO: Path = DIR_FP2 / "experimento_J" / "resultados" / "estudio"
RUTA_CFG_GANADORA_J: Path = DIR_J_ESTUDIO / "cfg_eb1d01e59b" / "config_barridos.json"
DIR_REF_S42: Path = DIR_J_ESTUDIO / "cfg_eb1d01e59b" / "semilla_42"
DIR_PRIMERO: Path = DIR_FP2 / "modelos" / "tesis_v1" / "RESULTADO_PRIMERO"
RUTA_MODELO_PRIMERO: Path = DIR_PRIMERO / "modelo_PRIMERO.zip"
RUTA_HPARAMS_T13:    Path = DIR_PRIMERO / "hiperparametros.json"
RUTA_METRICAS_100:   Path = DIR_PRIMERO / "metricas_100eps.json"
RUTA_CONSOLIDAR:     Path = DIR_FP2 / "consolidar_resultado_primero.py"

# ══════════════════════════════════════════════════════════════════════════════
#  DISEÑO (fijado en PREREGISTRO_P.md antes de correr)
# ══════════════════════════════════════════════════════════════════════════════

# Lista ORDENADA fijada a priori el 2026-09-24. N = 20 por brazo (decisión de
# Jose); con N = 10 se habrían usado las diez primeras.
SEMILLAS: Tuple[int, ...] = tuple(range(1001, 1021))
N_POR_BRAZO: int = 20

BRAZOS: Tuple[str, ...] = ("ganadora", "trial13")
CONFIGS: Dict[str, Path] = {
    "ganadora": DIR_CONFIG / "ganadora.json",
    "trial13":  DIR_CONFIG / "trial13.json",
}

# Conjuntos de episodios (semillas SEMILLA_EPISODIOS·10000 + offset + i, base 42)
CONJUNTO_NUEVO: Tuple[int, int] = (2_000, 100)    # (offset, n) → 422000–422099
CONJUNTO_FINAL: Tuple[int, int] = (1_000, 30)     # el objetivo de TPE en el Exp J
N_TRABAJADORES_EVAL: int = 5
PASO_FIJO: int = 200_000

# Control C2: semilla 42 de la ganadora, reentrenada en carpeta nueva.
SEMILLA_CONTROL: int = 42

# Valores oficiales para los controles C1 y C3 (metricas_100eps.json)
COB_OFICIAL_MADRL: float = 0.6812908187508583
COB_OFICIAL_NN:    float = 0.25434854030609133


# ══════════════════════════════════════════════════════════════════════════════
#  ESCRITURA EN BYTES (LF) Y HASHES
# ══════════════════════════════════════════════════════════════════════════════

def escribir_texto(ruta: Path, texto: str) -> None:
    """Escribe `texto` en UTF-8 con LF, sin conversión de fin de línea."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(texto.replace("\r\n", "\n").encode("utf-8"))


def escribir_json(ruta: Path, datos: Any) -> None:
    """Vuelca JSON con precisión completa (repr de float), UTF-8 y LF."""
    escribir_texto(ruta, json.dumps(datos, indent=2, ensure_ascii=False) + "\n")


def anexar_jsonl(ruta: Path, registro: Dict[str, Any]) -> None:
    """Agrega una línea JSON al registro (modo binario, LF)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "ab") as f:
        f.write((json.dumps(registro, ensure_ascii=False) + "\n").encode("utf-8"))


def sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def sha256_miembro_zip(ruta_zip: Path, miembro: str) -> str:
    """sha256 de un miembro de un .zip de SB3 (p. ej. 'policy.pth')."""
    with zipfile.ZipFile(ruta_zip) as z:
        return hashlib.sha256(z.read(miembro)).hexdigest()


def num_timesteps_zip(ruta_zip: Path) -> int:
    """Lee `num_timesteps` del miembro 'data' (JSON) de un .zip de SB3."""
    with zipfile.ZipFile(ruta_zip) as z:
        datos = json.loads(z.read("data").decode("utf-8"))
    return int(datos["num_timesteps"])


# ══════════════════════════════════════════════════════════════════════════════
#  IMPORTACIÓN DE LA COPIA PROPIA
# ══════════════════════════════════════════════════════════════════════════════

def importar_estudio_j_copia():
    """
    Importa `lib/j/estudio_J.py` (la copia) y verifica que `train`,
    `swarm_env_skeleton` y `concentration_dynamics` se resolvieron desde `lib/`
    y NO desde los originales de `fase_preliminar2`.

    Debe llamarse a nivel de módulo en los scripts que usan el pool de
    evaluación: con `spawn`, los procesos hijos re-importan `__main__` y
    necesitan que `lib/j` esté en `sys.path` para resolver
    `estudio_J._iniciar_trabajador_eval`.
    """
    if str(DIR_LIB_J) not in sys.path:
        sys.path.insert(0, str(DIR_LIB_J))
    import estudio_J as J  # noqa: E402  (copia propia)
    import train, swarm_env_skeleton, concentration_dynamics  # noqa: E401,E402
    for mod in (J, train, swarm_env_skeleton, concentration_dynamics):
        origen = Path(mod.__file__).resolve()
        if DIR_LIB.resolve() not in origen.parents:
            raise RuntimeError(f"{mod.__name__} se importó desde {origen}, no desde {DIR_LIB}")
    return J


# ══════════════════════════════════════════════════════════════════════════════
#  SUBPROCESO TRABAJADOR (modo trabajador de estudio_J.py, sin modificarlo)
# ══════════════════════════════════════════════════════════════════════════════

def entorno_subproceso(humo: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Entorno limpio para el trabajador: sin `EXPJ_*` heredadas (una residual
    daría una corrida corta que parece válida) y sin escribir bytecode.
    `humo` sólo se usa en la prueba de fontanería, nunca en la corrida real.
    """
    entorno = {k: v for k, v in os.environ.items() if not k.startswith("EXPJ_")}
    entorno["PYTHONDONTWRITEBYTECODE"] = "1"
    if humo:
        entorno.update(humo)
    return entorno


def correr_trabajador(
    semilla:     int,
    dir_semilla: Path,
    ruta_config: Path,
    ruta_log:    Path,
    humo:        Optional[Dict[str, str]] = None,
) -> Tuple[int, float]:
    """
    Entrena UNA semilla con el modo trabajador de la copia de `estudio_J.py`.

    Devuelve (código de salida, segundos de pared). Si `dir_semilla` ya tiene
    `resultado_semilla.json`, el propio `estudio_J` lo reutiliza sin entrenar;
    quien llama decide si eso es aceptable (reanudación) o no (controles).
    """
    cmd = [
        sys.executable, "-B", "-u", str(RUTA_ESTUDIO_J_COPIA),
        "--worker_semilla", str(semilla),
        "--worker_dir",     str(dir_semilla),
        "--worker_config",  str(ruta_config),
    ]
    ruta_log.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with open(ruta_log, "ab") as registro:
        proc = subprocess.run(cmd, stdout=registro, stderr=subprocess.STDOUT,
                              env=entorno_subproceso(humo), cwd=str(RAIZ_P))
    return proc.returncode, time.time() - t0


# ══════════════════════════════════════════════════════════════════════════════
#  CONDICIONES DE MEDICIÓN: CORRIENTE ALTERNA Y CARGA DE CPU
# ══════════════════════════════════════════════════════════════════════════════

def estado_bateria() -> Optional[int]:
    """
    `Win32_Battery.BatteryStatus` (2 = conectado a corriente alterna).
    None si no se pudo leer. Es el criterio del Exp M (bitácora).
    """
    try:
        salida = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Battery | Select-Object -First 1).BatteryStatus"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
        return int(salida) if salida else None
    except Exception:
        return None


def linea_ca() -> Optional[int]:
    """
    `GetSystemPowerStatus().ACLineStatus` de kernel32: 1 = conectado a
    corriente alterna, 0 = batería, 255 = desconocido. No lanza procesos, así
    que sirve para chequear seguido durante la medición.
    """
    try:
        import ctypes
        from ctypes import wintypes

        class _EstadoEnergia(ctypes.Structure):
            _fields_ = [("ACLineStatus", wintypes.BYTE), ("BatteryFlag", wintypes.BYTE),
                        ("BatteryLifePercent", wintypes.BYTE), ("SystemStatusFlag", wintypes.BYTE),
                        ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]
        estado = _EstadoEnergia()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(estado)):
            return None
        return int(estado.ACLineStatus) & 0xFF
    except Exception:
        return None


def en_corriente_alterna() -> bool:
    """Criterio de P: ACLineStatus == 1 (la condición la exige Jose, 2026-09-24)."""
    return linea_ca() == 1


def _tiempos_sistema() -> Optional[Tuple[float, float]]:
    """(ocioso, total) de GetSystemTimes, sumado sobre los hilos lógicos."""
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        idle, kern, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
        if not k32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
            return None
        conv = lambda ft: (ft.dwHighDateTime << 32) | ft.dwLowDateTime  # noqa: E731
        return float(conv(idle)), float(conv(kern) + conv(user))   # kernel incluye idle
    except Exception:
        return None


def carga_cpu_pct(segundos: float = 5.0) -> Optional[float]:
    """Ocupación media de TODO el sistema durante `segundos` (en % de los hilos lógicos)."""
    a = _tiempos_sistema()
    time.sleep(segundos)
    b = _tiempos_sistema()
    if not a or not b or b[1] <= a[1]:
        return None
    return 100.0 * (1.0 - (b[0] - a[0]) / (b[1] - a[1]))


class MonitorCarga:
    """Muestrea la ocupación de CPU del sistema en un hilo mientras corre una semilla."""

    def __init__(self, intervalo_s: float = 5.0) -> None:
        import threading
        self._intervalo = intervalo_s
        self._muestras: List[float] = []
        self._alterna: List[bool] = []
        self._detener = threading.Event()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)

    def _bucle(self) -> None:
        prev = _tiempos_sistema()
        n = 0
        while not self._detener.wait(self._intervalo):
            act = _tiempos_sistema()
            if prev and act and act[1] > prev[1]:
                self._muestras.append(100.0 * (1.0 - (act[0] - prev[0]) / (act[1] - prev[1])))
            prev = act
            n += 1
            if n % 12 == 0:                       # alimentación, cada ~1 min
                self._alterna.append(en_corriente_alterna())

    def iniciar(self) -> None:
        self._hilo.start()

    def detener(self) -> Dict[str, Any]:
        self._detener.set()
        self._hilo.join(timeout=self._intervalo * 3)
        m = self._muestras
        return {
            "n_muestras":          len(m),
            "carga_media_pct":     (sum(m) / len(m)) if m else None,
            "carga_max_pct":       max(m) if m else None,
            "siempre_en_alterna":  all(self._alterna) if self._alterna else None,
            "n_chequeos_alterna":  len(self._alterna),
        }
