# Preregistro — Experimento P

**Confirmación con semillas nuevas de la configuración ganadora del Exp J y del
Trial 13.** Fijado el 2026-09-24, ANTES de entrenar ninguna semilla nueva. Su
sha256 queda registrado en `manifiesto_P.json` y en cada evento de lanzamiento
de `resultados/registro_corridas.jsonl`. Cualquier desviación se declara como
tal en la entrada de la bitácora; este archivo no se edita después del
lanzamiento.

## 1. Propósito

**Estimación, no prueba de superioridad.** P estima, con semillas de
entrenamiento independientes de las del Exp J, la cobertura media y la
dispersión entre semillas de dos configuraciones: la ganadora del Exp J
(prueba 7) y el Trial 13 (`modelo_PRIMERO`). Se reporta la potencia junto a los
resultados. Ningún resultado de P cambia la decisión de no adoptar la
configuración del Exp J: la cadena de validación A–O se midió sobre
`modelo_PRIMERO` / `modelo_sanidad`.

**Por qué hace falta** (hallazgos verificados el 2026-09-24):

- **Nadie volvió a entrenar la ganadora con semillas nuevas.** Sólo se
  entrenó con 42, 123 y 777. El diagnóstico a 500k repite bit a bit la misma
  trayectoria hasta los 200k, así que no es una réplica.
- **El +0.0126 de la bitácora no compara cantidades homogéneas.** De un lado
  está la media de 3 semillas en su punto retenido; del otro, 1 semilla del
  Trial 13 en su punto final.
- **No existe ninguna medición del Trial 13 con varias semillas a 200k.**
- **El CV de 0.0126 de la ganadora está medido en el punto retenido.** A paso
  fijo de 200k su σ entre semillas es 0.056 (CV 0.089), del orden del CV del
  Trial 13 en H-05.
- **El conjunto final (offset 1000) no es independiente de la selección.**
  Fue el objetivo de TPE, así que favorece a la ganadora por selección.

## 2. Diseño

| Elemento | Valor fijado |
|---|---|
| Brazos | `ganadora` (λ_cbf 14.774443600789574, λ_ent 0.8719802820096347, n_epochs 8, n_steps 64) y `trial13` (λ_cbf 2.9655314099141474, λ_ent 1.1403296484190344, n_epochs 13, n_steps 128); los 8 restantes son los del Trial 13 en ambos |
| Semillas de entrenamiento | **1001–1020** (lista ordenada fijada a priori; N = 20 por brazo). Las mismas en ambos brazos |
| Presupuesto | 200 000 pasos por semilla, retención por cobertura cada 20 000 (código del Exp J sin cambios) |
| Orden | En serie, intercalado: 1001-ganadora, 1001-trial13, 1002-ganadora, … |
| Código | Modo trabajador de `estudio_J.py` (`--worker_semilla/--worker_dir/--worker_config`), desde una **copia propia** en `lib/` idéntica por sha256 a los originales (`estudio_J.py`, `train.py`, `swarm_env_skeleton.py`, `concentration_dynamics.py`). Ningún original se modifica |
| Configuraciones | `config/ganadora.json` = copia byte a byte de `cfg_eb1d01e59b/config_barridos.json`; `config/trial13.json` desde `RESULTADO_PRIMERO/hiperparametros.json`, verificado contra `materializar_configuracion` |
| Salidas | Sólo dentro de `fase_preliminar2/experimento_P/` |
| Intérprete y entorno | Python 3.13.14 de la Store (torch 2.10.0+cpu). Las variables de hilos de la sesión (`OMP_NUM_THREADS=12`) se registran en el manifiesto y no se cambian, igual que en el Exp J |

**Paso fijo.** El «paso fijo 200k» es el `_punto_control_actual.zip` con
`num_timesteps = 200000`. En ambos brazos tiene los pesos de 199 680 pasos:

- ganadora: 156 actualizaciones de 1280 pasos;
- Trial 13: 78 actualizaciones de 2560 pasos.

El 200k del brazo Trial 13 **no es `modelo_PRIMERO`**, que tiene 202 240 pasos
y 79 actualizaciones.

**Pesos de recompensa en la evaluación.** Se usan los del brazo, como en el
Exp J. Con `domain_rand=False` y una política determinista, la cobertura y las
colisiones no dependen de ellos.

### Conjuntos de episodios (semillas `42·10000 + offset + i`)

| Conjunto | offset | n | Semillas | Rol |
|---|---|---|---|---|
| Retención | 0 | 20 | 420000–420019 | elige el punto retenido (código del J) |
| Final | 1000 | 30 | 421000–421029 | objetivo de TPE en el Exp J; secundario |
| **Nuevo** | **2000** | **100** | **422000–422099** | **primario**; no participó en ninguna selección |

## 3. Controles previos — reglas de parada

Se corren antes de la primera semilla nueva. Si alguno falla, **P se detiene y
se reporta la diferencia, sin ajustar nada**.

- **C1.** Se evalúa `modelo_PRIMERO` con el evaluador de la copia, en 100
  episodios con offset 0. Tiene que dar **0.6812908187508583** a seis
  decimales (regla de CLAUDE.md §5). Además se compara con los 100 episodios
  de `metricas_100eps.json`, uno por uno.
- **C3.** Se corre la heurística NN sobre el entorno de la copia, en 100
  episodios con los pesos del Trial 13. Tiene que dar **0.25434854030609133** a
  seis decimales, y se compara episodio por episodio.
  - La función es una copia textual de `consolidar_resultado_primero.py`,
    verificada por sha256. Ese módulo no se importa porque trunca un log
    oficial al importarse.
- **C2.** Se reentrena la semilla 42 de la ganadora en una carpeta nueva. Tiene
  que reproducir **bit a bit** la corrida del Exp J (`cfg_eb1d01e59b/semilla_42`):
  - todas las claves de `resultado_semilla.json` salvo los tiempos: paso
    retenido 140000 y cobertura_final 0.6908460726340612;
  - el sha256 de `policy.pth` y de `policy.optimizer.pth` en los puntos de
    140k y 200k.

Durante la corrida:

- **Alimentación:** corriente alterna obligatoria (`GetSystemPowerStatus`,
  `ACLineStatus = 1`). Si se pierde, el orquestador pausa hasta que vuelva.
- **Carga de CPU:** se registra por semilla.
- **Otras sesiones:** ninguna otra sesión corre carga pesada ni escribe en la
  bitácora mientras P esté corriendo.
- **Semillas fallidas:** se registran y se sigue con la siguiente. No se
  imputan: se reporta el n efectivo.

## 4. Métricas (definidas a priori)

La unidad de análisis es la **semilla**. La métrica de cada semilla es la
media sobre los episodios del conjunto.

- **Primaria:** `cob_retenido_nuevo`, la cobertura AoI final del punto
  retenido sobre el conjunto nuevo.
- **Secundarias:**
  - `cob_retenido_final`: el punto retenido sobre el conjunto final. Es el
    objetivo del Exp J y se comprueba exactamente contra el JSON del
    trabajador.
  - `cob_fijo200k_nuevo` y `cob_fijo200k_final`: el modelo de
    `num_timesteps = 200000`, en cada conjunto.
- **Descriptivas:**
  - colisiones (pares a menos de D_SAFE = 0.15 m, política desnuda) en los
    cuatro cruces;
  - la distribución del paso retenido;
  - el CV entre semillas del punto retenido frente al paso fijo, en cada
    brazo.

## 5. Análisis

- **Por brazo y métrica:** n, media, DE (ddof = 1), CV, mediana, IQM (media
  recortada al 25 %) y mínimo/máximo.
  - IC95 de la media: t y bootstrap percentil.
  - IC95 del IQM: bootstrap.
- **Diferencia ganadora − Trial 13:** IC95 de Welch y bootstrap con remuestreo
  independiente por brazo.
  - Se tratan como muestras independientes: compartir semilla no correlaciona
    las trayectorias porque los hiperparámetros difieren.
  - Se reporta también la diferencia de IQM con su IC95 bootstrap.
- **Bootstrap:** B = 10 000, `numpy.random.default_rng(20260924)`.
- **Sin valores p de decisión.** Las semillas 42/123/777 del Exp J no se
  mezclan con las nuevas; se citan aparte como contexto.

### Potencia a priori (Welch bilateral, α = 0.05, δ = 0.0126, n = 20 por brazo)

| Escenario (σ ganadora, σ Trial 13) | Potencia | Efecto mínimo detectable al 80 % |
|---|---|---|
| 0.0086, 0.0086 (optimista, σ del J con n = 3) | 0.995 | 0.0078 |
| 0.0156, 0.0156 (σ agrupada de las 5 mejores del J) | 0.702 | 0.0142 |
| 0.0086, 0.0537 (Trial 13 con σ de H-05 reproducibilidad) | 0.167 | 0.0358 |
| 0.0086, 0.0909 (Trial 13 con σ de H-05 multimétrica) | 0.090 | 0.0602 |
| 0.0557, 0.0909 (paso fijo 200k) | 0.081 | 0.0689 |

Con n = 20, el IC95 de una media tiene una semiamplitud de 0.468·σ:

| σ | Semiamplitud |
|---|---|
| 0.0086 | ±0.0040 |
| 0.0156 | ±0.0073 |
| 0.0557 | ±0.0261 |

Una σ estimada con n = 3 tiene un factor de incertidumbre de ×0.52 a ×6.3: la
tabla es orientativa. Junto a los resultados se reportan dos cosas con las DE
observadas: la potencia para δ = 0.0126 y el efecto mínimo detectable al 80 %.
No se reporta la potencia "observada" con el efecto observado.

## 6. Lo que P no hace

- No prueba superioridad ni adopta modelos.
- No reentrena las semillas 42, 123 ni 777, salvo la 42 como control. El
  entrenamiento en CPU es determinista, así que repetirlas no aporta
  información.
- No modifica el entorno, la recompensa, la arquitectura ni los
  hiperparámetros.

## 7. Estimación de tiempo

Tiempos del Exp J, con la máquina en reposo:

| Tramo | Duración |
|---|---|
| Por semilla de la ganadora | ~3.9–5.5 min |
| Por semilla del Trial 13 | ~4.7–6.9 min |
| Controles | ~8 min |
| Evaluación auxiliar | ~1.5 min por modelo, ~60 min en total |
| **Total** | **~4–5.5 h** |

Con carga ajena el tiempo puede duplicarse.
