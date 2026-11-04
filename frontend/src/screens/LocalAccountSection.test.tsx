import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { IdentityConfiguration } from "../api/identity";
import { DashboardScreen } from "./Dashboard";
import { HistoryScreen } from "./History";
import { Phase6Shell } from "./Phase6Shell";
import { SettingsScreen } from "./Settings";
import { LocalAccountConfiguration } from "./LocalAccountSection";

const disabled: IdentityConfiguration = { version: 1, profile: "disabled", configured_origin: null, configuration_valid: true, login_available: false, authorization_profile: "legacy-evaluation", decision_mode: "shared" };
function render(node: React.ReactNode, client = new QueryClient()) {
  return renderToStaticMarkup(<QueryClientProvider client={client}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>);
}
describe("local account settings", () => {
  it("renders before project settings data exists and without any permitted project", () => {
    const client = new QueryClient();
    client.setQueryData(["projects", 0], []);
    client.setQueryData(["identity-configuration", 0], disabled);
    const html = render(<SettingsScreen />, client);
    expect(html).toContain('Local account</h2>');
    expect(html).toContain("Local account sign-in is disabled in this deployment.");
    expect(html).toContain('autoComplete="current-password"');
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Sign in<\/button>/);
    expect(html).not.toContain("Save AI settings");
  });
  it("shows current safe configuration and protected operator setup with no activation action", () => {
    const html = render(<LocalAccountConfiguration configuration={disabled} />);
    expect(html).toContain("Identity profile");
    expect(html).toContain("Not configured");
    expect(html).toContain("Operator setup for local accounts");
    expect(html).toContain("Copy Compose configuration");
    expect(html).toContain("DEPLOYWHISPER_IDENTITY_PROFILE: local-development");
    expect(html).not.toContain("DEPLOYWHISPER_AUTHORIZATION_PROFILE:");
    expect(html).toContain("Keep your current project authorization profile until the required project memberships are configured.");
    expect(html).toContain("python -m cli.identity bootstrap");
    expect(html).toContain("do not grant project membership or enable InfraFlow execution");
    expect(html).not.toContain("/auth/bootstrap");
  });
  it("uses fixed unavailable copy without inferring configuration", () => {
    const html = render(<LocalAccountConfiguration />);
    expect(html).toContain("Local account configuration is unavailable or invalid");
    expect(html).toContain("unavailable");
  });
  it.each([<DashboardScreen />, <HistoryScreen />, <Phase6Shell active="settings">{() => <p>Settings</p>}</Phase6Shell>])("places InfraFlow immediately before Settings after History", (screen) => {
    const html = render(screen);
    const nav = html.match(/<nav[^>]*aria-label="Primary"[\s\S]*?<\/nav>/)![0];
    expect(nav.indexOf('href="/history"')).toBeLessThan(nav.indexOf('href="/infra-automation'));
    expect(nav.indexOf('href="/infra-automation')).toBeLessThan(nav.indexOf('href="/settings"'));
    expect(nav).toMatch(/InfraFlow<\/span><\/a><a[^>]*href="\/settings"/);
  });
});
