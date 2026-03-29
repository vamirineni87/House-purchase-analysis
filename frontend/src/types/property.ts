/**
 * TypeScript interfaces matching PIPA backend Pydantic schemas.
 */

export interface Address {
  id: string;
  address_type: string;
  normalized_address: string;
  raw_address?: string;
  city?: string;
  state?: string;
  zip_code?: string;
  county?: string;
  latitude?: number;
  longitude?: number;
  is_current: boolean;
}

export interface ParcelIdentifier {
  id: string;
  county: string;
  identifier_type: string;
  identifier_value: string;
  is_current: boolean;
}

export interface Property {
  id: string;
  property_type: string;
  created_at: string;
  updated_at: string;
  addresses: Address[];
  parcel_identifiers: ParcelIdentifier[];
}

export interface PropertySummary {
  id: string;
  property_type: string;
  address?: string;
  county?: string;
  created_at: string;
}

export interface WatchlistEntry {
  id: string;
  property_id: string;
  stage: string;
  priority: number;
  added_at: string;
  stage_changed_at?: string;
}

export type WatchlistStage =
  | "researching"
  | "touring"
  | "offer"
  | "contract"
  | "closed"
  | "rejected";

// --- Alert types ---

export interface AlertEvent {
  id: string;
  property_id?: string;
  alert_type: string;
  title: string;
  description?: string;
  severity: "info" | "warning" | "critical";
  is_read: boolean;
  data?: Record<string, unknown>;
  triggered_at: string;
}

// --- Note types ---

export interface PropertyNote {
  id: string;
  property_id: string;
  content: string;
  note_type: string;
  created_at: string;
}

export interface NoteCreate {
  content: string;
  note_type: string;
}

// --- County data types ---

export interface AssessmentSnapshot {
  id: string;
  property_id: string;
  tax_year: number;
  land_value: number;
  improvement_value: number;
  total_value: number;
  tax_rate?: number;
  annual_tax?: number;
  snapshot_date: string;
}

export interface PermitRecord {
  id: string;
  property_id: string;
  permit_number?: string;
  type: string;
  description?: string;
  estimated_cost?: number;
  issue_date?: string;
  final_date?: string;
  status?: string;
  contractor?: string;
  source: string;
}

export interface DeedRecord {
  id: string;
  property_id: string;
  grantor?: string;
  grantee?: string;
  sale_price?: number;
  sale_date?: string;
  deed_type?: string;
  instrument_number?: string;
  recorded_date?: string;
}

export interface CountyData {
  assessments: AssessmentSnapshot[];
  permits: PermitRecord[];
  deeds: DeedRecord[];
}

// --- Financial analysis types ---

export interface MonthlyPaymentBreakdown {
  principal: number;
  interest: number;
  property_tax: number;
  homeowners_insurance: number;
  pmi: number;
  hoa: number;
  total: number;
}

export interface ClosingCosts {
  loan_origination: number;
  appraisal_fee: number;
  title_insurance: number;
  escrow_fees: number;
  recording_fees: number;
  prepaid_taxes: number;
  prepaid_insurance: number;
  inspection_fees: number;
  other: number;
  total: number;
}

export interface LoanScenario {
  name: string;
  loan_amount: number;
  interest_rate: number;
  term_years: number;
  down_payment: number;
  down_payment_pct: number;
  points: number;
}

export interface FinancialAnalysisResult {
  scenarios: LoanScenario[];
  payment_breakdowns: Record<string, MonthlyPaymentBreakdown>;
  closing_costs: ClosingCosts;
  cash_needed_at_closing: Record<string, number>;
}

export interface FinancialAnalysisRequest {
  list_price: number;
  hoa_monthly?: number;
  down_payment_pcts?: number[];
  term_years?: number[];
  rate_override?: number;
  property_tax_rate?: number;
}

// --- Comparison types ---

export interface PropertyScore {
  property_id: string;
  address?: string;
  total_score: number;
  category_scores: Record<string, number>;
  rank: number;
}

export interface ComparisonResult {
  properties: PropertyScore[];
  weights_used: Record<string, number>;
}

export interface ComparisonRequest {
  property_ids: string[];
  weights?: Record<string, number>;
}
