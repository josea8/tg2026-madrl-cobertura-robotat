"""
sonda_enlace_robots.py — ¿por qué un robot cierra su socket de ruedas?

⚠ Los robots NO se mueven: sólo se manda velocidad CERO. Igual se corre con
el operador presente y el interruptor de cada robot a mano.

Contexto (BITACORA_TECNICA, 2026-09-12): todos los 10054 de robots cayeron
con los robots QUIETOS, en la pausa de recolocación, nunca andando; el del
11-09 llegó 1–2 s después de apoyar el robot 3 en su nuevo lugar. El 10054
sólo dice que el robot mandó un RST. Esta sonda separa las hipótesis:

  H1 reinicio del ESP32 (contacto de batería/interruptor al manipularlo):
     el ping se corta varios segundos y la reconexión tarda lo mismo.
  H2 pérdida de WiFi sin reinicio: el ping se corta, pero al volver la
     conexión VIEJA puede seguir viva (no hay RST).
  H3 el firmware descarta la conexión sin reiniciarse: el ping NUNCA se
     corta y la reconexión sale al primer intento.

Por robot, en paralelo:
  · un socket de ruedas que manda (0, 0) a `--hz`, como el latido de la guía;
  · ping cada 0.5 s (transiciones arriba/abajo con hora);
  · al caer el socket, reintentos con timeout LARGO (3 s), para que Windows
    llegue a devolver "rechazada" en vez de timeout.
Y el operador anota lo que hace escribiendo en la consola y Enter
("levanto 3", "apoyo 3", "golpe interruptor 3"): queda con hora en el CSV.
Ctrl+C o `fin` termina; siempre manda (0, 0) y cierra.

Uso:
    python sonda_enlace_robots.py --robots 3 6 --duracion 600
"""
import argparse
import csv
import datetime as dt
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import config_robotat as cfg
from protocolo_robotat import codificar_velocidades_rueda

ap = argparse.ArgumentParser()
ap.add_argument("--robots", type=int, nargs="+",
                default=[m.id_robot for m in cfg.MAPEO_AGENTES.values()])
ap.add_argument("--duracion", type=float, default=600.0, help="segundos")
ap.add_argument("--hz", type=float, default=1.0,
                help="envíos de (0,0) por segundo (la guía late a 1 Hz)")
args = ap.parse_args()

T0 = time.perf_counter()
eventos = []
cerrojo = threading.Lock()
parar = threading.Event()
CERO = codificar_velocidades_rueda(0.0, 0.0)


def anotar(robot, fuente, evento, detalle=""):
    fila = {"hora": dt.datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "t_s": round(time.perf_counter() - T0, 3), "robot": robot,
            "fuente": fuente, "evento": evento, "detalle": detalle}
    with cerrojo:
        eventos.append(fila)
    print(f"{fila['hora']}  r{robot!s:<4} {fuente:<7} {evento:<22} {detalle}",
          flush=True)


def conectar(host, puerto, timeout):
    s = socket.create_connection((host, puerto), timeout=timeout)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return s


def clase(exc):
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "sin respuesta"
    if isinstance(exc, ConnectionRefusedError):
        return "rechazada"
    return f"{type(exc).__name__} {getattr(exc, 'errno', '')}"


def enlace(robot):
    host, puerto = cfg.endpoint_robot(robot)
    s = None
    try:
        s = conectar(host, puerto, 3.0)
        anotar(robot, "socket", "conectado", f"{host}:{puerto}")
    except OSError as exc:
        anotar(robot, "socket", "no conecta al inicio", clase(exc))
    t_caida = None
    periodo = 1.0 / args.hz
    while not parar.is_set():
        if s is not None:
            try:
                s.sendall(CERO)
            except OSError as exc:
                anotar(robot, "socket", "CAÍDA", f"{type(exc).__name__} "
                       f"{getattr(exc, 'errno', '')}")
                try:
                    s.close()
                except OSError:
                    pass
                s, t_caida, n = None, time.perf_counter(), 0
        if s is None:
            n = n + 1 if t_caida is not None else 1
            t = time.perf_counter()
            try:
                s = conectar(host, puerto, 3.0)
                demora = f"{time.perf_counter() - t_caida:.2f} s" if t_caida else "—"
                anotar(robot, "socket", "RECONECTADO",
                       f"intento {n}, a {demora} de la caída")
                t_caida = None
            except OSError as exc:
                anotar(robot, "socket", "reintento fallido",
                       f"{clase(exc)} en {time.perf_counter() - t:.2f} s")
                parar.wait(0.5)
                continue
        parar.wait(periodo)
    if s is not None:
        try:
            s.sendall(CERO)
            s.close()
        except OSError:
            pass


def ping(robot):
    host, _ = cfg.endpoint_robot(robot)
    arriba = None
    while not parar.is_set():
        r = subprocess.run(["ping", "-n", "1", "-w", "400", host],
                           capture_output=True, text=True)
        ok = "TTL=" in r.stdout.upper()   # "host inalcanzable" devuelve 0
        if ok != arriba:
            anotar(robot, "ping", "responde" if ok else "NO RESPONDE")
            arriba = ok
        parar.wait(0.5)


print(f"sonda de enlace — robots {args.robots}, {args.duracion:.0f} s, "
      f"(0,0) a {args.hz:g} Hz. Escribí lo que hacés + Enter; 'fin' termina.")
hilos = [threading.Thread(target=f, args=(r,), daemon=True)
         for r in args.robots for f in (enlace, ping)]
for h in hilos:
    h.start()


def leer_operador():
    for linea in sys.stdin:
        linea = linea.strip().lstrip("\ufeff")   # BOM del pipe de PowerShell
        if linea.lower() == "fin":
            parar.set()
            return
        if linea:
            anotar("-", "operador", "MARCA", linea)


threading.Thread(target=leer_operador, daemon=True).start()
try:
    # Esperas cortas: en Windows un wait largo puede no despertar con Ctrl+C.
    while (not parar.wait(0.2)
           and time.perf_counter() - T0 < args.duracion):
        pass
except KeyboardInterrupt:
    pass
finally:
    parar.set()
    for h in hilos:
        h.join(timeout=4.0)
    carpeta = Path(__file__).resolve().parent / "resultados_sesion"
    carpeta.mkdir(exist_ok=True)
    salida = carpeta / f"{dt.datetime.now():%Y%m%d_%H%M%S}_sonda-enlace.csv"
    with open(salida, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["hora", "t_s", "robot", "fuente",
                                           "evento", "detalle"])
        w.writeheader()
        w.writerows(eventos)
    print(f"\n{len(eventos)} eventos → {salida}")
