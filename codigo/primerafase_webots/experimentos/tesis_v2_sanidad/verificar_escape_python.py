"""
verificar_escape_python.py
==========================
VERIFICACIÓN: ¿el escape aporta cobertura POR SÍ MISMO?

Motivo
------
La cobertura con escape en Webots (0.5739) SUPERA el control de Python del
mismo modelo con bordes bloqueantes sobre las mismas 18 semillas (0.4426). La
física no debería mejorar el desempeño respecto del entorno idealizado, así
que hay que explicarlo.

Hipótesis: la maniobra de escape no sólo desatasca — también aporta cobertura
por sí misma (retroceso + giro rompe agrupamientos y hace recorrer zonas que
la política sola no visitaría). Si es así, el 0.5739 es un resultado HÍBRIDO
política+heurística y hay que declararlo como tal.

Diseño
------
Se porta el escape al entorno de Python (sin física, sin filtro CBF) con el
MISMO criterio de detección y la MISMA ley de ascenso sobre h, y se corren las
mismas 18 semillas con modo_borde="bloqueante".

    Python sin escape : 0.4426   (referencia ya medida, control_python_multi)
    Python con escape : ?
    Webots con escape : 0.5739

Si Python con escape también sube por encima de 0.4426, el escape es una
heurística de cobertura y hay que decirlo. Si se queda cerca de 0.4426, el
exceso viene de Webots y se investiga aparte.

Adaptación declarada
--------------------
La detección del coordinador es conjuntiva de TRES términos: poco
desplazamiento ∧ el CBF intervino ∧ h_min pequeño. En Python NO HAY filtro
CBF, así que el segundo término no existe y se usa el análogo honesto de dos
términos (desplazamiento ∧ h_min). Todo lo demás —ley de ascenso máximo,
composición de normales activas, histéresis, refractario, topes— es idéntico.

Esto hace que el escape de Python dispare algo MÁS fácil que el de Webots (le
falta un filtro de especificidad), lo cual es conservador para la hipótesis:
si aun así Python no sube, el exceso es de Webots con más razón.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

from stable_baselines3 import PPO

from lib.swarm_env_skeleton import D_SAFE, make_env

# ── Configuración idéntica a control_python_multi.py ─────────────────────
N_AGENTES:   int = 5
ARENA:       Tuple[float, float] = (3.0, 3.0)
MAX_STEPS:   int = 500
COMM_RADIUS: float = 1.0
SEED_BASE:   int = 42
N_EPISODIOS: int = 18
SEMILLAS: List[int] = [SEED_BASE * 10_000 + i for i in range(N_EPISODIOS)]

PESOS_TRIAL13: Dict[str, float] = {
    "lambda_gradient": 0.5622468083379316,
    "lambda_entropy":  1.1403296484190344,
    "lambda_ibrm":     0.48380314172632155,
    "lambda_cbf":      2.9655314099141474,
}

RUTA_MODELO: Path = _CARPETA / "modelo_sanidad.zip"
DIR_SALIDA:  Path = _CARPETA / "resultados"

# ── Parámetros del escape (idénticos al coordinador) ─────────────────────
ELE_A:        float = 0.05
D_SEGURA:     float = 0.18
D_ROBOTS:     float = 0.25
V_MAX:        float = 0.31
OMEGA_MAX:    float = 6.2832

ESC_UMBRAL_DESPLAZAMIENTO: float = 0.002
ESC_N_DETECCION:           int   = 6
ESC_H_ENTRADA:             float = 0.03
ESC_H_SALIDA:              float = 0.05
ESC_MIN_DECISIONES:        int   = 4
ESC_MAX_DECISIONES:        int   = 25
ESC_REFRACTARIO:           int   = 15
ESC_UMBRAL_ACTIVA:         float = 0.06
ESC_NORMA_MINIMA:          float = 0.20
ESC_FRACCION_V:            float = 0.5
ESC_FRACCION_OMEGA:        float = 0.5

# Referencias ya medidas.
REF_PY_SIN_ESCAPE:  float = 0.4426
REF_WEBOTS_ESCAPE:  float = 0.5739


# =============================================================================
# ESCAPE (puerto del coordinador)
# =============================================================================

def punto_de_mira(pose: np.ndarray) -> np.ndarray:
    """p = c + ℓa·(cosθ, senθ)."""
    return np.array([
        pose[0] + ELE_A * math.cos(pose[2]),
        pose[1] + ELE_A * math.sin(pose[2]),
    ])


def normales_activas(
    i: int, poses: np.ndarray,
) -> Tuple[Optional[np.ndarray], float]:
    """
    Suma normalizada de TODAS las normales activas (pared y robot-robot con
    h < ESC_UMBRAL_ACTIVA), más el h mínimo. None si no hay dirección de
    escape (normales opuestas).
    """
    p_i = punto_de_mira(poses[i])
    Wx, Wy = ARENA
    candidatas = [
        (np.array([1.0, 0.0]),  float(p_i[0]) - D_SEGURA),
        (np.array([-1.0, 0.0]), (Wx - float(p_i[0])) - D_SEGURA),
        (np.array([0.0, 1.0]),  float(p_i[1]) - D_SEGURA),
        (np.array([0.0, -1.0]), (Wy - float(p_i[1])) - D_SEGURA),
    ]
    for j in range(len(poses)):
        if j == i:
            continue
        p_j = punto_de_mira(poses[j])
        delta = p_i - p_j
        dist = float(np.linalg.norm(delta))
        if dist < 1e-9:
            continue
        candidatas.append((delta / dist, dist - D_ROBOTS))

    normales, h_min = [], float("inf")
    for normal, h in candidatas:
        h_min = min(h_min, h)
        if h < ESC_UMBRAL_ACTIVA:
            normales.append(normal)
    if not normales:
        return None, h_min
    suma = np.sum(np.asarray(normales), axis=0)
    norma = float(np.linalg.norm(suma))
    if norma < ESC_NORMA_MINIMA:
        return None, h_min
    return suma / norma, h_min


def accion_escape(direccion: np.ndarray, theta: float) -> np.ndarray:
    """Ley de ascenso máximo sobre h: v = V·sign(a), ω = Ω·sign(b)."""
    heading = np.array([math.cos(theta), math.sin(theta)])
    perp    = np.array([-math.sin(theta), math.cos(theta)])
    a = float(direccion @ heading)
    b = float(direccion @ perp)
    return np.array([
        ESC_FRACCION_V * V_MAX * np.sign(a),
        ESC_FRACCION_OMEGA * OMEGA_MAX * np.sign(b),
    ], dtype=np.float32)


class GestorEscape:
    """Máquina de estados del escape, una por enjambre."""

    def __init__(self, n: int) -> None:
        self.n = n
        self.reset()

    def reset(self) -> None:
        n = self.n
        self.estado      = [0] * n     # 0 inactivo, 1 escapando, 2 refractario
        self.deteccion   = [0] * n
        self.en_curso    = [0] * n
        self.refractario = [0] * n
        self.pose_previa: Optional[np.ndarray] = None
        # Métricas
        self.n_escapes   = [0] * n
        self.decisiones  = [0] * n
        self.infactibles = [0] * n
        self.agotados    = [0] * n

    def gestionar(
        self, i: int, poses: np.ndarray, u_nom: np.ndarray,
    ) -> np.ndarray:
        """Devuelve la acción a ejecutar para el agente `i`."""
        direccion, h_min = normales_activas(i, poses)

        if self.estado[i] == 2:
            self.refractario[i] -= 1
            if self.refractario[i] <= 0:
                self.estado[i] = 0
            return u_nom

        if self.estado[i] == 1:
            self.en_curso[i] += 1
            if self.en_curso[i] >= ESC_MAX_DECISIONES:
                self.agotados[i] += 1
            termina = (
                (self.en_curso[i] >= ESC_MIN_DECISIONES and h_min > ESC_H_SALIDA)
                or self.en_curso[i] >= ESC_MAX_DECISIONES
            )
            if termina or direccion is None:
                if direccion is None and not termina:
                    self.infactibles[i] += 1
                self.estado[i]      = 2
                self.refractario[i] = ESC_REFRACTARIO
                self.en_curso[i]    = 0
                self.deteccion[i]   = 0
                return u_nom
            self.decisiones[i] += 1
            return accion_escape(direccion, float(poses[i, 2]))

        # Inactivo. NOTA: sin el término "el CBF intervino" (no hay filtro
        # en Python); ver la adaptación declarada en el docstring del módulo.
        desplazamiento = float("inf")
        if self.pose_previa is not None:
            desplazamiento = float(np.linalg.norm(
                poses[i, :2] - self.pose_previa[i, :2]
            ))
        estancado = (
            desplazamiento < ESC_UMBRAL_DESPLAZAMIENTO
            and h_min < ESC_H_ENTRADA
        )
        self.deteccion[i] = self.deteccion[i] + 1 if estancado else 0

        if self.deteccion[i] >= ESC_N_DETECCION:
            if direccion is None:
                self.infactibles[i] += 1
                self.deteccion[i]   = 0
                self.estado[i]      = 2
                self.refractario[i] = ESC_REFRACTARIO
                return u_nom
            self.estado[i]      = 1
            self.en_curso[i]    = 1
            self.deteccion[i]   = 0
            self.n_escapes[i]  += 1
            self.decisiones[i] += 1
            return accion_escape(direccion, float(poses[i, 2]))

        return u_nom


# =============================================================================
# EPISODIO
# =============================================================================

def correr_episodio(
    env, modelo: PPO, seed_ep: int, gestor: Optional[GestorEscape],
) -> Dict[str, float]:
    """Un episodio determinista, con o sin escape."""
    obs, _ = env.reset(seed=seed_ep)
    agentes: List[str] = list(obs.keys())
    n_a = len(agentes)
    if gestor is not None:
        gestor.reset()

    pares15: set = set()
    pares22: set = set()
    n_pasos = 0
    done = False

    while not done:
        acciones, _ = modelo.predict(
            np.stack([obs[a] for a in agentes]), deterministic=True
        )
        acciones = np.asarray(acciones, dtype=np.float32)

        if gestor is not None:
            poses = np.array([env._estados[a][:3] for a in agentes])
            for i in range(n_a):
                acciones[i] = gestor.gestionar(i, poses, acciones[i])
            gestor.pose_previa = poses.copy()

        obs, _, term, trunc, _ = env.step(
            {a: acciones[k] for k, a in enumerate(agentes)}
        )
        n_pasos += 1
        pos = np.array([env._estados[a][:2] for a in agentes])
        for ii in range(n_a):
            for jj in range(ii + 1, n_a):
                d = float(np.linalg.norm(pos[ii] - pos[jj]))
                if d < 0.15:
                    pares15.add((ii, jj))
                if d < 0.22:
                    pares22.add((ii, jj))
        done = all(trunc.values()) or all(term.values())

    fila = {
        "cobertura_aoi_final": round(
            1.0 - float(np.mean(env._field._grid_aoi)), 6
        ),
        "colisiones_015": len(pares15),
        "colisiones_022": len(pares22),
        "frac_pasos_agente_recorte": round(
            sum(env.contador_recortes.values()) / (n_pasos * n_a), 6
        ) if n_pasos else 0.0,
        "pasos": n_pasos,
    }
    if gestor is not None:
        fila["escape_n"]          = sum(gestor.n_escapes)
        fila["escape_decisiones"] = sum(gestor.decisiones)
        fila["escape_frac_ciclo"] = round(
            sum(gestor.decisiones) / (n_pasos * n_a), 4
        ) if n_pasos else 0.0
        fila["escape_infactibles"] = sum(gestor.infactibles)
        fila["escape_agotados"]    = sum(gestor.agotados)
    else:
        for k in ("escape_n", "escape_decisiones", "escape_frac_ciclo",
                  "escape_infactibles", "escape_agotados"):
            fila[k] = 0
    return fila


def ic95(x: np.ndarray) -> Tuple[float, float, float]:
    """Media e IC95 por aproximación normal."""
    n = len(x); m = float(np.mean(x))
    ee = float(np.std(x, ddof=1)) / math.sqrt(n)
    return m, m - 1.96 * ee, m + 1.96 * ee


def main() -> None:
    """Corre las 18 semillas con y sin escape y compara."""
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    modelo = PPO.load(str(RUTA_MODELO), device="cpu")

    print("═" * 72)
    print("  VERIFICACIÓN — ¿el escape aporta cobertura por sí mismo?")
    print("═" * 72)

    filas: List[Dict[str, object]] = []
    resumen: Dict[str, np.ndarray] = {}

    for etiqueta, usar_escape in (("sin_escape", False), ("con_escape", True)):
        env = make_env(
            n_agents       = N_AGENTES,
            arena_size     = ARENA,
            max_steps      = MAX_STEPS,
            comm_radius    = COMM_RADIUS,
            reward_weights = PESOS_TRIAL13,
            domain_rand    = False,
            seed           = SEED_BASE,
            modo_borde     = "bloqueante",
        )
        gestor = GestorEscape(N_AGENTES) if usar_escape else None
        cobs: List[float] = []
        for s in SEMILLAS:
            m = correr_episodio(env, modelo, s, gestor)
            filas.append({"condicion": etiqueta, "semilla": s, **m})
            cobs.append(float(m["cobertura_aoi_final"]))
        resumen[etiqueta] = np.array(cobs)
        print(f"  {etiqueta:12s} cobertura = {np.mean(cobs):.4f} ± "
              f"{np.std(cobs):.4f}")

    ruta_csv = DIR_SALIDA / "verificacion_escape_python.csv"
    with open(ruta_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)

    d = resumen["con_escape"] - resumen["sin_escape"]
    m, lo, hi = ic95(d)
    esc = [r for r in filas if r["condicion"] == "con_escape"]
    frac = np.array([float(r["escape_frac_ciclo"]) for r in esc])
    n_esc = np.array([float(r["escape_n"]) for r in esc])

    L: List[str] = []
    L.append("VERIFICACIÓN — ¿el escape aporta cobertura por sí mismo?")
    L.append(f"{N_EPISODIOS} semillas ({SEMILLAS[0]}-{SEMILLAS[-1]}), "
             f"{N_AGENTES} agentes, modo_borde='bloqueante', modelo_sanidad,")
    L.append("deterministic=True, domain_rand=False. Entorno de Python: SIN")
    L.append("física y SIN filtro CBF.")
    L.append("=" * 70)
    L.append("")
    L.append("COBERTURA")
    L.append(f"  Python sin escape : {resumen['sin_escape'].mean():.4f} ± "
             f"{resumen['sin_escape'].std():.4f}")
    L.append(f"  Python con escape : {resumen['con_escape'].mean():.4f} ± "
             f"{resumen['con_escape'].std():.4f}")
    L.append(f"  Webots con escape : {REF_WEBOTS_ESCAPE:.4f}  (referencia)")
    L.append("")
    L.append(f"  Δ pareado (con − sin) = {m:+.4f}  IC95 [{lo:+.4f}, {hi:+.4f}]")
    L.append(f"  episodios mejores: {int(np.sum(d > 0))}/{N_EPISODIOS}")
    L.append("")
    L.append("ACTIVIDAD DEL ESCAPE EN PYTHON")
    L.append(f"  escapes por episodio      : {n_esc.mean():.2f}")
    L.append(f"  fracción de ciclo         : {frac.mean():.4f}")
    L.append(f"  infactibles / agotados    : "
             f"{sum(float(r['escape_infactibles']) for r in esc):.0f} / "
             f"{sum(float(r['escape_agotados']) for r in esc):.0f}")
    L.append("")
    L.append("INTERPRETACIÓN")
    if lo > 0:
        L.append("  El escape SÍ aporta cobertura por sí mismo (IC95 excluye")
        L.append("  el cero en un entorno sin física ni filtro). El resultado")
        L.append("  de Webots es HÍBRIDO política+heurística y debe declararse")
        L.append("  como tal: el escape no sólo desatasca, también explora.")
    elif hi < 0:
        L.append("  El escape REDUCE la cobertura en Python: su beneficio en")
        L.append("  Webots proviene exclusivamente de desatascar.")
    else:
        L.append("  El escape NO aporta cobertura por sí mismo (IC95 incluye")
        L.append("  el cero). El exceso de Webots proviene de otra causa y hay")
        L.append("  que investigarlo aparte.")
    L.append("")
    L.append("ADAPTACIÓN DECLARADA")
    L.append("  La detección del coordinador es conjuntiva de TRES términos:")
    L.append("  desplazamiento ∧ CBF intervino ∧ h_min. En Python no hay filtro")
    L.append("  CBF, así que se usa el análogo de DOS términos. Esto hace que")
    L.append("  el escape dispare algo más fácil que en Webots (le falta un")
    L.append("  filtro de especificidad), lo cual es CONSERVADOR para la")
    L.append("  hipótesis: si aun así Python no sube, el exceso es de Webots")
    L.append("  con más razón. La ley de ascenso, la composición de normales,")
    L.append("  la histéresis y los topes son idénticos.")

    resumen_txt = "\n".join(L)
    (DIR_SALIDA / "verificacion_escape_python.txt").write_text(
        resumen_txt, encoding="utf-8"
    )
    print(f"\nCSV → {ruta_csv}\n")
    print(resumen_txt)


if __name__ == "__main__":
    main()
