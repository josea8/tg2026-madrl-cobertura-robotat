# Demostración final en el Robotat: dos modos y panel en otro proceso (23-10)

**Demostración, no citable.** Nada de este reporte entra en el documento: es la herramienta para grabar el video, armar el póster y correr la demo en vivo frente al jurado. La campaña `L2_obstaculo_2` sigue ABIERTA y no se tocó.

**Datos crudos:** `REPORTE_2026-10-23_demo_final_datos.zip`. El script `scripts/verificar_cifras_demo_final.py` recalcula desde los CSV y los JSON cada cifra de este reporte y comprueba que el texto la diga igual (§6).

---

## 1. Resumen

1. **Está lista para usarse** en sus dos modos, con el simulador para ensayar en casa:
   - `objetivos`: la configuración de la evaluación del 30-09;
   - `mejorada`: lo mismo con el robot 4 como obstáculo móvil (L2, F2, τ_c 0.65 s), sin campaña.
2. **No toca nada congelado.** Los 22 archivos dan "IGUAL a lo probado" antes y después, y el verificador por AST confirma que el código nuevo sólo orquesta.
3. **Las 13 pruebas funcionales pasan**, incluida la de decidir bit a bit igual que el coordinador congelado, en los dos modos.
4. **Publicar no cuesta nada medible** sobre el lazo.
5. **Un panel con ventana en la misma laptop suma ~4.7 ms al ciclo p95** (umbral 2 ms). El diagnóstico muestra que lo causa **cualquier proceso con un bucle de eventos Tk**, aunque esté minimizado y no dibuje nada del panel. No es el dibujo, ni matplotlib, ni recibir datos. **Recomendación: el panel en otra laptop de la misma red.**
6. **La laptop del lazo tiene que estar enchufada.** A batería, el ciclo se cuadruplica.

## 2. Cómo se usa el día de la demo

En la laptop del lazo (enchufada, "Mejor rendimiento", sin Chrome ni otras apps), desde `controllers/coordinador_enjambre/`:

```text
python demo_final.py --modo objetivos --episodios 3 --gui <IP de la otra laptop>:27300
python demo_final.py --modo mejorada --robot-obstaculo 4 --episodios 3 --gui <IP>:27300
```

En la otra laptop (la del proyector):

```text
python panel_demo.py --puerto 27300
```

- Entre episodios la consola espera Enter: Enter sigue, "t" termina. `--hora-fin HH:MM` cierra la sesión a esa hora.
- `--gui` se puede repetir (panel, otra laptop, el espejo de Webots si se hace la fase 2).
- Antes de `mejorada`, la L0 del 4 del día (`demo_obstaculo_movil.py --modo L0 --robot-obstaculo 4`). Sin L0 OK no arranca (código 6) y no hay `--forzar`.
- Para ensayar en casa: agregar `--simulador`.

El panel muestra:
- **el mapa:** la arena con la banda de 0.18 m, la rejilla de AoI de fondo, los objetivos, y los agentes con rumbo, estela y color según su estado; en `mejorada`, el 4 con su anillo de 0.33 m;
- **las cifras grandes:** cobertura AoI (rejilla completa), intervención del filtro, escapes, retrocesos, pares < 0.15 m, distancia a la pared y al obstáculo;
- **el ritmo del lazo:** el ciclo p95 y la latencia de poses;
- **el seguimiento:** la gráfica de cobertura, el último evento y la tarjeta de resumen de cada episodio;
- **la hora de pared con décimas**, para sincronizar con la cámara.

## 3. Qué se construyó

- **`demo_final.py`** orquesta los dos modos. Copia literal lo que no se puede importar:
  - de `sesion_robotat.py`: 1991-2000, 2013-2034 y 2062-2235;
  - de `demo_obstaculo_movil.py`: 2653-2663 y 2692-2909.

  Las cinco copias son idénticas a su fuente salvo una línea marcada `[demo]`: con `--colocacion actual` no se pide reposicionar.
- **El coordinador** es una subclase que publica después de `super()._decidir_y_actuar()`. Los cinco robots ya recibieron su orden cuando se publica.
- **`publicador_estado.py`** manda por UDP, una vez por decisión. Nunca lanza: tras 20 errores seguidos se apaga y avisa una vez. Serializa y envía en un hilo propio, mientras el lazo duerme.
- **`panel_demo.py`** corre en un proceso aparte, con prioridad baja. Si se cae, la sesión sigue.
- Sus salidas van a `resultados_demo_final/`, nunca a la carpeta de la campaña.

## 4. Pruebas (simulador)

**Pruebas 1 a 6, funcionales.** Corrieron a batería: valen por lo que comprueban, pero sus tiempos no se citan.

- **1, `objetivos` (2 × 100):** 2/2 episodios válidos, con cobertura 0.1499 y 0.1843. El CSV de episodios tiene las 106 columnas de la etapa 7 del 30-09 en el mismo orden, y el de decisiones, las 14.
- **2, `mejorada` (2 × 100, el 4 en el simulador):**
  - 2/2 tomas válidas y 2/2 para el video, con 0 frenos de respaldo.
  - El agente más cercano al 4 quedó a 0.571 m.
  - El 4 recorrió el 83 % y el 91 % de lo comandado.
  - Los tres CSV tienen las columnas de `sesion_demo` (las del ensayo 1e del 17-10 menos las cuatro que sólo existen con campaña).
- **3, publicación:** un mensaje por decisión más inicio y fin de cada episodio, sin huecos en la secuencia y ninguno de más de 60 KB. La cobertura en vivo coincide con la del CSV.
- **4, fallas inyectadas:** puerto cerrado, excepción al serializar, excepción al armar el mensaje y destino inválido. En todos los casos el episodio terminó válido y la consola avisó una sola vez. Además, el hilo de envío conserva el orden y una ráfaga no lo apaga.
- **5, bit a bit:** los coordinadores de la demo deciden igual que los congelados, con la publicación encendida y apagada, ante las observaciones de un episodio del 30-09. Con obstáculo hubo que fijar el reloj dentro de la prueba: la F2 y el supervisor leen `perf_counter`, y sin eso ni el congelado es igual a sí mismo entre dos corridas.
- **6:** con `--simulador`, la calibración queda en identidad aunque exista `calibracion_medida.json`.

**Prueba 7, costo sobre el lazo.** Intercalada: 4 rondas; en cada una, 1 episodio × 300 decisiones por condición, con el orden rotado ronda a ronda. Enchufada, con Chrome y ChatGPT cerrados (quedó abierta la app de Claude, ~0.4 núcleo).

| condición | ciclo p95 medio |
|---|---|
| sin GUI | 7.80 ms |
| publica, sin panel | 7.75 ms |
| panel abierto, 10 Hz | 12.51 ms |

- Diferencia pareada, panel − sin GUI: +4.71 ms (de +4.02 a +5.13 en las 4 rondas). **No pasa** el umbral de +2 ms.
- Diferencia pareada, publica − sin GUI: -0.05 ms. Publicar no cuesta nada.
- Las corridas anteriores de esta prueba están en `_superadas/`, cada una con su motivo:
  - una corrió a batería;
  - otra, con Chrome abierto, dio un +0.30 ms que era ruido;
  - las otras dos son del panel antes de la corrección del §5.

## 5. De dónde salen los ~4.7 ms

**Primero se corrigió el panel, aunque no era la causa.**
- `plt.pause()` redibujaba la figura entera en cada cuadro, además del dibujo con blitting.
- La rejilla de AoI se redibujaba aunque no hubiera cambiado.
- La baja de prioridad del proceso nunca había funcionado: faltaban las firmas de `ctypes`.
- Con las tres cosas corregidas, el panel pasó de ocupar un núcleo entero (0.97) a 0.22. **El costo sobre el lazo no cambió** (la prueba 7 de arriba ya es con el panel corregido).

**Después se separaron los ingredientes**, intercalados y pareados contra "sin GUI" (`diagnostico_panel_20261023/`):

| condición | − sin GUI |
|---|---|
| panel con ventana, recibiendo | +3.92 ms |
| panel con ventana, **sin datos** | +3.74 ms |
| panel **sin ventana**, recibiendo y dibujando | +0.04 ms |
| proceso que sólo pide un temporizador de 1 ms | -0.86 ms |
| ventana Tk mínima (sólo un reloj), visible | +4.19 ms |
| la misma, **minimizada** | +3.99 ms |

- **No es** recibir ni dibujar, ni matplotlib, ni que la ventana esté visible o en primer plano, ni el temporizador.
- **Es** que haya un proceso con un bucle de eventos Tk corriendo en la misma máquina. El mecanismo dentro de Windows no se aisló.

**Hay dos límites para tenerlos presentes:**
- Se midió en el **simulador**, donde el proceso del lazo también tiene los hilos del simulador. En el Robotat el lazo es otro y el efecto podría ser distinto; con el panel en otra laptop no importa.
- Aun con el panel en la misma laptop, el lazo queda en ~12.5 ms de los 100: cumple con holgura el periodo, pero no el criterio de +2 ms que fija el plan.

## 6. Verificación

- `comparar_ast_demo_final.py`: "SÓLO ORQUESTAN: NADA REDEFINIDO NI PARCHEADO; COPIAS IDÉNTICAS SALVO LO MARCADO [demo]".
- Chequeo de congelados del protocolo: "IGUAL a lo probado". `manifiesto_sha256_demo_final.txt` registra los 22 archivos antes y después de cada paso, todos idénticos.
- `verificar_cifras_demo_final.py`: todas las cifras de este reporte (la salida va en el zip).

## 7. Pendiente

- Ensayar en casa con el panel en la segunda laptop, tres veces de corrido, y mirar el ciclo p95 en el panel.
- La fase 2 (espejo en Webots), sólo con OK de José. Webots también es una app con ventana: antes de usarlo en la misma laptop, medirlo como al panel.
