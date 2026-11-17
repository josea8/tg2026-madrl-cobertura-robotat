"""
recomputar_referencia.py — cobertura de `modelo_PRIMERO` bajo el protocolo único.

La tabla comparativa del Experimento J no debe copiar la cifra 0.6813 del
reporte del estudio original: ésa se midió con 100 episodios y semillas
`42·10000+i`. Para comparar peras con peras, el modelo adoptado se re-evalúa
aquí con EXACTAMENTE el protocolo del experimento J — 30 episodios de semillas
`42·10000+1000+i` — que es el que produce los valores objetivo del estudio.

Se reporta además la cifra con el conjunto de retención (20 episodios, offset 0)
para cuantificar el desplazamiento entre ambos conjuntos.
"""
from __future__ import annotations
import json, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

DIR_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR_BASE))
import estudio_J as J

RUTA_MODELO = DIR_BASE.parent / "modelos/tesis_v1/RESULTADO_PRIMERO/modelo_PRIMERO.zip"
# Pesos con los que se entrenó modelo_PRIMERO (Trial 13)
PESOS = {"lambda_gradient": 0.5622468083379316, "lambda_entropy": 1.1403296484190344,
         "lambda_ibrm": 0.48380314172632155, "lambda_cbf": 2.9655314099141474}

def main() -> None:
    assert RUTA_MODELO.exists(), RUTA_MODELO
    salida = {}
    with ProcessPoolExecutor(max_workers=J.N_TRABAJADORES_EVAL,
                             initializer=J._iniciar_trabajador_eval,
                             initargs=(PESOS,)) as pool:
        for nombre, n_eps, offset in (
            ("conjunto_final_30eps",     J.N_EPS_FINAL,     J.OFFSET_SEMILLAS_FINAL),
            ("conjunto_retencion_20eps", J.N_EPS_RETENCION, 0),
            ("cien_episodios",           100,               0),
        ):
            res = J.evaluar_modelo_en_paralelo(RUTA_MODELO, pool, n_eps, offset=offset)
            ag = res["agregados"]
            salida[nombre] = {
                "n_episodios": n_eps, "offset": offset,
                "cobertura": ag["cobertura_aoi_final"]["media"],
                "std":       ag["cobertura_aoi_final"]["std"],
                "colisiones": ag["n_colisiones"]["media"],
            }
            print(f"{nombre:<26} cob={salida[nombre]['cobertura']:.8f} "
                  f"± {salida[nombre]['std']:.8f}   col={salida[nombre]['colisiones']:.4f}")
    ruta = DIR_BASE / "resultados" / "analisis" / "referencia_recomputada.json"
    ruta.write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n→ {ruta}")

if __name__ == "__main__":
    main()
