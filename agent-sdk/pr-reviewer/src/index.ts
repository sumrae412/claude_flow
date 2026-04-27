import { execSync } from 'child_process';
import { deduplicateFindings, triageFindings } from './triage.js';
import { formatPRComment, postToGitHub } from './github.js';
import { getModelClient } from './model-client.js';
import { runReview } from './review.js';

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

// ─── Main ──────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const { prNumber, dryRun, maxAgents } = parseArgs();

  let diff: string;
  try {
    diff = execSync(`gh pr diff ${prNumber}`, { encoding: 'utf8' });
  } catch (err) {
    console.error(`Failed to fetch diff for PR #${prNumber}:`, err);
    process.exit(1);
  }

  const client = getModelClient();
  console.log(`PR #${prNumber}: ${diff.split('\n').length} lines in diff`);
  console.log(`Provider: ${client.providerName} (${client.modelId})`);

  const { findings, reviewerCount } = await runReview(diff, client, { maxAgents });

  const deduped = deduplicateFindings(findings);
  const triaged = triageFindings(deduped);

  console.log(
    `Findings — CRITICAL: ${triaged.critical.length}, HIGH: ${triaged.high.length}, ` +
    `MEDIUM: ${triaged.medium.length}, LOW: ${triaged.low.length}, NITPICK: ${triaged.nitpick.length}`
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
