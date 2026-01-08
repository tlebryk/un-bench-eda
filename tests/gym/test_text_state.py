"""Tests for text integration in gym state."""

import pytest
import numpy as np
from un_gym.spaces import State, Stage, Action


class TestTextState:
    """Tests for text fields in State."""

    def test_state_with_text_fields(self):
        """State should support optional text fields."""
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
            # New text fields
            draft_text="The General Assembly...",
            title="Situation of human rights...",
            resolution_symbol="A/RES/78/220",
        )

        assert state.draft_text == "The General Assembly..."
        assert state.title == "Situation of human rights..."
        assert state.resolution_symbol == "A/RES/78/220"

    def test_state_text_fields_optional(self):
        """Text fields should default to None."""
        state = State(
            stage=Stage.DRAFT,
            topic_id=0,
            sponsor_count=50,
            agent_is_sponsor=False,
            committee_yes=0,
            committee_no=0,
            committee_abstain=0,
            plenary_yes=0,
            plenary_no=0,
            plenary_abstain=0,
            t=0,
        )

        assert state.draft_text is None
        assert state.title is None
        assert state.resolution_symbol is None

    def test_to_vec_excludes_text(self):
        """to_vec should return same 14-dim vector regardless of text."""
        state_no_text = State(
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

        state_with_text = State(
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
            draft_text="The General Assembly...",
            title="Some title",
            resolution_symbol="A/RES/78/220",
        )

        vec_no_text = state_no_text.to_vec()
        vec_with_text = state_with_text.to_vec()

        # Both should be 14-dim
        assert vec_no_text.shape == (14,)
        assert vec_with_text.shape == (14,)

        # Numeric parts should be identical
        np.testing.assert_array_equal(vec_no_text, vec_with_text)

    def test_from_vec_preserves_text(self):
        """from_vec should accept optional text fields to preserve."""
        original = State(
            stage=Stage.COMMITTEE_VOTE,
            topic_id=0,
            sponsor_count=30,
            agent_is_sponsor=True,
            committee_yes=100,
            committee_no=50,
            committee_abstain=20,
            plenary_yes=0,
            plenary_no=0,
            plenary_abstain=0,
            t=3,
            draft_text="Original text...",
            title="Original title",
            resolution_symbol="A/RES/78/300",
        )

        vec = original.to_vec()

        # Reconstruct with text preservation
        reconstructed = State.from_vec(
            vec,
            draft_text="Original text...",
            title="Original title",
            resolution_symbol="A/RES/78/300",
        )

        assert reconstructed.draft_text == "Original text..."
        assert reconstructed.title == "Original title"
        assert reconstructed.resolution_symbol == "A/RES/78/300"

    def test_state_get_dim_unchanged(self):
        """get_dim should still return 14 (text not in vector)."""
        assert State.get_dim() == 14


class TestDataAdapterText:
    """Tests for text extraction in data adapter."""

    def test_trajectory_to_episode_includes_text(self):
        """trajectory_to_episode should extract text into states."""
        from un_gym.data_adapter import trajectory_to_episode

        # Minimal trajectory with text
        trajectory = {
            "trajectory_id": "A/RES/78/TEST",
            "metadata": {
                "symbol": "A/RES/78/TEST",
                "title": "Test Resolution Title",
                "final_outcome": "adopted",
            },
            "timesteps": [
                {
                    "stage": "draft_submission",
                    "action": {
                        "sponsors": ["France", "Germany"],
                        "draft_text": "The General Assembly decides...",
                    },
                },
                {
                    "stage": "committee_vote",
                    "action": {"votes": {"in_favour": ["France"], "against": [], "abstaining": ["Germany"]}},
                    "observation": {"vote_tally": {"yes": 100, "no": 20, "abstain": 30}},
                },
                {
                    "stage": "plenary_vote",
                    "action": {"votes": {"in_favour": ["France", "Germany"], "against": [], "abstaining": []}},
                    "observation": {"vote_tally": {"yes": 150, "no": 10, "abstain": 20}},
                },
            ],
        }

        episode = trajectory_to_episode(trajectory, "France")

        # Check that states have text fields
        s0, _, _, _, _ = episode[0]
        assert s0.draft_text == "The General Assembly decides..."
        assert s0.title == "Test Resolution Title"
        assert s0.resolution_symbol == "A/RES/78/TEST"


class TestEnvText:
    """Tests for text in environment."""

    def test_env_info_contains_text(self):
        """step() info dict should contain text fields."""
        from un_gym import UNDeliberationEnv

        trajectory = {
            "trajectory_id": "A/RES/78/TEST",
            "metadata": {
                "symbol": "A/RES/78/TEST",
                "title": "Test Resolution",
                "final_outcome": "adopted",
            },
            "timesteps": [
                {
                    "stage": "draft_submission",
                    "action": {
                        "sponsors": ["France"],
                        "draft_text": "Test draft text...",
                    },
                },
                {
                    "stage": "committee_vote",
                    "action": {"votes": {"in_favour": ["France"], "against": [], "abstaining": []}},
                    "observation": {"vote_tally": {"yes": 100, "no": 20, "abstain": 30}},
                },
                {
                    "stage": "plenary_vote",
                    "action": {"votes": {"in_favour": ["France"], "against": [], "abstaining": []}},
                    "observation": {"vote_tally": {"yes": 150, "no": 10, "abstain": 20}},
                },
            ],
        }

        env = UNDeliberationEnv(country="France", trajectories=[trajectory], seed=42)
        env.reset(trajectory=trajectory)

        _, _, _, info = env.step(0)  # COSPONSOR

        assert "draft_text" in info
        assert info["draft_text"] == "Test draft text..."
        assert "title" in info
        assert info["title"] == "Test Resolution"
        assert "resolution_symbol" in info
        assert info["resolution_symbol"] == "A/RES/78/TEST"

    def test_env_get_text_method(self):
        """Environment should have get_text() method for current text."""
        from un_gym import UNDeliberationEnv

        trajectory = {
            "trajectory_id": "A/RES/78/TEST",
            "metadata": {
                "symbol": "A/RES/78/TEST",
                "title": "Test Resolution",
                "final_outcome": "adopted",
            },
            "timesteps": [
                {
                    "stage": "draft_submission",
                    "action": {
                        "sponsors": [],
                        "draft_text": "Full draft text here...",
                    },
                },
                {
                    "stage": "committee_vote",
                    "action": {"votes": {"in_favour": [], "against": [], "abstaining": []}},
                    "observation": {"vote_tally": {"yes": 100, "no": 20, "abstain": 30}},
                },
                {
                    "stage": "plenary_vote",
                    "action": {"votes": {"in_favour": [], "against": [], "abstaining": []}},
                    "observation": {"vote_tally": {"yes": 150, "no": 10, "abstain": 20}},
                },
            ],
        }

        env = UNDeliberationEnv(country="France", trajectories=[trajectory], seed=42)
        env.reset(trajectory=trajectory)

        text_dict = env.get_text()

        assert text_dict["draft_text"] == "Full draft text here..."
        assert text_dict["title"] == "Test Resolution"
        assert text_dict["resolution_symbol"] == "A/RES/78/TEST"
