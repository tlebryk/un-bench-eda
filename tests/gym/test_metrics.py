"""Tests for metrics module."""

import pytest
import numpy as np
from un_gym.metrics import EpisodeMetrics, compare_trajectories
from un_gym.spaces import State, Stage, Action


@pytest.fixture
def sample_episode():
    """Create sample episode."""
    s0 = State(Stage.DRAFT, 0, 50, False, 0, 0, 0, 0, 0, 0, 0)
    s1 = State(Stage.DRAFT, 0, 50, True, 0, 0, 0, 0, 0, 0, 1)
    s2 = State(Stage.COMMITTEE_VOTE, 0, 50, True, 0, 0, 0, 0, 0, 0, 2)
    s3 = State(Stage.PLENARY_VOTE, 0, 50, True, 100, 50, 20, 0, 0, 0, 3)
    s4 = State(Stage.TERMINAL, 0, 50, True, 100, 50, 20, 110, 45, 15, 4)

    return [
        (s0, Action.COSPONSOR, s1, 0.0, False),
        (s1, Action.VOTE_YES, s2, 0.0, False),
        (s2, Action.VOTE_YES, s3, 1.0, True),
    ]


def test_episode_metrics_basic(sample_episode):
    """Test basic metrics tracking."""
    metrics = EpisodeMetrics()

    assert metrics.compute_stats() == {}

    metrics.add_episode(sample_episode)

    stats = metrics.compute_stats()

    assert stats['num_episodes'] == 1
    assert stats['num_transitions'] == 3
    assert stats['avg_episode_length'] == 3.0


def test_episode_metrics_action_distribution(sample_episode):
    """Test action distribution computation."""
    metrics = EpisodeMetrics()
    metrics.add_episode(sample_episode)

    stats = metrics.compute_stats()

    assert 'action_distribution' in stats
    assert stats['action_distribution']['COSPONSOR'] == 1
    assert stats['action_distribution']['VOTE_YES'] == 2


def test_episode_metrics_rewards(sample_episode):
    """Test reward statistics."""
    metrics = EpisodeMetrics()
    metrics.add_episode(sample_episode)

    stats = metrics.compute_stats()

    assert stats['reward_mean'] > 0  # Has positive reward
    assert stats['total_positive_rewards'] == 1
    assert stats['total_negative_rewards'] == 0


def test_episode_metrics_sponsor_rate(sample_episode):
    """Test sponsor rate calculation."""
    metrics = EpisodeMetrics()

    # Add episode with sponsor
    metrics.add_episode(sample_episode)

    # Add episode without sponsor
    s0 = State(Stage.DRAFT, 0, 50, False, 0, 0, 0, 0, 0, 0, 0)
    s1 = State(Stage.COMMITTEE_VOTE, 0, 50, False, 0, 0, 0, 0, 0, 0, 1)
    s2 = State(Stage.TERMINAL, 0, 50, False, 100, 50, 20, 110, 45, 15, 2)

    non_sponsor_episode = [
        (s0, Action.NO_ACTION, s1, 0.0, False),
        (s1, Action.VOTE_NO, s2, 0.0, True),
    ]

    metrics.add_episode(non_sponsor_episode)

    stats = metrics.compute_stats()

    # 1 out of 2 episodes had sponsor
    assert stats['sponsor_rate'] == 0.5


def test_compare_trajectories_exact_match():
    """Test trajectory comparison with exact match."""
    s0 = State(Stage.DRAFT, 0, 50, False, 0, 0, 0, 0, 0, 0, 0)
    s1 = State(Stage.TERMINAL, 0, 50, True, 100, 50, 20, 110, 45, 15, 1)

    trajectory = [
        (s0, Action.COSPONSOR, s1, 1.0, True),
    ]

    result = compare_trajectories(trajectory, trajectory)

    assert result['action_accuracy'] == 1.0
    assert result['outcome_match'] == True
    assert result['length_diff'] == 0


def test_compare_trajectories_different_actions():
    """Test trajectory comparison with different actions."""
    s0 = State(Stage.DRAFT, 0, 50, False, 0, 0, 0, 0, 0, 0, 0)
    s1 = State(Stage.TERMINAL, 0, 50, True, 100, 50, 20, 110, 45, 15, 1)

    real = [(s0, Action.COSPONSOR, s1, 1.0, True)]
    simulated = [(s0, Action.NO_ACTION, s1, 1.0, True)]

    result = compare_trajectories(real, simulated)

    assert result['action_accuracy'] == 0.0
    assert result['outcome_match'] == True


def test_compare_trajectories_different_outcomes():
    """Test trajectory comparison with different outcomes."""
    s0 = State(Stage.DRAFT, 0, 50, False, 0, 0, 0, 0, 0, 0, 0)
    s1 = State(Stage.TERMINAL, 0, 50, True, 100, 50, 20, 110, 45, 15, 1)

    real = [(s0, Action.COSPONSOR, s1, 1.0, True)]
    simulated = [(s0, Action.COSPONSOR, s1, -1.0, True)]

    result = compare_trajectories(real, simulated)

    assert result['action_accuracy'] == 1.0
    assert result['outcome_match'] == False
