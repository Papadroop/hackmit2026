import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react"
import { ChevronDown, Copy } from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { api } from "@/lib/api"
import { ANALYSIS_FAILED, isLifecycle, type ReceivedEvent } from "@/lib/events"
import { cn } from "@/lib/utils"
import { useAnalysis, type AnalysisStatus } from "@/state/analysis"

const STATUS_LABEL: Record<AnalysisStatus, string> = {
  connecting: "Connecting",
  streaming: "Streaming",
  reconnecting: "Reconnecting",
  completed: "Completed",
  failed: "Failed",
  missing: "Missing",
}

/**
 * The raw event log (roadmap: "a debug drawer listing raw events stays in the app throughout").
 * Shows every envelope as received: its seq, the log's own time (t), the client arrival time
 * (recv), type and payload. It reads from the same state as the real views, so what it shows is
 * exactly what they were given.
 */
export function DebugDrawer({ onCollapse }: { onCollapse: () => void }) {
  const { state } = useAnalysis()
  const [filter, setFilter] = useState("")
  const [follow, setFollow] = useState(true)
  const [expandedSeq, setExpandedSeq] = useState<number | null>(null)
  const viewportRef = useRef<HTMLDivElement>(null)

  const needle = filter.trim().toLowerCase()
  const visible = useMemo(
    () =>
      needle
        ? state.events.filter((e) => e.type.toLowerCase().includes(needle))
        : state.events,
    [state.events, needle]
  )

  useEffect(() => {
    const viewport = viewportRef.current
    if (!follow || viewport === null) return
    viewport.scrollTop = viewport.scrollHeight
  }, [visible.length, follow])

  const handleScroll = () => {
    const viewport = viewportRef.current
    if (viewport === null) return
    const atBottom =
      viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 4
    if (atBottom !== follow) setFollow(atBottom)
  }

  const copyLog = async () => {
    const lines = state.events
      .map(({ seq, t_ms, type, payload }) =>
        JSON.stringify({ seq, t_ms, type, payload })
      )
      .join("\n")
    try {
      await navigator.clipboard.writeText(lines + "\n")
      toast.success(`Copied ${state.events.length} events as JSONL`)
    } catch {
      toast.error("Could not copy. Open the log link instead.")
    }
  }

  const lastT = state.events.at(-1)?.t_ms

  return (
    <section
      aria-label="Event log"
      className="flex h-full flex-col overflow-hidden bg-card text-sm"
    >
      <div className="flex items-center gap-3 border-b px-3 py-1.5">
        <h2 className="font-medium">Events</h2>
        <Badge variant="outline">{STATUS_LABEL[state.status]}</Badge>
        <span className="text-muted-foreground tabular-nums">
          {state.events.length} received
          {lastT !== undefined && `, last at ${(lastT / 1000).toFixed(1)} s`}
        </span>
        <a
          className="text-muted-foreground underline underline-offset-4 hover:text-foreground"
          href={api.logUrl(state.analysisId)}
          target="_blank"
          rel="noreferrer"
        >
          log
        </a>
        <div className="ml-auto flex items-center gap-3">
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter by type"
            aria-label="Filter events by type"
            className="h-7 w-44"
          />
          <div className="flex items-center gap-1.5">
            <Switch
              id="follow"
              size="sm"
              checked={follow}
              onCheckedChange={setFollow}
            />
            <Label htmlFor="follow" className="text-muted-foreground">
              Follow
            </Label>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={copyLog}
            disabled={state.events.length === 0}
          >
            <Copy />
            Copy
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onCollapse}
            aria-label="Hide events panel"
          >
            <ChevronDown />
          </Button>
        </div>
      </div>
      <div
        ref={viewportRef}
        onScroll={handleScroll}
        className="min-h-0 flex-1 overflow-auto"
      >
        {state.events.length === 0 ? (
          <p className="p-3 text-muted-foreground">No events yet.</p>
        ) : visible.length === 0 ? (
          <p className="p-3 text-muted-foreground">
            No event types contain “{filter.trim()}”.
          </p>
        ) : (
          <table className="w-full border-collapse text-[13px] tabular-nums">
            <thead className="sticky top-0 bg-card text-left text-muted-foreground">
              <tr>
                <th className="w-12 px-3 py-1 font-medium">#</th>
                <th className="w-20 px-2 py-1 font-medium">t (ms)</th>
                <th className="w-20 px-2 py-1 font-medium">recv (ms)</th>
                <th className="w-56 px-2 py-1 font-medium">type</th>
                <th className="px-2 py-1 font-medium">payload</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((event) => (
                <EventRow
                  key={event.seq}
                  event={event}
                  expanded={expandedSeq === event.seq}
                  onToggle={() =>
                    setExpandedSeq(expandedSeq === event.seq ? null : event.seq)
                  }
                />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}

function EventRow({
  event,
  expanded,
  onToggle,
}: {
  event: ReceivedEvent
  expanded: boolean
  onToggle: () => void
}) {
  const compact = JSON.stringify(event.payload)
  const failed = event.type === ANALYSIS_FAILED
  const onKeyDown = (e: KeyboardEvent<HTMLTableRowElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault()
      onToggle()
    }
  }
  return (
    <>
      <tr
        tabIndex={0}
        onClick={onToggle}
        onKeyDown={onKeyDown}
        aria-expanded={expanded}
        className={cn(
          "cursor-pointer border-t border-border/60 align-top outline-none hover:bg-muted/60 focus-visible:bg-muted/60",
          expanded && "bg-muted/40"
        )}
      >
        <td className="px-3 py-1 text-muted-foreground">{event.seq}</td>
        <td className="px-2 py-1 text-muted-foreground">{event.t_ms}</td>
        <td className="px-2 py-1 text-muted-foreground">{event.received_ms}</td>
        <td
          className={cn(
            "px-2 py-1",
            isLifecycle(event.type)
              ? "text-muted-foreground"
              : "text-foreground",
            failed && "text-destructive"
          )}
        >
          {event.type}
        </td>
        <td className="w-full max-w-0 truncate px-2 py-1 text-muted-foreground">
          {compact === "{}" ? "" : compact}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-muted/40">
          <td colSpan={5} className="px-3 pb-2">
            <pre className="text-xs break-words whitespace-pre-wrap">
              {JSON.stringify(event.payload, null, 2)}
            </pre>
          </td>
        </tr>
      )}
    </>
  )
}
