---
name: repo-analysis
description: 'Cross-repository architecture audit and pattern absorption methodology. Use when analyzing external repos to extract design patterns, map them onto YOUR system''s architecture, and produce design documents with gap analysis and optional fix code. Covers 5 phases: repo scan, pattern extraction, mapping, value judgment, and structured output. 适用于外部仓库调研、架构审计、模式对比、设计文档产出与修复代码。'
keywords: [repo, analysis, architecture, audit, pattern, 仓库, 调研, 审计, 架构, 模式]
---
# Repo Analysis — Cross-Repository Architecture Audit & Pattern Absorption

Extract design patterns from external repositories, map them onto your own system's architecture, and produce a gap analysis with optional fix code. Core principle:

> **Don't copy implementations. Extract patterns → derive principles → design your own implementation.**

---

## Phase 1 — Repo scan (15–30 min/repo)

### 1.1 Fast structural assessment

For each external repo answer 5 questions without going deep:

| Dimension | Key question |
|---|---|
| **Positioning** | What problem does it solve? One-sentence core value |
| **Scale** | Code volume (files/lines), language stack, dependency complexity |
| **Core abstraction** | What new concepts does it introduce? (RLM, Harness, Skill, Evidence Graph...) |
| **Architecture pattern** | Monolith / microservices / plugin / Kernel+Extension? |
| **Maturity** | prototype / early-stage / production-ready? stars, maintenance activity |

### 1.2 Output

One structured summary per repo (≤ 500 words):

```markdown
## {Repo Name}
- **Positioning**: one sentence
- **Core abstractions**: {2-3 key concepts}
- **Architecture pattern**: {pattern name, with key directory tree}
- **Worth attention**: {yes/no, one-sentence reason}
- **Risks**: {license, dependencies, maturity}
```

---

## Phase 2 — Pattern extraction (cross-repo comparison)

### 2.1 Recognition dimensions

Classify each repo's patterns against a generic agent-system primitive taxonomy:

| Primitive | What to look for | External examples |
|-----------|-----------------|-------------------|
| **Intent** | How intent is expressed (natural language / structured / DSL) | structured problem definition; spec generation |
| **Context** | Context management (prompt injection / RAG / persistent REPL / knowledge graph) | RLM + persistent REPL; code graph |
| **Policy** | Constraint enforcement (RBAC / approval gates / cost quotas / constitution) | quality gates; governance layer |
| **Execution** | Agent runtime (tool use / sub-agents / sandbox / task queue) | Kernel+Extension; sub-agent recursion |
| **Evidence** | Verification mechanisms (test gates / data diff / audit logs / approval chains) | CI evidence; evidence gates |
| **Evaluation** | Quality assessment (metric-driven / LLM-as-judge / human review) | critique loops; metric ratchets |
| **Learning** | Continuous improvement (memory distillation / skill extraction / refine loops) | continual harness; interpretable memory |

### 2.2 Traps to avoid

- **Don't be misled by names**: a project called "Agent Framework" may have its core value in its evidence model, not its runtime
- **Don't classify whole repos**: the same repo can inspire multiple primitives (a repo = Context + Execution + Learning)
- **Distinguish "what it does" from "its design principles"**: the pattern may be Kernel+Extension, but the principle is "keep kernel small, everything else plugin" — the principle matters more than the implementation

---

## Phase 3 — Mapping to your system

### 3.1 Gap classification

For every identified pattern use a three-level marker:

| Marker | Meaning | Condition |
|--------|---------|-----------|
| ✅ **Implemented** | your system already has an equivalent | source path + functional comparison |
| ⚠️ **Partially implemented** | baseline exists but a key dimension is missing | point out what exists + what is missing |
| ❌ **Not implemented** | a real gap | no equivalent in your system |

Every judgment MUST be backed by source path and line number.

### 3.2 Mapping template

```markdown
### Pattern: {Pattern Name} (source: {Repo})

**Current status**: {✅/⚠️/❌}
**Existing implementation** (if any):
  - `path/to/file.py:L{line}` — {functional description}
**Missing dimensions**:
  1. {missing item 1}
  2. {missing item 2}
**Conflict/overlap risk**:
  - overlaps with existing {module}: {conflict / complementary / independent}
  - duplicates an existing module or ticket? {yes / no / partial}
```

---

## Phase 4 — Value judgment (absorb or not)

### 4.1 Decision matrix

For every ⚠️ or ❌ pattern:

| Dimension | Weight | Assessment question |
|-----------|--------|---------------------|
| **Architecture fit** | high | Does it fit your system's Work Model (Intent→Plan→Execute→Evidence→Validate→Approve)? |
| **Irreplaceability** | high | If absent, would it become a critical weakness? |
| **Implementation cost** | medium | How many new modules? How much existing code changes? |
| **Maintenance cost** | medium | Long-term complexity? New external dependencies? |
| **Overlap with existing modules** | high | Does an existing module already do 80%? (cross-directory check, not just same dir) |
| **Phase fit** | medium | Which roadmap phase does it belong to (reliable workflow / intelligence / continual agent)? |

### 4.2 Decision outcomes

- **Absorb**: architecture fit + irreplaceable → enter design phase
- **Stage**: valuable but not in the current phase → write a staged note, "wait for phase X"
- **Reference**: inspiring but not worth implementing → record in the knowledge base
- **Skip**: overlaps, conflicts, or cost far exceeds value → record the reason and skip

---

## Phase 5 — Output

### 5.1 Design document

Write one design document per absorbed pattern, using your repo's design-doc convention. Required sections: motivation, external reference, current-status mapping, design, change impact, risks & verification, phase ownership.

### 5.2 Fix code

If code changes are included:

- one-off scripts (audit, migration, verification) as standalone `.py` files with an `if __name__ == "__main__":` entry
- patch-level changes via a patch tool rather than new files
- code must be self-contained; use `print()` not a logging framework for one-off scripts

---

## Hard constraints

### Must do

1. **Every judgment carries source evidence** — no speculation; every ✅/⚠️/❌ has a file path + line
2. **Cross-domain audit** — before judging, check whether an existing module (including outside the same directory) already does 80%
3. **Separate principle from implementation** — the document's first half discusses the pattern (principle), the second half the concrete implementation plan
4. **Structured output** — design docs are designs, not production code; don't modify production source while designing

### Must not do

1. **Do not execute the external repo's code** — read, analyze, compare only
2. **Do not judge without looking at your own source** — "it probably doesn't exist" is not evidence
3. **Do not ignore overlap** — when an existing implementation is found, first evaluate enhancing it before building new
4. **Do not stop at positioning narrative** — "our system is an X" is a story, not a technical design. Technical design must answer "why must these primitives live together"

---

## Multi-repo batch flow

When the input is multiple repos:

```
Phase 1 (parallel)      each repo scanned independently, structured summaries
    ↓
Phase 2 (cross)         all repos compared, common patterns identified
    ↓
Phase 3 (per pattern)   each pattern mapped against your system
    ↓
Phase 4 (aggregate)     all gaps judged together, prioritized
    ↓
Phase 5 (output)        merged into 1-3 design docs grouped by primitive, not by repo
```

**Multi-repo output differs from single-repo**: a single repo yields one design doc; a batch (5+) yields docs merged by primitive — e.g. one doc covering every repo's findings on the Execution primitive.
