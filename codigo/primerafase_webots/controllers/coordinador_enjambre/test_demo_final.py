"""
test_demo_final.py
==================
Pruebas de `demo_final.py` y `publicador_estado.py` (DEMOSTRACIÓN, NO
CITABLE), contra el simulador local y sin hardware. Numeración del spec
(§7):

  1. modo `objetivos`, 2 episodios × 100 decisiones: corre completo y los
     CSV tienen las columnas de la etapa 7 (episodios: las del 30-09, en el
     mismo orden; decisiones: las 14);
  3. publicación: mensajes = decisiones + 2 por episodio (+ los de sesión),
     JSON, ≤ 60 KB, secuencia sin huecos en loopback, costo < 1 ms;
  4. falla inyectada en el publicador (puerto cerrado, excepción adentro de
     `publicar`, destino inválido): el episodio termina válido y la consola
     avisa UNA vez;
  5. a nivel de decisión, sin red ni tiempo real: `CoordinadorDemo` decide
     BIT A BIT igual que `CoordinadorEnjambre`, con la publicación encendida
     y apagada (el patrón de la prueba a1 de la réplica);
  6. con `--simulador` la calibración queda en identidad aunque exista
     `calibracion_medida.json`.

    python -m unittest test_demo_final -v

Las corridas del simulador escriben en
`resultados_demo_final/pruebas_<fecha>/` (rotuladas como demostración).

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import math
import socket
import sys
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from unittest import mock

_CARPETA = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import config_robotat as cfg
import demo_final as D
import publicador_estado as P

_PRUEBAS = D.DIR_SALIDA_DEMO_FINAL / f"pruebas_{datetime.now():%Y%m%d_%H%M%S}"
_REF_EPISODIOS = (_CARPETA.parents[2] / "REPORTE_2026-09-30_datos" / "csv"
                  / "20260930_sesion-evaluacion_etapa7_episodios.csv")
_COLUMNAS_DECISIONES = [
    "episodio", "agente", "robot", "paso", "pose_env_x", "pose_env_y",
    "pose_env_th", "v_ejecutada", "w_ejecutada", "en_escape", "cbf_intervino",
    "rpm_pico", "con_vecino", "en_retroceso"]
_GUARDADOS = ("ESCALA_POSICION", "ROTACION_MARCO_RAD", "TRASLACION_X_M",
              "TRASLACION_Y_M", "OFFSET_HEADING_RAD", "offset_rumbo_de_robot",
              "OFFSETS_RUMBO_POR_ROBOT", "OFFSETS_RUMBO_MEDIDOS",
              "SIMULADOR_ACTIVO", "SIMULADOR_HOST", "SIMULADOR_PUERTO_POSES",
              "SIMULADOR_PUERTO_BASE_ROBOT")


def _cabecera(ruta: Path) -> List[str]:
    with open(ruta, encoding="utf-8", newline="") as fh:
        return next(csv.reader(fh))


class Receptor:
    """Receptor UDP de prueba en un puerto libre de loopback."""

    def __init__(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.2)
        self.puerto = self.sock.getsockname()[1]
        self.crudos: List[bytes] = []
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()

    def _bucle(self) -> None:
        while not self._parar.is_set():
            try:
                datos, _ = self.sock.recvfrom(65535)
            except (socket.timeout, OSError):
                continue
            self.crudos.append(datos)

    def cerrar(self) -> List[bytes]:
        time.sleep(0.3)
        self._parar.set()
        self._hilo.join(timeout=2.0)
        self.sock.close()
        return self.crudos


class _ConCfg(unittest.TestCase):
    """Guarda y repone la configuración global que `main` toca."""

    def setUp(self) -> None:
        self._previo = {k: getattr(cfg, k) for k in _GUARDADOS
                        if hasattr(cfg, k)}

    def tearDown(self) -> None:
        for k, v in self._previo.items():
            setattr(cfg, k, v)

    def _correr(self, nombre: str, extra: List[str], puerto: int):
        salida = io.StringIO()
        argv = ["--modo", "objetivos", "--simulador", "--puerto-simulador",
                str(puerto), "--salida", str(_PRUEBAS / nombre),
                "--etiqueta", f"prueba {nombre}"] + extra
        with contextlib.redirect_stdout(salida):
            codigo = D.main(argv, preguntar=lambda _m: "")
        texto = salida.getvalue()
        (_PRUEBAS / nombre).mkdir(parents=True, exist_ok=True)
        (_PRUEBAS / nombre / "consola.txt").write_bytes(texto.encode("utf-8"))
        return codigo, texto

    @staticmethod
    def _episodios(nombre: str) -> List[Dict[str, str]]:
        ruta = next((_PRUEBAS / nombre).glob("*_demo-objetivos_episodios.csv"))
        with open(ruta, encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))


class Prueba1y3y6Objetivos(_ConCfg):
    """1, 3 y 6 sobre la MISMA corrida (2 × 100, colocación automática)."""

    def test_objetivos_publicacion_y_calibracion(self) -> None:
        self.assertTrue((_CARPETA / "calibracion_medida.json").is_file(),
                        "la prueba 6 sólo dice algo si existe la medida")
        rec = Receptor()
        costos: List[float] = []
        original = D.EstadoDemo.tras_decision

        def medido(self_, dt_s):
            t0 = time.perf_counter()
            original(self_, dt_s)
            costos.append(time.perf_counter() - t0)
        try:
            with mock.patch.object(D.EstadoDemo, "tras_decision", medido):
                codigo, texto = self._correr(
                    "p1_objetivos", ["--episodios", "2", "--decisiones", "100",
                                     "--gui", f"127.0.0.1:{rec.puerto}"],
                    27600)
            # (6) Antes de reponer la configuración: identidad.
            self.assertEqual(cfg.ESCALA_POSICION, 1.0)
            self.assertEqual(cfg.ROTACION_MARCO_RAD, 0.0)
            self.assertEqual((cfg.TRASLACION_X_M, cfg.TRASLACION_Y_M),
                             (1.5, 1.5))
            self.assertEqual(cfg.OFFSET_HEADING_RAD, 0.0)
            for i in range(5):
                rid = cfg.MAPEO_AGENTES[i].id_robot
                self.assertEqual(cfg.offset_rumbo_de_robot(rid), 0.0)
        finally:
            crudos = rec.cerrar()
        self.assertEqual(codigo, 0, texto[-3000:])

        # (1) corrió completo y las columnas.
        eps = self._episodios("p1_objetivos")
        self.assertEqual(len(eps), 2)
        self.assertTrue(all(e["valido"] == "1" for e in eps),
                        [e.get("motivo") for e in eps])
        ruta_ep = next((_PRUEBAS / "p1_objetivos").glob("*episodios.csv"))
        ruta_de = next((_PRUEBAS / "p1_objetivos").glob("*decisiones.csv"))
        self.assertEqual(_cabecera(ruta_ep), _cabecera(_REF_EPISODIOS))
        self.assertEqual(_cabecera(ruta_de), _COLUMNAS_DECISIONES)
        readme = (_PRUEBAS / "p1_objetivos" / "README.md").read_text(
            encoding="utf-8")
        self.assertEqual(readme.splitlines()[0], D.LEYENDA)

        # (3) los mensajes.
        msgs = [json.loads(c.decode("utf-8")) for c in crudos]
        self.assertTrue(all(len(c) <= P.MAX_DATAGRAMA_B for c in crudos))
        seq = [m["secuencia"] for m in msgs]
        self.assertEqual(seq, list(range(1, len(msgs) + 1)), "huecos")
        tipos = [m["tipo"] for m in msgs]
        decisiones = sum(int(e["decisiones"]) for e in eps)
        self.assertEqual(tipos.count("paso"), decisiones)
        self.assertEqual(tipos.count("inicio_episodio"), 2)
        self.assertEqual(tipos.count("fin_episodio"), 2)
        self.assertEqual(len(msgs), decisiones + 2 * 2
                         + tipos.count("estado_sesion"))
        pasos = [m for m in msgs if m["tipo"] == "paso"]
        self.assertTrue(all(len(m["agentes"]) == 5 for m in pasos))
        con_rejilla = [m for m in pasos if "rejilla" in m]
        self.assertEqual(len(con_rejilla),
                         sum(1 for m in pasos if m["paso"] % D.CADA_REJILLA == 0))
        # La cobertura en vivo del último paso = la del CSV (rejilla completa).
        for k, e in enumerate(eps, start=1):
            ult = [m for m in pasos if m["episodio"] == k][-1]
            self.assertAlmostEqual(ult["cobertura"], float(e["cobertura_aoi"]),
                                   places=4)
        fin = [m for m in msgs if m["tipo"] == "fin_episodio"]
        self.assertEqual([m["resultado"]["valido"] for m in fin], [1, 1])
        media_ms = 1000.0 * sum(costos) / len(costos)
        print(f"\n  [prueba 3] {len(msgs)} mensajes, máx "
              f"{max(len(c) for c in crudos)} B; costo medio de publicar "
              f"{media_ms:.3f} ms (p máx {1000 * max(costos):.2f} ms)")
        self.assertLess(media_ms, 1.0)


class Prueba4Fallas(_ConCfg):
    """Un episodio corto por falla, desde donde están (`--colocacion
    actual`): termina válido y la consola avisa una vez."""

    BASE = ["--episodios", "1", "--decisiones", "60", "--colocacion", "actual"]

    def _valido(self, nombre: str) -> None:
        eps = self._episodios(nombre)
        self.assertEqual([e["valido"] for e in eps], ["1"],
                         [e.get("motivo") for e in eps])

    def test_puerto_cerrado(self) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
        s.close()                              # nadie escucha
        codigo, texto = self._correr(
            "p4_puerto_cerrado", self.BASE + ["--gui", f"127.0.0.1:{puerto}"],
            27620)
        self.assertEqual(codigo, 0, texto[-3000:])
        self._valido("p4_puerto_cerrado")
        self.assertLessEqual(texto.count("publicación APAGADA"), 1)

    def test_excepcion_adentro_de_publicar(self) -> None:
        rec = Receptor()
        try:
            # Sólo el nombre `json` DEL PUBLICADOR (no el módulo global).
            falso = mock.Mock()
            falso.dumps.side_effect = RuntimeError("inyectada")
            with mock.patch.object(P, "json", falso):
                codigo, texto = self._correr(
                    "p4_excepcion", self.BASE + ["--gui",
                                                 f"127.0.0.1:{rec.puerto}"],
                    27640)
        finally:
            crudos = rec.cerrar()
        self.assertEqual(codigo, 0, texto[-3000:])
        self._valido("p4_excepcion")
        self.assertEqual(texto.count("publicación APAGADA"), 1)
        self.assertEqual(crudos, [])

    def test_excepcion_al_armar_el_mensaje(self) -> None:
        with mock.patch.object(D.EstadoDemo, "_mensaje_paso",
                               side_effect=KeyError("inyectada")):
            codigo, texto = self._correr(
                "p4_armado", self.BASE + ["--gui", "127.0.0.1:9"], 27660)
        self.assertEqual(codigo, 0, texto[-3000:])
        self._valido("p4_armado")
        self.assertEqual(texto.count("publicación APAGADA"), 1)

    def test_destino_invalido(self) -> None:
        codigo, texto = self._correr(
            "p4_destino_invalido",
            self.BASE + ["--gui", "noexiste.invalid:27300", "--gui", "abc"],
            27680)
        self.assertEqual(codigo, 0, texto[-3000:])
        self._valido("p4_destino_invalido")
        self.assertEqual(texto.count("publicación APAGADA"), 1)
        self.assertEqual(texto.count("descartado:"), 2)


class Prueba4Unitaria(unittest.TestCase):
    """El publicador por sí solo: nunca lanza, se apaga a los 20."""

    def test_nunca_lanza_y_se_apaga(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            pub = P.PublicadorEstado(["127.0.0.1:9"], en_hilo=False)
            pub._sock.close()
            pub._sock = mock.Mock()
            pub._sock.sendto.side_effect = OSError("roto")
            for _ in range(P.MAX_ERRORES_SEGUIDOS + 5):
                self.assertFalse(pub.publicar({"tipo": "paso"}))
            pub.cerrar()
        self.assertFalse(pub.activo)
        self.assertEqual(pub.errores, P.MAX_ERRORES_SEGUIDOS)
        self.assertEqual(out.getvalue().count("APAGADA"), 1)

    def test_datagrama_grande_y_nan(self) -> None:
        rec = Receptor()
        with contextlib.redirect_stdout(io.StringIO()):
            pub = P.PublicadorEstado([f"127.0.0.1:{rec.puerto}"], en_hilo=False)
            self.assertFalse(pub.publicar({"tipo": "x", "b": "a" * 70_000}))
            self.assertTrue(pub.publicar({"tipo": "y", "v": float("nan"),
                                          "w": math.inf}))
            pub.cerrar()
        crudos = rec.cerrar()
        self.assertEqual(len(crudos), 1)
        m = json.loads(crudos[0])
        self.assertEqual((m["tipo"], m["v"], m["w"], m["secuencia"]),
                         ("y", None, None, 2))


class Prueba4Hilo(unittest.TestCase):
    """El envío en hilo: en orden, sin huecos, y `cerrar` vacía la cola;
    un error adentro del hilo se cuenta y apaga igual que sin hilo."""

    def test_orden_y_vaciado(self) -> None:
        rec = Receptor()
        with contextlib.redirect_stdout(io.StringIO()):
            pub = P.PublicadorEstado([f"127.0.0.1:{rec.puerto}"])
            for k in range(300):
                self.assertTrue(pub.publicar({"tipo": "paso", "k": k}))
                time.sleep(0.002)
            pub.cerrar()
        crudos = rec.cerrar()
        msgs = [json.loads(c) for c in crudos]
        self.assertEqual([m["k"] for m in msgs], list(range(300)))
        self.assertEqual([m["secuencia"] for m in msgs], list(range(1, 301)))
        self.assertEqual((pub.enviados, pub.errores, pub.descartados),
                         (300, 0, 0))

    def test_rafaga_descarta_sin_apagar(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            pub = P.PublicadorEstado(["127.0.0.1:9"])
            for k in range(3 * P.COLA_MAX):
                self.assertTrue(pub.publicar({"tipo": "paso", "k": k}))
            pub.cerrar()
        self.assertTrue(pub.activo)
        self.assertEqual(pub.errores, 0)
        self.assertEqual(pub.enviados + pub.descartados, 3 * P.COLA_MAX)

    def test_error_en_el_hilo(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            pub = P.PublicadorEstado(["127.0.0.1:9"])
            pub._sock.close()
            for _ in range(P.MAX_ERRORES_SEGUIDOS + 5):
                pub.publicar({"tipo": "paso"})
                time.sleep(0.01)
            pub.cerrar()
        self.assertFalse(pub.activo)
        self.assertEqual(pub.errores, P.MAX_ERRORES_SEGUIDOS)
        self.assertEqual(out.getvalue().count("APAGADA"), 1)


class Prueba5BitABit(unittest.TestCase):
    """
    (5) `CoordinadorDemo` decide BIT A BIT como `CoordinadorEnjambre` ante
    las mismas observaciones, con la publicación encendida (a un receptor
    real) y apagada. El banco es el de la prueba a1 de la réplica
    (`test_replica_con_obstaculo.PruebaA1Decision`): sin red ni tiempo real,
    la fuente recibe la matriz de poses de cada decisión de un episodio del
    30-09 (s1, ep 5, semilla 420004), el canal registra los rpm y el entorno
    sólo cuenta ticks.
    """

    EPISODIO, SEMILLA = 5, 420004

    def setUp(self) -> None:
        import replica_con_obstaculo as R
        self.R = R
        self._previo = {k: getattr(cfg, k) for k in (
            "ESCALA_POSICION", "ROTACION_MARCO_RAD", "TRASLACION_X_M",
            "TRASLACION_Y_M", "OFFSET_HEADING_RAD", "offset_rumbo_de_robot")}
        R.imponer_identidad()

    def tearDown(self) -> None:
        for k, v in self._previo.items():
            setattr(cfg, k, v)

    def _matrices(self):
        R = self.R
        filas = [r for r in R._leer(
            R.DIR_3009 / "20260930_sesion-evaluacion_etapa7_decisiones.csv")
            if r["episodio"] == str(self.EPISODIO)]
        pasos = sorted({int(r["paso"]) for r in filas})
        por = {(r["paso"], r["agente"]): r for r in filas}
        out = []
        for k in pasos:
            m = []
            for i in range(R.N_AGENTES):
                r = por[(str(k), str(i))]
                rid = cfg.MAPEO_AGENTES[i].id_robot
                xl, yl, yaw = R.env_a_lab(float(r["pose_env_x"]),
                                          float(r["pose_env_y"]),
                                          float(r["pose_env_th"]), rid)
                m.append([xl, yl, 0.0, math.cos(yaw / 2), 0.0, 0.0,
                          math.sin(yaw / 2)])
            out.append(m)
        return out

    def _correr(self, variante: str, matrices, receptor=None):
        import numpy as np
        import adaptadores_robotat as ad
        import coordinador_enjambre as ce
        R = self.R

        class Entorno(ad.EntornoEjecucionRobotat):
            def avanzar(self, n_ticks: int) -> bool:
                for _ in range(int(n_ticks)):
                    self._k += 1
                return True
        fuente = ad.FuentePosesRobotat(R.N_AGENTES)
        canal = ad.CanalActuacionRobotat(R.N_AGENTES, fuente)
        entorno = Entorno(fuente, canal, 10)
        actual = {"k": 0}

        def un_viaje(_peticion, _n_filas):
            return np.array(matrices[min(actual["k"], len(matrices) - 1)],
                            dtype=np.float64)
        fuente._un_viaje = un_viaje
        fuente.agentes_vencidos = lambda: []
        rpm = []
        canal._enviar_crudo = (lambda i, a, b:
                               rpm.append((actual["k"], i, a, b)) or True)
        clase = ce.CoordinadorEnjambre if variante == "base" else D.CoordinadorDemo
        coord = clase(fuente=fuente, canal=canal, entorno=entorno,
                      n_agentes=R.N_AGENTES, timestep_ms=10)
        pub = None
        estado_demo = None
        if variante in ("demo_on", "demo_off"):
            pub = (P.PublicadorEstado([f"127.0.0.1:{receptor.puerto}"])
                   if variante == "demo_on" else None)
            estado_demo = D.EstadoDemo(coord, pub, "objetivos", {"episodio": 1},
                                canal, fuente, entorno, R.N_AGENTES,
                                len(matrices), 1)
            coord._demo = estado_demo
        obs = []

        def observador(d):
            obs.append((actual["k"], int(d["agente"]),
                        np.asarray(d["observacion"]).copy(),
                        np.asarray(d["accion_nominal"]).copy(),
                        np.asarray(d["accion_tras_escape"]).copy(),
                        np.asarray(d["accion_ejecutada"]).copy(),
                        int(d["en_escape"]), int(d["cbf_intervino"])))
            if estado_demo is not None:
                estado_demo.guardar_fila(d, {"en_retroceso": 0,
                                      "rpm_pico": canal.ultimo_pico_rpm})
        coord._observador_paso = observador
        canal.factor_operativo = 0.40
        try:
            self.assertTrue(coord._reiniciar_episodio(self.SEMILLA))
            for k in range(len(matrices)):
                actual["k"] = k
                coord._avanzar(coord.pasos_por_decision)
                coord._decidir_y_actuar()
            cobertura = 1.0 - float(np.mean(coord.env._field._grid_aoi))
        finally:
            import atexit
            atexit.unregister(coord._detener_seguro)
            if pub is not None:
                pub.cerrar()
        return obs, rpm, cobertura, pub

    def test_mismas_decisiones_con_y_sin_publicacion(self) -> None:
        import numpy as np
        matrices = self._matrices()
        rec = Receptor()
        with contextlib.redirect_stdout(io.StringIO()):
            base = self._correr("base", matrices)
            off = self._correr("demo_off", matrices)
            on = self._correr("demo_on", matrices, rec)
        crudos = rec.cerrar()
        self.assertGreater(len(base[0]), 0)
        for nombre, otra in (("apagada", off), ("encendida", on)):
            self.assertEqual(len(base[0]), len(otra[0]), nombre)
            for fa, fb in zip(base[0], otra[0]):
                self.assertEqual(fa[:2], fb[:2])
                for xa, xb in zip(fa[2:6], fb[2:6]):
                    self.assertTrue(np.array_equal(xa, xb), (nombre, fa[:2]))
                self.assertEqual(fa[6:], fb[6:], (nombre, fa[:2]))
            self.assertEqual(base[1], otra[1], f"rpm ({nombre})")
            self.assertEqual(base[2], otra[2], f"cobertura ({nombre})")
        # La encendida de verdad publicó: inicio + un paso por decisión.
        tipos = [json.loads(c)["tipo"] for c in crudos]
        self.assertEqual(tipos.count("paso"), len(matrices))
        self.assertEqual(tipos.count("inicio_episodio"), 1)
        self.assertEqual(on[3].errores, 0)


_REF_L2 = (_CARPETA / "resultados_demo_obstaculo" / "ensayo_campana_20261017_092424")
#: Las únicas columnas que `sesion_demo` agrega CON campaña (`cerrar_intento`).
_COLUMNAS_SOLO_CAMPANA = ("campana", "intento_campana", "incluida",
                          "motivo_inclusion")


class Prueba2Mejorada(_ConCfg):
    """(2) `mejorada`, 2 tomas × 100 decisiones con el robot 4 en el
    simulador: corre completo, los tres CSV tienen las columnas de
    `sesion_demo` (las de la sesión del ensayo 1e del 17-10 sin las cuatro
    de la campaña, en el mismo orden), el supervisor dejó traza y el 4
    recorrió su círculo. Y la publicación lleva el obstáculo."""

    def test_mejorada(self) -> None:
        rec = Receptor()
        try:
            salida = io.StringIO()
            argv = ["--modo", "mejorada", "--robot-obstaculo", "4",
                    "--simulador", "--puerto-simulador", "27800",
                    "--episodios", "2", "--decisiones", "100",
                    "--salida", str(_PRUEBAS / "p2_mejorada"),
                    "--gui", f"127.0.0.1:{rec.puerto}",
                    "--etiqueta", "prueba p2_mejorada"]
            with contextlib.redirect_stdout(salida):
                codigo = D.main(argv, preguntar=lambda _m: "")
            texto = salida.getvalue()
            (_PRUEBAS / "p2_mejorada").mkdir(parents=True, exist_ok=True)
            (_PRUEBAS / "p2_mejorada" / "consola.txt").write_bytes(
                texto.encode("utf-8"))
        finally:
            crudos = rec.cerrar()
        self.assertEqual(codigo, 0, texto[-3000:])
        carpeta = _PRUEBAS / "p2_mejorada"
        for d in ("decisiones", "obstaculo", "tomas"):
            mia = _cabecera(next(carpeta.glob(f"*_demo-mejorada_{d}.csv")))
            ref = [c for c in _cabecera(next(_REF_L2.glob(f"20261017_092425_L2_{d}.csv")))
                   if c not in _COLUMNAS_SOLO_CAMPANA]
            self.assertEqual(mia, ref, d)
        with open(next(carpeta.glob("*_demo-mejorada_tomas.csv")),
                  encoding="utf-8", newline="") as fh:
            tomas = list(csv.DictReader(fh))
        self.assertEqual(len(tomas), 2)
        self.assertTrue(all(t["valido"] == "1" for t in tomas),
                        [t.get("motivo") for t in tomas])
        for t in tomas:
            self.assertEqual(t["obst_modo"], "movil")
            com = float(t["obst_recorrido_comandado_m"])
            self.assertGreaterEqual(com, 0.20)
            self.assertGreaterEqual(float(t["obst_recorrido_m"]), 0.5 * com)
        with open(next(carpeta.glob("*_demo-mejorada_obstaculo.csv")),
                  encoding="utf-8", newline="") as fh:
            traza = list(csv.DictReader(fh))
        self.assertGreaterEqual(len(traza), 2 * 100)
        self.assertEqual({r["toma"] for r in traza}, {"1", "2"})
        self.assertIn("marcha", {r["estado"] for r in traza})
        # La publicación: lo mismo que en `objetivos`, más el obstáculo.
        msgs = [json.loads(c) for c in crudos]
        self.assertEqual([m["secuencia"] for m in msgs],
                         list(range(1, len(msgs) + 1)))
        tipos = [m["tipo"] for m in msgs]
        self.assertEqual(tipos.count("paso"),
                         sum(int(t["decisiones"]) for t in tomas))
        self.assertEqual((tipos.count("inicio_episodio"),
                          tipos.count("fin_episodio")), (2, 2))
        ini = [m for m in msgs if m["tipo"] == "inicio_episodio"][0]
        self.assertEqual(ini["obstaculo"]["centro"], [1.5, 1.5])
        self.assertEqual(ini["obstaculo"]["R"], 0.6)
        pasos = [m for m in msgs if m["tipo"] == "paso"]
        self.assertTrue(all(m["obstaculo"] and m["obstaculo"]["x"] is not None
                            for m in pasos))
        self.assertTrue(all(a["d_obst"] is not None
                            for m in pasos for a in m["agentes"]))
        fin = [m for m in msgs if m["tipo"] == "fin_episodio"]
        self.assertEqual([m["valido_demo"] for m in fin],
                         [int(t["valido_demo"]) for t in tomas])


class Prueba5BitABitObstaculo(Prueba5BitABit):
    """
    (5, mejorada) `CoordinadorDemoObstaculo` decide BIT A BIT como
    `CoordinadorConObstaculo` (F2, τ_c de la campaña), con la publicación
    encendida y apagada, ante las mismas observaciones del 30-09. El 4 está
    QUIETO en (1.5, 1.5) del env, dentro de la arena, con un supervisor
    'quieto': las filas de la barrera del obstáculo están activas.
    """

    POSE_OBST_ENV = (1.5, 1.5, 0.3)

    def _correr(self, variante: str, matrices, receptor=None):
        import numpy as np
        import adaptadores_robotat as ad
        import demo_obstaculo_movil as demo
        R = self.R

        class Entorno(ad.EntornoEjecucionRobotat):
            def avanzar(self, n_ticks: int) -> bool:
                for _ in range(int(n_ticks)):
                    self._k += 1
                return True
        fuente = demo.FuentePosesConObstaculo(R.N_AGENTES, R.ID_OBSTACULO,
                                              R.ID_OBSTACULO)
        canal = demo.CanalConObstaculo(R.N_AGENTES, fuente, R.ID_OBSTACULO,
                                       conectar_obstaculo=False)
        entorno = Entorno(fuente, canal, 10)
        actual = {"k": 0}
        o = list(R.env_a_lab(*self.POSE_OBST_ENV, R.ID_OBSTACULO))

        def un_viaje(_peticion, n_filas):
            m = [list(f) for f in matrices[min(actual["k"], len(matrices) - 1)]]
            if n_filas == R.N_AGENTES + 1:
                m.append([o[0], o[1], 0.0, math.cos(o[2] / 2), 0.0, 0.0,
                          math.sin(o[2] / 2)])
            return np.array(m, dtype=np.float64)
        fuente._un_viaje = un_viaje
        fuente.agentes_vencidos = lambda: []
        rpm = []
        canal._enviar_crudo = (lambda i, a, b:
                               rpm.append((actual["k"], i, a, b)) or True)
        supervisor = demo.SupervisorObstaculo(fuente, canal, modo="quieto",
                                              freno_activo=True)
        clase = (demo.CoordinadorConObstaculo if variante == "base"
                 else D.CoordinadorDemoObstaculo)
        coord = clase(fuente, canal, entorno, R.N_AGENTES, 10,
                      supervisor=supervisor, formulacion="F2",
                      tau_prediccion_s=demo.TAU_PREDICCION_S)
        pub = None
        estado_demo = None
        if variante in ("demo_on", "demo_off"):
            pub = (P.PublicadorEstado([f"127.0.0.1:{receptor.puerto}"])
                   if variante == "demo_on" else None)
            estado_demo = D.EstadoDemoObstaculo(
                coord, pub, "mejorada", {"episodio": 1}, canal, fuente,
                entorno, R.N_AGENTES, len(matrices), 1)
            coord._demo = estado_demo
        registro: List[Dict[str, Any]] = []
        obs_demo = demo.crear_observador(coord, canal, registro,
                                         {"episodio": 1})
        obs = []

        def observador(d):
            obs_demo(d)
            obs.append((actual["k"], int(d["agente"]),
                        np.asarray(d["observacion"]).copy(),
                        np.asarray(d["accion_nominal"]).copy(),
                        np.asarray(d["accion_tras_escape"]).copy(),
                        np.asarray(d["accion_ejecutada"]).copy(),
                        int(d["en_escape"]), int(d["cbf_intervino"])))
            if estado_demo is not None:
                estado_demo.guardar_fila(d, registro[-1])
        coord._observador_paso = observador
        canal.factor_operativo = 0.40
        # Reloj FIJADO por decisión: la F2 y el supervisor leen
        # `perf_counter` (predicción, marcha), así que sin esto ni la base es
        # igual a sí misma entre dos corridas. Avanza 0.1 s por decisión y no
        # depende de cuántas veces se lo consulte (la subclase lo consulta
        # dos veces más para medir el ciclo).
        reloj = mock.patch("time.perf_counter",
                           new=lambda: 1000.0 + 0.1 * actual["k"])
        try:
            reloj.start()
            self.assertTrue(coord._reiniciar_episodio(self.SEMILLA))
            for k in range(len(matrices)):
                actual["k"] = k
                coord._avanzar(coord.pasos_por_decision)
                coord._decidir_y_actuar()
            cobertura = 1.0 - float(np.mean(coord.env._field._grid_aoi))
            self.filas_activas = sum(1 for f in registro
                                     if f.get("h_obst_geom") not in ("", None))
        finally:
            reloj.stop()
            import atexit
            atexit.unregister(coord._detener_seguro)
            if pub is not None:
                pub.cerrar()
        return obs, rpm, cobertura, pub

    def test_mismas_decisiones_con_y_sin_publicacion(self) -> None:
        super().test_mismas_decisiones_con_y_sin_publicacion()
        self.assertGreater(self.filas_activas, 0,
                           "la barrera del obstáculo no se ejercitó")


@unittest.skipUnless(__import__("os").environ.get("DEMO_PRUEBA7") == "1",
                     "prueba 7 (~8 min, abre la ventana del panel): "
                     "DEMO_PRUEBA7=1")
class Prueba7Costo(_ConCfg):
    """
    (7) 3 episodios × 300 decisiones con `--sin-gui` y otros 3 con el panel
    abierto (ventana real, proceso aparte): `ciclo_p95_ms` de
    `_correr_episodio` no sube más de 2 ms. Escribe la tabla en
    `prueba7_costo.md`.
    """

    UMBRAL_MS = 2.0

    def _condicion(self, nombre: str, extra: List[str], puerto: int):
        codigo, texto = self._correr(
            nombre, ["--episodios", "3", "--decisiones", "300"] + extra, puerto)
        self.assertEqual(codigo, 0, texto[-3000:])
        eps = self._episodios(nombre)
        self.assertTrue(all(e["valido"] == "1" for e in eps),
                        [e.get("motivo") for e in eps])
        return [float(e["ciclo_p95_ms"]) for e in eps]

    def test_costo_del_panel(self) -> None:
        import os
        import statistics
        import subprocess
        hz = os.environ.get("DEMO_PRUEBA7_HZ", "10")
        # DEMO_PRUEBA7_BASE_MS: sólo la condición con panel (p. ej. otro
        # ritmo del panel), contra la media sin GUI de una corrida completa
        # anterior en las MISMAS condiciones de la máquina.
        base = os.environ.get("DEMO_PRUEBA7_BASE_MS")
        if base:
            sin, pub = [float(base)], []
        else:
            sin = self._condicion("p7_sin_gui", ["--sin-gui"], 27700)
            # Publicando a un puerto donde nadie escucha: el costo de
            # publicar solo, sin el panel compitiendo por CPU.
            pub = self._condicion("p7_publica_sin_panel",
                                  ["--gui", "127.0.0.1:27311"], 27740)
        panel = subprocess.Popen(
            [sys.executable, str(_CARPETA / "panel_demo.py"), "--puerto",
             "27310", "--hz", hz], cwd=str(_CARPETA), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        try:
            time.sleep(4.0)
            self.assertIsNone(panel.poll(), "el panel no arrancó")
            con = self._condicion("p7_con_panel",
                                  ["--gui", "127.0.0.1:27310"], 27720)
            vivo = panel.poll() is None
        finally:
            panel.terminate()
            salida_panel = panel.communicate(timeout=10)[0].decode(
                "utf-8", "replace").replace(chr(13), "")
        self.assertTrue(vivo, "el panel se cayó durante la corrida")
        m_sin, m_con = statistics.mean(sin), statistics.mean(con)
        m_pub = statistics.mean(pub) if pub else float("nan")
        tabla = [
            "# Prueba 7: costo del panel sobre el lazo (demostración, no citable)",
            "", f"{datetime.now():%Y-%m-%d %H:%M}, simulador local, 3 × 300 "
            "decisiones por condición, colocación automática. El panel corre "
            f"en otro proceso con prioridad bajo lo normal, a {hz} Hz.", "",
            "| condición | ciclo_p95_ms ep 1 | ep 2 | ep 3 | media |",
            "|---|---|---|---|---|",
            ("| sin GUI | " + " | ".join(f"{x:.2f}" for x in sin)
             + f" | {m_sin:.2f} |") if not base else
            f"| sin GUI (de la corrida anterior) | — | — | — | {m_sin:.2f} |",
            ("| publica, sin panel | " + " | ".join(f"{x:.2f}" for x in pub)
             + f" | {m_pub:.2f} |") if pub else
            "| publica, sin panel | — | — | — | — |",
            "| panel abierto | " + " | ".join(f"{x:.2f}" for x in con)
            + f" | {m_con:.2f} |", "",
            f"Diferencia de medias: {m_con - m_sin:+.2f} ms (umbral "
            f"+{self.UMBRAL_MS:.0f} ms).", "", "Panel: "
            + (salida_panel.strip().splitlines() or ["(sin salida)"])[-1], ""]
        (_PRUEBAS / "prueba7_costo.md").write_bytes(
            "\n".join(tabla).encode("utf-8"))
        print("\n" + "\n".join(tabla))
        self.assertLessEqual(m_con - m_sin, self.UMBRAL_MS)

    @unittest.skipUnless(__import__("os").environ.get("DEMO_PRUEBA7_RONDAS"),
                         "variante intercalada: DEMO_PRUEBA7_RONDAS=<n>")
    def test_costo_intercalado(self) -> None:
        """
        Las tres condiciones ALTERNADAS: en cada ronda, un episodio de 300
        decisiones por condición, con el orden rotado ronda a ronda, para que
        la deriva de la máquina (carga, frecuencia, carga de la batería) no
        caiga entera sobre una condición. Se compara PAREADO dentro de cada
        ronda. Cada sesión arranca un simulador nuevo con los robots en sus
        poses de arranque (`--colocacion actual`): la colocación no cambia lo
        que se mide, que es el ciclo DENTRO del episodio.
        """
        import os
        import statistics
        import subprocess
        rondas = int(os.environ["DEMO_PRUEBA7_RONDAS"])
        condiciones = ("sin_gui", "publica_sin_panel", "con_panel")
        res: Dict[str, List[float]] = {c: [] for c in condiciones}
        orden_total: List[str] = []
        puerto = 28000
        for r in range(rondas):
            orden = condiciones[r % 3:] + condiciones[:r % 3]
            for c in orden:
                puerto += 20
                nombre = f"p7i_r{r + 1}_{c}"
                extra = ["--episodios", "1", "--decisiones", "300",
                         "--colocacion", "actual"]
                panel = None
                if c == "sin_gui":
                    extra += ["--sin-gui"]
                elif c == "publica_sin_panel":
                    extra += ["--gui", "127.0.0.1:27311"]
                else:
                    extra += ["--gui", "127.0.0.1:27310"]
                    panel = subprocess.Popen(
                        [sys.executable, str(_CARPETA / "panel_demo.py"),
                         "--puerto", "27310"], cwd=str(_CARPETA),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(4.0)
                    self.assertIsNone(panel.poll(), "el panel no arrancó")
                try:
                    codigo, texto = self._correr(nombre, extra, puerto)
                    vivo = panel is None or panel.poll() is None
                finally:
                    if panel is not None:
                        panel.terminate()
                        panel.wait(10)
                self.assertEqual(codigo, 0, texto[-3000:])
                self.assertTrue(vivo, "el panel se cayó")
                ep = self._episodios(nombre)
                self.assertEqual([e["valido"] for e in ep], ["1"])
                res[c].append(float(ep[0]["ciclo_p95_ms"]))
                orden_total.append(c)
        d_panel = [p - s for p, s in zip(res["con_panel"], res["sin_gui"])]
        d_pub = [p - s for p, s in zip(res["publica_sin_panel"], res["sin_gui"])]
        L = ["# Prueba 7 intercalada: costo del panel sobre el lazo "
             "(demostración, no citable)", "",
             f"{datetime.now():%Y-%m-%d %H:%M}, simulador local, {rondas} "
             "rondas; en cada una, 1 episodio × 300 decisiones por condición, "
             "orden rotado ronda a ronda. Panel en otro proceso, 10 Hz, "
             "prioridad bajo lo normal.", "",
             "| ronda | orden | sin GUI | publica, sin panel | panel abierto "
             "| panel − sin GUI | publica − sin GUI |",
             "|---|---|---|---|---|---|---|"]
        for r in range(rondas):
            orden = condiciones[r % 3:] + condiciones[:r % 3]
            L.append(f"| {r + 1} | {' → '.join(orden)} | {res['sin_gui'][r]:.2f} "
                     f"| {res['publica_sin_panel'][r]:.2f} "
                     f"| {res['con_panel'][r]:.2f} | {d_panel[r]:+.2f} "
                     f"| {d_pub[r]:+.2f} |")
        L += ["", f"Medias: sin GUI {statistics.mean(res['sin_gui']):.2f} ms, "
              f"publica {statistics.mean(res['publica_sin_panel']):.2f} ms, "
              f"panel {statistics.mean(res['con_panel']):.2f} ms.",
              f"Diferencia pareada panel − sin GUI: media "
              f"{statistics.mean(d_panel):+.2f} ms (de {min(d_panel):+.2f} a "
              f"{max(d_panel):+.2f}); umbral +{self.UMBRAL_MS:.0f} ms.",
              f"Diferencia pareada publica − sin GUI: media "
              f"{statistics.mean(d_pub):+.2f} ms (de {min(d_pub):+.2f} a "
              f"{max(d_pub):+.2f}).", ""]
        (_PRUEBAS / "prueba7_intercalada.md").write_bytes(
            "\n".join(L).encode("utf-8"))
        print("\n" + "\n".join(L))
        self.assertLessEqual(statistics.mean(d_panel), self.UMBRAL_MS)


if __name__ == "__main__":
    unittest.main()
