import { useId } from "react";

import { colors } from "../../theme/tokens";

export function Sparkline({
  points,
  color = colors.brand,
  width = 76,
  height = 26,
  label = "Trend",
}: {
  points: number[];
  color?: string;
  width?: number;
  height?: number;
  label?: string;
}) {
  const gradientId = `${useId().replace(/:/g, "")}-sparkline-gradient`;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const coordinates = points.map((point, index) => {
    const x = points.length === 1 ? width / 2 : (index / (points.length - 1)) * width;
    const y = height - 3 - ((point - min) / range) * (height - 6);
    return [x, y] as const;
  });
  const path = coordinates.map(([x, y], index) => `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join("");

  return (
    <svg aria-label={label} height={height} role="img" width={width}>
      <defs>
        <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity=".2" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${path}L${width},${height}L0,${height}Z`} fill={`url(#${gradientId})`} />
      <path d={path} fill="none" stroke={color} strokeLinecap="round" strokeWidth="1.7" />
    </svg>
  );
}
