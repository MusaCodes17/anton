Print a concise, read-only status report for Anton so a fresh session can orient
in one glance. This command **changes no files** — it reads the perishable state
docs and the top of the changelog, then summarizes. Use it to answer "where are
we?" without paging through the whole doc suite.

## Steps

1. Read `docs/project_state.md` **§2** (Current Development Status table) and
   **§11** (Areas Requiring Immediate Attention).
2. Read the top **3** entries of `docs/changelog.md`.
3. Print a report with exactly these lines:
   - **Current phase** — the active R-item / focus from §2 + changelog header.
   - **Last completed task** — the newest changelog entry's headline.
   - **Next priority** — the first item in project_state §11.
   - **Open blockers** — from project_state §8 (or "none").
   - **Suite count** — the test count stated in the newest changelog entry.
4. Stop. Do not edit, commit, or start any task — this is orientation only.

## Required files to read first
- `docs/project_state.md` (§2, §8, §11)
- `docs/changelog.md` (top 3 entries)

## Output / success criteria
- A five-line status report as above, each line one sentence.
- Zero file writes, zero commits, no skill invoked.
- The suite count and next priority are quoted from the docs, not inferred.
