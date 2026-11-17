### EXPLORATORIO: S2 y S3, corridos después de la parada y fuera de la regla (2026-10-19; lectura corregida el 2026-10-24)

**S2 y S3 se corrieron DESPUÉS de la parada de S1 y FUERA de la regla de parada, por decisión de José del 19-10.** El motivo: el agotado que detuvo S1 no lo induce el obstáculo (la semilla 420001 lo tiene en las cuatro condiciones, también en el control). **Es exploratorio y no cambia el veredicto del Exp Q:** S1 detiene por la regla del Exp O, y lo de arriba queda tal cual.

**Corrección del 24-10 (pedido de José).** Se corrigieron los titulares y la lectura, y se agregó la estadística de eventos raros: Clopper-Pearson y McNemar exacta sobre episodios. **Ningún dato cambia y no se corrió ningún episodio.** Respaldo de la versión anterior: `ENTRADA_BITACORA_expQ_EXPLORATORIO_respaldo_20261024_preEventosRaros.md`.

**Cómo, sin tocar nada de S1.** `correr_exploratorio_Q.py` sólo orquesta: importa y llama a `correr_experimento_Q.py` y no redefine ni parchea nada. Lo comprueba `comparar_ast_exploratorio_Q.py`.
- Exige la huella `e265b6cd…4a29` y los tres registros aprobados con ella.
- Comprueba el sha256 de los tres archivos de S1 al empezar y al terminar.
- **Antes de S2, recalculó S1_din sin parciales: 100/100 semillas idénticas en texto a `experimento_Q_completo.csv` en las 66 columnas.**
- Después corrió S2 y S3 (cuatro condiciones, 100 semillas) sin detenerse.

Las salidas llevan EXPLORATORIO en el nombre, los CSV la columna `exploratorio` = 1 y los textos EXPLORATORIO en la primera línea:
- `experimento_Q_EXPLORATORIO_S2_S3.csv` (800 filas);
- `reproduccion_S1_din_EXPLORATORIO.csv`;
- `registro_Q_EXPLORATORIO.txt`, `resumen_Q_EXPLORATORIO.txt` y `corrida_Q_EXPLORATORIO.log`;
- `parciales/exploratorio_*`;
- `fig_EXPLORATORIO_*`;
- `manifiesto_sha256_Q_EXPLORATORIO.txt`.

**Criterios de falla (los cuatro del Exp O; acá no detienen), sumas sobre los 100 episodios:**

| | contactos | agotados | fallbacks del QP | infactibles con obstáculo activo | d_min centro→superficie |
|---|---|---|---|---|---|
| `S2_din` | 0 | 0 | 5 | 1 | 0.12054343 |
| `S2_quieto` | 0 | 1 | 0 | 0 | 0.14718863 |
| `S2_sinvel` | 0 | 0 | 0 | 0 | 0.09768094 |
| `S3_din` | 0 | 13 | 154 | 2 | 0.07890187 |
| `S3_quieto` | 0 | 3 | 0 | 2 | 0.14020460 |
| `S3_sinvel` | 13 | 5 | 79 | 3 | 0.07500000 |

Con la regla, `S2_din` y `S3_din` la habrían disparado.

**Eventos raros: episodios con al menos un evento, de 100, con su IC95 de Clopper-Pearson.** En el control, el contacto y el acercamiento "no aplican": el obstáculo no es físico, los agentes lo atraviesan y "bajo 0.13 m" da 100/100.

| | fallback | agotado | contacto | bajo 0.13 m |
|---|---|---|---|---|
| `S2_ctrl` | 0 [0.0000, 0.0362] | 0 [0.0000, 0.0362] | no aplica | no aplica |
| `S2_quieto` | 0 [0.0000, 0.0362] | 1 [0.0003, 0.0545] | 0 [0.0000, 0.0362] | 0 [0.0000, 0.0362] |
| `S2_din` | 2 [0.0024, 0.0704] | 0 [0.0000, 0.0362] | 0 [0.0000, 0.0362] | 1 [0.0003, 0.0545] |
| `S2_sinvel` | 0 [0.0000, 0.0362] | 0 [0.0000, 0.0362] | 0 [0.0000, 0.0362] | 11 [0.0562, 0.1883] |
| `S3_ctrl` | 0 [0.0000, 0.0362] | 0 [0.0000, 0.0362] | no aplica | no aplica |
| `S3_quieto` | 0 [0.0000, 0.0362] | 3 [0.0062, 0.0852] | 0 [0.0000, 0.0362] | 0 [0.0000, 0.0362] |
| `S3_din` | 5 [0.0164, 0.1128] | 8 [0.0352, 0.1516] | 0 [0.0000, 0.0362] | 28 [0.1948, 0.3787] |
| `S3_sinvel` | 3 [0.0062, 0.0852] | 5 [0.0164, 0.1128] | 3 [0.0062, 0.0852] | 47 [0.3694, 0.5724] |

Las comparaciones pareadas van con la McNemar exacta, bilateral, sobre los episodios discordantes: b/c son los episodios con el evento sólo en el primero y sólo en el segundo.

**El fallback y la distancia: primero el hecho, después la coincidencia y al final la hipótesis.**
1. **El hecho, por construcción.** Mientras el QP no tiene solución, el filtro manda u = (0, 0) **sin certificado**, y en esos pasos la garantía de invarianza del filtro no aplica.
2. **La coincidencia, por episodio.**
   - En `S3_din`, los 4 episodios que bajan de 0.10 m (420025, 420048, 420057 y 420099) están entre los 5 con fallback. En los otros 95, d_min no baja de 0.1208.
   - En `S3_sinvel`, los 3 episodios con contacto (420013, 420057 y 420090) son exactamente sus 3 episodios con fallback.
   - En `S2_din`, los 2 episodios con fallback no bajan de 0.13 m (d_min 0.13160467).
3. **La hipótesis, pendiente del diagnóstico.** Con el obstáculo en movimiento, detenerse no es seguro, y el mínimo de `S3_din` (0.07890187 m, a 3.9 mm del disco de contacto) habría ocurrido en un paso de fallback.
   - Los datos por episodio muestran que fallback y acercamiento coinciden, **no cuándo**.
   - Lo resolvería el diagnóstico de los 10 episodios con fallback, que por ahora queda afuera.

**Por eso "seguridad intacta, vitalidad degradada" no describe S3.** En los episodios con fallback lo que falla es el solver, y con él deja de aplicar la garantía.

**La hipótesis del encierro (§2.3 de la propuesta), observada como la anticipó §2.3.**
- Los fallbacks del QP aparecen sólo con el obstáculo en movimiento: 5 en 2/100 episodios de `S2_din` y 154 en 5/100 de `S3_din`, contra 0 con los obstáculos quietos.
- Ninguna fila F1 se saturó en ningún nivel.
- **Los datos por episodio no separan las dos vías de infactibilidad:**
  - el término de velocidad, que con h < s/α hace infactible u = 0;
  - la erosión del margen hasta h < 0, que también da fallbacks sin el término: `S3_sinvel` tiene 79 en 3/100, y sin el término, por construcción, un fallback exige algún h < 0.

**Atribución por semilla y prueba exacta pareada:**
- **Fallbacks: al movimiento, por un argumento estructural y no por la prueba exacta.**
  - Con obstáculos quietos, u = 0 es factible mientras todos los h ≥ 0, así que ahí sólo puede haber fallback después de una violación. No hubo ninguno.
  - La McNemar exacta, din frente a quieto, no los separa: 2/0, p = 0.5000 en S2; 5/0, p = 0.0625 en S3.
- **Agotados de S3: al obstáculo, no al movimiento. El contraste con S1 es explícito.**
  - En S1, el agotado aparecía también en el control, en la misma semilla (420001).
  - En S3, ninguno de los 8 episodios con agotado de `S3_din` tiene agotado en el control: 8/0, p = 0.0078. Ahí sí es el obstáculo.
  - No se puede decir que sea el movimiento: contra el quieto da 8/3, p = 0.2266.
- **Infactibles con obstáculo activo:** S2 da 1/0 contra el quieto (p = 1.0000) y S3 2/2 (p = 1.0000). No hay atribución.
- Por semilla, ningún evento de falla de `Sk_din` se repite en la misma semilla de `Sk_ctrl` o de `Sk_quieto`. Sólo la 420057 de S3 comparte el agotado y el fallback con `S3_sinvel`.

**El término de velocidad conserva margen.**
- **Episodios bajo 0.13 m** (con el término frente a sin él):
  - S2: 1 frente a 11 (sinvel − din 10/0, p = 0.0020);
  - S3: 28 frente a 47 (28/9, p = 0.0026).
- **Contactos de S3:** 0 frente a 3 episodios (3/0, p = 0.2500), todos por empuje del obstáculo. Apuntan en la misma dirección, pero no son significativos.

**Costo en tarea** (pareado; denominadores del §3.6):

| | din − ctrl (accesible) | din − quieto (fuera del arranque) | intervención din − ctrl |
|---|---|---|---|
| S2 | +0.03586702 [+0.02168296, +0.05005108]* | +0.01406646 [+0.00052355, +0.02760937]* | +0.19288800 [+0.16916511, +0.21661089]* |
| S3 | −0.00147768 [−0.01630747, +0.01335211] | −0.01027655 [−0.02445920, +0.00390609] | +0.32190000 [+0.30038257, +0.34341743]* |

- **En S2 el movimiento sigue subiendo la cobertura,** como en S1.
- **En S3 ya no se distingue de cero.** La intervención es casi toda del obstáculo (ligante +0.29051200 en S3), y la ocupación de la periferia sube +0.10771200 [+0.08916852, +0.12625548]*.

**Lectura.**
- **Fuera de la regla y con F1 no hubo contacto en S2 ni en S3, pero en S3 eso no es una garantía.** Los acercamientos bajo 0.10 m de `S3_din` están todos en episodios con fallback: tramos en los que el filtro, por construcción, manda u = (0, 0) sin certificado. Que el mínimo ocurra justo en esos pasos es la hipótesis pendiente.
- **El término de velocidad conserva margen** (episodios bajo 0.13 m: p = 0.0020 en S2 y p = 0.0026 en S3), pero no impide los fallbacks.
- **Los fallbacks aparecen sólo con el obstáculo en movimiento**, como anticipó §2.3, aunque los datos no separan h < s/α de la erosión del margen.
- **Los agotados de S3 son del obstáculo, no del movimiento.**

**No sustenta:**
- un cambio del veredicto del Exp Q (S1 detiene por la regla);
- nada sobre el laboratorio;
- que la garantía de no contacto sea robusta en S3: queda a 3.9 mm del contacto, en un episodio con fallback;
- que el mínimo ocurra con el agente detenido (es la hipótesis pendiente del diagnóstico);
- que el rescate de F2 resuelva estos encierros: no se probó.

**Verificación:**
- `verificar_cifras_exploratorio_Q.py` recalcula cada cifra del resumen exploratorio y de esta subsección. El Clopper-Pearson y la McNemar los recalcula con código propio, sin scipy. Comprueba también la reproducción de S1_din, el sha256 de S1, la huella, los rótulos y el pareo (resumen 3182/3182, subsección 439/439, fijos 609/609). Desde el 24-10 extrae además cada cifra del texto y exige que sea un valor recalculado o una constante de diseño (n, umbrales, número de sección);
- `test_exploratorio_Q.py`: 8 pruebas, entre ellas la igualdad del IC y de la p de los dos códigos, y valores conocidos;
- mutaciones: dos cifras de las secciones nuevas del resumen y tres de esta subsección, todas detectadas. La primera mutación de la subsección (una p que aparece en dos lugares) había pasado con el chequeo anterior, que sólo pedía la cifra en algún lugar del texto: por eso se agregó la extracción de cifras;
- el AST de los scripts nuevos: "sólo orquestan";
- el chequeo de congelados de la campaña: "IGUAL a lo probado" (24-10, 09:42).

**Costo:** la corrida, 28.6 min de máquina (20:22–20:51 del 19-10, con la PC libre), de los que 185 s fueron la reproducción de S1_din. La corrección del 24-10 no corrió episodios.
