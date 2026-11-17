# supervisor_fisica — Demo con FÍSICA REAL de ruedas (1 robot)

Controlador único para visualizar la política `RESULTADO_PRIMERO` con
**dinámica de ruedas real** en Webots R2025a. El robot ya no se teletransporta:
recibe `(v, ω)` de la política, los convierte a velocidades angulares de rueda
y el movimiento **emerge de la física de Webots**.

Demo PARALELO al cinemático (`supervisor_cobertura`). No comparte código en
caliente: cada controlador es autocontenido. La versión cinemática queda
intacta y funcional.

> **Estado**: corrida de calibración con **1 solo robot**. Aislar y validar
> signos de motor, asignación motor_1/motor_2 y mapeos de marco. Escalar a 5
> robots es paso posterior.

---

## 1. Estructura

```
supervisor_fisica/
├── supervisor_fisica.py     # entry-point que Webots ejecuta
├── README.md                # este archivo
├── lib/                     # copia paralela de fase_preliminar2 con parche
│   ├── __init__.py
│   ├── concentration_dynamics.py
│   └── swarm_env_skeleton.py  ← + modo_poses_externas, inyectar_poses_externas
└── modelos/
    └── modelo_PRIMERO.zip
```

---

## 2. Cambios al env (solo en esta copia de `lib/`)

El original en `fase_preliminar2/` NO se toca. El parche es de 3 puntos:

1. **Constructor**: nuevo parámetro `modo_poses_externas: bool = False`.
2. **Método público nuevo**: `inyectar_poses_externas(poses)`:
   - Solo válido si `modo_poses_externas=True`; raise si no.
   - Registra la pose POST-paso (estado t+1) de cada agente en un buffer.
   - **Warning en stderr** si la pose cae fuera de `[0, arena_size]` —
     detecta fugas físicas (robot atravesó pared o se desincronizaron los
     marcos).
3. **Rama nueva en `_integrate_kinematics`**: si modo externo, no integra ni
   refleja en bordes. Solo escribe `_estados[a] = [x_ext, y_ext, θ_ext,
   v_cmd, w_cmd]` (las paredes las maneja Webots).

El orden crítico del `step()` (snapshot C_prev / aoi_local_prev → mover →
C_curr → reward → field.step → AoI update → obs) **se preserva**: lo único
que cambia es que el "mover" se reemplaza por leer la pose ya producida por
Webots.

---

## 3. Modelo cinemático del diferencial

Derivado en clase de Robótica 1 (MT3005, UVG) por restricciones de
rodamiento / no-deslizamiento, metodología `f = R_B(θ)·A⁺·B·v`. El **modelo
directo** (ruedas → cuerpo):

```
v = (r/2)·(φ̇_R + φ̇_L)
ω = (r/(2·ℓ))·(φ̇_R − φ̇_L)
```

El controlador usa el **inverso** (política → ruedas):

```
φ̇_R = (v + ℓ·ω) / r
φ̇_L = (v − ℓ·ω) / r
```

| Parámetro | Valor | Origen |
|---|---|---|
| `r` (radio rueda) | **0.035 m** | `Cylinder { radius 0.035 }` del .wbt |
| `ℓ` (medio eje) | **0.07 m** | anchors `±0.07` del .wbt |

Ambos vienen de la **geometría del .wbt**, NO del hardware real del Pololu
3pi+ (que es r=0.032, ℓ=0.041). El demo simula la geometría que Webots
realmente está calculando, no el robot físico.

### 3.1 Unidades — punto crítico

`RotationalMotor.setVelocity(...)` de Webots **recibe rad/s directamente**.
El round-trip a rpm que aparece en `pololu3pi_controller.m` solo aplica
para el Pololu físico vía `robotat/` (Fase 4, no este demo). En Webots
**NO se convierte a rpm**.

### 3.2 maxVelocity

Rueda máxima exigida por (V_MAX, OMEGA_MAX):
```
(V_MAX + ℓ·OMEGA_MAX)/r = (0.31 + 0.07·6.2832)/0.035 ≈ 21.4 rad/s
```
El motor declara `maxVelocity 84` explícito en el .wbt — entra holgado.

---

## 4. Modos de calibración — `MODO` ∈ {`"actuacion"`, `"pose"`, `"politica"`}

El controlador tiene un dispatcher en la cabecera (`MODO` en línea ~91 de
`supervisor_fisica.py`) para alternar entre tres bucles de operación. Default
arranca en **`"actuacion"`**: el primer `Play` NO depende de signos correctos
ni de un offset de heading bien elegido — se prueba el lazo de actuación
primero, después la pose, y solo al final se cierra el lazo con la política.

### 4.1 `MODO = "actuacion"` — lazo abierto, sin política

- No instancia env ni carga modelo.
- Comanda **(V_TEST, OMEGA_TEST)** fijos directo a las ruedas vía
  `convertir_velocidades_a_ruedas` + `SIGNO_MOTOR_*`.
- Cada `PERIODO_LOG_S` segundos (default 1 s) imprime:
  ```
  [actuacion] cmd=(v=+0.100 m/s, ω=+0.000 rad/s)
              ruedas=(φ̇_R=+2.857, φ̇_L=+2.857) rad/s
              pose=(x=+0.500, y=+0.500, θ=+0.0°)
  ```

**Qué probar y qué te dice cada prueba:**

| Probá con | Comportamiento esperado | Si falla, indica |
|---|---|---|
| `V_TEST=0.1`, `OMEGA_TEST=0.0` | Avanza en línea recta hacia el +heading del robot | Si retrocede → **ambos signos invertidos**. Si gira en círculo → **un solo signo invertido**. Si no se mueve → motor mal nombrado o `maxVelocity` en default 10. |
| `V_TEST=0.0`, `OMEGA_TEST=1.0` | Gira en su lugar **a la izquierda** (CCW visto desde arriba) | Si gira a la derecha → **ambos signos invertidos** o convención de ω mal. |
| `V_TEST=0.1`, `OMEGA_TEST=0.5` | Avanza describiendo una curva a la izquierda | Sirve de cross-check del par anterior. |

Aislalo aquí. **NO cambies `OFFSET_HEADING_RAD` en este modo** — el heading
solo se usa para imprimir, no afecta a los motores.

### 4.2 `MODO = "pose"` — solo lectura, motores apagados

- No instancia env ni carga modelo.
- Mantiene motores en velocidad 0; el robot queda quieto salvo que vos lo
  muevas a mano en el editor de Webots (clic + arrastre).
- Cada `PERIODO_LOG_S` segundos imprime las tres lecturas:
  ```
  [pose] GPS=(x_w=+0.000, y_w=+0.000, z_w=+0.020) m
         COMPASS=(+0.000, +1.000, +0.000)
         ENV=(x=+1.500, y=+1.500, θ=+0.0°)
  ```

**Qué probar:**

| Acción manual en Webots | Lectura esperada (con `OFFSET_HEADING_RAD=0`) | Si no coincide, ajustar |
|---|---|---|
| Mover el robot al centro `(0, 0)` mundo | `ENV=(x≈1.500, y≈1.500, ...)` | Si `(x_env, y_env) ≠ (1.5, 1.5)` → el mapeo `+OFFSET_X/+OFFSET_Y` no se aplica bien (no debería pasar — son constantes). |
| Apuntar el robot hacia `+X` global (heading hacia "este" en el viewport) | `θ_env ≈ 0°` | Si `θ_env ≈ +90°` → `OFFSET_HEADING_RAD = -π/2`. Si `≈ -90°` → `+π/2`. Si `≈ ±180°` → `π`. |
| Apuntar hacia `+Y` global | `θ_env ≈ +90°` | Cross-check del item anterior. |

Esto aísla **`OFFSET_HEADING_RAD`**. Una vez calibrado, anotalo y pasá al
siguiente modo.

### 4.2b `MODO = "lote"` — Experimento A (corrida por lotes con detector de atasco)

Lazo cerrado idéntico a `"politica"`, pero:

- Corre `N_EPISODIOS_LOTE = 18` episodios con semillas fijas
  `SEMILLAS_LOTE = [420000..420017]` (misma familia que el protocolo de
  evaluación de RESULTADO_PRIMERO: `seed_ep = 42·10000 + i`).
- Al inicio de cada episodio **teletransporta el robot** a la pose inicial
  sorteada por el env (una única vez, entre episodios — equivale a
  reposicionarlo a mano). Sin esto, cada episodio arrancaría donde quedó el
  anterior (p. ej. pegado a la pared) y el lote quedaría contaminado.
- **Detector de atasco — SOLO REGISTRO** (no interviene): atascado si
  `‖Δpos‖ < 1 mm` y `|Δθ| < 0.5°` por 20 pasos consecutivos (= 2.0 s).
- Salidas: `resultados/experimento_A_atascos.csv` (fila por episodio:
  semilla, atascado, paso y posición del atasco, si la política comandó
  `v<0` durante el atasco) y `resultados/resumen_experimento_A.txt`.
- Al terminar: cierra Webots si `SALIR_AL_TERMINAR_LOTE=True` (necesario
  para corridas headless con `webots --batch`), si no pausa.

Corrida headless (sin GUI):

```powershell
& "C:\Program Files\Webots\msys64\mingw64\bin\webots.exe" --batch --mode=fast --no-rendering --stdout --stderr worlds\lab_robotat_fisica.wbt
```

### 4.3 `MODO = "politica"` — lazo cerrado, producción

- Instancia env (`modo_poses_externas=True`), carga modelo, hace primer
  reset + alineación con la pose física.
- Bucle: predict → ruedas → física → pose → inyectar → step env → mover
  hotspots. Lo del demo "real".
- Si `truncs[robot_0]` → reset + re-alineación.

Solo entrar acá **después** de validar `4.1` y `4.2`.

### 4.4 Secuencia recomendada (calibración en orden)

```text
1. MODO = "actuacion"
   ├─ V_TEST=0.1, OMEGA_TEST=0.0  → ajustar SIGNO_MOTOR_1, SIGNO_MOTOR_2.
   ├─ V_TEST=0.0, OMEGA_TEST=1.0  → confirmar sentido de giro.
   └─ V_TEST=0.1, OMEGA_TEST=0.5  → cross-check trayectoria curva.

2. MODO = "pose"
   ├─ Mover robot al (0,0) mundo → confirmar (1.5, 1.5) env.
   ├─ Apuntar a +X global       → ajustar OFFSET_HEADING_RAD.
   └─ Apuntar a +Y global       → cross-check.

3. MODO = "politica"
   └─ Si el robot ahora persigue las esferas: calibración OK.
```

**Regla**: ajustar **una** constante a la vez, volver a probar el modo
correspondiente, anotar. Si tocás tres a la vez y algo "anda", no vas a
saber cuál arregló qué.

---

## 5. Constantes calibrables (resumen)

| Constante | Default | Modo donde se valida |
|---|---|---|
| `SIGNO_MOTOR_1` | `+1` | `"actuacion"` (rueda derecha) |
| `SIGNO_MOTOR_2` | `+1` | `"actuacion"` (rueda izquierda) |
| `OFFSET_HEADING_RAD` | `0.0` | `"pose"` |
| `V_TEST` | `0.1` m/s | `"actuacion"` (comando de prueba) |
| `OMEGA_TEST` | `0.0` rad/s | `"actuacion"` (comando de prueba) |
| `PERIODO_LOG_S` | `1.0` s | (cadencia de print en `"actuacion"` y `"pose"`) |

---

## 6. Configuración del env

| Parámetro              | Valor   | Notas |
|------------------------|---------|---|
| `n_agents`             | **1**   | corrida de calibración |
| `arena_size`           | (3, 3)  | igual al entrenamiento |
| `max_steps`            | 500     | igual al entrenamiento |
| `comm_radius`          | 1.0     | igual al entrenamiento (irrelevante con 1 agente) |
| `dt`                   | 0.1     | igual al entrenamiento |
| `n_hotspots`           | 3       | igual al entrenamiento |
| `seed`                 | 42      | igual al entrenamiento |
| `domain_rand`          | **False** | la fricción real la pone Webots; sumar fricción simulada distorsionaría el delta sim-to-real |
| `modo_poses_externas`  | **True**  | habilita la rama del parche |

Con `n_agents=1`:
- `neighbor_embedding` (8 dims) = 0 — sin vecinos visibles.
- `p_cbf` = 0 — sin riesgo de colisión inter-agente.
- El robot solo persigue hotspots y explora; **no coordina** (esperado, no
  es bug).

---

## 7. Loop por iteración (resumen, modo `"politica"`)

```python
1. acción = modelo.predict(obs_actual, deterministic=True)
2. φ̇_R, φ̇_L = (v + ℓω)/r, (v − ℓω)/r          # rad/s, directo a setVelocity
3. motor_1.setVelocity(SIGNO_MOTOR_1 · φ̇_R)
   motor_2.setVelocity(SIGNO_MOTOR_2 · φ̇_L)
4. supervisor.step(N_TICKS)                       # Webots avanza la física
5. pose = (GPS, Compass) → marco env
6. env.inyectar_poses_externas({"robot_0": pose})
7. obs_actual = env.step({"robot_0": acción})    # incluye field.step, AoI
8. mover esferas hotspot por setSFVec3f(...)
9. si truncs[robot_0]: reset + re-alinear poses
```

---

## 8. Cómo correr

1. Configurar **Tools → Preferences → Python command** con el Python que
   tenga `numpy + torch (CPU) + stable_baselines3 + gymnasium + pettingzoo`.
   (Ver el README del demo cinemático para la verificación rápida.)
2. Abrir `worlds/lab_robotat_fisica.wbt` en Webots R2025a.
3. **Primera vez** (con `MODO="actuacion"` default): pulsar **Play** (▶).
   La consola debe imprimir:
   ```
   [SupervisorFisica][MODO=actuacion] LAZO ABIERTO  v_test=+0.100 m/s  ω_test=+0.000 rad/s  ...
   [actuacion] cmd=(v=+0.100, ω=+0.000)  ruedas=(...)  pose=(...)
   ```
   Seguir la **secuencia de calibración** descrita en §4.4: `"actuacion"`
   → `"pose"` → `"politica"`. Para cambiar de modo: editar la constante
   `MODO` en `supervisor_fisica.py` y reiniciar la simulación (Ctrl+Shift+T
   en Webots, o pause → revert).
4. Verificación visual mínima (en `MODO="politica"`):
   - El robot se mueve por giro de ruedas (no teletransporte).
   - Si lo pausás y lo empujás en el editor, debería resistir/caer como
     cuerpo físico (lo que prueba que la física está activa).
   - Las 3 esferas R/G/B se desplazan suavemente, rebotando en los bordes.

---

## 9. Troubleshooting

| Síntoma | Causa probable | Fix |
|---|---|---|
| Robot se queda pegado a una pared en `MODO="politica"` | Signos de motor y/o offset de heading no calibrados: la política manda comandos que la física interpreta en otro marco | NO calibrar a ciegas. Pasar a `MODO="actuacion"` y seguir §4 |
| `ValueError: MODO=... inválido` | Typo en la constante `MODO` | Valor exacto, sin mayúsculas, debe ser `"actuacion"`, `"pose"` o `"politica"` |
| `ModuleNotFoundError: stable_baselines3` | Python command incorrecto | Reapuntar (README cinemático §2) |
| `No se encontraron los motores motor_1/motor_2` | El .wbt no tiene esos `RotationalMotor` con esos nombres exactos | Restaurar `name "motor_1"` y `name "motor_2"` en el .wbt |
| El robot avanza al revés | Signos invertidos | Cambiar `SIGNO_MOTOR_1` y/o `SIGNO_MOTOR_2` a `-1` |
| El robot solo gira en lugar de avanzar | Un solo motor invertido | Probar `SIGNO_MOTOR_1 = -1` (o `SIGNO_MOTOR_2 = -1`), no ambos |
| El robot se mueve "de costado" respecto a su heading | Offset de heading | Ajustar `OFFSET_HEADING_RAD` (probar `π/2`, `-π/2`, `π`) |
| Warning `[modo_poses_externas] Pose ... fuera de [0, arena_size]` | El robot atravesó una pared (física), o los marcos están desincronizados | Si pasa una vez aislada: probable bug físico, no-op. Si pasa siempre: revisar mapeo de marcos `webots_a_env_xy` |
| `basicTimeStep ... no divide exactamente dt_env` | `.wbt` con `basicTimeStep` que no divide 100 ms | Restaurar `basicTimeStep 10` en el WorldInfo |
| Sensores devuelven NaN al inicio | Warm-up insuficiente | El controlador ya hace un `supervisor.step` antes del primer reset; si persiste, agregar un segundo step |
| Robot demasiado lento / queda parado | `maxVelocity` heredado del default (10 rad/s) | Verificar que el `.wbt` tenga `maxVelocity 84` en ambos `RotationalMotor` |

---

## 10. Filtro CBF de ejecución (safety shield)

`lib/filtro_cbf.py` implementa un filtro CBF con **punto de mira** (look-ahead
ℓa = 0.05 m) que se interpone entre la política y los motores cuando
`CBF_ACTIVO=True` (default `False` → regresión cero, el módulo ni se importa).
Aplica en `"politica"` y `"lote"` (no es un MODO). Formulación, matrices del
QP y los dos casos degenerados documentados (esquina-bisectriz y pared plana
con θ perpendicular) están en el docstring del módulo. Solver: scipy SLSQP.

- La acción que recibe el env es la **ejecutada** (filtrada), no la nominal.
- En lote, las salidas llevan sufijo `_cbf` para no pisar la corrida baseline
  (los originales están respaldados con sufijo `_original`).
- Columnas nuevas del CSV (registradas siempre): `intervenciones_cbf`,
  `magnitud_media_modificacion`, `distancia_minima_centro_a_pared`.
- Test unitario standalone: `python test_filtro_cbf.py` (6 casos, incluye los
  dos degenerados).

**Nota sobre `D_SEGURA_PUNTO = 0.18`**: el margen efectivo del centro a la
pared es ~0.13 m con el robot de frente. La configuración límite es el robot
**retrocediendo hacia la pared** (mirando hacia afuera): el punto de mira
queda del lado interior y el chasis se acerca hasta ~0.055 m de holgura
respecto de la pared. Suficiente, pero es lo que vigila la columna
`distancia_minima_centro_a_pared`; si saliera justa, subir `D_SEGURA_PUNTO`
(no tocar la formulación).

## 11. Limitaciones conocidas

- **1 robot solamente**: escalar a 5 requiere replantear la arquitectura
  (un Supervisor solo no puede manejar motores de OTROS Robots). Las
  opciones son: Emitter/Receiver, un controlador por robot + servidor
  central, o un MultiAgentRobot proto. No parte de esta entrega.
- **Sin coordinación visible**: ver §5. Esperable con 1 agente.
- **`maxVelocity` de la rueda no modela el comportamiento del Pololu real**:
  la rueda real satura por torque del RP2040 mucho antes; este demo no
  modela ese límite. Para evaluar Sim-to-Real serio, ese y otros gaps
  (slip, inercia, deadband del motor) habría que incluirlos.
