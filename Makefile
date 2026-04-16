.PHONY: test record-fixtures record-adversarial-fixture

# Default test run — fast, deterministic, no live LLM calls.
test:
	pytest tests/ -v

# Refresh all golden-fixture recordings against the live LLM.
# Requires ANTHROPIC_API_KEY in env. Network + paid tokens.
record-fixtures: record-adversarial-fixture

# Refresh tests/fixtures/adversarial_breaker/recorded_response.json by
# dispatching the real adversarial-breaker persona against the planted
# bug. The live test asserts contract bounds and writes the response back.
record-adversarial-fixture:
	RUN_LIVE_LLM=1 pytest tests/test_adversarial_breaker_live.py -v
