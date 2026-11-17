"""
lanzar_robotat.py
=================
Punto de entrada del despliegue físico: arma los adaptadores del Robotat,
hace los chequeos previos, y le entrega el control al MISMO
`CoordinadorEnjambre` que corre en Webots.

    python lanzar_robotat.py --simulador     # ensayo local, sin hardware
    python lanzar_robotat.py                 # laboratorio

Chequeos previos (antes de energizar nada)
------------------------------------------
1. Imprime la versión de la interfaz y el resumen de calibración, con las
   marcas `⚠ NO VERIFICADO` bien visibles.
2. Se NIEGA a arrancar si queda algún parámetro sin verificar. Con `--forzar`
   arranca igual, pero deja el aviso en el log — es para las pruebas de
   calibración de la primera sesión, donde por definición nada está
   verificado todavía.
3. Comprueba que los adaptadores cumplen los tres `Protocol`.
4. Conecta primero las POSES y después las RUEDAS: si la mocap no está, no
   se abre ni un socket hacia un robot.

⚠ Ver README_ROBOTAT.md §S1: la parada por software NO es una parada de
emergencia. Tiene que haber alguien mirando la arena con acceso al corte de
alimentación.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import argparse
import atexit
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import config_robotat as cfg
from adaptadores_robotat import (
    CanalActuacionRobotat,
    EntornoEjecucionRobotat,
    FuentePosesRobotat,
    revisar_poses_iniciales,
)
from interfaces import CanalActuacion, EntornoEjecucion, FuentePoses

VERSION_INTERFAZ: str = "1.1"   # 1.0 = Fase 1 (Webots); 1.1 = + Robotat

# El lazo decide cada 100 ms y el reloj corre a 10 ms, igual que en Webots.
TIMESTEP_MS: int = 10


def _sin_verificar() -> List[str]:
    """Nombres de los parámetros de calibración todavía sin medir."""
    pendientes: List[str] = []
    if cfg.ESCALA_NO_VERIFICADA:
        pendientes.append("ESCALA_POSICION (README §C1)")
    if cfg.MARCO_NO_VERIFICADO:
        pendientes.append("ROTACION_MARCO / TRASLACION (README §C2)")
    if cfg.HEADING_NO_VERIFICADO:
        pendientes.append("OFFSET_HEADING_RAD (README §C3)")
    if cfg.GEOMETRIA_NO_VERIFICADA:
        pendientes.append("RADIO_RUEDA_M / MEDIO_EJE_M (README §C4)")
    if cfg.MAPEO_NO_VERIFICADO:
        pendientes.append("MAPEO_AGENTES (README §C5 / verificar_mapeo_ids.py)")
    return pendientes


def chequeos_previos(forzar: bool) -> bool:
    """Imprime el estado y decide si se puede arrancar."""
    print("=" * 72)
    print(f"PUENTE AL ROBOTAT — interfaz v{VERSION_INTERFAZ}")
    print("=" * 72)
    for linea in cfg.resumen_calibracion():
        print(linea)
    print("-" * 72)

    pendientes = _sin_verificar()
    if not pendientes:
        print("Toda la calibración está verificada.")
        return True

    print("⚠ PARÁMETROS SIN VERIFICAR:")
    for p in pendientes:
        print(f"    · {p}")
    if forzar:
        print("\n--forzar: se arranca igual. Los robots se van a mover con")
        print("          parámetros sin calibrar. Usalo SÓLO para las")
        print("          pruebas de calibración de la primera sesión.")
        return True
    print("\nNO se arranca. Corré los procedimientos del README, poné los")
    print("flags *_NO_VERIFICADO en False, o usá --forzar si estás calibrando.")
    return False


def construir(n_agentes: int):
    """
    Arma los tres adaptadores y los conecta. Poses primero: si la mocap no
    responde, no se abre ningún socket hacia un robot.
    """
    # Sin `obtener_tick`: el reloj se lo instala `EntornoEjecucionRobotat`,
    # que es quien cuenta los ticks del lazo.
    fuente = FuentePosesRobotat(n_agentes)
    fuente.conectar()

    canal = CanalActuacionRobotat(n_agentes, fuente)
    try:
        canal.conectar()
    except OSError:
        fuente.cerrar()
        raise

    entorno = EntornoEjecucionRobotat(fuente, canal, TIMESTEP_MS)

    for obj, protocolo in ((fuente, FuentePoses), (canal, CanalActuacion),
                           (entorno, EntornoEjecucion)):
        if not isinstance(obj, protocolo):
            raise TypeError(
                f"{type(obj).__name__} no cumple {protocolo.__name__}."
            )
    return fuente, canal, entorno


def leer_poses_estables(
    fuente: FuentePosesRobotat,
    n_agentes: int,
    plazo_s: float = 3.0,
) -> Dict[int, np.ndarray]:
    """
    Junta una pose válida de cada agente, sondeando hasta `plazo_s`.

    Devuelve lo que haya conseguido: la decisión de arrancar o no la toma
    `chequeo_de_arranque`, que sabe nombrar a los que faltan.
    """
    ultimas: Dict[int, np.ndarray] = {}
    limite = time.perf_counter() + plazo_s
    while time.perf_counter() < limite:
        for i, medida in fuente.leer_poses():
            ultimas[i] = medida.pose
        if len(ultimas) == n_agentes:
            break
        time.sleep(0.02)
    return ultimas


def chequeo_de_arranque(
    fuente: FuentePosesRobotat,
    n_agentes: int,
    forzar: bool,
) -> bool:
    """
    Chequeo geométrico ANTES de la primera acción. Si algo no cierra, no se
    arranca: es más barato mover un robot a mano que perseguirlo.
    """
    print("-" * 72)
    print("CHEQUEO DE ARRANQUE")
    poses = leer_poses_estables(fuente, n_agentes)
    for i in sorted(poses):
        x, y, th = poses[i]
        print(f"  agente {i}: ({x:.3f}, {y:.3f}) m  "
              f"θ={np.degrees(th):+7.1f}°")

    problemas = revisar_poses_iniciales(poses, n_agentes)
    if not problemas:
        print("✔ Las poses iniciales permiten arrancar.")
        return True

    print("\n✘ NO SE PUEDE ARRANCAR:")
    for p in problemas:
        print(f"    · {p}")
    if forzar:
        print("\n--forzar: se arranca igual. Mirá la arena.")
        return True
    print("\nCorregí lo de arriba (mover robots a mano, o recalibrar) y "
          "volvé a correr.")
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--simulador", action="store_true",
                    help="correr contra el simulador local, sin hardware")
    ap.add_argument("--forzar", action="store_true",
                    help="arrancar aunque falte calibración o el chequeo "
                         "geométrico falle")
    ap.add_argument("--sin-arranque-seguro", action="store_true",
                    dest="sin_arranque_seguro",
                    help="⚠ velocidad plena desde el primer tick")
    ap.add_argument("--agentes", type=int, default=len(cfg.MAPEO_AGENTES))
    args = ap.parse_args()

    if args.simulador:
        cfg.activar_simulador_local()
        print("[lanzador] modo SIMULADOR: no hay hardware involucrado.")
    if args.sin_arranque_seguro:
        cfg.ARRANQUE_SEGURO = False

    if not chequeos_previos(args.forzar):
        return 2

    fuente, canal, entorno = construir(args.agentes)

    # Watchdog: cualquier salida —normal, excepción, Ctrl-C— frena los
    # robots. Es el mismo camino que el coordinador registra en Webots; acá
    # se registra ANTES de construirlo, porque los sockets ya están abiertos.
    atexit.register(canal.detener_todo)

    # Chequeo geométrico DESPUÉS de conectar (necesita poses) y ANTES de
    # construir el coordinador, que es lo primero que puede mandar una acción.
    if not chequeo_de_arranque(fuente, args.agentes, args.forzar):
        entorno.finalizar(3)
        return 3

    codigo = 0
    try:
        from coordinador_enjambre import CoordinadorEnjambre
        coordinador = CoordinadorEnjambre(
            fuente      = fuente,
            canal       = canal,
            entorno     = entorno,
            n_agentes   = args.agentes,
            timestep_ms = TIMESTEP_MS,
        )
        coordinador.correr()
    except KeyboardInterrupt:
        print("\n[lanzador] interrumpido por el usuario.")
        codigo = 130
    except Exception as exc:                                   # noqa: BLE001
        print(f"\n[lanzador] error: {type(exc).__name__}: {exc}")
        codigo = 1
        raise
    finally:
        try:
            entorno.finalizar(codigo)
        except Exception as exc:                               # noqa: BLE001
            print(f"[lanzador] cierre con problemas: {exc}")
            canal.detener_todo()
    return codigo


if __name__ == "__main__":
    sys.exit(main())
