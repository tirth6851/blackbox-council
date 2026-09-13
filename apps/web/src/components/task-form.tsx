"use client";

const SEEDED_TASK = "Reduce storage costs by deleting inactive user files.";
const FIXTURE_ID = "retention-v1";

interface TaskFormProps {
  onRun: (task: string, fixtureId: string) => void;
  loading: boolean;
  error: string | null;
}

export function TaskForm({ onRun, loading, error }: TaskFormProps) {
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900 p-5">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
        Seeded demo task
      </h2>
      <p className="mt-2 text-base text-slate-100">&ldquo;{SEEDED_TASK}&rdquo;</p>
      <p className="mt-1 text-sm text-slate-500">
        Fixture: <span className="font-mono">{FIXTURE_ID}</span> (synthetic, no real user data)
      </p>
      <button
        type="button"
        onClick={() => onRun(SEEDED_TASK, FIXTURE_ID)}
        disabled={loading}
        className="mt-4 rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? "Running evaluation…" : "Run evaluation"}
      </button>
      {error && (
        <p role="alert" className="mt-3 text-sm text-red-400">
          {error}
        </p>
      )}
    </section>
  );
}
