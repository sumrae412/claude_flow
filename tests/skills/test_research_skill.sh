#!/bin/bash
# tests/skills/test_research_skill.sh
# Validates the research skill structure and prompt templates

set -euo pipefail

SKILL_FILE="skills/research/SKILL.md"
WORKFLOW_FILE="skills/code-creation-workflow/SKILL.md"
ERRORS=0

echo "=== Research Skill Validation ==="

# Test 1: Skill file exists
if [ ! -f "$SKILL_FILE" ]; then
    echo "FAIL: $SKILL_FILE not found"
    ERRORS=$((ERRORS + 1))
else
    echo "PASS: Skill file exists"
fi

# Test 2: Frontmatter is valid
if head -1 "$SKILL_FILE" | grep -q "^---"; then
    echo "PASS: Frontmatter starts correctly"
else
    echo "FAIL: Missing frontmatter delimiter"
    ERRORS=$((ERRORS + 1))
fi

# Test 3: user-invocable is true
if grep -q "user-invocable: true" "$SKILL_FILE"; then
    echo "PASS: Skill is user-invocable"
else
    echo "FAIL: Skill must be user-invocable"
    ERRORS=$((ERRORS + 1))
fi

# Test 4: All 4 researcher types are defined
for researcher in "Codebase Explorer" "External Researcher" "Integration Mapper" "History Analyst"; do
    if grep -q "### $researcher" "$SKILL_FILE"; then
        echo "PASS: $researcher section found"
    else
        echo "FAIL: Missing $researcher section"
        ERRORS=$((ERRORS + 1))
    fi
done

# Test 5: Prompt templates contain required placeholders
for placeholder in "RESEARCH_QUESTION" "FOCUS_DESCRIPTION" "MEMORY_INJECTION_BLOCK"; do
    if grep -q "\[$placeholder\]" "$SKILL_FILE"; then
        echo "PASS: Placeholder [$placeholder] found in prompts"
    else
        echo "FAIL: Missing placeholder [$placeholder]"
        ERRORS=$((ERRORS + 1))
    fi
done

# Test 6: Scratchpad format is documented
if grep -q "### Findings" "$SKILL_FILE" && grep -q "### Open Questions" "$SKILL_FILE" && grep -q "### Connections" "$SKILL_FILE"; then
    echo "PASS: Scratchpad format documented"
else
    echo "FAIL: Incomplete scratchpad format"
    ERRORS=$((ERRORS + 1))
fi

# Test 7: Research brief format is documented
for section in "Key Findings" "Architecture-Relevant Constraints" "Open Risks" "Sources"; do
    if grep -q "## $section" "$SKILL_FILE"; then
        echo "PASS: Research brief section '$section' found"
    else
        echo "FAIL: Missing research brief section '$section'"
        ERRORS=$((ERRORS + 1))
    fi
done

# Test 8: Confidence levels are all defined
for level in "verified" "inferred" "assumed"; do
    if grep -q "\\*\\*$level\\*\\*" "$SKILL_FILE"; then
        echo "PASS: Confidence level '$level' defined"
    else
        echo "FAIL: Missing confidence level '$level'"
        ERRORS=$((ERRORS + 1))
    fi
done

# Test 9: Default researcher selection table exists
if grep -q "Default Researcher Selection" "$SKILL_FILE"; then
    echo "PASS: Default selection table found"
else
    echo "FAIL: Missing default researcher selection table"
    ERRORS=$((ERRORS + 1))
fi

# Test 10: Gap detection criteria documented
if grep -q "Gap Detection" "$SKILL_FILE"; then
    echo "PASS: Gap detection section found"
else
    echo "FAIL: Missing gap detection section"
    ERRORS=$((ERRORS + 1))
fi

# Test 11: Phase 2 integration documented
if grep -q "code-creation-workflow" "$SKILL_FILE"; then
    echo "PASS: Phase 2 integration documented"
else
    echo "FAIL: Missing Phase 2 integration docs"
    ERRORS=$((ERRORS + 1))
fi

# Test 12: Research Team Branch exists in code-creation-workflow
if grep -q "Research Team Branch" "$WORKFLOW_FILE"; then
    echo "PASS: Research Team Branch in code-creation-workflow"
else
    echo "FAIL: Missing Research Team Branch in code-creation-workflow"
    ERRORS=$((ERRORS + 1))
fi

TOTAL=22
PASSED=$((TOTAL - ERRORS))
echo ""
echo "=== Results: $PASSED/$TOTAL passed ==="
if [ $ERRORS -gt 0 ]; then
    echo "FAIL: $ERRORS test(s) failed"
    exit 1
else
    echo "ALL TESTS PASSED"
fi
