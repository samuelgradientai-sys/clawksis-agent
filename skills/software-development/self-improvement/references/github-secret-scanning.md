# GitHub secret scanning — detecting and fixing leaked credentials

When syncing skills from the profile to the repo, real API tokens stored in SKILL.md example config blocks will trigger GitHub push protection and block the push. This reference documents the detection and fix workflow.

## Real example (this session)

**Symptom:** Push rejected with:
```
remote: - Push cannot contain secrets
remote:   —— Notion API Token ——————————————————————————————————
remote:    locations:
remote:      - commit: af69bd40...
remote:        path: skills/integrations/notion-mcp/SKILL.md:49
```

The file at `skills/integrations/notion-mcp/SKILL.md:49` had:
```bash
NOTION_API_KEY=ntn_your_notion_token_here
```

## Fix workflow

```bash
# 1. Identify the file and line from the error
# 2. Replace the real token with a placeholder
echo "NOTION_API_KEY=ntn_your_notion_token_here"  # placeholder

# 3. Stage the fix and amend the commit
git add -A
git commit --amend --no-edit

# 4. Push again
git push origin main
```

## Prevention — check before committing

Before `git add -A` when syncing skills, search for token patterns:

```bash
grep -rn 'ntn_\|sk-proj-\|sk-ant\|ghp_\|gho_\|ghs_\|ghr_' \
  skills/ \
  --include='*.md' --include='*.py' --include='*.yaml' --include='*.json' \
  --include='*.yml' --include='*.toml' --include='*.env*'
```

**Evaluate each hit:**
- `sk-...` or `ghp_xx...xxxx` or `ntn_xxx...xxx` → **PLACEHOLDER** — no action needed
- `sk-proj-abc123def456...` or `ntn_12899076462...` or `ghp_AbCdEfGhIjKlMnOpQrStUvWxYz12345678` → **REAL TOKEN** — replace with placeholder before commit

**Common token formats:**
| Prefix | Service | Example placeholder |
|---|---|---|
| `ntn_` | Notion | `ntn_your_notion_token_here` |
| `sk-proj-` | OpenAI Project | `sk-proj-your-project-key` |
| `sk-ant-` | Anthropic | `sk-ant-your-anthropic-key` |
| `sk-or-` | OpenRouter | `sk-or-your-openrouter-key` |
| `ghp_` | GitHub PAT | `ghp_your_github_token` |
| `gho_` | GitHub OAuth | `gho_your_oauth_token` |

## Why this happens

Skills that include setup instructions with working tokens are common in profile copies because the user tested them. The repo's optional-skills may have proper placeholders, but the profile copy stores the actual configured value. When syncing profile → repo, these real tokens get committed. Always treat profile skill files as potentially containing real credentials.
