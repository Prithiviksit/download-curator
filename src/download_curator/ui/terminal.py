"""
Interactive Terminal Review Interface using Rich.
Presents proposals clearly and enforces explicit approval actions.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from download_curator.core.engine import CuratorEngine
from download_curator.core.models import Proposal


console = Console()


def format_proposal_panel(proposal: Proposal, index: int, total: int) -> Panel:
    """Format a proposal into a clear, beautiful Rich panel."""
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column(style="white")

    # Shorten current path for display
    cur_path = Path(proposal.current_path)
    try:
        display_path = f"~/{cur_path.relative_to(Path.home())}"
    except ValueError:
        display_path = str(cur_path)

    confidence_color = (
        "green" if proposal.confidence >= 0.85
        else "yellow" if proposal.confidence >= 0.65
        else "red"
    )

    table.add_row("Current:", f"[bold yellow]{display_path}[/]")
    table.add_row("Proposed Filename:", f"[bold green]{proposal.proposed_filename}[/]")
    table.add_row("Proposed Destination:", f"[bold magenta]{proposal.proposed_destination}/[/]")
    table.add_row("Category:", f"[bold blue]{proposal.category}[/]")
    table.add_row("Confidence:", f"[{confidence_color}]{proposal.confidence:.2f}[/]")
    table.add_row("Reason:", f"[italic]{proposal.reason}[/]")

    title = f" [bold white]Proposal {index} of {total}[/] "
    return Panel(
        table,
        title=title,
        border_style="cyan",
        padding=(1, 2),
    )


def run_interactive_review(engine: CuratorEngine, approve_all_default: bool = False) -> None:
    """Run interactive terminal review loop for all pending proposals."""
    pending = engine.get_pending_proposals()

    if not pending:
        console.print("\n[bold green]✓ No pending proposals to review.[/bold green]\n")
        return

    console.print(f"\n[bold]Found [cyan]{len(pending)}[/cyan] pending download proposals for review:[/bold]\n")

    auto_approve_remaining = approve_all_default
    idx = 0

    while idx < len(pending):
        proposal = pending[idx]

        # Re-check that source file still exists
        if not proposal.file_exists:
            console.print(f"[dim]File no longer exists: {proposal.current_path} (skipping)[/dim]")
            idx += 1
            continue

        console.print(format_proposal_panel(proposal, idx + 1, len(pending)))

        if auto_approve_remaining:
            try:
                dest = engine.approve_proposal(proposal.id)  # type: ignore
                console.print(f"[bold green]✓ Approved & Moved to:[/] {dest}\n")
            except Exception as e:
                console.print(f"[bold red]✗ Failed to move file:[/] {e}\n")
            idx += 1
            continue

        console.print("[bold]Available Actions:[/bold]")
        console.print(
            "  [bold green][a][/] Approve       "
            "  [bold cyan][A][/] Approve All   "
            "  [bold yellow][e][/] Edit"
        )
        console.print(
            "  [bold red][r][/] Reject        "
            "  [bold white][s][/] Skip          "
            "  [bold magenta][i][/] Ignore File"
        )
        console.print(
            "  [bold blue][p][/] Preview/Open  "
            "  [bold dim][q][/] Quit"
        )

        choice = Prompt.ask(
            "\n[bold cyan]Action[/bold cyan]",
            choices=["a", "A", "e", "r", "s", "i", "p", "o", "q"],
            default="a",
            show_choices=False,
        ).strip().lower()

        if choice == "a":
            try:
                dest = engine.approve_proposal(proposal.id)  # type: ignore
                console.print(f"\n[bold green]✓ Approved & Moved to:[/] [cyan]{dest}[/]\n")
            except Exception as e:
                console.print(f"\n[bold red]✗ Failed to move file:[/] {e}\n")
            idx += 1

        elif choice == "A" or choice == "a" and False:  # capital A
            auto_approve_remaining = True
            try:
                dest = engine.approve_proposal(proposal.id)  # type: ignore
                console.print(f"\n[bold green]✓ Approved & Moved to:[/] [cyan]{dest}[/]\n")
            except Exception as e:
                console.print(f"\n[bold red]✗ Failed to move file:[/] {e}\n")
            idx += 1

        elif choice == "e":
            console.print("\n[bold]Edit Proposal:[/bold]")
            new_name = Prompt.ask(
                "Proposed filename",
                default=proposal.proposed_filename,
            ).strip()
            new_dest = Prompt.ask(
                "Proposed destination folder",
                default=proposal.proposed_destination,
            ).strip()

            updated = engine.edit_proposal(
                proposal.id,  # type: ignore
                proposed_filename=new_name,
                proposed_destination=new_dest,
            )
            if updated:
                proposal = updated
                pending[idx] = updated
                approve_now = Prompt.ask(
                    "Approve this edited proposal now?",
                    choices=["y", "n"],
                    default="y",
                )
                if approve_now.lower() == "y":
                    try:
                        dest = engine.approve_proposal(proposal.id)  # type: ignore
                        console.print(f"\n[bold green]✓ Approved & Moved to:[/] [cyan]{dest}[/]\n")
                    except Exception as e:
                        console.print(f"\n[bold red]✗ Failed to move file:[/] {e}\n")
                    idx += 1
            console.print()

        elif choice == "r":
            engine.reject_proposal(proposal.id)  # type: ignore
            console.print(f"\n[yellow]✗ Rejected proposal for {Path(proposal.current_path).name} (file unchanged)[/]\n")
            idx += 1

        elif choice == "s":
            console.print("\n[dim]Skipped for now (file unchanged).[/dim]\n")
            idx += 1

        elif choice == "i":
            engine.ignore_file(proposal.id)  # type: ignore
            console.print(f"\n[magenta]⊘ File marked as permanently ignored: {Path(proposal.current_path).name}[/]\n")
            idx += 1

        elif choice in ("p", "o"):
            file_path = Path(proposal.current_path).expanduser().resolve()
            if file_path.exists():
                console.print(f"\n[blue]Opening {file_path.name}...[/blue]\n")
                try:
                    subprocess.run(["open", str(file_path)], check=False)
                except Exception as e:
                    console.print(f"[red]Error opening file: {e}[/red]\n")
            else:
                console.print("[red]File not found on disk.[/red]\n")

        elif choice == "q":
            console.print("\n[dim]Exited review. Remaining files untouched.[/dim]\n")
            break

    console.print("[bold green]Done.[/bold green]\n")
