"""Metrics and evaluation for UN Deliberation Gym."""

from typing import List, Dict, Tuple
import numpy as np
from collections import defaultdict
from .spaces import State, Action


class EpisodeMetrics:
    """Track and compute metrics for gym episodes."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Reset all metrics."""
        self.episodes = []
        self.transitions = []

    def add_episode(
        self,
        trajectory: List[Tuple[State, Action, State, float, bool]],
        metadata: Dict = None,
    ):
        """
        Add an episode for tracking.

        Args:
            trajectory: List of (s, a, s', r, done) tuples
            metadata: Optional episode metadata (country, resolution_id, etc.)
        """
        self.episodes.append({
            'trajectory': trajectory,
            'metadata': metadata or {},
        })

        for s, a, s_next, r, done in trajectory:
            self.transitions.append((s, a, s_next, r, done))

    def compute_stats(self) -> Dict:
        """Compute summary statistics."""
        if not self.episodes:
            return {}

        stats = {
            'num_episodes': len(self.episodes),
            'num_transitions': len(self.transitions),
            'avg_episode_length': np.mean([len(ep['trajectory']) for ep in self.episodes]),
        }

        # Action distribution
        action_counts = defaultdict(int)
        for _, a, _, _, _ in self.transitions:
            if isinstance(a, State):
                continue  # Skip if State object (shouldn't happen)
            action_counts[Action(a).name] += 1

        stats['action_distribution'] = dict(action_counts)

        # Reward distribution
        rewards = [r for _, _, _, r, _ in self.transitions]
        stats['reward_mean'] = np.mean(rewards)
        stats['reward_std'] = np.std(rewards)
        stats['total_positive_rewards'] = sum(1 for r in rewards if r > 0)
        stats['total_negative_rewards'] = sum(1 for r in rewards if r < 0)

        # Sponsor statistics
        sponsor_episodes = sum(
            1 for ep in self.episodes
            if any(s.agent_is_sponsor for s, _, _, _, _ in ep['trajectory'])
        )
        stats['sponsor_rate'] = sponsor_episodes / len(self.episodes)

        return stats

    def print_stats(self):
        """Print summary statistics."""
        stats = self.compute_stats()

        print("\n" + "=" * 60)
        print("EPISODE METRICS")
        print("=" * 60)

        print(f"\nEpisodes: {stats.get('num_episodes', 0)}")
        print(f"Transitions: {stats.get('num_transitions', 0)}")
        print(f"Avg episode length: {stats.get('avg_episode_length', 0):.2f}")
        print(f"Sponsor rate: {stats.get('sponsor_rate', 0):.2%}")

        print(f"\nReward statistics:")
        print(f"  Mean: {stats.get('reward_mean', 0):.3f}")
        print(f"  Std: {stats.get('reward_std', 0):.3f}")
        print(f"  Positive: {stats.get('total_positive_rewards', 0)}")
        print(f"  Negative: {stats.get('total_negative_rewards', 0)}")

        print(f"\nAction distribution:")
        for action, count in stats.get('action_distribution', {}).items():
            pct = count / stats.get('num_transitions', 1) * 100
            print(f"  {action}: {count} ({pct:.1f}%)")

        print("=" * 60)


def compare_trajectories(
    real_trajectory: List[Tuple],
    simulated_trajectory: List[Tuple],
) -> Dict:
    """
    Compare real vs simulated trajectory.

    Args:
        real_trajectory: Ground truth (s, a, s', r, done) tuples
        simulated_trajectory: Generated (s, a, s', r, done) tuples

    Returns:
        Dictionary of comparison metrics
    """
    # Action matching
    real_actions = [a for _, a, _, _, _ in real_trajectory]
    sim_actions = [a for _, a, _, _, _ in simulated_trajectory]

    action_match = sum(
        1 for ra, sa in zip(real_actions, sim_actions) if ra == sa
    ) / max(len(real_actions), 1)

    # Final outcome matching
    real_reward = real_trajectory[-1][3] if real_trajectory else 0
    sim_reward = simulated_trajectory[-1][3] if simulated_trajectory else 0
    outcome_match = (real_reward > 0) == (sim_reward > 0)

    return {
        'action_accuracy': action_match,
        'outcome_match': outcome_match,
        'length_diff': abs(len(real_trajectory) - len(simulated_trajectory)),
    }


def evaluate_world_model(
    model,
    test_transitions: List[Tuple[np.ndarray, int, np.ndarray, float, bool]],
) -> Dict:
    """
    Evaluate world model prediction accuracy.

    Args:
        model: World model with predict(s, a) -> s_next method
        test_transitions: List of (s, a, s', r, done) tuples

    Returns:
        Evaluation metrics
    """
    predictions = []
    targets = []

    for s, a, s_next, _, _ in test_transitions:
        pred_s_next = model.predict(s, a)
        predictions.append(pred_s_next)
        targets.append(s_next)

    predictions = np.array(predictions)
    targets = np.array(targets)

    # Mean squared error
    mse = np.mean((predictions - targets) ** 2)

    # Per-dimension accuracy (for discrete features)
    dim_accuracy = []
    for dim in range(predictions.shape[1]):
        # If dimension seems discrete (small number of unique values)
        unique_vals = len(np.unique(targets[:, dim]))
        if unique_vals < 10:
            acc = np.mean(
                np.round(predictions[:, dim]) == targets[:, dim]
            )
            dim_accuracy.append(acc)

    return {
        'mse': mse,
        'rmse': np.sqrt(mse),
        'discrete_accuracy': np.mean(dim_accuracy) if dim_accuracy else None,
        'num_predictions': len(predictions),
    }


def evaluate_policy(
    policy,
    test_episodes: List[Dict],
) -> Dict:
    """
    Evaluate learned policy against expert behavior.

    Args:
        policy: Policy with get_action(state) method
        test_episodes: List of expert episode dicts

    Returns:
        Policy evaluation metrics
    """
    action_matches = []
    total_returns = []

    for episode in test_episodes:
        trajectory = episode['trajectory']
        episode_return = 0
        matches = 0

        for s, expert_a, _, r, _ in trajectory:
            # Get policy action
            policy_a = policy.get_action(s)

            # Check if it matches expert
            if policy_a == expert_a:
                matches += 1

            episode_return += r

        action_matches.append(matches / len(trajectory))
        total_returns.append(episode_return)

    return {
        'action_accuracy': np.mean(action_matches),
        'action_accuracy_std': np.std(action_matches),
        'avg_return': np.mean(total_returns),
        'avg_return_std': np.std(total_returns),
    }
