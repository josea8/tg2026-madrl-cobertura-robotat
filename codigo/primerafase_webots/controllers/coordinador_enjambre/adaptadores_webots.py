"""
adaptadores_webots.py
=====================
Implementaciones de `FuentePoses`, `CanalActuacion` y `EntornoEjecucion` para
Webots. Mueven el código que estaba cableado en el coordinador **sin
modificarlo**: la Fase 1 de la capa de abstracción es de regresión cero.

Dos puntos donde una refactorización descuidada rompería la reproducibilidad
bit a bit, y cómo se preservan acá:

1. **El drenaje del receiver ocurre POR TICK, no por decisión.** El
   coordinador llama `avanzar(n)`, que internamente avanza tick a tick y drena
   en cada uno. Si el drenaje pasara a hacerse una vez por decisión, la
   antigüedad de las poses cambiaría y con ella todo el rollout.
   → Por eso `EntornoEjecucionWebots` recibe la fuente y la drena en cada tick.

2. **La degradación de pose (Exp F/H) se aplica POR MEDICIÓN.** Queda en el
   coordinador —no acá—, y se invoca sobre cada medición que devuelve
   `leer_poses()`, en el mismo punto del flujo que antes, para no alterar el
   orden de consumo del RNG.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from interfaces import PoseMedida
from protocolo import (
    CANAL_BAJADA,
    CANAL_SUBIDA,
    desempaquetar_pose,
    empaquetar_acciones,
    empaquetar_reset,
    env_a_webots_xy,
)


class FuentePosesWebots:
    """
    Poses recibidas por el canal de subida (los agentes las publican cada
    tick desde su GPS+Compass y las envían ya en marco del env).
    """

    nombre: str = "webots"

    def __init__(self, receiver, n_agentes: int, timestep_ms: int) -> None:
        self._receiver = receiver
        self._n_agentes = int(n_agentes)
        self._receiver.setChannel(CANAL_SUBIDA)
        self._receiver.enable(int(timestep_ms))
        self._vistos: set = set()

    def leer_poses(self) -> List[Tuple[int, PoseMedida]]:
        """
        Drena la cola COMPLETA del receiver y devuelve el flujo de mediciones
        EN ORDEN DE LLEGADA, sin deduplicar. Vaciar la cola entera evita
        acumular latencia si algún tick se retrasó.

        No se deduplica a propósito: la política de frescura es del
        coordinador (ver docstring de `FuentePoses.leer_poses`). En Webots
        hoy llega un mensaje por agente y por tick, así que deduplicar o no
        da el mismo resultado; se deja sin deduplicar por fidelidad al
        contrato de la interfaz.
        """
        medidas: List[Tuple[int, PoseMedida]] = []
        while self._receiver.getQueueLength() > 0:
            datos = bytes(self._receiver.getBytes())
            self._receiver.nextPacket()
            try:
                id_ag, x, y, th, tick_em = desempaquetar_pose(datos)
            except ValueError as exc:
                print(f"[fuente_webots] pose inválida descartada: {exc}")
                continue
            if not (0 <= id_ag < self._n_agentes):
                continue
            medidas.append((
                id_ag,
                PoseMedida(
                    pose=np.array([x, y, th], dtype=np.float64),
                    tick=int(tick_em),
                ),
            ))
            self._vistos.add(id_ag)
        return medidas

    def agentes_faltantes(self) -> List[int]:
        """Índices de los que nunca llegó una pose desde el último reinicio."""
        return [i for i in range(self._n_agentes) if i not in self._vistos]

    def reiniciar(self) -> None:
        """Olvida qué agentes se vieron (al empezar un episodio)."""
        self._vistos.clear()


class CanalActuacionWebots:
    """
    Acciones difundidas por el canal de bajada en UN mensaje. La conversión
    (v, ω) → rad/s de rueda la hace cada `controlador_agente`, del otro lado.
    """

    nombre: str = "webots"

    def __init__(self, emitter, obtener_tick) -> None:
        self._emitter = emitter
        self._obtener_tick = obtener_tick
        self._emitter.setChannel(CANAL_BAJADA)

    def enviar_acciones(
        self, acciones: Dict[int, Tuple[float, float]]
    ) -> None:
        """Difunde las N acciones ordenadas por índice de agente."""
        lista = [acciones[i] for i in sorted(acciones)]
        self._emitter.send(empaquetar_acciones(self._obtener_tick(), lista))

    def detener_todo(self) -> None:
        """
        Difunde RESET: los agentes frenan motores y descartan la acción
        vigente. Idempotente y no lanza — se invoca en caminos de error.
        """
        try:
            self._emitter.send(empaquetar_reset(self._obtener_tick()))
        except Exception as exc:                      # noqa: BLE001
            print(f"[canal_webots] detener_todo falló (ignorado): {exc}")


class EntornoEjecucionWebots:
    """Reloj, esferas de hotspots, teletransporte y cierre de Webots."""

    nombre: str = "webots"
    soporta_reposicionar: bool = True

    def __init__(
        self,
        supervisor,
        fuente: FuentePosesWebots,
        nodos_robots: List,
        campos_hotspots: List,
        timestep_ms: int,
        z_hotspot: float,
        offset_proto_rad: float,
    ) -> None:
        self._sup = supervisor
        self._fuente = fuente
        self._nodos = nodos_robots
        self._campos = campos_hotspots
        self._timestep_ms = int(timestep_ms)
        self._z = float(z_hotspot)
        self._offset_proto = float(offset_proto_rad)
        self.cerrado: bool = False

    def avanzar(self, n_ticks: int) -> bool:
        """
        Avanza el reloj de Webots. El drenaje de poses NO ocurre acá: lo hace
        el coordinador después de incrementar su tick, para preservar el
        orden exacto del código original (ver `_avanzar` del coordinador).
        """
        for _ in range(int(n_ticks)):
            if self._sup.step(self._timestep_ms) == -1:
                self.cerrado = True
                return False
        return True

    def publicar_visualizacion(self, posiciones_hotspots: np.ndarray) -> None:
        """Mueve las esferas de hotspots a las posiciones del env."""
        for j, campo in enumerate(self._campos):
            x_w, y_w = env_a_webots_xy(
                float(posiciones_hotspots[j, 0]),
                float(posiciones_hotspots[j, 1]),
            )
            campo.setSFVec3f([x_w, y_w, self._z])

    def reposicionar(self, poses: Dict[int, np.ndarray]) -> None:
        """
        Teletransporta los robots (sólo entre episodios) y anula sus
        velocidades residuales.
        """
        for i, pose in poses.items():
            x_w, y_w = env_a_webots_xy(float(pose[0]), float(pose[1]))
            nodo = self._nodos[i]
            nodo.getField("translation").setSFVec3f([x_w, y_w, 0.0])
            nodo.getField("rotation").setSFRotation(
                [0.0, 0.0, 1.0, float(pose[2]) + self._offset_proto]
            )
            nodo.resetPhysics()

    def finalizar(self, codigo: int = 0) -> None:
        """Cierra Webots."""
        if not self.cerrado:
            self._sup.simulationQuit(int(codigo))
