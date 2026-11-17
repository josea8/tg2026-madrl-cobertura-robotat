"""
test_retroceso_congelamiento.py
===============================
Pruebas del RETROCESO por pose repetida (2026-09-24), que reemplazó a la
pausa: `retroceso_congelamiento.py`, los mandos directos y el historial del
canal (`adaptadores_robotat.CanalActuacionRobotat`) y el retardo de actuación
del simulador. Corren SIN hardware:

    python test_retroceso_congelamiento.py

Qué se prueba, en orden de importancia:
  1. contra la "zona sin captura" del simulador de verdad —fuente, canal y
     sockets reales— con 0.45 s de retardo de actuación: el robot sale del
     punto ciego y se reanuda; con la ventana LITERAL ("el tiempo que lleva
     congelada", sin retardo ni margen) se queda adentro, que es por lo que
     la ventana los lleva; y si la zona no se puede dejar, queda parado y se
     aborta dentro del tope de tiempo;
  2. el plan deshace EXACTAMENTE el camino de entrada (uniciclo, arco por
     arco), con cualquier escalado de velocidad;
  3. sin repeticiones no cambia nada: el canal nuevo manda los mismos bytes
     que el de antes del cambio (respaldo `_preRetroceso`).

El banco cinemático (`correr_banco`: tiempo virtual, sin sockets) usa el
MISMO gestor y el MISMO plan que la sesión, con un uniciclo de retardo puro
y un Motive que retiene la última pose al entrar en la zona; barre muchos
casos en milisegundos.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import math
import random
import sys
import threading
import time
import unittest
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

_CARPETA = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import config_robotat as cfg
import sesion_robotat as ses
from adaptadores_robotat import CanalActuacionRobotat, FuentePosesRobotat
from protocolo_robotat import accion_a_rpm, codificar_velocidades_rueda
from retroceso_congelamiento import (
    ESPERA_VERIFICACION_S,
    K_MIN_RETROCESO,
    MARGEN_RETROCESO_S,
    RETARDO_ACTUACION_S,
    V_RUEDA_RETROCESO,
    VENTANA_MAX_S,
    GestorRetroceso,
    Retroceso,
    plan_retroceso,
    rpm_a_v_omega,
    ventana_a_deshacer,
)
from simulador_robotat import FallasSimulador, SimuladorRobotat
from test_diagnostico_poses import ConfigAislada, puerto_libre

R: float = cfg.RADIO_RUEDA_M
L: float = cfg.MEDIO_EJE_M


def dos_puertos() -> Tuple[int, int]:
    """Dos puertos libres DISTINTOS (poses y ruedas del robot)."""
    a = puerto_libre()
    b = puerto_libre()
    while b == a:
        b = puerto_libre()
    return a, b


def rpm(v: float, w: float) -> Tuple[float, float]:
    """(rpm_izq, rpm_der) de (v, ω), sin saturar (los casos no saturan)."""
    izq, der, _sat = accion_a_rpm(v, w, R, L)
    return izq, der


def integrar_arco(x: float, y: float, th: float, v: float, w: float,
                  dt: float) -> Tuple[float, float, float]:
    """Pose tras `dt` s a (v, ω) constantes: integración EXACTA del uniciclo."""
    if abs(w) < 1e-12:
        return x + v * dt * math.cos(th), y + v * dt * math.sin(th), th
    th2 = th + w * dt
    return (x + (v / w) * (math.sin(th2) - math.sin(th)),
            y - (v / w) * (math.cos(th2) - math.cos(th)), th2)


def recorrer(pose: Tuple[float, float, float],
             tramos: List[Tuple[float, float, float]]
             ) -> Tuple[float, float, float]:
    """Aplica tramos (rpm_izq, rpm_der, duración) a una pose."""
    x, y, th = pose
    for izq, der, dur in tramos:
        v, w = rpm_a_v_omega(izq, der, R, L)
        x, y, th = integrar_arco(x, y, th, v, w, dur)
    return x, y, th


# =============================================================================
# BANCO CINEMÁTICO (tiempo virtual)
# =============================================================================

class RobotRetardoPuro:
    """
    Uniciclo cuyas ruedas ejecutan cada orden `retardo_s` después de
    recibida. `arranque_extra_s` > 0 modela la fricción de arranque: cuando
    una orden arranca de quieto o invierte el sentido de marcha, el robot no
    se mueve durante ese tiempo extra (29-08: a 0.05 m/s el arranque tardó
    849 ms, contra 458 ms a 0.15 m/s).
    """

    def __init__(self, x: float, y: float, th: float,
                 retardo_s: float = 0.45, arranque_extra_s: float = 0.0) -> None:
        self.x, self.y, self.th = x, y, th
        self.retardo_s = float(retardo_s)
        self.arranque_extra_s = float(arranque_extra_s)
        self._cola: Deque[Tuple[float, float, float]] = deque()
        self._izq = self._der = 0.0
        self._signo = 0
        self._quieto_hasta = -math.inf

    def recibir(self, t: float, izq: float, der: float) -> None:
        self._cola.append((t + self.retardo_s, float(izq), float(der)))

    def avanzar(self, t0: float, t1: float) -> None:
        """Integra de `t0` a `t1`, aplicando las órdenes que vencen adentro."""
        t = t0
        while t < t1 - 1e-12:
            prox = t1
            if self._cola and self._cola[0][0] < prox:
                prox = max(t, self._cola[0][0])
            if t < self._quieto_hasta < prox:
                prox = self._quieto_hasta
            if t < self._quieto_hasta:
                v = w = 0.0
            else:
                v, w = rpm_a_v_omega(self._izq, self._der, R, L)
            self.x, self.y, self.th = integrar_arco(self.x, self.y, self.th,
                                                    v, w, prox - t)
            t = prox
            while self._cola and self._cola[0][0] <= t + 1e-12:
                _t, izq, der = self._cola.popleft()
                v_nueva, _w = rpm_a_v_omega(izq, der, R, L)
                signo = (v_nueva > 1e-9) - (v_nueva < -1e-9)
                if (self.arranque_extra_s > 0.0 and signo != 0
                        and signo != self._signo):
                    self._quieto_hasta = t + self.arranque_extra_s
                self._signo = signo
                self._izq, self._der = izq, der


class CanalVirtual:
    """
    Lo que el gestor usa del canal real, sobre un reloj virtual: la decisión
    manda la acción de la política SALVO que haya mando directo, y todo lo
    que se manda queda en el historial.
    """

    def __init__(self, robot: RobotRetardoPuro,
                 reloj: Callable[[], float]) -> None:
        self._robot = robot
        self._reloj = reloj
        self.mandos_directos: Dict[int, Tuple[float, float]] = {}
        self._historial: Dict[int, List[Tuple[float, float, float]]] = {}
        self.envios: List[Tuple[float, float, float]] = []

    def enviar(self, i: int, izq: float, der: float) -> None:
        mando = self.mandos_directos.get(i)
        if mando is not None:
            izq, der = mando
        self._enviar(i, izq, der)

    def _enviar(self, i: int, izq: float, der: float) -> None:
        t = self._reloj()
        self._historial.setdefault(i, []).append((t, float(izq), float(der)))
        self.envios.append((t, float(izq), float(der)))
        self._robot.recibir(t, izq, der)

    def historial_mandos(self, i: int) -> List[Tuple[float, float, float]]:
        return list(self._historial.get(i, []))

    def fijar_mando(self, i: int, izq: float, der: float,
                    enviar_ya: bool = True) -> None:
        self.mandos_directos[i] = (float(izq), float(der))
        if enviar_ya:
            self._enviar(i, izq, der)

    def liberar_mando(self, i: int) -> None:
        self.mandos_directos.pop(i, None)


@dataclass
class ResultadoBanco:
    """Lo que pasó en una corrida del banco."""

    evento_final: str            # "recuperada" · "sigue_congelada" · "sin_evento"
    t_deteccion: float
    t_final: float
    penetracion_max_m: float     # lo más adentro de la zona que llegó
    x_final_m: float             # < 0: afuera de la zona (x ≥ 0 no se ve)
    retroceso: Optional[Retroceso]


def correr_banco(v: float, w: float = 0.0, angulo_deg: float = 0.0,
                 fase: float = 0.0, retardo_robot_s: float = 0.45,
                 arranque_extra_s: float = 0.0,
                 gestor_kw: Optional[Dict[str, Any]] = None,
                 hz_motive: float = 120.0, t_max_s: float = 8.0,
                 semilla: int = 0) -> ResultadoBanco:
    """
    Un robot entra con (v, ω) constantes en el semiplano x ≥ 0, que la
    captura no ve: ahí Motive RETIENE la última pose registrada. Decisiones a
    10 Hz, cada consulta 5 ms antes de su decisión (como la fuente real, en
    el último tick). `fase` ∈ [0, 1) corre el cruce del borde dentro del
    período. Los cuadros de Motive traen ~10 µm de ruido, así que una pose
    VIVA nunca se repite y una retenida se repite bit a bit.
    """
    periodo = 0.1
    preroll = retardo_robot_s + arranque_extra_s + 0.3
    th0 = math.radians(angulo_deg)
    izq_pol, der_pol = rpm(v, w)
    t_cruce = 0.5 + fase * periodo

    # Dónde arrancar para cruzar x = 0 en `t_cruce`: el mismo recorrido sin
    # zona, desde x = 0 (la dinámica no depende de x).
    prueba = RobotRetardoPuro(0.0, 0.0, th0, retardo_robot_s, arranque_extra_s)
    prueba.recibir(-preroll, izq_pol, der_pol)
    prueba.avanzar(-preroll, t_cruce)
    x0 = -prueba.x

    reloj = [-preroll]
    robot = RobotRetardoPuro(x0, 0.0, th0, retardo_robot_s, arranque_extra_s)
    canal = CanalVirtual(robot, lambda: reloj[0])
    gestor = GestorRetroceso(canal, periodo_s=periodo, radio=R, medio_eje=L,
                             **(gestor_kw or {}))
    det = ses.DetectorCongelamiento(activo=True)
    rng = random.Random(semilla)
    canal.enviar(0, izq_pol, der_pol)

    def cuadro() -> Tuple[float, float, float]:
        return (robot.x + rng.gauss(0.0, 1e-5), robot.y + rng.gauss(0.0, 1e-5),
                robot.th + rng.gauss(0.0, 2e-4))

    retenida = cuadro()
    t = -preroll
    t_cuadro = t
    penetracion = 0.0
    politica = (izq_pol, der_pol)
    t_det = math.nan
    paso = 0

    def avanzar_hasta(t_obj: float) -> None:
        nonlocal t, t_cuadro, retenida, penetracion
        while t < t_obj - 1e-12:
            prox = min(t_obj, t_cuadro + 1.0 / hz_motive)
            robot.avanzar(t, prox)
            t = prox
            reloj[0] = t
            penetracion = max(penetracion, robot.x)
            if t >= t_cuadro + 1.0 / hz_motive - 1e-12:
                t_cuadro = t
                if robot.x < 0.0:          # visible: Motive registra
                    retenida = cuadro()

    evento_final = "sin_evento"
    while t < t_max_s:
        t_dec = paso * periodo
        avanzar_hasta(t_dec - 0.005)
        consulta = retenida
        avanzar_hasta(t_dec)
        canal.enviar(0, *politica)
        det.observar(0, consulta)
        ev = gestor.observar(0, det.repeticiones(0), t_dec, paso, consulta,
                             -robot.x)
        paso += 1
        if ev == "inicio":
            t_det = t_dec
        if ev in ("recuperada", "sigue_congelada"):
            evento_final = ev
            break
    t_final = t
    # La política frena (o el mando directo ya está en (0, 0)) y se deja
    # terminar lo que estaba en camino.
    politica = (0.0, 0.0)
    canal.enviar(0, *politica)
    avanzar_hasta(t + retardo_robot_s + arranque_extra_s + 0.3)
    return ResultadoBanco(evento_final, t_det, t_final, penetracion, robot.x,
                          gestor.terminados[-1] if gestor.terminados else None)


# =============================================================================
# 1. FUNCIONES PURAS
# =============================================================================

class PruebaFuncionesPuras(unittest.TestCase):

    def test_rpm_a_v_omega_es_la_inversa_de_accion_a_rpm(self) -> None:
        for v, w in [(0.124, 0.0), (0.0, 2.51), (-0.07, 0.8), (0.05, -1.3)]:
            izq, der = rpm(v, w)
            v2, w2 = rpm_a_v_omega(izq, der, R, L)
            self.assertAlmostEqual(v2, v, places=12)
            self.assertAlmostEqual(w2, w, places=12)

    def test_ventana_a_deshacer(self) -> None:
        # Primera repetición a 10 Hz: la última consulta distinta fue hace
        # 0.2 s → 0.2 + 0.45. El margen no va acá: es tiempo de retroceso.
        self.assertAlmostEqual(ventana_a_deshacer(10.0, 9.8), 0.65)
        self.assertAlmostEqual(ventana_a_deshacer(10.0, 9.8, retardo_s=0.0),
                               0.2)
        # Con tope, y sin referencia → el tope.
        self.assertEqual(ventana_a_deshacer(10.0, 9.0), VENTANA_MAX_S)
        self.assertEqual(ventana_a_deshacer(10.0, None), VENTANA_MAX_S)
        # Un reloj que retrocede no da ventanas negativas.
        self.assertAlmostEqual(ventana_a_deshacer(10.0, 10.5),
                               RETARDO_ACTUACION_S)


# =============================================================================
# 2. EL PLAN
# =============================================================================

class PruebaPlanRetroceso(unittest.TestCase):

    def _historial_al_azar(self, semilla: int, n: int = 12
                           ) -> Tuple[List[Tuple[float, float, float]], float]:
        rng = random.Random(semilla)
        t = 100.0
        hist = []
        for _ in range(n):
            v = rng.uniform(-0.05, 0.124)
            w = rng.uniform(-2.5, 2.5)
            hist.append((t, *rpm(v, w)))
            t += rng.uniform(0.02, 0.15)
        return hist, t

    def test_deshace_exactamente_el_camino_de_entrada(self) -> None:
        """
        La propiedad de la que depende todo: aplicar el plan desde donde
        terminó el robot lo devuelve adonde estaba al empezar la ventana,
        con la velocidad original (k = 1) y con el escalado por tramo.
        """
        for semilla in range(20):
            hist, t_fin = self._historial_al_azar(semilla)
            directos = [(izq, der, (hist[j + 1][0] if j + 1 < len(hist)
                                     else t_fin) - t)
                        for j, (t, izq, der) in enumerate(hist)]
            inicio = (0.3, -0.2, 0.7)
            fin = recorrer(inicio, directos)
            for kw in ({"k_min": 1.0, "v_rueda": 0.0}, {}):
                with self.subTest(semilla=semilla, kw=kw):
                    plan = plan_retroceso(hist, t_fin, t_fin - hist[0][0],
                                          margen_s=0.0, radio=R, medio_eje=L,
                                          **kw)
                    vuelta = recorrer(fin, [(p.rpm_izq, p.rpm_der,
                                             p.duracion_s)
                                            for p in plan.tramos])
                    for a, b in zip(vuelta, inicio):
                        self.assertAlmostEqual(a, b, places=9)

    def test_el_margen_sigue_por_el_camino_anterior(self) -> None:
        """
        Con k = 1, un margen de m segundos de retroceso deshace además las
        órdenes de [t0 − m, t0]: el robot vuelve adonde estaba en t0 − m,
        por el camino que hizo.
        """
        hist, t_fin = self._historial_al_azar(3, n=20)
        ventana, margen = 0.5, 0.3
        t_obj = t_fin - ventana - margen
        self.assertGreater(t_obj, hist[0][0])

        def pose_en(t_corte: float) -> Tuple[float, float, float]:
            tramos = []
            for j, (t, izq, der) in enumerate(hist):
                t_sig = hist[j + 1][0] if j + 1 < len(hist) else t_fin
                fin = min(t_sig, t_corte)
                if fin > t:
                    tramos.append((izq, der, fin - t))
            return recorrer((0.3, -0.2, 0.7), tramos)

        plan = plan_retroceso(hist, t_fin, ventana, margen_s=margen,
                              k_min=1.0, v_rueda=0.0, radio=R, medio_eje=L)
        self.assertAlmostEqual(plan.margen_s, margen)
        self.assertAlmostEqual(plan.duracion_s, ventana + margen)
        vuelta = recorrer(pose_en(t_fin), [(p.rpm_izq, p.rpm_der,
                                            p.duracion_s)
                                           for p in plan.tramos])
        for a, b in zip(vuelta, pose_en(t_obj)):
            self.assertAlmostEqual(a, b, places=9)

    def test_el_margen_es_tiempo_de_retroceso(self) -> None:
        """
        A 0.124 m/s constantes: la ventana se deshace a 0.07 m/s y el margen
        suma 0.4 s MÁS de retroceso, 2.8 cm; si el historial no llega tan
        atrás, el margen queda corto y el plan lo dice.
        """
        hist = [(9.0 + 0.1 * j, *rpm(0.124, 0.0)) for j in range(11)]
        plan = plan_retroceso(hist, 10.0, 0.65, radio=R, medio_eje=L)
        k = V_RUEDA_RETROCESO / 0.124
        self.assertAlmostEqual(plan.duracion_s, 0.65 / k + MARGEN_RETROCESO_S)
        self.assertAlmostEqual(plan.camino_m, 0.65 * 0.124
                               + MARGEN_RETROCESO_S * V_RUEDA_RETROCESO)
        self.assertAlmostEqual(plan.margen_s, MARGEN_RETROCESO_S)
        corto = plan_retroceso(hist[-8:], 10.0, 0.65, radio=R, medio_eje=L)
        self.assertAlmostEqual(corto.margen_s, 0.05 / k)     # 9.3 → 9.35

    def test_la_ventana_recorta_la_orden_que_estaba_vigente(self) -> None:
        hist = [(0.0, *rpm(0.1, 0.0)), (1.0, *rpm(0.05, 0.0))]
        plan = plan_retroceso(hist, 1.3, 0.5, margen_s=0.0, k_min=1.0,
                              v_rueda=0.0, radio=R, medio_eje=L)
        # 0.3 s de la segunda orden (la más nueva, primero) y 0.2 s de la
        # primera, al revés.
        self.assertEqual(len(plan.tramos), 2)
        self.assertAlmostEqual(plan.tramos[0].duracion_s, 0.3)
        self.assertAlmostEqual(plan.tramos[1].duracion_s, 0.2)
        self.assertAlmostEqual(rpm_a_v_omega(plan.tramos[0].rpm_izq,
                                             plan.tramos[0].rpm_der)[0], -0.05)
        self.assertAlmostEqual(rpm_a_v_omega(plan.tramos[1].rpm_izq,
                                             plan.tramos[1].rpm_der)[0], -0.1)
        self.assertAlmostEqual(plan.camino_m, 0.3 * 0.05 + 0.2 * 0.1)

    def test_velocidad_del_retroceso(self) -> None:
        """
        Rueda más rápida a 0.07 m/s, sin bajar nunca de la mitad de la
        entrada. Una entrada más lenta —la rampa de arranque va a
        ≤ 0.031 m/s— se deshace a 0.07: en reversa y desde quieto, más
        despacio el 3pi puede no arrancar.
        """
        casos = [  # (v, ω) de entrada → k esperado
            ((0.124, 0.0), V_RUEDA_RETROCESO / 0.124),
            ((0.031, 0.0), V_RUEDA_RETROCESO / 0.031),   # rampa: más rápido
            ((0.30, 0.0), K_MIN_RETROCESO),     # muy rápido: la mitad
            ((0.0, 2.51), V_RUEDA_RETROCESO / (2.51 * L)),
            ((0.124, 2.51), K_MIN_RETROCESO),   # rueda a 0.244 → la mitad
        ]
        for (v, w), k in casos:
            with self.subTest(v=v, w=w):
                plan = plan_retroceso([(0.0, *rpm(v, w))], 0.2, 0.2,
                                      margen_s=0.0, radio=R, medio_eje=L)
                (tramo,) = plan.tramos
                v2, w2 = rpm_a_v_omega(tramo.rpm_izq, tramo.rpm_der, R, L)
                self.assertAlmostEqual(v2, -k * v, places=9)
                self.assertAlmostEqual(w2, -k * w, places=9)
                self.assertAlmostEqual(tramo.duracion_s, 0.2 / k, places=9)

    def test_los_tramos_quietos_no_se_repiten(self) -> None:
        """
        Esperar al revés no deshace camino y obliga a otro arranque: una
        parada no entra al plan, ni en la ventana ni en el margen.
        """
        hist = [(0.0, *rpm(0.1, 0.0)), (0.5, 0.0, 0.0),
                (0.8, *rpm(0.124, 0.0))]
        plan = plan_retroceso(hist, 1.0, 0.5, margen_s=0.1,
                              radio=R, medio_eje=L)
        # Ventana [0.5, 1.0]: 0.2 s a 0.124 y 0.3 s quieto (fuera); margen:
        # 0.1 s de retroceso con la orden de 0.1 m/s, anterior a la parada.
        self.assertEqual(len(plan.tramos), 2)
        for tramo in plan.tramos:
            v, _w = rpm_a_v_omega(tramo.rpm_izq, tramo.rpm_der, R, L)
            self.assertAlmostEqual(v, -V_RUEDA_RETROCESO)
        self.assertAlmostEqual(plan.tramos[0].duracion_s,
                               0.2 * 0.124 / V_RUEDA_RETROCESO)
        self.assertAlmostEqual(plan.tramos[1].duracion_s, 0.1)
        self.assertAlmostEqual(plan.margen_s, 0.1)

    def test_una_rueda_quieta_queda_en_cero_positivo(self) -> None:
        """Giro sobre una rueda: la quieta sale 0.0, no −0.0."""
        plan = plan_retroceso([(0.0, *rpm(L * 1.0, 1.0))], 0.2, 0.2,
                              margen_s=0.0, radio=R, medio_eje=L)
        (tramo,) = plan.tramos
        self.assertEqual(tramo.rpm_izq, 0.0)
        self.assertFalse(math.copysign(1.0, tramo.rpm_izq) < 0)

    def test_mando_en(self) -> None:
        plan = plan_retroceso([(0.0, *rpm(0.1, 0.0)), (0.1, *rpm(0.05, 0.0))],
                              0.2, 0.2, margen_s=0.0, k_min=1.0, v_rueda=0.0,
                              radio=R, medio_eje=L)
        self.assertEqual(plan.mando_en(0.05), (plan.tramos[0].rpm_izq,
                                               plan.tramos[0].rpm_der))
        self.assertEqual(plan.mando_en(0.15), (plan.tramos[1].rpm_izq,
                                               plan.tramos[1].rpm_der))
        self.assertIsNone(plan.mando_en(0.2))
        self.assertAlmostEqual(plan.duracion_s, 0.2)

    def test_sin_historial_el_plan_es_vacio(self) -> None:
        plan = plan_retroceso([], 5.0, 0.85, radio=R, medio_eje=L)
        self.assertEqual(plan.tramos, [])
        self.assertIsNone(plan.mando_en(0.0))


# =============================================================================
# 3. EL GESTOR, CON TIEMPOS A MANO
# =============================================================================

class CanalQueAnota:
    """Canal falso: guarda los mandos directos y un historial fijo."""

    def __init__(self, historial: List[Tuple[float, float, float]]) -> None:
        self._hist = historial
        self.fijados: List[Tuple[int, float, float]] = []
        self.liberados: List[int] = []

    def historial_mandos(self, i: int) -> List[Tuple[float, float, float]]:
        return list(self._hist)

    def fijar_mando(self, i: int, izq: float, der: float,
                    enviar_ya: bool = True) -> None:
        self.fijados.append((i, izq, der))

    def liberar_mando(self, i: int) -> None:
        self.liberados.append(i)


class PruebaGestorRetroceso(unittest.TestCase):

    def _gestor(self, **kw: Any) -> Tuple[GestorRetroceso, CanalQueAnota]:
        # 1 s de marcha recta a 0.124 m/s, una orden cada 0.1 s.
        hist = [(9.0 + 0.1 * j, *rpm(0.124, 0.0)) for j in range(11)]
        canal = CanalQueAnota(hist)
        return GestorRetroceso(canal, periodo_s=0.1, radio=R, medio_eje=L,
                               **kw), canal

    def _hasta_la_deteccion(self, g: GestorRetroceso) -> str:
        """Consultas en 9.8 (pose A), 9.9 (B) y 10.0 (B otra vez)."""
        self.assertEqual(g.observar(0, 0, 9.8, 0, (1, 1, 0), 0.3), "")
        self.assertEqual(g.observar(0, 0, 9.9, 1, (1, 2, 0), 0.3), "")
        return g.observar(0, 1, 10.0, 2, (1, 2, 0), 0.3)

    def test_empieza_en_la_primera_repeticion_con_la_ventana_correcta(
            self) -> None:
        g, canal = self._gestor()
        self.assertEqual(self._hasta_la_deteccion(g), "inicio")
        r = g.activos[0]
        # La última consulta con pose DISTINTA fue la de 9.8: 0.2 + 0.45, y
        # 0.4 s más de retroceso a 0.07 m/s por el camino anterior.
        self.assertAlmostEqual(r.plan.ventana_s, 0.65)
        self.assertAlmostEqual(r.plan.margen_s, MARGEN_RETROCESO_S)
        self.assertAlmostEqual(r.plan.camino_m, 0.65 * 0.124
                               + MARGEN_RETROCESO_S * V_RUEDA_RETROCESO,
                               places=9)
        # Mandó en el acto, marcha atrás, a 0.07 m/s.
        (_i, izq, der), = canal.fijados
        v, w = rpm_a_v_omega(izq, der, R, L)
        self.assertAlmostEqual(v, -V_RUEDA_RETROCESO, places=9)
        self.assertAlmostEqual(w, 0.0, places=9)
        self.assertEqual(g.en_retroceso, {0})

    def test_se_reanuda_cuando_la_pose_vuelve_a_cambiar(self) -> None:
        g, canal = self._gestor()
        self._hasta_la_deteccion(g)
        self.assertEqual(g.observar(0, 2, 10.1, 3, (1, 2, 0), 0.3), "sigue")
        self.assertEqual(g.observar(0, 0, 10.2, 4, (1, 1.9, 0), 0.3),
                         "recuperada")
        self.assertEqual(canal.liberados, [0])
        self.assertEqual(g.en_retroceso, set())
        (r,) = g.terminados
        self.assertEqual((r.resultado, r.paso_inicio, r.paso_fin),
                         ("recuperada", 2, 4))
        self.assertAlmostEqual(r.duracion_s, 0.2)
        self.assertIn("recuperada", r.como_texto())

    def test_si_no_vuelve_para_y_declara_el_fallo_en_el_tope(self) -> None:
        g, canal = self._gestor()
        self._hasta_la_deteccion(g)
        r = g.activos[0]
        tope = r.plan.duracion_s + ESPERA_VERIFICACION_S
        t, paso, eventos = 10.0, 3, []
        while True:
            t += 0.1
            ev = g.observar(0, 2, t, paso, (1, 2, 0), 0.3)
            eventos.append(ev)
            paso += 1
            if ev == "sigue_congelada":
                break
            self.assertLess(t - 10.0, tope + 0.2)
        self.assertGreaterEqual(t - 10.0, tope - 1e-9)
        self.assertIn("verificando", eventos)
        # Lo último que se le mandó es (0, 0), y queda así.
        self.assertEqual(canal.fijados[-1][1:], (0.0, 0.0))
        self.assertEqual(g.terminados[-1].resultado, "sigue_congelada")
        # El plan se siguió en el tiempo: marcha atrás mientras duró.
        atras = [f for f in canal.fijados
                 if rpm_a_v_omega(f[1], f[2], R, L)[0] < -1e-6]
        self.assertGreaterEqual(len(atras), int(r.plan.duracion_s / 0.1) - 1)

    def test_sin_repeticiones_no_toca_el_canal(self) -> None:
        g, canal = self._gestor()
        for j in range(50):
            self.assertEqual(g.observar(0, 0, 10.0 + 0.1 * j, j,
                                        (1, 1 + 0.01 * j, 0), 0.3), "")
        self.assertEqual((canal.fijados, canal.liberados), ([], []))

    def test_cerrar_todos(self) -> None:
        g, _canal = self._gestor()
        self._hasta_la_deteccion(g)
        g.cerrar_todos(9, 10.5, "fin_del_episodio")
        self.assertEqual(g.en_retroceso, set())
        self.assertEqual(g.terminados[-1].resultado, "fin_del_episodio")


# =============================================================================
# 4. BANCO CINEMÁTICO: MUCHOS CASOS, EL MISMO CÓDIGO
# =============================================================================

class PruebaBancoCinematico(unittest.TestCase):
    """
    Uniciclo con 0.45 s de retardo puro y un Motive que retiene la última
    pose en la zona. Con los parámetros propuestos, sale SIEMPRE; con la
    ventana literal, no.
    """

    ENTRADAS = [(0.0, 0.0), (30.0, 0.0), (60.0, 0.0), (0.0, 0.8),
                (0.0, -0.8)]

    def test_con_los_parametros_propuestos_siempre_sale(self) -> None:
        # 0.031: la rampa de arranque seguro a factor 0.40; 0.124: el tope.
        for v in (0.031, 0.07, 0.10, 0.124):
            for ang, w in self.ENTRADAS:
                for fase in (0.0, 0.25, 0.5, 0.75):
                    with self.subTest(v=v, ang=ang, w=w, fase=fase):
                        res = correr_banco(v, w, ang, fase)
                        self.assertEqual(res.evento_final, "recuperada")
                        self.assertLess(res.x_final_m, 0.0)   # afuera
                        r = res.retroceso
                        self.assertLessEqual(
                            res.t_final - res.t_deteccion,
                            r.plan.duracion_s + ESPERA_VERIFICACION_S + 1e-9)
                        self.assertLessEqual(r.plan.ventana_s,
                                             VENTANA_MAX_S + 1e-12)

    def test_con_la_ventana_literal_se_queda_adentro(self) -> None:
        """
        "El tiempo que lleva congelada", sin retardo ni margen: deshace
        0.2 s de un camino de ~0.6 s. Es el control negativo del término de
        retardo.
        """
        for fase in (0.0, 0.25, 0.5, 0.75):
            with self.subTest(fase=fase):
                res = correr_banco(0.124, fase=fase,
                                   gestor_kw={"retardo_s": 0.0,
                                              "margen_s": 0.0})
                self.assertEqual(res.evento_final, "sigue_congelada")
                self.assertGreater(res.x_final_m, 0.02)   # >2 cm adentro


# =============================================================================
# 5. EL CANAL: MANDOS DIRECTOS E HISTORIAL
# =============================================================================

class SocketQueAnota:
    """Socket falso: acumula lo que se le manda."""

    def __init__(self) -> None:
        self.datos = bytearray()

    def sendall(self, b: bytes) -> None:
        self.datos += b

    def close(self) -> None:
        pass


class FuenteGuionada:
    """`agentes_vencidos` con una lista por llamada (vacía al agotarse)."""

    def __init__(self, guion: Optional[List[List[int]]] = None) -> None:
        self._guion = list(guion or [])

    def agentes_vencidos(self) -> List[int]:
        return self._guion.pop(0) if self._guion else []


def _canal_falso(modulo: Any, n: int, fuente: Any) -> Any:
    canal = modulo.CanalActuacionRobotat(n, fuente)
    canal._socks = {i: SocketQueAnota() for i in range(n)}
    return canal


class PruebaCanalMandosDirectos(unittest.TestCase):

    def setUp(self) -> None:
        self._mapeo = cfg.MAPEO_AGENTES
        cfg.MAPEO_AGENTES = {i: cfg.AsignacionAgente(id_marcador=i + 1,
                                                     id_robot=i + 1)
                             for i in range(3)}

    def tearDown(self) -> None:
        cfg.MAPEO_AGENTES = self._mapeo

    def test_sin_mandos_manda_los_mismos_bytes_que_antes_del_cambio(
            self) -> None:
        """
        El reemplazo de la pausa no puede cambiar NADA cuando no hay pose
        repetida: misma secuencia de órdenes —rampa de arranque, factor,
        poses vencidas, colocación, detención— al canal de antes
        (`adaptadores_robotat_respaldo_20260924_preRetroceso.py`) y al de
        ahora, mismos bytes en cada robot.
        """
        ruta = _CARPETA / "adaptadores_robotat_respaldo_20260924_preRetroceso.py"
        if not ruta.exists():
            self.skipTest(f"falta el respaldo {ruta.name}: no hay contra qué "
                          f"comparar")
        spec = importlib.util.spec_from_file_location("_adaptadores_pre", ruta)
        previo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(previo)
        import adaptadores_robotat as actual

        rng = random.Random(7)
        acciones = [{i: (rng.uniform(-0.1, 0.31), rng.uniform(-6.3, 6.3))
                     for i in range(3)} for _ in range(120)]
        vencidos = [[] for _ in range(120)]
        vencidos[60] = [1]
        vencidos[61] = [0, 2]
        salidas = []
        for modulo in (previo, actual):
            canal = _canal_falso(modulo, 3, FuenteGuionada(vencidos))
            with contextlib.redirect_stdout(io.StringIO()):
                for j, acc in enumerate(acciones):
                    canal.factor_operativo = 0.40 if j < 80 else 1.0
                    canal.enviar_acciones(acc)
                    if j == 90:
                        canal.enviar_directo({0: (0.05, 0.3), 2: (0.0, -1.0)})
                canal.detener_todo()
            salidas.append([bytes(canal._socks[i].datos) for i in range(3)])
        self.assertEqual(salidas[0], salidas[1])
        self.assertEqual(len(salidas[1][0]), 11 * (120 + 1 + 1))

    def test_el_mando_directo_reemplaza_a_la_accion_sin_factor(self) -> None:
        canal = _canal_falso(sys.modules["adaptadores_robotat"], 3,
                             FuenteGuionada())
        canal.factor_operativo = 0.40
        canal.decisiones_enviadas = cfg.DECISIONES_ARRANQUE      # sin rampa
        izq, der = rpm(-0.07, 0.0)
        with contextlib.redirect_stdout(io.StringIO()):
            canal.fijar_mando(1, izq, der)                        # en el acto
            canal.enviar_acciones({i: (0.3, 0.0) for i in range(3)})
            canal.liberar_mando(1)
            canal.enviar_acciones({i: (0.3, 0.0) for i in range(3)})
        esperado_mando = codificar_velocidades_rueda(izq, der)
        politica = codificar_velocidades_rueda(*rpm(0.3 * 0.40, 0.0))
        self.assertEqual(bytes(canal._socks[1].datos),
                         esperado_mando + esperado_mando + politica)
        self.assertEqual(bytes(canal._socks[0].datos), politica + politica)
        self.assertEqual(canal.decisiones_con_mando_directo, {1: 1})
        # El historial tiene lo que salió, en orden y con su instante.
        hist = canal.historial_mandos(1)
        self.assertEqual([h[1:] for h in hist],
                         [(izq, der), (izq, der), rpm(0.3 * 0.40, 0.0)])
        self.assertTrue(all(a[0] <= b[0] for a, b in zip(hist, hist[1:])))
        canal.olvidar_historial()
        self.assertEqual(canal.historial_mandos(1), [])

    def test_la_pose_vencida_manda_sobre_el_mando_directo(self) -> None:
        canal = _canal_falso(sys.modules["adaptadores_robotat"], 3,
                             FuenteGuionada([[1], [1]]))
        canal.decisiones_enviadas = cfg.DECISIONES_ARRANQUE
        with contextlib.redirect_stdout(io.StringIO()):
            canal.fijar_mando(1, *rpm(-0.07, 0.0))    # vencido → (0, 0)
            canal.enviar_acciones({i: (0.1, 0.0) for i in range(3)})
        cero = codificar_velocidades_rueda(0.0, 0.0)
        self.assertEqual(bytes(canal._socks[1].datos), cero + cero)

    def test_el_mando_se_recorta_al_tope_de_rpm(self) -> None:
        canal = _canal_falso(sys.modules["adaptadores_robotat"], 3,
                             FuenteGuionada())
        canal.fijar_mando(0, 10 * cfg.RPM_MAX, -10 * cfg.RPM_MAX)
        self.assertEqual(canal.mandos_directos[0],
                         (cfg.RPM_MAX, -cfg.RPM_MAX))


# =============================================================================
# 6. EL SIMULADOR: RETARDO DE ACTUACIÓN
# =============================================================================

class PruebaSimuladorRetardo(unittest.TestCase):

    def test_la_orden_llega_a_las_ruedas_tarde(self) -> None:
        with ConfigAislada():
            p_poses, p_rueda = dos_puertos()
            fallas = FallasSimulador(retardo_actuacion_s=0.3)
            sim = SimuladorRobotat({1: 1}, {1: (0.0, 0.5, 0.0)}, fallas,
                                   puerto_poses=p_poses,
                                   puerto_base=p_rueda - 1)
            with sim, contextlib.redirect_stdout(io.StringIO()):
                import socket as _s
                with _s.create_connection(("127.0.0.1", p_rueda),
                                          timeout=1.0) as con:
                    con.sendall(codificar_velocidades_rueda(*rpm(0.1, 0.0)))
                    time.sleep(0.15)
                    self.assertAlmostEqual(sim.pose_de_robot(1)[0], 0.0,
                                           places=9)
                    self.assertEqual(sim.rpm_en_ruedas(1), (0.0, 0.0))
                    self.assertNotEqual(sim.rpm_de_robot(1), (0.0, 0.0))
                    time.sleep(0.4)
                    self.assertGreater(sim.pose_de_robot(1)[0], 0.005)


# =============================================================================
# 7. CONTRA LA "ZONA SIN CAPTURA" DEL SIMULADOR, CON SOCKETS REALES
# =============================================================================

class PruebaContraElSimulador(unittest.TestCase):
    """
    Fuente, canal y simulador de verdad, con 0.45 s de retardo de actuación
    y un semiplano x ≥ 0 (marco del laboratorio) que la captura no ve: ahí
    el simulador devuelve la última pose publicada, como Motive. Un robot
    va derecho hacia el borde a 0.124 m/s (el tope del régimen del
    laboratorio, factor 0.40); el lazo es el de la sesión en miniatura:
    consulta, envío, detector y gestor, a 10 Hz.
    """

    ROBOT = 1
    MARCADOR = 1

    def setUp(self) -> None:
        self._cfg = ConfigAislada()
        self._cfg.__enter__()
        p_poses, p_rueda = dos_puertos()
        cfg.activar_simulador_local(puerto_poses=p_poses,
                                    puerto_base=p_rueda - self.ROBOT)
        cfg.MAPEO_AGENTES = {0: cfg.AsignacionAgente(
            id_marcador=self.MARCADOR, id_robot=self.ROBOT)}
        cfg.ESCALA_POSICION = 1.0
        cfg.ROTACION_MARCO_RAD = 0.0
        cfg.TRASLACION_X_M = 1.5
        cfg.TRASLACION_Y_M = 1.5
        cfg.OFFSET_HEADING_RAD = 0.0

    def tearDown(self) -> None:
        self._cfg.__exit__(None, None, None)

    def _correr(self, gestor_kw: Optional[Dict[str, Any]] = None,
                crecer_zona: bool = False, v: float = 0.124
                ) -> Dict[str, Any]:
        fallas = FallasSimulador(
            modo_marcador_perdido="congelado", ruido_pos_m=0.0005,
            retardo_actuacion_s=0.45, semilla=3,
            zona_sin_captura=(0.0, 10.0, -10.0, 10.0))
        sim = SimuladorRobotat({self.ROBOT: self.MARCADOR},
                               {self.ROBOT: (-0.12, 0.0, 0.0)}, fallas,
                               puerto_poses=cfg.SIMULADOR_PUERTO_POSES,
                               puerto_base=cfg.SIMULADOR_PUERTO_BASE_ROBOT)
        out: Dict[str, Any] = {"evento": "sin_evento", "x_max": -math.inf}
        parar = threading.Event()

        def muestrear() -> None:
            while not parar.is_set():
                out["x_max"] = max(out["x_max"], sim.pose_de_robot(self.ROBOT)[0])
                time.sleep(0.003)

        with sim, contextlib.redirect_stdout(io.StringIO()):
            fuente = FuentePosesRobotat(1)
            canal = CanalActuacionRobotat(1, fuente)
            fuente.conectar()
            canal.conectar()
            canal.decisiones_enviadas = cfg.DECISIONES_ARRANQUE   # sin rampa
            det = ses.DetectorCongelamiento(activo=True)
            gestor = GestorRetroceso(canal, periodo_s=0.1, **(gestor_kw or {}))
            hilo = threading.Thread(target=muestrear, daemon=True)
            hilo.start()
            try:
                proximo = time.perf_counter()
                for paso in range(80):
                    poses = fuente.leer_poses_ya()
                    ahora = time.perf_counter()
                    canal.enviar_acciones({0: (v, 0.0)})
                    if 0 in poses:
                        pose = tuple(float(c) for c in poses[0])
                        det.observar(0, pose)
                        ev = gestor.observar(0, det.repeticiones(0), ahora,
                                             paso, pose, 0.0)
                        if ev == "inicio":
                            out["t_det"] = ahora
                            if crecer_zona:
                                fallas.zona_sin_captura = (-10.0, 10.0,
                                                           -10.0, 10.0)
                        if ev in ("recuperada", "sigue_congelada"):
                            out["evento"], out["t_fin"] = ev, ahora
                            break
                    proximo += 0.1
                    time.sleep(max(0.0, proximo - time.perf_counter()))
                # La política frena; si hubo fallo, el mando ya es (0, 0).
                canal.enviar_acciones({0: (0.0, 0.0)})
                time.sleep(0.45 + 0.35)
                out["x_final"] = sim.pose_de_robot(self.ROBOT)[0]
                out["rpm_final"] = sim.rpm_en_ruedas(self.ROBOT)
                out["retroceso"] = (gestor.terminados[-1]
                                    if gestor.terminados else None)
            finally:
                parar.set()
                hilo.join(timeout=1.0)
                canal.cerrar()
                fuente.cerrar()
        return out

    def test_sale_del_punto_ciego_y_se_reanuda(self) -> None:
        out = self._correr()
        self.assertEqual(out["evento"], "recuperada", out)
        self.assertGreater(out["x_max"], 0.02, out)     # entró de verdad
        self.assertLess(out["x_final"], 0.0, out)        # y quedó afuera
        r = out["retroceso"]
        self.assertLessEqual(out["t_fin"] - out["t_det"],
                             r.plan.duracion_s + ESPERA_VERIFICACION_S + 0.15)

    def test_con_la_ventana_literal_se_queda_adentro(self) -> None:
        """Control negativo: sin el retardo ni el margen, no alcanza."""
        out = self._correr({"retardo_s": 0.0, "margen_s": 0.0})
        self.assertEqual(out["evento"], "sigue_congelada", out)
        self.assertGreater(out["x_final"], 0.01, out)    # quedó adentro

    def test_si_no_puede_salir_para_y_falla_dentro_del_tope(self) -> None:
        out = self._correr(crecer_zona=True)
        self.assertEqual(out["evento"], "sigue_congelada", out)
        r = out["retroceso"]
        self.assertLessEqual(out["t_fin"] - out["t_det"],
                             r.plan.duracion_s + ESPERA_VERIFICACION_S + 0.15)
        self.assertLessEqual(out["t_fin"] - out["t_det"],
                             VENTANA_MAX_S / K_MIN_RETROCESO
                             + MARGEN_RETROCESO_S + ESPERA_VERIFICACION_S
                             + 0.15)
        self.assertEqual(out["rpm_final"], (0.0, 0.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
