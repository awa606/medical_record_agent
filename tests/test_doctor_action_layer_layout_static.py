from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_doctor_action_bar_and_transcript_scroll_are_viewport_bound() -> None:
    css = (ROOT / "static" / "doctor-ui-v2.css").read_text(encoding="utf-8")

    assert "--action-bar-safe-space" in css
    assert "--layer-action-bar" in css
    assert "body.doctor-mode .encounter-view" in css
    assert "height: calc(100dvh - 68px)" in css
    assert "grid-template-rows: auto auto minmax(0, 1fr)" in css
    assert "body.doctor-mode .workbench" in css
    assert "overflow: hidden" in css
    assert "body.doctor-mode .transcript-list" in css
    assert "overscroll-behavior: contain" in css
    assert "overflow-wrap: anywhere" in css
    assert "word-break: normal" in css
    assert "z-index: var(--layer-action-bar)" in css
    assert "--layer-drawer-backdrop" in css
    assert "--layer-drawer" in css
    assert "z-index: var(--layer-drawer-backdrop)" in css
    assert "z-index: var(--layer-drawer)" in css
    assert "padding-bottom: calc(var(--action-bar-safe-space) + 24px)" in css
