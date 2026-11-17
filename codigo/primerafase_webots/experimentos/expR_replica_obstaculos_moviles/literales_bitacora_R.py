"""
literales_bitacora_R.py
=======================
ARCHIVO DE LITERALES del Exp R (§4 del prerregistro). Es POSTERIOR a la
corrida (13-11) y se declara como tal: no entró al manifiesto pre. Verifica
la subsección de resultados de la bitácora
(`ENTRADA_BITACORA_expR_resultados.md`), en los dos sentidos:

1. Cada cifra y cada veredicto que cita se recalcula desde los CRUDOS
   (`experimento_R_completo.csv`, sus trazas, el registro y los logs de la
   corrida) con las funciones del núcleo `verificar_cifras_R.py`, y tiene que
   estar en el texto tal cual. Las filas de la tabla de hipótesis se rearman
   completas, con su veredicto, y se comparan como texto.
2. Toda cifra del texto tiene que ser una de las recalculadas o una constante
   declarada en DECLARADAS, con su fuente: diseño fijado en el prerregistro,
   fechas y horas de los registros, eventos de Windows o archivos.
   Ninguna queda sin justificar.

Además corre el núcleo sobre `resumen_R.txt`, que tiene que dar 0 diferencias.

    python -B literales_bitacora_R.py

Termina con 0 si todo coincide y con 1 si no.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

import verificar_cifras_R as VC  # noqa: E402

RUTA_ENTRADA: Path = _CARPETA / "ENTRADA_BITACORA_expR_resultados.md"
LOG_TRAMO_1: Path = VC.DIR_RES / "corrida_R_experimento_20261113_202513.log"
RUTA_REGISTRO: Path = VC.DIR_RES / "registro_R.txt"
RUTA_MANIFIESTO_PRE: Path = VC.DIR_RES / "manifiesto_R_pre_20261113_2021.txt"

#: Cifras del texto que no salen del crudo de la corrida, con su fuente.
DECLARADAS: Dict[str, str] = {
    # Diseño, fijado en el prerregistro.
    "420110": "§1, primera semilla", "420509": "§1, última semilla",
    "400": "§1, n por celda", "0,05": "§2.2, α", "0,10": "§2.1, umbral de H6",
    "0,13": "§2.1, COTA_CENTRO_OBST", "0,075": "radio de contacto, §2.5/§3", "5": "§3.2, W",
    "1": "§3.2, W = 1 (sensibilidad)", "7": "§2.4, familia de Holm", "12": "§1, celdas",
    "44": "§3.4, trazas esperadas", "31": "§3.4, IC de Poisson", "57": "§3.4, IC de Poisson",
    "23": "§2.1, '≥ ~23 %' esperado en la sensibilidad", "100": "§2.1, episodios del exploratorio",
    "66": "columnas de Q del control",
    "1200": "control: episodios vistos (registro del control)",
    # Eventos y archivos fuera del crudo de la corrida.
    "105": "visor de eventos de Windows, Kernel-Power 105 (cambio de fuente)",
    "2.2e-16": "salida de verificar_cifras_R (se recalcula abajo)",
}
DECLARADAS_HORAS: Dict[str, str] = {
    "21:04:13": "visor de eventos de Windows (Kernel-Power 105), 13-11",
    "19:26": "mtime de la bitácora tras la pasada de otra sesión (respaldo preRonda3)",
}

_RE_HORA = re.compile(r"(?<![\d:])\d{2}:\d{2}(?::\d{2})?(?![\d:])")
_RE_CIFRA = re.compile(r"(?<![\w.\-−+/:,\[])[−+\-]?\d+(?:[.,]\d+)?(?:e-\d+)?(?:/\d+)?(?![\w\-/:%]|[.,]\d)")


def fmt_p_tabla(p: float) -> str:
    return "p < 0.0001" if p < 0.0001 else f"p = {p:.4f}"


def literales() -> Tuple[List[Tuple[str, str]], List[str]]:
    """(lista de (qué, texto esperado), diferencias del cálculo)."""
    dif: List[str] = []
    datos, _cols = VC.cargar([VC.RUTA_CSV_R], dif)
    sem = sorted(datos["S1_din"])
    n = len(sem)
    cuenta: Dict = {}
    pb = VC.parte_b_recalculada(datos, "R", VC.DIR_TRAZAS, dif, cuenta)
    L, V, res = VC.lineas_hipotesis(datos, sem, pb, None, "R", True, VC.DIR_TRAZAS)
    lit: List[Tuple[str, str]] = []
    clase = {p[0]: p[5] for p in VC.PRUEBAS}
    for pid, _ev, k, a, b, _c in VC.PRUEBAS:
        ka, kb, bb, cc, p = res[pid]
        lit.append((f"fila {pid}",
                    f"| {pid} | {clase[pid]} | {k}_{a} {ka}/{n}, {k}_{b} {kb}/{n}; "
                    f"b/c = {bb}/{cc}; {fmt_p_tabla(p)} | {V[pid]} |"))
    dk = {k: VC._resta(datos, k, "din", "ctrl", "cobertura_accesible", sem) for k in VC.NIVELES}
    piezas = [VC.ic95([x - y for x, y in zip(dk[k1], dk["S3"])]) for k1 in ("S1", "S2")]
    lit.append(("fila H4", f"| H4 | secundaria | Δ_S1 − Δ_S3 {VC.fmt_delta(*piezas[0], marca=False)}; "
                           f"Δ_S2 − Δ_S3 {VC.fmt_delta(*piezas[1], marca=False)} | {V['H4']} |"))
    cont = [len(VC.con_evento(datos, f"{k}_din", "contacto", sem)) for k in VC.NIVELES]
    if not any(cont):
        lit.append(("fila H5a", f"| H5a | primaria | contacto en Sk_din: 0/{n} en S1, S2 y S3 | "
                                f"{V['H5a']} |"))
    # H6, desde la Parte B recalculada.
    h6 = {}
    for k in VC.NIVELES:
        c = f"{k}_din"
        bajo = [s for s in sem if pb[c][s]["_d_min"] < VC.UMBRAL_H6]
        en_v = sum(int(pb[c][s]["fallback_ventana_d_min_5"]) for s in bajo)
        fuera = sum(pb[c][s]["d_min_fuera_ventana_5"] < VC.UMBRAL_H6 for s in sem)
        h6[k] = (len(bajo), en_v, fuera, bajo)
    m3, k3, _f, bajo3 = h6["S3"]
    lit.append(("fila H6a-S3", f"| H6a-S3 | secundaria | {k3} de {m3} episodios bajo 0,10 m con el "
                               f"mínimo en la ventana | {V['H6a-S3']} |"))
    if h6["S1"][0] == h6["S2"][0] == 0:
        lit.append(("fila H6a-S1/S2", "| H6a-S1, H6a-S2 | secundaria | ningún episodio bajo 0,10 m | "
                                      f"{V['H6a-S1']} |"))
    if all(h6[k][2] == 0 for k in VC.NIVELES):
        lit.append(("fila H6b", f"| H6b-S1, H6b-S2, H6b-S3 | secundaria | 0/{n} bajo 0,10 m fuera de "
                                f"la ventana en cada nivel | {V['H6b-S3']} |"))
    # Holm.
    ids = [p[0] for p in VC.PRUEBAS]
    aj = dict(zip(ids, VC.holm([res[i][4] for i in ids])))
    sost = [i for i in ids if V[i] == "sostenida"]
    holm_txt = ", ".join(f"{i} {VC.fmt_p(aj[i])}" for i in sost)
    lit.append(("Holm", f"(p Holm: {holm_txt})"))
    lit.append(("Holm, cuántas", {4: "cuatro"}.get(len(sost), str(len(sost)))
                + " pruebas con p sostenidas siguen bajo 0,05"))
    # Lectura.
    s3q = len(VC.con_evento(datos, "S3_quieto", "fallback", sem))
    quietos = [len(VC.con_evento(datos, f"{k}_quieto", "fallback", sem)) for k in VC.NIVELES]
    if not any(quietos):
        lit.append(("necesidad", f"(0/{n} en S1, S2 y S3)"))
    lit.append(("H1-S2 conteo", f"En S2 hubo {res['H1-S2'][0]} fallbacks contra {res['H1-S2'][1]}"))
    lit.append(("H2-S3 conteos", f"sin él, {res['H2-S3'][0]} de {n} episodios bajan de 0,13 m; con él, "
                                 f"{res['H2-S3'][1]}."))
    dif_ag = [float(VC.tiene(datos["S3_din"][s], "agotado")) - float(VC.tiene(datos["S3_quieto"][s],
              "agotado")) for s in sem]
    lit.append(("H3b Δ", f"Δ de tasas {VC.fmt_delta(*VC.ic95(dif_ag), marca=False)}"))
    lit.append(("H4 Δ_k", "Δ din − ctrl: " + ", ".join(
        f"{k} {VC.fmt_delta(*VC.ic95(dk[k]))[:11]}" for k in VC.NIVELES) + "."))
    lit.append(("cota H5a", f"por debajo de {VC.clopper_pearson(0, n)[1]:.4f} en cada nivel"))
    din_total = sum(len(datos[f"{k}_din"]) for k in VC.NIVELES)
    lit.append(("din total", f"en los {din_total} episodios"))
    dentro = [s for s in bajo3 if int(pb["S3_din"][s]["fallback_en_d_min"])]
    rachas = sorted(int(pb["S3_din"][s]["racha_fallback_d_min"]) for s in dentro)
    lit.append(("acercamientos", f"Los {m3} de S3_din caen en la ventana"))
    lit.append(("dentro/después", f"En {len(dentro)} el mínimo está dentro del fallback, con rachas de "
                                  f"{rachas[0]} a {rachas[-1]} decisiones, y en {m3 - len(dentro)} "
                                  f"justo después"))
    s_min = min(bajo3, key=lambda s: pb["S3_din"][s]["_d_min"])
    d_min = pb["S3_din"][s_min]["_d_min"]
    mm = f"{(d_min - 0.075) * 1000:.1f}".replace(".", ",")
    lit.append(("más profundo", f"S3_din {s_min}: {d_min:.4f} m, a {mm} mm del contacto"))
    lit.append(("racha del más profundo", f"dentro de un fallback de "
                f"{int(pb['S3_din'][s_min]['racha_fallback_d_min'])} decisiones"))
    # H5b: contactos de S3_sinvel, desde sus trazas.
    eps = sorted(VC.con_evento(datos, "S3_sinvel", "contacto", sem))
    tot = en_v = 0
    for s in eps:
        t, e = VC.contactos_de_traza(VC.leer_traza(VC.DIR_TRAZAS / f"R_S3_sinvel_{s}.csv"))
        tot, en_v = tot + t, en_v + e
    lit.append(("H5b episodios", f"Hubo {len(eps)} episodios de S3_sinvel, "
                                 + " y ".join(str(s) for s in eps)))
    lit.append(("H5b agente-pasos", f"con {tot} agente-pasos de contacto en total"))
    lit.append(("H5b en ventana", f"Los {en_v} caen en la ventana de un fallback del propio agente"
                if en_v == tot else f"{en_v} de {tot}"))
    lit.append(("H5b b/c", f"Con b/c = {res['H5b'][2]}/{res['H5b'][3]}"))
    # Sensibilidad.
    sens = {k: sum(pb[f"{k}_din"][s]["d_min_fuera_ventana_5"] < VC.UMBRAL_COTA for s in sem)
            for k in VC.NIVELES}
    lit.append(("sensibilidad", f"{sens['S3']}/{n} episodios en S3 ({100 * sens['S3'] / n:.0f} %), "
                                f"{sens['S2']}/{n} en S2 y {sens['S1']}/{n} en S1"))
    w1 = sum(pb["S3_din"][s]["d_min_sin_fallback"] < VC.UMBRAL_H6 for s in sem)
    lit.append(("sensibilidad W=1", f"S3 da {w1}/{n}"))
    # Corrida: log del tramo 1, registro y manifiesto.
    log1 = LOG_TRAMO_1.read_text(encoding="utf-8")
    for celda in ("S3_ctrl", "S1_ctrl", "S2_ctrl"):
        m = re.search(rf"{celda}\s+corrida en (\d+\.\d) s", log1)
        lit.append((f"tiempo {celda}", f"{m.group(1)} s" if m else f"(falta {celda} en el log)"))
    m = re.search(r"S3_ctrl\s+energía: enchufada, batería (\d+) %", log1)
    lit.append(("batería S3_ctrl", f"enchufada ({m.group(1)} %)" if m else "(falta)"))
    t_ctrl = VC.columna(datos, "S3_ctrl", "t_episodio_s", sem)
    lit.append(("t/ep S3_ctrl", f"t_episodio_s medio fue {sum(t_ctrl) / len(t_ctrl):.2f} s"))
    ini1 = re.search(r"inicio \d{4}-\d{2}-\d{2} (\d{2}:\d{2}:\d{2})", log1)
    lit.append(("inicio tramo 1", f"Desde las {ini1.group(1)}" if ini1 else "(falta)"))
    reg = RUTA_REGISTRO.read_text(encoding="utf-8")
    ini2 = re.search(r"^inicio \d{4}-\d{2}-\d{2} (\d{2}:\d{2}:\d{2})", reg, re.M)
    fin2 = re.search(r"^\s+fin \d{4}-\d{2}-\d{2} (\d{2}:\d{2}:\d{2})", reg, re.M)
    lit.append(("tramo 2", f"{ini2.group(1)}–{fin2.group(1)}" if ini2 and fin2 else "(falta)"))
    filas = [f for c in datos.values() for f in c.values()]
    prob, corrido, con_fb, cero = VC.autochequeos_corrida(filas)
    n_traz = sum(1 for c, fs in datos.items() for f in fs.values()
                 if VC.requiere_traza(c.split("_", 1)[1], f))
    lit.append(("FILAS", f"FILAS {len(filas)} ({len({(f['condicion'], f['seed_ep']) for f in filas})} "
                         f"distintas)"))
    lit.append(("autochequeos", f"con {prob} problemas en las {len(filas)} filas"))
    lit.append(("prueba física", f"{corrido} agente-pasos en {con_fb} episodios con fallback ({cero} de "
                                 f"ellos con 0)"))
    lit.append(("trazas", f"{n_traz} trazas"))
    for x in (f"FILAS: {len(filas)}", f"→ {prob} problemas", f"TRAZAS: {n_traz} episodios",
              "PARTE B: OK", "manifiesto pre: todas sus entradas con el sha256 actual"):
        if x not in reg:
            dif.append(f"REGISTRO: no dice «{x}»")
    fecha_pre = re.search(r"^fecha \d{4}-\d{2}-\d{2} (\d{2}:\d{2}:\d{2})",
                          RUTA_MANIFIESTO_PRE.read_text(encoding="utf-8"), re.M)
    lit.append(("manifiesto pre", f"Se hizo a las {fecha_pre.group(1)}" if fecha_pre else "(falta)"))
    # El núcleo sobre el resumen.
    dv, cv = VC.verificar("resultado")
    dif += [f"NÚCLEO: {x}" for x in dv]
    lit.append(("núcleo, líneas", f"las {cv['lineas_resumen']} líneas del resumen iguales"))
    lit.append(("núcleo, Parte B", f"en {cv['filas_con_traza']} filas desde su traza y en "
                                   f"{cv['filas_por_identidad']} por identidad"))
    lit.append(("núcleo, scipy", f"{cv['contrastes_scipy']} valores, con una diferencia máxima de "
                                 f"{cv['max_dif_scipy']:.1e}"))
    # Criterios: pruebas contadas por AST.
    for nombre, archivo in (("test_experimento_R", "test_experimento_R.py"),
                            ("test_verificar_cifras_R", "test_verificar_cifras_R.py")):
        arbol = ast.parse((_CARPETA / archivo).read_text(encoding="utf-8"))
        k = sum(1 for nodo in ast.walk(arbol) if isinstance(nodo, ast.FunctionDef)
                and nodo.name.startswith("test_"))
        lit.append((f"pruebas {nombre}", f"`{nombre}` {k}/{k}"))
    lit.append(("control 1200/1200", "1200/1200 filas idénticas en texto en las 66 columnas"))
    lit.append(("CSV", f"{len(filas)} filas, 12 celdas × {n} semillas"))
    return lit, dif


def tokens(texto: str) -> Tuple[List[str], List[str]]:
    """(cifras, horas) del texto, sin las de nombres de archivo, sha256 ni identificadores."""
    limpio = re.sub(r"(?m)^\s*\d+\.\s", " ", texto)               # numeración de listas
    limpio = re.sub(r"`[^`]*`", " ", limpio)                      # nombres de archivo, código
    limpio = re.sub(r"\b[0-9a-f]{8,}\b", " ", limpio)              # sha256 abreviados
    limpio = re.sub(r"\bS\d_\w+|\bH\d\w*(-S\d)?|\bW\s*=", " ", limpio)
    limpio = re.sub(r"§\d+(\.\d+)?|\bD\d+\b|\d{4}-\d{2}-\d{2}|\d{2}-\d{2}", " ", limpio)
    horas = _RE_HORA.findall(limpio)
    limpio = _RE_HORA.sub(" ", limpio)
    return _RE_CIFRA.findall(limpio), horas


def verificar_entrada(ruta: Path = RUTA_ENTRADA) -> Tuple[List[str], int]:
    """(diferencias, literales comprobados)."""
    texto = ruta.read_bytes().decode("utf-8")
    dif: List[str] = []
    if "\r" in texto:
        dif.append("ENTRADA: tiene CR")
    lit, d = literales()
    dif += d
    vistos: Set[str] = set()
    for que, esperado in lit:
        if esperado not in texto:
            dif.append(f"ENTRADA: falta o difiere «{esperado}» ({que})")
        else:
            vistos |= set(tokens(esperado)[0]) | set(tokens(esperado)[1])
    cifras, horas = tokens(texto)
    sueltas = sorted({c for c in cifras if c not in vistos and c.lstrip("+−-") not in DECLARADAS
                      and c not in DECLARADAS})
    sueltas_h = sorted({h for h in horas if h not in vistos and h not in DECLARADAS_HORAS})
    dif += [f"ENTRADA: cifra sin verificar ni declarar «{c}»" for c in sueltas]
    dif += [f"ENTRADA: hora sin verificar ni declarar «{h}»" for h in sueltas_h]
    return dif, len(lit)


#: Mutaciones del cierre (§4: al menos una por documento invierte un veredicto).
#: Son literales de RESULTADOS: este archivo es posterior a la corrida.
MUTACIONES_RESUMEN: Tuple[Tuple[str, str, str], ...] = (
    ("veredicto invertido (H1-S3)", "b/c = 12/0; p = 0.0005 → sostenida",
     "b/c = 12/0; p = 0.0005 → no sostenida"),
    ("cifra cambiada (H2-S2)", "b/c = 41/15", "b/c = 41/16"),
    ("cifra cambiada por otra que ya aparece (p Holm de H2-S2 por la de H1-S3)",
     "H2-S2: p = 0.0007; p Holm = 0.0027", "H2-S2: p = 0.0007; p Holm = 0.0024"),
)
MUTACIONES_ENTRADA: Tuple[Tuple[str, str, str], ...] = (
    ("veredicto invertido (H1-S3)", "b/c = 12/0; p = 0.0005 | sostenida |",
     "b/c = 12/0; p = 0.0005 | no sostenida |"),
    ("cifra cambiada (H2-S3)", "b/c = 133/44", "b/c = 133/45"),
    ("cifra cambiada por otra que ya aparece (p Holm)", "H2-S2 0.0027", "H2-S2 0.0024"),
    ("línea agregada con una cifra", "**Lectura.**\n",
     "**Lectura.**\n- En S2_quieto hubo 17 episodios con agotado.\n"),
)


def mutaciones() -> List[Tuple[str, bool]]:
    """(caso, ¿detectada?) para cada mutación, sobre copias temporales."""
    import tempfile
    salida = []
    res = (VC.DIR_RES / "resumen_R.txt").read_text(encoding="utf-8")
    ent = RUTA_ENTRADA.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as t:
        for caso, viejo, nuevo in MUTACIONES_RESUMEN:
            assert res.count(viejo) == 1, viejo
            ruta = Path(t) / "resumen_R.txt"
            ruta.write_bytes(res.replace(viejo, nuevo).encode("utf-8"))
            dif, _ = VC.verificar("resultado", ruta_resumen=ruta, contrastar=False)
            salida.append((f"resumen: {caso}", bool(dif)))
        for caso, viejo, nuevo in MUTACIONES_ENTRADA:
            assert ent.count(viejo) == 1, viejo
            ruta = Path(t) / "entrada.md"
            ruta.write_bytes(ent.replace(viejo, nuevo).encode("utf-8"))
            dif, _ = verificar_entrada(ruta)
            salida.append((f"entrada: {caso}", bool(dif)))
    return salida


def main() -> int:
    if sys.argv[1:] == ["--mutaciones"]:
        casos = mutaciones()
        for caso, detectada in casos:
            print(f"  {'DETECTADA' if detectada else 'NO DETECTADA'}: {caso}")
        return 0 if all(d for _c, d in casos) else 1
    dif, n = verificar_entrada()
    print(f"literales_bitacora_R.py — {RUTA_ENTRADA.name}: {n} literales recalculados desde el crudo")
    if dif:
        print(f"DIFERENCIAS: {len(dif)}")
        for x in dif:
            print("  " + x)
        return 1
    print("TODO COINCIDE: cada cifra de la subsección es recalculada o declarada, y el núcleo "
          "da 0 diferencias sobre resumen_R.txt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
