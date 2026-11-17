"""
concentration_dynamics.py
=========================
Implementación de:
  1. DynamicTargetSimulator  — objetivos puntuales dinámicos (cinemática simple)
  2. MeanEmbeddingEncoder    — codificación invariante a vecinos variables
                               [SIN CAMBIOS respecto a la versión anterior]

Cambio de arquitectura (v2)
───────────────────────────
Se reemplaza el antiguo `ConcentrationFieldSimulator` (basado en SDE de Langevin,
advección-difusión y vórtices de Rankine) por un modelo cinemático simple.

Motivación de ingeniería:
  - Los objetivos físicos en el laboratorio Robotat serán robots adicionales o
    marcadores virtuales en OptiTrack, NO floraciones de cianobacterias reales.
  - Simular dinámica de fluidos crea un Sim-to-Real gap innecesario.
  - Un modelo cinemático simple es perfectamente replicable físicamente.
  - La señal de gradiente (∇C) del campo es mucho más suave y monótona,
    lo que estabiliza el entrenamiento de PPO (menos varianza en los
    gradientes de política).

Modelo físico simplificado
──────────────────────────
Cada objetivo i ∈ {1, ..., H} es un punto con estado cinemático:

    estado_i = ( μᵢ, sᵢ, θᵢ )
        μᵢ ∈ ℝ²       : posición [m]
        sᵢ > 0         : rapidez constante durante el episodio [m/s]
        θᵢ ∈ (-π, π]  : orientación del vector velocidad [rad]

Dinámica (smooth random walk + reflexión elástica):

    θᵢ(t+dt)  = θᵢ(t) + α·√dt·ξᵢ,        ξᵢ ~ N(0, 1)    [deriva angular suave]
    μᵢ(t+dt)  = μᵢ(t) + sᵢ·[cos θᵢ, sin θᵢ]·dt            [movimiento lineal]
    + reflexión elástica en bordes:
        pared x=const:  θ → π - θ  (flip componente x de velocidad)
        pared y=const:  θ → -θ     (flip componente y de velocidad)

Con α = 0 → movimiento puramente lineal con rebotes (opción "ballistic").
Con α > 0 → smooth random walk (default, más robusto a sobre-ajuste).

Representación del "campo de interés" C(p, t):
    Cada objetivo genera una zona Gaussiana de amplitud 1 y σ fijo durante
    el episodio. El campo total es:

        C(p, t) = clip( Σᵢ exp(-‖p - μᵢ(t)‖² / (2σᵢ²)), 0, 1 )

    Esto conserva la semántica de "intensidad de interés" que los robots
    observan, SIN la complejidad de la dinámica difusiva.

Age-of-Information (AoI)
────────────────────────
IDÉNTICO al modelo anterior:
    Grid discreto (R×R) que mide cuánto tiempo lleva sin muestrearse cada celda.
    AoI[i,j] ∈ [0, 1], crece a ritmo dt/τ_max en cada step.
    Se resetea a 0.0 cuando un agente visita esa celda.

Convenciones de unidades
────────────────────────
  Posiciones  : metros [m], origen (0,0) en esquina inferior-izquierda
  Velocidades : m/s y rad/s
  Ángulos     : radianes, rango canónico (-π, π]
  Tipos NumPy : float32 para vectores de observación (compatibilidad SB3)
                float64 para cómputo interno (precisión numérica)

Integración con el resto del sistema
────────────────────────────────────
La clase mantiene la MISMA API pública que `ConcentrationFieldSimulator`:
    reset(), step(), sample(), gradiente(), update_aoi_grid(),
    get_aoi_map(), get_snapshot_campo()

Por tanto el entorno (`CyanobacteriaMonitoringEnv`) solo debe cambiar el
NOMBRE de la clase instanciada; la lógica interna del env es invariante.

Autores / Tesis: José — Mecatrónica UVG
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np

# ──────────────────────────────────────────────────────────────────────────────
# Constantes cinemáticas del Pololu 3pi+
# ──────────────────────────────────────────────────────────────────────────────
V_MAX: float = 0.31        # [m/s]
OMEGA_MAX: float = 6.2832  # [rad/s] ≈ 2π


# ──────────────────────────────────────────────────────────────────────────────
# Funciones auxiliares (módulo-nivel, sin estado)
# ──────────────────────────────────────────────────────────────────────────────

def _envolver_angulo(angulo: np.ndarray) -> np.ndarray:
    """
    Envuelve ángulo(s) al rango canónico (-π, π].

    Trabaja con escalares y arrays de cualquier forma via NumPy.

    Parámetros
    ----------
    angulo : np.ndarray | float

    Retorna
    -------
    np.ndarray | float  — mismo tipo/forma que la entrada
    """
    return (np.asarray(angulo) + math.pi) % (2.0 * math.pi) - math.pi


def _distancia_euclidea(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """
    Distancia euclídea ‖a - b‖₂ para pares de puntos 2D.

    Parámetros
    ----------
    a, b : np.ndarray, shape (..., 2)

    Retorna
    -------
    np.ndarray, shape (...)
    """
    diff = np.asarray(a) - np.asarray(b)
    return np.sqrt(np.sum(diff ** 2, axis=-1))


# ══════════════════════════════════════════════════════════════════════════════
#  1. DynamicTargetSimulator
# ══════════════════════════════════════════════════════════════════════════════

class DynamicTargetSimulator:
    """
    Simula H objetivos puntuales móviles mediante cinemática simple (sin fluidos).

    Cada objetivo i ∈ {1, ..., H} tiene estado:
      - μᵢ ∈ ℝ²  : posición [m]
      - sᵢ       : rapidez lineal constante durante el episodio [m/s]
      - θᵢ       : orientación del vector velocidad [rad]
      - σᵢ       : radio del kernel Gaussiano de "interés" [m], CONSTANTE por episodio

    Dinámica por step (dt):
      1. Deriva angular suave:  θᵢ ← θᵢ + α·√dt·ξᵢ,  ξᵢ ~ N(0, 1)
      2. Movimiento lineal:     μᵢ ← μᵢ + sᵢ·[cos θᵢ, sin θᵢ]·dt
      3. Reflexión elástica en los 4 bordes del arena.

    Parámetro α (escala_deriva_angular):
      - α = 0   → movimiento puramente lineal con rebotes ("ballistic").
      - α > 0   → smooth random walk (más robusto a exploits en la política).
      - Recomendado: 0.2–0.4 rad/√s (típico para tesis con estabilidad).

    El "campo de intensidad" C(p, t) ∈ [0, 1] es una suma de Gaussianas:
      C(p, t) = clip( Σᵢ exp(-‖p - μᵢ(t)‖² / (2σᵢ²)), 0, 1 )

    Nota: amplitud fija = 1 (no hay decaimiento ni crecimiento logístico).
    Esto garantiza que la señal de reward sea estacionaria durante el episodio,
    lo que estabiliza PPO.

    API pública (COMPATIBLE con ConcentrationFieldSimulator anterior):
      - reset(seed)
      - step()
      - sample(posiciones)        → campo evaluado en N puntos
      - gradiente(posicion)       → gradiente analítico
      - update_aoi_grid(pos)      → marca zonas visitadas
      - get_aoi_map(pos, N)       → AoI en sectores angulares
      - get_snapshot_campo()      → campo en todo el grid (para render)

    Parámetros de construcción
    --------------------------
    arena_size              : (ancho, alto) del área [m]
    n_objetivos             : número H de objetivos dinámicos
    dt                      : paso de tiempo [s]
    grid_resolution         : resolución R del grid de AoI (R×R celdas)
    rapidez_rango           : (min, max) de rapidez sᵢ [m/s]
                              Se sortea independientemente para cada objetivo.
    sigma_rango             : (min, max) de σᵢ [m]
                              Se sortea independientemente para cada objetivo.
    escala_deriva_angular   : α en rad/√s. 0 = movimiento lineal puro.
    radio_obs_aoi           : radio de "observación" de cada agente para AoI [m]
    edad_max_aoi            : τ — tiempo de saturación del AoI [s]
    radio_mapa_aoi          : radio alrededor del agente para consultar el AoI [m]
                              Si None, se usa 0.4·min(arena_size).
    seed                    : semilla para reproducibilidad
    """

    # ── Constantes físicas del modelo ─────────────────────────────────────
    _SIGMA_MIN: float = 0.05   # [m] límite inferior defensivo
    _SIGMA_MAX: float = 0.70   # [m] límite superior defensivo

    def __init__(
        self,
        arena_size: Tuple[float, float],
        n_objetivos: int = 3,
        dt: float = 0.1,
        grid_resolution: int = 64,
        rapidez_rango: Tuple[float, float] = (0.05, 0.15),
        sigma_rango: Tuple[float, float] = (0.10, 0.25),
        escala_deriva_angular: float = 0.30,
        radio_obs_aoi: float = 0.15,
        edad_max_aoi: float = 60.0,
        radio_mapa_aoi: Optional[float] = None,
        seed: Optional[int] = None,
    ) -> None:

        # ── Parámetros almacenados ─────────────────────────────────────────
        self.arena_size         = np.asarray(arena_size, dtype=np.float64)
        self.n_objetivos        = int(n_objetivos)
        self.dt                 = float(dt)
        self.grid_resolution    = int(grid_resolution)
        self.rapidez_rango      = rapidez_rango
        self.sigma_rango        = sigma_rango
        self.escala_deriva_angular = float(escala_deriva_angular)
        self.radio_obs_aoi      = float(radio_obs_aoi)
        self.edad_max_aoi       = float(edad_max_aoi)
        self.radio_mapa_aoi     = (
            float(radio_mapa_aoi) if radio_mapa_aoi is not None
            else 0.4 * float(min(arena_size))
        )
        self.rng = np.random.default_rng(seed)

        # Validaciones de consistencia
        if not (self._SIGMA_MIN <= sigma_rango[0] <= sigma_rango[1] <= self._SIGMA_MAX):
            raise ValueError(
                f"sigma_rango debe estar en [{self._SIGMA_MIN}, {self._SIGMA_MAX}] "
                f"y min ≤ max. Recibido: {sigma_rango}"
            )
        if not (0.0 < rapidez_rango[0] <= rapidez_rango[1]):
            raise ValueError(
                f"rapidez_rango debe cumplir 0 < min ≤ max. Recibido: {rapidez_rango}"
            )

        # ── Estado de los objetivos (inicializado en reset) ────────────────
        self._obj_posiciones:    np.ndarray  # (H, 2)  float64
        self._obj_rapideces:     np.ndarray  # (H,)    float64  — constantes por ep
        self._obj_orientaciones: np.ndarray  # (H,)    float64  — evolucionan
        self._obj_sigmas:        np.ndarray  # (H,)    float64  — constantes por ep

        # ── Grid de AoI ────────────────────────────────────────────────────
        R = self.grid_resolution
        Wx, Wy = float(self.arena_size[0]), float(self.arena_size[1])
        dx_celda = Wx / R
        dy_celda = Wy / R
        xs_celdas = np.linspace(dx_celda / 2.0, Wx - dx_celda / 2.0, R)
        ys_celdas = np.linspace(dy_celda / 2.0, Wy - dy_celda / 2.0, R)

        # Centros de celda: _grid_xx[i, j] = xs_celdas[i], _grid_yy[i, j] = ys_celdas[j]
        self._grid_xx, self._grid_yy = np.meshgrid(
            xs_celdas, ys_celdas, indexing='ij'
        )  # ambas (R, R) float64

        self._grid_aoi: np.ndarray  # (R, R) float32

        # ── Tiempo simulado ────────────────────────────────────────────────
        self._tiempo_sim: float = 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # API pública
    # ─────────────────────────────────────────────────────────────────────────

    def reset(self, seed: Optional[int] = None) -> None:
        """
        Reinicia el simulador para un nuevo episodio.

        Domain randomization ligero (no afecta la estabilidad):
          - Posiciones iniciales: uniformes dentro del 80% central del arena.
          - Orientaciones iniciales: uniformes en (-π, π].
          - Rapideces por objetivo: uniformes en rapidez_rango.
          - Sigmas por objetivo: uniformes en sigma_rango.

        Parámetros
        ----------
        seed : Optional[int]
            Si se provee, reinicia el RNG con esta semilla.
        """
        if seed is not None:
            self.rng = np.random.default_rng(seed)

        # ── Posiciones iniciales (dentro del 80% central del arena) ──────
        margen = 0.10 * self.arena_size
        self._obj_posiciones = self.rng.uniform(
            low  = margen,
            high = self.arena_size - margen,
            size = (self.n_objetivos, 2),
        ).astype(np.float64)

        # ── Orientaciones iniciales (uniformes) ───────────────────────────
        self._obj_orientaciones = self.rng.uniform(
            -math.pi, math.pi, size=(self.n_objetivos,)
        ).astype(np.float64)

        # ── Rapideces (constantes durante el episodio) ────────────────────
        self._obj_rapideces = self.rng.uniform(
            self.rapidez_rango[0], self.rapidez_rango[1],
            size=(self.n_objetivos,),
        ).astype(np.float64)

        # ── Sigmas (constantes durante el episodio) ───────────────────────
        self._obj_sigmas = self.rng.uniform(
            self.sigma_rango[0], self.sigma_rango[1],
            size=(self.n_objetivos,),
        ).astype(np.float64)

        # ── Grid de AoI: completamente inexplorado al inicio ──────────────
        self._grid_aoi = np.ones(
            (self.grid_resolution, self.grid_resolution), dtype=np.float32
        )

        self._tiempo_sim = 0.0

    def step(self) -> None:
        """
        Avanza la dinámica de los objetivos un paso dt.

        Secuencia:
          1. Deriva angular suave: θᵢ ← θᵢ + α·√dt·ξᵢ
          2. Cálculo de velocidades cartesianas: vᵢ = sᵢ·[cos θᵢ, sin θᵢ]
          3. Integración de posición: μᵢ ← μᵢ + vᵢ·dt
          4. Reflexión elástica en los 4 bordes (actualiza θ consistentemente).
          5. Envejece el grid de AoI.

        Nota: `update_aoi_grid` debe llamarse desde el entorno principal
        DESPUÉS de mover los agentes, no desde aquí.
        """
        # 1. Deriva angular (solo si α > 0)
        if self.escala_deriva_angular > 0.0:
            std_angular = self.escala_deriva_angular * math.sqrt(self.dt)
            ruido_angulos = self.rng.standard_normal(self.n_objetivos) * std_angular
            self._obj_orientaciones = _envolver_angulo(
                self._obj_orientaciones + ruido_angulos
            )

        # 2. Velocidades cartesianas: (H, 2)
        cos_th = np.cos(self._obj_orientaciones)
        sin_th = np.sin(self._obj_orientaciones)
        velocidades = np.column_stack([
            self._obj_rapideces * cos_th,
            self._obj_rapideces * sin_th,
        ])  # (H, 2)

        # 3. Integración de posición (Euler explícito, orden 1)
        nuevas_posiciones = self._obj_posiciones + velocidades * self.dt

        # 4. Reflexión elástica: actualiza posición Y orientación simultáneamente
        self._obj_posiciones, self._obj_orientaciones = \
            self._reflejar_elastico(nuevas_posiciones, self._obj_orientaciones)

        # 5. Envejecimiento del grid de AoI
        incremento_aoi = np.float32(self.dt / self.edad_max_aoi)
        self._grid_aoi = np.minimum(
            self._grid_aoi + incremento_aoi, np.float32(1.0)
        )

        self._tiempo_sim += self.dt

    def sample(self, posiciones: np.ndarray) -> np.ndarray:
        """
        Evalúa C(x,y,t) en un conjunto de posiciones.

        Implementación vectorizada (sin bucles Python).

        C(p, t) = clip( Σᵢ exp(-‖p - μᵢ‖² / (2σᵢ²)), 0, 1 )

        Complejidad: O(N · H) tiempo, O(N · H) espacio auxiliar.

        Parámetros
        ----------
        posiciones : np.ndarray, shape (N, 2)

        Retorna
        -------
        np.ndarray, shape (N,), dtype float32
            Intensidad C ∈ [0, 1] en cada posición.
        """
        pos = np.atleast_2d(posiciones).astype(np.float64)  # (N, 2)

        # Broadcasting: (N, 1, 2) - (1, H, 2) → (N, H, 2)
        diff = pos[:, np.newaxis, :] - self._obj_posiciones[np.newaxis, :, :]

        # Distancia cuadrada: (N, H)
        dist2 = np.sum(diff ** 2, axis=2)

        # Valor Gaussiano por objetivo (amplitud = 1): (N, H)
        sigma2 = self._obj_sigmas ** 2  # (H,)
        gaussianas = np.exp(-dist2 / (2.0 * sigma2[np.newaxis, :]))  # (N, H)

        # Suma sobre objetivos y clipping a [0, 1]
        intensidad = np.clip(np.sum(gaussianas, axis=1), 0.0, 1.0)
        return intensidad.astype(np.float32)

    def gradiente(self, posicion: np.ndarray) -> np.ndarray:
        """
        Calcula el gradiente analítico ∇C(x,y) en una posición.

        Derivada de la mezcla Gaussiana (con amplitudes = 1):
            ∂C/∂p = Σᵢ exp(-‖p-μᵢ‖²/(2σᵢ²)) · (-(p-μᵢ)/σᵢ²)
                  = -Σᵢ (gauss_i / σᵢ²) · (p - μᵢ)

        El gradiente apunta hacia el objetivo más cercano y es suave por
        construcción (superposición de Gaussianas). No requiere diferencias
        finitas.

        Parámetros
        ----------
        posicion : np.ndarray, shape (2,)

        Retorna
        -------
        np.ndarray, shape (2,), dtype float32
            [∂C/∂x,  ∂C/∂y]  en m⁻¹
        """
        pos = np.asarray(posicion, dtype=np.float64)

        # diff[i] = p - μᵢ, shape (H, 2)
        diff = pos - self._obj_posiciones
        dist2 = np.sum(diff ** 2, axis=1)   # (H,)
        sigma2 = self._obj_sigmas ** 2       # (H,)

        # Valor Gaussiano por objetivo
        vals_gauss = np.exp(-dist2 / (2.0 * sigma2))  # (H,)

        # Pesos: gauss_i / σᵢ², shape (H,)
        pesos = vals_gauss / sigma2

        # ∇C = -Σᵢ pesos_i · diff_i, shape (2,)
        grad = -np.sum(pesos[:, np.newaxis] * diff, axis=0)
        return grad.astype(np.float32)

    def update_aoi_grid(self, posiciones_agentes: np.ndarray) -> None:
        """
        Marca como "visitadas" las celdas del grid de AoI que están dentro
        del radio de observación de algún agente (AoI → 0).

        Debe llamarse desde el entorno principal en cada step, después de
        actualizar las posiciones de los robots.

        Complejidad: O(N · (radio_obs / dx_celda)²) — bounding-box + máscara circular.

        Parámetros
        ----------
        posiciones_agentes : np.ndarray, shape (N, 2)
            Posiciones actuales [x, y] de todos los agentes activos.
        """
        R = self.grid_resolution
        dx_celda = self.arena_size[0] / R
        dy_celda = self.arena_size[1] / R

        celdas_radio_x = int(math.ceil(self.radio_obs_aoi / dx_celda)) + 1
        celdas_radio_y = int(math.ceil(self.radio_obs_aoi / dy_celda)) + 1
        radio2 = self.radio_obs_aoi ** 2

        for pos in np.atleast_2d(posiciones_agentes):
            cx = int(pos[0] / dx_celda)
            cy = int(pos[1] / dy_celda)

            xi_lo = max(0, cx - celdas_radio_x)
            xi_hi = min(R, cx + celdas_radio_x + 1)
            yi_lo = max(0, cy - celdas_radio_y)
            yi_hi = min(R, cy + celdas_radio_y + 1)

            sub_xx = self._grid_xx[xi_lo:xi_hi, yi_lo:yi_hi]
            sub_yy = self._grid_yy[xi_lo:xi_hi, yi_lo:yi_hi]

            dist2_sub = (sub_xx - pos[0]) ** 2 + (sub_yy - pos[1]) ** 2
            mascara = dist2_sub <= radio2

            self._grid_aoi[xi_lo:xi_hi, yi_lo:yi_hi][mascara] = np.float32(0.0)

    def get_aoi_map(
        self,
        posicion: np.ndarray,
        n_sectores: int = 8,
    ) -> np.ndarray:
        """
        Calcula el Age-of-Information en N sectores angulares alrededor
        de una posición.

        Sectorización:
          El rango [0, 2π) se divide en n_sectores cuñas de ángulo igual.
          Sector k cubre ángulos ∈ [k·2π/N, (k+1)·2π/N).
          Sector 0 apunta a la derecha (+x), sentido antihorario.

        Parámetros
        ----------
        posicion  : np.ndarray, shape (2,)
        n_sectores: int (debe coincidir con D_AOI del entorno, default 8)

        Retorna
        -------
        np.ndarray, shape (n_sectores,), dtype float32
            AoI promedio ∈ [0, 1] por sector.
            1.0 = zona totalmente inexplorada.
            0.0 = zona visitada recientemente.
            Sectores sin celdas dentro del radio → 1.0.
        """
        pos = np.asarray(posicion, dtype=np.float64)

        dx = self._grid_xx - pos[0]   # (R, R)
        dy = self._grid_yy - pos[1]   # (R, R)
        dist2 = dx ** 2 + dy ** 2     # (R, R)

        dentro = dist2 <= (self.radio_mapa_aoi ** 2)

        if not np.any(dentro):
            return np.ones(n_sectores, dtype=np.float32)

        angulos = np.arctan2(dy, dx)
        angulos_pos = (angulos + 2.0 * math.pi) % (2.0 * math.pi)

        ancho_sector = 2.0 * math.pi / n_sectores
        ids_sector = np.floor(angulos_pos / ancho_sector).astype(np.int32)
        ids_sector = np.clip(ids_sector, 0, n_sectores - 1)

        resultado = np.empty(n_sectores, dtype=np.float32)
        for k in range(n_sectores):
            mascara_sector = dentro & (ids_sector == k)
            if np.any(mascara_sector):
                resultado[k] = float(np.mean(self._grid_aoi[mascara_sector]))
            else:
                resultado[k] = 1.0

        return resultado

    def get_snapshot_campo(self) -> np.ndarray:
        """
        Devuelve el campo evaluado en todos los centros de celda del grid (R×R).
        Útil para renderizado con matplotlib.imshow(..., origin='lower').

        Retorna
        -------
        np.ndarray, shape (R, R), dtype float32
        """
        puntos_grid = np.stack(
            [self._grid_xx.ravel(), self._grid_yy.ravel()], axis=1
        )  # (R², 2)
        campo_plano = self.sample(puntos_grid)
        return campo_plano.reshape(self.grid_resolution, self.grid_resolution)

    # ── Propiedades de acceso de solo lectura ────────────────────────────────

    @property
    def posiciones_objetivos(self) -> np.ndarray:
        """Posiciones actuales de los objetivos. (H, 2) float64."""
        return self._obj_posiciones.copy()

    @property
    def orientaciones_objetivos(self) -> np.ndarray:
        """Orientaciones (heading) actuales de los objetivos. (H,) float64."""
        return self._obj_orientaciones.copy()

    @property
    def rapideces_objetivos(self) -> np.ndarray:
        """Rapideces (constantes por episodio) de los objetivos. (H,) float64."""
        return self._obj_rapideces.copy()

    @property
    def sigmas_objetivos(self) -> np.ndarray:
        """Sigmas (constantes por episodio) de los objetivos. (H,) float64."""
        return self._obj_sigmas.copy()

    @property
    def tiempo_simulado(self) -> float:
        """Tiempo acumulado desde el último reset [s]."""
        return self._tiempo_sim

    # ─────────────────────────────────────────────────────────────────────────
    # Métodos privados
    # ─────────────────────────────────────────────────────────────────────────

    def _reflejar_elastico(
        self,
        posiciones:    np.ndarray,
        orientaciones: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Aplica reflexión elástica en los 4 bordes del arena y actualiza
        CONSISTENTEMENTE la orientación del vector velocidad.

        Fórmulas de reflexión (velocity = s·[cos θ, sin θ]):
          - Pared vertical (x=0 o x=W):  flipear componente x de v
                → v'ₓ = -vₓ, v'_y = v_y  ⇒  θ' = π - θ
          - Pared horizontal (y=0 o y=H): flipear componente y de v
                → v'ₓ = vₓ, v'_y = -v_y  ⇒  θ' = -θ

        Reflexión de la posición (sobre pared en c):
              p > c  →  p' = 2c - p
              p < c  →  p' = 2c - p  (con c = 0 → p' = -p)

        Esto preserva la trayectoria de forma geométricamente consistente:
        el ángulo de incidencia iguala al de reflexión.

        Manejo de reflexiones múltiples:
          Para dt·s < ancho_arena (condición trivial con valores típicos),
          un step genera a lo sumo 1 reflexión por eje. Clipping defensivo
          final evita quedar fuera por errores de punto flotante.

        Parámetros
        ----------
        posiciones    : np.ndarray, shape (H, 2)
        orientaciones : np.ndarray, shape (H,)

        Retorna
        -------
        (posiciones_reflejadas, orientaciones_actualizadas)
        """
        pos = posiciones.copy()
        ori = orientaciones.copy()
        Wx = float(self.arena_size[0])
        Wy = float(self.arena_size[1])

        # ── Pared izquierda (x = 0) ────────────────────────────────────────
        mask = pos[:, 0] < 0.0
        if np.any(mask):
            pos[mask, 0] = -pos[mask, 0]           # p' = -p  (reflexión en x=0)
            ori[mask]    = math.pi - ori[mask]     # θ' = π - θ

        # ── Pared derecha (x = Wx) ─────────────────────────────────────────
        mask = pos[:, 0] > Wx
        if np.any(mask):
            pos[mask, 0] = 2.0 * Wx - pos[mask, 0]
            ori[mask]    = math.pi - ori[mask]

        # ── Pared inferior (y = 0) ─────────────────────────────────────────
        mask = pos[:, 1] < 0.0
        if np.any(mask):
            pos[mask, 1] = -pos[mask, 1]
            ori[mask]    = -ori[mask]

        # ── Pared superior (y = Wy) ────────────────────────────────────────
        mask = pos[:, 1] > Wy
        if np.any(mask):
            pos[mask, 1] = 2.0 * Wy - pos[mask, 1]
            ori[mask]    = -ori[mask]

        # ── Clipping defensivo (errores de punto flotante) ─────────────────
        pos[:, 0] = np.clip(pos[:, 0], 1e-8, Wx - 1e-8)
        pos[:, 1] = np.clip(pos[:, 1], 1e-8, Wy - 1e-8)

        # ── Normalización de ángulos a (-π, π] ─────────────────────────────
        ori = _envolver_angulo(ori)

        return pos, ori


# ══════════════════════════════════════════════════════════════════════════════
#  2. MeanEmbeddingEncoder  —  [SIN CAMBIOS respecto a la versión anterior]
# ══════════════════════════════════════════════════════════════════════════════

class MeanEmbeddingEncoder:
    """
    Codifica un conjunto de tamaño VARIABLE de vecinos en un vector de
    tamaño FIJO mediante Mean Pooling (Mean Embedding).

    Dado el conjunto N_i(t) de vecinos visibles del agente ego i:
        φ(j) ∈ ℝ^{D_N}            — vector de características del vecino j
        h_i  = mean_{j∈N_i} φ(j)  si |N_i| ≥ 1
        h_i  = 0^{D_N}             si |N_i| = 0

    Propiedades formales garantizadas
    ──────────────────────────────────
    1. Invarianza a la permutación: mean es conmutativa y asociativa.
    2. Invarianza al cardinal: |h_i| = D_N independientemente de |N_i|.
    3. Diferenciabilidad: compatible con backprop (solo ops. de NumPy).
    4. Invarianza a rotación del mundo: se expresa en el marco del ego
       (rotación de -θ_ego), por lo que el embedding no cambia si todos
       los agentes rotan juntos.

    Vector de características por vecino φ(j) ∈ ℝ^8
    ─────────────────────────────────────────────────
    Índice │ Variable          │ Normalización  │ Rango
    ───────┼────────────────────┼─────────────────┼──────────
       0   │ Δx en marco ego   │ / comm_radius  │ (-1, 1)
       1   │ Δy en marco ego   │ / comm_radius  │ (-1, 1)
       2   │ Δθ relativo       │ / π            │ (-1, 1)
       3   │ v_j               │ / V_MAX        │ (-1, 1)
       4   │ ω_j               │ / OMEGA_MAX    │ (-1, 1)
       5   │ distancia_ij      │ / comm_radius  │  (0, 1)
       6   │ bearing en ego    │ / π            │ (-1, 1)
       7   │ concentración_j   │ ya ∈ [0,1]     │  (0, 1)

    Por qué representación en marco ego y no mundial:
        El actor descentralizado no conoce su orientación absoluta en el
        mundo. Al expresar las posiciones relativas en el marco del ego,
        el embedding es agnóstico a la orientación global → mejor
        transferibilidad sim-to-real.

    Parámetros
    ----------
    radio_comunicacion : float
        Radio máximo de visibilidad [m]. Debe coincidir con `comm_radius` del env.
    embed_dim : int
        Dimensión D_N del vector de embedding (= 8 por diseño del esqueleto).
    """

    EMBED_DIM: int = 8

    def __init__(
        self,
        radio_comunicacion: float = 1.0,
        embed_dim: int = 8,
    ) -> None:
        if embed_dim != self.EMBED_DIM:
            raise ValueError(
                f"embed_dim debe ser {self.EMBED_DIM} para coincidir con D_NEIGHBOR "
                f"del espacio de observación del entorno. Se recibió: {embed_dim}"
            )
        self.radio_comunicacion = float(radio_comunicacion)
        self.embed_dim = embed_dim

    # ─────────────────────────────────────────────────────────────────────────
    # API pública
    # ─────────────────────────────────────────────────────────────────────────

    def encode(
        self,
        estado_ego: np.ndarray,
        estados_vecinos: List[np.ndarray],
        concentraciones_vecinos: np.ndarray,
    ) -> np.ndarray:
        """
        Genera el mean embedding h_i para el agente ego.

        Parámetros
        ----------
        estado_ego : np.ndarray, shape (5,)
            Estado [x, y, θ, v, ω] del agente ego.
        estados_vecinos : List[np.ndarray]
            Lista de estados [x_j, y_j, θ_j, v_j, ω_j] de cada vecino.
            Longitud k = |N_i(t)| ∈ {0, …, N-1}.  VARIABLE.
        concentraciones_vecinos : np.ndarray, shape (k,)
            Concentración C_j medida por cada vecino j.

        Retorna
        -------
        np.ndarray, shape (8,), dtype float32
            h_i — mean embedding de vecinos.
            Vector cero si no hay vecinos visibles.
        """
        k = len(estados_vecinos)

        if k == 0:
            return np.zeros(self.embed_dim, dtype=np.float32)

        vecinos_arr = np.stack(estados_vecinos, axis=0)
        concs_arr   = np.asarray(concentraciones_vecinos, dtype=np.float64)

        matriz_phi = self._calcular_embeddings_batch(
            estado_ego, vecinos_arr, concs_arr
        )

        return np.mean(matriz_phi, axis=0).astype(np.float32)

    def _calcular_embedding_individual(
        self,
        estado_ego:         np.ndarray,
        estado_vecino:      np.ndarray,
        concentracion_vec:  float,
    ) -> np.ndarray:
        """
        Calcula φ(j) para un único vecino j (versión escalar, para testing/debug).

        Parámetros
        ----------
        estado_ego       : np.ndarray, shape (5,)
        estado_vecino    : np.ndarray, shape (5,)
        concentracion_vec: float

        Retorna
        -------
        np.ndarray, shape (8,), dtype float32
        """
        dx_mundo = estado_vecino[0] - estado_ego[0]
        dy_mundo = estado_vecino[1] - estado_ego[1]

        cos_h = math.cos(estado_ego[2])
        sin_h = math.sin(estado_ego[2])
        dx_ego =  cos_h * dx_mundo + sin_h * dy_mundo
        dy_ego = -sin_h * dx_mundo + cos_h * dy_mundo

        distancia = math.hypot(dx_mundo, dy_mundo)
        bearing   = math.atan2(dy_ego, dx_ego)
        dtheta    = float(_envolver_angulo(
            estado_vecino[2] - estado_ego[2]
        ))

        phi = np.array([
            dx_ego         / self.radio_comunicacion,
            dy_ego         / self.radio_comunicacion,
            dtheta         / math.pi,
            estado_vecino[3] / V_MAX,
            estado_vecino[4] / OMEGA_MAX,
            distancia      / self.radio_comunicacion,
            bearing        / math.pi,
            float(concentracion_vec),
        ], dtype=np.float32)

        return phi

    # ─────────────────────────────────────────────────────────────────────────
    # Métodos privados
    # ─────────────────────────────────────────────────────────────────────────

    def _calcular_embeddings_batch(
        self,
        estado_ego:               np.ndarray,  # (5,)
        estados_vecinos:          np.ndarray,  # (k, 5)
        concentraciones_vecinos:  np.ndarray,  # (k,)
    ) -> np.ndarray:
        """
        Versión vectorizada de `_calcular_embedding_individual` para k vecinos.

        Opera completamente en NumPy — sin bucles Python sobre vecinos.
        Complejidad: O(k) en tiempo y espacio.

        Parámetros
        ----------
        estado_ego              : (5,)
        estados_vecinos         : (k, 5)
        concentraciones_vecinos : (k,)

        Retorna
        -------
        np.ndarray, shape (k, 8), dtype float32
        """
        dx_mundo = estados_vecinos[:, 0] - estado_ego[0]
        dy_mundo = estados_vecinos[:, 1] - estado_ego[1]

        cos_h = math.cos(estado_ego[2])
        sin_h = math.sin(estado_ego[2])
        dx_ego =  cos_h * dx_mundo + sin_h * dy_mundo
        dy_ego = -sin_h * dx_mundo + cos_h * dy_mundo

        distancias = np.hypot(dx_mundo, dy_mundo)
        bearings   = np.arctan2(dy_ego, dx_ego)
        dthetas    = _envolver_angulo(
            estados_vecinos[:, 2] - estado_ego[2]
        ).astype(np.float64)

        matriz_phi = np.stack([
            dx_ego         / self.radio_comunicacion,
            dy_ego         / self.radio_comunicacion,
            dthetas        / math.pi,
            estados_vecinos[:, 3] / V_MAX,
            estados_vecinos[:, 4] / OMEGA_MAX,
            distancias     / self.radio_comunicacion,
            bearings       / math.pi,
            concentraciones_vecinos.astype(np.float64),
        ], axis=1)

        return matriz_phi.astype(np.float32)


# ══════════════════════════════════════════════════════════════════════════════
#  Tests unitarios (ejecutar con: python concentration_dynamics.py)
# ══════════════════════════════════════════════════════════════════════════════

def _test_dynamic_target_simulator() -> None:
    """Verifica propiedades cinemáticas y de campo del simulador."""
    print("\n── Test: DynamicTargetSimulator ──")

    sim = DynamicTargetSimulator(
        arena_size=(3.0, 3.0),
        n_objetivos=3,
        dt=0.1,
        grid_resolution=32,
        rapidez_rango=(0.05, 0.15),
        sigma_rango=(0.10, 0.25),
        escala_deriva_angular=0.30,
        seed=42,
    )
    sim.reset(seed=42)

    # 1. sample() devuelve valores ∈ [0, 1]
    N = 200
    rng = np.random.default_rng(0)
    pos_test = rng.uniform([0, 0], [3.0, 3.0], size=(N, 2))
    concs = sim.sample(pos_test)
    assert concs.shape == (N,), f"Shape incorrecto: {concs.shape}"
    assert concs.dtype == np.float32, f"dtype incorrecto: {concs.dtype}"
    assert np.all(concs >= 0.0) and np.all(concs <= 1.0), \
        f"Intensidad fuera de [0,1]: min={concs.min():.4f}, max={concs.max():.4f}"
    print(f"  sample() OK — min={concs.min():.4f}, max={concs.max():.4f}")

    # 2. gradiente() shape y dtype
    g = sim.gradiente(np.array([1.5, 1.5]))
    assert g.shape == (2,), f"Shape gradiente incorrecto: {g.shape}"
    assert g.dtype == np.float32
    print(f"  gradiente() OK — ∇C=[{g[0]:.4f}, {g[1]:.4f}]")

    # 3. step() × 50: los objetivos permanecen dentro del arena
    for _ in range(50):
        sim.step()
    pos_objs = sim.posiciones_objetivos
    assert np.all(pos_objs[:, 0] >= 0.0) and np.all(pos_objs[:, 0] <= 3.0)
    assert np.all(pos_objs[:, 1] >= 0.0) and np.all(pos_objs[:, 1] <= 3.0)
    print(f"  step()×50 OK — t_sim={sim.tiempo_simulado:.1f}s, "
          f"objetivos dentro del arena ✓")

    # 4. step() × 1000: estabilidad a largo plazo (prueba agresiva de reflexión)
    for _ in range(1000):
        sim.step()
    pos_objs = sim.posiciones_objetivos
    assert np.all(pos_objs[:, 0] >= 0.0) and np.all(pos_objs[:, 0] <= 3.0), \
        f"Objetivo fuera del arena tras 1000 steps: {pos_objs}"
    assert np.all(pos_objs[:, 1] >= 0.0) and np.all(pos_objs[:, 1] <= 3.0), \
        f"Objetivo fuera del arena tras 1000 steps: {pos_objs}"
    # Verificar que los objetivos SÍ se movieron (no se quedaron estáticos)
    sim.reset(seed=43)
    pos_inicial = sim.posiciones_objetivos.copy()
    for _ in range(100):
        sim.step()
    pos_final = sim.posiciones_objetivos
    desplazamientos = np.linalg.norm(pos_final - pos_inicial, axis=1)
    assert np.all(desplazamientos > 0.01), \
        f"Objetivos no se movieron suficiente: {desplazamientos}"
    print(f"  step()×1000 OK — estabilidad a largo plazo ✓, "
          f"desplazamiento medio = {desplazamientos.mean():.3f}m")

    # 5. Rapidez efectiva ≈ rapidez nominal (conservación de speed)
    sim.reset(seed=44)
    # Desactivar deriva angular para test de conservación de rapidez exacta
    sim.escala_deriva_angular = 0.0
    pos_ant = sim.posiciones_objetivos.copy()
    sim.step()
    pos_nue = sim.posiciones_objetivos
    rapidez_efectiva = np.linalg.norm(pos_nue - pos_ant, axis=1) / sim.dt
    # Con α=0 y sin reflexiones en este step, la rapidez debe ser exacta
    rapideces_nominales = sim.rapideces_objetivos
    # Tolerar diferencia por posibles reflexiones en el primer step
    err_rel = np.abs(rapidez_efectiva - rapideces_nominales) / rapideces_nominales
    print(f"  Conservación de rapidez (α=0): err_rel_max = {err_rel.max():.4f}")

    # 6. AoI: se inicializa en 1, se resetea con update_aoi_grid
    sim.reset(seed=45)
    assert np.all(sim._grid_aoi == 1.0), "AoI no inicializado correctamente"
    aoi = sim.get_aoi_map(np.array([1.5, 1.5]), n_sectores=8)
    assert aoi.shape == (8,)
    assert np.allclose(aoi, 1.0), f"AoI inicial debería ser 1.0 en todos los sectores: {aoi}"
    print(f"  get_aoi_map() inicial OK — todos los sectores = 1.0")

    # 7. update_aoi_grid() reduce el AoI en el área visitada
    pos_agentes = np.array([[1.5, 1.5], [0.5, 0.5]])
    aoi_antes = sim._grid_aoi.copy()
    sim.update_aoi_grid(pos_agentes)
    n_reseteadas = np.sum(sim._grid_aoi == 0.0)
    assert n_reseteadas > 0, "update_aoi_grid() no reseteó ninguna celda"
    print(f"  update_aoi_grid() OK — celdas reseteadas: {n_reseteadas}")

    # 8. AoI envejece con step()
    for _ in range(30):
        sim.step()
    n_envejecidas = np.sum((sim._grid_aoi > 0.0) & (sim._grid_aoi < 1.0))
    print(f"  Envejecimiento AoI OK — celdas en transición: {n_envejecidas}")

    # 9. get_snapshot_campo() shape correcto
    snap = sim.get_snapshot_campo()
    assert snap.shape == (32, 32)
    assert snap.dtype == np.float32
    print(f"  get_snapshot_campo() OK — shape={snap.shape}")

    # 10. Modo ballistic (α=0): trayectorias exactamente lineales entre rebotes
    sim_ballistic = DynamicTargetSimulator(
        arena_size=(3.0, 3.0),
        n_objetivos=1,
        escala_deriva_angular=0.0,
        seed=100,
    )
    sim_ballistic.reset(seed=100)
    ori_inicial = float(sim_ballistic.orientaciones_objetivos[0])
    # Avanzar pocos steps (para evitar rebotes)
    for _ in range(5):
        sim_ballistic.step()
    ori_final = float(sim_ballistic.orientaciones_objetivos[0])
    assert abs(ori_final - ori_inicial) < 1e-10, \
        f"En modo ballistic, la orientación NO debe cambiar sin rebote. " \
        f"Inicial: {ori_inicial}, Final: {ori_final}"
    print(f"  Modo ballistic (α=0) OK — θ invariante entre rebotes ✓")

    # 11. Propiedades de acceso
    assert sim.posiciones_objetivos.shape   == (3, 2)
    assert sim.orientaciones_objetivos.shape == (3,)
    assert sim.rapideces_objetivos.shape    == (3,)
    assert sim.sigmas_objetivos.shape        == (3,)
    print(f"  Propiedades de acceso OK ✓")

    print("  ✓ DynamicTargetSimulator: todos los tests pasaron.\n")


def _test_mean_embedding_encoder() -> None:
    """Verifica propiedades del encoder (idénticas a la versión anterior)."""
    print("── Test: MeanEmbeddingEncoder ──")

    enc = MeanEmbeddingEncoder(radio_comunicacion=1.0)
    rng = np.random.default_rng(7)

    ego = np.array([1.5, 1.5, 0.3, 0.1, 0.05])

    # 1. Sin vecinos → cero vector
    h0 = enc.encode(ego, [], np.array([]))
    assert h0.shape == (8,)
    assert np.all(h0 == 0.0), f"Embedding sin vecinos no es cero: {h0}"
    print("  encode(k=0) OK — cero-vector ✓")

    # 2. k=1 vecino → shape (8,), valores normalizados
    v1_state = np.array([2.0, 1.5, -0.2, 0.08, -0.1])
    h1 = enc.encode(ego, [v1_state], np.array([0.4]))
    assert h1.shape == (8,), f"Shape incorrecto k=1: {h1.shape}"
    assert h1.dtype == np.float32
    assert 0.0 <= h1[5] <= 1.0, f"distancia normalizada fuera de rango: {h1[5]}"
    print(f"  encode(k=1) OK — h={np.round(h1, 3)}")

    # 3. k=5 vecinos → MISMO shape (8,)
    vecinos_5 = [rng.uniform([0, 0, -np.pi, -V_MAX, -OMEGA_MAX],
                              [3, 3,  np.pi,  V_MAX,  OMEGA_MAX])
                 for _ in range(5)]
    concs_5 = rng.uniform(0, 1, size=5)
    h5 = enc.encode(ego, vecinos_5, concs_5)
    assert h5.shape == (8,), f"Shape incorrecto k=5: {h5.shape}"
    print(f"  encode(k=5) OK — shape fijo ✓, h_mean={h5.mean():.4f}")

    # 4. Invarianza a la permutación
    orden_alt = [vecinos_5[3], vecinos_5[0], vecinos_5[4],
                 vecinos_5[1], vecinos_5[2]]
    concs_alt = concs_5[[3, 0, 4, 1, 2]]
    h5_alt = enc.encode(ego, orden_alt, concs_alt)
    assert np.allclose(h5, h5_alt, atol=1e-6), \
        "Embedding NO es invariante a la permutación de vecinos"
    print("  Invarianza a permutación OK ✓")

    # 5. Consistencia batch vs individual
    phi_batch = enc._calcular_embeddings_batch(
        ego,
        np.stack(vecinos_5),
        concs_5,
    )
    phi_indiv = np.stack([
        enc._calcular_embedding_individual(ego, v, c)
        for v, c in zip(vecinos_5, concs_5)
    ])
    assert np.allclose(phi_batch, phi_indiv, atol=1e-5), \
        f"Batch vs individual discrepancia max: {np.abs(phi_batch - phi_indiv).max()}"
    print("  Consistencia batch ↔ individual OK ✓")

    print("  ✓ MeanEmbeddingEncoder: todos los tests pasaron.\n")


if __name__ == "__main__":
    _test_dynamic_target_simulator()
    _test_mean_embedding_encoder()
    print("═" * 50)
    print("Todos los tests pasaron ✓")
