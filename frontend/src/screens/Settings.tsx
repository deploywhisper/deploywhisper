import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, FileJson, Upload, Zap } from "lucide-react";

import {
  previewTopology,
  saveDriftCadence,
  saveProviderSettings,
  saveTopology,
  uploadCustomSkill,
  getSettingsSummary,
  type ProviderSettingsRequest,
  type SettingsSummary,
  type TopologyValidation,
} from "../api/phase6";
import { Button, Card, EvidenceTag, MonoRef, SkeletonCard, SkeletonLine } from "../components/ui";
import { Phase6Shell } from "./Phase6Shell";
import "./dashboard.css";
import "./phase6.css";

type ProviderForm = ProviderSettingsRequest;

function defaultProviderForm(summary?: SettingsSummary): ProviderForm {
  return {
    provider: summary?.provider.provider ?? "ollama",
    model: summary?.provider.model ?? "",
    api_base: summary?.provider.api_base ?? "",
    request_timeout_seconds: summary?.provider.request_timeout_seconds ?? 30,
    api_key: "",
    local_mode: summary?.provider.local_mode ?? false,
  };
}

function StatusNote({ message, tone = "info" }: { message?: string | null; tone?: "info" | "warning" }) {
  if (!message) {
    return null;
  }
  return <div className={`dw-phase6-note${tone === "warning" ? " dw-phase6-warning" : ""}`}>{message}</div>;
}

function ProviderSettingsCard({ projectId, summary }: { projectId?: number; summary: SettingsSummary }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ProviderForm>(() => defaultProviderForm(summary));
  const [showKey, setShowKey] = useState(false);
  const selectedOption = summary.provider_options.find((option) => option.provider === form.provider);

  useEffect(() => {
    setForm(defaultProviderForm(summary));
  }, [summary]);

  const saveMutation = useMutation({
    mutationFn: saveProviderSettings,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["settings-summary", projectId] });
    },
  });

  function updateProvider(provider: string) {
    const option = summary.provider_options.find((item) => item.provider === provider);
    setForm({
      provider,
      model: option?.model ?? "",
      api_base: option?.api_base ?? "",
      request_timeout_seconds: form.request_timeout_seconds,
      api_key: "",
      local_mode: provider === "ollama" ? Boolean(option?.local_mode) : false,
    });
  }

  return (
    <Card eyebrow="Provider" title="AI provider">
      <div className="dw-phase6-form">
        <StatusNote message="API keys remain environment-backed. Entering a key here validates the active provider for this session but does not persist raw secrets." />
        <label className="dw-field">
          <span>Active provider</span>
          <select onChange={(event) => updateProvider(event.target.value)} value={form.provider}>
            {summary.provider_options.map((option) => (
              <option key={option.provider} value={option.provider}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="dw-field">
          <span>Model</span>
          <input onChange={(event) => setForm({ ...form, model: event.target.value })} value={form.model} />
        </label>
        <label className="dw-field">
          <span>API base</span>
          <input onChange={(event) => setForm({ ...form, api_base: event.target.value })} value={form.api_base} />
        </label>
        <label className="dw-field">
          <span>Request timeout</span>
          <input
            min={1}
            max={600}
            onChange={(event) => setForm({ ...form, request_timeout_seconds: Number(event.target.value) })}
            type="number"
            value={form.request_timeout_seconds ?? 30}
          />
        </label>
        <label className="dw-field">
          <span>API key</span>
          <div className="dw-phase6-row">
            <input
              onChange={(event) => setForm({ ...form, api_key: event.target.value })}
              placeholder={summary.provider.api_key_present ? summary.provider.api_key_preview ?? "Configured in environment" : "No key in environment"}
              type={showKey ? "text" : "password"}
              value={form.api_key ?? ""}
            />
            <Button aria-label="Reveal API key field" onClick={() => setShowKey((value) => !value)} variant="ghost">
              {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
            </Button>
          </div>
        </label>
        <label className="dw-toggle">
          <input
            checked={Boolean(form.local_mode)}
            disabled={!selectedOption?.capabilities.supports_local_only_mode}
            onChange={(event) => setForm({ ...form, local_mode: event.target.checked })}
            type="checkbox"
          />
          <span>Local-only mode</span>
        </label>
        <div className="dw-phase6-actions">
          <Button disabled={saveMutation.isPending} onClick={() => saveMutation.mutate(form)} variant="primary-gradient">
            <Zap size={14} /> Save AI settings
          </Button>
          <EvidenceTag>{summary.provider.source}</EvidenceTag>
        </div>
        <StatusNote
          message={
            saveMutation.data
              ? saveMutation.data.validation.valid
                ? `AI provider settings saved. Timeout is ${saveMutation.data.settings.request_timeout_seconds}s.`
                : saveMutation.data.validation.message
              : saveMutation.error?.message
          }
          tone={saveMutation.data && !saveMutation.data.validation.valid ? "warning" : "info"}
        />
      </div>
    </Card>
  );
}

function TopologyCard({ projectId, summary }: { projectId?: number; summary: SettingsSummary }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const [staged, setStaged] = useState<{ filename: string; topology: Record<string, unknown> } | null>(null);
  const [preview, setPreview] = useState<TopologyValidation | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);

  const previewMutation = useMutation({
    mutationFn: previewTopology,
    onSuccess: setPreview,
  });
  const saveMutation = useMutation({
    mutationFn: saveTopology,
    onSuccess: (payload) => {
      setPreview(payload);
      setStaged(null);
      void queryClient.invalidateQueries({ queryKey: ["settings-summary", projectId] });
    },
  });
  const cadenceMutation = useMutation({
    mutationFn: saveDriftCadence,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["settings-summary", projectId] }),
  });

  async function handleFile(file?: File) {
    if (!file) {
      return;
    }
    setParseError(null);
    try {
      const parsed = JSON.parse(await file.text()) as Record<string, unknown>;
      setStaged({ filename: file.name, topology: parsed });
      previewMutation.mutate({ project_id: projectId, topology: parsed });
    } catch (error) {
      setPreview(null);
      setStaged(null);
      setParseError(error instanceof Error ? error.message : "Unable to parse topology JSON.");
    }
  }

  const topology = preview?.topology ?? summary.topology;
  const drift = summary.topology.drift;
  const driftOptions = summary.drift_cadence.options ?? [];
  const previewServices = topology.preview_services ?? [];
  const addedResources = drift?.added_resources ?? [];
  const removedResources = drift?.removed_resources ?? [];
  const modifiedResources = drift?.modified_resources ?? [];

  return (
    <Card eyebrow="Topology" title="Service context">
      <div className="dw-phase6-stack">
        <label className="dw-phase6-dropzone">
          <input
            ref={inputRef}
            accept=".json,application/json"
            className="dw-phase6-file-input"
            onChange={(event) => void handleFile(event.target.files?.[0])}
            type="file"
          />
          <FileJson size={24} />
          <strong>{staged?.filename ?? "Choose topology JSON"}</strong>
          <span>Validation runs before the topology is saved to the active project.</span>
        </label>
        <div className="dw-phase6-actions">
          <Button disabled={!staged || previewMutation.isPending} onClick={() => inputRef.current?.click()} variant="ghost">
            <Upload size={14} /> Browse
          </Button>
          <Button
            disabled={!staged || saveMutation.isPending || Boolean(preview?.error_message)}
            onClick={() => staged && saveMutation.mutate({ project_id: projectId, topology: staged.topology })}
            variant="primary-gradient"
          >
            Save topology
          </Button>
          <label className="dw-field" style={{ minWidth: 190 }}>
            <span>Drift cadence</span>
            <select
              onChange={(event) => cadenceMutation.mutate(Number(event.target.value))}
              value={summary.drift_cadence.interval_hours}
            >
              {driftOptions.map((hours) => (
                <option key={hours} value={hours}>
                  {hours === 168 ? "Weekly" : `${hours} hours`}
                </option>
              ))}
            </select>
          </label>
        </div>
        <StatusNote message={parseError ?? preview?.error_message ?? preview?.success_message ?? saveMutation.data?.success_message} tone={parseError || preview?.error_message ? "warning" : "info"} />
        <StatusNote
          message={
            cadenceMutation.data
              ? `Drift cadence saved: every ${cadenceMutation.data.interval_hours === 168 ? "week" : `${cadenceMutation.data.interval_hours} hours`}.`
              : cadenceMutation.error?.message
          }
          tone={cadenceMutation.error ? "warning" : "info"}
        />
        <div className="dw-phase6-stat-grid">
          <div className="dw-phase6-stat"><strong>{topology.service_count}</strong><span>Services</span></div>
          <div className="dw-phase6-stat"><strong>{topology.dependency_count}</strong><span>Dependencies</span></div>
          <div className="dw-phase6-stat"><strong>{topology.resource_key_count}</strong><span>Resources</span></div>
          <div className="dw-phase6-stat"><strong>{drift?.status?.replaceAll("_", " ") ?? "not run"}</strong><span>Drift</span></div>
        </div>
        <div className="dw-phase6-list-copy">
          Active file: <MonoRef>{topology.path}</MonoRef>
          {topology.updated_at ? <> Last updated: {topology.updated_at}.</> : <> No active topology timestamp.</>}
        </div>
        {previewServices.length > 0 && <div className="dw-phase6-list-copy">Preview: {previewServices.join(", ")}</div>}
        {drift && (
          <div className="dw-phase6-list-copy">
            Changed resources: +{addedResources.length} / -{removedResources.length} / ~{modifiedResources.length}
          </div>
        )}
      </div>
    </Card>
  );
}

function FeedbackCard({ summary }: { summary: SettingsSummary }) {
  const state = summary.feedback.current_state;
  const recentNotes = summary.feedback.recent_notes ?? [];
  const metrics = [
    ["Useful", state.useful_count],
    ["Noisy", state.noisy_count],
    ["False positives", state.false_positive_count],
    ["Missed findings", state.missed_finding_count],
  ];
  return (
    <Card eyebrow="Feedback" title="Reviewer feedback">
      <div className="dw-phase6-stack">
        <div className="dw-phase6-stat-grid">
          {metrics.map(([label, value]) => (
            <div className="dw-phase6-stat" key={label}>
              <strong>{value}</strong>
              <span>{label}</span>
            </div>
          ))}
        </div>
        <div className="dw-phase6-list-copy">Recorded feedback events: {summary.feedback.totals.events_recorded}</div>
        <div className="dw-phase6-list">
          {recentNotes.length === 0 ? (
            <div className="dw-phase6-empty">No reviewer notes have been captured for this project yet.</div>
          ) : (
            recentNotes.map((note) => (
              <div className="dw-phase6-list-item" key={`${note.created_at}-${note.text}`}>
                <div className="dw-phase6-list-title">{note.type.replaceAll("_", " ")}</div>
                <div className="dw-phase6-list-copy">{note.text}</div>
              </div>
            ))
          )}
        </div>
      </div>
    </Card>
  );
}

function CustomSkillsCard({ projectId, summary }: { projectId?: number; summary: SettingsSummary }) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const uploadMutation = useMutation({
    mutationFn: async (file: File) => uploadCustomSkill(file.name, await file.text()),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["settings-summary", projectId] }),
  });
  const statuses = uploadMutation.data?.statuses ?? summary.custom_skills ?? [];

  return (
    <Card eyebrow="Skills" title="Custom AI skills">
      <div className="dw-phase6-stack">
        <StatusNote message="Markdown files under skills/custom override built-ins or add team-specific guidance." />
        <input
          ref={inputRef}
          accept=".md,text/markdown"
          className="dw-phase6-file-input"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) {
              uploadMutation.mutate(file);
            }
          }}
          type="file"
        />
        <div className="dw-phase6-actions">
          <Button onClick={() => inputRef.current?.click()} variant="primary-gradient">
            <Upload size={14} /> Upload markdown
          </Button>
        </div>
        <StatusNote message={uploadMutation.data?.success_message ?? uploadMutation.data?.error_message ?? uploadMutation.error?.message} tone={uploadMutation.data?.error_message ? "warning" : "info"} />
        <div className="dw-phase6-list">
          {statuses.length === 0 ? (
            <div className="dw-phase6-empty">No custom skills detected.</div>
          ) : (
            statuses.map((status) => (
              <div className="dw-phase6-list-item" key={status.path}>
                <div className="dw-phase6-row">
                  <div className="dw-phase6-list-title">{status.name}</div>
                  <EvidenceTag>{status.mode}</EvidenceTag>
                  <EvidenceTag>{status.active ? "active" : "ignored"}</EvidenceTag>
                </div>
                <MonoRef>{status.path}</MonoRef>
                {status.warning && <StatusNote message={status.warning} tone="warning" />}
              </div>
            ))
          )}
        </div>
      </div>
    </Card>
  );
}

export function SettingsScreen() {
  return (
    <Phase6Shell active="settings">
      {({ selectedProject, selectedOption }) => {
        const settingsQuery = useQuery({
          enabled: Boolean(selectedProject),
          queryFn: () => getSettingsSummary(selectedProject?.id),
          queryKey: ["settings-summary", selectedProject?.id],
        });

        return (
          <div className="dw-dashboard-wrap dw-phase6-content">
            <header className="dw-phase6-header">
              <div>
                <p className="eyebrow">Workspace Settings</p>
                <h1>Settings</h1>
                <p className="lede">Provider, topology, reviewer feedback, and custom skill controls for {selectedOption?.name ?? "the active project"}.</p>
              </div>
              <EvidenceTag>Evidence Law enforced</EvidenceTag>
            </header>
            {settingsQuery.isLoading && (
              <div className="dw-phase6-grid">
                <SkeletonCard />
                <SkeletonCard />
              </div>
            )}
            {settingsQuery.error && <StatusNote message={settingsQuery.error.message} tone="warning" />}
            {settingsQuery.data && (
              <div className="dw-phase6-grid">
                <div className="dw-phase6-stack">
                  <ProviderSettingsCard projectId={selectedProject?.id} summary={settingsQuery.data} />
                  <TopologyCard projectId={selectedProject?.id} summary={settingsQuery.data} />
                </div>
                <aside className="dw-phase6-stack">
                  <FeedbackCard summary={settingsQuery.data} />
                  <CustomSkillsCard projectId={selectedProject?.id} summary={settingsQuery.data} />
                </aside>
              </div>
            )}
            {!settingsQuery.isLoading && !selectedProject && <SkeletonLine width="60%" />}
          </div>
        );
      }}
    </Phase6Shell>
  );
}
