### Resultados (corrida del 2026-11-13, semillas nuevas 420110–420509)

**Corrida.** `correr_experimento_R.py experimento`, con el "listo" de José, en dos tramos:
- **Desde las 20:25:13.** Corrió once celdas. La PC se desenchufó a las 21:04:13 (Kernel-Power 105), en medio de S3_ctrl. Esa celda había arrancado enchufada (83 %) y tardó 460.8 s, frente a 172.5 s de S1_ctrl y 198.0 s de S2_ctrl; su t_episodio_s medio fue 12.50 s. Antes de S3_sinvel la compuerta de energía dio PARAR.
- **21:30:22–21:34:46.** Ya enchufada otra vez, reutilizó las once celdas, previa comprobación de sus firmas, y corrió S3_sinvel.

El cálculo es determinista: el corte sólo cambia los tiempos de pared, que no entran en ninguna hipótesis.

**El registro** es `resultados/registro_R.txt`:
- FILAS 4800 (4800 distintas) y autochequeos de la Parte B con 0 problemas en las 4800 filas;
- la prueba física del pareo discrimina: 30 agente-pasos en 29 episodios con fallback (2 de ellos con 0);
- 33 trazas, en biyección con sus filas; se esperaban 44, con intervalo [31, 57];
- «PARTE B: OK»;
- congelados de la campaña "IGUAL a lo probado" al empezar y al terminar;
- el manifiesto pre (`manifiesto_R_pre_20261113_2021.txt`) con todas sus entradas iguales al terminar.

**Análisis y verificación.**
- `analizar_experimento_R.py`, en la versión de la adenda 1, escribió `resultados/resumen_R.txt` y tres figuras.
- `verificar_cifras_R.py` encontró las 258 líneas del resumen iguales a las recalculadas desde el crudo, texto contra texto. Recalculó la Parte B en 33 filas desde su traza y en 3567 por identidad, y contrastó con scipy 48 valores, con una diferencia máxima de 2.2e-16.
- `literales_bitacora_R.py` verifica cada cifra y cada veredicto de esta subsección.

**Resultados.** n = 400 por celda; McNemar exacta (b = sólo en A); IC95 de Clopper-Pearson; α = 0,05; palabras del §2.4.

| Hipótesis | Clase | Datos | Veredicto |
|---|---|---|---|
| H1-S3 | primaria | S3_din 12/400, S3_quieto 0/400; b/c = 12/0; p = 0.0005 | sostenida |
| H1-S2 | secundaria | S2_din 3/400, S2_quieto 0/400; b/c = 3/0; p = 0.2500 | no sostenida |
| H2-S2 | primaria | S2_sinvel 53/400, S2_din 27/400; b/c = 41/15; p = 0.0007 | sostenida |
| H2-S3 | primaria | S3_sinvel 177/400, S3_din 88/400; b/c = 133/44; p < 0.0001 | sostenida |
| H3a | primaria | S3_din 20/400, S3_ctrl 1/400; b/c = 20/1; p < 0.0001 | sostenida |
| H3b | secundaria | S3_din 20/400, S3_quieto 11/400; b/c = 19/10; p = 0.1360 | no sostenida |
| H4 | secundaria | Δ_S1 − Δ_S3 +0.02443442 [+0.01519369, +0.03367515]; Δ_S2 − Δ_S3 +0.03761557 [+0.02807480, +0.04715635] | sostenida |
| H5a | primaria | contacto en Sk_din: 0/400 en S1, S2 y S3 | cumplida |
| H5b | secundaria | S3_sinvel 2/400, S3_din 0/400; b/c = 2/0; p = 0.5000 | no sostenida |
| H6a-S3 | secundaria | 6 de 6 episodios bajo 0,10 m con el mínimo en la ventana | cumplida |
| H6a-S1, H6a-S2 | secundaria | ningún episodio bajo 0,10 m | no evaluable en el nivel |
| H6b-S1, H6b-S2, H6b-S3 | secundaria | 0/400 bajo 0,10 m fuera de la ventana en cada nivel | cumplida |

Con Holm sobre la familia de 7, las cuatro pruebas con p sostenidas siguen bajo 0,05 en la dirección predicha (p Holm: H1-S3 0.0024, H2-S2 0.0027, H2-S3 < 0.0001, H3a 0.0001). Holm no cambia ninguna palabra.

**Lectura.**
- **El encierro aparece con el movimiento en S3 (H1-S3).** Con obstáculos quietos no hubo ningún fallback en ningún nivel (0/400 en S1, S2 y S3). Es descriptivo: no se escribe que el encierro "necesita" el movimiento. En S2 hubo 3 fallbacks contra 0 (H1-S2 no sostenida, p = 0.2500), lo que no equivale a ausencia de efecto (§6).
- **El término de velocidad conserva margen (H2) en S2 y en S3.** En S3, sin él, 177 de 400 episodios bajan de 0,13 m; con él, 88.
- **Los agotados de S3 son del obstáculo (H3a).** Que el movimiento agregue agotados (H3b) queda no sostenida: Δ de tasas +0.02250000 [-0.00382795, +0.04882795]. Por el §2.3:
  - no se corrige la frase del exploratorio (D7, que se aplicaba sólo si H3b quedaba sostenida);
  - tampoco se afirma que los agotados no dependan del movimiento.
- **H4, sostenida: en S3 el efecto del obstáculo móvil (din − ctrl) sobre la cobertura accesible es menor, con signo, que en S1 y en S2.** El efecto es positivo en los tres niveles (con el obstáculo móvil la cobertura accesible es mayor que en el control), y en S3 casi desaparece. Δ din − ctrl: S1 +0.03306994, S2 +0.04625109, S3 +0.00863552.
- **Seguridad (H5a, H6).**
  - **Contactos.** Ninguno en din en los 1200 episodios. 0/400 por nivel acota la tasa de contacto por debajo de 0.0092 en cada nivel; no es una tasa cero.
  - **Acercamientos bajo 0,10 m.** Los 6 de S3_din caen en la ventana de un fallback del agente que se acerca. En 4 el mínimo está dentro del fallback, con rachas de 10 a 30 decisiones, y en 2 justo después.
  - **El más profundo** es S3_din 420289: 0.0755 m, a 0,5 mm del contacto (0,075 m), dentro de un fallback de 30 decisiones.
  - **Fuera de la ventana de 5 decisiones de un fallback** ningún agente bajó de 0,10 m en ningún nivel (H6b). Esto no significa «fuera de los fallbacks»: con W = 1, es decir, contando sólo las decisiones que no están ellas mismas en fallback, S3 tiene 3/400 episodios bajo 0,10 m (ver la sensibilidad).
- **Contactos sin el término de velocidad (H5b, no sostenida).** Hubo 2 episodios de S3_sinvel, 420402 y 420494, con 7 agente-pasos de contacto en total. Los 7 caen en la ventana de un fallback del propio agente. Con b/c = 2/0 la McNemar exacta no puede bajar de p = 0.5000, y «no sostenida» no es ausencia de efecto (§6).
- **Sensibilidad de H6** (descriptiva, sin veredicto).
  - Con W = 5 y umbral 0,13 m quedan fuera de la ventana 80/400 episodios en S3 (20 %), 26/400 en S2 y 6/400 en S1. El prerregistro esperaba en S3 al menos un ~23 %, así que el resultado queda algo por debajo. Ese ~23 % venía de los 23 de 100 episodios del exploratorio que bajaron de 0,13 m sin ningún fallback.
  - Con W = 1, en 0,10 m, S3 da 3/400.

**Lo que R no sustenta.** Es el §6 del prerregistro, palabra por palabra al final de `resumen_R.txt`. Lo esencial:
- R no cambia el veredicto del Exp Q;
- S2 y S3 no "pasan" la regla del Exp O;
- la garantía de no contacto no es robusta donde hay fallbacks, porque ahí el filtro manda u = (0, 0) sin certificado;
- H5a «cumplida» no es una tasa cero;
- una prueba «no sostenida» no es ausencia de efecto (aquí H1-S2, H3b y H5b);
- no se conserva la cota de diseño de 0,13 m fuera de los fallbacks: con W = 5, 80/400 episodios de S3_din bajan de 0,13 m fuera de la ventana;
- H6 mide coincidencia en el tiempo, no causa;
- R no dice nada del laboratorio, del rescate de F2 ni de otras políticas o geometrías;
- no es una verificación independiente del código.

**Criterios de cierre del spec (§6).**
1. **`comparar_ast_R.txt`.** Las cuatro comprobaciones están en OK: el spec pedía dos y el prerregistro sumó otras dos.
2. **Control.** 1200/1200 filas idénticas en texto en las 66 columnas, y pasos_agente_fallback = qp_fallbacks en las 1200.
3. **Pasabilidad.** OK en S1, S2 y S3 con las 400 semillas.
4. **Manifiesto pre.** Se hizo a las 20:21:42, antes del inicio de los dos tramos, y `experimento` lo comprobó al empezar y al terminar.
5. **CSV.** 4800 filas, 12 celdas × 400 semillas, sin semillas repetidas ni faltantes, y prerregistrado = 1 en todas.
6. **Resumen.**
   - Cada hipótesis tiene la palabra que fija el §2.4.
   - `verificar_cifras_R.py` está en orden con el resumen, y `literales_bitacora_R.py` con esta subsección.
   - Las mutaciones se detectan: una cifra y un veredicto invertido en cada documento.
7. **Figuras.** La leyenda queda afuera y el rótulo arriba, sin nada tapado; se revisaron una por una.
8. **Pruebas, huellas y congelados.**
   - Las pruebas están en verde: `test_experimento_R` 50/50 y `test_verificar_cifras_R` 44/44.
   - La huella de Q coincide al inicio y al final de cada subcomando.
   - Los sha256 de S1 y de los crudos exploratorios siguen intactos, y los congelados dan "IGUAL a lo probado".
9. **Fuera de la carpeta del Exp R** cambiaron dos archivos:
   - la bitácora, con tres respaldos (preExpR, preCorrExpR y preResultadosR) en lugar de los dos que preveía el spec, porque la pasada pre llevó una corrección de redacción;
   - `PROTOCOLO_L0_L2.md:71`, como excepción declarada: el filtro simétrico, con respaldo, previsto por el prerregistro.

   Fuera de los bloques del Exp R, la bitácora es idéntica byte a byte a la versión anterior a cada pasada. El 13-11 a las 19:26 la modificó además otra sesión (respaldo preRonda3), fuera de los bloques del Exp R.
10. **`manifiesto_sha256_R.txt`.** Se hizo al cierre.
