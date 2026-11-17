"""
panel_demo.py
=============
Interfaz gráfica 2D de la demostración final (`demo_final.py`):
DEMOSTRACIÓN, NO CITABLE. Proceso APARTE: recibe por UDP lo que publica
`publicador_estado.py` y dibuja. Si el panel muere, la sesión sigue (nunca
comparten proceso); si no llega nada, muestra "esperando al lazo".

    python panel_demo.py [--puerto 27300] [--grabar carpeta] [--hz 10]

  · un hilo recibe y guarda el ÚLTIMO estado; el dibujo va a ≤ 10 Hz con
    blitting (matplotlib, ya dependencia del proyecto). Si el cuadro tarda
    más de lo que da el ritmo, baja solo a 5 Hz y lo dice;
  · pensado para proyector y video: fondo claro, fuente grande;
  · `--grabar` guarda un PNG por segundo (para armar un video sin captura
    de pantalla). `--sin-ventana` dibuja sin abrir ventana (sólo con
    `--grabar`; para pruebas).

Todo en marco env ([0, 3]², origen en la esquina).

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import socket
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np

PUERTO_PANEL: int = 27300
#: Estela de cada agente: 5 s a 10 Hz.
LARGO_ESTELA: int = 50
RADIO_AGENTE_M: float = 0.075
RADIO_OBSTACULO_M: float = 0.15
D_O_M: float = 0.33
MAX_OBJETIVOS: int = 8
LEYENDA: str = "demostración, no citable"

#: Colores por estado del agente (y su leyenda).
COLORES = {"normal": "#2f6db5", "cbf": "#e39b16", "escape": "#c0392b",
           "retroceso": "#7f7f7f"}
TEXTO_ESTADO = {"normal": "normal", "cbf": "el filtro intervino",
                "escape": "en escape", "retroceso": "en retroceso"}


# ════════════════════════════════════════════════════════════════════════════
# RECEPCIÓN
# ════════════════════════════════════════════════════════════════════════════

class Receptor:
    """Hilo UDP: guarda lo último de cada tipo. Nunca bloquea al dibujo."""

    def __init__(self, puerto: int, host: str = "0.0.0.0") -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, puerto))
        self.sock.settimeout(0.2)
        self.lock = threading.Lock()
        self.inicio: Optional[Dict[str, Any]] = None
        self.paso: Optional[Dict[str, Any]] = None
        self.fin: Optional[Dict[str, Any]] = None
        self.estado: Optional[Dict[str, Any]] = None
        self.rejilla: Optional[np.ndarray] = None
        self.eventos: Deque[Tuple[float, str]] = deque(maxlen=20)
        self.estelas: Dict[int, Deque[Tuple[float, float]]] = {}
        self.cobertura: List[Tuple[int, float]] = []
        self.t_ultimo = 0.0
        self.recibidos = 0
        self.perdidos = 0
        self._seq = 0
        self.version = 0
        self._parar = threading.Event()
        self.hilo = threading.Thread(target=self._bucle, daemon=True)
        self.hilo.start()

    def detener(self) -> None:
        self._parar.set()

    def _bucle(self) -> None:
        while not self._parar.is_set():
            try:
                datos, _ = self.sock.recvfrom(65535)
                m = json.loads(datos.decode("utf-8"))
            except socket.timeout:
                continue
            except Exception:                               # noqa: BLE001
                continue
            try:
                self._procesar(m)
            except Exception:                               # noqa: BLE001
                pass

    def _procesar(self, m: Dict[str, Any]) -> None:
        with self.lock:
            seq = int(m.get("secuencia", 0))
            if self._seq and seq > self._seq + 1:
                self.perdidos += seq - self._seq - 1
            if seq < self._seq:             # la sesión se reinició
                self.perdidos = 0
            self._seq = seq
            self.recibidos += 1
            self.t_ultimo = time.time()
            tipo = m.get("tipo")
            if tipo == "inicio_episodio":
                self.inicio, self.fin, self.paso = m, None, None
                self.estelas.clear()
                self.cobertura = []
                self.rejilla = None
                self.eventos.append((time.time(),
                                     f"episodio {m.get('episodio')}: arranca "
                                     f"(semilla {m.get('semilla')})"))
            elif tipo == "paso":
                self.paso = m
                for a in m.get("agentes", []):
                    if a.get("x") is None:
                        continue
                    self.estelas.setdefault(
                        a["i"], deque(maxlen=LARGO_ESTELA)).append(
                        (a["x"], a["y"]))
                if m.get("cobertura") is not None:
                    self.cobertura.append((m["paso"], m["cobertura"]))
                rj = m.get("rejilla")
                if rj:
                    u8 = np.frombuffer(base64.b64decode(rj["b64"]),
                                       dtype=np.uint8)
                    # `_grid_aoi` se indexa [x, y]; imshow quiere [fila=y, col=x].
                    self.rejilla = u8.reshape(rj["forma"]).T.astype(float) / 255
                for e in m.get("eventos", []):
                    self.eventos.append((time.time(), e))
            elif tipo == "fin_episodio":
                self.fin = m
                r = m.get("resultado", {})
                self.eventos.append((time.time(),
                                     f"episodio {m.get('episodio')}: "
                                     f"{'VÁLIDO' if r.get('valido') else 'INVÁLIDO'}"
                                     + (f" — {r.get('motivo')}"
                                        if r.get("motivo") else "")))
            elif tipo == "estado_sesion":
                self.estado = m
                txt = m.get("evento", "")
                if m.get("detalle"):
                    txt += f": {m['detalle']}"
                self.eventos.append((time.time(), txt))
            self.version += 1

    def instantanea(self) -> Dict[str, Any]:
        with self.lock:
            return {"inicio": self.inicio, "paso": self.paso, "fin": self.fin,
                    "estado": self.estado, "rejilla": self.rejilla,
                    "eventos": list(self.eventos),
                    "estelas": {k: list(v) for k, v in self.estelas.items()},
                    "cobertura": list(self.cobertura),
                    "t_ultimo": self.t_ultimo, "perdidos": self.perdidos,
                    "version": self.version}


# ════════════════════════════════════════════════════════════════════════════
# DIBUJO
# ════════════════════════════════════════════════════════════════════════════

def _fmt(x: Any, f: str = "{:.3f}", nada: str = "—") -> str:
    try:
        return f.format(float(x)) if x is not None else nada
    except (TypeError, ValueError):
        return nada


def _estado_agente(a: Dict[str, Any]) -> str:
    if a.get("retroceso"):
        return "retroceso"
    if a.get("escape"):
        return "escape"
    if a.get("cbf"):
        return "cbf"
    return "normal"


class Panel:
    def __init__(self, receptor: Receptor, hz: float,
                 grabar: Optional[Path]) -> None:
        import matplotlib.pyplot as plt
        from matplotlib.colors import LinearSegmentedColormap
        from matplotlib.patches import Circle, Rectangle
        self.plt = plt
        self.rec = receptor
        self.hz = hz
        self.grabar = grabar
        self._t_png = 0.0
        self._tiempos: Deque[float] = deque(maxlen=30)
        self._avisado_5hz = False
        plt.rcParams.update({"font.size": 15, "font.family": "DejaVu Sans"})
        fig = plt.figure(figsize=(16, 9), facecolor="white")
        self.fig = fig
        try:
            fig.canvas.manager.set_window_title(f"Panel de la demo ({LEYENDA})")
        except Exception:                                   # noqa: BLE001
            pass
        # Mapa de la arena
        ax = fig.add_axes([0.02, 0.06, 0.53, 0.88])
        self.ax = ax
        ax.set_xlim(-0.05, 3.05)
        ax.set_ylim(-0.05, 3.05)
        ax.set_aspect("equal")
        ax.set_xticks([0, 1, 2, 3])
        ax.set_yticks([0, 1, 2, 3])
        ax.tick_params(labelsize=11)
        cmap = LinearSegmentedColormap.from_list(
            "aoi", ["#2e9e4f", "#cfe8c4", "#efefef"])
        self.img = ax.imshow(np.ones((64, 64)), extent=(0, 3, 0, 3),
                             origin="lower", cmap=cmap, vmin=0, vmax=1,
                             interpolation="nearest", animated=True)
        # Paredes y banda de margen: animadas, para quedar SOBRE la rejilla.
        m = 0.18
        self.paredes = [
            Rectangle((0, 0), 3, 3, fill=False, lw=3, color="black",
                      animated=True),
            Rectangle((m, m), 3 - 2 * m, 3 - 2 * m, fill=False, lw=1.5,
                      ls="--", color="#444444", animated=True)]
        for r_ in self.paredes:
            ax.add_patch(r_)
        self.objetivos = [Circle((-9, -9), 0.1, fill=True, alpha=0.25,
                                 color="#8e44ad", ec="#8e44ad", lw=2,
                                 animated=True) for _ in range(MAX_OBJETIVOS)]
        for c in self.objetivos:
            ax.add_patch(c)
        self.ref_obst = Circle((-9, -9), 0.6, fill=False, ls=":", lw=1.5,
                               color="#333333", animated=True)
        self.anillo_obst = Circle((-9, -9), D_O_M, fill=False, ls="--", lw=2,
                                  color="black", animated=True)
        self.obst = Circle((-9, -9), RADIO_OBSTACULO_M, color="black",
                           animated=True)
        for p in (self.ref_obst, self.anillo_obst, self.obst):
            ax.add_patch(p)
        self.estelas = []
        self.discos = []
        self.rumbos = []
        self.etiquetas = []
        for _ in range(10):
            ln, = ax.plot([], [], lw=2, alpha=0.45, color=COLORES["normal"],
                          animated=True)
            self.estelas.append(ln)
            d = Circle((-9, -9), RADIO_AGENTE_M, color=COLORES["normal"],
                       ec="white", lw=1.5, animated=True)
            ax.add_patch(d)
            self.discos.append(d)
            r, = ax.plot([], [], lw=3, color="white", animated=True)
            self.rumbos.append(r)
            self.etiquetas.append(ax.text(-9, -9, "", fontsize=11,
                                          ha="center", va="bottom",
                                          weight="bold", animated=True))
        self.titulo_mapa = ax.set_title("", fontsize=16, animated=True)
        # Leyenda de estados
        for k, (nombre, col) in enumerate(COLORES.items()):
            fig.text(0.04 + 0.13 * k, 0.015, f"● {TEXTO_ESTADO[nombre]}",
                     color=col, fontsize=13, weight="bold")
        # Columna de cifras
        self.axt = fig.add_axes([0.58, 0.30, 0.41, 0.66])
        self.axt.axis("off")
        self.reloj = self.axt.text(1.0, 1.0, "", ha="right", va="top",
                                   fontsize=30, family="DejaVu Sans Mono",
                                   weight="bold", animated=True)
        self.cabeza = self.axt.text(0.0, 1.0, "", ha="left", va="top",
                                    fontsize=18, weight="bold", animated=True)
        self.filas = []
        for k in range(10):
            et = self.axt.text(0.0, 0.84 - 0.083 * k, "", ha="left",
                               va="top", fontsize=17, animated=True)
            va = self.axt.text(1.0, 0.84 - 0.083 * k, "", ha="right",
                               va="top", fontsize=22, weight="bold",
                               animated=True)
            self.filas.append((et, va))
        self.pie = self.axt.text(0.0, 0.0, "", ha="left", va="bottom",
                                 fontsize=13, color="#444444", animated=True)
        # Gráfica de cobertura
        self.axc = fig.add_axes([0.62, 0.08, 0.36, 0.16])
        self.axc.set_xlim(0, 500)
        self.axc.set_ylim(0, 1)
        self.axc.set_xlabel("decisión", fontsize=12)
        self.axc.set_ylabel("cobertura", fontsize=12)
        self.axc.tick_params(labelsize=10)
        self.axc.grid(alpha=0.3)
        self.curva, = self.axc.plot([], [], lw=2.5, color="#2e9e4f",
                                    animated=True)
        # Línea de estado y tarjeta de resumen
        self.linea = fig.text(0.58, 0.265, "", fontsize=14, color="#222222",
                              animated=True)
        self.tarjeta = self.ax.text(
            1.5, 1.5, "", ha="center", va="center", fontsize=20,
            weight="bold", animated=True,
            bbox=dict(boxstyle="round,pad=0.8", fc="white", ec="#333333",
                      alpha=0.92))
        self.espera = self.ax.text(1.5, 2.75, "", ha="center", va="center",
                                   fontsize=22, color="#aa3300",
                                   weight="bold", animated=True)
        fig.text(0.995, 0.005, LEYENDA, ha="right", va="bottom", fontsize=10,
                 color="#888888")
        # La rejilla NO va en esta lista: se dibuja sólo cuando cambia (cada
        # 5 decisiones) y queda guardada como capa del mapa (`_capa_rejilla`).
        # Dibujarla en cada cuadro costaba 16 ms de los 30 (medido el 23-10).
        self.animados = (self.paredes + self.objetivos
                         + [self.ref_obst, self.anillo_obst, self.obst]
                         + self.estelas + self.discos + self.rumbos
                         + self.etiquetas
                         + [self.titulo_mapa, self.reloj, self.cabeza]
                         + [x for f in self.filas for x in f]
                         + [self.pie, self.curva, self.linea, self.tarjeta,
                            self.espera])
        self._fondo = None
        self._capa_rejilla = None
        self._rejilla = None
        self._xmax_cob = 500
        fig.canvas.mpl_connect("draw_event", self._al_redibujar)
        fig.canvas.mpl_connect("resize_event", lambda _e: None)

    # ── blitting ─────────────────────────────────────────────────────────
    def _al_redibujar(self, _evento: Any) -> None:
        self._fondo = self.fig.canvas.copy_from_bbox(self.fig.bbox)
        self._capa_rejilla = None
        self._dibujar_animados()

    def _dibujar_animados(self) -> None:
        """Rejilla desde su capa (o dibujada y guardada si cambió) y, encima,
        el resto de los artistas animados."""
        canvas = self.fig.canvas
        if self._capa_rejilla is None:
            self.fig.draw_artist(self.img)
            self._capa_rejilla = canvas.copy_from_bbox(self.ax.bbox)
        else:
            canvas.restore_region(self._capa_rejilla)
        for a in self.animados:
            self.fig.draw_artist(a)

    def cuadro(self) -> None:
        t0 = time.perf_counter()
        self._actualizar(self.rec.instantanea())
        canvas = self.fig.canvas
        if self._fondo is None:
            canvas.draw()
        else:
            canvas.restore_region(self._fondo)
            self._dibujar_animados()
            canvas.blit(self.fig.bbox)
        canvas.flush_events()
        ahora = time.time()
        if self.grabar is not None and ahora - self._t_png >= 1.0:
            self._t_png = ahora
            self.fig.savefig(self.grabar /
                             f"panel_{datetime.now():%Y%m%d_%H%M%S}.png",
                             dpi=80)
        dt = time.perf_counter() - t0
        self._tiempos.append(dt)
        if (self.hz > 5 and len(self._tiempos) >= 20
                and np.mean(self._tiempos) > 1.0 / self.hz):
            self.hz = 5.0
            if not self._avisado_5hz:
                self._avisado_5hz = True
                print(f"[panel] el cuadro tarda {1000*np.mean(self._tiempos):.0f}"
                      f" ms: se baja a 5 Hz.")

    # ── contenido ────────────────────────────────────────────────────────
    def _actualizar(self, s: Dict[str, Any]) -> None:
        self.reloj.set_text(datetime.now().strftime("%H:%M:%S.")
                            + f"{datetime.now().microsecond // 100000}")
        ini, paso, fin, est = s["inicio"], s["paso"], s["fin"], s["estado"]
        vivo = s["t_ultimo"] and (time.time() - s["t_ultimo"] < 3.0)
        modo = (paso or ini or est or {}).get("modo", "—")
        if s["rejilla"] is not None and s["rejilla"] is not self._rejilla:
            self._rejilla = s["rejilla"]
            self.img.set_data(s["rejilla"])
            self._capa_rejilla = None       # se vuelve a dibujar una vez
        # Esperando
        if not s["t_ultimo"]:
            self.espera.set_text("esperando al lazo…")
        elif not vivo and not (est and "terminada" in est.get("evento", "")):
            self.espera.set_text("esperando al lazo…")
        else:
            self.espera.set_text("")
        n_dec = (ini or {}).get("decisiones") or 500
        if n_dec != self._xmax_cob:
            self._xmax_cob = n_dec
            self.axc.set_xlim(0, n_dec)
            self._fondo = None
        # Objetivos
        objs = (paso or ini or {}).get("objetivos") or []
        for k, c in enumerate(self.objetivos):
            if k < len(objs) and objs[k].get("x") is not None:
                c.center = (objs[k]["x"], objs[k]["y"])
                c.set_radius(max(float(objs[k].get("sigma") or 0.1), 0.02))
                c.set_visible(True)
            else:
                c.set_visible(False)
        # Agentes
        agentes = (paso or {}).get("agentes") or []
        for k in range(len(self.discos)):
            a = agentes[k] if k < len(agentes) else None
            if a is None or a.get("x") is None:
                for art in (self.discos[k], self.rumbos[k], self.estelas[k],
                            self.etiquetas[k]):
                    art.set_visible(False)
                continue
            col = COLORES[_estado_agente(a)]
            x, y, th = a["x"], a["y"], a.get("th") or 0.0
            self.discos[k].center = (x, y)
            self.discos[k].set_color(col)
            self.discos[k].set_edgecolor("white")
            self.rumbos[k].set_data([x, x + 0.11 * math.cos(th)],
                                    [y, y + 0.11 * math.sin(th)])
            self.rumbos[k].set_color("white" if col != "#7f7f7f" else "black")
            est_k = s["estelas"].get(a["i"], [])
            self.estelas[k].set_data([p[0] for p in est_k],
                                     [p[1] for p in est_k])
            self.estelas[k].set_color(COLORES["normal"])
            self.etiquetas[k].set_position((x, y + RADIO_AGENTE_M + 0.02))
            self.etiquetas[k].set_text(str(a.get("robot", "")))
            for art in (self.discos[k], self.rumbos[k], self.estelas[k],
                        self.etiquetas[k]):
                art.set_visible(True)
        # Obstáculo
        po = (ini or {}).get("obstaculo")
        ob = (paso or {}).get("obstaculo")
        if po and po.get("centro"):
            self.ref_obst.center = tuple(po["centro"])
            self.ref_obst.set_radius(po.get("R", 0.6))
            self.ref_obst.set_visible(True)
        else:
            self.ref_obst.set_visible(False)
        if ob and ob.get("x") is not None:
            self.obst.center = (ob["x"], ob["y"])
            self.anillo_obst.center = (ob["x"], ob["y"])
            self.obst.set_visible(True)
            self.anillo_obst.set_visible(True)
        else:
            self.obst.set_visible(False)
            self.anillo_obst.set_visible(False)
        # Encabezado
        ep = (paso or ini or {}).get("episodio")
        n_ep = (ini or {}).get("episodios")
        self.titulo_mapa.set_text(
            f"Arena 3 × 3 m — {len(agentes)} agentes"
            + (" + obstáculo móvil" if modo == "mejorada" else ""))
        self.cabeza.set_text(f"modo «{modo}»"
                             + (f"\n{ini.get('etiqueta')}"
                                if ini and ini.get("etiqueta") else ""))
        ac = (paso or {}).get("acumulados") or {}
        filas = [
            ("episodio", f"{ep if ep is not None else '—'}"
                         + (f" / {n_ep}" if n_ep else "")),
            ("decisión", f"{(paso or {}).get('paso', -1) + 1} / {n_dec}"
             if paso else "—"),
            ("cobertura AoI (rejilla completa)",
             _fmt((paso or {}).get("cobertura"))),
            ("intervención del filtro",
             _fmt(ac.get("frac_cbf"), "{:.1%}")),
            ("escapes · retrocesos",
             f"{ac.get('escapes', '—')} · {ac.get('retrocesos', '—')}"),
            ("pares < 0.15 m", f"{ac.get('pares_015', '—')}"),
            ("distancia mínima a la pared",
             _fmt(ac.get("d_pared_min"), "{:.3f} m")),
        ]
        d_obst = None
        if modo == "mejorada":
            d_obst = (ob or {}).get("d_min")
            filas.append(("distancia al obstáculo",
                          _fmt(d_obst, "{:.3f} m")))
        for k, (et, va) in enumerate(self.filas):
            if k < len(filas):
                et.set_text(filas[k][0])
                va.set_text(filas[k][1])
                color = "black"
                if filas[k][0] == "pares < 0.15 m" and ac.get("pares_015"):
                    color = "#c0392b"
                if filas[k][0] == "distancia al obstáculo" and d_obst is not None:
                    color = ("#2e9e4f" if d_obst >= D_O_M else
                             "#e39b16" if d_obst >= 0.20 else "#c0392b")
                va.set_color(color)
            else:
                et.set_text("")
                va.set_text("")
        self.pie.set_text(
            f"ciclo p95 {_fmt(ac.get('ciclo_p95_ms'), '{:.1f}')} ms · "
            f"latencia de poses p95 {_fmt(ac.get('lat_poses_p95_ms'), '{:.1f}')} ms"
            f" · periodo 100 ms"
            + (f" · datagramas perdidos {s['perdidos']}" if s["perdidos"] else ""))
        cob = s["cobertura"]
        self.curva.set_data([c[0] for c in cob], [c[1] for c in cob])
        ultimo = s["eventos"][-1][1] if s["eventos"] else ""
        self.linea.set_text(f"▸ {ultimo}" if ultimo else "")
        # Tarjeta de resumen (se queda hasta el siguiente episodio)
        if fin:
            r = fin.get("resultado", {})
            texto = (f"Episodio {fin.get('episodio')}: "
                     f"{'VÁLIDO' if r.get('valido') else 'INVÁLIDO'}\n"
                     f"cobertura final {_fmt(r.get('cobertura_aoi'))}\n"
                     f"colisiones < 0.15 m: {r.get('colisiones_015', '—')}\n"
                     f"d mín a la pared {_fmt(r.get('d_pared_min'), '{:.3f} m')}")
            if fin.get("valido_demo") is not None:
                texto += f"\nválido para el video: {'sí' if fin['valido_demo'] else 'no'}"
            if r.get("motivo"):
                texto += f"\n{str(r['motivo'])[:60]}"
            self.tarjeta.set_text(texto)
            self.tarjeta.set_visible(True)
        else:
            self.tarjeta.set_visible(False)


def bajar_prioridad() -> str:
    """En Windows, el panel corre con prioridad BAJO LO NORMAL: si compite
    por CPU con el lazo de control (misma laptop), pierde el panel."""
    if sys.platform != "win32":
        return "sin cambio (no es Windows)"
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        # Con las firmas explícitas: sin ellas el seudo-identificador del
        # proceso (−1) no llega como HANDLE y la llamada falla en silencio.
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.SetPriorityClass.restype = wintypes.BOOL
        ok = k32.SetPriorityClass(k32.GetCurrentProcess(), 0x00004000)
        return "bajo lo normal" if ok else "no se pudo cambiar"
    except Exception as exc:                                # noqa: BLE001
        return f"no se pudo cambiar ({exc})"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=f"Panel de la demo ({LEYENDA}).")
    ap.add_argument("--puerto", type=int, default=PUERTO_PANEL)
    ap.add_argument("--grabar", default=None, help="carpeta: un PNG por segundo")
    ap.add_argument("--hz", type=float, default=10.0)
    ap.add_argument("--sin-ventana", action="store_true",
                    help="sin ventana (backend Agg), para pruebas")
    ap.add_argument("--duracion-s", type=float, default=0.0,
                    help="cerrar solo tras tantos segundos (0 = nunca)")
    args = ap.parse_args(argv)
    if args.sin_ventana:
        import matplotlib
        matplotlib.use("Agg")
    grabar = Path(args.grabar) if args.grabar else None
    if grabar is not None:
        grabar.mkdir(parents=True, exist_ok=True)
    print(f"[panel] prioridad del proceso: {bajar_prioridad()}")
    rec = Receptor(args.puerto)
    panel = Panel(rec, min(args.hz, 10.0), grabar)
    plt = panel.plt
    if not args.sin_ventana:
        plt.show(block=False)
    panel.fig.canvas.draw()
    print(f"[panel] escuchando UDP {args.puerto} — {LEYENDA}. Cerrá la "
          f"ventana o Ctrl+C para salir.")
    t_fin = time.time() + args.duracion_s if args.duracion_s > 0 else None
    cuadros = 0
    try:
        while True:
            t0 = time.perf_counter()
            if not args.sin_ventana and not plt.fignum_exists(panel.fig.number):
                break
            panel.cuadro()
            cuadros += 1
            if t_fin is not None and time.time() >= t_fin:
                break
            resto = 1.0 / panel.hz - (time.perf_counter() - t0)
            if resto > 0:
                if args.sin_ventana:
                    time.sleep(resto)
                else:
                    # NO `plt.pause`: si la figura quedó marcada como
                    # modificada (y cada cuadro la marca) la redibuja ENTERA
                    # antes de esperar, además del cuadro por blitting. Era la
                    # mayor parte de un núcleo ocupado (medido el 23-10).
                    panel.fig.canvas.start_event_loop(resto)
    except KeyboardInterrupt:
        pass
    finally:
        rec.detener()
    media = 1000 * np.mean(panel._tiempos) if panel._tiempos else float("nan")
    print(f"[panel] {cuadros} cuadros, {rec.recibidos} mensajes, "
          f"{rec.perdidos} perdidos; cuadro medio {media:.1f} ms "
          f"(ritmo final {panel.hz:.0f} Hz).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
