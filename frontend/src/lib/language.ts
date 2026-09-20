/**
 * Words for the Language layer (design-doc D4 Q2, contract `LanguageSignal`): the signal
 * kinds, the three polarities and their order of notice.
 */
import type { LanguageSignal, Polarity, SignalKind } from "@contract"

export const SIGNAL_KIND_LABELS: Record<SignalKind, string> = {
  hedge: "Hedge",
  vague_term: "Vague term",
  undefined_term: "Undefined term",
  comparative_without_baseline: "Comparative without a baseline",
  weak_verb: "Weak verb",
  qualifier_present: "Qualifier present",
  qualifier_absent: "Qualifier absent",
  scope_mismatch: "Scope mismatch",
  responsibility_diffusion: "Responsibility diffusion",
  framing: "Framing",
  ratio_language: "Ratio language",
  intensifier: "Intensifier",
  approximation: "Approximation",
  buried_admission: "Buried admission",
  prominence: "Prominence",
  share_of_attention: "Share of attention",
  emotive: "Emotive language",
  register: "Register",
}

/** Most notable first: what a word carrying several signals is styled as. */
export const POLARITY_ORDER: readonly Polarity[] = ["flag", "credit", "benign"]

export const POLARITY_LABELS: Record<Polarity, string> = {
  flag: "flagged",
  benign: "benign",
  credit: "counts in the text's favour",
}

export function isPolarity(value: unknown): value is Polarity {
  return (
    typeof value === "string" &&
    (POLARITY_ORDER as readonly string[]).includes(value)
  )
}

export function strongestPolarity(
  polarities: Iterable<Polarity>
): Polarity | null {
  let best: Polarity | null = null
  for (const polarity of polarities) {
    if (
      best === null ||
      POLARITY_ORDER.indexOf(polarity) < POLARITY_ORDER.indexOf(best)
    )
      best = polarity
  }
  return best
}

export function signalKindLabel(kind: string): string {
  return SIGNAL_KIND_LABELS[kind as SignalKind] ?? kind
}

/** "Undefined term: term of art defined only on the FAQ page." for a mark's tooltip. */
export function describeSignal(signal: LanguageSignal): string {
  const kind = signalKindLabel(signal.kind)
  return signal.note === "" ? kind : `${kind}: ${signal.note}`
}

export function signalsForClaim(
  signals: readonly LanguageSignal[],
  claimId: string
): LanguageSignal[] {
  return signals.filter((signal) => signal.claim_ids.includes(claimId))
}
