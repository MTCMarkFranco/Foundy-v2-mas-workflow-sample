"""Spectre Console-style progress display using Rich."""

from __future__ import annotations

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text


class SquareBarColumn(BarColumn):
    """Progress bar rendered with filled/empty square blocks (■ / □)."""

    def __init__(self, bar_width: int = 20):
        super().__init__(bar_width=bar_width)

    def render(self, task) -> Text:
        completed = int(task.completed)
        total = int(task.total) if task.total else 0
        if total == 0:
            return Text("□" * self.bar_width, style="bar.back")

        filled = int(self.bar_width * completed / total)
        empty = self.bar_width - filled
        bar = Text()
        bar.append("■" * filled, style="bold cyan")
        bar.append("□" * empty, style="dim white")
        return bar


# Ordered workflow milestones
MILESTONES: list[str] = [
    "Loading configuration",
    "Authenticating with Azure",
    "Creating CategorizeRiskAgent",
    "Creating SummarizeAgent",
    "Building workflow pipeline",
    "Running risk assessment",
    "Parsing results",
    "Complete",
]


class WorkflowProgress:
    """Manages a Spectre-style square-block progress bar for key milestones."""

    def __init__(self, console: Console | None = None):
        self._console = console or Console()
        self._progress = Progress(
            TextColumn("[bold blue]{task.description}"),
            SquareBarColumn(bar_width=20),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=self._console,
            transient=False,
        )
        self._task_id = None
        self._current_step = 0

    def __enter__(self) -> WorkflowProgress:
        self._progress.__enter__()
        self._console.print()
        self._console.rule("[bold cyan]Risk Assessment Workflow", style="cyan")
        self._console.print()
        self._task_id = self._progress.add_task(
            MILESTONES[0], total=len(MILESTONES)
        )
        return self

    def __exit__(self, *args):
        self._progress.__exit__(*args)

    def advance(self, milestone: str) -> None:
        """Advance to the next milestone step."""
        self._current_step += 1
        self._progress.update(
            self._task_id,
            completed=self._current_step,
            description=milestone,
        )

    def complete(self) -> None:
        """Mark the progress as fully complete."""
        self._progress.update(
            self._task_id,
            completed=len(MILESTONES),
            description="[bold green]✓ Complete",
        )

    def fail(self, message: str) -> None:
        """Mark the progress as failed."""
        self._progress.update(
            self._task_id,
            description=f"[bold red]✗ {message}",
        )
        self._progress.stop()
