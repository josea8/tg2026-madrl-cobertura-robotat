"""
entorno_obstaculos.py
=====================
Obstáculos CIRCULARES estáticos para el Exp O, por HERENCIA sobre las copias
de `lib/` (que quedan byte-idénticas a las del Exp N, verificables por sha256).

Qué agrega y por qué (decisiones aprobadas, ver bitácora Exp O)
----------------------------------------------------------------
1. El obstáculo EXISTE en el entorno, no sólo en el filtro. Contacto físico con
   un disco de radio r + 0,075 m (chasis): si el centro entra, se proyecta
   radialmente al borde y θ queda intacto (misma semántica que el borde
   bloqueante) y se cuenta un contacto. La pared de v2 trata al robot como
   PUNTO: ese tratamiento se hereda de la cadena validada y cambiarlo
   invalidaría la comparabilidad con A–N; el del obstáculo es nuevo y no hay
   razón para replicar una simplificación conocida. La inconsistencia es
   deliberada y va en dirección de mayor realismo.
2. Celdas del AoI OCUPADAS (centro dentro de r) se enmascaran: se fuerzan a
   AoI = 0 tras cada actualización, así la política no las ve como pendientes
   (si no, serían un atractor permanente hacia un lugar donde no cabe). El
   anillo entre r y r + 0,13 NO se enmascara: la huella de 0,15 m lo alcanza.
3. Los objetivos REBOTAN elásticamente en los discos (en r, como en la pared
   física), y los que nacen dentro de un disco se reubican.
4. Poses iniciales: se sortean EXACTAMENTE como en el protocolo (mismo RNG del
   env); sólo los agentes a menos de r + 0,25 m de un obstáculo se reubican con
   un RNG APARTE sembrado con la semilla del episodio. El resto de las poses y
   de los objetivos queda idéntico.

`obstaculos_fisicos` activa 1–3; `obstaculos_sorteo` activa sólo 4. El control
pareado usa fisicos=() y sorteo=escenario: mismas poses iniciales, sin
obstáculos. Con ambos vacíos el entorno es idéntico al original.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import math
from typing import Dict, Optional, Sequence, Tuple

import numpy as np

from lib.concentration_dynamics import DynamicTargetSimulator
from lib.swarm_env_skeleton import D_SAFE, CyanobacteriaMonitoringEnv

Obstaculo = Tuple[float, float, float]   # (x, y, r) [m]

RADIO_CHASIS:      float = 0.075
HOLGURA_ARRANQUE:  float = 0.25   # centro a ≥ r + 0,25 ⇒ h_obst ≥ 0,02 al inicio
HOLGURA_OBJETIVO:  float = 0.05   # objetivos nacen a ≥ r + 0,05


def distancia_minima(p: np.ndarray, obst: Sequence[Obstaculo]) -> float:
    """Distancia del punto `p` a la SUPERFICIE del obstáculo más cercano."""
    if not obst:
        return float("inf")
    return min(math.hypot(p[0] - ox, p[1] - oy) - r for ox, oy, r in obst)


def mascara_ocupada(xx: np.ndarray, yy: np.ndarray,
                    obst: Sequence[Obstaculo]) -> np.ndarray:
    """Celdas cuyo centro cae dentro de algún disco (radio r)."""
    m = np.zeros_like(xx, dtype=bool)
    for ox, oy, r in obst:
        m |= (xx - ox) ** 2 + (yy - oy) ** 2 < r * r
    return m


class CampoConObstaculos(DynamicTargetSimulator):
    """DynamicTargetSimulator con máscara de AoI, rebote y reubicación."""

    def __init__(self, *args,
                 obstaculos_fisicos: Sequence[Obstaculo] = (),
                 obstaculos_sorteo: Sequence[Obstaculo] = (),
                 obstaculos_rebote: Optional[Sequence[Obstaculo]] = None,
                 **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.obstaculos_fisicos: Tuple[Obstaculo, ...] = tuple(obstaculos_fisicos)
        self.obstaculos_sorteo:  Tuple[Obstaculo, ...] = tuple(obstaculos_sorteo)
        # Discos en que REBOTAN los objetivos. Por defecto, los físicos. El
        # control FANTASMA (13/sep) usa rebote = escenario y físicos = ():
        # misma dinámica de objetivos que Sk, sin máscara ni barrera.
        self.obstaculos_rebote: Tuple[Obstaculo, ...] = (
            tuple(obstaculos_rebote) if obstaculos_rebote is not None
            else self.obstaculos_fisicos)
        self.mascara: np.ndarray = mascara_ocupada(
            self._grid_xx, self._grid_yy, self.obstaculos_fisicos)
        self.n_objetivos_reubicados: int = 0
        self.n_rebotes_obstaculo:    int = 0

    def _anular_mascara(self) -> None:
        if self.obstaculos_fisicos:
            self._grid_aoi[self.mascara] = np.float32(0.0)

    def reset(self, seed: Optional[int] = None) -> None:
        """Reset estándar + reubicación de objetivos que nacen en un disco."""
        super().reset(seed=seed)
        self.n_objetivos_reubicados = 0
        self.n_rebotes_obstaculo = 0
        if self.obstaculos_sorteo:
            rng = np.random.default_rng([int(seed or 0), 1])
            margen = 0.10 * self.arena_size
            for h in range(self.n_objetivos):
                if distancia_minima(self._obj_posiciones[h],
                                    self.obstaculos_sorteo) < HOLGURA_OBJETIVO:
                    for _ in range(100_000):
                        cand = rng.uniform(margen, self.arena_size - margen)
                        if distancia_minima(cand, self.obstaculos_sorteo) >= HOLGURA_OBJETIVO:
                            break
                    else:
                        raise RuntimeError("no se pudo reubicar un objetivo")
                    self._obj_posiciones[h] = cand
                    self.n_objetivos_reubicados += 1
        self._anular_mascara()

    def step(self) -> None:
        """Paso estándar + rebote elástico de los objetivos en los discos."""
        super().step()
        for h in range(self.n_objetivos):
            for ox, oy, r in self.obstaculos_rebote:
                d = self._obj_posiciones[h] - np.array([ox, oy])
                dist = float(np.linalg.norm(d))
                if dist >= r:
                    continue
                n = d / dist if dist > 1e-12 else np.array([1.0, 0.0])
                # Posición: espejo sobre la tangente. Velocidad: v' = v − 2(v·n)n.
                self._obj_posiciones[h] = np.array([ox, oy]) + n * (2.0 * r - dist)
                th = float(self._obj_orientaciones[h])
                v = np.array([math.cos(th), math.sin(th)])
                v = v - 2.0 * float(v @ n) * n
                self._obj_orientaciones[h] = math.atan2(v[1], v[0])
                self.n_rebotes_obstaculo += 1
        W = self.arena_size
        self._obj_posiciones[:, 0] = np.clip(self._obj_posiciones[:, 0], 1e-8, W[0] - 1e-8)
        self._obj_posiciones[:, 1] = np.clip(self._obj_posiciones[:, 1], 1e-8, W[1] - 1e-8)
        self._anular_mascara()

    def update_aoi_grid(self, posiciones_agentes: np.ndarray) -> None:
        """Actualización estándar y re-anulación de las celdas ocupadas."""
        super().update_aoi_grid(posiciones_agentes)
        self._anular_mascara()


class EntornoObstaculos(CyanobacteriaMonitoringEnv):
    """CyanobacteriaMonitoringEnv con obstáculos circulares estáticos."""

    def __init__(self,
                 obstaculos_fisicos: Sequence[Obstaculo] = (),
                 obstaculos_sorteo: Sequence[Obstaculo] = (),
                 obstaculos_rebote: Optional[Sequence[Obstaculo]] = None,
                 **kwargs) -> None:
        super().__init__(**kwargs)
        self.obstaculos_fisicos: Tuple[Obstaculo, ...] = tuple(obstaculos_fisicos)
        self.obstaculos_sorteo:  Tuple[Obstaculo, ...] = tuple(obstaculos_sorteo)
        # Mismos argumentos con que el constructor base crea el campo.
        self._field = CampoConObstaculos(
            arena_size=tuple(float(a) for a in self.arena_size),
            n_objetivos=self.n_hotspots,
            dt=self.dt,
            grid_resolution=self.grid_resolution,
            seed=kwargs.get("seed"),
            obstaculos_fisicos=self.obstaculos_fisicos,
            obstaculos_sorteo=self.obstaculos_sorteo,
            obstaculos_rebote=obstaculos_rebote,
        )
        self._semilla_ep: Optional[int] = None
        self.n_agentes_reubicados: int = 0
        self.contactos_obstaculo: Dict[str, int] = {}

    def reset(self, seed: Optional[int] = None, options=None):
        """Reset estándar; guarda la semilla para el RNG de reubicación."""
        self._semilla_ep = seed
        self.n_agentes_reubicados = 0
        salida = super().reset(seed=seed, options=options)
        self.contactos_obstaculo = {a: 0 for a in self.agents}
        return salida

    def _sortear_poses_iniciales(self) -> Dict[str, np.ndarray]:
        """Sorteo del protocolo + reubicación SÓLO de los agentes en conflicto."""
        estados = super()._sortear_poses_iniciales()
        if not self.obstaculos_sorteo:
            return estados
        rng = np.random.default_rng([int(self._semilla_ep or 0), 2])
        margen = 0.15 * self.arena_size
        min_sep = 2.0 * D_SAFE + 0.01
        ids = list(estados.keys())
        for a in ids:
            if distancia_minima(estados[a][:2], self.obstaculos_sorteo) >= HOLGURA_ARRANQUE:
                continue
            otros = [estados[b][:2].copy() for b in ids if b != a]
            for _ in range(100_000):
                cand = rng.uniform(margen, self.arena_size - margen)
                if (distancia_minima(cand, self.obstaculos_sorteo) >= HOLGURA_ARRANQUE
                        and all(np.linalg.norm(cand - o) > min_sep for o in otros)):
                    break
            else:
                raise RuntimeError("no se pudo reubicar un agente")
            estados[a][0] = cand[0]
            estados[a][1] = cand[1]
            self.n_agentes_reubicados += 1
        return estados

    def _integrate_kinematics(self, agent_id: str, action: np.ndarray) -> None:
        """Cinemática estándar + contacto con el disco r + radio del chasis."""
        super()._integrate_kinematics(agent_id, action)
        if not self.obstaculos_fisicos:
            return
        est = self._estados[agent_id]
        for ox, oy, r in self.obstaculos_fisicos:
            R = r + RADIO_CHASIS
            d = est[:2] - np.array([ox, oy])
            dist = float(np.linalg.norm(d))
            if dist < R:
                n = d / dist if dist > 1e-12 else np.array([1.0, 0.0])
                est[0] = ox + n[0] * (R + 1e-9)
                est[1] = oy + n[1] * (R + 1e-9)
                self.contactos_obstaculo[agent_id] = (
                    self.contactos_obstaculo.get(agent_id, 0) + 1)
