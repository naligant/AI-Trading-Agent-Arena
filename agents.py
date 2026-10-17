class Agent:
    def decide(self, obs) -> dict:
        """Return target weights: coin -> signed leverage (1.0 = 1x long)."""
        raise NotImplementedError


class HoldAgent(Agent):
    """Always holds the same weights. Useful to prove the sim loop runs."""

    def __init__(self, weights: dict):
        self.weights = dict(weights)

    def decide(self, obs):
        return dict(self.weights)
