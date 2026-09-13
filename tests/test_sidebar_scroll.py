"""Regression coverage for the desktop sidebar scrolling bug: with the mouse over the
fixed left sidebar, the wheel event used to bubble up and scroll the main page instead of
the sidebar itself, because no element inside the sidebar was actually a scroll container
-- lower nav items (e.g. QR Scanner) could become unreachable on short viewports.

These tests parse the shipped stylesheet text (same approach as test_mobile_layout.py)
rather than driving a real browser, so they run without an extra runtime dependency and
fail loudly if a future edit removes the independent scroll container, lets the sidebar
itself gain scrolling instead of the nav area, or reintroduces horizontal overflow.
"""
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STYLE_CSS = (PROJECT_ROOT / "app" / "static" / "style.css").read_text(encoding="utf-8")


def _last_declaration(selector: str) -> str:
    """The LAST `{...}` declaration body for an exact, standalone `selector` in source
    order -- later same-specificity rules win the cascade, matching how the browser
    actually resolves it (same convention as test_mobile_layout.py)."""
    pattern = re.compile(re.escape(selector) + r"\{([^}]*)\}")
    matches = pattern.findall(STYLE_CSS)
    assert matches, f"expected at least one {selector!r} declaration"
    return matches[-1]


def test_sidebar_itself_stays_fixed_to_the_viewport():
    # position:fixed + inset:0 auto 0 0 pins the sidebar to the full viewport height;
    # it's declared once and never overridden by a later same-specificity rule.
    assert "position:fixed" in STYLE_CSS.split(".sidebar{", 1)[1][:200]
    assert "inset:0 auto 0 0" in STYLE_CSS


def test_only_the_middle_nav_area_is_an_independent_scroll_container():
    side_nav = _last_declaration(".side-nav")
    assert "overflow-y:auto" in side_nav
    assert "flex:1" in side_nav
    # Without min-height:0, a flex child can never shrink below its content size, so
    # overflow-y:auto would never actually engage -- the sidebar would just grow instead.
    assert "min-height:0" in side_nav
    # The sidebar's own rule must not take on scrolling -- only its middle nav child does.
    sidebar_rule_start = STYLE_CSS.index(".sidebar{")
    sidebar_rule_end = STYLE_CSS.index("}", sidebar_rule_start)
    assert "overflow" not in STYLE_CSS[sidebar_rule_start:sidebar_rule_end]


def test_side_nav_scroll_container_never_introduces_horizontal_overflow():
    side_nav = _last_declaration(".side-nav")
    assert "overflow-x:hidden" in side_nav


def test_top_and_bottom_sidebar_sections_stay_pinned_outside_the_scroll_area():
    # Top: clinic identity block is a normal (non-flex-grow, non-scrolling) sibling.
    assert ".clinic-identity{" in STYLE_CSS
    clinic_identity = _last_declaration(".clinic-identity")
    assert "overflow" not in clinic_identity
    assert "flex:1" not in clinic_identity
    # Bottom: the Add-patient/Sign-out cluster is pushed to the bottom via margin-top:auto,
    # not by scrolling -- it must always stay visible regardless of nav-list length.
    sidebar_lower = _last_declaration(".sidebar-lower")
    assert "margin-top:auto" in sidebar_lower


def test_side_nav_scrollbar_is_subtle_but_not_disabled():
    """Hiding the scrollbar with `scrollbar-width:none` (or width:0) would also silently
    break trackpad/touch scroll affordance in some browsers -- it must stay thin/subtle,
    never fully removed, and wheel/keyboard/touch input must remain native (no JS
    scroll-blocking here that could interfere with any input method)."""
    side_nav = _last_declaration(".side-nav")
    assert "scrollbar-width:thin" in side_nav
    assert "scrollbar-width:none" not in side_nav
    assert ".side-nav::-webkit-scrollbar{" in STYLE_CSS
    assert ".side-nav::-webkit-scrollbar-thumb{" in STYLE_CSS
    webkit_scrollbar = re.search(r"\.side-nav::-webkit-scrollbar\{([^}]*)\}", STYLE_CSS).group(1)
    assert "width:0" not in webkit_scrollbar
    assert "display:none" not in webkit_scrollbar


def test_mobile_off_canvas_drawer_behavior_is_unchanged():
    """The independent-scroll change must not touch how the sidebar slides on/off screen
    on phones (see test_mobile_layout.py for the full mobile-fix regression suite)."""
    assert "transform:translateX(-105%)" in STYLE_CSS
    assert ".sidebar.open{transform:none}" in STYLE_CSS
