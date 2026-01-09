# UN Deliberation Gym

A reinforcement learning environment for modeling UN resolution negotiation and voting processes. Designed for world modeling, inverse reinforcement learning (IRL), and multi-agent research.

## Table of Contents

1. [Overview](#overview)
2. [Installation & Quick Start](#installation--quick-start)
3. [Core Concepts](#core-concepts)
4. [API Reference](#api-reference)
5. [Interactive Tools](#interactive-tools)
6. [Evaluation & Testing](#evaluation--testing)
7. [Data Integration](#data-integration)
8. [Research Directions](#research-directions)
9. [Future Enhancements](#future-enhancements)

---

## Overview

### What is the UN Deliberation Gym?

A single-agent OpenAI Gym-style environment where an agent (representing a country) decides whether to cosponsor and how to vote on UN resolutions. The environment models the public observable state of the resolution process.

**Module name:** `un_gym` (to avoid conflicts with OpenAI's gym package)

### Key Features

- **OpenAI Gym API:** Standard `reset()`, `step()`, `render()` interface
- **Single-agent perspective:** Model one country's decision-making
- **Historical data:** Built from real UN resolution trajectories
- **Hybrid state representation:** 14-dim vectors for classic RL + raw text for LLM agents
- **Expert trajectories:** Extract real country behavior for IRL
- **Interactive visualization:** Terminal and web interfaces for exploration
- **Comprehensive testing:** 41 tests covering all core functionality

### Current Status

**Phase 0 Complete** ✓

Implemented:
- Core environment (`un_gym/env.py`)
- State/action spaces (`un_gym/spaces.py`)
- Data adapter (`un_gym/data_adapter.py`)
- Empirical dynamics (`un_gym/dynamics.py`)
- Metrics & evaluation (`un_gym/metrics.py`)
- Visualization (`un_gym/viz.py`)
- Interactive UI (`un_gym/interactive.py`)
- CLI tools (`un_gym/cli/`)

---

## Installation & Quick Start

### Setup

```bash
# Install dependencies (if not already done)
uv sync

# Run tests
uv run pytest tests/gym/ -v
```

### Quick Demo

```bash
# Interactive terminal UI (choose actions yourself)
uv run python -m un_gym.cli.play --country France

# Expert mode (watch historical actions)
uv run python -m un_gym.cli.play --country Germany --expert

# Generate web visualization
uv run python -m un_gym.cli.generate_web_viz \
    --country France \
    --output viz_france.html

# Open in browser
open viz_france.html
```

### Programmatic Usage

```python
from un_gym import UNDeliberationEnv, load_trajectory

# Load trajectory
traj = load_trajectory('scratch/220.json')

# Create environment
env = UNDeliberationEnv(
    country="France",
    trajectories=[traj],
    seed=42
)

# Run episode
obs = env.reset()
done = False

while not done:
    action = env.action_space.sample()  # or your policy
    obs, reward, done, info = env.step(action)
    env.render()
```

---

## Core Concepts

### State Space

State has **two parts**:

1. **Structured fields (14-dim vector)** - for RL algorithms via `state.to_vec()`
2. **Raw text fields (optional)** - for LLM-based agents

```python
State = {
    # Stage (one-hot encoded in vector, 4 dims)
    'stage': Enum[DRAFT, COMMITTEE_VOTE, PLENARY_VOTE, TERMINAL],

    # Resolution representation
    'topic_id': int,           # Categorical (0-N topic clusters)

    # Sponsor information
    'sponsor_count': int,      # Total number of sponsors
    'agent_is_sponsor': bool,  # Whether this country is a sponsor

    # Committee voting (0 until committee stage)
    'committee_yes': int,
    'committee_no': int,
    'committee_abstain': int,

    # Plenary voting (0 until plenary stage)
    'plenary_yes': int,
    'plenary_no': int,
    'plenary_abstain': int,

    # Timestep
    't': int,

    # --- Text fields (NOT in vector, for LLM agents) ---
    'draft_text': Optional[str],       # Full draft resolution text
    'title': Optional[str],            # Resolution title
    'resolution_symbol': Optional[str] # e.g., "A/RES/78/220"
}
```

**Vectorization:** `state.to_vec()` → `np.array([...])` (14 floats, excludes text)

**Text access:** Raw text available via:
- `state.draft_text`, `state.title`, `state.resolution_symbol`
- `env.get_text()` returns dict with all text fields
- `info` dict from `step()` includes text fields

### Action Space

**Discrete(5)** - action semantics depend on current stage:

```python
Action = Enum(
    COSPONSOR = 0,       # Valid in DRAFT stage
    VOTE_YES = 1,        # Valid in COMMITTEE_VOTE, PLENARY_VOTE
    VOTE_NO = 2,         # Valid in COMMITTEE_VOTE, PLENARY_VOTE
    VOTE_ABSTAIN = 3,    # Valid in COMMITTEE_VOTE, PLENARY_VOTE
    NO_ACTION = 4        # Always valid
)
```

**Action validity:**
- `DRAFT`: COSPONSOR or NO_ACTION
- `COMMITTEE_VOTE`: VOTE_YES, VOTE_NO, VOTE_ABSTAIN
- `PLENARY_VOTE`: VOTE_YES, VOTE_NO, VOTE_ABSTAIN
- `TERMINAL`: Only NO_ACTION (episode done)

Invalid actions → treated as `NO_ACTION` (with warning)

### Transition Dynamics

**Deterministic:** Stage progression is fixed:
```
DRAFT → COMMITTEE_VOTE → PLENARY_VOTE → TERMINAL
```

**Stochastic:**
- Other countries' cosponsorship: sampled from historical base rates
- Vote outcomes: sampled from empirical distributions conditioned on sponsors/topic
- Currently uses empirical distributions; future phases will use learned dynamics models

### Reward Function

Simple proxy reward, evaluated at `TERMINAL` state:

```python
def compute_reward(agent_is_sponsor: bool, outcome: str) -> float:
    """
    Sponsors want adoption → +1 if adopted, -1 if rejected
    Non-sponsors → 0 (neutral, or define preference later)
    """
    if not agent_is_sponsor:
        return 0.0
    return 1.0 if outcome == 'adopted' else -1.0
```

**Note:** This is a placeholder. Real reward is country-specific (inferred via IRL).

### Episode Structure

Typical episode has **3-4 steps**:

```
reset()           → state (DRAFT, t=0)
step(COSPONSOR)   → state (DRAFT, t=1, agent_is_sponsor=True)
step(NO_ACTION)   → state (COMMITTEE_VOTE, t=2)
step(VOTE_YES)    → state (PLENARY_VOTE, t=3, committee results filled)
step(VOTE_YES)    → state (TERMINAL, t=4, final outcome)
                    done=True, reward computed
```

---

## API Reference

### Environment Class

```python
class UNDeliberationEnv:
    def __init__(
        self,
        country: str,
        trajectories: List[Dict],
        seed: Optional[int] = None
    ):
        """
        Args:
            country: Which country's perspective (affects rewards)
            trajectories: Historical trajectory data for dynamics
            seed: Random seed for reproducibility
        """

    def reset(
        self,
        resolution_id: Optional[str] = None,
        trajectory: Optional[Dict] = None
    ) -> np.ndarray:
        """
        Reset environment to start new episode.

        Args:
            resolution_id: Specific resolution ID (optional)
            trajectory: Specific trajectory dict (optional)

        Returns:
            Initial state vector (14-dim)
        """

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, Dict]:
        """
        Take action, return (state, reward, done, info).

        Args:
            action: Action index (0-4)

        Returns:
            state: Next state vector (14-dim)
            reward: Reward (non-zero only at terminal)
            done: Episode finished?
            info: Dict with stage, sponsor_count, etc.
        """

    def render(self, mode='human'):
        """Print human-readable state to console."""

    def get_state_dim(self) -> int:
        """Dimension of state vector (14)."""

    def get_action_dim(self) -> int:
        """Number of discrete actions (5)."""

    def get_text(self) -> Dict[str, Optional[str]]:
        """
        Get raw text fields for current episode.

        Returns dict with:
            - draft_text: Full draft resolution text
            - title: Resolution title
            - resolution_symbol: Resolution symbol (e.g., "A/RES/78/220")

        For LLM-based agents that process raw text directly.
        """

    def get_transition_data(self) -> List[Tuple]:
        """
        Extract (s, a, s', r, done) tuples from all trajectories.
        For training world models or IRL.
        """
```

### Data Adapter Functions

```python
from un_gym.data_adapter import (
    load_trajectory,
    trajectory_to_episode,
    extract_country_action
)

# Load trajectory JSON
traj = load_trajectory('path/to/trajectory.json')

# Convert to episode from country perspective
episode = trajectory_to_episode(traj, country="France")
# Returns: List[(state, action, next_state, reward, done)]

# Extract what action a country took at timestep
action = extract_country_action(timestep, country="France")
# Returns: Action enum or None
```

### State/Action Utilities

```python
from un_gym.spaces import State, Stage, Action, is_action_valid

# Create state
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
    t=0
)

# Vectorize for neural nets
vec = state.to_vec()  # np.array, shape (14,)

# Reconstruct from vector
state2 = State.from_vec(vec)

# Check action validity
valid = is_action_valid(state, Action.COSPONSOR)  # True at DRAFT
```

---

## Interactive Tools

### Terminal UI

**Features:**
- Step-by-step state visualization
- Color-coded action validity
- Action history tracking
- Expert trajectory comparison
- Two modes: interactive (you choose) or expert (auto-play historical)

**Usage:**

```bash
# Interactive mode
uv run python -m un_gym.cli.play --country France

# Expert mode (auto-play)
uv run python -m un_gym.cli.play --country Germany --expert

# Custom trajectory
uv run python -m un_gym.cli.play \
    --trajectory path/to/traj.json \
    --country China \
    --seed 42
```

**Interface:**
- **Current State Panel:** Stage, timestep, sponsors, votes
- **Available Actions Panel:** Valid/invalid indicators
- **History Panel:** Past actions and rewards
- **Expert Comparison:** At end, see what country actually did

### Web Visualization

**Features:**
- Beautiful browser-based interface
- Resolution text display (scrollable)
- Expert mode toggle
- Progress indicator through stages
- Color-coded action buttons
- Standalone HTML (no server needed)

**Usage:**

```bash
# Generate visualization
uv run python -m un_gym.cli.generate_web_viz \
    --country France \
    --trajectory scratch/220.json \
    --output viz_france.html

# Open in browser
open viz_france.html
```

**Interface elements:**
- **Resolution Text Panel:** Full draft text (scrollable)
- **Stage Indicator:** Visual progress (DRAFT → COMMITTEE → PLENARY → DONE)
- **State Grid:** Timestep, sponsors, votes
- **Action Buttons:** Color-coded (green=cosponsor, blue=yes, red=no)
- **Expert Mode Toggle:** Switch between interactive and auto-play
- **History Panel:** Actions taken with rewards

**Key feature: Resolution text integration**
- Shows full draft resolution text
- Extracted from `draft_submission` timestep
- Helps understand voting context
- Enables future text-based features

### Comparison: Terminal vs Web

| Feature | Terminal UI | Web UI |
|---------|-------------|--------|
| **Setup** | Command line | Open HTML file |
| **Data** | Real Python backend | Embedded JSON |
| **Speed** | Fast keyboard | Mouse/keyboard |
| **Sharing** | SSH-friendly | Share HTML file |
| **Text** | Metadata only | Full resolution text |

**Use Terminal when:** Developing, debugging, SSH environment
**Use Web when:** Demoing, sharing, offline viewing

---

## Evaluation & Testing

### Test Suite

**33 tests, all passing** (located in `tests/gym/`)

```bash
# Run all tests
uv run pytest tests/gym/ -v

# Run specific test file
uv run pytest tests/gym/test_env.py -v

# With coverage
uv run pytest tests/gym/ --cov=un_gym
```

**Test coverage:**
- `test_spaces.py` - State vectorization, action validity
- `test_env.py` - Environment operations, rewards, reproducibility
- `test_data_adapter.py` - Trajectory parsing, country actions
- `test_metrics.py` - Statistics, comparisons, evaluation

### Metrics Module

Track and evaluate episodes:

```python
from un_gym.metrics import (
    EpisodeMetrics,
    compare_trajectories,
    evaluate_world_model,
    evaluate_policy
)

# Track statistics
metrics = EpisodeMetrics()
metrics.add_episode(trajectory)
stats = metrics.compute_stats()
# Returns: num_episodes, avg_length, action_distribution,
#          reward_mean, reward_std, sponsor_rate

# Compare trajectories
result = compare_trajectories(real_traj, simulated_traj)
# Returns: action_accuracy, outcome_match, length_diff

# Evaluate world model
metrics = evaluate_world_model(model, test_transitions)
# Returns: mse, rmse, discrete_accuracy, num_predictions

# Evaluate policy
metrics = evaluate_policy(policy, test_episodes)
# Returns: action_accuracy, avg_return
```

### Visualization

Generate plots for analysis:

```python
from un_gym.viz import (
    plot_trajectory,
    plot_action_distribution,
    plot_country_comparison,
    plot_training_metrics
)

# Single trajectory (4 panels: stage, actions, sponsors, votes)
plot_trajectory(trajectory, country="France", save_path='fig.png')

# Action distribution
plot_action_distribution(episodes, save_path='actions.png')

# Compare countries
plot_country_comparison(
    episodes_by_country,
    save_path='comparison.png'
)

# Training curves
plot_training_metrics(train_losses, val_losses, save_path='train.png')
```

### Evaluation Strategies

**For World Models:**
```python
# Extract transitions
transitions = env.get_transition_data()

# Train/test split
train, test = train_test_split(transitions, test_size=0.2)

# Evaluate
metrics = evaluate_world_model(model, test)
print(f"RMSE: {metrics['rmse']:.3f}")
print(f"Discrete accuracy: {metrics['discrete_accuracy']:.2%}")
```

**For IRL (Inverse Reinforcement Learning):**
```python
# Collect expert demonstrations
demos = env.get_transition_data()

# Infer reward function
reward_fn = max_entropy_irl(env, demos)

# Evaluate on held-out episodes
metrics = evaluate_policy(policy, test_episodes)
print(f"Action accuracy: {metrics['action_accuracy']:.2%}")
```

**For Simulators:**
- Vote distribution matching (KL divergence)
- Sponsor count distribution
- Outcome rate (% adopted)
- Statistical tests (KS test, chi-square)

---

## Data Integration

### Current State

**Trajectory JSON structure:**
```{code-block} text
{
  "trajectory_id": "A/RES/78/220",
  "metadata": {
    "symbol": "A/RES/78/220",
    "title": "Situation of human rights in Iran...",
    "session": 78,
    "committee": 3,
    "final_outcome": "adopted"
  },
  "timesteps": [
    {
      "stage": "draft_submission",
      "action": {
        "draft_text": "The General Assembly, ...",
        "draft_text_full_length": 29594,
        "sponsors": ["Albania", "Germany", ...]
      }
    },
    {
      "stage": "committee_vote",
      "observation": {
        "vote_tally": {"yes": 80, "no": 29, "abstain": 65}
      }
    },
    ...
  ]
}
```

**What's extracted:**
- Stage progression
- Sponsor lists
- Vote tallies (committee and plenary)
- Final outcome
- ✅ Draft text (available in State and via `env.get_text()`)
- ✅ Title (available in State and via `env.get_text()`)
- ✅ Resolution symbol (available in State and via `env.get_text()`)

**What's NOT yet in state:**
- ❌ Amendment text
- ❌ Statement text
- ❌ Country voting history
- ❌ Regional bloc information
- ❌ Topic embeddings beyond categorical ID

### Text Data Integration

**Hybrid approach:** Text fields are available in State but NOT in `to_vec()`:

```python
# Access text directly from state
state.draft_text      # Full draft resolution text
state.title           # Resolution title
state.resolution_symbol  # e.g., "A/RES/78/220"

# Or from environment
text_dict = env.get_text()

# Or from step() info dict
obs, reward, done, info = env.step(action)
info['draft_text']    # Same text fields
```

**Design rationale:**
- Classic RL algorithms: Use `state.to_vec()` (14-dim, no text)
- LLM-based agents: Access raw text via `state.draft_text` or `env.get_text()`
- Hybrid agents: Can use both

**Current display:**
- ✅ Web visualization shows full draft text in scrollable panel
- ✅ State object includes text fields
- ✅ `step()` info dict includes text fields

### Strategic Insights Available

Based on `scratch/SUMMARY_strategic_insights.md`:

**What we have:**
- ✅ Vote tallies (committee & plenary)
- ✅ Vote switching (countries changing votes)
- ✅ Sponsor counts
- ✅ Timeline reconstruction

**Critical gaps (not in gym yet):**
- ❌ Co-sponsor additions over time
- ❌ Draft revisions (L.41 vs L.41/Rev.1)
- ❌ Regional bloc analysis
- ❌ Statement position classification

---

## Research Directions

### 1. World Models for Legislation

**Goal:** Learn transition dynamics P(s' | s, a)

**Approach:**
```python
# Extract transitions
transitions = env.get_transition_data()

# Train model
model = TransitionModel(state_dim=14, action_dim=5)
model.fit(transitions)

# Evaluate
metrics = evaluate_world_model(model, test_transitions)
```

**Metrics:**
- Next-state prediction accuracy
- Vote count RMSE
- Trajectory rollout quality

**Research question:** Can we predict vote outcomes from draft stage?

### 2. Inverse Reinforcement Learning

**Goal:** Infer country preferences from behavior

**Approach:**
```python
# Collect expert demos for a country
demos = [trajectory_to_episode(t, "France") for t in trajectories]

# Maximum entropy IRL
reward_weights = max_entropy_irl(env, demos)

# Validate on held-out resolutions
accuracy = predict_votes_on_test_set(reward_weights, test_resolutions)
```

**Research questions:**
- Do trajectory-based preferences predict votes better than vote-only models?
- Can we cluster countries by learned reward functions?
- Does sponsorship reveal preferences votes miss?

### 3. Parliament Simulator

**Goal:** Build RL environment for counterfactual analysis

**Current status:**
- ✓ Single-agent environment operational
- ✓ Empirical dynamics from historical data
- ⚠️ Multi-agent extension planned
- ⚠️ Language actions (amendments, statements) not implemented

**Next steps:**
- Learn vote prediction model P(outcome | state)
- Extend to multi-agent (all countries act simultaneously)
- Add amendment proposal actions
- Enable counterfactual rollouts

---

## Future Enhancements

### Phase 1: Richer State Representation

**Text integration options:**

1. **Sentence embeddings** (simplest)
   ```python
   from sentence_transformers import SentenceTransformer

   model = SentenceTransformer('all-MiniLM-L6-v2')
   draft_embedding = model.encode(draft_text)  # 384-dim

   # Add to state vector
   state_vec = np.concatenate([
       state.to_vec(),      # 14-dim
       draft_embedding      # 384-dim
   ])  # Total: 398-dim
   ```

2. **Topic modeling** (intermediate)
   - Cluster resolutions by topic (LDA, BERTopic)
   - Replace categorical topic_id with topic embedding
   - Encode topic distribution (e.g., 50-dim topic vector)

3. **Paragraph embeddings** (advanced)
   - Embed operative paragraphs separately
   - Model amendment targets
   - Enable paragraph-level reasoning

**Decision factors:**
- **Model size:** Sentence embeddings add 384 dims
- **Training data:** Need multiple trajectories for supervised learning
- **Interpretability:** Categorical topics more interpretable than embeddings
- **Downstream tasks:** World models need fixed-size inputs

**Recommendation for next implementer:**
- Start with sentence embeddings of full draft text
- Add as optional feature (expand state dim from 14 to 398)
- Evaluate whether text features improve vote prediction
- Consider pre-computing embeddings and caching

### Phase 2: Enhanced Context

**Additional state features:**

1. **Voting history:**
   - Past votes by this country on similar resolutions
   - Historical co-sponsorship patterns
   - Country-country voting similarity

2. **Regional blocs:**
   - Country → region mapping
   - Bloc cohesion metrics
   - Deviation from bloc patterns

3. **Co-sponsor dynamics:**
   - Track sponsor additions over time
   - Model coalition formation
   - Predict sponsor recruitment

4. **Statement sentiment:**
   - Classify statements (support/oppose/neutral)
   - Extract key arguments
   - Link to voting behavior

### Phase 3: Multi-Agent Extension

**Current:** Single agent (one country's perspective)
**Future:** Multi-agent (all countries simultaneously)

**Challenges:**
- Coordination (who speaks when?)
- Observation space (what each agent sees)
- Reward structure (country-specific preferences)
- Dynamics complexity (strategic interactions)

**Approach:**
- Extend to MARL environment
- Model country interdependencies
- Enable coalition formation strategies
- Support amendment negotiation

### Phase 4: Language Actions

**Currently:** Actions are discrete (cosponsor, vote yes/no/abstain)
**Future:** Language-based actions (propose amendments, make statements)

**Required:**
- Amendment proposal action
- Statement text generation
- Debate turn-taking
- Text diff tracking (draft revisions)

**Integration with text features:**
- Use draft embeddings to guide amendment proposals
- Generate statements conditioned on state
- Model persuasion effects on other countries

---

## File Structure

```
un_gym/
├── __init__.py              # Package exports
├── env.py                   # Main UNDeliberationEnv class
├── spaces.py                # State/Action definitions
├── data_adapter.py          # JSON → episode conversion
├── dynamics.py              # Transition sampling (empirical)
├── metrics.py               # Evaluation functions
├── viz.py                   # Plotting utilities
├── interactive.py           # Terminal UI
└── cli/                     # Command-line tools
    ├── __init__.py
    ├── play.py              # Interactive/expert mode player
    └── generate_web_viz.py  # Web visualization generator

tests/gym/
├── test_spaces.py           # State/action tests
├── test_env.py              # Environment tests
├── test_data_adapter.py     # Data conversion tests
└── test_metrics.py          # Metrics tests

scratch/
├── 220.json                 # Example trajectory (Iran resolution)
├── gym_demo.py              # Basic usage demo
├── eval_demo.py             # Evaluation demo
└── (figures, sample viz)    # Short-lived assets only
```

---

## Summary

### What's Working Now ✓

- Single-agent RL environment with Gym API
- 14-dimensional state vectors for classic RL
- **Raw text fields** in State for LLM-based agents (hybrid approach)
- `env.get_text()` for convenient text access
- Text fields passed in `step()` info dict
- Expert trajectory extraction from historical data
- Interactive terminal and web UIs
- Expert mode (auto-play historical actions)
- Comprehensive testing (41 tests)
- Evaluation metrics and visualization

### Text Integration Complete ✓

The gym now supports a **hybrid approach**:
- **Classic RL:** Use `state.to_vec()` → 14-dim vector (unchanged)
- **LLM agents:** Access `state.draft_text`, `state.title`, `state.resolution_symbol`
- **Via env:** Call `env.get_text()` for dict of all text fields
- **Via info:** `step()` returns text in info dict

### Remaining Gaps ⚠️

- No paragraph-level representation
- No statement text integrated
- No amendment tracking
- No pre-computed embeddings (by design - agents do their own)

### Future Enhancements

1. **Sentence embeddings (optional utility):**
   - Provide helper to compute embeddings from raw text
   - Agents can use or ignore as needed

2. **Additional text fields:**
   - Amendment text when available
   - Statement text when available
   - Historical voting context

3. **Evaluation:**
   - Does text improve vote prediction?
   - Do text features help IRL infer preferences?

**For future implementers:** See [Data Integration](#data-integration) and [Future Enhancements](#future-enhancements) sections.
