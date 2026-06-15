import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";

import "@fontsource-variable/plus-jakarta-sans";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource-variable/jetbrains-mono";
import "./styles.css";

import { getHealth } from "./api/client";
import {
  Button,
  Card,
  ConfidenceBadge,
  EvidenceTag,
  MonoRef,
  ProjectSwitcher,
  ScoreRing,
  SegmentedTabs,
  SeverityBadge,
  SkeletonCard,
  SkeletonReportHeader,
  SkeletonTable,
  Sparkline,
  VerdictChip,
  demoProjects,
} from "./components/ui";

const queryClient = new QueryClient();

function HealthVersion() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    retry: false,
  });

  if (health.isLoading) {
    return <p className="status">Checking backend health...</p>;
  }

  if (health.isError) {
    return (
      <p className="status error" role="alert">
        Backend health unavailable.
      </p>
    );
  }

  if (!health.data) {
    return <p className="status">Waiting for backend health...</p>;
  }

  return (
    <p className="status" data-testid="health-version">
      Backend version <strong>{health.data.meta.version}</strong>
    </p>
  );
}

function App() {
  if (window.location.pathname.startsWith("/app/dev/components")) {
    return <ComponentGallery />;
  }

  return (
    <main className="shell">
      <section className="panel" aria-labelledby="phase-title">
        <p className="eyebrow">DeployWhisper UI Migration</p>
        <h1 id="phase-title">React shell is connected</h1>
        <p className="lede">
          Phase 0 placeholder served by Vite. The full design system starts in Phase 2.
        </p>
        <HealthVersion />
      </section>
    </main>
  );
}

function ComponentGallery() {
  return (
    <main className="component-gallery dw-ui">
      <div className="gallery-wrap">
        <header className="gallery-header">
          <div>
            <p className="eyebrow">DeployWhisper Design System</p>
            <h1>Phase 2 primitives</h1>
            <p className="lede">Tokens, badges, rings, controls, switcher, and loading states.</p>
          </div>
          <ProjectSwitcher initialOpen projects={demoProjects} selectedProject={demoProjects[0]} />
        </header>

        <section className="gallery-grid">
          <Card eyebrow="BADGE SYSTEM" title="Severity, verdict, evidence">
            <div className="gallery-row" data-testid="badge-set">
              <SeverityBadge level="CRITICAL" />
              <SeverityBadge level="HIGH" />
              <SeverityBadge level="MEDIUM" />
              <SeverityBadge level="LOW" />
              <VerdictChip size="sm" verdict="NO-GO" />
              <VerdictChip size="md" verdict="CAUTION" />
              <VerdictChip size="md" verdict="PROCEED" />
              <EvidenceTag>EV-01</EvidenceTag>
              <ConfidenceBadge level="HIGH" />
              <ConfidenceBadge level="LOW" />
              <MonoRef>terraform/rds.tf:18</MonoRef>
            </div>
          </Card>

          <Card eyebrow="SCORE RING" title="Light track">
            <div className="gallery-row">
              <ScoreRing score={78} size={76} />
              <ScoreRing score={42} size={62} />
              <Sparkline points={[2, 3, 3, 5, 6, 9, 14]} />
            </div>
          </Card>

          <div className="gallery-dark" data-testid="score-ring-dark">
            <div className="eyebrow">DARK TRACK</div>
            <div style={{ height: 12 }} />
            <ScoreRing dark score={78} size={72} />
          </div>

          <Card eyebrow="CONTROLS" title="Buttons and tabs">
            <div className="gallery-row">
              <Button variant="primary-gradient">Run analysis</Button>
              <Button variant="ghost">Compare</Button>
              <Button variant="dark">Copy briefing</Button>
              <Button disabled variant="primary-gradient">
                Analyze
              </Button>
            </div>
            <div style={{ height: 14 }} />
            <SegmentedTabs
              activeId="findings"
              tabs={[
                { id: "overview", label: "Overview" },
                { id: "findings", label: "Findings", count: 3 },
                { id: "audit", label: "Audit" },
              ]}
            />
          </Card>

          <Card eyebrow="LOADING" title="Skeleton states">
            <div style={{ display: "grid", gap: 14 }}>
              <SkeletonCard />
              <SkeletonTable rows={2} />
            </div>
          </Card>

          <Card eyebrow="HEADER" title="Report header skeleton">
            <SkeletonReportHeader />
          </Card>
        </section>
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
