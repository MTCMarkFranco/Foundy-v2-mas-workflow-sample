"""CLI entry point for the Risk Assessment Workflow."""

import argparse
import json
import logging
import sys

from src.config import Config
from src.errors import WorkflowError


def _create_project_client(endpoint: str):
    """Create an AIProjectClient with DefaultAzureCredential."""
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    return AIProjectClient(
        endpoint=endpoint,
        credential=DefaultAzureCredential(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Risk Assessment Multi-Agent Workflow"
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

    try:
        project_client = _create_project_client(config.foundry_endpoint)
    except Exception as e:
        print(f"Error: Could not connect to Azure AI Foundry: {e}", file=sys.stderr)
        return 1

    from src.workflow.orchestrator import RiskAssessmentWorkflow

    workflow = RiskAssessmentWorkflow(project_client, config)

    try:
        result = workflow.execute(args.client_id)
    except WorkflowError as e:
        print(f"Workflow error: {e}", file=sys.stderr)
        return 1

    if args.output_json:
        print(result.model_dump_json(indent=2))
    else:
        print(f"\n{'=' * 60}")
        print("RISK ASSESSMENT COMPLETE")
        print(f"{'=' * 60}")
        print(f"Client ID:  {result.client_id}")
        print(f"Risk Score: {result.risk_score}")
        print(f"\n{result.summary.summary_markdown or result.summary.summary_plain_text}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
