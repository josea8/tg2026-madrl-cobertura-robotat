# RESULTADO PRIMERO — Modelo MADRL final (200k, Trial 13)

*Generado: 2026-04-25 09:54:55*  —  *Tiempo de evaluación: 9.9 min*

## Identificación del modelo

- **Origen:** Variante A del A/B test de λ_cbf (`modelos/tesis_v1/test_lambda_cbf/variante_A/modelo_final.zip`)
- **Hiperparámetros:** Trial 13 del estudio Optuna `tesis_v1` (`mejores_hiperparametros.json`)
- **Pesos de recompensa:** λ_grad=0.562, λ_ent=1.140, λ_ibrm=0.484, **λ_cbf=2.966**
- **Configuración de entrenamiento:** seed=42, 200,000 steps, n_agentes=5, n_envs=4, max_steps_ep=500, domain_rand=True, **sin VecNormalize**
- **Arquitectura policy:** MlpPolicy default de SB3 (default share net), encoder vecino externo (Mean Embedding) integrado en el observation space

## Tabla de métricas (100 episodios deterministas, sin domain_rand)

| Política | Cobertura (μ±σ) | Mediana | Pares col/ep (μ±σ) | Mediana | % eps con col | Distancia [m] | t cob=0.5 | t cob=0.6 |
|----------|----------------:|--------:|-------------------:|--------:|---------------|--------------:|----------:|----------:|
| **MADRL 200k (PRIMERO)** | 0.681±0.020 | 0.682 | 0.21±0.50 | 0.0 | 18.0% | 15.24±0.07 | 164±17 | 256±33 |
| Heurística NN (carrot) | 0.254±0.046 | 0.256 | 4.18±1.97 | 4.0 | 100.0% | 6.32±0.87 | 500±0 | 500±0 |
| Aleatoria | 0.140±0.011 | 0.142 | 0.47±0.67 | 0.0 | 40.0% | 7.76±0.08 | 500±0 | 500±0 |

## Detalle de cada política

### MADRL 200k — RESULTADO PRIMERO

- **Cobertura AoI final:** μ=0.681, σ=0.020, mediana=0.682, rango=[0.616, 0.724]
- **Pares en colisión / ep:** μ=0.21, σ=0.50, mediana=0.0, rango=[0, 3]
- **% episodios con ≥1 colisión:** 18.0%
- **Distancia recorrida [m]:** μ=15.24, σ=0.07
- **Step al cruzar cob=0.5:** μ=164, σ=17
- **Step al cruzar cob=0.6:** μ=256, σ=33

### Baseline 1 — Heurística NN (go-to-nearest-target)

- **Cobertura AoI final:** μ=0.254, σ=0.046, mediana=0.256, rango=[0.146, 0.355]
- **Pares en colisión / ep:** μ=4.18, σ=1.97, mediana=4.0, rango=[2, 10]
- **% episodios con ≥1 colisión:** 100.0%
- **Distancia recorrida [m]:** μ=6.32, σ=0.87
- **Step al cruzar cob=0.5:** μ=500, σ=0
- **Step al cruzar cob=0.6:** μ=500, σ=0

### Baseline 2 — Política aleatoria

- **Cobertura AoI final:** μ=0.140, σ=0.011, mediana=0.142, rango=[0.108, 0.164]
- **Pares en colisión / ep:** μ=0.47, σ=0.67, mediana=0.0, rango=[0, 4]
- **% episodios con ≥1 colisión:** 40.0%
- **Distancia recorrida [m]:** μ=7.76, σ=0.08
- **Step al cruzar cob=0.5:** μ=500, σ=0
- **Step al cruzar cob=0.6:** μ=500, σ=0

## Por qué 200k y no más

El experimento de diagnóstico en [`diagnostico_sin_vecnormalize/`](../diagnostico_sin_vecnormalize/reporte_diagnostico.md) demuestra que entrenar más allá de 200k DEGRADA el desempeño con estos hiperparámetros, con o sin VecNormalize. La trayectoria observada de la cobertura sin VecNormalize a 100k–500k:

| Step | Cobertura (μ±σ) | Pares colisión/ep |
|-----:|----------------:|------------------:|
| 100k | 0.707±0.017 | 0.55 |
| **200k** ← pico | **0.682±0.018** | **0.15** |
| 300k | 0.674±0.019 | 0.85 |
| 400k | 0.669±0.018 | 0.80 |
| 500k | 0.579±0.060 | 0.60 |

La degradación monotónica desde 200k es consistente con un caso de **sobreajuste por horizonte**: los hiperparámetros del Trial 13 fueron seleccionados por Optuna usando un presupuesto de 100k steps por trial. Optuna optimizó para ese horizonte, lo que produjo hiperparámetros con buen desempeño temprano pero inestables a largo plazo. La corrida 5M con VecNormalize (abortada por alarma a 2.5M, cob=0.626, col=0.98) confirma la patología desde otro ángulo.

**Implicación metodológica documentada:** futuros estudios Optuna sobre este pipeline deben usar presupuestos de trial de al menos 500k–1M steps, idealmente con MedianPruner calibrado para detectar divergencia post-pico.

## Figuras

- [Comparación con baselines](figuras/fig_resultados_PRIMERO.png)
- [Evolución del proyecto](figuras/fig_evolucion_experimentos.png)
- [Snapshot de un episodio](figuras/fig_trayectoria_episodio.png)

## Artefactos en este directorio

- `modelo_PRIMERO.zip` — checkpoint PPO listo para inferencia
- `hiperparametros.json` — Trial 13 exacto
- `config_entrenamiento.json` — configuración de la corrida 200k
- `metricas_100eps.json` — datos crudos de los 300 episodios (3 políticas × 100 eps)
- `figuras/` — las 3 figuras del reporte
