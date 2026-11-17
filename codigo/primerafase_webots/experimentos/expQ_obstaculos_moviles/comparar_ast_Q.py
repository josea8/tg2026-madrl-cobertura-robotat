"""
comparar_ast_Q.py
=================
Comprobación de cierre del Exp Q (§4.3 de `tesis/PROPUESTA_expO_dinamico.md`):
que lo hecho para el experimento sean SÓLO clases y funciones nuevas sobre
el Exp O, sin tocar nada.

  1. Los archivos de `expO_obstaculos/` tienen el mismo sha256 que en el
     manifiesto tomado antes de empezar (`resultados/manifiesto_expO_pre_
     20261019.txt`).
  2. Las copias de la carpeta son byte a byte las del Exp O, y su AST es el
     mismo.
  3. En cada módulo nuevo: lista de clases y funciones de nivel superior;
     ninguna redefine un nombre importado del Exp O o de `lib/`; ninguna
     asignación (ni `setattr`) sobre un atributo de un módulo o una clase
     importados; cada clase que hereda de una del Exp O o de `lib/` se lista
     con los métodos que sobrescribe.

    python -B comparar_ast_Q.py      (escribe resultados/comparar_ast_Q.txt)

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

_CARPETA: Path = Path(__file__).resolve().parent
DIR_EXP_O: Path = _CARPETA.parent / "expO_obstaculos"
RUTA_MANIFIESTO: Path = _CARPETA / "resultados" / "manifiesto_expO_pre_20261019.txt"
RUTA_SALIDA: Path = _CARPETA / "resultados" / "comparar_ast_Q.txt"

COPIAS: Tuple[str, ...] = ("lib/__init__.py", "lib/concentration_dynamics.py",
                           "lib/filtro_cbf.py", "lib/swarm_env_skeleton.py",
                           "modelos/modelo_sanidad.zip", "entorno_obstaculos.py",
                           "correr_experimento_O.py")
NUEVOS: Tuple[str, ...] = ("entorno_obstaculos_moviles.py", "correr_experimento_Q.py",
                           "analizar_experimento_Q.py", "verificar_cifras_Q.py",
                           "test_experimento_Q.py", "comparar_ast_Q.py")
#: Módulos del Exp O y de lib/ (los "originales") por nombre de importación.
ORIGINALES: Dict[str, str] = {
    "entorno_obstaculos": "entorno_obstaculos.py",
    "correr_experimento_O": "correr_experimento_O.py",
    "lib.swarm_env_skeleton": "lib/swarm_env_skeleton.py",
    "lib.concentration_dynamics": "lib/concentration_dynamics.py",
    "lib.filtro_cbf": "lib/filtro_cbf.py",
}


def sha256_de(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def metodos_de_clases(arbol: ast.Module) -> Dict[str, Tuple[List[str], Set[str]]]:
    """Clase → (nombres de las bases, métodos definidos)."""
    salida = {}
    for nodo in arbol.body:
        if isinstance(nodo, ast.ClassDef):
            bases = [ast.unparse(b) for b in nodo.bases]
            metodos = {n.name for n in nodo.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            salida[nodo.name] = (bases, metodos)
    return salida


def clases_originales() -> Dict[str, Tuple[str, List[str], Set[str]]]:
    """Nombre de clase → (módulo, bases, métodos), de los originales."""
    clases = {}
    for mod, rel in ORIGINALES.items():
        arbol = ast.parse((_CARPETA / rel).read_text(encoding="utf-8"))
        for nombre, (bases, metodos) in metodos_de_clases(arbol).items():
            clases[nombre] = (mod, bases, metodos)
    return clases


def metodos_heredados(nombre: str, clases: Dict[str, Tuple[str, List[str], Set[str]]]
                      ) -> Set[str]:
    """Métodos de una clase original y de sus bases originales."""
    if nombre not in clases:
        return set()
    _mod, bases, metodos = clases[nombre]
    salida = set(metodos)
    for b in bases:
        salida |= metodos_heredados(b.split(".")[-1], clases)
    return salida


def revisar_modulo(rel: str, clases: Dict[str, Tuple[str, List[str], Set[str]]],
                   clases_nuevas: Dict[str, Tuple[List[str], Set[str]]]
                   ) -> Tuple[List[str], List[str]]:
    """(líneas de informe, problemas) de un módulo nuevo."""
    arbol = ast.parse((_CARPETA / rel).read_text(encoding="utf-8"))
    importados: Dict[str, str] = {}        # nombre local → módulo original
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.module in ORIGINALES:
            for a in nodo.names:
                importados[a.asname or a.name] = nodo.module
        elif isinstance(nodo, ast.Import):
            for a in nodo.names:
                if a.name in ORIGINALES:
                    importados[a.asname or a.name.split(".")[0]] = a.name
    problemas: List[str] = []
    defs: List[str] = []
    for nodo in arbol.body:
        nombres: List[str] = []
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nombres = [nodo.name]
            defs.append(("clase " if isinstance(nodo, ast.ClassDef) else "función ")
                        + nodo.name)
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
        for t in objetivos:
            if (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)
                    and t.value.id in importados):
                problemas.append(f"{rel}:{nodo.lineno}: asigna {ast.unparse(t)} "
                                 f"(atributo de un original)")
        if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
                and nodo.func.id == "setattr" and nodo.args
                and isinstance(nodo.args[0], ast.Name)
                and nodo.args[0].id in importados):
            problemas.append(f"{rel}:{nodo.lineno}: setattr sobre {nodo.args[0].id}")
    L = [f"  {rel}: {len(defs)} definiciones de nivel superior, todas nuevas"
         + (": " + ", ".join(defs) if defs else "")]
    for nombre, (bases, metodos) in metodos_de_clases(arbol).items():
        heredados: Set[str] = set()
        de_originales = []
        for b in bases:
            base = b.split(".")[-1]
            if base in clases:
                heredados |= metodos_heredados(base, clases)
                de_originales.append(b)
            elif base in clases_nuevas:
                for bb in clases_nuevas[base][0]:
                    heredados |= metodos_heredados(bb.split(".")[-1], clases)
                de_originales.append(b)
        if de_originales:
            sobres = sorted(m for m in metodos if m in heredados)
            L.append(f"    clase {nombre}({', '.join(de_originales)}): sobrescribe "
                     f"{', '.join(sobres) if sobres else 'nada'}; agrega "
                     f"{', '.join(sorted(metodos - set(sobres))) or 'nada'}")
    return L, problemas


def main() -> int:
    L: List[str] = ["COMPARACIÓN DE CIERRE DEL EXP Q (sha256 y AST)"]
    problemas: List[str] = []

    # 1. Exp O intacto
    esperado: Dict[str, str] = {}
    for linea in RUTA_MANIFIESTO.read_text(encoding="utf-8").splitlines():
        h, rel = linea.split(maxsplit=1)
        esperado[rel.lstrip("*").removeprefix("./")] = h
    distintos = [rel for rel, h in esperado.items()
                 if not (DIR_EXP_O / rel).exists() or sha256_de(DIR_EXP_O / rel) != h]
    actuales = {p.relative_to(DIR_EXP_O).as_posix() for p in DIR_EXP_O.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts}
    nuevos_en_o = sorted(actuales - set(esperado))
    L.append(f"1. expO_obstaculos/: {len(esperado) - len(distintos)}/{len(esperado)} "
             f"archivos con el sha256 del manifiesto previo; archivos nuevos: "
             f"{nuevos_en_o if nuevos_en_o else 'ninguno'}")
    problemas += [f"cambió {rel} del Exp O" for rel in distintos]
    problemas += [f"archivo nuevo en el Exp O: {rel}" for rel in nuevos_en_o]

    # 2. Copias
    for rel in COPIAS:
        a, b = _CARPETA / rel, DIR_EXP_O / rel
        igual = sha256_de(a) == sha256_de(b)
        ast_igual = True
        if rel.endswith(".py"):
            ast_igual = (ast.dump(ast.parse(a.read_text(encoding="utf-8")))
                         == ast.dump(ast.parse(b.read_text(encoding="utf-8"))))
        L.append(f"2. copia {rel}: sha256 {'IGUAL' if igual else 'DISTINTO'}"
                 + (f", AST {'IGUAL' if ast_igual else 'DISTINTO'}" if rel.endswith(".py") else ""))
        if not (igual and ast_igual):
            problemas.append(f"copia distinta: {rel}")

    # 3. Módulos nuevos
    clases = clases_originales()
    clases_nuevas: Dict[str, Tuple[List[str], Set[str]]] = {}
    for rel in NUEVOS:
        clases_nuevas.update(metodos_de_clases(
            ast.parse((_CARPETA / rel).read_text(encoding="utf-8"))))
    L.append("3. módulos nuevos:")
    for rel in NUEVOS:
        lineas, prob = revisar_modulo(rel, clases, clases_nuevas)
        L += lineas
        problemas += prob

    L.append("PROBLEMAS: " + ("; ".join(problemas) if problemas else "ninguno"))
    L.append("VEREDICTO: " + ("SÓLO CLASES Y FUNCIONES NUEVAS; NINGÚN ORIGINAL TOCADO"
                              if not problemas else "NO CUMPLE"))
    RUTA_SALIDA.write_bytes(("\n".join(L) + "\n").encode("utf-8"))
    print("\n".join(L))
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
