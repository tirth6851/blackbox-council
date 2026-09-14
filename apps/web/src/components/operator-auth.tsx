"use client";

import { useState } from "react";

export interface OperatorStatus {
  configured: boolean;
  authenticated: boolean;
}

interface OperatorAuthPanelProps {
  status: OperatorStatus;
  onChange: () => void;
}

/** Shown only when this deployment has OPERATOR_CREDENTIAL configured.
 * Signing in sets an HttpOnly session cookie (see api/operator/login) —
 * this component never learns or holds the credential itself beyond the
 * single submit, and the credential is never sent anywhere except this
 * same-origin login request. */
export function OperatorAuthPanel({ status, onChange }: OperatorAuthPanelProps) {
  const [credential, setCredential] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!status.configured) return null;

  if (status.authenticated) {
    return (
      <div className="flex items-center gap-2 text-xs text-emerald-300">
        <span>Operator session active.</span>
        <button
          type="button"
          onClick={async () => {
            await fetch("/api/operator/logout", { method: "POST" });
            onChange();
          }}
          className="underline underline-offset-2"
        >
          Sign out
        </button>
      </div>
    );
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/operator/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credential }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.error?.message ?? "Sign-in failed.");
      }
      setCredential("");
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap items-center gap-2 text-xs">
      <span className="text-amber-300">
        This deployment requires an operator sign-in for approval, execution, rollback, and live runs.
      </span>
      <input
        type="password"
        value={credential}
        onChange={(event) => setCredential(event.target.value)}
        placeholder="Operator credential"
        disabled={busy}
        className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-slate-100 disabled:opacity-50"
      />
      <button
        type="submit"
        disabled={busy || !credential}
        className="rounded bg-sky-600 px-2 py-1 font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? "Signing in…" : "Sign in"}
      </button>
      {error && (
        <span role="alert" className="text-red-400">
          {error}
        </span>
      )}
    </form>
  );
}
