/* Generated from contract/schema.json by contract/tools/gen_types.sh. Do not edit. */

/**
 * One line of the event log: the transport envelope (fixtures/README.md) with a contract payload. seq may be omitted in files (assigned from line order); t_ms is milliseconds since analysis.started, non-decreasing.
 */
export type Event = {
  seq?: number;
  t_ms: number;
  type: EventType;
  payload: {};
} & Event1;
export type EventType =
  | "analysis.started"
  | "stage.started"
  | "stage.completed"
  | "document.ingested"
  | "claim.extracted"
  | "language.signal"
  | "evidence.added"
  | "dimension.scored"
  | "omission.found"
  | "argument.made"
  | "verdict.issued"
  | "summary.updated"
  | "analysis.completed"
  | "analysis.failed"
  | "debug.note";
export type Event1 =
  | {
      type?: "analysis.started";
      payload?: P_AnalysisStarted;
    }
  | {
      type?: "stage.started";
      payload?: P_Stage;
    }
  | {
      type?: "stage.completed";
      payload?: P_Stage;
    }
  | {
      type?: "document.ingested";
      payload?: P_Document;
    }
  | {
      type?: "claim.extracted";
      payload?: P_Claim;
    }
  | {
      type?: "language.signal";
      payload?: P_Signal;
    }
  | {
      type?: "evidence.added";
      payload?: P_Evidence;
    }
  | {
      type?: "dimension.scored";
      payload?: P_Score;
    }
  | {
      type?: "omission.found";
      payload?: P_Omission;
    }
  | {
      type?: "argument.made";
      payload?: P_Argument;
    }
  | {
      type?: "verdict.issued";
      payload?: P_Verdict;
    }
  | {
      type?: "summary.updated";
      payload?: P_Summary;
    }
  | {
      type?: "analysis.completed";
      payload?: P_AnalysisCompleted;
    }
  | {
      type?: "analysis.failed";
      payload?: P_AnalysisFailed;
    }
  | {
      type?: "debug.note";
      payload?: P_DebugNote;
    };
/**
 * Stable identifier. Fixture ids are short (C1, L11, E8b, X3, O2); live ids may be generated. Unique across all entity types within one analysis.
 */
export type Id = string;
export type Mode = "fixture" | "live" | "replay";
/**
 * Pipeline stages, in canonical order, named as in fixtures/README.md. language = Linguistic evaluator (D5), substantiate = Substantiation evaluator, verify = External verification, consistency = Self-consistency. The four evaluators and omissions may run concurrently after extract; verdict waits for all of them; summary waits for verdict.
 */
export type Stage =
  | "ingest"
  | "extract"
  | "language"
  | "substantiate"
  | "verify"
  | "consistency"
  | "omissions"
  | "verdict"
  | "summary";
/**
 * The brief's kinds (label, policy, claim) plus common concrete forms.
 */
export type TextType = "label" | "policy" | "claim" | "press_release" | "web_page" | "report" | "other";
export type Date = string;
export type RegionKind =
  | "title"
  | "heading"
  | "paragraph"
  | "list_item"
  | "footnote"
  | "cautionary_note"
  | "promo"
  | "quote"
  | "caption"
  | "other";
/**
 * D4 Q1. Routes evaluation: factual claims are verified; commitments tested for credibility; comparatives need their baseline; certifications checked for existence and coverage; vague attributes are unverifiable by construction.
 */
export type ClaimType = "factual" | "commitment" | "comparative" | "vague_attribute" | "certification";
export type Scope = "product" | "packaging" | "operations" | "supply_chain" | "company" | "other";
export type Score01 = number;
/**
 * D4 Q2. Claim-level kinds are the first fourteen; prominence, share_of_attention, emotive and register may also be document-level.
 */
export type SignalKind =
  | "hedge"
  | "vague_term"
  | "undefined_term"
  | "comparative_without_baseline"
  | "weak_verb"
  | "qualifier_present"
  | "qualifier_absent"
  | "scope_mismatch"
  | "responsibility_diffusion"
  | "framing"
  | "ratio_language"
  | "intensifier"
  | "approximation"
  | "buried_admission"
  | "prominence"
  | "share_of_attention"
  | "emotive"
  | "register";
/**
 * flag = a greenwashing signal; benign = noted but harmless (so the Language layer visibly does not flag everything); credit = a qualifier or precision that counts in the text's favour.
 */
export type Polarity = "flag" | "benign" | "credit";
export type EvidenceItem = EvidenceItem1 & {
  id: Id;
  kind: EvidenceKind;
  tier: Tier;
  source: {
    name: string;
    publisher?: string;
    /**
     * Publication or decision date, ISO date or free text if only a year/month is known.
     */
    date?: string;
    /**
     * Page, paragraph, section or case reference.
     */
    locator?: string;
  };
  url?: string;
  /**
   * Verbatim text from the source. Displayed only when verified.
   */
  quote?: string;
  verified: boolean;
  verification: Verification;
  retrieved: Date;
  /**
   * Pipeline stages, in canonical order, named as in fixtures/README.md. language = Linguistic evaluator (D5), substantiate = Substantiation evaluator, verify = External verification, consistency = Self-consistency. The four evaluators and omissions may run concurrently after extract; verdict waits for all of them; summary waits for verdict.
   */
  stage?:
    | "ingest"
    | "extract"
    | "language"
    | "substantiate"
    | "verify"
    | "consistency"
    | "omissions"
    | "verdict"
    | "summary";
  /**
   * @minItems 1
   */
  links: [
    {
      /**
       * Stable identifier. Fixture ids are short (C1, L11, E8b, X3, O2); live ids may be generated. Unique across all entity types within one analysis.
       */
      target: string;
      relation: Relation;
    },
    ...{
      /**
       * Stable identifier. Fixture ids are short (C1, L11, E8b, X3, O2); live ids may be generated. Unique across all entity types within one analysis.
       */
      target: string;
      relation: Relation;
    }[]
  ];
  /**
   * For kind=computation: a number recomputed from other evidence.
   */
  computation?: {
    formula: string;
    inputs: {};
    result: string;
  };
  /**
   * Evidence ids this item was computed from.
   */
  derived_from?: Id[];
  note?: string;
  ext?: Ext;
};
export type EvidenceItem1 = {
  [k: string]: unknown;
};
export type EvidenceKind =
  | "ruling"
  | "law"
  | "filing"
  | "report"
  | "dataset"
  | "standard"
  | "company_page"
  | "press_release"
  | "news"
  | "archive"
  | "computation"
  | "other";
/**
 * D5 reliability tier. 1 regulator ruling, court judgment, law; 2 audited/assured filing, government or intergovernmental data; 3 independent third-party dataset or standard; 4 news; 5 the company's own material.
 */
export type Tier = number;
/**
 * fetched_exact: quote matched programmatically against the fetched source; fetched_by_eye: read from the fetched source by a person; second_party_fetch: fetched and quoted by a separate verification run; computed: the item is a computation, its quote is the result statement and its verification rests on derived_from; unverified: never displayed as a quote.
 */
export type Verification = "fetched_exact" | "fetched_by_eye" | "second_party_fetch" | "computed" | "unverified";
/**
 * From the target's point of view. supports/contradicts concern the literal content; contradicts_framing means the literal content stands but the impression does not; context is background or materiality; precedent is a ruling on similar wording; criteria is a rule the claim is measured against. For an omission target, supports means the evidence establishes the omitted fact.
 */
export type Relation = "supports" | "contradicts" | "contradicts_framing" | "context" | "precedent" | "criteria";
/**
 * D6 claim-level dimensions. Completeness is document-level and lives in Summary.
 */
export type Dimension = "clarity" | "support" | "materiality" | "consistency";
export type VerdictCategory = "supported" | "unsubstantiated" | "misleading_by_framing" | "contradicted";
/**
 * The seven sins of greenwashing plus greenrinsing (a target changed before it is met, from Planet Tracker's taxonomy).
 */
export type Tag =
  | "hidden_trade_off"
  | "no_proof"
  | "vagueness"
  | "irrelevance"
  | "lesser_of_two_evils"
  | "fibbing"
  | "false_labels"
  | "greenrinsing";
/**
 * Which way the headline moved between the company's oldest and newest document. Scores are problem scores, so `worsening` means the headline went up. `undetermined` is for fewer than two dated documents: a company with one page has not held still, it has not been watched.
 */
export type TrendDirection = "improving" | "worsening" | "steady" | "undetermined";

export interface Contract {
  event?: Event;
  analysis?: Analysis;
  company?: CompanyView;
}
/**
 * Descriptive keys are allowed (the transport adds `source`). contract_version is required so a consumer can refuse a log it does not understand.
 */
export interface P_AnalysisStarted {
  contract_version: string;
  analysis_id?: Id;
  mode?: Mode;
  document_ref?: {
    url?: string;
    title?: string;
  };
  source?: {};
  [k: string]: unknown;
}
export interface P_Stage {
  stage: Stage;
  /**
   * Human text for the progress display, e.g. 'Finding claims'.
   */
  label?: string;
  note?: string;
}
export interface P_Document {
  document: Document;
}
export interface Document {
  id: Id;
  title: string;
  company: Company;
  industry: Industry;
  text_type: TextType;
  source: {
    url?: string;
    retrieved: Date;
    /**
     * How the text was obtained (e.g. AEM model JSON, static HTML, PDF).
     */
    method?: string;
    archive_url?: string;
    /**
     * Repo path of the saved text, if any.
     */
    fixture_path?: string;
  };
  language?: string;
  /**
   * Canonical plain text. Rules: NFC-normalised; every Unicode space character (including U+00A0) becomes an ASCII space; no tabs or carriage returns; no runs of spaces; \n line breaks; blocks separated by exactly one blank line; no leading or trailing whitespace; no markdown markers. All spans index into this string by Unicode code point.
   */
  text: string;
  word_count?: number;
  regions: Region[];
  ext?: Ext;
}
export interface Company {
  name: string;
  aliases?: string[];
  ticker?: string;
  /**
   * ISO 3166-1 alpha-2
   */
  country?: string;
  sec_cik?: string;
  ext?: Ext;
}
/**
 * Free extension bag. Anything not in the contract goes here so additionalProperties can stay false everywhere else.
 */
export interface Ext {}
export interface Industry {
  label: string;
  /**
   * SASB industry codes used as the materiality reference, e.g. EM-EP.
   */
  sasb_codes?: string[];
  ext?: Ext;
}
/**
 * A labelled range of Document.text. Regions of the same kind must not overlap; different kinds may nest (a paragraph may contain list_items). Used for prominence weighting and for scrolling to paragraph labels.
 */
export interface Region {
  kind: RegionKind;
  start: number;
  end: number;
  /**
   * Human label such as P4 or 'Cautionary note'.
   */
  label?: string;
  /**
   * Heading level, for kind=heading.
   */
  level?: number;
  /**
   * 1.0 = headline/hero, 0.6 = body, 0.3 = footnote or cautionary note.
   */
  prominence?: number;
}
export interface P_Claim {
  claim: Claim;
}
export interface Claim {
  id: Id;
  /**
   * First span is the primary highlight; further spans are repeats of the same claim elsewhere in the text.
   *
   * @minItems 1
   */
  spans: [Span, ...Span[]];
  type: ClaimType;
  scope: Scope;
  /**
   * Precise scope in words, e.g. 'operated upstream assets only'.
   */
  scope_note?: string;
  /**
   * What is asserted: net zero, -36%, cleaner, ...
   */
  attribute: string;
  quantity?: string;
  baseline?: string;
  timeframe?: string;
  /**
   * Label of the paragraph region the primary span sits in (P1...).
   */
  paragraph?: string;
  prominence?: Score01;
  note?: string;
  ext?: Ext;
}
/**
 * A verbatim substring of Document.text. `text` is authoritative; `start`/`end` are Unicode code-point offsets into Document.text and must satisfy text == Document.text[start:end]. `context` and `occurrence` are authoring hints used to re-anchor the span if offsets go stale.
 */
export interface Span {
  text: string;
  start: number;
  end: number;
  /**
   * A unique substring of Document.text that contains `text`; disambiguates repeated phrases.
   */
  context?: string;
  /**
   * 1-based index of which occurrence of `text` in Document.text is meant, when `context` is not given.
   */
  occurrence?: number;
}
export interface P_Signal {
  signal: LanguageSignal;
}
export interface LanguageSignal {
  id: Id;
  level: "claim" | "document";
  kind: SignalKind;
  polarity: Polarity;
  /**
   * Word-level marks. Required non-empty for level=claim; may be empty for level=document.
   */
  spans: Span[];
  note: string;
  claim_ids: Id[];
  strength?: Score01;
  ext?: Ext;
}
export interface P_Evidence {
  evidence: EvidenceItem;
}
export interface P_Score {
  score: DimensionScore;
}
/**
 * score is a problem score: 0 = no greenwashing signal on this dimension, 1 = maximal. confidence is how sure the evaluator is of that score.
 */
export interface DimensionScore {
  claim_id: Id;
  dimension: Dimension;
  score: Score01;
  confidence: Score01;
  /**
   * One sentence saying why.
   */
  basis: string;
  evidence_ids?: Id[];
  stage?: Stage;
  ext?: Ext;
}
export interface P_Omission {
  omission: Omission;
}
export interface Omission {
  id: Id;
  /**
   * Short title for the margin card: 'Not mentioned: ...'.
   */
  topic: string;
  why_material: string;
  /**
   * The external reference that makes it material, e.g. 'SASB EM-EP: Reserves Valuation & Capital Expenditures'.
   */
  materiality_reference?: string;
  /**
   * What the document would say if it were complete.
   */
  complete_text?: string;
  score: Score01;
  confidence: Score01;
  evidence_ids?: Id[];
  ext?: Ext;
}
export interface P_Argument {
  argument: Argument;
}
export interface Argument {
  claim_id: Id;
  role: "prosecutor" | "defence" | "judge";
  text: string;
  evidence_ids?: Id[];
  ext?: Ext;
}
export interface P_Verdict {
  verdict: Verdict;
}
/**
 * likelihood = max of the claim's four dimension scores (weakest link). category is derived from the scores and the evidence relations by the rule in CONTRACT.md §6.
 */
export interface Verdict {
  claim_id: Id;
  likelihood: Score01;
  confidence: Score01;
  category: VerdictCategory;
  tags: Tag[];
  /**
   * The judge's reasoning, one to three sentences.
   */
  rationale: string;
  /**
   * What evidence or rewording would make the claim legitimate.
   */
  fix?: string;
  /**
   * The claim as the evidence would allow it to be stated.
   */
  rewrite?: string;
  evidence_ids?: Id[];
  ext?: Ext;
}
export interface P_Summary {
  summary: Summary;
  /**
   * True for the last summary of the analysis; earlier ones are provisional and may be replaced.
   */
  final: boolean;
}
export interface Summary {
  headline: ProfileEntry;
  dimensions: DimensionProfile;
  verdict_distribution: VerdictDistribution;
  top_issues: {
    rank: number;
    /**
     * Stable identifier. Fixture ids are short (C1, L11, E8b, X3, O2); live ids may be generated. Unique across all entity types within one analysis.
     */
    target: string;
    title: string;
  }[];
  /**
   * Credit where due: well-substantiated claims.
   */
  credit: {
    target: Id;
    title: string;
  }[];
  claim_count: number;
  omission_count: number;
  narrative?: string;
  ext?: Ext;
}
/**
 * score is the document's greenwashing likelihood.
 */
export interface ProfileEntry {
  score: Score01;
  confidence: Score01;
}
/**
 * The five D6 dimensions, each with its own score and confidence. Completeness is document-level, so at claim level it has no score of its own.
 */
export interface DimensionProfile {
  clarity: ProfileEntry1;
  support: ProfileEntry1;
  materiality: ProfileEntry1;
  consistency: ProfileEntry1;
  completeness: ProfileEntry1;
}
export interface ProfileEntry1 {
  score: Score01;
  confidence: Score01;
}
/**
 * How many claims fell into each verdict category. Must equal the verdicts counted.
 */
export interface VerdictDistribution {
  supported: number;
  unsubstantiated: number;
  misleading_by_framing: number;
  contradicted: number;
}
export interface P_AnalysisCompleted {
  duration_ms?: number;
  counts?: {
    claims: number;
    signals: number;
    evidence: number;
    omissions: number;
  };
}
export interface P_AnalysisFailed {
  /**
   * 'cancelled' when the user stopped it.
   */
  error: string;
  stage?: Stage;
}
/**
 * Free-form note for the debug drawer.
 */
export interface P_DebugNote {
  text: string;
  [k: string]: unknown;
}
/**
 * The folded result of one analysis: what the frontend holds in memory after consuming the event log, and what the fixture is authored as.
 */
export interface Analysis {
  /**
   * Stable identifier. Fixture ids are short (C1, L11, E8b, X3, O2); live ids may be generated. Unique across all entity types within one analysis.
   */
  analysis_id: string;
  contract_version: string;
  mode: Mode;
  document: Document;
  claims: Claim[];
  signals: LanguageSignal[];
  evidence: EvidenceItem1[];
  scores: DimensionScore[];
  arguments: Argument[];
  verdicts: Verdict[];
  omissions: Omission[];
  summary?: Summary;
  ext?: Ext;
}
/**
 * One company's analyses side by side, with the trend over time (D2's third zoom level, D6 "Aggregation"). Served by GET /api/company/{name} and built by backend/auditor/company.py; not part of an event stream, because it spans analyses. Every number is arithmetic over the documents listed beneath it and records its contributors in ext.drivers; only the narrative is written.
 */
export interface CompanyView {
  company: Company;
  industry?: Industry;
  headline: ProfileEntry2;
  dimensions: DimensionProfile;
  verdict_distribution: VerdictDistribution1;
  /**
   * Every document of this company that has a complete analysis, oldest first: the trend's order.
   */
  documents: CompanyDocument[];
  trend: CompanyTrend;
  /**
   * The company's worst findings across its documents, ranked by the same weighted severity the aggregation uses. A target is (document_id, target): claim and omission ids are unique within one analysis only.
   */
  top_issues: {
    rank: number;
    document_id: Id;
    /**
     * Stable identifier. Fixture ids are short (C1, L11, E8b, X3, O2); live ids may be generated. Unique across all entity types within one analysis.
     */
    target: string;
    /**
     * The title that document's own summary gave the finding.
     */
    title: string;
  }[];
  /**
   * Credit where due across the documents: well-substantiated claims.
   */
  credit: {
    document_id: Id;
    target: Id;
    title: string;
  }[];
  document_count: number;
  /**
   * Claims across every document listed.
   */
  claim_count: number;
  omission_count: number;
  /**
   * The one thing asked of a model, after the numbers are fixed. Absent when nobody has written one: GET /api/company/{name} serves arithmetic only, so no page waits on a model.
   */
  narrative?: string;
  ext?: Ext;
}
/**
 * score is the company's greenwashing likelihood across the documents analysed. It says what the worst of the record is; the trend says which way it is moving.
 */
export interface ProfileEntry2 {
  score: Score01;
  confidence: Score01;
}
/**
 * How many claims fell into each verdict category. Must equal the verdicts counted.
 */
export interface VerdictDistribution1 {
  supported: number;
  unsubstantiated: number;
  misleading_by_framing: number;
  contradicted: number;
}
/**
 * One analysed document as the company view lists it: its own header numbers, what it is worth in the company's (recency x confidence) and how much of the company's headline it is (share). Documents are listed oldest first.
 */
export interface CompanyDocument {
  /**
   * Stable identifier. Fixture ids are short (C1, L11, E8b, X3, O2); live ids may be generated. Unique across all entity types within one analysis.
   */
  document_id: string;
  analysis_id?: Id;
  title: string;
  url?: string;
  /**
   * When the document is from. Absent when neither an archive capture nor a retrieval date says; `date_basis` then reads `unknown` and the document is left off the trend.
   */
  date?: string;
  /**
   * Where `date` came from. `archive` wins over `retrieved`, because the ingester stamps `retrieved` with the day it ran even when it read a 2024 capture.
   */
  date_basis: "archive" | "retrieved" | "unknown";
  text_type?: TextType;
  headline: ProfileEntry3;
  dimensions: DimensionProfile;
  verdict_distribution: VerdictDistribution;
  claim_count: number;
  omission_count: number;
  /**
   * How current this document is against the company's newest: 1.0 for that one, halving every half-life before it. The company-level analogue of a claim's prominence.
   */
  recency: number;
  /**
   * recency x the headline's confidence: this document's say in every company number.
   */
  weight: number;
  /**
   * This document's share of the company headline. The shares add up to 1.
   */
  share: number;
  ext?: Ext;
}
/**
 * The document summary's headline, unchanged.
 */
export interface ProfileEntry3 {
  score: Score01;
  confidence: Score01;
}
/**
 * The movement of the headline across one company's documents in time order, with a separate confidence saying how much of it to believe and a note that says so in words. Two documents are a line, not a trend: `confidence` is low and `note` says why, and a page must show one with the other.
 */
export interface CompanyTrend {
  direction: TrendDirection;
  /**
   * Documents the direction rests on: those that carry a date.
   */
  points: number;
  /**
   * last.score - first.score. Null when there are fewer than two points.
   */
  change: number | null;
  /**
   * The change at an annual rate. Null when there are fewer than two points or they share a date.
   */
  per_year: number | null;
  /**
   * Days between the first and last point.
   */
  span_days: number | null;
  /**
   * How much of the direction to believe: 0 when undetermined, and never above the confidence of the two headlines that moved.
   */
  confidence: number;
  /**
   * The oldest point. Both ends are the same document when only one carries a date, and both are null when none does.
   */
  first: TrendPoint | null;
  /**
   * The newest point.
   */
  last: TrendPoint | null;
  /**
   * One sentence a page can print under the arrow, saying what the direction rests on — including, when it rests on two documents, that two documents are not a trend.
   */
  note: string;
  ext?: Ext;
}
/**
 * One end of the trend: the document whose headline it is, when that document is from, and what it read.
 */
export interface TrendPoint {
  document_id: Id;
  date: Date;
  score: Score01;
}
