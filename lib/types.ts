export type NodeState =
  | "unknown"
  | "not_applicable"
  | "pending_gate"
  | "vague"
  | "conflicted"
  | "verified"
  | "user_confirmed"
  | "attempted_unknown";

export type Importance = "high" | "medium" | "low";
export type SourceKind = "document" | "user" | "inference_gate";
export type ConflictKind =
  | "policy_vs_practice"
  | "stale_vs_current"
  | "source_disagreement"
  | "user_vs_document"
  | "scope_ambiguity";

export interface Theme {
  key: string;
  display_name: string;
  question_range: number[];
  multiplier: number;
}

export interface SlotDef {
  name: string;
  type: string;
  required: boolean;
  prompt: string;
  aliases: string[];
  enum?: string[];
}

export interface RubricDef {
  id: string;
  theme: string;
  question_ids: number[];
  claim: string;
  importance: Importance;
  answer_type: string;
  slots: SlotDef[];
  malformed?: boolean;
  render_template?: string;
  sufficiency?: string;
}

export interface GraphNode {
  rubric_id: string;
  theme: string;
  claim: string;
  importance: Importance;
  state: NodeState;
  confidence: number;
  filled_slots: string[];
  empty_required_slots: string[];
  question_ids: number[];
  malformed: boolean;
}

export interface GraphResponse {
  themes: Theme[];
  nodes: GraphNode[];
  conflicts: Conflict[];
}

export interface Entry {
  entry_id: string;
  company_id: string;
  rubric_id: string;
  slot: string;
  value: unknown;
  confidence: number;
  source_kind: SourceKind;
  source_id: string | null;
  source_type: string | null;
  source_span: string | null;
  source_locator: Record<string, unknown> | null;
  source_authored_at: string | null;
  source_speaker: string | null;
  created_at: string;
  superseded_by: string | null;
}

export interface Conflict {
  conflict_id: string;
  company_id: string;
  rubric_id: string;
  slot: string;
  kind: ConflictKind;
  entry_a: string;
  entry_b: string;
  summary: string;
  resolution_question: string;
  status: "open" | "resolved" | "dismissed";
  created_at: string;
}

export interface NodeDetail {
  rubric: RubricDef;
  node_state: {
    state: NodeState;
    confidence: number;
    filled_slots: string[];
    empty_required_slots: string[];
  } | null;
  entries: Entry[];
  conflicts: Conflict[];
}

export interface QueueItem {
  rubric_id: string;
  state: NodeState;
  priority: number;
  empty_required_slots: string[];
  claim: string;
  theme: string;
}

export interface Stats {
  total: number;
  verified: number;
  user_confirmed: number;
  vague: number;
  conflicted: number;
  unknown: number;
  not_applicable: number;
  pending_gate: number;
  attempted_unknown: number;
}

export interface Company {
  company_id: string;
  name: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ReportThemeScore {
  theme: string;
  display_name: string;
  score: number;
  answered: number;
  applicable: number;
  top_gaps: Array<{ rubric_id: string; claim: string }>;
}

export interface ReportRisk {
  rubric_id: string;
  claim: string;
  theme: string;
  importance: Importance;
  state: NodeState;
}

export interface AnalystReport {
  company: Company;
  generated_at: string;
  posture_score: number;
  answered: number;
  applicable: number;
  total: number;
  open_conflicts_count: number;
  theme_scores: ReportThemeScore[];
  top_risks: ReportRisk[];
}

export type QuestionStatus =
  | "verified_from_documents"
  | "confirmed_by_user"
  | "not_applicable"
  | "partial"
  | "unknown";

export interface QuestionEvidence {
  doc: string | null;
  date: string;
  page: number | null;
  span: string | null;
}

export interface QuestionnaireQuestion {
  question_id: number;
  label: string;
  status: QuestionStatus;
  response: string | null;
  confidence: number;
  evidence: QuestionEvidence[];
}

export interface QuestionnaireResponse {
  questions: QuestionnaireQuestion[];
}

export interface Document {
  id: string;
  company_id: string;
  filename: string;
  source_type: string;
  doc_class: string;
  authored_at: string | null;
  uploaded_at: string;
  page_count: number;
  raw_path: string | null;
}

export interface NodeDelta {
  rubric_id: string;
  old_state: NodeState | null;
  new_state: NodeState;
  slots_filled: string[];
  confidence: number;
}

export interface IngestionJobStatus {
  job_id: string;
  status: "pending" | "running" | "done" | "failed";
  progress: number;
  errors: string[];
  result: {
    files_processed?: number;
    candidates_extracted?: number;
    facts_bound?: number;
    graph_delta?: NodeDelta[];
    file_results?: Array<{
      file: string;
      status: string;
      candidates?: number;
      bound?: number;
      errors?: string[];
      graph_delta?: NodeDelta[];
    }>;
  } | null;
}
