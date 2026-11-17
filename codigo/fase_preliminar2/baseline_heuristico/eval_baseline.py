"""
eval_baseline.py
================
Evaluación visual del baseline heurístico Voronoi + PSO.

Uso típico desde la raíz del proyecto:
    python baseline_heuristico/eval_baseline.py

El script:
  1. Instancia `CyanobacteriaMonitoringEnv` con `domain_rand=False`.
  2. Construye `estado_global` desde el entorno.
  3. Ejecuta un episodio de 500 steps usando `controller.predict(...)`.
  4. Reporta cobertura AoI final y pares únicos en colisión.
  5. Superpone Voronoi y vectores de movimiento sobre el render actual.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from entorno.swarm_env_skeleton import CyanobacteriaMonitoringEnv, D_SAFE
except ImportError:
    from swarm_env_skeleton import CyanobacteriaMonitoringEnv, D_SAFE

try:
    from pyramidal_controller import PyramidalHeuristicController
except ImportError:
    from baseline_heuristico.pyramidal_controller import PyramidalHeuristicController


class VoronoiOverlay:
    """Overlay no intrusivo para visualizar Voronoi y vectores del controlador."""

    def __init__(self) -> None:
        self._line_collection: Optional[LineCollection] = None
        self._vector_quiver = None
        self._centroid_scatter = None
        self._quiver_size = -1

    def _rebuild_quiver(self, ax, offsets: np.ndarray, vectors: np.ndarray) -> None:
        """
        Matplotlib fija internamente N al crear `quiver`. Si nace con 0 flechas,
        luego no acepta `set_UVC` con 5 robots. Por eso lo recreamos cuando el
        cardinal cambia.
        """
        if self._vector_quiver is not None:
            self._vector_quiver.remove()

        self._vector_quiver = ax.quiver(
            offsets[:, 0] if len(offsets) else np.array([], dtype=np.float64),
            offsets[:, 1] if len(offsets) else np.array([], dtype=np.float64),
            vectors[:, 0] if len(vectors) else np.array([], dtype=np.float64),
            vectors[:, 1] if len(vectors) else np.array([], dtype=np.float64),
            angles="xy",
            scale_units="xy",
            scale=1.0,
            color="deepskyblue",
            width=0.004,
            zorder=8,
        )
        self._quiver_size = int(len(offsets))

    def update(self, env: CyanobacteriaMonitoringEnv, controller: PyramidalHeuristicController) -> None:
        """Crea o actualiza los artistas del overlay sobre la figura del entorno."""
        if getattr(env, "_ax", None) is None:
            return

        ax = env._ax
        if self._line_collection is None:
            self._line_collection = LineCollection(
                [],
                colors="cyan",
                linewidths=1.4,
                alpha=0.90,
                zorder=7,
            )
            ax.add_collection(self._line_collection)
            self._centroid_scatter = ax.scatter(
                [],
                [],
                s=26,
                c="white",
                edgecolors="black",
                linewidths=0.5,
                zorder=8,
            )

        segments = []
        offsets = []
        vectors = []
        centroids = []

        for info in controller.debug_data.values():
            polygon = np.asarray(info["cell_polygon"], dtype=np.float64)
            if len(polygon) >= 2:
                for idx in range(len(polygon)):
                    a = polygon[idx]
                    b = polygon[(idx + 1) % len(polygon)]
                    segments.append(np.vstack([a, b]))

            offsets.append(np.asarray(info["position"], dtype=np.float64))
            vectors.append(np.asarray(info["final_vector"], dtype=np.float64))
            centroids.append(np.asarray(info["cell_centroid"], dtype=np.float64))

        self._line_collection.set_segments(segments)

        if offsets:
            offsets_arr = np.vstack(offsets)
            vectors_arr = np.vstack(vectors)
            centroids_arr = np.vstack(centroids)

            if self._vector_quiver is None or self._quiver_size != len(offsets_arr):
                self._rebuild_quiver(ax, offsets_arr, vectors_arr)
            else:
                self._vector_quiver.set_offsets(offsets_arr)
                self._vector_quiver.set_UVC(vectors_arr[:, 0], vectors_arr[:, 1])
            self._centroid_scatter.set_offsets(centroids_arr)
        else:
            empty = np.empty((0, 2), dtype=np.float64)
            if self._vector_quiver is None or self._quiver_size != 0:
                self._rebuild_quiver(ax, empty, empty)
            else:
                self._vector_quiver.set_offsets(empty)
                self._vector_quiver.set_UVC(np.array([]), np.array([]))
            self._centroid_scatter.set_offsets(empty)

        if getattr(env, "_fig", None) is not None:
            env._fig.canvas.draw_idle()
            plt.pause(0.001)


def parse_args() -> argparse.Namespace:
    """Parámetros de ejecución desde terminal."""
    parser = argparse.ArgumentParser(
        description="Evalúa el baseline heurístico Voronoi + PSO.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Semilla del episodio.")
    parser.add_argument("--steps", type=int, default=500, help="Máximo de timesteps.")
    parser.set_defaults(render=True)
    parser.add_argument(
        "--no-render",
        action="store_false",
        dest="render",
        help="Ejecuta el episodio sin abrir la ventana de render.",
    )
    return parser.parse_args()


def extraer_estado_global(env: CyanobacteriaMonitoringEnv) -> Dict[str, object]:
    """Empaqueta el estado global mínimo que necesita el controlador."""
    return {
        "agent_ids": list(env.agents),
        "agent_states": {
            agent_id: np.asarray(env._estados[agent_id], dtype=np.float64).copy()
            for agent_id in env.agents
        },
        "hotspots": np.asarray(env._field.posiciones_objetivos, dtype=np.float64),
        "hotspot_sigmas": np.asarray(env._field.sigmas_objetivos, dtype=np.float64),
        "arena_size": np.asarray(env.arena_size, dtype=np.float64).copy(),
        "dt": float(env.dt),
        "step_count": int(env._step_count),
    }


def actualizar_colisiones(env: CyanobacteriaMonitoringEnv, pares_colision: Set[Tuple[int, int]]) -> None:
    """Cuenta colisiones como pares únicos (i, j), igual que en tu script de IA."""
    positions = np.array([env._estados[agent_id][:2] for agent_id in env.agents], dtype=np.float64)
    n_agents = len(positions)

    for i in range(n_agents):
        for j in range(i + 1, n_agents):
            if np.linalg.norm(positions[i] - positions[j]) < D_SAFE:
                pares_colision.add((i, j))


def render_compatible(env: CyanobacteriaMonitoringEnv) -> None:
    """
    Compatibilidad con ambas firmas:
      - env.render(mode='human')
      - env.render()
    """
    try:
        env.render(mode="human")
    except TypeError:
        env.render()


def main() -> None:
    args = parse_args()

    env = CyanobacteriaMonitoringEnv(
        n_agents=5,
        arena_size=(3.0, 3.0),
        max_steps=args.steps,
        comm_radius=1.0,
        dt=0.1,
        render_mode="human" if args.render else None,
        domain_rand=False,
        n_hotspots=3,
        grid_resolution=64,
        seed=args.seed,
    )

    controller = PyramidalHeuristicController(arena_size=tuple(env.arena_size))
    overlay = VoronoiOverlay()
    pares_colision: Set[Tuple[int, int]] = set()

    t0 = time.time()
    try:
        env.reset(seed=args.seed)
        controller.reset(list(env.agents))

        cobertura_hist = []

        for step_idx in range(args.steps):
            estado_global = extraer_estado_global(env)
            accion_dict = controller.predict(estado_global)

            if args.render:
                render_compatible(env)
                overlay.update(env, controller)

            _, _, terminations, truncations, _ = env.step(accion_dict)

            cobertura = 1.0 - float(np.mean(env._field._grid_aoi))
            cobertura_hist.append(cobertura)
            actualizar_colisiones(env, pares_colision)

            done = all(terminations.values()) or all(truncations.values())
            if done:
                break

        # Render final para ver el estado terminal del episodio.
        if args.render:
            estado_global = extraer_estado_global(env)
            controller.predict(estado_global)
            render_compatible(env)
            overlay.update(env, controller)

        cobertura_final = 1.0 - float(np.mean(env._field._grid_aoi))
        n_colisiones = len(pares_colision)
        duracion = time.time() - t0

        print("\n=== RESULTADOS BASELINE HEURISTICO ===")
        print(f"Seed                  : {args.seed}")
        print(f"Steps ejecutados      : {env._step_count}")
        print(f"Cobertura AoI final   : {cobertura_final:.4f} ({cobertura_final * 100.0:.2f}%)")
        print(f"Pares unicos colision : {n_colisiones}")
        print(f"Duracion total        : {duracion:.2f} s")

        if cobertura_hist:
            print(f"Cobertura maxima      : {max(cobertura_hist):.4f}")
    finally:
        try:
            if args.render:
                plt.ioff()
            env.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
