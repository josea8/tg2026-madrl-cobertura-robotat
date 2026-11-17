"""
correr_fase0_obstaculo.py
=========================
Campaña de seguridad de la FASE 0 de la demo del obstáculo móvil
(`demo_obstaculo_movil.py`), contra `SimuladorRobotat` con SEIS robots (los
cinco agentes 1, 5, 8, 6, 9 y el obstáculo 7) y retardo de actuación PURO
de 0.45 s y de 0.85 s.

Criterio, fijado ANTES de correr (plan aprobado por José, 2026-10-01, con su
ajuste: τ = 0.85 s también decide)
--------------------------------------------------------------------------
La distancia mínima CONTINUA entre centros, agente–obstáculo, tiene que
quedar > 0.15 m en TODOS los casos guionados y en las 10 tomas, con
τ = 0.45 s y con τ = 0.85 s, para la formulación que va al laboratorio (F2).
Cada caso y cada toma se corre con la rampa de arranque seguro (la primera
toma de una sesión) y sin ella (las siguientes: en el laboratorio la rampa
cuenta por sesión). Una corrida que falte, que no sea válida o que no llegue
a sus decisiones hace que el criterio NO se cumpla. Si no se cumple, no se va
al laboratorio. Se reportan además los pares de agentes bajo 0.15 m, los
fallbacks y rescates del QP y los frenos de respaldo (en esta campaña van en
SOMBRA: se cuenta cuándo habría frenado, pero no frena, para que la distancia
medida sea la del filtro solo). Advertencia (no criterio): mínimo < 0.185 m,
porque el hardware perdió ~3.5 cm de margen contra el simulador.

"Continua" = la pose VERDADERA del simulador, leída por un hilo a 200 Hz
(`MonitorVerdad`), hasta τ + 0.3 s después de la orden de freno final, no la
de las decisiones a 10 Hz (que también se reporta: es lo que se podrá medir en
el laboratorio).

⚠ DECISIÓN DE JOSÉ (2026-10-02): el diseño se congeló en F2 con el peso de
giro condicional DESPUÉS de ver la campaña de diseño, así que el veredicto lo
da el CONJUNTO DE CONFIRMACIÓN (`conf_guionada` + `conf_tomas`): geometrías y
semillas nuevas, fijadas en este archivo antes de correrlo, que no se usaron
para diseñar. La campaña de diseño (`guionada` + `tomas`) se informa, no
decide.

Bloques
-------
  conf_guionada  DECIDE. 19 casos guionados nuevos: otro punto de encuentro
             (fase 2.3 rad, no múltiplo de π/2), arco 0.45 m, disparo a
             0.50 m, corrimientos ±0.06/±0.20, rumbos a 45°/135°/225°/315°,
             encierro con el vecino corrido y en trío, CRUCE del camino del
             obstáculo, otros estacionados. Con y sin rampa.
  conf_tomas DECIDE. 10 tomas con semillas nunca usadas (420100–420109).
             Con y sin rampa.
  guionada   Diseño. Peor caso con la acción nominal REEMPLAZADA por una
             adversaria (`_ModeloConNominalForzada`) que ESPERA quieta hasta
             que el obstáculo está en marcha y a < 0.60 m, y entonces lo ataca:
             de frente (y corrido ±12 cm), de espaldas en reversa, quieto en
             cuatro rumbos, lateral desde afuera, desde adentro y desde el lado
             de la pared, encerrado contra otro agente, detrás, y sorpresa
             (h ≈ 0 cuando el obstáculo arranca). Los otros agentes,
             estacionados lejos. Con y sin rampa.
  tomas      Diseño. 10 tomas completas (500 decisiones), política + CBF +
             escape a factor 0.40, arranques sorteados como en el laboratorio
             y el obstáculo colocado con un error dentro de la tolerancia
             (±6 cm radial, ±25°). Con y sin rampa.
  control    Control NEGATIVO: los casos guionados con la barrera actual (F0,
             "un robot más"). Muestra que la medición detecta una barrera que
             falla. No decide.
  propuesta  F1, la formulación de la propuesta (sin predictor). No decide.
  ablacion   F2 sin el peso de giro (sólo predictor y rescate). No decide.
  mixto      Retardo distinto para agentes y obstáculo. No decide.
  ruido      1 mm de ruido de captura. No decide.
  lazo_lab   Las 10 tomas por el lazo del LABORATORIO (`_correr_episodio`, con
             todas sus reglas), τ = 0.45 s. No decide.

Uso
---
    python correr_fase0_obstaculo.py --paralelo 6
    python correr_fase0_obstaculo.py --bloques guionada --solo E2 --paralelo 4
    python correr_fase0_obstaculo.py --uno ruta/spec.json --ranura 3   (interno)

Salida: `resultados_demo_obstaculo/fase0_<fecha>/`, una carpeta por corrida
(spec.json, resultado.json, decisiones.csv, obstaculo.csv, verdad.csv, log)
y `resumen_fase0.csv` con una fila por corrida. Nada se pisa. El veredicto lo
da `analizar_fase0_obstaculo.py`.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

# ── Constantes de la campaña ──────────────────────────────────────────────
TAUS: Tuple[float, ...] = (0.45, 0.85)
FACTOR: float = 0.40
RPM_ABORTO: float = 200.0
DECISIONES_GUIONADA: int = 350
DECISIONES_TOMA: int = 500
UMBRAL_CRITERIO_M: float = 0.15
UMBRAL_ADVERTENCIA_M: float = 0.185
#: Arco que recorre el obstáculo desde su arranque hasta el punto del
#: encuentro guionado (la cuerda, 0.53 m, deja el arranque a ≥ 0.50 m).
ARCO_ENCUENTRO_M: float = 0.55
#: Fase del encuentro guionado: el lado derecho del círculo, (2.1, 1.5).
#: Ahí el obstáculo avanza hacia +y.
FASE_ENCUENTRO_RAD: float = 0.0
#: Agentes estacionados: esquinas a 0.5 m de las paredes, a 0.81 m del
#: círculo (nunca interactúan con el obstáculo).
ESTACIONADOS: Tuple[Tuple[float, float], ...] = (
    (0.5, 0.5), (2.5, 0.5), (0.5, 2.5), (2.5, 2.5))
#: Disparo de las nominales adversarias: obstáculo en marcha (|v̂| ≥ 0.02)
#: y a menos de esta distancia del agente de referencia.
DISPARO_M: float = 0.60
V_DISPARO_M_S: float = 0.02
#: Error de colocación del obstáculo en las tomas (dentro de la tolerancia
#: de `problemas_obstaculo_al_arrancar`: 8 cm y 30°).
PERTURBACION_RADIAL_M: float = 0.06
PERTURBACION_RUMBO_RAD: float = math.radians(25.0)
#: Puertos por ranura de ejecución en paralelo (lejos de los de las pruebas).
PUERTO_POSES_BASE: int = 23000
PUERTO_RUEDAS_BASE: int = 24000
SEPARACION_PUERTOS: int = 50

V_MAX_POL: float = 0.31
OMEGA_MAX_POL: float = 6.2832

BLOQUES: Tuple[str, ...] = ("conf_guionada", "conf_tomas", "guionada",
                            "tomas", "control", "propuesta", "ablacion",
                            "mixto", "ruido", "lazo_lab")
#: Decide el conjunto de CONFIRMACIÓN (decisión de José, 2026-10-02).
BLOQUES_QUE_DECIDEN: Tuple[str, ...] = ("conf_guionada", "conf_tomas")
#: La campaña de diseño, que se informa con su propio criterio (no decide).
BLOQUES_DE_DISENO: Tuple[str, ...] = ("guionada", "tomas")

# ── Conjunto de confirmación (fijado el 2026-10-02, antes de correrlo) ──
FASE_ENCUENTRO_CONF_RAD: float = 2.3
ARCO_ENCUENTRO_CONF_M: float = 0.45
DISPARO_CONF_M: float = 0.50
ESTACIONADOS_CONF: Tuple[Tuple[float, float], ...] = (
    (0.5, 0.5), (2.5, 0.5), (2.5, 2.5), (2.5, 1.5))
#: Semillas de las tomas de confirmación: nunca usadas (SEMILLAS_LOTE es
#: 420000–420017; la campaña de diseño usó 420000–420009).
SEMILLAS_CONF: Tuple[int, ...] = tuple(42 * 10_000 + 100 + k for k in range(10))


def _envolver(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


# =============================================================================
# ACCIONES NOMINALES ADVERSARIAS
# =============================================================================

def accion_hacia(pose_i: np.ndarray, objetivo: np.ndarray,
                 reversa: bool = False) -> np.ndarray:
    """Derecho a `objetivo` a V_MAX (de frente o de RETROCESO)."""
    rumbo = math.atan2(float(objetivo[1] - pose_i[1]),
                       float(objetivo[0] - pose_i[0]))
    if reversa:
        err = _envolver(rumbo + math.pi - float(pose_i[2]))
        v = -V_MAX_POL * max(0.0, math.cos(err))
    else:
        err = _envolver(rumbo - float(pose_i[2]))
        v = V_MAX_POL * max(0.0, math.cos(err))
    w = max(-OMEGA_MAX_POL, min(OMEGA_MAX_POL, 4.0 * err))
    return np.array([v, w], dtype=np.float32)


class NominalesGuionadas:
    """
    Las nominales adversarias de los casos guionados. Tipos:
      politica      → None (la de la política)
      quieto        → (0, 0) siempre
      hacia         → derecho al CENTRO del obstáculo, a V_MAX
      reversa_hacia → de RETROCESO hacia el obstáculo, a −V_MAX
      hacia_agente  → derecho al agente `j`, a V_MAX

    Las tres últimas ESPERAN quietas hasta el disparo: obstáculo en marcha y
    a < `DISPARO_M` del agente `disparo_de` (por defecto, el mismo). Una vez
    disparadas, siguen. (Revisión de la Fase 0: sin la espera perseguían al
    obstáculo estacionado desde t = 0 y la geometría declarada —lateral,
    corrida, desde la pared— no ocurría.)
    """

    def __init__(self, nominales: Dict[str, Dict[str, Any]], coord: Any,
                 disparo_m: float = DISPARO_M) -> None:
        self._nom = nominales
        self._coord = coord
        self._disparo_m = float(disparo_m)
        self.disparo_paso: Dict[int, int] = {}

    def _pose(self, j: int) -> Optional[np.ndarray]:
        c = self._coord._cache.get(j)
        return c.como_array() if c is not None else None

    def __call__(self, i: int, pose_i: np.ndarray,
                 pose_o: Optional[np.ndarray]) -> Optional[np.ndarray]:
        tipo = self._nom[str(i)]
        t = tipo["tipo"]
        if t == "politica":
            return None
        cero = np.array([0.0, 0.0], dtype=np.float32)
        if t == "quieto" or pose_o is None:
            return cero
        if i not in self.disparo_paso:
            ref = self._pose(int(tipo.get("disparo_de", i)))
            v_obst = self._coord.fuente.velocidad_obstaculo()
            rapidez = float(np.linalg.norm(v_obst)) if v_obst is not None else 0.0
            if (ref is None or rapidez < V_DISPARO_M_S
                    or float(np.linalg.norm(ref[:2] - pose_o[:2]))
                    >= self._disparo_m):
                return cero
            self.disparo_paso[i] = int(self._coord._paso_episodio)
        if t == "hacia":
            return accion_hacia(pose_i, pose_o)
        if t == "reversa_hacia":
            return accion_hacia(pose_i, pose_o, reversa=True)
        if t == "hacia_agente":
            pj = self._pose(int(tipo["j"]))
            return cero if pj is None else accion_hacia(pose_i, pj)
        if t == "hacia_punto":
            # CRUCE: derecho a un punto fijo al otro lado del camino del
            # obstáculo; al llegar (≤ 5 cm), se queda.
            punto = np.asarray(tipo["punto"], dtype=float)
            if float(np.linalg.norm(punto - pose_i[:2])) <= 0.05:
                return cero
            return accion_hacia(pose_i, punto)
        raise ValueError(f"nominal desconocida: {t}")


# =============================================================================
# ESCENARIOS
# =============================================================================

def _punto(fase: float) -> Tuple[float, float]:
    from demo_obstaculo_movil import CENTRO_CIRCULO_ENV, RADIO_CIRCULO_M
    return (CENTRO_CIRCULO_ENV[0] + RADIO_CIRCULO_M * math.cos(fase),
            CENTRO_CIRCULO_ENV[1] + RADIO_CIRCULO_M * math.sin(fase))


def _spec_guionado(nombre: str,
                   protagonistas: Dict[int, Tuple[float, float, float, Dict[str, Any]]],
                   tau: float, formulacion: str,
                   decisiones: int = DECISIONES_GUIONADA) -> Dict[str, Any]:
    """Arma una spec: protagonistas {i: (x, y, θ, nominal)}; el resto, estacionados."""
    from demo_obstaculo_movil import RADIO_CIRCULO_M
    fase0 = FASE_ENCUENTRO_RAD - ARCO_ENCUENTRO_M / RADIO_CIRCULO_M
    poses: Dict[str, List[float]] = {}
    nominales: Dict[str, Dict[str, Any]] = {}
    libres = list(ESTACIONADOS)
    for i in range(5):
        if i in protagonistas:
            x, y, th, nom = protagonistas[i]
            poses[str(i)] = [x, y, th]
            nominales[str(i)] = nom
        else:
            x, y = libres.pop(0)
            poses[str(i)] = [x, y, 0.0]
            nominales[str(i)] = {"tipo": "quieto"}
    return {"bloque": "guionada", "nombre": nombre, "tau": tau,
            "formulacion": formulacion, "decisiones": decisiones,
            "freno": "sombra", "semilla": 420000, "fase0": fase0,
            "obst_perturbacion": [0.0, 0.0], "sin_rampa": False,
            "poses_env": poses, "nominales": nominales, "ruido_m": 0.0}


def escenarios_guionados(tau: float, formulacion: str = "F2"
                         ) -> List[Dict[str, Any]]:
    """Los 17 casos de peor caso, con el encuentro en (2.1, 1.5)."""
    from demo_obstaculo_movil import RADIO_CIRCULO_M, punto_del_circulo
    xe, ye = _punto(FASE_ENCUENTRO_RAD)          # (2.1, 1.5); avance +y
    H = {"tipo": "hacia"}
    Q = {"tipo": "quieto"}
    R = {"tipo": "reversa_hacia"}
    f = formulacion
    s: List[Dict[str, Any]] = []
    # E1 de frente, el agente ataca al obstáculo; corrido ±12 cm
    for d in (0.0, 0.12, -0.12):
        s.append(_spec_guionado(f"E1_frente_hacia_d{d:+.2f}",
                                {0: (xe + d, ye, -math.pi / 2, H)}, tau, f))
    # E2 de espaldas, el agente retrocede hacia el obstáculo
    for d in (0.0, 0.12):
        s.append(_spec_guionado(f"E2_espaldas_reversa_d{d:+.2f}",
                                {0: (xe + d, ye, math.pi / 2, R)}, tau, f))
    # E3 quieto en el camino, cuatro rumbos: el agente tiene que huir
    for etiqueta, th in (("frente", -math.pi / 2), ("espaldas", math.pi / 2),
                         ("afuera", 0.0), ("adentro", math.pi)):
        s.append(_spec_guionado(f"E3_quieto_{etiqueta}",
                                {0: (xe, ye, th, Q)}, tau, f))
    # E4 lateral: desde afuera y desde adentro del círculo
    s.append(_spec_guionado("E4_lateral_afuera",
                            {0: (xe + 0.45, ye, math.pi, H)}, tau, f))
    s.append(_spec_guionado("E4_lateral_adentro",
                            {0: (xe - 0.45, ye, 0.0, H)}, tau, f))
    # E5 encierro: A en el camino, B detrás de A
    s.append(_spec_guionado("E5_encierro_A_quieto_B_hacia_A",
                            {0: (xe, ye, math.pi / 2, Q),
                             1: (xe, ye + 0.35, -math.pi / 2,
                                 {"tipo": "hacia_agente", "j": 0,
                                  "disparo_de": 0})},
                            tau, f))
    s.append(_spec_guionado("E5_encierro_A_y_B_hacia_obstaculo",
                            {0: (xe, ye, -math.pi / 2, H),
                             1: (xe, ye + 0.35, -math.pi / 2,
                                 {"tipo": "hacia", "disparo_de": 0})},
                            tau, f))
    # E6 lateral desde el lado de la pared x = 3 (a 0.28 m de ella). El
    # círculo deja 0.39 m de corredor al punto de mira: no hay encierro
    # contra la pared por construcción, así que no se lo llama "corredor".
    s.append(_spec_guionado("E6_lateral_desde_pared",
                            {0: (2.72, ye, math.pi, H)}, tau, f))
    # E7 detrás: persigue al obstáculo desde su arranque
    fase0 = FASE_ENCUENTRO_RAD - ARCO_ENCUENTRO_M / RADIO_CIRCULO_M
    p0, rumbo0 = punto_del_circulo(fase0)
    atras = p0 - 0.55 * np.array([math.cos(rumbo0), math.sin(rumbo0)])
    s.append(_spec_guionado("E7_detras_persigue",
                            {0: (float(atras[0]), float(atras[1]), rumbo0, H)},
                            tau, f))
    # E8 sorpresa: h ≈ 0 en el instante en que el obstáculo arranca,
    # directamente delante de él sobre la tangente
    adelante = np.array([math.cos(rumbo0), math.sin(rumbo0)])
    pf = p0 + 0.38 * adelante                 # de frente: mira = 0.33
    pe = p0 + 0.28 * adelante                 # de espaldas: mira = 0.33
    s.append(_spec_guionado("E8_sorpresa_frente",
                            {0: (float(pf[0]), float(pf[1]), rumbo0 + math.pi, Q)},
                            tau, f))
    s.append(_spec_guionado("E8_sorpresa_espaldas",
                            {0: (float(pe[0]), float(pe[1]), rumbo0, Q)},
                            tau, f))
    return s


def escenarios_confirmacion_guionados(tau: float) -> List[Dict[str, Any]]:
    """
    Los 19 casos guionados de CONFIRMACIÓN (fijados el 2026-10-02, antes de
    correrlos; ninguno se usó para diseñar). Se arman en el marco local del
    encuentro: P en el círculo, t̂ = sentido de marcha del obstáculo, r̂ =
    radial hacia afuera; `pos(a, l)` = P + a·t̂ + l·r̂.
    """
    from demo_obstaculo_movil import (CENTRO_CIRCULO_ENV, RADIO_CIRCULO_M,
                                      punto_del_circulo)
    fe = FASE_ENCUENTRO_CONF_RAD
    c = np.array(CENTRO_CIRCULO_ENV)
    r_ = np.array([math.cos(fe), math.sin(fe)])
    t_ = np.array([-math.sin(fe), math.cos(fe)])
    P = c + RADIO_CIRCULO_M * r_
    psi_t = math.atan2(t_[1], t_[0])

    def pos(a: float, l: float) -> Tuple[float, float]:
        q = P + a * t_ + l * r_
        return float(q[0]), float(q[1])

    def rumbo(v: np.ndarray) -> float:
        return math.atan2(float(v[1]), float(v[0]))

    fase0 = fe - ARCO_ENCUENTRO_CONF_M / RADIO_CIRCULO_M
    H = {"tipo": "hacia"}
    Q = {"tipo": "quieto"}
    R = {"tipo": "reversa_hacia"}
    casos: List[Tuple[str, Dict[int, Tuple[float, float, float, Dict[str, Any]]]]] = []
    for l in (-0.20, -0.06, 0.06, 0.20):
        casos.append((f"C1_frente_hacia_l{l:+.2f}",
                      {0: (*pos(0.0, l), psi_t + math.pi, H)}))
    for l in (-0.06, 0.20):
        casos.append((f"C2_espaldas_reversa_l{l:+.2f}",
                      {0: (*pos(0.0, l), psi_t, R)}))
    for g in (45, 135, 225, 315):
        casos.append((f"C3_quieto_{g:03d}",
                      {0: (*pos(0.0, 0.0), psi_t + math.radians(g), Q)}))
    casos.append(("C4_lateral_afuera_035",
                  {0: (*pos(0.0, 0.35), rumbo(-r_), H)}))
    casos.append(("C4_lateral_adentro_030",
                  {0: (*pos(0.0, -0.30), rumbo(r_), H)}))
    casos.append(("C5_encierro_B_corrido",
                  {0: (*pos(0.0, 0.0), psi_t, Q),
                   1: (*pos(0.30, 0.10), psi_t + math.pi,
                       {"tipo": "hacia_agente", "j": 0, "disparo_de": 0})}))
    casos.append(("C5_encierro_trio",
                  {0: (*pos(0.0, 0.0), psi_t, Q),
                   1: (*pos(0.30, 0.0), psi_t + math.pi,
                       {"tipo": "hacia_agente", "j": 0, "disparo_de": 0}),
                   2: (*pos(0.60, 0.0), psi_t + math.pi,
                       {"tipo": "hacia_agente", "j": 1, "disparo_de": 0})}))
    casos.append(("C6_cruce_en_P",
                  {0: (*pos(0.0, 0.45), rumbo(-r_),
                       {"tipo": "hacia_punto", "punto": list(pos(0.0, -0.45))})}))
    casos.append(("C6_cruce_adelantado",
                  {0: (*pos(0.15, 0.45), rumbo(-r_),
                       {"tipo": "hacia_punto", "punto": list(pos(0.15, -0.45))})}))
    p0, rumbo0 = punto_del_circulo(fase0)
    t0 = np.array([math.cos(rumbo0), math.sin(rumbo0)])
    r0 = np.array([math.cos(fase0), math.sin(fase0)])
    atras = p0 - 0.45 * t0
    casos.append(("C7_detras_045",
                  {0: (float(atras[0]), float(atras[1]), rumbo0, H)}))
    pf = p0 + 0.401 * t0 + 0.08 * r0        # de frente: h ≈ 0.03
    pe = p0 + 0.301 * t0 + 0.08 * r0        # de espaldas: h ≈ 0.03
    casos.append(("C8_sorpresa_frente_l008",
                  {0: (float(pf[0]), float(pf[1]), rumbo0 + math.pi, Q)}))
    casos.append(("C8_sorpresa_espaldas_l008",
                  {0: (float(pe[0]), float(pe[1]), rumbo0, Q)}))

    specs: List[Dict[str, Any]] = []
    for nombre, prot in casos:
        poses: Dict[str, List[float]] = {}
        nominales: Dict[str, Dict[str, Any]] = {}
        libres = list(ESTACIONADOS_CONF)
        for i in range(5):
            if i in prot:
                x, y, th, nom = prot[i]
                poses[str(i)] = [x, y, _envolver(th)]
                nominales[str(i)] = nom
            else:
                x, y = libres.pop(0)
                poses[str(i)] = [x, y, 0.0]
                nominales[str(i)] = {"tipo": "quieto"}
        specs.append({"bloque": "conf_guionada", "nombre": nombre, "tau": tau,
                      "formulacion": "F2", "decisiones": DECISIONES_GUIONADA,
                      "freno": "sombra", "semilla": 420100, "fase0": fase0,
                      "obst_perturbacion": [0.0, 0.0], "sin_rampa": False,
                      "disparo_m": DISPARO_CONF_M,
                      "poses_env": poses, "nominales": nominales,
                      "ruido_m": 0.0})
    return specs


def escenarios_tomas(tau: float, n: int = 10,
                     formulacion: str = "F2") -> List[Dict[str, Any]]:
    """Las 10 tomas completas, con los arranques que usaría el laboratorio."""
    from colocacion_autonoma import sortear_rumbos
    from coordinador_enjambre import SEMILLAS_LOTE
    from demo_obstaculo_movil import (arranque_obstaculo,
                                      fase_arranque_obstaculo,
                                      sortear_blancos_demo)
    return _tomas_de_semillas([SEMILLAS_LOTE[k] for k in range(n)], tau,
                              formulacion, "tomas")


def _tomas_de_semillas(semillas: List[int], tau: float, formulacion: str,
                       bloque: str) -> List[Dict[str, Any]]:
    """Tomas completas con los arranques que usaría el laboratorio."""
    from colocacion_autonoma import sortear_rumbos
    from demo_obstaculo_movil import (arranque_obstaculo,
                                      fase_arranque_obstaculo,
                                      sortear_blancos_demo)
    s: List[Dict[str, Any]] = []
    for k, semilla in enumerate(semillas):
        p0, _r = arranque_obstaculo(semilla, "L2")
        blancos = sortear_blancos_demo(5, semilla, p0)
        rumbos = sortear_rumbos(5, semilla)
        rng = np.random.default_rng([int(semilla), 77])
        pert = [float(rng.uniform(-PERTURBACION_RADIAL_M,
                                  PERTURBACION_RADIAL_M)),
                float(rng.uniform(-PERTURBACION_RUMBO_RAD,
                                  PERTURBACION_RUMBO_RAD))]
        s.append({"bloque": bloque, "nombre": f"toma_{k:02d}_s{semilla}",
                  "tau": tau, "formulacion": formulacion,
                  "decisiones": DECISIONES_TOMA, "freno": "sombra",
                  "semilla": int(semilla),
                  "fase0": fase_arranque_obstaculo(semilla),
                  "obst_perturbacion": pert, "sin_rampa": False,
                  "poses_env": {str(i): [float(blancos[i][0]),
                                         float(blancos[i][1]), float(rumbos[i])]
                                for i in range(5)},
                  "nominales": {str(i): {"tipo": "politica"} for i in range(5)},
                  "ruido_m": 0.0})
    return s


def _variantes_rampa(specs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cada spec con rampa (toma 1 de la sesión) y sin rampa (tomas 2+)."""
    out: List[Dict[str, Any]] = []
    for e in specs:
        out.append(dict(e, sin_rampa=False))
        out.append(dict(e, sin_rampa=True, nombre=f"{e['nombre']}_sinrampa"))
    return out


def construir_specs(bloques: List[str], taus: List[float]
                    ) -> List[Dict[str, Any]]:
    """Todas las specs de los bloques pedidos."""
    specs: List[Dict[str, Any]] = []
    if "conf_guionada" in bloques:
        for tau in taus:
            specs += _variantes_rampa(escenarios_confirmacion_guionados(tau))
    if "conf_tomas" in bloques:
        for tau in taus:
            specs += _variantes_rampa(_tomas_de_semillas(
                list(SEMILLAS_CONF), tau, "F2", "conf_tomas"))
    if "guionada" in bloques:
        for tau in taus:
            specs += _variantes_rampa(escenarios_guionados(tau, "F2"))
    if "tomas" in bloques:
        for tau in taus:
            specs += _variantes_rampa(escenarios_tomas(tau, formulacion="F2"))
    if "control" in bloques:
        for tau in taus:
            for e in escenarios_guionados(tau, "F0"):
                specs.append(dict(e, bloque="control"))
    if "propuesta" in bloques:
        for tau in taus:
            for e in escenarios_guionados(tau, "F1"):
                specs.append(dict(e, bloque="propuesta"))
    if "ablacion" in bloques:
        for tau in taus:
            for e in escenarios_guionados(tau, "F2"):
                specs.append(dict(e, bloque="ablacion", peso_giro=None,
                                  nombre=f"{e['nombre']}_sinpeso"))
    if "mixto" in bloques:
        # Retardo distinto para agentes y obstáculo (el 3pi tarda más en
        # arrancar despacio: 849 ms a 0.05 m/s, 458 ms a 0.15 m/s).
        for tau_ag, tau_ob in ((0.85, 0.45), (0.45, 0.85)):
            for e in escenarios_guionados(tau_ag, "F2"):
                specs.append(dict(e, bloque="mixto", tau_obstaculo=tau_ob,
                                  nombre=f"{e['nombre']}_tob{tau_ob:.2f}"))
    if "ruido" in bloques:
        for e in escenarios_guionados(0.85, "F2"):
            specs.append(dict(e, bloque="ruido", ruido_m=0.001,
                              nombre=f"{e['nombre']}_ruido1mm"))
    if "lazo_lab" in bloques:
        for e in escenarios_tomas(0.45, formulacion="F2"):
            specs.append(dict(e, bloque="lazo_lab", lazo="evaluacion"))
    return specs


# =============================================================================
# RETARDO POR ROBOT (bloque de sensibilidad "mixto")
# =============================================================================

def fallas_con_retardo_por_robot(retardos: Dict[int, float],
                                 por_defecto: float, **kw: Any) -> Any:
    """
    `FallasSimulador` con retardo de actuación DISTINTO por robot, sin tocar
    el simulador: el simulador lee `retardo_actuacion_s` al ENCOLAR cada
    orden, desde el hilo de ruedas de ese robot ("sim-ruedas-con-<id>"), y
    la física sólo pregunta si es > 0. La propiedad responde según el hilo.
    """
    from simulador_robotat import FallasSimulador

    class FallasRetardoPorRobot(FallasSimulador):
        @property                                   # type: ignore[override]
        def retardo_actuacion_s(self) -> float:
            nombre = threading.current_thread().name
            if nombre.startswith("sim-ruedas-con-"):
                rid = int(nombre.rsplit("-", 1)[1])
                return float(retardos.get(rid, por_defecto))
            return float(por_defecto)

        @retardo_actuacion_s.setter
        def retardo_actuacion_s(self, _valor: float) -> None:
            pass

    return FallasRetardoPorRobot(**kw)


# =============================================================================
# MONITOR DE VERDAD (200 Hz)
# =============================================================================

class MonitorVerdad:
    """
    Lee la pose VERDADERA del simulador a `hz` y lleva la distancia mínima
    continua entre centros: agente–obstáculo (por agente) y agente–agente.
    En el mínimo de cada agente guarda el ÁNGULO del encuentro: entre el
    rumbo del obstáculo y la dirección obstáculo→agente (0° = de frente,
    90° = de costado, 180° = por detrás). Guarda además una traza a 20 Hz.
    """

    def __init__(self, sim: Any, robots_agentes: List[int], robot_obst: int,
                 hz: float = 200.0) -> None:
        self._sim = sim
        self._ag = list(robots_agentes)
        self._ob = int(robot_obst)
        self._periodo = 1.0 / hz
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._correr, daemon=True)
        n = len(self._ag)
        self.d_min_obst: List[float] = [float("inf")] * n
        self.t_min_obst: List[float] = [float("nan")] * n
        self.angulo_min: List[float] = [float("nan")] * n
        self.d_min_pares: float = float("inf")
        self.par_min: Tuple[int, int] = (-1, -1)
        self.muestras: int = 0
        self.encuentros: List[int] = [0] * n       # entradas bajo 0.45 m
        self._cerca: List[bool] = [False] * n
        self.traza: List[Dict[str, float]] = []
        self._t0: float = 0.0

    def iniciar(self) -> None:
        self._t0 = time.perf_counter()
        self._hilo.start()

    def detener(self) -> None:
        self._parar.set()
        self._hilo.join(timeout=2.0)

    def _correr(self) -> None:
        siguiente = time.perf_counter()
        ultima_traza = -1.0
        while not self._parar.is_set():
            xo, yo, tho = self._sim.pose_de_robot(self._ob)
            po = np.array([xo, yo])
            pa = [np.array(self._sim.pose_de_robot(r)[:2]) for r in self._ag]
            t = time.perf_counter() - self._t0
            for i, p in enumerate(pa):
                d = float(np.linalg.norm(p - po))
                if d < self.d_min_obst[i]:
                    self.d_min_obst[i] = d
                    self.t_min_obst[i] = t
                    rel = math.atan2(float(p[1] - po[1]), float(p[0] - po[0]))
                    self.angulo_min[i] = abs(math.degrees(_envolver(rel - tho)))
                if not self._cerca[i] and d < 0.45:
                    self._cerca[i] = True
                    self.encuentros[i] += 1
                elif self._cerca[i] and d > 0.50:
                    self._cerca[i] = False
            for a in range(len(pa)):
                for b in range(a + 1, len(pa)):
                    d = float(np.linalg.norm(pa[a] - pa[b]))
                    if d < self.d_min_pares:
                        self.d_min_pares = d
                        self.par_min = (a, b)
            self.muestras += 1
            if t - ultima_traza >= 0.05:
                ultima_traza = t
                fila: Dict[str, float] = {"t": t, "obst_x": float(xo),
                                          "obst_y": float(yo),
                                          "obst_th": float(tho)}
                for i, p in enumerate(pa):
                    fila[f"a{i}_x"] = float(p[0])
                    fila[f"a{i}_y"] = float(p[1])
                    fila[f"d_obst_a{i}"] = float(np.linalg.norm(p - po))
                self.traza.append(fila)
            siguiente += self._periodo
            espera = siguiente - time.perf_counter()
            if espera > 0:
                time.sleep(espera)
            else:
                siguiente = time.perf_counter()

    def resumen(self) -> Dict[str, Any]:
        i_min = int(np.argmin(self.d_min_obst))
        return {
            "verdad_d_min_obst": float(min(self.d_min_obst)),
            "verdad_agente_min": i_min,
            "verdad_t_min_s": float(self.t_min_obst[i_min]),
            "verdad_angulo_min_deg": float(self.angulo_min[i_min]),
            "verdad_d_min_pares": float(self.d_min_pares),
            "verdad_par_min": f"{self.par_min[0]}-{self.par_min[1]}",
            "verdad_muestras": self.muestras,
            "verdad_hz_efectivo": self.muestras / max(
                1e-9, time.perf_counter() - self._t0),
            "encuentros_045": int(sum(self.encuentros)),
            **{f"verdad_d_min_obst_a{i}": float(v)
               for i, v in enumerate(self.d_min_obst)},
        }


# =============================================================================
# UNA CORRIDA (en su propio proceso)
# =============================================================================

def correr_una(spec: Dict[str, Any], ranura: int, carpeta: Path) -> Dict[str, Any]:
    """Una corrida completa contra un simulador propio. Escribe sus archivos."""
    import torch
    torch.set_num_threads(1)
    import config_robotat as cfg
    puerto_poses = PUERTO_POSES_BASE + SEPARACION_PUERTOS * ranura
    puerto_ruedas = PUERTO_RUEDAS_BASE + SEPARACION_PUERTOS * ranura
    cfg.activar_simulador_local(puerto_poses=puerto_poses,
                                puerto_base=puerto_ruedas)
    import demo_obstaculo_movil as demo
    from adaptadores_robotat import revisar_poses_iniciales
    from simulador_robotat import FallasSimulador, SimuladorRobotat

    n = 5
    robots = [cfg.MAPEO_AGENTES[i].id_robot for i in range(n)]
    marcadores = [cfg.MAPEO_AGENTES[i].id_marcador for i in range(n)]
    ro, mo = demo.ID_ROBOT_OBSTACULO, demo.ID_MARCADOR_OBSTACULO
    mapeo_real = {r: m for r, m in zip(robots, marcadores)}
    mapeo_real[ro] = mo
    tx, ty = cfg.TRASLACION_X_M, cfg.TRASLACION_Y_M
    poses_lab: Dict[int, Tuple[float, float, float]] = {}
    for i in range(n):
        x, y, th = spec["poses_env"][str(i)]
        poses_lab[robots[i]] = (x - tx, y - ty, th)
    fase0 = float(spec["fase0"])
    p0, rumbo0 = demo.punto_del_circulo(fase0)
    dr, dpsi = (float(v) for v in spec.get("obst_perturbacion", [0.0, 0.0]))
    p0 = p0 + dr * np.array([math.cos(fase0), math.sin(fase0)])
    poses_lab[ro] = (float(p0[0]) - tx, float(p0[1]) - ty,
                     _envolver(rumbo0 + dpsi))

    problemas = revisar_poses_iniciales(
        {i: np.array(spec["poses_env"][str(i)]) for i in range(n)}, n)

    tau = float(spec["tau"])
    tau_ob = spec.get("tau_obstaculo")
    if tau_ob is not None:
        fallas = fallas_con_retardo_por_robot(
            {ro: float(tau_ob)}, tau,
            ruido_pos_m=float(spec.get("ruido_m", 0.0)),
            semilla=int(spec["semilla"]) % 100000)
    else:
        fallas = FallasSimulador(retardo_actuacion_s=tau,
                                 ruido_pos_m=float(spec.get("ruido_m", 0.0)),
                                 semilla=int(spec["semilla"]) % 100000)
    sim = SimuladorRobotat(mapeo_real, poses_lab, fallas,
                           puerto_poses=puerto_poses, puerto_base=puerto_ruedas)
    sim.iniciar()
    t_ini = time.perf_counter()
    peso = spec.get("peso_giro", demo.PESO_GIRO_OBSTACULO)
    try:
        fuente, canal, entorno = demo.construir_con_obstaculo(n)
        supervisor = demo.SupervisorObstaculo(
            fuente, canal, modo="movil",
            freno_activo=(spec.get("freno", "sombra") == "activo"))
        coord = demo.CoordinadorConObstaculo(
            fuente, canal, entorno, n, 10, supervisor=supervisor,
            formulacion=spec["formulacion"],
            tau_prediccion_s=float(spec.get("tau_prediccion",
                                            demo.TAU_PREDICCION_S)),
            peso_giro_obstaculo=peso,
            rescate_qp=bool(spec.get("rescate", True)))
        canal.factor_operativo = FACTOR
        if spec.get("sin_rampa"):
            # Tomas 2+ de una sesión: la rampa ya se consumió (cuenta por
            # canal). Igual que `replica_con_capas.py`.
            canal.decisiones_enviadas = cfg.DECISIONES_ARRANQUE
        nominales = spec["nominales"]
        guion: Optional[NominalesGuionadas] = None
        if any(v["tipo"] != "politica" for v in nominales.values()):
            guion = NominalesGuionadas(nominales, coord,
                                       float(spec.get("disparo_m", DISPARO_M)))
            coord.instalar_nominal_forzada(guion)
        registro: List[Dict[str, Any]] = []
        estado = {"episodio": 1}
        coord._observador_paso = demo.crear_observador(coord, canal, registro,
                                                       estado)
        monitor = MonitorVerdad(sim, robots, ro)
        monitor.iniciar()
        try:
            res = demo.correr_toma(coord, canal, fuente, entorno,
                                   int(spec["semilla"]), int(spec["decisiones"]),
                                   registro, rpm_aborto=RPM_ABORTO,
                                   lazo=spec.get("lazo", "medicion"))
            # Las órdenes ya enviadas siguen ejecutándose durante τ después
            # del freno final: la verdad se mide hasta que terminan.
            time.sleep(max(tau, float(tau_ob or 0.0)) + 0.3)
        finally:
            monitor.detener()
        res.update(monitor.resumen())
        res["ticks_atrasados"] = entorno.ticks_atrasados
        res["problemas_arranque"] = "; ".join(problemas)
        res["peticiones_pose_sim"] = sim.peticiones_pose
        res["consultas_fuente"] = fuente.consultas
        res["disparos_guion"] = (";".join(f"a{i}@{p}" for i, p in
                                          sorted(guion.disparo_paso.items()))
                                 if guion is not None else "")
        trazas = list(supervisor.traza)
        entorno.finalizar()
    finally:
        sim.detener()
    for k in ("bloque", "nombre", "tau", "formulacion", "freno", "semilla",
              "fase0", "sin_rampa"):
        res[k] = spec.get(k)
    res["obst_perturbacion"] = spec.get("obst_perturbacion", [0.0, 0.0])
    res["decisiones_pedidas"] = spec["decisiones"]
    res["tau_obstaculo"] = spec.get("tau_obstaculo", "")
    res["ruido_m"] = spec.get("ruido_m", 0.0)
    res["tau_prediccion"] = (float(spec.get("tau_prediccion",
                                            demo.TAU_PREDICCION_S))
                             if spec["formulacion"] == "F2" else "")
    res["lazo_spec"] = spec.get("lazo", "medicion")
    res["duracion_total_s"] = time.perf_counter() - t_ini
    carpeta.mkdir(parents=True, exist_ok=True)
    demo.escribir_csv(carpeta / "decisiones.csv", registro)
    demo.escribir_csv(carpeta / "obstaculo.csv", trazas)
    demo.escribir_csv(carpeta / "verdad.csv", monitor.traza)
    (carpeta / "resultado.json").write_bytes(
        json.dumps(_a_json(res), indent=1, ensure_ascii=False).encode("utf-8"))
    return res


def _a_json(d: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, (np.floating,)):
            v = float(v)
        elif isinstance(v, (np.integer,)):
            v = int(v)
        elif isinstance(v, (np.bool_,)):
            v = bool(v)
        out[k] = v
    return out


# =============================================================================
# ORQUESTACIÓN
# =============================================================================

def _lanzar(spec: Dict[str, Any], ranura: int, carpeta_corrida: Path
            ) -> subprocess.Popen:
    carpeta_corrida.mkdir(parents=True, exist_ok=True)
    ruta_spec = carpeta_corrida / "spec.json"
    ruta_spec.write_bytes(json.dumps(spec, indent=1).encode("utf-8"))
    log = open(carpeta_corrida / "corrida.log", "wb")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    return subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--uno",
         str(ruta_spec), "--ranura", str(ranura)],
        cwd=str(_CARPETA), stdout=log, stderr=subprocess.STDOUT, env=env)


def _carpeta_de(carpeta: Path, k: int, spec: Dict[str, Any]) -> Path:
    return carpeta / (f"{k:03d}_{spec['bloque']}_{spec['nombre']}_"
                      f"tau{spec['tau']:.2f}_{spec['formulacion']}")


def orquestar(specs: List[Dict[str, Any]], paralelo: int, carpeta: Path,
              reanudar: bool = False) -> List[Dict[str, Any]]:
    """
    Corre las specs en `paralelo` procesos, cada uno en su ranura de puertos.

    `reanudar`: saltea las corridas que ya tienen `resultado.json` (mismo
    índice y nombre: las specs son deterministas) y renombra a
    `<carpeta>_interrumpida_<n>` las que quedaron a medias, para conservarlas
    como evidencia. (2026-10-02: el orquestador de la campaña final se cortó
    por el límite de tiempo de las tareas en segundo plano, a las 209/387.)
    """
    pendientes = list(enumerate(specs))
    if reanudar:
        quedan = []
        for k, spec in pendientes:
            c = _carpeta_de(carpeta, k, spec)
            if (c / "resultado.json").is_file():
                continue
            if c.exists():
                n = 1
                while c.with_name(f"{c.name}_interrumpida_{n}").exists():
                    n += 1
                c.rename(c.with_name(f"{c.name}_interrumpida_{n}"))
            quedan.append((k, spec))
        print(f"reanudación: {len(specs) - len(quedan)} ya hechas, "
              f"{len(quedan)} por correr", flush=True)
        pendientes = quedan
    activos: Dict[int, Tuple[subprocess.Popen, int, Dict[str, Any], Path]] = {}
    libres = list(range(paralelo))
    hechos: List[Dict[str, Any]] = []
    t0 = time.perf_counter()
    while pendientes or activos:
        while pendientes and libres:
            k, spec = pendientes.pop(0)
            ranura = libres.pop(0)
            c = _carpeta_de(carpeta, k, spec)
            activos[k] = (_lanzar(spec, ranura, c), ranura, spec, c)
        time.sleep(0.5)
        for k in list(activos):
            proc, ranura, spec, c = activos[k]
            if proc.poll() is None:
                continue
            del activos[k]
            libres.append(ranura)
            ruta = c / "resultado.json"
            if ruta.is_file():
                r = json.loads(ruta.read_text(encoding="utf-8"))
            else:
                r = {**{x: spec.get(x) for x in ("bloque", "nombre", "tau",
                                                 "formulacion")},
                     "valido": 0, "motivo": f"PROCESO FALLÓ (código "
                                            f"{proc.returncode}); ver {c.name}/corrida.log"}
            r["carpeta"] = c.name
            hechos.append(r)
            dm = r.get("verdad_d_min_obst", float("nan"))
            print(f"[{time.perf_counter() - t0:6.0f} s] {len(hechos):3d}/"
                  f"{len(specs)}  {spec['bloque']:<9} {spec['nombre']:<44} "
                  f"τ={spec['tau']:.2f} {spec['formulacion']}  d_min "
                  f"{dm if isinstance(dm, str) else f'{dm:.4f}'}  "
                  f"v {r.get('valido')}  {str(r.get('motivo', ''))[:50]}",
                  flush=True)
    return hechos


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--bloques", nargs="+", default=list(BLOQUES),
                    choices=BLOQUES)
    ap.add_argument("--taus", nargs="+", type=float, default=list(TAUS))
    ap.add_argument("--paralelo", type=int, default=6)
    ap.add_argument("--solo", nargs="*", default=None,
                    help="nombres de casos a correr (prefijo)")
    ap.add_argument("--uno", type=str, default=None)
    ap.add_argument("--ranura", type=int, default=0)
    ap.add_argument("--carpeta", type=str, default=None)
    ap.add_argument("--reanudar", action="store_true",
                    help="seguir una campaña cortada en --carpeta")
    args = ap.parse_args(argv)

    if args.uno:
        ruta = Path(args.uno)
        spec = json.loads(ruta.read_text(encoding="utf-8"))
        correr_una(spec, args.ranura, ruta.parent)
        return 0

    specs = construir_specs(args.bloques, args.taus)
    if args.solo:
        specs = [s for s in specs if any(s["nombre"].startswith(p)
                                         for p in args.solo)]
    from demo_obstaculo_movil import DIR_SALIDA_DEMO, escribir_csv
    carpeta = (Path(args.carpeta) if args.carpeta else
               DIR_SALIDA_DEMO / f"fase0_{datetime.now():%Y%m%d_%H%M%S}")
    if carpeta.exists() and any(carpeta.iterdir()) and not args.reanudar:
        print(f"✘ {carpeta} ya existe y no está vacía: no se pisa.")
        return 2
    carpeta.mkdir(parents=True, exist_ok=True)
    print(f"{len(specs)} corridas → {carpeta}  (paralelo {args.paralelo})",
          flush=True)
    orquestar(specs, args.paralelo, carpeta, reanudar=args.reanudar)
    # El resumen se arma desde TODO lo que hay en disco (también lo de antes
    # de una reanudación).
    hechos = []
    for ruta in sorted(carpeta.glob("*/resultado.json")):
        r = json.loads(ruta.read_text(encoding="utf-8"))
        r["carpeta"] = ruta.parent.name
        hechos.append(r)
    escribir_csv(carpeta / "resumen_fase0.csv", hechos)
    print(f"\nresumen: {carpeta / 'resumen_fase0.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
