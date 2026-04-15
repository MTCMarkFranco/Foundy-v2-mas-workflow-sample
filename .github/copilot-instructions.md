# Copilot Instructions

## Project Overview

This is a **prompt-contracts-only** repository — it contains no source code yet. The `prompt-contracts/` folder defines the architecture, agent instructions, and orchestration blueprint for a Risk Assessment Multi-Agent Workflow to be built on Azure AI Foundry v2 with Microsoft Agent Framework (MAF).

The workflow is a sequential two-agent pipeline:

1. **CategorizeRiskAgent** — accepts a Client ID, queries Azure AI Search (hybrid + semantic ranker), evaluates compliance/discrepancy rules, and outputs a risk score (Low/Medium/High) with structured JSON.
2. **SummarizeAgent** — receives the structured risk assessment and produces a human-readable executive summary with evidence-based reasoning and actionable recommendations.

A local MAF orchestrator chains these agents via `WorkflowBuilder.add_edge()`.

## Technology Stack

- **Orchestrator**: Microsoft Agent Framework (`agent-framework-core` / `agent-framework-azure-ai`, 1.0.0rc3)
- **Hosted Agents**: Azure AI Foundry v2
- **SDK**: `azure-ai-projects>=2.0.0`, `azure-ai-agentserver-agentframework 1.0.0b16`
- **Auth**: `azure.identity.aio` (async `DefaultAzureCredential` for local, `ManagedIdentityCredential` in Azure)
- **Knowledge Source**: Azure AI Search index `client-risk-data` (hybrid + semantic ranker)
- **Runtime**: Python >=3.10
- **Foundry Endpoint**: `https://foundry-cc-canada.services.ai.azure.com/api/projects/dev`

## Key Architecture Patterns

### Agent Invocation

Foundry v2 hosted agents are invoked via `responses.create()` with an `agent_reference` extra_body:

```python
response = openai_client.responses.create(
    input=[{"role": "user", "content": message}],
    extra_body={
        "agent_reference": {
            "name": "CategorizeRiskAgent",
            "version": "1",
            "type": "agent_reference"
        }
    }
)
```

### MAF Workflow Construction

Each agent **must** have its own client instance. Sequential handoff uses `WorkflowBuilder`:

```python
workflow = (
    WorkflowBuilder(
        name="RiskAssessmentWorkflow",
        start_executor=categorize_agent,
        output_executors=[categorize_agent, summarize_agent]
    )
    .add_edge(categorize_agent, summarize_agent)
    .build()
)
agent = workflow.as_agent()
```

### Authentication

- Use `azure.identity.aio` (async) for MAF — the sync version will not work.
- Use `get_bearer_token_provider` with scope `https://cognitiveservices.azure.com/.default` for long-running servers to avoid token expiry (401 after ~1 hour).
- Detect Azure environment via `MSI_ENDPOINT` env var to switch between `ManagedIdentityCredential` and `DefaultAzureCredential`.
- Load `.env` with `load_dotenv(override=False)` so Foundry runtime variables take precedence.

### HTTP Hosting for Foundry Deployment

```python
from azure.ai.agentserver.agentframework import from_agent_framework
# Accepts a built agent OR a .build method reference for lazy init
from_agent_framework(agent).run_async()
```

## Risk Scoring Rules

The CategorizeRiskAgent uses a weighted scoring matrix:

| Severity | Weight | Examples |
|----------|--------|----------|
| Critical | 3 | Missing compliance docs, expired certifications, watchlist match |
| Major | 2 | Conflicting records, outdated critical data |
| Minor | 1 | Missing optional fields, formatting inconsistencies |

- **Low**: weighted_score == 0
- **Medium**: weighted_score 1–5
- **High**: weighted_score >= 6

When uncertain, the agent should escalate to a higher risk category.

## Agent Output Contracts

CategorizeRiskAgent outputs JSON with: `client_id`, `risk_score`, `weighted_score`, `discrepancy_count`, `search_results[]`, `rule_evaluations[]`, `reasoning`.

SummarizeAgent outputs JSON with: `client_id`, `risk_score`, `summary_markdown`, `summary_plain_text`, `key_findings[]`, `recommendations[]`, `urgency_level` (routine/elevated/immediate), `generated_timestamp`.

## Test Data

Five test clients are defined in `prompt-contracts/sample-data/client-risk-data.json`:

| Client ID | Expected Risk |
|-----------|---------------|
| CLT-10001 | Low |
| CLT-20002 | Medium |
| CLT-30003 | High |
| CLT-40004 | Low |
| CLT-50005 | High |

## Build & Test

```bash
cd risk-assessment-workflow
pip install -r requirements.txt

# Run all tests
python -m pytest tests/ -v

# Run a single test file or class
python -m pytest tests/test_agents.py::TestComputeRiskScore -v

# Run the workflow CLI (requires Azure connectivity)
python -m src.main CLT-10001
python -m src.main CLT-10001 --json
```

## Project Structure

```
risk-assessment-workflow/
├── src/
│   ├── main.py              # CLI entry point (argparse)
│   ├── config.py             # Dataclass config from env vars
│   ├── errors.py             # Exception hierarchy + retry_with_backoff
│   ├── agents/
│   │   ├── base_agent.py     # HostedAgentInvoker (generic Foundry agent caller)
│   │   ├── categorize_agent.py  # Risk categorization + local score recomputation
│   │   └── summarize_agent.py   # Summary generation with consistency checks
│   ├── workflow/
│   │   ├── orchestrator.py   # RiskAssessmentWorkflow (sequential pipeline)
│   │   └── context.py        # Agent handoff helpers
│   └── models/
│       ├── input.py          # WorkflowInput with CLT-XXXXX validation
│       └── output.py         # RiskAssessment, SummaryOutput, WorkflowResult
├── tests/                    # pytest suite with mocked Azure services
├── requirements.txt
└── .env.example
```
