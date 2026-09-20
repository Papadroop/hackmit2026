import { useMemo, useSyncExternalStore } from "react"

import { companySlug } from "@/lib/company"
import {
  DEFAULT_SECTION,
  isAnalysisSection,
  type AnalysisSection,
} from "@/lib/sections"

/**
 * The URL is the source of truth for which screen is open. An analysis lives at
 * /a/<analysis id>, so a reload keeps it (the server still holds its log and the client
 * re-tails it), the back button works, and a run can be linked to. Its section is the next
 * segment, and the default one is left off, so /a/<id> stays the address of an analysis.
 */
export type Route =
  | { name: "menu" }
  | { name: "analysis"; id: string; section: AnalysisSection }
  | { name: "metrics" }
  | { name: "company"; slug: string }
  | { name: "not-found"; path: string }

export const paths = {
  menu: () => "/",
  analysis: (id: string, section: AnalysisSection = DEFAULT_SECTION) =>
    section === DEFAULT_SECTION
      ? `/a/${encodeURIComponent(id)}`
      : `/a/${encodeURIComponent(id)}/${section}`,
  metrics: () => "/calibration",
  company: (name: string) => `/c/${companySlug(name)}`,
}

export function parseRoute(pathname: string): Route {
  const path = pathname.replace(/\/+$/, "") || "/"
  if (path === "/") return { name: "menu" }
  if (path === "/calibration") return { name: "metrics" }
  const company = /^\/c\/([^/]+)$/.exec(path)
  if (company) return { name: "company", slug: decodeURIComponent(company[1]) }
  const analysis = /^\/a\/([^/]+)(?:\/([^/]+))?$/.exec(path)
  if (analysis) {
    const section = analysis[2]
    if (section === undefined)
      return {
        name: "analysis",
        id: decodeURIComponent(analysis[1]),
        section: DEFAULT_SECTION,
      }
    if (isAnalysisSection(section))
      return {
        name: "analysis",
        id: decodeURIComponent(analysis[1]),
        section,
      }
  }
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
