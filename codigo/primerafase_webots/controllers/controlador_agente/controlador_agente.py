"""
controlador_agente.py
=====================
Controlador que corre en CADA Pololu 3pi+ del enjambre multi-robot.
NO es supervisor: sólo maneja sus propios devices (motores, GPS, Compass,
Emitter, Receiver). Esa es la restricción de Webots que obliga a esta
arquitectura — un controlador no puede comandar los motores de otro robot.

Responsabilidades (mínimas y sin estado complejo, a propósito)
--------------------------------------------------------------
  1. Deducir su índice del nombre del nodo ("p3pi_3" → 3).
  2. En CADA tick: leer GPS + Compass, convertir al marco del env y emitir su
     pose por el canal de subida. Emisión ciega, sin esperar pedido.
  3. Drenar el canal de bajada. Si llega ACCIONES, extraer su par (v, ω) por
     índice; si llega RESET, frenar motores y descartar la acción vigente.
  4. MANTENER la última velocidad de rueda comandada hasta que llegue la
     siguiente acción (el coordinador decide cada 10 ticks; el agente corre
     cada 1 tick).

Toda la lógica de decisión vive en el coordinador. Este controlador es
deliberadamente "tonto": es el análogo del firmware del Pololu real, que
recibe (v, ω) por RF/UDP y sólo los traduce a PWM diferencial.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Tuple

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

from controller import Robot  # type: ignore  # provisto por Webots

from protocolo import (
    CANAL_BAJADA,
    CANAL_SUBIDA,
    SIGNO_MOTOR_1,
    SIGNO_MOTOR_2,
    TIPO_ACCIONES,
    TIPO_RESET,
    VELOCIDAD_MAX_RUEDA,
    compass_a_heading,
    convertir_velocidades_a_ruedas,
    empaquetar_pose,
    extraer_accion,
    leer_tipo,
    webots_a_env_xy,
)

# Nombres de devices (deben coincidir con el .wbt).
NOMBRE_MOTOR_DERECHO:   str = "motor_1"
NOMBRE_MOTOR_IZQUIERDO: str = "motor_2"
NOMBRE_GPS:             str = "gps"
NOMBRE_COMPASS:         str = "compass"
NOMBRE_EMITTER:         str = "emitter"
NOMBRE_RECEIVER:        str = "receiver"


class ControladorAgente:
    """Agente físico del enjambre: publica su pose y ejecuta (v, ω)."""

    def __init__(self) -> None:
        """Inicializa devices, deduce el índice y deja los motores en cero."""
        self.robot: Robot = Robot()
        self.timestep_ms: int = int(self.robot.getBasicTimeStep())

        # ── Índice del agente, deducido del nombre del nodo ──────────────
        nombre: str = self.robot.getName()
        try:
            self.id_agente: int = int(nombre.rsplit("_", 1)[1])
        except (IndexError, ValueError) as exc:
            raise RuntimeError(
                f"El nombre del robot {nombre!r} no termina en '_<indice>'. "
                f"Se espera 'p3pi_0', 'p3pi_1', ..."
            ) from exc

        # ── Motores en control por velocidad ─────────────────────────────
        self._motor_derecho   = self.robot.getDevice(NOMBRE_MOTOR_DERECHO)
        self._motor_izquierdo = self.robot.getDevice(NOMBRE_MOTOR_IZQUIERDO)
        if self._motor_derecho is None or self._motor_izquierdo is None:
            raise RuntimeError(
                f"[{nombre}] Faltan motores {NOMBRE_MOTOR_DERECHO!r}/"
                f"{NOMBRE_MOTOR_IZQUIERDO!r}."
            )
        for motor in (self._motor_derecho, self._motor_izquierdo):
            motor.setPosition(float("inf"))
            motor.setVelocity(0.0)

        # ── Sensores ─────────────────────────────────────────────────────
        self._gps     = self.robot.getDevice(NOMBRE_GPS)
        self._compass = self.robot.getDevice(NOMBRE_COMPASS)
        if self._gps is None or self._compass is None:
            raise RuntimeError(f"[{nombre}] Faltan GPS/Compass.")
        self._gps.enable(self.timestep_ms)
        self._compass.enable(self.timestep_ms)

        # ── Comunicación ─────────────────────────────────────────────────
        self._emitter  = self.robot.getDevice(NOMBRE_EMITTER)
        self._receiver = self.robot.getDevice(NOMBRE_RECEIVER)
        if self._emitter is None or self._receiver is None:
            raise RuntimeError(f"[{nombre}] Faltan Emitter/Receiver.")
        self._emitter.setChannel(CANAL_SUBIDA)
        self._receiver.setChannel(CANAL_BAJADA)
        self._receiver.enable(self.timestep_ms)

        # ── Estado ───────────────────────────────────────────────────────
        self._tick: int = 0
        # Última velocidad de rueda comandada; se mantiene entre decisiones.
        self._phi_R_cmd: float = 0.0
        self._phi_L_cmd: float = 0.0

        print(f"[agente {self.id_agente}] listo  nombre={nombre}  "
              f"timestep={self.timestep_ms} ms  "
              f"canales=(subida {CANAL_SUBIDA}, bajada {CANAL_BAJADA})")

    # ──────────────────────────────────────────────────────────────────────

    def _leer_pose_env(self) -> Tuple[float, float, float]:
        """Lee GPS + Compass y devuelve (x_env, y_env, theta_env)."""
        pos: List[float] = list(self._gps.getValues())
        mag: List[float] = list(self._compass.getValues())
        x_env, y_env = webots_a_env_xy(float(pos[0]), float(pos[1]))
        return x_env, y_env, compass_a_heading(mag)

    # ──────────────────────────────────────────────────────────────────────

    def _emitir_pose(self) -> None:
        """
        Emite la pose actual por el canal de subida. Se llama en CADA tick,
        sin esperar pedido: si un mensaje se pierde, el siguiente llega en
        `timestep_ms`.

        Si el GPS aún no tiene lectura válida (primer tick), no emite — un
        NaN corrompería el caché del coordinador.
        """
        x, y, th = self._leer_pose_env()
        if not (x == x and y == y and th == th):   # descarta NaN
            return
        self._emitter.send(
            empaquetar_pose(self.id_agente, x, y, th, self._tick)
        )

    # ──────────────────────────────────────────────────────────────────────

    def _procesar_bajada(self) -> None:
        """
        Drena el canal de bajada y aplica el último mensaje relevante.

        - ACCIONES : extrae el par propio por índice y actualiza las
                     velocidades de rueda comandadas.
        - RESET    : frena motores y descarta la acción vigente.

        Se drena la cola COMPLETA para no acumular latencia si algún tick se
        retrasó; sólo importa el mensaje más reciente de cada tipo.
        """
        while self._receiver.getQueueLength() > 0:
            datos: bytes = bytes(self._receiver.getBytes())
            self._receiver.nextPacket()

            tipo = leer_tipo(datos)
            if tipo == TIPO_RESET:
                self._phi_R_cmd = 0.0
                self._phi_L_cmd = 0.0
            elif tipo == TIPO_ACCIONES:
                try:
                    _tick_dec, v, omega = extraer_accion(datos, self.id_agente)
                except ValueError as exc:
                    print(f"[agente {self.id_agente}] mensaje inválido: {exc}")
                    continue
                phi_R, phi_L = convertir_velocidades_a_ruedas(v, omega)
                self._phi_R_cmd = SIGNO_MOTOR_1 * phi_R
                self._phi_L_cmd = SIGNO_MOTOR_2 * phi_L

    # ──────────────────────────────────────────────────────────────────────

    def _aplicar_velocidades(self) -> None:
        """
        Aplica las velocidades de rueda vigentes, saturadas a la cota del
        motor declarada en el .wbt. Se llama en CADA tick: entre decisiones
        del coordinador, mantiene la última orden recibida.
        """
        cota = VELOCIDAD_MAX_RUEDA
        self._motor_derecho.setVelocity(
            max(-cota, min(cota, self._phi_R_cmd))
        )
        self._motor_izquierdo.setVelocity(
            max(-cota, min(cota, self._phi_L_cmd))
        )

    # ──────────────────────────────────────────────────────────────────────

    def correr(self) -> None:
        """
        Bucle principal. Orden por tick:
          1. Procesar mensajes de bajada (acciones / reset).
          2. Aplicar velocidades vigentes a los motores.
          3. Emitir la pose actual.
          4. Avanzar la simulación.
        """
        while self.robot.step(self.timestep_ms) != -1:
            self._tick += 1
            self._procesar_bajada()
            self._aplicar_velocidades()
            self._emitir_pose()


def main() -> None:
    """Punto de entrada que Webots invoca al cargar el controlador."""
    ControladorAgente().correr()


if __name__ == "__main__":
    main()
