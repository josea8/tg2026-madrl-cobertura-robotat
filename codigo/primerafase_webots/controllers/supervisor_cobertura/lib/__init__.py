"""
lib — copia autocontenida de los módulos del entorno de entrenamiento.

Contiene:
  - concentration_dynamics.py : DynamicTargetSimulator + MeanEmbeddingEncoder.
  - swarm_env_skeleton.py     : CyanobacteriaMonitoringEnv (PettingZoo ParallelEnv).

Esta copia existe para que el proyecto Webots sea autocontenido y no dependa de
rutas relativas a `fase_preliminar2/`. La única edición respecto al original es
el cambio de `from concentration_dynamics ...` a `from .concentration_dynamics ...`
en `swarm_env_skeleton.py` (import relativo dentro del paquete `lib`).
"""
