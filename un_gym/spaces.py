"""State and action space definitions for UN Deliberation Gym."""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional
import numpy as np


class Stage(IntEnum):
    """Deliberation stages."""
    DRAFT = 0
    COMMITTEE_VOTE = 1
    PLENARY_VOTE = 2
    TERMINAL = 3


class Action(IntEnum):
    """Available actions."""
    COSPONSOR = 0
    VOTE_YES = 1
    VOTE_NO = 2
    VOTE_ABSTAIN = 3
    NO_ACTION = 4


@dataclass(frozen=True)
class State:
    """
    Environment state.

    The state has two parts:
    1. Structured fields (14-dim vector via to_vec()) - for RL algorithms
    2. Raw text fields (optional) - for LLM-based agents

    Text fields are NOT included in to_vec() - they're available for agents
    that want to do their own representation learning on raw text.
    """
    # Stage (will be one-hot in vector form)
    stage: Stage

    # Bill representation (placeholder for now)
    topic_id: int  # 0 for now, later categorized

    # Sponsor info
    sponsor_count: int
    agent_is_sponsor: bool

    # Committee vote results (0 until committee vote happens)
    committee_yes: int
    committee_no: int
    committee_abstain: int

    # Plenary vote results (0 until plenary vote happens)
    plenary_yes: int
    plenary_no: int
    plenary_abstain: int

    # Timestep
    t: int

    # --- Text fields (optional, not in vector representation) ---
    # Raw draft text for LLM-based agents to process directly
    draft_text: Optional[str] = None
    # Resolution title
    title: Optional[str] = None
    # Resolution symbol (e.g., "A/RES/78/220")
    resolution_symbol: Optional[str] = None

    def to_vec(self) -> np.ndarray:
        """Convert state to fixed-length vector for world modeling."""
        # Stage as one-hot (4 dims)
        stage_onehot = np.zeros(4)
        stage_onehot[self.stage] = 1.0

        # Scalar features
        scalars = np.array([
            self.topic_id,
            self.sponsor_count,
            float(self.agent_is_sponsor),
            self.committee_yes,
            self.committee_no,
            self.committee_abstain,
            self.plenary_yes,
            self.plenary_no,
            self.plenary_abstain,
            self.t,
        ])

        return np.concatenate([stage_onehot, scalars])

    @classmethod
    def from_vec(
        cls,
        vec: np.ndarray,
        draft_text: Optional[str] = None,
        title: Optional[str] = None,
        resolution_symbol: Optional[str] = None,
    ) -> 'State':
        """
        Reconstruct state from vector.

        Args:
            vec: 14-dimensional state vector
            draft_text: Optional raw text to preserve
            title: Optional title to preserve
            resolution_symbol: Optional symbol to preserve

        Returns:
            State object with numeric fields from vec, text fields from args
        """
        stage = Stage(np.argmax(vec[:4]))
        return cls(
            stage=stage,
            topic_id=int(vec[4]),
            sponsor_count=int(vec[5]),
            agent_is_sponsor=bool(vec[6]),
            committee_yes=int(vec[7]),
            committee_no=int(vec[8]),
            committee_abstain=int(vec[9]),
            plenary_yes=int(vec[10]),
            plenary_no=int(vec[11]),
            plenary_abstain=int(vec[12]),
            t=int(vec[13]),
            draft_text=draft_text,
            title=title,
            resolution_symbol=resolution_symbol,
        )

    @classmethod
    def get_dim(cls) -> int:
        """Dimension of state vector."""
        return 14  # 4 (stage one-hot) + 10 (scalars)


def is_action_valid(state: State, action: Action) -> bool:
    """Check if action is valid in current state."""
    if state.stage == Stage.DRAFT:
        return action in [Action.COSPONSOR, Action.NO_ACTION]
    elif state.stage == Stage.COMMITTEE_VOTE:
        return action in [Action.VOTE_YES, Action.VOTE_NO, Action.VOTE_ABSTAIN]
    elif state.stage == Stage.PLENARY_VOTE:
        return action in [Action.VOTE_YES, Action.VOTE_NO, Action.VOTE_ABSTAIN]
    elif state.stage == Stage.TERMINAL:
        return action == Action.NO_ACTION
    return False
