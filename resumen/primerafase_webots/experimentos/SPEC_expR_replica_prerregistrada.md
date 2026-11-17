# SPEC — Exp R: réplica prerregistrada de los obstáculos móviles (S1–S3, semillas nuevas)

Fecha del spec: 2026-10-24. Destinatario: Claude Code. Revisor: Claude. Requiere el OK de José en cada punto marcado **[OK José]**.

---

## 0. Qué es y qué no es

**Qué es.** Un experimento nuevo en Python que prueba, con semillas que nadie ha visto, las hipótesis que generó el análisis exploratorio de S2 y S3 del Exp Q (bitácora, líneas 2821–2936, lectura corregida el 24-10). Las hipótesis, las pruebas, el n, las semillas y el plan de análisis quedan escritos y con sha256 **antes** de correr. No hay regla de parada: los cuatro criterios de falla del Exp O son resultados que se miden en los tres niveles, no disparadores. Lo que salga se reporta tal cual.

**Qué no es.** No reabre el Exp Q. El veredicto del Exp Q (S1 detiene por la regla del Exp O) queda tal cual y R no puede hacer que S2 o S3 "pasen" nada. No cambia la política, el filtro, el escape, el entorno ni ningún parámetro: es el mismo código del Exp Q, con la huella `e265b6cd31e8d443977027b1bf1d4671c002b06c3ecbdc45a275521e49c24a29`, las mismas copias de `lib/` y el mismo `modelo_sanidad.zip` (sha256 `34831589…0c27`). Tampoco toca nada del laboratorio.

**Letra y precedente.** Exp R (la bitácora usa A–O y Q; la P es el prerregistro del Exp J). El formato del prerregistro sigue `fase_preliminar2/experimento_P/PREREGISTRO_P.md`: fijado antes de correr, con su sha256 en el manifiesto y en el registro de la corrida, sin ediciones después del lanzamiento, y cualquier desviación declarada como tal en la bitácora.

**Frase para la tesis** (la que justifica todo esto): las hipótesis generadas en el análisis exploratorio se probaron en una réplica prerregistrada con semillas independientes.

---

## 1. Reglas de la casa (sin cambios)

1. Plan en prosa antes de codear. **[OK José]**
2. Sólo archivos nuevos, todos dentro de `primerafase_webots/experimentos/expR_replica_obstaculos_moviles/`. No se toca nada de `expQ_obstaculos_moviles/` (código, resultados, figuras, parciales, respaldos), ni `lib/`, ni `modelos/`, ni `swarm_env_skeleton.py`, ni los 22 congelados de la campaña, ni `config_robotat.py`, ni nada del laboratorio.
3. La bitácora se modifica sólo con OK explícito, con respaldo `BITACORA_TECNICA_respaldo_AAAAMMDD_pre<Motivo>.md`, escribiendo en bytes con el fin de línea del archivo, y comprobando que fuera del bloque insertado quede idéntica byte a byte.
4. Código en español; `python -B`; nada pesado durante sesiones de laboratorio ni en paralelo con la réplica de la campaña (PC libre); antes de cada corrida larga, el chequeo de congelados de la campaña tiene que dar "IGUAL a lo probado" y `Q.huella_codigo()` tiene que ser `e265b6cd…4a29`.
5. Nada de monkeypatching: R **importa y llama**; no redefine ni parchea nada de Q, O, `entorno_obstaculos*` ni `lib/`. Lo comprueba `comparar_ast_R.py` (§4.5).

---

## 2. Diseño (lo que queda fijado)

| Elemento | Valor fijado |
|---|---|
| Niveles | S1, S2, S3 de `Q.ESCENARIOS_Q`, sin cambios (S1: r 0.30 en el círculo R 0.60; S2: ρ 0.20; S3: ρ 0.06) |
| Condiciones | las cuatro de `Q.TIPOS_Q`: `din`, `quieto`, `ctrl`, `sinvel` (`Q.condiciones_nivel(k)`) |
| Semillas | **420100–420499** (`SEED_BASE·10 000 + i`, i = 100…499), n = 400, las mismas en las 12 celdas. Nunca usadas: el Exp O y el Exp Q usaron 420000–420099; el Exp P usó 1001–1020 y 422000–422099 (otro dominio). Verificado el 24-10 con grep sobre la bitácora y `experimentos/`: el único "420224" es el decimal 0.420224 de `resumen_complementario_O.txt` |
| Episodios | 12 × 400 = 4800 |
| Regla de parada | **ninguna**. Los cuatro criterios del Exp O (contacto, agotado, fallback del QP, infactible con obstáculo activo) se miden y se reportan en todos los niveles |
| Orden | S1, S2, S3; dentro de cada nivel `din`, `quieto`, `ctrl`, `sinvel` (como Q). Una condición a la vez, en procesos, parciales propios reanudables |
| Dinámica y métricas | las 67 columnas del Exp Q, calculadas por el mismo camino (§4.3), más las columnas derivadas del registro por paso (§4.4) |
| Pareo | por semilla, dentro de cada nivel (din/quieto/ctrl/sinvel comparten poses, objetivos y fases) y entre niveles (misma semilla = mismas poses y objetivos iniciales; sólo cambian los obstáculos) |
| Estadística | la del Exp Q: Δ pareada por semilla con IC95 = media ± 1.96·EE (ddof = 1); McNemar exacta bilateral sobre los episodios discordantes (b/c); Clopper-Pearson exacto para eventos raros. Se importan `clopper_pearson` y `mcnemar_exacta` de `analizar_exploratorio_Q.py`, no se copian |
| α | 0.05 bilateral, sin ajuste, declarado a priori; se reporta además la p ajustada por Holm sobre las pruebas con p (sensibilidad). Las hipótesis se clasifican en primarias y secundarias (§3) |
| Salidas | sólo dentro de `expR_replica_obstaculos_moviles/` |

**Por qué n = 400.** La prueba más floja es H1 en S2: en el exploratorio `S2_din` tuvo fallback en 2/100 episodios y `S2_quieto` en 0/100. Con c = 0, la McNemar exacta bilateral da p ≤ 0.05 sólo con b ≥ 6 (2·0.5⁵ = 0.0625; 2·0.5⁶ = 0.0312). Potencia a priori de P(b ≥ 6) con b ~ Binomial(n, tasa):

| n | tasa 2 % (H1 S2) | tasa 3 % (H5b S3, contactos sinvel) | tasa 5 % (H1 S3) | tasa 8 % (H3a) | cota CP de 0/n |
|---|---|---|---|---|---|
| 200 | 0.21 | 0.56 | 0.94 | 1.00 | 1.83 % |
| 300 | 0.56 | 0.89 | 1.00 | 1.00 | 1.22 % |
| **400** | **0.81** | **0.98** | **1.00** | **1.00** | **0.92 %** |
| 500 | 0.93 | 1.00 | 1.00 | 1.00 | 0.73 % |

H2, H3a y H4 tienen potencia ≈ 1 a n = 400 con los tamaños de efecto del exploratorio (S2 bajo 0.13 m: 1 contra 11 de 100; S3: 28 contra 47; agotados S3 din contra ctrl: 8 contra 0; Δ cobertura S2 +0.036 con EE 0.007 a n = 100).

**Costo de máquina (del log del exploratorio, por 100 semillas y las cuatro condiciones):** S1 ≈ 590 s, S2 ≈ 500 s, S3 ≈ 1035 s (`S3_sinvel` sola 631 s). Por 400 semillas: ≈ 2.4 h. Pasabilidad de 400 semillas: ≈ 31 min (Q tardó 464 s por 100). Control bit a bit (1200 episodios vistos): ≈ 35 min. Total ≈ 3.5 h de PC libre, reanudable por parciales.

---

## 3. Hipótesis prerregistradas (texto que va, tal cual, a `PREREGISTRO_R.md`)

**Eventos por episodio** (todos de las columnas del Exp Q): fallback = `qp_fallbacks` ≥ 1; agotado = `escape_agotados` ≥ 1; contacto = `contactos_obst_eventos` ≥ 1; bajo 0.13 m = `d_min_obst_superficie` < 0.13; bajo 0.10 m = `d_min_obst_superficie` < 0.10; infactible activo = `escape_infactibles_junto_obst` ≥ 1. En `ctrl` el contacto y los acercamientos "no aplican" (obstáculo no físico), como en el exploratorio.

**Cobertura** (denominadores del §3.6 de la propuesta, los del Exp Q): din − ctrl sobre `cobertura_accesible` (fuera de la máscara permanente); din − quieto sobre `cob_acc_arranque` (fuera de la máscara de arranque).

| Id | Enunciado | Comparación y estadístico | Predicción | Clase |
|---|---|---|---|---|
| H1 | El encierro (fallback del QP) necesita que el obstáculo se mueva | Por nivel k ∈ {S2, S3}: episodios con fallback, `Sk_din` contra `Sk_quieto`, McNemar exacta bilateral | din > quieto, p < 0.05 en S3 y en S2. En S1 se reporta (predicción: 0 y 0) | S3 primaria; S2 secundaria (potencia 0.81) |
| H2 | El término de velocidad conserva margen | Por nivel k ∈ {S2, S3}: episodios bajo 0.13 m, `Sk_din` contra `Sk_sinvel`, McNemar exacta bilateral | din < sinvel, p < 0.05 en los dos. En S1 se reporta | primaria |
| H3a | Los agotados de S3 son del obstáculo | Episodios con agotado, `S3_din` contra `S3_ctrl`, McNemar exacta bilateral | din > ctrl, p < 0.05 | primaria |
| H3b | Los agotados de S3 no son atribuibles al movimiento | Episodios con agotado, `S3_din` contra `S3_quieto`, McNemar exacta bilateral; además la diferencia pareada de tasas con su IC95 | p ≥ 0.05. Un resultado no significativo no prueba igualdad: se escribe "la atribución al movimiento no queda sostenida" y se da el IC | secundaria |
| H4 | El efecto del movimiento sobre la cobertura cae con el nivel | Δ_k = cob din − ctrl pareada por semilla, en S1, S2, S3, con IC95; y el contraste Δ_S1 − Δ_S3 pareado por semilla, con IC95 | Δ_S1 > 0 y Δ_S2 > 0 (IC95 sobre cero); el IC95 de Δ_S3 incluye el cero o queda bajo cero; Δ_S1 − Δ_S3 > 0 con IC95 sobre cero | secundaria (compuesta; se reporta cada pieza) |
| H5a | Cero contactos con F1 en los tres niveles | `Sk_din`: contactos = 0, k = 1, 2, 3; cota superior de Clopper-Pearson (0/400 → 0.92 %) | 0 en los tres | primaria (se "cumple" o "no se cumple"; no lleva p) |
| H5b | Sin el término de velocidad hay contactos en S3 | Episodios con contacto, `S3_din` contra `S3_sinvel`, McNemar exacta bilateral | din < sinvel, p < 0.05 | secundaria |
| H6a | El acercamiento bajo 0.10 m ocurre en, o justo después de, un fallback del agente que se acerca | Sólo con la Parte B. Por nivel, en `Sk_din`: entre los episodios bajo 0.10 m, fracción con `fallback_ventana_d_min_5` = 1, con IC95 de Clopper-Pearson | todos (k/k) | secundaria (descriptiva, sin p) |
| H6b | Fuera de los pasos de fallback el margen se conserva | Sólo con la Parte B. Por nivel, en `Sk_din`: episodios con `d_min_sin_fallback` < 0.10 m, k/400 con IC95 | 0/400 | secundaria (descriptiva, sin p) |

**Descriptivos sin hipótesis** (se reportan igual): la tabla de eventos raros de las 12 celdas (episodios con fallback, agotado, contacto, bajo 0.13 m, infactible activo, con IC95), la intervención total y por restricción ligante, las filas F1 saturadas, los infactibles activos (`Sk_din` contra `Sk_quieto`, McNemar, sin predicción), y los agotados de S1 y S2.

**Reglas de lectura, fijadas a priori.** Una hipótesis con p queda "sostenida" si p < 0.05 en la dirección predicha y "no sostenida" en cualquier otro caso; H5a y H6 quedan "cumplida" o "no cumplida". Nada de esto se cambia después de ver los datos. Si alguna pieza del análisis tiene que cambiar después de correr (un error de código, por ejemplo), se declara como desviación en la bitácora, con el antes y el después.

**Lo que R no sustenta, escrito antes de correr:** un cambio del veredicto del Exp Q; que S2 o S3 "pasen" la regla del Exp O (con la regla, `S2_din` y `S3_din` la habrían disparado y la volverán a disparar); que la garantía de no contacto sea robusta donde hay fallbacks (ahí, por construcción, el filtro manda u = (0, 0) sin certificado); nada sobre el laboratorio; nada sobre el rescate de F2, que no se corre.

---

## 4. Código

Carpeta nueva: `primerafase_webots/experimentos/expR_replica_obstaculos_moviles/` con `resultados/`, `resultados/parciales/`, `resultados/trazas/`, `figuras/`.

### 4.1 Archivos

| Archivo | Qué hace |
|---|---|
| `PREREGISTRO_R.md` | §0, §2, §3 y el plan de análisis (§4.6), con fecha y hora de fijación. No se edita después de fijado (§5, paso 3). Su sha256 va al manifiesto pre, al registro de cada subcomando y a la bitácora |
| `correr_experimento_R.py` | Subcomandos `control`, `pasabilidad`, `experimento` (§4.2). Importa Q desde `../expQ_obstaculos_moviles` por `sys.path`, como hace `correr_exploratorio_Q.py` |
| `comparar_ast_R.py` | Las dos comprobaciones de §4.5. Escribe `resultados/comparar_ast_R.txt` |
| `analizar_experimento_R.py` | Produce `resultados/resumen_R.txt` y las figuras (§4.6). Se escribe y se prueba **antes** de correr, sobre los datos del Exp Q y del exploratorio como sustituto (§5, paso 6) |
| `verificar_cifras_R.py` | La disciplina del exploratorio del 24-10: recalcula cada cifra de `resumen_R.txt` y de la entrada de bitácora, extrae cada cifra del texto y exige que sea un valor recalculado o una constante de diseño declarada; Clopper-Pearson y McNemar con código propio sin scipy, comparados a 10 decimales con los de scipy |
| `test_experimento_R.py` | §4.7 |
| `ENTRADA_BITACORA_expR_pre.md` y `ENTRADA_BITACORA_expR.md` | Los dos textos para la bitácora (§5, pasos 3 y 8) |
| `resultados/manifiesto_R_pre_AAAAMMDD_HHMM.txt` | sha256 de todo lo que hay en la carpeta antes de `experimento`, incluido `PREREGISTRO_R.md` y `analizar_experimento_R.py`, más las huellas (§4.8) |
| `resultados/manifiesto_sha256_R.txt` | sha256 de todos los archivos de la carpeta al cierre |

### 4.2 Subcomandos de `correr_experimento_R.py`

```
python -B correr_experimento_R.py control      > resultados/corrida_R_control.log
python -B correr_experimento_R.py pasabilidad  > resultados/corrida_R_pasabilidad.log
python -B correr_experimento_R.py experimento  > resultados/corrida_R.log
```

Los tres empiezan igual: `Q.huella_codigo()` tiene que ser `HUELLA_Q_ESPERADA` (= `e265b6cd…4a29`); `Q.verificar_copias()` y `Q.verificar_stack()` tienen que pasar; los tres archivos de S1 (`SHA256_S1` de `correr_exploratorio_Q.py`) y los tres crudos exploratorios (`experimento_Q_EXPLORATORIO_S2_S3.csv`, `reproduccion_S1_din_EXPLORATORIO.csv`, `registro_Q_EXPLORATORIO.txt`, sha256 tomados del `manifiesto_sha256_Q_EXPLORATORIO.txt` del 24-10) tienen que estar intactos al empezar y al terminar. `n_trab = max(1, cpu_count() − 1)`, como Q.

**`control`.** Corre `correr_episodio_R` sobre los **1200 episodios ya vistos**: `S1_{din,quieto,ctrl,sinvel}` × 420000–420099 contra `experimento_Q_completo.csv`, y `S2_*`, `S3_*` × 420000–420099 contra `experimento_Q_EXPLORATORIO_S2_S3.csv`. Las 66 columnas (todas salvo `t_episodio_s`; en el exploratorio se ignora además la columna `exploratorio`) tienen que salir **idénticas en texto** con `Q._serial`, 1200/1200. Además, en las 1200 filas, `pasos_agente_fallback == qp_fallbacks` (autochequeo del registro por paso). Escribe `resultados/control_bit_a_bit_R.csv` (las filas de R con sus columnas nuevas) y `resultados/control_bit_a_bit_R.txt` con "CONTROL: OK" y la huella (§4.8); si falla, "CONTROL: NO" y PARAR. Sin parciales: corre en un pool propio, como `reproducir_s1_din`.

**`pasabilidad`.** `Q._pasabilidad_semilla((k, s))` para k ∈ {S1, S2, S3} y las 400 semillas nuevas, en procesos, y el mismo criterio que `Q.pasabilidad`: ningún fallo en ningún instante y `min(Q.peor_caso_analitico(k)) > Q.UMBRAL_PASO_ESC`. Escribe `resultados/pasabilidad_R.txt` con el formato de `pasabilidad_Q.txt` (una línea por nivel con huecos, áreas, instantes evaluados y PASABLE/NO PASABLE) y "PASABILIDAD: OK" o "NO PASA" y la huella. Si no pasa, PARAR (y pensar: no se cambian niveles ni semillas sin reabrir el prerregistro).

**`experimento`.** Se niega a correr si falta cualquiera de estas cosas, y dice cuál:
- `control_bit_a_bit_R.txt` con "CONTROL: OK" y la huella R actual;
- `pasabilidad_R.txt` con "PASABILIDAD: OK" y la huella R actual;
- el manifiesto pre más reciente (`manifiesto_R_pre_*.txt`) con el sha256 actual de `PREREGISTRO_R.md`, de `correr_experimento_R.py` y de `analizar_experimento_R.py`, y con la huella R actual;
- el chequeo de congelados de la campaña en "IGUAL a lo probado": `controllers/coordinador_enjambre/verificar_campana_l2.py`, corrido como subproceso al empezar, con su salida copiada al registro (si no se puede correr desde ahí, se exige que José lo haya corrido y se registra la hora que él indique).

Después corre las 12 celdas en el orden fijado con `correr_condiciones_R` (§4.3), parciales en `resultados/parciales/R_<celda>.csv` con su `.firma` (huella R + rango de semillas + n), reanudable. Escribe `resultados/experimento_R_completo.csv` (4800 filas, columna `prerregistrado` = 1 al principio de cada fila, como el `exploratorio` = 1 del exploratorio) y `resultados/registro_R.txt`. La primera línea del registro: "PRERREGISTRADO — Exp R: réplica con semillas nuevas 420100–420499 de las hipótesis del exploratorio de S2/S3 del Exp Q; sin regla de parada; no cambia el veredicto del Exp Q." El registro lleva el sha256 de `PREREGISTRO_R.md`, las dos huellas, la hora de inicio y de fin, y por celda lo que imprime `correr_condiciones` de Q (cob_acc, interv, t/ep) más las sumas de los cuatro criterios. Al terminar vuelve a comprobar los sha256 de S1 y del exploratorio y la huella de Q.

### 4.3 Parte A: orquestación

`_tarea_R(args) -> correr_episodio_R(*args)`, y `correr_condiciones_R(conds, n_trab, prefijo, huella_R, semillas)`: una copia de `Q.correr_condiciones` que usa `_tarea_R`, `DIR_PARCIALES_R` y la huella R en la firma. Es orquestación (no dinámica), así que no se le exige igualdad de AST; sí se le exige que no redefina nada de Q (§4.5). Semillas: `semillas_R() -> [Q.SEED_BASE * 10_000 + i for i in range(100, 500)]`, con un test que comprueba que es disjunto de `Q.semillas_protocolo()`.

Si la Parte B no pasa el control (§5, paso 4) y la causa no está en las líneas `[R]`, se cae a `Q._tarea_Q` (el camino del exploratorio), se quitan H6a y H6b del prerregistro **con una adenda fechada y declarada**, y se sigue con la Parte A sola. Es el único caso en que `PREREGISTRO_R.md` se edita después de fijado.

### 4.4 Parte B: registro por paso dentro de `correr_episodio_R`

`correr_episodio_R` es una **copia textual** de `Q.correr_episodio_Q` (líneas 317–535 de `correr_experimento_Q.py`) con líneas agregadas, cada una marcada al final con `# [R]`, o en bloques entre una línea `# [R] inicio` y una `# [R] fin`. No se cambia, se mueve ni se borra ninguna línea de la copia. Lo que las líneas `[R]` agregan:

1. En el bucle de decisiones (`for i in range(n_a)`), después de `cont["fallback"] += int(not res.exito_qp)`: `fb_t[i] = int(not res.exito_qp)`, `esc_t[i] = int(en_escape)`, `int_t[i] = int(res.intervino)` (arreglos locales de tamaño `n_a`, reiniciados en cada iteración del `while`).
2. Después de `env.step` y del bucle de distancias (`for k in range(n_a)`), en la misma iteración: `do_t[k]` = la `do` ya calculada (`distancia_minima(pos[k], obst_ahora)`), o `inf` si no hay obstáculos. **El pareo es dentro de la misma iteración del `while`:** la decisión t (bandera de fallback) y la distancia medida después de `env.step` de esa iteración.
3. Acumuladores, con el mismo orden de recorrido que Q (t ascendente, k ascendente) y el mismo criterio de mínimo (`<` estricto, así que se conserva la primera ocurrencia, como hace `min`):

| Columna nueva | Definición |
|---|---|
| `pasos_agente_fallback` | Σ_t Σ_i fb_t[i]. Tiene que ser igual a `qp_fallbacks` en todos los episodios (lo comprueba el control) |
| `d_min_sin_fallback` | mín de do_t[k] sobre los (t, k) con fb_t[k] = 0; `inf` si no hay obstáculos o no hay ninguno |
| `d_min_en_fallback` | mín de do_t[k] sobre los (t, k) con fb_t[k] = 1; `inf` si no hay |
| `paso_d_min`, `agente_d_min` | el (t, k) donde se alcanzó `d_min_obst_superficie` (primera ocurrencia); −1 y −1 sin obstáculos |
| `fallback_en_d_min` | fb en (`paso_d_min`, `agente_d_min`); 0 sin obstáculos |
| `racha_fallback_d_min` | iteraciones consecutivas, terminando en `paso_d_min`, en las que `agente_d_min` tuvo fb = 1; 0 si `fallback_en_d_min` = 0 |
| `fallback_ventana_d_min_5` | 1 si `agente_d_min` tuvo fb = 1 en alguna de las iteraciones `paso_d_min` − 4 … `paso_d_min`; 0 si no, y 0 sin obstáculos |

Las columnas nuevas van **al final** del diccionario de retorno, cada una en su propia línea `# [R]`, después de `t_episodio_s`. Las 67 columnas de Q quedan con su nombre, su orden y su valor.

4. **Trazas.** Si el episodio termina con `qp_fallbacks` ≥ 1 o `contactos_obst_eventos` ≥ 1 y la condición es `din` o `sinvel`, se escribe `resultados/trazas/R_<condicion>_<semilla>.csv` con columnas `paso, agente, fallback, d_obst, en_escape, intervino` (una fila por agente y paso). Se espera del orden de 60 episodios (≈ 75 KB cada uno). La escritura ocurre al final del episodio, fuera del bucle, y no toca ni el entorno ni el filtro ni el generador aleatorio. Las trazas del `control` van a `resultados/trazas/control_<condicion>_<semilla>.csv`: el prefijo se decide dentro de la función por la semilla (`"control"` si `seed_ep` está en `Q.semillas_protocolo()`, `"R"` si no), porque la firma de `correr_episodio_R` tiene que seguir siendo `(cond, seed_ep)` para que el AST coincida, y porque en Windows los procesos del pool se crean con `spawn` y no heredan variables de módulo puestas en `main()`; sólo las constantes de módulo (`DIR_TRAZAS_R`, `DIR_PARCIALES_R`) se reimportan bien.

Para que la copia sea textual, `correr_experimento_R.py` importa con `from correr_experimento_Q import *` más, explícitamente, los nombres con guión bajo que el cuerpo usa (`_inicializar_trabajador` viene de `correr_experimento_O`, como en el exploratorio). El `global _MODELO` de la copia se refiere a un `_MODELO = None` propio del módulo R. Este es el **único** lugar del proyecto donde se permite un `import *`, y el motivo queda en el docstring.

### 4.5 `comparar_ast_R.py`: dos comprobaciones, las dos tienen que dar OK

1. **"Sólo agrega registro".** Se toma el texto de `correr_experimento_R.py`, se quitan las líneas que terminan en `# [R]` y los bloques entre `# [R] inicio` y `# [R] fin`, se renombra `correr_episodio_R` → `correr_episodio_Q`, y `ast.dump` de esa función tiene que ser **idéntico** al de `correr_episodio_Q` en `correr_experimento_Q.py`. Si no, lista la primera diferencia y da NO.
2. **"Sólo orquesta".** Ningún `def` ni `class` de nivel de módulo en `correr_experimento_R.py` puede tener un nombre que exista en los espacios de nombres de `correr_experimento_Q`, `correr_experimento_O`, `entorno_obstaculos`, `entorno_obstaculos_moviles` o `lib/*`, salvo la lista permitida: `correr_episodio_R`, `_tarea_R`, `correr_condiciones_R`, `semillas_R`, `control`, `pasabilidad`, `experimento`, `main` y las constantes `*_R`. No hay asignaciones a atributos de módulos importados (`Q.algo = …`), ni `setattr`, ni `importlib.reload`.

Escribe `resultados/comparar_ast_R.txt` con las dos líneas de veredicto y la huella R. Es prerrequisito del `control`.

### 4.6 `analizar_experimento_R.py` y `resumen_R.txt`

Secciones, en este orden: ENCUADRE (el mismo del Exp Q: no prueba adaptabilidad de la política; prueba la generalidad de la capa de seguridad y su costo); PRERREGISTRO (fecha y hora de fijación, sha256 de `PREREGISTRO_R.md`, semillas, n); VERIFICACIÓN (control 1200/1200, pasabilidad, huellas, sha256 de S1 y del exploratorio, hora de inicio y fin); RESULTADOS POR HIPÓTESIS (H1…H6b, cada una con el enunciado, la cifra, el IC o la p, la p de Holm cuando aplica, y el veredicto con la palabra fijada); EVENTOS RAROS (la tabla de las 12 celdas con IC95, mismo formato que el exploratorio, "no aplica" en ctrl); COSTO EN TAREA (Δ pareadas por nivel con IC95, y Δ_S1 − Δ_S3); INTERVENCIÓN (total y por ligante, filas saturadas); DIAGNÓSTICO RETROSPECTIVO SOBRE SEMILLAS VISTAS (§5, paso 4; sección aparte y rotulada así); LO QUE R NO SUSTENTA (la lista de §3, tal cual). Todas las p con cuatro decimales o "< 0.0001"; los IC con corchetes; los eventos como k/n.

Figuras, con la leyenda fuera del área de datos y el rótulo arriba de los ejes, como quedaron las del exploratorio el 24-10:
- `fig_R_costo.png`: Δ cobertura pareada por nivel (S1, S2, S3), las dos comparaciones, IC95.
- `fig_R_intervencion.png`: las 12 celdas, intervención total y ligantes, umbral 0.5.
- `fig_R_fallback_distancia.png`: sólo con la Parte B. Para los episodios `din` bajo 0.10 m, la distancia del `agente_d_min` al obstáculo contra el paso, con los pasos en fallback marcados, en paneles pequeños. Es la figura que convierte "coinciden por episodio" en "coinciden en el tiempo", si los datos lo dicen.

El script tiene que correr sin cambios sobre los datos de R después de la corrida. Antes de la corrida se prueba sobre un sustituto: `experimento_Q_completo.csv` + `experimento_Q_EXPLORATORIO_S2_S3.csv` (y `control_bit_a_bit_R.csv` para las columnas de la Parte B), con la salida rotulada "PRUEBA DEL ANÁLISIS SOBRE DATOS VISTOS, NO ES EL RESULTADO DE R" y guardada como `resultados/resumen_R_prueba_sobre_Q.txt`. Esa prueba sirve también para fijar el formato del resumen y para que `verificar_cifras_R.py` exista antes de la corrida.

### 4.7 `test_experimento_R.py`

Con un presupuesto chico (uno o dos episodios cuando haga falta):
1. `semillas_R()` tiene 400 enteros, 420100…420499, disjuntos de `Q.semillas_protocolo()`.
2. Las columnas derivadas, sobre arreglos sintéticos `fb` y `do` de un episodio inventado: mínimo en paso de fallback, mínimo fuera de fallback, racha, ventana de 5, episodio sin obstáculos (todo `inf`/−1/0), episodio sin fallbacks (`d_min_sin_fallback == d_min`). Para esto, la lógica de las columnas derivadas vive en una función pura `columnas_derivadas(fb, do) -> dict` que `correr_episodio_R` llama en una línea `[R]`.
3. Un episodio real `S3_din` con una semilla vista (420057, la que comparte agotado y fallback con `S3_sinvel`): las 66 columnas idénticas en texto a la fila del CSV exploratorio, y `pasos_agente_fallback == qp_fallbacks`.
4. `comparar_ast_R.py` da OK sobre el archivo real, y da NO sobre una copia temporal con una línea cambiada sin marca `[R]` (y también con una línea `[R]` que modifique una variable de Q, por ejemplo `acciones[i] = 0 # [R]`, que el comparador tiene que rechazar porque no es sólo registro: la regla es que una línea `[R]` sólo puede asignar a nombres nuevos `*_t`, a los acumuladores nuevos o escribir archivos de traza).
5. Clopper-Pearson y McNemar: los valores conocidos del exploratorio (0/100 → [0, 0.0362]; b/c = 0/3 → 0.25; 8/3 → 0.2266; 28/9 → 0.0026).
6. El gate de `experimento`: con un manifiesto pre cuyo sha256 de `PREREGISTRO_R.md` no coincide, se niega a correr y dice por qué.
7. La escritura de trazas: un episodio con fallback produce el archivo con las columnas y el número de filas correctos (`pasos × n_a`); uno sin fallback ni contacto no lo produce.

### 4.8 Huellas

`huella_R = sha256(huella_Q + "|" + sha256(correr_experimento_R.py))`, con `huella_Q = Q.huella_codigo()`. Todo registro de R lleva las dos líneas `HUELLA_Q …` y `HUELLA_R …`. `_aprobado` de R exige la huella R; `huella_Q` tiene que ser `e265b6cd…4a29` siempre. El sha256 de `PREREGISTRO_R.md` se escribe en el manifiesto pre y en los tres registros.

---

## 5. Orden de ejecución, con sus compuertas

1. **Plan en prosa** de Claude Code, con los riesgos que vea (en particular el `import *` y el pareo decisión/distancia de §4.4). **[OK José]**
2. **Código, tests y comparador**, sin corridas largas. `test_experimento_R.py` en verde y `comparar_ast_R.py` en OK.
3. **Fijar las hipótesis.** `PREREGISTRO_R.md` queda terminado (§0, §2, §3, §4.6), se calcula su sha256 y se inserta en la bitácora, después del separador `---` que cierra la entrada del Exp Q (línea 2937 al 24-10) y antes de `## v2 — Reentrenamiento con bordes bloqueantes`, con el mismo patrón de separación que las demás entradas, una entrada corta `## Exp R — Réplica prerregistrada de los obstáculos móviles (prerregistrado el AAAA-MM-DD HH:MM)` con: propósito en tres líneas, semillas, n, la lista de hipótesis con su clase, el sha256 del prerregistro y la frase "resultados en su propia entrada". **[OK José]** Desde aquí, `PREREGISTRO_R.md` no se edita (salvo §4.3, último párrafo). **Esto va antes del control** a propósito: el control produce las columnas de la Parte B sobre semillas ya vistas, y H6 tiene que estar escrita antes de mirarlas.
4. **`control`** (≈ 35 min, PC libre). 1200/1200 y el autochequeo. Si falla por una línea `[R]`, se corrige y se repite; si falla por otra cosa, se aplica §4.3, último párrafo. Las columnas nuevas de `control_bit_a_bit_R.csv` sobre los episodios con fallback del exploratorio (`S2_din` 2, `S3_din` 5, `S3_sinvel` 3) son el **diagnóstico retrospectivo** que el 24-10 quedó opcional: se reporta en su sección aparte del resumen y de la bitácora, rotulado "sobre semillas vistas; descriptivo", y no cuenta como prueba de H6.
5. **`pasabilidad`** (≈ 31 min). PASABILIDAD: OK.
6. **Fijar el análisis.** `analizar_experimento_R.py` y `verificar_cifras_R.py` probados sobre el sustituto (§4.6). Se genera `manifiesto_R_pre_AAAAMMDD_HHMM.txt` con el sha256 de todos los archivos de la carpeta y las dos huellas. Desde aquí, ningún archivo de la carpeta cambia hasta que termine `experimento`.
7. **`experimento`** (≈ 2.4 h, PC libre, de noche o en una tarde sin laboratorio; reanudable). Antes: congelados "IGUAL a lo probado".
8. **Cierre.** `analizar_experimento_R.py` sin cambios (si hubo que cambiar algo, desviación declarada con diff); figuras; `verificar_cifras_R.py` en orden sobre el resumen y sobre la entrada de bitácora; tres mutaciones del resumen y tres de la entrada, todas detectadas; tests en verde; AST en OK; congelados "IGUAL a lo probado"; sha256 de Q y del exploratorio intactos; `manifiesto_sha256_R.txt`. Entrada de resultados en la bitácora, a continuación de la entrada pre, con la estructura de la del Exp Q (Encuadre, Qué no cambia, Verificación antes de correr, Resultado por hipótesis, Eventos raros, Costo, Diagnóstico retrospectivo, Qué afirmación del documento sustenta, No sustenta, Verificación, Costo de máquina). **[OK José]** Respaldo de la bitácora con sufijo `_respaldo_AAAAMMDD_preExpR`.

Opcional, con OK aparte: una línea al final de la subsección exploratoria del Exp Q que diga "La hipótesis del mecanismo se diagnosticó sobre estas semillas y se probó con semillas nuevas en el Exp R (ver su entrada)".

---

## 6. Criterios de cierre (todos)

- `comparar_ast_R.txt`: las dos comprobaciones OK.
- `control_bit_a_bit_R.txt`: 1200/1200 idénticas en texto en las 66 columnas; `pasos_agente_fallback == qp_fallbacks` en 1200/1200.
- `pasabilidad_R.txt`: PASABILIDAD: OK en S1, S2 y S3 con las 400 semillas.
- `manifiesto_R_pre_*.txt` anterior a la hora de inicio de `registro_R.txt`, con los sha256 que `experimento` comprobó.
- `experimento_R_completo.csv`: 4800 filas, 12 celdas × 400 semillas, sin semilla repetida ni faltante; columna `prerregistrado` = 1.
- `resumen_R.txt`: cada hipótesis con su veredicto en la palabra fijada; `verificar_cifras_R.py` en orden (resumen y entrada de bitácora); mutaciones detectadas.
- Figuras con leyenda afuera y rótulo arriba; nada tapado.
- Tests en verde; huella de Q `e265b6cd…4a29` al inicio y al final de cada subcomando; sha256 de los tres archivos de S1 y de los tres crudos exploratorios intactos; congelados de la campaña "IGUAL a lo probado".
- Fuera de la carpeta nueva, el único archivo modificado es la bitácora, con sus dos respaldos, y fuera de los bloques insertados idéntica byte a byte.
- `manifiesto_sha256_R.txt` al cierre.

---

## 7. Estimación

Claude Code: plan 0.5 h; código y tests 2–3 h; comparador 0.5 h; análisis y verificador 2 h antes de correr; cierre y bitácora 1.5 h. Total ≈ 7–8 h de trabajo, en dos o tres sesiones. Máquina: 35 + 31 min antes de correr, 2.4 h la corrida, todo con la PC libre y reanudable. Lo razonable es control y pasabilidad una tarde, la corrida esa noche, y el cierre al día siguiente.

---

## 8. Riesgos conocidos

- **El pareo decisión/distancia (§4.4, punto 2).** La distancia se mide después de `env.step` de la misma iteración en que se tomó la decisión. Si se parea con la iteración siguiente, H6 mide otra cosa. El test 2 y el test 3 lo fijan.
- **`import *`.** Trae todo lo público de Q (que a su vez trae lo de O); un nombre de R que colisione con uno de Q lo sombrearía sin aviso. Por eso §4.5, comprobación 2.
- **OneDrive.** Las corridas de Q y del exploratorio se hicieron en la carpeta sincronizada sin problema; si la sincronización bloquea un parcial, el `.firma` lo detecta y se reanuda.
- **Potencia de H1 en S2 (0.81).** Un "no sostenida" ahí es un resultado válido y se escribe así; no se agregan semillas después de ver el dato.
- **Tiempo de `S3_sinvel`** (6.3 s por episodio en el exploratorio, por los escapes): es la celda que marca el total.
