# 🤖 Risk Assessment Multi-Agent Workflow

> **A production-ready multi-agent system built on [Azure AI Foundry v2](https://learn.microsoft.com/azure/ai-studio/) and [Microsoft Agent Framework (MAF)](https://github.com/microsoft/agent-framework) that performs automated client risk assessments using cloud-hosted AI agents and Azure AI Search.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](#-prerequisites)
[![Azure AI Foundry](https://img.shields.io/badge/Azure%20AI-Foundry%20v2-0078D4?logo=microsoftazure&logoColor=white)](#-architecture-overview)
[![MAF v1.0.1](https://img.shields.io/badge/MAF-v1.0.1-purple)](#-technology-stack)
[![GPT-5.2](https://img.shields.io/badge/model-GPT--5.2-00A67E?logo=openai&logoColor=white)](#-technology-stack)

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Architecture Overview](#-architecture-overview)
- [How It Works](#-how-it-works)
- [Technology Stack](#-technology-stack)
- [Key Components](#-key-components)
- [Azure AI Search Integration](#-azure-ai-search-integration)
- [Risk Scoring Engine](#-risk-scoring-engine)
- [Agent Output Contracts](#-agent-output-contracts)
- [Token Economics](#-token-economics)
- [Graceful Degradation & AI Gateway](#-graceful-degradation--ai-gateway)
- [Observability Pipeline](#-observability-pipeline)
- [Prerequisites](#-prerequisites)
- [Getting Started](#-getting-started)
- [Running the Sample](#-running-the-sample)
- [Test Data](#-test-data)
- [Testing](#-testing)
- [Resilience & Actor Pattern Compliance](#️-resilience--actor-pattern-compliance)
- [Project Structure](#-project-structure)
- [License](#-license)

---

## 🌟 Overview

This sample demonstrates a **sequential two-agent pipeline** that evaluates client risk profiles by combining **cloud-hosted Foundry agents** with **local Python orchestration**:

1. **🔍 CategorizeRiskAgent** — Queries Azure AI Search, evaluates compliance & discrepancy rules, and outputs a structured risk score (Low / Medium / High).
2. **📝 SummarizeAgent** — Transforms the technical risk assessment into a human-readable executive summary with actionable recommendations.

The local orchestrator chains these agents using MAF's `SequentialBuilder`, providing a clean separation between **orchestration logic** (local) and **AI reasoning** (cloud).

---

## 🏗️ Architecture Overview

```mermaid
graph TB
    subgraph LOCAL["🖥️ Local Environment"]
        CLI["⌨️ CLI Entry Point<br/><code>python -m src.main CLT-10001</code>"]
        ORCH["🔄 MAF Sequential Orchestrator<br/><code>SequentialBuilder</code>"]
        PARSE["📦 Response Parser<br/>Pydantic Models"]
        RICH["🎨 Rich Console Output"]

        CLI --> ORCH
        ORCH --> PARSE
        PARSE --> RICH
    end

    subgraph FOUNDRY["☁️ Azure AI Foundry Environment"]
        subgraph AGENTS["🤖 Hosted Prompt Agents"]
            CAT["🔍 CategorizeRiskAgent<br/>GPT-5.2 · v1"]
            SUM["📝 SummarizeAgent<br/>GPT-5.2 · v1"]
        end

        subgraph TOOLS["🔧 Agent Tools (Cloud)"]
            SEARCH["🔎 Azure AI Search<br/><code>client-risk-data</code> index<br/>Semantic Hybrid Search"]
        end

        CAT -->|"tool_call: azure_ai_search<br/>filter: client_id eq 'CLT-XXXXX'"| SEARCH
        SEARCH -->|"Filtered documents<br/>+ relevance scores"| CAT
    end

    subgraph DATA["💾 Azure AI Search Index"]
        IDX["📊 client-risk-data<br/>Semantic Ranker · Scoring Profile<br/>10 documents · 5 clients"]
    end

    ORCH -->|"① FoundryAgent.run(prompt)"| CAT
    CAT -->|"RiskAssessment JSON"| ORCH
    ORCH -->|"② chain_only_agent_responses"| SUM
    SUM -->|"SummaryOutput JSON"| ORCH
    SEARCH <-->|"Hybrid Vector + Keyword"| IDX

    style LOCAL fill:#1a1a2e,stroke:#16213e,color:#e0e0e0
    style FOUNDRY fill:#0d2137,stroke:#0078D4,color:#e0e0e0
    style AGENTS fill:#1b3a5c,stroke:#4db8ff,color:#e0e0e0
    style TOOLS fill:#1b3a5c,stroke:#4db8ff,color:#e0e0e0
    style DATA fill:#1a2e1a,stroke:#4caf50,color:#e0e0e0
```

### 🔑 Key Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| **Local orchestration, cloud agents** | Keep orchestration logic testable and versionable locally; AI reasoning runs in Foundry's managed environment |
| **`chain_only_agent_responses=True`** | Only agent responses flow between stages — no conversation history bloat |
| **Fresh workflow per invocation** | Prevents conversation state leakage between separate risk assessments |
| **Search tool attached to agent in Foundry** | The AI Search tool runs server-side in Foundry, not locally — the agent autonomously invokes it |

---

## ⚙️ How It Works

### 🔄 End-to-End Workflow

```mermaid
sequenceDiagram
    actor User
    participant CLI as 🖥️ Local CLI
    participant Orch as 🔄 MAF Orchestrator
    participant Cat as 🔍 CategorizeRiskAgent<br/>(Foundry Cloud)
    participant Search as 🔎 Azure AI Search
    participant Sum as 📝 SummarizeAgent<br/>(Foundry Cloud)

    User->>CLI: python -m src.main CLT-10001
    CLI->>CLI: Validate client_id (CLT-XXXXX)
    CLI->>Orch: execute(client_id)

    Note over Orch: Build fresh SequentialBuilder<br/>per invocation

    Orch->>Cat: ① "Evaluate risk for CLT-10001..."
    Cat->>Search: tool_call: azure_ai_search<br/>filter: client_id eq 'CLT-10001'<br/>query_type: vector_semantic_hybrid
    Search-->>Cat: Matching documents + scores
    Cat->>Cat: Apply D1-D5 & C1-C5 rules<br/>Calculate weighted_score
    Cat-->>Orch: RiskAssessment JSON

    Orch->>Sum: ② Pass assessment (chain_only_agent_responses)
    Sum->>Sum: Transform to narrative<br/>Set urgency & recommendations
    Sum-->>Orch: SummaryOutput JSON

    Orch->>CLI: WorkflowResult
    CLI->>User: 🟢 LOW RISK / 🟡 MEDIUM / 🔴 HIGH
```

### 🔎 How Azure AI Search Is Invoked

The search tool is **attached to the CategorizeRiskAgent at agent creation time** in Azure AI Foundry — it is **not** a local tool. Here's how it works:

1. **🏗️ Agent Creation** — The `create_agents.py` script registers an `azure_ai_search` tool on the CategorizeRiskAgent with the `client-risk-data` index configured for `vector_semantic_hybrid` queries.

2. **📨 Prompt Injection** — The local orchestrator sends a prompt containing the client ID:
   ```
   "Evaluate the risk profile for Client ID: CLT-10001.
    Query the knowledge base filtered by this Client ID..."
   ```

3. **🤖 Autonomous Tool Call** — The hosted GPT-5.2 model decides when to invoke the search tool. Foundry executes the tool call server-side with:
   ```
   filter: client_id eq 'CLT-10001'
   query_type: vector_semantic_hybrid
   ```

4. **📊 Filtered Results** — Azure AI Search returns only documents matching that exact `client_id`, preventing cross-client data leakage. Results include relevance scores from the semantic ranker and the `risk-boost` scoring profile.

5. **🧠 Rule Evaluation** — The agent analyzes the filtered documents against 10 rules (D1–D5 discrepancy + C1–C5 compliance) and calculates the weighted risk score.

> **💡 Important:** The local Python code never directly calls Azure AI Search. The search tool lives in the Foundry cloud and is invoked autonomously by the agent's LLM reasoning.

---

## 🛠️ Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| 🧠 **AI Model** | GPT-5.2 | Deployed in Foundry |
| 🤖 **Agent Framework** | Microsoft Agent Framework (MAF) | `agent-framework-foundry>=1.0.1` |
| ☁️ **Agent Hosting** | Azure AI Foundry v2 Prompt Agents | `kind="prompt"` |
| 🔗 **Azure SDK** | Azure AI Projects SDK | `azure-ai-projects>=2.0.0` |
| 🔐 **Authentication** | Azure Identity | `DefaultAzureCredential` |
| 🔎 **Knowledge Store** | Azure AI Search | Semantic Hybrid + Ranker |
| 📐 **Data Models** | Pydantic v2 | Schema validation |
| 🎨 **CLI Display** | Rich Console | Progress bars + panels |
| 🐍 **Runtime** | Python 3.10+ | Fully async (`asyncio`) |

---

## 🧩 Key Components

### 1️⃣ Local Orchestrator — MAF Sequential Workflow

The heart of the system is a **local Python orchestrator** using MAF's `SequentialBuilder`:

```python
from agent_framework.foundry import FoundryAgent
from agent_framework.orchestrations import SequentialBuilder

# Connect to pre-deployed Foundry hosted agents
categorize_agent = FoundryAgent(
    project_endpoint="https://foundry-cc-canada.services.ai.azure.com/api/projects/dev",
    agent_name="CategorizeRiskAgent",
    agent_version="1",
    credential=DefaultAzureCredential(),
)

summarize_agent = FoundryAgent(
    project_endpoint="https://foundry-cc-canada.services.ai.azure.com/api/projects/dev",
    agent_name="SummarizeAgent",
    agent_version="1",
    credential=DefaultAzureCredential(),
)

# Chain agents in a sequential pipeline
workflow = SequentialBuilder(
    participants=[categorize_agent, summarize_agent],
    chain_only_agent_responses=True,
).build()

result = await workflow.run("Evaluate risk for CLT-10001...")
```

### 2️⃣ Cloud Foundry Hosted Agents

Both agents are **prompt agents** (`kind="prompt"`) deployed in Azure AI Foundry:

| Agent | Model | Tools | Purpose |
|-------|-------|-------|---------|
| 🔍 **CategorizeRiskAgent** | GPT-5.2 | `azure_ai_search` | Risk analysis + scoring |
| 📝 **SummarizeAgent** | GPT-5.2 | None | Narrative transformation |

### 3️⃣ Error Handling & Resilience

```
WorkflowError (base)
├── AgentInvocationError    — Agent call failed
├── ContextHandoffError     — Inter-agent data transfer issue
├── ClientNotFoundError     — Client ID not found in search
└── InvalidClientIdError    — Format validation failed (expects CLT-XXXXX)
```

- 🔁 **Retry decorator** with exponential backoff for transient errors (`ConnectionError`, `TimeoutError`)
- ✅ **Cross-stage consistency checks** — Corrects mismatched `client_id` or `risk_score` between agents

---

## 🔎 Azure AI Search Integration

### Index: `client-risk-data`

| Field | Type | Filterable | Searchable | Purpose |
|-------|------|:----------:|:----------:|---------|
| `client_id` | String | ✅ | ✅ | **Primary filter** for all queries |
| `document_type` | String | ✅ | ✅ | KYC, Financial, Compliance, etc. |
| `compliance_status` | String | ✅ | — | current, expired, pending |
| `risk_flags` | Collection | ✅ | ✅ | kyc_expired, adverse_media, etc. |
| `document_content` | String | — | ✅ | Full text (English analyzer) |

### Search Configuration

- **🔍 Query Type:** `vector_semantic_hybrid` (keyword + vector + semantic ranking)
- **📊 Semantic Config:** `default-semantic` with title, content, and keyword fields
- **⚖️ Scoring Profile:** `risk-boost` — weights `risk_flags` (3.0×), `document_content` (2.0×), `notes` (1.5×)

---

## 📊 Risk Scoring Engine

### Severity Weights

| Severity | Weight | Examples |
|----------|:------:|---------|
| 🔴 **Critical** | 3 | Missing compliance docs, expired certifications, watchlist match |
| 🟡 **Major** | 2 | Conflicting records, outdated critical data |
| 🟢 **Minor** | 1 | Missing optional fields, formatting inconsistencies |

### Score Calculation

```
weighted_score = Σ (discrepancy_count × severity_weight)
```

| Weighted Score | Risk Level | Action |
|:--------------:|:----------:|--------|
| `0` | 🟢 **Low** | No action required |
| `1 – 5` | 🟡 **Medium** | Review suggested |
| `≥ 6` | 🔴 **High** | Immediate action required |

> ⚠️ **Conservative Escalation:** When uncertain, the agent escalates to a higher risk category.

### Rules Applied

| ID | Category | Rule |
|----|----------|------|
| D1 | Discrepancy | Missing required fields |
| D2 | Discrepancy | Data format inconsistency |
| D3 | Discrepancy | Cross-reference conflicts |
| D4 | Discrepancy | Outdated or stale data |
| D5 | Discrepancy | Duplicate or conflicting entries |
| C1 | Compliance | Mandatory documents exist |
| C2 | Compliance | Compliance dates current |
| C3 | Compliance | Certifications valid |
| C4 | Compliance | Regulatory requirements met |
| C5 | Compliance | Watchlist/flag indicators |

---

## 📄 Agent Output Contracts

<details>
<summary><strong>🔍 CategorizeRiskAgent → RiskAssessment</strong></summary>

```json
{
  "client_id": "CLT-10001",
  "risk_score": "Low",
  "weighted_score": 0,
  "discrepancy_count": 0,
  "search_results": [
    {
      "document_id": "doc-001",
      "relevance_score": 0.95,
      "content_summary": "KYC documentation is current and complete",
      "fields": {}
    }
  ],
  "rule_evaluations": [
    {
      "rule_id": "C1",
      "rule_name": "Mandatory compliance documents exist",
      "passed": true,
      "severity": "Critical",
      "details": "All required documents present"
    }
  ],
  "reasoning": "All compliance checks passed with no discrepancies detected."
}
```
</details>

<details>
<summary><strong>📝 SummarizeAgent → SummaryOutput</strong></summary>

```json
{
  "client_id": "CLT-10001",
  "risk_score": "Low",
  "summary_markdown": "## 🟢 LOW RISK — Acme Financial Services\n...",
  "summary_plain_text": "LOW RISK - Acme Financial Services...",
  "key_findings": [
    "All KYC documentation is current",
    "No compliance violations detected"
  ],
  "recommendations": [
    "Continue standard monitoring schedule",
    "Next review date: Q3 2026"
  ],
  "urgency_level": "routine",
  "generated_timestamp": "2026-04-15T05:47:00Z"
}
```
</details>

---

## 💰 Token Economics

Understanding token consumption per agent call is critical for cost management, throttling decisions, and capacity planning.

### How Token Tracking Works

The MAF `AgentResponse` object exposes a `.token_usage` property with `prompt_tokens`, `completion_tokens`, and `total_tokens`. The orchestrator captures this metadata from each agent stage and surfaces it through multiple channels:

```
AgentResponse.token_usage
  ├──▶ AgentStageMetrics (per-agent: CategorizeRisk, Summarize)
  ├──▶ WorkflowResult.total_token_usage (aggregated)
  ├──▶ CLI: 📊 Token Usage panel
  └──▶ Structured log: [WORKFLOW:{id}] tokens(prompt=X, completion=Y, total=Z)
```

### Token Usage Output

```python
# Programmatic access
result = await workflow.execute("CLT-10001")
total = result.total_token_usage
print(f"Total tokens: {total.total_tokens}")
for stage in result.stage_metrics:
    print(f"  {stage.agent_name}: {stage.token_usage.total_tokens}")
```

```
# CLI output (automatic)
╭──────────────── 📊 Token Usage ─────────────────╮
│  CategorizeRiskAgent: prompt=1,200  completion=450  total=1,650  │
│  SummarizeAgent:      prompt=1,800  completion=600  total=2,400  │
│  ──────────────────────────────────────────────────              │
│  Total:               prompt=3,000  completion=1,050 total=4,050 │
╰─────────────────────────────────────────────────────────────────╯
```

### When to Implement Throttling

Use token usage data to inform throttling decisions:

| Signal | Threshold | Action |
|--------|-----------|--------|
| Single request tokens | > 10,000 total | Log warning; consider prompt optimization |
| Per-minute aggregate | Approaching model TPM limit | Enable APIM token rate limiting |
| Per-hour cost | > budget threshold | Alert + reject non-critical requests |
| Sustained high usage | > 80% capacity for 5+ min | Activate backend pool failover |

> **Note**: Local token tracking provides per-request visibility. For cross-request aggregation and enforcement, deploy **Azure API Management** as an AI Gateway (see [Graceful Degradation](#-graceful-degradation--ai-gateway)).

---

## 🛡️ Graceful Degradation & AI Gateway

Production deployments should use **Azure API Management (APIM)** as an AI Gateway in front of Foundry endpoints. APIM provides multiple modalities for handling rate limits, backend failures, and capacity exhaustion that the local orchestrator cannot implement alone.

### Architecture — APIM as AI Gateway

```mermaid
graph LR
    subgraph LOCAL["🖥️ Local Orchestrator"]
        CB["🔄 Circuit Breaker"]
        RETRY["🔁 Retry Logic"]
        TIMEOUT["⏱️ Timeout"]
    end

    subgraph APIM["🌐 Azure API Management (AI Gateway)"]
        TRL["📊 Token Rate Limit"]
        R429["🔁 429 + Retry-After"]
        BPF["🔀 Backend Pool Failover"]
        CACHE["💾 Cached Fallback"]
        DIAG["📋 Diagnostic Logging"]
    end

    subgraph FOUNDRY["☁️ Azure AI Foundry"]
        PRIMARY["🤖 Primary Endpoint"]
        BACKUP["🤖 Backup Endpoint"]
    end

    subgraph MONITOR["📈 Monitoring"]
        AM["Azure Monitor"]
        LA["Log Analytics"]
    end

    LOCAL -->|"HTTPS"| APIM
    APIM -->|"Primary"| PRIMARY
    APIM -->|"Failover"| BACKUP
    DIAG --> AM
    AM --> LA
```

### Degradation Modalities

| # | Modality | APIM Policy | When It Triggers |
|---|----------|-------------|-----------------|
| 1 | **Token rate limiting** | `azure-openai-token-limit` | Token budget per minute/hour exhausted |
| 2 | **HTTP 429 handling** | `retry` + `Retry-After` header | Backend returns 429; APIM respects wait time and retries or propagates to caller |
| 3 | **Backend pool failover** | `set-backend-service` in `<choose>` | Primary endpoint returns 429/5xx; traffic routes to secondary Foundry deployment |
| 4 | **Gateway circuit breaker** | Context variable tracking + `return-response` | Consecutive backend failures detected at gateway level |
| 5 | **Cached fallback** | `cache-lookup` / `cache-store` | Return cached risk assessment for recently-evaluated clients during outages |
| 6 | **Queue-based buffering** | Service Bus integration | Buffer excess requests during peak load instead of rejecting |
| 7 | **Graceful error response** | `return-response` with custom body | Return informative error with retry guidance instead of raw 429/503 |

### Example APIM Policy (429 Failover)

```xml
<outbound>
    <choose>
        <when condition="@(context.Response.StatusCode == 429)">
            <!-- Failover to backup Foundry endpoint -->
            <set-backend-service base-url="https://foundry-backup.services.ai.azure.com/api/projects/dev" />
            <forward-request />
        </when>
    </choose>
</outbound>
```

### How Local Resilience Complements APIM

| Layer | Handles | Doesn't Handle |
|-------|---------|----------------|
| **Local** (circuit breaker, retry, timeout) | Transient failures, deadline enforcement, state isolation | Cross-consumer token budgets, backend pool routing, 429 aggregation |
| **APIM** (AI Gateway) | Token rate limits, 429 failover, backend pools, request logging | Conversation state, JSON parsing, cross-agent consistency |

> Both layers are complementary. The local circuit breaker protects the orchestrator; APIM protects the entire system.

---

## 🔭 Observability Pipeline

The observability system captures three types of telemetry from agent executions: **token usage**, **reasoning traces**, and **workflow metrics**. Data flows through a three-tier pipeline.

### Three-Tier Observability Architecture

```
Tier 1: LOCAL CLI                    Tier 2: APIM GATEWAY              Tier 3: LOG ANALYTICS
┌─────────────────────┐     ┌─────────────────────────┐     ┌─────────────────────┐
│ 📊 Token usage      │     │ 📋 Request/response     │     │ 📈 Cross-project    │
│    panel             │     │    logging              │     │    analytics        │
│ 💭 Reasoning traces │     │ 📊 Token consumption    │     │ 🔍 Query & alerting │
│    (dim magenta)    │     │    metrics              │     │ 📊 Dashboards       │
│ 🔗 Correlation IDs  │     │ ⏱️ Latency percentiles │     │ 📦 Long-term store  │
└─────────────────────┘     └─────────────────────────┘     └─────────────────────┘
        ▲                            ▲                              ▲
        │                            │                              │
   Orchestrator               APIM Diagnostic              Foundry v2 SDK
   _extract_stage_metrics()    Settings                    Telemetry Pipeline
```

### Reasoning Traces

MAF `AgentResponse` messages may include a `.reasoning` property containing the model's chain-of-thought process — the step-by-step logic the agent used to arrive at its answer. This is **separate from the structured JSON output** and provides crucial insight into agent decision-making.

**Capture Flow**:
```
AgentResponse
  ├── .text       → Structured JSON output (parsed → RiskAssessment / SummaryOutput)
  ├── .reasoning  → Chain-of-thought trace (captured → AgentStageMetrics.reasoning)
  └── .token_usage → Token counts (captured → AgentStageMetrics.token_usage)
```

**CLI Display** (via `--verbose`):

```
╭──── 💭 CategorizeRiskAgent Reasoning ─────╮
│ I queried the knowledge base for           │
│ CLT-10001 and found 2 documents. Both      │
│ show current compliance status with no     │
│ risk flags. Applied rules D1-D5 and        │
│ C1-C5: all passed. Weighted score = 0.     │
│ Classification: Low risk.                   │
╰────────────────────────────────────────────╯
```

> Reasoning is rendered in **dim magenta** to visually distinguish it from the primary output. Enable with `--verbose` flag or `ENABLE_REASONING_DISPLAY=true`.

### Observability Configuration

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| **Reasoning display** | `ENABLE_REASONING_DISPLAY` | `true` | Show reasoning traces in CLI (when `--verbose` is used) |

### Pipeline to Log Analytics (Future)

The full observability pipeline routes telemetry from the local orchestrator through Foundry v2 to a Log Analytics workspace:

1. **Local orchestrator** → Structured logs with correlation IDs, token counts, reasoning
2. **Foundry v2 SDK** → Agent invocation telemetry sent to the Foundry project
3. **Foundry project diagnostic settings** → Route telemetry to Log Analytics workspace
4. **APIM diagnostic settings** → Route request/response logs and token metrics to Log Analytics
5. **Log Analytics** → KQL queries for cross-project analysis, alerting, and dashboards

```
Local Orchestrator                    Azure
┌─────────────────┐     ┌──────────────────────────────────────┐
│ _extract_stage_  │     │  Foundry v2 Project                 │
│  metrics()       │────▶│  • Agent telemetry                  │
│                  │     │  • Diagnostic settings ──────────┐  │
│ Structured logs  │     └──────────────────────────────────│──┘
│ [WORKFLOW:{id}]  │                                        │
│                  │     ┌──────────────────────────────┐   │
│                  │     │  APIM AI Gateway              │   │
│                  │────▶│  • Request/response logs      │   │
│                  │     │  • Token metrics ─────────┐   │   │
└─────────────────┘     └──────────────────────────│───┘   │
                                                    ▼       ▼
                                          ┌─────────────────────┐
                                          │  Log Analytics       │
                                          │  Workspace           │
                                          │  • KQL queries       │
                                          │  • Alert rules       │
                                          │  • Workbooks         │
                                          └─────────────────────┘
```

---

## ✅ Prerequisites

Before running this sample, ensure you have:

| Requirement | Details |
|-------------|---------|
| 🐍 **Python** | 3.10 or higher |
| ☁️ **Azure Subscription** | With Azure AI Foundry access |
| 🏗️ **Azure AI Foundry Project** | Provisioned with a GPT-5.2 model deployment |
| 🔎 **Azure AI Search** | Service with the `client-risk-data` index created |
| 🔐 **Azure CLI** | Logged in (`az login`) for local `DefaultAzureCredential` |
| 🤖 **Foundry Agents** | Both `CategorizeRiskAgent` and `SummarizeAgent` deployed |

---

## 🚀 Getting Started

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/your-org/Foundy-v2-mas-workflow-sample.git
cd Foundy-v2-mas-workflow-sample/code
```

### 2️⃣ Create a Virtual Environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

### 4️⃣ Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` with your Foundry project details:

```ini
FOUNDRY_ENDPOINT=https://foundry-cc-canada.services.ai.azure.com/api/projects/dev
CATEGORIZE_AGENT_NAME=CategorizeRiskAgent
CATEGORIZE_AGENT_VERSION=1
SUMMARIZE_AGENT_NAME=SummarizeAgent
SUMMARIZE_AGENT_VERSION=1
WORKFLOW_TIMEOUT_SECONDS=60
RETRY_COUNT=3
LOG_LEVEL=INFO
```

### 5️⃣ Authenticate with Azure

```bash
az login
```

### 6️⃣ One-Time Setup (if creating resources from scratch)

```bash
# Create the Azure AI Search index and upload sample data
python scripts/create_search_index.py

# Deploy the agents to Foundry
python scripts/create_agents.py
```

---

## ▶️ Running the Sample

### Basic Usage

```bash
# Run risk assessment for a client
python -m src.main CLT-10001
```

**Example Output:**
```
╭────────────────────────────────────────────────╮
│          Risk Assessment Complete               │
├────────────────────────────────────────────────┤
│ Client ID:  CLT-10001                           │
│ Risk Score: 🟢 LOW                              │
╰────────────────────────────────────────────────╯

## Risk Assessment Summary
**Client ID**: CLT-10001
**Risk Classification**: 🟢 LOW RISK
...
```

### JSON Output

```bash
# Get raw JSON output (for piping to other tools)
python -m src.main CLT-10001 --json
```

### Verbose Output (Reasoning Traces)

```bash
# Show agent reasoning traces alongside the risk assessment
python -m src.main CLT-10001 --verbose

# Combine with JSON output
python -m src.main CLT-10001 --json --verbose
```

The `--verbose` flag displays each agent's chain-of-thought reasoning in a distinct **magenta** panel, helping you understand *why* the agent made its classification decision. Token usage is always displayed when available.

---

## 🧪 Test Data

Five pre-loaded test clients are available in the Azure AI Search index:

| Client ID | Company | Expected Risk | Key Characteristics |
|-----------|---------|:-------------:|---------------------|
| `CLT-10001` | Acme Financial Services | 🟢 **Low** | All compliant, current documentation |
| `CLT-20002` | GlobalTech Industries | 🟡 **Medium** | Ownership change pending, expiring cert |
| `CLT-30003` | Northern Trust Holdings | 🔴 **High** | Expired KYC, adverse media, regulatory investigation |
| `CLT-40004` | Maple Leaf Ventures | 🟢 **Low** | Minor revenue decline, otherwise compliant |
| `CLT-50005` | Pacific Rim Trading Co | 🔴 **High** | High-risk jurisdiction, unusual transactions |

---

## 🧪 Testing

All tests use mocked agents — **no Azure connectivity required**.

```bash
# Run full test suite
python -m pytest tests/ -v

# Run specific test class
python -m pytest tests/test_workflow.py::TestRiskAssessmentWorkflow -v

# Run with coverage
python -m pytest tests/ -v --cov=src
```

### Test Coverage

| Test File | What It Tests |
|-----------|---------------|
| `test_workflow.py` | Orchestrator logic, agent chaining, consistency checks |
| `test_models.py` | Pydantic model validation, client ID format regex |
| `test_config.py` | Environment variable loading, defaults |
| `test_errors.py` | Exception hierarchy, retry decorator behavior |
| `test_agents.py` | Code fence stripping helper |
| `test_resilience.py` | Circuit breaker, async retry, concurrency limiter, typed exceptions |

---

## 🛡️ Resilience & Actor Pattern Compliance

This codebase implements execution-safety patterns inspired by the [Actor Pattern](external_sources/actor-pattern.md) to bridge the gap between AI reasoning and production reliability. See the full prompt contract: [ACTOR-PATTERN-COMPLIANCE.md](prompt-contracts/ACTOR-PATTERN-COMPLIANCE.md).

### Why This Matters

Agent frameworks handle **reasoning** — they do NOT handle **execution safety**. Without resilience patterns, a single backend outage can trigger retry storms, unbounded waits, and cascading failures across all concurrent users. These patterns fill that gap.

### Implemented Patterns

| Pattern | Module | What It Does |
|---------|--------|--------------|
| **Timeout Enforcement** | `orchestrator.py` | `asyncio.wait_for()` bounds every workflow execution to a hard deadline |
| **Circuit Breaker** | `resilience.py` | CLOSED → OPEN → HALF-OPEN state machine; fast-rejects when backend is failing |
| **Async Retry** | `resilience.py` | Exponential backoff on transient failures only; never retries parse/validation errors |
| **Concurrency Limiter** | `resilience.py` | Semaphore-based with fast-fail acquisition timeout (for service deployment) |
| **Typed Exceptions** | `errors.py` | `WorkflowTimeoutError`, `CircuitOpenError` for actionable error handling and UX |
| **Correlation IDs** | `orchestrator.py` | Unique ID per execution for distributed tracing and log correlation |

### Service Limits & Defaults

#### Timeout & Retry

| Setting | Env Var | Default | Behavior |
|---------|---------|---------|----------|
| **Workflow Timeout** | `WORKFLOW_TIMEOUT_SECONDS` | `30` | Hard deadline for the entire workflow execution including all retry attempts. Enforced via `asyncio.wait_for()`. If exceeded, raises `WorkflowTimeoutError`. |
| **Retry Count** | `RETRY_COUNT` | `3` | Maximum number of attempts before propagating the error. Only transient failures (connection, timeout, OS) are retried — parse and validation errors fail immediately. |
| **Retry Base Delay** | `RETRY_BASE_DELAY` | `1.0` | Initial backoff seed in seconds. Doubles each attempt (1s → 2s → 4s). Sleep is automatically capped so retries never extend past the workflow timeout deadline. |

> **How timeout and retry interact**: The retry loop operates within a total deadline budget equal to `WORKFLOW_TIMEOUT_SECONDS`. Each attempt checks the remaining time *before* executing and *before* sleeping. This guarantees users never wait longer than the configured timeout, regardless of how many retries are configured.

#### Circuit Breaker (Throttling Protection)

The circuit breaker prevents retry storms when the LLM backend is unhealthy. It uses a three-state machine:

```
    CLOSED (normal)  ──[threshold failures]──►  OPEN (rejecting)
         ▲                                          │
         │                                   [recovery period]
    [probe succeeds]                                │
         │                                          ▼
         └───────────────────────────────  HALF-OPEN (1 probe)
                                                    │
                                            [probe fails → re-open]
```

| Setting | Env Var | Default | Behavior |
|---------|---------|---------|----------|
| **Failure Threshold** | `CIRCUIT_BREAKER_THRESHOLD` | `3` | Number of **consecutive** transient failures before the circuit opens. Only infrastructure failures count — parse errors and validation failures are ignored. |
| **Recovery Period** | `CIRCUIT_BREAKER_RECOVERY_SECONDS` | `30.0` | Seconds the breaker stays OPEN before transitioning to HALF-OPEN. In HALF-OPEN, exactly **one probe request** is allowed through. If the probe succeeds, the breaker closes. If it fails, the breaker re-opens for another recovery period. |

> **What gets rejected**: When OPEN, all calls immediately receive a `CircuitOpenError` with `recovery_remaining` seconds — no backend call is made. This protects both your system and the LLM backend from load amplification during outages.

#### Concurrency Limits

| Setting | Env Var | Default | Behavior |
|---------|---------|---------|----------|
| **Max Concurrent Requests** | `MAX_CONCURRENT_REQUESTS` | `5` | Maximum parallel workflow executions (semaphore slots). When all slots are occupied, new requests wait up to 5 seconds for a slot. If no slot becomes available, the request is rejected (fast-fail). |

> **Note**: The concurrency limiter is available in `src/resilience.py` for service deployment. The CLI entry point (`main.py`) runs a single invocation and doesn't require it.

### Failure Classification

The retry and circuit breaker systems classify failures to avoid wasting resources on irrecoverable errors:

| Failure Type | Retried? | Trips Breaker? | Examples |
|-------------|----------|----------------|----------|
| **Transient** | ✅ Yes | ✅ Yes | `ConnectionError`, `TimeoutError`, `asyncio.TimeoutError`, `OSError` |
| **Validation** | ❌ No | ❌ No | `InvalidClientIdError`, Pydantic `ValueError` |
| **Contract** | ❌ No | ❌ No | `AgentInvocationError` (bad JSON, client_id mismatch) |
| **Timeout** | ❌ No | ✅ Yes | `WorkflowTimeoutError` (deadline exceeded) |

### Configuration Example

Add these to your `.env` file or set as environment variables:

```bash
# ── Execution Limits ───────────────────────────────
WORKFLOW_TIMEOUT_SECONDS=30        # Total deadline for workflow (seconds)
RETRY_COUNT=3                      # Max retry attempts for transient failures
RETRY_BASE_DELAY=1.0               # Backoff seed — doubles each retry (seconds)

# ── Circuit Breaker ────────────────────────────────
CIRCUIT_BREAKER_THRESHOLD=3        # Consecutive failures before OPEN
CIRCUIT_BREAKER_RECOVERY_SECONDS=30.0  # Seconds before HALF-OPEN probe

# ── Concurrency (for service deployment) ───────────
MAX_CONCURRENT_REQUESTS=5          # Max parallel workflow executions

# ── Observability ──────────────────────────────────
ENABLE_REASONING_DISPLAY=true      # Show reasoning traces (with --verbose)
```

> All settings use `load_dotenv(override=False)` — Foundry runtime environment variables always take precedence over `.env` file values.

### Cross-Cutting Concerns Scorecard

| Concern | Score | Status |
|---------|-------|--------|
| Isolation | 55% | 🟡 Fresh builder per call; no actor mailbox |
| Determinism | 40% | 🟡 Sequential pipeline; no request serialization |
| Concurrency Safety | 25% | 🟡 Limiter available; not wired for CLI |
| Supervision | 40% | 🟢 Async retry + typed exceptions |
| Separation of Concerns | 50% | 🟢 Resilience layer separated |
| Fast Failures | 50% | 🟢 asyncio.wait_for() enforced |
| Circuit Breaker | 35% | 🟢 Full state machine |
| Token Economics | 25% | 🟡 Per-stage usage tracked; APIM for enforcement |
| Graceful Degradation | 20% | 🟡 Local breaker; APIM recommended for 429/failover |
| Observability | 50% | 🟢 Tokens, reasoning, correlation IDs, durations |

See [ACTOR-PATTERN-COMPLIANCE.md](prompt-contracts/ACTOR-PATTERN-COMPLIANCE.md) for the full prompt contract with goals, microgoals, ADRs, and testing checklists.

---

## 📁 Project Structure

```
Foundy-v2-mas-workflow-sample/
│
├── 📄 README.md                          ← You are here
│
├── 📂 prompt-contracts/                  ← Agent design & specifications
│   ├── CATEGORIZE-RISK-AGENT.md          ← CategorizeRiskAgent prompt contract
│   ├── SUMMARIZE-AGENT.md                ← SummarizeAgent prompt contract
│   ├── ORCHESTRATION.md                  ← MAF orchestration patterns
│   ├── WORKFLOW-ARCHITECTURE.md          ← Architecture decisions
│   ├── ACTOR-PATTERN-COMPLIANCE.md       ← Actor Pattern cross-cutting concerns
│   └── sample-data/
│       ├── client-risk-data.json         ← 10 sample documents (5 clients)
│       └── index-schema.json             ← AI Search index definition
│
└── 📂 code/                              ← Working implementation
    ├── src/
    │   ├── main.py                       ← CLI entry point
    │   ├── config.py                     ← Environment-driven configuration
    │   ├── errors.py                     ← Exception hierarchy (typed resilience errors)
    │   ├── progress.py                   ← Rich console progress display
    │   ├── resilience.py                 ← Circuit breaker, async retry, concurrency limiter
    │   ├── agents/
    │   │   └── base_agent.py             ← Code fence stripping utility
    │   ├── workflow/
    │   │   ├── orchestrator.py           ← SequentialBuilder workflow
    │   │   └── context.py                ← WorkflowResult builder
    │   └── models/
    │       ├── input.py                  ← WorkflowInput (CLT-XXXXX regex)
    │       └── output.py                 ← Pydantic output schemas
    ├── tests/                            ← Full test suite (mocked agents)
    ├── scripts/
    │   ├── create_agents.py              ← Deploy agents to Foundry
    │   └── create_search_index.py        ← Create AI Search index
    ├── requirements.txt
    ├── pyproject.toml
    └── .env.example
```

---

## 📜 License

This project is provided as a sample for educational and demonstration purposes.

---

<p align="center">
  Built with ❤️ using <strong>Azure AI Foundry</strong> and <strong>Microsoft Agent Framework</strong>
</p>
