import { Moon, Sun } from "lucide-react"

import { Link } from "@/components/link"
import { useTheme } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"
import { paths } from "@/lib/router"

/**
 * The product name, always lowercase and always in italic Literata: in the application that
 * italic is the voice of the honest rewrite, so the name reads as the honest version
 * (../../menu-design.md §4.2). The menu screen shows no small wordmark; its title is the
 * wordmark.
 */
export function Wordmark() {
  return (
    <Link
      href={paths.menu()}
      className="wordmark wordmark-sm rounded-sm whitespace-nowrap outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      rinse
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
