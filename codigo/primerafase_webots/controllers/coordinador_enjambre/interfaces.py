"""
interfaces.py
=============
Capa de abstracción entre el coordinador y el mundo físico.

Motivación
----------
El coordinador tenía cableados dos extremos: de dónde vienen las poses
(GPS+Compass vía Emitter/Receiver de Webots) y a dónde van las acciones
(Emitter → `setVelocity` en rad/s). Extraerlos a interfaces permite que el
MISMO coordinador —con su política, su filtro CBF, su comportamiento de
recuperación y sus métricas, todo ya validado— corra contra Webots, contra el
Robotat físico o contra un simulador del laboratorio, sin tocar su lógica.

Tres interfaces
---------------
  FuentePoses      — de dónde vienen las poses de los agentes.
  CanalActuacion   — a dónde van las acciones (v, ω).
  EntornoEjecucion — el resto del acoplamiento al simulador: reloj,
                     visualización, reposicionamiento y cierre.

La tercera existe porque sin ella el coordinador seguiría con un
`self.supervisor` de Webots cableado, y el objetivo es que pueda correr fuera
de Webots. Sus operaciones son casi triviales en el Robotat (el reloj es
tiempo real, no hay esferas que mover) salvo una: **`reposicionar` NO EXISTE**
en el laboratorio, y debe fallar ruidosamente en vez de ser un no-op silencioso
(ver `EntornoEjecucion.reposicionar`).

Decisiones de diseño
--------------------
1. **Índice `int`, no `str`.** El coordinador usa `robot_i` internamente, pero
   el protocolo identifica agentes por índice y el Robotat por ID de marcador.
   Usar `int` en la frontera evita traducir dos veces.

2. **`leer_poses` devuelve SÓLO lo que llegó**, no todos los agentes. El caché
   y la política de "usá la última pose conocida" quedan en el COORDINADOR, no
   en la fuente: esa política ya está validada (los Exp F y H la ejercitaron
   con ruido y latencia) y moverla a cada implementación la duplicaría.

3. **El canal recibe `(v, ω)`, no rad/s de rueda.** La conversión al modelo
   diferencial vive dentro de cada implementación —en Webots la hace el
   `controlador_agente`, en el Robotat la hará `CanalActuacionRobotat`—, de
   modo que el modelo queda de un solo lado de la frontera y el coordinador
   nunca ve unidades de rueda.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Protocol, Tuple, runtime_checkable

import numpy as np


class PoseMedida(NamedTuple):
    """
    Una medición de pose tal como la entrega la fuente.

    Atributos
    ---------
    pose  : np.ndarray (3,) — [x, y, θ] en el marco del env (origen en
            esquina, arena [0,W]×[0,H]). La transformación desde el marco
            nativo de la fuente (Webots centrado, laboratorio del Robotat)
            es responsabilidad de la implementación.
    tick  : int — instante de la MEDICIÓN, no de la recepción. Es lo que
            permite al coordinador calcular la antigüedad de la pose.
    """
    pose: np.ndarray
    tick: int


@runtime_checkable
class FuentePoses(Protocol):
    """De dónde vienen las poses de los agentes."""

    nombre: str

    def leer_poses(self) -> List[Tuple[int, PoseMedida]]:
        """
        Devuelve el FLUJO de mediciones disponibles en este instante, como
        lista de `(id_agente, PoseMedida)` **en orden de llegada**.

        Deliberadamente NO es un dict indexado por agente. Una fuente de
        poses entrega un FLUJO de mediciones; decidir cuáles son válidas es
        política del consumidor. Además, la degradación de pose (Exp F/H)
        consume el RNG una vez por medición procesada, así que deduplicar
        acá podría alterar ese consumo si alguna vez llegaran dos mensajes
        del mismo agente en un tick (hoy no ocurre, pero la implementación
        del Robotat podría hacerlo).

        La deduplicación y la política de frescura son del coordinador.
        No debe bloquear; puede devolver lista vacía o parcial.
        """
        ...

    def agentes_faltantes(self) -> List[int]:
        """
        Índices de los que nunca se recibió pose desde el último `reiniciar`.
        Sirve para distinguir "todavía no llegó" de "nunca va a llegar"
        (marcador perdido, robot apagado, ID mal configurado).
        """
        ...

    def reiniciar(self) -> None:
        """Invalida el estado acumulado (al empezar un episodio)."""
        ...


@runtime_checkable
class CanalActuacion(Protocol):
    """A dónde van las acciones."""

    nombre: str

    def enviar_acciones(
        self, acciones: Dict[int, Tuple[float, float]]
    ) -> None:
        """
        Envía (v, ω) por agente. Unidades: v en m/s, ω en rad/s, en el marco
        del cuerpo. La conversión a velocidades de rueda es responsabilidad
        de la implementación.
        """
        ...

    def detener_todo(self) -> None:
        """
        Detiene TODOS los robots inmediatamente.

        El coordinador la invoca desde un bloque `finally` y desde un handler
        de `atexit`, de modo que cualquier salida —fin normal, excepción,
        interrupción por teclado— deje los robots quietos. En Webots es
        inofensivo; en el laboratorio es lo que evita que cinco robots sigan
        andando si el programa muere.

        Debe ser IDEMPOTENTE y no lanzar: se llama en caminos de error.
        """
        ...


@runtime_checkable
class EntornoEjecucion(Protocol):
    """
    El resto del acoplamiento: reloj, visualización, reposicionamiento y
    cierre. Todo lo que no es leer poses ni enviar acciones.
    """

    nombre: str

    #: True si el entorno puede teletransportar robots (ver `reposicionar`).
    #: El coordinador PREGUNTA por esta capacidad antes de llamar, en vez de
    #: llamar y atrapar la excepción: tragar un `NotImplementedError` haría
    #: indistinguible "este entorno no teletransporta" de "el teletransporte
    #: falló", y son dos situaciones muy distintas.
    soporta_reposicionar: bool

    def avanzar(self, n_ticks: int) -> bool:
        """
        Avanza el reloj `n_ticks`. En Webots es `supervisor.step`; en el
        laboratorio, esperar hasta el próximo instante de muestreo.

        Retorna False si el entorno pidió terminar.
        """
        ...

    def publicar_visualizacion(self, posiciones_hotspots: np.ndarray) -> None:
        """
        Refleja el estado del env en la visualización, si la hay. En el
        Robotat es no-op: los hotspots son virtuales y no existen esferas
        físicas que mover.
        """
        ...

    def reposicionar(self, poses: Dict[int, np.ndarray]) -> None:
        """
        Coloca los robots en poses dadas (teletransporte entre episodios).

        SÓLO EXISTE EN SIMULACIÓN. En el laboratorio los robots arrancan
        donde quedaron, y la implementación del Robotat debe lanzar
        `NotImplementedError` con un mensaje claro — un no-op silencioso
        haría que el código "funcione" mientras las poses iniciales quedan
        donde sea, y eso es peor que un fallo ruidoso.
        """
        ...

    def finalizar(self, codigo: int = 0) -> None:
        """Cierra el entorno (salir de Webots, cerrar sockets)."""
        ...
