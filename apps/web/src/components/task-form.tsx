"use client";

const SEEDED_TASK = "Reduce storage costs by deleting inactive user files.";
const FIXTURE_ID = "retention-v1";

interface TaskFormProps {
  onRun: (task: string, fixtureId: string, mode: "mock" | "live") => void;
  loading: boolean;
  // Live runs are a protected operator action; mock stays public even when
  // this is true (matches the plan's "synthetic mock demo stays public").
  liveLocked?: boolean;
  error: string | null;
}

export function TaskForm({ onRun, loading, liveLocked = false, error }: TaskFormProps) {
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900 p-5">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
        Seeded demo task
      </h2>
      <p className="mt-2 text-base text-slate-100">&ldquo;{SEEDED_TASK}&rdquo;</p>
      <p className="mt-1 text-sm text-slate-500">
        Fixture: <span className="font-mono">{FIXTURE_ID}</span> (synthetic, no real user data)
      </p>
      <div className="mt-4 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => onRun(SEEDED_TASK, FIXTURE_ID, "mock")}
          disabled={loading}
          className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Running evaluation…" : "Run evaluation"}
        </button>
        <button
          type="button"
          onClick={() => onRun(SEEDED_TASK, FIXTURE_ID, "live")}
          disabled={loading || liveLocked}
          title={
            liveLocked
              ? "Sign in as operator above to start a live run."
              : "Requires NEBIUS_API_KEY / NEBIUS_MODEL configured on the server. Unverified in this build — see docs/MODEL_INTEGRATION.md."
          }
          className="rounded-md border border-violet-700 px-4 py-2 text-sm font-medium text-violet-300 transition hover:bg-violet-950 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Run live council (Nemotron)
        </button>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        Live mode calls the four-pass council through Nebius Token Factory and returns
        immediately while it runs in the background; it errors clearly if the server has no
        model key configured, rather than silently falling back to mock output.
      </p>
      {error && (
        <p role="alert" className="mt-3 text-sm text-red-400">
          {error}
        </p>
      )}
    </section>
  );
}
