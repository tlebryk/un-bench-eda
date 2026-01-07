"""Visualization utilities for UN Deliberation Gym."""

from typing import List, Dict, Tuple
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict
from .spaces import State, Stage, Action


def plot_trajectory(
    trajectory: List[Tuple[State, Action, State, float, bool]],
    country: str = "Unknown",
    save_path: str = None,
):
    """
    Visualize a single trajectory.

    Args:
        trajectory: List of (s, a, s', r, done) tuples
        country: Country name for title
        save_path: Optional path to save figure
    """
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle(f'Trajectory Visualization - {country}', fontsize=14, fontweight='bold')

    # Extract data
    stages = []
    actions = []
    sponsor_counts = []
    is_sponsor = []

    for s, a, s_next, _, _ in trajectory:
        stages.append(s.stage.name)
        actions.append(Action(a).name)
        sponsor_counts.append(s.sponsor_count)
        is_sponsor.append(s.agent_is_sponsor)

    # Plot 1: Stage progression
    ax = axes[0, 0]
    timesteps = range(len(stages))
    stage_nums = [Stage[stage].value for stage in stages]
    ax.plot(timesteps, stage_nums, 'o-', linewidth=2, markersize=8)
    ax.set_yticks(range(4))
    ax.set_yticklabels(['DRAFT', 'COMMITTEE_VOTE', 'PLENARY_VOTE', 'TERMINAL'])
    ax.set_xlabel('Timestep')
    ax.set_ylabel('Stage')
    ax.set_title('Stage Progression')
    ax.grid(True, alpha=0.3)

    # Plot 2: Actions taken
    ax = axes[0, 1]
    action_colors = {
        'COSPONSOR': 'green',
        'VOTE_YES': 'blue',
        'VOTE_NO': 'red',
        'VOTE_ABSTAIN': 'gray',
        'NO_ACTION': 'lightgray',
    }
    colors = [action_colors.get(a, 'black') for a in actions]
    ax.bar(timesteps, [1] * len(actions), color=colors)
    ax.set_xlabel('Timestep')
    ax.set_ylabel('Action')
    ax.set_title('Actions Taken')
    ax.set_ylim([0, 1.5])
    ax.set_yticks([])

    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=color, label=action)
        for action, color in action_colors.items()
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=8)

    # Plot 3: Sponsor status
    ax = axes[1, 0]
    ax.plot(timesteps, is_sponsor, 'o-', linewidth=2, markersize=8, color='purple')
    ax.set_xlabel('Timestep')
    ax.set_ylabel('Is Sponsor')
    ax.set_title('Agent Sponsor Status')
    ax.set_ylim([-0.1, 1.1])
    ax.set_yticks([0, 1])
    ax.set_yticklabels(['No', 'Yes'])
    ax.grid(True, alpha=0.3)

    # Plot 4: Vote tallies (if available)
    ax = axes[1, 1]
    final_state = trajectory[-1][2]  # Last next_state
    if final_state.plenary_yes > 0:
        vote_data = {
            'Committee\nYes': final_state.committee_yes,
            'Committee\nNo': final_state.committee_no,
            'Committee\nAbstain': final_state.committee_abstain,
            'Plenary\nYes': final_state.plenary_yes,
            'Plenary\nNo': final_state.plenary_no,
            'Plenary\nAbstain': final_state.plenary_abstain,
        }
        colors_votes = ['green', 'red', 'gray', 'darkgreen', 'darkred', 'darkgray']
        ax.bar(vote_data.keys(), vote_data.values(), color=colors_votes)
        ax.set_ylabel('Vote Count')
        ax.set_title('Final Vote Tallies')
        ax.tick_params(axis='x', rotation=45, labelsize=8)
    else:
        ax.text(0.5, 0.5, 'No vote data available', ha='center', va='center', transform=ax.transAxes)
        ax.set_title('Vote Tallies')

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved figure to {save_path}")
    else:
        plt.show()

    plt.close()


def plot_action_distribution(
    episodes: List[Dict],
    save_path: str = None,
):
    """
    Plot action distribution across multiple episodes.

    Args:
        episodes: List of episode dicts with 'trajectory' key
        save_path: Optional path to save figure
    """
    action_counts = defaultdict(int)
    total = 0

    for episode in episodes:
        for _, a, _, _, _ in episode['trajectory']:
            action_counts[Action(a).name] += 1
            total += 1

    # Plot
    fig, ax = plt.subplots(figsize=(10, 6))

    actions = list(action_counts.keys())
    counts = [action_counts[a] for a in actions]
    percentages = [c / total * 100 for c in counts]

    colors = {
        'COSPONSOR': 'green',
        'VOTE_YES': 'blue',
        'VOTE_NO': 'red',
        'VOTE_ABSTAIN': 'gray',
        'NO_ACTION': 'lightgray',
    }
    bar_colors = [colors.get(a, 'black') for a in actions]

    bars = ax.bar(actions, percentages, color=bar_colors, edgecolor='black', linewidth=1.5)

    # Add count labels on bars
    for bar, count in zip(bars, counts):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{count}',
                ha='center', va='bottom', fontweight='bold')

    ax.set_ylabel('Percentage (%)', fontsize=12)
    ax.set_xlabel('Action', fontsize=12)
    ax.set_title(f'Action Distribution ({len(episodes)} episodes, {total} actions)', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved figure to {save_path}")
    else:
        plt.show()

    plt.close()


def plot_country_comparison(
    episodes_by_country: Dict[str, List[Dict]],
    save_path: str = None,
):
    """
    Compare action distributions across countries.

    Args:
        episodes_by_country: Dict mapping country name to list of episodes
        save_path: Optional path to save figure
    """
    fig, ax = plt.subplots(figsize=(12, 6))

    countries = list(episodes_by_country.keys())
    action_types = ['COSPONSOR', 'VOTE_YES', 'VOTE_NO', 'VOTE_ABSTAIN', 'NO_ACTION']

    # Compute action percentages for each country
    data = {action: [] for action in action_types}

    for country in countries:
        episodes = episodes_by_country[country]
        action_counts = defaultdict(int)
        total = 0

        for episode in episodes:
            for _, a, _, _, _ in episode['trajectory']:
                action_counts[Action(a).name] += 1
                total += 1

        # Convert to percentages
        for action in action_types:
            pct = (action_counts[action] / total * 100) if total > 0 else 0
            data[action].append(pct)

    # Plot grouped bars
    x = np.arange(len(countries))
    width = 0.15
    colors = ['green', 'blue', 'red', 'gray', 'lightgray']

    for i, (action, color) in enumerate(zip(action_types, colors)):
        offset = (i - 2) * width
        ax.bar(x + offset, data[action], width, label=action, color=color)

    ax.set_ylabel('Percentage (%)', fontsize=12)
    ax.set_xlabel('Country', fontsize=12)
    ax.set_title('Action Distribution by Country', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(countries, rotation=45, ha='right')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved figure to {save_path}")
    else:
        plt.show()

    plt.close()


def plot_training_metrics(
    train_losses: List[float],
    val_losses: List[float] = None,
    save_path: str = None,
):
    """
    Plot training and validation loss curves.

    Args:
        train_losses: Training loss per epoch/iteration
        val_losses: Optional validation loss per epoch/iteration
        save_path: Optional path to save figure
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    epochs = range(1, len(train_losses) + 1)
    ax.plot(epochs, train_losses, 'b-', label='Training Loss', linewidth=2)

    if val_losses:
        ax.plot(epochs, val_losses, 'r-', label='Validation Loss', linewidth=2)

    ax.set_xlabel('Epoch', fontsize=12)
    ax.set_ylabel('Loss', fontsize=12)
    ax.set_title('Training Metrics', fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved figure to {save_path}")
    else:
        plt.show()

    plt.close()
