"""
test_integracion_robotat.py
===========================
Pruebas del puente completo contra `simulador_robotat`: los adaptadores
hablan por sockets reales, con el formato real, y se verifica el
comportamiento observable — incluido el comportamiento bajo fallo.

    python test_integracion_robotat.py

Lo que estas pruebas SÍ demuestran: que el cliente pide, interpreta, manda,
frena y se recupera correctamente frente a un servidor que respeta el formato
relevado de `robotat/*.m`.

Lo que NO demuestran: que ese formato relevado sea el que habla el servidor
real, ni nada sobre el hardware. Ver la sección "qué queda sin probar" del
README.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import copy
import math
import threading
import time
import unittest
from typing import Tuple

import numpy as np

import config_robotat as cfg
from adaptadores_robotat import (
    CanalActuacionRobotat,
    EntornoEjecucionRobotat,
    FuentePosesRobotat,
    revisar_poses_iniciales,
)
from interfaces import CanalActuacion, EntornoEjecucion, FuentePoses
from protocolo_robotat import rad_s_a_rpm
from simulador_robotat import (
    FallasSimulador,
    SimuladorRobotat,
    simulador_por_defecto,
)
from lanzar_robotat import chequeo_de_arranque, construir
from verificar_mapeo_ids import informe, verificar

N_AGENTES: int = 3

#: Marcador y robot del AGENTE 1, el que estas pruebas "pierden" o dejan
#: sordo. Se DERIVAN de `MAPEO_AGENTES` en vez de escribirse a mano: hasta
#: el 2026-08-29 estaban fijos en 2, porque el mapeo era 1-5 y el agente 1
#: era el robot 2. Cuando el mapeo pasó al enjambre real —IDs no contiguos
#: 1, 6, 9, 10, 12— ese 2 dejó de pertenecer a ningún agente y cinco
#: pruebas empezaron a fallar sin que nada estuviera roto. Un número
#: duplicado de la configuración se desincroniza; uno derivado, no.
MARCADOR_AGENTE_1: int = cfg.MAPEO_AGENTES[1].id_marcador
ROBOT_AGENTE_1:    int = cfg.MAPEO_AGENTES[1].id_robot


def esperar_a(condicion, plazo_s: float = 1.0) -> bool:
    """
    Sondea `condicion()` hasta que se cumpla o venza el plazo.

    `sendall` retorna cuando el byte salió del socket, NO cuando el hilo del
    robot lo consumió. Comprobar el estado del simulador justo después de
    enviar es una carrera: acá se espera al efecto en vez de suponer que ya
    ocurrió.
    """
    limite = time.perf_counter() + plazo_s
    while time.perf_counter() < limite:
        if condicion():
            return True
        time.sleep(0.005)
    return bool(condicion())


class BaseIntegracion(unittest.TestCase):
    """Levanta simulador + adaptadores conectados, y los baja al terminar."""

    fallas: FallasSimulador = FallasSimulador()
    conectar_canal: bool = True
    # La mayoría de estas pruebas ejercitan el PROTOCOLO (leer_poses() de a
    # una, esperando que cada llamada sea una consulta real) — no el ritmo
    # de consulta del coordinador. Con el límite de tasa activo por
    # defecto (10 Hz, ver config_robotat.HZ_CONSULTA_POSES), la mayoría de
    # esas llamadas volverían `[]` sin tocar la red. Estas pruebas declaran
    # explícitamente que no les interesa el límite, subiéndolo a un valor
    # que en la práctica lo desactiva (`_intervalo_ticks` calculado da 1).
    # `PruebaTasaDeConsulta` es la que sí prueba el límite, con el default.
    hz_consulta_poses: float = 10_000.0

    def setUp(self) -> None:
        cfg.activar_simulador_local()
        self._hz_previo = cfg.HZ_CONSULTA_POSES
        cfg.HZ_CONSULTA_POSES = self.hz_consulta_poses
        self.tick = 0
        # COPIA, no la instancia de clase. `fallas` es un atributo de clase y
        # `FallasSimulador` es mutable: una prueba que le toque un campo al
        # simulador estaría modificando el objeto compartido por TODAS las
        # clases que usan el default, y el efecto aparecería en pruebas
        # posteriores sin relación aparente (pasó: dejar sin marcador al
        # agente 2 acá hacía fallar `PruebaPoseVencida` mucho después).
        self.sim = simulador_por_defecto(N_AGENTES, copy.deepcopy(self.fallas))
        self.sim.iniciar()
        self.fuente = FuentePosesRobotat(N_AGENTES, lambda: self.tick)
        self.fuente.conectar()
        self.canal = CanalActuacionRobotat(N_AGENTES, self.fuente)
        if self.conectar_canal:
            self.canal.conectar()
        self.entorno = EntornoEjecucionRobotat(self.fuente, self.canal, 10)
        self.poses_iniciales = {
            i: self.sim.pose_de_robot(cfg.MAPEO_AGENTES[i].id_robot)
            for i in range(N_AGENTES)
        }

    def tearDown(self) -> None:
        cfg.HZ_CONSULTA_POSES = self._hz_previo
        try:
            self.canal.cerrar()
        except Exception:                                   # noqa: BLE001
            pass
        self.fuente.cerrar()
        self.sim.detener()
        cfg.SIMULADOR_ACTIVO = False

    def avanzar_real(self, segundos: float) -> None:
        """Deja correr la física del simulador."""
        time.sleep(segundos)

    def esperar(self, condicion, plazo_s: float = 1.0) -> bool:
        """Ver `esperar_a`."""
        return esperar_a(condicion, plazo_s)

    def leer_pose_env(self, agente: int) -> np.ndarray:
        """Última pose del agente en marco del env, o falla si no llegó."""
        for _ in range(20):
            for i, medida in self.fuente.leer_poses():
                if i == agente:
                    return medida.pose
            time.sleep(0.01)
        self.fail(f"no llegó pose del agente {agente}")


# =============================================================================
# 1. LAZO CERRADO — LA PRUEBA DE ORDEN DE RUEDAS DE PUNTA A PUNTA
# =============================================================================

class PruebaLazoCerrado(BaseIntegracion):
    """
    Cierra el lazo por los DOS protocolos: se manda un giro por CBOR y se lee
    el resultado por JSON. Si el orden de ruedas estuviera invertido en
    cualquier punto de la cadena, el robot giraría al revés y estas pruebas
    lo verían en el signo de Δθ.
    """

    def test_giro_a_la_izquierda_aumenta_theta(self) -> None:
        th0 = float(self.leer_pose_env(0)[2])
        self.canal.enviar_acciones({0: (0.0, +2.0), 1: (0.0, 0.0),
                                    2: (0.0, 0.0)})
        self.avanzar_real(0.30)
        self.canal.enviar_acciones({i: (0.0, 0.0) for i in range(N_AGENTES)})
        th1 = float(self.leer_pose_env(0)[2])
        d = math.atan2(math.sin(th1 - th0), math.cos(th1 - th0))
        self.assertGreater(d, 0.1, f"ω>0 debe aumentar θ; Δθ = {d:.4f} rad")

    def test_giro_a_la_derecha_disminuye_theta(self) -> None:
        th0 = float(self.leer_pose_env(0)[2])
        self.canal.enviar_acciones({0: (0.0, -2.0), 1: (0.0, 0.0),
                                    2: (0.0, 0.0)})
        self.avanzar_real(0.30)
        self.canal.enviar_acciones({i: (0.0, 0.0) for i in range(N_AGENTES)})
        th1 = float(self.leer_pose_env(0)[2])
        d = math.atan2(math.sin(th1 - th0), math.cos(th1 - th0))
        self.assertLess(d, -0.1, f"ω<0 debe disminuir θ; Δθ = {d:.4f} rad")

    def test_avance_va_hacia_adelante(self) -> None:
        p0 = self.leer_pose_env(0).copy()
        self.canal.enviar_acciones({0: (0.20, 0.0), 1: (0.0, 0.0),
                                    2: (0.0, 0.0)})
        self.avanzar_real(0.30)
        self.canal.enviar_acciones({i: (0.0, 0.0) for i in range(N_AGENTES)})
        p1 = self.leer_pose_env(0)
        avance = ((p1[0] - p0[0]) * math.cos(p0[2])
                  + (p1[1] - p0[1]) * math.sin(p0[2]))
        # La rampa de arranque seguro está activa por defecto, así que el
        # desplazamiento esperado es el nominal por el factor. Lo que se
        # prueba acá es el SIGNO, no la magnitud: se exige la mitad de lo
        # esperado para no depender del instante exacto del muestreo.
        esperado = 0.20 * 0.30 * cfg.FACTOR_VELOCIDAD_ARRANQUE
        self.assertGreater(
            avance, esperado * 0.5,
            f"v>0 debe avanzar en +heading; avance = {avance:.4f} m "
            f"(esperado ≈ {esperado:.4f} m con la rampa activa)")

    def test_solo_se_mueve_el_agente_comandado(self) -> None:
        """Guardia contra un mapeo cruzado dentro del canal."""
        self.fuente.leer_poses()      # sin esto, el canal frena a todos
        self.canal.enviar_acciones({0: (0.20, 0.0), 1: (0.0, 0.0),
                                    2: (0.0, 0.0)})
        self.avanzar_real(0.20)
        self.canal.enviar_acciones({i: (0.0, 0.0) for i in range(N_AGENTES)})
        for i in range(N_AGENTES):
            id_robot = cfg.MAPEO_AGENTES[i].id_robot
            x, y, _ = self.sim.pose_de_robot(id_robot)
            x0, y0, _ = self.poses_iniciales[i]
            movido = math.hypot(x - x0, y - y0) > 0.01
            self.assertEqual(movido, i == 0,
                             f"agente {i}: movido={movido}, esperado={i == 0}")

    def test_sin_pose_no_se_mueve_nadie(self) -> None:
        """
        Contrapartida del anterior: si NUNCA llegó una pose, el canal no deja
        que ningún robot arranque. Es la primera línea de defensa contra
        conducir a ciegas.
        """
        self.assertEqual(sorted(self.fuente.agentes_vencidos()),
                         list(range(N_AGENTES)))
        self.canal.enviar_acciones({i: (0.25, 1.0) for i in range(N_AGENTES)})
        self.avanzar_real(0.15)
        for i in range(N_AGENTES):
            id_robot = cfg.MAPEO_AGENTES[i].id_robot
            self.assertEqual(self.sim.rpm_de_robot(id_robot), (0.0, 0.0))


# =============================================================================
# 2. CONFORMIDAD CON LAS INTERFACES
# =============================================================================

class PruebaConformidad(BaseIntegracion):

    def test_implementan_los_protocolos(self) -> None:
        self.assertIsInstance(self.fuente, FuentePoses)
        self.assertIsInstance(self.canal, CanalActuacion)
        self.assertIsInstance(self.entorno, EntornoEjecucion)

    def test_nombres(self) -> None:
        for obj in (self.fuente, self.canal, self.entorno):
            self.assertEqual(obj.nombre, "robotat")

    def test_reposicionar_lanza(self) -> None:
        """No hay teletransporte en el laboratorio: debe fallar RUIDOSAMENTE."""
        with self.assertRaises(NotImplementedError) as ctx:
            self.entorno.reposicionar({0: np.array([1.0, 1.0, 0.0])})
        self.assertIn("teletransporte", str(ctx.exception))

    def test_publicar_visualizacion_es_no_op(self) -> None:
        self.assertIsNone(
            self.entorno.publicar_visualizacion(np.zeros((3, 2)))
        )

    def test_avanzar_respeta_el_periodo(self) -> None:
        t0 = time.perf_counter()
        self.assertTrue(self.entorno.avanzar(10))     # 10 ticks × 10 ms
        transcurrido = time.perf_counter() - t0
        self.assertGreater(transcurrido, 0.08)
        self.assertLess(transcurrido, 0.30)


# =============================================================================
# 3. PÉRDIDA DE MARCADOR — LOS TRES MODOS PLAUSIBLES
# =============================================================================

class _BasePerdida(BaseIntegracion):
    """El agente 1 (marcador 2) queda sin pose; los otros dos siguen bien."""

    def _comprobar(self) -> None:
        vistos = set()
        for _ in range(10):
            for i, _m in self.fuente.leer_poses():
                vistos.add(i)
            time.sleep(0.01)
        self.assertNotIn(1, vistos, "el agente sin marcador NO debe dar pose")
        self.assertIn(1, self.fuente.agentes_faltantes())
        self.assertIn(1, self.fuente.agentes_vencidos())


class PruebaMarcadorEnCeros(_BasePerdida):
    fallas = FallasSimulador(marcadores_perdidos={MARCADOR_AGENTE_1},
                             modo_marcador_perdido="ceros")

    def test_se_descarta(self) -> None:
        self._comprobar()
        # los demás sí llegan
        self.assertNotIn(0, self.fuente.agentes_faltantes())
        self.assertNotIn(2, self.fuente.agentes_faltantes())


class PruebaMarcadorEnNaN(_BasePerdida):
    fallas = FallasSimulador(marcadores_perdidos={MARCADOR_AGENTE_1},
                             modo_marcador_perdido="nan")

    def test_se_descarta(self) -> None:
        self._comprobar()
        self.assertNotIn(0, self.fuente.agentes_faltantes())


class PruebaMarcadorAusente(_BasePerdida):
    """
    Fila ausente: la respuesta tiene 7·(N−1) valores. El cliente la descarta
    ENTERA —no puede saber a qué agente corresponde cada fila— y ningún
    agente recibe pose. Es el modo de fallo más severo de los tres, y por eso
    conviene saber cuál ocurre en el laboratorio (pregunta abierta al
    encargado del Robotat).
    """
    fallas = FallasSimulador(marcadores_perdidos={MARCADOR_AGENTE_1},
                             modo_marcador_perdido="faltante")

    def test_se_descarta_la_respuesta_entera(self) -> None:
        for _ in range(10):
            self.assertEqual(self.fuente.leer_poses(), [])
            time.sleep(0.01)
        self.assertEqual(self.fuente.agentes_faltantes(),
                         list(range(N_AGENTES)))


class PruebaRespuestaMalformada(BaseIntegracion):
    fallas = FallasSimulador(prob_respuesta_malformada=1.0)

    def test_no_rompe_y_cuenta_el_fallo(self) -> None:
        for _ in range(5):
            self.assertEqual(self.fuente.leer_poses(), [])
        self.assertGreaterEqual(self.fuente.fallos_consulta, 5)
        self.assertFalse(self.fuente.conexion_caida,
                         "una respuesta basura no es una conexión caída")


class PruebaUnidadesEnMilimetros(BaseIntegracion):
    """
    Si el servidor entregara milímetros y `ESCALA_POSICION` siguiera en 1.0,
    las poses caen fuera del rango del laboratorio y se rechazan TODAS. El
    sistema no arranca, en vez de conducir con posiciones 1000× mal.

    LÍMITE CONOCIDO de esta defensa: un robot en el origen es invariante de
    escala (0 mm = 0 m), y uno a menos de 5 mm del origen queda dentro del
    rango aun en milímetros. La detección por rango es una red de seguridad,
    no un sustituto de la calibración del README §C1.
    """
    fallas = FallasSimulador(unidades_milimetros=True)

    def test_se_rechazan_por_rango(self) -> None:
        for _ in range(5):
            self.fuente.leer_poses()
            time.sleep(0.01)
        self.assertEqual(self.fuente.agentes_faltantes(),
                         list(range(N_AGENTES)))
        self.assertTrue(self.fuente.rechazos_pose,
                        "debe registrar el motivo del rechazo")


# =============================================================================
# 4. CAÍDA DE LA CONEXIÓN DE POSES
# =============================================================================

class PruebaCaidaDePoses(BaseIntegracion):
    fallas = FallasSimulador(caer_poses_tras=3)

    def test_termina_el_lazo_y_frena(self) -> None:
        for _ in range(8):
            self.fuente.leer_poses()
        self.assertTrue(self.fuente.conexion_caida)
        self.assertFalse(self.entorno.avanzar(1),
                         "avanzar() debe pedir terminar si cayó la mocap")
        # el camino de parada de la Fase 1: finally/atexit → detener_todo
        self.canal.detener_todo()
        self.assertTrue(self.esperar(self.sim.todos_detenidos))


# =============================================================================
# 5. POSE VENCIDA → EL CANAL FRENA
# =============================================================================

class PruebaPoseVencida(BaseIntegracion):

    def test_frena_al_agente_sin_pose_fresca(self) -> None:
        self.fuente.leer_poses()                     # todos frescos
        self.assertEqual(self.fuente.agentes_vencidos(), [])
        self.canal.enviar_acciones({i: (0.2, 0.0) for i in range(N_AGENTES)})
        self.assertTrue(self.esperar(
            lambda: self.sim.rpm_de_robot(cfg.MAPEO_AGENTES[0].id_robot)
            != (0.0, 0.0)))

        time.sleep(cfg.ANTIGUEDAD_MAX_POSE_S + 0.05)  # se vencen
        self.assertEqual(sorted(self.fuente.agentes_vencidos()),
                         list(range(N_AGENTES)))
        self.canal.enviar_acciones({i: (0.2, 0.0) for i in range(N_AGENTES)})
        self.assertTrue(
            self.esperar(self.sim.todos_detenidos),
            "todo agente con pose vencida debe quedar quieto; rpm actuales: "
            f"{ {i: self.sim.rpm_de_robot(cfg.MAPEO_AGENTES[i].id_robot) for i in range(N_AGENTES)} }",
        )
        self.assertGreaterEqual(self.canal.frenados_por_pose_vieja, N_AGENTES)


# =============================================================================
# 6. DETENCIÓN — Y SUS LÍMITES
# =============================================================================

class PruebaDetencion(BaseIntegracion):

    def test_detiene_a_todos(self) -> None:
        self.fuente.leer_poses()
        self.canal.enviar_acciones({i: (0.2, 1.0) for i in range(N_AGENTES)})
        self.assertTrue(self.esperar(lambda: not self.sim.todos_detenidos()))
        self.canal.detener_todo()
        self.assertTrue(self.esperar(self.sim.todos_detenidos))

    def test_es_idempotente_y_no_lanza(self) -> None:
        for _ in range(3):
            self.canal.detener_todo()
        self.assertTrue(self.esperar(self.sim.todos_detenidos))


class PruebaDetencionConEnlaceCaido(BaseIntegracion):
    """
    ⚠ EL HALLAZGO QUE HAY QUE TENER PRESENTE EN EL LABORATORIO.

    El robot 1 corta el enlace tras 2 comandos, conservando su última orden
    (marcha), y queda INALCANZABLE: ya no acepta conexiones. `detener_todo()`
    frena a los demás, NO puede frenar a ése, y lo informa nominalmente —
    pero el robot SIGUE ANDANDO. La parada por software no es una parada de
    emergencia; alguien tiene que poder cortar la alimentación.

    Desde el 2026-09-11 el canal reconecta un enlace caído, así que esta
    lección vale para el robot que NO vuelve (`caidos_no_reaceptan`). El que
    sí vuelve está en `PruebaDetencionConEnlaceRecuperable`.
    """
    # Clave por ID DE ROBOT, no de agente: con el mapeo agente→robot
    # corregido (robot = agente 1..N, ya no 0..N-1), hardcodear "1" acá
    # apuntaba al robot del agente 0, no del agente 1 como pretendía la
    # prueba. Se deriva de cfg.MAPEO_AGENTES, igual que el resto de la
    # prueba más abajo.
    fallas = FallasSimulador(
        robots_que_caen_tras={cfg.MAPEO_AGENTES[1].id_robot: 2},
        caidos_no_reaceptan=True,
    )

    def test_frena_al_resto_informa_el_fallo_y_el_caido_sigue(self) -> None:
        self.fuente.leer_poses()
        for _ in range(4):
            self.canal.enviar_acciones({i: (0.2, 0.0)
                                        for i in range(N_AGENTES)})
            time.sleep(0.05)

        self.canal.detener_todo()                   # no debe lanzar

        id_caido = cfg.MAPEO_AGENTES[1].id_robot
        otros = [cfg.MAPEO_AGENTES[i].id_robot
                 for i in range(N_AGENTES)
                 if cfg.MAPEO_AGENTES[i].id_robot != id_caido]
        self.assertTrue(self.esperar(
            lambda: all(self.sim.rpm_de_robot(r) == (0.0, 0.0) for r in otros)
        ))
        for i in range(N_AGENTES):
            id_robot = cfg.MAPEO_AGENTES[i].id_robot
            izq, der = self.sim.rpm_de_robot(id_robot)
            if id_robot == id_caido:
                self.assertNotEqual(
                    (izq, der), (0.0, 0.0),
                    "el robot con el enlace caído CONSERVA su última orden: "
                    "la parada por software no lo alcanza",
                )
            else:
                self.assertEqual((izq, der), (0.0, 0.0),
                                 f"el robot {id_robot} sí debe frenar")

        self.assertIn(1, self.canal.envios_fallidos,
                      "el fallo debe quedar registrado por agente")
        self.assertFalse(self.sim.todos_detenidos())


class PruebaDetencionConEnlaceRecuperable(BaseIntegracion):
    """
    ⚠ REGRESIÓN (2026-09-11). El robot corta el enlace pero SIGUE escuchando,
    como el robot 3 real: cerró el socket con WinError 10054 y aceptaba
    conexiones nuevas. Sin reconexión, el canal lo daba por perdido y el
    robot no recibía ni una orden más —tampoco la de frenar—. Con
    reconexión, `detener_todo()` lo alcanza.
    """
    fallas = FallasSimulador(
        robots_que_caen_tras={cfg.MAPEO_AGENTES[1].id_robot: 2},
    )

    def test_el_caido_se_reconecta_y_frena(self) -> None:
        self.fuente.leer_poses()
        for _ in range(4):
            self.canal.enviar_acciones({i: (0.2, 0.0)
                                        for i in range(N_AGENTES)})
            time.sleep(0.05)

        self.canal.detener_todo()

        self.assertTrue(self.esperar(lambda: self.sim.todos_detenidos()),
                        "con el enlace recuperado, la parada alcanza a todos")
        self.assertIn(1, self.canal.reconexiones,
                      "la reconexión debe quedar registrada por agente")
        self.assertIn(1, self.canal.envios_fallidos,
                      "el fallo previo también")


class PruebaRobotSordo(BaseIntegracion):
    """Un robot que ni siquiera acepta la conexión: `conectar()` debe fallar."""
    conectar_canal = False
    fallas = FallasSimulador(robots_sordos={ROBOT_AGENTE_1})

    def test_conectar_falla_ruidosamente(self) -> None:
        with self.assertRaises(OSError):
            self.canal.conectar()


# =============================================================================
# 7. LATENCIA
# =============================================================================

class PruebaLatencia(BaseIntegracion):
    fallas = FallasSimulador(latencia_poses_s=0.020,
                             jitter_latencia_s=0.010, semilla=7)

    def test_se_mide_y_se_reporta(self) -> None:
        for _ in range(15):
            self.fuente.leer_poses()
        lat = np.asarray(self.fuente._latencias, dtype=np.float64)
        self.assertGreater(lat.size, 10)
        self.assertGreater(lat.mean(), 0.015)
        self.assertLess(lat.mean(), 0.10)
        print(f"\n    [latencia inyectada 20±10 ms] medida: "
              f"p50 {np.percentile(lat, 50)*1e3:.1f} ms · "
              f"p95 {np.percentile(lat, 95)*1e3:.1f} ms")
        self.assertTrue(any("latencia" in l for l in self.fuente.resumen()))


# =============================================================================
# 7b. TASA DE CONSULTA DE POSES — DECISIÓN 2026-08-22
# =============================================================================
# `leer_poses()` se sigue llamando una vez por TICK (eso no cambió: es
# `_avanzar`, compartido con Webots), pero sólo hace un round-trip real
# cada `_intervalo_ticks` llamadas. Estas pruebas SÍ quieren el límite de
# tasa activo, con el default de producción — a diferencia de casi todas
# las de arriba, que lo desactivan por ser pruebas de protocolo.

class PruebaTasaDeConsulta(BaseIntegracion):
    hz_consulta_poses = cfg.HZ_CONSULTA_POSES   # el default real, sin tocar

    def test_omite_la_mayoria_de_las_llamadas(self) -> None:
        # timestep=10 ms, HZ=10 ⇒ intervalo_ticks=10: 1 consulta real cada
        # 10 llamadas, empezando por la primera (fijar_intervalo_consulta
        # fuerza una consulta inmediata al conectar).
        for _ in range(25):
            self.fuente.leer_poses()
        self.assertEqual(self.fuente.consultas, 3)          # ticks 1, 11, 21
        self.assertEqual(self.fuente.consultas_omitidas, 22)

    def test_reiniciar_fuerza_consulta_inmediata(self) -> None:
        self.fuente.leer_poses()                 # consume el disparo inicial
        for _ in range(3):
            self.fuente.leer_poses()              # quedan a mitad de camino
        previas = self.fuente.consultas
        self.fuente.reiniciar()
        self.fuente.leer_poses()
        self.assertEqual(self.fuente.consultas, previas + 1,
                         "tras reiniciar(), la próxima llamada debe ser "
                         "una consulta real, no heredar el conteo previo")

    def test_intervalo_se_calcula_desde_hz_y_timestep(self) -> None:
        casos = [
            (10.0, 10, 10),    # default: 1 por decisión (100 ms / 10 ms)
            (100.0, 10, 1),    # tan rápido como el tick: sin límite real
            (20.0, 10, 5),
        ]
        for hz, timestep_ms, esperado in casos:
            cfg.HZ_CONSULTA_POSES = hz
            self.fuente.fijar_intervalo_consulta(timestep_ms)
            self.assertEqual(self.fuente._intervalo_ticks, esperado,
                             f"hz={hz} timestep={timestep_ms}")


class PruebaTasaDeConsultaEnElLazoReal(unittest.TestCase):
    """
    La verificación que de verdad importa: con el `CoordinadorEnjambre`
    real corriendo, el número de consultas reales debe ser el número de
    DECISIONES, no el número de TICKS — 10× menos, con el default.
    """

    N: int = 3

    def setUp(self) -> None:
        cfg.activar_simulador_local()
        self.sim = simulador_por_defecto(self.N)
        self.sim.iniciar()
        self.fuente, self.canal, self.entorno = construir(self.N)

    def tearDown(self) -> None:
        try:
            self.canal.cerrar()
        except Exception:                                       # noqa: BLE001
            pass
        self.fuente.cerrar()
        self.sim.detener()
        cfg.SIMULADOR_ACTIVO = False

    def test_una_consulta_real_por_decision(self) -> None:
        from coordinador_enjambre import SEMILLAS_LOTE, CoordinadorEnjambre

        coord = CoordinadorEnjambre(
            fuente=self.fuente, canal=self.canal, entorno=self.entorno,
            n_agentes=self.N, timestep_ms=10,
        )
        self.assertTrue(coord._reiniciar_episodio(SEMILLAS_LOTE[0]))
        consultas_tras_reinicio = self.fuente.consultas
        self.assertGreaterEqual(consultas_tras_reinicio, 1,
                                "el reinicio necesita al menos una consulta "
                                "real para poblar el caché")

        N_DECISIONES = 8
        for _ in range(N_DECISIONES):
            self.assertTrue(coord._avanzar(coord.pasos_por_decision))
            coord._decidir_y_actuar()

        nuevas = self.fuente.consultas - consultas_tras_reinicio
        self.assertEqual(
            nuevas, N_DECISIONES,
            f"{N_DECISIONES} decisiones deberían costar exactamente "
            f"{N_DECISIONES} consultas reales (1 c/u), no "
            f"{N_DECISIONES * coord.pasos_por_decision} (1 por tick)",
        )
        # Ninguna decisión se quedó sin pose por el límite de tasa: el
        # margen de antigüedad (150 ms) tolera de sobra la cadencia de
        # 100 ms entre consultas reales.
        self.assertEqual(self.fuente.agentes_vencidos(), [])


# =============================================================================
# 8. MAPEO CRUZADO — LO QUE DEBE DETECTAR `verificar_mapeo_ids.py`
# =============================================================================

class PruebaMapeoCruzado(unittest.TestCase):
    """
    El simulador arranca con marcadores y robots PERMUTADOS respecto de
    `config_robotat`. Comandar al agente 0 mueve el marcador de otro agente:
    exactamente el fallo silencioso que el mapeo mal configurado produce.
    """

    def setUp(self) -> None:
        cfg.activar_simulador_local()
        self.tick = 0
        # IDs de robot derivados de cfg.MAPEO_AGENTES, NO hardcodeados: el
        # canal/la fuente reales resuelven sus robots por ahí, así que un
        # número fijo (0,1,2) que no coincida con la tabla vigente hace que
        # `self.canal.conectar()` intente hablarle a un robot que el
        # simulador de esta prueba nunca levantó — exactamente lo que pasó
        # cuando la tabla por defecto cambió de robots 0-4 a 1-5.
        r0 = cfg.MAPEO_AGENTES[0].id_robot
        r1 = cfg.MAPEO_AGENTES[1].id_robot
        r2 = cfg.MAPEO_AGENTES[2].id_robot
        m0 = cfg.MAPEO_AGENTES[0].id_marcador
        m1 = cfg.MAPEO_AGENTES[1].id_marcador
        m2 = cfg.MAPEO_AGENTES[2].id_marcador
        # robot0 ↔ marcador de agente 1, robot1 ↔ marcador de agente 0
        # (cruzados); robot2 queda con el suyo (correcto).
        mapeo_cruzado = {r0: m1, r1: m0, r2: m2}
        poses = {r0: (-0.8, 0.0, 0.0), r1: (-0.4, 0.0, 0.0), r2: (0.0, 0.0, 0.0)}
        self.sim = SimuladorRobotat(mapeo_cruzado, poses)
        self.sim.iniciar()
        try:
            self.fuente = FuentePosesRobotat(3, lambda: self.tick)
            self.fuente.conectar()
            self.canal = CanalActuacionRobotat(3, self.fuente)
            self.canal.conectar()
        except Exception:
            # Si algo de esto falla, tearDown() NUNCA se llama (unittest no
            # lo invoca cuando setUp lanza) y `self.sim` quedaría corriendo
            # en segundo plano para siempre, contaminando con hilos zombis
            # los puertos que usan las pruebas siguientes — el mecanismo
            # exacto que hizo fallar en cascada media suite cuando esto
            # rompió por primera vez. Limpiar acá antes de relanzar.
            self.sim.detener()
            cfg.SIMULADOR_ACTIVO = False
            raise

    def tearDown(self) -> None:
        self.canal.cerrar()
        self.fuente.cerrar()
        self.sim.detener()
        cfg.SIMULADOR_ACTIVO = False

    def test_el_agente_equivocado_se_mueve(self) -> None:
        antes = {i: self.fuente.leer_poses() for i in range(1)}
        del antes
        poses0 = {i: m.pose.copy() for i, m in self.fuente.leer_poses()}
        self.canal.enviar_acciones({0: (0.25, 0.0), 1: (0.0, 0.0),
                                    2: (0.0, 0.0)})
        time.sleep(0.30)
        self.canal.enviar_acciones({i: (0.0, 0.0) for i in range(3)})
        poses1 = {i: m.pose.copy() for i, m in self.fuente.leer_poses()}

        desplazamientos = {
            i: float(np.linalg.norm(poses1[i][:2] - poses0[i][:2]))
            for i in poses0 if i in poses1
        }
        # Umbral compatible con la rampa de arranque: 0.25 m/s × 0.30 s × 0.25
        # ≈ 0.019 m de desplazamiento esperado para el que sí se mueve.
        movidos = [i for i, d in desplazamientos.items() if d > 0.01]
        self.assertEqual(
            movidos, [1],
            f"con el mapeo cruzado, comandar al agente 0 mueve al agente 1; "
            f"desplazamientos = {desplazamientos}",
        )


# =============================================================================
# 9. EL VERIFICADOR DE MAPEO, VERIFICADO
# =============================================================================

class PruebaVerificadorDeMapeo(unittest.TestCase):
    """
    Un verificador que siempre dice OK no verifica nada. Se lo corre contra
    dos "laboratorios": uno con el mapeo que declara `config_robotat` y otro
    permutado. Debe aprobar el primero y señalar exactamente qué está mal en
    el segundo.
    """

    def _correr(self, mapeo_real):
        cfg.activar_simulador_local()
        poses = {r: (-0.8 + 0.4 * k, 0.3, 0.0)
                 for k, r in enumerate(sorted(mapeo_real))}
        sim = SimuladorRobotat(mapeo_real, poses)
        sim.iniciar()
        try:
            return verificar(N_AGENTES, verboso=False)
        finally:
            sim.detener()
            cfg.SIMULADOR_ACTIVO = False

    def test_aprueba_el_mapeo_correcto(self) -> None:
        mapeo_real = {
            cfg.MAPEO_AGENTES[i].id_robot: cfg.MAPEO_AGENTES[i].id_marcador
            for i in range(N_AGENTES)
        }
        resultados = self._correr(mapeo_real)
        self.assertTrue(informe(resultados))
        self.assertEqual([r.veredicto for r in resultados], ["OK"] * N_AGENTES)

    def test_detecta_el_mapeo_cruzado(self) -> None:
        # IDs derivados de cfg.MAPEO_AGENTES (no hardcodeados): `verificar()`
        # resuelve sus robots por esa tabla, así que un número fijo que no
        # coincida deja al simulador de la prueba sin el robot que el
        # verificador intenta comandar.
        r0, r1, r2 = (cfg.MAPEO_AGENTES[i].id_robot for i in range(3))
        m0, m1, m2 = (cfg.MAPEO_AGENTES[i].id_marcador for i in range(3))
        # robot0 ↔ marcador de agente 1, robot1 ↔ marcador de agente 0
        # (intercambiados); robot2 ↔ el suyo (correcto).
        resultados = self._correr({r0: m1, r1: m0, r2: m2})
        self.assertFalse(informe(resultados))
        self.assertEqual([r.veredicto for r in resultados],
                         ["CRUZADO", "CRUZADO", "OK"])
        self.assertEqual(resultados[0].marcador_movido, m1)
        self.assertEqual(resultados[1].marcador_movido, m0)

    def test_detecta_un_robot_que_no_responde(self) -> None:
        """
        Robot presente en la red pero que no se mueve (batería, rueda
        trabada): ningún marcador cambia y el veredicto es NADIE, no un
        falso OK.
        """
        cfg.activar_simulador_local()
        mapeo_real = {
            cfg.MAPEO_AGENTES[i].id_robot: cfg.MAPEO_AGENTES[i].id_marcador
            for i in range(N_AGENTES)
        }
        poses = {r: (-0.8 + 0.4 * k, 0.3, 0.0)
                 for k, r in enumerate(sorted(mapeo_real))}
        sim = SimuladorRobotat(mapeo_real, poses)
        # el robot 1 acepta comandos pero su física queda congelada
        id_inerte = cfg.MAPEO_AGENTES[1].id_robot
        sim.iniciar()
        try:
            estado = sim.robots[id_inerte]

            # La física integra a partir de las rpm, así que "congelarlo" es
            # reponerlas a cero continuamente: el robot acepta el comando y
            # no se mueve, igual que con una rueda trabada.
            def congelar() -> None:
                while sim._corriendo.is_set():
                    with sim._lock:
                        estado.rpm_izq = 0.0
                        estado.rpm_der = 0.0
                    time.sleep(0.002)

            threading.Thread(target=congelar, daemon=True).start()
            resultados = verificar(N_AGENTES, verboso=False)
        finally:
            sim.detener()
            cfg.SIMULADOR_ACTIVO = False

        self.assertFalse(informe(resultados))
        self.assertEqual(resultados[1].veredicto, "NADIE")
        self.assertEqual([resultados[0].veredicto, resultados[2].veredicto],
                         ["OK", "OK"])


# =============================================================================
# 10. EL LAZO COMPLETO, FUERA DE WEBOTS
# =============================================================================

class PruebaLazoDeControlCompleto(unittest.TestCase):
    """
    La prueba que da sentido a todo lo anterior: el `CoordinadorEnjambre`
    real —política PPO, filtro CBF, escape, métricas— corriendo contra el
    simulador, sin Webots por ningún lado.

    Cubre en un solo camino: construcción con adaptadores inyectados,
    reinicio de episodio SIN teletransporte, decisión, conversión a ruedas,
    CBOR, física, JSON, validación, y parada final.
    """

    N: int = 5

    def setUp(self) -> None:
        cfg.activar_simulador_local()
        self.sim = simulador_por_defecto(self.N)
        self.sim.iniciar()
        self.fuente, self.canal, self.entorno = construir(self.N)

    def tearDown(self) -> None:
        try:
            self.canal.cerrar()
        except Exception:                                       # noqa: BLE001
            pass
        self.fuente.cerrar()
        self.sim.detener()
        cfg.SIMULADOR_ACTIVO = False

    def test_corre_un_tramo_de_episodio(self) -> None:
        from coordinador_enjambre import SEMILLAS_LOTE, CoordinadorEnjambre

        coord = CoordinadorEnjambre(
            fuente=self.fuente, canal=self.canal, entorno=self.entorno,
            n_agentes=self.N, timestep_ms=10,
        )
        # El nombre del CSV debe llevar el origen de los datos, para no pisar
        # el artefacto de Webots (mismo N y mismos flags ⇒ mismo nombre).
        self.assertIn("_robotat", coord.ruta_csv.name)

        self.assertTrue(coord._reiniciar_episodio(SEMILLAS_LOTE[0]),
                        "el reinicio sin teletransporte debe funcionar")

        posiciones_iniciales = {
            i: self.sim.pose_de_robot(cfg.MAPEO_AGENTES[i].id_robot)[:2]
            for i in range(self.N)
        }
        # Mismo orden que el lazo real: avanzar el reloj, después decidir.
        # `_decidir_y_actuar` devuelve `episodio_terminado`, y en 20
        # decisiones (2 s) el episodio no debe terminar.
        for k in range(20):
            self.assertTrue(coord._avanzar(coord.pasos_por_decision),
                            f"el reloj se detuvo en la decisión {k}")
            self.assertFalse(coord._decidir_y_actuar(),
                             f"el episodio terminó en la decisión {k}")

        # Guardia de regresión: el sello de tiempo de las mediciones tiene
        # que venir del reloj del lazo. Si la fuente sella con un contador
        # que no avanza, la antigüedad crece linealmente con el tick y el
        # coordinador cree estar decidiendo con poses de hace 20 segundos.
        self.assertLessEqual(
            coord._antiguedad_max, 3,
            f"antigüedad máxima {coord._antiguedad_max} ticks: la fuente no "
            f"está sellando las poses con el reloj del lazo",
        )

        movidos = sum(
            1 for i in range(self.N)
            if math.dist(
                self.sim.pose_de_robot(cfg.MAPEO_AGENTES[i].id_robot)[:2],
                posiciones_iniciales[i]) > 0.01
        )
        self.assertGreaterEqual(movidos, self.N - 1,
                                f"sólo {movidos}/{self.N} agentes se movieron")

        coord._detener_seguro()
        self.assertTrue(esperar_a(self.sim.todos_detenidos),
                        "el camino de parada del coordinador debe dejar "
                        "quietos a los cinco robots")
        for linea in self.fuente.resumen() + self.canal.resumen():
            print(f"    {linea}")


# =============================================================================
# 11. CONSULTA MARCADOR POR MARCADOR
# =============================================================================

class PruebaConsultaIndividual(BaseIntegracion):
    """
    Con `MODO_CONSULTA_POSES = "individual"`, la oclusión de un marcador
    afecta SÓLO a su agente. Es la contrapartida de
    `PruebaMarcadorAusente`, donde en modo "lote" la respuesta corta deja sin
    pose al enjambre entero.
    """

    fallas = FallasSimulador(marcadores_perdidos={MARCADOR_AGENTE_1},
                             modo_marcador_perdido="faltante")

    def setUp(self) -> None:
        self._modo_previo = cfg.MODO_CONSULTA_POSES
        cfg.MODO_CONSULTA_POSES = "individual"
        super().setUp()

    def tearDown(self) -> None:
        super().tearDown()
        cfg.MODO_CONSULTA_POSES = self._modo_previo

    def test_la_oclusion_no_contagia_al_resto(self) -> None:
        vistos = set()
        for _ in range(10):
            for i, _m in self.fuente.leer_poses():
                vistos.add(i)
            time.sleep(0.01)
        self.assertEqual(sorted(vistos), [0, 2],
                         "sólo el agente del marcador ocluido debe quedarse "
                         "sin pose")
        self.assertEqual(self.fuente.agentes_faltantes(), [1])

    def test_modo_invalido_se_rechaza(self) -> None:
        cfg.MODO_CONSULTA_POSES = "todos_juntos_porfa"
        try:
            with self.assertRaises(ValueError):
                FuentePosesRobotat(N_AGENTES, lambda: 0)
        finally:
            cfg.MODO_CONSULTA_POSES = "individual"


# =============================================================================
# 12. ARRANQUE SEGURO
# =============================================================================

class PruebaChequeoDeArranque(unittest.TestCase):
    """
    El chequeo geométrico es puro: se prueba con poses construidas a mano,
    una condición inválida por vez, y se exige que el mensaje NOMBRE al
    agente culpable — en el laboratorio, con cinco robots, "algo está mal" no
    sirve de nada.
    """

    @staticmethod
    def _ok(n: int = 3):
        return {0: np.array([0.6, 1.5, 0.0]),
                1: np.array([1.5, 1.5, 0.0]),
                2: np.array([2.4, 1.5, 0.0])}

    def test_configuracion_valida_pasa(self) -> None:
        self.assertEqual(revisar_poses_iniciales(self._ok(), 3), [])

    def test_agente_sin_pose(self) -> None:
        poses = self._ok()
        del poses[1]
        problemas = revisar_poses_iniciales(poses, 3)
        self.assertEqual(len(problemas), 1)
        self.assertIn("[1]", problemas[0])
        self.assertIn("sin pose", problemas[0])

    def test_fuera_de_la_arena(self) -> None:
        poses = self._ok()
        poses[2] = np.array([3.4, 1.5, 0.0])
        problemas = revisar_poses_iniciales(poses, 3)
        self.assertEqual(len(problemas), 1)
        self.assertIn("agente 2", problemas[0])
        self.assertIn("fuera de la arena", problemas[0])
        self.assertIn("C1", problemas[0])   # apunta a la calibración

    def test_pegado_a_la_pared(self) -> None:
        poses = self._ok()
        poses[0] = np.array([0.12, 1.5, 0.0])
        problemas = revisar_poses_iniciales(poses, 3)
        self.assertEqual(len(problemas), 1)
        self.assertIn("agente 0", problemas[0])
        self.assertIn("pared", problemas[0])

    def test_pared_en_cada_borde(self) -> None:
        """Los cuatro muros, no sólo el de x mínimo."""
        for k, p in enumerate([[0.10, 1.5], [2.90, 1.5],
                               [1.5, 0.10], [1.5, 2.90]]):
            poses = self._ok()
            poses[1] = np.array([p[0], p[1], 0.0])
            problemas = revisar_poses_iniciales(poses, 3)
            self.assertTrue(any("pared" in x for x in problemas),
                            f"borde {k} no detectado: {problemas}")

    def test_demasiado_juntos(self) -> None:
        poses = self._ok()
        poses[1] = np.array([0.68, 1.5, 0.0])      # a 8 cm del agente 0
        problemas = revisar_poses_iniciales(poses, 3)
        self.assertEqual(len(problemas), 1)
        self.assertIn("agentes 0 y 1", problemas[0])
        self.assertIn("colisión", problemas[0])

    def test_justo_en_el_umbral_pasa(self) -> None:
        """
        Estar exactamente en el umbral es admisible. Sin la tolerancia de
        `TOL_GEOMETRICA_M` este caso falla por redondeo: 0.20 + 0.15 − 0.20
        da 0.14999999999999997, y el rechazo diría "0.150 m (mínimo 0.15 m)".
        """
        poses = {0: np.array([cfg.MARGEN_PARED_ARRANQUE_M, 1.5, 0.0]),
                 1: np.array([cfg.MARGEN_PARED_ARRANQUE_M
                              + cfg.D_SEPARACION_MIN_ARRANQUE_M, 1.5, 0.0])}
        self.assertEqual(revisar_poses_iniciales(poses, 2), [])

    def test_la_tolerancia_no_desafila_el_chequeo(self) -> None:
        """1 cm por debajo del umbral se sigue rechazando."""
        poses = {0: np.array([cfg.MARGEN_PARED_ARRANQUE_M, 1.5, 0.0]),
                 1: np.array([cfg.MARGEN_PARED_ARRANQUE_M
                              + cfg.D_SEPARACION_MIN_ARRANQUE_M - 0.01,
                              1.5, 0.0])}
        self.assertEqual(len(revisar_poses_iniciales(poses, 2)), 1)
        poses = {0: np.array([cfg.MARGEN_PARED_ARRANQUE_M - 0.01, 1.5, 0.0]),
                 1: np.array([1.5, 1.5, 0.0])}
        self.assertEqual(len(revisar_poses_iniciales(poses, 2)), 1)

    def test_acumula_varios_problemas(self) -> None:
        poses = {0: np.array([0.05, 0.05, 0.0]),
                 1: np.array([0.10, 0.05, 0.0])}
        problemas = revisar_poses_iniciales(poses, 3)
        self.assertGreaterEqual(len(problemas), 3)   # falta el 2, pared, juntos


class PruebaArranqueSeguroExtremoAExtremo(BaseIntegracion):
    """El chequeo corriendo contra el simulador, con el lanzador real."""

    def test_acepta_la_formacion_por_defecto(self) -> None:
        self.assertTrue(chequeo_de_arranque(self.fuente, N_AGENTES,
                                            forzar=False))

    def test_rechaza_un_robot_contra_la_pared(self) -> None:
        # marco por defecto: env = lab + (1.5, 1.5); x_lab = −1.45 ⇒ x_env = 0.05
        with self.sim._lock:
            self.sim.robots[cfg.MAPEO_AGENTES[1].id_robot].x = -1.45
        self.assertFalse(chequeo_de_arranque(self.fuente, N_AGENTES,
                                             forzar=False))

    def test_rechaza_dos_robots_encimados(self) -> None:
        with self.sim._lock:
            a = self.sim.robots[cfg.MAPEO_AGENTES[0].id_robot]
            b = self.sim.robots[cfg.MAPEO_AGENTES[1].id_robot]
            b.x, b.y = a.x + 0.05, a.y
        self.assertFalse(chequeo_de_arranque(self.fuente, N_AGENTES,
                                             forzar=False))

    def test_rechaza_un_agente_sin_marcador(self) -> None:
        # `self.sim.fallas` es una copia propia de esta prueba (ver setUp),
        # así que mutarla no afecta a nadie más.
        self.sim.fallas.marcadores_perdidos = {
            cfg.MAPEO_AGENTES[2].id_marcador
        }
        self.assertFalse(chequeo_de_arranque(self.fuente, N_AGENTES,
                                             forzar=False))

    def test_forzar_arranca_igual(self) -> None:
        with self.sim._lock:
            self.sim.robots[cfg.MAPEO_AGENTES[1].id_robot].x = -1.45
        self.assertTrue(chequeo_de_arranque(self.fuente, N_AGENTES,
                                            forzar=True))


class PruebaRampaDeVelocidad(BaseIntegracion):

    def test_las_primeras_decisiones_van_al_25_por_ciento(self) -> None:
        self.assertTrue(cfg.ARRANQUE_SEGURO)
        self.fuente.leer_poses()
        id_robot = cfg.MAPEO_AGENTES[0].id_robot

        self.canal.enviar_acciones({i: (0.20, 0.0) for i in range(N_AGENTES)})
        self.assertTrue(self.esperar(
            lambda: self.sim.rpm_de_robot(id_robot) != (0.0, 0.0)))
        rpm_rampa = self.sim.rpm_de_robot(id_robot)[0]

        # agotar la rampa
        for _ in range(cfg.DECISIONES_ARRANQUE):
            self.fuente.leer_poses()
            self.canal.enviar_acciones({i: (0.20, 0.0)
                                        for i in range(N_AGENTES)})
        self.assertTrue(self.esperar(
            lambda: abs(self.sim.rpm_de_robot(id_robot)[0]
                        - rpm_rampa / cfg.FACTOR_VELOCIDAD_ARRANQUE) < 1.0))
        rpm_plena = self.sim.rpm_de_robot(id_robot)[0]

        self.assertAlmostEqual(rpm_rampa / rpm_plena,
                               cfg.FACTOR_VELOCIDAD_ARRANQUE, places=3)
        self.assertEqual(self.canal.decisiones_limitadas,
                         cfg.DECISIONES_ARRANQUE)

    def test_se_puede_desactivar(self) -> None:
        cfg.ARRANQUE_SEGURO = False
        try:
            self.assertEqual(self.canal.factor_arranque(), 1.0)
            self.fuente.leer_poses()
            self.canal.enviar_acciones({i: (0.20, 0.0)
                                        for i in range(N_AGENTES)})
            id_robot = cfg.MAPEO_AGENTES[0].id_robot
            self.assertTrue(self.esperar(
                lambda: self.sim.rpm_de_robot(id_robot) != (0.0, 0.0)))
            esperado = rad_s_a_rpm(0.20 / cfg.RADIO_RUEDA_M)
            self.assertAlmostEqual(self.sim.rpm_de_robot(id_robot)[0],
                                   esperado, places=2)
            self.assertEqual(self.canal.decisiones_limitadas, 0)
        finally:
            cfg.ARRANQUE_SEGURO = True

    def test_la_rampa_no_cambia_la_direccion(self) -> None:
        """
        Escalar v y ω por el mismo factor preserva el signo de ambos, que es
        lo que garantiza que ni el CBF ni el escape se rompan.
        """
        self.fuente.leer_poses()
        self.canal.enviar_acciones({i: (0.20, -3.0) for i in range(N_AGENTES)})
        id_robot = cfg.MAPEO_AGENTES[0].id_robot
        self.assertTrue(self.esperar(
            lambda: self.sim.rpm_de_robot(id_robot) != (0.0, 0.0)))
        izq, der = self.sim.rpm_de_robot(id_robot)
        self.assertGreater(izq, der, "ω<0 ⇒ rueda izquierda más rápida")
        self.assertGreater(izq, 0.0)


if __name__ == "__main__":
    print("=" * 70)
    print("PRUEBAS DE INTEGRACIÓN CONTRA EL SIMULADOR DEL ROBOTAT")
    print("=" * 70)
    unittest.main(verbosity=2)
