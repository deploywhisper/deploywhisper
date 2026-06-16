import { useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, GitBranch, PackageCheck, Search, ShieldCheck } from "lucide-react";

import { getSkill, getSkills, getSkillVersions, type SkillRegistryItem } from "../api/phase6";
import { Button, Card, EvidenceTag, MonoRef, SkeletonCard } from "../components/ui";
import { Phase6Shell } from "./Phase6Shell";
import "./dashboard.css";
import "./phase6.css";

function formatDate(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "2-digit", year: "numeric" }).format(parsed);
}

function passRate(skill: SkillRegistryItem) {
  const summary = skill.test_results;
  if (!summary || summary.status === "missing") {
    return "n/a";
  }
  return `${Math.round(summary.pass_rate * 100)}%`;
}

function unique(values: (string | undefined)[]) {
  return Array.from(new Set(values.filter(Boolean) as string[])).sort();
}

function SkillCard({ skill }: { skill: SkillRegistryItem }) {
  return (
    <Link className="dw-phase6-list-item dw-skill-card" to={`/skills/${skill.id}`}>
      <div className="dw-phase6-row">
        <div className="dw-phase6-list-title">{skill.name}</div>
        {skill.is_official && <EvidenceTag>Official</EvidenceTag>}
        {skill.is_featured && <EvidenceTag>Featured</EvidenceTag>}
      </div>
      <div className="dw-phase6-list-copy">{skill.description}</div>
      <div className="dw-skill-tags">
        <EvidenceTag>{skill.tool}</EvidenceTag>
        {skill.tags?.slice(0, 4).map((tag) => <EvidenceTag key={tag}>{tag}</EvidenceTag>)}
      </div>
      <div className="dw-phase6-stat-grid">
        <div className="dw-phase6-stat"><strong>{skill.install_count}</strong><span>Installs</span></div>
        <div className="dw-phase6-stat"><strong>{passRate(skill)}</strong><span>Pass rate</span></div>
      </div>
      <MonoRef>{skill.author} / {formatDate(skill.updated_at)}</MonoRef>
    </Link>
  );
}

function SkillsListContent() {
  const [searchParams, setSearchParams] = useSearchParams();
  const search = searchParams.get("search") ?? "";
  const tool = searchParams.get("tool") ?? "";
  const tag = searchParams.get("tag") ?? "";
  const author = searchParams.get("author") ?? "";
  const sort = searchParams.get("sort") === "recency" ? "recency" : "popularity";

  const catalogQuery = useQuery({
    queryFn: () => getSkills({ search, tool, tag, author, sort, pageSize: 100 }),
    queryKey: ["skills", search, tool, tag, author, sort],
  });
  const allQuery = useQuery({
    queryFn: () => getSkills({ pageSize: 100 }),
    queryKey: ["skills", "all-options"],
  });
  const optionItems = allQuery.data?.data ?? catalogQuery.data?.data ?? [];
  const tools = useMemo(() => unique(optionItems.map((item) => item.tool)), [optionItems]);
  const authors = useMemo(() => unique(optionItems.map((item) => item.author)), [optionItems]);
  const tags = useMemo(() => unique(optionItems.flatMap((item) => item.tags ?? [])), [optionItems]);

  function updateFilter(key: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    setSearchParams(next);
  }

  const items = catalogQuery.data?.data ?? [];

  return (
    <div className="dw-dashboard-wrap dw-phase6-content">
      <header className="dw-phase6-header">
        <div>
          <p className="eyebrow">Skills Registry</p>
          <h1>Skills</h1>
          <p className="lede">Search skill metadata, triggers, validation readiness, and install commands from the same registry the CLI consumes.</p>
        </div>
        <a href="https://deploywhisper.github.io/skills-registry/" rel="noreferrer" target="_blank">
          <Button variant="ghost">
            <ExternalLink size={14} /> Public registry
          </Button>
        </a>
      </header>
      <Card eyebrow="Catalog" title="Search current registry">
        <div className="dw-phase6-filter-grid">
          <label className="dw-field">
            <span>Search</span>
            <div className="dw-phase6-row">
              <Search size={15} />
              <input className="dw-phase6-search" onChange={(event) => updateFilter("search", event.target.value)} value={search} />
            </div>
          </label>
          <label className="dw-field">
            <span>Tool</span>
            <select onChange={(event) => updateFilter("tool", event.target.value)} value={tool}>
              <option value="">All tools</option>
              {tools.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <label className="dw-field">
            <span>Tag</span>
            <select onChange={(event) => updateFilter("tag", event.target.value)} value={tag}>
              <option value="">All tags</option>
              {tags.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <label className="dw-field">
            <span>Author</span>
            <select onChange={(event) => updateFilter("author", event.target.value)} value={author}>
              <option value="">All authors</option>
              {authors.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <label className="dw-field">
            <span>Sort</span>
            <select onChange={(event) => updateFilter("sort", event.target.value)} value={sort}>
              <option value="popularity">Popularity</option>
              <option value="recency">Recency</option>
            </select>
          </label>
        </div>
        {catalogQuery.isLoading && <SkeletonCard />}
        {catalogQuery.error && <div className="dw-phase6-note dw-phase6-warning">{catalogQuery.error.message}</div>}
        {!catalogQuery.isLoading && items.length === 0 && <div className="dw-phase6-empty">No skills match the current search and filter combination.</div>}
        {items.length > 0 && (
          <>
            <div className="dw-phase6-row" style={{ marginBottom: 12 }}>
              <EvidenceTag>{catalogQuery.data?.meta.total_count ?? items.length} visible skills</EvidenceTag>
              <EvidenceTag>{items.reduce((sum, item) => sum + item.install_count, 0)} installs</EvidenceTag>
              <EvidenceTag>{items.reduce((sum, item) => sum + item.active_issue_count, 0)} open issues</EvidenceTag>
            </div>
            <div className="dw-skill-card-grid">
              {items.map((skill) => <SkillCard key={skill.id} skill={skill} />)}
            </div>
          </>
        )}
      </Card>
    </div>
  );
}

function SkillDetailContent({ skillId }: { skillId: string }) {
  const skillQuery = useQuery({ queryFn: () => getSkill(skillId), queryKey: ["skill", skillId] });
  const versionsQuery = useQuery({ queryFn: () => getSkillVersions(skillId), queryKey: ["skill-versions", skillId] });
  const skill = skillQuery.data;

  return (
    <div className="dw-dashboard-wrap dw-phase6-content">
      <header className="dw-phase6-header">
        <div>
          <p className="eyebrow">Skill Detail</p>
          <h1>{skill?.name ?? "Skill"}</h1>
          <p className="lede">{skill?.description ?? "Loading registry metadata."}</p>
        </div>
        <Link to="/skills">
          <Button variant="ghost">Back to skills</Button>
        </Link>
      </header>
      {skillQuery.isLoading && (
        <div className="dw-phase6-grid">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      )}
      {skillQuery.error && <div className="dw-phase6-note dw-phase6-warning">Skill not found.</div>}
      {skill && (
        <div className="dw-phase6-grid">
          <div className="dw-phase6-stack">
            <Card eyebrow={skill.tool} title={skill.name}>
              <div className="dw-phase6-stack">
                <div className="dw-phase6-row">
                  {skill.is_official && <EvidenceTag>Official</EvidenceTag>}
                  {skill.is_featured && <EvidenceTag>Featured</EvidenceTag>}
                  <EvidenceTag>{skill.source}</EvidenceTag>
                </div>
                <div className="dw-skill-command-box">{skill.install_command}</div>
                <div className="dw-phase6-stat-grid">
                  <div className="dw-phase6-stat"><strong>{skill.author}</strong><span>Author</span></div>
                  <div className="dw-phase6-stat"><strong>{skill.maintainer}</strong><span>Maintainer</span></div>
                  <div className="dw-phase6-stat"><strong>{skill.install_count}</strong><span>Installs</span></div>
                  <div className="dw-phase6-stat"><strong>{passRate(skill)}</strong><span>Pass rate</span></div>
                </div>
                <div className="dw-skill-tags">
                  {skill.tags?.map((tag) => <EvidenceTag key={tag}>{tag}</EvidenceTag>)}
                </div>
              </div>
            </Card>
            <Card eyebrow="Triggers" title="Activation metadata">
              <div className="dw-phase6-stack">
                <div className="dw-phase6-row">
                  {(skill.triggers ?? []).map((trigger) => <MonoRef key={trigger}>{trigger}</MonoRef>)}
                </div>
                {(skill.trigger_content_patterns ?? []).map((pattern) => <MonoRef key={pattern}>{pattern}</MonoRef>)}
                {skill.test_suite_path && <MonoRef>{skill.test_suite_path}</MonoRef>}
              </div>
            </Card>
          </div>
          <aside className="dw-phase6-stack">
            <Card eyebrow="Readiness" title="Registry snapshot">
              <div className="dw-phase6-stack">
                <div className="dw-phase6-row"><PackageCheck size={16} /> <span className="dw-phase6-list-copy">{skill.available_versions} tracked versions</span></div>
                <div className="dw-phase6-row"><ShieldCheck size={16} /> <span className="dw-phase6-list-copy">{skill.active_issue_count} active issues</span></div>
                <div className="dw-phase6-row"><GitBranch size={16} /> <span className="dw-phase6-list-copy">Updated {formatDate(skill.updated_at)}</span></div>
              </div>
            </Card>
            <Card eyebrow="Versions" title="Version history">
              <div className="dw-phase6-list">
                {versionsQuery.isLoading && <SkeletonCard />}
                {(versionsQuery.data ?? []).map((version) => (
                  <div className="dw-phase6-list-item" key={version.version}>
                    <div className="dw-phase6-row">
                      <div className="dw-phase6-list-title">{version.version}</div>
                      <EvidenceTag>{version.is_current ? "Current" : "Archived"}</EvidenceTag>
                    </div>
                    <div className="dw-phase6-list-copy">{version.author} / {formatDate(version.updated_at)}</div>
                  </div>
                ))}
              </div>
            </Card>
          </aside>
        </div>
      )}
    </div>
  );
}

export function SkillsScreen() {
  const { skillId } = useParams();
  return (
    <Phase6Shell active="skills">
      {() => (skillId ? <SkillDetailContent skillId={skillId} /> : <SkillsListContent />)}
    </Phase6Shell>
  );
}
