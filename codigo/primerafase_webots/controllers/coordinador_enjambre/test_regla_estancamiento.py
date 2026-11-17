"""
test_regla_estancamiento.py
===========================
Pruebas de la regla "sin desplazamiento por 10 s" de
`sesion_robotat._correr_episodio`, arreglada el 2026-10-02 con el OK de José
(ver tesis/PROPUESTA_regla_estancamiento.md): el reloj arranca en el inicio
de la orden SOSTENIDA + `MARGEN_RETARDO_ESTANCAMIENTO_S`, no en el último
desplazamiento, y la orden se da por terminada sólo tras
`CORTE_ORDEN_ESTANCAMIENTO_S` seguidos sin orden.

Corren el lazo REAL de la evaluación (`_correr_episodio`, vía
`demo_obstaculo_movil.correr_toma(lazo="evaluacion")`) contra
`SimuladorRobotat` con 6 robots y 0.45 s de retardo. Para aislar la regla del
`DetectorSeguimiento` (que con un robot trabado corta antes, a los 5 s), las
pruebas del robot trabado lo reemplazan por uno que nunca juzga.

    python -m unittest test_regla_estancamiento -v

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import threading
import time
import unittest

import numpy as np

import demo_obstaculo_movil as demo
import sesion_robotat as ses
import test_demo_obstaculo_movil as base


class _SinSeguimiento:
    """`DetectorSeguimiento` que nunca acusa (aísla la regla de 10 s)."""

    def reiniciar(self) -> None:
        pass

    def observar(self, *_a, **_k) -> bool:
        return False


class PruebaReglaEstancamiento(base.BaseSim):

    def _armar_y_correr(self, mando, decisiones: int, trabar: bool,
                        sin_seguimiento: bool):
        p0, r0 = demo.punto_del_circulo(-demo.math.pi / 2)
        poses = self.poses_lejos()
        poses[0] = (0.5, 1.2, 0.0)             # lejos del círculo y de los demás
        self.levantar_sim(poses, (p0[0], p0[1], r0))
        fuente, canal, entorno, sup, coord, reg = self.armar()
        robot0 = self.robots[0]
        parar = threading.Event()

        def clavar() -> None:
            x, y, _ = self.sim.pose_de_robot(robot0)
            while not parar.is_set():
                with self.sim._lock:
                    est = self.sim.robots[robot0]
                    est.x, est.y = x, y
                time.sleep(0.002)

        hilo = threading.Thread(target=clavar, daemon=True)
        if trabar:
            hilo.start()

        def nominal(i, pose_i, pose_o):
            if i != 0:
                return np.array([0.0, 0.0], dtype=np.float32)
            return np.asarray(mando(coord._paso_episodio), dtype=np.float32)
        coord.instalar_nominal_forzada(nominal)
        try:
            with base._silencio():
                res = demo.correr_toma(
                    coord, canal, fuente, entorno, 420000, decisiones, reg,
                    lazo="evaluacion",
                    seguimiento=_SinSeguimiento() if sin_seguimiento else None)
        finally:
            parar.set()
        return res

    def test_constantes_del_arreglo(self) -> None:
        self.assertEqual(ses.MARGEN_RETARDO_ESTANCAMIENTO_S, 1.0)
        self.assertEqual(ses.CORTE_ORDEN_ESTANCAMIENTO_S, 1.0)

    def test_quieto_12_s_y_despues_huye_no_corta(self) -> None:
        """El caso de la demo: quieto y sin orden 12 s, después se le ordena
        moverse. Con la regla vieja cortaba en la decisión 120."""
        res = self._armar_y_correr(
            lambda paso: (0.0, 0.0) if paso < 120 else (0.15, 0.0),
            decisiones=150, trabar=False, sin_seguimiento=False)
        self.assertEqual(res["valido"], 1, res.get("motivo"))

    def test_trabado_con_orden_sostenida_corta(self) -> None:
        res = self._armar_y_correr(lambda paso: (0.15, 0.0), decisiones=140,
                                   trabar=True, sin_seguimiento=True)
        self.assertEqual(res["valido"], 0)
        self.assertIn("sin desplazamiento por 10 s", res["motivo"])
        # 10 s + el margen de 1 s, con la tolerancia del reloj de pared.
        self.assertGreaterEqual(res["decisiones"], 105)
        self.assertLessEqual(res["decisiones"], 125)

    def test_trabado_con_filtro_que_parpadea_corta(self) -> None:
        res = self._armar_y_correr(
            lambda paso: (0.15, 0.0) if paso % 5 < 3 else (0.0, 0.0),
            decisiones=140, trabar=True, sin_seguimiento=True)
        self.assertEqual(res["valido"], 0)
        self.assertIn("sin desplazamiento por 10 s", res["motivo"])

    def test_orden_cortada_mas_de_1_s_reinicia_el_reloj(self) -> None:
        """Trabado, orden 6 s, 1.5 s sin orden, orden otra vez: el reloj
        vuelve a empezar y en 14 s no corta (la regla vieja cortaba a los
        10 s del último desplazamiento)."""
        def mando(paso):
            return (0.0, 0.0) if 60 <= paso < 75 else (0.15, 0.0)
        res = self._armar_y_correr(mando, decisiones=140, trabar=True,
                                   sin_seguimiento=True)
        self.assertEqual(res["valido"], 1, res.get("motivo"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
