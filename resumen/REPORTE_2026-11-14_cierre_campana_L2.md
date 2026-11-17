# Cierre de la campaña L2_obstaculo_2: resultado del análisis fijado

**Qué es:** el reporte final de la campaña `L2_obstaculo_2` (L2 con el robot 4 como obstáculo móvil, enjambre de los robots 1, 5, 8, 2 y 9). Cubre:
- el cierre de la campaña (14-11, 00:14:20);
- la réplica de sus 30 tomas incluidas en el simulador (14-11, 00:31–04:31);
- el análisis fijado (`analizar_campana_l2.py`, 14-11, 10:16:47) y su verificador independiente (`verificar_campana_l2.py`);
- las declaraciones obligatorias del plan (§8), el chequeo de la PC de cada sesión y del lanzamiento de la réplica, y los pendientes que quedan.

Continúa a `REPORTE_2026-11-07_campana_L2.md` (versión 13-11), que llegaba hasta el 06-11 con la campaña abierta. De las sesiones solo se repite aquí lo que el análisis o las declaraciones necesitan.

**Decisión de José (13-11):** cerrar la campaña como está, con veredicto MÍNIMO. No se siguió hasta el tope ni se hizo el mapa de la sonda (§2).

**Datos crudos:** `REPORTE_2026-11-14_cierre_campana_L2_datos.zip`. El script `scripts/verificar_cifras_cierre_campana_l2_20261114.py` recalcula desde los crudos, o coteja contra el archivo de donde sale, las cifras de este reporte, y comprueba que el texto las diga igual. Lo que no cubre está en el §13.

---

## 1. Resumen

1. **Veredicto de la campaña: MÍNIMO.** 73 de 100 intentos, 56 corridas y 30 de 50 incluidas. El ritmo fue 30/73 = 41 %, con IC95 de Wilson [0.305, 0.526]. Cerrada el 14-11 a las 00:14:20 por falta de turnos en el Robotat.
2. **Principal (§3 del plan): no hay brecha detectable de cobertura entre el hardware y su réplica.** hw − réplica = −0.0131, IC95 [−0.0292, +0.0029] (n = 30). Con esta precisión, la brecha está acotada, con 95 % de confianza, a |brecha| ≤ 0.0292. **No se afirma equivalencia.** La media del hw (0.3348) queda por debajo de la de la réplica (0.3479); 20 de 30 diferencias son negativas.
3. **Referencias que no deciden:** el Wilcoxon da p = 0.0368 y el bootstrap, [−0.0284, +0.0023]. El IC t contiene el 0 (p = 0.1047). Las sensibilidades B, D y E dan IC95 que contienen el 0; A y C son idénticas al principal porque ninguna toma incluida tiene arranque fuera del soporte ni freno (§5).
4. **Seguridad (§4), durante la toma y sobre poses observadas:** 0 tomas con contacto (< 0.15 m) en las 56 corridas, IC95 de Clopper–Pearson [0.000, 0.064], y **0 frenos de respaldo en las 56 corridas**. La distancia mínima al obstáculo fue 0.2648 m, con mediana 0.3329 m. El hw pasa 0.0302 m más cerca de la pared que su réplica (IC95 [−0.0354, −0.0251]) (§6).
5. **Costo del obstáculo (§5 del plan), en la réplica:** con − sin obstáculo = +0.0077, IC95 [−0.0001, +0.0155]. No hay costo de cobertura detectable: el IC95 contiene el 0 y la estimación puntual es positiva (§7).
6. **Comparación con el 30-09 (solo descriptiva):** la brecha por pares fue +0.0077 y por escenario +0.0123, con IC95 que contienen el 0; la de esta campaña es −0.0131. Son escenarios distintos y no hay inferencia sobre la diferencia. El cierre (a3) dio **NO PASA** (media de Δ = −0.00252, IC95 [−0.01052, +0.00549], margen ±0.00827) y va como salvedad de esa comparación (§8).
7. **La réplica corrió completa (270 corridas, una sola pila), pero no en las condiciones del protocolo.** El operador corrió el chequeo de la PC y no guardó su salida: no consta su resultado. Windows muestra que Chrome y OMEN Command Center estaban abiertos durante toda la réplica y que las primeras 25 corridas empezaron con la laptop a batería. Una corrida quedó no válida, por antigüedad de pose (§4, §10).
8. **Chequeo de la PC de las 30 incluidas:** ninguna sale de una sesión con chequeo propio con salida pegada. Las 18 del 06-11 se declaran como "`CHEQUEO OK` declarado por el operador, sin salida pegada y sin hora" (§10).
9. **Descriptivos post hoc (§9):** el ciclo p95 de la réplica fue 11.64 ms (con obstáculo, τ = 0), 11.31 ms (con obstáculo, τ = 0.45) y 10.28 ms (sin obstáculo) de media. En la variante sin obstáculo, 8 de 30 tomas tienen un desvío entre repeticiones mayor que 0.01 (ddof = 1), contra 6 de 50 el 30-09.
10. **Lo que queda sin resolver** va como salvedades (§11): entre otras, la L0 habilitante sin `CHEQUEO OK`, la recalibración de Motive, el cierre del libro que no muestra su causa y la causa del corte de red del 04-11.

---

## 2. Decisión de José y cierre

**Decisión de José (13-11, `SPEC_cierre_campana_L2.md`):** "Cierro la campaña `L2_obstaculo_2` como está: 73/100 intentos y 30/50 incluidas, con veredicto MÍNIMO. Desde el 09-11 no hay más turnos en el Robotat. No se sigue hasta el tope ni se hace el mapa de la sonda."

**Comprobaciones previas (14-11, solo lectura):** sin `sesion.candado` y sin sesiones abiertas (17 aperturas y 17 cierres); ninguna reserva sin resultado; los 22 archivos congelados iguales a la cabecera de la campaña y "IGUAL a lo probado" con el comando del protocolo.

**Cierre:** `python demo_obstaculo_movil.py --modo L2 --robot-obstaculo 4 --campana L2_obstaculo_2 --cerrar-campana "Fin del tiempo disponible: no hay más turnos en el Robotat desde el 09-11. 73/100 intentos, 30 incluidas (MÍNIMO)."` Salió con código 0 el 14-11 a las 00:14:20. El libro quedó con 187 filas, una `cierre_campana` nueva, y las 73 reservas y los 73 resultados intactos.

**Chequeo de la PC de las 18 incluidas del 06-11** (decisión de José): se declaran como "`CHEQUEO OK` declarado por el operador, sin salida pegada y sin hora. Según el operador, la app de Claude se cerró antes de lanzar a las 19:38:52; la hora del cierre no consta". No cuentan como chequeo propio con salida. La fuente es el "si" que contestó el operador a la pregunta doble de si dio el `CHEQUEO OK` y cerró la app antes de lanzar a las 19:38 (bitácora, adenda del 07-11).

---

## 3. La campaña

**Por día:**

| Día | Intentos | Corridas | Incluidas | Ritmo |
|---|---|---|---|---|
| 21-10 | 1–17 | 14 | 7 | 41 % |
| 23-10 | 18–25 | 5 | 3 | 38 % |
| 04-11 | 26–37 | 6 | 2 | 17 % |
| 06-11 | 38–73 | 31 | 18 | 50 % |
| **campaña** | **1–73** | **56** | **30** | **41 %** |

**Los 43 intentos no incluidos**, según el análisis: 26 no válidas, 8 sin correr, 5 interrumpidas y 4 paradas en la colocación. El detalle por intento y su motivo está en `no_incluidas.csv`, en el §4 del reporte del 13-11 (intentos 18–73) y en el reporte del 22-10 (intentos 1–17). Las 5 interrumpidas son las reservas de los intentos 1, 17, 25, 35 y 73: sin resultado ni crudo en disco, y ninguna entra a la seguridad (§6a).

**Veredicto y tamaño:** meta 50, mínimo 30, tope 100. Cerrada con 30 incluidas: MÍNIMO. Llegar a 50 habría pedido 20 de los 27 intentos que quedaban; el reporte del 13-11 estimaba su probabilidad en 0.0005 al ritmo observado.

**Criterio de seguridad (§2 del plan):** 0 tomas corridas con contacto (< 0.15 m, con el obstáculo o entre agentes); el criterio no cerró la campaña. El cierre fue manual.

---

## 4. La réplica

**Qué corrió.** José la lanzó desde una PowerShell común, `python replica_con_obstaculo.py --campana L2_obstaculo_2`, de las 00:31 a las 04:31 del 14-11, una sola vez, sin `--reanudar` ni `--suplementaria`. La primera corrida empezó a las 00:31:57 y la última, a las 04:30:41. Todas empezaron después del cierre (0 corridas antes del cierre).

**Completa y de una sola pila.**
- 270 corridas: 30 tomas incluidas × 3 condiciones (con obstáculo τ = 0, sin obstáculo τ = 0 y con obstáculo τ = 0.45) × 3 repeticiones.
- La consola cerró con "[réplica] completa.", que solo se imprime en el camino del script que devuelve 0. El código de salida en sí no se capturó.
- Comprobación de solo lectura con la lógica del propio script: 270 corridas hechas, 0 grupos con la pasada normal incompleta, 0 grupos con 0 válidas sin pasada suplementaria, `validar_hechas` OK.
- Todas las corridas son de una sola pila, con sha256 `63b4078b13d1d875588998deaa982f83c08aa7d17c078b27942a126799c71562`, igual al de hoy. Ese sha256 es el de las 25 huellas de archivos de la pila (los 22 congelados, `simulador_robotat.py`, `replica_con_obstaculo.py` y `calibracion_medida.json`); los archivos, como van en el paquete, coinciden con ellas.
- Sin pasadas suplementarias, sin advertencias de la réplica, sin tomas excluidas por el cierre (b) y sin incluidas sin par.

**Corridas no válidas: 1 de 270.** Intento 20, con obstáculo, τ = 0.0, repetición 1: "antigüedad de pose sobre el umbral". Empezó a las 00:52:12 y duró 779.8 s (las demás duran unos 50 s). Las repeticiones 2 y 3 de esa toma son válidas, así que no hay grupo con 0 válidas.

**Condiciones, según Windows** (comprobado por Claude el 14-11; no es una declaración del operador). Fuentes: las consultas de las 00:14:55 y de las 04:57 (bitácora, adendas del 14-11) y la de las 10:19:47 (`derivados/condiciones_replica_windows_20261114.txt`):
- La laptop estaba a batería (40 %) a las 00:14:55 y enchufada, al 100 %, a las 04:57. El evento Kernel-Power 105 de las 01:05:10 ("Power source change") no trae la dirección del cambio: que fue de batería a enchufada se infiere de esas dos lecturas. A las 00:52:47 hubo un "Critical Battery Trigger", a las 00:52:49 la laptop entró a suspensión y a las 00:52:50 reanudó; a las 01:05:11–12, un Modern Standby breve.
- 25 de las 270 corridas empezaron antes de las 01:05:10 y 245, después (de ahí "a batería" y "enchufadas" en este reporte). La corrida no válida es la que estaba en marcha durante la batería crítica.
- Chrome (el proceso más antiguo, desde el 13-11 a las 18:16:35) y `OmenCommandCenterBackground.exe` (desde el 13-11 a las 18:02:21) ya corrían antes de la réplica y seguían vivos a las 10:19:47: estuvieron abiertos durante toda la réplica.
- La consulta de las 00:14:55 también mostró abiertos `OmenCap`, `OmenInstallMonitor`, `OverlayHelper`, `SystemOptimizer`, ChatGPT y dos servidores de Inventor (`servidor_inventor_mcp`, de la app de Claude). A las 04:57 ya no corría ninguno de esos: en la lista había solo Chrome, OMEN Command Center y los `python` que empezaron a las 04:55:53, después de la réplica. No consta cuándo se cerraron, ni si la app de Claude o su servidor de Inventor estaban abiertos entre las 00:31 y las 04:31.
- Ningún proceso del Exp R figuraba en esas consultas. Ninguna es de dentro de la réplica, así que no prueban que no corriera otra carga en paralelo.
- Durante la réplica no constan el plan ni el modo de energía, ni el ahorro de energía (el protocolo pide plan Equilibrado con modo Mejor rendimiento y ahorro apagado; a las 00:14:55 eran los de la referencia y el ahorro estaba apagado), ni el estado de ChatGPT y del servidor de Inventor.

**Chequeo previo de la PC de la réplica.** Según el operador, lo corrió antes de lanzar, pero no guardó la salida. No constan su resultado (`CHEQUEO OK` o `CHEQUEO FALLA`), su hora ni sus procesos, y no se pegó en la bitácora como pide el protocolo. Con lo que muestra Windows, la réplica no corrió con la PC limpia ni enchufada desde el principio. El operador la lanzó desde PowerShell; no declaró si la app de Claude estaba cerrada.

**Lo que no se hizo.** No se repitió la réplica, por decisión de José. Tampoco se corrió ninguna sensibilidad que no esté en el plan.

---

## 5. Principal (§3 del plan): la brecha de cobertura

d_k = hw_k − rep_k, con hw_k la cobertura final (`cobertura_aoi`) de la toma k y rep_k la media de las repeticiones válidas de la réplica con obstáculo y τ = 0. n = 30; IC95 t con 29 gl.

| | n | media | desvío | IC95 |
|---|---|---|---|---|
| hw | 30 | 0.3348 | 0.0323 | [0.3227, 0.3469] |
| réplica (con obstáculo, τ = 0) | 30 | 0.3479 | 0.0423 | [0.3322, 0.3637] |
| **d = hw − réplica** | 30 | **−0.0131** | 0.0430 | **[−0.0292, +0.0029]** |

- Mediana de d: −0.0104. Positivas 10, negativas 20.
- Referencias que no deciden: Wilcoxon de rangos con signo p = 0.0368; bootstrap percentil de la media [−0.0284, +0.0023]; p de la t, 0.1047.
- **Conclusión (redactada como fija el plan):** no hay brecha detectable: hw − réplica = −0.0131, IC95 [−0.0292, +0.0029] (n = 30); con esta precisión, la brecha está acotada, con 95 % de confianza, a |brecha| ≤ 0.0292. No se afirma equivalencia.
- Semiancho observado ±0.0161, contra ±0.016 esperado en el plan con n = 30.
- Ruido de la réplica entre repeticiones (desvío por toma): mediana 0.0011, máximo 0.0331.
- Respaldo por semilla: no aplica (ninguna semilla se repite).

**Sensibilidades (§3a; no deciden):**

| | n | media | IC95 | Wilcoxon p |
|---|---|---|---|---|
| A. sin arranques fuera del soporte | 30 | −0.0131 | [−0.0292, +0.0029] | 0.0368 |
| B. sin tomas con retroceso | 19 | −0.0113 | [−0.0339, +0.0113] | 0.2753 |
| C. sin tomas con freno de respaldo | 30 | −0.0131 | [−0.0292, +0.0029] | 0.0368 |
| D. sin tomas con rampa | 26 | −0.0137 | [−0.0322, +0.0048] | 0.0520 |
| E. réplica con τ = 0.45 s | 30 | −0.0098 | [−0.0246, +0.0051] | 0.1064 |

- A y C dan lo mismo que el principal: ninguna incluida tiene arranque fuera del soporte ni freno de respaldo.
- B quita las 11 tomas con retroceso; D quita las 4 con rampa (intentos 2, 8, 19 y 29).
- Ninguna sensibilidad cambia la conclusión: todos los IC95 contienen el 0.

---

## 6. Seguridad (§4 del plan)

**Alcance, escrito así:** durante la toma y sobre poses observadas.

**6a. Contra el obstáculo, sobre las 56 corridas** (las incluidas y las no incluidas que corrieron):
- distancia mínima medida al obstáculo en el hw: mínimo 0.2648 m (intento 71), mediana 0.3329 m, máximo 0.6415 m;
- tomas con contacto (< 0.15 m): 0 de 56, IC95 de Clopper–Pearson [0.000, 0.064]; ninguna en las no incluidas;
- tomas con freno de respaldo: 0 de 56, IC95 [0.000, 0.064], con 0 eventos y 0 decisiones en freno;
- **pareada en las 30 incluidas, hw − réplica**, con la réplica como media de las repeticiones válidas: −0.0069 m, IC95 [−0.0240, +0.0103], mediana +0.0001, positivas 15 de 30, Wilcoxon p = 0.7971. Con el mínimo de las repeticiones: −0.0037 m, IC95 [−0.0214, +0.0139], mediana +0.0010, positivas 16 de 30, p = 0.7343;
- en la réplica, tomas bajo 0.15 m: 0 de 30 por la media y 0 de 30 por el mínimo, IC95 [0.000, 0.116]; frenos en sombra de la réplica: 0.

Con 0 frenos de respaldo en las 56 corridas, el freno no actuó. Con el freno en sombra, la separación la sostuvo el filtro con su rescate, y el freno habría actuado como capa redundante. El `n_escape` medio fue 32.125 por corrida en el hw (§6c).

**6b. Pared**, pareado por toma. `d_pared_min` hw − réplica: **−0.0302 m**, IC95 [−0.0354, −0.0251] (n = 30), mediana −0.0283, negativas 30 de 30, Wilcoxon p < 0.0001. Con el mínimo de las repeticiones: −0.0291 m, IC95 [−0.0344, −0.0239], mediana −0.0278. El hw pasa más cerca de la pared que su réplica en las 30 tomas; es el mismo sentido que el 30-09 (−0.0355 m).
- `d_pared_min` medio: 0.1367 m en las incluidas del hw, 0.1669 m en su réplica y 0.1569 m en las 56 corridas del hw.
- `viola_018` (pasos a menos de 0.18 m de la pared) por toma: 1.87 en el hw y 1.93 en la réplica, en las pareadas.

**6c. Pares de agentes** (descriptivo): `colisiones_015` y `colisiones_022`, 0 en el hw y en la réplica. `frac_cbf` medio: 0.3073 en el hw y 0.3553 en la réplica. `n_escape` medio: 39.97 y 32.88 en las pareadas, y 32.125 en las 56 corridas del hw.

**Criterio de cierre por seguridad (§2 del plan):** 0 tomas corridas con contacto; no cerró la campaña por el criterio y no hay incumplimiento.

---

## 7. Costo del obstáculo (§5 del plan)

c_k = rep_con_k − rep_sin_k, las dos con τ = 0, medias de repeticiones válidas, desde la misma pose inicial y con la misma semilla.

- **c = +0.0077**, IC95 [−0.0001, +0.0155] (n = 30, 29 gl), mediana +0.0045, positivas 21 de 30. p de la t = 0.0520; Wilcoxon p = 0.0387.
- No hay costo de cobertura detectable en la réplica: el IC95 contiene el 0 (por poco) y la estimación puntual es positiva; en promedio, la cobertura con obstáculo no resultó menor que sin él. El plan fija el estimador y el IC, no una conclusión más fuerte.
- Descriptivos: `d_pared_min` con − sin = −0.0005 m; `frac_cbf` con − sin = +0.0437; hw − réplica sin obstáculo = −0.0054.
- **Condicional** a los arranques de la campaña (blancos a ≥ 0.65 m del 4 medido, chequeo de arranque a 0.50 m) y a la trayectoria medida del 4, que incluye los frenos del hw.

---

## 8. Comparación con el 30-09 (§6 del plan, solo descriptiva) y el cierre (a3)

Son escenarios distintos: no hay p ni IC de la diferencia. Se recalcularon desde el crudo empaquetado del 30-09.

| | 30-09 | esta campaña |
|---|---|---|
| cobertura del hw | 0.3452 ± 0.0428 (n = 50) | 0.3348 ± 0.0323 (n = 30) |
| brecha hw − réplica, por pares | +0.0077, IC95 [−0.0046, +0.0200] (n = 50) | −0.0131, IC95 [−0.0292, +0.0029] (n = 30) |
| brecha hw − réplica, por escenario | +0.0123, IC95 [−0.0073, +0.0318] (n = 12) | igual que por pares (una toma por escenario) |
| `d_pared_min` hw − réplica | −0.0355 m, IC95 [−0.0404, −0.0306] (n = 50) | −0.0302 m, IC95 [−0.0354, −0.0251] (n = 30) |

**Cierres (a1) y (b)** (pruebas de la réplica, plan §7). El (a1) se informó en el reporte del 22-10: sin obstáculo, la pila decide bit a bit igual que la del 30-09 ante las mismas observaciones. El (b), la trayectoria reproducida del 4 contra la medida, pasó en las 180 corridas con obstáculo (error máximo 0.0 m, sin desfase, mandos iguales, rumbo dentro de 4.4e−16 rad) y no excluyó ninguna toma.

**Composición:** la campaña usa el robot 2 en lugar del 6; cuatro de los cinco robots son los del 30-09. Esa diferencia se suma a la de las condiciones y nada la acota.

**Salvedad: el cierre (a3) dio NO PASA** (decisión de José, 10-10; `cierre_a3_20261010_b/`, completo en el zip):
- 12 episodios válidos del 30-09 corridos sin obstáculo con τ = 0 y 3 repeticiones (36/36 válidas, una sola pila): media de Δ = −0.00252, **IC95 [−0.01052, +0.00549]**. El margen aprobado es ±0.00827, y el límite inferior queda fuera.
- **Diagnóstico** (`diagnostico_20261010/`): la decisión de la pila es bit a bit igual a la del 30-09 en los episodios que lo deciden; y los dos episodios que lo deciden van en direcciones opuestas: la bifurcación nueva de s05 ep 2 (Δ = −0.040) y la corrida baja del 30-09 en s05 ep 8 (Δ = +0.013). Con los 12 Δ como intercambiables, la probabilidad de que pase es 0.615.
- **Ruido entre repeticiones.** El plan (§7) y la decisión de José del 10-10 dicen "el mismo ruido entre repeticiones que el 30-09". En los mismos 12 episodios, el desvío mediano por episodio es 0.0013 en las nuevas contra 0.0015 en las del 30-09, pero el máximo nuevo (0.0287, s05 ep 2) supera al del 30-09 (0.0175, s05 ep 8). La frase no se cambió (cambiarla exige una corrección declarada) y su redacción queda pendiente (§11).
- **La pila del a3 no es la de esta réplica.** El a3 corrió con la pila `b5a289046f966592…` y la réplica de la campaña, con `63b4078b13d1d875…`. Difieren 6 de los 25 archivos: `config_robotat.py` (la huella sin calibración), `calibracion_medida.json`, `campana_obstaculo.py`, `demo_obstaculo_movil.py`, `analizar_campana_l2.py` y el plan. Los otros 19 son iguales, entre ellos `replica_con_obstaculo.py`, `simulador_robotat.py`, `sesion_robotat.py` y `lib/`. El a3 evaluó la réplica de aquel momento; que la de la campaña se comporte igual no está mostrado.
- No se repitió el a3 ni se cambió el margen. El IC95 de arriba es la cota de cuánto puede diferir la réplica nueva de la del 30-09: es una salvedad de esta comparación descriptiva. El principal (§5) no depende de esto: compara el hw de la campaña con su propia réplica.

---

## 9. Descriptivos post hoc (§7 del plan)

Los pidió José el 10-10, después del a3. Son post hoc y no deciden nada.

**Ciclo p95 de la réplica** (`ciclo_p95_ms` de las 90 corridas de cada condición, válidas o no):

| Condición | media (ms) | máximo (ms) |
|---|---|---|
| con obstáculo, τ = 0 | 11.64 | 46.50 |
| sin obstáculo, τ = 0 | 10.28 | 41.04 |
| con obstáculo, τ = 0.45 | 11.31 | 46.70 |

**Por fuente de energía** (descriptivo adicional, post hoc: no está en el plan y no decide nada): en las 25 corridas que empezaron a batería, el ciclo p95 medio fue 35.0 ms (máximo 46.7); en las 245 que empezaron enchufadas, 8.6 ms (máximo 18.7). La única corrida con algún ciclo de más de 100 ms fue una de las de batería. El contraste coincide con las condiciones del §4.

**Desvío entre repeticiones, variante sin obstáculo:** de las 30 tomas (todas con ≥ 2 repeticiones válidas), **8 tienen un desvío mayor que 0.01** (ddof = 1), contra 6 de 50 en la réplica del 30-09. Con ddof = 0 son 6 de 30.

---

## 10. Declaraciones (§8 del plan)

**Cegado.** La cobertura de las tomas no se mostró durante la campaña (la consola de la toma no la muestra), y no se miró ninguna cobertura del hw antes del análisis fijado, que se corrió el 14-11 a las 10:16:47, después de la réplica. Dos precisiones:
- la consola que el operador pegó de la réplica trae la cobertura de cada corrida de la réplica (la imprime el script); no se tabuló ni se usó antes del análisis;
- para las condiciones de la réplica (§4) solo se leyeron de su tabla las columnas de inicio, validez, motivo y ciclo.

**Chequeo de la PC por sesión y por lanzamiento**, según el reporte del 13-11 (§9.1), que lo toma de las consolas, la bitácora y el operador (las consolas no van en este paquete), y para la réplica, según el operador y Windows:

| Sesión | ¿`CHEQUEO OK` antes? | Incluidas |
|---|---|---|
| 21-10, 13:26 (intento 1) | sí, pegado (13:25:56) | — |
| 21-10, 13:34 (intentos 2–7) | compartido: el OK de las 13:32:16 | 2 y 4 |
| 21-10, 13:48 (intentos 8–17) | no: el último OK, 963 s antes, era de otra sesión | 8, 9, 10, 13 y 14 |
| 23-10, 20:50 (intentos 18–25) | no: el último chequeo, a las 20:32:35, dio FALLA | 19, 20 y 21 |
| 04-11, 12:07 (intentos 26–35) | no consta | 29 y 33 |
| 04-11, 12:51 (intentos 36–37) | sí, pegado (12:49:56) | — |
| 06-11, 19:38 (intentos 38–73) | sí según el operador, sin la salida pegada; el último pegado, a las 19:21:17, dio FALLA | las 18 del 44 al 72 |
| **réplica, 14-11, 00:31 (lanzamiento único)** | el operador lo corrió y no guardó la salida: no consta el resultado | — |

- De las 30 incluidas: 18 con `CHEQUEO OK` declarado sin salida y sin hora, 2 con el OK compartido y 10 sin `CHEQUEO OK` propio. **Ninguna incluida sale de una sesión con chequeo propio con salida pegada.**
- **Las 18 del 06-11:** "`CHEQUEO OK` declarado por el operador, sin salida pegada y sin hora. Según el operador, la app de Claude se cerró antes de lanzar a las 19:38:52; la hora del cierre no consta" (§2). Ese OK solo cubriría la sesión si se corrió después de cerrar la app de Claude por última vez; si fue antes de las 19:33:31, quedó compartido con uno a cuatro lanzamientos que no arrancaron. El reporte del 13-11 (§9.1) tiene el detalle.
- **La réplica:** con lo que muestra Windows (§4), no corrió con la PC limpia: Chrome y OMEN Command Center estaban abiertos, y las primeras 25 corridas, a batería.
- **Aperturas sin tomas:** de las 17 aperturas del libro, 10 cerraron sin ningún intento (3 del 21-10, 2 del 23-10, 1 del 04-11 y 4 del 06-11), por "timed out", robot sin respuesta o "fin de la sesión". No aportan intentos ni incluidas, así que no entran a la tabla.
- La L0 habilitante es la del 21-10 a las 13:09, que corrió sin `CHEQUEO OK`.

**Código y configuración.** Los 22 sha256 de los archivos congelados son iguales a los de la cabecera de la campaña (22/22) y el análisis comprobó que el plan, `analizar_campana_l2.py` y `campana_obstaculo.py` coinciden con el libro. No hubo correcciones del libro (`--corregir-campana`), ni candados liberados, ni filas ilegibles. Los offsets de rumbo y la calibración del día fueron los mismos en las 17 sesiones: offsets en grados de los robots 1, 5, 8, 2, 9 y 4: 92.1293, 88.8106, 95.01, 89.7361, 94.2587 y 81.9006. `config_robotat.py` con sha256 `0c0465eb20f730d98ebe93c730555ff4c85227ffa5d99a6011ec066fefbc949e` y `calibracion_medida.json` con `bc077fd798ad9fc7094dbdb4ee762aca35e0299ebbc4b456753a2e97fc961a9a`. La calibración es la del 28 y 29-08; no consta una recalibración de Motive.

**Otras declaraciones del análisis:**
- tomas cuyo 4 no arrancó de la proyección (`col_obst_origen`): ninguna; las 30 incluidas son "proyección";
- tomas con rampa de arranque seguro (la primera de cada sesión, sensibilidad D): intentos 2, 8, 19 y 29;
- reservas marcadas por el análisis: ninguna; reservas que el libro marcó "interrumpida" al cerrar la sesión: intentos 1, 17, 25, 35 y 73 (5), sin resultado ni crudo en disco, de modo que no hay corridas marcadas interrumpidas que hayan corrido (recuento físico del análisis: 0), y no entran a la seguridad del §6a;
- incluidas sin par, o sin réplica sin obstáculo o con τ = 0.45: ninguna;
- pausas de seguridad (5):

| Intento | Regla | Respuesta |
|---|---|---|
| 7 | CONTACTO durante la colocación: robots 1 y 2 a 0.150 m | detenida |
| 15 | ABORTO POR EL OBSTÁCULO: marcador del obstáculo CONGELADO en (1.58, 0.92) | siguió |
| 24 | ABORTO POR EL OBSTÁCULO: el obstáculo NO FRENA, se movió 51.1 cm durante la colocación (v medida 0.000 m/s) | siguió |
| 36 | ABORTO POR EL OBSTÁCULO: enlace de ruedas del obstáculo (robot 4) caído antes de la colocación | siguió |
| 37 | ENLACE DE RUEDAS CAÍDO durante la colocación: robot 5 | detenida |

- el contacto del intento 7 (21-10) fue de la colocación y no cuenta para el criterio de seguridad;
- en el intento 24 el operador movió el 4 a mano (respuesta del 07-11), y las pausas del 24 y del 36 se contestaron "s" a los 4 y 5 s: el reporte del 13-11 (§4, §9.7) lo declara.

---

## 11. Salvedades y pendientes sin resolver

Siguen abiertos, por decisión de José (13-11), y van como salvedades de este reporte:
1. **La L0 habilitante** es la del 21-10 y corrió sin `CHEQUEO OK`. No se repitió.
2. **Recalibración de Motive:** no consta ninguna; falta confirmarlo con el laboratorio.
3. **El cierre del libro que no muestra su causa** (la sesión termina con "fin de la sesión" cuando un marcador está congelado o no responde). El 06-11 escondió que Motive estaba cerrado. Arreglarlo toca un archivo congelado.
4. **El modo de energía de referencia** y si el chequeo debe escribir solo en la bitácora.
5. **La tolerancia de colocación de la L0.**
6. **La frase sobre el ruido entre repeticiones del (a3):** "el mismo ruido que el 30-09" no coincide con el máximo en los mismos 12 episodios (0.0287 contra 0.0175); falta decidir su redacción (§8; reporte del 22-10, pendientes).
7. **El defecto de `--simulador`.**
8. **Las ruedas** de los robots que "no avanzan" en la colocación automática (el reporte del 13-11, §5).
9. **El corte de red del 04-11 (12:31:59):** falta confirmar su causa con el laboratorio (red, router, punto de acceso o servidor).
10. **El chequeo declarado del 06-11:** falta la hora del `CHEQUEO OK`, si se corrió después de cerrar la app de Claude y si el "timed out" del primer lanzamiento del 23-10 y del 04-11 fue la laptop sin conectar al Robotat.
11. **Los puntos ciegos de los marcadores:** cerca de (0.95, 2.80), la esquina −x+y y una zona lejos de las paredes (x entre 1.456 y 1.685, y entre 1.058 y 1.328). No se hizo el mapa de la sonda.
12. **La réplica:** corrió sin salida de chequeo guardada, con la PC no limpia y las primeras 25 corridas a batería (§4). No se repitió.

---

## 12. Para la tesis

Cifras que van al documento. Cada una con su unidad y su fuente (`analisis.json` es el de `analisis_campana/L2_obstaculo_2_20261114_101647/`).

| Cifra | Valor | Unidad | Fuente |
|---|---|---|---|
| Intentos / corridas / incluidas | 73 / 56 / 30 | intentos, corridas y tomas incluidas | libro, `analisis.json › conteos` |
| Veredicto | MÍNIMO (mínimo 30, meta 50, tope 100) | — | `analisis.json`, libro |
| Cobertura final del hw, incluidas | 0.3348 ± 0.0323 (n = 30) | fracción (`cobertura_aoi`), media ± desvío | `analisis.json › principal.hw` |
| Cobertura final de la réplica con obstáculo, τ = 0 | 0.3479 ± 0.0423 (n = 30) | fracción, media ± desvío | `analisis.json › principal.replica` |
| **Brecha hw − réplica (principal)** | **−0.0131, IC95 [−0.0292, +0.0029]** | fracción de cobertura | `analisis.json › principal` |
| Cota de la brecha | \|brecha\| ≤ 0.0292, sin afirmar equivalencia | fracción de cobertura | `analisis.json › principal.conclusion` |
| Costo del obstáculo (con − sin, réplica) | +0.0077, IC95 [−0.0001, +0.0155] | fracción de cobertura | `analisis.json › costo` |
| Contactos (< 0.15 m al obstáculo) | 0 de 56 corridas, IC95 [0.000, 0.064] | tomas | `analisis.json › seguridad.contacto_hw` |
| Frenos de respaldo | 0 de 56 corridas, IC95 [0.000, 0.064] | tomas | `analisis.json › seguridad.tomas_con_freno_hw`, libro |
| Distancia mínima al obstáculo (56 corridas) | mín 0.2648, mediana 0.3329, máx 0.6415 | m | `analisis.json › seguridad.d_min_obst_hw` |
| `d_min` hw − réplica (media de repeticiones) | −0.0069, IC95 [−0.0240, +0.0103] | m | `analisis.json › seguridad` |
| `d_pared_min` hw − réplica (media de repeticiones) | −0.0302, IC95 [−0.0354, −0.0251] | m | `analisis.json › seguridad` |
| Brecha hw − réplica del 30-09 (por pares / por escenario) | +0.0077 [−0.0046, +0.0200] / +0.0123 [−0.0073, +0.0318] | fracción de cobertura | `analisis.json › comparacion_3009` |
| Cierre (a3) | NO PASA: media de Δ −0.00252, IC95 [−0.01052, +0.00549], margen ±0.00827 | fracción de cobertura | `cierre_a3_20261010_b/cierre_a3_20261010_091454.json` |
| Ciclo p95 de la réplica (con obstáculo, τ = 0) | 11.64 media, 46.50 máx (post hoc) | ms | `replica_tomas.csv` |
| Tomas con desvío entre repeticiones > 0.01 (sin obstáculo, ddof = 1) | 8 de 30 (30-09: 6 de 50) (post hoc) | tomas | `replica_tomas.csv` |

Al citar estas cifras, van las salvedades del §10 y del §11: sin chequeo propio con salida en ninguna sesión incluida, la réplica corrida sin la PC limpia, el a3 NO PASA, y el principal acotado sin afirmar equivalencia.

---

## 13. Datos y verificación

`REPORTE_2026-11-14_cierre_campana_L2_datos.zip` repite las rutas del proyecto, para que el verificador independiente corra dentro del zip tal cual. Contiene:
- **`documentos/`:** este reporte; el reporte del 13-11 (`REPORTE_2026-11-07_campana_L2.md`) y el del 22-10; el extracto de la bitácora desde el 23-10.
- **raíz:** `PLAN_ANALISIS_campana_L2.md` (el plan congelado) y `PROTOCOLO_L0_L2.md` (como está hoy; difiere del que regía las sesiones solo en la línea del chequeo que busca los procesos del Exp R).
- **`primerafase_webots/controllers/coordinador_enjambre/`:** los archivos congelados, `config_robotat.py`, `calibracion_medida.json`, `simulador_robotat.py` y `replica_con_obstaculo.py` (la pila de la réplica), y `resultados_demo_obstaculo/` con:
  - `campanas/L2_obstaculo_2/` (`libro.csv` y `campana.json`, ya cerrada);
  - los CSV de tomas, decisiones y obstáculo de las siete sesiones, con la cobertura (la campaña ya está cerrada);
  - `replica_campana/L2_obstaculo_2/` (tomas, decisiones, obstáculo y pila de la réplica) y `replica_campana/cierre_a3_20261010_b/` completo, con `diagnostico_20261010/`;
  - `analisis_campana/L2_obstaculo_2_20261114_101647/` (`analisis.json`, `pares.csv`, `no_incluidas.csv`, `seguridad_tomas.csv` y `salida.txt`).
- **`REPORTE_2026-09-30_datos/csv/`:** los 10 CSV del 30-09 que usa la comparación.
- **`derivados/`:** la consulta a Windows sobre las condiciones de la réplica, la comprobación de su completitud con el script que la corrió, y la salida del verificador independiente. No son crudos de la campaña.
- **`scripts/`:** el verificador de cifras.
- **`sha256_paquete.txt`:** el sha256 de cada archivo del paquete, salvo esta lista.

No se incluye la consola que el operador pegó de la réplica: sus cifras son las de `replica_tomas.csv`.

**Verificador independiente** (congelado con el plan), desde la carpeta descomprimida y con Python 3.13 y `scipy`:

```text
cd primerafase_webots/controllers/coordinador_enjambre
python verificar_campana_l2.py resultados_demo_obstaculo/analisis_campana/L2_obstaculo_2_20261114_101647
```

Sale con 0: 131/131 coinciden.

**Verificador de cifras de este reporte**, desde la carpeta descomprimida. Hace falta Python 3.13, sin paquetes externos; el script no importa código del proyecto:

```text
python scripts/verificar_cifras_cierre_campana_l2_20261114.py . documentos/REPORTE_2026-11-14_cierre_campana_L2.md
```

El verificador recalcula con código propio, desde los CSV del paquete:
- el libro (intentos, incluidas, corridas, contactos, frenos, distancias y la tabla por día);
- el principal (hw, réplica, d, IC95 t, signos), las sensibilidades A–E, la seguridad pareada, la pared y el costo;
- la comparación con el 30-09 contra `analisis.json`, cuyos números recalcula el verificador independiente desde los CSV del 30-09 (este script no los abre);
- los descriptivos post hoc (ciclo p95 y desvíos entre repeticiones) y las condiciones de la réplica que salen de su tabla;
- los sha256 de los archivos congelados y de la pila de la réplica.

Comprueba que cada cifra aparezca igual en este texto.

**Algunas cifras no las recalcula, sino que las coteja contra un texto:**
- las de Windows (eventos y fechas de inicio de los procesos), contra `derivados/`, y las lecturas de las 00:14 y las 04:57, contra el extracto de la bitácora;
- las del cierre (a3), contra su JSON, su diagnóstico y las huellas de las dos pilas;
- los p de Wilcoxon y de la t, el bootstrap y la bandera de arranque fuera del soporte (sensibilidad A), contra `analisis.json` y `pares.csv`; el verificador independiente los recalcula;
- las citas de la bitácora, contra su extracto.

**No cubre, entre otras cosas:**
- las respuestas del operador (el "si" a la pregunta doble, el chequeo de la réplica sin salida guardada), que están en el extracto de la bitácora pero no en una consola;
- la clasificación del chequeo de cada sesión del §10: el verificador la compara con la tabla del §9.1 del reporte del 13-11, que va en el paquete, y cuenta desde el libro qué incluidas caen en cada sesión; no tiene las consolas;
- la redacción cualitativa: el verificador solo exige que estén las frases fijas (por ejemplo, "No se afirma equivalencia" y la del freno en sombra) y que no estén algunas prohibidas; no lee el resto del texto;
- las rutas absolutas: `analisis.json` y algunos scripts del paquete traen las de la laptop del proyecto (`C:\Users\velas\…`);
- el código de salida de la réplica, que no se capturó;
- que los demás trabajos del período (el Exp R y el material del video) no entren aquí.
