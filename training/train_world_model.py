#!/usr/bin/env python3
"""
Minimal world model training script.

Goal: Learn P(s' | s, a) - predict next state from current state and action.
Strategy: Train a simple MLP to predict state transitions.
"""

import argparse
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from un_gym import UNDeliberationEnv, load_trajectory


class WorldModel(nn.Module):
    """Simple MLP world model: (state, action) -> next_state."""

    def __init__(self, state_dim=14, action_dim=5, hidden_dim=64):
        super().__init__()
        self.state_dim = state_dim
        self.action_dim = action_dim

        # One-hot encode actions
        input_dim = state_dim + action_dim

        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, state_dim),
        )

    def forward(self, state, action):
        """
        Args:
            state: (batch, state_dim)
            action: (batch,) - integer actions
        Returns:
            next_state: (batch, state_dim)
        """
        # One-hot encode actions
        action_onehot = torch.zeros(action.shape[0], self.action_dim)
        action_onehot[torch.arange(action.shape[0]), action.long()] = 1.0

        # Concatenate state and action
        x = torch.cat([state, action_onehot], dim=1)

        return self.net(x)


def main():
    parser = argparse.ArgumentParser(description="Train world model")
    parser.add_argument("--trajectory", "-t", type=str, default="scratch/220.json",
                        help="Path to trajectory JSON")
    parser.add_argument("--country", "-c", type=str, default="France",
                        help="Country perspective")
    parser.add_argument("--epochs", "-e", type=int, default=100,
                        help="Training epochs")
    parser.add_argument("--lr", type=float, default=0.01,
                        help="Learning rate")
    args = parser.parse_args()

    print("=" * 60)
    print("WORLD MODEL TRAINING - MINIMAL DEMO")
    print("=" * 60)
    print(f"Trajectory: {args.trajectory}")
    print(f"Country: {args.country}")
    print(f"Epochs: {args.epochs}")
    print()

    # Load trajectory
    print("Loading trajectory...")
    traj = load_trajectory(args.trajectory)
    print(f"  Loaded: {traj['metadata']['symbol']}")
    print(f"  Title: {traj['metadata']['title'][:80]}...")
    print()

    # Create environment
    env = UNDeliberationEnv(country=args.country, trajectories=[traj], seed=42)

    # Extract transitions
    print("Extracting transitions...")
    transitions = env.get_transition_data()
    print(f"  Total transitions: {len(transitions)}")

    if len(transitions) == 0:
        print("ERROR: No transitions extracted!")
        return

    # Show example transition
    s, a, s_next, r, done = transitions[0]
    print(f"  Example transition:")
    print(f"    State shape: {s.shape}")
    print(f"    Action: {a}")
    print(f"    Next state shape: {s_next.shape}")
    print(f"    Reward: {r}")
    print(f"    Done: {done}")
    print()

    # Split train/test (use last transition as test)
    if len(transitions) > 1:
        train_transitions = transitions[:-1]
        test_transitions = [transitions[-1]]
        print(f"Train/test split: {len(train_transitions)} train, {len(test_transitions)} test")
    else:
        train_transitions = transitions
        test_transitions = []
        print("Using all data for training (no test set)")
    print()

    # Convert to tensors
    train_states = torch.tensor([t[0] for t in train_transitions], dtype=torch.float32)
    train_actions = torch.tensor([t[1] for t in train_transitions], dtype=torch.float32)
    train_next_states = torch.tensor([t[2] for t in train_transitions], dtype=torch.float32)

    print(f"Training data shapes:")
    print(f"  States: {train_states.shape}")
    print(f"  Actions: {train_actions.shape}")
    print(f"  Next states: {train_next_states.shape}")
    print()

    # Initialize model
    model = WorldModel(state_dim=14, action_dim=5)
    optimizer = optim.Adam(model.parameters(), lr=args.lr)
    criterion = nn.MSELoss()

    print("Training world model...")
    print("-" * 60)

    # Training loop
    losses = []
    for epoch in range(args.epochs):
        optimizer.zero_grad()

        # Forward pass
        pred_next_states = model(train_states, train_actions)
        loss = criterion(pred_next_states, train_next_states)

        # Backward pass
        loss.backward()
        optimizer.step()

        losses.append(loss.item())

        if (epoch + 1) % 20 == 0 or epoch == 0:
            print(f"Epoch {epoch+1:3d}/{args.epochs}: Loss = {loss.item():.6f}")

    print("-" * 60)
    print(f"Final training loss: {losses[-1]:.6f}")
    print()

    # Evaluate on test set
    if test_transitions:
        print("Evaluating on test set...")
        test_state = torch.tensor([test_transitions[0][0]], dtype=torch.float32)
        test_action = torch.tensor([test_transitions[0][1]], dtype=torch.float32)
        test_next_state = torch.tensor([test_transitions[0][2]], dtype=torch.float32)

        with torch.no_grad():
            pred = model(test_state, test_action)
            test_loss = criterion(pred, test_next_state).item()

        print(f"  Test MSE: {test_loss:.6f}")
        print(f"  Test RMSE: {np.sqrt(test_loss):.6f}")
        print()

        # Show prediction vs actual
        print("Sample prediction:")
        print(f"  True next state: {test_next_state[0][:8].numpy()}")
        print(f"  Pred next state: {pred[0][:8].detach().numpy()}")
        print(f"  (showing first 8 dims)")
        print()

    # Summary
    print("=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)
    print(f"Model parameters: {sum(p.numel() for p in model.parameters())}")
    print(f"Training loss: {losses[-1]:.6f}")
    if test_transitions:
        print(f"Test loss: {test_loss:.6f}")
    print()

    # Analysis
    print("ANALYSIS:")
    print("-" * 60)
    print("✓ World model successfully trained on minimal data")
    print(f"✓ Learned to predict {train_next_states.shape[1]}-dim state vectors")
    print(f"✓ Training converged (loss: {losses[0]:.4f} -> {losses[-1]:.6f})")

    if len(transitions) <= 3:
        print()
        print("⚠ CRITICAL ISSUE: Very few transitions!")
        print(f"  Only {len(transitions)} transition(s) from 1 trajectory")
        print("  This means:")
        print("  - Model is memorizing, not generalizing")
        print("  - Need more trajectories to learn meaningful dynamics")
        print("  - Current setup is proof-of-concept only")

    print()
    print("NEXT STEPS:")
    print("  1. Add more trajectories (need 10-50+ for real learning)")
    print("  2. Test on held-out resolutions")
    print("  3. Add regularization (dropout, weight decay)")
    print("  4. Evaluate discrete predictions (stage, vote counts)")
    print("=" * 60)


if __name__ == "__main__":
    main()
