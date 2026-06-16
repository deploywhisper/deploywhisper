import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Database, ShieldCheck } from "lucide-react";

import { getIncidentStatus, type IncidentSource } from "../api/phase6";
import { Card, EvidenceTag, MonoRef, SkeletonCard } from "../components/ui";
import { Phase6Shell } from "./Phase6Shell";
import "./dashboard.css";
import "./phase6.css";

function statusTone(status: string | null | undefined) {
  const normalized = String(status || "").toLowerCase();
  if (normalized.includes("stale") || normalized.includes("failed") || normalized.includes("missing")) {
    return "warning";
  }
  return "info";
}

function StatusNote({ message, tone = "info" }: { message?: string | null; tone?: "info" | "warning" }) {
  if (!message) {
    return null;
  }
  return <div className={`dw-phase6-note${tone === "warning" ? " dw-phase6-warning" : ""}`}>{message}</div>;
}

function SourceDetail({ source }: { source?: IncidentSource }) {
  if (!source) {
    return (
      <Card eyebrow="Detail" title="Incident source">
        <div className="dw-phase6-empty">Select a source to inspect indexed, rejected, and redaction details.</div>
      </Card>
    );
  }
  return (
    <Card eyebrow="Detail" title={source.title || source.import_source}>
      <div className="dw-phase6-stack">
        <div className="dw-phase6-row">
          <EvidenceTag>{source.freshness_status || "unknown freshness"}</EvidenceTag>
          <EvidenceTag>{source.redaction_status}</EvidenceTag>
          {source.scope_label && <EvidenceTag>{source.scope_label}</EvidenceTag>}
        </div>
        <MonoRef>{source.import_source}</MonoRef>
        <div className="dw-phase6-stat-grid">
          <div className="dw-phase6-stat"><strong>{source.indexed_count}</strong><span>Indexed</span></div>
          <div className="dw-phase6-stat"><strong>{source.rejected_count}</strong><span>Rejected</span></div>
        </div>
        <div className="dw-phase6-list-copy">Last indexed: {source.last_indexed_at || "not indexed yet"}</div>
        <div className="dw-phase6-list">
          {(source.failure_summaries ?? []).length === 0 ? (
            <div className="dw-phase6-empty">No import failures recorded for this source.</div>
          ) : (
            source.failure_summaries?.map((failure) => (
              <div className="dw-phase6-list-item" key={`${failure.source_file}-${failure.message}`}>
                <div className="dw-phase6-list-title">{failure.source_file}</div>
                <div className="dw-phase6-list-copy">{failure.message}</div>
                {failure.correction_path && <StatusNote message={failure.correction_path} tone="warning" />}
              </div>
            ))
          )}
        </div>
      </div>
    </Card>
  );
}

export function IncidentsScreen() {
  return (
    <Phase6Shell active="incidents">
      {({ selectedProject, selectedOption }) => {
        const [selectedSource, setSelectedSource] = useState<string | null>(null);
        const incidentQuery = useQuery({
          enabled: Boolean(selectedProject),
          queryFn: () => getIncidentStatus(selectedProject?.id),
          queryKey: ["incident-status", selectedProject?.id],
        });
        const sources = incidentQuery.data?.sources ?? [];
        const currentSource = useMemo(
          () => sources.find((source) => source.import_source === selectedSource) ?? sources[0],
          [selectedSource, sources],
        );

        return (
          <div className="dw-dashboard-wrap dw-phase6-content">
            <header className="dw-phase6-header">
              <div>
                <p className="eyebrow">Incident Memory</p>
                <h1>Incidents</h1>
                <p className="lede">Indexed incident context, import health, and source-level failures for {selectedOption?.name ?? "the active project"}.</p>
              </div>
              <EvidenceTag>Read-only index</EvidenceTag>
            </header>
            {incidentQuery.isLoading && (
              <div className="dw-phase6-grid">
                <SkeletonCard />
                <SkeletonCard />
              </div>
            )}
            {incidentQuery.error && <StatusNote message={incidentQuery.error.message} tone="warning" />}
            {incidentQuery.data && (
              <div className="dw-phase6-grid">
                <div className="dw-phase6-stack">
                  <Card eyebrow="Health" title="Ingestion status">
                    <div className="dw-phase6-stat-grid">
                      <div className="dw-phase6-stat"><strong>{incidentQuery.data.indexed_count}</strong><span>Indexed</span></div>
                      <div className="dw-phase6-stat"><strong>{incidentQuery.data.rejected_count}</strong><span>Rejected</span></div>
                      <div className="dw-phase6-stat"><strong>{incidentQuery.data.redaction_status}</strong><span>Redaction</span></div>
                      <div className="dw-phase6-stat"><strong>{incidentQuery.data.freshness_status}</strong><span>Freshness</span></div>
                    </div>
                    <StatusNote
                      message={`Last indexed: ${incidentQuery.data.last_indexed_at || "no import has completed"}`}
                      tone={statusTone(incidentQuery.data.freshness_status)}
                    />
                  </Card>
                  <Card eyebrow="Sources" title="Incident sources">
                    <div className="dw-phase6-list">
                      {sources.length === 0 ? (
                        <div className="dw-phase6-empty">
                          <Database size={18} /> No incident documents are indexed for this project.
                        </div>
                      ) : (
                        sources.map((source) => (
                          <button
                            className="dw-phase6-list-item"
                            key={source.import_source}
                            onClick={() => setSelectedSource(source.import_source)}
                            type="button"
                          >
                            <div className="dw-phase6-row">
                              <div className="dw-phase6-list-title">{source.title || source.import_source}</div>
                              <EvidenceTag>{source.freshness_status || "unknown"}</EvidenceTag>
                            </div>
                            <div className="dw-phase6-list-copy">
                              {source.indexed_count} indexed / {source.rejected_count} rejected
                            </div>
                          </button>
                        ))
                      )}
                    </div>
                  </Card>
                </div>
                <aside className="dw-phase6-stack">
                  <Card eyebrow="Access" title="Project incident context">
                    <div className="dw-phase6-stack">
                      <StatusNote message="Incident management remains scoped by project permissions." />
                      <div className="dw-phase6-row">
                        <ShieldCheck size={16} />
                        <span className="dw-phase6-list-copy">{selectedOption?.name ?? "Project"} context only</span>
                      </div>
                      {incidentQuery.data.rejected_count > 0 && (
                        <StatusNote message="One or more incident files need correction before they can inform matching." tone="warning" />
                      )}
                    </div>
                  </Card>
                  <SourceDetail source={currentSource} />
                </aside>
              </div>
            )}
            {!incidentQuery.isLoading && !incidentQuery.data && !incidentQuery.error && (
              <StatusNote message="Select a project to load incident memory." tone="warning" />
            )}
          </div>
        );
      }}
    </Phase6Shell>
  );
}
