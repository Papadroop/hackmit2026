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
