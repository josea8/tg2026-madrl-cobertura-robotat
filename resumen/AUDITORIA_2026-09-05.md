# AUDITORÍA INTEGRAL — Tesis TG 2026 (MADRL para cobertura de área con enjambre 3pi+)

**Fecha:** 2026-09-05
**Auditor:** revisión técnica independiente, modo solo-lectura.
**Alcance:** repositorio `C:\Users\velas\OneDrive\Documents\tesis` (`fase_preeliminar/`, `fase_preliminar2/`, `primerafase_webots/`).
**Método:** lectura de `CLAUDE.md`, `BITACORA_TECNICA.md`, `README_ROBOTAT.md`, `INFORME_CALIBRACION_20260829.md`, todos los `reporte_*.md`/`comparacion*.md`, logs de entrenamiento, `.json` de métricas, hashes de artefactos y código de las tres interfaces. No se ejecutó ningún entrenamiento ni se modificó ningún archivo.

---

## 1. VEREDICTO EN UNA PÁGINA

**Estado general.** El proyecto está considerablemente más avanzado y mejor documentado de lo que suele estar una tesis de grado a esta altura. La BITÁCORA es ejemplar: los experimentos A–I están diseñados con pareo por semilla, intervalos de confianza, cross-checks de control a 6–8 decimales, y — lo más valioso — varias conclusiones previas quedan explícitamente falsificadas o acotadas por el propio autor (Exp F "CONFUNDIDO", Exp H mínimo "NO concluyente", Exp G "contaminado por el solver", INFORME "dos conclusiones que no replicaron"). Ese nivel de autocrítica es el activo más fuerte del trabajo y hay que preservarlo en la redacción.

Dicho esto, hay **un problema estructural y tres riesgos técnicos** que condicionan lo que el documento puede afirmar.

**Problema estructural (CRÍTICO):** el documento de tesis, la carpeta `/thesis-knowledge/`, los archivos `.tex` y `m-bibliografia.bib` **no existen en el repositorio ni en el sistema de archivos**. Todo el Eje D (documento, bibliografía, estilo, cita de IA, referencias cruzadas, secciones placeholder) es literalmente inauditable con lo entregado, y el principio *single source of truth* no se puede verificar porque, si el documento vive en Overleaf, los números redactados están fuera del alcance de cualquier control del repo. Esto es lo primero a resolver: sin el `.tex` versionado junto al código, la trazabilidad número→fuente es un acto de fe.

**Los tres riesgos técnicos que más importan:**

1. **El número "consolidado" de cobertura (0.6813) descansa sobre una sola semilla de entrenamiento y un checkpoint de early-stop.** La configuración que lo produce (Trial 13) **reprobó el gate de reproducibilidad del propio proyecto** (veredicto ROJO: 3 semillas dieron recompensa −10/−32/−59, CV 0.589; cobertura 0.45–0.55 ó 0.53–0.70 según qué evaluación se mire). Ningún criterio de éxito definido en el proyecto ("DEFENDIBLE" 0.70–0.80, "LISTO SIM2REAL" >0.80 con col<0.1) se alcanzó jamás. La corrida de 5M **abortó por alarma a 2.5M** con cobertura 0.626 y `NECESITA_RECALIBRACION`, pero `reporte_final.md` la rotula como "5,000,000 pasos". La comparación cualitativa "MADRL supera a las heurísticas ~2.2–2.6×" sí sobrevive incluso con la semilla peor; lo que no sobrevive sin salvedades es llamar a 0.68 un resultado *estable* o *consolidado*.

2. **La garantía de seguridad del CBF no se transfiere al hardware, y la brecha de actuación no tiene mitigación implementada.** En simulación el margen de pared de 0.18 m no se viola nunca; en el tapete se violó en las **3 corridas y los 5 escalones** de velocidad (mínimo 0.128 m). El retardo de actuación real es **450–603 ms** (etapa 4 de calibración = FALLO) contra **0 ms en Webots** (los motores del `.wbt` no declaran `acceleration`). Los Exp F/H sólo midieron tolerancia a latencia de **pose** (≤300 ms), que es otro eje; ni el corte de pose vencida (150 ms) ni el escape protegen contra un comando que ya se ejecutó tarde. El régimen operativo reproducible en hardware es factor 0.40 (v ≤ 0.124 m/s), un tercio de la V_MAX con la que se entrenó y que está cableada en la normalización de observaciones.

3. **No hay una única fuente de verdad para el entorno ni para el código.** `swarm_env_skeleton.py` (que define reward, dinámica y observación) existe en **12 copias con 6 hashes distintos**: el env de entrenamiento ≠ el env de evaluación de los experimentos ≠ el env de ejecución en Webots. El repo **no es un repositorio git**, así que no hay `git log`, no hay trazabilidad commit→modelo, y no se puede reconstruir qué código exacto produjo cada `.zip`. Los cross-checks numéricos pasan a 1e-8, lo que sugiere que los caminos de código relevantes hoy son equivalentes, pero la práctica es frágil: cualquiera de esas copias puede derivar en silencio.

**Qué haría yo la próxima semana si fuera el autor (en orden):**

1. **Poner el `.tex` y la `.bib` bajo control de versiones dentro de este repo** (o un submódulo), e `git init` en la raíz con un commit inicial que congele el estado actual. Sin esto, ningún control de consistencia de datos es sostenible.
2. **Redactar la sección de resultados con la descomposición honesta que ya está en la BITÁCORA**, no con un número monolítico: política sola 0.44 (bloqueante) / 0.68 (reflexión, semilla 42), sistema de 3 capas 0.578, con la salvedad explícita de semilla única y early-stop. Declarar 0.68 como "mejor checkpoint de la mejor semilla" y reportar el rango entre semillas (0.53–0.70).
3. **Consolidar `swarm_env_skeleton.py` a una sola copia importable** y borrar las 11 restantes (o dejar un `sys.path` que apunte a una). Documentar en el código los 3 parches de SuperSuit/SB3 y su estado actual.
4. **Escribir el presupuesto de margen del CBF** como lo pide la propia BITÁCORA (holgura geométrica + σ_pose + V·latencia_pose + V·latencia_actuación + maniobra de escape) y ver si 0.18 m alcanza para 5 robots. Con los números de hoy, no alcanza reproduciblemente.
5. **Decidir el régimen post-rampa** (§C4b del README, marcado "decisión abierta previa a la primera sesión completa"): o se baja V_MAX y se reentrena, o se acepta operar a factor 0.40 y se dice en el documento.

---

## 2. HALLAZGOS

| ID | Sev. | Eje | Resumen | Evidencia | Acción sugerida (1 frase) |
|---|---|---|---|---|---|
| H-01 | CRÍTICO | D / A | No existe el documento de tesis, `/thesis-knowledge/`, ningún `.tex` ni `m-bibliografia.bib` en el repo ni en `~/OneDrive/Documents` (búsqueda a profundidad 3). | `find . -iname "*.tex" -o -iname "*.bib"` → vacío; sólo `guía_tesis.pdf` (la guía, no la tesis). | Versionar el `.tex`/`.bib` dentro del repo antes de cualquier otra cosa. |
| H-02 | CRÍTICO | E | La garantía del CBF (margen de pared 0.18 m) no transfiere: violada en 3/3 corridas y 5/5 escalones en hardware; nunca en sim. | `INFORME_CALIBRACION_20260829.md:19-30`, tabla `:96-104`, `:268` | Redimensionar el margen con un presupuesto explícito de error real y re-verificar en sim. |
| H-03 | CRÍTICO | E / B | Brecha de actuación sim-real no mitigada: 450–603 ms medidos vs 0 ms en Webots (motores sin `acceleration`); etapa 4 de calibración FALLA. | `INFORME_CALIBRACION_20260829.md:44`, `:199-214`, `:262-263`; `BITACORA_TECNICA.md:1341-1366` | Modelar el retardo del actuador en el env y reentrenar, o bajar V_MAX y aceptar el régimen 0.40. |
| H-04 | ALTO | A / C | El resultado "consolidado" (cobertura 0.6813) es de **una** semilla de entrenamiento (42) y un checkpoint de early-stop; la config degrada monótonamente después de 200k. | `RESULTADO_PRIMERO/reporte_consolidado.md:10,17,52-62`; `diagnostico_sin_vecnormalize/reporte_diagnostico.md:22-26` | Reportar el número con la salvedad de semilla única + rango entre semillas (0.53–0.70). |
| H-05 | ALTO | A / C | La config del Trial 13 **reprobó** el gate de reproducibilidad de 3 semillas (veredicto ROJO) y el de cobertura (CONSISTENTE_PERO_BAJA, media 0.636). El proyecto avanzó igual. | `verificacion_seeds/reporte_reproducibilidad.md:19-44`; `comparacion_seeds_multimetrica.md:20,36-52` | Decir en el documento que la política final es un outlier por semilla, no el comportamiento esperado de la config. |
| H-06 | ALTO | A / C | `reporte_final.md` afirma "Steps totales: 5,000,000" y "modelo al final de los 5M steps"; el log muestra ALARMA y pausa a 2.5M, y sólo hay checkpoints hasta 2.5M. | `entrenamiento_final_5M/reporte_final.md:17-18,57`; `entrenamiento_5M.log:9-11`; `curva_5M.csv` (última fila 2 500 000); `checkpoints/` (máx `ppo_5M_2500000_steps.zip`) | Corregir el rótulo a "corrida 5M abortada a 2.5M" en todo artefacto y en el documento. |
| H-07 | ALTO | B | `swarm_env_skeleton.py`: 12 copias, 6 hashes distintos. Entrenamiento (`fase_preliminar2`, `9bb4965…`) ≠ evaluación de experimentos (`4517ccd…`, expC/D/I) ≠ ejecución Webots (`dfaaa60…`). | `md5sum` sobre las 12 rutas (ver §Datos duros, fila "env hash") | Dejar una sola copia importable; borrar el resto. |
| H-08 | ALTO | B | El repo **no es git**. Sin `git log`, sin trazabilidad commit→modelo, sin poder reconstruir qué código produjo cada `.zip`. | `git rev-parse` → "not a git repository"; `CLAUDE.md` cita `git log` como paso de contexto que no se puede ejecutar. | `git init` en la raíz y congelar el estado; etiquetar el commit de cada modelo guardado. |
| H-09 | ALTO | E / A | Censo de marcadores inconsistente entre 3 documentos. Config: `MAPEO_NO_VERIFICADO=False`, "robot N ↔ marcador N, 1–16, hecho de plataforma". README (25-ago): marcadores 2,3,6,9 en *placeholder* (no trackeados). INFORME (3-sep): enjambre real = robots 1,2,3,6,9. Verificado físicamente sólo robots 1 y (una vez) 2. | `config_robotat.py:186-199` (`MAPEO_NO_VERIFICADO=False`), `:53-70` (`marcador_fijo_de_robot`); `README_ROBOTAT.md:284-297,586-589`; `INFORME_CALIBRACION_20260829.md:59-67`; `BITACORA_TECNICA.md:1946-1953` | Correr el censo pendiente de los 5 robots (§7 README) y fijar el mapeo con evidencia, no por convención. |
| H-10 | ALTO | D / B | `CLAUDE.md` (único handoff) está ~5 meses desactualizado: fechado 16-abr-2026, su "PRÓXIMA TAREA" ya está hecha, describe el estado previo a **todos** los resultados; dice SB3 2.7.1 y `num_cpus=1` obligatorio, pero `train.py:350` usa `min(n_envs, os.cpu_count())`. No hay handoff para la fase Webots (la activa). | `fase_preliminar2/CLAUDE.md:12,167-170,250,272-289`; `fase_preliminar2/train.py:335,350` | Reescribir `CLAUDE.md` al estado real o marcarlo como archivo histórico y crear un handoff de la fase Webots. |
| H-11 | MEDIO | A / C | Mismo modelo y semilla (`verificacion_seeds/seed_42/modelo_final.zip`) da cobertura **0.5546** ("20 stream-episodios", `reporte_reproducibilidad`) vs **0.698** ("30 episodios", `comparacion_seeds_multimetrica`). Gap sistemático ~0.10–0.14 en las 3 semillas. | `reporte_reproducibilidad.md:21-23` vs `comparacion_seeds_multimetrica.md:20` | Documentar qué diferencia a los dos protocolos de evaluación y usar uno solo para decisiones. |
| H-12 | MEDIO | C | El baseline "Heurística NN (carrot)" no tiene término de evitación inter-agente y hay más agentes (5) que hotspots (3): 100% de colisiones y el factor ~20× son artefacto de un baseline degenerado. La política aleatoria colisiona menos (40% eps). | `consolidar_resultado_primero.py:40-41`; `RESULTADO_PRIMERO/reporte_consolidado.md:17-19` | Reportar el factor de mejora contra Voronoi+PSO (2.6× cobertura, ~2× colisiones), no contra la NN. |
| H-13 | MEDIO | C | La conclusión "λ_cbf = 5.0 es veneno" descansa en un A/B de **una sola semilla** (42), 30 eps. Subir el peso de la penalización de colisión aumentó las colisiones (0.20→0.43): resultado contraintuitivo sin repetición. | `test_lambda_cbf/comparacion.md:18-28,49-51` | Repetir el A/B con ≥3 semillas antes de afirmarlo en el documento. |
| H-14 | MEDIO | A / D | Criterios de éxito contradictorios entre documentos: `reporte_final.md:46` marca 🔴 si `cob<0.70`; el modelo PRIMERO (0.681) es 🔴 por ese criterio pero `reporte_consolidado.md` lo presenta como el resultado final logrado. | `entrenamiento_final_5M/reporte_final.md:42-50` vs `RESULTADO_PRIMERO/reporte_consolidado.md:1,23-31` | Unificar un único criterio de éxito y aplicarlo a todos los modelos. |
| H-15 | MEDIO | B | `RADIO_RUEDA`/`MEDIO_EJE` duplicados en ≥4 archivos con 2 juegos de valores (Webots 0.035/0.07 vs Robotat 0.016/0.048). Correcto por dominio, pero sin fuente única y con cruce silencioso posible. | `controladores…/protocolo.py:236-237` y `:268-269`; `supervisor_fisica.py:198-201`; `config_robotat.py:492-493` | Centralizar cada juego en un módulo de constantes por dominio con nombre inequívoco. |
| H-16 | MEDIO | B | Import de acoplamiento en la capa del coordinador: `coordinador_enjambre.py:86` importa `protocolo` (formato de mensajes Emitter/Receiver de Webots) a nivel de módulo; comparaciones `nombre_entorno == "webots"` para nombrar CSV. | `coordinador_enjambre.py:79-93,531-532` | Mover `protocolo` a import perezoso como ya está `controller`/`adaptadores_webots`. |
| H-17 | BAJO | B | `tesis_v2_sanidad/lib/lib/` — directorio anidado por accidente de copia, con otra copia del env. | `find . -path "*tesis_v2_sanidad/lib/lib/*"` | Borrar el directorio anidado. |
| H-18 | BAJO | A / D | Conteo de pruebas sin sincronizar entre documentos: 165 (`BITACORA`, `README`) vs 182 (`INFORME`, 3-sep). No es contradicción (crecen), pero ningún documento cita el número vigente. | `BITACORA_TECNICA.md:1944`; `README_ROBOTAT.md:779`; `INFORME_CALIBRACION_20260829.md:13,297-298` | Poner el conteo de pruebas en un solo lugar y referenciarlo. |
| H-19 | BAJO | C | Tabla 5 del resumen (tiempo de decisión 0.734 ms, 10.96×) vs BITÁCORA (0.757 / 8.039 ms, 10.62×). Ya reconciliado en la BITÁCORA (promedia sólo `reflexion` vs ambas condiciones), pero el documento debe usar una sola cifra. | `BITACORA_TECNICA.md:166-182` | Elegir la media global y borrar la otra del documento. |

---

## 3. TABLA DE DATOS DUROS (Eje A)

Estado: `CONSISTENTE` = mismo valor en todas las fuentes; `DIVERGENTE` = fuentes discrepan; `HUÉRFANO` = aparece en un reporte sin respaldo en logs/artefactos; `SIN DOCUMENTO` = no se puede clasificar porque el `.tex` no existe.

| Dato | Valor(es) | Fuentes (archivo:línea) | Estado |
|---|---|---|---|
| Cobertura AoI, modelo 200k (PRIMERO), reflexión, 100 eps | **0.68129 ± 0.02000** (mediana 0.682, rango 0.616–0.724) | `RESULTADO_PRIMERO/metricas_100eps.json` (media 0.6812908187508583); `reporte_consolidado.md:17,25`; `BITACORA_TECNICA.md:17-18`; cross-check `expI/…/resumen` vía `BITACORA:871` (\|Δ\|=1.1e-8); Webots réplicas `BITACORA:42,110` | CONSISTENTE |
| Cobertura, modelo 200k, **borde bloqueante**, 100 eps | 0.4516 ± 0.0422 | `BITACORA_TECNICA.md:57-59` (Exp C), `:872` (Exp I), `:1013` | CONSISTENTE |
| Cobertura, política sola, bloqueante, factorial Python (18 semillas) | 0.4426 | `BITACORA_TECNICA.md:552,564,617` | CONSISTENTE |
| Cobertura, **sistema 3 capas** (política+CBF+escape), bloqueante, 18 semillas | 0.5780 (Python) / 0.5739 (Webots) | `BITACORA_TECNICA.md:555,618,622,660`; `INFORME` `REF_SIM` no lo contradice | CONSISTENTE |
| Cobertura, corrida 5M | 0.626 ± 0.028 (eval de `best_model.zip`, ≤2.5M) | `reporte_final.md:27`; `reporte_diagnostico.md:35`; `entrenamiento_5M.log:26` | CONSISTENTE en valor / **DIVERGENTE en etiqueta** (¿5M o 2.5M?) — ver H-06 |
| Cobertura entre 3 semillas de entrenamiento (Trial 13, 100k) | rew: −10.35 / −31.94 / −58.88; cob: **0.5546 / 0.5269 / 0.4509** (repro) **ó** 0.698 / 0.679 / 0.532 (multimétrica) | `reporte_reproducibilidad.md:21-23` vs `comparacion_seeds_multimetrica.md:20` | DIVERGENTE (dos protocolos de eval, gap sistemático ~0.12) — ver H-11 |
| Colisiones/episodio (pares <0.15 m), modelo 200k, reflexión | 0.21 ± 0.50 (mediana 0, 18% eps con ≥1) | `metricas_100eps.json` (n_colisiones media 0.21); `reporte_consolidado.md:17,26`; `BITACORA:876` | CONSISTENTE |
| Colisiones/episodio, sistema 3 capas, Webots (`col015`) | 0.000 (0/90) | `BITACORA_TECNICA.md:533,655`; `resultados_consolidados/tabla_final_webots.txt` | CONSISTENTE |
| Colisiones, corrida 5M | 0.98 ± 1.05 | `reporte_final.md:28`; `reporte_diagnostico.md:35` | CONSISTENTE |
| Factor de mejora en **cobertura** vs mejor heurística | **2.58×** (reflexión, vs Voronoi+PSO 0.2644) / **2.22×** (bloqueante, sistema) / 2.6× (redondeo Exp E) / ~2.68× vs NN 0.254 | `BITACORA_TECNICA.md:114,124,649,662`; `reporte_consolidado.md:17` | CONSISTENTE (con nota: el "×" cambia según baseline y condición; ver H-12) |
| Factor de mejora en **colisiones** vs heurística | ~20× vs NN (4.18 vs 0.21) / ~2× vs Voronoi+PSO (0.41 vs 0.21) | `reporte_consolidado.md:17-18`; `BITACORA_TECNICA.md:120,153` | CONSISTENTE en números / el "20×" es contra baseline degenerado — H-12 |
| Pasos de entrenamiento — Optuna `tesis_v1` | 20 trials × 100k pasos/trial | `CLAUDE.md:274-280`; `reporte_reproducibilidad.md:7,13` | CONSISTENTE |
| Pasos — modelo PRIMERO / `variante_A` | 200 000 | `reporte_consolidado.md:10`; `test_lambda_cbf/comparacion.md:18` | CONSISTENTE |
| Pasos — corrida "5M" | rotulada 5 000 000; **real ≈ 2 500 000** (abortada) | `reporte_final.md:17` vs `entrenamiento_5M.log:9-10`, `curva_5M.csv` | DIVERGENTE — H-06 |
| Pasos — diagnóstico sin VecNormalize | 500 000 | `reporte_diagnostico.md:11` | CONSISTENTE |
| Pasos — `modelo_sanidad` (v2), v3, v4 | 200 000 cada uno, Trial 13 sin cambios | `BITACORA_TECNICA.md:1001-1002,1037,1073,1084` | CONSISTENTE |
| Pesos de recompensa (Trial 13) | λ_grad=0.5622, λ_ent=1.1403, λ_ibrm=0.4838, **λ_cbf=2.9655** | `mejores_hiperparametros.json`; `metadata_trials/trial_013.json`; `reporte_consolidado.md:9` (2.966); `reporte_final.md:9` (2.9655); `test_lambda_cbf/comparacion.md:16` | CONSISTENTE (2.966 / 2.9655 / 2.97 = redondeos) |
| Radio de rueda — Webots | 0.035 m | `controllers/coordinador_enjambre/protocolo.py:268`; `controlador_agente/protocolo.py:236`; `supervisor_fisica.py:198` | CONSISTENTE (entre copias Webots) |
| Radio de rueda — Robotat (real) | 0.016 m (32 mm diámetro / 2) | `config_robotat.py:492`; `README_ROBOTAT.md:407,419-421` | CONSISTENTE |
| Semieje — Webots / lab11 / real | 0.0700 / 0.0412 / 0.0480 m | `protocolo.py:269` y `:251-255`; `README_ROBOTAT.md:412-417`; `BITACORA_TECNICA.md:1329-1333` | CONSISTENTE (tres dominios, documentado; riesgo de cruce = H-15) |
| Latencia de actuación (media) | ~450 ms @ 0.15 m/s; 848 ms @ 0.05 m/s; **603 ms** (veredicto etapa 4) | `INFORME_CALIBRACION_20260829.md:44,199-203,262` | CONSISTENTE (rango declarado; residuo inercia/canal no separado) |
| Latencia de actuación — Webots | 0 ms (motores `maxVelocity 84`, sin `acceleration`/`maxTorque`) | `INFORME_CALIBRACION_20260829.md:205-208,263` | CONSISTENTE |
| Latencia de percepción (pose) | 2.6 ms p50 / 4.19 ms p95 (200 consultas) | `INFORME_CALIBRACION_20260829.md:260` | CONSISTENTE |
| Latencia de pose tolerada (Exp F/H) | hasta 300 ms (3 decisiones); corte operativo 150 ms | `BITACORA_TECNICA.md:337-339,715-717,1368-1372` | CONSISTENTE |
| Período de decisión nominal | 100 ms (`DT_ENV = 0.1`, 10 Hz) | `README_ROBOTAT.md:205`; `BITACORA_TECNICA.md:1184,1854` | CONSISTENTE |
| Frecuencia de consulta de poses | **10 Hz** (`HZ_CONSULTA_POSES=10.0`, una por decisión); antes 100 Hz (por tick) | `README_ROBOTAT.md:186-238`; `BITACORA_TECNICA.md:1840-1875` | CONSISTENTE |
| Frecuencia del servidor de captura | ~82 Hz (tasa real de cambio) | `INFORME_CALIBRACION_20260829.md:261,185` | CONSISTENTE (dato de una sola sesión) |
| Puerto poses Robotat | `192.168.50.200:1883`, JSON/TCP, respuesta agente-major, quaternión escalar-primero | `README_ROBOTAT.md:42-52`; `BITACORA_TECNICA.md:1521-1522` | CONSISTENTE |
| Puerto ruedas Robotat | `192.168.50.10<id>:9090`, CBOR 11 B, float32 **big-endian**, RPM, sat. ±400, **izquierda primero** | `README_ROBOTAT.md:54-64`; `BITACORA_TECNICA.md:1282-1299`; `protocolo_robotat.py:16-20,104-127` | CONSISTENTE |
| IP por robot (censo) | .101 / .102 / .103 / .106 / .109 (robots 1,2,3,6,9) | `INFORME_CALIBRACION_20260829.md:59-67` | CONSISTENTE con README (`.10<id>`); mapeo de marcadores = H-09 |
| N.º de agentes por experimento A–I | A:1 · B:5 · C:5 · D:5 · E:5 · F:5 · G:5 · H:5 · I:{2,3,5,7,10} | `BITACORA_TECNICA.md:22,40-41,50,68,94-111,219-226,357,685-701,829-854` | CONSISTENTE |
| Semillas de protocolo | Python: `420000+i` (=42·10000+i); Webots: `420000–420017` (18) | `BITACORA_TECNICA.md:17-18,854`; `tabla_final_webots.txt:2` | CONSISTENTE |
| Criterio de despliegue físico (colisiones/episodio) | `reporte_final.md`: col < 0.1 ("LISTO") / col > 0.3 ("RECALIBRAR"). **No se encontró "<0.05" en el repo.** | `entrenamiento_final_5M/reporte_final.md:42-50` | HUÉRFANO (el umbral <0.05 que menciona la SPEC no está en ningún archivo del repo) |
| CBF: `D_SEGURA_PUNTO` (margen pared) / `D_SEGURA_ROBOTS` | 0.18 m / 0.25 m | `coordinador_enjambre.py:139,148`; `supervisor_fisica.py:147`; `BITACORA_TECNICA.md:1149-1159` | CONSISTENTE |
| `D_SAFE` del env (contacto de chasis) | 0.15 m | `swarm_env_skeleton.py:63`; `BITACORA_TECNICA.md:1239-1241` | CONSISTENTE |
| `V_MAX` / `OMEGA_MAX` | 0.31 m/s / 6.2832 rad/s | `concentration_dynamics.py:89-90` (todas las copias); `CLAUDE.md:34-35` | CONSISTENTE (excepto `adaptador_piramidal.py:34` usa 6.28 — documentado, H-19) |
| Intervención del CBF, 5 robots, hardware vs sim local | 37.6–42.7 % (hw) vs 59.4 % (sim, mismas condiciones iniciales) | `INFORME_CALIBRACION_20260829.md:83-89,120-141,266-267` | CONSISTENTE (y corrige la constante `REF_SIM["cbf"]="~0.37"`, que era HUÉRFANO — ver nota) |
| Constante `REF_SIM["cbf"] ≈ 0.37` en el código de sesión | 0.37 escrito a mano, procedencia no documentada; la comparación controlada da 0.594 | `INFORME_CALIBRACION_20260829.md:134-141` | **HUÉRFANO reconocido** (el propio INFORME lo marca como número sin fuente) |
| Reflexiones elásticas por episodio (Exp B) | 45.74 ± 5.54 (9.15/agente); 100% eps con ≥1 | `BITACORA_TECNICA.md:40-41`; cross-check Exp I `:874` | CONSISTENTE |
| Degradación borde bloqueante vs reflexión (n=5) | Δ pareada −0.2297, IC95 [−0.2385, −0.2208], 100/100 eps | `BITACORA_TECNICA.md:57-63` (C), `:81` (D), `:124` (E), `:943` (I) | CONSISTENTE (replicado en 4 experimentos) |
| `swarm_env_skeleton.py` — hash del archivo | 6 hashes: entren. `9bb4965…`; Webots exec `dfaaa60…`; exp C/D/I `4517ccd…`; supervisor_cobertura `b5d1a36…`; expB `7391ac2…`; v3 `4297e5d…`; v4 `a9cb184…` | `md5sum` sobre 12 rutas | DIVERGENTE — H-07 |
| `concentration_dynamics.py` — hash | `57d590328a16f559715d3c96abccce7c` en las 12 copias | `md5sum` | CONSISTENTE |
| `modelo_PRIMERO.zip` — hash | `7044039d…` idéntico en 8 copias | `md5sum` | CONSISTENTE |
| N.º de páginas / capítulos / referencias del documento | — | — | SIN DOCUMENTO |
| Trazabilidad de toda afirmación cuantitativa del `.tex` | — | — | SIN DOCUMENTO |
| Bibliografía (`.bib`): duplicados, huérfanos, DOIs, placeholders | — | — | SIN DOCUMENTO |
| Cita de asistencia de IA (guía UVG) | — | — | SIN DOCUMENTO (existe `guía_tesis.pdf` en la raíz, no revisada contra un `.tex` inexistente) |

**Sobre los HUÉRFANOS:** el único número inventado/heredado que se pudo identificar dentro del repo es la constante `REF_SIM["cbf"] ≈ 0.37` en el código de la sesión de laboratorio, y el propio `INFORME_CALIBRACION` ya lo detectó y desmintió (valor real 0.594). El umbral "<0.05 colisiones/episodio" que la SPEC da por existente **no aparece en ningún archivo**; el criterio operativo real del repo es col<0.1 (`reporte_final.md`). Cualquier otro huérfano estaría en el `.tex`, que no se puede revisar.

---

## 4. FICHAS DE EXPERIMENTOS (Eje C)

Todos los experimentos A–I viven en `primerafase_webots/` y están descritos en `BITACORA_TECNICA.md`. Los "artefactos" son rutas relativas a `primerafase_webots/`.

### Exp A — Atascos con física real (Webots, 1 robot)
| Campo | Contenido |
|---|---|
| Pregunta | ¿Qué le pasa a la política entrenada con reflexión elástica cuando la pared bloquea en vez de reflejar? |
| Configuración | 1 robot, 18 episodios, `modelo_PRIMERO`, sin CBF. |
| Artefactos | `controllers/supervisor_fisica/resultados/experimento_A_atascos_original.csv` |
| Conclusión afirmada | 18/18 atascos (100%); la política nunca comanda v<0 (0/18); no tiene recuperación aprendida. |
| ¿Se sostiene? | **Sí.** Base del resto del trabajo. n=18 es suficiente para un efecto del 100%. |

### Exp B — Dependencia de la reflexión elástica (Python, 100 eps)
| Campo | Contenido |
|---|---|
| Pregunta | ¿Cuánto depende la política del rebote idealizado? |
| Configuración | 5 agentes, 100 semillas, `modelo_PRIMERO`, reflexión. |
| Artefactos | `experimentos/expB_reflexiones/resultados/` (env hash `7391ac2…`, distinto del de entrenamiento y del de C/D/I) |
| Conclusión afirmada | 45.74 ± 5.54 reflexiones/ep; 100% eps con ≥1; cobertura replicada 0.6813. |
| ¿Se sostiene? | **Sí**, con salvedad menor: corre sobre una copia del env con hash propio; el cross-check de cobertura a 0.6813 mitiga la duda. |

### Exp C — Degradación bajo bordes bloqueantes (Python, pareado, 100 eps)
| Campo | Contenido |
|---|---|
| Pregunta | ¿Cuánta cobertura se pierde al pasar de reflexión a borde bloqueante? |
| Configuración | 5 agentes, 100 semillas, pareado por semilla, 2 condiciones. |
| Artefactos | `experimentos/expC_bordes/resultados/` (env `4517ccd…`) |
| Conclusión afirmada | Cobertura 0.6813 → 0.4516; Δ pareada −0.2297, IC95 [−0.2385,−0.2208], 100/100 peor. |
| ¿Se sostiene? | **Sí.** Diseño pareado correcto, IC excluye cero, efecto universal. Replicado en D/E/I. |

### Exp D — ¿Es específico de la política aprendida? (Python, 3×2×100)
| Campo | Contenido |
|---|---|
| Pregunta | ¿La degradación de borde es de MADRL o de cualquier controlador? |
| Configuración | 3 estrategias (MADRL, heurística NN, aleatoria) × 2 bordes × 100 semillas, pareado; DiD. |
| Artefactos | `experimentos/expD_lineas_base/resultados/` |
| Conclusión afirmada | Degradación específica de MADRL: Δ −0.2297 vs +0.0003 (NN) vs −0.0001 (aleatoria); DiD −0.2300, IC95 [−0.2389,−0.2211]. |
| ¿Se sostiene? | **Sí.** Control reproduce el protocolo a 6 decimales. El DiD es el estadístico correcto. |

### Exp E — Voronoi + PSO como cuarta línea base (Python, 4×2×100)
| Campo | Contenido |
|---|---|
| Pregunta | ¿Cómo rinde MADRL contra una heurística de cobertura con información global? |
| Configuración | 4 estrategias × 2 bordes × 100 semillas = 800 eps, pareado. `PyramidalHeuristicController` de `fase_preliminar2/baseline_heuristico/`, copia verificada por sha256. |
| Artefactos | `experimentos/expD_lineas_base/adaptador_piramidal.py`, `correr_experimento_E.py`, `resultados/experimento_E_completo.csv` (800 filas), `resumen_experimento_E.txt` |
| Conclusión afirmada | MADRL 0.6813 vs piramidal 0.2644 (2.6×); piramidal domina en seguridad de pared por diseño (evitación, no margen); tres regímenes de comportamiento de borde. |
| ¿Se sostiene? | **Sí, con salvedades ya declaradas por el autor** (asimetrías de información, sintonización y espacio de acción; ley de bajo nivel distinta entre las dos heurísticas). La comparación honesta es 2.6×, no el 20× de colisiones vs NN. |

### Exp F — Robustez a ruido y latencia de pose (Webots, 4×3×18)
| Campo | Contenido |
|---|---|
| Pregunta | ¿Cuánto ruido/latencia de pose tolera el sistema antes de entrar al laboratorio? |
| Configuración | `modelo_sanidad` + CBF, 5 agentes, 4 niveles σ × 3 latencias × 18 semillas = 216 eps, una sesión. |
| Artefactos | `controllers/coordinador_enjambre/resultados/expF_barrido_5agentes.csv` (216 filas), `expF_resumen_5agentes.txt` |
| Conclusión afirmada | **El propio autor lo marca CONFUNDIDO:** el ruido "mejora" el desempeño porque perturba un equilibrio patológico del CBF (deadlock de liveness), no porque el sistema sea robusto. El margen se consume (9/90 → 81/90 violaciones). |
| ¿Se sostiene? | **La conclusión negativa sí** ("esto no mide robustez"). Es un ejemplo de autocrítica bien hecha. No usar la tabla de cobertura como evidencia de tolerancia al ruido. |

### Exp G — ¿Se resuelve el bloqueo sintonizando el filtro? (Webots, 3×3×18)
| Campo | Contenido |
|---|---|
| Pregunta | ¿Existe una configuración del CBF (ℓa, w_ω) sin bloqueo? |
| Configuración | 3 ℓa × 3 w_ω × 18 semillas = 162 eps; α fijo; constantes acopladas (`d_s=0.13+ℓa`, `D_robots=0.15+2ℓa`). |
| Artefactos | `resultados/expG_barrido_filtro_5agentes.csv` (162 filas, 8 decimales), `expG_resumen_filtro_5agentes.txt` |
| Conclusión afirmada | Ninguna celda cumple; la base es la mejor. El eje ℓa empeora de forma monótona y estructural; el eje w_ω "sin efecto detectable" y **contaminado por el solver** (fallbacks del QP 2.22 → 40.28/ep con w_ω bajo → congela el robot). |
| ¿Se sostiene? | **Sí.** El eje ℓa está bien aislado (constantes acopladas para comparabilidad). El eje w_ω el autor lo declara no interpretable — correcto; requeriría un solver de conjunto activo exacto. |

### Exp H — Robustez sobre la configuración sana (Webots, 4×3×18)
| Campo | Contenido |
|---|---|
| Pregunta | Fase 2 del Exp G: ¿cuánta degradación tolera el sistema con política+CBF+**escape** (base sana, 0/90 atascos)? |
| Configuración | Mismo factorial que F, 216 eps (1080 agente-episodios). |
| Artefactos | `resultados/expH_barrido_5agentes.csv` (216 filas, `d_min` 8 decimales), `expH_resumen_5agentes.txt` |
| Conclusión afirmada | El sistema no se rompe en ningún punto: 0/1080 atascos, 0/1080 contacto de pared, 0 colisiones, `d_min` global mínima 0.0839 m (8.9 mm de holgura). Tres cosas rompen el mismo equilibrio (escape, ruido, latencia). El mínimo en σ=5 mm **NO concluyente** (IC apenas excluye cero, std 2.6× la base). |
| ¿Se sostiene? | **La afirmación central sí** (cero fallos en el rango). El autor ya marca lo que no está establecido. **Salvedad de auditoría:** todo esto es simulación Webots con actuación de 0 ms; no dice nada sobre la brecha de actuación real (H-03). |

### Exp I — Generalización a distinto número de agentes (Python, 5×2×100)
| Campo | Contenido |
|---|---|
| Pregunta | ¿El parameter sharing generaliza a n distinto sin reentrenar? |
| Configuración | n ∈ {2,3,5,7,10} × 2 bordes × 100 semillas = 1000 eps, pareado, `modelo_PRIMERO` sin tocar pesos. Invarianza al cardinal verificada por lectura. |
| Artefactos | `experimentos/expI_escalabilidad/` (copias verificadas byte a byte por sha256), `resultados/experimento_I_completo.csv` (1000 filas), `resumen_experimento_I.txt`, 3 figuras 300 dpi |
| Conclusión afirmada | Generaliza **en cobertura** (degradación suave y monótona, sin colapso en n∈[2,10]) pero **NO en seguridad**: colisiones ×13 de n=5 a n=10. Reformulación sugerida de la frase de la metodología. |
| ¿Se sostiene? | **Sí**, con una confusión que el autor declara: parte de la caída de cobertura por agente a n grande es saturación espacial (arena 3×3), no fallo de la política; haría falta barrer el tamaño de arena a densidad constante. La conclusión de seguridad (×13) es sólida. |

**Observación transversal sobre Eje C:** la descomposición factorial que importa (CBF × escape, `BITACORA:546-563`) tiene sus 4 celdas completas y pareadas por semilla. No hay celdas faltantes que se estén interpolando en la redacción **dentro de lo que audité**; no puedo verificar si el `.tex` interpola algo porque no existe.

---

## 5. COSAS QUE NO PUDE VERIFICAR (y qué haría falta)

1. **Todo el Eje D (documento, bibliografía, estilo, referencias cruzadas, secciones placeholder, cita de IA).** No hay `.tex` ni `.bib` en el repo ni en `~/OneDrive/Documents` (búsqueda a profundidad 3; existe `tesis.zip` sin abrir y `guía_tesis.pdf`). *Necesito:* el árbol LaTeX completo dentro del repo, o acceso al proyecto Overleaf.
2. **Conteo de páginas, capítulos y referencias.** Mismo motivo.
3. **Trazabilidad número→`.tex`.** El Eje A está hecho sobre reportes y logs; no puedo cruzarlo contra lo que el documento afirma. Varias cifras (0.68, 2.6×, 0.578) son consistentes *entre reportes*, pero si el `.tex` cita, por ejemplo, "0.68 de cobertura" sin la salvedad de semilla única y early-stop, eso sería una tergiversación que sólo se ve leyendo el documento.
4. **Origen del umbral "<0.05 colisiones/episodio".** La SPEC lo da por existente; no está en ningún archivo del repo. El criterio real es col<0.1 (`reporte_final.md:44`). Si el umbral 0.05 está en el `.tex` o en el protocolo aprobado, es un HUÉRFANO candidato. *Necesito:* el protocolo de tesis o el `.tex`.
5. **Objetivos específicos del protocolo vs lo que reporta el documento.** No hay copia del protocolo aprobado en el repo. *Necesito:* el documento de protocolo (o su sección de objetivos).
6. **Mapeo real marcador↔robot para los 5 robots.** El censo completo de los 5 Pololu (puertos de rueda + marcador) está marcado como **pendiente** en `README_ROBOTAT.md:564-589`. Verificado físicamente sólo robot 1 y, una vez, robot 2. La memoria del proyecto (fuera del repo) menciona una lista de marcadores `14,1,9,12,6` que **no coincide** con la del `INFORME_CALIBRACION` (`1,2,3,6,9`); no pude reconciliarlas porque una de las dos es posterior a los archivos entregados. *Necesito:* el CSV de la sesión de censo, cuando se corra.
7. **Contenido de los `.zip` de modelos** (arquitectura de red, `vecnormalize` stats). No los descomprimí; sólo verifiqué hashes e identidad entre copias. Los hiperparámetros se leyeron de los `.json` acompañantes, no del `.zip`.
8. **Si los 3 parches de SuperSuit/SB3 (`CLAUDE.md §7`) siguen siendo necesarios.** El código de `train.py` ya no fuerza `num_cpus=1` (usa `min(n_envs, cpu_count)`), lo que sugiere que el Bug B se resolvió con la subida a SB3 2.8, pero el `CLAUDE.md` no se actualizó y no hay una nota en el código que lo confirme. *Necesito:* correr la batería de tests de `fase_preliminar2` (no lo hice: la SPEC prohíbe ejecutar entrenamientos y no quise arriesgar efectos de red/archivos).
9. **Reproducción de curvas de aprendizaje desde artefactos versionados.** Los `tensorboard/` existen por experimento, pero sin git no se puede afirmar qué commit los generó. Las curvas `.csv` (`curva_5M.csv`, `curva_aprendizaje.csv` por semilla) sí permiten reconstruir la evolución de métricas agregadas.
10. **Cobertura de pruebas real.** Conté los archivos `test_*.py` y los números que reportan los documentos (133→182 pruebas, en crecimiento). No ejecuté las suites. No hay pruebas para el pipeline de entrenamiento de `fase_preliminar2` más allá de los "sanity checks" descritos en `CLAUDE.md §9`; las 182 pruebas son casi todas del puente al Robotat (`primerafase_webots/controllers/coordinador_enjambre/`).

---

*Fin de la auditoría. Un solo archivo nuevo creado: este.*
