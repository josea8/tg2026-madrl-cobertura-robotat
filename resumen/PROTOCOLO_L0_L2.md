# Demo del obstáculo móvil: protocolo de laboratorio L0–L2

**Estado:** fijado ANTES de la sesión.
- Decisiones de José del 2026-10-02, 03-10, 07-10, 08-10 (la campaña), 09-10 (el criterio de seguridad), 10-10 (toma sin distancia medida, cierre a3, cierre b, las dos convenciones de la réplica, el resultado del a3, y la corriente y la PC limpia en cada sesión y en la réplica) y 17-10 (el 2 en lugar del 6 en el enjambre y un bloque nuevo de semillas para la campaña nueva `L2_obstaculo_2`).
- Rige porque la 2.ª corrida del conjunto de confirmación pasó el criterio de la Fase 0 (`REPORTE_2026-10-02_obstaculo_fase0.md`).
- **Desde el 08-10, la L2 se mide como CAMPAÑA** (§L2 como campaña de medición). La L2 suelta de abajo queda para pruebas y para el video.
- Respaldos: `PROTOCOLO_L0_L2_respaldo_20261007_preColocacion.md` (antes de la colocación automática) y `PROTOCOLO_L0_L2_respaldo_20261008_preCampana.md` (antes de la campaña).

**Código:** `primerafase_webots/controllers/coordinador_enjambre/demo_obstaculo_movil.py` y `colocacion_con_obstaculo.py`.
- Formulación F2: predictor con τ_c = 0.65 s, peso de giro condicional y rescate del QP.
- Factor 0.40.
- Freno de respaldo ACTIVO en la L2. Es una capa redundante: la separación la sostiene el filtro de los agentes.
- Salidas en `resultados_demo_obstaculo/`, con nombres fechados: nada se pisa.

**Robot obstáculo: el 4** (decisión de José, 2026-10-07: el 7 lo está usando otro compañero).
- **Todos los comandos llevan `--robot-obstaculo 4`.** La bandera es obligatoria: sin ella el programa no arranca.
- El 4 usa el marcador 4 (regla N ↔ N) y el enlace `192.168.50.104:9090`. No es agente del enjambre (1, 5, 8, 2, 9: el 2 en lugar del 6, aprobado por José el 17-10; el 16-10 el 6 dejó de girar bien y el 3 no respondió).
- **Su offset de rumbo, +81.90°, es el de la tabla y nunca se verificó.** La L0 lo mide (§L0). En el 8 la tabla erraba 5.0° y en el 1, 1.6°.
- **El 7, el 6 y el 3 no tienen que estar en la arena:** el programa no los ve, y serían obstáculos sin seguimiento.

**Colocación AUTOMÁTICA en la L1 y la L2** (OK de José, 2026-10-07: Fase B de `PROPUESTA_colocacion_autonoma_obstaculo.md`).
- **Los 5 agentes van solos** a sus blancos alrededor del 4 **quieto**:
  - los blancos quedan a ≥ 0.65 m del 4;
  - lo rodean si lo tienen en el camino;
  - la barrera del 4 es la fila del Exp O;
  - entre agentes, el 50/50 de siempre.
- **El 4 no se mueve solo,** porque la Fase A no está implementada. En la L2 arranca desde donde lo dejó la toma anterior, que es la proyección de su pose sobre el círculo. Si está fuera de su envolvente (±6 cm del círculo, ±25° de la tangente), la sesión pide colocarlo **a mano** y dice dónde.
- **Un Enter por toma,** con el aviso "Los agentes van a ir SOLOS…", que nombra el robot, el marcador y la IP del obstáculo. Antes de ese Enter la sesión **descarta lo que se haya tecleado de más**.
- **Antes de colocar, espera a que el 4 quede quieto,** hasta 3 s. Al terminar una toma sigue andando por el retardo.
- **Durante la colocación todo se detiene con regla de parada** (exige la "s") si:
  - hay contacto (< 0.15 m entre centros medidos);
  - el 4 se mueve ("NO FRENA");
  - el marcador del 4 se congela o se pierde;
  - el enlace del 4 o el de un agente se cae.
- **Después de colocar,** los chequeos de siempre, más:
  - marcador congelado durante la colocación;
  - quietud de todos;
  - agentes a ≤ 0.12 m de su blanco;
  - el 4 en su envolvente.

  Si algo falla, hay reintento: corregir a mano y Enter, y se vuelven a colocar solos, hasta 5 veces sin gastar el intento. El que no avanzó rodea por el otro lado o primero se aleja 10 cm.
- **Con `--colocacion manual`** todo es como antes, con la guía y a mano.

**Seguridad, en todas las etapas:**
- Una persona junto a la arena, lista para levantar al obstáculo.
- La parada por software no es una parada de emergencia (README §S1).

**Chequeo previo de la PC, antes de cada sesión del laboratorio y de cada lanzamiento de la réplica** (decisiones de José del 10-10). Cubre la L0, la L1, la L2 y cada sesión de la campaña; en la réplica, también cada `--reanudar` o `--suplementaria`. En los ensayos, las tomas que se perdieron fueron por carga de la máquina, y con este registro se interpreta el p95 del ciclo de cada corrida.
- **Corriente:** la laptop enchufada y siempre con el mismo modo de energía de Windows.
  - La referencia es la que tenía la laptop el 10-10: plan "Equilibrado" (`381b4222-f694-41f0-9685-ff5bb260df2e`) con el modo de energía "Mejor rendimiento" enchufada (`ded574b5-45a0-4f42-8737-46345c09c238`).
  - Si el chequeo da otro, se corrige antes de lanzar: el modo, en Configuración → Sistema → Energía y batería, donde también se apaga el ahorro de energía si sale ACTIVO; el plan, con `powercfg /setactive 381b4222-f694-41f0-9685-ff5bb260df2e` en la misma PowerShell.
  - Si José elige otro modo, la referencia se cambia aquí, en el chequeo, antes de la primera sesión.
- **PC limpia:** sin Chrome, ChatGPT, Omen ni el servidor de Inventor ("sin Omen" al pie de la letra).
  - Cerrar Chrome y ChatGPT.
  - Para OMEN, cerrar OMEN Gaming Hub desde la bandeja (cierra `OmenCommandCenterBackground.exe` y `HP.OMEN.VirtualCamHelper.exe`). Hay otros cuatro componentes que no se cierran desde la bandeja; se detienen desde una PowerShell como administrador con `Stop-Service HPOmenCap; Stop-Process -Name OmenInstallMonitor, OverlayHelper, SystemOptimizer -Force`:
    - `OmenCap.exe` es el servicio de Windows `HPOmenCap` ("HP Omen HSA Service"). Se detiene con `Stop-Service` y no con `Stop-Process`, porque su recuperación lo reinicia.
    - `OmenInstallMonitor.exe`, `OverlayHelper.exe` (el OMEN Overlay) y `SystemOptimizer.exe` (el optimizador de OMEN) corren elevados y los lanza Windows al iniciar sesión; el chequeo los busca por nombre.
    - Todo vuelve al reiniciar, o con `Start-Service HPOmenCap`.
  - El servidor de Inventor es un `python` (`servidor_inventor_mcp.py`) que lanza la app de Claude: se cierra la app de Claude (la sesión o la réplica se lanzan desde una PowerShell común) o se desactiva ese conector.
- **El chequeo**, en una PowerShell común (no hace falta administrador). Tiene que terminar en `CHEQUEO OK`; si da `CHEQUEO FALLA`, se corrige lo que muestra y se vuelve a correr antes de lanzar:

   ```powershell
   Add-Type -Namespace Chequeo -Name Energia -MemberDefinition '[DllImport("kernel32.dll")] public static extern bool GetSystemPowerStatus(byte[] estado);'
   $ref = @{ plan = '381b4222-f694-41f0-9685-ff5bb260df2e'; modo = 'ded574b5-45a0-4f42-8737-46345c09c238' }
   $nombres = @{ '00000000-0000-0000-0000-000000000000' = 'Equilibrado'; '961cc777-2547-4f9d-8174-7d86181b8a7a' = 'Mejor eficiencia energetica'; 'ded574b5-45a0-4f42-8737-46345c09c238' = 'Mejor rendimiento'; '381b4222-f694-41f0-9685-ff5bb260df2e' = 'Equilibrado' }
   $k = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes'
   $plan = "$($k.ActivePowerScheme)"
   $modo = "$($k.ActiveOverlayAcPowerScheme)"; if (-not $modo) { $modo = '00000000-0000-0000-0000-000000000000' }
   $e = New-Object byte[] 12; if (-not [Chequeo.Energia]::GetSystemPowerStatus($e)) { $e[0] = 255; $e[3] = 255 }
   $enchufada = $e[0] -eq 1; $ahorro = $e[3]
   $procesos = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'chrome|chatgpt|omen|overlayhelper|systemoptimizer' -or $_.CommandLine -match 'servidor_inventor_mcp|correr_experimento_R|analizar_experimento_R|comparar_ast_R|potencia_R|test_experimento_R' })
   "chequeo previo de la PC: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
   "  corriente: $(switch ($e[0]) { 1 {'enchufada'} 0 {'A BATERIA'} default {'desconocida'} }) | ahorro de energia: $(switch ($ahorro) { 0 {'apagado'} 1 {'ACTIVO'} default {'desconocido'} })"
   "  plan: $plan ($($nombres[$plan])) | modo enchufada: $modo ($($nombres[$modo]))"
   "  procesos: $(if ($procesos.Count) { ($procesos | ForEach-Object { "$($_.Name) [$($_.ProcessId)]" }) -join ', ' } else { 'ninguno' })"
   if ($enchufada -and $ahorro -eq 0 -and $plan -eq $ref.plan -and $modo -eq $ref.modo -and -not $procesos.Count) { 'CHEQUEO OK' } else { 'CHEQUEO FALLA: no lanzar' }
   ```

- **Registro:** la salida del chequeo se pega en la bitácora, con la sesión o el lanzamiento y su comando. Si se lanzó sin `CHEQUEO OK`, se anota qué falló, y el reporte lo declara.

---

## L0: el 4 solo

```text
python demo_obstaculo_movil.py --modo L0 --robot-obstaculo 4
```

**Procedimiento:**
1. La sesión pide colocar al 4 **a mano** en (1.5, 0.9) del env, mirando +x, con ±8 cm y ±30°, y lo verifica. En la L0 la colocación sigue siendo a mano, porque la Fase A no está.
2. Después hace 10 arranques desde parado.
   - Cada uno dura 6 s desde el primer mando, patada incluida (0.08 m/s, ≤ 1 s).
   - Sigue el círculo de R 0.60 en (1.5, 1.5), a 0.05 m/s, en sentido antihorario.
   - Entre arranques hay 2 s de pausa.
3. El enjambre fuera de la arena.

**Criterio:**
- **10 de 10 arranques:** cada uno se mueve ≥ 3 mm antes de 1.5 s.
- **Error radial máximo < 5 cm,** sin contar los 2 s de enganche de cada marcha.
- **Offset de rumbo a ≤ 3° de la tabla** (decisión de José): la L0 lo mide en los tramos de crucero comparando la dirección del desplazamiento con el rumbo medido, con ≥ 20 pares.
- **Aborto inmediato:** si en algún momento, enganche incluido, el error radial supera 10 cm, la L0 frena y termina con FALLO. También aborta si el marcador se congela, si se pierde la pose o si la colocación falla 6 veces.

**Resultado:** `<fecha>_L0_resumen.csv`, con veredicto, arranques, error radial, ω saturado y la diferencia de offset. Se escribe en todos los caminos.

**La L0 habilita la L1 y la L2.**
- El programa **no arranca la L1 ni la L2** (sale con código 6) si la última L0 del 4 no dio OK, o si su offset difiere más de 3° de la tabla o no se pudo medir.
- Si difiere más de 3°, **se frena antes de la L1:** la consola imprime la corrección propuesta para `config_robotat.py`, que se aplica sólo con el OK de José.
- `--forzar` saltea este chequeo.

## L1: el 4 ENCENDIDO y quieto en el centro (el Exp O en físico)

```text
python demo_obstaculo_movil.py --modo L1 --tomas 3 --intentos 6 --robot-obstaculo 4
```

- **Opción (b) de José:** el 4 va **encendido y conectado**.
  - Durante las tomas se le manda (0,0) en cada decisión y se lo vigila.
  - Si se mueve ("NO FRENA") o se le cae el enlace, la toma se aborta y salta la regla de parada.
- **El 4 se coloca a mano UNA vez** en el centro, (1.5, 1.5) ±8 cm. Es siempre el mismo punto y no se mueve entre tomas.
- **Los agentes van solos,** con blancos a ≥ 0.65 m del 4.
- **Cada toma** son 500 decisiones de política + CBF + escape, con la barrera del obstáculo quieto. Es la **geometría** de la fila del Exp O (D_o = 0.33, sin término de velocidad), evaluada con F2: sobre la pose predicha del agente, con peso de giro y rescate. No es el filtro del Exp O bit a bit; ése sería F1.
- **Criterio:** el mismo de la L2, con 3 tomas. No se exige recorrido del obstáculo.

## L2: el 4 en movimiento (la demo)

```text
python demo_obstaculo_movil.py --modo L2 --tomas 10 --intentos 20 --robot-obstaculo 4
```

**Criterio, fijado antes de la sesión (decisión de José):**

| | definición |
|---|---|
| **Validez de la medición** | la toma corre completa por el lazo del laboratorio (`_correr_episodio`, con todas sus reglas y la regla de 10 s arreglada). Cualquier aborto la invalida, con su motivo. |
| **Toma válida para la demo** | válida, Y **sin intervención del freno de respaldo**, Y ningún agente a < 0.15 m del obstáculo, Y el obstáculo recorrió al menos la mitad de lo comandado (esto último sólo si lo comandado es ≥ 0.20 m) |
| **Métrica principal** | **distancia mínima agente–obstáculo** por toma, entre centros, medida por el mocap a 10 Hz (`d_min_obst_medida`) |
| **Objetivo** | 10 tomas válidas para la demo, en hasta 20 intentos |

**Qué se informa** (`python analizar_sesion_demo.py <…_L2_tomas.csv>`):
- las dos validez por separado, con los motivos;
- las tomas con freno, aparte, como "intervención del freno de respaldo";
- la distancia mínima de cada toma y su distribución sobre las válidas para la medición (mínimo, mediana y máximo), con cuántas quedan bajo 0.185 y bajo 0.15 m;
- aparte, los contactos en tomas no válidas y las reglas de parada que se dispararon, con la respuesta del operador, también las de la colocación.

No hay umbral de aprobación sobre la métrica: se informa.

**Expectativa, del simulador, que no es criterio:**
- Las 120 tomas con política de la Fase 0 quedaron ≥ 0.2696 m, sin ningún freno. Ese simulador no tenía zona muerta de rueda.
- En los ensayos finales con colocación automática y zona muerta (L2 y L1, τ = 0.45 y 0.85 s), 26 de 26 tomas válidas, sin frenos y con un mínimo de 0.3052 m al obstáculo.
- En un ensayo intermedio con τ = 0.85 s hubo 1 freno de respaldo en una toma, con un mínimo de 0.2093 m. Con un solo caso no se puede atribuir a la zona muerta.
- El hardware anduvo 3.5 cm más cerca de la pared que su réplica el 30-09. No sería raro ver ~0.23 m.

**Reglas de parada en la sesión. Desde el 03-10 las aplica el programa.**
- Después de cada toma corrida, válida o no, y durante la colocación: si se cumple una regla, la sesión frena todo y muestra "⛔ REGLA DE PARADA — …". Después pregunta "¿Seguir con la sesión?".
- **Mientras espera la respuesta, sigue frenando cada 1 s** y mantiene vivos los enlaces.
- **Si no pudo confirmar que algún robot frenó, lo dice:** "⚠ NO SE PUDO CONFIRMAR LA DETENCIÓN: … LEVANTARLO / CORTAR ALIMENTACIÓN A MANO".
- **Sólo "s" la continúa.** Enter, "si" o cualquier otra respuesta la termina, con veredicto DETENIDA.
- La regla y la respuesta quedan en el CSV de tomas (`regla_parada`, `parada_respuesta`).

Las reglas:
1. **Contacto:** algún agente a < 0.15 m del obstáculo, en la distancia medida. En la colocación, también entre agentes.
2. **Freno de respaldo en dos tomas corridas seguidas.**
3. **Aborto por el obstáculo:** no se mueve, no frena, enlace caído (también si se reabrió al frenar), se salió del círculo o marcador perdido. Hay que revisar el 4 antes de seguir.
   - Si el aborto fue por pose vencida del 4 con consultas de poses fallidas, se rotula como probable hipo del servidor de poses. Igual se detiene.
4. **Toma corrida sin distancia medida:** no se puede descartar un contacto.
5. **En la colocación:** el enlace de un agente que se cae.

**Qué hace el operador:**
- Revisa la causa antes de contestar, y contesta "s" sólo si está entendida y resuelta.
- La línea `>>> TOMA k` dice por qué una toma no vale.
- Ctrl+C también corta, y los CSV se guardan igual.
- El programa decide **entre tomas** y durante la colocación, no durante la toma. La parada de emergencia sigue siendo la persona junto a la arena.

**Si hay que relanzar una sesión cortada** (L2 suelta, sin campaña; en la campaña se reanuda con el mismo comando):

```text
python demo_obstaculo_movil.py --modo L2 --tomas <faltantes> --intentos 20 --intento-inicial <siguiente> --robot-obstaculo 4
```

- Siguen la numeración, las semillas y la cuenta contra el tope de 20.
- La rampa vuelve en la 1.ª toma de la sesión nueva, y la cuenta de frenos seguidos arranca de cero.
- Resumen de las dos sesiones juntas: `python analizar_sesion_demo.py <tomas_1.csv> <tomas_2.csv>`.

**Tener en cuenta:**
- La rampa de arranque seguro existe sólo en la **primera** toma de la sesión, porque cuenta por canal. Desde la 2.ª, el obstáculo arranca en la decisión 0. La Fase 0 lo cubrió con las variantes "sin rampa".
- **Sin resolver:**
  - **el 4 se coloca a mano** cuando está fuera de su envolvente: en la L0, en la L1 (una vez) y en la primera toma de la L2 si viene del centro. Moverlo solo es la Fase A, que no está implementada;
  - el retroceso por pose repetida va sin CBF, y lo mitiga el freno del 4 a 0.60 m (en la L2; en la Fase 0 no se ejercitó);
  - el offset de rumbo del 4 lo mide la L0.

## L2 como campaña de medición (decisión de José, 2026-10-08)

La L2 se mide como la evaluación del 30-09:
- tomas medidas en el Robotat;
- una réplica pareada en simulación, que corre **después** de cerrar la campaña y nunca en paralelo con el hardware;
- un análisis fijado antes: `PLAN_ANALISIS_campana_L2.md` y `analizar_campana_l2.py`.

El video sale de las mismas tomas. La Fase A sigue fuera. Detalle en `PROPUESTA_campana_L2_obstaculo.md`.

**La campaña de medición es `L2_obstaculo_2`** (José, 17-10: el 2 en lugar del 6, enjambre 1, 5, 8, 2, 9, y un bloque nuevo de semillas, que es el 422000 + k − 1). La primera, `L2_obstaculo` (16-10), quedó **cerrada y descartada** porque el Robotat estaba mal calibrado: ninguna de sus tomas entra en el documento, y no se reabre.

**Antes de abrir la campaña (en este orden):**
1. **L0 del 4 OK, con el offset a ≤ 3° de la tabla** (con el chequeo previo de la PC, como toda sesión). Si hay que corregir el offset en `config_robotat.py`, se corrige con el OK de José y se repite la L0.
   - Sin L0 OK, la campaña no se crea ni se abre (código 6). **`--forzar` no lo saltea.**
   - Una L0 corrida con `--simulador` no cuenta, y si el offset del 4 cambió desde la última L0 (también a mitad de campaña), el programa pide repetirla.
2. **Crear la campaña, UNA sola vez.** Congela el sha256 de los archivos de la lista de abajo; el plan y el script de análisis ya tienen que existir.
   - **Antes de crearla, comprobar que lo que se congela es lo probado.** La referencia es la campaña del ensayo 1e del 17-10, `ensayo_campana_20261017_092424`, con los archivos de la campaña nueva (enjambre 1, 5, 8, 2, 9; semillas 422000…): META, análisis y verificador en 0, 106/106, y las 13 suites (556 pruebas) OK con los mismos archivos. Desde la carpeta del coordinador:

     ```text
     python -c "import json,campana_obstaculo as C; p=json.load(open('resultados_demo_obstaculo/ensayo_campana_20261017_092424/campanas/ensayo/campana.json',encoding='utf-8'))['archivos_congelados']; h=C.hashes_congelados(); d=[k for k in h if h[k]!=p.get(k)]; print('IGUAL a lo probado' if not d else d)"
     ```

     Tiene que decir "IGUAL a lo probado". Si lista archivos, algo cambió después: no crear; revisar y anotar en la bitácora.

```text
python demo_obstaculo_movil.py --modo L2 --robot-obstaculo 4 --campana L2_obstaculo_2 --crear-campana
```

   Meta 50 incluidas, mínimo 30, tope 100 intentos (decisión 2 y plan §2). **No usar `--meta`, `--minimo` ni `--tope-intentos`:** con otros valores, el análisis se niega salvo con un desvío declarado.

**Cada sesión, con la hora de fin fijada antes de empezar y con el chequeo previo de la PC en `CHEQUEO OK`:**

```text
python demo_obstaculo_movil.py --modo L2 --robot-obstaculo 4 --campana L2_obstaculo_2 --hora-fin 17:30
```

- **El libro decide el intento y la semilla** (422000 + k − 1: bloque nuevo por decisión de José del 17-10), y **el plan fija el régimen** (500 decisiones, factor 0.40, colocación automática). Con `--campana` el programa se niega si se da `--tomas`, `--intentos`, `--intento-inicial`, `--decisiones`, `--factor`, `--colocacion` o `--forzar`, aunque sea con su valor por defecto.
- **`--hora-fin`** puede cruzar la medianoche (una hora ya pasada se toma como de mañana), pero no más de 12 h adelante. La consola muestra la fecha y hora que quedó.
- **La sesión corta sola** al llegar a 50 incluidas, al tope de 100 intentos o a la hora de fin. Para seguir, otro día o después de un corte, **el mismo comando**: reanuda donde quedó.
- **Incluida** = válida para la medición Y el 4 recorrió al menos la mitad de lo comandado (sólo si lo comandado es ≥ 0.20 m). **Los frenos y los contactos no excluyen:** son resultados.
- **La consola no muestra la cobertura.** La línea `>>> TOMA k` dice "INCLUIDA n/50" o "NO INCLUIDA (motivo)", y aparte si la toma sirve para el video (la validez de la demo de arriba).
- **Las reglas de parada siguen iguales**, con dos cambios:
  - un "no" (cualquier respuesta que no sea "s") termina la **sesión**, no la campaña;
  - la cadena "freno en dos tomas seguidas" **se arrastra entre sesiones**, con el libro (cuenta sólo las tomas que corrieron).
- **Criterio de seguridad (decisión de José, 09-10): la campaña se cierra SOLA** cuando se acumulan, en toda la campaña, **dos tomas corridas con contacto**: < 0.15 m entre centros medidos con el obstáculo o entre agentes. Las pausas siguen como están; los contactos de la colocación no cuentan (siguen siendo regla de parada de la sesión). Una toma sin distancia medida al obstáculo no cuenta como contacto con el obstáculo; sus pares de agentes sí cuentan (José, 10-10). Al anotar la segunda, la consola muestra "⛔⛔⛔ CAMPAÑA CERRADA — CRITERIO DE SEGURIDAD: …" y no se corre ningún intento más, aunque en la pausa se haya contestado "s"; tampoco se puede abrir otra sesión. Revisar los robots; lo ocurrido va a la bitácora y al reporte.
- **En la pausa de seguridad: para TERMINAR la sesión, "n" y Enter, no Ctrl+C; para seguir, "s", sólo con la causa entendida y resuelta.** La toma ya quedó anotada en el libro ANTES de la pregunta (el criterio de seguridad la cuenta aunque se corte ahí); la respuesta va en una fila aparte. Un Ctrl+C ahí deja la respuesta "interrumpida (Ctrl+C) en la pausa", pero corta la sesión sin la detención ordenada.
- **Ctrl+C a mitad de una toma** (por ejemplo, al ver un contacto): se frena todo y la toma se anota como corrida, cortada y no válida, con lo que alcanzó a correr; cuenta para el criterio de seguridad. Después, revisar antes de reanudar.
- **Ctrl+C o una caída durante la colocación:** la reserva en curso queda "interrumpida" y su semilla gastada. Se reanuda con el mismo comando.
- **Un corte duro a mitad de toma** (corte de luz, ventana cerrada, proceso matado) **pierde esa toma**: los CSV de la sesión se escriben al terminar cada intento, así que sus decisiones no llegan a disco y la reserva queda "interrumpida" en el libro, sin datos. Lo que se vio (por ejemplo, un contacto) va a la bitácora y al reporte. El análisis recuenta desde los CSV sólo las tomas cuyo crudo llegó a disco sin llegar al libro, y lo declara.
- **No abrir `libro.csv` ni los CSV de la sesión en Excel mientras corre:** Excel bloquea la escritura. El libro y los CSV de la sesión reintentan 30 s con un aviso en la consola ("cerralo"). Si sigue bloqueado, la sesión se detiene con error y esa toma queda sin anotar: su reserva, "interrumpida" (el crudo se escribe antes de anotar en el libro). Se reanuda con el mismo comando, con el Excel cerrado.
- La rampa de arranque seguro vuelve en la primera toma de cada sesión. Queda registrada (`decisiones_previas`) y el análisis tiene una sensibilidad sin esas tomas.

**Comandos del libro.** Todos exigen un motivo escrito, que queda en el libro:

| comando | cuándo |
|---|---|
| `--corregir-campana "motivo"` | hubo que cambiar un archivo congelado a mitad de campaña (p. ej. arreglar un error menor). Sin esto, el libro se niega a abrir la sesión siguiente. Deja el sha256 nuevo y la lista de lo que cambió. Entre sesiones, nunca con una abierta. |
| `--cerrar-campana "motivo"` | cualquier otro cierre: al terminar (meta, tope, fin del tiempo disponible, con MÍNIMO o INCOMPLETA) o anticipado (robot dañado, falla del laboratorio, sin más turnos). El cierre por el criterio de seguridad no necesita comando: lo hace el libro. Nunca con una sesión abierta. Marca las reservas sin resultado. Cerrada, no se abre más. |
| `--liberar-candado "motivo"` | una sesión murió sin cerrarse (corte de luz, ventana cerrada) y el libro quedó con candado. Marca sus reservas sin resultado como interrumpidas. Si no había candado, lo dice y no anota nada. **Nunca con la sesión viva:** si se libera igual, esa sesión ya no puede anotar. |

Los tres se usan así: `python demo_obstaculo_movil.py --modo L2 --robot-obstaculo 4 --campana L2_obstaculo_2 --corregir-campana "…"`.

**Qué bloquea y qué no:**
- **Bloquea** (sha256 en `campana.json` y en la fila de creación del libro; editar `campana.json` a mano también se detecta):
  - el código que carga una sesión: `adaptadores_robotat.py`, `calibracion_sesion.py`, `campana_obstaculo.py`, `colocacion_autonoma.py`, `colocacion_con_obstaculo.py`, `coordinador_enjambre.py`, `demo_obstaculo_movil.py`, `interfaces.py`, `lanzar_robotat.py`, `lib/__init__.py`, `lib/concentration_dynamics.py`, `lib/filtro_cbf.py`, `lib/swarm_env_skeleton.py`, `protocolo.py`, `protocolo_robotat.py`, `retroceso_congelamiento.py` y `sesion_robotat.py`;
  - el modelo de la política: `modelos/modelo_sanidad.zip`;
  - el plan, el script de análisis y el verificador independiente: `PLAN_ANALISIS_campana_L2.md`, `analizar_campana_l2.py` y `verificar_campana_l2.py`;
  - **todo `config_robotat.py` salvo la configuración del día** (huella `config_robotat.py#sin_calibracion`): la rampa (`DECISIONES_ARRANQUE`, `ARRANQUE_SEGURO`, `FACTOR_VELOCIDAD_ARRANQUE`), `RPM_MAX`, `ANTIGUEDAD_MAX_POSE_S`, la consulta de poses, `MAPEO_AGENTES`, la arena, las IP y las funciones. Los comentarios no cuentan.
- **No bloquea: la configuración del día** (decisión de José: offsets y calibración). Son, de `config_robotat.py`, sólo la tabla de offsets de rumbo (`OFFSETS_RUMBO_POR_ROBOT`, `OFFSETS_RUMBO_MEDIDOS`, `ORIGEN_OFFSET_RUMBO`), el marco y la escala del mocap (`ESCALA_POSICION`, `ROTACION_MARCO_RAD`, `TRASLACION_X_M`, `TRASLACION_Y_M`, `OFFSET_HEADING_RAD`) y sus banderas de verificación; y `calibracion_medida.json` entero. Se registra en el libro en cada apertura, con la calibración ya aplicada: los offsets efectivos de los seis robots, el marco y las banderas. El análisis declara la de cada sesión.
- **Durante la campaña, de `config_robotat.py` sólo se tocan los offsets.** Cualquier otro cambio bloquea la sesión siguiente hasta un `--corregir-campana "motivo"`. Si se cambia el offset del 4, hay que repetir la L0.
- **La calibración del mocap del día se hace con el robot 1**, o, si se hace con otro, se restaura `calibracion_medida.json` después (como el 22-09). Ese JSON pone al correr su robot como agente 0, con su offset. Con otro robot, la L0 o la colocación frenan la sesión, y si una toma corriera igual, el análisis la detiene por régimen: no contamina datos, pero cuesta el turno.

**Salidas:**
- el libro: `resultados_demo_obstaculo/campanas/L2_obstaculo_2/` (`campana.json` y `libro.csv`, que sólo crece);
- los CSV de cada sesión, como siempre, con el registro completo de cada toma corrida: poses iniciales medidas, robots y offsets de los agentes y del 4, pose medida del 4, `rpm_aborto`, `tau_prediccion_s`, `decisiones_previas` y un `id_sesion` común a los tres CSV.

**Réplica y cierres.** La réplica ya está escrita y probada con los ensayos del 07-10. Corre siempre con la máquina libre y nunca en paralelo con una sesión de hardware. En este orden:

1. **Antes del laboratorio, el cierre (a3)** (regla aprobada por José el 10-10):

   ```text
   python replica_con_obstaculo.py --episodios-3009 --salida resultados_demo_obstaculo/replica_campana/cierre_a3_AAAAMMDD
   python replica_con_obstaculo.py --evaluar-a3 resultados_demo_obstaculo/replica_campana/cierre_a3_AAAAMMDD
   ```

   - Si la primera sale con código 3, se completa con el mismo comando y `--reanudar` (falta la pasada normal) o `--suplementaria` (un episodio con 0 válidas).
   - La evaluación sale con 0 (PASA), 1 (NO PASA) o 3 (incompleta, sin veredicto). Escribe `cierre_a3_<fecha_hora>.json` sin pisar los anteriores.
   - **Si no pasa, se investiga antes de correr la réplica de la campaña, sin cambiar el margen (±0.00827).**
   - **Hecho el 10-10: NO PASA** (`cierre_a3_20261010_b`). José decidió seguir con la réplica de la campaña, con la investigación como respaldo. No se repite el a3 ni se cambia el margen (plan §7).
2. **Después de cerrar la campaña, la réplica de sus tomas, con la PC limpia: sin Chrome, ChatGPT, Omen ni el servidor de Inventor** (José, 10-10): `python replica_con_obstaculo.py --campana L2_obstaculo_2`. Si sale con 3, el mismo comando con `--reanudar` o `--suplementaria`, hasta que salga con 0 ("completa"). Con la campaña abierta se niega; cada corrida anota su hora de inicio y el análisis rechaza las anteriores al cierre.
   - **Antes de cada lanzamiento** (también con `--reanudar` o `--suplementaria`), el chequeo previo de la PC (al principio del protocolo) en `CHEQUEO OK`, con su salida en la bitácora.
3. **El análisis fijado:** `python analizar_campana_l2.py --campana L2_obstaculo_2`.
4. **El verificador independiente:** `python verificar_campana_l2.py <carpeta del análisis>`. Si el paquete se movió, con `--base`, `--dir-hw`, `--dir-replica` y `--dir-3009`.
5. **El reporte**, con el zip de datos crudos y `verificar_cifras`. Declara el a3 NO PASA con su diagnóstico y su IC95 como salvedad de la comparación con el 30-09, y trae los descriptivos post hoc del plan §7, rotulados así. El zip lleva también `cierre_a3_20261010_b/` completo, con `diagnostico_20261010/`. Declara, según los chequeos de la bitácora, que las sesiones y la réplica corrieron con `CHEQUEO OK` (enchufada, con el modo de referencia y la PC limpia), o cuáles no.
