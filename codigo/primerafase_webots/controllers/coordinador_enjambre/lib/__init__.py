"""
lib — copia autocontenida (variante para el demo con FÍSICA real de ruedas).

Diferencias respecto a `supervisor_cobertura/lib/`:
  - `swarm_env_skeleton.py` lleva un parche para habilitar
    `modo_poses_externas=True`. En ese modo:
      * El env deja de integrar la cinemática de los agentes; las poses
        provienen del exterior (Webots GPS+Compass).
      * Se expone `inyectar_poses_externas(poses)` para registrar la
        pose POST-paso de cada agente antes de llamar `step()`.
      * Se omite la reflexión elástica en bordes (las paredes las
        impone la física de Webots).
      * Si una pose externa cae fuera de [0, arena_size], se emite un
        WARNING en stderr antes del clip defensivo de la observación
        (sirve para detectar fugas físicas).
  - `concentration_dynamics.py` es idéntico al original.

Esta copia es PARALELA a la de `supervisor_cobertura/`. Cambios en una NO
afectan a la otra; cada controlador es autocontenido.
"""
