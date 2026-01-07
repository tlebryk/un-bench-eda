"""Transition dynamics for the environment."""

from typing import List, Dict, Tuple
import numpy as np
from .spaces import State, Stage, Action


class EmpiricalDynamics:
    """
    Sample transitions based on empirical distributions from historical data.

    For now, uses simple base rates. Later can be replaced with learned model.
    """

    def __init__(self, trajectories: List[Dict]):
        """
        Initialize from historical trajectories.

        Args:
            trajectories: List of trajectory dicts loaded from JSON
        """
        self.trajectories = trajectories
        self._compute_statistics()

    def _compute_statistics(self):
        """Compute empirical statistics from trajectories."""
        # Compute average sponsor count
        sponsor_counts = []
        for traj in self.trajectories:
            draft_step = next(
                (t for t in traj['timesteps'] if t['stage'] == 'draft_submission'),
                None
            )
            if draft_step:
                sponsors = draft_step['action'].get('sponsors', [])
                sponsor_counts.append(len(sponsors))

        self.mean_sponsor_count = int(np.mean(sponsor_counts)) if sponsor_counts else 30
        self.std_sponsor_count = int(np.std(sponsor_counts)) if sponsor_counts else 10

        # Compute adoption rate
        outcomes = [t['metadata'].get('final_outcome', 'adopted') for t in self.trajectories]
        adoption_count = sum(1 for o in outcomes if o.lower() == 'adopted')
        self.adoption_rate = adoption_count / len(outcomes) if outcomes else 0.5

    def sample_sponsor_count(self) -> int:
        """Sample number of sponsors from empirical distribution."""
        count = int(np.random.normal(self.mean_sponsor_count, self.std_sponsor_count))
        return max(1, count)  # at least 1 sponsor

    def sample_vote_outcome(
        self,
        sponsor_count: int,
        stage: Stage,
    ) -> Tuple[int, int, int]:
        """
        Sample vote outcome (yes, no, abstain counts).

        For now, uses simple heuristics. Later can be learned model.

        Returns:
            (yes_count, no_count, abstain_count)
        """
        # Total voters (approximate UN membership)
        total = 193

        # Higher sponsor count → higher yes probability
        sponsor_effect = min(sponsor_count / 50.0, 0.5)
        base_yes_prob = 0.4 + sponsor_effect

        # Sample vote counts
        yes_count = int(np.random.binomial(total, base_yes_prob))
        remaining = total - yes_count

        # Split remaining between no and abstain
        abstain_count = int(np.random.binomial(remaining, 0.4))
        no_count = remaining - abstain_count

        return yes_count, no_count, abstain_count

    def transition(
        self,
        state: State,
        action: Action,
        rng: np.random.Generator = None,
    ) -> State:
        """
        Sample next state given current state and action.

        Args:
            state: Current state
            action: Agent's action
            rng: Random number generator (optional)

        Returns:
            Next state
        """
        if rng is None:
            rng = np.random.default_rng()

        # Stage transitions are deterministic
        if state.stage == Stage.DRAFT:
            # Agent took action, now move to committee vote
            agent_is_sponsor = state.agent_is_sponsor or (action == Action.COSPONSOR)

            # If transitioning to committee vote stage
            if state.t == 0:
                # Just update sponsor status, stay in DRAFT
                return State(
                    stage=Stage.DRAFT,
                    topic_id=state.topic_id,
                    sponsor_count=state.sponsor_count,
                    agent_is_sponsor=agent_is_sponsor,
                    committee_yes=0,
                    committee_no=0,
                    committee_abstain=0,
                    plenary_yes=0,
                    plenary_no=0,
                    plenary_abstain=0,
                    t=state.t + 1,
                    # Preserve text fields
                    draft_text=state.draft_text,
                    title=state.title,
                    resolution_symbol=state.resolution_symbol,
                )
            else:
                # Move to committee vote
                return State(
                    stage=Stage.COMMITTEE_VOTE,
                    topic_id=state.topic_id,
                    sponsor_count=state.sponsor_count,
                    agent_is_sponsor=agent_is_sponsor,
                    committee_yes=0,
                    committee_no=0,
                    committee_abstain=0,
                    plenary_yes=0,
                    plenary_no=0,
                    plenary_abstain=0,
                    t=state.t + 1,
                    # Preserve text fields
                    draft_text=state.draft_text,
                    title=state.title,
                    resolution_symbol=state.resolution_symbol,
                )

        elif state.stage == Stage.COMMITTEE_VOTE:
            # Sample committee vote outcome
            yes, no, abstain = self.sample_vote_outcome(
                state.sponsor_count,
                Stage.COMMITTEE_VOTE,
            )

            return State(
                stage=Stage.PLENARY_VOTE,
                topic_id=state.topic_id,
                sponsor_count=state.sponsor_count,
                agent_is_sponsor=state.agent_is_sponsor,
                committee_yes=yes,
                committee_no=no,
                committee_abstain=abstain,
                plenary_yes=0,
                plenary_no=0,
                plenary_abstain=0,
                t=state.t + 1,
                # Preserve text fields
                draft_text=state.draft_text,
                title=state.title,
                resolution_symbol=state.resolution_symbol,
            )

        elif state.stage == Stage.PLENARY_VOTE:
            # Sample plenary vote outcome
            yes, no, abstain = self.sample_vote_outcome(
                state.sponsor_count,
                Stage.PLENARY_VOTE,
            )

            return State(
                stage=Stage.TERMINAL,
                topic_id=state.topic_id,
                sponsor_count=state.sponsor_count,
                agent_is_sponsor=state.agent_is_sponsor,
                committee_yes=state.committee_yes,
                committee_no=state.committee_no,
                committee_abstain=state.committee_abstain,
                plenary_yes=yes,
                plenary_no=no,
                plenary_abstain=abstain,
                t=state.t + 1,
                # Preserve text fields
                draft_text=state.draft_text,
                title=state.title,
                resolution_symbol=state.resolution_symbol,
            )

        else:  # TERMINAL
            # Stay in terminal
            return state
