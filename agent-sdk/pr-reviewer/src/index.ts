import Anthropic from '@anthropic-ai/sdk';
import { execSync } from 'child_process';
import { selectReviewers } from './reviewers.js';
import { parseFindings, deduplicateFindings, triageFindings } from './triage.js';
import type { Finding } from './triage.js';
import { formatPRComment, postToGitHub } from './github.js';

// ─── Argument parsing ──────────────────────────────────────────────────────────

function parseArgs(): {
  prNumber: number;
  dryRun: boolean;
  maxAgents: number;
} {
  const args = process.argv.slice(2);
  let prNumber: number | null = null;
  let dryRun = false;
  let maxAgents = 6;

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--dry-run') {
      dryRun = true;
    } else if (arg === '--max-agents') {
      const next = args[i + 1];
      if (next && /^\d+$/.test(next)) {
        maxAgents = parseInt(next, 10);
        i++;
      } else {
        console.error('--max-agents requires a numeric argument');
        process.exit(1);
      }
    } else if (/^\d+$/.test(arg)) {
      prNumber = parseInt(arg, 10);
    }
  }

  // Fallback to env var
  if (prNumber === null && process.env.GITHUB_PR_NUMBER) {
    const envNum = parseInt(process.env.GITHUB_PR_NUMBER, 10);
    if (!isNaN(envNum)) prNumber = envNum;
  }

  if (prNumber === null) {
    console.error(
      'Usage: node dist/index.js <PR_NUMBER> [--dry-run] [--max-agents N]\n' +
      'Or set GITHUB_PR_NUMBER env var.'
    );
    process.exit(1);
  }

  return { prNumber, dryRun, maxAgents };
}

// ─── Small PR combined prompt ─────────────────────────────────────────────────

function combinedSmallPRPrompt(diff: string): string {
  return `You are a thorough code reviewer. This is a small PR diff (under 50 lines). Review it comprehensively for bugs, security issues, silent failures, and any other problems.

Here is the diff:

\`\`\`diff
${diff}
\`\`\`

Format each finding as: [SEVERITY] file:line — description. Severities: CRITICAL, HIGH, MEDIUM, LOW, NITPICK.`;
}

// ─── Main ──────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const { prNumber, dryRun, maxAgents } = parseArgs();

  // Fetch the PR diff
  let diff: string;
  try {
    diff = execSync(`gh pr diff ${prNumber}`, { encoding: 'utf8' });
  } catch (err) {
    console.error(`Failed to fetch diff for PR #${prNumber}:`, err);
    process.exit(1);
  }

  const diffLines = diff.split('\n').length;
  console.log(`PR #${prNumber}: ${diffLines} lines in diff`);

  const client = new Anthropic();
  const allFindings: Finding[] = [];

  // Small PR shortcut: single combined prompt
  if (diffLines < 50) {
    console.log('Small PR detected — using single combined reviewer');
    try {
      const response = await client.messages.create({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 4096,
        messages: [{ role: 'user', content: combinedSmallPRPrompt(diff) }],
      });

      const text = response.content
        .filter((block) => block.type === 'text')
        .map((block) => (block as { type: 'text'; text: string }).text)
        .join('\n');

      const findings = parseFindings('combined', text);
      allFindings.push(...findings);
      console.log(`  combined: ${findings.length} findings`);
    } catch (err) {
      console.error('Anthropic API error (combined reviewer):', err);
    }
  } else {
    // Full pipeline: select reviewers
    let reviewers = selectReviewers(diff);
    console.log(
      `Selected reviewers: ${reviewers.map((r) => r.name).join(', ')}`
    );

    // Cap to maxAgents — if over limit, fall back to core 3 only
    if (reviewers.length > maxAgents) {
      console.warn(
        `Reviewer count (${reviewers.length}) exceeds maxAgents (${maxAgents}), truncating to core 3`
      );
      reviewers = reviewers.slice(0, 3);
    }

    // Run all reviewers in parallel
    const reviewerPromises = reviewers.map(async (reviewer) => {
      try {
        console.log(`  Running reviewer: ${reviewer.name}`);
        const response = await client.messages.create({
          model: 'claude-sonnet-4-20250514',
          max_tokens: 4096,
          messages: [{ role: 'user', content: reviewer.prompt(diff) }],
        });

        const text = response.content
          .filter((block) => block.type === 'text')
          .map((block) => (block as { type: 'text'; text: string }).text)
          .join('\n');

        const findings = parseFindings(reviewer.name, text);
        console.log(`  ${reviewer.name}: ${findings.length} findings`);
        return findings;
      } catch (err) {
        console.error(`Anthropic API error (${reviewer.name}):`, err);
        return [] as Finding[];
      }
    });

    const results = await Promise.all(reviewerPromises);
    for (const findings of results) {
      allFindings.push(...findings);
    }
  }

  // Deduplicate and triage
  const deduped = deduplicateFindings(allFindings);
  const triaged = triageFindings(deduped);

  console.log(
    `Findings — CRITICAL: ${triaged.critical.length}, HIGH: ${triaged.high.length}, ` +
    `MEDIUM: ${triaged.medium.length}, LOW: ${triaged.low.length}, NITPICK: ${triaged.nitpick.length}`
  );

  const reviewerCount = diffLines < 50 ? 1 : Math.min(
    selectReviewers(diff).length,
    maxAgents
  );
  const comment = formatPRComment(triaged, reviewerCount);

  if (dryRun) {
    console.log('\n─── PR Comment (dry run) ───\n');
    console.log(comment);
  } else {
    const hasCritical = triaged.critical.length > 0;
    try {
      await postToGitHub(prNumber, comment, hasCritical);
      console.log('Comment posted to GitHub.');
    } catch (err) {
      console.error('Failed to post to GitHub, printing comment instead:', err);
      console.log('\n─── PR Comment ───\n');
      console.log(comment);
    }
  }

  // Exit 1 if any CRITICAL findings
  if (triaged.critical.length > 0) {
    process.exit(1);
  }
}

main().catch((err) => {
  console.error('Unhandled error:', err);
  process.exit(1);
});
