"""
supervisor_cobertura.py
=======================
Controlador supervisor ÚNICO para el demo visual en Webots R2025a.

Rol del controlador
-------------------
Este script corre dentro del nodo Robot con `supervisor TRUE` declarado en
`worlds/lab_robotat.wbt`. Es el único controlador del mundo: NO se usan
controladores por robot ni canales Emitter/Receiver. Su responsabilidad es:

  1. Instanciar `CyanobacteriaMonitoringEnv` exactamente con la configuración
     del modelo `RESULTADO_PRIMERO` (200 k pasos de entrenamiento, n_agents=5,
     arena 3×3 m, dt=0.1 s, comm_radius=1.0 m, n_hotspots=3, seed=42), salvo
     `domain_rand=False` (mantenido para que el demo se vea limpio, sin ruido
     gaussiano sobre las poses).
  2. Cargar la política congelada `modelos/modelo_PRIMERO.zip` con `PPO.load`.
  3. Ejecutar un loop de rollout infinito: por cada paso obtiene la acción de
     cada agente con `modelo.predict(obs[agente], deterministic=True)`, hace
     `env.step(acciones)` con el dict de acciones agregado, y al truncarse el
     episodio reinicia con `env.reset()`.
  4. Renderizar cada paso copiando el estado interno del env a Webots:
        - Para cada agente i, lee `env._estados[robot_i] = [x, y, θ, v, ω]`
          y escribe `translation` y `rotation` del nodo Webots `DEF p3pi_i`.
        - Para cada objetivo j, lee `env._field.posiciones_objetivos[j] = [x, y]`
          y escribe `translation` del nodo `DEF obs(j+1)`. La altura z queda
          fija (las esferas sólo se mueven en el plano).

Convenciones de mapeo (env ↔ Webots)
------------------------------------
  - Marco del env  : esquina inferior izquierda en (0, 0), arena [0, Wx]×[0, Wy].
  - Marco de Webots: centrado, arena [-Wx/2, +Wx/2] × [-Wy/2, +Wy/2].
        x_webots = x_env − Wx/2,    y_webots = y_env − Wy/2.
  - Heading del env: θ=0 ⇒ moverse en +x  (convención math estándar).
  - Heading del proto `Pololu3piKin`: +Y por geometría (eje de ruedas en ±X).
        ⇒ Para alinear, el campo `rotation` del nodo del robot recibe el
          ángulo (θ_env + OFFSET_PROTO_RAD) sobre el eje +Z. Con
          OFFSET_PROTO_RAD = −π/2, θ_env=0 visualmente apunta a +X mundo.

Sincronía Webots ↔ env
----------------------
El env avanza con `dt=0.1 s`. El `.wbt` declara `basicTimeStep 10` (ms), por lo
que `robot.step(PASOS_WEBOTS_POR_DT)` con `PASOS_WEBOTS_POR_DT = int(env.dt*1000
/ basicTimeStep) = 10` mantiene la cadencia de animación 1 step env = 100 ms de
simulación Webots. Si el reloj real-time del PC va más lento, Webots se ajusta
manteniendo el orden temporal; la animación seguirá siendo visualmente coherente.

Requisitos del intérprete
-------------------------
Webots invoca el comando Python configurado en `Tools → Preferences → Python
command`. Ese intérprete necesita:
  numpy · torch (CPU) · stable_baselines3 · gymnasium · pettingzoo
Ver `README.md` para detalles.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Inyección de la ruta del paquete `lib` en sys.path
# ─────────────────────────────────────────────────────────────────────────────
# Webots arranca el controlador con cwd = carpeta del controlador, pero la
# resolución de imports relativos depende de cómo se invoque el script. Para
# robustez, agregamos explícitamente la carpeta del controlador a sys.path.
_CARPETA_CONTROLADOR: Path = Path(__file__).resolve().parent
if str(_CARPETA_CONTROLADOR) not in sys.path:
    sys.path.insert(0, str(_CARPETA_CONTROLADOR))

# ─────────────────────────────────────────────────────────────────────────────
# Imports de terceros y del paquete local (después de ajustar sys.path)
# ─────────────────────────────────────────────────────────────────────────────
from controller import Supervisor  # type: ignore  # provisto por Webots

from stable_baselines3 import PPO

from lib.swarm_env_skeleton import CyanobacteriaMonitoringEnv


# =============================================================================
# CONSTANTES DEL DEMO
# =============================================================================

# Configuración del entorno (idéntica a RESULTADO_PRIMERO salvo domain_rand).
N_AGENTES:        int                   = 5
ARENA_SIZE:       Tuple[float, float]   = (3.0, 3.0)
MAX_STEPS_EP:     int                   = 500
COMM_RADIUS:      float                 = 1.0
DT_ENV:           float                 = 0.1
N_HOTSPOTS:       int                   = 3
SEMILLA:          int                   = 42
DOMAIN_RAND_DEMO: bool                  = False   # demo limpio, sin ruido

# Mapeo de marcos.
OFFSET_X: float = ARENA_SIZE[0] / 2.0
OFFSET_Y: float = ARENA_SIZE[1] / 2.0

# Offset angular para alinear el "adelante" del proto (+Y local) con la
# convención del env (θ=0 ⇒ +X mundo). Ver docstring del módulo.
OFFSET_PROTO_RAD: float = -math.pi / 2.0

# Alturas (fijas) en Webots [m].
Z_AGENTE:    float = 0.0    # los robots se posan sobre el piso (proto define z)
Z_OBJETIVO:  float = 0.12   # esferas flotantes sobre la arena

# DEF names en el .wbt.
DEF_AGENTES:   List[str] = [f"p3pi_{i}"  for i in range(N_AGENTES)]
DEF_OBJETIVOS: List[str] = [f"obs{j+1}" for j in range(N_HOTSPOTS)]

# Rutas.
RUTA_MODELO: Path = _CARPETA_CONTROLADOR / "modelos" / "modelo_PRIMERO.zip"


# =============================================================================
# UTILIDADES DE TRANSFORMACIÓN
# =============================================================================

def env_a_webots_xy(x_env: float, y_env: float) -> Tuple[float, float]:
    """
    Traduce coordenadas del marco del env (origen en esquina) al marco de
    Webots (origen centrado).

    Parámetros
    ----------
    x_env, y_env : float — coordenadas en el marco [0, Wx]×[0, Wy] del env.

    Retorna
    -------
    (x_webots, y_webots) : Tuple[float, float] — coordenadas centradas.
    """
    return (x_env - OFFSET_X, y_env - OFFSET_Y)


def theta_env_a_rotation(theta_env: float) -> Tuple[float, float, float, float]:
    """
    Construye el axis-angle `rotation` de Webots a partir del ángulo del env.

    El proto `Pololu3piKin` tiene su "adelante" en +Y local; el env usa la
    convención θ=0 ⇒ heading +X. Por lo tanto se aplica OFFSET_PROTO_RAD
    (=-π/2) al ángulo.

    Retorna
    -------
    (ax, ay, az, ang) : ejes y ángulo en radianes (siempre rotación sobre Z).
    """
    return (0.0, 0.0, 1.0, float(theta_env + OFFSET_PROTO_RAD))


# =============================================================================
# CONTROLADOR PRINCIPAL
# =============================================================================

class SupervisorCobertura:
    """
    Encapsula el demo: Webots Supervisor + env + política PPO.

    Atributos públicos
    ------------------
    supervisor : controller.Supervisor — handle de Webots.
    env        : CyanobacteriaMonitoringEnv — entorno headless.
    modelo     : PPO — política congelada (deterministic=True en predict).
    timestep_ms: int — basicTimeStep del mundo Webots, en ms.
    pasos_webots_por_dt : int — cantidad de pasos de Webots por dt del env.
    """

    def __init__(self) -> None:
        """
        Inicializa el supervisor, descubre los nodos por DEF, instancia el env
        y carga la política.

        El constructor NO empieza a animar; eso lo hace `correr_loop_infinito`.
        """
        # ── Handle del Supervisor ──────────────────────────────────────────
        self.supervisor: Supervisor = Supervisor()
        self.timestep_ms: int = int(self.supervisor.getBasicTimeStep())

        # Cantidad de pasos de Webots por cada paso del env.
        # dt_env [s] × 1000 [ms/s] / timestep_ms [ms]
        pasos: float = DT_ENV * 1000.0 / float(self.timestep_ms)
        if not math.isclose(pasos, round(pasos), abs_tol=1e-6):
            raise ValueError(
                f"basicTimeStep={self.timestep_ms} ms no divide exactamente "
                f"dt_env={DT_ENV*1000:.0f} ms. Ajustar el .wbt."
            )
        self.pasos_webots_por_dt: int = int(round(pasos))

        # ── Localizar nodos por DEF ────────────────────────────────────────
        self._nodos_agentes:   List = []
        self._campos_trans_ag: List = []
        self._campos_rot_ag:   List = []
        for nombre_def in DEF_AGENTES:
            nodo = self.supervisor.getFromDef(nombre_def)
            if nodo is None:
                raise RuntimeError(
                    f"No se encontró el nodo Webots con DEF {nombre_def!r}. "
                    f"Revisar lab_robotat.wbt."
                )
            self._nodos_agentes.append(nodo)
            self._campos_trans_ag.append(nodo.getField("translation"))
            self._campos_rot_ag.append(nodo.getField("rotation"))

        self._nodos_objetivos:   List = []
        self._campos_trans_obj:  List = []
        for nombre_def in DEF_OBJETIVOS:
            nodo = self.supervisor.getFromDef(nombre_def)
            if nodo is None:
                raise RuntimeError(
                    f"No se encontró el nodo Webots con DEF {nombre_def!r}. "
                    f"Revisar lab_robotat.wbt."
                )
            self._nodos_objetivos.append(nodo)
            self._campos_trans_obj.append(nodo.getField("translation"))

        # ── Instanciar env headless ────────────────────────────────────────
        # `render_mode=None` desactiva matplotlib; la visualización corre en
        # Webots, no en el env.
        self.env: CyanobacteriaMonitoringEnv = CyanobacteriaMonitoringEnv(
            n_agents    = N_AGENTES,
            arena_size  = ARENA_SIZE,
            max_steps   = MAX_STEPS_EP,
            comm_radius = COMM_RADIUS,
            dt          = DT_ENV,
            render_mode = None,
            domain_rand = DOMAIN_RAND_DEMO,
            n_hotspots  = N_HOTSPOTS,
            seed        = SEMILLA,
        )

        # ── Cargar política ────────────────────────────────────────────────
        if not RUTA_MODELO.is_file():
            raise FileNotFoundError(
                f"No se encontró el modelo en {RUTA_MODELO!s}."
            )
        # `device='cpu'` evita warnings si torch detecta GPU pero el entrenamiento
        # fue CPU-only.
        self.modelo: PPO = PPO.load(str(RUTA_MODELO), device="cpu")

        # ── Reset inicial del env y sincronización a Webots ────────────────
        self._observaciones_actuales: Dict[str, np.ndarray]
        self._observaciones_actuales, _ = self.env.reset(seed=SEMILLA)
        self._publicar_estado_a_webots()

        # Log de inicio (visible en la consola de Webots).
        print(
            f"[SupervisorCobertura] listo  "
            f"timestep={self.timestep_ms} ms  "
            f"pasos_webots_por_dt={self.pasos_webots_por_dt}  "
            f"agentes={N_AGENTES}  hotspots={N_HOTSPOTS}  "
            f"domain_rand={DOMAIN_RAND_DEMO}"
        )

    # ──────────────────────────────────────────────────────────────────────

    def _publicar_estado_a_webots(self) -> None:
        """
        Copia las poses internas del env a los nodos de Webots.

        Lee:
          - `env._estados[robot_i] = np.ndarray (5,)` con [x, y, θ, v, ω].
          - `env._field.posiciones_objetivos` : np.ndarray (H, 2).
        Escribe `translation` y `rotation` de cada nodo correspondiente.
        """
        # ── Agentes ────────────────────────────────────────────────────────
        for i, agent_id in enumerate(self.env.possible_agents):
            estado: np.ndarray = self.env._estados[agent_id]
            x_env, y_env, theta_env = float(estado[0]), float(estado[1]), float(estado[2])

            x_w, y_w = env_a_webots_xy(x_env, y_env)
            self._campos_trans_ag[i].setSFVec3f([x_w, y_w, Z_AGENTE])
            self._campos_rot_ag[i].setSFRotation(
                list(theta_env_a_rotation(theta_env))
            )

        # ── Objetivos ──────────────────────────────────────────────────────
        posiciones_obj: np.ndarray = self.env._field.posiciones_objetivos   # (H, 2)
        for j in range(N_HOTSPOTS):
            x_env, y_env = float(posiciones_obj[j, 0]), float(posiciones_obj[j, 1])
            x_w, y_w = env_a_webots_xy(x_env, y_env)
            self._campos_trans_obj[j].setSFVec3f([x_w, y_w, Z_OBJETIVO])

    # ──────────────────────────────────────────────────────────────────────

    def _calcular_acciones(self) -> Dict[str, np.ndarray]:
        """
        Para cada agente activo, llama a `modelo.predict(obs, deterministic=True)`
        y arma el dict de acciones que espera `env.step`.

        Importante: este método NO reconstruye observaciones. Usa el dict que
        el propio env devolvió en el último `reset`/`step` — exactamente la
        misma construcción de observación que se usó durante el entrenamiento.
        """
        acciones: Dict[str, np.ndarray] = {}
        for agent_id in self.env.agents:
            obs: np.ndarray = self._observaciones_actuales[agent_id]
            accion, _ = self.modelo.predict(obs, deterministic=True)
            acciones[agent_id] = np.asarray(accion, dtype=np.float32).flatten()
        return acciones

    # ──────────────────────────────────────────────────────────────────────

    def _paso_de_rl(self) -> bool:
        """
        Ejecuta un paso del env (predict → step → publicar estado).

        Retorna
        -------
        episodio_terminado : bool — True si todos los agentes truncaron.
        """
        acciones = self._calcular_acciones()
        (
            self._observaciones_actuales,
            _rewards,
            _terminations,
            truncations,
            _infos,
        ) = self.env.step(acciones)

        self._publicar_estado_a_webots()

        return bool(truncations) and all(truncations.values())

    # ──────────────────────────────────────────────────────────────────────

    def correr_loop_infinito(self) -> None:
        """
        Loop principal del demo. Se ejecuta hasta que Webots cierra el
        controlador (devolviendo -1 desde `supervisor.step`).

        Patrón por iteración:
          1. `paso_de_rl()`           — avanza el env un dt y publica a Webots.
          2. `supervisor.step(N×ts)`  — avanza Webots `pasos_webots_por_dt`
                                        ticks, manteniendo dt_env real = 100 ms.
          3. Si Webots indica cierre, se sale del loop.
          4. Si el episodio truncó, `env.reset()` y se continúa.
        """
        n_ticks: int = self.timestep_ms * self.pasos_webots_por_dt

        while True:
            episodio_terminado: bool = self._paso_de_rl()

            # Webots avanza su reloj y renderiza la nueva pose.
            if self.supervisor.step(n_ticks) == -1:
                break

            if episodio_terminado:
                # Reset del env. La semilla cambia entre episodios para variar
                # las trayectorias de los objetivos; el modelo es estocástico
                # respecto a iniciales, no respecto a su política (determinista).
                semilla_nueva: int = int(
                    self.env.rng.integers(0, 2**31 - 1)
                )
                self._observaciones_actuales, _ = self.env.reset(seed=semilla_nueva)
                self._publicar_estado_a_webots()


# =============================================================================
# ENTRY-POINT WEBOTS
# =============================================================================

def main() -> None:
    """Punto de entrada que Webots invoca al cargar el controlador."""
    supervisor = SupervisorCobertura()
    supervisor.correr_loop_infinito()


if __name__ == "__main__":
    main()
