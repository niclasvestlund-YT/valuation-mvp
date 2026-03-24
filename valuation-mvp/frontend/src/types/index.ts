export type ValuationStatus =
  | "ok"
  | "ambiguous_model"
  | "insufficient_evidence"
  | "estimated_from_depreciation"
  | "degraded"
  | "error";

export interface MarketListing {
  title: string;
  price: number;
  currency: string;
  source: string;
  url: string | null;
  status: "sold" | "active";
  date: string | null;
  relevance_score: number;
}

export interface PricePoint {
  date: string;
  price: number;
  source: string;
}

export interface ReasoningStep {
  step: string;
  description: string;
  confidence: number;
  data_points: number;
}

export interface ValuationResponse {
  status: ValuationStatus;
  product_name: string | null;
  estimated_value: number | null;
  value_range: [number, number] | null;
  confidence: number | null;
  currency: string;
  new_price: number | null;
  new_price_source: string | null;
  price_history: PricePoint[];
  lowest_new_price_6m: number | null;
  depreciation_percent: number | null;
  market_listings: MarketListing[];
  comparables_used: number;
  reasoning: ReasoningStep[];
  warnings: string[];
  sources: string[];
  debug: Record<string, unknown> | null;
}

export interface ScanEntry {
  product_name: string | null;
  estimated_value: number | null;
  thumbnailUrl: string | null;
  timestamp: Date;
  result: ValuationResponse;
}
