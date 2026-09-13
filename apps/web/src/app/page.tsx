"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, createEvaluation, executeAction, getEvaluation, rollbackAction, submitApproval } from "@/lib/api";
import type { EvaluationReport } from "@/lib/types";
import { ModeBadge, OutcomeBadge } from "@/components/status-badge";
import { TaskForm } from "@/components/task-form";
import { Timeline } from "@/components/timeline";
import { ActionComparison } from "@/components/action-comparison";
import { EvidencePanel } from "@/components/evidence-panel";
import { ApprovalPanel } from "@/components/approval-panel";
import { ExecutionResult } from "@/components/execution-result";
import { CounterfactualPanel } from "@/components/counterfactual-panel";

type Phase = "idle" | "submitting" | "polling" | "report" | "busy";

const POLL_INTERVAL_MS = 1500;

export default function Home() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [report, setReport] = useState<EvaluationReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollCancelledRef = useRef(false);

  useEffect(() => {
    return () => {
      // Abort any in-flight poll loop if this page is ever unmounted.
      pollCancelledRef.current = true;
    };
  }, []);

  const refetch = useCallback(async (runId: string) => {
    const fresh = await getEvaluation(runId);
    setReport(fresh);
    return fresh;
  }, []);

  const pollUntilTerminal = useCallback(async (runId: string) => {
    pollCancelledRef.current = false;
    while (!pollCancelledRef.current) {
      let latest: EvaluationReport;
      try {
        latest = await refetch(runId);
      } catch {
        return; // a transient fetch error stops polling; the report already shown stays visible
      }
      if (latest.status !== "evaluating" || pollCancelledRef.current) {
        setPhase("report");
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    }
  }, [refetch]);

  const handleRun = useCallback(
    async (task: string, fixtureId: string, mode: "mock" | "live") => {
      pollCancelledRef.current = true; // stop any previous poll loop
      setPhase("submitting");
      setError(null);
      try {
        const created = await createEvaluation(task, fixtureId, mode);
        setReport(created);
        if (created.status === "evaluating") {
          setPhase("polling");
          void pollUntilTerminal(created.run_id);
        } else {
          setPhase("report");
        }
      } catch (err) {
        setError(describeError(err));
        setPhase("idle");
      }
    },
    [pollUntilTerminal],
  );

  const handleApprove = useCallback(
    async (reason: string) => {
      if (!report?.final_decision?.action_hash) return;
      setPhase("busy");
      setError(null);
      try {
        const updated = await submitApproval(report.run_id, report.final_decision.action_hash, "approve", reason);
        setReport(updated);
      } catch (err) {
        if (err instanceof ApiError && err.code === "action_hash_mismatch") {
          await refetch(report.run_id).catch(() => undefined);
        }
        setError(describeError(err));
      } finally {
        setPhase("report");
      }
    },
    [report, refetch],
  );

  const handleReject = useCallback(
    async (reason: string) => {
      if (!report?.final_decision?.action_hash) return;
      setPhase("busy");
      setError(null);
      try {
        const updated = await submitApproval(report.run_id, report.final_decision.action_hash, "reject", reason);
        setReport(updated);
      } catch (err) {
        setError(describeError(err));
      } finally {
        setPhase("report");
      }
    },
    [report],
  );

  const handleRunSimulation = useCallback(async () => {
    if (!report?.final_decision?.action_hash) return;
    setPhase("busy");
    setError(null);
    try {
      await executeAction(report.run_id, report.final_decision.action_hash);
      // Refetch the current execution before assuming it never ran, in case
      // of a slow network or a retried click.
      const updated = await refetch(report.run_id);
      setReport(updated);
    } catch (err) {
      await refetch(report.run_id).catch(() => undefined);
      setError(describeError(err));
    } finally {
      setPhase("report");
    }
  }, [report, refetch]);

  const handleRollback = useCallback(
    async (executionId: string) => {
      if (!report) return;
      setPhase("busy");
      setError(null);
      try {
        await rollbackAction(report.run_id, executionId);
        const updated = await refetch(report.run_id);
        setReport(updated);
      } catch (err) {
        setError(describeError(err));
      } finally {
        setPhase("report");
      }
    },
    [report, refetch],
  );

  const busy = phase === "busy" || phase === "submitting";
  const isRunning = phase === "submitting" || phase === "polling";

  return (
    <main className="mx-auto max-w-4xl space-y-6 px-4 py-10 sm:px-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold text-white">BlackBox Council — Decision X-Ray</h1>
        <p className="text-sm text-slate-400">
          An auditable pre-action policy gate: browser → API → deterministic decision → human approval →
          simulated archive → stored audit record.
        </p>
        {report && (
          <div className="flex flex-wrap gap-2">
            <ModeBadge mode={report.mode} />
            <span className="rounded-full border border-slate-700 px-2.5 py-0.5 text-xs text-slate-300">
              Status: {report.status}
            </span>
          </div>
        )}
      </header>

      <TaskForm onRun={handleRun} loading={isRunning} error={error} />

      {!report && !isRunning && (
        <p className="text-sm text-slate-500">Run the seeded demo to inspect a decision.</p>
      )}

      {phase === "polling" && report && (
        <p className="text-sm text-violet-300">
          Live council evaluation in progress ({report.events.length} stage(s) so far)…
        </p>
      )}

      {report && (
        <>
          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Final decision</h2>
            {report.final_decision && (
              <div className="flex items-center gap-3">
                <OutcomeBadge outcome={report.final_decision.outcome} />
                <p className="text-sm text-slate-300">{report.final_decision.summary}</p>
              </div>
            )}
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
              Candidate comparison
            </h2>
            {report.plan && (
              <ActionComparison
                candidates={report.plan.candidates}
                decisions={report.candidate_decisions}
                selectedCandidateId={report.final_decision?.selected_candidate_id ?? null}
              />
            )}
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Evidence</h2>
            <EvidencePanel context={report.context} />
          </section>

          {report.mode === "live" && report.status !== "evaluating" && (
            <section className="space-y-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
                Counterfactual probes &amp; risk
              </h2>
              <CounterfactualPanel extensions={report.extensions} />
            </section>
          )}

          {report.final_decision && (
            <section className="space-y-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
                Approval
              </h2>
              <ApprovalPanel
                finalDecision={report.final_decision}
                approval={report.approval}
                status={report.status}
                busy={busy}
                onApprove={handleApprove}
                onReject={handleReject}
              />
            </section>
          )}

          {(report.status === "approved" || report.execution) && (
            <section className="space-y-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
                Simulated execution
              </h2>
              <ExecutionResult
                status={report.status}
                execution={report.execution}
                busy={busy}
                onRunSimulation={handleRunSimulation}
                onRollback={handleRollback}
              />
            </section>
          )}

          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Timeline</h2>
            <Timeline events={report.events} />
          </section>

          <a
            href={`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/api/v1/evaluations/${report.run_id}/report`}
            className="inline-block text-xs text-sky-400 underline underline-offset-2"
          >
            Download full audit JSON
          </a>
        </>
      )}
    </main>
  );
}

function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    return err.message;
  }
  return "Something went wrong. Please try again.";
}
