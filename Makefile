.PHONY: test record-fixtures record-adversarial-fixture calibrate-adversarial calibrate-adversarial-dry advisor-ab-pilot advisor-ab-20trial advisor-ab-preflight

# Default test run — fast, deterministic, no live LLM calls.
test:
	pytest tests/ -v

# Refresh all golden-fixture recordings against the live LLM.
# Requires ANTHROPIC_API_KEY in env. Network + paid tokens.
record-fixtures: record-adversarial-fixture

# Refresh tests/fixtures/adversarial_breaker/recorded_response.json by
# dispatching the real adversarial-breaker persona against the planted
# bug. The live test asserts contract bounds and writes the response back.
# Cost: ~$0.01 per run.
record-adversarial-fixture:
	RUN_LIVE_LLM=1 pytest tests/test_adversarial_breaker_live.py -v

# Run the adversarial-breaker calibration loop against the labeled corpus
# (~20 LLM calls, ~$0.20 per run). Updates reviewer-registry.json's
# calibration block on pass; exits non-zero on fail.
# Manual / monthly cadence — DO NOT wire into per-PR CI.
calibrate-adversarial:
	RUN_LIVE_LLM=1 python scripts/calibrate_adversarial_breaker.py

# Same dispatch + scoring, but doesn't write the registry. Useful for
# previewing per-case scores before committing to a recorded value.
calibrate-adversarial-dry:
	RUN_LIVE_LLM=1 python scripts/calibrate_adversarial_breaker.py --dry-run

# ---------------- Advisor-tool A/B eval ----------------
#
# Preflight check — prints the 4 open TODOs from evals/advisor_tool_ab/README.md
# that MUST be addressed before trusting live-run numbers. Runs every time
# one of the live targets is invoked, as a dependency.
advisor-ab-preflight:
	@echo ""
	@echo "==================== Advisor A/B live preflight ===================="
	@echo "Before the numbers are trustworthy, verify ALL of these:"
	@echo ""
	@echo "  [ ] scripts/pricing.py rates match https://www.anthropic.com/pricing"
	@echo "      (rates ship with 'TODO: verify' comments)"
	@echo "  [ ] advisor_20260301 tool shape matches current Anthropic docs"
	@echo "      (run_ab.py uses a best-effort placeholder; prints a WARN)"
	@echo "  [ ] MODEL_SONNET / MODEL_OPUS IDs are current"
	@echo "      (https://docs.anthropic.com/en/docs/about-claude/models)"
	@echo "  [ ] ANTHROPIC_API_KEY is exported"
	@echo "  [ ] anthropic SDK installed (pip install anthropic)"
	@echo ""
	@echo "If any are unverified, cancel with Ctrl-C now."
	@echo "====================================================================="
	@echo ""

# Pilot — 1 trial across 4 cases x 3 arms = 12 API calls + 12 judge calls.
# Purpose: validate the end-to-end pipeline (prompts, advisor tool shape,
# pricing, ledger, judge, relevancy axis) BEFORE committing to a 20-trial run.
# Cost: ~$1-2. Writes results to evals/advisor_tool_ab/results_pilot.json
# and the ledger. Expected runtime: 1-3 minutes.
advisor-ab-pilot: advisor-ab-preflight
	@[ -n "$$RUN_LIVE_LLM" ] || (echo "ERROR: set RUN_LIVE_LLM=1 to enable live calls"; exit 1)
	@[ -n "$$ANTHROPIC_API_KEY" ] || (echo "ERROR: ANTHROPIC_API_KEY not set"; exit 1)
	python evals/advisor_tool_ab/run_ab.py \
		--cases-dir evals/advisor_tool_ab/cases \
		--out evals/advisor_tool_ab/results_pilot.json \
		--judge --relevancy-axis --trials 1 \
		--session-id advisor_ab_pilot_$$(date +%Y%m%d_%H%M%S)
	@echo ""
	@echo "Pilot complete. Review results_pilot.json, then run:"
	@echo "  python scripts/ledger.py summarize --caller advisor_ab"
	@echo ""
	@echo "If the pilot looks sane, graduate to: make advisor-ab-20trial"

# Full statistical-significance run — 4 cases x 3 arms x 20 trials = 240
# API calls + 240 judge calls. Cost: ~$20-40. Only run this AFTER the pilot
# validates the pipeline AND you have a decision pending that the result
# would actually swing. Writes results_20trial.json + analysis_20trial.md.
advisor-ab-20trial: advisor-ab-preflight
	@[ -n "$$RUN_LIVE_LLM" ] || (echo "ERROR: set RUN_LIVE_LLM=1 to enable live calls"; exit 1)
	@[ -n "$$ANTHROPIC_API_KEY" ] || (echo "ERROR: ANTHROPIC_API_KEY not set"; exit 1)
	@[ -f evals/advisor_tool_ab/results_pilot.json ] || (echo "ERROR: run 'make advisor-ab-pilot' first"; exit 1)
	python evals/advisor_tool_ab/run_ab.py \
		--cases-dir evals/advisor_tool_ab/cases \
		--out evals/advisor_tool_ab/results_20trial.json \
		--judge --relevancy-axis --trials 20 \
		--session-id advisor_ab_20trial_$$(date +%Y%m%d)
	python scripts/stat_analysis.py \
		--results evals/advisor_tool_ab/results_20trial.json \
		--format markdown \
		--out evals/advisor_tool_ab/analysis_20trial.md
	@echo ""
	@echo "20-trial complete. Reports:"
	@echo "  - evals/advisor_tool_ab/results_20trial.json"
	@echo "  - evals/advisor_tool_ab/analysis_20trial.md"
	@echo "  - python scripts/ledger.py summarize --session-id <from above>"
