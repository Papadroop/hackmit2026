import { describe, expect, it } from "vitest"

import { companySlug, formatChange } from "./company"

describe("companySlug", () => {
  it("agrees with company_slug in backend/auditor/company.py", () => {
    // The endpoint resolves a name, its slug, or an unambiguous prefix; these are the slugs
    // the three demo companies have to produce for a link from this app to find them.
    expect(companySlug("Shell plc")).toBe("shell-plc")
    expect(companySlug("Ørsted A/S")).toBe("orsted-a-s")
    expect(companySlug("Apple Inc.")).toBe("apple-inc")
  })

  it("folds diacritics rather than dropping the letters", () => {
    expect(companySlug("Société Générale")).toBe("societe-generale")
    expect(companySlug("Łódź Æther")).toBe("lodz-aether")
    expect(companySlug("Größe")).toBe("grosse")
  })

  it("collapses runs of punctuation and trims the ends", () => {
    expect(companySlug("  --Foo & Bar,  Inc.--  ")).toBe("foo-bar-inc")
    expect(companySlug("!!!")).toBe("")
  })
})

describe("formatChange", () => {
  it("always carries the sign, because the sign is the message", () => {
    expect(formatChange(0.18)).toBe("+0.18")
    expect(formatChange(-0.18)).toBe("−0.18")
    expect(formatChange(0)).toBe("0.00")
  })
})
