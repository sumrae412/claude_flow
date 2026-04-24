export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'NITPICK';

export interface Finding {
  severity: Severity;
  file: string;
  line: number | null;
  description: string;
  reviewer: string;
  // Populated by deduplicateFindings when two or more raw findings collapse
  // into one: the list of source reviewer labels (each entry is the
  // `reviewer` value of a raw finding that contributed). Size 1 = no merge
  // happened; size N>1 = this represents consensus across N sources. Useful
  // as a confidence signal — findings flagged by multiple reviewers or
  // models are higher-signal than single-source findings.
  mergedFrom?: string[];
}

const SEVERITY_RANK: Record<Severity, number> = {
  CRITICAL: 5,
  HIGH: 4,
  MEDIUM: 3,
  LOW: 2,
  NITPICK: 1,
};

// Matches: [SEVERITY] file:line — description
// The em dash separator can be — (U+2014) or -- or -
const FINDING_PATTERN = /^\[(?<severity>CRITICAL|HIGH|MEDIUM|LOW|NITPICK)\]\s+(?<file>[^\s:]+):(?<line>\d+|null|N\/A|\?+)?\s*[—\-–]+\s*(?<description>.+)$/;

export function parseFindings(reviewerName: string, output: string): Finding[] {
  const findings: Finding[] = [];

  for (const rawLine of output.split('\n')) {
    const line = rawLine.trim();
    if (!line) continue;

    const match = FINDING_PATTERN.exec(line);
    if (!match || !match.groups) continue;

    const { severity, file, line: lineStr, description } = match.groups;

    let lineNum: number | null = null;
    if (lineStr && /^\d+$/.test(lineStr)) {
      lineNum = parseInt(lineStr, 10);
    }

    findings.push({
      severity: severity as Severity,
      file: file.trim(),
      line: lineNum,
      description: description.trim(),
      reviewer: reviewerName,
    });
  }

  return findings;
}

// Stopwords stripped before similarity scoring. Common conjunctions, articles,
// and weak verbs that inflate set sizes without carrying semantic signal.
// Intentionally small — we want to keep domain words like "error", "null",
// "async", "trigger".
const STOPWORDS = new Set([
  'the', 'a', 'an', 'and', 'or', 'but', 'of', 'to', 'in', 'is', 'it', 'this',
  'that', 'on', 'at', 'by', 'for', 'with', 'as', 'be', 'will', 'can', 'not',
  'no', 'yes', 'has', 'have', 'had', 'are', 'was', 'were', 'been', 'being',
  'which', 'who', 'what', 'when', 'where', 'why', 'how', 'do', 'does', 'did',
  'if', 'then', 'else', 'so', 'than', 'also', 'too', 'just', 'only', 'its',
  'from', 'into', 'out', 'up', 'down', 'over', 'under', 'should', 'could',
  'would', 'may', 'might', 'must', 'shall',
]);

// Light stemmer: strips common English suffixes so "automatic", "automatically",
// and "automation" all collapse to the same stem. Not Porter — just enough to
// catch paraphrase-induced morphology gaps that otherwise tank Dice scores.
function lightStem(w: string): string {
  // Order matters: longer suffixes first.
  return w
    .replace(/(?:ically|ational|ations|ication|atively|ments|ment|ness|ing|ers|ion|ies|ed|ly|es|s|y)$/, '')
    .replace(/(?:^.{2,})al$/, (_, m) => m); // strip trailing "al" only if stem ≥ 2 chars
}

function tokenize(s: string): Set<string> {
  return new Set(
    s
      .toLowerCase()
      // Split on non-alphanumerics AND underscores so `workflow_dispatch`
      // contributes two tokens.
      .replace(/[^a-z0-9]/g, ' ')
      .split(/\s+/)
      .filter((w) => w.length > 2 && !STOPWORDS.has(w))
      .map(lightStem)
      .filter((w) => w.length > 2),
  );
}

// Sørensen–Dice coefficient: 2|A∩B| / (|A|+|B|). More forgiving than Jaccard
// for verbose paraphrases where different models pad the same observation
// with different boilerplate. 1.0 = identical token sets, 0.0 = disjoint.
function diceCoefficient(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 && b.size === 0) return 1;
  if (a.size === 0 || b.size === 0) return 0;
  let intersect = 0;
  for (const x of a) if (b.has(x)) intersect++;
  return (2 * intersect) / (a.size + b.size);
}

// Threshold picked empirically against ensemble output on PR #45 after light
// stemming. Different models rephrase the same "push trigger removed" issue
// with Dice scores around 0.25–0.40 against each other. 0.25 catches those
// paraphrases while still treating distinct issues on the same line as
// separate findings. Overridable via DEDUP_SIMILARITY_THRESHOLD for tuning.
const DEFAULT_SIMILARITY_THRESHOLD = 0.25;

export function deduplicateFindings(findings: Finding[]): Finding[] {
  const threshold = parseFloat(
    process.env.DEDUP_SIMILARITY_THRESHOLD ?? String(DEFAULT_SIMILARITY_THRESHOLD),
  );
  const deduplicated: Finding[] = [];
  // Cache token sets so we only tokenize each description once.
  const tokenCache = new Map<string, Set<string>>();
  const getTokens = (f: Finding): Set<string> => {
    let t = tokenCache.get(f.description);
    if (!t) { t = tokenize(f.description); tokenCache.set(f.description, t); }
    return t;
  };

  for (const candidate of findings) {
    let isDuplicate = false;
    const candTokens = getTokens(candidate);

    for (let i = 0; i < deduplicated.length; i++) {
      const existing = deduplicated[i];

      // Same file check
      if (existing.file !== candidate.file) continue;

      // Line proximity check: within 3 lines (or both null)
      const lineClose =
        existing.line === null && candidate.line === null
          ? true
          : existing.line !== null && candidate.line !== null
          ? Math.abs(existing.line - candidate.line) <= 3
          : false;

      if (!lineClose) continue;

      // Semantic similarity on descriptions (Dice over significant tokens).
      const score = diceCoefficient(getTokens(existing), candTokens);
      if (score < threshold) continue;

      // It's a duplicate — keep the higher-severity finding but merge the
      // provenance lists so downstream can show "found by N sources".
      isDuplicate = true;
      const existingProv = existing.mergedFrom ?? [existing.reviewer];
      const candidateProv = candidate.mergedFrom ?? [candidate.reviewer];
      const combinedProv = Array.from(new Set([...existingProv, ...candidateProv]));
      if (SEVERITY_RANK[candidate.severity] > SEVERITY_RANK[existing.severity]) {
        deduplicated[i] = { ...candidate, mergedFrom: combinedProv };
      } else {
        deduplicated[i] = { ...existing, mergedFrom: combinedProv };
      }
      break;
    }

    if (!isDuplicate) {
      // First time we see this finding — start its provenance list with its
      // own reviewer label.
      deduplicated.push({
        ...candidate,
        mergedFrom: candidate.mergedFrom ?? [candidate.reviewer],
      });
    }
  }

  return deduplicated;
}

export interface TriagedFindings {
  critical: Finding[];
  high: Finding[];
  medium: Finding[];
  low: Finding[];
  nitpick: Finding[];
}

export function triageFindings(findings: Finding[]): TriagedFindings {
  const result: TriagedFindings = {
    critical: [],
    high: [],
    medium: [],
    low: [],
    nitpick: [],
  };

  for (const finding of findings) {
    switch (finding.severity) {
      case 'CRITICAL':
        result.critical.push(finding);
        break;
      case 'HIGH':
        result.high.push(finding);
        break;
      case 'MEDIUM':
        result.medium.push(finding);
        break;
      case 'LOW':
        result.low.push(finding);
        break;
      case 'NITPICK':
        result.nitpick.push(finding);
        break;
    }
  }

  return result;
}
