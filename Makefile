.PHONY: test record-fixtures record-adversarial-fixture calibrate-adversarial calibrate-adversarial-dry

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
