import Anthropic from '@anthropic-ai/sdk';
import { Agent, fetch as undiciFetch } from 'undici';

// Shared response shape. `usage` mirrors Anthropic's prompt-cache fields so the
// existing logCacheUsage() helper in index.ts keeps working; non-Anthropic
// providers leave those fields undefined and the helper no-ops.
export interface ReviewResponse {
  text: string;
  usage?: {
    cache_creation_input_tokens?: number | null;
    cache_read_input_tokens?: number | null;
    input_tokens?: number | null;
  };
}

export interface ModelClient {
  readonly providerName: string;
  readonly modelId: string;
  // True for providers whose gateways filter/throttle aggressive overshoot
  // framing (e.g. NVIDIA free tier). Reviewer-selection code uses this to pick
  // `reviewer.systemSoft` over `reviewer.system`. See reviewers.ts.
  readonly preferSoftPrompts: boolean;
  createReview(system: string, user: string): Promise<ReviewResponse>;
}

// ─── Anthropic (default, preserves prompt caching) ────────────────────────────

class AnthropicModelClient implements ModelClient {
  readonly providerName = 'anthropic';
  readonly modelId: string;
  readonly preferSoftPrompts = false;
  private readonly client: Anthropic;
  private readonly maxTokens: number;

  constructor() {
    this.client = new Anthropic();
    this.modelId = process.env.ANTHROPIC_MODEL ?? 'claude-sonnet-4-20250514';
    this.maxTokens = parseInt(process.env.ANTHROPIC_MAX_TOKENS ?? '4096', 10);
  }

  async createReview(system: string, user: string): Promise<ReviewResponse> {
    const response = await this.client.messages.create({
      model: this.modelId,
      max_tokens: this.maxTokens,
      system: [
        { type: 'text', text: system, cache_control: { type: 'ephemeral' } },
      ],
      messages: [{ role: 'user', content: user }],
    });

    const text = response.content
      .filter((block) => block.type === 'text')
      .map((block) => (block as { type: 'text'; text: string }).text)
      .join('\n');

    return { text, usage: response.usage };
  }
}

// ─── NVIDIA (OpenAI-compatible, free tier) ────────────────────────────────────

interface OpenAIChatResponse {
  choices?: Array<{ message?: { content?: string | null } }>;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
  error?: { message?: string };
}

class NvidiaModelClient implements ModelClient {
  readonly providerName = 'nvidia';
  readonly modelId: string;
  // NVIDIA's free-tier gateway filters/throttles the aggressive overshoot
  // framing ("find at least 30 issues..."). Confirmed 2026-04-24: aggressive
  // timed out >120s; soft variant returned 200 in 81s for an identical diff.
  readonly preferSoftPrompts = true;
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly maxTokens: number;
  // Pool of model IDs. Length 1 = single-model mode. Length >1 = ensemble
  // fan-out (A+C pattern): each createReview call dispatches to every model
  // in parallel with a per-call AbortSignal timeout, then merges successful
  // responses. Partial success is fine — the existing triage.ts dedup
  // collapses overlapping findings. Fails only if every model errors/times out.
  private readonly modelPool: string[];
  private readonly perCallTimeoutMs: number;
  // After the first successful model in an ensemble returns, slower models get
  // this many ms of grace to also finish — then remaining in-flight requests
  // are aborted and we return whatever succeeded. Keeps wall time ≈
  // `time_to_first_success + graceMs` instead of the slowest survivor.
  private readonly graceMs: number;
  private readonly dispatcher: Agent;

  constructor() {
    const apiKey = process.env.NVIDIA_API_KEY;
    if (!apiKey) {
      throw new Error(
        'NVIDIA_API_KEY is required when PR_REVIEWER_PROVIDER=nvidia. ' +
        'Get one at https://build.nvidia.com/',
      );
    }
    const poolRaw = process.env.NVIDIA_MODEL_POOL?.trim();
    const singleRaw = process.env.NVIDIA_MODEL?.trim();
    const pool = poolRaw
      ? poolRaw.split(',').map((s) => s.trim()).filter(Boolean)
      : singleRaw
      ? [singleRaw]
      : [];
    if (pool.length === 0) {
      throw new Error(
        'NVIDIA_MODEL or NVIDIA_MODEL_POOL is required when PR_REVIEWER_PROVIDER=nvidia. ' +
        'Browse available models with: curl -sH "Authorization: Bearer $NVIDIA_API_KEY" ' +
        'https://integrate.api.nvidia.com/v1/models | jq \'.data[].id\'. ' +
        'Verified working 2026-04-24: moonshotai/kimi-k2-instruct-0905. ' +
        'Set NVIDIA_MODEL_POOL=m1,m2,m3 for ensemble fan-out.',
      );
    }
    this.apiKey = apiKey;
    this.modelPool = pool;
    this.modelId = pool.length === 1 ? pool[0] : `pool:${pool.join(',')}`;
    this.baseUrl = process.env.NVIDIA_BASE_URL ?? 'https://integrate.api.nvidia.com/v1';
    this.maxTokens = parseInt(process.env.NVIDIA_MAX_TOKENS ?? '4096', 10);
    // NVIDIA free-tier latency routinely exceeds undici's 300s default
    // headersTimeout for larger-context generations (verified: MiniMax M2.7
    // on a 44-line diff consistently hit 5:02 timeout). Extend to 15 min.
    const timeoutMs = parseInt(process.env.NVIDIA_TIMEOUT_MS ?? '900000', 10);
    this.dispatcher = new Agent({
      headersTimeout: timeoutMs,
      bodyTimeout: timeoutMs,
    });
    // Per-call ceiling for ensemble mode. Slow models get abandoned so a
    // 504-bound model doesn't block the whole ensemble. Sit just below
    // NVIDIA's observed ~5-min edge timeout so we bail client-side first
    // with a clean label instead of waiting for their 504.
    this.perCallTimeoutMs = parseInt(
      process.env.NVIDIA_PER_CALL_TIMEOUT_MS ?? '240000',
      10,
    );
    this.graceMs = parseInt(process.env.NVIDIA_ENSEMBLE_GRACE_MS ?? '30000', 10);
  }

  private async callModel(
    model: string,
    system: string,
    user: string,
    parentSignal?: AbortSignal,
  ): Promise<ReviewResponse> {
    // Abort on whichever fires first: per-call timeout, or parent (ensemble
    // grace expiry). AbortSignal.any needs Node 20+; this repo requires 22.
    const perCall = AbortSignal.timeout(this.perCallTimeoutMs);
    const signal = parentSignal
      ? AbortSignal.any([perCall, parentSignal])
      : perCall;

    const res = await undiciFetch(`${this.baseUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'claude-flow-pr-reviewer/0.1',
      },
      body: JSON.stringify({
        model,
        max_tokens: this.maxTokens,
        messages: [
          { role: 'system', content: system },
          { role: 'user', content: user },
        ],
      }),
      dispatcher: this.dispatcher,
      signal,
    });

    if (!res.ok) {
      const body = await res.text().catch(() => '');
      throw new Error(`${res.status}: ${body.slice(0, 200)}`);
    }

    const data = (await res.json()) as OpenAIChatResponse;
    if (data.error?.message) {
      throw new Error(data.error.message);
    }

    const text = data.choices?.[0]?.message?.content ?? '';
    return {
      text,
      usage: { input_tokens: data.usage?.prompt_tokens ?? null },
    };
  }

  async createReview(system: string, user: string): Promise<ReviewResponse> {
    // Single-model path — keep simple, no ensemble overhead.
    if (this.modelPool.length === 1) {
      return this.callModel(this.modelPool[0], system, user);
    }

    // Ensemble with early-exit: fire all in parallel. Once the first model
    // succeeds, the remaining in-flight calls get `graceMs` to also finish,
    // then we abort them. Net wall time ≈ time_to_first_success + graceMs.
    const graceController = new AbortController();
    type SlotResult =
      | { model: string; ok: true; response: ReviewResponse }
      | { model: string; ok: false; error: string };

    const tracked: Promise<SlotResult>[] = this.modelPool.map((m) =>
      this.callModel(m, system, user, graceController.signal)
        .then((response): SlotResult => ({ model: m, ok: true, response }))
        .catch((e): SlotResult => ({
          model: m,
          ok: false,
          error: e instanceof Error ? e.message : String(e),
        })),
    );

    // Wait for first success, OR for all to settle (all-fail case).
    const firstSuccessOrAllDone = new Promise<void>((resolve) => {
      let remaining = tracked.length;
      let resolved = false;
      const maybeResolve = () => {
        if (!resolved) { resolved = true; resolve(); }
      };
      tracked.forEach((p) =>
        p.then((r) => {
          if (r.ok) maybeResolve();
          if (--remaining === 0) maybeResolve();
        }),
      );
    });
    await firstSuccessOrAllDone;

    // After first success, let stragglers finish within graceMs, then abort.
    await Promise.race([
      Promise.allSettled(tracked),
      new Promise<void>((resolve) => setTimeout(resolve, this.graceMs).unref?.()),
    ]);
    graceController.abort();
    // Make sure every promise settles before reading their results.
    const settled = await Promise.all(tracked);

    const successes = settled.filter((r): r is Extract<SlotResult, { ok: true }> => r.ok);
    const failures = settled.filter((r): r is Extract<SlotResult, { ok: false }> => !r.ok);

    // Log ensemble breakdown once per createReview so index.ts output stays
    // readable. Format: "ensemble N/M ok (failed: model=reason, ...)".
    const summary = `ensemble ${successes.length}/${this.modelPool.length} ok` +
      (failures.length > 0
        ? ` (failed: ${failures.map((f) => `${f.model}=${f.error.slice(0, 60)}`).join('; ')})`
        : '');
    console.log(`    ${summary}`);

    if (successes.length === 0) {
      throw new Error(
        `All ${this.modelPool.length} models in ensemble failed. ` +
        failures.map((f) => `${f.model}: ${f.error}`).join(' | '),
      );
    }

    // Merge: concatenate text with a separator that preserves provenance in
    // logs but doesn't affect parseFindings (which scans line-by-line for
    // [SEVERITY] markers). Sum input_tokens across successes.
    const mergedText = successes
      .map((s) => `\n--- from ${s.model} ---\n${s.response.text}`)
      .join('\n');
    const totalInputTokens = successes.reduce(
      (sum, s) => sum + (s.response.usage?.input_tokens ?? 0),
      0,
    );
    return {
      text: mergedText,
      usage: { input_tokens: totalInputTokens || null },
    };
  }
}

// ─── Factory ──────────────────────────────────────────────────────────────────

export function getModelClient(): ModelClient {
  const provider = (process.env.PR_REVIEWER_PROVIDER ?? 'anthropic').toLowerCase();
  switch (provider) {
    case 'anthropic':
      return new AnthropicModelClient();
    case 'nvidia':
      return new NvidiaModelClient();
    default:
      throw new Error(
        `Unknown PR_REVIEWER_PROVIDER='${provider}'. Supported: anthropic, nvidia.`,
      );
  }
}
