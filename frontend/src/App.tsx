import { ThemeToggle, Wordmark } from "@/components/chrome"
import { Link } from "@/components/link"
import { Button } from "@/components/ui/button"
import { paths, useRoute } from "@/lib/router"
import { AnalysisScreen } from "@/screens/analysis"
import { CompanyScreen } from "@/screens/company"
import { MenuScreen } from "@/screens/menu"
import { MetricsScreen } from "@/screens/metrics"

export function App() {
  const route = useRoute()
  switch (route.name) {
    case "menu":
      return <MenuScreen />
    case "analysis":
      return <AnalysisScreen id={route.id} />
    case "metrics":
      return <MetricsScreen />
    case "company":
      return <CompanyScreen key={route.slug} slug={route.slug} />
    case "not-found":
      return <NotFound path={route.path} />
  }
}

function NotFound({ path }: { path: string }) {
  return (
    <div className="flex min-h-svh flex-col">
      <header className="flex items-center gap-3 px-6 py-3">
        <Wordmark />
        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </header>
      <main className="mx-auto w-full max-w-prose px-6 py-10">
        <h1 className="text-2xl font-medium">Nothing at this address</h1>
        <p className="mt-2 text-muted-foreground">
          There is no page at {path}.
        </p>
        <Button className="mt-6" asChild>
          <Link href={paths.menu()}>Choose a document</Link>
        </Button>
      </main>
    </div>
  )
}

export default App
