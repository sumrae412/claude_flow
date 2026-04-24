// Each reviewer is split into (system, user) so the static system prompt can be
// marked with `cache_control: { type: "ephemeral" }` at the call site. This gives
// a ~90% discount on the system portion when the same reviewer runs within the
// cache TTL (5 minutes by default). See index.ts for the cache_control wiring.
//
// Prompt variants:
// - `system`: aggressive overshoot framing ("I'm positive there are at least 30
//   issues — find them all"). Proven to improve recall on Anthropic models.
// - `systemSoft`: neutral variant without the overshoot framing. Required for
//   NVIDIA's free-tier gateway, which either filters or severely throttles the
//   aggressive variant (verified 2026-04-24: aggressive = >120s timeout, soft
//   = 81s HTTP 200). See CLAUDE.md "PR reviewer is provider-pluggable".

const FORMAT_INSTRUCTION = `Format each finding as: [SEVERITY] file:line — description. Severities: CRITICAL, HIGH, MEDIUM, LOW, NITPICK.`;

function userMessage(diff: string): string {
  return `Here is the diff to review:\n\n\`\`\`diff\n${diff}\n\`\`\``;
}

// ─── Core reviewers (always run) ──────────────────────────────────────────────

const CODE_REVIEW_SYSTEM = `You are an expert code reviewer performing a thorough analysis of a pull request diff.

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

Be thorough. Do not stop at the obvious issues — look deep. Report every problem you find, no matter how small.

${FORMAT_INSTRUCTION}`;

const CODE_REVIEW_SYSTEM_SOFT = `You are an expert code reviewer performing a thorough analysis of a pull request diff.

Review the diff for:
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

${FORMAT_INSTRUCTION}`;

const SILENT_FAILURE_SYSTEM = `You are a reliability engineer reviewing a pull request diff for silent failures and hidden error states.

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

Be exhaustive. Even subtle cases where a caller might not realize an operation failed should be reported.

${FORMAT_INSTRUCTION}`;

const SILENT_FAILURE_SYSTEM_SOFT = `You are a reliability engineer reviewing a pull request diff for silent failures and hidden error states.

Review the diff for:
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

${FORMAT_INSTRUCTION}`;

const SECURITY_REVIEW_SYSTEM = `You are a senior application security engineer performing a security review of a pull request diff.

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

Be exhaustive. Flag anything that could be exploited by a malicious actor.

${FORMAT_INSTRUCTION}`;

const SECURITY_REVIEW_SYSTEM_SOFT = `You are a senior application security engineer performing a security review of a pull request diff.

Apply OWASP Top 10 and beyond. Review the diff for:
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

${FORMAT_INSTRUCTION}`;

// ─── Conditional reviewers ─────────────────────────────────────────────────────

const MIGRATION_REVIEW_SYSTEM = `You are a database engineer reviewing an Alembic migration for safety and correctness.

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

Flag anything that could cause data loss, production downtime, or irreversible changes.

${FORMAT_INSTRUCTION}`;

const ASYNC_REVIEW_SYSTEM = `You are a concurrency specialist reviewing async/await Python code for correctness.

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

Be exhaustive. Async bugs are subtle and dangerous.

${FORMAT_INSTRUCTION}`;

const API_DOC_REVIEW_SYSTEM = `You are an API design reviewer checking route documentation and schema consistency.

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

Flag anything that would confuse API consumers or break existing integrations.

${FORMAT_INSTRUCTION}`;

// ─── Reviewer selector ─────────────────────────────────────────────────────────

export interface Reviewer {
  name: string;
  system: string;
  // Optional soft variant for providers whose gateways filter/throttle the
  // aggressive overshoot framing (e.g. NVIDIA free tier). Falls back to `system`.
  systemSoft?: string;
  userMessage: (diff: string) => string;
}

function make(name: string, system: string, systemSoft?: string): Reviewer {
  return { name, system, systemSoft, userMessage };
}

// Pick the appropriate system prompt for a given client preference.
export function pickSystem(reviewer: Reviewer, preferSoft: boolean): string {
  if (preferSoft && reviewer.systemSoft) return reviewer.systemSoft;
  return reviewer.system;
}

export function selectReviewers(diff: string): Array<Reviewer> {
  const reviewers: Array<Reviewer> = [
    make('code', CODE_REVIEW_SYSTEM, CODE_REVIEW_SYSTEM_SOFT),
    make('silentFailure', SILENT_FAILURE_SYSTEM, SILENT_FAILURE_SYSTEM_SOFT),
    make('security', SECURITY_REVIEW_SYSTEM, SECURITY_REVIEW_SYSTEM_SOFT),
  ];

  const hasMigrationFile = /\+\+\+ b\/.*\.(py)/.test(diff) &&
    /alembic|migration/i.test(diff);
  if (hasMigrationFile) {
    // Deterministic-scope reviewers (migration/async/apiDoc) don't use the
    // overshoot framing, so no soft variant needed — `system` is already neutral.
    reviewers.push(make('migration', MIGRATION_REVIEW_SYSTEM));
  }

  const hasPythonAsync = /\+\+\+ b\/.*\.py/.test(diff) &&
    /\b(async|await)\b/.test(diff);
  if (hasPythonAsync) {
    reviewers.push(make('async', ASYNC_REVIEW_SYSTEM));
  }

  const hasRouteFiles = /\+\+\+ b\/.*(route|endpoint|router|view|controller|api)\.(py|ts|js|go|rb)/.test(diff);
  if (hasRouteFiles) {
    reviewers.push(make('apiDoc', API_DOC_REVIEW_SYSTEM));
  }

  return reviewers;
}

// Combined reviewer for small PRs. Split the same way so the static portion caches.
export const COMBINED_SMALL_PR_SYSTEM = `You are a thorough code reviewer. This is a small PR diff (under 50 lines). Review it comprehensively for bugs, security issues, silent failures, and any other problems.

${FORMAT_INSTRUCTION}`;

export function combinedSmallPRUserMessage(diff: string): string {
  return userMessage(diff);
}
