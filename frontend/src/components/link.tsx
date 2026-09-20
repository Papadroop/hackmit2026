import type { AnchorHTMLAttributes, MouseEvent } from "react"

import { navigate } from "@/lib/router"

/** An anchor that navigates in-app for plain left clicks and behaves like a normal link
 * otherwise (modifier keys, middle click, other targets), so it stays a real link. */
export function Link({
  href,
  onClick,
  target,
  ...props
}: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) {
  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event)
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      (target !== undefined && target !== "_self")
    ) {
      return
    }
    event.preventDefault()
    navigate(href)
  }
  return <a href={href} target={target} onClick={handleClick} {...props} />
}
