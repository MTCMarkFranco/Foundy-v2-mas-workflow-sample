# Copilot Instructions

## Project Overview

This repository demonstrates a **Risk Assessment Multi-Agent Workflow** built on Azure AI Foundry v2 with **Microsoft Agent Framework (MAF) v1.0.1**. The `prompt-contracts/` folder defines the architecture and agent instructions; `risk-assessment-workflow/` contains the working implementation.

The workflow is a sequential two-agent pipeline:

1. **CategorizeRiskAgent** — accepts a Client ID, queries Azure AI Search (semantic ranker), evaluates compliance/discrepancy rules, and outputs a risk score (Low/Medium/High) with structured JSON.
2. **SummarizeAgent** — receives the structured risk assessment and produces a human-readable executive summary with evidence-based reasoning and actionable recommendations.

A local async orchestrator chains these agents via dependency-injected `FoundryAgent` instances.

## Technology Stack

- **Agent Framework**: Microsoft Agent Framework v1.0.1 (`agent-framework-foundry>=1.0.1`)
- **Agent Type**: Foundry v2 **prompt agents** (kind="prompt")
- **SDK**: `azure-ai-projects>=2.0.1`
- **Auth**: `azure.identity.DefaultAzureCredential` (works for both local dev and managed identity)
- **Knowledge Source**: Azure AI Search index `client-risk-data` (semantic query type)
- **Runtime**: Python >=3.10, fully async (`asyncio`)
- **Foundry Endpoint**: `https://foundry-cc-canada.services.ai.azure.com/api/projects/dev`

## Key Architecture Patterns

### Agent Invocation via MAF FoundryAgent

Agents are connected using `FoundryAgent` from `agent_framework.foundry`:

```python
from agent_framework.foundry import FoundryAgent
from azure.identity import DefaultAzureCredential

agent = FoundryAgent(
    project_endpoint="https://foundry-cc-canada.services.ai.azure.com/api/projects/dev",
    agent_name="CategorizeRiskAgent",
    agent_version="2",
    credential=DefaultAzureCredential(),
)
result = await agent.run("Evaluate client CLT-10001")
text = result.text  # AgentResponse.text returns the string
```

> **Important**: `FoundryAgent.run()` returns an `AgentResponse` object, not a plain `str`. Access `.text` for the response string.

### Sequential Workflow with SequentialBuilder

The orchestrator uses MAF's `SequentialBuilder` to chain agents:

```python
from agent_framework.orchestrations import SequentialBuilder

workflow = SequentialBuilder(
    participants=[categorize_agent, summarize_agent],
    chain_only_agent_responses=True,
).build()

result = await workflow.run(prompt)
outputs = result.get_outputs()  # list of Message lists
```

- `chain_only_agent_responses=True` ensures only agent responses are passed between stages (not the original user prompt)
- A fresh workflow is built per execution to prevent conversation state leakage
- Assistant messages are extracted by role from `get_outputs()` and parsed as JSON

### Authentication

- Use `DefaultAzureCredential` — it works for both local dev (falls back to `AzureCliCredential`) and Azure deployment (uses managed identity).
- Load `.env` with `load_dotenv(override=False)` so Foundry runtime variables take precedence.

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
│   ├── main.py              # CLI entry point — creates FoundryAgent instances, asyncio.run()
│   ├── config.py             # Dataclass config from env vars
│   ├── errors.py             # Exception hierarchy + retry_with_backoff
│   ├── agents/
│   │   └── base_agent.py     # strip_code_fence() helper for JSON parsing
│   ├── workflow/
│   │   ├── orchestrator.py   # RiskAssessmentWorkflow (MAF SequentialBuilder)
│   │   └── context.py        # build_workflow_result helper
│   └── models/
│       ├── input.py          # WorkflowInput with CLT-XXXXX validation
│       └── output.py         # RiskAssessment, SummaryOutput, WorkflowResult
├── tests/                    # pytest + pytest-asyncio, mocks SequentialBuilder
├── scripts/
│   ├── create_agents.py      # One-time: create prompt agents in Foundry
│   └── create_search_index.py # One-time: create AI Search index + upload sample data
├── requirements.txt
├── pyproject.toml            # pytest asyncio_mode = "auto"
└── .env.example
```
