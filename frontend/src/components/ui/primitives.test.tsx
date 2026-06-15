import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

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
} from ".";

function renderSnapshot(node: React.ReactElement) {
  return renderToStaticMarkup(node);
}

describe("SeverityBadge", () => {
  it("renders the critical severity anatomy", () => {
    expect(renderSnapshot(<SeverityBadge level="CRITICAL" />)).toMatchSnapshot();
  });
});

describe("VerdictChip", () => {
  it("renders small and medium verdict chips", () => {
    expect(
      renderSnapshot(
        <div>
          <VerdictChip size="sm" verdict="NO-GO" />
          <VerdictChip size="md" verdict="PROCEED" />
        </div>,
      ),
    ).toMatchSnapshot();
  });
});

describe("EvidenceTag", () => {
  it("renders deterministic evidence tags", () => {
    expect(renderSnapshot(<EvidenceTag>EV-01</EvidenceTag>)).toMatchSnapshot();
  });
});

describe("ConfidenceBadge", () => {
  it("renders high and low confidence variants", () => {
    expect(
      renderSnapshot(
        <div>
          <ConfidenceBadge level="HIGH" />
          <ConfidenceBadge level="LOW" />
        </div>,
      ),
    ).toMatchSnapshot();
  });
});

describe("MonoRef", () => {
  it("renders the evidence code chip", () => {
    expect(renderSnapshot(<MonoRef>terraform/rds.tf:18</MonoRef>)).toMatchSnapshot();
  });
});

describe("ScoreRing", () => {
  it("renders light and dark tracks", () => {
    expect(
      renderSnapshot(
        <div>
          <ScoreRing score={78} />
          <ScoreRing dark score={42} size={72} />
        </div>,
      ),
    ).toMatchSnapshot();
  });
});

describe("Sparkline", () => {
  it("renders a gradient sparkline path", () => {
    expect(renderSnapshot(<Sparkline points={[2, 3, 3, 5, 6, 9, 14]} />)).toMatchSnapshot();
  });
});

describe("Card", () => {
  it("renders card header and body anatomy", () => {
    expect(
      renderSnapshot(
        <Card eyebrow="OPERATIONAL NARRATIVE" title="What changed">
          <p>Deployment evidence summary</p>
        </Card>,
      ),
    ).toMatchSnapshot();
  });
});

describe("Button", () => {
  it("renders all button variants and disabled state", () => {
    expect(
      renderSnapshot(
        <div>
          <Button variant="primary-gradient">Run analysis</Button>
          <Button variant="ghost">Compare</Button>
          <Button variant="dark">Copy briefing</Button>
          <Button disabled variant="primary-gradient">
            Analyze
          </Button>
        </div>,
      ),
    ).toMatchSnapshot();
  });
});

describe("SegmentedTabs", () => {
  it("renders accessible tabs with count pill", () => {
    expect(
      renderSnapshot(
        <SegmentedTabs
          activeId="findings"
          tabs={[
            { id: "overview", label: "Overview" },
            { id: "findings", label: "Findings", count: 3 },
            { id: "audit", label: "Audit" },
          ]}
        />,
      ),
    ).toMatchSnapshot();
  });
});

describe("ProjectSwitcher", () => {
  it("renders the closed trigger state", () => {
    expect(renderSnapshot(<ProjectSwitcher projects={demoProjects} selectedProject={demoProjects[0]} />)).toMatchSnapshot();
  });

  it("renders the open listbox state", () => {
    expect(
      renderSnapshot(<ProjectSwitcher initialOpen projects={demoProjects} selectedProject={demoProjects[0]} />),
    ).toMatchSnapshot();
  });

  it("renders the empty search state", () => {
    expect(
      renderSnapshot(
        <ProjectSwitcher initialOpen initialQuery="missing-project" projects={demoProjects} selectedProject={demoProjects[0]} />,
      ),
    ).toMatchSnapshot();
  });
});

describe("Skeleton variants", () => {
  it("renders line, card, table, and report-header skeletons", () => {
    expect(
      renderSnapshot(
        <div>
          <SkeletonLine width={120} />
          <SkeletonCard />
          <SkeletonTable rows={2} />
          <SkeletonReportHeader />
        </div>,
      ),
    ).toMatchSnapshot();
  });
});
