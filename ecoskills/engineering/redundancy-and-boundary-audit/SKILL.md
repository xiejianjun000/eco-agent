---
name: redundancy-and-boundary-audit
description: Repository-level judgment framework for auditing duplication, module boundaries, and naming fidelity; complements module-level code review and produces a scan report. Use when asked to audit repo-level redundancy, boundary violations, or duplicate implementations. 仓库级重复、模块边界与命名保真审计框架；补充模块级代码审查并产出扫描报告。要求审计仓库级冗余、边界违规或重复实现时使用。
keywords: [redundancy, boundary, duplicate, overlap, dedup, 冗余, 重复, 边界]
---
# Repository-Level Redundancy & Boundary Audit

Repository-wide judgment framework for auditing duplication, module boundaries, and naming fidelity. Complements a module-level code-review skill (3-pass) — this skill operates at **repo level** and produces a scan report, not a code review.

## Step 0 — MANDATORY: delta against the previous scan

Before any new analysis, locate the most recent scan report (your repo's configured report directory, or the first-ever scan if none exists). For EVERY finding in it, mark exactly one of:

- **Resolved** — cite the commit or current `file:line` proving it
- **Still valid** — re-verify the evidence still matches (line numbers drift; re-grep, don't trust)
- **Outdated** — the code changed underneath it (e.g. a "weak 3-file module" grew 10×)

A scan that skips Step 0 is worse than no scan: it manufactures the illusion that "someone already checked". This is why previous scans rot.

## Step 1 — Ingest deterministic facts (never re-derive them by reading code)

Consume, in order:

1. Output of your repo's automated checks (duplicate-symbol scanners, path-cluster scanners, dead-reference checkers) — if any
2. Latest architecture/module inventory, if present
3. Import graph / code graph, if fresh

Your job starts where the checkers stop: they say "4 classes named AuditLogger exist"; you decide which of A/B/C each pair is. If a fact you need has no checker, note it as a tooling gap in the report — do not hand-count what a script should count.

## Step 2 — Duplication triage (the core judgment)

For every duplicate-symbol / parallel-implementation candidate:

**The falsifiable test**: two things are duplicates **iff a change to one MUST be synced to the other**. If you cannot name the concrete change that would need syncing, they are not duplicates.

Classify into exactly one:

| Class | Meaning | Action |
|---|---|---|
| **A — True duplicate** | Same concept, same contract; sync-or-break | Merge plan (bottom-up: leaf → stateful → orchestrator) |
| **B — Same name, different concept** | Same name, different semantics | Rename one (the less-established); NO merge |
| **C — Same shape, different domain** | Similar structure, different domain/lifecycle | Leave alone; record in the do-not-touch list |

Hard rules (violations are how such audits fail):

- Every A-class claim binds `file:line` for BOTH sides + the concrete sync-failure scenario
- **Line counts are banned as evidence.** Acceptance criteria use grep hit counts (e.g. `grep "class AuditLogger" src/ → 2`)
- Check the existing do-not-touch list BEFORE proposing any merge — C-class calls are already argued; re-litigating them wastes a cycle
- Caller analysis MUST include `tests/`, and import checks use symbol grep / AST, never single-line regex (multi-line parenthesized imports evade `from.*X` patterns)

## Step 3 — Boundary & naming fidelity

For each module flagged by Step 1/2, or new since the last scan:

- **Deletion test**: "if I delete this, what breaks?" — name the concrete breakage, or flag the module as possibly vestigial (verify via used-by graph, not intuition)
- **Naming match**: does the name describe what it does today? (`AuditLogger` that never logs fails this)
- **Declared-vs-real behavior**: what the docstring/README/prompt claims vs what the code does. Real cases: a "quality gate" whose verdict nothing parses; a script whose documented CLI usage cannot run (no `__main__`)
- **Capability-instruction alignment** (agent systems only): every instruction in an agent's prompt must be executable with its declared tools; impossible instructions produce hallucinated compliance

## Step 4 — Multi-angle verification of suspects

One angle per pass over the suspect list — never mix angles (you go blind to all but the first pattern):

1. Data/control flow  2. Import-dependency collision  3. API contract  4. Test impact
5. Frontend impact  6. Config/env  7. DX  8. Rollback safety
9. **Mechanism authenticity** — for every declared topic/capability/gate/hook, find its consumer; zero consumers = decorative mechanism (report as HIGH)
10. **Security-baseline regression** — spot-check path/shell safety, HMAC, error sanitization against past review conclusions; do not re-audit from scratch
11. **Process hygiene** — record-rule compliance (`file:line` on completed items), artifact-index registration, numbering collisions
12. **Runtime smoke** — if you can run it: the service boots, the health endpoint returns 200, one happy path works

## Step 5 — Report & closure (non-negotiable)

Output to your repo's configured report directory (never a git-ignored scratch dir — that is how a previous scan silently disappeared):

- `00_delta.md` — Step 0 result
- `10_duplication.md` — A/B/C table with evidence
- `20_boundaries.md` — Step 3 findings
- `30_angles.md` — Step 4, one section per angle actually run
- `90_actions.md` — remediation matrix (impact × risk), each action with `file:line`

Then: register the report in your repo's artifact index; file every action item into the repo's issue/todo tracker in the same session (an action that lives only in the report does not exist).

## Output discipline

- 0 findings is a legitimate result for a healthy area — never invent findings
- Every finding: severity (HIGH/MED/LOW) + class tag (A/B/C or angle number) + `file:line` + falsifiable acceptance criterion
- Confidence notes on judgment calls; a reviewer must be able to re-derive each verdict from its cited evidence alone
