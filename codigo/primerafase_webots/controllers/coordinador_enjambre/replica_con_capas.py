"""
replica_con_capas.py — réplica pareada de una sesión de evaluación física
con la MISMA pila que corrió en el laboratorio, contra el simulador local.

SOLO ESCRITORIO. No toca el laboratorio ni la calibración guardada.
⚠ Corre a ritmo real (10 Hz) y usa CPU: NO correrla en la PC que está
llevando una sesión con robots, porque le roba tiempo a ese lazo de control.

Por qué: la réplica de la sesión (`_replica_simulada`) corre el env de
entrenamiento SIN CBF ni escape. Si esas capas aportan cobertura, la réplica
queda sesgada a la baja y la diferencia hw − sim sale optimista. Esto corre
lo mismo que el hardware —política + CBF + escape, `CoordinadorEnjambre` con
los adaptadores del Robotat, ritmo real de 10 Hz, factor 0.40, misma rampa—
pero con `SimuladorRobotat` (cinemática ideal, retardo de actuación cero) en
lugar de los robots.

Pareo, por episodio válido:
  · misma semilla (hotspots y trayectoria del campo),
  · misma pose inicial MEDIDA (x0/y0/th0 del CSV de episodios), llevada al
    marco lab invirtiendo la cadena exacta de la fuente
    (cuaternión → heading_desde_cuaternion → lab_a_env con el offset de rumbo
    de cada robot); el ida y vuelta se verifica midiendo,
  · misma rampa de arranque. El canal la aplica a las primeras
    `DECISIONES_ARRANQUE` decisiones de TODA la sesión: `decisiones_enviadas`
    no se reinicia entre episodios, y cada decisión es exactamente un
    `enviar_acciones`. Por eso se reconstruye del CSV: al arrancar un
    episodio, el canal ya había enviado la suma de la columna `decisiones` de
    todos los episodios anteriores, válidos o no (los rechazados por el
    chequeo de colocación no corrieron y no suman). El 11-09 eso da rampa
    completa en el ep 1 y ninguna en los demás, igual que antes; en otra
    sesión un primer episodio abortado a mitad de la rampa se la pasa al
    siguiente, y la réplica lo reproduce.

Qué sesión se replica: `--episodios-csv` (por defecto la del 11-09, la de los
números citados). La sesión de origen queda en el nombre de la salida
(`…_capas-on_de-AAAAMMDD.csv`) y en cada fila (`fuente_episodios`), que es lo
que usa `analizar_replicas.py --sesion` para no mezclar réplicas de sesiones
distintas.

Uso (las corridas citadas del 12-09-2026, en este orden):
    python replica_con_capas.py --capas on  --reps 3 --puerto 38830
    python replica_con_capas.py --capas off --reps 3 --puerto 28830
    python analizar_replicas.py

Otra sesión (la réplica SIN capas no hace falta repetirla: 15/15 salen de la
arena ya está establecido):
    python replica_con_capas.py --capas on --reps 3 --puerto 38830 \
        --episodios-csv AAAAMMDD_sesion-evaluacion_etapa7_episodios.csv
    python analizar_replicas.py --sesion AAAAMMDD_sesion-evaluacion_etapa7_episodios.csv

Chequeo previo, sin simulador ni política (ida y vuelta, composición, plan
de rampa por episodio):
    python replica_con_capas.py --capas on --verificar --episodios-csv ...

Salida: resultados_sesion/AAAAMMDD_sesion-replica_etapa7_capas-{on,off}_de-ORIGEN.csv
(`ruta_salida` no pisa: si el nombre existe, agrega sufijo). Las dos del
12-09 son anteriores a `_de-` y a `fuente_episodios`: son de la sesión del
11-09. Detalle y números en BITACORA_TECNICA.md, "Evaluación física
(2026-09-11)".
"""
import argparse
import csv
import math
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

CSV_POR_DEFECTO = "20260911_sesion-evaluacion_etapa7_episodios.csv"

ap = argparse.ArgumentParser()
ap.add_argument("--capas", choices=["on", "off"], required=True)
ap.add_argument("--reps", type=int, default=3)
ap.add_argument("--puerto", type=int, default=18830,
                help="puerto de poses; los robots usan puerto+260+id")
ap.add_argument("--episodios-csv", dest="episodios_csv",
                default=CSV_POR_DEFECTO,
                help="CSV de episodios de la sesión física a replicar: ruta, "
                     "o nombre dentro de resultados_sesion/. Por defecto "
                     f"{CSV_POR_DEFECTO} (la de los números citados).")
ap.add_argument("--verificar", action="store_true",
                help="sólo los chequeos previos (ida y vuelta, composición, "
                     "rampa); no levanta el simulador ni carga la política")
args = ap.parse_args()


def resolver_csv(nombre: str) -> Path:
    p = Path(nombre)
    for cand in (p, RAIZ / p, RAIZ / "resultados_sesion" / p.name):
        if cand.is_file():
            return cand.resolve()
    sys.exit(f"✘ no encuentro el CSV de episodios: {nombre}")


CSV_EP = resolver_csv(args.episodios_csv)
# Etiqueta corta de la sesión de origen para el nombre de la salida:
# "20260922_sesion-evaluacion_etapa7_episodios_02" → "20260922_02".
ORIGEN = CSV_EP.stem.replace("_sesion-evaluacion_etapa7_episodios", "")

import numpy as np                                               # noqa: E402
import config_robotat as cfg                                     # noqa: E402
import calibracion_sesion as calib                               # noqa: E402

PUERTO_POSES = args.puerto
PUERTO_BASE = args.puerto + 260
cfg.activar_simulador_local(puerto_poses=PUERTO_POSES, puerto_base=PUERTO_BASE)
aplicados = calib.aplicar_a_config()          # sólo LEE el JSON medido

# ⚠ La calibración del LABORATORIO no vale en el simulador. El offset de rumbo
# (~92°) existe porque en los robots reales la constelación está montada
# girada respecto del chasis; el simulador emite el rumbo del chasis tal cual.
# Con la calibración del lab, la pila le sumaba 92° a un rumbo ya correcto:
# la política y el CBF razonaban sobre una dirección que no era la de avance
# y los robots se salían de la arena (primer intento, descartado). La escala
# 1.0167 además inflaba 1.7 % las velocidades. En el simulador el marco lab
# ES métrico y alineado: calibración identidad, como en `PruebaEvaluacion`.
# `aplicar_a_config()` se llama igual, por las banderas de "verificado".
cfg.ESCALA_POSICION = 1.0
cfg.ROTACION_MARCO_RAD = 0.0
cfg.TRASLACION_X_M = 1.5
cfg.TRASLACION_Y_M = 1.5
cfg.OFFSET_HEADING_RAD = 0.0
cfg.offset_rumbo_de_robot = lambda _id_robot: 0.0

N = len(cfg.MAPEO_AGENTES)

print(f"capas = {args.capas.upper()}  reps={args.reps}  puertos "
      f"{PUERTO_POSES}/{PUERTO_BASE}+id")
print(f"sesión de origen: {CSV_EP.name}  (etiqueta '{ORIGEN}')")
print(f"calibración aplicada: {aplicados}")
print(f"  escala {cfg.ESCALA_POSICION:.6f}  rot {math.degrees(cfg.ROTACION_MARCO_RAD):+.3f}°  "
      f"tras ({cfg.TRASLACION_X_M:.4f}, {cfg.TRASLACION_Y_M:.4f})")

# ── episodios del laboratorio ───────────────────────────────────────────────
todas = list(csv.DictReader(open(CSV_EP, encoding="utf-8")))
validos = [r for r in todas if r["valido"] == "1"]
print(f"episodios válidos a replicar: {[r['episodio'] for r in validos]}"
      f"  (de {len(todas)} intentos)")
if not validos:
    sys.exit("✘ la sesión no tiene episodios válidos: no hay nada que replicar")
# Régimen del laboratorio, del propio CSV (revisión del 2026-09-22: estaban
# fijos en 500 / 0.40 / 200 y una sesión corrida con otros valores quedaba
# mal pareada en silencio).
#  · decisiones: un episodio válido corre el lazo completo, así que su
#    columna `decisiones` ES el --decisiones de la sesión;
#  · factor y rpm_aborto: columnas desde el 2026-09-22; las sesiones
#    anteriores se corrieron con 0.40 y 200 (bitácora), y se avisa.
largos = {int(float(r["decisiones"])) for r in validos}
if len(largos) != 1:
    sys.exit(f"✘ episodios válidos con largos distintos: {sorted(largos)}")
DECISIONES = largos.pop()


def _regimen(clave, legado):
    vals = {float(r[clave]) for r in validos if r.get(clave) not in (None, "")}
    if not vals:
        print(f"  ⓘ el CSV no registra '{clave}' (anterior al 2026-09-22): "
              f"se usa {legado}, el de esas sesiones")
        return legado
    if len(vals) != 1:
        sys.exit(f"✘ '{clave}' distinto entre episodios válidos: {sorted(vals)}")
    return vals.pop()


FACTOR = _regimen("factor", 0.40)
RPM_ABORTO = _regimen("rpm_aborto", 200.0)
print(f"régimen del laboratorio: {DECISIONES} decisiones · factor {FACTOR:.2f}"
      f" · aborto {RPM_ABORTO:.0f} rpm")

faltan = [(r["episodio"], i) for r in validos for i in range(N)
          if r.get(f"x0_a{i}") in (None, "")]
if faltan:
    sys.exit(f"✘ al CSV le faltan poses iniciales para {N} agentes "
             f"(episodio, agente): {faltan[:5]}. ¿Se corrió con --agentes?")

# Composición con que se midió: columnas `robot_a{i}` desde el 2026-09-22.
con_comp = next((r for r in todas if r.get("robot_a0") not in (None, "")),
                None)
if con_comp is None:
    robots_hw = "—"
    print("composición del hardware: el CSV no la registra (anterior al "
          "2026-09-22; la sesión del 11-09 fue con los robots 1, 2, 3, 6, 9)")
else:
    ids_hw = [int(float(con_comp[f"robot_a{i}"])) for i in range(N)]
    robots_hw = "-".join(str(r) for r in ids_hw)
    print(f"composición del hardware: robots {ids_hw}")
    print("  offsets de rumbo con que se midió: " + "  ".join(
        f"r{ids_hw[i]} {float(con_comp[f'offset_deg_a{i}']):+.2f}°"
        for i in range(N) if con_comp.get(f"offset_deg_a{i}") not in (None, "")))
    ids_cfg = [cfg.MAPEO_AGENTES[i].id_robot for i in range(N)]
    if ids_hw != ids_cfg:
        print(f"  ⓘ el mapeo actual es {ids_cfg}. No cambia la réplica "
              "(calibración identidad, sin offset de montaje): sólo el nombre "
              "de los robots simulados.")


def decisiones_previas(ep: int) -> int:
    """Decisiones que el canal ya había enviado al arrancar el episodio `ep`."""
    return sum(int(float(r["decisiones"])) for r in todas
               if int(r["episodio"]) < ep
               and r.get("decisiones") not in (None, ""))


print("rampa de arranque (decisiones previas del canal → decisiones con rampa):")
for fila in validos:
    ep = int(fila["episodio"])
    prev = decisiones_previas(ep)
    n_rampa = (max(0, cfg.DECISIONES_ARRANQUE - prev)
               if cfg.ARRANQUE_SEGURO else 0)
    print(f"  ep {ep:>2}: {prev:5d} previas → {n_rampa:2d} con rampa")


def env_a_lab(x, y, th, id_robot):
    """Inversa exacta de lab_a_env + heading del cuaternión del simulador."""
    c, s = math.cos(cfg.ROTACION_MARCO_RAD), math.sin(cfg.ROTACION_MARCO_RAD)
    dx, dy = x - cfg.TRASLACION_X_M, y - cfg.TRASLACION_Y_M
    xs, ys = c * dx + s * dy, -s * dx + c * dy
    yaw = th - cfg.ROTACION_MARCO_RAD - cfg.offset_rumbo_de_robot(id_robot)
    yaw = math.atan2(math.sin(yaw), math.cos(yaw))
    return xs / cfg.ESCALA_POSICION, ys / cfg.ESCALA_POSICION, yaw


def objetivo_env(fila):
    return {i: np.array([float(fila[f"x0_a{i}"]), float(fila[f"y0_a{i}"]),
                         float(fila[f"th0_a{i}"])]) for i in range(N)}


def poses_lab(fila):
    obj = objetivo_env(fila)
    return {cfg.MAPEO_AGENTES[i].id_robot:
            env_a_lab(*obj[i], cfg.MAPEO_AGENTES[i].id_robot)
            for i in range(N)}


def numero(v):
    return float(v) if v not in (None, "") else None


# Verificación analítica del ida y vuelta, antes de levantar nada.
from protocolo_robotat import lab_a_env, heading_desde_cuaternion  # noqa: E402
peor = 0.0
for fila in validos:
    obj = objetivo_env(fila)
    for i in range(N):
        rid = cfg.MAPEO_AGENTES[i].id_robot
        xl, yl, yaw = env_a_lab(*obj[i], rid)
        yq, _ = heading_desde_cuaternion(math.cos(yaw / 2), 0.0, 0.0,
                                         math.sin(yaw / 2))
        e = lab_a_env(xl, yl, yq, cfg.offset_rumbo_de_robot(rid))
        dth = math.atan2(math.sin(e[2] - obj[i][2]), math.cos(e[2] - obj[i][2]))
        peor = max(peor, abs(e[0] - obj[i][0]), abs(e[1] - obj[i][1]), abs(dth))
print(f"ida y vuelta analítico env→lab→env: error máx {peor:.2e}")
assert peor < 1e-9

if args.verificar:
    print("\n--verificar: chequeos OK; no se levanta el simulador.")
    sys.exit(0)

import coordinador_enjambre as ce                                # noqa: E402
ce.CBF_ACTIVO = (args.capas == "on")
ce.ESCAPE_ACTIVO = (args.capas == "on")
print(f"capas: CBF={ce.CBF_ACTIVO} escape={ce.ESCAPE_ACTIVO}")

import sesion_robotat as ses                                     # noqa: E402
from lanzar_robotat import construir, leer_poses_estables        # noqa: E402
from simulador_robotat import SimuladorRobotat                   # noqa: E402

# ── simulador + pila del laboratorio ────────────────────────────────────────
mapeo_real = {cfg.MAPEO_AGENTES[i].id_robot: cfg.MAPEO_AGENTES[i].id_marcador
              for i in range(N)}
sim = SimuladorRobotat(mapeo_real, poses_lab(validos[0]), None,
                       puerto_poses=PUERTO_POSES, puerto_base=PUERTO_BASE)
sim.iniciar()

fuente = canal = coord = None
resultados = []
try:
    fuente, canal, entorno = construir(N)
    coord = ce.CoordinadorEnjambre(fuente=fuente, canal=canal,
                                   entorno=entorno, n_agentes=N,
                                   timestep_ms=10)
    canal.factor_operativo = FACTOR

    registro = []
    estado = {"episodio": 0}

    def observador(d):          # copia del de `sesion_evaluacion`
        ag = int(d["agente"])
        registro.append({
            "episodio":      estado["episodio"],
            "agente":        ag,
            "robot":         cfg.MAPEO_AGENTES[ag].id_robot,
            "paso":          d["paso"],
            "pose_env_x":    float(d["pose_env"][0]),
            "pose_env_y":    float(d["pose_env"][1]),
            "pose_env_th":   float(d["pose_env"][2]),
            "v_ejecutada":   float(d["accion_ejecutada"][0]),
            "w_ejecutada":   float(d["accion_ejecutada"][1]),
            "en_escape":     int(d["en_escape"]),
            "cbf_intervino": int(d["cbf_intervino"]),
            "rpm_pico":      canal.ultimo_pico_rpm,
            "con_vecino":    int(any(abs(float(v)) > 1e-9
                                     for v in np.asarray(d["observacion"])[8:16])),
        })

    coord._observador_paso = observador

    for rep in range(1, args.reps + 1):
        for fila in validos:
            ep = int(fila["episodio"])
            semilla = int(float(fila["semilla"]))
            # Teletransporte SÓLO en el simulador, entre episodios.
            canal.detener_todo(silencioso=True)
            time.sleep(0.2)
            with sim._lock:
                for rid, (x, y, yaw) in poses_lab(fila).items():
                    est = sim.robots[rid]
                    est.x, est.y, est.yaw = x, y, yaw
                    est.rpm_izq = est.rpm_der = 0.0
            time.sleep(0.2)

            # Verificación medida: la pila tiene que ver la pose del lab.
            fuente.reiniciar()
            medidas = leer_poses_estables(fuente, N)
            obj = objetivo_env(fila)
            err = max(float(np.linalg.norm(medidas[i][:2] - obj[i][:2]))
                      for i in range(N))

            # Rampa: la que tuvo ESTE episodio en el laboratorio.
            previas = decisiones_previas(ep)
            canal.decisiones_enviadas = previas

            estado["episodio"] = ep
            marca = len(registro)
            detector = ses.DetectorCongelamiento()
            seguimiento = ses.DetectorSeguimiento()
            entorno.reiniciar_reloj()
            if not coord._reiniciar_episodio(semilla):
                print(f"rep {rep} ep {ep}: no se pudo iniciar")
                continue
            res = ses._correr_episodio(coord, canal, fuente, registro, marca,
                                       DECISIONES, RPM_ABORTO, N, detector,
                                       semilla, seguimiento)
            fila_out = {
                "capas": args.capas, "rep": rep, "episodio": ep,
                "semilla": semilla, "error_pose_inicial_m": err,
                "fuente_episodios": CSV_EP.name,
                "robots_hw": robots_hw,
                "decisiones_previas": previas,
                "decisiones_episodio": DECISIONES,
                "factor": FACTOR,
                "rpm_aborto": RPM_ABORTO,
                "cobertura_hw": float(fila["cobertura_aoi"]),
                "cobertura_replica_sin_capas": numero(
                    fila.get("cobertura_replica")),
            }
            for k in ("valido", "motivo", "cobertura_aoi", "colisiones_015",
                      "colisiones_022", "d_pared_min", "viola_018", "frac_cbf",
                      "n_escape", "duracion_s", "ciclo_p95_ms",
                      "ciclos_sobre_100ms", "dist_min_robot", "dist_max_robot"):
                fila_out[k] = res.get(k)
            resultados.append(fila_out)
            print(f"rep {rep} ep {ep:>2}  sem {semilla}  pose ini err "
                  f"{err*1000:5.1f} mm  cobertura {res.get('cobertura_aoi')}"
                  f"  hw {float(fila['cobertura_aoi']):.4f}  "
                  f"dur {res.get('duracion_s')}  valido {res.get('valido')} "
                  f"{res.get('motivo') or ''}", flush=True)
finally:
    if canal is not None:
        try:
            canal.cerrar()
        except Exception:                                   # noqa: BLE001
            pass
    if fuente is not None:
        try:
            fuente.cerrar()
        except Exception:                                   # noqa: BLE001
            pass
    sim.detener()

pose_vieja = getattr(coord, "_decisiones_pose_vieja", None)
print(f"\ndecisiones con aviso de pose vieja en toda la corrida: {pose_vieja}")

salida = ses.ruta_salida("replica", 7, f"capas-{args.capas}_de-{ORIGEN}")
ses.escribir_csv(salida, resultados)
print(f"resultados → {salida}")
