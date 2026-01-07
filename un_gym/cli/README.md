# UN Deliberation Gym - Command-Line Tools

Production-ready CLI tools for the UN Deliberation Gym.

## Installation

```bash
uv sync
```

## Tools

### 1. Interactive Player

Step through gym episodes interactively or watch expert (historical) behavior.

```bash
# Interactive mode (you choose actions)
uv run python -m un_gym.cli.play --country France

# Expert mode (auto-play historical actions)
uv run python -m un_gym.cli.play --country Germany --expert

# Custom trajectory
uv run python -m un_gym.cli.play \
    --trajectory path/to/trajectory.json \
    --country China \
    --seed 42
```

**Options:**
- `--country, -c`: Country to play as (default: France)
- `--trajectory, -t`: Trajectory JSON file (default: scratch/220.json)
- `--seed, -s`: Random seed for reproducibility
- `--expert, -e`: Expert mode (auto-play using historical actions)

**Features:**
- Rich terminal UI with color-coded panels
- Step-by-step state visualization
- Action history tracking
- Expert trajectory comparison
- Two modes: interactive or auto-play

### 2. Web Visualization Generator

Generate standalone HTML visualizations with embedded trajectory data.

```bash
# Generate visualization
uv run python -m un_gym.cli.generate_web_viz \
    --country France \
    --trajectory scratch/220.json \
    --output viz_france.html

# Open in browser
open viz_france.html
```

**Options:**
- `--country, -c`: Country perspective (default: France)
- `--trajectory, -t`: Trajectory JSON file (default: scratch/220.json)
- `--output, -o`: Output HTML file (default: scratch/gym_viz_enhanced.html)

**Features:**
- Standalone HTML (no server needed)
- Full resolution text in scrollable panel
- Expert mode toggle
- Real UN vote tallies embedded
- Stage progress indicator
- Color-coded action buttons
- History panel

## Examples

### Compare Different Countries

```bash
# Generate visualizations for different perspectives
uv run python -m un_gym.cli.generate_web_viz --country Germany -o sponsor.html
uv run python -m un_gym.cli.generate_web_viz --country "Iran (Islamic Republic of)" -o opponent.html
uv run python -m un_gym.cli.generate_web_viz --country China -o neutral.html

# Open all three
open sponsor.html opponent.html neutral.html
```

### Debug Trajectory

```bash
# Use expert mode to see exactly what happened
uv run python -m un_gym.cli.play \
    --trajectory trajectory_A_RES_78_220.json \
    --country France \
    --expert
```

### Demo for Presentation

```bash
# Generate polished web visualization
uv run python -m un_gym.cli.generate_web_viz \
    --country France \
    --trajectory scratch/220.json \
    --output demo.html

# Share demo.html - completely standalone!
```

## Programmatic Usage

You can also import and use these tools in your own scripts:

```python
from un_gym.cli import play, generate_web_viz

# Or import the main functions directly
from un_gym.cli.play import main as play_main
from un_gym.cli.generate_web_viz import generate_html
```

## Migration from scratch/

These tools were moved from `scratch/` to `un_gym/cli/` for better organization.

**Old usage (still works):**
```bash
uv run python scratch/play_gym.py --country France
uv run python scratch/generate_web_viz.py --country France
```

**New usage (recommended):**
```bash
uv run python -m un_gym.cli.play --country France
uv run python -m un_gym.cli.generate_web_viz --country France
```

## Help

```bash
# Get help for any tool
uv run python -m un_gym.cli.play --help
uv run python -m un_gym.cli.generate_web_viz --help
```

## See Also

- **Full documentation:** [docs/gym.md](../../docs/gym.md)
- **Quick reference:** [docs/gym_quickref.md](../../docs/gym_quickref.md)
- **Expert mode guide:** [scratch/EXPERT_MODE_README.md](../../scratch/EXPERT_MODE_README.md)
