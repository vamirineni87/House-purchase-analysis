/**
 * TypeScript interfaces matching PIPA backend Pydantic schemas.
 */

// =====================================================================
// Core Property types
// =====================================================================

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

// =====================================================================
// Watchlist
// =====================================================================

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

// =====================================================================
// Alerts
// =====================================================================

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

// =====================================================================
// Notes
// =====================================================================

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

// =====================================================================
// County data
// =====================================================================

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

// =====================================================================
// Financial analysis
// =====================================================================

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

// =====================================================================
// Comparison
// =====================================================================

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

// =====================================================================
// Pipeline
// =====================================================================

export interface PipelineTaskRun {
  id: string;
  pipeline_run_id: string;
  task_name: string;
  status: string; // "pending" | "running" | "succeeded" | "failed" | "skipped"
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  retry_count: number;
  result_summary?: Record<string, unknown>;
  error_details?: string;
  created_at: string;
  updated_at: string;
}

export interface PipelineRun {
  id: string;
  property_id: string;
  run_type: string;
  status: string; // "queued" | "running" | "succeeded" | "partial_success" | "failed" | "cancelled"
  started_at?: string;
  completed_at?: string;
  initiated_by: string;
  summary_json?: Record<string, unknown>;
  error_count: number;
  warning_count: number;
  created_at: string;
  updated_at: string;
}

export interface PipelineRunDetail extends PipelineRun {
  tasks: PipelineTaskRun[];
}

// =====================================================================
// Decision Packet (7 sections)
// =====================================================================

export interface QuickTakeSection {
  recommendation: string; // "pursue" | "maybe" | "pass"
  bullets: string[];
}

export interface PriceViewSection {
  list_price?: number;
  comp_estimate?: number;
  assessment_value?: number;
  max_offer?: number;
  walk_away_price?: number;
}

export interface MonthlyCostSection {
  all_in_monthly?: number;
  cash_to_close?: number;
  stress_tested_monthly?: number;
  breakdown?: Record<string, number>;
}

export interface HiddenCostSection {
  capex_items?: Array<Record<string, unknown>>;
  unknowns?: string[];
  permit_concerns?: string[];
}

export interface CommunityViewSection {
  hoa_monthly?: number;
  hoa_health?: string;
  community_notes?: string[];
}

export interface CurrentHomeImpactSection {
  sell_vs_rent_summary?: string;
  net_monthly_delta?: number;
  details?: Record<string, unknown>;
}

export interface NextActionsSection {
  actions: Array<{
    title: string;
    category: string;
    severity: string;
    status: string;
  }>;
}

export interface DecisionPacket {
  property_id: string;
  decision_case_id?: string;
  generated_at: string;
  quick_take: QuickTakeSection;
  price_view: PriceViewSection;
  monthly_cost: MonthlyCostSection;
  hidden_cost: HiddenCostSection;
  community_view: CommunityViewSection;
  current_home_impact: CurrentHomeImpactSection;
  next_actions: NextActionsSection;
}

// =====================================================================
// Decision Case
// =====================================================================

export interface DecisionCase {
  id: string;
  property_id: string;
  stage: string;
  decision_status: string;
  priority: number;
  pursue_score?: number;
  max_offer_current?: number;
  walk_away_price?: number;
  target_monthly_payment?: number;
  confidence_level?: string;
  status_summary?: string;
  offer_deadline?: string;
  spouse_notes?: string;
  family_notes?: string;
  created_at: string;
  updated_at: string;
}

// =====================================================================
// Price Benchmarks (derived from decision packet price_view)
// =====================================================================

export interface PriceBenchmarks {
  ask_price?: number;
  zestimate?: number;
  assessed_value?: number;
  assessed_plus_7?: number;
  comp_estimate?: number;
}

// =====================================================================
// Comp types
// =====================================================================

export interface CompCandidate {
  address: string;
  price?: number;
  date?: string;
  status: string;
  source: string;
  distance_mi?: number;
  sqft?: number;
  beds?: number;
  baths?: number;
  days_on_market?: number;
  similarity_score?: number;
  year_built?: number;
  property_type?: string;
}

export interface EnrichedComp {
  address: string;
  sale_price: number;
  sale_date: string;
  sqft_above_grade?: number;
  total_livable_sqft?: number;
  year_built?: number;
  full_baths?: number;
  half_baths?: number;
  stories?: number;
  style?: string;
  condition?: string;
  grade?: string;
  roof_type?: string;
  roof_material?: string;
  exterior_wall?: string;
  heating_ac?: string;
  fireplaces?: number;
  basement_total_sqft?: number;
  basement_finished_sqft?: number;
  basement_unfinished_sqft?: number;
  basement_entrance?: string;
  garage_sqft?: number;
  garage_cars?: number;
  deck_sqft?: number;
  lot_acres?: number;
  lot_sqft?: number;
  assessed_land?: number;
  assessed_building?: number;
  assessed_total?: number;
  parcel_id?: string;
  subdivision?: string;
  zillow_sqft?: number;
  county_sqft?: number;
  sqft_conflict: boolean;
}

export interface QuickCompResult {
  candidates: CompCandidate[];
  filtered_comps: CompCandidate[];
  sold_count: number;
  active_count: number;
  pending_count: number;
  rough_value_band: { low: number; mid: number; high: number };
  quick_confidence: string;
  warnings: string[];
  assessment_context?: Record<string, unknown>;
  asking_vs_comps: string;
}

export interface DeepCompResult {
  sold_comps: EnrichedComp[];
  active_listings: CompCandidate[];
  pending_listings: CompCandidate[];
  appraisal: Record<string, unknown>;
  adjustments_summary: Record<string, unknown>;
  value_range: { low: number; mid: number; high: number };
  confidence: string;
  data_quality: Record<string, unknown>;
  conflicts: Array<Record<string, unknown>>;
  market_context: Record<string, unknown>;
  unresolved_unknowns: string[];
}

// =====================================================================
// Condition analysis
// =====================================================================

export interface ConditionResult {
  condition_score: number;
  capex_forecast: Record<number, number>; // year -> cost
  components_analyzed: number;
}

export interface ComponentInfo {
  type: string;
  install_year?: number;
  source?: string;
  confidence?: string;
  age?: number;
  remaining_life?: number;
  replacement_cost?: number;
}

// =====================================================================
// School info
// =====================================================================

export interface SchoolInfo {
  name: string;
  level: string; // "elementary" | "middle" | "high"
  rating?: number;
  distance_mi?: number;
  enrollment?: number;
  student_teacher_ratio?: number;
  test_scores?: Record<string, unknown>;
  assigned: boolean;
}

// =====================================================================
// Listing History
// =====================================================================

export interface ListingHistoryEvent {
  date: string;
  event_type: string; // "listed" | "price_change" | "pending" | "sold" | "withdrawn" | "relisted"
  price?: number;
  change_amount?: number;
  source?: string;
}

export interface ListingHistory {
  events: ListingHistoryEvent[];
  dom?: number;
  cdom?: number;
  total_reductions?: number;
  relist_detected: boolean;
  original_list_price?: number;
  current_list_price?: number;
}

// =====================================================================
// Offer strategy
// =====================================================================

export interface OfferStrategy {
  max_bid: Record<string, unknown>;
  walk_away_price: number;
  escalation_outcomes: Array<Record<string, unknown>>;
  appraisal_gap: Record<string, unknown>;
}

// =====================================================================
// Stress test
// =====================================================================

export interface StressTestResult {
  rate_shock: Record<string, unknown>;
  insurance_inflation: Record<string, unknown>;
  downside_sale: Record<string, unknown>;
}

// =====================================================================
// Warning / Red flag
// =====================================================================

export interface Warning {
  code: string;
  severity: "info" | "warning" | "critical";
  title: string;
  description: string;
  source?: string;
}

// =====================================================================
// Freshness
// =====================================================================

export interface SourceFreshness {
  source: string;
  last_fetched?: string;
  ttl_hours: number;
  is_stale: boolean;
  stale_behavior: string;
}

// =====================================================================
// Cross-reference conflict
// =====================================================================

export interface CrossReferenceConflict {
  field: string;
  source_a: string;
  source_b: string;
  value_a: unknown;
  value_b: unknown;
  severity: string;
  recommendation: string;
}

// =====================================================================
// Mortgage rates
// =====================================================================

export interface MortgageRates {
  rate_30yr: number;
  rate_15yr: number;
  source: string;
  as_of: string;
}

export interface CountyTaxRate {
  county: string;
  property_tax_rate: number;
  vehicle_tax_rate: number;
  stormwater_fee: number;
  source: string;
}

// =====================================================================
// Ingest response
// =====================================================================

export interface PropertyIngestResponse {
  property: Property;
  snapshot?: Record<string, unknown>;
}

// =====================================================================
// Full analysis
// =====================================================================

export interface FullAnalysisResult {
  financial: Record<string, unknown>;
  tax: Record<string, unknown>;
  investment: Record<string, unknown>;
  condition?: Record<string, unknown>;
}

// =====================================================================
// Recommendation
// =====================================================================

export interface Recommendation {
  id: string;
  property_id: string;
  decision_case_id?: string;
  pursue_recommendation: string;
  max_offer?: number;
  walk_away_price?: number;
  main_red_flags?: string[];
  unresolved_unknowns?: string[];
  top_questions?: string[];
  compare_rank?: number;
  confidence: string;
  reasoning?: string;
  created_at: string;
}
