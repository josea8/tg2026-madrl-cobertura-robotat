# Spec para Claude Code: cierre de la campaña L2_obstaculo_2 con 30 incluidas

## Decisión de José (13-11)

Cierro la campaña `L2_obstaculo_2` como está: 73/100 intentos y 30/50 incluidas, con veredicto MÍNIMO. Desde el 09-11 no hay más turnos en el Robotat. No se sigue hasta el tope ni se hace el mapa de la sonda.

**Chequeo de la PC de las 18 incluidas del 06-11** (§10.2 del reporte del 13-11): se declaran como "`CHEQUEO OK` declarado por el operador, sin salida pegada y sin hora. Según el operador, la app de Claude se cerró antes de lanzar a las 19:38:52; la hora del cierre no consta". No cuentan como chequeo propio con salida.

**Los demás pendientes del §10.3** (repetir la L0 con `CHEQUEO OK`, la recalibración de Motive, el cierre que no muestra su causa y los otros) quedan sin resolver. Van como salvedades en el reporte final.

## Pasos, en este orden

Siguen la sección "Réplica y cierres" de `PROTOCOLO_L0_L2.md` y `PLAN_ANALISIS_campana_L2.md`. Los comandos van desde la carpeta del coordinador (`primerafase_webots/controllers/coordinador_enjambre`).

1. **Comprobaciones previas, de sólo lectura.**
   - Que no haya ninguna sesión abierta ni candado en el libro.
   - Que los archivos congelados den "IGUAL a lo probado".
   - El estado del libro: intentos, incluidas y reservas.

   Mostrame el resumen y el comando exacto del cierre, y **esperá mi "cerrar" antes de correrlo**, porque no tiene vuelta atrás.
2. **Cierre:**

   ```text
   python demo_obstaculo_movil.py --modo L2 --robot-obstaculo 4 --campana L2_obstaculo_2 --cerrar-campana "Fin del tiempo disponible: no hay más turnos en el Robotat desde el 09-11. 73/100 intentos, 30 incluidas (MÍNIMO)."
   ```
3. **Réplica de las tomas:**

   ```text
   python replica_con_obstaculo.py --campana L2_obstaculo_2
   ```

   - Con la PC enchufada y limpia: sin Chrome, ChatGPT, Omen ni el servidor de Inventor.
   - El chequeo previo de la PC tiene que dar `CHEQUEO OK` antes de cada lanzamiento, y su salida se pega en la bitácora.
   - Si sale con 3, el mismo comando con `--reanudar` o `--suplementaria`, hasta que salga con 0.
   - Si el chequeo no da OK porque la app de Claude o su servidor de Inventor están abiertos, dame los comandos y lo lanzo yo desde una PowerShell común, con la app cerrada.
4. **Análisis fijado:**

   ```text
   python analizar_campana_l2.py --campana L2_obstaculo_2
   ```

   Sin `--desvio`. Si se niega, pará y explicame por qué antes de tocar nada.
5. **Verificador independiente:**

   ```text
   python verificar_campana_l2.py <carpeta del análisis>
   ```

   Tiene que salir con 0.
6. **Reporte final.** `REPORTE_<fecha>_cierre_campana_L2.md`, con su zip de datos crudos y su `verificar_cifras`, en el formato de los reportes anteriores. Tiene que traer:
   - el principal del plan (§3): la brecha de cobertura entre el hardware y la réplica, con su IC95, y sus sensibilidades;
   - la seguridad (§4), el costo del obstáculo (§5) y la comparación descriptiva con el 30-09 (§6);
   - el a3 NO PASA, con su diagnóstico y su IC95, como salvedad de esa comparación, y `cierre_a3_20261010_b/` completo en el zip;
   - los descriptivos del §7, rotulados como post hoc;
   - las declaraciones del §8, el chequeo de cada sesión y de cada lanzamiento de la réplica, y la declaración del 06-11 de arriba;
   - los pendientes sin resolver, como salvedades;
   - al final, un bloque corto "Para la tesis" con las cifras que van al documento, cada una con su unidad y su fuente.
7. **Bitácora.** Una entrada con respaldo previo, como en las anteriores.

## Reglas

- No cambiar archivos congelados, el plan, los márgenes ni el criterio de inclusión. Nada de `--corregir-campana`.
- Nadie mira la cobertura antes del paso 4.
- Nada en paralelo con la réplica: ni el Exp R ni otra corrida pesada.
- Para el verificador, usar la versión de Python que indica el §11 del reporte del 13-11.
- No tocar la tesis ni Overleaf.
- Si algo no cuadra (un conteo, un sha256, una corrida que se niega), parar y reportar en lugar de arreglarlo por tu cuenta.
