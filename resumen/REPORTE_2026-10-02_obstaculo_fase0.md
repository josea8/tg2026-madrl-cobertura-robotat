# Demo del obstáculo móvil: Fase 0 en el simulador (01 y 02-10)

**Qué es:** la verificación en el simulador de la demo de un 6.º Pololu, el robot 7, como obstáculo móvil no cooperativo.
- La pidió el asesor para el video de la presentación final.
- **No es un resultado citable de la tesis.**
- Lo que muestra es la generalidad de la capa de seguridad, no adaptabilidad: la política no ve al obstáculo.

**Decisiones de José que rigen esta fase:**
- Sólo la demo (Fases 0 y 1).
- El robot 7, con el 4 de reserva.
- El código va en un archivo aparte.
- La L1 se hace con el robot quieto.
- Una toma con intervención del freno de respaldo no vale para el video.
- La L2 sólo corre con la barrera extendida.
- **Criterio para ir al laboratorio:** distancia mínima > 0.15 m en el peor caso, con seis robots y retardo de 0.45 s **y** de 0.85 s.
- El 02-10:
  - el diseño se congela en F2 con el peso condicional, y el veredicto lo da un **conjunto de confirmación** con geometrías y semillas nuevas;
  - el encierro no se mejora: se reporta como límite;
  - OK a los dos arreglos de §7 y a repetir la confirmación.

**Datos crudos:** `REPORTE_2026-10-02_obstaculo_fase0_datos.zip`.
- Contiene las dos corridas de confirmación, la campaña final y la de diseño previa.
- También la exploración, el ensayo de la L2, los scripts, los manifiestos sha256 y `scripts/verificar_cifras_fase0.py`, que recalcula desde los crudos cada cifra de este reporte.

**Cómo se mide la distancia:** **mínima continua entre centros**, agente–obstáculo, con la pose verdadera del simulador leída a 200 Hz, hasta 0.3 s después de ejecutada la orden de freno final. La medida a 10 Hz, la que se verá en el laboratorio, se informa aparte.

---

## 1. Resumen

1. **Veredicto: PASA.** El veredicto sale de la **2.ª corrida** del conjunto de confirmación.
   - **116 de 116** corridas válidas y completas.
   - Todas sobre 0.15 m. El mínimo es **0.1815 m**, en el encierro en trío sin rampa con τ = 0.85 s: es la única bajo la advertencia de 0.185.
2. **La 1.ª corrida de la confirmación no pasó, y se declara por qué.**
   - 1 de sus 116 corridas fue inválida por un **falso positivo de la verificación de obediencia** del obstáculo. Un hipo del lazo de 0.374 s dejó sin estimación su velocidad; la función devolvió 0 como si "no sé" fuera "quieto", y la verificación abortó la toma con el obstáculo andando a 0.05 m/s.
   - En esa misma corrida las 116 ya estaban sobre 0.15 m, con mínimo 0.1836.
   - **Se cambió el juez de validez, no la barrera** (§7.2): la fila del obstáculo recibe exactamente el mismo v̂ que antes.
   - Corrida por corrida, la 2.ª difiere de la 1.ª sólo por la variabilidad del simulador en tiempo real: mediana de |Δ| 0.25 mm, p90 1.4 cm, máximo 5.5 cm.
3. **Hay dos validez distintas, y sólo una decide** (§4).
   - **Validez de la medición** (decide): 116/116 en la confirmación.
   - **Validez de la toma de demo** (excluye las tomas con freno de respaldo): 112/116.
   - **Las intervenciones del freno se concentran en los encierros guionados:** las 10 de las tres corridas (4 en cada confirmación y 2 en el diseño), todas a 0.245–0.250 m. **En las tomas con política no hubo ninguna.** Son 120 tomas (40 de diseño y 40 en cada confirmación), todas a ≥ 0.2696 m.
   - Esas intervenciones fueron **en sombra**: se registró cuándo habría frenado, pero el obstáculo no frenó. La separación la sostuvo el filtro con su rescate, y el freno habría actuado como capa redundante.
4. **La campaña de diseño (se informa) pasa:** 108 de 108, mínimo 0.1879 m.
5. **La barrera de mi propuesta (F1) no sirve con τ = 0.85 s:** 6 de 17 casos guionados bajo 0.15 m, mínimo 0.0868 m. La que va al laboratorio es **F2** (§3), que agrega:
   - un predictor del retardo;
   - un peso de giro condicional;
   - un rescate del QP.
6. **El control negativo detecta:** la barrera actual (F0, "un robot más") cae bajo 0.15 m en 12 de 34 corridas.
7. **Límite conocido: el encierro** (§6). Con τ = 0.85 s en los agentes, el peor caso de cada variante de F2 es un agente atrapado entre el obstáculo y un vecino: de 0.176 a 0.211 m.
   - Con el freno en sombra, la separación la sostuvo el filtro con su rescate; el escape llega tarde.
   - El freno habría saltado en estos encierros (todas sus intervenciones en sombra fueron ahí). En el laboratorio actúa como capa redundante, no como lo que evita el choque.
8. **La regla "sin desplazamiento por 10 s" quedó arreglada** en `sesion_robotat.py`, con respaldo y el CRLF conservado.
   - No había cortado ningún episodio real.
   - No cambia ninguno de los 50 válidos del 30-09.
   - Sin el arreglo, habría cortado 8 corridas guionadas de la demo; con él, ninguna.
9. **Ensayo de la L2 con 10 tomas en el simulador**, por el mismo camino que en el laboratorio (§8): 10 tomas válidas para la demo en 11 intentos, 0 frenos, mínimo 0.2967 m. Repetido con el código final: 10 en 12 intentos, 0 frenos, mínimo 0.3021 m.
10. **Reglas de parada automáticas** (03-10, §7.3).
    - Una toma con contacto, freno en dos tomas seguidas o aborto por el obstáculo detiene la sesión con todo frenado, y sólo sigue con una "s" del operador.
    - No tocan la barrera ni la validez, así que no se repitió la confirmación.
11. **Archivos existentes tocados:** sólo los dos autorizados, `sesion_robotat.py` y la bitácora, ambos con respaldo.
    - Batería existente después del arreglo: 343 de 344. La que falla es la conocida por dependencia de orden, que pasa sola.
    - Pruebas de la fase: 62 de 62 (57 de la demo y 5 de la regla).

---

## 2. Lo que se construyó

Todo es nuevo y está en `controllers/coordinador_enjambre/`. Se apoya en la pila del Robotat por herencia:

| archivo | qué hace |
|---|---|
| `demo_obstaculo_movil.py` | fuente con los 6 marcadores en **una** consulta de lote por decisión; canal con el robot 7 por su **propio socket**; coordinador con la fila del obstáculo en el QP y su normal en el escape; supervisor del obstáculo (círculo, patada, freno, abortos, obediencia); sesiones L0, L1 y L2 |
| `correr_fase0_obstaculo.py` | campaña: cada corrida es un proceso con su simulador de 6 robots y sus puertos; con `--reanudar` |
| `analizar_fase0_obstaculo.py` | aplica el criterio sobre el conjunto esperado |
| `cifras_fase0.py`, `verificar_cifras_fase0.py`, `figura_fase0_obstaculo.py` | cifras, verificación y figuras |
| `analizar_regla_estancamiento.py` | regla de 10 s sobre los episodios reales, de sólo lectura |
| `analizar_sesion_demo.py`, `ensayo_l2_simulador.py` | resumen de una sesión L1/L2 y ensayo de la L2 en el simulador |
| `test_demo_obstaculo_movil.py`, `test_regla_estancamiento.py` | 57 + 5 pruebas |

**Dos cambios a la propuesta del 01-10.**
- El robot 7 **no** va como agente 5: con el índice 5, `_correr_episodio` daba `KeyError` en `MAPEO_AGENTES[5]`.
- La colocación autónoma **no ve al 7**, porque `colocar_enjambre` filtra sólo contra los agentes. Por eso la demo usa colocación manual.

---

## 3. La barrera: de F1 a F2

La fila del obstáculo se evalúa sobre el punto de mira del agente y el centro del obstáculo:

```text
h   = ‖p_i − p_o‖ − 0.33
rhs = −α·h + s/k,   s = max(0, n·v̂_o, n·v_cmd),   k = 0.40
```

- El lado derecho se satura al 90 % de la capacidad de la caja.
- **En F1**, con el obstáculo quieto, es bit a bit la del Exp O, con r = 0.15. Hay prueba que extrae la función del Exp O con `ast`.
- **F2**, la que va al laboratorio, evalúa esa misma geometría en la pose **predicha** del agente y encarece ω cerca del obstáculo. En la L1 es la geometría del Exp O, no su filtro bit a bit.

**Distancia mínima por caso guionado, con rampa.**
- Sólo se muestran los casos que discriminan; el resto está en `analisis_fase0.txt`.
- F2 sin peso es la ablación. Fuente: campaña final.

| caso | τ | F0 (actual) | F1 (propuesta) | F2 sin peso | **F2** |
|---|---|---|---|---|---|
| E2 de espaldas, en reversa | 0.85 | 0.0175 | 0.0868 | 0.2427 | **0.2787** |
| E3 quieto, mirando afuera | 0.85 | 0.1293 | 0.1208 | 0.2785 | **0.2825** |
| E5 encierro: A quieto, B empuja | 0.85 | 0.1220 | 0.1131 | 0.1832 | **0.1986** |
| E5 encierro: A y B hacia el obstáculo | 0.85 | 0.0874 | 0.2200 | 0.2945 | **0.3265** |
| E2 de espaldas, en reversa | 0.45 | 0.0482 | 0.2042 | 0.2381 | **0.2802** |

**Por qué F1 falla con 0.85 s.**
- En el QP, ω cuesta ~3.3 veces menos que v (`W_OMEGA` = 0.3).
- Entonces el filtro paga el término de velocidad **girando**: mueve el punto de mira sobre un círculo de 5 cm, no el centro.
- Con 0.85 s de retardo, ω queda saturado y el rumbo da vueltas completas.

**Las tres piezas de F2:**
1. **Predictor.** La orden que sale ahora rige en t + τ_c, así que la fila se evalúa en el estado de ese instante. Se integran las órdenes "en vuelo" del agente y del obstáculo, que el canal ya registra.
   - Es la idea de Molnar, Kiss, Ames y Orosz (2023), aplicada sólo a esta fila.
   - τ_c = 0.65 s quedó fijado **antes** del barrido, como punto medio de 0.45–0.85.
   - En el barrido exploratorio fue el mejor peor caso con los dos τ: 0.2416 m, contra 0.1995 con τ_c = 0.85 y 0.2319 con τ_c = 0.45.
2. **Peso de giro 3.0** cuando la fila del obstáculo está cerca de ligar (h_eq < 0.15) **y ninguna otra fila lo está** (h < 0.06; en las filas robot–robot, h = 0.5·(dist − d), o sea 0.12 m geométricos).
   - Aplicado siempre, rompía el encierro: 0.1224 m en la campaña de diseño previa.
   - **La condición se eligió después de ver datos: por eso decide la confirmación.**
3. **Rescate.** Si el QP es infactible con la fila del obstáculo, se relaja esa fila antes de caer al fallback (0, 0).
   - Nivel 1: la mitad de la capacidad de la caja.
   - Nivel 2: c·u ≥ 0, "no acercarse".

**Otros cambios por la revisión adversarial** (§10):
- freno de respaldo a 0.25 m;
- ganancia de rumbo del obstáculo 1.0;
- verificación de obediencia del obstáculo;
- el enlace caído lo frena al reabrirse;
- la toma de demo exige además ningún agente a < 0.15 m y que el obstáculo haya recorrido al menos la mitad de lo comandado.

---

## 4. Dos validez

| | qué exige | para qué |
|---|---|---|
| **Validez de la medición** | la corrida termina completa: sus decisiones pedidas, sin aborto del supervisor del obstáculo, sin enlace caído ni agente fuera de la arena. En el laboratorio, además, todas las reglas de `_correr_episodio` | **decide el veredicto**: con la distancia > 0.15 m en todas, es el criterio de la Fase 0 |
| **Validez de la toma de demo** | válida para la medición, Y **sin intervención del freno de respaldo**, Y ningún agente a < 0.15 m del obstáculo, Y (en L2) el obstáculo recorrió al menos la mitad de lo comandado | qué tomas sirven para el video. No decide el veredicto de la Fase 0 |

**Por qué el freno no invalida la medición.** En la campaña el freno va **en sombra**: se registra cuándo habría frenado, pero el obstáculo no frena. Así la distancia medida es la del filtro solo. Una corrida con freno "en sombra" sigue siendo una medición válida, y su distancia cuenta para el criterio. No vale como toma de demo porque, con el freno activo, el obstáculo habría frenado y la toma ya no mostraría al filtro de los agentes solo. **La separación no depende del freno:** en esas corridas la sostuvo el filtro con su rescate, con el freno en sombra. El freno es una capa redundante.

| conjunto | válidas (medición) | válidas (demo) | excluidas por freno: guionadas / tomas con política |
|---|---|---|---|
| 2.ª confirmación (decide) | 116/116 | 112/116 | 4 / **0** |
| 1.ª confirmación | 115/116 | 111/116 | 4 / **0** |
| diseño | 108/108 | 106/108 | 2 / **0** |

**Las 10 intervenciones del freno, todas en sombra, ocurrieron en encierros guionados**, a 0.245–0.250 m: un agente atrapado entre el obstáculo y un vecino. **En las 120 tomas con política no hubo ninguna.**

---

## 5. Resultados

### 5.1 Confirmación (decide)

Son 19 casos guionados, todos distintos de los de diseño:
- encuentro en la fase 2.3 rad (no múltiplo de π/2), arco de 0.45 m y disparo a 0.50 m;
- corrimientos de ±0.06 y ±0.20, y rumbos a 45°, 135°, 225° y 315°;
- encierro con el vecino corrido, encierro en trío y **cruce** del camino;
- otros estacionados.

Además, 10 tomas con semillas nunca usadas (420100–420109). Todo con τ ∈ {0.45, 0.85} s, y con y sin rampa.

**Prueba de humo antes de la 1.ª corrida** (se declara): 4 corridas del conjunto (trío y cruce en P, τ 0.85, con y sin rampa), en `exploracion_fase0/humo_conf/`, sólo para comprobar que el conjunto corría.
- Terminó a las 16:56:34 del 02-10, y la 1.ª corrida arrancó a las 16:56:49: no hubo cambios entre una y otra. Sus specs son idénticas a las oficiales.
- El trío sin rampa ya dio ahí 0.1801 m.
- El conjunto no se usó para diseñar.

**2.ª corrida, la que decide** (`fase0_conf2_20261002_195453`):

| bloque | τ | rampa | n | mínimo (m) | caso | fallbacks QP | freno (sombra) |
|---|---|---|---|---|---|---|---|
| guionados | 0.45 | con | 19 | 0.2800 | C2 espaldas reversa l−0.06 | 0 | 0 |
| guionados | 0.45 | sin | 19 | 0.2035 | C5 encierro B corrido | 8 | 1 |
| guionados | 0.85 | con | 19 | 0.2091 | C5 encierro trío | 0 | 1 |
| guionados | 0.85 | sin | 19 | **0.1815** | C5 encierro trío | 9 | 2 |
| tomas | 0.45 | con | 10 | 0.2745 | toma 02 | 0 | 0 |
| tomas | 0.45 | sin | 10 | 0.3045 | toma 02 | 0 | 0 |
| tomas | 0.85 | con | 10 | 0.2752 | toma 05 | 8 | 0 |
| tomas | 0.85 | sin | 10 | 0.2910 | toma 09 | 0 | 0 |

- **116/116 válidas y completas, todas sobre 0.15 m, 1 bajo 0.185.** La medida a 10 Hz da un mínimo de 0.1818 m.
- Los laterales se encuentran de costado de verdad, a 69–93°, y los cruces entre 90° y 140°.
- La toma que en la 1.ª corrida se había abortado, `toma_05_s420105` con τ = 0.45, ahora corre completa: 500 decisiones y 0.3460 m.
- **Ninguna decisión quedó sin estimación de velocidad** en las 116 corridas. El ritmo del lazo fue ≥ 9.985 decisiones/s.

**1.ª corrida** (`fase0_20261002_165649`, junto con la campaña de diseño):
- **No pasó:** 115/116, con la inválida por el falso positivo descrito en §1. Fue `toma_05_s420105` con τ = 0.45: abortó en la decisión 212, con 0.3455 m hasta ahí.
- En las 116, la distancia quedó > 0.15 m, con mínimo 0.1836.
- El hipo de 0.374 s pasó con 6 simulaciones en paralelo. Durante la corrida se vio además que los servidores MCP de Inventor se lanzaban solos. Eso se observó en la sesión pero no quedó en los datos, así que como causa es una hipótesis.

**Las dos corridas, pareadas.** La barrera es la misma, así que la diferencia es la variabilidad del simulador en tiempo real. En 115 pares: media de Δ (2.ª − 1.ª) −0.0015 m, mediana de |Δ| 0.25 mm, p90 1.4 cm, máximo 5.5 cm. **El peor caso no es un número fijo:** en los encierros y en las tomas con política, una repetición puede correrse unos centímetros.

![Confirmación](primerafase_webots/controllers/coordinador_enjambre/resultados_demo_obstaculo/fase0_conf2_20261002_195453/fig_fase0_confirmacion.png)

*2.ª corrida, los 19 casos guionados (las tomas con política están en la tabla). Cada punto es el mínimo entre la corrida con rampa y la sin rampa.*

### 5.2 Diseño (se informa)

| bloque | τ | rampa | mínimo (m) | caso |
|---|---|---|---|---|
| guionados | 0.45 | con / sin | 0.2776 / 0.2792 | E8 sorpresa de espaldas |
| guionados | 0.85 | con / sin | 0.1986 / **0.1879** | E5 encierro A quieto |
| tomas | 0.45 | con / sin | 0.3043 / 0.3026 | |
| tomas | 0.85 | con / sin | 0.2883 / 0.2933 | |

- **108/108 válidas y completas, todas sobre 0.15 m.**
- ⚠ E6 ("lateral desde la pared") **no se ejerció**: el agente queda a 0.62 m del camino y el disparo es a 0.60. En la confirmación, el lateral C4 sí se ejerce.

![Diseño](primerafase_webots/controllers/coordinador_enjambre/resultados_demo_obstaculo/fase0_20261002_165649/fig_fase0_diseno.png)

### 5.3 Control, sensibilidades y lazo del laboratorio (no deciden)

| bloque | qué cambia | mínimo (m) | bajo 0.15 |
|---|---|---|---|
| control F0 | la barrera actual | 0.0175 (E2, τ 0.85) | **12/34** |
| F1 | la propuesta | 0.0868 (E2, τ 0.85) | 6/34 |
| ablación | F2 sin peso de giro | 0.1832 (E5, τ 0.85) | 0/34 |
| mixto | agentes 0.85 s, obstáculo 0.45 s | **0.1758** (E5 A quieto) | 0/17 |
| mixto | agentes 0.45 s, obstáculo 0.85 s | 0.2718 | 0/17 |
| ruido | 1 mm de ruido de pose, τ 0.85 | 0.2113 | 0/17 |
| lazo del laboratorio | `_correr_episodio` completo, τ 0.45 | 0.3108 | 0/10 |

---

## 6. Límite conocido: el encierro

**Con τ = 0.85 s en los agentes, el peor caso de cada variante de F2 es un encierro**, un agente atrapado entre el obstáculo y un vecino. Va de 0.176 a 0.211 m:
- E5, A quieto y B que empuja: 0.1879 m.
- C5 trío: 0.1815 m. Lo marca el agente **del medio** (B), que persigue a A y queda entre el obstáculo y C. A no baja de 0.246 m.
- Mixto (agentes 0.85 s, obstáculo 0.45 s): 0.1758 m.
- Ruido de 1 mm: 0.2113 m.

Con τ = 0.45 s el peor caso es otro (E8, C2), salvo en la confirmación sin rampa (C5 con el vecino corrido).

**El mecanismo, según los crudos:**
1. El obstáculo exige que el agente se aleje en una dirección, y la barrera con el vecino, que no se mueva en esa dirección. El QP se vuelve **infactible de verdad**.
2. El rescate relaja la fila del obstáculo, y domina el nivel 2, "no acercarse". En el trío sin rampa fueron 59 de 68 rescates (4 de nivel 1), y los 5 restantes fallaron y cayeron al fallback (0, 0).
3. **La separación la recupera el filtro rescatado, no el escape.** Con la nominal quieta, el (0, 0) que deja el rescate cumple la fila relajada sin que el CBF intervenga. El detector de escape exige esa intervención, así que no se arma. En E5 y en el mixto, el primer escape del agente encerrado llega **después** de su mínimo: en la decisión 146, contra el mínimo en la 87, y en la 195, contra la 139.

**Con el freno en sombra, la separación la sostuvo el filtro con su rescate.** El freno habría saltado en estos encierros (todas sus intervenciones en sombra, a 0.245–0.250 m, fueron ahí; §4), como capa redundante: no es lo que evita el choque. Decisión de José: no se mejora.

---

## 7. Los arreglos (02-10 y 03-10, con OK de José)

### 7.1 Regla "sin desplazamiento por 10 s" (`sesion_robotat.py`)

Detalle en `PROPUESTA_regla_estancamiento.md`.
- **El defecto:** medía desde el último desplazamiento de más de 2 mm, no desde la orden. Un agente quieto más de 10 s al que se le ordena huir cortaba la toma en la primera decisión.
- **Episodios reales:** 0 cortes en 95 episodios (65 válidos; 11-09, 26-09 y 30-09). La exposición máxima fue 5.11 s en todos y 3.20 s en los válidos.
- **Arreglo:** `t_ref = max(t_mov, t_inicio_orden + 1.0 s)`, con histéresis de 1.0 s sin orden.
  - Constantes: `MARGEN_RETARDO_ESTANCAMIENTO_S` y `CORTE_ORDEN_ESTANCAMIENTO_S`.
- **Efecto:** 0 de los 50 válidos del 30-09 cambian; por construcción, el arreglo sólo puede quitar cortes. En la campaña, la regla vieja habría cortado 4 + 4 corridas guionadas y la arreglada, 0.
- **Cómo se aplicó:**
  - respaldo `sesion_robotat_respaldo_20261002_preEstancamiento.py`;
  - **CRLF conservado**: 3866 de 3866 líneas.
- **Pruebas** en `test_regla_estancamiento.py`, un archivo nuevo, con 5 pruebas por el `_correr_episodio` real contra el simulador:
  - las constantes del arreglo;
  - el caso de la demo no corta;
  - el robot trabado corta;
  - con un filtro que parpadea, también;
  - una orden cortada 1.5 s reinicia el reloj.
- La batería existente sigue en 343/344.
- **El costo de la histéresis:** un robot trabado con tramos de orden de menos de ~11 s, separados por pausas de ≥ 1 s sin orden, nunca llega al corte de 10 s. En ese caso la protección queda sólo en `DetectorSeguimiento`.
- **Dónde se ejerce:** la 2.ª confirmación corre el lazo de medición, que no pasa por `_correr_episodio`. El arreglo lo ejercen las pruebas nuevas y el ensayo de la L2 (§8).
- **Fuera del arreglo:** una regla análoga en `_correr_escalon` (`sesion_robotat.py:3349-3361`), el barrido de régimen de la sesión de política. No es idéntica: mira también ω y aplica `factor_total`. No la usan la demo ni la evaluación, y queda como estaba (mismo hash de la función).

### 7.2 Obediencia del obstáculo (`demo_obstaculo_movil.py`)

Detalle en `PROPUESTA_obediencia_obstaculo.md`.
- **Qué cambió:**
  - `velocidad_obstaculo()` devuelve `None` sin estimación, en vez de 0;
  - la verificación no juzga sin estimación y exige **5 decisiones seguidas** (`N_CONFIRMACION_OBEDIENCIA`).
- **Qué no cambió: la barrera.** La fila del obstáculo recibe `_velocidad_o_cero(...)`: con estimación, el mismo v̂ de antes; sin ella, 0, que también es lo de antes. La patada se comporta igual.
- **Diferencia con la propuesta:** la propuesta decía que un obstáculo trabado abortaría a los 1.5 s + 0.5 s. La cuenta de 5 decisiones acumula dentro de la ventana de 1.5 s, así que aborta a los 1.5 s, como antes.
- **Qué más cambió entre las dos corridas.** Nada de esto toca la barrera ni la validez de la medición:
  - en `demo_obstaculo_movil.py`, la réplica fuera de línea de la regla de 10 s (`primer_corte_por_estancamiento`) pasó a la regla arreglada. Por eso la columna `corte_estancamiento_paso` cuenta 4 cortes en la 1.ª corrida y 0 en la 2.ª: cambió su definición, no el comportamiento. `validez_demo` no la lee;
  - la traza deja v̂ vacío sin estimación (antes "0.0"), y hay una columna nueva, `obst_decisiones_sin_estimacion_v`;
  - en `correr_fase0_obstaculo.py`, dos líneas: el disparo de las nominales trata el `None` como 0, igual que antes. Deshaciéndolas se reproduce el sha256 de la 1.ª corrida;
  - las 116 specs son idénticas en las dos corridas.
- **Cómo se aplicó:**
  - respaldo `demo_obstaculo_movil_respaldo_20261002_preObediencia.py`;
  - sha256 del código de la 1.ª corrida en `sha256_codigo_congelado_20261002.txt`, y del código tras los arreglos, con el que corrió la 2.ª, en `sha256_codigo_conf2_20261002.txt`.
- **Pruebas nuevas:**
  - un hueco de 0.374 s da `None`;
  - sin estimación no se aborta;
  - hacen falta 5 decisiones seguidas;
  - el trabado y el que no frena se siguen detectando.


### 7.3 Reglas de parada automáticas y otros tres cambios (03-10, OK de José)

**Por qué:** una toma con contacto pasaba sola a la siguiente, y detenerla dependía de que el operador estuviera mirando la consola. La regla de parada es la prioritaria, porque es de seguridad.

**Respaldos:**
- `demo_obstaculo_movil_respaldo_20261003_preParadas.py`, antes de todo. Es el código de la 2.ª confirmación: el mismo sha256;
- `demo_obstaculo_movil_respaldo_20261003_preLatido.py`, la versión con la que corrió el ensayo intermedio;
- sha256 del código final en `sha256_codigo_paradas_20261003.txt`.

**Qué no se tocó: la barrera ni la validez.** Comparando con el AST, sin docstrings, contra el respaldo previo, cambian sólo `sesion_demo`, `sesion_l0` y `main`, más funciones nuevas. `validez_demo`, `correr_toma`, el filtro, el predictor, el rescate, el escape y el supervisor son idénticos. **Por eso no se repitió la confirmación.**

1. **Reglas de parada** (`regla_de_parada`). Se miran después de cada toma corrida, válida o no:
   - contacto, con la distancia medida < 0.15 m;
   - freno de respaldo en dos tomas corridas seguidas;
   - aborto por el obstáculo, o caída de su enlace durante la toma aunque se haya reabierto al frenar;
   - toma corrida sin distancia medida.

   **Si se cumple una:**
   - la sesión frena todo y se detiene;
   - sigue frenando con un latido mientras espera, igual que en la colocación;
   - avisa si no pudo confirmar la detención;
   - sólo sigue con una **"s"** explícita. Cualquier otra respuesta la termina, con veredicto DETENIDA.

   La regla, la respuesta y lo que no se pudo confirmar frenado quedan en el CSV de tomas. La línea de cada toma ahora dice por qué no vale.
2. **`--intento-inicial N`:** reanuda una sesión cortada. Siguen la numeración, las semillas y la cuenta contra el tope. El analizador junta los CSV de las dos sesiones.
3. **Resumen de la L0** en `<fecha>_L0_resumen.csv`, en todos los caminos: normal, sin conexión, aborto radial y Ctrl+C.
4. **Comentarios:** el freno a 0.25 m (decía 0.20) y como capa redundante, y los docstrings de la L0, de la sesión y de `validez_demo`.

**Revisión adversarial de los cambios** (5 revisores de sólo lectura, `revision_adversarial_20261003/paradas/`). Confirmó que no se toca la barrera ni la validez. Además encontró, y se corrigió:
- **la espera sin latido:** no se reintentaba frenar al 7 y el socket de poses podía caerse;
- **el cartel** "con los robots frenados", que se mostraba sin confirmar la detención;
- **la caída del enlace del 7 en la última decisión**, que quedaba tapada por la reapertura al frenar;
- **un hipo del servidor de poses** rotulado como aborto del 7. Ahora se rotula como hipo, y la sesión igual se detiene;
- **"si" y "sí"** aceptados como "s";
- **el resumen de la L0 abortada**, que no guardaba el error del aborto;
- **pruebas que no verificaban lo que decían.**

**Pruebas:** 23 nuevas. Con ellas, la suite de la fase pasa **62 de 62** (57 de la demo y 5 de la regla).
- **Una por regla**, unitarias y con la sesión completa contra el simulador. En la sesión, las tomas son guionadas y el obstáculo queda andando al terminar cada una.
- **Tomas reales:** sin barrera, un agente va derecho al obstáculo. Lo que devuelve `correr_toma` dispara la regla: contacto en la 1.ª toma, y contacto más freno en dos tomas seguidas en la 2.ª.
- **La espera sigue frenando:** el latido corre mientras se espera la respuesta.
- **El cartel avisa** cuando el 7 no se pudo frenar.
- **La colocación fallida en medio** no corta la cadena de frenos.
- **El análisis de la respuesta.**
- **`--intento-inicial`**, en el borde.
- **La L0**, en sus cuatro caminos.
- **El analizador.**
- **Un mutante** sin el `detener_todo` antes de la pregunta hace fallar la prueba del contacto.

**Un error encontrado por las pruebas antes de usarlo:** en `sesion_demo` reusé el nombre `estado` para el rótulo de la toma, y ése es el diccionario del episodio. La sesión se habría caído en la 2.ª toma.
- **Ensayo de la L2 repetido** con el código final: 10/10 tomas válidas para la demo en 12 intentos, ninguna regla disparada sin motivo (§8).

---

## 8. Ensayo de la L2 en el simulador (10 tomas)

`ensayo_l2_simulador.py --tomas 10` corre la sesión L2 completa (`sesion_demo`, lazo de evaluación, freno de respaldo **activo**, colocación manual con la guía) contra el simulador con 6 robots y τ = 0.45 s. El "operador" es un gancho que, antes de cada Enter, pone a los agentes en sus blancos y al 7 en su arranque. **No es un resultado: verifica el procedimiento.**

| | resultado |
|---|---|
| intentos | 11, para 10 tomas válidas (tope 20) |
| validez de la medición | 10/11. La toma 2 se cortó en la decisión 411 por **antigüedad de pose > 150 ms** (`ANTIGUEDAD_MAX_POSE_S`), una regla del lazo. Esa toma registra 1 ciclo > 100 ms, igual que las tomas 3 y 9, que no se cortaron: la causa precisa no quedó registrada. La sesión siguió con otro intento, como está previsto |
| validez de la demo | **10/10** de las válidas |
| intervenciones del freno de respaldo | **0** |
| distancia mínima agente–obstáculo (10 Hz) | mín **0.2967** · mediana 0.3155 · máx 0.3688 m; ninguna bajo 0.185 |
| recorrido del obstáculo | 2.49 m por toma; 2.24 en la 1.ª, la de la rampa |
| duración | 541 s de tomas; con las colocaciones, 556 s según la consola |

Salida: `ensayo_l2_20261002_201318/` (CSV de tomas, decisiones y obstáculo; resumen y figura de `analizar_sesion_demo.py`). El 03-10 se corrigió la mediana del analizador, que tomaba la mediana superior (0.3190), y se regeneró el resumen.

**Repetido el 03-10 con las reglas de parada (§7.3)**, por el mismo camino:

| | intermedio (1.ª versión) | **final** (tras la revisión) |
|---|---|---|
| intentos para 10 tomas válidas | 10 | 12 |
| no válidas para la medición | 0 | 2 (tomas 1 y 4: antigüedad de pose > 150 ms, en las decisiones 472 y 480) |
| reglas de parada disparadas | 0 | 0 |
| intervenciones del freno | 0 | 0 |
| distancia mínima (10 Hz) | mín 0.2996 · mediana 0.3182 · máx 0.4026 m | mín 0.3021 · mediana 0.3163 · máx 0.3645 m |

- Las dos no válidas del final son del lazo: pose vencida, con 5 y 1 ciclos > 100 ms. Como corresponde, no detienen la sesión, porque no son del obstáculo.
- El código de la toma (`correr_toma`) no cambió: es la variabilidad del simulador en tiempo real en la misma máquina. El intermedio tuvo tiempos de ciclo peores (p95 de hasta 53 ms) sin ningún corte.
- **En 22 tomas corridas, ninguna regla se disparó sin motivo.**

Salidas: `ensayo_l2_20261003_093317/` (intermedio) y `ensayo_l2_20261003_100116/` (final).

---

## 9. Lo que el simulador no dice

- **El retardo es puro y no depende de la velocidad.** El 3pi real tarda 849 ms en arrancar a 0.05 m/s y 458 ms a 0.15 m/s.
- **No hay fricción de arranque.** La **L0** valida el arranque del obstáculo; el de los agentes es el medido antes (la línea anterior).
- **No hay contacto físico.**
- **El hardware anduvo 3.5 cm más cerca de la pared que su réplica** (30-09).
  - Restados del peor caso de la confirmación, quedarían ~0.147 m, **bajo el criterio de 0.15**. Es un orden de magnitud para pensar el margen, no una predicción.
  - Por eso el freno de respaldo va activo en la L2, como capa redundante del filtro.
  - Además, el peor caso es un encierro guionado; con política, el mínimo fue 0.2696 m.
- **No reproduce bit a bit:** ±1.4 cm en el p90 entre repeticiones (§5.1).

---

## 10. Revisión adversarial (01-10)

Fueron 4 revisores y 2 verificadores por hallazgo: **19 de 26 hallazgos sobrevivieron, y se atendieron todos.** Algunos con cambios de código; otros cubriéndolos en la campaña o documentándolos: la rampa sólo en la 1.ª toma se cubrió con las variantes sin rampa, y la mezcla de instantes, con el rescate. Los principales:
- el peso de giro y el ciclo bang-bang;
- la mezcla de instantes en F2;
- el enlace caído, que no frenaba al 7;
- que nada verificaba la obediencia del obstáculo;
- la ganancia de rumbo inestable con 0.85 s;
- que `valido_demo` no miraba el contacto;
- el control negativo que no fallaba;
- el analizador que daba PASA con corridas faltantes;
- las nominales que perseguían desde t = 0;
- la rampa presente sólo en la toma 1 del laboratorio;
- el monitor apagado antes del freno final;
- pruebas laxas.

El detalle está en `exploracion_fase0/`.

**Segunda revisión, del reporte y el protocolo (03-10).** Fueron 7 verificadores de sólo lectura, dos de ellos independientes sobre la barrera y otros dos sobre la sesión del laboratorio. Su trabajo fue intentar refutar cada afirmación cualitativa contra el código y los crudos.

**Confirmado:**
- la barrera no cambió;
- la regla de 10 s sólo quita cortes;
- las definiciones de validez son las del código;
- el CLI, la L0 y el cambio al robot 4;
- la cita.

**Corregido en el reporte:**
- el mecanismo del encierro (§6): el escape no es lo que saca al agente;
- "bit a bit" vale sólo para F1 (§3);
- la condición del peso de giro;
- la referencia y la descripción de `_correr_escalon`;
- los otros cambios entre las dos corridas (§7.2);
- la prueba de humo de la confirmación (§5.1);
- la mediana del ensayo;
- el conteo de pruebas.

**Corregido en el protocolo:** las reglas de parada **no** están en el programa y las aplica el operador.

Hallazgos y scripts de los verificadores: `revision_adversarial_20261003/`.

---

## 11. Laboratorio: L0 → L1 → L2

El protocolo, fijado antes de la sesión, está en `PROTOCOLO_L0_L2.md`.

1. **L0**, el 7 solo: `python demo_obstaculo_movil.py --modo L0`. Criterio: 10 de 10 arranques y error radial < 5 cm. El resultado queda en `<fecha>_L0_resumen.csv`. Si falla (el programa sale con código 1), no se sigue: esa decisión la toma el operador.
2. **L1**, el 7 apagado en el centro: `--modo L1 --tomas 3 --intentos 6`. Sin freno, porque el 7 no está conectado.
3. **L2**: `--modo L2 --tomas 10 --intentos 20`.
   - **Toma válida para la demo:** válida, sin intervención del freno de respaldo, sin contacto y con el obstáculo en marcha.
   - **Métrica principal:** distancia mínima agente–obstáculo por toma, medida a 10 Hz.
   - **Reglas de parada** (automáticas desde el 03-10, §7.3): contacto, freno en dos tomas seguidas, o aborto por el obstáculo. La sesión frena todo, se detiene y sólo sigue con una "s" del operador.
   - Una sesión cortada se reanuda con `--intento-inicial`.
   - El resumen sale con `python analizar_sesion_demo.py <…_L2_tomas.csv> [<otro, si se reanudó>]`.

**Sin resolver:**
- la colocación autónoma no ve al 7, por eso es manual;
- el retroceso va sin CBF, y lo mitiga el freno del 7 a 0.60 m, que en la Fase 0 no se ejercitó;
- los offsets de rumbo del 7 y del 4 son los de la tabla.

---

## 12. Datos y verificación

`REPORTE_2026-10-02_obstaculo_fase0_datos.zip` contiene:
- `fase0_conf2_20261002_195453/`: la 2.ª confirmación, la que decide.
- `fase0_20261002_165649/`: la 1.ª confirmación y la campaña de diseño, más el control, las sensibilidades y el lazo del laboratorio.
- `fase0_20261001_134427/`: el diseño previo, con el peso incondicional.
- `exploracion_fase0/` (con la prueba de humo de la confirmación) y los tres `ensayo_l2_*/`.
- `revision_adversarial_20261003/`: la revisión del reporte y, en `paradas/`, la de los cambios del 03-10.
- `regla_estancamiento_*`, los manifiestos sha256 y `scripts/`.

**En disco:**
- Campaña final: 387 corridas, más 5 carpetas de corridas interrumpidas al cortarse el proceso, conservadas y no contadas (se repitieron con `--reanudar`). Ritmo del lazo ≥ 9.781 decisiones/s y muestreo de la verdad ≥ 187.4 Hz.
- 2.ª confirmación: 116 corridas, 0 interrumpidas. Ritmo ≥ 9.985 decisiones/s y verdad ≥ 195.4 Hz.

Para verificar:

```text
python scripts/verificar_cifras_fase0.py fase0_20261002_165649 fase0_conf2_20261002_195453
```

**Referencia:** Molnar, T. G., Kiss, A. K., Ames, A. D., & Orosz, G. (2023). Safety-critical control with input delay in dynamic environment. *IEEE Transactions on Control Systems Technology, 31*(4), 1507–1520. https://doi.org/10.1109/TCST.2022.3227451
