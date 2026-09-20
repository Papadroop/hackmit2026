import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react"

import {
  CalibrationStrip,
  ReliabilityCurve,
} from "@/components/calibration-plot"
import { ThemeToggle, Wordmark } from "@/components/chrome"
import { Link } from "@/components/link"
import { Button } from "@/components/ui/button"
import { ApiError, api } from "@/lib/api"
import {
  OUTCOME_LABELS,
  called,
  formatPercent,
  isMiss,
  measure,
  type CalibrationCase,
  type CalibrationReport,
} from "@/lib/calibration"
import { formatDate } from "@/lib/format"
import { paths } from "@/lib/router"
import { cn } from "@/lib/utils"

/**
 * /calibration: how far the audit's likelihood matches what regulators actually decided
 * (roadmap step 19). The page reads the artifact `python -m auditor.calibration run` wrote and
 * does the arithmetic again itself, so the threshold is a control rather than a constant: the
 * sweep the command line prints becomes something the reader can push on. Nothing here is a
 * stat tile — the numbers sit in one band, as the summary header does, and the caveat the run
 * attached to them is beside them rather than in fine print.
 */
export function MetricsScreen() {
  const [report, setReport] = useState<CalibrationReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [threshold, setThreshold] = useState(0.5)
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    api
      .getCalibration()
      .then((loaded) => {
        if (!live) return
        setReport(loaded)
        setThreshold(loaded.metrics.threshold)
      })
      .catch((caught: unknown) => {
        if (live)
          setError(
            caught instanceof ApiError
              ? caught.message
              : "Could not load the run."
          )
      })
    return () => {
      live = false
    }
  }, [])

  return (
    <div className="flex min-h-svh flex-col bg-background">
      <header className="flex items-center gap-4 border-b px-4 py-2.5 sm:px-6">
        <Wordmark />
        <p className="text-[15px] font-medium">Calibration</p>
        <div className="ml-auto flex items-center gap-1">
          <Button variant="ghost" size="sm" asChild>
            <Link href={paths.menu()}>Documents</Link>
          </Button>
          <ThemeToggle />
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
        {error !== null ? (
          <Unrun detail={error} />
        ) : report === null ? (
          <p className="text-[15px] text-muted-foreground">Reading the run…</p>
        ) : (
          <Report
            report={report}
            threshold={threshold}
            onThreshold={setThreshold}
            selected={selected}
            onSelect={setSelected}
          />
        )}
      </main>
    </div>
  )
}

/** No run yet. The backend's own message names the command that makes one. */
function Unrun({ detail }: { detail: string }) {
  return (
    <div className="max-w-[68ch]">
      <h1 className="text-[28px] leading-tight font-medium">
        Nothing has been measured yet
      </h1>
      <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">
        {detail}
      </p>
      <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">
        The run scores every curated precedent with its own ruling taken out of
        the knowledge store. It calls Claude once per case, so it is done ahead
        of time and read from disk here.
      </p>
    </div>
  )
}

function Report({
  report,
  threshold,
  onThreshold,
  selected,
  onSelect,
}: {
  report: CalibrationReport
  threshold: number
  onThreshold: Dispatch<SetStateAction<number>>
  selected: string | null
  onSelect: (storeId: string | null) => void
}) {
  const metrics = useMemo(
    () => measure(report.cases, threshold),
    [report.cases, threshold]
  )
  const ranked = useMemo(
    () =>
      [...report.cases].sort(
        (a, b) => (b.likelihood ?? 0) - (a.likelihood ?? 0)
      ),
    [report.cases]
  )
  const lowest = Math.min(...report.cases.map((kase) => kase.likelihood ?? 1))
  const largest = metrics.bins.reduce(
    (best, bin) => (best === null || bin.count > best.count ? bin : best),
    metrics.bins[0] ?? null
  )
  const rows = useRef(new Map<string, HTMLLIElement>())

  useEffect(() => {
    if (selected === null) return
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    rows.current.get(selected)?.scrollIntoView({
      block: "nearest",
      behavior: still ? "auto" : "smooth",
    })
  }, [selected])

  return (
    <>
      <h1 className="text-[28px] leading-tight font-medium">
        What the audit gets right, and where it does not
      </h1>
      <p className="mt-3 max-w-[68ch] text-[17px] leading-relaxed text-muted-foreground">
        Every precedent in the knowledge store is also a test of it. Each ruling
        is taken out of the store, the audit scores the wording that was ruled
        on, and the likelihood it arrives at is set against what the regulator
        decided. {metrics.scored} cases, none of them allowed to see its own
        answer.
      </p>

      <figure className="mt-8">
        <CalibrationStrip
          cases={report.cases}
          threshold={threshold}
          onThreshold={onThreshold}
          selectedId={selected}
          onSelect={onSelect}
        />
        <figcaption className="mt-2 max-w-[72ch] text-[13px] leading-relaxed text-muted-foreground">
          One mark per case, at the likelihood the audit gave it: filled where a
          regulator upheld the complaint, hollow where the advertiser was
          cleared. Drag the line, or focus it and use the arrow keys, to move
          where a claim is called misleading; the marks that change colour are
          the cases the audit and the regulator read differently. Nothing scored
          below <span className="tabular-nums">{lowest.toFixed(2)}</span>, so
          the bottom of the scale is empty: on this set the audit separates
          claims by how strongly it doubts them, not by whether it doubts them
          at all.
        </figcaption>
      </figure>

      <section aria-label="Metrics" className="mt-8 border-y bg-card px-4 py-3">
        <div className="flex flex-wrap items-baseline gap-x-8 gap-y-2 text-[13px]">
          <p className="flex items-baseline gap-2">
            <span className="text-muted-foreground">Precision</span>
            <span className="text-[22px] leading-none font-medium tabular-nums">
              {formatPercent(metrics.precision)}
            </span>
          </p>
          <p className="flex items-baseline gap-2">
            <span className="text-muted-foreground">Recall</span>
            <span className="text-[22px] leading-none font-medium tabular-nums">
              {formatPercent(metrics.recall)}
            </span>
          </p>
          <p className="flex items-baseline gap-2 text-muted-foreground">
            <span>F1</span>
            <span className="tabular-nums">{formatPercent(metrics.f1)}</span>
          </p>
          <p className="flex items-baseline gap-2 text-muted-foreground">
            <span>Accuracy</span>
            <span className="tabular-nums">
              {formatPercent(metrics.accuracy)}
            </span>
          </p>
          <p className="flex items-baseline gap-2 text-muted-foreground">
            <span>Brier score</span>
            <span className="tabular-nums">
              {metrics.brier === null ? "not yet" : metrics.brier.toFixed(3)}
            </span>
            <span>(0 is perfect)</span>
          </p>
        </div>
        <dl className="mt-3 grid gap-x-8 gap-y-1 text-[13px] sm:grid-cols-2">
          {[
            {
              label: "Called misleading, and upheld",
              count: metrics.truePositive,
            },
            {
              label: "Called misleading, but cleared",
              count: metrics.falsePositive,
            },
            { label: "Left alone, and cleared", count: metrics.trueNegative },
            { label: "Left alone, but upheld", count: metrics.falseNegative },
          ].map((cell) => (
            <div
              key={cell.label}
              className="flex items-baseline justify-between gap-3 border-b py-1"
            >
              <dt className="text-muted-foreground">{cell.label}</dt>
              <dd className="tabular-nums">{cell.count}</dd>
            </div>
          ))}
        </dl>
      </section>

      <p className="mt-3 max-w-[72ch] text-[13px] leading-relaxed text-muted-foreground">
        {report.metrics.caveat}
      </p>

      <section className="mt-10 flex flex-col gap-6 sm:flex-row sm:items-start sm:gap-10">
        <div className="shrink-0">
          <h2 className="text-[17px] font-medium">The calibration curve</h2>
          <div className="mt-3">
            <ReliabilityCurve bins={metrics.bins} />
          </div>
        </div>
        <div className="max-w-[60ch] text-[15px] leading-relaxed text-muted-foreground">
          <p>
            Cases are bucketed by what the audit predicted and set against how
            many of each bucket a regulator upheld. A point on the diagonal
            means a score of 0.8 was right about eight times in ten. A point's
            size is how many cases it rests on.
          </p>
          {largest !== null && (
            <p className="mt-3">
              The {largest.count} cases scored between{" "}
              <span className="tabular-nums">{largest.low.toFixed(1)}</span> and{" "}
              <span className="tabular-nums">{largest.high.toFixed(1)}</span>{" "}
              average a prediction of{" "}
              <span className="tabular-nums">
                {largest.predicted.toFixed(2)}
              </span>{" "}
              and were upheld{" "}
              <span className="tabular-nums">
                {formatPercent(largest.observed)}
              </span>{" "}
              of the time
              {Math.abs(largest.predicted - largest.observed) < 0.05
                ? ", which is the audit meaning what it says"
                : ""}
              .
            </p>
          )}
          <p className="mt-3">
            The curve is the number to read, because it does not depend on where
            the threshold is put. Precision and recall do, and this set has too
            few cases decided in the advertiser's favour to hold them up.
          </p>
        </div>
      </section>

      <section className="mt-10">
        <h2 className="text-[17px] font-medium">
          Every case, strongest call first
        </h2>
        <ul className="mt-3">
          {ranked.map((kase) => (
            <CaseRow
              key={kase.store_id}
              kase={kase}
              threshold={threshold}
              selected={kase.store_id === selected}
              onSelect={onSelect}
              register={(node) => {
                if (node) rows.current.set(kase.store_id, node)
                else rows.current.delete(kase.store_id)
              }}
            />
          ))}
        </ul>
      </section>

      <footer className="mt-10 max-w-[72ch] border-t pt-4 text-[13px] leading-relaxed text-muted-foreground">
        <p>{report.method}.</p>
        <p className="mt-1">
          Scored on {formatDate(report.generated)}. Materiality and consistency
          are not run: a precedent gives a bare wording with no page around it,
          and searching the web for a famous ruling's words would find the
          ruling that is being held out.
        </p>
      </footer>
    </>
  )
}

function CaseRow({
  kase,
  threshold,
  selected,
  onSelect,
  register,
}: {
  kase: CalibrationCase
  threshold: number
  selected: boolean
  onSelect: (storeId: string | null) => void
  register: (node: HTMLLIElement | null) => void
}) {
  const missed = isMiss(kase, threshold) === true
  const call = called(kase.likelihood, threshold)
  return (
    <li
      ref={register}
      className={cn("border-b last:border-b-0", selected && "bg-accent/60")}
    >
      <button
        type="button"
        onClick={() => onSelect(selected ? null : kase.store_id)}
        className="flex w-full items-baseline gap-4 px-2 py-3 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <span
          className={cn(
            "w-11 shrink-0 text-[15px] font-medium tabular-nums",
            missed && "text-verdict-contradicted"
          )}
        >
          {kase.likelihood === null ? "—" : kase.likelihood.toFixed(2)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[13px] text-muted-foreground">
            {[kase.company, kase.body].filter(Boolean).join(", ")}
          </span>
          <span className="mt-1 block border-l-2 border-graphite/40 pl-3 font-serif text-[15px] leading-snug">
            {kase.claim_text}
          </span>
          {missed && (
            <span className="mt-1.5 block text-[13px] text-verdict-contradicted">
              {call
                ? "The audit called this misleading; the regulator did not."
                : "The regulator upheld this; the audit let it pass."}
            </span>
          )}
        </span>
        <span className="w-28 shrink-0 text-right text-[13px] text-muted-foreground">
          {OUTCOME_LABELS[kase.outcome] ?? kase.outcome}
          {kase.label === null && <span className="block">no finding</span>}
        </span>
      </button>
    </li>
  )
}
