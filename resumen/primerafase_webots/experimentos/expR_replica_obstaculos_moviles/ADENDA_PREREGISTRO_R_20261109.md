# Adenda 1 al prerregistro del Exp R — sección VERIFICACIÓN del resumen

Fijada: 2026-11-09 17:54

**Prerregistro.** `PREREGISTRO_R.md`, sha256 `a4635806cd2540cd44207224de25640b5040d4be76d2d04d8250f2f06ca67cdd` (Fijado: 2026-11-09 01:38). El prerregistro no se edita.
- Todo cambio posterior al código que fija es una desviación declarada con diff (§4).
- Se declara en la bitácora con el antes, el después y el diff (§7).
- Según el encabezado del prerregistro, va en un archivo aparte, con el sha256 del original y el suyo. Este es ese archivo; dónde queda su propio sha256 lo dice el §7 de esta adenda.

## 1. Cuándo

Cronología del 09-11 (hora local, UTC−06:00):
- **01:38** — se fija el prerregistro.
- **09:55–10:07** — control: «CONTROL: OK» y «PARTE B: OK».
- **10:39–10:58** — pasabilidad: «PASABILIDAD: OK».
- **11:00** — prueba del análisis sobre el control (`--prueba-control`), con el código fijado.
- José aprueba el cambio; a las **13:17** se modifica el código.
- **13:22** — se regeneran las dos pruebas del análisis.
- **17:54** — se fija esta adenda.

El faltante lo encontró la verificación independiente del registro del control, hecha después del control contra el §4 del prerregistro. Se declara en la bitácora junto con esta adenda.

Todo esto es ANTERIOR al manifiesto pre y al experimento. Con las semillas nuevas 420110–420509 no se corrió ningún episodio, y nadie vio ningún evento de los agentes ni ninguna cifra de las hipótesis. De esas semillas sólo se vio la geometría de la pasabilidad (`pasabilidad_R.txt`). Sí se vieron los resultados del control, pero son sobre las semillas ya vistas 420000–420099.

## 2. Qué faltaba

El §4 fija las secciones de `resumen_R.txt`. La 3 es «VERIFICACIÓN (líneas de `comparar_ast_R.txt`, `control_bit_a_bit_R.txt`, `pasabilidad_R.txt` y `registro_R.txt`, incluidas las verificaciones al empezar y al terminar)». El código fijado no las tomaba todas:
- **En los tres registros de corrida** faltaban:
  - las copias del Exp O: el encabezado y sus 7 líneas IGUAL;
  - las 6 líneas IGUAL de los crudos del Exp Q;
  - «AL TERMINAR:» y «copias del Exp O iguales».
- **En el control** faltaban además las firmas HUELLA_Q y HUELLA_R, que son las huellas al terminar.
- **En `registro_R.txt`** faltaban además las dos huellas al empezar: «huella del Exp Q: …» y «huella de R: …».
- **En la pasabilidad** faltaba casi todo el bloque: inicio, huellas, entorno, procesos, copias, stack, crudos, árbol, energía, reinicio y fin.

Se cuentan como «líneas de inicio y fin» las que van desde «inicio» hasta «congelados … al empezar», y desde «AL TERMINAR:» hasta el final, con veredictos y firmas incluidos (es la definición de `test_registros_reales`). Sobre los registros reales, el código fijado tomaba 24 de las 42 líneas del control y 5 de las 39 de la pasabilidad.

## 3. Qué cambia

Sólo qué líneas de los registros se copian a VERIFICACIÓN en modo resultado.
- **`analizar_experimento_R.py`.** La tupla nueva `VERIFICACION_INICIO_FIN` reúne los comienzos de las líneas que escriben `previos_R` y `finales_R` y de las firmas, y se suma a los prefijos propios de cada registro de corrida. Los prefijos de antes se conservan o quedan cubiertos: «HUELLA_» cubre «HUELLA_Q» y «HUELLA_R». Ninguna línea que antes se copiaba deja de copiarse. `seccion_verificacion` recibe la carpeta como argumento, con la de siempre por defecto, para poder probarla. Por AST, fuera de `VERIFICACION_INICIO_FIN`, `PREFIJOS_VERIFICACION` y `seccion_verificacion`, el archivo es idéntico al fijado.
- **`test_experimento_R.py`.** Se agrega `PruebaVerificacion`, con dos pruebas:
  - con registros sintéticos de las tres corridas, cada línea de inicio y de fin llega a VERIFICACIÓN, y una línea de resultados no llega;
  - con los registros reales del control y de la pasabilidad, llegan 42 de 42 y 39 de 39.

  Con los prefijos fijados, las dos pruebas fallan.

## 4. Qué no cambia

- **Código de corrida y huellas.** `correr_experimento_R.py`, `comparar_ast_R.py` y `potencia_R.py` conservan su sha256, y HUELLA_Q y HUELLA_R siguen iguales. Ninguna compuerta de `experimento` mira el sha256 de `analizar_experimento_R.py` ni el de `test_experimento_R.py`, salvo el manifiesto pre, que todavía no se hizo. Por eso el control (HUELLA_R, prerregistro, intérprete), la pasabilidad (HUELLA_Q, SEMILLAS_R, prerregistro) y `comparar_ast_R.txt` siguen valiendo.
- **Diseño y lectura.** No cambian las hipótesis, las celdas, las semillas, la estadística, las reglas de lectura, la Parte B ni las figuras. A los efectos del §2.4, el script de análisis prerregistrado pasa a ser el de esta adenda (`ab0500cd…`), que va al manifiesto pre. Como sólo difiere del fijado (`5c2e8c3a…`) en esas tres piezas, las palabras de los veredictos no dependen de cuál se tome.
- **Salidas de los modos de prueba.** En esos modos VERIFICACIÓN dice «no aplica», así que esta adenda no cambia sus salidas. Se regeneraron igual a las 13:22, porque la prueba sobre Q todavía llevaba el sha256 del prerregistro en BORRADOR (`36c9db7a…`):
  - `resumen_R_prueba_sobre_control.txt`: sha256 `0aa88d13e687a9d462adfed63248ba432a3a08b6dc222753733208b2337a2cf5`, igual al de las 11:00 (`resumen_R_prueba_sobre_control_respaldo_20261109_132216.txt`);
  - `resumen_R_prueba_sobre_Q.txt`: sha256 `db63b1c6ee79751b03b6b12f7dd8bd74a3244b7214a03480abf9e6722294a6a2`; frente a `…_respaldo_20261109_132209.txt` sólo cambió la línea del prerregistro.
- **Figuras.** Tienen los mismos sha256 que antes de regenerarlas:
  - costo: `cb64861eaaa5550c273b0fee1a1db040a75e9a1514a847245d90e2ec5b8185bb`, sobre Q y sobre el control;
  - intervención: `ad32962a268edc63cc2ccccd9a97ddca8ed78c73fa5fef9b36a5c677af33c2ff`, sobre Q y sobre el control;
  - fallback_distancia: `6b4ed7aeebd668be3c24bfd28057990ba7037ad7ca203cddc5e10f851f17bd1d`, sólo sobre el control.
- **Lo que no está en los registros.** VERIFICACIÓN copia lo que está en los registros. La compuerta de energía antes de cada celda y los tiempos quedan en los logs `corrida_R_*.log`, como hasta ahora. A VERIFICACIÓN llegan a través de la línea «logs de los tramos».

## 5. Estado del código con esta adenda

| Archivo | Al fijar el prerregistro | Con esta adenda |
|---|---|---|
| `analizar_experimento_R.py` | `5c2e8c3a6be93a71d49083e44fb673a848daa8126045067bdb70b327dab47f3e` | `ab0500cd363f7766b12326c6d0ce24693a68345131767e459a117e73a2349183` |
| `test_experimento_R.py` | `269d543d1fc3e2783ffba010a073097daa426461aa3d2372979239dd7a8ea34b` | `7ae0a7f86c4be3e0f1d48d31d344746ad03d5ef1e21f2db2a2e541e3cd802a61` |
| `correr_experimento_R.py` | `717c47a66c7c4d9cf0afa841881821e10878c1a0107596e8b4cbec9a4e4f6f39` | igual |
| `comparar_ast_R.py` | `fff0f75a3551d493b0e82b9e5dbc62fb72edc0c30bf2b2f91d33372e858f7579` | igual |
| `potencia_R.py` | `cc68d0699fef9a320cadc527a2a2e6f00372ecbc55496255c2c0c497903982ae` | igual |
| HUELLA_R | `c31f8cd6f4524804e51be7807bdd8a75e1a07885615791e251214708379f5a80` | igual |

- 50 pruebas en verde (antes eran 48).
- Respaldos de lo fijado, con los sha256 de la columna del medio:
  - `analizar_experimento_R_respaldo_20261109_prePrefijos.py`;
  - `test_experimento_R_respaldo_20261109_prePrefijos.py`.

## 6. Diff

```diff
--- analizar_experimento_R.py (al fijar, 5c2e8c3a…)
+++ analizar_experimento_R.py (adenda)
@@ -452,30 +452,35 @@
     return L
 
 
+#: Las verificaciones al empezar y al terminar (`previos_R` y `finales_R` de
+#: correr_experimento_R.py) y las firmas, comunes a los registros de las tres
+#: corridas: el §4 del prerregistro las pide todas en VERIFICACIÓN (adenda del
+#: 09-11: faltaban las copias del Exp O, «AL TERMINAR» y, en la pasabilidad,
+#: casi todo el bloque).
+VERIFICACION_INICIO_FIN: Tuple[str, ...] = (
+    "inicio", "huella", "HUELLA_", "ENTORNO_R", "procesos", "PREREGISTRO_R.md", "COPIAS",
+    "IGUAL", "STACK", "RESULTADOS DEL EXP Q", "ÁRBOL", "energía", "sin reinicio",
+    "congelados", "AL TERMINAR", "copias del Exp O", "manifiesto", "fin")
+
 #: Las líneas de cada registro que pasan a VERIFICACIÓN (por su comienzo).
 PREFIJOS_VERIFICACION: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
     ("comparar_ast_R.txt", ("COMPROBACIÓN", "NOMBRES LIBRES", "HUELLA_R")),
-    ("control_bit_a_bit_R.txt", ("inicio", "huella", "ENTORNO_R", "PREREGISTRO_R.md",
-                                 "ÁRBOL", "RESULTADOS DEL EXP Q", "STACK", "procesos",
-                                 "energía", "sin reinicio", "congelados", "CONTROL",
-                                 "de los 1200", "AUTOCHEQUEOS", "la prueba física", "TRAZAS",
-                                 "PARTE B", "fin")),
-    ("pasabilidad_R.txt", ("S1:", "S2:", "S3:", "PASABILIDAD:", "SEMILLAS_R",
-                           "PREREGISTRO_R.md", "congelados")),
-    ("registro_R.txt", ("PRERREGISTRADO", "inicio", "PREREGISTRO_R.md", "manifiesto",
-                        "semillas", "modo", "ENTORNO_R", "ÁRBOL", "RESULTADOS DEL EXP Q",
-                        "STACK", "procesos", "energía", "sin reinicio", "congelados",
-                        "AUTOCHEQUEOS", "la prueba física", "TRAZAS", "FILAS", "PARTE B",
-                        "logs de los tramos", "fin", "HUELLA_Q", "HUELLA_R")),
+    ("control_bit_a_bit_R.txt", VERIFICACION_INICIO_FIN + (
+        "CONTROL", "de los 1200", "AUTOCHEQUEOS", "la prueba física", "TRAZAS", "PARTE B")),
+    ("pasabilidad_R.txt", VERIFICACION_INICIO_FIN + (
+        "S1:", "S2:", "S3:", "PASABILIDAD:", "SEMILLAS_R")),
+    ("registro_R.txt", VERIFICACION_INICIO_FIN + (
+        "PRERREGISTRADO", "semillas", "modo", "AUTOCHEQUEOS", "la prueba física", "TRAZAS",
+        "FILAS", "PARTE B", "logs de los tramos")),
 )
 
 
-def seccion_verificacion(modo: str) -> List[str]:
+def seccion_verificacion(modo: str, dir_res: Path = DIR_RES) -> List[str]:
     if modo != "resultado":
         return ["VERIFICACIÓN — no aplica (prueba del análisis sobre datos vistos)"]
     L = ["VERIFICACIÓN (de los registros de la corrida)"]
     for nombre, prefijos in PREFIJOS_VERIFICACION:
-        ruta = DIR_RES / nombre
+        ruta = dir_res / nombre
         if not ruta.exists():
             L.append(f"  falta {nombre}")
             continue
```

```diff
--- test_experimento_R.py (al fijar, 269d543d…)
+++ test_experimento_R.py (adenda)
@@ -483,6 +483,73 @@
             self.assertTrue(all((Path(d) / "fig" / h).exists() for h in hechas))
 
 
+class PruebaVerificacion(unittest.TestCase):
+    """VERIFICACIÓN del resumen: todas las verificaciones al empezar y al terminar
+    de los tres registros (§4 del prerregistro; adenda del 09-11)."""
+
+    INICIO = [
+        "inicio 2026-11-09 09:55:12",
+        "huella del Exp Q: e265 (la de S1 y el exploratorio)",
+        "huella de R: c31f",
+        "ENTORNO_R python 3.13.14 | Intel64",
+        "procesos de trabajo: 11; -B sí",
+        "PREREGISTRO_R.md sha256 a463 (Fijado: 2026-11-09 01:38)",
+        "COPIAS del Exp O (copia = esperado = original):",
+        "  IGUAL 65d6 lib/__init__.py",
+        "STACK: torch 2.10.0 — igual a requisitos_congelados_2026-09-09",
+        "RESULTADOS DEL EXP Q sin cambios (S1 y crudos exploratorios):",
+        "  IGUAL ff55 resultados/registro_Q.txt",
+        "ÁRBOL DEL EXP Q igual a la referencia: 97 archivos",
+        "procesos: ninguna otra corrida, ni scripts del coordinador, ni MATLAB/Webots",
+        "energía: enchufada, batería 100 %",
+        "sin reinicio pendiente de Windows",
+        "congelados de la campaña al empezar (PROTOCOLO_L0_L2.md:210): IGUAL a lo probado"]
+    FIN = [
+        "AL TERMINAR:",
+        "  copias del Exp O iguales",
+        "  STACK: torch 2.10.0 — igual a requisitos_congelados_2026-09-09",
+        "  RESULTADOS DEL EXP Q sin cambios (S1 y crudos exploratorios):",
+        "  ÁRBOL DEL EXP Q igual a la referencia: 97 archivos",
+        "  congelados de la campaña al terminar: IGUAL a lo probado",
+        "  procesos: ninguna otra corrida, ni scripts del coordinador, ni MATLAB/Webots",
+        "  energía: enchufada, batería 100 %",
+        "  manifiesto pre: todas sus entradas con el sha256 actual",
+        "  fin 2026-11-09 10:07:08",
+        "HUELLA_Q e265",
+        "HUELLA_R c31f"]
+
+    def test_inicio_y_fin_en_los_tres_registros(self) -> None:
+        resultado = "S1_din: cob_acc=0.59930086 interv=0.547856 t/ep=5.46 s; criterios — x 0"
+        registros = {
+            "control_bit_a_bit_R.txt": ["CONTROL — Exp R"] + self.INICIO + ["CONTROL: OK"]
+            + self.FIN,
+            "pasabilidad_R.txt": ["PASABILIDAD — Exp R"] + self.INICIO
+            + ["  S1: peor caso → PASABLE", "PASABILIDAD: OK"] + self.FIN,
+            "registro_R.txt": [R.ENCABEZADO_R] + self.INICIO + [resultado] + self.FIN}
+        with tempfile.TemporaryDirectory() as d:
+            for nombre, lineas in registros.items():
+                (Path(d) / nombre).write_bytes(("\n".join(lineas) + "\n").encode("utf-8"))
+            L = A.seccion_verificacion("resultado", Path(d))
+        for nombre in registros:
+            for x in self.INICIO + self.FIN:
+                self.assertIn(f"  {nombre}: {x.strip()}", L, (nombre, x))
+        self.assertFalse(any(resultado in x for x in L))
+        self.assertIn("  falta comparar_ast_R.txt", L)
+
+    @unittest.skipUnless((A.DIR_RES / "control_bit_a_bit_R.txt").exists()
+                         and (A.DIR_RES / "pasabilidad_R.txt").exists(),
+                         "faltan los registros del control y de la pasabilidad")
+    def test_registros_reales(self) -> None:
+        L = A.seccion_verificacion("resultado")
+        for nombre in ("control_bit_a_bit_R.txt", "pasabilidad_R.txt"):
+            lineas = [x.strip() for x in
+                      (A.DIR_RES / nombre).read_text(encoding="utf-8").splitlines()]
+            fin_inicio = next(i for i, x in enumerate(lineas)
+                              if x.startswith("congelados de la campaña al empezar"))
+            esperadas = lineas[1:fin_inicio + 1] + lineas[lineas.index("AL TERMINAR:"):]
+            self.assertEqual([x for x in esperadas if f"  {nombre}: {x}" not in L], [], nombre)
+
+
 class PruebaCompuertaExperimento(unittest.TestCase):
 
     def test_lineas_parte_b(self) -> None:
```

## 7. Fijación y registro de esta adenda

Se fija escribiendo la fecha y la hora en la línea «Fijada:», y en ese momento se imprime su sha256. Un archivo no puede contener su propio sha256, así que el de esta adenda queda en tres lugares:
- en la entrada del Exp R en la bitácora, junto al del prerregistro y con el antes, el después y el diff (§7 del prerregistro);
- en el correo al asesor;
- en el manifiesto pre, que toma todos los archivos de la carpeta.

Se fija antes del manifiesto pre. Después del manifiesto no se edita ningún archivo de la carpeta, ni durante el experimento.
