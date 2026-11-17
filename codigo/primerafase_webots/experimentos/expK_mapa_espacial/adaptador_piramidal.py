"""
adaptador_piramidal.py
======================
Adapta el `PyramidalHeuristicController` (Voronoi + PSO) a la firma de
política que usa el protocolo de evaluación: `(env, obs_dict, rng) -> dict`.

El controlador original NO se modifica. Vive en `lib_baseline/` como copia
literal byte a byte del artefacto de `fase_preliminar2/baseline_heuristico/`,
para preservar su trazabilidad como trabajo previo de la UVG. Todo lo que hace
falta para integrarlo al protocolo está acá.

Qué resuelve el adaptador
-------------------------
1. FIRMA. El protocolo llama `accionar(env, obs_dict, rng)`; el controlador
   expone `predict(estado_global)`. El adaptador traduce.

2. CONSTRUCCIÓN DE `estado_global`. El controlador necesita cinco claves que
   se extraen del env por SOLA LECTURA (ninguna modifica nada):
     agent_ids      ← env.agents
     agent_states   ← env._estados[a]                    ([x, y, θ, v, ω])
     hotspots       ← env._field.posiciones_objetivos    (property, copia)
     hotspot_sigmas ← env._field.sigmas_objetivos        (property, copia)
     arena_size     ← env.arena_size

3. MEMORIA ENTRE EPISODIOS — crítico para el pareo. El controlador mantiene
   `_velocity_memory` con inercia tipo PSO (0.65·anterior + 0.35·nuevo), y su
   `predict` sólo auto-resetea si el dict está VACÍO, cosa que ocurre una
   única vez. Sin un `reset(agent_ids)` explícito al inicio de CADA episodio,
   la inercia del episodio i contamina el i+1 y rompe el diseño pareado.
   `AdaptadorPiramidal.reset_episodio()` lo fuerza; hay un test de
   reproducibilidad que lo verifica (`verificar_reproducibilidad`).

4. UNIFICACIÓN DE Ω_MAX. El módulo original define su propia constante local
   `OMEGA_MAX = 6.28`, mientras el resto del proyecto importa 6.2832 desde
   `concentration_dynamics`. La diferencia es numéricamente irrelevante, pero
   se elimina la duplicación pasando el valor canónico por el CONSTRUCTOR
   (que ya lo acepta como parámetro), sin tocar el archivo original.

Diferencias declaradas respecto de la heurística NN
---------------------------------------------------
Ambas líneas base usan control proporcional sobre el error de rumbo con la
velocidad modulada por cos(error), pero con leyes de bajo nivel DISTINTAS:

  | Aspecto | heurística NN | piramidal |
  |---------|---------------|-----------|
  | ganancia angular | K_ω = 4.00 | k_omega = 2.20 |
  | velocidad        | V_MAX·max(0,cos e) | k_v·‖vec‖·max(0,cos e), k_v=1.40 |
  | retroceso        | no (v ≥ 0)  | no (v ∈ [0, v_max]) |

Se corre el piramidal CON SUS GANANCIAS ORIGINALES a propósito: son parte de
su diseño (escala por distancia porque el punto deseado está dentro de su
propia celda de Voronoi, y frenar al llegar es intencional), y homogeneizarlas
evaluaría un controlador que nadie diseñó, además de anular el valor de
replicar el trabajo previo. La diferencia queda declarada como limitación.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

from lib.concentration_dynamics import OMEGA_MAX, V_MAX
from lib_baseline.pyramidal_controller import PyramidalHeuristicController


class AdaptadorPiramidal:
    """
    Envuelve `PyramidalHeuristicController` para el protocolo de evaluación.

    Uso
    ---
        adaptador = AdaptadorPiramidal(arena_size=(3.0, 3.0))
        for semilla in semillas:
            obs, _ = env.reset(seed=semilla)
            adaptador.reset_episodio(list(obs.keys()))   # ← imprescindible
            ...
            acciones = adaptador(env, obs, rng)
    """

    def __init__(
        self,
        arena_size: tuple = (3.0, 3.0),
        v_max:      float = V_MAX,
        omega_max:  float = OMEGA_MAX,
    ) -> None:
        """
        Construye el controlador con sus ganancias por defecto (k_v = 1.40,
        k_omega = 2.20 y los ~13 parámetros del diseño original), salvo
        `omega_max`, que se fija al valor canónico del proyecto para eliminar
        la duplicación de constante (6.28 local vs 6.2832 importado).
        """
        self.controlador = PyramidalHeuristicController(
            arena_size = arena_size,
            v_max      = v_max,
            omega_max  = omega_max,
        )
        self._episodios_reiniciados: int = 0

    # ──────────────────────────────────────────────────────────────────────

    def reset_episodio(self, agent_ids: List[str]) -> None:
        """
        Limpia `_velocity_memory` al inicio de un episodio.

        DEBE llamarse en cada episodio: sin esto la inercia del episodio
        anterior arrastra estado y contamina el diseño pareado.
        """
        self.controlador.reset(agent_ids)
        self._episodios_reiniciados += 1

    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def construir_estado_global(env) -> Dict[str, Any]:
        """
        Extrae del env el `estado_global` que el controlador espera.

        Sólo LECTURA: `posiciones_objetivos` y `sigmas_objetivos` son
        properties que devuelven copias, y `_estados` se copia explícitamente.
        """
        agent_ids: List[str] = list(env.agents)
        return {
            "agent_ids": agent_ids,
            "agent_states": {
                a: np.asarray(env._estados[a], dtype=np.float64).copy()
                for a in agent_ids
            },
            "hotspots": np.asarray(
                env._field.posiciones_objetivos, dtype=np.float64
            ),
            "hotspot_sigmas": np.asarray(
                env._field.sigmas_objetivos, dtype=np.float64
            ),
            "arena_size": np.asarray(env.arena_size, dtype=np.float64).copy(),
        }

    # ──────────────────────────────────────────────────────────────────────

    def __call__(self, env, obs_dict, rng) -> Dict[str, np.ndarray]:
        """
        Firma del protocolo. `obs_dict` y `rng` se reciben por compatibilidad:
        el controlador decide con el estado GLOBAL, no con la observación
        local (ver la asimetría de información declarada en el resumen).
        """
        estado_global = self.construir_estado_global(env)
        acciones = self.controlador.predict(estado_global)
        return {
            a: np.asarray(v, dtype=np.float32).flatten()
            for a, v in acciones.items()
        }


# =============================================================================
# TEST DE REPRODUCIBILIDAD
# =============================================================================

def verificar_reproducibilidad(
    construir_env,
    n_episodios: int = 3,
    seed_base:   int = 420_000,
) -> bool:
    """
    Verifica que `reset_episodio` elimina el arrastre de inercia entre
    episodios: corre la misma secuencia de semillas DOS veces y exige
    coberturas idénticas bit a bit.

    Si `reset_episodio` no se llamara, la segunda pasada arrancaría con la
    `_velocity_memory` del último episodio de la primera y las coberturas
    diferirían.

    Parámetros
    ----------
    construir_env : callable sin argumentos que devuelve un env nuevo.
    n_episodios   : cuántos episodios encadenar por pasada.
    seed_base     : primera semilla.

    Retorna
    -------
    True si ambas pasadas coinciden exactamente.
    """
    coberturas: List[List[float]] = []

    for _pasada in range(2):
        env = construir_env()
        adaptador = AdaptadorPiramidal(arena_size=tuple(env.arena_size))
        de_esta_pasada: List[float] = []

        for i in range(n_episodios):
            obs, _ = env.reset(seed=seed_base + i)
            adaptador.reset_episodio(list(obs.keys()))
            done = False
            while not done:
                acciones = adaptador(env, obs, None)
                obs, _, term, trunc, _ = env.step(acciones)
                done = all(trunc.values()) or all(term.values())
            de_esta_pasada.append(
                1.0 - float(np.mean(env._field._grid_aoi))
            )
        coberturas.append(de_esta_pasada)

    iguales = all(
        a == b for a, b in zip(coberturas[0], coberturas[1])
    )
    print(f"  pasada 1: {[f'{c:.6f}' for c in coberturas[0]]}")
    print(f"  pasada 2: {[f'{c:.6f}' for c in coberturas[1]]}")
    print(f"  reproducible: {iguales}")
    return iguales
