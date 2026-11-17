# Exp R — panorama al 9 de noviembre de 2026

Foto del estado del Exp R al 09-11, poco después de las 18:00. Reúne qué es, de dónde viene, qué se hizo, qué salió, qué falta y la pregunta pendiente (al final, §10).

> Este archivo está en la carpeta del Exp R y va a quedar dentro del manifiesto pre. Después del manifiesto no se edita: si cambia, el experimento se niega a correr.

---

## 1. Qué es el Exp R

Es una **réplica prerregistrada** de las hipótesis que salieron del análisis exploratorio de S2 y S3 del Exp Q (obstáculos móviles). Las pone a prueba con **400 semillas de episodio nuevas (420110–420509)**, que no participaron en generar esas hipótesis.

- **Celdas.** Corre los niveles S1, S2 y S3 en cuatro condiciones cada uno, din, quieto, ctrl y sinvel: 12 celdas × 400 = **4800 episodios**, sin regla de parada.
- **Código y política.** Son los del Exp Q (huella `e265b6cd…4a29`, `modelo_sanidad`). No cambia la política, el filtro CBF, el escape ni el entorno.
- **Lo que no hace.** No reabre el Exp Q, cuyo veredicto queda igual: S1 detiene por la regla del Exp O. Tampoco toca nada del laboratorio.
- **Alcance.** Las semillas nuevas cambian las poses, los objetivos y las fases de los obstáculos, no el entrenamiento. No es una réplica con otros entrenamientos ni una verificación independiente del código.

## 2. De dónde viene

1. **Exp Q.** Con la regla de parada del Exp O, S1 disparó la parada y S2 y S3 no se corrieron dentro de la regla.
2. **Exploratorio del Exp Q (19-10, lectura corregida el 24-10).** S2 y S3 se corrieron fuera de la regla, como exploración, con las semillas 420000–420099. De ahí salieron lecturas como:
   - en S3, los acercamientos bajo 0,10 m caen en episodios con fallback del QP;
   - los agotados son del obstáculo, no del movimiento;
   - el término de velocidad conserva margen.

   Eran observaciones, no pruebas: las mismas semillas que sugirieron las hipótesis no pueden confirmarlas.
3. **Spec del Exp R (José, 24-10)** y plan con las decisiones **D1–D7**, aprobado el 24-10.
4. **Exp R.** Las mismas hipótesis, escritas y fijadas ANTES de mirar semillas nuevas, se prueban con semillas nuevas.

## 3. Cómo está armado

### Hipótesis (fijadas en el §2.3 del prerregistro)

| Id | Qué dice | Prueba | Clase |
|---|---|---|---|
| H1 | El encierro (fallback del QP) aparece con el movimiento | McNemar, din > quieto | S3 primaria, S2 secundaria |
| H2 | El término de velocidad conserva margen | McNemar sobre episodios bajo 0,13 m, sinvel > din | S2 y S3 primarias |
| H3a | Los agotados de S3 son del obstáculo | McNemar, din > ctrl | primaria |
| H3b | El movimiento agrega agotados en S3 | McNemar, din > quieto | secundaria |
| H4 | En S3 el efecto del obstáculo móvil (din − ctrl) sobre la cobertura accesible es menor, con signo, que en S1 y en S2 | Δ pareadas con IC95 | secundaria, compuesta |
| H5a | Cero contactos con F1 en los tres niveles | Clopper-Pearson (0/400 → cota de 0,918 %) | primaria |
| H5b | El término de velocidad reduce los contactos en S3 | McNemar, sinvel > din | secundaria |
| H6a / H6b | Los acercamientos bajo 0,10 m ocurren en, o justo después de, un fallback del agente (ventana de 5 decisiones), y fuera de esa ventana ningún agente baja de 0,10 m | Parte B, descriptiva | secundarias |

- α = 0,05 bilateral, sin ajuste.
- Holm sobre las 7 McNemar, sólo como sensibilidad.
- En S1, H1 y H2 son descriptivas.
- **Lectura de H5a** (decisión de José): con k ≥ 1 se reporta la tasa k/400 con su IC y se discute con la traza de cada episodio. No se lee como "el filtro falla", porque con una tasa pequeña pero no nula, "no cumplida" es el resultado probable aunque el filtro funcione (potencia ≈ 0,09).

### La "Parte B"

Son columnas nuevas que registran, por agente y por paso, si el acercamiento mínimo al obstáculo cae dentro de la ventana de un fallback. El episodio en sí no se modifica:
- `correr_episodio_R` es una copia textual de `correr_episodio_Q` con 11 líneas `# [R]` que sólo registran;
- `comparar_ast_R.py` certifica, con cuatro comprobaciones, que la copia es idéntica y que esas líneas no cambian nada.

### Compuertas (cada corrida larga las exige)

- **Al empezar:**
  - prerregistro fijado;
  - huellas, copias del Exp O, stack y crudos del Exp Q intactos;
  - árbol del Exp Q igual a su referencia (97 archivos);
  - ningún otro proceso de corrida ni del laboratorio;
  - PC enchufada, también antes de cada celda;
  - sin reinicio pendiente;
  - congelados de la campaña en "IGUAL a lo probado".
- **Al terminar:** se repiten esas comprobaciones.
- **La exclusión con el laboratorio es simétrica.** El chequeo previo del laboratorio (`PROTOCOLO_L0_L2.md:71`) busca también los scripts de R.

## 4. Qué se hizo, en orden

| Fecha | Qué |
|---|---|
| 24-10 | Spec de José, plan con D1–D7 aprobado, referencia del árbol del Exp Q (97 archivos) |
| 26-10 | Revisión adversarial de sólo lectura del código y del prerregistro, con correcciones; comparador; cálculo de potencia |
| 09-11, 01:36 | `PROTOCOLO_L0_L2.md:71`: el filtro del laboratorio busca también los scripts de R (con respaldo) |
| 09-11, 01:38 | **Prerregistro fijado** con tus cinco precisiones (regla del mínimo, «PARTE B: NO», lectura de H5a, sha256 en los registros, filtro simétrico) |
| 09-11, 09:55–10:07 | **Control: OK** |
| 09-11, 10:39–10:58 | **Pasabilidad: OK** |
| 09-11, 11:00 | Prueba del análisis sobre el control |
| 09-11, 13:17–17:54 | **Adenda 1** (prefijos de VERIFICACIÓN): código, pruebas, revisión y fijación |
| 09-11, tarde | **Bitácora** en una pasada, revisada |

Cada paso importante lo verificaron revisores automáticos independientes, de sólo lectura, que recalcularon desde los datos crudos sin usar el código de R.

## 5. Resultados de hoy (todos sobre semillas ya vistas o sobre geometría: ninguno es resultado de R)

**Control** (`resultados/control_bit_a_bit_R.txt`):
- Se recorrieron con el código de R los 1200 episodios ya corridos por el Exp Q (semillas 420000–420099).
- **400/400** filas de S1 y **800/800** de S2 y S3 salieron idénticas en texto en las 66 columnas del Exp Q. La verificación independiente comparó 79 200 celdas y encontró 0 diferencias.
- 1100 de esos episodios se reprodujeron por primera vez, entre ellos los 11 de S3_sinvel que habían pasado por la suspensión de la PC del 19-10.
- **PARTE B: OK.** Los autochequeos dieron 0 problemas, y las 11 trazas están en biyección con sus filas.

**Pasabilidad** (`resultados/pasabilidad_R.txt`):
- Con las 400 semillas nuevas, la arena sigue siendo pasable en los 501 instantes de cada trayectoria de obstáculos: **0 fallos** en 200 400 instantes por nivel.
- El hueco más chico es el analítico: 0,60 m en S1, 0,5142 m en S2 y 0,49 m en S3, contra un umbral de 0,48 m. S3 queda con 1 cm de margen, igual que en el Exp Q.
- Sólo mira la geometría de los obstáculos: no corre ningún episodio.

**Prueba del análisis sobre el control** (`resultados/resumen_R_prueba_sobre_control.txt`):
- El pipeline completo corre sin errores.
- Sale idéntica a la prueba sobre los CSV del Exp Q, salvo en lo que tiene que diferir: la H6, que sólo se puede evaluar con la Parte B.

## 6. Decisiones tuyas que están aplicadas

- Las cinco precisiones del 09-11 están en el prerregistro, y su sha256 en los registros del control y de la pasabilidad.
- **Cambio en `PROTOCOLO_L0_L2.md:71`.** Sólo se agregaron los scripts de R al filtro, con respaldo con fecha.
- **"Correlo ahora"** fue tu "listo" para el control, y **"Sí, lanzala"** para la pasabilidad.
- **Adenda 1.** La sección VERIFICACIÓN del resumen no tomaba todas las verificaciones al empezar y al terminar que pide el §4. Se corrigió como desviación declarada, con diff. Pasó de 24/42 a 42/42 líneas en el control y de 5/39 a 39/39 en la pasabilidad. No cambia el código de corrida, las huellas, las hipótesis ni la estadística, así que el control y la pasabilidad siguen valiendo.
- **Correo D5.** El sha256 no se mandó por correo. Lo decidiste el 09-11, y quedó como nota en la bitácora, no como paso del proceso.
- **Bitácora en una sola pasada.** Lleva la entrada del Exp R, la corrección de "con la PC libre" en la línea de costo del exploratorio del Exp Q y la precisión de la semilla S3_sinvel 420057.

## 7. Archivos clave

| Archivo | sha256 | Estado |
|---|---|---|
| `PREREGISTRO_R.md` | `a4635806cd2540cd44207224de25640b5040d4be76d2d04d8250f2f06ca67cdd` | fijado 09-11 01:38; no se edita |
| `ADENDA_PREREGISTRO_R_20261109.md` | `8dcddafdc9c4a885e0a627d9fa5806edd58709869a9e83010425f7369c5b01df` | fijada 09-11 17:54; no se edita |
| `correr_experimento_R.py` | `717c47a66c7c4d9cf0afa841881821e10878c1a0107596e8b4cbec9a4e4f6f39` | sin cambios desde que se fijó |
| `analizar_experimento_R.py` | `ab0500cd363f7766b12326c6d0ce24693a68345131767e459a117e73a2349183` | versión de la adenda |
| `test_experimento_R.py` | `7ae0a7f86c4be3e0f1d48d31d344746ad03d5ef1e21f2db2a2e541e3cd802a61` | versión de la adenda; 50 pruebas en verde |
| `comparar_ast_R.py` | `fff0f75a3551d493b0e82b9e5dbc62fb72edc0c30bf2b2f91d33372e858f7579` | sin cambios |
| `potencia_R.py` | `cc68d0699fef9a320cadc527a2a2e6f00372ecbc55496255c2c0c497903982ae` | sin cambios |
| HUELLA_R | `c31f8cd6f4524804e51be7807bdd8a75e1a07885615791e251214708379f5a80` | sin cambios |
| `primerafase_webots/BITACORA_TECNICA.md` | `81c36b826ca9bdcfa4523232b0a8cbe0607e28b7ebd1502847639ab3baa5a6f9` | entrada del Exp R en las líneas 2939–3054 |

Respaldos de hoy:
- `BITACORA_TECNICA_respaldo_20261109_preExpR.md` y `_preCorrExpR.md`;
- `*_respaldo_20261109_prePrefijos.py`;
- `ENTRADA_BITACORA_expR_pre_respaldo_20261109_preBitacora.md` y `_preCorr.md`;
- `PROTOCOLO_L0_L2_respaldo_20261109_preFiltroExpR.md`.

## 8. Lo que falta, en orden (§5 del prerregistro)

| # | Paso | Quién decide | Duración aproximada |
|---|---|---|---|
| 1 | **`verificar_cifras_R.py` (núcleo)**: escribirlo, probarlo sobre las dos pruebas existentes y revisarlo | tu OK al plan (§10) | trabajo de código, sin corridas largas |
| 2 | **Manifiesto pre**: sha256 de todo lo de la carpeta | — | segundos |
| 3 | **Experimento**: 4800 episodios con las semillas nuevas | tu **"listo"**, en un día sin laboratorio, con la PC enchufada | unos 50–60 min (el control hizo 1200 en 12 min) |
| 4 | **Análisis en modo resultado** (`resumen_R.txt`), `verificar_cifras_R.py` sobre el resultado y el archivo de literales de la bitácora | — | minutos |
| 5 | **Cierre**: criterios del §6 del spec, `manifiesto_sha256_R.txt`, entrada de resultados en la bitácora y mutaciones | tu **OK** | — |

## 9. Cosas a tener en cuenta

- **Versión de Python.** El experimento exige el mismo intérprete del control: Python 3.13.14 de la Microsoft Store. Si la Store lo actualiza antes, hay que repetir el control (unos 12 min). Conviene no dejar pasar muchos días entre el manifiesto y el experimento.
- **Carpeta congelada.** Después del manifiesto no se toca ningún archivo de la carpeta del Exp R, este incluido, hasta que el experimento termine.
- **PC limpia.** Nada pesado en la PC durante una sesión de laboratorio, ni en paralelo con la réplica de la campaña.
- **Detalles cosméticos conocidos del código de corrida fijado.** Ninguno cambia lo que se verifica:
  - al terminar, la línea «RESULTADOS DEL EXP Q sin cambios» sale sin su lista, aunque el chequeo corre y para la corrida si algo difiere;
  - «PASABILIDAD: OK» no va al log.
- **H5a.** Con su potencia baja, un "no cumplida" no dice que el filtro falle (ver §3).

## 10. La pregunta que tenés que responder

**¿Te parece bien este plan para `verificar_cifras_R.py`?** Respondé "Sí, codealo" o "Cambiar algo: …".

### El plan

**Qué es.** El §4 del prerregistro pide un verificador que recalcule desde el CSV crudo, con código propio, cada cifra y cada palabra de veredicto del resumen. Tiene dos partes:
- un **núcleo fijo**, sin literales de resultados, que entra al manifiesto pre;
- un **archivo de literales** para la subsección de resultados de la bitácora, que se escribe después de la corrida y se declara como tal.

**Archivos nuevos (no se toca ninguno existente):**
- `verificar_cifras_R.py`, el núcleo;
- `test_verificar_cifras_R.py`, sus pruebas. Van en un archivo aparte porque cambiar `test_experimento_R.py` sería otra desviación con adenda.

**Independencia.** No importa nada del análisis ni del código de corrida: sólo `csv`, `math`, `hashlib` y `re`. Clopper-Pearson y McNemar exacta van con código propio y se contrastan con scipy a 10 decimales. Las reglas de lectura del §2.4 se reimplementan a partir del texto del prerregistro.

**Qué verifica, sección por sección del resumen:**
- **Prerregistro:** sha256 y línea «Fijado» recalculados; semillas, n y celdas desde el CSV.
- **Verificación** (sólo en modo resultado): cada línea copiada existe tal cual en su registro, y están todas las de inicio y fin.
- **Hipótesis H1–H6:**
  - k/n, IC, b/c, p y la palabra del veredicto, nivel por nivel;
  - en H4, las Δ pareadas con 1,96·EE;
  - en H5a, la línea de lectura cuando k ≥ 1;
  - en H6, los valores desde las columnas de la Parte B, más la sensibilidad;
  - si la Parte B falló, que diga «no evaluable».
- **Holm, eventos raros, infactibles, agotados, costo e intervención:** cada cifra.
- **«Lo que R no sustenta»:** idéntico, palabra por palabra, al §6 del prerregistro.
- **Figuras:** que estén las listadas.
- **Completitud:** toda línea del resumen se reconoce, y ninguna línea con cifras queda sin verificar.
- **Fijos** (en modo resultado):
  - 4800 filas, con las mismas 400 semillas en las 12 celdas;
  - `prerregistrado` = 1 en cada fila;
  - los sha256 del prerregistro, de la adenda y del CSV;
  - las huellas.

**Modos.**
- `--prueba-sustituto` y `--prueba-control` verifican ahora las dos pruebas existentes, antes del manifiesto, como pide el §4.
- Sin argumento corre en modo resultado, después del experimento.
- Sale con 0 si todo coincide y con 1 si no, listando cada diferencia.

**Pruebas.**
- Clopper-Pearson y McNemar contra valores conocidos y contra scipy.
- Las dos pruebas reales tienen que salir en verde.
- Mutaciones sobre copias temporales, nunca sobre los archivos reales: una cifra cambiada, un veredicto invertido («sostenida» por «no sostenida»), una línea con cifras agregada y otra borrada. Todas tienen que detectarse.

**Lo que no hace:** no mira los píxeles de las figuras, no recalcula tiempos de pared y no corre episodios.

**Después:** revisión independiente de sólo lectura y, con eso, el manifiesto pre (paso 2 del §8).
