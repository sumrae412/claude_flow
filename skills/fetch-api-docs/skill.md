---
name: fetch-api-docs
description: Fetch curated API docs from Context Hub before coding with external services to prevent hallucinations
---

# Fetch API Documentation

Before writing code that integrates with external APIs or SDKs, use Context Hub to get curated, accurate documentation.

## When to Use This Skill

Use this BEFORE coding with any external service, especially:
- Payment providers (Stripe, Braintree)
- Cloud services (AWS, Cloudflare)
- Auth providers (Auth0, Clerk)
- LLM APIs (Anthropic, OpenAI, Cohere)
- Databases (ChromaDB, CockroachDB)
- Any SDK where hallucination risk is high

## Workflow

### 1. Search for Available Docs
```bash
chub search <service-name>
```

Example: `chub search stripe` or `chub search aws`

### 2. Fetch the Relevant Doc
```bash
chub get <doc-id> --lang py   # For Python
chub get <doc-id> --lang js   # For JavaScript/TypeScript
```

Example: `chub get stripe/payments --lang py`

### 3. Follow the Documentation Exactly
- Use the exact import statements shown
- Use the exact method signatures
- Follow the initialization patterns
- Do NOT deviate from documented patterns

### 4. Annotate Discoveries
If you discover something the doc doesn't cover:
```bash
chub annotate <doc-id> "Note about what was missing or unclear"
```

### 5. Provide Feedback
After using a doc, rate it:
```bash
chub feedback <doc-id> up    # If it was helpful
chub feedback <doc-id> down  # If it was problematic
```

## Key Commands Reference

| Command | Purpose |
|---------|---------|
| `chub search` | List all available docs |
| `chub search <query>` | Search for specific docs |
| `chub get <id>` | Fetch a doc (auto-detects type) |
| `chub get <id> --lang py` | Fetch Python-specific version |
| `chub annotate <id> "note"` | Add a persistent note |
| `chub annotate --list` | View all your annotations |
| `chub feedback <id> up/down` | Rate a doc |
| `chub update` | Refresh the registry cache |

## Available Docs (Sample)

Run `chub search` to see all, but common ones include:
- `anthropic/claude-api` - Claude AI API
- `stripe/payments` - Stripe payments
- `aws/s3` - AWS S3
- `auth0/identity` - Auth0 authentication
- `cloudflare/workers` - Cloudflare Workers
