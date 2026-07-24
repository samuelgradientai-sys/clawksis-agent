# Supabase audit watchdogs

Use this pattern when the user wants to monitor application conversations or function outputs stored in Supabase and alert on suspicious replies.

## Good fit

- A table stores inbound and outbound messages for one tenant/user.
- A function or workflow (for example, an agent responder) should be checked against the input it received.
- You want to detect hallucinations, off-topic replies, missing context, or obvious schema/role violations.

## Recommended flow

1. Filter the source data as narrowly as possible first.
   - Prefer a single `user_id`, `conversation_id`, or tenant key.
   - Do not inspect every row in a multi-tenant table.
2. Pair the user message with the agent response.
   - Use direction/role columns if present.
   - Otherwise pair by ordering and timestamps.
3. Evaluate the response against the expected behavior of the function.
   - Did it answer the correct intent?
   - Did it preserve the conversation context?
   - Did it invent unsupported facts?
   - Did it violate the function’s role or domain?
4. Classify each exchange.
   - `ok`
   - `suspicious`
   - `incorrect`
   - `needs_review`
5. Emit only actionable findings.
   - Keep the report short.
   - Include the user input, model output, and the specific reason it was flagged.

## Implementation notes

- Prefer SQL or direct table queries over scraping APIs when the data already lives in Supabase.
- If the target is a Supabase Function, review the function’s input/output contract first, then compare live rows against that contract.
- Keep secrets in environment variables; do not hardcode service-role keys into cron prompts or scripts.
- If the Supabase service-role JWT is the only thing available, you can still extract the project ref for routing/configuration, but the key itself should stay out of logs and reports.
- For recurring monitors, use a silent cron/watchdog pattern: print nothing when everything looks normal; print a compact report only when a suspicious exchange is found.

## Useful report shape

- timestamp / row id
- user id or conversation id
- inbound text
- outbound text
- evaluation result
- short reason
- optional suggested fix

## Reference files

- `references/meta-status.md` — existing watchdog pattern for public status feeds.
- `references/supabase-audit-watchdog.md` — this guide for auditing Supabase message tables and function outputs.
