import { Activity, AlertTriangle, CheckCircle2, CircleDot } from "lucide-react";
import type { ReactNode } from "react";

import { colors, severity, verdict, type Confidence, type Severity, type Verdict } from "../../theme/tokens";

export function SeverityBadge({ level }: { level: Severity }) {
  const token = severity[level];

  return (
    <span className="dw-severity-badge" style={{ background: token.bg, color: token.fg }}>
      <span className="dw-severity-dot" style={{ background: token.dot }} />
      {token.label}
    </span>
  );
}

export function VerdictChip({ verdict: value, size = "md" }: { verdict: Verdict; size?: "sm" | "md" }) {
  const fill = verdict[value];
  const Icon = value === "PROCEED" ? CheckCircle2 : AlertTriangle;

  return (
    <span
      className={`dw-verdict-chip dw-verdict-chip-${size}`}
      style={{ background: fill, boxShadow: `0 2px 8px ${fill}55` }}
    >
      <Icon size={12} />
      {value}
    </span>
  );
}

export function EvidenceTag({ children }: { children: ReactNode }) {
  return (
    <span className="dw-evidence-tag">
      <CircleDot size={9} />
      {children}
    </span>
  );
}

export function ConfidenceBadge({ level }: { level: Confidence }) {
  return (
    <span className={`dw-confidence-badge${level === "LOW" ? " dw-confidence-low" : ""}`}>
      <Activity size={11} />
      {level === "LOW" ? "Low" : "High"} confidence
    </span>
  );
}

export function MonoRef({ children }: { children: ReactNode }) {
  return <code className="dw-mono-ref">{children}</code>;
}

export function evidenceLawChip() {
  return {
    background: colors.evidenceBg,
    border: colors.evidenceBorder,
    color: colors.evidenceText,
  };
}
