"""
config_robotat.py
=================
Parámetros de conexión y CALIBRACIÓN del despliegue en el Robotat.

REGLA DE ESTE ARCHIVO
---------------------
Todo valor que no fue medido contra el hardware lleva la marca
`NO_VERIFICADO` y el programa lo IMPRIME al arrancar. Nada acá debe
presuponerse correcto: el relevamiento del código MATLAB de referencia
(`robotat/*.m`) no declara unidades de posición, ni el origen y orientación
del marco del laboratorio, ni qué componente angular corresponde al heading
del robot. Son calibración de primera sesión.

El procedimiento para medir cada uno está en `README_ROBOTAT.md`.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import math
from typing import Dict, List, NamedTuple, Tuple

# =============================================================================
# ENDPOINTS — relevados del código MATLAB (estos SÍ están en el código)
# =============================================================================

IP_SERVIDOR_POSES: str = "192.168.50.200"
PUERTO_POSES:      int = 1883

# Los robots tienen IP derivada de su ID: 192.168.50.10<id> para id 0-9,
# 192.168.50.1<id> para id 10-19.
PUERTO_ROBOT: int = 9090


def ip_de_robot(id_robot: int) -> str:
    """
    IP del robot según su ID, con la misma regla que `robotat_3pi_connect.m`.

    Raises
    ------
    ValueError : si el ID está fuera de 0–19.
    """
    if not (0 <= id_robot <= 19):
        raise ValueError(
            f"ID de robot {id_robot} fuera de rango. Permitidos: 0–19."
        )
    base = "192.168.50.1" if id_robot > 9 else "192.168.50.10"
    return f"{base}{id_robot}"


def marcador_fijo_de_robot(id_robot: int) -> int:
    """
    Marcador que trae montado el robot `id_robot`, según la correspondencia
    física confirmada: robot N → marcador N, fijo, para robots 1–16.

    NO usar con `id_robot=0`: necesitaría marcador "0", que el protocolo
    rechaza como ID inválido (`min(agents_ids) > 0` en el código de
    referencia), y no está confirmado si el robot 0 existe físicamente.
    Lanza en vez de devolver un valor que el resto del sistema aceptaría en
    silencio y fallaría más adelante, lejos de la causa real.

    Raises
    ------
    ValueError : si `id_robot` es 0, o está fuera de 1–16.
    """
    if not (1 <= id_robot <= 16):
        raise ValueError(
            f"marcador_fijo_de_robot: id_robot={id_robot} fuera del rango "
            f"confirmado (1–16). El robot 0 en particular necesitaría "
            f"marcador '0', inválido para el protocolo; no se sabe si "
            f"existe físicamente. Medí este robot con verificar_mapeo_ids "
            f"antes de asumir la correspondencia directa."
        )
    return id_robot


# ── Redirección al simulador local ───────────────────────────────────────
# Los adaptadores NO leen las constantes de arriba directamente: piden el
# endpoint por estas dos funciones. Así el simulador del laboratorio se
# activa sin tocar el código de los adaptadores, y el mismo binario que se
# probó contra el simulador es el que corre en el Robotat.
SIMULADOR_ACTIVO:     bool = False
SIMULADOR_HOST:       str  = "127.0.0.1"
SIMULADOR_PUERTO_POSES: int = 18830
SIMULADOR_PUERTO_BASE_ROBOT: int = 19090   # robot k escucha en base + k


def activar_simulador_local(
    host:         str = "127.0.0.1",
    puerto_poses: int = 18830,
    puerto_base:  int = 19090,
) -> None:
    """Redirige TODOS los endpoints al simulador que corre en esta máquina."""
    global SIMULADOR_ACTIVO, SIMULADOR_HOST
    global SIMULADOR_PUERTO_POSES, SIMULADOR_PUERTO_BASE_ROBOT
    SIMULADOR_ACTIVO = True
    SIMULADOR_HOST = host
    SIMULADOR_PUERTO_POSES = int(puerto_poses)
    SIMULADOR_PUERTO_BASE_ROBOT = int(puerto_base)


def endpoint_poses() -> Tuple[str, int]:
    """(host, puerto) del servidor de captura."""
    if SIMULADOR_ACTIVO:
        return SIMULADOR_HOST, SIMULADOR_PUERTO_POSES
    return IP_SERVIDOR_POSES, PUERTO_POSES


def endpoint_robot(id_robot: int) -> Tuple[str, int]:
    """(host, puerto) de un robot."""
    if SIMULADOR_ACTIVO:
        return SIMULADOR_HOST, SIMULADOR_PUERTO_BASE_ROBOT + int(id_robot)
    return ip_de_robot(id_robot), PUERTO_ROBOT


# =============================================================================
# MAPEO DE IDs — DOS ESPACIOS DISTINTOS, SIN CORRESPONDENCIA IMPLÍCITA
# =============================================================================
# El servidor de captura identifica MARCADORES (1–100); los robots se
# direccionan por ID de ROBOT (0–19).
#
# CORRESPONDENCIA robot ↔ marcador — ASIGNACIÓN DE LA PLATAFORMA, no una
# inferencia de una sesión (confirmado por el autor, 2026-08-22): los
# marcadores 1 a 16 están destinados a los Pololu, uno por robot, con
# robot N ↔ marcador N. A diferencia de los marcadores SUELTOS (el de
# meta, por ejemplo, que se coloca a mano y no conserva su posición), los
# montados en el chasis de cada robot son fijos y permanentes — es un
# hecho de la plataforma, no algo que dependa de cómo quedó pegada una
# pegatina esta sesión. Coincide con el dato ya medido del robot 2 (etapa
# 1 de `sesion_robotat.py`: giró el marcador 2, ningún otro). Corrige la
# suposición anterior de esta tabla (desfase +1, nunca medido) que había
# quedado contradicha por esa misma medición.
#
# La numeración humana de los robots arranca en 1 (confirmado): el robot
# "0" del rango de `ip_de_robot` (0–19, la convención del protocolo de
# conexión) no corresponde a ningún Pololu físico. Por eso el swarm por
# defecto de acá usa los robots 1–5, no 0–4.
#
# `verificar_mapeo_ids.py` / la etapa 1 de `sesion_robotat.py` siguen
# disponibles como chequeo de seguridad OPCIONAL antes de mover un robot
# —por si se montó mal una constelación—, ya no como paso obligatorio.
#
# Índice de agente (0..N-1, el que usa el coordinador) → (marcador, robot)

class AsignacionAgente(NamedTuple):
    """Correspondencia entre índice de agente, marcador OptiTrack y robot."""
    id_marcador: int
    id_robot:    int


# Los CINCO robots del enjambre, confirmados por el operador en el
# laboratorio (2026-09-01). Los IDs NO son contiguos: 1, 2, 3, 6 y 9 —
# el resto de los Pololu del Robotat son de otros usuarios y no se leen.
# La regla marcador N ↔ robot N se sostiene en los cinco (por eso el
# marcador y el robot coinciden en cada fila); lo que cambió respecto de la
# tabla anterior (1-5) es sólo QUÉ robots son.
#
# Dos robots quedaron FUERA, por razones distintas:
#
#   robot 12 → sale porque `OFFSETS_RUMBO_POR_ROBOT` viene de la tabla del
#     laboratorio, que llega hasta el robot 10: el 12 no tiene offset de
#     partida y habría que medirlo desde cero. Entró el 3 en su lugar.
#
#   robot 10 → sale porque UNA DE SUS RUEDAS ESTÁ INVERTIDA. Con `v=0.05,
#     ω=0` —o sea las dos ruedas a +29.84 rpm, avance recto— giró sobre su
#     eje casi media vuelta, que es justo lo predicho para una rueda al
#     revés (ω = v/ℓ = 59.7 °/s durante 3 s ≈ 179°). No es un problema de
#     conversión: la MISMA cadena de código hizo avanzar recto al robot 1.
#     Encaja con que sea el único de la tabla con offset +33.66 cuando los
#     otros nueve rondan −90, y con que `laboratorio11.m` traiga una
#     bandera `invertir_ruedas` "normalmente FALSE" — el laboratorio ya
#     sabe que algunos chasis están armados distinto. Entró el 2.
#
# ⚠ El robot 2 dio `TimeoutError` en el puerto de ruedas al principio de la
# sesión (2026-08-25), confirmado también desde MATLAB. El 2026-09-01
# respondía bien; lo más probable es que fuera batería. Si un robot se cae
# durante una corrida, es el primero a revisar.
#
# El agente 0 es el robot 1 a propósito: es el que quedó calibrado por la
# sesión de un robot (etapas 0-5), y `calibracion_sesion.aplicar_a_config`
# sobreescribe justamente esa entrada con lo medido.
#
#   robot 3 → sale el 2026-09-22 por caídas repetidas de su socket de ruedas
#     con el robot quieto al manipularlo (9 y 11 sep; hipótesis: contacto
#     intermitente que reinicia el ESP32 — ver BITACORA_TECNICA). Entró el 8,
#     con offset de la tabla del laboratorio (+89.99°), igual de "de partida"
#     que el 2, 6 y 9. ⚠ La sesión del 11 sep (5 válidos) fue con el 3: los
#     episodios nuevos son de OTRA composición del enjambre.
#
#   robot 2 → sale el 2026-09-22: su MARCADOR se congeló en dos corridas
#     seguidas en el mismo punto (env 0.56, 1.74) al girar a su rumbo final,
#     y Motive no lo recuperó; el 11-09 también se había congelado. El robot
#     anda bien: es la constelación / el cuerpo rígido. Entró el 5 (etapa 3:
#     +87.97° medido contra +88.81° de la tabla, Δ 0.84° → se usa la tabla).
#     La sesión nueva no tenía válidos: el cambio no mezcla composiciones.
#
#   robot 6 → sale el 2026-10-16, en la primera sesión de la campaña L2 y
#     antes de cualquier toma corrida: dejó de girar bien (había que
#     golpearlo), y en la colocación su marcador se congeló y se perdió
#     (147 rechazos por inclinación). Primero se probó el 3: no respondió
#     en la red (placa sin servicio). Entra el 2 como agente 3, con el
#     offset de la tabla (+89.74°, de partida, nunca medido). ⚠ El 2 había
#     salido el 22-09 porque su marcador se congelaba en Motive (3 veces en
#     2 días); también tuvo un corte de socket y batería baja en septiembre.
#     Esa campaña (`L2_obstaculo`) se descartó por la calibración del Robotat;
#     la composición 1, 5, 8, 2, 9 la aprobó José el 17-10 para la nueva.
#
# IPs resultantes (ver `ip_de_robot`): .101, .105, .108, .102, .109
MAPEO_AGENTES: Dict[int, AsignacionAgente] = {
    0: AsignacionAgente(id_marcador=1, id_robot=1),
    1: AsignacionAgente(id_marcador=5, id_robot=5),
    2: AsignacionAgente(id_marcador=8, id_robot=8),
    3: AsignacionAgente(id_marcador=2, id_robot=2),
    4: AsignacionAgente(id_marcador=9, id_robot=9),
}
# La correspondencia id_marcador == id_robot es un hecho conocido del
# montaje físico (confirmado por el operador), no una medición que pueda
# quedar vieja — a diferencia de un marcador suelto, éste no se puede mover
# sin desarmar el chasis. `verificar_mapeo_ids.py` / la etapa 1 de
# `sesion_robotat.py` siguen disponibles como chequeo de seguridad opcional
# antes de mover un robot nuevo, pero ya no son un paso obligatorio.
MAPEO_NO_VERIFICADO: bool = False


# =============================================================================
# CALIBRACIÓN — TODO ESTO ES NO_VERIFICADO HASTA MEDIRLO
# =============================================================================

# ── (a) ESCALA de posición ───────────────────────────────────────────────
# El código MATLAB no declara unidades. Si el servidor entrega milímetros,
# este factor debe ser 0.001. Procedimiento: README §C1.
ESCALA_POSICION: float = 1.0          # multiplica lo que llega, para pasarlo a metros
ESCALA_NO_VERIFICADA: bool = True

# ── (b) TRANSFORMACIÓN de marco: laboratorio → env [0,W]×[0,H] ───────────
# El env vive en [0,3]×[0,3] con origen en esquina. El marco del laboratorio
# tiene otro origen y posiblemente otra orientación. Se aplica, en orden:
#     p_env = R(θ_marco) · (p_lab · ESCALA) + (TRASLACION_X, TRASLACION_Y)
# Procedimiento: README §C2.
ROTACION_MARCO_RAD: float = 0.0
TRASLACION_X_M:     float = 1.5       # supone laboratorio centrado en la arena
TRASLACION_Y_M:     float = 1.5
MARCO_NO_VERIFICADO: bool = True

# ── (c) OFFSET DE HEADING ────────────────────────────────────────────────
# Equivalente al OFFSET_HEADING_RAD que hubo que calibrar en Webots. Depende
# de cómo esté montada la constelación de marcadores sobre el robot.
# Procedimiento: README §C3 (mover en línea recta y comparar el heading
# reportado contra la dirección de desplazamiento).
#
# ⚠ ES POR ROBOT, NO GLOBAL (hallazgo del 2026-08-29). El offset describe la
# orientación con que la constelación quedó montada en ESE chasis, y varía
# de robot a robot. Un escalar único aplicado a todos le daría al robot 10
# un error de 127°: la política le diría "andá a la derecha" y se iría casi
# en dirección opuesta, con el CBF calculando márgenes sobre un rumbo falso.
#
# `OFFSET_HEADING_RAD` se mantiene como valor por defecto para un robot sin
# entrada propia, y es el que sigue usando la sesión de UN robot.
OFFSET_HEADING_RAD: float = 0.0
HEADING_NO_VERIFICADO: bool = True

#: Offset de rumbo por robot, en RADIANES.
#:
#: Origen: la tabla `marker_offsets` de `laboratorio11.m`, que el laboratorio
#: mantiene para sus propios robots. Nuestro convenio es el OPUESTO en signo
#: (ver la etapa 3, que lo reporta explícitamente), así que acá van negados.
#:
#: ⚠ Son valores DE PARTIDA, no mediciones nuestras. Para el robot 1, donde
#: tenemos las dos, la tabla y nuestra medición difieren 1.63°: es buena,
#: pero no exacta. La etapa 3 sobreescribe el de cada robot a medida que se
#: mide, igual que el resto de la calibración.
#:
#: ⚠ El robot 10 (+33.6573) se aparta ~127° de los demás, que rondan −90.
#: Quedó FUERA del enjambre por tener además una rueda invertida (ver
#: `MAPEO_AGENTES`), así que ese valor no se usa. Se deja en la tabla como
#: dato: si alguna vez se recupera ese chasis, hay que medir su offset con
#: la etapa 3 antes de confiar en esta entrada.
OFFSETS_RUMBO_POR_ROBOT: Dict[int, float] = {
    1:  math.radians(+93.7618),
    2:  math.radians(+89.7361),
    3:  math.radians(+89.8177),
    4:  math.radians(+81.9006),
    5:  math.radians(+88.8106),
    6:  math.radians(+89.9653),
    7:  math.radians(+94.0866),
    # ⚠ MEDIDO, no de tabla (la tabla dice +89.9872): ver ORIGEN_OFFSET_RUMBO.
    8:  math.radians(+95.0100),
    9:  math.radians(+94.2587),
    10: math.radians(-33.6573),
}

#: Robots cuyo offset fue MEDIDO por nuestra etapa 3, no tomado de la tabla.
#: El 8 está fijo acá; el robot de `calibracion_medida.json` (hoy el 1) se
#: agrega al aplicar la calibración guardada.
OFFSETS_RUMBO_MEDIDOS: set = {8}

#: Procedencia de los offsets que NO son de la tabla ni del JSON. Se imprime
#: en el encabezado de cada sesión y se escribe en el CSV de episodios, para
#: que ninguna medición se lea sin saber sobre qué rumbo se hizo.
#:
#: Robot 8 (2026-09-22): etapa 3 con avance recto de 16.4 cm, desvío lateral
#: 0.1 mm, dispersión del rumbo 0.22°. Da +95.01° contra +89.99° de la tabla:
#: 5.02° de diferencia, más de los 3° a partir de los cuales se usa el valor
#: medido (en el robot 1 la tabla erraba 1.63°). Es UNA sola corrida: si en la
#: evaluación el robot 8 muestra sesgo de giro, CBF anómalo o seguimiento bajo
#: que los otros no, revisar primero este número (repetir la etapa 3). CSV:
#: resultados_sesion/20260922_sesion-calibracion_etapa3_rumbo.csv.
ORIGEN_OFFSET_RUMBO: Dict[int, str] = {
    8: "MEDIDO etapa 3 del 2026-09-22, UNA sola corrida "
       "(tabla +89.99°, Δ 5.02°)",
    # Robot 5: la etapa 3 confirmó la tabla (recto 16.0 cm, desvío 0.6 mm,
    # dispersión 0.37°). Con Δ ≤ 3° se usa la tabla, como en el 2, 6 y 9.
    5: "tabla del laboratorio, VERIFICADA por etapa 3 del 2026-09-22 "
       "(medido +87.97°, Δ 0.84°)",
}


def origen_offset_rumbo(id_robot: int) -> str:
    """De dónde sale el offset de rumbo que usa `offset_rumbo_de_robot`."""
    rid = int(id_robot)
    if SIMULADOR_ACTIVO:
        return "simulador (sin offset de montaje)"
    if rid in ORIGEN_OFFSET_RUMBO:
        return ORIGEN_OFFSET_RUMBO[rid]
    if rid in OFFSETS_RUMBO_MEDIDOS:
        return "MEDIDO (calibracion_medida.json)"
    if rid in OFFSETS_RUMBO_POR_ROBOT:
        return "tabla del laboratorio (de partida)"
    return "SIN ENTRADA: default OFFSET_HEADING_RAD"


def offset_rumbo_de_robot(id_robot: int) -> float:
    """
    Offset de rumbo del robot, en radianes.

    Cae a `OFFSET_HEADING_RAD` si el robot no tiene entrada propia — que es
    lo correcto para la sesión de UN robot, donde ese escalar SÍ es el del
    robot calibrado.

    NO aplica en el simulador. La tabla describe cómo quedó montada la
    constelación sobre cada CHASIS FÍSICO; los robots simulados la tienen
    perfectamente alineada, así que su offset correcto es 0 (o el que la
    prueba haya puesto en `OFFSET_HEADING_RAD`). Aplicarles +93.76° rotaba
    el rumbo reportado y la prueba de lazo cerrado lo cazó de inmediato:
    el robot avanzaba, pero proyectado sobre un rumbo girado el avance
    salía negativo.
    """
    if SIMULADOR_ACTIVO:
        return OFFSET_HEADING_RAD
    return OFFSETS_RUMBO_POR_ROBOT.get(int(id_robot), OFFSET_HEADING_RAD)

# ── (d) Rango plausible del laboratorio, para validación defensiva ───────
# Se usa para descartar poses absurdas cuando un marcador no está visible
# (no sabemos qué devuelve el servidor en ese caso: ¿ceros? ¿NaN? ¿menos
# filas?). Generoso a propósito: sólo descarta lo claramente imposible.
RANGO_LAB_X_M: Tuple[float, float] = (-5.0, 5.0)
RANGO_LAB_Y_M: Tuple[float, float] = (-5.0, 5.0)
RANGO_LAB_Z_M: Tuple[float, float] = (-1.0, 3.0)

# Tolerancia de norma del cuaternión (debe ser unitario).
TOL_NORMA_CUATERNION: float = 0.10

# Inclinación máxima admisible del cuerpo rígido. Más allá de esto el heading
# plano está mal definido y la pose se descarta (ver §6 del diseño: se extrae
# el yaw por atan2 directo, sin pasar por Euler completo, pero si el robot
# está muy inclinado el yaw deja de ser interpretable).
INCLINACION_MAX_RAD: float = math.radians(30.0)


# =============================================================================
# TIEMPOS Y WATCHDOG
# =============================================================================

TIMEOUT_POSES_S:    float = 1.0   # espera máxima por respuesta del servidor
TIMEOUT_CONEXION_S: float = 5.0

# ── Modo de consulta de poses ────────────────────────────────────────────
# "lote"     : una petición con los N marcadores (lo que hace el código de
#              referencia). Una respuesta = todas las poses.
# "individual": una petición POR MARCADOR.
#
# POR QUÉ EXISTE LA SEGUNDA. No sabemos qué devuelve el servidor cuando un
# marcador no está visible. Si devuelve MENOS FILAS, el cliente no puede
# saber qué fila es de quién y tiene que descartar la respuesta entera: un
# marcador ocluido deja sin pose al enjambre COMPLETO ese ciclo. Consultando
# de a uno, la oclusión de un marcador sólo afecta a su agente.
#
# El costo es N veces más ida y vuelta por tick. Con la latencia medida
# contra el simulador (p50 < 1 ms) y 5 agentes es asumible, pero hay que
# medirlo en el laboratorio antes de dejarlo fijo.
#
# Default "lote" hasta que el encargado del Robotat conteste la pregunta 1
# del README §7. Si la respuesta es "devuelve menos filas", basta con
# cambiar este valor.
MODO_CONSULTA_POSES: str = "lote"     # "lote" | "individual"

# ── Tasa de consulta de poses del LAZO REAL ──────────────────────────────
# DECISIÓN (2026-08-22): consultar una vez por DECISIÓN, no una vez por
# TICK. `FuentePosesRobotat` heredó del adaptador de Webots el hábito de
# drenar en cada tick (100 Hz) — ahí es casi gratis, un mensaje interno
# simulado. En el Robotat cada consulta es un round-trip TCP real contra
# un servidor que esta sesión demostró DOS VECES que no es robusto bajo
# carga: empuja un frame sin pedirlo al aceptar conexión (ver
# `descartar_buffer_pendiente`), y se rompió con 26 reconexiones en 1.5 s
# durante un escaneo (ver `verificar_mapeo_ids._ClientePosesIndividual`).
# Sostener 100 consultas/s durante minutos, en una máquina compartida con
# otros estudiantes, es un riesgo innecesario: 9 de cada 10 no alimentan
# ninguna decisión real (el lazo decide a 10 Hz, `DT_ENV = 0.1` en
# coordinador_enjambre.py).
#
# El margen de antigüedad ya validado (300 ms, Exp F/H) cubre el peor caso
# a 10 Hz (~100 ms) con holgura de sobra — bajar la tasa no cuesta nada de
# lo que ya se probó.
#
# PARÁMETRO, no constante: se puede subir por sesión sin tocar código
# (`cfg.HZ_CONSULTA_POSES = 100.0` antes de construir el coordinador, por
# ejemplo). La etapa 4b (latencia de actuación) NO necesita esto: usa
# `ClientePosesCrudo` directamente, un cliente separado de
# `FuentePosesRobotat` que nunca pasó por este límite — ya consulta al
# máximo régimen posible.
HZ_CONSULTA_POSES: float = 10.0

# Plan de contingencia, NO implementado — se decide con el número medido
# en la etapa 4a (p95 del round-trip de poses). Si el p95 resulta una
# fracción apreciable del presupuesto de 100 ms por decisión, la salida NO
# es volver a 100 Hz: es un hilo de sondeo en segundo plano a tasa
# moderada, con el lazo leyendo de un caché sin bloquearse en la consulta
# síncrona. Ver README_ROBOTAT.md.

# Antigüedad máxima de la pose de un agente antes de detenerlo.
# JUSTIFICACIÓN: el lazo decide cada dt = 0.1 s. El Exp H mostró que el
# sistema tolera 3 decisiones de retardo (300 ms) sin degradarse. Se toma la
# mitad de ese margen probado como umbral de seguridad: si la pose de un
# agente supera 150 ms, se lo detiene individualmente. Es conservador respecto
# de lo medido y deja margen para el jitter de red del laboratorio.
ANTIGUEDAD_MAX_POSE_S: float = 0.15

# Si se pierde la conexión al servidor de poses, se detiene TODO.
DETENER_TODO_SI_CAE_CONEXION: bool = True

# Reintentos de la orden de detención. NO convierten la parada por software
# en una parada de emergencia (ver README §S1): el comando de freno viaja por
# la misma cola TCP que las órdenes de marcha y, si el enlace está caído, el
# robot conserva su última orden. Los reintentos sólo cubren el caso de una
# pérdida transitoria de paquetes.
INTENTOS_DETENCION: int = 3
ESPERA_REINTENTO_DETENCION_S: float = 0.05

# ── Registro de diagnóstico de la cadena de poses ────────────────────────
# Auditoría del 2026-09-24 (pérdida de seguimiento en los bordes). Con True,
# las sesiones de `sesion_robotat.py` conectan a la fuente un
# `RegistroDiagnosticoPoses` (`diagnostico_poses.py`) que guarda en JSONL,
# sólo cuando pasa algo, los bytes crudos del servidor, la comprobación que
# falló y el contexto de cada agente. Apagado no cambia nada; encendido
# tampoco cambia lo que hace la fuente: sólo mira. Se enciende por sesión con
# `--diagnostico-poses`.
DIAGNOSTICO_POSES: bool = False


# =============================================================================
# ARRANQUE SEGURO
# =============================================================================
# La contraparte de §S1 (la parada por software no está garantizada). El
# arranque tiene el mismo problema al revés: si el mapeo de IDs o la
# calibración de marco están mal, el primer comando manda un robot a velocidad
# plena en la dirección equivocada antes de que nadie alcance a reaccionar.
#
# Dos defensas independientes:
#
#   (a) CHEQUEO PREVIO a la primera acción — geométrico, sobre las poses
#       observadas. Si algo no cierra, NO se arranca.
#   (b) VELOCIDAD LIMITADA durante las primeras decisiones, para que un error
#       que el chequeo no vea se manifieste despacio.

ARRANQUE_SEGURO: bool = True          # desactivar EXPLÍCITAMENTE (--sin-arranque-seguro)

# (b) Factor y duración de la rampa.
# 0.25 · V_MAX = 0.078 m/s: a esa velocidad un robot recorre 8 cm en el
# segundo que tarda una persona en reaccionar, contra 31 cm a velocidad plena.
# 50 decisiones × dt_env = 0.1 s = 5 s, tiempo suficiente para ver las cinco
# trayectorias iniciales y abortar.
FACTOR_VELOCIDAD_ARRANQUE: float = 0.25
DECISIONES_ARRANQUE:       int   = 50

# (a) Umbrales del chequeo geométrico previo.
# Arena del env: [0, 3] × [0, 3] m.
ARENA_WX_M: float = 3.0
ARENA_WY_M: float = 3.0

# Área ÚTIL del Robotat, medida en el laboratorio (2026-08-26): lo que queda
# adentro una vez descontados los bordes. NO es lo que dice la documentación
# del laboratorio, y NO coincide con la arena del env: es más grande y no es
# cuadrada.
#
# ⚠ POR QUÉ NO SE ESCALA UNA EN LA OTRA. La tentación es mapear 4.67 × 3.45
# sobre 3.0 × 3.0 y seguir. Sería incorrecto por dos razones:
#
#   1. No es cuadrada. Haría falta un factor por eje (0.64 en x, 0.87 en y),
#      y `ESCALA_POSICION` es un escalar — una similitud, no una afinidad.
#      Un círculo de seguridad se volvería una elipse.
#   2. Peor: el robot NO se encoge con el env. Con un factor de ~0.64, los
#      0.15 m de `D_SEPARACION_MIN_ARRANQUE_M` entrarían al env como 0.096 m,
#      y los 0.20 m de `MARGEN_PARED_ARRANQUE_M` como 0.128 m. La política
#      se creería despejada estando en colisión. Los márgenes del CBF están
#      en metros absolutos y se calibraron contra el chasis real.
#
# Como 3.0 ≤ 3.45 y 3.0 ≤ 4.67, un cuadrado de 3 × 3 CABE dentro del área
# útil (sobran 1.67 m en x y 0.45 m en y). La etapa 2 trabaja sobre ese
# sub-cuadrado, 1:1 en metros, y por eso la escala esperada es 1.0.
AREA_UTIL_X_M: float = 4.67
AREA_UTIL_Y_M: float = 3.45

# Separación mínima entre robots. Es el D_SAFE del env (0.15 m entre centros
# = contacto de chasis de 0.075 m de radio): arrancar por debajo de esto es
# arrancar en colisión.
D_SEPARACION_MIN_ARRANQUE_M: float = 0.15

# Distancia mínima a una pared. La política NO sabe recuperarse si arranca
# contra un muro —es el hallazgo del Exp A/B— y el margen del CBF es 0.18 m,
# así que se pide algo más: 0.20 m.
MARGEN_PARED_ARRANQUE_M: float = 0.20

# Tolerancia de las comparaciones geométricas del chequeo. Existe para que el
# umbral no sea un filo de navaja: una pose justo en el límite puede caer de
# cualquier lado por error de redondeo (0.20 + 0.15 − 0.20 da 0.14999999…),
# y el mensaje de rechazo diría "0.150 m (mínimo 0.15 m)", que parece falsa
# alarma. 1 mm está muy por debajo de lo que distingue una captura de
# movimiento y de cualquier margen operativo.
TOL_GEOMETRICA_M: float = 1e-3


# =============================================================================
# GEOMETRÍA DEL ROBOT FÍSICO
# =============================================================================
# ⚠ NO son los valores de Webots, y la diferencia no es un detalle.
#
# HAY TRES SEMIEJES EN CIRCULACIÓN EN EL LABORATORIO:
#
#   0.0700 m  nuestro proto de Webots (anchors ±0.07 en X)  → `protocolo.py`
#   0.0412 m  proto del lab11 en Webots ((96 − 2·6.8 mm)/2)
#   0.0480 m  ROBOT REAL (`laboratorio11.m`: ell = 96 mm / 2) → ESTE archivo
#
# Y dos radios: el modelo de Webots del lab usa 32 mm de RADIO donde el robot
# físico tiene 32 mm de DIÁMETRO. El `laboratorio11.m` lo dice textual:
# "Radio de rueda: 16 mm (no 32 mm como en el modelo de simulación)".
#
# Cada valor es correcto en su dominio. Los de `protocolo.py` están calibrados
# contra la geometría que Webots simula (giro verificado a 6.28 s/vuelta);
# los de acá son los del hardware. Cruzarlos escala las velocidades por más
# de 2× en el radio.
#
# Origen: `laboratorio11.m` y la hoja de datos de Pololu. VERIFICADOS sobre
# los robots del laboratorio por el operador el 2026-09-03 — medidos a mano y
# coinciden con estos valores, así que la bandera baja.
#
# Sostén independiente de la misma sesión: en el barrido del enjambre el
# seguimiento (distancia real / distancia comandada) dio 1.01–1.03 en los
# cuatro escalones estables. Ese cociente depende directamente del radio: si
# `RADIO_RUEDA_M` estuviera mal por un factor k, el seguimiento saldría k y
# no 1. Procedimiento formal: README §C4.
RADIO_RUEDA_M: float = 0.016
MEDIO_EJE_M:   float = 0.048
GEOMETRIA_NO_VERIFICADA: bool = False

# ⚠ LOS SIGNOS DE MOTOR DE WEBOTS NO EXISTEN ACÁ.
# `protocolo.SIGNO_MOTOR_1/2 = -1` es la convención del modelo de simulación
# (ver `pololu3pi_controller.m`:194-195, "en el robot real se envían las rpm
# directamente"). El cliente del Robotat manda las RPM tal cual; aplicar esos
# signos pondría a los cinco robots en reversa. Hay una prueba estática que
# falla si alguien los introduce en este camino.


# =============================================================================
# LÍMITES DE ACTUACIÓN
# =============================================================================

# `robotat_3pi_set_wheel_velocities.m` satura a ±400 rpm (hay un 850
# comentado en el original, o sea que el límite fue reducido a mano).
RPM_MAX: float = 400.0


def resumen_calibracion() -> List[str]:
    """
    Líneas de resumen para imprimir al arrancar. Deja a la vista qué está
    verificado y qué no: en el laboratorio, con cinco robots encendidos,
    saber de un vistazo que se está usando un valor sin calibrar vale mucho.
    """
    def marca(no_verificado: bool) -> str:
        return "⚠ NO VERIFICADO" if no_verificado else "verificado"

    return [
        f"  escala posición    : {ESCALA_POSICION}  [{marca(ESCALA_NO_VERIFICADA)}]",
        f"  rotación de marco  : {math.degrees(ROTACION_MARCO_RAD):.2f}°  "
        f"traslación ({TRASLACION_X_M}, {TRASLACION_Y_M}) m  "
        f"[{marca(MARCO_NO_VERIFICADO)}]",
        f"  offset de heading  : {math.degrees(OFFSET_HEADING_RAD):.2f}°  "
        f"[{marca(HEADING_NO_VERIFICADO)}]",
        f"  geometría rueda    : r={RADIO_RUEDA_M} m  ℓ={MEDIO_EJE_M} m  "
        f"[{marca(GEOMETRIA_NO_VERIFICADA)}]",
        f"  mapeo de IDs       : "
        f"{ {i: (a.id_marcador, a.id_robot) for i, a in MAPEO_AGENTES.items()} }  "
        f"[{marca(MAPEO_NO_VERIFICADO)}]",
        "  offset de rumbo por agente:",
        *[f"      agente {i} → robot {a.id_robot}: "
          f"{math.degrees(offset_rumbo_de_robot(a.id_robot)):+7.2f}°  "
          f"[{origen_offset_rumbo(a.id_robot)}]"
          for i, a in sorted(MAPEO_AGENTES.items())],
        f"  antigüedad máx pose: {ANTIGUEDAD_MAX_POSE_S*1000:.0f} ms  "
        f"· RPM máx: {RPM_MAX:.0f}",
        f"  consulta de poses  : {MODO_CONSULTA_POSES}  a  "
        f"{HZ_CONSULTA_POSES:.0f} Hz (1 vez por decisión)",
        f"  arranque seguro    : "
        + (f"ON — {FACTOR_VELOCIDAD_ARRANQUE:.0%} de V_MAX durante "
           f"{DECISIONES_ARRANQUE} decisiones "
           f"({DECISIONES_ARRANQUE * 0.1:.0f} s)"
           if ARRANQUE_SEGURO else "⚠ OFF — velocidad plena desde el tick 0"),
    ]
