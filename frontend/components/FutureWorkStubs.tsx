export function FutureWorkStubs() {
  const stubs = ["Voice", "CSAT dashboard", "Live ticketing"];
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
      <span>Future work:</span>
      {stubs.map((label) => (
        <span
          key={label}
          title="Not available in MVP"
          className="cursor-not-allowed rounded-full border border-dashed border-line px-2 py-1"
        >
          {label}
        </span>
      ))}
    </div>
  );
}
