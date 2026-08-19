"""
CLI interface for download-curator.
Provides commands: scan, review, pending, history, undo, approve, reject, ignore, serve, launchd, config.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from download_curator.config import generate_default_config_yaml, load_config
from download_curator.core.engine import CuratorEngine
from download_curator.core.watcher import DownloadsWatcher
from download_curator.launchd.manager import LaunchAgentManager, generate_plist_content
from download_curator.ui.server import run_server
from download_curator.ui.terminal import run_interactive_review

app = typer.Typer(
    name="download-curator",
    help="Local macOS application for safe, AI-assisted download organization.",
    add_completion=False,
)
console = Console()


@app.command()
def scan(
    watch: bool = typer.Option(False, "--watch", "-w", help="Run continuously watching for new downloads."),
    dry_run: bool = typer.Option(False, "--dry-run", "-d", help="Scan read-only and print proposals without saving to DB."),
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to custom config.yaml"),
) -> None:
    """Scan ~/Downloads for completed files and create proposals (READ-ONLY)."""
    cfg = load_config(config_file)
    engine = CuratorEngine(config=cfg)

    console.print(f"[bold cyan]Scanning directory:[/] [yellow]{cfg.watch_directory}[/]")
    proposals = engine.scan(dry_run=dry_run)

    if not proposals:
        console.print("[green]No new uncurated downloads found.[/green]")
    else:
        console.print(f"[bold green]Found {len(proposals)} proposal(s):[/bold green]")
        table = Table(title="Generated Proposals", show_lines=True)
        table.add_column("Current File", style="yellow")
        table.add_column("Proposed Name", style="green")
        table.add_column("Category", style="blue")
        table.add_column("Destination", style="magenta")
        table.add_column("Conf.", justify="right")

        for p in proposals:
            table.add_row(
                Path(p.current_path).name,
                p.proposed_filename,
                p.category,
                f"{p.proposed_destination}/",
                f"{p.confidence:.2f}",
            )
        console.print(table)

        if dry_run:
            console.print("\n[italic dim][Dry run mode] Proposals were not saved to pending database.[/italic dim]")
        else:
            console.print(f"\n[cyan]Proposals saved to pending queue. Run [bold]download-curator review[/bold] to approve.[/cyan]")

    if watch:
        console.print("\n[bold green]Watcher active. Monitoring for completed downloads... (Ctrl+C to stop)[/bold green]")
        watcher = DownloadsWatcher(
            cfg,
            on_file_completed=lambda path: engine.process_file(path, notify=True),
        )
        watcher.start()
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            watcher.stop()
            console.print("\n[dim]Watcher stopped.[/dim]")


@app.command()
def review(
    all_auto: bool = typer.Option(False, "--all", "-a", help="Automatically approve all pending proposals."),
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to custom config.yaml"),
) -> None:
    """Launch interactive terminal review for pending proposals."""
    cfg = load_config(config_file)
    engine = CuratorEngine(config=cfg)
    run_interactive_review(engine, approve_all_default=all_auto)


@app.command()
def pending(
    as_json: bool = typer.Option(False, "--json", "-j", help="Output pending proposals as JSON."),
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to custom config.yaml"),
) -> None:
    """List all pending proposals awaiting approval."""
    cfg = load_config(config_file)
    engine = CuratorEngine(config=cfg)
    proposals = engine.get_pending_proposals()

    if as_json:
        print(json.dumps([p.model_dump() for p in proposals], default=str, indent=2))
        return

    if not proposals:
        console.print("[green]No pending proposals.[/green]")
        return

    table = Table(title=f"Pending Proposals ({len(proposals)})", show_lines=True)
    table.add_column("ID", style="dim", justify="right")
    table.add_column("Current File", style="yellow")
    table.add_column("Proposed Name", style="green")
    table.add_column("Category", style="blue")
    table.add_column("Destination", style="magenta")
    table.add_column("Conf.", justify="right")
    table.add_column("Reason", style="italic")

    for p in proposals:
        table.add_row(
            str(p.id),
            Path(p.current_path).name,
            p.proposed_filename,
            p.category,
            f"{p.proposed_destination}/",
            f"{p.confidence:.2f}",
            p.reason,
        )
    console.print(table)
    console.print("\n[cyan]Run [bold]download-curator review[/bold] to interactively review and approve.[/cyan]")


@app.command()
def history(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of records to show."),
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to custom config.yaml"),
) -> None:
    """Show immutable audit history of curated files."""
    cfg = load_config(config_file)
    engine = CuratorEngine(config=cfg)
    records = engine.get_history(limit=limit)

    if not records:
        console.print("[dim]No audit history found.[/dim]")
        return

    table = Table(title=f"Audit History (Last {len(records)})", show_lines=True)
    table.add_column("ID", justify="right", style="dim")
    table.add_column("Timestamp", style="cyan")
    table.add_column("Action", style="bold")
    table.add_column("Source", style="yellow")
    table.add_column("Destination", style="green")

    for r in records:
        action_color = (
            "green" if r.action.value == "executed"
            else "red" if r.action.value == "undone"
            else "yellow" if r.action.value == "proposed"
            else "magenta"
        )
        table.add_row(
            str(r.id),
            r.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            f"[{action_color}]{r.action.value}[/]",
            Path(r.source_path).name if r.source_path else "-",
            Path(r.destination_path).name if r.destination_path else "-",
        )
    console.print(table)


@app.command()
def undo(
    proposal_id: Optional[int] = typer.Argument(None, help="Optional proposal ID to undo. Defaults to last executed move."),
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to custom config.yaml"),
) -> None:
    """Safely undo the last executed file move/rename."""
    cfg = load_config(config_file)
    engine = CuratorEngine(config=cfg)

    try:
        restored_path = engine.undo(proposal_id=proposal_id)
        console.print(f"[bold green]✓ Successfully undone! Restored to:[/] [cyan]{restored_path}[/]")
    except Exception as e:
        console.print(f"[bold red]✗ Undo failed:[/] {e}")
        raise typer.Exit(code=1)


@app.command()
def approve(
    proposal_id: int = typer.Argument(..., help="Proposal ID to approve."),
    filename: Optional[str] = typer.Option(None, "--filename", "-f", help="Override proposed filename."),
    destination: Optional[str] = typer.Option(None, "--destination", "-d", help="Override destination folder."),
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to custom config.yaml"),
) -> None:
    """Explicitly approve and execute a proposal by ID."""
    cfg = load_config(config_file)
    engine = CuratorEngine(config=cfg)

    try:
        dest_path = engine.approve_proposal(
            proposal_id=proposal_id,
            custom_filename=filename,
            custom_destination=destination,
        )
        console.print(f"[bold green]✓ Approved & Moved to:[/] [cyan]{dest_path}[/]")
    except Exception as e:
        console.print(f"[bold red]✗ Approval failed:[/] {e}")
        raise typer.Exit(code=1)


@app.command()
def reject(
    proposal_id: int = typer.Argument(..., help="Proposal ID to reject."),
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to custom config.yaml"),
) -> None:
    """Reject a proposal without touching the original file."""
    cfg = load_config(config_file)
    engine = CuratorEngine(config=cfg)
    if engine.reject_proposal(proposal_id):
        console.print(f"[yellow]Proposal {proposal_id} rejected. File remains untouched.[/yellow]")
    else:
        console.print(f"[red]Proposal {proposal_id} not found.[/red]")


@app.command()
def ignore(
    proposal_id: int = typer.Argument(..., help="Proposal ID to permanently ignore."),
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to custom config.yaml"),
) -> None:
    """Permanently ignore a file so it is not proposed again."""
    cfg = load_config(config_file)
    engine = CuratorEngine(config=cfg)
    if engine.ignore_file(proposal_id):
        console.print(f"[magenta]Proposal {proposal_id} marked as ignored.[/magenta]")
    else:
        console.print(f"[red]Proposal {proposal_id} not found.[/red]")


@app.command()
def enhance(
    proposal_id: int = typer.Argument(..., help="Proposal ID to enhance with AI."),
    as_json: bool = typer.Option(False, "--json", "-j", help="Output raw JSON for UI consumption."),
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to custom config.yaml"),
) -> None:
    """Run AI model to generate/enhance proposal suggestion for comparison."""
    cfg = load_config(config_file)
    engine = CuratorEngine(config=cfg)

    try:
        updated = engine.enhance_with_ai(proposal_id)
        if as_json:
            print(updated.model_dump_json())
        else:
            console.print(f"[bold purple]✨ AI Suggestion:[/] [cyan]{updated.ai_filename}[/] -> [yellow]{updated.ai_destination}/[/]")
            if updated.ai_reason:
                console.print(f"[dim]Reason: {updated.ai_reason}[/dim]")
    except Exception as e:
        if as_json:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"[bold red]✗ AI enhancement failed:[/] {e}")
        raise typer.Exit(code=1)


@app.command()
def serve(
    port: Optional[int] = typer.Option(None, "--port", "-p", help="Server port."),
    watch: bool = typer.Option(True, "--watch/--no-watch", help="Also run background filesystem watcher."),
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to custom config.yaml"),
) -> None:
    """Run local API server and background download watcher."""
    cfg = load_config(config_file)
    engine = CuratorEngine(config=cfg)
    srv_port = port or cfg.server.port

    if watch:
        watcher = DownloadsWatcher(
            cfg,
            on_file_completed=lambda path: engine.process_file(path, notify=True),
        )
        watcher.start()

    console.print(f"[bold green]download-curator service running on http://{cfg.server.host}:{srv_port}[/bold green]")
    try:
        run_server(engine, host=cfg.server.host, port=srv_port)
    except KeyboardInterrupt:
        pass


launchd_app = typer.Typer(help="Manage macOS LaunchAgent background service.")
app.add_typer(launchd_app, name="launchd")


@launchd_app.command("status")
def launchd_status() -> None:
    """Show LaunchAgent status."""
    status = LaunchAgentManager.get_status()
    table = Table(title="LaunchAgent Daemon Status")
    table.add_column("Property", style="bold cyan")
    table.add_column("Value")
    for k, v in status.items():
        table.add_row(k, v)
    console.print(table)


@launchd_app.command("plist")
def launchd_plist() -> None:
    """Print the launchd plist configuration XML."""
    print(generate_plist_content())


@launchd_app.command("install")
def launchd_install() -> None:
    """Install and enable the LaunchAgent plist."""
    path = LaunchAgentManager.install()
    console.print(f"[bold green]✓ Installed and loaded LaunchAgent:[/] [cyan]{path}[/]")


@launchd_app.command("uninstall")
def launchd_uninstall() -> None:
    """Unload and remove the LaunchAgent plist."""
    LaunchAgentManager.uninstall()
    console.print("[bold yellow]✓ Unloaded and removed LaunchAgent.[/bold yellow]")


@launchd_app.command("start")
def launchd_start() -> None:
    """Start the LaunchAgent service."""
    LaunchAgentManager.start()
    console.print("[green]Sent start signal to LaunchAgent.[/green]")


@launchd_app.command("stop")
def launchd_stop() -> None:
    """Stop the LaunchAgent service."""
    LaunchAgentManager.stop()
    console.print("[yellow]Sent stop signal to LaunchAgent.[/yellow]")


@launchd_app.command("restart")
def launchd_restart() -> None:
    """Restart the LaunchAgent service to apply configuration changes."""
    LaunchAgentManager.restart()
    console.print("[bold green]✓ Restarted LaunchAgent daemon.[/bold green]")


config_app = typer.Typer(help="Manage configuration.")
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show(
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
) -> None:
    """Show current active configuration."""
    cfg = load_config(config_file)
    console.print_json(cfg.model_dump_json())


@config_app.command("init")
def config_init(
    path: Path = typer.Option(Path("~/.download-curator/config.yaml"), "--output", "-o", help="Target config path"),
) -> None:
    """Generate default config.yaml file."""
    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        console.print(f"[yellow]Config already exists at {target}[/yellow]")
        return
    with open(target, "w", encoding="utf-8") as f:
        f.write(generate_default_config_yaml())
    console.print(f"[bold green]✓ Created default config file at:[/] [cyan]{target}[/]")


if __name__ == "__main__":
    app()
