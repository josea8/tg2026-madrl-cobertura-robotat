"""
lib — copia autocontenida para el EXPERIMENTO B (conteo de reflexiones).

Base: copia de `controllers/supervisor_cobertura/lib/` (idéntica al env de
entrenamiento en `fase_preliminar2/`, salvo el import relativo).

Instrumentación agregada (solo en esta copia):
  - `CyanobacteriaMonitoringEnv._contador_reflexiones`: Dict[str, int] que
    cuenta, por agente y por episodio, cuántas veces se ejecutó una rama de
    reflexión elástica de pared en `_integrate_kinematics`. Un cruce
    simultáneo de pared vertical Y horizontal (esquina) cuenta como 2.
  - Se reinicia a ceros en cada `reset()`.
  - Property de lectura `contador_reflexiones`.

El propósito es cuantificar cuántas veces la política entrenada DEPENDE de la
reflexión elástica idealizada — dinámica que NO existe en Webots ni en el
Robotat físico (paredes sólidas que bloquean). Ver Experimento A (atascos).
"""
