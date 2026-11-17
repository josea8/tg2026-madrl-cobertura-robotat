"""
publicador_estado.py
====================
Publicación por UDP del estado de la demostración final (`demo_final.py`)
hacia la interfaz gráfica (`panel_demo.py`) y, en la fase 2, al espejo de
Webots. DEMOSTRACIÓN, NO CITABLE.

Reglas (spec de la demo final, §4):
  · un socket UDP NO bloqueante; cada destino recibe el mismo datagrama;
  · `publicar` JAMÁS lanza: todo va adentro de `try/except Exception`. Una
    excepción acá abortaría el episodio, porque `_correr_episodio` no la
    captura. Cuenta los errores y, tras `MAX_ERRORES_SEGUIDOS` consecutivos,
    se apaga solo y lo dice en consola UNA vez;
  · ningún datagrama pasa de `MAX_DATAGRAMA_B` (60 KB): el que se pasa se
    descarta y cuenta como error. Hacia 127.0.0.1 no hay fragmentación; hacia
    otra máquina el mensaje con la rejilla (~6 KB) puede fragmentarse en IP:
    si se pierde un fragmento se pierde ese cuadro, y es tolerable.

Mensajes: JSON con `tipo`, `secuencia` y `t` (hora de pared), los pone
`publicar`. Los NaN/inf salen como `null` (JSON estricto).

En HILO (por defecto, desde el 23-10): `publicar` sólo numera y encola; un
hilo del publicador serializa y envía, en orden, mientras el lazo duerme
(~88 ms de cada 100). Medido en el banco de la prueba 5: en el hilo de
control, serializar y enviar costaban ~0.2 ms por decisión. La cola tiene
tope (`COLA_MAX`); si el hilo se atrasa, se descarta lo más viejo y se
cuenta en `descartados` (un cuadro perdido, no un error). `cerrar()` vacía la cola antes de cerrar el socket.
`en_hilo=False` envía en el acto (pruebas del núcleo).

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import json
import math
import socket
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: Tope del datagrama (la rejilla de 64×64 en base64 ocupa ~5.5 KB).
MAX_DATAGRAMA_B: int = 60_000
#: Errores consecutivos tras los que el publicador se apaga solo.
MAX_ERRORES_SEGUIDOS: int = 20
#: Mensajes pendientes como máximo en la cola del hilo de envío.
COLA_MAX: int = 100
#: Puerto por defecto del panel.
PUERTO_PANEL: int = 27300


def _limpiar(x: Any) -> Any:
    """NaN/inf → None, numpy → tipos de Python (JSON estricto)."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {str(k): _limpiar(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_limpiar(v) for v in x]
    if hasattr(x, "item") and not isinstance(x, (str, bytes)):
        try:
            return _limpiar(x.item())
        except Exception:                                   # noqa: BLE001
            return None
    return x


def parsear_destino(texto: str) -> Tuple[str, int]:
    """'host:puerto' o 'puerto' → (host, puerto). Lanza ValueError."""
    texto = texto.strip()
    if ":" in texto:
        host, puerto = texto.rsplit(":", 1)
        return host.strip() or "127.0.0.1", int(puerto)
    return "127.0.0.1", int(texto)


class PublicadorEstado:
    """
    `PublicadorEstado(["127.0.0.1:27300", ...])`. Los destinos se resuelven
    UNA vez al construir (resolver un nombre en cada envío costaría
    milisegundos); uno que no resuelve se descarta con aviso y no lanza.
    """

    def __init__(self, destinos: Sequence[str], en_hilo: bool = True) -> None:
        self.destinos: List[Tuple[str, int]] = []
        self.en_hilo = bool(en_hilo)
        self._cola: deque = deque()
        self._hay = threading.Event()
        self._parar = threading.Event()
        self._hilo: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.activo = True
        self.secuencia = 0
        self.enviados = 0
        self.errores = 0
        self.errores_seguidos = 0
        self.descartados = 0
        self.ultimo_error = ""
        self._avisado = False
        self._sock: Optional[socket.socket] = None
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setblocking(False)
            # Windows: un ICMP "puerto inalcanzable" (panel cerrado) deja
            # pendiente un WSAECONNRESET que sale en la operación siguiente.
            if hasattr(socket, "SIO_UDP_CONNRESET"):
                self._sock.ioctl(socket.SIO_UDP_CONNRESET, False)
        except Exception as exc:                            # noqa: BLE001
            self._apagar(f"no se pudo abrir el socket UDP: {exc}")
            return
        for d in destinos:
            try:
                host, puerto = parsear_destino(d)
                ip = socket.gethostbyname(host)
                if not 0 < puerto < 65536:
                    raise ValueError(f"puerto {puerto} fuera de rango")
                self.destinos.append((ip, puerto))
            except Exception as exc:                        # noqa: BLE001
                print(f"[publicador] destino {d!r} descartado: {exc}")
        if not self.destinos:
            self._apagar("sin destinos válidos")
            return
        if self.en_hilo:
            self._hilo = threading.Thread(target=self._bucle_envio,
                                          name="publicador", daemon=True)
            self._hilo.start()

    def _apagar(self, motivo: str) -> None:
        self.activo = False
        if not self._avisado:
            self._avisado = True
            print(f"[publicador] ⚠ publicación APAGADA ({motivo}). La sesión "
                  f"sigue igual; sólo deja de haber interfaz gráfica.")

    def registrar_error(self, exc: BaseException) -> None:
        """Un error (de armar o de enviar). Nunca lanza."""
        try:
            with self._lock:
                self._registrar_error(exc)
        except Exception:                                   # noqa: BLE001
            pass

    def _registrar_error(self, exc: BaseException) -> None:
        try:
            self.errores += 1
            self.errores_seguidos += 1
            self.ultimo_error = f"{type(exc).__name__}: {exc}"
            if self.errores_seguidos >= MAX_ERRORES_SEGUIDOS and self.activo:
                self._apagar(f"{self.errores_seguidos} errores seguidos; "
                             f"último: {self.ultimo_error}")
        except Exception:                                   # noqa: BLE001
            pass

    def publicar(self, mensaje: Dict[str, Any]) -> bool:
        """Numera el mensaje y lo encola (en hilo) o lo envía en el acto.
        Devuelve si quedó encolado o salió a algún destino. JAMÁS lanza."""
        if not self.activo:
            return False
        try:
            self.secuencia += 1
            cuerpo = dict(mensaje)
            cuerpo["secuencia"] = self.secuencia
            cuerpo["t"] = time.time()
            if not self.en_hilo:
                return self._enviar(cuerpo)
            if len(self._cola) >= COLA_MAX:
                # Un cuadro perdido, no una falla: no cuenta para apagar.
                self._cola.popleft()
                self.descartados += 1
            self._cola.append(cuerpo)
            self._hay.set()
            return True
        except Exception as exc:                            # noqa: BLE001
            self.registrar_error(exc)
            return False

    def _bucle_envio(self) -> None:
        while True:
            self._hay.wait(0.2)
            self._hay.clear()
            while self._cola:
                try:
                    cuerpo = self._cola.popleft()
                except IndexError:
                    break
                if self.activo:
                    self._enviar(cuerpo)
            if self._parar.is_set() and not self._cola:
                return

    def _enviar(self, cuerpo: Dict[str, Any]) -> bool:
        """Serializa y envía a todos los destinos. JAMÁS lanza."""
        try:
            # Directo primero: el mensaje de `paso` ya viene con escalares de
            # Python y recorrerlo para limpiar costaba ~0.1 ms por decisión
            # (medido el 23-10). Si trae NaN, inf o tipos de numpy, el JSON
            # estricto falla y se limpia.
            try:
                texto = json.dumps(cuerpo, separators=(",", ":"),
                                   allow_nan=False)
            except (ValueError, TypeError):
                texto = json.dumps(_limpiar(cuerpo), separators=(",", ":"),
                                   allow_nan=False)
            datos = texto.encode("utf-8")
            if len(datos) > MAX_DATAGRAMA_B:
                raise ValueError(f"datagrama de {len(datos)} B > "
                                 f"{MAX_DATAGRAMA_B} B")
            salio = False
            fallo: Optional[BaseException] = None
            for destino in self.destinos:
                try:
                    self._sock.sendto(datos, destino)
                    salio = True
                except Exception as exc:                    # noqa: BLE001
                    fallo = exc
            if fallo is not None and not salio:
                raise fallo
            with self._lock:
                self.enviados += 1
                self.errores_seguidos = 0
            return True
        except Exception as exc:                            # noqa: BLE001
            self.registrar_error(exc)
            return False

    def cerrar(self, espera_s: float = 2.0) -> None:
        """Vacía la cola (hasta `espera_s`) y cierra. JAMÁS lanza."""
        try:
            if self._hilo is not None:
                self._parar.set()
                self._hay.set()
                self._hilo.join(timeout=espera_s)
        except Exception:                                   # noqa: BLE001
            pass
        try:
            if self._sock is not None:
                self._sock.close()
        except Exception:                                   # noqa: BLE001
            pass

    def resumen(self) -> str:
        return (f"[publicador] enviados {self.enviados}, errores "
                f"{self.errores}, descartados {self.descartados}, {'activo' if self.activo else 'APAGADO'}"
                + (f" (último error: {self.ultimo_error})"
                   if self.ultimo_error else ""))
