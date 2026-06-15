export const colors = {
  brand: "#F2551F",
  brandDark: "#CE3D0C",
  brandSoft: "#FEF0E9",
  brandGradient: "linear-gradient(135deg,#FF8A4C 0%,#F2511F 55%,#E03D0A 100%)",
  bg: "#F5F6F8",
  card: "#FFFFFF",
  border: "#E7E9EE",
  borderSoft: "#F0F1F4",
  ink: "#0E1116",
  text: "#252B36",
  muted: "#667085",
  faint: "#98A2B3",
  dark: "#14161C",
  dark2: "#1F222B",
  darkBorder: "#2C303C",
  evidenceBg: "#F2FBF6",
  evidenceBorder: "#CFEBDA",
  evidenceBorderSoft: "#D5EBDD",
  evidenceText: "#067647",
  evidenceDarkText: "#75DFA6",
  warningBg: "#FEF0E7",
  warningText: "#93370D",
} as const;

export const severity = {
  CRITICAL: { fg: "#D92D20", bg: "#FEECEB", dot: "#F04438", label: "Critical" },
  HIGH: { fg: "#E04F16", bg: "#FEF0E7", dot: "#F2551F", label: "High" },
  MEDIUM: { fg: "#B54708", bg: "#FEF4E4", dot: "#F5A60A", label: "Medium" },
  LOW: { fg: "#079455", bg: "#E9F8F0", dot: "#17B26A", label: "Low" },
} as const;

export const verdict = {
  "NO-GO": "#D92D20",
  CAUTION: "#F2551F",
  PROCEED: "#079455",
} as const;

export const typography = {
  families: {
    display: '"Plus Jakarta Sans Variable", ui-sans-serif, system-ui, sans-serif',
    body: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    mono: '"JetBrains Mono Variable", ui-monospace, "SF Mono", Menlo, monospace',
  },
  roles: {
    h1: { size: "22px", weight: 800, letterSpacing: "0" },
    h2: { size: "15px", weight: 700, letterSpacing: "0" },
    h3: { size: "14.5px", weight: 700, letterSpacing: "0" },
    cardTitleLarge: { size: "16.5px", weight: 800, letterSpacing: "0" },
    body: { size: "13.5px", lineHeight: 1.65, weight: 400 },
    secondary: { size: "12.5px", weight: 400 },
    table: { size: "13px", weight: 400 },
    micro: { size: "11px", weight: 500 },
    eyebrow: { size: "9.5px", weight: 500, letterSpacing: "0.15em" },
    tableHeader: { size: "10.5px", weight: 600, letterSpacing: "0.04em" },
    kpiValue: { size: "25px", weight: 800, letterSpacing: "0" },
  },
} as const;

export const radii = {
  card: "16px",
  inner: "12px",
  tile: "11px",
  button: "11px",
  badge: "999px",
  mono: "6px",
  evidence: "7px",
  option: "9px",
  popover: "14px",
} as const;

export const shadows = {
  card: "0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.05)",
  hover: "0 4px 10px rgba(16,24,40,.06), 0 12px 28px rgba(16,24,40,.09)",
  primaryButton: "0 4px 14px rgba(242,85,31,.32)",
  darkCard: "0 8px 28px rgba(16,24,40,.22)",
  popover: "0 4px 12px rgba(16,24,40,.08), 0 20px 48px rgba(16,24,40,.16)",
} as const;

export const motion = {
  cardHover: "180ms",
  buttonHover: "150ms",
  chevron: "180ms",
  scoreRing: "600ms",
  ping: "1600ms",
  easing: "ease",
} as const;

export type Severity = keyof typeof severity;
export type Verdict = keyof typeof verdict;
export type Confidence = "HIGH" | "LOW";
