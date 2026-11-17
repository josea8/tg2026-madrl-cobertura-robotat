# Campaña de Calibración — Robotat

**Informe de campo · Tesis Mecatrónica UVG**

Del robot 1 calibrado al enjambre de cinco corriendo la política: qué quedó
medido, qué se descubrió del servidor de captura, y qué dice la primera
transferencia sim‑real completa.

| | |
|---|---|
| **Período** | 25 agosto – 3 septiembre 2026 |
| **Informe anterior** | Bitácora de Depuración (22 agosto) |
| **Pruebas** | 182 en verde |

---

## La decisión

> ### El enjambre corre. La garantía de seguridad no se transfiere.
>
> Cinco robots completaron el barrido con la política en **tres corridas
> independientes**. La implementación funciona de punta a punta: seguimiento
> 1.02–1.05, cero salidas de la arena, el presupuesto de ciclo nunca al
> límite.
>
> Pero el margen de pared del CBF —0.18 m, que en simulación no se viola
> nunca— **se viola en el tapete en los cinco escalones y en las tres
> corridas**, con mínimos de 0.128 a 0.198 m. No hay un régimen de velocidad
> donde la garantía se sostenga de forma reproducible. El régimen operativo
> estable y repetible es **factor 0.40** (v ≤ 0.124 m/s).

---

## Lo que quedó listo

### Calibración, secuencia completa

| Etapa | Veredicto | Detalle |
|---|---|---|
| 0 — conexión y parada | ✔ OK | 20/20 poses válidas |
| 1 — correspondencia de IDs | ✔ OK | giro de 58.1° |
| 2 — marco y escala | ✔ OK (28 ago) | residuo RMS 5.6 mm |
| 3 — offset de rumbo | ✔ OK | +92.13° |
| 4 — latencias | ✘ FALLO | retardo de actuación 603 ms |
| 5 — marcador ocluido | ✔ RESUELTA | devuelve pose congelada |

Las cinco banderas de configuración quedaron en `[verificado]`: escala, marco,
rumbo, geometría de rueda y mapeo de IDs.

> **Salvedad de registro.** Los veredictos guardados de las etapas 2 y 3
> figuran como FALLO: son los intentos de recalibración del 3 de septiembre,
> que murieron con el marcador congelado. Los **valores en uso** son los de la
> corrida buena del 28 de agosto, y la traslación lleva un ajuste manual
> (+1.5 en ambos ejes) para corregir el origen centro→esquina. Funciona y está
> validado por las corridas, pero no es una medición limpia de punta a punta.

### Censo del enjambre

| Agente | Robot | Marcador | IP |
|---:|---:|---:|---|
| 0 | 1 | 1 | `192.168.50.101` |
| 1 | 2 | 2 | `192.168.50.102` |
| 2 | 3 | 3 | `192.168.50.103` |
| 3 | 6 | 6 | `192.168.50.106` |
| 4 | 9 | 9 | `192.168.50.109` |

IDs no contiguos. La regla marcador N ↔ robot N se sostiene en los cinco.

> **Lección del censo.** Los marcadores reflectivos son **pasivos**: que Motive
> los vea no dice nada sobre si el robot tiene alimentación. En la primera
> pasada los cinco marcadores estaban vivos y sólo el robot 1 respondía a
> comandos. Las dos mitades fallan independientemente y hay que probarlas por
> separado, siempre.

---

## El enjambre, corriendo

Tres corridas independientes de cinco robots (3 septiembre).

| Métrica | corrida 1 | corrida 2 | corrida 3 | Rango |
|---|---:|---:|---:|---|
| Intervención del CBF | 37.7 % | 37.6 % | 42.7 % | 37.6–42.7 |
| Decisiones con vecino | 44.6 % | 57.2 % | 64.9 % | 44.6–64.9 |
| Máximo factor estable | 0.55 | 0.55 | 0.40 | **0.40 reproducible** |

El CBF es la magnitud más estable entre corridas (media 39.3 %, sd 2.4). El
contacto entre vecinos varía mucho más y depende de cómo se coloquen los
robots al arrancar.

### El margen del CBF, sobre tres corridas

`d_pared` mínima por escalón, contra el margen de 0.18 m que el filtro
debería garantizar:

| Factor | v efectiva | c1 | c2 | c3 | media | Recorrido en 0.45 s |
|---:|---:|---:|---:|---:|---:|---:|
| 0.20 | 0.062 | 0.153 | 0.189 | 0.198 | 0.180 | 2.8 cm |
| 0.30 | 0.093 | 0.163 | 0.150 | 0.148 | 0.154 | 4.2 cm |
| 0.40 | 0.124 | 0.147 | 0.166 | 0.139 | 0.151 | 5.6 cm |
| 0.55 | 0.171 | 0.159 | 0.139 | 0.154 | 0.151 | 7.7 cm |
| 0.75 | 0.232 | — | 0.128 | — | 0.128 | 10.5 cm |

En simulación `d_pared` nunca baja de 0.18 en ningún escalón.

> **Corrección — dos conclusiones que no replicaron.**
>
> **«A factor 0.20 el margen se sostiene» era de una sola corrida.** Ahí dio
> 0.189 m. Con dos corridas más: 0.153 y 0.198. Una de las tres viola el
> margen claramente. **No hay ningún factor en el que la garantía se sostenga
> de forma reproducible.**
>
> **«El sobrepaso escala con la velocidad» es más débil de lo que una corrida
> sugería.** Las medias sí bajan, pero la dispersión entre corridas a un mismo
> factor —4.5 cm en el 0.20— es del mismo orden que la tendencia completa. La
> dirección del efecto se sostiene; su magnitud, no está establecida.
>
> Las dos afirmaciones se hicieron sobre *n = 1*.

### Comparación controlada contra simulación

Mismo código de sesión, mismas posiciones iniciales, mismos factores:

| Métrica | Hardware | Simulación local | Constante `REF_SIM` |
|---|---:|---:|---:|
| Intervención del CBF | 37.6 % | 59.4 % | ~37 % |
| σ de ω (con vecino) | 0.963 | 0.892 | — |
| `v` nominal | 0.310 fijo | 0.310 fijo | — |
| Decisiones con vecino | 57.2 % | 63.7 % | — |
| Salidas de la arena | 0 de 6145 | 0 | — |

> **Corrección — una coincidencia que no lo era.** La tasa del CBF en hardware
> dio 37.6 % y 37.7 %, contra la constante `REF_SIM["cbf"] = "sim: ~0.37"`.
> Eso se leyó como que el hardware reproducía la simulación.
>
> **No se sostiene.** Ese `~0.37` está escrito a mano en el código sin fuente
> documentada, y presumiblemente viene de los experimentos de Webots —otra
> física, otra estructura de episodio, otras condiciones iniciales—. La
> comparación controlada da **59.4 %**. En el tapete el filtro interviene
> *menos* que en simulación, no igual.

### El reparto entre agentes

La asimetría **también aparece en simulación** (CBF por agente de 35.7 % a
72.6 %, sd 12.9 contra 21.3 del hardware): es la política, no los robots.

Y sobre tres corridas, **cuál agente es el atípico cambia cada vez** — el
robot 1 dio 0 %, 36.5 % y 21.4 % de intervención. La asimetría es emergente y
depende de dónde arranca cada uno.

> **La excepción: el robot 2.** Recorrió **6.44 m** y **9.13 m** en las dos
> corridas que abortaron por estancamiento, contra **13.34 m** en la que no,
> mientras sus compañeros recorrían 9–13 m en todas. Es el mismo robot cuyo
> puerto de ruedas daba `TimeoutError` al comienzo de la campaña. Apunta a
> batería. Sin esos dos abortos, las tres corridas habrían llegado a 0.55.

---

## Hallazgos del servidor de captura

### Un marcador perdido devuelve su última pose, congelada

Respuesta a la pregunta abierta del §7 del README. Hay **dos comportamientos**:

| Situación | Respuesta del servidor | ¿Se detecta? |
|---|---|---|
| Marcador nunca trackeado | `[0,−0,0,1,0,−0,0]` | Sí |
| Marcador que se ocluye | última pose, congelada | Sí, por ausencia de jitter |

Medido tapando el marcador: la pose quedó clavada **13.4 s**, 246 lecturas
byte a byte idénticas, y las 366 dieron `pose_valida = 1`. Ninguna validación
de una sola pose puede verlo, y la defensa de antigüedad tampoco, porque mide
desde que *nosotros recibimos* el dato.

**Mecanismo, medido:** el estado viejo vive en el **servidor** y está atado al
**marcador**, no a la conexión.

- mismo socket, intercalados → marc. 1: 1 valor de 8; marc. 9: 8 de 8
- dos conexiones simultáneas al mismo marcador → las dos congeladas
- cerrar y reabrir el socket → mismos bytes

⇒ **Reconectar no sirve. La reacción correcta es abortar.**

**Cómo se detecta:** un marcador trackeado actualiza a **~82 Hz**; diez
lecturas idénticas en 0.2 s es tracking perdido. Implementado como
precondición en las etapas 0, 2, 3 y 5 y en el arranque del enjambre.

### Otros dos comportamientos confirmados

- **El saludo del servidor**: 52 B al conectar que, si no se drenan
  bloqueando, llegan pegados al JSON de la primera consulta y la hacen
  fallar. El síntoma es «marcador sin lectura».
- **Nunca vienen menos filas**: siempre 7 valores. El modo `"lote"` es seguro.

---

## Brecha sim‑real de actuación

```
arranque v=0.05 m/s   848.6 ms   (n=4, 518–1563; 1 de 5 no se movió)
arranque v=0.15 m/s   458.4 ms   (n=5, 331–611)
frenado desde 0.15    452.2 ms   (n=5, 189–679)
```

En `lab_robotat_fisica_multi5.wbt` los motores declaran sólo `maxVelocity 84`:
sin `acceleration` ni `maxTorque`, Webots usa aceleración infinita. **La rueda
simulada alcanza la velocidad comandada instantáneamente.**

El retardo **depende de la velocidad comandada** (848 → 458 ms), así que buena
parte es fricción de arranque, no comunicación. El residuo de ~450 ms a
velocidad operativa no está separado entre inercia real y latencia de canal.

Un comando tardío pesa más que una pose tardía: una pose vieja se descarta, un
comando tardío **ya se ejecutó**.

---

## Geometría del área

El área útil del Robotat, sin bordes, es **4.67 × 3.45 m**; el env es
3.0 × 3.0. **No se escala una en la otra**: haría falta un factor por eje, y
sobre todo **el robot no se encoge con el env** —con factor 0.64 los 0.15 m de
separación mínima entrarían como 0.096 m y la política se creería despejada
estando en colisión—. Se trabaja sobre un cuadrado de 3 × 3 dentro del área
útil, 1:1 en metros.

El servidor entrega **metros**: las `z` de un robot en el piso salen
0.038–0.069, que son los centímetros de alto del chasis con el marcador.

---

## Lo que costó tiempo, y por qué

El patrón se repitió: **una hipótesis plausible tratada como diagnóstico antes
de verificarla.**

- Se atribuyó a hardware —«el marcador 1 no está trackeado»— lo que era la
  carrera del saludo del servidor.
- Se dijo que la política «satura porque está fuera de distribución»; en
  simulación satura igual: va siempre a `v` máxima, y eso es normal.
- Se mandó a revisar Motive cuando alcanzaba con correr el punto de medición
  30 cm hacia adentro del volumen de captura.
- Se afirmó que el CBF del hardware «coincide con la simulación» comparando
  contra una constante de procedencia no documentada.
- Se dio un umbral operativo seguro (factor 0.20) sobre una sola corrida.

En todos los casos el dato que lo desmentía estaba a una medición de
distancia. **Lección metodológica: con n=1 se puede afirmar la dirección de un
efecto, no su magnitud ni su umbral.**

---

## Números citables

| Magnitud | Valor | Cómo se obtuvo |
|---|---:|---|
| Escala de posición | 1.0167 | 4 puntos, residuo RMS 5.6 mm |
| Rotación de marco | +0.49° | misma similitud |
| Offset de rumbo, robot 1 | +92.13° | coincide con la tabla del lab en 1.63° |
| Latencia de percepción | 2.6 ms | p50 de 200 consultas; p95 4.19 ms |
| Frecuencia del servidor de poses | ~82 Hz | tasa real de cambio, muestreo denso |
| Retardo de actuación | ~450 ms | a 0.15 m/s; 848 ms a 0.05 m/s |
| Retardo de actuación en Webots | 0 ms | motores sin `acceleration` |
| Área útil del Robotat | 4.67 × 3.45 m | medida, sin bordes |
| Pose congelada tras oclusión | 13.4 s | 246 lecturas idénticas, todas «válidas» |
| CBF en hardware, 5 robots | 37.6–42.7 % | 3 corridas |
| CBF en simulación local | 59.4 % | mismas condiciones iniciales |
| `d_pared` mínima en hardware | 0.128–0.198 m | margen del CBF: 0.18 m |
| Máximo factor estable | 0.40 | reproducible en 3 corridas |

---

## Lo que queda abierto

**De laboratorio:**

- Rehacer etapas 2 y 3 para que los veredictos queden limpios y la traslación
  sea medida en vez de parcheada (~20 min).
- Cargar o cambiar el robot 2.
- Más corridas: con tres se dan rangos; para un umbral de seguridad harían
  falta más.

**De escritorio:**

- Detección de congelamiento **a mitad** de corrida (sólo está en el
  arranque). Deprioritizado conscientemente.
- La sesión `evaluacion` sigue sin implementar.
- Un fallo intermitente en la batería de integración, visto una vez y no
  reproducido en seis corridas. Sin identificar.

**Ni de laboratorio ni de escritorio — son hallazgos para escribir:** las
violaciones del margen de pared, la asimetría entre agentes y la brecha de
actuación están medidas y explicadas, no «arregladas».

---

*182 pruebas en verde · `test_robotat.py` 55 · `test_integracion_robotat.py`
50 · `test_sesion_robotat.py` 77*
