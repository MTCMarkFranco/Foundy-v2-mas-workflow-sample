"""Create the client-risk-data index and upload sample documents."""

import json
import os
import sys

from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    SemanticConfiguration,
    SemanticSearch,
    SemanticPrioritizedFields,
    SemanticField,
    ScoringProfile,
    TextWeights,
)

SEARCH_ENDPOINT = "https://ai-search-hub-canada.search.windows.net"
INDEX_NAME = "client-risk-data"
SAMPLE_DATA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "prompt-contracts", "sample-data", "client-risk-data.json"
)

credential = DefaultAzureCredential()
index_client = SearchIndexClient(endpoint=SEARCH_ENDPOINT, credential=credential)

# --- Define the index ---
fields = [
    SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
    SearchableField(name="client_id", type=SearchFieldDataType.String, filterable=True, facetable=True),
    SearchableField(name="client_name", type=SearchFieldDataType.String, sortable=True),
    SearchableField(name="document_type", type=SearchFieldDataType.String, filterable=True, facetable=True),
    SimpleField(name="compliance_status", type=SearchFieldDataType.String, filterable=True, facetable=True),
    SimpleField(name="compliance_expiry_date", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
    SimpleField(name="last_review_date", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
    SearchField(
        name="risk_flags",
        type=SearchFieldDataType.Collection(SearchFieldDataType.String),
        filterable=True,
        facetable=True,
    ),
    SearchableField(name="document_content", type=SearchFieldDataType.String, analyzer_name="en.microsoft"),
    SearchableField(name="notes", type=SearchFieldDataType.String),
]

semantic_config = SemanticConfiguration(
    name="default-semantic",
    prioritized_fields=SemanticPrioritizedFields(
        title_field=SemanticField(field_name="document_type"),
        content_fields=[
            SemanticField(field_name="document_content"),
            SemanticField(field_name="notes"),
        ],
        keywords_fields=[
            SemanticField(field_name="risk_flags"),
            SemanticField(field_name="compliance_status"),
        ],
    ),
)

scoring_profile = ScoringProfile(
    name="risk-boost",
    text_weights=TextWeights(weights={
        "document_content": 2.0,
        "risk_flags": 3.0,
        "notes": 1.5,
    }),
)

index = SearchIndex(
    name=INDEX_NAME,
    fields=fields,
    semantic_search=SemanticSearch(
        default_configuration_name="default-semantic",
        configurations=[semantic_config],
    ),
    scoring_profiles=[scoring_profile],
)

print(f"Creating index '{INDEX_NAME}'...")
index_client.create_or_update_index(index)
print("  Index created/updated.")

# --- Upload sample data ---
with open(SAMPLE_DATA_PATH) as f:
    data = json.load(f)

documents = data["value"]
print(f"Uploading {len(documents)} documents...")

search_client = SearchClient(endpoint=SEARCH_ENDPOINT, index_name=INDEX_NAME, credential=credential)
result = search_client.upload_documents(documents)

succeeded = sum(1 for r in result if r.succeeded)
print(f"  Uploaded: {succeeded}/{len(documents)} succeeded.")

# Verify
print("\nVerifying with a search for CLT-10001...")
results = search_client.search(
    search_text="CLT-10001",
    filter="client_id eq 'CLT-10001'",
    top=5,
)
for r in results:
    print(f"  {r['id']} - {r['document_type']} - {r['compliance_status']}")

print("\nDone!")
