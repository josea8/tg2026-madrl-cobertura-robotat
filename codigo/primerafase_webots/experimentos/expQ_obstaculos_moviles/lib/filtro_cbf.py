"""
filtro_cbf.py
=============
Filtro CBF de EJECUCIÓN (safety shield) para el uniciclo Pololu 3pi+ contra
las paredes de la arena. Se interpone entre la política PPO y los motores:
modifica mínimamente la acción nominal (v, ω) para garantizar la invarianza
del conjunto seguro, resolviendo el atascamiento documentado en los
Experimentos A/B (la política fue entrenada con reflexión elástica de pared
y no tiene comportamiento de recuperación ante paredes sólidas).

NO confundir con el término de recompensa p_cbf del entrenamiento
(RewardCalculator._penalty_cbf): aquello moldea el aprendizaje; esto es una
capa de ejecución que garantiza la restricción en tiempo real.

Formulación — punto de mira (look-ahead)
----------------------------------------
La CBF ingenua sobre el CENTRO del uniciclo tiene grado relativo degenerado
en ω: para h(x, y) que solo depende de la posición, ḣ = ∇h·(v·cosθ, v·senθ)
no contiene ω, y el QP solo puede frenar → el robot queda detenido frente a
la pared. Se usa en su lugar el punto de mira adelantado

    p = (x + ℓa·cosθ,  y + ℓa·senθ),   ℓa > 0

cuya dinámica es LINEAL en el control u = (v, ω):

    ṗ = G(θ)·u,   G(θ) = [[cosθ, −ℓa·senθ],
                          [senθ,  ℓa·cosθ]],   det G = ℓa > 0.

La invertibilidad de G restituye grado relativo 1 en ambas entradas: el QP
puede resolver girando además de frenando. Esta construcción es la misma
que emplean los certificados de barrera del Robotarium (Georgia Tech) para
uniciclos, vía el difeomorfismo casi-identidad al punto adelantado
(Pickem et al., "The Robotarium", ICRA 2017; Ames et al., "Control Barrier
Functions: Theory and Applications", ECC 2019).

Barreras y QP
-------------
Cuatro barreras lineales en p para la arena [0, Wx]×[0, Wy] con margen d_s:

    h_izq = p_x − d_s              ∇h = (+1, 0)
    h_der = (Wx − p_x) − d_s       ∇h = (−1, 0)
    h_inf = p_y − d_s              ∇h = (0, +1)
    h_sup = (Wy − p_y) − d_s       ∇h = (0, −1)

Condición CBF con clase-K lineal:  ḣ_i ≥ −α·h_i, que en u es lineal:

    c_i^T·u ≥ −α·h_i,   c_i^T = ∇h_i^T·G(θ).

QP (2 variables, ≤ 4 + extras restricciones + caja):

    min  ((v − v_nom)/V_MAX)² + w·((ω − ω_nom)/Ω_MAX)²
    s.a.  c_i^T·u ≥ −α·h_i  ∀i,   |v| ≤ V_MAX,  |ω| ≤ Ω_MAX

con u_nom clippeado a la caja ANTES de filtrar. Solver: scipy SLSQP con
jacobianos analíticos (converge en 1–3 iteraciones). Corre a 10 Hz (una vez
por decisión de la política); el tiempo de solve es irrelevante.

Casos degenerados conocidos (documentados, no corregidos)
---------------------------------------------------------
1. ESQUINA + bisectriz exacta: con dos barreras ortogonales activas y u_nom
   apuntando exactamente a la bisectriz de la esquina con θ alineado, el
   óptimo puede ser v=0, ω=0 sostenido (equilibrio espurio clásico de CBF).
   Es un conjunto de medida cero; el ruido numérico de la física lo rompe.
   El detector de atasco del modo lote lo mediría si ocurriera.

2. PARED PLANA + θ exactamente perpendicular: si θ es perpendicular a una
   pared (p. ej. θ=90° frente a la pared superior), el coeficiente de ω en
   esa fila se anula (c_sup = (−senθ, −ℓa·cosθ) → (−1, 0)) y esa restricción
   solo puede frenar: v ≤ α·h. El robot se detiene de frente. Se destraba en
   el paso siguiente: como el coeficiente de ω es nulo, la ω de la política
   pasa SIN filtrar → el robot rota en el lugar → θ sale de la perpendicular
   y la componente de giro vuelve a estar disponible.

Factibilidad y fallback
-----------------------
Mientras h_i ≥ 0 ∀i, u = (0,0) es factible (0 ≥ −α·h_i) ⇒ el QP nunca es
infactible dentro del conjunto seguro. Desde violación (h_i < 0) se exige
empuje activo hacia adentro; la capacidad máxima sobre la caja es
V_MAX·|cosθ| + ℓa·Ω_MAX·|senθ| ≥ ~0.22 m/s en el peor ángulo (con
ℓa·Ω_MAX ≈ V_MAX la caja es casi isótropa en ṗ), de modo que con α = 2
son recuperables violaciones de hasta ~0.11 m. Más allá, o si SLSQP no
converge, el fallback es u = (0, 0) + RuntimeWarning.

Extensibilidad (fase de 5 agentes)
----------------------------------
`filtrar(...)` acepta `restricciones_extra`: una lista de RestriccionLineal
(c, h, nombre) ya proyectadas en u. Las barreras robot-robot se agregan ahí
sin reescribir el módulo: mismo QP, más filas.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from typing import List, NamedTuple, Optional, Tuple

import numpy as np
from scipy.optimize import minimize


# =============================================================================
# TIPOS
# =============================================================================

class RestriccionLineal(NamedTuple):
    """
    Restricción CBF ya proyectada en el control u = (v, ω):

        c^T·u ≥ −α·h

    Atributos
    ---------
    c      : np.ndarray shape (2,) — coeficientes de (v, ω).
    h      : float — valor de la barrera (h ≥ 0 dentro del conjunto seguro).
    nombre : str — identificador para diagnóstico ("pared_izq", ...).
    """
    c:      np.ndarray
    h:      float
    nombre: str


@dataclass
class ResultadoFiltroCBF:
    """
    Resultado de una llamada a `FiltroCBFParedes.filtrar`.

    Atributos
    ---------
    u_seguro              : np.ndarray (2,) — acción filtrada [v, ω].
    intervino             : bool — True si u_seguro difiere de u_nominal
                            (magnitud > tolerancia).
    magnitud_modificacion : float — raíz del costo del QP en el óptimo:
                            sqrt(((Δv)/V_MAX)² + w·((Δω)/Ω_MAX)²).
                            Adimensional; 0 si no intervino.
    h_minima              : float — mínimo de las h_i evaluadas (m).
    barrera_activa        : str — nombre de la barrera con h mínima.
    exito_qp              : bool — False si hubo fallback u = (0, 0).
    """
    u_seguro:              np.ndarray
    intervino:             bool
    magnitud_modificacion: float
    h_minima:              float
    barrera_activa:        str
    exito_qp:              bool


# =============================================================================
# FILTRO
# =============================================================================

class FiltroCBFParedes:
    """
    Safety shield CBF con punto de mira para las 4 paredes de la arena.

    Parámetros
    ----------
    arena_size : (Wx, Wy) de la arena en marco env [m].
    ele_a      : ℓa, adelanto del punto de mira [m].
    alfa       : α, ganancia clase-K lineal [1/s].
    d_segura   : d_s, margen del punto de mira a la pared [m].
    w_omega    : peso relativo de ω en el costo (preferir girar a frenar).
    v_max      : cota |v| [m/s].
    omega_max  : cota |ω| [rad/s].
    tol_intervencion : umbral de magnitud para reportar `intervino`.
    """

    def __init__(
        self,
        arena_size:       Tuple[float, float],
        ele_a:            float,
        alfa:             float,
        d_segura:         float,
        w_omega:          float,
        v_max:            float,
        omega_max:        float,
        tol_intervencion: float = 1e-4,
    ) -> None:
        self.arena_size       = (float(arena_size[0]), float(arena_size[1]))
        self.ele_a            = float(ele_a)
        self.alfa             = float(alfa)
        self.d_segura         = float(d_segura)
        self.w_omega          = float(w_omega)
        self.v_max            = float(v_max)
        self.omega_max        = float(omega_max)
        self.tol_intervencion = float(tol_intervencion)

        if self.ele_a <= 0.0:
            raise ValueError("ele_a debe ser > 0 (invertibilidad de G).")

    # ──────────────────────────────────────────────────────────────────────

    def _punto_de_mira(self, pose: np.ndarray) -> np.ndarray:
        """p = (x + ℓa·cosθ, y + ℓa·senθ). Retorna shape (2,)."""
        x, y, th = float(pose[0]), float(pose[1]), float(pose[2])
        return np.array(
            [x + self.ele_a * math.cos(th), y + self.ele_a * math.sin(th)],
            dtype=np.float64,
        )

    def _matriz_G(self, theta: float) -> np.ndarray:
        """G(θ) tal que ṗ = G(θ)·u. Shape (2, 2)."""
        c, s = math.cos(theta), math.sin(theta)
        return np.array(
            [[c, -self.ele_a * s],
             [s,  self.ele_a * c]],
            dtype=np.float64,
        )

    def _barreras_paredes(
        self,
        p:     np.ndarray,
        theta: float,
    ) -> List[RestriccionLineal]:
        """
        Construye las 4 restricciones de pared proyectadas en u.

        Para cada pared: h_i evaluada en el punto de mira, y
        c_i = ∇h_i^T·G(θ) (fila del QP).
        """
        Wx, Wy = self.arena_size
        G = self._matriz_G(theta)

        # (∇h, h, nombre) por pared.
        paredes = [
            (np.array([+1.0, 0.0]), float(p[0]) - self.d_segura,        "pared_izq"),
            (np.array([-1.0, 0.0]), (Wx - float(p[0])) - self.d_segura, "pared_der"),
            (np.array([0.0, +1.0]), float(p[1]) - self.d_segura,        "pared_inf"),
            (np.array([0.0, -1.0]), (Wy - float(p[1])) - self.d_segura, "pared_sup"),
        ]

        return [
            RestriccionLineal(c=grad @ G, h=h, nombre=nombre)
            for grad, h, nombre in paredes
        ]

    # ──────────────────────────────────────────────────────────────────────

    def filtrar(
        self,
        pose:                np.ndarray,
        u_nominal:           np.ndarray,
        restricciones_extra: Optional[List[RestriccionLineal]] = None,
    ) -> ResultadoFiltroCBF:
        """
        Filtra la acción nominal para garantizar las barreras.

        Parámetros
        ----------
        pose      : np.ndarray (3,) — [x, y, θ] en marco env.
        u_nominal : np.ndarray (2,) — [v, ω] de la política (se clipea a la
                    caja de actuador antes de filtrar).
        restricciones_extra : lista opcional de RestriccionLineal adicionales
                    (p. ej. barreras robot-robot en la fase de 5 agentes).

        Retorna
        -------
        ResultadoFiltroCBF
        """
        # ── u_nom clippeado a la caja del actuador ─────────────────────────
        u_nom = np.array([
            float(np.clip(u_nominal[0], -self.v_max,     self.v_max)),
            float(np.clip(u_nominal[1], -self.omega_max, self.omega_max)),
        ], dtype=np.float64)

        # ── Restricciones ──────────────────────────────────────────────────
        p     = self._punto_de_mira(pose)
        theta = float(pose[2])
        restricciones = self._barreras_paredes(p, theta)
        if restricciones_extra:
            restricciones = restricciones + list(restricciones_extra)

        h_min          = min(r.h for r in restricciones)
        barrera_activa = min(restricciones, key=lambda r: r.h).nombre

        # ── Shortcut: u_nom ya factible → no intervenir (costo 0 óptimo) ──
        margen = 1e-9
        if all(
            float(r.c @ u_nom) + self.alfa * r.h >= -margen
            for r in restricciones
        ):
            return ResultadoFiltroCBF(
                u_seguro              = u_nom,
                intervino             = False,
                magnitud_modificacion = 0.0,
                h_minima              = h_min,
                barrera_activa        = barrera_activa,
                exito_qp              = True,
            )

        # ── QP con SLSQP (jacobianos analíticos) ───────────────────────────
        def costo(u: np.ndarray) -> float:
            dv = (u[0] - u_nom[0]) / self.v_max
            dw = (u[1] - u_nom[1]) / self.omega_max
            return dv * dv + self.w_omega * dw * dw

        def jac_costo(u: np.ndarray) -> np.ndarray:
            return np.array([
                2.0 * (u[0] - u_nom[0]) / self.v_max ** 2,
                2.0 * self.w_omega * (u[1] - u_nom[1]) / self.omega_max ** 2,
            ])

        lista_restricciones = [
            {
                "type": "ineq",
                "fun":  (lambda u, c=r.c, h=r.h:
                         float(c @ u) + self.alfa * h),
                "jac":  (lambda u, c=r.c: np.asarray(c, dtype=np.float64)),
            }
            for r in restricciones
        ]
        cotas = [(-self.v_max, self.v_max), (-self.omega_max, self.omega_max)]

        try:
            solucion = minimize(
                costo,
                x0          = u_nom,
                jac         = jac_costo,
                method      = "SLSQP",
                bounds      = cotas,
                constraints = lista_restricciones,
                options     = {"maxiter": 50, "ftol": 1e-10},
            )
            exito = bool(solucion.success)
            # Verificación defensiva: la solución debe satisfacer TODAS las
            # restricciones (SLSQP a veces reporta éxito con violación leve).
            if exito:
                tol_violacion = 1e-6
                exito = all(
                    float(r.c @ solucion.x) + self.alfa * r.h >= -tol_violacion
                    for r in restricciones
                )
        except Exception:
            exito = False

        if not exito:
            warnings.warn(
                f"[FiltroCBF] QP sin solución factible "
                f"(h_min={h_min:.3f} m, barrera={barrera_activa}). "
                f"Fallback u=(0,0).",
                RuntimeWarning,
                stacklevel=2,
            )
            u_seg = np.zeros(2, dtype=np.float64)
        else:
            u_seg = np.asarray(solucion.x, dtype=np.float64)

        magnitud = math.sqrt(costo(u_seg))
        return ResultadoFiltroCBF(
            u_seguro              = u_seg,
            intervino             = magnitud > self.tol_intervencion,
            magnitud_modificacion = magnitud,
            h_minima              = h_min,
            barrera_activa        = barrera_activa,
            exito_qp              = exito,
        )
