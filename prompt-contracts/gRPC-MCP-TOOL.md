# MCP + gRPC + MAF Orchestrator Prompt Contract  
### For Azure AI Foundry Hosted Agents (Outbound‑Only Architecture)

## Purpose
This contract defines how the AI system integrates gRPC-based MCP servers into an Azure AI Foundry solution using the Microsoft Agent Framework (MAF) as the orchestrator. Hosted Agents remain outbound-only and never speak MCP or gRPC directly. MAF is the single integration layer that exposes MCP-backed tools to Foundry as simple HTTP/JSON tools.

## 1. Architectural Principles

Hosted Agents:
- Outbound-only networking
- No inbound TCP/HTTP/2/WebSockets/gRPC
- Cannot host MCP servers
- Cannot speak MCP or gRPC
- Can only call HTTP(S) tools defined in Foundry

Microsoft Agent Framework (MAF):
- Acts as the sole orchestrator
- Implements tools in code
- Opens gRPC channels to MCP servers
- Manages MCP session lifecycle
- Translates Foundry JSON → MCP/gRPC → JSON
- Exposes HTTP endpoints to Foundry

MCP Server (gRPC):
- Runs as a standalone service (App Service, Container Apps, AKS, VM)
- Exposes a gRPC endpoint (public or private)
- Implements MCP protocol: session negotiation, resource listing, tool invocation, notifications, streaming

## 2. Integration Pattern

Foundry Hosted Agent  
→ (JSON tool call)  
→ MAF Orchestrator (HTTP endpoint)  
→ (gRPC + MCP protocol)  
→ MCP Server (gRPC)

Foundry decides when to call a tool.  
MAF decides how to execute it.  
The MCP server performs the actual work.

## 3. Tool Exposure Model

Rule:
All MCP-backed tools must be implemented in MAF and exposed to Foundry as HTTP/JSON tools. Hosted Agents never see MCP or gRPC.

Example Foundry Tool Definition:
{
  "name": "mcp_get_customer_profile",
  "description": "Retrieve a customer profile using the MCP backend.",
  "parameters": {
    "type": "object",
    "properties": {
      "customerId": {
        "type": "string",
        "description": "The unique customer identifier."
      }
    },
    "required": ["customerId"]
  }
}

Example MAF Tool Implementation (Conceptual):
[Tool("mcp_get_customer_profile")]
public async Task<CustomerProfile> GetCustomerProfileAsync(GetCustomerProfileRequest request)
{
    // 1. Open or reuse gRPC channel to MCP server
    // 2. Start or attach to an MCP session
    // 3. Invoke MCP tool/resource over gRPC
    // 4. Map MCP response → CustomerProfile DTO
    // 5. Return JSON-serializable result to Foundry
}

## 4. MCP Server Requirements (gRPC)

The MCP server must:
- Expose a gRPC endpoint (https://mcp.yourdomain.com:443)
- Support session start, capability negotiation, resource listing, tool invocation, streaming
- Be reachable by MAF via public endpoint or private endpoint
- Allow MAF to handle TLS, HTTP/2, channel pooling, retries, and protocol semantics

## 5. Networking Requirements

Public Access:
MAF → outbound HTTPS → MCP server (public gRPC endpoint)

Private Access (VNet Isolation):
MAF → VNet → Private Endpoint → MCP server

Hosted Agents never require inbound access.

## 6. Orchestrator Behavior Rules

1. Hosted Agents never call MCP or gRPC directly.
2. MAF is the only MCP client.
3. Tools exposed to Foundry must be coarse-grained, JSON-based, deterministic.
4. MAF handles retries, backoff, error shaping, streaming, and session state.

## 7. Invariants

- Hosted Agents = outbound-only, stateless, MCP-agnostic
- MAF = orchestrator + MCP client + gRPC client
- MCP server = standalone, addressable, long-lived
- All MCP usage is encapsulated behind MAF tools
- Foundry sees only HTTP/JSON tools

## 8. Deliverables

1. MAF Tool Layer:
   - Tool definitions in code
   - gRPC channel setup
   - MCP session lifecycle
   - Mapping logic

2. MCP Server (gRPC):
   - gRPC service hosting MCP protocol
   - Tool/resource implementations
   - Public or private endpoint

3. Foundry Tool Config:
   - Tool schema
   - Endpoint pointing to MAF
   - Connection object for auth

## 9. Contract Summary

This system uses:
- Foundry Hosted Agents for reasoning
- MAF for orchestration and protocol translation
- gRPC MCP servers for backend capability

All MCP interactions flow through MAF. Hosted Agents remain clean, safe, outbound-only clients. This contract governs how the system behaves, how tools are exposed, and how MCP is integrated.
