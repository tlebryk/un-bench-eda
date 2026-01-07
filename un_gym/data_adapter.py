"""Adapter to convert trajectory JSON to gym episodes."""

from typing import Dict, List, Optional, Tuple
from .spaces import State, Stage, Action
import json


def load_trajectory(filepath: str) -> Dict:
    """Load trajectory from JSON file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def extract_country_action(
    timestep: Dict,
    country: str,
) -> Optional[Action]:
    """
    Extract what action a country took at a given timestep.

    Returns None if country didn't take an explicit action.
    """
    stage = timestep['stage']

    if stage == 'draft_submission':
        # Check if country is in sponsors list
        sponsors = timestep['action'].get('sponsors', [])
        if country in sponsors:
            return Action.COSPONSOR
        return Action.NO_ACTION

    elif stage == 'committee_vote' or stage == 'plenary_vote':
        # Check which list country is in
        votes = timestep['action'].get('votes', {})
        if country in votes.get('in_favour', []):
            return Action.VOTE_YES
        elif country in votes.get('against', []):
            return Action.VOTE_NO
        elif country in votes.get('abstaining', []):
            return Action.VOTE_ABSTAIN
        # Country might not have voted (not present)
        return None

    return None


def extract_text_fields(trajectory: Dict) -> Dict[str, Optional[str]]:
    """
    Extract text fields from trajectory for State objects.

    Returns dict with draft_text, title, resolution_symbol.
    """
    metadata = trajectory.get('metadata', {})
    timesteps = trajectory.get('timesteps', [])

    # Find draft submission step
    draft_step = next((t for t in timesteps if t['stage'] == 'draft_submission'), None)

    draft_text = None
    if draft_step:
        draft_text = draft_step.get('action', {}).get('draft_text')

    return {
        'draft_text': draft_text,
        'title': metadata.get('title'),
        'resolution_symbol': metadata.get('symbol'),
    }


def trajectory_to_episode(
    trajectory: Dict,
    country: str,
) -> List[Tuple[State, Action, State, float, bool]]:
    """
    Convert trajectory to episode from country's perspective.

    Returns list of (state, action, next_state, reward, done) tuples.
    States include text fields (draft_text, title, resolution_symbol).
    """
    timesteps = trajectory['timesteps']
    metadata = trajectory['metadata']

    # Find key timesteps
    draft_step = next((t for t in timesteps if t['stage'] == 'draft_submission'), None)
    committee_step = next((t for t in timesteps if t['stage'] == 'committee_vote'), None)
    plenary_step = next((t for t in timesteps if t['stage'] == 'plenary_vote'), None)

    if not (draft_step and committee_step and plenary_step):
        raise ValueError(f"Trajectory {metadata['symbol']} missing required stages")

    # Extract text fields
    text_fields = extract_text_fields(trajectory)

    # Extract sponsor list
    sponsors = draft_step['action'].get('sponsors', [])
    agent_is_sponsor = country in sponsors

    # Extract vote tallies
    committee_votes = committee_step['observation'].get('vote_tally', {})
    plenary_votes = plenary_step['observation'].get('vote_tally', {})

    # Final outcome
    final_outcome = metadata.get('final_outcome', 'adopted')

    # Build episode
    episode = []

    # State 0: DRAFT stage
    s0 = State(
        stage=Stage.DRAFT,
        topic_id=0,  # placeholder
        sponsor_count=len(sponsors),
        agent_is_sponsor=False,  # not yet
        committee_yes=0,
        committee_no=0,
        committee_abstain=0,
        plenary_yes=0,
        plenary_no=0,
        plenary_abstain=0,
        t=0,
        **text_fields,
    )

    # Action 0: COSPONSOR or NO_ACTION
    a0 = Action.COSPONSOR if agent_is_sponsor else Action.NO_ACTION

    # State 1: Still DRAFT, but agent may have joined sponsors
    s1 = State(
        stage=Stage.DRAFT,
        topic_id=0,
        sponsor_count=len(sponsors),
        agent_is_sponsor=agent_is_sponsor,
        committee_yes=0,
        committee_no=0,
        committee_abstain=0,
        plenary_yes=0,
        plenary_no=0,
        plenary_abstain=0,
        t=1,
        **text_fields,
    )

    episode.append((s0, a0, s1, 0.0, False))

    # State 2: COMMITTEE_VOTE stage
    s2 = State(
        stage=Stage.COMMITTEE_VOTE,
        topic_id=0,
        sponsor_count=len(sponsors),
        agent_is_sponsor=agent_is_sponsor,
        committee_yes=0,  # vote hasn't happened yet
        committee_no=0,
        committee_abstain=0,
        plenary_yes=0,
        plenary_no=0,
        plenary_abstain=0,
        t=2,
        **text_fields,
    )

    # Action 1: committee vote
    a1 = extract_country_action(committee_step, country)
    if a1 is None:
        a1 = Action.VOTE_ABSTAIN  # default if not found

    # State 3: PLENARY_VOTE stage (committee results known)
    s3 = State(
        stage=Stage.PLENARY_VOTE,
        topic_id=0,
        sponsor_count=len(sponsors),
        agent_is_sponsor=agent_is_sponsor,
        committee_yes=committee_votes.get('yes', 0),
        committee_no=committee_votes.get('no', 0),
        committee_abstain=committee_votes.get('abstain', 0),
        plenary_yes=0,  # vote hasn't happened yet
        plenary_no=0,
        plenary_abstain=0,
        t=3,
        **text_fields,
    )

    episode.append((s1, a1, s3, 0.0, False))

    # Action 2: plenary vote
    a2 = extract_country_action(plenary_step, country)
    if a2 is None:
        a2 = Action.VOTE_ABSTAIN

    # State 4: TERMINAL (all votes known)
    s4 = State(
        stage=Stage.TERMINAL,
        topic_id=0,
        sponsor_count=len(sponsors),
        agent_is_sponsor=agent_is_sponsor,
        committee_yes=committee_votes.get('yes', 0),
        committee_no=committee_votes.get('no', 0),
        committee_abstain=committee_votes.get('abstain', 0),
        plenary_yes=plenary_votes.get('yes', 0),
        plenary_no=plenary_votes.get('no', 0),
        plenary_abstain=plenary_votes.get('abstain', 0),
        t=4,
        **text_fields,
    )

    # Compute reward
    reward = compute_reward(agent_is_sponsor, final_outcome)

    episode.append((s3, a2, s4, reward, True))

    return episode


def compute_reward(agent_is_sponsor: bool, outcome: str) -> float:
    """
    Simple reward function.

    Sponsors want adoption, get +1 if adopted, -1 if rejected.
    Non-sponsors get 0 (neutral).
    """
    if not agent_is_sponsor:
        return 0.0

    if outcome.lower() == 'adopted':
        return 1.0
    else:
        return -1.0
