"""
swarm_env_skeleton.py
=====================
Implementación COMPLETA del entorno MADRL para el enjambre de Pololu 3pi+.

Paradigma : CTDE (Centralised Training, Decentralised Execution)
API       : PettingZoo ParallelEnv
Algoritmo : PPO via Stable-Baselines3 + SuperSuit wrappers
Simulador : DynamicTargetSimulator (cinemática simple, Sim-to-Real-ready)

Arquitectura (single-source-of-truth)
──────────────────────────────────────
  Observation space (D_OBS = 24, FIJO):
    ┌─────────┬─────────────────────┬────────────────────────┐
    │ Índices │ Componente          │ Descripción            │
    ├─────────┼─────────────────────┼────────────────────────┤
    │  0–4    │ own_state           │ [x, y, θ, v, ω] norm.  │
    │  5–7    │ env_reading         │ [C, ∂C/∂x, ∂C/∂y] norm │
    │  8–15   │ neighbor_embedding  │ Mean Embedding (invar.)│
    │ 16–23   │ aoi_map             │ AoI en 8 sectores      │
    └─────────┴─────────────────────┴────────────────────────┘

  Action space (continuo, acotado a cinemática Pololu):
    [v, ω] ∈ [-V_MAX, V_MAX] × [-OMEGA_MAX, OMEGA_MAX]

Orden de operaciones en step() — crítico para la integridad del reward:
  1. Snapshot de C_prev y aoi_local_prev (ANTES de cualquier movimiento)
  2. Integración cinemática de agentes (con fricción si domain_rand)
  3. Evaluación de C_curr con objetivos aún en t (aislar crédito del agente)
  4. Cálculo de recompensas (r_grad, r_ent, p_ibrm, p_cbf)
  5. Avance de objetivos (field.step, t → t+1)
  6. Actualización de AoI grid con nuevas posiciones de agentes
  7. Construcción de observaciones del estado t+1

Autores / Tesis: José — Mecatrónica UVG
"""

from __future__ import annotations

import functools
import math
import warnings
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

import numpy as np
from gymnasium import spaces
from pettingzoo import ParallelEnv

from concentration_dynamics import (
    DynamicTargetSimulator,
    MeanEmbeddingEncoder,
    V_MAX,
    OMEGA_MAX,
    _envolver_angulo,
)

# =============================================================================
# CONSTANTES CINEMÁTICAS Y DIMENSIONALES
# =============================================================================

# Distancia mínima de seguridad inter-agente [m]
D_SAFE: float = 0.15

# Dimensiones del vector de observación (FIJAS)
D_OWN:      int = 5
D_ENV:      int = 3
D_NEIGHBOR: int = 8
D_AOI:      int = 8
D_OBS:      int = D_OWN + D_ENV + D_NEIGHBOR + D_AOI  # = 24

# Factor de normalización del gradiente ∇C (m⁻¹)
#   Con σ_min=0.10 y A=1, max |∇C_i| ≈ 6.07/Gaussiana. Con H=3 en el peor caso
#   puede llegar a ~18, pero típicamente <5. G_MAX=10 es un compromiso seguro.
G_MAX: float = 10.0


# =============================================================================
# DOMAIN RANDOMIZER
# =============================================================================

class DomainRandomizer:
    """
    Aplica perturbaciones al entorno simulado para reducir el Sim-to-Real gap.

    Modela las imperfecciones del sistema físico (Robotat + Pololu 3pi+):
      - Ruido Gaussiano en las POSES observadas (error del OptiTrack).
      - Fricción variable en la tracción (slip de ruedas).

    Por simplicidad y estabilidad, NO se modela latencia de red en esta versión
    (podría agregarse con un deque por agente si se requiere posteriormente).

    Parámetros (rangos → se sortean al inicio de cada episodio)
    -----------------------------------------------------------
    pos_noise_std_range     : σ del ruido Gaussiano de posición [m]
    angle_noise_std_range   : σ del ruido Gaussiano de ángulo [rad]
    friction_scale_range    : factor multiplicativo sobre v y ω aplicados
    seed                    : semilla para reproducibilidad
    """

    def __init__(
        self,
        pos_noise_std_range:   Tuple[float, float] = (0.001, 0.010),
        angle_noise_std_range: Tuple[float, float] = (0.002, 0.030),
        friction_scale_range:  Tuple[float, float] = (0.85, 1.00),
        seed:                  Optional[int] = None,
    ) -> None:
        self.pos_noise_std_range   = pos_noise_std_range
        self.angle_noise_std_range = angle_noise_std_range
        self.friction_scale_range  = friction_scale_range
        self.rng = np.random.default_rng(seed)

        # Valores activos del episodio actual (sorteados en reset)
        self._pos_noise_std:  float = 0.0
        self._ang_noise_std:  float = 0.0
        self._friction_scale: float = 1.0

    def reset(self, seed: Optional[int] = None) -> None:
        """Sortea nuevos parámetros de perturbación para el episodio."""
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self._pos_noise_std  = float(self.rng.uniform(*self.pos_noise_std_range))
        self._ang_noise_std  = float(self.rng.uniform(*self.angle_noise_std_range))
        self._friction_scale = float(self.rng.uniform(*self.friction_scale_range))

    def corrupt_pose(self, estado: np.ndarray) -> np.ndarray:
        """
        Aplica ruido Gaussiano a la pose [x, y, θ] de un estado de agente.
        Las componentes de velocidad (v, ω) no se corrompen (vienen del actuador
        del propio agente, no del OptiTrack).

        Parámetros
        ----------
        estado : np.ndarray, shape (5,)  — [x, y, θ, v, ω]

        Retorna
        -------
        np.ndarray, shape (5,)  — estado con pose ruidosa
        """
        ruidoso = estado.copy()
        ruidoso[0] += self.rng.normal(0.0, self._pos_noise_std)
        ruidoso[1] += self.rng.normal(0.0, self._pos_noise_std)
        ruidoso[2] = float(_envolver_angulo(
            ruidoso[2] + self.rng.normal(0.0, self._ang_noise_std)
        ))
        return ruidoso

    def apply_friction(self, velocidad: np.ndarray) -> np.ndarray:
        """
        Escala la velocidad [v, ω] por el factor de fricción del episodio.

        Parámetros
        ----------
        velocidad : np.ndarray, shape (2,)

        Retorna
        -------
        np.ndarray, shape (2,)
        """
        return velocidad * self._friction_scale

    @property
    def friction_scale(self) -> float:
        return self._friction_scale


# =============================================================================
# REWARD CALCULATOR
# =============================================================================

class RewardCalculator:
    """
    Calcula la recompensa multiobjetivo de cada agente.

    r_total = λ_grad·r_grad  +  λ_ent·r_ent  -  λ_ibrm·p_ibrm  -  λ_cbf·p_cbf

    Componentes
    -----------
    r_grad  : Gradiente de intensidad — recompensa densa por aumentar C(pos).
              r_grad = C(pos_{t+1}) - C(pos_t)   ∈ [-1, 1] típicamente
    r_ent   : Entropía espacial — recompensa el AoI "cosechado" localmente
              (media del grid de AoI en la vecindad ANTES de update_aoi_grid).
              r_ent ∈ [0, 1]
    p_ibrm  : Ineffective Behavior Reduction Mechanism — castigo por:
                - jitter  : varianza de ω en ventana temporal > umbral
                - stagnation: desplazamiento acumulado < umbral
              p_ibrm ∈ [0, 2] aprox.
    p_cbf   : Control Barrier Function — castigo suave-severo por proximidad:
                dmin < D_SAFE      → p_cbf = 1 + (D_SAFE - dmin)/D_SAFE ∈ [1, 2]
                dmin ∈ [D_SAFE, 2·D_SAFE]  → p_cbf = lineal decreciente ∈ [0, 1]
                dmin ≥ 2·D_SAFE    → p_cbf = 0

    Los λ se sintonizan vía Optuna (Optimización Bayesiana) en train.py.
    """

    def __init__(
        self,
        lambda_gradient:          float = 1.0,
        lambda_entropy:           float = 0.5,
        lambda_ibrm:              float = 0.3,
        lambda_cbf:               float = 5.0,
        jitter_window:            int   = 10,
        jitter_threshold_frac:    float = 0.30,   # fracción de OMEGA_MAX
        stagnation_window:        int   = 20,
        stagnation_threshold_m:   float = 0.05,
    ) -> None:
        self.lambda_gradient        = float(lambda_gradient)
        self.lambda_entropy         = float(lambda_entropy)
        self.lambda_ibrm            = float(lambda_ibrm)
        self.lambda_cbf             = float(lambda_cbf)
        self.jitter_window          = int(jitter_window)
        self.jitter_threshold_var   = (jitter_threshold_frac * OMEGA_MAX) ** 2
        self.stagnation_window      = int(stagnation_window)
        self.stagnation_threshold_m = float(stagnation_threshold_m)

        # Buffers de historial (deques de tamaño fijo, auto-drop)
        self._omega_history:    Dict[str, Deque[float]]      = {}
        self._position_history: Dict[str, Deque[np.ndarray]] = {}

    def reset(self, agent_ids: List[str]) -> None:
        """Limpia los buffers para todos los agentes."""
        self._omega_history = {
            a: deque(maxlen=self.jitter_window) for a in agent_ids
        }
        self._position_history = {
            a: deque(maxlen=self.stagnation_window) for a in agent_ids
        }

    def compute(
        self,
        agent_id:           str,
        agent_idx:          int,
        curr_state:         np.ndarray,  # [x, y, θ, v, ω]
        concentracion_prev: float,
        concentracion_curr: float,
        aoi_local_mean:     float,
        all_positions:      np.ndarray,  # (N, 2)
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calcula r_total y un diccionario de componentes (para logging).

        Parámetros
        ----------
        agent_id           : str
        agent_idx          : int — índice en all_positions (para excluir self en CBF)
        curr_state         : np.ndarray, shape (5,) — [x, y, θ, v, ω] post-step
        concentracion_prev : float — C en pos_t (con targets en t)
        concentracion_curr : float — C en pos_{t+1} (con targets AÚN en t)
        aoi_local_mean     : float — AoI promedio local ANTES de update_aoi_grid
        all_positions      : np.ndarray (N, 2) — posiciones de todos los agentes

        Retorna
        -------
        r_total    : float
        components : Dict[str, float]  — componentes individuales
        """
        r_grad = concentracion_curr - concentracion_prev
        r_ent  = float(aoi_local_mean)

        p_ibrm = self._penalty_ibrm(
            agent_id, float(curr_state[4]), curr_state[:2]
        )
        p_cbf = self._penalty_cbf(
            curr_state[:2], all_positions, agent_idx
        )

        r_total = (
              self.lambda_gradient * r_grad
            + self.lambda_entropy  * r_ent
            - self.lambda_ibrm     * p_ibrm
            - self.lambda_cbf      * p_cbf
        )

        return float(r_total), {
            "r_gradient": float(r_grad),
            "r_entropy":  float(r_ent),
            "p_ibrm":     float(p_ibrm),
            "p_cbf":      float(p_cbf),
        }

    # ── Componentes individuales ─────────────────────────────────────────────

    def _penalty_ibrm(
        self,
        agent_id:   str,
        curr_omega: float,
        curr_pos:   np.ndarray,
    ) -> float:
        """
        Penalización por comportamiento inefectivo (jitter + stagnation).
        """
        self._omega_history[agent_id].append(curr_omega)
        self._position_history[agent_id].append(curr_pos.copy())

        penalty = 0.0

        # ── Jitter: varianza de ω en la ventana ────────────────────────────
        if len(self._omega_history[agent_id]) >= self.jitter_window:
            omega_var = float(np.var(self._omega_history[agent_id]))
            if omega_var > self.jitter_threshold_var:
                # Penalización escalada: 0 en el umbral, 1 cuando omega_var
                # es el doble del umbral, clippado a 1.
                penalty += min(
                    (omega_var / self.jitter_threshold_var) - 1.0, 1.0
                )

        # ── Stagnation: desplazamiento acumulado en la ventana ─────────────
        if len(self._position_history[agent_id]) >= self.stagnation_window:
            primera = self._position_history[agent_id][0]
            ultima  = self._position_history[agent_id][-1]
            desplazamiento = float(np.linalg.norm(ultima - primera))
            if desplazamiento < self.stagnation_threshold_m:
                # 0 en el umbral, 1 cuando desplazamiento = 0
                penalty += 1.0 - (desplazamiento / self.stagnation_threshold_m)

        return penalty

    def _penalty_cbf(
        self,
        curr_pos:       np.ndarray,
        all_positions:  np.ndarray,
        agent_idx:      int,
    ) -> float:
        """
        Penalización CBF-inspired: aumenta suavemente al acercarse a otros agentes.
          dmin < D_SAFE         → penalty = 1 + (D_SAFE - dmin)/D_SAFE ∈ [1, 2]
          D_SAFE ≤ dmin < 2·D_SAFE → penalty lineal ∈ [0, 1]
          dmin ≥ 2·D_SAFE        → penalty = 0
        """
        if len(all_positions) < 2:
            return 0.0

        # Excluir el propio agente
        mask = np.ones(len(all_positions), dtype=bool)
        mask[agent_idx] = False
        otras_pos = all_positions[mask]

        dists = np.linalg.norm(otras_pos - curr_pos, axis=1)
        dmin = float(dists.min())

        if dmin < D_SAFE:
            return 1.0 + (D_SAFE - dmin) / D_SAFE          # [1, 2]
        elif dmin < 2.0 * D_SAFE:
            return (2.0 * D_SAFE - dmin) / D_SAFE          # (0, 1]
        else:
            return 0.0


# =============================================================================
# ENTORNO PRINCIPAL — PettingZoo ParallelEnv
# =============================================================================

class CyanobacteriaMonitoringEnv(ParallelEnv):
    """
    Entorno de monitoreo ambiental multi-agente para el enjambre Pololu 3pi+.

    Implementa PettingZoo ParallelEnv con:
      ✓ Observación de dimensión FIJA (Mean Embedding Encoding).
      ✓ Acción continua acotada a la cinemática del Pololu 3pi+.
      ✓ Recompensa multiobjetivo configurable por Optuna.
      ✓ Domain Randomization (fricción + ruido Gaussiano en poses).
      ✓ Renderizado con matplotlib (modos 'human' y 'rgb_array').

    Parámetros
    ----------
    n_agents         : número de robots en el enjambre
    arena_size       : (ancho, alto) del área [m]
    max_steps        : horizonte de episodio
    comm_radius      : radio de comunicación/visibilidad [m]
    dt               : paso de tiempo [s]
    render_mode      : None, 'human' o 'rgb_array'
    reward_weights   : dict con λ_grad, λ_ent, λ_ibrm, λ_cbf  (opcional)
    domain_rand      : activa DomainRandomizer si True
    n_hotspots       : número de objetivos dinámicos
    grid_resolution  : resolución del AoI grid (R×R)
    seed             : semilla
    """

    metadata: Dict[str, Any] = {
        "render_modes": ["human", "rgb_array"],
        "name":         "cyano_swarm_v1",
    }

    def __init__(
        self,
        n_agents:        int = 5,
        arena_size:      Tuple[float, float] = (3.0, 3.0),
        max_steps:       int = 500,
        comm_radius:     float = 1.0,
        dt:              float = 0.1,
        render_mode:     Optional[str] = None,
        reward_weights:  Optional[Dict[str, float]] = None,
        domain_rand:     bool = True,
        n_hotspots:      int = 3,
        grid_resolution: int = 64,
        seed:            Optional[int] = None,
    ) -> None:
        super().__init__()

        # Validación mínima de argumentos
        if render_mode is not None and render_mode not in self.metadata["render_modes"]:
            raise ValueError(
                f"render_mode={render_mode!r} inválido. "
                f"Use uno de {self.metadata['render_modes']} o None."
            )

        # ── Parámetros de instancia ─────────────────────────────────────────
        self.n_agents_init   = int(n_agents)
        self.arena_size      = np.asarray(arena_size, dtype=np.float64)
        self.max_steps       = int(max_steps)
        self.comm_radius     = float(comm_radius)
        self.dt              = float(dt)
        self.render_mode     = render_mode
        self.domain_rand     = bool(domain_rand)
        self.n_hotspots      = int(n_hotspots)
        self.grid_resolution = int(grid_resolution)
        self.rng             = np.random.default_rng(seed)

        # ── Agentes PettingZoo ──────────────────────────────────────────────
        self.possible_agents: List[str] = [f"robot_{i}" for i in range(n_agents)]
        self.agents:          List[str] = []

        # ── Módulos auxiliares ──────────────────────────────────────────────
        self._field = DynamicTargetSimulator(
            arena_size      = tuple(arena_size),
            n_objetivos     = self.n_hotspots,
            dt              = self.dt,
            grid_resolution = self.grid_resolution,
            seed            = seed,
        )
        self._randomizer = DomainRandomizer(seed=seed) if self.domain_rand else None
        self._encoder    = MeanEmbeddingEncoder(
            radio_comunicacion = self.comm_radius,
            embed_dim          = D_NEIGHBOR,
        )
        self._reward_calc = RewardCalculator(
            **(reward_weights or {})
        )

        # ── Estado interno ──────────────────────────────────────────────────
        # Dict agente → [x, y, θ, v, ω]  (float64)
        self._estados: Dict[str, np.ndarray] = {}
        self._step_count: int = 0

        # ── Espacios (pre-construidos) ──────────────────────────────────────
        self._obs_space: spaces.Box = self._build_observation_space()
        self._act_space: spaces.Box = self._build_action_space()

        # ── Artefactos de rendering (lazy init) ─────────────────────────────
        self._fig             = None
        self._ax              = None
        self._im_aoi          = None
        self._target_scatter  = None
        self._target_circles: List[Any] = []
        self._agent_triangles: Dict[str, Any] = {}
        self._agent_comm_circles: Dict[str, Any] = {}
        self._render_title    = None

    # ──────────────────────────────────────────────────────────────────────────
    # ESPACIOS (PettingZoo API)
    # ──────────────────────────────────────────────────────────────────────────

    @functools.lru_cache(maxsize=None)
    def observation_space(self, agent: str) -> spaces.Box:
        return self._obs_space

    @functools.lru_cache(maxsize=None)
    def action_space(self, agent: str) -> spaces.Box:
        return self._act_space

    def _build_observation_space(self) -> spaces.Box:
        """
        Box con bounds semánticos por componente (normalizados):
          own_state     : x_norm, y_norm ∈ [0,1]; θ/π, v/V_MAX, ω/Ω_MAX ∈ [-1,1]
          env_reading   : C ∈ [0,1]; ∇C_x/G_MAX, ∇C_y/G_MAX ∈ [-1,1]
          neighbor_emb  : ∈ [-1,1]^8  (por construcción del MeanEmbeddingEncoder)
          aoi_map       : ∈ [0,1]^8
        """
        low = np.concatenate([
            np.array([0.0, 0.0, -1.0, -1.0, -1.0], dtype=np.float32),   # own
            np.array([0.0, -1.0, -1.0],            dtype=np.float32),   # env
            -np.ones(D_NEIGHBOR,                   dtype=np.float32),   # nbr
            np.zeros(D_AOI,                        dtype=np.float32),   # aoi
        ])
        high = np.concatenate([
            np.array([1.0, 1.0, 1.0, 1.0, 1.0], dtype=np.float32),
            np.array([1.0, 1.0, 1.0],           dtype=np.float32),
            np.ones(D_NEIGHBOR,                 dtype=np.float32),
            np.ones(D_AOI,                      dtype=np.float32),
        ])
        assert low.shape == (D_OBS,) and high.shape == (D_OBS,)
        return spaces.Box(low=low, high=high, shape=(D_OBS,), dtype=np.float32)

    def _build_action_space(self) -> spaces.Box:
        """Acción = [v, ω] acotada a la cinemática del Pololu 3pi+."""
        low  = np.array([-V_MAX, -OMEGA_MAX], dtype=np.float32)
        high = np.array([ V_MAX,  OMEGA_MAX], dtype=np.float32)
        return spaces.Box(low=low, high=high, shape=(2,), dtype=np.float32)

    # ──────────────────────────────────────────────────────────────────────────
    # API PRINCIPAL PettingZoo
    # ──────────────────────────────────────────────────────────────────────────

    def reset(
        self,
        seed:    Optional[int] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, np.ndarray], Dict[str, Dict]]:
        """
        Reinicia el entorno al inicio de un episodio.

        Acciones:
          1. Reinicia el RNG si se provee seed.
          2. Restaura el RNG y estados de los módulos auxiliares.
          3. Sortea poses iniciales de los agentes (distribución sin-colisión).
          4. Restaura self.agents = list(self.possible_agents).
          5. Calcula observaciones iniciales y retorna.

        Retorna
        -------
        observations : Dict[str, np.ndarray]
        infos        : Dict[str, Dict]
        """
        if seed is not None:
            self.rng = np.random.default_rng(seed)

        # ── Reiniciar módulos ──────────────────────────────────────────────
        self._field.reset(seed=seed)
        if self._randomizer is not None:
            self._randomizer.reset(seed=seed)

        # ── Agentes activos ────────────────────────────────────────────────
        self.agents = list(self.possible_agents)

        # ── Poses iniciales sin colisión (rejection sampling simple) ───────
        self._estados = self._sortear_poses_iniciales()

        # ── Reiniciar contadores y historiales ─────────────────────────────
        self._step_count = 0
        self._reward_calc.reset(self.agents)

        # ── Actualizar AoI con posiciones iniciales ────────────────────────
        posiciones = np.array([self._estados[a][:2] for a in self.agents])
        self._field.update_aoi_grid(posiciones)

        # ── Construir observaciones iniciales ──────────────────────────────
        observations = self._get_all_observations()
        infos: Dict[str, Dict] = {a: {} for a in self.agents}

        return observations, infos

    def step(
        self,
        actions: Dict[str, np.ndarray],
    ) -> Tuple[
        Dict[str, np.ndarray],
        Dict[str, float],
        Dict[str, bool],
        Dict[str, bool],
        Dict[str, Dict],
    ]:
        """
        Avanza el entorno un timestep dt.

        Orden de operaciones (CRÍTICO — ver docstring del módulo):
          1. Snapshot: C_prev(pos_t) y aoi_local_prev para cada agente.
          2. Integración cinemática de cada agente (aplica fricción).
          3. C_curr(pos_{t+1}) — targets AÚN en posición t (aislar crédito).
          4. Cálculo de recompensas con snapshots ↑.
          5. field.step() — targets avanzan a t+1.
          6. update_aoi_grid() con posiciones de agentes en t+1.
          7. Construcción de observaciones del estado t+1.

        Parámetros
        ----------
        actions : Dict[str, np.ndarray]
            {agent_id: [v, ω]} para cada agente activo.

        Retorna
        -------
        observations, rewards, terminations, truncations, infos
        """
        # ── Snapshot pre-step ──────────────────────────────────────────────
        c_prev:        Dict[str, float] = {}
        aoi_local_prev: Dict[str, float] = {}
        for agent_id in self.agents:
            pos = self._estados[agent_id][:2]
            c_prev[agent_id] = float(self._field.sample(pos[np.newaxis, :])[0])
            aoi_local_prev[agent_id] = self._calcular_aoi_local_mean(pos)

        # ── Integración cinemática de los agentes ──────────────────────────
        for agent_id in self.agents:
            if agent_id not in actions:
                continue  # agente inactivo o sin acción
            accion = np.asarray(actions[agent_id], dtype=np.float64).flatten()
            if accion.shape != (2,):
                raise ValueError(
                    f"Acción de {agent_id} debe ser shape (2,), recibido {accion.shape}"
                )
            self._integrate_kinematics(agent_id, accion)

        # ── C_curr con targets aún en posición t ──────────────────────────
        c_curr: Dict[str, float] = {}
        for agent_id in self.agents:
            pos = self._estados[agent_id][:2]
            c_curr[agent_id] = float(self._field.sample(pos[np.newaxis, :])[0])

        # ── Posiciones actuales para CBF ───────────────────────────────────
        all_positions = np.array(
            [self._estados[a][:2] for a in self.agents], dtype=np.float64
        )
        agent_to_idx = {a: i for i, a in enumerate(self.agents)}

        # ── Cálculo de recompensas ─────────────────────────────────────────
        rewards:    Dict[str, float]      = {}
        rew_componentes: Dict[str, Dict[str, float]] = {}
        for agent_id in self.agents:
            r_total, componentes = self._reward_calc.compute(
                agent_id           = agent_id,
                agent_idx          = agent_to_idx[agent_id],
                curr_state         = self._estados[agent_id],
                concentracion_prev = c_prev[agent_id],
                concentracion_curr = c_curr[agent_id],
                aoi_local_mean     = aoi_local_prev[agent_id],
                all_positions      = all_positions,
            )
            rewards[agent_id]         = r_total
            rew_componentes[agent_id] = componentes

        # ── Detección de colisiones (para infos) ───────────────────────────
        colisiones = self._check_collisions()

        # ── Avance de objetivos (t → t+1) ──────────────────────────────────
        self._field.step()

        # ── Actualizar AoI grid con posiciones t+1 ─────────────────────────
        self._field.update_aoi_grid(all_positions)

        # ── Contador de step + terminaciones/truncaciones ──────────────────
        self._step_count += 1
        terminations: Dict[str, bool] = {a: False for a in self.agents}
        truncations:  Dict[str, bool] = {
            a: (self._step_count >= self.max_steps) for a in self.agents
        }

        # ── Observaciones del estado t+1 ───────────────────────────────────
        observations = self._get_all_observations()

        # ── Infos con métricas para logging ────────────────────────────────
        cobertura_aoi_global = 1.0 - float(np.mean(self._field._grid_aoi))
        infos: Dict[str, Dict] = {}
        for agent_id in self.agents:
            infos[agent_id] = {
                "cobertura_aoi":    cobertura_aoi_global,
                "colision":         colisiones[agent_id],
                "n_agentes":        len(self.agents),
                "componentes_rew":  rew_componentes[agent_id],
            }

        return observations, rewards, terminations, truncations, infos

    # ──────────────────────────────────────────────────────────────────────────
    # CONSTRUCCIÓN DE OBSERVACIÓN
    # ──────────────────────────────────────────────────────────────────────────

    def _get_observation(self, agent_id: str) -> np.ndarray:
        """
        Construye el vector de observación D_OBS-dimensional del agente.

        Flujo:
          1. Extrae own_state y le aplica ruido (si domain_rand) — modela error
             del OptiTrack midiendo la pose del agente.
          2. Muestrea campo C y gradiente en la pose "ruidosa" (el agente
             observa con lo que el sensor reporta).
          3. Filtra vecinos dentro de comm_radius (usando poses ruidosas).
          4. Construye mean embedding de vecinos.
          5. Calcula aoi_map en 8 sectores angulares.
          6. Normaliza todo y concatena.

        Parámetros
        ----------
        agent_id : str

        Retorna
        -------
        np.ndarray, shape (D_OBS,), dtype float32
        """
        # ── Estado propio (ruidoso si domain_rand) ─────────────────────────
        estado_real = self._estados[agent_id]
        if self._randomizer is not None:
            estado_ego = self._randomizer.corrupt_pose(estado_real)
        else:
            estado_ego = estado_real.copy()

        # ── 1. own_state normalizado ───────────────────────────────────────
        own_norm = np.array([
            estado_ego[0] / self.arena_size[0],         # x ∈ [0, 1]
            estado_ego[1] / self.arena_size[1],         # y ∈ [0, 1]
            estado_ego[2] / math.pi,                    # θ/π ∈ [-1, 1]
            estado_ego[3] / V_MAX,                      # v/V_MAX
            estado_ego[4] / OMEGA_MAX,                  # ω/Ω_MAX
        ], dtype=np.float32)

        # ── 2. env_reading (C y ∇C en la pose ruidosa) ────────────────────
        pos_ego = estado_ego[:2]
        c_local = float(self._field.sample(pos_ego[np.newaxis, :])[0])
        grad    = self._field.gradiente(pos_ego)
        grad_norm = np.clip(grad / G_MAX, -1.0, 1.0)
        env_reading = np.array([
            c_local,
            float(grad_norm[0]),
            float(grad_norm[1]),
        ], dtype=np.float32)

        # ── 3. Vecinos visibles (con poses ruidosas) ──────────────────────
        ids_vecinos = self._get_visible_neighbors(agent_id)
        estados_vec: List[np.ndarray] = []
        conc_vec:    List[float]      = []

        for vid in ids_vecinos:
            estado_v_real = self._estados[vid]
            if self._randomizer is not None:
                estado_v = self._randomizer.corrupt_pose(estado_v_real)
            else:
                estado_v = estado_v_real.copy()
            estados_vec.append(estado_v)
            # Concentración percibida por el vecino en su (propia) posición
            c_v = float(self._field.sample(estado_v[:2][np.newaxis, :])[0])
            conc_vec.append(c_v)

        # ── 4. Mean embedding (invariante a |N_i|) ─────────────────────────
        neighbor_embedding = self._encoder.encode(
            estado_ego      = estado_ego,
            estados_vecinos = estados_vec,
            concentraciones_vecinos = np.asarray(conc_vec, dtype=np.float64),
        )

        # ── 5. AoI map en 8 sectores ───────────────────────────────────────
        aoi_map = self._field.get_aoi_map(pos_ego, n_sectores=D_AOI)

        # ── 6. Concatenación final ─────────────────────────────────────────
        obs = np.concatenate([own_norm, env_reading, neighbor_embedding, aoi_map])
        assert obs.shape == (D_OBS,), f"obs shape {obs.shape} ≠ ({D_OBS},)"

        # Clip defensivo (ruido podría empujar x/y fuera de [0,1] en el borde)
        obs = np.clip(obs, self._obs_space.low, self._obs_space.high)

        return obs.astype(np.float32)

    def _get_all_observations(self) -> Dict[str, np.ndarray]:
        return {a: self._get_observation(a) for a in self.agents}

    def _get_visible_neighbors(self, agent_id: str) -> List[str]:
        """
        Retorna los IDs de agentes dentro de comm_radius (excluye al ego).
        Usa las posiciones REALES (no ruidosas) para determinar visibilidad,
        ya que la oclusión es un evento físico en OptiTrack, no perceptual.
        """
        pos_ego = self._estados[agent_id][:2]
        vecinos = []
        for otro in self.agents:
            if otro == agent_id:
                continue
            pos_otro = self._estados[otro][:2]
            dist = float(np.linalg.norm(pos_otro - pos_ego))
            if dist <= self.comm_radius:
                vecinos.append(otro)
        return vecinos

    def _calcular_aoi_local_mean(self, pos: np.ndarray) -> float:
        """
        Calcula el AoI promedio del grid en un círculo de radio = radio_obs_aoi
        alrededor de `pos`. Usado como reward de entropía (antes de update).
        """
        grid_xx = self._field._grid_xx
        grid_yy = self._field._grid_yy
        dx = grid_xx - pos[0]
        dy = grid_yy - pos[1]
        dist2 = dx ** 2 + dy ** 2
        mascara = dist2 <= (self._field.radio_obs_aoi ** 2)
        if not np.any(mascara):
            return 0.0
        return float(np.mean(self._field._grid_aoi[mascara]))

    # ──────────────────────────────────────────────────────────────────────────
    # CINEMÁTICA
    # ──────────────────────────────────────────────────────────────────────────

    def _integrate_kinematics(
        self,
        agent_id: str,
        action:   np.ndarray,
    ) -> None:
        """
        Integra el modelo unicycle un paso dt para el agente.

        Modelo (unicycle / tracción diferencial):
          x(t+dt) = x(t) + v·cos(θ(t))·dt
          y(t+dt) = y(t) + v·sin(θ(t))·dt
          θ(t+dt) = θ(t) + ω·dt    (con wraparound a (-π, π])

        Pipeline:
          1. Clipping de la acción a los límites físicos del Pololu.
          2. Fricción (si domain_rand): v_eff = v·f, ω_eff = ω·f, f ∈ [0.85, 1.0]
          3. Integración Euler explícita.
          4. Reflexión elástica en los bordes del arena.
          5. Actualización de [v, ω] en el estado (para la próxima observación).

        Parámetros
        ----------
        agent_id : str
        action   : np.ndarray, shape (2,)  — [v_cmd, ω_cmd]
        """
        # 1. Clipping físico de la acción
        v_cmd = float(np.clip(action[0], -V_MAX, V_MAX))
        w_cmd = float(np.clip(action[1], -OMEGA_MAX, OMEGA_MAX))

        # 2. Fricción (domain randomization)
        if self._randomizer is not None:
            v_eff, w_eff = self._randomizer.apply_friction(
                np.array([v_cmd, w_cmd], dtype=np.float64)
            )
        else:
            v_eff, w_eff = v_cmd, w_cmd

        # 3. Estado actual
        estado = self._estados[agent_id]
        x, y, th = estado[0], estado[1], estado[2]

        # 4. Integración Euler explícita (orden 1)
        x_new  = x  + v_eff * math.cos(th) * self.dt
        y_new  = y  + v_eff * math.sin(th) * self.dt
        th_new = float(_envolver_angulo(th + w_eff * self.dt))

        # 5. Reflexión elástica en los bordes (consistente con objetivos)
        x_new, y_new, th_new = self._reflexion_elastica_agente(x_new, y_new, th_new)

        # 6. Actualización del estado
        self._estados[agent_id] = np.array(
            [x_new, y_new, th_new, v_eff, w_eff], dtype=np.float64
        )

    def _reflexion_elastica_agente(
        self,
        x:  float,
        y:  float,
        th: float,
    ) -> Tuple[float, float, float]:
        """
        Aplica reflexión elástica al agente si sale del arena.
        Usa la misma lógica de reflexión que los objetivos:
          pared vertical  (x=0 o x=Wx): θ → π - θ
          pared horizontal(y=0 o y=Wy): θ → -θ
        """
        Wx, Wy = float(self.arena_size[0]), float(self.arena_size[1])

        # Pared izquierda
        if x < 0.0:
            x  = -x
            th = math.pi - th
        # Pared derecha
        elif x > Wx:
            x  = 2.0 * Wx - x
            th = math.pi - th

        # Pared inferior
        if y < 0.0:
            y  = -y
            th = -th
        # Pared superior
        elif y > Wy:
            y  = 2.0 * Wy - y
            th = -th

        # Clipping defensivo
        x = float(np.clip(x, 1e-6, Wx - 1e-6))
        y = float(np.clip(y, 1e-6, Wy - 1e-6))
        th = float(_envolver_angulo(th))

        return x, y, th

    # ──────────────────────────────────────────────────────────────────────────
    # COLISIONES
    # ──────────────────────────────────────────────────────────────────────────

    def _check_collisions(self) -> Dict[str, bool]:
        """
        Detecta colisiones (d_ij < D_SAFE) entre todos los pares de agentes.
        Complejidad: O(N²) con vectorización NumPy — trivial para N≤20.

        Retorna
        -------
        Dict[str, bool]  — {agent_id: True si colisiona con alguno}
        """
        N = len(self.agents)
        colisiones: Dict[str, bool] = {a: False for a in self.agents}
        if N < 2:
            return colisiones

        pos = np.array([self._estados[a][:2] for a in self.agents])   # (N, 2)
        diffs = pos[:, None, :] - pos[None, :, :]                     # (N, N, 2)
        dists = np.linalg.norm(diffs, axis=2)                         # (N, N)
        np.fill_diagonal(dists, np.inf)

        min_dist_por_agente = dists.min(axis=1)                       # (N,)
        for i, a in enumerate(self.agents):
            colisiones[a] = bool(min_dist_por_agente[i] < D_SAFE)

        return colisiones

    # ──────────────────────────────────────────────────────────────────────────
    # POSES INICIALES SIN COLISIÓN
    # ──────────────────────────────────────────────────────────────────────────

    def _sortear_poses_iniciales(self) -> Dict[str, np.ndarray]:
        """
        Sortea poses iniciales garantizando que d_ij > 2·D_SAFE para todo par.
        Usa rejection sampling con límite de intentos; si falla, usa grid fallback.

        Retorna
        -------
        Dict[str, np.ndarray]  — {agent_id: [x, y, θ, 0, 0]}
        """
        N         = self.n_agents_init
        min_sep   = 2.0 * D_SAFE + 0.01
        margen    = 0.15 * self.arena_size
        max_tries = 200

        posiciones: List[np.ndarray] = []
        for _ in range(N):
            aceptado = False
            for _try in range(max_tries):
                cand = self.rng.uniform(
                    low  = margen,
                    high = self.arena_size - margen,
                    size = (2,),
                )
                if all(np.linalg.norm(cand - p) > min_sep for p in posiciones):
                    posiciones.append(cand)
                    aceptado = True
                    break
            if not aceptado:
                # Fallback: grid equiespaciado (raro con N pequeño en arena 3×3)
                warnings.warn(
                    "Rejection sampling falló al sortear poses iniciales; "
                    "usando grid fallback.", RuntimeWarning,
                )
                return self._grid_poses_fallback()

        orientaciones = self.rng.uniform(
            -math.pi, math.pi, size=(N,)
        )

        estados: Dict[str, np.ndarray] = {}
        for i, a in enumerate(self.possible_agents):
            estados[a] = np.array([
                posiciones[i][0],
                posiciones[i][1],
                orientaciones[i],
                0.0,   # v inicial
                0.0,   # ω inicial
            ], dtype=np.float64)
        return estados

    def _grid_poses_fallback(self) -> Dict[str, np.ndarray]:
        """Distribución equiespaciada en grid como fallback."""
        N = self.n_agents_init
        cols = int(math.ceil(math.sqrt(N)))
        rows = int(math.ceil(N / cols))
        dx = self.arena_size[0] / (cols + 1)
        dy = self.arena_size[1] / (rows + 1)

        estados: Dict[str, np.ndarray] = {}
        idx = 0
        for r in range(rows):
            for c in range(cols):
                if idx >= N:
                    break
                estados[self.possible_agents[idx]] = np.array([
                    (c + 1) * dx,
                    (r + 1) * dy,
                    float(self.rng.uniform(-math.pi, math.pi)),
                    0.0, 0.0,
                ], dtype=np.float64)
                idx += 1
        return estados

    # ──────────────────────────────────────────────────────────────────────────
    # RENDERIZADO (matplotlib)
    # ──────────────────────────────────────────────────────────────────────────

    def render(self) -> Optional[np.ndarray]:
        """
        Renderiza el estado actual del entorno.

        Visualiza:
          - AoI heatmap (fondo, escala invertida: oscuro = visitado)
          - Objetivos dinámicos: estrellas rojas con círculos punteados (σ)
          - Agentes: triángulos azules orientados según θ
          - Radios de comunicación: círculos translúcidos azules

        Modos:
          - 'human'     : interactivo con plt.pause (retorna None)
          - 'rgb_array' : retorna np.ndarray (H, W, 3) uint8

        Retorna
        -------
        None o np.ndarray según render_mode.
        """
        if self.render_mode not in ("human", "rgb_array"):
            return None

        # ── Lazy init de artefactos de matplotlib ──────────────────────────
        if self._fig is None:
            self._inicializar_render()

        # ── Actualizar datos de los artefactos ─────────────────────────────
        self._actualizar_render_artifacts()

        # ── Refresh según el modo ──────────────────────────────────────────
        if self.render_mode == "human":
            self._fig.canvas.draw_idle()
            try:
                import matplotlib.pyplot as plt
                plt.pause(0.001)
            except Exception:
                pass
            return None

        # rgb_array: extraer buffer del canvas
        self._fig.canvas.draw()
        img = np.asarray(self._fig.canvas.buffer_rgba())
        return img[..., :3].copy()   # (H, W, 3) uint8

    def _inicializar_render(self) -> None:
        """Crea la figura, los ejes y todos los artefactos persistentes."""
        try:
            import matplotlib.pyplot as plt
            import matplotlib.patches as mpatches
        except ImportError as exc:
            raise ImportError(
                "matplotlib es requerido para render(). Instálalo con "
                "`pip install matplotlib`."
            ) from exc

        if self.render_mode == "human":
            plt.ion()

        Wx, Wy = float(self.arena_size[0]), float(self.arena_size[1])
        self._fig, self._ax = plt.subplots(figsize=(8.5, 8.0))

        # ── AoI heatmap (background) ───────────────────────────────────────
        # Nota: .T es necesario porque _grid_aoi usa indexing='ij' (eje 0 = x)
        # y imshow por defecto espera (row=y, col=x).
        self._im_aoi = self._ax.imshow(
            self._field._grid_aoi.T,
            origin='lower',
            extent=[0.0, Wx, 0.0, Wy],
            cmap='hot_r',
            vmin=0.0, vmax=1.0,
            alpha=0.65,
            interpolation='bilinear',
            zorder=1,
        )
        cbar = self._fig.colorbar(self._im_aoi, ax=self._ax, fraction=0.046, pad=0.04)
        cbar.set_label("AoI (1 = inexplorado, 0 = visitado)", fontsize=10)

        # ── Objetivos: estrellas + círculos de radio σ ─────────────────────
        self._target_scatter = self._ax.scatter(
            [], [],
            s=250, c='red', marker='*',
            edgecolors='white', linewidths=1.5,
            zorder=5,
            label='Objetivos dinámicos',
        )
        self._target_circles = []
        for _ in range(self.n_hotspots):
            circ = mpatches.Circle(
                (0, 0), 0,
                fill=False, edgecolor='red', linewidth=1.2,
                alpha=0.6, linestyle='--',
                zorder=4,
            )
            self._ax.add_patch(circ)
            self._target_circles.append(circ)

        # ── Agentes: triángulos orientados + círculos de comunicación ──────
        self._agent_triangles   = {}
        self._agent_comm_circles = {}
        for agent_id in self.possible_agents:
            # Radio de comunicación (primero, para quedar debajo del triángulo)
            comm_circ = mpatches.Circle(
                (0, 0), self.comm_radius,
                fill=True, facecolor='royalblue',
                edgecolor='royalblue', linewidth=0.8,
                alpha=0.08, linestyle=':',
                zorder=2,
            )
            self._ax.add_patch(comm_circ)
            self._agent_comm_circles[agent_id] = comm_circ

            # Triángulo del agente (inicializado en dummy, se actualiza)
            tri = mpatches.Polygon(
                [[0, 0], [0, 0], [0, 0]],
                closed=True,
                facecolor='royalblue',
                edgecolor='navy', linewidth=1.2,
                alpha=0.95,
                zorder=6,
            )
            self._ax.add_patch(tri)
            self._agent_triangles[agent_id] = tri

        # ── Etiquetas y configuración de ejes ──────────────────────────────
        self._ax.set_xlim(0, Wx)
        self._ax.set_ylim(0, Wy)
        self._ax.set_aspect('equal')
        self._ax.set_xlabel('x [m]', fontsize=11)
        self._ax.set_ylabel('y [m]', fontsize=11)
        self._ax.grid(alpha=0.25, linestyle='--', linewidth=0.5)
        self._render_title = self._ax.set_title("", fontsize=12)

        # Leyenda (solo una entrada estática; los agentes son visualmente obvios)
        self._ax.legend(loc='upper right', fontsize=9, framealpha=0.85)

        self._fig.tight_layout()

    def _actualizar_render_artifacts(self) -> None:
        """Actualiza los datos de los artefactos persistentes (fast path)."""
        # ── AoI heatmap ───────────────────────────────────────────────────
        self._im_aoi.set_data(self._field._grid_aoi.T)

        # ── Objetivos: posiciones y radios σ ──────────────────────────────
        pos_tgt = self._field.posiciones_objetivos       # (H, 2)
        sigmas  = self._field.sigmas_objetivos           # (H,)
        self._target_scatter.set_offsets(pos_tgt)
        for circ, pos, sig in zip(self._target_circles, pos_tgt, sigmas):
            circ.center = (float(pos[0]), float(pos[1]))
            circ.set_radius(float(sig))

        # ── Agentes: triángulos orientados + comm circles ─────────────────
        # Geometría del Pololu 3pi+: chasis ≈ 10 cm de diámetro
        L = 0.07   # largo del triángulo [m]
        W = 0.05   # ancho del triángulo [m]

        agentes_activos = set(self.agents)
        for agent_id in self.possible_agents:
            if agent_id in agentes_activos:
                estado = self._estados[agent_id]
                x, y, th = float(estado[0]), float(estado[1]), float(estado[2])

                # Vértices del triángulo en marco local (heading = +x)
                v_local = np.array([
                    [ L,      0.0 ],   # punta (dirección θ)
                    [-L*0.5,  W*0.5],  # trasera-izquierda
                    [-L*0.5, -W*0.5],  # trasera-derecha
                ])
                # Rotación por θ + traslación
                R = np.array([[math.cos(th), -math.sin(th)],
                              [math.sin(th),  math.cos(th)]])
                v_world = (R @ v_local.T).T + np.array([x, y])

                self._agent_triangles[agent_id].set_xy(v_world)
                self._agent_triangles[agent_id].set_visible(True)
                self._agent_comm_circles[agent_id].center = (x, y)
                self._agent_comm_circles[agent_id].set_visible(True)
            else:
                # Agente terminado: ocultar sus artefactos
                self._agent_triangles[agent_id].set_visible(False)
                self._agent_comm_circles[agent_id].set_visible(False)

        # ── Título con info del step ──────────────────────────────────────
        cobertura = 1.0 - float(np.mean(self._field._grid_aoi))
        titulo = (
            f"Step {self._step_count}/{self.max_steps}    "
            f"t_sim={self._field.tiempo_simulado:.1f}s    "
            f"cobertura AoI={cobertura*100:.1f}%    "
            f"agentes={len(self.agents)}/{self.n_agents_init}"
        )
        self._render_title.set_text(titulo)

    def close(self) -> None:
        """Libera recursos de rendering."""
        if self._fig is not None:
            try:
                import matplotlib.pyplot as plt
                plt.close(self._fig)
            except Exception:
                pass
        self._fig = None
        self._ax = None
        self._im_aoi = None
        self._target_scatter = None
        self._target_circles = []
        self._agent_triangles = {}
        self._agent_comm_circles = {}
        self._render_title = None


# =============================================================================
# FÁBRICA — función helper para compatibilidad con train.py
# =============================================================================

def make_env(
    n_agents:       int = 5,
    arena_size:     Tuple[float, float] = (3.0, 3.0),
    max_steps:      int = 500,
    comm_radius:    float = 1.0,
    reward_weights: Optional[Dict[str, float]] = None,
    domain_rand:    bool = True,
    render_mode:    Optional[str] = None,
    seed:           Optional[int] = None,
) -> CyanobacteriaMonitoringEnv:
    """
    Crea una instancia configurada del entorno.

    Para usar con SB3 + SuperSuit:
        import supersuit as ss
        env = ss.pettingzoo_env_to_vec_env_v1(make_env(...))
        env = ss.concat_vec_envs_v1(env, n_envs=8, base_class='stable_baselines3')
    """
    return CyanobacteriaMonitoringEnv(
        n_agents       = n_agents,
        arena_size     = arena_size,
        max_steps      = max_steps,
        comm_radius    = comm_radius,
        reward_weights = reward_weights,
        domain_rand    = domain_rand,
        render_mode    = render_mode,
        seed           = seed,
    )


# =============================================================================
# DEMO INTERACTIVO (python swarm_env_skeleton.py)
# =============================================================================

if __name__ == "__main__":
    import sys

    # Para sandbox/CI sin display, forzar backend Agg
    import os
    import matplotlib

    # Detección funcional del backend: si no hay DISPLAY o tkinter falla,
    # usar Agg (que produce rgb_array sin necesitar display).
    tiene_display = bool(os.environ.get('DISPLAY', '')) or os.name == 'nt'
    if tiene_display:
        try:
            import tkinter  # noqa: F401 — solo para verificar disponibilidad
            matplotlib.use('TkAgg')
            modo_render = 'human'
        except ImportError:
            matplotlib.use('Agg')
            modo_render = 'rgb_array'
    else:
        matplotlib.use('Agg')
        modo_render = 'rgb_array'

    print("═" * 60)
    print("  DEMO: CyanobacteriaMonitoringEnv")
    print("═" * 60)
    print(f"Backend matplotlib: {matplotlib.get_backend()}  →  render_mode={modo_render!r}")

    env = CyanobacteriaMonitoringEnv(
        n_agents=5,
        arena_size=(3.0, 3.0),
        max_steps=200,
        comm_radius=0.8,
        domain_rand=True,
        n_hotspots=3,
        render_mode=modo_render,
        seed=42,
    )

    print(f"\nEspacios:")
    print(f"  obs_space : {env.observation_space('robot_0')}")
    print(f"  act_space : {env.action_space('robot_0')}")
    print(f"  D_OBS     : {D_OBS}  (esperado 24)")

    # ── Reset ──────────────────────────────────────────────────────────────
    obs, infos = env.reset(seed=42)
    assert len(obs) == 5 and all(o.shape == (D_OBS,) for o in obs.values()), \
        f"Obs shape incorrecto: {[o.shape for o in obs.values()]}"
    print(f"\nReset OK — {len(obs)} agentes, cada obs shape = {obs['robot_0'].shape}")

    # ── Ejecutar episodio ─────────────────────────────────────────────────
    print("\nEjecutando 100 steps con política aleatoria...")
    rew_acumulado = {a: 0.0 for a in env.agents}
    rng = np.random.default_rng(0)

    for step in range(100):
        actions = {
            agent: env.action_space(agent).sample()
            for agent in env.agents
        }
        obs, rewards, terms, truncs, infos = env.step(actions)

        for a, r in rewards.items():
            rew_acumulado[a] += r

        # Render cada 5 steps (para no saturar en modo human)
        if step % 5 == 0:
            img = env.render()
            if step == 0 and img is not None:
                print(f"  render('rgb_array') OK — shape={img.shape}, dtype={img.dtype}")

        if all(truncs.values()):
            print(f"  Episodio truncado en step {step}.")
            break

    print(f"\nRecompensas acumuladas por agente:")
    for a, r in rew_acumulado.items():
        print(f"  {a:>10s} : {r:+.3f}")

    # ── Métricas finales ──────────────────────────────────────────────────
    cobertura_final = 1.0 - float(np.mean(env._field._grid_aoi))
    print(f"\nCobertura AoI final: {cobertura_final*100:.2f}%")
    print(f"Fricción activa     : {env._randomizer.friction_scale:.3f}"
          if env._randomizer else "Fricción activa     : (domain_rand OFF)")

    # ── Render final + guardar imagen si modo rgb_array ────────────────────
    img_final = env.render()
    if img_final is not None:
        from matplotlib import image as mpimg
        ruta = "/tmp/swarm_render_demo.png"
        mpimg.imsave(ruta, img_final)
        print(f"\nRender final guardado → {ruta}")

    env.close()
    print("\n" + "═" * 60)
    print("  Demo completada ✓")
    print("═" * 60)
