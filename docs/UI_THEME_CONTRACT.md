# Veritas UI theme contract

The **Audit Workbench / Evidence Lens** visual language is the product baseline:
charcoal canvases, layered near-black surfaces, soft cool-gray typography, and
restrained teal for focused/interactive states. A warm white or cream application
canvas is not a supported default.

## Semantic colors

| Role | Web CSS token | React Native token | Value |
| --- | --- | --- | --- |
| Canvas | `--bg` | `workspaceColors.bg` | `#0e0e0e` |
| Panel | `--surface` | `workspaceColors.surface` | `#121212` |
| Raised panel | `--surface-soft` | `workspaceColors.surfaceSoft` | `#161616` |
| Selected/interactive panel | `--surface-strong` | `workspaceColors.surfaceStrong` | `#1c1c1c` |
| Primary text | `--text` | `workspaceColors.text` | `#e9f1f3` |
| Secondary text | `--text-soft` | `workspaceColors.textSoft` | `#a7a7a7` |
| Divider | `--line` | `workspaceColors.line` | `#292929` |
| Focus/accent | `--accent` | `workspaceColors.accent` | `#52d5cb` |
| Verified | `--good` | `workspaceColors.good` | `#55d59b` |
| Review required | `--warn` | `workspaceColors.warn` | `#e7b44a` |
| Contradiction/error | `--bad` | `workspaceColors.bad` | `#ff7070` |

## Sources of truth

- `src/veritas/harness/static/styles.css` defines **global** CSS semantic tokens.
- `src/veritas/harness/static/workspace-theme.css` resolves legacy light
  selectors shared across Overview, Audits, Findings, Benchmarks, Runs,
  Reproduction, dialogs, and the conversation sidecar.
- `src/veritas/harness/static/reference-workbench.css` and
  `reference-surfaces.css` supply Audit Workbench's denser inspector layout and
  context-specific panels. Do not copy an entire one-off palette for a new route.
- `mobile/theme.ts` is the semantic counterpart for React Native.
- `index.html` must load the common override **after** feature stylesheets.
- `sw.js` must precache `workspace-theme.css` and bump the shell version on
  theme changes, preventing stale PWA styles.

## Design decisions

1. Preserve original document appearance. A white PDF page in the evidence
   viewer is **paper content**, not an application background. Do not invert it.
2. The default full-screen application background is `#0e0e0e`, not cream,
   white, light gray, or a bright gradient.
3. Semantic status backgrounds stay dark and translucent; use color to convey
   state in labels, icons, and thin borders rather than entire pastel panels.
4. Use a shared neutral surface, divider, hover and focus vocabulary for dialogs,
   menus, data tables and sidebars. Do not introduce new hardcoded white panels.
5. Responsive and mobile views retain the same semantic palette. Native
   `userInterfaceStyle` should be `dark`.
6. Use contrast and readable typography; the dense audit inspector is a
   specialist view, not a reason to shrink generic page text to 6px.

## Regression checks

- `python scripts/smoke_workspace_theme_browser.py --base-url http://127.0.0.1:8765`
  uses real Chromium and checks computed colors for all major Web views,
  modal dialogs, the conversation panel, and mobile Web navigation.
- `.github/workflows/ui-visual-smoke.yml` runs this alongside the established
  screenshot workflows and uploads the result artifacts.
- `tests/test_ui_theme_contract.py` protects semantic token and PWA cache
  coupling; it does **not** substitute for device or browser screenshot review.
- `mobile` CI validates React Native tooling; visual fidelity on iOS/Android
  still needs an emulator/device check.
