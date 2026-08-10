# Verifying CI status after a push (check-runs vs classic statuses)

## Symptom

After pushing, `GET /repos/<owner>/<repo>/commits/<sha>/status` returns
`state: pending` with `total_count: 0` even when every CI check passed.
Waiting on that endpoint for `success` never resolves — you poll forever,
burn turns, or misreport a fully green CI as pending.

## Why

Repos whose CI runs on GitHub Actions report results as **check-runs**, not
classic commit *statuses*. The `/commits/<sha>/status` endpoint only reflects
classic statuses (legacy integrations); with 0 classic statuses it sits at
`pending` indefinitely regardless of Actions results. Real example: the
auto-mejora run for commit `d8f1ac1f` — all 9 check-runs `success`, workflow
run #491 `completed/success`, yet `/status` kept saying `pending`.

**Deeper root cause (real run, commit `399589a2`):** the combined state also
aggregates third-party check SUITES. This repo has a **Vercel** integration
whose suite stays in `queued` forever; while it is queued, the combined
`/commits/<sha>/status` is `pending` no matter how green GitHub Actions is.
This is a pre-existing condition, not something your push caused — verify by
listing check suites and confirming the only non-completed one is the
third-party app:

```bash
curl -s -H "Authorization: token $TOKEN" \
  "https://api.github.com/repos/<owner>/<repo>/commits/<sha>/check-suites" \
  | python3 -c "import json,sys; [print(s['id'], s['status'], s['conclusion'], (s.get('app') or {}).get('name')) for s in json.load(sys.stdin).get('check_suites',[])]"
```

GitHub Actions suite `completed`/`success` + Vercel `queued` → report CI
green and note the Vercel queue as pre-existing; do NOT block the deploy or
keep polling the combined endpoint. (`GET /actions/runs?head_sha=<sha>` can
return 0 runs even while check-runs exist — query `?per_page=N` instead, or
pull the run id from the check-runs listing.)

## The reliable check (check-runs)

```bash
TOKEN=$(sed 's|https://[^:]*:\([^@]*\)@github.com|\1|' ~/.git-credentials)
curl -s -H "Authorization: token $TOKEN" -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/<owner>/<repo>/commits/<sha>/check-runs" \
  | python3 -c "import json,sys; [print(f\" - {r['name']}: {r['status']} {r.get('conclusion')}\") for r in json.load(sys.stdin).get('check_runs',[])]"
```

Green = every check-run `status: completed` with `conclusion: success`.
`status: in_progress` with `conclusion: None` = still running.

## Workflow-level source of truth

`GET /actions/runs?per_page=N` → `workflow_runs` list: a run with
`status: completed` + `conclusion: success` is the definitive green signal.
Compare `created_at` vs `updated_at` to confirm progress when a run looks
stuck — a growing `updated_at` means it's working, not hung.

## Duration expectation (this repo)

CI run #491 took ~21 minutes wall-clock (created 00:41:43Z → updated
01:03:07Z). Lint/typecheck finish in ~1 min; the **Tests (3.11)/(3.12)** jobs
are the long tail. Poll in chunks (e.g. 25s sleep × N) and budget up to
~25 min — a single 600s terminal call is NOT enough; if it times out, check
the workflow run's `updated_at` to distinguish "still running" from "stuck"
before assuming a problem.

## Smoke tests for skill-doc (markdown-only) changes

After syncing skill files (SKILL.md + references), the cheap structure tests are:

```bash
uv run python -m pytest tests/website/test_extract_skills.py \
  tests/website/test_generate_skill_docs.py tests/tools/test_skill_size_limits.py -q
```

(34 passed on the self-improvement v1.10 sync.) Plus a frontmatter smoke check
on the copied SKILL.md (regex `^---\n(.*?)\n---`, assert `name:` and `version:`
present). No need to run the whole suite for markdown-only changes.
