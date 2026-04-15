"""CLI entry point for the Risk Assessment Workflow using Microsoft Agent Framework."""

import argparse
import asyncio
import logging
import sys

from rich.console import Console
from rich.panel import Panel

from src.config import Config
from src.errors import WorkflowError
from src.progress import WorkflowProgress


console = Console()


def _create_foundry_agents(config: Config, progress: WorkflowProgress):
    """Create FoundryAgent instances for both workflow agents."""
    from agent_framework.foundry import FoundryAgent
    from azure.identity import DefaultAzureCredential

    progress.advance("Authenticating with Azure")
    credential = DefaultAzureCredential()

    progress.advance("Creating CategorizeRiskAgent")
    categorize_agent = FoundryAgent(
        project_endpoint=config.foundry_endpoint,
        agent_name=config.categorize_agent_name,
        agent_version=config.categorize_agent_version,
        credential=credential,
    )

    progress.advance("Creating SummarizeAgent")
    summarize_agent = FoundryAgent(
        project_endpoint=config.foundry_endpoint,
        agent_name=config.summarize_agent_name,
        agent_version=config.summarize_agent_version,
        credential=credential,
    )

    return categorize_agent, summarize_agent


async def run_workflow(client_id: str, config: Config, output_json: bool = False) -> int:
    """Execute the risk assessment workflow via MAF SequentialBuilder."""
    from src.workflow.orchestrator import RiskAssessmentWorkflow

    with WorkflowProgress(console=console) as progress:
        progress.advance("Loading configuration")

        try:
            categorize_agent, summarize_agent = _create_foundry_agents(config, progress)
        except Exception as e:
            progress.fail("Agent initialization failed")
            console.print(f"\n[bold red]Error:[/] Could not initialize Foundry agents: {e}")
            return 1

        progress.advance("Building workflow pipeline")
        workflow = RiskAssessmentWorkflow(categorize_agent, summarize_agent, config)

        try:
            progress.advance("Running risk assessment")
            result = await workflow.execute(client_id)
        except WorkflowError as e:
            progress.fail("Workflow failed")
            console.print(f"\n[bold red]Workflow error:[/] {e}")
            return 1

        progress.advance("Parsing results")
        progress.complete()

    console.print()

    if output_json:
        console.print_json(result.model_dump_json(indent=2))
    else:
        risk_color = {
            "Low": "green", "Medium": "yellow", "High": "red"
        }.get(result.risk_score, "white")

        console.print(Panel.fit(
            f"[bold]Client ID:[/]  {result.client_id}\n"
            f"[bold]Risk Score:[/] [{risk_color} bold]{result.risk_score}[/]",
            title="[bold cyan]Risk Assessment Complete[/]",
            border_style="cyan",
        ))
        body = result.summary.summary_markdown or result.summary.summary_plain_text
        if body:
            console.print()
            from rich.markdown import Markdown
            console.print(Markdown(body))

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Risk Assessment Multi-Agent Workflow (Microsoft Agent Framework)"
    )
    parser.add_argument("client_id", help="Client ID to evaluate (e.g. CLT-10001)")
    parser.add_argument(
        "--json", action="store_true", dest="output_json",
        help="Output raw JSON instead of formatted text",
    )
    args = parser.parse_args(argv)

    config = Config()

    # Suppress noisy SDK logging — milestones are shown via progress bar
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("agent_framework").setLevel(logging.WARNING)
    logging.basicConfig(level=logging.WARNING)

    return asyncio.run(run_workflow(args.client_id, config, args.output_json))


if __name__ == "__main__":
    sys.exit(main())
