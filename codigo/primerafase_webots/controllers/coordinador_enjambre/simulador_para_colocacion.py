"""
simulador_para_colocacion.py
============================
Fallas del simulador que la colocación automática con obstáculo necesita
ver y que `SimuladorRobotat` no modela (revisión adversarial del plan,
2026-10-07). Por SUBCLASE, sin tocar `simulador_robotat.py`:

  · ZONA MUERTA de rueda desde parado: un robot quieto no arranca con
    |v| < V_MIN_ZONA y |ω| < W_MIN_ZONA (el 3pi real no vence la fricción
    con órdenes chicas; `colocacion_autonoma` usa V_MIN 0.03 y W_MIN 0.35
    por eso). Sin esto, un bloqueo del CBF que en el laboratorio deja al
    robot clavado se resuelve solo en el simulador;
  · RETARDO por robot (el obstáculo con 0.85 s y los agentes con 0.45 s):
    `correr_fase0_obstaculo.fallas_con_retardo_por_robot`, reexportado acá.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import math
import time
from typing import Any, Dict

from simulador_robotat import SimuladorRobotat

#: Zona muerta desde parado (m/s y rad/s): los mínimos de la colocación.
V_MIN_ZONA: float = 0.03
W_MIN_ZONA: float = 0.35


class SimuladorZonaMuerta(SimuladorRobotat):
    """`SimuladorRobotat` con zona muerta de arranque (ver módulo)."""

    def __init__(self, *args: Any, v_min: float = V_MIN_ZONA,
                 w_min: float = W_MIN_ZONA, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.v_min_zona = float(v_min)
        self.w_min_zona = float(w_min)
        self._parado: Dict[int, bool] = {rid: True for rid in self.robots}
        #: Cuántas veces la zona muerta retuvo a cada robot (para las pruebas).
        self.retenciones: Dict[int, int] = {rid: 0 for rid in self.robots}

    def _fisica(self) -> None:
        """La física de `SimuladorRobotat._fisica`, con la zona muerta."""
        siguiente = time.perf_counter()
        while self._corriendo.is_set():
            retardo = self.fallas.retardo_actuacion_s
            ahora = time.perf_counter()
            with self._lock:
                for rid, est in self.robots.items():
                    if retardo > 0.0:
                        while est.en_camino and est.en_camino[0][0] <= ahora:
                            (_t, est.rpm_izq_ruedas,
                             est.rpm_der_ruedas) = est.en_camino.popleft()
                        rpm_izq, rpm_der = est.rpm_izq_ruedas, est.rpm_der_ruedas
                    else:
                        rpm_izq, rpm_der = est.rpm_izq, est.rpm_der
                    phi_der = rpm_der * 2.0 * math.pi / 60.0
                    phi_izq = rpm_izq * 2.0 * math.pi / 60.0
                    v = self._r * (phi_der + phi_izq) / 2.0
                    w = self._r * (phi_der - phi_izq) / (2.0 * self._l)
                    if (self._parado.get(rid, True) and (v != 0.0 or w != 0.0)
                            and abs(v) < self.v_min_zona
                            and abs(w) < self.w_min_zona):
                        self.retenciones[rid] = self.retenciones.get(rid, 0) + 1
                        v = w = 0.0
                    self._parado[rid] = (v == 0.0 and w == 0.0)
                    est.x += v * math.cos(est.yaw) * self._dt
                    est.y += v * math.sin(est.yaw) * self._dt
                    est.yaw = math.atan2(math.sin(est.yaw + w * self._dt),
                                         math.cos(est.yaw + w * self._dt))
            siguiente += self._dt
            espera = siguiente - time.perf_counter()
            if espera > 0:
                time.sleep(espera)
            else:
                siguiente = time.perf_counter()


def fallas_con_retardo_por_robot(retardos: Dict[int, float],
                                 por_defecto: float, **kw: Any) -> Any:
    """Reexporta la de `correr_fase0_obstaculo` (retardo distinto por robot)."""
    from correr_fase0_obstaculo import fallas_con_retardo_por_robot as f
    return f(retardos, por_defecto, **kw)
