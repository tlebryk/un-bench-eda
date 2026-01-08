"""Tests for gym environment."""

import pytest
import numpy as np
from un_gym import UNDeliberationEnv, load_trajectory, Action, Stage


@pytest.fixture
def test_trajectory():
    """Load test trajectory."""
    return load_trajectory('/workspace/scratch/220.json')


@pytest.fixture
def env(test_trajectory):
    """Create test environment."""
    return UNDeliberationEnv(
        country="France",
        trajectories=[test_trajectory],
        seed=42,
    )


def test_env_reset(env):
    """Test environment reset."""
    state = env.reset()

    assert isinstance(state, np.ndarray)
    assert state.shape == (14,)
    assert env.state is not None
    assert env.state.stage == Stage.DRAFT
    assert not env.episode_done


def test_env_step_cosponsor(env):
    """Test cosponsoring in DRAFT stage."""
    env.reset()

    # Cosponsor
    next_state, reward, done, info = env.step(Action.COSPONSOR)

    assert isinstance(next_state, np.ndarray)
    assert next_state.shape == (14,)
    assert reward == 0.0  # No reward yet
    assert not done
    assert env.state.agent_is_sponsor


def test_env_step_full_episode(env):
    """Test running a full episode."""
    env.reset()

    # Step 1: Don't cosponsor
    s1, r1, done1, _ = env.step(Action.NO_ACTION)
    assert not done1
    assert not env.state.agent_is_sponsor

    # Step 2: Advance to committee vote
    s2, r2, done2, _ = env.step(Action.NO_ACTION)
    assert not done2
    assert env.state.stage == Stage.COMMITTEE_VOTE

    # Step 3: Vote in committee
    s3, r3, done3, _ = env.step(Action.VOTE_YES)
    assert not done3
    assert env.state.stage == Stage.PLENARY_VOTE

    # Step 4: Vote in plenary
    s4, r4, done4, _ = env.step(Action.VOTE_NO)
    assert done4
    assert env.state.stage == Stage.TERMINAL
    # Reward should be 0 since not a sponsor
    assert r4 == 0.0


def test_env_step_sponsor_reward(env):
    """Test that sponsors get rewards."""
    env.reset()

    # Become a sponsor
    env.step(Action.COSPONSOR)
    env.step(Action.NO_ACTION)  # Advance

    # Vote through
    env.step(Action.VOTE_YES)
    _, reward, done, _ = env.step(Action.VOTE_YES)

    assert done
    # Sponsor should get non-zero reward
    assert reward != 0.0


def test_env_reset_specific_resolution(env, test_trajectory):
    """Test resetting to specific resolution."""
    state = env.reset(resolution_id=test_trajectory['trajectory_id'])

    assert env.current_trajectory is not None
    assert env.current_trajectory['trajectory_id'] == test_trajectory['trajectory_id']


def test_env_invalid_action(env):
    """Test invalid action handling."""
    env.reset()

    # Try to vote in DRAFT stage (invalid)
    next_state, reward, done, info = env.step(Action.VOTE_YES)

    # Should treat as NO_ACTION
    assert not done
    assert env.state.stage == Stage.DRAFT


def test_env_episode_done_error(env):
    """Test error when stepping after episode done."""
    env.reset()

    # Run episode to completion
    env.step(Action.NO_ACTION)
    env.step(Action.NO_ACTION)
    env.step(Action.VOTE_YES)
    env.step(Action.VOTE_YES)

    # Try to step again
    with pytest.raises(RuntimeError):
        env.step(Action.NO_ACTION)


def test_env_get_state_dim(env):
    """Test get_state_dim method."""
    assert env.get_state_dim() == 14


def test_env_get_action_dim(env):
    """Test get_action_dim method."""
    assert env.get_action_dim() == 5


def test_env_get_transition_data(env):
    """Test extracting transition data."""
    transitions = env.get_transition_data()

    assert len(transitions) > 0

    for s, a, s_next, r, done in transitions:
        assert isinstance(s, np.ndarray)
        assert s.shape == (14,)
        assert isinstance(a, int)
        assert 0 <= a <= 4
        assert isinstance(s_next, np.ndarray)
        assert s_next.shape == (14,)
        assert isinstance(r, float)
        assert isinstance(done, bool)


def test_env_render(env, capsys):
    """Test render method."""
    env.reset()
    env.render()

    captured = capsys.readouterr()
    assert "UN Deliberation Environment" in captured.out
    assert "France" in captured.out
    assert "DRAFT" in captured.out


def test_env_reproducibility():
    """Test that same seed gives same results."""
    traj = load_trajectory('/workspace/scratch/220.json')

    env1 = UNDeliberationEnv(country="France", trajectories=[traj], seed=123)
    env2 = UNDeliberationEnv(country="France", trajectories=[traj], seed=123)

    s1 = env1.reset()
    s2 = env2.reset()

    # Same seed should give same initial state
    np.testing.assert_array_equal(s1, s2)

    # Take same actions
    s1_1, _, _, _ = env1.step(Action.COSPONSOR)
    s2_1, _, _, _ = env2.step(Action.COSPONSOR)

    np.testing.assert_array_equal(s1_1, s2_1)
