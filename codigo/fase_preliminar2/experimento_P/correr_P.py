"""
correr_P.py — Orquestador del Experimento P.

Secuencia (todo en SERIE: en esta máquina correr semillas de a dos fue entre
2 y 20 % más lento que en serie, según los registros del Exp J):

1. Condiciones: corriente alterna obligatoria (si se pierde, se PAUSA hasta
   recuperarla) y registro de la carga de CPU de fondo.
2. Controles (`controles_P.py`). Si alguno falla, se DETIENE todo sin ajustar
   nada.
3. Entrenamiento de las 20 semillas × 2 brazos con el modo trabajador de la
   copia de `estudio_J.py`, INTERCALANDO brazos (1001-ganadora,
   1001-trial13, 1002-ganadora, …). Los resultados no dependen del orden
   (el entrenamiento en CPU es determinista); intercalar sólo reparte entre
   brazos cualquier deriva en las condiciones de la máquina y deja datos
   balanceados si la corrida se interrumpe.
4. Evaluación auxiliar (`evaluar_P.py`) y análisis (`analizar_P.py`).

Reanudable: una semilla con `resultado_semilla.json` ya escrito no se
reentrena (mecanismo del propio `estudio_J`). Cada corrida queda en
`resultados/registro_corridas.jsonl` con su duración, carga y alimentación.

Uso:  python3 -B -u correr_P.py
      python3 -B -u correr_P.py --humo   (fontanería: 1 semilla por brazo,
                                          presupuesto diminuto, salida en
                                          $P_DIR_HUMO o resultados_humo/;
                                          NO es la corrida)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import comun_P as C

HUMO_ENV: Dict[str, str] = {"EXPJ_PRESUPUESTO": "6000", "EXPJ_FREQ_EVAL": "2000"}


def log(mensaje: str) -> None:
    print(f"{datetime.now().strftime('%H:%M:%S')} {mensaje}", flush=True)


def esperar_corriente_alterna() -> float:
    """Bloquea mientras la máquina esté a batería. Devuelve los segundos esperados."""
    t0 = time.time()
    avisado = False
    while not C.en_corriente_alterna():
        if not avisado:
            log("⚠ SIN CORRIENTE ALTERNA — en pausa hasta que se conecte")
            avisado = True
        time.sleep(30)
    if avisado:
        log("corriente alterna recuperada — se reanuda")
    return time.time() - t0


def ejecutar_script(nombre: str, extra: List[str]) -> int:
    cmd = [sys.executable, "-B", "-u", str(C.RAIZ_P / nombre)] + extra
    return subprocess.run(cmd, env=C.entorno_subproceso(), cwd=str(C.RAIZ_P)).returncode


def plan_corridas(humo: bool) -> List[Tuple[int, str]]:
    semillas = C.SEMILLAS[:1] if humo else C.SEMILLAS[:C.N_POR_BRAZO]
    return [(s, b) for s in semillas for b in C.BRAZOS]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--humo", action="store_true")
    args = parser.parse_args()

    dir_base = C.dir_base(args.humo)
    registro = dir_base / "registro_corridas.jsonl"

    # ── 1. Condiciones ──────────────────────────────────────────────────────
    if not C.RUTA_MANIFIESTO.exists():
        log("ABORTADO: falta manifiesto_P.json (correr preparar_P.py)")
        return 1
    esperar_corriente_alterna()
    carga_fondo = C.carga_cpu_pct(15.0)
    lanzamiento = {
        "evento": "lanzamiento", "humo": args.humo,
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "carga_fondo_15s_pct": carga_fondo, "bateria_status": C.estado_bateria(),
        "ac_line_status": C.linea_ca(),
        "variables_hilos": {k: os.environ.get(k) for k in
                            ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")},
        "scripts_P": {p.name: C.sha256_archivo(p) for p in sorted(C.RAIZ_P.glob("*.py"))},
        "preregistro_sha256": C.sha256_archivo(C.RAIZ_P / "PREREGISTRO_P.md"),
        "copias_lib": {str(p.relative_to(C.RAIZ_P)): C.sha256_archivo(p)
                       for p in sorted(C.DIR_LIB.rglob("*.py"))},
    }
    C.anexar_jsonl(registro, lanzamiento)
    log(f"carga de fondo (15 s): {carga_fondo:.1f} %" if carga_fondo is not None
        else "carga de fondo: no medida")

    # ── 2. Controles ────────────────────────────────────────────────────────
    log("controles: C1 (modelo_PRIMERO), C3 (heurística NN), C2 (semilla 42 bit a bit)")
    if ejecutar_script("controles_P.py", ["--humo"] if args.humo else []) != 0:
        log("✖ CONTROL FALLIDO — se detiene el Experimento P sin ajustar nada. "
            "Ver resultados/control/controles_P.json")
        C.anexar_jsonl(registro, {"evento": "detenido_por_control",
                                  "fecha": datetime.now().isoformat(timespec="seconds")})
        return 2
    log("controles aprobados")

    # ── 3. Entrenamiento, en serie e intercalado ────────────────────────────
    plan = plan_corridas(args.humo)
    for k, (semilla, brazo) in enumerate(plan, start=1):
        dir_semilla = dir_base / brazo / f"semilla_{semilla}"
        if (dir_semilla / "resultado_semilla.json").exists():
            log(f"[{k}/{len(plan)}] {brazo} s{semilla}: ya existe, se omite")
            continue
        espera = esperar_corriente_alterna()
        monitor = C.MonitorCarga()
        monitor.iniciar()
        inicio = datetime.now().isoformat(timespec="seconds")
        log(f"[{k}/{len(plan)}] {brazo} s{semilla}: entrenando")
        codigo, segundos = C.correr_trabajador(
            semilla, dir_semilla, C.CONFIGS[brazo],
            dir_base / "logs" / f"{brazo}_s{semilla}.log",
            humo=HUMO_ENV if args.humo else None)
        carga = monitor.detener()
        ok = codigo == 0 and (dir_semilla / "resultado_semilla.json").exists()
        C.anexar_jsonl(registro, {
            "evento": "semilla", "brazo": brazo, "semilla": semilla, "inicio": inicio,
            "fin": datetime.now().isoformat(timespec="seconds"), "segundos": segundos,
            "codigo_salida": codigo, "ok": ok, "espera_alterna_s": espera, **carga,
        })
        if ok:
            res = json.loads((dir_semilla / "resultado_semilla.json").read_text(encoding="utf-8"))
            log(f"    listo en {segundos:.0f} s — retenido {res['paso_retenido']}, "
                f"cob_final {res['cobertura_final']:.8f}, carga media "
                f"{carga['carga_media_pct'] if carga['carga_media_pct'] is not None else float('nan'):.0f} %")
        else:
            # Se registra y se sigue: una semilla fallida no invalida las demás.
            # Al final se informa; el análisis no la imputa.
            log(f"    ✖ FALLÓ (código {codigo}); se continúa con la siguiente")

    # ── 4. Evaluación auxiliar y análisis ───────────────────────────────────
    log("evaluación auxiliar (conjunto nuevo y paso fijo 200k)")
    if ejecutar_script("evaluar_P.py", ["--humo"] if args.humo else []) != 0:
        log("✖ la evaluación auxiliar falló")
        return 3
    log("análisis")
    if ejecutar_script("analizar_P.py", ["--humo"] if args.humo else []) != 0:
        log("✖ el análisis falló")
        return 4
    C.anexar_jsonl(registro, {"evento": "fin", "fecha": datetime.now().isoformat(timespec="seconds")})
    log("Experimento P terminado")
    (dir_base / "COMPLETADO").write_bytes(datetime.now().isoformat(timespec="seconds").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
