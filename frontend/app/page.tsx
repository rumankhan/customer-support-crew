"use client";

import { useState } from "react";
import { CrewStatusBanner } from "@/components/CrewStatusBanner";
import { DisclosureBanner } from "@/components/DisclosureBanner";
import { FutureWorkStubs } from "@/components/FutureWorkStubs";
import { HistoryList } from "@/components/HistoryList";
import { InputsForm } from "@/components/InputsForm";
import { ResultsPanel } from "@/components/ResultsPanel";
import { RunStatus } from "@/components/RunStatus";
import { useResearchWorkflow } from "@/lib/useResearchWorkflow";

export default function HomePage() {
  const workflow = useResearchWorkflow();
  const [query, setQuery] = useState("");
  const [requestHuman, setRequestHuman] = useState(false);
  const [disclosureAcknowledged, setDisclosureAcknowledged] = useState(false);

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-4 px-4 py-8 sm:px-6">
      <CrewStatusBanner
        status={workflow.crewStatus}
        lastUpdated={workflow.lastUpdated}
        stageLabel={workflow.stageLabel}
      />

      <header>
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Multi-Agent Customer Support Crew
        </p>
        <h1 className="mt-1 font-display text-3xl font-semibold">
          Critical Research Workflow
        </h1>
        <p className="mt-2 text-sm text-muted">
          Single route: submit inputs, watch a run, inspect results and session history.
        </p>
      </header>

      <DisclosureBanner
        acknowledged={disclosureAcknowledged}
        onAcknowledge={() => setDisclosureAcknowledged(true)}
      />

      <InputsForm
        query={query}
        requestHuman={requestHuman}
        phase={workflow.phase}
        crewStatus={workflow.crewStatus}
        error={workflow.error}
        onQueryChange={setQuery}
        onRequestHumanChange={setRequestHuman}
        onSubmit={() =>
          workflow.submit({
            query,
            requestHuman,
            disclosureAcknowledged,
          })
        }
      />

      <RunStatus
        phase={workflow.phase}
        crewStatus={workflow.crewStatus}
        stageLabel={workflow.stageLabel}
        lastUpdated={workflow.lastUpdated}
        runId={workflow.activeRunId}
        onReset={workflow.reset}
      />

      <ResultsPanel result={workflow.result} query={workflow.lastQuery} />

      <HistoryList
        entries={workflow.history}
        activeRunId={workflow.activeRunId}
        onSelect={workflow.showHistory}
      />

      <FutureWorkStubs />
    </main>
  );
}
