"""
adaptadores_robotat.py
======================
Implementaciones de `FuentePoses`, `CanalActuacion` y `EntornoEjecucion`
contra el Robotat físico. El coordinador —política, filtro CBF, escape,
métricas— no cambia: sólo se le inyectan estos tres objetos en vez de los de
Webots.

Divergencias DELIBERADAS respecto de los adaptadores de Webots
--------------------------------------------------------------
1. **La fuente CONSULTA; no recibe.** En Webots cada agente publicaba su pose
   sin que nadie la pidiera. Acá cada `leer_poses()` es un ida y vuelta TCP
   al servidor de captura. Se registra la latencia para poder contrastarla
   contra el margen que el Exp H mostró tolerable (300 ms).

2. **El canal FRENA a los agentes con pose vencida.** El coordinador usa la
   última pose conocida sin límite de antigüedad —política validada en los
   Exp F y H, que no se toca—, pero en el laboratorio conducir a ciegas con
   una pose de hace un segundo es peligroso. El corte por antigüedad va acá,
   en la frontera, y no altera el lazo de decisión.

3. **`reposicionar` lanza `NotImplementedError`.** No hay teletransporte.

4. **La caída de la conexión de poses termina el programa**, para que el
   `finally` y el `atexit` que ya existen en el coordinador ejecuten
   `detener_todo()`. Se reusa el camino de parada de la Fase 1 en vez de
   inventar uno nuevo.

⚠ LA PARADA POR SOFTWARE NO ESTÁ GARANTIZADA. `detener_todo()` es un mensaje
más en la misma cola TCP que el resto: si el enlace con un robot está caído,
ese robot CONSERVA SU ÚLTIMA ORDEN y sigue andando. Ver README §S1.

⚠ HALLAZGO DE LABORATORIO (2026-08-21): la primera consulta de pose después
de conectar fallaba sistemáticamente (respuesta no parseable, 200-203 B),
reproducido dos veces seguidas contra el robot 1 en el Robotat real,
mientras que las 19 consultas siguientes de cada corrida funcionaban. La
causa: `robotat_get_pose.m` hace `read(tcp_obj)` como PRIMERA línea, antes
de escribir nada — un vaciado del buffer de entrada que nuestro cliente no
portaba. El servidor aparentemente empuja algo (probablemente el último
frame en caché) apenas acepta la conexión, sin que se lo pidan; sin el
vaciado, esa basura queda pegada delante de la respuesta real y no parsea
nunca. Ver `descartar_buffer_pendiente`.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import json
import select
import socket
import threading
import time
from collections import deque
from typing import (TYPE_CHECKING, Callable, Deque, Dict, List, Optional,
                    Tuple)

import numpy as np

import config_robotat as cfg

if TYPE_CHECKING:          # sólo para las anotaciones: no se importa al correr
    from diagnostico_poses import RegistroDiagnosticoPoses


def descartar_buffer_pendiente(sock: socket.socket,
                               limite_bytes: int = 65536,
                               destino: Optional[bytearray] = None) -> int:
    """
    Descarta lo que ya esté esperando en el socket, ANTES de mandar una
    petición nueva. Ver el hallazgo de laboratorio en el encabezado del
    módulo.

    Réplica de `read(tcp_obj)` al comienzo de `robotat_get_pose.m`: en un
    `tcpclient` de MATLAB, `read()` sin argumentos vacía el buffer de
    entrada. El original lo hace como primera línea de CADA consulta, no
    sólo tras conectar — así que acá se llama en cada consulta también, por
    si el servidor puede empujar datos fuera de turno en cualquier momento,
    no sólo al aceptar la conexión.

    Usa `select` con timeout 0 para no bloquear ni gastar una syscall de
    `recv` cuando el buffer ya está vacío, que es el caso normal en cada
    tick del lazo de control a 100 Hz.

    `destino` (opcional): si se pasa, se le agrega lo descartado, para que el
    registro de diagnóstico pueda mostrar QUÉ se tiró y no sólo cuánto
    (auditoría del 2026-09-24). Con `None` es exactamente lo de siempre.

    Retorna
    -------
    Bytes descartados (0 en el caso normal). Se cuenta y se expone en el
    resumen de cada cliente: si vuelve a aparecer más allá de la primera
    consulta tras conectar, es una pista de que la causa no es sólo el
    saludo inicial del servidor.
    """
    descartados = 0
    while descartados < limite_bytes:
        listo, _, _ = select.select([sock], [], [], 0.0)
        if not listo:
            break
        trozo = sock.recv(4096)
        if not trozo:
            break
        descartados += len(trozo)
        if destino is not None:
            destino.extend(trozo)
    return descartados


#: Saludo que el servidor empuja al aceptar la conexión, medido contra el
#: Robotat real (2026-08-25). 52 B, sin terminador de línea.
SALUDO_SERVIDOR: bytes = b"Connected to the Robotat server"


def esperar_saludo_inicial(sock: socket.socket,
                           espera_max_s: float = 0.5) -> int:
    """
    Espera —BLOQUEANDO— el saludo que el servidor manda al conectar, y lo
    descarta, ANTES de que nadie mande la primera consulta.

    HALLAZGO DE LABORATORIO (2026-08-25): `descartar_buffer_pendiente` usa
    `select` con timeout 0, o sea NO espera. Sobre una conexión recién
    abierta el saludo todavía viaja por la red, así que descarta 0 B, se
    manda la petición, y el saludo llega DESPUÉS — pegado adelante de la
    respuesta JSON:

        b'Connected to the Robotat server... Type EXIT to stop[1.083, ...]'

    `decodificar_respuesta_poses` no puede parsear eso, devuelve None, y la
    consulta agota su timeout entero. El síntoma es traicionero: falla SÓLO
    la primera consulta de cada conexión, y el llamador lo reporta como
    "marcador sin lectura / no visible". Fue exactamente lo que hizo fallar
    la etapa 1 contra el marcador 1 —que estaba perfectamente trackeado— por
    ser el primer candidato del escaneo.

    Por qué no se notó antes: los clientes que hacen más trabajo entre
    conectar y consultar (imprimir, armar peticiones) le daban al saludo el
    tiempo de llegar por casualidad. Es una carrera, no un fallo
    determinista.

    Tolerante a propósito: si el saludo no llega en `espera_max_s` se sigue
    igual. No sabemos si TODAS las versiones del servidor saludan, y un
    servidor callado no debe colgar la sesión.

    Retorna
    -------
    Bytes descartados (52 contra el servidor real; 0 si no hubo saludo).
    """
    recibido = b""
    limite = time.perf_counter() + espera_max_s
    while time.perf_counter() < limite:
        restante = max(0.0, limite - time.perf_counter())
        listo, _, _ = select.select([sock], [], [], restante)
        if not listo:
            break
        trozo = sock.recv(4096)
        if not trozo:
            break
        recibido += trozo
        if SALUDO_SERVIDOR in recibido:
            # Ya llegó: barrer lo que venga pegado atrás sin volver a esperar.
            return len(recibido) + descartar_buffer_pendiente(sock)
    return len(recibido)
from interfaces import PoseMedida
from protocolo_robotat import (
    VALORES_POR_AGENTE,
    accion_a_rpm,
    codificar_peticion_poses,
    codificar_velocidades_rueda,
    decodificar_respuesta_poses,
    heading_desde_cuaternion,
    lab_a_env,
    pose_es_valida,
)


# =============================================================================
# FUENTE DE POSES
# =============================================================================

class FuentePosesRobotat:
    """
    Poses del servidor de captura de movimiento, por consulta TCP.

    Parámetros
    ----------
    n_agentes    : cuántos agentes tiene el enjambre.
    obtener_tick : callable que devuelve el tick del lazo, para sellar cada
                   medición (la interfaz lo pide en ticks, no en segundos).
                   Puede omitirse: `EntornoEjecucionRobotat` conecta su
                   propio contador al construirse, porque la fuente se crea
                   ANTES que el entorno y que el coordinador, y no hay de
                   dónde sacar el reloj todavía. Sin esa conexión el sello
                   quedaría clavado en 0 y toda pose parecería antiquísima.

    El endpoint se resuelve en `conectar()` con `cfg.endpoint_poses()`, NO en
    un valor por defecto del constructor: un default se evaluaría al importar
    el módulo y `activar_simulador_local()` no tendría efecto.
    """

    nombre: str = "robotat"

    def __init__(
        self,
        n_agentes:    int,
        obtener_tick: Optional[Callable[[], int]] = None,
    ) -> None:
        self._n = int(n_agentes)
        self._obtener_tick: Callable[[], int] = obtener_tick or (lambda: 0)
        self._reloj_propio: bool = obtener_tick is not None
        self._ip: str = ""
        self._puerto: int = 0

        faltan = [i for i in range(self._n) if i not in cfg.MAPEO_AGENTES]
        if faltan:
            raise ValueError(
                f"MAPEO_AGENTES no cubre los agentes {faltan}. "
                f"Editá config_robotat.MAPEO_AGENTES."
            )
        self._marcadores: List[int] = [
            cfg.MAPEO_AGENTES[i].id_marcador for i in range(self._n)
        ]
        if cfg.MODO_CONSULTA_POSES not in ("lote", "individual"):
            raise ValueError(
                f"MODO_CONSULTA_POSES={cfg.MODO_CONSULTA_POSES!r} inválido; "
                f"usar 'lote' o 'individual'."
            )
        self._modo_consulta: str = cfg.MODO_CONSULTA_POSES
        self._peticion: bytes = codificar_peticion_poses(self._marcadores)
        # Peticiones de un solo marcador, precalculadas (una por agente).
        self._peticiones_individuales: List[bytes] = [
            codificar_peticion_poses([m]) for m in self._marcadores
        ]

        self._sock: Optional[socket.socket] = None
        self.conexion_caida: bool = False
        self._vistos: set = set()
        self._ultimo_instante: Dict[int, float] = {}

        # Diagnóstico — se vuelca en `resumen()`.
        self.consultas:       int = 0
        self.consultas_omitidas: int = 0
        self.fallos_consulta: int = 0
        self.rechazos_pose:   Dict[str, int] = {}
        self._latencias:      List[float] = []
        self.bytes_descartados: int = 0
        self.consultas_con_descarte: int = 0

        # Registro de diagnóstico de la cadena de poses (auditoría del
        # 2026-09-24). `None` = apagado, el caso normal: cada gancho de esta
        # clase es un `if ... is not None`, así que apagado no cambia NADA.
        # Ver `activar_diagnostico` y `diagnostico_poses.py`.
        self._diag: Optional["RegistroDiagnosticoPoses"] = None

        # Una consulta a la vez (2026-09-24). ⚠ CAMBIO SEPARADO: NO es la
        # corrección de los congelamientos de borde del 22 y 24-09 (ver
        # BITACORA_TECNICA, "Cerrojo en la fuente de poses"). Dos hilos usan
        # esta fuente: el latido de la guía (`_esperar_reposicionamiento`) y
        # el hilo principal, y al latido se lo espera con `join(timeout=2.0)`:
        # si seguía dentro de una consulta, las dos peticiones compartían el
        # socket y podían cruzar sus respuestas. El canal tiene su cerrojo
        # desde el 22-09 (`_cerrojo_envio`); la fuente no lo tenía. RLock:
        # `leer_poses_ya` → `leer_poses`. Con un solo hilo no cambia nada.
        self._cerrojo = threading.RLock()

        # ── Tasa de consulta real (DECISIÓN 2026-08-22, ver config_robotat) ──
        # `leer_poses()` se sigue LLAMANDO por tick (`_avanzar` no cambia,
        # es código compartido con Webots), pero sólo hace un round-trip TCP
        # de verdad una vez cada `_intervalo_ticks` llamadas. Las llamadas
        # intermedias devuelven `[]` sin tocar la red — el coordinador ya
        # sabe leer eso como "nada nuevo este tick" (política de caché ya
        # validada en Exp F/H). Default 1 = sin limitar, hasta que
        # `fijar_intervalo_consulta` lo ajuste con el timestep real.
        self._intervalo_ticks: int = 1
        self._ticks_desde_consulta: int = 1

    def fijar_reloj(self, obtener_tick: Callable[[], int]) -> None:
        """
        Instala el reloj del lazo, si no se dio uno al construir. Lo llama
        `EntornoEjecucionRobotat`, que es quien cuenta los ticks.
        """
        if not self._reloj_propio:
            self._obtener_tick = obtener_tick

    def fijar_intervalo_consulta(self, timestep_ms: int) -> None:
        """
        Calcula cada cuántos ticks toca una consulta real, a partir de
        `cfg.HZ_CONSULTA_POSES`. Lo llama `EntornoEjecucionRobotat`, que es
        quien conoce el timestep — mismo patrón que `fijar_reloj`.

        `HZ_CONSULTA_POSES` se lee AQUÍ, no en `__init__`, para que un
        cambio de `cfg.HZ_CONSULTA_POSES` hecho antes de construir el
        entorno (p.ej. por sesión, vía `cfg.HZ_CONSULTA_POSES = ...`) tenga
        efecto — igual que `activar_simulador_local()` se lee en
        `conectar()`, no al importar el módulo.
        """
        periodo_ms = 1000.0 / max(cfg.HZ_CONSULTA_POSES, 1e-9)
        self._intervalo_ticks = max(1, round(periodo_ms / timestep_ms))
        # Forzar una consulta real en la PRÓXIMA llamada: sin esto, quien
        # ajuste la tasa a mitad de sesión heredaría hasta
        # `_intervalo_ticks` llamadas de retraso antes de la primera
        # consulta real bajo el nuevo régimen.
        self._ticks_desde_consulta = self._intervalo_ticks

    def activar_diagnostico(
        self, registro: Optional["RegistroDiagnosticoPoses"],
    ) -> None:
        """
        Conecta —o desconecta, con `None`— el registro de diagnóstico de la
        cadena de poses. Desde acá cada consulta real deja su traza (bytes
        pedidos, descartados y recibidos, tiempos, causa) y cada fila su
        resultado de validación; el registro decide qué escribir.

        No cambia qué devuelve la fuente ni cuándo consulta: sólo mira.
        """
        self._diag = registro

    # ── conexión ─────────────────────────────────────────────────────────
    def conectar(self) -> None:
        """Abre el socket. Lanza si no se puede: sin poses no hay lazo."""
        self._ip, self._puerto = cfg.endpoint_poses()
        s = socket.create_connection(
            (self._ip, self._puerto), timeout=cfg.TIMEOUT_CONEXION_S
        )
        s.settimeout(cfg.TIMEOUT_POSES_S)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # Antes de la primera consulta: ver `esperar_saludo_inicial`.
        saludo = esperar_saludo_inicial(s)
        self._sock = s
        self.conexion_caida = False
        print(f"[poses] conectado a {self._ip}:{self._puerto} · "
              f"marcadores {self._marcadores}"
              + (f" · saludo {saludo} B descartado" if saludo else ""))
        diag = self._diag
        if diag is not None:
            diag.registrar_evento(
                "conexion", endpoint=f"{self._ip}:{self._puerto}",
                saludo_descartado_bytes=saludo,
                marcadores=list(self._marcadores))

    def cerrar(self) -> None:
        """Manda 'EXIT' (lo que espera el servidor) y cierra. No lanza."""
        with self._cerrojo:
            if self._sock is None:
                return
            try:
                self._sock.sendall(b"EXIT")
            except OSError:
                pass
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    # ── lectura ──────────────────────────────────────────────────────────
    def _un_viaje(
        self, peticion: bytes, n_filas: int,
    ) -> Optional[np.ndarray]:
        """
        Un ida y vuelta: petición JSON → respuesta JSON → matriz (n_filas, 7).

        El protocolo NO tiene delimitador de mensaje ni longitud en la
        cabecera, así que se acumulan bytes hasta que el JSON parsee o
        expire el timeout. Es frágil por diseño del servidor, no nuestro;
        el fallo se traduce en None (= "no llegó pose"), que el coordinador
        ya sabe manejar.

        Antes de mandar la petición se descarta lo que ya esté en el buffer
        de entrada (ver `descartar_buffer_pendiente` y el hallazgo de
        laboratorio en el encabezado del módulo): sin esto, la primera
        consulta tras conectar o reconectar lee basura vieja en vez de la
        respuesta real y nunca parsea.

        Con el registro de diagnóstico activo (`activar_diagnostico`), deja
        una traza de la consulta: qué se pidió, qué había en el búfer antes
        de pedir, qué llegó, cuándo llegó el primer byte y por qué terminó.
        Apagado, `traza` es `None` y ninguna de las líneas que la tocan hace
        nada.
        """
        diag = self._diag
        traza = (diag.nueva_traza(peticion, n_filas, int(self._obtener_tick()))
                 if diag is not None else None)
        if self._sock is None:
            if traza is not None:
                traza.causa = "sin_socket"
                traza.t_fin = time.perf_counter()
                diag.registrar_consulta(traza)
            return None
        t0 = time.perf_counter()
        crudo = b""
        try:
            # El descarte va DENTRO del try: si el socket está muriendo,
            # `select` puede marcarlo "listo para leer" y el `recv` del
            # descarte lanza (visto en pruebas: ConnectionAbortedError al
            # simular una caída de conexión). Debe caer en el MISMO camino
            # de "conexión perdida" que ya maneja el resto del método, no
            # escapar como una excepción sin capturar.
            descartados = descartar_buffer_pendiente(
                self._sock,
                destino=traza.descartado if traza is not None else None)
            if descartados:
                self.bytes_descartados += descartados
                self.consultas_con_descarte += 1
            if traza is not None:
                traza.t_envio = time.perf_counter()
            self._sock.sendall(peticion)
            while True:
                trozo = self._sock.recv(4096)
                if not trozo:
                    raise ConnectionError("el servidor cerró la conexión")
                if traza is not None and traza.t_primer_byte is None:
                    traza.t_primer_byte = time.perf_counter()
                crudo += trozo
                m = decodificar_respuesta_poses(crudo, n_filas)
                if m is not None:
                    self._latencias.append(time.perf_counter() - t0)
                    if traza is not None:
                        traza.causa = "ok"
                        traza.matriz = m.copy()
                    return m
                if time.perf_counter() - t0 > cfg.TIMEOUT_POSES_S:
                    if traza is not None:
                        traza.causa = "timeout_plazo"
                    return None
        except socket.timeout:
            if traza is not None:
                traza.causa = "timeout_socket"
            return None
        except OSError as exc:
            print(f"[poses] conexión perdida: {exc}")
            self.conexion_caida = True
            if traza is not None:
                traza.causa = "conexion_perdida"
                traza.detalle = f"{type(exc).__name__}: {exc}"
            return None
        finally:
            if traza is not None:
                traza.crudo = crudo
                traza.t_fin = time.perf_counter()
                diag.registrar_consulta(traza)

    def _consultar(self) -> Optional[np.ndarray]:
        """
        Poses de los N agentes, según `MODO_CONSULTA_POSES`.

        En modo "individual" se hace una consulta por marcador y las que
        fallan se marcan con NaN, para que la validación defensiva las
        descarte por el mismo camino que cualquier otra pose inutilizable.
        Así la oclusión de un marcador NO deja sin pose al resto del
        enjambre, que es lo que pasaría en modo "lote" si el servidor
        respondiera con menos filas.
        """
        if self._modo_consulta == "lote":
            return self._un_viaje(self._peticion, self._n)

        filas = np.full((self._n, VALORES_POR_AGENTE), np.nan, dtype=np.float64)
        alguna = False
        for i in range(self._n):
            m = self._un_viaje(self._peticiones_individuales[i], 1)
            if self.conexion_caida:
                return None
            if m is not None:
                filas[i] = m[0]
                alguna = True
        return filas if alguna else None

    def leer_poses(self) -> List[Tuple[int, PoseMedida]]:
        """
        `_leer_poses_sin_cerrojo` con el cerrojo de la fuente tomado: el
        latido de la guía y el hilo principal no pueden compartir el socket a
        mitad de una consulta (ver `self._cerrojo` en `__init__`).
        """
        with self._cerrojo:
            return self._leer_poses_sin_cerrojo()

    def _leer_poses_sin_cerrojo(self) -> List[Tuple[int, PoseMedida]]:
        """
        Cuerpo de `leer_poses`; sólo se llama con el cerrojo tomado.

        Consulta el servidor y devuelve las mediciones VÁLIDAS, en orden de
        índice de agente. Las que no pasan la validación defensiva se
        descartan y se cuentan por motivo; el agente queda sin pose nueva,
        que es exactamente el caso que la lógica del coordinador ya cubre.

        Se sigue llamando UNA VEZ POR TICK (eso no cambia: es el mismo
        `_avanzar` compartido con Webots), pero sólo hace un round-trip TCP
        real cada `_intervalo_ticks` llamadas — devuelve `[]` en las demás,
        sin tocar la red. Con `_intervalo_ticks == pasos_por_decision` (el
        caso por defecto), la consulta real cae exactamente en el ÚLTIMO
        tick antes de cada decisión: la pose que usa `_decidir_y_actuar`
        tiene, como mucho, la antigüedad de un solo ida y vuelta — más
        fresca que sondeando a 100 Hz, donde igual se decide con la última
        lectura disponible más su propio retardo.
        """
        self._ticks_desde_consulta += 1
        if self._ticks_desde_consulta < self._intervalo_ticks:
            self.consultas_omitidas += 1
            return []
        self._ticks_desde_consulta = 0

        self.consultas += 1
        matriz = self._consultar()
        if matriz is None:
            self.fallos_consulta += 1
            return []

        tick = int(self._obtener_tick())
        ahora = time.perf_counter()
        diag = self._diag
        medidas: List[Tuple[int, PoseMedida]] = []
        for i in range(self._n):
            fila = matriz[i]
            ok, motivo = pose_es_valida(fila)
            if not ok:
                clave = motivo.split("=")[0].split(" ")[0]
                self.rechazos_pose[clave] = self.rechazos_pose.get(clave, 0) + 1
                if diag is not None:
                    diag.registrar_fila(i, fila, False, motivo, None, ahora,
                                        tick)
                continue
            yaw, _ = heading_desde_cuaternion(
                float(fila[3]), float(fila[4]), float(fila[5]), float(fila[6])
            )
            # El offset de rumbo es POR ROBOT, no global: describe cómo
            # quedó montada la constelación en ese chasis. Con el escalar
            # único, el robot 10 tendría 127° de error de rumbo según la
            # tabla del laboratorio. Ver `config_robotat.offset_rumbo_de_robot`.
            pose = lab_a_env(
                float(fila[0]), float(fila[1]), yaw,
                cfg.offset_rumbo_de_robot(cfg.MAPEO_AGENTES[i].id_robot),
            )
            medidas.append((i, PoseMedida(pose=pose, tick=tick)))
            self._vistos.add(i)
            self._ultimo_instante[i] = ahora
            if diag is not None:
                diag.registrar_fila(i, fila, True, "", pose, ahora, tick)
        return medidas

    def leer_poses_ya(self) -> Dict[int, np.ndarray]:
        """
        Una consulta REAL ahora, sin el límite de tasa por tick, como
        {agente: pose en el marco del env}. Para lazos que corren FUERA del
        episodio —la colocación autónoma—, donde el reloj de ticks del
        entorno no avanza y `leer_poses` devolvería `[]` nueve de cada diez
        llamadas.
        """
        # Bajo el cerrojo: si no, otro hilo podía consumir el forzado entre
        # esta línea y la consulta, y ésta volvía vacía.
        with self._cerrojo:
            self._ticks_desde_consulta = self._intervalo_ticks
            return {i: m.pose for i, m in self.leer_poses()}

    # ── estado para el watchdog ──────────────────────────────────────────
    def agentes_faltantes(self) -> List[int]:
        """Índices de los que nunca llegó una pose válida."""
        return [i for i in range(self._n) if i not in self._vistos]

    def agentes_vencidos(self) -> List[int]:
        """
        Índices cuya última pose válida supera `ANTIGUEDAD_MAX_POSE_S`. Un
        agente del que nunca se supo nada cuenta como vencido: nunca debe
        moverse a ciegas.
        """
        with self._cerrojo:
            ahora = time.perf_counter()
            vencidos = [
                i for i in range(self._n)
                if (i not in self._ultimo_instante)
                or (ahora - self._ultimo_instante[i]
                    > cfg.ANTIGUEDAD_MAX_POSE_S)
            ]
            diag = self._diag
            if diag is not None:
                diag.registrar_vencidos(vencidos, ahora)
            return vencidos

    def reiniciar(self) -> None:
        """
        Olvida qué agentes se vieron (al empezar un episodio) y fuerza una
        consulta real en la próxima llamada — el episodio arranca con
        poses frescas, no con lo que haya sobrevivido al límite de tasa de
        antes del reinicio.
        """
        with self._cerrojo:
            self._vistos.clear()
            self._ultimo_instante.clear()
            self._ticks_desde_consulta = self._intervalo_ticks

    def resumen(self) -> List[str]:
        """Diagnóstico de la sesión, para imprimir al terminar."""
        lat = np.asarray(self._latencias, dtype=np.float64)
        if lat.size:
            perfil = (f"p50 {np.percentile(lat, 50)*1e3:.1f} ms · "
                      f"p95 {np.percentile(lat, 95)*1e3:.1f} ms · "
                      f"máx {lat.max()*1e3:.1f} ms")
        else:
            perfil = "sin muestras"
        return [
            f"[poses] consultas: {self.consultas}  omitidas por tasa: "
            f"{self.consultas_omitidas}  fallidas: {self.fallos_consulta}  "
            f"latencia: {perfil}",
            f"[poses] poses rechazadas por motivo: {self.rechazos_pose or '—'}",
            f"[poses] descartes de buffer: {self.consultas_con_descarte} "
            f"consulta(s), {self.bytes_descartados} B total "
            f"(ver hallazgo de laboratorio 2026-08-21 en el encabezado del "
            f"módulo)",
        ]


# =============================================================================
# CHEQUEO GEOMÉTRICO PREVIO AL ARRANQUE
# =============================================================================

def revisar_poses_iniciales(
    poses: Dict[int, np.ndarray],
    n_agentes: int,
) -> List[str]:
    """
    Comprueba que el enjambre está en un estado del que se pueda arrancar.

    Cuatro condiciones, todas sobre poses YA transformadas al marco del env:

      1. hay pose de los N agentes;
      2. cada una cae dentro de la arena;
      3. ningún par está a menos de `D_SEPARACION_MIN_ARRANQUE_M`;
      4. ninguna está a menos de `MARGEN_PARED_ARRANQUE_M` de una pared.

    La cuarta no es cosmética: el Exp A mostró que la política no sabe
    despegarse de un muro —depende de la reflexión elástica que en física
    real no existe— y el escape sólo se dispara cuando el filtro CBF ya está
    saturado. Arrancar pegado a la pared es arrancar en el único estado del
    que el sistema no se recupera solo.

    Retorna
    -------
    Lista de problemas, vacía si se puede arrancar. Cada entrada nombra al
    agente y el motivo, para no tener que adivinar cuál de los cinco es.
    """
    problemas: List[str] = []

    faltan = [i for i in range(n_agentes) if i not in poses]
    if faltan:
        problemas.append(
            f"sin pose válida: agentes {faltan} "
            f"(marcador fuera del volumen, robot apagado, o mapeo de IDs mal)"
        )

    for i in sorted(poses):
        x, y = float(poses[i][0]), float(poses[i][1])
        if not (0.0 <= x <= cfg.ARENA_WX_M and 0.0 <= y <= cfg.ARENA_WY_M):
            problemas.append(
                f"agente {i}: ({x:.3f}, {y:.3f}) fuera de la arena "
                f"[0,{cfg.ARENA_WX_M}]×[0,{cfg.ARENA_WY_M}] — "
                f"revisar ESCALA_POSICION (§C1) y el marco (§C2)"
            )
            continue
        d_pared = min(x, cfg.ARENA_WX_M - x, y, cfg.ARENA_WY_M - y)
        if d_pared < cfg.MARGEN_PARED_ARRANQUE_M - cfg.TOL_GEOMETRICA_M:
            problemas.append(
                f"agente {i}: a {d_pared:.3f} m de una pared "
                f"(mínimo {cfg.MARGEN_PARED_ARRANQUE_M:.2f} m) — "
                f"la política no sabe despegarse de un muro; alejalo a mano"
            )

    indices = sorted(poses)
    for a in range(len(indices)):
        for b in range(a + 1, len(indices)):
            i, j = indices[a], indices[b]
            d = float(np.linalg.norm(poses[i][:2] - poses[j][:2]))
            if d < cfg.D_SEPARACION_MIN_ARRANQUE_M - cfg.TOL_GEOMETRICA_M:
                problemas.append(
                    f"agentes {i} y {j}: separados {d:.3f} m "
                    f"(mínimo {cfg.D_SEPARACION_MIN_ARRANQUE_M:.2f} m) — "
                    f"arrancarían en colisión"
                )
    return problemas


# =============================================================================
# CANAL DE ACTUACIÓN
# =============================================================================

class CanalActuacionRobotat:
    """
    Un socket TCP por robot. Convierte (v, ω) a RPM de rueda y envía el
    comando CBOR de 11 bytes.

    ⚠ El orden de ruedas se resuelve ÍNTEGRAMENTE en `protocolo_robotat`
    (`accion_a_rpm` devuelve izquierda-primero y `codificar_velocidades_rueda`
    la escribe primero). Acá no se reordena nada; ver `test_robotat.py`.
    """

    nombre: str = "robotat"

    def __init__(
        self,
        n_agentes: int,
        fuente:    Optional[FuentePosesRobotat] = None,
    ) -> None:
        self._n = int(n_agentes)
        self._fuente = fuente
        self._robots: List[int] = [
            cfg.MAPEO_AGENTES[i].id_robot for i in range(self._n)
        ]
        self._socks: Dict[int, socket.socket] = {}
        self.saturaciones:  int = 0
        self.envios_fallidos: Dict[int, int] = {}
        # Enlaces que se CAYERON (no los cerrados a propósito): son los únicos
        # que `_enviar_crudo` intenta reabrir. Ver `_reconectar`.
        self._caidos: Dict[int, float] = {}
        self.reconexiones: Dict[int, int] = {}
        # Diagnóstico de caídas: un registro por caída, con la demora hasta
        # reabrir y cada intento fallido clasificado. Ver `_reconectar`.
        self.eventos_enlace: List[Dict[str, object]] = []
        self._evento_abierto: Dict[int, Dict[str, object]] = {}
        # Un envío a la vez (2026-09-22). El latido de la guía manda
        # `detener_todo` desde OTRO hilo, y `_esperar_reposicionamiento` lo
        # espera con `join(timeout=2.0)`: con un robot caído, una vuelta del
        # latido puede durar más (cada reconexión bloquea hasta 0.5 s). Con
        # la colocación autónoma, lo que sigue al Enter ya no es una pausa
        # sino envíos de marcha; dos `sendall` concurrentes al mismo socket
        # pueden intercalar los bytes de dos comandos CBOR de 11 bytes y el
        # robot recibiría basura. RLock: `_enviar_crudo` → `_reconectar`.
        self._cerrojo_envio = threading.RLock()
        self.frenados_por_pose_vieja: int = 0
        # MANDOS DIRECTOS por agente (2026-09-24): rpm de rueda que
        # reemplazan la acción de la política hasta `liberar_mando`. Los usa
        # el RETROCESO por pose repetida (`retroceso_congelamiento.py`), que
        # reemplazó a la pausa del mismo día: un robot pausado dentro de un
        # punto ciego de las cámaras no volvía a ser visto. Lo decide la
        # sesión, que es la que ve la pose repetida; el canal obedece y
        # cuenta. Vacío —el caso normal y el de todas las demás sesiones— no
        # cambia nada. La pose vencida manda igual: (0, 0) antes que el mando.
        self.mandos_directos: Dict[int, Tuple[float, float]] = {}
        self.decisiones_con_mando_directo: Dict[int, int] = {}
        # Lo que RECIBIÓ cada robot, (instante, rpm_izq, rpm_der): de acá
        # sale el camino de entrada que el retroceso deshace. Lo anotan
        # `enviar_acciones`, `enviar_directo` y `fijar_mando`; no la
        # detención, que cierra el episodio. Ver `olvidar_historial`.
        self._historial: Dict[int, Deque[Tuple[float, float, float]]] = {}
        self._ultimo_aviso_vencidos: float = 0.0
        # True sólo si `cerrar()` llegó a confirmar la detención de TODOS
        # antes de cerrar los sockets. Distingue "ya están quietos y el canal
        # se cerró a propósito" de "no puedo hablarles", que es la situación
        # peligrosa. Sin esta distinción, el `atexit` posterior a un cierre
        # limpio imprimiría la alarma de corte de alimentación sin motivo.
        self._cerrado_ordenadamente: bool = False
        self.ultimos_fallos_detencion: List[int] = []

        # Rampa de arranque: las primeras decisiones salen a velocidad
        # reducida. Ver `enviar_acciones`.
        self.decisiones_enviadas: int = 0
        self.decisiones_limitadas: int = 0

        # Escalado GLOBAL adicional, independiente de la rampa. Lo usa el
        # barrido de régimen de `sesion_robotat.py` para recorrer desde el
        # régimen validado en el laboratorio hasta la caja de acciones
        # completa de la política. Multiplica al factor de arranque.
        self.factor_operativo: float = 1.0

        # Última orden efectivamente enviada, para diagnóstico y abortos.
        self.ultimas_rpm: Dict[int, Tuple[float, float]] = {}
        self.ultimo_pico_rpm: float = 0.0

    # ── conexión ─────────────────────────────────────────────────────────
    def conectar(self) -> None:
        """
        Abre los N sockets. Lanza si alguno falla: arrancar con 4 de 5
        robots controlables es peor que no arrancar.

        Prueba TODOS antes de lanzar (2026-09-22: el traceback nombraba sólo
        el primero que fallaba, y el operador tenía que ir de a uno), cierra
        los que sí abrió y lanza `RobotsInalcanzables` con la lista.
        """
        fallidos: List[str] = []
        for i in range(self._n):
            id_robot = self._robots[i]
            host, puerto = cfg.endpoint_robot(id_robot)
            try:
                s = socket.create_connection((host, puerto),
                                             timeout=cfg.TIMEOUT_CONEXION_S)
            except OSError as exc:
                clase = _clase_fallo_conexion(exc)
                fallidos.append(f"agente {i} → robot {id_robot} @ {host}:"
                                f"{puerto}: {clase}")
                print(f"[ruedas] agente {i} → robot {id_robot} @ {host}:"
                      f"{puerto}  ✘ {clase}")
                continue
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._socks[i] = s
            print(f"[ruedas] agente {i} → robot {id_robot} @ {host}:{puerto}")
        if fallidos:
            for s in self._socks.values():
                try:
                    s.close()
                except OSError:
                    pass
            self._socks.clear()
            raise RobotsInalcanzables(fallidos)

    def _enviar_crudo(self, i: int, rpm_izq: float, rpm_der: float) -> bool:
        """
        Envía a un robot. Devuelve False si el enlace falló.

        ⚠ HALLAZGO (2026-09-11): acá no había reconexión. En la sesión de
        evaluación el robot 3 cerró su socket (`WinError 10054`) durante una
        pausa de reposicionamiento; desde ese momento cada orden devolvía
        False en silencio y el robot —con su pose viva; nunca se verificó si
        seguía en la red— no volvió a recibir un solo comando. El detector de
        seguimiento tumbó los episodios 14 a 17 con 0 % de recorrido, y el
        síntoma se leía como "batería". Los datos lo desmienten: en los
        episodios 1 a 13 el robot 3 siguió el comando en la misma proporción
        que los otros cuatro (0.39–0.41) y cayó a 0.00 de golpe, sin
        degradación previa. Una batería se va apagando; esto fue un escalón.
        """
        with self._cerrojo_envio:
            return self._enviar_crudo_sin_cerrojo(i, rpm_izq, rpm_der)

    def _enviar_crudo_sin_cerrojo(self, i: int, rpm_izq: float,
                                  rpm_der: float) -> bool:
        """Cuerpo de `_enviar_crudo`; sólo se llama con el cerrojo tomado."""
        s = self._socks.get(i)
        if s is None:
            if i in self._caidos and not self._reconectar(i):
                return False
            s = self._socks.get(i)
            if s is None:
                return False
        try:
            s.sendall(codificar_velocidades_rueda(rpm_izq, rpm_der))
            return True
        except OSError as exc:
            self.envios_fallidos[i] = self.envios_fallidos.get(i, 0) + 1
            if self.envios_fallidos[i] <= 3:
                print(f"[ruedas] fallo enviando al agente {i} "
                      f"(robot {self._robots[i]}): {exc}")
            # El socket está muerto: se descarta y se marca para reabrir. Un
            # solo reintento inmediato; si no alcanza, el próximo envío vuelve
            # a probar respetando `RECONEXION_INTERVALO_S`.
            try:
                s.close()
            except OSError:
                pass
            self._socks.pop(i, None)
            self._caidos.setdefault(i, 0.0)
            if i not in self._evento_abierto:
                ev: Dict[str, object] = {
                    "robot": self._robots[i],
                    "hora": time.strftime("%H:%M:%S"),
                    "t0": time.perf_counter(),
                    "error": f"{type(exc).__name__} {getattr(exc, 'errno', '')}",
                    "intentos": [],
                    "demora_s": None,
                }
                self._evento_abierto[i] = ev
                self.eventos_enlace.append(ev)
            if self._reconectar(i):
                try:
                    self._socks[i].sendall(
                        codificar_velocidades_rueda(rpm_izq, rpm_der))
                    return True
                except OSError:
                    self._socks.pop(i, None)
            return False

    def _reconectar(self, i: int) -> bool:
        """
        Reabre el enlace del agente `i` si se cayó. No lanza.

        Espaciado por `RECONEXION_INTERVALO_S` y con timeout corto: con el
        robot apagado, cada intento bloquea el lazo hasta
        `RECONEXION_TIMEOUT_S`, y no se puede pagar eso en cada decisión. Sólo
        actúa sobre enlaces CAÍDOS: `cerrar()` vacía `_caidos`, así que un
        canal cerrado a propósito nunca se reabre solo.

        Cada intento queda en `eventos_enlace`, clasificado, porque la forma
        de la reapertura es la evidencia de POR QUÉ se cayó el enlace (el
        10054 sólo dice que el robot mandó un RST):
          · "sin respuesta" (timeout): el robot no estaba en la red — se
            reinició el ESP32 o perdió el WiFi, y todavía no volvió;
          · "rechazada": está en la red pero no hay servidor en el puerto —
            firmware arrancando, o el servidor se cayó;
          · reabre al PRIMER intento, en menos de ~1 s: el robot nunca se fue;
            fue el firmware el que descartó la conexión sin reiniciarse.

        ⚠ En Windows "rechazada" casi nunca aparece: ante un RST al SYN la
        pila reintenta y recién devuelve 10061 a los ~2 s (medido: 2.03 s en
        localhost), así que con `RECONEXION_TIMEOUT_S` = 0.5 un rechazo se
        registra como "sin respuesta". Acá lo que discrimina es la DEMORA y
        si reabrió al primer intento; ausente frente a rechazada lo separa
        `sonda_enlace_robots.py` (timeout largo + ping).
        """
        ahora = time.perf_counter()
        if ahora - self._caidos.get(i, 0.0) < RECONEXION_INTERVALO_S:
            return False
        self._caidos[i] = ahora
        ev = self._evento_abierto.get(i)
        host, puerto = cfg.endpoint_robot(self._robots[i])
        try:
            s = socket.create_connection((host, puerto),
                                         timeout=RECONEXION_TIMEOUT_S)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError as exc:
            if ev is not None:
                ev["intentos"].append(
                    (round(ahora - float(ev["t0"]), 2), _clase_fallo_conexion(exc)))
            return False
        self._socks[i] = s
        self._caidos.pop(i, None)
        self.reconexiones[i] = self.reconexiones.get(i, 0) + 1
        detalle = ""
        if ev is not None:
            ev["demora_s"] = round(time.perf_counter() - float(ev["t0"]), 2)
            self._evento_abierto.pop(i, None)
            detalle = (f" a los {ev['demora_s']:.1f} s de la caída "
                       f"(caída {ev['hora']}, {ev['error']}) · intentos "
                       f"fallidos: {_resumir_intentos(ev)}")
        print(f"[ruedas] agente {i} → robot {self._robots[i]} RECONECTADO "
              f"(reconexión n.º {self.reconexiones[i]}){detalle}")
        return True

    # ── interfaz ─────────────────────────────────────────────────────────
    def factor_arranque(self) -> float:
        """
        Factor de velocidad vigente: `FACTOR_VELOCIDAD_ARRANQUE` durante las
        primeras `DECISIONES_ARRANQUE` decisiones, 1.0 después.

        POR QUÉ ESCALAR NO ROMPE EL CBF. Escalar `(v, ω)` por el mismo
        k ∈ (0, 1] preserva las restricciones del filtro: si cᵀu ≥ −α·h con
        h ≥ 0, entonces cᵀ(k·u) = k·cᵀu ≥ k·(−α·h) ≥ −α·h, porque k·α·h ≤
        α·h. Reducir uniformemente nunca puede violar una barrera que ya se
        satisfacía. Tampoco rompe el escape: su ley de máximo ascenso da
        ḣ = V|a| + ℓa·Ω|b| > 0, y con k > 0 sigue siendo positiva, sólo más
        chica. Lo único que cambia es la velocidad de convergencia.

        LO QUE SÍ QUEDA DESALINEADO: el env recibe la acción SIN escalar, así
        que durante la rampa las componentes v/ω del `own_state` de la
        observación son optimistas respecto de lo que el robot hace. Las
        posiciones no: ésas entran por `inyectar_poses_externas` y son las
        medidas. Se acepta a propósito —el escalado va en la frontera para
        que valga pase lo que pase en el lazo— y dura 50 de varios cientos de
        decisiones.
        """
        if not cfg.ARRANQUE_SEGURO:
            return 1.0
        if self.decisiones_enviadas >= cfg.DECISIONES_ARRANQUE:
            return 1.0
        return cfg.FACTOR_VELOCIDAD_ARRANQUE

    def factor_total(self) -> float:
        """Rampa de arranque × escalado operativo del barrido de régimen."""
        return self.factor_arranque() * float(self.factor_operativo)

    def enviar_acciones(
        self, acciones: Dict[int, Tuple[float, float]]
    ) -> None:
        """
        Envía (v, ω) por agente, forzando (0, 0) a los que tengan la pose
        vencida (ver divergencia 2 en el encabezado del módulo) y aplicando
        la rampa de arranque seguro.
        """
        factor = self.factor_total()
        rampa = self.factor_arranque()
        self.decisiones_enviadas += 1
        if rampa < 1.0:
            self.decisiones_limitadas += 1
            if self.decisiones_enviadas == 1:
                print(f"[ruedas] ARRANQUE SEGURO: {factor:.0%} de velocidad "
                      f"durante {cfg.DECISIONES_ARRANQUE} decisiones "
                      f"({cfg.DECISIONES_ARRANQUE * 0.1:.0f} s).")
        elif self.decisiones_enviadas == cfg.DECISIONES_ARRANQUE + 1:
            print("[ruedas] fin de la rampa de arranque: velocidad plena.")

        vencidos = set(self._fuente.agentes_vencidos()) if self._fuente else set()
        if vencidos:
            self.frenados_por_pose_vieja += len(vencidos)
            ahora = time.perf_counter()
            if ahora - self._ultimo_aviso_vencidos > 1.0:
                print(f"[ruedas] frenando por pose vencida: "
                      f"{sorted(vencidos)}")
                self._ultimo_aviso_vencidos = ahora

        for i in sorted(acciones):
            mando = self.mandos_directos.get(i)
            if mando is not None and i not in vencidos:
                # Retroceso: rpm tal cual, sin rampa ni factor —salen de lo
                # que el robot ya recibió—. La acción de la política no va.
                self.decisiones_con_mando_directo[i] = (
                    self.decisiones_con_mando_directo.get(i, 0) + 1)
                rpm_izq, rpm_der, saturo = mando[0], mando[1], False
            else:
                v, omega = (0.0, 0.0) if i in vencidos else acciones[i]
                rpm_izq, rpm_der, saturo = accion_a_rpm(
                    float(v) * factor, float(omega) * factor,
                    cfg.RADIO_RUEDA_M, cfg.MEDIO_EJE_M
                )
            if saturo:
                self.saturaciones += 1
            self.ultimas_rpm[i] = (rpm_izq, rpm_der)
            self._anotar_mando(i, rpm_izq, rpm_der)
            self._enviar_crudo(i, rpm_izq, rpm_der)

        self.ultimo_pico_rpm = max(
            (max(abs(a), abs(b)) for a, b in self.ultimas_rpm.values()),
            default=0.0,
        )

    def _anotar_mando(self, i: int, rpm_izq: float, rpm_der: float) -> None:
        """Suma al historial del robot lo que se le está por mandar."""
        cola = self._historial.get(i)
        if cola is None:
            cola = self._historial[i] = deque(maxlen=HISTORIAL_MANDOS)
        cola.append((time.perf_counter(), float(rpm_izq), float(rpm_der)))

    def historial_mandos(self, i: int) -> List[Tuple[float, float, float]]:
        """(instante, rpm_izq, rpm_der) enviados al agente, del más viejo."""
        return list(self._historial.get(int(i), ()))

    def olvidar_historial(self) -> None:
        """
        Al empezar un episodio: el retroceso sólo deshace órdenes del
        episodio en curso. Antes, el robot estaba quieto —colocación terminada
        con (0, 0) y 0.6 s de espera, o puesto a mano—.
        """
        self._historial.clear()

    def fijar_mando(self, i: int, rpm_izq: float, rpm_der: float,
                    enviar_ya: bool = True) -> None:
        """
        Reemplaza la acción de la política del agente `i` por estas rpm de
        rueda, TAL CUAL —sin rampa ni factor—, en cada decisión hasta
        `liberar_mando`. Con `enviar_ya` las manda en el acto: el retroceso
        se decide después del envío de la decisión, y esperar a la próxima
        serían ~12 mm más a ciegas a 0.124 m/s. Pose vencida: sale (0, 0).
        """
        i = int(i)
        izq = max(-cfg.RPM_MAX, min(cfg.RPM_MAX, float(rpm_izq)))
        der = max(-cfg.RPM_MAX, min(cfg.RPM_MAX, float(rpm_der)))
        self.mandos_directos[i] = (izq, der)
        if not enviar_ya:
            return
        if self._fuente is not None and i in self._fuente.agentes_vencidos():
            izq = der = 0.0
        self.ultimas_rpm[i] = (izq, der)
        self._anotar_mando(i, izq, der)
        self._enviar_crudo(i, izq, der)

    def liberar_mando(self, i: int) -> None:
        """Devuelve el agente a la política desde la próxima decisión."""
        self.mandos_directos.pop(int(i), None)

    def liberar_mandos(self) -> None:
        """Nadie con mando directo. Al cerrar un episodio: no se hereda."""
        self.mandos_directos.clear()

    def enlaces_caidos(self) -> List[int]:
        """Agentes cuyo enlace se cayó y todavía no se pudo reabrir."""
        return sorted(self._caidos)

    def reintentar_enlaces(self) -> List[int]:
        """
        Un intento inmediato de reabrir cada enlace caído, sin esperar el
        espaciado de `RECONEXION_INTERVALO_S`. Devuelve los que siguen
        caídos. Lo usa el chequeo previo a cada episodio.
        """
        with self._cerrojo_envio:
            for i in list(self._caidos):
                self._caidos[i] = 0.0          # saltea el espaciado
                self._reconectar(i)
            return sorted(self._caidos)

    def enviar_directo(
        self, acciones: Dict[int, Tuple[float, float]]
    ) -> None:
        """
        Envía (v, ω) en m/s y rad/s TAL CUAL: sin rampa, sin factor operativo
        y SIN contar como decisión. Lo usa la colocación autónoma entre
        episodios (`colocacion_autonoma.py`), que tiene sus propios topes.

        No contar importa: la rampa de arranque se aplica a las primeras
        `DECISIONES_ARRANQUE` decisiones de la sesión, y la réplica pareada
        la reconstruye sumando la columna `decisiones` de los episodios. Si
        la colocación sumara, las dos cosas quedarían mal.
        """
        for i in sorted(acciones):
            v, omega = acciones[i]
            rpm_izq, rpm_der, saturo = accion_a_rpm(
                float(v), float(omega), cfg.RADIO_RUEDA_M, cfg.MEDIO_EJE_M)
            if saturo:
                self.saturaciones += 1
            self.ultimas_rpm[i] = (rpm_izq, rpm_der)
            self._anotar_mando(i, rpm_izq, rpm_der)
            self._enviar_crudo(i, rpm_izq, rpm_der)

    def detener_todo(self, silencioso: bool = False) -> None:
        """
        Intenta frenar los N robots. NO es una parada de emergencia:

        · el comando de freno es un mensaje más en la MISMA cola TCP que las
          órdenes de marcha, sin prioridad;
        · si el enlace con un robot está caído, ese robot CONSERVA su última
          orden y sigue andando;
        · por eso se recorre la lista COMPLETA aunque alguno falle, se
          reintenta, y se informa nominalmente cuáles no confirmaron.

        Idempotente y no lanza: se invoca desde `finally` y desde `atexit`.

        `silencioso` es para el latido que mantiene vivos los sockets durante
        las pausas: ahí esto se llama una vez por segundo, y con la traza
        normal la consola se vuelve ilegible. ⚠ HALLAZGO (2026-09-09): con un
        robot caído por batería, el latido repitió el cartel de "CORTAR
        ALIMENTACIÓN" más de sesenta veces en una pausa y sepultó la guía de
        colocación. Un cartel que se repite así deja de leerse, que es
        exactamente lo contrario de lo que una alarma tiene que lograr. En
        modo silencioso se calla la línea de rutina y el cartel se emite sólo
        cuando CAMBIA el conjunto de robots que no confirman.
        """
        if self._cerrado_ordenadamente:
            return          # ya se detuvieron y el canal se cerró a propósito

        fallidos: List[int] = []
        for intento in range(cfg.INTENTOS_DETENCION):
            fallidos = []
            for i in range(self._n):
                if not self._enviar_crudo(i, 0.0, 0.0):
                    fallidos.append(i)
            if not fallidos:
                break
            if intento + 1 < cfg.INTENTOS_DETENCION:
                time.sleep(cfg.ESPERA_REINTENTO_DETENCION_S)

        cambio = list(fallidos) != list(self.ultimos_fallos_detencion)
        self.ultimos_fallos_detencion = list(fallidos)
        if silencioso and not cambio:
            return
        if fallidos:
            print("=" * 68)
            print("⚠ NO SE PUDO CONFIRMAR LA DETENCIÓN DE:")
            for i in fallidos:
                host, puerto = cfg.endpoint_robot(self._robots[i])
                print(f"    agente {i} → robot {self._robots[i]} "
                      f"@ {host}:{puerto}")
            print("  Estos robots MANTIENEN SU ÚLTIMA ORDEN.")
            print("  CORTAR ALIMENTACIÓN A MANO (interruptor del robot).")
            print("=" * 68)
        elif not silencioso:
            print(f"[ruedas] detención enviada a los {self._n} robots.")

    def tiene_sockets_abiertos(self) -> bool:
        """True si queda algún enlace de rueda por cerrar."""
        return bool(self._socks)

    def cerrar(self) -> None:
        """Detiene y cierra los sockets. No lanza."""
        self.detener_todo()
        exito = not self.ultimos_fallos_detencion
        for s in self._socks.values():
            try:
                s.close()
            except OSError:
                pass
        self._socks.clear()
        self._caidos.clear()
        # Si algún robot NO confirmó la detención, el canal NO queda marcado
        # como cerrado ordenadamente: un `detener_todo()` posterior debe
        # volver a intentarlo y volver a gritar.
        self._cerrado_ordenadamente = exito

    def resumen(self) -> List[str]:
        """Diagnóstico de la sesión."""
        lineas = [
            f"[ruedas] saturaciones: {self.saturaciones}  "
            f"envíos fallidos: {self.envios_fallidos or '—'}  "
            f"reconexiones: {self.reconexiones or '—'}",
            f"[ruedas] frenados por pose vencida: "
            f"{self.frenados_por_pose_vieja}  ·  decisiones con mando de "
            f"retroceso: {self.decisiones_con_mando_directo or '—'}",
            f"[ruedas] decisiones: {self.decisiones_enviadas}  "
            f"de las cuales limitadas por arranque seguro: "
            f"{self.decisiones_limitadas}",
        ]
        for ev in self.eventos_enlace:
            estado = (f"reabierto a los {ev['demora_s']:.1f} s"
                      if ev["demora_s"] is not None else "NUNCA se reabrió")
            lineas.append(
                f"[ruedas] caída robot {ev['robot']} a las {ev['hora']} "
                f"({ev['error']}): {estado} · intentos fallidos: "
                f"{_resumir_intentos(ev)}")
        return lineas


class RobotsInalcanzables(ConnectionError):
    """No se pudo abrir el enlace de ruedas de uno o más robots."""

    def __init__(self, fallidos: List[str]) -> None:
        self.fallidos = list(fallidos)
        super().__init__(
            "no responden: " + "; ".join(self.fallidos) + ". "
            "'sin respuesta' = el robot no está en la red (apagado, sin "
            "batería o sin WiFi: mirá el LED de la placa); 'rechazada' = "
            "está en la red pero su programa no atiende el puerto.")


def _clase_fallo_conexion(exc: BaseException) -> str:
    """Clase de un intento de reapertura fallido; ver `_reconectar`."""
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "sin respuesta"
    if isinstance(exc, ConnectionRefusedError):
        return "rechazada"
    return f"{type(exc).__name__} {getattr(exc, 'errno', '')}".strip()


def _resumir_intentos(ev: Dict[str, object]) -> str:
    """'3 sin respuesta, 1 rechazada' — o 'ninguno'."""
    clases = [c for _t, c in ev["intentos"]]
    return ", ".join(f"{clases.count(c)} {c}"
                     for c in dict.fromkeys(clases)) or "ninguno"


#: Órdenes que recuerda el canal por robot. El retroceso deshace a lo sumo
#: 1.0 s (`retroceso_congelamiento.VENTANA_MAX_S`): ≤ 20 envíos a 10 Hz,
#: contando el reenvío inmediato de `fijar_mando`.
HISTORIAL_MANDOS: int = 64

#: Espaciado mínimo entre intentos de reabrir el enlace de un mismo robot.
RECONEXION_INTERVALO_S: float = 1.0
#: Timeout de cada intento. Corto a propósito: bloquea el lazo de control.
RECONEXION_TIMEOUT_S: float = 0.5


# =============================================================================
# ENTORNO DE EJECUCIÓN
# =============================================================================

class EntornoEjecucionRobotat:
    """
    Reloj de tiempo real y cierre. Sin esferas que mover y sin
    teletransporte.

    El reloj es de pared con deriva acumulada corregida: cada tick apunta a
    un instante absoluto (`t0 + k·dt`), no a "dormir dt". Dormir dt en cada
    iteración acumularía el costo del lazo y el período real se estiraría.
    """

    nombre: str = "robotat"
    soporta_reposicionar: bool = False    # no hay teletransporte

    def __init__(
        self,
        fuente:      FuentePosesRobotat,
        canal:       CanalActuacionRobotat,
        timestep_ms: int,
    ) -> None:
        self._fuente = fuente
        self._canal = canal
        self._dt = float(timestep_ms) / 1000.0
        self._t0: Optional[float] = None
        self._k: int = 0
        # Tick en que se ancló `_t0`. El horario se mide desde acá, así que
        # re-anclar NO necesita volver `_k` a cero (ver `reiniciar_reloj`).
        self._k_ancla: int = 0
        self.cerrado: bool = False
        self.ticks_atrasados: int = 0

        # El contador de ticks del entorno avanza en lockstep con el
        # `_tick` del coordinador: `_avanzar()` hace `entorno.avanzar(1)` y
        # justo después `self._tick += 1`, uno a uno. Por eso `_k` sirve para
        # sellar las mediciones con el mismo reloj contra el que el
        # coordinador mide la antigüedad.
        self._fuente.fijar_reloj(lambda: self._k)
        # Idem para la tasa de consulta: acá es donde se conoce el timestep
        # real. Ver `FuentePosesRobotat.fijar_intervalo_consulta`.
        self._fuente.fijar_intervalo_consulta(timestep_ms)

    def avanzar(self, n_ticks: int) -> bool:
        """
        Espera hasta el instante del próximo tick. Devuelve False —pidiendo
        terminar— si cayó la conexión de poses, de modo que el `finally` y el
        `atexit` del coordinador ejecuten la parada ya implementada.
        """
        if self._t0 is None:
            self._t0 = time.perf_counter()
            self._k_ancla = self._k
        for _ in range(int(n_ticks)):
            if cfg.DETENER_TODO_SI_CAE_CONEXION and self._fuente.conexion_caida:
                print("[entorno] conexión de poses caída → terminando lazo.")
                self.cerrado = True
                return False
            self._k += 1
            objetivo = self._t0 + (self._k - self._k_ancla) * self._dt
            restante = objetivo - time.perf_counter()
            if restante > 0.0:
                time.sleep(restante)
            else:
                self.ticks_atrasados += 1
        return True

    def reiniciar_reloj(self) -> None:
        """
        Vuelve a anclar el horario de ticks al instante actual.

        ⚠ HALLAZGO (2026-09-05): `avanzar` duerme contra un horario ABSOLUTO
        anclado en `_t0`, que se fija en la primera llamada y nunca se movía.
        Eso vale mientras el lazo corra sin interrupciones —el barrido, que
        nunca pausa— pero se rompe en cuanto hay una pausa: durante los
        minutos que el operador tarda en reposicionar los robots, el reloj de
        pared avanza y `_k` no. Al reanudar, `objetivo` queda decenas de
        segundos en el pasado, `restante` es negativo SIEMPRE, y el lazo deja
        de dormir.

        El daño es silencioso y grave: la sesión de evaluación corrió sus
        episodios de 500 decisiones en 6–8 s en vez de 50, o sea a ~71 Hz en
        vez de 10 Hz. Los robots tuvieron una séptima parte del tiempo real
        para moverse (0.9 m en vez de 5.9 m) y la cobertura AoI medida quedó
        sin sentido, sin que ninguna métrica lo delatara — `ticks_atrasados`
        lo registraba, pero nadie lo miraba.

        Hay que llamarla al empezar cada episodio, después de cualquier
        espera.

        ⚠ HALLAZGO (2026-09-11): la primera versión de este arreglo hacía
        además `self._k = 0`. Pero `_k` es el reloj con que la fuente sella
        cada pose (`fijar_reloj(lambda: self._k)`), y el coordinador mide la
        antigüedad contra su propio `_tick`, que no se reinicia. Desde el
        segundo episodio toda pose parecía tener la antigüedad del tick de
        arranque (5005, 10010, 15015… ticks), y el aviso de "pose vieja"
        llegó a ser el 95 % de la salida de consola, enterrando los mensajes
        que importan. El horario se re-ancla con `_k_ancla`; el contador
        sigue siendo monotónico y en lockstep con el coordinador.
        """
        self._t0 = None

    def publicar_visualizacion(self, posiciones_hotspots: np.ndarray) -> None:
        """No-op: los hotspots son virtuales, no hay esferas físicas."""
        return None

    def reposicionar(self, poses: Dict[int, np.ndarray]) -> None:
        """
        NO EXISTE en el laboratorio.

        Un no-op silencioso dejaría al coordinador creyendo que los robots
        están en las poses iniciales del episodio mientras siguen donde
        quedaron, y el rollout entero sería basura sin ningún síntoma.

        Raises
        ------
        NotImplementedError : siempre.
        """
        raise NotImplementedError(
            "reposicionar() no existe en el Robotat: no hay teletransporte. "
            "Los robots arrancan donde están. Colocalos a mano y reiniciá el "
            "episodio, o corré el coordinador en modo de episodio único."
        )

    def finalizar(self, codigo: int = 0) -> None:
        """Detiene los robots, cierra sockets y vuelca el diagnóstico."""
        if self.cerrado and not self._canal.tiene_sockets_abiertos():
            return
        self.cerrado = True
        print("-" * 68)
        for linea in self._fuente.resumen() + self._canal.resumen():
            print(linea)
        if self.ticks_atrasados:
            print(f"[entorno] ticks que no alcanzaron su plazo: "
                  f"{self.ticks_atrasados} (dt = {self._dt*1e3:.0f} ms)")
        print("-" * 68)
        self._canal.cerrar()
        self._fuente.cerrar()
