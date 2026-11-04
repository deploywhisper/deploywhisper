import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { getIdentityConfiguration, localAccountReturnTo, type IdentityConfiguration } from "../api/identity";
import { Button, Card } from "../components/ui";
import { AccountSessionFields } from "./AccountSessionFields";
import { useIdentity } from "./IdentitySession";
import "./account-access.css";

export const localAccountCompose = `# Localhost operator opt-in; save as compose.identity.yml.
services:
  deploywhisper:
    environment:
      DEPLOYWHISPER_IDENTITY_PROFILE: local-development
      DEPLOYWHISPER_IDENTITY_ORIGIN: http://localhost:8080
# Apply deliberately on the trusted host:
# docker compose -f docker-compose.yml -f compose.identity.yml up -d --build --force-recreate`;

const setupCommands = `docker compose exec deploywhisper sh -c 'umask 077; mkdir -p /tmp/dw-identity; chmod 700 /tmp/dw-identity; python -m cli.identity setup --output /tmp/dw-identity/setup'
docker compose exec deploywhisper python -m cli.identity bootstrap --username operator --credential-file /tmp/dw-identity/setup`;

export function LocalAccountConfiguration({ configuration, loading = false }: { configuration?: IdentityConfiguration; loading?: boolean }) {
  const [copyMessage, setCopyMessage] = useState("");
  const loginAvailable = Boolean(configuration?.configuration_valid && configuration.login_available && ["local-development", "https"].includes(configuration.profile));
  async function copy() {
    try { await navigator.clipboard.writeText(localAccountCompose); setCopyMessage("Compose configuration copied."); }
    catch { setCopyMessage("Copy is unavailable. Select and copy the configuration below."); }
  }
  return <div className="dw-phase6-stack">
    {loading ? <p role="status">Checking local account configuration…</p> : <>
      <dl className="dw-account-configuration">
        <div><dt>Identity profile</dt><dd>{configuration?.profile ?? "unavailable"}</dd></div>
        <div><dt>Configured origin</dt><dd>{configuration?.configured_origin ?? "Not configured"}</dd></div>
        <div><dt>Project authorization</dt><dd>{configuration?.authorization_profile ?? "unavailable"}</dd></div>
        <div><dt>Decision mode</dt><dd>{configuration?.decision_mode ?? "unavailable"}</dd></div>
      </dl>
      <p className="dw-phase6-note">{loginAvailable ? "Named account sign-in is configured. Sign in below with an account created by your application operator." : configuration?.profile === "disabled" ? "Local account sign-in is disabled in this deployment. An application operator must configure identity and create the first account on the trusted host." : configuration?.configuration_valid ? "Sign-in is unavailable from this browser origin. Open the configured origin or ask your application operator to check transport settings." : "Local account configuration is unavailable or invalid. Ask your application operator to check the deployment before signing in."}</p>
    </>}
    <details className="dw-account-setup">
      <summary>Operator setup for local accounts</summary>
      <p>These are deliberate changes on the trusted application host. The localhost profile is for local development; production requires the supported HTTPS profile and an exact trusted origin.</p>
      <p>Keep your current project authorization profile until the required project memberships are configured.</p>
      <Button onClick={() => { void copy(); }}>Copy Compose configuration</Button>
      {copyMessage && <p role="status">{copyMessage}</p>}
      <pre><code>{localAccountCompose}</code></pre>
      <p>After configuring the deployment, an operator creates the first administrator with the existing protected host CLI. The second command prompts securely for a password; keep credentials out of commands, environment variables and this page.</p>
      <pre><code>{setupCommands}</code></pre>
      <p>Setup evidence expires after five minutes. The setup command rejects existing accounts; use the protected host recovery procedure for an existing installation. Keep credential files in operator custody and remove consumed files under your retention policy.</p>
      <p>Sign-in and account creation do not grant project membership or enable InfraFlow execution. A project administrator must grant the required project access separately.</p>
    </details>
  </div>;
}

export function LocalAccountSection() {
  const { epoch } = useIdentity();
  const [params] = useSearchParams();
  const configuration = useQuery({ queryKey: ["identity-configuration", epoch], queryFn: ({ signal }) => getIdentityConfiguration(signal), retry: false });
  const data = configuration.data;
  const loginAvailable = Boolean(!configuration.isError && data?.configuration_valid && data.login_available && ["local-development", "https"].includes(data.profile));
  const returnTo = localAccountReturnTo(params.get("returnTo"));
  return <div className="dw-account-access dw-settings-account">
    <Card eyebrow="Account access" title="Local account">
      <div className="dw-phase6-stack">
        <LocalAccountConfiguration configuration={configuration.isError ? undefined : data} loading={configuration.isPending} />
        <AccountSessionFields returnTo={returnTo} loginAvailable={loginAvailable} />
      </div>
    </Card>
  </div>;
}
