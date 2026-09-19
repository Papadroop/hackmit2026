// Smoke test for the frontend stack. Replace with the real app (roadmap step 3).
import { useState } from "react"
import { motion } from "motion/react"
import { Leaf, Moon, ScanSearch, Sun } from "lucide-react"
import { toast } from "sonner"

import { useTheme } from "@/components/theme-provider"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"

export function App() {
  const [runs, setRuns] = useState(0)
  const { theme, setTheme } = useTheme()

  return (
    <main className="flex min-h-svh items-center justify-center p-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: "easeOut" }}
      >
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Leaf className="size-5" aria-hidden />
              Greenwashing Auditor
            </CardTitle>
            <CardDescription>
              Stack check: Tailwind, shadcn/ui, Motion and Lucide are wired up.
              Press <kbd>d</kbd> to toggle dark mode.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-3">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  onClick={() => {
                    setRuns((n) => n + 1)
                    toast.success("Analysis started")
                  }}
                >
                  <ScanSearch />
                  Analyse
                </Button>
              </TooltipTrigger>
              <TooltipContent>Runs the fixture replay</TooltipContent>
            </Tooltip>
            <Button
              variant="outline"
              size="icon"
              aria-label="Toggle theme"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            >
              {theme === "dark" ? <Sun /> : <Moon />}
            </Button>
            <Badge variant="secondary">Runs: {runs}</Badge>
          </CardContent>
        </Card>
      </motion.div>
    </main>
  )
}

export default App
