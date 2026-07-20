"""
Completion Validator
Ensures all sections are complete and properly formatted.
Now ACTIONABLE: auto-fixes minor issues and stores structured data in state.
"""

import re
from typing import Dict, List

# ✅ FIX #6: Import shared auto-fix utilities instead of duplicating the logic.
# Previously this file AND quality_control.py both contained identical code for
# fixing incomplete sentences and removing broken image placeholders.
# That logic now lives in fixes.py — one place to maintain, two places to use.
from Graph.Fixes import apply_all_fixes


def validate_completion(state: dict) -> dict:
    """
    Validates that the blog is complete and properly formatted.
    Auto-fixes minor issues and returns structured data for downstream nodes.
    """
    print("--- ✅ VALIDATING COMPLETENESS ---")

    final_text = state.get("final", "")
    plan = state.get("plan")

    if not plan:
        print("   ⚠️ No plan found")
        return {}

    issues = []

    # 1. Check if all sections exist (H2, H3, or H4)
    expected_sections = len(plan.tasks)
    actual_sections = len(re.findall(r'^#{2,4} ', final_text, re.MULTILINE))

    if actual_sections < expected_sections:
        issues.append({
            "type": "missing_sections",
            "detail": f"Expected {expected_sections}, found {actual_sections}",
            "severity": "high"
        })
        print(f"   ⚠️ Missing {expected_sections - actual_sections} sections")

    # ✅ FIX #6: Replaced ~20 lines of duplicated fix logic with one call.
    final_text, fixes_applied = apply_all_fixes(final_text)

    for fix in fixes_applied:
        print(f"   🔧 {fix}")

    # 2. Check word count
    total_words = len(final_text.split())
    expected_words = sum(task.target_words for task in plan.tasks)
    word_ratio = total_words / expected_words if expected_words > 0 else 1

    if word_ratio < 0.8:
        issues.append({
            "type": "low_word_count",
            "detail": f"{total_words} words (expected ~{expected_words})",
            "severity": "high"
        })
        print(f"   ⚠️ Word count: {total_words}/{expected_words} (low)")
    else:
        print(f"   ✅ Word count: {total_words} words")

    # 3. Compute completion score (0-10)
    score = 10
    if actual_sections < expected_sections:
        score -= min(4, (expected_sections - actual_sections) * 2)
    if word_ratio < 0.8:
        score -= 3
    elif word_ratio < 0.9:
        score -= 1
    score = max(0, score)

    # Generate completion report
    report = "COMPLETION VALIDATION REPORT\n"
    report += "=" * 60 + "\n"
    report += f"Score: {score}/10\n\n"

    if issues:
        report += "⚠️ ISSUES FOUND:\n"
        for i, issue in enumerate(issues, 1):
            report += f"  {i}. [{issue['severity'].upper()}] {issue['detail']}\n"
        report += "\n"

    if fixes_applied:
        report += "🔧 AUTO-FIXES APPLIED:\n"
        for fix in fixes_applied:
            report += f"  • {fix}\n"
        report += "\n"

    if not issues and not fixes_applied:
        report += "✅ Blog is complete and properly formatted!\n"

    report += f"- Total words: {total_words}\n"
    report += f"- Sections: {actual_sections}/{expected_sections}\n"

    print(f"   📊 Completion Score: {score}/10 | Fixes: {len(fixes_applied)} | Issues: {len(issues)}")

    return {
        "completion_report": report,
        "completion_score": score,
        "completion_issues": issues,
        "final": final_text,
    }