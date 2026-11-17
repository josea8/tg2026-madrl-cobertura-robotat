"""Verifica que la evaluación en paralelo da EXACTAMENTE los mismos números."""
import json, sys, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import estudio_J as J
from stable_baselines3 import PPO

def main() -> None:
    dir_s = Path("resultados/estudio/cfg_b54711973b/semilla_42")
    esperado = json.loads((dir_s / "resultado_semilla.json").read_text(encoding="utf-8"))
    ruta = dir_s / "mejor_punto_control.zip"
    pesos = {"lambda_gradient": 0.5622468083379316, "lambda_entropy": 1.9064,
             "lambda_ibrm": 0.48380314172632155, "lambda_cbf": 6.2436}
    cfg = json.loads(Path("resultados/estudio/cfg_b54711973b/resultado_prueba.json").read_text())["barridos"]
    pesos["lambda_entropy"] = cfg["lambda_entropy"]; pesos["lambda_cbf"] = cfg["lambda_cbf"]

    print(f"referencia (secuencial, ya medida): {esperado['cobertura_final']:.14f}")

    modelo = PPO.load(str(ruta), device="cpu")
    env = J.make_env(n_agents=5, arena_size=(3.0,3.0), max_steps=500, comm_radius=1.0,
                     reward_weights=pesos, domain_rand=False, seed=42)
    t0 = time.time()
    sec = J.evaluar_modelo(modelo, env, J.N_EPS_FINAL, offset=J.OFFSET_SEMILLAS_FINAL)
    t_sec = time.time() - t0
    print(f"secuencial ahora   : {sec['agregados']['cobertura_aoi_final']['media']:.14f}  ({t_sec:.1f} s)")

    for n in (5, 8, 10):
        with ProcessPoolExecutor(max_workers=n, initializer=J._iniciar_trabajador_eval,
                                 initargs=(pesos,)) as pool:
            pool.submit(int, 0).result()          # forzar arranque
            t0 = time.time()
            par = J.evaluar_modelo_en_paralelo(ruta, pool, J.N_EPS_FINAL,
                                               offset=J.OFFSET_SEMILLAS_FINAL)
            t_par = time.time() - t0
        v = par['agregados']['cobertura_aoi_final']['media']
        print(f"paralelo ({n} proc) : {v:.14f}  ({t_par:.1f} s)  "
              f"aceleración {t_sec/t_par:.2f}x")
        iguales = all(a == b for a, b in
                      zip([e['cobertura_aoi_final'] for e in sec['episodios']],
                          [e['cobertura_aoi_final'] for e in par['episodios']]))
        print(f"  ¿los 30 episodios son idénticos uno a uno? {iguales}")

if __name__ == "__main__":
    main()
