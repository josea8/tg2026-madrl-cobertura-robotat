# Reporte Final — Entrenamiento 5M (tesis_v1, Trial 13)

*Generado: 2026-04-18 22:05:09*

## Contexto

Corrida final del pipeline tesis_v1 con los hiperparámetros del Trial 13 (mejores_hiperparametros.json) validados previamente:

- **λ_cbf = 2.9655** (confirmado por A/B test: 5.0 degrada ambas métricas)
- **learning_rate = 6.86e-05**
- **γ = 0.9845**   **gae_λ = 0.9608**
- **n_steps = 128**   **batch_size = 64**   **n_epochs = 13**
- **ent_coef = 0.0229**   **clip_range = 0.206**

## Configuración de entrenamiento

- **Steps totales:** 5,000,000
- **Agentes:** 5  —  **max_steps_ep:** 500  —  **n_envs:** 4  —  **seed:** 42
- **EvalCallback:** cada 100,000 steps × 10 episodios deterministas
- **Checkpoints:** cada 500,000 steps
- **VecNormalize activo** (obs + reward) — stats guardados para inferencia

## Métricas finales (50 episodios deterministas, sin domain_rand)

| Métrica | Media ± σ | min | max |
|---------|----------:|----:|----:|
| Cobertura AoI final | **0.626** ± 0.028 | 0.536 | 0.680 |
| Pares en colisión / ep | **0.98** ± 1.05 | 0 | 5 |
| Distancia recorrida [m] | 15.34 ± 0.05 | 15.19 | 15.42 |
| Step al cruzar cob=0.5 | 215 ± 38 | 139 | 309 |

## Evolución con el presupuesto de entrenamiento

| Presupuesto | Cobertura AoI (μ±σ) | Pares colisión/ep (μ±σ) | Step a cob=0.5 (μ) | Distancia recorrida (μ) |
|------------:|--------------------:|-----------------------:|-------------------:|------------------------:|
| 100k (seed 42) | 0.698±0.018 | 0.53±0.72 | 153 | 15.34 |
| 200k (variante A) | 0.680±0.021 | 0.20±0.48 | 167 | 15.22 |
| **5M (final)** | **0.626±0.028** | **0.98±1.05** | 215 | 15.34 |

## Criterio de éxito

| Categoría | Condición |
|-----------|-----------|
| 🟢 LISTO PARA SIM2REAL | cob > 0.80 con std < 0.08 AND col < 0.1 |
| 🟡 RESULTADO DEFENDIBLE | cobertura 0.70 – 0.80 |
| 🔴 NECESITA RECALIBRACIÓN | cob < 0.70 OR col > 0.3 |

### Resultado: **NECESITA_RECALIBRACION**

Falla significativa (cobertura 0.626 < 0.70; colisiones 0.98 > 0.3). **NECESITA RECALIBRACIÓN.** Considerar: tesis_v2 con espacio Optuna reducido y ajuste manual de λ_entropy/λ_cbf.

## Curva de aprendizaje

![Curva 5M](curva_aprendizaje.png)

## Artefactos generados

- `modelo_final.zip` — modelo PPO al final de los 5M steps
- `mejor_modelo/best_model.zip` — modelo con mejor eval_rew (EvalCallback)
- `vecnorm/vecnorm_final.pkl` — estadísticas de normalización (críticas para sim2real)
- `checkpoints/ppo_5M_{500000,1000000,...}.zip` — checkpoints cada 500k
- `curva_5M.csv` — snapshot cada 100k (rewards, cobertura, colisiones)
- `metricas_finales.json` — datos crudos de los 50 episodios de eval
- `tensorboard/` — logs para `tensorboard --logdir`
- `entrenamiento_5M.log` — log de la corrida

## Próximos pasos

```powershell
# Visualizar curvas en TensorBoard
python -m tensorboard.main --logdir .\modelos\tesis_v1\entrenamiento_final_5M\tensorboard --port 6006
```