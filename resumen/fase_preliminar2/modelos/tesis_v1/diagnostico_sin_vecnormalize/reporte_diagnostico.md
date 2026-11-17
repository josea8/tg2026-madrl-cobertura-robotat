# Diagnóstico SIN VecNormalize — Trial 13, seed 42, 500k steps

*Generado: 2026-04-23 12:42:44*

## Objetivo

Aislar el efecto de VecNormalize. La corrida 5M con VecNormalize dio un modelo peor (cob=0.626, col=0.98) que el 200k del A/B test SIN VecNormalize (cob=0.680, col=0.20). Este experimento entrena 500k steps con idéntica configuración EXCEPTO que omitimos VecNormalize, y evalúa cada 100k.

## Configuración

- **Steps totales:** 500,000
- **Checkpoints cada:** 100,000 timesteps
- **Episodios de eval por checkpoint:** 20 (deterministas, SIN domain_rand)
- **n_agentes:** 5  —  **max_steps_ep:** 500  —  **n_envs:** 4  —  **seed:** 42
- **Duración entrenamiento:** 0.0 min
- **Duración evaluación total:** 2.2 min

## Tabla por checkpoint

| Step | Cobertura AoI (μ±σ) | Pares colisión/ep (μ±σ) | Distancia (μ) |
|-----:|--------------------:|------------------------:|--------------:|
| 100k | 0.707±0.017 | 0.55±0.74 | 15.40 |
| 200k | 0.682±0.018 | 0.15±0.36 | 15.19 |
| 300k | 0.674±0.019 | 0.85±0.85 | 15.03 |
| 400k | 0.669±0.018 | 0.80±0.98 | 15.15 |
| 500k | 0.579±0.060 | 0.60±0.66 | 15.37 |

## Comparación cruzada con experimentos previos

| Presupuesto | Config | Cobertura | Colisiones/ep |
|------------:|--------|----------:|--------------:|
| 100k (seed 42, reproducibilidad) | sin VN | 0.698 ± 0.018 | 0.53 ± 0.72 |
| 200k (variante A, A/B test) | sin VN | 0.680 ± 0.021 | 0.20 ± 0.48 |
| **500k (este diagnóstico)** | sin VN | **0.579 ± 0.060** | **0.60 ± 0.66** |
| 2.5M (corrida 5M abortada) | CON VN | 0.626 ± 0.028 | 0.98 ± 1.05 |

## Criterio de decisión

### Resultado: **PROBLEMA_NO_DIAGNOSTICADO**

cob@500k=0.579 < 0.6. VecNormalize NO era el único culpable. Investigar más antes de cualquier corrida larga.

⚠ Colisiones > 0.3 en: 100k=0.55, 300k=0.85, 400k=0.80, 500k=0.60

## Figura

![Curva diagnóstico](curva_diagnostico.png)

## Archivos generados

- `checkpoints/ppo_diag_{100000,200000,300000,400000,500000}_steps.zip`
- `tensorboard/` — logs de entrenamiento
- `curva_diagnostico.png` — figura de 2 paneles
- `metricas_checkpoints.json` — datos crudos por episodio
- `diagnostico.log` — log completo
