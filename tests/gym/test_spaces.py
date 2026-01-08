"""Tests for gym spaces."""

import pytest
import numpy as np
from un_gym.spaces import State, Stage, Action, is_action_valid


def test_state_to_vec():
    """Test state vectorization."""
    state = State(
        stage=Stage.DRAFT,
        topic_id=0,
        sponsor_count=50,
        agent_is_sponsor=True,
        committee_yes=0,
        committee_no=0,
        committee_abstain=0,
        plenary_yes=0,
        plenary_no=0,
        plenary_abstain=0,
        t=0,
    )

    vec = state.to_vec()

    # Check shape
    assert vec.shape == (14,)

    # Check stage one-hot
    assert vec[0] == 1.0  # DRAFT
    assert vec[1] == 0.0
    assert vec[2] == 0.0
    assert vec[3] == 0.0

    # Check scalar features
    assert vec[5] == 50  # sponsor_count
    assert vec[6] == 1.0  # agent_is_sponsor


def test_state_round_trip():
    """Test State -> vec -> State conversion."""
    original = State(
        stage=Stage.COMMITTEE_VOTE,
        topic_id=0,
        sponsor_count=30,
        agent_is_sponsor=False,
        committee_yes=100,
        committee_no=50,
        committee_abstain=20,
        plenary_yes=0,
        plenary_no=0,
        plenary_abstain=0,
        t=3,
    )

    vec = original.to_vec()
    reconstructed = State.from_vec(vec)

    assert original == reconstructed


def test_state_dimension():
    """Test state dimension is correct."""
    assert State.get_dim() == 14


def test_action_valid_draft():
    """Test action validation in DRAFT stage."""
    state = State(
        stage=Stage.DRAFT,
        topic_id=0,
        sponsor_count=10,
        agent_is_sponsor=False,
        committee_yes=0,
        committee_no=0,
        committee_abstain=0,
        plenary_yes=0,
        plenary_no=0,
        plenary_abstain=0,
        t=0,
    )

    assert is_action_valid(state, Action.COSPONSOR)
    assert is_action_valid(state, Action.NO_ACTION)
    assert not is_action_valid(state, Action.VOTE_YES)
    assert not is_action_valid(state, Action.VOTE_NO)
    assert not is_action_valid(state, Action.VOTE_ABSTAIN)


def test_action_valid_committee_vote():
    """Test action validation in COMMITTEE_VOTE stage."""
    state = State(
        stage=Stage.COMMITTEE_VOTE,
        topic_id=0,
        sponsor_count=10,
        agent_is_sponsor=True,
        committee_yes=0,
        committee_no=0,
        committee_abstain=0,
        plenary_yes=0,
        plenary_no=0,
        plenary_abstain=0,
        t=2,
    )

    assert is_action_valid(state, Action.VOTE_YES)
    assert is_action_valid(state, Action.VOTE_NO)
    assert is_action_valid(state, Action.VOTE_ABSTAIN)
    assert not is_action_valid(state, Action.COSPONSOR)


def test_action_valid_terminal():
    """Test action validation in TERMINAL stage."""
    state = State(
        stage=Stage.TERMINAL,
        topic_id=0,
        sponsor_count=10,
        agent_is_sponsor=True,
        committee_yes=100,
        committee_no=50,
        committee_abstain=20,
        plenary_yes=110,
        plenary_no=45,
        plenary_abstain=15,
        t=4,
    )

    assert is_action_valid(state, Action.NO_ACTION)
    assert not is_action_valid(state, Action.VOTE_YES)
    assert not is_action_valid(state, Action.COSPONSOR)
