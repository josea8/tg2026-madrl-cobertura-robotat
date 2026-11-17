"""
lib — copia autocontenida para el EXPERIMENTO C (bordes bloqueantes).

Base: copia de `experimentos/expB_reflexiones/lib/` (que a su vez copia el env
de entrenamiento y ya trae el contador de reflexiones del Experimento B, con
fidelidad de protocolo verificada: replica 0.6813 ± 0.0200 exacto).

Instrumentación agregada respecto a expB (solo en esta copia):
  - Parámetro `modo_borde` ∈ {"reflexion", "bloqueante"} en el constructor
    de `CyanobacteriaMonitoringEnv` (default "reflexion" → regresión cero).
      * "reflexion"   : comportamiento original — reflexión elástica del
                        agente en los bordes (θ → π−θ / θ → −θ).
      * "bloqueante"  : la posición integrada se RECORTA a [0,Wx]×[0,Wy] y
                        θ queda EXACTAMENTE como la integró la cinemática
                        (sin inversión). Modela una pared sólida que frena
                        el avance sin reorientar al robot — la condición
                        que impone Webots y el Robotat físico.
  - `_contador_recortes`: Dict[str, int] — pasos en los que el agente fue
    recortado por un borde bloqueante (por episodio).
  - Property `contador_recortes`.

IMPORTANTE — lo que NO cambia en modo "bloqueante":
  - El orden de operaciones del `step()` (snapshot C_prev/aoi_prev antes de
    mover, C_curr con targets aún en t, etc.).
  - La dinámica de los OBJETIVOS: los hotspots conservan su reflexión
    elástica en ambos modos. Solo cambian los bordes de los AGENTES.
  - El contador de reflexiones del Experimento B (sigue activo; en modo
    "bloqueante" queda naturalmente en 0 porque no se ejecuta esa rama).
"""
