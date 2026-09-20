import { describe, expect, it } from "vitest"

import { ANALYSIS_SECTIONS } from "@/lib/sections"

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
      section: "claims",
    })
    expect(parseRoute("/a/8ccb1a368d/")).toEqual({
      name: "analysis",
      id: "8ccb1a368d",
      section: "claims",
    })
    expect(parseRoute(paths.analysis("x y/z"))).toEqual({
      name: "analysis",
      id: "x y/z",
      section: "claims",
    })
  })

  it("reads the section from the next segment, and leaves the default one off", () => {
    for (const section of ANALYSIS_SECTIONS) {
      expect(parseRoute(paths.analysis("abc", section))).toEqual({
        name: "analysis",
        id: "abc",
        section,
      })
    }
    // The default section is not in the address, so /a/<id> stays the address of an analysis.
    expect(paths.analysis("abc")).toBe("/a/abc")
    expect(paths.analysis("abc", "claims")).toBe("/a/abc")
    expect(paths.analysis("abc", "verdict")).toBe("/a/abc/verdict")
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
    // A section the screen does not have is not an analysis with a stray segment.
    expect(parseRoute("/a/one/events")).toEqual({
      name: "not-found",
      path: "/a/one/events",
    })
    expect(parseRoute("/company/shell")).toEqual({
      name: "not-found",
      path: "/company/shell",
    })
  })
})
