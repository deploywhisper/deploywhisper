import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Clock,
  FileCode2,
  History,
  LayoutGrid,
  Play,
  Search,
  ShieldCheck,
  Trash2,
  Upload,
  Zap,
} from "lucide-react";

import {
  Button,
  Card,
  EvidenceTag,
  MonoRef,
  ProjectSwitcher,
  ScoreRing,
  SeverityBadge,
  SkeletonCard,
  SkeletonLine,
  SkeletonTable,
  Sparkline,
  VerdictChip,
  type ProjectOption,
} from "../components/ui";
import {
  createAnalysis,
  getProjects,
  getRecentAnalyses,
  getStatsSummary,
  getVerdictDistribution,
  type AnalysisReport,
  type Project,
  type StatsSummary,
  type VerdictDistribution,
} from "../api/dashboard";
import "./dashboard.css";

const supportedFilePattern = /\.(json|ya?ml|tf|tfvars|hcl|template)$/i;
const supportedNames = new Set(["Jenkinsfile"]);

type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
type Verdict = "NO-GO" | "CAUTION" | "PROCEED";

const severityDots: Record<Severity, string> = {
  CRITICAL: "var(--dw-critical-dot)",
  HIGH: "var(--dw-high-dot)",
  MEDIUM: "var(--dw-medium-dot)",
  LOW: "var(--dw-low-dot)",
};

export function isSupportedArtifact(file: Pick<File, "name">) {
  return supportedFilePattern.test(file.name) || supportedNames.has(file.name);
}

function normalizeSeverity(value: string | null | undefined): Severity {
  const normalized = String(value || "LOW").toUpperCase();
  if (normalized === "CRITICAL" || normalized === "HIGH" || normalized === "MEDIUM" || normalized === "LOW") {
    return normalized;
  }
  return "LOW";
}

function normalizeVerdict(value: string | null | undefined): Verdict {
  const normalized = String(value || "PROCEED").toUpperCase();
  if (normalized === "NO-GO" || normalized === "NO_GO" || normalized === "NO GO") {
    return "NO-GO";
  }
  if (normalized === "CAUTION") {
    return "CAUTION";
  }
  return "PROCEED";
}

function projectToOption(project: Project): ProjectOption {
  return {
    id: String(project.id),
    name: project.name || project.display_name || project.project_key,
    env: project.env_label || project.default_branch || "default",
    description: project.description || project.repository_url || project.project_key,
  };
}

function formatDuration(seconds: number | null | undefined) {
  if (!seconds || seconds <= 0) {
    return "n/a";
  }
  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }
  return `${Math.round(seconds / 60)}m`;
}

function formatPercent(value: number | null | undefined) {
  return `${Math.round(value ?? 0)}%`;
}

function formatCount(value: number | null | undefined) {
  return new Intl.NumberFormat("en-US").format(value ?? 0);
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getSparkPoints(series: { value: number }[] | undefined) {
  const values = series?.map((bucket) => bucket.value) ?? [];
  return values.length > 1 ? values : [0, 0, 0, 0, 0, 0, values[0] ?? 0];
}

function buildScope(project: Project | undefined) {
  return project ? { projectId: project.id } : {};
}

function DashboardError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="dw-error-strip" role="alert">
      <span className="dw-error-copy">
        <AlertCircle size={14} />
        <span>{message}</span>
      </span>
      <button className="dw-link-button" onClick={onRetry} type="button">
        Retry
      </button>
    </div>
  );
}

function Sidebar({ selectedProject }: { selectedProject: ProjectOption }) {
  const nav = [
    { label: "Dashboard", icon: LayoutGrid, active: true },
    { label: "Skills", icon: Zap },
    { label: "Incidents", icon: AlertTriangle, count: 0 },
    { label: "History", icon: History },
  ];

  return (
    <aside className="dw-sidebar">
      <div className="dw-brand">
        <span className="dw-brand-tile">
          <ShieldCheck size={18} />
        </span>
        <div>
          <div className="dw-brand-wordmark">
            Deploy<span>Whisper</span>
          </div>
          <div className="dw-brand-eyebrow">Evidence Engine</div>
        </div>
      </div>
      <nav className="dw-sidebar-nav" aria-label="Primary">
        {nav.map(({ label, icon: Icon, active, count }) => (
          <button key={label} className={`dw-nav-item${active ? " dw-nav-item-active" : ""}`} type="button">
            <Icon color={active ? "var(--dw-brand)" : "var(--dw-faint)"} size={17} />
            <span>{label}</span>
            {typeof count === "number" && <span className="dw-nav-count">{count}</span>}
          </button>
        ))}
      </nav>
      <div className="dw-active-project-card">
        <div className="dw-active-project-inner">
          <div className="dw-active-project-row">
            <span className="dw-active-dot" />
            Active Project
          </div>
          <div className="dw-active-project-name">{selectedProject.name}</div>
          <div className="dw-active-project-env">{selectedProject.env}</div>
          <div className="dw-active-project-chip">
            <ShieldCheck size={11} />
            Evidence Law enforced
          </div>
        </div>
      </div>
    </aside>
  );
}

function TopBar({
  projects,
  selectedProject,
  onProjectChange,
  onRunAnalysis,
  openSignal,
}: {
  projects: ProjectOption[];
  selectedProject: ProjectOption;
  onProjectChange: (project: ProjectOption) => void;
  onRunAnalysis: () => void;
  openSignal: number;
}) {
  return (
    <header className="dw-topbar">
      <div className="dw-global-search" aria-label="Global search">
        <Search size={15} />
        <span>Search analyses, services...</span>
        <kbd>⌘K</kbd>
      </div>
      <div className="dw-topbar-spacer" />
      <ProjectSwitcher openSignal={openSignal} projects={projects} selectedProject={selectedProject} onChange={onProjectChange} />
      <span className="dw-topbar-divider" />
      <Button variant="primary-gradient" onClick={onRunAnalysis}>
        <Play fill="#fff" size={13} /> Run analysis
      </Button>
      <div className="dw-avatar">DW</div>
    </header>
  );
}

function KpiCard({
  label,
  value,
  delta,
  attention = false,
  points,
  icon: Icon,
  sparkColor = "var(--dw-brand)",
}: {
  label: string;
  value: string;
  delta: string;
  attention?: boolean;
  points: number[];
  icon: typeof FileCode2;
  sparkColor?: string;
}) {
  return (
    <div className="dw-card dw-card-lift dw-kpi-card">
      <div className="dw-kpi-head">
        <span className="dw-kpi-icon">
          <Icon size={15} />
        </span>
        <Sparkline color={sparkColor} points={points} />
      </div>
      <div className="dw-kpi-label">{label}</div>
      <div className="dw-kpi-value-row">
        <span className="dw-kpi-value">{value}</span>
        <span className={`dw-kpi-delta ${attention ? "dw-kpi-delta-attention" : "dw-kpi-delta-good"}`}>{delta}</span>
      </div>
    </div>
  );
}

function KpiSection({
  stats,
  loading,
  error,
  onRetry,
}: {
  stats?: StatsSummary;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
}) {
  if (loading) {
    return (
      <div className="dw-kpi-grid" data-testid="kpi-skeletons">
        {[0, 1, 2, 3].map((item) => (
          <div className="dw-card dw-skeleton-block" key={item}>
            <SkeletonLine width={32} />
            <SkeletonLine width="60%" />
            <SkeletonLine width="42%" />
          </div>
        ))}
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="dw-kpi-grid">
        <div className="dw-card dw-skeleton-block" style={{ gridColumn: "1 / -1" }}>
          <DashboardError message="Dashboard KPIs are unavailable." onRetry={onRetry} />
        </div>
      </div>
    );
  }

  return (
    <div className="dw-kpi-grid">
      <KpiCard
        icon={FileCode2}
        label="Total analyses"
        value={formatCount(stats.total_analyses)}
        delta="7-day view"
        points={getSparkPoints(stats.series.analyses)}
      />
      <KpiCard
        attention={(stats.clean_verdict_rate ?? 0) < 50}
        icon={CheckCircle2}
        label="Clean verdict rate"
        sparkColor={(stats.clean_verdict_rate ?? 0) < 50 ? "var(--dw-high)" : "var(--dw-low-dot)"}
        value={formatPercent(stats.clean_verdict_rate)}
        delta={(stats.clean_verdict_rate ?? 0) < 50 ? "attention" : "healthy"}
        points={getSparkPoints(stats.series.clean_verdict_rate)}
      />
      <KpiCard
        attention={(stats.open_high_critical_count ?? 0) > 0}
        icon={AlertTriangle}
        label="High / critical open"
        sparkColor="var(--dw-high)"
        value={formatCount(stats.open_high_critical_count)}
        delta={(stats.open_high_critical_count ?? 0) > 0 ? "review" : "clear"}
        points={getSparkPoints(stats.series.open_high_critical_count)}
      />
      <KpiCard
        icon={Clock}
        label="Avg time to verdict"
        sparkColor="var(--dw-low-dot)"
        value={formatDuration(stats.avg_time_to_verdict_seconds)}
        delta="current"
        points={getSparkPoints(stats.series.avg_time_to_verdict_seconds)}
      />
    </div>
  );
}

function ScoreBar({ score, severity }: { score: number; severity: Severity }) {
  return (
    <span className="dw-score-bar">
      <span className="dw-score-track">
        <span className="dw-score-fill" style={{ background: severityDots[severity], width: `${Math.max(0, Math.min(score, 100))}%` }} />
      </span>
      {score}
    </span>
  );
}

export function RecentAnalysesTable({ analyses, onOpen }: { analyses: AnalysisReport[]; onOpen: (id: number) => void }) {
  if (analyses.length === 0) {
    return <div className="dw-empty-state">No analyses yet. Run a new analysis to start the evidence trail.</div>;
  }

  return (
    <table className="dw-recent-table">
      <thead>
        <tr>
          <th>Change</th>
          <th>Severity</th>
          <th>Verdict</th>
          <th>Score</th>
          <th>Env</th>
          <th aria-label="Open report" />
        </tr>
      </thead>
      <tbody>
        {analyses.map((analysis) => {
          const severity = normalizeSeverity(analysis.severity);
          const verdict = normalizeVerdict(analysis.verdict || analysis.recommendation);
          const filename = analysis.filenames[0] || "deployment artifact";
          const trigger = analysis.pr_ref || analysis.trigger_ref || "manual";
          return (
            <tr
              className="dw-clickable-row"
              key={analysis.id}
              onClick={() => onOpen(analysis.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onOpen(analysis.id);
                }
              }}
              tabIndex={0}
            >
              <td>
                <div className="dw-change-cell">
                  <span className="dw-file-tile">
                    <FileCode2 size={13} />
                  </span>
                  <div>
                    <div className="dw-file-name">{filename}</div>
                    <div className="dw-file-meta">
                      {trigger} · {formatDuration(analysis.analysis_duration_seconds)}
                    </div>
                  </div>
                </div>
              </td>
              <td>
                <SeverityBadge level={severity} />
              </td>
              <td>
                <VerdictChip size="sm" verdict={verdict} />
              </td>
              <td>
                <ScoreBar score={analysis.score ?? analysis.risk_score} severity={severity} />
              </td>
              <td>
                <span className="dw-env-ref">{analysis.env_label || analysis.workspace_label || "default"}</span>
              </td>
              <td>
                <ChevronRight color="var(--dw-faint)" size={15} />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function RecentAnalysesCard({
  analyses,
  loading,
  error,
  onRetry,
  onOpen,
}: {
  analyses?: AnalysisReport[];
  loading: boolean;
  error: boolean;
  onRetry: () => void;
  onOpen: (id: number) => void;
}) {
  return (
    <Card
      right={
        <Link className="dw-link-button" to="/history">
          View history <ChevronRight size={13} />
        </Link>
      }
      title="Recent analyses"
    >
      <p className="dw-card-subtitle">Last 5 deployment verdicts</p>
      {loading && <SkeletonTable rows={5} />}
      {!loading && error && <DashboardError message="Recent analyses are unavailable." onRetry={onRetry} />}
      {!loading && !error && <RecentAnalysesTable analyses={analyses ?? []} onOpen={onOpen} />}
    </Card>
  );
}

function latestStatValues(analysis: AnalysisReport) {
  const blast = (analysis.blast_radius?.direct_count ?? 0) + (analysis.blast_radius?.transitive_count ?? 0);
  const incident = Math.max(0, ...(analysis.incident_matches ?? []).map((match) => match.similarity ?? 0));
  const rollbackSteps = analysis.rollback_plan?.steps?.length ?? 0;
  return [
    [String(blast), "blast radius"],
    [incident ? `${Math.round(incident * 100)}%` : "0%", "incident match"],
    [rollbackSteps ? `${rollbackSteps} steps` : "n/a", "rollback est."],
  ];
}

function LatestBriefingCard({
  analysis,
  loading,
  error,
  onRetry,
  onOpen,
}: {
  analysis?: AnalysisReport;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
  onOpen: (id: number) => void;
}) {
  if (loading) {
    return (
      <div className="dw-latest-card">
        <div className="dw-latest-inner">
          <SkeletonLine width="44%" />
          <SkeletonCard />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dw-latest-card">
        <div className="dw-latest-inner">
          <span className="dw-dashboard-eyebrow">Latest Briefing</span>
          <DashboardError message="Latest briefing is unavailable." onRetry={onRetry} />
        </div>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="dw-latest-card">
        <div className="dw-latest-inner">
          <span className="dw-dashboard-eyebrow">Latest Briefing</span>
          <div className="dw-empty-state">No briefing yet. Upload artifacts to create the first report.</div>
        </div>
      </div>
    );
  }

  const verdict = normalizeVerdict(analysis.verdict || analysis.recommendation);
  const stats = latestStatValues(analysis);

  return (
    <div className="dw-latest-card">
      <div className="dw-latest-inner">
        <div className="dw-latest-head">
          <span className="dw-dashboard-eyebrow">Latest Briefing</span>
          <VerdictChip size="sm" verdict={verdict} />
        </div>
        <div className="dw-latest-body">
          <ScoreRing dark score={analysis.score ?? analysis.risk_score} size={72} />
          <p className="dw-latest-summary">{analysis.narrative_opening || analysis.top_risk || analysis.parse_summary}</p>
        </div>
        <div className="dw-latest-stats">
          {stats.map(([value, label]) => (
            <div className="dw-latest-stat" key={label}>
              <div className="dw-latest-stat-value">{value}</div>
              <div className="dw-latest-stat-label">{label}</div>
            </div>
          ))}
        </div>
        <Button className="dw-full-width-button" onClick={() => onOpen(analysis.id)} variant="primary-gradient">
          Open full briefing <ChevronRight size={15} />
        </Button>
      </div>
    </div>
  );
}

export function DropzoneCard({
  project,
  onOpenSwitcher,
}: {
  project: ProjectOption;
  onOpenSwitcher?: () => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [filterMessage, setFilterMessage] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => createAnalysis({ files: stagedFiles, projectId: Number(project.id) }),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      navigate(`/reports/${result.data.persisted_report.id}`);
    },
  });

  const addFiles = (files: FileList | File[]) => {
    const incoming = Array.from(files);
    const supported = incoming.filter(isSupportedArtifact);
    const rejected = incoming.length - supported.length;
    setFilterMessage(rejected ? `${rejected} unsupported file${rejected === 1 ? "" : "s"} skipped.` : null);
    setStagedFiles((current) => {
      const seen = new Set(current.map((file) => `${file.name}:${file.size}`));
      const next = [...current];
      for (const file of supported) {
        const key = `${file.name}:${file.size}`;
        if (!seen.has(key)) {
          next.push(file);
          seen.add(key);
        }
      }
      return next;
    });
  };

  const removeFile = (index: number) => {
    setStagedFiles((current) => current.filter((_, currentIndex) => currentIndex !== index));
  };

  const inFlight = mutation.isPending;
  const hasProject = Number(project.id) > 0;

  return (
    <Card
      right={
        <button className="dw-link-button" onClick={onOpenSwitcher} type="button">
          Change project
        </button>
      }
      title="New analysis"
    >
      <p className="dw-card-subtitle">
        Workspace <MonoRef>{project.name} · {project.env}</MonoRef>
      </p>
      <label
        className={`dw-dropzone${dragActive ? " dw-dropzone-active" : ""}`}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          setDragActive(false);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          setDragActive(false);
          addFiles(event.dataTransfer.files);
        }}
      >
        <input
          ref={inputRef}
          className="dw-dropzone-input"
          multiple
          onChange={(event) => {
            if (event.target.files) {
              addFiles(event.target.files);
            }
            event.currentTarget.value = "";
          }}
          type="file"
        />
        <span className="dw-dropzone-content">
          <span className="dw-dropzone-icon">
            <Upload size={18} />
          </span>
          <span className="dw-dropzone-line">
            Drop deployment artifacts, or <strong>browse files</strong>
          </span>
          <span className="dw-dropzone-formats">.tf · k8s yaml · ansible · Jenkinsfile · CloudFormation</span>
        </span>
      </label>
      {stagedFiles.length > 0 && (
        <div className="dw-staged-list" aria-label="Staged files">
          {stagedFiles.map((file, index) => (
            <div className="dw-staged-item" key={`${file.name}:${file.size}:${index}`}>
              <FileCode2 color="var(--dw-muted)" size={13} />
              <span className="dw-staged-name">{file.name}</span>
              <span className="dw-staged-size">{formatFileSize(file.size)}</span>
              <button aria-label={`Remove ${file.name}`} className="dw-icon-button" onClick={() => removeFile(index)} type="button">
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      )}
      {filterMessage && (
        <div className="dw-error-strip" role="status">
          <span className="dw-error-copy">
            <AlertCircle size={14} />
            <span>{filterMessage}</span>
          </span>
        </div>
      )}
      {mutation.isError && (
        <div className="dw-error-strip" role="alert">
          <span className="dw-error-copy">
            <AlertCircle size={14} />
            <span>Analysis failed. Confirm the artifacts are supported and retry.</span>
          </span>
        </div>
      )}
      {inFlight && (
        <div aria-label="Analysis upload in progress" className="dw-progress">
          <div className="dw-progress-bar" />
        </div>
      )}
      <div className="dw-upload-foot">
        <span className="dw-muted-small">{stagedFiles.length} files staged</span>
        <Button
          disabled={!hasProject || stagedFiles.length === 0 || inFlight}
          onClick={() => mutation.mutate()}
          variant="primary-gradient"
        >
          {inFlight ? "Analyzing" : "Analyze"}
        </Button>
      </div>
    </Card>
  );
}

function VerdictHealthCard({
  distribution,
  loading,
  error,
  onRetry,
}: {
  distribution?: VerdictDistribution;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
}) {
  if (loading) {
    return (
      <Card title="Verdict health">
        <SkeletonCard />
      </Card>
    );
  }

  if (error || !distribution) {
    return (
      <Card title="Verdict health">
        <DashboardError message="Verdict distribution is unavailable." onRetry={onRetry} />
      </Card>
    );
  }

  const counts = distribution.counts ?? {};
  const high = (counts["NO-GO"] ?? counts["no-go"] ?? 0) + (counts["HIGH"] ?? counts.high ?? 0);
  const caution = counts.CAUTION ?? counts.caution ?? 0;
  const clear = counts.PROCEED ?? counts.proceed ?? 0;
  const total = Math.max(distribution.total || high + caution + clear, 0);
  const safeTotal = total || 1;
  const series = [
    ["High focus", high, "#F2551F"],
    ["Caution", caution, "#F5B40A"],
    ["Clear", clear, "#17B26A"],
  ] as const;
  let cursor = 0;
  const stops = series
    .map(([, count, color]) => {
      const from = (cursor / safeTotal) * 360;
      cursor += count;
      return `${color} ${from}deg ${(cursor / safeTotal) * 360}deg`;
    })
    .join(",");
  const dominant = series.reduce((winner, item) => (item[1] > winner[1] ? item : winner), series[0]);
  const share = total ? Math.round((dominant[1] / total) * 100) : 0;

  return (
    <Card title="Verdict health">
      <p className="dw-card-subtitle">Distribution · last 30 days</p>
      <div className="dw-verdict-body">
        <div
          aria-label="Verdict distribution"
          className="dw-donut"
          role="img"
          style={{ background: total ? `conic-gradient(${stops})` : "#EEF0F3" }}
        >
          <div className="dw-donut-inner">
            <span className="dw-donut-share">{share}%</span>
            <span className="dw-donut-label">{dominant[0].toLowerCase()}</span>
          </div>
        </div>
        <ul className="dw-verdict-legend">
          {series.map(([label, count, color]) => (
            <li key={label}>
              <span className="dw-legend-dot" style={{ background: color }} />
              <span>{label}</span>
              <span className="dw-legend-count">{count}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="dw-alert-strip">
        <AlertCircle size={14} />
        <span>
          {high} of {total} reports are high or critical. Review open findings before the next release window.
        </span>
      </div>
    </Card>
  );
}

export function DashboardScreen() {
  const navigate = useNavigate();
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [projectSwitcherOpenSignal, setProjectSwitcherOpenSignal] = useState(0);
  const uploadRef = useRef<HTMLDivElement>(null);

  const projectsQuery = useQuery({
    queryKey: ["dashboard", "projects"],
    queryFn: getProjects,
    retry: false,
  });

  const projects = projectsQuery.data ?? [];
  const selectedProject = useMemo(() => {
    if (projects.length === 0) {
      return undefined;
    }
    return projects.find((project) => String(project.id) === selectedProjectId) ?? projects[0];
  }, [projects, selectedProjectId]);
  const projectOptions = projects.map(projectToOption);
  const selectedOption = selectedProject
    ? projectToOption(selectedProject)
    : { id: "0", name: "Loading project", env: "default", description: "Project context loading" };
  const scope = buildScope(selectedProject);

  const statsQuery = useQuery({
    enabled: Boolean(selectedProject),
    queryKey: ["dashboard", "stats", scope.projectId],
    queryFn: () => getStatsSummary(scope),
    retry: false,
  });
  const analysesQuery = useQuery({
    enabled: Boolean(selectedProject),
    queryKey: ["dashboard", "analyses", scope.projectId],
    queryFn: () => getRecentAnalyses(scope),
    retry: false,
  });
  const distributionQuery = useQuery({
    enabled: Boolean(selectedProject),
    queryKey: ["dashboard", "distribution", scope.projectId],
    queryFn: () => getVerdictDistribution(scope),
    retry: false,
  });

  const hasGlobalError = projectsQuery.isError;
  const latest = analysesQuery.data?.[0];

  const openReport = (id: number) => navigate(`/reports/${id}`);
  const refetchDashboard = () => {
    void statsQuery.refetch();
    void analysesQuery.refetch();
    void distributionQuery.refetch();
  };

  return (
    <div className="dw-app-shell dw-ui">
      <Sidebar selectedProject={selectedOption} />
      <div className="dw-main-pane">
        <TopBar
          onProjectChange={(project) => setSelectedProjectId(project.id)}
          onRunAnalysis={() => uploadRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })}
          openSignal={projectSwitcherOpenSignal}
          projects={projectOptions.length ? projectOptions : [selectedOption]}
          selectedProject={selectedOption}
        />
        <main className="dw-dashboard-scroll">
          <div className="dw-dashboard-wrap">
            {hasGlobalError && <DashboardError message="Project list is unavailable." onRetry={() => void projectsQuery.refetch()} />}
            <div className="dw-dashboard-header">
              <div>
                <h1 className="dw-dashboard-title">Good afternoon, DW</h1>
                <p className="dw-dashboard-subtitle">
                  Real-time verdicts across every environment · <strong>{selectedOption.name}</strong>
                </p>
              </div>
              <EvidenceTag>Evidence Law enforced</EvidenceTag>
            </div>

            <KpiSection
              error={statsQuery.isError}
              loading={projectsQuery.isLoading || statsQuery.isLoading}
              onRetry={() => void statsQuery.refetch()}
              stats={statsQuery.data}
            />

            <div className="dw-dashboard-grid">
              <div className="dw-table-card">
                <RecentAnalysesCard
                  analyses={analysesQuery.data}
                  error={analysesQuery.isError}
                  loading={projectsQuery.isLoading || analysesQuery.isLoading}
                  onOpen={openReport}
                  onRetry={() => void analysesQuery.refetch()}
                />
              </div>
              <LatestBriefingCard
                analysis={latest}
                error={analysesQuery.isError}
                loading={projectsQuery.isLoading || analysesQuery.isLoading}
                onOpen={openReport}
                onRetry={() => void analysesQuery.refetch()}
              />
            </div>

            <div className="dw-dashboard-grid" ref={uploadRef}>
              <DropzoneCard
                onOpenSwitcher={() => setProjectSwitcherOpenSignal((value) => value + 1)}
                project={selectedOption}
              />
              <VerdictHealthCard
                distribution={distributionQuery.data}
                error={distributionQuery.isError}
                loading={projectsQuery.isLoading || distributionQuery.isLoading}
                onRetry={() => void distributionQuery.refetch()}
              />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

export function ReportStub() {
  return (
    <main className="dw-report-stub dw-ui">
      <Card eyebrow="Report screen" title="Briefing route ready">
        <p className="dw-card-subtitle">The full report screen lands in Phase 4. This route keeps dashboard navigation stable.</p>
        <Link className="dw-link-button" to="/">
          Back to dashboard
        </Link>
      </Card>
    </main>
  );
}
