# supervisor_cobertura — Demo visual del modelo PPO `RESULTADO_PRIMERO`

Controlador único (supervisor) para visualizar la política MADRL entrenada en
`fase_preliminar2/modelos/tesis_v1/RESULTADO_PRIMERO/modelo_PRIMERO.zip` sobre
Webots R2025a. **No es sim-to-real, no entrena nada, no usa Robotat ni los
controladores MATLAB.** Solo carga la política congelada y mueve los nodos de
Webots por supervisión.

---

## 1. Estructura del controlador

```
supervisor_cobertura/
├── supervisor_cobertura.py     # entry-point que Webots ejecuta
├── README.md                   # este archivo
├── lib/
│   ├── __init__.py
│   ├── concentration_dynamics.py    ← copia desde fase_preliminar2/
│   └── swarm_env_skeleton.py        ← copia + 1 línea de import relativo
└── modelos/
    └── modelo_PRIMERO.zip            ← copia del modelo entrenado
```

El proyecto es **autocontenido**: nada bajo `controllers/` referencia
`../../fase_preliminar2/` ni hace `sys.path.insert` hacia rutas absolutas.
Para regenerar las copias de `lib/`, ver §6.

---

## 2. Intérprete Python que Webots debe usar

Webots invoca el comando configurado en **Tools → Preferences → Python
command**. Ese intérprete debe ser el mismo (o equivalente al) usado durante el
entrenamiento.

### 2.1 Dependencias mínimas

```text
python              3.13
numpy               (cualquiera ≥ 1.26)
torch               2.10 CPU      (no necesita CUDA)
stable_baselines3   2.7.1
gymnasium           reciente
pettingzoo          reciente
```

### 2.2 Verificación rápida

Con el mismo intérprete que apuntará Webots, ejecutar:

```powershell
python -c "import numpy, torch, stable_baselines3, gymnasium, pettingzoo; print('OK')"
```

Si el comando falla, instalar lo que falte:

```powershell
python -m pip install --upgrade numpy torch stable-baselines3 gymnasium pettingzoo
```

### 2.3 Apuntar Webots al intérprete correcto

1. Localizar la ruta absoluta del Python que tiene el stack instalado:
   ```powershell
   python -c "import sys; print(sys.executable)"
   ```
2. En Webots: **Tools → Preferences → General → Python command** → pegar la
   ruta completa al `.exe`. Por ejemplo:
   ```
   C:\Users\velas\AppData\Local\Programs\Python\Python313\python.exe
   ```
3. Reiniciar Webots.

---

## 3. Cómo correr el demo

1. Abrir `worlds/lab_robotat.wbt` en Webots R2025a.
2. Verificar que se ven: 5 Pololus en el plano + 3 esferas (R/G/B) a z=0.12.
3. Pulsar **Play** (▶) — la consola debe imprimir una línea similar a:
   ```
   [SupervisorCobertura] listo  timestep=10 ms  pasos_webots_por_dt=10  ...
   ```
4. Los robots empiezan a moverse según la política. Los hotspots derivan con
   reflexión en bordes. Al cumplirse `max_steps=500`, el env se resetea y el
   demo continúa indefinidamente.

---

## 4. Decisiones de diseño relevantes

### 4.1 Cinemática pura (no física)

El proto `Pololu3piKin.proto` define el robot con `physics NULL`, sin
`HingeJoint`/`BallJoint`/`RotationalMotor` y sin `boundingObject`. Las llantas
y caster balls son `Pose` + `Shape` decorativos: no giran sobre sí mismas, pero
el cuerpo entero rota como bloque cuando el supervisor escribe el campo
`rotation`. Eso es suficiente para un demo visual y elimina el riesgo de que
fuerzas residuales contradigan las poses dictadas por el supervisor.

### 4.2 Marco local del robot y offset angular

El proto preserva la orientación geométrica del `Pololu3pi.proto` original:
ruedas en `x = ±0.07` (eje X local) y caster balls en `y = ±0.06` (eje Y
local). Por tracción diferencial, "adelante" del robot es **+Y local**.

El env, en cambio, sigue la convención matemática estándar: θ=0 ⇒ heading
+X. Para conciliar ambos marcos, el supervisor aplica un offset constante al
construir el `rotation` del nodo de Webots:

```python
OFFSET_PROTO_RAD = -math.pi / 2
rotation = (0, 0, 1, theta_env + OFFSET_PROTO_RAD)
```

Si al abrir la simulación los robots aparentan moverse "de costado", el offset
está equivocado: cambiar el signo o el valor de `OFFSET_PROTO_RAD` en
`supervisor_cobertura.py` (4 valores razonables: `0`, `±π/2`, `π`).

### 4.3 Mapeo de marcos espaciales

El env vive en `[0, 3] × [0, 3]` con origen en la esquina inferior izquierda;
Webots usa origen centrado en `[-1.5, 1.5] × [-1.5, 1.5]`. Translación:

```python
x_webots = x_env - 1.5
y_webots = y_env - 1.5
```

(Misma transformación para hotspots.) La z queda fija: 0 para robots (la
altura intrínseca del proto la pone sobre el piso), 0.12 m para esferas.

### 4.4 Sincronía animación ↔ dt del env

El `.wbt` declara `basicTimeStep 10` ms. El env corre con `dt = 0.1` s.
Cada iteración del loop hace `env.step(...)` y luego avanza Webots por
`pasos_webots_por_dt = 100/10 = 10` ticks, manteniendo la cadencia real-time
exacta del entrenamiento (1 paso del env = 100 ms simulados de Webots).

Si se quiere animar más rápido o más lento, cambiar `basicTimeStep` en el
`.wbt`. El supervisor valida que el ratio sea entero al arrancar y aborta si
no lo es.

### 4.5 `domain_rand=False` en el demo

El modelo se entrenó con `domain_rand=True` (ruido gaussiano sobre poses +
fricción aleatoria). En el demo se desactiva (`DOMAIN_RAND_DEMO = False` en
`supervisor_cobertura.py`) para evitar jitter visual. La política se comporta
ligeramente diferente — no se nota a la vista, pero queda documentado. Para
reproducir EXACTAMENTE las condiciones de entrenamiento, cambiar la constante
a `True`.

### 4.6 `deterministic=True` en `predict`

La política se ejecuta determinísticamente. La estocasticidad del demo viene
ENTERAMENTE de las trayectorias aleatorias de los hotspots (que sí dependen
del RNG del env).

### 4.7 No se reconstruye la observación

El supervisor usa el dict que retornan `env.reset` y `env.step` sin tocar el
vector D_OBS=24. Eso garantiza que la entrada a la red sea la misma que
durante el entrenamiento (mean embedding, AoI sectorial, normalizaciones).

---

## 5. Configuración del env en el demo

| Parámetro      | Valor          | Fuente                                            |
| -------------- | -------------- | ------------------------------------------------- |
| `n_agents`     | 5              | `RESULTADO_PRIMERO/config_entrenamiento.json`     |
| `arena_size`   | (3.0, 3.0)     | idem                                              |
| `max_steps`    | 500            | idem (clave `max_steps_ep` en el JSON)            |
| `comm_radius`  | 1.0            | idem                                              |
| `dt`           | 0.1            | default del env (no override en el JSON)          |
| `n_hotspots`   | 3              | default del env (no override en el JSON)          |
| `seed`         | 42             | idem                                              |
| `domain_rand`  | **False**      | override del demo (ver §4.5)                      |

---

## 6. Regenerar las copias en `lib/` (si cambia el upstream)

Si `fase_preliminar2/concentration_dynamics.py` o `swarm_env_skeleton.py`
cambian, regenerar las copias:

```powershell
Copy-Item ..\..\..\fase_preliminar2\concentration_dynamics.py lib\
Copy-Item ..\..\..\fase_preliminar2\swarm_env_skeleton.py    lib\
```

Después editar **una sola línea** en `lib\swarm_env_skeleton.py`:

```python
# Cambiar:
from concentration_dynamics import (...)
# Por:
from .concentration_dynamics import (...)
```

Para regenerar el modelo:

```powershell
Copy-Item ..\..\..\fase_preliminar2\modelos\tesis_v1\RESULTADO_PRIMERO\modelo_PRIMERO.zip modelos\
```

---

## 7. Troubleshooting

| Síntoma                                                  | Causa probable                                                 | Fix                                                                              |
| -------------------------------------------------------- | -------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `ModuleNotFoundError: stable_baselines3`                 | Webots apunta a un Python sin sb3                              | Reapuntar Python command (§2.3)                                                  |
| `RuntimeError: No se encontró el nodo Webots con DEF...` | El `.wbt` no tiene el DEF esperado                             | Verificar que los nombres en el `.wbt` coincidan con `DEF_AGENTES`/`DEF_OBJETIVOS` |
| Robots aparecen pero no se mueven                        | Webots no está en Play, o el controlador crasheó               | Ver consola de Webots                                                            |
| Robots se mueven "de costado" 90°                        | Offset angular incorrecto                                      | Ajustar `OFFSET_PROTO_RAD` en `supervisor_cobertura.py` (§4.2)                   |
| Robots atraviesan paredes                                | Esperado: son cinemáticos. El env aplica reflexión interna     | No-op (la reflexión la maneja el env, no Webots)                                 |
| `ValueError: basicTimeStep ... no divide exactamente...` | El `.wbt` tiene un `basicTimeStep` que no divide `dt_env=100ms` | Restaurar `basicTimeStep 10` en `WorldInfo`                                      |
