#!/usr/bin/env python3
"""
Demo of UN Deliberation Gym for world modeling and IRL.

This script demonstrates:
1. Basic environment usage
2. Extracting expert trajectories for IRL
3. Preparing data for world model training
"""

import sys
sys.path.insert(0, '/workspace')

from un_gym import UNDeliberationEnv, load_trajectory, Action
import numpy as np


def demo_environment_interaction():
    """Show basic environment usage."""
    print("\n" + "=" * 70)
    print("DEMO 1: Environment Interaction")
    print("=" * 70)

    # Load trajectory
    traj = load_trajectory('/workspace/scratch/220.json')

    # Create environment
    env = UNDeliberationEnv(
        country="United States of America",
        trajectories=[traj],
        seed=123,
    )

    # Reset and run episode
    state = env.reset()
    env.render()

    # Agent decides to cosponsor (US was a sponsor in this resolution)
    print("\n→ Agent decides to COSPONSOR")
    state, reward, done, info = env.step(Action.COSPONSOR)
    env.render()

    # Skip to committee vote
    print("\n→ Agent advances to committee vote")
    state, reward, done, info = env.step(Action.NO_ACTION)
    env.render()

    # Vote yes in committee
    print("\n→ Agent votes YES in committee")
    state, reward, done, info = env.step(Action.VOTE_YES)
    env.render()

    # Vote yes in plenary
    print("\n→ Agent votes YES in plenary")
    state, reward, done, info = env.step(Action.VOTE_YES)
    env.render()

    print(f"\nFinal reward: {reward}")
    print(f"Episode done: {done}")


def demo_world_model_data():
    """Show how to prepare data for world model training."""
    print("\n" + "=" * 70)
    print("DEMO 2: World Model Training Data")
    print("=" * 70)

    traj = load_trajectory('/workspace/scratch/220.json')

    # Different countries see different trajectories
    countries = ["France", "China", "Brazil"]

    for country in countries:
        env = UNDeliberationEnv(country=country, trajectories=[traj])
        transitions = env.get_transition_data()

        print(f"\n{country}:")
        print(f"  Extracted {len(transitions)} transitions")

        # Show what the country did
        for i, (s, a, s_next, r, done) in enumerate(transitions):
            from un_gym import State
            state = State.from_vec(s)
            print(f"  Step {i}: {Action(a).name} at {state.stage.name}")


def demo_expert_trajectories():
    """Show expert trajectory extraction for IRL."""
    print("\n" + "=" * 70)
    print("DEMO 3: Expert Trajectories for IRL")
    print("=" * 70)

    traj = load_trajectory('/workspace/scratch/220.json')

    # Extract what a specific country did
    country = "Germany"
    env = UNDeliberationEnv(country=country, trajectories=[traj])

    # Get expert demonstrations
    expert_demo = env.get_transition_data()

    print(f"\nExpert demonstrations for {country}:")
    print(f"Number of state-action pairs: {len(expert_demo)}")

    # This data can be used for IRL:
    # - States: s (what Germany observed)
    # - Actions: a (what Germany chose)
    # - Goal: infer reward function R(s,a) that explains the policy

    print("\nFor IRL, we can:")
    print("1. Model Germany's policy as approximately optimal")
    print("2. Infer reward weights that explain the observed actions")
    print("3. Predict Germany's future votes on similar resolutions")

    # Show action distribution
    actions = [a for _, a, _, _, _ in expert_demo]
    print(f"\nObserved action sequence:")
    for i, a in enumerate(actions):
        print(f"  {i}: {Action(a).name}")


def demo_state_representation():
    """Show state vector structure."""
    print("\n" + "=" * 70)
    print("DEMO 4: State Representation")
    print("=" * 70)

    traj = load_trajectory('/workspace/scratch/220.json')
    env = UNDeliberationEnv(country="Sweden", trajectories=[traj])

    state_vec = env.reset()

    print(f"\nState vector dimension: {len(state_vec)}")
    print(f"State vector:\n{state_vec}")

    print("\nInterpretation:")
    print("  [0:4]  - Stage one-hot (DRAFT, COMMITTEE_VOTE, PLENARY_VOTE, TERMINAL)")
    print("  [4]    - Topic ID (placeholder, currently 0)")
    print("  [5]    - Sponsor count")
    print("  [6]    - Agent is sponsor (0/1)")
    print("  [7:10] - Committee vote counts (yes, no, abstain)")
    print("  [10:13]- Plenary vote counts (yes, no, abstain)")
    print("  [13]   - Timestep")

    # Show how to reconstruct State from vector
    from un_gym import State
    state_obj = State.from_vec(state_vec)
    print(f"\nReconstructed state:")
    print(f"  Stage: {state_obj.stage.name}")
    print(f"  Sponsor count: {state_obj.sponsor_count}")
    print(f"  Agent is sponsor: {state_obj.agent_is_sponsor}")


if __name__ == '__main__':
    demo_environment_interaction()
    demo_world_model_data()
    demo_expert_trajectories()
    demo_state_representation()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
The UN Deliberation Gym provides:

1. OpenAI Gym-style interface for RL research
2. State vectors ready for neural network training
3. Expert trajectories for IRL and imitation learning
4. Flexible country-specific perspectives

Next steps:
- Train world model P(s' | s, a) on historical transitions
- Use IRL to infer country reward functions
- Build multi-agent simulator for counterfactual analysis
    """)
