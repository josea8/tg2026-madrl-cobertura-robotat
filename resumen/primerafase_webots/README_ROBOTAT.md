# Puente al Robotat — manual de despliegue

Código para correr el enjambre entrenado sobre los Pololu 3pi+ del Robotat,
escrito y probado **sin hardware**. Este documento es lo que hay que leer
antes de la primera sesión de laboratorio.

La idea rectora: al llegar al laboratorio, lo único que no fue ejercitado
debe ser el hardware. Todo lo demás —formato en el cable, unidades, marcos,
manejo de fallos, parada— ya está probado contra un simulador local.

---

## 1. Qué hay acá

| Archivo | Qué hace |
|---|---|
| `config_robotat.py` | Endpoints, mapeo de IDs, **calibración** y límites. Todo lo no medido está marcado `NO_VERIFICADO`. |
| `protocolo_robotat.py` | Formato en el cable (JSON de poses, CBOR de ruedas), conversión de unidades, cuaternión→heading, validación y transformación de marco. **Único punto de conversión del orden de ruedas.** |
| `adaptadores_robotat.py` | `FuentePosesRobotat`, `CanalActuacionRobotat`, `EntornoEjecucionRobotat`. |
| `simulador_robotat.py` | Servidor local que habla los dos protocolos, con inyección de fallos. |
| `verificar_mapeo_ids.py` | Comprueba, moviendo un robot a la vez, que cada robot está asociado a su marcador. |
| `test_robotat.py` | 48 pruebas de formato y conversiones. Sin red. |
| `test_integracion_robotat.py` | 50 pruebas del puente completo contra el simulador, incluidas la tasa de consulta de poses y el `CoordinadorEnjambre` real corriendo fuera de Webots. |
| `lanzar_robotat.py` | Punto de entrada: chequeos previos, arranque seguro, lazo. |
| `sesion_robotat.py` | **Herramienta de sesión de laboratorio**: etapas guiadas, veredictos automáticos, registro completo. Ver §11. |
| `calibracion_sesion.py` | Almacén de lo medido (`calibracion_medida.json`); lo aplica sobre `config_robotat` al arrancar. |
| `test_sesion_robotat.py` | 67 pruebas del script de sesión contra el simulador, incluidos los cuatro abortos y el presupuesto de ciclo por decisión. |

Correr todo antes de salir para el laboratorio:

```bash
python test_robotat.py && python test_integracion_robotat.py && python test_sesion_robotat.py
```

---

## 2. Los dos protocolos, tal como se relevaron

Relevados de `robotat/*.m`. **No hay handshake, ni autenticación, ni
delimitador de mensaje, ni acuse de recibo en ninguno de los dos.**

### Poses — `192.168.50.200:1883`, JSON sobre TCP

```
petición : {"dst":1,"cmd":1,"pld":[<ids de marcador>]}
respuesta: [x,y,z,qw,qx,qy,qz, x,y,z,qw,qx,qy,qz, ...]   ← agente-major
desconexión: el literal ASCII 'EXIT'
```

El original hace `reshape(datos,[7,N])'`; como el `reshape` de MATLAB es
column-major, los **7 primeros valores son del primer agente**. El
cuaternión viene **escalar primero** (`qw` antes que `qx,qy,qz`).

### Ruedas — `192.168.50.10<id>:9090`, CBOR binario, 11 bytes

```
0x82                        array(2)
0xFA + 4 B float32 BE       dphiL   ← IZQUIERDA PRIMERO
0xFA + 4 B float32 BE       dphiR
```

Big-endian: el original hace `fliplr` sobre el typecast little-endian de
MATLAB. Unidades: **RPM**, saturadas a ±400 (en el original hay un 850
comentado, o sea que el límite se bajó a mano).

---

## 3. ⚠ El orden de ruedas

`robotat_3pi_set_wheel_velocities(robot, dphiL, dphiR)` recibe la
**izquierda primero**. Nuestro modelo diferencial produce `(φ̇_R, φ̇_L)` —
**derecha primero**. Son convenciones opuestas.

Toda la conversión vive en `protocolo_robotat.accion_a_rpm` y
`codificar_velocidades_rueda`, y en ningún otro lado. Está cubierta por:

* pruebas posicionales byte a byte (`test_robotat.PruebaOrdenDeRuedas`);
* pruebas de lazo cerrado contra el simulador, donde un giro comandado se
  lee de vuelta por el protocolo de poses
  (`test_integracion_robotat.PruebaLazoCerrado`);
* una prueba de mutación que introduce las dos inversiones posibles y
  confirma que la suite las detecta (4 y 3 fallos respectivamente).

Un error equivalente de asignación de motor en Webots costó dos sesiones de
depuración, porque el síntoma —el enjambre no cubre nada— es idéntico al de
una política que no sirve.

---

## 4. ⚠ S1 — La parada por software NO es una parada de emergencia

Esto no es una precaución genérica; es una consecuencia medida del
protocolo.

* `robotat_3pi_force_stop` es **byte a byte idéntico** a
  `set_wheel_velocities(robot, 0, 0)`: mismo socket, misma cola TCP, sin
  prioridad ni canal aparte.
* Si el enlace con un robot se cae, ese robot **conserva su última orden** y
  sigue andando indefinidamente. No hay watchdog del lado del robot.
* `CanalActuacionRobotat.detener_todo()` recorre los cinco robots aunque
  alguno falle, reintenta 3 veces, y **enumera por nombre** los que no
  confirmaron, con la instrucción de cortar alimentación a mano.

Está demostrado en
`test_integracion_robotat.PruebaDetencionConEnlaceCaido`: el robot con el
enlace caído queda con las ruedas girando mientras los demás frenan, y el
programa informa el fallo sin lanzar.

**Requisito operativo: durante toda sesión de laboratorio tiene que haber
una persona mirando la arena, con acceso físico al interruptor de cada
robot.** El software no puede garantizar la detención.

Defensas que sí están implementadas:

| Capa | Qué hace |
|---|---|
| `atexit` + `finally` (Fase 1) | cualquier salida del programa dispara `detener_todo()` |
| pose vencida (>150 ms) | el canal manda (0,0) a ese agente |
| sin pose nunca recibida | ese agente no arranca |
| caída de la mocap | `avanzar()` devuelve False → termina el lazo → parada |
| robot que no acepta conexión | `conectar()` falla y no se arranca con el enjambre incompleto |

---

## 4b. ⚠ S2 — Arranque seguro

§S1 cubre la detención. El arranque tiene el mismo problema al revés: si el
mapeo de IDs o la calibración de marco están mal, el primer comando manda un
robot a velocidad plena en la dirección equivocada antes de que nadie alcance
a reaccionar. Dos defensas independientes, activas por defecto.

### (a) Chequeo geométrico antes de la primera acción

`lanzar_robotat.py` junta una pose válida de cada agente y comprueba cuatro
condiciones **antes de construir el coordinador**, que es lo primero que
puede mandar una acción:

1. hay pose de los N agentes;
2. cada una cae dentro de la arena `[0,3]×[0,3]`;
3. ningún par está a menos de **0.15 m** (el `D_SAFE` del env: por debajo de
   eso se arranca en colisión);
4. ninguna está a menos de **0.20 m** de una pared.

La cuarta no es cosmética. El Exp A mostró que la política **no sabe
despegarse de un muro** —depende de la reflexión elástica, que en física real
no existe— y el comportamiento de escape sólo se dispara cuando el filtro CBF
ya está saturado. Arrancar pegado a la pared es arrancar en el único estado
del que el sistema no se recupera solo.

Si algo falla, no arranca y **nombra al agente y el motivo**; con cinco
robots en la arena, "algo está mal" no sirve. Los mensajes de fuera-de-arena
apuntan además a §C1/§C2, porque esa es casi siempre la causa real.

Las comparaciones llevan 1 mm de tolerancia (`TOL_GEOMETRICA_M`): sin ella el
umbral es un filo de navaja y una pose justo en el límite cae de cualquier
lado por redondeo, con un mensaje que parece falsa alarma
("0.150 m, mínimo 0.15 m").

### (b) Rampa de velocidad

Las primeras **50 decisiones (5 s)** salen al **25 % de V_MAX**. A 0.078 m/s
un robot recorre 8 cm en el segundo que tarda una persona en reaccionar,
contra 31 cm a velocidad plena.

El escalado va en el canal —la frontera—, no en el lazo, para que valga pase
lo que pase adentro. **Escalar no rompe el CBF**: si `cᵀu ≥ −α·h` con `h ≥ 0`,
entonces `cᵀ(k·u) = k·cᵀu ≥ k·(−α·h) ≥ −α·h` para todo `k ∈ (0,1]`; reducir
uniformemente nunca viola una barrera que ya se satisfacía. Tampoco rompe el
escape: su ley de máximo ascenso da `ḣ = V|a| + ℓa·Ω|b| > 0`, que con `k > 0`
sigue siendo positiva, sólo más chica.

**Lo que sí queda desalineado**, y se acepta a propósito: el env recibe la
acción sin escalar, así que durante la rampa las componentes v/ω del
`own_state` de la observación son optimistas respecto de lo que el robot
hace. Las posiciones no —ésas entran por `inyectar_poses_externas` y son las
medidas—, y son 50 de varios cientos de decisiones.

Para desactivarlo hay que pedirlo explícitamente:

```bash
python lanzar_robotat.py --sin-arranque-seguro
```

---

## 5a. ⚠ S3 — Tasa de consulta de poses: una vez por decisión, no por tick

**DECISIÓN (2026-08-22): consultar poses una vez por decisión (10 Hz), no
una vez por tick (100 Hz).**

### Por qué

`FuentePosesRobotat` heredó de Webots el hábito de drenar poses en cada
tick — ahí es casi gratis, un mensaje interno simulado. En el Robotat cada
consulta es un round-trip TCP real, y esta sesión demostró **dos veces**
que el servidor no es robusto bajo carga:

- empuja un frame sin que se lo pidan al aceptar la conexión (§3, hallazgo
  del `descartar_buffer_pendiente`);
- se rompió con 26 reconexiones en 1.5 s durante un escaneo de marcador
  (§5, hallazgo de `_ClientePosesIndividual`).

Sostener 100 consultas por segundo durante minutos, en una máquina
compartida con otros estudiantes, es un riesgo innecesario para
información que nadie consume: el lazo decide a **10 Hz**
(`DT_ENV = 0.1` en `coordinador_enjambre.py`), así que 9 de cada 10
consultas a 100 Hz no alimentaban ninguna acción.

La opción de mantener 100 Hz "para medirlo primero" se descartó porque la
medición ES el riesgo: si el servidor se degrada a esa carga, no se
obtiene un número limpio, se pierde una sesión depurando por qué las
poses llegan mal — exactamente lo que ya pasó dos veces.

Un punto intermedio (20–30 Hz) tampoco se justifica: conservaría
"frescura intra-decisión" que la política no consume, porque sólo mira la
pose en el instante de decidir.

### El margen que lo respalda

Consultar **justo antes de decidir** deja la pose con la antigüedad de un
solo ida y vuelta — más fresca que sondeando a 100 Hz, donde en el
instante de decidir se usa la última lectura disponible más su propio
retardo. El margen de 300 ms de antigüedad, validado en los Exp F/H,
cubre el caso nuevo (~100 ms) con holgura de sobra.

### Cómo funciona

`HZ_CONSULTA_POSES` en `config_robotat.py` — un **parámetro**, no una
constante: se puede subir por sesión sin tocar código
(`cfg.HZ_CONSULTA_POSES = 100.0` antes de construir el entorno). Default
10.0, igual a la tasa de decisión.

`leer_poses()` se sigue llamando una vez por tick (`_avanzar` no cambia,
es código compartido con Webots) pero sólo hace un round-trip real cada
`intervalo_ticks` llamadas — las demás devuelven `[]` sin tocar la red.
Con el default, `intervalo_ticks == pasos_por_decision`, así que la
consulta real cae exactamente en el **último tick antes de cada
decisión** — de ahí el margen mínimo de antigüedad.

La etapa 4b (latencia de actuación) **no** pasa por este límite: usa
`ClientePosesCrudo`, un cliente separado de `FuentePosesRobotat` que
siempre consultó al máximo régimen posible. No hace falta subir la tasa
para esa etapa.

**Hallazgo al implementar esto:** `fuente.reiniciar()` —documentado en la
interfaz para invalidar el estado acumulado al empezar un episodio— nunca
se llamaba, en ningún adaptador, desde que existe la Fase 1. Se agregó la
llamada en el mismo punto donde el coordinador invalida su propio caché.
Sin impacto en Webots (su `reiniciar()` sólo limpia un `_vistos` de
diagnóstico que nada más lee); en el Robotat, además, reinicia el
limitador de tasa para que la primera consulta de cada episodio sea
inmediata.

### El número que decide si esto se sostiene

**Medido en la etapa 4a, reportado como p95** (no la media: una cola larga
ocasional igual empuja alguna decisión fuera de presupuesto):

| p95 del round-trip / presupuesto de 100 ms | Veredicto |
|---|---|
| < 10 % | ✔ margen amplio |
| 10–30 % | ⚠ aceptable, vigilar |
| > 30 % | ✘ riesgoso — ver plan de contingencia abajo |

La sesión de política instrumenta lo mismo por decisión (consulta +
transformación + inferencia + filtro + envío), cuenta cuántas decisiones
superan el presupuesto, y lo reporta por escalón y en el resumen final.
Si ocurre de forma sistemática (>20 % de las decisiones de una ventana),
el lazo no está corriendo a la frecuencia que la política espera y **ese
dato invalida la corrida**, no sólo la anota.

### Plan de contingencia — NO implementado

Si el p95 medido en el laboratorio resulta una fracción apreciable del
presupuesto, la salida **no** es volver a 100 Hz: es un **hilo de sondeo
en segundo plano** a una tasa moderada, con el lazo de decisión leyendo de
un caché sin bloquearse en la consulta síncrona. Queda anotado, no
implementado — se decide con el número medido, no antes.

---

## 5. Los dos espacios de IDs

El servidor de captura identifica **marcadores** (1–100); los robots se
direccionan por **ID de robot** (0–19).

**Correspondencia confirmada por el autor (2026-08-22), asignación de la
plataforma, no una inferencia de sesión:** los marcadores 1 a 16 están
destinados a los Pololu, uno por robot, **robot N ↔ marcador N**. A
diferencia de un marcador SUELTO (el de meta, por ejemplo, que se coloca a
mano y no conserva su posición), el montado en el chasis de cada robot es
fijo y permanente. Coincide con el dato medido del robot 2 (giró el
marcador 2, ningún otro). La numeración humana arranca en 1: el robot "0"
del rango de conexión (0–19) no corresponde a ningún Pololu físico.

La tabla está en `config_robotat.MAPEO_AGENTES`, con la fórmula directa
(`id_marcador = id_robot`) y `MAPEO_NO_VERIFICADO = False`.

**`verificar_mapeo_ids.py` / la etapa 1 de `sesion_robotat.py` siguen
disponibles como chequeo de seguridad OPCIONAL**, no como paso obligatorio
— útiles antes de mover un robot que no se usó todavía, o si se sospecha
que una constelación se montó mal:

```bash
python verificar_mapeo_ids.py
# o, con escaneo de varios candidatos en un solo giro:
python sesion_robotat.py --sesion calibracion --etapa 1 --robot N
```

Gira el robot **en el lugar** (≈1 rad/s, 1.2 s, sin traslación) y observa
cuál marcador cambió de heading. Se usa rotación pura porque es segura y
porque el Δyaw no depende del offset de heading, que en la primera sesión
todavía no está calibrado.

Ambas herramientas están a su vez verificadas: contra un simulador con
mapeo correcto dan OK, contra uno permutado señalan exactamente qué
agentes están cruzados, y ante un robot que no se mueve dicen `NADIE` en
vez de un falso OK. Un mapeo cruzado **no produce un error** — produce un
enjambre donde cada robot obedece órdenes calculadas con la pose de otro,
indistinguible de "la política no sirve" — por eso vale la pena tener el
chequeo a mano aunque ya no sea obligatorio.

---

## 6. Procedimientos de calibración

Los cinco parámetros de abajo **no se pueden deducir del código de
referencia**. Hay que medirlos en la primera sesión. Mientras
`*_NO_VERIFICADO` sea `True`, `lanzar_robotat.py` lo avisa al arrancar.

### §C1 — Escala de posición (`ESCALA_POSICION`)

> **✔ MEDIDO (2026-08-26): el servidor entrega METROS, y la escala es 1.0.**
> Evidencia directa: las `z` de un robot en el piso salen 0.038–0.069, que
> son los centímetros de alto del chasis con el marcador encima. En
> milímetros esas alturas serían micras.
>
> **⚠ El área útil del Robotat NO es la arena del env.** Medida en el
> laboratorio, descontando los bordes: **4.67 × 3.45 m**, contra los
> 3.0 × 3.0 m del env. Ni el mismo tamaño ni la misma forma, y **no se
> escala una en la otra**:
>
> 1. no es cuadrada — haría falta un factor por eje (0.64 en x, 0.87 en y),
>    y `ESCALA_POSICION` es un escalar; un círculo de seguridad se
>    deformaría en elipse;
> 2. peor: **el robot no se encoge con el env**. Con un factor de ~0.64,
>    los 0.15 m de separación mínima entrarían como 0.096 m y los 0.20 m de
>    margen de pared como 0.128 m. La política se creería despejada estando
>    en colisión. Esos márgenes están en metros absolutos, calibrados
>    contra el chasis real.
>
> Como 3.0 cabe en 3.45 y en 4.67, **se elige un cuadrado de 3 × 3 dentro
> del área útil** (sobran 1.67 m en x, 0.45 m en y) y se trabaja sólo ahí,
> 1:1 en metros. Por eso la etapa 2 espera escala 1.0: cualquier otra cosa
> significa que las coordenadas medidas no son metros físicos desde la
> esquina de ese cuadrado.
>
> Cómo se descubrió: una etapa 2 dio escala 0.4168. No era una unidad —
> era el cociente entre lo que el mocap decía (los dos puntos a 2.76 m) y
> lo que se había ingresado (1.15 m). El prompt pedía coordenadas "en el
> marco del env, arena de 3.0 × 3.0" sin decir que el área física es otra,
> así que la conversión se la comía el operador en silencio.

El texto original, que sigue valiendo como método:

El código MATLAB no declara unidades. Puede entregar metros o milímetros.

1. Poner un robot en un punto, leer `x`.
2. Moverlo **exactamente 1 m** con cinta métrica, leer `x` de nuevo.
3. `ESCALA_POSICION = 1.0 / |Δx|`. Sale ≈1.0 (metros) o ≈0.001 (milímetros).
4. Poner `ESCALA_NO_VERIFICADA = False`.

*Red de seguridad, no sustituto:* si el servidor entrega milímetros con
escala 1.0, las poses caen fuera de `RANGO_LAB_*` y se rechazan todas —el
sistema no arranca en vez de conducir con posiciones 1000× mal. Pero un
robot cerca del origen es invariante de escala y esa defensa no lo ve.

### §C2 — Marco (`ROTACION_MARCO_RAD`, `TRASLACION_*`)

El env vive en `[0,3]×[0,3]` con origen en una esquina; el laboratorio tiene
otro origen y posiblemente otra orientación.

1. Poner un robot en tres esquinas conocidas de la arena de 3×3 y anotar
   `(x,y)` del laboratorio en cada una.
2. Ajustar la rotación como el ángulo entre el eje x del laboratorio y el
   lado de la arena que se eligió como +x del env.
3. La traslación es lo que lleva el origen del laboratorio al centro de la
   arena; con el laboratorio centrado da `(1.5, 1.5)`.
4. Comprobar: las cuatro esquinas del env deben caer en `(0,0)`, `(3,0)`,
   `(0,3)`, `(3,3)` con error < 5 cm.
5. Poner `MARCO_NO_VERIFICADO = False`.

### §C3 — Offset de heading (`OFFSET_HEADING_RAD`)

Depende de cómo esté montada la constelación de marcadores sobre el chasis.
Es el mismo parámetro que hubo que calibrar en Webots.

1. Comandar avance puro (v > 0, ω = 0) durante ~1 s.
2. Calcular la dirección real del desplazamiento:
   `α = atan2(Δy, Δx)` sobre las posiciones del laboratorio.
3. `OFFSET_HEADING_RAD = α − yaw_reportado` (envuelto a (−π, π]).
4. Repetir con el robot apuntando a otro lado: el offset debe dar igual.
5. Poner `HEADING_NO_VERIFICADO = False`.

### §C4 — Geometría de rueda (`RADIO_RUEDA_M`, `MEDIO_EJE_M`)

Los valores actuales (r = 16 mm, ℓ = 48 mm) vienen de `laboratorio11.m` y de
la hoja de datos de Pololu, **no de una medición**.

**Hay tres semiejes en circulación en el laboratorio.** Cada uno es correcto
en su dominio y cruzarlos escala mal las velocidades:

| Semieje | De dónde sale | Dónde va |
|---|---|---|
| 0.0700 m | anchors ±0.07 de nuestro proto | `protocolo.py` (Webots) |
| 0.0412 m | proto del lab11, (96 − 2·6.8 mm)/2 | ese controlador solamente |
| 0.0480 m | robot real, 96 mm / 2 | `config_robotat.py` (Robotat) |

Y dos radios: el modelo de Webots del lab usa 32 mm de **radio** donde el
robot físico tiene 32 mm de **diámetro**. `laboratorio11.m` lo dice textual:
*"Radio de rueda: 16 mm (no 32 mm como en el modelo de simulación)"*.

Los nuestros de Webots están calibrados contra la geometría que Webots
simula (giro verificado a 6.28 s/vuelta) y **no van al Robotat**.

1. Radio: medir el diámetro de rueda con calibre, dividir por 2.
2. Medio eje: medir de centro a centro de las bandas de rodadura, dividir
   por 2.
3. Comprobación funcional: comandar ω = 1 rad/s durante 6.28 s; el robot
   debe dar **una vuelta completa**. Si sobra o falta, corregir `ℓ`.
4. Comprobación funcional: comandar v = 0.2 m/s durante 2 s; debe recorrer
   40 cm. Si no, corregir `r`.
5. Poner `GEOMETRIA_NO_VERIFICADA = False`.

### §C4b — ⚠ La caja de acciones de la política es mucho más rápida que lo validado en el laboratorio

Con la geometría real, así se compara nuestra caja de acciones contra la del
controlador del lab que **ya funcionó en estos robots** (`laboratorio11.m`):

| Caso | rpm pico | vs. cap del lab (200) | vs. límite de la función (400) |
|---|---|---|---|
| nuestro: avance V_MAX = 0.31 m/s | 185.0 | 0.93× | 0.46× |
| nuestro: giro Ω_MAX = 6.28 rad/s | 180.0 | 0.90× | 0.45× |
| **nuestro: peor combinación** | **365.0** | **1.83×** | **0.91×** |
| lab real: avance v_max = 0.07 m/s | 41.8 | 0.21× | 0.10× |
| lab real: giro w_max = 1.0 rad/s | 28.6 | 0.14× | 0.07× |
| lab real: peor combinación | 70.4 | 0.35× | 0.18× |

Nuestra V_MAX es **4.43×** la del lab y nuestra Ω_MAX **6.28×**; en rpm de
rueda, el peor caso nuestro es **5.18×** el del lab.

Tres cosas que conviene tener claras:

1. **`rpm_max = 200` es del lab, no del protocolo.** La función
   `robotat_3pi_set_wheel_velocities` satura a 400 (con un 850 comentado);
   `laboratorio11.m` se impone además un tope operativo de 200. Nuestro peor
   caso pasa el tope del lab pero no el de la función.
2. **El motivo declarado de la reducción es el lag inalámbrico**
   (`laboratorio11.m`: *"Velocidades muy reducidas por el lag
   inalámbrico"*), y el mismo archivo usa la mitad de la ganancia angular
   que su gemelo de Webots (kpO 2.0 vs 4.0, v0 0.06 vs 0.6 m/s: 10×).
3. **El Exp H NO cubre esto.** Midió tolerancia a 300 ms de retardo en las
   POSES, que es latencia del lazo de decisión. El lag del que habla el lab
   está en el camino de ACTUACIÓN. Son ejes distintos y el Exp H no autoriza
   estas velocidades.

**No se cambió V_MAX.** La política fue entrenada con esa cota y aparece en
la normalización de las observaciones; bajarla invalidaría el modelo. La
rampa de arranque (§S2) cubre los primeros 5 s al 25 %, lo que da 91 rpm de
pico — dentro del régimen del lab. Qué hacer después de la rampa es una
decisión abierta y hay que tomarla ANTES de la primera sesión completa.

### §C5 — Mapeo de IDs

Ver §5. `python verificar_mapeo_ids.py`.

---

## 7. Preguntas para el encargado del Robotat

Ninguna de éstas se puede resolver por inferencia sobre el código, y dos de
ellas cambian el comportamiento del sistema:

1. **✔ RESUELTO. Son DOS comportamientos distintos, y el segundo es
   peligroso** (medidos 2026-08-25 y 2026-08-29).

   **(a) Marcador que NUNCA estuvo trackeado** → fila normal con ceros en la
   posición y cuaternión IDENTIDAD (detalle abajo).

   **(b) Marcador que VENÍA trackeado y se ocluye** → el servidor devuelve
   **la ÚLTIMA POSE CONOCIDA, congelada, indefinidamente**. Medido tapando
   el marcador con la mano: la pose quedó clavada **13.4 s** (246 lecturas
   byte a byte idénticas) hasta el final de la captura.

   > ⚠ **Ninguna validación de una sola pose puede detectar (b).** La
   > respuesta tiene la forma correcta, cuaternión unitario y posición en
   > rango: las 366 lecturas dieron `pose_valida = 1`. Y la defensa de
   > antigüedad (`ANTIGUEDAD_MAX_POSE_S = 150 ms`) tampoco la ve, porque
   > mide desde que **nosotros recibimos** el dato, no desde que el mocap lo
   > produjo. Un stream congelado parece perfectamente fresco.
   >
   > Consecuencia para el lazo: la política vería un robot que no se mueve,
   > aumentaría la corrección, y lo mandaría contra la pared —o fuera de la
   > plataforma, que está elevada ~0.5 m—. **La detección de congelamiento
   > es obligatoria, no opcional.**
   >
   > Cómo se detecta: un marcador trackeado **jitterea** en los últimos
   > decimales aunque el robot esté quieto (ruido de captura, no
   > movimiento): 12 valores distintos en 12 lecturas con el robot inmóvil.
   > Decenas de lecturas idénticas seguidas es la firma inequívoca. Ver
   > `sesion_robotat.stream_congelado`, ya usado como precondición en las
   > etapas 0 y 5.
   >
   > Este modo de falla arruinó dos corridas de la etapa 5 sin que nada se
   > quejara, y casi hace concluir lo contrario de la verdad ("la oclusión
   > no cambia nada").

   Lo bueno: **en ninguno de los dos casos vienen menos filas**, así que el
   modo `"lote"` es seguro y no hace falta pasar a `"individual"`.

   Detalle de (a) — el placeholder del marcador nunca trackeado: **una fila
   normal, con ceros en la posición y el cuaternión IDENTIDAD**:

   ```
   [0.0, -0.0, 0.0, 1.0, 0.0, -0.0, 0.0]
   ```

   No son NaN, no es un error, y **no son menos filas** — así que el modo
   `"lote"` sigue siendo seguro y no hace falta pasar a `"individual"`.
   Medido con sonda directa contra los 16 marcadores: los no trackeados
   devuelven exactamente eso, los trackeados devuelven posiciones reales.

   ⚠ **El problema es que este placeholder pasa por válido.** La norma del
   cuaternión identidad es 1.0, así que `pose_es_valida()` NO lo rechaza:
   una etapa 0 contra un marcador no trackeado reporta "20/20 poses
   válidas" con 20 filas idénticas de ceros. Ya pasó y casi se calibra
   sobre basura. **Pendiente:** hacer que `pose_es_valida()` lo rechace.

   El texto original de la pregunta, por si sirve de contexto: el caso
   "fila ausente" habría sido **cualitativamente peor**, porque obligaría a
   descartar la respuesta entera y dejaría al enjambre completo sin pose
   ese ciclo. No es lo que hace el servidor.

   **Ya está resuelto en código, sin reescribir nada.** Si la respuesta es
   "devuelve menos filas", basta con poner
   `config_robotat.MODO_CONSULTA_POSES = "individual"`: el cliente pasa a
   consultar marcador por marcador, y la oclusión de uno afecta sólo a su
   agente. El default es `"lote"` (una petición con los N marcadores, lo que
   hace el código de referencia) hasta tener la respuesta. El costo del modo
   individual es N veces más ida y vuelta por tick: con la latencia medida
   contra el simulador es asumible, pero hay que medirlo en el laboratorio
   antes de dejarlo fijo. Ambos modos están probados.
2. **¿En qué unidades vienen las posiciones?** (§C1 lo resuelve midiendo,
   pero preguntarlo ahorra la medición.)
3. **¿Dónde está el origen del marco del laboratorio y hacia dónde apuntan
   sus ejes?** (§C2.)
4. **¿Hay una frecuencia máxima de consulta recomendada?** Desde la
   decisión de §S3, el lazo consulta a **10 Hz** (una vez por decisión, no
   por tick) — igual sirve saberlo, por si el plan de contingencia de esa
   sección hiciera falta.
5. **¿Existe algún corte de emergencia centralizado** (de alimentación o de
   red) para los cinco robots a la vez? Ver §S1.

### Prueba pendiente: censo de los 5 pololus

**Todavía NO hecha.** Barrer los robots **1 a 5** y confirmar, para cada
uno, las dos mitades de la cadena por separado:

- **puerto de ruedas** — ¿responde `192.168.50.10N:9090`? (hoy el robot 2 da
  `TimeoutError`, confirmado también desde MATLAB, así que es del robot y no
  del cliente);
- **marcador** — ¿su ID devuelve pose real o el placeholder de ceros de la
  pregunta 1?

Las dos mitades fallan de forma independiente, y hoy vimos las dos: el robot
2 tiene marcador caído *y* puerto muerto, mientras que el robot 1 tenía el
marcador perfecto y lo reportábamos como invisible por un bug nuestro (el
saludo del servidor, §199). Un censo de una sola pasada evita volver a
diagnosticar de a uno.

Sirve además para responder si el `--robot N` de `sesion_robotat.py` resuelve
solo el marcador correcto en los cinco casos, que es justo lo que la
correspondencia fija `marcador_fijo_de_robot()` afirma y sólo está
verificada para el robot 1.

Estado del censo de marcadores al 2026-08-25 (parcial, un solo momento —
NO es el censo de la prueba, que además necesita los puertos de ruedas):
trackeados 1, 7, 10, 12, 61, 63; en placeholder 2, 3, 4, 5, 6, 8, 9, 11,
62, 71. Ojo que el **71** es la meta que usa `laboratorio11.m`.

---

## 7b. §11 — La herramienta de sesión

El tiempo de laboratorio es para **capturar**, no para analizar. Todo se
escribe a disco y cada etapa emite un veredicto automático.

```bash
python sesion_robotat.py --sesion calibracion    # etapas 0-5, un robot
python sesion_robotat.py --sesion politica       # un robot con la política
python sesion_robotat.py --etapa 3               # repetir una sola etapa
python sesion_robotat.py --sesion politica --simulador   # ensayo sin hardware
```

Cada sesión lee lo que midió la anterior desde `calibracion_medida.json` y
**se niega a correr** si falta un parámetro. Una etapa no corre si la
anterior no dio OK, salvo con `--forzar`, que lo avisa. Las salidas van a
`resultados_sesion/AAAAMMDD_sesion-X_etapaN_*.csv` **sin sobrescribir nunca**
(sufijo `_02`, `_03`, …).

### Etapas de calibración

| # | Qué hace | ~min |
|---|---|---|
| 0 | conexión, validación de 20 poses, `force_stop`. Aborta todo si falla | 5 |
| 1 | correspondencia marcador↔robot: **opcional**, chequeo de seguridad — ver abajo | 5 |
| 2 | marco y escala: 2 posiciones medidas con cinta → escala, rotación y traslación por ajuste de similitud; detecta milímetros | 10 |
| 3 | rumbo: avance recto, α por `atan2` del desplazamiento neto vs. rumbo reportado; contrasta con `marker_offsets` del lab | 10 |
| 4 | latencias: 4a percepción (200 consultas), 4b actuación (5 escalones) | 10 |
| 5 | marcador ocluido: registra los bytes **literales** de la respuesta | 5 |

**Etapa 1 — DOS tipos de marcador, uno fijo y uno suelto.** Confirmado por
el operador (2026-08-21/22): los marcadores **sueltos** (el de meta, por
ejemplo) son pegatinas que se colocan a mano y no conservan su posición.
Los marcadores **montados en el chasis de cada robot** son distintos: son
fijos y permanentes — **robot N trae siempre el marcador N**, confirmado
para robots 1–16 (`config_robotat.marcador_fijo_de_robot`). Verificado con
datos reales del robot 2 (giró el marcador 2, ningún otro).

Por eso la etapa 1 **ya no es un paso obligatorio de la secuencia**: el
marcador de un robot se resuelve directo (`id_robot` → mismo número), sin
girar nada. Sigue disponible como chequeo de seguridad opcional —por
ejemplo antes de usar un robot nuevo, o si algo no cierra— y para eso
escanea varios candidatos en **un solo giro** (peticiones individuales
sobre una única conexión persistente — no en lote, un candidato sin
marcador no debe arruinar la lectura de los demás; tampoco una conexión
nueva por candidato, ver el hallazgo de abajo).

```bash
python sesion_robotat.py --sesion calibracion --etapa 1 --robot 2   # opcional
```

⚠ **Caso sin resolver: robot 0.** `marcador_fijo_de_robot` rechaza
`id_robot=0` porque necesitaría marcador "0", inválido para el protocolo
(`min(agents_ids) > 0`). Confirmado por el operador: la numeración humana
arranca en 1, así que el robot "0" del software no se usa. El swarm por
defecto de `config_robotat.MAPEO_AGENTES` usa robots 1–5, no 0–4.

⚠ **`offset_heading_rad` SÍ sigue sin sobrevivir entre sesiones** (a
diferencia de `id_marcador`, que ya no está en esa categoría). Depende de
cómo está montada la constelación sobre el chasis; se mantiene el criterio
conservador de remedirlo cada sesión hasta confirmar si también es tan
estable como el ID. `aplicar_a_config()` se niega a confiar en un
`offset_heading_rad` medido en fecha distinta de hoy: la sesión de
política/enjambre lo trata como sin verificar. Volver a medirlo hoy
(etapa 3) limpia la marca sola; `--forzar` lo saltea bajo tu
responsabilidad.

```bash
python sesion_robotat.py --sesion calibracion --etapa 1 --robot 2
# o con un rango explícito:
python sesion_robotat.py --sesion calibracion --etapa 1 --robot 2 --candidatos 1,2,3,4,5,71
```

Si sobra tiempo, **repetir las etapas 3 y 4** en vez de avanzar: dos o tres
repeticiones dicen si las mediciones son estables entre corridas.

Dos honestidades incorporadas en las etapas:

* La **etapa 2 con 2 puntos** tiene residuo 0 *por construcción*, y lo dice:
  ese residuo no valida nada. Con 3 puntos o más el RMS sí es informativo.
* La **etapa 4b** descuenta la latencia de percepción **y** el tiempo
  puramente geométrico de recorrer el umbral de 3 mm (60 ms a 0.05 m/s). Si
  el retardo resultante queda por debajo del doble del período de muestreo,
  la etapa declara *"no resoluble"* en vez de reportar un número dudoso.

### Sesión de política: barrido progresivo de régimen

Responde la pregunta abierta de §C4b. Escalones y su justificación:

| factor | v efectiva | pico rpm | por qué está |
|---|---|---|---|
| 0.20 | 0.062 m/s | 73 | ≈ el peor caso del lab (70.4 rpm) y su `v0_lin` = 0.06 |
| 0.30 | 0.093 | 110 | salto ×1.5 |
| 0.40 | 0.124 | 146 | salto ×1.33 |
| **0.55** | 0.171 | **200** | **exactamente el tope operativo del lab** |
| 0.75 | 0.233 | 274 | salto ×1.36 |
| 1.00 | 0.310 | 365 | caja completa; 91 % del límite del protocolo |

⚠ Con el aborto por rpm en 200 (el default), **los escalones desde 0.55
pueden abortar por diseño**. Si abortan, es dato, no falla; para pasarlos
hay que subir `--rpm-aborto` deliberadamente.

**Veredicto por escalón**, automático y explícito:

* `ESTABLE` — seguimiento ≥ 0.70 y oscilación ≤ 0.25
* `MARGINAL` — seguimiento ≥ 0.40 y oscilación ≤ 0.45
* `INESTABLE` — por debajo de eso, o abortado
* `SIN DATOS` — distancia comandada < 2 cm: el escalón no alcanza para
  juzgar nada, y decirlo es distinto de declarar inestabilidad

El seguimiento se mide por **distancias acumuladas** (recorrido real /
recorrido comandado), no por cociente paso a paso: a velocidad baja el
desplazamiento por decisión es de ~1 mm, del orden del ruido de la captura.

**Abortos automáticos**: rpm > umbral, robot fuera del área, antigüedad de
pose por encima del umbral, o 10 s sin desplazamiento con comando no nulo.
En todos: `force_stop` y salida con el motivo impreso.

**El entregable es el CSV**: por paso de decisión guarda pose transformada,
las 24 dimensiones de la observación, acción nominal / tras escape /
ejecutada, factor total aplicado, rpm por rueda, estado del escape y del CBF,
y marcas de tiempo.

---

## 8. Agenda sugerida de la primera sesión

Con un solo robot encendido. Casi todo lo ejecuta la herramienta de §11.

**Sesión 1 — calibración (~45 min de las 2 h)**

```bash
python sesion_robotat.py --sesion calibracion
```

0. Conectividad y parada (etapa 0). Si no da OK, no sigue nada.

   ⚠ **No uses `ping` para diagnosticar.** El servidor de poses habla TCP en
   el puerto 1883 y los robots TCP en el 9090; `ping` usa ICMP, que es otro
   protocolo y que se bloquea o se ignora por defecto en muchos hosts.
   `ping` que falla mientras TCP funciona es una combinación normal, y
   perseguir ese falso negativo cuesta tiempo de laboratorio. Si hace falta
   un chequeo previo al script, que sea de TCP:

   ```bash
   python -c "import socket; s=socket.create_connection(('192.168.50.200',1883),3); print('poses OK'); s.close()"
   ```

   (`Test-NetConnection <ip> -Port 1883` sirve igual: mirá
   `TcpTestSucceeded`, no `PingSucceeded`.)
1. (opcional) Correspondencia marcador↔robot (etapa 1) — el marcador de
   cada robot se resuelve directo (robot N → marcador N, confirmado para
   1–16), así que sólo hace falta correrla como chequeo si algo no cierra
   o para un robot nuevo.
2. Marco y escala (etapa 2): tener cinta métrica y dos posiciones marcadas
   en el piso ANTES de empezar.
3. Rumbo (etapa 3): dejar ~30 cm libres por delante.
4. Latencias (etapa 4).
5. Marcador ocluido (etapa 5): contesta la pregunta 1 de §7.
6. **§C4 geometría de rueda**: medir con calibre; no lo hace el script.
7. Con tiempo restante: **repetir las etapas 3 y 4**, no avanzar.
8. Prueba de parada: arrancar `lanzar_robotat.py`, matarlo con Ctrl-C y
   confirmar que el robot frena (ejercita `finally`/`atexit`).
9. Prueba de arranque: dejar el robot pegado a la pared a propósito y
   confirmar que **se niega a arrancar** y lo nombra.

**Sesión 2 — política, un robot**

```bash
python sesion_robotat.py --sesion politica
```

Resuelve el régimen de operación (§C4b) con el barrido progresivo. Mirar los
primeros 5 s de rampa: si algo va en la dirección equivocada, se ve al 25 %
de velocidad y da tiempo a abortar.

**Sesiones 3+ — enjambre y evaluación**

Su diseño depende de lo anterior: el régimen que salga del barrido fija las
velocidades del enjambre, y el modo de consulta que salga de la etapa 5 dice
si cinco agentes pueden consultarse de a uno sin perder frecuencia. El
dispatcher las reconoce y avisa que están pendientes.

---

## 9. Qué quedó probado sin hardware, y qué no

**Probado sin hardware (165 pruebas, todas pasando):**

* formato en el cable de los dos protocolos, incluido el endianness;
* orden de ruedas, con prueba de mutación;
* conversión de unidades y detección de saturación;
* cuaternión→heading por `atan2`, verificado contra una construcción
  independiente desde Euler, con roll y pitch no nulos, y en la singularidad
  de pitch = 90° donde `q2eul` sólo emitiría un warning;
* validación defensiva: NaN, ceros, posiciones absurdas, cuaternión no
  unitario, robot volcado, respuesta truncada, respuesta malformada;
* pérdida de marcador en los tres modos plausibles;
* latencia inyectada, medida y reportada;
* caída de la mocap → fin del lazo → parada;
* pose vencida → freno de ese agente;
* `detener_todo` con un enlace caído: frena al resto, informa, y el caído
  sigue andando;
* robot que no acepta conexión → no se arranca;
* `reposicionar()` lanza `NotImplementedError`;
* el verificador de mapeo, contra un mapeo correcto, uno cruzado y un robot
  inerte;
* el chequeo geométrico de arranque, con cada condición inválida inyectada
  por separado —agente sin pose, fuera de arena, pegado a cada uno de los
  cuatro muros, dos robots encimados— y contra el simulador de punta a
  punta;
* la rampa de arranque: factor exacto, transición a velocidad plena,
  desactivación explícita, y que escalar no cambia la dirección;
* el modo de consulta individual: con un marcador ocluido, sólo su agente
  se queda sin pose;
* lazo cerrado: se comanda por CBOR y se lee el efecto por JSON;
* **el `CoordinadorEnjambre` completo —política PPO, filtro CBF,
  comportamiento de escape, métricas— corriendo contra el simulador sin
  Webots por ningún lado**, con reinicio de episodio sin teletransporte y
  parada final verificada;
* la tasa de consulta de poses (§S3): exactamente 1 round-trip real por
  decisión (no 10), verificado contra el `CoordinadorEnjambre` real
  corriendo 8 decisiones; que `reiniciar()` fuerza una consulta inmediata;
  y el veredicto de presupuesto de ciclo, con latencia inyectada suficiente
  para dispararlo y suficiente para no hacerlo.

**NO probado — necesariamente pendiente hasta tener hardware:**

* que el servidor real hable el formato que se relevó del código MATLAB;
* qué devuelve realmente con un marcador ocluido (pregunta 1 de §7);
* las unidades y el marco reales (§C1, §C2);
* el offset de heading real (§C3);
* la geometría real de los robots (§C4);
* el mapeo marcador↔robot real (§C5);
* **toda la dinámica**: derrape, retardo del actuador, zona muerta de los
  motores, descarga de batería. El simulador usa la misma cinemática ideal
  que el env, así que **nada de lo probado acá dice nada sobre el gap
  sim-to-real**. Lo único que se validó es el código de interfaz.

---

## 10. Cómo se conecta con el coordinador

`CoordinadorEnjambre` acepta los tres adaptadores por constructor. Sin
argumentos construye los de Webots y se comporta **exactamente** como antes
(es la ruta que produce los CSV de los Exp A–H); con adaptadores inyectados,
el mismo lazo corre fuera de Webots:

```python
coord = CoordinadorEnjambre(
    fuente=fuente, canal=canal, entorno=entorno,
    n_agentes=5, timestep_ms=10,
)
```

Dos detalles que importan:

* **El nombre del CSV codifica todo lo que distingue una corrida**: número de
  agentes, modelo, flags, entorno, σ y retardo. Antes dependía sólo de N y de
  los flags, así que dos configuraciones distintas escribían el mismo
  archivo — una corrida con σ=10 mm pisó el CSV de σ=0 y sólo se detectó al
  comparar columnas. Los CSV ya citados en la tesis **conservan su nombre
  viejo y ninguna corrida nueva los toca**: quedan congelados como
  artefactos. Las nuevas salen como
  `lote_multi_5agentes_cbf_escape_robotat_s0_r0.csv`.
* **El teletransporte se consulta, no se atrapa.** El coordinador mira
  `entorno.soporta_reposicionar` antes de llamar. Tragar el
  `NotImplementedError` haría indistinguible "este entorno no teletransporta"
  de "el teletransporte falló".

### Dos errores que las pruebas encontraron

Ambos son del tipo que no falla, sólo se comporta mal:

1. **Sello de tiempo clavado.** La fuente de poses sellaba cada medición con
   un contador que nunca avanzaba, así que la antigüedad crecía linealmente
   con el tick: a los 20 s el coordinador creía estar decidiendo con poses de
   hace 20 s. Se ve en el log como
   `[sync] Decisión con pose vieja: antigüedad=195 ticks`. El reloj lo instala
   ahora `EntornoEjecucionRobotat`, que es quien cuenta los ticks. Hay una
   guardia de regresión en `PruebaLazoDeControlCompleto`.
2. **Alarma de parada espuria.** Tras un cierre limpio, el `atexit` volvía a
   llamar `detener_todo()` sobre sockets ya cerrados e imprimía la alarma de
   "cortar alimentación a mano". El canal distingue ahora un cierre con
   detención confirmada de una imposibilidad de hablarle a un robot — que es
   la situación que sí debe gritar.
