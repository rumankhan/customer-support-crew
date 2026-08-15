"use client";

import { useState } from "react";
import { ChatWindow } from "@/components/ChatWindow";
import { DisclosureBanner } from "@/components/DisclosureBanner";
import { FutureWorkStubs } from "@/components/FutureWorkStubs";
import { RunStatus } from "@/components/RunStatus";
import { SpecialistStrip } from "@/components/SpecialistStrip";
import { useResearchWorkflow } from "@/lib/useResearchWorkflow";

export default function HomePage() {
  const workflow = useResearchWorkflow();
  const [query, setQuery] = useState("");
  const [requestHuman, setRequestHuman] = useState(false);
  const [disclosureAcknowledged, setDisclosureAcknowledged] = useState(false);

  function handleSubmit() {
    const trimmed = query.trim();
    workflow.submit({
      query,
      requestHuman,
      disclosureAcknowledged,
    });
    if (trimmed && trimmed.length <= 4000) {
      setQuery("");
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-4 px-4 py-8 sm:px-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          B-Mobile Support Crew
        </p>
        <h1 className="mt-1 font-display text-3xl font-semibold">
          How can we help?
        </h1>
        <p className="mt-2 text-sm text-muted">
          Ask about plans, billing, SIM, roaming, or a device order. Answers come
          from B-Mobile help articles, or we hand you to a specialist.
        </p>
      </header>

      <DisclosureBanner
        acknowledged={disclosureAcknowledged}
        onAcknowledge={() => setDisclosureAcknowledged(true)}
      />

      <ChatWindow
        history={workflow.history}
        lastQuery={workflow.lastQuery}
        phase={workflow.phase}
        stageLabel={workflow.stageLabel}
        query={query}
        requestHuman={requestHuman}
        crewStatus={workflow.crewStatus}
        error={workflow.error}
        onQueryChange={setQuery}
        onRequestHumanChange={setRequestHuman}
        onSubmit={handleSubmit}
        onNewConversation={() => {
          workflow.startNewConversation();
          setQuery("");
          setRequestHuman(false);
        }}
      />

      <RunStatus
        crewStatus={workflow.crewStatus}
        stageLabel={workflow.stageLabel}
        lastUpdated={workflow.lastUpdated}
        runId={workflow.activeRunId}
      />

      <SpecialistStrip result={workflow.result} />

      <FutureWorkStubs />
    </main>
  );
}
