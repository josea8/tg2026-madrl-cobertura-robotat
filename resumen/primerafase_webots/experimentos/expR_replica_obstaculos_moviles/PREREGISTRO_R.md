# Preregistro — Experimento R

**Réplica prerregistrada de los obstáculos móviles (S1–S3) con semillas de episodio nuevas.**

Fijado: 2026-11-09 01:38

Este archivo se fija ANTES de correr el control sobre semillas vistas y ANTES de correr ningún episodio con semillas nuevas. Fijarlo es escribir en la línea de arriba la fecha y la hora y calcular su sha256. El sha256, con la fecha y la hora, se imprime; José lo pega en el chat y se lo manda por correo a su asesor. Ese correo es el registro fuera de la PC (D5).

El sha256 va además a cada registro (`control`, `pasabilidad`, `experimento`), al manifiesto pre y a la entrada del Exp R en la bitácora. El código se niega a correr `control`, `pasabilidad`, `manifiesto` y `experimento` si la línea «Fijado:» no tiene fecha y hora.

Este archivo no se edita después de fijado. Cualquier cambio posterior va en un archivo aparte, `ADENDA_PREREGISTRO_R_AAAAMMDD.md`, con el sha256 del original y el suyo, declarado en la bitácora (§7).

## 0. Qué es y qué no es

**Qué es.** R prueba, con 400 semillas de episodio que no generaron las hipótesis, las hipótesis del análisis exploratorio de S2 y S3 del Exp Q (bitácora, subsección EXPLORATORIO del Exp Q, lectura corregida el 2026-10-24). No hay regla de parada: los cuatro criterios de falla del Exp O se miden y se reportan en los tres niveles, no detienen nada. Lo que salga se reporta tal cual, con las palabras de veredicto del §2.4.

**Qué no es.** No reabre el Exp Q: su veredicto (S1 detiene por la regla del Exp O) queda tal cual, y R no puede hacer que S2 o S3 "pasen" nada. No cambia la política, el filtro, el escape, el entorno ni ningún parámetro. La dinámica es el código del Exp Q con su huella `e265b6cd31e8d443977027b1bf1d4671c002b06c3ecbdc45a275521e49c24a29`, las copias de `lib/` y `modelo_sanidad.zip` (sha256 `34831589afd04593e70f8faf1cb51acaea7a7233063f4d2a43afbbe9ef1d0c27`). No toca nada del laboratorio.

**Alcance de la réplica.** Las semillas nuevas son semillas de EPISODIO: poses, objetivos y fases nuevas. La política es la misma (un solo entrenamiento, `modelo_sanidad`) y el código también. R no es una réplica con otros entrenamientos ni una verificación independiente del código.

**Origen del diseño.** Este prerregistro sale de dos fuentes, y manda sobre el spec donde difieren:
- el spec de José del 2026-10-24 (`experimentos/SPEC_expR_replica_prerregistrada.md`, sha256 `cf6add2b40ca676ecb8205264315f932344954f8f9cc24638010b58a99585eca`);
- las decisiones D1–D7 del plan del 24-10, aprobadas por José el 24-10, más las correcciones de la revisión adversarial del código del 26-10 y las precisiones de José del 09-11 (regla del mínimo, «PARTE B: NO», lectura de H5a, sha256 y «Fijado» en los registros, filtro simétrico del laboratorio).

Los criterios de cierre del §6 del spec siguen vigentes (§5.7).

## 1. Diseño

| Elemento | Valor fijado |
|---|---|
| Niveles | S1, S2, S3 de `ESCENARIOS_Q` del Exp Q, sin cambios |
| Condiciones | `din`, `quieto`, `ctrl`, `sinvel` (`condiciones_nivel` del Exp Q) |
| Semillas | **420110–420509** (`42·10 000 + i`, i = 110…509), n = 400, las mismas en las 12 celdas. 420000–420099 las usaron el Exp O y el Exp Q. **420100–420109 las usó la Fase 0 del obstáculo móvil** (02-10, `controllers/coordinador_enjambre/correr_fase0_obstaculo.py:44,152`), en otro dominio, y se dejan afuera. En la búsqueda del 24-10 de enteros 4201xx–4209xx en `primerafase_webots/` y `fase_preliminar2/` sólo aparecieron 420100–420109 de la Fase 0 y los extremos de rango del propio spec del Exp R. El Exp P prerregistró 1001–1020 (entrenamiento) y 420000–420019, 421000–421029 y 422000–422099 (episodios), y nunca se corrió |
| Episodios | 12 × 400 = 4800 |
| Regla de parada | ninguna |
| Orden | S1, S2, S3; dentro de cada nivel `din`, `quieto`, `ctrl`, `sinvel`; una celda a la vez, en procesos, con parciales reanudables |
| Pareo | Dentro de cada nivel, por semilla: las cuatro condiciones comparten poses, objetivos, fases y reubicaciones. Entre niveles, por semilla: el mismo sorteo base, pero la reubicación de agentes y objetivos depende del nivel (en el exploratorio, 76, 96 y 99 de 100 episodios con algún agente reubicado en S1, S2 y S3). Las fases de S1 son prefijo de las de S2 y S3. Correlación de las Δ de cobertura entre niveles, en el exploratorio: ≈ 0 entre S1 y S3 (−0,006) y +0,26 entre S2 y S3, donde el pareo baja el EE de 0,0105 a 0,0090 |
| Código | `correr_experimento_R.py`: copia textual de `correr_episodio_Q` con 11 líneas `# [R]` que sólo registran (§3); importa explícitamente los 37 nombres libres de la función, sin `import *`. `comparar_ast_R.py` certifica el cuerpo de la copia y la identidad de sus nombres libres; la orquestación (`_tarea_R`, `correr_condiciones_R`) la cubren la revisión y el control, éste sólo en 420000–420099. Los comparadores estáticos no protegen contra código escrito a propósito para eludirlos |

## 2. Hipótesis y reglas de lectura

### 2.1 Eventos por episodio

Un episodio "tiene" el evento si:

| Evento | Definición | En `ctrl` |
|---|---|---|
| fallback | `qp_fallbacks` > 0 | se mide |
| agotado | `escape_agotados` > 0 | se mide |
| contacto | `contactos_obst_eventos` > 0 | no aplica |
| bajo 0,13 m | `viol_cota_obst_agente_eps` > 0, equivalente a `d_min_obst_superficie` < 0,13 (COTA_CENTRO_OBST = 0,18 − 0,05; las dos definiciones coinciden en las 1200 filas vistas) | no aplica |
| bajo 0,10 m | `d_min_obst_superficie` < 0,10 | no aplica |
| infactible activo | `escape_infactibles_junto_obst` > 0 | no aplica |

En `ctrl` el obstáculo no es físico: los agentes lo atraviesan y la distancia sale negativa. "No aplica" es como en el exploratorio.

**El umbral de 0,10 m no es una constante de diseño.** Se eligió el 24-10 sobre los datos exploratorios: en S3_din todo episodio bajo 0,10 m tuvo fallback, y el mínimo sin fallback fue 0,1208. No separa todos los fallbacks: el de 420004 tuvo d_min 0,1164. Queda fijado ahora, antes de ver las semillas nuevas. H6 lleva además la sensibilidad en 0,13 m (COTA_CENTRO_OBST, §2.5). Ahí se espera que una fracción grande de S3_din quede fuera de la ventana: en el exploratorio, 23 de 100 episodios de S3_din bajaron de 0,13 m sin ningún fallback. R no afirma que se conserve la cota de 0,13.

### 2.2 Pruebas pareadas

Comparación A contra B: McNemar exacta, bilateral, sobre los episodios discordantes. b = episodios con el evento sólo en A; c = sólo en B. La predicción de las pruebas con veredicto es **A > B** (b > c).

Cobertura: Δ pareada por semilla, media ± 1,96·EE (ddof = 1). Proporciones: k/n con IC95 de Clopper-Pearson. α = 0,05 bilateral, sin ajuste.

### 2.3 Hipótesis

| Id | Enunciado | Prueba | Predicción | Clase |
|---|---|---|---|---|
| H1 | El encierro (fallback del QP) aparece con el movimiento | episodios con fallback, A = Sk_din, B = Sk_quieto | A > B, p < 0,05; se lee por nivel | S3 primaria; S2 secundaria |
| H2 | El término de velocidad conserva margen | episodios bajo 0,13 m, A = Sk_sinvel, B = Sk_din | A > B, p < 0,05; se lee por nivel | S2 primaria; S3 primaria |
| H3a | Los agotados de S3 son del obstáculo | episodios con agotado, A = S3_din, B = S3_ctrl | A > B, p < 0,05 | primaria |
| H3b | El movimiento agrega agotados en S3 | episodios con agotado, A = S3_din, B = S3_quieto; además, la Δ de tasas pareada (media ± 1,96·EE de la diferencia de indicadores), descriptiva | A > B, p < 0,05 | secundaria |
| H4 | En S3 el efecto del obstáculo móvil (din − ctrl) sobre la cobertura accesible es menor, con signo, que en S1 y que en S2 | Δ_k = `cobertura_accesible` din − ctrl pareada; piezas Δ_S1 − Δ_S3 y Δ_S2 − Δ_S3, pareadas por semilla, IC95 | las dos piezas con el límite inferior del IC95 > 0 | secundaria (compuesta) |
| H5a | Cero contactos con F1 en los tres niveles | episodios con contacto en Sk_din, k = 1, 2, 3, con Clopper-Pearson (0/400 → cota 0,918 %) | 0 en los tres | primaria |
| H5b | El término de velocidad reduce los contactos en S3 | episodios con contacto, A = S3_sinvel, B = S3_din | A > B, p < 0,05 | secundaria |
| H6a | El acercamiento bajo 0,10 m ocurre en, o justo después de, un fallback del agente que se acerca | Parte B, por nivel, en Sk_din: de los m episodios bajo 0,10 m, k con `fallback_ventana_d_min_5` = 1, con Clopper-Pearson | k = m | secundaria (descriptiva, sin p) |
| H6b | Fuera de la ventana de un fallback ningún agente baja de 0,10 m | Parte B, por nivel, en Sk_din: episodios con `d_min_fuera_ventana_5` < 0,10, k/400 con Clopper-Pearson | 0/400 | secundaria (descriptiva, sin p) |

**En S1, H1 y H2 son descriptivas**: se reportan con su p, sin veredicto y fuera de Holm (en el exploratorio, S1 tuvo 0 fallbacks en din y en quieto).

**Necesidad del movimiento (H1, descriptiva).** El enunciado de la propuesta era "el encierro necesita que el obstáculo se mueva". La prueba de H1 mide la asociación (din > quieto). La necesidad se reporta aparte, sin veredicto, como «con obstáculos quietos, fallback en k/400 [IC95]» en los tres niveles, y no se escribe "necesita".

Con obstáculos quietos, u = 0 es factible mientras todos los h ≥ 0. Así que ahí sólo puede haber fallback después de una violación o por una falla numérica del SLSQP (no convergencia o verificación defensiva).

**Por qué H3b pasó de nula a direccional (decidido antes de correr, el 24-10).** El spec la escribía como "los agotados de S3 no son atribuibles al movimiento", con la predicción p ≥ 0,05. En el exploratorio el efecto puntual fue +5 puntos: 8 % contra 3 %, discordantes 8/3, p = 0,2266.

Con ese efecto, a n = 400 la prueba da p < 0,05 con din > quieto con probabilidad 0,83 (plug-in) a 0,69 (predictiva) (§8). Una predicción nula sólo se habría podido evaluar como falta de potencia, y por la regla general no podía quedar "sostenida" con ningún resultado. Por eso se reformuló como hipótesis direccional, la que sugiere el dato.

- Si queda sostenida, corrige la frase del exploratorio "los agotados de S3 son del obstáculo, no del movimiento". La corrección se escribe en la entrada de R en la bitácora, no en la del Exp Q (D7).
- Si queda "no sostenida", no se afirma que los agotados no sean del movimiento: se da el IC de la Δ.

**Acoplamiento H5a–H5b.** Cada contacto en S3_din sube c en la McNemar de H5b. Con la tasa del 3 % en sinvel, la potencia en el punto baja de 0,9810 (c = 0) a 0,9138 (c = 1) y a 0,7616 (c = 2) (§8).

### 2.4 Reglas de lectura (fijadas; no se cambian después de ver los datos)

- **Pruebas con p** (H1 S2 y S3, H2 S2 y S3, H3a, H3b, H5b): "sostenida" si p < 0,05 y b > c; si no, "no sostenida". Se agrega "(dirección contraria)" si p < 0,05 con c > b, y "(sin discordantes)" si b + c = 0.
- **H1, H2 y H6 se leen por nivel**: no hay veredicto conjunto "H1", "H2" ni "H6".
- **H4**: "sostenida" si las dos piezas tienen el límite inferior del IC95 estrictamente > 0; si no, "no sostenida". Δ_S1, Δ_S2 y Δ_S3 se reportan con su IC, sin veredicto.
- **H5a**: "cumplida" si los tres niveles dan 0/400; si no, "no cumplida". Con k ≥ 1 se reporta como tasa k/400 con su IC95 de Clopper-Pearson por nivel, y se discute con la traza de cada episodio con contacto: si el contacto cayó en la ventana de un fallback del agente o no. No se lee como "el filtro falla". Con una tasa pequeña pero no nula, "no cumplida" es el resultado probable aunque el filtro funcione (§8).
- **H6a**, por nivel: "cumplida" si k = m ≥ 1; "no cumplida" si k < m; **"no evaluable en el nivel" si m = 0**. En S1 y S2 del exploratorio ningún episodio din bajó de 0,10 m.
- **H6b**, por nivel: "cumplida" si 0/400; si no, "no cumplida".
- **Parte B no evaluable.** Si el control o el experimento registran «PARTE B: NO» (§3.3, §7), H6a y H6b en los tres niveles, y la ubicación de los contactos de H5a, quedan "no evaluable". H1–H5 se leen igual.
- **Holm**: p ajustada sobre la familia cerrada de las 7 McNemar con predicción direccional, {H1-S3, H1-S2, H2-S2, H2-S3, H3a, H3b, H5b}. Es sólo sensibilidad: no cambia la palabra del veredicto. Quedan afuera las McNemar de S1, la de infactibles y toda McNemar descriptiva.
- **Errores después de correr.** Si una pieza del análisis tiene que cambiar después de correr (un error de código), el veredicto primario es el del script prerregistrado. El cambio se declara como desviación en la bitácora, con el antes, el después y el diff.

### 2.5 Descriptivos sin hipótesis

Se reportan igual:
- la tabla de eventos de las 12 celdas, con IC95;
- la intervención total y por restricción ligante, y las filas F1 saturadas;
- los infactibles activos, din contra quieto (McNemar, sin predicción);
- los agotados de S1 y S2;
- el costo en tarea (§4).

**Sensibilidad de H6** (rotulada, sin veredicto, del tipo H6b): episodios de Sk_din bajo el umbral fuera de la ventana, con:
- W = 1 (`d_min_sin_fallback`), W = 3 y W = 10, en 0,10 m;
- W = 5, en 0,13 m.

## 3. Parte B: registro por paso (definiciones congeladas)

### 3.1 Qué se registra y cuándo

`correr_episodio_R` es la copia textual de `correr_episodio_Q` (`correr_experimento_Q.py:317-534`) con 11 líneas `# [R]`. Se registra en cada iteración t del bucle y para cada agente k:
- t = 0…499, en orden. La base es el índice del bucle, no `n_pasos`, que se incrementa entre `env.step` y las distancias.
- k sigue el orden de `agentes`, fijo en el reset.

| Valor | Línea de Q de la que sale | Momento |
|---|---|---|
| `fb_t[k]` = `int(not res.exito_qp)` | después de `cont["fallback"] += …` (Q:426) | decisión t |
| `esc_t[k]` = `int(en_escape)` | ídem | decisión t: 1 si la acción que entró al filtro venía del escape; 0 en el paso en que el escape termina y en el refractario |
| `int_t[k]` = `int(res.intervino)` | ídem | decisión t (no contiene a `fb_t`: con u_nom ≈ 0 puede haber fallback sin intervención) |
| `do_t[k]` = `do` | dentro de `if obst_ahora:`, después de `do = distancia_minima(pos[k], obst_ahora)` (Q:453) | DESPUÉS de `env.step` de la iteración t |
| posición antes / después | `poses[:, :2]` (Q:380) / `pos` (Q:433) | antes / después del paso t |
| contador de contactos | `env.contactos_obstaculo` | después del paso t |

Los valores por defecto se reinician en cada iteración: −1 en `fb_t`, `esc_t` e `int_t`, inf en `do_t`. Todos los agentes pasan por el filtro en todos los pasos (no hay `continue` ni `break`), así que un −1 que llegue al final detiene el episodio con error.

**Pareo.** La decisión t usa las poses, los obstáculos y la velocidad de t. `env.step` mueve los obstáculos de t a t + 1, integra la acción filtrada y proyecta los contactos. La distancia `do_t` es, entonces, la consecuencia de la decisión t, y se parea con `fb_t` de la MISMA iteración.

### 3.2 Columnas derivadas (`columnas_derivadas(fb, do)`, función pura)

Los mínimos usan < estricto. La **ventana de W** de (t, k) son las decisiones t − W + 1 … t del mismo agente k. El valor es **W = 5 = 1/(α·dt) = 1/(2 · 0,1)**, la constante de tiempo de la recuperación exponencial que exige el CBF (ḣ ≥ −α·h).

La estimación que justifica el valor es aproximada, porque la orientación del agente cambia h sin mover el centro. Toma la recuperación mínima discreta (h ← 0,8·h por paso) con el punto de mira hacia afuera (h = d − 0,13). Desde el mínimo del exploratorio (d = 0,0789) quedan 2 mediciones bajo 0,10 m con el QP ya factible antes de superar 0,10, y la ventana de 5 las cubre. Es una sola definición para H6a y H6b.

| Columna | Definición |
|---|---|
| `pasos_agente_fallback` | Σ fb; tiene que ser `qp_fallbacks` |
| `d_min_sin_fallback` | mín de do sobre los (t, k) con fb = 0 (= ventana W = 1); inf si no hay |
| `d_min_en_fallback` | mín de do sobre los (t, k) con fb = 1; inf si no hay |
| `d_min_fuera_ventana_W`, W ∈ {3, 5, 10} | mín de do sobre los (t, k) cuyo agente no tuvo fallback en la ventana de W; inf si no hay |
| `pasos_bajo_010`, `pasos_bajo_010_fuera_ventana_5` | agente-pasos con do < 0,10, en total y fuera de la ventana de 5 |
| `paso_d_min`, `agente_d_min` | la primera (t, k) con d ≤ d_min + 1e-9 m, recorriendo t ascendente y k ascendente; sin obstáculos, −1 y −1 |
| `fallback_en_d_min` | fb en (`paso_d_min`, `agente_d_min`); 0 sin obstáculos |
| `racha_fallback_d_min` | decisiones consecutivas con fb = 1 del agente, terminando en `paso_d_min`; 0 si `fallback_en_d_min` = 0 |
| `fallback_ventana_d_min_5` | 1 si (`paso_d_min`, `agente_d_min`) está en la ventana de 5; 0 si no o sin obstáculos |

**Diferencia con el spec en `paso_d_min`.** El spec (§4.4) lo define como el argmin exacto (primera ocurrencia con < estricto). Este prerregistro toma la primera (t, k) con d ≤ d_min + 1e-9 m, recorriendo t ascendente y k ascendente (aprobado por José el 09-11). El motivo está en los contactos: la proyección deja la distancia en 0,075 + 1e-9 con un ruido de 1e-16, y el argmin exacto lo decidiría ese ruido. Con la tolerancia cuenta el PRIMER contacto en el tiempo.

En las semillas vistas con contacto (S3_sinvel 420013 y 420090), el (t, k) cambia en 2 pasos y `fallback_ventana_d_min_5` no cambia. Sin contactos coinciden.

**Lo que la ventana no ve.** Sólo mira hacia atrás. Un acercamiento bajo 0,10 m que PRECEDE al fallback (el fallback como consecuencia de la cercanía) cuenta como fuera de la ventana, es decir, en contra de H6b. Es coherente con el enunciado: lo que se afirma es que el acercamiento ocurre en, o justo después de, un fallback. H6 mide coincidencia en el tiempo, no causa.

### 3.3 Autochequeos de la captura

**En cada fila** del control y del experimento:
- `pasos_agente_fallback` = `qp_fallbacks`;
- mín(`d_min_sin_fallback`, `d_min_en_fallback`) = `d_min_obst_superficie`, exacto;
- `contactos_registrados` = `contactos_obst_eventos`;
- `pasos_agente_intervino` / (pasos · n_a) = `cbf_frac_interv`, en texto;
- `pasos_agente_escape_intervino` = `escape_filtro_modifico`;
- `xy_discontinuo` = 0: la posición antes del paso t + 1 es la posición después del paso t;
- **prueba física del pareo**: `fb_desplazado` = 0.

  Con u = (0, 0), la cinemática deja x, y exactos (la integración de Euler y el recorte de pared, que con u = 0 es la identidad). La posición sólo cambia por la proyección de un contacto con un obstáculo. No hay empuje entre robots: `_check_collisions` sólo detecta.

  Si el pareo estuviera corrido un paso, aparecerían agentes "en fallback" que se mueven sin contacto. Si `fb_desplazado` ≠ 0, antes de tocar nada se revisa si el entorno desplaza agentes por alguna otra vía, contacto entre robots incluido.

**En agregado**, sobre cada corrida (control, experimento): la suma de `fb_desplazado_corrido` sobre las filas con fallback es > 0. Es la misma cuenta con la bandera de la decisión t − 1, y muestra que la prueba discrimina. Por episodio puede ser 0 (una racha que llega a t = 499); cuántos episodios con fallback dan 0 se reporta como descriptivo.

Si algún autochequeo o la biyección de las trazas falla, el registro dice «PARTE B: NO». Debajo lista qué episodios fallaron qué autochequeo, y los problemas de trazas. Deja además constancia de que las 66 columnas de Q de cada fila siguen siendo válidas por construcción: las líneas `[R]` sólo registran (comprobación 3 de `comparar_ast_R.py`) y, sin ellas, el texto es el de `correr_episodio_Q` (comprobación 1). Las filas de H1–H5 no dependen de la Parte B y se escriben igual (§7).

### 3.4 Trazas

Para cada episodio de una celda con obstáculo físico (no `ctrl`) con fallback, contacto o `d_min_obst_superficie` < 0,10 m, se escribe `resultados/trazas/<prefijo>_<celda>_<semilla>.csv` (prefijo `R`; `controlR` en el control). Tiene 2500 filas (500 pasos × 5 agentes) y estas columnas:
- `paso`, `agente`, `fallback`, `d_obst`;
- `en_escape`, `intervino`;
- `x_antes`, `y_antes`, `x_despues`, `y_despues`;
- `contacto_nuevo`.

Las escribe el proceso principal, a un temporal y después `os.replace`, antes del parcial de la celda. Sólo cuentan los nombres exactos (una copia de conflicto de OneDrive no). El control y el experimento exigen la biyección entre trazas y filas que las requieren.

Se esperan 44 trazas, con un intervalo de Poisson al 95 % de [31, 57]. Salen de 11 episodios con traza en las 100 semillas vistas, por 4 (`resultados/potencia_R.txt`). El control produce las de las semillas vistas.

## 4. Plan de análisis (`analizar_experimento_R.py`)

Se escribió y se probó antes de fijar:
- sobre `experimento_Q_completo.csv` + `experimento_Q_EXPLORATORIO_S2_S3.csv` (`--prueba-sustituto`, salida `resumen_R_prueba_sobre_Q.txt`);
- sobre datos sintéticos con la Parte B y sus trazas, en `test_experimento_R.py`.

Después del control se corre SIN CAMBIOS sobre `control_bit_a_bit_R.csv` y sus trazas (`--prueba-control`, salida `resumen_R_prueba_sobre_control.txt`). Es la prueba del pipeline completo. Los modos de prueba llevan "PRUEBA DEL ANÁLISIS SOBRE DATOS VISTOS, NO ES EL RESULTADO DE R".

Los sha256 de `analizar_experimento_R.py`, `potencia_R.py`, `comparar_ast_R.py` y `test_experimento_R.py`, y la HUELLA_R, van a la entrada pre y al correo de D5 al fijar (§5.1). Todo cambio posterior a cualquiera de ellos es una desviación declarada con diff, aunque lo detecte la prueba sobre el control.

En modo resultado el análisis se niega a correr en cualquiera de estos casos:
- el prerregistro no está fijado;
- las semillas no son 420110–420509;
- hay una fila repetida;
- falta una traza.

Secciones de `resumen_R.txt`, en orden:
1. ENCUADRE;
2. PRERREGISTRO (sha256 y línea «Fijado»);
3. VERIFICACIÓN (líneas de `comparar_ast_R.txt`, `control_bit_a_bit_R.txt`, `pasabilidad_R.txt` y `registro_R.txt`, incluidas las verificaciones al empezar y al terminar);
4. RESULTADOS POR HIPÓTESIS (H1…H6b con la palabra del §2.4);
5. SENSIBILIDAD de Holm;
6. EVENTOS RAROS (12 celdas, "no aplica" en ctrl), INFACTIBLE ACTIVO y AGOTADOS de S1 y S2;
7. COSTO EN TAREA: din − ctrl sobre `cobertura_accesible`, din − quieto sobre `cob_acc_arranque`, intervención din − ctrl;
8. INTERVENCIÓN;
9. DIAGNÓSTICO RETROSPECTIVO SOBRE SEMILLAS VISTAS (del control: descriptivo, no cuenta como prueba de H6);
10. LO QUE R NO SUSTENTA (el §6 de este archivo, palabra por palabra: el script lo lee de acá).

Los denominadores de la cobertura son los del §3.6 de `tesis/PROPUESTA_expO_dinamico.md` (sha256 `91bbdc8981bfa17601a704bdc8d53593f33f51d20dc3a314e68482630ebe6e00`): din − ctrl sobre la cobertura fuera de la máscara permanente propia, din − quieto fuera de la máscara de arranque.

Figuras, con la leyenda fuera del área de datos y el rótulo arriba de los ejes:
- `fig_R_costo.png`;
- `fig_R_intervencion.png`;
- `fig_R_fallback_distancia.png`: los episodios din bajo 0,10 m, con la distancia del `agente_d_min` contra el paso y las decisiones en fallback marcadas. Sólo si la Parte B es evaluable.

`verificar_cifras_R.py` se escribe y se prueba sobre el sustituto ANTES del manifiesto pre, que lo exige. Recalcula cada cifra y cada palabra de veredicto con código propio: Clopper-Pearson y McNemar sin scipy, comparados a 10 decimales con los de scipy. Tiene dos partes:
- un núcleo fijo, sin literales, que entra al manifiesto pre;
- un archivo de literales posterior a la corrida, declarado como tal.

En las mutaciones del cierre, al menos una por documento invierte un veredicto.

## 5. Compuertas y orden

1. **Código, tests y comparador: hechos.** 48 pruebas en verde y las cuatro comprobaciones de `comparar_ast_R.py` en OK. El estado al fijar se lista en la tabla de abajo, y va a la entrada pre y al correo.
2. **Este prerregistro se fija** (fecha y hora en la línea «Fijado» y sha256 impreso y mandado por correo, D5). **[OK José]**
3. **`control`.** Corre los 1200 episodios vistos y exige 66 columnas idénticas en texto, los autochequeos y las trazas. De los 1200, 1100 se reproducen por PRIMERA vez: antes sólo S1_din se había recalculado. **[listo de José]**
   - El registro dice «CONTROL: OK» o «CONTROL: NO REPRODUCE», y aparte «PARTE B: OK» o «PARTE B: NO».
   - El registro del control y el de la pasabilidad llevan la línea «PREREGISTRO_R.md sha256 … (Fijado: AAAA-MM-DD HH:MM)», con el sha256 de este archivo y su línea «Fijado».
   - Si un episodio no reproduce, se diagnostican hasta 10 con `Q._tarea_Q` en un proceso nuevo, con tres resultados posibles:
     - Q da el CSV y R no: la falla es de R. Se corrige, cambia la HUELLA_R, se rehace `comparar_ast_R.py` y se repite el control completo, como desviación declarada con diff;
     - Q da lo mismo que R y distinto del CSV: la referencia no se reproduce, o derivó el entorno (intérprete o procesador, que el registro anota). Se PARA y se declara como hallazgo del exploratorio. R no corre sin una adenda fechada, decidida antes de ver ninguna semilla nueva;
     - ni Q ni R dan la referencia y difieren entre sí: se PARA y se diagnostica.
4. **`pasabilidad`.** Usa `Q._pasabilidad_semilla` y el criterio de `Q.pasabilidad` en las 400 semillas. Si no pasa, no se cambian niveles ni semillas sin reabrir este prerregistro. **[listo de José]**
5. **Prueba del análisis sobre el control, `verificar_cifras_R.py` (núcleo) y `manifiesto_R_pre_*.txt`** (sha256 de todo lo de la carpeta salvo los logs). El manifiesto se niega a hacerse si ya hay resultados de `experimento`.
6. **`experimento`.** Se niega si falta cualquiera de estas aprobaciones: **[listo de José]**
   - `comparar_ast_R.txt` en OK con la HUELLA_R actual;
   - el control en OK con la HUELLA_R, el sha256 de este prerregistro y el mismo intérprete;
   - la pasabilidad en OK con la huella de Q, la firma de las semillas y el sha256 de este prerregistro;
   - todas las entradas del último manifiesto pre con su sha256 actual;
   - el control sin «PARTE B: NO», salvo `--sin-parte-b` (§7).

   **Al empezar** cada subcomando largo se exige:
   - el prerregistro fijado;
   - huellas, copias del Exp O, stack y los seis crudos del Exp Q intactos;
   - el árbol del Exp Q igual a su referencia (97 archivos);
   - ningún otro proceso de corrida ni del laboratorio: scripts del coordinador, MATLAB, Webots. Si no se puede comprobar, PARAR. La exclusión es simétrica: el chequeo previo de la PC del laboratorio (`PROTOCOLO_L0_L2.md:71`) busca a su vez los scripts de R desde el 09-11;
   - la PC enchufada, también antes de cada celda;
   - ningún reinicio pendiente de Windows;
   - el chequeo de congelados de `PROTOCOLO_L0_L2.md:210` en "IGUAL a lo probado".

   **Al terminar** se repiten las huellas, las copias, el stack, los crudos, el árbol, los congelados y los procesos, y en `experimento` el manifiesto pre. La energía se registra. Todas esas líneas quedan en el registro.

   Antes de escribir cada parcial se comprueba que el código con que corrieron los trabajadores y el del disco sean los de la firma. R se corre sólo en días sin laboratorio ni réplica de la campaña, dentro del horario activo de Windows (08–02) o con las actualizaciones pausadas, y José anota la hora.
7. **Cierre** con los criterios del §6 del spec, `manifiesto_sha256_R.txt` y la entrada de resultados en la bitácora. **[OK José]**

**Estado del código al fijar** (calculado y confirmado al fijar):

| Archivo o huella | sha256 |
|---|---|
| HUELLA_R (`correr_experimento_R.py` + huella de Q) | `c31f8cd6f4524804e51be7807bdd8a75e1a07885615791e251214708379f5a80` |
| `correr_experimento_R.py` | `717c47a66c7c4d9cf0afa841881821e10878c1a0107596e8b4cbec9a4e4f6f39` |
| `comparar_ast_R.py` | `fff0f75a3551d493b0e82b9e5dbc62fb72edc0c30bf2b2f91d33372e858f7579` |
| `analizar_experimento_R.py` | `5c2e8c3a6be93a71d49083e44fb673a848daa8126045067bdb70b327dab47f3e` |
| `potencia_R.py` | `cc68d0699fef9a320cadc527a2a2e6f00372ecbc55496255c2c0c497903982ae` |
| `test_experimento_R.py` | `269d543d1fc3e2783ffba010a073097daa426461aa3d2372979239dd7a8ea34b` |

## 6. Lo que R no sustenta (escrito antes de correr)

- un cambio del veredicto del Exp Q (S1 detiene por la regla del Exp O);
- que S2 o S3 "pasen" la regla del Exp O (con la regla, S2_din y S3_din la dispararon en el exploratorio);
- que la garantía de no contacto sea robusta donde hay fallbacks: ahí, por construcción, el filtro manda u = (0, 0) sin certificado;
- que una H5a "cumplida" sea tasa cero de contacto: 0/400 sólo la acota bajo 0,918 % por nivel;
- que una H5a "no cumplida" muestre que el filtro falla: con una tasa pequeña pero no nula es el resultado probable aunque el filtro funcione (§8), y cada contacto se discute con su traza;
- que una prueba "no sostenida" sea ausencia de efecto: H1-S2, H3b y H5b tienen potencia predictiva de 0,58 a 0,80 (§8);
- que el fallback cause el acercamiento: H6 mide coincidencia en el tiempo, hacia atrás, con un umbral (0,10 m) y una ventana (W = 5) fijados sobre el exploratorio;
- que se conserve la cota de diseño de 0,13 m fuera de los fallbacks;
- nada sobre el laboratorio, ni sobre el rescate de F2, que no se corre;
- nada sobre otras políticas, otros entrenamientos, otros puntos de control ni otras geometrías o velocidades del obstáculo;
- una verificación independiente del código: un error sistemático se replicaría igual;
- la separación de las dos vías de infactibilidad (h < s/α frente a la erosión del margen hasta h < 0): la Parte B no registra h ni s.

## 7. Desviaciones y contingencias

Toda desviación de este prerregistro se declara en la bitácora, con el antes, el después y el diff.

**Contingencia prevista: la Parte B.**
- **Si falla en el control** («PARTE B: NO»): se busca la causa antes de tocar nada (§3.3). Si está en las líneas `[R]` o en las funciones de la Parte B, se corrige y se repite el control (nueva HUELLA_R), como desviación declarada.
- **Si no se puede corregir**, `experimento` corre con `--sin-parte-b`. H6a, H6b y la ubicación de los contactos de H5a quedan "no evaluable", y H1–H5 se leen igual. Se declara con una adenda fechada en archivo aparte, decidida antes de correr las semillas nuevas.
- **Si falla en el experimento** sobre las semillas nuevas: el registro dice «PARTE B: NO», con qué episodios fallaron qué autochequeo y la constancia de que las 66 columnas siguen siendo válidas por construcción (§3.3). El CSV completo se escribe igual, y H6 y la ubicación de los contactos de H5a quedan "no evaluable" por esta regla, sin adenda.

**Lo que siempre detiene.** Una falla del control en las 66 columnas («CONTROL: NO REPRODUCE») o filas incompletas en el experimento detienen siempre. Este archivo no se toca.

## 8. Potencia a priori (`potencia_R.py` → `resultados/potencia_R.txt`)

Bootstrap pareado por semilla sobre las 100 semillas vistas, 20 000 réplicas, con las reglas de lectura del §2.4. "Plug-in" toma las tasas vistas; "predictiva" agrega su incertidumbre (pesos de Dirichlet).

| Prueba | Discordantes vistos (b/c de 100) | Plug-in | Predictiva |
|---|---|---|---|
| H1-S3 | 5/0 | 1,0000 | 0,9692 |
| H1-S2 | 2/0 | 0,8152 | 0,5784 |
| H2-S2 | 10/0 | 1,0000 | 0,9999 |
| H2-S3 | 28/9 | 1,0000 | 0,9776 |
| H3a | 8/0 | 1,0000 | 0,9990 |
| H3b | 8/3 | 0,8336 | 0,6894 |
| H5b | 3/0 | 0,9813 | 0,8024 |
| H4 (las dos piezas) | — | 1,0000 | 0,9847 |

En el punto, con c = 0, la McNemar exacta bilateral exige b ≥ 6 (2·0,5⁵ = 0,0625; 2·0,5⁶ = 0,03125). A n = 400, P(b ≥ 6) es:

| Tasa | P(b ≥ 6) |
|---|---|
| 1 % | 0,2141 |
| 2 % | 0,8115 |
| 3 % | 0,9810 |
| 5 % | 0,9999 |
| 8 % | 1,0000 |

La cota de Clopper-Pearson de 0/400 es 0,918 %.

**Riesgos de potencia aceptados.**
- **H1-S2 (0,58–0,82) y H3b (0,69–0,83).** Un "no sostenida" ahí es un resultado válido y se escribe así; no se agregan semillas después de ver el dato.
- **H5a (primaria).** Con 0/100 vistos y una previa de Jeffreys, la probabilidad de 0/400 es ≈ 0,45 por nivel y ≈ 0,09 en los tres niveles si fueran independientes. Es una cota pesimista, porque S1 y S2 tienen más margen que S3. Aun con riesgo casi nulo en S1 y S2, la probabilidad de "cumplida" es ≈ 0,45: "no cumplida" es, a priori, el resultado más probable. Es plausible un contacto en S3_din, cuyo mínimo del exploratorio quedó a 3,9 mm del disco de contacto.
