---
name: code-review-methodology
description: Multi-dimensional review framework for auditing complex software modules across 18 quality dimensions in three passes — execution/integration, architecture/systems, reliability/correctness. Includes multi-angle iterative review, E2E-test review angles, migration review angles, and derived rules. Use when reviewing a module, pull request, or code change for bugs, architecture, or security issues. 多维度代码审查框架：三遍扫描覆盖 18 个质量维度（执行/集成、架构/系统、可靠性/正确性），含多角度迭代审查、E2E 测试审查与迁移审查。审查模块、PR 或代码变更的 bug、架构与安全问题（含中文）时使用。
keywords: [review, audit, code, pr, diff, lint, "pull request", check, 评审, 代码审查, 审核]
---
# Systematic Code Review Methodology

Multi-dimensional review framework for auditing complex software modules. Covers 18 quality dimensions across three review passes, plus multi-angle iterative review for cross-cutting features.

## Review Passes

### Pass 1 — Execution & Integration (7 dimensions)

Focus on what's broken *right now* — bugs, gaps, missing wiring.

| Dimension | Key Questions |
|-----------|---------------|
| **Task Lifecycle** | Are all states (PENDING→QUEUED→RUNNING→COMPLETED/FAILED/BLOCKED) handled? Are transitions validated? Is BLOCKED visible? |
| **Tool Calling** | Does every code path that needs tools have them? Are tools injected at the right layer? Are dynamic extensions missing tool handlers? |
| **Streaming** | Are SSE/websocket events real-time or batched? Are callbacks bridging async→generator correctly? Is backpressure handled? |
| **Memory** | Do worker outputs flow back into shared context? Do downstream steps see upstream results? Is memory compressed/saved at boundaries? |
| **Retries / Failure** | Is the escalation chain complete (retry→downgrade→re-decompose→report)? Are retries bounded? Do failed upstream steps block/unblock downstream correctly? |
| **Logging** | Are critical paths logged at info level? Are debug logs hiding in production? Are audit events logged? |
| **Governance** | Is approval wiring end-to-end? Do workers gate on approvals? Are permission checks performed before execution? |

### Pass 2 — Architecture & Systems (6 dimensions)

Focus on *how* the system runs, scales, and breaks.

| Dimension | Key Questions |
|-----------|---------------|
| **Distributed Systems** | Is state shared across workers? Are there module-level mutable globals? Is the task queue persistent or in-memory? Are there distributed locks? |
| **Runtime Architecture** | Are resources (connections, agents) pooled or leaked? Are there dual implementations of the same concept? Is there connection reuse? |
| **Async Systems** | Are async primitives used correctly? Is publish() sequential or parallel? Are there sync IO calls in async paths? Is backpressure implemented? |
| **Security Engineering** | Are shell/file operations gated on every path? Is user input sanitized before prompt injection? Is there rate limiting? Are secrets ever exposed in logs? |
| **Observability** | Can you trace a single request end-to-end? Are session ids consistent across layers? Are metrics exported? Is log rotation configured? |
| **Workflow Orchestration** | Are dependency types (HARD/SOFT/DATA) enforced? Is there cycle detection in the DAG? Are step timeouts configured? Is there pause/resume/checkpoint? |

### Pass 3 — Reliability & Correctness (5 dimensions)

Focus on *what happens when things go wrong*.

| Dimension | Key Questions |
|-----------|---------------|
| **Governance** | Is governance unified or split across layers? Are cost quotas enforced per-step? Are permission states persisted or in-memory? |
| **Validation** | Are step ids checked for uniqueness? Are dependency references validated against existing ids? Are self-references detected? Are lengths bounded? |
| **Schema Enforcement** | Are there duplicate model definitions? Are enum-like strings typed? Are registries consistent across layers? Do all models carry the same fields across boundaries? |
| **Retries** | Is the backoff strategy exponential with jitter? Are retry budgets layered (HTTP × task × DAG)? Are side-effect operations idempotent under retry? |
| **Fallback** | Is there a model/provider downgrade path? Is there tool-level recovery? Is there a checkpoint/restore mechanism? |

## Priority Tiers

| Tier | Label | Criteria | Examples |
|------|-------|----------|----------|
| **P0** | Fix now | Crash, infinite loop, security vacuum, data corruption | Missing approval gate, cycle in DAG, no step timeout |
| **P1** | Fix soon | Feature broken in common path, observability gap, leak | Resource leak, broken trace id, no exponential backoff |
| **P2** | Should fix | Design debt, missing feature, non-critical edge case | Unsupported dependency type, no rollback, dual governance |
| **P3** | Nice to have | Polish, nice-to-have, rare edge case | Log format, deadlock detail logging, sync IO cleanup |

## Review Workflow

```
1. SCOPE         → List all files in the module boundary (list dir, grep)
2. READ          → Read every file in the critical path (don't skip)
3. TRACE         → Follow the data flow: API → Service → Engine → Worker
4. SCAN-PUBLIC   → For every new/changed public symbol (enum value, class, function),
                    grep the whole repo for all callers and verify each one with
                    at least 8 lines of context. Include:
                    - Enum additions: check all `if x == Enum` comparisons and
                      `x in {...}` set membership checks for breakage
                    - Function signature changes: verify every call site still
                      works with new params
                    - Type additions: verify serialization/deserialization paths
5. FIND          → For each dimension, ask the standard questions
6. DOCUMENT      → Write findings with: severity, exact location (file:line), impact description
7. CROSS-REFERENCE → Note findings that appear in multiple dimensions (highest priority)
8. PRIORITIZE    → Assign P0-P3 with estimated effort
9. PUBLISH       → Write the review to your repo's review log with date + module
```

## Output Format

Each finding:

```
| Severity | Issue | `file:line` | Impact |
```

Master aggregation should include:
- Deduplication across review passes
- Cross-reference tracking (which passes found the same issue)
- Heatmap of dimensions vs priority tiers
- Fixed/unfixed status tracking

## Cross-Dimension Correlation

Findings that appear in multiple dimensions signal architectural flaws, not isolated bugs:

| Pattern | Dimensions | Meaning |
|---------|-----------|---------|
| Approval gap | Security + Governance + Runtime | A governance design exists but doesn't reach the execution path |
| Dual implementations | Architecture + Schema + Orchestration | Two code paths evolved separately, will diverge further |
| Missing fallback chain | Retries + Fallback + Architecture | Resilience was designed but not wired through |
| Capability promise gap | Security + Tool Calling + Governance | A role/agent card promises read-only but its tool registry exposes destructive tools — safety relies on prompt discipline instead of toolset enforcement. Check both the registry layer and the posture/permission layer — fixing only one leaves the other exposed |

## Library / Utility Module Review

When reviewing a non-runtime library module, the dimensions shift from runtime concerns to **correctness, integration, and hygiene**.

**Pass 1 — Code Quality**: data model correctness (field validation, enum→string coercion, lossless serialization roundtrips), edge cases (empty inputs, None, missing files, corrupted data), accurate type hints, docstrings matching behavior, dead code.

**Pass 2 — Integration & Consistency**: cross-module wiring (does data flow correctly between modules?), naming consistency, paired-dictionary key alignment (e.g. LANGUAGE_MAP vs FILE_TYPE_MAP keys must match), `__init__.py` exports, design-doc alignment.

**Pass 3 — Safety & Performance**: SQL injection (parameterized queries), path traversal (`resolve()` + containment check, symlinks off by default), memory (large files read in chunks), error handling (OSError/JSONDecodeError caught, actionable messages).

**Tool-assisted review notes**:
1. `ruff check <path>` (project rules) — import hygiene, trailing commas
2. `ruff check --select=ALL <path>` — broader issues; respect project config (many violations may be intentional)
3. `git diff --stat HEAD` after auto-fix — verify the fixer only touched what you expected
4. Run the full test suite after any fix — no matter how trivial
5. `python -c "import module"` — verify no import errors after `__init__.py` changes
6. **Don't trust project-rules-only lint config**: if `pyproject.toml` selects only a few rules, running all rules reveals far more issues (many auto-fixable). Check the config before deciding what to fix.

## Multi-Angle Iterative Review

When reviewing a cross-cutting feature that touches multiple layers (API, UI, persistence, tests), a single-pass review finds at most ~30% of real bugs. The remaining 70% surface only when you deliberately switch angles.

### The pattern: Review → Fix → Repeat × N

Each round picks ONE family of angles. Don't mix families — the brain optimizes for the first pattern it recognizes and becomes blind to others.

**Core insight**: Early rounds find bugs in *what was built*. Later rounds find bugs in *how it connects to everything else*. Cross-module issues are invisible until the core implementation stabilizes — that's why you need multiple passes.

### 8 angle families

| Family | What it catches | Example questions |
|--------|-----------------|-------------------|
| **Architecture & Design** | Model mismatch, missing routes, DRY violations | Do all layers agree on field names and types? Is every endpoint registered? |
| **Data Flow** | Write paths without persistence, broken roundtrips | If I mutate state, does it survive a restart? Do all consumers receive updates? |
| **Security** | Injection, unauthorized execution, prompt leaks | Is every user input validated before reaching the runtime? Is there a whitelist? |
| **Concurrency & Async** | Deadlocks, event-loop blocking, race conditions | What's the lock acquisition order? Any sync I/O in async functions? |
| **Backward Compatibility** | Breaking existing data, event contract changes | Does old data load without errors? Do existing consumers understand new fields? |
| **Error Handling** | Missing 4xx/5xx, silent failures, missing fallbacks | What happens when the external dependency is down? Does the UI close the modal? |
| **Test Quality** | Selector mismatches, missing coverage, unrealistic mocks | Does every UI test selector exist in the component? Are edge cases covered? |
| **Code Quality** | Unused code, type errors, coercion bugs | Any imports that nothing uses? Bytes vs string mismatches? |

### Rules

1. **One family per pass.** Checking security and data flow in the same pass guarantees you'll miss subtle issues in both.
2. **Grep test selectors against source before writing tests.** For every selector or identifier used in a test file, verify the corresponding attribute/element exists in the production code. A 10-second grep prevents a wasted review round.
3. **Assume every async/sync boundary is wrong until proven correct.** Static tools rarely catch sync functions calling async methods without `await`, or blocking I/O inside an event loop.
4. **Trace every state mutation to its persistence call.** "In-memory only" is the most common data-loss bug in stateful backends.
5. **Cross-module issues are invisible in single-file review.** When two files implement parallel versions of the same logic, review them side-by-side in the same pass.
6. **Commit per fix, not per review round.** Keeps `git bisect` functional.
7. **Verify after every edit.** A 3-second syntax check catches broken commits before they land.
8. **New enum variant → full-codebase grep.** Adding a value to an enum/union/dict key-set without grepping all consumers is the most common silent-gap bug. Grep the type name AND every existing variant value (raw strings) — mapping dicts, switch cases, match arms, if-elif chains, serialization round-trips. Pay special attention to `.get(x, default)` — it masks the gap.
9. **Dual-module consistency check.** When the same event/concept is projected by two modules, verify they agree on output shape. Neither module is individually wrong, but their outputs diverge silently.
10. **Snapshot payload ≠ state.** When a system writes snapshots, verify the snapshot content is the accumulated state, not the triggering event's payload (the implementation defaults to the data at hand).
11. **Real integration smoke test before sign-off.** Start the actual server and hit the changed endpoint. Mock-only testing cannot catch import errors, route registration failures, middleware misconfiguration, or key-resolution bugs.
12. **Warning/error pattern precision.** Test that warnings fire for the RIGHT imports/paths and not unrelated ones — a `DeprecationWarning` in a package `__init__` can fire on every import of any symbol from that package.

### When to use which strategy

| Scope | Strategy |
|-------|----------|
| Single-file bug fix | 1 family (usually Data Flow or Error Handling) |
| New module (< 200 lines) | 2 families: Architecture + Data Flow |
| Full-stack feature (FE+BE+tests) | 3–5 families minimum |
| Security-critical path | All 8 families |
| Refactor touching > 5 files | All 8 families |

### Universal verification checklist

Run after *every* review round, regardless of language or stack:

- [ ] Compile/parse check for every changed file
- [ ] Type-check if the language has a type checker
- [ ] Grep all test selectors/identifiers against source code
- [ ] `git diff --stat` — verify the file list matches intent
- [ ] Manual trace: pick one user action, follow it from entry point to persistence and back
- [ ] Audit every I/O call for async/sync correctness
- [ ] For every state change in memory, verify a corresponding persistence call exists
- [ ] If enum/type-union changed: grep all consumers of that type name + every existing variant value

## E2E + LLM-Driven Test Review Angles

When reviewing persona-driven, LLM-as-Judge, or multi-layer E2E tests, the standard angles miss test-infrastructure bugs that only surface at runtime:

| # | Angle | What it catches |
|---|-------|-----------------|
| 19 | **DOM Selector Fidelity** | Selectors in test JSON/TS that don't match actual `data-testid` attributes or DOM structure |
| 20 | **Behavioral Flag Defaults** | Test steps that assume a component flag is on but the source defaults it to off — the test exercises a different code path than intended |
| 21 | **Response Collection Correctness** | Element-type mismatches: collecting `.first()` when multi-turn/multi-element scenarios need all elements; page-type-specific selectors (chat vs plan) |
| 22 | **LLM-as-Judge Safety** | Judge API calls that flood the backend, miss fallbacks, or use wrong request shapes |
| 23 | **Cross-Page State Isolation** | Scenarios that navigate between pages while quality-check selectors only work on the origin page |
| 24 | **Test Environment Dependencies** | Missing env vars, port conflicts, concurrent-test safety, timeout stacking |

**Rules for E2E test review:**
1. Grep every test selector against source before trusting it — a selector that silently matches nothing wastes a whole round.
2. Every behavioral toggle in the source has a default — find it. If the test needs the toggle ON but never clicks it, the test is exercising a different path.
3. Response-text extraction must be page-aware, not hard-coded to one selector.
4. LLM-as-Judge must degrade gracefully in 3 failure modes: backend unreachable → skip; API timeout → heuristic fallback; malformed response → text-based heuristic. All three paths must be exercised in review.

## Data Migration Review

When reviewing a data migration (format upgrade, schema change, file conversion), the standard angles miss **data-integrity bugs** that only surface in the target dataset:

| # | Angle | What it catches | Example |
|---|-------|-----------------|---------|
| 25 | **Source-Target Cardinality** | File/record count mismatch between source and target | 187 source files vs 152 target — 35 missing, source grew after migration |
| 26 | **Field Completeness Across Code Paths** | New fields added to one function but not its sibling | One search path extracts the new dict, the other never passes it |
| 27 | **Idempotency Under Re-run** | Non-idempotent transforms that corrupt data on second pass | Re-running the migration should skip everything; any non-skip is a bug |
| 28 | **Path Traversal in Resolver Functions** | `Path(user_input)` without `resolve()` + containment check | `_resolve("../../../etc/passwd")` escapes the target directory |

**Migration review workflow:**

```
1. COUNT          → Compare counts: source vs target (mismatch = bug)
2. RE-RUN         → Execute migration again; verify ALL skip (idempotency)
3. SAMPLE         → Random-sample 3-5 target files; verify new + old fields
4. DIFF-BODY      → For one file, verify body unchanged (only metadata modified)
5. CROSS-PATH     → For every output constructor, verify fields appear in ALL paths
6. VALIDATE       → Run the target validator on the full directory
7. SECURITY-SCAN  → Audit every Path(user_input) for traversal
```

**Derived rules:**
1. Count before trusting. `len(source) == len(target)` catches 100% of stale-target bugs.
2. Re-run proves idempotency. Second run with all skips = correct.
3. Cross-path field audit: a new field in constructor A but not B is a bug, not a TODO.
4. Every user-input path needs a fence: `resolve()` + `relative_to` containment check.

## Pre-deletion safety (refactor reviews)

Before deleting any file: grep the full project for its path, imports, and exported symbols. Archive references are acceptable — active code references are NOT. Auto-generated reference docs (route indexes, README tables, endpoint counts) drift from actual code — re-check the doc's claim against the code before trusting a "0 endpoints" report.

Also check for unreachable code after `return`/`raise`/`sys.exit`: read the 5 lines after each at function scope; code after a return statement is dead code — the most common round-2 discovery.
