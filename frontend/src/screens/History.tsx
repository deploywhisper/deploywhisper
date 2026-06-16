import { Fragment, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getExpandedRowModel,
  useReactTable,
  type ExpandedState,
} from "@tanstack/react-table";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertCircle,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileCode2,
  History as HistoryIcon,
  LayoutGrid,
  Search,
  Settings,
  ShieldCheck,
  Trash2,
  Zap,
} from "lucide-react";

import { getProjects, type Project } from "../api/dashboard";
import {
  buildHistoryQueryParams,
  deleteAnalyses,
  getHistory,
  type HistoryFilters,
  type HistoryReport,
} from "../api/history";
import {
  Button,
  Card,
  ConfidenceBadge,
  EvidenceTag,
  MonoRef,
  ProjectSwitcher,
  SegmentedTabs,
  SeverityBadge,
  SkeletonTable,
  VerdictChip,
  type ProjectOption,
} from "../components/ui";
import type { Severity, Verdict } from "../theme/tokens";
import "./dashboard.css";
import "./history.css";

type FilterValue = "all" | string;

const severityTabs = [
  { id: "all", label: "All" },
  { id: "critical", label: "Critical" },
  { id: "high", label: "High" },
  { id: "medium", label: "Medium" },
  { id: "low", label: "Low" },
];

const verdictTabs = [
  { id: "all", label: "All" },
  { id: "no-go", label: "No-go" },
  { id: "caution", label: "Caution" },
  { id: "go", label: "Proceed" },
];

function projectToOption(project: Project): ProjectOption {
  return {
    id: String(project.id),
    name: project.name || project.display_name || project.project_key,
    env: project.env_label || project.default_branch || "default",
    description: project.description || project.repository_url || project.project_key,
  };
}

function normalizeSeverity(value: string | null | undefined): Severity {
  const normalized = String(value || "low").toUpperCase();
  if (normalized === "CRITICAL" || normalized === "HIGH" || normalized === "MEDIUM" || normalized === "LOW") {
    return normalized;
  }
  return "LOW";
}

function normalizeVerdict(value: string | null | undefined): Verdict {
  const normalized = String(value || "go").toUpperCase();
  if (normalized === "NO-GO" || normalized === "NO_GO" || normalized === "NO GO") {
    return "NO-GO";
  }
  if (normalized === "CAUTION") {
    return "CAUTION";
  }
  return "PROCEED";
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
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

function reportFiles(report: HistoryReport) {
  const filenames = report.filenames || report.audit?.files_analyzed || [];
  return filenames.length > 0 ? filenames : ["artifact"];
}

function reportTools(report: HistoryReport) {
  const tools = report.tool_mix || [];
  if (tools.length > 0) {
    return tools;
  }
  const fallback = report.submission_manifest_fallback?.map((item) => item.tool).filter(Boolean) || [];
  return fallback.length > 0 ? fallback : ["unknown"];
}

export function formatRescanDelta(report: HistoryReport) {
  const diff = report.previous_scan_diff;
  if (!diff) {
    return "First scan";
  }
  const prefix = diff.score_delta > 0 ? "+" : "";
  return `${prefix}${diff.score_delta} risk vs #${diff.previous_report_id}`;
}

function scoreTone(score: number) {
  if (score >= 90) {
    return "var(--dw-critical-dot)";
  }
  if (score >= 70) {
    return "var(--dw-high-dot)";
  }
  if (score >= 42) {
    return "var(--dw-medium-dot)";
  }
  return "var(--dw-low-dot)";
}

function selectionLabel(count: number) {
  return count === 1 ? "1 selected" : `${count} selected`;
}

function HistorySidebar({ selectedProject }: { selectedProject: ProjectOption }) {
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
        <Link className="dw-nav-item" to="/">
          <LayoutGrid color="var(--dw-faint)" size={17} />
          <span>Dashboard</span>
        </Link>
        <Link className="dw-nav-item" to="/skills">
          <Zap color="var(--dw-faint)" size={17} />
          <span>Skills</span>
        </Link>
        <Link className="dw-nav-item" to="/incidents">
          <AlertTriangle color="var(--dw-faint)" size={17} />
          <span>Incidents</span>
          <span className="dw-nav-count">0</span>
        </Link>
        <Link className="dw-nav-item dw-nav-item-active" to="/history">
          <HistoryIcon color="var(--dw-brand)" size={17} />
          <span>History</span>
        </Link>
        <Link className="dw-nav-item" to="/settings">
          <Settings color="var(--dw-faint)" size={17} />
          <span>Settings</span>
        </Link>
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

function HistoryTopBar({
  projects,
  selectedProject,
  onProjectChange,
}: {
  projects: ProjectOption[];
  selectedProject: ProjectOption;
  onProjectChange: (project: ProjectOption) => void;
}) {
  return (
    <header className="dw-topbar">
      <div className="dw-global-search" aria-label="Global search">
        <Search size={15} />
        <span>Search analyses, services...</span>
      </div>
      <div className="dw-topbar-spacer" />
      <ProjectSwitcher projects={projects} selectedProject={selectedProject} onChange={onProjectChange} />
      <span className="dw-topbar-divider" />
      <Link className="dw-history-top-link" to="/">
        <LayoutGrid size={14} />
        Dashboard
      </Link>
      <div className="dw-avatar">DW</div>
    </header>
  );
}

function HistoryError({ message, onRetry }: { message: string; onRetry: () => void }) {
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

function ScoreBar({ score }: { score: number }) {
  return (
    <span className="dw-history-score">
      <span className="dw-history-score-label">{score}</span>
      <span className="dw-history-score-track">
        <span className="dw-history-score-fill" style={{ background: scoreTone(score), width: `${Math.max(0, Math.min(100, score))}%` }} />
      </span>
    </span>
  );
}

function RescanDelta({ report }: { report: HistoryReport }) {
  const diff = report.previous_scan_diff;
  const direction = diff?.score_direction || "flat";
  return (
    <span className={`dw-rescan-delta dw-rescan-${direction}`}>
      {formatRescanDelta(report)}
    </span>
  );
}

function ExpandedReportDetail({ report }: { report: HistoryReport }) {
  const confidenceLevel = (report.confidence ?? 0) >= 0.7 ? "HIGH" : "LOW";
  const freshness = report.blast_radius?.freshness;
  const topologyFreshness = freshness?.updated_at ? `${freshness.updated_at}` : "Topology freshness unavailable";
  const redactionStatus = report.audit?.redaction_status || "standard";

  return (
    <div className="dw-history-detail">
      <div className="dw-history-detail-main">
        <div className="dw-history-detail-summary">
          <span className="dw-history-detail-label">Summary</span>
          <p>{report.narrative_opening || report.parse_summary || report.top_risk}</p>
        </div>
        <div className="dw-history-detail-grid">
          <span>
            <strong>Duration</strong>
            {formatDuration(report.analysis_duration_seconds)}
          </span>
          <span>
            <strong>Workspace</strong>
            {report.workspace_label || report.env_label || "Unassigned"}
          </span>
          <span>
            <strong>Status</strong>
            {report.analysis_status}
          </span>
          <span>
            <strong>Schema</strong>
            {report.report_schema_version}
          </span>
        </div>
      </div>
      <div className="dw-history-detail-side">
        <div className="dw-history-detail-tags">
          <ConfidenceBadge level={confidenceLevel} />
          <EvidenceTag>{redactionStatus}</EvidenceTag>
          <MonoRef>{topologyFreshness}</MonoRef>
        </div>
        <div className="dw-history-provenance">
          Risk: {report.assessment_source || "unknown"} | Narrative: {report.narrative_source || "unknown"}
          {report.narrative_provider ? ` | ${report.narrative_provider}` : ""}
        </div>
        <Link className="dw-history-report-link" to={`/reports/${report.id}?private=1`}>
          Open report
          <ChevronRight size={14} />
        </Link>
      </div>
    </div>
  );
}

type HistoryTableProps = {
  reports: HistoryReport[];
  selectedIds: Set<number>;
  expanded: ExpandedState;
  onExpandedChange: Dispatch<SetStateAction<ExpandedState>>;
  onToggleSelected: (id: number, checked: boolean) => void;
  onToggleSelectPage: (checked: boolean) => void;
  onOpenReport: (id: number) => void;
};

const columnHelper = createColumnHelper<HistoryReport>();

export function HistoryTable({
  reports,
  selectedIds,
  expanded,
  onExpandedChange,
  onToggleSelected,
  onToggleSelectPage,
  onOpenReport,
}: HistoryTableProps) {
  const allPageSelected = reports.length > 0 && reports.every((report) => selectedIds.has(report.id));
  const columns = useMemo(
    () => [
      columnHelper.display({
        id: "select",
        header: () => (
          <input
            aria-label="Select all reports on page"
            checked={allPageSelected}
            onChange={(event) => onToggleSelectPage(event.target.checked)}
            type="checkbox"
          />
        ),
        cell: ({ row }) => (
          <input
            aria-label={`Select report ${row.original.id}`}
            checked={selectedIds.has(row.original.id)}
            onChange={(event) => onToggleSelected(row.original.id, event.target.checked)}
            onClick={(event) => event.stopPropagation()}
            type="checkbox"
          />
        ),
      }),
      columnHelper.accessor("created_at", {
        header: "Timestamp",
        cell: ({ getValue, row }) => (
          <button className="dw-history-row-trigger" onClick={() => row.toggleExpanded()} type="button">
            {row.getIsExpanded() ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <span>{formatDateTime(getValue())}</span>
          </button>
        ),
      }),
      columnHelper.display({
        id: "change",
        header: "Change",
        cell: ({ row }) => (
          <span className="dw-history-change">
            <span>{row.original.top_risk}</span>
            <MonoRef>{reportFiles(row.original)[0]}</MonoRef>
          </span>
        ),
      }),
      columnHelper.accessor("severity", {
        header: "Severity",
        cell: ({ getValue }) => <SeverityBadge level={normalizeSeverity(getValue())} />,
      }),
      columnHelper.accessor("recommendation", {
        header: "Verdict",
        cell: ({ getValue }) => <VerdictChip size="sm" verdict={normalizeVerdict(getValue())} />,
      }),
      columnHelper.accessor("risk_score", {
        header: "Score",
        cell: ({ getValue }) => <ScoreBar score={getValue()} />,
      }),
      columnHelper.display({
        id: "tools",
        header: "Tools",
        cell: ({ row }) => (
          <span className="dw-history-tools">
            {reportTools(row.original)
              .slice(0, 2)
              .map((tool) => (
                <MonoRef key={tool}>{tool}</MonoRef>
              ))}
          </span>
        ),
      }),
      columnHelper.display({
        id: "rescan",
        header: "Rescan",
        cell: ({ row }) => <RescanDelta report={row.original} />,
      }),
      columnHelper.display({
        id: "open",
        header: "",
        cell: ({ row }) => (
          <button className="dw-history-icon-button" onClick={() => onOpenReport(row.original.id)} type="button">
            <ChevronRight size={15} />
            <span className="dw-sr-only">Open report {row.original.id}</span>
          </button>
        ),
      }),
    ],
    [allPageSelected, onOpenReport, onToggleSelectPage, onToggleSelected, selectedIds],
  );
  const table = useReactTable({
    data: reports,
    columns,
    state: { expanded },
    getCoreRowModel: getCoreRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getRowCanExpand: () => true,
    onExpandedChange,
  });

  return (
    <div className="dw-history-table-wrap">
      <table className="dw-history-table">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th key={header.id} scope="col">
                  {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <Fragment key={row.id}>
              <tr key={row.id} className="dw-history-row" onDoubleClick={() => onOpenReport(row.original.id)}>
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                ))}
              </tr>
              {row.getIsExpanded() && (
                <tr className="dw-history-expanded-row">
                  <td colSpan={row.getVisibleCells().length}>
                    <ExpandedReportDetail report={row.original} />
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HistoryFiltersBar({
  search,
  severity,
  recommendation,
  pageSize,
  onSearchChange,
  onSeverityChange,
  onRecommendationChange,
  onPageSizeChange,
}: {
  search: string;
  severity: FilterValue;
  recommendation: FilterValue;
  pageSize: number;
  onSearchChange: (value: string) => void;
  onSeverityChange: (value: string) => void;
  onRecommendationChange: (value: string) => void;
  onPageSizeChange: (value: number) => void;
}) {
  return (
    <div className="dw-history-filters">
      <label className="dw-history-search">
        <Search size={15} />
        <input
          aria-label="Search analysis history"
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Search top risk or summary"
          value={search}
        />
      </label>
      <div className="dw-history-filter-group">
        <span>Severity</span>
        <SegmentedTabs activeId={severity} label="Severity filter" onChange={onSeverityChange} tabs={severityTabs} />
      </div>
      <div className="dw-history-filter-group">
        <span>Verdict</span>
        <SegmentedTabs activeId={recommendation} label="Verdict filter" onChange={onRecommendationChange} tabs={verdictTabs} />
      </div>
      <label className="dw-history-page-size">
        Rows
        <select aria-label="Rows per page" onChange={(event) => onPageSizeChange(Number(event.target.value))} value={pageSize}>
          <option value={10}>10</option>
          <option value={25}>25</option>
          <option value={50}>50</option>
        </select>
      </label>
    </div>
  );
}

export function HistoryScreen() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState<FilterValue>("all");
  const [recommendation, setRecommendation] = useState<FilterValue>("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [expanded, setExpanded] = useState<ExpandedState>({});
  const [toast, setToast] = useState<string | null>(null);

  const projectsQuery = useQuery({ queryKey: ["projects"], queryFn: getProjects });
  const projects = projectsQuery.data ?? [];
  const projectOptions = projects.map(projectToOption);
  const selectedProject =
    projectOptions.find((project) => project.id === selectedProjectId) ||
    projectOptions[0] ||
    ({ id: "loading", name: "Loading", env: "default", description: "Loading projects" } satisfies ProjectOption);
  const selectedProjectData = projects.find((project) => String(project.id) === selectedProject.id) || projects[0];

  const filters: HistoryFilters = {
    projectId: selectedProjectData?.id,
    severity,
    recommendation,
    search,
    page,
    pageSize,
  };
  const historyQuery = useQuery({
    queryKey: ["history", buildHistoryQueryParams(filters).toString()],
    queryFn: () => getHistory(filters),
    enabled: Boolean(selectedProjectData),
  });
  const reports = historyQuery.data?.data ?? [];
  const totalCount = historyQuery.data?.meta.total_count ?? reports.length;
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  const startCount = totalCount === 0 ? 0 : (page - 1) * pageSize + 1;
  const endCount = Math.min(totalCount, page * pageSize);

  const deleteMutation = useMutation({
    mutationFn: (ids: number[]) => deleteAnalyses(ids),
    onSuccess: (response) => {
      setToast(`Deleted ${response.data.deleted_count} analysis report(s).`);
      setSelectedIds(new Set());
      setExpanded({});
      void queryClient.invalidateQueries({ queryKey: ["history"] });
    },
  });

  const resetToFirstPage = () => {
    setPage(1);
    setSelectedIds(new Set());
    setExpanded({});
  };

  const updateSelectedProject = (project: ProjectOption) => {
    setSelectedProjectId(project.id);
    resetToFirstPage();
  };

  const toggleSelected = (id: number, checked: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  };

  const toggleSelectPage = (checked: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      for (const report of reports) {
        if (checked) {
          next.add(report.id);
        } else {
          next.delete(report.id);
        }
      }
      return next;
    });
  };

  const selectedCount = selectedIds.size;
  const runDelete = () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0 || !window.confirm(`Delete ${ids.length} selected analysis report(s)?`)) {
      return;
    }
    deleteMutation.mutate(ids);
  };

  return (
    <div className="dw-app-shell dw-history-shell dw-ui">
      <HistorySidebar selectedProject={selectedProject} />
      <div className="dw-main-pane">
        <HistoryTopBar projects={projectOptions} selectedProject={selectedProject} onProjectChange={updateSelectedProject} />
        <main className="dw-dashboard-scroll">
          <div className="dw-dashboard-wrap dw-history-content">
          <section className="dw-hero-row">
            <div>
              <div className="dw-hero-eyebrow">
                <HistoryIcon size={14} />
                Analysis History
              </div>
              <h1>Review prior verdicts and rescan drift</h1>
              <p>Workspace: {selectedProject.name} / {selectedProject.env}</p>
            </div>
            <div className="dw-history-summary-pill">
              <BarChart3 size={14} />
              {totalCount} matching reports
            </div>
          </section>

          <Card
            eyebrow="HISTORY"
            right={
              <div className="dw-history-actions">
                <span aria-live="polite">{selectedCount > 0 ? selectionLabel(selectedCount) : "No selection"}</span>
                <Button disabled={selectedCount === 0 || deleteMutation.isPending} onClick={runDelete} variant="ghost">
                  <Trash2 size={14} />
                  Delete selected
                </Button>
              </div>
            }
            title="Analysis runs"
          >
            <HistoryFiltersBar
              pageSize={pageSize}
              recommendation={recommendation}
              search={search}
              severity={severity}
              onPageSizeChange={(value) => {
                setPageSize(value);
                resetToFirstPage();
              }}
              onRecommendationChange={(value) => {
                setRecommendation(value);
                resetToFirstPage();
              }}
              onSearchChange={(value) => {
                setSearch(value);
                resetToFirstPage();
              }}
              onSeverityChange={(value) => {
                setSeverity(value);
                resetToFirstPage();
              }}
            />

            {projectsQuery.isError && <HistoryError message="Projects could not be loaded." onRetry={() => void projectsQuery.refetch()} />}
            {historyQuery.isError && <HistoryError message="History could not be loaded." onRetry={() => void historyQuery.refetch()} />}
            {deleteMutation.isError && <HistoryError message="Selected reports could not be deleted." onRetry={() => deleteMutation.reset()} />}
            {toast && (
              <div className="dw-history-toast" role="status">
                <CheckCircle2 size={14} />
                {toast}
              </div>
            )}

            {historyQuery.isLoading || projectsQuery.isLoading ? (
              <SkeletonTable rows={pageSize > 10 ? 10 : pageSize} />
            ) : reports.length === 0 ? (
              <div className="dw-empty-state">
                <FileCode2 size={24} />
                <h2>No matching analyses</h2>
                <p>Adjust search, severity, or verdict filters to inspect this project history.</p>
              </div>
            ) : (
              <>
                <HistoryTable
                  expanded={expanded}
                  reports={reports}
                  selectedIds={selectedIds}
                  onExpandedChange={setExpanded}
                  onOpenReport={(id) => navigate(`/reports/${id}?private=1`)}
                  onToggleSelectPage={toggleSelectPage}
                  onToggleSelected={toggleSelected}
                />
                <div className="dw-history-pagination">
                  <span>
                    Showing {startCount}-{endCount} of {totalCount}
                  </span>
                  <div>
                    <Button disabled={page <= 1 || historyQuery.isFetching} onClick={() => setPage((value) => Math.max(1, value - 1))} variant="ghost">
                      Previous
                    </Button>
                    <span className="dw-history-page-indicator">Page {page} / {totalPages}</span>
                    <Button disabled={page >= totalPages || historyQuery.isFetching} onClick={() => setPage((value) => value + 1)} variant="ghost">
                      Next
                    </Button>
                  </div>
                </div>
              </>
            )}
          </Card>
          </div>
        </main>
      </div>
    </div>
  );
}
