"""
demo_final.py
=============
Sesión DEMOSTRATIVA final en el Robotat: DEMOSTRACIÓN, NO CITABLE. No es
una campaña de medición; sus salidas van a `resultados_demo_final/` y no
entran en el documento.

Dos modos:
  · `objetivos`: la configuración de la evaluación física del 30-09 (cinco
    robots, `modelo_sanidad`, CBF + escape de tres términos, factor 0.40,
    500 decisiones a 10 Hz, colocación autónoma);
  · `mejorada`: lo mismo con el robot del obstáculo móvil (modo L2, F2,
    τ_c 0.65 s), sin campaña (paso 4 del plan).

Este archivo sólo ORQUESTA: política, filtro, escape, colocación,
retroceso, detectores y abortos son los objetos del código congelado,
importados y usados tal cual (precedente: `correr_exploratorio_Q.py`). Lo
que hubo que copiar de `sesion_robotat.sesion_evaluacion` —que construye el
coordinador adentro y no acepta uno inyectado— está marcado con
`# ── COPIA LITERAL de sesion_robotat.py <líneas> ──` y su fin; los únicos
cambios dentro de una copia llevan `# [demo]`. `comparar_ast_demo_final.py`
lo verifica.

La publicación hacia la interfaz gráfica (`publicador_estado.py`) se hace
UNA vez por decisión, en la subclase del coordinador, DESPUÉS de
`super()._decidir_y_actuar()` (los cinco robots ya recibieron su orden), y
nunca lanza.

    python demo_final.py --modo objetivos --episodios 3
    python demo_final.py --modo objetivos --simulador --episodios 2

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import argparse
import atexit
import base64
import math
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

_CARPETA = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import config_robotat as cfg
import sesion_robotat as ses
from coordinador_enjambre import SEMILLAS_LOTE, CoordinadorEnjambre
from demo_obstaculo_movil import CoordinadorConObstaculo
from publicador_estado import PUERTO_PANEL, PublicadorEstado
# Los nombres que usan las copias literales, con el mismo nombre que en
# `sesion_robotat` (importados, NO redefinidos).
from sesion_robotat import (REINTENTOS_COLOCACION, RPM_CAP_LAB,
                            DetectorCongelamiento, DetectorSeguimiento,
                            ResultadoEtapa, _contadores_fuente,
                            _correr_episodio, _delta_contadores_fuente,
                            _enlaces_caidos_al_arrancar,
                            _esperar_reposicionamiento,
                            _marcadores_congelados_al_arrancar,
                            sortear_poses_arranque, stream_congelado)

#: Carpeta de salida de la demostración (nunca la de la campaña).
DIR_SALIDA_DEMO_FINAL: Path = _CARPETA / "resultados_demo_final"
#: Primera línea del README de la carpeta de salida.
LEYENDA: str = "demostración, no citable"
#: Banda de margen que dibuja el panel (la del CBF de paredes, m).
MARGEN_PARED_M: float = 0.18
#: La rejilla de AoI viaja cada tantas decisiones.
CADA_REJILLA: int = 5
#: El ciclo p95 y la latencia p95 se recalculan cada tantas decisiones.
CADA_PERCENTIL: int = 10
#: Simulador local (`--simulador`): puertos y retardos de los ensayos.
PUERTO_SIMULADOR: int = 27600
TAU_AGENTES_S: float = 0.45
TAU_OBSTACULO_S: float = 0.85
#: Arranque de los agentes en el simulador (marco env), como en
#: `ensayo_sesion_simulador.py`.
ARRANQUE_SIMULADOR_ENV = ((0.5, 0.5, 0.3), (2.5, 0.5, 2.0), (0.5, 2.5, -1.0),
                          (2.5, 2.5, -2.5), (1.5, 2.6, 0.0))


# ════════════════════════════════════════════════════════════════════════════
# PUBLICACIÓN: lo que la subclase del coordinador manda por decisión
# ════════════════════════════════════════════════════════════════════════════

def _r(x: Any, n: int = 4) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, n) if math.isfinite(v) else None


class EstadoDemo:
    """
    Acumulados del episodio y armado de los mensajes. Todo método público
    es a prueba de excepciones: un error se le cuenta al publicador y la
    decisión sigue.
    """

    def __init__(self, coord: Any, publicador: Optional[PublicadorEstado],
                 modo: str, estado: Dict[str, Any], canal: Any, fuente: Any,
                 entorno: Any, n_agentes: int, decisiones: int,
                 episodios: int, etiqueta: str = "") -> None:
        self.coord = coord
        self.pub = publicador
        self.modo = modo
        self.estado = estado
        self.canal = canal
        self.fuente = fuente
        self.entorno = entorno
        self.n = int(n_agentes)
        self.decisiones = int(decisiones)
        self.episodios = int(episodios)
        self.etiqueta = etiqueta
        self.filas: Dict[int, Any] = {}
        self._reiniciar_acumulados()

    def _reiniciar_acumulados(self) -> None:
        self.agente_decisiones = 0
        self.n_cbf = 0
        self.n_escapes = 0
        self.n_retrocesos = 0
        self._en_escape: Dict[int, int] = {}
        self._en_retroceso: Dict[int, int] = {}
        self.pares_015: set = set()
        self.pares_022: set = set()
        self.d_pared_min = float("inf")
        self.ciclos_ms: List[float] = []
        self.cobertura: List[float] = []
        self._p95: Optional[Tuple[Optional[float], Optional[float]]] = None

    # ── ganchos de la subclase ───────────────────────────────────────────
    def guardar_fila(self, d: Dict[str, Any], fila: Dict[str, Any]) -> None:
        """Desde el observador: sólo guarda referencias (no publica)."""
        self.filas[int(d["agente"])] = (d, fila)

    def publicar(self, mensaje: Dict[str, Any]) -> None:
        if self.pub is not None:
            self.pub.publicar(mensaje)

    def inicio_episodio(self, semilla: int) -> None:
        try:
            self._reiniciar_acumulados()
            self.filas.clear()
            if self.pub is None:
                return
            campo = self.coord.env._field
            agentes = [{"indice": i,
                        "robot": cfg.MAPEO_AGENTES[i].id_robot,
                        "marcador": cfg.MAPEO_AGENTES[i].id_marcador}
                       for i in range(self.n)]
            self.publicar({
                "tipo": "inicio_episodio", "modo": self.modo,
                "episodio": self.estado.get("episodio"),
                "episodios": self.episodios, "semilla": int(semilla),
                "agentes": agentes,
                "arena": {"wx": cfg.ARENA_WX_M, "wy": cfg.ARENA_WY_M,
                          "margen": MARGEN_PARED_M},
                "obstaculo": self.parametros_obstaculo(),
                "objetivos": self._objetivos(campo),
                "decisiones": self.decisiones, "etiqueta": self.etiqueta,
            })
        except Exception as exc:                            # noqa: BLE001
            self._error(exc)

    def tras_decision(self, dt_s: float) -> None:
        """Después de `super()._decidir_y_actuar()`: UNA publicación."""
        if self.pub is None or not self.pub.activo:
            self.filas.clear()
            return
        try:
            self.publicar(self._mensaje_paso(dt_s))
        except Exception as exc:                            # noqa: BLE001
            self._error(exc)
        finally:
            self.filas.clear()

    def fin_episodio(self, res: Dict[str, Any],
                     extra: Optional[Dict[str, Any]] = None) -> None:
        try:
            self.publicar({"tipo": "fin_episodio", "modo": self.modo,
                           "episodio": self.estado.get("episodio"),
                           "resultado": {k: v for k, v in res.items()
                                         if isinstance(v, (int, float, str,
                                                           bool, type(None)))},
                           **(extra or {})})
        except Exception as exc:                            # noqa: BLE001
            self._error(exc)

    def estado_sesion(self, **campos: Any) -> None:
        try:
            self.publicar({"tipo": "estado_sesion", "modo": self.modo,
                           **campos})
        except Exception as exc:                            # noqa: BLE001
            self._error(exc)

    # ── el modo `mejorada` las sobreescribe ──────────────────────────────
    def parametros_obstaculo(self) -> Optional[Dict[str, Any]]:
        return None

    def estado_obstaculo(self, poses: Dict[int, Tuple[float, float]]
                         ) -> Optional[Dict[str, Any]]:
        return None

    # ── internos ─────────────────────────────────────────────────────────
    def _error(self, exc: BaseException) -> None:
        try:
            if self.pub is not None:
                self.pub.registrar_error(exc)
        except Exception:                                   # noqa: BLE001
            pass

    @staticmethod
    def _objetivos(campo: Any) -> List[Dict[str, Any]]:
        pos = campo.posiciones_objetivos
        sig = campo.sigmas_objetivos
        return [{"x": _r(p[0]), "y": _r(p[1]), "sigma": _r(s)}
                for p, s in zip(pos, sig)]

    def _mensaje_paso(self, dt_s: float) -> Dict[str, Any]:
        # Medido el 23-10 (banco de la prueba 5): armar el mensaje costaba
        # 0.45 ms de 0.87. Por eso: escalares de Python (`tolist`) y no
        # `np.asarray` por campo, las distancias entre pares con `hypot`
        # y los percentiles cada `CADA_PERCENTIL` decisiones (el panel no
        # necesita un p95 nuevo cada 100 ms).
        coord = self.coord
        self.ciclos_ms.append(dt_s * 1000.0)
        paso = int(coord._paso_episodio) - 1
        wx, wy = cfg.ARENA_WX_M, cfg.ARENA_WY_M
        agentes: List[Dict[str, Any]] = []
        poses: Dict[int, Tuple[float, float]] = {}
        eventos: List[str] = []
        for ag in sorted(self.filas):
            d, fila = self.filas[ag]
            x, y, th = d["pose_env"].tolist()[:3]
            v_nom, w_nom = d["accion_nominal"].tolist()[:2]
            v_esc, w_esc = d["accion_tras_escape"].tolist()[:2]
            v, w = d["accion_ejecutada"].tolist()[:2]
            esc = int(d["en_escape"])
            cbf = int(d["cbf_intervino"])
            ret = int(fila.get("en_retroceso", 0) or 0)
            rob = cfg.MAPEO_AGENTES[ag].id_robot
            self.agente_decisiones += 1
            self.n_cbf += cbf
            if esc and not self._en_escape.get(ag, 0):
                self.n_escapes += 1
                eventos.append(f"agente {ag} (robot {rob}): escape")
            if ret and not self._en_retroceso.get(ag, 0):
                self.n_retrocesos += 1
                eventos.append(f"agente {ag} (robot {rob}): retroceso por "
                               f"pose repetida")
            self._en_escape[ag] = esc
            self._en_retroceso[ag] = ret
            poses[ag] = (x, y)
            dp = min(x, wx - x, y, wy - y)
            if dp < self.d_pared_min:
                self.d_pared_min = dp
            agentes.append({
                "i": ag, "robot": rob,
                "x": round(x, 4), "y": round(y, 4), "th": round(th, 4),
                "v_nom": round(v_nom, 4), "w_nom": round(w_nom, 4),
                "v_esc": round(v_esc, 4), "w_esc": round(w_esc, 4),
                "v": round(v, 4), "w": round(w, 4),
                "cbf": cbf, "escape": esc, "retroceso": ret,
                "rpm_pico": _r(fila.get("rpm_pico"), 1),
                "d_obst": _r(fila.get("d_obst_medida")),
                "h_obst": _r(fila.get("h_obst_geom")),
            })
        ids = sorted(poses)
        for k_, a_ in enumerate(ids):
            xa, ya = poses[a_]
            for b_ in ids[k_ + 1:]:
                dist = math.hypot(xa - poses[b_][0], ya - poses[b_][1])
                if dist < 0.22:
                    self.pares_022.add((a_, b_))
                    if dist < 0.15:
                        self.pares_015.add((a_, b_))
        campo = coord.env._field
        # Rejilla COMPLETA: la misma fórmula que `_correr_episodio` escribe
        # en `cobertura_aoi` al final del episodio (decisión de José).
        cob = 1.0 - float(np.mean(campo._grid_aoi))
        self.cobertura.append(cob)
        if paso % CADA_PERCENTIL == 0 or self._p95 is None:
            lat = getattr(self.fuente, "_latencias", None) or []
            self._p95 = (
                _r(np.percentile(self.ciclos_ms, 95), 2),
                _r(1000.0 * np.percentile(lat[-500:], 95), 2) if lat else None)
        msg: Dict[str, Any] = {
            "tipo": "paso", "modo": self.modo,
            "episodio": self.estado.get("episodio"), "paso": paso,
            "decisiones": self.decisiones,
            "agentes": agentes,
            "objetivos": self._objetivos(campo),
            "cobertura": round(cob, 5),
            "obstaculo": self.estado_obstaculo(poses),
            "acumulados": {
                "frac_cbf": round(self.n_cbf / max(self.agente_decisiones, 1), 4),
                "escapes": self.n_escapes,
                "retrocesos": self.n_retrocesos,
                "pares_015": len(self.pares_015),
                "pares_022": len(self.pares_022),
                "d_pared_min": _r(self.d_pared_min),
                "ciclo_p95_ms": self._p95[0],
                "lat_poses_p95_ms": self._p95[1],
                "ticks_atrasados": getattr(self.entorno, "ticks_atrasados",
                                           None),
            },
            "eventos": eventos,
        }
        if paso % CADA_REJILLA == 0:
            g = np.asarray(campo._grid_aoi, dtype=float)
            u8 = np.clip(np.rint(g * 255.0), 0, 255).astype(np.uint8)
            msg["rejilla"] = {"forma": list(u8.shape),
                              "b64": base64.b64encode(u8.tobytes()).decode()}
        return msg


class _MezclaDemo:
    """
    Lo que agregan las subclases del coordinador: medir la decisión con
    `perf_counter` y publicar DESPUÉS de `super()`. Sin `_demo` (o con el
    publicador apagado) son exactamente el coordinador de base.
    """

    _demo: Optional[EstadoDemo] = None

    def _decidir_y_actuar(self) -> bool:
        t0 = time.perf_counter()
        fin = super()._decidir_y_actuar()
        dt = time.perf_counter() - t0
        estado_demo = self._demo
        if estado_demo is not None:
            estado_demo.tras_decision(dt)
        return fin

    def _reiniciar_episodio(self, semilla: int) -> bool:
        ok = super()._reiniciar_episodio(semilla)
        estado_demo = self._demo
        if ok and estado_demo is not None:
            estado_demo.inicio_episodio(semilla)
        return ok


class CoordinadorDemo(_MezclaDemo, CoordinadorEnjambre):
    """`CoordinadorEnjambre` + publicación (modo `objetivos`)."""


# ════════════════════════════════════════════════════════════════════════════
# UTILIDADES DE LA SESIÓN
# ════════════════════════════════════════════════════════════════════════════

def preguntar_con_latido(ctx: Any, fuente: Any, canal: Any,
                         mensaje: str) -> str:
    """La espera del operador de `sesion_robotat._esperar_reposicionamiento`
    (con latido: los sockets no se mueren) pero devolviendo la respuesta."""
    captura: Dict[str, str] = {}
    original = ctx.preguntar

    def preguntar(m: str) -> str:
        captura["r"] = original(m)
        return captura["r"]
    ctx.preguntar = preguntar
    try:
        ses._esperar_reposicionamiento(ctx, fuente, canal, mensaje, None)
    finally:
        ctx.preguntar = original
    return (captura.get("r") or "").strip().lower()


def hora_fin_de(texto: Optional[str]) -> Optional[datetime]:
    if not texto:
        return None
    hh, mm = (int(x) for x in texto.split(":"))
    return datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)


def preparar_salida(carpeta: Path) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    readme = carpeta / "README.md"
    if not readme.exists():
        readme.write_bytes((
            f"{LEYENDA}\n\n"
            "Salidas de `demo_final.py` (sesión demostrativa final en el "
            "Robotat y sus ensayos en el simulador). Sirven para el video, el "
            "póster y la defensa en vivo; NO son datos citables en el "
            "documento.\n").encode("utf-8"))
    return carpeta


def levantar_simulador(id_robot_obstaculo: Optional[int], puerto: int) -> Any:
    """
    `SimuladorRobotat` (con zona muerta) en este proceso, como
    `ensayo_sesion_simulador.py`: los cinco agentes y, si se pasa, el robot
    del obstáculo; retardo de actuación por robot (0.45 s agentes, 0.85 s
    obstáculo). Se llama con la calibración IDENTIDAD ya impuesta: el marco
    lab del simulador es el env corrido 1.5 m.
    """
    from simulador_para_colocacion import (SimuladorZonaMuerta,
                                           fallas_con_retardo_por_robot)
    robots = [cfg.MAPEO_AGENTES[i].id_robot for i in range(5)]
    mapeo = {r: cfg.MAPEO_AGENTES[i].id_marcador for i, r in enumerate(robots)}
    tx, ty = cfg.TRASLACION_X_M, cfg.TRASLACION_Y_M
    inicial = {r: (x - tx, y - ty, th)
               for r, (x, y, th) in zip(robots, ARRANQUE_SIMULADOR_ENV)}
    retardos: Dict[int, float] = {}
    if id_robot_obstaculo is not None:
        import demo_obstaculo_movil as demo
        rid_o = int(id_robot_obstaculo)
        mapeo[rid_o] = cfg.marcador_fijo_de_robot(rid_o)
        p0, r0 = demo.punto_del_circulo(-math.pi / 2)
        inicial[rid_o] = (float(p0[0]) - tx, float(p0[1]) - ty, float(r0))
        retardos[rid_o] = TAU_OBSTACULO_S
    fallas = fallas_con_retardo_por_robot(retardos, TAU_AGENTES_S)
    sim = SimuladorZonaMuerta(mapeo, inicial, fallas, puerto_poses=puerto,
                              puerto_base=puerto + 100)
    sim.iniciar()
    return sim


def escribir_salidas(carpeta: Path, ts: str, modo: str,
                     tablas: Dict[str, Sequence[Dict[str, Any]]]
                     ) -> List[Path]:
    rutas = []
    for nombre, filas in tablas.items():
        ruta = carpeta / f"{ts}_demo-{modo}_{nombre}.csv"
        ses.escribir_csv(ruta, filas)
        if filas:
            rutas.append(ruta)
    return rutas


# ════════════════════════════════════════════════════════════════════════════
# MODO `objetivos`
# ════════════════════════════════════════════════════════════════════════════

def sesion_objetivos(ctx: Any, args: Any, publicador: Optional[PublicadorEstado],
                     salida: Path) -> Dict[str, Any]:
    """
    El mínimo de `sesion_robotat.sesion_evaluacion` (1917-2264) con el
    coordinador de la estado_demo. Por episodio, el orden de aquélla: semilla,
    sorteo de poses y rumbos, colocación, `revisar_poses_iniciales`,
    `leer_poses_estables`, `reiniciar_reloj`, `_reiniciar_episodio`,
    `_correr_episodio`, `detener_todo`.
    """
    from adaptadores_robotat import revisar_poses_iniciales
    from lanzar_robotat import construir, leer_poses_estables

    n_agentes = 5
    factor = args.factor
    decisiones = args.decisiones
    rpm_aborto = args.rpm_aborto
    colocacion = "manual" if args.colocacion == "manual" else (
        "auto" if args.colocacion == "auto" else "actual")
    # Las copias toman la semilla de `SEMILLAS_LOTE[intento - 1]`: con
    # `--semillas`, ese nombre local es la lista pedida.
    SEMILLAS_LOTE = list(args.semillas)                     # noqa: N806
    hora_fin = hora_fin_de(args.hora_fin)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    print()
    print("=" * 72)
    print(f"DEMOSTRACIÓN FINAL — modo 'objetivos' ({LEYENDA})")
    print("=" * 72)
    print(f"  {args.episodios} episodios × {decisiones} decisiones · factor "
          f"{factor:.2f} · colocación {colocacion} · semillas "
          f"{SEMILLAS_LOTE[:args.episodios]}")
    for i in range(n_agentes):
        a = cfg.MAPEO_AGENTES[i]
        print(f"  agente {i}: robot {a.id_robot} / marcador {a.id_marcador}")

    # ── COPIA LITERAL de sesion_robotat.py 1991-2000 ──
    ctx.conectar()
    for i in range(n_agentes):
        marc = cfg.MAPEO_AGENTES[i].id_marcador
        congelado, _d, utiles = stream_congelado(ctx.poses, marc)
        if not utiles or congelado:
            return ResultadoEtapa(
                7, "FALLO",
                f"no se arranca: marcador {marc} "
                f"{'congelado' if utiles else 'sin respuesta'}")
    ctx.cerrar()
    # ── fin de la copia 1991-2000 ──

    fuente, canal, entorno = construir(n_agentes)
    atexit.register(canal.detener_todo)
    coord = CoordinadorDemo(fuente=fuente, canal=canal, entorno=entorno,
                            n_agentes=n_agentes, timestep_ms=10)
    canal.factor_operativo = factor
    detector = DetectorCongelamiento()
    seguimiento = DetectorSeguimiento()

    registro: List[Dict[str, Any]] = []
    estado: Dict[str, Any] = {"episodio": 0}
    estado_demo = EstadoDemo(coord, publicador, "objetivos", estado, canal, fuente,
                      entorno, n_agentes, decisiones, args.episodios,
                      args.etiqueta)
    coord._demo = estado_demo

    # ── COPIA LITERAL de sesion_robotat.py 2013-2034 ──
    def observador(d: Dict[str, Any]) -> None:
        ag = int(d["agente"])
        registro.append({
            "episodio":     estado["episodio"],
            "agente":       ag,
            "robot":        cfg.MAPEO_AGENTES[ag].id_robot,
            "paso":         d["paso"],
            "pose_env_x":   float(d["pose_env"][0]),
            "pose_env_y":   float(d["pose_env"][1]),
            "pose_env_th":  float(d["pose_env"][2]),
            "v_ejecutada":  float(d["accion_ejecutada"][0]),
            "w_ejecutada":  float(d["accion_ejecutada"][1]),
            "en_escape":    int(d["en_escape"]),
            "cbf_intervino": int(d["cbf_intervino"]),
            "rpm_pico":     canal.ultimo_pico_rpm,
            "con_vecino":   int(any(
                abs(float(v)) > 1e-9
                for v in np.asarray(d["observacion"])[8:16])),
            # 1 si en esta decisión el canal le mandó el RETROCESO por pose
            # repetida (2026-09-24): la acción de arriba NO se ejecutó.
            "en_retroceso": int(ag in getattr(canal, "mandos_directos", {})),
        })
    # ── fin de la copia 2013-2034 ──

    def observador_demo(d: Dict[str, Any]) -> None:
        """El de la etapa 7 y, además, la fila para la publicación."""
        observador(d)
        estado_demo.guardar_fila(d, registro[-1])

    coord._observador_paso = observador_demo
    episodios: List[Dict[str, Any]] = []
    rechazos_colocacion = 0
    diag = None
    terminado = "completa"
    rutas: List[Path] = []

    try:
        for intento in range(1, args.episodios + 1):
            if hora_fin is not None and datetime.now() >= hora_fin:
                terminado = f"hora de fin {args.hora_fin}"
                print(f"\n  ⏰ son las {datetime.now():%H:%M}: se cierra la "
                      f"sesión ({terminado}).")
                break
            if intento > 1:
                estado_demo.estado_sesion(evento="esperando Enter",
                                   detalle="siguiente episodio o terminar",
                                   hora_fin=args.hora_fin)
                r = preguntar_con_latido(
                    ctx, fuente, canal,
                    f"  Episodio {intento - 1} terminado. Enter = siguiente "
                    f"episodio ({intento}/{args.episodios}); 't' = terminar.")
                if r.startswith("t"):
                    terminado = "terminada por el operador"
                    break
            print()
            print("-" * 72)
            print(f"EPISODIO {intento}/{args.episodios}  ({LEYENDA})")
            print("-" * 72)
            estado_demo.estado_sesion(evento=f"colocación ({colocacion})",
                               episodio=intento, hora_fin=args.hora_fin)
            # ── COPIA LITERAL de sesion_robotat.py 2062-2235 ──
            semilla = (SEMILLAS_LOTE[intento - 1]
                       if intento <= len(SEMILLAS_LOTE)
                       else SEMILLAS_LOTE[0] + intento - 1)
            blancos = sortear_poses_arranque(
                n_agentes, np.random.default_rng(semilla))
            from colocacion_autonoma import sortear_rumbos
            rumbos = sortear_rumbos(n_agentes, semilla)
            # El blanco de CADA intento queda en el CSV, válido o no: así
            # `diversidad_arranques` puede ver si las exclusiones sesgaron
            # los arranques. El rumbo sólo se pide en la colocación automática.
            info_col: Dict[str, Any] = {"colocacion": colocacion}
            for i in range(n_agentes):
                info_col[f"blanco_x_a{i}"] = round(float(blancos[i][0]), 4)
                info_col[f"blanco_y_a{i}"] = round(float(blancos[i][1]), 4)
                info_col[f"blanco_th_a{i}"] = (round(rumbos[i], 4)
                                               if colocacion == "auto" else "")

            abandonos_col: Dict[int, str] = {}

            def colocar_solos() -> None:
                """Colocación automática; deja su informe en `info_col`."""
                from colocacion_autonoma import colocar_enjambre
                if diag is not None:
                    diag.fijar_contexto(fase="colocacion")
                inf = colocar_enjambre(fuente, canal, blancos, rumbos,
                                       n_agentes)
                if diag is not None:
                    diag.fijar_contexto(fase="entre_episodios")
                    diag.registrar_evento(
                        "fin_colocacion", motivo=inf.motivo_fin,
                        t_colocacion_s=inf.t_s,
                        abandonados={str(k): v
                                     for k, v in inf.abandonados.items()})
                info_col.update(inf.como_fila(n_agentes))
                abandonos_col.clear()
                abandonos_col.update(inf.abandonados)

            def problemas_de_arranque(poses) -> List[str]:
                """Chequeo geométrico + poses VIVAS (ver funciones)."""
                problemas_ = revisar_poses_iniciales(poses, n_agentes)
                # Un marcador que se congeló durante la colocación deja una
                # posición no confiable: que lo vea el operador (revisión
                # adversarial 2026-09-22).
                problemas_ += [
                    f"agente {i} (robot {cfg.MAPEO_AGENTES[i].id_robot}): "
                    f"marcador congelado durante la colocación — movelo o "
                    f"giralo a mano hasta que la guía muestre su pose "
                    f"cambiando (Motive lo perdió)"
                    for i, m in sorted(abandonos_col.items())
                    if m == "marcador congelado"]
                problemas_ += _marcadores_congelados_al_arrancar(
                    fuente, n_agentes)
                problemas_ += _enlaces_caidos_al_arrancar(canal)
                return problemas_

            # ⚠ HALLAZGO (2026-09-11): un rechazo del chequeo de arranque
            # gastaba el intento. En la sesión del 11 de septiembre 7 de 19
            # intentos se fueron así, casi siempre por quedar 1–6 cm por
            # debajo del margen de 0.20 m, y la sesión se quedó sin intentos
            # con 5 válidos. Un rechazo no dice nada del sistema —el
            # episodio ni arrancó—, así que ahora se vuelve a pedir la misma
            # colocación. Con tope, para que un problema persistente no
            # cuelgue la sesión.
            if colocacion == "auto":
                # Un Enter por episodio: los robots se van a mover solos y el
                # operador tiene que haber despejado la arena. Con latido.
                _esperar_reposicionamiento(
                    ctx, fuente, canal,
                    "  Los robots van a ir SOLOS a estos blancos. Despejá la "
                    "arena y dale Enter (Ctrl+C corta).", blancos)
                colocar_solos()
            elif intento > 1 and colocacion != "actual":  # [demo] "actual": sin reposicionar
                # Con latido: sin él, los sockets se caen durante la pausa.
                _esperar_reposicionamiento(
                    ctx, fuente, canal,
                    "  Reposicioná los robots y dale Enter.", blancos)

            poses_ini = leer_poses_estables(fuente, n_agentes)
            problemas = problemas_de_arranque(poses_ini)
            reintento = 0
            while problemas and reintento < REINTENTOS_COLOCACION:
                reintento += 1
                rechazos_colocacion += 1
                if diag is not None:
                    diag.registrar_evento("rechazo_arranque",
                                          problemas=list(problemas),
                                          reintento=reintento)
                print("  ✘ no se arranca todavía:")
                for p in problemas:
                    print(f"      · {p}")
                print(f"  (no se gasta el intento: corregí y dale Enter — "
                      f"{reintento}/{REINTENTOS_COLOCACION})")
                _esperar_reposicionamiento(
                    ctx, fuente, canal,
                    ("  Corregí lo que impide moverse (marcador tapado, robot "
                     "apagado o trabado) y dale Enter: después se vuelven a "
                     "colocar solos." if colocacion == "auto"
                     else "  Corregí la colocación y dale Enter."), blancos)
                if colocacion == "auto":
                    colocar_solos()
                poses_ini = leer_poses_estables(fuente, n_agentes)
                problemas = problemas_de_arranque(poses_ini)
            if problemas:
                print("  ✘ no se arranca este episodio:")
                for p in problemas:
                    print(f"      · {p}")
                episodios.append({"episodio": intento, "valido": 0,
                                  "motivo": "; ".join(problemas), **info_col})
                if diag is not None:
                    diag.registrar_evento("intento_sin_arrancar",
                                          problemas=list(problemas))
                continue

            estado["episodio"] = intento
            marca = len(registro)
            detector.reiniciar()
            seguimiento.reiniciar()
            # Re-anclar el horario de ticks: sin esto, el tiempo que el
            # operador tardó en reposicionar deja el lazo permanentemente
            # atrasado y deja de dormir — el episodio corre a velocidad de
            # CPU. Ver `EntornoEjecucionRobotat.reiniciar_reloj`.
            if hasattr(entorno, "reiniciar_reloj"):
                entorno.reiniciar_reloj()
            if diag is not None:
                diag.fijar_contexto(fase="episodio")
            # Contadores de la fuente al empezar: el episodio se lleva la
            # diferencia (decisión del autor, 2026-09-24).
            contadores_antes = _contadores_fuente(fuente)
            if not coord._reiniciar_episodio(semilla):
                episodios.append({"episodio": intento, "valido": 0,
                                  "motivo": "no se pudo iniciar el episodio"})
                continue

            res = _correr_episodio(coord, canal, fuente, registro, marca,
                                   decisiones, rpm_aborto, n_agentes,
                                   detector, semilla, seguimiento, diag=diag)
            res.update(_delta_contadores_fuente(contadores_antes, fuente))
            res["episodio"] = intento
            if diag is not None:
                diag.registrar_evento(
                    "fin_episodio", valido=res["valido"], motivo=res["motivo"],
                    decisiones=res["decisiones"], duracion_s=res["duracion_s"])
            # Régimen con que corrió: la réplica pareada lo lee de acá en vez
            # de suponer los valores por defecto (revisión del 2026-09-22).
            res["factor"] = factor
            res["rpm_aborto"] = rpm_aborto
            res.update(info_col)
            for i in range(n_agentes):
                # Composición y offset de rumbo con que se midió este episodio:
                # el enjambre cambió de robots (3 → 8, 2026-09-22) y el 8 usa
                # un offset medido en una sola corrida. Sin esto, un CSV no
                # dice con qué robots ni sobre qué rumbo se obtuvo.
                rid = cfg.MAPEO_AGENTES[i].id_robot
                res[f"robot_a{i}"] = rid
                res[f"offset_deg_a{i}"] = round(
                    math.degrees(cfg.offset_rumbo_de_robot(rid)), 4)
                res[f"offset_origen_a{i}"] = cfg.origen_offset_rumbo(rid)
                if i in poses_ini:
                    res[f"x0_a{i}"] = float(poses_ini[i][0])
                    res[f"y0_a{i}"] = float(poses_ini[i][1])
                    res[f"th0_a{i}"] = float(poses_ini[i][2])
            episodios.append(res)
            print(f"  >>> EPISODIO {intento}: "
                  f"{'VÁLIDO' if res['valido'] else 'INVÁLIDO'}"
                  f"  {res.get('motivo', '')}")
            if res.get("retrocesos_detalle"):
                print(f"      ↩ retrocesos por pose repetida: "
                      f"{res['retrocesos_detalle']}  "
                      f"({res['decisiones_retroceso']} decisiones-agente, "
                      f"{100 * res['frac_decisiones_retroceso']:.1f} %)")
            if res["valido"]:
                print(f"      cobertura AoI {res['cobertura_aoi']:.4f}  ·  "
                      f"colisiones <0.15 {res['colisiones_015']}  ·  "
                      f"d_pared mín {res['d_pared_min']:.6f}")
            # ── fin de la copia 2062-2235 ──
            if res["valido"]:
                # La réplica pareada de la evaluación no se corre: es una
                # demostración. La columna queda para conservar las de la
                # etapa 7.
                res["cobertura_replica"] = ""
            estado_demo.fin_episodio(res)
    finally:
        canal.detener_todo()
        rutas = escribir_salidas(salida, ts, "objetivos",
                                 {"decisiones": registro,
                                  "episodios": episodios})
        print(f"[estado_demo] rechazos del chequeo de colocación que NO gastaron "
              f"episodio: {rechazos_colocacion}")
        estado_demo.estado_sesion(evento="sesión terminada", detalle=terminado)
        if publicador is not None:
            print(publicador.resumen())
    return {"episodios": episodios, "rutas": rutas, "terminado": terminado,
            "registro": registro, "pila": (fuente, canal, coord)}


def cerrar_pila_simulador(pila: Any) -> None:
    """Sólo con `--simulador`, ANTES de apagarlo: frena, cierra los enlaces
    y saca los `atexit` de frenado, que si no corren contra un simulador ya
    apagado y gritan "CORTAR ALIMENTACIÓN A MANO". En hardware no se llama:
    los `atexit` quedan como red de seguridad."""
    fuente, canal, coord = pila
    canal.detener_todo()
    for f in (canal.detener_todo, getattr(coord, "_detener_seguro", None)):
        if f is not None:
            atexit.unregister(f)
    for paso in (canal.cerrar, fuente.cerrar):
        try:
            paso()
        except Exception:                                   # noqa: BLE001
            pass


# ════════════════════════════════════════════════════════════════════════════
# MODO `mejorada`
# ════════════════════════════════════════════════════════════════════════════

class EstadoDemoObstaculo(EstadoDemo):
    """`EstadoDemo` + el robot del obstáculo y su supervisor."""

    def parametros_obstaculo(self) -> Optional[Dict[str, Any]]:
        import demo_obstaculo_movil as demo
        return {"centro": list(demo.CENTRO_CIRCULO_ENV),
                "R": demo.RADIO_CIRCULO_M, "v": demo.V_CRUCERO_M_S,
                "D_o": demo.D_OBSTACULO_M,
                "radio": demo.R_EFECTIVO_OBSTACULO_M,
                "robot": getattr(self.canal, "id_robot_obstaculo", None)}

    def estado_obstaculo(self, poses: Dict[int, Tuple[float, float]]
                         ) -> Optional[Dict[str, Any]]:
        sup = getattr(self.coord, "supervisor", None)
        traza = (sup.traza[-1] if sup is not None and getattr(sup, "traza", None)
                 else {})
        pose_o = self.fuente.pose_obstaculo()
        if pose_o is None and not traza:
            return None
        x = traza.get("x") if traza.get("x", "") != "" else (
            None if pose_o is None else float(pose_o[0]))
        y = traza.get("y") if traza.get("y", "") != "" else (
            None if pose_o is None else float(pose_o[1]))
        th = traza.get("th") if traza.get("th", "") != "" else (
            None if pose_o is None else float(pose_o[2]))
        d_min = None
        if x is not None and poses:
            d_min = min(math.hypot(p[0] - x, p[1] - y)
                        for p in poses.values())
        return {"x": _r(x), "y": _r(y), "th": _r(th),
                "v_cmd": _r(traza.get("v_cmd")), "w_cmd": _r(traza.get("w_cmd")),
                "estado": traza.get("estado", getattr(sup, "estado", None)),
                "en_freno": traza.get("en_freno"),
                "error_radial": _r(traza.get("error_radial")),
                "d_min": _r(d_min)}


class CoordinadorDemoObstaculo(_MezclaDemo, CoordinadorConObstaculo):
    """`CoordinadorConObstaculo` + publicación (modo `mejorada`)."""


class _Terminar(Exception):
    """El operador (o la hora de fin) cierra la sesión entre tomas."""


def sesion_mejorada(ctx: Any, args: Any, publicador: Optional[PublicadorEstado],
                    salida: Path, vista: Dict[str, Any]) -> Dict[str, Any]:
    """
    El mínimo de `demo_obstaculo_movil.sesion_demo` (2545-2933) en modo L2,
    SIN campaña (`campana = None`: sin libro, sin semillas reservadas, sin
    inclusión ni cierre), con el coordinador de la demo. El bucle de tomas
    —colocación con obstáculo, `correr_toma` con todos los abortos, reglas de
    parada y la pregunta al operador— es COPIA LITERAL; lo que agrega la demo
    (publicar, Enter entre tomas, hora de fin) entra por envoltorios LOCALES
    de `_colocar_toma_automatica`, `correr_toma` y `aplicar_regla_de_parada`,
    que llaman a las del módulo congelado.
    """
    import demo_obstaculo_movil as demo
    from adaptadores_robotat import revisar_poses_iniciales  # noqa: F401
    from lanzar_robotat import leer_poses_estables  # noqa: F401
    from demo_obstaculo_movil import (  # noqa: F401 (los usa la copia)
        TOL_COLOCACION_OBSTACULO_M, arranque_obstaculo, columnas_registro_toma,
        escribir_csv, fila_toma_cortada, problemas_obstaculo_al_arrancar,
        regla_de_parada, sortear_blancos_demo)

    modo = "L2"
    n = len(cfg.MAPEO_AGENTES)
    id_robot_obstaculo = int(args.robot_obstaculo)
    id_marcador_obstaculo = cfg.marcador_fijo_de_robot(id_robot_obstaculo)
    factor = args.factor
    decisiones = args.decisiones
    rpm_aborto = args.rpm_aborto
    tau_prediccion_s = demo.TAU_PREDICCION_S
    formulacion = "F2"
    automatica = args.colocacion == "auto"
    campana = None
    intento_inicial = 1
    intentos_max = args.episodios
    tomas = args.episodios
    SEMILLAS_LOTE = list(args.semillas)                     # noqa: N806
    hora_fin = hora_fin_de(args.hora_fin)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    id_sesion = f"demo-mejorada_{ts}"
    rutas = {d: salida / f"{ts}_demo-mejorada_{d}.csv"
             for d in ("decisiones", "obstaculo", "tomas")}

    print()
    print("=" * 72)
    print(f"DEMOSTRACIÓN FINAL — modo 'mejorada' ({LEYENDA})")
    print("=" * 72)
    print(f"  {n} agentes + robot {id_robot_obstaculo} (marcador "
          f"{id_marcador_obstaculo}) en el círculo de R "
          f"{demo.RADIO_CIRCULO_M:.2f} m alrededor de "
          f"{demo.CENTRO_CIRCULO_ENV} a {demo.V_CRUCERO_M_S} m/s")
    print(f"  barrera {formulacion} (τ_c = {tau_prediccion_s:.2f} s), D_o = "
          f"{demo.D_OBSTACULO_M:.2f} m; factor {factor:.2f}; freno de respaldo "
          f"ACTIVO; {args.episodios} tomas × {decisiones} decisiones; "
          f"colocación {args.colocacion}")
    print("  ⚠ Una persona junto a la arena, lista para levantar al obstáculo.")
    print(f"  Reglas de parada automáticas: contacto (< "
          f"{demo.UMBRAL_CONTACTO_M:.2f} m), freno en "
          f"{demo.TOMAS_CON_FRENO_SEGUIDAS} tomas seguidas, aborto por el "
          f"obstáculo.")

    # ── COPIA LITERAL de demo_obstaculo_movil.py 2653-2663 ──
    crudo = ses.ClientePosesCrudo()
    try:
        for marc in [cfg.MAPEO_AGENTES[i].id_marcador for i in range(n)] + [
                id_marcador_obstaculo]:
            congelado, _d, utiles = ses.stream_congelado(crudo, marc)
            if not utiles or congelado:
                return {"veredicto": "FALLO",
                        "detalle": f"marcador {marc} "
                                   f"{'congelado' if utiles else 'sin respuesta'}"}
    finally:
        crudo.cerrar()
    # ── fin de la copia 2653-2663 ──

    fuente, canal, entorno = demo.construir_con_obstaculo(
        n, conectar_obstaculo=True, id_robot_obstaculo=id_robot_obstaculo,
        id_marcador_obstaculo=id_marcador_obstaculo, timestep_ms=10)
    atexit.register(canal.detener_todo)
    supervisor = demo.SupervisorObstaculo(fuente, canal, modo="movil",
                                          freno_activo=True)
    coord = CoordinadorDemoObstaculo(fuente, canal, entorno, n, 10,
                                     supervisor=supervisor,
                                     formulacion=formulacion,
                                     tau_prediccion_s=tau_prediccion_s)
    canal.factor_operativo = factor
    registro: List[Dict[str, Any]] = []
    trazas: List[Dict[str, Any]] = []
    estado: Dict[str, Any] = {"episodio": 0}
    estado_demo = EstadoDemoObstaculo(
        coord, publicador, "mejorada", estado, canal, fuente, entorno, n,
        decisiones, args.episodios, args.etiqueta)
    coord._demo = estado_demo
    observador = demo.crear_observador(coord, canal, registro, estado)

    def observador_demo(d: Dict[str, Any]) -> None:
        """El de `sesion_demo` y, además, la fila para la publicación."""
        observador(d)
        estado_demo.guardar_fila(d, registro[-1])

    coord._observador_paso = observador_demo
    tomas_res: List[Dict[str, Any]] = []
    corridas: List[Dict[str, Any]] = []
    detenida: Optional[str] = None
    cuenta = {"tomas": 0}
    terminado = "completa"

    # ── envoltorios locales: llaman a las funciones congeladas ──────────
    def _colocar_publicando(ctx_, fuente_, canal_, n_, modo_, semilla_,
                            id_robot_obstaculo_, id_marcador_obstaculo_):
        if cuenta["tomas"] > 0:
            if hora_fin is not None and datetime.now() >= hora_fin:
                print(f"\n  ⏰ son las {datetime.now():%H:%M}: se cierra la "
                      f"sesión.")
                raise _Terminar(f"hora de fin {args.hora_fin}")
            estado_demo.estado_sesion(evento="esperando Enter",
                                      detalle="siguiente toma o terminar",
                                      hora_fin=args.hora_fin)
            r_ = preguntar_con_latido(
                ctx_, fuente_, canal_,
                f"  Toma terminada. Enter = siguiente toma; 't' = terminar.")
            if r_.startswith("t"):
                raise _Terminar("terminada por el operador")
        estado_demo.estado_sesion(evento="colocación alrededor del obstáculo",
                                  episodio=cuenta["tomas"] + 1,
                                  hora_fin=args.hora_fin)
        return demo._colocar_toma_automatica(
            ctx_, fuente_, canal_, n_, modo_, semilla_, id_robot_obstaculo_,
            id_marcador_obstaculo_)

    def _correr_toma_publicando(*a, **kw):
        cuenta["tomas"] += 1
        res_ = demo.correr_toma(*a, **kw)
        sup_ = {k: v for k, v in supervisor.resumen().items()
                if isinstance(v, (int, float, str))}
        estado_demo.fin_episodio(res_, {
            "valido_demo": int(res_.get("valido_demo", 0) or 0),
            "motivo_demo": res_.get("motivo_demo", ""),
            "supervisor": sup_})
        return res_

    def _aplicar_regla_publicando(ctx_, fuente_, canal_, regla_, fila_):
        estado_demo.estado_sesion(evento="PAUSA DE SEGURIDAD", detalle=regla_)
        seguir_ = demo.aplicar_regla_de_parada(ctx_, fuente_, canal_, regla_,
                                               fila_)
        estado_demo.estado_sesion(
            evento="pausa de seguridad respondida",
            detalle="sigue" if seguir_ else "se detiene la sesión")
        return seguir_

    # Los nombres que usa la copia, apuntando a los envoltorios.
    _colocar_toma_automatica = _colocar_publicando
    correr_toma = _correr_toma_publicando                   # noqa: F841
    aplicar_regla_de_parada = _aplicar_regla_publicando     # noqa: F841

    # Lo que `main` necesita aunque la sesión termine por `_Terminar` (que
    # sale de la copia DESPUÉS de su `finally`: frena y escribe los CSV).
    vista.update({"tomas": tomas_res, "rutas": list(rutas.values()),
                  "terminado": terminado, "registro": registro,
                  "trazas": trazas, "pila": (fuente, canal, coord),
                  "estado_demo": estado_demo})

    # ── COPIA LITERAL de demo_obstaculo_movil.py 2692-2909 ──
    def escribir_todo() -> None:
        for f in (*registro, *trazas, *tomas_res):
            f.setdefault("id_sesion", id_sesion)
        escribir_csv(rutas["decisiones"], registro)
        escribir_csv(rutas["obstaculo"], trazas)
        escribir_csv(rutas["tomas"], tomas_res)

    def cerrar_intento(fila: Dict[str, Any], semilla_: int) -> None:
        """Identifica la fila y, en campaña, la incluye o no y la anota."""
        fila.setdefault("id_sesion", id_sesion)
        fila.setdefault("semilla", semilla_)
        if campana is None:
            return
        incl, motivo_i = campana_inclusion(fila)
        fila.update({"campana": campana.nombre, "intento_campana": fila["toma"],
                     "incluida": incl, "motivo_inclusion": motivo_i})
        # El crudo de la toma va a disco ANTES de anotarla en el libro: el
        # libro nunca tiene un resultado sin su fila (auditoría final, 10-10).
        escribir_todo()
        previo_cierre = campana.cierre_por_seguridad
        campana.registrar(fila["toma"], semilla_, fila, rutas["tomas"].name)
        if campana.cierre_por_seguridad and not previo_cierre:
            # Criterio de seguridad de José (09-10): el libro cerró la
            # CAMPAÑA al anotar la segunda toma corrida con contacto.
            print("\n" + "⛔" * 3 + f" CAMPAÑA CERRADA — {campana.cierre_por_seguridad}")
            print("  Lo decidió el criterio fijado en el plan; no se corre ningún "
                  "intento más. Revisar los robots; lo ocurrido va a la "
                  "bitácora y al reporte.")

    def parar_y_cerrar(fila: Dict[str, Any], regla_: str,
                       semilla_: int) -> bool:
        """Anota el intento ANTES de la pausa de seguridad (el criterio de
        cierre lo cuenta aunque el proceso muera esperando la respuesta) y
        después pausa; la respuesta, también un Ctrl+C, va al libro en una
        fila aparte (revisiones del 08 y 10-10)."""
        cerrar_intento(fila, semilla_)
        try:
            seguir = aplicar_regla_de_parada(ctx, fuente, canal, regla_, fila)
        except BaseException:
            fila["parada_respuesta"] = "interrumpida (Ctrl+C) en la pausa"
            if campana is not None:
                campana.anotar_respuesta_pausa(fila["toma"], fila["parada_respuesta"])
            escribir_todo()
            raise
        if campana is not None:
            campana.anotar_respuesta_pausa(fila["toma"],
                                           fila.get("parada_respuesta", ""))
        escribir_todo()
        return seguir

    if campana is not None:
        from campana_obstaculo import inclusion_campana as campana_inclusion
        plan_intentos = campana.plan_de_intentos()
    else:
        plan_intentos = (
            (k, (SEMILLAS_LOTE[k - 1] if k <= len(SEMILLAS_LOTE)
                 else SEMILLAS_LOTE[0] + k - 1))
            for k in range(intento_inicial, intentos_max + 1))
    try:
        for intento, semilla in plan_intentos:
            if (campana is None
                    and sum(t.get("valido_demo", 0) for t in tomas_res) >= tomas):
                break
            if automatica:
                print(f"\n--- TOMA {intento} ---")
                col = _colocar_toma_automatica(
                    ctx, fuente, canal, n, modo, semilla, id_robot_obstaculo,
                    id_marcador_obstaculo)
                objetivo, rumbo = col["objetivo"], col["rumbo"]
                if col["parada"]:
                    fila = {"toma": intento, "semilla": semilla,
                            "id_sesion": id_sesion, "valido": 0,
                            "valido_demo": 0,
                            "motivo": f"colocación: {col['parada']}",
                            "regla_parada": col["parada"], **col["info"]}
                    tomas_res.append(fila)
                    seguir_ = parar_y_cerrar(fila, col["parada"], semilla)
                    if not seguir_:
                        detenida = col["parada"]
                        break
                    continue
                if col["problemas"]:
                    print("  ✘ no se arranca esta toma:")
                    for p_ in col["problemas"]:
                        print(f"      · {p_}")
                    tomas_res.append({"toma": intento, "valido": 0,
                                      "valido_demo": 0,
                                      "motivo": "; ".join(col["problemas"]),
                                      **col["info"]})
                    cerrar_intento(tomas_res[-1], semilla)
                    continue
                info_col = col["info"]
                poses_reg, pose_o_reg = col["poses_ini"], col["pose_o"]
            else:
                info_col = {"colocacion": "manual"}
                objetivo, rumbo = arranque_obstaculo(semilla, modo)
                blancos = sortear_blancos_demo(n, semilla, objetivo)
                print(f"\n--- TOMA {intento} ---")
                print(f"  OBSTÁCULO (robot {id_robot_obstaculo}): "
                      f"({objetivo[0]:.2f}, {objetivo[1]:.2f})"
                      + (f", rumbo {math.degrees(rumbo):+.0f}° (antihorario)"
                         if rumbo is not None else "")
                      + f" ±{TOL_COLOCACION_OBSTACULO_M * 100:.0f} cm")
                problemas = ["(sin colocar)"]
                for reintento in range(ses.REINTENTOS_COLOCACION + 1):
                    ses._esperar_reposicionamiento(
                        ctx, fuente, canal,
                        "  Colocá los agentes en sus blancos y el obstáculo en su "
                        "punto, y dale Enter.", blancos)
                    poses_ini = leer_poses_estables(fuente, n)
                    enlace_obst = ([] if canal.reintentar_enlace_obstaculo() else
                                   [f"enlace de ruedas del obstáculo (robot "
                                    f"{id_robot_obstaculo}) caído: ¿apagado o "
                                    f"sin batería?"])
                    problemas = (enlace_obst
                                 + revisar_poses_iniciales(poses_ini, n)
                                 + ses._marcadores_congelados_al_arrancar(fuente, n)
                                 + ses._enlaces_caidos_al_arrancar(canal)
                                 + problemas_obstaculo_al_arrancar(
                                     fuente, poses_ini, objetivo, rumbo))
                    if not problemas:
                        break
                    print("  ✘ no se arranca todavía:")
                    for p in problemas:
                        print(f"      · {p}")
                if problemas:
                    tomas_res.append({"toma": intento, "valido": 0,
                                      "valido_demo": 0,
                                      "motivo": "; ".join(problemas)})
                    cerrar_intento(tomas_res[-1], semilla)
                    continue
                poses_reg, pose_o_reg = poses_ini, fuente.pose_obstaculo()
            estado["episodio"] = intento
            decisiones_previas = canal.decisiones_enviadas
            enlace_antes = (canal.obstaculo_envios_fallidos,
                            canal.obstaculo_reconexiones)
            marca_toma = len(registro)
            try:
                res = correr_toma(coord, canal, fuente, entorno, semilla,
                                  decisiones, registro, rpm_aborto)
            except BaseException as exc:
                # Toma CORTADA A MITAD (Ctrl+C, caída): se frena, se arma su
                # fila con lo que alcanzó a correr y se ANOTA antes de
                # relanzar, para que el criterio de seguridad la cuente como
                # corrida (revisión del 10-10).
                canal.detener_todo(silencioso=True)
                res = fila_toma_cortada(coord, registro, marca_toma, semilla, exc)
                res.update({"toma": intento, "modo": modo, "factor": factor,
                            "obst_x0": float(objetivo[0]),
                            "obst_y0": float(objetivo[1]), **info_col})
                res.update(columnas_registro_toma(
                    poses_reg, pose_o_reg, id_robot_obstaculo,
                    id_marcador_obstaculo, decisiones_previas, rpm_aborto,
                    tau_prediccion_s, n))
                for f in supervisor.traza:
                    trazas.append({"toma": intento, **f})
                tomas_res.append(res)
                if res.get("decisiones") not in (None, ""):
                    corridas.append(res)
                res["regla_parada"] = ""
                cerrar_intento(res, semilla)
                raise
            # Una caída del enlace del obstáculo en la ÚLTIMA decisión, o en
            # la misma en que cortó otra regla, la tapa la reapertura de la
            # detención final (revisión 2026-10-03): se mira el contador.
            res["obst_enlace_cayo"] = int(
                (canal.obstaculo_envios_fallidos,
                 canal.obstaculo_reconexiones) != enlace_antes)
            res.update({"toma": intento, "modo": modo, "factor": factor,
                        "obst_x0": float(objetivo[0]),
                        "obst_y0": float(objetivo[1]), **info_col})
            res.update(columnas_registro_toma(
                poses_reg, pose_o_reg, id_robot_obstaculo,
                id_marcador_obstaculo, decisiones_previas, rpm_aborto,
                tau_prediccion_s, n))
            for f in supervisor.traza:
                trazas.append({"toma": intento, **f})
            tomas_res.append(res)
            # La línea de la toma dice POR QUÉ no vale: el motivo de la
            # medición si no es válida, el de la demo si lo es pero no sirve
            # para el video (antes un contacto salía "NO VÁLIDA" sin motivo).
            if res["valido_demo"]:
                rotulo = "VÁLIDA"
            elif not int(res.get("valido", 0) or 0):
                rotulo = f"NO VÁLIDA (medición: {res.get('motivo', '')})"
            else:
                rotulo = (f"NO VÁLIDA PARA LA DEMO "
                          f"({res.get('motivo_demo', '')})")
            try:
                d_txt = f"{float(res.get('d_min_obst_medida', '')):.4f} m"
            except (TypeError, ValueError):
                d_txt = "—"
            if campana is not None:
                incl_, motivo_i_ = campana_inclusion(res)
                ya = campana.estado()["incluidas"] + incl_
                rotulo += (f"  · INCLUIDA {ya}/{campana.meta}" if incl_
                           else f"  · NO INCLUIDA ({motivo_i_})")
                rotulo += f"  · video {'sí' if res['valido_demo'] else 'no'}"
            print(f"  >>> TOMA {intento}: {rotulo}  d_min obstáculo {d_txt}  "
                  f"frenos {res.get('frenos', 0)}")
            regla = regla_de_parada(res, corridas)
            # La cadena de frenos cuenta sólo las tomas que CORRIERON, con el
            # mismo criterio que el libro (`registrar`).
            if res.get("decisiones") not in (None, ""):
                corridas.append(res)
            res["regla_parada"] = regla or ""
            seguir_ = True
            if regla:
                seguir_ = parar_y_cerrar(res, regla, semilla)
            else:
                cerrar_intento(res, semilla)
            if not seguir_:
                detenida = regla
                break
    finally:
        canal.detener_todo()
        escribir_todo()
        entorno.finalizar()
    # ── fin de la copia 2692-2909 ──
    if detenida:
        vista["terminado"] = f"DETENIDA por regla de parada: {detenida}"
    return vista


# ════════════════════════════════════════════════════════════════════════════
# LÍNEA DE COMANDOS
# ════════════════════════════════════════════════════════════════════════════

def _semillas(texto: Optional[str]) -> List[int]:
    if not texto:
        return list(SEMILLAS_LOTE)
    return [int(x) for x in texto.split(",") if x.strip()]


def armar_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=f"Sesión demostrativa final ({LEYENDA}).")
    ap.add_argument("--modo", choices=("objetivos", "mejorada"), required=True)
    ap.add_argument("--episodios", type=int, default=3)
    ap.add_argument("--decisiones", type=int,
                    default=ses.DECISIONES_POR_EPISODIO)
    ap.add_argument("--factor", type=float, default=0.40)
    ap.add_argument("--rpm-aborto", type=float, default=RPM_CAP_LAB)
    ap.add_argument("--robot-obstaculo", type=int, default=None,
                    help="obligatorio en 'mejorada' (sin valor por defecto)")
    ap.add_argument("--colocacion", choices=("auto", "actual", "manual"),
                    default="auto")
    ap.add_argument("--semillas", type=_semillas, default=list(SEMILLAS_LOTE))
    ap.add_argument("--simulador", action="store_true")
    ap.add_argument("--puerto-simulador", type=int, default=PUERTO_SIMULADOR)
    ap.add_argument("--gui", action="append", default=None,
                    help="destino host:puerto; se puede repetir")
    ap.add_argument("--sin-gui", action="store_true")
    ap.add_argument("--etiqueta", default="")
    ap.add_argument("--hora-fin", default=None, help="HH:MM")
    ap.add_argument("--salida", default=str(DIR_SALIDA_DEMO_FINAL))
    return ap


def main(argv: Optional[List[str]] = None,
         preguntar: Optional[Callable[[str], str]] = None) -> int:
    args = armar_parser().parse_args(argv)
    mejorada = args.modo == "mejorada"
    if mejorada:
        if args.robot_obstaculo is None:
            print("[demo] --robot-obstaculo es obligatorio en 'mejorada'.")
            return 2
        if args.colocacion == "actual":
            print("[demo] 'actual' no va en 'mejorada': el obstáculo y los "
                  "agentes se colocan alrededor de su círculo (auto o manual).")
            return 2
    if args.episodios < 1 or args.decisiones < 1:
        print("[demo] --episodios y --decisiones tienen que ser ≥ 1.")
        return 2
    if len(args.semillas) < args.episodios:
        # Igual que las copias: más allá de la lista, SEMILLAS_LOTE[0] + k.
        print(f"[demo] ⓘ {len(args.semillas)} semillas para "
              f"{args.episodios} episodios: las que faltan siguen la fórmula "
              f"de la evaluación.")

    if args.simulador:
        cfg.activar_simulador_local(puerto_poses=args.puerto_simulador,
                                    puerto_base=args.puerto_simulador + 100)
    if mejorada and not args.simulador:
        # La L0 OK del día del robot del obstáculo, como en la demo: se lee
        # de `resultados_demo_obstaculo/` (no se toca `DIR_SALIDA_DEMO`). Sin
        # `--forzar`: en hardware no hay manera de saltearla.
        from demo_obstaculo_movil import l0_habilita
        ok_l0, motivo_l0 = l0_habilita(args.robot_obstaculo)
        print(f"[demo] L0 del robot {args.robot_obstaculo}: {motivo_l0}")
        if not ok_l0:
            print("✘ No se arranca: 'mejorada' exige una L0 OK del robot "
                  "del obstáculo con el offset de rumbo a ≤ 3° de la tabla.")
            return 6
    if mejorada:
        id_ctx, marc_ctx = (args.robot_obstaculo,
                            cfg.marcador_fijo_de_robot(args.robot_obstaculo))
    else:
        id_ctx, marc_ctx = (cfg.MAPEO_AGENTES[0].id_robot,
                            cfg.MAPEO_AGENTES[0].id_marcador)
    ctx = ses.Contexto(sesion="demo_final", id_robot=id_ctx,
                       marcador=marc_ctx, simulador=args.simulador,
                       **({"preguntar": preguntar} if preguntar else {}))
    atexit.register(ctx.detener_todo)
    ses._preparar(ctx)
    sim = None
    if args.simulador:
        # `_preparar` aplica la calibración MEDIDA del laboratorio también
        # acá; el simulador vive en el marco identidad.
        from replica_con_obstaculo import imponer_identidad
        imponer_identidad()
        print("[demo] --simulador: calibración IDENTIDAD (escala 1, rotación "
              "0, traslación 1.5/1.5, offsets 0).")
        sim = levantar_simulador(args.robot_obstaculo if mejorada else None,
                                 args.puerto_simulador)

    publicador = None
    if not args.sin_gui:
        publicador = PublicadorEstado(args.gui or [f"127.0.0.1:{PUERTO_PANEL}"])
    salida = preparar_salida(Path(args.salida))
    r: Any = None
    vista: Dict[str, Any] = {}
    try:
        if mejorada:
            try:
                r = sesion_mejorada(ctx, args, publicador, salida, vista)
            except _Terminar as exc:
                vista["terminado"] = str(exc)
                r = vista
            if "estado_demo" in r:
                r["estado_demo"].estado_sesion(evento="sesión terminada",
                                               detalle=r["terminado"])
            if publicador is not None:
                print(publicador.resumen())
        else:
            r = sesion_objetivos(ctx, args, publicador, salida)
    finally:
        if publicador is not None:
            publicador.cerrar()
        if sim is not None:
            if isinstance(r, dict) and "pila" in r:
                cerrar_pila_simulador(r["pila"])
            elif "pila" in vista:
                cerrar_pila_simulador(vista["pila"])
            atexit.unregister(ctx.detener_todo)
            ctx.detener_todo()
            sim.detener()
    if isinstance(r, ResultadoEtapa):
        print(f"\n>>> DEMO: {r.veredicto}  {r.detalle}")
        return 1
    if mejorada:
        if r.get("veredicto") == "FALLO":
            print(f">>> DEMO: FALLO  {r.get('detalle')}")
            return 1
        tm = r["tomas"]
        print(f">>> DEMO 'mejorada' ({LEYENDA}): "
              f"{sum(1 for t in tm if t.get('valido'))}/{len(tm)} tomas "
              f"válidas (lazo completo, sin aborto); para el video "
              f"{sum(1 for t in tm if t.get('valido_demo'))}/{len(tm)} "
              f"({r['terminado']}).")
        for ruta in r["rutas"]:
            if Path(ruta).exists():
                print(f"    {ruta}")
        return 0
    validos = sum(1 for e in r["episodios"] if e.get("valido"))
    print(f"\n>>> DEMO 'objetivos' ({LEYENDA}): {validos}/"
          f"{len(r['episodios'])} episodios válidos ({r['terminado']}).")
    for ruta in r["rutas"]:
        print(f"    {ruta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
