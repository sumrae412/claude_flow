# Memory systems takeaways — 2026-04-27

> **Status:** Proposal. Takeaways from a Claude memory article covering
> platform memory, project instructions, markdown memory folders, Notion, and
> Obsidian. This is not a commitment to ship.

**Scope:** Evaluate what is useful for `claude_flow`. The article is aimed at
general Claude users, so most of it is onboarding inspiration rather than new
architecture.

---

## Executive read

`claude_flow` already has the stronger version of the article's core idea:
file-based memory, MCP access, handoff snapshots, memory injection, event logs,
and an episodic/semantic/procedural taxonomy.

The useful work is not "add four markdown files." The useful work is making
memory safer and easier to operate: import, review, archive, restore, and
explain.

---

## 1. Memory hygiene flow — **recommend: adopt**

**Article idea:** Users should periodically open Claude memory, delete stale
entries, and manually curate what should persist.

**Relationship to `claude_flow`:**
We already have partial machinery:

- `memory/README.md` defines the 3-tier memory architecture.
- `hooks/tier2/memory-triage-on-stop.py` writes a mechanical review queue for
  unindexed memory files.
- `docs/superpowers/specs/2026-04-10-memory-compilation-design.md` proposes
  knowledge lint checks for broken links, orphan memories, stale entries, and
  contradictions.

**Recommendation:**
Promote memory hygiene from an internal hook side effect into a user-visible
workflow:

- Keep `memory-triage-on-stop.py` advisory-only.
- Add or finish a `/lint-memory` workflow that reports:
  - orphan memory files
  - broken links
  - stale file/function references
  - likely contradictions
- Require explicit user approval before deleting or rewriting memory entries.

**Why:**
Bad memory is worse than missing memory. Missing context creates uncertainty;
wrong context creates confident wrong behavior. Delightful little footgun.

---

## 2. Memory import/export — **recommend: adopt as onboarding**

**Article idea:** If a user has useful context in another LLM, export it and
seed Claude's memory rather than starting over.

**Relationship to `claude_flow`:**
This maps cleanly onto the existing file-based memory layout, but the repo has
no obvious import path today.

**Proposed feature:**
Add a small importer that takes a freeform markdown context dump and produces a
reviewable memory seed:

```text
input:  imported-context.md
output: memory/IMPORT_REVIEW.md
```

The output should classify entries into:

- project facts
- user preferences
- decisions
- recurring gotchas
- rejected / too vague / task-specific notes

Do not write directly to permanent memory on the first pass. Generate a review
file and let the user promote entries.

**Possible command shape:**

```bash
python scripts/import_memory_dump.py imported-context.md --out memory/IMPORT_REVIEW.md
```

**Why:**
This gives new projects a low-friction bootstrap path without polluting
`MEMORY.md` with a giant unvetted prompt blob.

---

## 3. Archive and restore — **recommend: adopt, narrow**

**Article idea:** Keep weekly archive copies of memory files outside Claude's
active working area so accidental rewrites can be restored.

**Relationship to `claude_flow`:**
We already snapshot before compaction via `hooks/tier1/pre-compaction-backup.sh`,
but that is session-state backup, not memory restore.

**Proposed feature:**
Document and optionally script a memory archive flow:

```text
.claude/memory-archives/YYYY-MM-DD/
```

or, for safer isolation:

```text
~/.claude/memory-archives/<project-slug>/YYYY-MM-DD/
```

The restore path matters more than the backup path:

- list available archives
- diff archive against current memory
- restore selected files only
- never restore over uncommitted memory changes without confirmation

**Recommendation:**
Start with docs plus a read-only diff command. Add write restore later if the
manual workflow proves annoying.

---

## 4. Obsidian / knowledge wiki — **recommend: continue existing design**

**Article idea:** Obsidian works well because it is local markdown with links,
which lets Claude build and maintain a second brain.

**Relationship to `claude_flow`:**
This is already aligned with the approved memory compilation design:

- raw memories remain source of truth
- compiled concept articles live under `memory/knowledge/concepts/`
- cross-links connect related concepts
- lint checks catch broken links and stale references

**Recommendation:**
Do not add an Obsidian dependency. Keep the output Obsidian-compatible markdown
so users can optionally open the memory directory as a vault.

**Concrete doc addition:**
When memory compilation ships, mention:

```text
Optional: open the project's memory directory as an Obsidian vault.
```

That gets the benefit without making the platform depend on a notes app.

---

## 5. Notion connector — **recommend: reject for core**

**Article idea:** Store AI preferences and prompts in a Notion database.

**Why not core:**

- `claude_flow` intentionally favors local markdown and file-based MCP access.
- Notion adds API state, auth, sync latency, and another source of truth.
- The highest-value memory entries are operational constraints and gotchas,
  which belong next to the repo.

**Allowed pattern:**
Users can keep a Notion database manually, but `claude_flow` should not treat
it as canonical memory.

---

## 6. Project instructions and platform memory — **recommend: document only**

**Article idea:** Clean up Claude's global memory and fill in project
instructions.

**Relationship to `claude_flow`:**
This is useful user advice, but not something the repo can or should automate.

**Recommendation:**
Add a short setup note to the user-facing docs:

- keep global Claude memory small
- put project-specific rules in `AGENTS.md` / `CLAUDE.md`
- put durable gotchas in project memory
- avoid duplicating the same rule across all three unless it is truly global

---

## Proposed sequence

1. **Memory hygiene docs:** Add a short "Memory Operations" section to
   `README.md`.
2. **Import review script:** Build `scripts/import_memory_dump.py` that writes
   `IMPORT_REVIEW.md` only.
3. **Archive diff:** Add a read-only archive/diff command before any restore
   automation.
4. **Memory compilation:** Continue the existing knowledge-wiki design; keep it
   Obsidian-compatible but app-agnostic.

## Non-goals

- Replace the existing 3-tier memory architecture with a beginner template.
- Auto-delete or auto-rewrite memory without review.
- Add Notion as a core dependency.
- Treat global Claude memory as project source of truth.
