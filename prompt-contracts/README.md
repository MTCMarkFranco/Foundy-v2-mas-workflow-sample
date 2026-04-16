# Risk Assessment Multi-Agent Workflow - Prompt Contracts

This folder contains the prompt contracts that define the architecture, goals, and microgoals for building a Foundry v2 multi-agent workflow using Microsoft Agent Framework.

## Overview

The workflow processes a **Client ID** through a sequential two-agent pipeline:

1. **CategorizeRiskAgent** - Analyzes client data against risk rules
2. **SummarizeAgent** - Produces human-readable risk summary

## Contract Files

| File | Description |
|------|-------------|
| [WORKFLOW-ARCHITECTURE.md](./WORKFLOW-ARCHITECTURE.md) | Overall system architecture and data flow |
| [CATEGORIZE-RISK-AGENT.md](./CATEGORIZE-RISK-AGENT.md) | Risk categorization agent instructions |
| [SUMMARIZE-AGENT.md](./SUMMARIZE-AGENT.md) | Summary generation agent instructions |
| [ORCHESTRATION.md](./ORCHESTRATION.md) | Microsoft Agent Framework orchestration contract |
| [ACTOR-PATTERN-COMPLIANCE.md](./ACTOR-PATTERN-COMPLIANCE.md) | Actor Pattern cross-cutting concerns & enforcement rules |

## Sample Data

| File | Description |
|------|-------------|
| [sample-data/index-schema.json](./sample-data/index-schema.json) | AI Search index schema for `client-risk-data` |
| [sample-data/client-risk-data.json](./sample-data/client-risk-data.json) | Sample documents for 5 test clients |

### Test Clients

| Client ID | Client Name | Expected Risk |
|-----------|-------------|---------------|
| CLT-10001 | Acme Financial Services | Low |
| CLT-20002 | GlobalTech Industries | Medium |
| CLT-30003 | Northern Trust Holdings | High |
| CLT-40004 | Maple Leaf Ventures | Low |
| CLT-50005 | Pacific Rim Trading Co | High |

## Technology Stack

- **Orchestrator**: Microsoft Agent Framework (local)
- **Hosted Agents**: Azure AI Foundry v2
- **SDK**: `azure-ai-projects>=2.0.0`
- **Authentication**: Azure CLI credentials (`DefaultAzureCredential`)
- **Knowledge Source**: Azure AI Search (Hybrid + Semantic Ranker)

## Endpoint Configuration

```
Foundry Endpoint: https://foundry-cc-canada.services.ai.azure.com/api/projects/dev
```
