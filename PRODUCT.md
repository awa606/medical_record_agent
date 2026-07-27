# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary users are outpatient doctors and project reviewers using a controlled AI-assisted EMR workspace. Doctors need to select or create an encounter, review ASR/transcript evidence, generate a draft record, confirm fields, and export only after human review. Reviewers use the same UI to verify the course/demo workflow, safety gates, and traceability.

## Product Purpose

Medical Record Agent turns synthetic Chinese medical dialogue text or audio into a structured, reviewable electronic medical record draft. Success means the user can complete the path from encounter selection to transcription, draft review, doctor approval, and gated export without losing track of patient safety, role quality, or evidence.

## Positioning

The product is a regulated-task doctor workbench, not a marketing site and not an autonomous diagnosis product. Its defining mechanism is a human-in-the-loop workflow that keeps ASR role quality, candidate diagnoses, safety checks, revision status, and export readiness visible before any final artifact is produced.

## Operating Context

The workspace runs as a FastAPI web app with static HTML, CSS, and native JavaScript. The primary route is `/static/doctor.html`. The UI includes a worklist/dashboard, encounter workspace, transcription/player area, record draft cards, AI assistance panels, doctor approval controls, drawers, popovers, and an admin/runtime view. All screenshots and examples use synthetic patient data only.

## Capabilities and Constraints

The product supports text generation, audio upload, browser recording entry, Mock/FunASR/SenseVoice/Whisper/Qwen/Online ASR routes, SSE transcription, speaker identity review, doctor profile enrollment, live record preview, draft saving, field confirmation, export readiness, and final export.

Do not introduce React, Tailwind, Motion, GSAP, external font CDNs, new front-end frameworks, or changed backend contracts. Preserve existing API paths, request parameters, response assumptions, DOM IDs, `data-*` attributes, Doctor A/B data isolation, Revision review behavior, speaker-role quality gates, doctor approval flow, export readiness checks, and blocked-export messaging.

## Brand Commitments

Use the established product name and Chinese clinical terminology: 智能病历助手, AI生成式电子病历辅助系统, 受控试点环境, 医生审核, 候选诊断, 证据追溯, and 导出门禁. The interface should feel like a restrained clinical task surface with high scan efficiency, not a promotional or decorative AI demo.

## Evidence on Hand

Existing implementation and acceptance evidence lives in `static/doctor.html`, `static/doctor.css`, `static/doctor-ui-v2.css`, `static/doctor.js`, `README.md`, `docs/doctor_workbench_acceptance_v1_0.md`, `docs/frontend_screenshot_acceptance_gate_v1_3.md`, and existing screenshot folders under `docs/final_report/images/`.

There is no clinical validation or real patient data in this repository. Future UI work must not imply production hospital readiness, independent medical judgment, or verified ASR/diagnosis accuracy beyond the existing demo evidence.

## Product Principles

- Preserve patient safety and export gates before visual polish.
- Keep the primary doctor task path visible: select encounter, transcribe, review, approve, export.
- Favor dense but legible clinical grouping over decoration.
- Make incomplete, failed, low-confidence, and blocked states explicit.
- Keep evidence and revision context reachable without crowding the default view.

## Accessibility & Inclusion

The doctor workbench should target WCAG AA contrast, visible keyboard focus, logical focus order, usable touch targets, clear disabled states, and resilient Chinese text wrapping. Required visual checks are 1366x768, 1440x900, and 1920x1080.
