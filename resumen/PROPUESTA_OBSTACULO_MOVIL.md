> Propuesta generada el 2026-10-01 a partir del código (solo lectura) por 4 exploradores, 3 diseños independientes y un revisor.
> Verifiqué a mano contra el código: barrera robot-robot `h = 0.5·(dist − d_robots)` sin velocidad del vecino (`coordinador_enjambre.py:1106–1117`);
> factor aplicado después del filtro (`adaptadores_robotat.py:993–997`); retroceso sin CBF (`:985–991`); `detener_todo` sólo `range(self._n)` (`:1125`);
> la fuente sólo lee marcadores de agentes (`:221`, `:512`); offsets de tabla de los robots 4 y 7 (`config_robotat.py`); arranque a 0.05 m/s = 848.6 ms y 1 de 5 sin moverse (memoria).
> Las distancias del modelo 1D son de centro a centro; "contacto" significa bajo 0.15 m, el umbral de colisión de la tesis (dos 3pi se tocan físicamente a ~0.10 m).

# 6.º Pololu como obstáculo móvil: recomendación

[V] código · [C] cálculo 1D (reproducido) · [M] memoria. Las rutas son relativas a `controllers/coordinador_enjambre/`. Modelo: `PROPUESTA_obstaculo_movil_modelo_1d.py` (en esta misma carpeta).

## 1. Respuesta directa

**Sí se puede.** Una demo que se vea en físico cuesta unas 3 jornadas de PC y 1 sesión de laboratorio. Pero no alcanza con sumarlo como "un robot más", por dos razones:

- **La barrera actual no sirve [V].**
  - La barrera robot-robot reparte la responsabilidad 50/50 y trata al vecino como quieto (`coordinador_enjambre.py:1106,1117`).
  - El factor 0.40 se aplica después del filtro (`adaptadores_robotat.py:993-997`), y ese escalado solo es seguro con h ≥ 0 (`:929-935`).
  - Resultado: a 0.05 m/s hay contacto [C].
- **La pila no conoce entidades que no sean agentes [V].**
  - La fuente solo lee los marcadores de `MAPEO_AGENTES` (`adaptadores_robotat.py:221,512-532`).
  - `detener_todo` solo frena `range(self._n)` (`:1125`).
  - Un enlace caído en el índice 5 da `KeyError` (`sesion_robotat.py:2816`).

**Qué cambia en la pila:**
- una fila de barrera estilo Exp O (`correr_experimento_O.py:181-196`) con la velocidad del obstáculo dividida por k;
- la misma normal en el escape;
- el marcador 7, fuera del caché de agentes;
- el robot 7 en el canal;
- un supervisor que lo mueve, lo frena y aborta.

`lib/` y `coordinador_enjambre.py` no se tocan. La política sigue sin ver el obstáculo (`coordinador_enjambre.py:1302-1304`).

## 2. Plan

**Fase 0: en la PC (2–3 jornadas)**
1. Respaldo con sha256 y la batería de pruebas como base (198 OK [M]).
2. Un archivo nuevo, `demo_obstaculo_movil.py`, con subclases de la fuente, el canal y el coordinador. No edita archivos existentes, así que los 50 válidos quedan protegidos.
3. Pruebas en `SimuladorRobotat` con 6 robots y retardo de 0.45 s (`simulador_robotat.py:105,179`). Tienen que comprobar:
   - una sola consulta por decisión;
   - que `detener_todo` frena al 7;
   - que congelar el marcador 7 (`:99`) aborta la toma;
   - que con v=0 la fila coincide con la del Exp O;
   - que el 7 queda quieto durante la rampa;
   - 0 contactos en 10 tomas.
4. El simulador no modela la fricción de arranque (`:17`). El arranque del 7 solo se puede validar en el laboratorio.

**Fase 1: laboratorio (~1.5 h)**
- **L0.** El 7 solo: marcador vivo, patada de arranque 10 de 10 y error radial < 5 cm.
- **L1.** El 7 apagado, 2–3 tomas. Es el Exp O en físico.
- **L2.** El 7 en movimiento, n=5, factor 0.40, hasta 3 tomas válidas en ≤ 6 intentos. Video cenital y una persona junto a la arena.

**Fase 2: citable, opcional (+6–8 jornadas)**
- Exp Q en Python:
  - retardo de 0.5 s y k = 0.4;
  - formulaciones F0, F1 y F50 a 0.03–0.10 m/s;
  - 100 semillas, anclado al Exp O;
  - criterio de ir al laboratorio preregistrado.
- Después, 3×10 episodios y una réplica que reproduzca la trayectoria medida del 7.

## 3. Parámetros

| | Valor | Justificación |
|---|---|---|
| Robot | 7 (o el 4) | Tiene offset en la tabla (`config_robotat.py:276`). El 2, el 3 y el 10 tienen fallas (`:166-197`). |
| Trayectoria | Círculo antihorario, R = 0.60, centrado en env (1.5, 1.5) | Queda a 0.90 m de las paredes. El punto de mira tiene un corredor de 0.39 m, así que no queda encerrado contra la pared. Está a 0.65 m de la zona ciega A [M]. Da unos 3–4 encuentros por episodio [C]. |
| Velocidad | 0.05 m/s, con patada de 0.08 m/s durante ≤ 1 s | A 0.05 m/s el 3pi tardó 849 ms en arrancar y falló 1 de 5 veces [M]. La patada usa `V_COL` (`colocacion_autonoma.py:75`). El escape ejecuta 0.062 m/s (`coordinador_enjambre.py:326` × 0.40). |
| Barrera | D_o = 0.33 (r_eff 0.15 + 0.18). Lado derecho = −α·h + s/k, saturado al 90 % de la capacidad, con s = max(0, n·v̂, n·v_cmd) y k = `factor_total()`. Entra como `h = −rhs/α` (`filtro_cbf.py:308-309`). | Distancia mínima entre centros: 0.27 m (τ 0.45) y 0.22 m (τ 0.85), contra contacto a 0.15 m [C]. Absorbe los ~3.5 cm que pierde el hardware [M]. |
| Quieto | Mientras `factor_arranque() < 1` | Con k = 0.10 (`config_robotat.py:473-474`), s/k > V_MAX. |
| Freno propio | Agente a < 0.20 m por delante, o agente en retroceso a < 0.60 m | En el modelo no se dispara: si actúa en el laboratorio, es una señal. |

## 4. Riesgos

- **Marcador del 7 congelado.** El CBF esquivaría una pose fantasma [M]. Mitigación: frenar y abortar a la primera fila repetida.
- **Encierro.** Si el QP es infactible, el respaldo es (0,0) (`filtro_cbf.py:338-346`). Mitigación: fila saturada, corredor libre y freno propio.
- **El retroceso no pasa por el CBF** (`adaptadores_robotat.py:985-991`). Mitigación: el obstáculo frena.
- **`detener_todo` no es una parada de emergencia** (`adaptadores_robotat.py:1096-1105`). Mitigación: frenar primero al 7, y que la persona junto a la arena lo levante.
- **Calibración.** La etapa 0 con `--robot 7` reemplaza `MAPEO_AGENTES[0]` (`calibracion_sesion.py:333-337`) y la 3 pisa un offset (`:352-357`). No correrlas con el 7.
- **Mando del 7.** Usar `_enviar_crudo`. `enviar_acciones` cuenta decisiones (`adaptadores_robotat.py:965`) y `enviar_directo` contamina `rpm_pico` (`:1092`).
- **El 7 es prestado** y nunca se probó.

## 5. Encuadre

**Se puede afirmar:** "la capa de seguridad, extendida con un término de velocidad, mantuvo la separación frente a un 3pi no cooperativo a 0.05 m/s en N tomas, sin que la política lo observe". Es una extensión dinámica del Exp O.

**No se puede afirmar:**
- que la política se adapta;
- una garantía formal;
- "nunca choca": con 0/30 la cota sigue en ~10–12 % por episodio [C];
- nada sobre otras velocidades u otros obstáculos;
- que funciona con la capa del 30-09 sin cambios;
- nada sobre la cobertura frente a los 50 válidos;
- que la capa sola bastó, en las tomas en que actuó el freno.

## 6. Correcciones a los diseños

- **expO:** "u = 0 es infactible si h < 2.5 cm" omite k. Con k = 0.40 el umbral es 6.25 cm.
- **riguroso:** con D_o = 0.255, su propia tabla da 14.8 cm a τ 0.85, o sea contacto.
- **demo:** abortar vía `_avanzar` deja como motivo "el entorno pidió terminar" (`sesion_robotat.py:2794`).
- **Contadores:** la fila del obstáculo se contaría como "pared" (`coordinador_enjambre.py:1342-1345`).
- **cbf:** la llamada a `_decidir_y_actuar()` dentro de `_correr_episodio` es `sesion_robotat.py:2802`, no la 3222.

## 7. Decisiones de Jose

1. **Alcance:** demo / demo + Exp Q / versión citable.
2. **Robot:** el 7 o el 4. Si no hay ninguno, un obstáculo virtual: no tiene riesgo, pero no se ve.
3. **Código:** archivo aparte / integrado con flags (la réplica pareada lo necesita).
4. **L1 estático:** hacerlo / saltarlo.
5. **Freno:** cuenta como falla / solo se reporta.
