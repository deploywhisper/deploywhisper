import { useId } from "react";

export function ScoreRing({
  score,
  size = 76,
  stroke = 7,
  dark = false,
  label = "Risk score",
}: {
  score: number;
  size?: number;
  stroke?: number;
  dark?: boolean;
  label?: string;
}) {
  const gradientId = `${useId().replace(/:/g, "")}-score-gradient`;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - Math.max(0, Math.min(100, score)) / 100);

  return (
    <span
      aria-label={`${label}: ${score} out of 100`}
      className={`dw-score-ring${dark ? " dw-score-ring-dark" : ""}`}
      role="img"
      style={{ height: size, width: size }}
    >
      <svg aria-hidden="true" height={size} width={size}>
        <defs>
          <linearGradient id={gradientId} x1="0%" x2="100%" y1="0%" y2="100%">
            <stop offset="0%" stopColor="#FF8A4C" />
            <stop offset="55%" stopColor="#F2511F" />
            <stop offset="100%" stopColor="#E03D0A" />
          </linearGradient>
        </defs>
        <circle
          cx={size / 2}
          cy={size / 2}
          fill="none"
          r={radius}
          stroke={dark ? "#2C303C" : "#EEF0F3"}
          strokeWidth={stroke}
        />
        <circle
          className="dw-score-ring-progress"
          cx={size / 2}
          cy={size / 2}
          fill="none"
          r={radius}
          stroke={`url(#${gradientId})`}
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          strokeWidth={stroke}
        />
      </svg>
      <span className="dw-score-ring-label">
        <span className="dw-score-ring-score" style={{ fontSize: size * 0.3 }}>
          {score}
        </span>
        <span className="dw-score-ring-total">/100</span>
      </span>
    </span>
  );
}
