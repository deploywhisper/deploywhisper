import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import "@fontsource-variable/plus-jakarta-sans";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource-variable/jetbrains-mono";
import "./styles.css";

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
  SkeletonLine,
  SkeletonReportHeader,
  SkeletonTable,
  Sparkline,
  VerdictChip,
  demoProjects,
} from "./components/ui";
import { DashboardScreen } from "./screens/Dashboard";
import { HistoryScreen } from "./screens/History";
import { IncidentsScreen } from "./screens/Incidents";
import { ReportScreen } from "./screens/Report";
import { SettingsScreen } from "./screens/Settings";
import { SkillsScreen } from "./screens/Skills";

const queryClient = new QueryClient();

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<ComponentGallery />} path="/dev/components" />
        <Route element={<HistoryScreen />} path="/history" />
        <Route element={<SettingsScreen />} path="/settings" />
        <Route element={<IncidentsScreen />} path="/incidents" />
        <Route element={<SkillsScreen />} path="/skills" />
        <Route element={<SkillsScreen />} path="/skills/:skillId" />
        <Route element={<ReportScreen />} path="/reports/:id" />
        <Route element={<DashboardScreen />} path="/" />
        <Route element={<DashboardScreen />} path="*" />
      </Routes>
    </BrowserRouter>
  );
}

function ComponentGallery() {
  const emptyProjects = demoProjects.slice(0, 2);

  return (
    <main className="component-gallery dw-ui">
      <div className="gallery-wrap">
        <header className="gallery-header">
          <div>
            <p className="eyebrow">DeployWhisper Design System</p>
            <h1>Phase 2 primitives</h1>
            <p className="lede">Tokens, badges, rings, controls, switcher, and loading states.</p>
          </div>
          <ProjectSwitcher projects={demoProjects} selectedProject={demoProjects[0]} />
        </header>

        <section className="gallery-grid">
          <Card eyebrow="SEVERITY" title="All severity badges">
            <div className="gallery-row" data-testid="badge-set">
              <SeverityBadge level="CRITICAL" />
              <SeverityBadge level="HIGH" />
              <SeverityBadge level="MEDIUM" />
              <SeverityBadge level="LOW" />
            </div>
          </Card>

          <Card eyebrow="VERDICTS" title="Small and medium chips">
            <div className="gallery-stack">
              <div className="gallery-row" data-testid="verdict-set-sm">
                <VerdictChip size="sm" verdict="NO-GO" />
                <VerdictChip size="sm" verdict="CAUTION" />
                <VerdictChip size="sm" verdict="PROCEED" />
              </div>
              <div className="gallery-row" data-testid="verdict-set-md">
                <VerdictChip size="md" verdict="NO-GO" />
                <VerdictChip size="md" verdict="CAUTION" />
                <VerdictChip size="md" verdict="PROCEED" />
              </div>
            </div>
          </Card>

          <Card eyebrow="EVIDENCE" title="Evidence, confidence, mono">
            <div className="gallery-row">
              <EvidenceTag>EV-01</EvidenceTag>
              <EvidenceTag>TF-18</EvidenceTag>
              <ConfidenceBadge level="HIGH" />
              <ConfidenceBadge level="LOW" />
              <MonoRef>terraform/rds.tf:18</MonoRef>
            </div>
          </Card>

          <Card eyebrow="SCORE RING" title="Light track scores">
            <div className="gallery-row gallery-score-row">
              <ScoreRing score={0} size={62} />
              <ScoreRing score={18} size={62} />
              <ScoreRing score={42} size={62} />
              <ScoreRing score={78} size={76} />
              <ScoreRing score={100} size={62} />
            </div>
          </Card>

          <div className="gallery-dark" data-testid="score-ring-dark">
            <div className="eyebrow">DARK TRACK</div>
            <div className="gallery-row gallery-score-row">
              <ScoreRing dark score={0} size={62} />
              <ScoreRing dark score={42} size={62} />
              <ScoreRing dark score={78} size={72} />
              <ScoreRing dark score={100} size={62} />
            </div>
          </div>

          <Card eyebrow="SPARKLINE" title="Compact trend">
            <div className="gallery-row">
              <Sparkline points={[2, 3, 3, 5, 6, 9, 14]} />
              <Sparkline points={[9, 7, 8, 4, 5, 3, 2]} />
              <Sparkline points={[1, 2, 2, 3, 5, 8, 13]} />
            </div>
          </Card>

          <Card eyebrow="CONTROLS" title="Buttons and tabs">
            <div className="gallery-row">
              <Button variant="primary-gradient">Run analysis</Button>
              <Button variant="ghost">Compare</Button>
              <Button variant="dark">Copy briefing</Button>
            </div>
            <div className="gallery-row">
              <Button disabled variant="primary-gradient">
                Run analysis
              </Button>
              <Button disabled variant="ghost">Compare</Button>
              <Button disabled variant="dark">Copy briefing</Button>
            </div>
            <SegmentedTabs
              activeId="findings"
              tabs={[
                { id: "overview", label: "Overview" },
                { id: "findings", label: "Findings", count: 3 },
                { id: "audit", label: "Audit" },
              ]}
            />
          </Card>

          <Card eyebrow="PROJECT SWITCHER" title="Closed">
            <ProjectSwitcher projects={demoProjects} selectedProject={demoProjects[0]} />
          </Card>

          <Card eyebrow="PROJECT SWITCHER" title="Open list">
            <div className="gallery-switcher-preview">
              <ProjectSwitcher initialOpen projects={demoProjects} selectedProject={demoProjects[2]} suppressBackdrop />
            </div>
          </Card>

          <Card eyebrow="PROJECT SWITCHER" title="Empty search">
            <div className="gallery-switcher-preview">
              <ProjectSwitcher
                initialOpen
                initialQuery="no-match"
                projects={emptyProjects}
                selectedProject={emptyProjects[0]}
                suppressBackdrop
              />
            </div>
          </Card>

          <Card eyebrow="LOADING" title="Skeleton states">
            <div style={{ display: "grid", gap: 14 }}>
              <div className="gallery-stack">
                <SkeletonLine width="72%" />
                <SkeletonLine width="48%" />
              </div>
              <SkeletonCard />
              <SkeletonTable rows={3} />
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
