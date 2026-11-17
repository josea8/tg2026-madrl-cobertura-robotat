"""
calibracion_sesion.py
=====================
Almacén de lo que se MIDE en el laboratorio, para que ninguna sesión repita
el trabajo de la anterior ni haya que reingresar un número a mano.

Cómo se relaciona con `config_robotat.py`
-----------------------------------------
`config_robotat` tiene los valores POR DEFECTO, todos marcados
`NO_VERIFICADO`. Este módulo guarda los valores MEDIDOS en un JSON y los
aplica sobre `config_robotat` al arrancar cada sesión, apagando las marcas de
"no verificado" de lo que ya se midió.

Separarlos importa: el archivo de configuración es código versionado y
legible; el archivo de medición es un artefacto de laboratorio con fecha,
que se puede borrar y rehacer sin tocar el repositorio.

Nunca se pierde una medición
----------------------------
`guardar` fusiona con lo que ya había y, antes de escribir, respalda el
archivo previo con sufijo de fecha y hora. Una calibración es media hora de
laboratorio con cinco personas esperando; no se sobrescribe en silencio.

⚠ CAMPOS FRÁGILES — NO válidos entre sesiones distintas
---------------------------------------------------------
Hallazgo de laboratorio (2026-08-21/22). Primera versión: se trató
`id_marcador` como frágil, asumiendo que CUALQUIER marcador se mueve a
mano. El operador corrigió eso — hay DOS tipos de marcador:

- **Marcadores SUELTOS** (el de meta, por ejemplo): se colocan a mano y NO
  conservan su posición. Éstos sí son efímeros.
- **Marcadores MONTADOS EN EL CHASIS** de cada robot: son fijos y
  permanentes — robot N trae siempre el marcador N (confirmado para
  robots 1–16; ver `config_robotat.marcador_fijo_de_robot`). Por eso
  `id_marcador` YA NO está en `CAMPOS_FRAGILES`: es un hecho de ingeniería
  conocido, no una medición que caduque. `verificar_mapeo_ids.py` / la
  etapa 1 de `sesion_robotat.py` siguen disponibles como chequeo de
  seguridad opcional, ya no como paso obligatorio.

`offset_heading_rad` SÍ sigue en `CAMPOS_FRAGILES`, con una salvedad
declarada: si la constelación está tan permanentemente montada como el
propio ID de marcador, es razonable esperar que la orientación de montaje
—y por lo tanto el offset— también sea estable. Pero eso es una inferencia
mía, no algo que el operador haya confirmado explícitamente todavía, así
que por ahora se mantiene el criterio conservador (remedir cada sesión) en
vez de asumirlo. Revisar si esto se confirma.

Escala y marco del laboratorio NUNCA estuvieron en este conjunto: dependen
del sistema de captura, que calibran los técnicos, no de dónde está pegado
un marcador.

Por eso los campos de acá llevan fecha de medición y `aplicar_a_config()`
se niega a confiar en ellos si no son de HOY: usa la fecha calendario como
proxy simple de "misma sesión física de laboratorio" — imperfecto (dos
sesiones el mismo día, o una que cruza medianoche), pero más seguro que
confiar indefinidamente. Si sospechás que un marcador SUELTO se movió
dentro del mismo día, alcanza con volver a correr la etapa que lo mide: al
remedir, la fecha se actualiza sola.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import json
import math
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import config_robotat as cfg

RUTA_CALIBRACION: Path = Path(__file__).resolve().parent / "calibracion_medida.json"

#: campo → (etapa que lo mide, atributo de config_robotat que sobreescribe)
CAMPOS: Dict[str, Tuple[str, Optional[str]]] = {
    "id_robot":              ("etapa 0", None),
    "id_marcador":           ("etapa 1", None),
    # Robot contra el que se MIDIÓ `id_marcador`. Existe porque `id_robot`
    # lo pisa la etapa 0 en cada corrida, así que no sirve para saber a qué
    # robot pertenece el `id_marcador` guardado: tras correr etapa 0 con el
    # robot 1, un `id_marcador` medido ayer con el robot 2 "coincidía" con
    # `id_robot=1` y se combinaban como si fueran el mismo robot. Este campo
    # sólo lo escribe la etapa 1, junto al `id_marcador` que le corresponde.
    "id_marcador_para_robot": ("etapa 1", None),
    "escala_posicion":       ("etapa 2", "ESCALA_POSICION"),
    "rotacion_marco_rad":    ("etapa 2", "ROTACION_MARCO_RAD"),
    "traslacion_x_m":        ("etapa 2", "TRASLACION_X_M"),
    "traslacion_y_m":        ("etapa 2", "TRASLACION_Y_M"),
    "offset_heading_rad":    ("etapa 3", "OFFSET_HEADING_RAD"),
}

#: Campos que pueden quedar desactualizados de una sesión a otra.
#:
#: Está VACÍO, y eso es una decisión, no un olvido. Los dos candidatos
#: quedaron descartados con información del laboratorio:
#:
#:   `id_marcador` — la correspondencia robot↔chasis es fija (ver
#:     `config_robotat.marcador_fijo_de_robot`).
#:
#:   `offset_heading_rad` — se mantuvo por precaución hasta el 2026-09-01,
#:     cuando el operador confirmó que las constelaciones están PREGRABADAS
#:     en Motive: la forma y el ID de cada una están definidos de antemano,
#:     así que la orientación del cuerpo rígido no cambia entre sesiones.
#:     Lo respalda que el propio laboratorio mantenga una tabla persistente
#:     de offsets por robot (`marker_offsets` en `laboratorio11.m`) y la
#:     reutilice: si cambiaran, esa tabla no serviría.
#:
#: Riesgo residual asumido: si alguna vez se desarma y rehace una
#: constelación, el offset guardado queda mal sin que nada avise. Se nota a
#: ojo —el robot avanza sistemáticamente torcido respecto de su rumbo
#: reportado— y la etapa 3 lo remide en 10 minutos.
#:
#: La maquinaria de campos frágiles se deja en pie: si aparece un parámetro
#: que sí caduque entre sesiones, basta con agregarlo acá.
CAMPOS_FRAGILES: Set[str] = set()

#: campos sin los que una sesión de política/enjambre no debe correr
REQUERIDOS_PARA_POLITICA: List[str] = [
    "id_robot", "id_marcador", "escala_posicion",
    "rotacion_marco_rad", "traslacion_x_m", "traslacion_y_m",
    "offset_heading_rad",
]

#: banderas de `config_robotat` que se apagan cuando su campo está medido
BANDERAS: Dict[str, List[str]] = {
    "ESCALA_NO_VERIFICADA":    ["escala_posicion"],
    "MARCO_NO_VERIFICADO":     ["rotacion_marco_rad", "traslacion_x_m",
                                "traslacion_y_m"],
    "HEADING_NO_VERIFICADO":   ["offset_heading_rad"],
    "MAPEO_NO_VERIFICADO":     ["id_marcador"],
}


def cargar() -> Dict[str, Any]:
    """Lee el JSON de mediciones. Devuelve {} si todavía no existe."""
    if not RUTA_CALIBRACION.is_file():
        return {}
    try:
        return json.loads(RUTA_CALIBRACION.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        print(f"[calib] no se pudo leer {RUTA_CALIBRACION.name}: {exc}")
        return {}


def guardar(nuevos: Dict[str, Any], etapa: Optional[str] = None) -> None:
    """
    Fusiona `nuevos` con lo ya medido y escribe, respaldando lo anterior.

    Nunca borra un campo que ya existía y no viene en `nuevos`. Cada campo
    PÚBLICO (no interno, no `_etapas`/`_historial`/`_medido_en`) que se
    guarda queda sellado con la fecha y hora de esta llamada en
    `_medido_en`, que es lo que permite detectar campos frágiles
    desactualizados (ver nota de módulo).
    """
    datos = cargar()
    if RUTA_CALIBRACION.is_file():
        sello = datetime.now().strftime("%Y%m%d_%H%M%S")
        respaldo = RUTA_CALIBRACION.with_name(
            f"{RUTA_CALIBRACION.stem}_prev_{sello}.json"
        )
        shutil.copy2(RUTA_CALIBRACION, respaldo)

    ahora_iso = datetime.now().isoformat(timespec="seconds")
    publicos = sorted(k for k in nuevos if not k.startswith("_"))

    datos.update(nuevos)
    medido_en = datos.setdefault("_medido_en", {})
    for campo in publicos:
        medido_en[campo] = ahora_iso

    historial = datos.setdefault("_historial", [])
    historial.append({
        "cuando": ahora_iso,
        "etapa":  etapa or "?",
        "campos": publicos,
    })
    RUTA_CALIBRACION.write_text(
        json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if publicos:      # los campos internos (_etapas) no se anuncian
        print(f"[calib] guardado en {RUTA_CALIBRACION.name}: {publicos}")


def fecha_medicion(campo: str) -> Optional[date]:
    """
    Fecha (calendario, hora local) en que se midió `campo`, o None.

    Primero busca en `_medido_en` (lo que graba `guardar()` desde que existe
    este mecanismo). Si falta, cae a la entrada más reciente de
    `_historial` que haya guardado ese campo — necesario para archivos de
    calibración escritos por una versión anterior del código, como el de
    la primera sesión real de laboratorio: `id_marcador` ya estaba medido
    CORRECTAMENTE ese mismo día cuando se agregó este chequeo, y sin este
    resguardo se hubiera visto como "de sesión anterior" y bloqueado al
    operador en medio de su propia sesión, por una migración de formato y
    no por un dato viejo de verdad.
    """
    datos = cargar()
    iso = datos.get("_medido_en", {}).get(campo)
    if iso is None:
        for entrada in reversed(datos.get("_historial", [])):
            if campo in entrada.get("campos", []):
                iso = entrada.get("cuando")
                break
    if iso is None:
        return None
    try:
        return datetime.fromisoformat(iso).date()
    except ValueError:
        return None


def campos_fragiles_desactualizados() -> List[str]:
    """
    Campos de `CAMPOS_FRAGILES` presentes en la calibración pero medidos en
    una fecha distinta de hoy — es decir, de una sesión física anterior, en
    la que los marcadores pueden haberse movido desde entonces.

    Usa la fecha calendario como proxy de "sesión física", documentado
    en la nota de módulo como heurística deliberadamente conservadora.
    """
    datos = cargar()
    hoy = datetime.now().date()
    desactualizados = []
    for campo in sorted(CAMPOS_FRAGILES):
        if campo not in datos:
            continue
        fecha = fecha_medicion(campo)
        if fecha is None or fecha != hoy:
            desactualizados.append(campo)
    return desactualizados


def registrar_etapa(etapa: int, veredicto: str, detalle: str = "") -> None:
    """Anota el veredicto de una etapa, para el control de secuencia."""
    datos = cargar()
    estados = datos.setdefault("_etapas", {})
    estados[str(etapa)] = {
        "veredicto": veredicto,
        "cuando":    datetime.now().isoformat(timespec="seconds"),
        "detalle":   detalle,
    }
    guardar({"_etapas": estados}, etapa=f"etapa {etapa}")


def veredicto_etapa(etapa: int) -> Optional[str]:
    """Veredicto registrado de una etapa, o None si nunca corrió."""
    est = cargar().get("_etapas", {}).get(str(etapa))
    return est["veredicto"] if est else None


def aplicar_a_config() -> List[str]:
    """
    Vuelca las mediciones sobre `config_robotat` y apaga las banderas de
    "no verificado" correspondientes.

    Los campos de `CAMPOS_FRAGILES` desactualizados (medidos en una fecha
    distinta de hoy) NO se aplican: quedan en el default de
    `config_robotat`, con su bandera `*_NO_VERIFICADO` intacta, para que el
    resto del sistema (`lanzar_robotat.chequeos_previos`, el chequeo de
    arranque) los trate como lo que son — sin verificar todavía en esta
    sesión— en vez de confiar en un mapeo de marcador que puede pertenecer
    a otro robot ahora.

    Retorna
    -------
    Lista de campos aplicados, para poder informarlos.
    """
    datos = cargar()
    desactualizados = set(campos_fragiles_desactualizados())
    if desactualizados:
        print(f"[calib] ⚠ SIN APLICAR (de una sesión anterior, los "
              f"marcadores pueden haberse movido): {sorted(desactualizados)}")
        print(f"[calib]   Volvé a correr la(s) etapa(s) que los miden.")

    aplicados: List[str] = []
    for campo, (_etapa, atributo) in CAMPOS.items():
        if atributo is None or campo not in datos or campo in desactualizados:
            continue
        setattr(cfg, atributo, datos[campo])
        aplicados.append(campo)

    for bandera, requiere in BANDERAS.items():
        # MAPEO_NO_VERIFICADO se decide más abajo, NO por mera presencia de
        # `id_marcador`. Ahí está el origen del `[verificado]` mentiroso que
        # apareció en el laboratorio (2026-08-25): el mapeo se mostraba como
        # verificado porque el campo EXISTÍA, aunque se hubiera medido para
        # otro robot y terminara descartado. Una bandera de "verificado" que
        # sólo mira si hay un dato, y no si el dato aplica, no verifica nada.
        if bandera == "MAPEO_NO_VERIFICADO":
            continue
        if all(c in datos and c not in desactualizados for c in requiere):
            setattr(cfg, bandera, False)

    # El mapeo medido reemplaza al del archivo para el agente 0, que es el
    # que usan las sesiones de un robot.
    if "id_robot" in datos:
        id_robot = int(datos["id_robot"])

        # ⚠ HALLAZGO (2026-08-25): `id_robot` e `id_marcador` se guardan
        # como campos INDEPENDIENTES, medidos por etapas distintas (0 y 1)
        # en momentos distintos. Si entre una corrida y otra cambia el
        # robot usado, el archivo termina con `id_robot` de una corrida e
        # `id_marcador` de OTRA — dos robots físicos distintos combinados
        # como si fueran uno. Pasó en el laboratorio: id_robot=1 (de hoy),
        # id_marcador=2 (medido para el robot 2, ayer). Por eso
        # `datos["id_marcador"]` sólo se confía si quedó medido para ESTE
        # MISMO id_robot (o si está desactualizado, cae al mismo camino).
        # OJO: comparar contra `datos["id_robot"]` sería una tautología —
        # `id_robot` SALE de ahí. El único dato que ata el `id_marcador`
        # guardado a un robot concreto es `id_marcador_para_robot`, que
        # escribe la etapa 1 y nadie más pisa. Si falta (archivo viejo),
        # no se puede saber para qué robot se midió: se descarta.
        id_marcador_coincide = (
            "id_marcador" in datos and "id_marcador" not in desactualizados
            and datos.get("id_marcador_para_robot") == id_robot
        )
        if id_marcador_coincide:
            id_marcador = int(datos["id_marcador"])
        else:
            if "id_marcador" in datos and not id_marcador_coincide:
                print(f"[calib] ⚠ id_marcador guardado "
                      f"({datos['id_marcador']}) se midió para otro robot "
                      f"— se descarta, se usa la correspondencia fija de "
                      f"la plataforma para el robot {id_robot}.")
            try:
                id_marcador = cfg.marcador_fijo_de_robot(id_robot)
            except ValueError:
                id_marcador = None   # robot 0 o fuera de 1-16: sin resolver

        if id_marcador is not None:
            cfg.MAPEO_AGENTES = dict(cfg.MAPEO_AGENTES)
            cfg.MAPEO_AGENTES[0] = cfg.AsignacionAgente(
                id_marcador=id_marcador, id_robot=id_robot,
            )
            # `id_marcador` no tiene un atributo simple de config_robotat
            # (va al mapeo, no a un `setattr`), así que el bucle genérico
            # de arriba no lo agrega. Bug preexistente: quedaba aplicado
            # pero nunca reportado en `aplicados`, así que `_preparar()` no
            # lo mencionaba al operador ni una prueba directa podía
            # confirmarlo.
            aplicados.append("id_marcador")

        # El offset de rumbo medido por la etapa 3 pertenece a ESTE robot, no
        # a todos: se vuelca también en el mapa por robot, donde le gana a la
        # tabla del laboratorio. Sin esto, `offset_rumbo_de_robot` devolvería
        # el valor de partida aunque tuviéramos la medición — para el robot 1
        # son 1.63° de diferencia, y el objetivo del mapa es que la medición
        # mande cuando existe.
        if ("offset_heading_rad" in datos
                and "offset_heading_rad" not in desactualizados):
            cfg.OFFSETS_RUMBO_POR_ROBOT = dict(cfg.OFFSETS_RUMBO_POR_ROBOT)
            cfg.OFFSETS_RUMBO_POR_ROBOT[id_robot] = float(
                datos["offset_heading_rad"]
            )
            cfg.OFFSETS_RUMBO_MEDIDOS = set(cfg.OFFSETS_RUMBO_MEDIDOS)
            cfg.OFFSETS_RUMBO_MEDIDOS.add(id_robot)

        # Sólo hay mapeo VERIFICADO si la etapa 1 lo midió para ESTE robot.
        # Caer a la correspondencia fija de la plataforma es un default
        # razonable, no una verificación: la bandera se queda en True y la
        # etapa 1 sigue siendo obligatoria.
        if id_marcador_coincide:
            cfg.MAPEO_NO_VERIFICADO = False
    return aplicados


def faltantes(requeridos: Optional[List[str]] = None) -> List[str]:
    """
    Campos requeridos que todavía no se midieron HOY, con su etapa.

    Un campo frágil (ver `CAMPOS_FRAGILES`) medido en una sesión anterior
    cuenta como faltante: no es que el dato nunca se tomó, es que no es
    seguro reusarlo sin volver a medirlo.
    """
    datos = cargar()
    desactualizados = set(campos_fragiles_desactualizados())
    req = requeridos if requeridos is not None else REQUERIDOS_PARA_POLITICA
    salida = []
    for c in req:
        etapa = CAMPOS.get(c, ("?", None))[0]
        if c not in datos:
            salida.append(f"{c} ({etapa})")
        elif c in desactualizados:
            salida.append(f"{c} ({etapa}, ⚠ de una sesión anterior — "
                          f"remedir)")
    return salida


def resumen() -> List[str]:
    """Líneas legibles del estado de la calibración."""
    datos = cargar()
    if not datos:
        return ["  (sin mediciones todavía — corré la sesión 'calibracion')"]
    desactualizados = set(campos_fragiles_desactualizados())
    lineas: List[str] = []
    for campo, (etapa, _atr) in CAMPOS.items():
        if campo in datos:
            v = datos[campo]
            if campo.endswith("_rad"):
                extra = f"  ({math.degrees(float(v)):+.2f}°)"
            else:
                extra = ""
            if campo in desactualizados:
                fecha = fecha_medicion(campo)
                extra += (f"  ⚠ DE UNA SESIÓN ANTERIOR ({fecha}) — los "
                          f"marcadores pueden haberse movido, remedir")
            elif campo in CAMPOS_FRAGILES:
                extra += "  (medido hoy)"
            lineas.append(f"  {campo:22s} = {v}{extra}   [{etapa}]")
        else:
            lineas.append(f"  {campo:22s} = —  ⚠ sin medir   [{etapa}]")
    etapas = datos.get("_etapas", {})
    if etapas:
        estado = "  ".join(
            f"E{k}:{v['veredicto']}" for k, v in sorted(etapas.items())
        )
        lineas.append(f"  etapas corridas: {estado}")
    return lineas
