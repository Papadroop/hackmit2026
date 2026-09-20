/** Per-viewer conveniences in localStorage. Every access is guarded: private windows and
 * blocked storage must never break the page. */
export function readPref<T>(
  key: string,
  fallback: T,
  accept: (value: unknown) => value is T
): T {
  try {
    const raw = localStorage.getItem(key)
    if (raw === null) return fallback
    const parsed: unknown = JSON.parse(raw)
    return accept(parsed) ? parsed : fallback
  } catch {
    return fallback
  }
}

export function writePref(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Storage unavailable; the preference just does not persist.
  }
}
