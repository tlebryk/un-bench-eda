"""Main UN Deliberation Gym environment."""

from typing import List, Dict, Tuple, Optional
import numpy as np
from .spaces import State, Stage, Action, is_action_valid
from .dynamics import EmpiricalDynamics
from .data_adapter import compute_reward, extract_text_fields


class UNDeliberationEnv:
    """
    UN Resolution deliberation environment.

    OpenAI Gym-style interface for single-agent (country) interaction
    with UN resolution process.
    """

    def __init__(
        self,
        country: str,
        trajectories: List[Dict],
        seed: Optional[int] = None,
    ):
        """
        Initialize environment.

        Args:
            country: Which country's perspective (affects rewards)
            trajectories: Historical trajectory data for sampling dynamics
            seed: Random seed for reproducibility
        """
        self.country = country
        self.trajectories = trajectories
        self.dynamics = EmpiricalDynamics(trajectories)

        self.rng = np.random.default_rng(seed)

        # Current episode state
        self.state: Optional[State] = None
        self.current_trajectory: Optional[Dict] = None
        self.episode_done = False

        # Text fields for current episode (extracted once at reset)
        self._text_fields: Dict[str, Optional[str]] = {
            'draft_text': None,
            'title': None,
            'resolution_symbol': None,
        }

    def reset(
        self,
        resolution_id: Optional[str] = None,
        trajectory: Optional[Dict] = None,
    ) -> np.ndarray:
        """
        Reset environment to start new episode.

        Args:
            resolution_id: Specific resolution to load (optional)
            trajectory: Specific trajectory dict to use (optional)

        Returns:
            Initial state as vector
        """
        if trajectory is not None:
            self.current_trajectory = trajectory
        elif resolution_id is not None:
            # Find trajectory by ID
            self.current_trajectory = next(
                (t for t in self.trajectories if t['trajectory_id'] == resolution_id),
                None
            )
            if self.current_trajectory is None:
                raise ValueError(f"Resolution {resolution_id} not found")
        else:
            # Sample random trajectory
            idx = self.rng.integers(0, len(self.trajectories))
            self.current_trajectory = self.trajectories[idx]

        # Extract initial state from trajectory
        draft_step = next(
            (t for t in self.current_trajectory['timesteps']
             if t['stage'] == 'draft_submission'),
            None
        )

        if draft_step is None:
            raise ValueError("Trajectory missing draft_submission stage")

        sponsors = draft_step['action'].get('sponsors', [])

        # Extract text fields for this episode
        self._text_fields = extract_text_fields(self.current_trajectory)

        # Initial state: DRAFT stage, agent hasn't acted yet
        self.state = State(
            stage=Stage.DRAFT,
            topic_id=0,  # placeholder
            sponsor_count=len(sponsors),
            agent_is_sponsor=False,
            committee_yes=0,
            committee_no=0,
            committee_abstain=0,
            plenary_yes=0,
            plenary_no=0,
            plenary_abstain=0,
            t=0,
            **self._text_fields,
        )

        self.episode_done = False

        return self.state.to_vec()

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, Dict]:
        """
        Take action in environment.

        Args:
            action: Action index (0-4, see Action enum)

        Returns:
            (next_state_vec, reward, done, info)
        """
        if self.state is None:
            raise RuntimeError("Must call reset() before step()")

        if self.episode_done:
            raise RuntimeError("Episode is done, call reset()")

        action = Action(action)

        # Validate action
        if not is_action_valid(self.state, action):
            # Invalid action treated as NO_ACTION
            print(f"Warning: Invalid action {action} for stage {self.state.stage}")
            action = Action.NO_ACTION

        # Transition to next state
        next_state = self.dynamics.transition(self.state, action, self.rng)

        # Compute reward (only non-zero at terminal)
        reward = 0.0
        done = False

        if next_state.stage == Stage.TERMINAL:
            # Determine outcome from vote tally
            outcome = 'adopted' if next_state.plenary_yes > next_state.plenary_no else 'rejected'
            reward = compute_reward(next_state.agent_is_sponsor, outcome)
            done = True
            self.episode_done = True

        self.state = next_state

        info = {
            'stage': next_state.stage.name,
            'sponsor_count': next_state.sponsor_count,
            'agent_is_sponsor': next_state.agent_is_sponsor,
            # Text fields for LLM-based agents
            'draft_text': self._text_fields.get('draft_text'),
            'title': self._text_fields.get('title'),
            'resolution_symbol': self._text_fields.get('resolution_symbol'),
        }

        return next_state.to_vec(), reward, done, info

    def render(self, mode='human'):
        """Print human-readable state."""
        if self.state is None:
            print("Environment not initialized. Call reset().")
            return

        print(f"\n=== UN Deliberation Environment ===")
        print(f"Country: {self.country}")
        print(f"Stage: {self.state.stage.name}")
        print(f"Timestep: {self.state.t}")
        print(f"Sponsors: {self.state.sponsor_count} (agent is sponsor: {self.state.agent_is_sponsor})")

        if self.state.committee_yes > 0:
            print(f"Committee vote: {self.state.committee_yes} yes, {self.state.committee_no} no, {self.state.committee_abstain} abstain")

        if self.state.plenary_yes > 0:
            print(f"Plenary vote: {self.state.plenary_yes} yes, {self.state.plenary_no} no, {self.state.plenary_abstain} abstain")

        print("=" * 35)

    def get_state_dim(self) -> int:
        """Get dimension of state vector."""
        return State.get_dim()

    def get_action_dim(self) -> int:
        """Get number of discrete actions."""
        return 5

    def get_text(self) -> Dict[str, Optional[str]]:
        """
        Get raw text fields for current episode.

        Returns dict with:
            - draft_text: Full draft resolution text
            - title: Resolution title
            - resolution_symbol: Resolution symbol (e.g., "A/RES/78/220")

        For LLM-based agents that want to process raw text directly.
        """
        return self._text_fields.copy()

    def get_transition_data(self) -> List[Tuple]:
        """
        Extract (s, a, s', r, done) tuples from all historical trajectories.

        Useful for training world models.

        Returns:
            List of (state_vec, action, next_state_vec, reward, done) tuples
        """
        from .data_adapter import trajectory_to_episode

        transitions = []
        for traj in self.trajectories:
            try:
                episode = trajectory_to_episode(traj, self.country)
                for s, a, s_next, r, done in episode:
                    transitions.append((
                        s.to_vec(),
                        int(a),
                        s_next.to_vec(),
                        r,
                        done,
                    ))
            except (ValueError, KeyError) as e:
                # Skip trajectories with missing data
                print(f"Warning: Skipping trajectory {traj.get('trajectory_id', 'unknown')}: {e}")
                continue

        return transitions
