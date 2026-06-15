import { useState } from "react";
import {
  LayoutGrid, Zap, AlertTriangle, History, Settings, Play, Search,
  ChevronRight, ChevronDown, ArrowLeft, Share2, GitCompare, Copy,
  ShieldCheck, FileCode2, Clock, Network, RotateCcw, CheckCircle2,
  CircleDot, Upload, Plus, AlertCircle, ArrowUpRight, ArrowDownRight,
  Activity, Layers, Check, ChevronsUpDown, FolderGit2,
} from "lucide-react";

const PROJECTS = [
  { name: "payments-api", env: "prod · main", desc: "Core payment processing" },
  { name: "test1", env: "test", desc: "Key test workspace" },
  { name: "checkout-infra", env: "staging", desc: "Checkout Terraform stack" },
  { name: "data-platform", env: "prod", desc: "Airflow + warehouse IaC" },
];

/* ──────────────── tokens ──────────────── */
const C = {
  brand: "#F2551F", brandDark: "#CE3D0C", brandSoft: "#FEF0E9",
  grad: "linear-gradient(135deg,#FF8A4C 0%,#F2511F 55%,#E03D0A 100%)",
  bg: "#F5F6F8", card: "#FFFFFF",
  border: "#E7E9EE", borderSoft: "#F0F1F4",
  ink: "#0E1116", text: "#252B36", muted: "#667085", faint: "#98A2B3",
  dark: "#14161C", dark2: "#1F222B", darkBorder: "#2C303C",
  critical: "#D92D20", criticalBg: "#FEECEB",
  high: "#E04F16", highBg: "#FEF0E7",
  medium: "#B54708", mediumBg: "#FEF4E4",
  low: "#079455", lowBg: "#E9F8F0",
};
const SEV = {
  CRITICAL: { fg: C.critical, bg: C.criticalBg, dot: "#F04438" },
  HIGH: { fg: C.high, bg: C.highBg, dot: "#F2551F" },
  MEDIUM: { fg: C.medium, bg: C.mediumBg, dot: "#F5A60A" },
  LOW: { fg: C.low, bg: C.lowBg, dot: "#17B26A" },
};
const VERDICT = { "NO-GO": "#D92D20", CAUTION: "#F2551F", PROCEED: "#079455" };

const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap');
:root{
  --display:'Plus Jakarta Sans',ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif;
  --body:'Inter',ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif;
  --mono:'JetBrains Mono',ui-monospace,'SF Mono',Menlo,monospace;
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-font-smoothing:antialiased}
button{font:inherit;border:none;background:none;cursor:pointer;color:inherit}
table{border-collapse:collapse}
.dw-app{display:flex;height:100vh;overflow:hidden;background:${C.bg};font-family:var(--body);color:${C.text};font-size:14px;line-height:1.5}
.dw-main{min-width:0;flex:1;display:flex;flex-direction:column}
.dw-scroll{min-height:0;flex:1;overflow-y:auto}
.dw-wrap{max-width:1120px;margin:0 auto;padding:26px 28px}
.dw-card{background:#fff;border:1px solid ${C.border};border-radius:16px;
  box-shadow:0 1px 2px rgba(16,24,40,.04),0 1px 3px rgba(16,24,40,.05)}
.dw-lift{transition:box-shadow .18s ease,transform .18s ease}
.dw-lift:hover{transform:translateY(-2px);box-shadow:0 4px 10px rgba(16,24,40,.06),0 12px 28px rgba(16,24,40,.09)}
.dw-btn{display:inline-flex;align-items:center;gap:7px;border-radius:10px;
  font-family:var(--display);font-weight:700;transition:transform .15s ease,box-shadow .15s ease,background .15s ease}
.dw-btn:hover{transform:translateY(-1px)}
.dw-btn:active{transform:scale(.97)}
.dw-btn-primary{background:${C.grad};color:#fff;padding:9px 16px;font-size:13px;
  box-shadow:0 4px 14px rgba(242,85,31,.32)}
.dw-btn-ghost{border:1px solid ${C.border};background:#fff;color:${C.text};
  padding:8px 13px;font-size:12px;box-shadow:0 1px 2px rgba(16,24,40,.05)}
.dw-btn-ghost:hover{border-color:#D5D9E2}
.dw-btn-dark{background:${C.ink};color:#fff;padding:8px 13px;font-size:12px}
.dw-nav{display:flex;align-items:center;gap:11px;width:100%;text-align:left;
  border-radius:11px;padding:9px 13px;font-size:13.5px;font-weight:500;color:${C.muted};
  transition:background .12s ease,color .12s ease}
.dw-nav:hover{background:#F3F4F7}
.dw-nav.on{background:${C.brandSoft};color:${C.brandDark};font-weight:600}
.dw-row{transition:background .12s ease}
.dw-row:hover{background:#FAFBFC}
.dw-tab{border-radius:999px;padding:7px 15px;font-family:var(--display);font-weight:600;
  font-size:12.5px;color:${C.muted};white-space:nowrap;transition:all .15s ease}
.dw-tab:hover{color:${C.ink}}
.dw-tab.on{background:#fff;color:${C.ink};font-weight:700;box-shadow:0 1px 3px rgba(16,24,40,.14)}
.dw-pill{border:1px solid ${C.border};background:#fff;border-radius:999px;padding:5px 13px;
  font-size:11.5px;font-weight:500;color:${C.muted};transition:all .12s ease}
.dw-pill:hover{transform:translateY(-1px);border-color:#D5D9E2;color:${C.text}}
.dw-link{color:${C.brand};font-weight:600;font-size:12px;border-radius:8px;padding:5px 9px;
  display:inline-flex;align-items:center;gap:4px;transition:background .12s ease}
.dw-link:hover{background:${C.brandSoft}}
.dw-drop{width:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;
  border:2px dashed #DCDFE6;border-radius:16px;padding:38px 24px;background:#FBFBFC;transition:all .18s ease}
.dw-drop:hover{border-color:${C.brand};background:${C.brandSoft}}
.dw-drop:hover .dw-drop-ico{background:${C.grad};color:#fff;box-shadow:0 6px 16px rgba(242,85,31,.35)}
.dw-drop-ico{display:flex;height:44px;width:44px;align-items:center;justify-content:center;border-radius:999px;
  background:#EFF1F4;color:${C.faint};transition:all .18s ease}
button:focus-visible{outline:2px solid ${C.brand};outline-offset:2px}
.dw-opt{transition:background .1s ease}
.dw-opt:hover{background:#F3F4F7}
.dw-newproj{transition:background .12s ease}
.dw-newproj:hover{background:${C.brandSoft}}
.dw-sb{display:none}
@media(min-width:900px){.dw-sb{display:flex}}
.dw-grid-kpi{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}
.dw-grid-32{display:grid;grid-template-columns:1fr;gap:18px}
.dw-grid-2{display:grid;grid-template-columns:1fr;gap:18px}
@media(min-width:1000px){
  .dw-grid-kpi{grid-template-columns:repeat(4,1fr)}
  .dw-grid-32{grid-template-columns:2fr 1fr}
  .dw-grid-2{grid-template-columns:1fr 1fr}
}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
@keyframes dwping{75%,100%{transform:scale(2.2);opacity:0}}
`;

/* type helpers */
const T = {
  h1: { fontFamily: "var(--display)", fontWeight: 800, fontSize: 22, color: C.ink, letterSpacing: "-0.03em" },
  h2: { fontFamily: "var(--display)", fontWeight: 700, fontSize: 15, color: C.ink, letterSpacing: "-0.01em" },
  h3: { fontFamily: "var(--display)", fontWeight: 700, fontSize: 14.5, color: C.ink },
  eyebrow: { fontFamily: "var(--mono)", fontSize: 9.5, letterSpacing: "0.15em", color: C.faint },
  sub: { fontSize: 12.5, color: C.muted },
  body: { fontSize: 13.5, lineHeight: 1.65, color: C.text },
  mono: (s = 12, c = C.muted) => ({ fontFamily: "var(--mono)", fontSize: s, color: c }),
};

/* ──────────────── badges ──────────────── */
function SeverityBadge({ level }) {
  const s = SEV[level];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6, borderRadius: 999,
      padding: "3px 10px", fontSize: 11, fontWeight: 600, background: s.bg, color: s.fg, whiteSpace: "nowrap",
    }}>
      <span style={{ height: 6, width: 6, borderRadius: 999, background: s.dot }} />
      {level[0] + level.slice(1).toLowerCase()}
    </span>
  );
}
function VerdictChip({ verdict, sm }) {
  const bg = VERDICT[verdict];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5, borderRadius: 999, color: "#fff",
      padding: sm ? "3px 10px" : "5px 13px", fontSize: sm ? 10 : 11, fontWeight: 700,
      fontFamily: "var(--display)", letterSpacing: "0.07em", background: bg,
      boxShadow: `0 2px 8px ${bg}55`, whiteSpace: "nowrap",
    }}>
      {verdict === "PROCEED" ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}
      {verdict}
    </span>
  );
}
function EvidenceTag({ children }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5, borderRadius: 7, padding: "2px 8px",
      fontFamily: "var(--mono)", fontSize: 10.5, border: "1px solid #CFEBDA",
      background: "#F2FBF6", color: "#067647", whiteSpace: "nowrap",
    }}>
      <CircleDot size={9} />{children}
    </span>
  );
}
function ConfidenceBadge({ level }) {
  const low = level === "LOW";
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5, borderRadius: 999, padding: "3px 10px",
      fontSize: 11, fontWeight: 500, border: `1px solid ${low ? "#F9DBCB" : "#CFEBDA"}`,
      color: low ? C.high : "#067647", background: "#fff", whiteSpace: "nowrap",
    }}>
      <Activity size={11} />{level[0] + level.slice(1).toLowerCase()} confidence
    </span>
  );
}
function MonoRef({ children }) {
  return (
    <code style={{
      fontFamily: "var(--mono)", fontSize: "0.85em", background: "#F2F4F7",
      border: "1px solid #E7E9EE", borderRadius: 6, padding: "1px 6px", color: C.ink, whiteSpace: "nowrap",
    }}>{children}</code>
  );
}

/* ──────────────── gauges ──────────────── */
function ScoreRing({ score, size = 76, stroke = 7, dark }) {
  const r = (size - stroke) / 2, circ = 2 * Math.PI * r;
  return (
    <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <defs>
          <linearGradient id={`rg${size}`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#FF8A4C" /><stop offset="100%" stopColor="#E03D0A" />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={dark ? "#2C303C" : "#EEF0F3"} strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={`url(#rg${size})`} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={circ * (1 - score / 100)} />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontFamily: "var(--display)", fontWeight: 800, fontSize: size * 0.3, color: dark ? "#fff" : C.ink, lineHeight: 1, letterSpacing: "-0.03em" }}>{score}</span>
        <span style={{ fontFamily: "var(--mono)", fontSize: 8, color: dark ? "#7E8696" : C.faint, letterSpacing: "0.08em", marginTop: 2 }}>/100</span>
      </div>
    </div>
  );
}
function Sparkline({ points, color = C.brand, w = 76, h = 26, id }) {
  const max = Math.max(...points), min = Math.min(...points);
  const pts = points.map((p, i) => [(i / (points.length - 1)) * w, h - 3 - ((p - min) / (max - min || 1)) * (h - 6)]);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
  return (
    <svg width={w} height={h} aria-hidden="true">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity=".2" /><stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${d}L${w},${h}L0,${h}Z`} fill={`url(#${id})`} />
      <path d={d} fill="none" stroke={color} strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

/* ──────────────── shell ──────────────── */
const NAV = [
  { id: "dashboard", label: "Dashboard", icon: LayoutGrid },
  { id: "skills", label: "Skills", icon: Zap },
  { id: "incidents", label: "Incidents", icon: AlertTriangle, count: 0 },
  { id: "history", label: "History", icon: History },
  { id: "settings", label: "Settings", icon: Settings },
];

function Sidebar({ view, onNav, project }) {
  return (
    <aside className="dw-sb" style={{ width: 236, flexShrink: 0, flexDirection: "column", background: "#fff", borderRight: `1px solid ${C.border}` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "20px 20px 26px" }}>
        <div style={{ display: "flex", height: 36, width: 36, alignItems: "center", justifyContent: "center", borderRadius: 11, background: C.grad, boxShadow: "0 4px 12px rgba(242,85,31,.35)" }}>
          <ShieldCheck size={18} color="#fff" />
        </div>
        <div>
          <div style={{ fontFamily: "var(--display)", fontWeight: 800, fontSize: 15, color: C.ink, letterSpacing: "-0.02em" }}>
            Deploy<span style={{ color: C.brand }}>Whisper</span>
          </div>
          <div style={{ ...T.eyebrow, fontSize: 8.5 }}>EVIDENCE ENGINE</div>
        </div>
      </div>
      <nav style={{ display: "flex", flexDirection: "column", gap: 3, padding: "0 12px" }} aria-label="Primary">
        {NAV.map(({ id, label, icon: Icon, count }) => {
          const on = view === id || (view === "report" && id === "history");
          return (
            <button key={id} className={`dw-nav${on ? " on" : ""}`} onClick={() => onNav(id)}>
              <Icon size={17} style={{ color: on ? C.brand : C.faint, flexShrink: 0 }} />
              <span style={{ flex: 1 }}>{label}</span>
              {typeof count === "number" && (
                <span style={{ borderRadius: 999, padding: "1px 7px", fontSize: 10, fontWeight: 600, background: "#F0F1F4", color: C.faint, fontFamily: "var(--mono)" }}>{count}</span>
              )}
            </button>
          );
        })}
      </nav>
      <div style={{ marginTop: "auto", padding: 14 }}>
        <div style={{ borderRadius: 16, padding: 16, background: C.dark, boxShadow: "0 8px 24px rgba(16,24,40,.18)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7, fontFamily: "var(--mono)", fontSize: 8.5, color: "#7E8696", letterSpacing: "0.15em" }}>
            <span style={{ position: "relative", display: "flex", height: 6, width: 6 }}>
              <span style={{ position: "absolute", height: "100%", width: "100%", borderRadius: 999, background: C.brand, animation: "dwping 1.6s cubic-bezier(0,0,.2,1) infinite" }} />
              <span style={{ position: "relative", height: 6, width: 6, borderRadius: 999, background: C.brand }} />
            </span>
            ACTIVE PROJECT
          </div>
          <div style={{ marginTop: 8, fontFamily: "var(--display)", fontWeight: 700, fontSize: 14, color: "#fff" }}>{project.name}</div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "#7E8696", marginTop: 1 }}>{project.env}</div>
          <div style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 6, borderRadius: 9, padding: "6px 9px", background: C.dark2, fontFamily: "var(--mono)", fontSize: 9.5, color: "#75DFA6" }}>
            <ShieldCheck size={11} /> Evidence Law enforced
          </div>
        </div>
      </div>
    </aside>
  );
}

function ProjectSwitcher({ project, setProject, initialOpen = false }) {
  const [open, setOpen] = useState(initialOpen);
  const [q, setQ] = useState("");
  const list = PROJECTS.filter((p) => p.name.toLowerCase().includes(q.toLowerCase()));
  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => setOpen(!open)}
        aria-haspopup="listbox" aria-expanded={open}
        className="dw-btn dw-btn-ghost"
        style={{ padding: "7px 12px", gap: 8, fontWeight: 600, borderColor: open ? C.brand : undefined, boxShadow: open ? "0 0 0 3px rgba(242,85,31,.12)" : undefined }}
      >
        <span style={{ display: "flex", height: 20, width: 20, alignItems: "center", justifyContent: "center", borderRadius: 6, background: C.brandSoft, color: C.brand }}>
          <FolderGit2 size={12} />
        </span>
        <span style={{ maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 12.5 }}>{project.name}</span>
        <span style={{ borderRadius: 999, padding: "1px 7px", fontSize: 9.5, fontFamily: "var(--mono)", background: "#F0F1F4", color: C.muted }}>{project.env.split(" ")[0]}</span>
        <ChevronsUpDown size={13} style={{ color: C.faint }} />
      </button>
      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 40 }} />
          <div role="listbox" style={{
            position: "absolute", right: 0, top: "calc(100% + 8px)", zIndex: 50, width: 296,
            borderRadius: 14, border: `1px solid ${C.border}`, background: "#fff",
            boxShadow: "0 4px 12px rgba(16,24,40,.08), 0 20px 48px rgba(16,24,40,.16)", overflow: "hidden",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, borderBottom: `1px solid ${C.borderSoft}`, padding: "10px 14px" }}>
              <Search size={14} style={{ color: C.faint, flexShrink: 0 }} />
              <input
                autoFocus value={q} onChange={(e) => setQ(e.target.value)}
                placeholder="Search projects…"
                style={{ flex: 1, border: "none", outline: "none", fontSize: 13, fontFamily: "var(--body)", color: C.text, background: "transparent" }}
              />
            </div>
            <div style={{ maxHeight: 240, overflowY: "auto", padding: 6 }}>
              <div style={{ padding: "6px 10px 4px", fontFamily: "var(--mono)", fontSize: 9, letterSpacing: "0.14em", color: C.faint }}>
                PROJECTS · {list.length}
              </div>
              {list.length === 0 && (
                <div style={{ padding: "14px 10px", fontSize: 12.5, color: C.muted }}>
                  No project matches “{q}”. Create it below.
                </div>
              )}
              {list.map((p) => {
                const on = p.name === project.name;
                return (
                  <button
                    key={p.name} role="option" aria-selected={on}
                    onClick={() => { setProject(p); setOpen(false); setQ(""); }}
                    className="dw-opt"
                    style={{ display: "flex", width: "100%", alignItems: "center", gap: 10, borderRadius: 9, padding: "8px 10px", textAlign: "left", background: on ? C.brandSoft : "transparent" }}
                  >
                    <span style={{ display: "flex", height: 28, width: 28, flexShrink: 0, alignItems: "center", justifyContent: "center", borderRadius: 8, background: on ? "#fff" : "#F3F4F7", color: on ? C.brand : C.muted }}>
                      <FolderGit2 size={13} />
                    </span>
                    <span style={{ minWidth: 0, flex: 1 }}>
                      <span style={{ display: "flex", alignItems: "center", gap: 7 }}>
                        <span style={{ fontSize: 13, fontWeight: 600, color: on ? C.brandDark : C.ink, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.name}</span>
                        <span style={{ fontFamily: "var(--mono)", fontSize: 9.5, color: C.faint }}>{p.env}</span>
                      </span>
                      <span style={{ display: "block", fontSize: 11, color: C.muted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.desc}</span>
                    </span>
                    {on && <Check size={15} style={{ color: C.brand, flexShrink: 0 }} />}
                  </button>
                );
              })}
            </div>
            <button className="dw-newproj" style={{ display: "flex", width: "100%", alignItems: "center", gap: 9, borderTop: `1px solid ${C.borderSoft}`, padding: "11px 16px", fontSize: 12.5, fontWeight: 600, color: C.brand, background: "#FCFCFD" }}>
              <span style={{ display: "flex", height: 22, width: 22, alignItems: "center", justifyContent: "center", borderRadius: 7, background: C.brandSoft }}>
                <Plus size={13} />
              </span>
              New project
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function TopBar({ project, setProject, initialSwitcherOpen }) {
  return (
    <header style={{ display: "flex", alignItems: "center", gap: 10, borderBottom: `1px solid ${C.border}`, background: "rgba(255,255,255,.85)", backdropFilter: "blur(12px)", padding: "11px 24px", position: "relative", zIndex: 30 }}>
      <div style={{ display: "flex", flex: 1, maxWidth: 380, alignItems: "center", gap: 9, borderRadius: 11, border: `1px solid ${C.border}`, background: "#FBFBFC", padding: "8px 13px" }}>
        <Search size={15} style={{ color: C.faint, flexShrink: 0 }} />
        <span style={{ fontSize: 13, color: C.faint, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>Search analyses, services…</span>
        <kbd style={{ marginLeft: "auto", borderRadius: 6, border: `1px solid ${C.border}`, background: "#fff", padding: "1px 6px", fontSize: 10, color: C.faint, fontFamily: "var(--mono)" }}>⌘K</kbd>
      </div>
      <div style={{ flex: 1 }} />
      <ProjectSwitcher project={project} setProject={setProject} initialOpen={initialSwitcherOpen} />
      <span style={{ height: 22, width: 1, background: C.border, margin: "0 2px" }} />
      <button className="dw-btn dw-btn-primary"><Play size={13} fill="#fff" /> Run analysis</button>
      <div style={{ display: "flex", height: 34, width: 34, alignItems: "center", justifyContent: "center", borderRadius: 999, background: C.grad, color: "#fff", fontSize: 12, fontWeight: 700, fontFamily: "var(--display)" }}>JD</div>
    </header>
  );
}

/* ──────────────── dashboard ──────────────── */
const RECENT = [
  { file: "terraform/rds.tf +2", pr: "#2847", sev: "HIGH", verdict: "CAUTION", score: 78, env: "prod", dur: "14s", open: true },
  { file: "k8s/nginx-k8s.yml", pr: "#2846", sev: "MEDIUM", verdict: "CAUTION", score: 42, env: "staging", dur: "9s" },
  { file: "k8s/etcd-sc-backup.yaml", pr: "#2845", sev: "HIGH", verdict: "NO-GO", score: 81, env: "prod", dur: "11s" },
  { file: "ansible/site.yml", pr: "#2844", sev: "LOW", verdict: "PROCEED", score: 18, env: "staging", dur: "8s" },
  { file: "cfn/network-stack.json", pr: "#2843", sev: "MEDIUM", verdict: "CAUTION", score: 55, env: "prod", dur: "12s" },
];

function Kpi({ label, value, delta, up, good, icon: Icon, spark, sparkColor, sid }) {
  return (
    <div className="dw-card dw-lift" style={{ padding: 17 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ display: "flex", height: 32, width: 32, alignItems: "center", justifyContent: "center", borderRadius: 9, background: C.brandSoft, color: C.brand }}>
          <Icon size={15} />
        </span>
        <Sparkline points={spark} color={sparkColor || C.brand} id={sid} />
      </div>
      <div style={{ marginTop: 13, fontSize: 12, fontWeight: 500, color: C.muted }}>{label}</div>
      <div style={{ marginTop: 2, display: "flex", alignItems: "baseline", gap: 8 }}>
        <span style={{ fontFamily: "var(--display)", fontWeight: 800, fontSize: 25, color: C.ink, letterSpacing: "-0.03em" }}>{value}</span>
        <span style={{
          display: "inline-flex", alignItems: "center", gap: 2, borderRadius: 999, padding: "1px 7px",
          fontSize: 10.5, fontWeight: 600, background: good ? C.lowBg : C.highBg, color: good ? C.low : C.high,
        }}>
          {up ? <ArrowUpRight size={11} /> : <ArrowDownRight size={11} />}{delta}
        </span>
      </div>
    </div>
  );
}

function ScoreBar({ score, sev }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 7, fontFamily: "var(--mono)", fontSize: 12.5, fontWeight: 600, color: C.ink }}>
      <span style={{ height: 5, width: 38, borderRadius: 999, background: "#EEF0F3", overflow: "hidden", display: "inline-block" }}>
        <span style={{ display: "block", height: "100%", borderRadius: 999, width: `${score}%`, background: SEV[sev].dot }} />
      </span>
      {score}
    </span>
  );
}

function RecentTable({ openReport }) {
  const th = { padding: "9px 12px", textAlign: "left", fontSize: 10.5, fontWeight: 600, color: C.faint, letterSpacing: "0.04em", textTransform: "uppercase", background: "#FAFBFC", borderTop: `1px solid ${C.borderSoft}`, borderBottom: `1px solid ${C.borderSoft}` };
  return (
    <div className="dw-card" style={{ overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "18px 20px 13px" }}>
        <div>
          <h3 style={T.h3}>Recent analyses</h3>
          <p style={{ ...T.sub, marginTop: 1, fontSize: 12 }}>Last 5 deployment verdicts</p>
        </div>
        <button className="dw-link">View history <ChevronRight size={13} /></button>
      </div>
      <table style={{ width: "100%", fontSize: 13 }}>
        <thead><tr>
          <th style={{ ...th, paddingLeft: 20 }}>Change</th><th style={th}>Severity</th>
          <th style={th}>Verdict</th><th style={th}>Score</th><th style={th}>Env</th><th style={th} />
        </tr></thead>
        <tbody>
          {RECENT.map((r, i) => (
            <tr key={i} className="dw-row" onClick={() => r.open && openReport()}
              style={{ cursor: r.open ? "pointer" : "default", borderBottom: i < RECENT.length - 1 ? `1px solid ${C.borderSoft}` : "none" }}>
              <td style={{ padding: "11px 12px 11px 20px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ display: "flex", height: 28, width: 28, alignItems: "center", justifyContent: "center", borderRadius: 8, background: "#F3F4F7", color: C.muted, flexShrink: 0 }}>
                    <FileCode2 size={13} />
                  </span>
                  <div>
                    <div style={T.mono(12, C.ink)}>{r.file}</div>
                    <div style={{ fontSize: 11, color: C.faint }}>PR {r.pr} · {r.dur}</div>
                  </div>
                </div>
              </td>
              <td style={{ padding: "11px 12px" }}><SeverityBadge level={r.sev} /></td>
              <td style={{ padding: "11px 12px" }}><VerdictChip verdict={r.verdict} sm /></td>
              <td style={{ padding: "11px 12px" }}><ScoreBar score={r.score} sev={r.sev} /></td>
              <td style={{ padding: "11px 12px" }}><span style={T.mono(11)}>{r.env}</span></td>
              <td style={{ padding: "11px 16px 11px 12px", textAlign: "right" }}>
                {r.open && <ChevronRight size={15} style={{ color: C.faint }} />}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BriefingCard({ onOpen }) {
  return (
    <div style={{ position: "relative", overflow: "hidden", borderRadius: 16, padding: 20, background: C.dark, boxShadow: "0 8px 28px rgba(16,24,40,.22)", height: "100%" }}>
      <div style={{ position: "absolute", right: -56, top: -56, height: 190, width: 190, borderRadius: 999, opacity: 0.22, background: "radial-gradient(circle,#F2551F 0%,transparent 70%)", pointerEvents: "none" }} />
      <div style={{ position: "relative", display: "flex", flexDirection: "column", height: "100%" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontFamily: "var(--mono)", fontSize: 9, letterSpacing: "0.16em", color: "#7E8696" }}>LATEST BRIEFING</span>
          <VerdictChip verdict="CAUTION" sm />
        </div>
        <div style={{ marginTop: 16, display: "flex", alignItems: "center", gap: 16, flex: 1 }}>
          <ScoreRing score={78} size={72} stroke={6.5} dark />
          <p style={{ flex: 1, fontSize: 12.5, lineHeight: 1.6, color: "#C2C7D1" }}>
            RDS security group widened during ECS rollout. Cross-tool with K8s replica scale-up risks pool exhaustion in prod.
          </p>
        </div>
        <div style={{ marginTop: 16, marginBottom: 16, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
          {[["8", "blast radius"], ["89%", "incident match"], ["12m", "rollback est."]].map(([v, l]) => (
            <div key={l} style={{ borderRadius: 11, padding: "9px 11px", background: C.dark2, border: `1px solid ${C.darkBorder}` }}>
              <div style={{ fontFamily: "var(--display)", fontWeight: 700, fontSize: 15.5, color: "#fff" }}>{v}</div>
              <div style={{ marginTop: 1, fontSize: 10, color: "#7E8696" }}>{l}</div>
            </div>
          ))}
        </div>
        <button onClick={onOpen} className="dw-btn dw-btn-primary" style={{ marginTop: "auto", paddingTop: 10, paddingBottom: 10, width: "100%", justifyContent: "center" }}>
          Open full briefing <ChevronRight size={15} />
        </button>
      </div>
    </div>
  );
}

function VerdictHealth() {
  const data = [["High focus", 11, "#F2551F"], ["Caution", 3, "#F5B40A"], ["Clear", 0, "#17B26A"]];
  const total = 14;
  let acc = 0;
  const stops = data.map(([, n, color]) => {
    const from = (acc / total) * 360; acc += n;
    return `${color} ${from}deg ${(acc / total) * 360}deg`;
  }).join(",");
  return (
    <div className="dw-card" style={{ padding: 20 }}>
      <h3 style={T.h3}>Verdict health</h3>
      <p style={{ ...T.sub, marginTop: 1, fontSize: 12 }}>Distribution · last 30 days</p>
      <div style={{ marginTop: 18, display: "flex", alignItems: "center", gap: 20 }}>
        <div role="img" aria-label="Verdict distribution" style={{ position: "relative", height: 104, width: 104, flexShrink: 0, borderRadius: 999, background: `conic-gradient(${stops})` }}>
          <div style={{ position: "absolute", inset: 10, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", borderRadius: 999, background: "#fff" }}>
            <span style={{ fontFamily: "var(--display)", fontWeight: 800, fontSize: 19, color: C.ink }}>79%</span>
            <span style={{ fontSize: 9.5, color: C.faint }}>high focus</span>
          </div>
        </div>
        <ul style={{ flex: 1, listStyle: "none", display: "flex", flexDirection: "column", gap: 10 }}>
          {data.map(([label, n, color]) => (
            <li key={label} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
              <span style={{ height: 8, width: 8, borderRadius: 999, background: color }} />
              <span style={{ color: C.text }}>{label}</span>
              <span style={{ marginLeft: "auto", ...T.mono(11.5, C.muted), fontWeight: 600 }}>{n}</span>
            </li>
          ))}
        </ul>
      </div>
      <div style={{ marginTop: 16, display: "flex", gap: 8, borderRadius: 11, padding: 12, background: C.highBg, fontSize: 11.5, lineHeight: 1.55, color: "#93370D" }}>
        <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
        <span>11 of 14 reports are high or critical. Review open findings before the next release window.</span>
      </div>
    </div>
  );
}

function UploadZone({ project }) {
  return (
    <div className="dw-card" style={{ padding: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h3 style={T.h3}>New analysis</h3>
          <p style={{ ...T.sub, marginTop: 2, fontSize: 12 }}>Workspace <MonoRef>{project.name} · {project.env}</MonoRef></p>
        </div>
        <button className="dw-link">Change project</button>
      </div>
      <button className="dw-drop" style={{ marginTop: 15 }}>
        <span className="dw-drop-ico"><Upload size={18} /></span>
        <span style={{ fontSize: 13.5, fontWeight: 500, color: C.text }}>
          Drop deployment artifacts, or <span style={{ color: C.brand, fontWeight: 600 }}>browse files</span>
        </span>
        <span style={T.mono(10.5, C.faint)}>.tf · k8s yaml · ansible · Jenkinsfile · CloudFormation</span>
      </button>
      <div style={{ marginTop: 13, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 12, color: C.faint }}>0 files staged</span>
        <button disabled style={{ borderRadius: 11, padding: "9px 20px", fontSize: 13, fontWeight: 700, fontFamily: "var(--display)", background: "#F0F1F4", color: C.faint, cursor: "not-allowed" }}>
          Analyze
        </button>
      </div>
    </div>
  );
}

function Dashboard({ openReport, project }) {
  return (
    <div className="dw-wrap">
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
        <div>
          <h1 style={T.h1}>Good afternoon, JD</h1>
          <p style={{ ...T.sub, marginTop: 3 }}>
            Real-time verdicts across every environment · <span style={{ fontWeight: 600, color: C.text }}>{project.name}</span>
          </p>
        </div>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6, borderRadius: 999, border: "1px solid #CFEBDA", background: "#F2FBF6", padding: "6px 13px", fontSize: 11.5, fontWeight: 500, color: "#067647" }}>
          <ShieldCheck size={13} /> Evidence Law enforced
        </span>
      </div>

      <div className="dw-grid-kpi" style={{ marginTop: 22 }}>
        <Kpi label="Total analyses" value="14" delta="4 this wk" up good icon={FileCode2} spark={[2, 3, 3, 5, 6, 9, 14]} sid="s1" />
        <Kpi label="Clean verdict rate" value="0.0%" delta="attention" up={false} icon={CheckCircle2} spark={[12, 8, 6, 4, 2, 1, 0]} sparkColor="#E04F16" sid="s2" />
        <Kpi label="High / critical open" value="11" delta="+3 vs wk" up icon={AlertTriangle} spark={[2, 4, 5, 7, 8, 10, 11]} sparkColor="#E04F16" sid="s3" />
        <Kpi label="Avg time to verdict" value="10s" delta="−2s" up={false} good icon={Clock} spark={[15, 14, 13, 12, 12, 11, 10]} sparkColor="#17B26A" sid="s4" />
      </div>

      <div className="dw-grid-32" style={{ marginTop: 18 }}>
        <RecentTable openReport={openReport} />
        <BriefingCard onOpen={openReport} />
      </div>

      <div className="dw-grid-32" style={{ marginTop: 18 }}>
        <UploadZone project={project} />
        <VerdictHealth />
      </div>
    </div>
  );
}

/* ──────────────── report ──────────────── */
const FINDINGS = [
  {
    sev: "HIGH", crossTool: true,
    title: "RDS publicly exposed during rollout",
    body: "Security-group ingress widened from VPC CIDR to 0.0.0.0/0. Exposes Postgres 5432 to the public internet during the deploy window.",
    evidence: ["rds.tf:18", "checkov CKV_AWS_24"],
    diff: { file: "terraform/rds.tf", lines: [
      { n: 17, txt: "  to_port     = 5432" },
      { n: 18, txt: '  cidr_blocks = ["10.0.0.0/16"]', del: true },
      { n: 18, txt: '  cidr_blocks = ["0.0.0.0/0"]', add: true },
    ]},
  },
  {
    sev: "HIGH",
    title: "Connection-pool exhaustion likely",
    body: "Replica scale-up 3 → 10 against unchanged Aurora max_connections. 89% similarity to INC-2024-Q3-17, a prior pool-exhaustion incident.",
    evidence: ["deployment.yaml:24", "incident-match 0.89"],
    diff: { file: "k8s/deployment.yaml", lines: [
      { n: 23, txt: "spec:" },
      { n: 24, txt: "  replicas: 3", del: true },
      { n: 24, txt: "  replicas: 10  # scale for Black Friday", add: true },
    ]},
  },
  {
    sev: "MEDIUM",
    title: "Rollback requires DB validation",
    body: "Rollback complexity 4/5. Reverting requires a stateful connectivity check after the security group is narrowed back.",
    evidence: ["rollback plan · 5 steps"],
  },
];
const TABS = ["Overview", "Findings", "Confidence", "Context", "Rollback", "Audit"];

function ReportHeader({ tab, setTab, onBack }) {
  return (
    <div style={{ position: "sticky", top: 0, zIndex: 20, borderBottom: `1px solid ${C.border}`, background: "rgba(245,246,248,.88)", backdropFilter: "blur(14px)" }}>
      <div style={{ maxWidth: 1120, margin: "0 auto", padding: "14px 28px 12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 18, flexWrap: "wrap" }}>
          <button onClick={onBack} className="dw-btn dw-btn-ghost" style={{ padding: 9, borderRadius: 11 }} aria-label="Back to dashboard">
            <ArrowLeft size={16} />
          </button>
          <ScoreRing score={78} size={62} stroke={6} />
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <VerdictChip verdict="CAUTION" />
              <SeverityBadge level="HIGH" />
              <ConfidenceBadge level="HIGH" />
              <EvidenceTag>4 deterministic items</EvidenceTag>
            </div>
            <h1 style={{ ...T.h2, fontSize: 16.5, marginTop: 6, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              Review before merge — RDS exposure + replica scale-up
            </h1>
            <div style={{ marginTop: 3, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: 11.5, color: C.muted }}>
              <MonoRef>PR #2847</MonoRef>
              <span>payments-api · prod</span><span style={{ color: C.faint }}>·</span>
              <span>Jun 9, 2:57 PM</span><span style={{ color: C.faint }}>·</span>
              <span style={T.mono(11)}>3 files · 14s</span>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button className="dw-btn dw-btn-ghost"><GitCompare size={13} /> Compare</button>
            <button className="dw-btn dw-btn-ghost"><Share2 size={13} /> Share</button>
            <button className="dw-btn dw-btn-dark"><Copy size={13} /> Copy briefing</button>
          </div>
        </div>
        <div role="tablist" style={{ marginTop: 12, display: "inline-flex", gap: 2, borderRadius: 999, border: `1px solid ${C.border}`, background: "#EDEEF2", padding: 4, maxWidth: "100%", overflowX: "auto" }}>
          {TABS.map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={`dw-tab${tab === t ? " on" : ""}`}>
              {t}
              {t === "Findings" && (
                <span style={{ marginLeft: 6, borderRadius: 999, padding: "1px 6px", fontSize: 10, fontWeight: 700, background: C.highBg, color: C.high, fontFamily: "var(--mono)" }}>3</span>
              )}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Card({ eyebrow, title, right, children, style }) {
  return (
    <section className="dw-card" style={{ padding: 20, ...style }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
        <div>
          {eyebrow && <div style={T.eyebrow}>{eyebrow}</div>}
          <h2 style={{ ...T.h2, marginTop: 3 }}>{title}</h2>
        </div>
        {right}
      </div>
      <div style={{ marginTop: 14 }}>{children}</div>
    </section>
  );
}

function DiffBlock({ diff }) {
  return (
    <div style={{ overflow: "hidden", borderRadius: 12, boxShadow: "0 8px 24px rgba(16,24,40,.18)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 14px", background: C.dark2 }}>
        <span style={{ display: "flex", gap: 6 }}>
          {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => <span key={c} style={{ height: 10, width: 10, borderRadius: 999, background: c }} />)}
        </span>
        <span style={{ marginLeft: 4, ...T.mono(11, "#9CA3B2") }}>{diff.file}</span>
      </div>
      <div style={{ background: C.dark, fontFamily: "var(--mono)", fontSize: 12 }}>
        {diff.lines.map((l, i) => (
          <div key={i} style={{
            display: "flex",
            background: l.add ? "rgba(23,178,106,.13)" : l.del ? "rgba(240,68,56,.13)" : "transparent",
            color: l.add ? "#75DFA6" : l.del ? "#FDA29B" : "#7E8696",
          }}>
            <span style={{ width: 40, flexShrink: 0, padding: "4px 8px", textAlign: "right", color: "#4A5160", userSelect: "none" }}>{l.n}</span>
            <span style={{ width: 20, flexShrink: 0, padding: "4px 0", textAlign: "center", userSelect: "none" }}>{l.add ? "+" : l.del ? "−" : ""}</span>
            <pre style={{ margin: 0, padding: "4px 12px 4px 0", overflowX: "auto", fontFamily: "inherit" }}>{l.txt}</pre>
          </div>
        ))}
      </div>
    </div>
  );
}

function FindingCard({ f, open, onToggle }) {
  return (
    <div className="dw-card" style={{ overflow: "hidden", boxShadow: open ? "0 4px 10px rgba(16,24,40,.06),0 12px 28px rgba(16,24,40,.09)" : undefined }}>
      <button onClick={onToggle} aria-expanded={open} style={{ display: "flex", width: "100%", alignItems: "flex-start", gap: 14, padding: "17px 20px", textAlign: "left" }}>
        <span style={{ marginTop: 1, display: "flex", height: 36, width: 36, flexShrink: 0, alignItems: "center", justifyContent: "center", borderRadius: 11, background: SEV[f.sev].bg, color: SEV[f.sev].fg }}>
          <AlertTriangle size={16} />
        </span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontFamily: "var(--display)", fontWeight: 700, fontSize: 14, color: C.ink }}>{f.title}</span>
            <SeverityBadge level={f.sev} />
            {f.crossTool && (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4, borderRadius: 999, padding: "2px 9px", fontSize: 10, fontWeight: 700, background: C.brandSoft, color: C.brandDark }}>
                <Layers size={10} /> Cross-tool
              </span>
            )}
          </div>
          <p style={{ marginTop: 5, fontSize: 13, lineHeight: 1.6, color: C.muted }}>{f.body}</p>
          <div style={{ marginTop: 9, display: "flex", gap: 6, flexWrap: "wrap" }}>
            {f.evidence.map((e) => <EvidenceTag key={e}>{e}</EvidenceTag>)}
          </div>
        </div>
        <ChevronDown size={16} style={{ marginTop: 6, flexShrink: 0, color: C.faint, transform: open ? "rotate(180deg)" : "none", transition: "transform .18s ease" }} />
      </button>
      {open && (
        <div style={{ borderTop: `1px solid ${C.borderSoft}`, background: "#FAFBFC", padding: "16px 20px" }}>
          {f.diff ? <DiffBlock diff={f.diff} /> : (
            <p style={{ fontSize: 13, color: C.muted }}>
              See the <span style={{ fontWeight: 600, color: C.ink }}>Rollback</span> tab for the ordered plan and the stateful validation step.
            </p>
          )}
          <div style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 11.5, color: C.faint }}>Was this finding useful?</span>
            {["Useful", "Noisy", "False positive"].map((a) => <button key={a} className="dw-pill">{a}</button>)}
          </div>
        </div>
      )}
    </div>
  );
}

function OverviewTab({ goFindings }) {
  return (
    <div className="dw-grid-32" style={{ gridTemplateColumns: undefined }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <Card eyebrow="OPERATIONAL NARRATIVE" title="What changed, and why it's risky">
          <div style={{ display: "flex", flexDirection: "column", gap: 12, ...T.body }}>
            <p>
              This PR widens the RDS security group from the VPC CIDR to <MonoRef>0.0.0.0/0</MonoRef> in{" "}
              <MonoRef>rds.tf:18</MonoRef> while scaling <MonoRef>payments-api</MonoRef> from 3 to 10 replicas
              in <MonoRef>deployment.yaml:24</MonoRef>. Individually each change looks routine; together they
              expose Postgres 5432 publicly during the deploy window and push connection demand past the
              unchanged Aurora <MonoRef>max_connections</MonoRef>.
            </p>
            <p>
              The scale-up is 89% similar to <MonoRef>INC-2024-Q3-17</MonoRef> — a pool-exhaustion incident
              this team has already lived through.
            </p>
          </div>
          <div style={{ marginTop: 16, display: "flex", gap: 12, borderRadius: 12, padding: 14, background: C.highBg }}>
            <span style={{ display: "flex", height: 28, width: 28, flexShrink: 0, alignItems: "center", justifyContent: "center", borderRadius: 8, background: "#fff", color: C.high }}>
              <AlertCircle size={14} />
            </span>
            <div>
              <div style={{ fontFamily: "var(--display)", fontWeight: 700, fontSize: 12.5, color: "#93370D" }}>Verify before deploying</div>
              <p style={{ marginTop: 2, fontSize: 12.5, lineHeight: 1.6, color: "#93370D" }}>
                Confirm the ingress widening is intentional and time-boxed, and confirm Aurora connection headroom for 10 replicas.
              </p>
            </div>
          </div>
        </Card>
        <Card eyebrow="TOP FINDINGS" title="3 findings · 2 high, 1 medium"
          right={<button className="dw-link" onClick={goFindings}>All findings <ChevronRight size={13} /></button>}>
          <ul style={{ listStyle: "none" }}>
            {FINDINGS.map((f, i) => (
              <li key={f.title} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderTop: i ? `1px solid ${C.borderSoft}` : "none", fontSize: 13 }}>
                <SeverityBadge level={f.sev} />
                <span style={{ fontWeight: 500, color: C.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.title}</span>
                <span style={{ marginLeft: "auto", flexShrink: 0 }}><EvidenceTag>{f.evidence[0]}</EvidenceTag></span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <Card eyebrow="DECISION INPUTS" title="At a glance">
          <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: 15 }}>
            {[
              [Network, "Blast radius", "8 services", "3 direct · 5 transitive"],
              [History, "Incident match", "89%", "INC-2024-Q3-17"],
              [RotateCcw, "Rollback", "5 steps · ~12 min", "complexity 4/5"],
              [ShieldCheck, "Evidence Law", "Reconciled", "severe claims backed"],
            ].map(([Icon, l, v, s]) => (
              <li key={l} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ display: "flex", height: 36, width: 36, flexShrink: 0, alignItems: "center", justifyContent: "center", borderRadius: 11, background: C.brandSoft, color: C.brand }}>
                  <Icon size={15} />
                </span>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                    <span style={{ fontSize: 11.5, color: C.muted }}>{l}</span>
                    <span style={T.mono(9.5, C.faint)}>{s}</span>
                  </div>
                  <div style={{ fontFamily: "var(--display)", fontWeight: 700, fontSize: 13.5, color: C.ink }}>{v}</div>
                </div>
              </li>
            ))}
          </ul>
        </Card>
        <Card eyebrow="CONTEXT QUALITY" title="Completeness">
          <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
            <span style={{ fontFamily: "var(--display)", fontWeight: 800, fontSize: 23, color: C.ink }}>0.86</span>
            <span style={{ fontSize: 11.5, color: C.faint }}>/ 1.00</span>
          </div>
          <div style={{ marginTop: 9, height: 7, borderRadius: 999, background: "#EEF0F3", overflow: "hidden" }}>
            <div style={{ height: "100%", width: "86%", borderRadius: 999, background: "linear-gradient(90deg,#34D399,#079455)" }} />
          </div>
          <p style={{ marginTop: 10, fontSize: 12, lineHeight: 1.6, color: C.muted }}>
            Topology 2 days fresh · 3/3 parsers succeeded · 1 TODO open: link the Aurora parameter group.
          </p>
        </Card>
      </div>
    </div>
  );
}

function ConfidenceTab() {
  const ledger = (items, hot) => (
    <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: 12 }}>
      {items.map((t, i) => (
        <li key={i} style={{ display: "flex", gap: 10, ...T.body }}>
          <span style={{ marginTop: 2, display: "flex", height: 20, width: 20, flexShrink: 0, alignItems: "center", justifyContent: "center", borderRadius: 999, fontSize: 10, fontWeight: 700, fontFamily: "var(--mono)", background: hot ? C.highBg : "#F0F1F4", color: hot ? C.high : C.muted }}>{i + 1}</span>
          <span>{t}</span>
        </li>
      ))}
    </ul>
  );
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div className="dw-grid-2">
        <Card eyebrow="CONFIDENCE LEDGER" title="Why not lower">
          {ledger([
            <>Deterministic evidence at <MonoRef>rds.tf:18</MonoRef> contributes 31 risk points — the largest single contributor.</>,
            <>Incident similarity of 0.89 is an unbounded escalation signal under the scoring model.</>,
            <>Production environment applies a 2× resource multiplier.</>,
          ], true)}
        </Card>
        <Card eyebrow="CONFIDENCE LEDGER" title="Why not higher">
          {ledger([
            <>Score 78 sits below the critical boundary of 90; no data-loss path was identified.</>,
            <>A tested rollback plan exists — complexity is elevated but bounded.</>,
            <>Evidence Law does not support a stronger claim from the available artifacts.</>,
          ])}
        </Card>
      </div>
      <Card eyebrow="EVIDENCE REGISTER" title="4 deterministic items">
        <div style={{ overflow: "hidden", borderRadius: 12, border: `1px solid ${C.borderSoft}` }}>
          {[
            ["EV-01", "rds.tf:18", "Security-group ingress widened to 0.0.0.0/0", "parser"],
            ["EV-02", "CKV_AWS_24", "Checkov: SG allows public ingress on 5432", "scanner"],
            ["EV-03", "deployment.yaml:24", "Replicas 3 → 10", "parser"],
            ["EV-04", "INC-2024-Q3-17", "Incident-match similarity 0.89", "memory"],
          ].map(([id, ref, desc, src], i) => (
            <div key={id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 16px", fontSize: 13, borderTop: i ? `1px solid ${C.borderSoft}` : "none", background: i % 2 ? "#FAFBFC" : "#fff" }}>
              <span style={T.mono(11, C.faint)}>{id}</span>
              <MonoRef>{ref}</MonoRef>
              <span style={{ minWidth: 0, flex: 1, color: C.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{desc}</span>
              <span style={{ borderRadius: 999, padding: "2px 9px", fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", background: "#F0F1F4", color: C.muted, fontFamily: "var(--mono)" }}>{src}</span>
            </div>
          ))}
        </div>
        <p style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: C.muted }}>
          <ShieldCheck size={13} style={{ color: C.low }} />
          AI explains. Evidence decides — disable the narrative layer and this register still stands.
        </p>
      </Card>
    </div>
  );
}

function ContextTab() {
  const rows = [
    ["Topology freshness", "2 days", "fresh snapshot", true],
    ["Parser success", "3 / 3 files", "terraform · kubernetes", true],
    ["Incident index", "41 incidents", "last import 6d ago", true],
    ["Evidence coverage", "1.00", "all material changes represented", true],
    ["Aurora parameter group", "missing", "link to topology to confirm max_connections", false],
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <Card eyebrow="CONTEXT COMPLETENESS" title="0.86 / 1.00 — strong context">
        <div style={{ overflow: "hidden", borderRadius: 12, border: `1px solid ${C.borderSoft}` }}>
          {rows.map(([l, v, s, ok], i) => (
            <div key={l} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 16px", fontSize: 13, borderTop: i ? `1px solid ${C.borderSoft}` : "none" }}>
              <span style={{ display: "flex", height: 24, width: 24, flexShrink: 0, alignItems: "center", justifyContent: "center", borderRadius: 999, background: ok ? C.lowBg : C.highBg }}>
                {ok ? <CheckCircle2 size={13} style={{ color: C.low }} /> : <AlertCircle size={13} style={{ color: C.high }} />}
              </span>
              <span style={{ width: 185, flexShrink: 0, fontWeight: 500, color: C.ink }}>{l}</span>
              <span style={T.mono(12, ok ? C.text : C.high)}>{v}</span>
              <span style={{ marginLeft: "auto", fontSize: 12, color: C.faint, textAlign: "right" }}>{s}</span>
            </div>
          ))}
        </div>
        <button className="dw-btn dw-btn-ghost" style={{ marginTop: 14, color: C.brand }}>
          <Plus size={13} /> Resolve open context TODO
        </button>
      </Card>
      <Card eyebrow="BLAST RADIUS" title="8 services affected">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {["payments-api", "checkout", "orders", "ledger", "notif-svc", "fraud-check", "billing", "audit-log"].map((s, i) => (
            <span key={s} style={{
              display: "inline-flex", alignItems: "center", gap: 6, borderRadius: 999, padding: "6px 13px",
              fontFamily: "var(--mono)", fontSize: 11.5,
              border: `1px solid ${i < 3 ? "#F9DBCB" : C.border}`,
              background: i < 3 ? C.brandSoft : "#FAFBFC",
              color: i < 3 ? C.brandDark : C.muted,
            }}>
              <span style={{ height: 6, width: 6, borderRadius: 999, background: i < 3 ? C.brand : "#C6CCD6" }} />
              {s}
            </span>
          ))}
        </div>
        <p style={{ marginTop: 12, fontSize: 12, color: C.muted }}>3 directly affected, 5 transitive · graph depth 2 · topology snapshot 2 days old.</p>
      </Card>
    </div>
  );
}

function RollbackTab() {
  const steps = [
    ["Narrow SG ingress back to 10.0.0.0/16", "~2 min", false],
    ["Verify Postgres connectivity from ECS tasks", "~3 min", true],
    ["Scale payments-api 10 → 3 replicas", "~2 min", false],
    ["Drain excess connections; watch pool gauge", "~4 min", true],
    ["Confirm prior stable state in dashboard", "~1 min", false],
  ];
  return (
    <Card eyebrow="ROLLBACK PLAN" title="5 steps · ~12 min · complexity 4/5"
      right={<button className="dw-btn dw-btn-ghost"><Copy size={13} /> Copy full plan</button>}>
      <ol style={{ listStyle: "none" }}>
        {steps.map(([t, d, critical], i) => (
          <li key={t} style={{ position: "relative", display: "flex", gap: 16, paddingBottom: i < steps.length - 1 ? 24 : 0 }}>
            {i < steps.length - 1 && <span style={{ position: "absolute", left: 15, top: 36, bottom: 0, width: 1, background: C.border }} />}
            <span style={{
              zIndex: 1, display: "flex", height: 31, width: 31, flexShrink: 0, alignItems: "center", justifyContent: "center",
              borderRadius: 999, fontSize: 12, fontWeight: 700, fontFamily: "var(--mono)",
              background: critical ? C.grad : "#fff", color: critical ? "#fff" : C.muted,
              border: critical ? "none" : `1.5px solid ${C.border}`,
              boxShadow: critical ? "0 4px 10px rgba(242,85,31,.3)" : "none",
            }}>{i + 1}</span>
            <div style={{ display: "flex", minWidth: 0, flex: 1, alignItems: "baseline", gap: 9, paddingTop: 6, flexWrap: "wrap" }}>
              <span style={{ fontSize: 13.5, fontWeight: 500, color: C.text }}>{t}</span>
              {critical && (
                <span style={{ borderRadius: 999, padding: "1px 9px", fontSize: 9.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", background: C.highBg, color: C.high }}>
                  critical path
                </span>
              )}
              <span style={{ marginLeft: "auto", ...T.mono(11, C.faint) }}>{d}</span>
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}

function AuditTab() {
  const meta = [
    ["Interface", "ui"], ["Trigger", "dashboard_upload"], ["Provider", "groq"],
    ["Model", "llama-3.3-70b-versatile"], ["Risk scoring", "deterministic v2"],
    ["Narrative source", "llm · secondary"], ["Schema", "v2"], ["Files analyzed", "3"],
    ["Skills applied", "terraform · kubernetes"],
  ];
  return (
    <Card eyebrow="AUDIT METADATA" title="How this report was produced">
      <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(180px,1fr))", gap: 12 }}>
        {meta.map(([k, v]) => (
          <div key={k} style={{ borderRadius: 11, border: `1px solid ${C.borderSoft}`, background: "#FAFBFC", padding: 12 }}>
            <dt style={{ fontSize: 9.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: C.faint }}>{k}</dt>
            <dd style={{ marginTop: 4, ...T.mono(12, C.ink) }}>{v}</dd>
          </div>
        ))}
      </dl>
      <p style={{ marginTop: 16, fontSize: 12, color: C.muted }}>
        Advisory only — DeployWhisper produces intelligence, not authorization. The human reviewer decides.
      </p>
    </Card>
  );
}

function Report({ onBack, initialTab = "Overview" }) {
  const [tab, setTab] = useState(initialTab);
  const [open, setOpen] = useState(0);
  return (
    <div>
      <ReportHeader tab={tab} setTab={setTab} onBack={onBack} />
      <div style={{ maxWidth: 1120, margin: "0 auto", padding: "22px 28px" }}>
        {tab === "Overview" && <OverviewTab goFindings={() => setTab("Findings")} />}
        {tab === "Findings" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {FINDINGS.map((f, i) => (
              <FindingCard key={f.title} f={f} open={open === i} onToggle={() => setOpen(open === i ? -1 : i)} />
            ))}
          </div>
        )}
        {tab === "Confidence" && <ConfidenceTab />}
        {tab === "Context" && <ContextTab />}
        {tab === "Rollback" && <RollbackTab />}
        {tab === "Audit" && <AuditTab />}
        <div style={{ height: 90 }} />
      </div>
    </div>
  );
}

/* ──────────────── root ──────────────── */
export default function App({ initialView = "dashboard", initialTab = "Overview", initialSwitcherOpen = false }) {
  const [view, setView] = useState(initialView);
  const [project, setProject] = useState(PROJECTS[0]);
  return (
    <div className="dw-app">
      <style>{CSS}</style>
      <Sidebar view={view} onNav={(id) => setView(id === "history" ? "report" : "dashboard")} project={project} />
      <div className="dw-main">
        <TopBar project={project} setProject={setProject} initialSwitcherOpen={initialSwitcherOpen} />
        <main className="dw-scroll">
          {view === "dashboard" ? <Dashboard openReport={() => setView("report")} project={project} /> : <Report onBack={() => setView("dashboard")} initialTab={initialTab} />}
        </main>
      </div>
    </div>
  );
}
