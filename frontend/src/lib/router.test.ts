import { describe, expect, it } from "vitest"

import { parseRoute, paths } from "./router"

describe("parseRoute", () => {
  it("maps the root to the menu", () => {
    expect(parseRoute("/")).toEqual({ name: "menu" })
    expect(parseRoute("")).toEqual({ name: "menu" })
    expect(parseRoute("///")).toEqual({ name: "menu" })
  })

  it("maps /a/<id> to an analysis and round-trips through paths", () => {
    expect(parseRoute("/a/8ccb1a368d")).toEqual({
      name: "analysis",
      id: "8ccb1a368d",
    })
    expect(parseRoute("/a/8ccb1a368d/")).toEqual({
      name: "analysis",
      id: "8ccb1a368d",
    })
    expect(parseRoute(paths.analysis("x y/z"))).toEqual({
      name: "analysis",
      id: "x y/z",
    })
  })

  it("maps /calibration to the metrics page", () => {
    expect(parseRoute("/calibration")).toEqual({ name: "metrics" })
    expect(parseRoute(paths.metrics())).toEqual({ name: "metrics" })
    expect(parseRoute("/calibration/")).toEqual({ name: "metrics" })
  })

  it("maps /c/<company> to a company, by slug", () => {
    expect(parseRoute("/c/shell-plc")).toEqual({
      name: "company",
      slug: "shell-plc",
    })
    // The slug has to match company_slug in backend/auditor/company.py, or the link would
    // not find its own company.
    expect(parseRoute(paths.company("Ørsted A/S"))).toEqual({
      name: "company",
      slug: "orsted-a-s",
    })
  })

  it("reports everything else as not found", () => {
    expect(parseRoute("/a")).toEqual({ name: "not-found", path: "/a" })
    expect(parseRoute("/a/one/two")).toEqual({
      name: "not-found",
      path: "/a/one/two",
    })
    expect(parseRoute("/company/shell")).toEqual({
      name: "not-found",
      path: "/company/shell",
    })
  })
})
