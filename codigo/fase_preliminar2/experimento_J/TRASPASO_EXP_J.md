# Traspaso — Experimento J

Documento de continuidad para retomar el Experimento J sin releer la sesión que
lo produjo. Los resultados y su interpretación están en
`primerafase_webots/BITACORA_TECNICA.md` (sección "Exp J", línea ~999); **este
archivo NO los repite**: contiene los parámetros exactos, el estado operativo y
las decisiones y hallazgos que no quedaron en la bitácora.

**Estado general: el experimento está CERRADO.** Fase 0, estudio de 20 pruebas,
diagnóstico de presupuesto a 500k, recomputación de la referencia y análisis
están todos ejecutados y con artefactos en disco. No hay nada corriendo.

Fechas: Fase 0 el 2026-09-07; estudio, diagnóstico y análisis el 2026-09-08.

---

## 1. Parámetros exactos del diseño aprobado

Todos están codificados en `estudio_J.py` (sección CONFIGURACIÓN). Esta tabla es
la referencia canónica: si el código y esta tabla divergen, el código manda y
hay que actualizar esto.

| Parámetro | Valor | Constante en `estudio_J.py` |
|---|---|---|
| Pruebas (trials) | 20 | `--n_trials 20` |
| Presupuesto por semilla | 200 000 pasos | `PRESUPUESTO_PASOS` |
| Semillas de entrenamiento | 42, 123, 777 | `SEMILLAS_ENTREN` |
| Semilla primaria (criba + poda) | 42 | `SEMILLA_PRIMARIA` |
| Objetivo | media de cobertura AoI de las 3 semillas | `objetivo()` |
| Frecuencia de evaluación | cada 20 000 pasos → 10 por semilla | `FRECUENCIA_EVAL_TS` |
| Episodios de retención | 20, semillas `42·10000 + i` | `N_EPS_RETENCION` |
| Episodios de evaluación final | 30, semillas `42·10000 + 1000 + i` | `N_EPS_FINAL`, `OFFSET_SEMILLAS_FINAL` |
| Retención del punto de control | por COBERTURA (no por recompensa) | `CallbackCoberturaJ` |
| Envs de entrenamiento | 4 (→ 20 streams con 5 agentes) | `N_ENVS_ENTREN` |
| Trabajadores del pool de evaluación | 5; **2** en cada trabajador de confirmación, `max(2, 5 // 2)` en `estudio_J.py:703` (corregido el 2026-09-24: decía «3 en los trabajadores de confirmación», como el comentario de `estudio_J.py:151-153`, que está mal y no se edita) | `N_TRABAJADORES_EVAL` |
| Condición de borde | reflexión elástica | heredada del env |
| Agentes / pasos por episodio / arena / radio | 5 / 500 / (3.0, 3.0) / 1.0 | `N_AGENTES`, `MAX_STEPS_EP`, `ARENA`, `COMM_RADIUS` |

### Espacio de búsqueda — 4 dimensiones

Rangos IDÉNTICOS a los del estudio original, para que las correlaciones de rango
de ambos sean comparables.

| Parámetro | Rango | Tipo |
|---|---|---|
| `lambda_cbf` | 1.0 – 15.0 | float uniforme |
| `lambda_entropy` | 0.1 – 2.0 | float uniforme |
| `n_epochs` | 3 – 15 | int |
| `n_steps_exp` → `n_steps = 2^n` | 6 – 10 | int |

### Los ocho fijos (valores del Trial 13)

De `modelos/tesis_v1/RESULTADO_PRIMERO/hiperparametros.json`, replicados en
`HPARAMS_FIJOS` y `PESOS_FIJOS`:

```
learning_rate   = 6.855028382061343e-05      lambda_gradient = 0.5622468083379316
gamma           = 0.9844980522475681         lambda_ibrm     = 0.48380314172632155
clip_range      = 0.20631649325745388
batch_size      = 64
ent_coef        = 0.022872258876193912
gae_lambda      = 0.9608422073341644
vf_coef         = 0.5
max_grad_norm   = 0.5
```

### Sampler y pruner

```
TPESampler(n_startup_trials=5, seed=42)

MedianPruner(n_startup_trials=5,
             n_warmup_steps=100_000,   # EN PASOS DE ENTORNO (ver §4)
             interval_steps=1)
```

**Criba en dos etapas** (`objetivo()` en `estudio_J.py`):

1. **Etapa 1** — la semilla 42 entrena con poda intermedia POR COBERTURA, activa
   sólo desde los 100 000 pasos.
2. **Etapa 2** — si sobrevive, su cobertura se compara contra la mediana de las
   coberturas de semilla 42 de las pruebas ya COMPLETAS (`user_attr`
   `cob_semilla_42`, mínimo 5 pruebas: `MIN_TRIALS_CRIBA`). Si no la supera, la
   prueba muere sin gastar las semillas 123 y 777.
3. Sólo las que pasan ambas etapas corren las dos semillas de confirmación, **en
   paralelo**, como subprocesos independientes.

La mediana se calcula SÓLO sobre `cob_semilla_42`, nunca sobre el objetivo
promediado, para comparar cantidades homogéneas.

---

## 2. Estado de la Fase 0

**Completada, con dos corridas.** El objetivo era medir el costo antes de
comprometerlo, y dio además la verificación de control del experimento.

### Corrida 1 — `resultados/fase0_20260907_sin_evalcallback/`

Conservada a propósito. El `EvalCallback` **no se disparó ni una vez** por el bug
de unidades (§4), de modo que esta corrida es entrenamiento puro sin evaluación
periódica. Sirvió para dos cosas:

- aislar el costo del entrenamiento sin evaluaciones: 233.0 s para 200k pasos;
- **verificación de control**: entrenamiento fresco de 200k con hiperparámetros
  del Trial 13 y semilla 42 → cobertura **0.68359382748603830** contra la cifra
  oficial de referencia 0.6813. La cadena reproduce.

### Corrida 2 — `resultados/fase0/` (la válida)

Con el `EvalCallback` corregido. `reporte_fase0.json` tiene el desglose completo:

```
construccion_entornos        16.29 s
learn_total                 378.82 s
  entrenamiento_puro        306.94 s
  evaluaciones_periodicas    71.87 s   (10 evaluaciones × ~7.2 s)
protocolo_cobertura_mejor    39.75 s   (20 eps, env único sin vectorizar)
protocolo_cobertura_final    41.30 s
total_prueba                480.44 s
```

**El hallazgo que cambió el diseño:** el punto retenido por RECOMPENSA (paso
160k, rew −0.18) da cobertura **0.667724360525608**, mientras que el punto final
(200k, rew −5.76) da **0.683593827486038**. Seleccionar por recompensa produce un
modelo PEOR en la métrica objetivo. Por eso el estudio retiene por cobertura.

### Proyección de costo vs. realidad

La proyección inicial (~7 h, luego corregida a ~11 h) quedó muy por encima del
costo real.

**Corregido el 2026-09-24.** Aquí decía «el estudio real corrió en **2.07 h**
gracias a la paralelización (§5)».

- **Las 2.07 h son sólo el segundo lanzamiento** (8-sep, 01:22:48→03:27:02,
  pruebas 2–21).
- **El primero sumó al menos 1.40 h más** (7-sep, 22:15:17→23:39:19): la prueba
  0 completa y la 1 cortada.
- **Total: ≥ 3.47 h de máquina.** Ver la bitácora, Exp J, párrafo «Costo».
- **Qué funcionó y qué no.** Lo que funcionó fue repartir la evaluación entre 5
  procesos. Correr en paralelo las dos semillas de confirmación NO aceleró
  (§5.2).

Si se rehace la Fase 0 para otro diseño, contar con que la estimación inicial es
optimista en el ritmo por semilla y pesimista en el total.

---

## 3. Intérprete y entorno

**La tesis corre con el Python de la Microsoft Store. NO instalar torch ni
dependencias pesadas ahí sin pensarlo** (ver la memoria `dos-entornos-python`).

```
ejecutable : C:\Users\velas\AppData\Local\Microsoft\WindowsApps\
             PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe
python     : 3.13.14
torch      : 2.10.0+cpu   (CUDA disponible: False)
sb3        : 2.7.1
optuna     : 4.8.0
supersuit  : 3.9.3
numpy      : 2.4.1
scipy      : 1.17.1
```

Notas operativas:

- El binario se llama **`python3.13.exe`**, no `python.exe`. Buscar procesos con
  `tasklist /FI "IMAGENAME eq python.exe"` devuelve vacío aunque haya
  entrenamientos corriendo. Usar:
  `Get-Process | Where-Object { $_.ProcessName -like "*python*" }`.
- **`CLAUDE.md` ya está al día (corregido el 2026-09-24).** Aquí decía que
  declaraba SuperSuit 3.10.0 y `num_cpus=1` forzado en
  `construir_vec_env_entrenamiento`. Hoy `CLAUDE.md` §10 dice **SuperSuit 3.9.3**
  y, en el bug B, `min(n_envs_efectivos, os.cpu_count() or 1)` con «**NO es
  `num_cpus=1`**». Así estaba ya en `CLAUDE_respaldo_20260909_preL.md`. El
  VecEnv resultante es un `ProcConcatVec` (multiproceso), no un `DummyVecEnv`.
- Máquina: 12 núcleos, RTX 4050 Laptop 6 GB (no usada; ver Exp L en memoria).
- **Finales de línea:** los archivos del proyecto están en **LF**. Escribir con
  `Path.write_text()` en Windows los convierte a CRLF y hace que el archivo
  entero aparezca como modificado. Usar `write_bytes()` con el texto codificado.

---

## 4. Los dos bugs de unidades (corregidos, con respaldo)

Descubiertos durante la Fase 0. Están documentados en la bitácora, pero aquí va
el detalle operativo.

**Naturaleza:** SB3 compara `self.n_calls % eval_freq` — LLAMADAS al callback,
no pasos de entorno. Cada llamada avanza `num_envs` pasos. Lo mismo vale para
`MedianPruner.n_warmup_steps`, que se compara contra el `step` reportado a
Optuna, que es `num_timesteps`.

**Estado actual de `train.py`: CORREGIDO** el 2026-09-08. Los cuatro cambios:

| Línea aprox. | Antes | Ahora |
|---|---|---|
| 192–196 | `n_warmup_steps = 5` | `n_warmup_steps = 100_000` (pasos de entorno) |
| 736–746 | `eval_freq = n_steps_reporte` | `eval_freq = max(1, n_steps_reporte // env_train.num_envs)` |
| 920–921 | `eval_freq = config_train.frecuencia_eval` | `… // env_train_norm.num_envs` |
| 928–934 | `save_freq = config_train.frecuencia_ckpt` | `max(1, config_train.frecuencia_ckpt // env_train_norm.num_envs)` |

**Respaldo — corregido el 2026-09-24.** Antes decía «respaldo íntegro del
archivo previo» y listaba sólo los tres primeros cambios. En realidad
`fase_preliminar2/train_respaldo_20260908.py` se tomó a las 20:59:11, justo
antes del cuarto cambio (`train.py` es de las 20:59:31), y **ya trae los tres
primeros**: su diff contra `train.py` es sólo el `save_freq`. **La versión con
`n_warmup_steps = 5`, la del estudio original, no se conserva como archivo**, así
que la columna "Antes" de las tres primeras filas no puede verificarse contra
ningún archivo; el comportamiento previo queda documentado en la bitácora.
La bitácora decía que `train.py` "NO se modificó". Era cierto mientras corrió
el Exp J, y ya quedó anotada con este estado posterior.

**`train.py` corregido NO se ha ejecutado nunca.** Compila e importa, pero
ninguna corrida real lo usó después del arreglo. La primera que lo use conviene
supervisarla: `n_warmup_steps = 100_000` cambia el comportamiento de poda de
cualquier estudio futuro y `eval_freq` cambia cuántas veces se evalúa.

**Lo que NO está afectado:** el diagnóstico 100k–500k del documento. Su script
`diagnostico_sin_vecnormalize.py` ya tenía la corrección ("Bug C") y los cinco
`.zip` declaran `num_timesteps` exactos de 100k a 500k. Verificado.

---

## 5. Decisiones y hallazgos que NO están en la bitácora

### 5.1 Por qué no se usa GPU (y por qué la cifra citada cambió)

Se midió el reparto del tiempo con `perfilar_cuello_botella.py` y dio 83 %
entorno / 17 % red, techo de Amdahl 1.20×. **Ese número fue corregido después
por el Exp L a 27/73**, que además encontró la RTX 4050 más lenta que la CPU
(0.7–0.8× en entrenamiento). La conclusión operativa se sostuvo por otra vía: la
GPU no es la palanca para esta carga. `perfilar_cuello_botella.py` queda en el
directorio, pero **su reparto 83/17 está superado por el Exp L**.

### 5.2 Paralelización: qué funcionó y qué no

- **Repartir los episodios de evaluación entre 5 procesos: 3.08×**, de 42.0 s a
  13.6 s para 30 episodios. Probado con 5, 8 y 10 trabajadores; **5 es el
  óptimo**, más empeora por contención.
- **`torch.set_num_threads(1)` en cada trabajador es imprescindible.** Sin eso
  la aceleración cae de 3.08× a 1.41×: cinco procesos abrían 40 hilos sobre 12
  núcleos.
- **Equivalencia verificada** (`verificar_paralelo.py`): paralelo y secuencial
  dan `0.64919573764006` — idénticos a 14 decimales y episodio por episodio.
- **Lo que NO rinde:** el paralelismo interno del VecEnv. Un entorno solo da 690
  transiciones/s y el entrenamiento con 4 procesos da 575. La comunicación entre
  procesos por paso se come la ganancia, porque el paso de entorno es muy barato.
  **Paralelizar arriba (procesos independientes), no adentro.**
- Sólo se paralelizan las dos semillas de CONFIRMACIÓN. La semilla 42 va en
  serie porque la criba la necesita antes de decidir si gastar las otras.
- **Ese par en paralelo NO aceleró** (corregido el 2026-09-24; la bitácora y §2
  lo contaban como fuente de aceleración).
  - En las 8 pruebas completas del segundo lanzamiento el par tardó 3992 s de
    pared, contra 3662 s que habrían costado las dos semillas en serie al ritmo
    de la semilla 42. La razón fue 1.09 (1.03–1.20 según la prueba).
  - Cada trabajador entrenó 1.65–2.26× más lento que la semilla 42 sola. Es
    consistente con CPU saturada, pero la carga no se registró.
  - La evaluación fue 2.11–2.41× más lenta, esperable por el pool de 2 (§1).
  - «Paralelizar arriba» rinde sólo si quedan núcleos libres.

### 5.3 Reanudación: los directorios se nombran por HASH de configuración

`resultados/estudio/cfg_<sha1[:10]>/semilla_<n>/`. **No por número de prueba**,
porque al reanudar Optuna asigna números nuevos y `prueba_007` dejaría de
apuntar a la misma configuración. Si existe `resultado_semilla.json`, se
reutiliza sin reentrenar.

**Efecto secundario no previsto:** al reanudar, el TPE sembrado **reinicia su
secuencia aleatoria** y vuelve a proponer configuraciones ya vistas. **Hay dos
duplicados** (corregido el 2026-09-24; antes decía «las pruebas 0 y 2 son
idénticas — 19 configuraciones distintas, no 20»):

- **0≡2.** Las dos están COMPLETE. La 2 reutilizó por hash el resultado de la 0
  en 0.1 s, sin reentrenar.
- **1≡3.** La 1 es la RUNNING huérfana y la 3 la reentrenó completa (`cfg_c4841946c7`).

En total hay **20 configuraciones distintas en 22 registros**: 20 entre las 21
terminadas y 9 entre las 10 COMPLETE. El valor repetido 0≡2 además sesga
levemente hacia abajo la mediana de la criba de etapa 2.
Si se relanza un estudio, **empezar limpio** en vez de `--reanudar`, salvo que
se acepte ese efecto.

### 5.4 Estado de la base de Optuna

`optuna_studies/experimento_J.db` → **22 registros** (pruebas 0–21): 10 COMPLETE,
11 PRUNED (9 en etapa 1, 2 en etapa 2), **1 RUNNING huérfano** (la prueba 1,
cortada cuando se interrumpió el primer lanzamiento). Las 0–1 son del primer
lanzamiento (7-sep, 22:15); las 2–21, del segundo, reanudado con
`--n_trials 20` (8-sep, 01:22). El "20 pruebas" del diseño es el argumento,
no el número de registros.
No rompe nada — Optuna ignora las no completas para el muestreo y para la
mediana — pero **aparece como fila fantasma en el CSV**. Filtrar por estado al
analizar.

### 5.5 Gancho de presupuesto para pruebas

`estudio_J.py` lee dos variables de entorno para poder ejercitar el flujo
completo en un minuto sin gastar una corrida real:

```bash
EXPJ_PRESUPUESTO=4000 EXPJ_FREQ_EVAL=2000 python estudio_J.py --worker_semilla 999 ...
```

**Trampa al usarlo:** con `n_steps_exp=8` el buffer de rollout es 256×20 = 5120
pasos. Con un presupuesto de prueba de 4000, PPO **nunca completa un rollout** y
la política no se actualiza: las evaluaciones dan valores idénticos y parece un
bug de caché. No lo es. Elegir el presupuesto de prueba mayor que
`2^n_steps_exp × num_envs`.

### 5.6 El desplazamiento entre conjuntos de episodios está medido

Los dos conjuntos no son igual de difíciles, y la diferencia es **~0.010**,
común a todos los modelos. Medido sobre `modelo_PRIMERO`
(`recomputar_referencia.py`):

```
100 episodios, offset 0        → 0.68129082   (reproduce el 0.6813 oficial)
 20 episodios, offset 0        → 0.68359383   (conjunto de retención)
 30 episodios, offset 1000     → 0.67359557   (conjunto de evaluación final)
```

Por eso `sesgo_retencion` toma valores NEGATIVOS: mezcla el sesgo de selección
(siempre positivo) con este desplazamiento (signo propio). **No es una
estimación del sesgo de selección.**

**⚠ Revisión 2026-09-24.** Dos afirmaciones de esta sección quedan sin sostén.

- **Que el ~0.010 sea «común a todos los modelos» no está verificado.** En los
  seis pares sin selección del Exp J (prueba 7, semillas 42/123/777 a 100k y
  200k, misma política en el estudio y en el diagnóstico), retención − final
  va de −0.01230 a +0.01452, con media +0.0016. Un desplazamiento común de
  +0.010 no se confirma ni se rechaza.
- **Tampoco explicaría los negativos.** `sesgo_retencion` es retención − final,
  y un desplazamiento positivo lo empujaría hacia arriba.

La conclusión en negrita se mantiene: **no es una estimación del sesgo de
selección.** Ver la bitácora, Exp J, «Validación de control».

### 5.7 Errores de proceso cometidos, para no repetirlos

Dos errores de esta sesión tuvieron la misma raíz — **poner un número al lado de
otro sin verificar que midieran la misma cantidad**:

- Se comparó el CV de cobertura del Exp J (0.0126) contra el **0.589 de H-05**,
  que es el CV de la **RECOMPENSA**. Los CV de cobertura del Trial 13 son
  0.1051 y 0.1428. Ya corregido en la bitácora.
- El scatter dibujaba 12 puntos con **dos escalas distintas en el mismo eje**
  (10 completas con media de 3 semillas, 2 podadas con una sola) mientras el ρ
  del título salía de 10. Ya corregido: la figura lleva el n en cada subtítulo.

Regla para lo que queda del capítulo: **toda cifra puesta junto a otra en una
tabla debe venir con su definición explícita**, como la tabla de los cinco
análisis de correlación en la bitácora. (**⚠ 2026-09-24:** esa tabla tenía
mal dos n. A, B y C contaban dos veces la configuración 0≡2 y D/E son 27
semillas, no 29. El recálculo con Holm está en la bitácora, Exp J, Resultado 3,
y en `recalcular_ABC_sin_duplicado_holm.py`.)

---

## 6. Scripts — qué hace cada uno

Todos se corren desde `fase_preliminar2/experimento_J/`. Ninguno modifica
`swarm_env_skeleton.py` ni `concentration_dynamics.py`: los importan en sólo
lectura.

| Script | Qué hace | Costo |
|---|---|---|
| `fase0_costo.py` | Una prueba completa cronometrada por partidas | ~8 min |
| `estudio_J.py` | El estudio. `--n_trials`, `--reanudar`, modo trabajador | ~2 h por lanzamiento de 20 pruebas; el estudio completo sumó ≥ 3.47 h en dos lanzamientos (corregido el 2026-09-24; decía «~2 h», ver §2) |
| `analizar_estudio_J.py` | CSV, 5 análisis de correlación, figuras, comparativa | segundos |
| `diagnostico_presupuesto_J.py` | 500k × 3 semillas, puntos de control cada 100k | ~21 min |
| `recomputar_referencia.py` | `modelo_PRIMERO` bajo el protocolo único. **Sobrescribe** `resultados/analisis/referencia_recomputada.json` y, sin `-B`, regenera el `.pyc` de evidencia de `estudio_J`: no volver a correrlo tal cual | ~1 min (corregido el 2026-09-24; decía «~3 min») |
| `cv_vieja_usanza.py` | CV con episodios propios por semilla | ~2 min |
| `verificar_paralelo.py` | Equivalencia paralelo vs. secuencial | ~2 min |
| `perfilar_cuello_botella.py` | Reparto entorno/red (**superado por Exp L**) | ~2 min |

---

## 7. Qué queda abierto

- **Ninguna tarea del Exp J.** El experimento está cerrado y reportado.
- `train.py` corregido **sin estrenar** (§4). Supervisar su primera corrida.
- ~~`CLAUDE.md` tiene dos datos desactualizados~~ **Resuelto** (corregido el
  2026-09-24): `CLAUDE.md` ya dice SuperSuit 3.9.3 y «NO es `num_cpus=1`» (§3).
- El umbral de colisiones **no se fijó a priori** y quedó calibrado a
  posteriori sobre la distribución observada, con la aclaración de que la
  medición es sobre la política DESNUDA y de que la viabilidad del sistema
  desplegado la aporta la capa CBF + escape. Si se retoma, la comparación debe
  hacerse **a paso fijo**, nunca en el punto retenido.
- El modelo del Exp J **no se adopta**. La declaración de qué revalidación
  exigiría adoptarlo está en la bitácora, sección "Qué revalidación exigiría
  adoptar el modelo nuevo".
