/* 32x32 icon button with subtle border. Usage: <IconButton title="..." onClick={...}>{svg}</IconButton> */

import type { ButtonHTMLAttributes, ReactNode } from "react";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
}

export function IconButton({ children, className = "", ...rest }: Props) {
  return (
    <button
      type="button"
      {...rest}
      className={`w-8 h-8 bg-surface border border-border rounded-sm text-text-muted flex items-center justify-center transition-colors hover:text-text hover:border-border-strong hover:bg-surface-2 ${className}`}
    >
      {children}
    </button>
  );
}
