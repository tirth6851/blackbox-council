import type { EventRecord } from "@/lib/types";

export function Timeline({ events }: { events: EventRecord[] }) {
  if (events.length === 0) {
    return <p className="text-sm text-slate-500">No events recorded yet.</p>;
  }

  return (
    <ol className="space-y-3">
      {events.map((event) => (
        <li key={event.sequence} className="flex gap-3 text-sm">
          <span className="mt-0.5 font-mono text-xs text-slate-500">
            {new Date(event.created_at).toLocaleTimeString()}
          </span>
          <div>
            <span className="font-medium text-slate-200">{event.stage}</span>{" "}
            <span className="text-slate-500">({event.status})</span>
            <p className="text-slate-400">{event.message}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
