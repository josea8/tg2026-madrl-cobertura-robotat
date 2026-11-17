# Colocación autónoma en la demo del obstáculo (L0, L1, L2): propuesta

**Estado:** OK de José el 2026-10-07, con las dos recomendaciones del §9. La **Fase B está APLICADA**: los agentes se colocan solos alrededor del 4 quieto (`colocacion_con_obstaculo.py`; ver `REPORTE_2026-10-07_colocacion_automatica.md`). La **Fase A**, que mueve solo al 4, **NO está aplicada**: queda a decisión de José.
- La pidió José el 2026-10-07.
- La decisión sobre la L1 ya está tomada: opción (b). El 4 va **encendido**, se coloca solo en el centro y durante las tomas queda conectado y frenado.
- Una revisión adversarial del borrador (3 revisores de sólo lectura) encontró 2 problemas críticos y varios importantes. Esta versión los incorpora; el detalle está en `resultados_demo_obstaculo/revision_adversarial_20261003/revision_plan_colocacion_20261007.json`.

**Qué no se toca:**
- `colocacion_autonoma.py` y `sesion_robotat.py` quedan intactos: el código nuevo los usa por importación.
- En la demo no cambian la barrera, el predictor, el rescate, el escape, `correr_toma`, `validez_demo` ni las reglas de parada.
- Hay **un** cambio del supervisor, sólo en la L1, que exige la opción (b): §5.

---

## 1. Cómo funciona hoy en `sesion_robotat`

1. Un Enter por episodio ("despejá la arena").
2. `colocar_enjambre` lleva a los 5 agentes a su blanco y a su rumbo:
   - la ley es girar, avanzar y orientarse, a ≤ 0.08 m/s;
   - cada orden pasa por el filtro CBF de paredes, con h recortado a ≥ 0, y por las barreras robot–robot 50/50;
   - se abandona a un robot sin pose, con el marcador congelado o sin progreso en 12 s;
   - al final, (0,0) a todos y 0.6 s de asentamiento.
3. El chequeo de arranque, con reintentos que no gastan el intento, y el operador puede corregir a mano.

La demo no puede usarla tal cual porque `colocar_enjambre` no ve al obstáculo.

## 2. Idea central: nunca se mueven a la vez el obstáculo y los agentes

La revisión mostró que mover a todos a la vez, con barreras de "responsabilidad completa" en los dos sentidos, es **menos** conservador que el 50/50.
- Con retardo, el par se cierra al doble de velocidad.
- En el peor caso, con τ = 0.85 s, la barrera queda violada en ~12 cm.

Por eso la colocación va **en dos fases**:

**Fase A, el obstáculo solo.** Los agentes están quietos y frenados desde hace más de 1 s.
- El 4 va a su punto y a la tangente.
- Sus barreras contra los agentes son de responsabilidad completa, que es válida porque ellos están quietos.
- D_o = 0.33 desde el punto de mira del 4 al centro de cada agente: la misma fila del Exp O y de la toma.

**Fase B, los agentes.** El 4 está quieto y frenado.
- Los 5 van a sus blancos.
- Contra el obstáculo, cada agente usa la fila del Exp O con v = 0: h = ‖p_i − p_o‖ − 0.33, de responsabilidad completa. Es la misma que ya tiene prueba bit a bit.
- Entre agentes, el 50/50 de siempre.

**En la L2, el obstáculo casi no se mueve en la Fase A.** Al terminar cada toma, el 4 queda sobre su círculo, porque lo recorre durante la toma.
- El punto de arranque de la toma siguiente es **la proyección de su pose actual sobre el círculo**. A lo sumo hace un giro en el lugar si quedó a más de 30° de la tangente.
- La Fase A completa, cruzando la arena, sólo ocurre en la **primera toma**, porque viene del centro después de la L1, o si quedó fuera del círculo.
- Variedad: en 500 decisiones el 4 avanza ~2.5 m, unos 239°, así que las fases de arranque se reparten solas.
- **Decisión 1 para José** (§9): con esto el punto de arranque del 4 ya no sale de la semilla.

## 3. Lo que vigila la colocación, además de lo de `colocar_enjambre`

**El obstáculo mientras se mueve en la Fase A.** Esto corrige los dos críticos.
- **Enlace:** en cada ciclo se mira lo que devuelve el envío y `obstaculo_caido`. Ante una falla:
  - (0,0) a todos;
  - `detener_obstaculo()`, que reabre el enlace y frena, con reintentos;
  - el cartel "LEVANTARLO / CORTAR ALIMENTACIÓN";
  - la **regla de parada** "ABORTO POR EL OBSTÁCULO", que exige la "s".
  - No es un reintento silencioso: una reconexión durante la colocación también dispara la regla.
- **Obediencia:** si se le ordenó (0,0) hace más de 1.2 s (τ 0.85 + la ventana de v̂ de 0.3) y su velocidad medida es > 0.02 m/s en 5 ciclos seguidos, es "NO FRENA" y se detiene todo. Si tiene orden de marcha y no se mueve, es "NO SE MUEVE".
- **Frescura de la pose:** se mide con `antiguedad_obstaculo_s()`, porque `pose_obstaculo()` devuelve la última pose válida para siempre.
  - Con más de 0.15 s de antigüedad, (0,0) al 4 en el acto.
  - Con el marcador repetido en hardware, o la pose vencida mientras se movía, se detiene a **todos** de inmediato, como hace el supervisor.
- **Rumbo coherente:** mientras avanza con |ω| < 0.3 rad/s y ≥ 3 cm recorridos, si la dirección del desplazamiento difiere del rumbo medido en más de 20°, se detiene todo con "offset de rumbo sospechoso". Esto protege del offset del 4, que es de tabla y nunca se verificó: §7.
- **Al final:** siempre `detener_obstaculo()`, que deja (0,0) también en el historial del predictor, y no sólo un envío directo.

**Los bloqueos.** Esto corrige el otro crítico.
- **Puntos de paso:** si el tramo recto al blanco cruza el disco del obstáculo, de radio ≈ 0.45 m, el robot va primero a un punto tangente sobre un círculo de ~0.55 m, por el lado de menor rodeo y lejos de paredes y de agentes listos. Lo mismo hace el 4 en la Fase A frente a un agente quieto.
- **Progreso:** se mide hacia el punto de paso vigente.
- **Reintento después de un "no avanza":** cambia de lado o retrocede 10 cm.
- **Margen de separación:** en modo automático, los blancos de los agentes se sortean a **≥ 0.65 m** del punto medido del obstáculo. Con 0.50 m, sin margen para las tolerancias de llegada, el chequeo fallaba con todos listos y el reintento no lo arreglaba. El chequeo de arranque sigue en 0.50 m.
- **Un "no avanza" del obstáculo no detiene a todos** si su pose está fresca. Queda como barrera fija y esa toma se lo coloca a mano. Detener a todos queda para la pose perdida, el marcador congelado, el enlace caído y el "no frena".

**Contacto durante la colocación.** Se mide la distancia mínima agente–obstáculo y agente–agente. Si baja de 0.15 m, se aplica la regla de parada de contacto, con la "s".

**Antes de arrancar la toma:**
- un asentamiento de ≥ 1.2 s, en lugar de 0.6, porque el obstáculo puede tener 0.85 s de retardo;
- quietud medida de todos: v̂ < 0.01 m/s;
- los chequeos de hoy, más dos nuevos:
  - el "marcador congelado durante la colocación", que no gasta el intento, como en la sesión;
  - la **envolvente de la Fase 0**: cada agente a ≤ 0.12 m de su blanco, y el obstáculo con |error radial| ≤ 0.06 m y a ≤ 25° de la tangente.

## 4. El flujo por etapa

**Cada toma de la L1 y la L2:**
1. Un Enter, con latido. El aviso nombra el **robot, el marcador y la IP del obstáculo** y pide una persona junto a la arena.
2. La Fase A y la Fase B.
3. Los chequeos.
4. Si fallan, reintento: Enter, corrección a mano si hace falta y colocación otra vez, hasta 5. Si no se logra, se pierde el intento, como hoy.

**La primera vez que se mueve el 4 en la sesión,** un pulso corto de giro comprueba que gira el marcador 4. Es la lógica de la etapa 1 de `sesion_robotat`, y descarta que robot y marcador no correspondan.

**L0, el 4 solo.**
- Antes de moverlo, la sesión lee los marcadores del enjambre (1, 5, 8, 6, 9) y del 7. **Si alguno está dentro de la arena, no mueve nada.**
- El 4 va solo a (1.5, 0.9) mirando +x. Empieza por un tramo corto de prueba y estima el offset de rumbo con los tramos rectos. Si el error supera 15°, aborta antes de cruzar la arena, y la estimación queda en el `L0_resumen.csv`.
- Después, los 10 arranques de siempre, con 2 s de quietud comprobada antes del primero.

**L1, opción (b).**
- El 4 se conecta, **va solo al centro** (1.5, 1.5) en su Fase A, se frena y queda conectado.
- Los agentes van solos, esquivándolo con la fila del Exp O.

**L2.** Como en el §2.

**Modo manual.** Sigue existiendo con `--colocacion manual`. Las funciones quedan en "manual" por defecto, igual que en `sesion_robotat`, así las pruebas existentes no cambian. "auto" es el valor por defecto sólo en la línea de comandos.

## 5. Cambio del supervisor en la L1

En la L1 el 4 ahora está encendido. Hoy en modo "quieto" nadie mira si se mueve, porque se suponía apagado.
- Se agrega el chequeo "NO FRENA" con la obediencia de siempre: se le ordenó (0,0) y se mueve.
- Se agrega el chequeo del enlace, y la quietud del 4 antes de arrancar.
- Abortar por eso dispara la regla de parada.
- No cambia la barrera ni la validez de las tomas que corren bien.

## 6. Robot del obstáculo obligatorio

`--robot-obstaculo` pasa a ser **obligatorio**, sin valor por defecto. Así, si alguien se olvida, la colocación no puede mover el robot 7 del compañero. Las funciones y las pruebas no cambian.

## 7. Offset de rumbo del 4

Es el de la tabla del laboratorio, +81.90°, y nunca se verificó.

**Propuesta:** la L0 lo **mide** con la estimación del §4, y lo protegen el monitor de coherencia del §3 y el pulso inicial.
- Si da > 3° de diferencia, propongo corregirlo. Eso sí toca `config_robotat.py`, un archivo existente, y queda para tu OK.
- **Alternativa:** correr antes las etapas 1 y 3 de `sesion_robotat` con el 4, como con el 8 y el 5 el 22-09. Ojo: escribe la calibración guardada, que es un archivo existente.

## 8. Validación y criterio, fijados antes

**Criterio de la colocación en el simulador** (`MonitorVerdad`, τ = 0.45 y 0.85 s, N semillas):
- distancia mínima continua agente–obstáculo y agente–agente **> 0.15 m durante toda la colocación**;
- ningún robot fuera de [0, 3]²;
- 0 fallas que el reintento no resuelva.

**Fallas inyectadas**, por subclase del simulador en un archivo nuevo. Se espera:

| falla | qué se espera |
|---|---|
| enlace del 4 que cae a mitad de la colocación | detención y regla de parada |
| marcador 4 perdido o congelado | detención inmediata |
| offset de rumbo falso sólo en el 4 | "offset sospechoso" |
| zona muerta de rueda (\|v\| < 0.03 y \|ω\| < 0.35 no mueven) | se rompen los bloqueos |
| obstáculo con τ = 0.85 y agentes con 0.45 | criterio cumplido |
| blanco justo detrás del obstáculo | se rompen los bloqueos |

**Pruebas nuevas:** una por cada guarda del §3, más las que señaló la revisión. Una de ellas: con el obstáculo invisible al empezar, ninguna orden distinta de cero a nadie. Las pruebas existentes no se tocan.

**Ensayos en el simulador sin teletransporte,** con los robots colocándose solos: L0, L1 y L2 con 10 tomas, con τ = 0.45 y 0.85.

**Registro en el CSV de tomas,** también para las que no arrancan:
- modo de colocación, blancos y rumbos;
- el informe por agente y del obstáculo;
- la distancia mínima durante la colocación;
- los reintentos y las poses medidas de arranque.

**¿Hay que repetir la confirmación de la Fase 0?** Propongo que **no**:
- las tomas arrancan dentro de la envolvente de la Fase 0, porque ahora se exige;
- los rumbos de los agentes salen de `sortear_rumbos`, que es exactamente lo que usó la Fase 0;
- la separación de 0.65 m es más holgada que la de 0.50 m;
- la colocación tiene su propio criterio, el de arriba.

## 9. Decisiones para José

1. **Punto de arranque del 4 en la L2:**
   - **(recomendado)** la proyección de su pose actual sobre el círculo: casi no se mueve entre tomas, es más rápido y más seguro, y el arranque ya no sale de la semilla;
   - o la fase sorteada por semilla en cada toma: cruza la arena en cada colocación.
2. **Offset del 4:**
   - **(recomendado)** se mide en la L0 y se corrige después con tu OK;
   - o se calibra antes con las etapas 1 y 3.
3. **OK al plan.** Archivo nuevo `colocacion_con_obstaculo.py`, cambios en `demo_obstaculo_movil.py` con respaldo fechado, pruebas, ensayos y reporte con sus cifras verificadas.
