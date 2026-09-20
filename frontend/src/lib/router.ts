import { useMemo, useSyncExternalStore } from "react"

/**
 * The URL is the source of truth for which screen is open. An analysis lives at
 * /a/<analysis id>, so a reload keeps it (the server still holds its log and the client
 * re-tails it), the back button works, and a run can be linked to.
 */
export type Route =
  | { name: "menu" }
  | { name: "analysis"; id: string }
  | { name: "not-found"; path: string }

export const paths = {
  menu: () => "/",
  analysis: (id: string) => `/a/${encodeURIComponent(id)}`,
}

export function parseRoute(pathname: string): Route {
  const path = pathname.replace(/\/+$/, "") || "/"
  if (path === "/") return { name: "menu" }
  const analysis = /^\/a\/([^/]+)$/.exec(path)
  if (analysis) return { name: "analysis", id: decodeURIComponent(analysis[1]) }
  return { name: "not-found", path }
}

const listeners = new Set<() => void>()

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  window.addEventListener("popstate", listener)
  return () => {
    listeners.delete(listener)
    window.removeEventListener("popstate", listener)
  }
}

function currentPath(): string {
  return window.location.pathname
}

export function navigate(
  path: string,
  options: { replace?: boolean } = {}
): void {
  if (options.replace) window.history.replaceState(null, "", path)
  else window.history.pushState(null, "", path)
  for (const listener of listeners) listener()
}

export function useRoute(): Route {
  const pathname = useSyncExternalStore(subscribe, currentPath)
  return useMemo(() => parseRoute(pathname), [pathname])
}
