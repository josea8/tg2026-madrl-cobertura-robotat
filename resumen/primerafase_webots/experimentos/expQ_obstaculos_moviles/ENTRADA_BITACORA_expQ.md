## Exp Q — Obstáculos MÓVILES como barreras de ejecución (Python, versión dinámica del Exp O, 100 eps)

**Encuadre — leer antes que los números.** Igual que el Exp O, esto **NO** prueba adaptabilidad de la política: la observación no codifica obstáculos y el agente es ciego a ellos. Prueba la **generalidad de la capa de seguridad** frente a obstáculos que se mueven, y su costo en progreso de tarea. Diseño, decisiones y estimación: `tesis/PROPUESTA_expO_dinamico.md`, aprobada por José el 19-10 con las nueve decisiones recomendadas. La letra Q ya figuraba en `PROPUESTA_OBSTACULO_MOVIL.md` (01-10) con otro diseño, que no se eligió; la P es el prerregistro del Exp J.

### Qué no cambia y qué es nuevo

**Igual que el Exp O, verificado:**
- `modelo_sanidad.zip` (sha256 `34831589…0c27`, el mismo del Exp O y el congelado de la campaña), sin reentrenar;
- el filtro, el escape y todos sus parámetros, importados de copias byte a byte del Exp O (`lib/`, `entorno_obstaculos.py`, `correr_experimento_O.py`; sha256 verificado al arrancar cada subcomando);
- el protocolo: n = 5, arena 3.0, 500 pasos, semillas 420000–420099, bordes bloqueantes.

**Lo único nuevo** (`entorno_obstaculos_moviles.py`, `correr_experimento_Q.py`):
1. **Los obstáculos se mueven:** círculos antihorarios a 0.05 m/s, con la fase inicial sorteada por semilla (`default_rng([semilla, 3])`). En cada paso, los obstáculos pasan de t a t + 1 antes de integrar a los agentes, y el contacto del Exp O se evalúa contra los discos en t + 1.
2. **La fila del obstáculo es la F1 de la campaña:** rhs = −α·h + s/k con k = 1 y s = max(0, n·v_o), donde v_o es la secante del paso; saturada al 90 % de la capacidad sólo con s > 0; h_eq = −rhs/α. Con s = 0 es la fila del Exp O, el mismo objeto. No entran el predictor, el peso de giro, el rescate ni el freno de F2.

**Por las decisiones de José:**
- S1 es el obstáculo del Exp O (r 0.30) en el círculo de la campaña (R 0.60). S2 y S3 son círculos de ρ 0.20 y 0.06 alrededor de las posiciones del Exp O.
- Los objetivos son **transparentes**: la dinámica de objetivos es idéntica en todas las condiciones, así que no hace falta control fantasma.
- La máscara es la permanente: centro dentro de r en los 501 instantes.
- Las reubicaciones de arranque son las del Exp O, respecto de la posición inicial del obstáculo.
- Cuatro condiciones pareadas por semilla: `Sk_din`, `Sk_quieto` (los mismos obstáculos quietos en su arranque), `Sk_ctrl` y `Sk_sinvel` (descriptiva, sin el término de velocidad).

### Verificación antes de correr

**Control bit a bit (obligatorio).** Por el camino NUEVO, con trayectorias quietas en las posiciones del Exp O, salieron **idénticas en texto (repr de cada float) las 1000 corridas distintas del Exp O**:
- 700/700 filas en las 43 columnas de `experimento_O_completo.csv`;
- 900/900 en las 49 de `experimento_O_complementario.csv`;
- todas las columnas salvo `t_episodio_s`.

**Pasabilidad a lo largo de la trayectoria** (§3.2 de la propuesta). Huecos > 0.48 y región conexa con h ≥ 0 y con h ≥ 0.06, con rejilla de 0.01, en los 501 instantes de las 100 semillas; además, el chequeo exacto del Exp O en el peor instante de cada semilla. Los huecos mínimos, iguales al peor caso analítico:

| | hueco obstáculo–pared | hueco obstáculo–obstáculo | instantes | fallidos |
|---|---|---|---|---|
| S1 | 0.6000 | — | 50100 | 0 |
| S2 | 0.5500 | 0.5142 | 50100 | 0 |
| S3 | 0.4900 | 0.4907 | 50100 | 0 |

Una versión anterior del chequeo, que corría el del Exp O en todos los instantes, también dio S1 y S2 pasables. La sesión se cortó en S3 y se cambió a lo aprobado.

**Control negativo de la instrumentación.** El obstáculo móvil de S1 sin su fila en el filtro, 10 semillas:
- **628 contactos (37 por empuje) en 10/10 episodios;**
- el contador ve el contacto con algo que se mueve.

**Pruebas:** `test_experimento_Q.py`, 23 pruebas. Entre ellas: la F1 contra la fórmula de la campaña; el entorno quieto igual a `EntornoObstaculos` paso a paso; los objetivos transparentes; la máscara; el empuje y el avance; los tiempos del bucle con movimiento (decisión en t, distancias en t + 1); y dos episodios completos iguales al Exp O.

### Resultado — S1 dispara la parada; S2 y S3 no se corren

| S1 | `S1_ctrl` | `S1_quieto` | `S1_din` (decide) | `S1_sinvel` |
|---|---|---|---|---|
| Contactos con obstáculo | — | 0 | 0 | 0 |
| Colisiones < 0.15 m | 0 | 0 | 0 | 0 |
| Fallbacks del QP | 0 | 0 | 0 | 0 |
| Filas F1 saturadas | — | 0 | 0 | 0 |
| Escapes agotados | 1 | 2 | **1** | 2 |
| Infactibles con obstáculo activo | — | 0 | 0 | 1 |
| d_min centro→superficie, mínimo global | — | 0.16846609 | 0.12495033 | 0.12478619 |
| Intervención media (indicador) | 0.397176 | 0.524344 | 0.547856 | 0.547556 |
| Episodios con intervención > 0.5 | 15/100 | 58/100 | 73/100 | 74/100 |

**Por la regla del Exp O, fijada antes de correr, `S1_din` falla:** tiene 1 escape agotado. Por eso no se corren S2 ni S3.

**La lectura que va con el veredicto.** El agotado **no lo induce el obstáculo**:
- es el de la semilla 420001, que tiene un agotado en las CUATRO condiciones, incluido el control sin obstáculos;
- la Δ pareada din − ctrl de agotados es exactamente 0, sin ninguna semilla a favor ni en contra;
- en esa semilla la regla de arranque reubica 2 agentes respecto del punto de partida del obstáculo, y con esas poses el escape se agota aun sin obstáculo. En el S0 del Exp O, sin reubicación, esa semilla no tiene agotados.

Es la salvedad que el Exp O ya había declarado ("los agotados no son específicos del obstáculo") y que la propuesta dejó como estaba. **El veredicto se reporta tal cual, como el límite de la arquitectura con este criterio, y no se ajusta nada.**

**Seguridad: intacta.** En `S1_din` no hay ningún contacto con el obstáculo, ninguna colisión, ningún fallback del QP y ninguna fila saturada.
- El mínimo centro→superficie es 0.12495033 m, por debajo de la cota de diseño de 0.13 m en 2 agente-episodios.
- Es la erosión por discretización ya documentada: el centro quedó a más de 4.9 cm del disco de contacto. Es el mismo fenómeno del S2 del Exp O (0.12876785).

**Hipótesis previa, no confirmada.** La propuesta (§2.3) esperaba, si algo fallaba, un fallback del QP en un encierro: con el obstáculo en movimiento, u = 0 deja de ser factible cuando h < s/α. No hubo ningún fallback ni ninguna fila saturada. El encierro no apareció en S1.

**Costo en tarea (pareado, 100 semillas):**

| Comparación | Cobertura (denominador) | Δ | IC95 |
|---|---|---|---|
| din − ctrl | accesible (máscara permanente: vacía en S1) | +0.03331428 | [+0.02030114, +0.04632743]* |
| din − quieto | fuera de la máscara de arranque | +0.01298304 | [+0.00209123, +0.02387485]* |
| quieto − ctrl (descriptiva) | fuera de la máscara de arranque | +0.02106630 | [+0.00793127, +0.03420133]* |
| sinvel − din (descriptiva) | accesible | +0.00042739 | [−0.00819487, +0.00904964] n.s. |

- **El obstáculo móvil no cuesta cobertura: la sube,** y más que el quieto en su mismo arranque.
- Como los objetivos son transparentes, la dinámica de objetivos es idéntica en las condiciones y **la subida es del sistema**. Es la confusión que el Exp O tuvo que resolver con el fantasma; acá queda descartada por construcción.
- Va en el sentido del Exp O con obstáculos descentrados (S2 +0.0288*, S3 +0.0183*). La hipótesis sin verificar de las trayectorias repetitivas que se rompen sigue sin verificar.

**Intervención y mecanismo** (se lee por restricción ligante; en `S1_din` el "h mínimo" usa h_eq y se inclina hacia el obstáculo por construcción):
- **din − ctrl:** +0.15068000 [+0.12957251, +0.17178749]*. De eso, el obstáculo ligante aporta +0.097652 y la pared ligante +0.04834400 [+0.02882004, +0.06786796]*.
  - La ocupación de la periferia sube +0.05712000 [+0.04235515, +0.07188485]*.
  - Es el canal indirecto del Exp O: el obstáculo empuja hacia las paredes.
- **din − quieto:** +0.02351200 [+0.00371723, +0.04330677]*, casi todo del obstáculo (+0.01441200 [+0.00548351, +0.02334049]*).
  - La pared ligante (+0.00577200 [−0.01286624, +0.02441024]) y la periferia (+0.00014 [−0.0135, +0.0137]) no cambian.
  - Lo que agrega el movimiento es **intervención directa del obstáculo, no más desplazamiento hacia las paredes**.
- **Exposición en `S1_din`:** fila del obstáculo activa (h < 0.06) en el 0.10824800 de las agente-decisiones, y activa y acercándose en el 0.05749600.
- **Parte de ω en c·u en las filas ligantes con el obstáculo acercándose: 0.369415** sobre 12914 filas. El QP paga el término de velocidad sobre todo trasladando, y el ciclo de giro de la Fase 0 no aparece sin retardo.

**El término de velocidad, sin retardo (decisión 9, descriptiva):** `S1_sinvel` − `S1_din` no se distingue de cero en intervención (−0.00030000 [−0.01184459, +0.01124459]) ni en cobertura. El mínimo es casi igual: 0.12478619 sin el término contra 0.12495033 con él. Sin el término apareció 1 escape infactible con el obstáculo activo (semilla 420042), y con el término ninguno.
- **Lectura:** con retardo cero y a 0.05 m/s, la fila del Exp O en la posición actual ya contiene al obstáculo en S1.
- El término de velocidad es necesario en el laboratorio por el retardo (Fase 0). Este experimento no lo distingue en Python.

### Qué afirmación del documento sustenta

**RESPALDA, con el límite caracterizado:**

> "Con un obstáculo que se mueve a 0.05 m/s y que la política no percibe, la capa de ejecución extendida con el término de velocidad mantuvo la seguridad en simulación: cero contactos, cero colisiones, cero fallos del solver. El movimiento agrega intervención directa del obstáculo, pero no cuesta cobertura. El nivel se detuvo por un escape agotado que también ocurre, en la misma semilla, sin obstáculos."

**No sustenta:**
- nada sobre S2 ni S3, que no se corrieron;
- nada sobre el laboratorio: Python con retardo cero y k = 1 es el caso más favorable para F1;
- adaptabilidad de la política;
- "el término de velocidad hace falta": en Python sin retardo no se distingue.

**Artefactos:** `experimentos/expQ_obstaculos_moviles/`:
- **copias:** `lib/`, `modelos/`, `entorno_obstaculos.py` y `correr_experimento_O.py`, verificadas por sha256;
- **código nuevo:** `entorno_obstaculos_moviles.py`, `correr_experimento_Q.py`, `analizar_experimento_Q.py`, `verificar_cifras_Q.py`, `test_experimento_Q.py` y `comparar_ast_Q.py`;
- **en `resultados/`:**
  - los datos: `experimento_Q_completo.csv` (400 filas, sin redondeo), `control_bit_a_bit_Q.csv` (1000) y `control_negativo_Q.csv` (10);
  - los registros: `registro_Q.txt`, `pasabilidad_Q.txt`, `control_bit_a_bit_Q.txt` y `control_negativo_Q.txt`, todos con la huella `e265b6cd…4a29`;
  - las salidas: `resumen_experimento_Q.txt`, `corrida_Q.log`, `corrida_Q_preparacion.log` (la corrida cortada), `parciales/`, `comparar_ast_Q.txt`, `manifiesto_expO_pre_20261019.txt` y `manifiesto_sha256_Q.txt`;
- **en `figuras/`:** `fig_obstaculos_moviles_intervencion.png` y `fig_obstaculos_moviles_costo.png`.

**Cierre:**
- `verificar_cifras_Q.py` recalcula cada cifra del resumen y de esta entrada (resumen 1338/1338, entrada 105/105, pareo 300/300);
- la comparación por AST da sólo clases y funciones nuevas, con el Exp O intacto (`comparar_ast_Q.txt`);
- el chequeo de congelados de la campaña da "IGUAL a lo probado" antes (16:42) y después (18:41).

**Revisión adversarial** (4 revisores, sólo lectura): fidelidad bit a bit, conformidad con la propuesta, análisis y verificador.
- **Sin hallazgos de severidad alta en el código de la corrida.**
- **Se corrigió en el análisis y el verificador:** el mecanismo pasó a leerse por restricción ligante; se agregaron la completitud según §3.6, el pareo y el veredicto con la bitácora obligatoria; salieron de la tabla `cob_acc_din` y `cobertura_protocolo`, sesgadas en el quieto; se agregaron los infactibles por motivo.
- **Se corrigió en la corrida, antes de lanzar la definitiva:** la huella se toma al empezar, la reanudación es por condición y la comparación del control es estricta por texto.

**Declarado, sin cambio:**
- el stack no entra en la huella (se registra: igual a `requisitos_congelados_2026-09-09`);
- los agente-episodios con contacto no se separan por empuje y por avance;
- un agente empujado se desplaza más que el umbral del detector de atasco, así que bajo empuje el escape no se arma.

**Costo:**
- pasabilidad 89 + 119 + 256 s, control 809 s y S1 309 s, con 11 procesos y la máquina compartida con 8 procesos de MATLAB;
- el chequeo de la PC del protocolo dio FALLA (Chrome, ChatGPT, OMEN, Inventor). No afecta los resultados: no hay tiempo real y la corrida es determinista.
