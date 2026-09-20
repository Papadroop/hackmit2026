import { useEffect, useState } from "react"

import { ThemeToggle, Wordmark } from "@/components/chrome"
import { Link } from "@/components/link"
import { ScoreBar } from "@/components/score-bar"
import { TrendLine } from "@/components/trend-line"
import { VerdictMark } from "@/components/verdict-mark"
import { Button } from "@/components/ui/button"
import { ApiError, api } from "@/lib/api"
import {
  TREND_LABELS,
  describeDateBasis,
  formatChange,
  type CompanyDocument,
  type CompanyView,
} from "@/lib/company"
import { VERDICT_LABELS, VERDICT_ORDER, formatScore } from "@/lib/encoding"
import { PROFILE_LABELS, PROFILE_ORDER } from "@/lib/evidence"
import { formatDate, formatNumber } from "@/lib/format"
import { paths } from "@/lib/router"

/**
 * /c/<company>: one company across its documents, with the trend (roadmap step 18, design-doc
 * D6; the "zoom out to the company" of the demo narrative).
 *
 * The company's headline is not a fifth opinion — it is a weighted mean of the documents listed
 * beneath it, and every row carries the share of the headline it accounts for, so the number
 * can be read back to the page that caused it. The trend is the reason the view exists, so it
 * comes first and says in words what this many documents can support: two points are a step,
 * not a trend, and one document is not a trend at all.
 */
export function CompanyScreen({ slug }: { slug: string }) {
  // Mounted with `key={slug}` in App.tsx, as the analysis screen is keyed by its id, so a
  // different company starts from nothing instead of showing the last one's numbers.
  const [view, setView] = useState<CompanyView | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    api
      .getCompany(slug)
      .then((loaded) => live && setView(loaded))
      .catch((caught: unknown) => {
        if (live)
          setError(
            caught instanceof ApiError
              ? caught.message
              : "Could not load the company."
          )
      })
    return () => {
      live = false
    }
  }, [slug])

  return (
    <div className="flex min-h-svh flex-col bg-background">
      <header className="flex items-center gap-4 border-b px-4 py-2.5 sm:px-6">
        <Wordmark />
        <p className="truncate text-[15px] font-medium">
          {view?.company.name ?? "Company"}
        </p>
        <div className="ml-auto flex items-center gap-1">
          <Button variant="ghost" size="sm" asChild>
            <Link href={paths.menu()}>Documents</Link>
          </Button>
          <ThemeToggle />
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
        {error !== null ? (
          <div className="max-w-[68ch]">
            <h1 className="text-[28px] leading-tight font-medium">
              Nothing to show for this company yet
            </h1>
            <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">
              {error}
            </p>
            <Button className="mt-6" asChild>
              <Link href={paths.menu()}>Choose a document</Link>
            </Button>
          </div>
        ) : view === null ? (
          <p className="text-[15px] text-muted-foreground">
            Reading the analyses…
          </p>
        ) : (
          <View view={view} />
        )}
      </main>
    </div>
  )
}

function View({ view }: { view: CompanyView }) {
  const { trend } = view
  const plotted = view.documents.filter((document) => document.date).length
  const titles = new Map(
    view.documents.map((document) => [document.document_id, document.title])
  )
  const named = (id: string, target: string) =>
    `${titles.get(id) ?? id}, ${target}`
  const counts = [
    `${view.document_count} ${view.document_count === 1 ? "document" : "documents"}`,
    `${formatNumber(view.claim_count)} ${view.claim_count === 1 ? "claim" : "claims"}`,
    `${view.omission_count} ${view.omission_count === 1 ? "omission" : "omissions"}`,
  ].join(", ")

  return (
    <>
      <h1 className="text-[28px] leading-tight font-medium">
        {view.company.name}
      </h1>
      <p className="mt-2 text-[15px] text-muted-foreground">
        {[view.industry?.label, counts].filter(Boolean).join(", ")}
      </p>

      <section
        aria-label="Across the documents"
        className="mt-6 border-y bg-card px-4 py-3 text-[13px]"
      >
        <div className="flex flex-wrap items-baseline gap-x-8 gap-y-2">
          <p className="flex items-baseline gap-2 whitespace-nowrap">
            <span className="text-muted-foreground">Likelihood</span>
            <span className="text-[22px] leading-none font-medium tabular-nums">
              {formatScore(view.headline.score)}
            </span>
            <span className="text-muted-foreground tabular-nums">
              confidence {formatScore(view.headline.confidence)}
            </span>
          </p>
          <ul className="flex flex-wrap items-baseline gap-x-5 gap-y-1">
            {PROFILE_ORDER.map((dimension) => {
              const entry = view.dimensions[dimension]
              if (!entry) return null
              return (
                <li
                  key={dimension}
                  className="flex items-baseline gap-1.5 whitespace-nowrap"
                >
                  <span className="text-muted-foreground">
                    {PROFILE_LABELS[dimension]}
                  </span>
                  <ScoreBar
                    score={entry.score}
                    confidence={entry.confidence}
                    className="w-10"
                  />
                  <span className="tabular-nums">
                    {formatScore(entry.score)}
                  </span>
                </li>
              )
            })}
          </ul>
        </div>
        <ul className="mt-2 flex flex-wrap items-baseline gap-x-5 gap-y-1">
          {VERDICT_ORDER.map((category) => (
            <li key={category} className="whitespace-nowrap tabular-nums">
              {view.verdict_distribution[category]}{" "}
              <VerdictMark category={category} confidence={0.85}>
                {VERDICT_LABELS[category].toLowerCase()}
              </VerdictMark>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-10">
        <h2 className="text-[17px] font-medium">Over time</h2>
        {plotted >= 2 && (
          <div className="mt-4">
            <TrendLine documents={view.documents} />
          </div>
        )}
        <p className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[15px]">
          <span className="font-medium">{TREND_LABELS[trend.direction]}</span>
          {trend.change !== null && (
            <span className="text-muted-foreground tabular-nums">
              {formatChange(trend.change)} across {trend.points} documents
            </span>
          )}
          <span className="text-muted-foreground tabular-nums">
            confidence {formatScore(trend.confidence)}
          </span>
        </p>
        <p className="mt-2 max-w-[72ch] text-[13px] leading-relaxed text-muted-foreground">
          {trend.note}
        </p>
      </section>

      <section className="mt-10">
        <h2 className="text-[17px] font-medium">The documents, oldest first</h2>
        <ul className="mt-3">
          {view.documents.map((document) => (
            <DocumentRow key={document.document_id} document={document} />
          ))}
        </ul>
      </section>

      {(view.top_issues.length > 0 || view.credit.length > 0) && (
        <section className="mt-10 grid gap-8 sm:grid-cols-2">
          {view.top_issues.length > 0 && (
            <div>
              <h2 className="text-[17px] font-medium">Worst findings</h2>
              <ol className="mt-3 space-y-2">
                {view.top_issues.map((issue) => (
                  <li
                    key={`${issue.document_id}:${issue.target}`}
                    className="flex gap-3 text-[15px] leading-snug"
                  >
                    <span className="w-4 shrink-0 text-muted-foreground tabular-nums">
                      {issue.rank}
                    </span>
                    <span>
                      {issue.title}
                      <span className="mt-0.5 block text-[13px] text-muted-foreground">
                        {named(issue.document_id, issue.target)}
                      </span>
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          )}
          {view.credit.length > 0 && (
            <div>
              <h2 className="text-[17px] font-medium">Credit where due</h2>
              <ul className="mt-3 space-y-2">
                {view.credit.map((entry) => (
                  <li
                    key={`${entry.document_id}:${entry.target}`}
                    className="text-[15px] leading-snug"
                  >
                    {entry.title}
                    <span className="mt-0.5 block text-[13px] text-muted-foreground">
                      {named(entry.document_id, entry.target)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <Derivation view={view} />
    </>
  )
}

function DocumentRow({ document }: { document: CompanyDocument }) {
  const basis = describeDateBasis(document.date_basis)
  return (
    <li className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b py-3 last:border-b-0">
      <span className="w-28 shrink-0 text-[13px] text-muted-foreground">
        {document.date ? formatDate(document.date) : "undated"}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[15px] leading-snug font-medium">
          {document.title}
        </span>
        <span className="mt-0.5 block text-[13px] text-muted-foreground">
          {[
            basis,
            `${document.claim_count} claims`,
            document.omission_count > 0
              ? `${document.omission_count} omissions`
              : null,
            `${Math.round(document.share * 100)}% of the company's number`,
          ]
            .filter(Boolean)
            .join(", ")}
        </span>
      </span>
      <span className="flex shrink-0 items-baseline gap-2">
        <ScoreBar
          score={document.headline.score}
          confidence={document.headline.confidence}
        />
        <span className="w-9 text-[15px] font-medium tabular-nums">
          {formatScore(document.headline.score)}
        </span>
      </span>
    </li>
  )
}

/** The company number said as arithmetic, because a number nobody can retrace is the thing
 * this page exists not to be. */
function Derivation({ view }: { view: CompanyView }) {
  const ext = (view.ext ?? {}) as {
    power?: number
    halflife_days?: number
    notes?: string[]
  }
  const years =
    ext.halflife_days === undefined
      ? null
      : Math.round((ext.halflife_days / 365) * 10) / 10

  return (
    <footer className="mt-10 max-w-[72ch] border-t pt-4 text-[13px] leading-relaxed text-muted-foreground">
      <p>
        The company's likelihood is a weighted mean of the documents above,
        leaning towards the worst of them
        {ext.power === undefined ? "" : ` (power ${ext.power})`}, so a page that
        does not say much cannot bury one that does. Each document's say is how
        recent it is, times the confidence of its own header, times the square
        of its score
        {years === null
          ? ""
          : `; recency halves every ${years} ${years === 1 ? "year" : "years"}`}
        . The share beside each document is what it accounts for.
      </p>
      <p className="mt-2">
        The headline says what the worst of the record is; the trend says which
        way it is moving. One number cannot do both, so a company that has
        cleaned up still reads high here until the older page has aged out of
        the weighting.
      </p>
      {(ext.notes ?? []).map((note) => (
        <p key={note} className="mt-2">
          {note}
        </p>
      ))}
    </footer>
  )
}
