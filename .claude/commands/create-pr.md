Commit, push, open a pull request, wait for CI, and merge it into `main` once
both CI checks pass. This is the end-to-end "ship this branch" path. CI is the
gate (CLAUDE.md §10, design_decisions E15): a PR merges **only** with
`backend (pytest)` and `frontend (vite build)` both green. This command never
merges around a red or missing check.

## Steps

1. **Branch.** If on `main`, create a descriptive feature branch first
   (`git switch -c <slug>`). Never commit or push directly to `main`.
2. **Commit.** Review `git status` and `git diff HEAD`. Stage only files that
   belong to the change. Don't stage stray untracked files without asking.
   Write phase-prefixed conventional commits (CLAUDE.md §5), one per numbered
   task, each ending with the session's attribution line.
3. **Push.** `git push -u origin <branch>`.
4. **Open the PR.** `gh pr create --base main` with a title matching the
   commit style and a body covering what / why / how-verified (suite count,
   `vite build`, desktop + ~380 px pass for UI work). End the body with the
   session's PR attribution line. If a PR already exists for the branch, reuse
   it (`gh pr view --json number,url`).
5. **Wait for CI.** `gh pr checks <number> --watch --fail-fast` (run it in the
   background if the harness supports that; CI usually takes a few minutes).
   Don't poll with sleeps or loops.
6. **Gate.** Before merging, confirm all of the following with
   `gh pr view <number> --json state,isDraft,mergeable,reviewDecision,statusCheckRollup`:
   - both CI checks finished with `SUCCESS`, and none are pending, failed or
     cancelled;
   - the PR is open, not a draft, and `mergeable` is `MERGEABLE` (no conflicts);
   - `reviewDecision` is not `CHANGES_REQUESTED`.
   If any condition fails, **stop and don't merge.** Report which check or
   condition failed and give the failing job's log excerpt
   (`gh run view <run-id> --log-failed`). For a test or build failure, propose
   the fix. Re-run this command after the fix is pushed.
7. **Merge.** `gh pr merge <number> --merge --delete-branch`. Merge commits
   are this repo's convention ("Merge pull request #N from …"), so don't
   squash or rebase. Never pass `--admin`, and never enable auto-merge in
   place of this gated step.
8. **Sync local.** `git switch main && git pull --ff-only`, then confirm the
   merge commit is at `HEAD` (`git log --oneline -1`).

## Required files to read first
- `CLAUDE.md` §5 (commit style), §10 (CI is the gate), Session Checklist
- `.github/workflows/ci.yml` (the two required check names)

## Output / success criteria
- PR URL, the CI result for each check, and the merge commit SHA on `main`.
- If the run stopped at the gate: the failing check or condition, the log
  excerpt, and the proposed fix. The PR stays open and unmerged.
- Deploying (the `dist/` rsync to Hetzner) is **not** part of this command.
  Do it separately after the merge.
