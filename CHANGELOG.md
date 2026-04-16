# Changelog

All notable changes to Claude Flow will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Adversarial drift detection workflow with calibration loop
- Adversarial-breaker reviewer for Phase 6
- Runtime symlink resolution for moved skill scripts
- Context facts injection into next-task subagent prompts
- Phase 5 Step 3e mid-run context extraction
- `context_facts` field in `$diff` contract
- Judge calibration, conditional re-grade, and explain-before-fix gate
- Statistical evaluation framework for prompt optimization
- Shell→LLM-CLI discipline and trap-before-side-effect patterns in coding-best-practices
- Direct-execution shape codification in subagent-driven-development
- Writing-plans gate validation against target repo script paths
- Excalidraw canvas and curmudgeon reviewer
- Workflow improvements from external pattern mining
- Three improvements inspired by Lindquist advanced-CC patterns

### Changed
- Skills moved to claude-skills repo (single source of truth via symlink)
- `.worktrees/` ignored for isolated workspaces

### Fixed
- Wired `select_reviewers.py` and `match_memory_domains.py` into skills
- `install.sh` tolerates missing memory templates and matches new subdir layout
- CodeRabbit review findings addressed

### Docs
- Archived skills-consolidation plan
- Session-learnings proposals applied from recent PRs
