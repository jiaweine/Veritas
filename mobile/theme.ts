/**
 * Veritas native palette mirrors the Audit Workbench semantic colors on web.
 * Keep component styling in StyleSheet; do not copy the old light literals.
 */
export const workspaceColors = {
  bg: "#0e0e0e",
  surface: "#121212",
  surfaceSoft: "#161616",
  surfaceStrong: "#1c1c1c",
  text: "#e9f1f3",
  textSoft: "#a7a7a7",
  textFaint: "#858585",
  line: "#292929",
  lineStrong: "#3c3c3c",
  accent: "#52d5cb",
  accentInk: "#80e5de",
  onAccent: "#08201e",
  accentSoft: "#1c3432",
  accentLine: "#397e79",
  good: "#55d59b",
  goodSoft: "#17352b",
  goodLine: "#356b55",
  warn: "#e7b44a",
  warnSoft: "#322b19",
  warnLine: "#725c2b",
  bad: "#ff7070",
  badSoft: "#352022",
  badLine: "#743c43",
} as const;
