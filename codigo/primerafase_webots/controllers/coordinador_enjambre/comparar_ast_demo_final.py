"""
comparar_ast_demo_final.py
==========================
DEMOSTRACIÓN, NO CITABLE. Comprueba por AST que los archivos nuevos de la
demostración final SÓLO orquestan (precedente: `comparar_ast_exploratorio_Q.py`):

  1. ninguno redefine (clase, función o asignación, a cualquier nivel) un
     nombre importado de un módulo congelado;
  2. ninguno asigna, borra ni hace `setattr`/`delattr` sobre un atributo de
     un módulo congelado importado (en las pruebas, reponer la configuración
     en `tearDown` se informa aparte, no es un parche);
  3. las pruebas no parchean (`mock.patch`) nada de un módulo congelado: se
     listan los parches y su destino;
  4. cada bloque `# ── COPIA LITERAL de <archivo> a-b ──` de `demo_final.py`
     es IDÉNTICO, línea por línea, a esas líneas de su fuente (sin contar el
     fin de línea), salvo las marcadas `# [demo]`, que se listan.

Los envoltorios LOCALES de `sesion_mejorada` (nombres que usa la copia y que
llaman a la función congelada) se listan como tales.

    python -B comparar_ast_demo_final.py   (resultados_demo_final/comparar_ast_demo_final.txt)

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

_CARPETA: Path = Path(__file__).resolve().parent
RUTA_SALIDA: Path = _CARPETA / "resultados_demo_final" / "comparar_ast_demo_final.txt"
NUEVOS: Tuple[str, ...] = ("demo_final.py", "publicador_estado.py", "panel_demo.py",
                           "test_demo_final.py", "comparar_ast_demo_final.py",
                           "verificar_cifras_demo_final.py")
#: Los módulos de `campana_obstaculo.ARCHIVOS_CONGELADOS`.
CONGELADOS: Tuple[str, ...] = (
    "adaptadores_robotat", "calibracion_sesion", "campana_obstaculo",
    "colocacion_autonoma", "colocacion_con_obstaculo", "coordinador_enjambre",
    "demo_obstaculo_movil", "interfaces", "lanzar_robotat", "lib",
    "lib.concentration_dynamics", "lib.filtro_cbf", "lib.swarm_env_skeleton",
    "protocolo", "protocolo_robotat", "retroceso_congelamiento", "sesion_robotat",
    "analizar_campana_l2", "verificar_campana_l2", "config_robotat",
)
#: Los envoltorios locales declarados (función → nombre que usa la copia).
ENVOLTORIOS: Dict[str, str] = {
    "_colocar_toma_automatica": "_colocar_publicando",
    "correr_toma": "_correr_toma_publicando",
    "aplicar_regla_de_parada": "_aplicar_regla_publicando",
}
#: Sombras LOCALES declaradas (dentro de una función, nunca de módulo): las
#: copias literales toman la semilla de `SEMILLAS_LOTE[intento - 1]`, y con
#: `--semillas` ese nombre local es la lista pedida.
SOMBRAS_LOCALES: Dict[str, str] = {
    "SEMILLAS_LOTE": "la lista de --semillas que usan las copias literales",
}
_MARCA = re.compile(r"# ── COPIA LITERAL de (\S+) (\d+)-(\d+) ──")


def raiz(nodo: ast.AST) -> str:
    """Nombre en la raíz de una cadena de atributos o subíndices (a.b[c].d → a)."""
    while isinstance(nodo, (ast.Attribute, ast.Subscript)):
        nodo = nodo.value
    return nodo.id if isinstance(nodo, ast.Name) else ""


def _en_teardown(arbol: ast.AST) -> set:
    """Las líneas que están dentro de un método `tearDown`."""
    lineas = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.FunctionDef) and n.name == "tearDown":
            lineas.update(range(n.lineno, (n.end_lineno or n.lineno) + 1))
    return lineas


def revisar(rel: str) -> Tuple[List[str], List[str]]:
    texto = (_CARPETA / rel).read_text(encoding="utf-8")
    arbol = ast.parse(texto)
    importados: Dict[str, str] = {}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.module in CONGELADOS:
            for a in nodo.names:
                importados[a.asname or a.name] = nodo.module
        elif isinstance(nodo, ast.Import):
            for a in nodo.names:
                if a.name in CONGELADOS:
                    importados[a.asname or a.name.split(".")[0]] = a.name
    problemas: List[str] = []
    notas: List[str] = []
    defs = [("clase " if isinstance(n, ast.ClassDef) else "función ") + n.name
            for n in arbol.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    teardown = _en_teardown(arbol)
    de_modulo = {id(n) for n in arbol.body}
    for nodo in ast.walk(arbol):
        # (1) redefiniciones, a cualquier nivel
        nombres: List[Tuple[str, int]] = []
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nombres = [(nodo.name, nodo.lineno)]
        elif isinstance(nodo, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            objetivos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
            nombres = [(t.id, nodo.lineno) for t in objetivos if isinstance(t, ast.Name)]
        for n, ln in nombres:
            if (n in SOMBRAS_LOCALES and rel == "demo_final.py"
                    and id(nodo) not in de_modulo):
                notas.append(f"{rel}:{ln}: sombra local declarada '{n}' "
                             f"({SOMBRAS_LOCALES[n]})")
            elif n in importados:
                problemas.append(f"{rel}:{ln}: redefine '{n}', importado de {importados[n]}")
            elif (n in ENVOLTORIOS and rel == "demo_final.py"
                  and isinstance(nodo, ast.Assign)
                  and isinstance(nodo.value, ast.Name)
                  and nodo.value.id == ENVOLTORIOS[n]):
                notas.append(f"{rel}:{ln}: envoltorio local '{n}' = {nodo.value.id} "
                             f"(llama a la congelada; el módulo no se toca)")
        # (2) asignaciones a atributos de un congelado
        objetivos = []
        if isinstance(nodo, ast.Assign):
            objetivos = nodo.targets
        elif isinstance(nodo, (ast.AnnAssign, ast.AugAssign)):
            objetivos = [nodo.target]
        elif isinstance(nodo, ast.Delete):
            objetivos = nodo.targets
        for t in objetivos:
            if isinstance(t, (ast.Attribute, ast.Subscript)) and raiz(t) in importados:
                problemas.append(f"{rel}:{nodo.lineno}: modifica {ast.unparse(t)} (congelado)")
        if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
                and nodo.func.id in ("setattr", "delattr") and nodo.args
                and raiz(nodo.args[0]) in importados):
            if nodo.lineno in teardown and nodo.func.id == "setattr":
                notas.append(f"{rel}:{nodo.lineno}: setattr sobre "
                             f"{ast.unparse(nodo.args[0])} en tearDown (repone la "
                             f"configuración guardada en setUp)")
            else:
                problemas.append(f"{rel}:{nodo.lineno}: {nodo.func.id} sobre un congelado")
        # (3) parches
        if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr in ("patch", "object")
                and "patch" in ast.unparse(nodo.func) and nodo.args):
            destino = nodo.args[0]
            if nodo.func.attr == "object":
                quien = raiz(destino)
                desc = f"mock.patch.object({ast.unparse(destino)}, {ast.unparse(nodo.args[1])})"
                if quien in importados:
                    problemas.append(f"{rel}:{nodo.lineno}: {desc} parchea un congelado")
                else:
                    notas.append(f"{rel}:{nodo.lineno}: {desc} — módulo propio")
            elif isinstance(destino, ast.Constant) and isinstance(destino.value, str):
                mod = destino.value.rsplit(".", 1)[0]
                desc = f"mock.patch({destino.value!r})"
                if mod in CONGELADOS:
                    problemas.append(f"{rel}:{nodo.lineno}: {desc} parchea un congelado")
                else:
                    notas.append(f"{rel}:{nodo.lineno}: {desc} — biblioteca estándar "
                                 f"(reloj fijado dentro de la prueba 5)")
    L = [f"  {rel}: {len(defs)} definiciones de nivel superior, todas nuevas: "
         + (", ".join(defs) or "ninguna"),
         "    importa de los congelados: "
         + (", ".join(f"{n} ({m})" for n, m in sorted(importados.items())) or "nada")]
    L += [f"    nota: {n}" for n in notas]
    return L, problemas


def revisar_copias(rel: str = "demo_final.py") -> Tuple[List[str], List[str]]:
    lineas = (_CARPETA / rel).read_text(encoding="utf-8").split("\n")
    L: List[str] = []
    problemas: List[str] = []
    k = 0
    while k < len(lineas):
        m = _MARCA.search(lineas[k])
        if not m:
            k += 1
            continue
        fuente, a, b = m.group(1), int(m.group(2)), int(m.group(3))
        fin = next(j for j in range(k + 1, len(lineas))
                   if f"fin de la copia {a}-{b}" in lineas[j])
        copia = lineas[k + 1:fin]
        orig = (_CARPETA / fuente).read_bytes().decode("utf-8").replace(
            "\r\n", "\n").split("\n")[a - 1:b]
        cambios = []
        if len(copia) != len(orig):
            problemas.append(f"copia de {fuente} {a}-{b}: {len(copia)} líneas, "
                             f"la fuente tiene {len(orig)}")
        for i, (c, o) in enumerate(zip(copia, orig)):
            if c != o:
                if "# [demo]" in c:
                    cambios.append(f"{fuente}:{a + i}: «{o.strip()}» → «{c.strip()}»")
                else:
                    problemas.append(f"copia de {fuente} {a}-{b}: línea {a + i} "
                                     f"distinta y sin marca [demo]")
        L.append(f"  {rel}:{k + 1}: COPIA de {fuente} {a}-{b} ({len(orig)} líneas): "
                 + ("IDÉNTICA" if not cambios else
                    f"idéntica salvo {len(cambios)} línea(s) marcada(s) [demo]"))
        L += [f"      [demo] {c}" for c in cambios]
        k = fin + 1
    return L, problemas


def main() -> int:
    L = ["DEMOSTRACIÓN, NO CITABLE — comprobación por AST de los archivos nuevos "
         "de la demostración final"]
    problemas: List[str] = []
    for rel in NUEVOS:
        lineas, prob = revisar(rel)
        L += lineas
        problemas += prob
    L.append("Copias literales:")
    lineas, prob = revisar_copias()
    L += lineas
    problemas += prob
    L.append("PROBLEMAS: " + ("; ".join(problemas) if problemas else "ninguno"))
    L.append("VEREDICTO: " + ("SÓLO ORQUESTAN: NADA REDEFINIDO NI PARCHEADO; COPIAS "
                              "IDÉNTICAS SALVO LO MARCADO [demo]" if not problemas
                              else "NO CUMPLE"))
    RUTA_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    RUTA_SALIDA.write_bytes(("\n".join(L) + "\n").encode("utf-8"))
    print("\n".join(L))
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
