## Exp R — Réplica prerregistrada de los obstáculos móviles (Python, 12 celdas × 400 semillas nuevas; prerregistrado el 2026-11-09 01:38)

**Propósito.** Probar, con 400 semillas de episodio que no generaron las hipótesis (420110–420509), las hipótesis del exploratorio de S2 y S3 del Exp Q (subsección EXPLORATORIO del Exp Q, lectura corregida el 24-10).
- Abarca S1, S2 y S3 × {din, quieto, ctrl, sinvel}: 12 celdas × 400 = 4800 episodios, sin regla de parada.
- Usa el mismo código del Exp Q (huella `e265b6cd…4a29`) y la misma política.
- No cambia el veredicto del Exp Q y no toca nada del laboratorio.

**Prerregistro.** `experimentos/expR_replica_obstaculos_moviles/PREREGISTRO_R.md`, fijado el 2026-11-09 01:38 (UTC−06:00), sha256 `a4635806cd2540cd44207224de25640b5040d4be76d2d04d8250f2f06ca67cdd`. Se fijó ANTES de correr el control sobre las semillas vistas y antes de correr ninguna semilla nueva. Estado del código al fijar:
- HUELLA_R `c31f8cd6f4524804e51be7807bdd8a75e1a07885615791e251214708379f5a80`;
- `correr_experimento_R.py` `717c47a66c7c4d9cf0afa841881821e10878c1a0107596e8b4cbec9a4e4f6f39`;
- `comparar_ast_R.py` `fff0f75a3551d493b0e82b9e5dbc62fb72edc0c30bf2b2f91d33372e858f7579`;
- `analizar_experimento_R.py` `5c2e8c3a6be93a71d49083e44fb673a848daa8126045067bdb70b327dab47f3e`;
- `potencia_R.py` `cc68d0699fef9a320cadc527a2a2e6f00372ecbc55496255c2c0c497903982ae`;
- `test_experimento_R.py` `269d543d1fc3e2783ffba010a073097daa426461aa3d2372979239dd7a8ea34b`;
- 48 pruebas en verde y las cuatro comprobaciones de `comparar_ast_R.py` en OK.

**Nota sobre el correo (D5).** El §5 del prerregistro preveía mandar su sha256 por correo al asesor, como sello de fecha fuera de la PC. No se mandó: el 09-11 José decidió dejarlo como nota y no como paso del proceso. Tampoco se manda el de la adenda 1, aunque su §7 nombre el correo. La fecha la respaldan los registros del control (09:55) y de la pasabilidad (10:39), que llevan el sha256 del prerregistro, los sha256 de esta entrada y, cuando se haga, el manifiesto pre.

**Hipótesis** (α = 0,05 bilateral sin ajuste; Holm sobre las 7 McNemar direccionales, sólo como sensibilidad):
- H1, el encierro aparece con el movimiento: fallback, din > quieto. S3 primaria, S2 secundaria;
- H2, el término de velocidad conserva margen: bajo 0,13 m, sinvel > din. S2 y S3 primarias;
- H3a, los agotados de S3 son del obstáculo: din > ctrl. Primaria;
- H3b, el movimiento agrega agotados en S3: din > quieto. Secundaria; pasó de nula a direccional antes de correr, §2.3 del prerregistro;
- H4, en S3 el efecto del obstáculo móvil (din − ctrl) sobre la cobertura accesible es menor, con signo, que en S1 y en S2. Secundaria, compuesta;
- H5a, cero contactos con F1 en los tres niveles. Primaria;
- H5b, el término de velocidad reduce los contactos en S3. Secundaria;
- H6a y H6b, la Parte B: acercamientos bajo 0,10 m en, o fuera de, la ventana de 5 decisiones de un fallback. Secundarias y descriptivas.

**El código.**
- `correr_episodio_R` es una copia textual de `correr_episodio_Q` con 11 líneas `# [R]` que sólo registran. Importa explícitamente sus 37 nombres libres, sin `import *`.
- `comparar_ast_R.py` certifica el cuerpo de la copia y la identidad de esos nombres.
- La prueba física del pareo decisión/distancia es `fb_desplazado` = 0: con u = (0, 0), un agente sin contacto nuevo no se mueve.
- La revisión adversarial de sólo lectura del 26-10 corrigió el código y el prerregistro antes de fijarlo. El §0 del prerregistro la menciona y enumera las precisiones de José del 09-11.

**Control y pasabilidad (09-11).** Los dos corrieron enchufados, dentro del horario activo de Windows y sin laboratorio ni réplica de la campaña. El chequeo de congelados dio "IGUAL a lo probado" al empezar y al terminar.
- **Control, 09:55:12–10:07:08: «CONTROL: OK» y «PARTE B: OK».** 1200 episodios distintos (semillas vistas 420000–420099). Son idénticas en texto, en las 66 columnas del Exp Q, 400/400 filas de S1 y 800/800 de S2 y S3. 1100 se reprodujeron por primera vez, entre ellos los 11 de S3_sinvel que pasaron por la suspensión del 19-10. Los autochequeos de la Parte B dieron 0 problemas, y las 11 trazas están en biyección con sus filas. `resultados/control_bit_a_bit_R.txt`, sha256 `c5ffcf9a14afd49d7c26e6b7fff1eb6a9956a34e4e5fc824802c1b6e4261dbab`.
- **Pasabilidad, 10:39:41–10:58:26: «PASABILIDAD: OK».** S1, S2 y S3 sin fallos en 200 400 instantes cada uno (400 semillas nuevas × 501 instantes). El hueco más chico en las semillas es el analítico: 0,60 m en S1 (pared), 0,5142 m en S2 (entre obstáculos; a la pared, 0,55 m) y 0,49 m en S3 (pared; entre obstáculos, 0,4907 m), contra un umbral de 0,48 m. En S3 queda 1 cm de margen, como en el Exp Q. Sólo mira la geometría de los obstáculos, sin correr episodios. `resultados/pasabilidad_R.txt`, sha256 `eb268ca8cc140e7ee849d61ded5ffc0ea626576cfc1d433b06b420c541b574ce`.
- **Prueba del análisis sobre el control, 11:00.** El pipeline completo corrió sin errores. El resumen es idéntico a la prueba sobre los CSV del Exp Q salvo el modo, la línea del prerregistro, la H6 (sólo evaluable con la Parte B) y la lista de figuras. Las figuras comunes son iguales byte a byte.
- **Verificación independiente, de sólo lectura** (revisores automáticos; sus scripts quedaron fuera del proyecto, y las cifras se recalculan desde los crudos).
  - Control, cinco revisores: 79 200 celdas comparadas como texto, con 0 diferencias. `t_episodio_s` difiere en 1200/1200 filas, así que se recalculó y no se copió. La Parte B recalculada desde las 11 trazas coincide, y las firmas de los parciales también.
  - Pasabilidad, dos revisores: 18 semillas recalculadas, sin fallos y dentro de los rangos del registro. El criterio es, sentencia por sentencia, el de `Q.pasabilidad`.

**Adenda 1, desviación declarada (09-11).** `ADENDA_PREREGISTRO_R_20261109.md`, fijada el 2026-11-09 17:54 (UTC−06:00), sha256 `8dcddafdc9c4a885e0a627d9fa5806edd58709869a9e83010425f7369c5b01df`.
- **Antes.** Los prefijos con que la sección VERIFICACIÓN de `resumen_R.txt` copia los registros no tomaban todas las verificaciones al empezar y al terminar que pide el §4. Faltaban las copias del Exp O, los IGUAL de los crudos, «AL TERMINAR», las huellas del control y del experimento, y casi todo el bloque de la pasabilidad. Sobre los registros reales tomaban 24 de 42 líneas del control y 5 de 39 de la pasabilidad. `analizar_experimento_R.py` `5c2e8c3a…`, `test_experimento_R.py` `269d543d…`, 48 pruebas.
- **Después.** Toman 42 de 42 y 39 de 39, y no se cuela ninguna línea de resultados. `analizar_experimento_R.py` `ab0500cd363f7766b12326c6d0ce24693a68345131767e459a117e73a2349183` y `test_experimento_R.py` `7ae0a7f86c4be3e0f1d48d31d344746ad03d5ef1e21f2db2a2e541e3cd802a61`, que agrega `PruebaVerificacion`; 50 pruebas en verde. Respaldos de lo fijado: `*_respaldo_20261109_prePrefijos.py`.
- **Qué no cambia.** `correr_experimento_R.py`, `comparar_ast_R.py`, `potencia_R.py` y las huellas: el control y la pasabilidad siguen valiendo. Tampoco cambian las hipótesis, las semillas, la estadística, las reglas de lectura ni las figuras. Se aprobó y se fijó antes del manifiesto pre y antes de correr ningún episodio con las semillas nuevas.
- **Diff de `analizar_experimento_R.py`.** El de las pruebas, que sólo agrega la clase, está en el §6 de la adenda.

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

**Aclaraciones.**
- Las semillas 420100–420109 las usó la Fase 0 del obstáculo móvil (02-10) y se dejaron afuera.
- `tesis/PROTOCOLO_L0_L2.md:71`: desde el 09-11, el chequeo previo de la PC del laboratorio busca también los scripts de R (`correr_experimento_R`, `analizar_experimento_R`, `comparar_ast_R`, `potencia_R`, `test_experimento_R`), para que la exclusión con R sea simétrica. Respaldo: `PROTOCOLO_L0_L2_respaldo_20261109_preFiltroExpR.md`. Sólo cambió esa línea. El protocolo no está entre los congelados, y el chequeo de congelados siguió en "IGUAL a lo probado".
- La corrección de "con la PC libre", en la línea de costo del exploratorio (entrada del Exp Q, arriba), se hace sólo en esta bitácora. `expQ_obstaculos_moviles/ENTRADA_BITACORA_expQ_EXPLORATORIO.md` está congelado en el manifiesto del Exp Q y en la referencia del árbol del Exp R, y conserva el texto original.
- El §3.2 del prerregistro (línea 160) nombra como «semillas vistas con contacto» sólo S3_sinvel 420013 y 420090. La 420057 también tiene contacto (2 eventos). Ahí las dos reglas del mínimo coinciden, así que lo que dice esa línea no cambia. El prerregistro no se edita.
- Dos detalles de los registros de R, que vienen del código de corrida fijado y no cambian lo que se verifica:
  - al terminar, la línea «RESULTADOS DEL EXP Q sin cambios» aparece sin su lista: el chequeo corre y para la corrida si algún archivo difiere, pero no reimprime las líneas IGUAL;
  - «PASABILIDAD: OK» va al registro y no al log del tramo.

**Sigue:** `verificar_cifras_R.py` (núcleo), el manifiesto pre y el experimento (§5 del prerregistro). Los resultados irán en su propia subsección, al cierre.

---

<!-- ANEXO (no va a la bitácora): la línea de costo del exploratorio, bitácora:2935, reemplazada el 2026-11-09 en la misma pasada que insertó esta entrada. -->
<!-- Texto anterior:
**Costo:** la corrida, 28.6 min de máquina (20:22–20:51 del 19-10, con la PC libre), de los que 185 s fueron la reproducción de S1_din. La corrección del 24-10 no corrió episodios.
-->
<!-- Texto nuevo:
**Costo:** la corrida, 28.6 min de reloj (20:22–20:51 del 19-10), de los que 185 s fueron la reproducción de S1_din. **Corrección del 2026-11-09: no fue "con la PC libre", como decía esta línea, que además decía "de máquina" en lugar de "de reloj".** La PC estaba a batería desde las 19:53:37 (Kernel-Power 105) y se suspendió por batería crítica de 20:41:30 a 20:50:10 (visor de eventos de Windows: Kernel-Power 524 y 42 al entrar; al volver, Kernel-General 1 ajustó el reloj en 517 s). Eso explica que 11 episodios de S3_sinvel (420033–420043) tardaran ≈ 530 s cada uno y que esa celda tardara 631 s. El cálculo es determinista: la suspensión no cambia ningún resultado, y el control del Exp R reprodujo esos episodios bit a bit (ver su entrada, abajo). La corrección del 24-10 no corrió episodios.
-->
