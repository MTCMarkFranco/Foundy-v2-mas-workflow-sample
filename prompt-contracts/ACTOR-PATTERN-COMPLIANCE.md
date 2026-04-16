# Actor Pattern Compliance — Prompt Contract

## Document Purpose

This contract defines the cross-cutting execution-safety concerns that any production deployment of this workflow MUST enforce. It is based on the [Actor Pattern principles](../external_sources/actor-pattern.md) and serves as the architectural guardrail between AI reasoning (handled by agents) and execution safety (handled by infrastructure code).

> **Key Insight**: Agent frameworks handle *reasoning*. They do NOT handle *execution safety*. This contract fills that gap.

---

## 🎯 Primary Goal

Ensure that the Risk Assessment Multi-Agent Workflow is protected against cascading failures, unbounded waits, uncontrolled concurrency, and silent degradation when running under production conditions — including multi-user load, transient backend failures, and LLM rate limiting.

---

## Technology Stack (Resilience Layer)

| Component | Module | Purpose |
|-----------|--------|---------|
| Circuit Breaker | `src/resilience.py` → `CircuitBreaker` | Prevents retry storms when backend is failing |
| Async Retry | `src/resilience.py` → `async_retry_with_backoff()` | Exponential backoff on transient errors only |
| Concurrency Limiter | `src/resilience.py` → `ConcurrencyLimiter` | Semaphore-based with fast-fail acquisition |
| Timeout Enforcement | `src/workflow/orchestrator.py` | `asyncio.wait_for()` bounding every pipeline call |
| Typed Exceptions | `src/errors.py` | `WorkflowTimeoutError`, `CircuitOpenError` |
| Configuration | `src/config.py` → `Config` dataclass | All limits configurable via environment variables |

---

## Service Limits & Defaults

All resilience settings are configurable through environment variables. The `Config` dataclass in `src/config.py` loads these at startup with `load_dotenv(override=False)`, ensuring Foundry runtime variables take precedence.

### Timeout & Retry

| Setting | Env Var | Code Default | Description |
|---------|---------|-------------|-------------|
| **Workflow Timeout** | `WORKFLOW_TIMEOUT_SECONDS` | `30` | Maximum wall-clock time for the entire workflow execution, **including all retry attempts**. Enforced via `asyncio.wait_for()`. |
| **Retry Count** | `RETRY_COUNT` | `3` | Maximum number of attempts before giving up. Only transient failures are retried. |
| **Retry Base Delay** | `RETRY_BASE_DELAY` | `1.0` | Initial backoff in seconds. Doubles each attempt (1s → 2s → 4s). Capped by remaining deadline. |

### Circuit Breaker

| Setting | Env Var | Code Default | Description |
|---------|---------|-------------|-------------|
| **Failure Threshold** | `CIRCUIT_BREAKER_THRESHOLD` | `3` | Consecutive transient failures before the breaker opens. |
| **Recovery Period** | `CIRCUIT_BREAKER_RECOVERY_SECONDS` | `30.0` | Seconds the breaker stays OPEN before transitioning to HALF-OPEN and allowing one probe request. |

### Concurrency

| Setting | Env Var | Code Default | Description |
|---------|---------|-------------|-------------|
| **Max Concurrent Requests** | `MAX_CONCURRENT_REQUESTS` | `5` | Semaphore slot count. Excess requests rejected after a 5-second acquire timeout. |

### Configuration Example (`.env`)

```bash
# ── Execution ──────────────────────────────────────
WORKFLOW_TIMEOUT_SECONDS=30        # Total deadline (seconds)
RETRY_COUNT=3                      # Max retry attempts
RETRY_BASE_DELAY=1.0               # Backoff seed (seconds)

# ── Circuit Breaker ────────────────────────────────
CIRCUIT_BREAKER_THRESHOLD=3        # Failures before OPEN
CIRCUIT_BREAKER_RECOVERY_SECONDS=30.0  # OPEN → HALF-OPEN delay

# ── Concurrency ────────────────────────────────────
MAX_CONCURRENT_REQUESTS=5          # Parallel execution slots
```

---

## Goals

### G-ACTOR-001: Timeout Enforcement (Fast Failures)

**Objective**: No workflow execution may run longer than the configured deadline, including retries.

**Rationale**: The actor-pattern document's "5-Minute Timeout Trap" shows that users abandon requests long before unbounded calls complete. Every second spent waiting on a doomed request is wasted capacity.

**Success Criteria**:
- `asyncio.wait_for()` wraps every `workflow.run()` call
- Total time across all retry attempts is bounded by `Config.timeout_seconds`
- `WorkflowTimeoutError` is raised with `client_id` and `timeout_seconds` for actionable UX
- Retry backoff delays are capped by remaining deadline budget — retries MUST NOT extend past the timeout

**Implementation Reference**: `src/workflow/orchestrator.py` → `RiskAssessmentWorkflow.execute()` inner `_run_pipeline()` function.

---

### G-ACTOR-002: Circuit Breaker (Cascading Failure Protection)

**Objective**: When the LLM backend is failing, stop sending requests to allow recovery.

**Rationale**: Without a circuit breaker, transient backend failures trigger retry storms that amplify load, deepen outages, and exhaust token budgets. The actor pattern prescribes a state machine that **fast-fails** when the backend is unhealthy.

**Success Criteria**:
- `CircuitBreaker` tracks **only transient failures** (connection, timeout, OS-level) — NOT parse/validation errors
- State machine transitions: CLOSED → OPEN (at threshold) → HALF-OPEN (after recovery) → CLOSED (on success)
- HALF-OPEN allows exactly one probe request; success closes the breaker, failure re-opens it
- `CircuitOpenError` is raised immediately when the breaker is OPEN, with `recovery_remaining` for UX
- State transitions are logged at WARNING level with `[CIRCUIT-BREAKER]` prefix
- The breaker is **shared across invocations** of the same `RiskAssessmentWorkflow` instance

**State Machine**:

```
                    threshold failures
       ┌─────────┐ ──────────────────► ┌──────────┐
       │ CLOSED  │                     │   OPEN   │
       │ (allow) │ ◄─────────── probe  │ (reject) │
       └─────────┘   succeeds          └────┬─────┘
            ▲                                │
            │         recovery_seconds       │
            │         elapsed                ▼
            │                          ┌───────────┐
            └───── probe succeeds ──── │ HALF-OPEN │
                                       │ (1 probe) │
              probe fails ────────────►└───────────┘
              (re-opens)
```

**Implementation Reference**: `src/resilience.py` → `CircuitBreaker` class.

---

### G-ACTOR-003: Classified Retry (Supervision)

**Objective**: Retry only transient infrastructure failures. Never retry logic, validation, or contract errors.

**Rationale**: The actor pattern emphasizes that supervision strategies must distinguish between recoverable and irrecoverable failures. Retrying a parse error wastes time and tokens. Retrying a connection blip is the correct response.

**Retryable (Transient) Errors**:

| Exception | Source | Example |
|-----------|--------|---------|
| `ConnectionError` | Network / SDK | Backend unreachable |
| `TimeoutError` | Python stdlib | Individual call timeout |
| `asyncio.TimeoutError` | asyncio | `wait_for()` deadline |
| `OSError` | OS / socket | DNS failure, socket reset |

**Non-Retryable (Permanent) Errors**:

| Exception | Source | Why Not Retry |
|-----------|--------|---------------|
| `AgentInvocationError` | Orchestrator | Agent returned invalid JSON or mismatched client_id |
| `InvalidClientIdError` | Input validation | Bad input will never become good |
| `ValueError` | Pydantic | Schema validation failure |
| `WorkflowError` (generic) | Orchestrator | Logic / handoff failure |

**Success Criteria**:
- `async_retry_with_backoff()` catches only `TRANSIENT_EXCEPTIONS` tuple
- Non-transient errors propagate immediately on first occurrence
- Backoff is exponential: `base_delay × 2^attempt` (1s → 2s → 4s)
- Each attempt checks circuit breaker **before** executing
- Each attempt checks remaining deadline **before** sleeping

**Implementation Reference**: `src/resilience.py` → `async_retry_with_backoff()` function.

---

### G-ACTOR-004: Isolation (State Leakage Prevention)

**Objective**: No mutable state may leak between concurrent workflow executions.

**Rationale**: The actor pattern's first principle is isolation. Shared mutable state between concurrent requests leads to race conditions, data corruption, and non-deterministic behavior.

**Success Criteria**:
- A **fresh `SequentialBuilder`** is constructed per `execute()` call — conversation history MUST NOT carry over
- `chain_only_agent_responses=True` ensures only agent responses pass between stages (not the original user prompt)
- The orchestrator's static methods (`_parse_assessment`, `_parse_summary`, `_strip_code_fence`) have **no side effects**
- Each `execute()` call generates a unique `correlation_id` for tracing

**Implementation Reference**: `src/workflow/orchestrator.py` lines 100-108 (fresh builder) and `uuid.uuid4().hex[:8]` for correlation ID.

---

### G-ACTOR-005: Concurrency Safety

**Objective**: When served concurrently (e.g., behind a web API), limit parallel executions and fail fast when capacity is exceeded.

**Rationale**: Without concurrency control, a burst of requests can exhaust thread pools, token budgets, and backend capacity simultaneously. The actor pattern prescribes bounded concurrency with fast rejection.

**Success Criteria**:
- `ConcurrencyLimiter` uses `asyncio.Semaphore` with a finite slot count (default: 5)
- Acquire timeout is 5 seconds — requests that can't get a slot within 5s are rejected, not queued forever
- Semaphore is always released in a `finally` block (or equivalent)
- For CLI usage: the limiter is available but not required (single-user)

**Implementation Reference**: `src/resilience.py` → `ConcurrencyLimiter` class.

---

### G-ACTOR-006: Observability (Structured Logging)

**Objective**: Every workflow execution MUST produce structured, traceable log output for production diagnostics.

**Rationale**: The actor pattern document states "you can't fix what you can't see." Correlation IDs, durations, and state transitions are the minimum observability surface for debugging production issues.

**Log Format Convention**:

```
[COMPONENT:CORRELATION_ID] message key=value
```

**Required Log Events**:

| Event | Level | Prefix | Fields |
|-------|-------|--------|--------|
| Workflow start | INFO | `[WORKFLOW:{id}]` | client_id, timeout, breaker_state |
| Pipeline running | INFO | `[WORKFLOW:{id}]` | — |
| Agent stage complete | INFO | `[WORKFLOW:{id}]` | risk_score, weighted_score, urgency_level |
| Workflow complete | INFO | `[WORKFLOW:{id}]` | client_id, risk_score, duration_seconds |
| Workflow timeout | ERROR | `[WORKFLOW:{id}]` | client_id, duration_seconds |
| Retry attempt | WARNING | `[RETRY]` | attempt, max_retries, error, delay |
| Breaker state change | WARNING | `[CIRCUIT-BREAKER]` | prev_state → new_state, failure_count |
| Breaker rejection | WARNING | `[CIRCUIT-BREAKER]` | recovery_remaining |
| Concurrency rejection | WARNING | `[CONCURRENCY]` | slots_busy, wait_timeout |

**Success Criteria**:
- All log messages include correlation ID where available
- Duration is logged in seconds with 2 decimal places
- Raw prompts and full agent responses are NEVER logged (PII risk)
- Circuit breaker state transitions are always logged

**Implementation Reference**: `src/workflow/orchestrator.py` (correlation IDs), `src/resilience.py` (breaker + retry logging).

---

## Microgoals

### MG-ACTOR-001: Timeout Configuration

**Checklist**:
- [ ] `Config.timeout_seconds` loaded from `WORKFLOW_TIMEOUT_SECONDS` env var
- [ ] Default is `30` seconds (code default; `.env` may override)
- [ ] Value used as both `asyncio.wait_for()` timeout AND retry deadline budget
- [ ] `WorkflowTimeoutError` raised with `timeout_seconds` and `client_id` attributes

### MG-ACTOR-002: Circuit Breaker Configuration

**Checklist**:
- [ ] `Config.circuit_breaker_threshold` loaded from `CIRCUIT_BREAKER_THRESHOLD` (default: `3`)
- [ ] `Config.circuit_breaker_recovery_seconds` loaded from `CIRCUIT_BREAKER_RECOVERY_SECONDS` (default: `30.0`)
- [ ] `CircuitBreaker` instantiated in `RiskAssessmentWorkflow.__init__()` using config values
- [ ] `CircuitBreaker` can be injected via constructor for testing
- [ ] `CircuitOpenError` raised with `recovery_remaining` attribute

### MG-ACTOR-003: Retry Configuration

**Checklist**:
- [ ] `Config.retry_count` loaded from `RETRY_COUNT` (default: `3`)
- [ ] `Config.retry_base_delay` loaded from `RETRY_BASE_DELAY` (default: `1.0`)
- [ ] `async_retry_with_backoff()` called with `deadline=config.timeout_seconds`
- [ ] Only `TRANSIENT_EXCEPTIONS` tuple is caught for retry
- [ ] Backoff sleep is capped by remaining deadline

### MG-ACTOR-004: Concurrency Configuration

**Checklist**:
- [ ] `Config.max_concurrent_requests` loaded from `MAX_CONCURRENT_REQUESTS` (default: `5`)
- [ ] `ConcurrencyLimiter` available for service-mode usage
- [ ] Acquire timeout is finite (default: 5s) — not unbounded

### MG-ACTOR-005: Structured Logging

**Checklist**:
- [ ] Unique correlation ID generated per `execute()` call (`uuid.uuid4().hex[:8]`)
- [ ] All `[WORKFLOW:*]` log messages include correlation ID
- [ ] Duration logged at workflow completion (`time.monotonic()` delta)
- [ ] Circuit breaker state transitions logged at WARNING
- [ ] No PII (raw prompts, full responses) in log output

### MG-ACTOR-006: Exception Hierarchy

**Checklist**:
- [ ] `WorkflowTimeoutError(WorkflowError)` — timeout with `timeout_seconds`, `client_id`
- [ ] `CircuitOpenError(WorkflowError)` — breaker rejection with `recovery_remaining`
- [ ] `AgentInvocationError(WorkflowError)` — agent failure with `agent_name`
- [ ] `InvalidClientIdError(WorkflowError)` — input validation with `client_id`
- [ ] `ClientNotFoundError(WorkflowError)` — search miss with `client_id`
- [ ] `ContextHandoffError(WorkflowError)` — inter-agent handoff failure

---

## Cross-Cutting Concerns Scorecard

| # | Concern | Score | Status | Key Evidence |
|---|---------|-------|--------|--------------|
| 1 | **Isolation** | 55% | 🟡 Partial | Fresh SequentialBuilder per call; no per-client actor mailbox |
| 2 | **Determinism** | 40% | 🟡 Partial | Sequential pipeline ordered; no request-level serialization |
| 3 | **Concurrency Safety** | 25% | 🟡 Partial | ConcurrencyLimiter available; not wired into CLI path |
| 4 | **Supervision** | 40% | 🟢 Improved | Async retry + typed exceptions + failure classification |
| 5 | **Separation of Concerns** | 50% | 🟢 Improved | Resilience layer separated from errors and orchestration |
| 6 | **Fast Failures** | 50% | 🟢 Improved | asyncio.wait_for() enforced; deadline bounds retries |
| 7 | **Circuit Breaker** | 35% | 🟢 Implemented | Full state machine; integrated into retry flow |
| 8 | **Token Economics** | 25% | 🟡 Partial | AgentResponse.token_usage extracted per stage; APIM recommended for budget enforcement |
| 9 | **Graceful Degradation** | 20% | 🟡 Partial | Circuit breaker + limiter locally; APIM AI Gateway recommended for 429/backend-pool failover |
| 10 | **Observability** | 50% | 🟢 Improved | Correlation IDs, durations, token usage, reasoning traces captured; APIM + Log Analytics recommended for full pipeline |
| | **Overall** | **39%** | | +5% from previous (34%) |

---

## Gaps & Future Work

These items require infrastructure or framework changes beyond the current codebase:

| Gap | Required For | Dependency |
|-----|-------------|------------|
| Per-client actor mailbox | Isolation (100%), Determinism (100%) | Actor framework (e.g., Orleans, Dapr) or custom async queue per client_id |
| AI Gateway (APIM) deployment | Token Economics (100%), Graceful Degradation (100%) | Azure API Management with `azure-openai-token-limit` policy, backend pools, and 429 failover |
| Token budget enforcement | Token Economics (100%) | APIM token rate-limiting policies + local threshold alerts from `AgentResponse.token_usage` |
| OpenTelemetry export | Observability (100%) | `opentelemetry-sdk` + Azure Monitor exporter to Log Analytics workspace |
| Reasoning traces to Log Analytics | Observability (100%) | Foundry v2 SDK telemetry pipeline → Log Analytics workspace |
| Request queuing with backpressure | Graceful Degradation (100%) | Service layer (FastAPI / Azure Functions) with bounded queue |
| Supervision tree | Supervision (100%) | Hierarchical error escalation with restart strategies |

---

### G-ACTOR-007: Token Economics (Usage Tracking & Budget Awareness)

**Objective**: Capture token consumption per agent call to enable cost visibility, throttling decisions, and budget enforcement.

**Rationale**: Without token usage visibility, there is no way to detect runaway prompts, set per-client budgets, or decide when to throttle. The MAF `AgentResponse` object exposes `.token_usage` with `prompt_tokens`, `completion_tokens`, and `total_tokens`. This data must be captured, logged, and surfaced to operators.

**What's Implemented (Local)**:
- `AgentStageMetrics` model captures `TokenUsage` per agent stage in `src/models/output.py`
- `_extract_stage_metrics()` in `orchestrator.py` reads `token_usage` from MAF `AgentResponse` messages
- Token counts logged per-stage with correlation ID at INFO level
- CLI displays token usage summary panel when data is available
- `WorkflowResult.total_token_usage` aggregates across all stages

**What Requires AI Gateway (APIM) for Full Coverage**:
- **Token rate limiting**: APIM `azure-openai-token-limit` policy enforces per-minute/per-hour token budgets at the gateway level
- **Budget alerting**: APIM metrics emit token counts to Azure Monitor; alert rules trigger when thresholds are approached
- **Cross-request aggregation**: Individual requests know their own usage, but only an API gateway can aggregate across all consumers
- **Throttling decisions**: When to apply backpressure is a gateway-level concern — the local orchestrator provides the data, APIM enforces the policy

**Success Criteria**:
- [x] `TokenUsage` Pydantic model with `prompt_tokens`, `completion_tokens`, `total_tokens`
- [x] `AgentStageMetrics` captures per-agent `TokenUsage` and reasoning
- [x] Token usage extracted from `AgentResponse` message metadata
- [x] Token counts logged with correlation ID
- [x] CLI displays token usage summary
- [ ] (Future) APIM `azure-openai-token-limit` policy deployed
- [ ] (Future) Azure Monitor alerts on token budget thresholds

**Implementation Reference**: `src/models/output.py` → `TokenUsage`, `AgentStageMetrics`; `src/workflow/orchestrator.py` → `_extract_stage_metrics()`; `src/main.py` → `_display_token_usage()`.

---

### G-ACTOR-008: Graceful Degradation (AI Gateway)

**Objective**: Handle HTTP 429 (rate limiting), backend failures, and capacity exhaustion gracefully using an AI Gateway (Azure API Management) in front of Foundry endpoints.

**Rationale**: The local circuit breaker and retry logic protect against transient failures at the orchestrator level, but production deployments need gateway-level protection. An AI Gateway like Azure API Management provides multiple modalities for graceful degradation that the local orchestrator cannot implement alone.

**Degradation Modalities via APIM AI Gateway**:

| Modality | APIM Policy | Behavior |
|----------|-------------|----------|
| **Token rate limiting** | `azure-openai-token-limit` | Reject requests before they hit the LLM when token budget is exhausted |
| **HTTP 429 handling** | `retry` + `Retry-After` header | Respect backend rate limits; propagate `Retry-After` to callers |
| **Backend pool failover** | `set-backend-service` + `choose` | Route to alternate Foundry endpoints or model deployments when primary returns 429/5xx |
| **Request queuing** | External queue (Service Bus) | Buffer excess requests instead of rejecting them outright |
| **Circuit breaker** | `choose` + context variables | Gateway-level circuit breaker complements local breaker for cascading protection |
| **Cached fallback** | `cache-lookup` / `cache-store` | Return cached risk assessments for recently-evaluated clients during outages |
| **Graceful error response** | `return-response` | Return informative error with retry guidance instead of raw 429/503 |

**Architecture — APIM as AI Gateway**:

```
┌──────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  Client   │────▶│  Azure API Mgmt     │────▶│  Foundry Endpoint   │
│  (CLI /   │     │  (AI Gateway)       │     │  (Primary)          │
│  Service) │     │                     │     └─────────────────────┘
└──────────┘     │  • Token rate limit  │              │
                 │  • 429 → Retry-After │     ┌────────▼────────────┐
                 │  • Backend failover  │────▶│  Foundry Endpoint   │
                 │  • Circuit breaker   │     │  (Secondary/Backup) │
                 │  • Request logging   │     └─────────────────────┘
                 └─────────────────────┘
```

**Success Criteria**:
- [x] Local circuit breaker protects against cascading failures
- [x] Local retry with classified failure handling
- [ ] (Future) APIM deployed as AI Gateway in front of Foundry endpoint
- [ ] (Future) `azure-openai-token-limit` policy configured
- [ ] (Future) Backend pool with primary + secondary Foundry endpoints
- [ ] (Future) 429 responses handled with `Retry-After` propagation

**Implementation Reference**: Local resilience in `src/resilience.py`; APIM deployment is infrastructure-level (see `WORKFLOW-ARCHITECTURE.md` AI Gateway section).

---

### G-ACTOR-009: Observability Pipeline (Reasoning, Tokens, Telemetry)

**Objective**: Capture the full observability surface — token usage, agent reasoning traces, and workflow telemetry — and route it through a pipeline from the local orchestrator → Foundry v2 project → Log Analytics workspace.

**Rationale**: Production AI systems require visibility into *what the model thought* (reasoning), *how much it cost* (tokens), and *how it performed* (latency, errors). The observability pipeline has three tiers:

1. **Local CLI** — Immediate developer feedback (reasoning in magenta, token usage panel)
2. **Foundry v2 Project** — Agent telemetry sent via SDK for project-level dashboards
3. **Log Analytics Workspace** — Long-term storage for cross-project analytics and alerting

**Tier 1: Local CLI (Implemented)**:
- Reasoning traces displayed in `dim magenta` via `--verbose` flag
- Token usage summary panel displayed after every run
- Correlation IDs in structured log output
- Duration tracking per workflow execution

**Tier 2: APIM Gateway Observability**:
- Request/response logging via APIM diagnostic settings
- Token consumption metrics emitted to Azure Monitor
- Prompt content (optionally) captured for audit trails
- Latency percentiles per agent endpoint

**Tier 3: Foundry v2 → Log Analytics Pipeline**:
- Foundry v2 SDK captures agent invocation telemetry within the project
- Project diagnostic settings route telemetry to a Log Analytics workspace
- Reasoning traces (returned as separate property on `AgentResponse`) are:
  1. Extracted by the orchestrator (`_extract_stage_metrics()`)
  2. Displayed locally (CLI)
  3. Logged with correlation ID (structured logging)
  4. (Future) Sent to Foundry project via SDK telemetry
  5. (Future) Routed to Log Analytics for long-term analysis

**Reasoning Capture Architecture**:

```
AgentResponse
  ├── .text          → JSON output (parsed by orchestrator)
  ├── .reasoning     → Chain-of-thought trace (captured by _extract_stage_metrics)
  └── .token_usage   → Token counts (captured by _extract_stage_metrics)
         │
         ├──▶ CLI: dim magenta panel (--verbose)
         ├──▶ Structured log: [WORKFLOW:{id}] reasoning: ...
         ├──▶ (Future) Foundry v2 project telemetry
         └──▶ (Future) Log Analytics workspace
```

**Success Criteria**:
- [x] Reasoning extracted from `AgentResponse` message metadata
- [x] Reasoning displayed in CLI with distinct color (dim magenta)
- [x] Token usage logged per stage with correlation ID
- [x] `--verbose` flag enables reasoning display
- [x] `ENABLE_REASONING_DISPLAY` env var for config
- [ ] (Future) APIM diagnostic settings configured
- [ ] (Future) Foundry v2 SDK telemetry integration
- [ ] (Future) Log Analytics workspace receiving reasoning + token data

**Implementation Reference**: `src/workflow/orchestrator.py` → `_extract_stage_metrics()`; `src/main.py` → `_display_reasoning()`, `_display_token_usage()`; `src/config.py` → `enable_reasoning_display`.

---

## Architecture Decision Records

### ADR-001: Resilience in `src/resilience.py`, Not `src/errors.py`

**Context**: Circuit breaker, retry, and concurrency limiter are stateful policy objects. Exception definitions are stateless type declarations.

**Decision**: Resilience primitives live in `src/resilience.py`. Exception types live in `src/errors.py`.

**Rationale**: Mixing stateful resilience policy with exception definitions violates single-responsibility. The resilience module depends on `CircuitOpenError` from errors, but errors must NOT depend on resilience state.

### ADR-002: Retry Only Transient Failures

**Context**: The actor pattern document warns against retrying everything. Parse errors, validation failures, and contract violations will never succeed on retry.

**Decision**: `TRANSIENT_EXCEPTIONS = (ConnectionError, TimeoutError, asyncio.TimeoutError, OSError)`. All other exceptions propagate immediately.

**Rationale**: Retrying a `json.JSONDecodeError` from a malformed agent response wastes one full timeout cycle and one full token budget. The correct response is to fail immediately and surface the contract violation.

### ADR-003: Total Deadline Budget, Not Per-Attempt Timeout

**Context**: A naive approach sets a per-attempt timeout (e.g., 10s × 3 attempts = 30s max). But backoff delays between attempts add unbounded time.

**Decision**: `async_retry_with_backoff()` accepts a `deadline` parameter. Each attempt checks `time.monotonic()` against the deadline before executing AND before sleeping.

**Rationale**: This guarantees the user never waits longer than `Config.timeout_seconds`, regardless of retry count or backoff growth.

---

## Testing Checklist

| Test | File | Validates |
|------|------|-----------|
| Circuit breaker opens at threshold | `test_resilience.py` | G-ACTOR-002 |
| Circuit breaker half-open allows probe | `test_resilience.py` | G-ACTOR-002 |
| Circuit breaker success resets state | `test_resilience.py` | G-ACTOR-002 |
| Retry succeeds after transient failure | `test_resilience.py` | G-ACTOR-003 |
| No retry on non-transient error | `test_resilience.py` | G-ACTOR-003 |
| Retry respects deadline budget | `test_resilience.py` | G-ACTOR-001 + G-ACTOR-003 |
| Workflow timeout raises typed error | `test_workflow.py` | G-ACTOR-001 |
| Breaker rejects when open | `test_workflow.py` | G-ACTOR-002 |
| Transient retry in workflow succeeds | `test_workflow.py` | G-ACTOR-003 |
| Concurrency limiter rejects when full | `test_resilience.py` | G-ACTOR-005 |
| Fresh builder per execute() call | `test_workflow.py` | G-ACTOR-004 |
| Stage metrics populated with agent names | `test_workflow.py` | G-ACTOR-007, G-ACTOR-009 |
| Token usage extracted from message metadata | `test_workflow.py` | G-ACTOR-007 |
| Reasoning extracted from message metadata | `test_workflow.py` | G-ACTOR-009 |
| TokenUsage model defaults and values | `test_models.py` | G-ACTOR-007 |
| AgentStageMetrics model with reasoning | `test_models.py` | G-ACTOR-009 |
| WorkflowResult total_token_usage aggregation | `test_models.py` | G-ACTOR-007 |
