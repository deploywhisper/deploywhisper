import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { SkillRegistryItem } from "../api/phase6";
import {
  SkillCard,
  SkillDetailContent,
  SkillsListContent,
  skillSourceLabel,
  skillTestStatusLabel,
  skillTrustLabel,
} from "./Skills";

const skill: SkillRegistryItem = {
  id: "terraform",
  name: "Terraform",
  version: "1.0.0",
  trust_level: "core",
  source: "built-in",
  author: "DeployWhisper",
  maintainer: "DeployWhisper",
  is_official: true,
  is_featured: false,
  license: "Apache-2.0",
  description: "Evidence-backed Terraform deployment guidance.",
  tool: "terraform",
  tags: ["iac"],
  token_budget: 1200,
  test_suite_path: "tests/skill-tests/terraform",
  test_results: {
    total_scenarios: 3,
    passed_scenarios: 3,
    failed_scenarios: 0,
    pass_rate: 1,
    status: "passing",
    display_text: "3/3 scenarios passed",
    generated_at: "2026-07-27T00:00:00Z",
  },
  triggers: [".tf"],
  trigger_content_patterns: [],
  contributors: ["DeployWhisper", "Platform Safety"],
  install_count: 12,
  active_issue_count: 0,
  analytics_updated_at: "2026-07-27T00:00:00Z",
  download_count: 12,
  star_count: 4,
  updated_at: "2026-07-27T00:00:00Z",
  available_versions: 1,
  install_command: "deploywhisper skill install terraform",
};

function renderWithQuery(node: React.ReactElement, client: QueryClient) {
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Skills browser labels", () => {
  it("uses explicit trust, source, and deterministic test-status labels", () => {
    expect(skillTrustLabel("core")).toBe("Core trust");
    expect(skillSourceLabel("built-in")).toBe("Public registry");
    expect(skillSourceLabel("custom-override")).toBe("Local override");
    expect(skillSourceLabel("custom-new")).toBe("Private local");
    expect(skillSourceLabel("future-source" as SkillRegistryItem["source"])).toBe("Unknown source");
    expect(skillTestStatusLabel(skill.test_results)).toBe("Tests passing");
    expect(skillTestStatusLabel({ ...skill.test_results!, status: "failing" })).toBe("Tests failing");
    expect(skillTestStatusLabel(null)).toBe("Tests missing");
  });

  it("renders trust, public source, and test status in each catalog result", () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter>
        <SkillCard skill={skill} />
      </MemoryRouter>,
    );

    expect(markup).toContain("Core trust");
    expect(markup).toContain("Public registry");
    expect(markup).toContain("Tests passing");
    expect(markup).toContain("100%");
  });

  it("distinguishes private local skills from public registry skills", () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter>
        <SkillCard
          skill={{
            ...skill,
            id: "organization-guardrails",
            name: "Organization guardrails",
            trust_level: "experimental",
            source: "custom-new",
            is_official: false,
          }}
        />
      </MemoryRouter>,
    );

    expect(markup).toContain("Experimental trust");
    expect(markup).toContain("Private local");
    expect(markup).not.toContain("Public registry");
  });

  it("renders accessible search semantics from preloaded registry data", () => {
    const client = new QueryClient();
    const envelope = {
      data: [skill],
      meta: {
        app: "deploywhisper",
        version: "test",
        count: 1,
        total_count: 1,
        page: 1,
        page_size: 100,
        filters: {},
      },
    };
    client.setQueryData(["skills", "", "", "", "", "popularity"], envelope);
    client.setQueryData(["skills", "all-options"], envelope);

    const markup = renderWithQuery(<SkillsListContent />, client);

    expect(markup).toContain('aria-label="Search skills"');
    expect(markup).toContain("Core trust");
    expect(markup).toContain("Public registry");
  });

  it("renders harness freshness, analytics freshness, and contributors in detail", () => {
    const client = new QueryClient();
    client.setQueryData(["skill", "terraform"], skill);
    client.setQueryData(["skill-versions", "terraform"], []);

    const markup = renderWithQuery(<SkillDetailContent skillId="terraform" />, client);

    expect(markup).toContain("3/3 scenarios passed");
    expect(markup).toContain("Harness run");
    expect(markup).toContain("Analytics refreshed");
    expect(markup).toContain("DeployWhisper");
    expect(markup).toContain("Platform Safety");
  });
});
