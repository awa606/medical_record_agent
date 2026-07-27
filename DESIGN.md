---
name: Medical Record Agent Doctor Workbench
description: Restrained clinical task UI for AI-assisted electronic medical record review.
colors:
  primary: "#1768c4"
  primary-strong: "#0f55a8"
  primary-soft: "#eaf3ff"
  background: "#f3f6fa"
  surface: "#ffffff"
  surface-soft: "#f7f9fc"
  line: "#dfe6ee"
  line-strong: "#c9d4e2"
  text: "#172033"
  muted: "#64748b"
  success: "#158463"
  success-soft: "#ecf8f3"
  warning: "#b7791f"
  warning-soft: "#fff8e6"
  danger: "#c53b47"
  danger-soft: "#fff0f1"
  nav: "#102b46"
typography:
  body:
    fontFamily: "\"Segoe UI\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "13px"
    fontWeight: 500
    lineHeight: 1.45
  title:
    fontFamily: "\"Segoe UI\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "18px"
    fontWeight: 800
    lineHeight: 1.25
  label:
    fontFamily: "\"Segoe UI\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "11px"
    fontWeight: 700
    lineHeight: 1.3
rounded:
  sm: "7px"
  md: "10px"
  lg: "14px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    padding: "8px 13px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "8px 13px"
---

# Design System: Medical Record Agent Doctor Workbench

## Overview

**Creative North Star: "Clinical Control Room"**

The UI is a restrained doctor operation surface. It should help clinicians scan status, evidence, and next actions quickly while keeping the AI system's uncertainty and approval boundaries visible. Familiar controls, predictable grid behavior, stable typography, and semantic state colors matter more than visual novelty.

The design language is native web HTML/CSS/JavaScript with system fonts and clinical blue/green/yellow/red semantics. It should not use decorative animation, external fonts, heavy gradients, bouncy motion, or marketing composition.

## Colors

The palette is cool neutral with one primary clinical blue and semantic medical state colors.

### Primary
- **Clinical Blue** (`#1768c4`): primary actions, selected navigation, focus-supporting accents, and stable progress indicators.
- **Clinical Blue Strong** (`#0f55a8`): primary hover and stronger selected states.
- **Clinical Blue Soft** (`#eaf3ff`): low-emphasis selected or informational surfaces.

### Neutral
- **Workbench Background** (`#f3f6fa`): app background.
- **Surface** (`#ffffff`): cards, panels, drawers, menus, and controls.
- **Surface Soft** (`#f7f9fc`): table headers, panel interiors, and low-emphasis grouping.
- **Line** (`#dfe6ee`) and **Line Strong** (`#c9d4e2`): borders and separators.
- **Text** (`#172033`) and **Muted** (`#64748b`): primary and secondary text.

### Semantic
- **Success** (`#158463` / `#ecf8f3`): reviewed, passed, confirmed, export-ready states.
- **Warning** (`#b7791f` / `#fff8e6`): pending review, low confidence, missing non-blocking details.
- **Danger** (`#c53b47` / `#fff0f1`): blocked export, failed transcription, gate violations.

## Typography

Use system UI and Chinese system fonts only: `"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif`. Do not depend on external font CDNs. Keep type compact and fixed, not viewport-scaled.

### Hierarchy
- **Title**: 16-18px, weight 800, used for product name, panel titles, and important task headings.
- **Body**: 12-13px, weight 500-700, line-height 1.45-1.65, used for clinical content and instructions.
- **Label**: 10-12px, weight 700-800, used for metadata labels, chips, and compact controls.
- **Data**: use tabular numeric features where duration, segment counts, or measurements need alignment.

## Layout

The app shell is a fixed-height desktop task surface with a top bar, left product navigation, scrollable product main area, and an encounter workspace. The encounter view uses a patient banner, command/status center, three clinical work zones, and a fixed bottom action bar.

Supported desktop checks are 1366x768, 1440x900, and 1920x1080. At wide widths the transcript, record, and assist panels may be side-by-side. At constrained widths, the workspace can become a two-row grid. Long transcript and detail regions must scroll independently; page-level horizontal overflow is a defect.

## Elevation & Depth

Depth is quiet and structural. Panels use tonal layering, borders, and soft shadows only to separate working regions. The bottom action bar can use stronger elevation because it stays fixed and must remain visible.

## Shapes

Use modest clinical radii: 7px for controls, 9-10px for cards and fields, 12-14px for major panels. Avoid pill-shaped primary controls unless the existing component is a compact chip or status badge.

## Components

### Buttons
- Primary buttons use Clinical Blue with white text and clear hover/focus states.
- Secondary buttons are white or soft neutral with line borders.
- Danger/export buttons use danger semantics but must still show blocked/disabled states clearly.
- Busy and disabled states must prevent duplicate submit and explain why an action is unavailable when relevant.

### Cards / Containers
- Cards represent real repeated clinical entities: record fields, transcript rows, assist cards, worklist rows.
- Use border, background tint, chips, and status dots for state. Avoid thick side-tab borders as the only state signal.

### Inputs / Fields
- Inputs use white backgrounds, 1px borders, 8px radius, and visible focus rings.
- File, select, and text controls keep existing IDs and API wiring.

### Overlays
- Drawers and popovers must render above scroll containers and must not be clipped by `overflow` ancestors.
- Drawer content must be scrollable without hiding its close control.

## Do's and Don'ts

### Do:
- **Do** preserve existing API paths, DOM IDs, `data-*` attributes, and event contracts.
- **Do** make loading, empty, failed, disabled, retry, and blocked-export states visible.
- **Do** keep transcript, draft fields, and AI assist areas independently scrollable.
- **Do** use medical semantic colors even when a generic one-accent rule would suggest otherwise.

### Don't:
- **Don't** introduce React, Tailwind, Motion, GSAP, icon libraries, or external font CDNs.
- **Don't** add decorative animation, page entrance choreography, parallax, magnetic motion, or bounce effects.
- **Don't** remove doctor review, Revision review, role-quality, or export readiness gates.
- **Don't** use real patient data, real identities, or claims of clinical validation.
