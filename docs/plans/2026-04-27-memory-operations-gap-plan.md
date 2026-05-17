# Memory Operations Gap Plan

> **For Claude:** Use `claude_flow` execution discipline: inspect first, keep
> changes scoped, implement task-by-task, verify after each task, and do not
> auto-promote or delete memory without explicit user approval.

**Goal:** Fill the remaining gaps from
`docs/proposals/2026-04-27-memory-systems-takeaways.md` by adding safe,
review-first memory operations: import review, archive listing/diffing, lint
alignment, and docs.

**Architecture:** Add deterministic Python CLIs that produce review artifacts
and read-only reports. No LLM calls, no background daemon, no database, no
Notion dependency. Permanent memory files remain user-reviewed source of truth.

**Tech Stack:** Python stdlib, markdown files, pytest. Follow existing script
style: importable functions plus CLI, `CLAUDE_FLOW_DIR` override for tests,
manual review outputs, no auto-commit.

**Source proposal:** `docs/proposals/2026-04-27-memory-systems-takeaways.md`

---

## Current State

Already done:

- README has a compact "Memory operations" section.
- `docs/backlog/2026-q2.md` links the remaining import/archive tasks.
- Existing memory system has episodic/semantic/procedural layout.
- Existing `memory-triage-on-stop.py` writes advisory `REVIEW_QUEUE.md`.
- Existing memory-compilation design covers `/lint-memory`, broken links,
  orphan memories, stale references, and contradictions.

Gaps to fill:

1. No importer for freeform memory dumps from other LLMs.
2. No read-only archive listing/diff workflow.
3. README guidance does not show concrete commands yet.
4. Backlog should be closed only after tested implementation lands.
5. Need to verify whether `/lint-memory` already covers the new conventions
   (`IMPORT_REVIEW.md`, archive directories, review-only outputs).

---

## Non-Goals

- Do not replace the 3-tier memory architecture.
- Do not auto-write imported entries into `MEMORY.md`.
- Do not auto-delete stale memories.
- Do not add Notion, Obsidian, or any external app dependency.
- Do not implement write-restore in v1. Diff first; restore later if needed.
- Do not modify global Claude memory.

---

## Files Touched

Create:

- `scripts/import_memory_dump.py`
- `scripts/memory_archive.py`
- `tests/test_import_memory_dump.py`
- `tests/test_memory_archive.py`

Modify:

- `README.md`
- `docs/backlog/2026-q2.md`
- Possibly `docs/conventions/memory-entry-schema.md` if new review artifact
  conventions need documenting
- Possibly `skills/lint-memory/SKILL.md` in the canonical skills repo if the
  skill does not already exclude review artifacts and archive directories

Verify only:

- `hooks/tier2/memory-triage-on-stop.py`
- `docs/archive/plans/2026-04-10-memory-compilation-design.md`
- `docs/archive/plans/2026-04-10-memory-compilation.md`

---

## Task 0: Pre-Flight

**Purpose:** Avoid branch drift and stale assumptions.

1. Confirm repository root:

   ```bash
   git rev-parse --show-toplevel
   ```

   Expected: `/Users/summerrae/claude_code/claude_flow`

2. Confirm the symlinked canonical path still resolves to the same checkout:

   ```bash
   pwd -P
   git -C /Users/summerrae/Codex/claude_flow rev-parse --show-toplevel
   ```

3. Confirm worktree state:

   ```bash
   git status --short --branch
   ```

   Expected: no tracked changes except the current docs/proposal work. Preserve
   existing untracked `.claude/worktrees/`, `AGENTS.md`, and `skills/`.

4. Read the proposal and existing memory docs:

   ```bash
   sed -n '1,240p' docs/proposals/2026-04-27-memory-systems-takeaways.md
   sed -n '1,220p' memory/README.md
   sed -n '1,220p' hooks/tier2/memory-triage-on-stop.py
   ```

---

## Task 1: Implement `scripts/import_memory_dump.py`

**Purpose:** Convert a freeform exported memory/context dump into a review-only
`IMPORT_REVIEW.md` file.

**Files:**

- Create: `scripts/import_memory_dump.py`
- Create: `tests/test_import_memory_dump.py`

### Behavior

CLI:

```bash
python scripts/import_memory_dump.py imported-context.md \
  --out memory/IMPORT_REVIEW.md
```

Inputs:

- Markdown or plain text file.
- Optional `--project-root` for tests and nonstandard execution.
- Optional `--force` to overwrite an existing output file.

Output:

```markdown
# Import Review

_Source: imported-context.md_
_Generated: 2026-04-27T...Z_

## Project Facts

- [ ] ...

## User Preferences

- [ ] ...

## Decisions

- [ ] ...

## Recurring Gotchas

- [ ] ...

## Rejected / Too Vague / Task-Specific

- [ ] ...
```

Classification rules, v1 deterministic:

- User preferences: lines containing "prefer", "never", "always", "I like",
  "I don't want", "responses", "style", "tone".
- Decisions: lines containing "decided", "decision", "chose", "use X over Y",
  "approved", "rejected".
- Gotchas: lines containing "gotcha", "bug", "failed", "avoid", "do not",
  "breaks", "regression", "watch out".
- Project facts: lines containing repository/tooling/domain facts that do not
  match stronger categories.
- Rejected/vague/task-specific: lines that are too short, purely temporal
  ("today", "this task"), or generic advice with no durable project value.

Classification priority:

1. Rejected/vague/task-specific
2. Recurring gotchas
3. Decisions
4. User preferences
5. Project facts

Safety constraints:

- Never modify `MEMORY.md`.
- Never modify files under `memory/semantic`, `memory/procedural`, or
  `memory/episodic`.
- Refuse to overwrite `--out` unless `--force` is provided.
- Preserve original text as bullets; do not invent facts.

### Implementation Notes

Expose importable functions:

```python
def split_candidate_lines(text: str) -> list[str]: ...
def classify_line(line: str) -> str: ...
def build_review_markdown(source: Path, categorized: dict[str, list[str]]) -> str: ...
```

Keep code stdlib-only. Use `argparse`, `datetime`, and `pathlib`.

### Tests

Add tests for:

- obvious preference line maps to `User Preferences`
- obvious decision line maps to `Decisions`
- obvious gotcha line maps to `Recurring Gotchas`
- short/vague lines map to rejected
- generated markdown has all expected headings
- existing output is not overwritten without `--force`
- script does not create or modify `MEMORY.md`

Run:

```bash
python -m pytest tests/test_import_memory_dump.py -q
```

Acceptance criteria:

- All tests pass.
- Running the script on a small fixture creates only `IMPORT_REVIEW.md`.
- Output is reviewable markdown with checkboxes.

---

## Task 2: Implement `scripts/memory_archive.py`

**Purpose:** Provide safe archive visibility before any restore automation:
list archives, create snapshots, and diff archive vs current memory.

**Files:**

- Create: `scripts/memory_archive.py`
- Create: `tests/test_memory_archive.py`

### CLI

```bash
python scripts/memory_archive.py create \
  --memory-dir memory \
  --archive-root .claude/memory-archives

python scripts/memory_archive.py list \
  --archive-root .claude/memory-archives

python scripts/memory_archive.py diff 2026-04-27T181500Z \
  --memory-dir memory \
  --archive-root .claude/memory-archives
```

### Behavior

`create`:

- Copies memory files into a timestamped archive directory.
- Includes `.md`, `.json`, and `.jsonl` files under `memory/`.
- Excludes `memory/IMPORT_REVIEW.md`, `memory/REVIEW_QUEUE.md`, and
  `memory/knowledge/` generated articles unless `--include-derived` is passed.
- Refuses to overwrite an existing archive ID.

`list`:

- Prints archive IDs, file count, and total bytes.
- Exits 0 with a friendly empty-state message if no archives exist.

`diff`:

- Produces a unified diff between the archive and current memory.
- Read-only.
- Exits 0 when no diff, 1 when differences exist, 2 for invalid input.

### Safety Constraints

- No restore command in v1.
- No deletion.
- No auto-commit.
- No writes outside `--archive-root` for create.
- Do not follow symlinks inside memory directories.

### Implementation Notes

Expose importable functions:

```python
def iter_memory_files(memory_dir: Path, include_derived: bool = False) -> list[Path]: ...
def create_archive(memory_dir: Path, archive_root: Path, archive_id: str | None = None) -> Path: ...
def list_archives(archive_root: Path) -> list[ArchiveInfo]: ...
def diff_archive(memory_dir: Path, archive_dir: Path) -> str: ...
```

Use stdlib only: `argparse`, `dataclasses`, `difflib`, `pathlib`, `shutil`.

### Tests

Add tests for:

- archive creates expected directory and copies expected files
- review artifacts are excluded by default
- derived knowledge files are excluded by default
- `--include-derived` includes knowledge files
- list returns archives sorted by ID
- diff reports changed, added, and removed files
- diff command does not modify current memory

Run:

```bash
python -m pytest tests/test_memory_archive.py -q
```

Acceptance criteria:

- All tests pass.
- Manual create/list/diff works against a temp memory fixture.
- No restore behavior exists.

---

## Task 3: Align `/lint-memory` With Review Artifacts

**Purpose:** Ensure new review-only files do not become lint noise.

**Files:**

- Verify: `docs/archive/plans/2026-04-10-memory-compilation.md`
- Verify or modify canonical `lint-memory` skill if present

### Steps

1. Locate canonical `lint-memory`:

   ```bash
   ls ~/.claude/skills/lint-memory/SKILL.md
   ls /Users/summerrae/claude_code/claude-skills/lint-memory/SKILL.md
   ```

2. Inspect its exclusions:

   ```bash
   rg -n "IMPORT_REVIEW|REVIEW_QUEUE|archive|knowledge|exclude|orphan" \
     ~/.claude/skills/lint-memory/SKILL.md
   ```

3. If `IMPORT_REVIEW.md`, `REVIEW_QUEUE.md`, and archive directories are not
   excluded from orphan-memory checks, update the canonical skill to say:

   ```text
   Exclude review/operational artifacts from orphan checks:
   IMPORT_REVIEW.md, REVIEW_QUEUE.md, .claude/memory-archives/**,
   memory-archives/**, knowledge/** derived articles.
   ```

4. If the skill lives outside this repo, make a separate commit in the
   canonical skills repo. Do not fake it inside `claude_flow`.

Acceptance criteria:

- `/lint-memory` will not tell users to add `IMPORT_REVIEW.md` to permanent
  memory.
- Archive directories are ignored.
- Any cross-repo edits are called out explicitly in final handoff.

---

## Task 4: Update Docs and Backlog

**Purpose:** Make the new workflows discoverable and close completed backlog.

**Files:**

- Modify: `README.md`
- Modify: `docs/backlog/2026-q2.md`
- Optionally modify: `docs/conventions/memory-entry-schema.md`

### README Additions

Under "Memory operations", add concrete commands:

```bash
# Import a memory/context dump into a review file
python scripts/import_memory_dump.py imported-context.md --out memory/IMPORT_REVIEW.md

# Create a dated memory archive
python scripts/memory_archive.py create --memory-dir memory

# List archives
python scripts/memory_archive.py list

# Diff an archive against current memory
python scripts/memory_archive.py diff <archive-id> --memory-dir memory
```

Add one sentence:

```text
`IMPORT_REVIEW.md` is a staging file. Promote entries manually; do not treat it
as canonical memory.
```

### Backlog

Mark completed after tests pass:

- `scripts/import_memory_dump.py`
- read-only memory archive diff workflow

Acceptance criteria:

- README shows exact commands.
- Backlog accurately reflects completed work.
- No docs claim restore is available.

---

## Task 5: Full Verification

Run targeted tests:

```bash
python -m pytest tests/test_import_memory_dump.py tests/test_memory_archive.py -q
```

Run broader relevant tests:

```bash
python -m pytest scripts/test_pattern_detector.py tests/test_pricing.py tests/test_ledger.py -q
```

Manual smoke tests:

```bash
tmpdir=$(mktemp -d)
mkdir -p "$tmpdir/memory"
printf '%s\n' \
  'Prefer concise responses.' \
  'Decision: use local markdown over Notion.' \
  'Gotcha: do not auto-promote imported memory.' \
  > "$tmpdir/imported-context.md"

python scripts/import_memory_dump.py "$tmpdir/imported-context.md" \
  --out "$tmpdir/memory/IMPORT_REVIEW.md"

python scripts/memory_archive.py create \
  --memory-dir "$tmpdir/memory" \
  --archive-root "$tmpdir/archives"

python scripts/memory_archive.py list \
  --archive-root "$tmpdir/archives"
```

Expected:

- Import review file exists and contains categorized checkboxes.
- Archive create succeeds.
- Archive list shows one archive.
- `memory/IMPORT_REVIEW.md` is not copied unless explicitly included.

---

## Commit Strategy

Recommended commits:

1. `docs(memory): plan memory operations gap closure`
2. `feat(memory): add import review script`
3. `feat(memory): add read-only archive diff workflow`
4. `docs(memory): document memory operation commands`

If `lint-memory` requires changes in the separate `claude-skills` repo, commit
that separately there:

```bash
git -C /Users/summerrae/claude_code/claude-skills add lint-memory/SKILL.md
git -C /Users/summerrae/claude_code/claude-skills commit \
  -m "docs(lint-memory): ignore memory review artifacts"
```

---

## Final Acceptance Criteria

- `scripts/import_memory_dump.py` exists, is tested, and never modifies
  canonical memory.
- `scripts/memory_archive.py` exists, is tested, and supports create/list/diff
  without restore/delete.
- README includes command examples and clearly labels `IMPORT_REVIEW.md` as
  staging.
- Backlog items from `docs/proposals/2026-04-27-memory-systems-takeaways.md`
  are either completed or explicitly left open.
- `/lint-memory` behavior is verified or patched so review artifacts do not
  pollute memory hygiene reports.
- No external dependencies are added.
- No user memory is deleted, overwritten, or promoted automatically.
