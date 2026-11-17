"""
test_diagnostico_poses.py
=========================
Pruebas del registro de diagnóstico de la cadena de poses (auditoría de
pérdida de seguimiento en los bordes, 2026-09-24): `diagnostico_poses.py`,
sus ganchos en `adaptadores_robotat.py` y `sesion_robotat.py`, los fallos
nuevos del simulador y `sonda_seguimiento.py`. Corren SIN hardware:

    python test_diagnostico_poses.py

Lo que más importa probar es lo que se prometió al pedir el OK:
  1. APAGADO NO CAMBIA NADA — la fuente nueva con el registro apagado da,
     contra un servidor guionado, exactamente lo mismo que la fuente ORIGINAL
     (el respaldo `adaptadores_robotat_respaldo_20260924_preDiag.py`) y que
     la nueva con el registro encendido: mismas poses, mismos contadores.
  2. el registro captura lo que la auditoría no pudo ver: los bytes crudos,
     la comprobación que falló, la PRIMERA repetición de un marcador con la
     respuesta que trajo el valor, y lo que el vaciado del búfer tiraba;
  3. no ensucia la consola: una línea al abrir, otra al cerrar;
  4. `--alternar-orden` de la sonda detecta una respuesta que corresponde a
     la petición anterior —y sin alternar, no: por eso la sesión no puede—.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import math
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

_CARPETA = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import calibracion_sesion as calib
import config_robotat as cfg
import sesion_robotat as ses
import sonda_seguimiento as sonda
from adaptadores_robotat import (
    SALUDO_SERVIDOR,
    FuentePosesRobotat,
    descartar_buffer_pendiente,
)
from diagnostico_poses import (
    RegistroDiagnosticoPoses,
    diagnosticar_fila,
    diagnosticar_respuesta,
    distancia_a_pared,
)
from protocolo_robotat import decodificar_respuesta_poses, pose_es_valida
from simulador_robotat import FallasSimulador, SimuladorRobotat

#: El saludo real: 52 B, medido el 2026-08-25.
SALUDO_REAL: bytes = b"Connected to the Robotat server... Type EXIT to stop"
PLACEHOLDER: List[float] = [0.0, -0.0, 0.0, 1.0, 0.0, -0.0, 0.0]


def _mudo(_texto: str) -> None:
    """`imprimir` que no imprime."""


def fila(x: float, y: float, yaw: float = 0.0, z: float = 0.05) -> List[float]:
    """[x, y, z, qw, qx, qy, qz] de un robot plano con rumbo `yaw`."""
    return [x, y, z, math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)]


def respuesta(*filas: List[float]) -> bytes:
    """Respuesta JSON plana, agente-major, como la del servidor."""
    return json.dumps([v for f in filas for v in f]).encode("ascii")


def eventos(ruta: Path) -> List[Dict[str, Any]]:
    """Los eventos de un JSONL del registro."""
    return [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def puerto_libre() -> int:
    """Un puerto TCP libre de localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class ServidorGuionado:
    """
    Servidor de poses de prueba. Saluda al conectar, como el real, y contesta
    la petición número n con `responder(n, marcadores)` (bytes, o None para
    no contestar). `empujar_tras[n]` manda además bytes NO pedidos después
    de la respuesta n: la firma de un desfase de búfer.
    """

    def __init__(self, responder: Callable[[int, List[int]], Optional[bytes]],
                 empujar_tras: Optional[Dict[int, bytes]] = None,
                 demora_s: float = 0.0) -> None:
        self._responder = responder
        self._empujar = dict(empujar_tras or {})
        self._demora = float(demora_s)
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(4)
        self._srv.settimeout(0.2)
        self.puerto: int = int(self._srv.getsockname()[1])
        self.peticiones: List[List[int]] = []
        self._cerrojo = threading.Lock()
        self._parar = threading.Event()
        self._hilos: List[threading.Thread] = []

    def __enter__(self) -> "ServidorGuionado":
        h = threading.Thread(target=self._aceptar, daemon=True)
        h.start()
        self._hilos.append(h)
        return self

    def __exit__(self, *_exc: object) -> None:
        self._parar.set()
        try:
            self._srv.close()
        except OSError:
            pass
        for h in self._hilos:
            h.join(timeout=1.0)

    def _aceptar(self) -> None:
        while not self._parar.is_set():
            try:
                con, _ = self._srv.accept()
            except (socket.timeout, OSError):
                continue
            h = threading.Thread(target=self._atender, args=(con,), daemon=True)
            h.start()
            self._hilos.append(h)

    def _atender(self, con: socket.socket) -> None:
        con.settimeout(0.2)
        try:
            con.sendall(SALUDO_REAL)
            pendiente = b""
            while not self._parar.is_set():
                try:
                    trozo = con.recv(4096)
                except socket.timeout:
                    continue
                if not trozo:
                    return
                pendiente += trozo
                if pendiente.startswith(b"EXIT"):
                    return
                while b"}" in pendiente:
                    fin = pendiente.index(b"}") + 1
                    texto, pendiente = pendiente[:fin], pendiente[fin:]
                    pld = json.loads(texto.decode("ascii"))["pld"]
                    pld = list(pld) if isinstance(pld, list) else [pld]
                    with self._cerrojo:
                        self.peticiones.append(pld)
                        n = len(self.peticiones)
                    if self._demora:
                        time.sleep(self._demora)
                    datos = self._responder(n, pld)
                    if datos:
                        con.sendall(datos)
                    extra = self._empujar.get(n)
                    if extra:
                        # Con un respiro: pegado a la respuesta, el cliente
                        # lo leería junto con ella ("respuestas_pegadas") en
                        # vez de encontrarlo en el vaciado de la siguiente.
                        time.sleep(0.02)
                        con.sendall(extra)
        except OSError:
            return
        finally:
            try:
                con.close()
            except OSError:
                pass


class ConfigAislada:
    """Guarda y restaura lo que estas pruebas tocan de `config_robotat`."""

    CAMPOS = ("SIMULADOR_ACTIVO", "SIMULADOR_HOST", "SIMULADOR_PUERTO_POSES",
              "SIMULADOR_PUERTO_BASE_ROBOT", "MAPEO_AGENTES", "TIMEOUT_POSES_S",
              "DIAGNOSTICO_POSES", "ESCALA_POSICION", "ROTACION_MARCO_RAD",
              "TRASLACION_X_M", "TRASLACION_Y_M", "OFFSET_HEADING_RAD",
              "MARCO_NO_VERIFICADO", "HEADING_NO_VERIFICADO",
              "MAPEO_NO_VERIFICADO", "ESCALA_NO_VERIFICADA",
              # `calib.aplicar_a_config` los REEMPLAZA (no los muta): basta
              # con devolver la referencia original.
              "OFFSETS_RUMBO_POR_ROBOT", "OFFSETS_RUMBO_MEDIDOS")

    def __enter__(self) -> "ConfigAislada":
        self._previo = {c: getattr(cfg, c) for c in self.CAMPOS}
        return self

    def __exit__(self, *_exc: object) -> None:
        for campo, valor in self._previo.items():
            setattr(cfg, campo, valor)


def _dos_agentes(puerto_poses: int, puerto_base: int = 19090) -> None:
    """Endpoints al servidor local, marcadores 1 y 5, marco identidad."""
    cfg.activar_simulador_local(puerto_poses=puerto_poses,
                                puerto_base=puerto_base)
    cfg.MAPEO_AGENTES = {
        0: cfg.AsignacionAgente(id_marcador=1, id_robot=1),
        1: cfg.AsignacionAgente(id_marcador=5, id_robot=5),
    }
    cfg.ESCALA_POSICION = 1.0
    cfg.ROTACION_MARCO_RAD = 0.0
    cfg.TRASLACION_X_M = 1.5
    cfg.TRASLACION_Y_M = 1.5
    cfg.OFFSET_HEADING_RAD = 0.0


# =============================================================================
# 1. FUNCIONES PURAS
# =============================================================================

class PruebaDiagnosticarRespuesta(unittest.TestCase):
    """Misma decisión que `decodificar_respuesta_poses`, con la causa."""

    CASOS = [
        (b"[0.3, -0.2, 0.05, 1.0, 0.0, 0.0, 0.0]", 1, "ok"),
        (b"[0.3,-0.2,0.05,1,0,0,0,0.1,0.2,0.05,1,0,0,0]", 2, "ok"),
        (b"[NaN, 0, 0.05, 1, 0, 0, 0]", 1, "ok"),      # parsea; lo rechaza la fila
        (b"", 1, "vacia"),
        (SALUDO_REAL + b"[0.3, -0.2, 0.05, 1.0, 0.0, 0.0, 0.0]", 1,
         "saludo_pegado"),
        (b"[0.3,-0.2,0.05,1,0,0,0][0.3,-0.2,0.05,1,0,0,0]", 1,
         "respuestas_pegadas"),
        (b"[0.3, -0.2, 0.05, 1.0, 0.0", 1, "json_invalido"),
        (b'{"err":"mocap busy"}', 1, "no_es_lista"),
        (b"[0.3, -0.2, 0.05, 1.0, 0.0, 0.0]", 1, "tamano"),
        (b"[0.3,-0.2,0.05,1,0,0,0]", 2, "tamano"),
        (b"[0.3, -0.2, \xff 0.05]", 1, "no_ascii"),
    ]

    def test_misma_decision_y_causa_nombrada(self) -> None:
        for datos, n, causa in self.CASOS:
            with self.subTest(datos=datos[:40], n=n):
                m, c, _detalle = diagnosticar_respuesta(datos, n)
                self.assertEqual(c, causa)
                original = decodificar_respuesta_poses(datos, n)
                self.assertEqual(original is None, m is None)
                if m is not None:
                    np.testing.assert_array_equal(m, original)

    def test_texto_dentro_de_la_lista(self) -> None:
        """
        El único caso donde las dos no coinciden: `decodificar_respuesta_poses`
        deja subir el `ValueError` de numpy. Acá se nombra la causa.
        """
        _m, causa, _d = diagnosticar_respuesta(
            b'[0.3, "a", 0.05, 1.0, 0.0, 0.0, 0.0]', 1)
        self.assertEqual(causa, "valor_no_numerico")


class PruebaDiagnosticarFila(unittest.TestCase):
    """`valida` y `primera_falla` coinciden con `pose_es_valida`, rama a rama."""

    C20 = math.cos(math.radians(10.0))
    S20 = math.sin(math.radians(10.0))      # inclinación 20°
    C40 = math.cos(math.radians(20.0))
    S40 = math.sin(math.radians(20.0))      # inclinación 40°

    CORPUS = {
        "valida":        [0.30, -0.20, 0.05, 1.0, 0.0, 0.0, 0.0],
        "placeholder":   PLACEHOLDER,
        "origen_rotado": [0.0, 0.0, 0.0, math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5)],
        "nan":           [float("nan"), 0.0, 0.05, 1.0, 0.0, 0.0, 0.0],
        "inf":           [0.3, float("inf"), 0.05, 1.0, 0.0, 0.0, 0.0],
        "x_fuera":       [5.5, 0.0, 0.05, 1.0, 0.0, 0.0, 0.0],
        "x_borde":       [4.9, 0.0, 0.05, 1.0, 0.0, 0.0, 0.0],
        "y_fuera":       [0.0, -6.0, 0.05, 1.0, 0.0, 0.0, 0.0],
        "z_alto":        [0.0, 0.1, 3.5, 1.0, 0.0, 0.0, 0.0],
        "z_bajo":        [0.0, 0.1, -1.5, 1.0, 0.0, 0.0, 0.0],
        "milimetros":    [300.0, -200.0, 50.0, 1.0, 0.0, 0.0, 0.0],
        "norma":         [0.3, 0.2, 0.05, 0.5, 0.0, 0.0, 0.0],
        "inclinado_40":  [0.3, 0.2, 0.05, C40, S40, 0.0, 0.0],
        "inclinado_20":  [0.3, 0.2, 0.05, C20, S20, 0.0, 0.0],
        "forma":         [0.3, 0.2, 0.05, 1.0, 0.0, 0.0],
    }

    @staticmethod
    def _nombre(motivo: str) -> str:
        for prefijo, nombre in (("forma", "forma"),
                                ("valores no finitos", "finitud"),
                                ("marcador no trackeado", "placeholder"),
                                ("x=", "rango_x"), ("y=", "rango_y"),
                                ("z=", "rango_z"),
                                ("cuaternión de norma", "norma_cuaternion"),
                                ("inclinación", "inclinacion")):
            if motivo.startswith(prefijo):
                return nombre
        return f"?{motivo}"

    def test_coincide_con_pose_es_valida(self) -> None:
        with ConfigAislada():
            for escala in (1.0, 1.0166876084261378):     # la del laboratorio
                cfg.ESCALA_POSICION = escala
                for nombre, valores in self.CORPUS.items():
                    with self.subTest(caso=nombre, escala=escala):
                        arr = np.array(valores, dtype=np.float64)
                        ok, motivo = pose_es_valida(arr)
                        d = diagnosticar_fila(arr)
                        self.assertEqual(d["valida"], ok)
                        self.assertEqual(d["primera_falla"],
                                         "" if ok else self._nombre(motivo))

    def test_informa_valor_y_umbral(self) -> None:
        d = diagnosticar_fila(np.array(self.CORPUS["x_fuera"]))
        rx = d["comprobaciones"]["rango_x"]
        self.assertFalse(rx["ok"])
        self.assertAlmostEqual(rx["valor_m"], 5.5 * cfg.ESCALA_POSICION)
        self.assertEqual(rx["rango_m"], list(cfg.RANGO_LAB_X_M))
        # las demás se evalúan igual, aunque la primera ya falló
        self.assertTrue(d["comprobaciones"]["norma_cuaternion"]["ok"])

    def test_distancia_a_pared(self) -> None:
        self.assertEqual(distancia_a_pared(0.10, 1.5), (0.10, "x=0"))
        d, pared = distancia_a_pared(1.5, 2.9)
        self.assertAlmostEqual(d, 0.1)
        self.assertEqual(pared, "y=3")


class PruebaDescarteConDestino(unittest.TestCase):
    """`descartar_buffer_pendiente(destino=...)`: mismo conteo, y el contenido."""

    def test_guarda_lo_que_tira_sin_cambiar_el_conteo(self) -> None:
        for con_destino in (False, True):
            a, b = socket.socketpair()
            try:
                b.sendall(b"[9.9, 8.8]")
                time.sleep(0.05)
                destino = bytearray() if con_destino else None
                n = descartar_buffer_pendiente(a, destino=destino)
                self.assertEqual(n, 10)
                if con_destino:
                    self.assertEqual(bytes(destino), b"[9.9, 8.8]")
                self.assertEqual(descartar_buffer_pendiente(a), 0)
            finally:
                a.close()
                b.close()


# =============================================================================
# 2. EL REGISTRO, CON TRAZAS SINTÉTICAS
# =============================================================================

class PruebaRegistroSintetico(unittest.TestCase):
    """La lógica de eventos, sin sockets."""

    PETICION = b'{"dst":1,"cmd":1,"pld":[1,5]}'

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="diag_test_"))
        self.ruta = self.tmp / "registro.jsonl"
        self.salida: List[str] = []
        self.reg = RegistroDiagnosticoPoses(
            self.ruta, [1, 5], [1, 5], imprimir=self.salida.append)

    def tearDown(self) -> None:
        self.reg.cerrar()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _consulta(self, filas: List[List[float]], t: float,
                  primer_byte_s: float = 0.002, causa: str = "ok",
                  crudo: Optional[bytes] = None, descartado: bytes = b"",
                  reg: Optional[RegistroDiagnosticoPoses] = None) -> None:
        reg = reg or self.reg
        tr = reg.nueva_traza(self.PETICION, len(filas), tick=0)
        tr.t_inicio, tr.t_envio = t, t + 1e-4
        tr.t_primer_byte = t + 1e-4 + primer_byte_s
        tr.t_fin = tr.t_primer_byte + 5e-4
        tr.crudo = crudo if crudo is not None else respuesta(*filas)
        tr.descartado.extend(descartado)
        tr.causa = causa
        if causa == "ok":
            tr.matriz = np.array(filas, dtype=np.float64)
        reg.registrar_consulta(tr)
        if causa == "ok":
            for i, f in enumerate(filas):
                pose = np.array([f[0] + 1.5, f[1] + 1.5, 0.0])
                reg.registrar_fila(i, np.array(f), True, "", pose, t, 0)

    def _tipos(self) -> List[str]:
        self.reg.cerrar()
        return [e["tipo"] for e in eventos(self.ruta)]

    def test_la_repeticion_se_registra_en_la_primera_con_la_respuesta_de_origen(
            self) -> None:
        a0, b0 = fila(-0.50, 0.20), fila(0.30, -0.40)
        self._consulta([a0, b0], 0.0)
        self._consulta([fila(-0.49, 0.20), b0], 0.1)    # repite el agente 1
        self._consulta([fila(-0.48, 0.20), b0], 0.2)    # sigue repitiendo
        self._consulta([fila(-0.47, 0.20), fila(0.32, -0.40)], 0.3)
        self.reg.cerrar()
        ev = eventos(self.ruta)
        inicios = [e for e in ev if e["tipo"] == "repeticion_inicio"]
        self.assertEqual(len(inicios), 1)
        ini = inicios[0]
        self.assertEqual(ini["agente"], 1)
        self.assertEqual(ini["filas_iguales_a_la_respuesta_anterior"],
                         [False, True])
        # la respuesta que trajo el valor retenido es la primera (seq 1)
        self.assertEqual(ini["consulta_que_trajo_el_valor"]["seq"], 1)
        self.assertEqual(ini["consulta"]["seq"], 2)
        self.assertIn(json.dumps(b0)[1:-1], ini["consulta"]["crudo"])
        fines = [e for e in ev if e["tipo"] == "repeticion_fin"]
        self.assertEqual(len(fines), 1)
        self.assertEqual(fines[0]["repeticiones"], 2)
        self.assertAlmostEqual(fines[0]["duracion_valor_retenido_s"], 0.3)
        self.assertAlmostEqual(fines[0]["salto"]["desplazamiento_m"], 0.02)
        # el contexto dice cuánto hace que el valor no cambia
        self.assertAlmostEqual(ini["ultimo_cambio_hace_s"], 0.1)

    def test_salto_imposible_sin_repeticion(self) -> None:
        self._consulta([fila(-0.50, 0.20), fila(0.30, -0.40)], 0.0)
        self._consulta([fila(0.50, 0.20), fila(0.31, -0.40)], 0.1)   # 1 m en 0.1 s
        self._consulta([fila(-1.40, 0.20), fila(0.32, -0.40)], 100.0)  # lento
        tipos = self._tipos()
        self.assertEqual(tipos.count("salto_de_pose"), 1)

    def test_vencidas_solo_en_las_transiciones(self) -> None:
        self._consulta([fila(-0.50, 0.20), fila(0.30, -0.40)], 0.0)
        for vencidos in ([0], [0], [0], [], [0, 1]):
            self.reg.registrar_vencidos(vencidos, 1.0)
        tipos = self._tipos()
        self.assertEqual(tipos.count("pose_vencida"), 3)
        self.assertEqual(tipos.count("pose_recuperada"), 1)

    def test_datos_no_pedidos_y_respuesta_sin_demora(self) -> None:
        a, b = fila(-0.50, 0.20), fila(0.30, -0.40)
        self._consulta([a, b], 0.0, descartado=b"[9.9]")
        self._consulta([a, b], 0.1, descartado=SALUDO_SERVIDOR)
        self._consulta([fila(-0.4, 0.2), fila(0.4, -0.4)], 0.2,
                       primer_byte_s=1e-4)
        self.reg.cerrar()
        ev = eventos(self.ruta)
        no_pedidos = [e for e in ev if e["tipo"] == "datos_no_pedidos"]
        self.assertEqual([e["contiene_saludo"] for e in no_pedidos],
                         [False, True])
        self.assertEqual(no_pedidos[0]["consulta"]["descartado_antes"], "[9.9]")
        self.assertEqual(sum(e["tipo"] == "respuesta_sin_demora" for e in ev), 1)

    def test_consulta_fallida_con_causa_y_bytes(self) -> None:
        self._consulta([fila(0, 0), fila(0, 0)], 0.0, causa="timeout_plazo",
                       crudo=b"[0.3, -0.2")
        self.reg.cerrar()
        falla = [e for e in eventos(self.ruta) if e["tipo"] == "consulta_fallida"]
        self.assertEqual(len(falla), 1)
        self.assertEqual(falla[0]["causa_parseo"], "json_invalido")
        self.assertEqual(falla[0]["consulta"]["crudo"], "[0.3, -0.2")
        self.assertEqual(len(falla[0]["agentes"]), 2)

    def test_tope_por_tipo_y_agente(self) -> None:
        reg = RegistroDiagnosticoPoses(self.tmp / "tope.jsonl", [1], [1],
                                       max_eventos_por_clave=2, imprimir=_mudo)
        for k in range(5):
            reg.registrar_evento("prueba", k=k)
        reg.cerrar()
        ev = eventos(self.tmp / "tope.jsonl")
        self.assertEqual(sum(e["tipo"] == "prueba" for e in ev), 2)
        self.assertEqual(reg.omitidos, 3)
        self.assertEqual(ev[-1]["eventos_por_tipo"]["prueba"], 5)

    def test_nunca_pisa_un_archivo(self) -> None:
        with self.assertRaises(FileExistsError):
            RegistroDiagnosticoPoses(self.ruta, [1, 5], [1, 5], imprimir=_mudo)

    def test_un_error_interno_no_sube(self) -> None:
        self.reg.registrar_fila(0, "basura", True, "", None, 0.0)  # type: ignore
        self.assertEqual(self.reg.errores_internos, 1)
        self.reg.cerrar()
        self.assertEqual(eventos(self.ruta)[-1]["errores_internos"], 1)

    def test_con_umbral_dos_una_repeticion_suelta_solo_se_cuenta(self) -> None:
        """
        Revisión del autor (2026-09-24): con el umbral del registro alineado
        al de la alarma (2 a 20 Hz), una retención de UNA repetición no es
        evento —existen en toda el área y agotarían el tope—: se cuenta, por
        agente y por franja de distancia a la pared.
        """
        reg = RegistroDiagnosticoPoses(self.tmp / "u2.jsonl", [1, 5], [1, 5],
                                       imprimir=_mudo,
                                       repeticiones_para_evento=2)
        b0 = fila(0.30, -0.40)            # entorno (1.8, 1.1): 1.1 m de pared
        self._consulta([fila(-0.50, 0.20), b0], 0.0, reg=reg)
        self._consulta([fila(-0.49, 0.20), b0], 0.05, reg=reg)
        self._consulta([fila(-0.48, 0.20), fila(0.31, -0.40)], 0.10, reg=reg)
        reg.cerrar()
        ev = eventos(self.tmp / "u2.jsonl")
        tipos = [e["tipo"] for e in ev]
        self.assertNotIn("repeticion_inicio", tipos)
        self.assertNotIn("repeticion_fin", tipos)
        self.assertEqual(ev[-1]["retenciones_cortas_por_agente"], {"1": 1})
        self.assertEqual(ev[-1]["retenciones_cortas_por_franja_d_pared_m"],
                         {">=0.60": 1})
        self.assertEqual(ev[0]["repeticiones_para_evento"], 2)

    def test_con_umbral_dos_el_evento_trae_las_tres_respuestas(self) -> None:
        """
        Al llegar al umbral, el evento trae la respuesta actual, la de la
        PRIMERA repetición y la que trajo el valor por primera vez.
        """
        reg = RegistroDiagnosticoPoses(self.tmp / "u2b.jsonl", [1, 5], [1, 5],
                                       imprimir=_mudo,
                                       repeticiones_para_evento=2)
        b0 = fila(0.30, -0.40)
        self._consulta([fila(-0.50, 0.20), b0], 0.0, reg=reg)     # seq 1
        self._consulta([fila(-0.49, 0.20), b0], 0.05, reg=reg)    # seq 2
        self._consulta([fila(-0.48, 0.20), b0], 0.10, reg=reg)    # seq 3
        self._consulta([fila(-0.47, 0.20), fila(0.31, -0.40)], 0.15, reg=reg)
        reg.cerrar()
        ev = eventos(self.tmp / "u2b.jsonl")
        ini = [e for e in ev if e["tipo"] == "repeticion_inicio"]
        self.assertEqual(len(ini), 1)
        self.assertEqual(ini[0]["repeticiones"], 2)
        self.assertEqual(ini[0]["consulta"]["seq"], 3)
        self.assertEqual(ini[0]["consulta_primera_repeticion"]["seq"], 2)
        self.assertEqual(ini[0]["consulta_que_trajo_el_valor"]["seq"], 1)
        self.assertAlmostEqual(ini[0]["duracion_valor_retenido_s"], 0.10)
        fin = [e for e in ev if e["tipo"] == "repeticion_fin"]
        self.assertEqual([e["repeticiones"] for e in fin], [2])
        self.assertEqual(ev[-1]["retenciones_cortas_por_agente"], {})

    def test_cerrar_es_idempotente_y_despues_no_escribe(self) -> None:
        self.reg.cerrar()
        self.reg.cerrar()
        self.reg.registrar_evento("tarde")
        ev = eventos(self.ruta)
        self.assertEqual([e["tipo"] for e in ev], ["inicio", "resumen"])
        self.assertEqual(sum(s.startswith("[diag]") for s in self.salida), 2)


# =============================================================================
# 3. LA FUENTE REAL CONTRA UN SERVIDOR GUIONADO
# =============================================================================

def _guion(n: int, _pld: List[int]) -> Optional[bytes]:
    """
    Siete respuestas que recorren los casos de la auditoría:
      1 normal · 2 el agente 1 repite bit a bit · 3 respuesta que no es lista
      · 4 placeholder del agente 1 · 5 agente 0 en milímetros (fuera de
      rango) · 6 normal, y el servidor empuja bytes no pedidos · 7 normal.
    """
    b0 = fila(0.30, -0.40, 1.0)
    if n == 1:
        return respuesta(fila(-0.50, 0.20, 0.1), b0)
    if n == 2:
        return respuesta(fila(-0.49, 0.20, 0.1), b0)
    if n == 3:
        return b'{"err":"mocap busy"}'
    if n == 4:
        return respuesta(fila(-0.48, 0.20, 0.1), PLACEHOLDER)
    if n == 5:
        return respuesta(fila(-470.0, 200.0, 0.1), fila(0.31, -0.40, 1.0))
    return respuesta(fila(-0.47 + 0.01 * (n - 6), 0.20, 0.1),
                     fila(0.32 + 0.01 * (n - 6), -0.40, 1.0))


class PruebaApagadoNoCambiaNada(unittest.TestCase):
    """
    La promesa central: con el registro apagado la fuente nueva hace
    exactamente lo mismo que la original, y encendido también (sólo mira).
    """

    N_CONSULTAS = 7

    def _correr(self, clase_fuente: Any, con_registro: bool,
                tmp: Path) -> Dict[str, Any]:
        with ConfigAislada(), ServidorGuionado(
                _guion, empujar_tras={6: b"[9.9]"}) as srv:
            _dos_agentes(srv.puerto)
            cfg.TIMEOUT_POSES_S = 0.2
            fuente = clase_fuente(2)
            reg = None
            if con_registro:
                reg = RegistroDiagnosticoPoses(tmp / "equivalencia.jsonl",
                                               [1, 5], [1, 5], imprimir=_mudo)
                fuente.activar_diagnostico(reg)
            with contextlib.redirect_stdout(io.StringIO()):
                fuente.conectar()
            consola = io.StringIO()
            salidas = []
            with contextlib.redirect_stdout(consola):
                for _ in range(self.N_CONSULTAS):
                    salidas.append(fuente.leer_poses_ya())
                    time.sleep(0.05)   # que lo empujado llegue antes del vaciado
            with contextlib.redirect_stdout(io.StringIO()):
                fuente.cerrar()
            if reg is not None:
                reg.cerrar()
            return {
                "salidas": salidas,
                "consola": consola.getvalue(),
                "contadores": (fuente.consultas, fuente.fallos_consulta,
                               dict(fuente.rechazos_pose),
                               fuente.bytes_descartados,
                               fuente.consultas_con_descarte,
                               len(fuente._latencias)),
                "peticiones": list(srv.peticiones),
            }

    def _iguales(self, a: Dict[str, Any], b: Dict[str, Any]) -> None:
        self.assertEqual(a["contadores"], b["contadores"])
        self.assertEqual(a["peticiones"], b["peticiones"])
        self.assertEqual(len(a["salidas"]), len(b["salidas"]))
        for sa, sb in zip(a["salidas"], b["salidas"]):
            self.assertEqual(sorted(sa), sorted(sb))
            for k in sa:
                np.testing.assert_array_equal(sa[k], sb[k])

    def test_apagado_es_igual_al_original(self) -> None:
        """
        Contra la fuente ORIGINAL, la del respaldo previo al registro. Si el
        respaldo no está, la prueba se SALTEA a la vista, con su motivo: no
        pasa en verde en silencio (revisión del autor, 2026-09-24), porque
        esta comparación es la que sostiene "apagado no cambia nada".
        """
        try:
            original = importlib.import_module(
                "adaptadores_robotat_respaldo_20260924_preDiag")
        except ImportError:
            self.skipTest("falta adaptadores_robotat_respaldo_20260924_"
                          "preDiag.py: sin él no hay comparación contra la "
                          "fuente original")
        tmp = Path(tempfile.mkdtemp(prefix="diag_orig_"))
        try:
            self._iguales(self._correr(FuentePosesRobotat, False, tmp),
                          self._correr(original.FuentePosesRobotat, False,
                                       tmp))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_apagado_y_encendido_dan_lo_mismo(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="diag_eq_"))
        try:
            apagado = self._correr(FuentePosesRobotat, False, tmp)
            encendido = self._correr(FuentePosesRobotat, True, tmp)
            self._iguales(apagado, encendido)
            # el guion ejercita lo que tiene que ejercitar
            self.assertEqual(apagado["contadores"][1], 1)          # 1 fallida
            self.assertEqual(apagado["contadores"][2],
                             {"marcador": 1, "x": 1})              # 2 rechazos
            self.assertEqual(apagado["contadores"][3], 5)          # "[9.9]"
            # y la fuente no escribe nada en consola, encendida o no
            self.assertEqual(encendido["consola"], "")
            self.assertEqual(apagado["consola"], "")

            ev = eventos(tmp / "equivalencia.jsonl")
            tipos = [e["tipo"] for e in ev]
            self.assertEqual(tipos[0], "inicio")
            self.assertEqual(tipos[-1], "resumen")
            self.assertIn("conexion", tipos)
            ini = [e for e in ev if e["tipo"] == "repeticion_inicio"]
            self.assertEqual([(e["agente"], e["consulta"]["seq"]) for e in ini],
                             [(1, 2)])
            falla = [e for e in ev if e["tipo"] == "consulta_fallida"]
            self.assertEqual(len(falla), 1)
            self.assertEqual(falla[0]["causa"], "timeout_socket")
            self.assertEqual(falla[0]["causa_parseo"], "no_es_lista")
            self.assertEqual(falla[0]["consulta"]["crudo"],
                             '{"err":"mocap busy"}')
            rechazos = {(e["agente"], e["diagnostico"]["primera_falla"])
                        for e in ev if e["tipo"] == "pose_rechazada"}
            self.assertEqual(rechazos, {(1, "placeholder"), (0, "rango_x")})
            no_pedidos = [e for e in ev if e["tipo"] == "datos_no_pedidos"]
            self.assertEqual(len(no_pedidos), 1)
            self.assertEqual(no_pedidos[0]["consulta"]["descartado_antes"],
                             "[9.9]")
            fines = [e for e in ev if e["tipo"] == "repeticion_fin"]
            self.assertEqual([e["agente"] for e in fines], [1])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# =============================================================================
# 4. EL SIMULADOR: FALLOS NUEVOS, Y SIN CAMBIOS POR DEFECTO
# =============================================================================

class PruebaSimuladorPorDefectoIgualAlOriginal(unittest.TestCase):
    """Con los fallos nuevos apagados, las respuestas son byte a byte las de antes."""

    def test_respuestas_identicas(self) -> None:
        try:
            viejo = importlib.import_module(
                "simulador_robotat_respaldo_20260924_preDiag")
        except ImportError:
            self.skipTest("no está el respaldo del simulador")
        import simulador_robotat as nuevo
        configuraciones = [
            {},
            {"marcadores_perdidos": {5}, "modo_marcador_perdido": "ceros"},
            {"marcadores_perdidos": {5}, "modo_marcador_perdido": "nan"},
            {"marcadores_perdidos": {5}, "modo_marcador_perdido": "faltante"},
            {"unidades_milimetros": True},
            {"prob_respuesta_malformada": 0.5, "semilla": 3},
        ]
        poses = {1: (-0.5, 0.2, 0.3), 5: (0.4, -0.1, 1.2)}
        for conf in configuraciones:
            with self.subTest(conf=conf):
                a = viejo.SimuladorRobotat({1: 1, 5: 5}, poses,
                                           viejo.FallasSimulador(**conf))
                b = nuevo.SimuladorRobotat({1: 1, 5: 5}, poses,
                                           nuevo.FallasSimulador(**conf))
                for _ in range(20):
                    self.assertEqual(a._respuesta([1, 5, 7]),
                                     b._respuesta([1, 5, 7]))


class PruebaZonaSinCaptura(unittest.TestCase):
    """
    Un robot que entra a la zona sin captura queda congelado bit a bit en la
    última pose publicada, como el servidor real; el otro sigue vivo en la
    MISMA respuesta. Es la firma de los 15 eventos de la auditoría, y el
    registro tiene que capturarla en la primera repetición.
    """

    def test_captura_la_firma_de_la_auditoria(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="diag_zona_"))
        pp, pb = puerto_libre(), puerto_libre()
        fallas = FallasSimulador(modo_marcador_perdido="congelado",
                                 zona_sin_captura=(1.0, 2.0, -1.0, 1.0),
                                 ruido_pos_m=0.0005)
        sim = SimuladorRobotat({1: 1, 5: 5},
                               {1: (-0.5, 0.2, 0.0), 5: (0.5, -0.3, 1.0)},
                               fallas, puerto_poses=pp, puerto_base=pb)
        try:
            with ConfigAislada():
                sim.iniciar()
                _dos_agentes(pp, pb)
                fuente = FuentePosesRobotat(2)
                reg = RegistroDiagnosticoPoses(tmp / "zona.jsonl", [1, 5],
                                               [1, 5], imprimir=_mudo)
                fuente.activar_diagnostico(reg)
                with contextlib.redirect_stdout(io.StringIO()):
                    fuente.conectar()

                def leer(n: int) -> None:
                    for _ in range(n):
                        fuente.leer_poses_ya()
                        time.sleep(0.02)

                leer(5)                                    # los dos vivos
                with sim._lock:
                    sim.robots[1].x = 1.5                  # entra a la zona
                leer(5)
                with sim._lock:
                    sim.robots[1].x = 0.2                  # sale
                leer(3)
                with contextlib.redirect_stdout(io.StringIO()):
                    fuente.cerrar()
                reg.cerrar()
            ev = eventos(tmp / "zona.jsonl")
            ini = [e for e in ev if e["tipo"] == "repeticion_inicio"]
            self.assertEqual([e["agente"] for e in ini], [0])
            self.assertEqual(ini[0]["filas_iguales_a_la_respuesta_anterior"],
                             [True, False])
            # los 7 números del marcador retenido son los mismos, byte a byte,
            # en la respuesta que lo trajo y en la que lo repite
            antes = json.loads(ini[0]["consulta_que_trajo_el_valor"]["crudo"])[:7]
            ahora = json.loads(ini[0]["consulta"]["crudo"])[:7]
            self.assertEqual(antes, ahora)
            fin = [e for e in ev if e["tipo"] == "repeticion_fin"]
            self.assertEqual(len(fin), 1)
            self.assertGreaterEqual(fin[0]["repeticiones"], 4)
            self.assertAlmostEqual(fin[0]["salto"]["desplazamiento_m"], 0.7,
                                   delta=0.01)
            self.assertNotIn("salto_de_pose", [e["tipo"] for e in ev])
        finally:
            sim.detener()
            shutil.rmtree(tmp, ignore_errors=True)


# =============================================================================
# 5. LA SONDA
# =============================================================================

POSICIONES_GUION: Dict[int, tuple] = {1: (-0.5, 0.2), 5: (0.5, -0.3)}


def _guion_vivo(atrasado: bool) -> Callable[[int, List[int]], bytes]:
    """
    Respuestas "vivas" (cambian un poco en cada consulta). Con `atrasado`,
    la petición n recibe la respuesta armada para la petición n−1: el
    desfase de búfer de H5, visto desde el servidor.
    """
    previa: Dict[str, Any] = {}

    def responder(n: int, pld: List[int]) -> bytes:
        filas_ = [fila(POSICIONES_GUION[m][0] + 1e-4 * n,
                       POSICIONES_GUION[m][1], 0.2) for m in pld]
        actual = respuesta(*filas_)
        if not atrasado:
            return actual
        salida = previa.get("r", actual)
        previa["r"] = actual
        return salida
    return responder


class PruebaSonda(unittest.TestCase):
    """`correr_sonda` y `--alternar-orden`."""

    def _correr(self, responder: Callable[[int, List[int]], bytes],
                alternar: bool, duracion_s: float = 0.6) -> Dict[str, Any]:
        tmp = Path(tempfile.mkdtemp(prefix="sonda_test_"))
        try:
            with ConfigAislada(), ServidorGuionado(responder) as srv:
                _dos_agentes(srv.puerto)
                fuente = sonda.FuenteSonda(2, alternar_orden=alternar)
                # El registro de la sonda REAL: umbral = alarma, tope 1000.
                with contextlib.redirect_stdout(io.StringIO()):
                    reg = sonda.crear_registro(tmp / "s.jsonl", [1, 5],
                                               [1, 5], alarma=2)
                fuente.activar_diagnostico(reg)
                with contextlib.redirect_stdout(io.StringIO()):
                    fuente.conectar()
                csv_ = io.StringIO()
                lineas: List[str] = []
                res = sonda.correr_sonda(fuente, reg, csv_, duracion_s, hz=20,
                                         alarma=2, imprimir=lineas.append)
                with contextlib.redirect_stdout(io.StringIO()):
                    fuente.cerrar()
                    reg.cerrar()
                return {"res": res, "csv": csv_.getvalue(), "lineas": lineas,
                        "tipos": [e["tipo"] for e in eventos(tmp / "s.jsonl")],
                        "peticiones": list(srv.peticiones)}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_alternando_con_servidor_sano_no_hay_saltos(self) -> None:
        r = self._correr(_guion_vivo(atrasado=False), alternar=True)
        self.assertGreaterEqual(r["res"]["consultas"], 6)
        self.assertEqual(r["res"]["saltos"], 0)
        self.assertNotIn("salto_de_pose", r["tipos"])
        self.assertIn([5, 1], r["peticiones"])       # sí pidió en orden inverso
        self.assertIn("invertido", r["csv"])
        self.assertEqual(sum(v for v in r["res"]["alarmas_por_robot"].values()), 0)

    def test_alternando_detecta_la_respuesta_de_la_peticion_anterior(self) -> None:
        r = self._correr(_guion_vivo(atrasado=True), alternar=True)
        self.assertGreater(r["res"]["saltos"], 0)
        self.assertIn("salto_de_pose", r["tipos"])
        self.assertTrue(any("SALTO DE POSE" in l for l in r["lineas"]))

    def test_sin_alternar_el_desfase_es_invisible(self) -> None:
        """Por qué la sesión no puede verlo: sus peticiones son todas iguales."""
        r = self._correr(_guion_vivo(atrasado=True), alternar=False)
        self.assertEqual(r["res"]["saltos"], 0)
        self.assertNotIn("salto_de_pose", r["tipos"])

    def test_alarma_y_recuperacion_de_un_marcador_congelado(self) -> None:
        congelada = fila(0.5, -0.3, 1.0)

        def responder(n: int, pld: List[int]) -> bytes:
            a = fila(-0.5 + 1e-4 * n, 0.2, 0.2)
            b = congelada if 3 <= n <= 8 else fila(0.5 + 1e-4 * n, -0.3, 1.0)
            por_marcador = {1: a, 5: b}
            return respuesta(*[por_marcador[m] for m in pld])

        r = self._correr(responder, alternar=False, duracion_s=0.7)
        self.assertEqual(r["res"]["alarmas_por_robot"], {1: 0, 5: 1})
        self.assertTrue(any("robot 5 REPITE" in l for l in r["lineas"]))
        self.assertTrue(any("robot 5 vivo otra vez" in l for l in r["lineas"]))
        self.assertIn("repeticion_inicio", r["tipos"])

    def test_el_registro_de_la_sonda_usa_el_umbral_de_la_alarma(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="sonda_umbral_"))
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                reg = sonda.crear_registro(tmp / "r.jsonl", [1, 5], [1, 5],
                                           alarma=3)
                reg.cerrar()
            ini = eventos(tmp / "r.jsonl")[0]
            self.assertEqual(ini["repeticiones_para_evento"], 3)
            self.assertEqual(ini["max_eventos_por_clave_efectivo"],
                             sonda.MAX_EVENTOS_SONDA)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_las_rutas_de_salida_no_pisan(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="sonda_rutas_"))
        try:
            from datetime import datetime
            ahora = datetime(2026, 9, 24, 12, 0, 0)
            a_csv, a_jsonl = sonda.rutas_salida(ahora, tmp)
            a_csv.write_text("x")
            b_csv, b_jsonl = sonda.rutas_salida(ahora, tmp)
            self.assertNotEqual(a_csv, b_csv)
            self.assertTrue(b_csv.name.endswith("_02.csv"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# =============================================================================
# 6. LA BANDERA DE LA SESIÓN
# =============================================================================

class PruebaSesionConBandera(unittest.TestCase):
    """
    `sesion_evaluacion` contra el simulador, con y sin `DIAGNOSTICO_POSES`.
    Encendido: aparece el JSONL con inicio, fin de episodio y resumen (con
    los contadores de la fuente que antes se perdían), y la consola sólo
    gana las dos líneas del registro. Apagado: no aparece nada.
    """

    ROBOTS = (0, 1, 2)

    def setUp(self) -> None:
        self._cfg = ConfigAislada().__enter__()
        self.tmp = Path(tempfile.mkdtemp(prefix="diag_sesion_"))
        self._ruta_calib = calib.RUTA_CALIBRACION
        self._dir_salida = ses.DIR_SALIDA
        calib.RUTA_CALIBRACION = self.tmp / "calibracion_medida.json"
        ses.DIR_SALIDA = self.tmp / "resultados_sesion"
        pp, pb = puerto_libre(), puerto_libre()
        cfg.activar_simulador_local(puerto_poses=pp, puerto_base=pb)
        poses = {r: (-0.4 + 0.4 * k, 0.2, 0.0) for k, r in enumerate(self.ROBOTS)}
        self.sim = SimuladorRobotat({r: r + 1 for r in self.ROBOTS}, poses,
                                    None, puerto_poses=pp, puerto_base=pb)
        self.sim.iniciar()
        cfg.MAPEO_AGENTES = {
            i: cfg.AsignacionAgente(id_marcador=r + 1, id_robot=r)
            for i, r in enumerate(self.ROBOTS)}
        with contextlib.redirect_stdout(io.StringIO()):
            calib.guardar({
                "id_robot": self.ROBOTS[0], "id_marcador": self.ROBOTS[0] + 1,
                "escala_posicion": 1.0, "rotacion_marco_rad": 0.0,
                "traslacion_x_m": 1.5, "traslacion_y_m": 1.5,
                "offset_heading_rad": 0.0}, etapa="prueba")
            calib.aplicar_a_config()
        self.ctx = ses.Contexto(sesion="prueba", id_robot=self.ROBOTS[0],
                                marcador=self.ROBOTS[0] + 1,
                                preguntar=lambda _m: "")

    def tearDown(self) -> None:
        try:
            self.ctx.cerrar()
        except Exception:                                  # noqa: BLE001
            pass
        self.sim.detener()
        calib.RUTA_CALIBRACION = self._ruta_calib
        ses.DIR_SALIDA = self._dir_salida
        self._cfg.__exit__()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _reponer(self) -> None:
        """Los robots vuelven a su arranque: cada corrida parte igual."""
        with self.sim._lock:
            for k, r in enumerate(self.ROBOTS):
                est = self.sim.robots[r]
                est.x, est.y, est.yaw = -0.4 + 0.4 * k, 0.2, 0.0
                est.rpm_izq = est.rpm_der = 0.0

    def _sesion(self) -> str:
        self._reponer()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ses.sesion_evaluacion(
                self.ctx, n_agentes=len(self.ROBOTS), factor=0.40,
                episodios_objetivo=1, episodios_minimo=1, decisiones=15,
                intentos_max=1, rpm_aborto=400.0)
        return buf.getvalue()

    def test_encendida_deja_el_registro_y_apagada_no(self) -> None:
        cfg.DIAGNOSTICO_POSES = False
        self._sesion()
        salida = ses.DIR_SALIDA
        self.assertEqual(list(salida.glob("*.jsonl")), [])
        csv_apagada = sorted(p.name for p in salida.glob("*.csv"))

        cfg.DIAGNOSTICO_POSES = True
        consola = self._sesion()
        jsonl = list(salida.glob("*diagnostico-poses*.jsonl"))
        self.assertEqual(len(jsonl), 1, consola)
        ev = eventos(jsonl[0])
        self.assertEqual(ev[0]["tipo"], "inicio")
        self.assertEqual(ev[0]["sesion"], "evaluacion")
        self.assertIn("fin_episodio", [e["tipo"] for e in ev])
        self.assertEqual(ev[-1]["tipo"], "resumen")
        self.assertTrue(any("[poses] poses rechazadas" in s
                            for s in ev[-1]["resumen_fuente"]))
        lineas_diag = [l for l in consola.splitlines() if l.startswith("[diag]")]
        self.assertEqual(len(lineas_diag), 2, consola)
        # los CSV de la sesión siguen saliendo igual (con sufijo _02)
        csv_encendida = sorted(p.name for p in salida.glob("*.csv"))
        self.assertEqual(len(csv_encendida), 2 * len(csv_apagada))


if __name__ == "__main__":
    unittest.main(verbosity=2)
