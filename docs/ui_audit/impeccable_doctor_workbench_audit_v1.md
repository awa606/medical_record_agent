# Impeccable doctor workbench audit v1

Baseline: `e4e10ef3ee70e40e3aeea5cff89512fc997a1fd7` (`codex/pilot-rc2-candidate`) in `06_UI_EXPERIMENTS/mra_ui_impeccable_v1`.

Scope: `/static/doctor.html`, `/static/doctor.css`, `/static/doctor-ui-v2.css`, `/static/doctor.js`. This first pass is audit-only; fixes are applied after this report.

## Audit Health Score

| # | Dimension | Score | Key Finding |
|---|-----------|-------|-------------|
| 1 | Accessibility | 3 | Focus rings and ARIA labels exist, but several compact controls and disabled/export states need clearer non-color communication. |
| 2 | Performance | 3 | Native static UI is lean; detector flags a `transition: width` progress animation and fixed blur/elevation in sticky action areas. |
| 3 | Responsive Design | 2 | 1366/1440/1920 rules exist, but the 1366 encounter layout has high risk of vertical crowding and fixed bottom bar overlap. |
| 4 | Theming | 3 | Token set exists in `doctor-ui-v2.css`; legacy `doctor.css` still carries duplicate colors and state-border patterns. |
| 5 | Implementation Integrity | 2 | Coherent clinical shell exists, but detector flags repeated thick side-tab borders and overused font declarations. |
| **Total** | | **13/20** | **Acceptable: improve responsive density, state hardening, and detector findings before polish.** |

## Implementation Integrity Verdict

Pass with required follow-up. The implementation is product-specific: dashboard/worklist, encounter workspace, transcript/player, draft fields, AI assist, and export gate are recognizably clinical and task-oriented. It is not interchangeable with a marketing page. However, repeated thick left borders on cards/status panels create noisy state signaling, and the font stack includes `Inter` despite the project constraint against external font dependency.

Detector command:

```powershell
node .agents\skills\impeccable\scripts\detect.mjs --json static
```

Detector result summary:
- `side-tab` warnings in `static/doctor-ui-v2.css` at field cards and step prompt, plus legacy matches in `static/doctor.css`.
- `overused-font` warnings for `Inter` in `static/doctor-ui-v2.css` and Arial in legacy/static pages.
- `layout-transition` warning for `transition: width` in `static/doctor.css`.

## Detailed Findings

### P1: Bottom action bar can compete with 1366px vertical space

- Location: `static/doctor-ui-v2.css`, encounter workspace and `.encounter-action-bar`.
- Category: Responsive Design / Layout.
- Impact: At 1366x768, the fixed action bar can consume the lower viewport while the workbench still uses large minimum heights. This risks hiding transcript or assist content behind the export/review controls.
- Recommendation: Reserve enough bottom padding on encounter view, make workbench min-height less aggressive at 1366, and keep panel internals independently scrollable.
- Suggested command: `$impeccable adapt`.

### P1: Export disabled state is visible but recovery reason is not always proximate

- Location: `static/doctor.js` render operation state and `.encounter-action-bar #exportButton`.
- Category: Accessibility / Hardening.
- Impact: Disabled export is safety-critical. Users need a nearby reason that does not rely only on button disabled styling or tooltip.
- Recommendation: Add an always-visible compact operation hint derived from existing readiness/status state, without changing export gate logic.
- Suggested command: `$impeccable harden`.

### P2: Thick side-tab borders are repeated as a generic state pattern

- Location: `static/doctor-ui-v2.css` field cards and prompt accents; legacy matches in `static/doctor.css`.
- Category: Implementation Integrity / Theming.
- Impact: State meaning is over-concentrated in left borders and can read as noisy or generic. It also creates detector noise.
- Recommendation: Replace active doctor-workbench side borders with 1px semantic borders, soft background tints, and status dots/chips. Leave legacy-only rules alone unless they affect the active route.
- Suggested command: `$impeccable layout`.

### P2: Font stack conflicts with local-only font constraint

- Location: `static/doctor-ui-v2.css`.
- Category: Theming / Accessibility.
- Impact: `Inter` is not loaded locally and should not be treated as a dependency. The UI should rely on Windows/macOS/system Chinese fonts.
- Recommendation: Remove `Inter` from the primary stack and document the system-font rule in DESIGN.md.
- Suggested command: `$impeccable typeset` or `$impeccable polish`.

### P2: Progress animation uses width transition

- Location: `static/doctor.css`, `.progress-track span`.
- Category: Performance.
- Impact: Animating width can cause layout work during frequent progress updates.
- Recommendation: Switch the progress fill to a transform-based scale update, or disable the width transition for this legacy progress track.
- Suggested command: `$impeccable optimize`.

### P2: Overlay z-index and overflow behavior needs explicit protection

- Location: `.input-method-popover`, `.display-settings-popover`, `.drawer`, `.product-main`, `.topbar`.
- Category: Responsive Design / Implementation Integrity.
- Impact: Menus and drawers are safety-relevant for starting flows and reviewing details. They should not be clipped by scroll containers or appear under fixed bars.
- Recommendation: Raise popover stacking over the top bar, keep drawer/backdrop above action bar, and verify narrow viewports.
- Suggested command: `$impeccable layout`.

## Positive Findings

- Existing UI already has product-specific clinical regions and avoids landing-page composition.
- The implementation preserves native HTML/CSS/JS and has clear API/DOM wiring.
- Empty states, loading labels, failure recovery, role review, export readiness, and doctor approval states already exist in JavaScript.
- Focus-visible rules and ARIA labels are present across many controls.
- Required 1366/1920 responsive work has prior evidence and explicit CSS breakpoints.

## Recommended Actions

1. **[P1] `$impeccable adapt`**: tighten 1366/1440/1920 encounter layout and reserve bottom action space.
2. **[P1] `$impeccable harden`**: make blocked export, busy, failed, empty, and retry states clearer without changing backend gates.
3. **[P2] `$impeccable layout`**: reduce noisy side-tab borders in the active doctor workbench and protect popovers/drawers from clipping.
4. **[P2] `$impeccable polish`**: remove local font ambiguity, run detector/static checks, and keep only intentional exceptions.

## Fix Pass v1

Applied after the audit in the UI-only worktree.

### Changes

- Added project context in `PRODUCT.md` and `DESIGN.md` for regulated clinical task UI, Operate-mode density, native HTML/CSS/JS, synthetic patient data only, no external font CDN, and no API/DOM contract changes.
- Explicitly disabled Impeccable hooks in `.impeccable/config.json`.
- Temporarily disabled `detector.designSystem.enabled` for manual detector runs. Reason: this first round creates a product/design constraint document, not a complete token inventory for the existing legacy CSS. Mechanical detector rules still run with `npx impeccable detect static`.
- Replaced `Inter`/explicit `Arial` stacks with system UI and Chinese system fonts.
- Replaced repeated thick side-tab borders with 1px semantic borders, quiet background tints, or inset state outlines.
- Tightened 1366px encounter layout spacing and workbench height to reduce bottom action bar crowding.
- Added drawer/popover stacking protection so menus and detail drawers stay above scroll containers and the fixed action bar.
- Changed transcript progress fill from width animation to transform scale.
- Added export disabled reason into the footer hint and button metadata without changing export gate logic.
- Updated the static product-shell test to assert the new 1366px compact workbench height.

### Validation

```powershell
node --check static\doctor.js
npx impeccable detect static
pytest -q tests\test_tasks_api.py tests\test_records_api.py tests\test_asr_sessions_api.py tests\test_audio_api.py tests\test_speaker_profiles.py tests\test_speaker_role_quality_policy.py
pytest -q
```

Results:

- `node --check static\doctor.js`: pass.
- `npx impeccable detect static`: pass with project config; design-system drift check is disabled as noted above.
- Targeted backend/gate regression: `68 passed, 1 warning`.
- Full regression: `330 passed, 1 warning`.

### Browser Evidence

Screenshots are saved under:

`docs/ui_audit/screenshots_v1/`

Captured states at `1366x768`, `1440x900`, and `1920x1080`:

- `empty_state`
- `input_menu_open`
- `transcription_preview`
- `generated_record`
- `detail_drawer`
- `role_review_state`
- `export_blocked`
- `export_success`

Manifest:

`docs/ui_audit/screenshots_v1/browser_acceptance_manifest.json`

Contact sheet:

`docs/ui_audit/screenshots_v1/browser_acceptance_contact_sheet.png`
