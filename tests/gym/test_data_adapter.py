"""Tests for data adapter."""

import pytest
from un_gym.data_adapter import (
    load_trajectory,
    extract_country_action,
    trajectory_to_episode,
    compute_reward,
)
from un_gym.spaces import Action


@pytest.fixture
def test_trajectory():
    """Load test trajectory."""
    return load_trajectory('/workspace/scratch/220.json')


def test_load_trajectory(test_trajectory):
    """Test loading trajectory from JSON."""
    assert 'trajectory_id' in test_trajectory
    assert 'metadata' in test_trajectory
    assert 'timesteps' in test_trajectory
    assert len(test_trajectory['timesteps']) > 0


def test_extract_country_action_sponsor(test_trajectory):
    """Test extracting sponsor action."""
    draft_step = next(
        t for t in test_trajectory['timesteps']
        if t['stage'] == 'draft_submission'
    )

    # France was a sponsor
    action = extract_country_action(draft_step, "France")
    assert action == Action.COSPONSOR

    # China was not a sponsor
    action = extract_country_action(draft_step, "China")
    assert action == Action.NO_ACTION


def test_extract_country_action_vote(test_trajectory):
    """Test extracting vote action."""
    plenary_step = next(
        t for t in test_trajectory['timesteps']
        if t['stage'] == 'plenary_vote'
    )

    # France voted yes
    action = extract_country_action(plenary_step, "France")
    assert action == Action.VOTE_YES

    # China voted no
    action = extract_country_action(plenary_step, "China")
    assert action == Action.VOTE_NO

    # Brazil abstained
    action = extract_country_action(plenary_step, "Brazil")
    assert action == Action.VOTE_ABSTAIN


def test_trajectory_to_episode_france(test_trajectory):
    """Test converting trajectory to episode for France."""
    episode = trajectory_to_episode(test_trajectory, "France")

    assert len(episode) == 3  # 3 transitions

    # Check structure
    for s, a, s_next, r, done in episode:
        assert hasattr(s, 'stage')
        assert isinstance(a, Action)
        assert hasattr(s_next, 'stage')
        assert isinstance(r, (int, float))
        assert isinstance(done, bool)

    # First action should be COSPONSOR (France sponsored)
    assert episode[0][1] == Action.COSPONSOR

    # Last transition should be done
    assert episode[-1][4] == True

    # Last transition should have non-zero reward (France was sponsor)
    assert episode[-1][3] != 0.0


def test_trajectory_to_episode_china(test_trajectory):
    """Test converting trajectory to episode for China."""
    episode = trajectory_to_episode(test_trajectory, "China")

    assert len(episode) == 3

    # First action should be NO_ACTION (China didn't sponsor)
    assert episode[0][1] == Action.NO_ACTION

    # China voted no
    assert episode[1][1] == Action.VOTE_NO
    assert episode[2][1] == Action.VOTE_NO

    # Last reward should be 0 (not a sponsor)
    assert episode[-1][3] == 0.0


def test_compute_reward_sponsor_adopted():
    """Test reward for sponsor when adopted."""
    reward = compute_reward(agent_is_sponsor=True, outcome='adopted')
    assert reward == 1.0


def test_compute_reward_sponsor_rejected():
    """Test reward for sponsor when rejected."""
    reward = compute_reward(agent_is_sponsor=True, outcome='rejected')
    assert reward == -1.0


def test_compute_reward_non_sponsor():
    """Test reward for non-sponsor."""
    reward = compute_reward(agent_is_sponsor=False, outcome='adopted')
    assert reward == 0.0

    reward = compute_reward(agent_is_sponsor=False, outcome='rejected')
    assert reward == 0.0
