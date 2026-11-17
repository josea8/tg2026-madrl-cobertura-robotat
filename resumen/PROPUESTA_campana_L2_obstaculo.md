# Campaña de medición L2 con el obstáculo móvil: propuesta

**Estado:** APROBADA por José el 2026-10-08, con ocho decisiones y ajustes; después, el criterio de seguridad (09-10) y tres respuestas (10-10). Rigen `PLAN_ANALISIS_campana_L2.md` y `PROTOCOLO_L0_L2.md`; el cuerpo de abajo queda como registro de la propuesta.

**El cambio de objetivo:** la L2 deja de ser sólo una demo. Pasa a ser una campaña de medición como la evaluación del 30-09:
- tomas medidas en el Robotat;
- réplica pareada en simulación;
- análisis fijado antes.

El video sale de las mismas tomas. La Fase A sigue fuera.

**Base:** una lectura de sólo lectura con 4 lectores (registro, réplica, análisis del 30-09, modo campaña), con chequeos sobre los CSV reales. Detalle en `resultados_demo_obstaculo/revision_adversarial_20261003/entender_campana_20261008.json`.

**Qué no se toca:**
- `sesion_robotat.py`, `replica_con_capas.py`, `colocacion_autonoma.py`, `coordinador_enjambre.py`, `adaptadores_robotat.py`, `simulador_robotat.py` y `lib/filtro_cbf.py`;
- en la demo: la barrera, `correr_toma`, `validez_demo` y las reglas de parada. Se verifica con el AST, como en la Fase B.

---

## 1a. Registro: qué ya se puede reconstruir y qué falta

**Lo demostrado con los CSV de los ensayos del 07-10** (36 tomas corridas):

| lo que la réplica necesita | dónde está hoy | estado |
|---|---|---|
| pose inicial medida de cada agente | fila `paso = 0` del CSV de decisiones: es la pose antes de la primera orden. En el 30-09, paso 0 contra `x0`: mediana 0.01 mm, máximo 0.58 mm y 0.47° | está, pero implícita |
| robot de cada agente | columna `robot` de decisiones | está, pero implícita |
| **offset de rumbo de cada agente y su origen** | en ningún CSV (depende de la tabla y de la calibración guardada del día) | **falta** |
| rampa de la toma | suma de `decisiones` de las tomas anteriores del mismo CSV, como hace `replica_con_capas`. Confirmado: el 4 queda "en espera" exactamente en los pasos 0–49 de la toma 1 y en ninguna otra | se reconstruye |
| trayectoria del 4 decisión por decisión | `*_obstaculo.csv`, con x, y, th, `v_cmd` y `w_cmd`, 1:1 con las decisiones (500 filas por toma). La pose es la MISMA que usó la barrera: recalculada coincide a 4·10⁻¹⁶ | está |
| pose inicial medida del 4 | fila `paso = 0` de la traza. **Ojo:** `obst_x0/obst_y0` de las tomas es el OBJETIVO, no la medida | implícita |
| **robot, marcador, offset y origen del 4** | sólo por consola | **falta** |
| **`rpm_aborto`, `tau_prediccion_s`** | en ningún lado | **falta** |

**Columnas nuevas,** sólo en las tomas que corrieron. Por agente van con los mismos nombres y el mismo formato que el 30-09:
- por agente: `robot_a{i}`, `offset_deg_a{i}`, `offset_origen_a{i}`, `x0_a{i}`, `y0_a{i}`, `th0_a{i}`;
- del 4: `obst_robot`, `obst_marcador`, `obst_offset_deg`, `obst_offset_origen`, `obst_x0_med`, `obst_y0_med`, `obst_th0_med`;
- régimen: `rpm_aborto`, `tau_prediccion_s` y `decisiones_previas` (el contador del canal antes de la toma, es decir, la rampa);
- un `id_sesion` común a los tres CSV.

**Cómo se hace:**
- El bloque del 30-09 que escribe esas columnas está en línea dentro de `sesion_evaluacion` (`sesion_robotat.py:2204-2222`, CRLF) y no es una función. **No se edita.** Se reproduce en un helper de la demo con las mismas llamadas y el mismo redondeo, y una prueba extrae ese bloque con `ast` y verifica la igualdad bit a bit.
- Se captura después de la colocación y antes de `correr_toma`, con la misma pose que validaron los chequeos.
- **Cierre:**
  - las columnas aparecen;
  - `x0` contra paso 0 ≤ 1 mm;
  - `obst_*_med` igual a la traza;
  - `decisiones_previas` igual a la suma acumulada.
  - Con el AST: sólo cambian `sesion_demo`, `_colocar_toma_automatica` y el helper.

## 1b. Modo campaña

**Inclusión.** La decide una función pura, `inclusion_campana`:
- toma **válida para la medición** Y el 4 recorrió ≥ ½ de lo comandado;
- **frenos y contactos NO excluyen:** son resultados;
- `valido_demo` se sigue calculando sólo para elegir el video;
- los intentos no incluidos van en una tabla por motivo.

**Cuenta y parada:**
- La sesión corta al llegar a **50 incluidas** o al tope de intentos, que es una decisión del §8.
- El veredicto es META (≥ 50), MÍNIMO (≥ 30) o INCOMPLETA.
- **La consola no muestra la cobertura**, para que el operador quede ciego al resultado principal. Muestra "INCLUIDA n/50" y, aparte, si la toma sirve para el video.

**Las reglas de parada de seguridad siguen pausando** (contacto, freno en dos tomas seguidas, aborto del 4). Así se concilian con "la parada no depende de los resultados":
- la pausa **no excluye** tomas;
- **no cierra** la campaña;
- cerrarla es un comando aparte, con un motivo escrito y un criterio de seguridad fijado ahora;
- cada respuesta queda en el CSV.

## 1c. Semillas únicas en toda la campaña

**Libro de campaña** en `resultados_demo_obstaculo/campanas/<nombre>/`: un `libro.csv` de sólo agregar y un `campana.json` de cabecera. La cabecera guarda la meta, el mínimo, el tope, la plataforma, el robot del 4 y el sha256 del plan y del código.

**La semilla** del intento k es **421000 + k − 1**, un bloque nunca usado. Ya se usaron:
- 420000–420059 en el 30-09, los ensayos y el Monte Carlo;
- 420100–420109 en la confirmación de la Fase 0.

**Cómo se lleva el libro:**
- antes de colocar se **reserva** la semilla, porque ya fija los blancos y los rumbos;
- al terminar se agrega el resultado;
- una reserva sin resultado, por un Ctrl+C o una caída, queda gastada e "interrumpida".
- **Al abrir,** el libro calcula solo el siguiente intento y las incluidas. Se niega a seguir si:
  - hay semillas repetidas;
  - cambió el sha256 del plan o del código;
  - hay copias en conflicto de OneDrive;
  - hay otra sesión abierta, o la campaña está cerrada.

**Banderas:** `--campana NOMBRE`, `--meta 50`, `--minimo 30` y `--tope-intentos`. Con `--campana`, el libro decide los intentos (no se usan `--intento-inicial`, `--tomas` ni `--intentos`).

**Dónde va el código:** en un módulo nuevo, `campana_obstaculo.py`. Sin `--campana`, la demo queda como hoy.

## 1d. Plan de análisis fijado antes, con su sha256

`PLAN_ANALISIS_campana_L2.md`, `analizar_campana_l2.py` y un verificador independiente se congelan con su sha256 **antes de la primera toma**. Se hashea el archivo que se va a correr.

**Unidad:** la toma incluida. Con semillas únicas, "por toma" es lo mismo que "por escenario": desaparece el agrupamiento por semilla del 30-09.

**Principal: la brecha de cobertura.**
- d_k = cobertura_hw,k − media de las réplicas válidas de la toma k (con el 4 reproducido y τ = 0).
- Estimador: la media de d_k, con IC95 t de n − 1 gl.
- Referencias que no deciden: Wilcoxon y bootstrap.
- **Precisión esperada,** con la dispersión por pares del 30-09 (0.0432): semiancho ±0.012 con n = 50 y ±0.016 con n = 30.
- **Cómo se redacta la conclusión** queda fijado ahora: si el IC contiene el 0, se dice "no hay brecha detectable" y se da la cota. Equivalencia, sólo con un δ que José fije antes.
- **Sensibilidades que no deciden:**
  - sin arranques fuera del soporte;
  - sin tomas con retroceso;
  - **sin tomas con freno**;
  - sin tomas con rampa;
  - réplica con τ = 0.45 s.

**Seguridad:**
- distancia mínima agente–obstáculo por toma, en hw (10 Hz) y en la réplica, con la misma definición (`d_min_obst_medida`);
- tomas con < 0.15 m y frenos de respaldo: proporciones con IC, sin inferencia de diferencias (se esperan pocos o ningún evento);
- pared y pares, como el 30-09;
- mediana y Wilcoxon, porque un mínimo es asimétrico;
- **sobre TODAS las tomas corridas**, no sólo las incluidas.

**Costo del obstáculo:** réplica con obstáculo − réplica sin obstáculo, desde las mismas poses, pareada por toma, con IC95 t.

**Comparación con el 30-09:** sólo descriptiva, porque son escenarios distintos.

**Tamaño:** meta 50 incluidas, mínimo 30. Ningún criterio de parada mira la cobertura ni la brecha, y la réplica no se corre hasta cerrar el laboratorio.

**El contrato de columnas del CSV de la réplica se fija en el plan,** así el script de análisis se congela aunque la réplica se escriba después del laboratorio.

**El script se valida antes con datos sintéticos:** los ensayos del 07-10 como hw falso, más réplicas falsas.

## 1e. Ensayo corto de la L2 en el simulador

En modo campaña, con unas 5 incluidas:
- un corte y una reanudación, para comprobar que las semillas siguen y no se repiten;
- la auditoría de las columnas del registro contra decisiones y traza;
- una corrida del script de análisis sobre esa salida, con réplica falsa.

## 2. Réplica con obstáculo, en un archivo nuevo: `replica_con_obstaculo.py`

**La misma pila del laboratorio:**
- `CoordinadorConObstaculo` con F2 y su predictor;
- `correr_toma` con el lazo de evaluación;
- `SimuladorRobotat` con **retardo cero** y offsets en 0, como `replica_con_capas`.

**El 4 se reproduce, no se simula.** Son dos subclases en el archivo nuevo:
- **`SimuladorReplay`:** el robot 4 no se mueve por física. En cada decisión se lo pone en su pose medida.
- **`SupervisorReplay`:** en cada decisión manda el (v_cmd, w_cmd) **grabado**, así el historial del predictor y el v_cmd de la barrera son los que vio el hardware. El freno se calcula en **sombra**, con los agentes de la réplica, y se informa.

**Variantes y repeticiones:**
- 3 repeticiones por toma con el obstáculo;
- 3 repeticiones de la variante **sin obstáculo**, desde las mismas poses, con el 4 estacionado fuera de la arena y sin fila de obstáculo;
- τ es un parámetro (`retardo_actuacion_s`): la sensibilidad con τ = 0.45 s es una corrida más;
- escritura incremental con `--reanudar`, y CSV de decisiones para la seguridad.

**Cierres:**
- **(a) Sin obstáculo contra `replica_con_capas`** en episodios del 30-09. Bit a bit no es posible, porque las dos corren en tiempo real. Propongo:
  - **(a1)** el mismo camino de código y las mismas acciones ante las mismas observaciones, en una prueba unitaria;
  - **(a3)** la distribución de la cobertura de las repeticiones, equivalente dentro del ruido de réplica del 30-09.
  - Un cierre en lazo cerrado sin tiempo real (a2) agregaría 3–5 h.
- **(b) Con obstáculo:** la trayectoria reproducida del 4 coincide con la medida dentro de 1 mm, sin desfase de una decisión.

**Dos cosas a tener en cuenta al interpretar:**
1. **Los frenos del hw quedan grabados** en la trayectoria del 4. En la réplica, el 4 frena igual aunque no haya nadie cerca. Por eso la sensibilidad "sin tomas con freno" está fijada antes, y se informan los frenos en sombra.
2. **Con retardo cero, el predictor F2 (τ_c = 0.65 s) integra órdenes "en vuelo"** que la planta ideal ya ejecutó. Parte de la brecha y del costo refleja ese desajuste y no sólo la planta. Se dice al interpretar, y la sensibilidad con τ = 0.45 s lo acota.

**Tiempo de máquina:** ~4.3 h para 50 tomas × 3 repeticiones × 2 variantes, más ~2 h para τ = 0.45 sólo con obstáculo. **Nunca en paralelo con una sesión de hardware.**

## 3. Después del laboratorio

La réplica (desatendida), el análisis fijado y el reporte con el zip y `verificar_cifras`.

---

## 8. Decisiones para José

1. **Inclusión, caso borde:** "recorrió ≥ ½ de lo comandado" ¿sólo si lo comandado es ≥ 0.20 m, como en `validez_demo` (recomendado), o literal? Literal, una toma con el 4 frenado casi todo el tiempo entra igual, porque 0 ≥ 0.
2. **Tope de intentos y fin del turno:** propongo 100 intentos (2 × meta, como el 30-09) y una hora de fin fijada antes de cada sesión.
3. **La cadena "freno en dos tomas seguidas" entre sesiones:** ¿se arrastra con el libro (recomendado) o arranca de cero en cada sesión, como hoy?
4. **Cerrar la campaña por seguridad:** propongo que un "no" en la pausa termine sólo la sesión, y que cerrar la campaña sea un comando aparte con motivo escrito.
5. **Equivalencia:** ¿se fija un δ para TOST, o se renuncia a afirmar equivalencia y se informa la cota (recomendado)?
6. **Réplica:**
   - 3 repeticiones también sin obstáculo (recomendado);
   - las inválidas, con una pasada suplementaria declarada, regla del 30-09;
   - τ = 0.45 sólo con obstáculo (recomendado);
   - por toma, la media de las repeticiones para la seguridad, informando también el mínimo.
7. **Cierre (a):** a1 + a3 (recomendado) o también a2 (+3–5 h).
8. **Si el cierre (b) falla para una toma:** se excluye de la réplica con el motivo, y se informa.

## 9. Estimación de horas

Son horas activas. Calibré con la Fase B: llevó ~3 h reales contra 5–6 estimadas, y los lectores estimaron sin esa corrección (ver la última columna).

| bloque | estimación | lectores, sin calibrar |
|---|---|---|
| 1a registro | 2–3 h | 4–6 h |
| 1b + 1c campaña y libro de semillas | 4–5 h | 8–10 h |
| 1d plan + script de análisis + verificador independiente | 6–8 h | 14–20 h |
| 1e ensayo corto y auditoría | 1–1.5 h (+15 min de máquina) | 1–1.5 h |
| revisión adversarial de 1a–1e y correcciones | 1.5–2 h | — |
| **subtotal antes del laboratorio** | **15–19 h ≈ 2 jornadas** | |
| 2 réplica con obstáculo + cierres a1 + a3 y b | 9–12 h (+ ~6 h de máquina) | 15–19 h |
| 3 análisis fijado y reporte con zip y verificar | 3–5 h | — |
| **total** | **27–36 h** | |

**Orden propuesto con los ~10 días:**
1. Del 1a al 1e, antes del laboratorio: unas dos jornadas.
2. La campaña en el Robotat.
3. La réplica (código y corrida desatendida), mientras escribís el documento.
4. Análisis y reporte.
