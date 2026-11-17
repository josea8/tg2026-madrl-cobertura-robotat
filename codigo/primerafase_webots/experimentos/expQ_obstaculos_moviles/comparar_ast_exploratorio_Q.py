"""
comparar_ast_exploratorio_Q.py
==============================
EXPLORATORIO — fuera de la regla de parada. Comprueba que los scripts de lo
exploratorio (S2 y S3) SÓLO orquestan: ninguno redefine un nombre importado
del Exp O, de `lib/` o del Exp Q, ni asigna (o hace `setattr`/`del`) sobre
un atributo de un módulo o un objeto importado. Además, que el código con
huella sigue siendo el de S1 (e265b6cd…4a29).

    python -B comparar_ast_exploratorio_Q.py   (resultados/comparar_ast_EXPLORATORIO.txt)

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Dict, List, Tuple

_CARPETA: Path = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

from verificar_cifras_Q import _huella_propia

RUTA_SALIDA: Path = _CARPETA / "resultados" / "comparar_ast_EXPLORATORIO.txt"
HUELLA_S1: str = "e265b6cd31e8d443977027b1bf1d4671c002b06c3ecbdc45a275521e49c24a29"
NUEVOS: Tuple[str, ...] = ("correr_exploratorio_Q.py", "analizar_exploratorio_Q.py",
                           "verificar_cifras_exploratorio_Q.py", "test_exploratorio_Q.py",
                           "comparar_ast_exploratorio_Q.py")
ORIGINALES: Tuple[str, ...] = (
    "entorno_obstaculos", "correr_experimento_O", "lib", "lib.swarm_env_skeleton",
    "lib.concentration_dynamics", "lib.filtro_cbf", "entorno_obstaculos_moviles",
    "correr_experimento_Q", "analizar_experimento_Q", "verificar_cifras_Q", "comparar_ast_Q",
    "correr_exploratorio_Q", "analizar_exploratorio_Q", "verificar_cifras_exploratorio_Q",
)


def raiz(nodo: ast.AST) -> str:
    """Nombre en la raíz de una cadena de atributos o subíndices (a.b[c].d → a)."""
    while isinstance(nodo, (ast.Attribute, ast.Subscript)):
        nodo = nodo.value
    return nodo.id if isinstance(nodo, ast.Name) else ""


def revisar(rel: str) -> Tuple[List[str], List[str]]:
    arbol = ast.parse((_CARPETA / rel).read_text(encoding="utf-8"))
    propio = rel[:-3]
    importados: Dict[str, str] = {}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.module in ORIGINALES and nodo.module != propio:
            for a in nodo.names:
                importados[a.asname or a.name] = nodo.module
        elif isinstance(nodo, ast.Import):
            for a in nodo.names:
                if a.name in ORIGINALES and a.name != propio:
                    importados[a.asname or a.name.split(".")[0]] = a.name
    problemas: List[str] = []
    defs: List[str] = []
    for nodo in arbol.body:
        nombres: List[str] = []
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nombres = [nodo.name]
            defs.append(("clase " if isinstance(nodo, ast.ClassDef) else "función ") + nodo.name)
        elif isinstance(nodo, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            objetivos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
            nombres = [t.id for t in objetivos if isinstance(t, ast.Name)]
        for n in nombres:
            if n in importados:
                problemas.append(f"{rel}: redefine '{n}', importado de {importados[n]}")
    for nodo in ast.walk(arbol):
        objetivos = []
        if isinstance(nodo, ast.Assign):
            objetivos = nodo.targets
        elif isinstance(nodo, (ast.AnnAssign, ast.AugAssign)):
            objetivos = [nodo.target]
        elif isinstance(nodo, ast.Delete):
            objetivos = nodo.targets
        for t in objetivos:
            if isinstance(t, (ast.Attribute, ast.Subscript)) and raiz(t) in importados:
                problemas.append(f"{rel}:{nodo.lineno}: modifica {ast.unparse(t)} (importado)")
        if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
                and nodo.func.id in ("setattr", "delattr") and nodo.args
                and raiz(nodo.args[0]) in importados):
            problemas.append(f"{rel}:{nodo.lineno}: {nodo.func.id} sobre un importado")
        if isinstance(nodo, ast.Attribute) and nodo.attr in ("patch", "patch.object"):
            problemas.append(f"{rel}:{nodo.lineno}: usa mock.patch")
    L = [f"  {rel}: {len(defs)} definiciones de nivel superior, todas nuevas: " + ", ".join(defs),
         f"    importa de los originales: " + (", ".join(f"{n} ({m})" for n, m in
                                                     sorted(importados.items())) or "nada")]
    return L, problemas


def main() -> int:
    L = ["EXPLORATORIO — comprobación por AST de los scripts de S2 y S3 (fuera de la "
         "regla de parada)"]
    problemas: List[str] = []
    huella = _huella_propia()
    L.append(f"huella del código con huella: {huella} "
             f"({'IGUAL' if huella == HUELLA_S1 else 'DISTINTA'} a la de S1)")
    if huella != HUELLA_S1:
        problemas.append("la huella del código cambió")
    for rel in NUEVOS:
        lineas, prob = revisar(rel)
        L += lineas
        problemas += prob
    L.append("PROBLEMAS: " + ("; ".join(problemas) if problemas else "ninguno"))
    L.append("VEREDICTO: " + ("SÓLO ORQUESTAN: NADA REDEFINIDO NI PARCHEADO" if not problemas
                              else "NO CUMPLE"))
    RUTA_SALIDA.write_bytes(("\n".join(L) + "\n").encode("utf-8"))
    print("\n".join(L))
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
