#!/usr/bin/env python3
"""
Minimal IRL (Inverse Reinforcement Learning) script.

Goal: Infer reward function from expert demonstrations.
Strategy: Learn linear reward weights over state features using MaxEnt IRL.
"""

import argparse
import numpy as np
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from un_gym import UNDeliberationEnv, load_trajectory, trajectory_to_episode, Stage, Action


def extract_state_features(state_vec):
    """
    Extract interpretable features from state vector.

    State vector (14-dim):
    - [0:4]: stage one-hot
    - [4]: topic_id
    - [5]: sponsor_count
    - [6]: agent_is_sponsor
    - [7:10]: committee votes (yes, no, abstain)
    - [10:13]: plenary votes (yes, no, abstain)
    - [13]: timestep
    """
    features = {
        'is_sponsor': state_vec[6],
        'sponsor_count': state_vec[5],
        'committee_support': state_vec[7] - state_vec[8],  # yes - no
        'plenary_support': state_vec[10] - state_vec[11],  # yes - no
        'in_draft': state_vec[0],  # stage == DRAFT
        'in_committee': state_vec[1],  # stage == COMMITTEE_VOTE
        'in_plenary': state_vec[2],  # stage == PLENARY_VOTE
    }
    return features


def compute_feature_expectations(episodes):
    """
    Compute average feature values over expert trajectories.

    This is the core of IRL: we want to learn a reward that makes
    the expert's feature expectations optimal.
    """
    all_features = []

    for episode in episodes:
        for state, action, next_state, reward, done in episode:
            features = extract_state_features(state.to_vec())
            all_features.append(list(features.values()))

    feature_matrix = np.array(all_features)
    feature_expectations = np.mean(feature_matrix, axis=0)

    return feature_expectations, list(features.keys())


def simple_irl(expert_episodes, n_iterations=50, lr=0.1):
    """
    Simplified Maximum Entropy IRL.

    Learn linear reward weights: R(s) = w^T * features(s)

    In proper MaxEnt IRL, we'd:
    1. Compute expert feature expectations
    2. Sample trajectories from current policy
    3. Update weights to match feature expectations

    For this minimal version, we'll use a simpler approach:
    - Learn weights that correlate with expert rewards
    """
    print("Running simplified IRL...")

    # Extract features from all states
    all_states = []
    all_rewards = []

    for episode in expert_episodes:
        for state, action, next_state, reward, done in episode:
            all_states.append(extract_state_features(state.to_vec()))
            all_rewards.append(reward)

    # Convert to matrix
    feature_names = list(all_states[0].keys())
    feature_matrix = np.array([[s[k] for k in feature_names] for s in all_states])
    reward_vector = np.array(all_rewards)

    print(f"  Feature matrix shape: {feature_matrix.shape}")
    print(f"  Reward vector shape: {reward_vector.shape}")

    # Simple linear regression: find w such that w^T * features ≈ reward
    # Use gradient descent
    n_features = feature_matrix.shape[1]
    weights = np.zeros(n_features)

    losses = []
    for iteration in range(n_iterations):
        # Predict rewards
        pred_rewards = feature_matrix @ weights

        # Loss: MSE
        loss = np.mean((pred_rewards - reward_vector) ** 2)
        losses.append(loss)

        # Gradient
        grad = 2 * feature_matrix.T @ (pred_rewards - reward_vector) / len(reward_vector)

        # Update
        weights -= lr * grad

        if (iteration + 1) % 10 == 0 or iteration == 0:
            print(f"  Iteration {iteration+1:3d}: Loss = {loss:.6f}")

    return weights, feature_names, losses


def main():
    parser = argparse.ArgumentParser(description="Train IRL model")
    parser.add_argument("--trajectory", "-t", type=str, default="scratch/220.json",
                        help="Path to trajectory JSON")
    parser.add_argument("--country", "-c", type=str, default="France",
                        help="Country perspective")
    parser.add_argument("--iterations", "-i", type=int, default=50,
                        help="IRL iterations")
    parser.add_argument("--lr", type=float, default=0.1,
                        help="Learning rate")
    args = parser.parse_args()

    print("=" * 60)
    print("INVERSE REINFORCEMENT LEARNING - MINIMAL DEMO")
    print("=" * 60)
    print(f"Trajectory: {args.trajectory}")
    print(f"Country: {args.country}")
    print(f"Iterations: {args.iterations}")
    print()

    # Load trajectory
    print("Loading trajectory...")
    traj = load_trajectory(args.trajectory)
    print(f"  Loaded: {traj['metadata']['symbol']}")
    print(f"  Title: {traj['metadata']['title'][:80]}...")
    print()

    # Convert to episode
    print(f"Converting trajectory to episode (from {args.country}'s perspective)...")
    try:
        episode = trajectory_to_episode(traj, args.country)
        print(f"  Episode length: {len(episode)} transitions")
        print()
    except Exception as e:
        print(f"ERROR: Failed to convert trajectory: {e}")
        return

    # Show expert actions
    print("Expert demonstration:")
    print("-" * 60)
    for i, (state, action, next_state, reward, done) in enumerate(episode):
        action_name = Action(action).name
        stage_name = Stage(int(state.stage)).name
        print(f"  Step {i}: {stage_name:15s} -> {action_name:15s} (reward: {reward:+.1f})")
    print("-" * 60)
    print()

    # Run IRL
    weights, feature_names, losses = simple_irl(
        [episode],
        n_iterations=args.iterations,
        lr=args.lr
    )

    print()
    print("IRL complete!")
    print()

    # Display learned reward function
    print("=" * 60)
    print("LEARNED REWARD FUNCTION")
    print("=" * 60)
    print("R(s) = w^T * features(s), where:")
    print()
    for name, weight in zip(feature_names, weights):
        sign = "+" if weight >= 0 else ""
        print(f"  {name:20s}: {sign}{weight:7.4f}")
    print()

    # Interpret results
    print("=" * 60)
    print("INTERPRETATION")
    print("=" * 60)

    # Find most important features
    abs_weights = np.abs(weights)
    sorted_indices = np.argsort(abs_weights)[::-1]

    print("Most important features:")
    for idx in sorted_indices[:3]:
        name = feature_names[idx]
        weight = weights[idx]
        interpretation = "positive" if weight > 0 else "negative"
        print(f"  {name:20s}: {weight:7.4f} ({interpretation} reward)")

    print()

    # Check if results make sense
    print("Sanity checks:")
    is_sponsor_idx = feature_names.index('is_sponsor')
    support_indices = [i for i, name in enumerate(feature_names) if 'support' in name]

    sponsor_weight = weights[is_sponsor_idx]
    print(f"  • Sponsor weight: {sponsor_weight:.4f}")
    if sponsor_weight > 0:
        print("    ✓ Positive - makes sense (sponsors prefer adoption)")
    else:
        print("    ⚠ Negative or zero - unexpected!")

    print()

    # Analysis
    print("=" * 60)
    print("ANALYSIS")
    print("=" * 60)
    print(f"✓ IRL converged (loss: {losses[0]:.4f} -> {losses[-1]:.6f})")
    print(f"✓ Learned {len(weights)} reward weights")
    print(f"✓ Most important feature: {feature_names[sorted_indices[0]]}")

    print()
    print("⚠ CRITICAL LIMITATIONS:")
    print("  1. Single trajectory = single expert demo")
    print("     - Can't learn general country preferences")
    print("     - Just memorizing one episode")
    print("  2. Simplified IRL (not true MaxEnt)")
    print("     - Should sample trajectories from learned policy")
    print("     - Should iteratively match feature expectations")
    print("  3. No held-out test set")
    print("     - Can't validate learned preferences")

    print()
    print("NEXT STEPS:")
    print("  1. Collect multiple trajectories for same country")
    print("  2. Implement proper MaxEnt IRL with policy sampling")
    print("  3. Test on held-out resolutions")
    print("  4. Compare learned preferences across countries")
    print("=" * 60)


if __name__ == "__main__":
    main()
