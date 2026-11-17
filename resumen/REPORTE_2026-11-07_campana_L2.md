# Campaña L2 con el obstáculo móvil: sesiones del 23-10 al 06-11 y el mínimo de 30 incluidas

**Qué es:** la continuación del reporte del 22-10 (`REPORTE_2026-10-22_campana_L2.md`), que llegaba hasta el 21-10. Este cubre del 23-10 al 07-11:
- las sesiones de `L2_obstaculo_2` del 23-10, del 04-11 y del 06-11 (intentos 18–73);
- el corte simultáneo del 04-11 (servidor de poses y los 6 robots) y el diagnóstico de la red;
- los lanzamientos del 06-11 que no arrancaron: tres porque Motive estaba cerrado y uno porque la laptop no estaba conectada al Robotat;
- la revisión de la bitácora del 07-11 y las respuestas del operador, incluidas las que dio a las preguntas de la primera versión de este reporte (07-11).

**Esta versión (13-11) reemplaza a las dos del 07-11** (la primera, con su zip de 302 cifras, y la segunda, ya con las respuestas del operador). Frente a la segunda, lo principal que cambia:
- el corte del 04-11: que fallara el servidor, como dice el operador, explica la pérdida de poses pero no por sí solo el corte de los robots, cuyos enlaces no pasan por el servidor de poses; y el "timed out" del primer lanzamiento ya no se usa ni a favor ni en contra de una red degradada antes del corte (§1.6, §3.2, §7);
- la pose (2.10, 1.36) del robot 1 el 06-11: sí se leyó con el enlace caído. La versión del 07-11 decía lo contrario y lo declaraba como corrección a la bitácora; esa corrección se retira (§3.4; se quitó del §9.8);
- cuándo pudo correrse el `CHEQUEO OK` declarado del 06-11 y qué se sabe de la app de Claude ese día (§3.4, §9.1);
- la primera corrida de `verificar_red.py` del 06-11, que sí dejó salida y va en el paquete (§3.4, §11);
- "la laptop conectada a la red del Robotat" entra en la lección, el protocolo y la lista de antes de lanzar (§8, §10);
- la pausa del intento 24, que ya no se declara como desvío por una causa sin resolver (§4, §9.7);
- la versión de Python que necesita el verificador, y lo que comprueba y no cubre (§11).

Frente a la primera versión del 07-11 cambian, además, las respuestas del operador a las preguntas de aquella versión (§3, §9.5).

El reporte del 23-10 (`REPORTE_2026-10-23_demo_final.md`) es de la demostración final, que no se cita en el documento. De ella aquí sólo va la decisión de José sobre el panel (§2).

**La campaña `L2_obstaculo_2` sigue ABIERTA.** Este reporte no da ninguna cobertura de sus tomas, y el zip tampoco:
- la consola de la toma no la muestra;
- las tablas de tomas de `sesiones/` van sin la columna `cobertura_aoi` (los originales quedan intactos).

El análisis fijado corre después del cierre y de la réplica.

**Datos crudos:** `REPORTE_2026-11-07_campana_L2_datos.zip`. El script `scripts/verificar_cifras_campana_l2_20261107.py` recalcula desde los crudos, o coteja contra el archivo de donde sale, las cifras de este reporte, y comprueba que el texto las diga igual. Lo principal que no cubre está en el §11.

**Fuera de este reporte:** los demás trabajos del período (el Exp Q, el Exp R y el material del video) no entran aquí.

---

## 1. Resumen

1. **El 06-11 se alcanzó el mínimo.** La campaña va en **73/100 intentos y 30/50 incluidas**, con 56 corridas y, en ellas, **0 tomas con contacto, 0 frenos de respaldo y 0 pares de agentes a < 0.15 m**. El contacto de colocación del intento 7 (21-10) no cuenta para el criterio de seguridad. Sigue abierta, y su veredicto ya no puede ser INCOMPLETA.
2. **En el período** se usaron los intentos 18–73: 56 intentos, 42 corridas y 23 incluidas. La sesión del 06-11 dio 18 incluidas en 36 intentos (50 %): el mejor día de la campaña. Por sesión, iguala a la de las 13:48 del 21-10, que dio 5 de 10 (§5).
3. **Distancia al obstáculo:** en las 56 corridas de la campaña, entre 0.2648 y 0.6415 m; en las 30 incluidas, entre 0.2648 y 0.4217 m, con mediana 0.3177 m. La menor, 0.2648 m, fue en el intento 71, sin contacto.
4. **Ritmo y meta:** 30/73 = 41 %, con IC95 de Wilson [0.305, 0.526].
   - Con los 27 intentos que quedan, el tope daría unas 41 incluidas (entre 38 y 44 con el IC).
   - Llegar a 50 exige 20 de 27. Al ritmo de la campaña la probabilidad es 0.0005, y 0.019 con el límite superior del IC.
   - Cerrando ahora, el veredicto es MÍNIMO; agotando el tope, casi seguro también. **Decide José: cerrar ahora o agotar el tope**, que es una sesión más de alrededor de 1 h (§5, §10).
5. **Los 33 intentos del período que no se incluyeron:** 18 por el seguimiento (14 por marcador congelado y 4 por antigüedad de pose), 8 sin correr por la colocación (7 por el 4 y 1 por los agentes), 4 por el obstáculo, los enlaces o la batería, y 3 interrumpidos (§5).
6. **El 04-11, entre las 12:31:59 y las 12:32:09, se cortaron a la vez el servidor de poses y los 6 robots** (10054). Apunta a una caída de la red del laboratorio. El operador dice que lo que fallaba era el servidor: eso explica la pérdida de poses, pero no por sí solo el corte de los robots, cuyos enlaces no pasan por el servidor de poses. Ninguna de las dos lecturas está confirmada con el laboratorio. En la sesión de las 12:51 los enlaces se volvieron a resetear con el tráfico (16 resets de los agentes y 3 del 4 en 6 min); en reposo, 90 s sin cortes. El diagnóstico de sólo lectura apuntó al WiFi del laboratorio, también sin confirmar. El 06-11 la red anduvo bien (§3, §7).
7. **El 06-11 no arrancaron cuatro lanzamientos.** Tres se cerraron en 1 s porque Motive estaba cerrado: el servidor del Robotat igual acepta la conexión y devuelve los marcadores congelados con valores basura, y el lanzamiento termina sin decir por qué. El primero, a las 19:29:46, dio "timed out" al conectar con el servidor de poses porque, según el operador, la laptop todavía no estaba conectada al Robotat; Motive cerrado no lo explicaba, porque sin Motive el servidor conectaba en 24 ms. El primer lanzamiento del 23-10 y del 04-11 dio el mismo "timed out"; probablemente fue lo mismo, sin confirmar. No se gastaron intentos (§8).
8. **Seguimiento:**
   - De los 14 congelamientos que pararon tomas, 10 fueron junto a la pared +y (4 de ellos en una esquina), 3 en la mitad alta junto a una pared lateral y 1 cerca de la esquina (0, 0).
   - El 06-11 se repitieron dos puntos, con varios robots: cerca de (0.95, 2.80) y la esquina (0.20–0.27, 2.77–2.83).
   - Hubo congelamientos lejos de las paredes los tres días: el 23-10 y el 04-11 a 3–5 cm de la zona interior del 21-10, y el 06-11 a 10–20 cm. Todo junto: x entre 1.456 y 1.685, y entre 1.058 y 1.328 (§6).
9. **El lazo:** 0 intervalos > 150 ms en las tres sesiones con tomas (el 21-10 hubo 3 y 6). El ciclo p95 medio fue 11.8 ms el 23-10 y 12.1 ms el 06-11, contra 23.4 y 23.6 ms el 21-10. El 04-11 por la mañana anduvo peor: 36.2 ms y 1.11 ticks fuera de plazo por decisión (el 21-10, 0.90 y 0.81). Esa sesión no tiene chequeo de la PC, y en sus tomas no hubo consultas de pose fallidas ni resets: la causa no consta (§7).
10. **Declaraciones** (§9):
    - de las 30 incluidas, 18 salen de una sesión con `CHEQUEO OK` declarado por el operador pero sin la salida pegada, 2 de una sesión con el OK compartido y 10 de sesiones sin `CHEQUEO OK` propio. En la sesión del 06-11, además, la app de Claude estaba abierta a las 19:34:58; el operador contestó "si" a si la cerró antes de lanzar (§9.5), y la hora del OK no consta;
    - la L0 habilitante sigue siendo la del 21-10, sin `CHEQUEO OK`;
    - no consta una recalibración de Motive;
    - los 22 archivos congelados siguen iguales a la cabecera de la campaña (22/22).

---

## 2. Decisiones de José del período

| Fecha | Decisión | Dónde quedó |
|---|---|---|
| 23-10 | "Acepto el panel en la misma laptop: el lazo queda en ~12.5 ms de 100." Es de la demostración final (no citable): la prueba 7 de su plan queda no aprobada y se acepta así. | bitácora, 23-10 |

En el período no hubo decisiones sobre la campaña. Las sesiones del 23-10, del 04-11 y del 06-11 se corrieron sin respuesta a dos decisiones del reporte del 22-10: la del ritmo (seguir, hacer antes el mapa de la sonda o aceptar el MÍNIMO) y la de repetir la L0 con `CHEQUEO OK`. Las que siguen pendientes están en el §10.

---

## 3. Sesiones

| Sesión | Abre | Cierra | Hora de fin | Intentos | Motivo del cierre |
|---|---|---|---|---|---|
| `L2_20261023_204819` | 20:48:19 | 20:48:24 | 21:15 | — | "timed out" con el servidor de poses |
| `L2_20261023_204919` | 20:49:19 | 20:49:30 | 21:15 | — | el robot 2 no responde en la red |
| `L2_20261023_205007` | 20:50:08 | 21:23:37 | 21:15 | 18–25 | interrumpida (Ctrl+C) |
| `L2_20261104_120701` | 12:07:02 | 12:07:07 | 13:40 | — | "timed out" con el servidor de poses |
| `L2_20261104_120744` | 12:07:44 | 12:41:20 | 13:40 | 26–35 | interrumpida (Ctrl+C), durante el corte de los enlaces |
| `L2_20261104_125102` | 12:51:02 | 12:58:45 | 13:40 | 36–37 | "fin de la sesión": pausa contestada "detenida" |
| `L2_20261106_192946` | 19:29:46 | 19:29:51 | 21:00 | — | "timed out" con el servidor de poses |
| `L2_20261106_193200` | 19:32:00 | 19:32:01 | 21:00 | — | "fin de la sesión" (Motive cerrado, §8) |
| `L2_20261106_193221` | 19:32:21 | 19:32:22 | 21:00 | — | "fin de la sesión" (ídem) |
| `L2_20261106_193330` | 19:33:30 | 19:33:31 | 21:00 | — | "fin de la sesión" (ídem) |
| `L2_20261106_193852` | 19:38:52 | 20:48:09 | 21:00 | 38–73 | interrumpida (Ctrl+C) |

Las horas y los motivos son los del libro. Los CSV de la sesión `L2_20261023_205007` llevan el prefijo `20261023_205008`, porque la hora de su nombre se toma un segundo después que la del identificador de la sesión.

### 3.1 23-10

- **Chequeo de la PC** a las 20:32:35: FALLA, a batería y con 5 procesos de OMEN. No consta un `CHEQUEO OK` después.
- **Intentos 18–25:** 3 incluidas (19, 20 y 21).
- **El intento 24** paró en la colocación por "ABORTO POR EL OBSTÁCULO: el obstáculo NO FRENA: se movió 51.1 cm durante la colocación (v medida 0.000 m/s)", y la pausa se contestó "s". Durante esa guía se movieron robots a mano, y **el operador confirmó (07-11) que también movió el 4**: el aborto lo causó la mano, no el robot (v medida 0).

### 3.2 04-11 por la mañana, y el corte de los enlaces

- **Chequeo de la PC:** no consta.
- **Intentos 26–35:** 2 incluidas (29 y 33). Los intentos 26, 27 y 28 se gastaron sin correr porque el 4 no quedó en su arranque.
- **La caída** (consola):
  - primero la fuente de poses se quedó sin datos frescos de los 6 marcadores;
  - después, entre las 12:31:59 y las 12:32:09, se cortaron los enlaces de los 6 robots (10054) y la conexión con el servidor de poses;
  - los robots 5, 2, 8 y 9 y el 4 volvieron a los 234–291 s; **el robot 1 no volvió** (274 intentos sin respuesta);
  - durante el corte la consola no pudo confirmar la detención de los robots y pidió cortarles la alimentación a mano. La del robot 1 siguió sin confirmarse hasta el final de la sesión; el operador le cortó la alimentación (respuesta del 07-11);
  - a las 12:40:24–26 se cortaron otra vez los cuatro agentes que habían vuelto y el 4. Los agentes regresaron en 18.5–22.2 s, y el 4 volvió frenado;
  - antes de esos fallos de envío, la consola imprime 14 líneas seguidas "[poses] conexión perdida", sin hora. No son 14 caídas nuevas del servidor de poses: son consultas fallidas sobre la conexión que se perdió en el primer corte y que la sesión no reabre (hay un solo "[poses] conectado", al arrancar). No dicen nada del estado del servidor en ese momento.
- Que caigan a la vez el servidor de poses y todos los robots apunta a la red del laboratorio, no al código ni a un robot. El operador dice que lo que fallaba era el servidor. Eso explica la pérdida de poses, pero no por sí solo el corte de los robots: la laptop (192.168.50.3) habla con cada robot (192.168.50.101–109) directo por el WiFi, sin pasar por el servidor de poses (192.168.50.200). **Ninguna de las dos lecturas está confirmada con el laboratorio.**
- El operador cortó con Ctrl+C a las 12:41:20, en la colocación del intento 35.

### 3.3 04-11 a las 12:51, y el diagnóstico de la red

- **Antes de lanzar** (sólo lectura, desde la laptop; resultado a las 12:46:40): los 7 equipos respondían al ping y aceptaban conexión, y los 6 marcadores estaban vivos. Latencia de poses en 200 consultas en lote: p50 3.4 ms, p95 14.9 ms y máx 52.3 ms, sin fallas.
- **Chequeo de la PC** a las 12:49:56: **OK**, pegado.
- **Intentos 36 y 37:** se gastaron en la colocación, el 36 por el enlace caído del 4 y el 37 por el del robot 5. Entre las 12:52:04 y las 12:58:13 hubo 16 resets de los enlaces de los agentes y 3 del 4.
- **Diagnóstico después de la sesión** (`derivados/diagnostico_solo_lectura_20261104.txt`):
  - ningún proceso de la laptop seguía conectado a los robots;
  - sin conflicto de IP: en 12 vueltas cada IP dio siempre la misma MAC;
  - ping de 60 s, sin pérdidas: router 8 ms de p50, servidor de poses 4 ms y los robots unos 210 ms;
  - conexiones abiertas con los 6 robots durante 90 s, sin enviar datos: 0 cortes;
  - la laptop tenía dos adaptadores WiFi activos: el TP-Link USB en la red del laboratorio y el interno en otra red. La ruta a los robots iba por el TP-Link.
- **Lectura:** con el tráfico de una sesión los enlaces se reseteaban; en reposo, no. Apunta al WiFi del laboratorio, que volvió degradado después de la caída. No está confirmado.

### 3.4 06-11

- **Chequeo de la PC** a las 19:21:17: FALLA, por 58 procesos de Chrome. Para la sesión de las 19:38 el operador informó (07-11) que dio `CHEQUEO OK`, pero la salida no se pegó: no constan la hora ni los procesos.
  - **La app de Claude** se había cerrado para el chequeo de las 19:21:17. Después se volvió a usar en la laptop: el operador le pegó la salida de ese chequeo, y de ella salió la primera corrida de `verificar_red.py` (abajo). El primer registro de `derivados/diagnostico_solo_lectura_20261106.txt`, de las 19:33:47, es el aviso de esa llamada cortada porque la sesión de la app terminó antes de registrar su resultado. Entre las 19:33:47 y las 19:34:58 hay resultados de comandos de la verificación de sólo lectura; son las horas de los resultados, no las de abrir y cerrar la app. El operador contestó "si" a si la cerró antes de lanzar a las 19:38:52 (§9.5); la hora del cierre no consta.
  - **La primera corrida de `verificar_red.py`** dejó salida (`derivados/verificar_red_20261106_1922_salida.txt`, copia literal): el archivo se creó a las 19:22:44 y se escribió por última vez a las 19:23:26. Ni el servidor de poses ni ninguno de los 6 robots abrió conexión (TimeoutError); el servidor y los robots 1, 5 y 8 perdieron el 100 % de los paquetes del ping (de los otros tres no quedó resultado), y la lectura de marcadores falló ("no se pudo leer el servidor de poses"). Es coherente con lo que dijo el operador: la laptop no estaba conectada al Robotat. No consta hasta cuándo siguió así.
- **Los cuatro lanzamientos que no arrancaron** (19:29–19:33): uno por "timed out" y tres que se cerraron en 1 s con "fin de la sesión". Los tres cierres de 1 s se deben a Motive cerrado (§8). El "timed out" fue porque la laptop todavía no estaba conectada al Robotat, según el operador.
- **Sesión de las 19:38:52, intentos 38–73:** 18 incluidas. Detalle en el §4.
- **El robot 1 a las 20:09:** en la toma 51 no siguió el comando (0 % de lo comandado en 50 pasos), y a las 20:09:01, en la guía de la toma 52, se cortó su enlace (10054). Volvió a los 84.4 s. Se le acabó la batería, y **el operador se la cambió** (respuesta del 07-11; su primera respuesta, "no fue intervención", se refería a la causa del corte).
  - Mientras el enlace estaba caído, el robot estuvo 30 refrescos sin pose, y después su pose reapareció a saltos: pasó de (2.26, 1.85) a (2.10, 1.36), donde quedó. Es el robot levantado para cambiarle la batería.
  - La tabla con (2.10, 1.36) sale impresa justo después de la línea de la reconexión, pero se leyó antes. En cada refresco, la guía lee las poses, después frena a los robots (ahí se reabrió el enlace) y recién entonces imprime la tabla (`_esperar_reposicionamiento`, en `sesion_robotat.py`).
  - Al reabrirse el enlace, el robot 1 llegó a su blanco en 12 s, y la toma 52 fue válida. Siguió en las tomas 52–72, con 14 de las incluidas, ya con la batería nueva.
- El operador cortó con Ctrl+C a las 20:48:09, en la guía del intento 73, al ver alcanzado el mínimo de 30, 12 min antes de la hora de fin. El corte gastó el intento 73.

---

## 4. Intentos 18–73

| Intento | Semilla | Estado | Válida / incluida | Motivo | d_min obstáculo (m) |
|---|---|---|---|---|---|
| 18 | 422017 | sin correr | — / no | el 4 no quedó en su arranque (a +159° de la tangente) | — |
| 19 | 422018 | corrida | sí / **sí** |  | 0.3469 |
| 20 | 422019 | corrida | sí / **sí** |  | 0.2968 |
| 21 | 422020 | corrida | sí / **sí** |  | 0.3465 |
| 22 | 422021 | corrida | no / no | marcador 9 congelado en (0.21, 2.56) | 0.4121 |
| 23 | 422022 | corrida | no / no | antigüedad de pose (marcador 8 repetido en (1.56, 1.31)) | 0.4644 |
| 24 | 422023 | parada en la colocación | — / no | ABORTO POR EL OBSTÁCULO: "NO FRENA", se movió 51.1 cm con v medida 0; pausa: "siguió" | — |
| 25 | 422024 | interrumpida | — / no | Ctrl+C en la guía, con el 4 fuera de su arranque | — |
| 26 | 422025 | sin correr | — / no | el 4 a +11.6 cm de su círculo y a +49° de la tangente | — |
| 27 | 422026 | sin correr | — / no | el 4 a +36.5 cm de su círculo | — |
| 28 | 422027 | sin correr | — / no | el 4 a +27.6 cm de su círculo | — |
| 29 | 422028 | corrida | sí / **sí** |  | 0.3696 |
| 30 | 422029 | corrida | no / no | antigüedad de pose (marcador 8 repetido en (1.48, 1.33)) | 0.6411 |
| 31 | 422030 | corrida | no / no | antigüedad de pose (marcador 9 repetido en (0.59, 0.37)) | 0.4295 |
| 32 | 422031 | corrida | no / no | marcador 9 congelado en (0.24, 0.30) | 0.6415 |
| 33 | 422032 | corrida | sí / **sí** |  | 0.2880 |
| 34 | 422033 | corrida | no / no | marcador 8 congelado en (2.71, 2.51) | 0.3551 |
| 35 | 422034 | interrumpida | — / no | Ctrl+C en la colocación, durante el corte de los enlaces | — |
| 36 | 422035 | parada en la colocación | — / no | ABORTO POR EL OBSTÁCULO: enlace del 4 caído antes de la colocación; pausa: "siguió" | — |
| 37 | 422036 | parada en la colocación | — / no | ENLACE DE RUEDAS CAÍDO en la colocación (robot 5); pausa: "detenida" | — |
| 38 | 422037 | sin correr | — / no | el 4 a +82.8 cm de su círculo | — |
| 39 | 422038 | sin correr | — / no | el 4 a +52.4 cm de su círculo y a −49° de la tangente | — |
| 40 | 422039 | sin correr | — / no | el 4 a +11.3 cm de su círculo | — |
| 41 | 422040 | sin correr | — / no | colocación de los agentes: el 8 a 186 cm y el 2 a 19 cm de su blanco | — |
| 42 | 422041 | corrida | no / no | marcador 1 congelado en (0.27, 2.81) | 0.4575 |
| 43 | 422042 | corrida | no / no | antigüedad de pose (marcador 9 repetido en (0.29, 0.46)) | 0.2886 |
| 44 | 422043 | corrida | sí / **sí** |  | 0.3326 |
| 45 | 422044 | corrida | no / no | marcador 1 congelado en (0.20, 2.83) | 0.3743 |
| 46 | 422045 | corrida | sí / **sí** |  | 0.3386 |
| 47 | 422046 | corrida | sí / **sí** |  | 0.3138 |
| 48 | 422047 | corrida | sí / **sí** |  | 0.2987 |
| 49 | 422048 | corrida | no / no | marcador 1 congelado en (0.94, 2.79) | 0.3174 |
| 50 | 422049 | corrida | no / no | marcador 9 congelado en (0.97, 2.82) | 0.2979 |
| 51 | 422050 | corrida | no / no | el robot 1 no sigue el comando (0 %); se le acababa la batería, según el operador | 0.3958 |
| 52 | 422051 | corrida | sí / **sí** |  | 0.3102 |
| 53 | 422052 | corrida | sí / **sí** |  | 0.3355 |
| 54 | 422053 | corrida | sí / **sí** |  | 0.2961 |
| 55 | 422054 | corrida | no / no | marcador 8 congelado en (2.86, 2.71) | 0.3939 |
| 56 | 422055 | corrida | sí / **sí** |  | 0.2926 |
| 57 | 422056 | corrida | no / no | marcador 9 congelado en (0.25, 2.41) | 0.4093 |
| 58 | 422057 | corrida | sí / **sí** |  | 0.2922 |
| 59 | 422058 | corrida | sí / **sí** |  | 0.3301 |
| 60 | 422059 | corrida | no / no | marcador 9 congelado en (0.84, 2.73) | 0.4197 |
| 61 | 422060 | corrida | sí / **sí** |  | 0.3417 |
| 62 | 422061 | corrida | no / no | marcador 9 congelado en (1.42, 2.82) | 0.4312 |
| 63 | 422062 | corrida | no / no | marcador 2 congelado en (0.92, 2.78) | 0.3412 |
| 64 | 422063 | corrida | sí / **sí** |  | 0.3014 |
| 65 | 422064 | corrida | sí / **sí** |  | 0.3068 |
| 66 | 422065 | corrida | sí / **sí** |  | 0.4217 |
| 67 | 422066 | corrida | no / no | marcador 9 congelado en (0.45, 2.82) | 0.3303 |
| 68 | 422067 | corrida | sí / **sí** |  | 0.3282 |
| 69 | 422068 | corrida | sí / **sí** |  | 0.3157 |
| 70 | 422069 | corrida | no / no | marcador 9 congelado en (0.20, 2.77) | 0.5496 |
| 71 | 422070 | corrida | sí / **sí** |  | 0.2648 |
| 72 | 422071 | corrida | sí / **sí** |  | 0.3198 |
| 73 | 422072 | interrumpida | — / no | Ctrl+C en la guía, con el marcador 9 congelado | — |

- **Libro:** semilla = 422000 + intento − 1 en todos los intentos; 0 tomas con contacto, 0 frenos de respaldo y 0 pares de agentes a < 0.15 m.
- "— / no" marca los intentos que no corrieron. Los motivos del 24, 25, 35 y 73 resumen el libro con lo que muestra la consola, y la batería del 51 sale de la respuesta del operador; las coordenadas de los congelamientos son las del libro.
- **Las pausas:** se contestó "siguió" en el 24 y el 36, y "detenida" en el 37. En el 24 y el 36 la respuesta llegó a los 4 y 5 s. En el 36, con la causa sin resolver: los enlaces seguían cayéndose (el 37 se perdió por lo mismo 32 s después). En el 24 la consola pedía levantar al 4 o cortarle la alimentación, pero según el operador (07-11) el 4 lo movió él a mano (§3.1): el aborto salió del desplazamiento, con v medida 0, y el 4 no andaba solo. Eso consta sólo por su respuesta; en la consola no consta que la causa estuviera entendida al contestar. El protocolo pide seguir sólo con la causa entendida y resuelta (§9).

---

## 5. Pérdidas y ritmo

**Por día:**

| Día | Intentos | Corridas | Incluidas | Ritmo |
|---|---|---|---|---|
| 21-10 (reporte anterior) | 1–17 | 14 | 7 | 41 % |
| 23-10 | 18–25 | 5 | 3 | 38 % |
| 04-11 | 26–37 | 6 | 2 | 17 % |
| 06-11 | 38–73 | 31 | 18 | 50 % |
| **campaña** | **1–73** | **56** | **30** | **41 %** |

**Los 33 intentos del período que no se incluyeron:**
- **seguimiento, 18:**
  - marcador congelado, 14: 22, 32, 34, 42, 45, 49, 50, 55, 57, 60, 62, 63, 67 y 70;
  - antigüedad de pose, 4: 23, 30, 31 y 43;
- **colocación, 8 sin correr:** 7 porque el 4 no quedó en su arranque (18, 26, 27, 28, 38, 39 y 40) y 1 por los agentes (41);
- **obstáculo, enlaces y batería, 4:** el 24 (el 4 "NO FRENA"), el 36 (enlace del 4), el 37 (enlace del 5) y el 51 (el robot 1 no siguió el comando; batería, según el operador);
- **interrumpidos con Ctrl+C, 3:** 25, 35 y 73.

En toda la campaña, los 43 no incluidos se reparten así: 24 por el seguimiento, 8 por la colocación, 6 por los robots, los enlaces o el obstáculo, y 5 interrumpidos.

**Ritmo:** 30/73 = 41 %, con IC95 de Wilson [0.305, 0.526].
- Al ritmo puntual, los 27 intentos que quedan dan unas 11 incluidas más: unas 41 al tope. Con el IC, entre 38 y 44.
- La meta de 50 pide 20 de 27 (74 %). Con un binomial de 27 intentos, la probabilidad de llegar es 0.0005 al ritmo puntual, 0.010 con un ritmo de 50 % y 0.019 con el límite superior del IC.
- **Cerrando ahora, el veredicto es MÍNIMO; agotando el tope, casi seguro también.** Seguir suma incluidas.
- El 06-11 se hicieron 36 intentos entre las 19:38:52 y las 20:48:09: unos 1.9 min por intento. Agotar el tope es una sesión más de alrededor de 1 h.

**La colocación del 4 gasta los reintentos de los agentes.** En `demo_obstaculo_movil.py`, cada pedido de colocar el 4 a mano y cada reintento de colocación de los agentes consumen una vuelta del mismo ciclo de 6 (`REINTENTOS_COLOCACION` = 5 en `sesion_robotat.py`). La columna `col_reintentos` de las tablas de tomas guarda la última vuelta usada (de 0 a 5).
- Los 7 intentos gastados por el 4 agotaron las 6 vueltas sólo con él.
- En el 41 se fueron 4 vueltas con el 4, así que el primer reintento de los agentes ya salió como "reintento 5/5" y el siguiente fallo gastó el intento.
- El 29 entró en la última vuelta (`col_reintentos` = 5).
- **Para el operador:** dejar el 4 bien en el primer pedido conserva los reintentos para los agentes.

**Además del 4, los reintentos los gastan los robots que "no avanza" en la colocación automática.** Avisos de "queda para el operador (no avanza)" en las consolas: 4 el 23-10 (el 5 ×3 y el 8 ×1), 8 el 04-11 por la mañana (el 1 ×3, el 5 ×3 y el 9 ×2), 8 a las 12:51, con los enlaces cayéndose, y 30 el 06-11, de los cinco robots (el 9 ×8, el 8 ×7, el 5 ×7, el 1 ×5 y el 2 ×3). Sigue pendiente revisar las ruedas.

---

## 6. Seguimiento: congelamientos de marcadores

Igual que en el reporte anterior, son rachas de pose repetida bit a bit en los CSV de decisiones (sólo durante las tomas; en la guía no se registran).

**Los 14 que pararon tomas** (posición del libro):

| Fecha | Intento | Robot | Posición |
|---|---|---|---|
| 23-10 | 22 | 9 | (0.21, 2.56) |
| 04-11 | 32 | 9 | (0.24, 0.30) |
| 04-11 | 34 | 8 | (2.71, 2.51) |
| 06-11 | 42 | 1 | (0.27, 2.81) |
| 06-11 | 45 | 1 | (0.20, 2.83) |
| 06-11 | 49 | 1 | (0.94, 2.79) |
| 06-11 | 50 | 9 | (0.97, 2.82) |
| 06-11 | 55 | 8 | (2.86, 2.71) |
| 06-11 | 57 | 9 | (0.25, 2.41) |
| 06-11 | 60 | 9 | (0.84, 2.73) |
| 06-11 | 62 | 9 | (1.42, 2.82) |
| 06-11 | 63 | 2 | (0.92, 2.78) |
| 06-11 | 67 | 9 | (0.45, 2.82) |
| 06-11 | 70 | 9 | (0.20, 2.77) |

- 10 de los 14 fueron a ≤ 0.30 m de la pared +y (y entre 2.71 y 2.83); 4 de ellos, en una esquina, también a ≤ 0.30 m de una pared lateral. Otros 3 fueron en la mitad alta, junto a una pared lateral: (0.21, 2.56), (2.71, 2.51) y (0.25, 2.41). El restante, cerca de la esquina (0, 0). 8 son del robot 9.
- **Puntos que se repiten el 06-11, con varios robots:**
  - **cerca de (0.95, 2.80):** 9 rachas con 3 robots (1, 9 y 2), en x entre 0.92 y 0.97 e y entre 2.78 y 2.82. 3 pararon la toma (49, 50 y 63) y 6 se recuperaron (en las tomas 45, 47, 55 ×2, 64 y 72). Además, en la guía de la 53 el marcador 1 estaba congelado en (0.95, 2.82);
  - **la esquina (0.20–0.27, 2.77–2.83):** pararon ahí 3 tomas (42 y 45 con el robot 1, 70 con el 9), y en las guías se vio congelados al 9 en (0.27, 2.80) y al 1 en (0.21, 2.83).

  Apuntan a puntos ciegos de las cámaras. No está confirmado; el mapa de la sonda lo decidiría. Los congelamientos de las guías salen de la consola, no de los CSV.
- **El 04-11 también se repitieron puntos, cada uno con un solo robot:** el 5, cuatro veces en la toma 32 en (2.36–2.37, 2.70–2.72), todas recuperadas; y el 9 en (0.24, 0.30), donde paró la 32, y en (0.25, 0.31) en la 34, recuperada. Con un solo robot no distinguen un lugar de un marcador.
- **Congelamientos lejos de las paredes** (> 1.0 m; el reporte del 22-10 usaba > 1.2 m) en los tres días:

  | Fecha | Intento | Robot | Posición | Cómo terminó |
  |---|---|---|---|---|
  | 23-10 | 23 | 8 | (1.56, 1.31) | en la parada por antigüedad de pose |
  | 04-11 | 30 | 8 | (1.46, 1.32) y (1.48, 1.33) | la segunda, en la parada por antigüedad de pose |
  | 06-11 | 48 | 1 | (1.67, 1.07) y (1.67, 1.06) | recuperadas |
  | 06-11 | 52 | 8 | (1.62, 1.14) | recuperada |
  | 06-11 | 66 | 9 | (1.68, 1.08) | recuperada |

  - Forman dos grupos. El 23-10 y el 04-11, el robot 8 quedó a 3–5 cm de la zona interior del 21-10 (x 1.456–1.548, y 1.213–1.281). El 06-11, los robots 1, 8 y 9 quedaron a 10–20 cm de esa zona, y a menos de 1.2 m de la pared y = 0: con el criterio del 22-10 no contarían como interiores.
  - En el período: x entre 1.462 y 1.685, y entre 1.058 y 1.328. Con el 21-10: **x entre 1.456 y 1.685, y entre 1.058 y 1.328**, con los robots 1, 8 y 9.
  - El grupo del 06-11, con tres robots, apunta a un lugar más que a un marcador. Que los dos grupos sean el mismo lugar no está mostrado.
- **Las 4 paradas por antigüedad de pose del período** (23, 30, 31 y 43) terminaron con una racha de 2 pasos de un robot: dos veces el 8 lejos de las paredes y dos el 9 en el cuadrante de la esquina (0, 0), a 0.5–0.7 m de ella, en (0.59, 0.37) y (0.29, 0.46). Un marcador que Motive mantiene congelado sigue mandando filas válidas y no dispara esa regla, así que en estas cuatro el marcador se quedó sin poses válidas. En cada una actuó el frenado por pose vencida (§7).
- **Repeticiones simultáneas:** ningún paso del período con los 5 agentes repetidos a la vez (el 21-10 hubo uno). El 04-11, en la toma 32, hubo 3 pasos con 2 agentes repetidos a la vez: el 5 en (2.36, 2.70) y el 9 en (0.24, 0.30).
- **Retrocesos por congelamiento**, según la columna `retrocesos_detalle` de las tablas de tomas:

  | Sesión | Recuperados | Siguieron congelados (parada) | Cortados por la parada por antigüedad | Cortados por el fin de la toma |
  |---|---|---|---|---|
  | 23-10 | 0 | 1 | 1 | 0 |
  | 04-11 | 7 | 2 | 2 | 0 |
  | 06-11 | 12 | 11 | 1 | 1 |

---

## 7. Tiempo del lazo, poses y enlaces

| | 23-10 | 04-11 (mañana) | 04-11 (12:51) | 06-11 |
|---|---|---|---|---|
| consultas de poses | 4860 | 5156 | 744 | 27007 |
| consultas fallidas | 0 | 32 | 0 | 0 |
| latencia de poses p50 / p95 / máx (ms) | 3.5 / 5.5 / 94.3 | 3.9 / 39.8 / 741.0 | 4.0 / 30.2 / 52.8 | 3.3 / 5.2 / 34.0 |
| poses rechazadas por inclinación | 345 | 9 | 0 | 170 |
| decisiones | 1878 | 1850 | 0 | 12841 |
| ticks que no alcanzaron su plazo | 1088 | 2046 | — | 9890 |
| ticks fuera de plazo por decisión | 0.58 | 1.11 | — | 0.77 |
| intervalos del lazo > 150 ms | 0 de 1873 | 0 de 1844 | — | 0 de 12810 |
| intervalo máximo (ms) | 126.3 | 142.7 | — | 129.7 |
| ciclo p95 medio por toma (ms) | 11.8 | 36.2 | — | 12.1 |
| resets de enlace de los agentes / del 4 | 0 / 0 | 9 / 2 | 16 / 3 | 1 / 0 |
| frenados por pose vencida | 1 | 2 | 0 | 1 |

- Las filas de consultas, latencias, rechazos, decisiones, ticks, resets y frenados son de la consola; las de intervalos y ciclo, de los CSV. Los frenados por pose vencida coinciden con las 4 paradas por antigüedad de pose (23, 30, 31 y 43).
- **Comparación con el 21-10:** ticks por decisión 0.90 y 0.81, intervalos > 150 ms 3 y 6, y ciclo p95 medio 23.4 y 23.6 ms. El 06-11 tiene el total de ticks más alto de la campaña porque fue la sesión más larga. Por decisión (0.77) es la segunda más baja de las cinco sesiones con tomas: sólo el 23-10 (0.58) quedó más abajo.
- **El 04-11 por la mañana** anduvo peor que el 21-10 en el ciclo p95 y en los ticks por decisión. Sus 6 tomas terminaron antes del corte de las 12:31:59, sin consultas de pose fallidas; las 32 fallidas y el máximo de 741.0 ms de la consola no cayeron en las tomas: la consola imprime 21 líneas de pérdida de la conexión con el servidor de poses, en el corte, y no se puede fechar el resto de las 32 ni el máximo, porque no imprime los vencimientos de plazo ni las latencias. La sesión no tiene chequeo de la PC. El "timed out" del primer lanzamiento se repitió los otros dos días con el lazo normal (el del 06-11, según el operador, porque la laptop no estaba conectada al Robotat), así que no indica una red degradada. Los datos no permiten saber si la red ya venía mal antes del corte. La causa del 36.2 ms no consta.
- **Enlaces del 04-11 por la mañana:** los 9 resets de agentes son los de la caída (5 a las 12:31:59–12:32:09 y 4 a las 12:40:24–26). El del robot 1 no se reabrió.
- **El 06-11** el único reset fue el del robot 1 a las 20:09:01. Según el operador, se le acabó la batería y se la cambió (§3.4). Fue un solo robot, sin otros resets en 69 min: nada apunta a la red.

---

## 8. El 06-11: Motive cerrado

- Lo que se vio: a las 19:29:46 un lanzamiento se cerró a los 5 s por "timed out" al conectar con el servidor de poses, y los de las 19:32:00, 19:32:21 y 19:33:30 se cerraron en 1 s con "fin de la sesión".
- **Verificación de sólo lectura a las 19:34:58** (`derivados/diagnostico_solo_lectura_20261106.txt`):
  - el servidor de poses conectaba en 24 ms;
  - los 6 marcadores salieron CONGELADOS: 1 valor distinto en 15 lecturas;
  - la consulta en lote respondía "OK" en 4.6 ms, pero con números basura, como 9.083e+223.
- **La causa:** al preguntarle qué se hizo en el laboratorio entre las 19:35 y las 19:38 (así quedó anotada la pregunta; la textual no consta), el operador respondió (07-11) "solo corrí el motive". De ahí se infiere que Motive no estaba corriendo, lo que coincide con la verificación de las 19:34:58. Con Motive corriendo, la sesión de las 19:38:52 arrancó con los marcadores vivos.
- **Lo que Motive no explica:** el "timed out" de las 19:29:46. Con Motive cerrado, el servidor aceptaba la conexión en 24 ms. Según el operador (07-11), fue porque la laptop todavía no estaba conectada al Robotat, y la primera corrida de `verificar_red.py` (§3.4) ya mostraba que no alcanzaba ni al servidor ni a los robots. Es el mismo "timed out" de 5 s del primer lanzamiento del 23-10 y del 04-11; probablemente por lo mismo, sin confirmar.
- **Por qué no se vio la causa de los cierres de 1 s:** antes de abrir los enlaces, la sesión revisa los 6 marcadores. Si alguno está congelado o sin respuesta, termina sin imprimir el porqué, y en campaña el libro anota sólo "fin de la sesión". Es el mismo cierre sin causa del reporte anterior (§10, punto 4); no gasta intentos.
- **Lección:** sin Motive, el servidor del Robotat no avisa. Antes de lanzar hay que comprobar que la laptop esté conectada a la red del Robotat y que Motive esté abierto y transmitiendo. Un "timed out" al conectar apunta primero a la laptop fuera de esa red; varios marcadores congelados a la vez, a Motive.

---

## 9. Declaraciones para el documento

1. **Chequeo de la PC por sesión con intentos**, según las consolas, la bitácora y el operador:

   | Sesión | ¿`CHEQUEO OK` antes? | Incluidas |
   |---|---|---|
   | 21-10, 13:26 (intento 1) | sí, pegado (13:25:56) | — |
   | 21-10, 13:34 (intentos 2–7) | compartido: el OK de las 13:32:16 | 2 y 4 |
   | 21-10, 13:48 (intentos 8–17) | no: el último OK, 963 s antes, era de otra sesión | 8, 9, 10, 13 y 14 |
   | 23-10, 20:50 (intentos 18–25) | no: el último chequeo, a las 20:32:35, dio FALLA | 19, 20 y 21 |
   | 04-11, 12:07 (intentos 26–35) | no consta | 29 y 33 |
   | 04-11, 12:51 (intentos 36–37) | sí, pegado (12:49:56) | — |
   | 06-11, 19:38 (intentos 38–73) | sí según el operador, sin la salida pegada; el último pegado, a las 19:21:17, dio FALLA | las 18 del 44 al 72 |

   - De las 30 incluidas: **18** con `CHEQUEO OK` declarado sin salida, **2** con el OK compartido y **10** sin `CHEQUEO OK` propio. De esas 10, 5 son de la sesión de las 13:48 del 21-10, 3 del 23-10 (el último chequeo dio FALLA) y 2 del 04-11 por la mañana (no consta ninguno).
   - El reporte del 22-10 contaba como chequeo propio sólo el que tenía su salida pegada. Con ese criterio, ninguna incluida tiene chequeo propio. Con la declaración del operador, las 18 del 06-11 tienen un `CHEQUEO OK` declarado, sin hora. No consta cuándo fue: el operador confirmó que dio OK, pero no la hora. Aun con la declaración, sólo cubriría la sesión si se corrió después de cerrar la app de Claude por última vez y antes de lanzar a las 19:38:52. La app se volvió a usar después del chequeo de las 19:21:17 y estaba en uso a las 19:34:58, y la hora en que se cerró no consta (§3.4). Un OK anterior a ese cierre no cubre el uso de la app, porque el chequeo detecta el servidor de Inventor de la app. Si además fue antes de las 19:33:31, cuando se cerró el último lanzamiento que no arrancó, quedó compartido con uno a cuatro de esos lanzamientos, entre 321 y 1055 s antes de abrir la sesión: como el de las 13:34 del 21-10, o sin `CHEQUEO OK` propio, como el de las 13:48 (963 s antes, de otra sesión). La pregunta al operador fue qué se hizo en el laboratorio entre las 19:35 y las 19:38, así que su "solo corrí el motive" no fecha el OK. Cómo contarlas en el documento lo decide José (§10).
   - **La app de Claude el 06-11:** se volvió a usar en la laptop después del chequeo de las 19:21:17 (el operador le pegó su salida, y de ella salió la primera corrida de `verificar_red.py`), y hay resultados de sus comandos entre las 19:33:47 y las 19:34:58. El operador contestó "si" a si la cerró antes de lanzar a las 19:38:52 (§9.5); la hora del cierre no consta. El chequeo detecta el servidor de Inventor de la app, no la app, así que un `CHEQUEO OK` anterior a ese cierre no cubre ese uso.
2. **La L0 habilitante** sigue siendo la del 21-10 a las 13:09, que corrió sin `CHEQUEO OK`. No se repitió: la línea "[campaña] L0 del robot 4: L0 OK" de cada lanzamiento es la lectura de esa L0 guardada.
3. **Recalibración de Motive:** no consta ninguna. El 06-11 Motive sólo se abrió. La calibración aplicada en todas las sesiones del período es la guardada en `calibracion_medida.json`: escala 1.0167 y rotación +0.49° (medidas el 28-08) y traslación (1.506, 1.256) (29-08). Es la misma del 16 y del 21-10; ese día la etapa 2 falló sin guardar valores.
4. **El código que corrió es el congelado.** Los 22 sha256 de hoy son iguales a los de la cabecera de `L2_obstaculo_2` (22/22).
5. **Respuestas del operador del 07-11**, a las preguntas de la primera versión de este reporte:
   - "timed out" de las 19:29:46 del 06-11: la laptop no estaba conectada al Robotat;
   - intento 24 (23-10): movió el 4 a mano;
   - 04-11: le cortó la alimentación al robot 1, y dice que lo que fallaba era el servidor;
   - robot 1 el 06-11: se le acabó la batería y se la cambió, lo que explica el cambio de pose con el enlace caído (§3.4);
   - 06-11: a la pregunta doble "¿a qué hora te dio el `CHEQUEO OK`, y cerraste la app de Claude antes de lanzar a las 19:38?" contestó "si". Se lee como que dio `CHEQUEO OK` y cerró la app antes de lanzar. **No dio la hora del OK ni la del cierre.**
6. **Rampa de arranque seguro:** la primera toma corrida de cada sesión la lleva (`decisiones_previas` = 0). En el período fueron la 19 y la 29, las dos incluidas, y la 42, no válida. Entran en la sensibilidad D del plan.
7. **Las pausas del 24 y del 36** se contestaron "s" a los 4 y 5 s (§4). El protocolo pide seguir sólo con la causa entendida y resuelta. La del 36, con los enlaces todavía cayéndose, se declara como desvío. La del 24 no se cuenta como desvío por una causa sin resolver si vale la respuesta del operador (movió el 4 a mano): lo que se declara es ese movimiento del 4 durante la colocación, que gastó el intento 24.
8. **Correcciones a la bitácora.** La bitácora es sólo de agregado; lo que se encontró se declara aquí o en adendas:
   - la adenda del 06-11 ya tiene sus correcciones en las tres adendas del 07-11. La primera corrige la L0, los intentos 43, 48 y 51, los reintentos de colocación, los ticks, la red, los retrocesos, los congelamientos de las guías y los puntos que se repiten; sobre el robot 1 a las 20:09, reemplaza "probablemente lo movieron a mano" por la batería y deja sin explicar sólo el cambio de pose con el enlace caído. La segunda corrige el `CHEQUEO OK` de la sesión de las 19:38. La tercera, con las respuestas del operador a la versión del 07-11 de este reporte, explica ese cambio de pose: el operador levantó el robot para cambiarle la batería, así que sí lo movieron a mano;
   - en la segunda adenda del 07-11, "Con la declaración del operador, 18 sí lo tienen" (chequeo propio) no se sostiene mientras no conste la hora del OK: lo declarado es un `CHEQUEO OK` sin hora, que pudo quedar compartido con los lanzamientos que no arrancaron y ser anterior al uso de la app de Claude (§9.1);
   - en la primera adenda del 07-11, "Del 23-10 y del 04-11 no hay conteo de decisiones registrado" está mal: las consolas dan 1878 y 1850 decisiones, es decir 0.58 y 1.11 ticks fuera de plazo por decisión (§7);
   - en la adenda del 04-11 a las 12:51, la verificación antes de lanzar figura "(12:48)"; su resultado es de las 12:46:40;
   - en la adenda del 04-11 por la mañana, "La red ya venía mal: el primer lanzamiento dio "timed out"" no se sostiene: el mismo "timed out" se repitió el 23-10 y el 06-11 con el lazo normal (el del 06-11, porque la laptop no estaba conectada al Robotat), y de las 32 consultas fallidas y el máximo de 741.0 ms ninguno cayó en las tomas (§7).

---

## 10. Pendiente

**Decisiones de José:**
1. **Cerrar o seguir.** Ya hay MÍNIMO, y llegar a la meta de 50 es muy improbable (§5).
   - Cerrar ahora: `--cerrar-campana "motivo"`, irreversible. Después vienen la réplica, el análisis y el reporte final.
   - Seguir hasta el tope: unas 41 incluidas (38–44), en una sesión de alrededor de 1 h. Casi seguro, el veredicto sigue en MÍNIMO.
   - Del reporte anterior sigue abierta otra opción: el mapa de la sonda en la pared +y, la esquina −x+y y la zona lejos de las paredes, antes de seguir o después del cierre. Los criterios de parada no cambian sin un desvío declarado.
2. **Cómo declarar el chequeo de la PC** de las 18 incluidas del 06-11: con `CHEQUEO OK` declarado (propio o compartido, según la hora que dé el operador), o sin chequeo porque no hay salida pegada (§9.1).
3. **Siguen las del reporte anterior**, sin cambios:
   - repetir la L0 con `CHEQUEO OK`;
   - confirmar con el laboratorio si se recalibró Motive;
   - el arreglo del cierre que no muestra su causa (corrección declarada; toca un archivo congelado). El 06-11 escondió que Motive estaba cerrado;
   - el modo de energía de referencia, y si el chequeo debe escribir solo en la bitácora;
   - la tolerancia de colocación de la L0;
   - la frase sobre el ruido entre repeticiones del (a3);
   - el defecto de `--simulador`.

**Operador:** la hora del `CHEQUEO OK` del 06-11 y si lo corrió después de cerrar la app de Claude (§9.1, §9.5); y si el "timed out" del primer lanzamiento del 23-10 y del 04-11 también fue la laptop sin conectar al Robotat (§8; no se le preguntó).

**Red del laboratorio:** confirmar la causa del corte del 04-11 (router, punto de acceso o servidor) y, si se sigue, que la red esté estable.

**Protocolo** (no está congelado; con el OK de José):
- antes de lanzar, comprobar que la laptop esté conectada a la red del Robotat y que Motive esté abierto y transmitiendo;
- apagar el WiFi interno de la laptop durante la sesión;
- mover el 4 a mano sólo cuando la guía lo pide para el obstáculo;
- pegar en la bitácora la salida del chequeo de la PC;
- dejar el 4 bien en el primer pedido, porque los pedidos del 4 gastan los reintentos de los agentes;
- los pendientes del reporte anterior: el paso de OMEN de la bandeja, el offset del 4 y el comando que revisa los marcadores.

**Laboratorio, si se sigue:** el mismo comando, desde el intento 74 (semilla 422073). Antes de cada lanzamiento, también al relanzar tras un corte:
1. la laptop conectada a la red del Robotat;
2. Motive abierto;
3. la app de Claude cerrada;
4. `CHEQUEO OK`, con la salida pegada;
5. los 6 marcadores vivos;
6. el 4 en su arranque;
7. la batería de los robots, sobre todo la del 1, las ruedas de los que "no avanza" y los enlaces del 8 y el 9.

**Después del cierre:**
1. la réplica, con `CHEQUEO OK` por lanzamiento y nunca en paralelo con el hardware;
2. el análisis fijado y el verificador independiente;
3. el reporte final con el zip, que lleva el (a3) NO PASA con su diagnóstico, los descriptivos post hoc rotulados y el chequeo de cada sesión y de cada lanzamiento.

---

## 11. Datos y verificación

`REPORTE_2026-11-07_campana_L2_datos.zip` contiene:
- **`documentos/`:**
  - este reporte;
  - el plan congelado y el protocolo como estaban al armar el zip: el 09-11, ya armado, se agregaron al chequeo de la PC los procesos del Exp R (es la única línea que difiere, y no estaba en las sesiones del período);
  - el extracto de la bitácora desde el 23-10 (`BITACORA_extracto_desde_20261023.md`);
  - el reporte del 22-10 (`REPORTE_2026-10-22_campana_L2.md`), para las cifras del 21-10.
- **`consola/`:** los textos pegados por el operador en el período, copiados literales: el chequeo del 23-10, las sesiones del 23-10, la del 04-11 por la mañana con el corte, el chequeo y la sesión de las 12:51, el chequeo del 06-11, dos de los lanzamientos del 06-11 que no arrancaron y la sesión del 06-11. El "timed out" de las 19:29:46 y el tercer cierre de 1 s constan sólo en el libro. Además, `referencia_consola_20261021_1409.txt`, la consola del 21-10 del zip anterior, de donde salen sus decisiones y ticks.
- **`campanas/L2_obstaculo_2/`:** `libro.csv` y `campana.json`.
- **`sesiones/`:** las cuatro sesiones del período con tomas o reservas (tomas sin `cobertura_aoi`, decisiones y obstáculo).
- **`derivados/`:** las salidas de las verificaciones de sólo lectura del 04-11 y del 06-11, con sus comandos y la hora local. Los dos scripts que van al lado hicieron la verificación de las 12:46:40 y la prueba de 90 s del 04-11; el resto fueron comandos en línea, que van en el mismo archivo. De las corridas de `verificar_red.py` del 06-11, la primera dejó salida, que va aparte y literal en `verificar_red_20261106_1922_salida.txt` (el archivo se creó a las 19:22:44 y se escribió por última vez a las 19:23:26). Las demás no dieron salida: una falló al llamar a la herramienta y la de las 19:34 terminó con `[killed]`. No son crudos de la campaña.
- **`codigo/`:** los 20 archivos congelados de la carpeta del coordinador (el plan va en `documentos/`), más `config_robotat.py` (su huella sin la calibración también está congelada) y `calibracion_medida.json`.
- **`scripts/`:** el verificador.
- **`sha256_paquete.txt`:** el sha256 de cada archivo del paquete, salvo esta lista.

Para verificar, desde la carpeta descomprimida. Hace falta Python 3.13, sin paquetes externos; el script no importa código del proyecto. Se probó con Python 3.13.14, en Windows con el código de página del sistema en UTF-8; el script escribe su salida en UTF-8. Con 3.14 no se probó.
- Con 3.11 o anterior no compila.
- Con 3.12, la huella sin calibración de `config_robotat.py` saldría distinta de la cabecera. Es un sha256 de `ast.dump`, y `ast.dump` cambió en 3.13 (ya no escribe las listas vacías). Por eso el script sólo corre con 3.13 y con otra versión se niega: 3.14 y posteriores no se probaron, y `ast.dump` puede volver a cambiar.

El comando:

```text
python scripts/verificar_cifras_campana_l2_20261107.py . documentos/REPORTE_2026-11-07_campana_L2.md
```

El verificador recalcula con código propio:
- el libro: estados, incluidas, semillas, d_min y la tabla de intentos;
- el ritmo, el IC de Wilson y las probabilidades del binomial;
- los intervalos del lazo, el ciclo p95, las rachas de pose repetida y los retrocesos, desde los CSV;
- los sha256 de los congelados contra la cabecera.

Comprueba que cada cifra que recalcula o coteja aparezca igual en este texto, y que ninguna tabla de tomas de `sesiones/` traiga cobertura.
- Varias de las del Resumen (§1) que repiten una del cuerpo con otras palabras tienen su propia comprobación; las que no la tienen están en «No cubre».
- Las principales que se repiten se comprueban en todas sus apariciones; las horas "entre las … y las …", todas contra las que salen de los crudos.
- Las demás se buscan como texto en todo el reporte, así que una segunda copia distinta de la misma cifra no se detecta.

**Algunas cifras no las recalcula, sino que las coteja contra un texto:**
- las de la consola (latencias, consultas, rechazos, decisiones, ticks, resets, caídas, frenados, avisos de "no avanza" y lo del robot 1 el 06-11), contra `consola/`;
- las del diagnóstico de la red y la verificación de las 19:34:58, contra `derivados/`;
- las citas de la bitácora, contra su extracto. Las que este texto copia literal (la decisión de José del §2, el aborto del intento 24, "solo corrí el motive", "no fue intervención", la pregunta doble de §9.5, la hora "(12:48)" y las frases que corrige el §9.8), también contra el cuerpo de este texto, sin contar el §11 que las nombra;
- el orden en que la guía lee las poses, frena a los robots e imprime la tabla (§3.4), contra `codigo/sesion_robotat.py`; y que el freno llega a reabrir el enlace, contra `codigo/adaptadores_robotat.py`;
- las direcciones de la laptop, los robots y el servidor de poses (§3.2), contra `derivados/`.

**No cubre, entre otras cosas:**
- las respuestas del operador (§1, §3.1, §3.2, §3.4, §4, §5, §7, §8 y §9), que están en el extracto de la bitácora pero no en una consola;
- cuándo se abrió y se cerró la app de Claude el 06-11: el derivado sólo da las horas de los resultados de sus comandos;
- del Resumen (§1): los 6 robots del corte del 04-11 y el intento 7 del 21-10;
- en la columna Motivo del §4, el texto de cada motivo: sólo se cotejan con el libro sus cifras (centímetros, grados, robots y coordenadas de los congelamientos) y, en el 51, el robot y el 0 %. No se comprueba lo que los motivos del 24, 25, 35 y 73 toman de la consola, ni la batería del 51, ni la v medida del 24;
- la clasificación del chequeo de cada sesión del §9.1 (propio, compartido, declarado o sin `CHEQUEO OK`): el verificador la toma fija y sólo cuenta, desde el libro, qué incluidas caen en cada sesión;
- que las vueltas de los intentos 18, 26–28 y 38–41 fueran pedidos del 4: comprueba `col_reintentos` = 5, que no los distingue de los reintentos de los agentes; se ve en la consola;
- los congelamientos de las guías (§6), que salen de la consola, y el final de las rachas lejos de las paredes del 04-11 y de la toma 48, que el verificador trae escrito;
- el "~1 h" del §5, que es una cuenta con los minutos por intento del 06-11;
- la lista de correcciones de la primera viñeta del §9.8, que resume las adendas del 07-11;
- que los demás trabajos del período no entren aquí.
