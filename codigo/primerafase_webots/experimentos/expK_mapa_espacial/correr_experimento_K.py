"""
correr_experimento_K.py
=======================
EXPERIMENTO K — descomposición espacial del error de cobertura.

Toda la evaluación previa del proyecto reporta la cobertura como un escalar
agregado (0.6813 para MADRL, 0.2644 para Voronoi+PSO). Eso dice CUÁNTO cubre
cada estrategia, no DÓNDE falla. Este experimento descompone ese escalar.

La descomposición es EXACTA, no aproximada: la métrica reportada es
    cobertura = 1 - media(grid_aoi)
y la media espacial conmuta con el promedio sobre semillas, de modo que la
media espacial del mapa promedio de AoI reproduce el número oficial a seis
decimales. Esa igualdad es la verificación de control del experimento.

Diseño
------
4 estrategias x 100 semillas = 400 episodios, condición de borde "reflexion"
(la del entrenamiento). Protocolo estándar: 500 pasos, 5 agentes,
deterministic=True, domain_rand=False, pesos del Trial 13, semillas
42*10000 + i.

Mapas acumulados por estrategia (todos 64x64, promediados sobre semillas)
------------------------------------------------------------------------
  M_final    : grid_aoi al terminar el episodio. Corresponde EXACTAMENTE a la
               métrica reportada en toda la tesis.
  M_tiempo   : media de grid_aoi sobre los 500 pasos. Revela regiones
               crónicamente desatendidas que M_final ocultaría si fueron
               visitadas justo al final.
  M_par/M_impar : mitades de 50 semillas (índice par / impar), para comprobar
               si sobrevive estructura atribuible a la ubicación de los
               objetivos.
  M_temprano : media de grid_aoi sobre los primeros PASOS_TEMPRANOS pasos,
               para cuantificar el sesgo de arranque hacia el centro.

Estadística POR SEMILLA (no sobre el mapa promediado)
-----------------------------------------------------
Sobre un mapa ya promediado no hay medida de dispersión. Por eso la cobertura
de cada región se calcula para CADA episodio por separado y se reportan media,
IC95 y comparaciones PAREADAS por semilla: entre regiones dentro de una
estrategia, y entre estrategias dentro de una región.

Geometría declarada
-------------------
  Arena 3.0 x 3.0 m, grilla 64x64  =>  celda = 0.046875 m.
  Centros de celda en (i+0.5)*0.046875; el eje 0 del grid es x, el 1 es y.
  Radio de observación de AoI = 0.15 m ~= 3.2 celdas: cada visita marca un
  disco de ~6 celdas de diámetro, de modo que la grilla NO limita bandas de
  varias celdas, pero sí impide bandas más finas que ~0.05 m.

  Bandas radiales: 4 celdas = 0.1875 m cada una, 8 bandas que cubren
  exactamente las 32 filas hasta el centro. Sin bandas raídas ni cortes a
  mitad de celda.

  Anillo de 0.30 m: se usa la máscara IDÉNTICA a `cobertura_anillo` de
  `tesis_v3_radio/entrenar_v3.py` (dist_pared <= 0.30 sobre centros de celda),
  que selecciona 6 filas por lado. El corte es por tanto INDISTINGUIBLE de
  cualquier umbral en (0.2578125, 0.3046875) m — centro de la última fila
  incluida y centro de la primera excluida —, porque todos producen la misma
  máscara. Se declara para que el cruce con los v3 sea exacto.

Confusión NO separable (declarada, no resuelta)
-----------------------------------------------
Las poses iniciales se sortean en el 80% central: margen = 0.10*arena = 0.30 m,
es decir en [0.30, 2.70]^2. Esa frontera COINCIDE EXACTAMENTE con ANCHO_ANILLO
= 0.30 de los reentrenamientos v3. El déficit perimetral y el sesgo de arranque
comparten frontera, así que el NIVEL ABSOLUTO de la cobertura de anillo no es
interpretable como déficit puro de la estrategia. Las comparaciones ENTRE
estrategias y ENTRE condiciones sí lo son, porque comparten el mismo sorteo
inicial y el sesgo es constante.

Salidas
-------
  resultados/expK_mapas.csv               (mapas aplanados por estrategia)
  resultados/expK_perfil_radial.csv       (perfil por banda)
  resultados/expK_regiones_por_semilla.csv
  resultados/fig_mapa_espacial.png
  resultados/fig_perfil_radial.png
  resultados/tabla_expK.tex
  resultados/resumen_experimento_K.txt

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import math
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

from stable_baselines3 import PPO

from adaptador_piramidal import AdaptadorPiramidal
from correr_experimento_D import (
    ARENA,
    COMM_RADIUS,
    MAX_STEPS_EP,
    N_AGENTES,
    PESOS_TRIAL13,
    RUTA_MODELO,
    SEED_BASE,
    politica_aleatoria,
    politica_heuristica_NN,
    politica_madrl,
)
from lib.swarm_env_skeleton import make_env

# =============================================================================
# CONSTANTES
# =============================================================================

N_EPISODIOS: int = 100
SEMILLAS: List[int] = [SEED_BASE * 10_000 + i for i in range(N_EPISODIOS)]
CONDICION: str = "reflexion"

ESTRATEGIAS: Tuple[str, ...] = ("madrl", "piramidal", "heuristica", "aleatoria")
ETIQUETAS: Dict[str, str] = {
    "madrl":      "MADRL (200k)",
    "piramidal":  "Voronoi + PSO",
    "heuristica": "Heurística NN",
    "aleatoria":  "Aleatoria",
}

# Referencias de la verificación de control, EXACTAS a seis decimales: la
# descomposición espacial es una identidad algebraica, no una estimación, así
# que no se admite tolerancia estadística.
#
# MADRL y heurística NN se contrastan contra RESULTADO_PRIMERO
# (metricas_100eps.json), que reproducen hasta el último dígito.
#
# La política ALEATORIA se contrasta contra 0.139373, que es su valor bajo ESTE
# protocolo — el de los Exp D y E, ambos con ese número en sus CSV, y el que la
# bitácora reporta como 0.1394. NO se contrasta contra el 0.140186 de
# RESULTADO_PRIMERO porque son CANTIDADES DISTINTAS: la aleatoria es la única
# estrategia cuyo resultado depende de un RNG ajeno al entorno, y los Exp D/E
# lo resiembran por episodio con default_rng(seed_ep) mientras RESULTADO_PRIMERO
# usó su propio flujo. La diferencia (0.000813 = 0.07 desviaciones, con
# sigma = 0.0112) es estadísticamente nula, pero es una diferencia de
# PROTOCOLO, no de ruido, y los Exp D/E la dejaban pasar silenciosa con
# TOL = 0.01. Se declara en vez de absorberla en una tolerancia.
OFICIAL: Dict[str, float] = {
    "madrl":      0.681291,
    "heuristica": 0.254349,
    "aleatoria":  0.139373,
}
FUENTE_CONTROL: Dict[str, str] = {
    "madrl":      "RESULTADO_PRIMERO/metricas_100eps.json",
    "heuristica": "RESULTADO_PRIMERO/metricas_100eps.json",
    "aleatoria":  "Exp D y Exp E (protocolo de resiembra por episodio)",
}
# Valor de RESULTADO_PRIMERO para la aleatoria, que este protocolo NO reproduce.
ALEATORIA_RESULTADO_PRIMERO: float = 0.140186

TOL_CONTROL: float = 5e-7

CELDAS_POR_BANDA: int = 4        # 4 celdas = 0.1875 m con la grilla de 64
ANCHO_ANILLO: float = 0.30       # idéntico a tesis_v3_radio/entrenar_v3.py
PASOS_TEMPRANOS: int = 50        # ventana de arranque

REGIONES: Tuple[str, ...] = ("esquinas", "bordes", "interior", "total")
ETIQ_REGION: Dict[str, str] = {
    "esquinas": "Esquinas",
    "bordes":   "Bordes",
    "interior": "Interior",
    "total":    "Total",
}

DIR_SALIDA:    Path = _CARPETA / "resultados"
RUTA_MAPAS:    Path = DIR_SALIDA / "expK_mapas.csv"
RUTA_PERFIL:   Path = DIR_SALIDA / "expK_perfil_radial.csv"
RUTA_REGIONES: Path = DIR_SALIDA / "expK_regiones_por_semilla.csv"
RUTA_FIG_MAPA: Path = DIR_SALIDA / "fig_mapa_espacial.png"
RUTA_FIG_PERF: Path = DIR_SALIDA / "fig_perfil_radial.png"
RUTA_TEX:      Path = DIR_SALIDA / "tabla_expK.tex"
RUTA_RESUMEN:  Path = DIR_SALIDA / "resumen_experimento_K.txt"


# =============================================================================
# GEOMETRÍA DE LA GRILLA
# =============================================================================

class GeometriaGrilla:
    """
    Máscaras espaciales derivadas de los centros de celda del grid de AoI.

    Se construye a partir del `env` real (no de constantes reescritas a mano)
    para que la geometría sea exactamente la que usa la métrica reportada.
    """

    def __init__(self, env) -> None:
        self.xx: np.ndarray = np.asarray(env._field._grid_xx, dtype=np.float64)
        self.yy: np.ndarray = np.asarray(env._field._grid_yy, dtype=np.float64)
        self.R: int = int(self.xx.shape[0])
        self.Wx: float = float(ARENA[0])
        self.Wy: float = float(ARENA[1])
        self.dx: float = self.Wx / self.R
        self.dy: float = self.Wy / self.R

        # Distancia de cada centro de celda a la pared más cercana, por eje.
        self.dist_x: np.ndarray = np.minimum(self.xx, self.Wx - self.xx)
        self.dist_y: np.ndarray = np.minimum(self.yy, self.Wy - self.yy)
        self.dist_pared: np.ndarray = np.minimum(self.dist_x, self.dist_y)

        # ── Regiones: partición exacta de la grilla ───────────────────────
        anillo = self.dist_pared <= ANCHO_ANILLO
        esquinas = (self.dist_x <= ANCHO_ANILLO) & (self.dist_y <= ANCHO_ANILLO)
        self.anillo: np.ndarray = anillo
        self.mascaras: Dict[str, np.ndarray] = {
            "esquinas": esquinas,
            "bordes":   anillo & ~esquinas,
            "interior": ~anillo,
            "total":    np.ones_like(anillo, dtype=bool),
        }

        # ── Bandas radiales de CELDAS_POR_BANDA celdas ────────────────────
        # Índice de fila radial de cada celda: 0 = fila adyacente a la pared.
        idx_radial = np.rint(self.dist_pared / self.dx - 0.5).astype(int)
        self.n_bandas: int = (self.R // 2) // CELDAS_POR_BANDA
        self.banda: np.ndarray = np.clip(
            idx_radial // CELDAS_POR_BANDA, 0, self.n_bandas - 1
        )
        self.bordes_banda: List[Tuple[float, float]] = [
            (k * CELDAS_POR_BANDA * self.dx,
             (k + 1) * CELDAS_POR_BANDA * self.dx)
            for k in range(self.n_bandas)
        ]
        self.centros_banda: np.ndarray = np.array(
            [0.5 * (a + b) for a, b in self.bordes_banda]
        )
        self.mascaras_banda: List[np.ndarray] = [
            self.banda == k for k in range(self.n_bandas)
        ]

        # Corte efectivo del anillo de 0.30 m, por la discretización.
        self.filas_anillo: int = int(np.max(idx_radial[anillo])) + 1
        self.corte_anillo: Tuple[float, float] = (
            (self.filas_anillo - 1) * self.dx + self.dx / 2.0,
            self.filas_anillo * self.dx + self.dx / 2.0,
        )

    def cobertura(self, grid_aoi: np.ndarray, mascara: np.ndarray) -> float:
        """Cobertura = 1 - media del AoI restringida a `mascara`."""
        return 1.0 - float(np.mean(np.asarray(grid_aoi)[mascara]))


# =============================================================================
# ESTADÍSTICA
# =============================================================================

def ic95(x: np.ndarray) -> Tuple[float, float, float, float]:
    """Media, desviación (ddof=1) e IC95 por aproximación normal."""
    n = len(x)
    m = float(np.mean(x))
    s = float(np.std(x, ddof=1))
    ee = s / math.sqrt(n)
    return m, s, m - 1.96 * ee, m + 1.96 * ee


def pareada(a: np.ndarray, b: np.ndarray) -> Dict[str, object]:
    """
    Comparación pareada a - b sobre el MISMO conjunto de semillas.

    Devuelve media, desviación, IC95, t, fracción de semillas con a > b y si
    el IC95 excluye el cero.
    """
    d = np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)
    m, s, lo, hi = ic95(d)
    ee = s / math.sqrt(len(d))
    return {
        "delta": m,
        "std":   s,
        "lo":    lo,
        "hi":    hi,
        "t":     (m / ee) if ee > 0.0 else float("nan"),
        "frac_mayor":   float(np.mean(d > 0)),
        "excluye_cero": bool((lo < 0 and hi < 0) or (lo > 0 and hi > 0)),
    }


# =============================================================================
# EPISODIO
# =============================================================================

def correr_episodio(
    env,
    accionar:  Callable,
    seed_ep:   int,
    geo:       GeometriaGrilla,
    adaptador: AdaptadorPiramidal = None,
) -> Tuple[Dict[str, float], np.ndarray, np.ndarray, np.ndarray]:
    """
    Ejecuta un episodio determinista y devuelve sus métricas y sus mapas.

    El RNG se siembra por episodio (misma convención que los Exp D y E) para
    que la política aleatoria reciba la misma secuencia y el pareo sea válido.

    Devuelve
    --------
    (metricas, aoi_final, aoi_medio_en_el_tiempo, aoi_medio_temprano)
    """
    rng = np.random.default_rng(seed_ep)
    obs, _ = env.reset(seed=seed_ep)
    agentes: List[str] = list(obs.keys())

    # Imprescindible: limpia la inercia PSO del episodio anterior.
    if adaptador is not None:
        adaptador.reset_episodio(agentes)

    acum_tiempo   = np.zeros((geo.R, geo.R), dtype=np.float64)
    acum_temprano = np.zeros((geo.R, geo.R), dtype=np.float64)
    n_pasos = 0
    n_temprano = 0
    done = False

    while not done:
        acciones = accionar(env, obs, rng)
        obs, _, term, trunc, _ = env.step(acciones)
        n_pasos += 1

        grid = np.asarray(env._field._grid_aoi, dtype=np.float64)
        acum_tiempo += grid
        if n_pasos <= PASOS_TEMPRANOS:
            acum_temprano += grid
            n_temprano += 1

        done = all(trunc.values()) or all(term.values())

    aoi_final = np.asarray(env._field._grid_aoi, dtype=np.float64).copy()

    metricas: Dict[str, float] = {
        f"cob_{r}": round(geo.cobertura(aoi_final, geo.mascaras[r]), 6)
        for r in REGIONES
    }
    metricas["cob_anillo_030"] = round(geo.cobertura(aoi_final, geo.anillo), 6)
    for k in range(geo.n_bandas):
        metricas[f"cob_banda_{k}"] = round(
            geo.cobertura(aoi_final, geo.mascaras_banda[k]), 6
        )
    metricas["pasos"] = n_pasos

    return (
        metricas,
        aoi_final,
        acum_tiempo / n_pasos,
        acum_temprano / max(n_temprano, 1),
    )


# =============================================================================
# FIGURAS
# Estilo de fig_resultados_CUATRO.png: 300 dpi, etiquetas en español, sin
# título dentro de la figura, grilla tenue, misma paleta de cuatro colores.
# =============================================================================

def figura_mapas(mapas_cob: Dict[str, np.ndarray], geo: GeometriaGrilla) -> None:
    """
    Los cuatro mapas de cobertura final lado a lado, misma escala cromática.

    El grid está indexado [x, y]; se transpone y se usa origin='lower' para que
    la figura tenga x horizontal e y vertical, como la arena.
    """
    fig, axes = plt.subplots(1, 4, figsize=(16.5, 4.4))
    vmin = 0.0
    vmax = float(max(np.max(m) for m in mapas_cob.values()))

    im = None
    for ax, est in zip(axes, ESTRATEGIAS):
        im = ax.imshow(
            mapas_cob[est].T, origin="lower", cmap="viridis",
            vmin=vmin, vmax=vmax,
            extent=(0.0, geo.Wx, 0.0, geo.Wy), interpolation="nearest",
        )
        ax.set_title(ETIQUETAS[est], fontsize=11)
        ax.set_xlabel("$x$ [m]", fontsize=10)
        ax.set_xticks([0.0, 0.75, 1.5, 2.25, 3.0])
        ax.set_yticks([0.0, 0.75, 1.5, 2.25, 3.0])
        # Frontera del anillo de 0.30 m, que es también la frontera del sorteo
        # de poses iniciales (confusión declarada en el resumen).
        ax.plot(
            [ANCHO_ANILLO, geo.Wx - ANCHO_ANILLO, geo.Wx - ANCHO_ANILLO,
             ANCHO_ANILLO, ANCHO_ANILLO],
            [ANCHO_ANILLO, ANCHO_ANILLO, geo.Wy - ANCHO_ANILLO,
             geo.Wy - ANCHO_ANILLO, ANCHO_ANILLO],
            color="white", ls="--", lw=1.0, alpha=0.85,
        )
    axes[0].set_ylabel("$y$ [m]", fontsize=10)

    fig.subplots_adjust(right=0.90)
    cax = fig.add_axes([0.915, 0.15, 0.013, 0.70])
    cb = fig.colorbar(im, cax=cax)
    cb.set_label(
        f"Cobertura por celda, $1-\\mathrm{{AoI}}$ "
        f"(escala {vmin:.2f}–{vmax:.2f})", fontsize=10
    )
    fig.savefig(RUTA_FIG_MAPA, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Figura → {RUTA_FIG_MAPA}")


def figura_perfil(perfil: Dict[str, np.ndarray], geo: GeometriaGrilla) -> None:
    """Cobertura contra distancia a la pared, las cuatro estrategias."""
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    colores = ["#2c7fb8", "#41ab5d", "#7fcdbb", "#d95f0e"]
    marcas = ["o", "s", "^", "d"]

    for est, c, mk in zip(ESTRATEGIAS, colores, marcas):
        datos = perfil[est]                        # (n_semillas, n_bandas)
        m = np.mean(datos, axis=0)
        ee = np.std(datos, axis=0, ddof=1) / math.sqrt(datos.shape[0])
        ax.plot(geo.centros_banda, m, marker=mk, color=c, lw=1.8, ms=5,
                label=ETIQUETAS[est])
        ax.fill_between(geo.centros_banda, m - 1.96 * ee, m + 1.96 * ee,
                        color=c, alpha=0.20, lw=0)

    ax.axvline(ANCHO_ANILLO, color="gray", ls=":", lw=1.2)
    # La anotación va abajo a la izquierda: arriba pisaría la curva de MADRL,
    # que es la que más cerca de la pared corre.
    ymin, ymax = ax.get_ylim()
    ax.text(ANCHO_ANILLO + 0.03, ymin + 0.03 * (ymax - ymin),
            "0,30 m: anillo v3 y frontera\ndel sorteo de poses iniciales",
            fontsize=8, va="bottom", ha="left", color="gray")
    ax.set_xlabel("Distancia a la pared más cercana [m]", fontsize=11)
    ax.set_ylabel("Cobertura AoI final", fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9, loc="lower right")

    plt.tight_layout()
    fig.savefig(RUTA_FIG_PERF, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Figura → {RUTA_FIG_PERF}")


# =============================================================================
# TABLA LATEX — plantilla UVG: macro \note{}, sin threeparttable
# =============================================================================

def _num(x: float, dec: int) -> str:
    """Formatea con separador decimal COMA, como exige la plantilla."""
    return f"{x:.{dec}f}".replace(".", "{,}")


def tabla_latex(
    reg: Dict[str, Dict[str, np.ndarray]],
    geo: GeometriaGrilla,
) -> List[str]:
    """Cuadro de cobertura por región y estrategia, listo para pegar."""
    n_esq = int(np.sum(geo.mascaras["esquinas"]))
    n_bor = int(np.sum(geo.mascaras["bordes"]))
    n_int = int(np.sum(geo.mascaras["interior"]))

    L: List[str] = []
    L.append(r"% --- Cuadro del Exp K (generado por correr_experimento_K.py) ---")
    L.append(r"% Requiere: \usepackage{booktabs}. \note{} es el macro de la plantilla UVG.")
    L.append(r"\begin{table}[htbp]")
    L.append(r"  \centering")
    L.append(r"  \caption{Descomposición espacial de la cobertura por región de "
             r"la arena. Cien episodios deterministas por estrategia, condición "
             r"de reflexión elástica.}")
    L.append(r"  \label{tab:exp-k-regiones}")
    L.append(r"  \begin{tabular}{lcccc}")
    L.append(r"    \toprule")
    L.append(r"    Estrategia & Esquinas & Bordes & Interior & Total \\")
    L.append(r"    \midrule")
    for e in ESTRATEGIAS:
        celdas = [
            f"{_num(float(np.mean(reg[e][r])), 4)} $\\pm$ "
            f"{_num(float(np.std(reg[e][r], ddof=1)), 4)}"
            for r in REGIONES
        ]
        L.append(f"    {ETIQUETAS[e]} & " + " & ".join(celdas) + r" \\")
    L.append(r"    \bottomrule")
    L.append(r"  \end{tabular}")
    L.append(
        r"  \note{Variable: cobertura AoI final, $1-\overline{\mathrm{AoI}}$, "
        r"restringida a la región. Conjunto: las mismas cien semillas "
        r"deterministas ($42\cdot10^4+i$) para las cuatro estrategias; "
        r"$n=100$ episodios por celda. Se calcula por episodio y luego se "
        r"promedia, de modo que la desviación mide variabilidad entre "
        r"semillas y no dispersión espacial. Regiones definidas sobre los "
        + f"centros de celda de la grilla de AoI (${geo.R}\\times{geo.R}$ "
        + f"celdas, celda de {_num(geo.dx, 6)}\\,m): «esquinas» son las celdas "
        + r"con ambas distancias a pared $\le 0{,}30$\,m "
        + f"({n_esq} celdas), «bordes» el resto del anillo perimetral de "
        + f"$0{{,}}30$\\,m ({n_bor} celdas) e «interior» las restantes "
        + f"{n_int} celdas. El corte efectivo del anillo cae entre "
        + f"{_num(geo.corte_anillo[0], 5)} y {_num(geo.corte_anillo[1], 5)}\\,m "
        + r"por la discretización, y emplea la máscara idéntica a la métrica de "
        + r"anillo de los reentrenamientos v3. La columna «Total» reproduce la "
        + r"cobertura agregada reportada en el resto del documento: la "
        + r"descomposición es exacta, no aproximada. Advertencia: las poses "
        + r"iniciales se sortean en el $80\%$ central de la arena, cuya "
        + r"frontera coincide exactamente con la del anillo de $0{,}30$\,m, "
        + r"por lo que el nivel absoluto de las columnas «Esquinas» y "
        + r"«Bordes» arrastra un sesgo de arranque no separable del déficit "
        + r"propio de la estrategia; las comparaciones entre estrategias sí "
        + r"son válidas, porque todas comparten el mismo sorteo inicial.}"
    )
    L.append(r"\end{table}")
    return L


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    """Corre 4x100 episodios, acumula mapas y emite CSV, figuras, tabla y resumen."""
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("  EXPERIMENTO K — descomposición espacial de la cobertura (4x100)")
    print("=" * 78)

    modelo = PPO.load(str(RUTA_MODELO), device="cpu")
    adaptador = AdaptadorPiramidal(arena_size=ARENA)

    accionadores: Dict[str, Callable] = {
        "madrl":      politica_madrl(modelo),
        "piramidal":  adaptador,
        "heuristica": politica_heuristica_NN,
        "aleatoria":  politica_aleatoria,
    }

    env = make_env(
        n_agents       = N_AGENTES,
        arena_size     = ARENA,
        max_steps      = MAX_STEPS_EP,
        comm_radius    = COMM_RADIUS,
        reward_weights = PESOS_TRIAL13,
        domain_rand    = False,
        seed           = SEED_BASE,
        modo_borde     = CONDICION,
    )
    env.reset(seed=SEMILLAS[0])
    geo = GeometriaGrilla(env)
    radio_obs = float(env._field.radio_obs_aoi)

    print(f"  Grilla {geo.R}x{geo.R}; celda {geo.dx:.6f} m")
    print(f"  Radio de observación de AoI {radio_obs:.3f} m = "
          f"{radio_obs/geo.dx:.2f} celdas")
    print(f"  Bandas radiales: {geo.n_bandas} de {CELDAS_POR_BANDA} celdas "
          f"({CELDAS_POR_BANDA*geo.dx:.4f} m)")
    print(f"  Anillo 0.30 m: {geo.filas_anillo} filas; corte efectivo entre "
          f"{geo.corte_anillo[0]:.5f} y {geo.corte_anillo[1]:.5f} m")
    print(f"  Celdas: esquinas {int(np.sum(geo.mascaras['esquinas']))}, "
          f"bordes {int(np.sum(geo.mascaras['bordes']))}, "
          f"interior {int(np.sum(geo.mascaras['interior']))}, "
          f"total {geo.R*geo.R}\n")

    # ── Acumuladores de mapas ────────────────────────────────────────────
    def cero() -> np.ndarray:
        return np.zeros((geo.R, geo.R), dtype=np.float64)

    aoi_final    = {e: cero() for e in ESTRATEGIAS}
    aoi_tiempo   = {e: cero() for e in ESTRATEGIAS}
    aoi_temprano = {e: cero() for e in ESTRATEGIAS}
    aoi_par      = {e: cero() for e in ESTRATEGIAS}
    aoi_impar    = {e: cero() for e in ESTRATEGIAS}

    filas_reg: List[Dict[str, object]] = []
    reg: Dict[str, Dict[str, np.ndarray]] = {}
    anillo_semilla: Dict[str, np.ndarray] = {}
    perfil: Dict[str, np.ndarray] = {}

    for est in ESTRATEGIAS:
        t0 = time.time()
        acumulado: Dict[str, List[float]] = {r: [] for r in REGIONES}
        anillos: List[float] = []
        bandas: List[List[float]] = []

        for i, semilla in enumerate(SEMILLAS):
            m, mf, mt, mtemp = correr_episodio(
                env, accionadores[est], semilla, geo,
                adaptador if est == "piramidal" else None,
            )
            aoi_final[est]    += mf
            aoi_tiempo[est]   += mt
            aoi_temprano[est] += mtemp
            (aoi_par if i % 2 == 0 else aoi_impar)[est] += mf

            for r in REGIONES:
                acumulado[r].append(float(m[f"cob_{r}"]))
            anillos.append(float(m["cob_anillo_030"]))
            bandas.append([float(m[f"cob_banda_{k}"])
                           for k in range(geo.n_bandas)])
            filas_reg.append({"estrategia": est, "seed_ep": semilla, **m})

        for acumulador in (aoi_final, aoi_tiempo, aoi_temprano):
            acumulador[est] /= N_EPISODIOS
        aoi_par[est]   /= (N_EPISODIOS // 2)
        aoi_impar[est] /= (N_EPISODIOS // 2)

        reg[est] = {r: np.asarray(acumulado[r]) for r in REGIONES}
        anillo_semilla[est] = np.asarray(anillos)
        perfil[est] = np.asarray(bandas)

        print(f"  {est:11s} total={float(np.mean(reg[est]['total'])):.6f}  "
              f"esq={float(np.mean(reg[est]['esquinas'])):.4f}  "
              f"bor={float(np.mean(reg[est]['bordes'])):.4f}  "
              f"int={float(np.mean(reg[est]['interior'])):.4f}  "
              f"({time.time()-t0:.0f}s)")

    # ── VERIFICACIÓN DE CONTROL (exacta a seis decimales) ────────────────
    print("\n  VERIFICACIÓN DE CONTROL — 1 - media espacial del mapa final")
    aborta = False
    ctrl: Dict[str, Tuple[float, float]] = {}
    for est, oficial in OFICIAL.items():
        cob_mapa = 1.0 - float(np.mean(aoi_final[est]))
        delta = abs(round(cob_mapa, 6) - oficial)
        ctrl[est] = (cob_mapa, delta)
        marca = "OK" if delta <= TOL_CONTROL else "DESVIACIÓN"
        print(f"    {est:11s} {cob_mapa:.6f} vs {oficial:.6f}  "
              f"|Δ| = {delta:.6f}  [{marca}]  ({FUENTE_CONTROL[est]})")
        if delta > TOL_CONTROL:
            aborta = True
    print(f"    nota: la aleatoria de RESULTADO_PRIMERO vale "
          f"{ALEATORIA_RESULTADO_PRIMERO:.6f}; este protocolo NO lo reproduce "
          f"(Δ = {abs(ctrl['aleatoria'][0] - ALEATORIA_RESULTADO_PRIMERO):.6f}) "
          f"por resiembra del RNG. Son cantidades distintas.")
    if aborta:
        print("\n  ABORTADO: la descomposición espacial no reproduce el "
              "protocolo. Hay un error de acumulación.")
        sys.exit(1)
    print()

    # ── CSV: mapas aplanados ─────────────────────────────────────────────
    region_de_celda = np.where(
        geo.mascaras["esquinas"], "esquinas",
        np.where(geo.mascaras["bordes"], "bordes", "interior"),
    )
    with open(RUTA_MAPAS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "estrategia", "ix", "iy", "x_m", "y_m", "dist_pared_m",
            "banda", "region",
            "aoi_final", "aoi_tiempo", "aoi_temprano", "aoi_par", "aoi_impar",
        ])
        for est in ESTRATEGIAS:
            for ix in range(geo.R):
                for iy in range(geo.R):
                    w.writerow([
                        est, ix, iy,
                        round(float(geo.xx[ix, iy]), 6),
                        round(float(geo.yy[ix, iy]), 6),
                        round(float(geo.dist_pared[ix, iy]), 6),
                        int(geo.banda[ix, iy]),
                        str(region_de_celda[ix, iy]),
                        round(float(aoi_final[est][ix, iy]), 6),
                        round(float(aoi_tiempo[est][ix, iy]), 6),
                        round(float(aoi_temprano[est][ix, iy]), 6),
                        round(float(aoi_par[est][ix, iy]), 6),
                        round(float(aoi_impar[est][ix, iy]), 6),
                    ])
    print(f"CSV mapas    → {RUTA_MAPAS}")

    # ── CSV: regiones por semilla ────────────────────────────────────────
    with open(RUTA_REGIONES, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas_reg[0].keys()))
        w.writeheader()
        w.writerows(filas_reg)
    print(f"CSV regiones → {RUTA_REGIONES}")

    # ── CSV: perfil radial ───────────────────────────────────────────────
    with open(RUTA_PERFIL, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["estrategia", "banda", "borde_int_m", "borde_ext_m",
                    "centro_m", "n_celdas", "cobertura_media", "std",
                    "ic95_lo", "ic95_hi"])
        for est in ESTRATEGIAS:
            for k in range(geo.n_bandas):
                m, s, lo, hi = ic95(perfil[est][:, k])
                a, b = geo.bordes_banda[k]
                w.writerow([est, k, round(a, 6), round(b, 6),
                            round(float(geo.centros_banda[k]), 6),
                            int(np.sum(geo.mascaras_banda[k])),
                            round(m, 6), round(s, 6),
                            round(lo, 6), round(hi, 6)])
    print(f"CSV perfil   → {RUTA_PERFIL}")

    # ── Figuras ──────────────────────────────────────────────────────────
    figura_mapas({e: 1.0 - aoi_final[e] for e in ESTRATEGIAS}, geo)
    figura_perfil(perfil, geo)

    # ── Tabla LaTeX ──────────────────────────────────────────────────────
    RUTA_TEX.write_text("\n".join(tabla_latex(reg, geo)) + "\n",
                        encoding="utf-8")
    print(f"Tabla LaTeX  → {RUTA_TEX}")

    # ── Resumen ──────────────────────────────────────────────────────────
    L: List[str] = []
    L.append("EXPERIMENTO K — descomposición espacial del error de cobertura")
    L.append("4 estrategias x 100 semillas = 400 episodios, condición 'reflexion'.")
    L.append("5 agentes, 500 pasos, deterministic=True, domain_rand=False,")
    L.append("pesos del Trial 13, semillas 42*10000 + i.")
    L.append("=" * 74)
    L.append("")

    L.append("GEOMETRÍA DECLARADA")
    L.append(f"  Arena {ARENA[0]} x {ARENA[1]} m; grilla de AoI {geo.R}x{geo.R}.")
    L.append(f"  Celda: {geo.dx:.6f} m.")
    L.append(f"  Radio de observación de AoI: {radio_obs:.3f} m = "
             f"{radio_obs/geo.dx:.2f} celdas; cada visita marca un disco de")
    L.append(f"  ~{2*radio_obs/geo.dx:.1f} celdas de diámetro.")
    L.append(f"  Bandas radiales: {geo.n_bandas} bandas de {CELDAS_POR_BANDA} "
             f"celdas = {CELDAS_POR_BANDA*geo.dx:.4f} m, que cubren")
    L.append(f"  exactamente las {geo.R//2} filas hasta el centro. Sin bandas raídas.")
    L.append(f"  El perfil radial NO está limitado por la resolución: la banda")
    L.append(f"  ({CELDAS_POR_BANDA*geo.dx:.4f} m) es {CELDAS_POR_BANDA}x la celda "
             f"y ~{CELDAS_POR_BANDA*geo.dx/(2*radio_obs):.2f}x el diámetro de marcado.")
    L.append(f"  Anillo de 0.30 m: máscara IDÉNTICA a cobertura_anillo() de")
    L.append(f"  tesis_v3_radio/entrenar_v3.py => {geo.filas_anillo} filas por lado;")
    L.append(f"  corte efectivo entre {geo.corte_anillo[0]:.5f} y "
             f"{geo.corte_anillo[1]:.5f} m.")
    L.append(f"  Celdas por región: esquinas {int(np.sum(geo.mascaras['esquinas']))}, "
             f"bordes {int(np.sum(geo.mascaras['bordes']))},")
    L.append(f"  interior {int(np.sum(geo.mascaras['interior']))}, "
             f"total {geo.R*geo.R}. Las tres primeras son una partición exacta.")
    L.append("")

    L.append("VERIFICACIÓN DE CONTROL — la descomposición es exacta")
    L.append("  Variable: 1 - media espacial del mapa de AoI FINAL promediado")
    L.append("  sobre las 100 semillas. Debe igualar la cobertura oficial a")
    L.append("  seis decimales (es una identidad algebraica, no una estimación).")
    for est, oficial in OFICIAL.items():
        c, d = ctrl[est]
        L.append(f"  {ETIQUETAS[est]:14s} {c:.6f} vs {oficial:.6f}  "
                 f"|Δ| = {d:.6f}")
        L.append(f"      referencia: {FUENTE_CONTROL[est]}")
    L.append("  (Voronoi+PSO no tiene valor oficial previo; su referencia es el")
    L.append("   Exp E, que lo incorporó al protocolo.)")
    L.append("")
    L.append("  HALLAZGO COLATERAL — dos números que no son la misma cantidad.")
    L.append(f"  RESULTADO_PRIMERO reporta {ALEATORIA_RESULTADO_PRIMERO:.6f} para la")
    L.append("  política aleatoria; este protocolo da 0.139373, igual que los CSV")
    L.append("  de los Exp D y E. MADRL y heurística NN, en cambio, coinciden con")
    L.append("  RESULTADO_PRIMERO hasta el último dígito. La aleatoria es la ÚNICA")
    L.append("  estrategia cuyo resultado depende de un RNG ajeno al entorno: los")
    L.append("  Exp D/E lo resiembran por episodio con default_rng(seed_ep) para")
    L.append("  que el pareo entre condiciones sea válido, y RESULTADO_PRIMERO usó")
    L.append("  su propio flujo. La diferencia (0.000813 = 0.07 desviaciones, con")
    L.append("  sigma = 0.0112) es estadísticamente nula, pero es una diferencia de")
    L.append("  PROTOCOLO, no de ruido. Los Exp D y E la dejaban pasar silenciosa")
    L.append("  por llevar TOL = 0.01; la tolerancia exacta de este experimento la")
    L.append("  expuso. No invalida ningún resultado previo — la aleatoria nunca")
    L.append("  sostuvo una conclusión por su valor absoluto —, pero al citar la")
    L.append("  línea base aleatoria hay que decir bajo qué protocolo se midió.")
    L.append("")

    L.append("TABLA 1 — COBERTURA POR REGIÓN (estadística POR SEMILLA)")
    L.append("  Variable: cobertura AoI final = 1 - media(grid_aoi) restringida")
    L.append("  a la región, calculada por episodio. Conjunto: las mismas 100")
    L.append("  semillas para las cuatro estrategias. n = 100 episodios.")
    L.append("  La desviación mide variabilidad ENTRE SEMILLAS, no dispersión")
    L.append("  espacial dentro del mapa.")
    for e in ESTRATEGIAS:
        L.append(f"  {ETIQUETAS[e]}:")
        for r in REGIONES:
            m, s, lo, hi = ic95(reg[e][r])
            L.append(f"      {ETIQ_REGION[r]:10s} {m:.4f} ± {s:.4f}  "
                     f"IC95 [{lo:.4f}, {hi:.4f}]")
        m, s, lo, hi = ic95(anillo_semilla[e])
        L.append(f"      {'Anillo030':10s} {m:.4f} ± {s:.4f}  "
                 f"IC95 [{lo:.4f}, {hi:.4f}]   (= esquinas + bordes)")
    L.append("")

    L.append("TABLA 2 — COMPARACIÓN PAREADA ENTRE REGIONES")
    L.append("  Dentro de cada estrategia, pareo por semilla, n = 100.")
    L.append("  Δ = cobertura(A) - cobertura(B) en la MISMA semilla.")
    pares_reg = [("esquinas", "interior"), ("bordes", "interior"),
                 ("esquinas", "bordes")]
    for e in ESTRATEGIAS:
        L.append(f"  {ETIQUETAS[e]}:")
        for a, b in pares_reg:
            p = pareada(reg[e][a], reg[e][b])
            L.append(f"      {ETIQ_REGION[a]:9s}-{ETIQ_REGION[b]:9s} "
                     f"Δ = {p['delta']:+.4f} ± {p['std']:.4f}  "
                     f"IC95 [{p['lo']:+.4f}, {p['hi']:+.4f}]  "
                     f"t = {p['t']:+8.2f}  "
                     f"¿excluye 0? {'SÍ' if p['excluye_cero'] else 'NO'}  "
                     f"A>B en {int(round(p['frac_mayor']*100)):3d}/100")
    L.append("")

    L.append("TABLA 3 — COMPARACIÓN PAREADA ENTRE ESTRATEGIAS")
    L.append("  Dentro de cada región, pareo por semilla, n = 100.")
    L.append("  Δ = cobertura(MADRL) - cobertura(línea base) en la MISMA semilla.")
    for r in REGIONES:
        L.append(f"  Región {ETIQ_REGION[r]}:")
        for base in ("piramidal", "heuristica", "aleatoria"):
            p = pareada(reg["madrl"][r], reg[base][r])
            L.append(f"      vs {ETIQUETAS[base]:14s} "
                     f"Δ = {p['delta']:+.4f} ± {p['std']:.4f}  "
                     f"IC95 [{p['lo']:+.4f}, {p['hi']:+.4f}]  "
                     f"t = {p['t']:+8.2f}  "
                     f"¿excluye 0? {'SÍ' if p['excluye_cero'] else 'NO'}  "
                     f"mejor en {int(round(p['frac_mayor']*100)):3d}/100")
    L.append("")

    L.append("TABLA 4 — PERFIL RADIAL (cobertura vs distancia a la pared)")
    L.append(f"  Bandas de {CELDAS_POR_BANDA} celdas = "
             f"{CELDAS_POR_BANDA*geo.dx:.4f} m. Media sobre 100 semillas.")
    L.append("  " + f"{'banda [m]':<16s}{'celdas':>8s}" +
             "".join(f"{ETIQUETAS[e]:>17s}" for e in ESTRATEGIAS))
    for k in range(geo.n_bandas):
        a, b = geo.bordes_banda[k]
        fila = f"  {a:5.3f}-{b:5.3f}".ljust(18)
        fila += f"{int(np.sum(geo.mascaras_banda[k])):>8d}"
        for e in ESTRATEGIAS:
            fila += f"{float(np.mean(perfil[e][:, k])):>17.4f}"
        L.append(fila)
    L.append("")
    L.append("  Banda de 0.30 m (máscara idéntica a la métrica de anillo de los")
    L.append("  v3), para cruce directo con los reentrenamientos:")
    for e in ESTRATEGIAS:
        m, s, lo, hi = ic95(anillo_semilla[e])
        L.append(f"      {ETIQUETAS[e]:14s} {m:.4f} ± {s:.4f}  "
                 f"IC95 [{lo:.4f}, {hi:.4f}]")
    L.append("")

    L.append("MAPA PROMEDIADO EN EL TIEMPO vs MAPA FINAL")
    L.append("  El mapa temporal (media sobre los 500 pasos) revela regiones")
    L.append("  crónicamente desatendidas que el final ocultaría si fueron")
    L.append("  visitadas justo al terminar. Cobertura por región:")
    L.append(f"  {'estrategia':14s} {'región':10s} {'temporal':>10s} {'final':>10s}"
             f" {'Δ':>9s}")
    for e in ESTRATEGIAS:
        for r in ("esquinas", "bordes", "interior", "total"):
            ct = 1.0 - float(np.mean(aoi_tiempo[e][geo.mascaras[r]]))
            cf = 1.0 - float(np.mean(aoi_final[e][geo.mascaras[r]]))
            L.append(f"  {ETIQUETAS[e]:14s} {ETIQ_REGION[r]:10s} "
                     f"{ct:10.4f} {cf:10.4f} {cf-ct:+9.4f}")
    L.append("")

    L.append("CAVEAT 1 — ¿bastan 100 semillas para lavar la estructura debida")
    L.append("           a la ubicación de los objetivos? (split-half par/impar)")
    L.append("  Se comparan los mapas de AoI final promediados sobre las 50")
    L.append("  semillas de índice PAR contra las 50 de índice IMPAR. Si el")
    L.append("  promedio conservara estructura debida a los objetivos, las dos")
    L.append("  mitades diferirían más allá del ruido.")
    L.append("  Referencia de escala: desviación espacial del propio mapa.")
    L.append("  Descomposición señal/ruido POR CELDA: las dos mitades son")
    L.append("  independientes y de igual tamaño, así que la desviación del")
    L.append("  ruido del mapa de 100 semillas es RMS(Δ)/2, y la desviación de")
    L.append("  la estructura verdadera es sqrt(var_total - var_ruido).")
    for e in ESTRATEGIAS:
        d = aoi_par[e] - aoi_impar[e]
        r_pearson = float(np.corrcoef(aoi_par[e].ravel(),
                                      aoi_impar[e].ravel())[0, 1])
        rms = float(np.sqrt(np.mean(d ** 2)))
        sd_total = float(np.std(aoi_final[e]))
        sd_ruido = rms / 2.0
        sd_senal = math.sqrt(max(0.0, sd_total ** 2 - sd_ruido ** 2))
        L.append(f"  {ETIQUETAS[e]:14s} r = {r_pearson:.4f}  "
                 f"max|Δ| = {float(np.max(np.abs(d))):.4f}  "
                 f"RMS Δ = {rms:.4f}  desv. espacial = {sd_total:.4f}")
        L.append(f"      {'':14s} ruido/celda = {sd_ruido:.4f}  "
                 f"señal/celda = {sd_senal:.4f}  "
                 f"razón señal/ruido = {sd_senal/sd_ruido:.2f}")
    L.append("")
    L.append("  LECTURA. La estructura espacial supera al ruido en las cuatro")
    L.append("  estrategias, pero por márgenes muy distintos, y en el caso de la")
    L.append("  heurística NN el margen es estrecho. CONSECUENCIA OPERATIVA: los")
    L.append("  mapas NO deben leerse celda a celda — a esa escala el ruido de")
    L.append("  muestreo es comparable a la estructura. Sí son válidas las")
    L.append("  lecturas AGREGADAS (regiones y bandas radiales), que promedian")
    L.append("  entre 64 y 2704 celdas y cuya incertidumbre está reportada como")
    L.append("  IC95 entre semillas en las Tablas 1 a 4. Todas las afirmaciones")
    L.append("  de este experimento son agregadas por construcción.")
    L.append("  Las 100 semillas, por tanto, bastan para el nivel de región y de")
    L.append("  banda, que es el nivel al que se concluye; NO bastan para")
    L.append("  afirmar nada sobre una celda individual.")
    L.append("")

    L.append("CAVEAT 2 — sesgo de las poses iniciales: CONFUSIÓN NO SEPARABLE")
    L.append("  Las poses iniciales se sortean uniformemente en el 80% central:")
    L.append("  margen = 0.10*arena = 0.30 m, es decir en [0.30, 2.70]^2. Esa")
    L.append("  frontera COINCIDE EXACTAMENTE con ANCHO_ANILLO = 0.30 de")
    L.append("  tesis_v3_radio. El anillo perimetral es, literalmente, la región")
    L.append("  donde ningún agente nace jamás.")
    L.append(f"  Cuantificación: cobertura por región en la ventana temprana")
    L.append(f"  (primeros {PASOS_TEMPRANOS} pasos, AoI promediado) contra el mapa final.")
    L.append(f"  {'estrategia':14s} {'región':10s} {'temprano':>10s} {'final':>10s}")
    for e in ESTRATEGIAS:
        for r in ("esquinas", "bordes", "interior"):
            ct = 1.0 - float(np.mean(aoi_temprano[e][geo.mascaras[r]]))
            cf = 1.0 - float(np.mean(aoi_final[e][geo.mascaras[r]]))
            L.append(f"  {ETIQUETAS[e]:14s} {ETIQ_REGION[r]:10s} "
                     f"{ct:10.4f} {cf:10.4f}")
    L.append("")
    L.append("  Interpretación admisible: el sorteo inicial NO puede separarse")
    L.append("  del déficit perimetral, porque comparten frontera exacta. El")
    L.append("  NIVEL ABSOLUTO de la cobertura de anillo no es interpretable")
    L.append("  como déficit puro de la estrategia. Las comparaciones ENTRE")
    L.append("  estrategias y ENTRE condiciones sí lo son, porque todas")
    L.append("  comparten el mismo sorteo inicial y el sesgo es constante.")
    L.append("")
    L.append("  IMPLICACIÓN PARA EL DOCUMENTO: el cuadro de la variante de")
    L.append("  alineación geométrica reporta cobertura de anillo 0.4565 contra")
    L.append("  0.5114 global. Ese valor absoluto arrastra el mismo sesgo. La")
    L.append("  comparación ENTRE los tres pesos de lambda_pared sigue siendo")
    L.append("  válida, porque el sesgo es constante en las tres; lo que NO es")
    L.append("  interpretable de forma absoluta es el NIVEL.")
    L.append("")

    L.append("CAVEAT 3 — resolución de la grilla")
    L.append("  Declarada en GEOMETRÍA. El perfil radial usa bandas de")
    L.append(f"  {CELDAS_POR_BANDA*geo.dx:.4f} m, {CELDAS_POR_BANDA} veces la "
             f"celda de {geo.dx:.6f} m, así que el perfil")
    L.append("  no está limitado por la discretización. Lo que sí está limitado")
    L.append("  es la resolución MÍNIMA alcanzable: bandas más finas que una")
    L.append("  celda no son representables, y bandas menores que el diámetro")
    L.append(f"  de marcado ({2*radio_obs:.3f} m) mezclan celdas que una sola")
    L.append("  visita marca de forma conjunta.")

    resumen = "\n".join(L)
    RUTA_RESUMEN.write_text(resumen, encoding="utf-8")
    print(f"Resumen      → {RUTA_RESUMEN}\n")
    print(resumen)


if __name__ == "__main__":
    main()
