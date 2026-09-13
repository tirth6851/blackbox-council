import type { ErrorEnvelope, EvaluationReport, ExecutionRecord } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "network_error", "Could not reach the BlackBox Council API.");
  }

  if (!response.ok) {
    let body: ErrorEnvelope | null = null;
    try {
      body = await response.json();
    } catch {
      // fall through to a generic message below
    }
    if (body?.error) {
      throw new ApiError(response.status, body.error.code, body.error.message);
    }
    throw new ApiError(response.status, "http_error", `Request failed with status ${response.status}.`);
  }

  return (await response.json()) as T;
}

export function createEvaluation(task: string, fixtureId: string): Promise<EvaluationReport> {
  return request<EvaluationReport>("/api/v1/evaluations", {
    method: "POST",
    body: JSON.stringify({ task, fixture_id: fixtureId, mode: "mock" }),
  });
}

export function getEvaluation(runId: string): Promise<EvaluationReport> {
  return request<EvaluationReport>(`/api/v1/evaluations/${runId}`);
}

export function submitApproval(
  runId: string,
  actionHash: string,
  decision: "approve" | "reject",
  reason: string,
): Promise<EvaluationReport> {
  return request<EvaluationReport>(`/api/v1/evaluations/${runId}/approvals`, {
    method: "POST",
    body: JSON.stringify({ action_hash: actionHash, decision, reason }),
  });
}

export function executeAction(runId: string, actionHash: string): Promise<ExecutionRecord> {
  return request<ExecutionRecord>(`/api/v1/evaluations/${runId}/execute`, {
    method: "POST",
    body: JSON.stringify({ action_hash: actionHash }),
  });
}

export function rollbackAction(runId: string, executionId: string): Promise<ExecutionRecord> {
  return request<ExecutionRecord>(`/api/v1/evaluations/${runId}/rollback`, {
    method: "POST",
    body: JSON.stringify({ execution_id: executionId }),
  });
}
