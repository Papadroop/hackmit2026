import { Moon, Sun } from "lucide-react"

import { Link } from "@/components/link"
import { useTheme } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"
import { paths } from "@/lib/router"

export function Wordmark() {
  return (
    <Link
      href={paths.menu()}
      className="rounded-sm text-[15px] font-medium whitespace-nowrap outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      Greenwashing Auditor
    </Link>
  )
}

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const dark = theme === "dark"
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      onClick={() => setTheme(dark ? "light" : "dark")}
    >
      {dark ? <Sun /> : <Moon />}
    </Button>
  )
}
