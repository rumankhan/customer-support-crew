"use client";

type Props = {
  acknowledged: boolean;
  onAcknowledge: () => void;
};

export function DisclosureBanner({ acknowledged, onAcknowledge }: Props) {
  if (acknowledged) {
    return (
      <p className="rounded-md border border-line bg-white px-3 py-2 text-sm text-muted">
        You are chatting with the B-Mobile AI assistant. Answers are grounded on
        B-Mobile help articles or escalated to a specialist.
      </p>
    );
  }

  return (
    <div
      role="status"
      className="flex flex-col gap-3 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
    >
      <p className="text-sm text-ink">
        You are chatting with the B-Mobile AI assistant. This does not replace a
        specialist when we lack an article or you ask to talk to a person.
      </p>
      <button
        type="button"
        onClick={onAcknowledge}
        className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-sm font-medium text-white hover:bg-stone-800"
      >
        I understand
      </button>
    </div>
  );
}
