# Plan de análisis de la campaña L2 con el obstáculo móvil

**Estado:** FIJADO ANTES de la primera toma. Su sha256, el de `analizar_campana_l2.py` y el del verificador independiente `verificar_campana_l2.py` quedan en el libro de la campaña al crearla (`campana.json` y la fila de creación del libro, lista `archivos_congelados`). Cambiar cualquiera de los tres después exige una corrección declarada con motivo (`--corregir-campana "motivo"`, mientras la campaña está abierta) o un desvío declarado al analizar (`--desvio "motivo"`, después del cierre). Las dos cosas quedan escritas.

**Base:** la propuesta aprobada (`PROPUESTA_campana_L2_obstaculo.md`) con las ocho decisiones de José del 2026-10-08, su criterio de seguridad del 09-10, sus respuestas del 10-10 (toma sin distancia medida, cierre a3, cierre b, las dos convenciones del §7 y qué hacer con el resultado del a3), la composición con el robot 2 en lugar del 6 y el bloque nuevo de semillas, aprobados por José el 17-10 (el 16-10 el 6 dejó de girar bien y el 3 no respondió en la red), el descarte de la campaña `L2_obstaculo` del 16-10 (Robotat mal calibrado: cerrada con motivo, ninguna de sus tomas entra en el documento) y las correcciones de las revisiones adversariales. Lo que sigue las aplica. Agrega sólo descriptivos que no deciden: el respaldo por semilla (§3, para un caso que el libro impide), el ruido de la réplica entre repeticiones (§3, como el 30-09), los descriptivos del costo (§5) y los descriptivos post hoc que pidió José después del a3 (§7).

**Qué se mide:** el enjambre del 30-09 con el robot 2 en lugar del 6 (robots 1, 5, 8, 2 y 9; factor 0.40; 500 decisiones; colocación autónoma; retroceso), con el robot 4 como obstáculo móvil en el círculo fijo y el filtro F2 con su predictor (τ_c = 0.65 s). Lazo de evaluación (`lazo="evaluacion"`), el del laboratorio.

---

## 0. Datos y convenciones

- **Unidad:** la toma incluida. Las semillas son únicas en toda la campaña (422000 + k − 1: bloque nuevo por decisión de José del 17-10; el 421000… lo usó la campaña descartada), así que "por toma" es lo mismo que "por escenario". Desaparece el agrupamiento por semilla del 30-09.
- **Hardware:** el libro (`resultados_demo_obstaculo/campanas/<nombre>/libro.csv`) decide qué intentos existen y cuáles se incluyen. Los valores salen del CSV de tomas de cada sesión (`archivo_tomas` del libro), fila `intento_campana = k`. Se leen todos los CSV de tomas de las sesiones de la campaña (por `id_sesion`), también los de una sesión que sólo dejó intentos interrumpidos. El script se detiene (código 4) si:
  - el libro y el CSV no coinciden en semilla, inclusión, validez, frenos o distancia mínima, o la inclusión registrada no es la que da `inclusion_campana` sobre la fila;
  - una toma corrida está fuera del régimen de "Qué se mide": factor 0.40, F2, τ_c = 0.65 s, colocación automática, lazo de evaluación, robots 1, 5, 8, 2 y 9 (en ese orden de agentes), y el 4 de obstáculo;
  - hay reservas o resultados escritos DESPUÉS del cierre de la campaña;
  - hay una reserva sin resultado con la campaña abierta. Con la campaña cerrada, vale "interrumpida" (la regla del libro) y se declara.
- **Réplica:** los CSV del §9, en `resultados_demo_obstaculo/replica_campana/<nombre>/`.
- Todo se calcula desde el crudo, con ddof = 1, en el marco env, de centro a centro y a 10 Hz. IC95 t con n − 1 gl.

## 1. Inclusión (la decide el código)

- **Incluida:** toma válida para la medición (`valido = 1`) Y, si al 4 se le comandaron ≥ 0.20 m, recorrió al menos la mitad (decisión 1). Con menos de 0.20 m comandados no se exige recorrido.
- **Los frenos de respaldo y los contactos NO excluyen:** son resultados.
- `valido_demo` sólo elige el video; el análisis no lo usa.
- Los intentos no incluidos van en una tabla por motivo (no válidas, recorrido corto, parada en la colocación, sin correr, interrumpidas). No tienen par.

## 2. Tamaño y parada

- Meta 50 incluidas, mínimo 30, tope 100 intentos (decisión 2). La hora de fin de cada sesión se fija antes de empezarla.
- **Veredicto:** META (≥ 50), MÍNIMO (≥ 30) o INCOMPLETA. Con INCOMPLETA el análisis se corre igual, con este mismo plan, y se rotula.
- Ningún criterio de parada mira la cobertura ni la brecha. La consola de la toma no muestra la cobertura.
- Las PAUSAS de seguridad pausan la sesión y no excluyen tomas; el único cierre automático es el criterio de abajo. Un "no" termina sólo la sesión (decisión 4). Cada pausa y su respuesta se informan en una tabla.
- La cadena "freno en dos tomas seguidas" se arrastra con el libro (decisión 3).
- **Criterio de seguridad para cerrar la campaña** (decisión de José, 2026-10-09), fijado ahora: la campaña se cierra **sola** cuando se acumulan, en toda la campaña, **dos tomas corridas con contacto**: < 0.15 m entre centros medidos con el obstáculo (`d_min_obst_medida`) o entre agentes (`colisiones_015`, pares distintos).
  - Las pausas siguen como están.
  - Los contactos de la colocación no cuentan para este criterio: siguen siendo regla de parada de la sesión.
  - "Toma corrida" es la que corrió, válida o no, aunque se haya cortado a mitad. Es la MISMA definición en el libro, en este criterio y en la seguridad del §4a.
  - Sin distancia medida al obstáculo, la toma no cuenta como contacto CON EL OBSTÁCULO (no hay contacto medido); sus pares de agentes sí cuentan (decisión de José, 2026-10-10).
  - Lo aplica el libro al anotar la segunda: escribe el cierre con el motivo y los intentos, y la sesión no corre ningún intento más. También lo aplica al abrir una sesión y al cerrar, por si un corte quedó entre la segunda toma con contacto y su cierre.
  - El libro anota TODA toma que corrió: la completa; la que dispara una regla de parada, ANTES de preguntar en la pausa (la respuesta va en una fila aparte); y la cortada a mitad (Ctrl+C, caída de enlace), con una fila parcial armada de lo que alcanzó a correr (decisiones, distancia mínima al obstáculo medida hasta ese momento y pares de agentes a < 0.15 m), no válida, que se anota antes de relanzar el corte. Sólo un corte duro a mitad de toma (corte de luz, proceso matado) queda fuera del libro, y sin datos: los CSV de la sesión se escriben al terminar cada intento, así que sus decisiones se pierden. Su reserva queda "interrumpida" y lo que se vio va a la bitácora y al reporte.
  - El análisis igual hace el recuento FÍSICO desde el crudo: suma las tomas que corrieron y el libro marcó interrumpidas, si su crudo llegó a disco (por su fila de tomas o, si no la tienen, por el CSV de decisiones), como un corte entre la escritura del crudo y la anotación en el libro. Esas tomas también entran a la seguridad del §4a.
  - El análisis verifica contra el libro que el cierre vino después de la segunda toma con contacto anotada, sin ninguna reserva ni resultado en el medio (si no, se detiene con código 4). Un cierre manual no puede usar el prefijo del cierre automático. Si el recuento físico llega a dos y hubo intentos (reservas) DESPUÉS de esa toma, lo declara como INCUMPLIMIENTO DEL CRITERIO, con el intento tras el que debió cerrar y los intentos de después. Todo se informa aparte del principal.
- **Cualquier otro cierre anticipado** (robot dañado, falla del laboratorio, sin más turnos) es el comando `--cerrar-campana` con motivo escrito.
- Ninguno de los dos cierres mira la cobertura. Los dos quedan en el libro y en el reporte, y la campaña cerrada se analiza con este mismo plan, con su veredicto (META, MÍNIMO o INCOMPLETA).

## 3. PRINCIPAL: brecha de cobertura

- hw_k = `cobertura_aoi` de la toma k (cobertura FINAL, la misma columna que el 30-09).
- rep_k = media de `cobertura_aoi` de las repeticiones VÁLIDAS de la toma k, con el 4 reproducido y τ = 0 (condición `con_obstaculo`, `tau_s = 0`).
- **d_k = hw_k − rep_k.** Estimador: la media de los d_k. IC95: t con n − 1 gl.
- **Referencias que no deciden:** Wilcoxon de rangos con signo (exacto con n ≤ 25, si no aproximado, como el 30-09) y bootstrap percentil de la media (10 000 remuestreos, semilla 20261008).
- **Respaldo**, por si alguna semilla se repitiera (no debería: el libro se niega): media de las medias por semilla, con IC t sobre las semillas.
- **Conclusión, redactada así** (decisión 5, sin δ):
  - si el IC contiene el 0: "no hay brecha detectable: hw − réplica = m, IC95 [a, b]; con esta precisión, la brecha está acotada, con 95 % de confianza, a |brecha| ≤ max(|a|, |b|)";
  - si no lo contiene: "brecha detectable: hw − réplica = m, IC95 [a, b]".
  - **No se afirma equivalencia.**
- Precisión esperada con la dispersión por pares del 30-09 (0.0432): semiancho ±0.012 con n = 50 y ±0.016 con n = 30. Si la dispersión crece con el obstáculo, el semiancho crece; se informa el observado.
- Diagnóstico: el ruido de la réplica entre repeticiones (desvío por toma; mediana y máximo).

### 3a. Sensibilidades (no deciden)

Cada una repite el principal sobre un subconjunto, o con otra réplica:

- **A. Sin arranques fuera del soporte.** El criterio del 30-09 (`pareo_final_0930.fuera_de_soporte`), sin cambios: algún agente con `col_estado` distinto de `listo`, o a más de 0.12 m de su blanco (`x0` contra `blanco`), o algún par de agentes a menos de 0.31 m al arrancar.
- **B. Sin tomas con retroceso.** `retrocesos_detalle` no vacío (el criterio "pose repetida" del 30-09).
- **C. Sin tomas con freno de respaldo.** `frenos > 0`. Los frenos del hw quedan grabados en la trayectoria del 4, y en la réplica el 4 frena igual aunque no haya nadie cerca.
- **D. Sin tomas con rampa.** `decisiones_previas < 50` (`DECISIONES_ARRANQUE`): la primera toma de cada sesión, con la rampa de arranque seguro y el 4 en espera.
- **E. Réplica con τ = 0.45 s** (`con_obstaculo`, `tau_s = 0.45`) en lugar de τ = 0. Con retardo cero, el predictor F2 integra órdenes "en vuelo" que la planta ideal ya ejecutó; E acota cuánto de la brecha viene de ese desajuste.

## 4. Seguridad

**4a. Contra el obstáculo.**
- Métrica: `d_min_obst_medida` por toma, con la misma definición en hw y réplica (después de decidir, pose del agente contra la pose del 4 en esa decisión).
- **Sobre TODAS las tomas corridas** (la definición del §2), no sólo las incluidas: las del libro (también las cortadas a mitad, con su fila parcial) y, declaradas, las que corrieron pero el libro marcó interrumpidas (por su fila de tomas o, si no la tienen, por sus decisiones).
  - hw: mínimo, mediana y máximo;
  - tomas con `d_min_obst_medida < 0.15 m` (contacto según el protocolo): proporción con IC de Clopper–Pearson;
  - tomas con freno de respaldo: proporción con Clopper–Pearson, más el total de eventos y de decisiones en freno;
  - los contactos en tomas no incluidas se listan aparte.
- **Pareada, en las incluidas con réplica:** hw − réplica, donde la réplica es la MEDIA de las repeticiones válidas y, aparte, el MÍNIMO (decisión 6). IC t, mediana de las diferencias, Wilcoxon y conteo de signos. Un mínimo es asimétrico: la media sola no alcanza.
- En la réplica, tomas bajo 0.15 m (por la media y por el mínimo de las repeticiones) con Clopper–Pearson, y frenos en sombra, sólo descriptivos.
- No hay inferencia sobre diferencias de tasas: se esperan pocos o ningún evento.

**4b. Pared**, como el 30-09 pero fijado antes y pareado por toma: `d_pared_min` hw − réplica con IC t, con la réplica como MEDIA de las repeticiones y, aparte, el MÍNIMO (decisión 6); `viola_018` hw y réplica, descriptivo.

**4c. Pares de agentes:** `colisiones_015` y `colisiones_022` (pares distintos por toma, no eventos), `frac_cbf` y `n_escape`. Medias de hw y réplica, descriptivas.

**Alcance, escrito así:** "durante la toma y sobre poses observadas".

## 5. Costo del obstáculo

- c_k = rep_con_k − rep_sin_k, las dos con τ = 0 y medias de repeticiones válidas, desde la misma pose inicial, con la misma semilla y la misma rampa.
- Estimador: la media de c_k, con IC95 t pareado.
- Descriptivos: lo mismo para `d_pared_min` y `frac_cbf`, y el total hw − rep_sin.
- Se declara que el costo es condicional a los arranques de la campaña (blancos a ≥ 0.65 m del 4 medido, chequeo de arranque a 0.50 m) y a la trayectoria medida del 4, que incluye los frenos del hw.

## 6. Comparación con el 30-09 (sólo descriptiva)

Son escenarios distintos: no hay p ni IC de la diferencia. Se recalculan desde el crudo empaquetado (`REPORTE_2026-09-30_datos/csv`), con las reglas del 30-09:
- cobertura hw de los 50 válidos (0.3452 ± 0.0428 en el reporte);
- brecha hw − réplica con capas, por pares (+0.0077) y por escenario (+0.0123);
- `d_pared_min` hw − réplica (−0.0355).

Se ponen al lado de los mismos números de la campaña.

**Salvedad (decisión de José, 2026-10-10):** el cierre (a3) dio NO PASA (§7). Su IC95 de la media de Δ, [−0.0105, +0.0055], va en el reporte como la cota de cuánto puede diferir la réplica nueva de la del 30-09: es una salvedad de esta comparación descriptiva. El resultado principal (§3) no depende de eso: compara el hw de la campaña con su propia réplica.

**Composición:** la campaña usa el robot 2 en lugar del 6 (cuatro de los cinco robots son los del 30-09). La comparación de este § suma esa diferencia, que nada acota.

## 7. Réplica: repeticiones, inválidas y cierres (decisiones 6–8)

- Tres repeticiones por toma incluida con el obstáculo (τ = 0), tres sin obstáculo (τ = 0) y tres con el obstáculo y τ = 0.45. τ = 0.45 se corre sólo con el obstáculo.
- **Repeticiones inválidas:** la réplica de una toma es la media de sus repeticiones VÁLIDAS (1 a 3). Si una toma queda con 0 válidas en una condición, se corre una pasada suplementaria SÓLO de esa toma y esa condición, y se declara (regla del 30-09; son 3 repeticiones, la 4, la 5 y la 6: convención aprobada por José el 2026-10-10). Una pasada suplementaria de una toma que ya tenía alguna válida no cuenta y se advierte.
- **Completitud y una sola pila:** la réplica tiene que estar COMPLETA. Cada toma incluida (salvo las que excluye el cierre b) tiene las tres condiciones, cada una con las repeticiones normales 1, 2 y 3 (válidas o no), y la pasada suplementaria (3 repeticiones, la 4, la 5 y la 6) cuando la normal dio 0 válidas. Todas las corridas son de UNA sola pila (`sha256_pila`), nunca la réplica FALSA de los ensayos. Si falta o sobra algo, o hay más de una pila, el script se detiene (código 3): la réplica se completa con `--reanudar` o `--suplementaria`, que también avisan qué falta. Con `--desvio` se declara en vez de detenerse. Sin ninguna réplica con obstáculo válida, no hay principal y se detiene.
- **Cierre (b):** la trayectoria reproducida del 4 coincide con la medida dentro de 1 mm, sin desfase de una decisión, con el rumbo dentro de 1e-6 rad y los mandos del 4 idénticos a los grabados (decisión de José, 2026-10-10). Se evalúa sobre las decisiones que corrieron, **también en las corridas inválidas**, y el script aplica los umbrales él mismo (bandera en 0, error > 1 mm, desfase ≠ 0, rumbo > 1e-6 rad o mandos distintos es falla). Un cierre sin evaluar en una corrida con obstáculo viola el contrato (código 3). Una corrida con 0 decisiones (no arrancó) no tiene cierre (b): es una repetición inválida y no excluye la toma (convención aprobada por José, 2026-10-10).
  - Si falla en una toma, esa toma se excluye de la réplica con su motivo y se informa.
  - **Si falla en más de dos tomas, es un error de la réplica:** el script se detiene, la réplica se corrige y se vuelve a correr. No se excluye.
- **Cierres (a1) y (a3)** de la variante sin obstáculo contra `replica_con_capas` (decisión 7, sin a2). Son pruebas de la réplica, no del análisis: se informan en el reporte.
  - **(a1):** por AST, la inversa de marcos, la calibración identidad y la regla de la rampa son las de `replica_con_capas.py`; a nivel de decisión, sin red ni tiempo real, la pila sin obstáculo decide bit a bit igual que la del 30-09 ante las mismas observaciones (también durante la rampa); y `correr_toma` llama al lazo de evaluación con los mismos argumentos.
  - **(a3), aprobado por José (2026-10-10):** 12 episodios válidos del 30-09, la última aparición válida de cada semilla, corridos sin obstáculo con τ = 0 y 3 repeticiones. Para cada episodio, Δ = media de las repeticiones válidas nuevas − media de las repeticiones válidas de la réplica del 30-09. **Pasa** si el IC95 t (11 gl) de la media de Δ queda dentro de ±0.00827, el desvío dentro de episodio agrupado de la réplica del 30-09 (50 episodios, 98 gl, ddof = 1). Corre con la máquina libre, como la réplica del 30-09. **Si no pasa, se investiga antes de correr la réplica de la campaña, sin cambiar el margen.**
    - **Resultado (2026-10-10): NO PASA.** En `resultados_demo_obstaculo/replica_campana/cierre_a3_20261010_b/` (12 episodios, 36/36 repeticiones válidas, una sola pila): media de Δ = −0.00252, IC95 [−0.01052, +0.00549]; el límite inferior queda fuera de ±0.00827. La investigación está en `cierre_a3_20261010_b/diagnostico_20261010/`.
    - **Decisión de José (2026-10-10):** sigue la réplica de la campaña, con la investigación como respaldo. El veredicto queda NO PASA y se declara así en el reporte, con el diagnóstico: la decisión es bit a bit igual a la del 30-09 en los episodios que lo deciden; el ruido entre repeticiones es el mismo que el del 30-09; y esos dos episodios van en direcciones opuestas (la bifurcación nueva de s05 ep 2, Δ = −0.040, y la corrida baja del 30-09 en s05 ep 8, Δ = +0.013). No se repite el a3 ni se cambia el margen. Su IC95 va al reporte como salvedad del §6.
- La réplica se escribe antes del laboratorio y se prueba con los ensayos del 07-10 (ajuste de José). Sobre las tomas de la campaña corre después de cerrarla, nunca en paralelo con el hardware, y **con la PC limpia: sin Chrome, ChatGPT, Omen ni el servidor de Inventor** (decisión de José, 2026-10-10). Cada corrida anota su inicio y el sha256 de su pila (§9).
- **Descriptivos post hoc** (los pidió José el 2026-10-10, después del a3; van en el reporte rotulados "post hoc" y no deciden nada):
  - el p95 del ciclo de la réplica: el `ciclo_p95_ms` de cada corrida con `decisiones` > 0 (normales y suplementarias, válidas o no; columna informativa de la réplica), su media y su máximo por condición (las tres de arriba);
  - en la variante sin obstáculo, cuántas tomas tienen un desvío entre repeticiones > 0.01 (repeticiones válidas, ddof = 1, tomas con ≥ 2 válidas), contra 6 de 50 en la réplica del 30-09, con la misma definición (con ddof = 0 también son 6).

## 8. Cegado y declaraciones obligatorias

- Ninguna corrida de réplica sobre tomas de la campaña, ni parcial, antes de cerrarla: una con `inicio` anterior al cierre detiene el análisis (código 3).
- El análisis exige la campaña CERRADA, de plataforma `hw`, y el sha256 de este plan, del script y de `campana_obstaculo.py` (de él depende la inclusión) iguales a los vigentes del libro. Si no, se niega, salvo `--desvio "motivo"`, que queda escrito en la salida. `--ensayo` es sólo para datos de prueba: rotula todo como ENSAYO y se niega sobre una campaña de hardware.
- El verificador independiente (`verificar_campana_l2.py`, congelado con el plan) recalcula desde el crudo, con código propio, las cifras de la salida y el d_k de cada toma, y comprueba los sha256 contra el libro. Con un `--desvio` que cambió uno de esos archivos, recalcula igual todas las cifras, pero informa la diferencia de sha256 como falla y sale con 1 (no lee la declaración del análisis); el reporte la presenta con el motivo del desvío.
- **Configuración del día:** los offsets de rumbo y la calibración del mocap no bloquean (decisión de José); se anotan en el libro en cada apertura, ya aplicados. El resto de `config_robotat.py` (rampa, rpm, antigüedad de pose, mapeo de agentes, funciones) entra con una huella propia y bloquea como un archivo congelado. El mapeo bloquea en el archivo; el que aplica la calibración del día al correr (su robot como agente 0) se registra y lo verifica el régimen del análisis (robots 1, 5, 8, 2 y 9).
- Se declaran:
  - las tomas cuyo 4 no arrancó de la proyección (`col_obst_origen`), con sus intentos;
  - la rampa en la primera toma de cada sesión (sensibilidad D);
  - las correcciones del libro con sus motivos, los candados liberados y las filas ilegibles del libro;
  - las pausas de seguridad con sus respuestas;
  - las reservas que marcó el análisis y las corridas que el libro marcó interrumpidas;
  - los sha256 de las pilas de la réplica;
  - la configuración del día de cada sesión (offsets efectivos y sha256 de `config_robotat.py` y de la calibración).

## 9. Contrato de columnas del CSV de la réplica

Archivos `*_replica_tomas.csv` en `resultados_demo_obstaculo/replica_campana/<nombre>/`. Una fila por corrida:

| columna | contenido |
|---|---|
| `campana` | nombre de la campaña |
| `fuente_tomas` | nombre del CSV de tomas del hw de donde sale la toma |
| `id_sesion` | sesión del hw |
| `intento_campana` | intento del libro (la clave del pareo) |
| `semilla` | semilla del intento (se verifica contra el libro) |
| `condicion` | `con_obstaculo` o `sin_obstaculo` |
| `tau_s` | retardo de actuación de la réplica: 0 o 0.45 |
| `rep` | número de repetición (1, 2, 3; la suplementaria sigue numerando) |
| `pasada` | `normal` o `suplementaria` |
| `inicio` | inicio de la corrida, ISO 8601 local con segundos (`AAAA-MM-DDTHH:MM:SS`, como el libro) |
| `sha256_pila` | sha256 de la pila de la réplica al lanzarla |
| `decisiones_previas` | la rampa usada; tiene que ser la de la toma del hw |
| `valido`, `motivo` | validez de la corrida simulada, con las reglas del lazo de evaluación |
| `decisiones` | decisiones corridas |
| `cobertura_aoi` | cobertura final |
| `d_min_obst_medida` | vacío en `sin_obstaculo` |
| `d_pared_min`, `viola_018`, `colisiones_015`, `colisiones_022`, `frac_cbf`, `n_escape` | las del 30-09 |
| `frenos_sombra` | frenos que el supervisor habría dado con los agentes de la réplica (vacío en `sin_obstaculo`) |
| `cierre_b_ok`, `cierre_b_err_max_m`, `cierre_b_desfase`, `cierre_b_err_th_rad`, `cierre_b_mandos_iguales` | cierre (b) de la reproducción del 4 (posición, desfase, rumbo y mandos), sobre las decisiones corridas, también en las corridas inválidas (vacíos en `sin_obstaculo` y en una corrida con 0 decisiones, que no tiene cierre (b): §7) |

El script se detiene (código 3) si:
- la clave (`intento_campana`, `condicion`, `tau_s`, `rep`) se repite (típico de un `--reanudar` mal hecho);
- falta una columna del contrato o un entero no se puede leer;
- hay filas de un intento que no es una toma incluida, o una combinación condición/τ fuera de las tres del §7;
- la semilla o `decisiones_previas` no son las de la toma del hw.

Columnas extra se ignoran.

## 10. Salidas

En `resultados_demo_obstaculo/analisis_campana/<nombre>_<fecha_hora>[_ENSAYO]/`, nunca sobre una salida previa:
- `analisis.json`: todas las cifras a precisión completa, con los sha256 del plan, del script, del libro, de su cabecera y de cada CSV leído (también los del 30-09);
- `salida.txt`: el resumen legible;
- `pares.csv`: una fila por toma incluida (hw, réplicas, d_k, banderas A–D, costo, seguridad);
- `seguridad_tomas.csv`: una fila por toma corrida;
- `no_incluidas.csv`: los intentos no incluidos con su motivo.

El reporte cita estas cifras; `verificar_campana_l2.py <carpeta>` las recalcula desde el crudo (N/N) y se entrega con el zip de datos crudos, junto con el `verificar_cifras` del reporte. Fuera del análisis fijado, el reporte agrega el veredicto del a3 con su diagnóstico y su IC95 como salvedad (§6, §7) y los descriptivos post hoc del §7; sus cifras también van en `verificar_cifras`.
