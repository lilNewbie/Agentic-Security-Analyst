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
