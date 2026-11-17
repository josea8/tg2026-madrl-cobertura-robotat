"""
sonda_seguimiento.py — ¿dónde y por qué se congela un marcador?
================================================================
Sonda de laboratorio de la auditoría de pérdida de seguimiento en los bordes
(2026-09-24). En pocos minutos separa las hipótesis que el escritorio no
puede separar:
  · si el marcador que se congela lo pierde MOTIVE, o Motive lo sigue viendo
    y lo retiene el SERVIDOR (H4 / H6: retención por calidad);
  · si cada respuesta corresponde a su petición (H5: desfase de búfer).

⚠ SÓLO LEE POSES. No abre ningún socket de ruedas: los robots pueden estar
apagados —los marcadores son pasivos— y se mueven A MANO.

⚠ CÓMO SE MUEVE EL ROBOT (revisión del autor, 2026-09-24): empujando la BASE
con un dedo, con la mano por DEBAJO del plano de los marcadores; para girarlo,
empujando un costado de la base. Nunca con la mano sobre la constelación: la
cercanía de la mano sube el ruido de la pose 7–18× (auditoría), y un
congelamiento durante esa manipulación no sería atribuible al borde. Y el
control del centro se INTERCALA con la misma técnica (borde, centro, borde,
centro…), no se deja para el final.

Qué hace
--------
Consulta el servidor a `--hz` (20 por defecto) con la MISMA clase de fuente
que usa la sesión (`FuentePosesRobotat`) y con el registro de diagnóstico
activo, así que lo que registra vale para el cliente de la sesión.
  · Una línea de estado por segundo: por marcador, vivo / REPITE / rechazada
    / sin respuesta, la pose del entorno y la distancia a la pared.
  · ALARMA cuando la fila de un marcador se repite bit a bit `--alarma` veces
    seguidas (a 20 Hz, 2 = 100 ms). Un marcador vivo no repite a esa escala:
    0 repeticiones en 34 715 pares consecutivos a 10 Hz (auditoría). El
    registro usa el MISMO umbral para escribir un evento: las retenciones más
    cortas existen en toda el área y sólo se cuentan, por franja de distancia
    a la pared, en el resumen del registro.
  · El operador anota lo que ve en Motive escribiendo en la consola + Enter,
    con hora: `mv` (Motive lo muestra trackeado y moviéndose), `mp` (lo
    muestra perdido), o texto libre con los marcadores que Motive ve de la
    constelación o el error que muestra (eso es lo que decide H6). `fin`
    termina.
  · `--alternar-orden`: una consulta de cada dos pide los marcadores en orden
    inverso y reubica las filas. Si una respuesta correspondiera a la
    petición ANTERIOR, las filas quedarían cruzadas y la pose saltaría la
    distancia entre robots: `salto_de_pose` en el registro y alarma en la
    consola. La sesión no puede comprobarlo: todas sus peticiones son
    idénticas, y una respuesta atrasada no se distingue por contenido.

Modo de MAPEO (`--mapeo`, 2026-09-24; revisado el 2026-09-25)
-------------------------------------------------------------
El encargado del Robotat confirmó que el congelamiento es Motive reteniendo
la última pose de un marcador que entró en un punto ciego de las cámaras. El
modo de mapeo recorre SISTEMÁTICAMENTE y registra, por celda del marco del
laboratorio (`--celda`, 0.25 m por defecto), si hubo congelamiento, y el
ANCHO DE LA FRANJA sin captura por lado: ver `mapa_seguimiento.py`. El
recorrido lo hace el operador, con la misma técnica (dedo en la base, mano
bajo los marcadores).
  · `--orden peine` (por defecto): un pase perpendicular por cada tramo de
    0.5 m de cada pared de la arena, desde 0.90 m adentro hacia la pared. Es
    el que mide el ancho: cruzar la franja en paralelo a la pared da
    distancias menores que su ancho. La sonda dice el próximo pase y lo marca
    con → en el mapa ASCII.
  · `--orden anillos` / `serpentina`: toda la plataforma, celda por celda.
Cuando suene un ⚠, seguir EN LÍNEA RECTA ~20 cm y volver por donde vino
(nunca más allá del borde de la plataforma). Al terminar escribe el mapa por
celda (CSV y PNG), el ancho de la franja por lado —con la arena libre de
franja comparada con la de 2.7 m del Exp N— y el contraste de la dimensión
corta.

⚠ PALIATIVO. La franja no se puede esquivar con el CBF (queda una arena útil
mucho menor que la de 2.7 m que el Exp N rechazó): la solución de fondo es que
el laboratorio restituya la cobertura del 11-09. El mapa documenta la franja,
le lleva evidencia al laboratorio y verifica si la restituyó.

⚠ VIGENCIA: un mapa vale SÓLO para su sesión —la franja cambió entre el 22 y
el 24-09—. Si se usa, se mapea al inicio de CADA sesión. El PNG lleva la fecha
y hora; contra el simulador lleva además "SIMULADOR — no es dato del
Robotat".

`--plataforma` da la extensión de la plataforma en el marco del laboratorio.
NUNCA se midió (no confundir con la calibración laboratorio → entorno, que
no tiene evidencia de error): sin ella se la SUPONE centrada en el origen de
Motive. Medirla es el paso 1 del procedimiento. Lo que el mapa dice de la
ARENA no depende de ese supuesto.

Salidas en resultados_sesion/, con fecha y hora (nunca pisa):
  <fecha_hora>_sonda-seguimiento.csv    una fila por marcador y consulta, con
                                        los 7 valores crudos y el estado;
  <fecha_hora>_sonda-seguimiento.jsonl  el registro de diagnóstico;
  <fecha_hora>_sonda-seguimiento_mapa.csv / _mapa.png   con `--mapeo`.

Uso:
    python sonda_seguimiento.py --robots 9 1 --hz 20 --alternar-orden
    python sonda_seguimiento.py --robots 1 --mapeo --duracion 1200
    python sonda_seguimiento.py --simulador --robots 1 5    # simulador local

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import argparse
import csv
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, TextIO, Tuple

import numpy as np

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import config_robotat as cfg
from adaptadores_robotat import FuentePosesRobotat
from diagnostico_poses import RegistroDiagnosticoPoses, distancia_a_pared
from mapa_seguimiento import (CELDA_POR_DEFECTO_M, MapaSeguimiento, Rejilla,
                              origen_por_defecto, plataforma_por_defecto,
                              resumen_congelamientos, rotulo_origen)
from protocolo_robotat import codificar_peticion_poses

HZ_POR_DEFECTO: float = 20.0

#: Tope de frecuencia. El servidor del Robotat no es robusto bajo carga
#: (bitácora, 2026-08-22); la etapa 4a midió 200 consultas seguidas sin
#: problema, pero una sesión de sonda puede durar varios minutos.
HZ_MAXIMO: float = 50.0

#: Repeticiones seguidas que disparan la alarma.
ALARMA_POR_DEFECTO: int = 2

#: Cada cuánto se muestra el mapa en ASCII en el modo de mapeo (s).
INTERVALO_MAPA_S: float = 15.0

#: Tope de eventos por (tipo, agente) del registro de la sonda. Más alto que
#: el de la sesión: una sonda dura minutos y los eventos de borde son el
#: objeto de la medición; que no se pierdan sus bytes por el tope.
MAX_EVENTOS_SONDA: int = 1000

DIR_SALIDA: Path = _CARPETA / "resultados_sesion"

COLUMNAS_CSV: List[str] = [
    "t_s", "consulta", "orden", "agente", "robot", "marcador", "estado",
    "repeticiones", "x_lab", "y_lab", "z_lab", "qw", "qx", "qy", "qz",
    "x_env", "y_env", "th_env", "d_pared_m", "pared",
]


class FuenteSonda(FuentePosesRobotat):
    """
    La fuente de la sesión con dos agregados para la sonda:
      · guarda la última matriz cruda, en orden de agente (`ultima_matriz`);
      · con `alternar_orden`, pide una consulta de cada dos en orden inverso
        y reubica las filas ANTES de validar.
    Todo lo demás —vaciado del búfer, lectura, validación, transformación y
    ganchos del registro— es el código de `FuentePosesRobotat`, sin cambios.

    ⚠ Usa internos de la clase base (`_consultar`, `_un_viaje`,
    `_marcadores`). Si cambian allá, `test_diagnostico_poses.py` lo detecta.
    """

    def __init__(self, n_agentes: int, alternar_orden: bool = False) -> None:
        super().__init__(n_agentes)
        # En modo "individual" cada petición lleva un solo marcador: no hay
        # orden que alternar.
        self.alternar_orden: bool = (bool(alternar_orden) and n_agentes > 1
                                     and cfg.MODO_CONSULTA_POSES == "lote")
        self._invertir_proxima: bool = False
        self.ultima_matriz: Optional[np.ndarray] = None
        self.ultimo_orden: str = "directo"

    def _consultar(self) -> Optional[np.ndarray]:
        self.ultima_matriz = None
        invertir = self.alternar_orden and self._invertir_proxima
        self._invertir_proxima = not self._invertir_proxima
        if not invertir:
            self.ultimo_orden = "directo"
            matriz = super()._consultar()
        else:
            self.ultimo_orden = "invertido"
            orden = list(reversed(range(self._n)))
            peticion = codificar_peticion_poses(
                [self._marcadores[k] for k in orden])
            respuesta = self._un_viaje(peticion, self._n)
            if respuesta is None:
                matriz = None
            else:
                # Cada fila vuelve a su agente. Si la respuesta fuera la de la
                # petición anterior (otro orden), acá quedarían cruzadas.
                matriz = np.empty_like(respuesta)
                for posicion, k in enumerate(orden):
                    matriz[k] = respuesta[posicion]
        if matriz is not None:
            self.ultima_matriz = matriz.copy()
        return matriz


def correr_sonda(
    fuente: FuenteSonda,
    registro: RegistroDiagnosticoPoses,
    salida_csv: TextIO,
    duracion_s: float,
    hz: float = HZ_POR_DEFECTO,
    alarma: int = ALARMA_POR_DEFECTO,
    marcas: Optional["queue.Queue[str]"] = None,
    imprimir: Callable[[str], None] = print,
    reloj: Callable[[], float] = time.perf_counter,
    mapa: Optional[MapaSeguimiento] = None,
    intervalo_mapa_s: float = INTERVALO_MAPA_S,
) -> Dict[str, Any]:
    """
    El lazo de la sonda, separado de `main` para probarlo sin consola.

    `mapa`: el modo de mapeo. Recibe cada muestra válida de cada marcador en
    el marco del LABORATORIO (x, y crudos del servidor) y si la fila completa
    repite la anterior; tiene que tener como umbral la misma `alarma`.

    Retorna
    -------
    {"consultas", "duracion_s", "alarmas_por_robot", "saltos"}
    """
    if mapa is not None and mapa.umbral != alarma:
        raise ValueError(f"el mapa cuenta congelamientos con umbral "
                         f"{mapa.umbral} y la alarma es {alarma}: tienen que "
                         f"ser el mismo")
    n = len(fuente._marcadores)
    robots = [cfg.MAPEO_AGENTES[i].id_robot for i in range(n)]
    marcadores = [cfg.MAPEO_AGENTES[i].id_marcador for i in range(n)]
    escritor = csv.DictWriter(salida_csv, fieldnames=COLUMNAS_CSV)
    escritor.writeheader()

    periodo = 1.0 / float(hz)
    t0 = reloj()
    proximo = t0
    ultimo_estado = -1e9
    previas: Dict[int, np.ndarray] = {}
    repite: Dict[int, int] = {i: 0 for i in range(n)}
    desde: Dict[int, float] = {}
    alarmas: Dict[int, int] = {i: 0 for i in range(n)}
    estados: Dict[int, str] = {i: "—" for i in range(n)}
    poses_env: Dict[int, np.ndarray] = {}
    poses_lab: Dict[int, Tuple[float, float]] = {}
    consultas = 0
    saltos_vistos = 0
    terminar = False
    ultimo_mapa = 0.0

    def mostrar_mapa() -> None:
        for linea in mapa.ascii(poses_lab):
            imprimir(linea)

    while not terminar and reloj() - t0 < duracion_s:
        poses = fuente.leer_poses_ya()
        consultas += 1
        t = reloj() - t0
        matriz = fuente.ultima_matriz
        for i in range(n):
            fila = None if matriz is None else matriz[i]
            if fila is None:
                estado = "sin respuesta"
            elif i not in poses:
                estado = "rechazada"
            else:
                poses_env[i] = poses[i]
                if i in previas and np.array_equal(fila, previas[i]):
                    repite[i] += 1
                    estado = "REPITE"
                    if repite[i] == alarma:
                        alarmas[i] += 1
                        x, y = float(poses[i][0]), float(poses[i][1])
                        d, pared = distancia_a_pared(x, y)
                        en_lab = (f" [lab ({float(fila[0]):+.2f}, "
                                  f"{float(fila[1]):+.2f})]"
                                  if mapa is not None else "")
                        imprimir(
                            f"⚠ {t:7.2f} s  robot {robots[i]} REPITE desde "
                            f"{desde.get(i, t):.2f} s en ({x:.2f}, {y:.2f})"
                            f"{en_lab}, a {d:.2f} m de la pared {pared} — "
                            f"mirá Motive y anotá (mv / mp / lo que muestre)")
                else:
                    if repite[i] >= alarma:
                        imprimir(f"✔ {t:7.2f} s  robot {robots[i]} vivo otra "
                                 f"vez tras {t - desde.get(i, t):.2f} s")
                    repite[i] = 0
                    desde[i] = t
                    estado = "vivo"
                # ⚠ La comparación de arriba es de la fila COMPLETA de 7
                # valores, no de la posición: ver la nota en
                # `diagnostico_poses.RegistroDiagnosticoPoses.registrar_fila`.
                previas[i] = np.array(fila, dtype=np.float64, copy=True)
                if mapa is not None:
                    xl, yl = float(fila[0]), float(fila[1])
                    poses_lab[i] = (xl, yl)
                    ev = mapa.observar(marcadores[i], t, xl, yl,
                                       estado == "REPITE")
                    if ev == "fin":
                        k = mapa.congelamientos_de(marcadores[i])[-1]
                        imprimir(
                            f"  ▣ {t:7.2f} s  robot {robots[i]}: tramo sin "
                            f"captura de ({k.x0:+.2f}, {k.y0:+.2f}) a "
                            f"({k.x1:+.2f}, {k.y1:+.2f}) lab — "
                            f"{k.tramo_m:.2f} m, {len(k.celdas)} celda(s)")
            estados[i] = estado

            fila_csv: Dict[str, Any] = {
                "t_s": round(t, 4), "consulta": consultas,
                "orden": fuente.ultimo_orden, "agente": i,
                "robot": robots[i], "marcador": marcadores[i],
                "estado": estado, "repeticiones": repite[i],
            }
            if fila is not None:
                for k, nombre in enumerate(
                        ("x_lab", "y_lab", "z_lab", "qw", "qx", "qy", "qz")):
                    fila_csv[nombre] = repr(float(fila[k]))
            if i in poses:
                x, y, th = (float(v) for v in poses[i])
                d, pared = distancia_a_pared(x, y)
                fila_csv.update(x_env=repr(x), y_env=repr(y), th_env=repr(th),
                                d_pared_m=round(d, 4), pared=pared)
            escritor.writerow(fila_csv)

        saltos = int(registro.conteo.get("salto_de_pose", 0))
        if saltos > saltos_vistos:
            imprimir(f"⚠ {t:7.2f} s  SALTO DE POSE: una respuesta no "
                     f"corresponde a su petición (filas cruzadas) — ver "
                     f"`salto_de_pose` en el registro")
            saltos_vistos = saltos

        if marcas is not None:
            while True:
                try:
                    texto = marcas.get_nowait()
                except queue.Empty:
                    break
                if texto.strip().lower() == "fin":
                    terminar = True
                    continue
                if mapa is not None and texto.strip().lower() == "mapa":
                    mostrar_mapa()
                    continue
                registro.registrar_evento("marca_operador", texto=texto,
                                          t_sonda_s=round(t, 3))
                imprimir(f"  ✎ {t:7.2f} s  marca anotada: {texto}")

        if t - ultimo_estado >= 1.0:
            ultimo_estado = t
            partes = []
            for i in range(n):
                if mapa is not None and i in poses_lab:
                    # El mapa y la próxima celda son del marco del
                    # LABORATORIO: la pose del robot, también.
                    xl, yl = poses_lab[i]
                    partes.append(f"r{robots[i]} {estados[i]:<13} "
                                  f"lab({xl:+.2f},{yl:+.2f})")
                elif i in poses_env:
                    x, y = float(poses_env[i][0]), float(poses_env[i][1])
                    d, _pared = distancia_a_pared(x, y)
                    partes.append(f"r{robots[i]} {estados[i]:<13} "
                                  f"({x:.2f},{y:.2f}) d={d:.2f}")
                else:
                    partes.append(f"r{robots[i]} {estados[i]}")
            if mapa is not None:
                partes.append(f"mapa · {mapa.destino()}")
            imprimir(f"  {t:7.1f} s | " + " | ".join(partes))
            if mapa is not None and t - ultimo_mapa >= intervalo_mapa_s:
                ultimo_mapa = t
                mostrar_mapa()

        proximo += periodo
        espera = proximo - reloj()
        if espera > 0.0:
            time.sleep(espera)
        else:
            proximo = reloj()           # atrasada: no acumular deuda

    salida_csv.flush()
    return {
        "consultas": consultas,
        "duracion_s": reloj() - t0,
        "alarmas_por_robot": {robots[i]: alarmas[i] for i in range(n)},
        "saltos": saltos_vistos,
    }


def crear_registro(ruta_jsonl: Path, marcadores: Sequence[int],
                   robots: Sequence[int], alarma: int,
                   datos_inicio: Optional[Dict[str, Any]] = None,
                   ) -> RegistroDiagnosticoPoses:
    """
    El registro de la sonda: escribe una retención como evento con el MISMO
    umbral que la alarma (revisión del autor, 2026-09-24) y con tope
    `MAX_EVENTOS_SONDA`, para que las retenciones cortas de toda el área no
    agoten el tope antes de los bordes.
    """
    return RegistroDiagnosticoPoses(
        ruta_jsonl, marcadores=list(marcadores), robots=list(robots),
        datos_inicio=datos_inicio, repeticiones_para_evento=int(alarma),
        max_eventos_por_clave=MAX_EVENTOS_SONDA)


def _leer_consola(marcas: "queue.Queue[str]") -> None:
    """Hilo que pasa lo que escribe el operador a la cola de marcas."""
    for linea in sys.stdin:
        linea = linea.strip().lstrip("﻿")   # BOM del pipe de PowerShell
        if linea:
            marcas.put(linea)
            if linea.lower() == "fin":
                return


def rutas_mapa(ruta_csv: Path) -> Tuple[Path, Path]:
    """CSV y PNG del mapa, con la base del CSV de la sonda."""
    return (ruta_csv.with_name(f"{ruta_csv.stem}_mapa.csv"),
            ruta_csv.with_name(f"{ruta_csv.stem}_mapa.png"))


def rutas_salida(ahora: datetime, carpeta: Optional[Path] = None,
                 ) -> Tuple[Path, Path]:
    """
    CSV y JSONL con fecha y hora; si ya existen —ellos o los del mapa—,
    sufijo `_02`, `_03`…
    """
    carpeta = carpeta or DIR_SALIDA
    carpeta.mkdir(parents=True, exist_ok=True)
    base = f"{ahora:%Y%m%d_%H%M%S}_sonda-seguimiento"
    k = 1
    while True:
        sufijo = "" if k == 1 else f"_{k:02d}"
        ruta_csv = carpeta / f"{base}{sufijo}.csv"
        ruta_jsonl = carpeta / f"{base}{sufijo}.jsonl"
        if not any(p.exists() for p in (ruta_csv, ruta_jsonl,
                                        *rutas_mapa(ruta_csv))):
            return ruta_csv, ruta_jsonl
        k += 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--robots", type=int, nargs="+",
                    default=[a.id_robot for _i, a
                             in sorted(cfg.MAPEO_AGENTES.items())],
                    help="robots a vigilar (robot N ↔ marcador N)")
    ap.add_argument("--hz", type=float, default=HZ_POR_DEFECTO,
                    help=f"consultas por segundo (máximo {HZ_MAXIMO:g})")
    ap.add_argument("--duracion", type=float, default=600.0,
                    help="segundos (default 600); 'fin' + Enter corta antes")
    ap.add_argument("--alarma", type=int, default=ALARMA_POR_DEFECTO,
                    help="repeticiones seguidas que disparan la alarma")
    ap.add_argument("--alternar-orden", action="store_true",
                    dest="alternar_orden",
                    help="alterna el orden de los marcadores en la petición "
                         "para verificar que cada respuesta es de SU petición")
    ap.add_argument("--simulador", action="store_true",
                    help="contra el simulador local, sin hardware")
    ap.add_argument("--mapeo", action="store_true",
                    help="modo de mapeo: recorrido sistemático y mapa por "
                         "celda de dónde se congela (ver mapa_seguimiento.py)")
    ap.add_argument("--celda", type=float, default=CELDA_POR_DEFECTO_M,
                    help="lado de la celda del mapa, en m")
    ap.add_argument("--plataforma", type=float, nargs=4,
                    metavar=("X_MIN", "X_MAX", "Y_MIN", "Y_MAX"),
                    default=None,
                    help="extensión de la plataforma en el marco del "
                         "laboratorio, en m (por defecto se la SUPONE "
                         "centrada en el origen de Motive)")
    ap.add_argument("--orden", choices=("peine", "anillos", "serpentina"),
                    default="peine",
                    help="recorrido: peine (pases perpendiculares a cada pared "
                         "de la arena: mide el ancho de la franja), anillos o "
                         "serpentina (toda la plataforma)")
    args = ap.parse_args(list(argv) if argv is not None else None)

    if not (0.0 < args.hz <= HZ_MAXIMO):
        print(f"[sonda] --hz {args.hz:g} fuera de (0, {HZ_MAXIMO:g}].")
        return 2
    if args.alarma < 1:
        print("[sonda] --alarma tiene que ser ≥ 1.")
        return 2
    plataforma = (tuple(args.plataforma) if args.plataforma
                  else plataforma_por_defecto())
    if args.mapeo and not (plataforma[0] < plataforma[1]
                           and plataforma[2] < plataforma[3]
                           and 0.02 <= args.celda <= 1.0):
        print("[sonda] --plataforma tiene que ser X_MIN < X_MAX, Y_MIN < Y_MAX "
              "y --celda entre 0.02 y 1 m.")
        return 2
    if args.simulador:
        cfg.activar_simulador_local()

    # El mismo marco laboratorio → entorno que la sesión, para que la pose y
    # la distancia a la pared que se ven acá sean las que ve el lazo.
    import calibracion_sesion as calib
    calib.aplicar_a_config()

    try:
        cfg.MAPEO_AGENTES = {
            i: cfg.AsignacionAgente(id_marcador=cfg.marcador_fijo_de_robot(r),
                                    id_robot=r)
            for i, r in enumerate(args.robots)}
    except ValueError as exc:
        print(f"[sonda] {exc}")
        return 2

    ahora = datetime.now()
    sesion = f"{ahora:%Y-%m-%d %H:%M}"
    ruta_csv, ruta_jsonl = rutas_salida(ahora)
    ruta_mapa_csv, ruta_mapa_png = rutas_mapa(ruta_csv)
    mapa: Optional[MapaSeguimiento] = None
    if args.mapeo:
        mapa = MapaSeguimiento(
            Rejilla(*plataforma, celda=args.celda), umbral=args.alarma,
            plataforma=plataforma, orden=args.orden)
        # El peine sale de la arena, que sale de la calibración: se arma
        # después de `calib.aplicar_a_config()` (más arriba).
    n = len(args.robots)
    fuente = FuenteSonda(n, alternar_orden=args.alternar_orden)
    registro = crear_registro(
        ruta_jsonl,
        marcadores=[cfg.MAPEO_AGENTES[i].id_marcador for i in range(n)],
        robots=list(args.robots), alarma=args.alarma,
        datos_inicio={"herramienta": "sonda_seguimiento", "hz": args.hz,
                      "alarma": args.alarma,
                      "alternar_orden": fuente.alternar_orden,
                      "mapeo": bool(args.mapeo), "celda_m": args.celda,
                      "plataforma_lab": list(plataforma),
                      "plataforma_supuesta": args.plataforma is None,
                      "orden": args.orden,
                      "argv": list(sys.argv[1:] if argv is None else argv)},
    )
    fuente.activar_diagnostico(registro)

    host, puerto = cfg.endpoint_poses()
    print("=" * 72)
    print("SONDA DE SEGUIMIENTO — sólo lee poses; NO mueve ningún robot")
    print("=" * 72)
    print("  marcadores : " + ", ".join(
        f"robot {cfg.MAPEO_AGENTES[i].id_robot} → marcador "
        f"{cfg.MAPEO_AGENTES[i].id_marcador}" for i in range(n)))
    print(f"  frecuencia : {args.hz:g} Hz · alarma a {args.alarma} "
          f"repeticiones ({1000.0 * args.alarma / args.hz:.0f} ms) · orden "
          f"alternado: {'sí' if fuente.alternar_orden else 'no'}")
    print(f"  servidor   : {host}:{puerto}")
    print(f"  salidas    : {ruta_csv.name} / {ruta_jsonl.name}")
    print("  Mové el robot EMPUJANDO LA BASE CON UN DEDO, la mano por DEBAJO")
    print("  de los marcadores (nunca encima de la constelación); para girarlo,")
    print("  empujá un costado de la base. Intercalá el centro: borde, centro,")
    print("  borde, centro… con la misma técnica.")
    print("  En cada ⚠ mirá Motive y escribí + Enter:")
    print("     mv = trackeado y moviéndose · mp = perdido · o lo que muestre")
    print("     (cuántos marcadores de la constelación ve, el error medio)")
    if mapa is not None:
        px0, px1, py0, py1 = plataforma
        print("-" * 72)
        print(f"  MAPEO: plataforma x [{px0:+.3f}, {px1:+.3f}] · y "
              f"[{py0:+.3f}, {py1:+.3f}] m lab"
              + (" (SUPUESTA centrada en el origen: medila y pasala con "
                 "--plataforma)" if args.plataforma is None else ""))
        rotulo = rotulo_origen(origen_por_defecto())
        if rotulo:
            print(f"  ⚠ {rotulo}")
        print(f"  El mapa vale SÓLO para esta sesión ({sesion}): la franja")
        print("  cambió entre el 22 y el 24-09. Si se usa, mapeá al inicio de")
        print("  CADA sesión.")
        if args.orden == "peine":
            print(f"  recorrido 'peine': {len(mapa.pases)} pases, uno por tramo "
                  f"de 0.5 m de cada pared de la arena, en perpendicular")
            print("  Llevá UN robot al inicio del pase que indica la sonda (→ en")
            print("  el mapa) y empujalo DERECHO hacia la pared (dedo en la")
            print("  base). En un ⚠ seguí ~20 cm y volvé por donde viniste;")
            print("  nunca más allá del borde de la plataforma.")
        else:
            print(f"  celdas de {args.celda:.2f} m: {mapa.rejilla.n_x} × "
                  f"{mapa.rejilla.n_y} = {mapa.rejilla.total} · recorrido "
                  f"'{args.orden}' ({'el perímetro primero' if args.orden == 'anillos' else 'filas a lo largo de x'})")
            print("  Llevá UN robot a la celda marcada con → en el mapa, con la")
            print("  misma técnica (dedo en la base). En un ⚠ seguí EN LÍNEA")
            print("  RECTA hasta el ✔: así queda medido el tramo sin captura; si")
            print("  no vuelve en ~20 cm o se acerca el borde, volvé por donde")
            print("  viniste.")
        print("  Cada tanto, una pasada por el centro (control).")
        print("  'mapa' + Enter muestra el mapa en el acto.")
    print("  'fin' + Enter termina (o Ctrl+C).")
    print("=" * 72)

    marcas: "queue.Queue[str]" = queue.Queue()
    threading.Thread(target=_leer_consola, args=(marcas,), daemon=True).start()

    resumen: Dict[str, Any] = {}
    codigo = 0
    try:
        fuente.conectar()
        with open(ruta_csv, "x", newline="", encoding="utf-8") as fh:
            resumen = correr_sonda(fuente, registro, fh, args.duracion,
                                   args.hz, args.alarma, marcas, mapa=mapa)
    except KeyboardInterrupt:
        print("\n[sonda] interrumpida por el usuario.")
    except OSError as exc:
        print(f"[sonda] ✘ no se pudo hablar con el servidor de poses: {exc}")
        codigo = 5
    finally:
        fuente.cerrar()
        if mapa is not None:
            _cerrar_mapa(mapa, registro, ruta_mapa_csv, ruta_mapa_png,
                         args.plataforma is None, sesion=sesion)
        registro.cerrar(resumen_fuente=fuente.resumen(),
                        contadores={"sonda": resumen})
    print(f"[sonda] {resumen.get('consultas', 0)} consultas · alarmas por "
          f"robot {resumen.get('alarmas_por_robot', {})} · saltos "
          f"{resumen.get('saltos', 0)}")
    print(f"[sonda] CSV → {ruta_csv}")
    return codigo


def _cerrar_mapa(mapa: MapaSeguimiento, registro: RegistroDiagnosticoPoses,
                 ruta_csv: Path, ruta_png: Path,
                 plataforma_supuesta: bool, sesion: str = "",
                 origen: Optional[str] = None) -> None:
    """
    Escribe el mapa (CSV por celda y PNG, sin pisar nada), lo muestra, y deja
    el ancho de la franja por lado, el contraste de la dimensión corta y cada
    congelamiento en el registro. `origen` ("robotat", "simulador" o
    "sintetico"; por defecto, según la configuración) rotula todo lo que no
    es dato del Robotat. No lanza: corre en el `finally`, y lo medido ya está
    en el CSV de la sonda.
    """
    try:
        origen = origen or origen_por_defecto()
        rotulo = rotulo_origen(origen)
        print("=" * 72)
        if rotulo:
            print(f"⚠ {rotulo}")
        print("MAPA DE CONGELAMIENTOS (marco del laboratorio)"
              + (f" — sesión {sesion}, vale sólo para esta sesión"
                 if sesion else ""))
        for linea in mapa.ascii():
            print(linea)
        for linea in mapa.lineas_franja():
            print(linea)
        print("CONTRASTE: ¿los puntos ciegos están junto a los bordes de la "
              "dimensión corta?")
        for linea in mapa.lineas_contraste():
            print(linea)
        if plataforma_supuesta:
            print("  ⚠ plataforma SUPUESTA centrada en el origen de Motive: "
                  "lo que se dice de la PLATAFORMA vale lo que valga ese "
                  "supuesto (lo de la arena, no).")
        with open(ruta_csv, "x", newline="", encoding="utf-8") as fh:
            mapa.escribir_csv(fh, origen)
        print(f"[sonda] mapa por celda → {ruta_csv}")
        titulo = ("Mapa de congelamientos (marco del laboratorio)"
                  + (f"\nsesión {sesion} — vale sólo para esta sesión"
                     if sesion else ""))
        if mapa.guardar_png(ruta_png, titulo, origen):
            print(f"[sonda] mapa → {ruta_png}")
        else:
            print("[sonda] sin matplotlib: no hay PNG (el CSV alcanza)")
        registro.registrar_evento(
            "mapa_resumen", origen=origen, sesion=sesion,
            orden=mapa.modo_orden,
            pases=({"hechos": mapa.pases_hechos(), "total": len(mapa.pases)}
                   if mapa.pases else None),
            franja_arena=mapa.franja_por_lado("arena"),
            franja_plataforma=mapa.franja_por_lado("plataforma"),
            contraste=mapa.contraste(),
            congelamientos=resumen_congelamientos(mapa),
            plataforma_supuesta=plataforma_supuesta)
    except Exception as exc:                                # noqa: BLE001
        print(f"[sonda] ✘ no se pudo escribir el mapa: {exc}")


if __name__ == "__main__":
    sys.exit(main())
