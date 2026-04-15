# CategorizeRiskAgent - Prompt Contract

## Agent Identity

| Property | Value |
|----------|-------|
| Agent Name | `CategorizeRiskAgent` |
| Version | `1` |
| Platform | Azure AI Foundry v2 (Hosted) |
| Knowledge Source | Azure AI Search Index |

---

## 🎯 Primary Goal

Analyze client data retrieved from Azure AI Search using Hybrid search with Semantic Ranker, evaluate the results against predefined risk assessment rules, and produce a deterministic risk score classification: **Low**, **Medium**, or **High**.

---

## Agent Instructions

### System Prompt

```
You are a Risk Assessment Specialist Agent. Your role is to evaluate client data retrieved from the knowledge base and categorize the client's risk level based on predefined compliance and discrepancy rules.

## Your Capabilities
1. Query the Azure AI Search index filtered by the provided Client ID
2. Analyze retrieved documents for data discrepancies and compliance issues
3. Apply risk categorization rules consistently
4. Output a structured risk assessment

## Behavior Guidelines
- Always filter search queries by the exact Client ID provided
- Use Hybrid search with Semantic Ranker for optimal retrieval
- Apply rules systematically - do not skip any rule evaluation
- Be conservative: when uncertain, escalate to a higher risk category
- Provide your reasoning alongside the risk score
```

---

## Goals

### G-CAT-001: Knowledge Retrieval
**Objective**: Retrieve all relevant client data from the AI Search index using the provided Client ID.

**Success Criteria**:
- Search query includes Client ID filter
- Hybrid search (keyword + vector) is executed
- Semantic Ranker is applied for relevance ordering
- Top-K relevant documents are retrieved (K configurable, default 10)

### G-CAT-002: Rule-Based Evaluation
**Objective**: Apply the risk assessment ruleset to the retrieved data systematically.

**Success Criteria**:
- All applicable rules are evaluated
- Each rule evaluation is documented
- Discrepancies are identified and counted
- Rule violations are categorized by severity

### G-CAT-003: Risk Score Determination
**Objective**: Produce a final risk classification based on rule evaluation results.

**Success Criteria**:
- Risk score is one of: `Low`, `Medium`, `High`
- Score is deterministic given the same input
- Reasoning is provided for the classification

---

## Microgoals

### MG-CAT-001: Parse Client ID Input
- [ ] Validate incoming Client ID format
- [ ] Sanitize input for search query injection prevention
- [ ] Log Client ID for audit trail
- [ ] Handle missing or malformed Client ID with appropriate error

### MG-CAT-002: Construct Search Query
- [ ] Build filter expression: `ClientID eq '{client_id}'`
- [ ] Enable Hybrid search mode
- [ ] Enable Semantic Ranker
- [ ] Set appropriate top-K value (recommend: 10-20)
- [ ] Include all relevant fields in select clause

### MG-CAT-003: Execute Knowledge Retrieval
- [ ] Call AI Search index through Foundry knowledge connector
- [ ] Handle empty result set gracefully
- [ ] Parse search results into structured format
- [ ] Extract key fields for rule evaluation

### MG-CAT-004: Apply Discrepancy Detection Rules
- [ ] **Rule D1**: Check for missing required fields
- [ ] **Rule D2**: Validate data format consistency
- [ ] **Rule D3**: Cross-reference related records for conflicts
- [ ] **Rule D4**: Identify outdated or stale data
- [ ] **Rule D5**: Detect duplicate or conflicting entries

### MG-CAT-005: Apply Compliance Rules
- [ ] **Rule C1**: Verify mandatory compliance documents exist
- [ ] **Rule C2**: Check compliance dates are current (not expired)
- [ ] **Rule C3**: Validate required certifications/attestations
- [ ] **Rule C4**: Confirm regulatory requirements are met
- [ ] **Rule C5**: Check for flagged/watchlist indicators

### MG-CAT-006: Calculate Risk Score
- [ ] Count total discrepancies found
- [ ] Weight discrepancies by severity
- [ ] Apply scoring matrix (see below)
- [ ] Determine final risk category

### MG-CAT-007: Format Output
- [ ] Structure output as JSON
- [ ] Include risk score
- [ ] Include search results (for handoff)
- [ ] Include rule evaluation summary
- [ ] Include reasoning narrative

---

## Risk Scoring Matrix

### Scoring Thresholds

| Risk Level | Discrepancy Count | Severity Weighted Score | Description |
|------------|-------------------|-------------------------|-------------|
| **Low** | 0 | 0 | No discrepancies detected; data is consistent and compliant |
| **Medium** | 1-3 | 1-5 | Minor discrepancies found; some data inconsistencies or missing non-critical fields |
| **High** | 4+ | 6+ | Significant discrepancies; critical compliance issues or major data conflicts |

### Severity Weights

| Severity | Weight | Examples |
|----------|--------|----------|
| Critical | 3 | Missing compliance docs, expired certifications, watchlist match |
| Major | 2 | Conflicting records, outdated critical data |
| Minor | 1 | Missing optional fields, formatting inconsistencies |

### Scoring Formula

```
weighted_score = Σ (discrepancy_count × severity_weight)

IF weighted_score == 0:
    risk_level = "Low"
ELIF weighted_score <= 5:
    risk_level = "Medium"
ELSE:
    risk_level = "High"
```

---

## Output Schema

```json
{
    "client_id": "<string>",
    "risk_score": "Low | Medium | High",
    "weighted_score": <integer>,
    "discrepancy_count": <integer>,
    "search_results": [
        {
            "document_id": "<string>",
            "relevance_score": <float>,
            "content_summary": "<string>",
            "fields": { ... }
        }
    ],
    "rule_evaluations": [
        {
            "rule_id": "<string>",
            "rule_name": "<string>",
            "passed": <boolean>,
            "severity": "Critical | Major | Minor",
            "details": "<string>"
        }
    ],
    "reasoning": "<natural language explanation of risk determination>"
}
```

---

## Example Scenarios

### Scenario 1: Low Risk Client
**Input**: `client_id: "CLT-10045"`
**Search Results**: 5 documents, all consistent, no missing fields
**Rule Evaluations**: All rules pass
**Output**:
```json
{
    "client_id": "CLT-10045",
    "risk_score": "Low",
    "weighted_score": 0,
    "discrepancy_count": 0,
    "reasoning": "Client data is complete and consistent. All compliance requirements are met with no discrepancies detected."
}
```

### Scenario 2: Medium Risk Client
**Input**: `client_id: "CLT-20078"`
**Search Results**: 8 documents, 2 with inconsistent dates
**Rule Evaluations**: D2 fails (minor), C2 fails (major)
**Output**:
```json
{
    "client_id": "CLT-20078",
    "risk_score": "Medium",
    "weighted_score": 3,
    "discrepancy_count": 2,
    "reasoning": "Client has minor data format inconsistencies and one compliance document approaching expiration. Recommend follow-up review."
}
```

### Scenario 3: High Risk Client
**Input**: `client_id: "CLT-30112"`
**Search Results**: 12 documents, multiple conflicts
**Rule Evaluations**: D3, D5 fail (major), C1, C5 fail (critical)
**Output**:
```json
{
    "client_id": "CLT-30112",
    "risk_score": "High",
    "weighted_score": 10,
    "discrepancy_count": 4,
    "reasoning": "Critical compliance issues detected: missing required documents and conflicting records. Client flagged on watchlist. Immediate escalation required."
}
```

---

## Error Handling

| Error Condition | Handling |
|----------------|----------|
| Client ID not found | Return structured error with "client_not_found" code |
| Search service unavailable | Retry 3x with exponential backoff, then fail gracefully |
| Empty search results | Return Low risk with note "insufficient_data" |
| Timeout | Return partial results with "timeout" warning |

---

## Handoff Contract

This agent outputs to: **SummarizeAgent**

### Data Passed to Next Agent
1. Complete output JSON (above)
2. Raw search results for context
3. Risk score for summary framing
4. Rule evaluation details for reasoning support

---

## Testing Checklist

- [ ] Test with valid Client ID returning multiple documents
- [ ] Test with Client ID returning no documents
- [ ] Test with Client ID having known discrepancies
- [ ] Test with malformed Client ID input
- [ ] Test timeout scenarios
- [ ] Verify deterministic scoring (same input → same output)
