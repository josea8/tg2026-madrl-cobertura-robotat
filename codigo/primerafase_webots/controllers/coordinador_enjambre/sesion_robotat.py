"""
sesion_robotat.py
=================
Herramienta guiada para las sesiones de laboratorio en el Robotat.

PRINCIPIO RECTOR: el tiempo de laboratorio es para CAPTURAR, no para
analizar. Todo se escribe a disco; el análisis se hace después. Cada etapa
emite un veredicto automático, sin pedirle una interpretación a nadie con
cinco robots encendidos y el reloj corriendo.

Invocación
----------
    python sesion_robotat.py --sesion calibracion   # etapas 0-5, un robot
    python sesion_robotat.py --sesion politica      # un robot con la política
    python sesion_robotat.py --sesion enjambre      # cinco robots (pendiente)
    python sesion_robotat.py --sesion evaluacion    # corridas de tesis (pendiente)

    python sesion_robotat.py --etapa 3              # repetir una sola etapa
    python sesion_robotat.py --sesion politica --simulador   # ensayo sin hardware

Secuencia
---------
Cada etapa exige que la anterior haya dado OK. `--forzar` lo saltea, con
advertencia. Lo que se mide se guarda en `calibracion_medida.json` y las
sesiones siguientes lo leen: nada se reingresa a mano, ninguna sesión repite
trabajo de la previa.

⚠ Ver README_ROBOTAT.md §S1: la parada por software NO es una parada de
emergencia. Tiene que haber alguien mirando la arena con acceso al corte de
alimentación.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import argparse
import atexit
import csv
import json
import math
import socket
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import (Any, Callable, Deque, Dict, List, Optional, Sequence,
                    Tuple)

import numpy as np

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import calibracion_sesion as calib
import config_robotat as cfg
from adaptadores_robotat import descartar_buffer_pendiente
from protocolo_robotat import (
    VALORES_POR_AGENTE,
    accion_a_rpm,
    codificar_peticion_poses,
    codificar_velocidades_rueda,
    decodificar_respuesta_poses,
    heading_desde_cuaternion,
    lab_a_env,
    es_placeholder_no_trackeado,
    pose_es_valida,
)
from retroceso_congelamiento import GestorRetroceso

DIR_SALIDA: Path = _CARPETA / "resultados_sesion"

# Cotas de la caja de acciones de la política (concentration_dynamics).
V_MAX_POLITICA:     float = 0.31
OMEGA_MAX_POLITICA: float = 6.2832

# `DT_ENV` de coordinador_enjambre.py: el lazo decide cada 100 ms. Se
# repite acá como constante (no se importa `coordinador_enjambre` a nivel
# de módulo, mismo criterio que el resto del archivo) porque la etapa 4a
# la necesita para juzgar si el round-trip de poses es una fracción
# apreciable del presupuesto de una decisión — el número que decide si la
# arquitectura de consulta-antes-de-decidir (2026-08-22) se sostiene.
PERIODO_DECISION_S: float = 0.1
UMBRAL_PRESUPUESTO_HOLGADO:  float = 0.10   # p95 < 10 % del período: cómodo
UMBRAL_PRESUPUESTO_RIESGOSO: float = 0.30   # p95 > 30 %: plan de contingencia

#: Retardo de actuación tolerable, en múltiplos del período de decisión.
#: Un retardo por debajo de UNA decisión es lo que el lazo puede absorber sin
#: que la política actúe sobre información vieja. Se pone en 1.0 —no más
#: laxo— porque un comando tardío no se puede descartar como una pose
#: tardía: ya se ejecutó. Ver la nota en la etapa 4.
UMBRAL_ACTUACION_RIESGOSO: float = 1.0

# ── Referencia del laboratorio (laboratorio11.m) ─────────────────────────
# Offsets de rumbo por robot, en grados. El original los usa como
# `theta = wrap(yaw_reportado - offset)` y los indexa con `robot_no` en
# base 1: `marker_offsets(1)` corresponde al robot 1. No hay entrada para el
# robot 0. Se usan SÓLO como referencia para contrastar lo que mida la
# etapa 3; no se aplican automáticamente.
OFFSETS_LAB_DEG: Dict[int, float] = {
    1: -93.7618, 2: -89.7361, 3: -89.8177, 4: -81.9006, 5: -88.8106,
    6: -89.9653, 7: -94.0866, 8: -89.9872, 9: -94.2587, 10: 33.6573,
}

# Régimen validado en el laboratorio, para contrastar el barrido.
V_LAB:        float = 0.07     # velsat_v de laboratorio11.m
OMEGA_LAB:    float = 1.00     # velsat_w
RPM_CAP_LAB:  float = 200.0    # rpm_max (tope operativo, no del protocolo)


# =============================================================================
# UTILIDADES
# =============================================================================

class AbortoEtapa(Exception):
    """Condición que obliga a cortar la etapa en curso."""


class ConexionImposible(AbortoEtapa):
    """No se pudo abrir un socket, con diagnóstico accionable."""


def _diagnostico_conexion(que: str, host: str, puerto: int,
                          exc: BaseException) -> str:
    """
    Traduce un fallo de socket a algo que se pueda ACCIONAR en el
    laboratorio, distinguiendo los dos casos que piden cosas distintas.
    """
    es_timeout = isinstance(exc, (socket.timeout, TimeoutError))
    lineas = [
        f"No se pudo conectar al {que} en {host}:{puerto}",
        f"  ({type(exc).__name__}: {exc})",
        "",
    ]
    if es_timeout:
        lineas += [
            "TIMEOUT: el SYN no obtuvo respuesta. El host no contestó, no es",
            "que haya rechazado la conexión. Casos típicos, en orden:",
            "",
            f"  1. No estás en la red del laboratorio. Verificá que tengas",
            f"     una dirección de la misma subred:",
            f"       ipconfig | findstr IPv4",
            f"     Tiene que aparecer una 192.168.50.x",
            "  2. El servidor no está encendido o cambió de dirección.",
            "  3. Un firewall descarta el tráfico en silencio (descartar es",
            "     timeout; rechazar sería 'connection refused').",
            "",
            "NOTA: que `ping` falle NO prueba nada — el servidor habla TCP y",
            "muchos hosts ignoran ICMP. Pero un timeout de TCP como éste sí",
            "es un problema real de camino de red.",
        ]
    else:
        lineas += [
            "El host respondió pero rechazó la conexión: está en la red y",
            "accesible, pero no hay nadie escuchando en ese puerto.",
            "",
            "  1. ¿Es el puerto correcto? Poses = 1883, robots = 9090.",
            "  2. ¿El servicio está levantado en el servidor?",
            "  3. Si es un robot: ¿está encendido y con batería?",
        ]
    lineas += [
        "",
        "Prueba mínima equivalente, para aislar del resto del programa:",
        f"  python -c \"import socket; socket.create_connection"
        f"(('{host}',{puerto}),5); print('OK')\"",
    ]
    return "\n".join(lineas)


def ruta_salida(sesion: str, etapa: int, descripcion: str,
                extension: str = "csv") -> Path:
    """
    Ruta de salida con fecha, sin sobrescribir nunca. Si el nombre ya
    existe, agrega un sufijo `_02`, `_03`, …
    """
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    fecha = datetime.now().strftime("%Y%m%d")
    base = f"{fecha}_sesion-{sesion}_etapa{etapa}_{descripcion}"
    ruta = DIR_SALIDA / f"{base}.{extension}"
    k = 2
    while ruta.exists():
        ruta = DIR_SALIDA / f"{base}_{k:02d}.{extension}"
        k += 1
    return ruta


def escribir_csv(ruta: Path, filas: Sequence[Dict[str, Any]]) -> None:
    """Vuelca filas a CSV. No hace nada si no hay filas."""
    if not filas:
        print(f"[csv] sin datos para {ruta.name}")
        return
    columnas: List[str] = []
    for f in filas:
        for k in f:
            if k not in columnas:
                columnas.append(k)
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columnas)
        w.writeheader()
        w.writerows(filas)
    print(f"[csv] {len(filas)} filas → {ruta}")


def envolver(a: float) -> float:
    """Envuelve un ángulo a (-π, π]."""
    return math.atan2(math.sin(a), math.cos(a))


def ajustar_similitud(
    medidos: np.ndarray, reales: np.ndarray,
) -> Tuple[float, float, np.ndarray, float]:
    """
    Ajusta `real ≈ escala · R(θ) · medido + t` por mínimos cuadrados.

    Con dos puntos el ajuste es exacto (residuo 0 por construcción, así que
    el residuo NO valida nada); con tres o más, el RMS del residuo sí dice
    si el modelo de similitud alcanza.

    Retorna
    -------
    (escala, rotacion_rad, traslacion (2,), rms_residuo_m)
    """
    m = np.asarray(medidos, dtype=np.float64)[:, :2]
    r = np.asarray(reales,  dtype=np.float64)[:, :2]
    if m.shape[0] < 2:
        raise ValueError("hacen falta al menos dos puntos")

    cm, cr = m.mean(axis=0), r.mean(axis=0)
    a, b = m - cm, r - cr
    num = float(np.sum(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]))
    den = float(np.sum(a[:, 0] * b[:, 0] + a[:, 1] * b[:, 1]))
    theta = math.atan2(num, den)
    rot = np.array([[math.cos(theta), -math.sin(theta)],
                    [math.sin(theta),  math.cos(theta)]])
    a_rot = a @ rot.T
    denom = float(np.sum(a * a))
    escala = float(np.sum(b * a_rot) / denom) if denom > 0 else 1.0
    t = cr - escala * (rot @ cm)
    pred = escala * (m @ rot.T) + t
    rms = float(np.sqrt(np.mean(np.sum((pred - r) ** 2, axis=1))))
    return escala, theta, t, rms


# =============================================================================
# CLIENTES DE BAJO NIVEL
# =============================================================================
# Las etapas de calibración necesitan acceso CRUDO: bytes tal como llegan,
# poses sin transformar, un robot elegido por línea de comandos. Los
# adaptadores (`FuentePosesRobotat`) ya aplican mapeo y transformación de
# marco, que es justamente lo que estas etapas están midiendo.

class ClientePosesCrudo:
    """Cliente mínimo del servidor de poses, con acceso a los bytes."""

    def __init__(self) -> None:
        host, puerto = cfg.endpoint_poses()
        self.host, self.puerto = host, puerto
        self._sock = socket.create_connection((host, puerto),
                                              timeout=cfg.TIMEOUT_CONEXION_S)
        self._sock.settimeout(cfg.TIMEOUT_POSES_S)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # Ver `esperar_saludo_inicial`: sin esto la primera consulta de la
        # conexión puede recibir el saludo pegado adelante del JSON.
        from adaptadores_robotat import esperar_saludo_inicial
        #: bytes del saludo, descartados al conectar (52 B contra el real).
        self.saludo_descartado: int = esperar_saludo_inicial(self._sock)
        #: bytes descartados del buffer en la última `consultar()`.
        self.ultimo_descarte: int = 0

    def consultar(
        self, marcadores: List[int],
    ) -> Tuple[bytes, Optional[np.ndarray], float]:
        """
        Una consulta. Devuelve `(bytes_crudos, matriz|None, latencia_s)`.

        Los bytes crudos se devuelven SIEMPRE, incluso si no parsean: la
        etapa 5 los necesita literalmente.

        Antes de mandar, descarta lo que ya esté en el buffer de entrada
        (ver `descartar_buffer_pendiente`). Hallazgo de laboratorio
        (2026-08-21): sin esto, la primera consulta tras conectar leía
        basura vieja del servidor y nunca parseaba — reproducido dos veces
        contra el robot 1 real. `self.ultimo_descarte` queda expuesto para
        que la etapa 0 lo registre en el CSV como evidencia.
        """
        peticion = codificar_peticion_poses(marcadores)
        t0 = time.perf_counter()
        crudo = b""
        self.ultimo_descarte = 0
        try:
            # Dentro del try: si el socket está muriendo, `select` puede
            # marcarlo "listo" y el `recv` del descarte lanza. Debe caer en
            # el mismo manejo de (OSError, socket.timeout) que el resto.
            self.ultimo_descarte = descartar_buffer_pendiente(self._sock)
            self._sock.sendall(peticion)
            while True:
                trozo = self._sock.recv(4096)
                if not trozo:
                    break
                crudo += trozo
                m = decodificar_respuesta_poses(crudo, len(marcadores))
                if m is not None:
                    return crudo, m, time.perf_counter() - t0
                if time.perf_counter() - t0 > cfg.TIMEOUT_POSES_S:
                    break
        except (OSError, socket.timeout):
            pass
        return crudo, None, time.perf_counter() - t0

    def pose(self, marcador: int) -> Optional[np.ndarray]:
        """Fila (7,) del marcador, o None."""
        _crudo, m, _lat = self.consultar([marcador])
        return None if m is None else m[0]

    def cerrar(self) -> None:
        try:
            self._sock.sendall(b"EXIT")
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass


class ClienteRueda:
    """Comando de ruedas a UN robot, con parada garantizada al cerrar."""

    def __init__(self, id_robot: int) -> None:
        self.id_robot = int(id_robot)
        host, puerto = cfg.endpoint_robot(self.id_robot)
        self.host, self.puerto = host, puerto
        self._sock = socket.create_connection((host, puerto),
                                              timeout=cfg.TIMEOUT_CONEXION_S)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.ultimo_pico_rpm: float = 0.0

    def enviar(self, v: float, omega: float) -> Tuple[float, float]:
        """(v, ω) → RPM (izquierda, derecha), enviadas y devueltas."""
        rpm_izq, rpm_der, _sat = accion_a_rpm(
            v, omega, cfg.RADIO_RUEDA_M, cfg.MEDIO_EJE_M
        )
        self.ultimo_pico_rpm = max(abs(rpm_izq), abs(rpm_der))
        self._sock.sendall(codificar_velocidades_rueda(rpm_izq, rpm_der))
        return rpm_izq, rpm_der

    def detener(self) -> bool:
        """Freno. No lanza: se invoca desde `finally` y desde `atexit`."""
        try:
            self._sock.sendall(codificar_velocidades_rueda(0.0, 0.0))
            return True
        except OSError as exc:
            print(f"[robot {self.id_robot}] ⚠ NO SE PUDO FRENAR: {exc}")
            print("  CORTAR ALIMENTACIÓN A MANO.")
            return False

    def cerrar(self) -> None:
        self.detener()
        try:
            self._sock.close()
        except OSError:
            pass


# =============================================================================
# CONTEXTO
# =============================================================================

def stream_congelado(poses: "ClientePosesCrudo", marcador: int,
                     n: int = 15, pausa_s: float = 0.05,
                     ) -> Tuple[bool, int, int]:
    """
    ¿El servidor está entregando datos VIVOS, o repitiendo la última pose?

    ⚠ HALLAZGO (2026-08-29): cuando Motive deja de transmitir, el servidor
    del Robotat NO avisa: sigue contestando la última pose conocida, para
    siempre. Esa respuesta es estructuralmente perfecta —cuaternión
    unitario, posición en rango, parsea— así que `pose_es_valida` la
    acepta, y la defensa de antigüedad tampoco la ve, porque mide desde que
    NOSOTROS recibimos el dato, no desde que el mocap lo produjo.

    Pasó dos veces en el laboratorio y arruinó dos corridas de la etapa 5
    sin que nada se quejara: 363 y 366 lecturas con UN SOLO valor distinto
    a lo largo de 20 s, interpretadas como "la oclusión no cambia nada".

    Cómo se detecta: un marcador realmente trackeado jitterea en los
    últimos decimales aunque el robot esté quieto —es ruido de captura, no
    movimiento—. Se midieron 12 valores distintos en 12 lecturas con el
    robot inmóvil. Cero variación en decenas de lecturas es la firma
    inequívoca de un stream detenido.

    Retorna
    -------
    (congelado, valores_distintos, lecturas_utiles)
    """
    # El simulador local es IDEAL: sin ruido de captura, un robot quieto
    # devuelve exactamente la misma pose, que es justo la firma que acá se
    # busca. La detección apunta a un modo de falla del hardware real que el
    # simulador no tiene, así que ahí no aplica —si no, toda etapa simulada
    # con el robot detenido daría "congelado". `stream_congelado` se prueba
    # por separado con datos sintéticos.
    if cfg.SIMULADOR_ACTIVO:
        return False, n, n

    vistos = set()
    utiles = 0
    for _ in range(n):
        _crudo, m, _lat = poses.consultar([marcador])
        if m is not None:
            vistos.add(tuple(float(v) for v in m[0]))
            utiles += 1
        time.sleep(pausa_s)
    # Sin lecturas no se puede afirmar nada: eso es otro problema, no éste.
    congelado = utiles >= 5 and len(vistos) <= 1
    return congelado, len(vistos), utiles


def exigir_stream_vivo(ctx: "Contexto", etapa: int) -> Optional["ResultadoEtapa"]:
    """
    Corta la etapa si el mocap no está transmitiendo. Devuelve el
    `ResultadoEtapa` de fallo, o None si todo está bien.
    """
    if ctx.poses is None:
        # No es un error del laboratorio: es que alguien llamó a esto sin
        # conectar. Se dice así, en vez de reventar con un AttributeError
        # sobre None a mitad de una sesión.
        return ResultadoEtapa(etapa, "FALLO",
                              "cliente de poses sin conectar (error interno: "
                              "falta ctx.conectar() antes del chequeo)")
    congelado, distintos, utiles = stream_congelado(ctx.poses, ctx.marcador)
    if not utiles:
        return ResultadoEtapa(etapa, "FALLO",
                              "el servidor no entregó ninguna pose")
    if congelado:
        print(f"  ✘ STREAM CONGELADO: {utiles} lecturas del marcador "
              f"{ctx.marcador} devolvieron SIEMPRE el mismo valor.")
        print("    El servidor está repitiendo la última pose conocida: "
              "Motive dejó de transmitir.")
        print("    Revisá que la captura esté corriendo en Motive. Los "
              "datos de esta etapa no servirían.")
        return ResultadoEtapa(etapa, "FALLO",
                              "stream congelado (Motive no transmite)")
    return None


@dataclass
class ResultadoEtapa:
    """Veredicto y datos de una etapa."""
    etapa:     int
    veredicto: str                  # OK | ADVERTENCIA | FALLO | OMITIDA
    detalle:   str = ""
    mediciones: Dict[str, Any] = field(default_factory=dict)
    salidas:   List[Path] = field(default_factory=list)

    @property
    def paso(self) -> bool:
        return self.veredicto in ("OK", "ADVERTENCIA")


@dataclass
class Contexto:
    """Estado compartido por las etapas de una sesión."""
    sesion:    str
    id_robot:  int
    marcador:  int
    forzar:    bool = False
    simulador: bool = False
    poses:     Optional[ClientePosesCrudo] = None
    rueda:     Optional[ClienteRueda] = None
    #: inyectable para las pruebas; en el laboratorio es `input`
    preguntar: Callable[[str], str] = input
    #: candidatos explícitos para la etapa 1 (`--candidatos`); None = default
    candidatos_marcador: Optional[List[int]] = None
    #: puntos que mide la etapa 2 (`--puntos`). Con 2 el residuo RMS es 0 por
    #: construcción y NO valida nada: cualquier par de puntos, bien o mal
    #: medidos, produce una similitud exacta. Con 3 el residuo sí delata una
    #: medición inconsistente. Pasó en el laboratorio dos veces seguidas
    #: (escalas 0.4168 y 1.1341, ambas de datos malos, ambas con RMS 0).
    puntos_marco: int = 2

    def conectar(self) -> None:
        """
        Abre los clientes si no están abiertos. Idempotente.

        Existe porque `--etapa N` con N > 0 corre una etapa suelta sin haber
        pasado por la 0, que es donde se abrían las conexiones. Sin esto,
        repetir una etapa —que es un caso de uso explícito— fallaba con un
        `AttributeError` sobre None en vez de conectarse.

        Un fallo de conexión sale como `ConexionImposible` con un
        diagnóstico accionable, no como un traceback: en el laboratorio,
        una pila de llamadas de `socket.py` no le dice a nadie qué hacer.
        """
        if self.poses is None:
            host, puerto = cfg.endpoint_poses()
            try:
                self.poses = ClientePosesCrudo()
            except OSError as exc:
                raise ConexionImposible(
                    _diagnostico_conexion("servidor de poses", host, puerto,
                                          exc)
                ) from None
        if self.rueda is None:
            host, puerto = cfg.endpoint_robot(self.id_robot)
            try:
                self.rueda = ClienteRueda(self.id_robot)
            except OSError as exc:
                raise ConexionImposible(
                    _diagnostico_conexion(f"robot {self.id_robot}",
                                          host, puerto, exc)
                ) from None

    def detener_todo(self) -> None:
        """Freno incondicional. Idempotente, no lanza."""
        if self.rueda is not None:
            self.rueda.detener()

    def cerrar(self) -> None:
        if self.rueda is not None:
            self.rueda.cerrar()
            self.rueda = None
        if self.poses is not None:
            self.poses.cerrar()
            self.poses = None

    def leer_float(self, mensaje: str) -> float:
        """Lee un número del operador, reintentando hasta que sea válido."""
        while True:
            texto = self.preguntar(mensaje).strip().replace(",", ".")
            try:
                return float(texto)
            except ValueError:
                print("  (no es un número; probá de nuevo)")

    def esperar_enter(self, mensaje: str) -> None:
        self.preguntar(f"{mensaje} [Enter para seguir] ")


def banner(etapa: int, titulo: str, minutos: int) -> None:
    print()
    print("=" * 72)
    print(f"ETAPA {etapa} — {titulo}   (~{minutos} min)")
    print("=" * 72)


# =============================================================================
# ETAPA 0 — CONEXIÓN Y PARADA
# =============================================================================

def etapa_0(ctx: Contexto) -> ResultadoEtapa:
    banner(0, "CONEXIÓN Y PARADA", 5)
    print("Conectando al servidor de poses y a UN robot. Nada más corre si")
    print("esta etapa no da OK.")

    problemas: List[str] = []

    ctx.conectar()
    print(f"  poses  : {ctx.poses.host}:{ctx.poses.puerto}  OK")
    print(f"  robot {ctx.id_robot}: {ctx.rueda.host}:{ctx.rueda.puerto}  OK")

    # ── Validación de poses ──────────────────────────────────────────────
    filas: List[Dict[str, Any]] = []
    validas = 0
    total_descartado = 0
    for k in range(20):
        crudo, m, lat = ctx.poses.consultar([ctx.marcador])
        descarte = ctx.poses.ultimo_descarte
        total_descartado += descarte
        if m is None:
            problemas.append(f"consulta {k}: respuesta no parseable "
                             f"({len(crudo)} B)"
                             + (f", {descarte} B descartados del buffer "
                                f"antes de mandar" if descarte else ""))
            filas.append({"i": k, "latencia_ms": lat * 1e3, "valida": 0,
                          "motivo": "no parseable", "bytes": len(crudo),
                          "descarte_previo_bytes": descarte,
                          "crudo_hex": crudo[:120].hex()})
            continue
        ok, motivo = pose_es_valida(m[0])
        validas += int(ok)
        if not ok:
            problemas.append(f"consulta {k}: pose inválida ({motivo})")
        q = m[0][3:7]
        filas.append({
            "i": k, "latencia_ms": lat * 1e3, "valida": int(ok),
            "motivo": motivo,
            "x": m[0][0], "y": m[0][1], "z": m[0][2],
            "qw": q[0], "qx": q[1], "qy": q[2], "qz": q[3],
            "norma_q": float(np.linalg.norm(q)),
            "descarte_previo_bytes": descarte,
        })
        time.sleep(0.02)

    if total_descartado:
        print(f"  ⚠ se descartaron {total_descartado} B de buffer previo "
              f"en total (ver hallazgo de laboratorio 2026-08-21 en "
              f"adaptadores_robotat.py)")

    salida = ruta_salida(ctx.sesion, 0, "conexion")
    escribir_csv(salida, filas)
    print(f"  poses válidas: {validas}/20")

    # Las 20 poses pueden ser todas "válidas" y aun así ser la MISMA pose
    # repetida, si Motive dejó de transmitir. La etapa 0 es la compuerta de
    # toda la secuencia: dejar pasar un stream muerto acá contamina todo lo
    # que venga después. Ver `stream_congelado`.
    # (No aplica al simulador: es ideal y sin ruido. Ver `stream_congelado`.)
    valores_distintos = len({
        (f["x"], f["y"], f["z"], f["qw"], f["qx"], f["qy"], f["qz"])
        for f in filas if f.get("valida")
    })
    if (not cfg.SIMULADOR_ACTIVO) and validas >= 5 and valores_distintos <= 1:
        print(f"  ✘ STREAM CONGELADO: las {validas} poses válidas son "
              f"IDÉNTICAS entre sí.")
        print("    El servidor repite la última pose conocida — Motive no "
              "está transmitiendo.")
        problemas.append("stream congelado (Motive no transmite)")

    # ── Parada ───────────────────────────────────────────────────────────
    freno_ok = ctx.rueda.detener()
    print(f"  force_stop: {'OK' if freno_ok else 'FALLÓ'}")
    if not freno_ok:
        problemas.append("force_stop falló")

    if validas < 18 or problemas:
        for p in problemas[:8]:
            print(f"    ✘ {p}")
        return ResultadoEtapa(0, "FALLO",
                              f"{validas}/20 poses válidas, "
                              f"{len(problemas)} problemas",
                              salidas=[salida])

    print("✔ Conexión y parada verificadas.")
    return ResultadoEtapa(0, "OK", f"{validas}/20 poses válidas",
                          mediciones={"id_robot": ctx.id_robot},
                          salidas=[salida])


# =============================================================================
# ETAPA 1 — CORRESPONDENCIA DE IDENTIFICADORES
# =============================================================================

def _candidatos_por_defecto(ctx: Contexto) -> List[int]:
    """
    Rango de marcadores a escanear cuando no se pasa `--candidatos`.

    ⚠ NO HAY CONVENCIÓN que descubrir. Confirmado por el operador
    (2026-08-21): los marcadores son pegatinas reflectantes que se colocan a
    mano y NUNCA conservan su posición — se pueden mover entre robots o
    remontar en cualquier momento. Que en una sesión el robot 2 haya dado
    marcador 2 fue el resultado de ESA colocación física en ESE momento, no
    evidencia de una regla general (`id_marcador = id_robot` o cualquier
    otra) que vaya a repetirse con otro robot o en otra sesión. Cada robot
    se mide por separado, siempre.

    Esta lista es sólo un conjunto de candidatos BARATOS de probar primero
    —no hipótesis a confirmar—: el rango de `marker_offsets` del lab
    (índices 1–10), el marcador de meta (71, por si la constelación se
    confundió con él), `id_robot` e `id_robot+1` (por si acaso, sin
    suponer que generalicen), y lo que se haya pasado por `--marcador`. El
    escaneo cubre igual de bien un acierto que un tiro al aire: encuentra
    lo que realmente giró, no lo que se esperaba que girara.
    """
    candidatos = set(range(1, 13)) | {71}
    if 1 <= ctx.marcador <= 100:
        candidatos.add(ctx.marcador)
    for c in (ctx.id_robot, ctx.id_robot + 1):     # candidatos baratos, no hipótesis
        if 1 <= c <= 100:
            candidatos.add(c)
    return sorted(candidatos)


def etapa_1(ctx: Contexto,
           candidatos: Optional[List[int]] = None) -> ResultadoEtapa:
    banner(1, "CORRESPONDENCIA marcador ↔ robot", 5)
    print(f"El robot {ctx.id_robot} va a girar SOBRE SU EJE ~1.2 s, UNA vez.")
    print("Se escanean varios marcadores candidatos EN ESE MISMO giro —no")
    print("hace falta saber de antemano cuál es el correcto.")

    from verificar_mapeo_ids import escanear_candidatos, informe_escaneo

    lista = (candidatos if candidatos is not None
             else ctx.candidatos_marcador if ctx.candidatos_marcador
             else _candidatos_por_defecto(ctx))
    ctx.detener_todo()
    ctx.cerrar()                      # el escaneo abre sus propios sockets
    try:
        giros = escanear_candidatos(ctx.id_robot, lista, verboso=True)
        movido = informe_escaneo(ctx.id_robot, giros, esperado=ctx.marcador)
    finally:
        ctx.poses = ClientePosesCrudo()
        ctx.rueda = ClienteRueda(ctx.id_robot)
        ctx.detener_todo()

    sin_lectura = [c for c, d in giros.items() if d is None]
    if sin_lectura:
        print(f"  (sin lectura: {sin_lectura} — no es necesariamente un "
              f"problema, puede que esos IDs no existan en la constelación)")

    if movido is None:
        movidos_multiples = [c for c, d in giros.items()
                             if d is not None and d > 0.30]
        veredicto = "AMBIGUO" if len(movidos_multiples) > 1 else "NADIE"
        return ResultadoEtapa(1, "FALLO", f"veredicto {veredicto}")

    if movido == ctx.marcador:
        return ResultadoEtapa(
            1, "OK", f"robot {ctx.id_robot} ↔ marcador {movido}",
            mediciones={"id_robot": ctx.id_robot, "id_marcador": int(movido),
                        "id_marcador_para_robot": ctx.id_robot},
        )
    print(f"  ⚠ el robot {ctx.id_robot} mueve el marcador {movido}, no el "
          f"{ctx.marcador} que se venía probando.")
    print("  Se ADOPTA el marcador observado: es el dato medido.")
    return ResultadoEtapa(
        1, "ADVERTENCIA", f"marcador corregido {ctx.marcador} → {movido}",
        mediciones={"id_robot": ctx.id_robot, "id_marcador": int(movido),
                    "id_marcador_para_robot": ctx.id_robot},
    )


# =============================================================================
# ETAPA 2 — MARCO Y ESCALA
# =============================================================================

def etapa_2(ctx: Contexto, n_puntos: Optional[int] = None) -> ResultadoEtapa:
    # El parámetro explícito manda (lo usan las pruebas); si no, lo dice el
    # contexto, que es por donde entra `--puntos`.
    if n_puntos is None:
        n_puntos = ctx.puntos_marco
    banner(2, "MARCO Y ESCALA", 10)
    print("Con el robot QUIETO en posiciones que vos medís con cinta.")
    print()
    print(f"  El env es un cuadrado de {cfg.ARENA_WX_M} × {cfg.ARENA_WY_M} m, "
          f"y el área útil del")
    print(f"  Robotat es MÁS GRANDE ({cfg.AREA_UTIL_X_M} × "
          f"{cfg.AREA_UTIL_Y_M} m, sin los bordes).")
    print(f"  NO se comprime una en la otra: se elige un CUADRADO DE "
          f"{cfg.ARENA_WX_M} × {cfg.ARENA_WY_M} m")
    print("  DENTRO del área útil y se trabaja sólo ahí, 1:1 en metros.")
    print("  (Comprimir encogería el env pero NO al robot: los márgenes de")
    print("   choque de la política quedarían mintiendo. Ver README §C1.)")
    print()
    print("  Elegí una esquina de ESE cuadrado como origen, marcala, y medí")
    print("  con cinta desde ahí, en METROS FÍSICOS, con x e y hacia adentro.")
    print(f"  Las dos coordenadas caen entre 0 y {cfg.ARENA_WX_M:.1f}.")
    print(f"  La escala esperada es 1.0: si sale otra cosa, algo no cuadra.")
    print()
    print(f"Se piden {n_puntos} posiciones (dos alcanzan para fijar escala,")
    print("rotación y traslación; una tercera da residuo, que sí valida).")

    medidos: List[np.ndarray] = []
    reales:  List[np.ndarray] = []
    filas: List[Dict[str, Any]] = []
    sospecha_mm = False

    for k in range(n_puntos):
        ctx.esperar_enter(f"\n  Punto {k+1}/{n_puntos}: poné el robot y medí.")
        muestras = []
        invalidas = 0
        crudas_completas = []
        for _ in range(10):
            p = ctx.poses.pose(ctx.marcador)
            if p is not None:
                # ⚠ HALLAZGO (2026-09-02): esta etapa NO validaba las poses,
                # a diferencia de la 0. Con el marcador congelado aceptó dos
                # puntos con la MISMA pose —la última conocida, tomada con el
                # robot en la mano a 47.6 cm de altura— y los habría metido
                # en el ajuste como si fueran dos posiciones distintas. Un
                # punto malo acá contamina TODA la calibración.
                # Sólo el PLACEHOLDER, no la validez completa: esta etapa
                # detecta a propósito magnitudes enormes (servidor en
                # milímetros) y `pose_es_valida` las rechazaría, tapando ese
                # diagnóstico. Ver `es_placeholder_no_trackeado`.
                if es_placeholder_no_trackeado(p):
                    invalidas += 1
                    continue
                muestras.append(p[:3])
                crudas_completas.append(tuple(float(v) for v in p))
            time.sleep(0.02)
        if len(muestras) < 5:
            detalle = (f"sólo {len(muestras)}/10 poses válidas en el "
                       f"punto {k+1}")
            if invalidas:
                detalle += (f" ({invalidas} inválidas: el marcador "
                            f"{ctx.marcador} no está trackeado)")
            return ResultadoEtapa(2, "FALLO", detalle)

        # Stream congelado: 10 lecturas idénticas. Un marcador trackeado
        # jitterea aunque el robot esté quieto (ver `stream_congelado`).
        if not cfg.SIMULADOR_ACTIVO and len(set(crudas_completas)) <= 1:
            # Medido el 2026-09-03: un marcador trackeado actualiza a ~82 Hz,
            # así que en esta ventana de 0.2 s da 10 valores distintos de 10.
            # Diez idénticos es tracking perdido, no muestreo corto.
            #
            # La causa más común acá NO es que Motive se haya caído, sino que
            # el punto elegido quede FUERA DEL VOLUMEN DE CAPTURA: esta etapa
            # invita a medir en las esquinas, que son justo los extremos.
            # Decirlo importa, porque el mensaje anterior mandaba a revisar
            # Motive cuando alcanzaba con correr el punto unos centímetros.
            return ResultadoEtapa(
                2, "FALLO",
                f"sin tracking en el punto {k+1}: las 10 lecturas del "
                f"marcador {ctx.marcador} son idénticas (un marcador vivo "
                f"cambia a ~82 Hz). Lo más probable es que este punto quede "
                f"fuera del volumen de captura — probá 20-30 cm más adentro. "
                f"Si falla en todos lados, ahí sí revisá Motive.")

        crudo = np.median(np.asarray(muestras), axis=0)

        # ¿Este punto está en el MISMO lugar que uno anterior? Con el stream
        # congelado la pose no cambia aunque el robot sí se haya movido, y
        # así se registran dos esquinas distintas con la misma coordenada.
        for j, previo in enumerate(medidos):
            if float(np.linalg.norm(crudo[:2] - previo)) < 0.005:
                return ResultadoEtapa(
                    2, "FALLO",
                    f"el punto {k+1} da la MISMA pose que el punto {j+1} "
                    f"({crudo[0]:+.4f}, {crudo[1]:+.4f}): o no se movió el "
                    f"robot, o el marcador perdió el tracking y el servidor "
                    f"repite la pose vieja. No se puede calibrar así.")
        magnitud = float(np.max(np.abs(crudo[:2])))
        if magnitud > 100.0:
            sospecha_mm = True
        env_actual = lab_a_env(float(crudo[0]), float(crudo[1]), 0.0)

        print(f"    pose CRUDA del servidor : x={crudo[0]:+10.4f}  "
              f"y={crudo[1]:+10.4f}  z={crudo[2]:+10.4f}")
        print(f"    con la calibración actual: x={env_actual[0]:+8.4f}  "
              f"y={env_actual[1]:+8.4f}  (marco del env)")
        if magnitud > 100.0:
            print(f"    ⚠ magnitud {magnitud:.1f}: el servidor parece "
                  f"entregar MILÍMETROS, no metros.")

        x_real = ctx.leer_float("    x real medida [m]: ")
        y_real = ctx.leer_float("    y real medida [m]: ")
        medidos.append(crudo[:2])
        reales.append(np.array([x_real, y_real]))
        filas.append({
            "punto": k + 1,
            "crudo_x": crudo[0], "crudo_y": crudo[1], "crudo_z": crudo[2],
            "env_actual_x": env_actual[0], "env_actual_y": env_actual[1],
            "real_x": x_real, "real_y": y_real,
            "magnitud_cruda": magnitud,
        })

    escala, rot, tras, rms = ajustar_similitud(np.array(medidos),
                                               np.array(reales))
    salida = ruta_salida(ctx.sesion, 2, "marco")
    escribir_csv(salida, filas)

    print()
    print(f"  escala propuesta    : {escala:.6f}"
          + ("   (≈ milímetros → metros)" if escala < 0.01 else ""))
    print(f"  rotación propuesta  : {math.degrees(rot):+.3f}°")
    print(f"  traslación propuesta: ({tras[0]:+.4f}, {tras[1]:+.4f}) m")
    if n_puntos >= 3:
        print(f"  residuo RMS         : {rms*1000:.1f} mm")
    else:
        print("  residuo RMS         : 0 por construcción (2 puntos); "
              "no valida nada")

    avisos: List[str] = []

    # Todos los puntos deben tomarse con el robot APOYADO EN EL PISO. Si uno
    # se mide con el robot en la mano, su z se dispara y el centroide del
    # marcador se corre horizontalmente al inclinarlo: la escala sale mal sin
    # que nada más lo delate, porque con 2 puntos el residuo es 0 igual.
    # Pasó en el laboratorio (2026-08-28): z de 0.2326 y 0.0610 m —17 cm de
    # diferencia— dieron escala 1.1341 con RMS 0. Se avisa a partir de 5 cm,
    # bastante más que el desnivel de un piso pero mucho menos que una mano.
    # ── ¿los puntos están bien repartidos? ───────────────────────────────
    # Con los puntos casi ALINEADOS la similitud queda mal condicionada: la
    # rotación se apoya casi entera en el único punto fuera de la recta, y el
    # residuo puede verse chico igual porque mide el AJUSTE, no el
    # condicionamiento.
    #
    # Se mide con los valores singulares de los puntos REALES centrados: el
    # cociente σ₂/σ₁ vale 1 para las cuatro esquinas de un cuadrado y tiende
    # a 0 cuando se alinean. Con dos puntos no aplica: dos puntos siempre
    # están alineados, y ese caso ya lo cubre el aviso de "residuo 0 por
    # construcción".
    #
    # ALCANCE, para no confiarse: esto detecta degeneración GEOMÉTRICA, no
    # mala cobertura. La corrida del 2026-08-28 tenía tres de sus cuatro
    # puntos sobre un mismo borde y da σ₂/σ₁ = 0.41 — no la habría marcado,
    # y revisándola, tampoco estaba mal condicionada: el cuarto punto caía a
    # 1.5 m de esa recta. Su problema era estar los cuatro sobre el borde,
    # cubriendo media arena, que es otra cosa y no se detecta así. El umbral
    # 0.15 marca alineación de verdad (tres en fila con uno a 10 cm da 0.06).
    if n_puntos >= 3:
        p = np.array(reales, dtype=np.float64)
        sv = np.linalg.svd(p - p.mean(axis=0), compute_uv=False)
        razon = float(sv[1] / sv[0]) if sv[0] > 0 else 0.0
        if razon < 0.15:
            avisos.append(
                f"los {n_puntos} puntos están casi ALINEADOS (σ₂/σ₁ = "
                f"{razon:.3f}): la rotación queda mal condicionada. "
                f"Repartilos en dos dimensiones —las cuatro esquinas del "
                f"cuadrado es lo ideal")

    zs = [f["crudo_z"] for f in filas]
    dispersion_z = float(max(zs) - min(zs))
    if dispersion_z > 0.05:
        avisos.append(
            f"las alturas z difieren {dispersion_z*100:.0f} cm entre puntos "
            f"({min(zs):.3f}…{max(zs):.3f} m): ¿algún punto se midió con el "
            f"robot levantado? Todos deben estar apoyados en el piso"
        )

    if sospecha_mm and escala > 0.01:
        avisos.append("magnitudes de milímetros pero escala ≈ 1")
    if abs(escala - 1.0) > 0.02 and abs(escala - 0.001) > 0.0002:
        avisos.append(f"escala {escala:.4f} no es ni 1 ni 0.001")
    if n_puntos >= 3 and rms > 0.05:
        avisos.append(f"residuo {rms*1000:.0f} mm: la similitud no alcanza")

    mediciones = {
        "escala_posicion":    float(escala),
        "rotacion_marco_rad": float(rot),
        "traslacion_x_m":     float(tras[0]),
        "traslacion_y_m":     float(tras[1]),
    }
    if avisos:
        for a in avisos:
            print(f"  ⚠ {a}")
        return ResultadoEtapa(2, "ADVERTENCIA", "; ".join(avisos),
                              mediciones=mediciones, salidas=[salida])
    print("✔ Marco y escala determinados.")
    return ResultadoEtapa(2, "OK", f"escala {escala:.4f}, "
                          f"rot {math.degrees(rot):+.2f}°",
                          mediciones=mediciones, salidas=[salida])


# =============================================================================
# ETAPA 3 — RUMBO
# =============================================================================

def etapa_3(ctx: Contexto, v_prueba: float = 0.05,
            duracion_s: float = 3.0) -> ResultadoEtapa:
    banner(3, "OFFSET DE RUMBO", 10)
    print(f"Avance rectilíneo a {v_prueba} m/s durante {duracion_s:.0f} s "
          f"(≈ {v_prueba*duracion_s*100:.0f} cm).")
    print("Dejá espacio libre POR DELANTE del robot.")
    ctx.esperar_enter("  Listo?")

    muestras: List[Dict[str, Any]] = []
    invalidas = 0
    t0 = time.perf_counter()
    try:
        ctx.rueda.enviar(v_prueba, 0.0)
        while time.perf_counter() - t0 < duracion_s:
            p = ctx.poses.pose(ctx.marcador)
            if p is not None:
                # ⚠ HALLAZGO (2026-09-01): esta etapa NO validaba las poses,
                # a diferencia de la 0. Con el marcador 10 sin trackear, las
                # 104 muestras fueron el placeholder de ceros y la etapa
                # concluyó «el robot recorrió 0 mm: no se mueve». El robot
                # SÍ se movió —el operador lo vio girar— y la que estaba
                # ciega era la medición. Un diagnóstico equivocado manda a
                # revisar el hardware equivocado, que es peor que no dar
                # ninguno.
                ok, _motivo = pose_es_valida(p)
                if not ok:
                    invalidas += 1
                else:
                    yaw, incl = heading_desde_cuaternion(
                        float(p[3]), float(p[4]), float(p[5]), float(p[6])
                    )
                    muestras.append({
                        "t_s": time.perf_counter() - t0,
                        "x": float(p[0]), "y": float(p[1]),
                        "yaw_rad": yaw, "inclinacion_rad": incl,
                    })
            time.sleep(0.02)
    finally:
        ctx.detener_todo()

    if invalidas and len(muestras) < 20:
        return ResultadoEtapa(
            3, "FALLO",
            f"el marcador {ctx.marcador} no está trackeado: {invalidas} "
            f"lecturas inválidas y sólo {len(muestras)} útiles. NO es que el "
            f"robot no se mueva — no lo estamos viendo. Revisá Motive.")

    if len(muestras) < 20:
        return ResultadoEtapa(3, "FALLO",
                              f"sólo {len(muestras)} muestras")

    # Poses válidas pero todas iguales: el stream está congelado. Mismo
    # razonamiento que arriba — el robot puede estar moviéndose igual.
    #
    # No aplica al simulador: es ideal y sin ruido de captura, así que un
    # robot REALMENTE detenido le da poses idénticas de forma legítima. Ahí
    # el diagnóstico correcto es «no se mueve», que es lo que comprueba
    # `PruebaEtapa3RobotInmovil`. Contra hardware real un marcador trackeado
    # siempre jitterea, aunque el robot esté quieto.
    if (not cfg.SIMULADOR_ACTIVO
            and len({(m["x"], m["y"], m["yaw_rad"]) for m in muestras}) <= 1):
        return ResultadoEtapa(
            3, "FALLO",
            f"stream congelado: las {len(muestras)} poses son idénticas. "
            f"El robot puede estar moviéndose igual; no lo estamos viendo.")

    p0 = np.array([muestras[0]["x"], muestras[0]["y"]])
    p1 = np.array([muestras[-1]["x"], muestras[-1]["y"]])
    desplazamiento = p1 - p0
    recorrido = float(np.linalg.norm(desplazamiento)) * cfg.ESCALA_POSICION

    salida = ruta_salida(ctx.sesion, 3, "rumbo")
    escribir_csv(salida, muestras)

    if recorrido < 0.02:
        return ResultadoEtapa(3, "FALLO",
                              f"el robot recorrió {recorrido*1000:.0f} mm: "
                              f"no se mueve o la escala está mal",
                              salidas=[salida])

    # Todo en el marco del LABORATORIO: así el offset de rumbo sale
    # independiente de la rotación de marco de la etapa 2.
    alfa = math.atan2(float(desplazamiento[1]), float(desplazamiento[0]))
    yaw_medio = math.atan2(
        float(np.mean([math.sin(m["yaw_rad"]) for m in muestras])),
        float(np.mean([math.cos(m["yaw_rad"]) for m in muestras])),
    )
    offset = envolver(alfa - yaw_medio)

    dispersion = float(np.std([
        envolver(m["yaw_rad"] - yaw_medio) for m in muestras
    ]))

    print()
    print(f"  recorrido neto        : {recorrido*100:.1f} cm")
    print(f"  dirección de avance α : {math.degrees(alfa):+8.2f}°  (lab)")
    print(f"  rumbo reportado medio : {math.degrees(yaw_medio):+8.2f}°  (lab)")
    print(f"  OFFSET propuesto      : {math.degrees(offset):+8.2f}°")
    print(f"  dispersión del rumbo  : {math.degrees(dispersion):.2f}°")

    # Contraste con la tabla del laboratorio.
    ref = OFFSETS_LAB_DEG.get(ctx.id_robot)
    if ref is None:
        print(f"  tabla del lab         : sin entrada para el robot "
              f"{ctx.id_robot} (marker_offsets cubre 1–10)")
    else:
        # laboratorio11.m hace theta = wrap(yaw - offset_lab), o sea que su
        # offset es el NEGATIVO del nuestro.
        esperado = -math.radians(ref)
        diferencia = abs(math.degrees(envolver(offset - esperado)))
        print(f"  tabla del lab         : marker_offsets[{ctx.id_robot}] = "
              f"{ref:+.4f}°  ⇒ equivalente al nuestro "
              f"{math.degrees(esperado):+.2f}°")
        print(f"  diferencia            : {diferencia:.2f}°")

    mediciones = {"offset_heading_rad": float(offset)}
    if dispersion > math.radians(15.0):
        return ResultadoEtapa(3, "ADVERTENCIA",
                              f"rumbo disperso ({math.degrees(dispersion):.1f}°): "
                              f"el avance no fue recto",
                              mediciones=mediciones, salidas=[salida])
    print("✔ Offset de rumbo determinado.")
    return ResultadoEtapa(3, "OK", f"offset {math.degrees(offset):+.2f}°",
                          mediciones=mediciones, salidas=[salida])


# =============================================================================
# ETAPA 4 — LATENCIAS
# =============================================================================

def etapa_4(ctx: Contexto, n_consultas: int = 200,
            repeticiones: int = 5) -> ResultadoEtapa:
    banner(4, "LATENCIAS", 10)

    # ── 4a: percepción ───────────────────────────────────────────────────
    print(f"4a — percepción: {n_consultas} consultas con el robot QUIETO.")
    ctx.detener_todo()
    latencias: List[float] = []
    fallos = 0
    t0 = time.perf_counter()
    for _ in range(n_consultas):
        _crudo, m, lat = ctx.poses.consultar([ctx.marcador])
        if m is None:
            fallos += 1
        latencias.append(lat)
    duracion = time.perf_counter() - t0

    lat = np.asarray(latencias)
    frecuencia = n_consultas / duracion
    p50, p95 = float(np.percentile(lat, 50)), float(np.percentile(lat, 95))
    print(f"    frecuencia sostenida : {frecuencia:7.1f} Hz")
    print(f"    tiempo de respuesta  : media {lat.mean()*1e3:6.2f} ms · "
          f"p50 {p50*1e3:6.2f} · p95 {p95*1e3:6.2f} · "
          f"máx {lat.max()*1e3:6.2f}")
    print(f"    consultas fallidas   : {fallos}/{n_consultas}")

    # ── El número que decide si "consultar una vez por decisión" (2026-08-22)
    # se sostiene: el lazo tiene 100 ms (PERIODO_DECISION_S) para consultar
    # + transformar + inferir + filtrar + enviar. El p95, no la media, es el
    # que importa: la media puede verse bien con una cola larga ocasional
    # que igual empuja alguna decisión fuera de presupuesto.
    fraccion_p95 = p95 / PERIODO_DECISION_S
    if fraccion_p95 < UMBRAL_PRESUPUESTO_HOLGADO:
        presupuesto_riesgoso = False
        veredicto_presupuesto = (
            f"✔ p95 = {fraccion_p95:.0%} del presupuesto de decisión "
            f"({PERIODO_DECISION_S*1e3:.0f} ms) — margen amplio."
        )
    elif fraccion_p95 < UMBRAL_PRESUPUESTO_RIESGOSO:
        presupuesto_riesgoso = False
        veredicto_presupuesto = (
            f"⚠ p95 = {fraccion_p95:.0%} del presupuesto de decisión — "
            f"aceptable, pero vigilar en la sesión de política (punto 4)."
        )
    else:
        presupuesto_riesgoso = True
        veredicto_presupuesto = (
            f"✘ p95 = {fraccion_p95:.0%} del presupuesto de decisión — "
            f"RIESGOSO. La consulta síncrona dentro del lazo puede no "
            f"sostenerse. NO volver a 100 Hz: considerar el plan de "
            f"contingencia (hilo de sondeo en segundo plano, caché sin "
            f"bloquear) — ver README_ROBOTAT.md."
        )
    print(f"    {veredicto_presupuesto}")

    filas_a = [{"i": i, "latencia_ms": l * 1e3} for i, l in enumerate(latencias)]
    salida_a = ruta_salida(ctx.sesion, 4, "latencia-percepcion")
    escribir_csv(salida_a, filas_a)

    # ── 4b: actuación ────────────────────────────────────────────────────
    v_paso = 0.05
    umbral_m = 0.003
    # Tiempo puramente geométrico en recorrer el umbral a la velocidad del
    # escalón: si no se descuenta, se reporta como latencia algo que es sólo
    # el tamaño del umbral.
    t_geometrico = umbral_m / v_paso
    print()
    print(f"4b — actuación: {repeticiones} escalones de {v_paso} m/s, "
          f"umbral de detección {umbral_m*1000:.0f} mm.")
    print(f"    se descuentan la latencia de percepción (p50 = "
          f"{p50*1e3:.1f} ms) y el tiempo geométrico de recorrer el umbral "
          f"({t_geometrico*1e3:.0f} ms).")

    medidas_b: List[Dict[str, Any]] = []
    retardos: List[float] = []
    no_resueltos = 0
    for k in range(repeticiones):
        ctx.detener_todo()
        time.sleep(0.4)
        p_ini = ctx.poses.pose(ctx.marcador)
        if p_ini is None:
            continue
        base = np.array([p_ini[0], p_ini[1]]) * cfg.ESCALA_POSICION

        t_cmd = time.perf_counter()
        ctx.rueda.enviar(v_paso, 0.0)
        detectado: Optional[float] = None
        muestras_hasta = 0
        while time.perf_counter() - t_cmd < 2.0:
            p = ctx.poses.pose(ctx.marcador)
            muestras_hasta += 1
            if p is None:
                continue
            d = float(np.linalg.norm(
                np.array([p[0], p[1]]) * cfg.ESCALA_POSICION - base))
            if d > umbral_m:
                detectado = time.perf_counter() - t_cmd
                break
        ctx.detener_todo()
        time.sleep(0.3)

        if detectado is None:
            print(f"    rep {k+1}: no se detectó movimiento en 2 s")
            medidas_b.append({"rep": k + 1, "detectado_s": "",
                              "retardo_estimado_ms": "",
                              "resuelto": 0, "muestras": muestras_hasta})
            continue

        retardo = detectado - p50 - t_geometrico
        # Resolución temporal: no se puede afirmar un retardo más chico que
        # el período de muestreo de las poses.
        periodo = 1.0 / frecuencia
        resuelto = retardo > 2.0 * periodo
        if not resuelto:
            no_resueltos += 1
        print(f"    rep {k+1}: detección a {detectado*1e3:6.1f} ms  ⇒ "
              f"retardo estimado {retardo*1e3:+6.1f} ms"
              + ("" if resuelto else
                 f"   (POR DEBAJO DE LA RESOLUCIÓN: período "
                 f"{periodo*1e3:.1f} ms)"))
        retardos.append(retardo)
        medidas_b.append({
            "rep": k + 1, "detectado_s": detectado,
            "retardo_estimado_ms": retardo * 1e3,
            "resuelto": int(resuelto), "muestras": muestras_hasta,
            "periodo_muestreo_ms": periodo * 1e3,
        })

    salida_b = ruta_salida(ctx.sesion, 4, "latencia-actuacion")
    escribir_csv(salida_b, medidas_b)

    mediciones = {
        "latencia_percepcion_p50_s": p50,
        "latencia_percepcion_p95_s": p95,
        "frecuencia_poses_hz":       float(frecuencia),
        "presupuesto_p95_fraccion":  fraccion_p95,
    }
    print()
    if not retardos:
        return ResultadoEtapa(
            4, "ADVERTENCIA" if not presupuesto_riesgoso else "FALLO",
            "no se pudo medir el retardo de actuación"
            + (f"; además, {veredicto_presupuesto}" if presupuesto_riesgoso
               else ""),
            mediciones=mediciones, salidas=[salida_a, salida_b])
    r = np.asarray(retardos)
    mediciones["latencia_actuacion_media_s"] = float(r.mean())
    if no_resueltos >= len(retardos):
        print(f"  ⚠ el retardo de actuación (media {r.mean()*1e3:.1f} ms) "
              f"está POR DEBAJO de la resolución temporal del muestreo de "
              f"poses. NO se reporta como número medido.")
        detalle = "retardo de actuación no resoluble con este período de muestreo"
        return ResultadoEtapa(
            4, "FALLO" if presupuesto_riesgoso else "ADVERTENCIA",
            detalle + (f"; {veredicto_presupuesto}" if presupuesto_riesgoso
                       else ""),
            mediciones=mediciones, salidas=[salida_a, salida_b])
    print(f"  retardo de actuación: media {r.mean()*1e3:.1f} ms  "
          f"(σ {r.std()*1e3:.1f} ms, n={len(r)})")

    # ⚠ HALLAZGO (2026-08-29): esta etapa MEDÍA el retardo de actuación y no
    # lo juzgaba nunca — el único veredicto miraba la percepción. Una media
    # de 602.7 ms, seis veces el período de decisión, salió reportada como
    # OK. Medir sin juzgar es peor que no medir: da confianza infundada.
    #
    # Por qué importa tanto más que la percepción: una pose que llega tarde
    # se puede descartar (para eso está ANTIGUEDAD_MAX_POSE_S), pero un
    # comando que se aplica tarde YA SE APLICÓ. El robot sigue ejecutando la
    # decisión vieja mientras la política cree que corrigió. A V_MAX el
    # robot recorre 0.31 m/s · 0.6 s = 19 cm durante el retardo, más que los
    # 0.18 m de margen del CBF y que los 0.15 m de separación mínima.
    #
    # No aplica al simulador: ahí la actuación es instantánea por
    # construcción, y lo poco que se mide es ruido de muestreo y de carga de
    # la máquina. Juzgarlo produjo un fallo intermitente en la batería —bajo
    # carga, una medición pasaba de 100 ms— que no decía nada del sistema.
    fraccion_act = float(r.mean()) / PERIODO_DECISION_S
    if (not cfg.SIMULADOR_ACTIVO) and fraccion_act > UMBRAL_ACTUACION_RIESGOSO:
        avisos_act = (
            f"retardo de actuación {r.mean()*1e3:.0f} ms = "
            f"{fraccion_act:.1f}× el período de decisión "
            f"({PERIODO_DECISION_S*1e3:.0f} ms)"
        )
        print(f"  ✘ {avisos_act}.")
        print(f"    A V_MAX el robot recorre "
              f"{V_MAX_POLITICA * r.mean()*100:.0f} cm antes de que un "
              f"comando surta efecto.")
        print(f"    Antes de correr la política hay que saber si esto es la "
              f"vía de comando o el arranque mecánico del robot: repetí 4b "
              f"a una velocidad más alta. Si el retardo se desploma, es "
              f"fricción de arranque a 0.05 m/s, no la red.")
        if no_resueltos:
            print(f"    ({no_resueltos} de {repeticiones} repeticiones ni "
                  f"siquiera se movieron: el fenómeno es intermitente.)")
        return ResultadoEtapa(
            4, "FALLO", avisos_act
            + (f"; además, {veredicto_presupuesto}" if presupuesto_riesgoso
               else ""),
            mediciones=mediciones, salidas=[salida_a, salida_b])
    if presupuesto_riesgoso:
        print(f"  {veredicto_presupuesto}")
        return ResultadoEtapa(
            4, "FALLO",
            f"percepción p50 {p50*1e3:.1f} ms pero p95 = "
            f"{fraccion_p95:.0%} del presupuesto — ver plan de "
            f"contingencia",
            mediciones=mediciones, salidas=[salida_a, salida_b])
    print("✔ Latencias medidas.")
    return ResultadoEtapa(4, "OK",
                          f"percepción p50 {p50*1e3:.1f} ms, "
                          f"actuación {r.mean()*1e3:.1f} ms",
                          mediciones=mediciones,
                          salidas=[salida_a, salida_b])


# =============================================================================
# ETAPA 5 — MARCADOR OCLUIDO
# =============================================================================

def etapa_5(ctx: Contexto, duracion_s: float = 20.0) -> ResultadoEtapa:
    banner(5, "MARCADOR OCLUIDO", 5)
    print("Es la pregunta que NO se puede contestar leyendo el código de")
    print("referencia: qué devuelve el servidor cuando un marcador no está")
    print("visible. Se registran los bytes LITERALES.")
    print()
    print("  Con el robot quieto: tapá el marcador con la mano cuando se")
    print(f"  indique, y destapalo al final. Dura {duracion_s:.0f} s.")
    ctx.detener_todo()

    # Precondición: sin stream vivo esta etapa no puede concluir NADA. Su
    # veredicto se basa en detectar un CAMBIO en la respuesta, y una pose
    # congelada nunca cambia — se leería como "la oclusión no hace nada".
    # Fue exactamente el error del 2026-08-29, dos corridas seguidas.
    fallo = exigir_stream_vivo(ctx, 5)
    if fallo is not None:
        return fallo

    ctx.esperar_enter("  Listo?")

    filas: List[Dict[str, Any]] = []
    t0 = time.perf_counter()
    # Dos banderas independientes: con una sola, el aviso de destapar la
    # reseteaba y volvía a dispararse el de tapar, alternando en bucle.
    aviso_tapar = False
    aviso_destapar = False
    while time.perf_counter() - t0 < duracion_s:
        t = time.perf_counter() - t0
        if not aviso_tapar and t > duracion_s * 0.25:
            print("  >>> TAPAR EL MARCADOR AHORA <<<")
            aviso_tapar = True
        if not aviso_destapar and t > duracion_s * 0.75:
            print("  >>> DESTAPAR <<<")
            aviso_destapar = True
        crudo, m, lat = ctx.poses.consultar([ctx.marcador])
        try:
            estructura = json.loads(crudo.decode("ascii", errors="replace"))
            tipo = type(estructura).__name__
            n_val = len(estructura) if isinstance(estructura, list) else -1
            texto = json.dumps(estructura)[:200]
        except (ValueError, UnicodeDecodeError):
            tipo, n_val = "no-json", -1
            texto = crudo.decode("ascii", errors="replace")[:200]
        ok, motivo = (pose_es_valida(m[0]) if m is not None
                      else (False, "no parseable"))
        filas.append({
            "t_s": t, "latencia_ms": lat * 1e3,
            "n_bytes": len(crudo), "tipo_json": tipo, "n_valores": n_val,
            "parsea_como_pose": int(m is not None),
            "pose_valida": int(ok), "motivo": motivo,
            "crudo_hex": crudo[:80].hex(),
            "crudo_texto": texto,
        })
        time.sleep(0.05)

    salida = ruta_salida(ctx.sesion, 5, "marcador-ocluido")
    escribir_csv(salida, filas)

    tipos = {}
    for f in filas:
        clave = (f["tipo_json"], f["n_valores"], f["parsea_como_pose"])
        tipos[clave] = tipos.get(clave, 0) + 1
    print()
    print("  Respuestas observadas (tipo, nº de valores, parsea como pose):")
    for (tipo, n, parsea), cuenta in sorted(tipos.items(),
                                            key=lambda kv: -kv[1]):
        print(f"    {tipo:10s}  n={n:4d}  parsea={parsea}  ×{cuenta}")

    # ── ¿se CONGELÓ la pose? ─────────────────────────────────────────────
    # MEDIDO (2026-08-29): la respuesta real del Robotat a un marcador que
    # venía trackeado y se ocluye NO es ninguna de las tres hipótesis que
    # esta etapa buscaba. Devuelve la ÚLTIMA POSE CONOCIDA, congelada,
    # indefinidamente — con la forma correcta, cuaternión unitario y
    # posición en rango. Las 366 lecturas de la corrida dieron
    # `pose_valida=1`, y la etapa concluyó "no se observó ningún cambio",
    # que era exactamente al revés: sí pasó algo, y de lo más peligroso.
    #
    # Clasificar sólo por (tipo, nº de valores, parsea) no puede verlo: una
    # pose congelada es estructuralmente idéntica a una buena. Hay que
    # mirar los VALORES.
    racha_max, racha_ini, racha_fin = 0, 0.0, 0.0
    actual, ini = 0, 0.0
    previo: Optional[str] = None
    for f in filas:
        crudo = f.get("crudo_texto")
        if previo is not None and crudo == previo:
            actual += 1
            if actual > racha_max:
                racha_max, racha_ini, racha_fin = actual, ini, f["t_s"]
        else:
            actual, ini = 1, f["t_s"]
        previo = crudo
    dur_congelada = racha_fin - racha_ini
    # Umbral generoso: a ~18 Hz de muestreo, 2 s son ~36 lecturas idénticas.
    # Ni el ruido de captura ni un robot quieto producen eso.
    hubo_congelada = dur_congelada >= 2.0

    n_esperado = VALORES_POR_AGENTE
    hubo_corta = any(f["n_valores"] not in (-1, n_esperado) for f in filas)
    hubo_invalida = any(f["parsea_como_pose"] and not f["pose_valida"]
                        for f in filas)
    if hubo_congelada:
        print(f"  ⚠ pose CONGELADA durante {dur_congelada:.1f} s "
              f"(t={racha_ini:.2f}…{racha_fin:.2f}), {racha_max} lecturas "
              f"idénticas seguidas.")
        conclusion = (
            f"el servidor devuelve la ÚLTIMA POSE CONOCIDA congelada "
            f"({dur_congelada:.1f} s) con el marcador ocluido — estructura "
            f"válida, pasa toda validación de una sola pose. El modo 'lote' "
            f"es seguro, pero el lazo DEBE detectar el congelamiento"
        )
        print(f"  ⇒ {conclusion}")
        return ResultadoEtapa(
            5, "OK", conclusion,
            mediciones={"oclusion_respuesta": conclusion,
                        "oclusion_congela_pose": 1,
                        "oclusion_duracion_congelada_s": float(dur_congelada)},
            salidas=[salida])

    if hubo_corta:
        conclusion = ("el servidor devuelve MENOS VALORES con el marcador "
                      "ocluido ⇒ poner MODO_CONSULTA_POSES='individual'")
    elif hubo_invalida:
        conclusion = ("el servidor devuelve una pose inválida (ceros/NaN) "
                      "⇒ la validación defensiva ya lo cubre en modo 'lote'")
    else:
        conclusion = ("no se observó ningún cambio: ¿se llegó a tapar el "
                      "marcador? Repetir la etapa")
    print(f"  ⇒ {conclusion}")

    veredicto = "OK" if (hubo_corta or hubo_invalida) else "ADVERTENCIA"
    return ResultadoEtapa(5, veredicto, conclusion,
                          mediciones={"oclusion_respuesta": conclusion},
                          salidas=[salida])


# =============================================================================
# SESIÓN "politica" — BARRIDO PROGRESIVO DE RÉGIMEN
# =============================================================================
# Los escalones se eligen para responder la pregunta abierta del régimen de
# operación, no por comodidad:
#
#   0.20 → pico teórico  73 rpm ≈ el peor caso del laboratorio (70.4 rpm), y
#          v efectiva 0.062 m/s ≈ v0_lin = 0.06 de laboratorio11.m. Es el
#          régimen que YA se sabe que funciona en estos robots.
#   0.55 → pico teórico 200 rpm = EXACTAMENTE el tope operativo del lab.
#   1.00 → caja de acciones completa; pico 365 rpm = 91 % del límite del
#          protocolo (400 rpm).
#   Los intermedios (0.30, 0.40, 0.75) dan saltos relativos parecidos
#   (×1.5, ×1.33, ×1.36, ×1.33), para que ningún escalón sea un salto al
#   vacío respecto del anterior.
FACTORES_BARRIDO: List[float] = [0.20, 0.30, 0.40, 0.55, 0.75, 1.00]
SEGUNDOS_POR_ESCALON: float = 30.0

# Referencias de simulación, para el diagnóstico en vivo.
REF_SIM: Dict[str, str] = {
    "accion":   f"sim: v hasta {V_MAX_POLITICA}, ω en ±{OMEGA_MAX_POLITICA}",
    "cbf":      "sim: ~0.37",
    "escape":   "sim: ~1.8 por agente-episodio",
    "pared":    "sim: nunca < 0.18",
    "rpm":      f"límite operativo de referencia: {RPM_CAP_LAB:.0f}",
}

# Criterios AUTOMÁTICOS del veredicto por escalón.
SEG_ESTABLE:    float = 0.70   # seguimiento v_real/v_comandada
SEG_MARGINAL:   float = 0.40
OSC_ESTABLE:    float = 0.25   # fracción de cambios de signo de ω real
OSC_MARGINAL:   float = 0.45


#: distancia comandada mínima para que el seguimiento signifique algo
DISTANCIA_MINIMA_SEGUIMIENTO_M: float = 0.02


def _veredicto_escalon(seguimiento: float, oscilacion: float,
                       abortado: bool,
                       datos_suficientes: bool = True) -> Tuple[str, str]:
    """
    Criterio explícito, sin interpretación humana en el momento.

    `datos_suficientes` NO es un detalle: sin él, un escalón donde el robot
    apenas recibió comando —por ejemplo entero dentro de la rampa de
    arranque— daba seguimiento 0.00 y se declaraba INESTABLE. Un cero por
    falta de medición no es evidencia de inestabilidad, y confundirlos
    inventa un resultado.
    """
    if abortado:
        return "INESTABLE", "abortado durante el escalón"
    if not datos_suficientes:
        return "SIN DATOS", (
            f"distancia comandada por debajo de "
            f"{DISTANCIA_MINIMA_SEGUIMIENTO_M*100:.0f} cm: el escalón no "
            f"alcanza para juzgar el seguimiento"
        )
    razones: List[str] = []
    if seguimiento < SEG_MARGINAL:
        razones.append(f"seguimiento {seguimiento:.2f} < {SEG_MARGINAL}")
    if oscilacion > OSC_MARGINAL:
        razones.append(f"oscilación {oscilacion:.2f} > {OSC_MARGINAL}")
    if razones:
        return "INESTABLE", "; ".join(razones)
    if seguimiento < SEG_ESTABLE:
        razones.append(f"seguimiento {seguimiento:.2f} < {SEG_ESTABLE}")
    if oscilacion > OSC_ESTABLE:
        razones.append(f"oscilación {oscilacion:.2f} > {OSC_ESTABLE}")
    if razones:
        return "MARGINAL", "; ".join(razones)
    return "ESTABLE", f"seguimiento {seguimiento:.2f}, oscilación {oscilacion:.2f}"


#: Decisiones consecutivas con la MISMA pose que se toleran antes de declarar
#: el marcador congelado, POR AGENTE.
#:
#: A 10 Hz de decisión, 10 son 1 segundo. El criterio se apoya en lo medido el
#: 2026-09-03: un marcador trackeado actualiza a ~82 Hz, así que dos decisiones
#: consecutivas NUNCA traen la misma pose — ni con el robot detenido, porque el
#: ruido de captura mueve los últimos decimales. Una sola repetición ya es
#: sospechosa; diez son una certeza y dejan margen para cualquier hipo del
#: muestreo.
#:
#: Por qué hace falta en evaluación y no en el barrido: se midió una pose
#: congelada de 13.4 s. Sobre episodios de 50 s eso es el 27 % del episodio con
#: el env recibiendo una pose muerta, y la cobertura AoI resultante sería
#: basura sin que ninguna validación de pose individual lo notara.
#:
#: ⚠ DESDE EL 2026-09-24 ya no aborta por agente: a la PRIMERA repetición
#: (`retroceso_congelamiento.REPETICIONES_PARA_RETROCESO`) el agente
#: RETROCEDE por donde entró y se reanuda cuando su pose vuelve; si no
#: vuelve, se aborta (ver `_correr_episodio`). Este umbral quedó para el
#: aborto que no espera al retroceso: TODOS los agentes con la pose repetida
#: estas decisiones seguidas.
DECISIONES_CONGELADO: int = 10


class DetectorCongelamiento:
    """
    Vigila, agente por agente, que la pose SIGA CAMBIANDO durante la corrida.

    `activo=False` lo apaga: en el simulador local, que es ideal y no tiene
    ruido de captura, un robot genuinamente detenido produce poses idénticas y
    el detector no puede distinguir "no se mueve" de "no lo vemos". Contra
    hardware real sí puede, y por eso ahí va encendido.

    Las pruebas lo instancian con `activo=True` a propósito, para ejercitar la
    lógica con un congelamiento inyectado.
    """

    def __init__(self, umbral: int = DECISIONES_CONGELADO,
                 activo: Optional[bool] = None) -> None:
        self.umbral = int(umbral)
        self.activo = (not cfg.SIMULADOR_ACTIVO) if activo is None else activo
        self._ultima: Dict[int, Tuple[float, ...]] = {}
        self._repeticiones: Dict[int, int] = {}

    def reiniciar(self) -> None:
        """Entre episodios: la pose de referencia ya no vale."""
        self._ultima.clear()
        self._repeticiones.clear()

    def observar(self, agente: int, pose: Tuple[float, ...]) -> bool:
        """
        Registra una pose. Devuelve True si ESE agente está congelado.

        ⚠ DECISIÓN DE LA QUE DEPENDE LA CORRECCIÓN: `pose` tiene que ser la
        pose COMPLETA —(x, y, θ) del entorno— y se compara entera. Nunca
        reducirla a la posición: con 10 µm de ruido de captura UNA coordenada
        float32 repite por azar en ~0.33 % de los pares, y cada repetición
        falsa es un retroceso falso. Con la fila completa de 7 valores del
        servidor, 0 en 400 000 (verificación del autor, 2026-09-24); con
        (x, y, θ), 0 en 34 715 pares medidos a 10 Hz (auditoría).
        """
        if not self.activo:
            return False
        clave = tuple(float(v) for v in pose)
        if self._ultima.get(agente) == clave:
            self._repeticiones[agente] = self._repeticiones.get(agente, 0) + 1
        else:
            self._repeticiones[agente] = 0
            self._ultima[agente] = clave
        return self._repeticiones.get(agente, 0) >= self.umbral

    def repeticiones(self, agente: int) -> int:
        return self._repeticiones.get(agente, 0)


def _activar_diagnostico_poses(fuente: Any, canal: Any, sesion: str,
                               etapa: int, n_agentes: int) -> Optional[Any]:
    """
    Si `cfg.DIAGNOSTICO_POSES` está encendido (`--diagnostico-poses`), crea
    el registro de diagnóstico de la cadena de poses, lo conecta a la fuente
    y a las órdenes del canal, y lo devuelve. Apagado devuelve `None` y no
    toca nada.

    ⚠ POR QUÉ (auditoría del 2026-09-24). Los 14 episodios perdidos por
    "marcador congelado" el 22 y el 24-09 no dejaron ni los bytes de la
    respuesta ni los contadores de la fuente (rechazos por motivo, consultas
    fallidas, descartes de búfer): salían por consola y se perdían. El
    registro los deja en `resultados_sesion/<fecha>_sesion-<sesion>_etapa<n>_
    diagnostico-poses.jsonl`. Ver `diagnostico_poses.py`.
    """
    if not cfg.DIAGNOSTICO_POSES:
        return None
    from diagnostico_poses import RegistroDiagnosticoPoses
    registro = RegistroDiagnosticoPoses(
        ruta_salida(sesion, etapa, "diagnostico-poses", extension="jsonl"),
        marcadores=[cfg.MAPEO_AGENTES[i].id_marcador for i in range(n_agentes)],
        robots=[cfg.MAPEO_AGENTES[i].id_robot for i in range(n_agentes)],
        datos_inicio={"sesion": sesion, "etapa": etapa,
                      "argv": list(sys.argv[1:])},
    )
    registro.fijar_fuente_comandos(lambda i: canal.ultimas_rpm.get(i))
    fuente.activar_diagnostico(registro)
    return registro


def sesion_politica(ctx: Contexto, rpm_aborto: float = RPM_CAP_LAB,
                    factores: Optional[List[float]] = None,
                    segundos_por_escalon: float = SEGUNDOS_POR_ESCALON,
                    n_agentes: int = 1,
                    ) -> ResultadoEtapa:
    """
    La política recorriendo el régimen de operación, con N robots.

    Usa el `CoordinadorEnjambre` real —política, filtro CBF, escape— con los
    adaptadores del Robotat, y le instala un observador por paso para
    registrar TODO a CSV. El CSV es el entregable de la sesión.

    `n_agentes = 1` es la sesión 'politica' (un robot, para caracterizar la
    cadena de actuación); `n_agentes = len(MAPEO_AGENTES)` es la sesión
    'enjambre'.

    ⚠ POR QUÉ IMPORTA N. Con un solo robot, las dimensiones 8–15 de la
    observación —el `neighbor_embedding`— quedan en CERO permanentemente:
    no hay vecinos que codificar. Es un tercio de la entrada de la política,
    y la generalización se validó para n ∈ {2..10}, no para n = 1. Medido en
    el laboratorio (2026-09-02) con un robot: la acción salió CONSTANTE y
    saturada (v = 0.310 en las 1505 decisiones, ω ≈ −2.13 con σ 0.067), que
    es un círculo de radio v/ω ≈ 14 cm — exactamente lo que hizo el robot.
    La corrida con n=1 caracteriza la ACTUACIÓN, no el comportamiento de la
    política; para eso hacen falta vecinos.
    """
    if n_agentes < 1:
        raise ValueError(f"n_agentes debe ser ≥ 1, no {n_agentes}")
    es_enjambre = n_agentes > 1
    from adaptadores_robotat import revisar_poses_iniciales
    from coordinador_enjambre import SEMILLAS_LOTE, CoordinadorEnjambre
    from lanzar_robotat import construir

    factores = factores if factores is not None else FACTORES_BARRIDO

    print()
    print("=" * 72)
    if es_enjambre:
        print(f"SESIÓN 'enjambre' — {n_agentes} ROBOTS, BARRIDO PROGRESIVO "
              f"DE RÉGIMEN")
    else:
        print("SESIÓN 'politica' — UN ROBOT, BARRIDO PROGRESIVO DE RÉGIMEN")
    print("=" * 72)
    print(f"  escalones      : {factores}")
    print(f"  duración c/u   : {segundos_por_escalon:.0f} s  ⇒ total ≈ "
          f"{len(factores)*segundos_por_escalon/60:.0f} min")
    print(f"  aborto por rpm : {rpm_aborto:.0f}")
    pico_teorico = max(abs(x) for x in accion_a_rpm(
        V_MAX_POLITICA, OMEGA_MAX_POLITICA,
        cfg.RADIO_RUEDA_M, cfg.MEDIO_EJE_M)[:2])
    umbral_factor = rpm_aborto / pico_teorico
    print(f"  ⚠ el pico teórico a factor 1.0 es {pico_teorico:.0f} rpm, así "
          f"que a partir del factor {umbral_factor:.2f}")
    print(f"    un peor caso de la política puede disparar el aborto POR "
          f"DISEÑO. Si ocurre, es dato, no falla.")

    # ⚠ `construir(1)` arma la fuente/el canal a partir de
    # `cfg.MAPEO_AGENTES[0]`, NO de `ctx.id_robot`/`ctx.marcador`. Sin esto,
    # el barrido correría en silencio sobre el robot que haya quedado en
    # `MAPEO_AGENTES[0]` —el de una calibración persistida, quizás de OTRO
    # robot— y no sobre el que el operador eligió con `--robot`. Se fuerza
    # acá, justo antes de construir, para que sea la ÚLTIMA palabra.
    #
    # Sólo aplica con UN robot: ahí `--robot` elige cuál. Con el enjambre, el
    # mapeo de los N agentes ES la configuración, y pisar la entrada 0 con el
    # robot de `--robot` rompería la correspondencia del resto.
    if not es_enjambre:
        cfg.MAPEO_AGENTES = dict(cfg.MAPEO_AGENTES)
        cfg.MAPEO_AGENTES[0] = cfg.AsignacionAgente(
            id_marcador=ctx.marcador, id_robot=ctx.id_robot,
        )
        print(f"  robot / marcador: {ctx.id_robot} / {ctx.marcador}")
    else:
        if len(cfg.MAPEO_AGENTES) < n_agentes:
            return ResultadoEtapa(
                6, "FALLO",
                f"se piden {n_agentes} agentes pero MAPEO_AGENTES sólo tiene "
                f"{len(cfg.MAPEO_AGENTES)}")
        for i in range(n_agentes):
            a = cfg.MAPEO_AGENTES[i]
            host, _p = cfg.endpoint_robot(a.id_robot)
            print(f"  agente {i}: robot {a.id_robot} / marcador "
                  f"{a.id_marcador}  @ {host}")

    # Chequeo previo de stream vivo. Versión MÍNIMA a propósito: no aborta a
    # media corrida —eso queda pendiente—, sólo se niega a ARRANCAR contra un
    # marcador congelado. Es el caso que más barato sale atajar y el que más
    # tiempo hace perder: con el stream muerto, el barrido entero se registra
    # contra una pose que no cambia y hay que repetirlo. Ya pasó dos veces con
    # la etapa 5. Un congelamiento a mitad de corrida sigue dependiendo de que
    # el operador esté mirando, que en una primera prueba supervisada es una
    # defensa razonable.
    # `correr_calibracion` conecta antes de cada etapa; este camino no pasa
    # por ahí, así que hay que hacerlo acá. Es idempotente.
    ctx.conectar()
    # Con el enjambre hay que revisar los N marcadores, no sólo el de `--robot`:
    # un solo marcador congelado basta para que ese agente conduzca a ciegas.
    marcadores = ([cfg.MAPEO_AGENTES[i].id_marcador for i in range(n_agentes)]
                  if es_enjambre else [ctx.marcador])
    for marc in marcadores:
        congelado, distintos, utiles = stream_congelado(ctx.poses, marc)
        if not utiles:
            return ResultadoEtapa(
                6, "FALLO",
                f"no se arranca: el marcador {marc} no devolvió ninguna pose")
        if congelado:
            print(f"  ✘ STREAM CONGELADO en el marcador {marc}: {utiles} "
                  f"lecturas con un solo valor.")
            print("    El servidor repite la última pose conocida — Motive "
                  "dejó de trackearlo.")
            return ResultadoEtapa(
                6, "FALLO",
                f"no se arranca el barrido: marcador {marc} congelado")

    ctx.cerrar()
    fuente, canal, entorno = construir(n_agentes)
    atexit.register(canal.detener_todo)
    diag = _activar_diagnostico_poses(
        fuente, canal, "enjambre" if es_enjambre else "politica", 6, n_agentes)

    try:
        # ── Chequeo geométrico obligatorio ───────────────────────────────
        from lanzar_robotat import leer_poses_estables
        poses = leer_poses_estables(fuente, n_agentes)
        problemas = revisar_poses_iniciales(poses, n_agentes)
        if problemas:
            print("\n✘ NO SE ARRANCA:")
            for p in problemas:
                print(f"    · {p}")
            lim = (f"[{cfg.MARGEN_PARED_ARRANQUE_M:.2f}, "
                   f"{cfg.ARENA_WX_M - cfg.MARGEN_PARED_ARRANQUE_M:.2f}]")
            print(f"\n  Posiciones actuales (hay que ponerlos dentro de {lim} "
                  f"en x e y, y a más de "
                  f"{cfg.D_SEPARACION_MIN_ARRANQUE_M:.2f} m entre sí):")
            for i in range(n_agentes):
                if i in poses:
                    x, y = float(poses[i][0]), float(poses[i][1])
                    rob = cfg.MAPEO_AGENTES[i].id_robot
                    print(f"    agente {i} (robot {rob}): "
                          f"({x:.3f}, {y:.3f})")
                else:
                    print(f"    agente {i}: SIN POSE")
            if not ctx.forzar:
                return ResultadoEtapa(6, "FALLO", "; ".join(problemas))
            print("  --forzar: se arranca igual.")

        coord = CoordinadorEnjambre(
            fuente=fuente, canal=canal, entorno=entorno,
            n_agentes=n_agentes, timestep_ms=10,
        )

        registro: List[Dict[str, Any]] = []
        estado: Dict[str, Any] = {"factor": factores[0], "escalon": 0}

        def observador(d: Dict[str, Any]) -> None:
            # El coordinador llama a esto UNA VEZ POR AGENTE y por decisión,
            # así que `registro` recibe N filas por decisión. El campo
            # `agente` es lo que las distingue; antes se ignoraba y las RPM
            # se leían siempre del agente 0, lo que con un enjambre habría
            # registrado las del robot equivocado en N−1 de cada N filas.
            ag = int(d["agente"])
            registro.append({
                "t_wall":            time.time(),
                "escalon":           estado["escalon"],
                "factor":            estado["factor"],
                "agente":            ag,
                "robot":             cfg.MAPEO_AGENTES[ag].id_robot,
                "paso":              d["paso"],
                "tick":              d["tick"],
                "pose_env_x":        float(d["pose_env"][0]),
                "pose_env_y":        float(d["pose_env"][1]),
                "pose_env_th":       float(d["pose_env"][2]),
                "v_nominal":         float(d["accion_nominal"][0]),
                "w_nominal":         float(d["accion_nominal"][1]),
                "v_tras_escape":     float(d["accion_tras_escape"][0]),
                "w_tras_escape":     float(d["accion_tras_escape"][1]),
                "v_ejecutada":       float(d["accion_ejecutada"][0]),
                "w_ejecutada":       float(d["accion_ejecutada"][1]),
                "en_escape":         int(d["en_escape"]),
                "cbf_intervino":     int(d["cbf_intervino"]),
                "factor_total":      canal.factor_total(),
                "rpm_izq":           canal.ultimas_rpm.get(ag, (0.0, 0.0))[0],
                "rpm_der":           canal.ultimas_rpm.get(ag, (0.0, 0.0))[1],
                # `ultimo_pico_rpm` ya es el máximo sobre TODOS los agentes:
                # es el número correcto para el aborto, y se repite en las N
                # filas de la decisión a propósito.
                "rpm_pico":          canal.ultimo_pico_rpm,
                **{f"obs_{k:02d}": float(v)
                   for k, v in enumerate(d["observacion"])},
            })

        coord._observador_paso = observador

        if not coord._reiniciar_episodio(SEMILLAS_LOTE[0]):
            return ResultadoEtapa(6, "FALLO", "no se pudo iniciar el episodio")

        resumen_escalones: List[Dict[str, Any]] = []
        motivo_aborto: Optional[str] = None

        for idx, factor in enumerate(factores):
            estado["escalon"], estado["factor"] = idx, factor
            canal.factor_operativo = factor
            if diag is not None:
                diag.fijar_contexto(fase="escalon", escalon=idx, factor=factor)
            v_ef = V_MAX_POLITICA * factor
            w_ef = OMEGA_MAX_POLITICA * factor
            print()
            print("-" * 72)
            print(f"ESCALÓN {idx+1}/{len(factores)}  factor {factor:.2f}  ⇒ "
                  f"v_ef ≤ {v_ef:.3f} m/s, ω_ef ≤ {w_ef:.2f} rad/s"
                  f"   [lab: {V_LAB} m/s, {OMEGA_LAB} rad/s]")
            print("-" * 72)

            marca = len(registro)
            resultado_esc = _correr_escalon(
                coord, canal, fuente, registro, marca,
                segundos_por_escalon, rpm_aborto, n_agentes,
            )
            resumen_escalones.append({"escalon": idx, "factor": factor,
                                      **resultado_esc})
            print(f"  VEREDICTO escalón {idx+1}: {resultado_esc['veredicto']}"
                  f"  ({resultado_esc['razon']})")
            if resultado_esc["abortado"]:
                motivo_aborto = resultado_esc["razon"]
                if diag is not None:
                    diag.registrar_evento("aborto", escalon=idx, factor=factor,
                                          motivo=motivo_aborto)
                break

        canal.detener_todo()
        # El nombre del archivo distingue las dos sesiones: los CSV son el
        # entregable y mezclar un barrido de un robot con uno de cinco en el
        # mismo nombre haría imposible saber cuál es cuál después.
        nombre_ses = "enjambre" if es_enjambre else "politica"
        salida = ruta_salida(nombre_ses, 6, "barrido-regimen")
        escribir_csv(salida, registro)
        salida_res = ruta_salida(nombre_ses, 6, "resumen-escalones")
        escribir_csv(salida_res, resumen_escalones)

        print()
        print("=" * 72)
        print("RESUMEN DEL BARRIDO")
        col_sep = f"{'sep_min':>8} " if es_enjambre else ""
        print(f"{'esc':>4} {'factor':>7} {'veredicto':>10} {'segui':>7} "
              f"{'oscil':>7} {'d_cmd_m':>8} {col_sep}{'rpm pico':>9} "
              f"{'ciclo p95':>10}  razón")
        for r in resumen_escalones:
            marca_ciclo = " ⚠" if r.get("frac_ciclo_sobre_presupuesto", 0.0) > 0.20 else "  "
            val_sep = (f"{r.get('separacion_min_m', 0.0):>8.3f} "
                       if es_enjambre else "")
            print(f"{r['escalon']:>4} {r['factor']:>7.2f} "
                  f"{r['veredicto']:>10} {r['seguimiento']:>7.2f} "
                  f"{r['oscilacion']:>7.2f} {r['dist_comandada_m']:>8.3f} "
                  f"{val_sep}"
                  f"{r['rpm_pico']:>9.1f} {r.get('ciclo_ms_p95', 0.0):>8.1f} ms"
                  f"{marca_ciclo}  {r['razon']}")
        estables = [r["factor"] for r in resumen_escalones
                    if r["veredicto"] == "ESTABLE"]
        if estables:
            print(f"\n  Máximo factor ESTABLE: {max(estables):.2f}  "
                  f"⇒ v ≤ {V_MAX_POLITICA*max(estables):.3f} m/s")
        print("=" * 72)

        veredicto = "OK" if not motivo_aborto else "ADVERTENCIA"
        return ResultadoEtapa(
            6, veredicto,
            motivo_aborto or f"{len(resumen_escalones)} escalones corridos",
            salidas=[salida, salida_res],
        )
    finally:
        try:
            canal.detener_todo()
        finally:
            if diag is not None:
                diag.cerrar(resumen_fuente=fuente.resumen() + canal.resumen())
            entorno.finalizar(0)


#: Valores de simulación contra los que se compara la evaluación. Se declaran
#: acá, con su procedencia, y NO como una constante suelta: la lección del
#: 2026-09-03 fue que `REF_SIM["cbf"] = "~0.37"` no tenía fuente documentada y
#: se usó para afirmar una coincidencia que no existía.
REF_EVAL: Dict[str, str] = {
    "cobertura_webots": "0.5739",
    "cobertura_python": "0.5780",
    "colisiones":       "0.000 (Webots)",
    "d_pared":          "nunca < 0.18 (Webots)",
}

#: Episodio de evaluación: 500 decisiones a dt_env = 0.1 s = 50 s, igual que
#: en simulación, para que la estadística sea comparable.
DECISIONES_POR_EPISODIO: int = 500

#: Regla "sin desplazamiento por 10 s" de `_correr_episodio` (arreglo del
#: 2026-10-02, con OK de José; ver tesis/PROPUESTA_regla_estancamiento.md).
#: Antes medía desde el ÚLTIMO desplazamiento > 2 mm, no desde que se le
#: ORDENÓ moverse: un agente quieto y sin orden más de 10 s al que de pronto
#: se le ordena moverse —el caso de la demo del obstáculo móvil: agentes
#: quietos que tienen que huir— cortaba la toma en la primera decisión con
#: orden, antes de que el retardo de actuación le dejara moverse. Ahora el
#: reloj arranca en el inicio de la orden SOSTENIDA más un margen para el
#: retardo (849 ms de arranque a 0.05 m/s, el peor medido), y la orden se da
#: por terminada sólo tras `CORTE_ORDEN_ESTANCAMIENTO_S` seguidos sin orden
#: (histéresis: un filtro que parpadea no reinicia el reloj de un robot
#: trabado). Como el nuevo instante de referencia es ≥ el viejo, el arreglo
#: sólo puede QUITAR cortes: 0 de los 50 válidos del 30-09 cambian.
MARGEN_RETARDO_ESTANCAMIENTO_S: float = 1.0
CORTE_ORDEN_ESTANCAMIENTO_S: float = 1.0


def sesion_evaluacion(ctx: Contexto, n_agentes: int,
                      factor: float = 0.40,
                      episodios_objetivo: int = 10,
                      episodios_minimo: int = 5,
                      decisiones: int = DECISIONES_POR_EPISODIO,
                      intentos_max: Optional[int] = None,
                      rpm_aborto: float = RPM_CAP_LAB,
                      colocacion: str = "manual",
                      ) -> ResultadoEtapa:
    """
    Episodios REPETIDOS a factor FIJO, para producir estadística comparable
    con la simulación.

    `colocacion`: "manual" (el operador lleva cada robot a su blanco con la
    guía) o "auto" (los robots van solos a blanco y rumbo antes de cada
    episodio, incluido el primero; ver `colocacion_autonoma.py`). Si la
    automática deja algo que el chequeo geométrico rechaza, se cae a la guía
    manual y, tras el Enter del operador, se vuelve a colocar sola.

    Se diferencia de `sesion_politica` en el propósito: aquella barre factores
    para caracterizar el régimen de actuación; ésta fija el régimen y repite
    episodios completos para medir COBERTURA y COLISIONES, que son las dos
    métricas que faltaban.

    Un episodio abortado —estancamiento, congelamiento, cualquier causa— se
    marca INVÁLIDO con su motivo y se repite. Sólo los válidos entran en la
    estadística.

    ⚠ CAVEATS que van en el reporte, no descubiertos después:

    1. Las semillas controlan las trayectorias de los objetivos virtuales,
       pero NO las poses iniciales: en hardware son las que queden al
       reposicionar a mano. La comparación con simulación NO es pareada por
       semilla.
    2. El `factor` escala la acción COMANDADA pero no la observación: la
       política "cree" ir más rápido de lo que va. Es la misma desalineación
       ya documentada para la rampa de arranque seguro.
    """
    from adaptadores_robotat import revisar_poses_iniciales
    from coordinador_enjambre import SEMILLAS_LOTE, CoordinadorEnjambre
    from lanzar_robotat import construir, leer_poses_estables

    if n_agentes < 2:
        return ResultadoEtapa(7, "FALLO",
                              f"la evaluación necesita ≥2 agentes, no {n_agentes}")
    intentos_max = intentos_max or (episodios_objetivo * 2)

    print()
    print("=" * 72)
    print(f"SESIÓN 'evaluacion' — {n_agentes} ROBOTS, FACTOR FIJO {factor:.2f}")
    print("=" * 72)
    print(f"  v efectiva     : ≤ {V_MAX_POLITICA*factor:.3f} m/s   "
          f"ω ≤ {OMEGA_MAX_POLITICA*factor:.2f} rad/s")
    print(f"  episodios      : {episodios_objetivo} válidos "
          f"(mínimo aceptable {episodios_minimo}, hasta {intentos_max} intentos)")
    print(f"  cada uno       : {decisiones} decisiones × 0.1 s = "
          f"{decisiones*0.1:.0f} s")
    print(f"  capas          : política + CBF + escape")
    print(f"  aborto por rpm : {rpm_aborto:.0f}")
    if colocacion == "auto":
        from colocacion_autonoma import V_COL, W_COL
        print(f"  colocación     : AUTOMÁTICA — antes de cada episodio los robots")
        print(f"                   van SOLOS a blanco y rumbo (≤ {V_COL} m/s, "
              f"≤ {W_COL} rad/s, con CBF)")
    else:
        print(f"  colocación     : manual, con guía")
    print()
    print("  ⚠ No hay reset por teletransporte: los robots se colocan entre")
    print("    episodios. Las poses iniciales no las fija la semilla, así que")
    print("    la comparación con simulación NO es pareada por semilla.")
    for i in range(n_agentes):
        a = cfg.MAPEO_AGENTES[i]
        print(f"  agente {i}: robot {a.id_robot} / marcador {a.id_marcador}")

    ctx.conectar()
    for i in range(n_agentes):
        marc = cfg.MAPEO_AGENTES[i].id_marcador
        congelado, _d, utiles = stream_congelado(ctx.poses, marc)
        if not utiles or congelado:
            return ResultadoEtapa(
                7, "FALLO",
                f"no se arranca: marcador {marc} "
                f"{'congelado' if utiles else 'sin respuesta'}")
    ctx.cerrar()

    fuente, canal, entorno = construir(n_agentes)
    atexit.register(canal.detener_todo)
    coord = CoordinadorEnjambre(fuente=fuente, canal=canal, entorno=entorno,
                                n_agentes=n_agentes, timestep_ms=10)
    canal.factor_operativo = factor
    detector = DetectorCongelamiento()
    seguimiento = DetectorSeguimiento()

    registro: List[Dict[str, Any]] = []
    estado: Dict[str, Any] = {"episodio": 0}

    def observador(d: Dict[str, Any]) -> None:
        ag = int(d["agente"])
        registro.append({
            "episodio":     estado["episodio"],
            "agente":       ag,
            "robot":        cfg.MAPEO_AGENTES[ag].id_robot,
            "paso":         d["paso"],
            "pose_env_x":   float(d["pose_env"][0]),
            "pose_env_y":   float(d["pose_env"][1]),
            "pose_env_th":  float(d["pose_env"][2]),
            "v_ejecutada":  float(d["accion_ejecutada"][0]),
            "w_ejecutada":  float(d["accion_ejecutada"][1]),
            "en_escape":    int(d["en_escape"]),
            "cbf_intervino": int(d["cbf_intervino"]),
            "rpm_pico":     canal.ultimo_pico_rpm,
            "con_vecino":   int(any(
                abs(float(v)) > 1e-9
                for v in np.asarray(d["observacion"])[8:16])),
            # 1 si en esta decisión el canal le mandó el RETROCESO por pose
            # repetida (2026-09-24): la acción de arriba NO se ejecutó.
            "en_retroceso": int(ag in getattr(canal, "mandos_directos", {})),
        })

    coord._observador_paso = observador
    episodios: List[Dict[str, Any]] = []
    rechazos_colocacion = 0
    diag = _activar_diagnostico_poses(fuente, canal, "evaluacion", 7,
                                      n_agentes)

    try:
        for intento in range(1, intentos_max + 1):
            validos = sum(1 for e in episodios if e["valido"])
            if validos >= episodios_objetivo:
                break
            print()
            print("-" * 72)
            print(f"EPISODIO {intento}  (válidos hasta ahora: {validos}/"
                  f"{episodios_objetivo})")
            print("-" * 72)
            if diag is not None:
                diag.fijar_contexto(episodio=intento, fase="entre_episodios")
            # Un blanco distinto por episodio, sorteado de la distribución
            # de entrenamiento: sin esto el operador no tiene a qué apuntar
            # y termina reponiendo siempre al mismo lugar, que colapsa la
            # varianza del informe (ver `sortear_poses_arranque`).
            # Semilla por intento. Eran las 18 de SEMILLAS_LOTE en ciclo, con
            # hasta 2×objetivo intentos: los intentos 19 y 20 repetían EXACTO
            # la configuración de los 1 y 2 (blancos y campo). Se sigue la
            # misma fórmula (42·10⁴ + i) en vez de volver a empezar.
            semilla = (SEMILLAS_LOTE[intento - 1]
                       if intento <= len(SEMILLAS_LOTE)
                       else SEMILLAS_LOTE[0] + intento - 1)
            blancos = sortear_poses_arranque(
                n_agentes, np.random.default_rng(semilla))
            from colocacion_autonoma import sortear_rumbos
            rumbos = sortear_rumbos(n_agentes, semilla)
            # El blanco de CADA intento queda en el CSV, válido o no: así
            # `diversidad_arranques` puede ver si las exclusiones sesgaron
            # los arranques. El rumbo sólo se pide en la colocación automática.
            info_col: Dict[str, Any] = {"colocacion": colocacion}
            for i in range(n_agentes):
                info_col[f"blanco_x_a{i}"] = round(float(blancos[i][0]), 4)
                info_col[f"blanco_y_a{i}"] = round(float(blancos[i][1]), 4)
                info_col[f"blanco_th_a{i}"] = (round(rumbos[i], 4)
                                               if colocacion == "auto" else "")

            abandonos_col: Dict[int, str] = {}

            def colocar_solos() -> None:
                """Colocación automática; deja su informe en `info_col`."""
                from colocacion_autonoma import colocar_enjambre
                if diag is not None:
                    diag.fijar_contexto(fase="colocacion")
                inf = colocar_enjambre(fuente, canal, blancos, rumbos,
                                       n_agentes)
                if diag is not None:
                    diag.fijar_contexto(fase="entre_episodios")
                    diag.registrar_evento(
                        "fin_colocacion", motivo=inf.motivo_fin,
                        t_colocacion_s=inf.t_s,
                        abandonados={str(k): v
                                     for k, v in inf.abandonados.items()})
                info_col.update(inf.como_fila(n_agentes))
                abandonos_col.clear()
                abandonos_col.update(inf.abandonados)

            def problemas_de_arranque(poses) -> List[str]:
                """Chequeo geométrico + poses VIVAS (ver funciones)."""
                problemas_ = revisar_poses_iniciales(poses, n_agentes)
                # Un marcador que se congeló durante la colocación deja una
                # posición no confiable: que lo vea el operador (revisión
                # adversarial 2026-09-22).
                problemas_ += [
                    f"agente {i} (robot {cfg.MAPEO_AGENTES[i].id_robot}): "
                    f"marcador congelado durante la colocación — movelo o "
                    f"giralo a mano hasta que la guía muestre su pose "
                    f"cambiando (Motive lo perdió)"
                    for i, m in sorted(abandonos_col.items())
                    if m == "marcador congelado"]
                problemas_ += _marcadores_congelados_al_arrancar(
                    fuente, n_agentes)
                problemas_ += _enlaces_caidos_al_arrancar(canal)
                return problemas_

            # ⚠ HALLAZGO (2026-09-11): un rechazo del chequeo de arranque
            # gastaba el intento. En la sesión del 11 de septiembre 7 de 19
            # intentos se fueron así, casi siempre por quedar 1–6 cm por
            # debajo del margen de 0.20 m, y la sesión se quedó sin intentos
            # con 5 válidos. Un rechazo no dice nada del sistema —el
            # episodio ni arrancó—, así que ahora se vuelve a pedir la misma
            # colocación. Con tope, para que un problema persistente no
            # cuelgue la sesión.
            if colocacion == "auto":
                # Un Enter por episodio: los robots se van a mover solos y el
                # operador tiene que haber despejado la arena. Con latido.
                _esperar_reposicionamiento(
                    ctx, fuente, canal,
                    "  Los robots van a ir SOLOS a estos blancos. Despejá la "
                    "arena y dale Enter (Ctrl+C corta).", blancos)
                colocar_solos()
            elif intento > 1:
                # Con latido: sin él, los sockets se caen durante la pausa.
                _esperar_reposicionamiento(
                    ctx, fuente, canal,
                    "  Reposicioná los robots y dale Enter.", blancos)

            poses_ini = leer_poses_estables(fuente, n_agentes)
            problemas = problemas_de_arranque(poses_ini)
            reintento = 0
            while problemas and reintento < REINTENTOS_COLOCACION:
                reintento += 1
                rechazos_colocacion += 1
                if diag is not None:
                    diag.registrar_evento("rechazo_arranque",
                                          problemas=list(problemas),
                                          reintento=reintento)
                print("  ✘ no se arranca todavía:")
                for p in problemas:
                    print(f"      · {p}")
                print(f"  (no se gasta el intento: corregí y dale Enter — "
                      f"{reintento}/{REINTENTOS_COLOCACION})")
                _esperar_reposicionamiento(
                    ctx, fuente, canal,
                    ("  Corregí lo que impide moverse (marcador tapado, robot "
                     "apagado o trabado) y dale Enter: después se vuelven a "
                     "colocar solos." if colocacion == "auto"
                     else "  Corregí la colocación y dale Enter."), blancos)
                if colocacion == "auto":
                    colocar_solos()
                poses_ini = leer_poses_estables(fuente, n_agentes)
                problemas = problemas_de_arranque(poses_ini)
            if problemas:
                print("  ✘ no se arranca este episodio:")
                for p in problemas:
                    print(f"      · {p}")
                episodios.append({"episodio": intento, "valido": 0,
                                  "motivo": "; ".join(problemas), **info_col})
                if diag is not None:
                    diag.registrar_evento("intento_sin_arrancar",
                                          problemas=list(problemas))
                continue

            estado["episodio"] = intento
            marca = len(registro)
            detector.reiniciar()
            seguimiento.reiniciar()
            # Re-anclar el horario de ticks: sin esto, el tiempo que el
            # operador tardó en reposicionar deja el lazo permanentemente
            # atrasado y deja de dormir — el episodio corre a velocidad de
            # CPU. Ver `EntornoEjecucionRobotat.reiniciar_reloj`.
            if hasattr(entorno, "reiniciar_reloj"):
                entorno.reiniciar_reloj()
            if diag is not None:
                diag.fijar_contexto(fase="episodio")
            # Contadores de la fuente al empezar: el episodio se lleva la
            # diferencia (decisión del autor, 2026-09-24).
            contadores_antes = _contadores_fuente(fuente)
            if not coord._reiniciar_episodio(semilla):
                episodios.append({"episodio": intento, "valido": 0,
                                  "motivo": "no se pudo iniciar el episodio"})
                continue

            res = _correr_episodio(coord, canal, fuente, registro, marca,
                                   decisiones, rpm_aborto, n_agentes,
                                   detector, semilla, seguimiento, diag=diag)
            res.update(_delta_contadores_fuente(contadores_antes, fuente))
            res["episodio"] = intento
            if diag is not None:
                diag.registrar_evento(
                    "fin_episodio", valido=res["valido"], motivo=res["motivo"],
                    decisiones=res["decisiones"], duracion_s=res["duracion_s"])
            # Régimen con que corrió: la réplica pareada lo lee de acá en vez
            # de suponer los valores por defecto (revisión del 2026-09-22).
            res["factor"] = factor
            res["rpm_aborto"] = rpm_aborto
            res.update(info_col)
            for i in range(n_agentes):
                # Composición y offset de rumbo con que se midió este episodio:
                # el enjambre cambió de robots (3 → 8, 2026-09-22) y el 8 usa
                # un offset medido en una sola corrida. Sin esto, un CSV no
                # dice con qué robots ni sobre qué rumbo se obtuvo.
                rid = cfg.MAPEO_AGENTES[i].id_robot
                res[f"robot_a{i}"] = rid
                res[f"offset_deg_a{i}"] = round(
                    math.degrees(cfg.offset_rumbo_de_robot(rid)), 4)
                res[f"offset_origen_a{i}"] = cfg.origen_offset_rumbo(rid)
                if i in poses_ini:
                    res[f"x0_a{i}"] = float(poses_ini[i][0])
                    res[f"y0_a{i}"] = float(poses_ini[i][1])
                    res[f"th0_a{i}"] = float(poses_ini[i][2])
            episodios.append(res)
            print(f"  >>> EPISODIO {intento}: "
                  f"{'VÁLIDO' if res['valido'] else 'INVÁLIDO'}"
                  f"  {res.get('motivo', '')}")
            if res.get("retrocesos_detalle"):
                print(f"      ↩ retrocesos por pose repetida: "
                      f"{res['retrocesos_detalle']}  "
                      f"({res['decisiones_retroceso']} decisiones-agente, "
                      f"{100 * res['frac_decisiones_retroceso']:.1f} %)")
            if res["valido"]:
                print(f"      cobertura AoI {res['cobertura_aoi']:.4f}  ·  "
                      f"colisiones <0.15 {res['colisiones_015']}  ·  "
                      f"d_pared mín {res['d_pared_min']:.6f}")
                # Réplica pareada: el mismo episodio en simulación, desde
                # esta misma pose inicial. Es la comparación honesta.
                rep = _replica_simulada(poses_ini, semilla, decisiones,
                                        n_agentes, factor)
                res["cobertura_replica"] = rep
                if rep is not None:
                    print(f"      réplica simulada {rep:.4f}  ·  "
                          f"diferencia {res['cobertura_aoi'] - rep:+.4f}")
    finally:
        canal.detener_todo()
        # ⚠ HALLAZGO (2026-09-09): estas dos escrituras estaban DESPUÉS del
        # try/finally. La sesión se cortó con Ctrl+C en el episodio 4 —a un
        # robot se le acabó la batería— y no quedó ni una fila en disco: se
        # perdió el único episodio válido, con su cobertura y su réplica
        # pareada, después de que el operador reposicionara los robots a mano
        # tres veces. Una sesión de laboratorio no se puede repetir gratis, así
        # que lo medido se persiste pase lo que pase: interrupción, excepción
        # o final normal.
        salida = ruta_salida("evaluacion", 7, "decisiones")
        escribir_csv(salida, registro)
        salida_ep = ruta_salida("evaluacion", 7, "episodios")
        escribir_csv(salida_ep, episodios)
        print(f"[sesion] rechazos del chequeo de colocación que NO gastaron "
              f"intento: {rechazos_colocacion}")
        if diag is not None:
            diag.cerrar(resumen_fuente=fuente.resumen() + canal.resumen())

    return _informe_evaluacion(episodios, factor, n_agentes,
                               [salida, salida_ep])


#: Cuántas veces se vuelve a pedir la colocación tras un rechazo del chequeo
#: de arranque antes de dar el intento por perdido.
REINTENTOS_COLOCACION: int = 5


#: Período del latido que mantiene vivas las conexiones durante las pausas.
#: 1 s es holgado frente a cualquier tiempo de descarte razonable y no carga
#: la red: son 6 mensajes por segundo contra los ~10 Hz de una corrida.
PERIODO_LATIDO_S: float = 1.0


# =============================================================================
# COLOCACIÓN ASISTIDA DE LOS ROBOTS ENTRE EPISODIOS
# =============================================================================
#
# ⚠ HALLAZGO (2026-09-05). En la sesión de evaluación el operador repuso los
# robots "al centro" en todos los episodios, porque intentar variarlos —los
# quiso agrupar en una esquina— se lo rechazaba el chequeo geométrico. El
# resultado se midió: contra un arranque uniforme, la media de cobertura casi
# no cambia (+0.044, dentro del ruido a 8 semillas) pero la desviación cae de
# 0.1061 a 0.0213, CINCO VECES. Un `±` medido así no describe al sistema,
# describe la repetibilidad de una sola condición inicial.
#
# La causa no fue criterio del operador sino falta de blanco: el chequeo dice
# que NO, nunca dónde SÍ. Peor, sus umbrales son más permisivos que la
# distribución de entrenamiento —acepta 0.20 m de la pared, y el sorteo de
# entrenamiento nunca produce menos de 0.45 m—, así que hay colocaciones que
# el chequeo aprueba y que la política jamás vio.
#
# Esto sortea un blanco por robot DE LA MISMA DISTRIBUCIÓN que el
# entrenamiento y guía al operador hasta él.

#: Margen a la pared del sorteo de entrenamiento: `0.15 * arena_size` sobre
#: 3×3 m (ver `_sortear_poses_iniciales` en lib/swarm_env_skeleton.py).
MARGEN_ARRANQUE_M: float = 0.45

#: Separación mínima entre blancos. El entrenamiento usa 2·D_SAFE+0.01 =
#: 0.31 m; acá se pide más para que el error de colocación no empuje a un par
#: por debajo del mínimo del chequeo (0.15 m). Es un SUBCONJUNTO del soporte
#: de entrenamiento, no otra distribución.
D_SEPARACION_OBJETIVO_M: float = 0.45

#: Cuánto puede desviarse un robot de su blanco. No hace falta más precisión:
#: la comparación con simulación se hace pareada desde la pose REAL medida
#: (ver `_replica_simulada`), así que el blanco sólo garantiza variedad y
#: estar dentro de distribución, no exactitud.
TOL_COLOCACION_M: float = 0.12


def sortear_poses_arranque(
    n_agentes: int,
    rng: Optional[np.random.Generator] = None,
    intentos: int = 400,
) -> Dict[int, np.ndarray]:
    """
    Sortea un blanco de colocación por agente, en el marco del env.

    Misma distribución que `_sortear_poses_iniciales` del entorno: uniforme
    en [MARGEN, arena-MARGEN]² con separación mínima entre pares.

    Retorna
    -------
    {indice_agente: np.ndarray (2,)}
    """
    rng = rng or np.random.default_rng()
    lo = MARGEN_ARRANQUE_M
    hi_x = cfg.ARENA_WX_M - MARGEN_ARRANQUE_M
    hi_y = cfg.ARENA_WY_M - MARGEN_ARRANQUE_M

    puestos: List[np.ndarray] = []
    for _ in range(n_agentes):
        for _try in range(intentos):
            cand = np.array([rng.uniform(lo, hi_x), rng.uniform(lo, hi_y)])
            if all(float(np.linalg.norm(cand - p)) > D_SEPARACION_OBJETIVO_M
                   for p in puestos):
                puestos.append(cand)
                break
        else:
            raise RuntimeError(
                f"no se pudo colocar {n_agentes} blancos separados "
                f"{D_SEPARACION_OBJETIVO_M} m en el área útil")
    return {i: p for i, p in enumerate(puestos)}


def _marcadores_congelados_al_arrancar(fuente, n_agentes: int) -> List[str]:
    """
    Agentes cuya pose NO está viva justo antes de arrancar un episodio.

    ⚠ HALLAZGO (2026-09-22, episodio 1 de ese día + revisión adversarial): el
    chequeo de arranque mira presencia, arena, pared y separación, pero no si
    la pose se está actualizando. Un marcador congelado —el servidor repite
    la última pose válida— pasa el chequeo, el episodio arranca y
    `DetectorCongelamiento` lo invalida al segundo: se gasta el intento. Acá
    se convierte en un rechazo de colocación, que NO lo gasta.

    Dos consultas reales separadas 0.15 s: un marcador vivo tiembla a ~82 Hz
    y nunca repite bit a bit. No aplica en el simulador (poses ideales: un
    robot quieto repite), igual que `DetectorCongelamiento`. Compara la pose
    COMPLETA (x, y, θ), nunca sólo la posición: ver
    `DetectorCongelamiento.observar`.
    """
    if cfg.SIMULADOR_ACTIVO or not hasattr(fuente, "leer_poses_ya"):
        return []
    a = fuente.leer_poses_ya()
    time.sleep(0.15)
    b = fuente.leer_poses_ya()
    return [f"agente {i} (robot {cfg.MAPEO_AGENTES[i].id_robot}): marcador "
            f"CONGELADO (misma pose en dos lecturas) — movelo o giralo a mano "
            f"hasta que la guía muestre su pose cambiando, o revisá Motive"
            for i in sorted(set(a) & set(b)) if np.array_equal(a[i], b[i])]


def _enlaces_caidos_al_arrancar(canal) -> List[str]:
    """
    Robots cuyo enlace de ruedas sigue caído justo antes de arrancar.

    ⚠ HALLAZGO (2026-09-24): el robot 5 estuvo 5.4 min fuera de la red (227
    intentos de reconexión sin respuesta) y la sesión arrancó igual cinco
    episodios, que murieron al segundo. Acá se intenta reabrir una vez más
    y lo que siga caído es un rechazo de colocación, que no gasta intento.
    """
    if not hasattr(canal, "reintentar_enlaces"):
        return []
    return [f"robot {cfg.MAPEO_AGENTES[i].id_robot}: su enlace de ruedas "
            f"no responde (¿apagado, sin batería o fuera del WiFi?) — "
            f"revisalo antes de seguir"
            for i in canal.reintentar_enlaces()]


def _rumbo_cardinal(dx: float, dy: float) -> str:
    """Dirección en palabras, para no tener que interpretar un signo."""
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return "—"
    ang = math.degrees(math.atan2(dy, dx)) % 360.0
    nombres = ["+x", "+x+y", "+y", "-x+y", "-x", "-x-y", "-y", "+x-y"]
    return nombres[int((ang + 22.5) // 45) % 8]


def _tabla_colocacion(poses: Dict[int, np.ndarray],
                      blancos: Dict[int, np.ndarray],
                      congelados: Optional[set] = None,
                      ) -> Tuple[List[str], bool]:
    """
    Arma la guía de colocación: dónde está cada robot y cuánto le falta.

    `congelados`: agentes cuya pose no cambió entre dos latidos. ⚠ 2026-09-22:
    la guía le ponía ✔ al robot 2 con el marcador congelado —la pose repetida
    estaba en su blanco— y el operador no tenía cómo saber que tenía que
    moverlo para que Motive lo recuperara.

    Retorna las líneas y si TODOS están dentro de la tolerancia.
    """
    congelados = congelados or set()
    lineas: List[str] = []
    todos_ok = True
    for i in sorted(blancos):
        b = blancos[i]
        rob = cfg.MAPEO_AGENTES[i].id_robot
        if i not in poses:
            lineas.append(f"    robot {rob}: SIN POSE  ·  blanco "
                          f"({b[0]:.2f}, {b[1]:.2f})")
            todos_ok = False
            continue
        if i in congelados:
            lineas.append(f"  ✘ robot {rob}: marcador CONGELADO (pose repetida "
                          f"en {poses[i][0]:.2f}, {poses[i][1]:.2f}) — movelo o "
                          f"giralo a mano hasta que la pose cambie")
            todos_ok = False
            continue
        p = np.asarray(poses[i])[:2]
        d = float(np.linalg.norm(b - p))
        ok = d <= TOL_COLOCACION_M
        todos_ok = todos_ok and ok
        marca = "✔" if ok else " "
        rumbo = "" if ok else f"  →  mover {d*100:5.1f} cm hacia " \
                              f"{_rumbo_cardinal(b[0]-p[0], b[1]-p[1])}"
        lineas.append(
            f"  {marca} robot {rob}: está ({p[0]:.2f}, {p[1]:.2f})  "
            f"blanco ({b[0]:.2f}, {b[1]:.2f}){rumbo}")
    return lineas, todos_ok


def _esperar_reposicionamiento(
        ctx: "Contexto", fuente, canal, mensaje: str,
        blancos: Optional[Dict[int, np.ndarray]] = None) -> None:
    """
    Espera al operador SIN dejar morir las conexiones.

    ⚠ HALLAZGO (2026-09-05): la sesión de evaluación falló repetidamente con
    `WinError 10054` —«conexión cerrada por el otro extremo»— tanto en el
    servidor de poses como en los cinco robots, mientras que el barrido corría
    sin un solo fallo. La diferencia no era el protocolo: el barrido nunca
    pausa, y la evaluación sí, mientras el operador reposiciona los robots a
    mano. Con los seis sockets abiertos y sin tráfico durante minutos, el
    servidor embebido y los robots los descartan.

    El síntoma engaña: el robot está encendido y respondiendo, lo que se cayó
    es el socket. Por eso acá se late durante la espera —una consulta de poses
    y un `detener_todo`, que además deja los robots frenados mientras se los
    manipula— en vez de reconectar después, que llegaría tarde.
    """
    parar = threading.Event()

    def latir() -> None:
        # ⚠ HALLAZGO (2026-09-09): acá se llamaba a `fuente.leer_poses()`,
        # que devuelve una LISTA de pares (indice, medida) y además sólo hace
        # una consulta real cada `_intervalo_ticks` llamadas. `_tabla_
        # colocacion` espera un dict indexado por agente, así que `i not in
        # poses` comparaba un int contra tuplas: SIEMPRE daba falso y la guía
        # imprimía "SIN POSE" para los cinco robots, en todas las pausas de
        # toda la sesión. El operador reposicionó a ojo, que es justo lo que
        # esta guía venía a evitar. `leer_poses_estables` es la lectura que ya
        # usa el resto de la sesión: sondea hasta juntar a los N y devuelve el
        # dict que la tabla necesita.
        from lanzar_robotat import leer_poses_estables
        n_esperados = len(blancos) if blancos else 0
        anteriores: Dict[int, np.ndarray] = {}
        while not parar.is_set():
            try:
                poses = (leer_poses_estables(fuente, n_esperados, plazo_s=0.5)
                         if blancos else fuente.leer_poses())
            except Exception:                              # noqa: BLE001
                poses = None
            # Pose idéntica entre dos latidos (1 s) = marcador congelado: uno
            # vivo tiembla a ~82 Hz. No en el simulador (poses ideales). Pose
            # COMPLETA (x, y, θ): ver `DetectorCongelamiento.observar`.
            congelados: set = set()
            if blancos and isinstance(poses, dict):
                if not cfg.SIMULADOR_ACTIVO:
                    congelados = {i for i, p in poses.items()
                                  if i in anteriores
                                  and np.array_equal(np.asarray(p),
                                                     anteriores[i])}
                anteriores = {i: np.asarray(p).copy()
                              for i, p in poses.items()}
            try:
                canal.detener_todo(silencioso=True)
            except TypeError:          # canal sin el modo silencioso
                canal.detener_todo()
            except Exception:                              # noqa: BLE001
                pass
            # El latido ya está leyendo poses para no dejar morir el socket;
            # mostrarlas no cuesta una consulta más y le da al operador el
            # blanco al que apuntar, que es justo lo que le faltaba.
            if blancos and poses:
                lineas, todos_ok = _tabla_colocacion(poses, blancos,
                                                     congelados)
                print()
                for ln in lineas:
                    print(ln)
                if todos_ok:
                    print(f"  ✔ los {len(blancos)} en su blanco "
                          f"(±{TOL_COLOCACION_M*100:.0f} cm) — dale Enter.")
            parar.wait(PERIODO_LATIDO_S)

    if blancos:
        print()
        print("  BLANCOS DE ESTE EPISODIO (marco del env, metros sobre la")
        print(f"  cuadrícula de {cfg.ARENA_WX_M:.0f}×{cfg.ARENA_WY_M:.0f} m):")
        for i in sorted(blancos):
            b = blancos[i]
            print(f"    robot {cfg.MAPEO_AGENTES[i].id_robot}: "
                  f"({b[0]:.2f}, {b[1]:.2f})")
        print(f"  Tolerancia ±{TOL_COLOCACION_M*100:.0f} cm. La guía se "
              f"refresca cada {PERIODO_LATIDO_S:.0f} s.")

    hilo = threading.Thread(target=latir, daemon=True)
    hilo.start()
    try:
        ctx.esperar_enter(mensaje)
    finally:
        parar.set()
        hilo.join(timeout=2.0)


#: Ventana del detector de seguimiento, en decisiones (5 s a 10 Hz). La
#: ventana ES el antirruido: un tropiezo suelto no puede hundir un promedio
#: de 5 s, así que no hace falta exigir repeticiones como en el congelamiento.
VENTANA_SEGUIMIENTO: int = 50

#: Camino recorrido / camino comandado por debajo del cual se considera que
#: el robot NO está siguiendo la orden.
#:
#: Calibrado el 2026-09-08 sobre las seis corridas de barrido del 2 y 3 de
#: septiembre (397 ventanas de 5 s, ritmo correcto): el seguimiento sano es
#: notablemente estrecho —mediana 1.02, p05 0.94, 89.9 % entre 0.90 y 1.10—
#: y la cola patológica cae bajo 0.50 (13 ventanas, 6 de ellas del robot 2
#: en las sesiones donde se le acabó la batería). Entre 0.70 y 0.90 no hay
#: NINGUNA ventana: 0.50 se apoya en ese hueco, con el p05 sano al doble.
UMBRAL_SEGUIMIENTO: float = 0.50

#: Camino comandado mínimo en la ventana para emitir un juicio. Sin esto se
#: dividiría por casi cero cuando la política pide poca traslación —girar en
#: el lugar es legítimo— y cualquier ruido de captura daría un cociente
#: absurdo.
COMANDO_MINIMO_SEGUIMIENTO_M: float = 0.10


class DetectorSeguimiento:
    """
    Vigila que cada robot RECORRA lo que se le comanda.

    ⚠ POR QUÉ NO ALCANZA EL DETECTOR DE ESTANCAMIENTO. Aquél aborta si un
    agente no se desplaza más de 2 mm en 10 s. El 2026-09-08 el robot 9 fue
    comandado a avanzar recto y GIRÓ sobre su eje: recorrió 0.079 m de los
    0.24 comandados (33 %) mientras los otros cuatro hacían 0.245-0.249 m.
    Su marcador, montado ~1.5 cm descentrado, trazaba un arco de varios
    centímetros — muy por encima de los 2 mm. El estancamiento NUNCA habría
    disparado, y el episodio habría entrado como VÁLIDO con un robot girando
    en el lugar y aportando cobertura casi nula.

    Tampoco sirve la rectitud (neto/camino): el robot 9 dio 0.70 ahí, más
    alto que muchas ventanas sanas. Lo que separa las dos poblaciones es el
    SEGUIMIENTO, camino real contra camino comandado.

    `activo=False` lo apaga para el simulador local, igual que
    `DetectorCongelamiento`: ahí no hay ruedas que patinen.
    """

    def __init__(self, ventana: int = VENTANA_SEGUIMIENTO,
                 umbral: float = UMBRAL_SEGUIMIENTO,
                 comando_minimo: float = COMANDO_MINIMO_SEGUIMIENTO_M,
                 activo: Optional[bool] = None) -> None:
        self.ventana = int(ventana)
        self.umbral = float(umbral)
        self.comando_minimo = float(comando_minimo)
        self.activo = (not cfg.SIMULADOR_ACTIVO) if activo is None else activo
        self._hist: Dict[int, Deque[Tuple[float, float]]] = {}
        self._previa: Dict[int, np.ndarray] = {}
        self._ratio: Dict[int, float] = {}

    def reiniciar(self) -> None:
        self._hist.clear()
        self._previa.clear()
        self._ratio.clear()

    def observar(self, agente: int, pos_xy, comandado_m: float) -> bool:
        """
        Una decisión de un agente. `comandado_m` son los metros que se le
        pidieron recorrer en esta decisión (|v| ya escalada, por dt real).

        Devuelve True si el agente NO está siguiendo la orden.
        """
        p = np.asarray(pos_xy, dtype=np.float64)[:2]
        previa = self._previa.get(agente)
        self._previa[agente] = p
        if previa is None:
            return False

        avance = float(np.linalg.norm(p - previa))
        cola = self._hist.setdefault(agente, deque(maxlen=self.ventana))
        cola.append((avance, float(comandado_m)))
        if not self.activo or len(cola) < self.ventana:
            return False

        comandado = sum(c for _a, c in cola)
        if comandado < self.comando_minimo:
            return False              # se pidió poca traslación: no se juzga
        recorrido = sum(a for a, _c in cola)
        self._ratio[agente] = recorrido / comandado
        return self._ratio[agente] < self.umbral

    def seguimiento(self, agente: int) -> Optional[float]:
        """Último cociente calculado, o None si aún no se juzgó."""
        return self._ratio.get(agente)


def _replica_simulada(poses_ini: Dict[int, np.ndarray], semilla: int,
                      decisiones: int, n_agentes: int,
                      factor: float) -> Optional[float]:
    """
    Corre en simulación EL MISMO episodio: misma pose inicial medida, misma
    semilla, mismas decisiones, mismo factor. Devuelve su cobertura AoI.

    ⚠ POR QUÉ EXISTE. Comparar el hardware contra un promedio de simulación
    mezcla dos diferencias en un solo número: la del sistema físico y la de
    la condición inicial, que en hardware la pone la mano del operador y en
    simulación un sorteo. La segunda no es un defecto del sistema y no
    debería contaminar la conclusión: se midió que cambiar sólo el arranque
    mueve la desviación de la cobertura de 0.0213 a 0.1061.

    Pareando cada episodio con su propia réplica, la condición inicial deja
    de ser una variable: la diferencia que queda es atribuible al hardware
    —retardo de actuación, ruido de captura, calibración de ruedas—, que es
    lo que la tesis quiere medir. Además vuelve irrelevante la precisión con
    que se coloquen los robots, porque la réplica arranca de donde QUEDARON,
    no de donde se los quiso poner.

    ⚠ DIFERENCIAS DECLARADAS de la réplica (no es un gemelo exacto):
      · corre sin CBF ni capa de escape — esas viven en el coordinador, no
        en el entorno desnudo. La réplica es "la política sola, desde este
        arranque", no "el sistema completo sin hardware".
      · el `factor` se aplica a la acción, igual que en hardware.

    Retorna None si no se puede construir la réplica (falta el modelo, falta
    alguna pose): el informe lo reporta como réplica ausente, no como cero.
    """
    try:
        from stable_baselines3 import PPO
        from lib.swarm_env_skeleton import make_env
        from coordinador_enjambre import RUTA_MODELO
    except Exception:                                      # noqa: BLE001
        return None
    if any(i not in poses_ini for i in range(n_agentes)):
        return None

    try:
        env = make_env(n_agents=n_agentes,
                       arena_size=(cfg.ARENA_WX_M, cfg.ARENA_WY_M),
                       max_steps=decisiones, comm_radius=1.0, seed=semilla)
        obs, _ = env.reset(seed=semilla)
        modelo = PPO.load(str(RUTA_MODELO), device="cpu")

        # Sembrar el entorno con la pose REAL medida en la plataforma.
        for i, a in enumerate(env.agents):
            est = env._estados[a]
            est[0], est[1], est[2] = (float(poses_ini[i][0]),
                                      float(poses_ini[i][1]),
                                      float(poses_ini[i][2]))
        env._field.update_aoi_grid(
            np.array([env._estados[a][:2] for a in env.agents]))
        obs = env._get_all_observations()

        for _ in range(decisiones):
            acciones = {}
            for a in env.agents:
                acc, _ = modelo.predict(obs[a], deterministic=True)
                acciones[a] = (np.asarray(acc, dtype=np.float32).flatten()
                               * factor)
            obs, _r, term, trunc, _i = env.step(acciones)
            if not env.agents or all(term.values()) or all(trunc.values()):
                break
        return 1.0 - float(np.mean(env._field._grid_aoi))
    except Exception:                                      # noqa: BLE001
        return None


def _contadores_fuente(fuente: Any) -> Dict[str, Any]:
    """Foto de los contadores de la fuente de poses (0 si no los tiene)."""
    return {
        "consultas": int(getattr(fuente, "consultas", 0)),
        "fallidas": int(getattr(fuente, "fallos_consulta", 0)),
        "rechazos": dict(getattr(fuente, "rechazos_pose", None) or {}),
        "bytes_descartados": int(getattr(fuente, "bytes_descartados", 0)),
        "consultas_con_descarte": int(
            getattr(fuente, "consultas_con_descarte", 0)),
    }


def _delta_contadores_fuente(antes: Dict[str, Any],
                             fuente: Any) -> Dict[str, Any]:
    """
    Lo que la fuente contó DURANTE un episodio, para el CSV de episodios
    (decisión del autor, 2026-09-24). Hasta entonces estos contadores sólo
    salían por consola al cerrar la sesión: la auditoría de los
    congelamientos no pudo saber si hubo rechazos de pose en esos episodios.
    """
    ahora = _contadores_fuente(fuente)
    rechazos = {k: ahora["rechazos"].get(k, 0) - antes["rechazos"].get(k, 0)
                for k in ahora["rechazos"]}
    rechazos = {k: v for k, v in rechazos.items() if v}
    return {
        "poses_consultas": ahora["consultas"] - antes["consultas"],
        "poses_fallidas": ahora["fallidas"] - antes["fallidas"],
        "poses_rechazadas": int(sum(rechazos.values())),
        "poses_rechazos_motivo": ";".join(
            f"{k}:{v}" for k, v in sorted(rechazos.items())),
        "poses_bytes_descartados": (ahora["bytes_descartados"]
                                    - antes["bytes_descartados"]),
        "poses_consultas_con_descarte": (ahora["consultas_con_descarte"]
                                         - antes["consultas_con_descarte"]),
    }


def _correr_episodio(coord, canal, fuente, registro, marca, decisiones,
                     rpm_aborto, n_agentes, detector, semilla,
                     seguimiento=None, diag=None):
    """
    Un episodio completo. Devuelve el dict de métricas.

    ⚠ POSE REPETIDA → RETROCESO (2026-09-24). Hasta esa fecha, 10
    decisiones con la misma pose abortaban el episodio, y entre la primera
    repetición y el aborto el robot seguía andando a ciegas ~1 s, escape
    incluido (auditoría de los congelamientos de borde). El mismo día se
    pasó a PAUSAR al agente en la primera repetición, y enseguida se
    reemplazó: el encargado del Robotat confirmó que la pose se congela
    porque el robot entró en un punto ciego de las cámaras —Motive retiene
    la última pose registrada— y un robot pausado ahí adentro no vuelve a
    ser visto nunca.

    Ahora, a la PRIMERA repetición el agente RETROCEDE por el camino por el
    que entró: el canal le manda al revés, y más despacio, las órdenes que
    recibió en la ventana anterior. Si su pose vuelve a cambiar, se reanuda
    en el acto; si el retroceso se agota y la pose sigue repetida, queda
    parado y el episodio se aborta. Los parámetros y de dónde sale cada uno,
    en `retroceso_congelamiento.py`.

    Los retrocesos afectan la cobertura, así que quedan registrados: la
    columna `en_retroceso` del CSV de decisiones y, por episodio,
    `retrocesos_a{i}`, `decisiones_retroceso_a{i}`, `decisiones_retroceso`,
    `frac_decisiones_retroceso`, `retroceso_max_s`,
    `retrocesos_recuperados` y `retrocesos_detalle`.
    ⚠ La réplica pareada NO reproduce los retrocesos: un episodio con
    retrocesos no es comparable con su réplica sin decidir antes cómo
    tratarlo.

    En retroceso, el camino "comandado" del agente es cero para el detector
    de seguimiento —su pose está congelada: no hay recorrido medido con qué
    compararlo— y no se le exige desplazamiento; al reanudar, el reloj de
    "sin desplazamiento" arranca de nuevo.

    Excepción, heredada de la pausa: si TODOS los agentes tienen la pose
    repetida a la vez durante `detector.umbral` decisiones seguidas, no es
    un punto ciego —son por marcador: en los 15 congelamientos auditados los
    otros cuatro siguieron vivos en la misma respuesta— sino el flujo entero
    detenido, y se aborta sin esperar a los retrocesos.

    `diag`: registro de diagnóstico de poses, si está activo; recibe el
    inicio y el fin de cada retroceso.
    """
    t0 = time.perf_counter()
    t_previo = t0
    abortado, motivo = False, ""
    tiempos_ciclo_ms: List[float] = []
    dist: Dict[int, float] = {}
    previa: Dict[int, np.ndarray] = {}
    t_mov: Dict[int, float] = {}
    # Regla de 10 s: inicio de la orden sostenida y comienzo del tramo sin
    # orden de cada agente (ver `MARGEN_RETARDO_ESTANCAMIENTO_S`).
    t_orden: Dict[int, Optional[float]] = {}
    t_sin_orden: Dict[int, Optional[float]] = {}
    col_015: set = set()
    col_022: set = set()
    d_pared_min: Dict[int, float] = {}
    # Retroceso por pose repetida (ver el docstring). Un mando directo no se
    # hereda de otro episodio, y el retroceso sólo deshace órdenes de éste.
    if hasattr(canal, "liberar_mandos"):
        canal.liberar_mandos()
    if hasattr(canal, "olvidar_historial"):
        canal.olvidar_historial()
    gestor = GestorRetroceso(canal, periodo_s=PERIODO_DECISION_S)
    decisiones_retroceso: Dict[int, int] = {}
    todos_congelados = 0
    paso = -1

    for paso in range(decisiones):
        if not coord._avanzar(coord.pasos_por_decision):
            abortado, motivo = True, "el entorno pidió terminar"
            break
        lat = fuente._latencias[-1] if fuente._latencias else 0.0
        t_d0 = time.perf_counter()
        # Los que están en retroceso AHORA son los que el canal mueve con su
        # mando en esta decisión (la acción de la política no sale). Uno que
        # empiece más abajo manda en el acto y cuenta desde la próxima.
        en_retroceso_al_enviar = gestor.en_retroceso
        coord._decidir_y_actuar()
        tiempos_ciclo_ms.append((lat + time.perf_counter() - t_d0) * 1000.0)

        # ⚠ HALLAZGO (2026-09-24): con un robot fuera de la red, cada envío
        # intentaba reabrir su enlace y bloqueaba el lazo ~0.45 s por
        # decisión; el episodio terminaba a las 4 decisiones como
        # "antigüedad de pose sobre el umbral" y el motivo real no aparecía.
        # Se perdieron así 5 intentos seguidos. Un enlace que no se pudo
        # reabrir en el mismo envío es un robot que no está recibiendo
        # órdenes: se aborta con ese motivo. Un corte que se reabre al
        # instante (RST y reconexión en <0.5 s) no llega acá.
        caidos = (canal.enlaces_caidos()
                  if hasattr(canal, "enlaces_caidos") else [])
        if caidos:
            robots = ", ".join(str(cfg.MAPEO_AGENTES[i].id_robot)
                               for i in caidos)
            abortado, motivo = True, (
                f"enlace de ruedas caído: robot {robots} no recibe órdenes "
                f"(¿apagado, sin batería o fuera del WiFi?)")
            break

        if len(registro) < marca + n_agentes:
            continue
        filas = registro[-n_agentes:]
        ahora = time.perf_counter()
        # dt REAL, no el nominal: si el lazo se desbocara, el camino
        # comandado calculado con 0.1 s fijo sería ficción y el detector
        # de seguimiento acusaría a un robot sano.
        dt_dec = ahora - t_previo
        t_previo = ahora
        # `factor_total` incluye la rampa de arranque seguro, así que
        # durante los primeros 50 pasos el comando es menor y el cociente
        # sigue valiendo 1 en un robot sano.
        factor_ahora = canal.factor_total() if hasattr(
            canal, "factor_total") else 1.0
        poses: Dict[int, np.ndarray] = {}
        congelados_ahora = 0
        for f in filas:
            ag = int(f["agente"])
            p = np.array([f["pose_env_x"], f["pose_env_y"]])
            poses[ag] = p
            dp = min(p[0], cfg.ARENA_WX_M - p[0], p[1], cfg.ARENA_WY_M - p[1])
            d_pared_min[ag] = min(d_pared_min.get(ag, float("inf")), float(dp))
            if ag in previa:
                avance = float(np.linalg.norm(p - previa[ag]))
                dist[ag] = dist.get(ag, 0.0) + avance
                if avance > 0.002:
                    t_mov[ag] = ahora
            else:
                t_mov[ag] = ahora
            previa[ag] = p
            if ag in en_retroceso_al_enviar:
                decisiones_retroceso[ag] = decisiones_retroceso.get(ag, 0) + 1
            # ── Pose repetida: RETROCESO del agente ──────────────────────
            # Pose COMPLETA (x, y, θ): de eso depende que no haya
            # retrocesos falsos (ver `DetectorCongelamiento.observar`).
            pose_env = (f["pose_env_x"], f["pose_env_y"], f["pose_env_th"])
            detector.observar(ag, pose_env)
            repeticiones = detector.repeticiones(ag)
            if repeticiones:
                congelados_ahora += 1
            evento = gestor.observar(ag, repeticiones, ahora, paso,
                                     pose_env, dp)
            rob = cfg.MAPEO_AGENTES[ag].id_robot
            if evento == "inicio":
                r = gestor.activos[ag]
                print(f"  ↩ agente {ag} (robot {rob}): pose repetida en "
                      f"({p[0]:.2f}, {p[1]:.2f}), a {dp:.2f} m de la pared — "
                      f"RETROCEDE por donde entró: deshace "
                      f"{r.plan.ventana_s:.2f} s de órdenes y sigue "
                      f"{r.plan.margen_s:.1f} s más, "
                      f"{100 * r.plan.camino_m:.1f} cm, en ≤ "
                      f"{r.plan.duracion_s + gestor.espera_s:.1f} s "
                      f"(decisión {paso})")
                if diag is not None:
                    diag.registrar_evento(
                        "retroceso_inicio", agente=ag, paso=paso,
                        ventana_s=r.plan.ventana_s,
                        margen_s=r.plan.margen_s,
                        duracion_plan_s=r.plan.duracion_s,
                        camino_m=r.plan.camino_m, tramos=len(r.plan.tramos),
                        d_pared_m=dp)
            elif evento in ("recuperada", "sigue_congelada"):
                r = gestor.terminados[-1]
                if diag is not None:
                    diag.registrar_evento(
                        "retroceso_fin", agente=ag, paso=paso,
                        resultado=r.resultado, duracion_s=r.duracion_s)
                if evento == "recuperada":
                    t_mov[ag] = ahora
                    print(f"  ▶ agente {ag} (robot {rob}): pose viva otra "
                          f"vez tras {r.duracion_s:.1f} s de retroceso — "
                          f"reanuda")
                else:
                    abortado = True
                    motivo = (f"marcador CONGELADO: agente {ag} (robot "
                              f"{rob}) sigue sin captura tras retroceder "
                              f"{r.duracion_s:.1f} s "
                              f"({100 * r.plan.camino_m:.1f} cm comandados)"
                              f" — pose congelada en ({p[0]:.2f}, "
                              f"{p[1]:.2f}), a {dp:.2f} m de la pared")
                    break
            # ── Seguimiento: ¿recorre lo que se le comanda? ──────────────
            # El estancamiento no cubre esto: un robot que gira en el lugar
            # mueve su marcador mucho más de 2 mm. Ver `DetectorSeguimiento`.
            # En retroceso la pose está congelada: no hay recorrido medido
            # con qué comparar lo comandado.
            comandado_m = (0.0 if ag in en_retroceso_al_enviar
                           else abs(float(f["v_ejecutada"])) * factor_ahora
                           * dt_dec)
            if seguimiento is not None and seguimiento.observar(
                    ag, p, comandado_m):
                abortado = True
                motivo = (f"agente {ag} NO SIGUE el comando: recorrió el "
                          f"{100*seguimiento.seguimiento(ag):.0f} % de lo "
                          f"comandado en los últimos "
                          f"{seguimiento.ventana} pasos (mínimo "
                          f"{100*seguimiento.umbral:.0f} %) — rueda trabada, "
                          f"batería caída o el robot gira en vez de avanzar")
                break
        if abortado:
            break

        # ── Todos congelados a la vez: no es un punto ciego ──────────────
        todos_congelados = (todos_congelados + 1
                            if congelados_ahora >= n_agentes else 0)
        if todos_congelados >= detector.umbral:
            abortado = True
            motivo = (f"marcadores CONGELADOS de todos los agentes: "
                      f"{todos_congelados} decisiones seguidas sin ninguna "
                      f"pose viva (el flujo entero, no un punto ciego)")
            break

        ids = sorted(poses)
        for a_ in range(len(ids)):
            for b_ in range(a_ + 1, len(ids)):
                d = float(np.linalg.norm(poses[ids[a_]] - poses[ids[b_]]))
                if d < 0.15:
                    col_015.add((ids[a_], ids[b_]))
                if d < 0.22:
                    col_022.add((ids[a_], ids[b_]))

        pico = abs(filas[-1]["rpm_pico"])
        if pico > rpm_aborto:
            abortado, motivo = True, f"rpm {pico:.0f} > {rpm_aborto:.0f}"
            break
        fuera = [ag for ag, p in poses.items()
                 if not (0 <= p[0] <= cfg.ARENA_WX_M
                         and 0 <= p[1] <= cfg.ARENA_WY_M)]
        if fuera:
            abortado, motivo = True, f"agente {fuera[0]} fuera de la arena"
            break
        if fuente.agentes_vencidos():
            abortado, motivo = True, "antigüedad de pose sobre el umbral"
            break
        for f in filas:
            ag = int(f["agente"])
            # Período de orden con histéresis (arreglo del 2026-10-02).
            con_orden = abs(f["v_ejecutada"]) > 0.02
            if con_orden:
                t_sin_orden[ag] = None
                if t_orden.get(ag) is None:
                    t_orden[ag] = ahora
            else:
                if t_sin_orden.get(ag) is None:
                    t_sin_orden[ag] = ahora
                if (t_orden.get(ag) is not None
                        and ahora - t_sin_orden[ag]
                        >= CORTE_ORDEN_ESTANCAMIENTO_S):
                    t_orden[ag] = None
            if ag in gestor.en_retroceso:
                continue            # retrocede a ciegas: no se le exige nada
            if con_orden:
                t_ref = max(t_mov.get(ag, ahora),
                            t_orden[ag] + MARGEN_RETARDO_ESTANCAMIENTO_S)
                if ahora - t_ref > 10.0:
                    abortado = True
                    motivo = f"agente {ag} sin desplazamiento por 10 s"
                    break
        if abortado:
            break

    # Retrocesos abiertos al terminar: se cierran en la última decisión, y
    # nadie queda con mando directo para lo que siga (colocación, otro
    # episodio).
    gestor.cerrar_todos(max(paso, 0), time.perf_counter(),
                        "episodio_abortado" if abortado
                        else "fin_del_episodio")
    if hasattr(canal, "liberar_mandos"):
        canal.liberar_mandos()

    # Detención al final de TODO episodio, no sólo de los abortados.
    # ⚠ HALLAZGO (2026-09-30): al terminar un episodio VÁLIDO no se mandaba
    # nada; cada robot seguía con su última orden mientras la sesión calculaba
    # la réplica simulada, hasta que la guía siguiente latía (0,0). Se midieron
    # 25–56 cm de avance a ciegas, sin CBF ni escape, con robots a 2 cm de la
    # pared. No cambia nada dentro del episodio: las métricas ya están cerradas.
    canal.detener_todo()
    if abortado:
        print(f"  ⛔ {motivo}")

    tramo = registro[marca:]
    cob = 1.0 - float(np.mean(coord.env._field._grid_aoi))

    # ── ¿El episodio corrió al ritmo que dice? ────────────────────────────
    # 500 decisiones a 0.1 s deben tardar ~50 s de RELOJ DE PARED. Si tardan
    # mucho menos, el lazo no está durmiendo y los robots tuvieron menos
    # tiempo real para moverse del que la métrica supone: la cobertura queda
    # sin sentido. Pasó el 2026-09-05 —episodios de 7 s en vez de 50— y no
    # había nada que lo detectara. Se invalida el episodio, que es lo mismo
    # que se hace con cualquier otra corrupción del dato.
    esperado_s = decisiones * PERIODO_DECISION_S
    duracion = time.perf_counter() - t0
    if not abortado and duracion < 0.75 * esperado_s:
        abortado = True
        motivo = (f"ritmo del lazo: {len(tiempos_ciclo_ms)} decisiones en "
                  f"{duracion:.1f} s, se esperaban ~{esperado_s:.0f} s "
                  f"({len(tiempos_ciclo_ms)/max(duracion,1e-9):.0f} Hz en vez "
                  f"de {1/PERIODO_DECISION_S:.0f} Hz). Los robots tuvieron "
                  f"menos tiempo real del que la métrica supone.")
        print(f"  ⛔ {motivo}")

    return {
        "valido":        int(not abortado),
        "motivo":        motivo,
        "semilla":       semilla,
        "decisiones":    len(tiempos_ciclo_ms),
        "duracion_s":    time.perf_counter() - t0,
        "cobertura_aoi": cob,
        "colisiones_015": len(col_015),
        "colisiones_022": len(col_022),
        "d_pared_min":   min(d_pared_min.values()) if d_pared_min else 0.0,
        "viola_018":     sum(1 for v in d_pared_min.values() if v < 0.18),
        "frac_cbf":      float(np.mean([f["cbf_intervino"] for f in tramo]))
                         if tramo else 0.0,
        "n_escape":      int(sum(f["en_escape"] for f in tramo)),
        "frac_vecino":   float(np.mean([f["con_vecino"] for f in tramo]))
                         if tramo else 0.0,
        "dist_min_robot": min(dist.values()) if dist else 0.0,
        "dist_max_robot": max(dist.values()) if dist else 0.0,
        "ciclo_p95_ms":  float(np.percentile(tiempos_ciclo_ms, 95))
                         if tiempos_ciclo_ms else 0.0,
        "ciclos_sobre_100ms": sum(1 for t in tiempos_ciclo_ms if t > 100.0),
        # ── Retrocesos por pose repetida (ver el docstring) ──────────────
        "decisiones_retroceso": int(sum(decisiones_retroceso.values())),
        "frac_decisiones_retroceso": (
            sum(decisiones_retroceso.values())
            / (n_agentes * len(tiempos_ciclo_ms))
            if tiempos_ciclo_ms else 0.0),
        "retroceso_max_s": max((r.duracion_s for r in gestor.terminados),
                               default=0.0),
        "retrocesos_recuperados": sum(1 for r in gestor.terminados
                                      if r.resultado == "recuperada"),
        "retrocesos_detalle": ";".join(r.como_texto()
                                       for r in gestor.terminados),
        **{f"retrocesos_a{i}": sum(1 for r in gestor.terminados
                                   if r.agente == i)
           for i in range(n_agentes)},
        **{f"decisiones_retroceso_a{i}": decisiones_retroceso.get(i, 0)
           for i in range(n_agentes)},
    }


def _informe_evaluacion(episodios, factor, n_agentes, salidas):
    """Media y desviación sobre los VÁLIDOS, más la tabla comparativa."""
    val = [e for e in episodios if e.get("valido")]
    print()
    print("=" * 72)
    print(f"EVALUACIÓN — {len(val)} episodios válidos de {len(episodios)} "
          f"intentos")
    print("=" * 72)
    if not val:
        for e in episodios:
            print(f"  episodio {e['episodio']}: INVÁLIDO — {e.get('motivo','')}")
        return ResultadoEtapa(7, "FALLO", "ningún episodio válido",
                              salidas=salidas)

    def ms(clave):
        v = [float(e[clave]) for e in val]
        return float(np.mean(v)), (float(np.std(v)) if len(v) > 1 else 0.0)

    filas = [
        ("cobertura AoI",          "cobertura_aoi",   "{:.4f}"),
        ("colisiones < 0.15 m",    "colisiones_015",  "{:.2f}"),
        ("colisiones < 0.22 m",    "colisiones_022",  "{:.2f}"),
        ("d_pared mínima [m]",     "d_pared_min",     "{:.6f}"),
        ("agentes que violan 0.18", "viola_018",      "{:.2f}"),
        ("intervención CBF",       "frac_cbf",        "{:.3f}"),
        ("activaciones de escape", "n_escape",        "{:.1f}"),
        ("decisiones con vecino",  "frac_vecino",     "{:.3f}"),
        ("distancia mín. por robot [m]", "dist_min_robot", "{:.2f}"),
        ("ciclo p95 [ms]",         "ciclo_p95_ms",    "{:.1f}"),
    ]
    print(f"{'métrica':<32} {'media':>12} {'desv':>10}")
    for etiqueta, clave, fmt in filas:
        m, s = ms(clave)
        print(f"{etiqueta:<32} {fmt.format(m):>12} {fmt.format(s):>10}")

    cob_m, cob_s = ms("cobertura_aoi")
    col_m, _ = ms("colisiones_015")
    dp_m, _ = ms("d_pared_min")
    con_col = 100 * sum(1 for e in val if e["colisiones_015"] > 0) / len(val)
    print()
    pareados = [(float(e["cobertura_aoi"]), float(e["cobertura_replica"]))
                for e in val if e.get("cobertura_replica") is not None]
    if pareados:
        d = np.array([h - s for h, s in pareados])
        rep_m = float(np.mean([s for _h, s in pareados]))
        print(f"COMPARACIÓN PAREADA  ({len(pareados)} de {len(val)} episodios)")
        print("  Cada episodio contra SU RÉPLICA: misma pose inicial medida,")
        print("  misma semilla, mismas decisiones, mismo factor. La condición")
        print("  inicial deja de ser una variable y la diferencia que queda")
        print("  es atribuible al hardware.")
        print(f"    hardware {cob_m:.4f}   ·   réplica {rep_m:.4f}")
        print(f"    diferencia media {d.mean():+.4f} ± {d.std():.4f}  "
              f"({100*d.mean()/rep_m:+.1f} % de la réplica)")
        print("    ⚠ SESGADA A LA BAJA — NO CITAR ESTA DIFERENCIA. La réplica")
        print("      corre el env de entrenamiento SIN CBF ni escape: es 'la")
        print("      política sola desde este arranque', no el sistema completo.")
        print("      La comparación válida corre la MISMA pila con las tres")
        print("      capas contra el simulador: `replica_con_capas.py` +")
        print("      `analizar_replicas.py` (BITACORA_TECNICA, evaluación 11-09).")
        print()
    print("COMPARACIÓN CONTRA SIMULACIÓN (no pareada — referencia histórica)")
    print(f"  cobertura AoI     hardware {cob_m:.4f} ± {cob_s:.4f}   ·  "
          f"Webots {REF_EVAL['cobertura_webots']}  ·  "
          f"Python {REF_EVAL['cobertura_python']}")
    print(f"  colisiones 0.15 m hardware {col_m:.2f} por episodio "
          f"({con_col:.0f} % de episodios con ≥1)   ·  "
          f"Webots {REF_EVAL['colisiones']}")
    print(f"  d_pared mínima    hardware {dp_m:.6f}   ·  "
          f"Webots {REF_EVAL['d_pared']}")
    print()
    # Diversidad de los arranques (2026-09-22): con n chico una muestra al
    # azar puede salir amontonada, y las exclusiones pueden sesgarla. Nunca
    # tumba el informe: es un diagnóstico más.
    try:
        from diversidad_arranques import informe as _informe_diversidad
        _informe_diversidad(episodios, n_agentes)
    except Exception as exc:                                  # noqa: BLE001
        print(f"DIVERSIDAD DE LOS ARRANQUES: no se pudo calcular ({exc})")
    print()
    print("CAVEATS")
    print("  · Las semillas fijan las trayectorias de los objetivos, NO las")
    print("    poses iniciales: en hardware son las que dejó la colocación")
    print("    (a mano o automática, ver columna `colocacion`). Por eso la")
    print("    comparación de referencia NO es pareada; la")
    print("    pareada de arriba sí lo es, pero su réplica está sesgada (sin")
    print("    capas): la que se cita es la de `replica_con_capas.py`.")
    print("  · Los blancos de colocación se sortean de la distribución de")
    print(f"    entrenamiento con tolerancia ±{TOL_COLOCACION_M*100:.0f} cm. "
          f"La réplica arranca de")
    print("    la pose REAL medida, no del blanco, así que el error de")
    print("    colocación no entra en la comparación pareada.")
    print(f"  · El factor {factor:.2f} escala la acción comandada pero NO la")
    print("    observación: la política 'cree' ir más rápido de lo que va.")
    invalidos = [e for e in episodios if not e.get("valido")]
    if invalidos:
        print()
        print(f"EPISODIOS INVÁLIDOS ({len(invalidos)}):")
        for e in invalidos:
            print(f"  · episodio {e['episodio']}: {e.get('motivo','')}")
    print("=" * 72)

    veredicto = "OK" if len(val) >= 5 else "ADVERTENCIA"
    return ResultadoEtapa(
        7, veredicto,
        f"{len(val)} episodios válidos · cobertura {cob_m:.4f}±{cob_s:.4f} · "
        f"colisiones<0.15 {col_m:.2f}/ep",
        salidas=salidas)


def _correr_escalon(coord, canal, fuente, registro: List[Dict[str, Any]],
                    marca: int, segundos: float,
                    rpm_aborto: float, n_agentes: int = 1) -> Dict[str, Any]:
    """
    Corre un escalón del barrido con diagnóstico en vivo, veredicto
    acumulado cada 10 s y aborto automático.
    """
    t0 = time.perf_counter()
    t_diag = t0
    t_veredicto = t0
    # (el seguimiento de movimiento y la pose previa pasaron a ser POR
    # AGENTE — ver `t_ultimo_mov_ag` y `pose_previa_ag` más abajo)
    abortado, razon_aborto = False, ""

    # Seguimiento por DISTANCIAS ACUMULADAS, no por cociente paso a paso: a
    # velocidades bajas el desplazamiento por decisión (≈1 mm) es del orden
    # del ruido de la captura, y el cociente instantáneo sería basura.
    #
    # TODO por agente: el coordinador emite una fila por agente y por
    # decisión, así que `registro[-1]` era la del ÚLTIMO agente del bucle
    # —el 0 con un robot, uno arbitrario con cinco—. Medir seguimiento y
    # oscilación sobre un agente cualquiera de un enjambre no dice nada del
    # enjambre; peor, un robot trabado quedaría invisible si el muestreado
    # es otro.
    dist_real: Dict[int, float] = {}
    dist_comandada: Dict[int, float] = {}
    signos_w: Dict[int, List[float]] = {}
    pose_previa_ag: Dict[int, np.ndarray] = {}
    t_ultimo_mov_ag: Dict[int, float] = {}
    rpm_pico = 0.0
    #: separación mínima observada entre robots durante el escalón. Sólo
    #: tiene sentido con más de uno, y es la magnitud de seguridad propia
    #: del enjambre: dos robots acercándose es lo que el CBF debe evitar.
    separacion_min = float("inf")
    #: decisiones en que CADA agente vio al menos un vecino.
    #:
    #: ⚠ HALLAZGO (2026-09-02): se corrió el enjambre con dos robots y el
    #: `neighbor_embedding` (obs 8–15) quedó en CERO las 775 decisiones de
    #: los dos. Estuvieron entre 1.13 y 1.40 m separados, y `comm_radius` es
    #: 1.0 m: nunca se vieron. Para la política fueron dos corridas de un
    #: robot en paralelo, y volvió a saturar `v` igual que con n=1.
    #:
    #: Sin este contador, la corrida se veía perfectamente normal — dos
    #: robots moviéndose, CSV lleno, veredictos ESTABLE. Un enjambre en el
    #: que nadie ve a nadie NO es un enjambre, y hay que decirlo.
    con_vecino: Dict[int, int] = {}
    decisiones_ag: Dict[int, int] = {}

    # Punto 4 de la decisión 2026-08-22: instrumentar el riesgo de exceder
    # el presupuesto de 100 ms por decisión. `tiempo_ciclo` = la última
    # consulta de poses (una por decisión, ver adaptadores_robotat) + todo
    # `_decidir_y_actuar` (transformación, inferencia, filtro, envío). Si
    # esto se pasa del presupuesto de forma sistemática, el lazo no corre a
    # la frecuencia que la política espera y la corrida queda invalidada.
    tiempos_ciclo_ms: List[float] = []
    ciclos_sobre_presupuesto = 0

    while time.perf_counter() - t0 < segundos:
        if not coord._avanzar(coord.pasos_por_decision):
            abortado, razon_aborto = True, "el entorno pidió terminar"
            break
        lat_consulta_s = fuente._latencias[-1] if fuente._latencias else 0.0
        t_decision0 = time.perf_counter()
        coord._decidir_y_actuar()
        t_decision_s = time.perf_counter() - t_decision0

        tiempo_ciclo_ms = (lat_consulta_s + t_decision_s) * 1000.0
        tiempos_ciclo_ms.append(tiempo_ciclo_ms)
        if tiempo_ciclo_ms > PERIODO_DECISION_S * 1000.0:
            ciclos_sobre_presupuesto += 1

        if not registro:
            continue
        # Las N filas de ESTA decisión, una por agente.
        filas_dec = registro[-n_agentes:]
        ult = filas_dec[-1]
        rpm_pico = max(rpm_pico, abs(ult["rpm_pico"]))
        dt = coord.pasos_por_decision * 0.01
        ahora_mov = time.perf_counter()
        poses_dec: Dict[int, np.ndarray] = {}

        for fila in filas_dec:
            ag = int(fila.get("agente", 0))
            pose = np.array([fila["pose_env_x"], fila["pose_env_y"]])
            poses_dec[ag] = pose
            if ag in pose_previa_ag:
                avance = float(np.linalg.norm(pose - pose_previa_ag[ag]))
                dist_real[ag] = dist_real.get(ag, 0.0) + avance
                dist_comandada[ag] = (
                    dist_comandada.get(ag, 0.0)
                    + abs(fila["v_ejecutada"]) * fila["factor_total"] * dt
                )
                if avance > 0.002:
                    t_ultimo_mov_ag[ag] = ahora_mov
            else:
                t_ultimo_mov_ag[ag] = ahora_mov
            pose_previa_ag[ag] = pose
            signos_w.setdefault(ag, []).append(
                math.copysign(1.0, fila["w_ejecutada"]))

            # ¿este agente vio a alguien? El embedding de vecinos son las
            # dimensiones 8–15 de la observación; todas en cero significa
            # "ningún vecino dentro de comm_radius".
            decisiones_ag[ag] = decisiones_ag.get(ag, 0) + 1
            if any(abs(fila.get(f"obs_{k:02d}", 0.0)) > 1e-9
                   for k in range(8, 16)):
                con_vecino[ag] = con_vecino.get(ag, 0) + 1

        # ── ABORTOS AUTOMÁTICOS ──────────────────────────────────────────
        if abs(ult["rpm_pico"]) > rpm_aborto:
            abortado = True
            razon_aborto = (f"rpm comandada {abs(ult['rpm_pico']):.0f} > "
                            f"{rpm_aborto:.0f}")
            break

        fuera = [(ag, p) for ag, p in poses_dec.items()
                 if not (0.0 <= p[0] <= cfg.ARENA_WX_M
                         and 0.0 <= p[1] <= cfg.ARENA_WY_M)]
        if fuera:
            ag, p = fuera[0]
            abortado = True
            razon_aborto = (f"agente {ag} fuera del área de trabajo: "
                            f"({p[0]:.3f}, {p[1]:.3f})")
            break

        # Separación entre robots: la magnitud de seguridad del enjambre. Un
        # contacto es daño físico, y sobre una plataforma elevada puede ser
        # una caída. Se aborta por debajo del radio de contacto de chasis
        # (D_SEPARACION_MIN_ARRANQUE_M), no del margen del CBF: hasta ahí es
        # trabajo del filtro, y abortar antes ocultaría si el CBF funciona.
        if len(poses_dec) > 1:
            ids = sorted(poses_dec)
            for a_ in range(len(ids)):
                for b_ in range(a_ + 1, len(ids)):
                    d = float(np.linalg.norm(poses_dec[ids[a_]]
                                             - poses_dec[ids[b_]]))
                    separacion_min = min(separacion_min, d)
                    if d < cfg.D_SEPARACION_MIN_ARRANQUE_M:
                        abortado = True
                        razon_aborto = (
                            f"agentes {ids[a_]} y {ids[b_]} a {d*100:.0f} cm "
                            f"(mínimo "
                            f"{cfg.D_SEPARACION_MIN_ARRANQUE_M*100:.0f} cm)")
                        break
                if abortado:
                    break
            if abortado:
                break

        if fuente.agentes_vencidos():
            abortado = True
            razon_aborto = ("antigüedad de pose por encima del umbral "
                            f"({cfg.ANTIGUEDAD_MAX_POSE_S*1000:.0f} ms)")
            break

        # Estancamiento: se mira AGENTE POR AGENTE. Con un enjambre, que el
        # conjunto se mueva no dice nada de un robot que quedó trabado.
        for fila in filas_dec:
            ag = int(fila.get("agente", 0))
            comando_no_nulo = (
                abs(fila["v_ejecutada"]) * fila["factor_total"] > 0.02
                or abs(fila["w_ejecutada"]) * fila["factor_total"] > 0.3)
            if (comando_no_nulo
                    and ahora_mov - t_ultimo_mov_ag.get(ag, ahora_mov) > 10.0):
                abortado = True
                razon_aborto = (f"agente {ag} sin desplazamiento por 10 s "
                                f"con comando no nulo")
                break
        if abortado:
            break

        # ── Diagnóstico en vivo, una vez por segundo ─────────────────────
        ahora = time.perf_counter()
        if ahora - t_diag >= 1.0:
            t_diag = ahora
            _imprimir_diagnostico(coord, registro, marca, ult)
        if ahora - t_veredicto >= 10.0:
            t_veredicto = ahora
            _imprimir_veredicto_acumulado(registro, marca, rpm_aborto,
                                          tiempos_ciclo_ms)

    if abortado:
        print(f"\n  ⛔ ABORTO: {razon_aborto}")
        canal.detener_todo()

    tramo = registro[marca:]
    # Agregación sobre agentes. El seguimiento se calcula con las distancias
    # SUMADAS, no promediando cocientes por agente: un robot que casi no se
    # movió tiene un cociente ruidoso que arrastraría el promedio, mientras
    # que sumando pesa lo que efectivamente recorrió.
    total_real = sum(dist_real.values())
    total_comandada = sum(dist_comandada.values())
    suficientes = total_comandada >= DISTANCIA_MINIMA_SEGUIMIENTO_M * n_agentes
    seguimiento = (total_real / total_comandada) if total_comandada > 0 else 0.0
    # Oscilación: promedio de la de cada agente. Acá sí conviene promediar
    # cocientes, porque es una fracción de cambios de signo y no depende de
    # cuánto recorrió cada uno.
    oscs = []
    for ag, sig in signos_w.items():
        cambios = sum(1 for a, b in zip(sig, sig[1:]) if a != b)
        oscs.append(cambios / max(1, len(sig) - 1))
    oscilacion = float(np.mean(oscs)) if oscs else 0.0
    veredicto, razon = _veredicto_escalon(seguimiento, oscilacion, abortado,
                                          suficientes)

    # Un agente que no se movió NADA mientras los demás sí es un fallo del
    # enjambre aunque el agregado se vea bien. Se reporta explícitamente.
    quietos = [ag for ag in dist_real
               if dist_real[ag] < 0.02 and dist_comandada.get(ag, 0.0) > 0.05]
    if quietos and not abortado:
        print(f"  ⚠ agentes que no se movieron: {sorted(quietos)} "
              f"(comando no nulo pero < 2 cm recorridos)")

    # Fracción de decisiones en que cada agente vio al menos un vecino.
    fracs = {ag: con_vecino.get(ag, 0) / max(1, decisiones_ag.get(ag, 1))
             for ag in decisiones_ag}
    frac_vecino = min(fracs.values()) if fracs else 0.0
    # Se nombran los agentes AISLADOS, con su fracción. La primera versión
    # disparaba por el mínimo pero listaba sólo a los de fracción CERO, así
    # que con un agente al 3 % imprimía «los agentes [] no vieron a ningún
    # vecino» — una lista vacía y una afirmación falsa a la vez.
    aislados = {ag: fr for ag, fr in fracs.items() if fr < 0.05}
    if n_agentes > 1 and aislados:
        detalle = ", ".join(f"{ag} ({fr:.0%})" for ag, fr in
                            sorted(aislados.items()))
        print(f"  ✘ SIN ENJAMBRE para: agente(s) {detalle} — fracción de "
              f"decisiones con algún vecino a la vista.")
        print(f"    Con el `neighbor_embedding` (obs 8–15) en cero, esos "
              f"agentes ven lo mismo que un robot solo y la política corre "
              f"fuera del régimen con el que se entrenó.")
        print(f"    Separación mínima observada: {separacion_min:.2f} m · "
              f"radio de comunicación: 1.00 m.")

    ciclo_p95_ms = (float(np.percentile(tiempos_ciclo_ms, 95))
                    if tiempos_ciclo_ms else 0.0)
    frac_ciclo_sobre = (ciclos_sobre_presupuesto / len(tiempos_ciclo_ms)
                        if tiempos_ciclo_ms else 0.0)
    if frac_ciclo_sobre > 0.20:
        print(f"  ⚠ {ciclos_sobre_presupuesto}/{len(tiempos_ciclo_ms)} "
              f"decisiones de este escalón superaron el presupuesto de "
              f"{PERIODO_DECISION_S*1000:.0f} ms — el lazo no corrió a la "
              f"frecuencia que la política espera. Este dato invalida la "
              f"corrida del escalón.")

    return {
        "veredicto":   veredicto,
        "razon":       razon_aborto if abortado else razon,
        "seguimiento": seguimiento,
        "oscilacion":  oscilacion,
        "dist_real_m":       total_real,
        "dist_comandada_m":  total_comandada,
        "separacion_min_m":  (separacion_min if separacion_min < float("inf")
                              else 0.0),
        "agentes_quietos":   len(quietos),
        "frac_con_vecino":   frac_vecino,
        "rpm_pico":    rpm_pico,
        "pasos":       len(tramo),
        "abortado":    int(abortado),
        "ciclo_ms_p95":            ciclo_p95_ms,
        "ciclos_sobre_presupuesto": ciclos_sobre_presupuesto,
        "frac_ciclo_sobre_presupuesto": frac_ciclo_sobre,
        "frac_cbf":    (float(np.mean([f["cbf_intervino"] for f in tramo]))
                        if tramo else 0.0),
        "n_escape":    int(sum(f["en_escape"] for f in tramo)),
    }


def _imprimir_diagnostico(coord, registro: List[Dict[str, Any]],
                          marca: int, ult: Dict[str, Any]) -> None:
    """Una línea por magnitud, con su referencia de simulación al lado."""
    tramo = registro[marca:]
    frac_cbf = float(np.mean([f["cbf_intervino"] for f in tramo])) if tramo else 0.0
    n_esc = int(sum(f["en_escape"] for f in tramo))
    x, y = ult["pose_env_x"], ult["pose_env_y"]
    d_pared = min(x, cfg.ARENA_WX_M - x, y, cfg.ARENA_WY_M - y)
    d_hot = _distancia_hotspot(coord, np.array([x, y]))
    print(f"    (v,ω)=({ult['v_ejecutada']:+.3f},{ult['w_ejecutada']:+.2f})"
          f"×{ult['factor_total']:.2f}   [{REF_SIM['accion']}]")
    print(f"    hotspot más cercano {d_hot:6.3f} m"
          f"   ·  d_pared {d_pared:5.3f} m   [{REF_SIM['pared']}]")
    print(f"    CBF {frac_cbf:5.2f} [{REF_SIM['cbf']}]"
          f"   ·  escape {n_esc} [{REF_SIM['escape']}]"
          f"   ·  rpm ({ult['rpm_izq']:+6.1f},{ult['rpm_der']:+6.1f}) "
          f"[{REF_SIM['rpm']}]")


def _distancia_hotspot(coord, pos: np.ndarray) -> float:
    """
    Distancia al hotspot más cercano.

    La ruta es `env._field.posiciones_objetivos`, la misma que usa
    `CoordinadorEnjambre._publicar_hotspots`; se accede con `getattr` para
    que un cambio de nombre degrade a NaN en el diagnóstico en vez de
    tumbar la sesión con el robot andando.
    """
    campo = getattr(coord.env, "_field", None)
    h = getattr(campo, "posiciones_objetivos", None) if campo else None
    if h is None:
        return float("nan")
    h = np.asarray(h)
    if h.ndim != 2 or h.shape[1] < 2:
        return float("nan")
    return float(np.min(np.linalg.norm(h[:, :2] - pos, axis=1)))


def _imprimir_veredicto_acumulado(registro: List[Dict[str, Any]],
                                  marca: int, rpm_aborto: float,
                                  tiempos_ciclo_ms: Optional[List[float]] = None
                                  ) -> None:
    """NORMAL / ANÓMALO cada 10 s, con la razón."""
    tramo = registro[marca:]
    if not tramo:
        return
    frac_cbf = float(np.mean([f["cbf_intervino"] for f in tramo]))
    pico = max(abs(f["rpm_pico"]) for f in tramo)
    d_pared = min(
        min(f["pose_env_x"], cfg.ARENA_WX_M - f["pose_env_x"],
            f["pose_env_y"], cfg.ARENA_WY_M - f["pose_env_y"])
        for f in tramo
    )
    razones: List[str] = []
    if frac_cbf > 0.60:
        razones.append(f"CBF interviene {frac_cbf:.2f} (sim ~0.37)")
    if pico > 0.9 * rpm_aborto:
        razones.append(f"rpm pico {pico:.0f} cerca del aborto {rpm_aborto:.0f}")
    if d_pared < 0.18:
        razones.append(f"d_pared mínima {d_pared:.3f} < 0.18 (sim nunca)")
    # Punto 4: si más de 1 de cada 5 decisiones de esta ventana se pasó del
    # presupuesto de 100 ms, el lazo no está corriendo a la frecuencia que
    # la política espera — invalida la corrida, no sólo la incomoda.
    if tiempos_ciclo_ms:
        sobre = sum(1 for t in tiempos_ciclo_ms
                   if t > PERIODO_DECISION_S * 1000.0)
        frac_sobre = sobre / len(tiempos_ciclo_ms)
        if frac_sobre > 0.20:
            razones.append(
                f"{sobre}/{len(tiempos_ciclo_ms)} decisiones superaron el "
                f"presupuesto de {PERIODO_DECISION_S*1000:.0f} ms "
                f"(p95 ciclo {np.percentile(tiempos_ciclo_ms, 95):.0f} ms)"
            )
    if razones:
        print(f"  >>> ANÓMALO: {'; '.join(razones)}")
    else:
        print(f"  >>> NORMAL (CBF {frac_cbf:.2f}, rpm pico {pico:.0f}, "
              f"d_pared {d_pared:.3f})")


# =============================================================================
# DESPACHADOR
# =============================================================================

ETAPAS_CALIBRACION: Dict[int, Tuple[str, Callable[[Contexto], ResultadoEtapa]]] = {
    0: ("conexión y parada",     etapa_0),
    1: ("correspondencia de IDs", etapa_1),
    2: ("marco y escala",        etapa_2),
    3: ("offset de rumbo",       etapa_3),
    4: ("latencias",             etapa_4),
    5: ("marcador ocluido",      etapa_5),
}


def _preparar(ctx: Contexto) -> None:
    """Aplica la calibración medida y la informa."""
    aplicados = calib.aplicar_a_config()
    print("=" * 72)
    print(f"SESIÓN '{ctx.sesion}'   robot {ctx.id_robot}   "
          f"marcador {ctx.marcador}")
    print("=" * 72)
    print("Calibración medida:")
    for linea in calib.resumen():
        print(linea)
    # `resumen()` muestra lo GUARDADO en el archivo, que puede ser de otro
    # robot que el de esta corrida —pasa apenas se calibra el marco con un
    # robot distinto—. Sin esta línea, la tabla dice `id_robot = 1` mientras
    # el encabezado dice `robot 3`, y parece que `--robot` no se respetó.
    medido_de = calib.cargar().get("id_robot")
    if medido_de is not None and int(medido_de) != ctx.id_robot:
        print(f"  ⓘ esa tabla es de lo GUARDADO (robot {medido_de}); esta "
              f"corrida usa el robot {ctx.id_robot}. La escala y el marco "
              f"son del mocap y valen igual; el offset de rumbo es por "
              f"robot.")
    if aplicados:
        print(f"  (aplicados a la configuración: {aplicados})")
    print()
    print("Configuración vigente:")
    for linea in cfg.resumen_calibracion():
        print(linea)


def correr_calibracion(ctx: Contexto,
                       solo_etapa: Optional[int] = None) -> int:
    """Etapas 0-5. Cada una exige OK de la anterior salvo `--forzar`."""
    etapas = ([solo_etapa] if solo_etapa is not None
              else sorted(ETAPAS_CALIBRACION))
    fallos = 0
    for n in etapas:
        if n not in ETAPAS_CALIBRACION:
            print(f"[sesion] etapa {n} no existe en 'calibracion'.")
            return 2

        if n > 0:
            previo = calib.veredicto_etapa(n - 1)
            if previo not in ("OK", "ADVERTENCIA"):
                if not ctx.forzar:
                    print(f"\n✘ La etapa {n-1} no dio OK (estado: {previo}). "
                          f"No se corre la etapa {n}.")
                    print("  Corregí eso, o usá --forzar bajo tu "
                          "responsabilidad.")
                    return 3
                print(f"\n⚠ --forzar: se corre la etapa {n} aunque la "
                      f"{n-1} no dio OK (estado: {previo}).")

        _titulo, funcion = ETAPAS_CALIBRACION[n]
        try:
            # Repetir una etapa suelta debe funcionar: si no se pasó por la
            # 0, las conexiones todavía no existen.
            ctx.conectar()
            resultado = funcion(ctx)
        except KeyboardInterrupt:
            ctx.detener_todo()
            print(f"\n[sesion] etapa {n} interrumpida. Robot detenido.")
            calib.registrar_etapa(n, "INTERRUMPIDA")
            return 130
        except AbortoEtapa as exc:
            ctx.detener_todo()
            resultado = ResultadoEtapa(n, "FALLO", str(exc))
        except Exception as exc:                              # noqa: BLE001
            ctx.detener_todo()
            print(f"\n[sesion] etapa {n} falló: {type(exc).__name__}: {exc}")
            calib.registrar_etapa(n, "FALLO", str(exc))
            raise
        finally:
            ctx.detener_todo()

        if "\n" in resultado.detalle:
            print(f"\n>>> ETAPA {n}: {resultado.veredicto}")
            for linea in resultado.detalle.splitlines():
                print(f"    {linea}")
        else:
            print(f"\n>>> ETAPA {n}: {resultado.veredicto}  "
                  f"{resultado.detalle}")
        if resultado.mediciones:
            calib.guardar(resultado.mediciones, etapa=f"etapa {n}")
        calib.registrar_etapa(n, resultado.veredicto, resultado.detalle)
        if not resultado.paso:
            fallos += 1
            if not ctx.forzar:
                print("\nSe detiene la sesión acá. Revisá lo de arriba.")
                return 1
    return 0 if fallos == 0 else 1


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sesion", default="calibracion",
                    choices=["calibracion", "politica", "enjambre",
                             "evaluacion"])
    ap.add_argument("--etapa", type=int, default=None,
                    help="correr una sola etapa")
    ap.add_argument("--robot", type=int, default=None,
                    help="ID del robot (0-19); por defecto, el calibrado")
    ap.add_argument("--marcador", type=int, default=None,
                    help="ID del marcador esperado")
    ap.add_argument("--candidatos", type=str, default=None,
                    help="etapa 1: lista de marcadores a escanear en UN "
                         "giro, ej. '1,2,3,4,5,71'. Por defecto escanea "
                         "1-12 + 71 + el robot/robot+1 + --marcador.")
    ap.add_argument("--factor", type=float, default=0.40,
                    help="sesión 'evaluacion': factor de velocidad FIJO. El "
                         "0.40 por defecto es el único régimen que resultó "
                         "estable en tres corridas de barrido.")
    ap.add_argument("--episodios", type=int, default=10,
                    help="sesión 'evaluacion': episodios VÁLIDOS buscados "
                         "(default 10; mínimo aceptable 5).")
    ap.add_argument("--decisiones", type=int, default=DECISIONES_POR_EPISODIO,
                    help="sesión 'evaluacion': decisiones por episodio "
                         "(default 500 = 50 s, igual que en simulación).")
    ap.add_argument("--colocacion", choices=["auto", "manual"], default="auto",
                    help="sesión 'evaluacion': 'auto' (default) = antes de "
                         "cada episodio los robots van solos a blanco y rumbo "
                         "(≤0.08 m/s, con CBF); 'manual' = el operador los "
                         "lleva con la guía.")
    ap.add_argument("--agentes", type=int, default=None,
                    help="sesión 'enjambre': cuántos robots usar. Por "
                         "defecto, todos los de MAPEO_AGENTES. Sirve para "
                         "empezar con 2 y subir, en vez de saltar a 5.")
    ap.add_argument("--puntos", type=int, default=2,
                    help="etapa 2: cuántas posiciones medir (default 2). "
                         "Con 2 el residuo RMS es 0 por construcción y no "
                         "valida nada; con 3 o más el residuo delata una "
                         "medición mal tomada. Usá 3 si la escala sale "
                         "distinta de 1.0.")
    ap.add_argument("--forzar", action="store_true",
                    help="saltear la exigencia de secuencia (con advertencia)")
    ap.add_argument("--simulador", action="store_true",
                    help="correr contra el simulador local")
    ap.add_argument("--rpm-aborto", type=float, default=RPM_CAP_LAB,
                    dest="rpm_aborto")
    ap.add_argument("--diagnostico-poses", action="store_true",
                    dest="diagnostico_poses",
                    help="sesiones 'politica', 'enjambre' y 'evaluacion': "
                         "guarda en resultados_sesion/…_diagnostico-poses."
                         "jsonl los bytes crudos del servidor y el contexto "
                         "de cada rechazo, repetición o consulta fallida "
                         "(auditoría del 2026-09-24). No cambia el "
                         "comportamiento de la sesión.")
    args = ap.parse_args(argv)
    if args.diagnostico_poses:
        cfg.DIAGNOSTICO_POSES = True

    if args.simulador:
        cfg.activar_simulador_local()
        print("[sesion] modo SIMULADOR: no hay hardware involucrado.")

    medido = calib.cargar()
    id_robot = (args.robot if args.robot is not None
                else int(medido.get("id_robot",
                                    cfg.MAPEO_AGENTES[0].id_robot)))

    # ⚠ HALLAZGO (2026-08-25): `id_robot` e `id_marcador` se guardan como
    # campos INDEPENDIENTES, medidos por etapas distintas (0 y 1) en
    # momentos distintos. Si entre una corrida y la otra cambia el
    # `--robot` (p.ej. robot 2 ayer, robot 1 hoy), el archivo termina con
    # `id_robot` de HOY e `id_marcador` de AYER — dos robots distintos
    # combinados como si fueran uno. Pasó en el laboratorio: id_robot=1,
    # id_marcador=2 (medido para el robot 2). Por eso `medido["id_marcador"]`
    # sólo se usa si quedó medido para ESTE MISMO id_robot; si no coincide,
    # se descarta como el dato viejo que es y se recalcula por la
    # correspondencia fija de la plataforma.
    #
    # OJO: comparar contra `medido["id_robot"]` NO alcanza — la etapa 0 lo
    # pisa en cada corrida, así que tras correr etapa 0 con el robot 1 el
    # `id_marcador` de ayer (robot 2) "coincidía" igual. El único campo que
    # ata el marcador guardado a un robot es `id_marcador_para_robot`, que
    # escribe sólo la etapa 1. Si falta (archivo de antes de este arreglo),
    # no hay forma de saber para qué robot se midió: se descarta.
    id_marcador_medido_para_este_robot = (
        "id_marcador" in medido
        and medido.get("id_marcador_para_robot") == id_robot
    )
    if args.marcador is not None:
        marcador = args.marcador
    elif id_marcador_medido_para_este_robot:
        marcador = int(medido["id_marcador"])
    else:
        if "id_marcador" in medido and not id_marcador_medido_para_este_robot:
            medido_para = medido.get("id_marcador_para_robot", "desconocido")
            print(f"[sesion] ⚠ id_marcador guardado ({medido['id_marcador']}) "
                  f"se midió para el robot {medido_para}, no para el robot "
                  f"{id_robot} de esta corrida — se descarta.")
        # Sin --marcador explícito ni una medición válida para ESTE robot:
        # usar la correspondencia fija robot↔chasis para EL ROBOT ELEGIDO
        # (no el de MAPEO_AGENTES[0], que podría ser otro si --robot apunta
        # a uno distinto). Si el robot está fuera del rango confirmado
        # (1-16, o es el 0 sin resolver), no se adivina: se avisa y se cae
        # al default de la tabla, que sigue exigiendo verificación manual.
        try:
            marcador = cfg.marcador_fijo_de_robot(id_robot)
        except ValueError as exc:
            marcador = cfg.MAPEO_AGENTES[0].id_marcador
            print(f"[sesion] ⚠ {exc}")
            print(f"[sesion]   Usando el default de MAPEO_AGENTES[0] "
                  f"({marcador}) como candidato de partida — verificalo "
                  f"con --sesion calibracion --etapa 1.")

    candidatos_marcador = None
    if args.candidatos:
        try:
            candidatos_marcador = [int(x) for x in args.candidatos.split(",")
                                   if x.strip()]
        except ValueError:
            print(f"[sesion] --candidatos inválido: {args.candidatos!r} "
                  f"(esperado 'N,N,N,...')")
            return 2

    if args.puntos < 2:
        print(f"[sesion] --puntos {args.puntos}: hacen falta al menos 2 "
              f"para fijar escala, rotación y traslación.")
        return 2

    ctx = Contexto(sesion=args.sesion, id_robot=id_robot, marcador=marcador,
                   forzar=args.forzar, simulador=args.simulador,
                   candidatos_marcador=candidatos_marcador,
                   puntos_marco=args.puntos)
    atexit.register(ctx.detener_todo)
    _preparar(ctx)

    try:
        if args.sesion == "calibracion":
            return correr_calibracion(ctx, args.etapa)

        if args.sesion == "politica":
            faltan = calib.faltantes()
            if faltan:
                print("\n✘ Faltan parámetros de calibración:")
                for f in faltan:
                    print(f"    · {f}")
                if not ctx.forzar:
                    print("\nCorré primero: python sesion_robotat.py "
                          "--sesion calibracion")
                    return 3
                print("⚠ --forzar: se corre con calibración incompleta.")
            resultado = sesion_politica(ctx, rpm_aborto=args.rpm_aborto)
            print(f"\n>>> SESIÓN política: {resultado.veredicto}  "
                  f"{resultado.detalle}")
            return 0 if resultado.paso else 1

        if args.sesion == "enjambre":
            faltan = calib.faltantes()
            if faltan:
                print("\n✘ Faltan parámetros de calibración:")
                for f in faltan:
                    print(f"    · {f}")
                if not ctx.forzar:
                    print("\nCorré primero: python sesion_robotat.py "
                          "--sesion calibracion")
                    return 3
                print("⚠ --forzar: se corre con calibración incompleta.")
            n = args.agentes or len(cfg.MAPEO_AGENTES)
            if n < 2:
                print(f"\n✘ La sesión 'enjambre' necesita al menos 2 agentes "
                      f"(se pidieron {n}). Para uno solo: --sesion politica.")
                return 2
            resultado = sesion_politica(ctx, rpm_aborto=args.rpm_aborto,
                                        n_agentes=n)
            print(f"\n>>> SESIÓN enjambre: {resultado.veredicto}  "
                  f"{resultado.detalle}")
            return 0 if resultado.paso else 1

        if args.sesion == "evaluacion":
            faltan = calib.faltantes()
            if faltan:
                print("\n✘ Faltan parámetros de calibración:")
                for f in faltan:
                    print(f"    · {f}")
                if not ctx.forzar:
                    print("\nCorré primero: python sesion_robotat.py "
                          "--sesion calibracion")
                    return 3
                print("⚠ --forzar: se corre con calibración incompleta.")
            n = args.agentes or len(cfg.MAPEO_AGENTES)
            resultado = sesion_evaluacion(
                ctx, n_agentes=n, factor=args.factor,
                episodios_objetivo=args.episodios,
                decisiones=args.decisiones,
                rpm_aborto=args.rpm_aborto,
                colocacion=args.colocacion)
            print(f"\n>>> SESIÓN evaluacion: {resultado.veredicto}  "
                  f"{resultado.detalle}")
            return 0 if resultado.paso else 1

        print(f"\nLa sesión '{args.sesion}' todavía NO está implementada.")
        print("Su diseño depende de lo que arrojen 'calibracion' y")
        print("'politica': el régimen de operación que salga del barrido")
        print("determina las velocidades del enjambre, y el modo de consulta")
        print("de poses que salga de la etapa 5 determina si cinco agentes")
        print("pueden consultarse de a uno sin perder frecuencia.")
        return 4
    except KeyboardInterrupt:
        print("\n[sesion] interrumpida por el usuario.")
        return 130
    except ConnectionError as exc:
        # `RobotsInalcanzables` y afines: diagnóstico, no traceback. Ningún
        # robot recibió órdenes (el canal no llegó a abrirse).
        print(f"\n[sesion] ✘ no se arranca: {exc}")
        return 5
    finally:
        ctx.detener_todo()
        ctx.cerrar()


if __name__ == "__main__":
    sys.exit(main())
