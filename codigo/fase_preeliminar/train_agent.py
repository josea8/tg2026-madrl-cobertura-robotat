import gymnasium
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
import supersuit as ss
from tesis_env import PololuCoverageEnv

def train():
    # 1. Instanciar entorno
    env = PololuCoverageEnv()
    
    # 2. Wrapper "SuperSuit": Convierte Multi-Agente -> Vectorizado (Compatible con SB3)
    # Esto hace que PPO crea que está entrenando un solo "super-agente" que controla a los 3
    env = ss.pettingzoo_env_to_vec_env_v1(env)
    
    # 3. Concatenar para acelerar (opcional, bueno para escalar)
    env = ss.concat_vec_envs_v1(env, 1, num_cpus=1, base_class='stable_baselines3')

    # 4. Definir el modelo (PPO)
    model = PPO(
        "MlpPolicy",    # Red Neuronal Perceptrón Multicapa (básica)
        env, 
        verbose=1, 
        learning_rate=1e-3,
        batch_size=256
    )

    print("Iniciando entrenamiento de la tesis...")
    # 5. Entrenar (Prueba con 50,000 pasos para empezar)
    model.learn(total_timesteps=50000)
    
    # 6. Guardar el cerebro
    model.save("modelo_tesis_v1")
    print("¡Entrenamiento finalizado y modelo guardado!")

if __name__ == "__main__":
    train()