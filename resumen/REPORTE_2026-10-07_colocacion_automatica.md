# Demo del obstáculo móvil: colocación automática, Fase B (07-10)

**Qué es:** la colocación AUTÓNOMA de los 5 agentes antes de cada toma de la L1 y la L2.
- Los agentes van solos a sus blancos alrededor del obstáculo **quieto**, el robot 4.
- Es la Fase B de `PROPUESTA_colocacion_autonoma_obstaculo.md`.
- **No es un resultado citable:** es la herramienta para grabar la demo.

**Decisiones de José (07-10):**
- el robot 4 como obstáculo;
- la L1 con el 4 **encendido** y conectado;
- OK al plan;
- el arranque del 4 en la L2 desde la proyección de su pose;
- el offset del 4 se mide en la L0, y si difiere más de 3° se frena antes de la L1;
- no repetir la confirmación de la Fase 0;
- no recortar las fallas inyectadas ni los ensayos con τ = 0.85 s;
- empezar por la Fase B; la Fase A, que mueve solo al 4, se decide al cerrar ésta.

**Datos crudos:** `REPORTE_2026-10-07_colocacion_automatica_datos.zip`. `scripts/verificar_cifras_colocacion.py` recalcula desde los crudos cada cifra de este reporte.

---

## 1. Resumen

1. **La Fase B está lista para el laboratorio.** En los cuatro ensayos finales, con los robots colocándose solos y sin teletransporte:
   - L2 y L1, cada uno con τ = 0.85 s y con τ = 0.45 s;
   - simulador con zona muerta de rueda;
   - el obstáculo con 0.85 s de retardo.

   Resultados:
   - **26 de 26 tomas válidas para la demo**, en 27 intentos;
   - **0 frenos de respaldo y 0 reglas de parada**;
   - **el 4 nunca tuvo que colocarse a mano.**
2. **Criterio de la colocación, fijado antes (> 0.15 m durante toda la colocación, en la verdad del simulador): cumple.**
   - Agente–obstáculo, ≥ 0.3052 m.
   - Agente–agente, ≥ 0.1582 m. Este margen de 8 mm aparece con τ = 0.85 s en la barrera **entre agentes**, que es la heredada de la colocación de `sesion_robotat` y no se tocó (§5).
3. **El ensayo con τ = 0.85 s encontró un falso positivo,** y se corrigió.
   - Al terminar una toma el 4 sigue andando por su retardo. La colocación lo tomó por "NO FRENA" y detuvo la sesión.
   - Ahora espera hasta 3 s a que quede quieto.
4. **Revisión adversarial,** en dos rondas, con 3 revisores cada una: una del plan y otra del código. Lo que encontró se corrigió (§4). Entre lo más serio:
   - el enlace del 4 que se caía sin que nada lo frenara;
   - el bloqueo frontal contra el 4 quieto;
   - un falso "marcador congelado";
   - el Enter de más que autorizaba el movimiento.
5. **Barrera y validez sin cambios.** Comparando con el AST, sin docstrings, contra el respaldo previo, sólo cambian `sesion_demo`, `sesion_l0`, `_metricas_l0`, `main` y `SupervisorObstaculo` (los métodos `__init__`, `_abortar`, `_chequear`, `paso` y `_mandar`; los dos últimos sólo con `quieto_conectado`, que es False salvo en la L1 automática), más funciones nuevas.
6. **El offset del 4 se mide en la L0,** y la L1/L2 no arranca sin una L0 OK con el offset a ≤ 3° de la tabla.
7. **Pruebas: 102 de 102** (97 de la demo y 5 de la regla de 10 s).
8. **Tiempo real de la etapa:** unas 3 h, contra 5–6 h estimadas.

---

## 2. Lo que se construyó

| archivo | qué hace |
|---|---|
| `colocacion_con_obstaculo.py` (nuevo) | la Fase B: blancos a ≥ 0.65 m del 4 medido; rodeo del 4; fila del Exp O como barrera fija; vigilancia del 4 y de los enlaces; contacto; espera de quietud; envolvente |
| `demo_obstaculo_movil.py` | `--colocacion auto` (por defecto en la línea de comandos); `--robot-obstaculo` **obligatorio**; L1 con el 4 conectado y vigilado (`quieto_conectado`); la regla de parada también en la colocación; offset en la L0 y su habilitación |
| `simulador_para_colocacion.py` (nuevo) | simulador con zona muerta de rueda desde parado y retardo por robot |
| `ensayo_sesion_simulador.py` (nuevo) | ensayo de L1 o L2 completa con colocación automática, con `MonitorVerdad` durante toda la sesión |
| `analizar_sesion_demo.py` | cuenta también las paradas de la colocación |

`colocacion_autonoma.py` y `sesion_robotat.py` no se tocaron.

**Respaldos:**
- `demo_obstaculo_movil_respaldo_20261007_preColocacion.py`;
- `PROTOCOLO_L0_L2_respaldo_20261007_preColocacion.md`.

## 3. Cómo funciona una toma automática

1. **Enlaces vivos.** Si alguno está caído, no se mueve a nadie.
2. **El 4 quieto:** hasta 3 s, con todos frenados.
   - Si se mueve con orden de parada, es "NO FRENA" y regla de parada.
   - Si no tiene pose, vuelve al operador.
3. **Dónde arranca el 4:**
   - L1: el centro;
   - L2: la proyección de su pose sobre el círculo.
   - Si está fuera de su envolvente (±6 cm del círculo, ±25° de la tangente), se lo coloca **a mano**, porque la Fase A no está.
4. **Blancos** a ≥ 0.65 m del 4 medido, con los rumbos de `sortear_rumbos`, que es lo mismo que usó la Fase 0.
5. **Un Enter,** previo descarte de lo tecleado de más, con el aviso "Los agentes van a ir SOLOS…".
6. **La colocación,** con estas guardas:

   | qué detecta | qué hace |
   |---|---|
   | contacto, < 0.15 m entre centros medidos | todos frenan y regla de parada |
   | el 4 que se mueve | ídem |
   | marcador del 4 congelado o perdido | ídem; con la pose vencida, los agentes frenan en el acto |
   | enlace del 4 o de un agente caído | ídem |
   | un agente que tiene al 4 en el camino | lo rodea por el lado libre de agentes quietos |
   | un agente que no avanza | en el reintento, cambia de lado o primero se aleja 10 cm |

7. **Asentamiento** de 1.2 s y los chequeos: geometría, congelados, quietud, agentes a ≤ 0.12 m del blanco y el 4 en su envolvente. Si fallan, reintento, hasta 5, sin gastar el intento.

## 4. Revisión adversarial y lo que se corrigió

**Del plan (3 revisores):**
- **Críticos:** el enlace del 4 que se caía en plena colocación sin que nada lo frenara, y el bloqueo frontal contra el 4 quieto.
- **Importantes:**
  - mover a la vez al 4 y a los agentes;
  - la responsabilidad "completa" de los dos lados, que es menos conservadora que el 50/50;
  - el 7 por defecto;
  - el offset del 4 sin verificar;
  - el margen de 0.50 m de separación.
- Quedó en `PROPUESTA_colocacion_autonoma_obstaculo.md`.

**Del código de la Fase B (3 revisores).** Se corrigió:
- el falso "marcador congelado" con dos consultas pegadas;
- el enlace de un **agente** que se cae durante la colocación. Esto va más allá del plan, pero es una guarda de seguridad del mismo tipo;
- el rodeo, que no esquivaba a los agentes ya en su blanco;
- el reintento, que repetía la misma configuración;
- el Enter de más que autorizaba el movimiento;
- el cartel "LEVANTARLO", que llegaba 1.5 s tarde;
- la ventana de quietud, que podía no confirmar nunca;
- el 4 sin pose al empezar, que era regla de parada y no volvía al operador;
- el analizador, que no veía las paradas de la colocación;
- las pruebas que no detectaban mutantes.

**Lo que confirmaron:**
- que no cambia la barrera, `correr_toma` ni la validez;
- que el camino manual queda igual.

## 5. Ensayos en el simulador

Todos con L1 o L2 completa, colocación automática, zona muerta, el obstáculo con τ = 0.85 s y `MonitorVerdad` durante toda la sesión, colocaciones incluidas.

| ensayo | τ agentes | intentos | válidas demo | frenos | paradas | 4 a mano | reintentos | verdad agente–obstáculo | verdad agente–agente | zona muerta (retenciones) |
|---|---|---|---|---|---|---|---|---|---|---|
| L2 | 0.85 | 10 | 10 | 0 | 0 | 0 | 3 | 0.3052 | 0.1763 | 800 |
| L1 | 0.85 | 3 | 3 | 0 | 0 | 0 | 0 | 0.3907 | **0.1582** | 0 |
| L2 | 0.45 | 11 | 10 | 0 | 0 | 0 | 7 | 0.3055 | 0.2154 | 14399 |
| L1 | 0.45 | 3 | 3 | 0 | 0 | 0 | 4 | 0.3257 | 0.2468 | 2400 |

**Duración de cada colocación:** de 26 a 45 s en la L2 con τ = 0.85; de 32 a 36 s en la L1 con τ = 0.85; de 14 a 44 s en la L2 con τ = 0.45; de 20 a 29 s en la L1 con τ = 0.45.

**Lo que muestran:**
- **El mínimo agente–agente de 0.1582 m** fue durante la colocación de la 3.ª toma de la L1 con τ = 0.85. Cumple el criterio por 8 mm.
  - Es la barrera **entre agentes** de `colocacion_autonoma`: 50/50, D = 0.25 entre puntos de mira. La misma de la colocación que ya se usa en el laboratorio desde el 22-09, sin cambios.
  - En las tomas, el mínimo entre agentes fue ≥ 0.2264 m.
- **El intento perdido de la L2 con τ = 0.45** fue un agente pegado a una pared (a 0.196 m). Sólo podía recibir órdenes que la zona muerta no dejaba pasar, y no se movió en los 6 reintentos.
  - En el simulador nadie lo mueve a mano. En el laboratorio, el aviso del reintento pide justamente eso ("alejalo a mano").
  - Es un límite heredado de la colocación de `sesion_robotat`.
- **La zona muerta actuó en las sesiones** (hasta 14 399 retenciones). En las pruebas aisladas de colocación no llegó a actuar: las órdenes de la ley quedan sobre el mínimo, y ni con el agente bloqueado el QP deja órdenes dentro de la zona muerta.

**Ensayos anteriores, que se declaran:**
- **El 1.º** (L2, τ = 0.85, antes de la espera de quietud) se detuvo en la 2.ª colocación por el falso positivo: "el obstáculo NO FRENA: se movió 1.9 cm durante la colocación (v medida 0.046 m/s), debía estar quieto". Corrió 2 intentos.
- **El intermedio** (L2, τ = 0.85, con la espera de quietud y antes de las correcciones de la revisión) dio 10 tomas válidas en 11 intentos.
  - Hubo **1 intervención del freno de respaldo** en una toma con política, con un mínimo de 0.2093 m. En las 120 tomas con política de la Fase 0 no hubo ninguna, pero ese simulador no tenía zona muerta, y éste la tuvo (1299 retenciones). Con un solo caso no se puede atribuir.
  - El mínimo entre agentes, 0.1693 m, fue durante una colocación.

## 6. Pruebas

**102 de 102:** 97 de `test_demo_obstaculo_movil.py` y 5 de `test_regla_estancamiento.py`. Las de esta etapa:
- **Geometría:** proyección y envolvente, objetivo del 4, blancos a 0.65 m, rodeo (también esquivando a un agente quieto) y fila fija del Exp O.
- **Supervisor de la L1 con el 4 conectado:** el que se mueve es "NO FRENA", el quieto recibe (0,0), y el enlace caído aborta. La L1 apagada sigue igual.
- **Colocación con el blanco detrás del 4,** con zona muerta y τ = 0.45/0.85 y 0.85/0.85: llegan todos a > 0.15 m en la verdad. **Sin el rodeo, la barrera sola mantiene > 0.25 m.** Un mutante sin rodeo deja al agente trabado.
- **Fallas inyectadas:** son las mismas guardas de la tabla del §3, cada una provocada a propósito. Además:
  - el 4 conectado que no obedece;
  - el contacto antes de mover a nadie;
  - el 4 invisible al empezar, en cuyo caso nadie se mueve.
- **Quietud:** el 4 que viene andando con τ = 0.85 no es "NO FRENA"; el que no frena sí; un lazo lento igual confirma la quietud; sin pose no es regla de parada.
- **Sesiones:**
  - la L2 automática, con una toma y con dos seguidas, después de una toma real;
  - la L1 automática con el supervisor conectado;
  - el 4 fuera de la envolvente, que se coloca a mano;
  - el 4 sin pose al empezar, que vuelve al operador;
  - el contacto en la colocación, que detiene la sesión.
- **Offset de la L0:** estimación y signo, la habilitación de la L1/L2 y `main` que no arranca la L1 sin L0. También que `--robot-obstaculo` es obligatorio.

## 7. Laboratorio

El protocolo actualizado está en `PROTOCOLO_L0_L2.md`:

```text
python demo_obstaculo_movil.py --modo L0 --robot-obstaculo 4
python demo_obstaculo_movil.py --modo L1 --tomas 3 --intentos 6 --robot-obstaculo 4
python demo_obstaculo_movil.py --modo L2 --tomas 10 --intentos 20 --robot-obstaculo 4
```

- **La L0** se coloca a mano. Mide el offset del 4 y, si difiere más de 3° de la tabla, la consola imprime la corrección propuesta para `config_robotat.py`, que se aplica sólo con el OK de José. Sin una L0 OK, la L1/L2 no arranca.
- **La L1:** el 4 encendido se coloca a mano UNA vez en el centro; los agentes van solos.
- **La L2:** los agentes van solos. El 4 arranca desde donde terminó la toma anterior; sólo en la 1.ª toma, si viene del centro, se lo coloca a mano en su punto del círculo, que imprime la sesión.

## 8. Decisión pendiente: la Fase A

La Fase A es que el 4 se mueva solo. Su único efecto es quitar las tres colocaciones a mano del 4: la L0, el centro de la L1 y la 1.ª toma de la L2.

| opción | qué implica |
|---|---|
| **Ir al laboratorio con la Fase B** | el 4 se coloca a mano en esos tres casos; todo lo demás es automático |
| **Seguir con la Fase A** | ~4–5 h más, con sus propias fallas inyectadas y ensayos: el 4 en movimiento, el enlace, la obediencia, el pulso de verificación de marcador y el offset falso |

## 9. Datos y verificación

`REPORTE_2026-10-07_colocacion_automatica_datos.zip` contiene:
- los 6 `ensayo_L*_auto_*/`, con CSV de tomas, decisiones y obstáculo, `resumen_ensayo.json` y el resumen;
- `revision_adversarial_20261003/` (hallazgos y scripts: `revision_plan_colocacion_20261007.json`, y la revisión del código en `colocacion_fase_b/`);
- `pruebas_fase_20261007.log`, `sha256_codigo_colocacion_20261007.txt` y `scripts/`.

Para verificar:

```text
python scripts/verificar_cifras_colocacion.py . pruebas_fase_20261007.log
```
