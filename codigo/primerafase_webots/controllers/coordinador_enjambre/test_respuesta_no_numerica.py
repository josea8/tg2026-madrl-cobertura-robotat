"""
test_respuesta_no_numerica.py
=============================
Una respuesta del servidor con algo que no es número dentro de la lista (un
texto, un objeto, listas de largos distintos) es una consulta FALLIDA, no una
excepción que tire la sesión.

⚠ CAMBIO SEPARADO (2026-09-24), declarado como tal y no relacionado con los
congelamientos de borde: nunca se observó en el laboratorio. Lo encontró la
auditoría al comparar `diagnosticar_respuesta` con
`decodificar_respuesta_poses`, que dejaba subir el `ValueError` de numpy.
Ver BITACORA_TECNICA, "Respuesta no numérica del servidor".

    python test_respuesta_no_numerica.py

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path
from typing import List

_CARPETA = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import config_robotat as cfg
import test_diagnostico_poses as tdp       # sólo sus ayudantes (tdp.X)
from adaptadores_robotat import FuentePosesRobotat
from diagnostico_poses import diagnosticar_respuesta
from protocolo_robotat import decodificar_respuesta_poses

NO_NUMERICAS = [
    b'[0.3, "a", 0.05, 1.0, 0.0, 0.0, 0.0]',          # texto
    b'[0.3, {"x": 1}, 0.05, 1.0, 0.0, 0.0, 0.0]',      # objeto
    b"[[0.3, -0.2], [0.05, 1.0, 0.0, 0.0, 0.0]]",      # largos distintos
]


class PruebaRespuestaNoNumerica(unittest.TestCase):

    def test_decodificar_devuelve_none_y_no_lanza(self) -> None:
        for datos in NO_NUMERICAS:
            with self.subTest(datos=datos):
                self.assertIsNone(decodificar_respuesta_poses(datos, 1))
                _m, causa, _d = diagnosticar_respuesta(datos, 1)
                self.assertEqual(causa, "valor_no_numerico")

    def test_la_fuente_la_cuenta_como_consulta_fallida(self) -> None:
        """
        Contra un servidor que contesta una lista con un texto adentro: la
        fuente devuelve `{}`, cuenta una consulta fallida y la siguiente
        consulta, normal, funciona. Antes: `ValueError` hasta la sesión.
        """
        def responder(n: int, pld: List[int]) -> bytes:
            if n == 1:
                return NO_NUMERICAS[0]
            return tdp.respuesta(*[tdp.fila(0.1 * m, 0.2) for m in pld])

        with tdp.ConfigAislada(), tdp.ServidorGuionado(responder) as srv:
            tdp._dos_agentes(srv.puerto)
            cfg.TIMEOUT_POSES_S = 0.2
            fuente = FuentePosesRobotat(2)
            with contextlib.redirect_stdout(io.StringIO()):
                fuente.conectar()
                primera = fuente.leer_poses_ya()
                segunda = fuente.leer_poses_ya()
                fuente.cerrar()
        self.assertEqual(primera, {})
        self.assertEqual(fuente.fallos_consulta, 1)
        self.assertEqual(sorted(segunda), [0, 1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
