#!/usr/bin/env python3
"""Interactive gym player - step through episodes interactively."""

import argparse
from un_gym import UNDeliberationEnv, load_trajectory
from un_gym.interactive import launch_interactive


def main():
    parser = argparse.ArgumentParser(description='Play UN Deliberation Gym interactively')
    parser.add_argument(
        '--country',
        '-c',
        default='France',
        help='Country to play as (default: France)'
    )
    parser.add_argument(
        '--trajectory',
        '-t',
        default='scratch/220.json',
        help='Trajectory file to load (default: scratch/220.json)'
    )
    parser.add_argument(
        '--seed',
        '-s',
        type=int,
        default=None,
        help='Random seed for reproducibility'
    )
    parser.add_argument(
        '--expert',
        '-e',
        action='store_true',
        help='Expert mode: auto-play using historical actions'
    )

    args = parser.parse_args()

    # Load trajectory
    print(f"Loading trajectory from {args.trajectory}...")
    traj = load_trajectory(args.trajectory)

    # Create environment
    print(f"Creating environment for {args.country}...")
    env = UNDeliberationEnv(
        country=args.country,
        trajectories=[traj],
        seed=args.seed,
    )

    # Launch interactive mode
    launch_interactive(env, expert_mode=args.expert)


if __name__ == '__main__':
    main()
