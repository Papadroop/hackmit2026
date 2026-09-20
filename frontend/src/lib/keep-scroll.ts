import { useLayoutEffect, useRef, type RefObject } from "react"

/** Where each scrolling area of one analysis was left, by section. Held by the screen, so it
 * is gone when the analysis is. */
export type ScrollStore = Map<string, number>

/**
 * Remembers how far a scrolling area was scrolled and puts it back when it returns. Moving
 * between the file's sections unmounts them, and without this, reading half-way down a
 * document and glancing at the verdict would cost the reader their place.
 */
export function useKeptScroll<T extends HTMLElement>(
  store: ScrollStore,
  key: string
): RefObject<T | null> {
  const ref = useRef<T>(null)
  useLayoutEffect(() => {
    const node = ref.current
    if (node === null) return
    node.scrollTop = store.get(key) ?? 0
    return () => {
      store.set(key, node.scrollTop)
    }
  }, [store, key])
  return ref
}
