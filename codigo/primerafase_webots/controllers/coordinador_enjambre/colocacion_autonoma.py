"""
colocacion_autonoma.py — antes de cada episodio de evaluación, los robots van
SOLOS a su blanco (posición y rumbo sorteados de la distribución de
entrenamiento), en vez de que el operador los lleve a mano.

Por qué (sesión del 2026-09-22):
  · colocar a mano cinco robots cerca de blancos sorteados es lento y el
    chequeo geométrico rechazaba seguido (pared a 15 cm, marcador tapado
    mientras se lo llevaba, robot fuera de la arena);
  · TODOS los cortes de socket de ruedas registrados (robots 1, 2 y 3; 9, 11
    y 22 sep) ocurrieron con el robot quieto mientras el operador lo
    manipulaba en la pausa de recolocación. Sin manipulación, esa fuente de
    episodios perdidos desaparece (y, de paso, se pone a prueba la hipótesis);
  · el pareo con la réplica NO depende de acertar el blanco: la réplica
    arranca de la pose MEDIDA al empezar el episodio. El blanco sólo asegura
    variedad y estar dentro de distribución. Esto además agrega el RUMBO, que
    a mano no se pedía: el entrenamiento lo sortea uniforme en (−π, π]
    (`swarm_env_skeleton._sortear_poses_iniciales`), y un robot que llega
    andando queda mirando en la dirección en que vino.

Ley de control, por robot, a 10 Hz:
  1. lejos del blanco: si el error de rumbo hacia el blanco supera 50°, gira
     en el lugar; si no, avanza con v ∝ distancia·cos(error) y ω ∝ error;
  2. en el blanco (< TOL_LLEGADA_M, con histéresis hasta TOL_SALIDA_M): gira
     en el lugar al rumbo sorteado;
  3. listo: (0, 0).
Velocidades ≤ V_COL = 0.08 m/s y ≤ W_COL = 1 rad/s: el régimen que el
laboratorio ya usa (V_LAB 0.07, OMEGA_LAB 1.0), muy por debajo del de la
política (0.124 m/s y 2.5 rad/s con factor 0.40).

Seguridad:
  · cada comando pasa por el MISMO filtro CBF de los episodios —paredes con
    d=0.18 y robot-robot con d=0.25 sobre el punto de mira, ℓa=0.05, α=2—
    con una sola diferencia: una barrera YA violada (h<0: un robot pegado a
    la pared o fuera de la arena al terminar el episodio anterior) exige "no
    empeorar" (ḣ ≥ 0) en vez de ḣ ≥ −α·h. Con h muy negativo, ḣ ≥ −α·h pide
    más velocidad de la que da la caja, el QP queda infactible, el filtro cae
    a u=(0,0) y el robot no sale nunca. Con h ≥ 0 recortado, u=(0,0) es
    siempre factible y cualquier movimiento hacia adentro está permitido;
  · NADIE se mueve hasta haber visto a TODOS al menos una vez: un robot que
    nunca se vio no tiene barrera en el filtro de los demás. Si alguno sigue
    sin verse a los S_SIN_POSE_MAX, la colocación termina sin mover a nadie y
    la sesión pasa al operador (revisión adversarial del 2026-09-22);
  · un robot que se deja de ver DESPUÉS recibe (0,0) y los demás lo esquivan
    en su última pose conocida; si pasa S_SIN_POSE_MAX sin pose, se lo deja;
  · marcador congelado (pose idéntica: un marcador vivo tiembla a ~82 Hz y
    nunca repite): a la primera repetición mientras se le ordenaba moverse se
    lo frena; si sigue igual S_CONGELADO, se detiene la colocación de TODOS,
    porque su posición real ya no se conoce y los demás lo esquivarían en una
    pose falsa. No aplica en el simulador, que repite poses de robots quietos;
  · un robot que no progresa en S_SIN_PROGRESO (enlace de ruedas caído, rueda,
    batería, dos robots trabados por el CBF) se detiene y se deja;
  · NO cuenta como decisión: usa `CanalActuacionRobotat.enviar_directo`, así
    la rampa de arranque —y su reconstrucción en la réplica— no cambian;
  · `finally`: (0, 0) a todos, y ESPERA_ASENTAR_S antes de devolver, para
    que la pose de arranque que lee la sesión (la de la réplica) no se tome
    con los robots todavía moviéndose por el retardo de actuación.
Si al terminar el chequeo geométrico no pasa, la sesión cae a la guía manual
de siempre, y lo que el operador haya dejado a mano se vuelve a colocar solo.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

import config_robotat as cfg
from lib.filtro_cbf import FiltroCBFParedes, RestriccionLineal

# ── régimen de colocación ────────────────────────────────────────────────────
V_COL: float = 0.08            # m/s, tope de avance
W_COL: float = 1.0             # rad/s, tope de giro
V_MIN: float = 0.03            # m/s: por debajo, la rueda no vence la zona muerta
W_MIN: float = 0.35            # rad/s, ídem al girar en el lugar
K_V: float = 0.8               # 1/s
K_W: float = 1.2               # 1/s
ANG_GIRO_EN_LUGAR: float = math.radians(50.0)
TOL_LLEGADA_M: float = 0.05
TOL_SALIDA_M: float = 0.10     # histéresis: recién acá deja de contar como llegado
TOL_RUMBO_RAD: float = math.radians(20.0)
HZ: float = 10.0
T_MAX_S: float = 90.0
S_SIN_POSE_MAX: float = 2.0
S_CONGELADO: float = 1.5
S_SIN_PROGRESO: float = 12.0
MEJORA_MINIMA: float = 0.01    # en la métrica de progreso (m + 0.1·rad)
ESPERA_ASENTAR_S: float = 0.6  # > retardo de actuación del 3pi (~0.45 s)

# ── filtro: los MISMOS parámetros que `coordinador_enjambre` (hay prueba) ────
ELE_A: float = 0.05
ALFA_CBF: float = 2.0
D_SEGURA_PUNTO: float = 0.18
W_OMEGA: float = 0.3
D_ROBOTS: float = 0.15 + 2.0 * ELE_A


def sortear_rumbos(n_agentes: int, semilla: int) -> Dict[int, float]:
    """
    Un rumbo por agente, uniforme en (−π, π] como en el entrenamiento.

    Generador APARTE del de los blancos de posición, para que agregar el
    rumbo no cambie las posiciones sorteadas de siempre.
    """
    rng = np.random.default_rng([int(semilla), 20260922])
    return {i: float(rng.uniform(-math.pi, math.pi)) for i in range(n_agentes)}


def _envolver(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


def ley_nominal(pose: np.ndarray, blanco: np.ndarray, rumbo: float,
                en_blanco: bool) -> Tuple[Tuple[float, float], str]:
    """(v, ω) nominal y la fase: 'girando', 'avanzando', 'orientando', 'listo'."""
    x, y, th = float(pose[0]), float(pose[1]), float(pose[2])
    if not en_blanco:
        dx, dy = float(blanco[0]) - x, float(blanco[1]) - y
        d = math.hypot(dx, dy)
        err = _envolver(math.atan2(dy, dx) - th)
        if abs(err) > ANG_GIRO_EN_LUGAR:
            w = math.copysign(min(max(K_W * abs(err), W_MIN), W_COL), err)
            return (0.0, w), "girando"
        v = min(max(K_V * d * math.cos(err), V_MIN), V_COL)
        w = max(-W_COL, min(W_COL, K_W * err))
        return (v, w), "avanzando"
    err = _envolver(float(rumbo) - th)
    if abs(err) <= TOL_RUMBO_RAD:
        return (0.0, 0.0), "listo"
    w = math.copysign(min(max(K_W * abs(err), W_MIN), W_COL), err)
    return (0.0, w), "orientando"


def _no_empeorar(r: RestriccionLineal) -> RestriccionLineal:
    """Barrera ya violada: exigir ḣ ≥ 0 en vez de ḣ ≥ −α·h (ver módulo)."""
    return RestriccionLineal(c=r.c, h=max(float(r.h), 0.0), nombre=r.nombre)


class FiltroColocacion(FiltroCBFParedes):
    """El filtro de paredes de los episodios, con h recortado a ≥ 0."""

    def __init__(self) -> None:
        super().__init__(
            arena_size=(cfg.ARENA_WX_M, cfg.ARENA_WY_M), ele_a=ELE_A,
            alfa=ALFA_CBF, d_segura=D_SEGURA_PUNTO, w_omega=W_OMEGA,
            v_max=V_COL, omega_max=W_COL)

    def _barreras_paredes(self, p, theta):
        return [_no_empeorar(r) for r in super()._barreras_paredes(p, theta)]

    def barreras_robots(self, i: int,
                        poses: Dict[int, np.ndarray]) -> List[RestriccionLineal]:
        """Robot-robot sobre puntos de mira, reparto 50/50 como el coordinador."""
        extras: List[RestriccionLineal] = []
        p_i = self._punto_de_mira(poses[i])
        G_i = self._matriz_G(float(poses[i][2]))
        for j, pose_j in poses.items():
            if j == i:
                continue
            delta = p_i - self._punto_de_mira(pose_j)
            dist = float(np.linalg.norm(delta))
            if dist < 1e-9:
                continue
            extras.append(_no_empeorar(RestriccionLineal(
                c=(delta / dist) @ G_i, h=0.5 * (dist - D_ROBOTS),
                nombre=f"robot_{j}")))
        return extras


@dataclass
class InformeColocacion:
    t_s: float = 0.0
    motivo_fin: str = ""
    listos: List[int] = field(default_factory=list)
    abandonados: Dict[int, str] = field(default_factory=dict)
    error_m: Dict[int, float] = field(default_factory=dict)
    error_rumbo_deg: Dict[int, float] = field(default_factory=dict)

    def como_fila(self, n_agentes: int) -> Dict[str, object]:
        """Columnas para el CSV de episodios."""
        fila: Dict[str, object] = {
            "col_t_s": round(self.t_s, 1),
            "col_motivo": self.motivo_fin,
            "col_listos": len(self.listos),
        }
        for i in range(n_agentes):
            fila[f"col_err_m_a{i}"] = (round(self.error_m[i], 4)
                                       if i in self.error_m else "")
            fila[f"col_err_rumbo_deg_a{i}"] = (
                round(self.error_rumbo_deg[i], 1)
                if i in self.error_rumbo_deg else "")
            fila[f"col_estado_a{i}"] = (
                "listo" if i in self.listos
                else self.abandonados.get(i, "no llegó"))
        return fila


def _leer(fuente, n_agentes: int) -> Dict[int, np.ndarray]:
    """Una consulta real por ciclo, sin el límite de tasa por tick."""
    if hasattr(fuente, "leer_poses_ya"):
        return fuente.leer_poses_ya()
    from lanzar_robotat import leer_poses_estables
    return leer_poses_estables(fuente, n_agentes, plazo_s=0.15)


def colocar_enjambre(
    fuente, canal,
    blancos: Dict[int, np.ndarray],
    rumbos: Dict[int, float],
    n_agentes: int,
    t_max_s: float = T_MAX_S,
    imprimir: Callable[[str], None] = print,
) -> InformeColocacion:
    """Lleva a cada agente a su blanco y rumbo. No lanza por un robot que falle."""
    filtro = FiltroColocacion()
    robot = {i: cfg.MAPEO_AGENTES[i].id_robot for i in range(n_agentes)}
    ultima: Dict[int, np.ndarray] = {}
    visto: Dict[int, float] = {}
    igual_desde: Dict[int, float] = {}
    llego = {i: False for i in range(n_agentes)}
    fase: Dict[int, str] = {i: "—" for i in range(n_agentes)}
    abandonado: Dict[int, str] = {}
    mejor: Dict[int, Tuple[float, float]] = {}     # (métrica, instante)
    comandado: Dict[int, Tuple[float, float]] = {i: (0.0, 0.0)
                                                  for i in range(n_agentes)}
    inf = InformeColocacion()
    t0 = time.perf_counter()
    proximo = t0
    ultimo_informe = -1e9
    try:
        while True:
            ahora = time.perf_counter()
            t = ahora - t0
            poses = _leer(fuente, n_agentes)
            for i in range(n_agentes):
                if i not in poses:
                    continue
                p = np.asarray(poses[i], dtype=np.float64)
                se_movia = comandado[i] != (0.0, 0.0)
                # Congelado: pose idéntica a la anterior. Un marcador vivo
                # tiembla a ~82 Hz y nunca repite; basta UNA repetición
                # mientras se le ordenaba moverse para frenarlo (abajo), y el
                # cronómetro sigue aunque ya esté frenado. En el simulador las
                # poses son ideales y un robot quieto repite: no aplica, igual
                # que `DetectorCongelamiento`.
                # Pose COMPLETA (x, y, θ), nunca sólo la posición: ver
                # `sesion_robotat.DetectorCongelamiento.observar`.
                repetida = i in ultima and np.array_equal(p, ultima[i])
                if (repetida and (se_movia or i in igual_desde)
                        and not cfg.SIMULADOR_ACTIVO):
                    igual_desde.setdefault(i, ahora)
                else:
                    igual_desde.pop(i, None)
                ultima[i] = p
                visto[i] = ahora

            # ── nadie se mueve hasta que se vea a TODOS ──────────────────
            # Revisión adversarial 2026-09-22: un robot que no se ve desde el
            # principio no tiene barrera en el filtro de los demás, que le
            # pasarían por encima (p. ej. uno que el episodio anterior dejó
            # en el hueco de seguimiento). Un robot perdido DESPUÉS sí
            # conserva su barrera en la última pose conocida (`ultima`).
            nunca_vistos = [i for i in range(n_agentes) if i not in ultima]
            if nunca_vistos:
                comandado = {i: (0.0, 0.0) for i in range(n_agentes)}
                canal.enviar_directo(comandado)
                if t > S_SIN_POSE_MAX:
                    for i in nunca_vistos:
                        abandonado[i] = "sin pose desde el inicio"
                    inf.motivo_fin = (
                        "no se movió a nadie: sin pose al empezar el/los "
                        "robot(s) " + ", ".join(str(robot[i])
                                                for i in nunca_vistos))
                    imprimir(f"  ⚠ colocación: {inf.motivo_fin}")
                    break
                proximo += 1.0 / HZ
                time.sleep(max(0.0, proximo - time.perf_counter()))
                continue

            # ── abandonos ────────────────────────────────────────────────
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
                    pista = {
                        # 2026-09-22, robot 1: pose viva, envíos sin error y
                        # cero movimiento. La placa atiende la red; lo que
                        # falla es la base del 3pi o su firmware.
                        "no avanza": " — pose viva y órdenes enviadas, pero no"
                                     " se mueve: revisá interruptor y pilas de"
                                     " la base, o apagalo y prendelo",
                        "sin pose": " — revisá que Motive lo vea",
                    }.get(abandonado[i], "")
                    imprimir(f"  ⚠ colocación: robot {robot[i]} queda para el "
                             f"operador ({abandonado[i]}){pista}")
            if congelado_ahora:
                # Su posición real ya no se conoce (pudo andar hasta
                # ~V_COL·(S_CONGELADO + 0.45 s de retardo) ≈ 16 cm sin que
                # se viera), y los demás lo esquivan en una pose falsa. No se
                # sigue moviendo a nadie: el operador lo saca de la zona.
                inf.motivo_fin = (
                    "marcador congelado (robot " + ", ".join(
                        str(robot[i]) for i in congelado_ahora)
                    + "): se detuvo la colocación de todos")
                imprimir(f"  ⚠ colocación: {inf.motivo_fin}")
                break

            # ── ley + filtro ─────────────────────────────────────────────
            acciones: Dict[int, Tuple[float, float]] = {}
            for i in range(n_agentes):
                if i in abandonado or i not in poses or i in igual_desde:
                    acciones[i] = (0.0, 0.0)
                    continue
                p = ultima[i]
                d = float(np.linalg.norm(np.asarray(blancos[i])[:2] - p[:2]))
                antes = llego[i]
                if d <= TOL_LLEGADA_M:
                    llego[i] = True
                elif d > TOL_SALIDA_M:
                    llego[i] = False
                if llego[i] != antes:
                    mejor.pop(i, None)      # otra fase, otra métrica
                u_nom, fase[i] = ley_nominal(p, np.asarray(blancos[i]),
                                             rumbos[i], llego[i])
                # Progreso: distancia + error de rumbo hacia el blanco, o
                # sólo el error al rumbo final una vez en el blanco.
                if llego[i]:
                    metrica = 0.1 * abs(_envolver(rumbos[i] - float(p[2])))
                else:
                    err = _envolver(math.atan2(float(blancos[i][1]) - p[1],
                                               float(blancos[i][0]) - p[0])
                                    - float(p[2]))
                    metrica = d + 0.1 * abs(err)
                if i not in mejor or metrica < mejor[i][0] - MEJORA_MINIMA:
                    mejor[i] = (metrica, ahora)
                if fase[i] == "listo":
                    acciones[i] = (0.0, 0.0)
                    continue
                res = filtro.filtrar(p, np.array(u_nom),
                                     filtro.barreras_robots(i, ultima))
                u = res.u_seguro if res.exito_qp else np.zeros(2)
                acciones[i] = (float(u[0]), float(u[1]))

            canal.enviar_directo(acciones)
            comandado = acciones

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
                        e = f"{d*100:.0f} cm {fase[i]}"
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
            proximo += 1.0 / HZ
            time.sleep(max(0.0, proximo - time.perf_counter()))
    finally:
        try:
            canal.enviar_directo({i: (0.0, 0.0) for i in range(n_agentes)})
        except Exception:                                      # noqa: BLE001
            pass

    # Que termine lo que ya estaba en camino: con ~450 ms de retardo de
    # actuación, el último comando sigue moviendo al robot después del (0,0).
    # La sesión lee acá la pose de ARRANQUE, que es la que usa la réplica
    # (revisión adversarial 2026-09-22). El informe usa esa misma lectura.
    time.sleep(ESPERA_ASENTAR_S)
    try:
        for i, p in _leer(fuente, n_agentes).items():
            if i not in igual_desde:
                ultima[i] = np.asarray(p, dtype=np.float64)
    except Exception:                                          # noqa: BLE001
        pass

    inf.t_s = time.perf_counter() - t0
    inf.abandonados = dict(abandonado)
    inf.listos = [i for i in range(n_agentes) if fase[i] == "listo"
                  and i not in abandonado]
    for i, p in ultima.items():
        inf.error_m[i] = float(np.linalg.norm(np.asarray(blancos[i])[:2] - p[:2]))
        inf.error_rumbo_deg[i] = math.degrees(abs(_envolver(rumbos[i] - float(p[2]))))
    imprimir(f"  colocación: {inf.motivo_fin} en {inf.t_s:.0f} s — "
             f"{len(inf.listos)}/{n_agentes} en su blanco")
    return inf
