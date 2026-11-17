import functools
import gymnasium
import numpy as np
from gymnasium.spaces import Box
from pettingzoo import ParallelEnv

class PololuCoverageEnv(ParallelEnv):
    metadata = {"render_modes": ["human"], "name": "pololu_v0"}

    def __init__(self, render_mode=None):
        # --- CONSTANTES FÍSICAS ---
        self.MAP_SIZE = 4.0
        self.NUM_ROBOTS = 3
        self.NUM_TARGETS = 3
        self.MAX_SPEED = 0.4
        self.DT = 0.1
        self.MAX_STEPS = 200
        
        self.possible_agents = [f"robot_{i}" for i in range(self.NUM_ROBOTS)]
        self.render_mode = render_mode
        
        # Espacios de acción y observación
        self.action_spaces = {agent: Box(low=-1, high=1, shape=(2,), dtype=np.float32) for agent in self.possible_agents}
        self.observation_spaces = {agent: Box(low=0, high=self.MAP_SIZE, shape=(4,), dtype=np.float32) for agent in self.possible_agents}

        # --- CORRECCIÓN CRÍTICA ---
        # Inicializamos las variables aquí para que siempre existan, 
        # evitando el AttributeError incluso si no se ha llamado a reset()
        self.robot_positions = {agent: np.zeros(2) for agent in self.possible_agents}
        self.target_positions = np.zeros((self.NUM_TARGETS, 2))

    def reset(self, seed=None, options=None):
        self.agents = self.possible_agents[:]
        self.steps = 0
        
        # Posiciones aleatorias
        self.robot_positions = {agent: np.random.rand(2) * self.MAP_SIZE for agent in self.agents}
        self.target_positions = np.random.rand(self.NUM_TARGETS, 2) * self.MAP_SIZE
        
        return self._get_obs(), {agent: {} for agent in self.agents}

    def step(self, actions):
        self.steps += 1
        rewards = {}
        terminations = {}
        truncations = {}
        infos = {}

        for agent in self.agents:
            if agent in actions:
                action = actions[agent]
                new_pos = self.robot_positions[agent] + action * self.MAX_SPEED * self.DT
                self.robot_positions[agent] = np.clip(new_pos, 0, self.MAP_SIZE)

        # Cálculo de recompensa simplificado para visualización
        for agent in self.agents:
            my_pos = self.robot_positions[agent]
            distances = [np.linalg.norm(my_pos - t_pos) for t_pos in self.target_positions]
            min_dist = min(distances) if distances else 0
            
            reward = -0.1 - min_dist
            if min_dist < 0.1: 
                reward += 10.0
            
            rewards[agent] = reward
            terminations[agent] = self.steps >= self.MAX_STEPS
            truncations[agent] = False
            infos[agent] = {}

        if self.steps >= self.MAX_STEPS:
            self.agents = []

        return self._get_obs(), rewards, terminations, truncations, infos

    def _get_obs(self):
        observations = {}
        for agent in self.agents:
            my_pos = self.robot_positions[agent]
            # Si no hay targets, usar (0,0) para evitar error
            if len(self.target_positions) > 0:
                distances = [np.linalg.norm(my_pos - t_pos) for t_pos in self.target_positions]
                nearest_target = self.target_positions[np.argmin(distances)]
            else:
                nearest_target = np.zeros(2)
            
            observations[agent] = np.concatenate([my_pos, nearest_target]).astype(np.float32)
        return observations

    def observation_space(self, agent):
        return self.observation_spaces[agent]

    def action_space(self, agent):
        return self.action_spaces[agent]

    # --- MÉTODO NUEVO PARA VISUALIZACIÓN ---
    def get_positions(self):
        """Retorna las posiciones actuales de forma limpia para el visualizador"""
        return self.robot_positions, self.target_positions