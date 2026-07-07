# Skill S07 — ai-agent

## Purpose
Design agent workflows (MCP prompts / proactive digests) under Anton's automation posture:
*prepare and propose; the runner disposes.*

## When to use
Roadmap R3/R4 items (weekly summary, deal alerts, coupon hunting) and any new
"Anton does X for you."

## Required context
- `docs/design_decisions.md` C6 and **C9 (non-negotiable — no confidence exception, ever)**.
- The `sync_coros_runs` prompt in `mcp_server.py` — the reference protocol. Its step list:
  fetch external runs → dedup (external ID, then date + distance-within-0.1 km fallback) →
  suggest a shoe per run (pace primary, distance secondary, active shoes only, lower mileage
  breaks ties — the heuristic *stated in the prompt*) → present → **WAIT** → write via
  `log_run_to_shoe` → summarize → 600/700/800 km threshold check. Timezone: run dates are
  already America/Toronto local (`run_date` field — never convert raw timestamps).
  This step list mirrors the source; if they disagree, the prompt in `mcp_server.py` wins.
- `docs/domain_model.md` §5.3 (the assistant is a client) and §5.5 (the runner is the tiebreaker).
- `docs/roadmap.md` R3 for sequencing; CLAUDE.md §14 INV-8 (the confirmation-gate invariant).

## Workflow
1. **State what the agent *reads*** — existing tools/resources only. A missing read is an
   S01/S06 prerequisite, not an excuse to improvise.
2. **State what it may *write*** — must be an existing gated path (never a new one; INV-2).
3. **Encode the protocol as numbered steps** modeled on the reference above, always including
   an explicit **WAIT for confirmation** step and the suggestion heuristic in the prompt text.
4. Decide the surface: prompt in the + menu, Home module, or the R3.5 channel.
5. **Dry-run the full protocol conversationally** before calling it done.

## Common mistakes
- Auto-writing "because the confidence is high" — C9 has no confidence exception.
- Inventing data when a tool returns empty — the prompt must say "never invent."
- Burying the suggestion heuristic so the runner can't audit it.
- Building delivery infrastructure before the on-demand version proves value (roadmap ordering).
- Giving the agent a personality at the expense of the protocol.

## Checklist
- [ ] Reads = existing tools only
- [ ] Writes = existing gated paths only
- [ ] Explicit WAIT step present
- [ ] Heuristics stated in the prompt text
- [ ] Dry-run transcript sane
- [ ] C9 re-read and complied with · wrap up per S13
