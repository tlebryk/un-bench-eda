"""Interactive terminal UI for UN Deliberation Gym."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.text import Text
from rich.prompt import Prompt, IntPrompt
from rich import box
from .spaces import State, Stage, Action, is_action_valid
from .env import UNDeliberationEnv
from typing import List, Optional
import sys


class InteractiveGym:
    """Interactive terminal interface for stepping through gym episodes."""

    def __init__(self, env: UNDeliberationEnv, expert_mode: bool = False):
        self.env = env
        self.console = Console()
        self.history = []
        self.expert_mode = expert_mode
        self.expert_trajectory = None

    def render_state(self, state: State) -> Panel:
        """Render current state as a rich panel."""
        # Create state table
        state_table = Table(show_header=False, box=box.SIMPLE)
        state_table.add_column("Property", style="cyan")
        state_table.add_column("Value", style="yellow")

        state_table.add_row("Stage", state.stage.name)
        state_table.add_row("Timestep", str(state.t))
        state_table.add_row("Sponsor Count", str(state.sponsor_count))
        state_table.add_row("Agent Is Sponsor", "✓" if state.agent_is_sponsor else "✗")

        if state.committee_yes > 0:
            state_table.add_row("", "")  # Spacer
            state_table.add_row("[bold]Committee Vote[/bold]", "")
            state_table.add_row("  Yes", str(state.committee_yes))
            state_table.add_row("  No", str(state.committee_no))
            state_table.add_row("  Abstain", str(state.committee_abstain))

        if state.plenary_yes > 0:
            state_table.add_row("", "")  # Spacer
            state_table.add_row("[bold]Plenary Vote[/bold]", "")
            state_table.add_row("  Yes", str(state.plenary_yes))
            state_table.add_row("  No", str(state.plenary_no))
            state_table.add_row("  Abstain", str(state.plenary_abstain))

        return Panel(
            state_table,
            title=f"[bold green]Current State[/bold green]",
            border_style="green"
        )

    def render_actions(self, state: State) -> Panel:
        """Render available actions."""
        action_table = Table(show_header=True, box=box.SIMPLE)
        action_table.add_column("#", style="cyan", width=3)
        action_table.add_column("Action", style="yellow")
        action_table.add_column("Valid", style="green")

        for i, action in enumerate(Action):
            valid = is_action_valid(state, action)
            valid_text = "✓" if valid else "✗"
            style = "" if valid else "dim"
            action_table.add_row(str(i), action.name, valid_text, style=style)

        return Panel(
            action_table,
            title="[bold blue]Available Actions[/bold blue]",
            border_style="blue"
        )

    def render_history(self) -> Optional[Panel]:
        """Render action history."""
        if not self.history:
            return None

        history_table = Table(show_header=True, box=box.SIMPLE)
        history_table.add_column("Step", style="cyan", width=5)
        history_table.add_column("Action", style="yellow")
        history_table.add_column("Reward", style="green")

        for i, (action, reward) in enumerate(self.history):
            reward_str = f"{reward:+.1f}" if reward != 0 else "-"
            history_table.add_row(str(i), Action(action).name, reward_str)

        return Panel(
            history_table,
            title="[bold magenta]History[/bold magenta]",
            border_style="magenta"
        )

    def run(self):
        """Run interactive session."""
        self.console.clear()

        mode_text = "Expert Mode (Auto-play)" if self.expert_mode else "Interactive Mode"
        instructions = "Press Enter to see next expert action" if self.expert_mode else "Choose actions to step through the episode"

        self.console.print(Panel.fit(
            f"[bold cyan]UN Deliberation Gym - {mode_text}[/bold cyan]\n\n"
            f"Country: {self.env.country}\n"
            f"Resolution: {self.env.current_trajectory.get('trajectory_id', 'unknown') if self.env.current_trajectory else 'none'}\n\n"
            f"{instructions}",
            border_style="cyan"
        ))

        # Reset environment
        state_vec = self.env.reset()
        done = False
        total_reward = 0.0

        # Load expert trajectory if in expert mode
        if self.expert_mode:
            from .data_adapter import trajectory_to_episode
            try:
                self.expert_trajectory = trajectory_to_episode(
                    self.env.current_trajectory,
                    self.env.country
                )
            except (ValueError, KeyError) as e:
                self.console.print(f"[red]Error loading expert trajectory: {e}[/red]")
                self.expert_mode = False

        while not done:
            self.console.clear()
            self.console.print()

            # Show current state
            self.console.print(self.render_state(self.env.state))
            self.console.print()

            # Show available actions
            self.console.print(self.render_actions(self.env.state))
            self.console.print()

            # Show history
            history_panel = self.render_history()
            if history_panel:
                self.console.print(history_panel)
                self.console.print()

            # Get user input
            try:
                if self.expert_mode:
                    # In expert mode, show what action will be taken
                    step_idx = len(self.history)
                    if step_idx < len(self.expert_trajectory):
                        _, expert_action, _, _, _ = self.expert_trajectory[step_idx]
                        action_choice = int(expert_action)

                        self.console.print(
                            f"\n[bold yellow]Expert action: {Action(action_choice).name}[/bold yellow]"
                        )
                        self.console.print("\n[dim]Press Enter to continue...[/dim]")
                        input()
                    else:
                        action_choice = 4  # NO_ACTION fallback
                else:
                    action_choice = IntPrompt.ask(
                        "[bold green]Choose action (0-4)[/bold green]",
                        default=4
                    )

                    if action_choice < 0 or action_choice > 4:
                        self.console.print("[red]Invalid action number. Press Enter to continue.[/red]")
                        input()
                        continue

                action = Action(action_choice)

                # Take step
                state_vec, reward, done, info = self.env.step(action)
                total_reward += reward
                self.history.append((action_choice, reward))

                # Show transition
                if reward != 0:
                    self.console.print(
                        f"\n[bold yellow]Received reward: {reward:+.1f}[/bold yellow]"
                    )

                if not done:
                    self.console.print("\n[dim]Press Enter to continue...[/dim]")
                    input()

            except KeyboardInterrupt:
                self.console.print("\n\n[yellow]Session interrupted.[/yellow]")
                break
            except EOFError:
                break

        # Show final results
        self.console.clear()
        self.console.print()
        self.console.print(Panel.fit(
            f"[bold green]Episode Complete![/bold green]\n\n"
            f"Total Reward: {total_reward:+.1f}\n"
            f"Steps: {len(self.history)}\n",
            border_style="green"
        ))

        self.console.print(self.render_state(self.env.state))
        self.console.print()

        # Ask if they want to see what the expert did
        show_expert = Prompt.ask(
            "\nShow what the expert (real country) did?",
            choices=["y", "n"],
            default="y"
        )

        if show_expert == "y":
            self.show_expert_trajectory()

    def show_expert_trajectory(self):
        """Show what the country actually did in the real trajectory."""
        self.console.print("\n[bold cyan]Expert Trajectory (Historical Data)[/bold cyan]\n")

        transitions = self.env.get_transition_data()

        expert_table = Table(show_header=True, box=box.ROUNDED)
        expert_table.add_column("Step", style="cyan", width=5)
        expert_table.add_column("Stage", style="yellow")
        expert_table.add_column("Action", style="green")
        expert_table.add_column("Reward", style="magenta")

        from .spaces import State
        for i, (s, a, s_next, r, done) in enumerate(transitions):
            state = State.from_vec(s)
            expert_table.add_row(
                str(i),
                state.stage.name,
                Action(a).name,
                f"{r:+.1f}" if r != 0 else "-"
            )

        self.console.print(expert_table)


def launch_interactive(env: UNDeliberationEnv, expert_mode: bool = False):
    """Launch interactive session.

    Args:
        env: The gym environment
        expert_mode: If True, automatically use expert actions instead of prompting
    """
    interactive = InteractiveGym(env, expert_mode=expert_mode)
    interactive.run()
