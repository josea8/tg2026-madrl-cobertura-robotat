"""
campana_obstaculo.py
====================
Libro de la CAMPAÑA DE MEDICIÓN L2 con el obstáculo móvil (OK de José,
2026-10-08; `tesis/PROPUESTA_campana_L2_obstaculo.md`). La L2 deja de ser
sólo una demo: tomas medidas en el Robotat, réplica pareada y análisis
fijado antes, como la evaluación del 30-09.

El libro vive en `resultados_demo_obstaculo/campanas/<nombre>/`:

  · `campana.json` — cabecera: meta (50), mínimo (30), tope de intentos
    (100), plataforma (hw/simulador), robot del obstáculo, base de semillas
    y el sha256 de los ARCHIVOS CONGELADOS al crearla.
  · `libro.csv` — SÓLO SE AGREGAN filas (nunca se reescribe): creación,
    apertura y cierre de cada sesión, reserva y resultado de cada intento,
    correcciones declaradas, cierre de la campaña.

Reglas (decisiones de José del 2026-10-08):

  · SEMILLAS ÚNICAS en toda la campaña, también al cortar y reanudar: la del
    intento k es la semilla base de la campaña + k − 1 (un bloque nunca usado). Se
    RESERVA antes de colocar (ya fija los blancos y los rumbos); una
    reserva sin resultado (Ctrl+C, caída) queda gastada como
    "interrumpida".
  · INCLUSIÓN: toma válida para la medición Y el obstáculo recorrió al
    menos la mitad de lo comandado (sólo si lo comandado es ≥ 0.20 m). Los
    frenos de respaldo y los contactos son RESULTADOS, no exclusiones.
  · Meta 50 incluidas, mínimo 30, tope 100 intentos; la hora de fin de cada
    sesión se fija antes de empezarla. Esas paradas no miran resultados; el
    único cierre automático por resultados es el criterio de seguridad de
    abajo (contactos), y ningún cierre mira la cobertura.
  · La cadena "freno en dos tomas seguidas" se ARRASTRA con el libro.
  · Un "no" en la pausa de seguridad termina sólo la SESIÓN; cerrar la
    CAMPAÑA es un comando aparte, con motivo escrito.
  · CRITERIO DE SEGURIDAD (José, 2026-10-09): la campaña se cierra SOLA
    cuando se acumulan dos tomas CORRIDAS con contacto medido (< 0.15 m entre
    centros: con el obstáculo, `d_min_obst_medida`, o entre agentes,
    `colisiones_015`). Las pausas siguen como están; los contactos de la
    colocación no cuentan (siguen siendo regla de parada de la sesión). Lo
    anota el propio libro al registrar la segunda. Ninguno de los dos
    cierres mira la cobertura.
  · HASH: si cambia un archivo congelado, el libro se niega a seguir. La
    salida declarada es `--corregir-campana "motivo"`, que deja en el libro
    el hash nuevo (y cuáles cambiaron). La CONFIGURACIÓN DEL DÍA (offsets,
    calibración) se registra en cada apertura y NO bloquea. De
    `config_robotat.py` sólo es configuración del día lo que nombra
    `NOMBRES_CONFIG_DEL_DIA` (offsets de rumbo, marco y escala del mocap y sus
    banderas de verificación): todo lo demás (rampa, rpm, antigüedad de
    pose, mapeo de agentes…) entra con una huella `config_robotat.py#sin_
    calibracion` y BLOQUEA como un archivo congelado (revisión del 08-10).
  · El libro se defiende de lo que pasa en el laboratorio: una última línea
    truncada por un corte de luz se aísla (no se le pega la fila siguiente),
    un libro.csv bloqueado por Excel se reintenta con aviso, el candado se
    suelta si falla la apertura, cerrar/corregir se niegan con una sesión
    abierta, y cada sesión verifica que el candado siga siendo suyo.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

_CARPETA = Path(__file__).resolve().parent
_TESIS = _CARPETA.parents[2]

#: Semilla del intento k = semilla base + k − 1. Bloque 422000–422999, nuevo por
#: decisión de José (17-10): el 420000–420109 lo usaron el 30-09, los ensayos y
#: la Fase 0; el 421000… la campaña descartada `L2_obstaculo` (16-10) y los
#: ensayos de campaña en el simulador. Cada campaña guarda la suya en la
#: cabecera (`semilla_base`) y la usa: una campaña vieja no cambia de bloque.
SEMILLA_BASE: int = 422000
INTENTO_MAX_FORMULA: int = 999
META_POR_DEFECTO: int = 50
MINIMO_POR_DEFECTO: int = 30
TOPE_POR_DEFECTO: int = 100

#: Archivos cuyo sha256 BLOQUEA. El código que carga una sesión (medido:
#: los módulos del proyecto en `sys.modules` al correr la demo), el modelo
#: de la política, y el plan y el script de análisis fijados antes.
ARCHIVOS_CONGELADOS: Tuple[str, ...] = (
    "adaptadores_robotat.py",
    "calibracion_sesion.py",
    "campana_obstaculo.py",
    "colocacion_autonoma.py",
    "colocacion_con_obstaculo.py",
    "coordinador_enjambre.py",
    "demo_obstaculo_movil.py",
    "interfaces.py",
    "lanzar_robotat.py",
    "lib/__init__.py",
    "lib/concentration_dynamics.py",
    "lib/filtro_cbf.py",
    "lib/swarm_env_skeleton.py",
    "protocolo.py",
    "protocolo_robotat.py",
    "retroceso_congelamiento.py",
    "sesion_robotat.py",
    "modelos/modelo_sanidad.zip",
    "analizar_campana_l2.py",
    "verificar_campana_l2.py",
    "TESIS/PLAN_ANALISIS_campana_L2.md",
    "config_robotat.py#sin_calibracion",
)
#: La configuración del día: se REGISTRA en cada apertura, no bloquea.
ARCHIVOS_CONFIGURACION: Tuple[str, ...] = (
    "config_robotat.py",
    "calibracion_medida.json",
)
#: Lo único de `config_robotat.py` que es configuración del día (decisión de
#: José: "offsets, calibración"): los offsets de rumbo, el marco y la escala
#: del mocap (lo que vuelca `calibracion_sesion.aplicar_a_config`) y sus
#: banderas de verificación. La huella `#sin_calibracion` los excluye.
NOMBRES_CONFIG_DEL_DIA: frozenset = frozenset({
    "ESCALA_POSICION", "ESCALA_NO_VERIFICADA", "ROTACION_MARCO_RAD",
    "TRASLACION_X_M", "TRASLACION_Y_M", "MARCO_NO_VERIFICADO",
    "OFFSET_HEADING_RAD", "HEADING_NO_VERIFICADO", "MAPEO_NO_VERIFICADO",
    "OFFSETS_RUMBO_POR_ROBOT", "OFFSETS_RUMBO_MEDIDOS", "ORIGEN_OFFSET_RUMBO",
})
#: Un libro.csv bloqueado (Excel, OneDrive): reintentos con aviso.
REINTENTOS_ESCRITURA: int = 60
ESPERA_REINTENTO_S: float = 0.5

COLUMNAS_LIBRO: Tuple[str, ...] = (
    "tipo", "fecha", "id_sesion", "intento", "semilla", "estado", "valido",
    "incluida", "motivo_inclusion", "valido_demo", "frenos",
    "d_min_obst_medida", "regla_parada", "parada_respuesta", "archivo_tomas",
    "motivo", "detalle", "contacto", "colisiones_015",
)

#: Recorrido: igual que `validez_demo` (decisión 1 de José).
FRACCION_RECORRIDO_MIN: float = 0.5
RECORRIDO_COMANDADO_MIN_M: float = 0.20

#: Criterio de seguridad para cerrar la campaña (decisión de José, 09-10).
UMBRAL_CONTACTO_M: float = 0.15
TOMAS_CON_CONTACTO_PARA_CERRAR: int = 2
PREFIJO_CIERRE_SEGURIDAD: str = "CRITERIO DE SEGURIDAD"


class ErrorCampana(RuntimeError):
    """El libro se niega a seguir (con el motivo)."""


def _ruta_archivo(nombre: str) -> Path:
    if Path(nombre).is_absolute():
        return Path(nombre)
    if nombre.startswith("TESIS/"):
        return _TESIS / nombre[len("TESIS/"):]
    return _CARPETA / nombre


def sha256_archivo(ruta: Path) -> str:
    if not ruta.is_file():
        return "FALTA"
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def huella_sin_calibracion(ruta: Path) -> str:
    """
    sha256 de `config_robotat.py` SIN la configuración del día: el árbol
    sintáctico de las sentencias de módulo, salvo las asignaciones a
    `NOMBRES_CONFIG_DEL_DIA` y los textos sueltos (docstrings). Los
    comentarios no cuentan. Cambiar un offset no la mueve; cambiar la rampa,
    el rpm máximo, el mapeo de agentes o una función, sí.
    """
    import ast
    if not ruta.is_file():
        return "FALTA"
    arbol = ast.parse(ruta.read_bytes().decode("utf-8"))
    partes = []
    for nodo in arbol.body:
        if isinstance(nodo, ast.Expr) and isinstance(nodo.value, ast.Constant):
            continue
        if isinstance(nodo, (ast.Assign, ast.AnnAssign)):
            blancos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
            if all(isinstance(b, ast.Name) and b.id in NOMBRES_CONFIG_DEL_DIA
                   for b in blancos):
                continue
        partes.append(ast.dump(nodo, include_attributes=False))
    return hashlib.sha256("\n".join(partes).encode("utf-8")).hexdigest()


def hash_congelado(nombre: str) -> str:
    """El sha256 de un archivo de la lista; con '#sin_calibracion', la
    huella de `config_robotat.py` sin la configuración del día."""
    if nombre.endswith("#sin_calibracion"):
        return huella_sin_calibracion(_ruta_archivo(nombre.split("#", 1)[0]))
    return sha256_archivo(_ruta_archivo(nombre))


def hashes_congelados(archivos: Optional[Sequence[str]] = None
                      ) -> Dict[str, str]:
    archivos = ARCHIVOS_CONGELADOS if archivos is None else archivos
    return {a: hash_congelado(a) for a in archivos}


def configuracion_del_dia(id_robot_obstaculo: int) -> Dict[str, Any]:
    """Offsets efectivos (agentes y obstáculo) y su origen, el marco y la
    escala del mocap, las banderas de verificación y el sha256 de la
    configuración y la calibración guardada. Se registra; no bloquea. Se
    llama con la calibración YA aplicada (`_preparar_campana`)."""
    import config_robotat as cfg
    robots = [cfg.MAPEO_AGENTES[i].id_robot for i in range(len(cfg.MAPEO_AGENTES))]
    robots.append(int(id_robot_obstaculo))
    return {
        "offsets_deg": {str(r): round(math.degrees(cfg.offset_rumbo_de_robot(r)), 4)
                        for r in robots},
        "offsets_origen": {str(r): cfg.origen_offset_rumbo(r) for r in robots},
        "marco": {k: getattr(cfg, k, None) for k in (
            "ESCALA_POSICION", "ROTACION_MARCO_RAD", "TRASLACION_X_M",
            "TRASLACION_Y_M", "OFFSET_HEADING_RAD")},
        "banderas": {k: getattr(cfg, k, None) for k in (
            "ESCALA_NO_VERIFICADA", "MARCO_NO_VERIFICADO",
            "HEADING_NO_VERIFICADO", "MAPEO_NO_VERIFICADO")},
        "sha256": {a: sha256_archivo(_ruta_archivo(a))
                   for a in ARCHIVOS_CONFIGURACION},
        "simulador": bool(getattr(cfg, "SIMULADOR_ACTIVO", False)),
    }


def contacto_de_toma(res: Dict[str, Any]) -> Tuple[int, str]:
    """
    ¿Hubo contacto MEDIDO en una toma corrida? (< 0.15 m entre centros: con
    el obstáculo, o algún par de agentes). Devuelve (0/1, descripción). Sin
    distancia medida al obstáculo no cuenta como contacto CON EL OBSTÁCULO;
    sus pares de agentes sí cuentan (decisión de José, 2026-10-10).
    """
    partes = []
    try:
        d = float(res.get("d_min_obst_medida"))
    except (TypeError, ValueError):
        d = float("nan")
    if d == d and d < UMBRAL_CONTACTO_M:
        partes.append(f"obstáculo a {d:.3f} m")
    try:
        pares = int(float(res.get("colisiones_015") or 0))
    except (TypeError, ValueError):
        pares = 0
    if pares > 0:
        partes.append(f"{pares} par(es) de agentes < {UMBRAL_CONTACTO_M} m")
    return (1 if partes else 0), "; ".join(partes)


def inclusion_campana(res: Dict[str, Any]) -> Tuple[int, str]:
    """
    ¿La toma entra en la campaña? Válida para la medición Y, si es la L2 y se
    le comandó al obstáculo ≥ 0.20 m, recorrió al menos la mitad. Frenos y
    contactos NO se consultan: son resultados. Devuelve (0/1, motivo).
    """
    if not int(res.get("valido", 0) or 0):
        return 0, f"no válida: {res.get('motivo', '')}"
    if res.get("obst_modo") == "movil":
        med = float(res.get("obst_recorrido_m", 0.0) or 0.0)
        com = float(res.get("obst_recorrido_comandado_m", 0.0) or 0.0)
        if (com >= RECORRIDO_COMANDADO_MIN_M
                and med < FRACCION_RECORRIDO_MIN * com):
            return 0, (f"el obstáculo recorrió {med:.2f} m de {com:.2f} m "
                       f"comandados")
    return 1, ""


def _fecha() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Campana:
    """El libro de una campaña, abierto por UNA sesión (con candado)."""

    def __init__(self, carpeta: Path) -> None:
        self.carpeta = Path(carpeta)
        self.ruta_cabecera = self.carpeta / "campana.json"
        self.ruta_libro = self.carpeta / "libro.csv"
        self.ruta_candado = self.carpeta / "sesion.candado"
        if not self.ruta_cabecera.is_file() or not self.ruta_libro.is_file():
            raise ErrorCampana(f"no existe la campaña en {self.carpeta}")
        self.cabecera: Dict[str, Any] = json.loads(
            self.ruta_cabecera.read_text(encoding="utf-8"))
        self.filas_descartadas: List[str] = []
        # La cabecera también quedó en la fila de creación del libro (que
        # sólo crece): si alguien edita campana.json, se nota.
        creacion = [f for f in self.filas() if f["tipo"] == "creacion"]
        if creacion:
            original = json.loads(creacion[0]["detalle"]).get("cabecera")
            if original is not None and original != self.cabecera:
                raise ErrorCampana("campana.json no coincide con la cabecera "
                                   "guardada en la fila de creación del libro "
                                   "(¿se editó a mano?)")
        self.nombre: str = self.cabecera["nombre"]
        self.meta: int = int(self.cabecera["meta"])
        self.minimo: int = int(self.cabecera["minimo"])
        self.tope: int = int(self.cabecera["tope_intentos"])
        self.id_sesion: Optional[str] = None
        self.hora_fin: Optional[datetime] = None
        self.motivo_fin: str = ""
        self.cierre_por_seguridad: str = ""
        self._abierta = False

    # ── creación y comandos ──────────────────────────────────────────────
    @staticmethod
    def carpeta_de(base: Path, nombre: str) -> Path:
        if not nombre or any(c in nombre for c in '\\/:*?"<>|') or nombre.startswith("."):
            raise ErrorCampana(f"nombre de campaña inválido: {nombre!r}")
        return Path(base) / "campanas" / nombre

    @classmethod
    def crear(cls, base: Path, nombre: str, plataforma: str,
              id_robot_obstaculo: int, id_marcador_obstaculo: int,
              meta: int = META_POR_DEFECTO, minimo: int = MINIMO_POR_DEFECTO,
              tope: int = TOPE_POR_DEFECTO) -> "Campana":
        if plataforma not in ("hw", "simulador"):
            raise ErrorCampana(f"plataforma {plataforma!r}")
        if not 0 < minimo <= meta <= tope <= INTENTO_MAX_FORMULA:
            raise ErrorCampana("debe ser 0 < mínimo ≤ meta ≤ tope ≤ 999")
        carpeta = cls.carpeta_de(base, nombre)
        if carpeta.exists():
            raise ErrorCampana(f"la campaña {nombre!r} ya existe")
        hashes = hashes_congelados()
        faltan = [a for a, h in hashes.items() if h == "FALTA"]
        if faltan:
            raise ErrorCampana("faltan archivos congelados (el plan y el script "
                               "de análisis se congelan ANTES de crear la "
                               "campaña): " + ", ".join(faltan))
        carpeta.mkdir(parents=True)
        cabecera = {
            "nombre": nombre, "creada": _fecha(), "plataforma": plataforma,
            "robot_obstaculo": int(id_robot_obstaculo),
            "marcador_obstaculo": int(id_marcador_obstaculo),
            "meta": int(meta), "minimo": int(minimo), "tope_intentos": int(tope),
            "semilla_base": SEMILLA_BASE, "archivos_congelados": hashes,
        }
        (carpeta / "campana.json").write_bytes(
            json.dumps(cabecera, ensure_ascii=False, indent=1).encode("utf-8"))
        with open(carpeta / "libro.csv", "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh, lineterminator="\n").writerow(COLUMNAS_LIBRO)
        c = cls(carpeta)
        c._agregar({"tipo": "creacion", "detalle": json.dumps(
            {"cabecera": cabecera}, ensure_ascii=False)})
        return c

    def _chequear_sin_candado(self, que: str) -> None:
        if self.ruta_candado.exists():
            previo = self.ruta_candado.read_text(encoding="utf-8", errors="replace")
            raise ErrorCampana(f"no se puede {que} con una sesión abierta "
                               f"({previo.strip()}). Si murió sin cerrarse: "
                               f"--liberar-candado \"motivo\"")

    @classmethod
    def corregir(cls, base: Path, nombre: str, motivo: str) -> List[str]:
        """
        La salida declarada para corregir algo a mitad de campaña: deja en
        el libro el hash nuevo de los archivos congelados, cuáles cambiaron
        y el motivo. Devuelve los archivos que cambiaron. Entre sesiones,
        nunca con una sesión abierta.
        """
        if not motivo or not motivo.strip():
            raise ErrorCampana("la corrección exige un motivo escrito")
        c = cls(cls.carpeta_de(base, nombre))
        c._chequear_no_cerrada()
        c._chequear_sin_candado("corregir la campaña")
        previos = c.hashes_vigentes()
        nuevos = hashes_congelados()
        faltan = [a for a, h in nuevos.items() if h == "FALTA"]
        if faltan:
            raise ErrorCampana("faltan archivos congelados: " + ", ".join(faltan))
        cambiaron = sorted(a for a in nuevos if nuevos[a] != previos.get(a))
        c._agregar({"tipo": "correccion", "motivo": motivo.strip(),
                    "detalle": json.dumps({"cambiaron": cambiaron,
                                           "previos": {a: previos.get(a) for a in cambiaron},
                                           "archivos_congelados": nuevos},
                                          ensure_ascii=False)})
        return cambiaron

    @classmethod
    def cerrar(cls, base: Path, nombre: str, motivo: str) -> None:
        """Cierra la CAMPAÑA (comando aparte, con motivo escrito), nunca con
        una sesión abierta. Antes marca las reservas sin resultado."""
        if not motivo or not motivo.strip():
            raise ErrorCampana("cerrar la campaña exige un motivo escrito")
        if motivo.strip().casefold().startswith(PREFIJO_CIERRE_SEGURIDAD.casefold()):
            raise ErrorCampana(f"el motivo no puede empezar con "
                               f"{PREFIJO_CIERRE_SEGURIDAD!r}: ese cierre lo escribe "
                               f"sólo el libro")
        c = cls(cls.carpeta_de(base, nombre))
        if not c.ruta_candado.exists():
            c._aplicar_criterio_de_seguridad()
        if c.cierre_por_seguridad:
            raise ErrorCampana(f"la campaña ya la cerró el criterio de seguridad: "
                               f"{c.cierre_por_seguridad}")
        c._chequear_no_cerrada()
        c._chequear_sin_candado("cerrar la campaña")
        c._marcar_interrumpidas("al cerrar la campaña")
        c._agregar({"tipo": "cierre_campana", "motivo": motivo.strip(),
                    "detalle": json.dumps(c.estado(), ensure_ascii=False)})

    @classmethod
    def liberar_candado(cls, base: Path, nombre: str, motivo: str) -> bool:
        """Quita el candado de una sesión que murió sin cerrarse (con motivo)
        y marca sus reservas sin resultado. Devuelve si había candado."""
        if not motivo or not motivo.strip():
            raise ErrorCampana("liberar el candado exige un motivo escrito")
        c = cls(cls.carpeta_de(base, nombre))
        if not c.ruta_candado.exists():
            return False
        previo = c.ruta_candado.read_text(encoding="utf-8", errors="replace")
        c.ruta_candado.unlink()
        c._agregar({"tipo": "candado_liberado", "motivo": motivo.strip(),
                    "detalle": previo})
        c._marcar_interrumpidas("al liberar el candado")
        return True

    # ── lectura del libro ────────────────────────────────────────────────
    def filas(self) -> List[Dict[str, str]]:
        """Las filas del libro. Tolera una última línea truncada (corte en
        plena escritura) y descarta, anotándola en `filas_descartadas`,
        toda fila con otra cantidad de campos."""
        texto = self.ruta_libro.read_text(encoding="utf-8")
        if texto and not texto.endswith("\n"):
            texto = texto[: texto.rfind("\n") + 1]
        lector = csv.reader(io.StringIO(texto))
        try:
            cabeza = next(lector)
        except StopIteration:
            return []
        filas, descartadas = [], []
        for campos in lector:
            if len(campos) == len(cabeza):
                filas.append(dict(zip(cabeza, campos)))
            elif campos:
                descartadas.append(",".join(campos)[:200])
        self.filas_descartadas = descartadas
        return filas

    def hashes_vigentes(self) -> Dict[str, str]:
        vig = None
        for f in self.filas():
            if f["tipo"] == "creacion" and vig is None:
                cab = json.loads(f["detalle"]).get("cabecera")
                vig = dict(cab["archivos_congelados"]) if cab else None
            elif f["tipo"] == "correccion":
                vig = json.loads(f["detalle"])["archivos_congelados"]
        return vig if vig is not None else dict(self.cabecera["archivos_congelados"])

    def estado(self) -> Dict[str, Any]:
        filas = self.filas()
        try:
            reservas = [int(f["intento"]) for f in filas if f["tipo"] == "reserva"]
            res = [f for f in filas if f["tipo"] == "resultado"]
            corridas = [f for f in res if f["estado"] == "corrida"]
            return {
                "intentos_usados": max(reservas) if reservas else 0,
                "incluidas": sum(1 for f in res if f["incluida"] == "1"),
                "corridas": len(corridas),
                "frenos_ultima_corrida": (int(float(corridas[-1]["frenos"] or 0))
                                          if corridas else 0),
                "cerrada": any(f["tipo"] == "cierre_campana" for f in filas),
                "tomas_con_contacto": sum(1 for f in corridas
                                          if f.get("contacto") == "1"),
                "filas_descartadas": len(self.filas_descartadas),
            }
        except (ValueError, KeyError) as exc:
            raise ErrorCampana(f"el libro tiene una fila ilegible: {exc}") from exc

    def semilla(self, intento: int) -> int:
        if not 1 <= intento <= INTENTO_MAX_FORMULA:
            raise ErrorCampana(f"intento {intento} fuera de la fórmula")
        return int(self.cabecera.get("semilla_base", SEMILLA_BASE)) + int(intento) - 1

    # ── validaciones ─────────────────────────────────────────────────────
    def _chequear_no_cerrada(self) -> None:
        if self.estado()["cerrada"]:
            raise ErrorCampana(f"la campaña {self.nombre!r} está CERRADA")

    def _chequear_libro(self) -> None:
        conflictos = [p.name for p in self.carpeta.iterdir()
                      if p.is_file() and p.name not in (
                          "campana.json", "libro.csv", "sesion.candado")
                      and (p.name.startswith("libro") or p.name.startswith("campana"))]
        if conflictos:
            raise ErrorCampana("hay copias en conflicto del libro (¿OneDrive?): "
                               + ", ".join(conflictos) + " — resolverlas a mano")
        vistos: Dict[int, int] = {}
        try:
            for f in self.filas():
                if f["tipo"] != "reserva":
                    continue
                k, s = int(f["intento"]), int(f["semilla"])
                if k in vistos:
                    raise ErrorCampana(f"intento {k} reservado dos veces")
                if s != self.semilla(k):
                    raise ErrorCampana(f"semilla {s} del intento {k} fuera de la "
                                       f"fórmula ({self.semilla(k)})")
                vistos[k] = s
        except ValueError as exc:
            raise ErrorCampana(f"el libro tiene una reserva ilegible: {exc}") from exc
        if len(set(vistos.values())) != len(vistos):
            raise ErrorCampana("semillas repetidas en el libro")

    def _chequear_hashes(self) -> None:
        vig = self.hashes_vigentes()
        ahora = hashes_congelados(tuple(vig))
        distintos = sorted(a for a in vig if ahora.get(a) != vig[a])
        if distintos:
            raise ErrorCampana(
                "cambiaron archivos congelados desde la última corrección: "
                + ", ".join(distintos) + ". Si el cambio es intencional, "
                "declararlo con --corregir-campana \"motivo\" (deja el hash "
                "nuevo en el libro).")

    def _candado_propio(self) -> bool:
        try:
            texto = self.ruta_candado.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        return texto.startswith(f"{self.id_sesion} ")

    def _chequear_candado_propio(self) -> None:
        if not self._candado_propio():
            raise ErrorCampana("el candado del libro ya no es de esta sesión "
                               "(¿--liberar-candado con la sesión viva?): no "
                               "se anota nada más")

    # ── sesión ───────────────────────────────────────────────────────────
    def abrir_sesion(self, plataforma: str, id_robot_obstaculo: int,
                     hora_fin: datetime, id_sesion: str,
                     l0: Optional[Dict[str, Any]] = None,
                     script: Optional[Path] = None) -> None:
        """Valida todo, toma el candado y anota la apertura (con la
        configuración del día, que no bloquea). Si algo falla después de
        tomar el candado, lo suelta. Antes aplica el criterio de seguridad
        (por si un corte quedó entre la 2.ª toma con contacto y su cierre)."""
        if not self.ruta_candado.exists():
            self._aplicar_criterio_de_seguridad()
        if self.cierre_por_seguridad:
            raise ErrorCampana(f"la campaña está CERRADA por el criterio de "
                               f"seguridad: {self.cierre_por_seguridad}")
        self._chequear_no_cerrada()
        self._chequear_libro()
        if plataforma != self.cabecera["plataforma"]:
            raise ErrorCampana(f"la campaña es de plataforma "
                               f"{self.cabecera['plataforma']!r}, no {plataforma!r}")
        if int(id_robot_obstaculo) != int(self.cabecera["robot_obstaculo"]):
            raise ErrorCampana(f"la campaña es con el robot "
                               f"{self.cabecera['robot_obstaculo']} de obstáculo")
        if plataforma == "hw":
            # El congelamiento mira los archivos en disco; esto, el script que
            # CORRE: un respaldo viejo de la demo no abre una sesión de
            # hardware (auditoría final, 10-10).
            if script is None:
                raise ErrorCampana("una sesión de hardware tiene que declarar el script "
                                   "que la corre (¿un respaldo viejo de la demo?)")
            vig = self.hashes_vigentes().get("demo_obstaculo_movil.py")
            if vig is not None and sha256_archivo(Path(script)) != vig:
                raise ErrorCampana(f"{Path(script).name} no es la demo congelada (sha256 "
                                   f"distinto): ¿un respaldo?")
        if hora_fin <= datetime.now():
            raise ErrorCampana(f"la hora de fin {hora_fin:%H:%M} ya pasó")
        self._chequear_hashes()
        try:
            fd = os.open(self.ruta_candado, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            previo = self.ruta_candado.read_text(encoding="utf-8", errors="replace")
            raise ErrorCampana(
                f"otra sesión tiene abierto el libro ({previo.strip()}). Si "
                f"murió sin cerrarse: --liberar-candado \"motivo\"") from None
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(f"{id_sesion} pid {os.getpid()} desde {_fecha()}\n")
            self.id_sesion = id_sesion
            self.hora_fin = hora_fin
            self._abierta = True
            self._marcar_interrumpidas("al abrir la sesión")
            est = self.estado()
            self._agregar({"tipo": "apertura", "id_sesion": id_sesion,
                           "motivo": f"hora de fin {hora_fin:%Y-%m-%d %H:%M}",
                           "detalle": json.dumps({
                               "estado": est, "l0": l0 or {},
                               "configuracion": configuracion_del_dia(id_robot_obstaculo)},
                               ensure_ascii=False, default=str)})
        except BaseException as exc:
            self._abierta = False
            try:
                self.ruta_candado.unlink()
            except OSError:
                pass
            if isinstance(exc, (ErrorCampana, KeyboardInterrupt)):
                raise
            raise ErrorCampana(f"no se pudo abrir la sesión: {exc}") from exc

    def cerrar_sesion(self, motivo: str) -> None:
        if not self._abierta:
            return
        self._abierta = False
        propio = self._candado_propio()
        if propio:
            self._marcar_interrumpidas("al cerrar la sesión")
        self._agregar({"tipo": "cierre_sesion", "id_sesion": self.id_sesion,
                       "motivo": motivo if propio else
                       f"{motivo} (el candado ya no era de esta sesión: no se borró)",
                       "detalle": json.dumps(self.estado(), ensure_ascii=False)})
        if propio:
            try:
                self.ruta_candado.unlink()
            except OSError:
                pass

    def _marcar_interrumpidas(self, cuando: str) -> None:
        filas = self.filas()
        con_resultado = {f["intento"] for f in filas if f["tipo"] == "resultado"}
        for f in filas:
            if f["tipo"] == "reserva" and f["intento"] not in con_resultado:
                self._agregar({"tipo": "resultado", "id_sesion": f["id_sesion"],
                               "intento": f["intento"], "semilla": f["semilla"],
                               "estado": "interrumpida", "incluida": "0",
                               "motivo_inclusion": "reserva sin resultado",
                               "motivo": f"marcada {cuando}"})

    def plan_de_intentos(self) -> Iterator[Tuple[int, int]]:
        """
        (intento, semilla) mientras la campaña siga: abierta, menos incluidas
        que la meta, menos intentos que el tope y antes de la hora de fin.
        Cada uno se RESERVA en el libro antes de entregarlo.
        """
        while True:
            est = self.estado()
            if est["cerrada"]:
                self.motivo_fin = ("CAMPAÑA CERRADA POR EL CRITERIO DE SEGURIDAD"
                                   if self.cierre_por_seguridad else "CAMPAÑA CERRADA")
                return
            if est["incluidas"] >= self.meta:
                self.motivo_fin = f"META: {est['incluidas']} incluidas"
                return
            if est["intentos_usados"] >= self.tope:
                self.motivo_fin = f"TOPE de {self.tope} intentos"
                return
            if self.hora_fin is not None and datetime.now() >= self.hora_fin:
                self.motivo_fin = f"HORA DE FIN {self.hora_fin:%H:%M}"
                return
            self._chequear_candado_propio()
            k = est["intentos_usados"] + 1
            s = self.semilla(k)
            self._agregar({"tipo": "reserva", "id_sesion": self.id_sesion,
                           "intento": k, "semilla": s, "estado": "reservada"})
            yield k, s

    def registrar(self, intento: int, semilla: int, res: Dict[str, Any],
                  archivo_tomas: str) -> None:
        self._chequear_candado_propio()
        if any(f["tipo"] == "resultado" and f["intento"] == str(intento)
               for f in self.filas()):
            raise ErrorCampana(f"el intento {intento} ya tiene resultado en el libro")
        corrio = res.get("decisiones") not in (None, "")
        contacto, que_contacto = contacto_de_toma(res) if corrio else (0, "")
        if corrio:
            estado = "corrida"
        elif str(res.get("motivo", "")).startswith("colocación:"):
            estado = "parada_colocacion"
        else:
            estado = "sin_correr"
        self._agregar({
            "tipo": "resultado", "id_sesion": self.id_sesion, "intento": intento,
            "semilla": semilla, "estado": estado,
            "valido": res.get("valido", 0), "incluida": res.get("incluida", 0),
            "motivo_inclusion": res.get("motivo_inclusion", ""),
            "valido_demo": res.get("valido_demo", 0),
            "frenos": res.get("frenos", 0) if corrio else "",
            "d_min_obst_medida": res.get("d_min_obst_medida", ""),
            "regla_parada": res.get("regla_parada", ""),
            "parada_respuesta": res.get("parada_respuesta", ""),
            "archivo_tomas": archivo_tomas,
            "motivo": str(res.get("motivo", ""))[:300],
            "contacto": contacto if corrio else "",
            "colisiones_015": res.get("colisiones_015", "") if corrio else "",
            "detalle": que_contacto})
        self._aplicar_criterio_de_seguridad()

    def _aplicar_criterio_de_seguridad(self) -> None:
        """Dos tomas corridas con contacto en toda la campaña: el libro
        escribe el cierre (decisión de José, 09-10), con los intentos."""
        filas = self.filas()
        if any(f["tipo"] == "cierre_campana" for f in filas):
            return
        con_contacto = [f for f in filas if f["tipo"] == "resultado"
                        and f["estado"] == "corrida" and f.get("contacto") == "1"]
        if len(con_contacto) < TOMAS_CON_CONTACTO_PARA_CERRAR:
            return
        intentos = [int(f["intento"]) for f in con_contacto]
        motivo = (f"{PREFIJO_CIERRE_SEGURIDAD}: {len(con_contacto)} tomas corridas "
                  f"con contacto (< {UMBRAL_CONTACTO_M} m) — intentos "
                  + ", ".join(str(k) for k in intentos))
        self._agregar({"tipo": "cierre_campana", "id_sesion": self.id_sesion,
                       "motivo": motivo,
                       "detalle": json.dumps({
                           "criterio": "dos tomas corridas con contacto medido "
                                       "(obstáculo o entre agentes), José 2026-10-09",
                           "contactos": [{"intento": int(f["intento"]),
                                          "que": f.get("detalle", "")}
                                         for f in con_contacto],
                           "estado": self.estado()}, ensure_ascii=False)})
        self.cierre_por_seguridad = motivo

    def anotar_respuesta_pausa(self, intento: int, respuesta: str) -> None:
        """La respuesta del operador a la pausa de seguridad, en una fila
        aparte: el resultado de la toma ya se anotó ANTES de preguntar (así
        el criterio la cuenta aunque el proceso muera esperando)."""
        self._chequear_candado_propio()
        self._agregar({"tipo": "pausa", "id_sesion": self.id_sesion,
                       "intento": intento, "parada_respuesta": respuesta})

    def veredicto(self) -> str:
        est = self.estado()
        if est["incluidas"] >= self.meta:
            return "META"
        if est["incluidas"] >= self.minimo:
            return "MÍNIMO"
        return "INCOMPLETA"

    # ── escritura ────────────────────────────────────────────────────────
    def _agregar(self, fila: Dict[str, Any]) -> None:
        """
        Agrega UNA fila (con flush y fsync). Si la última línea quedó
        truncada por un corte, primero la cierra con un fin de línea, para
        que la fila nueva no se le pegue (`filas()` descarta el fragmento).
        Si el archivo está bloqueado (Excel, OneDrive), reintenta con aviso.
        """
        completa = {c: "" for c in COLUMNAS_LIBRO}
        completa["fecha"] = _fecha()
        completa.update({k: ("" if v is None else v) for k, v in fila.items()})
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerow(
            [completa[c] for c in COLUMNAS_LIBRO])
        datos = buf.getvalue().encode("utf-8")
        with open(self.ruta_libro, "r", encoding="utf-8", newline="") as fh:
            cabeza = next(csv.reader(fh), [])
        if tuple(cabeza) != COLUMNAS_LIBRO:
            raise ErrorCampana("el libro tiene otro formato de columnas (de una "
                               "versión anterior): no se escribe en él")
        avisado = False
        for intento in range(REINTENTOS_ESCRITURA):
            try:
                with open(self.ruta_libro, "rb") as fh:
                    fh.seek(0, os.SEEK_END)
                    if fh.tell() > 0:
                        fh.seek(-1, os.SEEK_END)
                        truncada = fh.read(1) != b"\n"
                    else:
                        truncada = False
                with open(self.ruta_libro, "ab") as fh:
                    fh.write((b"\n" if truncada else b"") + datos)
                    fh.flush()
                    os.fsync(fh.fileno())
                return
            except PermissionError:
                if intento == REINTENTOS_ESCRITURA - 1:
                    raise
                if not avisado:
                    print(f"⚠ [campaña] {self.ruta_libro.name} está bloqueado "
                          f"(¿abierto en Excel?): cerralo; reintento "
                          f"{REINTENTOS_ESCRITURA * ESPERA_REINTENTO_S:.0f} s…")
                    avisado = True
                time.sleep(ESPERA_REINTENTO_S)
