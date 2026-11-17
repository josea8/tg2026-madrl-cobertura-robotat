"""
test_cerrojo_fuente_poses.py
============================
Pruebas del cerrojo de `FuentePosesRobotat` (2026-09-24).

⚠ CAMBIO SEPARADO, declarado como tal: NO es la corrección de los
congelamientos de borde del 22 y 24 de septiembre, y no debe atribuírsele si
el síntoma no reaparece en la próxima sesión. Aquellos ocurrieron a mitad de
episodio, con un solo hilo consultando, en UNA fila de respuestas cuyas otras
filas seguían vivas; un cruce de respuestas desordena la respuesta entera.
Ver BITACORA_TECNICA, "Cerrojo en la fuente de poses".

La carrera que sí cierra: el latido de la guía de colocación y el hilo
principal usan la misma fuente, y al latido se lo espera con
`join(timeout=2.0)`. Sin cerrojo, dos consultas podían compartir el socket.

    python test_cerrojo_fuente_poses.py

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import sys
import threading
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

_CARPETA = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import config_robotat as cfg
import test_diagnostico_poses as tdp       # sólo sus ayudantes (tdp.X)
from adaptadores_robotat import FuentePosesRobotat


def _respuesta_viva(n: int, pld: List[int]) -> bytes:
    """Poses que cambian un poco en cada petición, en el orden pedido."""
    posiciones = {1: (-0.5, 0.2), 5: (0.5, -0.3)}
    return tdp.respuesta(*[tdp.fila(posiciones[m][0] + 1e-4 * n,
                                    posiciones[m][1], 0.2) for m in pld])


class PruebaCerrojoDeLaFuente(unittest.TestCase):

    def test_dos_hilos_no_cruzan_sus_consultas(self) -> None:
        """
        Dos hilos consultando a la vez la MISMA fuente, contra un servidor
        que tarda 10 ms en cada respuesta: con el cerrojo, cada consulta
        vuelve completa, ninguna falla y el servidor ve exactamente una
        petición por consulta.
        """
        errores: List[BaseException] = []
        resultados: List[Dict[int, np.ndarray]] = []
        cerrojo_res = threading.Lock()
        with tdp.ConfigAislada(), tdp.ServidorGuionado(
                _respuesta_viva, demora_s=0.01) as srv:
            tdp._dos_agentes(srv.puerto)
            cfg.TIMEOUT_POSES_S = 0.5
            fuente = FuentePosesRobotat(2)
            with contextlib.redirect_stdout(io.StringIO()):
                fuente.conectar()

            def consultar() -> None:
                try:
                    for _ in range(15):
                        r = fuente.leer_poses_ya()
                        with cerrojo_res:
                            resultados.append(r)
                except BaseException as exc:                   # noqa: BLE001
                    errores.append(exc)

            hilos = [threading.Thread(target=consultar) for _ in range(2)]
            for h in hilos:
                h.start()
            for h in hilos:
                h.join(timeout=20.0)
            with contextlib.redirect_stdout(io.StringIO()):
                fuente.cerrar()
            peticiones = len(srv.peticiones)
        self.assertEqual(errores, [])
        self.assertEqual(len(resultados), 30)
        self.assertEqual(fuente.fallos_consulta, 0)
        self.assertEqual(peticiones, 30)
        for r in resultados:
            self.assertEqual(sorted(r), [0, 1])
            # cada fila es la de su marcador: nada cruzado
            self.assertLess(abs(float(r[0][0]) - (1.5 - 0.5)), 0.01)
            self.assertLess(abs(float(r[1][0]) - (1.5 + 0.5)), 0.01)

    def test_una_consulta_espera_a_la_que_esta_en_curso(self) -> None:
        """
        Con el cerrojo tomado —como lo tendría un latido a mitad de una
        consulta—, otra consulta no toca el socket hasta que se suelte.
        """
        with tdp.ConfigAislada(), tdp.ServidorGuionado(_respuesta_viva) as srv:
            tdp._dos_agentes(srv.puerto)
            fuente = FuentePosesRobotat(2)
            with contextlib.redirect_stdout(io.StringIO()):
                fuente.conectar()
            salida: Dict[str, Any] = {}
            fuente._cerrojo.acquire()
            try:
                h = threading.Thread(
                    target=lambda: salida.update(r=fuente.leer_poses_ya()))
                h.start()
                time.sleep(0.2)
                self.assertTrue(h.is_alive())
                self.assertEqual(len(srv.peticiones), 0)
            finally:
                fuente._cerrojo.release()
            h.join(timeout=5.0)
            self.assertFalse(h.is_alive())
            self.assertEqual(sorted(salida["r"]), [0, 1])
            self.assertEqual(len(srv.peticiones), 1)
            with contextlib.redirect_stdout(io.StringIO()):
                fuente.cerrar()

    def test_con_un_solo_hilo_es_igual_que_sin_cerrojo(self) -> None:
        """
        Contra el mismo guion de siete respuestas de la prueba de
        equivalencia del registro, la fuente con cerrojo da exactamente lo
        mismo que la de antes del cerrojo.
        """
        try:
            antes = importlib.import_module(
                "adaptadores_robotat_respaldo_20260924_preCerrojo")
        except ImportError:
            self.skipTest("no está el respaldo previo al cerrojo")
        prueba = tdp.PruebaApagadoNoCambiaNada()
        tmp = Path(".")        # sin registro: no escribe nada
        con = prueba._correr(FuentePosesRobotat, False, tmp)
        sin = prueba._correr(antes.FuentePosesRobotat, False, tmp)
        self._comparar(con, sin)

    def _comparar(self, a: Dict[str, Any], b: Dict[str, Any]) -> None:
        self.assertEqual(a["contadores"], b["contadores"])
        self.assertEqual(a["peticiones"], b["peticiones"])
        self.assertEqual(len(a["salidas"]), len(b["salidas"]))
        for sa, sb in zip(a["salidas"], b["salidas"]):
            self.assertEqual(sorted(sa), sorted(sb))
            for k in sa:
                np.testing.assert_array_equal(sa[k], sb[k])


if __name__ == "__main__":
    unittest.main(verbosity=2)
