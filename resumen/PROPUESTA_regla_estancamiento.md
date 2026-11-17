# Regla "sin desplazamiento por 10 s": diagnóstico y arreglo propuesto

**Estado:** APLICADA el 2026-10-02, con OK de José (sha256 de `sesion_robotat.py` 87fb924c…, respaldo `sesion_robotat_respaldo_20261002_preEstancamiento.py`). El texto de abajo es la propuesta tal como se aprobó; las referencias de línea son de antes del cambio (ver la nota de aplicación al final).
**Análisis:** `primerafase_webots/controllers/coordinador_enjambre/analizar_regla_estancamiento.py`, de sólo lectura.
- Salidas: `resultados_demo_obstaculo/regla_estancamiento_resumen.txt` y `regla_estancamiento_episodios.csv`.

## 1. El defecto

La regla está en `_correr_episodio`, `sesion_robotat.py:2957-2965`:

```python
for f in filas:
    ag = int(f["agente"])
    if ag in gestor.en_retroceso:
        continue            # retrocede a ciegas: no se le exige nada
    if (abs(f["v_ejecutada"]) > 0.02
            and ahora - t_mov.get(ag, ahora) > 10.0):
        abortado = True
        motivo = f"agente {ag} sin desplazamiento por 10 s"
        break
```

`t_mov[ag]` es el instante del **último desplazamiento** de más de 2 mm entre decisiones (`:2849`, `:2851`, `:2891`), no el instante en que se le **ordenó** moverse. Supongamos un agente que estuvo quieto y sin orden más de 10 s, y al que de pronto se le ordena moverse. La regla corta la toma en la **primera** decisión con |v| > 0.02, antes de que el retardo de actuación (0.45–0.85 s) le deje moverse.

Es exactamente la situación de la demo del obstáculo: agentes quietos que tienen que huir cuando el obstáculo se acerca. En la Fase 0 se reprodujo en el simulador con el caso guionado "quieto de espaldas": el corte llegó en la decisión 101, con el obstáculo encima.

## 2. ¿Cortó algún episodio real? (punto a)

| | episodios | válidos | cortes reales (motivo en el CSV) | réplica de la regla actual | exposición máxima, regla actual | ídem, regla arreglada |
|---|---|---|---|---|---|---|
| 11-09 | 19 | 5 | 0 | 0 | 5.11 s | 4.11 s |
| 26-09 | 19 | 10 | 0 | 0 | 5.00 s | 4.00 s |
| 30-09 (5 sesiones) | 57 | 50 | 0 | 0 | 5.00 s | 4.00 s |
| **pedidas** | **95** | **65** | **0** | **0** | **5.11 s** | **4.11 s** |
| extra (05-09, 22-09 ×2, 24-09) | 39 | 11 | 0 | 0 | 2.50 s | 2.50 s |

Cómo se mide la **exposición**: es el máximo, sobre las decisiones con orden, de (t − t_mov), es decir, cuánto le faltó a la regla para cortar. La réplica usa el período **real** de cada episodio (`duracion_s / decisiones`), porque la regla usa el reloj de pared, que no está en el CSV.

Con el período nominal de 0.1 s da lo mismo en las tres fechas pedidas. La excepción es la sesión del 05-09, la del reloj desbocado: ahí el lazo corrió a ~70 Hz, con 0.013–0.016 s por decisión, y el nominal infla el tiempo unas 7 veces. Con el nominal, las **dos** reglas "cortarían" 3 de sus válidos; con el período real, ninguna. Es un artefacto del nominal, no de la regla.

**Ningún episodio real se cortó por esta regla.** Las exposiciones de ~5 s son todas de episodios **inválidos**, y se cortaron en la decisión 50: un robot que no se movía en absoluto, como el robot 3 con el socket caído el 11-09. Los cortó antes, a los 5 s, `DetectorSeguimiento`, que compara lo recorrido con lo comandado en una ventana de 50 decisiones.

En los **válidos**, la exposición máxima fue **3.2 s**. Por lo tanto, ante una falla real la regla de 10 s nunca fue la protección activa: la falla la atrapa antes el detector de seguimiento.

## 3. El arreglo (punto b)

Se mide desde el **inicio de la orden sostenida**, con margen para el retardo:

```text
t_ref = max(t_mov, t_inicio_orden + 1.0 s)
corta si:  orden sostenida  y  ahora − t_ref > 10 s
```

- **`t_inicio_orden`** es el comienzo del período de orden vigente (|v_ejecutada| > 0.02). El período termina sólo después de **1.0 s seguido sin orden**. Esa histéresis evita que un filtro que parpadea reinicie el reloj y le permita a un robot trabado esquivar la regla.
- **Margen de 1.0 s:** mayor que los 849 ms de arranque a 0.05 m/s medidos el 29-08, que son el peor retardo medido.
- **Sin cambios:** los 2 mm, la exclusión de los agentes en retroceso y el reinicio de `t_mov` al recuperarse de un retroceso.

Cambio concreto en `sesion_robotat.py`:
- dos diccionarios nuevos, `t_orden` y `t_sin_orden`, junto a `t_mov`;
- dos constantes con nombre, `MARGEN_RETARDO_ESTANCAMIENTO_S = 1.0` y `CORTE_ORDEN_ESTANCAMIENTO_S = 1.0`;
- la condición de arriba en lugar de `ahora - t_mov.get(ag, ahora) > 10.0`.

Antes de tocarlo:
- respaldo `sesion_robotat_respaldo_20261002_preEstancamiento.py`;
- el archivo está en **CRLF** y se conserva así.

Las pruebas van en un archivo **nuevo**, `test_regla_estancamiento.py`, con tres casos:
1. el caso de la demo: quieto 12 s y después se le ordena huir → NO corta;
2. el robot trabado: orden sostenida 11.5 s sin moverse → SÍ corta;
3. un filtro que parpadea sobre un robot trabado → SÍ corta.

## 4. ¿Cambia algún válido? (punto c)

**No: 0 de los 50 válidos del 30-09**, ni de los 65 válidos de las tres fechas pedidas, ni de los 11 de las demás. Se verificó con la réplica episodio por episodio y con el período real. En ningún episodio, ni con el período real ni con el nominal, el arreglo corta donde la regla actual no corta.

La lógica del arreglo se probó en la réplica con cuatro casos sintéticos:
- quieto 12 s y después huye → no corta;
- trabado con orden sostenida → corta a los 10.1 s del margen;
- trabado con un filtro que parpadea → corta igual;
- orden cortada 1.5 s → reinicia el reloj.

La primera versión de la réplica tenía un error: tomaba un inicio de orden en t = 0 como "sin dato". Lo detectó esa prueba sintética y se corrigió antes de reportar.

Además, se cumple por construcción. Como `t_ref ≥ t_mov`, la condición nueva implica la vieja: el arreglo **sólo puede quitar cortes, nunca agregarlos**. Lo que hoy no corta, después tampoco.

## 5. Lo que el arreglo no cubre

**Movimiento lento continuo.** "Desplazamiento" sigue siendo un avance de más de 2 mm **entre dos decisiones**. Con el factor 0.40, un agente que se mueve de verdad pero con |v_ejecutada| < 0.05 avanza menos de 2 mm por decisión y no refresca `t_mov`. Si lo sostiene más de 11 s, la regla lo corta igual.

En la demo esto no debería pasar: huir del obstáculo exige ejecutar ≥ 0.05 m/s, que son ≥ 5 mm por decisión. Si se quisiera cubrirlo, el arreglo de fondo es medir el desplazamiento desde un **ancla** (la pose en t_mov) y no entre decisiones consecutivas. No se propone ahora: cambia la semántica de la regla más allá de lo pedido.

**Alternativa considerada: quitar la regla.** El detector de seguimiento ya mide contra lo comandado y fue el que cortó todos los casos reales. Quitarla es más invasivo y no es lo que se pidió; queda como opción.

## Nota de aplicación (2026-10-03)

- **Referencias de línea en el archivo actual:** la regla está en `sesion_robotat.py:2977-3002` (antes 2957-2965), y `t_mov` se actualiza en `:2869`, `:2871` y `:2911` (antes 2849, 2851 y 2891).
- **Verificación adversarial:**
  - el diff contra el respaldo tiene sólo los 4 bloques del arreglo;
  - CRLF 3866/3866;
  - `_correr_escalon` no cambió (mismo hash);
  - un fuzz de 40 000 trazas sobre los fragmentos reales dio 0 cortes nuevos y 0 adelantados: la regla nueva sólo quita cortes.
- **Costo de la histéresis:** un robot trabado con tramos de orden de menos de ~11 s, separados por pausas de ≥ 1 s sin orden, nunca llega al corte de 10 s. En ese caso la protección queda sólo en `DetectorSeguimiento`.
- **Réplicas fuera de línea:** las de `analizar_regla_estancamiento.py` y `demo_obstaculo_movil.py` no reproducen el reinicio `t_mov = ahora` al salir de un retroceso (`:2910-2911`), y usan la columna `en_retroceso` en vez de `gestor.en_retroceso`. Sirven para el diagnóstico, no son la regla.
