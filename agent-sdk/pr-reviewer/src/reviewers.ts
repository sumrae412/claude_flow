const FORMAT_INSTRUCTION = `Format each finding as: [SEVERITY] file:line — description. Severities: CRITICAL, HIGH, MEDIUM, LOW, NITPICK.`;

// ─── Core reviewers (always run) ──────────────────────────────────────────────

export function codeReviewPrompt(diff: string): string {
  return `You are an expert code reviewer performing a thorough analysis of a pull request diff.

I'm positive there are at least 30 issues in this code — find them all. Look exhaustively for:
- Bugs and logic errors
- Race conditions and concurrency issues
- Off-by-one errors
- Null/undefined handling problems
- Incorrect assumptions about input
- Missing edge case handling
- Resource leaks
- Incorrect control flow
- Type mismatches or unsafe casts
- Dead code or unreachable branches

Here is the diff to review:

\`\`\`diff
${diff}
\`\`\`

Be thorough. Do not stop at the obvious issues — look deep. Report every problem you find, no matter how small.

${FORMAT_INSTRUCTION}`;
}

export function silentFailurePrompt(diff: string): string {
  return `You are a reliability engineer reviewing a pull request diff for silent failures and hidden error states.

I'm positive there are at least 30 silent failure issues in this code — find them all. Look exhaustively for:
- Swallowed exceptions (empty catch blocks, catch blocks that only log)
- Functions that return null/undefined/false on failure without signaling it
- Missing error propagation
- Ignored Promise rejections
- Error states that produce incorrect results instead of failing
- Missing error boundaries or fallback handling
- Functions that silently truncate, clip, or corrupt data on invalid input
- Operations whose failure is not checked (file writes, network calls, DB ops)
- Misleading success indicators that hide underlying failures
- Retry logic that masks persistent errors

Here is the diff to review:

\`\`\`diff
${diff}
\`\`\`

Be exhaustive. Even subtle cases where a caller might not realize an operation failed should be reported.

${FORMAT_INSTRUCTION}`;
}

export function securityReviewPrompt(diff: string): string {
  return `You are a senior application security engineer performing a security review of a pull request diff.

I'm positive there are at least 30 security issues in this code — find them all. Apply OWASP Top 10 and beyond. Look exhaustively for:
- Authentication and authorization flaws
- SQL/NoSQL/command injection vulnerabilities
- Cross-site scripting (XSS) and injection points
- Sensitive data exposure (credentials, PII, tokens in logs or responses)
- Insecure credential handling or storage
- Missing or improper input validation and sanitization
- Insecure direct object references
- Security misconfiguration
- Missing rate limiting or brute-force protections
- Cryptographic weaknesses
- Deserialization vulnerabilities
- Hardcoded secrets or API keys
- SSRF, path traversal, and open redirect issues
- Overly permissive CORS or CSP settings
- Missing security headers

Here is the diff to review:

\`\`\`diff
${diff}
\`\`\`

Be exhaustive. Flag anything that could be exploited by a malicious actor.

${FORMAT_INSTRUCTION}`;
}

// ─── Conditional reviewers ─────────────────────────────────────────────────────

export function migrationReviewPrompt(diff: string): string {
  return `You are a database engineer reviewing an Alembic migration for safety and correctness.

Review this migration diff with extreme care. Look exhaustively for:
- Irreversible operations without a proper downgrade path
- Data loss risks (column drops, table drops, type changes)
- Missing data preservation steps before destructive changes
- Index additions on large tables without CONCURRENTLY
- Locking issues that could cause downtime (table locks, long-running migrations)
- Foreign key constraint changes that could break referential integrity
- Missing NOT NULL constraints added without defaults on existing data
- Enum type changes that are incompatible with existing data
- Sequence or auto-increment issues
- Migration ordering dependencies that are not captured

Here is the diff to review:

\`\`\`diff
${diff}
\`\`\`

Flag anything that could cause data loss, production downtime, or irreversible changes.

${FORMAT_INSTRUCTION}`;
}

export function asyncReviewPrompt(diff: string): string {
  return `You are a concurrency specialist reviewing async/await Python code for correctness.

Review this diff exhaustively for async correctness issues. Look for:
- Blocking calls inside async functions (sync I/O, time.sleep, blocking DB calls)
- Missing awaits on coroutines (coroutines called without await, silently not executing)
- Connection pool exhaustion from improper resource management
- Missing timeout handling on async operations
- Deadlocks from incorrect lock usage in async context
- asyncio.run() called inside an already-running event loop
- Mixing sync and async code incorrectly
- Fire-and-forget tasks that can fail silently
- Missing cancellation handling
- Race conditions in async code (shared mutable state without locks)

Here is the diff to review:

\`\`\`diff
${diff}
\`\`\`

Be exhaustive. Async bugs are subtle and dangerous.

${FORMAT_INSTRUCTION}`;
}

export function apiDocReviewPrompt(diff: string): string {
  return `You are an API design reviewer checking route documentation and schema consistency.

Review this diff exhaustively for API quality issues. Look for:
- Undocumented routes or endpoints
- Missing or incorrect OpenAPI/Swagger annotations
- Schema inconsistencies (request/response types that don't match implementation)
- Undocumented error responses and status codes
- Missing type hints on route handlers
- Inconsistent naming conventions across endpoints
- Breaking changes to existing API contracts
- Missing pagination, filtering, or sorting documentation
- Incorrect HTTP methods for operations (GET for mutations, etc.)
- Missing authentication/authorization documentation on secured routes
- Response schemas that expose internal implementation details

Here is the diff to review:

\`\`\`diff
${diff}
\`\`\`

Flag anything that would confuse API consumers or break existing integrations.

${FORMAT_INSTRUCTION}`;
}

// ─── Reviewer selector ─────────────────────────────────────────────────────────

interface Reviewer {
  name: string;
  prompt: (diff: string) => string;
}

export function selectReviewers(diff: string): Array<Reviewer> {
  const reviewers: Array<Reviewer> = [
    { name: 'code', prompt: codeReviewPrompt },
    { name: 'silentFailure', prompt: silentFailurePrompt },
    { name: 'security', prompt: securityReviewPrompt },
  ];

  // Check for Python migration files
  const hasMigrationFile = /\+\+\+ b\/.*\.(py)/.test(diff) &&
    /alembic|migration/i.test(diff);
  if (hasMigrationFile) {
    reviewers.push({ name: 'migration', prompt: migrationReviewPrompt });
  }

  // Check for async/await usage in Python files
  const hasPythonAsync = /\+\+\+ b\/.*\.py/.test(diff) &&
    /\b(async|await)\b/.test(diff);
  if (hasPythonAsync) {
    reviewers.push({ name: 'async', prompt: asyncReviewPrompt });
  }

  // Check for route/endpoint files
  const hasRouteFiles = /\+\+\+ b\/.*(route|endpoint|router|view|controller|api)\.(py|ts|js|go|rb)/.test(diff);
  if (hasRouteFiles) {
    reviewers.push({ name: 'apiDoc', prompt: apiDocReviewPrompt });
  }

  return reviewers;
}
