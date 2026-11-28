"use client";

import { useEffect, type RefObject } from "react";

/**
 * Keeps the Tab key inside a modal: the slip's sheet, the confirmation's
 * sheet and the question before a slip is cleared. Each says it is modal
 * (aria-modal), so the keyboard must not wander to the page behind it.
 *
 * Modals can sit inside each other (the clear-slip question inside the
 * sheet), so only the one opened last answers the key.
 */

const open: HTMLElement[] = [];

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function useFocusTrap(ref: RefObject<HTMLElement | null>, active: boolean): void {
  useEffect(() => {
    const box = ref.current;
    if (!active || !box) return;
    open.push(box);

    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Tab" || open[open.length - 1] !== box) return;
      const items = Array.from(box.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (element) => element.getClientRects().length > 0,
      );
      const first = items[0];
      const last = items[items.length - 1];
      if (!first || !last) return;
      const current = document.activeElement;
      if (!box.contains(current)) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && (current === first || current === box)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && current === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      open.splice(open.indexOf(box), 1);
    };
  }, [ref, active]);
}
