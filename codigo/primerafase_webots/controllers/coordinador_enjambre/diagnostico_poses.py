"""
diagnostico_poses.py
====================
Registro de diagnóstico de la cadena de poses del Robotat. Se activa con
`config_robotat.DIAGNOSTICO_POSES` (en la sesión, `--diagnostico-poses`) y lo
usa siempre `sonda_seguimiento.py`.

POR QUÉ EXISTE (auditoría del 2026-09-24)
-----------------------------------------
El 22 y el 24 de septiembre se perdieron 14 episodios por "marcador
congelado", casi todos cerca de una pared. La auditoría de escritorio mostró,
con los CSV de decisiones, que la pose llega congelada EN LA RESPUESTA del
servidor y que el congelamiento es por marcador: en la misma respuesta en
lote, los otros cuatro seguían vivos. Pero no pudo mostrar los BYTES. El lazo
sólo guardaba la pose ya transformada; los contadores de rechazos y de
consultas fallidas salían por consola y se perdían; y el vaciado previo a
cada consulta tiraba lo que encontraba sin mirarlo.

Este módulo guarda eso, y sólo cuando pasa algo. Eventos:

  consulta_fallida      la consulta no dio una respuesta utilizable: causa
                        nombrada y bytes recibidos.
  pose_rechazada        una fila no pasó `pose_es_valida`: TODAS las
                        comprobaciones, con su valor y su umbral.
  repeticion_inicio     la fila de un agente llega bit a bit igual a la última
                        aceptada. Se registra en la PRIMERA repetición, no en
                        la décima, con los bytes de esta respuesta y los de la
                        que trajo el valor por primera vez, y qué filas de la
                        misma respuesta repitieron.
  repeticion_fin        la fila vuelve a cambiar: cuántas repeticiones, cuánto
                        duró el valor retenido y cuánto saltó la pose.
  salto_de_pose         dos lecturas aceptadas seguidas implican una velocidad
                        imposible, sin repetición en el medio: la firma de una
                        respuesta que no corresponde a su petición.
  datos_no_pedidos      el vaciado previo a una consulta encontró bytes: la
                        firma de un desfase de búfer (H5a de la auditoría).
  respuesta_sin_demora  el primer byte llegó antes de lo que tarda un viaje de
                        ida y vuelta (mínimo medido: 1.85 ms en 1 295
                        consultas): había datos esperando.
  pose_vencida / pose_recuperada
                        un agente cruza `ANTIGUEDAD_MAX_POSE_S`, una vez por
                        transición.
  conexion              al conectar: endpoint y bytes del saludo descartados.

Quien lo usa agrega los suyos (contexto, aborto, fin de episodio, marca del
operador). El archivo abre con `inicio` —la configuración vigente— y cierra
con `resumen` —conteos y contadores de la fuente—.

Cada evento de un agente lleva la última pose válida (entorno y laboratorio)
con su distancia a la pared más cercana y cuál es; el movimiento entre las dos
últimas lecturas aceptadas y entre los dos últimos valores DISTINTOS; el
tiempo desde la última pose aceptada y desde el último CAMBIO de pose —con un
flujo congelado la "última aceptada" es la congelada, así que lo que
discrimina es lo segundo—; y la última orden de rueda enviada a ese robot, si
la sesión la conectó.

GARANTÍAS
---------
· Apagado —el caso normal— la fuente no crea nada: cada gancho es un
  `if ... is not None`. Mismas respuestas, mismos contadores, mismas
  excepciones. `test_diagnostico_poses.py` lo verifica contra un servidor
  guionado.
· Encendido tampoco cambia el comportamiento: no agrega consultas ni esperas.
  Guarda en memoria las últimas respuestas crudas y escribe a disco sólo en
  los eventos, con tope por tipo y agente. Un error interno del registro se
  cuenta y se informa al cerrar; nunca sube a la fuente.
· No imprime nada durante la sesión: una línea al abrir y otra al cerrar.
· JSONL, un evento por línea, escrito en bytes con LF, en un archivo NUEVO:
  se abre en modo exclusivo, así que nunca pisa uno existente.
· Seguro entre hilos: el latido de la guía y el hilo principal usan la misma
  fuente.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import functools
import json
import math
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import (Any, Callable, Deque, Dict, List, Optional, Sequence,
                    Tuple, TypeVar)

import numpy as np

import config_robotat as cfg
from protocolo_robotat import (
    TOL_PLACEHOLDER,
    VALORES_POR_AGENTE,
    heading_desde_cuaternion,
)

#: Versión del formato del archivo. Va en el evento `inicio`.
VERSION_FORMATO: str = "1"

#: Respuestas crudas que se guardan en memoria para adjuntarlas a un evento.
HISTORIAL_CONSULTAS: int = 20

#: Eventos escritos por (tipo, agente). Pasado el tope sólo se cuentan, para
#: que una tormenta de fallos no infle el archivo ni frene el lazo.
MAX_EVENTOS_POR_CLAVE: int = 200

#: Primer byte antes de esto tras enviar ⇒ la respuesta ya estaba esperando.
#: El mínimo medido contra el Robotat fue 1.85 ms (1 295 consultas de las
#: etapas 4a y 5, 29-08); medio milisegundo deja margen de sobra.
UMBRAL_SIN_DEMORA_S: float = 0.0005

#: Velocidad implícita a partir de la cual dos lecturas seguidas son un salto.
#: La caja de la política llega a 0.31 m/s; 1 m/s no lo alcanza ningún robot.
VELOCIDAD_SALTO_M_S: float = 1.0

#: Y desplazamiento mínimo, para que el ruido con dt chico no dispare.
DESPLAZAMIENTO_SALTO_M: float = 0.05

#: Repeticiones seguidas a partir de las cuales una retención es EVENTO. Una,
#: por defecto: es lo calibrado a 10 Hz (una repetición = 100 ms; 0
#: repeticiones benignas en 34 715 pares consecutivos de las sesiones del 11,
#: 22 y 24-09). Quien consulta más rápido tiene que subirlo para medir el
#: MISMO lapso —la sonda a 20 Hz usa su `--alarma`, 2 = 100 ms—: las
#: retenciones cortas existen en toda el área (el 05-09, a ~14 ms entre
#: consultas, retuvo 1–2 filas en 555 pares, sin depender de la pared), y
#: con umbral 1 llenarían el tope de eventos antes de llegar a los bordes.
#: Las retenciones por debajo del umbral no se escriben: se cuentan, por
#: agente y por franja de distancia a la pared, en el `resumen`.
REPETICIONES_PARA_EVENTO: int = 1

#: Franjas de distancia a la pared (m) para contar las retenciones cortas.
FRANJAS_PARED_M: Tuple[float, ...] = (0.20, 0.35, 0.60)

#: Nombres de las comprobaciones de `pose_es_valida`, en el orden en que las
#: aplica. `primera_falla` usa estos nombres.
COMPROBACIONES: Tuple[str, ...] = (
    "forma", "finitud", "placeholder", "rango_x", "rango_y", "rango_z",
    "norma_cuaternion", "inclinacion",
)


# =============================================================================
# FUNCIONES PURAS: POR QUÉ UNA RESPUESTA O UNA FILA NO SIRVE
# =============================================================================

def diagnosticar_respuesta(
    datos: bytes, n_esperados: int,
) -> Tuple[Optional[np.ndarray], str, str]:
    """
    La misma decisión que `protocolo_robotat.decodificar_respuesta_poses`
    (utilizable o no), pero diciendo POR QUÉ no.

    Causas: "ok", "vacia", "no_ascii", "saludo_pegado" (el saludo del
    servidor delante del JSON: el bug del 2026-08-21), "respuestas_pegadas"
    (dos JSON seguidos: la firma de un desfase de búfer), "json_invalido"
    (truncada o basura), "no_es_lista", "valor_no_numerico" y "tamano" (no
    son 7 valores por marcador).

    "valor_no_numerico" fue, hasta el 2026-09-24, el único caso en que las
    dos funciones no coincidían: `decodificar_respuesta_poses` dejaba subir
    el `ValueError` de `np.asarray`. Se corrigió como cambio aparte (ver
    `test_respuesta_no_numerica.py`); ahora las dos devuelven "no utilizable".

    Retorna
    -------
    (matriz (N, 7) o None, causa, detalle)
    """
    if not datos:
        return None, "vacia", "no llegó ningún byte"
    try:
        texto = bytes(datos).decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        return None, "no_ascii", str(exc)
    try:
        plano = json.loads(texto)
    except json.JSONDecodeError as exc:
        if _contiene_saludo(texto):
            return None, "saludo_pegado", str(exc)
        if exc.msg == "Extra data":
            return None, "respuestas_pegadas", str(exc)
        return None, "json_invalido", str(exc)
    if not isinstance(plano, list):
        return None, "no_es_lista", type(plano).__name__
    try:
        arreglo = np.asarray(plano, dtype=np.float64).ravel()
    except (ValueError, TypeError) as exc:
        return None, "valor_no_numerico", str(exc)
    esperado = int(n_esperados) * VALORES_POR_AGENTE
    if arreglo.size != esperado:
        return None, "tamano", (f"{arreglo.size} valores; se esperaban "
                                f"{esperado}")
    return arreglo.reshape(int(n_esperados), VALORES_POR_AGENTE), "ok", ""


def diagnosticar_fila(fila: np.ndarray) -> Dict[str, Any]:
    """
    Evalúa POR SEPARADO cada comprobación de `pose_es_valida`, con su valor y
    su umbral. `pose_es_valida` corta en la primera que falla y devuelve sólo
    un texto; para saber si una pose de borde se descarta, y por cuánto, hace
    falta ver todas.

    La decisión (`valida`) y `primera_falla` coinciden con `pose_es_valida`
    por construcción —mismo orden, mismas constantes de `config_robotat`— y
    hay prueba sobre un corpus que recorre cada rama.

    Retorna
    -------
    {"valida", "primera_falla" (nombre de `COMPROBACIONES` o ""),
     "comprobaciones": {nombre: {...}}, "no_evaluadas": [...]}
    """
    arr = np.asarray(fila, dtype=np.float64)
    comp: Dict[str, Dict[str, Any]] = {}

    def resultado() -> Dict[str, Any]:
        primera = next((c for c in COMPROBACIONES
                        if c in comp and not comp[c]["ok"]), "")
        return {
            "valida": primera == "",
            "primera_falla": primera,
            "comprobaciones": comp,
            "no_evaluadas": [c for c in COMPROBACIONES if c not in comp],
        }

    comp["forma"] = {"ok": arr.shape == (VALORES_POR_AGENTE,),
                     "valor": list(arr.shape), "esperada": [VALORES_POR_AGENTE]}
    if not comp["forma"]["ok"]:
        return resultado()

    no_finitos = [k for k in range(VALORES_POR_AGENTE)
                  if not math.isfinite(float(arr[k]))]
    comp["finitud"] = {"ok": not no_finitos, "indices_no_finitos": no_finitos}
    if no_finitos:
        return resultado()

    x, y, z, qw, qx, qy, qz = (float(v) for v in arr)
    en_origen = (abs(x) <= TOL_PLACEHOLDER and abs(y) <= TOL_PLACEHOLDER
                 and abs(z) <= TOL_PLACEHOLDER)
    identidad = (abs(qw - 1.0) <= TOL_PLACEHOLDER and abs(qx) <= TOL_PLACEHOLDER
                 and abs(qy) <= TOL_PLACEHOLDER and abs(qz) <= TOL_PLACEHOLDER)
    comp["placeholder"] = {"ok": not (en_origen and identidad),
                           "en_origen": en_origen,
                           "cuaternion_identidad": identidad,
                           "tolerancia": TOL_PLACEHOLDER}

    e = cfg.ESCALA_POSICION
    for nombre, valor, rango in (("rango_x", x * e, cfg.RANGO_LAB_X_M),
                                 ("rango_y", y * e, cfg.RANGO_LAB_Y_M),
                                 ("rango_z", z * e, cfg.RANGO_LAB_Z_M)):
        comp[nombre] = {"ok": rango[0] <= valor <= rango[1],
                        "valor_m": valor, "rango_m": list(rango)}

    norma = float(np.linalg.norm(arr[3:7]))
    comp["norma_cuaternion"] = {"ok": abs(norma - 1.0) <= cfg.TOL_NORMA_CUATERNION,
                                "valor": norma,
                                "tolerancia": cfg.TOL_NORMA_CUATERNION}

    _yaw, inclinacion = heading_desde_cuaternion(qw, qx, qy, qz)
    comp["inclinacion"] = {"ok": inclinacion <= cfg.INCLINACION_MAX_RAD,
                           "valor_deg": math.degrees(inclinacion),
                           "umbral_deg": math.degrees(cfg.INCLINACION_MAX_RAD)}
    return resultado()


def distancia_a_pared(x: float, y: float) -> Tuple[float, str]:
    """Distancia de un punto del entorno a la pared más cercana, y cuál es."""
    wx, wy = float(cfg.ARENA_WX_M), float(cfg.ARENA_WY_M)
    candidatas = {"x=0": x, f"x={wx:g}": wx - x, "y=0": y, f"y={wy:g}": wy - y}
    pared = min(candidatas, key=candidatas.__getitem__)
    return float(candidatas[pared]), pared


# =============================================================================
# ESTRUCTURAS
# =============================================================================

@dataclass
class TrazaConsulta:
    """
    Lo que pasó en UNA consulta al servidor (un `_un_viaje` de la fuente).
    La crea `RegistroDiagnosticoPoses.nueva_traza` y la llena la fuente, sólo
    si el registro está activo.
    """
    peticion: bytes
    n_filas: int
    tick: Optional[int] = None
    #: Lo que el vaciado previo encontró en el búfer ANTES de pedir.
    descartado: bytearray = field(default_factory=bytearray)
    crudo: bytes = b""
    t_inicio: Optional[float] = None
    t_envio: Optional[float] = None
    t_primer_byte: Optional[float] = None
    t_fin: Optional[float] = None
    #: "ok", "sin_socket", "timeout_socket", "timeout_plazo",
    #: "conexion_perdida" o "sin_terminar" (una excepción no prevista).
    causa: str = "sin_terminar"
    detalle: str = ""
    matriz: Optional[np.ndarray] = None
    #: Por fila: ¿igual bit a bit a la respuesta anterior a la MISMA petición?
    filas_iguales: Optional[List[bool]] = None
    seq: int = 0


@dataclass
class _Lectura:
    """Una fila aceptada de un agente."""
    t: float
    seq: int
    tick: Optional[int]
    fila: np.ndarray
    pose_env: np.ndarray


_F = TypeVar("_F", bound=Callable[..., Any])


def _sin_propagar(metodo: _F) -> _F:
    """
    Un error del diagnóstico nunca debe tumbar la sesión ni cambiar lo que
    hace la fuente: se cuenta, se guarda el último mensaje y se sigue.
    """
    @functools.wraps(metodo)
    def envoltura(self: "RegistroDiagnosticoPoses", *args: Any,
                  **kwargs: Any) -> Any:
        try:
            return metodo(self, *args, **kwargs)
        except Exception as exc:                          # noqa: BLE001
            self.errores_internos += 1
            self.ultimo_error_interno = f"{type(exc).__name__}: {exc}"
            return None
    return envoltura  # type: ignore[return-value]


# =============================================================================
# REGISTRO
# =============================================================================

class RegistroDiagnosticoPoses:
    """
    Registro de eventos de la cadena de poses, en JSONL.

    Parámetros
    ----------
    ruta        : archivo a crear. Debe NO existir (modo exclusivo).
    marcadores, robots : por índice de agente, en el orden de la fuente.
    datos_inicio: campos extra para el evento `inicio` (sesión, herramienta).
    historial   : respuestas crudas que se guardan en memoria.
    max_eventos_por_clave : tope de eventos escritos por (tipo, agente).
    repeticiones_para_evento : ver `REPETICIONES_PARA_EVENTO`; alinearlo con
                  la frecuencia de consulta (1 a 10 Hz, 2 a 20 Hz).
    reloj       : el mismo reloj que usa la fuente (`time.perf_counter`).
    imprimir    : destino de las dos únicas líneas de consola.
    """

    def __init__(
        self,
        ruta: Path,
        marcadores: Sequence[int],
        robots: Sequence[int],
        datos_inicio: Optional[Dict[str, Any]] = None,
        historial: int = HISTORIAL_CONSULTAS,
        max_eventos_por_clave: int = MAX_EVENTOS_POR_CLAVE,
        reloj: Callable[[], float] = time.perf_counter,
        imprimir: Callable[[str], None] = print,
        repeticiones_para_evento: int = REPETICIONES_PARA_EVENTO,
    ) -> None:
        if len(marcadores) != len(robots):
            raise ValueError("marcadores y robots deben tener el mismo largo")
        if int(repeticiones_para_evento) < 1:
            raise ValueError("repeticiones_para_evento debe ser ≥ 1")
        self._rep_evento: int = int(repeticiones_para_evento)
        self.ruta: Path = Path(ruta)
        self._marcadores: List[int] = [int(m) for m in marcadores]
        self._robots: List[int] = [int(r) for r in robots]
        self._n: int = len(self._marcadores)
        self._max: int = int(max_eventos_por_clave)
        self._reloj = reloj
        self._imprimir = imprimir
        self._cerrojo = threading.RLock()

        self._consultas: Deque[TrazaConsulta] = deque(maxlen=int(historial))
        self._seq: int = 0
        self._ultima_matriz: Dict[bytes, np.ndarray] = {}
        self._ult: Dict[int, _Lectura] = {}         # última fila aceptada
        self._ant: Dict[int, _Lectura] = {}         # la aceptada anterior
        self._cambio: Dict[int, _Lectura] = {}      # 1.ª vez del valor vigente
        self._cambio_ant: Dict[int, _Lectura] = {}  # 1.ª vez del valor previo
        self._racha: Dict[int, int] = {}
        self._primera_rep: Dict[int, int] = {}     # seq de la 1.ª repetición
        self.retenciones_cortas: Counter = Counter()          # por agente
        self.retenciones_cortas_por_franja: Counter = Counter()
        self._vencidos: set = set()
        self._contexto: Dict[str, Any] = {}
        self._obtener_comando: Optional[Callable[[int], Any]] = None

        self.conteo: Counter = Counter()
        self._escritos: Counter = Counter()
        self.omitidos: int = 0
        self.errores_internos: int = 0
        self.ultimo_error_interno: str = ""
        self._cerrado: bool = False

        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        # "xb": exclusivo. Si el archivo ya existe, falla acá: nunca pisa.
        self._fh = open(self.ruta, "xb")
        self._t0: float = reloj()
        self._escribir_linea("inicio", None, {
            **_configuracion_vigente(),
            "marcadores": self._marcadores,
            "robots": self._robots,
            "repeticiones_para_evento": self._rep_evento,
            "max_eventos_por_clave_efectivo": self._max,
            **(datos_inicio or {}),
        })
        imprimir(f"[diag] registro de poses ACTIVO → {self.ruta}")

    # ── configuración desde quien lo usa ─────────────────────────────────
    def fijar_contexto(self, **campos: Any) -> None:
        """Fase, episodio, escalón… `None` borra el campo."""
        with self._cerrojo:
            for clave, valor in campos.items():
                if valor is None:
                    self._contexto.pop(clave, None)
                else:
                    self._contexto[clave] = valor

    def fijar_fuente_comandos(
        self, obtener: Optional[Callable[[int], Any]],
    ) -> None:
        """Callable agente → (rpm_izq, rpm_der) de la última orden enviada."""
        self._obtener_comando = obtener

    def nueva_traza(self, peticion: bytes, n_filas: int,
                    tick: Optional[int] = None) -> TrazaConsulta:
        """Traza vacía para una consulta que empieza ahora."""
        return TrazaConsulta(peticion=bytes(peticion), n_filas=int(n_filas),
                             tick=tick, t_inicio=self._reloj())

    # ── ganchos que llama la fuente ──────────────────────────────────────
    @_sin_propagar
    def registrar_consulta(self, traza: TrazaConsulta) -> None:
        """Una consulta terminada, bien o mal. La llama `_un_viaje`."""
        with self._cerrojo:
            self._seq += 1
            traza.seq = self._seq
            self._consultas.append(traza)
            ahora = traza.t_fin if traza.t_fin is not None else self._reloj()

            if traza.descartado:
                self._evento("datos_no_pedidos", None, {
                    "contiene_saludo": _contiene_saludo(_texto(traza.descartado)),
                    "consulta": self._traza_a_dict(traza)})

            if (traza.t_envio is not None and traza.t_primer_byte is not None
                    and traza.t_primer_byte - traza.t_envio
                    < UMBRAL_SIN_DEMORA_S):
                self._evento("respuesta_sin_demora", None, {
                    "umbral_ms": UMBRAL_SIN_DEMORA_S * 1000.0,
                    "consulta": self._traza_a_dict(traza)})

            if traza.causa == "ok" and traza.matriz is not None:
                previa = self._ultima_matriz.get(traza.peticion)
                if previa is not None and previa.shape == traza.matriz.shape:
                    traza.filas_iguales = [
                        bool(np.array_equal(traza.matriz[k], previa[k]))
                        for k in range(traza.matriz.shape[0])]
                self._ultima_matriz[traza.peticion] = traza.matriz.copy()
            elif traza.causa != "ok":
                _m, causa_parseo, detalle = diagnosticar_respuesta(
                    traza.crudo, traza.n_filas)
                self._evento("consulta_fallida", None, {
                    "causa": traza.causa,
                    "detalle": traza.detalle,
                    "causa_parseo": causa_parseo,
                    "detalle_parseo": detalle,
                    "consulta": self._traza_a_dict(traza),
                    "agentes": [{"agente": i, **self._contexto_agente(i, ahora)}
                                for i in range(self._n)]})

    @_sin_propagar
    def registrar_fila(
        self, i: int, fila: np.ndarray, valida: bool, motivo: str,
        pose_env: Optional[np.ndarray], ahora: float,
        tick: Optional[int] = None,
    ) -> None:
        """
        Una fila de la última respuesta, ya validada (y transformada si pasó).
        La llama `leer_poses`, una vez por agente y por consulta real.
        """
        with self._cerrojo:
            consulta = self._consultas[-1] if self._consultas else None
            if not valida:
                self._evento("pose_rechazada", i, {
                    "motivo": motivo,
                    "diagnostico": diagnosticar_fila(fila),
                    "fila_cruda": [_num(v) for v in np.asarray(fila).ravel()],
                    "consulta": self._traza_a_dict(consulta),
                    **self._contexto_agente(i, ahora)})
                return

            lectura = _Lectura(
                t=float(ahora),
                seq=consulta.seq if consulta is not None else 0,
                tick=tick,
                fila=np.array(fila, dtype=np.float64, copy=True),
                pose_env=np.array(pose_env, dtype=np.float64, copy=True))
            previa = self._ult.get(i)

            # ⚠ DECISIÓN DE LA QUE DEPENDE LA CORRECCIÓN: se compara la fila
            # COMPLETA de 7 valores —posición Y cuaternión—, nunca sólo la
            # posición. Con 10 µm de ruido de captura UNA coordenada float32
            # repite por azar en ~0.33 % de los pares; la fila completa, 0 en
            # 400 000 (verificación del autor, 2026-09-24). Reducirlo a
            # (x, y) llenaría el registro de falsas retenciones.
            if previa is not None and np.array_equal(lectura.fila, previa.fila):
                n = self._racha.get(i, 0) + 1
                self._racha[i] = n
                if n == 1:
                    self._primera_rep[i] = lectura.seq
                if n == self._rep_evento:
                    origen = self._cambio.get(i, previa)
                    primera = self._primera_rep.get(i, lectura.seq)
                    self._evento("repeticion_inicio", i, {
                        "repeticiones": n,
                        "umbral_repeticiones": self._rep_evento,
                        "duracion_valor_retenido_s": lectura.t - origen.t,
                        "fila_cruda": [_num(v) for v in lectura.fila],
                        "pose_env": [float(v) for v in lectura.pose_env],
                        "filas_iguales_a_la_respuesta_anterior":
                            consulta.filas_iguales if consulta else None,
                        "consulta": self._traza_a_dict(consulta),
                        "consulta_primera_repeticion":
                            (self._traza_a_dict(self._buscar(primera))
                             if primera != lectura.seq else None),
                        "consulta_que_trajo_el_valor":
                            self._traza_a_dict(self._buscar(origen.seq)),
                        **self._contexto_agente(i, ahora)})
            else:
                n = self._racha.get(i, 0)
                if previa is not None and 0 < n < self._rep_evento:
                    # Retención corta, por debajo del umbral: se cuenta.
                    d_pared, _pared = distancia_a_pared(
                        float(previa.pose_env[0]), float(previa.pose_env[1]))
                    self.retenciones_cortas[i] += 1
                    self.retenciones_cortas_por_franja[_franja(d_pared)] += 1
                elif previa is not None and n > 0:
                    origen = self._cambio.get(i, previa)
                    self._evento("repeticion_fin", i, {
                        "repeticiones": n,
                        "umbral_repeticiones": self._rep_evento,
                        "duracion_valor_retenido_s": lectura.t - origen.t,
                        "salto": _movimiento(previa, lectura),
                        "pose_retenida_env": [float(v) for v in previa.pose_env],
                        "pose_nueva_env": [float(v) for v in lectura.pose_env],
                        "fila_cruda_nueva": [_num(v) for v in lectura.fila],
                        "consulta": self._traza_a_dict(consulta),
                        **self._contexto_agente(i, ahora)})
                elif previa is not None:
                    mov = _movimiento(previa, lectura)
                    v = mov["velocidad_m_s"]
                    if (mov["desplazamiento_m"] > DESPLAZAMIENTO_SALTO_M
                            and v is not None and v > VELOCIDAD_SALTO_M_S):
                        self._evento("salto_de_pose", i, {
                            "salto": mov,
                            "pose_previa_env": [float(x) for x in previa.pose_env],
                            "pose_nueva_env": [float(x) for x in lectura.pose_env],
                            "consulta": self._traza_a_dict(consulta),
                            "consulta_previa":
                                self._traza_a_dict(self._buscar(previa.seq)),
                            **self._contexto_agente(i, ahora)})
                self._racha[i] = 0
                if i in self._cambio:
                    self._cambio_ant[i] = self._cambio[i]
                self._cambio[i] = lectura
            if previa is not None:
                self._ant[i] = previa
            self._ult[i] = lectura

    @_sin_propagar
    def registrar_vencidos(self, vencidos: Sequence[int], ahora: float) -> None:
        """
        Estado de antigüedad de los agentes. Sólo escribe las TRANSICIONES:
        `agentes_vencidos` se consulta varias veces por decisión.
        """
        with self._cerrojo:
            actuales = {int(i) for i in vencidos}
            for i in sorted(actuales - self._vencidos):
                self._evento("pose_vencida", i, {
                    "umbral_s": cfg.ANTIGUEDAD_MAX_POSE_S,
                    "nunca_visto": i not in self._ult,
                    **self._contexto_agente(i, ahora)})
            for i in sorted(self._vencidos - actuales):
                self._evento("pose_recuperada", i,
                             self._contexto_agente(i, ahora))
            self._vencidos = actuales

    @_sin_propagar
    def registrar_evento(self, tipo: str, agente: Optional[int] = None,
                         **datos: Any) -> None:
        """Evento libre de quien usa el registro (sesión, sonda)."""
        with self._cerrojo:
            if agente is not None:
                datos = {**self._contexto_agente(int(agente), self._reloj()),
                         **datos}
            elif self._contexto:
                datos = {"contexto": dict(self._contexto), **datos}
            self._evento(tipo, agente, datos)

    def cerrar(self, resumen_fuente: Optional[Sequence[str]] = None,
               contadores: Optional[Dict[str, Any]] = None) -> None:
        """
        Escribe el resumen y cierra. Idempotente y NO lanza: la sesión lo
        llama en su `finally`, justo antes de cerrar los sockets, y un error
        de disco acá no puede dejar un robot sin su orden de parada.
        """
        with self._cerrojo:
            if self._cerrado:
                return
            try:
                self._escribir_linea("resumen", None, {
                    "consultas_registradas": self._seq,
                    "eventos_por_tipo": dict(sorted(self.conteo.items())),
                    "eventos_omitidos_por_tope": self.omitidos,
                    "repeticiones_para_evento": self._rep_evento,
                    "retenciones_cortas_por_agente": {
                        str(i): n for i, n
                        in sorted(self.retenciones_cortas.items())},
                    "retenciones_cortas_por_franja_d_pared_m": dict(
                        sorted(self.retenciones_cortas_por_franja.items())),
                    "errores_internos": self.errores_internos,
                    "ultimo_error_interno": self.ultimo_error_interno,
                    "resumen_fuente": list(resumen_fuente or []),
                    **(contadores or {})})
            except Exception as exc:                      # noqa: BLE001
                self.errores_internos += 1
                self.ultimo_error_interno = f"{type(exc).__name__}: {exc}"
            finally:
                self._cerrado = True
                try:
                    self._fh.close()
                except Exception:                         # noqa: BLE001
                    pass
        eventos = dict(sorted(self.conteo.items())) or "ninguno"
        extra = (f" · ⚠ {self.errores_internos} error(es) interno(s) del "
                 f"registro" if self.errores_internos else "")
        try:
            self._imprimir(f"[diag] registro de poses cerrado: {self._seq} "
                           f"consultas; eventos {eventos}{extra} → {self.ruta}")
        except Exception:                                 # noqa: BLE001
            pass

    # ── internos ─────────────────────────────────────────────────────────
    def _evento(self, tipo: str, agente: Optional[int],
                datos: Dict[str, Any]) -> None:
        """Cuenta siempre; escribe si no se pasó el tope y está abierto."""
        self.conteo[tipo] += 1
        clave = (tipo, agente)
        if self._cerrado or self._escritos[clave] >= self._max:
            self.omitidos += 1
            return
        self._escritos[clave] += 1
        self._escribir_linea(tipo, agente, datos)

    def _escribir_linea(self, tipo: str, agente: Optional[int],
                        datos: Dict[str, Any]) -> None:
        linea: Dict[str, Any] = {
            "t_s": round(self._reloj() - self._t0, 6),
            "hora": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "tipo": tipo,
        }
        if agente is not None:
            linea["agente"] = int(agente)
        linea.update(datos)
        texto = json.dumps(_limpiar(linea), ensure_ascii=False, allow_nan=False)
        self._fh.write(texto.encode("utf-8") + b"\n")
        self._fh.flush()

    def _buscar(self, seq: int) -> Optional[TrazaConsulta]:
        for traza in reversed(self._consultas):
            if traza.seq == seq:
                return traza
        return None

    def _traza_a_dict(
        self, traza: Optional[TrazaConsulta],
    ) -> Optional[Dict[str, Any]]:
        if traza is None:
            return None

        def ms(a: Optional[float], b: Optional[float]) -> Optional[float]:
            return None if a is None or b is None else round((b - a) * 1e3, 3)

        return {
            "seq": traza.seq,
            "tick": traza.tick,
            "peticion": _texto(traza.peticion),
            "descartado_antes_len": len(traza.descartado),
            "descartado_antes": _texto(traza.descartado),
            "crudo_len": len(traza.crudo),
            "crudo": _texto(traza.crudo),
            "causa": traza.causa,
            "detalle": traza.detalle,
            "ms_hasta_primer_byte": ms(traza.t_envio, traza.t_primer_byte),
            "ms_total": ms(traza.t_inicio, traza.t_fin),
        }

    def _contexto_agente(self, i: int, ahora: float) -> Dict[str, Any]:
        """Lo que se sabe de un agente en este instante (ver el módulo)."""
        d: Dict[str, Any] = {"robot": self._robots[i],
                             "marcador": self._marcadores[i]}
        if self._contexto:
            d["contexto"] = dict(self._contexto)
        ult = self._ult.get(i)
        if ult is not None:
            x, y = float(ult.pose_env[0]), float(ult.pose_env[1])
            d_pared, pared = distancia_a_pared(x, y)
            d["ultima_valida"] = {
                "pose_env": [x, y, float(ult.pose_env[2])],
                "lab_xyz": [_num(v) for v in ult.fila[:3]],
                "d_pared_m": d_pared,
                "pared": pared,
                "hace_s": ahora - ult.t,
                "seq": ult.seq,
                "tick": ult.tick,
            }
            ant = self._ant.get(i)
            if ant is not None:
                d["entre_ultimas_dos_aceptadas"] = _movimiento(ant, ult)
        cambio = self._cambio.get(i)
        if cambio is not None:
            d["ultimo_cambio_hace_s"] = ahora - cambio.t
            cambio_ant = self._cambio_ant.get(i)
            if cambio_ant is not None:
                d["entre_ultimos_dos_valores_distintos"] = _movimiento(
                    cambio_ant, cambio)
        if self._obtener_comando is not None:
            try:
                orden = self._obtener_comando(i)
            except Exception:                              # noqa: BLE001
                orden = None
            if orden is not None:
                d["ultima_orden_rpm"] = [float(v) for v in orden]
        return d


# =============================================================================
# AUXILIARES
# =============================================================================

def _contiene_saludo(texto: str) -> bool:
    """¿Está el saludo del servidor en este texto?"""
    # Import perezoso: `adaptadores_robotat` no depende de este módulo, y así
    # tampoco hay ciclo al importar.
    from adaptadores_robotat import SALUDO_SERVIDOR
    return SALUDO_SERVIDOR.decode("ascii") in texto


def _franja(d_pared: float) -> str:
    """Franja de distancia a la pared, con los cortes de `FRANJAS_PARED_M`."""
    anterior = 0.0
    for corte in FRANJAS_PARED_M:
        if d_pared < corte:
            return f"{anterior:.2f}-{corte:.2f}"
        anterior = corte
    return f">={anterior:.2f}"


def _texto(datos: Any) -> str:
    """Bytes → texto legible y reversible: ASCII tal cual, el resto \\xNN."""
    if not datos:
        return ""
    return bytes(datos).decode("ascii", errors="backslashreplace")


def _num(v: Any) -> Any:
    """Número para JSON; los no finitos van como texto ("nan", "inf")."""
    f = float(v)
    return f if math.isfinite(f) else str(f)


def _movimiento(a: _Lectura, b: _Lectura) -> Dict[str, Any]:
    """Desplazamiento, intervalo, velocidad implícita y giro entre lecturas."""
    d = float(np.linalg.norm(b.pose_env[:2] - a.pose_env[:2]))
    dt = float(b.t - a.t)
    giro = float(b.pose_env[2] - a.pose_env[2])
    giro = math.atan2(math.sin(giro), math.cos(giro))
    return {"desplazamiento_m": d, "dt_s": dt,
            "velocidad_m_s": d / dt if dt > 0 else None,
            "giro_deg": math.degrees(giro)}


def _limpiar(obj: Any) -> Any:
    """Deja cualquier cosa serializable en JSON estricto."""
    if isinstance(obj, dict):
        return {str(k): _limpiar(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, deque)):
        return [_limpiar(v) for v in obj]
    if isinstance(obj, (bytes, bytearray)):
        return _texto(obj)
    if isinstance(obj, np.ndarray):
        return [_limpiar(v) for v in obj.tolist()]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return _num(obj)
    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    return repr(obj)


def _configuracion_vigente() -> Dict[str, Any]:
    """Lo que hace falta para interpretar el archivo meses después."""
    host, puerto = cfg.endpoint_poses()
    return {
        "version_formato": VERSION_FORMATO,
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "endpoint_poses": f"{host}:{puerto}",
        "simulador": bool(cfg.SIMULADOR_ACTIVO),
        "modo_consulta": cfg.MODO_CONSULTA_POSES,
        "hz_consulta": cfg.HZ_CONSULTA_POSES,
        "timeout_poses_s": cfg.TIMEOUT_POSES_S,
        "antiguedad_max_pose_s": cfg.ANTIGUEDAD_MAX_POSE_S,
        "rango_lab_m": {"x": list(cfg.RANGO_LAB_X_M),
                        "y": list(cfg.RANGO_LAB_Y_M),
                        "z": list(cfg.RANGO_LAB_Z_M)},
        "tol_norma_cuaternion": cfg.TOL_NORMA_CUATERNION,
        "inclinacion_max_deg": math.degrees(cfg.INCLINACION_MAX_RAD),
        "calibracion": {
            "escala": cfg.ESCALA_POSICION,
            "rotacion_deg": math.degrees(cfg.ROTACION_MARCO_RAD),
            "traslacion_m": [cfg.TRASLACION_X_M, cfg.TRASLACION_Y_M],
        },
        "arena_m": [cfg.ARENA_WX_M, cfg.ARENA_WY_M],
        "umbrales_registro": {
            "sin_demora_ms": UMBRAL_SIN_DEMORA_S * 1e3,
            "salto_velocidad_m_s": VELOCIDAD_SALTO_M_S,
            "salto_desplazamiento_m": DESPLAZAMIENTO_SALTO_M,
            "historial_consultas": HISTORIAL_CONSULTAS,
            "max_eventos_por_clave": MAX_EVENTOS_POR_CLAVE,
            "franjas_pared_m": list(FRANJAS_PARED_M),
        },
    }
