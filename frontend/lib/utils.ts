import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Computes a `position: fixed` {top, left} for a popup of size (popupW, popupH)
 * anchored to `anchor` (from getBoundingClientRect), flipping above/below and
 * clamping horizontally so the popup never renders past the viewport edge —
 * used for floating panels rendered via a portal so ancestor `overflow` can't clip them.
 */
export function clampToViewport(
  anchor: { top: number; left: number; width: number; height: number },
  popupW: number,
  popupH: number,
  margin = 8
): { top: number; left: number } {
  const vw = typeof window !== "undefined" ? window.innerWidth : popupW + margin * 2;
  const vh = typeof window !== "undefined" ? window.innerHeight : popupH + margin * 2;

  let left = anchor.left + anchor.width / 2 - popupW / 2;
  left = Math.min(Math.max(left, margin), Math.max(margin, vw - popupW - margin));

  let top = anchor.top - popupH - 10;
  if (top < margin) {
    top = anchor.top + anchor.height + 10;
  }
  top = Math.min(Math.max(top, margin), Math.max(margin, vh - popupH - margin));

  return { top, left };
}
