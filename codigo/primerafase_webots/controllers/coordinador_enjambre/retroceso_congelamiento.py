"""
retroceso_congelamiento.py
==========================
Reacción del lazo de evaluación a un marcador que se congela: el robot
RETROCEDE por el camino por el que entró, en vez de quedarse en pausa.

Por qué (2026-09-24)
--------------------
El encargado del Robotat confirmó el mecanismo de los congelamientos de
borde: un marcador que nunca se detectó sale como [0 0 0]; uno que YA se
detectó y entra en un punto ciego de las cámaras sale con la ÚLTIMA pose
registrada, retenida por Motive. El servidor no verifica la detección: sólo
reenvía. El congelamiento viene en los datos y la causa son los puntos ciegos
de la cobertura de cámaras.

Con eso, la pausa en la primera repetición (implementada el mismo día) se
traba: un robot detenido DENTRO del punto ciego no vuelve a ser visto nunca.
Lo que sí sirve es volver adonde se lo veía, y ese lugar se conoce sin mirar:
es el camino que el robot acaba de recorrer, que además estaba libre porque
lo ocupaba él.

Cómo
----
1. A la PRIMERA repetición de la pose completa (x, y, θ) se arma un plan con
   las órdenes que el robot RECIBIÓ en la ventana W anterior —rpm de rueda,
   ya escaladas por la rampa y el factor—, en orden inverso y con el signo
   cambiado. En el modelo diferencial, aplicar (−v, −ω) en orden inverso
   recorre el mismo camino hacia atrás, arco por arco. Después, un margen:
   el plan sigue unos cm más por el camino ANTERIOR a la ventana. Cada tramo
   cambia de velocidad por un factor k (ver "Velocidad"): el camino es el
   mismo y tarda 1/k.
2. Si durante el retroceso la pose vuelve a cambiar, el agente se reanuda en
   el acto: la política vuelve a mandar.
3. Si el plan se agota y, tras una espera de verificación en (0, 0), la pose
   sigue repetida, el robot queda parado y el episodio se aborta.

Los números (propuesta del 2026-09-24; a validar en el laboratorio)
-------------------------------------------------------------------
Qué se deshace: las órdenes de la ventana W = congelada + retardo, con tope
de 1.0 s, y después 0.4 s MÁS de retroceso por el camino anterior (margen).
  · congelada = t_detección − t_de_la_última_consulta_con_pose_distinta. Es
    la cota del tiempo que lleva congelada la pose: la última pose viva se
    capturó entre esa consulta y la primera que trajo el valor repetido. En
    la primera repetición, a 10 Hz, 0.2 s.
  · retardo = 0.45 s: el robot sigue ejecutando lo que ya recibió durante el
    retardo de actuación medido el 29-08 con el robot 1 (arranque a 0.15 m/s
    458 ms; frenado desde 0.15 m/s 452 ms). Sin este término —el "tiempo que
    lleva congelada" literal— se deshacen 0.2 s de un camino de ~0.6 s: a
    0.124 m/s el robot queda ~4–5 cm adentro del punto ciego. Lo muestran las
    pruebas con retardo (`test_retroceso_congelamiento.py`).
  · tope = 1.0 s de ventana: ≤ 12.4 cm a 0.124 m/s, el tope del régimen del
    laboratorio (factor 0.40). En la primera repetición W ≈ 0.65 s.
  · margen = 0.4 s DE RETROCESO, no de órdenes de entrada: si el robot tarda
    en arrancar en reversa, lo que se pierde es tiempo de retroceso. A
    0.05 m/s el arranque tardó 849 ms contra 458 ms a 0.15 m/s (29-08):
    +0.39 s. Expresado en órdenes de entrada, un margen de 0.2 s agregaba
    0.6 cm a 0.031 m/s y no cubría ese arranque (lo mostró el barrido del
    banco cinemático). A 0.07 m/s, 0.4 s son 2.8 cm, por espacio que el
    robot ya recorrió.
Velocidad: cada tramo se escala para que su rueda más rápida vaya a
  0.07 m/s (`V_LAB`, la saturación de `laboratorio11.m`), sin bajar nunca de
  la mitad de la velocidad de entrada (k ≥ 0.5). Una entrada más lenta que
  0.07 m/s se deshace a 0.07, más rápido que como entró: el retroceso
  arranca de quieto y en reversa, y a 0.05 m/s el arranque ya no es
  confiable; durante la rampa de arranque seguro la entrada va a
  ≤ 0.031 m/s (factor 0.40 × 0.25). El retroceso va a lazo abierto —la pose
  está congelada y no hay con qué corregir—: un robot que no arranca es un
  retroceso perdido.
Los tramos quietos no se repiten: esperar al revés no deshace camino, y cada
  parada obliga a otro arranque.
Espera de verificación: 0.6 s en (0, 0) cuando el plan se agota (> 0.45 s de
  retardo más una consulta; el mismo valor que `ESPERA_ASENTAR_S` de la
  colocación autónoma).
Tope total hasta el aborto: W/k + 0.4 + 0.6 s ≤ 3.0 s. En la primera
  repetición y entrando a 0.124 m/s: 0.65 / 0.565 + 0.4 + 0.6 ≈ 2.15 s, con
  8.1 + 2.8 ≈ 10.9 cm de camino comandado.

Seguridad frente a los otros robots: ellos esquivan la pose CONGELADA —la
última viva, que es la que les llega—; el robot real está adentro del punto
ciego, a lo sumo unos cm más allá. El retroceso lo devuelve hasta unos cm
DETRÁS de esa pose, por donde vino, así que achica la diferencia en vez de
agrandarla. La pausa lo dejaba en el punto más profundo.

⚠ Todo esto es a lazo abierto y supone un retardo puro. Es lo que prueba el
simulador (`FallasSimulador.retardo_actuacion_s`); el robot real tiene además
fricción de arranque que depende de la velocidad. Se valida en el laboratorio.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import config_robotat as cfg

# =============================================================================
# PARÁMETROS (ver el encabezado: de dónde sale cada uno)
# =============================================================================

#: Repeticiones de la pose de un agente que disparan el retroceso. Una: a
#: 10 Hz hubo 0 repeticiones benignas de (x, y, θ) en 34 715 pares
#: consecutivos (sesiones del 11, 22 y 24-09), y los 15 congelamientos
#: reales empezaron con el robot en marcha (auditoría del 24-09).
REPETICIONES_PARA_RETROCESO: int = 1

#: Retardo de actuación del 3pi a velocidad operativa (29-08, robot 1).
RETARDO_ACTUACION_S: float = 0.45

#: Segundos de retroceso DE MÁS, por el camino anterior a la ventana: cubre
#: un arranque en reversa hasta 0.4 s más lento que el retardo nominal (ver
#: el encabezado).
MARGEN_RETROCESO_S: float = 0.4

#: Tope de la ventana de órdenes que se deshace (sin contar el margen).
VENTANA_MAX_S: float = 1.0

#: Nunca más lento que esta fracción de la orden original. Acota además la
#: duración del plan: ≤ ventana / K_MIN_RETROCESO.
K_MIN_RETROCESO: float = 0.5

#: Velocidad lineal de la rueda más rápida al retroceder, en m/s.
V_RUEDA_RETROCESO: float = 0.07

#: Espera en (0, 0) cuando el plan se agota, antes de declarar el fallo.
ESPERA_VERIFICACION_S: float = 0.6

_RPM_A_RAD_S: float = 2.0 * math.pi / 60.0


# =============================================================================
# FUNCIONES PURAS
# =============================================================================

def rpm_a_v_omega(rpm_izq: float, rpm_der: float,
                  radio: Optional[float] = None,
                  medio_eje: Optional[float] = None) -> Tuple[float, float]:
    """
    (v, ω) del cuerpo a partir de las rpm de rueda: el modelo diferencial
    directo, v = r(φ̇_R + φ̇_L)/2 y ω = r(φ̇_R − φ̇_L)/(2ℓ). Inversa de
    `protocolo_robotat.accion_a_rpm` (sin la saturación).
    """
    r = cfg.RADIO_RUEDA_M if radio is None else float(radio)
    ell = cfg.MEDIO_EJE_M if medio_eje is None else float(medio_eje)
    phi_izq = float(rpm_izq) * _RPM_A_RAD_S
    phi_der = float(rpm_der) * _RPM_A_RAD_S
    return r * (phi_der + phi_izq) / 2.0, r * (phi_der - phi_izq) / (2.0 * ell)


def ventana_a_deshacer(t_deteccion: float,
                       t_ultima_distinta: Optional[float],
                       retardo_s: float = RETARDO_ACTUACION_S,
                       tope_s: float = VENTANA_MAX_S) -> float:
    """
    Segundos de órdenes a deshacer: lo que lleva congelada la pose (su cota
    superior) + el retardo de actuación, con tope. El margen va aparte: es
    tiempo de retroceso, no de órdenes (ver `plan_retroceso`).

    `t_ultima_distinta` es el instante de la última consulta cuya pose era
    DISTINTA del valor que ahora se repite. `None` —la pose se repitió antes
    de que hubiera dos consultas distintas— da el tope.
    """
    if t_ultima_distinta is None:
        return float(tope_s)
    congelada = max(0.0, float(t_deteccion) - float(t_ultima_distinta))
    return min(float(tope_s), congelada + float(retardo_s))


@dataclass(frozen=True)
class TramoRetroceso:
    """Un tramo del plan: rpm de rueda constantes durante `duracion_s`."""

    rpm_izq: float
    rpm_der: float
    duracion_s: float


@dataclass
class PlanRetroceso:
    """
    Las órdenes de la ventana y las del margen, en orden inverso, con el
    signo cambiado y la velocidad cambiada tramo a tramo. `mando_en(τ)` dice
    qué mandar a los τ segundos de empezado; `None` cuando el plan se agotó.
    """

    tramos: List[TramoRetroceso]
    ventana_s: float
    radio: float
    medio_eje: float
    #: Segundos de retroceso de margen que SÍ se pudieron armar: menos que
    #: lo pedido si el historial del episodio no llegaba tan atrás.
    margen_s: float = 0.0

    @property
    def duracion_s(self) -> float:
        """Lo que tarda el plan entero, en segundos."""
        return float(sum(t.duracion_s for t in self.tramos))

    def mando_en(self, tau: float) -> Optional[Tuple[float, float]]:
        """(rpm_izq, rpm_der) vigentes a los `tau` s del inicio, o None."""
        acumulado = 0.0
        for t in self.tramos:
            acumulado += t.duracion_s
            if tau < acumulado:
                return t.rpm_izq, t.rpm_der
        return None

    def _integral(self, indice: int) -> float:
        return float(sum(
            abs(rpm_a_v_omega(t.rpm_izq, t.rpm_der, self.radio,
                              self.medio_eje)[indice]) * t.duracion_s
            for t in self.tramos))

    @property
    def camino_m(self) -> float:
        """Largo del camino comandado hacia atrás, en metros."""
        return self._integral(0)

    @property
    def giro_rad(self) -> float:
        """Giro total comandado (suma de |ω|·dt), en radianes."""
        return self._integral(1)


def plan_retroceso(historial: Sequence[Tuple[float, float, float]],
                   t_ahora: float,
                   ventana_s: float,
                   margen_s: float = MARGEN_RETROCESO_S,
                   k_min: float = K_MIN_RETROCESO,
                   v_rueda: float = V_RUEDA_RETROCESO,
                   radio: Optional[float] = None,
                   medio_eje: Optional[float] = None) -> PlanRetroceso:
    """
    Arma el plan de retroceso con el historial de órdenes del agente.

    `historial`: (instante de envío, rpm_izq, rpm_der) en orden de envío —lo
    que el robot RECIBIÓ, ya escalado—. Cada orden rige desde su envío hasta
    el siguiente; la última, hasta `t_ahora`.

    1. Se deshace la ventana [t_ahora − ventana_s, t_ahora]: la orden vigente
       al empezar la ventana entra con la parte que cae adentro.
    2. Margen: se sigue con las órdenes ANTERIORES a la ventana hasta sumar
       `margen_s` segundos más de retroceso (el último tramo, recortado). Si
       el historial no llega, el margen queda más corto (`plan.margen_s`).

    Escala por tramo: k = V_RUEDA / (velocidad de la rueda más rápida), con
    k ≥ k_min, y la duración pasa a d/k. Como cada tramo es un arco (v, ω
    constantes) y escalar v y ω por el mismo k conserva el arco, el camino
    hacia atrás es el mismo con cualquier k. Los tramos quietos se omiten:
    no deshacen camino.
    """
    r = cfg.RADIO_RUEDA_M if radio is None else float(radio)
    ell = cfg.MEDIO_EJE_M if medio_eje is None else float(medio_eje)
    t_ahora = float(t_ahora)
    t0 = t_ahora - max(0.0, float(ventana_s))

    # Órdenes con el intervalo en que rigieron, de la más vieja a la nueva.
    rigieron: List[Tuple[float, float, float, float]] = []
    for j, (t, izq, der) in enumerate(historial):
        t_sig = float(historial[j + 1][0]) if j + 1 < len(historial) else t_ahora
        inicio, fin = float(t), min(t_sig, t_ahora)
        if fin > inicio:
            rigieron.append((float(izq), float(der), inicio, fin))

    tramos: List[TramoRetroceso] = []
    margen_pendiente = max(0.0, float(margen_s))
    for izq, der, inicio, fin in reversed(rigieron):
        if fin <= t0 and margen_pendiente <= 1e-12:
            break                       # ya todo es anterior a la ventana
        rueda_m_s = max(abs(izq), abs(der)) * _RPM_A_RAD_S * r
        if rueda_m_s <= 1e-12:
            continue                    # quieto: no hay camino que deshacer
        k = max(float(k_min), float(v_rueda) / rueda_m_s)
        # `0.0 - x` y no `-x`: un cero queda en 0.0 y no en −0.0.
        atras = (0.0 - k * izq, 0.0 - k * der)
        adentro = fin - max(inicio, t0)
        if adentro > 0.0:
            tramos.append(TramoRetroceso(*atras, adentro / k))
        antes = min(fin, t0) - inicio
        if antes > 0.0 and margen_pendiente > 1e-12:
            dur = min(antes / k, margen_pendiente)
            tramos.append(TramoRetroceso(*atras, dur))
            margen_pendiente -= dur
    return PlanRetroceso(tramos, float(ventana_s), r, ell,
                         max(0.0, float(margen_s)) - margen_pendiente)


# =============================================================================
# MÁQUINA DE ESTADOS POR EPISODIO
# =============================================================================

@dataclass
class Retroceso:
    """Un retroceso de un agente: en curso o terminado."""

    agente: int
    paso_inicio: int
    t_inicio: float
    plan: PlanRetroceso
    pose_congelada: Tuple[float, ...]
    d_pared_m: float
    paso_fin: int = -1
    t_fin: float = float("nan")
    #: "" en curso · "recuperada" · "sigue_congelada" · lo que diga
    #: `GestorRetroceso.cerrar_todos` (fin o aborto del episodio).
    resultado: str = ""

    @property
    def duracion_s(self) -> float:
        """De la detección al final (NaN si sigue en curso)."""
        return float(self.t_fin - self.t_inicio)

    def como_texto(self) -> str:
        """Una entrada de `retrocesos_detalle` en el CSV de episodios."""
        return (f"a{self.agente}:{self.paso_inicio}-{self.paso_fin}"
                f"({self.duracion_s:.1f}s,{100.0 * self.plan.camino_m:.1f}cm,"
                f"{self.resultado})")


class GestorRetroceso:
    """
    El retroceso por pose repetida, agente por agente, durante UN episodio.

    Se le pasa cada decisión de cada agente DESPUÉS del envío (`observar`),
    con las repeticiones que contó `DetectorCongelamiento`, y decide:
    empezar un retroceso, seguirlo, reanudar al agente o declararlo
    congelado. Manda por el canal (`fijar_mando`, `liberar_mando`) y arma el
    plan con lo que el canal registró (`historial_mandos`).

    `observar` devuelve qué pasó: "" (nada), "inicio", "sigue",
    "verificando", "recuperada" o "sigue_congelada" —ésta, para abortar—.
    """

    def __init__(self, canal: Any, periodo_s: float = 0.1,
                 retardo_s: float = RETARDO_ACTUACION_S,
                 margen_s: float = MARGEN_RETROCESO_S,
                 ventana_max_s: float = VENTANA_MAX_S,
                 k_min: float = K_MIN_RETROCESO,
                 v_rueda: float = V_RUEDA_RETROCESO,
                 espera_s: float = ESPERA_VERIFICACION_S,
                 repeticiones: int = REPETICIONES_PARA_RETROCESO,
                 radio: Optional[float] = None,
                 medio_eje: Optional[float] = None) -> None:
        self._canal = canal
        self.periodo_s = float(periodo_s)
        self.retardo_s = float(retardo_s)
        self.margen_s = float(margen_s)
        self.ventana_max_s = float(ventana_max_s)
        self.k_min = float(k_min)
        self.v_rueda = float(v_rueda)
        self.espera_s = float(espera_s)
        self.repeticiones = int(repeticiones)
        self._radio = radio
        self._medio_eje = medio_eje
        self.activos: Dict[int, Retroceso] = {}
        self.terminados: List[Retroceso] = []
        self._t_obs_previa: Dict[int, float] = {}
        self._t_ultima_distinta: Dict[int, float] = {}

    @property
    def en_retroceso(self) -> Set[int]:
        """Agentes con un retroceso en curso."""
        return set(self.activos)

    def observar(self, agente: int, repeticiones: int, ahora: float,
                 paso: int, pose: Sequence[float], d_pared_m: float) -> str:
        """Una decisión de un agente, después del envío. Ver la clase."""
        agente = int(agente)
        ahora = float(ahora)
        previa = self._t_obs_previa.get(agente)
        self._t_obs_previa[agente] = ahora
        if repeticiones == 0 and previa is not None:
            # La consulta anterior traía otra pose que ésta.
            self._t_ultima_distinta[agente] = previa

        r = self.activos.get(agente)
        if r is not None:
            if repeticiones == 0:
                self._terminar(r, paso, ahora, "recuperada")
                self._canal.liberar_mando(agente)
                return "recuperada"
            tau = ahora - r.t_inicio
            # Mitad del período: el mando elegido rige hasta la próxima
            # decisión, así que se elige el del centro de ese intervalo.
            mando = r.plan.mando_en(tau + self.periodo_s / 2.0)
            if mando is not None:
                self._canal.fijar_mando(agente, *mando)
                return "sigue"
            self._canal.fijar_mando(agente, 0.0, 0.0)
            if tau < r.plan.duracion_s + self.espera_s:
                return "verificando"
            self._terminar(r, paso, ahora, "sigue_congelada")
            return "sigue_congelada"

        if repeticiones >= self.repeticiones:
            ventana = ventana_a_deshacer(
                ahora, self._t_ultima_distinta.get(agente), self.retardo_s,
                self.ventana_max_s)
            plan = plan_retroceso(
                self._canal.historial_mandos(agente), ahora, ventana,
                self.margen_s, self.k_min, self.v_rueda, self._radio,
                self._medio_eje)
            self.activos[agente] = Retroceso(
                agente, int(paso), ahora, plan,
                tuple(float(v) for v in pose), float(d_pared_m))
            mando = plan.mando_en(self.periodo_s / 2.0)
            self._canal.fijar_mando(agente,
                                    *(mando if mando is not None
                                      else (0.0, 0.0)))
            return "inicio"
        return ""

    def cerrar_todos(self, paso: int, ahora: float, resultado: str) -> None:
        """Cierra los retrocesos en curso al terminar el episodio."""
        for r in list(self.activos.values()):
            self._terminar(r, paso, ahora, resultado)

    def _terminar(self, r: Retroceso, paso: int, ahora: float,
                  resultado: str) -> None:
        r.paso_fin = int(paso)
        r.t_fin = float(ahora)
        r.resultado = str(resultado)
        self.activos.pop(r.agente, None)
        self.terminados.append(r)
