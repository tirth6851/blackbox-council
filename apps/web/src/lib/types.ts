// Mirrors apps/api/app/schemas.py. Kept as a small hand-written contract
// fixture until OpenAPI-generated types replace it (see plan/01-phase-1-working-demo.md 1.2).

export type Outcome =
  | "safe"
  | "safeguard_required"
  | "clarification_required"
  | "approval_required"
  | "blocked";

export type RunStatus =
  | "created"
  | "evaluating"
  | "decision_ready"
  | "awaiting_approval"
  | "approved"
  | "executing"
  | "completed"
  | "rejected"
  | "needs_clarification"
  | "needs_safeguards"
  | "blocked"
  | "failed";

export type TrustLevel =
  | "server_policy"
  | "server_metadata"
  | "repository_trusted"
  | "repository_untrusted"
  | "model_output";

export interface ContextItem {
  id: string;
  source: string;
  trust: TrustLevel;
  content: string;
  content_sha256: string;
}

export interface CandidateAction {
  id: string;
  operation: "delete" | "archive" | "dry_run" | "clarify";
  file_ids: string[];
  dry_run: boolean;
  backup_manifest: boolean;
  recovery_days: number;
  rationale: string;
}

export interface Plan {
  id: string;
  assumptions: string[];
  unanswered_questions: string[];
  candidates: CandidateAction[];
  preferred_candidate_id: string | null;
}

export interface Scenario {
  id: string;
  candidate_id: string;
  kind: "best" | "likely_failure" | "worst";
  premise: string;
  outcome: string;
  evidence_ids: string[];
  mitigation: string;
}

export interface Review {
  role: "planner" | "red_team" | "privacy" | "arbiter" | "mock";
  summary: string;
  concerns: string[];
  suggested_outcome: Outcome;
  evidence_ids: string[];
}

export interface PolicyFinding {
  rule_id: string;
  candidate_id: string | null;
  severity: "info" | "low" | "moderate" | "high" | "critical";
  status: "triggered" | "clear";
  effect: "block" | "clarify" | "safeguard" | "info";
  evidence: string[];
  explanation: string;
  remediation: string;
}

export interface CandidateDecision {
  candidate_id: string;
  outcome: Outcome;
  findings: PolicyFinding[];
  prerequisites_missing: string[];
}

export interface FinalDecision {
  outcome: Outcome;
  selected_candidate_id: string | null;
  summary: string;
  safeguards: string[];
  action_hash: string | null;
}

export interface ApprovalRecord {
  action_hash: string;
  decision: "approve" | "reject";
  reason: string;
  created_at: string;
  expires_at: string;
  consumed_at: string | null;
}

export interface ExecutionRecord {
  id: string;
  run_id: string;
  action_hash: string;
  status: "completed" | "failed" | "rolled_back";
  simulated: true;
  before_digest: string;
  after_digest: string;
  archived_file_ids: string[];
  rollback_record_id: string | null;
}

export interface EventRecord {
  sequence: number;
  stage: string;
  status: string;
  message: string;
  created_at: string;
}

export interface EvaluationReport {
  schema_version: string;
  run_id: string;
  mode: "mock" | "live";
  status: RunStatus;
  task: string;
  fixture_id: string;
  context: ContextItem[];
  plan: Plan | null;
  reviews: Review[];
  scenarios: Scenario[];
  candidate_decisions: CandidateDecision[];
  final_decision: FinalDecision | null;
  events: EventRecord[];
  approval: ApprovalRecord | null;
  execution: ExecutionRecord | null;
}

export interface ErrorEnvelope {
  error: { code: string; message: string };
}
