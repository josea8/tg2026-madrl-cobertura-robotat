"""
mapa_seguimiento.py
===================
Mapa, celda por celda, de DÓNDE se congela un marcador, y ancho de la franja
sin captura por lado: el modo de mapeo de la sonda
(`sonda_seguimiento.py --mapeo`, 2026-09-24; ancho por lado y recorrido en
peine, 2026-09-25).

Por qué
-------
El encargado del Robotat confirmó el mecanismo: un marcador ya detectado que
entra en un punto ciego de las cámaras sale con la ÚLTIMA pose registrada,
retenida por Motive, y el servidor la reenvía sin verificar. La auditoría
mostró una franja perimetral: 0 inicios de congelamiento en 7 818
decisiones-agente a ≥ 0.60 m de la pared (22 y 24-09).

⚠ Esto es un PALIATIVO. La franja no se puede esquivar con el CBF: tratarla
como obstáculo deja una arena útil mucho menor que la de 2.7 × 2.7 m que el
Exp N ya rechazó (conclusión estratégica del autor, 2026-09-25). La solución
de fondo es que el laboratorio restituya la cobertura del 11-09. El mapa sirve
para documentar la franja, llevarle evidencia al laboratorio y verificar si
la restituyó.

Vigencia
--------
Un mapa vale SÓLO para la sesión en que se toma: la franja cambió entre
sesiones (22-09 y 24-09). Si se usa, se mapea al inicio de CADA sesión. La
imagen lleva la fecha y hora de su sesión.

Qué registra
------------
En el marco del LABORATORIO —el de Motive y la plataforma—, sobre una rejilla
de celdas (0.25 m por defecto):
  · muestras vivas por celda, y qué marcadores pasaron;
  · cada congelamiento: dónde EMPEZÓ —la pose retenida es la última que
    Motive registró: el borde del punto ciego del lado por el que se entró— y
    dónde el marcador volvió a verse. Las celdas del segmento entre esos dos
    puntos se cuentan como cruzadas a ciegas (interpolación en línea recta:
    válida si el operador empuja en línea recta);
  · las retenciones cortas (menos repeticiones que el umbral), aparte.
Un congelamiento cuenta con el MISMO umbral que la alarma de la sonda y que el
evento del registro, y la repetición se juzga sobre la fila COMPLETA de 7
valores, como en todo el proyecto.

Estado de cada celda: "viva" (sólo muestras vivas), "borde" (vivas y además
un inicio, un fin o un cruce de un congelamiento), "ciega" (cruzada a ciegas y
nunca vista viva) y "sin_visitar".

Ancho de la franja por lado (`franja_por_lado`)
-----------------------------------------------
El estadístico que ahora más informa: ¿la franja es uniforme o algún lado
está peor? Una TRANSICIÓN es un punto donde el marcador se perdió (la pose
retenida) o volvió a verse, con la DIRECCIÓN en que se movía (entrada: las
últimas muestras vivas antes de perderse; salida: las primeras después de
volver). Sólo una transición PERPENDICULAR a la pared (±30°: hacia la pared
al perderse, alejándose al volver) cae en el borde interior del punto ciego,
y su distancia a ESA pared es el ancho ahí; por eso cada transición se
atribuye a la pared hacia la que avanzaba en perpendicular (si hay una a
≤ 0.90 m), no a la más cercana. Una que no avanzaba en perpendicular hacia
ninguna pared mide el carril por donde iba el robot —el CBF los lleva a
~0.17–0.24 m—: es sólo una COTA INFERIOR del ancho de la pared más cercana.
Lo mostró la auditoría de los inicios del 22 y 24-09 (revisión del
2026-09-25): el 24-09, 7 de 10 entraron paralelos a la pared más cercana, y
6 de esos 7 iban de frente hacia la pared adyacente, a 0.43–0.70 m de ella.

Por lado —de la ARENA (marco del entorno, con la calibración vigente) y de la
plataforma (marco lab)—: transiciones (y cuántas perpendiculares), ancho
mediano y máximo con las perpendiculares, cota inferior con las demás,
transiciones por marcador, y el perfil en tramos de 0.5 m a lo largo del
lado. Para la arena, además:
  · esquinas contra tramo medio: inicios por 1000 muestras vivas a < 0.35 m
    de la pared, en los tramos extremos de cada lado y en los del medio (el
    24-09 los inicios se concentraron cerca de las esquinas);
  · la ARENA LIBRE de franja (centro del robot fuera de ella) y la arena
    EQUIVALENTE en la convención del Exp N: el CBF ya mantiene el punto de
    mira (ℓa = 0.05 m delante del centro) a 0.18 m de la pared, así que
    esquivar una franja de ancho w exige subir ese margen a w + 0.05 (el
    centro fuera con cualquier rumbo), y cada lado resta
    max(0, w + 0.05 − 0.18). Se compara con la 2.7 × 2.7 del Exp N, que se
    midió con ese mismo CBF.

⚠ El ancho depende del marcador: el 24-09 el robot 6 no se congeló nunca
donde los demás sí. Un mapa hecho con un solo robot puede no valer para los
otros; por eso las transiciones se desglosan por marcador.

⚠ Un recorrido paralelo a la pared da transiciones LATERALES, con distancias
menores que el ancho: por eso existe el recorrido en peine. Y en las esquinas
—a menos del ancho de las dos paredes— cada punto cuenta para la pared más
cercana: ahí el ancho por lado es ambiguo por construcción.

Recorrido sistemático
---------------------
  · "peine" (el de la sonda por defecto): un pase por cada tramo de 0.5 m de
    cada pared de la arena, en perpendicular, desde 0.90 m adentro hasta 5 cm
    más allá de la pared (recortado a 5 cm del borde de la plataforma). Un
    pase queda hecho cuando dio una transición en ese tramo o cuando el robot
    llegó VIVO a ≤ 2 cm de la pared. Es el que mide bien el ancho, y el más
    corto: 24 pases en la arena de 3 × 3.
  · "anillos": toda la plataforma, de afuera hacia adentro;
  · "serpentina": toda la plataforma, filas a lo largo de x.

Contraste de la dimensión corta (`contraste`)
---------------------------------------------
Se mantiene la prueba exacta de Fisher sobre la predicción de que los puntos
ciegos se concentran junto a los bordes de la dimensión corta de la
plataforma, aunque el 24-09 (congelamientos junto a las cuatro paredes) ya la
contradice. Lo que más informa ahora es el ancho por lado.

⚠ La posición de la plataforma en el marco de Motive NUNCA se midió —no hay
que confundirla con la calibración laboratorio → entorno, que no tiene
evidencia de error—: sin `--plataforma` se la supone centrada en el origen, y
todo lo que se diga de la plataforma vale lo que valga ese supuesto. Se mide
con la sonda (paso 1 del procedimiento). Lo de la ARENA no depende de eso.

⚠ Todo PNG hecho contra el simulador, o con datos sintéticos, lleva una marca
visible: "SIMULADOR — no es dato del Robotat".

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, TextIO, Tuple

import config_robotat as cfg

#: Lado de celda por defecto (m): ~2.5 diámetros de robot.
CELDA_POR_DEFECTO_M: float = 0.25

#: Franjas de distancia al borde de la plataforma para el contraste (m).
FRANJAS_BORDE_M: Tuple[float, ...] = (0.25, 0.50, 1.00)

#: Distancia al borde que define "junto al borde" en la prueba de Fisher.
CERCA_DEL_BORDE_M: float = 0.50

#: Largo de los tramos en que se divide cada lado para el perfil (m).
SEGMENTO_LADO_M: float = 0.50

#: Un tramo tiene datos si hubo una transición o una muestra viva a menos de
#: esto de la pared: más allá no hubo congelamientos (0 en 7 818
#: decisiones-agente a ≥ 0.60 m, auditoría del 24-09).
VISITA_LADO_M: float = 0.60

#: Sin transiciones en un lado y visto vivo a ≤ esto de su pared → ese lado
#: cuenta con franja 0 para la arena libre. 0.25 m: el CBF deja el centro del
#: robot a 0.13–0.23 m de la pared según el rumbo (punto de mira a 0.18 m,
#: 0.05 m delante), así que en una sesión nadie llega más cerca; visto vivo en
#: ese carril, lo que quede de franja no afecta la operación.
SIN_FRANJA_SI_VIVO_A_M: float = 0.25

#: Recorrido en peine: cada pase va de PEINE_DESDE_M adentro de la arena a
#: PEINE_HASTA_M (negativo = afuera), recortado a BORDE_SEGURO_M del borde de
#: la plataforma. Queda hecho con una transición en su tramo o con el robot
#: visto vivo a ≤ LLEGO_A_LA_PARED_M de la pared.
PEINE_DESDE_M: float = 0.90
PEINE_HASTA_M: float = -0.05
BORDE_SEGURO_M: float = 0.05
LLEGO_A_LA_PARED_M: float = 0.02
#: Una transición cuenta para un pase si está a menos de esto de su línea
#: (un cuarto de tramo): el operador empuja sobre la línea, y con una banda
#: del tramo entero los pases de paredes vecinas se solapan en las esquinas.
TOLERANCIA_PASE_M: float = 0.125

#: La arena reducida que el Exp N midió y rechazó (m de lado).
ARENA_EXP_N_M: float = 2.7

#: CBF de pared del coordinador (y del Exp N): el punto de mira va `ELE_A_M`
#: delante del centro y se mantiene a `D_SEGURA_PARED_M` de la pared
#: (`coordinador_enjambre.ELE_A`, `D_SEGURA_PUNTO`).
ELE_A_M: float = 0.05
D_SEGURA_PARED_M: float = 0.18

#: Una transición es perpendicular si su dirección está a ≤ esto de la normal
#: de la pared (hacia la pared al perderse, alejándose al volver).
ANGULO_PERPENDICULAR_DEG: float = 30.0

#: Muestras vivas que se usan para la dirección de una transición, y el
#: desplazamiento mínimo para que haya dirección (m). 1 cm: con ~10 µm de
#: ruido de captura el error angular es despreciable, y en la rampa de
#: arranque (≤ 0.031 m/s) 6 decisiones a 10 Hz recorren ~1.5 cm.
MUESTRAS_DIRECCION: int = 6
DESPLAZAMIENTO_DIRECCION_M: float = 0.01

#: "Cerca de la pared" para contar exposición en el contraste esquinas vs
#: tramo medio (m): el umbral de la auditoría.
CERCA_PARED_M: float = 0.35

ORIGENES: Tuple[str, ...] = ("robotat", "simulador", "sintetico")
ROTULOS_ORIGEN: Dict[str, str] = {
    "simulador": "SIMULADOR — no es dato del Robotat",
    "sintetico": "SINTÉTICO — no es dato del Robotat",
}

REFERENCIAS: Tuple[str, ...] = ("arena", "plataforma")

ESTADOS: Tuple[str, ...] = ("sin_visitar", "viva", "borde", "ciega")
SIMBOLOS: Dict[str, str] = {"sin_visitar": "·", "viva": "○", "borde": "◐",
                            "ciega": "█"}

COLUMNAS_CSV_MAPA: List[str] = [
    "origen", "ix", "iy", "x_min", "x_max", "y_min", "y_max", "x_centro",
    "y_centro", "estado", "vivas", "repetidas", "retenciones_cortas",
    "inicios", "fines", "cruces", "marcadores", "borde_plataforma",
    "dimension_borde", "d_borde_plataforma_m", "franja_borde", "pared_arena",
    "d_pared_arena_m",
]

Rect = Tuple[float, float, float, float]            # x_min, x_max, y_min, y_max
Indice = Tuple[int, int]


# =============================================================================
# FUNCIONES PURAS
# =============================================================================

def plataforma_por_defecto() -> Rect:
    """El área útil (`AREA_UTIL_*`) CENTRADA en el origen de Motive: supuesto."""
    ax = float(cfg.AREA_UTIL_X_M) / 2.0
    ay = float(cfg.AREA_UTIL_Y_M) / 2.0
    return (-ax, ax, -ay, ay)


def env_a_lab_xy(x_env: float, y_env: float) -> Tuple[float, float]:
    """Inversa de la parte de posición de `protocolo_robotat.lab_a_env`."""
    dx = float(x_env) - cfg.TRASLACION_X_M
    dy = float(y_env) - cfg.TRASLACION_Y_M
    c, s = math.cos(cfg.ROTACION_MARCO_RAD), math.sin(cfg.ROTACION_MARCO_RAD)
    return ((c * dx + s * dy) / cfg.ESCALA_POSICION,
            (-s * dx + c * dy) / cfg.ESCALA_POSICION)


def lab_a_env_xy(x_lab: float, y_lab: float) -> Tuple[float, float]:
    """Posición lab → entorno con la MISMA función que usa la fuente."""
    from protocolo_robotat import lab_a_env
    p = lab_a_env(float(x_lab), float(y_lab), 0.0, 0.0)
    return float(p[0]), float(p[1])


def arena_env() -> Rect:
    """La arena en el marco del entorno."""
    return (0.0, float(cfg.ARENA_WX_M), 0.0, float(cfg.ARENA_WY_M))


def arena_en_lab() -> List[Tuple[float, float]]:
    """Las cuatro esquinas de la arena (y la primera otra vez), marco lab."""
    wx, wy = float(cfg.ARENA_WX_M), float(cfg.ARENA_WY_M)
    return [env_a_lab_xy(x, y)
            for x, y in ((0, 0), (wx, 0), (wx, wy), (0, wy), (0, 0))]


def nombres_lados(referencia: str) -> Tuple[str, str, str, str]:
    """(x mín, x máx, y mín, y máx) con el nombre de cada lado."""
    if referencia == "arena":
        return ("x=0", f"x={float(cfg.ARENA_WX_M):g}", "y=0",
                f"y={float(cfg.ARENA_WY_M):g}")
    if referencia == "plataforma":
        return ("x-", "x+", "y-", "y+")
    raise ValueError(f"referencia desconocida: {referencia!r}")


def distancia_a_lado(x: float, y: float, rect: Rect, indice: int
                     ) -> Tuple[float, float, float]:
    """
    (distancia, u, largo) de (x, y) al lado `indice` de `rect` (0: x mín,
    1: x máx, 2: y mín, 3: y máx): `u` es la coordenada a lo largo del lado
    desde su extremo de x o y mínimos. Distancia negativa = afuera.
    """
    x0, x1, y0, y1 = rect
    return ((x - x0, y - y0, y1 - y0), (x1 - x, y - y0, y1 - y0),
            (y - y0, x - x0, x1 - x0), (y1 - y, x - x0, x1 - x0))[indice]


def lado_mas_cercano(x: float, y: float, rect: Rect,
                     nombres: Sequence[str]) -> Tuple[str, float, float, float]:
    """
    (lado, distancia, u, largo) del lado de `rect` más cercano a (x, y): `u`
    es la coordenada a lo largo del lado desde su extremo de x o y mínimos, y
    `largo` el largo del lado. Distancia negativa = afuera.
    """
    candidatos = [(nombres[i], *distancia_a_lado(x, y, rect, i))
                  for i in range(4)]
    lado, d, u, largo = min(candidatos, key=lambda c: c[1])
    return lado, float(d), float(u), float(largo)


def tramo_de(u: float, largo: float) -> int:
    """Índice del tramo de `SEGMENTO_LADO_M` que contiene u."""
    n = max(1, math.ceil(largo / SEGMENTO_LADO_M - 1e-9))
    return min(max(int(u // SEGMENTO_LADO_M), 0), n - 1)


def borde_mas_cercano(x: float, y: float, plataforma: Rect
                      ) -> Tuple[float, str, str]:
    """
    (distancia, borde, dimensión) del borde de la plataforma más cercano a
    (x, y). `borde` es "x-", "x+", "y-" o "y+"; `dimensión`, "corta" o
    "larga": la corta es la de menor extensión (y, 3.45 m, en el Robotat), y
    sus bordes son los perpendiculares a ella. Negativa = afuera.
    """
    x0, x1, y0, y1 = plataforma
    candidatos = {"x-": x - x0, "x+": x1 - x, "y-": y - y0, "y+": y1 - y}
    borde = min(candidatos, key=lambda k: candidatos[k])
    corta = "y" if (y1 - y0) <= (x1 - x0) else "x"
    return float(candidatos[borde]), borde, (
        "corta" if borde[0] == corta else "larga")


def franja(d: float) -> str:
    """Nombre de la franja de distancia al borde (ver `FRANJAS_BORDE_M`)."""
    if d < 0.0:
        return "fuera"
    previo = 0.0
    for tope in FRANJAS_BORDE_M:
        if d < tope:
            return f"{previo:.2f}-{tope:.2f}"
        previo = tope
    return f">={previo:.2f}"


def fisher_unilateral(a: int, b: int, c: int, d: int) -> float:
    """
    Prueba exacta de Fisher, unilateral: P(X ≥ a) con los márgenes de la
    tabla [[a, b], [c, d]] fijos (hipergeométrica). H1: la primera fila
    tiene MÁS casos en la primera columna que lo esperable por azar.
    """
    n1, col1, n = a + b, a + c, a + b + c + d
    if n == 0:
        return 1.0
    total = math.comb(n, n1)
    return float(sum(math.comb(col1, k) * math.comb(n - col1, n1 - k)
                     for k in range(a, min(n1, col1) + 1)) / total)


def unitario(dx: float, dy: float) -> Optional[Tuple[float, float]]:
    """Vector unitario, o None si el desplazamiento es < `DESPLAZAMIENTO_...`."""
    n = math.hypot(dx, dy)
    if n < DESPLAZAMIENTO_DIRECCION_M:
        return None
    return dx / n, dy / n


def direccion_en_entorno(v: Tuple[float, float]) -> Tuple[float, float]:
    """Una dirección del marco lab, rotada al del entorno (la escala no la cambia)."""
    c, s = math.cos(cfg.ROTACION_MARCO_RAD), math.sin(cfg.ROTACION_MARCO_RAD)
    return c * v[0] - s * v[1], s * v[0] + c * v[1]


def normal_saliente(lado_idx: int) -> Tuple[float, float]:
    """Normal hacia afuera de cada lado: (x mín, x máx, y mín, y máx)."""
    return ((-1.0, 0.0), (1.0, 0.0), (0.0, -1.0), (0.0, 1.0))[lado_idx]


def clase_de_transicion(tipo: str, direccion: Optional[Tuple[float, float]],
                        normal: Tuple[float, float]) -> Tuple[str, Optional[float]]:
    """
    ("perpendicular" | "oblicua" | "sin_direccion", ángulo en grados) de una
    transición respecto de la normal SALIENTE de su pared: una entrada
    perpendicular va hacia la pared; una salida perpendicular, alejándose.
    """
    if direccion is None:
        return "sin_direccion", None
    sentido = 1.0 if tipo == "entrada" else -1.0
    cos = sentido * (direccion[0] * normal[0] + direccion[1] * normal[1])
    angulo = math.degrees(math.acos(max(-1.0, min(1.0, cos))))
    return ("perpendicular" if angulo <= ANGULO_PERPENDICULAR_DEG
            else "oblicua"), angulo


def reduccion_exp_n(w: Optional[float]) -> float:
    """Lo que una franja de ancho w resta a un lado, convención del Exp N."""
    if w is None:
        return 0.0
    return max(0.0, float(w) + ELE_A_M - D_SEGURA_PARED_M)


def origen_por_defecto() -> str:
    """"simulador" si la configuración apunta al simulador local."""
    return "simulador" if cfg.SIMULADOR_ACTIVO else "robotat"


def rotulo_origen(origen: str) -> str:
    """La marca visible de lo que NO es dato del Robotat ("" si lo es)."""
    if origen not in ORIGENES:
        raise ValueError(f"origen desconocido: {origen!r}")
    return ROTULOS_ORIGEN.get(origen, "")


# =============================================================================
# REJILLA Y RECORRIDOS
# =============================================================================

@dataclass(frozen=True)
class Rejilla:
    """Celdas cuadradas de lado `celda` sobre un rectángulo del marco lab."""

    x_min: float
    x_max: float
    y_min: float
    y_max: float
    celda: float = CELDA_POR_DEFECTO_M

    @property
    def n_x(self) -> int:
        return max(1, math.ceil((self.x_max - self.x_min) / self.celda - 1e-9))

    @property
    def n_y(self) -> int:
        return max(1, math.ceil((self.y_max - self.y_min) / self.celda - 1e-9))

    @property
    def total(self) -> int:
        return self.n_x * self.n_y

    def indice(self, x: float, y: float) -> Optional[Indice]:
        """Celda de (x, y), o None si cae fuera del rectángulo."""
        if not (self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max):
            return None
        ix = min(int((x - self.x_min) / self.celda), self.n_x - 1)
        iy = min(int((y - self.y_min) / self.celda), self.n_y - 1)
        return ix, iy

    def limites(self, ix: int, iy: int) -> Rect:
        x0 = self.x_min + ix * self.celda
        y0 = self.y_min + iy * self.celda
        return (x0, min(x0 + self.celda, self.x_max),
                y0, min(y0 + self.celda, self.y_max))

    def centro(self, ix: int, iy: int) -> Tuple[float, float]:
        x0, x1, y0, y1 = self.limites(ix, iy)
        return (x0 + x1) / 2.0, (y0 + y1) / 2.0

    def celdas_del_segmento(self, p: Tuple[float, float],
                            q: Tuple[float, float]) -> List[Indice]:
        """Celdas que cruza el segmento p→q, en orden (muestreo a celda/20)."""
        largo = math.hypot(q[0] - p[0], q[1] - p[1])
        pasos = max(1, int(math.ceil(largo / (self.celda / 20.0))))
        vistas: List[Indice] = []
        for k in range(pasos + 1):
            f = k / pasos
            idx = self.indice(p[0] + f * (q[0] - p[0]), p[1] + f * (q[1] - p[1]))
            if idx is not None and idx not in vistas:
                vistas.append(idx)
        return vistas


def orden_de_recorrido(rejilla: Rejilla, modo: str = "anillos") -> List[Indice]:
    """
    El recorrido de TODA la plataforma: cada celda una vez.
      · "anillos": de afuera hacia adentro, cada anillo en sentido horario
        desde la esquina (x mín, y mín). El perímetro va primero.
      · "serpentina": filas a lo largo de x, de y mín a y máx, alternando el
        sentido.
    (El peine no recorre celdas sino pases: ver `pases_peine`.)
    """
    nx, ny = rejilla.n_x, rejilla.n_y
    if modo == "serpentina":
        orden: List[Indice] = []
        for iy in range(ny):
            columnas = range(nx) if iy % 2 == 0 else range(nx - 1, -1, -1)
            orden.extend((ix, iy) for ix in columnas)
        return orden
    if modo != "anillos":
        raise ValueError(f"orden de recorrido desconocido: {modo!r}")
    orden = []
    vistos: Set[Indice] = set()
    k = 0
    while True:
        x0, x1, y0, y1 = k, nx - 1 - k, k, ny - 1 - k
        if x0 > x1 or y0 > y1:
            break
        anillo = [(ix, y0) for ix in range(x0, x1 + 1)]
        anillo += [(x1, iy) for iy in range(y0 + 1, y1 + 1)]
        if y1 > y0:
            anillo += [(ix, y1) for ix in range(x1 - 1, x0 - 1, -1)]
        if x1 > x0:
            anillo += [(x0, iy) for iy in range(y1 - 1, y0, -1)]
        for c in anillo:
            if c not in vistos:
                vistos.add(c)
                orden.append(c)
        k += 1
    return orden


@dataclass(frozen=True)
class Pase:
    """Un pase del peine: perpendicular a una pared de la arena, en un tramo."""

    lado: str
    k: int
    u_desde: float
    u_hasta: float
    desde_lab: Tuple[float, float]
    hasta_lab: Tuple[float, float]
    recortado: bool

    def texto(self) -> str:
        return (f"pase {self.lado} tramo {self.u_desde:.1f}–{self.u_hasta:.1f} m: "
                f"de lab ({self.desde_lab[0]:+.2f}, {self.desde_lab[1]:+.2f}) "
                f"a ({self.hasta_lab[0]:+.2f}, {self.hasta_lab[1]:+.2f})"
                + (" [recortado por el borde de la plataforma]"
                   if self.recortado else ""))


def pases_peine(plataforma: Rect) -> List[Pase]:
    """
    Un pase por tramo de `SEGMENTO_LADO_M` de cada pared de la arena, en el
    orden y=0, x=W, y=H, x=0. Cada uno, del centro del tramo a
    `PEINE_DESDE_M` adentro, en perpendicular, hasta `PEINE_HASTA_M` (afuera)
    —recortado para quedar a `BORDE_SEGURO_M` adentro de la plataforma—.
    """
    wx, wy = float(cfg.ARENA_WX_M), float(cfg.ARENA_WY_M)
    n0, n1, n2, n3 = nombres_lados("arena")
    px0, px1, py0, py1 = plataforma
    seguro = (px0 + BORDE_SEGURO_M, px1 - BORDE_SEGURO_M,
              py0 + BORDE_SEGURO_M, py1 - BORDE_SEGURO_M)

    def adentro(p: Tuple[float, float]) -> bool:
        return seguro[0] <= p[0] <= seguro[1] and seguro[2] <= p[1] <= seguro[3]

    lados = [  # (nombre, largo, punto del entorno a distancia d y posición u)
        (n2, wx, lambda u, d: (u, d)),
        (n1, wy, lambda u, d: (wx - d, u)),
        (n3, wx, lambda u, d: (u, wy - d)),
        (n0, wy, lambda u, d: (d, u)),
    ]
    pases: List[Pase] = []
    for nombre, largo, punto in lados:
        n = max(1, math.ceil(largo / SEGMENTO_LADO_M - 1e-9))
        for k in range(n):
            u0, u1 = k * SEGMENTO_LADO_M, min((k + 1) * SEGMENTO_LADO_M, largo)
            uc = (u0 + u1) / 2.0
            desde = env_a_lab_xy(*punto(uc, PEINE_DESDE_M))
            hasta = env_a_lab_xy(*punto(uc, PEINE_HASTA_M))
            recortado = False
            # Recortar el tramo final para no salir de la plataforma: se
            # retrocede desde `hasta` hacia `desde` hasta quedar adentro.
            if not adentro(hasta):
                recortado = True
                for j in range(1, 101):
                    f = 1.0 - j / 100.0
                    q = (desde[0] + f * (hasta[0] - desde[0]),
                         desde[1] + f * (hasta[1] - desde[1]))
                    if adentro(q):
                        hasta = q
                        break
                else:
                    hasta = desde
            pases.append(Pase(nombre, k, u0, u1, desde, hasta, recortado))
    return pases


# =============================================================================
# EL MAPA
# =============================================================================

@dataclass
class Celda:
    """Lo que se vio en una celda."""

    vivas: int = 0
    repetidas: int = 0
    retenciones_cortas: int = 0
    inicios: int = 0
    fines: int = 0
    cruces: int = 0
    marcadores: Set[int] = field(default_factory=set)


@dataclass
class Congelamiento:
    """Un congelamiento de un marcador, en el marco lab."""

    marcador: int
    t_inicio: float
    x0: float
    y0: float
    t_fin: Optional[float] = None
    x1: Optional[float] = None
    y1: Optional[float] = None
    celdas: List[Indice] = field(default_factory=list)
    #: Dirección (unitaria, marco lab) al perderse y al volver; None si el
    #: robot casi no se movía.
    dir_entrada: Optional[Tuple[float, float]] = None
    dir_salida: Optional[Tuple[float, float]] = None

    @property
    def tramo_m(self) -> Optional[float]:
        """Largo del tramo que no se vio (entrada → salida), si terminó."""
        if self.x1 is None or self.y1 is None:
            return None
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)


class MapaSeguimiento:
    """
    Acumula las muestras de la sonda por celda y arma el mapa.

    `observar` recibe cada muestra VÁLIDA de cada marcador (marco lab) y si
    su fila completa repite la anterior. Con `umbral` repeticiones seguidas
    empieza un congelamiento —en la celda de la pose retenida— y termina
    cuando el marcador vuelve a verse.

    `orden`: "anillos" o "serpentina" guían celda por celda; "peine" guía
    pase por pase (ver `pases_peine`).
    """

    def __init__(self, rejilla: Rejilla, umbral: int,
                 plataforma: Optional[Rect] = None,
                 orden: str = "anillos") -> None:
        if umbral < 1:
            raise ValueError("el umbral tiene que ser ≥ 1")
        if orden not in ("anillos", "serpentina", "peine"):
            raise ValueError(f"orden de recorrido desconocido: {orden!r}")
        self.rejilla = rejilla
        self.umbral = int(umbral)
        self.plataforma: Rect = plataforma or (rejilla.x_min, rejilla.x_max,
                                               rejilla.y_min, rejilla.y_max)
        self.modo_orden = orden
        # Las celdas se recorren siempre en algún orden (lectura, contraste);
        # con el peine, la guía es por pases.
        self.orden = orden_de_recorrido(
            rejilla, "anillos" if orden == "peine" else orden)
        self.pases: List[Pase] = (pases_peine(self.plataforma)
                                  if orden == "peine" else [])
        self.celdas: Dict[Indice, Celda] = {}
        self.congelamientos: List[Congelamiento] = []
        self.muestras_fuera: int = 0
        self._racha: Dict[int, int] = {}
        self._retenida: Dict[int, Tuple[float, float]] = {}
        self._abierto: Dict[int, Congelamiento] = {}
        # (referencia, lado, tramo) → [distancia mínima a la pared de una
        # muestra VIVA, muestras vivas, vivas a < CERCA_PARED_M]: de acá sale
        # "vivo hasta X m" y la exposición del contraste esquinas/medio.
        self._vivo_lado: Dict[Tuple[str, str, int], List[float]] = {}
        # Últimas muestras vivas por marcador (dirección de la entrada), y
        # salidas cuya dirección todavía se está midiendo.
        self._recientes: Dict[int, List[Tuple[float, float]]] = {}
        self._salida_pendiente: Dict[int, Tuple[Congelamiento,
                                                List[Tuple[float, float]]]] = {}

    # ── marcos de referencia ─────────────────────────────────────────────
    def _rect(self, referencia: str) -> Rect:
        if referencia == "arena":
            return arena_env()
        if referencia == "plataforma":
            return self.plataforma
        raise ValueError(f"referencia desconocida: {referencia!r}")

    @staticmethod
    def _en_referencia(referencia: str, x: float, y: float
                       ) -> Tuple[float, float]:
        return lab_a_env_xy(x, y) if referencia == "arena" else (x, y)

    def _lado(self, referencia: str, x_lab: float, y_lab: float
              ) -> Tuple[str, float, int]:
        """(lado, distancia a él, tramo) de un punto del marco lab."""
        px, py = self._en_referencia(referencia, x_lab, y_lab)
        lado, d, u, largo = lado_mas_cercano(px, py, self._rect(referencia),
                                             nombres_lados(referencia))
        return lado, d, tramo_de(u, largo)

    # ── acumulación ──────────────────────────────────────────────────────
    def _celda(self, x: float, y: float) -> Optional[Celda]:
        idx = self.rejilla.indice(x, y)
        if idx is None:
            return None
        return self.celdas.setdefault(idx, Celda())

    def observar(self, marcador: int, t: float, x: float, y: float,
                 repite: bool) -> str:
        """
        Una muestra válida de un marcador. Devuelve "inicio" cuando la racha
        de repeticiones llega al umbral, "fin" cuando el marcador vuelve a
        verse tras un congelamiento, y "" en los demás casos.
        """
        marcador = int(marcador)
        if self.rejilla.indice(x, y) is None:
            self.muestras_fuera += 1
        if repite:
            racha = self._racha.get(marcador, 0) + 1
            self._racha[marcador] = racha
            if racha == 1:
                self._retenida[marcador] = (float(x), float(y))
            c = self._celda(x, y)
            if c is not None:
                c.repetidas += 1
            if racha == self.umbral:
                cong = Congelamiento(marcador, float(t), float(x), float(y))
                previas = self._recientes.get(marcador, [])
                if len(previas) >= 2:
                    cong.dir_entrada = unitario(previas[-1][0] - previas[0][0],
                                                previas[-1][1] - previas[0][1])
                self._cerrar_salida(marcador)
                self._abierto[marcador] = cong
                self.congelamientos.append(cong)
                if c is not None:
                    c.inicios += 1
                return "inicio"
            return ""

        racha = self._racha.pop(marcador, 0)
        retenida = self._retenida.pop(marcador, None)
        evento = ""
        cong = self._abierto.pop(marcador, None)
        if cong is not None:
            cong.t_fin, cong.x1, cong.y1 = float(t), float(x), float(y)
            cong.celdas = self.rejilla.celdas_del_segmento((cong.x0, cong.y0),
                                                           (cong.x1, cong.y1))
            for idx in cong.celdas:
                self.celdas.setdefault(idx, Celda()).cruces += 1
            c_fin = self._celda(x, y)
            if c_fin is not None:
                c_fin.fines += 1
            evento = "fin"
        elif 0 < racha < self.umbral and retenida is not None:
            c_ret = self._celda(*retenida)
            if c_ret is not None:
                c_ret.retenciones_cortas += 1
        c = self._celda(x, y)
        if c is not None:
            c.vivas += 1
            c.marcadores.add(marcador)
        for referencia in REFERENCIAS:
            lado, d, k = self._lado(referencia, x, y)
            if d >= 0.0:
                v = self._vivo_lado.setdefault((referencia, lado, k),
                                               [math.inf, 0, 0])
                v[0] = min(v[0], d)
                v[1] += 1
                v[2] += int(d < CERCA_PARED_M)
        punto = (float(x), float(y))
        recientes = self._recientes.setdefault(marcador, [])
        recientes.append(punto)
        del recientes[:-MUESTRAS_DIRECCION]
        if evento == "fin":
            self._cerrar_salida(marcador)
            self._salida_pendiente[marcador] = (cong, [punto])
            self._recientes[marcador] = [punto]
        elif marcador in self._salida_pendiente:
            self._salida_pendiente[marcador][1].append(punto)
            if len(self._salida_pendiente[marcador][1]) >= MUESTRAS_DIRECCION:
                self._cerrar_salida(marcador)
        return evento

    def _cerrar_salida(self, marcador: int) -> None:
        """Fija la dirección de una salida con las muestras que haya."""
        pendiente = self._salida_pendiente.pop(marcador, None)
        if pendiente is None:
            return
        cong, puntos = pendiente
        if len(puntos) >= 2:
            cong.dir_salida = unitario(puntos[-1][0] - puntos[0][0],
                                       puntos[-1][1] - puntos[0][1])

    # ── lectura: celdas ──────────────────────────────────────────────────
    def estado(self, idx: Indice) -> str:
        c = self.celdas.get(idx)
        if c is None:
            return "sin_visitar"
        marcada = bool(c.inicios or c.fines or c.cruces)
        if c.vivas and marcada:
            return "borde"
        if c.vivas:
            return "viva"
        if marcada:
            return "ciega"
        return "sin_visitar"

    def visitadas(self) -> int:
        return sum(1 for idx in self.orden if self.estado(idx) != "sin_visitar")

    def congelamientos_de(self, marcador: int) -> List[Congelamiento]:
        """Los congelamientos de un marcador, en orden."""
        return [k for k in self.congelamientos if k.marcador == int(marcador)]

    def proxima_sin_visitar(self) -> Optional[Indice]:
        """La primera celda del recorrido que todavía no se visitó."""
        for idx in self.orden:
            if self.estado(idx) == "sin_visitar":
                return idx
        return None

    # ── lectura: peine ───────────────────────────────────────────────────
    def transiciones(self) -> List[Tuple[str, float, float]]:
        """("entrada" | "salida", x_lab, y_lab) de cada congelamiento."""
        return [(tipo, x, y) for tipo, x, y, _m, _d in
                self.transiciones_con_direccion()]

    def transiciones_con_direccion(
            self) -> List[Tuple[str, float, float, int,
                                Optional[Tuple[float, float]]]]:
        """
        (tipo, x_lab, y_lab, marcador, dirección lab) de cada congelamiento.
        La dirección de una salida todavía en medición se estima con las
        muestras que ya haya.
        """
        pendientes = {id(c): pts for c, pts in self._salida_pendiente.values()}
        puntos = []
        for k in self.congelamientos:
            puntos.append(("entrada", k.x0, k.y0, k.marcador, k.dir_entrada))
            if k.x1 is not None and k.y1 is not None:
                direccion = k.dir_salida
                pts = pendientes.get(id(k))
                if direccion is None and pts and len(pts) >= 2:
                    direccion = unitario(pts[-1][0] - pts[0][0],
                                         pts[-1][1] - pts[0][1])
                puntos.append(("salida", k.x1, k.y1, k.marcador, direccion))
        return puntos

    @staticmethod
    def _en_pared(lado: str, x_lab: float, y_lab: float
                  ) -> Tuple[float, float]:
        """(distancia a ESA pared de la arena, posición a lo largo de ella)."""
        xe, ye = lab_a_env_xy(x_lab, y_lab)
        wx, wy = float(cfg.ARENA_WX_M), float(cfg.ARENA_WY_M)
        n0, n1, n2, _n3 = nombres_lados("arena")
        if lado == n0:
            return xe, ye
        if lado == n1:
            return wx - xe, ye
        if lado == n2:
            return ye, xe
        return wy - ye, xe

    def pase_hecho(self, pase: Pase) -> bool:
        """
        Hubo una transición SOBRE el pase —a menos de `TOLERANCIA_PASE_M` de
        su línea, medida contra su propia pared y no contra la más cercana: en
        los tramos de esquina el borde interior de la franja puede estar más
        cerca de la pared vecina y la guía se trabaría—, o se lo vio vivo a
        ≤ `LLEGO_A_LA_PARED_M` de la pared.
        """
        u_linea = (pase.u_desde + pase.u_hasta) / 2.0
        for _tipo, x, y in self.transiciones():
            d, u = self._en_pared(pase.lado, x, y)
            if (abs(u - u_linea) < TOLERANCIA_PASE_M
                    and -0.10 <= d <= PEINE_DESDE_M + 0.10):
                return True
        v = self._vivo_lado.get(("arena", pase.lado, pase.k))
        return v is not None and v[0] <= LLEGO_A_LA_PARED_M

    def proximo_pase(self) -> Optional[Pase]:
        for pase in self.pases:
            if not self.pase_hecho(pase):
                return pase
        return None

    def pases_hechos(self) -> int:
        return sum(1 for p in self.pases if self.pase_hecho(p))

    def destino(self) -> str:
        """Adónde llevar el robot ahora, en texto (la guía de la sonda)."""
        if self.modo_orden == "peine":
            pase = self.proximo_pase()
            return ("peine completo" if pase is None else
                    f"{self.pases_hechos()}/{len(self.pases)} pases · próximo "
                    f"{pase.texto()}")
        proxima = self.proxima_sin_visitar()
        return (f"{self.visitadas()}/{self.rejilla.total} celdas · "
                + ("recorrido completo" if proxima is None else
                   "próxima ({:+.2f}, {:+.2f}) lab".format(
                       *self.rejilla.centro(*proxima))))

    def celda_destino(self) -> Optional[Indice]:
        """La celda que se marca con → en el mapa ASCII."""
        if self.modo_orden == "peine":
            pase = self.proximo_pase()
            return None if pase is None else self.rejilla.indice(*pase.desde_lab)
        return self.proxima_sin_visitar()

    # ── ancho de la franja por lado ──────────────────────────────────────
    def franja_por_lado(self, referencia: str = "arena") -> Dict[str, Any]:
        """
        Por lado de la referencia: transiciones, ancho mediano y máximo (su
        distancia a la pared), y el perfil por tramos. Para la arena, además,
        la arena libre de franja con el ancho máximo de cada lado.
        """
        rect = self._rect(referencia)
        nombres = nombres_lados(referencia)
        x0, x1, y0, y1 = rect
        largos = {nombres[0]: y1 - y0, nombres[1]: y1 - y0,
                  nombres[2]: x1 - x0, nombres[3]: x1 - x0}
        # (d, tramo, tipo, clase, ángulo, marcador) por lado
        por_lado: Dict[str, List[Tuple[float, int, str, str, Optional[float],
                                       int]]] = {n: [] for n in nombres}
        fuera = 0
        for tipo, x, y, marcador, direccion in self.transiciones_con_direccion():
            lado, d, k = self._lado(referencia, x, y)
            if d < 0.0:
                fuera += 1
                continue
            if direccion is not None and referencia == "arena":
                direccion = direccion_en_entorno(direccion)
            # Atribución: a la pared hacia la que AVANZABA en perpendicular
            # (o desde la que se alejaba, al volver), si hay una a
            # ≤ PEINE_DESDE_M; si no, a la más cercana. La auditoría del
            # 24-09: 6 de las 7 entradas paralelas a la pared más cercana iban
            # de frente hacia la pared ADYACENTE, a 0.43–0.70 m de ella: eran
            # entradas por la esquina, y su profundidad es respecto de ésa.
            px, py = self._en_referencia(referencia, x, y)
            perpendiculares = []
            for i, nombre in enumerate(nombres):
                d_i, u_i, largo_i = distancia_a_lado(px, py, rect, i)
                if 0.0 <= d_i <= PEINE_DESDE_M:
                    clase_i, ang_i = clase_de_transicion(
                        tipo, direccion, normal_saliente(i))
                    if clase_i == "perpendicular":
                        perpendiculares.append((d_i, nombre, u_i, largo_i,
                                                ang_i))
            if perpendiculares:
                d, lado, u, largo_i, angulo = min(perpendiculares)
                k = tramo_de(u, largo_i)
                clase = "perpendicular"
            else:
                clase, angulo = clase_de_transicion(
                    tipo, direccion, normal_saliente(nombres.index(lado)))
            por_lado[lado].append((d, k, tipo, clase, angulo, marcador))
        lados = []
        for nombre in nombres:
            largo = largos[nombre]
            trans = por_lado[nombre]
            n_tramos = max(1, math.ceil(largo / SEGMENTO_LADO_M - 1e-9))
            tramos = []
            for k in range(n_tramos):
                perp = [tr[0] for tr in trans
                        if tr[1] == k and tr[3] == "perpendicular"]
                otras = [tr[0] for tr in trans
                         if tr[1] == k and tr[3] != "perpendicular"]
                v = self._vivo_lado.get((referencia, nombre, k))
                tramos.append({
                    "k": k, "desde_m": round(k * SEGMENTO_LADO_M, 3),
                    "hasta_m": round(min((k + 1) * SEGMENTO_LADO_M, largo), 3),
                    "transiciones": len(perp) + len(otras),
                    "inicios": sum(1 for tr in trans
                                   if tr[1] == k and tr[2] == "entrada"),
                    "franja_m": round(max(perp), 4) if perp else None,
                    "cota_m": round(max(otras), 4) if otras else None,
                    "vivo_min_m": round(v[0], 4) if v else None,
                    "vivas": int(v[1]) if v else 0,
                    "vivas_cerca": int(v[2]) if v else 0,
                })
            con_datos = sum(1 for t in tramos if t["transiciones"] or (
                t["vivo_min_m"] is not None
                and t["vivo_min_m"] < VISITA_LADO_M))
            ds_perp = sorted(tr[0] for tr in trans if tr[3] == "perpendicular")
            ds_otras = sorted(tr[0] for tr in trans if tr[3] != "perpendicular")
            ancho_es_cota = False
            if ds_perp:
                ancho: Optional[float] = max(ds_perp)
            elif ds_otras:
                ancho, ancho_es_cota = max(ds_otras), True
            elif any(t["vivo_min_m"] is not None
                     and t["vivo_min_m"] <= SIN_FRANJA_SI_VIVO_A_M
                     for t in tramos):
                ancho = 0.0
            else:
                ancho = None
            por_marcador: Dict[str, int] = {}
            for tr in trans:
                if tr[2] == "entrada":
                    por_marcador[str(tr[5])] = por_marcador.get(str(tr[5]), 0) + 1
            lados.append({
                "lado": nombre, "largo_m": round(largo, 4),
                "transiciones": len(trans),
                "perpendiculares": len(ds_perp),
                "ancho_mediano_m": (round(statistics.median(ds_perp), 4)
                                    if ds_perp else None),
                "ancho_max_m": round(max(ds_perp), 4) if ds_perp else None,
                "cota_inferior_m": (round(max(ds_otras), 4)
                                    if ds_otras else None),
                "ancho_m": None if ancho is None else round(ancho, 4),
                "ancho_es_cota": ancho_es_cota,
                "inicios_por_marcador": por_marcador,
                "detalle": [{"d_m": round(tr[0], 4), "tramo": tr[1],
                             "tipo": tr[2], "clase": tr[3],
                             "angulo_deg": (None if tr[4] is None
                                            else round(tr[4], 1)),
                             "marcador": tr[5]} for tr in trans],
                "tramos_con_franja": sum(1 for t in tramos
                                         if t["transiciones"]),
                "tramos_con_datos": con_datos, "tramos": tramos,
            })
        salida: Dict[str, Any] = {"referencia": referencia,
                                  "rect": [round(v, 4) for v in rect],
                                  "lados": lados,
                                  "transiciones_fuera": fuera}
        if referencia == "arena":
            w = {l["lado"]: l["ancho_m"] for l in lados}
            ancho_x = (x1 - x0) - (w[nombres[0]] or 0.0) - (w[nombres[1]] or 0.0)
            ancho_y = (y1 - y0) - (w[nombres[2]] or 0.0) - (w[nombres[3]] or 0.0)
            area = max(0.0, ancho_x) * max(0.0, ancho_y)
            total = (x1 - x0) * (y1 - y0)
            eq_x = (x1 - x0) - reduccion_exp_n(w[nombres[0]]) \
                - reduccion_exp_n(w[nombres[1]])
            eq_y = (y1 - y0) - reduccion_exp_n(w[nombres[2]]) \
                - reduccion_exp_n(w[nombres[3]])
            salida["libre"] = {
                "ancho_x_m": round(ancho_x, 4), "ancho_y_m": round(ancho_y, 4),
                "area_m2": round(area, 4),
                "fraccion": round(area / total, 4) if total else None,
                "equivalente_exp_n_x_m": round(eq_x, 4),
                "equivalente_exp_n_y_m": round(eq_y, 4),
                "lados_sin_datos": [n for n in nombres if w[n] is None],
                "lados_con_cota": [l["lado"] for l in lados
                                   if l["ancho_es_cota"]],
                "tramos_con_datos": sum(l["tramos_con_datos"] for l in lados),
                "tramos_total": sum(len(l["tramos"]) for l in lados),
                "exp_n_area_m2": round(ARENA_EXP_N_M ** 2, 4),
                "exp_n_fraccion": round(ARENA_EXP_N_M ** 2 / total, 4)
                                  if total else None,
            }
            # Esquinas (tramo extremo de cada lado) contra tramo medio.
            ext = {"inicios": 0, "vivas_cerca": 0}
            med = {"inicios": 0, "vivas_cerca": 0}
            for l in lados:
                ultimo = len(l["tramos"]) - 1
                for t in l["tramos"]:
                    g = ext if t["k"] in (0, ultimo) else med
                    g["inicios"] += t["inicios"]
                    g["vivas_cerca"] += t["vivas_cerca"]
            for g in (ext, med):
                g["inicios_por_1000_vivas"] = (
                    round(1000.0 * g["inicios"] / g["vivas_cerca"], 3)
                    if g["vivas_cerca"] else None)
            salida["esquinas_vs_medio"] = {
                "esquinas": ext, "medio": med,
                "definicion": (f"esquinas = el tramo de {SEGMENTO_LADO_M:g} m "
                               f"de cada extremo de cada lado; vivas a "
                               f"< {CERCA_PARED_M:g} m de la pared"),
            }
        return salida

    def lineas_franja(self) -> List[str]:
        """El ancho de la franja por lado, para la consola."""
        lineas = ["  ANCHO DE LA FRANJA POR LADO — ancho = distancia a la pared "
                  "de las transiciones PERPENDICULARES (±"
                  f"{ANGULO_PERPENDICULAR_DEG:g}°) donde el marcador se perdió "
                  "o volvió a verse; las demás dan sólo una cota inferior",
                  f"  (tramos de {SEGMENTO_LADO_M:.1f} m; un tramo tiene datos "
                  f"con una transición o visto vivo a < {VISITA_LADO_M:.2f} m "
                  f"de la pared)"]
        for referencia, titulo in (("arena", "arena (marco del entorno)"),
                                   ("plataforma", "plataforma (marco lab)")):
            r = self.franja_por_lado(referencia)
            lineas.append(f"  {titulo}:")
            lineas.append("    lado     transic. (perp.)  ancho mediana / máx "
                          "(m)  cota inf.  tramos con franja / con datos / "
                          "total  inicios por marcador")
            for l in r["lados"]:
                med = ("—" if l["ancho_mediano_m"] is None
                       else f"{l['ancho_mediano_m']:.2f}")
                mx = ("—" if l["ancho_max_m"] is None
                      else f"{l['ancho_max_m']:.2f}")
                cota = ("—" if l["cota_inferior_m"] is None
                        else f"{l['cota_inferior_m']:.2f}")
                marcadores = (", ".join(f"m{m}: {n}" for m, n in
                                        sorted(l["inicios_por_marcador"]
                                               .items())) or "—")
                lineas.append(
                    f"    {l['lado']:<7}  {l['transiciones']:>8} "
                    f"({l['perpendiculares']})  {med:>12} / {mx:<9}  "
                    f"{cota:>9}  {l['tramos_con_franja']:>6} / "
                    f"{l['tramos_con_datos']} / {len(l['tramos'])}  "
                    f"{marcadores}")
            if referencia == "arena":
                for l in r["lados"]:
                    perfil = []
                    for t in l["tramos"]:
                        if t["franja_m"] is not None:
                            s = f"{t['franja_m']:.2f}"
                        elif t["cota_m"] is not None:
                            s = f"≥{t['cota_m']:.2f}"
                        elif (t["vivo_min_m"] is not None
                              and t["vivo_min_m"] < VISITA_LADO_M):
                            s = f"vivo a {t['vivo_min_m']:.2f}"
                        else:
                            s = "—"
                        perfil.append(f"{t['desde_m']:.1f}–{t['hasta_m']:.1f}: "
                                      f"{s}")
                    lineas.append(f"    perfil {l['lado']}: " + " · ".join(perfil))
                em = r["esquinas_vs_medio"]

                def tasa(g: Dict[str, Any]) -> str:
                    v = g["inicios_por_1000_vivas"]
                    return (f"{g['inicios']}/{g['vivas_cerca']}"
                            + ("" if v is None else f" = {v:.2f} ‰"))

                lineas.append(f"  esquinas vs tramo medio (inicios / muestras "
                              f"vivas a < {CERCA_PARED_M:g} m): esquinas "
                              f"{tasa(em['esquinas'])} · medio "
                              f"{tasa(em['medio'])}  ({em['definicion']})")
                lib = r["libre"]
                estado = ("" if not lib["lados_sin_datos"]
                          and lib["tramos_con_datos"] == lib["tramos_total"]
                          else f" · INCOMPLETO: {lib['tramos_con_datos']}/"
                               f"{lib['tramos_total']} tramos con datos"
                               + (f", lados sin datos "
                                  f"{', '.join(lib['lados_sin_datos'])} "
                                  f"(contados como 0)"
                                  if lib["lados_sin_datos"] else ""))
                if lib["lados_con_cota"]:
                    estado += (f" · con COTA inferior (sin transiciones "
                               f"perpendiculares): "
                               f"{', '.join(lib['lados_con_cota'])}")
                lineas.append(
                    f"  arena libre SI la franja fuera UNIFORME en cada lado "
                    f"(con su ancho máximo; centro fuera de ella): {lib['ancho_x_m']:.2f} × "
                    f"{lib['ancho_y_m']:.2f} m = {lib['area_m2']:.2f} m² "
                    f"({100 * lib['fraccion']:.1f} % de la arena){estado}")
                lineas.append(
                    f"  arena equivalente, convención del Exp N (el CBF ya "
                    f"deja el punto de mira a {D_SEGURA_PARED_M:g} m; cada "
                    f"lado resta máx(0, w + {ELE_A_M:g} − "
                    f"{D_SEGURA_PARED_M:g})): "
                    f"{lib['equivalente_exp_n_x_m']:.2f} × "
                    f"{lib['equivalente_exp_n_y_m']:.2f} m · el Exp N "
                    f"rechazó {ARENA_EXP_N_M:g} × {ARENA_EXP_N_M:g}")
            if r["transiciones_fuera"]:
                lineas.append(f"    ({r['transiciones_fuera']} transiciones "
                              f"fuera de la {referencia})")
        return lineas

    # ── salidas ──────────────────────────────────────────────────────────
    def ascii(self, posiciones: Optional[Dict[int, Tuple[float, float]]] = None
              ) -> List[str]:
        """
        El mapa en texto, y creciente hacia arriba: · sin visitar, ○ viva,
        ◐ borde de un punto ciego, █ ciega, @ un marcador ahora, → adónde ir
        (la próxima celda, o el inicio del próximo pase del peine).
        """
        marcas: Dict[Indice, str] = {}
        for x, y in (posiciones or {}).values():
            idx = self.rejilla.indice(x, y)
            if idx is not None:
                marcas[idx] = "@"
        destino = self.celda_destino()
        lineas = []
        for iy in range(self.rejilla.n_y - 1, -1, -1):
            _xc, yc = self.rejilla.centro(0, iy)
            fila = "".join(
                marcas.get((ix, iy))
                or ("→" if (ix, iy) == destino
                    else SIMBOLOS[self.estado((ix, iy))])
                for ix in range(self.rejilla.n_x))
            lineas.append(f"  y={yc:+.2f} |{fila}|")
        lineas.append(f"         x: {self.rejilla.x_min:+.2f} … "
                      f"{self.rejilla.x_max:+.2f} (celda "
                      f"{self.rejilla.celda:.2f} m) · ○ viva · ◐ borde · "
                      f"█ ciega · · sin visitar · @ robot · → destino")
        return lineas

    def fila_de_celda(self, idx: Indice, origen: str = "robotat"
                      ) -> Dict[str, Any]:
        """La fila del CSV de una celda."""
        ix, iy = idx
        x0, x1, y0, y1 = self.rejilla.limites(ix, iy)
        xc, yc = self.rejilla.centro(ix, iy)
        d, borde, dimension = borde_mas_cercano(xc, yc, self.plataforma)
        pared, d_arena, _k = self._lado("arena", xc, yc)
        c = self.celdas.get(idx, Celda())
        return {
            "origen": origen,
            "ix": ix, "iy": iy, "x_min": round(x0, 4), "x_max": round(x1, 4),
            "y_min": round(y0, 4), "y_max": round(y1, 4),
            "x_centro": round(xc, 4), "y_centro": round(yc, 4),
            "estado": self.estado(idx), "vivas": c.vivas,
            "repetidas": c.repetidas,
            "retenciones_cortas": c.retenciones_cortas,
            "inicios": c.inicios, "fines": c.fines, "cruces": c.cruces,
            "marcadores": " ".join(str(m) for m in sorted(c.marcadores)),
            "borde_plataforma": borde, "dimension_borde": dimension,
            "d_borde_plataforma_m": round(d, 4), "franja_borde": franja(d),
            "pared_arena": pared, "d_pared_arena_m": round(d_arena, 4),
        }

    def escribir_csv(self, salida: TextIO, origen: Optional[str] = None) -> int:
        """
        Una fila por celda de la rejilla, visitada o no, con su `origen`
        ("robotat", "simulador" o "sintetico"; por defecto, según la
        configuración). Devuelve cuántas.
        """
        origen = origen or origen_por_defecto()
        rotulo_origen(origen)                       # valida
        escritor = csv.DictWriter(salida, fieldnames=COLUMNAS_CSV_MAPA)
        escritor.writeheader()
        n = 0
        for iy in range(self.rejilla.n_y):
            for ix in range(self.rejilla.n_x):
                escritor.writerow(self.fila_de_celda((ix, iy), origen))
                n += 1
        return n

    def contraste(self) -> Dict[str, Any]:
        """
        La predicción de la dimensión corta, contra los datos. Por
        (dimensión del borde más cercano, franja de distancia): celdas
        visitadas, celdas con congelamiento ("borde" o "ciega"), inicios y
        muestras vivas; más la prueba de Fisher sobre las celdas a
        < `CERCA_DEL_BORDE_M`.
        """
        grupos: Dict[Tuple[str, str], Dict[str, int]] = {}
        cerca = {"corta": [0, 0], "larga": [0, 0]}   # [con congelamiento, sin]
        for idx in self.orden:
            est = self.estado(idx)
            if est == "sin_visitar":
                continue
            xc, yc = self.rejilla.centro(*idx)
            d, _borde, dimension = borde_mas_cercano(xc, yc, self.plataforma)
            g = grupos.setdefault((dimension, franja(d)),
                                  {"celdas_visitadas": 0,
                                   "celdas_con_congelamiento": 0,
                                   "inicios": 0, "muestras_vivas": 0})
            c = self.celdas.get(idx, Celda())
            con = est in ("borde", "ciega")
            g["celdas_visitadas"] += 1
            g["celdas_con_congelamiento"] += int(con)
            g["inicios"] += c.inicios
            g["muestras_vivas"] += c.vivas
            if 0.0 <= d < CERCA_DEL_BORDE_M:
                cerca[dimension][0 if con else 1] += 1
        filas = []
        for (dimension, fr), g in sorted(grupos.items()):
            vivas = g["muestras_vivas"]
            filas.append({"dimension_borde": dimension, "franja_borde": fr,
                          **g, "inicios_por_1000_vivas":
                              (1000.0 * g["inicios"] / vivas) if vivas else None})
        a, b = cerca["corta"]
        c_, d_ = cerca["larga"]
        # Sin celdas visitadas junto a los bordes de alguna de las dos
        # dimensiones no hay comparación: p = None, no un p = 1 que parezca
        # un resultado.
        hay_contraste = (a + b) > 0 and (c_ + d_) > 0
        return {
            "grupos": filas,
            "cerca_del_borde_m": CERCA_DEL_BORDE_M,
            "tabla_cerca": {"corta_con": a, "corta_sin": b,
                            "larga_con": c_, "larga_sin": d_},
            "p_fisher_corta_mayor": (fisher_unilateral(a, b, c_, d_)
                                     if hay_contraste else None),
            "congelamientos": len(self.congelamientos),
            "sin_terminar": sum(1 for k in self.congelamientos
                                if k.t_fin is None),
            "celdas_visitadas": self.visitadas(),
            "celdas_total": self.rejilla.total,
            "muestras_fuera_de_la_rejilla": self.muestras_fuera,
            "plataforma_lab": list(self.plataforma),
        }

    def lineas_contraste(self) -> List[str]:
        """El contraste de la dimensión corta, para la consola."""
        r = self.contraste()
        t = r["tabla_cerca"]
        lineas = [
            f"  celdas visitadas {r['celdas_visitadas']}/{r['celdas_total']} · "
            f"congelamientos {r['congelamientos']} "
            f"({r['sin_terminar']} sin volver a verse)",
            "  dimensión  franja (m)   visitadas  con congel.  inicios  "
            "inicios/1000 vivas",
        ]
        for g in r["grupos"]:
            tasa = g["inicios_por_1000_vivas"]
            lineas.append(
                f"  {g['dimension_borde']:<9}  {g['franja_borde']:<11}  "
                f"{g['celdas_visitadas']:>9}  "
                f"{g['celdas_con_congelamiento']:>11}  {g['inicios']:>7}  "
                f"{'—' if tasa is None else f'{tasa:.2f}':>18}")
        p = r["p_fisher_corta_mayor"]
        prueba = (f"Fisher unilateral (corta > larga) p = {p:.4f}"
                  if p is not None else
                  "SIN CONTRASTE: faltan celdas visitadas junto a los bordes "
                  "de una de las dos dimensiones")
        lineas.append(
            f"  a < {r['cerca_del_borde_m']:.2f} m del borde: dimensión corta "
            f"{t['corta_con']}/{t['corta_con'] + t['corta_sin']} celdas con "
            f"congelamiento, larga {t['larga_con']}/"
            f"{t['larga_con'] + t['larga_sin']} · {prueba}")
        lineas.append("  (celdas con congelamiento = estado borde o ciega; "
                      "franja = distancia del centro de la celda al borde de "
                      "la plataforma más cercano)")
        return lineas

    def figura(self, titulo: str = "", origen: Optional[str] = None) -> Any:
        """
        La figura del mapa (matplotlib): celdas, plataforma, arena, cada tramo
        a ciegas y la arena libre de franja. Lo que no es dato del Robotat
        lleva el rótulo cruzado sobre el mapa y en el título. Lanza
        ImportError si no hay matplotlib.
        """
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch, Rectangle

        origen = origen or origen_por_defecto()
        rotulo = rotulo_origen(origen)
        colores = {"sin_visitar": "#ffffff", "viva": "#b7e4c7",
                   "borde": "#f4a261", "ciega": "#9d0208"}
        fig, ax = plt.subplots(figsize=(10, 7.8))
        for iy in range(self.rejilla.n_y):
            for ix in range(self.rejilla.n_x):
                x0, x1, y0, y1 = self.rejilla.limites(ix, iy)
                ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0,
                                       facecolor=colores[self.estado((ix, iy))],
                                       edgecolor="#d0d0d0", linewidth=0.5))
        px0, px1, py0, py1 = self.plataforma
        ax.add_patch(Rectangle((px0, py0), px1 - px0, py1 - py0, fill=False,
                               edgecolor="black", linewidth=2.0))
        esquinas = arena_en_lab()
        ax.plot([p[0] for p in esquinas], [p[1] for p in esquinas], "--",
                color="#1d4ed8", linewidth=1.5)
        leyenda = [
            Patch(facecolor=colores["viva"], edgecolor="#999", label="viva"),
            Patch(facecolor=colores["borde"], edgecolor="#999",
                  label="borde de punto ciego"),
            Patch(facecolor=colores["ciega"], edgecolor="#999", label="ciega"),
            Patch(facecolor="white", edgecolor="#999", label="sin visitar"),
            Patch(facecolor="none", edgecolor="black", label="plataforma"),
            Patch(facecolor="none", edgecolor="#1d4ed8", linestyle="--",
                  label="arena (calibración)"),
        ]
        franja_arena = self.franja_por_lado("arena")
        if self.congelamientos:
            wx, wy = float(cfg.ARENA_WX_M), float(cfg.ARENA_WY_M)
            w = {l["lado"]: (l["ancho_m"] or 0.0)
                 for l in franja_arena["lados"]}
            n0, n1, n2, n3 = nombres_lados("arena")
            libre = [env_a_lab_xy(x, y) for x, y in (
                (w[n0], w[n2]), (wx - w[n1], w[n2]), (wx - w[n1], wy - w[n3]),
                (w[n0], wy - w[n3]), (w[n0], w[n2]))]
            ax.plot([p[0] for p in libre], [p[1] for p in libre], ":",
                    color="#15803d", linewidth=2.0)
            lib = franja_arena["libre"]
            leyenda.append(Patch(
                facecolor="none", edgecolor="#15803d", linestyle=":",
                label=f"arena libre si la franja fuera uniforme "
                      f"{lib['ancho_x_m']:.2f} × "
                      f"{lib['ancho_y_m']:.2f} m"))
        if self.pases:
            for pase in self.pases:
                hecho = self.pase_hecho(pase)
                ax.plot([pase.desde_lab[0], pase.hasta_lab[0]],
                        [pase.desde_lab[1], pase.hasta_lab[1]], "-",
                        color="#15803d" if hecho else "#9ca3af",
                        linewidth=1.2 if hecho else 0.8, alpha=0.8)
            leyenda.append(Patch(
                facecolor="none", edgecolor="#15803d",
                label=f"pases del peine hechos ({self.pases_hechos()}/"
                      f"{len(self.pases)}; gris = pendientes)"))
        for k in self.congelamientos:
            ax.plot(k.x0, k.y0, "x", color="black", markersize=7)
            if k.x1 is not None and k.y1 is not None:
                ax.plot([k.x0, k.x1], [k.y0, k.y1], "-", color="black",
                        linewidth=1.0)
                ax.plot(k.x1, k.y1, "o", mfc="none", color="black",
                        markersize=6)
        ax.set_xlim(min(self.rejilla.x_min, px0) - 0.1,
                    max(self.rejilla.x_max, px1) + 0.1)
        ax.set_ylim(min(self.rejilla.y_min, py0) - 0.1,
                    max(self.rejilla.y_max, py1) + 0.1)
        ax.set_aspect("equal")
        ax.set_xlabel("x laboratorio (m)")
        ax.set_ylabel("y laboratorio (m)")
        titulo = titulo or "Mapa de congelamientos (marco del laboratorio)"
        if rotulo:
            titulo = f"[{rotulo}]\n{titulo}"
            fig.text(0.45, 0.5, rotulo, fontsize=30, color="#dc2626",
                     alpha=0.35, rotation=25, ha="center", va="center",
                     fontweight="bold")
        ax.set_title(titulo, color="#dc2626" if rotulo else "black")
        ax.legend(handles=leyenda, loc="upper left", bbox_to_anchor=(1.01, 1.0),
                  fontsize=8)
        return fig

    def guardar_png(self, ruta: Path, titulo: str = "",
                    origen: Optional[str] = None) -> bool:
        """
        El mapa como imagen (ver `figura`). Crea el archivo en modo
        exclusivo: nunca pisa uno existente (lanza FileExistsError). Devuelve
        False si no hay matplotlib.
        """
        try:
            fig = self.figura(titulo, origen)
        except ImportError:
            return False
        import matplotlib.pyplot as plt
        try:
            with open(ruta, "xb") as fh:
                fig.savefig(fh, format="png", dpi=120, bbox_inches="tight")
        finally:
            plt.close(fig)
        return True


def resumen_congelamientos(mapa: MapaSeguimiento) -> List[Dict[str, Any]]:
    """
    Cada congelamiento con su entrada y salida (lab), la celda de inicio, y la
    pared de la arena y el borde de la plataforma más cercanos a la entrada.
    """
    filas = []
    for k in mapa.congelamientos:
        d, borde, dimension = borde_mas_cercano(k.x0, k.y0, mapa.plataforma)
        pared, d_pared, tramo = mapa._lado("arena", k.x0, k.y0)
        clase, angulo = clase_de_transicion(
            "entrada", (None if k.dir_entrada is None
                        else direccion_en_entorno(k.dir_entrada)),
            normal_saliente(nombres_lados("arena").index(pared)))
        filas.append({
            "clase_entrada": clase,
            "angulo_entrada_deg": None if angulo is None else round(angulo, 1),
            "marcador": k.marcador, "t_inicio_s": round(k.t_inicio, 3),
            "t_fin_s": None if k.t_fin is None else round(k.t_fin, 3),
            "entrada_lab": [round(k.x0, 4), round(k.y0, 4)],
            "salida_lab": (None if k.x1 is None
                           else [round(k.x1, 4), round(k.y1, 4)]),
            "tramo_m": None if k.tramo_m is None else round(k.tramo_m, 4),
            "celda_inicio": mapa.rejilla.indice(k.x0, k.y0),
            "d_borde_plataforma_m": round(d, 4), "borde_plataforma": borde,
            "dimension_borde": dimension,
            "pared_arena": pared, "d_pared_arena_m": round(d_pared, 4),
            "tramo_pared": tramo,
        })
    return filas
