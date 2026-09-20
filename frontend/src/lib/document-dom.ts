/**
 * DOM geometry for the document pane: margin labels and scrolling to a span. Kept apart from
 * the component so the component file exports only components (fast refresh).
 */
import { markKey } from "./document-layout"

/** Something one section has asked another to point at: a claim to scroll to, an omission
 * card to flash. The key makes a second request for the same id a new one. */
export type Focus = { id: string; span: number; key: number }

const LABEL_HEIGHT = 18
const LABEL_GAP = 2

/**
 * Put each margin label ([data-label-for]) beside the first line box of its claim's primary
 * highlight ([data-primary]). Labels that would overlap are pushed down in order.
 */
export function placeGutterLabels(sheet: HTMLElement): void {
  const base = sheet.getBoundingClientRect().top + sheet.clientTop
  const placed: { label: HTMLElement; top: number }[] = []
  for (const label of sheet.querySelectorAll<HTMLElement>("[data-label-for]")) {
    const id = label.dataset.labelFor ?? ""
    const mark = sheet.querySelector<HTMLElement>(
      `[data-primary="${CSS.escape(id)}"]`
    )
    if (mark === null) {
      label.hidden = true
      continue
    }
    const rect = mark.getClientRects()[0] ?? mark.getBoundingClientRect()
    placed.push({
      label,
      top: rect.top - base + (rect.height - LABEL_HEIGHT) / 2,
    })
  }
  placed.sort((a, b) => a.top - b.top)
  let floor = Number.NEGATIVE_INFINITY
  for (const { label, top } of placed) {
    const y = Math.max(top, floor)
    label.hidden = false
    label.style.top = `${Math.round(y)}px`
    floor = y + LABEL_HEIGHT + LABEL_GAP
  }
}

export function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches
}

/** A brief background pulse on an element that was just scrolled to. */
export function flash(element: HTMLElement): void {
  element.animate(
    [{ backgroundColor: "var(--muted)" }, { backgroundColor: "transparent" }],
    { duration: 1500, easing: "ease-out" }
  )
}

/** Scroll the pane to an omission card ([data-omission]) and pulse it. */
export function scrollToOmission(
  root: HTMLElement | null,
  id: string
): boolean {
  const target = root?.querySelector<HTMLElement>(
    `[data-omission="${CSS.escape(id)}"]`
  )
  if (!target) return false
  target.scrollIntoView({
    block: "center",
    behavior: prefersReducedMotion() ? "auto" : "smooth",
  })
  flash(target)
  return true
}

/** Scroll the pane so the given span (claim or signal id plus span index) is in view. */
export function scrollToSpan(
  root: HTMLElement | null,
  id: string,
  span = 0
): boolean {
  if (root === null) return false
  const target = root.querySelector<HTMLElement>(
    `[data-anchor="${CSS.escape(markKey({ id, span }))}"]`
  )
  if (target === null) return false
  target.scrollIntoView({
    block: "center",
    behavior: prefersReducedMotion() ? "auto" : "smooth",
  })
  return true
}
