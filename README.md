# Manejo de cobertura con enjambres de robots mediante aprendizaje por refuerzo multi-agente

Repositorio del trabajo de graduación *Evaluación e implementación de algoritmos de aprendizaje de refuerzo profundo para aplicaciones de robótica de enjambre* (Ingeniería Mecatrónica, Universidad del Valle de Guatemala, 2026), de José Eduardo Velasquez Ardón.

El trabajo entrena con PPO una política para cinco agentes, con entrenamiento centralizado y ejecución descentralizada, y la compara con estrategias de referencia sin aprendizaje. Después la transfiere a un simulador con dinámica de contacto (Webots) y a robots Pololu 3pi+ en la plataforma Robotat. La métrica principal es la cobertura basada en la edad de la información (AoI).

Aquí están el código, los reportes de cada experimento y los datos crudos que respaldan las cifras de la tesis, incluidas las secciones que no cupieron en los anexos.

## Estructura

| Carpeta | Contenido |
|---|---|
| `codigo/` | Código fuente. `fase_preeliminar/` y `fase_preliminar2/` tienen el entorno, el entrenamiento, la sintonización y las evaluaciones en simulación cinemática. `primerafase_webots/` tiene los mundos y controladores de Webots, el coordinador del enjambre para el Robotat y los scripts de cada experimento (`experimentos/exp*`). |
| `resumen/` | Reportes de cada campaña y experimento (`REPORTE_*.md`), protocolos, planes de análisis, prerregistros, propuestas, la bitácora técnica (`primerafase_webots/BITACORA_TECNICA.md`), el informe de calibración y los resúmenes de análisis. Es el punto de partida para revisar una cifra. |
| `material_complementario/` | Las secciones que salieron de los anexos de la tesis por el límite de extensión (aceleración con GPU, robustez ante pose degradada, generalización a otro número de agentes, variantes de reentrenamiento, verificación del cliente, peso de penalización, material del capítulo de transferencia, perfil radial y análisis de asociación de hiperparámetros). `material_complementario.pdf` es el documento listo para leer y `fuente/` tiene el LaTeX y las figuras. |
| `figuras_tesis/` | Las figuras de resultados de la tesis, generadas con `codigo/figuras_tesis/regenerar_figuras_tesis.py` a partir de los datos guardados. |
| `datos_crudos/` | Resultados sin procesar: episodios, trazas, tomas de la plataforma, réplicas en simulación, modelos entrenados y estudios de Optuna, empaquetados en archivos zip. |

Las rutas dentro de `codigo/`, `resumen/` y de los zip de `datos_crudos/` conservan la estructura original del proyecto. Por eso un script de `codigo/` encuentra sus datos si se descomprimen los zip en la misma carpeta raíz.

## Material complementario

`material_complementario/material_complementario.pdf` reúne, sin cambios en el texto, los cuadros ni las figuras, las secciones de los anexos que la tesis remite a este repositorio. Sus secciones, cuadros y figuras van numerados con la letra C (C.1, C.2, ...). Las referencias sin la letra C apuntan a la tesis, en su versión del 17 de noviembre de 2026. En este documento la cobertura está como fracción entre 0 y 1, no en porcentaje. La única corrección respecto de los anexos está en el análisis de asociación entre hiperparámetros y desempeño, que ahora excluye la prueba 2 del estudio J (repetía la configuración de la prueba 0) y usa 27 semillas a paso fijo en lugar de 29.

Para recompilarlo hay que correr `pdflatex material_complementario.tex` dos veces dentro de `fuente/`. El archivo `numeracion_tesis.aux` trae la numeración de la tesis para resolver esas referencias.

## Datos crudos

Los datos están en zip de menos de 100 MB, que es el límite de GitHub por archivo. Cada zip es independiente y se abre con cualquier descompresor. `datos_crudos/LISTA.md` indica qué contiene cada uno.

Los paquetes de datos de los reportes (`REPORTE_*_datos.zip`, en `datos_crudos/paquetes_de_reportes/`) van tal como se generaron. El del 2 de octubre pesa más de 100 MB y está partido en piezas que hay que unir antes de abrirlo:

```bash
cat REPORTE_2026-10-02_obstaculo_fase0_datos.zip.parte* > REPORTE_2026-10-02_obstaculo_fase0_datos.zip
```

En Windows:

```bat
copy /b REPORTE_2026-10-02_obstaculo_fase0_datos.zip.parte01 + REPORTE_2026-10-02_obstaculo_fase0_datos.zip.parte02 + REPORTE_2026-10-02_obstaculo_fase0_datos.zip.parte03 REPORTE_2026-10-02_obstaculo_fase0_datos.zip
```

## Qué no incluye

- Los modelos 3D del Pololu 3pi+, que son del laboratorio.
- Las versiones de respaldo de los documentos de trabajo.
- Las credenciales o accesos a la red del laboratorio. Las direcciones IP que aparecen en el código y en los reportes son de la red privada del Robotat y no son accesibles desde fuera.

## Reproducir

Las versiones de las bibliotecas de la fase de entrenamiento están en `codigo/fase_preliminar2/requisitos_congelados_2026-09-09.txt`. Cada carpeta `codigo/primerafase_webots/experimentos/exp*` tiene sus scripts de corrida y análisis, y su prerregistro o reporte está en la carpeta equivalente de `resumen/`.

## Licencia

El código de `codigo/` está bajo la licencia MIT (`LICENSE`). Los reportes, los datos, las figuras y el material complementario están bajo CC BY 4.0 (`LICENSE-datos-y-documentos.md`), así que se pueden reutilizar citando la autoría.
