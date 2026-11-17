# Exp Q — Obstáculos móviles: la versión dinámica del Exp O (propuesta)

**Estado:** PROPUESTA del 2026-10-19, sin código. Espera el OK de José. No se creó ni se modificó ningún archivo del proyecto salvo éste.

**La letra es la Q.**
- En la bitácora, de la A a la O tienen entrada, y la P está tomada: es la confirmación prerregistrada del Exp J (`BITACORA_TECNICA.md:1483-1492`, `fase_preliminar2/experimento_P/PREREGISTRO_P.md`).
- La Q ya aparece una vez, en `PROPUESTA_OBSTACULO_MOVIL.md` (01-10, §2 "Fase 2" y decisión 1), como un "Exp Q en Python" opcional con otro diseño: retardo de 0.5 s, k = 0.4, F0/F1/F50 entre 0.03 y 0.10 m/s. No se eligió (José: "sólo la demo").
- Esta propuesta ocupa la Q con el diseño pedido ahora. Aquél queda como antecedente, sin letra.

**Encuadre, el mismo del Exp O.** Esto **no** prueba adaptabilidad de la política: la observación (24 dimensiones) no codifica obstáculos y el agente es ciego a ellos. Prueba la **generalidad de la capa de seguridad** (el filtro CBF con el término de velocidad y el escape) frente a obstáculos que se mueven, y a qué costo en progreso de tarea.

**Base.** Leí `fase_preliminar2/CLAUDE.md`. De la bitácora: la entrada del Exp O (`:2358-2677`), la Fase 0 del obstáculo móvil (`:4323-4418`) y sus adendas hasta `L2_obstaculo_2` lista (`:4420-4946`). También el código y los resultados del Exp O, y de `PROTOCOLO_L0_L2.md` la lista de congelados y el chequeo previo (`:206-213`, `:253-261`). Verificado hoy, sólo leyendo:
- el sha256 del modelo y de las copias de `lib/` (tabla del §1);
- que el stack instalado es el de `requisitos_congelados_2026-09-09.txt` (torch 2.10.0, SB3 2.7.1, numpy 2.4.1, scipy 1.17.1);
- las cifras geométricas del §3. Salen de un script de apoyo en el scratchpad de la sesión: no está en el proyecto, no corre episodios y tardó 33 s. La implementación las recalcula en su verificación de pasabilidad.

---

## 1. Lo que no cambia, y cómo se demuestra

| | En el Exp Q | Cómo se verifica |
|---|---|---|
| Política | `modelo_sanidad.zip`, sin reentrenar, `deterministic=True` | sha256 `34831589…0c27`, igual al del Exp O y al congelado de la campaña (`controllers/coordinador_enjambre/modelos/`) |
| `lib/` | copias byte a byte de `expO_obstaculos/lib/`: `__init__.py` `65d6ab2d…`, `concentration_dynamics.py` `e707e79b…`, `filtro_cbf.py` `b2d94289…`, `swarm_env_skeleton.py` `f41b4c6e…` | manifiesto sha256 antes de correr y al cerrar |
| Filtro | `FiltroCBFParedes` con ℓa 0.05, α 2.0, w_ω 0.3, d_segura 0.18; robot-robot 50/50 con 0.25; margen de obstáculo 0.18; V_MAX 0.31, Ω_MAX 6.2832; ante un QP infactible, el fallback (0, 0) de siempre | las constantes se importan del módulo del Exp O, no se reescriben; control bit a bit (§4) |
| Escape | el de tres términos del Exp O, con todas sus constantes `ESC_*` (`correr_experimento_O.py:91-101`); suma las normales de obstáculo con h geométrico < 0.06 | ídem |
| Protocolo | n = 5, arena 3.0, 500 pasos (50 s), semillas 420000–420099, bordes bloqueantes, sin aleatorización de dominio, pesos del Trial 13 | ídem |
| Código del Exp O | `entorno_obstaculos.py` (`c69b5e76…`) y `correr_experimento_O.py` (`67509b60…`), copiados byte a byte a la carpeta nueva y usados por importación y herencia | sha256 de la copia contra el original; los originales no se abren para escribir |
| Congelados de la campaña | el Exp Q no escribe nada en `controllers/coordinador_enjambre/` ni importa nada de ahí | chequeo previo del protocolo en "IGUAL a lo probado" antes de empezar y al terminar; las dos salidas van a la bitácora |

**Lo que NO entra de la campaña**, aunque forme parte de F2 o de la demo:
- **El predictor, el peso de giro 3.0 condicional y el rescate del QP infactible.** Cambian el costo del QP o su fallback, que este pedido deja fijos.
- **El freno de respaldo.** Haría cooperativo al obstáculo.
- **La ventana de 0.3 s de v̂, su zona muerta de 0.01 m/s, la patada y la rampa.** Son de la medición y la actuación del laboratorio. En Python la velocidad del obstáculo es exacta y no hay rampa.

---

## 2. Lo único nuevo

### 2.1 Los obstáculos se mueven

**Movimiento.** Cada obstáculo recorre un círculo antihorario a 0.05 m/s. La posición se calcula exacta a partir del índice del paso, sin acumular: p_k(t) = c_k + ρ_k·(cos φ_k(t), sen φ_k(t)), con φ_k(t) = φ_k0 + (0.05/ρ_k)·0.1·t. No coopera: nunca frena, y si llega a un agente, lo empuja.

**Orden dentro del paso:**
1. En la decisión t, la barrera y el escape usan p_o(t) y v_o(t).
2. `env.step`:
   1. **[nuevo]** los obstáculos pasan a t + 1;
   2. los agentes integran, y el contacto se evalúa contra los discos en t + 1, con la misma proyección radial del Exp O (θ intacto). Así cubre los dos casos: el agente que choca con el obstáculo y el obstáculo que choca con el agente;
   3. el resto del paso es el del Exp O: objetivos, AoI y máscara.
3. Las distancias se miden después del paso, contra las posiciones en t + 1.

Con una trayectoria quieta, el paso 2.1 no cambia nada y el paso es el del Exp O.

**Atribución del contacto** (descriptiva, no cambia el criterio): "por empuje" si la posición nueva del agente queda fuera del disco de contacto en p_o(t) pero dentro del de p_o(t + 1); si no, "por avance".

### 2.2 La fila del obstáculo: F1 de la campaña, en Python

Es la de `demo_obstaculo_movil.py:36-62` y `:1479-1519`:

```text
h   = ‖p_i − p_o‖ − (r + 0.18),   n = (p_i − p_o)/‖·‖,   c = n·G(θ_i)
rhs = −α·h + s/k,                 s = max(0, n·v̂_o, n·v_cmd)
rhs se satura al 90 % de |c_v|·V_MAX + |c_ω|·Ω_MAX, y entra como h_eq = −rhs/α
```

En Python se simplifican tres cosas, y ninguna es una elección:
- **k = 1.** El entorno ejecuta la acción comandada (`swarm_env_skeleton.py:847-866`; sin aleatorización de dominio no hay fricción). El 0.40 es el factor de velocidad del laboratorio.
- **v̂ = v_cmd = v_o.** No hay medición ni retardo, así que s = max(0, n·v_o).
  - v_o es lo que el obstáculo se va a desplazar en el paso, dividido por 0.1 s (la secante): exactamente lo que ocurre entre esta decisión y la siguiente.
  - Difiere de la tangente en menos de 0.1 % en módulo y en ≤ 0.042 rad en dirección, en S3, el círculo más cerrado.
- **r es el de cada obstáculo del Exp O**, no el 0.15 del robot 4 (D_o = 0.33 en la campaña).

**Con v_o = 0, la fila es la del Exp O.** La función nueva llama a `barreras_obstaculos` del Exp O (`correr_experimento_O.py:181-196`) y sólo reemplaza h por h_eq en las filas con s > 0 (decisión 6, sobre la saturación).

**Margen.** Es la regla del Exp O (0.075 de chasis + 0.05 de punto de mira + 0.031 de avance entre decisiones = 0.156 ≤ 0.18), con los 5 mm que se mueve el obstáculo en cada decisión: 0.075 + 0.05 + (0.31 + 0.05)·0.1 = 0.161 ≤ 0.18. La cota de diseño centro→superficie sigue siendo 0.13 m.

### 2.3 Una consecuencia estructural, y la predicción que sale de ella

**El cambio.** En el Exp O, u = (0, 0) cumple toda fila con h ≥ 0 (c·0 = 0 ≥ −α·h): el QP sólo puede quedar infactible después de una violación. Con el obstáculo en movimiento eso deja de valer.
- Si h < s/α (hasta 2.5 cm con el obstáculo de frente), la fila exige retroceder activamente.
- Si otra fila se opone (un vecino o una pared detrás), el QP puede ser infactible con todos los h ≥ 0, y cae al fallback (0, 0).

Es el encierro de la Fase 0 (bitácora `:4390-4395`), que la campaña resolvió con el rescate de F2. Acá el rescate queda fuera por diseño.

**Hipótesis, no criterio:**
- **Si algún nivel falla, la falla más probable es un fallback del QP en un encierro**, obstáculo más vecino. Si pasa, se reporta como el límite de F1 sin rescate y no se ajusta nada.
- **El mecanismo por el que F1 falló en la Fase 0 no debería reaparecer.** Ahí el QP pagaba el término de velocidad girando, con 0.85 s de retardo (`:4358-4362`), y eso necesita retardo: en Python no hay. Se mide con la parte de ω en las filas ligantes (§5).

---

## 3. Diseño

### 3.1 Niveles y trayectorias

En los tres niveles van los mismos obstáculos del Exp O (cantidad y radio), con trayectorias alrededor de sus posiciones, fase inicial sorteada por semilla, y todos antihorarios a 0.05 m/s.

| | Obstáculos (Exp O) | Trayectoria | Vueltas por episodio | Hueco mín. a pared / entre obstáculos, peor instante | Celdas inaccesibles todo el episodio | Área h ≥ 0 del punto de mira |
|---|---|---|---|---|---|---|
| S1 | 1, r = 0.30 | el círculo de la campaña: R 0.60 alrededor de (1.5, 1.5) | 0.663 (2.5 m) | 0.60 / — | 0 | 6.245–6.248 m² (Exp O 6.2454) |
| S2 | 2, r = 0.25 | un círculo de ρ = 0.20 alrededor de (1, 1) y otro alrededor de (2, 2), fases independientes | 1.989 | 0.55 / 0.5142 | 6 (0.146 %) | 5.806–5.810 m² (Exp O 5.8078) |
| S3 | 4, r = 0.20, más 1 central de r = 0.25 | un círculo de ρ = 0.06 alrededor de cada posición, fases independientes | 6.631 | 0.49 / 0.4907 | 180 (4.395 %) | 4.572–4.579 m² (Exp O 4.5719) |

Los huecos son el peor caso analítico sobre todas las fases. En S2 y S3 las 100 semillas lo alcanzan a 4 decimales. El área se calculó con una rejilla de 0.01 (el Exp O usó 0.005). La región factible es conexa con h ≥ 0 y con h ≥ 0.06 en todos los instantes calculados (cada 25 pasos, las 100 semillas). Como referencia, el Exp O enmascaraba 124, 186 y 296 celdas.

**S1.** Con r = 0.30 en el círculo de 0.60, el corredor del punto de mira entre el obstáculo y la pared mide 0.24 m con h ≥ 0 y 0.12 m con h ≥ 0.06. Ninguna celda queda tapada todo el episodio, así que no hay máscara. El radio es la decisión 2.

**S2: por qué ρ = 0.20.** Con fases independientes, la distancia entre los dos obstáculos baja hasta 0.914 − 2ρ, y para que el hueco no baje de 0.48 tiene que ser ρ ≤ 0.217. Contra la pared, 0.75 − ρ ≥ 0.48 da ρ ≤ 0.27. Con 0.20 quedan 3.4 cm sobre el umbral en el peor instante. Las 6 celdas inaccesibles todo el episodio son el disco de radio r − ρ = 0.05 alrededor de cada centro.

**S3: por qué ρ = 0.06, y qué significa.**
- La pared da ρ ≤ 0.55 − 0.48 = 0.07, y la distancia de una esquina al centro da ρ ≤ (0.6107 − 0.48)/2 = 0.065. **El S3 del Exp O ya estaba al borde de la pasabilidad**: cualquier amplitud mayor rompe el 0.48 en algún instante.
- El resultado es la misma velocidad con una amplitud de 6 cm: una vibración, no un recorrido.
- En el peor instante, el corredor con h ≥ 0.06 mide 1 cm.
- El S3 estático ya falla el criterio de recuperación en el Exp O. **Una falla del S3 dinámico es lo esperable.** Lo informativo es la comparación con los obstáculos quietos: si el movimiento agrega fallas.

**Fases.** `np.random.default_rng([semilla, 3]).uniform(−π, π, size=m)`, en el orden de los obstáculos (verificado: el primer elemento es el mismo que un sorteo escalar). El flujo 3 es nuevo; el [semilla, 1] de los objetivos y el [semilla, 2] de los agentes siguen siendo los del Exp O. `fase_arranque_obstaculo` de la demo usa [semilla, 7], y no lo reuso: el vínculo sería cosmético, las semillas del laboratorio son otras y en la L2 el 4 arranca de la proyección de su pose.

**Una propiedad que hace limpia la comparación con los quietos.** La fase es uniforme y la velocidad angular es común. Por eso, sobre las 100 semillas, la distribución de las posiciones de los obstáculos en cualquier instante es la misma que en t = 0. El obstáculo móvil y el quieto en su punto de arranque comparten la geometría marginal; lo único que los distingue es el movimiento.

### 3.2 Pasabilidad a lo largo de la trayectoria

Es el chequeo del Exp O (`correr_experimento_O.py:541-569`): huecos > 0.48 y región del punto de mira conexa con h ≥ 0 y con h ≥ 0.06. Se aplica:
- en cada instante, del 0 al 500, de cada una de las 100 semillas, y además el peor caso analítico sobre todas las fases;
- la conexidad, con una rejilla de 0.01 en todos los instantes y con la de 0.005 del Exp O en el peor instante de cada semilla.

Si algo no cumple: **PARAR**, "no pasable por construcción", como en el Exp O, y aviso.

### 3.3 Máscara

**La regla.** Una celda se enmascara si su centro queda dentro de algún disco (radio r) en **los 501 instantes** del episodio: el criterio del Exp O, "centro dentro de r", extendido en el tiempo.
- Se calcula por episodio, antes de correr, desde la trayectoria.
- En la condición quieta da exactamente la máscara del Exp O en el punto de arranque.
- Las celdas enmascaradas se fuerzan a AoI = 0, como en el Exp O.

**Las celdas que el obstáculo tapa sólo por un rato no se enmascaran.** Acumulan AoI mientras están tapadas y la política puede sentirse atraída hacia ellas: es parte del costo del movimiento. Es también como funciona la campaña: en el laboratorio no hay máscara (`demo_obstaculo_movil.py` no tiene ni máscara ni rebote).

### 3.4 Los objetivos: transparentes (recomendado; decisión 3)

En el Exp O, los objetivos rebotaban elásticamente en los discos. Propongo que en el Exp Q **atraviesen los obstáculos**, tanto los móviles como los quietos de la segunda comparación. Por qué:

1. **Rebotar en un disco que se mueve está mal planteado acá.** Los objetivos van a 0.05–0.15 m/s (`concentration_dynamics.py:198`), lo mismo que el obstáculo. Un rebote de espejo sin transferencia de cantidad de movimiento deja a un objetivo de 0.05 m/s que va delante del obstáculo chocando en cada paso, y el obstáculo lo arrastra. Ese "arreo" es un acoplamiento artificial, sin contraparte en el encuadre (una floración no rebota en una lancha), y obligaría a una decisión de modelado sin referencia.
2. **Elimina por construcción la confusión que en el Exp O obligó al control fantasma.** Con objetivos transparentes, su trayectoria es idéntica paso a paso en las tres condiciones: el campo no depende de los agentes y la reubicación usa su propio generador. La diferencia con el control es sólo la del sistema.
3. **Es lo que hace la campaña:** en el laboratorio, los objetivos virtuales no interactúan con el 4.
4. **Usa una perilla que el código del Exp O ya tiene:** `obstaculos_rebote=()` (`entorno_obstaculos.py:79-84`), la misma del fantasma.

**El costo.** Es un tercer cambio respecto del Exp O, y no es inocuo. En el S1 del Exp O, el rebote en el disco central costó −0.01048* de cobertura accesible por la sola dinámica de los objetivos (fantasma − control, bitácora `:2601`). Las Δ del Exp Q, puestas al lado de las del Exp O, mezclan las dos reglas; las comparaciones internas del Exp Q, no.

**La alternativa.** Rebote en el disco móvil, con un control fantasma por nivel: una condición más por nivel y código nuevo para el rebote.

**Los objetivos que nacen dentro de un disco** se reubican igual que en el Exp O (a ≥ r + 0.05, con [semilla, 1]), respecto de la posición inicial. No hace falta por física, pero deja las condiciones iniciales idénticas en las tres condiciones y lo más cerca posible del Exp O.

### 3.5 Reubicaciones de arranque

Se aplica la regla del Exp O tal cual (`entorno_obstaculos.py:94-113` y `:177-200`), **respecto de la posición inicial de cada obstáculo**:
- los agentes a menos de r + 0.25 se reubican con [semilla, 2], en el 70 % central y a más de 0.31 de los demás;
- los objetivos a menos de r + 0.05 se reubican con [semilla, 1].

El obstáculo móvil y el quieto arrancan en el mismo punto, y el control usa ese mismo punto para sortear: **las condiciones iniciales son idénticas en las tres condiciones.**

En t = 0, un agente reubicado justo delante del obstáculo tiene h ≥ 0.02 y rhs = −0.04 + 0.05 = 0.01: le basta retroceder, así que es factible.

**Por qué no respecto de toda la trayectoria.** En S1 eso reubicaría casi a todos (el barrido es un anillo de 0.30 a 0.90 m del centro, 2.26 m²) y alejaría el arranque del sorteo del protocolo.

Se reportan los agentes y los objetivos reubicados por episodio.

### 3.6 Condiciones y comparaciones, por nivel

| Condición | Obstáculos en barrera y contacto | Se mueven | Rebote de objetivos | Máscara | Poses y objetivos iniciales |
|---|---|---|---|---|---|
| `Sk_din` | sí | sí | no | la permanente (§3.3) | sorteo + reubicación respecto del arranque |
| `Sk_quieto` | sí, quietos en el punto de arranque | no | no | la del Exp O en el arranque | las mismas |
| `Sk_ctrl` | no | — | no | ninguna (para la métrica usa las dos de arriba) | las mismas |

**Comparaciones pareadas por semilla:**
1. **`Sk_din − Sk_ctrl`**, como en el Exp O: el costo del obstáculo móvil.
2. **`Sk_din − Sk_quieto`**: lo que agrega el movimiento. Las condiciones iniciales, los objetivos, el área bloqueada instantánea (la tabla del §3.1) y la geometría marginal (§3.1) son los mismos. Incluye tres cosas, y se declaran: la interacción dinámica (barrera y escape), lo que el obstáculo ocupa al pasar por celdas que en la quieta están libres, y menos lo que libera del punto de arranque.
3. **Descriptiva: `Sk_quieto − Sk_ctrl`.** Es el efecto estático "a la Exp O" en los puntos de arranque, con objetivos transparentes. Es el puente al Exp O, declarado como no comparable 1 a 1 (otra posición y otra regla de objetivos).

**Cobertura.** Cada fila guarda todas las variantes, para que cada comparación tenga el mismo denominador en los dos lados:
- **accesible**, sobre las celdas fuera de la máscara permanente, para la comparación 1. En el control se mide sobre esas mismas celdas, como en el Exp O. En S1 es la cuadrícula entera;
- **accesible común**, sobre las celdas fuera de la máscara del arranque, para las comparaciones 2 y 3. Contiene a la permanente, porque ésta está dentro de cualquier disco instantáneo;
- **cuadrícula completa**, con las celdas enmascaradas como nunca cubiertas;
- **la del protocolo**, 1 − media en float32.

### 3.7 Orden de corrida y regla de parada

**El orden:**
1. El control bit a bit (§4). Si no da 1000/1000, se para.
2. S1, con sus tres condiciones juntas. Se revisan los criterios.
3. S2, ídem.
4. S3.

**La regla, la del Exp O sin cambios** (`correr_experimento_O.py:115-120`). Se detiene al primer nivel en que, sumado sobre los 100 episodios de `Sk_din`, haya algún:
- contacto con obstáculo;
- escape agotado;
- fallback del QP;
- escape infactible con obstáculo activo.

Entonces no se corre el nivel siguiente.

**Lo que sólo se reporta:**
- la intervención > 0.5, que es un indicador y no detiene;
- los criterios de `Sk_quieto` (decisión 7).

La salvedad conocida del Exp O se mantiene: el escape agotado no es específico del obstáculo (`S3_ctrl` tuvo uno). El criterio queda como está y se reporta con su Δ pareada contra el control y contra el quieto.

---

## 4. Control obligatorio y pruebas, antes de correr

**4.1 Bit a bit con velocidad cero.**

**El camino que se prueba es el nuevo:** el entorno nuevo, el bucle de episodio nuevo, la fila F1 y el gestor de escape con obstáculos actualizables. Se le dan trayectorias quietas en las posiciones del Exp O, rebote como en el Exp O y su máscara.

**Lo que tiene que reproducir** (decisión 8): las 1000 corridas distintas del Exp O, en todas las columnas salvo `t_episodio_s`, con igualdad exacta de los float leídos del CSV:
- S0 (100 corridas, `experimento_O_completo.csv`, 43 columnas);
- S1–S3 con sus controles (600 corridas), contra el mismo CSV, y en las 49 columnas de `experimento_O_complementario.csv`;
- las 300 corridas del fantasma (`experimento_O_complementario.csv`).

**Antes de lanzarlo:** el stack contra los requisitos congelados, para que una diferencia sea atribuible al código. Hoy coincide.

**Si no da 1000/1000:** se para y aviso. No se corre nada más.

**Por qué la saturación sólo con s > 0 (decisión 6).** Con s = 0, la F1 de la campaña satura si −α·h > 0.9·capacidad, o sea con h < −0.1395. En el Exp O, el mínimo centro→superficie (0.12876785 m) implica h ≥ −0.1012 en el punto de mira: con estas semillas la saturación no se dispararía nunca. Pero esa igualdad sería empírica. Con la saturación sólo para s > 0, es estructural.

**4.2 Pruebas unitarias,** en `test_experimento_Q.py`:
- **Fila F1:**
  - con v = 0, igual bit a bit a `barreras_obstaculos`, en poses al azar;
  - con v ≠ 0, igual a la fórmula de `demo_obstaculo_movil.py:1498-1519` con k = 1, reescrita en la prueba, sin importar nada del coordinador.
- **Objetivos transparentes:** posiciones idénticas en `Sk_din` y `Sk_ctrl` en los 500 pasos, en varias semillas.
- **Trayectoria:**
  - el radio, exacto a 1e−12;
  - el desplazamiento por paso;
  - con una trayectoria quieta, la máscara permanente igual a `mascara_ocupada`.
- **Contacto por empuje:** un caso guionado en que el obstáculo avanza sobre un agente quieto. Se cuenta, se proyecta y se atribuye "por empuje".
- **Control negativo de la instrumentación:** el obstáculo móvil sin su fila en el filtro, en 10 semillas, tiene que dar contactos. Muestra que el contador ve los contactos con algo que se mueve; no es un resultado.

**4.3 AST al terminar.** Script `comparar_ast_Q.py`:
- los originales del Exp O, con el mismo sha256 que antes;
- las copias, idénticas;
- los módulos nuevos, sólo con clases y funciones de nivel superior nuevas: las clases heredan y agregan o sobrescriben métodos dentro de sí mismas;
- ninguna asignación a atributos de un módulo importado, o sea, ningún parche en caliente;
- ningún nombre del Exp O redefinido a nivel de módulo.

---

## 5. Métricas, fijadas antes de correr

**Deciden la parada:** los cuatro criterios del §3.7.

**Se reportan, como en el Exp O:**
- **Seguridad:**
  - contactos con obstáculo (eventos y agente-episodios, por empuje y por avance);
  - colisiones < 0.15 y < 0.22 m;
  - d_min centro→superficie (mínimo global) y agente-episodios bajo 0.13;
  - contacto con pared y d_min a la pared.
- **Solver:** fallbacks del QP y, nuevo, **filas F1 saturadas**. Es un indicador: una fila saturada relaja la barrera.
- **Escape:** activaciones, con obstáculo activo al disparar, infactibles (por motivo, opuestas o sin activas, y por tipo: pared, robot u obstáculo), agotados y fracción del ciclo.
- **Intervención por tipo de barrera** (pared, robot u obstáculo; por h mínimo y por restricción ligante; varios tipos a la vez) y magnitud. El indicador > 0.5, con la cantidad de episodios que lo superan.
- **Ocupación de la periferia** (< 0.5 m de una pared), banda de 0.18 y las cuatro coberturas del §3.6.

**Nuevas, descriptivas:**
- **Exposición:** agente-pasos con la fila del obstáculo activa (h geométrico < 0.06) y, dentro de ellos, con s > 0, es decir, con el obstáculo acercándose. Dice si el movimiento generó encuentros de verdad.
- **Filas del obstáculo ligantes con s > 0**, y la parte de ω en c·u en esas filas: el mecanismo de giro de la Fase 0.

**Estadística, la de los Exp C–N:**
- Δ pareada por semilla, IC95 = media ± 1.96·EE (ddof = 1), "*" si el intervalo excluye el 0, y la cantidad de semillas con Δ > 0 y con Δ < 0;
- sin corrección por multiplicidad, como en el Exp O; se declara;
- los criterios de falla son recuentos y se reportan sin IC.

---

## 6. Archivos y verificación de cifras

`primerafase_webots/experimentos/expQ_obstaculos_moviles/`:
- **copias:** `lib/`, `modelos/`, `entorno_obstaculos.py` y `correr_experimento_O.py`;
- **nuevos:** `entorno_obstaculos_moviles.py`, `correr_experimento_Q.py`, `analizar_experimento_Q.py`, `verificar_cifras_Q.py`, `test_experimento_Q.py` y `comparar_ast_Q.py`;
- **`resultados/`:** `control_bit_a_bit_Q.csv`, `experimento_Q_completo.csv` (sin redondeo, con respaldo automático si ya existe), `registro_Q.txt`, `corrida_Q.log`, `resumen_experimento_Q.txt` y `manifiesto_sha256_Q.txt`;
- **`figuras/`:** las dos del Exp O, en su versión dinámica (300 dpi, es-ES, sin título).

**`verificar_cifras_Q.py`** recalcula desde el CSV, con código propio, toda cifra del resumen y de la entrada de la bitácora, y termina en N/N.

**Los archivos nuevos van en LF**, como los del Exp O; las copias son byte a byte.

**La entrada de la bitácora** va después de un respaldo `BITACORA_TECNICA_respaldo_AAAAMMDD_preExpQ.md`.

---

## 7. Cuándo se corre

**Tiempo de máquina.** Con los tiempos del Exp O (~0.5 s de pared por episodio con 11 procesos):
- el control bit a bit son 1000 episodios, unos 9 min;
- el experimento son hasta 900 episodios, unos 8 min, más 3 si entra la ablación de la decisión 9;
- la pasabilidad extendida, 1–2 min.

**Sólo con la PC libre:** sin sesión de laboratorio y nunca en paralelo con la réplica de la campaña. Propongo correr antes el chequeo previo de la PC del protocolo y pegar su salida en la bitácora. No lo exige nada, pero deja asentada la carga de la máquina, y cuesta un minuto.

---

## 8. Lo que tiene que decidir José

Cada punto va con mi recomendación primero.

1. **La letra:** Q, por lo dicho al principio.
2. **El radio del obstáculo de S1:**
   - **0.30, el del Exp O** (recomendado). El nivel conserva su obstáculo, y lo que cambia contra el S1 del Exp O es la posición y el movimiento.
   - O 0.15, el del 4: la geometría de la campaña, cuyo hueco a la pared es 0.75. La comparación con la campaña igual no es directa (sin retardo, k = 1, F1 y no F2).
3. **Los objetivos:**
   - **transparentes** (recomendado, §3.4);
   - o rebote en el disco móvil, con control fantasma por nivel: +1 condición por nivel y ~2 h de código y pruebas.
4. **Las trayectorias de S2 y S3:**
   - **las del §3.1** (recomendado);
   - o S2 rígido: ρ = r = 0.25 con una sola fase para los dos, sin celdas inaccesibles y con 0.50 de hueco a la pared, pero dos obstáculos que se mueven en bloque.
5. **S3:**
   - **correrlo si S2 pasa**, con los 6 cm de amplitud que permite la pasabilidad, rotulado así (recomendado);
   - o no correrlo y declararlo fuera por pasabilidad.
6. **La saturación de la fila F1:**
   - **sólo con s > 0** (recomendado): con v = 0 la fila es la del Exp O por construcción;
   - o tal cual la campaña, también con s = 0: con los datos del Exp O no se dispara, pero la igualdad sería empírica (§4.1).
7. **Sobre qué decide la regla de parada:**
   - **sobre `Sk_din`** (recomendado); las fallas de `Sk_quieto` se reportan;
   - o que cualquiera de las dos condiciones con obstáculos detenga.
8. **El alcance del control bit a bit:**
   - **las 1000 corridas del Exp O, con el fantasma** (recomendado; 2.5 min más);
   - o lo mínimo del pedido: S1–S3 con sus controles (600 corridas) más S0.
9. **Opcional y descriptivo: `Sk_din_sinvel`**, el obstáculo móvil con la fila del Exp O en su posición actual y sin el término de velocidad.
   - Mide cuánto aporta el término cuando no hay retardo: la pregunta que va a hacer cualquier lector sobre "extendido con un término de velocidad".
   - No entra en la regla de parada; sus contactos, si los hay, son el resultado.
   - Recomiendo **sí**: cuesta ~1 min de máquina por nivel y media hora de análisis.

---

## 9. Estimación de horas

| Tarea | Horas de trabajo |
|---|---|
| Entorno con obstáculos móviles, trayectorias, fila F1, gestor de escape actualizable y bucle del episodio | 4 |
| Pasabilidad extendida y máscara permanente | 1 |
| Pruebas unitarias, control negativo y `comparar_ast_Q.py` | 2.5 |
| Control bit a bit: corrida (~9 min de máquina) y revisión | 0.5 |
| Corrida S1 → S3 (~8–11 min de máquina) | 0.5 |
| Análisis: resumen y figuras | 2 |
| `verificar_cifras_Q.py` | 1.5 |
| Revisión adversarial con lectores independientes, de sólo lectura, y correcciones | 1.5 |
| Entrada en la bitácora, con respaldo | 1 |
| **Total** | **≈ 14.5 h (unas dos jornadas)** |

**Además:**
- menos de 30 min de máquina, con la PC libre;
- de José, ~30 min para decidir esto y ~1 h para revisar el resultado;
- si se elige el rebote con fantasma (decisión 3), +2 h y 300 episodios;
- si el control bit a bit no reproduce, el resto queda en espera hasta entender por qué.

---

## 10. Qué se va a poder afirmar y qué no

**Se podrá afirmar**, si los niveles pasan: "la capa de ejecución, extendida con el término de velocidad de la campaña, absorbe en simulación hasta k obstáculos que se mueven a 0.05 m/s y que la política no percibe, sin contacto, sin fallo del solver y sin fallo de la recuperación". También el costo del movimiento, aislado contra los mismos obstáculos quietos.

**No se podrá afirmar:**
- **adaptabilidad de la política;**
- **nada sobre el laboratorio.** Python sin retardo y con k = 1 es el caso más favorable para F1, que en la Fase 0 falló justamente por el retardo; la campaña corre F2;
- **nada sobre otras velocidades,** ni sobre trayectorias que no sean círculos;
- **en S3, nada sobre recorridos amplios:** la amplitud es de 6 cm;
- **comparaciones directas de Δ con el Exp O.** Cambian la posición de los obstáculos y la regla de los objetivos; para eso está la comparación 3, declarada como puente.

Si un nivel falla, la lectura es la del patrón del proyecto (*seguridad intacta, vitalidad degradada*) o, si el fallo es del solver, el límite de F1 sin rescate. Se reporta como el límite de la arquitectura, sin tocar ningún parámetro.
