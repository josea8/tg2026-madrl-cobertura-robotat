"""
comparar_ast_R.py
=================
Comprueba, sin correr episodios, que `correr_experimento_R.py` sólo AGREGA
REGISTRO a la copia de `correr_episodio_Q` y no redefine ni parchea nada de
Q, O, `entorno_obstaculos*` ni `lib/`. Certifica el CUERPO de
`correr_episodio_R` y la identidad de sus nombres libres; la orquestación
(`_tarea_R`, `correr_condiciones_R`) la cubren la revisión y el control. Cuatro
comprobaciones; las cuatro tienen que dar OK:

  1. SÓLO AGREGA REGISTRO. Hay UN solo `def correr_episodio_R` de nivel
     superior, sin decoradores y sin otra ligadura de ese nombre. Se quitan de
     él las líneas que terminan en `# [R]` y los bloques entre `# [R] inicio`
     y `# [R] fin`; lo que queda tiene que ser IGUAL EN TEXTO a
     `correr_episodio_Q` (`correr_experimento_Q.py:317-534`, salvo el nombre
     en la línea del `def`) y su `ast.dump` (con el FunctionDef renombrado en
     el AST) igual al de Q. Las marcas `[R]` sólo pueden estar dentro de esa
     función, y el archivo tiene el fin de línea de Q (LF).
  2. SÓLO ORQUESTA. Ningún `def`, `class`, asignación ni import de nivel de
     módulo de R liga un nombre de Q, O, `entorno_obstaculos*`, `lib/*` o de
     los builtins, salvo `control`, `pasabilidad`, `experimento`, `main`,
     `_MODELO = None` (una sola vez) y los imports de esos mismos módulos. En
     ninguna parte de R: asignación, `del` o método mutador sobre algo
     importado o sobre un alias suyo (asignación, anotación, `for`, walrus,
     desempaque); `setattr`, `delattr`, `getattr`, `globals`, `vars`, `exec`,
     `eval`, `__import__`, `compile`, `reload`, `import_module`,
     `sys.modules` ni `.patch`; `global` sólo el `_MODELO` de la copia; el
     nivel de módulo sólo tiene docstring, imports, constantes, `def`,
     `class` y los tres `if` previstos (-B, sys.path, main), con
     `sys.path.insert(0, str(_CARPETA_Q))` y `_CARPETA_Q` literales.
  3. LAS LÍNEAS [R] SÓLO REGISTRAN. Cada sentencia [R] está marcada en
     TODAS sus líneas; es una asignación a nombres NUEVOS (que no aparecen en
     `correr_episodio_Q` ni en esos espacios de nombres, ni son alias [R] de
     un objeto de Q) o un `append` sobre uno de ellos; un subíndice sólo de
     un nivel (`nuevo[i] = …`); sus llamadas son sólo a `int`, `float`,
     `bool`, `len`, `list`, `tuple`, `range`, `min`, `max`, `sum`, `abs`,
     `any`, `all`, `zip`, `enumerate`, a métodos puros (`copy`, `get`,
     `tolist`, `keys`, `values`, `items`) o a `append` de un nombre nuevo, y
     sin argumentos con nombre (`key=` ejecutaría cualquier cosa). Ninguna
     línea [R] es un `else:`. Las entradas [R] del dict de retorno van al
     final, con claves nuevas, sin `**` y con un nombre nuevo de valor.
  4. NOMBRES LIBRES. Hay una sentencia `from correr_experimento_Q import …`
     cuyo conjunto de nombres es EXACTAMENTE el de los nombres libres del
     cuerpo de `correr_episodio_Q` (AST, sin `_MODELO`), sin `as`, y ninguno
     de ellos se liga en otro lugar del nivel superior. Importado R, cada uno
     es el MISMO objeto que en Q (`is`), `_MODELO` de R es None, la función
     cargada es la del `def` verificado, y Q, O, los entornos y `lib/` se
     cargaron desde la carpeta del Exp Q.

    python -B comparar_ast_R.py      (resultados/comparar_ast_R.txt)

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import sys

if not sys.flags.dont_write_bytecode:
    raise SystemExit("PARAR: correr con python -B (importar R importa el Exp Q).")

import ast
import builtins
import hashlib
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple

_CARPETA: Path = Path(__file__).resolve().parent
_CARPETA_Q: Path = (_CARPETA.parent / "expQ_obstaculos_moviles").resolve()
RUTA_R: Path = _CARPETA / "correr_experimento_R.py"
RUTA_Q: Path = _CARPETA_Q / "correr_experimento_Q.py"
RUTA_SALIDA: Path = _CARPETA / "resultados" / "comparar_ast_R.txt"
#: Módulos cuyos nombres de nivel superior R no puede volver a ligar.
ORIGINALES: Tuple[str, ...] = (
    "correr_experimento_Q.py", "correr_experimento_O.py", "entorno_obstaculos.py",
    "entorno_obstaculos_moviles.py", "lib/__init__.py", "lib/swarm_env_skeleton.py",
    "lib/concentration_dynamics.py", "lib/filtro_cbf.py",
)
#: Los módulos importados que se cargan desde la carpeta del Exp Q.
MODULOS_Q: Tuple[str, ...] = ("correr_experimento_Q", "correr_experimento_O",
                              "entorno_obstaculos", "entorno_obstaculos_moviles",
                              "lib.filtro_cbf", "lib.swarm_env_skeleton",
                              "lib.concentration_dynamics")
MARCA, INICIO, FIN = "# [R]", "# [R] inicio", "# [R] fin"
DEFS_PERMITIDOS: Set[str] = {"control", "pasabilidad", "experimento", "main"}
#: El texto exacto de las dos líneas que fijan de dónde se importa Q.
CARPETA_Q_LITERAL: str = "(_CARPETA_R.parent / 'expQ_obstaculos_moviles').resolve()"
CARPETA_R_LITERAL: str = "Path(__file__).resolve().parent"
INSERCION_LITERAL: str = "sys.path.insert(0, str(_CARPETA_Q))"
PROHIBIDAS: Set[str] = {"setattr", "delattr", "getattr", "globals", "vars", "exec", "eval",
                        "__import__", "compile"}
ATRIBUTOS_PROHIBIDOS: Set[str] = {"reload", "import_module", "patch", "modules"}
MUTADORES: Set[str] = {"append", "extend", "insert", "remove", "pop", "popitem", "clear",
                       "update", "setdefault", "add", "discard", "sort", "reverse", "fill",
                       "put", "resize", "itemset", "__setitem__", "__delitem__",
                       "__setattr__", "__delattr__", "__ior__", "__iadd__", "__init__",
                       "copyto", "putmask", "place"}
#: Módulos que sólo sirven para mutar por la puerta de atrás.
MODULOS_PROHIBIDOS: Set[str] = {"operator", "importlib", "ctypes.util", "copyreg", "gc"}
BUILTINS_R: Set[str] = {"int", "float", "bool", "len", "list", "tuple", "range", "min",
                        "max", "sum", "abs", "any", "all", "zip", "enumerate"}
METODOS_PUROS_R: Set[str] = {"copy", "get", "tolist", "keys", "values", "items"}
NOMBRES_BUILTINS: Set[str] = set(dir(builtins))


def raiz(nodo: ast.AST) -> str:
    """Nombre en la raíz de una cadena de atributos o subíndices (a.b[c].d → a)."""
    while isinstance(nodo, (ast.Attribute, ast.Subscript, ast.Starred)):
        nodo = nodo.value
    if isinstance(nodo, ast.NamedExpr):
        return raiz(nodo.value)
    return nodo.id if isinstance(nodo, ast.Name) else ""


def funciones(arbol: ast.Module, nombre: str) -> List[ast.FunctionDef]:
    return [n for n in arbol.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == nombre]


def funcion(arbol: ast.Module, nombre: str) -> ast.FunctionDef:
    return funciones(arbol, nombre)[0]


def lineas_marcadas(texto: str) -> Set[int]:
    """Números de línea (desde 1) marcados [R]: los que terminan en la marca y
    los bloques entre `# [R] inicio` y `# [R] fin`, inclusive."""
    marcadas: Set[int] = set()
    dentro = False
    for i, linea in enumerate(texto.split("\n"), start=1):
        s = linea.strip()
        if s == INICIO:
            dentro = True
        if dentro or linea.rstrip().endswith(MARCA):
            marcadas.add(i)
        if s == FIN:
            dentro = False
    return marcadas


def ligaduras_de_nivel(n: ast.stmt) -> Set[str]:
    """Nombres que liga UNA sentencia de nivel superior (def, class, asignación, import)."""
    nombres: Set[str] = set()
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        nombres.add(n.name)
    elif isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.For)):
        objetivos = n.targets if isinstance(n, ast.Assign) else [n.target]
        for o in objetivos:
            nombres |= {x.id for x in ast.walk(o) if isinstance(x, ast.Name)}
    elif isinstance(n, (ast.Import, ast.ImportFrom)):
        nombres |= {(a.asname or a.name).split(".")[0] for a in n.names}
    elif isinstance(n, ast.If):
        for s in n.body + n.orelse:
            nombres |= ligaduras_de_nivel(s)
    return nombres


def nombres_de_nivel(texto: str) -> Set[str]:
    """Nombres que liga el nivel superior de un módulo."""
    salida: Set[str] = set()
    for n in ast.parse(texto).body:
        salida |= ligaduras_de_nivel(n)
    return salida


def nombres_libres_Q(texto_q: str) -> Set[str]:
    """Nombres que el cuerpo de `correr_episodio_Q` usa y no liga (sin builtins)."""
    fn = funcion(ast.parse(texto_q), "correr_episodio_Q")
    ligados = {a.arg for a in fn.args.args}
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            ligados.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            ligados |= {(a.asname or a.name).split(".")[0] for a in n.names}
    usados = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)
              and isinstance(n.ctx, ast.Load)}
    globales = {x for g in ast.walk(fn) if isinstance(g, ast.Global) for x in g.names}
    return (usados - ligados - NOMBRES_BUILTINS) | globales


def todos_los_nombres(nodo: ast.AST) -> Set[str]:
    """Todo identificador que aparece en un nodo (nombres, argumentos, atributos)."""
    salida: Set[str] = set()
    for n in ast.walk(nodo):
        if isinstance(n, ast.Name):
            salida.add(n.id)
        elif isinstance(n, ast.arg):
            salida.add(n.arg)
        elif isinstance(n, ast.Attribute):
            salida.add(n.attr)
    return salida


# =============================================================================
# COMPROBACIÓN 1
# =============================================================================

def comprobacion_1(texto_r: str, texto_q: str) -> Tuple[List[str], str]:
    """(problemas, detalle)."""
    problemas: List[str] = []
    if "\r\n" in texto_r and "\r\n" not in texto_q:
        problemas.append("fin de línea distinto (CRLF en R; Q es LF)")
    arbol_r = ast.parse(texto_r)
    defs = funciones(arbol_r, "correr_episodio_R")
    otras = [n.lineno for n in arbol_r.body if "correr_episodio_R" in ligaduras_de_nivel(n)
             and n not in defs]
    if len(defs) != 1 or otras:
        problemas.append(f"correr_episodio_R tiene que ligarse UNA vez (defs en "
                         f"{[d.lineno for d in defs]}, otras ligaduras en {otras})")
    fr = defs[0]
    if fr.decorator_list:
        problemas.append(f"línea {fr.lineno}: correr_episodio_R no puede tener decoradores")
    lin_r = texto_r.split("\n")
    fq = funcion(ast.parse(texto_q), "correr_episodio_Q")
    marcadas = lineas_marcadas(texto_r)
    fuera = sorted(i for i in marcadas if not fr.lineno <= i <= fr.end_lineno)
    if fuera:
        problemas.append(f"marcas [R] fuera de correr_episodio_R: líneas {fuera[:10]}")
    seg = [lin_r[i - 1] for i in range(fr.lineno, fr.end_lineno + 1) if i not in marcadas]
    seg_q = texto_q.split("\n")[fq.lineno - 1:fq.end_lineno]
    texto_igual = ([seg[0].replace("def correr_episodio_R(", "def correr_episodio_Q(", 1)]
                   + seg[1:]) == seg_q if seg else False
    if not texto_igual:
        primera = next((j for j, (a, b) in enumerate(zip(seg[1:], seg_q[1:]), start=1)
                        if a != b), min(len(seg), len(seg_q)))
        problemas.append(f"el texto sin [R] difiere de Q (línea {primera} de la función: "
                         f"{seg[primera] if primera < len(seg) else '∅'!r})")
    try:
        f2 = ast.parse("\n".join(seg)).body[0]
        f2.name = "correr_episodio_Q"
        if ast.dump(f2) != ast.dump(fq):
            problemas.append("el AST sin [R] difiere del de correr_episodio_Q")
    except SyntaxError as e:
        problemas.append(f"quitar las líneas [R] rompe la sintaxis: {e}")
    detalle = (f"texto y AST de correr_episodio_R sin sus {len(marcadas)} líneas [R] "
               f"idénticos a correr_episodio_Q (correr_experimento_Q.py:{fq.lineno}-"
               f"{fq.end_lineno}, salvo el nombre); un solo def, sin decoradores")
    return problemas, detalle


# =============================================================================
# COMPROBACIÓN 2
# =============================================================================

def _if_permitido(n: ast.If) -> bool:
    """Los tres `if` de nivel superior previstos: -B, sys.path y main."""
    cuerpo = n.body
    if n.orelse or len(cuerpo) != 1:
        return False
    s = cuerpo[0]
    if isinstance(s, ast.Raise):
        return isinstance(s.exc, ast.Call) and getattr(s.exc.func, "id", "") == "SystemExit"
    if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call):
        f = s.value.func
        if isinstance(f, ast.Name) and f.id == "main" and not s.value.args:
            return True
        return ast.unparse(s.value) == INSERCION_LITERAL
    return False


def _alias_de_funcion(fn: ast.AST, raices: Set[str]) -> Set[str]:
    """
    Nombres que dentro de `fn` quedan ligados a algo importado (o a un alias):
    asignación, anotación con valor, `for … in <importado>`, walrus o
    desempaque, con un valor que es un nombre, atributo o subíndice (pelado) de
    raíz vigilada. El resultado de una llamada es un objeto nuevo y no cuenta.
    """
    propios: Set[str] = set()

    def vigilado(v: ast.AST) -> bool:
        if isinstance(v, (ast.Tuple, ast.List)):
            return any(vigilado(e) for e in v.elts)
        return (isinstance(v, (ast.Name, ast.Attribute, ast.Subscript, ast.NamedExpr))
                and raiz(v) in raices | propios)

    # Parámetros con valor por defecto importado (def f(x=Q.ALGO)).
    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        a = fn.args
        posicionales = a.posonlyargs + a.args
        for arg, d in list(zip(posicionales[len(posicionales) - len(a.defaults):], a.defaults)) + [
                (k, d) for k, d in zip(a.kwonlyargs, a.kw_defaults) if d is not None]:
            if vigilado(d):
                propios.add(arg.arg)
    cambio = True
    while cambio:
        cambio = False
        for a in ast.walk(fn):
            pares: List[Tuple[ast.AST, ast.AST]] = []
            if isinstance(a, ast.Assign):
                pares = [(o, a.value) for o in a.targets]
            elif isinstance(a, ast.AnnAssign) and a.value is not None:
                pares = [(a.target, a.value)]
            elif isinstance(a, (ast.For, ast.comprehension)):
                pares = [(a.target, a.iter)]
            elif isinstance(a, ast.NamedExpr):
                pares = [(a.target, a.value)]
            elif isinstance(a, ast.withitem) and a.optional_vars is not None:
                pares = [(a.optional_vars, a.context_expr)]
            for objetivo, valor in pares:
                if vigilado(valor):
                    for x in ast.walk(objetivo):
                        if isinstance(x, ast.Name) and x.id not in propios:
                            propios.add(x.id)
                            cambio = True
    return propios


def comprobacion_2(texto_r: str, espacios: Set[str]) -> List[str]:
    problemas: List[str] = []
    arbol = ast.parse(texto_r)
    importados: Set[str] = set()
    asignaciones_modelo = 0
    for i, n in enumerate(arbol.body):
        ligados = ligaduras_de_nivel(n)
        con_builtin = sorted(ligados & NOMBRES_BUILTINS)
        if con_builtin:
            problemas.append(f"línea {n.lineno}: liga {con_builtin}, que son builtins que usa "
                             f"la copia")
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            if any(a.name == "*" for a in n.names):
                problemas.append(f"línea {n.lineno}: import * no permitido")
            modulos = ({a.name for a in n.names} if isinstance(n, ast.Import)
                       else {n.module or ""})
            if modulos & MODULOS_PROHIBIDOS:
                problemas.append(f"línea {n.lineno}: import de {sorted(modulos & MODULOS_PROHIBIDOS)}")
            importados |= ligados
        elif isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            if n.name in espacios and n.name not in DEFS_PERMITIDOS:
                problemas.append(f"línea {n.lineno}: def/class {n.name} redefine un nombre "
                                 f"de Q/O/entorno/lib")
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            objetivos = n.targets if isinstance(n, ast.Assign) else [n.target]
            for o in objetivos:
                if not isinstance(o, ast.Name):
                    problemas.append(f"línea {n.lineno}: asignación de nivel superior a "
                                     f"{ast.unparse(o)}")
                elif o.id == "_MODELO":
                    asignaciones_modelo += 1
                    if not (isinstance(n.value, ast.Constant) and n.value.value is None):
                        problemas.append(f"línea {n.lineno}: _MODELO tiene que ser None")
                elif o.id in espacios:
                    problemas.append(f"línea {n.lineno}: la asignación a {o.id} sombrea un "
                                     f"nombre de Q/O/entorno/lib")
                elif o.id == "_CARPETA_Q" and ast.unparse(n.value) != CARPETA_Q_LITERAL:
                    problemas.append(f"línea {n.lineno}: _CARPETA_Q no es "
                                     f"{CARPETA_Q_LITERAL}")
                elif o.id == "_CARPETA_R" and ast.unparse(n.value) != CARPETA_R_LITERAL:
                    problemas.append(f"línea {n.lineno}: _CARPETA_R no es "
                                     f"{CARPETA_R_LITERAL}")
        elif isinstance(n, ast.If):
            if not _if_permitido(n):
                problemas.append(f"línea {n.lineno}: if de nivel superior no previsto")
        elif isinstance(n, ast.Expr) and i == 0 and isinstance(n.value, ast.Constant):
            continue
        else:
            problemas.append(f"línea {n.lineno}: sentencia de nivel superior no prevista "
                             f"({type(n).__name__})")
    if asignaciones_modelo != 1:
        problemas.append(f"_MODELO se asigna {asignaciones_modelo} veces en el nivel superior")
    # Alias de algo importado, por función: mutarlos es mutar lo importado.
    alias: Dict[int, Set[str]] = {}
    for fn in ast.walk(arbol):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            propios = _alias_de_funcion(fn, importados)
            for x in ast.walk(fn):
                alias.setdefault(id(x), set()).update(propios)
    inserciones_path = 0
    for n in ast.walk(arbol):
        vigilados = importados | alias.get(id(n), set())
        if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)):
            objetivos = (n.targets if isinstance(n, (ast.Assign, ast.Delete)) else [n.target])
            for o in objetivos:
                if isinstance(n, ast.AugAssign) and isinstance(o, ast.Name) \
                        and o.id in alias.get(id(n), set()):
                    problemas.append(f"línea {n.lineno}: {o.id} {type(n.op).__name__}= sobre un "
                                     f"alias de algo importado")
                for x in ast.walk(o):
                    if (isinstance(x, (ast.Attribute, ast.Subscript))
                            and isinstance(x.ctx, (ast.Store, ast.Del))
                            and raiz(x) in vigilados):
                        problemas.append(f"línea {n.lineno}: modifica {ast.unparse(x)}, "
                                         f"que es importado")
        elif isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id in PROHIBIDAS:
                problemas.append(f"línea {n.lineno}: llama a {f.id}")
            elif isinstance(f, ast.Attribute):
                if f.attr in ATRIBUTOS_PROHIBIDOS:
                    problemas.append(f"línea {n.lineno}: usa .{f.attr}")
                elif f.attr in MUTADORES and raiz(f.value) in vigilados:
                    if ast.unparse(n) == INSERCION_LITERAL:
                        inserciones_path += 1
                    else:
                        problemas.append(f"línea {n.lineno}: {ast.unparse(f)} muta algo "
                                         f"importado")
        elif isinstance(n, ast.Attribute) and n.attr in ATRIBUTOS_PROHIBIDOS:
            problemas.append(f"línea {n.lineno}: usa .{n.attr}")
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            if not (isinstance(n, ast.Global) and n.names == ["_MODELO"]):
                problemas.append(f"línea {n.lineno}: {type(n).__name__.lower()} {n.names}")
    globales = [n for n in ast.walk(funcion(arbol, "correr_episodio_R"))
                if isinstance(n, ast.Global)]
    total_globales = [n for n in ast.walk(arbol) if isinstance(n, ast.Global)]
    if len(globales) != 1 or len(total_globales) != 1:
        problemas.append("`global _MODELO` tiene que estar sólo en correr_episodio_R")
    if inserciones_path != 1:
        problemas.append(f"'{INSERCION_LITERAL}' aparece {inserciones_path} veces (tiene que "
                         f"ser 1)")
    return problemas


# =============================================================================
# COMPROBACIÓN 3
# =============================================================================

def _sentencias(cuerpo: Sequence[ast.stmt]):
    """Todas las sentencias de un cuerpo, recursivamente."""
    for s in cuerpo:
        yield s
        for campo in ("body", "orelse", "finalbody"):
            yield from _sentencias(getattr(s, campo, []) or [])
        for h in getattr(s, "handlers", []) or []:
            yield from _sentencias(h.body)


def comprobacion_3(texto_r: str, texto_q: str, espacios: Set[str]) -> Tuple[List[str], str]:
    problemas: List[str] = []
    marcadas = lineas_marcadas(texto_r)
    lin = texto_r.split("\n")
    fr = funcion(ast.parse(texto_r), "correr_episodio_R")
    fq = funcion(ast.parse(texto_q), "correr_episodio_Q")
    prohibidos = todos_los_nombres(fq) | espacios
    for i in sorted(marcadas):
        cuerpo = lin[i - 1].rstrip()
        cuerpo = cuerpo[:-len(MARCA)].strip() if cuerpo.endswith(MARCA) else cuerpo.strip()
        if cuerpo.startswith(("else", "elif", "except", "finally")):
            problemas.append(f"línea {i}: una línea [R] no puede ser {cuerpo.split(':')[0]}")
    cubiertas: Set[int] = set()
    sent_r: List[ast.stmt] = []
    for s in _sentencias(fr.body):
        lineas = set(range(s.lineno, s.end_lineno + 1))
        if lineas <= marcadas:
            sent_r.append(s)
            cubiertas |= lineas
        elif (lineas & marcadas) and not isinstance(s, (ast.While, ast.For, ast.If,
                                                         ast.With, ast.Try, ast.Return)):
            problemas.append(f"línea {s.lineno}: sentencia marcada [R] sólo en parte")
    # Alias [R]: una línea [R] cuyo destino es un nombre y cuyo valor es un nombre,
    # atributo o subíndice pelado de un objeto de Q (o de otro alias) no es un
    # nombre nuevo: es el objeto de Q con otro nombre.
    nuevos = {x.id for s in sent_r if isinstance(s, ast.Assign) for o in s.targets
              for x in (o.elts if isinstance(o, ast.Tuple) else [o]) if isinstance(x, ast.Name)}
    alias: Set[str] = set()
    cambio = True
    while cambio:
        cambio = False
        for s in sent_r:
            if not (isinstance(s, ast.Assign)
                    and isinstance(s.value, (ast.Name, ast.Attribute, ast.Subscript))):
                continue
            r = raiz(s.value)
            if r and (r not in nuevos or r in alias):
                for o in s.targets:
                    if isinstance(o, ast.Name) and o.id not in alias:
                        alias.add(o.id)
                        cambio = True
    vedados = prohibidos | alias
    for s in sent_r:
        if not isinstance(s, (ast.Assign, ast.Expr)):
            problemas.append(f"línea {s.lineno}: sentencia [R] de tipo {type(s).__name__}")
            continue
        if isinstance(s, ast.Assign):
            for o in s.targets:
                for x in (o.elts if isinstance(o, ast.Tuple) else [o]):
                    if isinstance(x, ast.Subscript) and not isinstance(x.value, ast.Name):
                        problemas.append(f"línea {s.lineno}: subíndice [R] de más de un nivel: "
                                         f"{ast.unparse(x)}")
                    r = raiz(x) if isinstance(x, ast.Subscript) else (
                        x.id if isinstance(x, ast.Name) else "")
                    if not r or isinstance(x, ast.Attribute):
                        problemas.append(f"línea {s.lineno}: destino [R] no permitido: "
                                         f"{ast.unparse(x)}")
                    elif r in prohibidos:
                        problemas.append(f"línea {s.lineno}: la línea [R] asigna a {r}, que "
                                         f"no es un nombre nuevo")
                    elif isinstance(x, ast.Subscript) and r in alias:
                        problemas.append(f"línea {s.lineno}: la línea [R] modifica {r}, alias "
                                         f"de un objeto de Q")
        else:
            c = s.value
            if not (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                    and c.func.attr == "append" and isinstance(c.func.value, ast.Name)
                    and c.func.value.id not in vedados):
                problemas.append(f"línea {s.lineno}: expresión [R] que no es append sobre un "
                                 f"nombre nuevo")
        for x in ast.walk(s):
            if isinstance(x, (ast.Lambda, ast.NamedExpr, ast.Await, ast.Yield,
                              ast.YieldFrom)):
                problemas.append(f"línea {s.lineno}: {type(x).__name__} en una línea [R]")
            elif isinstance(x, (ast.Attribute, ast.Subscript)) and isinstance(
                    x.ctx, (ast.Store, ast.Del)) and raiz(x) in prohibidos:
                problemas.append(f"línea {s.lineno}: la línea [R] modifica {ast.unparse(x)}")
            elif isinstance(x, ast.Call):
                f = x.func
                if x.keywords:
                    problemas.append(f"línea {s.lineno}: argumentos con nombre en una "
                                     f"llamada [R]: {ast.unparse(x)}")
                ok = ((isinstance(f, ast.Name) and f.id in BUILTINS_R)
                      or (isinstance(f, ast.Attribute) and f.attr in METODOS_PUROS_R)
                      or (isinstance(f, ast.Attribute) and f.attr == "append"
                          and isinstance(f.value, ast.Name) and f.value.id not in vedados))
                if not ok:
                    problemas.append(f"línea {s.lineno}: llamada no permitida en [R]: "
                                     f"{ast.unparse(f)}")
    # Entradas [R] del dict de retorno: al final, claves nuevas, valor = nombre nuevo.
    ret = fr.body[-1]
    claves_q = [k.value for k in fq.body[-1].value.keys]
    entradas_r = 0
    if isinstance(ret, ast.Return) and isinstance(ret.value, ast.Dict):
        vistas_r = False
        for k, v in zip(ret.value.keys, ret.value.values):
            if k is None:
                problemas.append(f"línea {v.lineno}: desempaque ** en el retorno")
                continue
            lineas = set(range(k.lineno, v.end_lineno + 1))
            if lineas <= marcadas:
                vistas_r = True
                entradas_r += 1
                cubiertas |= lineas
                if not (isinstance(k, ast.Constant) and isinstance(k.value, str)
                        and k.value not in claves_q):
                    problemas.append(f"línea {k.lineno}: clave [R] no nueva")
                if not (isinstance(v, ast.Name) and v.id not in vedados):
                    problemas.append(f"línea {k.lineno}: valor [R] que no es un nombre nuevo")
            elif lineas & marcadas:
                problemas.append(f"línea {k.lineno}: entrada del retorno marcada en parte")
            elif vistas_r:
                problemas.append(f"línea {k.lineno}: entrada de Q después de una [R]")
    else:
        problemas.append("correr_episodio_R no termina en `return {...}`")
    # Toda línea marcada es una sentencia [R], una entrada [R] o una marca de bloque.
    sueltas = [i for i in sorted(marcadas) if i not in cubiertas
               and lin[i - 1].strip() not in (INICIO, FIN)
               and not lin[i - 1].strip().startswith("#")]
    if sueltas:
        problemas.append(f"líneas [R] que no son sentencias completas: {sueltas[:10]}")
    detalle = f"{len(sent_r)} sentencias [R] y {entradas_r} entradas [R] del retorno"
    return problemas, detalle


# =============================================================================
# COMPROBACIÓN 4
# =============================================================================

def comprobacion_nombres(texto_r: str, texto_q: str) -> Tuple[List[str], Set[str]]:
    """Estática: un `from correr_experimento_Q import` con exactamente los libres, sin `as`,
    y ninguna otra ligadura de nivel superior de esos nombres."""
    libres = nombres_libres_Q(texto_q) - {"_MODELO"}
    arbol = ast.parse(texto_r)
    bloques = [n for n in arbol.body
               if isinstance(n, ast.ImportFrom) and n.module == "correr_experimento_Q"]
    exacto = [n for n in bloques if {(a.name, a.asname) for a in n.names}
              == {(x, None) for x in libres}]
    if not exacto:
        cercano = max(({a.name for a in n.names} for n in bloques),
                      key=lambda b: len(b & libres), default=set())
        return ([f"ninguna sentencia `from correr_experimento_Q import` tiene exactamente los "
                 f"{len(libres)} nombres libres sin `as` (faltan {sorted(libres - cercano)}, "
                 f"sobran {sorted(cercano - libres)})"], libres)
    problemas = []
    for n in arbol.body:
        if n is exacto[0]:
            continue
        dobles = sorted(ligaduras_de_nivel(n) & libres)
        if dobles:
            problemas.append(f"línea {n.lineno}: vuelve a ligar {dobles}, que son nombres "
                             f"libres de la copia")
    return problemas, libres


def identidad_en_ejecucion(libres: Set[str]) -> List[str]:
    """Importado R (sin efectos): mismos objetos que Q, _MODELO None, la función del
    def verificado y los módulos de Q cargados desde la carpeta del Exp Q."""
    if str(_CARPETA) not in sys.path:
        sys.path.insert(0, str(_CARPETA))
    import importlib
    import correr_experimento_R as R
    import correr_experimento_Q as Q
    problemas = [f"{n}: no es el mismo objeto que en Q" for n in sorted(libres)
                 if getattr(R, n, None) is not getattr(Q, n)]
    if R._MODELO is not None:
        problemas.append("_MODELO de R no es None")
    fr = funcion(ast.parse(RUTA_R.read_bytes().decode("utf-8")), "correr_episodio_R")
    if R.correr_episodio_R.__code__.co_firstlineno != fr.lineno:
        problemas.append("la correr_episodio_R cargada no es la del def verificado")
    for nombre in MODULOS_Q:
        mod = importlib.import_module(nombre)
        archivo = Path(mod.__file__).resolve()
        if _CARPETA_Q not in archivo.parents:
            problemas.append(f"{nombre} se cargó desde {archivo}, no desde la carpeta del Exp Q")
    return problemas


def comprobar(texto_r: str, texto_q: str, espacios: Set[str]) -> Dict[str, Tuple[List[str], str]]:
    """Las cuatro comprobaciones ESTÁTICAS (la identidad en ejecución va aparte)."""
    p1, d1 = comprobacion_1(texto_r, texto_q)
    p2 = comprobacion_2(texto_r, espacios)
    p3, d3 = comprobacion_3(texto_r, texto_q, espacios)
    p4, libres = comprobacion_nombres(texto_r, texto_q)
    return {"1": (p1, d1), "2": (p2, "sin redefiniciones, parches ni efectos de nivel superior"),
            "3": (p3, d3), "4": (p4, f"{len(libres)} nombres libres")}


def espacios_originales() -> Set[str]:
    return set().union(*(nombres_de_nivel((_CARPETA_Q / rel).read_text(encoding="utf-8"))
                         for rel in ORIGINALES))


def main() -> None:
    texto_r = RUTA_R.read_bytes().decode("utf-8")
    texto_q = RUTA_Q.read_bytes().decode("utf-8")
    res = comprobar(texto_r, texto_q, espacios_originales())
    libres = nombres_libres_Q(texto_q) - {"_MODELO"}
    p4 = res["4"][0] + (identidad_en_ejecucion(libres) if not res["4"][0] else [])
    import correr_experimento_R as R
    titulos = {"1": "sólo agrega registro", "2": "sólo orquesta",
               "3": "las líneas [R] sólo registran"}
    L = ["COMPARAR AST — Exp R (correr_experimento_R.py contra correr_experimento_Q.py)"]
    for k in ("1", "2", "3"):
        problemas, detalle = res[k]
        L.append(f"  comprobación {k} ({titulos[k]}): "
                 f"{'OK' if not problemas else 'NO'} — {detalle}")
        L += [f"    {p}" for p in problemas[:20]]
    L.append(f"  nombres libres: {'OK' if not p4 else 'NO'} — {res['4'][1]} importados "
             f"de correr_experimento_Q sin `as`, el mismo objeto (is); _MODELO propio = None; "
             f"función cargada = def verificado; módulos de Q desde su carpeta")
    L += [f"    {p}" for p in p4[:20]]
    for k in ("1", "2", "3"):
        L.append(f"COMPROBACIÓN {k}: {'OK' if not res[k][0] else 'NO'}")
    L.append(f"NOMBRES LIBRES: {'OK' if not p4 else 'NO'}")
    L += [f"HUELLA_Q {R.Q.huella_codigo()}", f"HUELLA_R {R.huella_R()}",
          f"SHA256 comparar_ast_R.py "
          f"{hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()}"]
    RUTA_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    if RUTA_SALIDA.exists():
        from datetime import datetime
        RUTA_SALIDA.rename(RUTA_SALIDA.with_name(
            f"{RUTA_SALIDA.stem}_respaldo_{datetime.now():%Y%m%d_%H%M%S}{RUTA_SALIDA.suffix}"))
    RUTA_SALIDA.write_bytes(("\n".join(L) + "\n").encode("utf-8"))
    for x in L:
        print(x)
    if any(res[k][0] for k in ("1", "2", "3")) or p4:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
