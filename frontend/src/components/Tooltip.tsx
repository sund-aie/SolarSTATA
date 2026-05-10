/* Self-teaching tooltip — what / how / example.
 *
 * Wrap any interactive element in <Tooltip what="..." how="..." example="...">
 * to surface the three-part copy after a 350ms hover delay. Tooltips also
 * appear on focus and dismiss on Escape, blur, or pointer-leave.
 *
 * Renders to a portal anchored to <body> with viewport-edge clamping so a
 * button near the right edge doesn't push the panel off-screen.
 */

import {
  cloneElement,
  isValidElement,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

interface Props {
  what: string;
  how: string;
  example?: ReactNode;
  /** Where to anchor the tooltip relative to the trigger. */
  side?: "bottom" | "top" | "right";
  /** Disable for development (e.g. tests). */
  disabled?: boolean;
  children: ReactElement;
}

const DELAY_MS = 350;

export function Tooltip({ what, how, example, side = "bottom", disabled, children }: Props) {
  const triggerRef = useRef<HTMLElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const timer = useRef<number | null>(null);
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<{ x: number; y: number } | null>(null);
  const tipId = useId();

  const cancelTimer = useCallback(() => {
    if (timer.current != null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const scheduleOpen = useCallback(() => {
    if (disabled) return;
    cancelTimer();
    timer.current = window.setTimeout(() => setOpen(true), DELAY_MS);
  }, [cancelTimer, disabled]);

  const close = useCallback(() => {
    cancelTimer();
    setOpen(false);
  }, [cancelTimer]);

  // Position the popover after open
  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    const r = triggerRef.current.getBoundingClientRect();
    const margin = 8;
    let x = r.left;
    let y = r.bottom + margin;
    if (side === "top") y = r.top - margin;
    if (side === "right") {
      x = r.right + margin;
      y = r.top;
    }
    // Clamp to viewport (after popover renders so we know its size)
    const popoverW = popoverRef.current?.offsetWidth ?? 320;
    const popoverH = popoverRef.current?.offsetHeight ?? 0;
    if (x + popoverW > window.innerWidth - 8) x = window.innerWidth - popoverW - 8;
    if (x < 8) x = 8;
    if (y + popoverH > window.innerHeight - 8) y = r.top - margin - popoverH;
    if (y < 8) y = 8;
    setCoords({ x, y });
  }, [open, side]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);

  if (!isValidElement(children)) return children;

  const child = children as ReactElement<any>;
  const wrapped = cloneElement(child, {
    ref: (n: HTMLElement) => {
      triggerRef.current = n;
      const original = (child as any).ref;
      if (typeof original === "function") original(n);
      else if (original && typeof original === "object") (original as any).current = n;
    },
    "aria-describedby": open ? tipId : undefined,
    onMouseEnter: (e: any) => {
      child.props.onMouseEnter?.(e);
      scheduleOpen();
    },
    onMouseLeave: (e: any) => {
      child.props.onMouseLeave?.(e);
      close();
    },
    onFocus: (e: any) => {
      child.props.onFocus?.(e);
      scheduleOpen();
    },
    onBlur: (e: any) => {
      child.props.onBlur?.(e);
      close();
    },
  });

  return (
    <>
      {wrapped}
      {open && coords && createPortal(
        <div
          ref={popoverRef}
          id={tipId}
          role="tooltip"
          className="fixed z-[1000] max-w-[340px] bg-surface-2 border border-border-strong rounded-md shadow-elevated p-4 text-text"
          style={{ left: coords.x, top: coords.y }}
        >
          <div className="font-serif italic text-[14px] text-accent mb-1">What it does</div>
          <div className="text-[13px] text-text mb-3 leading-snug">{what}</div>

          <div className="font-serif italic text-[14px] text-accent mb-1">How to use it</div>
          <div className="text-[13px] text-text mb-3 leading-snug">{how}</div>

          {example && (
            <>
              <div className="font-serif italic text-[14px] text-accent mb-1">Example</div>
              <div className="text-[12px] text-text-muted leading-snug">{example}</div>
            </>
          )}
        </div>,
        document.body,
      )}
    </>
  );
}
