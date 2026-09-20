import { useTheme } from "@/components/theme-provider"
import { useMediaQuery } from "@/lib/use-media-query"

/** The theme actually in force, with "system" resolved against the viewer's own setting. */
export function useResolvedTheme(): "light" | "dark" {
  const { theme } = useTheme()
  const systemDark = useMediaQuery("(prefers-color-scheme: dark)")
  if (theme === "system") return systemDark ? "dark" : "light"
  return theme
}
