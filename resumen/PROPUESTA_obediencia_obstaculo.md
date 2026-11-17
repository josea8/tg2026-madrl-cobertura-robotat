# Verificación de obediencia del obstáculo: falso positivo y arreglo propuesto

**Estado:** APLICADA el 2026-10-02, con OK de José (respaldo `demo_obstaculo_movil_respaldo_20261002_preObediencia.py`; la 2.ª confirmación corrió con este código y PASA). El texto de abajo es la propuesta tal como se aprobó; ver la nota de aplicación al final.
- Toca `demo_obstaculo_movil.py`, congelado para la Fase 0 (decisión de José, 2026-10-02).
- Después de aplicarla hay que volver a correr el conjunto de confirmación.

## 1. Qué pasó

En la campaña final, 1 de las 486 corridas de las dos campañas se abortó por un falso positivo:
- corrida: `conf_tomas`, `toma_05_s420105`, τ = 0.45 s, con rampa;
- motivo: "el obstáculo NO SE MUEVE: 16.5 s con orden de marcha y v medida 0.000 m/s";
- es una corrida del conjunto de confirmación.

**El obstáculo sí se movía.** En las decisiones 209–211, v̂ ≈ (−0.049, −0.003) m/s y x pasó de 1.454 a 1.444 m. El lazo tuvo un **hipo**:
- entre las decisiones 211 y 212 pasaron **0.374 s**;
- los cinco agentes quedaron con la pose vencida ("frenando por pose vencida");
- la corrida acumuló 956 ticks atrasados;
- corrían 6 simulaciones en paralelo y, además, los servidores MCP de Inventor se lanzaban solos.

`FuentePosesConObstaculo.velocidad_obstaculo()` busca una muestra de entre 0.05 y 0.35 s de antigüedad. Con un hueco de 0.374 s no hay ninguna, y la función devuelve **(0, 0)**. Es un "no sé" disfrazado de "quieto". `SupervisorObstaculo._verificar_obediencia` lo lee como "orden de marcha y no se mueve" y aborta en la primera decisión, sin pedir que se sostenga.

**La barrera no se ve afectada.** El término de velocidad usa `s = max(0, n·v̂, n·v_cmd)`, y con v̂ = 0 queda la velocidad comandada, que es la que anticipa.

**Importa para el laboratorio:** el 30-09 ya se observó el "hipo" del lazo (5 retrocesos falsos). Con este defecto, un hipo en la L2 abortaría la toma con un diagnóstico falso ("¿rueda trabada?").

## 2. Arreglo propuesto

1. `velocidad_obstaculo()` devuelve **`None` cuando no hay estimación**: menos de dos muestras, o ninguna en la ventana. Sólo da 0 cuando la medición dice que está quieto. Quien la usa decide qué hacer con `None`:
   - la barrera: v̂ = 0, o sea, se queda con v_cmd, como hoy;
   - la patada: no la termina por movimiento;
   - la traza: celda vacía.
2. `_verificar_obediencia`:
   - se **saltea** si no hay estimación;
   - exige que la condición ("en marcha y |v̂| < 0.01" o "parado y |v̂| > 0.02") se cumpla en **5 decisiones seguidas con estimación válida**, además de los 1.5 s de orden sostenida;
   - cualquier decisión sin estimación, o fuera de la condición, reinicia la cuenta.
3. La desobediencia real se sigue detectando: un obstáculo trabado da v̂ válida y ≈ 0 en todas las decisiones, y aborta a los 1.5 s + 0.5 s.

**Pruebas nuevas**, en `test_demo_obstaculo_movil.py`, que es un archivo de esta fase:
- un hueco de 0.4 s en la historia → `None`, sin aborto;
- un obstáculo trabado → aborta igual;
- un obstáculo que no frena → aborta igual.

## 3. Qué cambia en las corridas

**Nada, salvo donde la verificación disparó:**
- con una muestra en la ventana, la función da exactamente lo mismo que hoy;
- la verificación sólo cambia de veredicto cuando hoy habría abortado.

Disparó 1 vez en 486 corridas. Igual, como el código está congelado y el veredicto lo da la confirmación, se propone volver a correr **el conjunto de confirmación completo**: 116 corridas, ~20 min.

## Nota de aplicación (2026-10-03)

- **Diferencia con el punto 3 de §2:** la cuenta de 5 decisiones seguidas acumula también dentro de la ventana de 1.5 s. Un obstáculo trabado aborta a los **1.5 s**, como antes, no a los 1.5 s + 0.5 s. El arranque lento no gana tolerancia.
- **Verificación adversarial, con dos verificadores independientes:**
  - la barrera recibe exactamente el mismo v̂, bit a bit en 300 000 historias simuladas;
  - el predictor, el escape y el freno no consumen v̂;
  - `None` nunca llega a la aritmética;
  - en 60 000 secuencias, la obediencia nueva sólo aborta donde abortaba la vieja, en la misma decisión o después.
- **Otros cambios en el mismo archivo**, que no tocan la barrera ni la validez:
  - la réplica fuera de línea de la regla de 10 s pasó a la regla arreglada;
  - la traza deja v̂ vacío sin estimación;
  - hay una columna nueva, `obst_decisiones_sin_estimacion_v`.
  - Además, `correr_fase0_obstaculo.py` cambió en 2 líneas: el `None` en el disparo de las nominales.
  - Detalle en el §7.2 del reporte.
