"""
correr_experimento_R.py
=======================
EXPERIMENTO R — réplica PRERREGISTRADA de las hipótesis del exploratorio de
S2 y S3 del Exp Q, con semillas de episodio nuevas (420110–420509, n = 400)
en S1, S2 y S3 × {din, quieto, ctrl, sinvel}, SIN regla de parada. El
prerregistro es `PREREGISTRO_R.md`: su sha256 va a cada registro, al
manifiesto pre y a la bitácora. R no cambia el veredicto del Exp Q.

Qué no cambia
-------------
Todo lo que decide la dinámica y las 67 columnas es el código del Exp Q con
su huella (e265b6cd…4a29): entorno, filtro, fila F1, escape, política y las
copias de lib/ y de O. R IMPORTA Y LLAMA; no redefine ni parchea nada.
`comparar_ast_R.py` certifica el cuerpo de `correr_episodio_R` y la identidad
de sus nombres libres; la orquestación (`_tarea_R`, `correr_condiciones_R`)
la cubren la revisión y el control, éste sólo en 420000–420099.

Lo único nuevo: el registro por paso (Parte B)
----------------------------------------------
`correr_episodio_R` es una COPIA TEXTUAL de `correr_episodio_Q`
(`correr_experimento_Q.py:317-534`) con líneas agregadas, cada una marcada
`# [R]`, que sólo GUARDAN, en cada iteración t (t = 0…499) y para cada agente
k: la bandera de fallback de la decisión t, si la acción venía del escape, si
el filtro intervino, la distancia centro→superficie al obstáculo más cercano
medida DESPUÉS del `env.step` de esa misma iteración (la consecuencia de la
decisión t), la posición antes y después del paso y el contador de contactos.
Las columnas derivadas (§3.2 del prerregistro) las calcula después, fuera
del episodio, la función pura `columnas_derivadas`; los autochequeos de la
captura (§3.3), `autochequeos_R`, contra los contadores del propio Q.

Por qué no `import *`
---------------------
`correr_experimento_Q` no define `__all__`: un `import *` traería sus 109
nombres públicos, entre ellos rutas y funciones que escriben en la carpeta
del Exp Q. La copia necesita sólo los 37 nombres libres de su cuerpo, más un
`_MODELO` propio: se importan explícitamente desde `correr_experimento_Q`, así
que son los MISMOS objetos que resuelve `correr_episodio_Q`.
`comparar_ast_R.py` exige que ese conjunto sea exactamente el de los nombres
libres del AST de Q y que cada uno sea el mismo objeto (`is`).

Uso (siempre con -B: sin -B, importar el Exp Q escribiría __pycache__ en su
carpeta, y el módulo se niega a cargar)
---
    python -B correr_experimento_R.py arbol         referencia del árbol del Exp Q
    python -B correr_experimento_R.py control       1200 episodios vistos, bit a bit
    python -B correr_experimento_R.py pasabilidad   400 semillas × S1–S3
    python -B correr_experimento_R.py manifiesto    manifiesto pre (antes de experimento)
    python -B correr_experimento_R.py experimento   12 celdas × 400 semillas
    python -B correr_experimento_R.py experimento --sin-parte-b   (sólo §7)

Cada invocación escribe su propio log, con sello, en resultados/.

Autor: José — Tesis Mecatrónica UVG.
"""

from __future__ import annotations

import csv
import ctypes
import hashlib
import os
import platform
import re
import subprocess
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Sequence

if not sys.flags.dont_write_bytecode:
    raise SystemExit("PARAR: correr con python -B (sin -B, importar el Exp Q escribiría "
                     "__pycache__ en su carpeta).")

_CARPETA_R: Path = Path(__file__).resolve().parent
_CARPETA_Q: Path = (_CARPETA_R.parent / "expQ_obstaculos_moviles").resolve()
if str(_CARPETA_Q) not in sys.path:
    sys.path.insert(0, str(_CARPETA_Q))

import correr_experimento_Q as Q
# Los 37 nombres libres del cuerpo de `correr_episodio_Q` (AST): los MISMOS
# objetos que resuelve la función original, tomados del espacio de nombres de Q.
from correr_experimento_Q import (ALFA_CBF, ANCHO_PERIFERIA, ARENA, COMM_RADIUS,
                                  COTA_CENTRO_OBST, CondicionQ, D_SEGURA, Dict,
                                  ELE_A, ESC_UMBRAL_ACTIVA, EntornoObstaculosMoviles,
                                  GestorEscapeMovil, List, MARGEN_CBF_M, MAX_STEPS,
                                  N_AGENTES, OMEGA_MAX, PESOS_TRIAL13, RADIO_CHASIS,
                                  RUTA_MODELO, SEED_BASE, TOL_LIGANTE, Tuple, V_MAX,
                                  W_OMEGA, armar_condicion, barreras_robot_robot,
                                  combinations, distancia_minima, filas_obstaculo_f1,
                                  mascara_ocupada, mascara_permanente, np,
                                  obstaculos_en, time, tipo_barrera, warnings)
# Utilidades de Q y de O que R usa tal cual (no escriben nada).
from correr_experimento_Q import _leer_csv, _pasabilidad_semilla, _serial
from correr_experimento_O import CRITERIOS_FALLA, _inicializar_trabajador

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

#: La huella del código del Exp Q con que corrieron S1 y el exploratorio.
HUELLA_Q_ESPERADA: str = "e265b6cd31e8d443977027b1bf1d4671c002b06c3ecbdc45a275521e49c24a29"
ENCABEZADO_R: str = ("PRERREGISTRADO — Exp R: réplica con semillas nuevas 420110–420509 de las "
                     "hipótesis del exploratorio de S2/S3 del Exp Q; sin regla de parada; no "
                     "cambia el veredicto del Exp Q.")

#: Semillas: SEED_BASE·10 000 + i, i = 110…509. 420100–420109 las usó la Fase 0
#: del obstáculo móvil (02-10); 420000–420099, el Exp O y el Exp Q.
SEMILLA_INICIO_R: int = 110
N_SEMILLAS_R: int = 400
NIVELES_R: Tuple[str, ...] = ("S1", "S2", "S3")
PREFIJO_CONTROL_R: str = "controlR"
PREFIJO_EXP_R: str = "R"

#: Parte B (§3.2 del prerregistro). Ventana de W decisiones: t−W+1 … t del
#: mismo agente, con W = 1/(α·dt) = 1/(2 · 0,1) = 5; 3 y 10 son sensibilidad
#: (W = 1 es `d_min_sin_fallback`).
W_VENTANA_R: int = 5
VENTANAS_R: Tuple[int, ...] = (3, 5, 10)
UMBRAL_H6_R: float = 0.10
#: El paso del mínimo es la PRIMERA (t, k) a menos de 1e-9 m de d_min: con
#: contactos, la proyección deja la distancia en 0,075 + 1e-9 con ruido de
#: 1e-16, y así cuenta el primer contacto y no el ruido.
TOL_EMPATE_R: float = 1e-9

DERIVADAS_R: Tuple[str, ...] = (
    "pasos_agente_fallback", "d_min_sin_fallback", "d_min_en_fallback",
    "d_min_fuera_ventana_3", "d_min_fuera_ventana_5", "d_min_fuera_ventana_10",
    "pasos_bajo_010", "pasos_bajo_010_fuera_ventana_5", "paso_d_min", "agente_d_min",
    "fallback_en_d_min", "racha_fallback_d_min", "fallback_ventana_d_min_5",
)
AUTOCHEQUEOS_R: Tuple[str, ...] = (
    "pasos_agente_intervino", "pasos_agente_escape_intervino", "contactos_registrados",
    "fb_desplazado", "xy_discontinuo", "fb_desplazado_corrido",
)
COLUMNAS_TRAZA_R: Tuple[str, ...] = (
    "paso", "agente", "fallback", "d_obst", "en_escape", "intervino",
    "x_antes", "y_antes", "x_despues", "y_despues", "contacto_nuevo",
)

RUTA_CODIGO_R: Path = _CARPETA_R / "correr_experimento_R.py"
RUTA_COMPARADOR_R: Path = _CARPETA_R / "comparar_ast_R.py"
RUTA_PREREG_R: Path = _CARPETA_R / "PREREGISTRO_R.md"
DIR_RES_R: Path = _CARPETA_R / "resultados"
DIR_PARCIALES_R: Path = DIR_RES_R / "parciales"
DIR_TRAZAS_R: Path = DIR_RES_R / "trazas"
RUTA_AST_R: Path = DIR_RES_R / "comparar_ast_R.txt"
RUTA_ARBOL_REF_R: Path = DIR_RES_R / "arbol_expQ_referencia_R.txt"
RUTA_CONTROL_CSV_R: Path = DIR_RES_R / "control_bit_a_bit_R.csv"
RUTA_CONTROL_TXT_R: Path = DIR_RES_R / "control_bit_a_bit_R.txt"
RUTA_PASAB_TXT_R: Path = DIR_RES_R / "pasabilidad_R.txt"
RUTA_CSV_R: Path = DIR_RES_R / "experimento_R_completo.csv"
RUTA_REG_R: Path = DIR_RES_R / "registro_R.txt"
#: Archivos que tienen que estar en el manifiesto pre.
REQUERIDOS_MANIFIESTO_R: Tuple[str, ...] = (
    "PREREGISTRO_R.md", "correr_experimento_R.py", "comparar_ast_R.py",
    "analizar_experimento_R.py", "verificar_cifras_R.py", "test_experimento_R.py",
    "potencia_R.py", "resultados/potencia_R.txt", "resultados/resumen_R_prueba_sobre_Q.txt",
    "resultados/resumen_R_prueba_sobre_control.txt",
)
#: El prerregistro está fijado si su línea «Fijado:» tiene fecha y hora.
RE_FIJADO_R = re.compile(r"^Fijado: \d{4}-\d{2}-\d{2} \d{2}:\d{2}")

#: Referencias del Exp Q, que R sólo lee.
RUTA_CSV_Q_S1: Path = _CARPETA_Q / "resultados" / "experimento_Q_completo.csv"
RUTA_CSV_EXPL_Q: Path = _CARPETA_Q / "resultados" / "experimento_Q_EXPLORATORIO_S2_S3.csv"
#: Los tres archivos de S1 y los tres crudos exploratorios (manifiestos del Exp Q).
SHA256_INTACTOS_R: Dict[str, str] = {
    "resultados/registro_Q.txt":
        "ff553e66d06420ff1f7abcabb9f03070885f96be8b8856850c3a5dd249d8673a",
    "resultados/experimento_Q_completo.csv":
        "341562959d02b113e1585590425bc4f51918cb3d4ff6e944f46dc616a08d5dbf",
    "resultados/resumen_experimento_Q.txt":
        "f5f69c4ea9b667d5e4e62b91e25fd1087f09320c7f15f04e529293eaff672a43",
    "resultados/experimento_Q_EXPLORATORIO_S2_S3.csv":
        "2f4ae0751220ef448cf07af7df9605cfad6bdeb496c72cbf28de3670940de8bd",
    "resultados/reproduccion_S1_din_EXPLORATORIO.csv":
        "8fc750cce3b0ea4d3dfbadecd2e75615f68fefa2cb418d79e64449c5248f3830",
    "resultados/registro_Q_EXPLORATORIO.txt":
        "3e34427dfacc6ac5dd2bd7ab6b315d3e305bb0cec77138660b27921c324b18c3",
}
MANIFIESTOS_Q_R: Tuple[str, ...] = ("resultados/manifiesto_sha256_Q.txt",
                                    "resultados/manifiesto_sha256_Q_EXPLORATORIO.txt")

#: Chequeo de congelados de la campaña: el comando de `PROTOCOLO_L0_L2.md:210`,
#: desde la carpeta del coordinador. Imprime la frase o la lista de distintos
#: y en los dos casos sale con 0: se aprueba por la salida.
DIR_COORD_R: Path = _CARPETA_R.parents[1] / "controllers" / "coordinador_enjambre"
CMD_CONGELADOS_R: str = (
    "import json,campana_obstaculo as C; p=json.load(open('resultados_demo_obstaculo/"
    "ensayo_campana_20261017_092424/campanas/ensayo/campana.json',encoding='utf-8'))"
    "['archivos_congelados']; h=C.hashes_congelados(); d=[k for k in h if h[k]!=p.get(k)]; "
    "print('IGUAL a lo probado' if not d else d)")
#: Procesos que no pueden estar corriendo al lanzar, por línea de comandos (el
#: servidor de Inventor es un python3.13.exe permanente y no cuenta): otra
#: corrida de O, Q o R, y cualquier script del coordinador (laboratorio,
#: réplica de la campaña); y por nombre, MATLAB y Webots.
RE_CORRIDAS_R = re.compile(r"correr_(experimento|exploratorio)_\w+\.py|coordinador_enjambre")
PROGRAMAS_R: Tuple[str, ...] = ("matlab", "webots")
REINTENTOS_ESCRITURA_R: int = 60

_MODELO = None


def correr_episodio_R(cond: CondicionQ, seed_ep: int) -> Dict[str, object]:
    """
    Un episodio determinista, por el camino nuevo. Sigue paso a paso
    `correr_episodio` del Exp O; lo nuevo son las posiciones de los
    obstáculos en cada decisión, la fila F1 y las métricas agregadas.
    Métricas SIN redondear; las columnas del Exp O conservan su nombre.
    """
    global _MODELO
    from lib.filtro_cbf import FiltroCBFParedes
    if _MODELO is None:
        from stable_baselines3 import PPO
        _MODELO = PPO.load(str(RUTA_MODELO), device="cpu")

    t0 = time.perf_counter()
    arm = armar_condicion(cond, seed_ep)
    env = EntornoObstaculosMoviles(
        trayectorias=arm.trayectorias, fisicos=arm.fisicos,
        obstaculos_rebote=arm.rebote,
        n_agents=N_AGENTES, arena_size=(ARENA, ARENA), max_steps=MAX_STEPS,
        comm_radius=COMM_RADIUS, reward_weights=PESOS_TRIAL13,
        domain_rand=False, seed=SEED_BASE, modo_borde="bloqueante",
    )
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        obs, _ = env.reset(seed=seed_ep)
    uso_fallback = int(any("grid fallback" in str(a.message) for a in avisos))
    agentes = list(obs.keys())
    n_a = len(agentes)
    xx, yy = env._field._grid_xx, env._field._grid_yy
    # Máscara propia (la de la métrica, como en el Exp O también en el
    # control) y las dos del nivel, para que cada comparación tenga el mismo
    # denominador en los dos lados (§3.6).
    mascara = mascara_permanente(arm.trayectorias, xx, yy, MAX_STEPS)
    mascara_din = mascara_permanente(arm.trayectorias_nivel, xx, yy, MAX_STEPS)
    mascara_arr = mascara_ocupada(xx, yy, obstaculos_en(arm.trayectorias_nivel, 0))
    if arm.fisicos and not np.array_equal(mascara, env._field.mascara):
        raise RuntimeError("la máscara del campo no es la permanente")

    filtro = FiltroCBFParedes(arena_size=(ARENA, ARENA), ele_a=ELE_A, alfa=ALFA_CBF,
                              d_segura=D_SEGURA, w_omega=W_OMEGA,
                              v_max=V_MAX, omega_max=OMEGA_MAX)
    gestor = GestorEscapeMovil(n_a, ARENA,
                               env.posiciones_actuales() if arm.fisicos else ())

    pares15, pares22 = set(), set()
    n_pasos = pasos_banda = pasos_periferia = 0
    d_min_pared = float("inf")
    d_min_obst = float("inf")
    violo_margen = [False] * n_a
    contacto_pared = [False] * n_a
    viol_cota_obst = [False] * n_a
    cont = {"interv": 0, "hmin_pared": 0, "hmin_robot": 0, "hmin_obst": 0,
            "lig_pared": 0, "lig_robot": 0, "lig_obst": 0, "lig_ninguna": 0,
            "lig_multi": 0, "fallback": 0, "esc_mod": 0}
    q = {"saturadas": 0, "activo": 0, "activo_acerc": 0, "lig_obst_vel": 0,
         "omega_suma": 0.0, "omega_n": 0}
    suma_mag = 0.0
    done = False
    hist_R = []  # [R]

    while not done:
        acciones, _ = _MODELO.predict(np.stack([obs[a] for a in agentes]),
                                      deterministic=True)
        acciones = np.asarray(acciones, dtype=np.float32)
        poses = np.array([env._estados[a][:3] for a in agentes])
        fb_t, esc_t, int_t = [-1] * n_a, [-1] * n_a, [-1] * n_a  # [R]
        do_t = [float("inf")] * n_a  # [R]
        xy_antes_t = poses[:, :2].copy()  # [R]
        obst_t = env.posiciones_actuales()
        vel_t = env.velocidades_actuales()
        if arm.fisicos:
            gestor.actualizar_obstaculos(obst_t)
        for i in range(n_a):
            accion_i, en_escape = gestor.gestionar(i, poses, acciones[i])
            acciones[i] = accion_i
            extras = barreras_robot_robot(filtro, i, poses)
            info: List[Tuple[str, float, float]] = []
            if arm.fisicos and arm.filas_obstaculo and obst_t:
                filas, info, n_sat = filas_obstaculo_f1(
                    filtro, poses[i], obst_t, vel_t, arm.termino_velocidad)
                extras = extras + filas
                q["saturadas"] += n_sat
            res = filtro.filtrar(poses[i], acciones[i], restricciones_extra=extras)
            if res.intervino:
                cont["interv"] += 1
                suma_mag += res.magnitud_modificacion
                cont["hmin_" + tipo_barrera(res.barrera_activa)] += 1
                restr = filtro._barreras_paredes(filtro._punto_de_mira(poses[i]),
                                                 float(poses[i, 2])) + extras
                u = np.asarray(res.u_seguro, dtype=np.float64)
                tipos = {tipo_barrera(r.nombre) for r in restr
                         if abs(float(r.c @ u) + ALFA_CBF * r.h) <= TOL_LIGANTE}
                for t in ("pared", "robot", "obst"):
                    cont["lig_" + t] += int(t in tipos)
                cont["lig_ninguna"] += int(not tipos)
                cont["lig_multi"] += int(len(tipos) > 1)
                cont["esc_mod"] += int(en_escape)
                # [Q] filas del obstáculo ligantes con el obstáculo acercándose,
                # y la parte de ω en c·u (el mecanismo de giro de la Fase 0).
                acerc = {nombre for nombre, _h, s in info if s > 0.0}
                if acerc:
                    lig_vel = [r for r in restr if r.nombre in acerc and
                               abs(float(r.c @ u) + ALFA_CBF * r.h) <= TOL_LIGANTE]
                    q["lig_obst_vel"] += int(bool(lig_vel))
                    for r in lig_vel:
                        cv = abs(float(r.c[0]) * float(u[0]))
                        cw = abs(float(r.c[1]) * float(u[1]))
                        if cv + cw > 0.0:
                            q["omega_suma"] += cw / (cv + cw)
                            q["omega_n"] += 1
            q["activo"] += int(any(h < ESC_UMBRAL_ACTIVA for _n, h, _s in info))
            q["activo_acerc"] += int(any(h < ESC_UMBRAL_ACTIVA and s > 0.0
                                         for _n, h, s in info))
            cont["fallback"] += int(not res.exito_qp)
            fb_t[i] = int(not res.exito_qp)  # [R]
            esc_t[i] = int(en_escape)  # [R]
            int_t[i] = int(res.intervino)  # [R]
            gestor.intervino_prev[i] = bool(res.intervino)
            acciones[i] = np.asarray(res.u_seguro, dtype=np.float32)
        gestor.pose_previa = poses.copy()

        obs, _, term, trunc, _ = env.step({a: acciones[k] for k, a in enumerate(agentes)})
        n_pasos += 1
        pos = np.array([env._estados[a][:2] for a in agentes])
        obst_ahora = env.posiciones_actuales()
        for ii, jj in combinations(range(n_a), 2):
            d = float(np.linalg.norm(pos[ii] - pos[jj]))
            if d < 0.15:
                pares15.add((ii, jj))
            if d < 0.22:
                pares22.add((ii, jj))
        for k in range(n_a):
            x, y = float(pos[k, 0]), float(pos[k, 1])
            dp = min(x, ARENA - x, y, ARENA - y)
            d_min_pared = min(d_min_pared, dp)
            if dp < ANCHO_PERIFERIA:
                pasos_periferia += 1
            if dp < MARGEN_CBF_M:
                pasos_banda += 1
                violo_margen[k] = True
            if dp < RADIO_CHASIS:
                contacto_pared[k] = True
            if obst_ahora:
                do = distancia_minima(pos[k], obst_ahora)
                do_t[k] = do  # [R]
                d_min_obst = min(d_min_obst, do)
                if do < COTA_CENTRO_OBST:
                    viol_cota_obst[k] = True
        cto_t = [int(env.contactos_obstaculo[a]) for a in agentes]  # [R]
        hist_R.append((fb_t, esc_t, int_t, do_t, xy_antes_t, pos.copy(), cto_t))  # [R]
        done = all(trunc.values()) or all(term.values())

    grid = env._field._grid_aoi.astype(np.float64)
    acc = ~mascara
    ap = n_pasos * n_a
    cob_acc = 1.0 - float(np.mean(grid[acc]))
    if arm.fisicos:
        cob_sin = 1.0 - (float(np.sum(grid[acc])) + float(np.sum(mascara))) / grid.size
    else:
        cob_sin = 1.0 - float(np.mean(env._field._grid_aoi))
    return {
        "condicion": cond.nombre, "escenario": cond.escenario,
        "fisicos": int(arm.fisicos), "seed_ep": seed_ep,
        "cobertura_accesible": cob_acc,
        "cobertura_sin_enmascarar": cob_sin,
        "cobertura_protocolo": 1.0 - float(np.mean(env._field._grid_aoi)),
        "frac_mascara": float(np.mean(mascara)),
        "cobertura_por_agente": cob_acc / n_a,
        "colisiones_015": len(pares15), "colisiones_022": len(pares22),
        "frac_agente_paso_banda_018": pasos_banda / ap,
        "frac_agente_paso_periferia_050": pasos_periferia / ap,
        "d_min_pared_centro": d_min_pared,
        "violaciones_margen": sum(violo_margen),
        "contacto_pared": sum(contacto_pared),
        "contactos_obst_eventos": sum(env.contactos_obstaculo.values()),
        "contactos_obst_agente_eps": sum(v > 0 for v in env.contactos_obstaculo.values()),
        "d_min_obst_superficie": d_min_obst,
        "viol_cota_obst_agente_eps": sum(viol_cota_obst),
        "cbf_frac_interv": cont["interv"] / ap,
        "cbf_frac_hmin_pared": cont["hmin_pared"] / ap,
        "cbf_frac_hmin_robot": cont["hmin_robot"] / ap,
        "cbf_frac_hmin_obst": cont["hmin_obst"] / ap,
        "cbf_frac_lig_pared": cont["lig_pared"] / ap,
        "cbf_frac_lig_robot": cont["lig_robot"] / ap,
        "cbf_frac_lig_obst": cont["lig_obst"] / ap,
        "cbf_frac_lig_multitipo": cont["lig_multi"] / ap,
        "cbf_frac_interv_sin_ligante": cont["lig_ninguna"] / ap,
        "cbf_magnitud_media": suma_mag / cont["interv"] if cont["interv"] else 0.0,
        "qp_fallbacks": cont["fallback"],
        "escape_n": sum(gestor.n_escapes),
        "escape_n_junto_obst": sum(gestor.n_escapes_obst),
        "escape_frac_ciclo": sum(gestor.decisiones) / ap,
        "escape_infactibles": sum(gestor.infactibles),
        "escape_infactibles_junto_obst": sum(gestor.infactibles_obst),
        "escape_infact_opuestas": sum(gestor.infact_opuestas),
        "escape_infact_sin_activas": sum(gestor.infact_sin_activas),
        "escape_infact_op_con_pared": gestor.infact_op_tipos["pared"],
        "escape_infact_op_con_robot": gestor.infact_op_tipos["robot"],
        "escape_infact_op_con_obst": gestor.infact_op_tipos["obst"],
        "rebote_fantasma": int(cond.tipo == "expo_fant"),
        "escape_agotados": sum(gestor.agotados),
        "escape_filtro_modifico": cont["esc_mod"],
        "agentes_reubicados": env.n_agentes_reubicados,
        "objetivos_reubicados": env._field.n_objetivos_reubicados,
        "rebotes_objetivo_obst": env._field.n_rebotes_obstaculo,
        "uso_grid_fallback": uso_fallback,
        "pasos": n_pasos,
        # ── [Q] columnas nuevas ──────────────────────────────────────────
        "tipo": cond.tipo,
        "mueve": int(any(tr.mueve for tr in arm.trayectorias)),
        "filas_obstaculo": int(arm.filas_obstaculo),
        "termino_velocidad": int(arm.termino_velocidad),
        "fases": ";".join(repr(float(f)) for f in arm.fases),
        "cob_acc_din": 1.0 - float(np.mean(grid[~mascara_din])),
        "cob_acc_arranque": 1.0 - float(np.mean(grid[~mascara_arr])),
        "frac_mascara_din": float(np.mean(mascara_din)),
        "frac_mascara_arranque": float(np.mean(mascara_arr)),
        "contactos_obst_empuje": env.contactos_empuje,
        "contactos_obst_avance": env.contactos_avance,
        "f1_filas_saturadas": q["saturadas"],
        "expo_frac_obst_activo": q["activo"] / ap,
        "expo_frac_activo_acercandose": q["activo_acerc"] / ap,
        "cbf_frac_lig_obst_vel": q["lig_obst_vel"] / ap,
        "f1_parte_omega_media": (q["omega_suma"] / q["omega_n"]
                                 if q["omega_n"] else 0.0),
        "f1_parte_omega_n": q["omega_n"],
        "t_episodio_s": time.perf_counter() - t0,
        "_hist_R": hist_R,  # [R]
    }


# =============================================================================
# PARTE B: COLUMNAS DERIVADAS, AUTOCHEQUEOS Y TRAZAS (funciones puras)
# =============================================================================

def _en_ventana(fb: Sequence[Sequence[int]], t: int, k: int, w: int) -> bool:
    """¿El agente k tuvo fallback en alguna de las decisiones t−w+1 … t?"""
    return any(fb[s][k] for s in range(max(0, t - w + 1), t + 1))


def columnas_derivadas(fb: Sequence[Sequence[int]], do: Sequence[Sequence[float]]
                       ) -> Dict[str, object]:
    """
    Columnas de la Parte B (§3.2 del prerregistro). fb[t][k] es la bandera de
    fallback de la decisión t del agente k; do[t][k], su distancia
    centro→superficie al obstáculo más cercano DESPUÉS del paso t (inf sin
    obstáculos). t = 0…T−1 en el orden del bucle, k ascendente; los mínimos
    usan < estricto (se conserva la primera ocurrencia, como `min`).
    """
    inf = float("inf")
    T = len(fb)
    n = len(fb[0]) if T else 0
    d_min = d_sin = d_en = inf
    fuera = {w: inf for w in VENTANAS_R}
    bajo = bajo_fuera = 0
    for t in range(T):
        for k in range(n):
            d = do[t][k]
            if d < d_min:
                d_min = d
            if fb[t][k]:
                if d < d_en:
                    d_en = d
            elif d < d_sin:
                d_sin = d
            for w in VENTANAS_R:
                if d < fuera[w] and not _en_ventana(fb, t, k, w):
                    fuera[w] = d
            if d < UMBRAL_H6_R:
                bajo += 1
                bajo_fuera += int(not _en_ventana(fb, t, k, W_VENTANA_R))
    paso = agente = -1
    if d_min < inf:
        paso, agente = next((t, k) for t in range(T) for k in range(n)
                            if do[t][k] <= d_min + TOL_EMPATE_R)
    fb_en = int(fb[paso][agente]) if paso >= 0 else 0
    racha = 0
    if fb_en:
        s = paso
        while s >= 0 and fb[s][agente]:
            racha += 1
            s -= 1
    salida: Dict[str, object] = {
        "pasos_agente_fallback": int(sum(sum(f) for f in fb)),
        "d_min_sin_fallback": d_sin,
        "d_min_en_fallback": d_en,
    }
    for w in VENTANAS_R:
        salida[f"d_min_fuera_ventana_{w}"] = fuera[w]
    salida.update({
        "pasos_bajo_010": bajo,
        "pasos_bajo_010_fuera_ventana_5": bajo_fuera,
        "paso_d_min": paso,
        "agente_d_min": agente,
        "fallback_en_d_min": fb_en,
        "racha_fallback_d_min": racha,
        "fallback_ventana_d_min_5": (int(_en_ventana(fb, paso, agente, W_VENTANA_R))
                                     if paso >= 0 else 0),
    })
    return salida


def _contactos_nuevos(hist: Sequence[tuple]) -> List[List[int]]:
    """Contactos nuevos por (t, k): diferencia del contador acumulado."""
    previos = [0] * (len(hist[0][6]) if hist else 0)
    salida = []
    for h in hist:
        salida.append([c - p for c, p in zip(h[6], previos)])
        previos = list(h[6])
    return salida


def autochequeos_R(hist: Sequence[tuple]) -> Dict[str, int]:
    """
    Autochequeos de la captura (§3.3 del prerregistro), contra contadores del
    propio Q. En cada fila:
      pasos_agente_intervino / (pasos·n_a) == cbf_frac_interv;
      pasos_agente_escape_intervino == escape_filtro_modifico;
      contactos_registrados == contactos_obst_eventos;
      fb_desplazado == 0: con u = (0, 0) la cinemática (Euler y el recorte de
        pared, que con u = 0 es la identidad) deja x, y EXACTOS, y la posición
        sólo cambia por la proyección de un contacto con obstáculo (no hay
        empuje entre robots: `_check_collisions` sólo detecta); un agente en
        fallback sin contacto nuevo no se mueve. Si el pareo
        decisión/distancia estuviera corrido un paso, fallaría;
      xy_discontinuo == 0: la posición después del paso t es la de antes del
        paso t + 1 (la captura de las posiciones está en su lugar).
    Agregado sobre una corrida (control, experimento):
      Σ fb_desplazado_corrido > 0 en las filas con fallback: lo mismo con la
        bandera de la decisión t − 1, que muestra que la prueba discrimina.
    """
    nuevos = _contactos_nuevos(hist)
    interv = esc_int = contactos = desplazado = corrido = discontinuo = 0
    for t, (fb_t, esc_t, int_t, _do_t, xy_a, xy_d, _cto_t) in enumerate(hist):
        for k in range(len(fb_t)):
            contactos += nuevos[t][k]
            interv += int_t[k]
            esc_int += esc_t[k] * int_t[k]
            movido = bool(xy_d[k][0] != xy_a[k][0] or xy_d[k][1] != xy_a[k][1])
            if nuevos[t][k] == 0 and movido:
                desplazado += fb_t[k]
                if t > 0:
                    corrido += hist[t - 1][0][k]
            if t > 0:
                previo = hist[t - 1][5][k]
                discontinuo += int(bool(xy_a[k][0] != previo[0] or xy_a[k][1] != previo[1]))
    return {"pasos_agente_intervino": interv, "pasos_agente_escape_intervino": esc_int,
            "contactos_registrados": contactos, "fb_desplazado": desplazado,
            "xy_discontinuo": discontinuo, "fb_desplazado_corrido": corrido}


def filas_traza_R(hist: Sequence[tuple]) -> List[Dict[str, object]]:
    """Una fila por (paso, agente), en el orden del bucle."""
    nuevos = _contactos_nuevos(hist)
    filas: List[Dict[str, object]] = []
    for t, (fb_t, esc_t, int_t, do_t, xy_a, xy_d, _cto_t) in enumerate(hist):
        for k in range(len(fb_t)):
            filas.append({"paso": t, "agente": k, "fallback": fb_t[k], "d_obst": do_t[k],
                          "en_escape": esc_t[k], "intervino": int_t[k],
                          "x_antes": float(xy_a[k][0]), "y_antes": float(xy_a[k][1]),
                          "x_despues": float(xy_d[k][0]), "y_despues": float(xy_d[k][1]),
                          "contacto_nuevo": nuevos[t][k]})
    return filas


def requiere_traza_R(fila: Dict[str, object]) -> bool:
    """Celdas con obstáculo físico: fallback, contacto o d_min < 0,10 m."""
    return (str(fila["tipo"]) != "ctrl"
            and (float(fila["qp_fallbacks"]) > 0
                 or float(fila["contactos_obst_eventos"]) > 0
                 or float(fila["d_min_obst_superficie"]) < UMBRAL_H6_R))


def _tarea_R(args: Tuple[CondicionQ, int]) -> Dict[str, object]:
    """Episodio + columnas derivadas + autochequeos (+ traza), en el trabajador."""
    cond, seed_ep = args
    fila = correr_episodio_R(cond, seed_ep)
    hist = fila.pop("_hist_R")
    if any(-1 in h[0] or -1 in h[1] or -1 in h[2] for h in hist):
        raise RuntimeError(f"{cond.nombre}/{seed_ep}: un agente no pasó por el filtro")
    fila.update(columnas_derivadas([h[0] for h in hist], [h[3] for h in hist]))
    fila.update(autochequeos_R(hist))
    fila["_traza_R"] = filas_traza_R(hist) if requiere_traza_R(fila) else None
    # El código con que corrió ESTE trabajador (spawn lo carga del disco al
    # crear el pool): el proceso principal lo compara con la firma.
    fila["_huella_trabajador_R"] = _HUELLA_AL_IMPORTAR_R
    return fila


def semillas_R() -> List[int]:
    """420110–420509."""
    return [SEED_BASE * 10_000 + i for i in range(SEMILLA_INICIO_R,
                                                  SEMILLA_INICIO_R + N_SEMILLAS_R)]


def linea_semillas_R(semillas: Sequence[int]) -> str:
    """La firma de una lista de semillas (la pasabilidad se ata a ella)."""
    h = hashlib.sha256(",".join(str(s) for s in semillas).encode("utf-8")).hexdigest()
    return f"SEMILLAS_R {h} {semillas[0]}-{semillas[-1]} n {len(semillas)}"


def linea_entorno_R() -> str:
    """Intérprete y procesador: el control aprobado vale sólo en el mismo entorno."""
    return f"ENTORNO_R python {platform.python_version()} | {platform.processor()}"


# =============================================================================
# ORQUESTACIÓN: PARCIALES Y TRAZAS
# =============================================================================

def claves_retorno_Q() -> List[str]:
    """Las 67 claves del retorno de `correr_episodio_Q`, en su orden (AST)."""
    import ast
    arbol = ast.parse((_CARPETA_Q / "correr_experimento_Q.py").read_text(encoding="utf-8"))
    fn = next(n for n in arbol.body if isinstance(n, ast.FunctionDef)
              and n.name == "correr_episodio_Q")
    return [k.value for k in fn.body[-1].value.keys]


def columnas_esperadas_R() -> List[str]:
    return claves_retorno_Q() + list(DERIVADAS_R) + list(AUTOCHEQUEOS_R)


def ruta_traza_R(dir_trazas: Path, prefijo: str, cond: str, semilla: object) -> Path:
    return dir_trazas / f"{prefijo}_{cond}_{int(semilla)}.csv"


def trazas_de_celda_R(dir_trazas: Path, prefijo: str, cond: str) -> List[Path]:
    """Sólo los nombres EXACTOS <prefijo>_<celda>_<semilla de 6 cifras>.csv (una
    copia de conflicto de OneDrive u otro archivo no cuentan)."""
    patron = re.compile(rf"^{re.escape(prefijo)}_{re.escape(cond)}_\d{{6}}\.csv$")
    return sorted(p for p in dir_trazas.glob(f"{prefijo}_{cond}_*") if patron.match(p.name))


def _reintentar_R(accion: Callable[[], None]) -> None:
    """Reintenta una escritura o un renombre bloqueados (OneDrive, un visor abierto)."""
    for intento in range(REINTENTOS_ESCRITURA_R):
        try:
            accion()
            return
        except PermissionError:
            if intento == REINTENTOS_ESCRITURA_R - 1:
                raise
            time.sleep(0.5)


def _respaldar_R(ruta: Path) -> None:
    """Si existe, el archivo pasa a <nombre>_respaldo_<sello><sufijo> (nunca se pisa)."""
    if ruta.exists():
        destino = ruta.with_name(f"{ruta.stem}_respaldo_{datetime.now():%Y%m%d_%H%M%S}"
                                 f"{ruta.suffix}")
        _reintentar_R(lambda: ruta.rename(destino))


def escribir_csv_R(filas: Sequence[Dict[str, object]], ruta: Path) -> None:
    """
    El formato de `escribir_csv` del Exp O (repr de cada float, LF, sin
    redondeo), pero a un temporal y después `os.replace`: un corte no deja un
    CSV a medias con el nombre final. Respalda lo que existiera.
    """
    _respaldar_R(ruta)
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")

    def escribir() -> None:
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(filas[0].keys()), lineterminator="\n")
            w.writeheader()
            for fila in filas:
                w.writerow({k: (repr(v) if isinstance(v, float) else v) for k, v in fila.items()})
        os.replace(tmp, ruta)
    _reintentar_R(escribir)


def escribir_traza_R(filas: Sequence[Dict[str, object]], ruta: Path) -> None:
    """CSV LF sin redondeo, a un temporal y después `os.replace`."""
    tmp = ruta.with_suffix(".tmp")

    def escribir() -> None:
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(COLUMNAS_TRAZA_R), lineterminator="\n")
            w.writeheader()
            for fila in filas:
                w.writerow({k: (repr(v) if isinstance(v, float) else v)
                            for k, v in fila.items()})
        os.replace(tmp, ruta)
    _reintentar_R(escribir)


def _apartar_trazas_R(dir_trazas: Path, prefijo: str, cond: str) -> int:
    """Antes de rehacer una celda, sus trazas viejas van a un respaldo con sello."""
    viejas = trazas_de_celda_R(dir_trazas, prefijo, cond)
    if viejas:
        destino = dir_trazas / f"respaldo_{datetime.now():%Y%m%d_%H%M%S}"
        destino.mkdir(parents=True, exist_ok=True)
        for p in viejas:
            _reintentar_R(lambda p=p: p.rename(destino / p.name))
    return len(viejas)


def _problemas_trazas_R(filas: Sequence[Dict[str, str]], prefijo: str, cond: str,
                        dir_trazas: Path) -> List[str]:
    """Biyección trazas ↔ filas que las requieren, con pasos·n_a filas cada una."""
    esperadas = {ruta_traza_R(dir_trazas, prefijo, cond, f["seed_ep"]).name: f
                 for f in filas if requiere_traza_R(f)}
    hay = {p.name for p in trazas_de_celda_R(dir_trazas, prefijo, cond)}
    malas = [f"traza que sobra: {n}" for n in sorted(hay - set(esperadas))]
    malas += [f"traza que falta: {n}" for n in sorted(set(esperadas) - hay)]
    for nombre in sorted(set(esperadas) & hay):
        with open(dir_trazas / nombre, encoding="utf-8") as fh:
            lector = csv.reader(fh)
            cab = next(lector, [])
            n = sum(1 for _ in lector)
        f = esperadas[nombre]
        if tuple(cab) != COLUMNAS_TRAZA_R or n != int(f["pasos"]) * N_AGENTES:
            malas.append(f"traza incompleta: {nombre} ({n} filas)")
    return malas


def _leer_firma_R(meta: Path) -> Tuple[str, str]:
    """(firma, sha256 del CSV) de un archivo .firma de dos líneas."""
    lineas = meta.read_text(encoding="utf-8").splitlines()
    return (lineas[0].strip() if lineas else "",
            lineas[1].strip()[len("csv "):] if len(lineas) > 1 else "")


def parcial_invalido_R(ruta: Path, firma: str, semillas: Sequence[int],
                       columnas: Sequence[str], prefijo: str, cond: str,
                       dir_trazas: Path) -> Optional[str]:
    """Motivo por el que un parcial NO se puede reutilizar, o None."""
    meta = ruta.with_suffix(".firma")
    if not (ruta.exists() and meta.exists()):
        return "no existe"
    firma_hay, sha_csv = _leer_firma_R(meta)
    if firma_hay != firma:
        return "firma distinta (otro código, otras semillas u otro intérprete)"
    datos = ruta.read_bytes()
    if hashlib.sha256(datos).hexdigest() != sha_csv:
        return "el CSV no es el que se firmó (¿editado o cortado?)"
    if not datos.endswith(b"\n"):
        return "el CSV no termina en fin de línea (¿corte a mitad de la escritura?)"
    fc = _leer_csv(ruta)
    if not fc or list(fc[0].keys()) != list(columnas):
        return "columnas distintas de las esperadas"
    if any(None in f or any(v is None or v == "" for v in f.values()) for f in fc):
        return "fila incompleta o con campos de más"
    if sorted(int(f["seed_ep"]) for f in fc) != sorted(semillas):
        return "semillas distintas"
    malas = _problemas_trazas_R(fc, prefijo, cond, dir_trazas)
    return f"trazas: {malas[0]}" if malas else None


def correr_condiciones_R(conds: Sequence[CondicionQ], n_trab: int, prefijo: str,
                         huella_q: str, huella_r: str, semillas: Sequence[int],
                         dir_parciales: Path, dir_trazas: Path, log: Callable[[str], None],
                         compuerta: Optional[Callable[[str], None]] = None
                         ) -> List[Dict[str, str]]:
    """
    La orquestación de `Q.correr_condiciones` con `_tarea_R`: condiciones ×
    semillas en procesos (1 hilo de torch cada uno), una condición a la vez,
    cada una en `<dir_parciales>/<prefijo>_<condición>.csv` con su firma
    (huella R + semillas + intérprete, y el sha256 del CSV). Un parcial se
    reutiliza sólo con la misma firma, el mismo sha256, filas completas, las
    mismas semillas y sus trazas completas. Antes de escribir cada parcial se
    comprueba que el código con que corrieron los trabajadores Y el del disco
    sean los de la firma (spawn carga el código al crear el pool). Las trazas
    las escribe ESTE proceso, antes del parcial. `compuerta(celda)` corre antes
    de cada celda que hay que correr. Devuelve las filas COMO TEXTO.
    """
    semillas = list(semillas)
    if len(set(semillas)) != len(semillas):
        raise SystemExit("PARAR: semillas repetidas.")
    dir_parciales.mkdir(parents=True, exist_ok=True)
    dir_trazas.mkdir(parents=True, exist_ok=True)
    firma = (f"{huella_r} semillas {semillas[0]}-{semillas[-1]} n {len(semillas)} "
             f"python {platform.python_version()}")
    columnas = columnas_esperadas_R()
    filas: List[Dict[str, str]] = []
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=n_trab, initializer=_inicializar_trabajador) as ex:
        for c in conds:
            ruta = dir_parciales / f"{prefijo}_{c.nombre}.csv"
            meta = ruta.with_suffix(".firma")
            motivo = parcial_invalido_R(ruta, firma, semillas, columnas, prefijo,
                                        c.nombre, dir_trazas)
            reutilizada = motivo is None
            if not reutilizada:
                if compuerta is not None:
                    compuerta(c.nombre)
                if motivo != "no existe":
                    log(f"  {c.nombre:10s} se rehace: {motivo}")
                _respaldar_R(meta)
                _respaldar_R(ruta)
                apartadas = _apartar_trazas_R(dir_trazas, prefijo, c.nombre)
                if apartadas:
                    log(f"  {c.nombre:10s} {apartadas} trazas viejas a respaldo")
                t1 = time.perf_counter()
                nuevas = list(ex.map(_tarea_R, [(c, s) for s in semillas], chunksize=1))
                otras = {f.pop("_huella_trabajador_R") for f in nuevas} - {huella_r}
                if otras or Q.huella_codigo() != huella_q or huella_R() != huella_r:
                    raise SystemExit(f"PARAR: el código cambió durante {c.nombre} (trabajadores "
                                     f"{sorted(otras) or 'iguales'}); no se escribe el parcial.")
                for f in nuevas:
                    traza = f.pop("_traza_R")
                    if traza is not None:
                        escribir_traza_R(traza, ruta_traza_R(dir_trazas, prefijo, c.nombre,
                                                             f["seed_ep"]))
                escribir_csv_R(nuevas, ruta)
                sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
                _reintentar_R(lambda: meta.write_bytes(f"{firma}\ncsv {sha}\n".encode("utf-8")))
                motivo = parcial_invalido_R(ruta, firma, semillas, columnas, prefijo,
                                            c.nombre, dir_trazas)
                if motivo is not None:
                    raise SystemExit(f"PARAR: el parcial recién escrito de {c.nombre} no "
                                     f"valida: {motivo}")
                log(f"  {c.nombre:10s} corrida en {time.perf_counter() - t1:.1f} s")
            fc = _leer_csv(ruta)
            log(f"  {c.nombre:10s} cob_acc="
                f"{np.mean([float(f['cobertura_accesible']) for f in fc]):.8f} "
                f"interv={np.mean([float(f['cbf_frac_interv']) for f in fc]):.6f} "
                f"t/ep={np.mean([float(f['t_episodio_s']) for f in fc]):.2f} s"
                f"{' (reutilizada)' if reutilizada else ''}")
            problemas, _resumen = autochequeos_filas_R(fc, agregado=False)
            if problemas:
                log(f"  {c.nombre:10s} PARTE B: {len(problemas)} problemas en la celda "
                    f"(primero: {problemas[0]})")
            filas += fc
    log(f"  tiempo de pared {time.perf_counter() - t0:.1f} s")
    return filas


# =============================================================================
# VERIFICACIONES
# =============================================================================

def sha256_archivo_R(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def huella_R() -> str:
    """sha256(huella_Q + "|" + sha256(correr_experimento_R.py))."""
    return hashlib.sha256(f"{Q.huella_codigo()}|{sha256_archivo_R(RUTA_CODIGO_R)}"
                          .encode("utf-8")).hexdigest()


def prerregistro_R() -> Tuple[str, str]:
    """(línea 'PREREGISTRO_R.md sha256 … (Fijado: …)', línea Fijado)."""
    texto = RUTA_PREREG_R.read_bytes()
    fijado = next((x.strip() for x in texto.decode("utf-8").splitlines()
                   if x.startswith("Fijado: ")), "Fijado: (sin línea)")
    return (f"PREREGISTRO_R.md sha256 {hashlib.sha256(texto).hexdigest()} ({fijado})", fijado)


def exigir_prerregistro_fijado_R() -> str:
    """El control, la pasabilidad, el manifiesto y el experimento exigen el
    prerregistro FIJADO (línea 'Fijado: AAAA-MM-DD HH:MM'). Devuelve su línea."""
    linea, fijado = prerregistro_R()
    if not RE_FIJADO_R.match(fijado):
        raise SystemExit(f"PARAR: PREREGISTRO_R.md no está fijado ({fijado}).")
    return linea


def sha256_intactos_R() -> List[str]:
    """Los tres archivos de S1 y los tres crudos exploratorios; si no, PARAR."""
    L, malos = [], []
    for rel, esperado in SHA256_INTACTOS_R.items():
        actual = sha256_archivo_R(_CARPETA_Q / rel)
        L.append(f"  {'IGUAL' if actual == esperado else 'DISTINTO'} {actual} {rel}")
        if actual != esperado:
            malos.append(rel)
    if malos:
        raise SystemExit(f"PARAR: cambiaron resultados del Exp Q: {malos}")
    return ["RESULTADOS DEL EXP Q sin cambios (S1 y crudos exploratorios):"] + L


def _leer_manifiesto_R(ruta: Path) -> Dict[str, str]:
    """`<sha256> *./<ruta>` → {ruta: sha256} (formato de sha256sum)."""
    salida: Dict[str, str] = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        partes = linea.split(" ", 1)
        if len(partes) == 2 and partes[1].startswith("*./") and len(partes[0]) == 64:
            salida[partes[1][3:]] = partes[0]
    return salida


def arbol_expq_R() -> Dict[str, str]:
    """{ruta relativa: sha256} de TODOS los archivos de la carpeta del Exp Q."""
    return {p.relative_to(_CARPETA_Q).as_posix(): sha256_archivo_R(p)
            for p in sorted(_CARPETA_Q.rglob("*")) if p.is_file()}


def revisar_arbol_R() -> List[str]:
    """El árbol del Exp Q contra la referencia: ni cambios ni archivos nuevos."""
    if not RUTA_ARBOL_REF_R.exists():
        raise SystemExit("PARAR: falta la referencia del árbol del Exp Q; correr "
                         "`python -B correr_experimento_R.py arbol`.")
    ref = _leer_manifiesto_R(RUTA_ARBOL_REF_R)
    actual = arbol_expq_R()
    malas = ([f"nuevo: {r}" for r in sorted(set(actual) - set(ref))]
             + [f"falta: {r}" for r in sorted(set(ref) - set(actual))]
             + [f"cambió: {r}" for r in sorted(set(ref) & set(actual)) if ref[r] != actual[r]])
    if malas:
        raise SystemExit(f"PARAR: el árbol del Exp Q cambió: {malas[:10]}")
    return [f"ÁRBOL DEL EXP Q igual a la referencia: {len(actual)} archivos"]


def chequeo_congelados_R() -> Tuple[bool, str]:
    """El chequeo de PROTOCOLO_L0_L2.md:210 (sólo lee: sha256 de los congelados)."""
    r = subprocess.run([sys.executable, "-B", "-c", CMD_CONGELADOS_R], cwd=str(DIR_COORD_R),
                       capture_output=True, text=True, encoding="utf-8", timeout=300,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    salida = (r.stdout or "").strip()
    return salida == "IGUAL a lo probado", salida or (r.stderr or "").strip()[-400:]


class _EstadoEnergiaR(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]


def corriente_alterna_R() -> Tuple[bool, str]:
    """(¿enchufada?, texto), de GetSystemPowerStatus (sólo lee)."""
    e = _EstadoEnergiaR()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(e)):
        return False, "energía: GetSystemPowerStatus falló"
    fuente = {0: "a batería", 1: "enchufada"}.get(e.ACLineStatus, "desconocida")
    pct = "?" if e.BatteryLifePercent == 255 else f"{e.BatteryLifePercent} %"
    return e.ACLineStatus == 1, f"energía: {fuente}, batería {pct}"


def reinicio_pendiente_R() -> Optional[str]:
    """Clave de Windows Update con un reinicio pendiente, o None (sólo lee)."""
    import winreg
    claves = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
              r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending")
    for clave in claves:
        try:
            winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, clave).Close()
            return clave.rsplit(chr(92), 1)[-1]
        except OSError:
            continue
    return None


def patrones_coordinador_R() -> List[str]:
    """Los scripts del coordinador (sin tests ni respaldos), como nombres de archivo."""
    return sorted(p.name for p in DIR_COORD_R.glob("*.py")
                  if not p.name.startswith("test_") and "_respaldo_" not in p.name)


def proceso_bloquea_R(nombre: str, cmd: str, scripts: Sequence[str]) -> bool:
    """¿Este proceso impide correr? MATLAB o Webots por nombre; un python con otra
    corrida de O, Q o R o con un script del coordinador en la línea de comandos."""
    nom = nombre.strip().lower()
    if nom.startswith(PROGRAMAS_R):
        return True
    return nom.startswith("python") and bool(
        RE_CORRIDAS_R.search(cmd) or any(re.search(rf"(?<![\w.]){re.escape(s)}\b", cmd)
                                         for s in scripts))


def otros_procesos_R() -> Tuple[List[str], Optional[str]]:
    """
    (procesos que impiden correr, motivo si NO se pudo comprobar). Falla
    cerrado: si PowerShell o CIM fallan, si la consulta no ve a este mismo
    proceso o si un python llega sin línea de comandos, no se pudo comprobar.
    """
    orden = ("Get-CimInstance Win32_Process | ForEach-Object "
             "{ \"$($_.ProcessId)`t$($_.Name)`t$($_.CommandLine)\" }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", orden],
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return [], f"no se pudo consultar los procesos: {e}"
    if r.returncode != 0:
        return [], f"PowerShell salió con {r.returncode}: {(r.stderr or '').strip()[:200]}"
    propios = {os.getpid(), os.getppid()}
    scripts = patrones_coordinador_R()
    vistos, malos, sin_cmd = set(), [], []
    for linea in (r.stdout or "").splitlines():
        pid, nombre, cmd = (linea.split("\t", 2) + ["", ""])[:3]
        if not pid.strip().isdigit():
            continue
        pid_i = int(pid)
        vistos.add(pid_i)
        if pid_i in propios:
            continue
        if nombre.strip().lower().startswith("python") and not cmd.strip():
            sin_cmd.append(pid_i)
        elif proceso_bloquea_R(nombre, cmd, scripts):
            malos.append(f"{pid_i}: {nombre.strip()} {cmd.strip()[:160]}")
    if os.getpid() not in vistos:
        return malos, "la consulta de procesos no ve a este mismo proceso"
    if sin_cmd:
        return malos, f"procesos de python sin línea de comandos legible: {sin_cmd}"
    return malos, None


def exigir_stack_R() -> str:
    linea = Q.verificar_stack()
    if "DISTINTO" in linea:
        raise SystemExit(f"PARAR: {linea}")
    return linea


# =============================================================================
# REGISTROS
# =============================================================================

def _escribir_registro_R(ruta: Path, lineas: Sequence[str], huella_q: str, huella_r: str,
                         firmas: Sequence[str]) -> None:
    """
    Escribe un registro DESPUÉS de comprobar que ni el código del Exp Q ni el
    de R cambiaron durante la corrida. `firmas` son las líneas que lo atan a lo
    que se aprobó (HUELLA_Q, HUELLA_R, SEMILLAS_R, PREREGISTRO_R.md…). Si ya
    existía, el viejo pasa a `_respaldo_<sello>`.
    """
    if Q.huella_codigo() != huella_q or huella_R() != huella_r:
        raise SystemExit(f"PARAR: el código cambió durante la corrida; no se escribe "
                         f"{ruta.name}.")
    _respaldar_R(ruta)
    texto = "\n".join(list(lineas) + list(firmas)) + "\n"
    _reintentar_R(lambda: ruta.write_bytes(texto.encode("utf-8")))


def _aprobado_R(ruta: Path, requeridas: Sequence[str]) -> Optional[str]:
    """Motivo de rechazo, o None si el registro tiene TODAS las líneas pedidas."""
    if not ruta.exists():
        return f"falta {ruta.name}"
    lineas = set(ruta.read_text(encoding="utf-8").splitlines())
    faltan = [r for r in requeridas if r not in lineas]
    return f"{ruta.name} no tiene: {faltan}" if faltan else None


def lineas_ast_requeridas_R(huella_r: str, carpeta: Path) -> List[str]:
    return ["COMPROBACIÓN 1: OK", "COMPROBACIÓN 2: OK", "COMPROBACIÓN 3: OK",
            "NOMBRES LIBRES: OK", f"HUELLA_R {huella_r}",
            f"SHA256 comparar_ast_R.py {sha256_archivo_R(carpeta / 'comparar_ast_R.py')}"]


def manifiestos_R(dir_res: Path) -> List[Path]:
    return sorted(dir_res.glob("manifiesto_R_pre_*.txt"))


def ultimo_manifiesto_R(dir_res: Path) -> Optional[Path]:
    hay = manifiestos_R(dir_res)
    return hay[-1] if hay else None


def resultados_de_R_existentes(dir_res: Path) -> List[str]:
    """Lo que ya produjo `experimento` (el manifiesto pre se niega si hay algo)."""
    hay = (sorted((dir_res / "parciales").glob(f"{PREFIJO_EXP_R}_*"))
           + sorted((dir_res / "trazas").glob(f"{PREFIJO_EXP_R}_*"))
           + [p for p in (dir_res / "registro_R.txt", dir_res / "experimento_R_completo.csv")
              if p.exists()])
    return [p.name for p in hay]


def motivos_manifiesto_R(dir_res: Path, carpeta: Path, huella_r: str) -> List[str]:
    """El manifiesto pre más reciente: completo y con el sha256 actual de todo."""
    ruta = ultimo_manifiesto_R(dir_res)
    if ruta is None:
        return ["falta el manifiesto pre (manifiesto_R_pre_*.txt)"]
    entradas = _leer_manifiesto_R(ruta)
    motivos = [f"{ruta.name} no lista {r}" for r in REQUERIDOS_MANIFIESTO_R
               if r not in entradas]
    for rel, h in entradas.items():
        p = carpeta / rel
        if not p.exists():
            motivos.append(f"{ruta.name}: falta {rel}")
        elif sha256_archivo_R(p) != h:
            motivos.append(f"{ruta.name}: {rel} cambió después del manifiesto")
    if f"HUELLA_R {huella_r}" not in ruta.read_text(encoding="utf-8").splitlines():
        motivos.append(f"{ruta.name} se hizo con OTRO código de R")
    return motivos


def motivos_experimento_R(dir_res: Path, carpeta: Path, huella_q: str, huella_r: str,
                          semillas: Sequence[int], linea_prereg: str, linea_entorno: str,
                          sin_parte_b: bool) -> List[str]:
    """TODOS los motivos por los que `experimento` no puede correr (lista vacía: puede)."""
    motivos = []
    control = dir_res / "control_bit_a_bit_R.txt"
    for ruta, requeridas in (
            (dir_res / "comparar_ast_R.txt", lineas_ast_requeridas_R(huella_r, carpeta)),
            (control, ["CONTROL: OK", f"HUELLA_R {huella_r}", linea_prereg, linea_entorno]),
            (dir_res / "pasabilidad_R.txt", ["PASABILIDAD: OK", f"HUELLA_Q {huella_q}",
                                            linea_semillas_R(semillas), linea_prereg])):
        m = _aprobado_R(ruta, requeridas)
        if m:
            motivos.append(m)
    if (control.exists() and "PARTE B: NO" in control.read_text(encoding="utf-8")
            and not sin_parte_b):
        motivos.append("el control dice PARTE B: NO; corregir y repetir el control, o correr "
                       "con --sin-parte-b (§7 del prerregistro)")
    return motivos + motivos_manifiesto_R(dir_res, carpeta, huella_r)


# =============================================================================
# COMPARACIÓN Y AUTOCHEQUEOS SOBRE FILAS DE TEXTO
# =============================================================================

def comparar_filas_R(filas: Sequence[Dict[str, str]], ruta: Path, ignorar: Sequence[str]
                     ) -> Tuple[int, int, int, List[str], List[Tuple[str, int]]]:
    """
    (iguales, filas del CSV, columnas comparadas, diferencias, claves malas).
    ESTRICTO: el texto de cada columna del CSV de referencia (salvo `ignorar`)
    tiene que ser idéntico al de la fila de R (`_serial`, repr de cada float).
    """
    ref = {(r["condicion"], int(r["seed_ep"])): r for r in _leer_csv(ruta)}
    propias = {(str(f["condicion"]), int(f["seed_ep"])): f for f in filas}
    columnas = [c for c in next(iter(ref.values())).keys() if c not in ignorar]
    malas, claves = [], []
    iguales = 0
    for clave, r in ref.items():
        f = propias.get(clave)
        dif = ["(falta en R)"] if f is None else [c for c in columnas
                                                  if _serial(f.get(c)) != r[c]]
        if dif:
            malas.append(f"{clave}: {dif[:4]}")
            claves.append(clave)
        else:
            iguales += 1
    return iguales, len(ref), len(columnas), malas, claves


def autochequeos_filas_R(filas: Sequence[Dict[str, str]], agregado: bool = True
                         ) -> Tuple[List[str], List[str]]:
    """(problemas, resumen) de los autochequeos de la Parte B en filas de texto."""
    problemas: List[str] = []
    corrido = con_fb = corrido_cero = 0
    for f in filas:
        clave = f"{f['condicion']}/{f['seed_ep']}"
        ap = int(f["pasos"]) * N_AGENTES
        if int(f["pasos_agente_fallback"]) != int(f["qp_fallbacks"]):
            problemas.append(f"{clave}: pasos_agente_fallback ≠ qp_fallbacks")
        if (min(float(f["d_min_sin_fallback"]), float(f["d_min_en_fallback"]))
                != float(f["d_min_obst_superficie"])):
            problemas.append(f"{clave}: mín(sin, en fallback) ≠ d_min_obst_superficie")
        if int(f["fb_desplazado"]) != 0:
            problemas.append(f"{clave}: {f['fb_desplazado']} agente-pasos en fallback "
                             f"se movieron sin contacto")
        if int(f["xy_discontinuo"]) != 0:
            problemas.append(f"{clave}: posición antes del paso ≠ posición después del anterior")
        if int(f["contactos_registrados"]) != int(f["contactos_obst_eventos"]):
            problemas.append(f"{clave}: contactos_registrados ≠ contactos_obst_eventos")
        if repr(int(f["pasos_agente_intervino"]) / ap) != f["cbf_frac_interv"]:
            problemas.append(f"{clave}: pasos_agente_intervino/(pasos·n_a) ≠ cbf_frac_interv")
        if int(f["pasos_agente_escape_intervino"]) != int(f["escape_filtro_modifico"]):
            problemas.append(f"{clave}: escape∧intervino ≠ escape_filtro_modifico")
        if int(f["qp_fallbacks"]) > 0:
            con_fb += 1
            corrido += int(f["fb_desplazado_corrido"])
            corrido_cero += int(int(f["fb_desplazado_corrido"]) == 0)
    resumen = [f"AUTOCHEQUEOS de la Parte B en {len(filas)} filas: pasos_agente_fallback = "
               f"qp_fallbacks; mín(d_min_sin_fallback, d_min_en_fallback) = "
               f"d_min_obst_superficie; contactos_registrados = contactos_obst_eventos; "
               f"intervención y escape∧intervino = los contadores de Q; continuidad de las "
               f"posiciones; fb_desplazado = 0 (prueba física del pareo) → "
               f"{len(problemas)} problemas",
               f"  la prueba física discrimina: con la bandera corrida un paso, "
               f"{corrido} agente-pasos en fallback se mueven sin contacto, en {con_fb} "
               f"episodios con fallback ({corrido_cero} de ellos con 0, descriptivo)"]
    if agregado and con_fb and corrido == 0:
        problemas.append("la prueba física no discrimina (Σ fb_desplazado_corrido = 0)")
    return problemas, resumen


def lineas_parte_b_R(auto: Sequence[str], traz: Sequence[str], sin_parte_b: bool = False
                     ) -> List[str]:
    """
    El veredicto de la Parte B para un registro. Con «PARTE B: NO» lista TODOS
    los episodios con el autochequeo que falló (y los problemas de trazas), y
    deja constancia de que las 66 columnas de Q de cada fila siguen valiendo
    por construcción.
    """
    if sin_parte_b:
        return ["PARTE B: NO (corrida --sin-parte-b, §7 del prerregistro)"]
    if not auto and not traz:
        return ["PARTE B: OK"]
    return (["PARTE B: NO (H6 y la ubicación de los contactos de H5a quedan 'no evaluable')"]
            + [f"  autochequeo que falló — {p}" for p in auto]
            + [f"  trazas — {p}" for p in traz]
            + ["  las 66 columnas de Q de cada fila siguen siendo válidas por construcción: las "
               "líneas [R] sólo registran (comprobación 3 de comparar_ast_R.py) y, sin ellas, "
               "el texto de correr_episodio_R es el de correr_episodio_Q (comprobación 1); lo "
               "único que no se puede leer es la Parte B"])


def biyeccion_trazas_R(filas: Sequence[Dict[str, str]], prefijo: str, dir_trazas: Path
                       ) -> Tuple[List[str], int]:
    """(problemas, trazas) sobre todas las celdas de `filas`."""
    problemas: List[str] = []
    celdas = sorted({str(f["condicion"]) for f in filas})
    for c in celdas:
        problemas += _problemas_trazas_R([f for f in filas if f["condicion"] == c],
                                         prefijo, c, dir_trazas)
    return problemas, sum(1 for f in filas if requiere_traza_R(f))


# =============================================================================
# SUBCOMANDOS
# =============================================================================

class RegistroTramo:
    """Imprime y agrega al log del tramo (uno por invocación, con sello)."""

    def __init__(self, ruta: Path) -> None:
        self.ruta = ruta

    def __call__(self, texto: str) -> None:
        try:
            print(texto, flush=True)
        except UnicodeEncodeError:
            print(texto.encode("ascii", "replace").decode("ascii"), flush=True)
        with open(self.ruta, "a", encoding="utf-8", newline="\n") as f:
            f.write(texto + "\n")


def compuerta_energia_R(log: Callable[[str], None]) -> Callable[[str], None]:
    """Antes de cada celda: enchufada, o PARAR (los parciales quedan)."""
    def compuerta(celda: str) -> None:
        ok, texto = corriente_alterna_R()
        log(f"  {celda:10s} {texto}")
        if not ok:
            raise SystemExit(f"PARAR antes de {celda}: la PC no está enchufada. Lo hecho "
                             f"queda en los parciales; enchufar y relanzar.")
    return compuerta


def _procesos_o_parar_R(L: List[str]) -> None:
    malos, motivo = otros_procesos_R()
    if motivo:
        raise SystemExit(f"PARAR: no se pudo comprobar que no haya otra corrida ni el "
                         f"laboratorio en marcha ({motivo}).")
    if malos:
        raise SystemExit(f"PARAR: hay otra corrida, el laboratorio o MATLAB/Webots en marcha: "
                         f"{malos}")
    L.append("procesos: ninguna otra corrida, ni scripts del coordinador, ni MATLAB/Webots")


def previos_R(modo: str, huella_q: str, huella_r: str, n_trab: int,
              log: Callable[[str], None]) -> List[str]:
    """Verificaciones al empezar cada subcomando (cualquier falla: PARAR)."""
    L = [f"inicio {datetime.now():%Y-%m-%d %H:%M:%S}",
         f"huella del Exp Q: {huella_q} (la de S1 y el exploratorio)",
         f"huella de R: {huella_r}", linea_entorno_R(),
         f"procesos de trabajo: {n_trab}; -B {'sí' if sys.flags.dont_write_bytecode else 'NO'}"]
    if modo in ("control", "pasabilidad", "manifiesto", "experimento"):
        L.append(exigir_prerregistro_fijado_R())
    L += Q.verificar_copias()
    L.append(exigir_stack_R())
    L += sha256_intactos_R()
    if modo != "arbol":
        L += revisar_arbol_R()
    if modo in ("control", "pasabilidad", "experimento"):
        _procesos_o_parar_R(L)
        ok, texto = corriente_alterna_R()
        L.append(texto)
        if not ok:
            raise SystemExit("PARAR: la PC no está enchufada.")
        reinicio = reinicio_pendiente_R()
        if reinicio:
            raise SystemExit(f"PARAR: Windows tiene un reinicio pendiente ({reinicio}); "
                             f"reiniciar antes de una corrida larga.")
        L.append("sin reinicio pendiente de Windows")
        ok, texto = chequeo_congelados_R()
        L.append(f"congelados de la campaña al empezar (PROTOCOLO_L0_L2.md:210): {texto}")
        if not ok:
            raise SystemExit("PARAR: el chequeo de congelados no dio 'IGUAL a lo probado'.")
    for x in L:
        log("  " + x)
    return L


def finales_R(modo: str, huella_q: str, huella_r: str, log: Callable[[str], None]
              ) -> List[str]:
    """
    Al terminar se repiten las huellas, las copias del Exp O, el stack, los
    crudos del Exp Q, el árbol, los congelados y los procesos (y, en
    `experimento`, el manifiesto pre); la energía se registra.
    """
    if Q.huella_codigo() != huella_q or huella_R() != huella_r:
        raise SystemExit("PARAR: el código cambió durante la corrida.")
    L = ["AL TERMINAR:"]
    Q.verificar_copias()
    L.append("  copias del Exp O iguales")
    L.append("  " + exigir_stack_R())
    L += ["  " + sha256_intactos_R()[0]] + ["  " + x for x in revisar_arbol_R()]
    if modo in ("control", "pasabilidad", "experimento"):
        ok, texto = chequeo_congelados_R()
        L.append(f"  congelados de la campaña al terminar: {texto}")
        if not ok:
            raise SystemExit("PARAR: el chequeo de congelados cambió durante la corrida.")
        procesos: List[str] = []
        _procesos_o_parar_R(procesos)
        L += ["  " + x for x in procesos]
        L.append("  " + corriente_alterna_R()[1])
    if modo == "experimento":
        motivos = motivos_manifiesto_R(DIR_RES_R, _CARPETA_R, huella_r)
        if motivos:
            raise SystemExit(f"PARAR: el manifiesto pre ya no vale al terminar: {motivos}")
        L.append("  manifiesto pre: todas sus entradas con el sha256 actual")
    L.append(f"  fin {datetime.now():%Y-%m-%d %H:%M:%S}")
    for x in L:
        log(x)
    return L


def arbol(log: Callable[[str], None]) -> None:
    """La referencia del árbol del Exp Q, UNA vez, con sus manifiestos al 100 %."""
    if RUTA_ARBOL_REF_R.exists():
        raise SystemExit(f"PARAR: {RUTA_ARBOL_REF_R.name} ya existe; no se reescribe.")
    actual = arbol_expq_R()
    cubiertos = set()
    for rel in MANIFIESTOS_Q_R:
        entradas = _leer_manifiesto_R(_CARPETA_Q / rel)
        malas = [r for r, h in entradas.items() if actual.get(r) != h]
        log(f"  {rel}: {len(entradas) - len(malas)}/{len(entradas)} IGUAL")
        if malas:
            raise SystemExit(f"PARAR: {rel} no coincide: {malas[:10]}")
        cubiertos |= set(entradas)
    fuera = sorted(set(actual) - cubiertos - set(MANIFIESTOS_Q_R))
    L = [f"{h} *./{r}" for r, h in actual.items()]
    L.append(f"ARCHIVOS {len(actual)}; fuera de los manifiestos del Exp Q: {len(fuera)}")
    L += [f"  fuera: {r}" for r in fuera]
    DIR_RES_R.mkdir(parents=True, exist_ok=True)
    RUTA_ARBOL_REF_R.write_bytes(("\n".join(L) + "\n").encode("utf-8"))
    log(f"  {RUTA_ARBOL_REF_R.name}: {len(actual)} archivos; {len(fuera)} fuera de los "
        f"manifiestos del Exp Q")


def diagnosticar_R(claves: Sequence[Tuple[str, int]], filas_r: Sequence[Dict[str, str]],
                   refs: Dict[Tuple[str, int], Dict[str, str]]) -> List[str]:
    """
    Hasta 10 episodios que no reproducen se recorren con `Q._tarea_Q` en un
    proceso nuevo: si Q da lo mismo que R y distinto del CSV, la REFERENCIA no
    se reproduce (o derivó el entorno); si Q da el CSV y R no, la falla es de R.
    """
    propias = {(str(f["condicion"]), int(f["seed_ep"])): f for f in filas_r}
    L = [f"    diagnóstico de {min(10, len(claves))} de {len(claves)} episodios que no "
         f"reproducen"]
    with ProcessPoolExecutor(max_workers=1, initializer=_inicializar_trabajador) as ex:
        for clave in claves[:10]:
            cond_nombre, semilla = clave
            k, tipo = cond_nombre.split("_", 1)
            fq = ex.submit(Q._tarea_Q, (CondicionQ(cond_nombre, k, tipo), semilla)).result()
            ref = refs[clave]
            cols = [c for c in ref if c not in ("t_episodio_s", "exploratorio")]
            q_ref = all(_serial(fq[c]) == ref[c] for c in cols)
            f = propias.get(clave)
            q_r = f is not None and all(_serial(fq[c]) == f[c] for c in cols)
            veredicto = ("falla de R" if q_ref and not q_r else
                         "la REFERENCIA no se reproduce, o derivó el entorno (Q da lo mismo "
                         "que R)" if q_r else
                         "ni Q ni R dan la referencia, y difieren entre sí")
            L.append(f"    diagnóstico {clave}: Q==CSV {q_ref}, Q==R {q_r} → {veredicto}")
    return L


def control(n_trab: int, huella_q: str, huella_r: str, previos: List[str],
            log: Callable[[str], None]) -> None:
    """Los 1200 episodios ya vistos por `correr_episodio_R`, bit a bit."""
    motivo = _aprobado_R(RUTA_AST_R, lineas_ast_requeridas_R(huella_r, _CARPETA_R))
    if motivo:
        raise SystemExit(f"PARAR: {motivo}. Correr antes comparar_ast_R.py con este código.")
    linea_prereg = exigir_prerregistro_fijado_R()
    firmas = [f"HUELLA_Q {huella_q}", f"HUELLA_R {huella_r}", linea_prereg, linea_entorno_R()]
    L: List[str] = ["CONTROL — Exp R"] + previos
    try:
        log("  CONTROL bit a bit sobre los 1200 episodios vistos…")
        conds = [CondicionQ(f"{k}_{t}", k, t) for k in NIVELES_R for t in Q.TIPOS_Q]
        filas = correr_condiciones_R(conds, n_trab, PREFIJO_CONTROL_R, huella_q, huella_r,
                                     Q.semillas_protocolo(), DIR_PARCIALES_R, DIR_TRAZAS_R,
                                     log, compuerta_energia_R(log))
        escribir_csv_R(filas, RUTA_CONTROL_CSV_R)
        i1, n1, c1, m1, k1 = comparar_filas_R(filas, RUTA_CSV_Q_S1, ("t_episodio_s",))
        i2, n2, c2, m2, k2 = comparar_filas_R(filas, RUTA_CSV_EXPL_Q,
                                              ("t_episodio_s", "exploratorio"))
        distintas = {(str(f["condicion"]), int(f["seed_ep"])) for f in filas}
        cubre = len(filas) == len(distintas) == n1 + n2 == 1200
        auto, resumen = autochequeos_filas_R(filas)
        traz, n_traz = biyeccion_trazas_R(filas, PREFIJO_CONTROL_R, DIR_TRAZAS_R)
        ok = not m1 and not m2 and i1 == n1 and i2 == n2 and cubre
        L += [f"CONTROL bit a bit (correr_episodio_R, semillas 420000–420099): "
              f"{len(distintas)} episodios distintos; {i1}/{n1} filas idénticas en las {c1} "
              f"columnas de experimento_Q_completo.csv (S1) y {i2}/{n2} en las {c2} de "
              f"experimento_Q_EXPLORATORIO_S2_S3.csv (S2, S3); todas salvo t_episodio_s y "
              f"exploratorio; texto idéntico, repr de cada float",
              f"  de los 1200, 1100 se reproducen por PRIMERA vez: antes sólo S1_din se había "
              f"recalculado (reproducción del exploratorio, 19-10)"]
        L += [f"    S1: {m}" for m in m1[:10]] + [f"    exploratorio: {m}" for m in m2[:10]]
        if m1 or m2:
            refs = {(r["condicion"], int(r["seed_ep"])): r
                    for ruta in (RUTA_CSV_Q_S1, RUTA_CSV_EXPL_Q) for r in _leer_csv(ruta)}
            L += diagnosticar_R(k1 + k2, filas, refs)
        L += resumen
        L.append(f"TRAZAS: {n_traz} episodios con traza (fallback, contacto o d_min < 0,10 m "
                 f"en celdas con obstáculo físico); biyección y tamaño → {len(traz)} problemas")
        for x in L[len(previos) + 1:]:
            log("  " + x)
        L += finales_R("control", huella_q, huella_r, log)
        # Los veredictos van DESPUÉS de los chequeos finales: si alguno falla,
        # el registro no puede quedar con 'CONTROL: OK'.
        veredictos = (["CONTROL: OK" if ok else "CONTROL: NO REPRODUCE"]
                      + lineas_parte_b_R(auto, traz))
        L += veredictos
        for x in veredictos:
            log("  " + x)
    except BaseException as e:
        L.append(f"CONTROL: NO (excepción: {e!r})")
        try:
            _escribir_registro_R(RUTA_CONTROL_TXT_R, L, huella_q, huella_r, firmas)
        except BaseException as e2:
            log(f"  no se pudo escribir {RUTA_CONTROL_TXT_R.name}: {e2!r}")
        raise
    _escribir_registro_R(RUTA_CONTROL_TXT_R, L, huella_q, huella_r, firmas)
    if not ok:
        raise SystemExit("PARAR: el control no reproduce (ver el diagnóstico).")


def pasabilidad(n_trab: int, huella_q: str, huella_r: str, previos: List[str],
                log: Callable[[str], None]) -> None:
    """Pasabilidad de S1–S3 en las 400 semillas nuevas y los 501 instantes (criterio de Q)."""
    semillas = semillas_R()
    linea_prereg = exigir_prerregistro_fijado_R()
    L = ["PASABILIDAD — Exp R"] + previos + [
        f"PASABILIDAD a lo largo de la trayectoria (huecos y conexidad, rejilla 0,01, "
        f"en cada instante 0..500 de las {len(semillas)} semillas {semillas[0]}–"
        f"{semillas[-1]}; chequeo exacto del Exp O, rejilla 0,005, en el peor instante "
        f"de cada semilla; `Q._pasabilidad_semilla` y el criterio de `Q.pasabilidad`):"]
    malos: List[str] = []
    compuerta = compuerta_energia_R(log)
    for k in NIVELES_R:
        compuerta(f"pasab. {k}")
        t0 = time.perf_counter()
        with ProcessPoolExecutor(max_workers=n_trab) as ex:
            res = list(ex.map(_pasabilidad_semilla, [(k, s) for s in semillas], chunksize=4))
        gw_an, go_an = Q.peor_caso_analitico(k)
        fallos = [f for r in res for f in r["fallos"]]
        ok = not fallos and min(gw_an, go_an) > Q.UMBRAL_PASO_ESC
        L.append(
            f"  {k}: peor caso analítico pared {gw_an:.4f} m, obst–obst {go_an:.4f} m; "
            f"en las semillas pared {min(r['gw'] for r in res):.4f} m, obst–obst "
            f"{min(r['go'] for r in res):.4f} m; área h≥0 (0,01) "
            f"{min(r['a0'][0] for r in res):.6f}–{max(r['a0'][1] for r in res):.6f} m², "
            f"h≥0,06 {min(r['a6'][0] for r in res):.6f}–{max(r['a6'][1] for r in res):.6f} m²; "
            f"exacta en el peor instante h≥0 "
            f"{min(r['exacta'][0] for r in res):.6f}–{max(r['exacta'][0] for r in res):.6f} m², "
            f"h≥0,06 {min(r['exacta'][1] for r in res):.6f}–{max(r['exacta'][1] for r in res):.6f} m²; "
            f"instantes evaluados {len(res) * (Q.MAX_STEPS + 1)}, fallidos {len(fallos)} "
            f"→ {'PASABLE' if ok else 'NO PASABLE'} ({time.perf_counter() - t0:.0f} s)")
        log(L[-1])
        if not ok:
            malos.append(k)
            L += ["    " + f for f in fallos[:10]]
    L.append("PASABILIDAD: " + ("NO PASA" if malos else "OK"))
    L += finales_R("pasabilidad", huella_q, huella_r, log)
    _escribir_registro_R(RUTA_PASAB_TXT_R, L, huella_q, huella_r,
                         [f"HUELLA_Q {huella_q}", linea_semillas_R(semillas), linea_prereg])
    if malos:
        raise SystemExit(f"PARAR: {malos} no pasable con las semillas nuevas. No se "
                         f"cambian niveles ni semillas sin reabrir el prerregistro.")


def manifiesto(huella_q: str, huella_r: str, log: Callable[[str], None]) -> None:
    """sha256 de todo lo de la carpeta (salvo los logs) y las dos huellas, ANTES de
    correr ninguna semilla nueva (se niega si ya hay resultados de `experimento`)."""
    linea_prereg = exigir_prerregistro_fijado_R()
    ya = resultados_de_R_existentes(DIR_RES_R)
    if ya:
        raise SystemExit(f"PARAR: ya hay resultados de experimento ({ya[:5]}…); el "
                         f"manifiesto pre no se rehace después de correr semillas nuevas.")
    motivos = [m for m in (
        _aprobado_R(RUTA_AST_R, lineas_ast_requeridas_R(huella_r, _CARPETA_R)),
        _aprobado_R(RUTA_CONTROL_TXT_R, ["CONTROL: OK", f"HUELLA_R {huella_r}", linea_prereg]),
        _aprobado_R(RUTA_PASAB_TXT_R, ["PASABILIDAD: OK", f"HUELLA_Q {huella_q}",
                                       linea_semillas_R(semillas_R()), linea_prereg])) if m]
    motivos += [f"falta {r}" for r in REQUERIDOS_MANIFIESTO_R if not (_CARPETA_R / r).exists()]
    if motivos:
        raise SystemExit(f"PARAR: {motivos}")
    ruta = DIR_RES_R / f"manifiesto_R_pre_{datetime.now():%Y%m%d_%H%M}.txt"
    if ruta.exists():
        raise SystemExit(f"PARAR: {ruta.name} ya existe.")
    archivos = [p for p in sorted(_CARPETA_R.rglob("*"))
                if p.is_file() and not p.name.startswith("corrida_R_")
                and not p.name.startswith("manifiesto_R_pre_")]
    L = [f"{sha256_archivo_R(p)} *./{p.relative_to(_CARPETA_R).as_posix()}" for p in archivos]
    L += [f"ARCHIVOS {len(archivos)} (sin los logs corrida_R_*)", linea_prereg,
          f"HUELLA_Q {huella_q}", f"HUELLA_R {huella_r}",
          f"fecha {datetime.now():%Y-%m-%d %H:%M:%S}"]
    ruta.write_bytes(("\n".join(L) + "\n").encode("utf-8"))
    log(f"  {ruta.name}: {len(archivos)} archivos; desde aquí ninguno de ellos cambia "
        f"hasta que termine `experimento`")


def experimento(n_trab: int, huella_q: str, huella_r: str, previos: List[str],
                sin_parte_b: bool, log: Callable[[str], None]) -> None:
    """Las 12 celdas × 400 semillas nuevas, sin regla de parada."""
    semillas = semillas_R()
    linea_prereg = exigir_prerregistro_fijado_R()
    motivos = motivos_experimento_R(DIR_RES_R, _CARPETA_R, huella_q, huella_r, semillas,
                                    linea_prereg, linea_entorno_R(), sin_parte_b)
    if motivos:
        raise SystemExit("PARAR: experimento no puede correr:\n  " + "\n  ".join(motivos))
    informe = [ENCABEZADO_R] + previos + [
        linea_prereg,
        "manifiestos pre: " + ", ".join(p.name for p in manifiestos_R(DIR_RES_R))
        + f" (vale el último, {ultimo_manifiesto_R(DIR_RES_R).name}: todas sus entradas "
          f"con el sha256 actual)",
        f"semillas {semillas[0]}–{semillas[-1]} (n = {len(semillas)}), las mismas en las 12 "
        f"celdas; orden S1, S2, S3 y din, quieto, ctrl, sinvel",
        f"modo: {'SIN PARTE B (§7 del prerregistro)' if sin_parte_b else 'con la Parte B'}"]
    filas: List[Dict[str, str]] = []
    compuerta = compuerta_energia_R(log)
    for k in NIVELES_R:
        nuevas = correr_condiciones_R(Q.condiciones_nivel(k), n_trab, PREFIJO_EXP_R,
                                      huella_q, huella_r, semillas, DIR_PARCIALES_R,
                                      DIR_TRAZAS_R, log, compuerta)
        filas += nuevas
        for tipo in Q.TIPOS_Q:
            fk = [f for f in nuevas if f["tipo"] == tipo]
            sumas = "; ".join(f"{e} {int(sum(float(f[c]) for f in fk))}"
                              for c, e in CRITERIOS_FALLA)
            informe.append(
                f"{k}_{tipo}: cob_acc={np.mean([float(f['cobertura_accesible']) for f in fk]):.8f} "
                f"interv={np.mean([float(f['cbf_frac_interv']) for f in fk]):.6f} "
                f"t/ep={np.mean([float(f['t_episodio_s']) for f in fk]):.2f} s; criterios "
                f"(se miden, no detienen) — {sumas}")
            log("  " + informe[-1])
    distintas = {(str(f["condicion"]), int(f["seed_ep"])) for f in filas}
    completo = len(filas) == len(distintas) == 12 * len(semillas)
    informe.append(f"FILAS: {len(filas)} ({len(distintas)} distintas; esperadas "
                   f"{12 * len(semillas)})")
    if not completo:
        log("  " + informe[-1])
        raise SystemExit("PARAR: las filas no cierran; no se escribe el CSV completo.")
    auto, resumen = autochequeos_filas_R(filas)
    traz, n_traz = biyeccion_trazas_R(filas, PREFIJO_EXP_R, DIR_TRAZAS_R)
    informe += resumen
    informe.append(f"TRAZAS: {n_traz} episodios con traza; biyección y tamaño → "
                   f"{len(traz)} problemas")
    parte_b = lineas_parte_b_R(auto, traz, sin_parte_b)
    informe += parte_b
    for x in resumen + informe[-(len(parte_b) + 1):]:
        log("  " + x)
    informe += finales_R("experimento", huella_q, huella_r, log)
    informe.append("logs de los tramos: " + ", ".join(
        sorted(p.name for p in DIR_RES_R.glob("corrida_R_experimento_*.log"))))
    escribir_csv_R([{"prerregistrado": 1, **f} for f in filas], RUTA_CSV_R)
    _escribir_registro_R(RUTA_REG_R, informe, huella_q, huella_r,
                         [f"HUELLA_Q {huella_q}", f"HUELLA_R {huella_r}", linea_prereg])
    log(f"  CSV → {RUTA_CSV_R} ({len(filas)} filas)")


def main() -> None:
    modos = ("arbol", "control", "pasabilidad", "manifiesto", "experimento")
    modo = sys.argv[1] if len(sys.argv) > 1 else ""
    extra = sys.argv[2:]
    if modo not in modos or (extra and (modo, extra) != ("experimento", ["--sin-parte-b"])):
        raise SystemExit("uso: python -B correr_experimento_R.py {" + "|".join(modos) + "}"
                         " [--sin-parte-b sólo con experimento]")
    DIR_RES_R.mkdir(parents=True, exist_ok=True)
    log = RegistroTramo(DIR_RES_R / f"corrida_R_{modo}_{datetime.now():%Y%m%d_%H%M%S}.log")
    try:
        n_trab = max(1, (os.cpu_count() or 2) - 1)
        # Las huellas se toman AL EMPEZAR; cada parcial y cada registro
        # comprueban que no cambiaron.
        huella_q = Q.huella_codigo()
        if huella_q != HUELLA_Q_ESPERADA:
            raise SystemExit(f"PARAR: la huella del Exp Q es {huella_q}, no {HUELLA_Q_ESPERADA}.")
        huella_r = huella_R()
        log("═" * 74)
        log(f"  EXPERIMENTO R — réplica prerregistrada ({modo})")
        log("═" * 74)
        previos = previos_R(modo, huella_q, huella_r, n_trab, log)
        if modo == "arbol":
            arbol(log)
        elif modo == "control":
            control(n_trab, huella_q, huella_r, previos, log)
        elif modo == "pasabilidad":
            pasabilidad(n_trab, huella_q, huella_r, previos, log)
        elif modo == "manifiesto":
            manifiesto(huella_q, huella_r, log)
        else:
            experimento(n_trab, huella_q, huella_r, previos, extra == ["--sin-parte-b"], log)
        log(f"fin {datetime.now():%Y-%m-%d %H:%M:%S}")
    except BaseException as e:
        # Cualquier PARAR o excepción queda en el log del tramo, con su traza.
        log(f"TERMINÓ CON {type(e).__name__}: {e}")
        if not isinstance(e, SystemExit):
            log(traceback.format_exc())
        raise


#: La huella con que se cargó este módulo (en cada trabajador spawn, la del
#: código que leyó del disco al crear el pool).
_HUELLA_AL_IMPORTAR_R: str = huella_R()


if __name__ == "__main__":
    main()
