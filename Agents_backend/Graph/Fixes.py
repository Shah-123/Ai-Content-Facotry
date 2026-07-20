"""
fixes.py — Shared Auto-Fix Utilities
=====================================
Extracted from completion_validator.py and quality_control.py.

Previously both files contained identical logic for:
  - Auto-fixing incomplete sentences (missing trailing punctuation)
  - Removing broken [[IMAGE_X]] placeholders

Having it in two places meant a bug fix in one left the other broken.
Both files now import from here instead.
"""

import re
from typing import Tuple, List


def fix_incomplete_sentences(text: str) -> Tuple[str, List[str]]:
    """
    Scans every paragraph and appends a period to any that end without
    proper punctuation. Skips image blocks and headings.

    Returns:
        (fixed_text, list_of_fix_descriptions)
    """
    paragraphs = text.split('\n\n')
    fixed_paragraphs = []
    fixes_applied = []

    for i, para in enumerate(paragraphs):
        original = para
        para_stripped = para.strip()

        # Skip image markdown and headers — they never need a trailing period
        if para_stripped.startswith('![') or para_stripped.startswith('#'):
            fixed_paragraphs.append(original)
            continue

        # Strip inline markdown formatting before checking the last character
        clean_para = para_stripped.strip('*_` ')

        if clean_para and len(clean_para) > 50:
            if not clean_para.endswith(('.', '!', '?', '"', ')')):
                fixed_paragraphs.append(para.rstrip() + ".")
                fixes_applied.append(f"Added missing period to paragraph {i + 1}")
                continue

        fixed_paragraphs.append(original)

    return '\n\n'.join(fixed_paragraphs), fixes_applied


def fix_broken_image_placeholders(text: str) -> Tuple[str, List[str]]:
    """
    Removes any leftover [[IMAGE_N]] placeholders that were never
    replaced with real image markdown.

    Returns:
        (fixed_text, list_of_fix_descriptions)
    """
    broken = re.findall(r'\[\[IMAGE_\d+\]\]', text)
    fixes_applied = []

    if broken:
        text = re.sub(r'\[\[IMAGE_\d+\]\]\n?', '', text)
        fixes_applied.append(f"Removed {len(broken)} broken image placeholder(s)")

    return text, fixes_applied


def apply_all_fixes(text: str) -> Tuple[str, List[str]]:
    """
    Convenience wrapper — runs all auto-fixes in the correct order
    and returns the cleaned text plus a combined list of applied fixes.

    Usage:
        final_text, fixes = apply_all_fixes(raw_text)
    """
    all_fixes: List[str] = []

    text, fixes = fix_incomplete_sentences(text)
    all_fixes.extend(fixes)

    text, fixes = fix_broken_image_placeholders(text)
    all_fixes.extend(fixes)

    return text, all_fixes