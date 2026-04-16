# Workflow Architecture Contract

## Document Purpose

This contract defines the overall architecture, data flow, and integration patterns for the Risk Assessment Multi-Agent Workflow built on Azure AI Foundry v2 with Microsoft Agent Framework orchestration.

---

## 🎯 Primary Goal

Build a sequential multi-agent workflow that accepts a Client ID, performs risk categorization using knowledge retrieval (AI Search), and produces a human-readable risk assessment summary.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     MICROSOFT AGENT FRAMEWORK                           │
│                        (Local Orchestrator)                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌──────────┐     ┌─────────────────────┐     ┌──────────────────┐    │
│   │  INPUT   │────▶│ CategorizeRiskAgent │────▶│  SummarizeAgent  │    │
│   │Client ID │     │   (Foundry v2)      │     │   (Foundry v2)   │    │
│   └──────────┘     └─────────────────────┘     └──────────────────┘    │
│                              │                          │               │
│                              ▼                          ▼               │
│                    ┌─────────────────┐         ┌───────────────┐        │
│                    │ AI Search Index │         │ Final Output  │        │
│                    │ (Hybrid+Semantic)│         │ Risk Summary  │        │
│                    └─────────────────┘         └───────────────┘        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │     AZURE AI FOUNDRY v2       │
                    │  foundry-cc-canada project    │
                    └───────────────────────────────┘
```

---

## Data Flow Specification

### Stage 1: Input Ingestion

| Property | Value |
|----------|-------|
| Input Type | Single `client_id` (string) |
| Source | External caller / API |
| Validation | Non-empty, valid client identifier format |

### Stage 2: Risk Categorization (Agent 1)

| Property | Value |
|----------|-------|
| Agent Name | `CategorizeRiskAgent` |
| Agent Version | `1` |
| Input | `client_id` |
| Knowledge Source | Azure AI Search Index |
| Search Type | Hybrid with Semantic Ranker |
| Output | Risk Score (`Low` / `Medium` / `High`) + Search Results |

### Stage 3: Summarization (Agent 2)

| Property | Value |
|----------|-------|
| Agent Name | `SummarizeAgent` |
| Agent Version | `1` |
| Input | Risk Score + Search Results from Stage 2 |
| Output | Natural language risk summary with reasoning |

### Stage 4: Final Output

| Property | Value |
|----------|-------|
| Format | JSON or structured text |
| Contents | Client ID, Risk Score, Summary, Reasoning |

---

## Microgoals for Implementation

### MG-ARCH-001: Environment Setup
- [ ] Install `azure-ai-projects>=2.0.0`
- [ ] Configure Azure CLI authentication
- [ ] Verify connectivity to Foundry endpoint
- [ ] Validate access to both hosted agents

### MG-ARCH-002: Client Configuration
- [ ] Initialize `AIProjectClient` with endpoint
- [ ] Configure `DefaultAzureCredential` for local dev
- [ ] Create OpenAI client wrapper for agent invocation

### MG-ARCH-003: Agent Reference Pattern
- [ ] Implement agent reference structure:
  ```python
  {
      "agent_reference": {
          "name": "<agent_name>",
          "version": "<version>",
          "type": "agent_reference"
      }
  }
  ```
- [ ] Create reusable agent invocation function

### MG-ARCH-004: Sequential Workflow Pattern
- [ ] Implement synchronous agent chaining
- [ ] Design context passing between agents
- [ ] Handle response parsing and transformation

### MG-ARCH-005: Error Handling
- [ ] Implement retry logic for transient failures
- [ ] Add timeout handling for agent responses
- [ ] Log all agent interactions for debugging

---

## Integration Points

### Azure AI Foundry v2

| Component | Configuration |
|-----------|---------------|
| Endpoint | `https://foundry-cc-canada.services.ai.azure.com/api/projects/dev` |
| Authentication | `DefaultAzureCredential` (Azure CLI) |
| API Pattern | `responses.create()` with `agent_reference` extra_body |

### Azure AI Search (Knowledge Source)

| Component | Configuration |
|-----------|---------------|
| Service | Connected resource in Foundry `dev` project |
| Index Name | `client-risk-data` |
| Search Type | Hybrid (keyword + vector) |
| Ranking | Semantic Ranker enabled |
| Filter | `client_id` field filter |
| Integration | Accessed via Foundry Projects SDK |

#### Index Schema: `client-risk-data`

```json
{
  "name": "client-risk-data",
  "fields": [
    { "name": "id", "type": "Edm.String", "key": true, "filterable": true },
    { "name": "client_id", "type": "Edm.String", "filterable": true, "searchable": true },
    { "name": "client_name", "type": "Edm.String", "searchable": true },
    { "name": "document_type", "type": "Edm.String", "filterable": true, "facetable": true },
    { "name": "compliance_status", "type": "Edm.String", "filterable": true, "facetable": true },
    { "name": "compliance_expiry_date", "type": "Edm.DateTimeOffset", "filterable": true, "sortable": true },
    { "name": "last_review_date", "type": "Edm.DateTimeOffset", "filterable": true, "sortable": true },
    { "name": "risk_flags", "type": "Collection(Edm.String)", "filterable": true, "searchable": true },
    { "name": "document_content", "type": "Edm.String", "searchable": true },
    { "name": "notes", "type": "Edm.String", "searchable": true },
    { "name": "content_vector", "type": "Collection(Edm.Single)", "dimensions": 1536, "vectorSearchProfile": "default-profile" }
  ],
  "vectorSearch": {
    "profiles": [{ "name": "default-profile", "algorithm": "default-algorithm" }],
    "algorithms": [{ "name": "default-algorithm", "kind": "hnsw" }]
  },
  "semantic": {
    "configurations": [{
      "name": "default-semantic",
      "prioritizedFields": {
        "contentFields": [{ "fieldName": "document_content" }],
        "titleField": { "fieldName": "document_type" },
        "keywordsFields": [{ "fieldName": "risk_flags" }]
      }
    }]
  }
}
```

#### Sample Data (5 Clients)

```json
[
  {
    "id": "CLT-10001-DOC-001",
    "client_id": "CLT-10001",
    "client_name": "Acme Financial Services",
    "document_type": "KYC Verification",
    "compliance_status": "current",
    "compliance_expiry_date": "2027-06-15T00:00:00Z",
    "last_review_date": "2026-03-01T00:00:00Z",
    "risk_flags": [],
    "document_content": "KYC verification completed. All identity documents verified. Business registration confirmed. Beneficial ownership structure documented. No adverse media findings.",
    "notes": "Annual review completed on schedule. All documentation current."
  },
  {
    "id": "CLT-10001-DOC-002",
    "client_id": "CLT-10001",
    "client_name": "Acme Financial Services",
    "document_type": "Financial Statement",
    "compliance_status": "current",
    "compliance_expiry_date": "2027-01-31T00:00:00Z",
    "last_review_date": "2026-02-15T00:00:00Z",
    "risk_flags": [],
    "document_content": "Audited financial statements for FY2025. Revenue: $12.5M. Net income positive. Debt-to-equity ratio within acceptable limits. No material weaknesses identified.",
    "notes": "Clean audit opinion received."
  },
  {
    "id": "CLT-20002-DOC-001",
    "client_id": "CLT-20002",
    "client_name": "GlobalTech Industries",
    "document_type": "KYC Verification",
    "compliance_status": "current",
    "compliance_expiry_date": "2026-12-01T00:00:00Z",
    "last_review_date": "2025-12-01T00:00:00Z",
    "risk_flags": ["ownership_change_pending"],
    "document_content": "KYC verification completed. Identity documents verified. Note: Pending acquisition by ParentCorp Holdings expected Q2 2026. Beneficial ownership structure may change.",
    "notes": "Monitor for ownership structure changes. Re-verification required post-acquisition."
  },
  {
    "id": "CLT-20002-DOC-002",
    "client_id": "CLT-20002",
    "client_name": "GlobalTech Industries",
    "document_type": "Compliance Certificate",
    "compliance_status": "expiring_soon",
    "compliance_expiry_date": "2026-05-01T00:00:00Z",
    "last_review_date": "2025-05-01T00:00:00Z",
    "risk_flags": ["expiring_certification"],
    "document_content": "ISO 27001 certification valid until May 2026. SOC 2 Type II report on file. GDPR compliance attestation current.",
    "notes": "ISO certification renewal in progress. Follow up required."
  },
  {
    "id": "CLT-30003-DOC-001",
    "client_id": "CLT-30003",
    "client_name": "Northern Trust Holdings",
    "document_type": "KYC Verification",
    "compliance_status": "expired",
    "compliance_expiry_date": "2026-01-15T00:00:00Z",
    "last_review_date": "2025-01-15T00:00:00Z",
    "risk_flags": ["kyc_expired", "review_overdue"],
    "document_content": "KYC verification expired. Last verification January 2025. Multiple requests for updated documentation sent. Client unresponsive to renewal requests.",
    "notes": "URGENT: KYC expired 3 months ago. Escalate to relationship manager."
  },
  {
    "id": "CLT-30003-DOC-002",
    "client_id": "CLT-30003",
    "client_name": "Northern Trust Holdings",
    "document_type": "Adverse Media Report",
    "compliance_status": "flagged",
    "compliance_expiry_date": null,
    "last_review_date": "2026-03-28T00:00:00Z",
    "risk_flags": ["adverse_media", "regulatory_investigation"],
    "document_content": "Adverse media alert: News articles from March 2026 indicate regulatory investigation by provincial securities commission regarding disclosure practices. Investigation ongoing. No charges filed.",
    "notes": "Enhanced monitoring required. Weekly adverse media checks recommended."
  },
  {
    "id": "CLT-40004-DOC-001",
    "client_id": "CLT-40004",
    "client_name": "Maple Leaf Ventures",
    "document_type": "KYC Verification",
    "compliance_status": "current",
    "compliance_expiry_date": "2027-08-20T00:00:00Z",
    "last_review_date": "2026-02-20T00:00:00Z",
    "risk_flags": [],
    "document_content": "KYC verification completed. All identity documents verified. Domestic corporation registered in Ontario. Simple ownership structure - single shareholder.",
    "notes": "Low complexity client. Standard review cycle."
  },
  {
    "id": "CLT-40004-DOC-002",
    "client_id": "CLT-40004",
    "client_name": "Maple Leaf Ventures",
    "document_type": "Financial Statement",
    "compliance_status": "current",
    "compliance_expiry_date": "2027-03-31T00:00:00Z",
    "last_review_date": "2026-04-01T00:00:00Z",
    "risk_flags": ["revenue_decline"],
    "document_content": "Review engagement financial statements FY2025. Revenue: $2.1M (down 15% YoY). Net income: $180K. Cash position adequate. Note: Revenue decline attributed to loss of major customer.",
    "notes": "Monitor financial health. Revenue decline within acceptable threshold."
  },
  {
    "id": "CLT-50005-DOC-001",
    "client_id": "CLT-50005",
    "client_name": "Pacific Rim Trading Co",
    "document_type": "KYC Verification",
    "compliance_status": "current",
    "compliance_expiry_date": "2026-11-30T00:00:00Z",
    "last_review_date": "2025-11-30T00:00:00Z",
    "risk_flags": ["high_risk_jurisdiction", "complex_ownership"],
    "document_content": "KYC verification completed with enhanced due diligence. Complex multi-jurisdictional ownership structure spanning Canada, Singapore, and British Virgin Islands. UBO identified and verified.",
    "notes": "High-risk jurisdiction exposure requires enhanced monitoring. Semi-annual review cycle."
  },
  {
    "id": "CLT-50005-DOC-002",
    "client_id": "CLT-50005",
    "client_name": "Pacific Rim Trading Co",
    "document_type": "Transaction Monitoring Report",
    "compliance_status": "flagged",
    "compliance_expiry_date": null,
    "last_review_date": "2026-04-10T00:00:00Z",
    "risk_flags": ["unusual_transaction_pattern", "large_cash_movements"],
    "document_content": "Transaction monitoring alert: Unusual pattern detected - multiple large wire transfers to new counterparties in high-risk jurisdictions over past 30 days. Total value: $4.2M. Pattern deviates from historical baseline.",
    "notes": "SAR consideration required. Compliance review scheduled for April 15."
  }
]
```

#### Expected Risk Scores by Client

| Client ID | Client Name | Expected Risk | Reason |
|-----------|-------------|---------------|--------|
| CLT-10001 | Acme Financial Services | **Low** | All documents current, no flags |
| CLT-20002 | GlobalTech Industries | **Medium** | Pending ownership change, expiring certification |
| CLT-30003 | Northern Trust Holdings | **High** | Expired KYC, adverse media, regulatory investigation |
| CLT-40004 | Maple Leaf Ventures | **Low** | Current compliance, minor revenue flag |
| CLT-50005 | Pacific Rim Trading Co | **High** | High-risk jurisdiction, unusual transactions, complex ownership |

#### Querying AI Search via Foundry Projects SDK

```python
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

# Initialize client
credential = DefaultAzureCredential()
project_client = AIProjectClient(
    endpoint="https://foundry-cc-canada.services.ai.azure.com/api/projects/dev",
    credential=credential
)

# Get the AI Search connection from Foundry project
search_connection = project_client.connections.get("aisearchhubcanadadrta5x")

# Create search client from connection
from azure.search.documents import SearchClient

search_client = SearchClient(
    endpoint=search_connection.endpoint,
    index_name="client-risk-data",
    credential=credential
)

def query_client_documents(client_id: str) -> list[dict]:
    """
    Query AI Search for all documents related to a client.
    Uses hybrid search with semantic ranking.
    """
    results = search_client.search(
        search_text=f"client {client_id}",
        filter=f"client_id eq '{client_id}'",
        query_type="semantic",
        semantic_configuration_name="default-semantic",
        top=20,
        select=["id", "client_id", "client_name", "document_type", 
                "compliance_status", "compliance_expiry_date", 
                "risk_flags", "document_content", "notes"]
    )
    
    return [dict(result) for result in results]


def hybrid_search_with_context(client_id: str, query: str) -> list[dict]:
    """
    Hybrid search combining filter + semantic search for richer context.
    """
    results = search_client.search(
        search_text=query,
        filter=f"client_id eq '{client_id}'",
        query_type="semantic",
        semantic_configuration_name="default-semantic",
        top=10,
    )
    
    return [dict(result) for result in results]
```

#### Alternative: Using Foundry Agent with Knowledge Tool

If the CategorizeRiskAgent is configured with AI Search as a knowledge source in Foundry, it can query the index automatically via the agent's tool:

```python
# The hosted agent already has access to the search index
# Simply invoke the agent with the client ID - it will search automatically

response = openai_client.responses.create(
    input=[{
        "role": "user", 
        "content": f"Evaluate risk for client {client_id}. Query all their documents."
    }],
    extra_body={
        "agent_reference": {
            "name": "CategorizeRiskAgent",
            "version": "1",
            "type": "agent_reference"
        }
    }
)
```

---

## AI Gateway (Azure API Management)

For production deployments, an **AI Gateway** layer (Azure API Management) should sit between the local orchestrator and the Foundry endpoints. This provides capabilities that the local orchestrator cannot implement alone.

### Architecture

```
┌──────────────────┐     ┌─────────────────────────────┐     ┌─────────────────────┐
│  Local           │     │  Azure API Management        │     │  Azure AI Foundry   │
│  Orchestrator    │────▶│  (AI Gateway)                │────▶│  (Primary Endpoint) │
│                  │     │                              │     └─────────────────────┘
│  • Circuit       │     │  • Token rate limiting       │              │
│    breaker       │     │  • 429 → Retry-After         │     ┌────────▼────────────┐
│  • Retry logic   │     │  • Backend pool failover     │────▶│  Azure AI Foundry   │
│  • Timeout       │     │  • Request/response logging  │     │  (Backup Endpoint)  │
│    enforcement   │     │  • Diagnostic settings       │     └─────────────────────┘
└──────────────────┘     │  • Cached fallback           │              │
                         └─────────────────────────────┘              ▼
                                      │                     ┌─────────────────────┐
                                      ▼                     │  Log Analytics      │
                              ┌───────────────┐             │  Workspace          │
                              │ Azure Monitor │────────────▶│  (long-term store)  │
                              └───────────────┘             └─────────────────────┘
```

### Graceful Degradation Modalities

| Modality | APIM Implementation | When to Use |
|----------|---------------------|-------------|
| **Token rate limiting** | `azure-openai-token-limit` policy | Prevent token budget exhaustion across all consumers |
| **HTTP 429 handling** | `retry` policy + `Retry-After` header propagation | Backend is rate-limited; respect and relay wait times |
| **Backend pool failover** | `set-backend-service` in `<choose>` block | Primary Foundry endpoint returns 429 or 5xx; failover to secondary |
| **Circuit breaker (gateway)** | Context variable tracking + `return-response` | Consecutive backend failures detected at gateway level |
| **Cached fallback** | `cache-lookup` / `cache-store` policies | Return cached assessment for recently-evaluated clients during outages |
| **Queue-based buffering** | Service Bus integration policy | Buffer excess requests during peak load instead of rejecting |
| **Graceful error response** | `return-response` with custom body | Return informative error with retry guidance instead of raw 429/503 |

### Token Economics via APIM

APIM serves as the **enforcement point** for token budgets:

1. **Local orchestrator** captures per-request token usage from `AgentResponse.token_usage`
2. **APIM** aggregates token consumption across all consumers via `azure-openai-token-limit` policy
3. **Azure Monitor** receives token metrics from APIM diagnostic settings
4. **Alert rules** trigger when per-minute/per-hour token thresholds are approached

### Observability Pipeline via APIM

APIM provides the **telemetry bridge** between the orchestrator and Log Analytics:

1. **Request/response logging** — APIM captures prompts, responses, and token counts
2. **Diagnostic settings** route logs to a Log Analytics workspace
3. **Agent reasoning traces** (captured locally from `AgentResponse.reasoning`) are logged via structured logging and can be forwarded via Application Insights or direct Log Analytics ingestion
4. **Foundry v2 project** diagnostic settings provide an additional telemetry stream

---

## Success Criteria

1. ✅ Workflow accepts a single `client_id` input
2. ✅ CategorizeRiskAgent successfully queries AI Search with client filter
3. ✅ Risk score is deterministically produced based on defined rules
4. ✅ SummarizeAgent receives full context from previous agent
5. ✅ Final output is human-readable with clear reasoning
6. ✅ End-to-end latency < 30 seconds for typical requests
7. ✅ All errors are gracefully handled with meaningful messages

---

## Dependencies

```
azure-ai-projects>=2.0.0
azure-identity
```

---

## Next Steps

1. Review [CATEGORIZE-RISK-AGENT.md](./CATEGORIZE-RISK-AGENT.md) for agent-specific instructions
2. Review [SUMMARIZE-AGENT.md](./SUMMARIZE-AGENT.md) for summarization instructions
3. Review [ORCHESTRATION.md](./ORCHESTRATION.md) for implementation blueprint
