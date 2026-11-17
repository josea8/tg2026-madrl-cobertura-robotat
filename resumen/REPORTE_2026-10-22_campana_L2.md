# Campaña L2 con el obstáculo móvil: preparación, cierre (a3) y primeras sesiones (08-10 al 21-10)

**Qué es:** la continuación del reporte del 07-10 (colocación automática).
- El 08-10 José decidió que la L2 deja de ser sólo una demo y pasa a ser una **campaña de medición** como la evaluación del 30-09: tomas medidas en el Robotat, réplica pareada en simulación y análisis fijado antes de la primera toma. El video sale de las mismas tomas.
- Este reporte cubre del 08 al 21-10:
  - lo que se construyó y auditó antes del laboratorio;
  - el cierre (a3) de la réplica;
  - el chequeo previo de la PC;
  - la campaña descartada del 16-10;
  - la campaña vigente, `L2_obstaculo_2`, creada el 21-10.

**La campaña `L2_obstaculo_2` está ABIERTA.** Este reporte no da ninguna cobertura de sus tomas, y el zip tampoco:
- la consola de la toma no la muestra;
- las tablas de tomas de las sesiones de campaña (`sesiones/`) van sin la columna `cobertura_aoi` (los originales quedan intactos). Sólo traen cobertura las tablas del (a3) (réplica del 10-10 de episodios del 30-09, sin obstáculo), las del 30-09 y las del ensayo 1e (en el simulador): ninguna es una toma de la campaña.

El análisis fijado corre después del cierre y de la réplica.

**Datos crudos:** `REPORTE_2026-10-22_campana_L2_datos.zip`. El script `scripts/verificar_cifras_campana_l2_20261022.py` recalcula desde los crudos, o coteja contra el archivo de donde sale, cada cifra de este reporte, y comprueba que el texto la diga igual. Lo principal que no cubre está en el §11.

**Fuera de este reporte:** el Exp Q (obstáculos móviles en el entorno de Python, 19-10) se trabajó en otra sesión. Tiene su entrada en la bitácora y sus verificadores en `experimentos/expQ_obstaculos_moviles/`.

---

## 1. Resumen

1. **La campaña quedó construida y auditada antes del laboratorio (08 al 10-10):**
   - el libro (`campana_obstaculo.py`) y el modo campaña de la demo;
   - el plan de análisis fijado, con su script y un verificador independiente;
   - la réplica con obstáculo;
   - el criterio de seguridad de José.

   Con los archivos que hoy están congelados, las 13 suites dieron **556 pruebas OK** el 17-10. El ensayo 1e de referencia llegó a META, con el verificador independiente en **106/106**.
2. **El cierre (a3) de la réplica NO PASA:** media Δ −0.00252, IC95 [−0.01052, +0.00549] contra ±0.00827.
   - Lo deciden dos episodios en direcciones opuestas.
   - Ante las mismas observaciones, la pila nueva decide bit a bit igual que la del 30-09 en los tres episodios revisados.
   - José decidió seguir con la réplica de la campaña: el NO PASA se declara, y su IC95 queda como salvedad de la comparación descriptiva con el 30-09 (§4).
3. **Chequeo previo de la PC** antes de cada sesión del laboratorio y de cada lanzamiento de la réplica: enchufada, ahorro de energía apagado, el mismo plan y modo de Windows, y sin Chrome, ChatGPT, OMEN ni el servidor de Inventor (§5).
4. **16-10: la campaña `L2_obstaculo` se creó y se descartó.**
   - El robot 6 dejó de girar bien, el 3 no respondió en la red y entró el 2.
   - Después, el operador notó que el Robotat estaba mal calibrado.
   - Resultado: 7 intentos, 3 corridas, todas no válidas, y 0 incluidas. **Ninguna de sus tomas entra en el documento** (§6).
5. **17-10: José aprobó el enjambre 1, 5, 8, 2, 9 y un bloque nuevo de semillas** (la implementación eligió el 422000). Con eso se volvieron a probar los congelados (§7).
6. **21-10: se creó `L2_obstaculo_2`.** Al terminar el día iba en **17/100 intentos, 7/50 incluidas y 14 corridas, con 0 tomas con contacto y 0 frenos de respaldo.** Sigue abierta (§8).
7. **Ritmo:** 7 incluidas en 17 intentos (41 %).
   - A ese ritmo, el mínimo de 30 llega cerca del intento 73, y los 100 intentos dan unas 41: **a ese ritmo puntual, la meta de 50 no se alcanza.** Con sólo 17 intentos el ritmo es incierto, y no se descartan ni INCOMPLETA ni META (§8.4).
   - De los 10 intentos no incluidos, 6 se perdieron por el seguimiento (marcadores congelados, antigüedad de pose y una repetición simultánea), 2 por los robots y 2 quedaron interrumpidos con Ctrl+C.
8. **La parada "ABORTO POR EL OBSTÁCULO" de la toma 15 no la causó el robot 4.** En el paso 203 se repitieron a la vez, bit a bit, los 6 marcadores, justo después de un hueco de 309 ms en el lazo (§8.5).
9. **Declaraciones para el documento** (§9):
   - La L0 que habilitó la campaña corrió sin `CHEQUEO OK`.
   - Ninguna de las 7 tomas incluidas salió de una sesión con un chequeo propio.
   - No consta si se recalibró Motive entre el 16 y el 21-10.
10. **Decisiones pendientes de José** (§10). Entre otras:
    - qué hacer con el ritmo;
    - si se repite la L0 con el chequeo en OK;
    - el arreglo de un cierre de sesión que no muestra su causa.

---

## 2. Decisiones de José del período

Los textos están en `decisiones_jose/` del zip, tal como llegaron.

| Fecha | Decisión | Dónde quedó |
|---|---|---|
| 08-10 | La L2 pasa a campaña de medición como el 30-09; el video sale de las mismas tomas; la Fase A sigue fuera. | `PROPUESTA_campana_L2_obstaculo.md` (aprobada), plan y protocolo |
| 08-10 | Ocho decisiones y cuatro ajustes al plan. Entre ellos: la mitad de lo comandado sólo si es ≥ 0.20 m; tope de 100 intentos; un "no" en la pausa termina sólo la sesión; cierre (a1) + (a3), sin (a2); la configuración del día se registra y no bloquea; corrección declarada con motivo; la L0 OK antes de abrir. | `campana_obstaculo.py`, plan §1–§2 y §7 |
| 09-10 | Criterio de seguridad: la campaña se cierra **sola** con dos tomas corridas con contacto (< 0.15 m entre centros medidos). Cualquier otro cierre, con comando y motivo escrito. | Plan §2, libro, protocolo |
| 10-10 | Sin distancia medida al obstáculo no hay contacto con el obstáculo (los pares de agentes sí cuentan). La regla del (a3) se aprueba con máquina libre y sin cambiar el margen. El cierre (b) exige rumbo ≤ 1e-6 rad y mandos idénticos. | Plan §2 y §7, `CIERRE_B_RUMBO_MAX_RAD` |
| 10-10 | (a3) NO PASA declarado con su diagnóstico. Su IC95 es la cota de cuánto puede diferir la réplica nueva de la del 30-09. La réplica corre con la PC limpia. Descriptivos post hoc. Se aprueban las dos convenciones del §7. | Plan §6, §7 y §10 |
| 10-10 | "Sin Omen" al pie de la letra. La laptop enchufada y con el mismo modo de energía. El chequeo de PC limpia antes de cada sesión del laboratorio. | `PROTOCOLO_L0_L2.md`, sección del chequeo |
| 17-10 | "se arpueba el 2 y para las semillas un bloque nuevo". | `config_robotat.py`, `campana_obstaculo.py`, plan y protocolo |

El número 422000 lo eligió la implementación; José aprobó "un bloque nuevo". El descarte de `L2_obstaculo` (16-10) fue decisión del operador en el laboratorio y no tiene una ratificación de José registrada.

---

## 3. Antes del laboratorio: lo que se construyó y cómo se probó (08 al 17-10)

**Lo que se construyó** (todo en `controllers/coordinador_enjambre/`, salvo el plan):
- **`campana_obstaculo.py`**, el libro de la campaña (`campana.json` + `libro.csv`, que sólo crece):
  - reserva la semilla de cada intento antes de colocar;
  - cuenta las incluidas;
  - arrastra la cadena de frenos;
  - aplica el criterio de seguridad;
  - congela 22 archivos por sha256: el código que carga una sesión, el modelo, el plan, el análisis, el verificador y una huella de `config_robotat.py` sin la calibración del día.
- **El modo campaña de `demo_obstaculo_movil.py`:**
  - exige la L0 OK;
  - rechaza `--factor`, `--decisiones`, `--colocacion` y `--forzar`;
  - anota toda toma que corrió, también la cortada a mitad y la que dispara una regla de parada, antes de la pausa;
  - escribe los CSV en forma atómica y el crudo antes que el libro;
  - **sólo cambia el registro, el modo campaña y la L0.** Comprobado hoy por AST contra `demo_obstaculo_movil_respaldo_20261008_preCampana.py`:
    - cambian `sesion_demo`, `_colocar_toma_automatica`, `main`, `sesion_l0`, `l0_habilita` y `escribir_csv`, y hay 5 funciones nuevas;
    - quedan idénticos la barrera (`FiltroConObstaculo`, `CoordinadorConObstaculo`), `SupervisorObstaculo`, `correr_toma`, `validez_demo`, `regla_de_parada`, `aplicar_regla_de_parada` y `estimar_error_offset`;
    - `sesion_robotat.py` no se toca desde el 02-10.

    Es la condición de José del 08-10 para comparar con el 30-09.
- **`tesis/PLAN_ANALISIS_campana_L2.md`, `analizar_campana_l2.py` y `verificar_campana_l2.py`:**
  - principal: brecha de cobertura hw − réplica, pareada por toma, con IC95 t;
  - sensibilidades;
  - seguridad;
  - costo del obstáculo;
  - el 30-09, sólo descriptivo.
- **`replica_con_obstaculo.py`:** la misma pila del laboratorio contra el simulador con retardo cero; el 4 no se simula: se reproduce su trayectoria medida, decisión por decisión.
  - **Cierre (a1):** sin obstáculo, decide bit a bit igual que la pila del 30-09 ante las mismas observaciones.
  - **Cierre (b):** en tiempo real, error 0.0 m, rumbo 2.2e-16 rad y mandos idénticos en las tomas probadas.

**Revisiones adversariales** (según la bitácora):

| Fecha | Qué se revisó | Resultado |
|---|---|---|
| 08-10 | el libro, el registro, el análisis, el plan y el protocolo | ~45 hallazgos |
| 09/10-10 | el criterio de seguridad | dos verificaciones |
| 09/10-10 | la réplica | 10 confirmados y 2 refutados |
| 10-10 | auditoría final | 27 hallazgos: 26 confirmados y 1 refutado |
| 10-10 | la decisión del (a3) | ronda 1: 18 hallazgos, 8 confirmados y 10 refutados; ronda 2: 13, 7 y 6 |
| 10-10 | el chequeo de la PC | 12 hallazgos, 3 confirmados y 9 refutados |
| 17-10 | las semillas | 11 hallazgos, 7 confirmados y 4 refutados |

Lo confirmado se corrigió en cada caso. Entre lo más serio:
- un Ctrl+C en la pausa perdía una toma con contacto;
- una toma cortada a mitad no contaba para el criterio;
- `config_robotat.py` quedaba entero fuera del bloqueo;
- el chequeo de PC limpia no podía salir vacío.

**Pruebas del 17-10**, con los archivos de `L2_obstaculo_2`, en `pruebas/suites_20261017/`:

| Suite | Pruebas | Suite | Pruebas |
|---|---|---|---|
| campaña | 45 | diagnóstico | 28 |
| análisis | 34 | mapa | 46 |
| réplica | 31 | respuesta | 2 |
| demo | 97 | retroceso | 26 |
| estancamiento | 5 | robotat | 67 |
| sesión | 121 | integración | 51 |
| cerrojo | 3 | **total** | **556, 13/13 OK** |

**Ensayo 1e de referencia** (`ensayo_campana_20261017_092424`, en el simulador, por el mismo camino que el laboratorio):
- META;
- 6 intentos, 5 incluidas y un corte con Ctrl+C reanudado;
- semillas 422000–422005;
- registro sin problemas;
- análisis y verificador con código 0; **verificador independiente 106/106**;
- verdad mínima agente–obstáculo 0.3265 m y agente–agente 0.2303 m.

**Congelados:** los 22 sha256 de hoy son iguales a los del 1e y a los de `L2_obstaculo_2` (22/22): las suites y el 1e corrieron con el código que corre la campaña.

---

## 4. El cierre (a3) de la réplica: NO PASA

**La regla** (aprobada por José el 10-10):
- 12 episodios del 30-09: la última aparición válida de cada semilla.
- 3 repeticiones nuevas por episodio.
- Δ = media nueva − media del 30-09.
- PASA si el IC95 t de la media de Δ queda dentro de ±δ, con δ = 0.00827: el desvío dentro de episodio agrupado de la réplica del 30-09, con 98 gl.

**El resultado** (`replica_campana/cierre_a3_20261010_b/`):
- 36/36 corridas válidas, de una sola pila;
- E = 12;
- media Δ −0.00252, IC95 [−0.01052, +0.00549]: **el límite inferior queda fuera.** NO PASA.
- El recálculo independiente de este reporte reproduce al bit el JSON del cierre.

**El diagnóstico** (`diagnostico_20261010/`):
- **Lo deciden dos episodios.**
  - s05 ep 2, Δ = −0.0404: el 30-09 dio 0.326, 0.329 y 0.332; las reps nuevas, 0.322, 0.277 y 0.268. Dos cayeron en un modo bajo, y se separan más de 5 cm hacia el paso 207.
  - s05 ep 8, Δ = +0.0129: el 30-09 dio 0.404, 0.410 y **0.377**; las nuevas, 0.412, 0.410 y 0.409. El Δ sale de la rep baja del 30-09.
  - De los otros 10, 9 tienen |Δ| ≤ 0.002; el décimo, s02 ep 12, tiene Δ = −0.0040.
- **La decisión es la misma.** Ante las mismas observaciones (las poses hw del 30-09), la pila nueva decide bit a bit igual que la del 30-09 en s05 ep 2, s05 ep 8 y s02 ep 12: 2500/2500 filas.
- **El ruido entre repeticiones**, en los mismos 12 episodios:
  - Desvío mediano por episodio: 0.0013 en las nuevas y 0.0015 en las del 30-09 de los mismos 12 episodios.
  - El máximo nuevo (0.0287, s05 ep 2) supera al del 30-09 en esos episodios (0.0175, s05 ep 8).
  - En todos los episodios, las reps nuevas se separan más de 1 mm entre los pasos 1 y 111.
- **Tiempos:** el ciclo p95 medio fue 25.3 ms, contra 20.8 ms en las mismas 36 corridas del 30-09. No se puede separar si viene de la pila o de la carga de la máquina: el a3 corrió antes de que existiera el chequeo de la PC.
- **Si las coberturas nuevas y las del 30-09 fueran intercambiables:**
  - la regla daría PASA con probabilidad 0.615;
  - una |media Δ| como la observada aparece con probabilidad 0.261;
  - el Wilcoxon de los 12 Δ da p = 1.000, con mediana Δ = +0.00009.

**Lectura:** no aparece un error de la réplica. El NO PASA lo explican dos episodios caóticos y la potencia de la regla con 12 × 3. El margen no cambió.

**Decisión de José (10-10):**
- sigue la réplica de la campaña;
- el NO PASA se declara con el diagnóstico, sin repetir el a3. José lo aprobó con la frase "el mismo ruido entre repeticiones que el 30-09". Esa frase salía de la comparación de la bitácora (máximo 0.029 contra 0.031), que enfrentaba los 12 episodios nuevos con los 50 del 30-09. En los mismos 12, la mediana es 0.0013 contra 0.0015 y el máximo 0.0287 contra 0.0175 (arriba). La redacción queda pendiente (§10);
- su IC95 [−0.0105, +0.0055] es la cota de cuánto puede diferir la réplica nueva de la del 30-09, y entra como salvedad de la comparación descriptiva con el 30-09;
- el resultado principal no depende de eso.

**Registro aparte:** el primer lanzamiento del a3 (`cierre_a3_20261010/`) se cortó a las 2 corridas porque el plan, que está en la pila, se editó mientras corría. Fue el 10-10, antes de crear la campaña de medición: sólo había libros de ensayo en el simulador, y el plan admitía cambios antes de la primera toma. La guarda de la réplica funcionó, y ese lanzamiento quedó SIN VEREDICTO.

---

## 5. Chequeo previo de la PC

Es un bloque de PowerShell común (`documentos/chequeo_previo_pc.ps1`, igual al del protocolo). Imprime:
- la corriente y el ahorro de energía;
- el plan y el modo de Windows (referencia: Equilibrado `381b4222…` con "Mejor rendimiento" `ded574b5…`);
- los procesos prohibidos: Chrome, ChatGPT, OMEN (con `OmenCap`, `OverlayHelper`, `OmenInstallMonitor` y `SystemOptimizer`) y el servidor de Inventor, que es un proceso hijo de la app de Claude.

Termina en `CHEQUEO OK` o en `CHEQUEO FALLA: no lanzar`, y la salida se pega en la bitácora. Para que no haya servidor de Inventor, el protocolo pide cerrar la app de Claude o desactivar su conector de Inventor.

**Chequeos registrados en el período:**

| Fecha y hora | Resultado | Qué fallaba |
|---|---|---|
| 10-10 15:07:38 | FALLA | OMEN y un servidor de Inventor, con la app de Claude abierta (era la referencia; no se lanzó nada) |
| 16-10 20:17:20 | FALLA | dos procesos de OMEN que quedan vivos al cerrar la bandeja, y dos servidores de Inventor |
| 16-10 20:26:17 | **OK** | |
| 21-10 13:11:44 | FALLA | a batería, 6 procesos de OMEN y ChatGPT |
| 21-10 13:12:37 | FALLA | a batería y 6 procesos de OMEN |
| 21-10 13:25:56 | **OK** | |
| 21-10 13:32:16 | **OK** | |

**Desajuste del protocolo:** según el protocolo, cerrar OMEN desde la bandeja cierra `OmenCommandCenterBackground.exe` y `HP.OMEN.VirtualCamHelper.exe`.
- El 16-10 quedaron vivos después de cerrar la bandeja, y hubo que detenerlos como administrador.
- El 21-10 no consta que se cerrara la bandeja. Estaban vivos en los chequeos de las 13:11:44 y las 13:12:37, y ya no existían cuando el comando de administrador los buscó (`consola/consola_20261021_1315.txt`).

---

## 6. Laboratorio del 16-10: L0 del 4 y la campaña descartada

**L0 del robot 4.** La hora es la del final, cuando se escriben los archivos.

| Hora | Veredicto | Detalle |
|---|---|---|
| 19:48:27 | FALLO | marcador 4 congelado; 0 arranques |
| 19:49:02 | FALLO | marcador 4 congelado; 0 arranques |
| 19:55:42 | FALLO | 10/10 arranques; error radial máximo 6.39 cm, contra < 5 cm; offset −0.34° (370 pares) |
| 20:29:10 | **OK** | 10/10 arranques; error radial máximo 2.31 cm; offset −0.14° (370 pares) |

- **El FALLO de las 19:55 es de la colocación.**
  - El 4 arrancó a 7.6 cm del punto de arranque (1.50, 0.90), dentro de la tolerancia de ±8 cm. Su error radial inicial era de −7.3 cm, y lo corrigió despacio, a 0.4–0.6 cm/s.
  - Para José: la tolerancia de colocación de la L0 (±8 cm) es más ancha que el tope radial (5 cm, sin los 2 s de enganche).
- **Sesgo del seguimiento:** las cuatro L0 con traza (16 y 21-10) muestran el mismo sesgo estacionario hacia adentro, de unos −2 cm: la media desde el arranque 3, sin los 2 s de enganche, queda entre −1.93 y −2.05 cm según la L0. Es del seguimiento, no de una colocación puntual.

**Campaña `L2_obstaculo`**, creada a las 20:31:08:
- Sesión 1 (enjambre con el 6):
  - intento 1: parada en la colocación, porque los robots 8 y 9 habían quedado juntos de antes;
  - intento 2: interrumpido; el 6 no avanzaba.
- Corrección declarada a las 20:42:59: entra el 3 en lugar del 6.
- Sesión 2: se cerró a los 11 s porque el robot 3 no respondía en la red.
- Corrección declarada a las 20:48:51: entra el 2 en lugar del 3.
- Sesión 3 (intentos 3–7):
  - intentos 3 y 6: corridas, no válidas por marcador congelado (el 5 y el 8, cerca de la pared);
  - intento 5: corrida, no válida por antigüedad de pose;
  - intento 4: sin correr;
  - intento 7: interrumpido.
- **Cerrada a las 21:07:22 con motivo escrito:** "Campaña DESCARTADA para el documento: el Robotat estaba mal calibrado".
- Estado final: 7 intentos, 3 corridas, 0 incluidas, 0 tomas con contacto. Semillas 421000–421006.

---

## 7. 17-10: composición, semillas y congelados

- **Enjambre:** 1, 5, 8, 2, 9, con el 4 de obstáculo. El 6 no gira bien y el 3 no responde.
  - Riesgo del 2: su offset es el de la tabla (+89.74°), nunca medido.
  - En septiembre se le congelaba el marcador.
- **Semillas:** `SEMILLA_BASE` = 422000, un bloque que no aparece en ningún resultado anterior. `Campana.semilla()` usa la `semilla_base` de la cabecera de cada campaña, así que `L2_obstaculo` conserva su 421000. Una prueba nueva lo comprueba.
- **Congelados:** entre `L2_obstaculo` (con los congelados de su creación) y `L2_obstaculo_2` difieren 5 de 22:
  - el plan;
  - `analizar_campana_l2.py`;
  - `campana_obstaculo.py`;
  - `demo_obstaculo_movil.py`;
  - la huella de `config_robotat.py`.

  Los otros 17 son iguales.
- **Pruebas y 1e:** se repitieron con estos archivos (§3); la referencia del chequeo de congelados pasó al 1e del 17-10.

---

## 8. Laboratorio del 21-10: la campaña `L2_obstaculo_2`

### 8.1 Antes de crearla

**L0 del 4:**

| Hora | Veredicto | Detalle |
|---|---|---|
| 12:55:45 | FALLO | "no se pudo conectar (servidor de poses): timed out" |
| 12:59:01 | FALLO | "pose perdida en el arranque 3", en (2.00, 1.80). Esa zona tuvo huecos de decisión y poses repetidas también en la L0 siguiente. |
| 13:09:48 | **OK** | 10/10 arranques; error radial máximo 2.15 cm; offset −0.27° (362 pares) |

- **Calibración del mocap con el robot 1:** la etapa 0 dio OK, y los dos intentos de la etapa 2 fallaron en el punto 1 sin guardar ningún valor de calibración.
  - El marco aplicado el 21-10 es el mismo del 16-10: escala 1.0167, rotación +0.49°, traslación (1.506, 1.256).
  - `calibracion_medida.json` se escribió a las 13:03:26 (la etapa 0 guardó `id_robot` = 1), y a las 13:04:28 y 13:05:17 (el FALLO de cada intento de la etapa 2), pero no cambió el marco.
  - **No consta si se recalibró Motive** entre el 16-10, cuando la campaña se descartó por "Robotat mal calibrado", y el 21-10.
- **Chequeo de la PC:** los dos de las 13:11 y 13:12 dieron FALLA (§5). **La L0 de las 13:09:48, la que habilitó la campaña, corrió sin `CHEQUEO OK`.** No consta ningún chequeo antes de las L0. El primero del día, a las 13:11:44 (1 min 56 s después de terminar esa L0), dio a batería, con OMEN y con ChatGPT. La bitácora recomendó repetirla; no se repitió.

**Creación:** `L2_obstaculo_2` a las 13:17:55:
- hw, robot y marcador 4;
- meta 50, mínimo 30, tope 100;
- `semilla_base` 422000;
- chequeo de congelados en "IGUAL a lo probado".

### 8.2 Sesiones

| Sesión | Abre | Cierra | Hora de fin | Intentos | Motivo del cierre |
|---|---|---|---|---|---|
| `L2_20261021_131821` | 13:18:21 | 13:18:22 | 13:50 | — | "fin de la sesión" (falló la revisión previa de marcadores, que no imprime la causa; por la duración, < 2 s, fue el 1 o el 5, no el 8) |
| `L2_20261021_132110` | 13:21:10 | 13:21:13 | 13:50 | — | ídem; compatible con el 8 congelado del chequeo de las 13:2x, sin confirmar |
| `L2_20261021_132617` | 13:26:17 | 13:28:48 | 14:10 | 1 | interrumpida (Ctrl+C) |
| `L2_20261021_133237` | 13:32:37 | 13:32:49 | 14:15 | — | robot 8 sin respuesta en la red |
| `L2_20261021_133444` | 13:34:44 | 13:45:40 | 14:15 | 2–7 | regla de parada en la colocación; pausa "detenida" |
| `L2_20261021_134819` | 13:48:19 | 14:03:36 | 14:15 | 8–17 | interrumpida (Ctrl+C), para terminar el día |

**El cierre que no muestra su causa:** antes de abrir los enlaces, la sesión revisa los 6 marcadores. En modo campaña, si alguno está congelado o sin respuesta, la sesión termina sin imprimir el porqué y el libro anota sólo "fin de la sesión". Así se cerraron las dos primeras sesiones. Un chequeo de sólo lectura hecho después, a las 13:2x, dio el marcador 8 congelado. La revisión hace 15 lecturas de 0.05 s por marcador en el orden 1, 5, 8, 2, 9 y 4, así que la primera sesión, que duró menos de 2 s, no alcanzó a revisar el 8.
- Arreglarlo toca `demo_obstaculo_movil.py`, que está congelado. Queda propuesto como corrección declarada, y no se aplicó.
- Mientras tanto, la bitácora recomienda correr, antes de cada sesión, un comando de una línea que revisa los marcadores.
  - En las consolas consta una sola vez, antes de la sesión de las 13:32, con los 6 vivos.
  - No consta antes de las sesiones de las 13:34 y 13:48, que dieron las 7 incluidas.
  - Antes de la de las 13:26, la bitácora anota los marcadores vivos sin decir con qué se revisaron.

### 8.3 Intentos

| Intento | Semilla | Estado | Válida / incluida | Motivo | d_min obstáculo (m) |
|---|---|---|---|---|---|
| 1 | 422000 | interrumpida | — / no | el robot 1 no avanzaba en la colocación (diagnóstico probable: sin potencia en los motores) | — |
| 2 | 422001 | corrida | sí / **sí** | | 0.3212 |
| 3 | 422002 | corrida | no / no | marcador 8 congelado en (2.62, 2.70) | 0.5648 |
| 4 | 422003 | corrida | sí / **sí** | | 0.3153 |
| 5 | 422004 | corrida | no / no | agente 4 (robot 9): recorrió el 48 % de lo comandado | 0.3050 |
| 6 | 422005 | corrida | no / no | antigüedad de pose (marcador 9 repetido en (0.17, 0.25)) | 0.3161 |
| 7 | 422006 | parada en la colocación | no / no | contacto de colocación entre los robots 1 y 2 (el 1 no avanzaba) | — |
| 8 | 422007 | corrida | sí / **sí** | | 0.3011 |
| 9 | 422008 | corrida | sí / **sí** | | 0.3395 |
| 10 | 422009 | corrida | sí / **sí** | | 0.3054 |
| 11 | 422010 | corrida | no / no | marcador 9 congelado en (0.41, 2.34) | 0.3366 |
| 12 | 422011 | corrida | no / no | antigüedad de pose (marcador 1 en la zona interior) | 0.3158 |
| 13 | 422012 | corrida | sí / **sí** | | 0.3285 |
| 14 | 422013 | corrida | sí / **sí** | | 0.3870 |
| 15 | 422014 | corrida | no / no | ABORTO POR EL OBSTÁCULO (repetición simultánea, §8.5); pausa: "siguió" | 0.3762 |
| 16 | 422015 | corrida | no / no | marcador 9 congelado en (2.83, 2.77) | 0.3333 |
| 17 | 422016 | interrumpida | — / no | Ctrl+C en la guía, con el marcador 9 congelado | — |

- **Libro:** semilla = 422000 + intento − 1 en todos los intentos, 0 tomas con contacto, 0 frenos de respaldo y 0 pares de agentes a < 0.15 m.
- **d_min con el obstáculo:** entre 0.3011 y 0.5648 m en las 14 corridas, y entre 0.3011 y 0.3870 m en las 7 incluidas.
- **El contacto de colocación del intento 7** no cuenta para el criterio de seguridad: es regla de parada de la sesión.
- **Las dos pausas:** en el intento 7 se terminó la sesión, y en el 15 se siguió.

### 8.4 Pérdidas y ritmo

**Los 10 intentos no incluidos, según el libro:**
- **seguimiento, 6:**
  - marcador congelado: 3, 11 y 16;
  - antigüedad de pose: 6 y 12;
  - repetición simultánea: 15;
- **robots, 2:** el 5 (el robot 9 no siguió el comando) y el 7 (el contacto de colocación con el robot 1 detenido);
- **interrumpidos con Ctrl+C, 2:**
  - el 1, con el robot 1 sin moverse;
  - el 17, con el marcador 9 congelado en la guía.

**Ritmo:** 7/17 = 41 %. Al mismo ritmo:
- el mínimo de 30 llega en el intento 30 · 17/7 ≈ 73;
- el tope de 100 da 100 · 7/17 ≈ 41 incluidas;
- la meta de 50 no se alcanza a ese ritmo puntual.

**Con 17 intentos el ritmo es incierto:** el IC95 de Wilson de 7/17 es [0.216, 0.640]. Aplicado a los 83 intentos que quedan (7 + 83 · p), da entre unas 25 y unas 60 incluidas al tope (la sesión se detiene al llegar a la meta de 50). Ese rango incluye INCOMPLETA (< 30) y META (≥ 50).

El veredicto de la campaña será MÍNIMO o META según lo que se alcance, o INCOMPLETA si no llega a 30 (plan §2).

### 8.5 La toma 15: el aborto por el obstáculo

Lo que muestran los crudos (`20261021_134819_L2_decisiones.csv` y `_obstaculo.csv`):
- Los intervalos entre pasos venían en ~100 ms: 100.9 ms y 100.9 ms.
- Entre los pasos 200 y 201 hubo un hueco de **308.7 ms**.
- Después, los pasos 201 → 202 → 203 vinieron a **9.7 ms** y **11.1 ms**.
- En el paso 203, **los 5 agentes y el obstáculo repiten bit a bit** la fila del paso 202.
  - Es el único paso de las dos sesiones con los 5 agentes repetidos.
  - No hay ninguno con 3 o 4 repetidos a la vez.
  - Lo más probable es que la consulta, 11 ms después de la anterior, recibiera el mismo cuadro del mocap.
- La supervisión del obstáculo aborta ante una sola fila repetida bit a bit, y eso disparó la regla de parada.
- El robot 4 estaba sano. Contestar "s" fue correcto. No se cambió nada.

### 8.6 Congelamientos de marcadores

Son rachas de pose repetida bit a bit en los CSV de decisiones.

- **Cerca de la pared** (sin contar la repetición simultánea de la toma 15):
  - robot 8 en (2.62, 2.70), (0.19, 0.85), (0.47, 0.32) y (2.72, 0.17);
  - robot 9 en (0.17, 0.25), (0.41, 2.34) y (2.83, 2.77).
- **Zona interior** (> 1.2 m de las paredes): x entre 1.456 y 1.548, y entre 1.213 y 1.281.
  - Se congelaron dos marcadores distintos: el 1 en las tomas 12 y 14, y el 9 en la 8. Todas las posiciones están a menos de 9.9 cm entre sí.
  - El obstáculo estaba a 0.70–0.81 m, así que no tapaba la vista.
  - Apunta a un lugar (un punto ciego de cámaras) más que a un marcador. El mapa de la sonda en esa zona lo decidiría.
- **Recuperación:** las rachas de la zona interior duraron 1–6 pasos.
  - Todas volvieron durante el retroceso, en 0.1–0.6 s (el código las marca "recuperada"), salvo la de la toma 12, que terminó por antigüedad de pose.
  - Eso no muestra que el retroceso las recuperara: las de un solo paso volvieron en la consulta siguiente.

### 8.7 Tiempo del lazo y enlaces

- **Huecos del lazo** (intervalos del obstáculo dentro de cada toma):
  - sesión de las 13:34: 3 de 1698 > 150 ms y 1 > 250 ms (270 ms);
  - sesión de las 13:48: 6 de 3743 > 150 ms y 1 > 250 ms (309 ms, el de la toma 15).
- **Ciclo p95 medio por toma:** 23.4 ms y 23.6 ms.
- **De la consola** (`consola/consola_20261021_1409.txt`):
  - ticks que no alcanzaron su plazo: 1540 y 3041;
  - latencia de poses p95: 16.8 ms y 17.8 ms. El 16-10 había sido de 5.4 ms y 5.0 ms;
  - poses rechazadas por inclinación: 233 y 5.
- **Enlaces** (consola):
  - el robot 9 se cayó a las 13:40:59, durante la guía del intento 6, y volvió a los 63.0 s. Fue **después** del intento 5, que se cerró a las 13:40:28;
  - el robot 1 se cayó a las 13:44:35, en la pausa, mientras se le cambiaba la batería, y volvió a los 56.2 s.

---

## 9. Declaraciones para el documento

1. **Chequeo de la PC por sesión**, según la bitácora y las consolas:

   | Sesión o paso | ¿`CHEQUEO OK` propio antes? |
   |---|---|
   | L0 16-10 de las 19:48, 19:49 y 19:55 | no consta |
   | L0 16-10 de las 20:29 | sí (20:26:17) |
   | creación y 3 sesiones de `L2_obstaculo` | no (último OK: 20:26:17) |
   | L0 21-10 de las 12:55, 12:59 y **13:09 (habilitante)** | **no**: no consta ningún chequeo antes. El primero, a las 13:11:44, posterior a las tres, dio a batería, con OMEN y ChatGPT |
   | creación de `L2_obstaculo_2` (13:17:55) | **no** (último chequeo: FALLA de las 13:12:37) |
   | sesiones de las 13:18 y 13:21 | no (cerradas en 1–3 s) |
   | sesión de las 13:26 (intento 1) | sí (13:25:56) |
   | sesión de las 13:32 | sí (13:32:16) |
   | sesión de las 13:34 (intentos 2–7) | compartido: el OK de las 13:32:16, 148 s antes de abrir |
   | sesión de las 13:48 (intentos 8–17) | **no**: el último OK, 963 s antes |

   - Ninguna de las 7 incluidas salió de una sesión con un chequeo propio: la 2 y la 4, de la sesión del OK compartido; la 8, 9, 10, 13 y 14, de la sesión sin chequeo.
   - **Indicio, no prueba,** de que la app de Claude estaba abierta: la última escritura de la bitácora (un agregado) fue a las 13:47:39, 40 s antes de abrir la sesión de las 13:48. La hora sale del mtime de su respaldo (`derivados/mtimes_bitacora.txt`). El 16-10 también hubo escrituras poco antes de las tres sesiones (10, 84 y 52 s). El protocolo admite, en lugar de cerrar la app, desactivar su conector de Inventor, y eso no consta. Lo declarable es la falta de `CHEQUEO OK`.
   - Los huecos del lazo no difieren entre la sesión con OK compartido y la sin chequeo (§8.7).
2. **La L0 habilitante corrió sin `CHEQUEO OK`.** El protocolo pide la L0 OK con el chequeo antes de crear la campaña.
3. **Recalibración:** `L2_obstaculo` se descartó por "Robotat mal calibrado". El 21-10 se aplicó el mismo marco del mocap, y no consta una recalibración de Motive. Las dos L0 OK (16 y 21-10) se midieron con ese marco.
4. **`L2_obstaculo` está descartada:** ninguna de sus tomas entra en el documento. Si se cita, es como campaña descartada, con su motivo.
5. **El (a3) NO PASA**, declarado con el diagnóstico del §4. Su IC95 es la salvedad de la comparación descriptiva con el 30-09. La frase sobre el ruido entre repeticiones está pendiente de José (§10).
6. **Correcciones a la bitácora** que salieron al recalcular para este reporte (la bitácora no se editó: es sólo de agregado):

   | Lugar | Decía | Correcto |
   |---|---|---|
   | a3, 10-10 | de los otros 10 episodios, "8 de ellos ≤ 0.002" | 9 de los 10 tienen \|Δ\| ≤ 0.002; s02 ep 12 tiene −0.0040 |
   | a3, 10-10 | "Desvío mediano 0.0013 en las dos réplicas"; desvío máximo nuevo 0.029 contra 0.031 del 30-09 | las dos cifras del 30-09 son de sus 50 episodios. En los mismos 12: mediana 0.0013 contra 0.0015 y máximo 0.0287 contra 0.0175 |
   | pruebas, 17-10 | "campaña 44/44, más las 2 pruebas nuevas" | una sola prueba nueva: campaña 45 y total 556 |
   | L0, 16-10 | "7.3 cm hacia adentro, dentro de la tolerancia de ±8 cm" | los 7.3 cm son el error radial; la tolerancia rige sobre la distancia al punto de arranque, que fue 7.6 cm |
   | intento 5, 21-10 | el enlace del 9 "se había caído a las 13:40:59" | se cayó después, durante la guía del intento 6 |

   **No son errores, sino otra base o clasificación:**
   - La bitácora dice que de los 10 no incluidos "7 fueron del seguimiento", porque reparte por causa los dos interrumpidos: el 17, cortado con el marcador 9 congelado, va al seguimiento, y el 1, con el robot 1 sin potencia, a los robots. El §8.4 los separa según el estado del libro. Las dos cuentas son compatibles. Lo único corregible de esa frase, "el 9 con el enlace caído", es la fila del intento 5.
   - Su zona interior "(1.42–1.55, …), el 1 en las tomas 12, 13 y 14" y el 8 en "(2.76, 0.20)" incluyen lo que la consola mostró en la guía y en la colocación: el 1 en (1.42, 1.24) en la guía de la toma 13, y el 8 en la colocación de la toma 12. En los CSV de decisiones, x 1.456–1.548, con el 1 en las tomas 12 y 14 (§8.6).
   - "5 poses rechazadas por inclinación" es la cifra de la consola para toda la sesión, colocación incluida (§8.7); las tomas suman 3.

---

## 10. Pendiente

**Decisiones de José:**
1. **Ritmo:** al ritmo puntual actual, la meta de 50 no llega (con el IC del ritmo no se descartan ni INCOMPLETA ni META, §8.4). Opciones posibles: más sesiones hasta el tope, el mapa de la sonda en la zona interior y en las esquinas antes de seguir, o aceptar el MÍNIMO. Los criterios de parada no cambian sin un desvío declarado.
2. **¿Repetir la L0 con `CHEQUEO OK`** antes de la próxima sesión, como pide el protocolo?
3. **Recalibración de Motive:** confirmar con el laboratorio si se hizo entre el 16 y el 21-10.
4. **El cierre que no muestra su causa:** corrección declarada entre sesiones (`--corregir-campana`), con sus pruebas. Toca un archivo congelado.
5. **El modo de energía de referencia** (hoy Equilibrado + "Mejor rendimiento"), y si el chequeo debe escribir solo en la bitácora (sería un script nuevo).
   - La bitácora del 10-10 fijó que, si José elegía otra referencia, se cambiaba antes de la primera sesión. Ese plazo pasó el 16-10, y todos los chequeos del 16 y del 21-10 leen esta.
   - Cambiarla ahora rompe dentro de `L2_obstaculo_2` el "siempre con el mismo modo" del 10-10. Si se cambia, se declara desde qué sesión rige.
6. **La tolerancia de colocación de la L0** (±8 cm) frente al tope radial (5 cm). Toca un archivo congelado: `TOL_COLOCACION_OBSTACULO_M` está en `demo_obstaculo_movil.py`, y la misma constante entra en el chequeo del obstáculo al arrancar cada toma. Cambiarla exige una corrección declarada entre sesiones, con sus pruebas, o dejarla para después del cierre.
7. **El ruido entre repeticiones en el diagnóstico del (a3).** Lo aprobado, igual que el plan congelado (§7), dice "el mismo ruido entre repeticiones que el 30-09". En los mismos 12 episodios:
   - la mediana es 0.0013 contra 0.0015;
   - el máximo es 0.0287 (s05 ep 2) contra 0.0175 (s05 ep 8).

   ¿Se mantiene "el mismo ruido" o pasa a "del mismo orden en la mediana, con un máximo nuevo mayor en el episodio que decide"? Cambiar el texto del plan exige una corrección declarada.
8. **Defecto abierto, detectado el 08-10:** `main --simulador` aplica al simulador la calibración guardada del laboratorio (offset de rumbo ~92°, escala 1.0167).
   - No afecta a la campaña: el ensayo 1e y `replica_con_obstaculo.py` imponen la identidad.
   - El primer 1e (`ensayo_campana_20261008_195824`) gastó sus 15 intentos por eso.
   - Corregirlo toca un archivo congelado.

**Protocolo** (no está congelado; con el OK de José):
- el paso de OMEN de la bandeja (§5);
- el offset del 4, que ya está confirmado por tres L0 (−0.34°, −0.14° y −0.27°);
- el comando de una línea que revisa los marcadores antes de cada sesión.

**Laboratorio:** seguir `L2_obstaculo_2` con el mismo comando, desde el intento 18 (semilla 422017). Antes de cada lanzamiento, también al relanzar tras un corte:
1. la app de Claude cerrada;
2. `CHEQUEO OK`;
3. los 6 marcadores vivos.

Hay que cuidar la batería y la conexión del robot 1, y los enlaces de los robots 8 y 9.

**Después del cierre:**
1. la réplica, con `CHEQUEO OK` por lanzamiento y nunca en paralelo con el hardware;
2. el análisis fijado y el verificador independiente;
3. el reporte final con el zip. Ese reporte lleva:
   - el (a3) NO PASA con su diagnóstico;
   - los descriptivos post hoc rotulados: el p95 del ciclo de la réplica y, en la variante sin obstáculo, las tomas con desvío entre repeticiones > 0.01, contra 6 de 50 del 30-09;
   - el chequeo de cada sesión y de cada lanzamiento.

---

## 11. Datos y verificación

`REPORTE_2026-10-22_campana_L2_datos.zip` contiene:
- **`documentos/`:**
  - este reporte;
  - el plan, el protocolo y la propuesta como están hoy;
  - el extracto de la bitácora desde el 08-10;
  - el bloque del chequeo de la PC.
- **`decisiones_jose/` y `consola/`:** los textos pegados por el operador, copiados literales.
- **`campanas/`:** `libro.csv` y `campana.json` de las dos campañas.
- **`sesiones/`:** las L0 del 16 y 21-10, y las sesiones L2 de las dos campañas (tomas sin `cobertura_aoi`, decisiones y obstáculo).
- **`replica_campana/`:** el (a3) que vale, con su diagnóstico, y el interrumpido.
- **`referencia_3009/`:** los episodios y la réplica del 30-09 que usa la regla del (a3).
- **`ensayo_1e/`:** el ensayo de referencia del chequeo de congelados.
- **`pruebas/`:** las 13 suites del 17-10 y el log del 1e.
- **`derivados/`:** `mtimes_bitacora.txt`, la hora de modificación de cada respaldo de la bitácora, tomada el 22-10 con `os.stat`. No es un crudo de la campaña; de ahí sale el indicio del §9.1.
- **`codigo/`:** los 20 archivos congelados de la carpeta del coordinador (el plan va en `documentos/`), más `config_robotat.py` (su huella sin la calibración también está congelada), `calibracion_medida.json`, `replica_con_obstaculo.py` y, en `codigo/respaldos/`, el respaldo de la demo previo a la campaña, para la comparación por AST.
- **`scripts/`:** el verificador.
- **`sha256_paquete.txt`:** el sha256 de cada archivo del paquete, salvo esta lista.

Para verificar, desde la carpeta descomprimida. Hace falta Python 3 con numpy y scipy, que sólo usa el (a3); el script no importa código del proyecto. Se probó con Python 3.13, y las probabilidades por permutación del (a3) usan un generador con semilla:

```text
python scripts/verificar_cifras_campana_l2_20261022.py . documentos/REPORTE_2026-10-22_campana_L2.md
```

El verificador recalcula con código propio:
- el libro;
- los intervalos y las repeticiones de los CSV;
- las L0;
- el (a3) completo, con δ, Δ e IC95;
- las pruebas;
- el 1e;
- los sha256 de los congelados contra las dos cabeceras;
- la comparación por AST de la demo contra su respaldo previo a la campaña.

Comprueba que cada cifra aparezca igual en este texto, y también que ninguna tabla de tomas de `sesiones/` traiga cobertura.

**Algunas cifras no las recalcula, sino que las coteja contra un texto:**
- las de la consola, contra `consola/`;
- las de las revisiones adversariales y las citas de la bitácora, contra su extracto;
- las horas del indicio del §9.1, contra `derivados/`;
- del 1e, el veredicto y las distancias contra `resumen_ensayo.json`, y el 106/106 contra su log;
- el 2500/2500 del §4, contra la salida del diagnóstico. Para reproducirlo hacen falta `test_replica_con_obstaculo.py`, `simulador_robotat.py` y los CSV de decisiones del 30-09, que no van en el zip.

**No cubre, entre otras cosas:**
- el offset del 2 (§7);
- el "Qué fallaba" de los chequeos del 10 y del 16-10, y el desajuste de OMEN (§5);
- la columna "Motivo del cierre" (§8.2);
- los motivos de los intentos 1 y 17 (§8.3), que vienen de la bitácora y de la consola, no del libro;
- el "13:2x" del chequeo de sólo lectura de marcadores (§8.2);
- el "~92°" y los "15 intentos" del defecto de `--simulador` (§10);
- que `sesion_robotat.py` no se toca desde el 02-10 (§3), que sale de la fecha del archivo.
