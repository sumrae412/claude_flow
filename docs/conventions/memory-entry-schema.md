# Memory Entry Schema

Canonical schema for optional YAML frontmatter fields in memory files under `~/.claude/projects/<project>/memory/`.

Validated by [`lint-memory` Check 6 (Frontmatter Schema)](https://github.com/summerela/claude-skills/blob/main/lint-memory/SKILL.md).

## Required fields

Every memory file carries these fields (separately documented in the auto-memory system — see `CLAUDE.md`):

- `name` — short identifier
- `description` — one-line summary
- `type` — one of `user`, `feedback`, `project`, `reference`

## Optional fields

Authors may add the fields below to strengthen a claim with provenance or calibration. Absence is never a warning.

### `evidence`

- **Type:** list of non-empty strings
- **Purpose:** point at the episodes, incidents, or lessons the entry builds on. Lets a future reader trace why the memory was written.
- **Example:**
  ```yaml
  evidence:
    - "2026-03-14 incident: migration silently skipped backfill"
    - "PR #214 rollback discussion"
  ```
- **Invalid shapes (rejected by Check 6):**
  - `evidence: ""` — empty string, not a list
  - `evidence: null` — null, not a list
  - `evidence: "ep-001"` — scalar string, not a list
  - `evidence: [""]` — list contains an empty string
  - `evidence: [null]` — list contains a non-string

### `confidence`

- **Type:** number (int or float) in the inclusive range `[0.0, 1.0]`
- **Purpose:** calibrate how strongly the memory claims its rule. `1.0` = certain, `0.5` = heuristic, `<0.3` = speculative. Useful when later-session retrieval needs to weight memories.
- **Example:**
  ```yaml
  confidence: 0.85
  ```
- **Invalid shapes (rejected by Check 6):**
  - `confidence: "0.9"` — string, not a number
  - `confidence: 1.5` — above range
  - `confidence: -0.1` — below range
  - `confidence: "high"` — non-numeric

## Why these specific fields

`evidence` and `confidence` were carved out because they're the two fields most likely to drive automated consumption later (e.g. weighted retrieval, blame-tracing when a memory turns out wrong). Typos here silently break downstream tooling; typos in free-form prose don't. Validating shape — not presence — preserves the freedom to add them only where they earn their keep.

## Adding new optional fields

If you propose a new optional frontmatter field for general adoption:

1. Update this schema doc with type, purpose, example, and invalid shapes
2. Extend Check 6 in `lint-memory/SKILL.md` to validate the new field
3. Leave absence as non-fatal (new fields must not regress existing memory)
