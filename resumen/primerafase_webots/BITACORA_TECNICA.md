# Bitácora técnica — Fase Webots

Registro de los experimentos ejecutados sobre el demo de Webots, desde la
detección del gap sim-to-real de paredes hasta la configuración final
adoptada. Cada entrada apunta a sus artefactos para que los números sean
trazables y citables.

**Configuración final adoptada: `modelo_sanidad` (v2) + filtro CBF de ejecución.**
Tabla consolidada: [`resultados_consolidados/tabla_final_webots.txt`](resultados_consolidados/tabla_final_webots.txt)

---

## Contexto: el modelo de partida

`modelo_PRIMERO.zip` (RESULTADO_PRIMERO, 200k pasos, Trial 13, 5 agentes).
Cobertura oficial de referencia: **0.6813 ± 0.0200** sobre 100 episodios
deterministas con semillas `42·10000 + i`. Todas las réplicas de protocolo
posteriores validan contra ese número antes de reportar nada.

---

## Exp A — Atascos con física real (Webots, 1 robot)

**Pregunta:** ¿qué le pasa a la política entrenada cuando la pared deja de
reflejar y pasa a bloquear?

**Resultado:** **18/18 episodios con atasco** (100%), tiempo medio al atasco
11.8 s, distancia mínima centro→pared 0.0745 m = radio del chasis (contacto).
La política **nunca comandó `v<0`** (0/18): no tiene comportamiento de
recuperación aprendido.

**Artefactos:** `controllers/supervisor_fisica/resultados/experimento_A_atascos_original.csv`

---

## Exp B — Dependencia de la reflexión elástica (Python, 100 eps)

**Pregunta:** ¿cuánto depende la política del rebote idealizado?

**Resultado:** **45.74 ± 5.54 reflexiones por episodio** (9.15 por agente),
**100% de episodios con ≥1**. Cross-check de fidelidad del protocolo:
cobertura replicada 0.6813, idéntica a la oficial.

**Artefactos:** `experimentos/expB_reflexiones/resultados/`

---

## Exp C — Degradación bajo bordes bloqueantes (Python, pareado, 100 eps)

**Diseño:** mismas 100 semillas en dos condiciones (`reflexion` vs
`bloqueante`), pareado por semilla para cancelar la varianza entre semillas.

**Resultado:**

| Condición | Cobertura |
|---|---|
| reflexión | 0.6813 ± 0.0201 |
| bloqueante | 0.4516 ± 0.0422 |

Diferencia pareada **−0.2297**, IC95 **[−0.2385, −0.2208]**, degradación
relativa **−33.7%**, **100/100 episodios peor** (efecto universal, no
promedio). Los agentes quedan recortados el 51.2% de los agente-paso.

**Artefactos:** `experimentos/expC_bordes/resultados/`

---

## Exp D — ¿Es específico de la política aprendida? (Python, 3×2×100)

**Diseño:** 3 estrategias (MADRL, heurística NN, aleatoria) × 2 condiciones de
borde × 100 semillas, todo pareado. Estadístico decisivo: diferencia de
diferencias.

**Validación de control:** MADRL 0.681291 y heurística 0.254349 reproducen el
protocolo original **exacto a 6 decimales**.

**Resultado:** la degradación es **específica de MADRL**.

| Estrategia | Δ pareada (bloq − refl) | IC95 |
|---|---|---|
| MADRL | −0.2297 | [−0.2385, −0.2208] |
| heurística NN | +0.0003 | [−0.0007, +0.0013] |
| aleatoria | −0.0001 | [−0.0003, +0.0000] |

**DiD MADRL vs heurística = −0.2300, IC95 [−0.2389, −0.2211]** (excluye cero).
Mecanismo: tiempo agente-paso contra el borde 0.5117 (MADRL) vs 0.0065 (NN) vs
0.0002 (aleatoria).

**Artefactos:** `experimentos/expD_lineas_base/resultados/`

---

## Exp E — Voronoi + PSO como cuarta línea base (Python, 4×2×100)

**Diseño:** se incorpora al protocolo de evaluación el controlador
Voronoi + PSO (`PyramidalHeuristicController`: Voronoi acotado a la arena con
recorte Sutherland-Hodgman, centroide de celda, término PSO con inercia,
atracción a hotspots, sesgo al centroide y empuje hacia adentro cerca del
borde). El controlador ya existía en `fase_preliminar2/baseline_heuristico/`;
**lo nuevo es su evaluación** — su único script de uso corría un episodio con
render, un visualizador y no un evaluador, razón por la cual esta línea base
no aparece en los diagramas de caja de RESULTADO_PRIMERO.

El artefacto original **no se modificó**: la copia en `lib_baseline/` se
verificó **idéntica byte a byte por sha256**, y toda la integración vive en
`adaptador_piramidal.py`.

4 estrategias × 2 condiciones de borde × 100 semillas = **800 episodios**,
pareado por semilla. Validación de control: **MADRL 0.681291** y
**heurística NN 0.254349**, ambos con **|Δ| = 0.000000**.

### Resultados

Cobertura bajo `reflexion`: **MADRL 0.6813** · piramidal 0.2644 ·
NN 0.2543 · aleatoria 0.1394. MADRL supera al piramidal **2.6×**.

**Piramidal vs NN (pareado):** Δ = **+0.0100**, IC95 **[+0.0025, +0.0176]**,
t = 2.60, mejor en **61/100**. Significativo pero marginal: la partición
geométrica compra ~1 punto de cobertura sobre la asignación codiciosa. Donde
sí domina es en **seguridad**: 0.41 vs 4.18 colisiones por episodio.

**DiD MADRL vs piramidal = −0.2297**, IC95 **[−0.2386, −0.2209]**, excluye el
cero. La especificidad de la degradación queda confirmada ahora contra **tres
líneas base independientes**, una de ellas un algoritmo de cobertura con
información global.

### Tres regímenes de comportamiento de borde

La columna decisiva no es cuántos episodios empeoran sino **cuántos cambian**
al alterar la condición de borde:

| Estrategia | Δ pareada | Episodios alterados | Régimen |
|---|---|---|---|
| MADRL | −0.2297 | **100/100** | depende del rebote |
| Heurística NN | +0.0003 | **100/100** | toca pero no depende |
| Voronoi + PSO | +0.00003 | **4/100** | **nunca toca (evita)** |

NN y piramidal son igual de indiferentes **en cobertura**, pero por razones
**opuestas**: la NN encuentra la condición de borde en todos los episodios y
no le afecta; el piramidal **casi nunca la encuentra** (0.04 reflexiones por
episodio, fracción agente-paso en borde 0.0001). Es **evitación por diseño**
—celdas recortadas contra la arena más `boundary_gain` empujando hacia
adentro— y no indiferencia. La media de la diferencia oculta la distinción;
el conteo de episodios alterados la revela.

### Exclusión geométrica ≠ margen de seguridad

Razón entre el umbral de margen (0.22 m) y el de contacto (0.15 m):

| Estrategia | col. 0.15 m | col. 0.22 m | Razón |
|---|---|---|---|
| MADRL | 0.210 | 0.320 | 1.52 |
| **Voronoi + PSO** | **0.410** | **2.940 (97% eps)** | **7.17** |
| Heurística NN | 4.180 | 4.670 | 1.12 |

El piramidal tiene **7× más rozamientos que contactos**: sus agentes
**habitan la banda [0.15, 0.22] m**. El mecanismo es estructural — la
frontera de Voronoi es por definición el lugar de equidistancia, así que dos
agentes cada uno dentro de su propia celda y cerca de su frontera compartida
están legítimamente separados y aun así a ~16 cm uno del otro. **La partición
garantiza propiedad de celda, no distancia.** Relevante para el despliegue
físico: un algoritmo que nunca "colisiona" en el sentido geométrico puede aun
así violar el margen operativo de forma sistemática.

### Tiempo de decisión

Una decisión produce las acciones de los 5 agentes de una vez, en las cuatro
estrategias. Medido con `perf_counter`, promediado sobre las dos condiciones:

| Estrategia | ms/decisión | × vs MADRL |
|---|---|---|
| MADRL | 0.757 | 1.00× |
| **Voronoi + PSO** | **8.039** | **10.62×** |
| Heurística NN | 0.178 | 0.23× |
| Aleatoria | 0.025 | 0.03× |

**Salvedad:** con n = 5 agentes esto **no verifica** la afirmación asintótica
O(n log n) vs O(1) del cuadro de antecedentes — haría falta barrer el tamaño
del enjambre. Lo que sí aporta es una **medición propia** que sustituye a una
cita sin respaldo, en la configuración concreta de la tesis.
(La Tabla 5 del resumen reporta 0.734 ms y 10.96× porque promedia sólo la
condición `reflexion`; acá se usa la media global de ambas.)

### Limitaciones declaradas de la comparación

- **(a) Asimetría de INFORMACIÓN — favorece a la línea base.** La partición de
  Voronoi requiere las posiciones **globales** de todos los agentes; MADRL
  opera sólo con observación local dentro de `comm_radius = 1.0 m`. La
  comparación es por tanto **conservadora** respecto de MADRL.
- **(b) Asimetría de SINTONIZACIÓN — favorece a MADRL.** El piramidal tiene
  ~13 parámetros fijados a mano, sin sintonización automática; la política
  MADRL pasó por 20 pruebas de optimización bayesiana (Optuna/TPE).
- **(c) Asimetría de ESPACIO DE ACCIÓN — favorece a MADRL.** MADRL puede
  comandar `v < 0`; el piramidal está acotado a `v ∈ [0, v_max]` por
  construcción de su ley de seguimiento. Ante un obstáculo frontal su única
  salida es girar, no retroceder.
- **(d) LEY DE BAJO NIVEL distinta entre las dos heurísticas.** Ambas usan
  control proporcional sobre el error de rumbo con `v` modulada por
  `cos(error)`, pero con ganancias distintas: NN usa `K_ω = 4.00` y
  `v = V_MAX·max(0,cos e)`; el piramidal usa `k_ω = 2.20` y
  `v = k_v·‖vec‖·max(0,cos e)` con `k_v = 1.40` (escala por distancia). Se
  corrió el piramidal **con sus ganancias originales**: son parte de su diseño
  (frenar al aproximarse al punto deseado dentro de su celda es intencional) y
  homogeneizarlas evaluaría un controlador que nadie diseñó, además de anular
  el valor de replicar el trabajo previo de la UVG. En consecuencia, entre las
  dos heurísticas difiere tanto la **decisión de destino** como la ley de
  seguimiento. (`Ω_MAX` sí se unificó al valor canónico 6.2832 del proyecto,
  vía constructor, sin tocar el archivo original.)

**Artefactos:** `experimentos/expD_lineas_base/adaptador_piramidal.py`,
`correr_experimento_E.py`, `lib_baseline/`,
`resultados/experimento_E_completo.csv` (800 filas),
`resultados/resumen_experimento_E.txt`,
`resultados/fig_resultados_CUATRO.png` (no pisa la figura de
RESULTADO_PRIMERO).

---

## Exp F — Robustez a ruido y latencia de pose (Webots, 4×3×18)

**Objetivo:** determinar el umbral de tolerancia del sistema antes de entrar al
laboratorio, para decidir si hace falta filtrado de pose y/o reducir la
latencia del lazo.

**Configuración:** `modelo_sanidad` + CBF (la adoptada), 5 agentes con física.
Barrido factorial completo **4 niveles de ruido × 3 de latencia × 18 semillas
= 216 episodios**, en una sola sesión de Webots. Regresión cero verificada
antes de lanzar: con σ = 0 y retardo = 0, las 58 columnas previas quedan
**idénticas** al lote de referencia.

### Validez: separación de poses

Las poses **degradadas** (ruido + retardo) van únicamente al env y al filtro
CBF — lo que el sistema cree ver. **Todas las métricas físicas** (colisiones,
`d_min` a pared, detector de atasco, violaciones de margen) usan las poses
**reales** del GPS/Compass. Sin esta separación el experimento mediría el
error de medición en vez de la seguridad.

**Ruido angular acoplado:** `σ_θ = σ_pos·√2/L` con L = 0.15 m (constelación de
marcadores), porque OptiTrack estima el heading de la constelación y no lo mide
directamente. Es ~3× más agresivo que el `DomainRandomizer` del entrenamiento
(10 mm ↔ 5.4° acá vs 1.7° allá). **Los umbrales de esta sección deben
enunciarse como "σ_pos con constelación L = 0.15 m"**, no como σ_pos a secas:
con otra geometría de marcadores el mismo error posicional produce otro error
angular.

### Resultado: la degradación MEJORA el desempeño

| σ_pos | σ_θ | ret | Cobertura | Atascos | col015 | CBF frac | Viol. margen |
|---|---|---|---|---|---|---|---|
| **0 mm** | 0° | **0** | **0.3199** | **39/90** | 0.000 | 0.371 | **9/90** |
| 0 | 0° | 3 | 0.5787 | 7/90 | 0.000 | 0.212 | 76/90 |
| 5 | 2.7° | 0 | 0.5174 | **0/90** | 0.000 | 0.415 | 46/90 |
| 10 | 5.4° | 0 | 0.6014 | 0/90 | 0.000 | 0.412 | 60/90 |
| **20** | 10.8° | **3** | **0.6779** | **0/90** | 0.000 | 0.193 | **81/90** |

**Todas** las celdas con σ > 0 dan **cero atascos** (vs 39/90 de la base). La
cobertura pareada sube entre +0.20 y +0.36, con IC95 que excluye el cero en
11 de 12 celdas.

### ⚠ El resultado está CONFUNDIDO con el equilibrio de liveness del CBF

**Este experimento no midió robustez al ruido. Midió qué pasa cuando se
perturba un equilibrio patológico.**

La configuración base tiene 39/90 atascos, de los cuales **33 ocurren en el
margen del CBF** (d ≈ 0.18 m con v ≈ 0.0016 m/s) — el equilibrio de liveness
documentado en la sección del filtro. Ese equilibrio es determinista y frágil:
el ruido perturba el punto fijo y el retardo hace que el filtro vea una pose
vieja y no clampee tan fuerte. En ambos casos el robot escapa.

Es decir: **el desempeño mejora porque la capa de seguridad deja de
funcionar**, no porque el sistema sea robusto. La fracción intervenida por el
CBF baja de 0.371 a 0.193, coherente con un filtro que interviene menos porque
ya no pelea contra una política clavada.

Corolario: si el deadlock se resolviera por diseño, el beneficio del ruido
desaparecería y sólo quedaría su costo. **El resultado no puede leerse como
tolerancia al ruido.**

### El costo: el margen se consume

| Configuración | Viol. margen (<0.18 m) | Contacto (<0.075 m) | d_min |
|---|---|---|---|
| base (0, 0) | **9/90** | 0/90 | 0.1800 m |
| (0 mm, 3 dec) | 76/90 | **1/90** | 0.0742 m |
| (20 mm, 3 dec) | **81/90** | **1/90** | 0.0745 m |

Δ pareado de violaciones: **+1.4 a +4.0**, con IC95 que excluye el cero en las
**12/12** celdas. El margen de diseño se consume de forma sistemática.

**El contacto físico con la pared, en cambio, es raro:** 2 agente-episodios
sobre 1080 (`d_min` < 0.075 m = radio del chasis), y el Δ pareado **no** es
significativo (IC95 incluye el cero). El margen absorbe la degradación —que es
exactamente su función— pero queda consumido casi por completo.

`col015` se mantiene en **0.000 en las 12 celdas**: nunca hay contacto entre
robots. `col022` aparece con valores leves (0.056–0.111).

### Nota sobre la definición de "violación de margen"

`violaciones_margen` cuenta agente-episodios en que el **centro** del robot
(pose **real**) estuvo a menos de `MARGEN_CBF_M = 0.18` m de una pared.
Recalcular el mismo criterio desde la columna `dist_min_pared_a*` da 0/90 en
la base, en aparente contradicción con el 9/90 reportado: **es un artefacto de
redondeo**. Esa columna se vuelca con `round(..., 4)`, así que un valor como
0.179996 se muestra como `0.1800` aunque sí disparó el flag (26
agente-episodios muestran exactamente `0.1800` en la base). Ambas columnas usan
la misma referencia —centro del robot, pose real— y todos los deltas de la
comparación pareada se calculan sobre el contador sin redondear.

### Interacción ruido × latencia: fuerte y subaditiva

| Métrica | Solo ruido | Solo latencia | Suma | Conjunto | **Interacción** |
|---|---|---|---|---|---|
| Cobertura | +0.3269 | +0.2589 | +0.5858 | +0.3580 | **−0.2277** |
| Atascados | −2.167 | −1.778 | −3.944 | −2.167 | +1.778 |

El efecto conjunto es apenas el **61%** de la suma de los individuales: ambos
mecanismos rompen el **mismo** deadlock, así que una vez roto, el segundo no
aporta. (La de atascados está saturada: no se puede bajar de cero.)

**Consecuencia operativa:** ruido y latencia **no** se pueden presupuestar por
separado. El margen tolerable en uno depende del otro.

### Conclusión: el margen del CBF está sub-dimensionado

La lectura "no hace falta filtrado de pose" estaría respaldada por la cobertura
pero sería **peligrosa**: el desempeño mejora a costa de que la capa de
seguridad deje de operar (violaciones 9/90 → 81/90).

Lo que el experimento sí establece es que **`D_SEGURA_PUNTO = 0.18 m` se
dimensionó suponiendo pose perfecta**. El presupuesto del margen debe incluir,
además de la holgura geométrica (radio de chasis 0.075 + punto de mira 0.05):

- **σ_pos** del sistema de captura (y su error angular acoplado), y
- **V_MAX · latencia_total**, que con 3 decisiones de retardo son 0.093 m
  adicionales — la mitad del margen actual.

Las dos preguntas de mitigación quedan así:
- **¿Filtrado de pose?** No es la mitigación correcta. Filtrar reduciría el
  ruido que hoy desbloquea al enjambre y podría reintroducir los 39/90
  atascos, sin atacar la causa.
- **¿Reducir la latencia?** Tampoco es un objetivo en sí. El retardo de 3
  decisiones es la celda con mejor cobertura.
- **Lo que sí hace falta:** ampliar el margen del CBF para absorber ruido y
  latencia reales, y resolver el deadlock de liveness por diseño en vez de
  depender de que una perturbación lo rompa.

**Artefactos:** `controllers/coordinador_enjambre/resultados/expF_barrido_5agentes.csv`
(216 filas), `expF_resumen_5agentes.txt`. Constantes: `SIGMA_POS_M`,
`RETARDO_EXTRA_DECISIONES`, `L_MARCADORES`, `MODO_BARRIDO` (defaults en cero =
no-op exacto).

---

## Exp G — ¿Se resuelve el bloqueo sintonizando el filtro? (Webots, 3×3×18)

**Objetivo:** encontrar una configuración del CBF que no produzca bloqueo, para
tener un sistema **sano** sobre el cual medir robustez de verdad (el Exp F
midió la perturbación de un equilibrio patológico, no tolerancia al ruido).

**Palancas elegidas.** No `d_s`: los atascos ocurren **en** el margen (33/39 a
d ≈ 0.18) y en esquinas, así que ampliarlo sólo mudaría el equilibrio. Se
barren `ℓa` (autoridad de giro: el coeficiente de ω en la restricción es
`ℓa·n·perp(heading)`) y `w_ω` (preferencia por girar sobre frenar). **α queda
fijo**: en el equilibrio `h ≈ 0` la condición es `c·u ≥ 0` sin α, así que no
mueve el punto fijo.

**Constantes acopladas** para que las celdas sean comparables en seguridad:
`d_s = 0.13 + ℓa` (holgura de peor caso constante: centro a 0.13 m, 0.055 m de
chasis libre) y **`D_robots = 0.15 + 2ℓa`** — sin este segundo acople la
garantía entre centros se anularía con ℓa = 0.15 (`0.25 − 0.30 < 0`) y las
celdas de ℓa alto se verían artificialmente buenas por competir contra una
restricción más floja.

### Resultado: ninguna celda cumple; la base es la mejor

| ℓa | w_ω | Atascos | Cobertura | Anillo | CBF frac | Fallb/ep |
|---|---|---|---|---|---|---|
| 0.05 | 0.03 | 46/90 | 0.2588 | 0.1985 | 0.443 | **40.28** |
| 0.05 | 0.10 | 43/90 | 0.2714 | 0.2216 | 0.428 | 8.78 |
| **0.05** | **0.30** | **39/90** | **0.3199** | **0.2503** | **0.371** | **2.22** ← base |
| 0.10 | 0.30 | 57/90 | 0.2102 | 0.1377 | 0.585 | 43.06 |
| 0.15 | 0.30 | **78/90** | 0.1660 | 0.0671 | 0.802 | 113.39 |

Criterio de éxito (≤ 10/90 sin subir colisiones ni contacto): **ninguna celda
lo alcanza**. Contacto con pared 0/90 y `col015` = 0.000 en las nueve.

### El eje ℓa: resultado sólido y estructural

Subir ℓa empeora de forma monótona y significativa: 39 → 57 → 78 atascos, con
IC95 que excluye el cero en las seis celdas de ℓa > 0.05.

**La predicción de que ℓa ayudaría (más autoridad de giro) resultó
equivocada.** El beneficio local —`c_ω ∝ ℓa`— queda sepultado por dos costos
globales:

1. **El límite de aproximación crece** a `d_s + ℓa = 0.13 + 2ℓa` → 0.23 / 0.33
   / **0.43 m**. La zona de exclusión se agranda y más agentes topan con la
   restricción. La cobertura de anillo lo confirma: cae 0.2503 → 0.1377 →
   0.0671, **más rápido que la global**, o sea que la pérdida es **geométrica**
   (el agente no puede entrar al perímetro encarándolo) y no de comportamiento.
2. **`D_robots` crece** a 0.45 m, restrictivo en una arena de 3×3 con 5 robots.
   Evidencia directa: las intervenciones robot-robot pasan de **5.1% → 16.7% →
   34.0%**.

**Punto estructural:** con el formalismo del punto de mira **no se puede
aumentar ℓa sin agrandar la zona de exclusión (`0.13 + 2ℓa`) o sacrificar
holgura de seguridad**. Es una propiedad del formalismo, no del diseño
experimental: el mismo ℓa que da autoridad de giro es el que separa el punto de
mira del centro en ambos sentidos.

### El eje w_ω: sin efecto detectable, y contaminado por el solver

**w_ω no "va al revés": su efecto no es significativo.** Los dos Δ pareados a
ℓa = 0.05 tienen IC95 que **incluyen el cero**: `+0.389 [−0.004, +0.781]` para
w_ω = 0.03 y `+0.222 [−0.116, +0.560]` para w_ω = 0.10. La lectura correcta es
**"sin efecto detectable"**, no empeoramiento.

**Limitación declarada: el eje quedó contaminado por el solver.** Los fallbacks
del QP pasan de **2.22 a 40.28 por episodio (18.1×)** al bajar w_ω a 0.03. La
factibilidad no depende del costo, así que no es infactibilidad real: con
w_ω = 0.03 el costo queda casi plano en ω, **SLSQP no converge**, reporta fallo
y cae al fallback `u = (0,0)` — que **congela el robot**, exactamente lo
contrario de lo que se quería probar.

En otras palabras: **no se probó "preferir girar", se probó "degradar el
condicionamiento del QP"**. Probar ese eje limpiamente requeriría un **solver
exacto de conjunto activo** — con 2 variables y ≤8 restricciones el problema es
enumerable y admite solución cerrada, sin depender de convergencia iterativa.

**El margen se erosiona por vía del fallback.** Con w_ω bajo, `d_min` cae por
debajo del margen de diseño (**0.17568485** vs 0.18), mientras que con
w_ω ≥ 0.10 se respeta al octavo decimal (0.17999833, 0.22999866, 0.28000921).
Es el mismo mecanismo de erosión documentado en la sección del filtro, pero
ahora de origen **numérico** en vez de por conflicto política-filtro: el
fallback `u = (0,0)` no garantiza nada cuando el estado ya está en violación.

### Clasificación esquina vs pared plana

Derivada de `h_min2` (los dos h de pared más pequeños en el instante del
atasco, volcados sin redondear), con umbral 0.02 m:

| Celda | Esquina | Pared plana |
|---|---|---|
| base (0.05, 0.30) | 36 (**92%**) | 3 |
| (0.10, 0.30) | 37 (65%) | 20 |
| (0.15, 0.30) | 35 (45%) | 43 |

El número de atascos **de esquina se mantiene** (~35–37) en todas las celdas;
lo que se suma al subir ℓa son atascos **de pared plana**, de 3 a 43. Coherente
con el límite de aproximación: con ℓa alto el agente se traba también en
paredes rectas, no sólo en esquinas.

### Conclusión

El bloqueo **no se resuelve por sintonización del filtro**. El espacio
explorado cubre 3× en ℓa y 10× en w_ω: el eje ℓa empeora de forma sólida y por
razones estructurales, y el eje w_ω no muestra efecto detectable y además quedó
contaminado numéricamente.

La causa es estructural: el equilibrio vive en `h = 0`, donde la condición
`c·u ≥ 0` no depende de α y donde ninguna elección de ℓa o w_ω impide que
exista un óptimo con velocidad casi nula. Hay que atacarlo **por diseño** —
comportamiento de escape explícito—, no por parámetros.

**No se avanzó a la Fase 2** (barrido de ruido sobre configuración sana):
no tiene sentido medir robustez sobre un sistema que sigue bloqueado.

**Artefactos:** `resultados/expG_barrido_filtro_5agentes.csv` (162 filas, 8
decimales sin redondear), `expG_resumen_filtro_5agentes.txt`. Regresión cero
verificada antes de lanzar (62 columnas idénticas).

---

## Comportamiento de escape — la tercera capa del sistema

El Exp G descartó resolver el bloqueo por sintonización. Este es el ataque por
diseño, y su evaluación cambia cómo hay que leer el resultado final: **la
configuración adoptada son TRES capas** —política aprendida + filtro de
seguridad + comportamiento de recuperación—, y la cobertura de 0.578 es del
**sistema**, no de la política sola. El factorial 2×2 mide la contribución de
cada una por separado.

### Diseño

El escape **reemplaza `u_nom`, no al filtro**:

```
política → u_nom ──┐
                   ├→ [selector] → u_deseado → FILTRO CBF → u_ejecutado
escape   → u_esc ──┘
```

El QP sigue corriendo sobre lo que se le pase, así que **la garantía nunca se
suspende** y el escape sólo necesita ser *usualmente factible*, no perfecto.

**Ley de ascenso máximo sobre h.** Con `ṗ = G(θ)u` y `n` la normal interior:

```
ḣ = n·ṗ = a·v + ℓa·b·ω      a = n·heading,  b = n·perp(heading)
v = V_esc·sign(a)           ω = Ω_esc·sign(b)
```

Da `ḣ = V_esc·|a| + ℓa·Ω_esc·|b| > 0` **siempre** (`a² + b² = 1`, no se anulan
a la vez). Resuelve el caso perpendicular (`b = 0` → **retroceso puro**, el
degenerado que ninguna sintonización arreglaba) y el paralelo (`a = 0` → giro
puro). Explota `v < 0`, grado de libertad que la política **nunca comanda**
(0/18 en el Exp A) pese a tenerlo en su espacio de acción.

Como la maniobra se aleja de la barrera, `ḣ > 0` y la restricción se satisface
con holgura: **el filtro la deja pasar casi intacta**. Verificado — el QP
modificó la acción de escape con magnitud media **0.037**, contra 0.82 del
conflicto política-filtro. El escape **convive** con la garantía.

**Dirección con varias barreras:** suma normalizada de **todas** las normales
activas (`h < 0.06`), pared **y** robot-robot. Alejarse sólo del robot que
bloquea podría meter al agente en una pared. Si la norma cae bajo 0.20
(normales opuestas, sin salida) se aborta y se registra `escape_infactible`.

**Detección conjuntiva** (3 términos, 6 decisiones sostenidas): poco
desplazamiento ∧ el CBF intervino ∧ `h_min` pequeño. El segundo término
distingue "bloqueado por el filtro" de "la política decidió frenar", que es
legítimo. **Histéresis** 0.03 / 0.05, mín 4, máx 25, **refractario** 15.

### Resultado en Webots (18 semillas, pareado)

| Métrica | Base | Con escape | Δ pareado (IC95) |
|---|---|---|---|
| **Atascos** | **39/90** | **0/90** | **−2.167 [−2.493, −1.840]** |
| Cobertura | 0.3199 | 0.5739 | +0.2540 [+0.209, +0.300] |
| `col015` / `col022` | 0.000 | 0.000 | — |
| Contacto pared | 0/90 | 0/90 | — |
| Violaciones margen | 0.500 | 2.889 | +2.389 [+1.966, +2.812] |

**Ciclo de trabajo 2.0%** (desagregado por agente: 1.4–2.4 escapes/ep,
repartido parejo, máximo agente-episodio 5.6%, **0/18 episodios sobre 30%**).
Ningún escape agotó el tope de 25 decisiones; 2 infactibles en 90
agente-episodios.

**Costo declarado:** el escape roza el margen al maniobrar (`d_min` 0.17999862
→ 0.14893113), pero sigue muy por encima del radio del chasis (0.075) y el
contacto físico es 0/90.

### Factorial 2×2 en Python: qué aporta cada capa

Mismas 18 semillas, `modo_borde="bloqueante"`, sin física:

| Condición | Cobertura | Dist. media | CBF frac | Escapes/ep | col015 |
|---|---|---|---|---|---|
| (a) sin CBF, sin escape | 0.4426 | 1.7301 | — | 0.00 | 0.278 |
| (b) con CBF, sin escape | **0.2985** | **1.8847** | 0.402 | 0.00 | 0.000 |
| (c) sin CBF, con escape | 0.4477 | 1.7218 | — | 0.11 | 0.278 |
| **(d) con CBF, con escape** | **0.5780** | 1.7094 | 0.429 | **9.94** | 0.000 |

**Efectos pareados por semilla:**

| Efecto | Δ | IC95 | Mejores |
|---|---|---|---|
| CBF (b − a) | **−0.1441** | [−0.1913, −0.0970] | 1/18 |
| Escape sin CBF (c − a) | +0.0051 | [−0.0045, +0.0147] | 2/18 |
| **Escape con CBF (d − b)** | **+0.2795** | **[+0.2555, +0.3034]** | **18/18** |
| **Conjunto (d − a)** | **+0.1353** | **[+0.0930, +0.1777]** | 16/18 |

### Tres lecturas que corrigen hipótesis previas

**1. Hay DOS mecanismos de bloqueo, no uno.** El escape resuelve ambos:

- **Contacto físico** (sólo Webots, sin filtro): la fricción del chasis traba
  la rotación. Sin CBF, `modelo_sanidad` da 51/90 atascos y `modelo_PRIMERO`
  18/18. **Existe deadlock sin filtro.**
- **Equilibrio en el margen del CBF** (ambos entornos): óptimo del QP con
  velocidad casi nula. Evidencia: el escape se dispara **179 veces** en Python
  *con* CBF contra **2** *sin* CBF — el filtro crea el bloqueo también en
  ausencia de física.

**2. La hipótesis de dispersión queda falsificada.** El CBF **sí** dispersa
(distancia media 1.7301 → 1.8847, **+0.1546 m**, IC95 [+0.105, +0.204]), pero
eso **no** mejora la cobertura: la empeora en −0.1441. El mecanismo existe y no
produce el efecto que se le atribuía. Que el CBF ayude en Webots (+0.1031) y
perjudique en Python (−0.1441) se explica por otra vía: en Webots además
previene que los agentes se peguen a la pared (56.7% de atascos sin filtro), y
ese beneficio supera su costo; en Python no hay nada de eso que prevenir.

**3. El escape tiene dos componentes separables.** De sus +0.2795:

```
+0.1441  deshace el costo que introduce el CBF   (d − b) − (d − a)
+0.1354  GANANCIA NETA sobre no tener capa de seguridad   (d − a)
────────
+0.2795
```

Si el escape sólo deshiciera el costo del filtro, (d) igualaría a (a). Está
0.135 por encima, con 16/18 semillas mejores. **Efecto medido:** el escape
mejora la cobertura por encima de la línea sin capa de seguridad.
**Hipótesis del mecanismo (no verificada):** la maniobra rompe patrones
repetitivos de trayectoria, y eso beneficia una métrica de frescura como el
AoI. Se registran como cosas separadas: el efecto está medido; la explicación
no.

Nota sobre la primera verificación (`verificar_escape_python.py`): intentó
aislar la contribución del escape en Python **sin CBF** y **no concluye** — se
disparó 2 veces en total, o sea potencia nula por dosis nula. Las 2 semillas
con delta no nulo son exactamente las 2 donde disparó. El factorial 2×2 sí
tiene dosis (9.94 escapes/ep en la celda d).

### Se cierra el enigma del "exceso de Webots"

El 0.5739 de Webots se estaba comparando contra Python **sin CBF y sin
escape**: dos tratamientos de diferencia. Like-for-like:

| Configuración | Python | Webots | Diferencia |
|---|---|---|---|
| sin CBF, sin escape | 0.4426 | 0.2168 | −0.2258 |
| con CBF, sin escape | 0.2985 | 0.3199 | +0.0214 |
| **con CBF, con escape** | **0.5780** | **0.5739** | **−0.0041** |

**No hay anomalía**: en la comparación correcta Webots queda 0.4% por debajo de
Python, que es lo que uno espera de agregar física. La configuración final
rinde prácticamente igual en simulación idealizada y con física real.

### Conclusión

La cobertura de **0.578 es del sistema de tres capas**, no de la política. Su
descomposición: la política sola rinde 0.4426; el filtro de seguridad **cuesta**
0.1441 de cobertura a cambio de eliminar colisiones (0.278 → 0.000) y contacto
con pared; el escape recupera ese costo y agrega 0.1354 más. Declararlo así es
más honesto y más informativo que un número monolítico.

### Las DOS comparaciones válidas contra las líneas base

El Exp E mostró que las líneas base son **indiferentes a la condición de
borde** (Voronoi+PSO 0.2644 en ambas, Δ pareado +0.00003 con 4/100 episodios
alterados; NN 0.2543/0.2546, IC95 incluye el cero). Eso habilita **dos**
comparaciones legítimas, y presentar ambas es más fuerte que elegir una:

**(1) Bajo reflexión elástica — política sola vs líneas base.**
Aísla la contribución del **aprendizaje**, con todo lo demás igual: ninguna de
las cuatro estrategias tiene capa de seguridad ni de recuperación.

| Estrategia | Cobertura | `col015` |
|---|---|---|
| **MADRL (política sola)** | **0.6813** | 0.210 |
| Voronoi + PSO | 0.2644 | 0.410 |
| Heurística NN | 0.2543 | 4.180 |

**2.58×** sobre la mejor línea base.

**(2) Bajo bordes bloqueantes — sistema completo vs líneas base.**
Responde qué rinde **lo que se va a desplegar**.

| Estrategia | Cobertura | `col015` |
|---|---|---|
| **Sistema (política+CBF+escape)** | **0.5780** | **0.000** |
| MADRL sola | 0.4426 | 0.278 |
| Voronoi + PSO | 0.2606 | 0.222 |
| Heurística NN | 0.2671 | 4.056 |

**2.22×** sobre la mejor línea base, **y con cero colisiones**. El sistema
domina en **ambas** métricas simultáneamente.

*(Nota de pareo: las líneas base se restringen acá a las MISMAS 18 semillas
del sistema, subconjunto de las 100 del Exp E. Con las 100 los valores son
0.2644 y 0.2546, y la razón da 2.19× — la diferencia es de muestreo, no de
efecto.)*

**Sobre "tres capas contra una":** la objeción no aplica. Voronoi+PSO **no es
de una capa** — tiene partición geométrica (la exclusión ES su mecanismo de
seguridad), término PSO, sesgo al centroide y empuje hacia adentro cerca del
borde. Es un sistema completo de ingeniería, sólo que **fijado por diseño en
vez de aprendido y filtrado**. Sistema completo contra sistema completo es la
comparación justa, y es la comparación (2).

**Artefactos:** `ESCAPE_ACTIVO` en `coordinador_enjambre` (default `False`,
regresión cero verificada con 77 columnas),
`resultados/lote_multi_5agentes_cbf_escape.csv`,
`experimentos/tesis_v2_sanidad/verificar_cbf_python.py` y
`resultados/verificacion_cbf_python.{csv,txt}`,
`verificar_escape_python.py` y su resumen (con la interpretación corregida).

---

## Exp H — Robustez a ruido y latencia sobre la configuración sana (4×3×18)

Es la **Fase 2 que quedó pendiente del Exp G**, ahora ejecutable porque el
comportamiento de recuperación eliminó el equilibrio patológico (0/90 atascos
en la base).

**Diferencia con el Exp F:** aquel midió la perturbación de un sistema
**bloqueado** y su resultado quedó confundido — el ruido "mejoraba" porque
inhabilitaba el filtro. Acá la base es **sana**, así que la pregunta "¿cuánta
degradación tolera el sistema?" tiene respuesta interpretable.

Configuración: `modelo_sanidad` + CBF + escape, 5 agentes, 18 semillas. Mismo
factorial que el Exp F para que las tablas sean comparables. Regresión cero
verificada antes de lanzar (110 columnas idénticas con σ=0, retardo=0). Las
poses degradadas van al env, al filtro **y al detector del escape** —los tres
son consumidores de información—; todas las métricas físicas usan poses reales.

### El resultado sólido: el sistema no se rompe en ningún punto

| Métrica, sobre las **216 celdas** (1080 agente-episodios) | Valor |
|---|---|
| Atascos | **0 / 1080** |
| Contacto con pared (`d_min` < 0.075 m) | **0 / 1080** |
| `col015` (colisiones entre robots) | **0** |
| `d_min` mínimo global | **0.08388161 m** |

Contra un radio de chasis de 0.075 m, el peor caso del barrido completo deja
**8.9 mm de holgura**. Cero atascos, cero contacto con pared y cero colisiones
en las doce configuraciones. **Esta es la afirmación defendible para el
despliegue:** en todo el rango evaluado —hasta 20 mm de σ (10.8° de error
angular con constelación L = 0.15 m) y 300 ms de retardo adicional— el sistema
no falla.

### Las 12 configuraciones

| σ_pos | σ_θ | ret | Cobertura | Atascos | Escapes/**episodio** | CBF frac | Viol. margen |
|---|---|---|---|---|---|---|---|
| **0** | 0° | **0** | 0.5739 ± 0.045 | 0/90 | **9.11** | 0.404 | 52/90 |
| 0 | 0° | 1 | 0.5770 ± 0.038 | 0/90 | **9.33** | 0.378 | 64/90 |
| 0 | 0° | 3 | 0.6222 ± 0.034 | 0/90 | **0.56** | 0.192 | 80/90 |
| 5 | 2.7° | 0 | 0.4968 ± 0.115 | 0/90 | 0.00 | 0.394 | 46/90 |
| 10 | 5.4° | 0 | 0.5702 ± 0.122 | 0/90 | 0.00 | 0.405 | 49/90 |
| 20 | 10.8° | 3 | 0.6634 ± 0.037 | 0/90 | 0.00 | 0.195 | 81/90 |

*(Unidad: escapes por **episodio**, sumando los 5 agentes. Dividir por 5 para
obtener activaciones por agente-episodio.)*

Δ pareado de atascados: **+0.000, IC95 [0.000, 0.000]** en las once celdas
contra la base.

### TRES cosas rompen el mismo equilibrio, no dos

El escape se inhibe **tanto por ruido como por latencia**, y la latencia lo
hace **sin ruido alguno**:

| σ=0 | Escapes/episodio | Cobertura |
|---|---|---|
| ret = 0 | 9.11 | 0.5739 |
| ret = 1 | 9.33 | 0.5770 |
| **ret = 3** | **0.56** | **0.6222** ← el mejor valor del bloque |

Con σ > 0 las activaciones caen a **0.00 en las nueve celdas**, ya desde 5 mm.
Causa aritmética: la detección exige `‖Δpos‖ < 2 mm` sostenido, y con σ = 5 mm
el desplazamiento aparente entre decisiones es ~√2·5 = 7 mm. **Cero falsos
positivos** en todo el barrido: la rama "dispararse sin motivo" queda
descartada; la que ocurre es "dejar de dispararse".

Y sin embargo los atascos **no vuelven**. La lectura correcta no es "dos
mecanismos" sino **tres cosas que rompen el mismo equilibrio del CBF**:

- **el escape** — deliberado, medido, con histéresis y ciclo de trabajo acotado;
- **el ruido** — incidental (mecanismo del Exp F);
- **la latencia** — incidental, y suficiente por sí sola (ret=3 con σ=0 baja
  los escapes a 0.56/ep y aun así da 0/90 atascos y la mejor cobertura del
  bloque sin ruido).

### ¿Es entonces necesario el escape?

El factorial 2×2 en Python dice que **sí**: sin escape y sin perturbación la
cobertura cae a 0.2985 y los atascos vuelven. Pero en Webots **cualquier
perturbación realista rompe el equilibrio sola**.

La lectura honesta: **el escape es la solución determinista y controlada**;
ruido y latencia producen el mismo efecto **por accidente**. En el laboratorio
estarán las tres presentes y **no se podrá saber cuál está actuando** — sólo
que el enjambre no se traba.

Eso tiene una consecuencia de diseño que conviene dejar escrita: el escape
sigue justificándose no porque sea el único que puede desatascar, sino porque
es el único cuyo comportamiento está caracterizado (2% de ciclo de trabajo,
0 agotados, magnitud de recorte 0.037). Depender de que el ruido haga el
trabajo es depender de una propiedad no especificada del sistema de captura.

### El mínimo en σ = 5 mm: NO concluyente

La cobertura no es monótona — cae a 0.4968 en σ=5 (ret=0) y se recupera
después. **Pero el efecto no está establecido:**

```
base (σ=0)  : 0.5739 ± 0.0446
σ=5 mm      : 0.4968 ± 0.1148     (std 2.6× la de la base)
Δ pareado   : −0.0771  IC95 [−0.1353, −0.0189]   |t| = 2.60
```

Con n = 18 y una desviación casi tres veces mayor, el IC95 **apenas** excluye
el cero. Es la clase de resultado que no sobrevive a una réplica. **No se
recomienda ninguna acción operativa a partir de él**, y en particular no se
afirma que exista una "zona muerta" entre mecanismos: eso sería
sobreinterpretar un mínimo local con potencia insuficiente.

Para establecerlo haría falta **más semillas en σ=5 mm**, no un barrido fino de
σ ∈ (0,5) — un barrido más denso arrastraría el mismo problema de potencia en
cada celda nueva. Queda como verificación pendiente, no como hallazgo.

### Interacción

Subaditiva otra vez, consistente con el Exp F: cobertura conjunta **+0.0895**
contra suma de individuales **+0.1283** (interacción **−0.0389**). Coherente
con que ruido y latencia actúen sobre el mismo equilibrio: una vez roto, el
segundo no aporta.

### Las tres preguntas de mitigación

- **¿Filtrado de pose?** **No hay evidencia que lo justifique ni que lo
  contraindique.** El sistema no falla en ningún punto del rango evaluado, así
  que no hay problema que filtrar. La única señal en contra —el mínimo en
  σ=5 mm— no está establecida (ver arriba).
- **¿Reducir la latencia del lazo?** **No.** El retardo de 3 decisiones da la
  mejor cobertura en las cuatro filas de ruido, y con σ=0 es la mejor celda del
  bloque. No es un objetivo de diseño.
- **¿Ampliar el margen del CBF?** **Sí**, por la misma razón del Exp F, y acá
  con un término adicional: la base **ya** tiene 52/90 violaciones (contra 9/90
  sin escape) porque **el escape maniobra cerca de la barrera**. El presupuesto
  del margen debe absorber **ruido + latencia + maniobra de recuperación**, no
  sólo la holgura geométrica. Que el contacto físico siga en 0/1080 indica que
  el margen actual alcanza, pero está trabajando con menos reserva de la que su
  dimensionamiento suponía.

**Artefactos:** `resultados/expH_barrido_5agentes.csv` (216 filas, `d_min` con
8 decimales), `expH_resumen_5agentes.txt`. El prefijo de salida es `expH`
cuando `ESCAPE_ACTIVO=True` y `expF` cuando no, así ambas tablas conviven.

---

## Exp I — Generalización a distinto número de agentes (Python, 5×2×100)

**Pregunta:** la metodología afirma que el esquema de parámetros compartidos
"favorece la generalización a distintos números de agentes sin reentrenamiento
adicional", apoyada sólo en una cita. Este experimento produce evidencia propia
evaluando `modelo_PRIMERO` (entrenada con 5 agentes) sobre enjambres de 2, 3, 5,
7 y 10 agentes, sin tocar los pesos.

**Por qué en Python y no en Webots:** en física, variar el número de agentes
mezcla generalización de la política con degradación por densidad, y ya está
medido que la densidad domina (atascos 16.7% con 1 agente, 25.0% con 2, 56.7%
con 5). En el entorno de entrenamiento la única variable es el cardinal del
enjambre, así que el efecto queda aislado.

**Invarianza al cardinal, verificada por lectura antes de asumirla:** el env
deriva todo de `n_agents` y `n_hotspots` es independiente (queda en 3);
`MeanEmbeddingEncoder.encode` promedia sobre `|N_i|` y devuelve el vector cero
si `|N_i|=0` → salida de dimensión fija para cualquier n; `politica_madrl` hace
`predict` sobre un batch `(n, 24)` sin dependencia de n. Ningún cambio de código
en el env.

**Diseño:** n ∈ {2,3,5,7,10} × {reflexion, bloqueante} × 100 semillas del
protocolo estándar (`420000+i`) = **1000 episodios**, pareado por semilla.
`deterministic=True`, `domain_rand=False`, 500 pasos, arena 3.0×3.0,
`comm_radius=1.0`, `n_hotspots=3`. El pareo comparte la dinámica de hotspots
entre valores de n; lo único que varía es el cardinal.

**Métrica clave — activación del embedding:** fracción de agente-decisión en que
el `neighbor_embedding` de la observación es NO NULO. Es **exacta, no
aproximada**: la componente 5 de φ(j) es `distancia/comm_radius`, siempre `>0`
para un vecino visible, así que el embedding es exactamente `0⁸` si y sólo si el
agente no ve vecinos. Mide cuánto del camino multiagente de la política se
ejercita realmente en cada densidad.

**Sorteo de poses iniciales:** el fallback de grilla se usó **0/1000
episodios** (incluido n=10), así que las poses iniciales son comparables entre
todos los n y la comparación pareada no queda condicionada por ese lado.

### Validación de control — múltiples cruces, todos reproducen

| Métrica (n=5) | Exp I | Referencia previa |
|---|---|---|
| Cobertura reflexión | 0.68129083 | 0.68129082 (metricas_100eps.json, \|Δ\|=1.1e-8) |
| Cobertura bloqueante | 0.4516 | 0.4516 (Exp C) |
| Δ pareado borde | −0.2297, IC95 [−0.2385,−0.2208], 100/100 | idéntico (Exp C/D/E) |
| Reflexiones/episodio | 45.74 | 45.74 ± 5.54 (Exp B) |
| Frac. agente-paso en borde | 0.5117 | 0.5117 (Exp D) |
| Colisiones <0.15 m (reflex.) | 0.210 | 0.21 (metricas_100eps.json) |

### Resultado 1 — no hay colapso; degradación suave y monótona

| n | Cob. total (reflex.) | Cob. **por agente** | Cob. total (bloq.) | Cob. por agente (bloq.) |
|---|---|---|---|---|
| 2 | 0.3785 ± 0.030 | **0.1892** | 0.1258 | 0.0629 |
| 3 | 0.5183 ± 0.027 | **0.1728** | 0.2429 | 0.0810 |
| 5 | 0.6813 ± 0.020 | **0.1363** | 0.4516 | **0.0903** |
| 7 | 0.7582 ± 0.016 | **0.1083** | 0.5791 | 0.0827 |
| 10 | 0.7967 ± 0.019 | **0.0797** | 0.6681 | 0.0668 |

La cobertura **total** crece monótona con n (trivial: más agentes cubren más;
no es evidencia de generalización). La cobertura **por agente** cae de forma
**suave y monótona** bajo reflexión (0.189 → 0.080, sin discontinuidad en
ningún n). **En ninguna densidad la política colapsa.**

Detalle que sí sugiere un leve sobreajuste al cardinal de entrenamiento: bajo
**borde bloqueante** la cobertura por agente **tiene su máximo exactamente en
n=5** (0.0903), y es menor tanto por debajo como por encima. Bajo reflexión —la
condición de entrenamiento— la curva es monótona; el pico en n=5 aparece sólo
en la condición fuera de distribución.

### Resultado 2 — el mecanismo: cuánto se ejercita el camino multiagente

Fracción de agente-decisión con vecino visible (embedding no nulo):

| n | reflexión | bloqueante |
|---|---|---|
| 2 | 0.103 | 0.054 |
| 3 | 0.190 | 0.129 |
| 5 | 0.351 | 0.263 |
| 7 | 0.513 | 0.394 |
| 10 | 0.740 | 0.643 |

Casi lineal en n, saturando hacia n=10. **Con n=2 la política corre ~90% del
tiempo como agente aislado** (el término `neighbor_embedding` es cero); con
n=10 casi nunca está sola. El régimen que la política realmente ejercita cambia
de forma masiva con la densidad, aunque los pesos sean los mismos. El valor de
n=2 (~10–20%) es consistente con el ~21% citado para Webots con 2 agentes.

### Resultado 3 — la seguridad NO generaliza

Colisiones por episodio (reflexión):

| n | pares <0.15 m | pares <0.22 m |
|---|---|---|
| 2 | 0.01 | 0.02 |
| 3 | 0.06 | 0.09 |
| 5 | 0.21 | 0.32 |
| 7 | 0.72 | 1.15 |
| 10 | **2.70** | **4.43** |

Escalan mucho peor que linealmente: de n=5 a n=10 el contacto de chasis se
multiplica por **13**. La política sola no mantiene separación inter-agente
fuera de su régimen de entrenamiento; para n>5 hace falta la capa CBF (ya
adoptada para la fase física). **La generalización es en cobertura, no en
seguridad.**

### Resultado 4 — la dependencia del borde cambia con n

Δ pareado (bloqueante − reflexión) por cada n:

| n | Δ absoluta | IC95 | Δ relativa | Episodios peor |
|---|---|---|---|---|
| 2 | −0.2527 | [−0.2626, −0.2428] | **−66.8%** | 100/100 |
| 3 | −0.2754 | [−0.2874, −0.2633] | −53.1% | 100/100 |
| 5 | −0.2297 | [−0.2385, −0.2208] | −33.7% | 100/100 |
| 7 | −0.1791 | [−0.1860, −0.1721] | −23.6% | 100/100 |
| 10 | −0.1286 | [−0.1358, −0.1213] | **−16.1%** | 100/100 |

El efecto es universal (100/100 en todos los n) pero su **magnitud relativa
decrece monótona** al crecer n: con pocos agentes la política depende mucho más
del rebote idealizado. Coherente con la fracción de agente-paso contra el borde,
que también cae con n (0.72 → 0.62 → 0.51 → 0.47 → 0.43): más agentes → cada uno
pasa menos tiempo pegado al borde → menos exposición a la diferencia de
dinámica de pared. **Consecuencia:** un resultado de robustez sim-to-real
medido con n=5 no es extrapolable a otro cardinal.

### Confusión no resuelta (declarada)

Con n grande en una arena de 3×3, parte de la caída de cobertura por agente es
**saturación espacial** (no cabe más cobertura útil en 9 m²), no fallo de la
política. Este diseño no separa "la política no generaliza" de "el espacio se
saturó". La activación del embedding y las colisiones ayudan a acotar —muestran
que el comportamiento multiagente sí cambia y sí se degrada—, pero no cierran la
atribución. Haría falta barrer también el tamaño de arena a densidad constante.

### Qué le hace este experimento a la afirmación de la tesis

La frase de la metodología —parameter sharing "favorece la generalización a
distintos números de agentes sin reentrenamiento"— **hay que acotarla a un
rango y matizarla, no puede quedar como enunciado general**:

- **Se sostiene, acotada:** la política es funcional sobre n ∈ [2, 10] sin
  reentrenar, con degradación **suave y monótona** de la cobertura por agente y
  **sin colapso en ninguna densidad**. El Mean Embedding cumple su función de
  invarianza al cardinal en la práctica, no sólo formalmente.
- **Matiz 1 — seguridad:** la separación inter-agente **no** generaliza; las
  colisiones escalan 13× entre n=5 y n=10 y para n>5 se depende de la capa CBF.
- **Matiz 2 — condición fuera de distribución:** bajo borde bloqueante la
  cobertura por agente es óptima justo en n=5, señal de un leve sobreajuste al
  cardinal de entrenamiento.
- **Matiz 3 — transferencia de garantías:** la dependencia de la política
  respecto de la dinámica de borde varía con n (−67% a −16%), así que las
  mediciones de robustez a n=5 (Exp F–H) no se extrapolan a otro cardinal.

Reformulación sugerida para el documento: *"el esquema de parámetros compartidos
permite desplegar la política en enjambres de 2 a 10 agentes sin reentrenamiento,
con una degradación suave y monótona de la cobertura por agente y sin colapso;
la seguridad inter-agente, en cambio, se degrada con la densidad y depende de la
capa CBF para n mayor que el de entrenamiento."*

**Artefactos:** `experimentos/expI_escalabilidad/` (carpeta nueva, copias de
`lib/`, `modelo_PRIMERO.zip` y `correr_experimento_D.py` verificadas byte a byte
por sha256), `correr_experimento_I.py`,
`resultados/experimento_I_completo.csv` (1000 filas),
`resultados/resumen_experimento_I.txt` (5 tablas + cuadro LaTeX con coma
decimal), `figuras/fig_escalabilidad_{cobertura,embedding,seguridad}.png`
(300 dpi, es-ES, sin título). Ninguna corrida nueva pisa artefactos previos.

---

## Exp J — Sintonización con presupuesto y semillas corregidos (Python, 20×3×200k)

**Pregunta:** el estudio original (`optuna_studies/tesis_v1.db`) barrió doce
hiperparámetros con veinte pruebas de 100k pasos, maximizando recompensa media
sobre una semilla. Este experimento repite la sintonización corrigiendo cuatro
desajustes metodológicos y verifica una hipótesis que el capítulo declara pero
no comprueba: que la degradación más allá de 200k se debe al desajuste entre el
presupuesto de sintonización y el horizonte de uso.

**Encuadre:** el entregable es el ANÁLISIS. El experimento NO reemplaza a
`modelo_sanidad` / `modelo_PRIMERO`, sobre los que se midió toda la cadena de
validación A–I. Explora qué gobierna el desempeño del algoritmo.

### Los cuatro cambios metodológicos

| | Estudio original | Exp J |
|---|---|---|
| Espacio | 12 hiperparámetros | 4 (los de \|ρ\|>0.30 más λ_entropy) |
| Objetivo | recompensa media de evaluación | cobertura AoI |
| Presupuesto | 100 000 pasos | 200 000 pasos |
| Semillas | 1 | 3 (42, 123, 777), objetivo = media |
| Episodios de evaluación | 10 | 20 (retención) + 30 disjuntos (objetivo) |
| Retención | **ninguna** (ver abajo) | mejor punto de control por cobertura, cada 20k |

**⚠ Revisión 2026-09-24 (depende de λ).** El criterio |ρ|>0.30 que metió a
λ_cbf en el espacio sale del estudio original, que correlacionaba contra
RECOMPENSA. Para los λ, esa correlación es en parte mecánica: ver la revisión
en el Resultado 3.

### Dos bugs de implementación encontrados en `train.py`

**El `EvalCallback` del estudio original se disparó UNA sola vez por trial, al
final.** SB3 compara `n_calls % eval_freq`, o sea LLAMADAS al callback, mientras
`train.py:736` le pasa `presupuesto//10` como si fueran pasos de entorno. Con
5 agentes × 2 envs = 10 streams, `n_calls` llegó a 10 000 justo al agotar los
100k y disparó la única evaluación. Verificado en
`mejores_trials/trial_000/evaluations.npz`: `timesteps [100000]`, `results` de
forma (1,10); los veinte `best_model.zip` guardan `num_timesteps=100000`.
**Los "mejores modelos" de los trials son el punto de control FINAL.** Esto
matiza H-04, que los describe como "checkpoint de early-stop".

**El warmup del pruner nunca protegió nada.** `MedianPruner(n_warmup_steps=5)`
(`train.py:141`, `train.py:1295`, numeración de la versión de entonces) se
compara contra el `step` reportado, que es `num_timesteps` (10 000+). Por eso
los diez trials podados murieron todos en el primer reporte, al 10% del
presupuesto. En el Exp J el warmup es 100 000 pasos.

Mientras corrió el Exp J, `train.py` NO se modificó, para no alterar el script
con el que se produjeron los resultados existentes. El Exp J corre con su propio
`estudio_J.py`, que importa de `train.py` sólo las configuraciones y los
constructores de entorno y de PPO (`estudio_J.py:127-134`), no el callback ni
el pruner afectados. El diagnóstico `diagnostico_sin_vecnormalize.py` ya tenía los
dos bugs corregidos ("Bug C"), así que la curva 100k–500k del documento **no
está afectada**: los cinco `.zip` verificados declaran `num_timesteps` exactos
de 100k a 500k.

**Corregido el 2026-09-24 — estado posterior de `train.py`.** Este párrafo
decía que los bugs "siguen presentes"; dejó de ser cierto el mismo 2026-09-08,
después del estudio. Ese día `train.py` se corrigió: warmup de 100 000 pasos de
entorno (hoy `train.py:196`) y `eval_freq` convertido a llamadas (`:740` y
`:921`). Más tarde se corrigió también el `CheckpointCallback` (`:934`).
El respaldo `fase_preliminar2/train_respaldo_20260908.py` se tomó justo antes de
ese último cambio (20:59:11 contra 20:59:31) y **ya trae los otros tres**: su
diff contra `train.py` es sólo el `save_freq`. **La versión con
`n_warmup_steps=5` que produjo el estudio original no se conserva como
archivo**; su comportamiento queda documentado sólo en esta sección.

### Validación de control

| Métrica | Exp J | Referencia previa |
|---|---|---|
| Cobertura `modelo_PRIMERO`, 100 eps | 0.68129082 | 0.68129083 (Exp I), 0.6813 oficial |
| Colisiones `modelo_PRIMERO`, 100 eps | 0.2100 | 0.21 (`metricas_100eps.json`) |
| Entrenamiento fresco 200k, Trial 13, semilla 42 | 0.68359383 | 0.6813 oficial |
| Semilla 42 de la prueba 7 en 100k, la misma trayectoria entrenada dos veces (estudio y diagnóstico) | 0.68209981 / 0.67661919 | misma política en dos conjuntos: 20 eps offset 0 (estudio) y 30 eps offset 1000 (diagnóstico); diferencia +0.00548 |

**Corregido el 2026-09-24 — fila de la semilla 42.** Decía «dos corridas
independientes» y «difieren sólo por el conjunto de episodios (+0.010, ver
abajo)». Es la MISMA trayectoria: a 200k, `policy.pth` y el estado del
optimizador del estudio y del diagnóstico son idénticos bit a bit en las
semillas 42, 123 y 777. La diferencia medida es +0.00548. El 0.010 es el de
`modelo_PRIMERO`.

**Desplazamiento entre conjuntos de episodios, medido:** el mismo
`modelo_PRIMERO` da 0.68359383 sobre el conjunto de retención (20 eps, offset 0)
y 0.67359557 sobre el de evaluación final (30 eps, offset 1000). Ese ~0.010 es
común a todos los modelos y explica los valores NEGATIVOS de `sesgo_retencion`.

**⚠ Revisión 2026-09-24.** Las dos afirmaciones del párrafo anterior quedan
sin sostén.

- **Que sea común a todos los modelos no está verificado.** En los seis pares
  sin selección del Exp J (prueba 7, semillas 42/123/777 a 100k y 200k, la
  misma política en el estudio y en el diagnóstico), retención − final va de
  −0.01230 a +0.01452, con media +0.0016. Un desplazamiento común de +0.010 no
  se confirma ni se rechaza.
- **Tampoco explicaría los valores negativos de `sesgo_retencion`**, que es
  retención − final: un desplazamiento positivo lo empujaría hacia arriba.

### Resultado 1 — la mejor configuración

```
Prueba 7 — λ_cbf=14.7744  λ_ent=0.8720  n_epochs=8  n_steps=64
cobertura 0.68615543 ± 0.00863623   CV 0.0126   colisiones 2.844
```

Comparación bajo el MISMO protocolo (30 episodios disjuntos):

| | Cobertura | CV entre semillas | Colisiones |
|---|---|---|---|
| `modelo_PRIMERO` / Trial 13 (1 semilla) | 0.67359557 ± 0.02400525 | 0.1051–0.1428 | 0.133 |
| Exp J, prueba 7 (media de 3) | 0.68615543 ± 0.00863623 | 0.0126 | 2.844 |

En cobertura la diferencia (+0.0126) es del orden de la desviación entre
semillas: **no es una mejora establecida**. Lo que sí cambia es la naturaleza
del número — media de tres semillas en vez del mejor punto de una semilla
afortunada — y la estabilidad.

**⚠ Revisión 2026-09-24 (comparación entre configuraciones que difieren en
λ_cbf y λ_entropy).** La tabla no compara bajo el mismo protocolo en CV ni en
colisiones.

- **Dónde se mide cada fila.**
  - La prueba 7 está en su punto RETENIDO, elegido por cobertura. Además, el
    conjunto final fue el objetivo de TPE, así que la selección la favorece.
  - El Trial 13 está en su punto final: 202 240 pasos, una semilla.
- **La prueba 7 a paso fijo de 200k** (Resultado 2, mismo conjunto final) da
  0.62567153 ± 0.05569633 (CV 0.089) y 1.400 colisiones.
- **Los CV 0.1051–0.1428 del Trial 13** son de modelos de 100k.
- **La «estabilidad» no está establecida.** El +0.0126 no compara cantidades
  homogéneas.

Re-estimación fuera de muestra, con 20 semillas nuevas por brazo: Exp P.

**Precisión sobre el 0.589 de H-05:** ese número es el CV de la RECOMPENSA
(−10.350 / −31.939 / −58.878 → σ/|μ| = 0.589, `reporte_reproducibilidad.md:32`),
NO de la cobertura. Los CV de COBERTURA del Trial 13 son 0.1051 (protocolo de
reproducibilidad: 0.5546/0.5269/0.4509) y 0.1428 (multimétrica:
0.698/0.679/0.532). La comparación correcta es contra ésos.

**El protocolo de evaluación no explica la diferencia, y está medido.** Se
recalculó el CV de la prueba 7 sobre los MISMOS modelos evaluando cada semilla
en SU PROPIO conjunto de episodios (`semilla·10000+i`, como
`verificacion_seeds`): **CV 0.010613**, contra 0.012586 con el conjunto común.
La diferencia es despreciable. Por tanto la reducción del CV de 0.105–0.143 a
~0.011 es real y no un artefacto de protocolo.

**⚠ Revisión 2026-09-24.** El control de arriba sólo cambió el conjunto de
episodios. No controló la retención ni el presupuesto:

- el CV de la prueba 7 se midió en el punto retenido y a 200k;
- el del Trial 13, en el punto final y a 100k.

A paso fijo de 200k, la prueba 7 tiene CV 0.089. Que la reducción sea «real»
queda sin establecer.

Las diez pruebas completas. **Conteo corregido el 2026-09-24 contra la base**
(decía «de veinte; diez podadas»): `experimento_J.db` tiene 22 registros,
pruebas 0–21. Son 10 COMPLETE, 11 PRUNED (9 en la etapa 1 y 2 en la etapa 2)
y 1 RUNNING huérfano. La 0 y la 1 salen del primer lanzamiento, que se
interrumpió con la 1 a medio correr. Las 20 restantes, de la 2 a la 21, salen
del segundo lanzamiento, reanudado con 20 pruebas. Entre las diez completas hay
nueve configuraciones distintas (0≡2, ver limitaciones):

| Prueba | λ_cbf | λ_ent | n_epochs | n_steps | Cobertura | CV | Colisiones |
|---|---|---|---|---|---|---|---|
| 7 | 14.774 | 0.872 | 8 | 64 | 0.68615543 | 0.0126 | 2.844 |
| 6 | 14.692 | 0.333 | 7 | 64 | 0.68466557 | 0.0281 | 2.822 |
| 17 | 7.922 | 0.831 | 14 | 64 | 0.68398049 | 0.0265 | 1.544 |
| 13 | 14.868 | 0.105 | 8 | 64 | 0.67316780 | 0.0307 | 3.122 |
| 8 | 11.425 | 0.962 | 9 | 128 | 0.67247357 | 0.0044 | 1.644 |
| 5 | 12.654 | 0.503 | 5 | 64 | 0.65656427 | 0.0419 | 3.222 |
| 0 / 2 | 6.244 | 1.906 | 12 | 256 | 0.58722550 | 0.1055 | 1.322 |
| 3 | 3.184 | 0.396 | 3 | 1024 | 0.45945694 | 0.4088 | 2.133 |
| 4 | 9.416 | 1.445 | 3 | 1024 | 0.32539906 | 0.1556 | 1.033 |

Las cinco primeras son indistinguibles entre sí y de la referencia en cobertura.
Lo que las separa es el CV y las colisiones. **⚠ Revisión 2026-09-24:** esas
dos columnas están medidas en el punto retenido (trampa 1 del Resultado 3). En
el último punto de la curva, a 200k sobre los 20 episodios de retención, el
orden cambia:

| Prueba | 7 | 6 | 17 | 13 | 8 |
|---|---|---|---|---|---|
| CV | 0.089 | 0.385 | 0.064 | 0.490 | 0.085 |
| Colisiones | 1.767 | 1.717 | 0.167 | 2.483 | 0.817 |

Fuente: último punto de `curva` en `cfg_*/semilla_*/resultado_semilla.json`,
media de 3 semillas.

Las pruebas 0 y 2 son la MISMA
configuración: al reanudar el estudio, el TPE sembrado reinició su secuencia y
propuso una configuración duplicada (ver limitaciones).

### Resultado 2 — HIPÓTESIS (1) REFUTADA

Diagnóstico de puntos de control con la mejor configuración, 500k pasos,
**3 semillas** (el diagnóstico original usó una):

| Pasos | Cobertura (media ± σ entre semillas) | Colisiones |
|---|---|---|
| 100 000 | 0.60090543 ± 0.10192919 | 2.767 |
| 200 000 | 0.62567153 ± 0.05569633 | 1.400 |
| 300 000 | 0.60031574 ± 0.11335795 | 1.189 |
| 400 000 | 0.41736344 ± 0.16245461 | 0.656 |
| 500 000 | 0.53360612 ± 0.10728186 | 0.567 |

**Sintonizar con el presupuesto igual al horizonte de uso NO eliminó la
degradación.** La hipótesis del desajuste presupuesto/horizonte queda refutada.

Las semillas por separado dicen algo más preciso:

| Semilla | 100k | 200k | 300k | 400k | 500k |
|---|---|---|---|---|---|
| 42 | **0.6766** | 0.6349 | 0.4700 | 0.5999 | 0.6076 |
| 123 | 0.4850 | **0.6762** | 0.6548 | 0.2885 | 0.5827 |
| 777 | 0.6411 | 0.5659 | **0.6762** | 0.3637 | 0.4106 |

**Las tres alcanzan el mismo techo (~0.676) en pasos DISTINTOS** — 100k, 200k y
300k — y después caen. La degradación no es monótona (hay recuperaciones) y la
dispersión entre semillas llega a 0.16. No es sobreentrenamiento sistemático:
es inestabilidad del entrenamiento con varianza alta entre semillas.

**Consecuencia práctica:** la retención de puntos de control a resolución fina
no es un refinamiento sino un requisito. La misma configuración da 0.686 con
retención cada 20k y 0.60–0.63 muestreando cada 100k — no porque un método mida
mejor, sino porque el desempeño oscila lo suficiente como para que el momento en
que uno mire determine el resultado.

### Resultado 3 — qué gobierna el desempeño

**Hay CINCO análisis de correlación distintos en los artefactos y NO son
intercambiables.** Confundirlos produce contradicciones aparentes: λ_cbf sale
ρ=+0.695 en uno y ρ=+0.132 en otro. Cada uno se identifica por su variable
dependiente, el conjunto sobre el que se calcula y su n:

| | Variable dependiente | Conjunto | n |
|---|---|---|---|
| **A** | cobertura media de 3 semillas, **en su punto retenido** | pruebas completas | **10** |
| **B** | cobertura de la semilla 42, en su punto retenido | pruebas con semilla 42 evaluada | **12** |
| **C** | colisiones medias de 3 semillas, **en su punto retenido** | pruebas completas | **10** |
| **D** | colisiones **a paso fijo 200k** | semillas individuales | **29** |
| **E** | cobertura **a paso fijo 200k** | semillas individuales | **29** |

**⚠ Revisión 2026-09-24:** A, B y C cuentan dos veces la configuración 0≡2 (n
real 9/11/9), y D y E tienen n = 27, no 29. Recálculo con Holm en «Revisión
del 2026-09-24», debajo de la tabla siguiente.

| Parámetro | A (cob, ret, 10) | B (cob s42, ret, 12) | C (col, ret, 10) | D (col, fijo, 29) | E (cob, fijo, 29) |
|---|---|---|---|---|---|
| `lambda_cbf` | +0.695 p=0.026 | +0.607 p=0.036 | +0.671 p=0.034 | +0.132 p=0.512 | +0.144 p=0.475 |
| `lambda_entropy` | −0.427 p=0.219 | −0.670 p=0.017 | −0.768 p=0.009 | −0.182 p=0.362 | −0.098 p=0.628 |
| `n_epochs` | +0.344 p=0.331 | +0.071 p=0.827 | −0.282 p=0.430 | −0.288 p=0.146 | +0.374 p=0.054 |
| `n_steps_exp` | **−0.895 p=0.0005** | −0.832 p=0.0008 | −0.712 p=0.021 | −0.016 p=0.938 | **−0.400 p=0.038** |

`scatter_hparams_J.png` es el **análisis A**. Referencia del estudio original,
contra RECOMPENSA y no cobertura: λ_cbf −0.76, n_epochs +0.48, n_steps_exp
+0.33, λ_entropy +0.28.

**⚠ Revisión 2026-09-24 (depende de λ).** Contra la recompensa, la
correlación de los λ es en parte mecánica. El entorno de evaluación del estudio
original usa los pesos de la propia prueba (`train.py:705-710`), y
r = … + λ_ent·r_ent − λ_cbf·p_cbf. Con el mismo comportamiento, la recompensa
baja al subir λ_cbf y sube al subir λ_ent. Los signos −0.76 y +0.28 son los que
predice la escala, así que no se comparan con A–E como efectos de conducta.

#### Revisión del 2026-09-24 — A, B y C sin la configuración duplicada, con Holm

**Qué se corrigió.**

- **El duplicado.** A, B y C contaban dos veces la configuración 0≡2: la
  prueba 2 reutilizó el resultado de la 0 y tiene user_attrs idénticos. Se
  quitó la 2, y quedan A y C con n = 9 y B con n = 11. La 1≡3 no entra en
  ningún análisis, porque la 1 no tiene métricas.
- **El n de D y E.** No tenían el duplicado, pero su n es **27, no 29**.
  `cfg_06b72b7fcf` y `cfg_4dc3f27f85` no tienen `config_barridos.json` y
  `analizar_estudio_J.py:123-126` las descarta. Son 27 semillas de **9**
  configuraciones, y los ρ y p publicados de D y E corresponden a n = 27.
- **Control.** Con el duplicado dentro, el recálculo reproduce bit a bit
  `resultados/analisis/comparativa.json` y la tabla de arriba.

**Holm, con familia = los 4 hiperparámetros de cada análisis** (α = 0.05).
Se declara ahora, a posteriori: los cinco análisis no se fijaron de antemano.

| Parámetro | A (n=9) ρ · p · p_Holm | B (n=11) ρ · p · p_Holm | C (n=9) ρ · p · p_Holm |
|---|---|---|---|
| `lambda_cbf` | +0.650 · 0.0581 · 0.174 | +0.600 · 0.0510 · 0.153 | +0.683 · 0.0424 · 0.127 |
| `lambda_entropy` | −0.367 · 0.332 · 0.402 | −0.591 · 0.0556 · 0.153 | −0.717 · 0.0298 · 0.119 |
| `n_epochs` | +0.471 · 0.201 · 0.402 | +0.212 · 0.532 · 0.532 | −0.193 · 0.618 · 0.618 |
| `n_steps_exp` | **−0.853 · 0.0034 · 0.014** | **−0.803 · 0.0029 · 0.012** | −0.679 · 0.0443 · 0.127 |

**Lectura.**

- **Ningún λ sobrevive.** Ninguna correlación de λ_cbf ni de λ_entropy es
  significativa tras Holm en A, B ni C. λ_cbf en A ya no lo es ni sin corregir
  (p = 0.058). Los p = 0.017 (λ_ent en B) y 0.009 (λ_ent en C) no se sostienen.
- **`n_steps_exp` sobrevive sólo en A y B**, que están en el punto retenido.
  La conclusión depende de cómo se defina la familia:
  - con familia A∪B (8 contrastes), se mantiene;
  - con una familia de los 20 contrastes de A–E, no sobrevive nada: el menor
    p_Holm es 0.059.
- **A paso fijo, E no sobrevive a la misma corrección** (p_Holm 0.154). Si se
  agrega por configuración (media de 3 semillas, n = 9, sin
  pseudorreplicación), da ρ = −0.468 y p = 0.204.
- **Sesgo de selección.** A, B y C están condicionados a sobrevivir la criba,
  que selecciona por la propia cobertura de la semilla 42.

**Artefactos.**

- Script: `experimento_J/recalcular_ABC_sin_duplicado_holm.py`, que lee la base
  en modo lectura.
- Salida: `resultados/analisis/correlaciones_ABC_sin_duplicado_holm.json`, con
  precisión completa.
- Las cifras las verificó una reproducción independiente.
- La familia de 20 contrastes y la agregación de E por configuración se
  calcularon aparte, sobre los mismos datos.

#### El único resultado positivo que aguanta: `n_steps_exp`

Es el único hiperparámetro con **efecto sostenido en los dos análisis**:
ρ = −0.895 (p=0.0005) a nivel de prueba y ρ = −0.400 (p=0.038) a paso fijo,
mismo signo y significativo en ambos. Buffers de rollout chicos favorecen la
cobertura. Las cinco mejores configuraciones del estudio usan `n_steps` de 64 o
128; las dos peores, 1024.

`n_epochs` queda al borde (+0.374, p=0.054 en E) y no se sostiene en A
(p=0.331): insuficiente para afirmarlo.

**⚠ Revisión 2026-09-24.** "Sostenido en los dos análisis" ya no vale.

- **En el punto retenido (A y B) se sostiene**, sin el duplicado y con Holm
  por análisis: A −0.853, p_Holm 0.014 (n = 9); B −0.803, p_Holm 0.012
  (n = 11).
- **A paso fijo (E, n = 27 semillas de 9 configuraciones) no se sostiene**:
  p_Holm 0.154. Agregado por configuración da −0.468, p = 0.204.

Lo defendible es un efecto en el punto retenido, condicionado a la familia de
Holm por análisis. Ver la revisión de arriba.

#### Sobre λ_cbf: el estudio NO tiene potencia para atribuirle efecto

Se declaró antes, incorrectamente, que "λ_cbf no predice las colisiones" como
resultado positivo. **Esa afirmación no es defendible y se retira.** Lo que los
datos muestran es que la diferencia entre ρ=+0.695 y ρ=+0.132 NO está en la
variable dependiente sino en el análisis:

- en el punto retenido λ_cbf correlaciona con **ambas**: +0.695 con cobertura
  (A) y +0.671 con colisiones (C);
- a paso fijo no correlaciona con **ninguna**: +0.144 (E) y +0.132 (D).

Su correlación aparente a nivel de prueba está confundida con dos cosas: la
posición del punto retenido, y `n_steps_exp`, que covaría con λ_cbf porque el
TPE los exploró juntos y da ρ=−0.895 sobre el mismo conjunto de diez. Con n=10
y muestreo concentrado por el TPE, ambas contribuciones no se pueden separar.
**La conclusión defendible es que este estudio no permite atribuir a λ_cbf
efecto en ninguna dirección.**

**⚠ Revisión 2026-09-24 (depende de λ).** Las cifras de este apartado cambian
así:

- **Los +0.695 (A) y +0.671 (C) incluyen el duplicado 0≡2.** Sin él son +0.650
  (p = 0.058) y +0.683 (p = 0.042), con p_Holm 0.174 y 0.127.
- **"El mismo conjunto de diez" son nueve configuraciones.** La covariación que
  se invoca está medida: ρ(λ_cbf, n_steps_exp) = −0.725, p = 0.027, n = 9.
- **D y E usan 27 semillas de 9 configuraciones.** Que λ_cbf "no correlacione"
  a paso fijo es ausencia de evidencia, no evidencia de ausencia.
- **La conclusión se refuerza y se extiende a λ_entropy**, cuyo p_Holm en
  A/B/C es 0.402/0.153/0.119. Tampoco se le puede atribuir efecto.

**Esto NO debilita el argumento de poner la seguridad en la capa de ejecución.**
Ese argumento no se apoya en una correlación observacional sino en el contraste
controlado ya existente (`test_lambda_cbf`), donde subir λ_cbf de 2.97 a 5.0
degradó simultáneamente cobertura y colisiones: variable manipulada, no
observada. Ese resultado sigue en pie por sí solo.

**⚠ Revisión 2026-09-24 (depende de λ_cbf).** "Por sí solo" es demasiado
fuerte.

- **Es un A/B de UNA semilla de entrenamiento por brazo.** El aumento de
  colisiones (0.20 → 0.43) no es significativo ni entre episodios (Welch
  p ≈ 0.09).
- **La misma semilla puede multiplicar las colisiones por 5 con una
  perturbación irrelevante.** El Exp L lo midió: con la misma semilla y sólo
  cambiando la aritmética de GPU, pasaron de 0.210 a 1.070.
- **La caída de cobertura (−0.089) cabe en la dispersión entre semillas** del
  Trial 13 ([0.532, 0.698]) y de la prueba 7 a 200k.
- **Queda como indicio sin réplica.** No alcanza para afirmar por sí solo un
  efecto de λ_cbf.

#### Dos trampas metodológicas, declaradas

**Contaminación por el punto retenido (afecta a A, B y C).** Las métricas
medidas en el punto retenido no describen a la configuración sino a dónde
aterrizó la retención — que va por cobertura y cae en pasos distintos según la
semilla. Ejemplo real (prueba 13, MISMA configuración): la semilla 42 retiene en
140k con 0.800 colisiones, la 123 en 100k con 3.633 y la 777 en 80k con 4.933.

**Pseudorreplicación (afecta a D y E).** Las 29 semillas provienen de ~12
configuraciones, tres semillas cada una: NO son 29 observaciones independientes
para un efecto de hiperparámetro. El n efectivo es el número de configuraciones,
no el de semillas, y los valores p de D y E son en consecuencia optimistas.
**⚠ Revisión 2026-09-24:** en D y E entran 27 semillas de 9 configuraciones,
no 29 de ~12 (ver la revisión del Resultado 3).

**Defecto de figura corregido.** La versión inicial de `scatter_hparams_J.png`
dibujaba 12 puntos —10 completas en azul y 2 podadas en rojo— mientras el ρ del
título se calculaba sólo sobre las 10, y la ordenada de los puntos rojos era la
cobertura de UNA semilla y no la media de tres: dos escalas distintas en el mismo
eje, sin declararlo. La figura regenerada indica el n en cada subtítulo, qué
puntos entran en el ρ, y que no es comparable con el análisis a paso fijo.

### Resultado 4 — la degradación no es universal

De 29 curvas de cobertura-contra-pasos, **20 tienen máximo identificable** —el
máximo supera al segundo mejor por más que el error estándar de la evaluación—
y 9 no lo tienen y quedan excluidas de cualquier correlación de posición. De las
20: **11 tienen su máximo antes de agotar el presupuesto y 9 al final**. Mediana
de la posición 150 000, con resolución de 20 000 pasos (no es estimación fina).
Degradación pico→final: mediana 0.012765, máxima 0.415860.

### Limitaciones declaradas

- **Muestreo asimétrico.** Sólo la semilla 42 reporta a Optuna y decide la
  criba. Una configuración con mala suerte en esa semilla muere sin saberse si
  era buena en promedio. El estudio NO explora el espacio de forma uniforme.
- **Potencia estadística.** Con 10 pruebas completas y 29 semillas, el estudio
  distingue efectos grandes y descarta los muy fuertes, pero no establece
  correlaciones moderadas. Es la misma crítica que este experimento le hace al
  estudio original, aplicada a sí mismo. **⚠ Revisión 2026-09-24:** son 9
  configuraciones completas distintas y, en D/E, 27 semillas de 9
  configuraciones. Para λ_cbf y λ_entropy ni siquiera descarta efectos
  fuertes, porque los intervalos de ρ con n = 9 son muy anchos.
- **El TPE concentra el muestreo.** A partir de la quinta prueba ya no muestrea
  uniformemente, así que una correlación de rango mide la relación DENTRO de la
  región explotada, no en todo el espacio. Afecta a ambos estudios.
- **Dos podas de frontera** (etapa 2, pruebas 14 y 20) descartaron
  configuraciones por 0.0013 y 0.0030 de cobertura, márgenes sin significado
  estadístico. La criba ahorra tiempo pero en esa franja selecciona al azar.
- **Configuraciones duplicadas (corregido el 2026-09-24).** Al reanudar, el TPE
  sembrado reinició su secuencia y volvió a proponer las dos primeras
  configuraciones. Hay DOS duplicados:
  - 0≡2: las dos quedaron COMPLETE; la 2 reutilizó por hash el resultado de la
    0 sin reentrenar.
  - 1≡3: la 1 es la huérfana RUNNING y la 3 la reentrenó completa.

  La base tiene 20 configuraciones distintas en 22 registros, 20 también entre
  las 21 terminadas, y 9 entre las 10 completas. Antes decía «19
  configuraciones distintas, no 20» y omitía el duplicado 1≡3. El valor
  repetido 0≡2 además sesga levemente hacia abajo la mediana de la criba.
- **CV: salvedad levantada.** Se sospechaba que el CV no fuera comparable con
  el de `verificacion_seeds` porque aquí las 3 semillas comparten conjunto de
  episodios y allá no. Medido sobre los mismos modelos, el protocolo cambia el
  CV de 0.012586 a 0.010613: no explica nada. La comparación es válida.
  **⚠ Revisión 2026-09-24:** sólo es válida respecto del conjunto de
  episodios. La retención y el presupuesto no se controlaron: a paso fijo de
  200k la prueba 7 tiene CV 0.089 (ver Resultado 1).
- **La retención por cobertura ignora las colisiones.** En la prueba 13, semilla
  42, el punto retenido (140k) tiene 1.200 colisiones y el de 200k tiene 0.100
  con 0.015 menos de cobertura. Al elegir un modelo hay que mirar la curva
  completa, no el punto que el callback retuvo.

### Qué revalidación exigiría adoptar el modelo nuevo

No se adopta. Si se adoptara, habría que rehacer, como mínimo:

1. **La cadena de seguridad completa.** La política nueva tiene 2.844 colisiones
   por episodio en la política desnuda contra 0.133 de la adoptada. Habría que
   verificar que el filtro CBF + escape la lleva a 0.000 en las 18 semillas de
   Webots, y recalibrar el filtro si no lo hace. **⚠ Revisión 2026-09-24:** el
   2.844 es del punto retenido. A paso fijo de 200k, sobre el mismo conjunto
   final, la prueba 7 da 1.400: unas 10 veces el 0.133 del Trial 13, no 20. La
   conclusión (hay que revalidar la seguridad) no cambia.
2. **Exp A–E** (atascos, dependencia de la reflexión, degradación bajo bordes
   bloqueantes, líneas base): todos se midieron sobre `modelo_PRIMERO`.
3. **Exp F–H** (robustez a ruido y latencia): el equilibrio de liveness del CBF
   depende de la política.
4. **Exp I** (generalización a n agentes): la seguridad no generalizaba ya con
   la política actual (colisiones 13× de n=5 a n=10); con una política que choca
   veinte veces más, hay que remedirlo. (**⚠ 2026-09-24:** unas 10 veces a
   paso fijo; ver el punto 1.)
5. **El reentrenamiento con bordes bloqueantes** (v2, `modelo_sanidad`), porque
   el Exp J usó reflexión elástica para aislar el efecto metodológico.
6. **La calibración del demo físico** y la brecha de actuación sim-real.

**Continuación → Exp P (preregistrado el 2026-09-24).** Es una confirmación
fuera de muestra, con propósito de estimación y no de superioridad.

- **Brazos:** la configuración de la prueba 7 y el Trial 13.
- **Semillas:** 20 nuevas por brazo (1001–1020), con el mismo código en modo
  trabajador.
- **Métrica primaria:** la cobertura del punto retenido sobre un conjunto de
  episodios nuevo (offset 2000, 100 eps).

Diseño: `fase_preliminar2/experimento_P/PREREGISTRO_P.md`. Resultados en su
propia entrada.

**Artefactos:** `fase_preliminar2/experimento_J/`
— `estudio_J.py`, `analizar_estudio_J.py`, `diagnostico_presupuesto_J.py`,
`fase0_costo.py`, `perfilar_cuello_botella.py`, `recomputar_referencia.py`
— `optuna_studies/experimento_J.db`, `resultados/estudio/cfg_*/semilla_*/`
— `resultados/analisis/` (CSV, comparativa, `scatter_hparams_J.png`,
`curvas_cobertura_J.png`, `referencia_recomputada.json`)
— `resultados/diagnostico_presupuesto/`

**Costo — corregido el 2026-09-24.** Decía «estudio completo en 2.07 h (20
pruebas, 10 completas × 3 semillas)». Las 2.07 h son sólo el **segundo
lanzamiento** (8-sep, 01:22:48→03:27:02):

- pruebas 2–21, con 9 COMPLETE: 8 entrenaron sus tres semillas y la 2
  reutilizó la 0;
- 2 semillas 42 llevadas a 200k y podadas en la etapa 2;
- 9 semillas 42 cortadas en la etapa 1 (8 en 100k, la 12 en 120k).

El **primer lanzamiento** (7-sep, 22:15:17→23:39:19) duró al menos 1.40 h:

- la prueba 0 completa, con sus tres semillas en serie;
- la semilla 42 de la prueba 1 hasta 200k, sin evaluación final.

**Tiempo de máquina del estudio: ≥ 3.47 h** (12 496 s, sin la pausa entre
lanzamientos). La GPU no se usó. **Reparto corregido el 2026-09-24:** aquí decía que el
entrenamiento es 83% simulación del entorno y 17% red neuronal, con un techo de
1.20× por Amdahl. Esa medición tomaba el entorno en serie. El Exp L midió la
corrida real y dio ~27% entorno / 73% red, con techo de 3.7×. También encontró
la GPU (RTX 4050) más lenta que la CPU a esta escala: 0.7–0.8× en
entrenamiento. La decisión de no usar GPU se sostiene, pero por ese resultado
del Exp L, no por Amdahl. La aceleración vino de repartir los episodios de
evaluación entre 5 procesos (3.08× medido en banco, con
`torch.set_num_threads(1)` por trabajador).

**Corregido el 2026-09-24:** decía además «y de correr las dos semillas de
confirmación en paralelo». **Ese par no aceleró.** En las 8 pruebas completas
del segundo lanzamiento tardó 3992 s de pared, contra 3662 s que habrían
costado las dos semillas en serie al ritmo de la semilla 42: razón 1.09, entre
1.03 y 1.20 según la prueba.

- **Entrenamiento:** cada trabajador fue 1.65–2.26× más lento que la semilla 42
  sola. Es consistente con CPU saturada, pero la carga no se registró.
- **Evaluación:** fue 2.11–2.41× más lenta, esperable por diseño, porque el pool
  es de 2 procesos y no de 5.
- **Entre lanzamientos:** la evaluación de una semilla pasó de 553–562 s a
  74.8–78.5 s. El pool explica una parte; el resto no está atribuido, porque la
  máquina no estaba aislada.

---

## Exp K — ¿Dónde falla la cobertura? Descomposición espacial (Python, 4×100)

**Pregunta:** toda la evaluación del proyecto reporta la cobertura como un
escalar agregado (0.6813 MADRL, 0.2644 Voronoi+PSO). Eso dice CUÁNTO cubre cada
estrategia, no DÓNDE falla.

**Diseño:** 4 estrategias × 100 semillas = 400 episodios, condición `reflexion`.
La descomposición es EXACTA, no aproximada: la métrica es `1 − media(grid_aoi)`
y la media espacial conmuta con el promedio sobre semillas, así que el mapa
promedio contiene literalmente el origen espacial del número reportado.
Estadística POR SEMILLA (sobre el mapa promediado no hay dispersión): la
cobertura de cada región se calcula por episodio y se comparan medias pareadas.

**Validación de control:** MADRL **0.681291**, heurística NN **0.254349** y
aleatoria **0.139373**, las tres con **|Δ| = 0.000000** a seis decimales
(tolerancia 5e-7, no estadística).

**Geometría declarada:** grilla 64×64 sobre arena 3.0 m ⇒ celda 0.046875 m.
Regiones: esquinas 144 celdas, bordes 1248, interior 2704 (partición exacta,
4096). Anillo de 0.30 m con la máscara IDÉNTICA a `cobertura_anillo` de
`entrenar_v3.py`: 6 filas por lado, indistinguible para cualquier umbral en
(0.2578125, 0.3046875) m. Bandas radiales de 4 celdas = 0.1875 m, 8 bandas que
cubren exactamente las 32 filas hasta el centro.

### Resultado principal: los modos de falla son OPUESTOS, no distintos

Cobertura por región (media ± desv. entre 100 semillas):

| Estrategia | Esquinas | Bordes | Interior | Total |
|---|---|---|---|---|
| MADRL (200k) | 0.6200 | **0.7140** | 0.6695 | 0.6813 |
| Voronoi + PSO | 0.0217 | 0.0702 | **0.3669** | 0.2644 |
| Heurística NN | 0.1702 | 0.2041 | **0.2820** | 0.2543 |
| Aleatoria | 0.0037 | 0.0338 | **0.1953** | 0.1394 |

**MADRL no tiene déficit perimetral: tiene superávit.** Sus bordes superan a su
interior en **+0.0445** pareado, IC95 **[+0.0303, +0.0587]**, t = 6.15, mejor en
71/100. Las otras tres van en sentido contrario, y con márgenes mucho mayores:
Voronoi+PSO **−0.2967** IC95 [−0.3121, −0.2814] (0/100), heurística NN
**−0.0779** IC95 [−0.0940, −0.0618], aleatoria **−0.1615** IC95
[−0.1709, −0.1522] (0/100).

El perfil radial lo muestra como un cruce de pendientes: la cobertura de MADRL
**decrece** con la distancia a la pared (0.6800 en la banda 0–0.1875 m, máximo
0.7557 en 0.1875–0.375 m, y baja a 0.5826 hacia el centro), mientras las tres
líneas base **crecen** monótonamente. Voronoi+PSO sólo alcanza a MADRL en las
dos bandas más centrales (0.6131 vs 0.6136 y 0.6176 vs 0.6180): su ventaja
declarada de partición geométrica existe únicamente lejos de la pared.

**Esquinas.** Es la única región donde MADRL sí queda por debajo de su propio
interior: **−0.0495** pareado, IC95 [−0.0781, −0.0209], t = −3.40, y por debajo
de sus propios bordes **−0.0940** IC95 [−0.1163, −0.0717]. El déficit existe,
pero es un orden de magnitud menor que el de las líneas base (Voronoi+PSO
esquinas 0.0217 contra interior 0.3669, factor 17). Coincide en localización con
los atascamientos del filtro CBF (16 de 17 en esquinas), sin filtro alguno de
por medio.

**Dominancia por región.** MADRL supera a las tres líneas base en las cuatro
regiones, **100/100 semillas en las doce comparaciones**. La ventaja es mayor en
bordes (+0.6438 vs Voronoi+PSO) que en interior (+0.3026): el margen agregado se
gana sobre todo en el perímetro.

### Anillo de 0.30 m, para cruce con los v3

MADRL **0.7042 ± 0.0494**, Voronoi+PSO 0.0652 ± 0.0457, heurística NN
0.2006 ± 0.0657, aleatoria 0.0307 ± 0.0305. Máscara idéntica a la de v3.

### Caveats verificados, no supuestos

**(a) ¿Bastan 100 semillas?** Split-half par/impar sobre los mapas. Separando
señal de ruido por celda (las mitades son independientes y de igual tamaño, así
que el ruido del mapa de 100 vale RMS(Δ)/2): la estructura supera al ruido en
las cuatro estrategias, pero por márgenes muy distintos — razón señal/ruido
Voronoi+PSO 6.55, aleatoria 2.99, MADRL 2.02, **heurística NN 1.28**.
**Consecuencia operativa: los mapas NO deben leerse celda a celda.** Sí son
válidas las lecturas agregadas por región y por banda —promedian entre 64 y 2704
celdas— que son las únicas que este experimento afirma, y cuya incertidumbre va
reportada como IC95 entre semillas.

**(b) Sesgo de arranque: CONFUSIÓN NO SEPARABLE.** Las poses iniciales se
sortean en el 80% central, `margen = 0.10·arena = 0.30 m`, o sea `[0.30, 2.70]²`.
Esa frontera **coincide exactamente** con `ANCHO_ANILLO = 0.30` de los v3: el
anillo perimetral es, literalmente, la región donde ningún agente nace jamás. A
50 pasos MADRL lleva 0.0687 en bordes contra 0.1955 en interior; al final la
relación se invierte a 0.7140 contra 0.6695. El **nivel absoluto** de cualquier
cobertura de anillo no es interpretable como déficit puro de la estrategia. Las
comparaciones ENTRE estrategias y ENTRE condiciones sí lo son, porque comparten
el sorteo y el sesgo es constante.

**(c) Resolución.** Declarada arriba; las bandas son 4× la celda, así que el
perfil no está limitado por la discretización.

### Hallazgo colateral: dos números que no son la misma cantidad

RESULTADO_PRIMERO reporta **0.140186** para la política aleatoria; este
protocolo da **0.139373**, igual que los CSV de los Exp D y E y que el 0.1394 de
la entrada del Exp E. MADRL y heurística NN, en cambio, coinciden con
RESULTADO_PRIMERO hasta el último dígito. La aleatoria es la ÚNICA estrategia
cuyo resultado depende de un RNG ajeno al entorno: los Exp D/E lo resiembran por
episodio con `default_rng(seed_ep)` para que el pareo sea válido, y
RESULTADO_PRIMERO usó su propio flujo. La diferencia (0.000813 = 0.07σ, con
σ = 0.0112) es estadísticamente nula, pero es de PROTOCOLO, no de ruido. Los
Exp D y E la dejaban pasar silenciosa por llevar `TOL = 0.01`; la tolerancia
exacta de este experimento la expuso. No invalida nada previo —la aleatoria
nunca sostuvo una conclusión por su nivel absoluto, sólo por su Δ pareada, que
es inmune— pero al citar esa línea base hay que decir bajo qué protocolo se
midió.

### Qué afirmación del documento toca este experimento

**MATIZA** la lectura del déficit perimetral. El documento venía sugiriendo, a
partir de la métrica de anillo de los v3 y del comportamiento en el borde del
Exp C/D, que la banda perimetral era zona deficitaria. Sobre la configuración
adoptada y sin filtro, **eso no se sostiene para MADRL**: el perímetro es donde
la política cubre MEJOR, y es donde gana la mayor parte de su ventaja sobre las
líneas base. Lo que sí es deficitario, y de forma acotada, son las **esquinas**.

**RESPALDA** la superioridad de MADRL sobre Voronoi+PSO del Exp E, y le da
mecanismo: el 2.6× agregado no está repartido de manera uniforme, se concentra
en el perímetro, y en las dos bandas más centrales las dos estrategias empatan.

**MATIZA** el nivel absoluto de toda cobertura de anillo del documento, la del
cuadro de la variante de alineación geométrica incluida (0.4565 anillo contra
0.5114 global): arrastra el sesgo de arranque descrito en (b). La comparación
ENTRE los tres pesos de λ_pared sigue siendo válida porque el sesgo es constante
en las tres; lo que no es interpretable de forma absoluta es el NIVEL.

**Artefactos:** `experimentos/expK_mapa_espacial/resultados/`
(`expK_mapas.csv`, `expK_perfil_radial.csv`,
`expK_regiones_por_semilla.csv`, `fig_mapa_espacial.png`,
`fig_perfil_radial.png`, `tabla_expK.tex`, `resumen_experimento_K.txt`).
Libs copiadas y verificadas idénticas por sha256; ningún original modificado.

---

## Exp L — Costo computacional: CPU frente a GPU (Python, 3 condiciones × 2 regímenes)

**Pregunta:** el catedrático pidió medir cuánto cambia el costo de entrenamiento
si la red corre en la GPU disponible (RTX 4050) y, para la tesis, cuánto cambia
el tiempo por decisión de la política, que el documento cita como 0.76 ms
contra 8.04 ms de Voronoi+PSO. El Exp J había descartado la GPU por Amdahl con
un reparto 83 % entorno / 17 % red y techo 1.20×; acá ese reparto se contrasta,
no se asume.

**Hardware declarado:** CPU Intel Core i5-13420H (8 núcleos físicos, 12
lógicos), 16 GiB RAM, Windows 11 26200. GPU NVIDIA GeForce RTX 4050 Laptop,
6141 MiB, driver 592.82, rueda torch cu128 (CUDA runtime 12.8), cuDNN 9.19,
capacidad de cómputo 8.9. Torch con 8 hilos en el proceso principal en las
tres condiciones. **La máquina NO estaba aislada**: corrían otras aplicaciones
del autor (videollamada, MATLAB, navegador); la ocupación de CPU del sistema se
muestreó cada 2 s durante cada corrida y se reporta al lado de cada cifra.

**Diseño — el confundido a evitar.** El venv con CUDA tiene torch 2.11.0+cu128
y la tesis torch 2.10.0+cpu; comparar uno contra otro mediría versión y
dispositivo a la vez. Las tres condiciones son:

| Condición | Intérprete | torch | device |
|---|---|---|---|
| `gpu` | `venv_lab4` | 2.11.0+cu128 | cuda |
| `cpu_control` | `venv_lab4` | 2.11.0+cu128 | cpu — **el control** |
| `referencia` | Python de la tesis | 2.10.0+cpu | cpu — tercer punto, mide la versión |

El contraste limpio es `gpu` contra `cpu_control` (misma rueda, sólo cambia el
dispositivo). En el venv se instalaron las MISMAS versiones que la tesis
(SB3 2.7.1, SuperSuit 3.9.3, PettingZoo 1.24.3, Optuna 4.8.0, gymnasium 1.2.3,
numpy 2.4.1, scipy 1.17.1); en el `pip freeze` del stack importado sólo difiere
torch (`resultados/diff_freeze_tesis_vs_venv.txt`). El intérprete de la tesis
no se tocó. `train.py` no se modificó: la copia `train_L.py` agrega únicamente
el parámetro `dispositivo` a `construir_modelo_ppo` (diff de seis líneas).
**Era necesario**: sin él SB3 usa `device="auto"`, que en el venv habría elegido
CUDA sin declararlo.

**Dos hallazgos de implementación, declarados.** (1) Los trabajadores del VecEnv
(4 procesos, `num_cpus=4`) arrancan con el ejecutable BASE (el Python de la
Store) aunque hereden la ruta de paquetes del venv: es el comportamiento de
`multiprocessing` en venvs de Windows (`sys._base_executable`). El entorno
corre por tanto en el mismo binario en las tres condiciones; sólo cambia el
proceso principal, que es donde vive la red. (2) Los cronómetros instalados
como atributos de instancia arrastran el VecEnv al `save()` de SB3 y cuelgan el
proceso al encurtir las tuberías; se retiran antes de guardar.

### Régimen 1 — entrenamiento (Trial 13, semilla 42, 200 000 pasos, 4 envs = 20 flujos)

Sin `EvalCallback` (contaminaría el tiempo). Una corrida = 79 iteraciones PPO;
cada iteración = rollout de 2560 transiciones + actualización de 520
minibatches de 64 (13 épocas × 40). Se cronometra por separado el entorno
(`step_async`+`step_wait`, incluye IPC), la inferencia del rollout
(`collect_rollouts` − entorno) y la actualización (`train()`), con
`torch.cuda.synchronize()` antes de detener cada reloj en CUDA. Cada condición
se corrió dos veces (la referencia una), porque la carga ajena resultó
determinante.

**Totales crudos, corrida 1** (s de pared; carga = ocupación media del sistema
en % de 12 hilos lógicos durante la corrida):

| Condición | learn | entorno | inferencia | actualización | red | carga |
|---|---|---|---|---|---|---|
| gpu | 1175.6 | 185.0 (15.7 %) | 69.8 (5.9 %) | 920.7 (78.3 %) | 990.5 (84.3 %) | 46.0 |
| cpu_control | 257.2 | 68.1 (26.5 %) | 11.8 (4.6 %) | 177.3 (68.9 %) | 189.2 (73.5 %) | 81.9 |
| referencia | 283.6 | 75.6 (26.7 %) | 12.5 (4.4 %) | 195.5 (68.9 %) | 208.0 (73.3 %) | 80.3 |

**Por iteración PPO, todas las corridas** (mediana (mínimo) sobre 79
iteraciones; ms/minibatch = actualización/520):

| Corrida | learn [s] | entorno/iter [s] | actualización/iter [s] | ms/minibatch | carga % |
|---|---|---|---|---|---|
| gpu | 1175.6 | 2.27 (0.49) | 9.88 (3.30) | 19.00 (6.35) | 46.0 |
| gpu_rep2 | 307.4 | 0.47 (0.39) | 3.13 (2.67) | 6.02 (5.14) | 21.9 |
| cpu_control | 257.2 | 0.85 (0.75) | 2.21 (2.05) | 4.24 (3.94) | 81.9 |
| cpu_control_rep2 | 515.6 | 1.25 (0.73) | 2.95 (1.47) | 5.68 (2.82) | 74.9 |
| referencia | 283.6 | 0.94 (0.84) | 2.33 (2.06) | 4.48 (3.97) | 80.3 |

Los totales crudos arrastran valores atípicos (en `cpu_control_rep2` una
iteración tardó 105 s de entorno contra una mediana de 1.25 s; en `gpu` la
actualización osciló entre 3.3 y 49.8 s). **Las medianas y los mínimos por
iteración son estables entre corridas y son la base del contraste.**

**Resultado 1 — la GPU es más lenta, en todos los cortes.** Agrupando las
corridas por condición (medianas por iteración): GPU 0.54 + 0.31 + 3.60 =
4.46 s/iteración contra 0.97 + 0.16 + 2.41 = 3.53 s en el control; **0.79×**.
Con los mínimos (aproximación al costo sin contención): **0.70×**. Con los
totales crudos de la corrida 1: **0.22×**. La actualización cuesta 6.0 ms por
minibatch de 64 en CUDA en la mejor corrida (5.1 mínimo) contra 4.2 en CPU
(2.8 mínimo). Un microbenchmark aislado lo explica: en CUDA el minibatch de 64
y el de 2560 cuestan lo mismo (~10 ms), o sea que el costo es de LANZAMIENTO de
núcleos y sincronizaciones (`.item()` de SB3), no de cómputo; el MLP de 145 157
parámetros no llena la GPU. SB3 mismo advierte al construir el modelo que PPO
con `MlpPolicy` en GPU "podría tardar más que en CPU".

**Resultado 2 — el reparto 83/17 del Exp J no es el reparto de la corrida
real.** Medido dentro del entrenamiento, el control reparte **26.5 % entorno /
73.5 % red** (mediana agrupada: f_red = 0.727). La razón es metodológica: el
perfilador del Exp J midió el entorno EN SERIE, en un proceso, con acciones
aleatorias; en el entrenamiento los cuatro trabajadores simulan EN PARALELO y
el proceso principal sólo espera. Con la f medida, el techo de Amdahl no es
1.20× sino **3.66×**. La conclusión de no usar GPU se sostiene, pero **por la
razón opuesta**: no porque la fracción acelerable sea pequeña, sino porque la
GPU DESACELERA esa fracción (s_red = 0.656× en medianas, 0.546× en mínimos).

**Contraste explícito con Amdahl** (f y s_red medidos, control contra GPU):

| Base | f_red | techo 1/(1−f) | s_red | s_entorno | S_pred = 1/((1−f)+f/s_red) | S_obs |
|---|---|---|---|---|---|---|
| totales crudos, corrida 1 | 0.735 | 3.78× | 0.191× | 0.368× | 0.243× | 0.219× |
| medianas por iteración, 2+2 corridas | 0.727 | 3.66× | 0.656× | 1.784× | 0.724× | 0.793× |
| mínimos por iteración | 0.684 | 3.16× | 0.546× | 1.852× | 0.638× | 0.703× |

La predicción y la observación coinciden dentro del 10 % en las dos bases
robustas; la diferencia es exactamente s_entorno ≠ 1. **Hallazgo colateral,
declarado como hipótesis:** el entorno es MÁS RÁPIDO en la condición GPU
(0.54 contra 0.97 s/iteración) porque el proceso principal deja de ocupar 7
núcleos con los 8 hilos de torch y los 4 trabajadores dejan de competir con
ellos en 8 núcleos físicos. Sugiere que el entrenamiento en CPU está
sobresuscrito y que bajar los hilos de torch podría acelerarlo; NO se midió
(`regimen1_entrenamiento.py --hilos_torch` queda disponible para hacerlo).

**Efecto de la versión de torch, aislado:** referencia (2.10) contra control
(2.11), ambas CPU, medianas: 0.967× total, 0.965× en la red. Despreciable.

**Verificación de equivalencia — resultado más fuerte de lo pedido.** No se
esperaba reproducibilidad bit a bit y sin embargo:

| Corrida | cobertura (100 eps) | colisiones <0.15 m | máx |Δpeso| vs `modelo_PRIMERO` |
|---|---|---|---|
| cpu_control, cpu_control_rep2 | 0.68129082 ± 0.02009684 | 0.210 | **0.0** |
| referencia | 0.68129082 ± 0.02009684 | 0.210 | **0.0** |
| gpu, gpu_rep2 | 0.67556251 ± 0.02155467 | 1.070 | 0.78 |

**Entrenar en CPU con semilla 42 reproduce `modelo_PRIMERO` peso a peso, en las
dos versiones de torch y en dos corridas independientes.** El entrenamiento es
determinista y la cadena de este experimento es la misma que produjo el modelo
de referencia. En GPU la aritmética diverge y el modelo es otro: −0.0057 de
cobertura (dentro de la banda entre semillas [0.532, 0.698] del Trial 13) pero
**5× las colisiones** (1.070 contra 0.210) — la misma lección del Exp J: la
cobertura sola no basta para juzgar un modelo. El modelo GPU también es
determinista entre sus dos corridas.

### Régimen 2 — inferencia (`modelo_PRIMERO`, protocolo del Exp E, n ∈ {5, 10, 20, 50, 100})

Cronómetro `perf_counter` alrededor de la llamada de decisión completa (apilar
n observaciones, `predict` determinista, desempaquetar), como en el Exp E,
dentro de episodios reales del entorno del protocolo (reflexión, sin domain
randomization, modelo cargado con `device` explícito). n = 5: 100 episodios ×
500 pasos (réplica exacta del Exp E, que además sirve de control); n = 10: 20 ×
500; n = 20: 10 × 500; n = 50: 4 × 200; n = 100: 2 × 100. **Para n ≥ 50 el
entorno tarda de 0.4 a 1.2 s por paso y el sorteo de poses cae a la grilla**:
los episodios se truncan, la latencia por decisión sigue siendo válida (depende
del lote `(n, 24)`, no del estado) y la cobertura de esas filas NO es del
protocolo y va marcada. Dos corridas por condición; se agrupan las decisiones.

**Validación de control (n = 5, 100 episodios completos):** `cpu_control` y
`referencia` reproducen **0.68129082** (|Δ| = 1.8e-7, a seis decimales) en las
cuatro corridas. **`gpu` da 0.68165370 (Δ = +3.6e-4) en las dos corridas**: la
aritmética de la GPU cambia algunas decisiones. Es inocuo en cobertura, pero
significa que una política evaluada en GPU NO es bit a bit la evaluada en CPU.

**ms por decisión, mediana agrupada [media]:**

| n | gpu | cpu_control | referencia | gpu / control |
|---|---|---|---|---|
| 5 | 0.9486 [1.0394] | 0.3916 [0.4259] | 0.4959 [0.5732] | 2.42× |
| 10 | 0.9665 [1.0188] | 0.4788 [0.4970] | 0.6274 [0.7259] | 2.02× |
| 20 | 1.1244 [1.2149] | 0.6056 [0.6655] | 0.7086 [0.7089] | 1.86× |
| 50 | 1.2758 [1.3819] | 0.9257 [0.9102] | 0.8951 [0.8897] | 1.38× |
| 100 | 1.3618 [1.4810] | 1.1470 [1.1112] | 1.1122 [1.1368] | 1.19× |

**Punto de cruce: AUSENTE en el rango protocolar.** La GPU es más lenta en los
cinco cardinales, con ventaja decreciente (2.42× → 1.19×). En el barrido
sintético complementario (lotes `(n, 24)` aleatorios, fuera del protocolo) la
GPU es prácticamente plana —0.51 a 0.97 ms de n = 5 a n = 5000— mientras la CPU
crece con n; **el cruce aparece en n = 200** (0.89×) y a n = 5000 la GPU es 7×
más rápida (0.97 contra 6.9 ms). Es decir, la GPU conviene para enjambres del
orden de 200 agentes o más, cuarenta veces el de la tesis y veinte veces el
máximo evaluado en el Exp I.

**Variabilidad entre corridas, declarada.** A n = 5 la media por corrida fue
0.785 y 0.361 ms en la referencia, 0.468 y 0.384 en el control, 1.053 y 1.025
en GPU; el sintético a n = 5 va de 0.16 a 0.35 ms en CPU. La corrida lenta de
la referencia fue lenta hasta en el entorno (NumPy puro, idéntico), así que es
ruido de máquina, no versión de torch. El **0.757 ms del Exp E cae dentro de lo
observado en CPU** (0.36–0.79 ms de media por corrida).

### Qué afirmación del documento toca este experimento

**RESPALDA** la afirmación de viabilidad del despliegue: la decisión de la
política cuesta entre 0.36 y 0.79 ms en CPU según la corrida (0.757 publicado),
de 8 a 22 veces menos que los 8.04 ms de Voronoi+PSO; en GPU costaría ~1.0 ms y
seguiría 8× por debajo. Para cinco robots la GPU no aporta nada en inferencia.

**RESPALDA** la decisión de entrenar en CPU, pero **MATIZA su justificación**:
el argumento del Exp J (reparto 83/17, techo 1.20×) describe mal la corrida
real, que es 27/73 con techo 3.7×. La GPU no se usa porque desacelera la red
(minibatch de 64 y MLP de 145 k parámetros: costo de lanzamiento, no de
cómputo), no porque la red sea una fracción pequeña. La frase del documento
debe cambiar de razón.

**MATIZA** el cuadro de antecedentes "O(1) de la inferencia neuronal frente a
O(n log n) de Voronoi": el costo O(1) en n es de la GPU (plana hasta n = 5000);
en CPU la inferencia crece con n (0.42 → 6.9 ms de n = 100 a n = 5000). A la
escala de la tesis el crecimiento es irrelevante, pero la afirmación asintótica
no es propiedad de la red, es del dispositivo.

**Hallazgo colateral con valor propio:** el entrenamiento con semilla fija es
**determinista bit a bit en CPU** entre versiones de torch y entre corridas, y
reproduce `modelo_PRIMERO` exactamente. Eso convierte la "verificación de
control" del Exp J (0.68359 sobre 20 eps) en identidad, no en cercanía.

**Artefactos:** `fase_preliminar2/experimento_L/` — `train_L.py` (copia con
`dispositivo`), `comun_L.py`, `regimen1_entrenamiento.py`,
`regimen2_inferencia.py`, `analizar_L.py`; `resultados/mediciones_L.csv`
(formato largo, cada cifra con definición, conjunto y n),
`resultados/tabla_comparativa.md`, `resultados/fig_cpu_gpu_inferencia.png`,
`resultados/analisis_L.json`, `resultados/regimen1/<corrida>/`
(`reporte.json`, `tiempos_por_iteracion.csv`, `protocolo_episodios.csv`,
`modelo_final.zip`), `resultados/regimen2/<corrida>/` (`reporte.json`,
`protocolo_episodios.csv`, `sintetico.csv`, `tiempos_decision_n*.npy`),
logs `r1_*.log`, `r2_*.log`, `pip_freeze_venv_lab4_2026-09-09.txt`. Ningún
original modificado; `regimen2/referencia_INCOMPLETO_interrumpido_20260909`
es una corrida abortada a mano y no se usa.

**Costo:** ~2.5 h de máquina en total (entrenamientos de 4 a 20 min según
carga; barridos de inferencia de 5 a 12 min por condición).

---

## Exp M — Punto de cruce del entrenamiento: minilote y ancho de red (banco de tiempos, 3 condiciones)

**Pregunta:** el Exp L ubicó el cruce CPU/GPU de la INFERENCIA en n ≈ 200
agentes y midió que en ENTRENAMIENTO la GPU es más lenta con la configuración
actual, pero no dijo dónde estaría el cruce del entrenamiento. Este experimento
lo acota. **Encuadre:** caracterización complementaria que sustenta una
recomendación de trabajo futuro, no un resultado central; costó ~30 min de
máquina.

**Hardware declarado:** el mismo del Exp L — CPU Intel Core i5-13420H (8
núcleos físicos, 12 lógicos, 2100 MHz nominales), 16 GiB RAM, Windows 11 26200;
GPU NVIDIA GeForce RTX 4050 Laptop, 6141 MiB, 20 multiprocesadores, capacidad
8.9, **driver 592.82 (el mismo del Exp L; no se actualizó, a propósito)**, CUDA
runtime 12.8, cuDNN 9.19. Equipo HP Victus, Omen Gaming Hub en modo
**Standard** (el de mayor rendimiento que ofrece el modelo; no tiene modo
"Performance"), Windows en "Mejor rendimiento" con CA, límite de potencia
impuesto a la GPU **50 W**. Torch con 8 hilos en el proceso en las tres
condiciones (`OMP_NUM_THREADS=12` está definido en el entorno y no altera ese
número).

**Aislamiento: la máquina SÍ estaba en reposo y con CA**, a diferencia del
Exp L. Antes de lanzar: `BatteryStatus=2` (CA), ocupación de CPU 8.2 % de media
en 20 s (mín 4.0, máx 13.2), aplicaciones del autor cerradas; quedaron
servicios de fondo (licencias de Autodesk, servicio de MATLAB, PowerToys). La
ocupación del sistema se muestreó cada 2 s durante cada corrida con el monitor
del Exp L: 17–21 % en las corridas de GPU y 53–73 % en las de CPU, que es el
propio proceso (8 hilos de 12 ≈ 67 %), no carga ajena. Todas las corridas
registraron `BatteryStatus=2`. **Un piloto previo corrió a batería por error
(plan "Mejor eficiencia energética") y dio `train()/520` 5.6× más lento en CPU
(23.8 contra 4.24 ms del Exp L): se descartó** (`resultados/piloto_descartado/`,
con `LEEME.txt`). Es la evidencia medida de que la alimentación mueve estas
cifras más que cualquier diferencia entre condiciones.

**Condiciones:** las tres del Exp L, con la misma validación del intérprete en
tiempo de ejecución: `gpu` = venv_lab4, torch 2.11.0+cu128, cuda;
`cpu_control` = mismo intérprete, cpu — **el control que aísla el
dispositivo**; `referencia` = intérprete de la tesis, torch 2.10.0+cpu. Ningún
original ni archivo del Exp L modificado: `comun_L` y `train_L` se importan en
sólo lectura.

### Diseño — banco de tiempos, no corridas de entrenamiento

**Problema del diseño pedido, resuelto antes de medir.** El búfer de la
configuración de la tesis tiene 2560 transiciones (128 × 4 entornos × 5
agentes): los minilotes 4096 y 8192 del barrido no existen en ella. Además SB3
recorre el búfer con un último minilote truncado cuando B no lo divide, lo que
sesga cualquier "tiempo por minilote" derivado de `train()`. Se pobló **una
vez** un búfer real de 10 240 transiciones (rollout de 512 pasos × 20 flujos
con la política sin entrenar, semilla 42, en CPU; `bufer_poblado_10240.npz`,
compartido por las tres condiciones) y se cronometró **un paso de gradiente
aislado** sobre minilotes de tamaño B tomados de él.

**Qué es un paso:** la réplica exacta del cuerpo del bucle de `PPO.train()` del
SB3 2.7.1 instalado — indexado NumPy del minilote y conversión
`th.tensor(..., device)` de los seis arreglos (como
`RolloutBuffer._get_samples`), `evaluate_actions`, normalización de la ventaja,
pérdida recortada, pérdida de valor, entropía, los cuatro `.item()` y el
`.cpu().numpy()` de SB3 (cinco sincronizaciones), `zero_grad`, `backward`,
`clip_grad_norm_` y `optimizer.step`. Hiperparámetros del Trial 13. Con CUDA,
`synchronize()` antes de detener el reloj.

**Repeticiones:** por celda (condición × arquitectura × B × modo), **50 pasos
de calentamiento descartados** y luego 200 medidos (B ≤ 1024) o 60 (B > 1024);
orden de celdas barajado con semilla por corrida. Dos corridas completas por
condición, intercaladas gpu → cpu_control → referencia → (rep2). El
calentamiento remanente es nulo: la mediana de los 10 primeros pasos
descartados sobre la mediana medida da 1.00–1.01 en las tres condiciones.

**Barridos:** B ∈ {64, 128, 256, 512, 1024, 2048, 4096, 8192} y tres anchos de
red: `[256, 256]` (145 157 parámetros, **la de la tesis**), `[512, 512]`
(552 453) y `[1024, 1024]` (2 153 477), separados para actor y crítico como en
`train.py`. **Se ensanchó y no se profundizó** porque el costo aritmético lo
domina el producto oculta→oculta, que crece como h²: 256→512→1024 da 4× y 16×
la aritmética por muestra con la profundidad fija. Agregar capas aumentaría el
número de lanzamientos de núcleo, que es justamente la variable que se quiere
aislar. Este eje no toca nada de la tesis, que usa `[256, 256]`.

**Refinamiento:** localizado el par que encierra cada cruce, se midieron tres
puntos intermedios, cuartiles geométricos redondeados a múltiplos de 8 (608,
720 y 864 para `[256,256]`; 152, 184 y 216 para `[512,512]`), con dos corridas
más por condición y control de banco.

### Verificación de control del banco — condición de parada

En cada corrida, antes del barrido, se corre `PPO.train()` REAL de SB3 sobre la
configuración de la tesis (2560 transiciones, B = 64, 13 × 40 minilotes; 10
llamadas tras 2 descartadas) y se compara `train()/520` con la mediana del
banco a B = 64 en el mismo proceso. Tolerancia declarada de antemano: 20 %. Si
falla, la corrida aborta y el análisis se niega a correr.

| Condición | `train()/520` [ms], 4 corridas | banco B=64 [ms] | desvío | Exp L (ms/minibatch) |
|---|---|---|---|---|
| gpu | 5.94 – 6.32 | 5.98 – 6.60 | 0.6 – 9.5 % | 6.02 (mediana, mejor corrida) |
| cpu_control | 2.63 – 3.03 | 2.62 – 2.80 | 0.7 – 11.7 % | 4.24 mediana; 2.82–3.94 mínimos |
| referencia | 2.70 – 2.81 | 2.43 – 2.84 | 1.4 – 12.9 % | — |

**Las 12 corridas aprobaron.** El banco mide lo mismo que `train()`. La GPU
reproduce el 6.02 ms del Exp L; la CPU cae en la franja de los MÍNIMOS del
Exp L y no en su mediana, lo esperable al pasar de máquina cargada a máquina en
reposo, y es la confirmación directa de que en el Exp L la carga ajena
castigaba a la CPU.

### Resultado 1 — el cruce, por arquitectura

t = mediana del tiempo de pared de un paso de gradiente, calentamiento
excluido, rep1 y rep2 agrupadas (más el refinamiento en sus puntos): 400 pasos
por celda para B ≤ 1024 y 120 para B > 1024. r = t_gpu / t_cpu_control, en modo
SB3 real (datos desde memoria del sistema). B* por interpolación lineal de
log r contra log B entre los dos B medidos que lo encierran. **n* = B*/12.8**
(supuesto más abajo).

| Arquitectura | Parámetros | r a B=64 (n=5) | B* agrupado | n* | Banda entre repeticiones (B*; n*) | Estado |
|---|---|---|---|---|---|---|
| `[256, 256]` (tesis) | 145 157 | 2.13 | **704** | **55** | 675–832; 53–65 | cruce único |
| `[512, 512]` | 552 453 | 1.23 | **133** | **10** | 132–194; 10–15 | franja de empate (ver abajo) |
| `[1024, 1024]` | 2 153 477 | 0.45 | — | — | — | **ausente: la GPU gana en todo el rango (cruce < 64)** |

**Lectura.** Con la red de la tesis, la GPU es 2.13× más lenta por paso a la
escala de la tesis y empata hacia B ≈ 700; por encima gana rápido (r = 0.48 a
B = 2048, 0.15 a 8192). **El cruce se mueve con la capacidad del modelo, y
mucho:** cuadruplicar la aritmética por muestra (`[512,512]`) lo baja de n ≈ 55
a n ≈ 10, y multiplicarla por 16 (`[1024,1024]`) lo saca del rango. Con esa red
la GPU ya sería 2.2× más rápida con los cinco robots de la tesis.

**`[512,512]` no tiene un punto de cruce sino una franja de empate:** r = 1.02,
0.92, 1.00 y 0.90 en B = 128, 152, 184 y 216. Dentro de ella cada repetición
ubica el cruce según su ruido (132 y 194). Lo honesto es reportar "empate en
B ∈ [128, 216], n ∈ [10, 17]", no un B* de tres cifras. El de `[256,256]` sí es
un cruce neto (r = 1.12 a 608, 0.98 a 720 y 864, 0.78 a 1024), con una banda
entre repeticiones estrecha (n 53–65).

**Versión de torch, otra vez despreciable:** `referencia` y `cpu_control`
coinciden en todas las celdas (en la figura, la curva aqua cae sobre la
naranja). El cruce GPU contra referencia da n* = 53 y 14, dentro de las bandas.

### Resultado 2 — descomposición mecanística: ni transferencia ni cómputo, sino costo fijo

Sólo para la GPU. **En CPU los datos ya están en memoria del sistema y la
descomposición no aplica**: no hay columna residente para CPU. `desde_sistema`
= SB3 real, copia anfitrión→dispositivo de los seis arreglos por minilote;
`residente` = los mismos arreglos precargados en la GPU, sólo se indexan.
Transferencia = diferencia entre ambos. Medianas agrupadas, en ms por paso.

| Arq. | B (n) | t desde sistema | t residente | transferencia | % | t CPU control |
|---|---|---|---|---|---|---|
| `[256,256]` | 64 (5) | 5.861 | 5.761 | 0.100 | 1.7 % | 2.751 |
| `[256,256]` | 2048 (160) | 6.375 | 5.981 | 0.394 | 6.2 % | 13.369 |
| `[256,256]` | 8192 (640) | 7.346 | 6.170 | 1.176 | 16.0 % | 48.989 |
| `[512,512]` | 64 (5) | 6.270 | 6.378 | −0.109 | −1.7 % | 5.080 |
| `[512,512]` | 2048 (160) | 6.913 | 6.658 | 0.255 | 3.7 % | 34.214 |
| `[1024,1024]` | 64 (5) | 6.470 | 6.512 | −0.042 | −0.7 % | 14.393 |
| `[1024,1024]` | 2048 (160) | 10.238 | 9.946 | 0.292 | 2.9 % | 125.156 |

(Las 36 celdas completas están en `tabla_M.md`.) Las diferencias negativas
llegan a −0.72 ms, y ese es el ruido de la resta. **Hasta B = 2048 la
transferencia es indistinguible de cero en las tres redes**; sólo con la red
chica y B ≥ 4096 asoma ~1.1 ms (16 %), cuando el cómputo es tan barato que
cualquier cosa se nota.

**Lo que domina es un piso FIJO de ~6 ms por paso, plano en B:** con
`[256,256]` y datos residentes, 5.7–6.3 ms de B = 64 a B = 8192, un factor 128
de trabajo sin cambio de costo. Es el costo de lanzar la cadena de núcleos del
paso y las cinco sincronizaciones de SB3. El cómputo real sólo asoma por
encima de ese piso con `[512,512]` a B = 8192 (11.8 ms) y con `[1024,1024]`
desde B ≈ 1024. **Esto pasa a medido lo que el Exp L conjeturó** ("costo de
lanzamiento, no de cómputo") y descarta la tercera explicación posible, la
transferencia por el bus, que el Exp L no había separado. Consecuencia
práctica: mover el búfer a la GPU no movería el cruce de la red de la tesis
(con datos residentes da n* = 58, dentro de la banda); lo que lo movería es
reducir las sincronizaciones por paso o aumentar el trabajo por lanzamiento.

### Traducción a escala de enjambre y su supuesto

Con n agentes, horizonte `n_steps` = 128 y 4 entornos, el búfer por iteración
es 128 × 4 × n = 512 n transiciones. **Supuesto de la conversión: se mantienen
los 40 pasos de gradiente por época de la configuración actual**, de modo que
B = 512 n / 40 = **12.8 n**, y B = 64 ↔ n = 5 es exactamente la tesis. Con el
supuesto alternativo —B fijo en 64 y más minilotes por época— el trabajo por
lanzamiento no crece con n y **la GPU no ganaría nunca con `[256,256]`**: el
cruce existe sólo si el minilote escala con el enjambre.

### Hipótesis previa, verificada

Enunciada antes de medir: el cruce del entrenamiento caería en un cardinal
menor que el de la inferencia, porque el paso de gradiente hace más trabajo
por muestra y amortiza mejor el lanzamiento. **Se confirma para la red de la
tesis: n* ≈ 55 (banda 53–65) contra n ≈ 200 del Exp L.** La GPU convendría
antes para entrenar que para ejecutar. Dos confusiones declaradas y no
resueltas: (1) los dos cardinales salen de conversiones distintas (en
inferencia, n son las filas de un lote; acá es un n equivalente bajo el
supuesto de arriba); (2) el cruce de inferencia del Exp L se midió con la
máquina cargada y el de este experimento, en reposo. Sobre (2), como
hipótesis: la carga castigaba sobre todo a la CPU (el control lo muestra), lo
que adelantaba el cruce de inferencia; en reposo quedaría en n ≥ 200, y la
separación entre ambos cruces sólo crecería.

### Caveat que acota la recomendación: cruce por paso ≠ cruce de la corrida

El cruce es del **paso de actualización**, no del tiempo de pared del
entrenamiento. En el Exp L la actualización fue ~69 % de la corrida a n = 5,
pero el entorno escala con n y ya a n ≥ 50 tarda de 0.4 a 1.2 s por paso
(Exp L, régimen 2). **A n ≈ 55 el entorno probablemente dominaría la
corrida**, y el reparto de Amdahl del Exp L se invertiría: acelerar la red
rendiría poco en tiempo total. Esto no se midió aquí —el experimento es de
costo por operación, como se pidió— y queda declarado como la condición bajo
la cual vale la recomendación.

**Límite de potencia:** la hipótesis previa era que la GPU no llegaría al tope
de 50 W porque la carga está limitada por el lanzamiento. Al terminar cada
corrida de GPU, `nvidia-smi` marcó P0 y 11–15 W. Es una instantánea final, no
un muestreo continuo: es consistente con la hipótesis, no la prueba. **Los
cruces son de esta máquina con este límite**, igual que los del Exp L.

### Qué afirmación del documento toca este experimento

**RESPALDA y CUANTIFICA** la recomendación de trabajo futuro. Con la
arquitectura de la tesis, el paso de entrenamiento en GPU conviene a partir de
un enjambre de ~55 agentes (minilote ~700, banda 53–65), once veces el de la
tesis y antes que la inferencia (~200); ese umbral baja a ~10 agentes si la red
se ensancha a `[512,512]` y desaparece con `[1024,1024]`. Frase que sustenta:
*"La aceleración por GPU del entrenamiento no se justifica a la escala de la
tesis; se volvería ventajosa para enjambres del orden de 50 agentes con la red
actual, o para redes más anchas a cualquier escala, siempre que el costo del
entorno no domine la corrida."*

**MATIZA** la justificación del Exp L: a la escala de la tesis, el costo de la
GPU no es de transferencia (≤ 2 % a B = 64) ni de cómputo, sino un piso fijo de
~6 ms por paso, de lanzamiento y sincronización.

**Artefactos:** `fase_preliminar2/experimento_M/` — `banco_M.py` (poblado del
búfer, control de banco, barrido), `analizar_M.py` (cruces, bandas por
repetición, descomposición, figura, tablas), `cadena_M.sh`,
`cadena_M_refino.sh`; `resultados/mediciones_M.csv` (formato largo: una fila
por celda y corrida, más las agrupadas, con definición y n de pasos),
`resultados/tabla_M.md`, `resultados/fig_cruce_entrenamiento.png`,
`resultados/analisis_M.json` (incluye hardware y carga por corrida),
`resultados/bufer_poblado_10240.npz` + `bufer_poblado_meta.json`,
`resultados/corridas/<condicion>_<rep|refino_rep>/` (`pasos.csv` con cada paso
medido y descartado, `reporte.json`), `resultados/logs/`,
`resultados/piloto_descartado/` (no se usa). Ningún original modificado.

**Costo:** ~30 min de máquina (barrido principal de 14:07 a 14:26 y
refinamiento de 14:27 a 14:35, el 11/sep/2026), más ~10 min del piloto
descartado.

---

## Exp N — Costo de reducir la arena a 2,7 × 2,7 m (Python, 2 config × 4 celdas × 100)

**Pregunta:** el asesor recomendó reducir el área a 2,7 × 2,7 m porque el
centro del volumen de captura del Robotat resuelve mejor. La observación
normaliza la posición por la arena, así que la política vería un mundo
comprimido. ¿Cuánto cuesta el cambio, antes de comprometer una sesión de
laboratorio?

**Alcance declarado:** este experimento mide el **COSTO** de reducir la arena.
El **BENEFICIO** —mejor seguimiento en el centro del volumen— **no lo
cuantificó nadie**. La decisión necesita ambos lados. **Medición pendiente de
laboratorio:** jitter de pose con un robot quieto en varias posiciones del
volumen, esquinas incluidas.

### Verificación previa por lectura (antes de codear)

- **La arena es un parámetro** en el env, el `DynamicTargetSimulator` y
  `FiltroCBFParedes`; los objetivos nacen en `[0,10·W, 0,90·W]` y rebotan en
  `arena_size`. **Excepción encontrada:** el escape portado a Python
  (`verificar_escape_python.py:67`) tenía `ARENA = (3.0, 3.0)` como global de
  módulo; la copia del Exp N lo parametriza.
- **Constantes absolutas que NO escalan** (parte del corrimiento de
  distribución): rapidez de objetivos 0,05–0,15 m/s, σ 0,10–0,25 m,
  `comm_radius` 1,0 m, huella del sensor 0,15 m, edad máxima AoI 60 s.
- **Cuadrícula AoI de resolución fija 64×64:** celda 0,046875 → 0,0421875 m.
  Error de discretización de la huella −0,11 % (3,0) y +0,001 % (2,7):
  despreciable.
- **Sorteo de poses:** los agentes arrancan en el **70 % central** (margen
  `0,15·W`), no en el 80 % (ese es el de los objetivos). Escala. Sorteo de
  respaldo: 0/818 episodios.

### La cobertura cruda no compara entre arenas

Con huella, rapidez y edad AoI absolutas, en una arena menor la cobertura
**sube de forma mecánica** aunque la política empeore. Lo que decide es el
**residuo sobre la predicción por densidad**: 5 agentes en 7,29 m² tienen el
mismo cociente área barrida / área que **n_eq = 5·9/7,29 = 6,172840** agentes en
9 m² (6,364234 con el área libre del punto de mira). Por eso se agregó un
**brazo de densidad** (n = 6 y 7 a W = 3,0) en ambas configuraciones, y la
predicción se construye **por semilla** interpolando entre esas celdas.

**Trampa de normalización evitada:** colisiones (pares únicos) y escapes
(suma sobre agentes) crecen con n y no sólo con la densidad; se interpolan
**por par** y **por agente**. Sin normalizar, la política aislada daba un
residuo espurio de −0,24 colisiones por episodio.

| Geometría | W = 3,0 | W = 2,7 |
|---|---|---|
| Área libre del punto de mira (W − 0,36)² | 6,969600 m² (77,44 %) | 5,475600 m² (75,11 %) |
| Densidad nominal | 0,55555556 /m² | 0,68587106 /m² (+23,46 %) |
| Densidad efectiva | 0,71740129 /m² | 0,91314194 /m² (+27,28 %) |
| Perímetro / área | 1,333 m⁻¹ | 1,481 m⁻¹ (+11,1 %) |

### Diseño

(a) política aislada: `modelo_PRIMERO`, reflexión, sin filtro ni escape.
(b) configuración final: `modelo_sanidad`, bloqueante, CBF + escape con
detección de **tres** términos (como el coordinador desplegado). Celdas
{W=3,0 n=5; W=2,7 n=5; W=3,0 n=6; W=3,0 n=7} × 100 semillas del protocolo,
pareado por semilla, más un puente de 18 semillas con detección de dos términos.

### Validación de control

| Control | Resultado |
|---|---|
| (a) W=3,0 n=5 vs oficial 0,681291 | 0,6812908188, \|Δ\| = 1,8·10⁻⁷ |
| (a) n=5 y n=7 por semilla vs Exp I | 100/100 y 100/100 idénticas a 6 dec. |
| (b) dos términos, 18 semillas, vs factorial (d) | 0,5779647222, 18/18 idénticas |

### Resultado 1 — política aislada: la densidad lo explica todo

Residuo de cobertura **−0,00071411, IC95 [−0,00567, +0,00425]** (n.s.;
Lagrange −0,00168). Colisiones por par, n.s. en ambos umbrales. La compresión
de la observación **no** degrada la cobertura de la política aislada más allá
de lo que predice la densidad. Único residuo: más tiempo en la banda de
0,18 m (+0,0258, IC95 [+0,0186, +0,0330]), coherente con +11 % de perímetro por
área.

### Resultado 2 — configuración final: costo significativo más allá de la densidad

| Métrica (b), W=2,7, n=5 | Observado | Predicho | Residuo, IC95 |
|---|---|---|---|
| **Cobertura AoI** | 0,59909133 | 0,61953486 | **−0,02044353 [−0,03584, −0,00504]** |
| Intervención del filtro | 0,54105200 | 0,49497885 | +0,04607315 [+0,02895, +0,06320] |
| … atribuida a pared (h mín.) | 0,51884800 | 0,45463634 | **+0,06421166** [+0,04563, +0,08279] |
| … atribuida a robot (h mín.) | 0,02220400 | 0,04034251 | −0,01813851 [−0,02872, −0,00756] |
| Escapes por agente | 2,84 | 2,23 | +0,605 [+0,469, +0,741] |
| Violación de margen por agente | 0,766 | 0,712 | +0,054 [+0,024, +0,083] |

El residuo de cobertura es −3,3 % sobre lo predicho, robusto a las tres
interpolaciones (lineal −0,0204, Lagrange −0,0214, densidad efectiva −0,0263,
todas con IC95 que excluye 0). **El filtro cruza el umbral operativo:** 0,541
de intervención media, **72/100 episodios sobre 0,5** (13/100 a W=3,0). Seguridad
intacta: 0 colisiones en ambos umbrales, 0 contacto con pared, 0 fallbacks del
QP, d_min centro→pared global 0,14004731 m (0,13171086 a 3,0).

Comparación cruda pareada 2,7 − 3,0 (n=5), sólo como referencia y **no** como
medida de desempeño: (a) +0,04996025 [+0,04473, +0,05519]; (b) +0,02904290
[+0,01404, +0,04404].

**Atribución — HIPÓTESIS, no verificada:** el residuo agrupa tres canales que
este diseño no separa (compresión de la observación, más perímetro por área
con márgenes absolutos, objetivos relativamente mayores). La evidencia apunta
al **canal de pared**: el exceso de intervención es todo de pared mientras la
de robot baja, su magnitud relativa (+14 %) es del orden del aumento de
perímetro por área (+11 %), y la política aislada —sin márgenes que consumir—
no muestra residuo de cobertura. Salvedad: (a) y (b) son modelos distintos, así
que el nulo de (a) no descarta el canal de observación para `modelo_sanidad`.
La sonda "2,7 normalizada por 3,0" se descartó por diseño: sustituye un
corrimiento por otro (rango [0; 0,9], nunca el borde) y sería ambigua.

### Resultado 3 — brazo de densidad: primera medición de las tres capas a otro cardinal

| n (W=3,0) | Cobertura | Cob./agente | col015 | col022 | Frac. filtro | Episodios > 0,5 | Escapes/ep |
|---|---|---|---|---|---|---|---|
| 5 | 0,57004842 | 0,11400968 | 0 | 0 | 0,396564 | 13/100 | 9,00 |
| 6 | 0,61420834 | 0,10236806 | 0 | 0 | 0,487607 | 46/100 | 13,21 |
| 7 | 0,64502608 | 0,09214658 | 0 | 0 | 0,530260 | 69/100 | 16,76 |

Llena un hueco del Exp I, que midió sólo la política aislada: **con las tres
capas la seguridad sí se sostiene al aumentar n** (0 colisiones hasta n=7,
contra 0,72 de la política sola), pero **el conflicto política-filtro cruza el
umbral operativo en n = 7**. Cero fallbacks del QP en todas las celdas.

### Puente — escape desplegado (tres términos) vs factorial (dos)

Idénticos **bit a bit en 18/18 semillas** en todas las métricas. Verificado que
no es un defecto (`verificar_veto_tercer_termino.py`): el tercer término vetó
**2 de 5564** detecciones de dos términos a W=3,0 y **8 de 8788** a W=2,7; con
el instrumento la cobertura coincide 100/100 con el CSV principal. En Python,
estar quieto con h_min < 0,03 implica que el filtro intervino. **El +0,13534334
[+0,09297, +0,17772] del factorial describe también al escape desplegado** y es
citable como tal (en simulación; en hardware el ruido podría hacer relevante
el tercer término).

### Recomendación: mantener 3,0 × 3,0

1. **El costo está medido y es significativo** en la configuración que se
   despliega: −0,0204 de cobertura más allá de la densidad.
2. **Indicador adelantado, FUERA de su dominio de calibración — no es una
   predicción verificada.** A 2,7 la intervención es 0,541 (72/100 episodios
   sobre 0,5). El umbral de 0,5 se calibró en **Webots con física de contacto**
   (r = +0,905 contra atascamiento, n = 18); en Python la intervención alta
   **no** produce atascos (0 escapes agotados, 0 fallbacks del QP a 2,7). Esta
   pata tiene menos fuerza que la 1: **el residuo de −0,0204 es medición dentro
   de dominio y sostiene la decisión por sí solo**; el cruce del umbral sólo
   advierte qué conviene mirar si se llevara 2,7 al hardware.
3. **El beneficio no está cuantificado.** Si la medición de jitter mostrara una
   mejora grande en el centro, la decisión se revisa contra estos números.

**Si aun así se adopta 2,7**, la lista de cambios incluye los tres 3,0 fijos
del cliente físico: `protocolo.py:195` (`ARENA_WX/WY` y el offset),
`config_robotat.py:418` (`ARENA_WX_M/WY_M`) y `coordinador_enjambre.py:104`
(`ARENA_SIZE`), además del sorteo de arranque de `sesion_robotat.py`, que
deriva de `ARENA_WX_M`.

### Precisiones de la revisión (12/sep/2026)

**Límite de escalamiento de la arquitectura de tres capas — caracterización
nueva.** A W = 3,0 con n = 7 la intervención ya es 0,530, con 69/100 episodios
sobre el umbral: la configuración de tres capas tiene un límite de
escalamiento propio alrededor de **n = 6–7 en la arena de 3,0**. El Exp I sólo
había medido la política aislada.
*Acotación:* el límite es de **densidad**, no de cardinal. La
propia equivalencia de abajo lo muestra: la misma intervención aparece con
n = 5 si la arena se achica. Lo medido es que, a W = 3,0, el límite cae entre
0,667 y 0,778 agentes/m² nominales (n = 6 y 7). Que el umbral en densidad sea
el mismo en otra arena es plausible, pero no está verificado: cambia también el
perímetro por área.

**Equivalencia "la reducción cuesta dos agentes".** Para el filtro, operar a
2,7 con n = 5 (0,541; 72/100 sobre 0,5) equivale a operar a 3,0 con n = 7
(0,530; 69/100), aunque la densidad nominal de 2,7 corresponde a n = 6,17. Los
~0,8 agentes de diferencia son el mismo exceso de pared del Resultado 2. La
equivalencia vale para la **intervención**; en cobertura, 2,7 queda por debajo
incluso de n = 6 (0,599 contra 0,614).

### Qué afirmación del documento toca este experimento

**RESPALDA** mantener la arena de entrenamiento en el despliegue y **AMPLÍA** el
Exp I: la capa CBF sostiene cero colisiones al aumentar la densidad, a costa de
un conflicto política-filtro creciente. Frase que sustenta: *"Reducir la arena
de despliegue a 2,7 m cuesta cobertura más allá de lo que explica la mayor
densidad y lleva el conflicto política-filtro sobre el umbral operativo; sin
una medición del beneficio de seguimiento que lo compense, se mantiene la arena
de 3,0 m."*

**Artefactos:** `experimentos/expN_arena/` — `lib/` y `modelos/` (copias
verificadas por sha256 contra los originales), `correr_experimento_N.py`,
`analizar_experimento_N.py`, `verificar_veto_tercer_termino.py`;
`resultados/experimento_N_completo.csv` (818 filas, sin redondeo),
`experimento_N_control.csv`, `control_N.txt`, `resumen_experimento_N.txt`
(el respaldo `_sin_normalizar` es la versión con la predicción mal
normalizada, no citable), `verificacion_veto_tercer_termino.txt`, logs;
`figuras/fig_arena_densidad_cobertura.png`, `fig_arena_residuos.png` (300 dpi,
es-ES, sin título). Ningún original modificado.

**Costo:** ~7 min de máquina el 12/sep/2026 (11 procesos; 3,3–7,1 s por
episodio en paralelo).

---

## Exp O — Obstáculos estáticos como barreras de ejecución (Python, S0 + 3 escenarios pareados, 100 eps)

**Encuadre — leer antes que los números.** Esto **NO** prueba adaptabilidad de
la política: la observación (24 dims: estado propio 5, campo 3, vecindad 8,
mapa AoI 8) no codifica obstáculos; el agente es **ciego** a ellos. Lo que se
prueba es la **generalidad de la capa de seguridad**: que la capa de ejecución
absorbe obstáculos que la política no percibe, y a qué costo en progreso de
tarea.

### Formulación

Obstáculos **circulares** como vecinos fantasma inmóviles, por el mismo camino
de código que la barrera robot-robot con el otro punto fijo:
`h = ‖p − p_obs‖ − (r_obs + 0,18)`, `c = nᵀ·G(θ)`, con **responsabilidad
completa** (h, no h/2). Margen 0,18 por la misma regla que el de pared
(0,075 + 0,05 + 0,031 = 0,156 ≤ 0,18): en el peor caso deja el centro a
r + 0,13. El escape suma también las normales de obstáculo activas.

Implementación por **herencia** (`entorno_obstaculos.py`) sobre copias de
`lib/` byte-idénticas a las del Exp N:

- **El obstáculo existe en el entorno:** disco de contacto r + 0,075 (chasis);
  el centro que entra se proyecta radialmente y θ queda intacto. *Inconsistencia
  deliberada:* la pared de v2 trata al robot como punto; ese tratamiento se
  hereda de la cadena validada y cambiarlo invalidaría la comparabilidad con
  A–N; el del obstáculo es nuevo y no hay razón para replicar una simplificación
  conocida. Va en dirección de mayor realismo.
- **Máscara del AoI:** celdas con centro dentro de r, forzadas a AoI = 0 (no
  atractoras). El anillo r…r+0,13 queda al alcance de la huella de 0,15 m.
  S1: **3,027344 %** de las celdas (124/4096).
- **Objetivos:** rebotan elásticamente en r; los que nacen dentro se reubican.
- **Poses:** la restricción "obstáculos fuera de la región de sorteo" era
  incumplible (la región es el 70 % central; con las poses estándar habría
  conflicto en 70/95/100 de 100 episodios en S1/S2/S3). Se sortea como en el
  protocolo y sólo los agentes a < r + 0,25 se reubican con un RNG aparte
  sembrado por episodio (S1: 1,02 agentes y 0,22 objetivos por episodio). El
  control **Sk_ctrl** usa esas MISMAS poses y objetivos iniciales sin
  obstáculos: pareo exacto.

### Pasabilidad, verificada antes de correr

Umbrales: **0,36 m** entre superficies (geométrico, 0,18 + 0,18) y **0,48 m**
(con escape operable: debajo, en todo el corredor las dos barreras quedan
activas con normales opuestas y el escape es infactible por construcción).

| Escenario | Obstáculos | Hueco mín. obst–pared / obst–obst | Región factible del punto de mira (h≥0 / h≥0,06) |
|---|---|---|---|
| S1 sencillo | 1 central, r=0,30 | 1,20 / — | 6,245 / 5,435 m², conexa |
| S2 medio | (1,1) y (2,2), r=0,25 | 0,75 / 0,91 | 5,808 / 4,842 m², conexa |
| S3 difícil | 4 a (0,75;0,75)… r=0,20 + central r=0,25 | 0,55 / 0,61 | 4,572 / 3,162 m², conexa |

### Validación de control

**S0 (sin obstáculos) reproduce b3_W30_n5 del Exp N bit a bit en 100/100
semillas** (cobertura, intervención, escapes, d_min). La herencia no altera la
dinámica.

### Resultado 1 — S1: la capa absorbe el obstáculo central

**Seguridad: el obstáculo queda absorbido por completo.** 0 contactos con el
obstáculo, 0 colisiones (0,15 y 0,22), 0 contacto con pared, **0 fallbacks del
QP** en 100 episodios. d_min centro→superficie del obstáculo, mínimo global
**0,13716615 m**, sobre la cota de diseño de 0,13 (0 agente-episodios bajo ella).
Ningún escape infactible junto al obstáculo.

**Costo en tarea (pareado S1 − S1_ctrl, 100 semillas):**

| Métrica | Δ | IC95 |
|---|---|---|
| Cobertura sobre celdas accesibles | −0,01213155 (−1,21 %) | [−0,02649, +0,00223] n.s. |
| Cobertura sobre la cuadrícula completa | −0,03327021 | [−0,04733, −0,01921]* |
| Escapes por episodio | +2,12 | [+1,47, +2,77]* |
| … con obstáculo activo al disparar | +0,08 | [+0,003, +0,157]* |

El costo sobre lo accesible no se distingue de cero; la caída en la cuadrícula
completa es casi toda el área perdida (3,03 %).

**Intervención (indicador, NO parada — ver la corrección de abajo).**
0,39461200 → **0,57544400**
(+0,18083200 [+0,15223, +0,20943]); **73/100 episodios sobre 0,5**. Desagregada
por barrera de h mínimo:

| Tipo | S1_ctrl | S1 | Δ |
|---|---|---|---|
| pared | 0,37141600 | 0,44860000 | **+0,07718400*** |
| robot | 0,02319600 | 0,02389200 | +0,00069600 n.s. |
| obstáculo | 0 | 0,10295200 | **+0,10295200*** |

Por restricción ligante en el óptimo da lo mismo (obstáculo +0,102, pared
+0,077, robot +0,010; ≥2 tipos a la vez +0,008). **El obstáculo explica sólo
el 57 % del aumento; el 43 % restante es intervención de PARED.**
**Hipótesis, no verificada:** al quitar área del centro, el obstáculo desplaza
la ocupación hacia la periferia (tiempo en la banda de 0,18 m +0,00206*,
violaciones de margen de pared +0,63*), donde la política —bloqueante— ya estaba
en conflicto con el filtro.

### Corrección del criterio de parada (13/sep/2026)

La primera corrida se detuvo en S1 por **intervención > 0,5**. Ese criterio
estaba **mal calibrado para este experimento**: se escribió para no gastar
tiempo en una configuración que falla, pero la configuración **no falla** en
S1 (0 contactos, 0 colisiones, 0 fallbacks, 0 escapes agotados con intervención
0,575). Lo que cruzó es un **indicador adelantado** calibrado en Webots con
física de contacto (r = +0,905 contra atascamiento), fuera de su dominio en
Python — la misma salvedad del Exp N.

**Criterio corregido, de falla real:** se detiene al primer escenario en que,
sobre sus 100 episodios, haya **algún** contacto con obstáculo, escape
agotado, fallback del QP o escape infactible con obstáculo activo. La
intervención > 0,5 se sigue **reportando** como indicador. Se relanzó
S0 → S1 → S2 → S3 completo (S0 vuelve a ser control bit a bit). La corrida
anterior quedó respaldada con sufijo `_parada_indicador`.

**Lectura conjunta con el Exp N — cuánto margen tiene la arquitectura.** La
configuración desplegada opera a **0,397** de intervención con el indicador en
**0,5**: **~0,10 de margen**. Tres perturbaciones distintas lo consumen por
igual: **agregar agentes** (n = 7 → 0,530), **reducir el área** (2,7 m →
0,541) o **agregar un obstáculo central** (→ 0,575). Esta caracterización
sale de los dos experimentos juntos: la restricción operativa del sistema de
tres capas no es la seguridad (intacta en todo lo medido) sino el **conflicto
política-filtro**, y la arquitectura tiene poco margen frente a cualquier
barrera nueva.

### Resultado 2 — S2 y S3 con el criterio corregido

Relanzado S0 → S3 el 13/sep/2026. **Reproducibilidad:** S0 vuelve a dar
100/100 bit a bit contra el Exp N, y S0, S1 y S1_ctrl salen **idénticos** a la
corrida del 12/sep en 100/100 semillas.

| | S1 (1 central) | S2 (2 descentrados) | S3 (5, corredores 0,55 m) |
|---|---|---|---|
| Contactos con obstáculo | 0 | 0 | 0 |
| Colisiones <0,15 m | 0 | 0 | 0 |
| Fallbacks del QP | 0 | 0 | 0 |
| d_min centro→superficie, mínimo global | 0,13716615 | **0,12876785** | 0,15505628 |
| Escapes agotados (suma, 100 eps) | 0 | 0 | **5** (4 episodios) |
| Escapes infactibles con obstáculo activo | 0 | 0 | **5** (5 episodios) |
| Intervención media (indicador) | 0,575444 | 0,574132 | 0,671060 |
| Episodios con intervención > 0,5 | 73/100 | 86/100 | 100/100 |

**S2 pasa los cuatro criterios de falla. S3 dispara dos** (escape agotado y
escape infactible con obstáculo activo) → **parada por falla real en S3**.

**Qué falla en S3 — liveness de la capa de recuperación, NO la garantía de
seguridad.** Con cinco obstáculos, 0 contactos, 0 colisiones y 0 fallbacks: el
filtro sigue cumpliendo lo que promete. Lo que empieza a fallar es el escape:
infactibles 0,20 por episodio contra 0,02 en su control (Δ +0,18 [+0,074,
+0,286]*), 5 de ellos con un obstáculo activo (episodios 420012, 420015,
420044, 420062, 420096). Los **agotados no son específicos del obstáculo:**
S3_ctrl, sin obstáculos, también tuvo uno (420092), y el Δ pareado es +0,04
[−0,015, +0,095] n.s.; en S3 ocurren en 420009, 420037 (2), 420076 y 420096.
**Atribución verificada (corrida complementaria, 13/sep/2026).** El exceso de
S3 es de 18 infactibles (20 contra 2 del control), y sólo 5 estaban marcados
"junto a obstáculo". Se descartaron dos hipótesis de instrumentación:

- *"Junto a obstáculo" contaría sólo el obstáculo de h mínimo* — **falsa**: ya
  se contaba como obstáculo **activo** (h < 0,06).
- *Parte de los "infactibles" serían escapes exitosos* — el contador, heredado
  del coordinador, también suma el caso "ninguna barrera activa antes de
  ESC_MIN_DECISIONES" (el escape ya salió) — **falsa en los datos**: ese caso
  ocurrió **0 veces** en las nueve condiciones. Las 20 son infactibilidades
  reales (normales activas cuya suma tiene norma < 0,20). *(No verificado en
  Webots, donde el mismo contador reportó 2/90.)*

**Qué barreras estaban activas en las 20 de S3: robot en las 20, pared en 14,
obstáculo en 5.** En todas las condiciones, sin excepción, la infactibilidad
involucra a un **robot vecino**. Las 13 no marcadas son **pared + robot**: un
agente apretado entre la pared y un vecino, sin el obstáculo activo. No se
explican por desplazamiento al perímetro (la intervención de pared baja en
S3) sino por **hacinamiento**: en S3 la barrera robot-robot ligante sube +0,090
[+0,077, +0,103]* y la de h mínimo robot +0,0137*. Los corredores concentran a
los agentes. **La falla de S3 es inducida por los obstáculos, pero
mayoritariamente por vía indirecta (hacinamiento de robots); el obstáculo
participa directamente en 5 de 18.** Opuestas reales pareadas S3 − control:
+0,18 [+0,074, +0,286]*; con obstáculo: +0,05 [+0,007, +0,093]*. El 68,5 % de los
escapes adicionales de S3 se dispara junto a un obstáculo (4 % en S1, 11 % en
S2).

**Nota sobre d_min en S2 (0,12876785 < 0,13).** Un único agente-episodio bajo
la cota de diseño de peor caso (0,01 por episodio), con 0 contactos: el centro
quedó a 5,4 cm de la superficie del disco de contacto (r + 0,075). Es la
erosión por discretización ya documentada en *Filtro CBF de ejecución* (hasta
0,031 m entre decisiones), no una falla de la garantía de no contacto.

### Resultado 3 — mecanismo: el costo indirecto por las paredes, y su predicción

**Mecanismo propuesto por el revisor (13/sep), sobre los datos de S1:** el
obstáculo central aporta +0,103 de intervención propia, pero la de **pared**
sube +0,077, y de los +2,12 escapes sólo 0,08 (4 %) se disparan junto al
obstáculo. El obstáculo desplaza a los agentes hacia el perímetro —el área
libre del punto de mira baja de 6,97 a 6,25 m²— y **casi la mitad de su costo
es indirecto, por las paredes.** Predicción: obstáculos periféricos costarían
menos por ese canal.

**Verificación directa del desplazamiento** con una métrica nueva (fracción de
agente-paso con el centro a < 0,5 m de una pared, anillo de 5 m²): **sube en
los tres escenarios** (S1 +0,0764*, S2 +0,0468*, S3 +0,0837*).

**Contraste de la predicción** (`contraste_central_periferico.py`), por semilla
sobre las diferencias pareadas: contraste = Δ(S1) − Δ(S2), n = 100.

| Métrica | Δ S1 | Δ S2 | Δ S3 | S1 − S2, IC95 |
|---|---|---|---|---|
| Intervención de **pared** (indirecta) | +0,077184 | +0,025280 | −0,022172 | **+0,051904 [+0,019112, +0,084696]*** |
| Intervención de obstáculo (directa) | +0,102952 | +0,128400 | +0,287852 | −0,025448 [−0,037991, −0,012905]* |
| Intervención total | +0,180832 | +0,153908 | +0,279348 | +0,026924 [−0,008260, +0,062108] n.s. |
| Ocupación de la periferia | +0,076404 | +0,046808 | +0,083672 | +0,029596 [+0,003470, +0,055722]* |
| Por m² de área libre perdida (total) | +0,2497 | +0,1325 | +0,1165 | **+0,117225 [+0,073996, +0,160455]*** |
| Por m² perdido (pared) | +0,1066 | +0,0218 | −0,0092 | +0,084819 [+0,046173, +0,123465]* |

Fracción indirecta (Δ pared / Δ total): **S1 0,43 · S2 0,16 · S3 −0,08.**

**La predicción se sostiene.** Los dos obstáculos descentrados quitan un 60 %
más de área (1,16 contra 0,72 m²) y producen **un tercio** del costo de pared
del central; por m² perdido el costo total es la **mitad**. En S3 el canal
indirecto desaparece (−0,022, n.s.): con cuatro obstáculos junto a las
esquinas la periferia misma está ocupada, y el costo pasa a ser casi todo
directo (+0,288) y de interacción robot-robot en los corredores (robot
ligante +0,090*). Salvedades: S2 no es puramente periférico (superficies a
0,50 m de la pared), y S1 y S2 difieren también en número de obstáculos.
**Consecuencia de diseño:** para una misma área bloqueada, un obstáculo en el
centro de la arena es el peor caso para esta arquitectura, porque empuja a
los agentes contra el borde donde la política ya estaba en conflicto con el
filtro.

### Cobertura: un resultado no esperado, con la confusión RESUELTA

Cobertura sobre celdas accesibles, pareada contra el control: S1 −0,0121 n.s.;
**S2 +0,0288 [+0,0151, +0,0425]*; S3 +0,0183 [+0,0039, +0,0326]*.** Con
obstáculos descentrados, la cobertura del área accesible **sube**. Sobre la
cuadrícula completa, que incluye el área perdida: S1 −0,0333*, S2 +0,0048
n.s., S3 −0,0207*.

**Confusión candidata:** los objetivos rebotan en los obstáculos sólo en Sk,
así que la dinámica de objetivos —y el gradiente que sigue la política— difiere
del control. **Se resolvió con un control FANTASMA** (Sk_fant, propuesto por el
revisor): los objetivos rebotan en los mismos discos que en Sk —su dinámica no
depende de los agentes, así que es idéntica—, pero los agentes no tienen
barrera, contacto ni máscara (intervención del fantasma igual a la del control:
0,400 / 0,424 / 0,390).

| Cobertura accesible, pareada | fant − ctrl (objetivos) | Sk − fant (sistema) |
|---|---|---|
| S1 | **−0,01048 [−0,01572, −0,00524]*** | −0,00165 [−0,01667, +0,01336] n.s. |
| S2 | −0,00393 [−0,01140, +0,00354] n.s. | **+0,03273 [+0,01955, +0,04592]*** |
| S3 | +0,00211 [−0,00706, +0,01127] n.s. | **+0,01615 [+0,00160, +0,03070]*** |

**En S2 y S3 la subida es del SISTEMA, no de la dinámica de objetivos.** La
sospecha declarada queda refutada. En S1 ocurre lo contrario: el rebote de los
objetivos en el disco central cuesta −0,010* y el sistema no agrega nada.
**Qué parte del sistema** —la barrera que desvía a los agentes o la máscara que
les quita un atractor— **no se separa** con este diseño. Hipótesis, no
verificada: los obstáculos descentrados rompen trayectorias repetitivas (la
misma hipótesis sin verificar del escape).

### Qué afirmación del documento sustenta

**RESPALDA, con límite caracterizado**, la generalidad de la capa de
seguridad: *"La capa de ejecución absorbe obstáculos que la política no
percibe. Hasta dos obstáculos, no se observó ninguna falla —ni contacto, ni
colisión, ni fallo del solver, ni del comportamiento de recuperación—. Con
cinco obstáculos y corredores de 0,55 m la garantía de no contacto se mantiene,
pero la capa de recuperación empieza a fallar (escapes infactibles junto a
obstáculos en 5 de 100 episodios), lo que marca el límite de la arquitectura
sin percepción de obstáculos. Para una misma área bloqueada, un obstáculo
central cuesta el doble que uno descentrado, porque desplaza a los agentes
hacia las paredes."*

**No** sustenta que "absorbe hasta cinco obstáculos sin perder la garantía" en
sentido amplio: la garantía de **seguridad** sí se conserva en S3, pero el
criterio de falla acordado incluye la recuperación, y ésa falló. Tampoco
sustenta ninguna afirmación de adaptabilidad de la política.

**Encuadre de S3 para el documento — tercera instancia de un patrón, no una
excepción nueva.** S3 es la **tercera** vez que el proyecto observa el mismo
patrón: **seguridad intacta, vitalidad degradada**.

1. **Equilibrio en el margen del CBF** (*Filtro CBF de ejecución*, *Criterio
   operativo*): 33 de los 39 atascos restantes de v2+CBF ocurren en el margen,
   con velocidad casi nula y sin contacto. El filtro garantiza invarianza, no
   progreso.
2. **Erosión del margen bajo conflicto alto** (v3+CBF): el margen de diseño se
   viola en 79/90 agente-episodios (d_min 0,1118 m) sin contacto físico. La
   garantía se conserva por la holgura con que se dimensionó, no por la
   formulación.
3. **Exp O, S3:** con cinco obstáculos y corredores de 0,55 m, 0 contactos,
   0 colisiones y 0 fallbacks, pero la capa de recuperación empieza a quedarse
   sin dirección de escape.

Escrito así, S3 **refuerza una conclusión existente** —la capa de ejecución
entrega seguridad pero no vitalidad, y la vitalidad es lo que se degrada al
aumentar la dificultad— en vez de abrir un caso aparte.

**Recomendación de despliegue (accionable).** A igual área bloqueada, el
obstáculo central es el peor caso: **0,250 de intervención por m² de área
libre perdida**, contra 0,132 (S2) y 0,117 (S3), con el contraste pareado
S1 − S2 significativo (+0,117 [+0,074, +0,160]). Si el entorno real tiene
obstrucciones, **conviene que no estén en el centro del área de trabajo**: un
obstáculo central empuja a los agentes contra las paredes, donde la política ya
estaba en conflicto con el filtro.

**Artefactos:** `experimentos/expO_obstaculos/` — `lib/`, `modelos/` (copias
verificadas por sha256), `entorno_obstaculos.py`, `correr_experimento_O.py`,
`analizar_experimento_O.py`, `contraste_central_periferico.py`;
`resultados/experimento_O_completo.csv` (700 filas: S0 y S1–S3 con sus
controles; sin redondeo), `registro_O.txt`, `corrida_O.log`,
`resumen_experimento_O.txt`, `contraste_central_periferico.txt`;
corrida complementaria (`python correr_experimento_O.py complementario`,
`analizar_complementario_O.py`): `experimento_O_complementario.csv` (900 filas,
S1–S3 × {Sk, ctrl, fant}; Sk/ctrl idénticas bit a bit al CSV principal),
`registro_O_complementario.txt`, `resumen_complementario_O.txt`,
`corrida_O_complementario.log`; los respaldos
`_parada_indicador` y `experimento_O_completo_respaldo_20260913_132727.csv`
son la corrida del 12/sep (sólo S0/S1, idéntica); `figuras/fig_obstaculos_intervencion.png`,
`fig_obstaculos_costo.png` (300 dpi, es-ES, sin título). Ningún original
modificado.

**Costo:** ~3,5 min de máquina el 12/sep/2026 y ~7 min el 13/sep/2026 (11
procesos).

---

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

### EXPLORATORIO: S2 y S3, corridos después de la parada y fuera de la regla (2026-10-19; lectura corregida el 2026-10-24)

**S2 y S3 se corrieron DESPUÉS de la parada de S1 y FUERA de la regla de parada, por decisión de José del 19-10.** El motivo: el agotado que detuvo S1 no lo induce el obstáculo (la semilla 420001 lo tiene en las cuatro condiciones, también en el control). **Es exploratorio y no cambia el veredicto del Exp Q:** S1 detiene por la regla del Exp O, y lo de arriba queda tal cual.

**Corrección del 24-10 (pedido de José).** Se corrigieron los titulares y la lectura, y se agregó la estadística de eventos raros: Clopper-Pearson y McNemar exacta sobre episodios. **Ningún dato cambia y no se corrió ningún episodio.** Respaldo de la versión anterior: `ENTRADA_BITACORA_expQ_EXPLORATORIO_respaldo_20261024_preEventosRaros.md`.

**Cómo, sin tocar nada de S1.** `correr_exploratorio_Q.py` sólo orquesta: importa y llama a `correr_experimento_Q.py` y no redefine ni parchea nada. Lo comprueba `comparar_ast_exploratorio_Q.py`.
- Exige la huella `e265b6cd…4a29` y los tres registros aprobados con ella.
- Comprueba el sha256 de los tres archivos de S1 al empezar y al terminar.
- **Antes de S2, recalculó S1_din sin parciales: 100/100 semillas idénticas en texto a `experimento_Q_completo.csv` en las 66 columnas.**
- Después corrió S2 y S3 (cuatro condiciones, 100 semillas) sin detenerse.

Las salidas llevan EXPLORATORIO en el nombre, los CSV la columna `exploratorio` = 1 y los textos EXPLORATORIO en la primera línea:
- `experimento_Q_EXPLORATORIO_S2_S3.csv` (800 filas);
- `reproduccion_S1_din_EXPLORATORIO.csv`;
- `registro_Q_EXPLORATORIO.txt`, `resumen_Q_EXPLORATORIO.txt` y `corrida_Q_EXPLORATORIO.log`;
- `parciales/exploratorio_*`;
- `fig_EXPLORATORIO_*`;
- `manifiesto_sha256_Q_EXPLORATORIO.txt`.

**Criterios de falla (los cuatro del Exp O; acá no detienen), sumas sobre los 100 episodios:**

| | contactos | agotados | fallbacks del QP | infactibles con obstáculo activo | d_min centro→superficie |
|---|---|---|---|---|---|
| `S2_din` | 0 | 0 | 5 | 1 | 0.12054343 |
| `S2_quieto` | 0 | 1 | 0 | 0 | 0.14718863 |
| `S2_sinvel` | 0 | 0 | 0 | 0 | 0.09768094 |
| `S3_din` | 0 | 13 | 154 | 2 | 0.07890187 |
| `S3_quieto` | 0 | 3 | 0 | 2 | 0.14020460 |
| `S3_sinvel` | 13 | 5 | 79 | 3 | 0.07500000 |

Con la regla, `S2_din` y `S3_din` la habrían disparado.

**Eventos raros: episodios con al menos un evento, de 100, con su IC95 de Clopper-Pearson.** En el control, el contacto y el acercamiento "no aplican": el obstáculo no es físico, los agentes lo atraviesan y "bajo 0.13 m" da 100/100.

| | fallback | agotado | contacto | bajo 0.13 m |
|---|---|---|---|---|
| `S2_ctrl` | 0 [0.0000, 0.0362] | 0 [0.0000, 0.0362] | no aplica | no aplica |
| `S2_quieto` | 0 [0.0000, 0.0362] | 1 [0.0003, 0.0545] | 0 [0.0000, 0.0362] | 0 [0.0000, 0.0362] |
| `S2_din` | 2 [0.0024, 0.0704] | 0 [0.0000, 0.0362] | 0 [0.0000, 0.0362] | 1 [0.0003, 0.0545] |
| `S2_sinvel` | 0 [0.0000, 0.0362] | 0 [0.0000, 0.0362] | 0 [0.0000, 0.0362] | 11 [0.0562, 0.1883] |
| `S3_ctrl` | 0 [0.0000, 0.0362] | 0 [0.0000, 0.0362] | no aplica | no aplica |
| `S3_quieto` | 0 [0.0000, 0.0362] | 3 [0.0062, 0.0852] | 0 [0.0000, 0.0362] | 0 [0.0000, 0.0362] |
| `S3_din` | 5 [0.0164, 0.1128] | 8 [0.0352, 0.1516] | 0 [0.0000, 0.0362] | 28 [0.1948, 0.3787] |
| `S3_sinvel` | 3 [0.0062, 0.0852] | 5 [0.0164, 0.1128] | 3 [0.0062, 0.0852] | 47 [0.3694, 0.5724] |

Las comparaciones pareadas van con la McNemar exacta, bilateral, sobre los episodios discordantes: b/c son los episodios con el evento sólo en el primero y sólo en el segundo.

**El fallback y la distancia: primero el hecho, después la coincidencia y al final la hipótesis.**
1. **El hecho, por construcción.** Mientras el QP no tiene solución, el filtro manda u = (0, 0) **sin certificado**, y en esos pasos la garantía de invarianza del filtro no aplica.
2. **La coincidencia, por episodio.**
   - En `S3_din`, los 4 episodios que bajan de 0.10 m (420025, 420048, 420057 y 420099) están entre los 5 con fallback. En los otros 95, d_min no baja de 0.1208.
   - En `S3_sinvel`, los 3 episodios con contacto (420013, 420057 y 420090) son exactamente sus 3 episodios con fallback.
   - En `S2_din`, los 2 episodios con fallback no bajan de 0.13 m (d_min 0.13160467).
3. **La hipótesis, pendiente del diagnóstico.** Con el obstáculo en movimiento, detenerse no es seguro, y el mínimo de `S3_din` (0.07890187 m, a 3.9 mm del disco de contacto) habría ocurrido en un paso de fallback.
   - Los datos por episodio muestran que fallback y acercamiento coinciden, **no cuándo**.
   - Lo resolvería el diagnóstico de los 10 episodios con fallback, que por ahora queda afuera.

**Por eso "seguridad intacta, vitalidad degradada" no describe S3.** En los episodios con fallback lo que falla es el solver, y con él deja de aplicar la garantía.

**La hipótesis del encierro (§2.3 de la propuesta), observada como la anticipó §2.3.**
- Los fallbacks del QP aparecen sólo con el obstáculo en movimiento: 5 en 2/100 episodios de `S2_din` y 154 en 5/100 de `S3_din`, contra 0 con los obstáculos quietos.
- Ninguna fila F1 se saturó en ningún nivel.
- **Los datos por episodio no separan las dos vías de infactibilidad:**
  - el término de velocidad, que con h < s/α hace infactible u = 0;
  - la erosión del margen hasta h < 0, que también da fallbacks sin el término: `S3_sinvel` tiene 79 en 3/100, y sin el término, por construcción, un fallback exige algún h < 0.

**Atribución por semilla y prueba exacta pareada:**
- **Fallbacks: al movimiento, por un argumento estructural y no por la prueba exacta.**
  - Con obstáculos quietos, u = 0 es factible mientras todos los h ≥ 0, así que ahí sólo puede haber fallback después de una violación. No hubo ninguno.
  - La McNemar exacta, din frente a quieto, no los separa: 2/0, p = 0.5000 en S2; 5/0, p = 0.0625 en S3.
- **Agotados de S3: al obstáculo, no al movimiento. El contraste con S1 es explícito.**
  - En S1, el agotado aparecía también en el control, en la misma semilla (420001).
  - En S3, ninguno de los 8 episodios con agotado de `S3_din` tiene agotado en el control: 8/0, p = 0.0078. Ahí sí es el obstáculo.
  - No se puede decir que sea el movimiento: contra el quieto da 8/3, p = 0.2266.
- **Infactibles con obstáculo activo:** S2 da 1/0 contra el quieto (p = 1.0000) y S3 2/2 (p = 1.0000). No hay atribución.
- Por semilla, ningún evento de falla de `Sk_din` se repite en la misma semilla de `Sk_ctrl` o de `Sk_quieto`. Sólo la 420057 de S3 comparte el agotado y el fallback con `S3_sinvel`.

**El término de velocidad conserva margen.**
- **Episodios bajo 0.13 m** (con el término frente a sin él):
  - S2: 1 frente a 11 (sinvel − din 10/0, p = 0.0020);
  - S3: 28 frente a 47 (28/9, p = 0.0026).
- **Contactos de S3:** 0 frente a 3 episodios (3/0, p = 0.2500), todos por empuje del obstáculo. Apuntan en la misma dirección, pero no son significativos.

**Costo en tarea** (pareado; denominadores del §3.6):

| | din − ctrl (accesible) | din − quieto (fuera del arranque) | intervención din − ctrl |
|---|---|---|---|
| S2 | +0.03586702 [+0.02168296, +0.05005108]* | +0.01406646 [+0.00052355, +0.02760937]* | +0.19288800 [+0.16916511, +0.21661089]* |
| S3 | −0.00147768 [−0.01630747, +0.01335211] | −0.01027655 [−0.02445920, +0.00390609] | +0.32190000 [+0.30038257, +0.34341743]* |

- **En S2 el movimiento sigue subiendo la cobertura,** como en S1.
- **En S3 ya no se distingue de cero.** La intervención es casi toda del obstáculo (ligante +0.29051200 en S3), y la ocupación de la periferia sube +0.10771200 [+0.08916852, +0.12625548]*.

**Lectura.**
- **Fuera de la regla y con F1 no hubo contacto en S2 ni en S3, pero en S3 eso no es una garantía.** Los acercamientos bajo 0.10 m de `S3_din` están todos en episodios con fallback: tramos en los que el filtro, por construcción, manda u = (0, 0) sin certificado. Que el mínimo ocurra justo en esos pasos es la hipótesis pendiente.
- **El término de velocidad conserva margen** (episodios bajo 0.13 m: p = 0.0020 en S2 y p = 0.0026 en S3), pero no impide los fallbacks.
- **Los fallbacks aparecen sólo con el obstáculo en movimiento**, como anticipó §2.3, aunque los datos no separan h < s/α de la erosión del margen.
- **Los agotados de S3 son del obstáculo, no del movimiento.**

**No sustenta:**
- un cambio del veredicto del Exp Q (S1 detiene por la regla);
- nada sobre el laboratorio;
- que la garantía de no contacto sea robusta en S3: queda a 3.9 mm del contacto, en un episodio con fallback;
- que el mínimo ocurra con el agente detenido (es la hipótesis pendiente del diagnóstico);
- que el rescate de F2 resuelva estos encierros: no se probó.

**Verificación:**
- `verificar_cifras_exploratorio_Q.py` recalcula cada cifra del resumen exploratorio y de esta subsección. El Clopper-Pearson y la McNemar los recalcula con código propio, sin scipy. Comprueba también la reproducción de S1_din, el sha256 de S1, la huella, los rótulos y el pareo (resumen 3182/3182, subsección 439/439, fijos 609/609). Desde el 24-10 extrae además cada cifra del texto y exige que sea un valor recalculado o una constante de diseño (n, umbrales, número de sección);
- `test_exploratorio_Q.py`: 8 pruebas, entre ellas la igualdad del IC y de la p de los dos códigos, y valores conocidos;
- mutaciones: dos cifras de las secciones nuevas del resumen y tres de esta subsección, todas detectadas. La primera mutación de la subsección (una p que aparece en dos lugares) había pasado con el chequeo anterior, que sólo pedía la cifra en algún lugar del texto: por eso se agregó la extracción de cifras;
- el AST de los scripts nuevos: "sólo orquestan";
- el chequeo de congelados de la campaña: "IGUAL a lo probado" (24-10, 09:42).

**Costo:** la corrida, 28.6 min de reloj (20:22–20:51 del 19-10), de los que 185 s fueron la reproducción de S1_din. **Corrección del 2026-11-09: no fue "con la PC libre", como decía esta línea, que además decía "de máquina" en lugar de "de reloj".** La PC estaba a batería desde las 19:53:37 (Kernel-Power 105) y se suspendió por batería crítica de 20:41:30 a 20:50:10 (visor de eventos de Windows: Kernel-Power 524 y 42 al entrar; al volver, Kernel-General 1 ajustó el reloj en 517 s). Eso explica que 11 episodios de S3_sinvel (420033–420043) tardaran ≈ 530 s cada uno y que esa celda tardara 631 s. El cálculo es determinista: la suspensión no cambia ningún resultado, y el control del Exp R reprodujo esos episodios bit a bit (ver su entrada, abajo). La corrección del 24-10 no corrió episodios.

---

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

### Resultados (corrida del 2026-11-13, semillas nuevas 420110–420509)

**Corrida.** `correr_experimento_R.py experimento`, con el "listo" de José, en dos tramos:
- **Desde las 20:25:13.** Corrió once celdas. La PC se desenchufó a las 21:04:13 (Kernel-Power 105), en medio de S3_ctrl. Esa celda había arrancado enchufada (83 %) y tardó 460.8 s, frente a 172.5 s de S1_ctrl y 198.0 s de S2_ctrl; su t_episodio_s medio fue 12.50 s. Antes de S3_sinvel la compuerta de energía dio PARAR.
- **21:30:22–21:34:46.** Ya enchufada otra vez, reutilizó las once celdas, previa comprobación de sus firmas, y corrió S3_sinvel.

El cálculo es determinista: el corte sólo cambia los tiempos de pared, que no entran en ninguna hipótesis.

**El registro** es `resultados/registro_R.txt`:
- FILAS 4800 (4800 distintas) y autochequeos de la Parte B con 0 problemas en las 4800 filas;
- la prueba física del pareo discrimina: 30 agente-pasos en 29 episodios con fallback (2 de ellos con 0);
- 33 trazas, en biyección con sus filas; se esperaban 44, con intervalo [31, 57];
- «PARTE B: OK»;
- congelados de la campaña "IGUAL a lo probado" al empezar y al terminar;
- el manifiesto pre (`manifiesto_R_pre_20261113_2021.txt`) con todas sus entradas iguales al terminar.

**Análisis y verificación.**
- `analizar_experimento_R.py`, en la versión de la adenda 1, escribió `resultados/resumen_R.txt` y tres figuras.
- `verificar_cifras_R.py` encontró las 258 líneas del resumen iguales a las recalculadas desde el crudo, texto contra texto. Recalculó la Parte B en 33 filas desde su traza y en 3567 por identidad, y contrastó con scipy 48 valores, con una diferencia máxima de 2.2e-16.
- `literales_bitacora_R.py` verifica cada cifra y cada veredicto de esta subsección.

**Resultados.** n = 400 por celda; McNemar exacta (b = sólo en A); IC95 de Clopper-Pearson; α = 0,05; palabras del §2.4.

| Hipótesis | Clase | Datos | Veredicto |
|---|---|---|---|
| H1-S3 | primaria | S3_din 12/400, S3_quieto 0/400; b/c = 12/0; p = 0.0005 | sostenida |
| H1-S2 | secundaria | S2_din 3/400, S2_quieto 0/400; b/c = 3/0; p = 0.2500 | no sostenida |
| H2-S2 | primaria | S2_sinvel 53/400, S2_din 27/400; b/c = 41/15; p = 0.0007 | sostenida |
| H2-S3 | primaria | S3_sinvel 177/400, S3_din 88/400; b/c = 133/44; p < 0.0001 | sostenida |
| H3a | primaria | S3_din 20/400, S3_ctrl 1/400; b/c = 20/1; p < 0.0001 | sostenida |
| H3b | secundaria | S3_din 20/400, S3_quieto 11/400; b/c = 19/10; p = 0.1360 | no sostenida |
| H4 | secundaria | Δ_S1 − Δ_S3 +0.02443442 [+0.01519369, +0.03367515]; Δ_S2 − Δ_S3 +0.03761557 [+0.02807480, +0.04715635] | sostenida |
| H5a | primaria | contacto en Sk_din: 0/400 en S1, S2 y S3 | cumplida |
| H5b | secundaria | S3_sinvel 2/400, S3_din 0/400; b/c = 2/0; p = 0.5000 | no sostenida |
| H6a-S3 | secundaria | 6 de 6 episodios bajo 0,10 m con el mínimo en la ventana | cumplida |
| H6a-S1, H6a-S2 | secundaria | ningún episodio bajo 0,10 m | no evaluable en el nivel |
| H6b-S1, H6b-S2, H6b-S3 | secundaria | 0/400 bajo 0,10 m fuera de la ventana en cada nivel | cumplida |

Con Holm sobre la familia de 7, las cuatro pruebas con p sostenidas siguen bajo 0,05 en la dirección predicha (p Holm: H1-S3 0.0024, H2-S2 0.0027, H2-S3 < 0.0001, H3a 0.0001). Holm no cambia ninguna palabra.

**Lectura.**
- **El encierro aparece con el movimiento en S3 (H1-S3).** Con obstáculos quietos no hubo ningún fallback en ningún nivel (0/400 en S1, S2 y S3). Es descriptivo: no se escribe que el encierro "necesita" el movimiento. En S2 hubo 3 fallbacks contra 0 (H1-S2 no sostenida, p = 0.2500), lo que no equivale a ausencia de efecto (§6).
- **El término de velocidad conserva margen (H2) en S2 y en S3.** En S3, sin él, 177 de 400 episodios bajan de 0,13 m; con él, 88.
- **Los agotados de S3 son del obstáculo (H3a).** Que el movimiento agregue agotados (H3b) queda no sostenida: Δ de tasas +0.02250000 [-0.00382795, +0.04882795]. Por el §2.3:
  - no se corrige la frase del exploratorio (D7, que se aplicaba sólo si H3b quedaba sostenida);
  - tampoco se afirma que los agotados no dependan del movimiento.
- **H4, sostenida: en S3 el efecto del obstáculo móvil (din − ctrl) sobre la cobertura accesible es menor, con signo, que en S1 y en S2.** El efecto es positivo en los tres niveles (con el obstáculo móvil la cobertura accesible es mayor que en el control), y en S3 casi desaparece. Δ din − ctrl: S1 +0.03306994, S2 +0.04625109, S3 +0.00863552.
- **Seguridad (H5a, H6).**
  - **Contactos.** Ninguno en din en los 1200 episodios. 0/400 por nivel acota la tasa de contacto por debajo de 0.0092 en cada nivel; no es una tasa cero.
  - **Acercamientos bajo 0,10 m.** Los 6 de S3_din caen en la ventana de un fallback del agente que se acerca. En 4 el mínimo está dentro del fallback, con rachas de 10 a 30 decisiones, y en 2 justo después.
  - **El más profundo** es S3_din 420289: 0.0755 m, a 0,5 mm del contacto (0,075 m), dentro de un fallback de 30 decisiones.
  - **Fuera de la ventana de 5 decisiones de un fallback** ningún agente bajó de 0,10 m en ningún nivel (H6b). Esto no significa «fuera de los fallbacks»: con W = 1, es decir, contando sólo las decisiones que no están ellas mismas en fallback, S3 tiene 3/400 episodios bajo 0,10 m (ver la sensibilidad).
- **Contactos sin el término de velocidad (H5b, no sostenida).** Hubo 2 episodios de S3_sinvel, 420402 y 420494, con 7 agente-pasos de contacto en total. Los 7 caen en la ventana de un fallback del propio agente. Con b/c = 2/0 la McNemar exacta no puede bajar de p = 0.5000, y «no sostenida» no es ausencia de efecto (§6).
- **Sensibilidad de H6** (descriptiva, sin veredicto).
  - Con W = 5 y umbral 0,13 m quedan fuera de la ventana 80/400 episodios en S3 (20 %), 26/400 en S2 y 6/400 en S1. El prerregistro esperaba en S3 al menos un ~23 %, así que el resultado queda algo por debajo. Ese ~23 % venía de los 23 de 100 episodios del exploratorio que bajaron de 0,13 m sin ningún fallback.
  - Con W = 1, en 0,10 m, S3 da 3/400.

**Lo que R no sustenta.** Es el §6 del prerregistro, palabra por palabra al final de `resumen_R.txt`. Lo esencial:
- R no cambia el veredicto del Exp Q;
- S2 y S3 no "pasan" la regla del Exp O;
- la garantía de no contacto no es robusta donde hay fallbacks, porque ahí el filtro manda u = (0, 0) sin certificado;
- H5a «cumplida» no es una tasa cero;
- una prueba «no sostenida» no es ausencia de efecto (aquí H1-S2, H3b y H5b);
- no se conserva la cota de diseño de 0,13 m fuera de los fallbacks: con W = 5, 80/400 episodios de S3_din bajan de 0,13 m fuera de la ventana;
- H6 mide coincidencia en el tiempo, no causa;
- R no dice nada del laboratorio, del rescate de F2 ni de otras políticas o geometrías;
- no es una verificación independiente del código.

**Criterios de cierre del spec (§6).**
1. **`comparar_ast_R.txt`.** Las cuatro comprobaciones están en OK: el spec pedía dos y el prerregistro sumó otras dos.
2. **Control.** 1200/1200 filas idénticas en texto en las 66 columnas, y pasos_agente_fallback = qp_fallbacks en las 1200.
3. **Pasabilidad.** OK en S1, S2 y S3 con las 400 semillas.
4. **Manifiesto pre.** Se hizo a las 20:21:42, antes del inicio de los dos tramos, y `experimento` lo comprobó al empezar y al terminar.
5. **CSV.** 4800 filas, 12 celdas × 400 semillas, sin semillas repetidas ni faltantes, y prerregistrado = 1 en todas.
6. **Resumen.**
   - Cada hipótesis tiene la palabra que fija el §2.4.
   - `verificar_cifras_R.py` está en orden con el resumen, y `literales_bitacora_R.py` con esta subsección.
   - Las mutaciones se detectan: una cifra y un veredicto invertido en cada documento.
7. **Figuras.** La leyenda queda afuera y el rótulo arriba, sin nada tapado; se revisaron una por una.
8. **Pruebas, huellas y congelados.**
   - Las pruebas están en verde: `test_experimento_R` 50/50 y `test_verificar_cifras_R` 44/44.
   - La huella de Q coincide al inicio y al final de cada subcomando.
   - Los sha256 de S1 y de los crudos exploratorios siguen intactos, y los congelados dan "IGUAL a lo probado".
9. **Fuera de la carpeta del Exp R** cambiaron dos archivos:
   - la bitácora, con tres respaldos (preExpR, preCorrExpR y preResultadosR) en lugar de los dos que preveía el spec, porque la pasada pre llevó una corrección de redacción;
   - `PROTOCOLO_L0_L2.md:71`, como excepción declarada: el filtro simétrico, con respaldo, previsto por el prerregistro.

   Fuera de los bloques del Exp R, la bitácora es idéntica byte a byte a la versión anterior a cada pasada. El 13-11 a las 19:26 la modificó además otra sesión (respaldo preRonda3), fuera de los bloques del Exp R.
10. **`manifiesto_sha256_R.txt`.** Se hizo al cierre.

**Manifiesto al cierre.** `resultados/manifiesto_sha256_R.txt`: 144 archivos (todos, logs incluidos), sha256 `51326df1ac53efbff0c57f0354937238a6f2003b6a30e1e6908e874fc457262c`. La copia de esta subsección que está en la carpeta (`ENTRADA_BITACORA_expR_resultados.md`) no lleva este párrafo, porque el manifiesto la incluye.

---

## v2 — Reentrenamiento con bordes bloqueantes (`modelo_sanidad`)

**Cambio:** `modo_borde="bloqueante"` durante el entrenamiento (posición
recortada a `[0, W]`, θ intacta). 200k pasos, Trial 13 sin cambios.

**Resultado en Python:** v2 alcanza **cobertura equivalente** a
RESULTADO_PRIMERO bajo bordes bloqueantes, con **9.5× menos fracción de tiempo
en el borde** (0.5117 → 0.0541).

La equivalencia es un resultado del test pareado sobre las mismas 100
semillas, no una lectura de las medias:

| | Cobertura |
|---|---|
| RESULTADO_PRIMERO (bloqueante) | 0.4516 |
| v2 sanidad (bloqueante) | 0.4345 |

Diferencia pareada **−0.0171 ± 0.0921**, IC95 **[−0.0351, +0.0010]** — el
intervalo **incluye el cero**, así que las dos son estadísticamente
indistinguibles en cobertura. Comparar 0.4345 contra un umbral fijo de 0.4516
habría reportado un incumplimiento que el test descarta.

**Nota sobre el checkpoint:** el pico de las curvas estaba en **170k
(cobertura 0.6242)** y cayó −27.4% hasta 200k, que fue el checkpoint guardado.
Primera aparición del problema de selección de checkpoint; el modelo adoptado
podría haber sido mejor aún.

**Resultado en Webots (1 robot):** atascos **18/18 → 3/18**, tiempo al primer
atasco 11.8 → 31.3 s, distancia media a pared 0.0745 → **0.5125 m**. Con CBF:
1/18 atascos e intervenciones 408/ep → **31.1/ep** (13/18 episodios con cero).

**Artefactos:** `experimentos/tesis_v2_sanidad/`,
`controllers/supervisor_fisica/resultados/experimento_A_atascos_sanidad*.csv`

---

## v3 — Radio de chasis + penalización de pared

**Cambios:** `modo_borde="bloqueante_radio"` (recorte a `[r, W−r]` con
r = 0.075, alineando la geometría con Webots) y penalización graduada
`p_pared` con barrido `λ_pared ∈ {0, 1, 3}`. `λ=0` aísla el efecto del radio.

**Resultado en Python:**

| λ_pared | Cobertura | Anillo perimetral | Colisiones |
|---|---|---|---|
| 0.0 | **0.5114 ± 0.0757** | 0.4565 | 0.17 (11% eps) |
| 1.0 | 0.3822 ± 0.0960 | 0.2701 | 3.72 (100% eps) |
| 3.0 | 0.1659 ± 0.0432 | 0.1693 | 9.44 (100% eps) |

**La penalización quedó descartada:** empuja a los agentes al centro y dispara
las colisiones. λ=3 además colapsó en los últimos 40k (0.4483@160k → 0.1595),
segunda aparición del problema de checkpoint.

**Resultado en Webots (5 agentes): PEOR que v2.** Atascos **85/90 (94.4%)** vs
51/90 de v2, pese a mejor cobertura (0.3107).

**Diagnóstico:** la acción previa al atasco fue **v = −0.3100 m/s (V_MAX en
reversa) en 85 de 85 casos**. Al mover la pared a `[r, W−r]` con λ=0, meterse
contra el muro dejó de tener costo alguno en el entrenamiento. v3 corrigió
DÓNDE está la pared pero no QUÉ SE SIENTE tocarla.

**Con CBF:** aún peor — atascos 90.0%, y la fracción intervenida sube a
**0.702** (vs 0.371 de v2+CBF) porque la política quiere estar a 0.075 m y el
filtro le exige 0.18 m. El CBF pierde incluso su logro principal: 0.222
colisiones en lugar de cero.

**Artefactos:** `experimentos/tesis_v3_radio/`,
`controllers/coordinador_enjambre/resultados/lote_multi_5agentes_modelo_v3_lp0*.csv`

---

## v4 — Contacto que bloquea la rotación

**Cambio:** `modo_borde="contacto_rigido"`. Recorte a `[r, W−r]` **más**: si el
agente está en contacto y la componente de su velocidad en la normal de la
pared apunta hacia afuera, **θ no se integra ese paso**. Modela lo medido en
Webots (durante los atascos Δθ = 0.0° exacto por la fricción del chasis). La
salida queda siempre disponible: bajando o invirtiendo `v`, la rotación se
libera, de modo que no hay estados absorbentes. λ_pared = 0.

Lógica verificada con 4 casos unitarios (empuje frontal → θ congelada;
alejándose → θ libre; **reversa contra el muro → θ congelada**, que es
exactamente el modo de fallo de v3; espacio libre → θ libre).

Se incorporó selección del mejor checkpoint (**20 episodios** por evaluación,
no 5) — eligió 180k sobre el final de 200k.

**Resultado: no aprendió.**

| Métrica | Python | Webots |
|---|---|---|
| Cobertura | 0.2279 ± 0.0667 | 0.2312 ± 0.0781 |
| Rotación bloqueada | **0.6869** | — |
| Atascos | — | **82/90 (91.1%)** |
| Colisiones | 1.556 (72% eps) | 0.500 (39% eps) |

Verificación de que no era artefacto de medición: la mediana de distancia a
la pared es **exactamente 0.0750 m = r**, y la política comanda `v<0` en
**84.6%** de los pasos. La política vive contra los muros empujando en reversa.

**Interpretación:** bloquear la rotación endurece la asignación de crédito —
la única salida es reducir o invertir `v`, y hasta descubrirla el agente
acumula largas secuencias donde sus acciones de giro no afectan el estado. PPO
convergió a una política degenerada en 200k pasos.

**Advertencia de medición:** `frac_contacto` y `frac_bloqueo` son idénticos por
construcción (la posición sólo se recorta si la velocidad empujó hacia
afuera), así que la etiqueta "contacto" del resumen de v4 es engañosa: mide
"empujando contra la pared".

**Artefactos:** `experimentos/tesis_v4_contacto/`,
`controllers/coordinador_enjambre/resultados/lote_multi_5agentes_modelo_v4_mejor.csv`

---

## Arquitectura multi-robot (Fases 1 y 2)

Un controlador en Webots sólo puede comandar los motores de su propio robot,
así que el patrón de supervisor único no escala. Arquitectura adoptada:
N × `controlador_agente` (no supervisores) + 1 `coordinador_enjambre`
(supervisor, corre env + política + hotspots), con `Emitter`/`Receiver`:
canal 1 para poses (cada tick, emisión ciega) y canal 2 para acciones (cada 10
ticks, un solo mensaje difundido). Mensajes en `struct` (`protocolo.py`),
copiado idéntico en ambos controladores.

**Sincronía: impecable en 1, 2 y 5 agentes.** Antigüedad de pose **1 tick
siempre**, **0 decisiones con pose vieja**, latencia **10.00 ms**. El 1 tick es
lag estructural (Webots no garantiza orden de ejecución entre controladores).

**Tasa de atascos por densidad** (`modelo_sanidad`, sin CBF):

| Agentes | Atascos | Tasa |
|---|---|---|
| 1 | 3/18 | 16.7% |
| 2 | 9/36 | 25.0% |
| 5 | 51/90 | 56.7% |

**Diagnóstico del mecanismo:** con 5 agentes sólo **15/51** atascos tenían un
vecino dentro de `comm_radius` (y de esos, 7 a <0.22 m); con 2 agentes, 0/9.
La acción previa era `v = +0.31` (V_MAX contra la pared). El mecanismo
dominante **no es el empuje entre robots** sino el gap chasis-vs-punto; la
densidad aumenta la exposición, no la causa.

**Artefactos:** `controllers/coordinador_enjambre/`, `worlds/generar_mundo_multi.py`

---

## Filtro CBF de ejecución

`lib/filtro_cbf.py`. Formulación con **punto de mira** (ℓa = 0.05 m) para
evitar el grado relativo degenerado de la CBF ingenua sobre el centro del
uniciclo: con `p = c + ℓa·(cosθ, senθ)` la dinámica `ṗ = G(θ)·u` es lineal e
invertible (det G = ℓa > 0), así que el QP puede resolver girando y no sólo
frenando. QP de 2 variables resuelto con SLSQP. Barreras robot-robot añadidas
vía `restricciones_extra` con reparto de responsabilidad 50/50.

`D_SEGURA_ROBOTS = 0.25 m` entre puntos de mira: como los puntos están 0.05 m
por delante de cada centro, con ambos robots enfrentados la distancia entre
centros es la de los puntos menos 0.1 m, así que 0.25 garantiza ≥0.15 m entre
centros (contacto de chasis) en el peor caso.

**Aporte medido (v2, 5 agentes):** colisiones **0.500 → 0.000** en ambos
umbrales sobre las 18 semillas, cobertura 0.2168 → 0.3199, atascos 56.7% →
43.3%, distancia mínima a pared 0.0712 → 0.1800 m (nunca contacto).

**Limitación conocida — liveness:** 33 de los 39 atascos restantes ocurren
**en el margen** (d ≈ 0.18 m, con v ≈ 0.0016 m/s). El shield garantiza
invarianza del conjunto seguro pero no progreso de tarea cuando la política
está en conflicto sistemático con las restricciones. Las intervenciones son
**94.9% de pared y sólo 5.1% robot-robot**: el cuello de botella no es la
coordinación entre robots.

**Limitación conocida — el margen se erosiona bajo conflicto alto.** El margen
de diseño es 0.18 m del centro a la pared. Medido sobre los 90
agente-episodios:

| Configuración | d_min mínima | Agente-eps bajo 0.18 m | Holgura del chasis |
|---|---|---|---|
| v2 sanidad + CBF | **0.1800 m** | **0/90** | 0.105 m |
| v3 radio + CBF | **0.1118 m** | **79/90** | **0.037 m** |

v2+CBF mantuvo el margen **exacto**, sin una sola violación. v3+CBF lo violó
en 79 de 90 agente-episodios, llegando a 0.1118 m.

**Causa probable: discretización.** El filtro decide cada 100 ms (dt del env)
y el robot recorre hasta `V_MAX · dt = 0.031 m` entre decisiones. Con la
política de v3 empujando de forma sostenida contra la restricción (70.2% de
pasos intervenidos, magnitud media 0.932) el sobrepaso se acumula entre
decisiones y el margen se erosiona.

**Consecuencia para el criterio operativo:** el conflicto política-filtro no
sólo cuesta liveness — también **erosiona la garantía de invarianza**, que es
lo único que el shield realmente promete. Un CBF con conflicto alto no es
"seguro pero lento": es menos seguro de lo que su formulación sugiere.

**Lo que salvó el caso:** la holgura con que se dimensionó el margen
(0.075 de chasis + 0.05 de punto de mira + 0.031 de desplazamiento entre
decisiones) fue lo que evitó el contacto físico. A 0.1118 m el chasis quedó a
**3.7 cm de tocar** la pared. Con un margen dimensionado más ajustado, la
violación habría terminado en colisión.

---

## Criterio operativo: el conflicto política-filtro predice los atascos

La fracción de pasos-agente en que el CBF modifica la acción correlaciona
fuertemente con la tasa de atascos, por episodio:

| Configuración | r (n=18) | Fracción intervenida media |
|---|---|---|
| v2 sanidad + CBF | **+0.905** | 0.371 |
| v3 radio + CBF | +0.674 | 0.702 |

En v2+CBF el ordenamiento es casi monótono: semilla 420005 con 0.190 de
fracción → 1 atascado; 420000 con 0.710 → 4 atascados. En v3+CBF la
correlación es más débil porque el conflicto está saturado (mínimo 0.505) y
queda poco rango para discriminar.

**Umbral práctico:** si al activar el CBF la fracción intervenida supera
**~0.5**, la política y el filtro están en conflicto y los atascos serán
altos. Es un test barato — un lote headless de 3 minutos — para descartar
políticas candidatas sin correr experimentos largos.

---

## Lecciones transversales

1. **Selección de checkpoint.** Nos mordió dos veces (v2 picó en 170k, v3 λ=3
   colapsó en los últimos 40k). Cualquier estudio Optuna debe usar
   `best_model_save_path` con ≥20 episodios de evaluación, o sesgará la
   búsqueda hacia hiperparámetros que simplemente degradan menos al final.

2. **Comparabilidad de métricas entre versiones.** `frac_contacto` se dispara
   cuando el centro cruza el límite del dominio, y ese límite es `[0,W]` en v2
   y `[r,W−r]` en v3/v4. Las coberturas de Python tampoco son comparables
   entre versiones, porque cada una se evalúa en su propia dinámica de borde.
   **La única comparación limpia es la tabla de Webots**, donde las cinco
   configuraciones corren en la misma física.

3. **Umbral de colisión.** `0.15 m` entre centros es el contacto físico de los
   chasis (radio 0.075 c/u) y es el `D_SAFE` del env: es el umbral con el que
   se midieron todas las métricas previas, y por lo tanto el comparable.
   `0.22 m` es el margen operativo de la metodología de tesis (~7 cm de
   holgura) y se reporta como columna adicional.

4. **El gap no se cerró por reentrenamiento.** Las tres variantes de dinámica
   de borde (v2, v3, v4) dan entre 56.7% y 94.4% de atascos en física real. Lo
   único que bajó la tasa fue el filtro de ejecución. Es un resultado negativo
   informativo: justifica el enfoque de safety shield para la fase física.

---

## Puente al Robotat — capa de abstracción y cliente físico

Objetivo: escribir y **probar** todo el código de despliegue físico sin
hardware, de modo que en el laboratorio lo único no ejercitado sea el
hardware mismo. Documentación operativa completa en `README_ROBOTAT.md`.

### Fase 1 — Capa de abstracción (regresión cero)

Tres `Protocol` en `interfaces.py` —`FuentePoses`, `CanalActuacion`,
`EntornoEjecucion`— y los adaptadores de Webots en `adaptadores_webots.py`.
El lazo de control quedó desacoplado de Webots sin cambiar un número.

Dos decisiones que valen la pena registrar:

1. **`leer_poses()` devuelve un flujo en orden de llegada, no un dict.** Una
   fuente entrega mediciones; decidir cuáles valen es política del
   consumidor. Además la degradación de pose (Exp F/H) consume el RNG una vez
   por medición, así que deduplicar en la fuente podría alterar ese consumo.
2. **`reposicionar()` lanza `NotImplementedError` en el Robotat**, no es un
   no-op. Un no-op silencioso dejaría al coordinador creyendo que los robots
   están en las poses iniciales del episodio mientras siguen donde quedaron.

### Fase 2 — Cliente del Robotat, simulador y verificación

Relevamiento de `robotat/*.m`, y luego cliente propio: `config_robotat.py`,
`protocolo_robotat.py`, `adaptadores_robotat.py`, `simulador_robotat.py`,
`verificar_mapeo_ids.py`, `lanzar_robotat.py`, con 64 pruebas.

**Hallazgos del relevamiento que cambian el diseño:**

- **El orden de ruedas del Robotat es el opuesto al nuestro.**
  `set_wheel_velocities(robot, dphiL, dphiR)` recibe la izquierda primero;
  nuestro modelo diferencial produce `(φ̇_R, φ̇_L)`. Aislado en un único punto
  de conversión, con prueba de mutación que introduce las dos inversiones
  posibles y confirma que la suite las detecta (4 y 3 fallos).
- **`force_stop` es byte a byte idéntico a `set_wheel_velocities(r,0,0)`**:
  misma cola TCP, sin prioridad. Si el enlace se cae, el robot conserva su
  última orden. **La parada por software no es una parada de emergencia**, y
  está demostrado con una prueba donde el robot con el enlace caído sigue
  girando mientras los demás frenan.
- **Dos espacios de IDs sin correspondencia declarada** (marcadores 1–100,
  robots 0–19). Un mapeo cruzado no falla: se comporta mal, de forma
  indistinguible de "la política no sirve".
  `verificar_mapeo_ids.py` lo comprueba girando un robot a la vez, y está a
  su vez verificado contra un simulador con mapeo permutado.
- **El cable es big-endian** (el original hace `fliplr` sobre el typecast
  little-endian de MATLAB), y la respuesta de poses es agente-major (el
  `reshape` de MATLAB es column-major).
- **Heading por `atan2` directo, no por Euler completo.** `q2eul` emite
  warning en la singularidad y devuelve un valor igual; acá se extrae el yaw
  con `atan2(2(qw·qz+qx·qy), 1−2(qy²+qz²))` y se valida la inclinación del
  cuerpo, que es la comprobación que reemplaza al warning.

**Calibración: cinco parámetros que no se pueden deducir del código.**
Escala de posición, marco del laboratorio, offset de heading, geometría de
rueda y mapeo de IDs están marcados `NO_VERIFICADO`, se imprimen al arrancar
y `lanzar_robotat.py` **se niega a correr** mientras alguno siga sin medir.
Los procedimientos están en el README §C1–C5.

### Contraste con el material del laboratorio (MT3005 lab 11)

El controlador de Webots del lab y su gemelo para el robot real
(`pololu3pi_controller.m` y `laboratorio11.m`) confirman tres cosas y
aportan una cuarta que no teníamos.

**(a) Los signos de motor son la convención del modelo, no un parche.** El
controlador de Webots del lab hace
`wb_motor_set_velocity(motor, -rpm2rads(...))` con el comentario textual
*"La inversión de signo y la conversión a rad/s son específicas de la
simulación (en el robot real se envían las rpm directamente)"*. Eso valida
nuestros `SIGNO_MOTOR_1 = SIGNO_MOTOR_2 = -1` en Webots y, sobre todo, deja
claro que **no van al cliente del Robotat**: aplicarlos ahí pondría a los
cinco robots en reversa, con un enjambre que se comportaría de forma
coherente pero equivocada. Verificado que `protocolo_robotat.py` y
`adaptadores_robotat.py` no los referencian, con una guardia estática cuya
detección se comprobó por mutación.

**(b) Tres semiejes en circulación**, cada uno correcto en su dominio:
0.0700 m (nuestro proto de Webots, anchors ±0.07), 0.0412 m (proto del
lab11), 0.0480 m (robot real, `laboratorio11.m`). Y dos radios: el modelo de
Webots del lab usa 32 mm de RADIO donde el robot físico tiene 32 mm de
DIÁMETRO — el propio archivo lo aclara. Documentado en los dos lados.

**(c) La fórmula de heading desde el compass coincide.** Verificada contra
`pololu3pi_controller.m`:115-116 a 8.9e-16 rad sobre 721 ángulos, con el
Compass montado igual en ambos mundos. Detalle no obvio: la línea 116 no
sólo envuelve, envuelve **−bearing**; con la fórmula del `bearing` sola las
dos quedan opuestas.

**(d) HALLAZGO NUEVO — la caja de acciones de la política es mucho más
rápida que lo validado en estos robots.** Con la geometría real:

| Caso | rpm pico | vs. cap del lab (200) |
|---|---|---|
| nuestro: avance V_MAX = 0.31 m/s | 185.0 | 0.93× |
| nuestro: giro Ω_MAX = 6.28 rad/s | 180.0 | 0.90× |
| **nuestro: peor combinación** | **365.0** | **1.83×** |
| lab real: peor combinación | 70.4 | 0.35× |

V_MAX es 4.43× la del lab, Ω_MAX 6.28×, y en rpm de rueda el peor caso es
5.18×. El lab además se impone un tope operativo de 200 rpm que no está en
el protocolo (la función satura a 400), y su versión de Webots usa 10× más
velocidad nominal y el doble de ganancia angular que su gemelo real
(v0 0.6 vs 0.06 m/s, kpO 4.0 vs 2.0). El motivo declarado es el **lag
inalámbrico**.

Importa distinguir ejes: el Exp H midió tolerancia a 300 ms de retardo en
las POSES —latencia del lazo de decisión—, mientras que el lag del que habla
el lab está en el camino de ACTUACIÓN. **El Exp H no autoriza estas
velocidades.**

No se cambió V_MAX: la política se entrenó con esa cota y aparece en la
normalización de las observaciones. La rampa de arranque cubre los primeros
5 s a 91 rpm de pico, dentro del régimen del lab; qué hacer después es una
decisión abierta previa a la primera sesión completa.

**Antigüedad máxima de pose = 150 ms.** Es la mitad del margen que el Exp H
mostró tolerable (3 decisiones = 300 ms). Superado el umbral, el canal manda
(0,0) a ese agente. El corte va en la frontera, no en el lazo de decisión:
la política de "usá la última pose conocida" es la que validaron los Exp F y
H y no se toca.

**Arranque seguro (§S2 del README).** La contraparte de §S1: si el mapeo de
IDs o el marco están mal calibrados, el primer comando manda un robot a
velocidad plena en la dirección equivocada. Dos defensas, activas por
defecto:

- *Chequeo geométrico antes de la primera acción*: las N poses presentes y
  válidas, dentro de la arena, separadas ≥ 0.15 m (el `D_SAFE` del env) y a
  ≥ 0.20 m de cualquier pared. La última condición sale directo del Exp A:
  la política no sabe despegarse de un muro, y el escape sólo actúa cuando
  el CBF ya está saturado, así que arrancar pegado a la pared es arrancar en
  el único estado del que el sistema no se recupera solo. Si falla, no
  arranca y **nombra al agente y el motivo**.
- *Rampa de velocidad*: 25 % de V_MAX durante las primeras 50 decisiones
  (5 s). A 0.078 m/s un robot avanza 8 cm en el segundo de reacción de una
  persona, contra 31 cm a velocidad plena.

El escalado va en la frontera, no en el lazo, y **no rompe las garantías**:
si `cᵀu ≥ −α·h` con `h ≥ 0`, entonces `cᵀ(k·u) ≥ −α·h` para todo
`k ∈ (0,1]`, así que reducir uniformemente nunca viola una barrera que ya se
satisfacía; y la ley de máximo ascenso del escape da `ḣ = V|a| + ℓa·Ω|b| > 0`,
que con `k > 0` sigue siendo positiva. Lo que sí queda desalineado —y se
acepta explícitamente— es que el env recibe la acción sin escalar, de modo
que durante la rampa las componentes v/ω de la observación son optimistas;
las posiciones no, porque entran por `inyectar_poses_externas`.

**Consulta de poses configurable.** `MODO_CONSULTA_POSES ∈ {lote,
individual}`. En "lote" se piden los N marcadores de una (lo que hace el
código de referencia); en "individual", uno por petición. La segunda existe
porque si el servidor responde con MENOS FILAS ante un marcador ocluido, el
cliente no puede saber qué fila es de quién y debe descartar la respuesta
entera: un marcador tapado dejaría sin pose al enjambre completo. Default
"lote" hasta que el encargado del Robotat conteste; el cambio es una línea
de configuración y ambos modos están probados.

**Inyección de adaptadores en el coordinador.** `CoordinadorEnjambre` los
acepta por constructor; sin argumentos construye los de Webots y se comporta
igual que antes. Verificado contra la celda σ=0/ret=0 del barrido del Exp H:
**0 diferencias en 2088 celdas** (18 semillas × 116 columnas).

Dos detalles que salieron de esa verificación:

- **Trazabilidad del nombre del CSV.** Dependía sólo de N y de los flags, así
  que dos configuraciones distintas escribían el mismo archivo. El riesgo se
  materializó en esta sesión: una corrida con σ=10 mm había pisado el CSV de
  σ=0, y sólo se detectó al comparar la columna `sigma_pos_mm` de una
  comparación que parecía dar 499 diferencias. Ahora el nombre codifica
  entorno, σ y retardo; los CSV ya citados conservan su nombre y ninguna
  corrida nueva los toca.
- El coordinador **consulta** `entorno.soporta_reposicionar` en vez de
  llamar y atrapar la excepción: tragar el `NotImplementedError` haría
  indistinguible "este entorno no teletransporta" de "el teletransporte
  falló".

**Tres errores que las pruebas encontraron**, los tres del tipo que no falla
sino que se comporta mal:

(a) la fuente sellaba las mediciones con un contador que nunca avanzaba, de
modo que la antigüedad crecía linealmente con el tick y a los 20 s el
coordinador creía decidir con poses de hace 20 s;
(b) tras un cierre limpio, el `atexit` reimprimía la alarma de "cortar
alimentación a mano" sin motivo, que es exactamente cómo una alarma real
deja de tomarse en serio;
(c) una prueba mutaba el objeto `FallasSimulador` compartido como atributo
de clase, y el efecto —dejar sin marcador al agente 2— aparecía en una clase
de pruebas posterior, sin relación aparente. Se arregló copiando la
configuración de fallos en cada `setUp`, que cierra la clase entera de fuga,
no sólo este caso.

Los tres tienen guardia de regresión.

**Nota de método.** El chequeo geométrico usa 1 mm de tolerancia. Sin ella el
umbral es un filo de navaja: `0.20 + 0.15 − 0.20` da `0.14999999999999997`, y
una pose exactamente en el límite se rechazaba con el mensaje "0.150 m
(mínimo 0.15 m)", que parece falsa alarma. Hay una prueba que confirma que la
tolerancia no desafila el chequeo (1 cm por debajo se sigue rechazando).

**Qué queda sin probar hasta tener hardware:** que el servidor real hable el
formato relevado; qué devuelve con un marcador ocluido; unidades, marco,
heading, geometría y mapeo reales; y **toda la dinámica** —derrape, retardo
del actuador, zona muerta, batería—. El simulador usa la misma cinemática
ideal que el env, así que nada de lo probado acá dice nada sobre el gap
sim-to-real: lo único validado es el código de interfaz.

### Herramienta de sesión de laboratorio (`sesion_robotat.py`)

Principio: el tiempo de laboratorio es para CAPTURAR, no para analizar. Todo
a disco, veredicto automático por etapa, ningún juicio pedido en el momento.

Seis etapas de calibración (conexión y parada, correspondencia de IDs, marco
y escala, rumbo, latencias, marcador ocluido) más una sesión de política con
barrido progresivo de régimen. Las sesiones de enjambre y evaluación quedan
reconocidas por el despachador pero sin implementar: su diseño depende de lo
que arrojen las dos primeras. 38 pruebas contra el simulador.

**Tres decisiones de medición que evitan reportar números falsos:**

1. **El ajuste de marco con dos puntos tiene residuo cero por construcción**,
   y la etapa lo dice en vez de mostrarlo como validación. Recién con tres
   puntos el RMS informa algo. Con dos puntos se obtienen escala, rotación y
   traslación por ajuste de similitud, que es todo lo que hace falta.
2. **La latencia de actuación descuenta dos cosas**: la latencia de
   percepción y el tiempo puramente geométrico de recorrer el umbral de
   detección (3 mm a 0.05 m/s = 60 ms). Sin el segundo descuento se
   reportaría como retardo algo que es sólo el tamaño del umbral. Y si el
   resultado cae por debajo del doble del período de muestreo, la etapa
   declara "no resoluble" en lugar de dar un número.
3. **`SIN DATOS` no es `INESTABLE`.** El veredicto por escalón distingue "el
   seguimiento fue malo" de "no hubo distancia comandada suficiente para
   medir el seguimiento". La primera versión daba INESTABLE cuando el
   escalón caía entero dentro de la rampa de arranque: un cero por ausencia
   de medición presentado como evidencia de inestabilidad.

**Seguimiento por distancias acumuladas, no por cociente instantáneo.** A
factor 0.20 con la rampa activa, el desplazamiento por decisión es ~1 mm,
del orden del ruido de captura; el cociente paso a paso daba 0. El cociente
de recorridos totales sobre el escalón da 1.00 en el simulador ideal, que es
lo correcto.

**Escalones del barrido de régimen**, elegidos para responder la pregunta
abierta de §C4b y no por comodidad: 0.20 (≈ el peor caso del laboratorio,
73 rpm), 0.30, 0.40, **0.55 (= exactamente el tope operativo de 200 rpm del
lab)**, 0.75, 1.00 (caja completa, 365 rpm). Desde 0.55 el aborto por rpm
puede dispararse por construcción; que ocurra es dato, no falla.

**Cuatro abortos automáticos** —rpm, fuera del área, pose vencida, sin
desplazamiento— probados uno por uno contra el simulador. Al probarlos
apareció que **están escalonados**: una pose implausible se rechaza por
rango, el agente se queda sin pose y salta el aborto por antigüedad ANTES de
que el chequeo de área vea nada. El aborto por área cubre las poses válidas
pero fuera de la arena. Hay una prueba para cada rama.

**Defecto de usabilidad que encontraron las pruebas:** `--etapa N` con N > 0
—repetir una sola etapa, que es un caso de uso explícito— fallaba con un
`AttributeError` sobre `None` porque las conexiones se abrían en la etapa 0.
Ahora cualquier etapa abre lo que necesita.

**Gancho de observación en el coordinador.** Para registrar acción nominal,
tras escape y ejecutada por separado, se agregó un callback opcional que
`_decidir_y_actuar` invoca sólo si está instalado. Con `None` —todos los
lotes de los Exp A–H— el costo es un `is not None` por agente y por decisión.
Verificado contra la celda σ=0/ret=0 del Exp H: **0 diferencias en 2088
celdas**.

---

## Primera conexión real al Robotat (2026-08-21) — hallazgo de protocolo

Primera sesión con hardware real. `robotat_connect.m` confirma el endpoint
del servidor de poses byte a byte contra `config_robotat` (`192.168.50.200:
1883`), así que esa hipótesis quedó descartada por lectura, sin gastar tiempo
de laboratorio.

**Síntoma:** la etapa 0 de `sesion_robotat.py` conectaba sin problema al
servidor de poses y al robot, pero **la primera consulta de pose después de
conectar** fallaba con "respuesta no parseable" (200-203 B). Las 19
consultas siguientes de la misma corrida funcionaban. Reproducido
**dos veces seguidas** contra el robot 1 físico — no era ruido.

**Causa, verificada por lectura del código de referencia antes de
afirmarla:** `robotat_get_pose.m` hace `read(tcp_obj)` como **primera línea
de la función**, antes de escribir la petición. En un `tcpclient` de MATLAB,
`read()` sin argumentos vacía el buffer de entrada. El código de referencia
se está defendiendo de algo: el servidor aparentemente empuja datos (el
candidato más probable, el último frame de captura en caché) apenas acepta
la conexión, sin que se los pidan. Nuestra reimplementación en Python omitía
ese vaciado, así que la primera consulta leía esa basura pegada delante de
la respuesta real; como basura + JSON válido no es JSON válido, el parseo
nunca converge y expira por timeout.

**Fix:** `descartar_buffer_pendiente(sock)` en `adaptadores_robotat.py` —
usa `select` con timeout 0 para no bloquear cuando el buffer ya está vacío
(el caso normal en cada tick a 100 Hz), y descarta lo que encuentre antes de
mandar. Aplicado en los DOS clientes que hablan el protocolo de poses:
`FuentePosesRobotat._un_viaje` (el cliente real de despliegue — este hueco
también lo tenía, no sólo la herramienta de diagnóstico) y
`ClientePosesCrudo.consultar` (`sesion_robotat.py`). Se cuenta y se expone
en `resumen()`: si el descarte vuelve a aparecer más allá de la primera
consulta tras conectar, es evidencia de que la causa no es sólo el saludo
inicial del servidor.

**Bug introducido y corregido en el mismo pase:** la primera versión del fix
llamaba a `descartar_buffer_pendiente` FUERA del `try/except OSError` que ya
maneja la pérdida de conexión. Lo agarró la prueba que simula deliberadamente
una caída de conexión (`PruebaCaidaDePoses`): con el socket muriendo,
`select` puede marcarlo "listo para leer" y el `recv` del descarte lanza
`ConnectionAbortedError` sin capturar, en vez de caer en el camino normal de
"conexión perdida". Se movió el descarte adentro del `try` existente en
ambos clientes.

**Deuda de proceso, reconocida:** el envoltorio `ConexionImposible` (mensaje
de diagnóstico accionable en vez de traceback crudo, agregado unos turnos
antes en la misma sesión de laboratorio) se probó manualmente con un
`print()` pero **no se corrió la batería completa** después de agregarlo.
Quedó una prueba (`PruebaEtapa0RobotSordo.test_no_conecta`) esperando el tipo
de excepción viejo, y no se detectó hasta esta ronda. Corregida, y se agregó
una segunda prueba que ejercita el camino real de uso (`--etapa 0` vía
`correr_calibracion`) para que un cambio de este tipo no vuelva a pasar
inadvertido.

5 pruebas nuevas contra `socket.socketpair()` (sin red): descarta lo
pendiente y cuenta los bytes, no bloquea con el buffer vacío, una segunda
llamada no encuentra nada, reproduce el patrón exacto del laboratorio
(basura pegada delante de una respuesta real, en la misma conexión), y una
guardia negativa que confirma que sin el fix el parseo se rompe de verdad.
Batería completa tras el fix: **133/133** (48 + 46 + 39).

**Artefactos:** `adaptadores_robotat.descartar_buffer_pendiente`,
`test_robotat.PruebaDescartarBufferPendiente` (5 pruebas),
`test_sesion_robotat.PruebaEtapa0RobotSordo` (2 pruebas).

---

## Etapa 1 rediseñada: escaneo de candidatos en un solo giro (2026-08-21)

Durante la primera sesión de laboratorio, la etapa 1 pedía un `--marcador`
fijo y sólo comprobaba ESE candidato por giro. Con el robot 2 se probaron
71 (equivocado: es `meta_id` de `laboratorio11.m`, no el marcador de ningún
robot) y 67 (sin justificación clara), ambos con veredicto `NADIE`. El
consejo previo de probar "3" mezclaba sin darse cuenta dos hipótesis de
convención distintas — error propio, corregido antes de gastar más giros.

**Las dos hipótesis, ninguna verificada:**
- **A** — `laboratorio11.m` línea 131: `robotat_get_pose(robotat, robot_no,
  ...)` usa `robot_no` DIRECTAMENTE como ID de marcador. Robot 2 → marcador 2.
- **B** — `config_robotat.MAPEO_AGENTES` (default nuestro, sin medir): robot
  *i* → marcador *i+1*. Robot 2 → marcador 3.

Además había un defecto real en la herramienta: la etapa 1 imprimía
"marcadores del mapeo configurado: [1, 2, 3, 4, 5, 71]" dando la impresión
de que se vigilaban seis candidatos, cuando `verificar_mapeo_ids.verificar`
sólo consultaba el que venía por `--marcador`. La lista impresa nunca se
usaba para nada. Explica por qué adivinar un número a la vez parecía la
única vía.

**Rediseño: `escanear_candidatos(id_robot, candidatos)`.** Un solo giro
físico, poses ANTES y DESPUÉS para TODOS los candidatos a la vez, con
**consultas individuales** (no en lote): no sabemos todavía —la etapa 5 lo
mide, y no se corrió aún contra el Robotat real— si el servidor responde
con menos filas ante un marcador ausente; una petición en lote con un
candidato malo se caería entera. Con consultas individuales, un candidato
sin lectura no afecta a los demás. `informe_escaneo` da el veredicto: un
único candidato con Δyaw > 17° → identificado; ninguno → `NADIE`; más de
uno → `AMBIGUO`.

**Candidatos por defecto**, sin asumir cuál hipótesis rige: `1–12` (rango de
`marker_offsets` del lab) ∪ `{71}` (meta) ∪ `{id_robot, id_robot+1}` (las
dos hipótesis A y B) ∪ `{--marcador}` si se pasó uno fuera de ese rango.
`--candidatos` permite una lista explícita.

**14 pruebas nuevas** contra el simulador: identifica el marcador correcto
entre varios candidatos sin que `--marcador` lo delate de antemano; un
candidato "faltante" (modo que la etapa 5 podría confirmar como el real) no
arruina la lectura de los demás — probado tanto en `escanear_candidatos`
directo como en la etapa completa; `informe_escaneo` con datos sintéticos
(un giro, ninguno, ambiguo, candidatos sin lectura no cuentan como giro);
`_candidatos_por_defecto` cubre ambas hipótesis y rechaza IDs fuera del
rango válido del protocolo (1–100). Batería completa: **146/146** (48 + 46
+ 52).

**Pendiente de verificar en el próximo giro:** cuál marcador mueve
realmente el robot 2, y si la convención resultante (A, B, o ninguna) se
sostiene para el resto de los robots.

---

## Segundo hallazgo de la etapa 1 rediseñada: conexión nueva por candidato rompe contra hardware real (2026-08-21, misma sesión)

Primer uso real del escaneo (robot 2, 13 candidatos: 1–12 más 71): **los 13
volvieron "sin lectura"**, incluido el marcador 71 — que la etapa 0, minutos
antes, había leído **20/20 veces** por una conexión persistente.

Ese dato descarta de plano "el marcador no existe": el servidor lo tenía
segundos atrás. La única variable que cambió es CÓMO se consultaba: la
primera versión de `escanear_candidatos` abría una conexión TCP nueva por
cada consulta (`_pose_individual`), 2·N conexiones para N candidatos —26 en
~1.5 s para 13 candidatos. El simulador (Python sin límite de conexiones
concurrentes) nunca mostró el problema; el servidor embebido del Robotat, al
parecer, no tolera esa cadencia de reconexión.

**Fix:** `_ClientePosesIndividual`, una conexión persistente para todo el
escaneo, con consultas individuales (una por marcador, no en lote) sobre esa
misma conexión — se conserva la propiedad de seguridad que motivó las
consultas de a una (un candidato ausente no arruina a los demás) sin volver
a abrir sockets. Aplicado también `descartar_buffer_pendiente` (el mismo
mecanismo del hallazgo anterior) antes de cada consulta individual, y en
`_ClientePoses.headings()` del camino original de `verificar()`, por
consistencia — mismo tipo de riesgo, aunque no exercitado en este episodio.

**Prueba de regresión:** se agregó un contador
`SimuladorRobotat.conexiones_poses_aceptadas` y una prueba que exige
`nuevas == 1` para 6 candidatos escaneados — con la versión vieja hubiera
dado 12. El propio simulador no puede reproducir el síntoma original (acepta
conexiones sin límite), así que la prueba no verifica que el escaneo
funcione, verifica que usa el PATRÓN de conexión correcto, que es lo que
realmente se rompió.

Batería completa: **147/147** (48 + 46 + 53).

**Aprendizaje declarado, no sólo para este caso:** el simulador modela fielmente
el protocolo (formato, validación, fallos de datos) pero NO modela límites
de recursos del servidor embebido real —conexiones concurrentes, cadencia de
reconexión. Dos hallazgos de la misma sesión de laboratorio (el descarte de
buffer y éste) fueron cosas que "pasan los 147 tests" no podía haber
detectado por sí solo, porque el simulador no las modelaba. El patrón
correcto —una conexión persistente, reusada— ya lo seguían
`FuentePosesRobotat`, `ClientePosesCrudo` y `_ClientePoses`; sólo
`escanear_candidatos` se apartó de él, y fue el único que falló contra
hardware real.

**Pendiente:** repetir el escaneo del robot 2 con la versión corregida.

---

## Corrección conceptual del operador: los marcadores no son una propiedad del robot (2026-08-21/22)

El operador corrigió un modelo mental equivocado antes de que se propagara
más: **los marcadores del Robotat son pegatinas reflectantes que se colocan
a mano y nunca conservan su posición** — se pueden mover entre robots o
remontar en cualquier momento. No hay convención `id_marcador ↔ id_robot`
que descubrir y generalizar; el consejo del turno anterior ("confirmá la
convención con otro robot, corregí `MAPEO_AGENTES` entero") estaba mal —
mezclaba una coincidencia de una sesión con una regla general.

Consecuencia de diseño: `calibracion_medida.json` guardaba `id_marcador`
(y `offset_heading_rad`, que depende de cómo está montada la constelación)
y los **reutilizaba en sesiones futuras sin remedir** — exactamente lo
contrario de lo que el operador acaba de confirmar que hace falta.

**Fix, en `calibracion_sesion.py`:**

- `CAMPOS_FRAGILES = {"id_marcador", "offset_heading_rad"}` — dependen de
  dónde está pegada la pegatina AHORA, no del hardware ni del sistema de
  captura (escala/marco SÍ son estables entre sesiones: calibración de los
  técnicos, no de dónde está una pegatina).
- Cada campo guardado lleva sello `_medido_en[campo]` con fecha y hora.
- `campos_fragiles_desactualizados()`: un campo frágil presente pero
  medido en fecha distinta de HOY cuenta como desactualizado. Fecha
  calendario como proxy de "sesión física" — documentado como heurística
  conservadora, imperfecta pero mucho más segura que confiar indefinido.
- `aplicar_a_config()` NO aplica campos frágiles desactualizados: el
  mapeo/offset quedan en el default de `config_robotat`, con su bandera
  `*_NO_VERIFICADO` intacta, así que `lanzar_robotat.chequeos_previos` ya
  los bloquea sin código nuevo — se reusó el mecanismo de gate existente.
- `correr_calibracion` bloquea las etapas 2/4/5 (que consultan
  `ctx.marcador` para MEDIR) si `id_marcador` está desactualizado: sin
  este chequeo medirían en silencio contra el marcador de otro robot y
  guardarían un número que parece válido sin serlo. La etapa 1 queda
  exenta —siempre remide de cero, nunca depende de `ctx.marcador` para
  funcionar— para no bloquearse a sí misma.
- `_candidatos_por_defecto` reescrito: ya no llama "hipótesis A/B" a
  `id_robot`/`id_robot+1`, son candidatos baratos de probar primero, no
  convenciones a confirmar.

**Bug preexistente encontrado al escribir la prueba de `aplicar_a_config`**
(no introducido en este cambio): `id_marcador` nunca se agregaba a la
lista `aplicados` que devuelve la función, ni siquiera cuando sí se
aplicaba al mapeo — `CAMPOS["id_marcador"]` tiene `atributo=None` (va por
la rama especial de `MAPEO_AGENTES`, no por el `setattr` genérico), y esa
rama nunca hacía el `.append()`. `_preparar()` nunca lo mencionaba al
operador. Corregido.

**Segundo bug encontrado al verificar contra el archivo real de hoy:** el
`calibracion_medida.json` de la sesión de laboratorio se había escrito
ANTES de que existiera `_medido_en` — sólo tenía `_historial`. Sin
resguardo, `fecha_medicion` devolvía `None` para `id_marcador` (medido esa
misma tarde) y lo mostraba como "DE UNA SESIÓN ANTERIOR (None)", que
hubiera bloqueado al operador en medio de su propia sesión por un problema
de FORMATO del archivo, no por un dato viejo de verdad. Corregido: si
`_medido_en` no tiene el campo, `fecha_medicion` cae a la entrada más
reciente de `_historial` que lo haya guardado — recuperó correctamente
`2026-08-21` para `id_marcador`. (Al verificar esto se confirmó además que
el reloj del sistema ya había avanzado a 2026-08-22: el aviso de
"desactualizado" que se ve ahora es correcto y esperado, un día calendario
después de la medición, no un artefacto.)

18 pruebas nuevas: frescura de campos frágiles (recién medido, medido
ayer, offset de heading también frágil, campos NO frágiles nunca se
marcan), `aplicar_a_config` con/sin desactualización, `faltantes()` trata
lo desactualizado como faltante, `resumen()` lo marca, remedir hoy limpia
la marca, el archivo de formato viejo (sin `_medido_en`) recupera la fecha
del `_historial`, y la secuencia de `correr_calibracion` bloqueando
2/4/5 con marcador viejo mientras deja pasar la etapa 1 y respeta
`--forzar`. Batería completa: **160/160** (48 + 46 + 66).

---

## Corrección final del operador y arreglo de fondo (2026-08-22)

El operador precisó su corrección anterior: hay **dos tipos** de marcador.
Los **sueltos** (el de meta) se mueven a mano, como ya se había establecido.
Los **montados en el chasis de cada robot** son distintos: fijos y
permanentes — **robot N trae siempre el marcador N**, confirmado para
robots 1–16. Coincide exactamente con el dato real ya medido (robot 2 →
marcador 2). Ante la pregunta explícita sobre el robot 0 (marcador "0" es
inválido para el protocolo), el operador confirmó: **la numeración arranca
en 1; el robot 0 del software no se usa.**

### Cambios de fondo

- **`config_robotat.MAPEO_AGENTES`**: la fórmula pasa de `marcador = robot+1`
  (suposición nunca medida) a `marcador = robot` (confirmado). El swarm por
  defecto pasa de robots 0–4 a **1–5**, evitando el caso sin resolver del
  robot 0. Nueva función `marcador_fijo_de_robot(id_robot)`, que lanza
  explícitamente para `id_robot=0` o fuera de 1–16 en vez de devolver un
  valor adivinado. `MAPEO_NO_VERIFICADO` pasa a `False` por defecto: ya no
  es una suposición, es un hecho de ingeniería conocido.
- **`calibracion_sesion.CAMPOS_FRAGILES`**: `id_marcador` sale del
  conjunto — ya no necesita remedirse cada sesión. `offset_heading_rad`
  se mantiene, con una salvedad declarada: si la constelación está tan
  fija como su ID, es razonable esperar que la orientación de montaje
  también lo sea, pero eso es una inferencia propia, no algo confirmado
  explícitamente, así que se mantiene el criterio conservador.
- **La etapa 1 pasa de obligatoria a opcional**: el bloqueo de las etapas
  2/4/5 por `id_marcador` desactualizado se retiró (ya no puede
  dispararse). La etapa sigue disponible como chequeo de seguridad.
- **`sesion_robotat.main()`**: al resolver el marcador por defecto sin
  `--marcador` explícito, ahora usa `marcador_fijo_de_robot(id_robot)` —
  del ROBOT ELEGIDO por `--robot`, no de `MAPEO_AGENTES[0]` a ciegas.

### Bug serio encontrado al revisar el flujo completo, no relacionado con lo anterior

**`sesion_politica()` ignoraba `ctx.id_robot`/`ctx.marcador` por completo.**
`construir(1)` arma el canal a partir de `cfg.MAPEO_AGENTES[0]`
directamente; nada en `sesion_politica()` lo sincronizaba con lo que el
operador eligió por `--robot`. Un operador corriendo
`--sesion politica --robot 3` habría ejecutado el barrido de velocidad **en
silencio sobre el robot que quedara en `MAPEO_AGENTES[0]`** —una
calibración persistida de otro robot— y no sobre el robot 3 que creía estar
mirando. Exactamente el tipo de peligro que toda la sesión de arranque
seguro busca evitar, por una vía que ese chequeo no cubre. Corregido:
`sesion_politica()` fuerza `MAPEO_AGENTES[0] = (ctx.marcador, ctx.id_robot)`
como último paso antes de `construir()`, y lo imprime explícitamente.
Prueba de regresión: `MAPEO_AGENTES[0]` apuntando a un robot inexistente
(99) en el simulador, y la sesión debe controlar igual al robot correcto.

### Bug de cascada en la batería de pruebas

Al corregir `MAPEO_AGENTES` (robots 0-4 → 1-5), tres pruebas que
**hardcodeaban IDs de robot literales** (`{0: 2, 1: 1, 2: 3}`,
`robots_que_caen_tras={1: 2}`) en vez de derivarlos de
`cfg.MAPEO_AGENTES` quedaron desalineadas con lo que el canal real resuelve
internamente, y fallaban en `setUp()`. Como unittest **no llama a
`tearDown()`** cuando `setUp()` lanza, el simulador de esas pruebas quedaba
corriendo en segundo plano, con hilos zombis ocupando los mismos puertos
que usan las pruebas siguientes — de ahí una cascada de ~15 fallos
aparentemente inconexos (timeouts, RPM que no llegaban a cero, respuestas
mezcladas). Corregido en las tres pruebas (IDs derivados de
`cfg.MAPEO_AGENTES`, no hardcodeados) y además `PruebaMapeoCruzado.setUp`
ahora limpia su simulador en un `except` antes de relanzar, para que un
fallo de setup futuro no vuelva a envenenar el resto de la batería.

### Cuelgue real en la batería de sesión

`PruebaSesionSeNiegaConMarcadorViejo` probaba el bloqueo de la etapa 2 por
`id_marcador` desactualizado — comportamiento que ya no existe. Sin el
bloqueo, la etapa 2 corría **de verdad** contra un operador simulado sin
respuestas preparadas para sus prompts, y `leer_float()` quedaba esperando
un número válido indefinidamente (nunca sale del `while True` con un
`""` repetido). Clase eliminada; su premisa dejó de ser válida.
`PruebaCamposFragiles` reescrita para usar `offset_heading_rad` como sujeto
(el único campo que sigue siendo frágil) en vez de `id_marcador`.

Batería completa: **158/158** (48 + 46 + 64).

---

## Decisión: consultar poses una vez por decisión, no por tick (2026-08-22)

El asesor cuestionó dos cosas del cliente del Robotat: si cada agente
tenía su propio "objeto TCP", y si el protocolo de comunicación merecía
depurarse porque "la información que se manda sí es mucha". Verificado en
vez de asumido:

- **"Un objeto TCP por agente"**: ya estaba hecho para los motores desde
  la Fase 2 (`CanalActuacionRobotat` mantiene un socket por robot). No
  aplica igual a las poses — hay un solo servidor de captura para todo el
  enjambre, no un endpoint por robot.
- **"La información es mucha"**: medido y confirmado. `leer_poses()` se
  llamaba una vez por TICK (100 Hz, heredado del adaptador de Webots,
  donde drenar es casi gratis) cuando el lazo sólo DECIDE 10 veces por
  segundo (`DT_ENV = 0.1`). 9 de cada 10 consultas no alimentaban ninguna
  acción: 100 round-trips TCP reales por segundo, 45.9 KB/s, contra un
  servidor que esta misma sesión demostró DOS VECES que no es robusto bajo
  carga (el hallazgo del buffer con datos empujados sin pedir, y el de las
  26 reconexiones en 1.5 s durante el escaneo de marcador).

**Decisión: opción A — 10 Hz, una consulta por decisión.** La razón
principal no es el ancho de banda: es que sostener 100 consultas/s en una
máquina compartida es un riesgo de robustez innecesario para información
que nadie consume. La opción de medir primero a 100 Hz se descartó porque
la medición ES el riesgo — si el servidor se degrada bajo esa carga, no se
obtiene un número limpio, se pierde una sesión depurando por qué las
poses llegan mal (ya pasó dos veces). Un punto intermedio (20–30 Hz) no se
justifica: conservaría frescura intra-decisión que la política no
consume, porque sólo mira la pose en el instante de decidir.

### Implementación

**`HZ_CONSULTA_POSES` en `config_robotat.py`**, parámetro ajustable por
sesión sin tocar código (default 10.0, igual a la tasa de decisión).
`FuentePosesRobotat` sigue recibiendo `leer_poses()` una vez por tick —
`_avanzar` no cambia, es código compartido con Webots— pero sólo hace un
round-trip real cada `intervalo_ticks` llamadas, calculado a partir de
`HZ_CONSULTA_POSES` y el timestep. Las llamadas intermedias devuelven `[]`
sin tocar la red; el coordinador ya sabe leer eso como "nada nuevo este
tick" (política de caché validada en Exp F/H, sin tocar).

**La consulta cae en el ÚLTIMO tick antes de cada decisión, no en
cualquiera.** Con `intervalo_ticks == pasos_por_decision` (el caso por
defecto), la aritmética modular del contador de ticks garantiza esto de
forma determinista para toda la duración de un episodio — sin depender de
sondeo por reloj de pared, que hubiera introducido deriva de fase. La pose
que usa `_decidir_y_actuar` tiene, como mucho, la antigüedad de un solo
ida y vuelta.

**Hallazgo al diseñar la alineación de fase:** `fuente.reiniciar()`
—documentado en `interfaces.py` para invalidar el estado acumulado al
empezar un episodio— **nunca se llamaba**, en ningún adaptador, desde que
existe la Fase 1. Sin esa llamada, el limitador de tasa heredaría hasta
`intervalo_ticks` llamadas de fase incorrecta de la etapa de espera de
poses tras cada reinicio de episodio (`TICKS_MAX_ESPERA_POSE = 20`, con
margen de sobra para absorberlo, pero sin necesidad de dejarlo así).
Se agregó la llamada en `_reiniciar_episodio`, en el mismo punto donde el
coordinador invalida su propio caché (`self._cache.clear()`) — los dos
pasos están documentados como el mismo paso del reinicio. Verificado que
no afecta a Webots: `FuentePosesWebots.reiniciar()` sólo limpia un
`_vistos` de diagnóstico que ningún otro método del coordinador consulta
(`agentes_faltantes()` tampoco se llama desde ningún lado); no toca RNG,
poses ni métricas.

**Etapa 4a ahora emite un veredicto explícito sobre el presupuesto**, no
sólo el número: p95 del round-trip contra el presupuesto de 100 ms por
decisión, con tres franjas (< 10 % holgado, 10–30 % vigilar, > 30 %
riesgoso → plan de contingencia). La etapa 4b (`ClientePosesCrudo`) nunca
pasó por el límite de tasa — sigue consultando al máximo régimen posible
sin necesidad de ningún ajuste.

**La sesión de política instrumenta el mismo presupuesto por decisión**
(consulta + transformación + inferencia + filtro + envío), cuenta
decisiones que lo superan, y lo reporta por escalón y en el resumen
final. Si ocurre de forma sistemática (> 20 % de una ventana de 10 s), el
mensaje es explícito: "invalida la corrida", no una anotación al margen.

**Plan de contingencia, deliberadamente NO implementado:** si el p95 real
resulta riesgoso, la salida no es volver a 100 Hz — es un hilo de sondeo
en segundo plano con el lazo leyendo de un caché sin bloquearse. Se decide
con el número medido en el laboratorio, no antes.

### Verificación

12 pruebas nuevas: que el límite omite la mayoría de las llamadas con la
aritmética exacta esperada (25 llamadas → 3 consultas reales, no 25);
que `reiniciar()` fuerza una consulta inmediata; que `intervalo_ticks` se
calcula bien para varios HZ; y la que de verdad importa —**contra el
`CoordinadorEnjambre` real, 8 decisiones cuestan exactamente 8 consultas,
no 80**, sin que ningún agente quede con pose vencida. Más las del
veredicto de presupuesto (etapa 4a y sesión de política), con latencia
inyectada suficiente para dispararlo y suficiente para no hacerlo.

La mayoría de las pruebas de protocolo existentes (`test_integracion_robotat.py`)
no querían el límite de tasa —prueban el cable, no el ritmo del
coordinador— así que se les dio una vía explícita para desactivarlo
(`hz_consulta_poses` de clase, vía el mismo parámetro público
`cfg.HZ_CONSULTA_POSES`), en vez de que el default de producción las
rompiera en silencio.

**Regresión en Webots (punto 5, obligatorio):** el único cambio a código
compartido fue la llamada a `fuente.reiniciar()`. Verificado contra la
celda σ=0/ret=0 del Exp H — ver resultado abajo.

Batería completa: **165/165** (48 + 50 + 67).

### Corrección de fondo, dato confirmado por el autor

`config_robotat.MAPEO_AGENTES` corregido de "hipótesis, sin generalizar"
a **hecho de la plataforma**: los marcadores 1 a 16 están destinados a los
Pololu, uno por robot, robot N ↔ marcador N — no es una convención que
dependa de cómo quedó pegada una constelación esta sesión. La etapa 1 /
`verificar_mapeo_ids.py` quedan como chequeo de seguridad opcional, ya
documentado así en el README.

---

## Evaluación física (2026-09-11) y réplica pareada con capas (2026-09-12)

Sesión `--sesion evaluacion --factor 0.40` con la calibración del 28–29 ago,
robots 1, 2, 3, 6 y 9, política + CBF (ℓa = 0.05, α = 2, d_pared = 0.18,
d_robots = 0.25) + escape, 500 decisiones × 0.1 s. CSV:
`resultados_sesion/20260911_sesion-evaluacion_etapa7_{decisiones,episodios}.csv`.
19 intentos → **5 válidos** (ep 1, 2, 3, 10, 12); n = 5 era el mínimo
declarado antes de correr. Las sesiones anteriores no cuentan: la del 5 sep
tenía el bug de ritmo (0.87 m por robot en todo el episodio) y el ep 1 del
9 sep no tiene CSV (se perdió antes de que la escritura pasara al `finally`).

### Citable tal cual

- Cobertura AoI: **0.3176 ± 0.0202**, IC95 ≈ [0.293, 0.343].
- **0 colisiones < 0.15 m** en los 5 episodios.
- Ritmo verificado: duración 49.998–50.047 s, ciclo p95 23–58 ms.
- Recorrido 4.9–6.9 m por robot por episodio.
- El punto de mira entra al margen de pared (0.18 m) en el 12.5 % de las
  decisiones; **el CBF o el escape actúan en el 99 % de ellas**. Mínimo
  6.4 cm (centro) en ep 1, robot 1, ya en recuperación.

Exclusiones: 7 por el chequeo de pared al arrancar (nunca corrieron, cada una
gastaba un intento — ya no, ver abajo), 4 robot 3 (socket), 1 robot 9 (falla
de seguimiento real), 1 robot 2 en escape (ambiguo), 1 marcador 2 congelado.

### La comparación pareada del informe de sesión está sesgada

`_replica_simulada` corre el env de entrenamiento **sin CBF ni escape**. El
factorial 2×2 (§ "Factorial 2×2 en Python") atribuye a esas capas ~+0.135 de
cobertura, así que la réplica queda sesgada a la baja por construcción y el
"+0.024 a favor del hardware" que imprime el informe es optimista. Corregido
en el informe: ahora la marca como sesgada y remite a la válida.

**Réplica válida** (`replica_con_capas.py`, en el repo): la MISMA pila del
laboratorio —`CoordinadorEnjambre` con los adaptadores del Robotat, 10 Hz
reales, factor 0.40, rampa sólo en el ep 1 como en la sesión— contra
`SimuladorRobotat`, con la misma semilla y la misma pose inicial medida de
cada episodio (ida y vuelta env→lab→env verificado analíticamente y
midiendo). Calibración **identidad**: la del lab lleva un offset de rumbo de
92° que modela la constelación montada girada sobre el chasis real; el
simulador emite el rumbo del chasis, y con ese offset los robots salían de la
arena (primer intento, descartado). 3 repeticiones; ruido entre repeticiones
mediana 0.0008, máximo 0.0212.

| | cobertura |
|---|---|
| hardware (n = 5) | 0.3176 |
| réplica con capas | **0.3409** |
| réplica del informe (sin capas, sesgada) | 0.2940 |

**hardware − réplica con capas: −0.0233 ± 0.0538, IC95 [−0.090, +0.044],
2/5 positivas, t pareado p = 0.39, Wilcoxon p = 0.44.** El signo se invierte
respecto de la réplica sesgada. Heterogéneo por episodio (ep 3 −0.111,
ep 12 +0.030).

Seguridad, hardware frente a réplica con capas: d_pared mínima 0.113 frente a
0.157 m (el hardware llega 4.4 cm más cerca, consistente con el retardo de
actuación del 3pi, ver "Brecha de actuación"), agentes que violan 0.18 2.4
frente a 2.5 por episodio, fracción CBF 0.41 frente a 0.49, colisiones 0 y 0.

### Tamaño de muestra: la comparación no se resuelve dentro del trabajo

Con la diferencia y el desvío observados (0.0233, 0.0538) harían falta
**~23 episodios para que el IC95 apenas excluya el cero y ~44 para potencia
0.80** (t de Student; con la aproximación normal salen ~20 y ~42). A n = 10
la potencia es 0.23. Los diez episodios planeados **no** resuelven la
comparación. La conclusión defendible no es que haya o no haya pérdida de
cobertura en hardware, sino que **la comparación requiere un n fuera del
alcance de este trabajo**. Lo que se reporta es la estimación puntual
(≈ −7 % relativo a la réplica) con su IC, sin afirmar ni pérdida ni
equivalencia. `analizar_replicas.py` imprime este cálculo.

### Hallazgo: en hardware las capas son condición de existencia del episodio

La misma pila **sin** CBF ni escape (`--capas off`), mismos arranques y
semillas: **15/15 episodios salen de la arena**, mediana 9.6 s (3.9–20.2 s de
50). No hay cobertura que comparar.

La razón es de entorno, no de política. En el env de Python con bordes
bloqueantes la **simulación contiene al agente gratis**: el recorte de
posición hace el trabajo y el agente sin capas nunca sale. En el Robotat la
plataforma excede la arena de 3×3 y nada lo retiene. Por lo tanto el +0.135
del factorial está medido en un entorno que regala la contención y
**subestima el valor de las capas**. La afirmación es: *en simulación las
capas aportan cobertura; en hardware son condición para que el episodio
exista.*

### Arreglos operativos surgidos de la sesión

- **Robot 3 no era batería.** Siguió el comando (razón 0.39–0.41, igual que
  los demás) en ep 1–13 y cayó a 0.00 de golpe tras un WinError 10054:
  `CanalActuacionRobotat._enviar_crudo` no reconectaba. Ahora reconecta
  (`_reconectar`, limitado a 1 intento/s, timeout 0.5 s); `cerrar()` no
  revive un canal cerrado a propósito. El test de enlace caído se partió en
  inalcanzable (sigue la lección de seguridad) y recuperable. Por qué el robot
  cierra el socket sigue abierto.
- **Rechazo del chequeo de colocación** vuelve a pedir la colocación hasta 5
  veces sin gastar el intento (`REINTENTOS_COLOCACION`). 7 de 19 intentos se
  perdieron así el 11 sep.
- **Aviso de "pose vieja"** (95 % de la consola): lo causaba el arreglo de
  ritmo del 5 sep, que reiniciaba `_k` y con él el tick de las poses. Ahora
  el horario se re-ancla (`_k_ancla`) sin reiniciar el contador. 0 avisos en
  las 30 corridas de réplica.
- Guía de colocación que siempre decía "SIN POSE" (lista frente a dict) y CSV
  que se perdía con Ctrl+C: corregidos, con test.

Batería: **213/213** (`test_robotat`, `test_sesion_robotat`,
`test_integracion_robotat`).

### Investigación abierta: por qué el robot 3 cierra el socket (2026-09-12)

Trabajo de escritorio sobre los logs de consola de las tres sesiones y el CSV
de decisiones del 11 sep. **Causa todavía no establecida**; lo que sigue son
hechos y las hipótesis que quedan en pie.

**Hechos.**
- Todos los 10054 de sockets de ruedas cayeron con los robots **quietos, en la
  pausa de recolocación**. Ninguno con los robots andando: 5 sep robot 1 dos
  veces (antes de que existiera el latido), 9 sep robot 3 (guía del ep 3), 11
  sep robot 3 (guía del ep 14).
- 11 sep: el robot 3 siguió el comando normalmente hasta el ep 13 (1.19 m, como
  los demás; picos de rpm iguales a los otros cuatro) y estaba muerto desde el
  primer paso del ep 14. La guía (latido de 1 s) lo muestra quieto en
  (0.61, 1.85) durante ~11 s, lo muestra apoyado en (1.47, 2.30) —el operador
  lo levantó y lo movió—, y **1–2 latidos después** llega el RST. En los ep
  14–17 su pose estaba viva (tiembla, nunca repite) pero con 0.00 m recorridos.
- 9 sep: justo antes de la caída, el ep 2 se invalidó porque el robot 3 recorría
  el **13 %** de lo comandado. Con el socket vivo, no avanzaba: eso es potencia
  en el robot, no red.
- Otros robots manipulados en la misma guía (p. ej., robot 2 el 11 sep) no se
  cayeron.
- El latido del 9 y el 11 sep mandaba (0, 0) cada segundo: el diagnóstico del
  5 sep ("socket inactivo que el robot descarta") **no explica** estas dos
  caídas.
- Un 10054 significa que el robot contestó con RST: su pila de red estaba viva
  al recibir nuestro paquete. Si el robot se hubiera apagado del todo habría
  timeouts, no RST. Un ESP32 recién reiniciado sí contesta RST a una conexión
  que no conoce.
- En el sketch de MT3006 (misma placa TinyS3), el `setup` deja los motores
  apagados hasta que conecta el WiFi: un reinicio se ve como "robot quieto que
  parece sin batería". El firmware del servidor 9090 del Robotat no está en
  disco.

**Hipótesis.**
- **H1**, la más consistente hoy: un contacto intermitente de potencia en el
  robot 3 (batería o interruptor) que, al manipularlo, reinicia el ESP32. Explica
  que caiga al apoyarlo, que el RST llegue en 1–2 s y el 13 % del 9 sep.
- **H2**: el robot pierde el WiFi en la nueva ubicación sin reiniciarse.
- **H3**: el firmware descarta la conexión sin reiniciarse.

**Instrumentos (listos, sin correr en el laboratorio).**
- `CanalActuacionRobotat` registra cada caída en `eventos_enlace`: la demora
  hasta reabrir y cada intento clasificado. La consola dice "RECONECTADO a los
  X s … intentos fallidos: …" y el resumen lista las caídas. Reabrir al primer
  intento en <1 s apunta a H3; varios segundos sin respuesta, a H1 o H2.
  ⚠ En Windows un rechazo tarda ~2 s (medido: 2.03 s), así que con el timeout
  de 0.5 s aparece como "sin respuesta". En sesión sólo discrimina la demora.
- `sonda_enlace_robots.py`: manda **sólo (0, 0)**, hace ping cada 0.5 s y
  reintenta con timeout de 3 s. El operador anota lo que hace desde la consola.
  Firmas esperadas:
  - H1: el ping se corta varios segundos y reconecta al volver.
  - H2: el ping se corta y puede no haber RST.
  - H3: el ping nunca se corta y reconecta al primer intento.

  Probada contra un robot local que corta con RST: registró caída y reconexión
  al primer intento a 0.01 s, con el ping arriba.
- Protocolo propuesto, robots 3 y 6 (control):
  1. Quietos 60 s.
  2. Levantar y apoyar cada uno 5 veces.
  3. Moverlo a (1.47, 2.30) y a la esquina +x+y.
  4. Golpecito al interruptor.
  5. Presionar suavemente la batería.

### Cambio de composición: el robot 8 reemplaza al 3 (2026-09-22)

El agente 2 pasa del robot 3 al **8**. El 3 sale por las caídas de socket
descritas arriba; su causa sigue sin investigar. Candidatos con offset en la
tabla del laboratorio: 4, 5, 7 y 8. Se eligió el 8 por tener el offset más
parecido al resto del enjambre.

**Etapa 3 sobre el robot 8** (`--robot 8 --forzar`; `--forzar` porque el
registro marca la etapa 2 como FALLO por la recalibración descartada del
9 sep, y la etapa 3 se calcula en el marco del laboratorio sin usar la 2):
- Avance recto de 16.4 cm, desvío lateral 0.1 mm, giro del rumbo +0.06°,
  dispersión 0.22°. Sin rueda invertida.
- Offset **+95.01°** frente a +89.99° de la tabla: **5.02°** de diferencia (en
  el robot 1 la tabla erraba 1.63°).
- Supera los 3° de diferencia a partir de los cuales se usa el valor medido,
  así que se cargó el medido. CSV:
  `resultados_sesion/20260922_sesion-calibracion_etapa3_rumbo.csv`.
- La etapa escribe su offset en `calibracion_medida.json`, que está a nombre
  del robot 1. Se respaldó antes de correrla y se restauró después (hash
  idéntico), así que el robot 1 conserva sus 92.13°.

**⚠ A tener en cuenta en toda medición posterior** (pedido del autor):
- El offset del 8 sale de **una sola corrida**. Si en la evaluación el robot 8
  muestra sesgo de giro, CBF anómalo o seguimiento bajo que los otros no
  tienen, lo primero es repetir su etapa 3.
- Los episodios con el 8 son **otra composición** que los 5 válidos del
  11 sep (robots 1, 2, 3, 6, 9). No se agregan a ese n sin declararlo.
- Para que ningún resultado se lea sin esto:
  - `config_robotat.origen_offset_rumbo` declara de dónde sale cada offset.
  - El encabezado de cada sesión imprime el offset y su origen por agente.
  - El CSV de episodios lleva `robot_a{i}`, `offset_deg_a{i}` y
    `offset_origen_a{i}`.

Batería: 217/217.

### Hallazgo: los arranques del 11-09 no representan la distribución de entrenamiento (2026-09-22)

Los 5 episodios válidos del 11-09 arrancaron en **formación compacta** ("en
cruz"): distancia media al vecino más cercano **0.27 m**, contra 0.64–0.84 m
(IC 95 %) del sorteo de entrenamiento con el mismo n. Los episodios 1–3
arrancaron con el centroide en (1.5, 1.25); el 10 y el 12, en racimos contra
un borde. Sólo 8 de las 16 celdas del área de arranque recibieron algún
robot, y KS de x e y en el percentil 100. El operador colocó los robots a
ojo porque la guía de ese día imprimía "SIN POSE" (error de lista contra dict,
corregido después de esa sesión).

Consecuencias:
- **El pareo hardware − réplica sigue siendo válido**, porque la réplica arranca
  de las mismas poses.
- **La cobertura absoluta** (0.318 en hardware, 0.341 en la réplica con capas)
  corresponde a arranques compactos y **no se compara** con 0.5739 (Webots) ni
  con 0.578 (Python). Esos valores, además, son con factor 1.0: hay dos
  factores confundidos (arranque y velocidad), y no se atribuye la diferencia
  a ninguno sin medirlo.

**Instrumento** (`diversidad_arranques.py`): ubica seis estadísticos de los
arranques de una sesión en su distribución bajo el sorteo de entrenamiento con
el mismo número de episodios y agentes (Monte Carlo, 1000 sesiones):
- celdas cubiertas;
- dispersión del centroide;
- vecino medio;
- resultante de rumbos;
- KS de x;
- KS de y.

Si el CSV trae los blancos de TODOS los intentos, compara también válidos
contra todos, para detectar el sesgo que introducen las exclusiones. Lo
imprimen el informe de sesión y `analizar_replicas.py`. Con seis estadísticos,
un ⚠ aislado aparece por azar en ~1 de cada 4 sesiones sanas.

### Colocación autónoma entre episodios (2026-09-22)

`colocacion_autonoma.py`, `--colocacion auto` (el default de la sesión de
evaluación). Antes de cada episodio, incluido el primero, los robots van solos
al blanco sorteado.

- **Blanco:** posición de siempre y un **rumbo** nuevo, uniforme en (−π, π] como
  en el entrenamiento, de un generador aparte para no cambiar las posiciones.
- **Velocidades:** ≤ 0.08 m/s y ≤ 1 rad/s (el régimen del laboratorio).
- **Seguridad:**
  - Cada comando pasa por el mismo filtro CBF de los episodios, con una sola
    diferencia: una barrera ya violada exige "no empeorar" (ḣ ≥ 0). Con la
    condición de los episodios, un robot fuera de la arena deja el QP
    infactible y queda clavado.
  - Un robot sin pose, con el marcador congelado o sin progreso se detiene y
    se deja para el operador. Los demás siguen.
- **Rampa intacta:** no cuenta como decisión (`enviar_directo`), así que la
  rampa y su reconstrucción en la réplica no cambian.
- **Si el chequeo geométrico no pasa:** cae a la guía manual y, tras el Enter,
  se vuelve a colocar sola.
- **CSV:** `colocacion`, `blanco_{x,y,th}_a{i}`, `col_err_m_a{i}`,
  `col_err_rumbo_deg_a{i}`, `col_estado_a{i}` y `col_t_s`.

Motivación:
1. En la sesión del 22-09 colocar a mano no avanzaba (0 válidos en 2 intentos).
2. Todos los cortes de socket de ruedas registrados (robots 1, 2 y 3) fueron
   durante la manipulación.
3. Los arranques a ojo salen compactos (ver arriba).

**Cortes de socket del 22-09, durante la colocación a mano:**
- Robot 2: no volvió en minutos.
- Robot 1:
  - Primera caída: volvió a los **49.2 s** después de 34 intentos sin
    respuesta. Estuvo fuera de la red.
  - Segunda caída: volvió a los **0.4 s**, al primer intento. Estaba en la red
    y cortó igual.

Las dos firmas no son compatibles con una sola hipótesis. Se registra; con la
colocación autónoma se ve si los cortes persisten sin manipulación.

**Otros arreglos del día:**
- **Semillas:** pasados los 18 intentos se siguen generando semillas nuevas.
  Antes, los intentos 19 y 20 repetían la configuración de los 1 y 2.
- **Régimen en el CSV:** cada episodio lleva su `factor` y su `rpm_aborto`, y
  la réplica los lee junto con las `decisiones`. Antes los tenía fijos en
  0.40, 500 y 200; una sesión corrida con otros valores quedaba mal pareada sin
  aviso. Hallazgo de la revisión adversarial.
- **Analizador:** `n_necesario` ya no se cae con `StopIteration` cuando la
  diferencia es indistinguible de cero.
- **Canal:** los envíos van con candado (`_cerrojo_envio`), porque el latido de
  la guía (otro hilo) puede solaparse con los envíos de la colocación.

**Revisión adversarial de la colocación.** Tres revisores (seguridad,
hardware real, metodología) y un escéptico por hallazgo. Tres defectos
confirmados y corregidos:
1. **Un robot que no se ve al empezar no tenía barrera para los demás.**
   Ahora nadie se mueve hasta ver a todos. Si alguno sigue sin verse a los
   2 s, la colocación termina sin mover a nadie y pasa al operador.
2. **Un marcador congelado dejaba andar al robot ~2 s a ciegas** (hasta
   ~16 cm) y el episodio arrancaba igual.
   - A la primera repetición de pose se lo frena.
   - Si se confirma, se detiene la colocación de todos.
   - La sesión lo trata como problema de arranque, que no gasta el intento.
   - Nuevo `_marcadores_congelados_al_arrancar`, en los dos modos: dos
     lecturas separadas 0.15 s no pueden ser idénticas, porque un marcador
     vivo tiembla a ~82 Hz. El episodio 1 del 22-09 se perdió así.
3. **La pose de arranque (la de la réplica) se leía con los robots todavía
   moviéndose** por el retardo de 450 ms. Ahora espera 0.6 s.

Refutado: que `W_MIN` dejara los giros en la zona muerta de las ruedas. Esa
zona muerta no está medida; se verá en el laboratorio.

Batería: **233/233** (`test_robotat`, `test_sesion_robotat`,
`test_integracion_robotat`). En el simulador: tres robots que se cruzan
llegan a blanco y rumbo sin bajar nunca de 0.15 m entre centros, y la
colocación no suma decisiones. Todavía **sin probar con robots reales**.

### Sesiones del 22 y 24 de septiembre: la captura perdió el perímetro de la arena

Composición final: robots 1, **5**, 8, 6 y 9. El 2 salió porque su marcador se
congelaba; el 5 entró con la etapa 3 verificada (+87.97° medido contra +88.81°
de la tabla, Δ 0.84°).

**La colocación autónoma funcionó.** En casi todos los intentos los cinco
llegaron a blanco y rumbo en 14–34 s, sin choques y sin intervención.

**24-09: 1 válido de 17 intentos.** El episodio 2 dio cobertura 0.2416,
0 colisiones y d_pared mínima 0.229 m. Por qué se cayeron los demás:
- **10 por marcador congelado,** en todos los robots (1, 5, 8 y 9). **9 de
  los 10 fueron a menos de 35 cm de una pared, en los cuatro lados,** aunque
  los robots pasan ahí sólo el 21.8 % de las decisiones. El 11-09 los robots
  pasaron el 35.1 % de las decisiones (5992) a menos de 35 cm de una pared, y
  hubo **un solo** congelamiento en toda la sesión. El 22-09 se había visto lo
  mismo, pero sólo en el borde superior.
- **Conclusión:** entre el 11 y el 22-09 cambió algo en la captura del
  Robotat que hace perder los marcadores a la altura del piso en una franja
  de ~20–30 cm del borde de la arena. No es un robot ni el código: pasa con
  todos. Hay que revisar con el laboratorio la calibración de Motive y las
  cámaras.
- **5 (episodios 5 a 9) por "antigüedad de pose", a las 4 decisiones.** La
  causa real: el robot 5 estuvo **5.4 min fuera de la red** (227 intentos de
  reconexión sin respuesta; en el episodio 4 ya seguía sólo el 50 % de lo
  comandado, lo que apunta a potencia). Cada envío intentaba reabrir su
  enlace y trababa el lazo ~0.45 s (ciclo p95 de 450 ms). **Error mío,
  corregido:**
  - el chequeo previo reintenta los enlaces caídos y no arranca si alguno
    sigue caído (rechazo de colocación, sin gastar intento);
  - a mitad de episodio, un enlace que no se reabre en el mismo envío aborta
    con "enlace de ruedas caído: robot X".
- **1 por seguimiento del robot 5 (50 %),** justo antes de que se fuera de la
  red.

El desfase de ~25 cm en y entre el marco de la arena y el cuadrado del piso
(traslación y = 1.256, parchada a mano el 28-08; el 11-09 los arranques "en
el centro" se leyeron con y = 1.24) sigue sin medir. Con la pérdida de
perímetro de ahora, corregirlo no alcanza: la franja perdida está en los
cuatro lados.

---

## Cerrojo en la fuente de poses (2026-09-24) — cambio separado; NO corrige los congelamientos de borde

**⚠ Esto no es la corrección de los congelamientos de marcador del 22 y
24-09**, y no hay que atribuírselo si el síntoma no reaparece en la próxima
sesión. Se registra aparte justamente para evitar esa lectura. La auditoría de
esos congelamientos sigue abierta —falta decidir en el laboratorio si la pose
la retiene el servidor o la pierde Motive (H4/H6)— y tendrá su propia entrada
cuando se cierre.

**Por qué no puede ser la corrección.** Los 15 congelamientos registrados (11,
22 y 24-09) ocurrieron a mitad de episodio, con un solo hilo consultando —el
latido de la guía sólo corre en las pausas—, y en UNA fila de respuestas cuyas
otras cuatro filas cambiaron en todas las decisiones. Un cruce de respuestas
entre dos hilos desordena o rompe la respuesta entera, no una fila.

**Qué corrige.** Una condición de carrera real, encontrada durante la
auditoría. `FuentePosesRobotat` no tenía cerrojo y la usan dos hilos: el
latido de `_esperar_reposicionamiento` (cada 1 s) y el hilo principal. Al
latido se lo espera con `join(timeout=2.0)` y la sesión sigue aunque no haya
terminado. Si seguía dentro de una consulta —hasta 1 s si el servidor no
contesta— cuando empezaba la colocación, dos peticiones compartían el socket y
podían cruzar sus respuestas. El canal de ruedas recibió `_cerrojo_envio` el
22-09 por ese mismo solape; la fuente de poses no.

**Arreglo.** Un `RLock` en la fuente, que toman `leer_poses`, `leer_poses_ya`,
`agentes_vencidos`, `reiniciar` y `cerrar`. Con un solo hilo no cambia nada:
contra un servidor guionado de siete respuestas, la fuente con cerrojo da las
mismas poses y los mismos contadores que la previa. Pruebas propias en
`test_cerrojo_fuente_poses.py`: dos hilos sobre la misma fuente (30 consultas,
0 fallidas, 30 peticiones en el servidor, ninguna fila cruzada) y una consulta
que espera a la que está en curso.

Respaldo previo: `adaptadores_robotat_respaldo_20260924_preCerrojo.py`.
Batería: **263/263** (`test_robotat`, `test_sesion_robotat`,
`test_integracion_robotat`, `test_diagnostico_poses`,
`test_cerrojo_fuente_poses`).

---

## Respuesta no numérica del servidor (2026-09-24) — cambio separado

`decodificar_respuesta_poses` dejaba subir el `ValueError` (o `TypeError`) de
`np.asarray` cuando la lista de la respuesta traía algo que no es un número
—un texto, un objeto, listas de largos distintos—: la excepción atravesaba la
fuente y tiraba la sesión, en vez de contarse como consulta fallida. **Nunca se
observó en el laboratorio** y no tiene relación con los congelamientos de
borde; lo encontró la auditoría al comparar la función con su versión
diagnóstica (`diagnosticar_respuesta`). Ahora devuelve `None`, como cualquier
otra respuesta no utilizable, y la fuente cuenta una consulta fallida.

Respaldo previo: `protocolo_robotat_respaldo_20260924_preValueError.py`.
Prueba propia: `test_respuesta_no_numerica.py`, con control negativo (la
versión previa lanza `ValueError` ante la misma respuesta).

---

## Evaluación: pausa por pose repetida en lugar de aborto, y contadores de la fuente en el CSV (2026-09-24) — cambio de protocolo

Decisión del autor tras la auditoría de los congelamientos de borde. **No es
una corrección de esos congelamientos** —su causa sigue abierta (H4/H6)—: es
la reacción del lazo cuando ocurren.

**Antes:** 10 decisiones con la misma pose (1 s) abortaban el episodio, y entre
la primera repetición y el aborto el robot seguía andando a ciegas, con el
escape actuando sobre una pose falsa.

**Ahora** (`_correr_episodio`; `CanalActuacionRobotat.pausar` / `reanudar`):
- a la **primera** repetición de la pose (x, y, θ) de un agente
  (`REPETICIONES_PARA_PAUSA = 1`), el agente queda EN PAUSA: el canal le manda
  (0, 0) en el acto y en cada decisión;
- cuando su pose vuelve a cambiar, se reanuda. **El episodio no se aborta**;
- en pausa, su camino comandado cuenta cero para el detector de seguimiento y
  no se le exige desplazamiento; al reanudar, el reloj de "sin desplazamiento"
  arranca de nuevo;
- **única excepción**, agregada al implementarlo: si TODOS los agentes quedan
  en pausa a la vez durante `DECISIONES_CONGELADO` (10) decisiones seguidas, no
  queda ninguna pose viva y el episodio se aborta.

Una sola repetición basta: a 10 Hz hubo 0 repeticiones benignas de (x, y, θ)
en 34 715 pares consecutivos (sesiones del 11, 22 y 24-09), y los 15
congelamientos reales empezaron con el robot en marcha. La comparación es de
la pose COMPLETA, y está marcada así en el código: con una sola coordenada,
10 µm de ruido de captura dan ~0.33 % de repeticiones por azar; con la fila
completa de 7 valores del servidor, 0 en 400 000 (verificación del autor).

**Registro de las pausas**, porque afectan la cobertura: columna `pausado` en
el CSV de decisiones; por episodio, `pausas_a{i}`, `decisiones_pausadas_a{i}`,
`decisiones_pausadas`, `frac_decisiones_pausadas`, `pausa_max_s` y
`pausas_detalle`.

**Contadores de la fuente por episodio**, en el CSV de episodios:
`poses_consultas`, `poses_fallidas`, `poses_rechazadas`,
`poses_rechazos_motivo`, `poses_bytes_descartados` y
`poses_consultas_con_descarte`. Hasta ahora sólo salían por consola al cerrar
la sesión, y por eso la auditoría no pudo saber si hubo rechazos el 22 y 24-09.

⚠ **A decidir antes de usar episodios con pausas en la estadística:**
- un robot pausado dentro de una zona sin captura no sale solo, porque está
  quieto; el 29-08 un marcador quieto en la esquina +x+y siguió congelado
  20 s. Un episodio puede terminar con un robot pausado de ahí al final;
- la réplica pareada (`replica_con_capas.py`) no reproduce las pausas: tal
  como está, un episodio con pausas no es comparable con su réplica.

Respaldos previos: `*_respaldo_20260924_preRevision.py`. Batería:
**270/270** (`test_robotat`, `test_sesion_robotat`,
`test_integracion_robotat`, `test_diagnostico_poses`,
`test_cerrojo_fuente_poses`, `test_respuesta_no_numerica`).

---

## Auditoría: pérdida de seguimiento en los bordes (2026-09-24) — mecanismo confirmado por el laboratorio

Pregunta: por qué se congelaron las poses cerca de las paredes el 22 y el
24-09 (14 episodios perdidos por "marcador congelado"). Fuentes: los CSV de
evaluación del 11, 22 y 24-09, los bytes crudos de la etapa 5 del 29-08, la
lectura MATLAB del 09-09 y las consultas rápidas del 05-09. Sólo lectura: los
80 archivos de `resultados/` y `resultados_sesion/` tienen el mismo hash antes
y después.

**Mecanismo (confirmado por el encargado del Robotat, 24-09).** Un marcador
que nunca se detectó sale como [0 0 0]; uno que ya se detectó y entra en un
punto ciego de las cámaras sale con la ÚLTIMA pose registrada, que Motive
retiene. El servidor no verifica la detección: reenvía lo que le da Motive.
El congelamiento viene en los datos, y la causa son puntos ciegos de la
cobertura de cámaras.

**Lo que la auditoría había establecido con datos** (el laboratorio no lo
contradice):
- Los 15 congelamientos a 10 Hz (1 el 11-09, 4 el 22-09, 10 el 24-09) no los
  produce el cliente: sólo puede repetir una pose bit a bit si el servidor
  mandó los mismos números; un rechazo propio aborta por antigüedad (0.15 s)
  en 1–2 decisiones, que es otra firma.
- Son por marcador: en los 15, los otros cuatro agentes cambiaron en la MISMA
  respuesta en lote.
- Dependencia espacial, 22+24-09, en inicios por 1000 decisiones-agente según
  la distancia a la pared más cercana: 3.9 a < 0.20 m; 2.6 entre 0.20 y
  0.35 m; 0.33 entre 0.35 y 0.60 m; 0 en 7 818 decisiones-agente a ≥ 0.60 m.
- Cambio entre fechas: a < 0.35 m de una pared, 1 inicio en 5 992
  decisiones-agente el 11-09 contra 12 en 3 962 el 22+24-09 (~18×).

**Veredictos.**
- H1 (el rango de validación rechaza las poses de borde): descartada. El
  rango es ±5 m en el marco del laboratorio, y las 729 respuestas congeladas
  del 29-08 pasaron la validación.
- H2 (un robot detenido repite la pose): descartada. 0 repeticiones exactas
  de (x, y, θ) en 34 715 pares consecutivos a 10 Hz, 988 de ellos con el
  robot quieto (< 0.5 mm y < 0.2° entre decisiones).
- H3 (error de marco): agrava el borde superior —la arena está corrida
  +0.24 m en y del laboratorio— pero no explica el inferior ni el cambio entre
  fechas. No se remide (decisión del autor: no hay evidencia de error de
  marco).
- H4 (Motive pierde el marcador en la periferia): CONFIRMADA como mecanismo
  por el laboratorio. DÓNDE están los puntos ciegos sigue abierto: lo mide el
  modo de mapeo de la sonda (entrada siguiente a la del retroceso).
- H5 (desfase del búfer: frame fantasma al conectar, o lectura de largo
  fijo): descartada en las dos variantes. Ninguna lectura es de largo fijo;
  lo que el servidor manda al conectar es el saludo de texto de 52 B; y un
  desfase daría un flujo vivo atrasado, nunca una fila congelada entre cuatro
  vivas.
- H6 (el servidor retiene el último valor por calidad): descartada por el
  laboratorio, el servidor no mira la detección. La respuesta tampoco trae
  campos de calidad (1 095 respuestas crudas: lista plana de 7·N números).

**Abierto: el cambio entre el 11 y el 22-09.** El mecanismo confirmado no lo
explica solo: el 11-09 los robots pasaron cientos de veces por los mismos
puntos sin congelarse. Hipótesis, sin verificar: cambió la cobertura de
cámaras (posición, calibración o cámaras activas) entre esas fechas. Se
contrasta preguntando al laboratorio, o mapeando y comparando con los
recorridos del 11-09.

**La predicción del autor contra los datos que ya hay.** "Si los puntos
ciegos están en la periferia de la plataforma (4.67 × 3.45 m), se concentran
junto a los bordes de la dimensión corta, donde la arena queda a ~22 cm."
Inicios por 1000 decisiones-agente a < 0.35 m de la pared más cercana,
22+24-09: paredes y de la arena 8/2 460 = 3.25 ‰, paredes x 4/1 502 =
2.66 ‰. Repartiendo los 12 inicios según esa exposición, P(≥ 8 en las paredes
y) = 0.50 (binomial condicional, unilateral): los datos no la apoyan ni la
refutan. Por pared: y = 3, 4/767 = 5.22 ‰ (P = 0.19); y = 0, 4/1 693 =
2.36 ‰; x = 3, 3/905 = 3.31 ‰; x = 0, 1/597 = 1.68 ‰.
⚠ "A ~22 cm del borde" supone la arena centrada en la plataforma, y no lo
está: con la calibración vigente, SI la plataforma está centrada en el origen
de Motive —no medido—, la pared y = 3 queda a ~1 cm de su borde, la y = 0 a
~49 cm y las x a ~86 cm. La pared más cercana al borde es la de más inicios,
pero con 4 eventos. Lo decide el mapa.

Instrumentos que dejó la auditoría: el registro de diagnóstico de poses
(`--diagnostico-poses`), la sonda de seguimiento, el cerrojo de la fuente y
la corrección del `ValueError` (entradas anteriores).

---

## Evaluación: RETROCESO por pose repetida en lugar de la pausa (2026-09-24) — cambio de protocolo

Reemplaza a la pausa de la entrada "pausa por pose repetida", del mismo día,
por lo que confirmó el laboratorio: un robot pausado DENTRO de un punto ciego
no vuelve a ser visto nunca, y el episodio queda trabado. **No corrige los
puntos ciegos** —siguen ahí—: es la reacción del lazo cuando un robot entra
en uno.

**Ahora** (`retroceso_congelamiento.py`, `_correr_episodio`, y en el canal
`fijar_mando`, `liberar_mando` e `historial_mandos`): a la PRIMERA repetición
de la pose completa, el agente RETROCEDE por su trayectoria de entrada: el
canal le manda, en orden inverso y con el signo cambiado, las órdenes de rueda
que el robot RECIBIÓ. En el modelo diferencial eso recorre el mismo camino
hacia atrás, arco por arco. Si su pose vuelve a cambiar, se reanuda en el
acto; si el retroceso se agota y, tras la espera de verificación, la pose
sigue repetida, queda parado y el episodio se aborta ("marcador CONGELADO …
tras retroceder").

**Topes propuestos** (a validar en el laboratorio):

| parámetro | valor | de dónde sale |
|---|---|---|
| órdenes a deshacer | congelada + 0.45 s, tope 1.0 s | congelada = t de detección − t de la última consulta con pose distinta: 0.2 s en la 1.ª repetición a 10 Hz. 0.45 s = retardo de actuación medido el 29-08 |
| margen | 0.4 s más de retroceso, por el camino anterior | arranque a 0.05 m/s: 849 ms, contra 458 ms a 0.15 m/s (+0.39 s) |
| velocidad | rueda más rápida a 0.07 m/s, nunca < 0.5 × la entrada | 0.07 = `V_LAB`; más lento el 3pi puede no arrancar (1 de 5 a 0.05 m/s) |
| espera de verificación | 0.6 s en (0, 0) | > 0.45 s de retardo + una consulta |
| tope hasta el aborto | ≤ 1.0 / 0.5 + 0.4 + 0.6 = 3.0 s | en la 1.ª repetición a 0.124 m/s: ≈ 2.15 s y 10.9 cm de camino |

Por qué no el "tiempo que lleva congelada" literal: son 0.2 s, pero con
0.45 s de retardo el robot entró ~0.6 s; a 0.124 m/s quedaría 4–5 cm adentro.
Y por qué el margen es tiempo de RETROCESO y no de órdenes de entrada: la
primera versión (0.2 s de órdenes de entrada) agregaba 0.6 cm a 0.031 m/s —la
rampa de arranque— y no cubría un arranque lento; lo mostró el barrido.

**Pruebas** (`test_retroceso_congelamiento.py`, 26, y 2 de sesión en
`test_sesion_robotat.py`, que reemplazan a la de la pausa):
- el plan deshace exactamente el camino de entrada (integración exacta del
  uniciclo, 20 historiales al azar), margen incluido;
- contra la zona sin captura del SIMULADOR, con fuente, canal y sockets
  reales y 0.45 s de retardo de actuación (`FallasSimulador.
  retardo_actuacion_s`, nuevo; por defecto 0, como antes): sale del punto
  ciego y se reanuda; con la ventana literal se queda adentro (control
  negativo); si la zona crece y no hay salida, queda parado y falla dentro
  del tope;
- sesión completa, 3 robots con política y CBF: se recupera a los 0.8 s y el
  episodio queda VÁLIDO; con la zona agrandada, INVÁLIDO a los 1.4 s con su
  motivo;
- sin repeticiones no cambia nada: el canal nuevo manda los mismos bytes que
  el de antes del cambio.

**Barrido en el banco cinemático** (`test_retroceso_congelamiento.correr_banco`:
el mismo gestor y el mismo plan que la sesión, con un uniciclo de retardo puro
y fricción de arranque; 250 entradas por condición = 5 velocidades de 0.031 a
0.124 m/s × 5 ángulos o arcos × 10 fases del cruce). Entradas que salen:

| retardo real | arranque extra 0 s | 0.2 s | 0.4 s |
|---|---|---|---|
| 0.30 s | 250 | 250 | 250 |
| 0.45 s | 250 | 250 | 216 |
| 0.60 s | 250 | 214 | 0 |

Con la ventana literal: 0/250 en todas. La envolvente: tolera ~0.4 s de
arranque extra, o ~0.15 s más de retardo, pero no los dos juntos.

**Registro** (reemplaza al de la pausa): columna `en_retroceso` en el CSV de
decisiones; por episodio, `retrocesos_a{i}`, `decisiones_retroceso_a{i}`,
`decisiones_retroceso`, `frac_decisiones_retroceso`, `retroceso_max_s`,
`retrocesos_recuperados` y `retrocesos_detalle`; en el registro de
diagnóstico, `retroceso_inicio` y `retroceso_fin`.

**Se conservó** el aborto si TODOS los agentes tienen la pose repetida
`DECISIONES_CONGELADO` (10) decisiones seguidas: eso es el flujo entero
detenido, no un punto ciego.

⚠ **Abierto:**
- velocidad y margen van a lazo abierto: se validan con el robot real;
- oscilación: al reanudar, la política puede volver a meter al robot en el
  mismo punto ciego. Cada ciclo queda registrado, sin tope por episodio. La
  solución de fondo es que el CBF trate como obstáculo las celdas ciegas del
  mapa (propuesta, no implementada);
- la réplica pareada no reproduce los retrocesos: un episodio con
  retrocesos no es comparable con su réplica sin decidir antes cómo tratarlo;
- la colocación autónoma sigue deteniendo a todos ante un marcador
  congelado, sin retroceder (sus blancos están a ≥ 0.45 m de las paredes).

Respaldos previos: `*_respaldo_20260924_preRetroceso.py`.

---

## Sonda: modo de mapeo de los puntos ciegos (2026-09-24)

`sonda_seguimiento.py --mapeo`, con `mapa_seguimiento.py`: un recorrido
sistemático de la plataforma y un mapa, por celda del marco del LABORATORIO
(0.25 m por defecto: 19 × 14 = 266 celdas en 4.67 × 3.45 m), de dónde se
congela un marcador. La sonda sigue siendo de sólo lectura: el recorrido lo
hace el operador, con la técnica de la revisión (dedo en la base, mano por
debajo de los marcadores).
- Por celda: muestras vivas; inicios y fines de congelamiento, con el MISMO
  umbral que la alarma; cruces a ciegas (el segmento entre la última pose
  viva y la primera al volver); y las retenciones cortas, aparte. Estados:
  viva, borde, ciega, sin visitar.
- Recorrido "anillos" (el perímetro primero: si se acaba el tiempo, falta el
  interior) o "serpentina". La sonda muestra la próxima celda y el mapa en
  ASCII cada 15 s, o al escribir `mapa`.
- Salidas: `_mapa.csv` (una fila por celda), `_mapa.png` (plataforma, arena
  según la calibración y cada tramo a ciegas) y el contraste de la predicción
  en consola y en el registro (`mapa_resumen`). Nada se pisa.
- Contraste: cada celda visitada va al borde de la plataforma más cercano
  (dimensión corta o larga) y a una franja de distancia; por grupo, celdas
  con congelamiento e inicios por 1000 muestras vivas; y una prueba exacta de
  Fisher unilateral sobre las celdas a < 0.50 m del borde.
- ⚠ La posición de la plataforma en el marco de Motive no está medida: sin
  `--plataforma` se la supone centrada en el origen, y el contraste vale lo
  que valga ese supuesto.

Pruebas: `test_mapa_seguimiento.py` (25), con una corrida de la sonda contra
la zona sin captura del simulador. Una corrida de humo de la sonda real
(`main --simulador --mapeo`) dejó dos arreglos: con mapa, la línea de estado y
la alarma van en el marco del laboratorio —mezclaban la pose del entorno con
la celda del laboratorio—, y sin celdas visitadas junto a los bordes de las
dos dimensiones el contraste dice "SIN CONTRASTE" en vez de un p = 1 que
parecía un resultado. Respaldo previo:
`sonda_seguimiento_respaldo_20260924_preMapeo.py`.

Batería: **322/322** (`test_robotat`, `test_sesion_robotat`,
`test_integracion_robotat`, `test_diagnostico_poses`,
`test_cerrojo_fuente_poses`, `test_respuesta_no_numerica`,
`test_retroceso_congelamiento`, `test_mapa_seguimiento`).

---

## Demo del obstáculo móvil: Fase 0 en el simulador (2026-10-01/02) — NO citable

**Encuadre.** La demo la pidió el asesor para el video de la presentación final:
- un 6.º Pololu, el robot 7 (el 4 de reserva), funciona como obstáculo MÓVIL no cooperativo;
- **no es un resultado citable**;
- muestra la generalidad de la capa de seguridad, no adaptabilidad: la observación de la política no codifica al obstáculo. Es la extensión dinámica del Exp O.

Esta entrada registra la Fase 0: implementación y verificación en `SimuladorRobotat`, con 6 robots. El detalle y las cifras verificadas están en `tesis/REPORTE_2026-10-02_obstaculo_fase0.md`, con su paquete de datos crudos y `verificar_cifras_fase0.py` (111/111).

**Decisiones de José:**
- alcance: sólo la demo (Fases 0 y 1);
- código en un archivo aparte; L1 con el robot quieto;
- una toma con freno del obstáculo no cuenta;
- **criterio para ir al laboratorio:** distancia mínima continua > 0.15 m en el peor caso, con τ = 0.45 s **y** 0.85 s;
- el 02-10: el diseño se congela en F2 con el peso condicional y **decide un conjunto de confirmación** (geometrías y semillas nuevas);
- el encierro no se mejora: se reporta como límite.

### Implementación

Todo es nuevo y por herencia. Ningún archivo existente cambió: el manifiesto sha256 previo verifica 258/258.

- **`demo_obstaculo_movil.py`.**
  - La fuente lee los 6 marcadores en **una** consulta de lote por decisión.
  - El canal manda al 7 por su **propio socket**, no como agente 5: con el índice 5, `_correr_episodio` da `KeyError` en `MAPEO_AGENTES[5]`. `detener_todo` lo frena primero.
  - El coordinador agrega una fila al QP y una normal al escape.
  - El supervisor del obstáculo: círculo antihorario de R 0.60 en (1.5, 1.5), 0.05 m/s, patada de 0.08 ≤ 1 s, quieto durante la rampa, freno de respaldo, abortos.
  - Sesiones L0, L1 y L2. La colocación es manual porque `colocar_enjambre` no ve al 7.
- **Campaña y análisis:**
  - `correr_fase0_obstaculo.py`: cada corrida es un proceso con su simulador y sus puertos; la distancia la mide un monitor de la verdad a 200 Hz.
  - `analizar_fase0_obstaculo.py`: el criterio, sobre el conjunto esperado.
  - `cifras_fase0.py`, `verificar_cifras_fase0.py`, `figura_fase0_obstaculo.py`.
  - `test_demo_obstaculo_movil.py`: 30 pruebas.

### La barrera

**F1 (la propuesta del 01-10)** usa `h = ‖p_i − p_o‖ − 0.33` y `rhs = −α·h + s/k`, con `s = max(0, n·v̂, n·v_cmd)`.
- Con v = 0 es bit a bit la fila del Exp O, con r = 0.15 (hay prueba).
- **Falla con τ = 0.85 s:** 6/17 casos guionados bajo 0.15 m, mínimo 0.0868 m.
- El modelo 1D de la propuesta predecía 0.223 m.
- **Mecanismo:** con `W_OMEGA = 0.3`, el QP paga el término de velocidad GIRANDO, que mueve el punto de mira sin mover el centro. Con el retardo, ω queda saturado y el rumbo da vueltas.

**F2, la que va al laboratorio:**
1. **Predictor:** la fila se evalúa en el estado en que la orden se ejecuta, t + τ_c, integrando las órdenes en vuelo del agente y del obstáculo (Molnar, Kiss, Ames y Orosz, 2023). τ_c = 0.65 s quedó fijado antes del barrido.
2. **Peso de giro 3.0, sólo si ninguna otra fila tiene h < 0.06.** Incondicional rompía el encierro: 0.1224 m. Condicional se eligió después de ver datos.
3. **Rescate** del QP infactible antes del fallback (0, 0).

**Además:**
- freno de respaldo a 0.25 m;
- ganancia de rumbo del obstáculo 1.0, porque con 2.0, k·τ superaba π/2;
- verificación de obediencia del obstáculo;
- el enlace caído lo frena al reabrirse.

Todo esto salió de una revisión adversarial: 19 de 26 hallazgos confirmados y corregidos.

### Resultados (campaña final del 02-10, 387 corridas)

- **Confirmación (decide), 116 corridas.**
  - **116/116 sobre 0.15 m**, con mínimo **0.1836 m** (encierro en trío, sin rampa, τ 0.85).
  - **Veredicto formal: NO PASA**, porque 1 corrida es inválida por un **falso positivo de la verificación de obediencia**: un hipo del lazo de 0.374 s dejó sin estimación la velocidad del obstáculo y la función devolvió 0 como si fuera "quieto".
- **Diseño:** 108/108 válidas, mínimo 0.1879 m.
- **Tomas con política:** las 80, ≥ 0.2696 m.
- **Control F0:** 12/34 bajo 0.15 → la medición detecta una barrera que falla.
- **Sensibilidades:**
  - retardo mixto (agentes 0.85 / obstáculo 0.45): 0.1758 m;
  - ruido de 1 mm: 0.2113 m.
- **Lazo del laboratorio:** 10/10 válidas.

### Límite conocido: el encierro

El peor caso en todas las variantes es un agente atrapado entre el obstáculo y un vecino que lo empuja: entre 0.18 y 0.21 m.
- El QP es infactible de verdad, y la salida la da el escape.
- Es el patrón de siempre: **seguridad intacta, vitalidad degradada**.
- En las 6 corridas de diseño y confirmación en que el freno de respaldo se habría disparado, fue en un encierro, a 0.245–0.250 m.

### Hallazgo colateral: la regla "sin desplazamiento por 10 s"

La regla de `_correr_episodio` mide desde el último desplazamiento, no desde la orden. Un agente quieto más de 10 s al que se le ordena huir corta la toma, y ése es el escenario de la demo.
- En 95 episodios reales (11-09, 26-09 y 30-09) cortó 0. La exposición máxima en válidos fue 3.20 s, y los casos reales de robot trabado los cortó antes `DetectorSeguimiento`.
- **Arreglo propuesto:** `t_ref = max(t_mov, t_inicio_orden + 1 s)`. Deja igual los 50/50 válidos del 30-09 y cumple que sólo puede quitar cortes.
- Ver `tesis/PROPUESTA_regla_estancamiento.md`.

### Pendiente (espera el OK de José)

1. Aplicar el arreglo de la regla de 10 s (`sesion_robotat.py`, en CRLF, con respaldo).
2. Aplicar el arreglo de la obediencia (`tesis/PROPUESTA_obediencia_obstaculo.md`).
3. Volver a correr el conjunto de confirmación. Si pasa: L0 → L1 → L2.

**Sin resolver:** la colocación autónoma no ve al 7; el retroceso va sin CBF y lo cubre el freno a 0.60 m; los offsets del 7 y del 4 son los de la tabla.

**Artefactos:** `controllers/coordinador_enjambre/resultados_demo_obstaculo/`, con:
- `fase0_20261002_165649/` (final) y `fase0_20261001_134427/` (diseño previo);
- `exploracion_fase0/`;
- `regla_estancamiento_*`, `manifiesto_sha256_pre_20261001.txt` y `sha256_codigo_congelado_20261002.txt`.

**Batería existente:** 344, 343 OK + la falla conocida por dependencia de orden (`test_el_ancho_medido_es_el_de_la_franja`, que pasa sola). **Respaldo de esta bitácora:** `BITACORA_TECNICA_respaldo_20261001_preObstaculoMovil.md`.


### Adenda (2026-10-02, noche): los dos arreglos, 2.ª confirmación y ensayo de la L2

**Con OK de José**, aplicados con respaldo:
1. **Regla de 10 s** (`sesion_robotat.py`, CRLF conservado 3866/3866; respaldo `sesion_robotat_respaldo_20261002_preEstancamiento.py`): `t_ref = max(t_mov, t_inicio_orden + 1.0 s)` con histéresis de 1.0 s sin orden (`MARGEN_RETARDO_ESTANCAMIENTO_S`, `CORTE_ORDEN_ESTANCAMIENTO_S`). 0/50 válidos del 30-09 cambian. La copia de la regla en `_correr_escalon` queda como estaba. Pruebas nuevas en `test_regla_estancamiento.py` (5).
2. **Obediencia del obstáculo** (`demo_obstaculo_movil.py`; respaldo `..._respaldo_20261002_preObediencia.py`): `velocidad_obstaculo()` devuelve `None` sin estimación y la verificación exige 5 decisiones seguidas. **La barrera no cambió:** la fila recibe el mismo v̂ (`_velocidad_o_cero`).

**2.ª corrida de la confirmación (decide): PASA.** 116/116 válidas y completas, todas > 0.15 m, mínimo **0.1815 m** (C5 encierro en trío, sin rampa, τ 0.85). La 1.ª no había pasado (115/116) por el falso positivo de la obediencia. Pareadas, la diferencia es la variabilidad del simulador: mediana |Δ| 0.25 mm, p90 1.4 cm, máx 5.5 cm.

**Dos validez:** la de la medición decide (116/116); la de la toma de demo excluye el freno (112/116). Los 10 frenos de las tres corridas fueron en encierros guionados, a 0.245–0.250 m; en las 120 tomas con política, ninguno (mínimo 0.2696 m).

**Ensayo de la L2 en el simulador** (`ensayo_l2_simulador.py`, 10 tomas, freno activo): 10/10 válidas para la demo en 11 intentos, 0 frenos, mínimo 0.2967 m. El intento 2 se cortó por antigüedad de pose > 150 ms (hipo del simulador cargado).

`verificar_cifras_fase0.py` con las dos carpetas: 160/160. Batería existente después de los arreglos: 344, 343 OK + la falla conocida. Pruebas de la fase: 39/39.

**Sigue:** L0 → L1 → L2 en el laboratorio, según `tesis/PROTOCOLO_L0_L2.md` (L2 con 10 tomas y el criterio fijado antes de la sesión). **Respaldo de esta bitácora antes de la adenda:** `BITACORA_TECNICA_respaldo_20261002_preConf2.md`.


### Adenda (2026-10-03): revisión adversarial del reporte y del protocolo

Fueron 7 verificadores de sólo lectura sobre las afirmaciones cualitativas; las cifras ya estaban verificadas.

**Confirmado:**
- la barrera recibe el mismo v̂, bit a bit en 300 000 historias;
- la regla de 10 s sólo quita cortes (fuzz de 40 000 trazas sobre los fragmentos reales);
- `_correr_escalon` no cambió;
- las validez coinciden con el código;
- el CLI y la L0;
- la cita de Molnar et al. (2023), contra Crossref.

**Corregido en los documentos:**
1. **Mecanismo del encierro.** El escape NO es lo que saca al agente. Con la nominal quieta, el (0,0) del rescate de nivel 2 cumple la fila relajada sin que el CBF intervenga, y el detector de escape (que exige intervención) no se arma. El primer escape llega después del mínimo: decisión 146 contra 87 en E5, y 195 contra 139 en el mixto. La separación la recupera el filtro rescatado. En el trío, el mínimo lo marca el agente del medio (B).
2. "Bit a bit la del Exp O" vale para F1; la L1 corre F2, que evalúa la geometría del Exp O en la pose predicha.
3. **Las reglas de parada de la L2 NO están en el programa:** las aplica el operador, con Enter retenido o Ctrl+C. El protocolo ahora lo dice, y también cómo relanzar.
4. Cambios no declarados entre las dos corridas, ninguno en la barrera:
   - la réplica de la regla de 10 s en el demo (cambió la definición de `corte_estancamiento_paso`);
   - la traza;
   - 2 líneas de `correr_fase0_obstaculo.py`, el `None` del disparo. Deshaciéndolas se reproduce el sha256 de la 1.ª corrida.
5. Se declara la prueba de humo de 4 corridas de la confirmación, hecha 15 s antes de la 1.ª corrida, sin cambios entre ambas.
6. Mediana del ensayo: 0.3155, no 0.3190. Se corrigió `statistics.median` en `analizar_sesion_demo.py`.
7. Otros:
   - pruebas 34 + 5;
   - `_correr_escalon` en `:3349-3361`, una regla análoga y no idéntica;
   - las dos propuestas quedan marcadas como aplicadas, con su nota de aplicación (obediencia: un trabado aborta a los 1.5 s, no a los 2.0 s).

`verificar_cifras_fase0.py`: 194/194. Evidencia en `resultados_demo_obstaculo/revision_adversarial_20261003/`. Las propuestas de código que salieron de la revisión esperan el OK de José y no tocan la barrera: reglas de parada automáticas, reanudar la sesión, resumen de la L0 en un archivo y docstrings. **Respaldo antes de esta adenda:** `BITACORA_TECNICA_respaldo_20261003_preRevision.md`.


### Adenda (2026-10-03, mediodía): reglas de parada automáticas y otros tres cambios en `demo_obstaculo_movil.py` (OK de José)

**Por qué:** una toma con contacto pasaba sola a la siguiente, y detenerla dependía del operador mirando la consola. La regla de parada es la prioritaria, por seguridad.

**Respaldos:**
- `demo_obstaculo_movil_respaldo_20261003_preParadas.py`, que es el código de la 2.ª confirmación, con el mismo sha256;
- `..._preLatido.py`, el del ensayo intermedio.

**Qué cambia:**
1. `regla_de_parada`, después de cada toma corrida, válida o no. Mira contacto (< 0.15 m medido), freno en 2 tomas corridas seguidas, aborto por el obstáculo o caída de su enlace durante la toma, y toma sin distancia medida.
   - Si se cumple una, la sesión frena todo, sigue frenando con un latido mientras espera y avisa si no pudo confirmar la detención.
   - Sólo sigue con una "s"; si no, veredicto DETENIDA.
   - La regla y la respuesta quedan en el CSV.
2. `--intento-inicial` para reanudar una sesión. El analizador junta los CSV.
3. Resumen de la L0 en archivo, en todos los caminos.
4. Docstrings: el freno a 0.25 m y como capa REDUNDANTE.

**Qué no cambia, por AST sin docstrings:**
- sólo cambian `sesion_demo`, `sesion_l0` y `main`, más funciones nuevas;
- la barrera, `correr_toma` y `validez_demo` son idénticos;
- **no se repitió la confirmación.**

**Revisión adversarial de los cambios:** 5 revisores (`revision_adversarial_20261003/paradas/`). Confirmaron la restricción, y se corrigió:
- la espera sin latido;
- el cartel sin confirmar la detención;
- la caída del enlace del 7 tapada en la última decisión;
- el hipo de poses rotulado como aborto del 7;
- "si" aceptado como "s";
- el resumen de la L0 abortada;
- las pruebas débiles.

**Pruebas:** 23 nuevas. Una por regla, unitarias y por la sesión completa. Con tomas REALES (sin barrera, kamikaze), la regla se dispara: contacto, y contacto más dos frenos seguidos. Un mutante sin la detención antes de la pregunta hace fallar la prueba. **Suite de la fase: 62/62.** Las pruebas encontraron antes de usarlo un nombre que pisaba el diccionario del episodio: la sesión se habría caído en la 2.ª toma.

**Ensayo de la L2 repetido:**
- intermedio: 10/10 en 10 intentos, mín 0.2996;
- final: 10/10 en 12 intentos, mín 0.3021, con 2 cortes por antigüedad de pose del lazo que, como corresponde, no detienen;
- 0 frenos y ninguna regla disparada sin motivo en 22 tomas.

**El reporte, corregido a pedido de José:** con el freno en sombra, la separación la sostuvo el filtro con su rescate. El freno habría actuado como capa redundante; no es lo que evita el choque. Esto corrige lo que dicen las entradas anteriores de esta bitácora ("ahí actúa el freno de respaldo").

**Cifras:** `verificar_cifras_fase0.py` da 213/213. **Respaldo antes de esta adenda:** `BITACORA_TECNICA_respaldo_20261003_preParadas.md`.


### Adenda (2026-10-07): colocación automática en la demo (Fase B), robot 4 y offset en la L0

**Decisiones de José:**
- el robot 4 como obstáculo, porque el 7 lo usa otro compañero;
- colocación automática en todas las etapas, con OK al plan (`tesis/PROPUESTA_colocacion_autonoma_obstaculo.md`);
- en la L2 el 4 arranca de la proyección de su pose sobre el círculo;
- su offset se mide en la L0, y si difiere más de 3° se frena antes de la L1;
- la L1 con el 4 encendido;
- no repetir la confirmación;
- no recortar las fallas inyectadas ni los ensayos con τ = 0.85 s;
- primero la Fase B.

**Implementado (Fase B):**
- `colocacion_con_obstaculo.py`, nuevo: los agentes van solos alrededor del 4 **quieto**.
  - Blancos a ≥ 0.65 m del 4 medido.
  - Rodeo por el lado libre de agentes quietos.
  - Fila del Exp O como barrera fija.
  - Vigilancia del 4 (quietud, frescura, congelamiento, enlace) y de los enlaces de los agentes; contacto.
  - Espera de quietud del 4, de hasta 3 s.
  - Envolvente de la Fase 0.
- En `demo_obstaculo_movil.py`:
  - `--colocacion auto`;
  - `--robot-obstaculo` obligatorio;
  - L1 con el 4 conectado y vigilado (`quieto_conectado`);
  - la regla de parada también en la colocación;
  - el offset del 4 medido en la L0 (`estimar_error_offset`), y la L1/L2 que no arranca sin una L0 OK con el offset a ≤ 3° (`l0_habilita`).
- **AST, sin docstrings:** la barrera, `correr_toma` y `validez_demo` quedan idénticos.
- **Respaldos:** `demo_obstaculo_movil_respaldo_20261007_preColocacion.py` y `PROTOCOLO_L0_L2_respaldo_20261007_preColocacion.md`.
- `colocacion_autonoma.py` y `sesion_robotat.py` sin tocar.

**Hallazgos:**
1. **Falso "NO FRENA" con τ = 0.85 s,** encontrado por el ensayo y corregido. El 4 sigue andando después del fin de la toma por su retardo, y la colocación lo veía moverse.
2. **Revisión adversarial,** del plan y del código, 3 + 3 revisores. Se corrigió:
   - el enlace del 4 que se caía sin freno;
   - el bloqueo frontal;
   - un falso "marcador congelado";
   - el Enter de más;
   - la ventana de quietud;
   - el enlace de un agente que se cae, que va más allá del plan pero es una guarda de seguridad.
3. **En un ensayo intermedio con τ = 0.85 s, 1 freno de respaldo** en una toma con política (mínimo 0.2093 m), con un simulador con zona muerta que la Fase 0 no tenía. En los ensayos finales, ninguno. Con un solo caso no se puede atribuir.
4. **Margen agente–agente en la colocación:** 0.1582 m con τ = 0.85 s. Cumple > 0.15 por 8 mm. Es la barrera 50/50 heredada de `colocacion_autonoma`, la misma del laboratorio desde el 22-09.
5. **Un agente pegado a una pared** no se mueve con la zona muerta: es un límite heredado, y en el laboratorio el reintento pide moverlo a mano.

**Ensayos finales** (L2 y L1, τ = 0.85 y 0.45, zona muerta, el obstáculo con 0.85): 26/26 tomas válidas en 27 intentos, 0 frenos, 0 paradas, el 4 nunca a mano. En la verdad, ≥ 0.3052 m al obstáculo y ≥ 0.1582 m entre agentes.

**Pruebas:** 102/102. **Reporte:** `tesis/REPORTE_2026-10-07_colocacion_automatica.md`, con su zip y `verificar_cifras_colocacion.py`.

**Pendiente:** la Fase A (que el 4 se mueva solo), a decisión de José. Sin ella, el 4 se coloca a mano en la L0, en el centro de la L1 y en la 1.ª toma de la L2.

**Respaldo antes de esta adenda:** `BITACORA_TECNICA_respaldo_20261007_preColocacion.md`.

### Campaña de medición L2 con el obstáculo móvil: lo de antes del laboratorio (2026-10-08/09)

**Decisión de José (08-10):** la L2 deja de ser sólo una demo y pasa a ser una campaña de medición como la evaluación del 30-09: tomas medidas en el Robotat, réplica pareada en simulación y análisis fijado antes. El video sale de las mismas tomas. La Fase A sigue fuera. Plan, ocho decisiones y cuatro ajustes: `tesis/PROPUESTA_campana_L2_obstaculo.md`.

**Qué se hizo** (todo en `controllers/coordinador_enjambre/` salvo lo indicado):
- `campana_obstaculo.py` (nuevo): el libro de la campaña, en `resultados_demo_obstaculo/campanas/<nombre>/` (`campana.json` + `libro.csv`, que sólo crece).
  - Semilla del intento k = 421000 + k − 1 (bloque nunca usado), reservada antes de colocar; una reserva sin resultado queda "interrumpida" y su semilla gastada.
  - Meta 50 incluidas, mínimo 30, tope 100 intentos, hora de fin por sesión; la cadena de dos frenos seguidos se arrastra con el libro.
  - Inclusión: válida para la medición Y el 4 recorrió ≥ la mitad de lo comandado (sólo si lo comandado es ≥ 0.20 m). Frenos y contactos no excluyen.
  - sha256 de los archivos congelados (el código que carga una sesión, el modelo, el plan, el script de análisis, el verificador y una huella de `config_robotat.py` sin la configuración del día); corrección, cierre y liberación del candado con motivo escrito.
- `demo_obstaculo_movil.py`: el registro de cada toma con las mismas columnas que el 30-09 (`columnas_registro_toma`, igual bit a bit al bloque de `sesion_robotat.py`, prueba con `ast`), más la pose medida del 4, `rpm_aborto`, `tau_prediccion_s`, `decisiones_previas` e `id_sesion` en los tres CSV; el modo campaña (`--campana`, `--crear-campana`, `--hora-fin`, `--corregir-campana`, `--cerrar-campana`, `--liberar-candado`), que exige la L0 OK sin que `--forzar` la saltee.
- `tesis/PLAN_ANALISIS_campana_L2.md`, `analizar_campana_l2.py` y `verificar_campana_l2.py` (nuevos): el análisis fijado (principal: brecha de cobertura hw − réplica pareada por toma con IC95 t; sensibilidades A–E; seguridad sobre todas las corridas; costo del obstáculo; 30-09 descriptivo) con el contrato de columnas de la réplica, y un verificador que recalcula las cifras con código propio. El 30-09 se reproduce desde el crudo: 0.3452 ± 0.0428, +0.0077 [−0.0046, +0.0200] por pares, +0.0123 [−0.0073, +0.0318] por escenario, d_pared −0.0355 [−0.0404, −0.0306].
- `ensayo_campana_simulador.py` (nuevo): el ensayo 1e por el mismo camino que el laboratorio (`main` con `--campana`).
- `tesis/PROTOCOLO_L0_L2.md`: sección "L2 como campaña de medición".
- **AST contra el respaldo previo a la campaña:** cambian `sesion_demo`, `_colocar_toma_automatica`, `main`, `sesion_l0` y `l0_habilita`, más funciones nuevas. La barrera (`FiltroConObstaculo`, `CoordinadorConObstaculo`), `SupervisorObstaculo`, `correr_toma`, `validez_demo`, `regla_de_parada`, `aplicar_regla_de_parada` y `estimar_error_offset` quedan idénticos. `sesion_robotat.py` sin tocar.

**Revisión adversarial** (4 revisores: libro, registro, análisis, plan y protocolo; ~45 hallazgos). Se corrigió, entre otras cosas:
1. **Un Ctrl+C en la pausa de seguridad perdía una toma que ya había corrido:** quedaba "interrumpida", es decir excluida (justo el caso con contacto, un canal de sesgo) y cortaba la cadena de frenos. Ahora la toma se anota siempre (`parar_y_cerrar`), con la respuesta "interrumpida (Ctrl+C) en la pausa".
2. **`config_robotat.py` entero quedaba fuera del bloqueo,** con la rampa, el rpm, la antigüedad de pose y el mapeo. Ahora sólo los offsets y la calibración del mocap son configuración del día (lo que dijo José); el resto entra con la huella `#sin_calibracion` y bloquea.
3. Los offsets del día se anotaban antes de aplicar la calibración: ahora se aplica antes de abrir.
4. El modo campaña aceptaba `--factor`, `--decisiones`, `--colocacion` y `--forzar`: ahora los rechaza, y el análisis comprueba el régimen de cada toma (factor, F2, τ_c, colocación, lazo, robots).
5. El libro: una línea truncada por un corte dejaba el libro ilegible tras la escritura siguiente; un `libro.csv` abierto en Excel dejaba el candado huérfano; cerrar o corregir desde otra consola ignoraban la sesión abierta; la cabecera se podía editar sin rastro; la hora de fin no cruzaba la medianoche. Todo corregido.
6. El análisis: una reserva colgada impedía analizar una campaña cerrada; el cierre (b) contaba como falla una corrida abortada sin evaluar y confiaba en la bandera de la réplica; una réplica incompleta pasaba en silencio; faltaba verificar el sha256 de `campana_obstaculo.py`; el verificador independiente, que la propuesta congelaba antes de la primera toma, faltaba. Todo corregido.
7. Una L0 del simulador o medida contra otro offset habilitaba la campaña: ya no.

**Verificación:**
- Pruebas: campaña 34/34, análisis y verificador 20/20, demo 96/97 en la corrida completa (la falla, el aborto por marcador congelado del 4 que salió por antigüedad de pose con la máquina cargada, pasa 6/6 aislada; el código del supervisor y de `correr_toma` es idéntico), las otras 9 suites OK.
- **Ensayo 1e,** campaña de ensayo en el simulador (zona muerta, τ agentes 0.45 / obstáculo 0.85, meta 5): crear, corte con Ctrl+C en la sesión 1, reanudación hasta META en la sesión 2, cierre. Con el código revisado (`resultados_demo_obstaculo/ensayo_campana_20261009_185745`): semillas 421000–421006 sin repetir, el intento 3 interrumpido, 1 toma no válida (antigüedad de pose) excluida con su motivo, auditoría del registro sin problemas (x0 contra el paso 0 ≤ 1 mm, pose del 4 contra la traza, rampa contra la suma acumulada, `id_sesion` en los tres CSV), análisis con réplica FALSA que recupera lo sembrado, verificador independiente 102/102. Verdad: ≥ 0.2877 m agente–obstáculo y ≥ 0.2244 m entre agentes. El ensayo con el código previo a la revisión también pasó (`ensayo_campana_20261008_200039`).
- **Hallazgo lateral, no corregido (fuera del plan):** `main --simulador` aplica la calibración guardada del laboratorio (offset de rumbo ~92°, escala 1.0167) al simulador, que no la tiene. El primer intento del 1e (`ensayo_campana_20261008_195824`, se conserva) gastó los 15 intentos con el 4 fuera de su envolvente por eso. El ensayo impone la calibración identidad después de `_preparar`, como `replica_con_capas.py`.

**Pendiente:**
- José: la propuesta prometía cerrar la campaña "con un criterio de seguridad fijado ahora"; la decisión 4 sólo pide motivo escrito. Falta su respuesta.
- La réplica con obstáculo (`replica_con_obstaculo.py`): escribirla y probarla con los ensayos del 07-10; sobre las tomas de la campaña corre sólo después de cerrarla.

**Respaldos:** `demo_obstaculo_movil_respaldo_20261008_preCampana.py` y `_preRevision.py`, `campana_obstaculo_respaldo_20261008_preRevision.py`, `analizar_campana_l2_respaldo_20261008_preRevision.py`, `tesis/PLAN_ANALISIS_campana_L2_respaldo_20261008_preRevision.md`, `tesis/PROTOCOLO_L0_L2_respaldo_20261008_preCampana.md` y `_preRevision.md`; antes de esta adenda, `BITACORA_TECNICA_respaldo_20261009_preCampana.md`.

### Campaña L2: criterio de cierre de seguridad, tomas cortadas y réplica con obstáculo (2026-10-09/10)

**Decisión de José (09-10), las dos cosas separadas:**
1. Criterio de seguridad fijado en el plan: la campaña se cierra SOLA si se acumulan dos tomas corridas con contacto (< 0.15 m entre centros medidos, con el obstáculo o entre agentes). Las pausas siguen como están; los contactos de la colocación no cuentan (siguen siendo regla de parada de la sesión).
2. Cualquier otro cierre anticipado (robot dañado, falla del laboratorio, sin más turnos) es el comando con motivo escrito.
Ninguno mira la cobertura; los dos quedan en el libro y en el reporte.

**Implementación** (`campana_obstaculo.py`, `demo_obstaculo_movil.py`, `analizar_campana_l2.py`, `verificar_campana_l2.py`, `tesis/PLAN_ANALISIS_campana_L2.md` §2, `tesis/PROTOCOLO_L0_L2.md`):
- `contacto_de_toma`: `d_min_obst_medida` < 0.15 o `colisiones_015` > 0 (pares distintos sobre poses medidas, la misma definición del 30-09). Columnas nuevas del libro `contacto` y `colisiones_015`.
- El libro aplica el criterio al registrar la segunda toma con contacto (escribe `cierre_campana` con el prefijo "CRITERIO DE SEGURIDAD", los intentos y el detalle), y también al abrir una sesión sin candado y al cerrar (por un corte entre esa toma y su cierre). La sesión no corre ningún intento más. Un cierre manual no puede usar ese prefijo.
- El análisis recalcula los contactos del crudo, verifica que el cierre vino después de la segunda toma con contacto sin reservas en el medio (código 4 si no), hace el recuento FÍSICO (también con las tomas que el libro no pudo anotar, por su fila o por sus decisiones) y declara INCUMPLIMIENTO si hubo reservas después del cierre debido. El verificador lo recalcula por su cuenta.

**Dos verificaciones adversariales del criterio** (3 lentes + un escéptico por hallazgo; la primera se cortó a medias por el límite de uso y se repitió completa). Se corrigió:
1. "Toma corrida" quedaba como "anotada en el libro": una toma cortada A MITAD (Ctrl+C al ver un contacto, caída de enlace) no la contaba el libro y la campaña seguía. Ahora la sesión la atrapa, frena, arma su fila parcial con lo que alcanzó a correr (`fila_toma_cortada`: decisiones, distancia mínima medida hasta ahí, pares < 0.15 m) y la ANOTA antes de relanzar el corte. Sólo un corte duro (corte de luz) queda fuera del libro; el análisis lo recuenta desde los CSV.
2. La toma que dispara una regla de parada se anota ANTES de la pausa (la respuesta va en una fila `pausa` del libro): si el proceso muere esperando la respuesta, el criterio igual la cuenta. Las pausas no cambian.
3. Una sola definición de "toma corrida" en el libro, el criterio y la seguridad del §4a.
4. Detalles: textos viejos del plan y del docstring que contradecían el cierre automático; el libro se niega a escribir en un archivo de formato viejo; la definición de incumplimiento ("hubo intentos después del cierre debido"); la salida muestra siempre el recuento físico; el verificador recalcula también el incumplimiento.

**La réplica con obstáculo** (`replica_con_obstaculo.py` + `test_replica_con_obstaculo.py`, nuevos; diseño de 5 lectores + crítico en `resultados_demo_obstaculo/revision_adversarial_20261003/entender_replica_20261009/`):
- La misma pila del laboratorio (F2, `correr_toma` con el lazo de evaluación) contra el simulador con retardo cero y calibración identidad. `SimuladorReplay`: la física no integra al 4 (un dict cuyo `values()` lo omite). `SupervisorReplay`: manda el (v_cmd, w_cmd) grabado, coloca al 4 en hw[0] al reiniciar y en hw[k+1] al final de la decisión k (la fuente lo ve en la consulta de la decisión siguiente), freno en sombra. Sin obstáculo: el mismo coordinador con `supervisor=None` y el 4 estacionado fuera del alcance del mocap.
- Cierre (a1): por AST, la inversa de marcos, la calibración identidad y la regla de la rampa son las de `replica_con_capas.py`; y a nivel de decisión, sin red ni tiempo real, la pila sin obstáculo decide BIT A BIT igual que la del 30-09 ante las mismas observaciones (500 decisiones de s1 ep 5, y las 500 de s2 ep 1 con la rampa de 50): observación, acciones, escape, CBF, rpm y cobertura. `correr_toma` le pasa a `_correr_episodio` los mismos 11 argumentos que el 30-09.
- Cierre (b), en tiempo real: la toma 1 de `ensayo_campana_20261009_185745` y la toma 6 de `ensayo_L2_auto_20261007_121157` (con freno del 4) dieron error 0.0 m, desfase 0, rumbo 2.2e-16 rad y mandos idénticos; el freno (v_cmd = 0 en los pasos 327–393) se reproduce exacto. `--verificar` carga y audita las 5 tomas del ensayo de campaña y las 32 del 07-10.
- **Revisión adversarial de la réplica** (4 lentes + escéptico; 10 confirmados, 2 refutados). Se corrigió: la réplica sale con código 3 si queda incompleta o sin la pasada suplementaria; se niega a reanudar sobre corridas de otra pila, de la FALSA o de otra campaña; `--solo-tomas`/`--reps` exigen una `--salida` propia; la auditoría compara los robots y la pose inicial contra el paso 0 y la traza; y el análisis exige la réplica completa y de una sola pila (plan §7). Cinco mutaciones que pasaban las pruebas ahora las rompen.

**Verificación:** campaña 42/42, análisis 30/30, réplica 30/30, demo 97/97; las 12 suites completas en la tanda previa (511/511). Ensayo 1e final (`resultados_demo_obstaculo/ensayo_campana_20261009_213224`): META, corte y reanudación, auditoría sin problemas, verificador independiente 106/106.

**Pendiente (de José), antes de crear la campaña:**
- ¿Una toma corrida sin distancia medida al obstáculo cuenta como contacto? (Lectura escrita en el plan, "a confirmar": no; sus pares de agentes sí.)
- La regla del cierre (a3) (propuesta: 12 episodios del 30-09, la última aparición válida de cada semilla; pasa si el IC95 de la media de Δ queda dentro de ±0.00827, el desvío dentro de episodio agrupado de la réplica del 30-09).
- Si el cierre (b) exige también rumbo y mandos idénticos (así está implementado).

**Respaldos:** `*_respaldo_20261009_preCriterio`, `*_respaldo_20261010_preFidelidad`, `*_respaldo_20261010_preCortadas`, `*_respaldo_20261010_preRevisionReplica` (código, plan y protocolo); antes de esta adenda, `BITACORA_TECNICA_respaldo_20261010_preCriterioReplica.md`.

### Campaña L2: respuestas de José del 10-10, auditoría final y cierre (a3) (2026-10-10)

**Respuestas de José (10-10), textuales:**
1. "Una toma corrida sin distancia medida al obstáculo no cuenta como contacto para el criterio. Sus pares de agentes sí cuentan. Quitá el 'a confirmar' del plan."
2. "Apruebo la regla de a3 tal como está, con dos condiciones: corre con la máquina libre, como la réplica del 30-09, y si no pasa se investiga antes de correr la réplica de la campaña, sin cambiar el margen."
3. "El cierre b exige también rumbo ≤ 1e-6 rad y mandos idénticos, como lo implementaste."
4. "Con eso, dejá la campaña lista para crearse antes de la primera toma. El a3 corrélo antes del laboratorio si la máquina está libre."

**Dónde quedó cada una:**
- (1) en el plan §2 (sin el "a confirmar"), en el docstring de `contacto_de_toma` y en el criterio del protocolo; una prueba nueva cubre "sin distancia + pares".
- (2) en el plan §7 (con las dos condiciones), en `A3_ESTADO` y en el bloque "Réplica y cierres" del protocolo.
- (3) en el plan §7 y en `CIERRE_B_RUMBO_MAX_RAD`; el análisis y el verificador lo aplican igual.

**Auditoría final antes de crear la campaña** (4 lentes: trazabilidad, plan↔código, protocolo, congelados; un escéptico por hallazgo). Resultado: 27 hallazgos, 26 confirmados (9 de severidad media, 17 baja) y 1 refutado. El refutado: el verificador no dispensa el sha256 por un desvío; es lo correcto, porque si no el análisis se certificaría a sí mismo. Se corrigió:
- **Cierre (a3):**
  - `evaluar_cierre_a3` exige los 12 episodios completos (reps 1–3, o la suplementaria 4–6) y una sola pila; si no, da SIN VEREDICTO.
  - Cada evaluación queda en un archivo nuevo `cierre_a3_<fecha_hora>.json`.
  - Sale con 0 (PASA), 1 (NO PASA) o 3 (incompleto).
- **Cierre (b):**
  - Una corrida con 0 decisiones no tiene cierre (b): es una repetición inválida y no excluye la toma. Es convención propia, a confirmar con José; quedó escrita en el plan §7.
  - El motivo de exclusión nombra la corrida, la bandera, el error, el desfase, el rumbo y los mandos.
- **Análisis:**
  - Exige meta, mínimo y tope de 50/30/100; con otros valores se niega, salvo un desvío.
  - Una réplica parcial con `--desvio` se declara en vez de detenerse.
- **Verificador:** `--dir-hw`, `--dir-replica` y `--dir-3009`; un paquete movido de carpeta se verifica N/N.
- **Demo:**
  - Los CSV de la sesión se escriben en forma atómica (temporal, fsync, `os.replace`), con 60 reintentos de 0.5 s y aviso si están bloqueados.
  - El crudo de la toma va a disco ANTES de anotarla en el libro.
  - La sesión de hardware exige la ruta del script y que su sha256 sea el congelado de la demo: un respaldo corrido por error se niega.
  - Se actualizaron el docstring y el `--help`.
- **Textos:**
  - Protocolo: encabezado con el 09 y el 10-10; la regla de José; la pausa ("n" para terminar, "s" sólo con la causa resuelta); el corte duro (pierde la toma: los CSV se escriben al terminar cada intento); Excel; la calibración del mocap del día con el robot 1; el bloque "Réplica y cierres"; no usar `--meta`/`--minimo`/`--tope-intentos`; y el chequeo previo a crear ("IGUAL a lo probado", contra la pila del a3).
  - Plan: la base; el corte duro en el §2; en el §7, la suplementaria (3 repeticiones, como número del plan) y la convención n = 0; en el §8, el mapeo de la calibración y el verificador con desvío.
  - Propuesta: la línea de estado, APROBADA.
- **Sin cambio de código:** la calibración del día hecha con otro robot. La frenan la L0 o la colocación, o si no el análisis por régimen; el protocolo pide hacerla con el robot 1.

**Incidente del a3:**
- El primer lanzamiento (07:06) se detuvo a las 2 corridas con "cambió la pila durante la réplica": edité el plan, que está en la pila, mientras corría. La guarda funcionó.
- Queda como registro en `resultados_demo_obstaculo/replica_campana/cierre_a3_20261010/` (2 corridas, pila 1d1f1944…, SIN VEREDICTO).
- El a3 que vale es el de `cierre_a3_20261010_b/`, lanzado después de las suites con la pila final, con la máquina libre.

**Verificación con el código y el plan finales:**
- **13 suites, 555 pruebas OK.**
  - En la primera tanda fallaron 3 pruebas de tiempo real (`test_registro_de_dos_tomas`, `test_corte_y_reanudacion_sin_repetir_semillas` y `test_l1_automatica_con_el_obstaculo_conectado`), todas por "antigüedad de pose sobre el umbral": una toma no válida y, por eso, un intento de más.
  - Ninguna función cambiada hoy corre durante una toma. Solas pasan las tres, y las dos suites repetidas completas dan 44/44 y 97/97.
- **Ensayo 1e** (`resultados_demo_obstaculo/ensayo_campana_20261010_081427`): META, con corte y reanudación, el registro sin problemas y el verificador independiente 106/106.

**Cierre (a3): NO PASA** (`resultados_demo_obstaculo/replica_campana/cierre_a3_20261010_b/cierre_a3_20261010_091454.json`).
- La corrida: 36/36 válidas, completa, una sola pila (b5a28904…).
- E = 12 y media Δ = −0.00252, con IC95 [−0.01052, +0.00549] contra ±0.00827: el límite inferior queda fuera.

**Investigación** (condición de José: antes de la réplica de la campaña, sin cambiar el margen). Scripts y salidas en `cierre_a3_20261010_b/diagnostico_20261010/`.
- **Lo deciden dos episodios.** Los otros 10 dan |Δ| ≤ 0.004, y 8 de ellos ≤ 0.002.
  - **s05 ep 2, Δ = −0.0404.** El 30-09 dio 0.326, 0.329 y 0.332; las reps nuevas, 0.322, 0.277 y 0.268. Dos cayeron en un modo bajo; se separan en más de 5 cm hacia el paso 207.
  - **s05 ep 8, Δ = +0.0129.** El 30-09 dio 0.404, 0.410 y **0.377**; las tres nuevas, ~0.410. El Δ sale de la rep baja del 30-09.
- **La decisión es la misma.** A nivel de decisión, ante las mismas observaciones (las poses hw del 30-09), la pila nueva decide BIT A BIT igual que la del 30-09 en s05 ep 2, s05 ep 8 y s02 ep 12.
  - Coinciden las 2500/2500 filas, los rpm y la cobertura, en episodios con 255 a 1075 intervenciones del CBF y hasta 62 escapes.
  - La causa no está en la decisión ni en los archivos congelados.
- **El ruido entre reps es el del 30-09.** La réplica en tiempo real no es determinista entre reps: en todos los episodios se separan más de 1 mm entre los pasos 1 y 111.
  - Desvío mediano 0.0013 en las dos réplicas; máximo 0.029 contra 0.031.
  - El 30-09 ya tenía 6 episodios con desvío > 0.012, entre ellos s05 ep 8.
- **Tiempos.** El error de pose inicial es 0 en las dos y no hay ningún ciclo de más de 100 ms. El ciclo p95 es mayor ahora: 25.3 ms contra 20.8 ms en las mismas corridas del 30-09. No se puede separar si es la pila o la carga de fondo de la máquina.
- **Diagnóstico, no veredicto.** Si las coberturas nuevas y las del 30-09 fueran intercambiables (las 6 de cada episodio mezcladas):
  - la regla daría PASA el 61.5 % de las veces;
  - una |media Δ| como la observada aparece el 26 % de las veces;
  - el Wilcoxon de los 12 Δ da p = 1.0, con mediana Δ = +0.00009.
- **Lectura.** No aparece un error de la réplica. El NO PASA lo explican dos episodios caóticos (bimodales) y la potencia de la regla con 12 episodios × 3 reps. El veredicto queda NO PASA y el margen no cambia. **La réplica de la campaña no se corre hasta que José decida con esta investigación.**

**Lista para crearse:**
- La campaña NO está creada: exige la L0 OK del 4, en el laboratorio.
- Lo que se congela es lo probado hoy (las suites, el 1e y la pila del a3). El chequeo previo del protocolo tiene que dar "IGUAL a lo probado"; contra la pila del a3 interrumpido marca el plan, como debe.
- El NO PASA del a3 no toca ningún archivo congelado.

**Pendiente:**
- (de José) decidir con la investigación del a3. La réplica de la campaña corre después del cierre; crear la campaña no depende del a3.
- (de José) confirmar dos convenciones propias del plan §7: una corrida con 0 decisiones no tiene cierre (b) y no excluye la toma; la suplementaria son 3 repeticiones (la 4, la 5 y la 6).
- (laboratorio) L0 del 4 OK → chequeo "IGUAL a lo probado" → crear la campaña → primera sesión.

**Respaldos:**
- `*_respaldo_20261010_preDecisiones` y `*_respaldo_20261010_preAuditoria` (código y pruebas);
- `*_respaldo_20261010_preTextos` (plan, protocolo y propuesta);
- antes de esta adenda, `BITACORA_TECNICA_respaldo_20261010_preRespuestas.md`.

### Campaña L2: decisión de José sobre el a3 y las dos convenciones (2026-10-10, tarde)

**Decisión de José (10-10), textual:**
"Sobre el a3: sigue la réplica de la campaña, con tu investigación como respaldo.
- El veredicto queda NO PASA y se declara así en el reporte, con el diagnóstico: decisión bit a bit igual en los episodios que lo deciden, el mismo ruido entre repeticiones que el 30-09, y los dos episodios en direcciones opuestas (la bifurcación nueva de s05 ep 2 y la corrida baja del 30-09 en s05 ep 8). No se repite el a3 ni se cambia el margen.
- Su IC95 [−0.0105, +0.0055] va en el reporte como la cota de cuánto puede diferir la réplica nueva de la del 30-09: es una salvedad de la comparación descriptiva con el 30-09. El resultado principal no depende de eso.
- La réplica de la campaña corre con la PC limpia: sin Chrome, ChatGPT, Omen ni el servidor de Inventor. En el reporte, como descriptivo post hoc y rotulado así: el p95 del ciclo de la réplica y, en la variante sin obstáculo, cuántas tomas tienen desvío entre repeticiones > 0.01, contra 6 de 50 del 30-09.
Las dos convenciones del §7 quedan aprobadas: una corrida con 0 decisiones no tiene cierre (b) ni excluye la toma, y la pasada suplementaria son las repeticiones 4, 5 y 6.
Si para dejar todo esto asentado tenés que tocar el plan, hacelo ahora y actualizá la referencia del chequeo previo, para que el día del laboratorio dé 'IGUAL a lo probado'."

**Dónde quedó** (sin cambios de código):
- `tesis/PLAN_ANALISIS_campana_L2.md`:
  - en el encabezado, la base;
  - en el §6, la salvedad con el IC95 como cota;
  - en el §7, el resultado del a3 y la decisión, la PC limpia, los descriptivos post hoc con su definición operativa y las dos convenciones aprobadas;
  - en el §10, lo que el reporte agrega fuera del análisis fijado.
- `tesis/PROTOCOLO_L0_L2.md`: el encabezado; el a3 hecho; la réplica con la PC limpia; el reporte; y la referencia del chequeo previo.
- El "6 de 50" del 30-09 se verificó desde el crudo: desvío entre repeticiones > 0.01, con ddof = 1 y también con ddof = 0. La siguiente, s02 ep 7, queda en 0.00996.

**Dos rondas de verificación** (lentes independientes, sólo lectura, con un escéptico por hallazgo):
- **Ronda 1** (fidelidad, cifras, coherencia, completitud): 18 hallazgos, 8 confirmados (4 problemas distintos) y 10 refutados. Todas las cifras del texto nuevo se recalcularon desde el crudo y coinciden. Se corrigió:
  - en el §9, las columnas `cierre_b_*` van vacías también en una corrida con 0 decisiones (contradecía la convención aprobada);
  - el paréntesis del "6 de 50" asignaba mal el ddof;
  - el p95 entra sólo con las corridas con `decisiones` > 0 (las otras dejan 0 y bajarían la media);
  - el protocolo no decía cómo dejar la PC limpia ni comprobarlo.
- **Ronda 2** (arreglos, comandos, completitud): 13 hallazgos, 7 confirmados y 6 refutados. El chequeo de PC limpia no podía salir vacío: `OmenCap.exe` (servicio `HPOmenCap`) y `OmenInstallMonitor.exe` no se cierran desde la bandeja, y `OverlayHelper.exe` (OMEN Overlay) no entraba en el filtro.
  - El protocolo ahora los detiene como administrador (con `Stop-Service` para el servicio) y dice cómo se restauran; el filtro agrega `overlayhelper`. Se probó en modo lectura: detecta los 8 procesos que corren hoy.
  - Cada lanzamiento de la réplica se anota en la bitácora con su comprobación, y el reporte lo declara.
- Se tomó "sin Omen" al pie de la letra (también el servicio y las tareas). Si José quiere sólo cerrar la app, es cambiar el filtro.

**Referencia del chequeo previo:**
- Es el ensayo 1e repetido con el plan final (`resultados_demo_obstaculo/ensayo_campana_20261010_100632`): META, análisis 0, verificador 0 (106/106) y registro sin problemas.
- Su `campana.json` es igual a lo congelable hoy (22/22) y, contra la pila del a3 `_b`, difiere sólo en el plan (el cambio de texto de esta decisión).
- El comando del protocolo, con la ruta literal, da "IGUAL a lo probado".
- Las suites y el a3 corrieron con el mismo código.

**Respaldos:** `PLAN_ANALISIS_campana_L2_respaldo_20261010_preDecisionA3.md` y `PROTOCOLO_L0_L2_respaldo_20261010_preDecisionA3.md`; antes de esta adenda, `BITACORA_TECNICA_respaldo_20261010_preDecisionA3.md`.

### Protocolo: corriente, modo de energía y PC limpia antes de cada sesión (2026-10-10, tarde)

**Decisión de José (10-10), textual:**
"'Sin Omen' queda al pie de la letra, como lo dejaste.
Dos agregados al protocolo, que no está congelado:
1. Corriente: para la réplica y para cada sesión del laboratorio, la laptop enchufada y siempre con el mismo modo de energía de Windows. Que el chequeo previo a cada lanzamiento lo compruebe y lo anote en la bitácora junto con los procesos, para poder interpretar el p95 de cada corrida.
2. El mismo chequeo de PC limpia antes de cada sesión del laboratorio, no sólo antes de la réplica: en los ensayos, las tomas que se perdieron fueron por carga de la máquina.
No toques nada congelado: el chequeo previo tiene que seguir dando 'IGUAL a lo probado'."

**Dónde quedó** (sólo `tesis/PROTOCOLO_L0_L2.md`, que no está congelado; respaldo `PROTOCOLO_L0_L2_respaldo_20261010_preCorriente.md`):
- **Sección nueva antes de la L0:** "Chequeo previo de la PC, antes de cada sesión del laboratorio y de cada lanzamiento de la réplica". Cubre la L0, la L1, la L2, cada sesión de la campaña y, en la réplica, cada `--reanudar` o `--suplementaria`.
  - Corriente: enchufada, con el ahorro de energía apagado, y el mismo plan y modo que la referencia.
  - PC limpia: sin Chrome, ChatGPT, Omen ni el servidor de Inventor; "sin Omen" al pie de la letra.
  - Un bloque de PowerShell común, sin administrador, que imprime la fecha y hora, la corriente, el ahorro de energía, el plan, el modo y los procesos, y termina en `CHEQUEO OK` o `CHEQUEO FALLA: no lanzar`.
  - La salida se pega en la bitácora con la sesión o el lanzamiento y su comando.
- **Remisiones a la sección:** desde la L0 de "Antes de abrir la campaña", desde "Cada sesión" y desde el paso 2 de la réplica. El bloque viejo de la réplica pasó a la sección común.
- **El reporte** declara, según los chequeos de la bitácora, qué sesiones y lanzamientos corrieron con `CHEQUEO OK`.
- **Referencia del modo:** la que tenía la laptop el 10-10, el plan Equilibrado (`381b4222-f694-41f0-9685-ff5bb260df2e`) con el modo "Mejor rendimiento" enchufada (`ded574b5-45a0-4f42-8737-46345c09c238`). Si José elige otro, se cambia en el protocolo antes de la primera sesión.
- **La anotación en la bitácora es manual** (se pega la salida). Que el chequeo escriba solo en la bitácora sería un script nuevo: queda como opción, con plan en prosa y el OK de José.

**Chequeo de referencia del 10-10** (salida del bloque del protocolo, 15:07):
```text
chequeo previo de la PC: 2026-10-10 15:07:38
  corriente: enchufada | ahorro de energia: apagado
  plan: 381b4222-f694-41f0-9685-ff5bb260df2e (Equilibrado) | modo enchufada: ded574b5-45a0-4f42-8737-46345c09c238 (Mejor rendimiento)
  procesos: SystemOptimizer.exe [8580], OmenCommandCenterBackground.exe [17476], HP.OMEN.VirtualCamHelper.exe [6480], python.exe [15096], python3.13.exe [15352]
CHEQUEO FALLA: no lanzar
```
(FALLA esperada: OMEN Gaming Hub y la app de Claude abiertos. No se lanzó nada.)

**Verificación** (3 lentes, sólo lectura, con un escéptico por hallazgo): 12 hallazgos, 3 confirmados y 9 refutados. Se corrigió:
- `SystemOptimizer.exe`, el optimizador de OMEN, corre elevado y su nombre no contiene "omen". Se agregó al filtro y al comando de administrador (ahora son cuatro componentes que no se cierran desde la bandeja).
- El ahorro de energía de Windows 11 puede estar activo con la laptop enchufada: el chequeo lo lee (`GetSystemPowerStatus`) y exige que esté apagado.
- Si el plan no coincide, se corrige con `powercfg /setactive 381b4222-f694-41f0-9685-ff5bb260df2e`; desde Configuración sólo se cambia el modo.

El bloque se probó dos veces seguidas en la misma consola de PowerShell 5.1, extraído del protocolo tal como está escrito.

**Congelados:** el chequeo previo sigue dando "IGUAL a lo probado"; el plan no se tocó.

**Observación (no es regla):** el chequeo lee el modo de energía de Windows, que es lo que pidió José. El modo de rendimiento propio de OMEN Gaming Hub es otra cosa y no lo lee.

**Respaldos:** `PROTOCOLO_L0_L2_respaldo_20261010_preCorriente.md`; antes de esta adenda, `BITACORA_TECNICA_respaldo_20261010_preCorriente.md`.

### L0 del 4 en el laboratorio: tres intentos, último FALLO por la colocación (2026-10-16)

**Disponibilidad de robots:** primero se informó que estaban sólo el 1, 2, 3, 4, 5 y 8. Se evaluó sustituir el 6 y el 9 por el 2 y el 3 (exigía cambiar 3 congelados antes de crear la campaña). Se hicieron respaldos `*_respaldo_20261016_preRobots` y no se llegó a editar nada. Después aparecieron el 6 y el 9: el enjambre queda el del plan (1, 5, 8, 6, 9 con el 4 de obstáculo). Los siete archivos son idénticos a sus respaldos y el chequeo previo da "IGUAL a lo probado".

**L0** (`python demo_obstaculo_movil.py --modo L0 --robot-obstaculo 4`), en `resultados_demo_obstaculo/`:
- 19:48:27 y 19:49:02: FALLO, "marcador 4 congelado", con 0 arranques corridos. Si se repite, redefinir el cuerpo rígido 4 en Motive.
- 19:55:42: **FALLO.** Dio 10/10 arranques, ω saturado 0 % y offset de rumbo a −0.34° de la tabla (370 pares): el +81.90° de la tabla sirve. Lo que falla es el error radial máximo: 6.39 cm contra < 5 cm.
- **Diagnóstico** (traza `20261016_195542_L0_traza.csv`):
  - El 4 se colocó 7.3 cm hacia adentro del círculo (env (1.521, 0.973)), dentro de la tolerancia de ±8 cm. Corrige despacio, a ~0.5 cm/s, así que a t = 2 s (fin del enganche excluido) seguía a −6.39 cm.
  - Los arranques 1 y 2 siguen convergiendo (3.82 y 2.87 cm). Del 3 al 9 el error queda fijo en −2.0 cm (−1.91 a −2.23), igual en toda la vuelta: es un sesgo hacia adentro del seguimiento, no un centro corrido.
  - El FALLO es de la colocación, no del seguimiento.
- **Qué sigue:** repetir la L0 colocándolo más exacto en (1.50, 0.90), mirando +x. Cuenta la última L0, y los criterios no cambian.
- **Para José:** la tolerancia de colocación de la L0 (±8 cm) es más ancha que el tope radial (5 cm con 2 s de enganche). Con una colocación en el borde, la L0 falla aunque el 4 siga bien.
- **Pendiente:** confirmar si se corrió el chequeo previo de la PC antes de esta L0 y pegar su salida aquí.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261016_preL0.md`.

### L0 del 4: OK (2026-10-16, 20:29)

**Chequeo previo de la PC** (con la app de Claude cerrada; salida pegada por el operador):
```text
chequeo previo de la PC: 2026-10-16 20:26:17
  corriente: enchufada | ahorro de energia: apagado
  plan: 381b4222-f694-41f0-9685-ff5bb260df2e (Equilibrado) | modo enchufada: ded574b5-45a0-4f42-8737-46345c09c238 (Mejor rendimiento)
  procesos: ninguno
CHEQUEO OK
```
- Un chequeo anterior, a las 20:17:20, dio FALLA por `OmenCommandCenterBackground.exe` y `HP.OMEN.VirtualCamHelper.exe`, que quedaron huérfanos tras cerrar OMEN desde la bandeja, y por dos servidores de Inventor de dos sesiones de Claude.
- Se resolvió con `Stop-Process` como administrador y cerrando la app de Claude.
- Antes de la L0 de las 19:55 no consta ningún chequeo.

**L0** (`20261016_202910_L0_resumen.csv`):
- Veredicto **OK**: 10/10 arranques, error radial máximo 2.3 cm sin los 2 s de enganche, ω saturado 0 %, offset de rumbo a −0.1° de la tabla (370 pares).
- La colocación se corrigió una vez (estaba a 25.5 cm del punto de arranque).
- `l0_habilita(4)` → `(True, 'L0 OK, offset a -0.1° de la tabla (370 pares)')`.
- El offset +81.90° de la tabla queda confirmado por dos L0 (−0.34° y −0.1°).
- El chequeo de congelados sigue dando "IGUAL a lo probado".

**Sigue:** crear la campaña (`--crear-campana`) y la primera sesión, cada una con su chequeo de la PC y la hora de fin fijada por José antes de empezar.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261016_preL0OK.md`.

### Campaña L2, sesión 1 (16-10): sin tomas corridas; el robot 3 reemplaza al 6

**Creación:** `L2_obstaculo` se creó a las 20:31:08 (meta 50, mínimo 30, tope 100), con la L0 OK de las 20:29 y el chequeo de congelados en "IGUAL a lo probado".

**Sesión `L2_20261016_203129`** (hora de fin 21:00):
- **Intento 1** (semilla 421000): `parada_colocacion`, "CONTACTO antes de mover a nadie: robots 8 y 9 a 0.134 m". Habían quedado juntos de antes. No cuenta para el criterio de seguridad. Pausa: "siguió".
- **Intento 2** (semilla 421001): el robot 6 no avanzó en la colocación (cinco reintentos; había que golpearlo para que girara). Además, su marcador se congeló en (1.44, 1.85), después se perdió ("SIN POSE"), y hubo 147 rechazos de pose por inclinación.
  - El operador cortó con Ctrl+C durante la colocación: la reserva quedó "interrumpida" y la sesión se cerró limpia ("interrumpida (Ctrl+C)", sin candado).
  - Corridas: 0.
- **Cambio de robot** (decisión del operador en el laboratorio): sale el 6, entra el 3 como agente 3. Como no hay ninguna toma corrida, no se mezclan composiciones; el régimen del análisis sólo mira las tomas corridas.
- **Archivos.** Los respaldos previos son `*_respaldo_20261016_preRobots`, idénticos al estado anterior.
  - `config_robotat.py`: `MAPEO_AGENTES[3]` = (3, 3), con comentario.
  - `analizar_campana_l2.py`: `ROBOTS_AGENTES` = ("1", "5", "8", "3", "9").
  - Plan: base, "Qué se mide", régimen del §2, §6 (composición) y §8.
  - Protocolo: robots del enjambre; ni el 6 ni el 7 en la arena.
  - Pruebas no congeladas: `test_analizar_campana_l2.py` deriva ROBOTS del análisis; `test_replica_con_obstaculo.py` corre con el mapeo y el régimen de sus datos (1, 5, 8, 6, 9); `test_demo_obstaculo_movil.py` elige para la prueba de L0 sin conexión un robot que no es agente.
- **Verificación:** análisis 34/34, réplica 31/31, L0 4/4. Fuera del libro, cambian `TESIS/PLAN_ANALISIS_campana_L2.md`, `analizar_campana_l2.py` y `config_robotat.py#sin_calibracion`. Se declara con `--corregir-campana "motivo"` antes de la sesión siguiente.
- **Riesgos del 3:** su offset es el de la tabla (+89.82°), nunca medido. Salió el 22-09 por caídas de socket al manipularlo (9 y 11 sep), causa nunca investigada. Su marcador 3 tiene que estar trackeado en Motive.
- **Pendiente:** las suites completas y un 1e con el mapeo nuevo, cuando no haya laboratorio. Si aparece algo, se corrige con otra corrección declarada entre sesiones.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261016_pre3por6.md`.

### Campaña L2: el 3 no responde; entra el 2 (16-10, 20:45)

- **Corrección del 6 por el 3**, anotada a las 20:42:59 (cambiaron el plan, `analizar_campana_l2.py` y `config_robotat.py#sin_calibracion`).
- **Sesión `L2_20261016_204312`** (fin 21:15): se cerró a los 11 s por un error de conexión. El robot 3 (192.168.50.103:9090) no respondía en la red ("sin respuesta": la placa no sirve, según el operador). Sin reservas, sin tomas, sin candado.
- **Cambio del 3 por el 2** como agente 3 (decisión del operador). Respaldos `*_respaldo_20261016_pre2por3`.
  - `MAPEO_AGENTES[3]` = (2, 2) y `ROBOTS_AGENTES` = ("1", "5", "8", "2", "9"); el plan y el protocolo, ajustados.
  - Las pruebas no cambian (derivan del análisis o usan el mapeo de sus datos): análisis 34/34, réplica 31/31, L0 4/4.
  - Sigue sin haber tomas corridas: no se mezclan composiciones.
  - Se declara con otra `--corregir-campana "motivo"`.
- **Riesgos del 2:** offset de la tabla (+89.74°), nunca medido. Salió el 22-09 porque su marcador se congelaba en Motive (3 veces en 2 días, dos en env (0.56, 1.74)); en septiembre también tuvo un corte de socket y batería baja. La sesión lo detecta solo (marcador congelado al arrancar y retroceso).

### Campaña `L2_obstaculo`: CERRADA y DESCARTADA para el documento (2026-10-16, 21:07)

**Sesión `L2_20261016_204859`** (enjambre 1, 5, 8, 2, 9; fin 21:15). Tras la segunda corrección, la del 3 por el 2, anotada a las 20:48:51:
- **Intento 3** (semilla 421002): corrida, NO VÁLIDA. El marcador 5 se congeló en (0.27, 2.83), a 0.17 m de la pared, y seguía sin captura tras retroceder 2.2 s. Antes había retrocedido otra vez en (2.58, 2.75) y se recuperó. d_min obstáculo 0.341 m.
- **Intento 4** (semilla 421003): sin correr. El marcador 5 congelado en (0.27, 2.83) y en (0.53, 2.23); después, el 8 no avanzó y su marcador se congeló en (1.82, 1.87) y en (1.70, 0.99). Se agotaron los 5 reintentos.
- **Intento 5** (semilla 421004): corrida, NO VÁLIDA por "antigüedad de pose sobre el umbral". Hubo avisos de pose vieja (10 y 20 ticks) y el 9 retrocedió por pose repetida. La sesión cerró con 506 ticks que no alcanzaron su plazo. No consta un chequeo de la PC antes de esta sesión.
- **Intento 6** (semilla 421005): corrida, NO VÁLIDA. El marcador 8 se congeló en (2.86, 2.71), a 0.14 m de la pared (esquina +x+y). d_min obstáculo 0.341 m.
- **Intento 7** (semilla 421006): el operador lo cortó con Ctrl+C en la colocación (marcador 8 congelado). Quedó "interrumpida" y la sesión se cerró limpia.
- Sesión completa: 265 poses rechazadas por inclinación y 1064 decisiones.

**Decisión del operador:** el Robotat estaba mal calibrado, así que esta campaña no cuenta para las mediciones del documento.
- Se cerró con `--cerrar-campana`, con el motivo escrito ("Campaña DESCARTADA para el documento: el Robotat estaba mal calibrado …").
- Estado final: 7 intentos usados, 3 corridas (3, 5 y 6, todas no válidas), 0 incluidas, 0 tomas con contacto.
- Copia del libro y de `campana.json` previa al cierre en el scratchpad de la sesión (`libro_L2_obstaculo_respaldo_20261016_preCierre.csv`).
- Ninguna toma de `L2_obstaculo` entra en el documento. Si alguna vez se cita, es como campaña descartada, con este motivo.

**Antes de una campaña nueva:**
- **Recalibrar el Robotat:** Motive y la calibración del mocap del día con el robot 1 (etapas 0–2). Si se calibra con otro robot, restaurar `calibracion_medida.json`.
- **Composición:** el estado actual de los archivos es 1, 5, 8, 2, 9. El 6 tiene problemas de giro y el 3 no responde. Si vuelve el 6, hay que revertir con respaldo.
- **Congelados:** la referencia del chequeo previo (1e `ensayo_campana_20261010_100632`) ya no coincide; cambiaron el plan, el análisis y la huella de config con las correcciones. Hay que repetir las suites y el 1e con los archivos vigentes y actualizar la referencia.
- **Nombre:** la campaña nueva lleva otro nombre (p. ej. `L2_obstaculo_2`); la cerrada no se reabre.
- **Para José:** si la campaña nueva reusa el bloque de semillas 421000… (en la descartada corrieron 421002, 421004 y 421005) o empieza uno nuevo, y si aprueba la composición con el 2.
- Chequeo de la PC antes de cada sesión, pegado en la bitácora.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261016_preDescarte.md`.

### Campaña nueva `L2_obstaculo_2`: decisiones de José del 17-10 (composición y semillas)

**Decisiones de José (17-10), transmitidas por el usuario:** se aprueba el robot 2 en lugar del 6 (enjambre 1, 5, 8, 2, 9) y la campaña nueva usa un **bloque nuevo de semillas**. El usuario pidió dejar todo listo para que el día del laboratorio sólo haya que comprobar los robots y la PC.

**Implementación** (respaldos `*_respaldo_20261017_preSemillas`):
- **Semillas (`campana_obstaculo.py`).**
  - `SEMILLA_BASE` pasa de 421000 a **422000**. Ese bloque no aparece en ningún CSV de resultados: el 420000 lo usaron el 30-09, los ensayos y la Fase 0; el 421000, la campaña descartada y los ensayos de campaña en el simulador.
  - `Campana.semilla()` usa la `semilla_base` de la cabecera de cada campaña. Así `L2_obstaculo` conserva su 421000, comprobado en su `campana.json`.
- **Ensayo:** `ensayo_campana_simulador.py` chequea las semillas con `campana.semilla(k)`.
- **Comentarios:** en `analizar_campana_l2.py` y `config_robotat.py`, la composición aprobada por José. `ROBOTS_AGENTES` y `MAPEO_AGENTES` ya eran (1, 5, 8, 2, 9).
- **Demo:** el texto de ayuda de `demo_obstaculo_movil.py` usa `--campana L2_obstaculo_2`.
- **Pruebas** (`test_campana_obstaculo.py`, `test_analizar_campana_l2.py`):
  - las semillas se derivan de `CO.SEMILLA_BASE`;
  - una prueba fija el bloque 422000 y otra comprueba que una campaña con cabecera 421000 conserva su bloque.
  - En `test_replica_con_obstaculo.py`, sólo un comentario.
- **Plan:** la base (composición y bloque nuevo aprobados el 17-10; descarte de `L2_obstaculo`) y el §0 (422000 + k − 1).
- **Protocolo:**
  - encabezado con el 17-10 y nota de la campaña nueva;
  - semillas 422000 + k − 1 y robots del enjambre;
  - todos los comandos con `--campana L2_obstaculo_2`, y el libro en `campanas/L2_obstaculo_2/`.
  - El número 422000 lo eligió la implementación; José aprobó "un bloque nuevo".

**Verificación:**
- Pruebas: análisis 34/34, réplica 31/31, campaña 44/44, más las 2 pruebas nuevas.
- Verificación adversarial (2 lentes con escéptico por hallazgo): 11 hallazgos, 7 confirmados, todos menores y aplicados, y 4 refutados.
  - El texto de ayuda de la demo traía el nombre viejo.
  - El encabezado del protocolo no incluía el 17-10.
  - El número del bloque estaba atribuido a José.
  - Quedaba un comentario viejo en las pruebas de la réplica.
  - Faltaban las pruebas del bloque.
  - Faltaba esta adenda.
- Refutado: blindar `registrar()` contra una semilla distinta de la reserva sería alcance nuevo; el análisis ya lo detecta con código 4.
- Nota: el 422000–422099 figura en el prerregistro del Exp P como semillas de entrenamiento. Es otro dominio, sin conflicto técnico.

**Sigue:** las 13 suites y un 1e con estos archivos (en curso), y apuntar el chequeo previo del protocolo a ese 1e. El día del laboratorio: chequeo de la PC → L0 del 4 → "IGUAL a lo probado" → `--crear-campana` (L2_obstaculo_2) → sesiones.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261017_preSemillas.md`.

### `L2_obstaculo_2` lista para crearse (2026-10-17, 09:35)

- **13 suites OK, 556 pruebas,** con los archivos de la campaña nueva: campaña 45, análisis 34, réplica 31, demo 97, estancamiento 5, sesión 121, cerrojo 3, diagnóstico 28, mapa 46, respuesta 2, retroceso 26, robotat 67, integración 51.
- **Ensayo 1e `resultados_demo_obstaculo/ensayo_campana_20261017_092424`:** META, análisis y verificador en 0 (106/106), registro sin problemas, `semilla_base` 422000. Su `campana.json` es igual a lo congelable hoy (22/22).
- **Protocolo:** el chequeo previo apunta a ese 1e (respaldo `PROTOCOLO_L0_L2_respaldo_20261017_preReferencia.md`) y da "IGUAL a lo probado".
- **El día del laboratorio:**
  1. recalibrar el Robotat (Motive, y la calibración del mocap con el robot 1);
  2. chequeo de la PC → `CHEQUEO OK`, pegado aquí;
  3. L0 del 4, repetida porque la del 16-10 se midió con la calibración mala;
  4. chequeo de congelados → "IGUAL a lo probado";
  5. `--campana L2_obstaculo_2 --crear-campana`, una sola vez;
  6. sesión con la hora de fin fijada por José.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261017_preLista.md`.

### L0 del 4 antes de `L2_obstaculo_2` (2026-10-21)

- **12:55:** FALLO, "no se pudo conectar (servidor de poses): timed out". El servidor del Robotat no respondía; después la prueba TCP a 192.168.50.200:1883 dio "poses OK".
- **12:59:** FALLO, "pose perdida en el arranque 3". El seguimiento estaba bien (−2.0 a −2.4 cm del círculo) y la pose se perdió en env (2.00, 1.80). La colocación pidió corregir cuatro veces: 45.5, 44.4, 44.9 y 19.6 cm.
- **Calibración del mocap:** la etapa 0 dio OK (20/20 poses del marcador 1, force_stop OK; guardó `id_robot` = 1). Los dos intentos de etapa 2 fallaron en el punto 1 y no guardaron nada:
  - 0/10 poses válidas, con un 10054 del robot 1 al manipularlo;
  - 10 lecturas idénticas: punto ciego, igual que la etapa 2 del 09-09.
  - Se sospechó un marco del mocap corrido; no se confirmó.
- **L0 repetida: OK.** 10/10 arranques, error radial máximo 2.2 cm, ω saturado 0 % y offset de rumbo a −0.3° de la tabla (362 pares). La colocación entró al primer intento. La calibración (escala 1.0167, rotación +0.49°, traslación (1.506, 1.256)) es la misma de antes.
  - Esta L0 OK más las dos del 16-10 (−0.34° y −0.1°) indican que el marco sigue bien. Las fallas de hoy fueron el servidor de poses y un punto ciego o la colocación.
- **Antes de crear:** `l0_habilita(4)` OK y chequeo de congelados contra el 1e `ensayo_campana_20261017_092424` en "IGUAL a lo probado". `L2_obstaculo_2` todavía no existe.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261021_preL0.md`.

### Chequeo previo de la PC antes de crear `L2_obstaculo_2` (2026-10-21)

```text
chequeo previo de la PC: 2026-10-21 13:11:44
  corriente: A BATERIA | ahorro de energia: apagado
  plan: 381b4222-f694-41f0-9685-ff5bb260df2e (Equilibrado) | modo enchufada: ded574b5-45a0-4f42-8737-46345c09c238 (Mejor rendimiento)
  procesos: OmenCap.exe, OverlayHelper.exe, OmenInstallMonitor.exe, SystemOptimizer.exe, OmenCommandCenterBackground.exe, HP.OMEN.VirtualCamHelper.exe, ChatGPT Classic.exe (×6), ChatGPT.exe (×13)
CHEQUEO FALLA: no lanzar
chequeo previo de la PC: 2026-10-21 13:12:37
  corriente: A BATERIA | ahorro de energia: apagado
  plan: 381b4222-… (Equilibrado) | modo enchufada: ded574b5-… (Mejor rendimiento)
  procesos: OmenCap.exe, OverlayHelper.exe, OmenInstallMonitor.exe, SystemOptimizer.exe, OmenCommandCenterBackground.exe, HP.OMEN.VirtualCamHelper.exe
CHEQUEO FALLA: no lanzar
```

- Faltan dos cosas: enchufar la laptop y detener los seis procesos de OMEN como administrador. Los cuatro de sistema se detienen con `Stop-Service HPOmenCap; Stop-Process …`, y `OmenCommandCenterBackground` y `HP.OMEN.VirtualCamHelper` siguen vivos aunque se cierre la bandeja.
- **Declaración:** las L0 de hoy (12:55, 12:59 y la OK de las 13:09) corrieron SIN `CHEQUEO OK`: a batería, con OMEN, y ChatGPT al menos hasta las 13:11. Se recomienda repetir la L0 con el chequeo en OK antes de crear la campaña.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261021_preChequeo.md`.

### `L2_obstaculo_2` creada; sesiones cerradas al instante por el marcador 8 congelado (2026-10-21)

- **Creación:** `L2_obstaculo_2` se creó a las 13:17:55 (hw, meta 50, mínimo 30, tope 100, `semilla_base` 422000), con la L0 de las 13:09 (`20261021_130948_L0_resumen.csv`, OK).
- **Sesiones `L2_20261021_131821` y `L2_20261021_132110`** (fin 13:50): cada una se abrió y se cerró en 1–3 s con "fin de la sesión", sin intentos ni reservas. La campaña sigue en 0/100.
- **Causa:** `sesion_demo` revisa los 6 marcadores antes de abrir los enlaces (`stream_congelado`) y devuelve FALLO si alguno está congelado o sin respuesta. Un chequeo de sólo lectura a las 13:2x dio el **marcador 8 CONGELADO** (15 lecturas idénticas) y los demás vivos (1, 5, 2, 9 y 4).
- **Defecto:** en modo campaña, ese FALLO no se imprime y el libro anota sólo "fin de la sesión". Arreglarlo (imprimir el detalle y llevarlo al motivo del cierre) toca `demo_obstaculo_movil.py`, que está congelado: queda propuesto como corrección declarada entre sesiones, con sus pruebas, y no se aplicó.
- **Mientras tanto:** antes de cada sesión, el comando de una línea que revisa los 6 marcadores (vivo / CONGELADO / SIN RESPUESTA). Si el 8 sigue congelado en el centro, redefinir su cuerpo rígido en Motive.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261021_preMarcador8.md`.

### `L2_obstaculo_2`, sesión `L2_20261021_132617`: el robot 1 no mueve las ruedas (2026-10-21)

**Chequeo previo de la PC** (13:25:56): enchufada, ahorro de energía apagado, Equilibrado + Mejor rendimiento, procesos: ninguno → `CHEQUEO OK`. Los marcadores 8 y demás estaban vivos.

**Intento 1** (semilla 422000), en la colocación:
- El robot 1 arrancó en env (0.04, −0.22), fuera de la arena.
- Después, en (0.69, 0.69) y a mano cerca de su blanco en (1.92, 2.37), quedó "girando" sin avanzar ni girar en los cinco reintentos ("no avanza"). Los otros cuatro agentes llegaron a sus blancos.
- Su enlace se cortó dos veces (10054, 13:27:21 y 13:27:58, al manipularlo) y reconectó en 0.1–0.2 s.
- El operador cortó con Ctrl+C: la reserva quedó "interrumpida" (semilla gastada) y la sesión se cerró limpia. 0 tomas corridas; la campaña va en 1/100 intentos.

**Diagnóstico probable:** el ESP32 del robot 1 recibe los mandos, pero no llega potencia a los motores (batería, interruptor o conexión). Es el mismo cuadro del 22-09 ("pose viva, envíos sin error, pero no movió las ruedas"); los 10054 al tocarlo apuntan a una conexión floja. El robot 1 es el agente 0 y el robot de la calibración, así que reemplazarlo implica recalibrar con otro y declarar una corrección: hay que arreglarlo.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261021_preRobot1.md`.

### `L2_obstaculo_2`: primeras tomas incluidas (2026-10-21, 13:32–13:45)

- **Sesión `L2_20261021_133237`** (fin 14:15): se cerró a los 12 s, "no responden: agente 2 → robot 8 … sin respuesta". Sin reservas.
- **Sesión `L2_20261021_133444`** (fin 14:15):
  - **Intento 2** (422001): corrida, válida, **INCLUIDA**; d_min obstáculo 0.321 m.
  - **Intento 3** (422002): corrida, no válida (marcador 8 congelado tras retroceder 2.4 s).
  - **Intento 4** (422003): corrida, válida, **INCLUIDA**; d_min obstáculo 0.315 m.
  - **Intento 5** (422004): corrida, no válida. El agente 4 (robot 9) recorrió el 48 % de lo comandado; su enlace se había caído a las 13:40:59 y estuvo 63 s afuera.
  - **Intento 6** (422005): corrida, no válida (antigüedad de pose).
  - **Intento 7** (422006): parada en la colocación, "CONTACTO durante la colocación: robots 1 y 2 a 0.150 m". El robot 1 otra vez no avanzó (118 cm "girando"), y su enlace se cortó a las 13:44:35 mientras se le cambiaba la batería.
  - **Pausa:** el operador dio Enter sin "s" → "detenida": termina sólo la SESIÓN (regla de José).
  - La sesión cerró limpia; hubo 1540 ticks fuera de plazo.
- **Estado de la campaña:** 7/100 intentos, **2/50 incluidas**, 5 corridas, 0 tomas con contacto, abierta, sin candado. Se retoma con el mismo comando, en el intento 8.
- **A cuidar:** la batería y la conexión del robot 1 (no avanza en la colocación), los cortes de enlace de los robots 8 y 9, el marcador 8, y el chequeo de la PC antes de cada relanzamiento.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261021_preSesion2.md`.

### `L2_obstaculo_2`, sesión `L2_20261021_134819`: 7 incluidas al cerrar el día (2026-10-21, 13:48–14:03)

**Chequeo previo de la PC** de las sesiones de las 13:32 y 13:34 (faltaba en la adenda anterior):

```text
chequeo previo de la PC: 2026-10-21 13:32:16
  corriente: enchufada | ahorro de energia: apagado
  plan: 381b4222-f694-41f0-9685-ff5bb260df2e (Equilibrado) | modo enchufada: ded574b5-45a0-4f42-8737-46345c09c238 (Mejor rendimiento)
  procesos: ninguno
CHEQUEO OK
```

- **Declaración:** la sesión de las 13:48 no tuvo chequeo propio; el último `CHEQUEO OK` es el de las 13:32:16. Entre las dos sesiones el operador consultó a Claude, y no consta si la app quedó cerrada.
- Los huecos del lazo no muestran diferencia entre las dos sesiones: > 150 ms, 3 de 1698 intervalos (13:34) y 6 de 3743 (13:48); > 250 ms, 1 en cada una.

**Sesión `L2_20261021_134819`** (fin 14:15), intentos 8–17:
- **Intento 8** (422007): válida, **INCLUIDA**; d_min obstáculo 0.301 m. El marcador 9 se repitió en (1.51, 1.27) y (1.53, 1.28) y se recuperó con el retroceso.
- **Intento 9** (422008): válida, **INCLUIDA**; 0.339 m.
- **Intento 10** (422009): válida, **INCLUIDA**; 0.305 m.
- **Intento 11** (422010): no válida, marcador 9 congelado en (0.41, 2.34) tras retroceder 2.3 s.
- **Intento 12** (422011): no válida, antigüedad de pose: el marcador 1 se congeló en (1.46, 1.21), en el interior. Antes de correr hubo dos reintentos de colocación, por los marcadores 9 y 8 congelados.
- **Intento 13** (422012): válida, **INCLUIDA**; 0.328 m. En la guía, el marcador 1 estuvo congelado en (1.42, 1.24) hasta que se movió el robot.
- **Intento 14** (422013): válida, **INCLUIDA**; 0.387 m. Hubo un reintento de colocación (robots 1, 2 y 9 "no avanza") y retrocesos recuperados del 8 en (2.72, 0.17) y del 1 en (1.55, 1.24) y (1.54, 1.21).
- **Intento 15** (422014): no válida, con la **regla de parada "ABORTO POR EL OBSTÁCULO"** (marcador 4 repetido bit a bit en (1.58, 0.92)). Pausa: "s" → siguió.
- **Intento 16** (422015): no válida, marcador 9 congelado en la esquina (2.83, 2.77), a 0.17 m de la pared.
- **Intento 17** (422016): en la guía, con el marcador 9 todavía congelado en (2.83, 2.77), el operador cortó con Ctrl+C a las 14:03:36 para terminar el día. La reserva quedó "interrumpida" (semilla gastada) y la sesión se cerró "interrumpida (Ctrl+C)", con la detención enviada.
- 0 contactos y 0 frenos de respaldo. 0 envíos fallidos y 0 reconexiones. 3041 ticks fuera de plazo; latencia de poses p50 3.6 ms, p95 17.8 ms y máx 212.6 ms; 5 poses rechazadas por inclinación.

**La toma 15 no la causó el robot del obstáculo.** En los crudos (`20261021_134819_L2_decisiones.csv` y `_obstaculo.csv`), en el paso 203 se repiten a la vez, bit a bit, los 6 marcadores (los 5 agentes y el 4).
- Antes hubo un hueco del lazo de 309 ms entre los pasos 200 y 201.
- Después, los pasos 201 → 202 → 203 vinieron a 10 y 11 ms. La consulta del 203 devolvió lo mismo que la del 202; lo más probable es que fuera el mismo cuadro del mocap.
- Es el único hueco de la sesión > 250 ms y la única repetición simultánea de los 6. El 4 estaba sano y el "s" fue correcto. No se cambió nada.

**Congelamientos por marcador** en esta sesión:
- el 9 en (0.41, 2.34) y en la esquina (2.83, 2.77);
- el 8 en (0.47, 0.32), (2.76, 0.20) y (2.72, 0.17);
- una **zona interior** en (1.42–1.55, 1.21–1.28): el 1 en las tomas 12, 13 y 14, y el 9 en la 8. Como se repite, el mapa de la sonda en esa zona ayudaría a decidir si es un punto ciego.

**Estado de la campaña:** 17/100 intentos, **7/50 incluidas** (intentos 2, 4, 8, 9, 10, 13 y 14), 14 corridas, 0 tomas con contacto. Sigue **abierta**, sin candado: el operador terminó por hoy, no cerró la campaña. Se retoma con el mismo comando, en el intento 18 (semilla 422017).
- **Ritmo:** 7 incluidas en 17 intentos (41 %). A ese ritmo, el mínimo de 30 llega cerca del intento 73 y los 100 intentos dan unas 41 incluidas: la meta de 50 no se alcanza si no bajan las pérdidas del seguimiento.
- **Pérdidas:** de los 10 intentos no incluidos, 7 fueron del seguimiento (marcadores congelados, antigüedad de pose y la repetición simultánea de la toma 15). Los otros 3 fueron de los robots: el 1 sin potencia, el 9 con el enlace caído, y el contacto de la colocación con el 1 detenido.
- **Próxima sesión:**
  - chequeo de la PC, con la app de Claude cerrada, antes de CADA lanzamiento (también al relanzar después de un corte);
  - chequeo de los 6 marcadores;
  - si hay tiempo, el mapa de la sonda en la zona interior.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261021_preSesion3.md`.

### Demostración final: dos modos y panel en otro proceso (2026-10-23) — demostración, no citable

**Qué es:** la sesión de demostración de la implementación final, para el video del documento, el póster y la defensa en vivo. No es una medición: sus salidas van a `resultados_demo_final/` y **no se citan en el documento**. La campaña `L2_obstaculo_2` sigue ABIERTA y no se tocó.

**Archivos nuevos** (en `controllers/coordinador_enjambre/`, LF): `demo_final.py`, `publicador_estado.py`, `panel_demo.py`, `test_demo_final.py`, `comparar_ast_demo_final.py`, `verificar_cifras_demo_final.py` y `manifiesto_sha256_demo_final.txt`. No se modificó ningún archivo existente salvo esta bitácora.

**Los dos modos:**
- `objetivos`: la configuración de la evaluación del 30-09 (robots 1, 5, 8, 2, 9; `modelo_sanidad`; CBF y escape; factor 0.40; 500 decisiones; colocación autónoma).
- `mejorada`: lo mismo con el robot 4 como obstáculo móvil del modo L2 (F2, τ_c 0.65 s, círculo de R 0.60 alrededor de (1.5, 1.5) a 0.05 m/s), sin campaña.
- En hardware, `mejorada` exige la L0 OK del día del 4 (código 6, sin `--forzar`).

**Sólo orquesta.** Lo que no se podía importar se copió literal y está marcado con su archivo y líneas:
- `sesion_robotat.py` 1991-2000, 2013-2034 y 2062-2235;
- `demo_obstaculo_movil.py` 2653-2663 y 2692-2909 (el bucle de tomas con las reglas de parada, con `campana = None`).
- `comparar_ast_demo_final.py` comprueba que las cinco copias son idénticas a su fuente salvo **una línea marcada `[demo]`** (`sesion_robotat.py:2133`, `--colocacion actual` no pide reposicionar), y que nada redefine ni parchea un congelado. Veredicto: "SÓLO ORQUESTAN".
- La publicación, el Enter entre episodios y la hora de fin entran por la subclase del coordinador (publica DESPUÉS de `super()._decidir_y_actuar()`) y por tres envoltorios locales que llaman a las funciones congeladas.

**Publicación:** UDP, una vez por decisión. Nunca lanza: tras 20 errores seguidos se apaga y avisa una vez. Serializar y enviar va en un hilo del publicador, mientras el lazo duerme. Medido en el banco de la prueba 5, intercalado: en hilo cuesta el 58–61 % de enviar en el acto.

**Pruebas** (simulador, Python de la Store = el de la campaña): 13/13 funcionales OK.
- 1 y 2: los dos modos corren completos y los CSV tienen las columnas de la etapa 7 y de `sesion_demo`.
- 3 y 4: los mensajes llegan completos y en orden, y las fallas inyectadas no invalidan el episodio.
- 5: bit a bit contra `CoordinadorEnjambre` y `CoordinadorConObstaculo`. Con obstáculo hubo que **fijar el reloj** en la prueba: la F2 y el supervisor leen `perf_counter`, y sin eso ni la base es igual a sí misma entre dos corridas.
- 6: en `--simulador` la calibración queda en identidad.
- Las pruebas 1 a 6 corrieron **a batería**: valen como funcionales, pero sus tiempos no se citan.

**Prueba 7 (costo del panel), NO PASA en la misma laptop.**
- La primera corrida fue a batería (22 %) y no vale: el ciclo p95 sin GUI subió de ~10 a 42 ms en las tres condiciones. Quedó en `_superadas/` con su LEEME.
- Repetida **enchufada** (medias del ciclo p95, 3 × 300):

| condición | media |
|---|---|
| sin GUI | 9.99 ms |
| publica, sin panel | 9.40 ms |
| panel abierto, 10 Hz | 14.56 ms |
| panel abierto, 5 Hz | 14.44 ms |

- **Publicar no cuesta nada medible**; el panel abierto en la misma laptop suma +4.56 ms (10 Hz) y +4.45 ms (5 Hz), sobre el umbral de +2 ms.
- Como no baja con el ritmo de dibujo, no es el dibujo en sí. La causa no se aisló.
- **Recomendación:** el panel en otra laptop de la misma red (`--gui <IP>:27300`), que es la salida que ya preveía el plan. Con la misma laptop, el lazo igual cumple con holgura (~15 ms de 100), pero no el criterio de +2 ms.

**El día de la demo, lo que aprendimos hoy:** la laptop del lazo **enchufada** y en "Mejor rendimiento". A batería, el ciclo se cuadruplica.

**Congelados:** el chequeo del protocolo da "IGUAL a lo probado" antes de empezar y al terminar cada paso. El manifiesto sha256 registra los 22 archivos idénticos.

**Pendiente:** la fase 2 (espejo en Webots), sólo con OK de José; el ensayo completo en casa con el panel en la segunda laptop.

**Reporte:** `REPORTE_2026-10-23_demo_final.md` con `REPORTE_2026-10-23_demo_final_datos.zip`.

**Respaldo:** antes de esta entrada, `BITACORA_TECNICA_respaldo_20261023_preDemoFinal.md`.

### Demostración final: de dónde salen los ~4.7 ms del panel (2026-10-23, noche) — demostración, no citable

**Corrige la entrada anterior.** Allí la prueba 7 decía +4.56 ms y "no es el dibujo". Ahora la causa está acotada y la cifra vigente es la de la prueba intercalada.

**El panel se corrigió, aunque no era la causa.**
- `plt.pause()` redibujaba la figura entera en cada cuadro, además del blitting. Se reemplazó por `canvas.start_event_loop()`.
- La rejilla de AoI se redibujaba sin haber cambiado. Ahora queda guardada como capa y sólo se vuelve a dibujar cuando llega una nueva.
- La baja de prioridad del proceso **nunca había funcionado**: faltaban las firmas de `ctypes`. Ahora dice "bajo lo normal".
- Resultado: el panel pasó de 0.97 a 0.22 de un núcleo, con la misma imagen. **El costo sobre el lazo no cambió.**

**Prueba 7 intercalada** (enchufada, sin Chrome ni ChatGPT; 4 rondas, 1 × 300 por condición, orden rotado): sin GUI 7.80 ms, publica 7.75 ms, panel 12.51 ms.
- Panel − sin GUI, pareado: **+4.71 ms** (de +4.02 a +5.13). No pasa.
- Publica − sin GUI: -0.05 ms.
- Una corrida anterior con Chrome abierto dio +0.30 ms: era ruido. Está en `_superadas/` con su LEEME.

**Ingredientes separados** (`resultados_demo_final/diagnostico_panel_20261023/`, intercalados, pareados contra sin GUI):

| condición | − sin GUI |
|---|---|
| panel con ventana, recibiendo | +3.92 ms |
| panel con ventana, sin datos | +3.74 ms |
| panel sin ventana (Agg), recibiendo | +0.04 ms |
| sólo timer de 1 ms | -0.86 ms |
| ventana Tk mínima (un reloj) | +4.19 ms |
| la misma, minimizada | +3.99 ms |

- **Causa: cualquier proceso con un bucle de eventos Tk** en la misma máquina, aunque esté minimizado.
- **No es** dibujar, recibir, matplotlib, el foco ni el temporizador. El mecanismo dentro de Windows no se aisló.
- Medido en el simulador, donde el proceso del lazo tiene además los hilos del simulador. En el Robotat podría ser distinto.

**Errores del diagnóstico, declarados:**
- Una corrida A/G/H leyó el CSV viejo de A porque reutilizaba la carpeta: se descartó, se corrigió el script y se repitió.
- Una condición con el Bloc de notas se canceló antes de correr, porque al final cerraba todos los Bloc de notas. No se cerró ninguno.

**Decisión pendiente de José:** el panel en otra laptop de la misma red (recomendado), o aceptarlo en la misma laptop con el lazo en ~12.5 ms de 100.

**Reporte y zip actualizados:** `REPORTE_2026-10-23_demo_final.md`, 24/24 cifras verificadas.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261023_preCausaPanel.md`.

### Demostración final: el panel va en la misma laptop — decisión de José (2026-10-23)

**Decisión de José (23-10), textual:** "Acepto el panel en la misma laptop: el lazo queda en ~12.5 ms de 100."

- Se aparta del criterio de la prueba 7 del plan (+2 ms como máximo): con el panel abierto, el ciclo p95 sube +4.71 ms pareado (7.80 → 12.51 ms), según la adenda anterior. La prueba 7 queda **no aprobada** y se acepta así, por decisión de José.
- El periodo del lazo es de 100 ms: queda con holgura.
- Lo medido es del simulador. El día del laboratorio, mirar el ciclo p95 que muestra el panel durante el ensayo. Si se aleja de lo medido acá, la otra laptop sigue disponible (`--gui <IP>:27300`).
- No cambia nada del código.

**Respaldo:** antes de esta entrada, `BITACORA_TECNICA_respaldo_20261023_preDecisionPanel.md`.

### `L2_obstaculo_2`, sesiones del 23-10 (20:48–21:23): 10/50 incluidas

**Chequeo previo de la PC** (pegado por el operador):

```text
chequeo previo de la PC: 2026-10-23 20:32:35
  corriente: A BATERIA | ahorro de energia: apagado
  plan: 381b4222-f694-41f0-9685-ff5bb260df2e (Equilibrado) | modo enchufada: ded574b5-45a0-4f42-8737-46345c09c238 (Mejor rendimiento)
  procesos: OverlayHelper.exe [5728], SystemOptimizer.exe [5876], OmenInstallMonitor.exe [9212], OmenCommandCenterBackground.exe [6376], HP.OMEN.VirtualCamHelper.exe [2024]
CHEQUEO FALLA: no lanzar
```

- Se indicó enchufar la laptop y detener los procesos de OMEN como administrador.
- **Declaración:** no consta un `CHEQUEO OK` antes de las sesiones. La salida pegada de las sesiones empieza en el comando de la primera; el último chequeo registrado es esta FALLA, 16 min antes.

**Sesiones:**
- **`L2_20261023_204819`** (fin 21:15): se cerró a los 5 s por "timed out" al conectar con el servidor de poses del Robotat. Sin reservas.
- **`L2_20261023_204919`**: se cerró a los 11 s porque el robot 2 no respondía en la red. Sin reservas.
- **`L2_20261023_205007`** (20:50:08–21:23:37), intentos 18–25:
  - **Intento 18** (422017): sin correr. El 4 no quedó en su arranque: la guía pidió colocarlo a mano seis veces, y al final quedó a +159° de la tangente.
  - **Intento 19** (422018): válida, **INCLUIDA**; d_min obstáculo 0.347 m.
  - **Intento 20** (422019): válida, **INCLUIDA**; d_min obstáculo 0.297 m, la menor de la campaña hasta ahora (sin contacto). Hubo un reintento de colocación: el 8 "no avanza".
  - **Intento 21** (422020): válida, **INCLUIDA**; d_min obstáculo 0.346 m. Hubo un reintento: el 5 "no avanza".
  - **Intento 22** (422021): no válida, marcador 9 congelado en (0.21, 2.56), a 0.21 m de la pared, tras retroceder 2.4 s.
  - **Intento 23** (422022): no válida por antigüedad de pose. El marcador 8 se repitió en (1.56, 1.31), a unos 3 cm de la zona interior del 21-10 (x 1.456–1.548, y 1.213–1.281). Antes hubo tres reintentos de colocación: el marcador 9 congelado y, dos veces, el 5 que no avanzaba.
  - **Intento 24** (422023): parada en la colocación por **"ABORTO POR EL OBSTÁCULO: el obstáculo NO FRENA: se movió 51.1 cm durante la colocación (v medida 0.000 m/s)"**. Pausa: "s" → siguió.
    - Durante esa guía el marcador 8 estuvo un buen rato "SIN POSE", y varios robots cambiaron de lugar sin colocación en marcha: los movieron a mano.
    - Con v medida 0, lo más probable es que el 4 también se moviera a mano, o que su marcador saltara. No fue el robot andando. Falta confirmarlo con el operador.
  - **Intento 25** (422024): en la guía el 4 estaba fuera de su arranque (primero cerca del centro, después a 10–23 cm del círculo). El operador cortó con Ctrl+C a las 21:23:37: "interrumpida".
  - 0 contactos, 0 frenos de respaldo y 0 pares a < 0.15 m. Consola: 1088 ticks fuera de plazo; latencia de poses p50 3.5 ms, p95 5.5 ms y máx 94.3 ms (el 21-10, p95 16.8–17.8 ms); 345 poses rechazadas por inclinación; 0 envíos fallidos y 0 reconexiones.

**Estado de la campaña:** 25/100 intentos, **10/50 incluidas** (intentos 2, 4, 8, 9, 10, 13, 14, 19, 20 y 21), 19 corridas, 0 tomas con contacto. Sigue abierta, sin candado. Se retoma con el mismo comando, en el intento 26 (semilla 422025). Ritmo: 10/25 = 40 %.

**Para la próxima sesión:**
- `CHEQUEO OK` antes de cada lanzamiento, pegado aquí.
- Mover el 4 a mano sólo cuando la guía lo pide para el obstáculo, no durante la colocación de los agentes.
- Revisar los marcadores 8 y 9 (congelados o sin pose varias veces) y las ruedas del 5 y el 8 ("no avanza").

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261023_preSesionL2.md`.

### `L2_obstaculo_2`, sesión del 04-11 (12:07–12:41): 12/50 incluidas y caída de la red del laboratorio

**Chequeo previo de la PC:** no consta (no se pegó ninguna salida). Se declara como sesión sin `CHEQUEO OK`.

**Sesiones:**
- **`L2_20261104_120701`** (fin 13:40): se cerró a los 5 s por "timed out" al conectar con el servidor de poses. Sin reservas.
- **`L2_20261104_120744`** (12:07:44–12:41:20), intentos 26–35:
  - **Intentos 26, 27 y 28** (422025–422027): sin correr. El 4 no quedó en su arranque después de seis correcciones a mano cada uno: a 11.6 cm del círculo y 49°, a 36.5 cm, y a 27.6 cm. En el 29 se lo puso en (1.50, 0.90), mirando +x (el arranque de la L0), y entró.
  - **Intento 29** (422028): válida, **INCLUIDA**; d_min obstáculo 0.370 m. Antes hubo tres reintentos: el robot 1 "no avanza".
  - **Intento 30** (422029): no válida por antigüedad de pose. El marcador 8 se repitió en (1.46, 1.32) y (1.48, 1.33), en la zona interior del 21-10 (x 1.456–1.548, y 1.213–1.281) o a 5 cm de ella.
  - **Intento 31** (422030): no válida por antigüedad de pose (marcador 9 repetido en (0.59, 0.37)). En la guía, el marcador 8 seguía congelado en (1.49, 1.33).
  - **Intento 32** (422031): no válida, marcador 9 congelado en (0.24, 0.30). Antes, el 5 se repitió cuatro veces en (2.36–2.37, 2.70–2.72) y se recuperó.
  - **Intento 33** (422032): válida, **INCLUIDA**; d_min obstáculo 0.288 m, la menor de la campaña hasta ahora (sin contacto).
  - **Intento 34** (422033): no válida, marcador 8 congelado en (2.71, 2.51). Hubo tres reintentos de colocación: el 5 y el 9 "no avanza".
  - **Intento 35** (422034): en la colocación, todos los marcadores y el del 4 se quedaron a la vez sin pose fresca, y enseguida cayó la red (abajo). El operador cortó con Ctrl+C a las 12:41:20: "interrumpida".

**La caída de la red** (consola):
- Primero la fuente de poses se quedó sin datos frescos para los 6 marcadores a la vez. Después, entre las 12:31:59 y las 12:32:09, se cortaron los enlaces de los 6 robots (10054) y la conexión con el servidor de poses, que se perdió varias veces más.
- Los robots 5, 2, 8 y 9 y el 4 volvieron a los 234–291 s. **El robot 1 no volvió nunca** (274 intentos sin respuesta): su detención no se pudo confirmar.
- A las 12:40:24–26 se cortaron otra vez los 5 que habían vuelto, y regresaron en unos 20 s.
- Que caigan a la vez el servidor de poses y todos los robots, con 10054 (la conexión la cierra el otro extremo), y que los robots tarden unos 4 min en volver, apunta a la red del laboratorio (router o punto de acceso reiniciado o caído). No apunta al código ni a un robot. No está confirmado con el laboratorio.
- La red ya venía mal: el primer lanzamiento dio "timed out", y la latencia de poses de la sesión fue p50 3.9 ms, p95 39.8 ms y máx 741.0 ms, con 32 consultas fallidas. El 23-10 había sido p95 5.5 ms y máx 94.3 ms. Hubo 2046 ticks fuera de plazo.
- 0 contactos, 0 frenos de respaldo y 0 pares a < 0.15 m.

**Estado de la campaña:** 35/100 intentos, **12/50 incluidas** (2, 4, 8, 9, 10, 13, 14, 19, 20, 21, 29 y 33), 25 corridas, 0 tomas con contacto. Sigue abierta, sin candado. Se retoma en el intento 36 (semilla 422035). Ritmo: 12/35 = 34 %. A ese ritmo el mínimo de 30 llegaría cerca del intento 88; quedan 65 intentos para 18 incluidas (28 %).

**Para la próxima sesión:**
- Confirmar con el laboratorio el estado de la red; si vuelve a dar "timed out" o la latencia sube, no lanzar.
- Apagar y prender el robot 1, y comprobar que vuelva a la red.
- `CHEQUEO OK` y revisión de marcadores antes de cada lanzamiento, pegados aquí.
- Antes de lanzar, dejar el 4 en (1.50, 0.90) mirando +x: hoy tres intentos se gastaron sin correr porque el 4 no quedó en su arranque.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261104_preSesionL2.md`.

### `L2_obstaculo_2`, sesión del 04-11 a las 12:51: dos paradas por enlaces que se cortan, y diagnóstico de la red

**Verificación antes de lanzar (12:48, sólo lectura, desde la laptop):**
- Los 7 equipos responden al ping sin pérdidas y aceptan conexión en su puerto: el servidor de poses y los robots 1, 5, 8, 2, 9 y 4. El robot 1 volvió a la red.
- Los 6 marcadores estaban vivos.
- Latencia del servidor de poses, en 200 consultas en lote: p50 3.4 ms, p95 14.9 ms y máx 52.3 ms, sin fallas.

**Chequeo previo de la PC** (pegado por el operador):

```text
chequeo previo de la PC: 2026-11-04 12:49:56
  corriente: enchufada | ahorro de energia: apagado
  plan: 381b4222-f694-41f0-9685-ff5bb260df2e (Equilibrado) | modo enchufada: ded574b5-45a0-4f42-8737-46345c09c238 (Mejor rendimiento)
  procesos: ninguno
CHEQUEO OK
```

**Sesión `L2_20261104_125102`** (fin 13:40):
- **Intento 36** (422035): parada en la colocación por **"ABORTO POR EL OBSTÁCULO: enlace de ruedas del obstáculo (robot 4) caído antes de la colocación"**. Antes, en la colocación, los robots 5, 8, 2 y 9 "no avanza": sus enlaces se habían reseteado (10054). Pausa: "s" → siguió.
- **Intento 37** (422036): parada en la colocación por **"ENLACE DE RUEDAS CAÍDO durante la colocación: robot(s) 5"**. Otra vez los 5, 8, 2 y 9 "no avanza", y el 1 llegó solo. Pausa: "detenida" (12:58:45).
- Entre las 12:52:04 y las 12:58:13 hubo 16 resets (10054) de los enlaces de los robots, en los seis y escalonados: 4 del 2, 4 del 9, 4 del 8, 3 del 5 y 1 del 1, más 3 del 4. Casi todos se reabrieron en 0.0–0.5 s; algunos tardaron 4–22 s.
- El servidor de poses anduvo bien: 744 consultas sin fallas, p50 4.0 ms, p95 30.2 ms y máx 52.8 ms.
- 0 decisiones de toma; 0 contactos.

**Diagnóstico después de la sesión (sólo lectura):**
- En la laptop no quedó ningún proceso conectado a los robots: sólo conexiones en TIME_WAIT y el servidor de Inventor, que arrancó a las 12:59:49, después de la sesión.
- No hay conflicto de IP: en 12 vueltas (unos 40 s), cada IP de robot dio siempre la misma MAC (98-cd-ac-… y 34-ab-95-…, placas Espressif).
- La laptop tiene dos adaptadores WiFi activos: el USB TP-Link (`Wi-Fi 6`, 192.168.50.3, red del laboratorio) y el interno Realtek (`Wi-Fi`, 10.100.0.92, otra red). La ruta hacia 192.168.50.0/24 va por el TP-Link, como corresponde.
- Ping de 60 s, en paralelo y sin pérdidas:

  | Destino | p50 | p95 |
  |---|---|---|
  | router .1 | 8 ms | 40 ms |
  | servidor de poses | 4 ms | 26 ms |
  | los 6 robots | 207–215 ms | 340–348 ms |

  Los seis robots dan lo mismo.
- Conexiones abiertas con los 6 robots durante 90 s, sin enviar datos (sólo keepalive TCP cada 2 s): 0 cortes.

**Lectura:**
- Antes de la caída de la red de las 12:31:59, esta mañana no hubo ningún reset, y el 23-10 tampoco.
- Desde que la red volvió, los robots responden con latencia alta y pareja (unos 210 ms; no hay una medición anterior para comparar). Con el tráfico de la sesión, a 10 Hz, sus enlaces se resetean cada 10–60 s; en reposo, no.
- Apunta al WiFi del laboratorio, que volvió degradado después de la caída. No apunta al código, que no cambió (congelados), ni a un robot en particular.
- No está confirmado. Las paradas de seguridad actuaron como debían: detuvieron la sesión al caer los enlaces.

**Estado de la campaña:** 37/100 intentos, 12/50 incluidas, 25 corridas, 0 tomas con contacto. Sigue abierta y se retoma en el intento 38 (422037). Los intentos 36 y 37 se gastaron sin correr.

**Para seguir:**
- No lanzar con la red así: cada lanzamiento gasta intentos.
- Pedir al laboratorio que revise el router o el punto de acceso (canal, si es el mismo de antes) y reiniciar los robots para que se reconecten.
- Antes de lanzar, repetir esta verificación. Opcional: apagar el WiFi interno de la laptop durante la sesión, para no tener dos radios transmitiendo.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261104_preSesion2.md`.

### `L2_obstaculo_2`, 06-11: se alcanza el mínimo de 30 incluidas (intentos 38–73)

**Antes de lanzar:**
- Chequeo de la PC a las 19:21:17: **FALLA** por Chrome. No consta un `CHEQUEO OK` después. La app de Claude estaba abierta a las 19:35 (verificación de marcadores); no consta si se cerró antes de la sesión de las 19:38.
- Cuatro lanzamientos no arrancaron; ninguno reservó intentos:
  - `L2_20261106_192946`: "timed out" al conectar con el servidor de poses (19:29:51).
  - `L2_20261106_193200`, `L2_20261106_193221` y `L2_20261106_193330`: se cerraron en 1 s con "fin de la sesión". Es el FALLO silencioso del chequeo de marcadores (defecto conocido, demo congelada).
- Verificación de sólo lectura a las 19:34:58: el servidor de poses conecta en 24 ms, pero los 6 marcadores salen CONGELADOS (1 valor distinto en 15 lecturas) y la consulta en lote devuelve números basura (p. ej. 9.083e+223). Motive o el servidor del Robotat no estaban transmitiendo poses reales.
- A las 19:38:52 la sesión arrancó con los marcadores vivos. Qué se hizo en el laboratorio entre las 19:35 y las 19:38 no consta.

**Sesión `L2_20261106_193852`** (fin fijado 21:00; 19:38:52–20:48:09), intentos 38–73. L0 del robot 4: OK, offset a −0.3° de la tabla (362 pares).

| Intento | Semilla | Resultado | d_min obstáculo (m) | Nota |
|---|---|---|---|---|
| 38 | 422037 | sin correr | — | el 4 a +82.8 cm de su círculo, tras seis pedidos de colocación |
| 39 | 422038 | sin correr | — | el 4 a +52.4 cm de su círculo y a −49° de la tangente |
| 40 | 422039 | sin correr | — | el 4 a +11.3 cm de su círculo |
| 41 | 422040 | sin correr | — | colocación de agentes: el 8 a 186 cm y el 2 a 19 cm de su blanco ("no avanza") |
| 42 | 422041 | no válida | 0.457 | marcador 1 congelado en (0.27, 2.81) tras retroceder 2.2 s |
| 43 | 422042 | no válida | 0.289 | antigüedad de pose (10 y 20 ticks) mientras el 9 retrocedía desde (0.29, 0.46); antes el 8 se recuperó dos veces en (0.22, 1.83) |
| 44 | 422043 | **INCLUIDA** | 0.333 | |
| 45 | 422044 | no válida | 0.374 | marcador 1 congelado en (0.20, 2.83); antes se recuperó en (0.95, 2.82) |
| 46 | 422045 | **INCLUIDA** | 0.339 | dos reintentos de colocación: el 5 "no avanza" |
| 47 | 422046 | **INCLUIDA** | 0.314 | el 9 se recuperó en (0.96, 2.82) |
| 48 | 422047 | **INCLUIDA** | 0.299 | el 1 se recuperó dos veces en (1.67, 1.07); el 8 retrocedía en (0.89, 2.76) al terminar (decisión 496 de 500) |
| 49 | 422048 | no válida | 0.317 | marcador 1 congelado en (0.94, 2.79) |
| 50 | 422049 | no válida | 0.298 | marcador 9 congelado en (0.97, 2.82) |
| 51 | 422050 | no válida | 0.396 | agente 0 (robot 1) NO SIGUE el comando (0 % en 50 pasos); 8 s después se cayó su enlace |
| 52 | 422051 | **INCLUIDA** | 0.310 | en la guía, enlace del 1 caído a las 20:09:01 (10054) y reabierto a los 84.4 s; el 8 se recuperó en (1.62, 1.14) |
| 53 | 422052 | **INCLUIDA** | 0.336 | |
| 54 | 422053 | **INCLUIDA** | 0.296 | |
| 55 | 422054 | no válida | 0.394 | marcador 8 congelado en (2.86, 2.71); antes el 2 se recuperó dos veces en (0.94, 2.79) |
| 56 | 422055 | **INCLUIDA** | 0.293 | |
| 57 | 422056 | no válida | 0.409 | marcador 9 congelado en (0.25, 2.41) |
| 58 | 422057 | **INCLUIDA** | 0.292 | |
| 59 | 422058 | **INCLUIDA** | 0.330 | |
| 60 | 422059 | no válida | 0.420 | marcador 9 congelado en (0.84, 2.73) |
| 61 | 422060 | **INCLUIDA** | 0.342 | |
| 62 | 422061 | no válida | 0.431 | marcador 9 congelado en (1.42, 2.82) |
| 63 | 422062 | no válida | 0.341 | marcador 2 congelado en (0.92, 2.78) |
| 64 | 422063 | **INCLUIDA** | 0.301 | el 9 se recuperó en (0.96, 2.82) |
| 65 | 422064 | **INCLUIDA** | 0.307 | |
| 66 | 422065 | **INCLUIDA** | 0.422 | el 9 se recuperó en (1.68, 1.08) |
| 67 | 422066 | no válida | 0.330 | marcador 9 congelado en (0.45, 2.82) |
| 68 | 422067 | **INCLUIDA** | 0.328 | |
| 69 | 422068 | **INCLUIDA** | 0.316 | |
| 70 | 422069 | no válida | 0.550 | marcador 9 congelado en (0.20, 2.77) |
| 71 | 422070 | **INCLUIDA** | 0.265 | la menor de la campaña, sin contacto |
| 72 | 422071 | **INCLUIDA** | 0.320 | el 9 se recuperó en (0.96, 2.82) |
| 73 | 422072 | interrumpida | — | Ctrl+C en la guía a las 20:48:09, con el marcador 9 congelado en (0.80, 2.77) |

Coordenadas en el marco del env (m), tomadas de la consola. Todas las paradas por marcador congelado fueron después de retroceder 1.9–2.4 s sin recuperar la captura.

**Resumen de la sesión:**
- 36 intentos: **18 incluidas**; 13 corridas no válidas (11 por marcador congelado, 1 por antigüedad de pose, 1 porque el robot 1 no seguía el comando); 4 sin correr (3 por la colocación del obstáculo y 1 por la de los agentes); 1 interrumpida. Ritmo 18/36 = 50 %.
- 0 contactos, 0 frenos de respaldo y 0 pares a < 0.15 m. d_min al obstáculo entre 0.265 y 0.550 m.
- Consola: 27007 consultas de poses, 0 fallidas, p50 3.3 ms, p95 5.2 ms y máx 34.0 ms; 170 poses rechazadas por inclinación; 1 envío fallido y 1 reconexión (robot 1); 1 frenado por pose vencida; 12841 decisiones; **9890 ticks fuera de plazo**, la cifra más alta por sesión en la campaña (antes 506–3041), en la sesión más larga.
- La red se comportó: un solo reset de enlace en 70 min (el del robot 1), frente a los 16 en 6 min del 04-11. La latencia de poses volvió a la del 23-10 (p95 5.5 ms).

**Congelamientos de marcador (de la consola):**
- Los 11 que pararon tomas fueron en la franja alta del env: 10 con y entre 2.71 y 2.83 (pared +y) y 1 en (0.25, 2.41).
- Un punto se repite: **cerca de (0.95, 2.80)**, 9 veces con 3 robots distintos (1, 9 y 2), dentro de ±3 cm. 3 pararon la toma (49, 50 y 63) y 6 se recuperaron con el retroceso. Apunta a un punto ciego de las cámaras en ese lugar; no está confirmado.
- 4 congelamientos interiores, todos recuperados en 0.2–0.9 s: (1.67, 1.07) dos veces, (1.62, 1.14) y (1.68, 1.08), con los robots 1, 8 y 9. Quedan a unos 10–20 cm de la zona interior del 21-10 (x 1.42–1.55, y 1.21–1.28).

**Declaraciones:**
- No consta un `CHEQUEO OK` antes de esta sesión. Sigue sin haber incluidas que salgan de una sesión con chequeo propio.
- El aviso "NO SE PUDO CONFIRMAR LA DETENCIÓN" del robot 1 (20:09) salió en la guía de la toma 52. Su última orden había sido la detención del fin de la toma 51. Después estuvo un rato SIN POSE y reapareció en otra posición: probablemente lo movieron a mano. Falta confirmarlo con el operador.

**Estado de la campaña:** 73/100 intentos, **30/50 incluidas → veredicto MÍNIMO alcanzado**: intentos 2, 4, 8, 9, 10, 13, 14, 19, 20, 21, 29, 33, 44, 46, 47, 48, 52, 53, 54, 56, 58, 59, 61, 64, 65, 66, 68, 69, 71 y 72. 56 corridas, 0 tomas con contacto. Sigue **abierta**, sin candado; si se sigue, se retoma en el intento 74 (semilla 422073). Ritmo de la campaña: 30/73 = 41 %.

**Para decidir (José):**
- Quedan 27 intentos hasta el tope. Para llegar a la meta de 50 hacen falta 20 de 27 (74 %). Con el ritmo de la campaña (41 %) se esperan unas 11 incluidas más (≈ 41 al tope); con el de hoy (50 %), 13–14 (≈ 43–44). Salvo un ritmo muy superior, el veredicto queda en MÍNIMO por cualquiera de los dos caminos; seguir sólo suma incluidas.
- Hoy se hicieron 36 intentos en 69 min, unos 1.9 min cada uno: agotar el tope es una sesión más de alrededor de 1 h.
- Cerrar ahora es `--cerrar-campana "motivo"` y no tiene vuelta atrás. Después vienen la réplica (PC limpia, `CHEQUEO OK` por lanzamiento, nunca en paralelo con el hardware), el análisis, el verificador y el reporte con el zip. La cobertura sigue sin mirarse hasta el cierre.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261106_preSesionL2.md`.

### `L2_obstaculo_2`, 07-11: respuesta del operador sobre el robot 1 y correcciones a la adenda del 06-11

La adenda anterior se revisó afirmación por afirmación contra la consola pegada, el libro y esta bitácora. Seis revisores, uno por sección; cada discrepancia pasó por tres escépticos y quedó si la sostuvieron al menos dos. Los conteos de reintentos y de congelamientos en las guías los rehíce aparte sobre la consola. Nada de esto cambia el estado de la campaña: 73/100 intentos, 30/50 incluidas (MÍNIMO), 56 corridas, 0 contactos.

**Robot 1 a las 20:09 (respuesta del operador):** "se fue la batería no fue intervención". Reemplaza "probablemente lo movieron a mano. Falta confirmarlo con el operador".
- Con eso, el "NO SIGUE el comando" del intento 51 (0 % de lo comandado en 50 pasos) es la batería: el propio aviso la lista entre las causas posibles. El único 10054 de la sesión (20:09:01) también.
- Lo que muestra la consola:
  - Su orden vigente era la detención: la del fin de la toma 51 y el latido de la guía, que manda parar cada 1 s.
  - No se movió de (2.26, 1.85) hasta 8 refrescos después del corte.
  - Después estuvo 30 refrescos SIN POSE.
  - Su pose reapareció en (2.01, 1.98), (2.33, 1.07) y (2.13, 1.33), y quedó en (2.10, 1.36). Todo eso pasó con el enlace todavía caído: se reabrió a los 84.4 s, tras 41 intentos sin respuesta.
- La consola no explica cómo pasó de (2.26, 1.85) a (2.10, 1.36) sin enlace. Queda como dato.
- La colocación automática de la toma 52 arrancó desde ahí, y la toma fue válida.

**Correcciones a la adenda del 06-11:**

1. **L0 del robot 4.** Es la del 21-10 a las 13:09 (`20261021_130948_L0_resumen.csv`), con la que se creó la campaña. El 06-11 no se corrió L0: la línea "[campaña] L0 del robot 4: L0 OK" es el lanzamiento leyendo esa L0 guardada.
2. **Intento 43.**
   - El aviso de 10 ticks salió en la misma decisión en que el 9 empezó a retroceder desde (0.29, 0.46). El de 20 ticks salió en la siguiente, y terminó en el frenado del 9 por pose vencida: el único de la sesión.
   - Por cómo funcionan los dos avisos, el 9 se quedó sin poses válidas; no fue un marcador que Motive mantuviera congelado, porque ese sigue mandando filas válidas. En la guía de la toma 44 el 9 aparece SIN POSE.
   - Las dos recuperaciones del 8 fueron en (0.22, 1.83) y (0.22, 1.84), a los 1.7 y 1.6 s.
3. **Intento 48.**
   - Las recuperaciones del 1 fueron en (1.67, 1.07) y (1.67, 1.06).
   - El 8 no se recuperó: terminó la toma congelado en (0.89, 2.76) y siguió así en la guía de la 49, donde frenó dos veces la colocación. La segunda vez, junto con el 9 congelado en (2.81, 2.32).
4. **Intento 51.** La causa es la batería del robot 1 (ver arriba).
5. **Reintentos de colocación.** Las notas de la tabla sólo los anotaron en el 41 y el 46. No gastan el intento. En total hubo 20 en 14 tomas:

   | Toma | 41 | 43 | 44 | 46 | 48 | 49 | 50 | 51 | 56 | 61 | 63 | 65 | 72 | 73 |
   |---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
   | Reintentos | 1 | 1 | 1 | 2 | 1 | 2 | 1 | 1 | 1 | 1 | 1 | 3 | 3 | 1 |

   - Causas: robots que "no avanza" en la colocación automática (30 avisos, de los cinco robots); marcadores congelados o sin pose (44, 48, 49 y 73); y distancias mínimas al obstáculo o a una pared.
   - **Por qué se gastó el intento 41:** los pedidos de colocar al 4 a mano consumen vueltas del mismo ciclo de 6 que los reintentos de los agentes (el bucle de `REINTENTOS_COLOCACION` en `demo_obstaculo_movil.py`).
     - En el 41 hubo 4 pedidos del obstáculo, así que el primer reintento de los agentes ya salió como "reintento 5/5" y el siguiente fallo gastó el intento.
     - En el 38, el 39 y el 40 los 6 pedidos fueron del obstáculo.
     - Para el operador: dejar bien al 4 en el primer pedido le conserva los reintentos a los agentes.
6. **Ticks fuera de plazo.**
   - "(antes 506–3041)" está mal: el 506 es de la campaña descartada `L2_obstaculo` (16-10). En `L2_obstaculo_2` las cifras anteriores son 1540, 3041, 1088 y 2046, así que el rango es 1088–3041. Que los 9890 del 06-11 sean el total más alto sigue siendo cierto.
   - Por decisión no lo es: 9890/12841 = 0.77 el 06-11, contra 1540/1703 = 0.90 y 3041/3752 = 0.81 en las dos sesiones del 21-10 (sus consolas están en el zip del reporte del 22-10). Del 23-10 y del 04-11 no hay conteo de decisiones registrado.
   - El total alto viene de la duración de la sesión, no de un lazo peor.
7. **Red.**
   - "un solo reset de enlace en 70 min (el del robot 1)" pasa a: **ningún reset atribuible a la red en 69 min**. El único 10054 fue la batería del 1.
   - La comparación con el 04-11 tiene que contar los seis robots: allí hubo **19** resets en 6 min (16 de los agentes y 3 del robot 4), no 16.
8. **Congelamientos.**
   - **Retrocesos.** En las tomas 42–72 hubo 25:
     - 11 terminaron en parada por marcador congelado;
     - 12 se recuperaron;
     - 2 quedaron sin resolver: el del 9 en (0.29, 0.46), que acabó en la parada por antigüedad de la 43, y el del 8 en (0.89, 2.76), cortado por el fin de la 48.
     - De los recuperados, la adenda no listó los dos del 8 en la 43, junto a la pared −x.
   - **Hay un segundo punto que se repite:** la esquina −x+y, con x entre 0.20 y 0.27 e y entre 2.77 y 2.83.
     - Ahí pararon 3 tomas: la 42 y la 45 con el robot 1, y la 70 con el 9.
     - Además hubo 2 congelamientos que sólo se vieron en las guías: el 9 en (0.27, 2.80) antes de la 48 y el 1 en (0.21, 2.83) antes de la 64.
     - "Un punto se repite" pasa a "**se repiten dos puntos**".
   - **Punto de (0.95, 2.80).** A los 9 de las tomas se suma el 1 congelado en (0.95, 2.82) en la guía de la 53, donde había terminado la 52: son 10 con las guías.
   - **Guías.** La sección contó sólo lo que pasó durante las tomas y el congelamiento de la 73. En las guías, los congelamientos nuevos fueron 7; el resto repite el marcador y la posición que habían parado la toma anterior:

     | Antes de la toma | 41 | 44 | 48 | 49 | 53 | 64 | 73 |
     |---|---|---|---|---|---|---|---|
     | Robot | 1 | 8 | 9 | 9 | 1 | 1 | 9 |
     | Posición | (0.60, 1.72) | (0.33, 2.06) | (0.27, 2.80) | (2.81, 2.32) | (0.95, 2.82) | (0.21, 2.83) | (0.80, 2.77) |

9. **Se revisó y queda igual:** "Sigue sin haber incluidas que salgan de una sesión con chequeo propio". Es el criterio del reporte del 22-10 (§9): la 2 y la 4 salen de la sesión de las 13:34 del 21-10, que tuvo el `CHEQUEO OK` de las 13:32:16 compartido, no uno propio.

**Sigue pendiente del operador:**
- qué se hizo en el laboratorio entre las 19:35 y las 19:38 del 06-11, cuando los marcadores volvieron;
- si hubo un `CHEQUEO OK` antes de la sesión de las 19:38.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261107_preCorreccion.md`.

### `L2_obstaculo_2`, 07-11: respuestas del operador sobre el arranque del 06-11

**Qué se hizo entre las 19:35 y las 19:38:** "solo corrí el motive".
- Motive no estaba corriendo. Mientras tanto, el servidor del Robotat aceptaba la conexión (24 ms) y devolvía los 6 marcadores congelados con valores basura, como mostró la verificación de las 19:34:58.
- Con Motive corriendo, la sesión de las 19:38:52 arrancó con los marcadores vivos.
- **Lección:** sin Motive, el servidor no da ningún aviso. En modo campaña el lanzamiento se cierra en unos 1 s con "fin de la sesión" (el FALLO silencioso), y no gasta intentos. Antes de lanzar hay que comprobar que Motive esté abierto y transmitiendo.

**Chequeo de la PC antes de la sesión de las 19:38:** "si", dio `CHEQUEO OK`.
- La salida no se pegó, así que no consta la hora ni la lista de procesos.
- Esto corrige "No consta un `CHEQUEO OK` antes de esta sesión" de la adenda del 06-11, y cierra el pendiente de la adenda anterior. El último pendiente también queda resuelto con la respuesta sobre Motive.

**Efecto en la declaración de chequeos.** Las 30 incluidas quedan así:
- **18** (intentos 44–72, del 06-11): de una sesión con `CHEQUEO OK` declarado por el operador, sin la salida pegada.
- **2** (intentos 2 y 4, del 21-10): de la sesión de las 13:34, con el OK de las 13:32:16 compartido.
- **10** (intentos 8, 9, 10, 13, 14, 19, 20, 21, 29 y 33): de sesiones sin chequeo registrado.

"Sigue sin haber incluidas que salgan de una sesión con chequeo propio" sólo vale contando las salidas pegadas, que es el criterio del reporte del 22-10. Con la declaración del operador, 18 sí lo tienen. Cómo contarlas en el reporte lo decide José.

**Para las próximas sesiones:** pegar aquí la salida del chequeo, como pide el protocolo.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261107_preRespuestas.md`.

### `L2_obstaculo_2`, 07-11: respuestas del operador a las preguntas del reporte del 07-11

Las preguntas salieron de `tesis/REPORTE_2026-11-07_campana_L2.md` (§9.5). Respuestas textuales del operador:

- **El "timed out" del primer lanzamiento del 06-11 (19:29:46):** "era que no estaba conectado al robotat". La laptop todavía no estaba conectada al Robotat. Del "timed out" del primer lanzamiento del 23-10 y del 04-11 no se preguntó; tienen la misma firma, pero no está confirmado.
- **Intento 24 (23-10), "ABORTO POR EL OBSTÁCULO: el obstáculo NO FRENA":** "si": el operador movió el 4 a mano durante la colocación. Confirma lo probable de la adenda del 23-10. El aborto lo causó la mano, no el robot.
- **04-11, robot 1 sin detención confirmada durante el corte:** "si, se lo quite, pero lo que pasó es que el server estaba fallando". El operador le cortó la alimentación al robot 1. Según él, lo que fallaba era el servidor. Queda como su lectura; la adenda del 04-11 apuntaba a la red del laboratorio, y ninguna de las dos está confirmada con el laboratorio.
- **06-11, robot 1 a las 20:09:** "le cambié la batería, fué cuando se quedó sin ella". Se le acabó la batería, y el operador se la cambió.
  - Eso explica el cambio de pose con el enlace caído: el robot se levantó para cambiarle la batería.
  - También explica que después anduviera hasta el final.
  - La respuesta anterior, "no fue intervención", se refería a la causa del corte (la batería), no a lo que pasó después.
  - Con esto queda resuelta la contradicción que anotaron la primera adenda del 07-11 y el reporte del 07-11.
- **06-11, `CHEQUEO OK` y app de Claude:** a la pregunta "¿a qué hora te dio el `CHEQUEO OK`, y cerraste la app de Claude antes de lanzar a las 19:38?", el operador contestó "si".
  - Se lee como que cerró la app de Claude antes de lanzar.
  - La hora del `CHEQUEO OK` sigue sin constar.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261107_preRespuestas2.md`.

### `L2_obstaculo_2`, 09-11: revisión del reporte del 07-11

- **La pose (2.10, 1.36) del robot 1 el 06-11 sí se leyó con el enlace caído**, como dice la primera adenda del 07-11.
  - La versión del 07-11 de `tesis/REPORTE_2026-11-07_campana_L2.md` la daba como leída después de la reconexión, y lo declaraba como corrección a esa adenda. La corrección se retira; la adenda estaba bien.
  - En la consola, la tabla con (2.10, 1.36) sale justo después de "RECONECTADO (reconexión n.º 1) a los 84.4 s".
  - Pero en cada refresco de la guía (`latir`, dentro de `_esperar_reposicionamiento` en `sesion_robotat.py`) el orden es: se leen las poses; `detener_todo` frena a los robots, y ahí `_reconectar` reabrió el enlace e imprimió "RECONECTADO"; recién entonces se imprime la tabla con las poses leídas antes.
  - **Para leer las guías en la consola:** la tabla que sigue a un "RECONECTADO" es de antes de la reconexión.
- El resto de la revisión quedó en la versión del 09-11 del reporte: el corte del 04-11 frente a "el server estaba fallando" (los enlaces de los robots no pasan por el servidor de poses), cuándo pudo correrse el `CHEQUEO OK` del 06-11, la laptop conectada a la red del Robotat en la lista de antes de lanzar, y Python 3.13 para el verificador.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261109_preRevision.md`.

### `L2_obstaculo_2`, 13-11: tercera revisión del reporte de la campaña (versión 13-11) y la primera corrida de `verificar_red.py` del 06-11

La versión 09-11 de `tesis/REPORTE_2026-11-07_campana_L2.md` pasó por una tercera ronda: 8 revisores, 24 hallazgos distintos, los 24 sostenidos por al menos 2 de 3 escépticos. Se aplicaron en la versión 13-11 del reporte, de su verificador y de su zip.

**Lo que cambia sobre lo que decía esta bitácora o el reporte anterior:**
- **La primera corrida de `verificar_red.py` del 06-11 sí dejó salida.** El reporte decía que no.
  - Su archivo de salida se creó a las 19:22:44 y se escribió por última vez a las 19:23:26 (1014 bytes). Ni el servidor de poses ni ninguno de los 6 robots abrió conexión (TimeoutError); el servidor y los robots 1, 5 y 8 perdieron el 100 % de los paquetes del ping; la lectura de marcadores falló.
  - Es coherente con la respuesta del operador del 07-11 ("era que no estaba conectado al robotat"): a esa hora la laptop no alcanzaba la red del Robotat. No consta hasta cuándo.
  - Va en el paquete como `derivados/verificar_red_20261106_1922_salida.txt`, copia literal. En `diagnostico_solo_lectura_20261106.txt` esa corrida figura a las 19:33:47 porque ahí está la hora en que quedó registrada como llamada interrumpida, no la de su lanzamiento.
- **La app de Claude el 06-11.** Se había cerrado para el chequeo de las 19:21:17; después se volvió a usar (el operador le pegó la salida de ese chequeo, y de ella salió la corrida de `verificar_red.py`). Los resultados de comandos del derivado van de las 19:33:47 (el aviso de la llamada cortada porque la sesión de la app terminó) a las 19:34:58; son horas de resultados, no de abrir y cerrar la app. El operador contestó "si" a la pregunta doble de si dio el `CHEQUEO OK` y cerró la app antes de lanzar; no dio ninguna de las dos horas.
- **El `CHEQUEO OK` declarado del 06-11 sólo cubriría la sesión de las 19:38:52 si se corrió después de cerrar la app por última vez.** Un OK anterior a ese cierre no cubre el uso de la app, porque el chequeo detecta el servidor de Inventor de la app. Si fue antes de las 19:33:31, quedó compartido con uno a cuatro lanzamientos que no arrancaron, entre 321 y 1055 s antes de abrir la sesión. Esto corrige "Con la declaración del operador, 18 sí lo tienen" (chequeo propio) de la segunda adenda del 07-11, y la ventana que daba la versión 09-11 del reporte.
- **Las "14 pérdidas seguidas" de la conexión con el servidor de poses del 04-11** (12:40) son 14 líneas "[poses] conexión perdida" seguidas, sin hora: consultas fallidas sobre la conexión perdida en el primer corte, que la sesión no reabre (un solo "[poses] conectado", al arrancar). No son caídas nuevas del servidor. La consola trae 21 de esas líneas en toda la sesión.
- **La pausa del intento 24 (23-10):** si vale la respuesta del operador (movió el 4 a mano), la causa del aborto era conocida; el desvío de pausa con causa sin resolver es sólo el del 36. Lo que se declara del 24 es el movimiento del 4 durante la colocación.
- **Protocolo del paquete:** es el que regía las sesiones del período. El 09-11 a las 01:36, ya armado el primer zip, se agregaron al chequeo de la PC los procesos del Exp R.

**Pendiente con el operador** (consta en el §10 del reporte): la hora del `CHEQUEO OK` del 06-11 y si lo corrió después de cerrar la app de Claude; y si el "timed out" del primer lanzamiento del 23-10 y del 04-11 también fue la laptop sin conectar al Robotat (no se le preguntó).

**Verificador:** 338 cifras (316 en la versión anterior). Sólo corre con Python 3.13 y escribe su salida en UTF-8.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261113_preRonda3.md`.

### `L2_obstaculo_2`, 14-11: CIERRE de la campaña (MÍNIMO) y preparación de la réplica

**Decisión de José (13-11, `SPEC_cierre_campana_L2.md`):** cerrar como está, 73/100 intentos y 30/50 incluidas, veredicto MÍNIMO. Desde el 09-11 no hay más turnos en el Robotat. No se sigue hasta el tope ni se hace el mapa de la sonda.

**Comprobaciones previas (sólo lectura, 14-11):**
- sin `sesion.candado` y sin sesiones abiertas (17 aperturas, 17 cierres); ninguna reserva sin resultado (el intento 73 ya figuraba "interrumpida");
- archivos congelados: 22/22 iguales a la cabecera de la campaña, y "IGUAL a lo probado" con el comando del protocolo (referencia del ensayo 1e del 17-10);
- el libro, antes del cierre: 73 intentos, 30 incluidas, 56 corridas, 0 tomas con contacto, 0 filas descartadas, sin columna de cobertura (no se miró).

**Cierre (14-11, 00:14:20):**
- Comando, desde `primerafase_webots/controllers/coordinador_enjambre`: `python demo_obstaculo_movil.py --modo L2 --robot-obstaculo 4 --campana L2_obstaculo_2 --cerrar-campana "Fin del tiempo disponible: no hay más turnos en el Robotat desde el 09-11. 73/100 intentos, 30 incluidas (MÍNIMO)."`
- Salida: "[campaña] 'L2_obstaculo_2' CERRADA: …", código 0. El libro quedó con 187 filas (una `cierre_campana` nueva, que guarda el estado), `estado()["cerrada"]` en True, los 22 congelados iguales y las 73 reservas y 73 resultados intactos.
- Estado al cierre: 73/100 intentos, 30/50 incluidas, 56 corridas, 0 tomas con contacto.
- **Frenos de respaldo: 0 en las 56 corridas.** Contado desde la columna `frenos` del libro: ninguna corrida con frenos > 0, suma 0, y también 0 en los 73 resultados. (El `frenos_ultima_corrida: 0` que muestra `estado()` es sólo el de la última.)

**Declaración del chequeo de la PC de las 18 incluidas del 06-11** (decisión de José, §10.2 del reporte del 13-11): "`CHEQUEO OK` declarado por el operador, sin salida pegada y sin hora. Según el operador, la app de Claude se cerró antes de lanzar a las 19:38:52; la hora del cierre no consta". No cuentan como chequeo propio con salida. Fuente: el operador contestó "si" a la pregunta doble de si dio el `CHEQUEO OK` y cerró la app antes de lanzar (extracto de la bitácora, adenda del 07-11 con las respuestas a las preguntas del reporte). Los demás pendientes del §10.3 del reporte quedan sin resolver y van como salvedades en el reporte final.

**Preflight de la réplica** (`python replica_con_obstaculo.py --campana L2_obstaculo_2 --verificar`, sin simulador, sin escribir salida): carga las 30 tomas incluidas (intentos 2, 4, 8, 9, 10, 13, 14, 19, 20, 21, 29, 33, 44, 46, 47, 48, 52, 53, 54, 56, 58, 59, 61, 64, 65, 66, 68, 69, 71 y 72), la auditoría pasa y el error máximo de la ida y vuelta env→lab→env es 2.22e-16. Código 0.

**Chequeo de la PC visto desde la sesión de Claude (diagnóstico, no es el previo a un lanzamiento):** `CHEQUEO FALLA` a las 00:14:55. A batería (40 %); ahorro de energía apagado; plan Equilibrado y modo Mejor rendimiento, como la referencia; procesos: OmenCap, OmenInstallMonitor, OverlayHelper, SystemOptimizer, OmenCommandCenterBackground, ChatGPT, Chrome y dos servidores de Inventor (`servidor_inventor_mcp`, de la app de Claude). Ningún proceso del Exp R. Por eso la réplica no se lanza desde esta sesión: la lanza José desde una PowerShell común, con la app de Claude cerrada, la laptop enchufada y la PC limpia, con `CHEQUEO OK` antes de cada lanzamiento y su salida pegada en la bitácora.

**Pasos que siguen** (en este orden, sin nada en paralelo con la réplica): réplica de las tomas, análisis fijado (sin `--desvio`), verificador independiente, reporte final con su zip y su `verificar_cifras`, y la entrada de bitácora de resultados. Nadie mira la cobertura antes del análisis.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261114_preCierreL2.md`.

### `L2_obstaculo_2`, 14-11: la réplica de las tomas (completa) y sus condiciones

**Qué corrió.** José lanzó la réplica desde una PowerShell común, `python replica_con_obstaculo.py --campana L2_obstaculo_2`, de las 00:31 a las 04:31 del 14-11, en `resultados_demo_obstaculo/replica_campana/L2_obstaculo_2/` con el prefijo `20261114_003144_`. Una sola pasada, sin `--reanudar` ni `--suplementaria`.
- Primer archivo a las 00:31:44, primera corrida a las 00:31:57, última a las 04:30:41, últimos archivos escritos a las 04:31:32.
- 270 corridas: 30 tomas (las 30 incluidas) × 3 condiciones (con obstáculo τ=0.0, sin obstáculo, con obstáculo τ=0.45) × 3 repeticiones.
- Cierre de la consola: "[réplica] completa."

**Código de salida y completitud.**
- El código de salida no se capturó (no se mostró `$LASTEXITCODE`). Se confirma por el código del script: "[réplica] completa." sólo se imprime en el camino que devuelve 0 (`_informar_completitud`, `sys.exit(main())`).
- Comprobación de sólo lectura, con la lógica del propio script: 270 corridas hechas, 0 grupos con la pasada normal incompleta, 0 grupos con 0 válidas sin su pasada suplementaria (el código de completitud sería 0), `validar_hechas` OK, y el sha256 de la pila de la réplica (`63b4078b13d1d875…`) igual al de hoy.

**Chequeo previo de la PC.** Según el operador, lo corrió antes de lanzar la réplica, pero no guardó la salida. No constan su resultado (`CHEQUEO OK` o `CHEQUEO FALLA`), su hora ni sus procesos, y no se pegó aquí como pide el protocolo. Se registra así, a pedido de José. El reporte final lo declara.

**Lo que muestra Windows** (comprobado por Claude el 14-11 a las 04:57; no es una declaración del operador):
- Procesos del chequeo ("PC limpia") que ya corrían antes de la réplica y seguían vivos después: Chrome (10 procesos; el más antiguo, desde el 13-11 a las 18:16:35) y `OmenCommandCenterBackground.exe` (desde el 13-11 a las 18:02:21). Estaban abiertos durante toda la réplica. Los demás procesos que listó el diagnóstico de las 00:14 (`OmenCap`, `OmenInstallMonitor`, `OverlayHelper`, `SystemOptimizer`, ChatGPT) ya no corrían a las 04:57; no consta cuándo se cerraron.
- Corriente (Kernel-Power): la laptop estaba a batería al lanzar y cambió de fuente a las 01:05:10. A las 00:52:47 hubo un "Critical Battery Trigger", a las 00:52:49 entró a suspensión y a las 00:52:50 reanudó. A las 01:05:11–12 hubo un Modern Standby breve. A las 04:57 estaba enchufada, al 100 %.
- De las 270 corridas, 25 empezaron antes de las 01:05:10 (a batería) y 245 después. Ciclo p95 medio: 35.0 ms (máx 46.7) a batería y 8.6 ms (máx 18.7) enchufada. Corridas con algún ciclo de más de 100 ms: 1 y 0.

**Corridas no válidas: 1 de 270.** Intento 20, con obstáculo, τ=0.0, repetición 1: "antigüedad de pose sobre el umbral". Empezó a las 00:52:12 y duró 779.8 s (las demás, unos 50 s), hasta las 01:05:12, es decir, durante el estado de batería crítica y la suspensión. Las repeticiones 2 y 3 de esa toma son válidas. No hay ningún grupo con 0 válidas.

**Lo que se leyó.** Para lo de arriba se leyeron sólo las columnas de inicio, validez, motivo y ciclo de la tabla de tomas de la réplica. La consola que pegó José trae las coberturas de la réplica por corrida (las imprime el script): no se usaron ni se tabularon. La cobertura medida en el hardware no se miró.

**Decisión.** Claude señaló la brecha con el protocolo y propuso declarar la réplica tal cual o repetirla. José pidió registrar el chequeo como arriba y seguir con el análisis fijado: la réplica no se repite.

**Siguen** (en este orden): análisis fijado sin `--desvio`, verificador independiente, reporte final con su zip y su `verificar_cifras`, y la entrada de bitácora de resultados.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261114_preReplicaL2.md`.

### `L2_obstaculo_2`, 14-11: análisis fijado, verificador independiente y reporte de cierre

**Análisis fijado.** `python analizar_campana_l2.py --campana L2_obstaculo_2`, sin `--desvio`, el 14-11 a las 10:16:47, desde `primerafase_webots/controllers/coordinador_enjambre`. Salió con código 0 y veredicto MÍNIMO. Los sha256 del plan, de `analizar_campana_l2.py` y de `campana_obstaculo.py` son iguales a los del libro. Salida en `resultados_demo_obstaculo/analisis_campana/L2_obstaculo_2_20261114_101647/` (`analisis.json`, `pares.csv`, `no_incluidas.csv`, `seguridad_tomas.csv` y `salida.txt`).

**Verificador independiente.** `python verificar_campana_l2.py resultados_demo_obstaculo/analisis_campana/L2_obstaculo_2_20261114_101647`, con Python 3.13.14. Salió con código 0: 131/131 coinciden. También da 131/131 dentro de la copia del paquete de datos.

**Resultados** (el detalle está en `tesis/REPORTE_2026-11-14_cierre_campana_L2.md`):
- 73 intentos, 56 corridas, 30 incluidas; veredicto MÍNIMO.
- **Principal:** hw − réplica = −0.0131, IC95 [−0.0292, +0.0029] (n = 30); no hay brecha detectable, acotada a |brecha| ≤ 0.0292 con 95 % de confianza; no se afirma equivalencia. Wilcoxon p = 0.0368, bootstrap [−0.0284, +0.0023], p de la t = 0.1047 (referencias que no deciden). Sensibilidades A–E: ninguna cambia la conclusión.
- **Seguridad:** 0 de 56 corridas con contacto (< 0.15 m, IC95 [0.000, 0.064]) y 0 de 56 con freno de respaldo; distancia mínima al obstáculo 0.2648 m. `d_pared_min` hw − réplica = −0.0302 m, IC95 [−0.0354, −0.0251].
- **Costo del obstáculo (réplica, con − sin):** +0.0077, IC95 [−0.0001, +0.0155].
- **30-09 (descriptivo):** brecha por pares +0.0077 y por escenario +0.0123, con IC95 que contienen el 0. El a3 sigue NO PASA (media de Δ = −0.00252, IC95 [−0.01052, +0.00549], margen ±0.00827): va como salvedad.
- **Post hoc:** ciclo p95 de la réplica 11.64 ms (con obstáculo, τ = 0), 11.31 ms (con obstáculo, τ = 0.45) y 10.28 ms (sin obstáculo) de media; 8 de 30 tomas con desvío entre repeticiones mayor que 0.01 (ddof = 1), contra 6 de 50 el 30-09.

**Reporte final y zip.** `tesis/REPORTE_2026-11-14_cierre_campana_L2.md` y `tesis/REPORTE_2026-11-14_cierre_campana_L2_datos.zip`, con `scripts/verificar_cifras_cierre_campana_l2_20261114.py` (151/151 desde una extracción limpia; 41 errores puestos a propósito, detectados; Python 3.13). El zip repite las rutas del proyecto para que el verificador independiente corra dentro de él, y trae `cierre_a3_20261010_b/` completo con su diagnóstico.

**Revisión del reporte.** Tres revisores independientes (hechos, cumplimiento de la spec y el plan, y el verificador con el paquete) reportaron 20 hallazgos; dos escépticos por hallazgo confirmaron 19, y se aplicaron todos. Los de más peso:
- las condiciones de la réplica según Windows ahora citan sus fuentes (las consultas de las 00:14:55, las 04:57 y las 10:19:47); el evento de cambio de corriente no trae dirección, y que fue de batería a enchufada se infiere; también se declara lo que no consta durante la réplica (plan y modo de energía, ahorro, ChatGPT, servidor de Inventor y otras cargas en paralelo);
- la frase "el mismo ruido entre repeticiones que el 30-09" del a3 no coincide con el máximo en los mismos 12 episodios (0.0287 contra 0.0175): queda como pendiente, sin cambiar el plan;
- el costo del obstáculo se redactó sin una frase más fuerte que el IC;
- se declararon las 5 reservas "interrumpida" (intentos 1, 17, 25, 35 y 73), las 10 aperturas sin tomas, el cierre (b) (pasó en las 180 corridas con obstáculo) y el (a1) por referencia al reporte del 22-10;
- la unidad de la primera fila de "Para la tesis".
- **Hallazgo propio, que ningún revisor vio:** la pila del a3 (`b5a289046f966592…`) no es la de la réplica de la campaña (`63b4078b13d1d875…`). Difieren 6 de los 25 archivos (`config_robotat.py#sin_calibracion`, `calibracion_medida.json`, `campana_obstaculo.py`, `demo_obstaculo_movil.py`, `analizar_campana_l2.py` y el plan); los otros 19, entre ellos `replica_con_obstaculo.py`, `simulador_robotat.py`, `sesion_robotat.py` y `lib/`, son iguales. El reporte lo declara en el §8.

**Declaraciones.** Las 18 incluidas del 06-11 quedan como "`CHEQUEO OK` declarado por el operador, sin salida pegada y sin hora; según el operador, la app de Claude se cerró antes de lanzar a las 19:38:52; la hora del cierre no consta". Ninguna incluida sale de una sesión con chequeo propio con salida pegada. La réplica corrió sin salida de chequeo guardada y no en las condiciones del protocolo (entrada anterior de hoy).

**Sin tocar.** Archivos congelados, plan, márgenes y criterio de inclusión. Sin `--corregir-campana` ni `--desvio`.

**Sigue pendiente** (salvedades del reporte, §11): la L0 habilitante sin `CHEQUEO OK`; la recalibración de Motive; el cierre del libro que no muestra su causa; el modo de energía de referencia; la tolerancia de colocación de la L0; la frase del ruido del a3; el defecto de `--simulador`; las ruedas de los robots que "no avanzan"; la causa del corte de red del 04-11; la hora del `CHEQUEO OK` del 06-11 y el "timed out" del 23-10 y el 04-11; los puntos ciegos de los marcadores (no se hizo el mapa de la sonda); y la réplica sin chequeo guardado.

**Respaldo:** antes de esta adenda, `BITACORA_TECNICA_respaldo_20261114_preResultadosL2.md`.
