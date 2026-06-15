import type { ReactNode } from "react";

export function Card({
  eyebrow,
  title,
  right,
  children,
  lift = false,
}: {
  eyebrow?: string;
  title?: string;
  right?: ReactNode;
  children: ReactNode;
  lift?: boolean;
}) {
  return (
    <section className={`dw-card${lift ? " dw-card-lift" : ""}`}>
      {(eyebrow || title || right) && (
        <div className="dw-card-header">
          <div>
            {eyebrow && <div className="dw-card-eyebrow">{eyebrow}</div>}
            {title && <h2 className="dw-card-title">{title}</h2>}
          </div>
          {right}
        </div>
      )}
      <div className="dw-card-body">{children}</div>
    </section>
  );
}
