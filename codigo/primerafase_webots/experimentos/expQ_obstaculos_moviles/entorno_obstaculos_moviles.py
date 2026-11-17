"""
entorno_obstaculos_moviles.py
=============================
Obstáculos circulares MÓVILES para el Exp Q (la versión dinámica del Exp O),
por HERENCIA sobre la copia byte-idéntica de `entorno_obstaculos.py` del Exp O
(sha256 verificado en `correr_experimento_Q.py`). Nada del Exp O se edita.

Qué agrega (propuesta `tesis/PROPUESTA_expO_dinamico.md`, aprobada el
2026-10-19 con las nueve decisiones recomendadas)
---------------------------------------------------------------------------
1. TRAYECTORIAS. Cada obstáculo es una `TrayectoriaQuieta` (el Exp O y la
   condición "quieto") o una `TrayectoriaCircular` antihoraria a 0,05 m/s. La
   posición se calcula EXACTA desde el índice del paso, sin acumular:

       p(t) = c + ρ·(cos φ(t), sen φ(t)),   φ(t) = φ0 + (v/ρ)·dt·t

   y la velocidad que ve la barrera en la decisión t es la SECANTE del paso,
   (p(t+1) − p(t))/dt: exactamente lo que el obstáculo se desplaza entre esta
   decisión y la siguiente.
2. ORDEN DENTRO DEL PASO. `step` mueve primero los obstáculos de t a t + 1 y
   después llama al paso de siempre: los agentes integran y el contacto
   (disco r + 0,075, proyección radial con θ intacto, el código del Exp O) se
   evalúa contra los discos en t + 1. Así cubre al agente que choca con el
   obstáculo y al obstáculo que choca con el agente. Con trayectorias quietas
   el movimiento no cambia nada y el paso es el del Exp O.
3. MÁSCARA PERMANENTE. Una celda se enmascara si su centro queda dentro de
   algún disco (radio r) en los `n_pasos + 1` instantes del episodio: el
   criterio del Exp O ("centro dentro de r"), extendido en el tiempo. Con
   trayectorias quietas da exactamente la máscara del Exp O.
4. ATRIBUCIÓN DEL CONTACTO (descriptiva; el criterio de falla es el mismo):
   "por empuje" si la posición recién integrada del agente quedaba FUERA de
   todo disco de contacto en t, y "por avance" si ya estaba dentro de alguno.
   Para conocer esa posición antes de la proyección, `_PosicionIntegrada` se
   intercala en el MRO entre `EntornoObstaculos` y el entorno base: el
   `super()` de `EntornoObstaculos._integrate_kinematics` pasa por ella, que
   sólo copia la posición y no cambia nada.

Los objetivos de las condiciones con obstáculos móviles son TRANSPARENTES
(decisión 3): `obstaculos_rebote=()`, la misma perilla del control fantasma
del Exp O. El rebote en un disco que se mueve no está implementado y se niega.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple, Union

import numpy as np

from entorno_obstaculos import (RADIO_CHASIS, CampoConObstaculos,
                                EntornoObstaculos, Obstaculo, mascara_ocupada)
from lib.swarm_env_skeleton import CyanobacteriaMonitoringEnv

#: Velocidad de los obstáculos móviles: la del robot 4 en el laboratorio.
V_OBSTACULO: float = 0.05
#: dt del entorno (`CyanobacteriaMonitoringEnv`, 0,1 s por defecto). El
#: entorno nuevo verifica que coincida con el suyo.
DT_ENTORNO: float = 0.1


# =============================================================================
# TRAYECTORIAS
# =============================================================================

@dataclass(frozen=True)
class TrayectoriaQuieta:
    """Obstáculo quieto en `punto` (x, y) con radio `r`."""
    punto: Tuple[float, float]
    r:     float

    @property
    def mueve(self) -> bool:
        return False

    def posicion(self, t: int) -> Tuple[float, float]:
        """Posición en el paso t: siempre `punto`, sin operar sobre él."""
        return (self.punto[0], self.punto[1])

    def obstaculo(self, t: int) -> Obstaculo:
        """(x, y, r) en el paso t, con los mismos float que `punto` y `r`."""
        return (self.punto[0], self.punto[1], self.r)

    def velocidad(self, t: int) -> np.ndarray:
        """Velocidad del paso t → t + 1: cero."""
        return np.zeros(2, dtype=np.float64)


@dataclass(frozen=True)
class TrayectoriaCircular:
    """
    Círculo antihorario de radio `rho` alrededor de `centro`, a rapidez `v`,
    desde la fase `fase0` [rad]; obstáculo de radio `r`.
    """
    centro: Tuple[float, float]
    rho:    float
    fase0:  float
    r:      float
    v:      float = V_OBSTACULO
    dt:     float = DT_ENTORNO

    def __post_init__(self) -> None:
        if not (self.rho > 0.0 and self.v > 0.0 and self.dt > 0.0):
            raise ValueError("TrayectoriaCircular: rho, v y dt deben ser > 0 "
                             "(un obstáculo quieto es TrayectoriaQuieta).")

    @property
    def mueve(self) -> bool:
        return True

    @property
    def omega(self) -> float:
        """Velocidad angular sobre el círculo [rad/s]."""
        return self.v / self.rho

    def fase(self, t: int) -> float:
        """φ(t) = φ0 + ω·dt·t, desde el índice del paso (sin acumular)."""
        return self.fase0 + self.omega * self.dt * float(t)

    def posicion(self, t: int) -> Tuple[float, float]:
        ph = self.fase(t)
        return (self.centro[0] + self.rho * math.cos(ph),
                self.centro[1] + self.rho * math.sin(ph))

    def obstaculo(self, t: int) -> Obstaculo:
        x, y = self.posicion(t)
        return (x, y, self.r)

    def velocidad(self, t: int) -> np.ndarray:
        """Secante del paso t → t + 1, dividida por dt [m/s]."""
        x0, y0 = self.posicion(t)
        x1, y1 = self.posicion(t + 1)
        return np.array([(x1 - x0) / self.dt, (y1 - y0) / self.dt],
                        dtype=np.float64)


Trayectoria = Union[TrayectoriaQuieta, TrayectoriaCircular]


def obstaculos_en(trayectorias: Sequence[Trayectoria], t: int
                  ) -> Tuple[Obstaculo, ...]:
    """Los obstáculos (x, y, r) en el paso t, en el orden de las trayectorias."""
    return tuple(tr.obstaculo(t) for tr in trayectorias)


def mascara_permanente(trayectorias: Sequence[Trayectoria],
                       xx: np.ndarray, yy: np.ndarray,
                       n_pasos: int) -> np.ndarray:
    """
    Celdas cuyo centro queda dentro de algún disco (radio r) en TODOS los
    instantes 0..n_pasos. Usa `mascara_ocupada` del Exp O en cada instante.
    Sin trayectorias, la máscara vacía (como `mascara_ocupada` con ()).
    """
    if not trayectorias:
        return mascara_ocupada(xx, yy, ())
    m = mascara_ocupada(xx, yy, obstaculos_en(trayectorias, 0))
    for t in range(1, int(n_pasos) + 1):
        if not m.any():
            break
        m &= mascara_ocupada(xx, yy, obstaculos_en(trayectorias, t))
    return m


# =============================================================================
# CAMPO
# =============================================================================

class CampoConObstaculosMoviles(CampoConObstaculos):
    """
    `CampoConObstaculos` del Exp O cuya máscara es la PERMANENTE de las
    trayectorias (se calcula con la propia cuadrícula del campo). El rebote,
    la reubicación de objetivos y la anulación de la máscara son los del Exp O.
    """

    def __init__(self, *args,
                 trayectorias: Sequence[Trayectoria] = (),
                 n_pasos: int = 500,
                 **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.trayectorias: Tuple[Trayectoria, ...] = tuple(trayectorias)
        if self.obstaculos_fisicos:
            self.mascara = mascara_permanente(self.trayectorias, self._grid_xx,
                                              self._grid_yy, n_pasos)


# =============================================================================
# ENTORNO
# =============================================================================

class _PosicionIntegrada(CyanobacteriaMonitoringEnv):
    """
    Eslabón del MRO entre `EntornoObstaculos` y el entorno base: guarda la
    posición recién integrada (ANTES del contacto con obstáculos), para la
    atribución del contacto. No cambia el estado.
    """

    def _integrate_kinematics(self, agent_id: str, action: np.ndarray) -> None:
        super()._integrate_kinematics(agent_id, action)
        self._pos_integrada = np.array(self._estados[agent_id][:2],
                                       dtype=np.float64)


class EntornoObstaculosMoviles(EntornoObstaculos, _PosicionIntegrada):
    """
    `EntornoObstaculos` del Exp O con obstáculos que siguen trayectorias.

    Parámetros
    ----------
    trayectorias      : una por obstáculo; sus posiciones en t = 0 son las del
                        sorteo de poses y objetivos (reubicación del Exp O
                        respecto de la posición INICIAL).
    fisicos           : True = barrera, contacto y máscara (condiciones con
                        obstáculos); False = sólo sorteo (control).
    obstaculos_rebote : como en el Exp O. Con alguna trayectoria móvil tiene
                        que ser () (objetivos transparentes, decisión 3).
    """

    def __init__(self,
                 trayectorias: Sequence[Trayectoria] = (),
                 fisicos: bool = True,
                 obstaculos_rebote: Optional[Sequence[Obstaculo]] = None,
                 **kwargs) -> None:
        trayectorias = tuple(trayectorias)
        if any(tr.mueve for tr in trayectorias) and (
                obstaculos_rebote is None or tuple(obstaculos_rebote) != ()):
            raise ValueError("con obstáculos móviles los objetivos son "
                             "transparentes: obstaculos_rebote=() (decisión 3)")
        obst0 = obstaculos_en(trayectorias, 0)
        super().__init__(obstaculos_fisicos=obst0 if fisicos else (),
                         obstaculos_sorteo=obst0,
                         obstaculos_rebote=obstaculos_rebote, **kwargs)
        for tr in trayectorias:
            if tr.mueve and tr.dt != self.dt:
                raise ValueError(f"dt de la trayectoria {tr.dt} ≠ dt del "
                                 f"entorno {self.dt}")
        self.trayectorias: Tuple[Trayectoria, ...] = trayectorias
        self.fisicos: bool = bool(fisicos)
        # Mismos argumentos con que `EntornoObstaculos` crea su campo, más las
        # trayectorias para la máscara permanente.
        self._field = CampoConObstaculosMoviles(
            arena_size=tuple(float(a) for a in self.arena_size),
            n_objetivos=self.n_hotspots,
            dt=self.dt,
            grid_resolution=self.grid_resolution,
            seed=kwargs.get("seed"),
            obstaculos_fisicos=self.obstaculos_fisicos,
            obstaculos_sorteo=self.obstaculos_sorteo,
            obstaculos_rebote=obstaculos_rebote,
            trayectorias=trayectorias,
            n_pasos=self.max_steps,
        )
        self._t_obst: int = 0
        self._obst_previos: Tuple[Obstaculo, ...] = obst0
        self._pos_integrada: np.ndarray = np.zeros(2)
        self.contactos_empuje: int = 0
        self.contactos_avance: int = 0

    # ── consultas ────────────────────────────────────────────────────────
    @property
    def paso_obstaculos(self) -> int:
        """Índice t de la posición actual de los obstáculos."""
        return self._t_obst

    def posiciones_actuales(self) -> Tuple[Obstaculo, ...]:
        """Obstáculos (x, y, r) en el instante actual (aunque no sean físicos)."""
        return obstaculos_en(self.trayectorias, self._t_obst)

    def velocidades_actuales(self) -> Tuple[np.ndarray, ...]:
        """Velocidad de cada obstáculo en el paso actual → siguiente."""
        return tuple(tr.velocidad(self._t_obst) for tr in self.trayectorias)

    # ── ciclo ────────────────────────────────────────────────────────────
    def reset(self, seed: Optional[int] = None, options=None):
        """Obstáculos en t = 0, contadores nuevos y el reset del Exp O."""
        self._t_obst = 0
        self._obst_previos = obstaculos_en(self.trayectorias, 0)
        if self.fisicos:
            self.obstaculos_fisicos = obstaculos_en(self.trayectorias, 0)
        self.contactos_empuje = 0
        self.contactos_avance = 0
        return super().reset(seed=seed, options=options)

    def step(self, actions: Dict[str, np.ndarray]):
        """Obstáculos de t a t + 1 y, después, el paso de siempre."""
        self._obst_previos = obstaculos_en(self.trayectorias, self._t_obst)
        self._t_obst += 1
        if self.fisicos:
            self.obstaculos_fisicos = obstaculos_en(self.trayectorias,
                                                    self._t_obst)
        return super().step(actions)

    def _integrate_kinematics(self, agent_id: str, action: np.ndarray) -> None:
        """Paso del Exp O (cinemática + contacto) y atribución del contacto."""
        antes = self.contactos_obstaculo.get(agent_id, 0)
        super()._integrate_kinematics(agent_id, action)
        nuevos = self.contactos_obstaculo.get(agent_id, 0) - antes
        if nuevos <= 0:
            return
        p = self._pos_integrada
        ya_dentro = any(math.hypot(float(p[0]) - ox, float(p[1]) - oy)
                        < r + RADIO_CHASIS for ox, oy, r in self._obst_previos)
        if ya_dentro:
            self.contactos_avance += nuevos
        else:
            self.contactos_empuje += nuevos
