import type { ContextItem, TrustLevel } from "@/lib/types";

const TRUST_LABEL: Record<TrustLevel, string> = {
  server_policy: "Server policy",
  server_metadata: "Server metadata",
  repository_trusted: "Repository (trusted)",
  repository_untrusted: "Repository (UNTRUSTED)",
  model_output: "Model output",
};

const TRUST_CLASS: Record<TrustLevel, string> = {
  server_policy: "border-sky-700 text-sky-300",
  server_metadata: "border-sky-700 text-sky-300",
  repository_trusted: "border-slate-700 text-slate-300",
  repository_untrusted: "border-red-700 text-red-300",
  model_output: "border-violet-700 text-violet-300",
};

export function EvidencePanel({ context }: { context: ContextItem[] }) {
  if (context.length === 0) {
    return <p className="text-sm text-slate-500">No evidence loaded yet.</p>;
  }

  return (
    <div className="space-y-3">
      {context.map((item) => (
        <div key={item.id} className="rounded-md border border-slate-800 bg-slate-900 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${TRUST_CLASS[item.trust]}`}
            >
              {TRUST_LABEL[item.trust]}
            </span>
            <span className="font-mono text-xs text-slate-500">{item.source}</span>
          </div>
          {/* Repository/model content is rendered as plain escaped text only.
              Never dangerouslySetInnerHTML this field. */}
          <p className="mt-2 whitespace-pre-wrap break-words text-sm text-slate-300">{item.content}</p>
        </div>
      ))}
    </div>
  );
}
