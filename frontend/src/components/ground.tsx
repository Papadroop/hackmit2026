import { useEffect, useState } from "react"

import { paperGrain } from "@/lib/paper"

/**
 * The surface the whole menu sits on (../../menu-design.md §8): a dense canopy seen from the
 * air, veiled back until it is a ground rather than a photograph, with the paper's own fibre
 * tiled over it. Fixed under the forest, so the surface stays put while the page moves across
 * it, and on from the first frame — the rinse takes the pigment off the card, and what is under
 * the sheet is the forest itself.
 *
 * The photograph is `public/canopy.jpg`, "Aerial view of the Amazon Rainforest" by lubasi,
 * CC BY-SA 2.0, credited at the foot of the list. The fibre is generated once and goes out as
 * `--paper-grain`, because the sheets in the list are the same paper and take the same tile.
 */

let grain: string | null = null

export function Ground() {
  const [ready, setReady] = useState(grain !== null)

  useEffect(() => {
    if (grain !== null) return
    const frame = requestAnimationFrame(() => {
      grain = paperGrain()
      setReady(true)
    })
    return () => cancelAnimationFrame(frame)
  }, [])

  useEffect(() => {
    if (!ready || grain === null) return
    const root = document.documentElement
    root.style.setProperty("--paper-grain", `url("${grain}")`)
    return () => {
      root.style.removeProperty("--paper-grain")
    }
  }, [ready])

  return (
    <>
      <div className="rinse-ground" aria-hidden="true">
        <div className="rinse-canopy" />
        <div className="rinse-veil" />
      </div>
      {ready && <div className="rinse-grain" aria-hidden="true" />}
    </>
  )
}
