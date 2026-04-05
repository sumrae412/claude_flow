export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'NITPICK';

export interface Finding {
  severity: Severity;
  file: string;
  line: number | null;
  description: string;
  reviewer: string;
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

export function deduplicateFindings(findings: Finding[]): Finding[] {
  const deduplicated: Finding[] = [];

  for (const candidate of findings) {
    let isDuplicate = false;

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

      // Similar description: first 50 chars match
      const existingDesc = existing.description.slice(0, 50).toLowerCase();
      const candidateDesc = candidate.description.slice(0, 50).toLowerCase();

      if (existingDesc !== candidateDesc) continue;

      // It's a duplicate — keep higher severity
      isDuplicate = true;
      if (SEVERITY_RANK[candidate.severity] > SEVERITY_RANK[existing.severity]) {
        deduplicated[i] = { ...candidate };
      }
      break;
    }

    if (!isDuplicate) {
      deduplicated.push({ ...candidate });
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
