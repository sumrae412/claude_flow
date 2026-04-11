# Pattern Library

Cross-session patterns generalized from episodic data. Each pattern has evidence (session count) and confidence level.

Patterns are added by `session-learnings` skill and `scripts/pattern-detector.py` as they accumulate evidence across sessions.

## Entry Template

```
## pattern-id
Pattern: [what happens]
Signal: [how to detect]
Response: [what to do]
Evidence: [N sessions]
Confidence: high/medium/low
Last validated: [date]
```
