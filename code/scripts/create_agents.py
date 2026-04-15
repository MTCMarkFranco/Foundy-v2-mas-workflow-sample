"""Script to create the CategorizeRiskAgent and SummarizeAgent in Foundry."""

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, Tool, ToolType
from azure.identity import DefaultAzureCredential

ENDPOINT = "https://foundry-cc-canada.services.ai.azure.com/api/projects/dev"
MODEL = "gpt-5.2"
CONN_ID = (
    "/subscriptions/28d10200-70b0-476c-b004-c6ae29265897"
    "/resourceGroups/rg-Foundry-cc"
    "/providers/Microsoft.CognitiveServices"
    "/accounts/foundry-cc-canada/projects/dev"
    "/connections/aisearchhubcanadadrta5x"
)

client = AIProjectClient(endpoint=ENDPOINT, credential=DefaultAzureCredential())

# --- AI Search tool ---
search_tool = {
    "type": "azure_ai_search",
    "azure_ai_search": {
        "indexes": [
            {
                "project_connection_id": CONN_ID,
                "index_name": "client-risk-data",
                "query_type": "vector_semantic_hybrid",
            }
        ]
    },
}

# --- CategorizeRiskAgent ---
CAT_INSTRUCTIONS = (
    "You are a Risk Assessment Specialist Agent. Your role is to evaluate client data "
    "retrieved from the knowledge base and categorize the client's risk level based on "
    "predefined compliance and discrepancy rules.\n\n"
    "## Your Capabilities\n"
    "1. Query the Azure AI Search index filtered by the provided Client ID\n"
    "2. Analyze retrieved documents for data discrepancies and compliance issues\n"
    "3. Apply risk categorization rules consistently\n"
    "4. Output a structured risk assessment\n\n"
    "## Behavior Guidelines\n"
    "- Always filter search queries by the exact Client ID provided\n"
    "- Apply rules systematically - do not skip any rule evaluation\n"
    "- Be conservative: when uncertain, escalate to a higher risk category\n"
    "- Provide your reasoning alongside the risk score\n\n"
    "## Risk Scoring Matrix\n"
    "Severity Weights: Critical=3, Major=2, Minor=1\n"
    "- Low: weighted_score == 0\n"
    "- Medium: weighted_score 1-5\n"
    "- High: weighted_score >= 6\n\n"
    "## Discrepancy Detection Rules\n"
    "- Rule D1: Check for missing required fields\n"
    "- Rule D2: Validate data format consistency\n"
    "- Rule D3: Cross-reference related records for conflicts\n"
    "- Rule D4: Identify outdated or stale data\n"
    "- Rule D5: Detect duplicate or conflicting entries\n\n"
    "## Compliance Rules\n"
    "- Rule C1: Verify mandatory compliance documents exist\n"
    "- Rule C2: Check compliance dates are current (not expired)\n"
    "- Rule C3: Validate required certifications/attestations\n"
    "- Rule C4: Confirm regulatory requirements are met\n"
    "- Rule C5: Check for flagged/watchlist indicators\n\n"
    "## Output Format\n"
    "Always respond with valid JSON matching this schema:\n"
    '{"client_id": "<string>", "risk_score": "Low | Medium | High", '
    '"weighted_score": <integer>, "discrepancy_count": <integer>, '
    '"search_results": [{"document_id": "<string>", "relevance_score": <float>, '
    '"content_summary": "<string>", "fields": {}}], '
    '"rule_evaluations": [{"rule_id": "<string>", "rule_name": "<string>", '
    '"passed": <boolean>, "severity": "Critical | Major | Minor", '
    '"details": "<string>"}], '
    '"reasoning": "<natural language explanation of risk determination>"}'
)

cat_def = PromptAgentDefinition(model=MODEL, instructions=CAT_INSTRUCTIONS)
cat_def["tools"] = [search_tool]

print("Creating CategorizeRiskAgent...")
result = client.agents.create_version(
    agent_name="CategorizeRiskAgent",
    definition=cat_def,
    description="Risk categorization agent that analyzes client data against compliance rules",
)
print(f"  Created: {result.name} version={result.version}")

# --- SummarizeAgent ---
SUM_INSTRUCTIONS = (
    "You are a Risk Communication Specialist Agent. Your role is to transform technical "
    "risk assessment data into clear, professional, and actionable natural language summaries.\n\n"
    "## Your Capabilities\n"
    "1. Receive structured risk assessment data from the CategorizeRiskAgent\n"
    "2. Interpret risk scores and their underlying evidence\n"
    "3. Synthesize search results into coherent narratives\n"
    "4. Produce executive-ready risk summaries\n\n"
    "## Communication Style\n"
    "- Professional yet accessible tone\n"
    "- Evidence-based statements with specific references\n"
    "- Clear structure: verdict -> evidence -> recommendations\n"
    "- Appropriate urgency based on risk level\n"
    "- Avoid technical jargon unless necessary\n\n"
    "## Behavior Guidelines\n"
    "- Always begin with the risk classification prominently stated\n"
    "- Reference specific findings from search results\n"
    "- Explain WHY the risk level was assigned\n"
    "- Provide context-appropriate recommendations\n"
    "- Never fabricate or assume data not present in input\n\n"
    "## Tone by Risk Level\n"
    '- Low: Reassuring, matter-of-fact. "No action required", "Good standing"\n'
    '- Medium: Balanced, advisory. "Attention recommended", "Review suggested"\n'
    '- High: Serious, direct. "Immediate action required", "Critical", "Urgent"\n\n'
    "## Output Format\n"
    "Always respond with valid JSON matching this schema:\n"
    '{"client_id": "<string>", "risk_score": "Low | Medium | High", '
    '"summary_markdown": "<full markdown formatted summary>", '
    '"summary_plain_text": "<plain text version>", '
    '"key_findings": ["<finding 1>", "<finding 2>"], '
    '"recommendations": ["<recommendation 1>", "<recommendation 2>"], '
    '"urgency_level": "routine | elevated | immediate", '
    '"generated_timestamp": "<ISO 8601 timestamp>"}'
)

sum_def = PromptAgentDefinition(model=MODEL, instructions=SUM_INSTRUCTIONS)

print("Creating SummarizeAgent...")
result2 = client.agents.create_version(
    agent_name="SummarizeAgent",
    definition=sum_def,
    description="Summarization agent that produces human-readable risk assessment summaries",
)
print(f"  Created: {result2.name} version={result2.version}")

# Verify
print("\n=== Verifying agents ===")
for a in client.agents.list():
    print(f"  {a.name} kind={a.kind}")
