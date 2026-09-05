"""Regression coverage for the mobile layout bug: on phones, every authenticated page was
pushed sideways by an unconditional `.app-main{margin-left:256px}` rule that had the same CSS
specificity as, and came after in source order, the original mobile reset — so it silently won
the cascade at every viewport width, leaving a permanent blank strip on the left (reserved for
the visually off-canvas sidebar) with page content cut off on the right.

These tests parse the actual shipped stylesheet/template text rather than spinning up a browser,
so they run without any extra runtime dependency and fail loudly if a future edit reintroduces
the same "later unconditional rule beats the earlier mobile reset" mistake for `.app-main` or
`.sidebar`, or if the viewport meta tag / mobile-specific rules disappear.
"""
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STYLE_CSS = (PROJECT_ROOT / "app" / "static" / "style.css").read_text(encoding="utf-8")
BASE_HTML = (PROJECT_ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")


def _all_declarations(selector: str) -> list[str]:
    """Every `{...}` declaration block for an exact, standalone `selector` in source order."""
    pattern = re.compile(re.escape(selector) + r"\{([^}]*)\}")
    return pattern.findall(STYLE_CSS)


def test_viewport_meta_tag_present():
    assert '<meta name="viewport" content="width=device-width,initial-scale=1">' in BASE_HTML


def test_app_main_margin_left_last_declaration_resets_to_zero():
    """CSS applies same-specificity rules in source order, so whichever `.app-main{margin-left:
    ...}` declaration appears LAST in the file is what actually renders — regardless of which
    one sits inside a mobile media query. This must be a reset to 0, or every phone gets pushed
    sideways by the desktop sidebar width again."""
    declarations = _all_declarations(".app-main")
    margin_lefts = [
        match.group(1)
        for decl in declarations
        if (match := re.search(r"margin-left\s*:\s*([^;]+)", decl))
    ]
    assert margin_lefts, "expected at least one .app-main margin-left declaration"
    assert margin_lefts[-1].strip() == "0", (
        "the LAST .app-main margin-left declaration in style.css must be 0 (mobile full-width "
        f"reset) — found {margin_lefts[-1]!r}. If you added a new unconditional `.app-main` "
        "rule after the mobile reset, either move it before the reset or add a matching "
        "`margin-left:0` to the trailing mobile fix block instead."
    )


def test_sidebar_is_off_canvas_by_default_on_mobile():
    assert "transform:translateX(-105%)" in STYLE_CSS
    assert ".sidebar.open{transform:none}" in STYLE_CSS


def test_mobile_fix_block_is_present_and_last_in_file():
    """The dedicated mobile-layout-fix block must stay the last rule in the stylesheet so it
    always wins the cascade at phone widths, regardless of what gets added above it."""
    marker = "/* Mobile layout fix"
    idx = STYLE_CSS.rfind(marker)
    assert idx != -1, "mobile layout fix block is missing from style.css"
    tail = STYLE_CSS[idx:]
    assert ".app-main{margin-left:0" in tail
    assert "overflow-x:hidden" in tail
    # Nothing meaningful should follow the fix block's closing brace except whitespace.
    after_block = tail[tail.rindex("}") + 1:]
    assert after_block.strip() == "", (
        "found CSS after the mobile layout fix block — move new rules above it so the fix "
        "block stays last and keeps winning the cascade on mobile"
    )
