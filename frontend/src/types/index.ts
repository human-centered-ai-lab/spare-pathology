// ─── Domain Models ───────────────────────────────────────────────────────────

export interface User {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  institution: string | null;
  role: "admin" | "participant";
  comments: string | null;
  last_login: string | null;
  is_test_user: boolean;
  created_at: string;
  impersonating?: boolean;
  impersonator_id?: number;
}

export interface SchemaQuestion {
  id: string;
  type: "ordinal" | "free_text";
  name: string;
  description?: string;
  min?: number;
  max?: number;
  labels?: Record<string, string>;
}

export interface FailureReasonConfig {
  enabled: boolean;
  label: string;
  options: string[];
  multi_select: boolean;
  condition?: {
    type: "any_ordinal" | "specific_question";
    question_id?: string;
    operator: string;
    value: number;
  };
}

export interface PassFailConfig {
  enabled: boolean;
  total_score_questions?: string[];
  conditions: {
    field: string;
    operator: string;
    value: number;
  }[];
}

export interface RatingSchema {
  questions: SchemaQuestion[];
  failure_reason?: FailureReasonConfig;
  visible_attributes?: string[];
}

export interface Study {
  id: number;
  name: string;
  description: string | null;
  protocol_pdf_path: string | null;
  status: "draft" | "active" | "finished";
  uncertainty_enabled: boolean;
  session_instruction: string | null;
  rating_schema: RatingSchema;
  pass_fail_config?: PassFailConfig;
  dataset_name: string | null;
  default_image_viewer: "native" | "xopat";
  created_at: string;
  image_count?: number;
  participant_count?: number;
  completed_count?: number;
  rating_count?: number;
}

export interface StudyParticipant {
  study_id: number;
  user_id: number;
  submitted: boolean;
  submitted_at: string | null;
  random_seed: number;
  last_viewed_image_id: number | null;
}

export interface DatasetImage {
  id: number;
  study_id: number;
  image_path: string;
  attributes: Record<string, string | number | boolean>;
  sequence_number: number;
}

export interface Rating {
  id: number;
  user_id: number;
  dataset_image_id: number;
  study_id: number;
  responses: Record<string, number | string | string[] | null>;
  uncertainty: boolean;
  time_spent_seconds: number;
  created_at: string;
  updated_at: string;
}

// ─── API Response Types ──────────────────────────────────────────────────────

export interface ParticipantStatus {
  user_id: number;
  first_name: string;
  last_name: string;
  email: string;
  institution: string | null;
  is_test_user: boolean;
  has_ratings: boolean;
  submitted: boolean;
  status_key: "submitted" | "in_progress" | "not_started";
  status_label: string;
  completion_pct: number;
  submitted_at: string | null;
}

export interface EvaluationStatus {
  total_users: number;
  total_images: number;
  submitted: number;
  in_progress: number;
  not_started: number;
  users: ParticipantStatus[];
}

export interface ImageListItem {
  position: number;
  dataset_image_id: number;
  image_name: string;
  status: "not_opened" | "opened" | "partial" | "complete";
  visible_attributes?: Record<string, string | number | boolean>;
}

export interface ImageData {
  dataset_image_id: number;
  position: number;
  image_url: string;
  total_images: number;
  rating: Rating | null;
  visible_attributes?: Record<string, string | number | boolean>;
  question_attributes?: Record<string, string | number | boolean>;
  xopat_slide_id?: string;
  xopat_microns?: number | null;
}

export interface BrowseImage {
  image_name: string;
  image_path: string;
  attributes: Record<string, string | number | boolean>;
  in_dataset: boolean;
  dataset_image_id: number | null;
  missing_file?: boolean;
  xopat_slide_id?: string;
  xopat_microns?: number | null;
}

export interface ToggleResponse {
  status: "added" | "removed";
  in_dataset: boolean;
  dataset_image_id: number | null;
}

export interface PaginatedDatasetImages {
  items: DatasetImage[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface PaginatedBrowse {
  items: BrowseImage[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface DatasetInfo {
  name: string;
  image_count: number;
  attribute_names: string[];
}

export interface AttributeSchema {
  name: string;
  type: string;
  values: (string | number | boolean)[];
}

export interface DatasetStats {
  total: number;
  by_attribute: Record<string, Record<string, number>>;
}

export interface ParticipantStudy {
  id: number;
  name: string;
  description?: string;
  status: string;
  has_protocol_pdf: boolean;
  uncertainty_enabled: boolean;
  session_instruction?: string;
  rating_schema: RatingSchema;
  default_image_viewer: "native" | "xopat";
  completion: {
    total: number;
    completed: number;
    pct: number;
  };
  last_viewed_position?: number | null;
  submitted: boolean;
  submitted_at?: string;
}

export interface FilterOptions {
  attributes: Array<{ name: string; type: string; values: (string | number | boolean)[] }>;
  users: { id: number; name: string; institution: string | null }[];
}

export interface StatResult {
  value: number | null;
  ci_lower: number | null;
  ci_upper: number | null;
  message: string | null;
}

export interface CenterEffectItem {
  center: string;
  effect: number;
  ci_lower: number;
  ci_upper: number;
  is_reference: boolean;
}

export interface CenterEffectsResult {
  effects: CenterEffectItem[];
  converged: boolean;
  message: string | null;
}

export interface FailureModesResult {
  by_center: Record<string, Record<string, number>>;
  overall: Record<string, number>;
  message: string | null;
}

export interface ScoreDistributionStats {
  scores: number[];
  mean: number;
  median: number;
  std: number;
  q1: number;
  q3: number;
  count: number;
}

export interface ScoreDistributionsResult {
  groups: Record<string, ScoreDistributionStats>;
  message: string | null;
}

export interface GroupComparisonResult {
  pass_rates: Record<string, number> | null;
  score_comparison: Record<string, { mean: number; std: number } | number | null> | null;
  per_question: Record<string, Record<string, number | null>> | null;
  message: string | null;
}

export interface BreakdownGroupStats {
  mean_score: number;
  std_score: number;
  pass_rate: number | null;
  count: number;
  n_raters: number;
  n_images: number;
}

export interface BreakdownsResult {
  groups: Record<string, BreakdownGroupStats>;
  message: string | null;
}

export interface ValidationResult {
  is_balanced: boolean;
  n_raters: number;
  n_images: number;
  expected_ratings: number;
  actual_ratings: number;
  missing_ratings: number;
  completeness: number;
  warnings: string[];
}

export interface EvaluationData {
  validation: ValidationResult;
  icc: StatResult;
  fleiss_kappa: StatResult;
  question_agreement: Record<string, { value: number | null; metric: string | null; message: string | null }>;
  center_effects: CenterEffectsResult;
  failure_modes: FailureModesResult;
  score_distributions: ScoreDistributionsResult;
  group_comparison: GroupComparisonResult;
  breakdowns: BreakdownsResult;
}

export interface DatasetsOverview {
  dataset_name: string;
  image_count: number;
  attribute_names: string[];
  referenced_by_studies: number;
}

export interface CompletionStatus {
  complete: boolean;
  total_images: number;
  completed_images: number;
  incomplete_images: {
    position: number;
    missing: string[];
  }[];
}
