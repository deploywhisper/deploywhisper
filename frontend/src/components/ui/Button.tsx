import type { ButtonHTMLAttributes } from "react";

export type ButtonVariant = "primary-gradient" | "ghost" | "dark";

export function Button({
  variant = "ghost",
  children,
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
}) {
  return (
    <button className={`dw-button dw-button-${variant}${className ? ` ${className}` : ""}`} type="button" {...props}>
      {children}
    </button>
  );
}
