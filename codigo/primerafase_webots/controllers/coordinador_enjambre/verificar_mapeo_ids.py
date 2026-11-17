"""
verificar_mapeo_ids.py
======================
Comprueba, moviendo un robot a la vez, que `config_robotat.MAPEO_AGENTES`
asocia cada robot con SU marcador.

Por qué hace falta
------------------
El servidor de captura identifica MARCADORES (1–100) y los robots se
direccionan por ID de ROBOT (0–19). Son espacios independientes: nada en el
código de referencia los relaciona. Si el mapeo está cruzado, el sistema NO
falla — se comporta mal: cada robot ejecuta las órdenes calculadas a partir
de la pose de otro. El síntoma (el enjambre no cubre nada) es
indistinguible de "la política no sirve", que es justo el diagnóstico que
esta tesis necesita poder hacer con confianza.

Cómo lo hace
------------
Para cada agente: gira SU robot sobre el eje —sin traslación, así no se sale
de su lugar ni choca— y mira CUÁL de todos los marcadores configurados
cambió de heading. Ese marcador debe ser el que declara el mapeo.

Se usa rotación pura, no avance, por dos razones: es segura (el robot no se
desplaza) y el Δyaw es insensible al offset de heading sin calibrar, que en
la primera sesión todavía no se conoce.

Este script NO usa `FuentePosesRobotat`: esa clase ya aplica el mapeo que
estamos poniendo a prueba. Habla el protocolo directo, indexando por
marcador.

Uso
---
    python verificar_mapeo_ids.py                 # contra el Robotat
    python verificar_mapeo_ids.py --simulador     # contra el simulador local

⚠ SEGURIDAD: mueve robots reales. Baja velocidad (≈1 rad/s) y giro en el
lugar, pero alguien debe estar mirando la arena y con acceso al corte de
alimentación. Ver README §S1.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import argparse
import math
import socket
import sys
import time
from typing import Dict, List, NamedTuple, Optional, Tuple

import config_robotat as cfg
from protocolo_robotat import (
    accion_a_rpm,
    codificar_peticion_poses,
    codificar_velocidades_rueda,
    decodificar_respuesta_poses,
    heading_desde_cuaternion,
)

# Parámetros de la maniobra de prueba.
OMEGA_PRUEBA_RAD_S: float = 1.0    # giro en el lugar, sin traslación
DURACION_GIRO_S:    float = 1.2    # ⇒ ≈ 69° de rotación esperada
UMBRAL_MOVIDO_RAD:  float = 0.30   # ≈ 17°, muy por encima del ruido
PAUSA_ENTRE_ROBOTS_S: float = 0.5


class ResultadoVerificacion(NamedTuple):
    """Veredicto para un agente."""

    agente:            int
    id_robot:          int
    marcador_esperado: int
    marcador_movido:   Optional[int]
    giros:             Dict[int, float]   # marcador → |Δyaw| observado
    veredicto:         str                # OK | CRUZADO | NADIE | AMBIGUO


class _ClientePoses:
    """Cliente mínimo del servidor de poses, indexado por MARCADOR."""

    def __init__(self, marcadores: List[int]) -> None:
        from adaptadores_robotat import esperar_saludo_inicial
        self._marcadores = list(marcadores)
        self._peticion = codificar_peticion_poses(self._marcadores)
        host, puerto = cfg.endpoint_poses()
        self._sock = socket.create_connection((host, puerto),
                                              timeout=cfg.TIMEOUT_CONEXION_S)
        self._sock.settimeout(cfg.TIMEOUT_POSES_S)
        esperar_saludo_inicial(self._sock)

    def headings(self) -> Optional[Dict[int, float]]:
        """{marcador: yaw} o None si la respuesta no sirve."""
        t0 = time.perf_counter()
        try:
            from adaptadores_robotat import descartar_buffer_pendiente
            descartar_buffer_pendiente(self._sock)
            self._sock.sendall(self._peticion)
            crudo = b""
            while True:
                trozo = self._sock.recv(4096)
                if not trozo:
                    return None
                crudo += trozo
                m = decodificar_respuesta_poses(crudo, len(self._marcadores))
                if m is not None:
                    break
                if time.perf_counter() - t0 > cfg.TIMEOUT_POSES_S:
                    return None
        except OSError:
            return None
        salida: Dict[int, float] = {}
        for k, marcador in enumerate(self._marcadores):
            fila = m[k]
            yaw, _ = heading_desde_cuaternion(
                float(fila[3]), float(fila[4]), float(fila[5]), float(fila[6])
            )
            salida[marcador] = yaw
        return salida

    def cerrar(self) -> None:
        try:
            self._sock.sendall(b"EXIT")
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass


def _abrir_robots(ids_robot: List[int]) -> Dict[int, socket.socket]:
    """Un socket por robot. Cierra todo y relanza si alguno falla."""
    socks: Dict[int, socket.socket] = {}
    try:
        for id_robot in ids_robot:
            host, puerto = cfg.endpoint_robot(id_robot)
            s = socket.create_connection((host, puerto),
                                         timeout=cfg.TIMEOUT_CONEXION_S)
            socks[id_robot] = s
    except OSError:
        for s in socks.values():
            s.close()
        raise
    return socks


def _mandar(sock: socket.socket, v: float, omega: float) -> None:
    """Convierte y envía. El orden de ruedas lo resuelve `protocolo_robotat`."""
    rpm_izq, rpm_der, _ = accion_a_rpm(
        v, omega, cfg.RADIO_RUEDA_M, cfg.MEDIO_EJE_M
    )
    sock.sendall(codificar_velocidades_rueda(rpm_izq, rpm_der))


def _delta_angular(a: float, b: float) -> float:
    """|a − b| envuelto a [0, π]."""
    return abs(math.atan2(math.sin(a - b), math.cos(a - b)))


def verificar(
    n_agentes: int,
    verboso:   bool = True,
    pares:     Optional[List[Tuple[int, int]]] = None,
) -> List[ResultadoVerificacion]:
    """
    Corre la verificación completa. Detiene TODOS los robots al terminar,
    pase lo que pase.

    Parámetros
    ----------
    n_agentes : cuántos agentes verificar, usando `cfg.MAPEO_AGENTES`.
    pares     : alternativa explícita `[(id_marcador, id_robot), ...]`, para
                verificar un robot que no está en el mapeo por defecto — es
                lo que usa la etapa 1 de `sesion_robotat.py`, donde el robot
                de la sesión se elige por línea de comandos. Si se da, se
                ignora `n_agentes`.
    """
    if pares is not None:
        marcadores = [m for m, _ in pares]
        robots     = [r for _, r in pares]
    else:
        marcadores = [cfg.MAPEO_AGENTES[i].id_marcador
                      for i in range(n_agentes)]
        robots     = [cfg.MAPEO_AGENTES[i].id_robot
                      for i in range(n_agentes)]
    n_agentes = len(marcadores)

    poses = _ClientePoses(marcadores)
    socks = _abrir_robots(robots)
    resultados: List[ResultadoVerificacion] = []

    try:
        for i in range(n_agentes):
            id_robot = robots[i]
            esperado = marcadores[i]

            antes = poses.headings()
            if antes is None:
                resultados.append(ResultadoVerificacion(
                    i, id_robot, esperado, None, {}, "NADIE"))
                continue

            if verboso:
                print(f"  agente {i}: girando robot {id_robot} "
                      f"({math.degrees(OMEGA_PRUEBA_RAD_S):.0f}°/s durante "
                      f"{DURACION_GIRO_S:.1f} s)…")
            _mandar(socks[id_robot], 0.0, OMEGA_PRUEBA_RAD_S)
            time.sleep(DURACION_GIRO_S)
            _mandar(socks[id_robot], 0.0, 0.0)
            time.sleep(0.15)

            despues = poses.headings()
            if despues is None:
                resultados.append(ResultadoVerificacion(
                    i, id_robot, esperado, None, {}, "NADIE"))
                continue

            giros = {
                m: _delta_angular(despues[m], antes[m]) for m in marcadores
            }
            movidos = [m for m, d in giros.items() if d > UMBRAL_MOVIDO_RAD]
            if not movidos:
                veredicto, movido = "NADIE", None
            elif len(movidos) > 1:
                veredicto, movido = "AMBIGUO", None
            else:
                movido = movidos[0]
                veredicto = "OK" if movido == esperado else "CRUZADO"

            resultados.append(ResultadoVerificacion(
                i, id_robot, esperado, movido, giros, veredicto))
            time.sleep(PAUSA_ENTRE_ROBOTS_S)
    finally:
        for s in socks.values():
            try:
                _mandar(s, 0.0, 0.0)
            except OSError:
                pass
        for s in socks.values():
            try:
                s.close()
            except OSError:
                pass
        poses.cerrar()

    return resultados


class _ClientePosesIndividual:
    """
    Consulta marcadores DE A UNO, sobre UNA conexión persistente.

    HALLAZGO DE LABORATORIO (2026-08-21): la primera versión de
    `escanear_candidatos` abría y cerraba una conexión TCP por cada consulta
    (2·N conexiones para N candidatos). Contra el Robotat real, TODOS los
    candidatos volvían "sin lectura" — incluido el marcador 71, que la
    etapa 0 acababa de leer 20/20 veces segundos antes por la MISMA
    conexión persistente que usan `ClientePosesCrudo` y `FuentePosesRobotat`.
    Eso descarta "el marcador no existe": la única variable que cambió fue
    abrir 26 conexiones nuevas en ~1.5 s en vez de reusar una. El servidor
    embebido no lo tolera igual que el simulador (Python sin límite de
    conexiones concurrentes).

    Se mantiene la propiedad de seguridad que motivó las consultas
    individuales —un candidato sin marcador no debe arruinar la lectura de
    los demás, ver `escanear_candidatos`— pero ahora sobre la MISMA conexión,
    como hace el resto del código que ya funciona contra hardware real.

    Antes de cada consulta se descarta lo que ya esté en el buffer de
    entrada (mismo mecanismo que `adaptadores_robotat.descartar_buffer_pendiente`,
    aplicable acá por la misma razón: una respuesta parcial o inesperada de
    la consulta anterior no debe contaminar la siguiente).
    """

    def __init__(self) -> None:
        from adaptadores_robotat import esperar_saludo_inicial
        host, puerto = cfg.endpoint_poses()
        self._sock = socket.create_connection((host, puerto),
                                              timeout=cfg.TIMEOUT_CONEXION_S)
        self._sock.settimeout(cfg.TIMEOUT_POSES_S)
        # Sin esto, el PRIMER candidato del escaneo sale siempre "sin
        # lectura": el saludo del servidor llega pegado a su respuesta.
        # Ver `esperar_saludo_inicial` y el hallazgo del 2026-08-25.
        esperar_saludo_inicial(self._sock)

    def pose(self, marcador: int) -> Optional[float]:
        """Yaw de un marcador, o None si no se pudo leer."""
        from adaptadores_robotat import descartar_buffer_pendiente
        try:
            descartar_buffer_pendiente(self._sock)
            self._sock.sendall(codificar_peticion_poses([marcador]))
            crudo = b""
            t0 = time.perf_counter()
            while True:
                trozo = self._sock.recv(4096)
                if not trozo:
                    return None
                crudo += trozo
                m = decodificar_respuesta_poses(crudo, 1)
                if m is not None:
                    yaw, _ = heading_desde_cuaternion(
                        float(m[0][3]), float(m[0][4]),
                        float(m[0][5]), float(m[0][6]),
                    )
                    return yaw
                if time.perf_counter() - t0 > cfg.TIMEOUT_POSES_S:
                    return None
        except OSError:
            return None

    def cerrar(self) -> None:
        try:
            self._sock.sendall(b"EXIT")
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass


def escanear_candidatos(
    id_robot:   int,
    candidatos: List[int],
    verboso:    bool = True,
) -> Dict[int, Optional[float]]:
    """
    Descubre CUÁL marcador está montado sobre `id_robot`, en UN solo giro
    físico, en vez de adivinar un candidato a la vez —cada intento fallido
    cuesta un giro completo y minutos de laboratorio.

    Consulta cada candidato con su PROPIA petición individual (no en lote),
    antes y después del giro, pero todas sobre la MISMA conexión (ver
    `_ClientePosesIndividual`). Es deliberadamente más lento que un pedido
    en lote (2·N ida-y-vueltas en vez de 2) porque todavía no sabemos —la
    etapa 5 de calibración es justo la que lo mide— cómo responde el
    servidor real ante un marcador ausente. Si fuera "menos filas" (una de
    las tres hipótesis, ver README §7), UNA consulta en lote con un
    candidato malo tumbaría el escaneo completo sin decir cuál. Con
    consultas individuales, un candidato ausente sólo afecta a ese
    candidato — pero reconectar por cada una rompía contra hardware real
    (ver el hallazgo en `_ClientePosesIndividual`), así que la conexión se
    abre una sola vez para todo el escaneo.

    Retorna
    -------
    {candidato: |Δyaw| rad}. Un candidato queda ausente del dict si no se
    pudo leer su pose ni antes ni después del giro (no confundir con
    Δyaw ≈ 0, que sí es una lectura válida de "no giró").
    """
    poses = _ClientePosesIndividual()
    try:
        if verboso:
            print(f"  escaneando {len(candidatos)} candidatos: {candidatos}")
            print(f"  leyendo poses ANTES del giro…")
        antes = {c: poses.pose(c) for c in candidatos}

        host, puerto = cfg.endpoint_robot(id_robot)
        sock = socket.create_connection((host, puerto),
                                        timeout=cfg.TIMEOUT_CONEXION_S)
        try:
            if verboso:
                print(f"  girando robot {id_robot} "
                      f"({math.degrees(OMEGA_PRUEBA_RAD_S):.0f}°/s durante "
                      f"{DURACION_GIRO_S:.1f} s)…")
            _mandar(sock, 0.0, OMEGA_PRUEBA_RAD_S)
            time.sleep(DURACION_GIRO_S)
            _mandar(sock, 0.0, 0.0)
            time.sleep(0.15)
        finally:
            try:
                _mandar(sock, 0.0, 0.0)
            except OSError:
                pass
            sock.close()

        if verboso:
            print(f"  leyendo poses DESPUÉS del giro…")
        despues = {c: poses.pose(c) for c in candidatos}
    finally:
        poses.cerrar()

    giros: Dict[int, Optional[float]] = {}
    for c in candidatos:
        if antes[c] is None or despues[c] is None:
            giros[c] = None
        else:
            giros[c] = _delta_angular(despues[c], antes[c])
    return giros


def informe_escaneo(id_robot: int, giros: Dict[int, Optional[float]],
                    esperado: Optional[int] = None) -> Optional[int]:
    """
    Imprime la tabla del escaneo y devuelve el marcador identificado, o
    None si el resultado es ambiguo (ninguno o más de uno giraron).
    """
    print()
    print("=" * 72)
    print(f"ESCANEO DE MARCADOR — robot {id_robot}")
    print("=" * 72)
    print(f"{'marcador':>8}  {'Δyaw':>8}   estado")
    movidos: List[int] = []
    for c, d in sorted(giros.items()):
        if d is None:
            estado = "sin lectura (no visible / no responde)"
            texto_d = "   —"
        else:
            texto_d = f"{math.degrees(d):5.1f}°"
            if d > UMBRAL_MOVIDO_RAD:
                estado = "◄── GIRÓ"
                movidos.append(c)
            else:
                estado = ""
        marca = "  *" if c == esperado else "   "
        print(f"{c:>8}{marca}  {texto_d:>8}   {estado}")
    if esperado is not None:
        print(f"  (* = candidato que se venía probando: {esperado})")
    print("=" * 72)

    if len(movidos) == 1:
        print(f"✔ El robot {id_robot} mueve el marcador {movidos[0]}.")
        return movidos[0]
    if not movidos:
        print(f"✘ Ningún candidato giró más de "
              f"{math.degrees(UMBRAL_MOVIDO_RAD):.0f}°. Candidatos posibles: "
              f"¿la constelación no está en el volumen de captura? ¿el ID "
              f"real está fuera del rango escaneado? ¿el robot no giró "
              f"(batería, rueda trabada)?")
    else:
        print(f"✘ Giraron VARIOS candidatos ({movidos}): ¿algo más se está "
              f"moviendo en la arena, o dos marcadores comparten ID?")
    return None


def informe(resultados: List[ResultadoVerificacion]) -> bool:
    """Imprime la tabla y devuelve True si TODOS los agentes dieron OK."""
    print()
    print("=" * 72)
    print("VERIFICACIÓN DE MAPEO marcador ↔ robot")
    print("=" * 72)
    print(f"{'ag':>3} {'robot':>6} {'marc.esp':>9} {'marc.movido':>12} "
          f"{'veredicto':>10}   giros observados [°]")
    for r in resultados:
        giros = "  ".join(
            f"m{m}:{math.degrees(d):5.1f}" for m, d in sorted(r.giros.items())
        )
        print(f"{r.agente:>3} {r.id_robot:>6} {r.marcador_esperado:>9} "
              f"{str(r.marcador_movido):>12} {r.veredicto:>10}   {giros}")
    print("=" * 72)

    todo_ok = all(r.veredicto == "OK" for r in resultados)
    if todo_ok:
        print("✔ El mapeo declarado coincide con el comportamiento observado.")
        print("  Poné MAPEO_NO_VERIFICADO = False en config_robotat.py.")
    else:
        for r in resultados:
            if r.veredicto == "CRUZADO":
                print(f"✘ agente {r.agente}: el robot {r.id_robot} mueve el "
                      f"marcador {r.marcador_movido}, no el "
                      f"{r.marcador_esperado}. Corregí MAPEO_AGENTES.")
            elif r.veredicto == "NADIE":
                print(f"✘ agente {r.agente}: ningún marcador se movió. "
                      f"¿Robot {r.id_robot} apagado, sin batería, atascado, "
                      f"o el marcador no está en el volumen de captura?")
            elif r.veredicto == "AMBIGUO":
                print(f"✘ agente {r.agente}: se movió más de un marcador. "
                      f"¿Algo más se está moviendo en la arena?")
        print("\n  MAPEO_NO_VERIFICADO debe QUEDARSE en True.")
    print("=" * 72)
    return todo_ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--simulador", action="store_true",
                    help="verificar contra el simulador local")
    ap.add_argument("--agentes", type=int, default=len(cfg.MAPEO_AGENTES))
    args = ap.parse_args()

    if args.simulador:
        cfg.activar_simulador_local()
        print("[verif] usando el SIMULADOR local.")
    else:
        print("[verif] usando el ROBOTAT. Los robots SE VAN A MOVER.")
        print("[verif] giro en el lugar, ~1 rad/s, 1.2 s por robot.")

    for linea in cfg.resumen_calibracion():
        print(linea)

    return 0 if informe(verificar(args.agentes)) else 1


if __name__ == "__main__":
    sys.exit(main())
