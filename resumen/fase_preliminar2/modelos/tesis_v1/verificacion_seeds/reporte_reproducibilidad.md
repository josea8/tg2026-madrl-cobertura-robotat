# Reporte de Reproducibilidad — Trial 13 (tesis_v1)

*Generado: 2026-04-17 21:17:06*

## Contexto

El Trial 13 del estudio Optuna `tesis_v1` obtuvo `eval_rew_mean = -1.5096`, un outlier de 16.7 puntos por encima del segundo mejor (-18.22). Trial 18, con hiperparámetros casi idénticos, fue **podado** en step 10k con ep_rew ≈ -90. Este experimento verifica si el valor del Trial 13 es reproducible bajo 3 seeds independientes (42, 123, 777).

## Configuración

- **Hiperparámetros:** exactos del Trial 13 (`modelos/tesis_v1/metadata_trials/trial_013.json`)
- **n_agentes:** 5 — **max_steps_ep:** 500 — **n_envs:** 4 — **domain_rand:** True (train) / False (eval)
- **Presupuesto por seed:** 100,000 steps
- **Evaluación:** 20 stream-episodios deterministas
- **Arquitectura de env:** idéntica al flujo de trials de Optuna (sin VecNormalize) para comparabilidad directa

## Resultados por seed

| Seed | eval_rew_mean | eval_rew_std | ep_len_mean | cobertura_aoi_mean | Duración (s) |
|-----:|--------------:|-------------:|------------:|-------------------:|-------------:|
| 42 | -10.350 | 12.172 | 500.0 | 0.5546 | 139.1 |
| 123 | -31.939 | 31.088 | 500.0 | 0.5269 | 124.7 |
| 777 | -58.878 | 59.489 | 500.0 | 0.4509 | 119.5 |

**Trial 13 original (referencia):** -1.5096

## Estadísticos agregados

- **Media (μ):** -33.722
- **Desviación estándar (σ):** 19.852
- **Rango:** [-58.878, -10.350]
- **Coeficiente de variación (σ/|μ|):** 0.589

## Criterio de decisión

| Criterio | Condición | Acción |
|----------|-----------|--------|
| 🟢 VERDE | σ/|μ| < 0.5 AND todas ∈ [-20, 20] | Proceder a 5M |
| 🟡 AMARILLO | 0.5 ≤ σ/|μ| < 1.5 AND ninguna < -50 | Discutir |
| 🔴 ROJO | σ/|μ| ≥ 1.5 OR alguna < -50 | Recalibrar Optuna |

### Resultado: **ROJO**

La reproducibilidad es insuficiente. Trial 13 parece haber sido un outlier por seed. **No proceder al Día 2.** Recalibrar:
  1. Relanzar Optuna (estudio `tesis_v2`) con 20 trials adicionales.
  2. Restringir `λ_cbf ∈ [1.0, 5.0]` (por encima de 5 es veneno).
  3. Restringir `n_steps_exp ∈ [7, 9]` (128–512, donde viven los mejores).
  4. Considerar correr cada trial con 2 seeds y promediar para mitigar varianza inter-seed.

## Figura

![Curvas de aprendizaje](curvas_3_seeds.png)

## Archivos generados

- `seed_42/modelo_final.zip` — checkpoint entrenado
- `seed_42/metricas.json` — métricas de evaluación
- `seed_42/curva_aprendizaje.csv` — curva ep_rew_mean vs timesteps
- `seed_42/tensorboard/` — logs para TensorBoard
- `seed_123/modelo_final.zip` — checkpoint entrenado
- `seed_123/metricas.json` — métricas de evaluación
- `seed_123/curva_aprendizaje.csv` — curva ep_rew_mean vs timesteps
- `seed_123/tensorboard/` — logs para TensorBoard
- `seed_777/modelo_final.zip` — checkpoint entrenado
- `seed_777/metricas.json` — métricas de evaluación
- `seed_777/curva_aprendizaje.csv` — curva ep_rew_mean vs timesteps
- `seed_777/tensorboard/` — logs para TensorBoard