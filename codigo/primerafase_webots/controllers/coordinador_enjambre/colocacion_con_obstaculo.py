"""
colocacion_con_obstaculo.py
===========================
Colocación AUTÓNOMA de la demo del obstáculo móvil (2026-10-07, OK de José;
`tesis/PROPUESTA_colocacion_autonoma_obstaculo.md`). Antes de cada toma de
la L1 y la L2, los 5 agentes van SOLOS a sus blancos alrededor del
obstáculo QUIETO (Fase B de la propuesta), en vez de que el operador los
lleve a mano con la guía.

Se apoya en `colocacion_autonoma` (la colocación de la evaluación) por
IMPORTACIÓN, sin tocarla: la misma ley (girar, avanzar, orientarse, a
≤ 0.08 m/s), el mismo filtro de colocación (paredes con h recortado a ≥ 0,
robot–robot 50/50 entre agentes), las mismas reglas de abandono. Lo que
agrega, por la revisión adversarial del plan:

  · el obstáculo es una barrera FIJA con la fila del Exp O con v = 0
    (h = ‖p_mira − p_o‖ − D_o, D_o = 0.33, la misma de la toma), con
    responsabilidad COMPLETA del agente: el obstáculo no se mueve en esta
    fase. NUNCA se mueven a la vez el obstáculo y los agentes;
  · RODEO: si el tramo recto al blanco cruza el disco del obstáculo
    (radio 0.45 m), el agente lo rodea por el lado de menor arco, siguiendo
    un punto 60° adelante sobre un círculo de 0.55 m, y la métrica de
    progreso es el arco que le falta (sin esto, un agente que lo tenía de
    frente se trababa contra la barrera y se lo abandonaba a los 12 s);
  · el OBSTÁCULO vigilado en cada ciclo: pose fresca
    (`antiguedad_obstaculo_s`, porque `pose_obstaculo` devuelve la última
    válida para siempre), marcador congelado (hardware), que siga QUIETO
    (se movió más de 3 cm, o v̂ > 0.02 m/s en 5 ciclos seguidos = NO FRENA)
    y, si está conectado, su enlace (se le manda (0,0) en cada ciclo). Ante
    cualquiera: todos frenan y la colocación termina con `parada`, que la
    sesión trata como regla de parada (exige la "s");
  · CONTACTO durante la colocación (centros medidos < 0.15 m, agente–
    obstáculo o agente–agente): todos frenan y `parada`;
  · asentamiento de ESPERA_ASENTAR_S = 1.2 s (el obstáculo puede tener
    0.85 s de retardo) y comprobación de que todos quedaron quietos.

Blancos: los de la distribución de entrenamiento, por rechazo hasta quedar a
≥ SEPARACION_BLANCOS_AUTO_M = 0.65 m del punto MEDIDO del obstáculo (el
chequeo de arranque sigue en 0.50 m: el margen absorbe las tolerancias de
llegada). Rumbos: `sortear_rumbos`, lo mismo que usó la Fase 0.

Arranque del obstáculo en la L2 (decisión de José): la PROYECCIÓN de su pose
actual sobre el círculo. Al terminar una toma queda sobre él y mirando en el
sentido de marcha, así que casi nunca hay que moverlo.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

import config_robotat as cfg
import demo_obstaculo_movil as demo
from colocacion_autonoma import (
    HZ, MEJORA_MINIMA, S_CONGELADO, S_SIN_POSE_MAX, S_SIN_PROGRESO, T_MAX_S,
    TOL_LLEGADA_M, TOL_SALIDA_M, FiltroColocacion, InformeColocacion,
    _envolver, _leer, _no_empeorar, ley_nominal, sortear_rumbos,
)
from lib.filtro_cbf import RestriccionLineal

# ── parámetros (propuesta, §2–§3) ────────────────────────────────────────────
#: Separación de los blancos al punto MEDIDO del obstáculo, en automático.
SEPARACION_BLANCOS_AUTO_M: float = 0.65
#: Rodeo: el tramo al blanco "cruza" al obstáculo si pasa a menos de esto de
#: su centro (D_o 0.33 + 0.12) ...
RADIO_DISCO_RODEO_M: float = 0.45
#: ... y entonces se lo rodea siguiendo un punto sobre este círculo,
RADIO_RODEO_M: float = 0.55
#: ... adelantado este ángulo (o el arco que falte, si es menor).
ADELANTO_RODEO_RAD: float = math.radians(60.0)
#: El punto de rodeo no puede quedar más cerca que esto de una pared.
MARGEN_PARED_RODEO_M: float = 0.25
#: Un lado del rodeo se descarta si su arco pasa a menos de esto de un
#: agente que no se mueve (listo o abandonado): ahí el corredor entre la
#: fila del obstáculo y la del agente quieto queda de pocos cm (revisión).
DESPEJE_RODEO_M: float = 0.30
#: Reintento después de un "no avanza" sin rodeo: primero se aleja esto de
#: lo que tenga más cerca (propuesta §3, "retrocede 10 cm").
ALEJAMIENTO_REINTENTO_M: float = 0.10
#: Separación mínima entre dos consultas de poses de la colocación: dos
#: consultas pegadas pueden devolver la misma fila del servidor, que se
#: leería como marcador congelado (revisión; `_marcadores_congelados_al_
#: arrancar` separa las suyas 0.15 s por lo mismo).
ESPACIADO_MIN_CONSULTAS_S: float = 0.05
#: Asentamiento al terminar (el obstáculo puede tener 0.85 s de retardo).
ESPERA_ASENTAR_S: float = 1.2
#: Quietud: desplazamiento máximo entre dos lecturas separadas 0.3 s.
QUIETUD_M: float = 0.005
#: El obstáculo tiene que seguir quieto: desplazamiento máximo tolerado.
DESPLAZAMIENTO_OBSTACULO_MAX_M: float = 0.03
#: Antes de usar al obstáculo como barrera fija hay que esperar a que quede
#: QUIETO: al terminar una toma sigue andando hasta su retardo (0.85 s)
#: después de la orden de parada. Ensayo L2 con τ = 0.85 s del 2026-10-07:
#: sin esta espera, la colocación lo vio moverse 1.9 cm y lo tomó por "NO
#: FRENA" (falso positivo). Pasado este plazo con la orden de parada, sí lo
#: es.
T_MAX_QUIETUD_OBSTACULO_S: float = 3.0
#: Envolvente de arranque de la Fase 0 (propuesta, §3).
TOL_BLANCO_ARRANQUE_M: float = 0.12
ENVOLVENTE_RADIAL_M: float = 0.06
ENVOLVENTE_RUMBO_RAD: float = math.radians(25.0)


# =============================================================================
# GEOMETRÍA (funciones puras)
# =============================================================================

def proyeccion_al_circulo(pose: Sequence[float],
                          centro: Tuple[float, float] = demo.CENTRO_CIRCULO_ENV,
                          radio: float = demo.RADIO_CIRCULO_M,
                          distancia_min: float = 0.30,
                          ) -> Optional[Tuple[np.ndarray, float, float, float]]:
    """
    (P, rumbo de la tangente antihoraria en P, error radial, error de rumbo)
    de una pose; None si está a menos de `distancia_min` del centro, donde
    la proyección no está definida (p. ej. después de la L1).
    """
    dx, dy = float(pose[0]) - centro[0], float(pose[1]) - centro[1]
    d = math.hypot(dx, dy)
    if d < distancia_min:
        return None
    fase = math.atan2(dy, dx)
    p = np.array([centro[0] + radio * math.cos(fase),
                  centro[1] + radio * math.sin(fase)])
    rumbo = _envolver(fase + math.pi / 2.0)
    return p, rumbo, d - radio, _envolver(float(pose[2]) - rumbo)


def objetivo_obstaculo(modo: str, pose_o: Optional[Sequence[float]],
                       semilla: int) -> Tuple[np.ndarray, Optional[float], str]:
    """
    Punto (y rumbo, en la L2) donde tiene que arrancar el obstáculo, y de
    dónde sale: L1 → el centro; L2 → la proyección de su pose actual sobre
    el círculo (decisión de José) o, si no está definida, la fase sorteada
    por la semilla, como hasta ahora.
    """
    if modo == "L1":
        return np.array(demo.PUNTO_L1_ENV, dtype=np.float64), None, "centro"
    if pose_o is not None:
        proy = proyeccion_al_circulo(pose_o)
        if proy is not None:
            return proy[0], proy[1], "proyeccion"
    p, rumbo = demo.arranque_obstaculo(semilla, "L2")
    return np.asarray(p, dtype=np.float64), rumbo, "semilla"


def problemas_envolvente_obstaculo(modo: str,
                                   pose_o: Optional[Sequence[float]]) -> List[str]:
    """¿El obstáculo está donde la Fase 0 validó los arranques? (propuesta §3)"""
    if pose_o is None:
        return ["obstáculo: sin pose"]
    if modo == "L1":
        c = np.array(demo.PUNTO_L1_ENV)
        d = float(np.linalg.norm(np.asarray(pose_o[:2], dtype=float) - c))
        if d > demo.TOL_COLOCACION_OBSTACULO_M:
            return [f"obstáculo a {d * 100:.1f} cm del centro (máx "
                    f"{demo.TOL_COLOCACION_OBSTACULO_M * 100:.0f} cm)"]
        return []
    proy = proyeccion_al_circulo(pose_o)
    if proy is None:
        return ["obstáculo fuera del círculo (cerca del centro)"]
    _p, _r, e_rad, e_rumbo = proy
    problemas: List[str] = []
    if abs(e_rad) > ENVOLVENTE_RADIAL_M:
        problemas.append(f"obstáculo a {e_rad * 100:+.1f} cm de su círculo "
                         f"(máx ±{ENVOLVENTE_RADIAL_M * 100:.0f} cm)")
    if abs(e_rumbo) > ENVOLVENTE_RUMBO_RAD:
        problemas.append(f"obstáculo a {math.degrees(e_rumbo):+.0f}° de la "
                         f"tangente antihoraria (máx "
                         f"±{math.degrees(ENVOLVENTE_RUMBO_RAD):.0f}°)")
    return problemas


def sortear_blancos_lejos(n_agentes: int, semilla: int,
                          punto_obstaculo: Sequence[float],
                          separacion: float = SEPARACION_BLANCOS_AUTO_M,
                          intentos: int = 400) -> Dict[int, np.ndarray]:
    """`sortear_blancos_demo` con la separación como parámetro (0.65 m)."""
    import sesion_robotat as ses
    rng = np.random.default_rng(int(semilla))
    p_o = np.asarray(punto_obstaculo, dtype=np.float64)[:2]
    for _ in range(intentos):
        b = ses.sortear_poses_arranque(n_agentes, rng)
        if all(float(np.linalg.norm(p - p_o)) >= separacion for p in b.values()):
            return b
    raise RuntimeError("no se pudieron sortear blancos lejos del obstáculo")


def _tramo_cruza_disco(a: np.ndarray, b: np.ndarray, o: np.ndarray,
                       radio: float) -> bool:
    """¿El tramo a→b pasa a menos de `radio` de o, con o ENTRE los dos?"""
    ab = b - a
    largo2 = float(ab @ ab)
    if largo2 < 1e-12:
        return False
    t = float((o - a) @ ab) / largo2
    if not 0.0 < t < 1.0:
        return False
    return float(np.linalg.norm(a + t * ab - o)) < radio


def _dentro(p: np.ndarray, margen: float) -> bool:
    return (margen <= float(p[0]) <= cfg.ARENA_WX_M - margen
            and margen <= float(p[1]) <= cfg.ARENA_WY_M - margen)


def _arco_despejado(o: np.ndarray, fa: float, s: int, arco: float,
                    quietos: Sequence[np.ndarray]) -> bool:
    """¿El arco de rodeo (cada ~10°) pasa lejos de los agentes quietos?"""
    if not quietos:
        return True
    pasos = max(1, int(math.ceil(arco / math.radians(10.0))))
    for k in range(pasos + 1):
        ang = fa + s * arco * k / pasos
        q = o + RADIO_RODEO_M * np.array([math.cos(ang), math.sin(ang)])
        if any(float(np.linalg.norm(q - np.asarray(z)[:2])) < DESPEJE_RODEO_M
               for z in quietos):
            return False
    return True


def meta_de_rodeo(p: Sequence[float], blanco: Sequence[float],
                  p_o: Sequence[float], sentido: Optional[int] = None,
                  quietos: Sequence[np.ndarray] = (),
                  ) -> Tuple[Optional[np.ndarray], Optional[int], float]:
    """
    Rodeo del obstáculo (propuesta §3). Si el tramo p→blanco cruza su disco,
    devuelve (punto al que ir, sentido +1 antihorario / −1 horario, métrica
    de progreso = arco que falta + lo que queda del círculo al blanco); si
    no, (None, None, distancia al blanco). `sentido` se respeta si es
    posible (pegajoso: no cambia de lado a mitad del rodeo). Un lado cuyo
    arco pasa a menos de DESPEJE_RODEO_M de un agente `quieto` se descarta
    mientras el otro esté libre; si los dos están ocupados, el de siempre.
    """
    a = np.asarray(p, dtype=np.float64)[:2]
    b = np.asarray(blanco, dtype=np.float64)[:2]
    o = np.asarray(p_o, dtype=np.float64)[:2]
    directo = float(np.linalg.norm(b - a))
    if not _tramo_cruza_disco(a, b, o, RADIO_DISCO_RODEO_M):
        return None, None, directo
    fa = math.atan2(a[1] - o[1], a[0] - o[0])
    fb = math.atan2(b[1] - o[1], b[0] - o[0])
    preferidos = ([sentido, -sentido] if sentido in (1, -1)
                  else ([1, -1] if _envolver(fb - fa) >= 0 else [-1, 1]))
    resto = max(0.0, float(np.linalg.norm(b - o)) - RADIO_RODEO_M)
    candidatos = []
    for s in preferidos:
        arco = ((fb - fa) % (2 * math.pi)) if s > 0 else ((fa - fb) % (2 * math.pi))
        ang = fa + s * min(ADELANTO_RODEO_RAD, arco)
        w = o + RADIO_RODEO_M * np.array([math.cos(ang), math.sin(ang)])
        if _dentro(w, MARGEN_PARED_RODEO_M):
            candidatos.append((w, s, RADIO_RODEO_M * arco + resto,
                               _arco_despejado(o, fa, s, arco, quietos)))
    for w, s, m, libre in candidatos:
        if libre:
            return w, s, m
    if candidatos:
        w, s, m, _ = candidatos[0]
        return w, s, m
    return None, sentido, directo


def fila_obstaculo_fijo(filtro: FiltroColocacion, pose_i: np.ndarray,
                        p_o: Sequence[float]) -> RestriccionLineal:
    """
    La fila del Exp O con v = 0 sobre el punto de mira del agente y el
    CENTRO del obstáculo (h = ‖p_mira − p_o‖ − D_o), responsabilidad
    completa del agente, con h recortado a ≥ 0 como toda barrera de la
    colocación ("no empeorar" si ya está violada).
    """
    p_i = filtro._punto_de_mira(pose_i)
    G_i = filtro._matriz_G(float(pose_i[2]))
    delta = p_i - np.asarray(p_o, dtype=np.float64)[:2]
    dist = float(np.linalg.norm(delta))
    n = delta / dist if dist > 1e-9 else np.array([1.0, 0.0])
    return _no_empeorar(RestriccionLineal(
        c=n @ G_i, h=dist - demo.D_OBSTACULO_M, nombre="obstaculo"))


# =============================================================================
# COLOCACIÓN (FASE B)
# =============================================================================

@dataclass
class InformeColocacionObstaculo(InformeColocacion):
    """`InformeColocacion` más lo del obstáculo y la parada."""
    d_min_obst_m: float = float("inf")
    d_min_pares_m: float = float("inf")
    #: Texto de la regla de parada (contacto o falla del obstáculo), o "".
    parada: str = ""
    quietos: bool = False
    rodeos: Dict[int, int] = field(default_factory=dict)
    sentidos: Dict[int, int] = field(default_factory=dict)

    def como_fila(self, n_agentes: int) -> Dict[str, object]:
        fila = super().como_fila(n_agentes)
        fila.update({
            "col_d_min_obst_m": (round(self.d_min_obst_m, 4)
                                 if math.isfinite(self.d_min_obst_m) else ""),
            "col_d_min_pares_m": (round(self.d_min_pares_m, 4)
                                  if math.isfinite(self.d_min_pares_m) else ""),
            "col_parada": self.parada,
            "col_quietos": int(self.quietos),
            "col_rodeos": sum(self.rodeos.values()),
        })
        return fila


def _cartel_levantar(imprimir: Callable[[str], None], motivo: str) -> None:
    """El mismo cartel que la toma, en el acto (revisión: llegaba 1.5 s tarde)."""
    imprimir("=" * 68)
    imprimir(f"⚠ {motivo}")
    imprimir("⚠ EL OBSTÁCULO NO OBEDECE O NO SE LO PUEDE FRENAR: LEVANTARLO / "
             "CORTAR ALIMENTACIÓN.")
    imprimir("=" * 68)


def colocar_alrededor_del_obstaculo(
    fuente: Any, canal: Any,
    blancos: Dict[int, np.ndarray],
    rumbos: Dict[int, float],
    n_agentes: int,
    t_max_s: float = T_MAX_S,
    imprimir: Callable[[str], None] = print,
    vigilar_congelamiento: Optional[bool] = None,
    sentidos_previos: Optional[Dict[int, int]] = None,
    alejar: Sequence[int] = (),
    pose_obstaculo_ref: Optional[Sequence[float]] = None,
) -> InformeColocacionObstaculo:
    """
    Fase B: lleva a cada agente a su blanco y rumbo con el obstáculo QUIETO
    como barrera fija. No lanza por un robot que falle.

    `sentidos_previos`: sentido de rodeo a usar por agente (el reintento
    después de un "no avanza" pasa el contrario). `alejar`: agentes que, en
    un reintento después de un "no avanza" sin rodeo, primero se alejan
    ALEJAMIENTO_REINTENTO_M de lo que tengan más cerca. `pose_obstaculo_ref`:
    la pose del obstáculo cuando se lo dio por quieto, ANTES del Enter: si
    se movió desde entonces, es "NO FRENA" (sin esto, un movimiento durante
    el Enter no se veía).
    """
    vigilar = ((not cfg.SIMULADOR_ACTIVO) if vigilar_congelamiento is None
               else bool(vigilar_congelamiento))
    filtro = FiltroColocacion()
    robot = {i: cfg.MAPEO_AGENTES[i].id_robot for i in range(n_agentes)}
    rid_o = getattr(canal, "id_robot_obstaculo", "?")
    ultima: Dict[int, np.ndarray] = {}
    visto: Dict[int, float] = {}
    igual_desde: Dict[int, float] = {}
    llego = {i: False for i in range(n_agentes)}
    fase: Dict[int, str] = {i: "—" for i in range(n_agentes)}
    abandonado: Dict[int, str] = {}
    mejor: Dict[int, Tuple[float, float]] = {}
    modo_meta: Dict[int, str] = {}
    sentido: Dict[int, Optional[int]] = dict(sentidos_previos or {})
    comandado: Dict[int, Tuple[float, float]] = {i: (0.0, 0.0)
                                                  for i in range(n_agentes)}
    inf = InformeColocacionObstaculo()
    p_o_ini: Optional[np.ndarray] = (
        None if pose_obstaculo_ref is None
        else np.asarray(pose_obstaculo_ref, dtype=np.float64)[:2].copy())
    t_obst_fresco: Optional[float] = None
    rapidas = 0
    t0 = time.perf_counter()
    proximo = t0
    ultimo_informe = -1e9
    con_obst = bool(getattr(canal, "con_obstaculo", False))
    primer_ciclo = True
    alejar_meta: Dict[int, np.ndarray] = {}
    pendientes_alejar = set(int(i) for i in alejar)
    # La base de "fila repetida" del obstáculo es de la colocación: una fila
    # del latido del Enter, pegada a la primera consulta, no es congelamiento.
    if hasattr(fuente, "olvidar_fila_obstaculo"):
        fuente.olvidar_fila_obstaculo()

    def frenar_todos() -> None:
        canal.enviar_directo({i: (0.0, 0.0) for i in range(n_agentes)})

    def dormir() -> None:
        nonlocal proximo
        proximo = max(proximo + 1.0 / HZ,
                      time.perf_counter() + ESPACIADO_MIN_CONSULTAS_S)
        time.sleep(max(0.0, proximo - time.perf_counter()))

    try:
        while True:
            ahora = time.perf_counter()
            t = ahora - t0
            poses = _leer(fuente, n_agentes)          # refresca al obstáculo
            for i in range(n_agentes):
                if i not in poses:
                    continue
                p = np.asarray(poses[i], dtype=np.float64)
                se_movia = comandado[i] != (0.0, 0.0)
                repetida = i in ultima and np.array_equal(p, ultima[i])
                if repetida and (se_movia or i in igual_desde) and vigilar:
                    igual_desde.setdefault(i, ahora)
                else:
                    igual_desde.pop(i, None)
                ultima[i] = p
                visto[i] = ahora

            # ── el obstáculo: fresco, no congelado, quieto, enlace vivo ──
            pose_o = fuente.pose_obstaculo()
            fresca = (pose_o is not None and fuente.antiguedad_obstaculo_s()
                      <= cfg.ANTIGUEDAD_MAX_POSE_S)
            if fresca:
                t_obst_fresco = ahora
                if p_o_ini is None:
                    p_o_ini = np.asarray(pose_o[:2], dtype=np.float64).copy()
            motivo_o: Optional[str] = None
            if con_obst and (not canal.enviar_obstaculo(0.0, 0.0)
                             or canal.obstaculo_caido):
                motivo_o = (f"enlace de ruedas del obstáculo (robot {rid_o}) "
                            f"caído durante la colocación")
            if (motivo_o is None and vigilar and fresca
                    and fuente.repeticiones_obstaculo >= 1):
                motivo_o = ("marcador del obstáculo CONGELADO durante la "
                            "colocación (fila repetida bit a bit)")
            if motivo_o is None and fresca and p_o_ini is not None:
                desp = float(np.linalg.norm(np.asarray(pose_o[:2]) - p_o_ini))
                v_o = fuente.velocidad_obstaculo()
                rap = float(np.linalg.norm(v_o)) if v_o is not None else 0.0
                rapidas = rapidas + 1 if rap > demo.V_NO_FRENA_M_S else 0
                if (desp > DESPLAZAMIENTO_OBSTACULO_MAX_M
                        or rapidas >= demo.N_CONFIRMACION_OBEDIENCIA):
                    motivo_o = (f"el obstáculo NO FRENA: se movió "
                                f"{desp * 100:.1f} cm durante la colocación "
                                f"(v medida {rap:.3f} m/s), debía estar quieto")
            if motivo_o is None:
                desde = t0 if t_obst_fresco is None else t_obst_fresco
                if ahora - desde > S_SIN_POSE_MAX:
                    motivo_o = "sin pose fresca del obstáculo"
            if motivo_o is not None:
                frenar_todos()
                inf.parada = f"ABORTO POR EL OBSTÁCULO: {motivo_o}"
                inf.motivo_fin = motivo_o
                if "NO FRENA" in motivo_o or "enlace" in motivo_o:
                    _cartel_levantar(imprimir, motivo_o)
                else:
                    imprimir(f"  ⛔ colocación: {motivo_o} — se mandó frenar "
                             f"a todos")
                break

            # ── nadie se mueve hasta ver a TODOS y al obstáculo fresco ───
            nunca_vistos = [i for i in range(n_agentes) if i not in ultima]
            if nunca_vistos or not fresca:
                comandado = {i: (0.0, 0.0) for i in range(n_agentes)}
                canal.enviar_directo(comandado)
                if nunca_vistos and t > S_SIN_POSE_MAX:
                    for i in nunca_vistos:
                        abandonado[i] = "sin pose desde el inicio"
                    inf.motivo_fin = (
                        "no se movió a nadie: sin pose al empezar el/los "
                        "robot(s) " + ", ".join(str(robot[i])
                                                for i in nunca_vistos))
                    imprimir(f"  ⚠ colocación: {inf.motivo_fin}")
                    break
                primer_ciclo = False
                dormir()
                continue

            # ── contacto (centros medidos) ───────────────────────────────
            p_o = np.asarray(pose_o[:2], dtype=np.float64)
            contacto: Optional[str] = None
            for i, p in ultima.items():
                d_ = float(np.linalg.norm(p[:2] - p_o))
                inf.d_min_obst_m = min(inf.d_min_obst_m, d_)
                if d_ < demo.UMBRAL_CONTACTO_M and contacto is None:
                    contacto = f"robot {robot[i]} a {d_:.3f} m del obstáculo"
            ids = sorted(ultima)
            for a_ in range(len(ids)):
                for b_ in range(a_ + 1, len(ids)):
                    d_ = float(np.linalg.norm(ultima[ids[a_]][:2]
                                              - ultima[ids[b_]][:2]))
                    inf.d_min_pares_m = min(inf.d_min_pares_m, d_)
                    if d_ < demo.UMBRAL_CONTACTO_M and contacto is None:
                        contacto = (f"robots {robot[ids[a_]]} y "
                                    f"{robot[ids[b_]]} a {d_:.3f} m")
            if contacto is not None:
                frenar_todos()
                inf.parada = (f"CONTACTO "
                              + ("antes de mover a nadie" if primer_ciclo
                                 else "durante la colocación")
                              + f": {contacto} (< {demo.UMBRAL_CONTACTO_M:.2f} m)")
                inf.motivo_fin = inf.parada
                imprimir(f"  ⛔ colocación: {inf.parada} — se mandó frenar a "
                         f"todos")
                break

            # ── abandonos (como `colocar_enjambre`) ──────────────────────
            congelado_ahora: List[int] = []
            for i in range(n_agentes):
                if i in abandonado or fase[i] == "listo":
                    continue
                if ahora - visto.get(i, t0) > S_SIN_POSE_MAX:
                    abandonado[i] = "sin pose"
                elif (i in igual_desde
                      and ahora - igual_desde[i] > S_CONGELADO):
                    abandonado[i] = "marcador congelado"
                    congelado_ahora.append(i)
                elif i in mejor and ahora - mejor[i][1] > S_SIN_PROGRESO:
                    abandonado[i] = "no avanza"
                if i in abandonado:
                    imprimir(f"  ⚠ colocación: robot {robot[i]} queda para el "
                             f"operador ({abandonado[i]})")
            if congelado_ahora:
                inf.motivo_fin = (
                    "marcador congelado (robot " + ", ".join(
                        str(robot[i]) for i in congelado_ahora)
                    + "): se detuvo la colocación de todos")
                imprimir(f"  ⚠ colocación: {inf.motivo_fin}")
                break

            # ── ley + rodeo + filtro ─────────────────────────────────────
            acciones: Dict[int, Tuple[float, float]] = {}
            quietos_pos = [ultima[j][:2] for j in range(n_agentes)
                           if j in ultima and (j in abandonado
                                               or fase[j] == "listo")]
            for i in sorted(pendientes_alejar):
                if i in ultima and i not in alejar_meta:
                    # Alejarse de lo más cercano: otro agente o el obstáculo.
                    otros = [ultima[j][:2] for j in ultima if j != i] + [p_o]
                    cerca = min(otros, key=lambda q: float(
                        np.linalg.norm(q - ultima[i][:2])))
                    dir_ = ultima[i][:2] - cerca
                    nd = float(np.linalg.norm(dir_))
                    dir_ = dir_ / nd if nd > 1e-9 else np.array([1.0, 0.0])
                    alejar_meta[i] = ultima[i][:2] + ALEJAMIENTO_REINTENTO_M * dir_
            for i in range(n_agentes):
                if i in abandonado or i not in poses or i in igual_desde:
                    acciones[i] = (0.0, 0.0)
                    continue
                p = ultima[i]
                blanco = np.asarray(blancos[i], dtype=np.float64)
                if i in pendientes_alejar and i in alejar_meta:
                    if float(np.linalg.norm(alejar_meta[i] - p[:2])) <= TOL_LLEGADA_M:
                        pendientes_alejar.discard(i)
                        mejor.pop(i, None)
                    else:
                        meta_a = alejar_meta[i]
                        if modo_meta.get(i) != "alejar":
                            mejor.pop(i, None)
                            modo_meta[i] = "alejar"
                        u_nom, fase[i] = ley_nominal(p, meta_a, rumbos[i], False)
                        metrica = float(np.linalg.norm(meta_a - p[:2]))
                        if i not in mejor or metrica < mejor[i][0] - MEJORA_MINIMA:
                            mejor[i] = (metrica, ahora)
                        restr = filtro.barreras_robots(i, ultima) + [
                            fila_obstaculo_fijo(filtro, p, p_o)]
                        res = filtro.filtrar(p, np.array(u_nom), restr)
                        u = res.u_seguro if res.exito_qp else np.zeros(2)
                        acciones[i] = (float(u[0]), float(u[1]))
                        continue
                d = float(np.linalg.norm(blanco[:2] - p[:2]))
                antes = llego[i]
                if d <= TOL_LLEGADA_M:
                    llego[i] = True
                elif d > TOL_SALIDA_M:
                    llego[i] = False
                if llego[i] != antes:
                    mejor.pop(i, None)
                if llego[i]:
                    meta, modo = blanco, "orientar"
                    metrica = 0.1 * abs(_envolver(rumbos[i] - float(p[2])))
                else:
                    paso_, s, m = meta_de_rodeo(p, blanco, p_o, sentido.get(i),
                                                quietos_pos)
                    if paso_ is not None:
                        if modo_meta.get(i) != "rodeo":
                            inf.rodeos[i] = inf.rodeos.get(i, 0) + 1
                        sentido[i] = s
                        meta, modo, metrica = paso_, "rodeo", m
                    else:
                        meta, modo = blanco, "directo"
                        err = _envolver(math.atan2(blanco[1] - p[1],
                                                   blanco[0] - p[0])
                                        - float(p[2]))
                        metrica = d + 0.1 * abs(err)
                if modo_meta.get(i) != modo:
                    mejor.pop(i, None)       # otra meta, otra métrica
                    modo_meta[i] = modo
                u_nom, fase[i] = ley_nominal(p, meta, rumbos[i], llego[i])
                if i not in mejor or metrica < mejor[i][0] - MEJORA_MINIMA:
                    mejor[i] = (metrica, ahora)
                if fase[i] == "listo":
                    acciones[i] = (0.0, 0.0)
                    continue
                restr = filtro.barreras_robots(i, ultima) + [
                    fila_obstaculo_fijo(filtro, p, p_o)]
                res = filtro.filtrar(p, np.array(u_nom), restr)
                u = res.u_seguro if res.exito_qp else np.zeros(2)
                acciones[i] = (float(u[0]), float(u[1]))

            canal.enviar_directo(acciones)
            comandado = acciones
            primer_ciclo = False
            # Enlace de un AGENTE caído: conserva su última orden y sigue
            # andando sin que nadie lo vea (la toma sí corta por esto).
            caidos = (canal.enlaces_caidos()
                      if hasattr(canal, "enlaces_caidos") else [])
            if caidos:
                frenar_todos()
                quienes = ", ".join(str(robot[i]) for i in caidos if i in robot)
                inf.parada = (f"ENLACE DE RUEDAS CAÍDO durante la colocación: "
                              f"robot(s) {quienes} — conserva(n) su última "
                              f"orden")
                inf.motivo_fin = inf.parada
                _cartel_levantar(imprimir, inf.parada)
                break

            if t - ultimo_informe >= 2.0:
                ultimo_informe = t
                partes = []
                for i in range(n_agentes):
                    if i in abandonado:
                        e = f"✘ {abandonado[i]}"
                    elif i not in ultima:
                        e = "SIN POSE"
                    elif fase[i] == "listo":
                        e = "✔"
                    else:
                        d = float(np.linalg.norm(
                            np.asarray(blancos[i])[:2] - ultima[i][:2]))
                        e = (f"{d * 100:.0f} cm {fase[i]}"
                             + (" (rodeando)" if modo_meta.get(i) == "rodeo"
                                else ""))
                    partes.append(f"r{robot[i]} {e}")
                imprimir(f"  [colocación {t:4.0f} s] " + " · ".join(partes))

            pendientes = [i for i in range(n_agentes)
                          if i not in abandonado and fase[i] != "listo"]
            if not pendientes:
                inf.motivo_fin = ("todos listos" if not abandonado
                                  else "listos los que se podían mover")
                break
            if t > t_max_s:
                inf.motivo_fin = "tiempo agotado"
                break
            dormir()
    finally:
        try:
            frenar_todos()
        except Exception:                                      # noqa: BLE001
            pass
        if con_obst:
            try:
                canal.detener_obstaculo()
            except Exception:                                  # noqa: BLE001
                pass

    if inf.parada:
        # La sesión frena todo y pregunta con latido: no hay nada que asentar.
        inf.t_s = time.perf_counter() - t0
        inf.abandonados = dict(abandonado)
        inf.listos = [i for i in range(n_agentes) if fase[i] == "listo"
                      and i not in abandonado]
        return inf

    # Que termine lo que estaba en camino (retardo de hasta 0.85 s), y
    # comprobar que todos quedaron QUIETOS antes de leer la pose de arranque.
    time.sleep(ESPERA_ASENTAR_S)
    try:
        a = _leer(fuente, n_agentes)
        o_a = fuente.pose_obstaculo()
        time.sleep(0.3)
        b = _leer(fuente, n_agentes)
        o_b = fuente.pose_obstaculo()
        quietos = all(i in a and i in b and float(np.linalg.norm(
            np.asarray(b[i])[:2] - np.asarray(a[i])[:2])) <= QUIETUD_M
            for i in range(n_agentes))
        if o_a is not None and o_b is not None:
            quietos = quietos and float(np.linalg.norm(
                np.asarray(o_b)[:2] - np.asarray(o_a)[:2])) <= QUIETUD_M
        else:
            quietos = False
        inf.quietos = bool(quietos)
        for i, p in b.items():
            if i not in igual_desde:
                ultima[i] = np.asarray(p, dtype=np.float64)
    except Exception:                                          # noqa: BLE001
        inf.quietos = False

    inf.t_s = time.perf_counter() - t0
    inf.abandonados = dict(abandonado)
    inf.listos = [i for i in range(n_agentes) if fase[i] == "listo"
                  and i not in abandonado]
    inf.sentidos = {i: s for i, s in sentido.items() if s is not None}
    for i, p in ultima.items():
        inf.error_m[i] = float(np.linalg.norm(
            np.asarray(blancos[i])[:2] - p[:2]))
        inf.error_rumbo_deg[i] = math.degrees(
            abs(_envolver(rumbos[i] - float(p[2]))))
    imprimir(f"  colocación: {inf.motivo_fin} en {inf.t_s:.0f} s — "
             f"{len(inf.listos)}/{n_agentes} en su blanco"
             + ("" if inf.quietos else " · ⚠ no todos quedaron quietos"))
    return inf


def esperar_obstaculo_quieto(fuente: Any, canal: Any, n_agentes: int,
                             t_max_s: float = T_MAX_QUIETUD_OBSTACULO_S
                             ) -> Tuple[Optional[str], str,
                                        Optional[np.ndarray]]:
    """
    Frena a todos y espera a que el obstáculo quede QUIETO: velocidad
    medida conocida y en la zona muerta, y < QUIETUD_M en ≥ 0.3 s.
    Devuelve (tipo, motivo, pose):
      · (None, "", pose)            quedó quieto: `pose` es la referencia;
      · ("mueve", …) / ("enlace", …) NO FRENA medido o enlace caído: regla
        de parada;
      · ("sin_pose", …) / ("sin_confirmar", …) no se pudo juzgar: vuelve al
        operador sin regla de parada (revisión: el obstáculo sin pose antes
        de colocar volvía inalcanzable la guía "colocalo A MANO").
    """
    con_obst = bool(getattr(canal, "con_obstaculo", False))
    rid_o = getattr(canal, "id_robot_obstaculo", "?")
    t0 = time.perf_counter()
    muestras: List[Tuple[float, np.ndarray]] = []
    rap = float("nan")
    while True:
        ahora = time.perf_counter()
        canal.enviar_directo({i: (0.0, 0.0) for i in range(n_agentes)})
        if con_obst and (not canal.enviar_obstaculo(0.0, 0.0)
                         or canal.obstaculo_caido):
            return ("enlace", f"enlace de ruedas del obstáculo (robot {rid_o}) "
                              f"caído antes de la colocación", None)
        _leer(fuente, n_agentes)
        pose = fuente.pose_obstaculo()
        if (pose is not None and fuente.antiguedad_obstaculo_s()
                <= cfg.ANTIGUEDAD_MAX_POSE_S):
            muestras.append((ahora, np.asarray(pose[:2], dtype=np.float64)))
            # Se guarda más de lo que se compara: con el costo de cada vuelta
            # una ventana de 0.30–0.35 s podía quedar sin muestras (revisión).
            muestras = [m for m in muestras if ahora - m[0] <= 1.0]
            v = fuente.velocidad_obstaculo()
            rap = float(np.linalg.norm(v)) if v is not None else float("nan")
            viejas = [m for m in muestras if ahora - m[0] >= 0.3]
            if (v is not None and rap < demo.ZONA_MUERTA_VELOCIDAD_M_S
                    and viejas and float(np.linalg.norm(
                        muestras[-1][1] - viejas[-1][1])) < QUIETUD_M):
                return None, "", np.asarray(pose, dtype=np.float64).copy()
        if ahora - t0 > t_max_s:
            if not muestras:
                return "sin_pose", "obstáculo: sin pose fresca", None
            if math.isfinite(rap) and rap > demo.V_NO_FRENA_M_S:
                return ("mueve", f"el obstáculo NO FRENA: sigue moviéndose "
                                 f"{t_max_s:.1f} s después de la orden de "
                                 f"parada (v medida {rap:.3f} m/s)", None)
            return ("sin_confirmar", f"obstáculo: no se pudo confirmar que "
                                     f"esté quieto (v medida {rap:.3f} m/s)",
                    None)
        time.sleep(0.1)


def problemas_tras_colocar(inf: InformeColocacionObstaculo,
                           poses_agentes: Dict[int, np.ndarray],
                           blancos: Dict[int, np.ndarray], modo: str,
                           pose_o: Optional[Sequence[float]],
                           n_agentes: int) -> List[str]:
    """
    Lo que la colocación automática agrega al chequeo de arranque (propuesta
    §3): marcador congelado durante la colocación, quietud y la envolvente
    de la Fase 0 (agentes a ≤ 0.12 m de su blanco; obstáculo en su círculo).
    """
    problemas: List[str] = []
    for i, m in sorted(inf.abandonados.items()):
        if m == "marcador congelado":
            problemas.append(
                f"agente {i} (robot {cfg.MAPEO_AGENTES[i].id_robot}): "
                f"marcador congelado durante la colocación — movelo o giralo "
                f"a mano hasta que la guía muestre su pose cambiando (Motive "
                f"lo perdió)")
    if not inf.quietos:
        problemas.append("no todos quedaron quietos después de la colocación")
    for i in range(n_agentes):
        if i not in poses_agentes:
            continue
        d = float(np.linalg.norm(np.asarray(poses_agentes[i])[:2]
                                 - np.asarray(blancos[i])[:2]))
        if d > TOL_BLANCO_ARRANQUE_M:
            problemas.append(
                f"agente {i} (robot {cfg.MAPEO_AGENTES[i].id_robot}): a "
                f"{d * 100:.0f} cm de su blanco (máx "
                f"{TOL_BLANCO_ARRANQUE_M * 100:.0f} cm)")
    problemas += problemas_envolvente_obstaculo(modo, pose_o)
    return problemas
