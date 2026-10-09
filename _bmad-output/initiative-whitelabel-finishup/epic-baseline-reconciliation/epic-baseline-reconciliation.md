---
tracker_id: ""
key: ""
type: epic
status: done
title: "Reconcile fork baseline & ratify vendor-branch strategy"
parent: initiative-whitelabel-finishup
covers: ["B1", "B2"]
after: []
assignee: ""
risk: medium
---

# Reconcile fork baseline & ratify vendor-branch strategy

## Description

Before any further commit lands on the fork, the repo's relationship to its upstream `deepseek-harness` baseline must be understood and a strategy ratified. The fork was set up as a flattened/rewritten independent repository, not a branch of upstream: `git merge-base main dsh-v0.2.0-rc.2` is empty and `main...dsh-v0.2.0-rc.2` reports `8 / 20470` changed paths. The upstream tag is therefore provenance-only, not a merge base. This epic records that finding and ratifies how the fork will relate to upstream going forward (independent fork; upstream tag kept as a provenance ref).

## Outcome

Anyone opening the repo understands that `eco-agent` is an independent fork of `deepseek-harness`, where the upstream tag sits, and that all work commits to `main` of the fork without an upstream merge — so the two follow-up epics commit their batches correctly. The signal: a `BASELINE-DEVIATION.md` exists and `git merge-base --is-ancestor dsh-v0.2.0-rc.2 main` returns false.

## Requirements

- B1: Disjoint-history finding is verified (empty merge base; `8 / 20470` divergence) and written down.
- B2: Vendor-branch strategy is chosen and recorded (independent fork; upstream tag = provenance ref; all commits to `main`).

## Done when

1. `BASELINE-DEVIATION.md` records the empty `git merge-base`, the `8 / 20470` divergence figure, and the conclusion that the upstream tag is provenance-only.
2. The ratified strategy is recorded as a dated `Decision:` in `BASELINE-DEVIATION.md` and reflected in `initiative-whitelabel-finishup.md` Notes.
3. `git merge-base --is-ancestor dsh-v0.2.0-rc.2 main` returns false (confirming the documented state).
4. Epic 2 and Epic 3 each know, from this epic, that their batches commit to `main` of the fork.

## Boundaries

Git history, provenance documentation, and the commit-branch contract. Not: any code change, any re-merge of upstream, or any change to the already-pushed commits. Not: removing the upstream tag (a policy choice settled in entry 2).

## References

- parent — _bmad-output/initiative-whitelabel-finishup/initiative-whitelabel-finishup.md, Requirements B1–B2
- source — repo: `E:/DSH/eco-agent`; tag `dsh-v0.2.0-rc.2` (local `639ed01`); commits `59366af145`, `5b4bfde858`
- constraint — prior session: lefthook pre-push death-lock; push uses SSH-over-443 + `--no-verify`

## Notes

- Decision: push uses SSH-over-443 + `git push --no-verify` (documented 2026-10-09).
- Decision: vendor-branch strategy = **establish `vendor/dsh` tracking branch** as the vendored upstream provenance snapshot; `main` stays an independent eco-agent product and does not git-merge `vendor/dsh` (would rewrite history). User's choice, 2026-10-09. The upstream tag `dsh-v0.2.0-rc.2` is retained.
- Progress (2026-10-09): entry 1.1 verified (merge-base empty, is-ancestor exit 1, 8/20470); entry 1.2 created `vendor/dsh` at `639ed01` and `BASELINE-DEVIATION.md` written. Epic 1 closed.

## Closure (2026-10-09)

- **Done when satisfied:** (1) `BASELINE-DEVIATION.md` records empty merge-base + `8 / 20470` + provenance-only tag — ✓; (2) ratified strategy recorded as dated `Decision:` — ✓ (`vendor/dsh` tracking branch; `main` independent); (3) `git merge-base --is-ancestor dsh-v0.2.0-rc.2 main` returns false (verified, exit 1) — ✓; (4) epics 2 & 3 cite this as the commit-branch contract — ✓.
- **BMAD tracking:** epic set `status: done`; leaf tickets 1.1 (spike) + 1.2 (story, hitl) marked `done` via plan files.
