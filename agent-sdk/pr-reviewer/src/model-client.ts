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

  private readonly dispatcher: Agent;

  constructor() {
    const apiKey = process.env.NVIDIA_API_KEY;
    if (!apiKey) {
      throw new Error(
        'NVIDIA_API_KEY is required when PR_REVIEWER_PROVIDER=nvidia. ' +
        'Get one at https://build.nvidia.com/',
      );
    }
    const modelId = process.env.NVIDIA_MODEL;
    if (!modelId) {
      throw new Error(
        'NVIDIA_MODEL is required when PR_REVIEWER_PROVIDER=nvidia. ' +
        'Browse available models at https://build.nvidia.com/models. ' +
        'Coding-capable picks: deepseek-ai/deepseek-v3 or moonshotai/kimi-k2.',
      );
    }
    this.apiKey = apiKey;
    this.modelId = modelId;
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
  }

  async createReview(system: string, user: string): Promise<ReviewResponse> {
    const res = await undiciFetch(`${this.baseUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'claude-flow-pr-reviewer/0.1',
      },
      body: JSON.stringify({
        model: this.modelId,
        max_tokens: this.maxTokens,
        messages: [
          { role: 'system', content: system },
          { role: 'user', content: user },
        ],
      }),
      dispatcher: this.dispatcher,
    });

    if (!res.ok) {
      const body = await res.text().catch(() => '');
      throw new Error(`NVIDIA API error ${res.status}: ${body.slice(0, 500)}`);
    }

    const data = (await res.json()) as OpenAIChatResponse;
    if (data.error?.message) {
      throw new Error(`NVIDIA API error: ${data.error.message}`);
    }

    const text = data.choices?.[0]?.message?.content ?? '';
    return {
      text,
      usage: { input_tokens: data.usage?.prompt_tokens ?? null },
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
