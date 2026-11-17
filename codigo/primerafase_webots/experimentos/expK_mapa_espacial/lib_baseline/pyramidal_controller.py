"""
pyramidal_controller.py
=======================
Controlador heurístico piramidal para el baseline de la tesis:

  1. Voronoi acotado al arena  -> separación espacial / anti-colisión.
  2. PSO modificado            -> atracción hacia hotspots dinámicos.
  3. Control cinemático        -> mapeo a [v, omega] continuo.

El controlador no modifica el entorno. Solo consume un "estado_global" y
devuelve un diccionario de acciones compatible con `env.step(...)`.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Tuple

import numpy as np
from scipy.spatial import Voronoi


# Límites del Pololu 3pi+ pedidos explícitamente para el baseline.
V_MAX: float = 0.31
OMEGA_MAX: float = 6.28


def _wrap_angle(angle: float) -> float:
    """Envuelve un ángulo al rango canónico (-pi, pi]."""
    return float((angle + math.pi) % (2.0 * math.pi) - math.pi)


def _safe_norm(vec: np.ndarray, eps: float = 1e-9) -> float:
    """Norma Euclídea robusta para evitar divisiones por cero."""
    return float(max(np.linalg.norm(vec), eps))


def _clip_vector(vec: np.ndarray, max_norm: float) -> np.ndarray:
    """Satura un vector 2D por magnitud manteniendo dirección."""
    norm = _safe_norm(vec)
    if norm <= max_norm:
        return vec.astype(np.float64, copy=True)
    return (vec / norm) * max_norm


def _polygon_area(poly: np.ndarray) -> float:
    """Área firmada de un polígono 2D."""
    if len(poly) < 3:
        return 0.0
    x = poly[:, 0]
    y = poly[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _polygon_centroid(poly: np.ndarray) -> np.ndarray:
    """Centroide de un polígono simple; si es degenerado usa promedio."""
    area = _polygon_area(poly)
    if abs(area) < 1e-9:
        return np.mean(poly, axis=0)

    x = poly[:, 0]
    y = poly[:, 1]
    cross = x * np.roll(y, -1) - np.roll(x, -1) * y
    cx = np.sum((x + np.roll(x, -1)) * cross) / (6.0 * area)
    cy = np.sum((y + np.roll(y, -1)) * cross) / (6.0 * area)
    return np.array([cx, cy], dtype=np.float64)


def _deduplicate_polygon(poly: np.ndarray, tol: float = 1e-9) -> np.ndarray:
    """Elimina vértices consecutivos repetidos para estabilizar la geometría."""
    if len(poly) == 0:
        return poly

    clean: List[np.ndarray] = [np.asarray(poly[0], dtype=np.float64)]
    for vertex in poly[1:]:
        vertex = np.asarray(vertex, dtype=np.float64)
        if np.linalg.norm(vertex - clean[-1]) > tol:
            clean.append(vertex)

    if len(clean) > 1 and np.linalg.norm(clean[0] - clean[-1]) <= tol:
        clean.pop()

    return np.asarray(clean, dtype=np.float64)


def _is_inside_halfspace(point: np.ndarray, edge: str, box: np.ndarray) -> bool:
    """Chequea pertenencia respecto a una de las 4 paredes del rectángulo."""
    x_max, y_max = float(box[0]), float(box[1])
    x, y = float(point[0]), float(point[1])
    if edge == "left":
        return x >= 0.0
    if edge == "right":
        return x <= x_max
    if edge == "bottom":
        return y >= 0.0
    if edge == "top":
        return y <= y_max
    raise ValueError(f"Edge desconocido: {edge}")


def _segment_box_intersection(
    p1: np.ndarray,
    p2: np.ndarray,
    edge: str,
    box: np.ndarray,
) -> np.ndarray:
    """Intersección entre un segmento y una pared axis-aligned del rectángulo."""
    p1 = np.asarray(p1, dtype=np.float64)
    p2 = np.asarray(p2, dtype=np.float64)
    delta = p2 - p1
    x_max, y_max = float(box[0]), float(box[1])

    if edge in ("left", "right"):
        x_edge = 0.0 if edge == "left" else x_max
        if abs(delta[0]) < 1e-12:
            return np.array([x_edge, p1[1]], dtype=np.float64)
        t = (x_edge - p1[0]) / delta[0]
        y = p1[1] + t * delta[1]
        return np.array([x_edge, y], dtype=np.float64)

    y_edge = 0.0 if edge == "bottom" else y_max
    if abs(delta[1]) < 1e-12:
        return np.array([p1[0], y_edge], dtype=np.float64)
    t = (y_edge - p1[1]) / delta[1]
    x = p1[0] + t * delta[0]
    return np.array([x, y_edge], dtype=np.float64)


def _clip_polygon_to_box(poly: np.ndarray, box: np.ndarray) -> np.ndarray:
    """
    Recorta un polígono contra el rectángulo [0, box_x] x [0, box_y]
    usando Sutherland-Hodgman.
    """
    output = np.asarray(poly, dtype=np.float64)
    if len(output) == 0:
        return output

    for edge in ("left", "right", "bottom", "top"):
        if len(output) == 0:
            break

        input_vertices = output
        output_list: List[np.ndarray] = []
        s = input_vertices[-1]

        for e in input_vertices:
            s_inside = _is_inside_halfspace(s, edge, box)
            e_inside = _is_inside_halfspace(e, edge, box)

            if e_inside:
                if not s_inside:
                    output_list.append(_segment_box_intersection(s, e, edge, box))
                output_list.append(np.asarray(e, dtype=np.float64))
            elif s_inside:
                output_list.append(_segment_box_intersection(s, e, edge, box))

            s = e

        output = np.asarray(output_list, dtype=np.float64)

    return _deduplicate_polygon(output)


def _point_in_convex_polygon(point: np.ndarray, poly: np.ndarray, tol: float = 1e-9) -> bool:
    """Prueba robusta para polígonos convexos usando el signo del producto cruz."""
    if len(poly) < 3:
        return False

    signs: List[float] = []
    for i in range(len(poly)):
        a = poly[i]
        b = poly[(i + 1) % len(poly)]
        cross = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])
        if abs(cross) > tol:
            signs.append(float(np.sign(cross)))

    if not signs:
        return False

    arr = np.asarray(signs, dtype=np.float64)
    return bool(np.all(arr >= 0.0) or np.all(arr <= 0.0))


def _nearest_point_on_segment(point: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Proyección ortogonal de un punto sobre un segmento 2D."""
    ab = b - a
    denom = float(np.dot(ab, ab))
    if denom < 1e-12:
        return a.copy()
    t = float(np.clip(np.dot(point - a, ab) / denom, 0.0, 1.0))
    return a + t * ab


def _project_point_to_polygon(point: np.ndarray, poly: np.ndarray) -> Tuple[np.ndarray, float]:
    """
    Si el punto está dentro, lo retorna. Si está fuera, retorna el punto más
    cercano sobre el borde del polígono y la distancia al borde.
    """
    point = np.asarray(point, dtype=np.float64)
    if _point_in_convex_polygon(point, poly):
        nearest_dist = min(
            np.linalg.norm(_nearest_point_on_segment(point, poly[i], poly[(i + 1) % len(poly)]) - point)
            for i in range(len(poly))
        )
        return point.copy(), float(nearest_dist)

    best_point = poly[0].copy()
    best_dist2 = float("inf")
    for i in range(len(poly)):
        a = poly[i]
        b = poly[(i + 1) % len(poly)]
        candidate = _nearest_point_on_segment(point, a, b)
        dist2 = float(np.sum((candidate - point) ** 2))
        if dist2 < best_dist2:
            best_dist2 = dist2
            best_point = candidate

    return best_point, float(math.sqrt(best_dist2))


def _voronoi_finite_polygons_2d(vor: Voronoi, radius: float) -> Tuple[List[List[int]], np.ndarray]:
    """
    Reconstruye regiones infinitas de Voronoi como polígonos finitos.

    Basado en la receta oficial de SciPy, adaptada a esta tesis para luego
    recortarlas contra el arena rectangular.
    """
    if vor.points.shape[1] != 2:
        raise ValueError("Solo se soporta Voronoi 2D.")

    new_regions: List[List[int]] = []
    new_vertices = vor.vertices.tolist()
    center = vor.points.mean(axis=0)

    all_ridges: Dict[int, List[Tuple[int, int, int]]] = {}
    for (p1, p2), (v1, v2) in zip(vor.ridge_points, vor.ridge_vertices):
        all_ridges.setdefault(p1, []).append((p2, v1, v2))
        all_ridges.setdefault(p2, []).append((p1, v1, v2))

    for point_idx, region_idx in enumerate(vor.point_region):
        region = vor.regions[region_idx]
        if not region:
            new_regions.append([])
            continue

        if all(v >= 0 for v in region):
            new_regions.append(region)
            continue

        new_region = [v for v in region if v >= 0]
        ridges = all_ridges.get(point_idx, [])

        for neighbor_idx, v1, v2 in ridges:
            if v2 < 0:
                v1, v2 = v2, v1

            if v1 >= 0 and v2 >= 0:
                continue

            tangent = vor.points[neighbor_idx] - vor.points[point_idx]
            tangent /= _safe_norm(tangent)
            normal = np.array([-tangent[1], tangent[0]], dtype=np.float64)

            midpoint = 0.5 * (vor.points[point_idx] + vor.points[neighbor_idx])
            direction = np.sign(np.dot(midpoint - center, normal)) * normal
            far_point = vor.vertices[v2] + direction * radius

            new_vertices.append(far_point.tolist())
            new_region.append(len(new_vertices) - 1)

        vs = np.asarray([new_vertices[v] for v in new_region], dtype=np.float64)
        c = np.mean(vs, axis=0)
        angles = np.arctan2(vs[:, 1] - c[1], vs[:, 0] - c[0])
        order = np.argsort(angles)
        new_regions.append([new_region[i] for i in order])

    return new_regions, np.asarray(new_vertices, dtype=np.float64)


class PyramidalHeuristicController:
    """
    Controlador baseline basado en una arquitectura piramidal Voronoi + PSO.

    Flujo por timestep:
      1. Calcula Voronoi acotado con las posiciones actuales de los robots.
      2. Para cada robot, construye un vector "PSO" con:
         - inercia de su movimiento anterior,
         - atracción social hacia los hotspots,
         - sesgo suave hacia el centroide de su celda,
         - empuje hacia el interior si va pegado al borde de la celda.
      3. Proyecta el punto deseado dentro de la celda de Voronoi.
      4. Convierte el vector resultante a velocidades [v, omega].

    `predict(estado_global)` retorna:
        {
            "robot_0": np.array([v, omega], dtype=np.float32),
            ...
        }

    Además guarda `self.debug_data`, útil para superponer Voronoi y vectores
    sobre el render del entorno sin tocar `swarm_env_skeleton.py`.
    """

    def __init__(
        self,
        arena_size: Tuple[float, float] = (3.0, 3.0),
        v_max: float = V_MAX,
        omega_max: float = OMEGA_MAX,
        inertia_gain: float = 0.55,
        hotspot_gain: float = 1.35,
        centroid_gain: float = 0.40,
        boundary_gain: float = 0.85,
        inverse_distance_gain: float = 0.18,
        max_projection_step: float = 0.45,
        interior_bias: float = 0.08,
        boundary_margin: float = 0.12,
        k_v: float = 1.40,
        k_omega: float = 2.20,
        default_hotspot_sigma: float = 0.18,
    ) -> None:
        self.arena_size = np.asarray(arena_size, dtype=np.float64)
        self.v_max = float(v_max)
        self.omega_max = float(omega_max)

        self.inertia_gain = float(inertia_gain)
        self.hotspot_gain = float(hotspot_gain)
        self.centroid_gain = float(centroid_gain)
        self.boundary_gain = float(boundary_gain)
        self.inverse_distance_gain = float(inverse_distance_gain)
        self.max_projection_step = float(max_projection_step)
        self.interior_bias = float(interior_bias)
        self.boundary_margin = float(boundary_margin)
        self.k_v = float(k_v)
        self.k_omega = float(k_omega)
        self.default_hotspot_sigma = float(default_hotspot_sigma)

        # Memoria tipo "velocidad de partícula" para el término de inercia.
        self._velocity_memory: Dict[str, np.ndarray] = {}

        # Estructura opcional para debugging / render.
        self.debug_data: Dict[str, Dict[str, Any]] = {}

    def reset(self, agent_ids: List[str]) -> None:
        """Limpia memoria interna al inicio de cada episodio."""
        self._velocity_memory = {
            agent_id: np.zeros(2, dtype=np.float64) for agent_id in agent_ids
        }
        self.debug_data = {}

    def predict(self, estado_global: Any) -> Dict[str, np.ndarray]:
        """
        Calcula acciones continuas `[v, omega]` para todos los robots.

        El controlador acepta:
          - un diccionario explícito con estado global, o
          - directamente una instancia del entorno, para facilitar pruebas.
        """
        state = self._parse_global_state(estado_global)
        agent_ids = state["agent_ids"]
        agent_states = state["agent_states"]
        hotspots = state["hotspots"]
        hotspot_sigmas = state["hotspot_sigmas"]
        self.arena_size = state["arena_size"]

        if not self._velocity_memory:
            self.reset(agent_ids)

        positions = np.vstack([agent_states[agent_id][:2] for agent_id in agent_ids])
        cells = self._compute_bounded_voronoi(positions)

        actions: Dict[str, np.ndarray] = {}
        self.debug_data = {}

        for idx, agent_id in enumerate(agent_ids):
            state_i = agent_states[agent_id]
            position = state_i[:2]
            theta = float(state_i[2])

            cell_polygon = cells[idx]
            cell_centroid = _polygon_centroid(cell_polygon)
            hotspot_vector, hotspot_weights = self._compute_hotspot_vector(
                position=position,
                hotspots=hotspots,
                hotspot_sigmas=hotspot_sigmas,
            )

            inertia_vector = self.inertia_gain * self._velocity_memory[agent_id]
            centroid_vector = self.centroid_gain * (cell_centroid - position)

            _, clearance = _project_point_to_polygon(position, cell_polygon)
            if clearance < self.boundary_margin:
                inward = cell_centroid - position
                inward = inward / _safe_norm(inward)
                boundary_vector = self.boundary_gain * (1.0 - clearance / self.boundary_margin) * inward
            else:
                boundary_vector = np.zeros(2, dtype=np.float64)

            raw_vector = (
                inertia_vector
                + self.hotspot_gain * hotspot_vector
                + centroid_vector
                + boundary_vector
            )

            candidate_step = _clip_vector(raw_vector, self.max_projection_step)
            candidate_point = position + candidate_step

            projected_point, _ = _project_point_to_polygon(candidate_point, cell_polygon)
            safe_point = projected_point + self.interior_bias * (cell_centroid - projected_point)
            safe_point, _ = _project_point_to_polygon(safe_point, cell_polygon)

            final_vector = safe_point - position
            if np.linalg.norm(final_vector) < 1e-4:
                safe_point, _ = _project_point_to_polygon(cell_centroid, cell_polygon)
                final_vector = safe_point - position

            v_cmd, omega_cmd = self._vector_to_unicycle_command(final_vector, theta)
            actions[agent_id] = np.array([v_cmd, omega_cmd], dtype=np.float32)

            # Actualiza memoria PSO para el siguiente timestep.
            self._velocity_memory[agent_id] = 0.65 * self._velocity_memory[agent_id] + 0.35 * final_vector

            self.debug_data[agent_id] = {
                "position": position.copy(),
                "cell_polygon": cell_polygon.copy(),
                "cell_centroid": cell_centroid.copy(),
                "candidate_point": candidate_point.copy(),
                "projected_point": projected_point.copy(),
                "safe_point": safe_point.copy(),
                "raw_vector": raw_vector.copy(),
                "final_vector": final_vector.copy(),
                "clearance": float(clearance),
                "theta": float(theta),
                "hotspot_weights": hotspot_weights.copy(),
            }

        return actions

    def _parse_global_state(self, estado_global: Any) -> Dict[str, Any]:
        """Normaliza diferentes formatos de entrada al mismo esquema interno."""
        if hasattr(estado_global, "_estados") and hasattr(estado_global, "_field"):
            env = estado_global
            agent_ids = list(env.agents)
            return {
                "agent_ids": agent_ids,
                "agent_states": {
                    agent_id: np.asarray(env._estados[agent_id], dtype=np.float64).copy()
                    for agent_id in agent_ids
                },
                "hotspots": np.asarray(env._field.posiciones_objetivos, dtype=np.float64),
                "hotspot_sigmas": np.asarray(env._field.sigmas_objetivos, dtype=np.float64),
                "arena_size": np.asarray(env.arena_size, dtype=np.float64).copy(),
            }

        if not isinstance(estado_global, Mapping):
            raise TypeError(
                "estado_global debe ser un Mapping o una instancia del entorno."
            )

        agent_states_raw = (
            estado_global.get("agent_states")
            or estado_global.get("states")
            or estado_global.get("estados")
        )
        if not isinstance(agent_states_raw, Mapping) or not agent_states_raw:
            raise ValueError(
                "estado_global debe incluir `agent_states` como dict agente -> [x, y, theta, v, omega]."
            )

        agent_ids = list(estado_global.get("agent_ids", agent_states_raw.keys()))
        agent_states = {
            agent_id: np.asarray(agent_states_raw[agent_id], dtype=np.float64).flatten()
            for agent_id in agent_ids
        }

        hotspots = np.asarray(
            estado_global.get("hotspots", estado_global.get("objetivos", np.empty((0, 2)))),
            dtype=np.float64,
        )
        if hotspots.size == 0:
            hotspots = np.empty((0, 2), dtype=np.float64)
        else:
            hotspots = np.atleast_2d(hotspots)

        hotspot_sigmas = np.asarray(
            estado_global.get(
                "hotspot_sigmas",
                np.full(len(hotspots), self.default_hotspot_sigma, dtype=np.float64),
            ),
            dtype=np.float64,
        )

        arena_size = np.asarray(
            estado_global.get("arena_size", self.arena_size),
            dtype=np.float64,
        )

        return {
            "agent_ids": agent_ids,
            "agent_states": agent_states,
            "hotspots": hotspots,
            "hotspot_sigmas": hotspot_sigmas,
            "arena_size": arena_size,
        }

    def _compute_hotspot_vector(
        self,
        position: np.ndarray,
        hotspots: np.ndarray,
        hotspot_sigmas: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Componente PSO-social:
        crea un atractor ponderado por cercanía y por sigma de cada hotspot.
        """
        if len(hotspots) == 0:
            return np.zeros(2, dtype=np.float64), np.zeros(0, dtype=np.float64)

        sigmas = np.asarray(hotspot_sigmas, dtype=np.float64).reshape(-1)
        if len(sigmas) != len(hotspots):
            sigmas = np.full(len(hotspots), self.default_hotspot_sigma, dtype=np.float64)

        diff = hotspots - position
        dists = np.linalg.norm(diff, axis=1)
        safe_dists = np.maximum(dists, 1e-4)
        sigma2 = np.maximum(sigmas ** 2, 1e-6)

        # Peso combinado: "qué tan relevante" es cada hotspot para este robot.
        gaussian_gain = np.exp(-(safe_dists ** 2) / (2.0 * sigma2))
        inverse_distance = self.inverse_distance_gain / safe_dists
        weights = gaussian_gain + inverse_distance

        attractor = np.average(hotspots, axis=0, weights=weights)
        return attractor - position, weights

    def _compute_bounded_voronoi(self, points: np.ndarray) -> Dict[int, np.ndarray]:
        """Calcula Voronoi finito y recortado al rectángulo del arena."""
        if len(points) == 1:
            return {0: self._arena_box_polygon()}

        try:
            vor = Voronoi(points, qhull_options="Qbb Qc Qx QJ")
            radius = float(np.linalg.norm(self.arena_size) * 4.0)
            regions, vertices = _voronoi_finite_polygons_2d(vor, radius=radius)

            cells: Dict[int, np.ndarray] = {}
            for idx in range(len(points)):
                region = regions[idx]
                polygon = vertices[region]
                clipped = _clip_polygon_to_box(polygon, self.arena_size)
                cells[idx] = self._sanitize_cell(clipped, points[idx])
            return cells
        except Exception:
            return self._fallback_cells(points)

    def _sanitize_cell(self, polygon: np.ndarray, reference_point: np.ndarray) -> np.ndarray:
        """Asegura una celda válida incluso con degeneraciones geométricas."""
        poly = _deduplicate_polygon(np.asarray(polygon, dtype=np.float64))
        if len(poly) < 3 or abs(_polygon_area(poly)) < 1e-8:
            return self._fallback_cell(reference_point)
        return poly

    def _fallback_cells(self, points: np.ndarray) -> Dict[int, np.ndarray]:
        """Fallback defensivo si Qhull falla por degeneración numérica."""
        return {idx: self._fallback_cell(point) for idx, point in enumerate(points)}

    def _fallback_cell(self, point: np.ndarray) -> np.ndarray:
        """Celda local cuadrada y recortada al arena para casos extremos."""
        half = 0.22
        x, y = float(point[0]), float(point[1])
        poly = np.array(
            [
                [x - half, y - half],
                [x + half, y - half],
                [x + half, y + half],
                [x - half, y + half],
            ],
            dtype=np.float64,
        )
        return _clip_polygon_to_box(poly, self.arena_size)

    def _arena_box_polygon(self) -> np.ndarray:
        """Polígono del contorno del arena."""
        x_max, y_max = float(self.arena_size[0]), float(self.arena_size[1])
        return np.array(
            [[0.0, 0.0], [x_max, 0.0], [x_max, y_max], [0.0, y_max]],
            dtype=np.float64,
        )

    def _vector_to_unicycle_command(self, vector: np.ndarray, theta: float) -> Tuple[float, float]:
        """
        Mapea el vector deseado dentro de la celda a un comando [v, omega].

        - omega sigue un control proporcional sobre el error de heading.
        - v se modula por la alineación `cos(error)` para evitar avanzar fuerte
          mientras el robot todavía está girando.
        """
        distance = float(np.linalg.norm(vector))
        if distance < 1e-6:
            return 0.0, 0.0

        desired_heading = math.atan2(float(vector[1]), float(vector[0]))
        heading_error = _wrap_angle(desired_heading - theta)

        omega_cmd = float(np.clip(self.k_omega * heading_error, -self.omega_max, self.omega_max))
        alignment = max(0.0, math.cos(heading_error))
        v_cmd = float(np.clip(self.k_v * distance * alignment, 0.0, self.v_max))
        return v_cmd, omega_cmd
