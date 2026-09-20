/**
 * The honest version's redline (design-doc D6, roadmap step 9): how a claim's original words
 * become its honest rewrite. A word-level diff is shown only when it reads as a correction
 * (most words kept, few change runs); otherwise the whole span is replaced, which is what a
 * rewrite from scratch is.
 */
export type DiffOp = { type: "equal" | "delete" | "insert"; text: string }

export type RewritePlan = { mode: "words"; ops: DiffOp[] } | { mode: "block" }

/** Words only: the canonical text has single spaces, so joining with a space restores it. */
export function words(text: string): string[] {
  return text.split(/\s+/).filter((w) => w !== "")
}

/** Longest common subsequence over words, as equal, delete and insert runs. Runs of one
 * kept word between two changes are absorbed into the change so the result is not choppy. */
export function diffWords(a: string, b: string): DiffOp[] {
  const x = words(a)
  const y = words(b)
  const n = x.length
  const m = y.length
  // lcs[i][j] = length of the LCS of x[i..] and y[j..]
  const lcs: Uint16Array[] = Array.from(
    { length: n + 1 },
    () => new Uint16Array(m + 1)
  )
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] =
        x[i] === y[j]
          ? lcs[i + 1][j + 1] + 1
          : Math.max(lcs[i + 1][j], lcs[i][j + 1])
    }
  }
  const raw: { type: DiffOp["type"]; word: string }[] = []
  let i = 0
  let j = 0
  while (i < n || j < m) {
    if (i < n && j < m && x[i] === y[j]) {
      raw.push({ type: "equal", word: x[i] })
      i++
      j++
    } else if (j < m && (i >= n || lcs[i][j + 1] >= lcs[i + 1][j])) {
      raw.push({ type: "insert", word: y[j] })
      j++
    } else {
      raw.push({ type: "delete", word: x[i] })
      i++
    }
  }
  // Runs, then absorb single kept words that sit between two changes.
  const runs: { type: DiffOp["type"]; words: string[] }[] = []
  for (const { type, word } of raw) {
    const last = runs.at(-1)
    if (last !== undefined && last.type === type) last.words.push(word)
    else runs.push({ type, words: [word] })
  }
  for (let k = 1; k < runs.length - 1; k++) {
    const run = runs[k]
    if (run.type !== "equal" || run.words.length > 1) continue
    if (runs[k - 1].type === "equal" || runs[k + 1].type === "equal") continue
    runs.splice(
      k,
      1,
      { type: "delete", words: [...run.words] },
      { type: "insert", words: [...run.words] }
    )
  }
  // Order each change as delete then insert, and merge what is now adjacent.
  const ops: DiffOp[] = []
  let k = 0
  while (k < runs.length) {
    if (runs[k].type === "equal") {
      ops.push({ type: "equal", text: runs[k].words.join(" ") })
      k++
      continue
    }
    const deleted: string[] = []
    const inserted: string[] = []
    while (k < runs.length && runs[k].type !== "equal") {
      ;(runs[k].type === "delete" ? deleted : inserted).push(...runs[k].words)
      k++
    }
    if (deleted.length > 0)
      ops.push({ type: "delete", text: deleted.join(" ") })
    if (inserted.length > 0)
      ops.push({ type: "insert", text: inserted.join(" ") })
  }
  return ops
}

/** Word mode when at least half the original words survive in at most four change runs. */
export function planRewrite(original: string, rewrite: string): RewritePlan {
  const total = words(original).length
  if (total === 0) return { mode: "block" }
  const ops = diffWords(original, rewrite)
  const kept = ops
    .filter((op) => op.type === "equal")
    .reduce((n, op) => n + words(op.text).length, 0)
  let hunks = 0
  for (let k = 0; k < ops.length; k++) {
    if (ops[k].type !== "equal" && (k === 0 || ops[k - 1].type === "equal"))
      hunks++
  }
  if (kept / total < 0.5 || hunks > 4) return { mode: "block" }
  return { mode: "words", ops }
}

/** The text a reader of the honest version sees: kept and inserted words. */
export function honestText(ops: DiffOp[]): string {
  return ops
    .filter((op) => op.type !== "delete")
    .map((op) => op.text)
    .join(" ")
}
