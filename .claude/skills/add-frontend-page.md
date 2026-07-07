# Skill S08 — add-frontend-page

## Purpose
Add or rework a page/feature in the SPA the project way.

## When to use
New route, new page-level feature, significant component work.

## Required context
- `CLAUDE.md` §5 (JavaScript/React standards) — tokens only, React Query only, no TypeScript.
- Exemplars: `pages/Home.jsx` (inline page-local sub-components), `hooks/useApi.js`,
  `services/api.js`.
- `REDESIGN_PLAN.md` §5 — no heavy dependencies, design tokens only, mobile pass is part of done.

## Workflow
1. **api-client function** in `services/api.js`, grouped per domain.
2. **React Query hook** in `hooks/useApi.js` — query keys consistent with the family;
   mutations invalidate or optimistically patch (`onMutate`) their keys.
3. **Page** in `pages/` with page-local sub-components inline in the page file.
4. **Route** in `App.jsx` (+ legacy redirect if renaming a path).
5. Deep links carry state via params (`/deals?deal=id`), never globals.
6. Styling through `index.css` tokens and `components/ui/` primitives only — no hard-coded hex.
7. **Verify**: desktop **and** ~380 px, `vite build` clean, 0 console errors.

## Common mistakes
- fetch-in-useEffect instead of React Query.
- Recomputing a server-computed number "just for display" (violates design_decisions A4).
- Hardcoded colors bypassing tokens.
- A new charting/date/utility dependency when recharts/existing utils suffice.
- Skipping the mobile pass — it is part of Definition of Done, not polish.
- Missing empty states (the "Rotation healthy — show it proudly and small" school).

## Checklist
- [ ] `api.js` → `useApi.js` → page chain intact
- [ ] Query invalidation correct
- [ ] Both viewports pass · 0 console errors · `vite build` clean
- [ ] Deep links work
- [ ] No new heavy dependency · wrap up per S13
