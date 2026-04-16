# Orchestration Contract - Microsoft Agent Framework

## Document Purpose

This contract defines the implementation blueprint for orchestrating the Risk Assessment workflow using Microsoft Agent Framework as the local orchestrator, coordinating two Foundry v2 hosted agents in a sequential pattern.

---

## 🎯 Primary Goal

Implement a production-ready Python application using Microsoft Agent Framework that orchestrates a sequential multi-agent workflow, invoking Foundry v2 hosted agents via the `azure-ai-projects` SDK, managing context handoff between agents, and producing a final consolidated risk assessment output.

---

## Technology Stack

| Component | Technology | Version |
|-----------|------------|---------|
| Orchestrator | Microsoft Agent Framework | 1.0.0rc3 |
| Hosted Agents | Azure AI Foundry v2 | GA |
| SDK - Agent Framework | agent-framework-azure-ai | 1.0.0rc3 |
| SDK - Agent Framework Core | agent-framework-core | 1.0.0rc3 |
| SDK - Agent Server | azure-ai-agentserver-agentframework | 1.0.0b16 |
| SDK - Agent Server Core | azure-ai-agentserver-core | 1.0.0b16 |
| SDK - Foundry Projects | azure-ai-projects | >=2.0.0 |
| Authentication | azure-identity (async) | Latest |
| Runtime | Python | >=3.10 |

---

## Quick Reference: Key Imports

```python
# Microsoft Agent Framework - Core
from agent_framework import Agent, WorkflowBuilder, Message
from agent_framework.azure import AzureAIClient  # Or AzureOpenAIChatClient

# Concurrent workflows
from agent_framework import ConcurrentBuilder

# Azure Identity - MUST use async (aio) version for MAF
from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential

# HTTP hosting adapter for Foundry deployment
from azure.ai.agentserver.agentframework import from_agent_framework

# Foundry v2 Hosted Agent invocation (for calling remote hosted agents)
from azure.ai.projects import AIProjectClient

# Environment - use override=False so Foundry runtime vars take precedence
from dotenv import load_dotenv
load_dotenv(override=False)
```

> ⚠️ **Version Warning**: The SDK is in preview with frequent breaking changes. Always pin versions exactly as specified in requirements.txt.

---

## Native MAF Patterns Reference

### Pattern 1: Simple Agent (Local)
```python
from agent_framework import Agent
from agent_framework.azure import AzureOpenAIChatClient

# Option A: Agent class with client parameter
agent = Agent(
    client=AzureOpenAIChatClient(),
    name="MyAgent",
    instructions="You are a helpful assistant.",
    tools=[my_tool_function]  # Optional
)

# Option B: Client's create_agent() method (more concise)
agent = AzureOpenAIChatClient(ad_token_provider=_token_provider).create_agent(
    instructions="You are a helpful assistant.",
    name="MyAgent"
)

result = await agent.run("Hello!")
```

### Pattern 2: Sequential Workflow (WorkflowBuilder)
```python
from agent_framework import Agent, WorkflowBuilder

# Create agents (each needs its own client instance)
writer = Agent(client=AzureOpenAIChatClient(), name="Writer", instructions="...")
reviewer = Agent(client=AzureOpenAIChatClient(), name="Reviewer", instructions="...")

# Build sequential workflow with .add_edge()
workflow = (
    WorkflowBuilder(
        name="WriterReviewer",
        start_executor=writer,         # First agent
        output_executors=[writer, reviewer]
    )
    .add_edge(writer, reviewer)         # writer → reviewer
    .build()
)

# Convert to agent for hosting
agent = workflow.as_agent()
```

### Pattern 3: Concurrent Workflow (ConcurrentBuilder)
```python
from agent_framework import ConcurrentBuilder
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

# Token provider for automatic refresh in long-running servers (avoids 401 after ~1 hour)
_credential = DefaultAzureCredential()
_token_provider = get_bearer_token_provider(_credential, "https://cognitiveservices.azure.com/.default")

def create_workflow_builder():
    # Alternative agent creation pattern: client.create_agent() 
    researcher = AzureOpenAIChatClient(ad_token_provider=_token_provider).create_agent(
        instructions="You're an expert researcher...",
        name="researcher"
    )
    analyst = AzureOpenAIChatClient(ad_token_provider=_token_provider).create_agent(
        instructions="You're a data analyst...",
        name="analyst"
    )
    
    # ConcurrentBuilder runs agents in parallel
    workflow_builder = ConcurrentBuilder().participants([researcher, analyst])
    return workflow_builder

def main():
    # Pass .build method reference (not .build()) to from_agent_framework
    from_agent_framework(create_workflow_builder().build).run()
```

> **Note**: `from_agent_framework()` accepts either a built agent OR a `.build` method reference for lazy initialization.

---

## Goals

### G-ORCH-001: Framework Setup
**Objective**: Configure Microsoft Agent Framework with proper authentication and Foundry connectivity.

**Success Criteria**:
- Framework initializes without errors
- Azure credentials authenticate successfully
- Foundry endpoint is reachable
- Both hosted agents are accessible

### G-ORCH-002: Agent Integration
**Objective**: Integrate both Foundry v2 hosted agents as workflow participants.

**Success Criteria**:
- CategorizeRiskAgent invocable via framework
- SummarizeAgent invocable via framework
- Agent references resolve correctly
- Responses parse successfully

### G-ORCH-003: Sequential Workflow
**Objective**: Implement reliable sequential execution with proper context handoff.

**Success Criteria**:
- Workflow accepts Client ID input
- CategorizeRiskAgent executes first
- Output flows to SummarizeAgent
- Final output consolidates both results

### G-ORCH-004: Production Readiness
**Objective**: Ensure the implementation is robust for production use.

**Success Criteria**:
- Error handling is comprehensive
- Logging enables debugging
- Performance is acceptable
- Code is maintainable

### G-ORCH-005: Token Economics & Observability
**Objective**: Capture token usage and reasoning from agent responses for cost visibility, debugging, and operational monitoring.

**Success Criteria**:
- Token usage (prompt/completion/total) extracted from `AgentResponse.token_usage` per agent stage
- Reasoning traces extracted from `AgentResponse.reasoning` property
- Token counts logged with correlation ID in structured format
- CLI displays token usage summary and reasoning traces (via `--verbose`)
- `AgentStageMetrics` model tracks per-stage metrics in `WorkflowResult`
- Configuration via `ENABLE_REASONING_DISPLAY` environment variable

**Observability Pipeline** (Local → Foundry → Log Analytics):
1. **Local**: Orchestrator extracts `token_usage` and `reasoning` from MAF `AgentResponse` messages
2. **CLI**: Token usage displayed as summary panel; reasoning shown in dim magenta (via `--verbose`)
3. **Structured logs**: Token counts and reasoning logged with `[WORKFLOW:{correlation_id}]` prefix
4. **(Future) APIM**: Gateway captures request/response telemetry, token counts via diagnostic settings
5. **(Future) Foundry v2**: SDK telemetry sent to project for agent-level dashboards
6. **(Future) Log Analytics**: Long-term storage via APIM/Foundry diagnostic settings for cross-project analysis

**AI Gateway (APIM) Guidance**:
- Deploy APIM in front of Foundry endpoints for token rate limiting (`azure-openai-token-limit`)
- Configure backend pools for failover when primary endpoint returns 429/5xx
- Enable diagnostic settings to route request logs and token metrics to Log Analytics workspace
- Use `Retry-After` header propagation for graceful 429 handling

---

## Microgoals

### MG-ORCH-001: Project Structure Setup
- [ ] Create project directory structure
- [ ] Initialize Python virtual environment
- [ ] Install required dependencies
- [ ] Create configuration management module

**Directory Structure**:
```
risk-assessment-workflow/
├── src/
│   ├── __init__.py
│   ├── main.py                 # Entry point
│   ├── config.py               # Configuration
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base_agent.py       # Base agent wrapper
│   │   ├── categorize_agent.py # CategorizeRiskAgent wrapper
│   │   └── summarize_agent.py  # SummarizeAgent wrapper
│   ├── workflow/
│   │   ├── __init__.py
│   │   ├── orchestrator.py     # Workflow orchestration
│   │   └── context.py          # Context management
│   └── models/
│       ├── __init__.py
│       ├── input.py            # Input models
│       └── output.py           # Output models
├── tests/
│   ├── __init__.py
│   ├── test_agents.py
│   └── test_workflow.py
├── requirements.txt
├── .env.example
└── README.md
```

### MG-ORCH-002: Configuration Module
- [ ] Define configuration class
- [ ] Load Foundry endpoint from environment
- [ ] Configure agent names and versions
- [ ] Support local development and production configs

**Configuration Contract**:
```python
@dataclass
class Config:
    foundry_endpoint: str = "https://foundry-cc-canada.services.ai.azure.com/api/projects/dev"
    
    categorize_agent_name: str = "CategorizeRiskAgent"
    categorize_agent_version: str = "1"
    
    summarize_agent_name: str = "SummarizeAgent"
    summarize_agent_version: str = "1"
    
    timeout_seconds: int = 60
    retry_count: int = 3
```

### MG-ORCH-003: Azure Client Initialization
- [ ] Create async credential using `azure.identity.aio`
- [ ] Use separate client instances for each agent (MAF requirement)
- [ ] Use token provider for long-running servers to avoid 401 errors
- [ ] Validate connectivity on startup
- [ ] Handle authentication failures gracefully

**Client Initialization Pattern**:
```python
import os
import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Load environment - override=False lets Foundry runtime vars take precedence
load_dotenv(override=False)

# Microsoft Agent Framework
from agent_framework import Agent, WorkflowBuilder
from agent_framework.azure import AzureAIClient, AzureOpenAIChatClient
from azure.ai.agentserver.agentframework import from_agent_framework

# Azure Identity - MUST use async (aio) version for MAF
from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential
from azure.identity import get_bearer_token_provider

# For remote hosted agent invocation
from azure.ai.projects import AIProjectClient

# Environment variables
PROJECT_ENDPOINT = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
MODEL_DEPLOYMENT = os.getenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "gpt-4o")

def get_credential():
    """Use ManagedIdentity in Azure, DefaultAzureCredential locally."""
    if os.getenv("MSI_ENDPOINT"):  # Running in Azure
        return ManagedIdentityCredential()
    return DefaultAzureCredential()

# For long-running servers: use token provider to auto-refresh tokens
from azure.identity import DefaultAzureCredential as SyncCredential
_credential = SyncCredential()
_token_provider = get_bearer_token_provider(
    _credential, 
    "https://cognitiveservices.azure.com/.default"
)

def create_project_client():
    """Create Foundry project client for hosted agent invocation."""
    return AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=SyncCredential()
    )
```

### MG-ORCH-004: Hosted Agent Invocation Pattern
- [ ] Create callable wrapper for remote Foundry v2 Hosted Agents
- [ ] Implement agent_reference construction for `responses.create()`
- [ ] Parse responses consistently
- [ ] Make wrapper compatible with MAF workflow

**Hosted Agent Invocation Pattern** (for calling Foundry v2 Hosted Agents):
```python
from dataclasses import dataclass
from typing import Any

@dataclass
class HostedAgentConfig:
    """Configuration for a Foundry v2 hosted agent."""
    name: str
    version: str = "1"

class HostedAgentInvoker:
    """Invokes Foundry v2 hosted agents via azure-ai-projects SDK."""
    
    def __init__(self, project_client: AIProjectClient, config: HostedAgentConfig):
        self.openai_client = project_client.get_openai_client()
        self.config = config
    
    def invoke(self, user_message: str) -> str:
        """Invoke the hosted agent and return response text."""
        response = self.openai_client.responses.create(
            input=[{"role": "user", "content": user_message}],
            extra_body={
                "agent_reference": {
                    "name": self.config.name,
                    "version": self.config.version,
                    "type": "agent_reference"
                }
            }
        )
        return response.output_text
    
    def invoke_with_context(self, messages: list[dict]) -> str:
        """Invoke with full message history for multi-turn."""
        response = self.openai_client.responses.create(
            input=messages,
            extra_body={
                "agent_reference": {
                    "name": self.config.name,
                    "version": self.config.version,
                    "type": "agent_reference"
                }
            }
        )
        return response.output_text
```

**Alternative: Native MAF Agent with Local Client** (if NOT using remote hosted agents):
```python
from agent_framework import Agent
from agent_framework.azure import AzureOpenAIChatClient

# Each agent needs its own client instance
categorize_client = AzureOpenAIChatClient(ad_token_provider=_token_provider)
summarize_client = AzureOpenAIChatClient(ad_token_provider=_token_provider)

categorize_agent = Agent(
    client=categorize_client,
    name="CategorizeRiskAgent",
    instructions="""You are a Risk Assessment Specialist...""",
    tools=[search_knowledge_base]  # Tool to query AI Search
)

summarize_agent = Agent(
    client=summarize_client,
    name="SummarizeAgent",
    instructions="""You are a Risk Communication Specialist..."""
)
```

### MG-ORCH-005: Data Models
- [ ] Define Pydantic/dataclass models for workflow state
- [ ] Define models for agent outputs
- [ ] Implement serialization for context passing

### MG-ORCH-006: Entry Point
- [ ] Create main.py with CLI interface for Option B
- [ ] Or create async main with `from_agent_framework(agent).run_async()` for Option A
- [ ] Accept Client ID as input
- [ ] Execute workflow and output results

### MG-ORCH-007: Workflow Orchestrator
- [ ] Implement sequential workflow using MAF native `WorkflowBuilder`
- [ ] Use `start_executor=...` pattern (not `.set_start_executor(...)`)
- [ ] Use `.add_edge()` for sequential handoff
- [ ] Use `output_executors=` to define which agents produce final output
- [ ] Call `.build().as_agent()` to convert workflow to hostable agent
- [ ] Log all workflow stages

---

## Option A: Native MAF Workflow (Recommended)

Use native MAF `Agent` + `WorkflowBuilder` when your agents run locally with their own model client:

```python
import asyncio
import os
from contextlib import asynccontextmanager

from agent_framework import Agent, WorkflowBuilder
from agent_framework.azure import AzureOpenAIChatClient
from azure.ai.agentserver.agentframework import from_agent_framework
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

load_dotenv(override=False)

# Token provider for automatic refresh in long-running servers
_credential = DefaultAzureCredential()
_token_provider = get_bearer_token_provider(
    _credential, 
    "https://cognitiveservices.azure.com/.default"
)

@asynccontextmanager
async def create_agents():
    """Create MAF agents with their own client instances."""
    # Each agent MUST have its own client instance
    categorize_agent = Agent(
        client=AzureOpenAIChatClient(ad_token_provider=_token_provider),
        name="CategorizeRiskAgent",
        instructions="""You are a Risk Assessment Specialist Agent.
        
        Given a Client ID, you will:
        1. Query the Azure AI Search index filtered by that Client ID
        2. Analyze retrieved documents for discrepancies
        3. Apply risk categorization rules
        4. Return a risk score: Low, Medium, or High
        
        Output your assessment in JSON format with:
        - client_id, risk_score, discrepancy_count, reasoning
        """,
        tools=[query_ai_search]  # Tool function to call AI Search
    )
    
    summarize_agent = Agent(
        client=AzureOpenAIChatClient(ad_token_provider=_token_provider),
        name="SummarizeAgent",
        instructions="""You are a Risk Communication Specialist Agent.
        
        Given a risk assessment result, you will:
        1. Transform the technical assessment into clear language
        2. Explain the risk score with evidence
        3. Provide actionable recommendations
        
        Output a professional, human-readable summary.
        """
    )
    
    yield categorize_agent, summarize_agent


def create_workflow(categorize_agent: Agent, summarize_agent: Agent):
    """Build sequential workflow: Categorize → Summarize."""
    workflow = (
        WorkflowBuilder(
            name="RiskAssessmentWorkflow",
            start_executor=categorize_agent,            # First agent
            output_executors=[categorize_agent, summarize_agent]  # Both contribute to output
        )
        .add_edge(categorize_agent, summarize_agent)    # Sequential handoff
        .build()
    )
    return workflow.as_agent()  # Convert to hostable agent


async def main():
    """Entry point for the Risk Assessment Workflow."""
    async with create_agents() as (categorize_agent, summarize_agent):
        agent = create_workflow(categorize_agent, summarize_agent)
        
        # Run as HTTP server for Foundry hosting
        await from_agent_framework(agent).run_async()


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Option B: Hybrid - MAF Orchestrating Remote Hosted Agents

Use this pattern when calling pre-deployed **Foundry v2 Hosted Agents** via `azure-ai-projects`:

```python
import asyncio
import logging
from datetime import datetime
from dataclasses import dataclass

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv(override=False)

logger = logging.getLogger(__name__)

@dataclass
class WorkflowResult:
    client_id: str
    risk_score: str
    risk_assessment_raw: str
    summary: str
    completed_at: datetime


class HostedAgentInvoker:
    """Invokes Foundry v2 hosted agents."""
    
    def __init__(self, project_client: AIProjectClient, agent_name: str, version: str = "1"):
        self.openai_client = project_client.get_openai_client()
        self.agent_name = agent_name
        self.version = version
    
    def invoke(self, user_message: str) -> str:
        response = self.openai_client.responses.create(
            input=[{"role": "user", "content": user_message}],
            extra_body={
                "agent_reference": {
                    "name": self.agent_name,
                    "version": self.version,
                    "type": "agent_reference"
                }
            }
        )
        return response.output_text


class RiskAssessmentWorkflow:
    """Orchestrates sequential workflow calling remote hosted agents."""
    
    def __init__(self, project_endpoint: str):
        credential = DefaultAzureCredential()
        self.project_client = AIProjectClient(
            endpoint=project_endpoint,
            credential=credential
        )
        
        # Initialize hosted agent invokers
        self.categorize_agent = HostedAgentInvoker(
            self.project_client, 
            agent_name="CategorizeRiskAgent",
            version="1"
        )
        self.summarize_agent = HostedAgentInvoker(
            self.project_client,
            agent_name="SummarizeAgent", 
            version="1"
        )
    
    def execute(self, client_id: str) -> WorkflowResult:
        """Execute the sequential workflow."""
        logger.info(f"Starting workflow for client: {client_id}")
        
        # Stage 1: CategorizeRiskAgent
        logger.info("Stage 1: Invoking CategorizeRiskAgent")
        categorize_prompt = f"""Evaluate the risk profile for Client ID: {client_id}.
        Query the knowledge base filtered by this Client ID,
        apply all risk assessment rules, and return your assessment."""
        
        risk_assessment = self.categorize_agent.invoke(categorize_prompt)
        logger.info(f"Risk assessment received")
        
        # Stage 2: SummarizeAgent (receives context from Stage 1)
        logger.info("Stage 2: Invoking SummarizeAgent")
        summarize_prompt = f"""Generate a professional risk assessment summary.
        
        Client ID: {client_id}
        
        Risk Assessment Results:
        {risk_assessment}
        
        Provide a clear summary explaining the risk classification,
        key findings, and recommended actions."""
        
        summary = self.summarize_agent.invoke(summarize_prompt)
        logger.info("Summary generated")
        
        # Extract risk score from assessment (parse as needed)
        risk_score = self._extract_risk_score(risk_assessment)
        
        return WorkflowResult(
            client_id=client_id,
            risk_score=risk_score,
            risk_assessment_raw=risk_assessment,
            summary=summary,
            completed_at=datetime.utcnow()
        )
    
    def _extract_risk_score(self, assessment: str) -> str:
        """Extract risk score from assessment text."""
        assessment_lower = assessment.lower()
        if "high" in assessment_lower:
            return "High"
        elif "medium" in assessment_lower:
            return "Medium"
        return "Low"


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Risk Assessment Workflow")
    parser.add_argument("client_id", help="Client ID to evaluate")
    args = parser.parse_args()
    
    workflow = RiskAssessmentWorkflow(
        project_endpoint="https://foundry-cc-canada.services.ai.azure.com/api/projects/dev"
    )
    
    result = workflow.execute(args.client_id)
    
    print(f"\n{'='*60}")
    print(f"RISK ASSESSMENT COMPLETE")
    print(f"{'='*60}")
    print(f"Client ID: {result.client_id}")
    print(f"Risk Score: {result.risk_score}")
    print(f"\n{result.summary}")


if __name__ == "__main__":
    main()
```

### MG-ORCH-008: Error Handling
- [ ] Implement retry decorator for transient failures
- [ ] Create custom exception hierarchy
- [ ] Add timeout handling
- [ ] Log errors with context

**Error Handling Contract**:
```python
class WorkflowError(Exception):
    """Base exception for workflow errors."""
    pass

class AgentInvocationError(WorkflowError):
    """Error invoking a hosted agent."""
    def __init__(self, agent_name: str, message: str):
        self.agent_name = agent_name
        super().__init__(f"Agent '{agent_name}' error: {message}")

class ContextHandoffError(WorkflowError):
    """Error during context handoff between agents."""
    pass

def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator for retry logic with exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
        return wrapper
    return decorator
```

---

## Workflow Sequence Diagram

```
┌──────────┐     ┌─────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  Caller  │     │ Orchestrator│     │ CategorizeRiskAgent │     │  SummarizeAgent  │
└────┬─────┘     └──────┬──────┘     └──────────┬──────────┘     └────────┬─────────┘
     │                  │                       │                         │
     │ execute(client_id)                       │                         │
     │─────────────────▶│                       │                         │
     │                  │                       │                         │
     │                  │ evaluate_risk(client_id)                        │
     │                  │──────────────────────▶│                         │
     │                  │                       │                         │
     │                  │                       │ [Query AI Search]       │
     │                  │                       │ [Apply Rules]           │
     │                  │                       │ [Calculate Score]       │
     │                  │                       │                         │
     │                  │  RiskAssessmentResult │                         │
     │                  │◀──────────────────────│                         │
     │                  │                       │                         │
     │                  │ summarize_assessment(result)                    │
     │                  │────────────────────────────────────────────────▶│
     │                  │                                                 │
     │                  │                                                 │ [Parse Context]
     │                  │                                                 │ [Build Narrative]
     │                  │                                                 │ [Format Output]
     │                  │                                                 │
     │                  │                              SummaryResult      │
     │                  │◀────────────────────────────────────────────────│
     │                  │                                                 │
     │   WorkflowResult │                                                 │
     │◀─────────────────│                                                 │
     │                  │                                                 │
```

---

## Dependencies

### requirements.txt
```
# Microsoft Agent Framework (PIN THESE VERSIONS - SDK is in preview with breaking changes)
agent-framework-azure-ai==1.0.0rc3
agent-framework-core==1.0.0rc3

# Agent Server for HTTP hosting
azure-ai-agentserver-agentframework==1.0.0b16
azure-ai-agentserver-core==1.0.0b16

# Azure AI Foundry Projects SDK (for hosted agent invocation)
azure-ai-projects>=2.0.0

# Azure Identity (use async version in code: azure.identity.aio)
azure-identity>=1.15.0

# Supporting packages
pydantic>=2.0.0
python-dotenv>=1.0.0
```

### Install Command
```bash
pip install agent-framework-azure-ai==1.0.0rc3 agent-framework-core==1.0.0rc3 \
    azure-ai-agentserver-agentframework==1.0.0b16 azure-ai-agentserver-core==1.0.0b16 \
    azure-ai-projects>=2.0.0 azure-identity pydantic python-dotenv
```

### .env.example
```bash
# Azure AI Foundry Configuration
# Project endpoint for hosted agent invocation
FOUNDRY_ENDPOINT=https://foundry-cc-canada.services.ai.azure.com/api/projects/dev

# Model deployment (if using AzureAIClient directly)
FOUNDRY_PROJECT_ENDPOINT=https://foundry-cc-canada.services.ai.azure.com/api/projects/dev
FOUNDRY_MODEL_DEPLOYMENT_NAME=gpt-4o

# Hosted Agent Configuration
CATEGORIZE_AGENT_NAME=CategorizeRiskAgent
CATEGORIZE_AGENT_VERSION=1
SUMMARIZE_AGENT_NAME=SummarizeAgent
SUMMARIZE_AGENT_VERSION=1

# Execution Configuration
WORKFLOW_TIMEOUT_SECONDS=60
RETRY_COUNT=3
LOG_LEVEL=INFO
```

> **Note**: Use `load_dotenv(override=False)` in code so Foundry runtime environment variables take precedence over local `.env` values during deployment.

---

## Testing Strategy

### Unit Tests
- [ ] Test agent wrapper construction
- [ ] Test message formatting
- [ ] Test response parsing
- [ ] Test error handling paths

### Integration Tests
- [ ] Test CategorizeRiskAgent invocation (requires Azure connection)
- [ ] Test SummarizeAgent invocation (requires Azure connection)
- [ ] Test full workflow execution

### Mock Tests
- [ ] Mock Azure responses for offline testing
- [ ] Test various risk score scenarios
- [ ] Test error handling with mocked failures

---

## Logging Strategy

```python
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Log workflow stages
logger.info(f"[WORKFLOW] Starting for client: {client_id}")
logger.info(f"[AGENT:CategorizeRisk] Invoking with client_id: {client_id}")
logger.debug(f"[AGENT:CategorizeRisk] Response: {response}")
logger.info(f"[AGENT:CategorizeRisk] Risk score: {risk_score}")
logger.info(f"[AGENT:Summarize] Invoking with context")
logger.info(f"[WORKFLOW] Completed successfully")
```

---

## Success Criteria Checklist

### Functionality
- [ ] Workflow accepts Client ID and produces final output
- [ ] CategorizeRiskAgent correctly queries and evaluates
- [ ] SummarizeAgent produces readable summary
- [ ] Context flows correctly between agents

### Reliability
- [ ] Handles network failures with retry
- [ ] Handles agent errors gracefully
- [ ] Provides meaningful error messages
- [ ] Completes within timeout

### Maintainability
- [ ] Code is modular and testable
- [ ] Configuration is externalized
- [ ] Logging enables debugging
- [ ] Documentation is complete

---

## Next Steps After Contract Approval

1. **Initialize Project**: Run `pip install` and create directory structure
2. **Implement Config Module**: Start with configuration management
3. **Implement Base Agent**: Create the reusable agent wrapper
4. **Implement Specific Agents**: Create wrappers for both agents
5. **Implement Orchestrator**: Build the workflow coordination
6. **Add Tests**: Write unit and integration tests
7. **Validate End-to-End**: Test with real Foundry connection
