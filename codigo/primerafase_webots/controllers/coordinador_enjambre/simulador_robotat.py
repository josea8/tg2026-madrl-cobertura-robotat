"""
simulador_robotat.py
====================
Servidor local que habla LOS DOS protocolos del Robotat —JSON de poses y CBOR
de ruedas— con un modelo cinemático detrás, para ejercitar todo el código de
despliegue sin hardware.

Qué es y qué NO es
------------------
SÍ es: un banco de pruebas del CLIENTE. Verifica que sabemos pedir poses,
interpretarlas, mandar ruedas, cerrar el lazo, y sobre todo que reaccionamos
bien cuando el sistema se porta mal.

NO es: un modelo del laboratorio real. Las poses las genera la misma
cinemática ideal que ya usábamos; no hay derrape, ni oclusión real de
marcadores, y el retardo del actuador es a lo sumo un retardo PURO opcional
(`retardo_actuacion_s`, apagado por defecto), sin la fricción de arranque del
3pi. Nada de lo que salga de acá dice nada sobre el gap sim-to-real. Lo único
que valida es el código de interfaz.

El simulador tiene su PROPIO mapeo marcador↔robot, independiente del que
declara `config_robotat`. Esa separación es a propósito: es lo que permite
que `verificar_mapeo_ids.py` detecte un mapeo cruzado (se puede arrancar el
simulador con una permutación y comprobar que la verificación falla).

Inyección de fallos
-------------------
  · latencia fija y con jitter en las respuestas de pose
  · pérdida de marcador, en los TRES modos plausibles (ceros / NaN / fila
    ausente), porque el código de referencia no documenta cuál ocurre, y en
    el que resultó ser el real: "congelado", la última pose, bit a bit
  · una zona sin captura (rectángulo del marco del laboratorio) donde el
    robot que entra pierde el marcador —la pérdida en los bordes que audita
    `diagnostico_poses.py`— y ruido de posición opcional, para que un robot
    quieto deje de repetir la pose bit a bit, como el real
  · retardo de actuación puro: cada orden de rueda llega a las ruedas
    `retardo_actuacion_s` después de recibida (el 3pi real tarda ~0.45 s;
    ver la memoria del 29-08). Lo usa la prueba del retroceso por pose
    repetida, que sin retardo no se puede juzgar
  · respuestas malformadas
  · caída de la conexión de poses tras N peticiones
  · robots "sordos" (rechazan conexión) y robots que caen tras N comandos
  · posiciones en milímetros, para ejercitar el rechazo por rango

Uso autónomo:
    python simulador_robotat.py            # arranca y queda escuchando

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import json
import math
import random
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Set, Tuple

from protocolo_robotat import decodificar_velocidades_rueda

# =============================================================================
# CONFIGURACIÓN DE FALLOS
# =============================================================================

@dataclass
class FallasSimulador:
    """Interruptores de inyección de fallos. Todo apagado por defecto."""

    latencia_poses_s:       float = 0.0
    jitter_latencia_s:      float = 0.0
    marcadores_perdidos:    Set[int] = field(default_factory=set)
    #: "congelado" es lo que hace el servidor real (medido 2026-08-29 y
    #: 2026-09-01): devuelve la ÚLTIMA pose publicada de ese marcador, bit a
    #: bit, o el placeholder `[0,-0,0,1,0,-0,0]` si nunca se publicó.
    modo_marcador_perdido:  str = "ceros"   # ceros | nan | faltante | congelado
    prob_respuesta_malformada: float = 0.0
    caer_poses_tras:        Optional[int] = None
    robots_sordos:          Set[int] = field(default_factory=set)
    robots_que_caen_tras:   Dict[int, int] = field(default_factory=dict)
    #: Si True, un robot de `robots_que_caen_tras` además deja de aceptar
    #: conexiones al caer: modela un robot INALCANZABLE (apagado, fuera de la
    #: red). Si False, sólo se corta esa conexión y el robot sigue escuchando
    #: —lo que hizo el robot 3 real el 2026-09-11—, y el canal lo recupera
    #: reconectando.
    caidos_no_reaceptan:    bool = False
    unidades_milimetros:    bool = False
    semilla:                int = 0
    #: Rectángulo del marco del laboratorio `(x_min, x_max, y_min, y_max)`
    #: donde la captura "no ve": un robot adentro cuenta como marcador
    #: perdido, con `modo_marcador_perdido`. `None` = sin zona.
    zona_sin_captura:       Optional[Tuple[float, float, float, float]] = None
    #: Si no es None, la zona sin captura sólo afecta a ESTOS marcadores: aísla
    #: un robot en las pruebas de sesión, para que la zona no atrape a otro
    #: que pasaba por ahí. `None` —el default— = todos.
    zona_solo_marcadores:   Optional[Set[int]] = None
    #: σ (m) de un ruido gaussiano en x e y de cada pose publicada, y σ/0.05
    #: rad en el rumbo. Con 0 —el default— el simulador sigue siendo ideal.
    ruido_pos_m:            float = 0.0
    #: Retardo PURO (s) entre recibir una orden de rueda y que las ruedas la
    #: ejecuten. Con 0 —el default— la orden rige en el acto, como siempre.
    retardo_actuacion_s:    float = 0.0


# =============================================================================
# ESTADO DE UN ROBOT
# =============================================================================

@dataclass
class EstadoRobot:
    """Pose en el marco del laboratorio y última orden de rueda recibida."""

    x:       float = 0.0
    y:       float = 0.0
    yaw:     float = 0.0
    rpm_izq: float = 0.0
    rpm_der: float = 0.0
    comandos_recibidos: int = 0
    #: Con `retardo_actuacion_s` > 0: órdenes recibidas que todavía no
    #: llegaron a las ruedas, (instante de aplicación, rpm_izq, rpm_der), y
    #: lo que las ruedas están haciendo. Con retardo 0 no se usan: la física
    #: integra `rpm_izq`/`rpm_der` como siempre.
    en_camino: Deque[Tuple[float, float, float]] = field(default_factory=deque)
    rpm_izq_ruedas: float = 0.0
    rpm_der_ruedas: float = 0.0


# =============================================================================
# SIMULADOR
# =============================================================================

class SimuladorRobotat:
    """
    Parámetros
    ----------
    mapeo_real : {id_robot: id_marcador} — la verdad del "laboratorio"
                 simulado. Permutarlo respecto de `config_robotat.MAPEO_AGENTES`
                 simula un mapeo mal configurado.
    poses_iniciales : {id_robot: (x, y, yaw)} en metros y radianes, marco lab.
    radio, medio_eje : geometría usada para integrar (por defecto, la del
                 config del cliente: el simulador no introduce discrepancia
                 de modelo, sólo de protocolo).
    """

    def __init__(
        self,
        mapeo_real:      Dict[int, int],
        poses_iniciales: Optional[Dict[int, Tuple[float, float, float]]] = None,
        fallas:          Optional[FallasSimulador] = None,
        host:            str = "127.0.0.1",
        puerto_poses:    int = 18830,
        puerto_base:     int = 19090,
        radio:           float = 0.016,
        medio_eje:       float = 0.048,
        dt_fisica_s:     float = 0.005,
    ) -> None:
        self.mapeo_real = dict(mapeo_real)
        self.fallas = fallas or FallasSimulador()
        self._host = host
        self._puerto_poses = int(puerto_poses)
        self._puerto_base = int(puerto_base)
        self._r = float(radio)
        self._l = float(medio_eje)
        self._dt = float(dt_fisica_s)
        self._rng = random.Random(self.fallas.semilla)
        # Generador APARTE para el ruido de posición: el de arriba ya decide
        # latencias y respuestas malformadas, y usar el mismo cambiaría esas
        # secuencias en las pruebas que no piden ruido.
        self._rng_ruido = random.Random(self.fallas.semilla + 7919)
        # Última pose publicada por marcador: la que devuelve el modo
        # "congelado".
        self._ultima_publicada: Dict[int, List[float]] = {}

        poses_iniciales = poses_iniciales or {}
        self.robots: Dict[int, EstadoRobot] = {}
        for id_robot in self.mapeo_real:
            x, y, yaw = poses_iniciales.get(id_robot, (0.0, 0.0, 0.0))
            self.robots[id_robot] = EstadoRobot(x=x, y=y, yaw=yaw)

        # marcador → robot, para responder consultas de pose
        self._de_marcador: Dict[int, int] = {
            m: r for r, m in self.mapeo_real.items()
        }

        self._lock = threading.Lock()
        self._corriendo = threading.Event()
        self._hilos: List[threading.Thread] = []
        self._escuchas: List[socket.socket] = []
        self.peticiones_pose: int = 0
        #: conexiones TCP nuevas aceptadas en el servidor de poses. Lo usa
        #: la prueba de regresión del escaneo de marcador: abrir una
        #: conexión NUEVA por consulta rompió contra el Robotat real (ver
        #: hallazgo de laboratorio 2026-08-21 en verificar_mapeo_ids.py),
        #: aunque el simulador —Python sin límite de conexiones— nunca lo
        #: hubiera mostrado por sí solo.
        self.conexiones_poses_aceptadas: int = 0
        self._escucha_por_robot: Dict[int, socket.socket] = {}
        self._ruedas_muertas: Set[int] = set()

    # ── ciclo de vida ────────────────────────────────────────────────────
    def iniciar(self) -> None:
        """Levanta el servidor de poses, los de ruedas y la física."""
        self._corriendo.set()
        self._lanzar(self._servidor_poses, "poses")
        for id_robot in sorted(self.mapeo_real):
            if id_robot in self.fallas.robots_sordos:
                print(f"[sim] robot {id_robot} SORDO (no escucha)")
                continue
            self._lanzar(self._servidor_ruedas, f"ruedas-{id_robot}", id_robot)
        self._lanzar(self._fisica, "fisica")
        time.sleep(0.15)   # que los listen() estén arriba antes de volver

    def detener(self) -> None:
        """Baja todo. Idempotente."""
        self._corriendo.clear()
        for s in self._escuchas:
            try:
                s.close()
            except OSError:
                pass
        self._escuchas.clear()
        for h in self._hilos:
            h.join(timeout=1.0)
        self._hilos.clear()

    def __enter__(self) -> "SimuladorRobotat":
        self.iniciar()
        return self

    def __exit__(self, *_excepcion: object) -> None:
        self.detener()

    def _lanzar(self, objetivo, nombre: str, *args: object) -> None:
        h = threading.Thread(target=objetivo, args=args,
                             name=f"sim-{nombre}", daemon=True)
        h.start()
        self._hilos.append(h)

    # ── física ───────────────────────────────────────────────────────────
    def _fisica(self) -> None:
        """
        Integra el modelo diferencial DIRECTO a partir de las RPM recibidas:
            v = r(φ̇_R + φ̇_L)/2      ω = r(φ̇_R − φ̇_L)/(2ℓ)
        """
        siguiente = time.perf_counter()
        while self._corriendo.is_set():
            retardo = self.fallas.retardo_actuacion_s
            ahora = time.perf_counter()
            with self._lock:
                for est in self.robots.values():
                    if retardo > 0.0:
                        while est.en_camino and est.en_camino[0][0] <= ahora:
                            (_t, est.rpm_izq_ruedas,
                             est.rpm_der_ruedas) = est.en_camino.popleft()
                        rpm_izq, rpm_der = est.rpm_izq_ruedas, est.rpm_der_ruedas
                    else:
                        rpm_izq, rpm_der = est.rpm_izq, est.rpm_der
                    phi_der = rpm_der * 2.0 * math.pi / 60.0
                    phi_izq = rpm_izq * 2.0 * math.pi / 60.0
                    v = self._r * (phi_der + phi_izq) / 2.0
                    w = self._r * (phi_der - phi_izq) / (2.0 * self._l)
                    est.x += v * math.cos(est.yaw) * self._dt
                    est.y += v * math.sin(est.yaw) * self._dt
                    est.yaw = math.atan2(math.sin(est.yaw + w * self._dt),
                                         math.cos(est.yaw + w * self._dt))
            siguiente += self._dt
            espera = siguiente - time.perf_counter()
            if espera > 0:
                time.sleep(espera)
            else:
                siguiente = time.perf_counter()

    # ── servidor de poses ────────────────────────────────────────────────
    def _servidor_poses(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self._host, self._puerto_poses))
        srv.listen(4)
        srv.settimeout(0.2)
        self._escuchas.append(srv)
        while self._corriendo.is_set():
            try:
                con, _ = srv.accept()
            except (socket.timeout, OSError):
                continue
            self.conexiones_poses_aceptadas += 1
            self._lanzar(self._atender_poses, "poses-con", con)

    def _atender_poses(self, con: socket.socket) -> None:
        con.settimeout(0.5)
        pendiente = b""
        try:
            while self._corriendo.is_set():
                try:
                    trozo = con.recv(4096)
                except socket.timeout:
                    continue
                if not trozo:
                    return
                pendiente += trozo
                if pendiente.strip().upper().startswith(b"EXIT"):
                    return
                try:
                    peticion = json.loads(pendiente.decode("ascii"))
                except (ValueError, UnicodeDecodeError):
                    continue          # mensaje incompleto: seguir acumulando
                pendiente = b""

                self.peticiones_pose += 1
                if (self.fallas.caer_poses_tras is not None
                        and self.peticiones_pose > self.fallas.caer_poses_tras):
                    print("[sim] cortando la conexión de poses (fallo inyectado)")
                    return

                lat = self.fallas.latencia_poses_s
                if self.fallas.jitter_latencia_s > 0.0:
                    lat += self._rng.uniform(0.0, self.fallas.jitter_latencia_s)
                if lat > 0.0:
                    time.sleep(lat)

                con.sendall(self._respuesta(list(peticion.get("pld", []))))
        except OSError:
            return
        finally:
            try:
                con.close()
            except OSError:
                pass

    def _respuesta(self, marcadores: List[int]) -> bytes:
        """Construye la respuesta JSON, aplicando los fallos configurados."""
        if (self.fallas.prob_respuesta_malformada > 0.0
                and self._rng.random() < self.fallas.prob_respuesta_malformada):
            return b'{"err":"mocap busy"}'

        escala = 1000.0 if self.fallas.unidades_milimetros else 1.0
        plano: List[float] = []
        with self._lock:
            for m in marcadores:
                id_robot = self._de_marcador.get(m)
                solo = self.fallas.zona_solo_marcadores
                perdido = (m in self.fallas.marcadores_perdidos
                           or (id_robot is not None
                               and (solo is None or m in solo)
                               and self._en_zona_sin_captura(id_robot)))
                if perdido and self.fallas.modo_marcador_perdido == "faltante":
                    continue
                if perdido and self.fallas.modo_marcador_perdido == "nan":
                    plano.extend([float("nan")] * 7)
                    continue
                if perdido and self.fallas.modo_marcador_perdido == "congelado":
                    plano.extend(self._ultima_publicada.get(
                        m, [0.0, -0.0, 0.0, 1.0, 0.0, -0.0, 0.0]))
                    continue
                if perdido:                       # "ceros"
                    plano.extend([0.0] * 7)
                    continue

                if id_robot is None:
                    plano.extend([0.0] * 7)
                    continue
                est = self.robots[id_robot]
                x, y, yaw = est.x, est.y, est.yaw
                if self.fallas.ruido_pos_m > 0.0:
                    s = self.fallas.ruido_pos_m
                    x += self._rng_ruido.gauss(0.0, s)
                    y += self._rng_ruido.gauss(0.0, s)
                    yaw += self._rng_ruido.gauss(0.0, s / 0.05)
                valores = [
                    x * escala, y * escala, 0.0,
                    math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0),
                ]
                self._ultima_publicada[m] = valores
                plano.extend(valores)
        return json.dumps(plano).encode("ascii")

    def _en_zona_sin_captura(self, id_robot: int) -> bool:
        """¿El robot está en la zona sin captura? Con el cerrojo tomado."""
        zona = self.fallas.zona_sin_captura
        if zona is None:
            return False
        est = self.robots[id_robot]
        x_min, x_max, y_min, y_max = zona
        return x_min <= est.x <= x_max and y_min <= est.y <= y_max

    # ── servidores de ruedas ─────────────────────────────────────────────
    def _servidor_ruedas(self, id_robot: int) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self._host, self._puerto_base + id_robot))
        srv.listen(2)
        srv.settimeout(0.2)
        self._escuchas.append(srv)
        self._escucha_por_robot[id_robot] = srv
        while self._corriendo.is_set():
            if id_robot in self._ruedas_muertas:
                return
            try:
                con, _ = srv.accept()
            except (socket.timeout, OSError):
                continue
            self._lanzar(self._atender_ruedas, f"ruedas-con-{id_robot}",
                         con, id_robot)

    def _atender_ruedas(self, con: socket.socket, id_robot: int) -> None:
        """
        Lee comandos de 11 bytes. El robot MANTIENE la última orden hasta
        recibir otra —igual que el hardware—, así que perder la conexión no
        lo detiene: es justo el comportamiento que hace que la parada por
        software no sea una parada de emergencia.
        """
        con.settimeout(0.5)
        pendiente = b""
        limite = self.fallas.robots_que_caen_tras.get(id_robot)
        try:
            while self._corriendo.is_set():
                try:
                    trozo = con.recv(256)
                except socket.timeout:
                    continue
                if not trozo:
                    return
                pendiente += trozo
                while len(pendiente) >= 11:
                    marco, pendiente = pendiente[:11], pendiente[11:]
                    try:
                        rpm_izq, rpm_der = decodificar_velocidades_rueda(marco)
                    except ValueError:
                        pendiente = b""
                        break
                    with self._lock:
                        est = self.robots[id_robot]
                        est.rpm_izq, est.rpm_der = rpm_izq, rpm_der
                        retardo = self.fallas.retardo_actuacion_s
                        if retardo > 0.0:
                            est.en_camino.append(
                                (time.perf_counter() + retardo,
                                 rpm_izq, rpm_der))
                        est.comandos_recibidos += 1
                        n = est.comandos_recibidos
                    if limite is not None and n >= limite:
                        print(f"[sim] robot {id_robot}: cortando enlace tras "
                              f"{n} comandos (fallo inyectado). Conserva "
                              f"rpm=({rpm_izq:.1f}, {rpm_der:.1f}).")
                        if self.fallas.caidos_no_reaceptan:
                            # Inalcanzable: se cierra el listener ANTES de
                            # soltar la conexión, así ningún reintento del
                            # cliente llega a colarse.
                            self._ruedas_muertas.add(id_robot)
                            srv = self._escucha_por_robot.get(id_robot)
                            if srv is not None:
                                try:
                                    srv.close()
                                except OSError:
                                    pass
                        return
        except OSError:
            return
        finally:
            try:
                con.close()
            except OSError:
                pass

    # ── inspección ───────────────────────────────────────────────────────
    def pose_de_robot(self, id_robot: int) -> Tuple[float, float, float]:
        """Pose real (verdad del simulador), para las aserciones de los tests."""
        with self._lock:
            e = self.robots[id_robot]
            return e.x, e.y, e.yaw

    def rpm_de_robot(self, id_robot: int) -> Tuple[float, float]:
        """
        Última orden de rueda recibida, en orden (izquierda, derecha). Con
        `retardo_actuacion_s` > 0 las ruedas todavía pueden estar ejecutando
        una anterior: ver `rpm_en_ruedas`.
        """
        with self._lock:
            e = self.robots[id_robot]
            return e.rpm_izq, e.rpm_der

    def rpm_en_ruedas(self, id_robot: int) -> Tuple[float, float]:
        """Lo que las ruedas ejecutan AHORA (con retardo 0, lo recibido)."""
        with self._lock:
            e = self.robots[id_robot]
            if self.fallas.retardo_actuacion_s > 0.0:
                return e.rpm_izq_ruedas, e.rpm_der_ruedas
            return e.rpm_izq, e.rpm_der

    def todos_detenidos(self, tol: float = 1e-6) -> bool:
        """True si todos los robots tienen orden de rueda nula (recibida)."""
        with self._lock:
            return all(abs(e.rpm_izq) < tol and abs(e.rpm_der) < tol
                       for e in self.robots.values())


def simulador_por_defecto(
    n_agentes: int = 5,
    fallas: Optional[FallasSimulador] = None,
) -> SimuladorRobotat:
    """
    Simulador con el MISMO mapeo que declara `config_robotat` y los robots
    repartidos en una fila, separados 0.4 m. Es el punto de partida de los
    tests de integración.

    Ninguna pose inicial está en el origen ni sobre un eje: un robot en
    (0, 0) es invariante de escala, y con él la validación por rango no
    podría distinguir metros de milímetros.
    """
    import config_robotat as cfg
    mapeo_real = {
        cfg.MAPEO_AGENTES[i].id_robot: cfg.MAPEO_AGENTES[i].id_marcador
        for i in range(n_agentes)
    }
    poses = {
        cfg.MAPEO_AGENTES[i].id_robot: (-0.8 + 0.4 * i, 0.3, 0.0)
        for i in range(n_agentes)
    }
    return SimuladorRobotat(mapeo_real, poses, fallas)


if __name__ == "__main__":
    import config_robotat as cfg

    sim = simulador_por_defecto()
    with sim:
        print("=" * 68)
        print("SIMULADOR DEL ROBOTAT — escuchando")
        print(f"  poses  : {sim._host}:{sim._puerto_poses}")
        for r in sorted(sim.mapeo_real):
            print(f"  robot {r}: {sim._host}:{sim._puerto_base + r}  "
                  f"(marcador {sim.mapeo_real[r]})")
        print("  Ctrl-C para terminar.")
        print("=" * 68)
        try:
            while True:
                time.sleep(1.0)
                for r in sorted(sim.mapeo_real):
                    x, y, th = sim.pose_de_robot(r)
                    izq, der = sim.rpm_de_robot(r)
                    print(f"  robot {r}: ({x:+.3f}, {y:+.3f}) "
                          f"θ={math.degrees(th):+7.1f}°  "
                          f"rpm=({izq:+7.1f}, {der:+7.1f})")
        except KeyboardInterrupt:
            print("\n[sim] terminando.")
