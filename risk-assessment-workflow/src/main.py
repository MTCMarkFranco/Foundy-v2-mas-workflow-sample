"""CLI entry point for the Risk Assessment Workflow using Microsoft Agent Framework."""

import argparse
import asyncio
import logging
import sys

from src.config import Config
from src.errors import WorkflowError


def _create_foundry_agents(config: Config):
    """Create FoundryAgent instances for both workflow agents."""
    from agent_framework.foundry import FoundryAgent
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()

    categorize_agent = FoundryAgent(
        project_endpoint=config.foundry_endpoint,
        agent_name=config.categorize_agent_name,
        agent_version=config.categorize_agent_version,
        credential=credential,
    )

    summarize_agent = FoundryAgent(
        project_endpoint=config.foundry_endpoint,
        agent_name=config.summarize_agent_name,
        agent_version=config.summarize_agent_version,
        credential=credential,
    )

    return categorize_agent, summarize_agent


async def run_workflow(client_id: str, config: Config, output_json: bool = False) -> int:
    """Execute the risk assessment workflow asynchronously."""
    from src.workflow.orchestrator import RiskAssessmentWorkflow

    try:
        categorize_agent, summarize_agent = _create_foundry_agents(config)
    except Exception as e:
        print(f"Error: Could not initialize Foundry agents: {e}", file=sys.stderr)
        return 1

    workflow = RiskAssessmentWorkflow(categorize_agent, summarize_agent, config)

    try:
        result = await workflow.execute(client_id)
    except WorkflowError as e:
        print(f"Workflow error: {e}", file=sys.stderr)
        return 1

    if output_json:
        print(result.model_dump_json(indent=2))
    else:
        print(f"\n{'=' * 60}")
        print("RISK ASSESSMENT COMPLETE")
        print(f"{'=' * 60}")
        print(f"Client ID:  {result.client_id}")
        print(f"Risk Score: {result.risk_score}")
        print(f"\n{result.summary.summary_markdown or result.summary.summary_plain_text}")

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

    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    return asyncio.run(run_workflow(args.client_id, config, args.output_json))


if __name__ == "__main__":
    sys.exit(main())
