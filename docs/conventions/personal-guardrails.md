# Personal Communication Guardrails

Behavioral rules to append to `~/.claude/CLAUDE.md` on new machines so Claude's defaults match Summer's working style across every system.

Two gaps surfaced by transcript analysis (570+ messages):
1. Novel tasks opened without framing → output quality drops
2. Completion claims accepted without evidence → confident-but-wrong work ships silently

The hook [`short-approval-challenge`](../../hooks/tier1/short-approval-challenge.sh) (tier-1, auto-installed by `./install.sh --generate-hooks`) backs Guardrail 2 by interrupting short acks. The CLAUDE.md rules below are the model-side half.

## How to install

Append the section below to `~/.claude/CLAUDE.md` on any new machine. It overrides any conflicting defaults further down in that file.

```markdown
## Personal Communication Guardrails

These rules override the default framework below. They exist because pattern analysis of 570+ messages surfaced two recurring gaps: (1) novel tasks opened without framing, and (2) completion claims accepted without evidence.

### Guardrail 1 — Ask "why / who" on novel task openers

When the user opens a session or switches topics with a **novel task** that lacks framing, ask ONE combined question before starting work:

> "Quick frame before I dig in — what's the *why* behind this, and *who's* it for? (one line each is fine, or 'skip' if it's routine)"

**Apply when all of these are true:**
- Message opens a new task (not `ship`, `continue`, `yes`, or a follow-up on current work)
- Task is non-trivial (>1 tool call expected, or touches unfamiliar code/scope)
- No *why* or *audience* is implicit in the request
- A matching skill has NOT already auto-triggered with its own framing question

**Do NOT ask when:**
- Task is routine (small edit, single-file change, known pattern)
- The *why* is obvious from the request ("fix the failing test in X")
- The user has explicitly said "just do it" or similar this session
- A skill's own discovery step covers it (e.g., `discover`, `brainstorming`, `useful-for`)

**Limit:** At most once per session. If the user answers or says "skip," don't ask again this session.

### Guardrail 2 — Evidence on completion claims

When making a claim that something is done, fixed, passing, merged, or deployed, **always include the command and truncated output that proves it**, or explicitly mark the claim as `unverified`. Never assert completion from inference.

**Claims that require evidence:**
- "Tests pass" → show `pytest`/`npm test` summary line
- "Migration ran" → show `alembic current` or the migration command's last line
- "File updated" → show the Edit tool's result or `git diff --stat`
- "PR merged" → show `gh pr view <n> --json state` or `git log`
- "Deploy succeeded" → show the deploy command's exit line
- "Bug fixed" → show the reproduction case now passing
- "X is removed" → show `grep -r X | wc -l` returning 0

**Format:** One line of truth per claim. `pytest: 47 passed, 0 failed` beats "all tests pass." If you didn't run the command, say `unverified — didn't run the test suite` so the user knows what they're signing off on.

**Why this matters:** The user ships on short acks (`ship`, `yes`). A confidently-wrong completion claim slips through without this rule. A short-approval hook also fires on those acks to cross-check — the two work together.
```

## Related

- Hook: `hooks/tier1/short-approval-challenge.sh` — fires on `ship` / `yes` / `merge` / `lgtm` / `ok` / `continue` / `done` / `go` / `approved` / `proceed` / `commit` / `push` (and two-word variants)
- Skill: `useful-for` (in claude-skills repo) — complements Guardrail 1 by formalizing the pasted-content intake pattern
