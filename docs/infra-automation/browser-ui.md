# Workflow editor and run history

The React app offers a project and workspace scoped view for uploaded preflight
workflows. Open **Automation** in the sidebar when execution is enabled, or visit
`/infra-automation` directly to read permitted history when it is disabled. The
Dashboard's analysis flow and global search remain available.

## Account and project access

Use **Settings → Named account access** (`/settings/account`) to sign in with a
local account. The operator must first enable a supported identity profile and
create the account with the protected local bootstrap procedure in [Identity](identity.md).
Project membership grants workflow permissions separately from account sign-in;
see [Permissions](permissions.md). An operator configures project automation
enablement through the existing API described in [Workflows](workflows.md). The
current Settings screen does not configure automation policy.

The browser keeps mutation protection in memory. After a full page reload, a
restored session can read authorized history, but saving, publishing, starting or
signing out requires signing in again. Logout, expiry and revocation clear
protected screen data. The account page accepts only screened local return paths;
it never stores passwords, session or bootstrap credentials in browser storage.
Recovery requires an operator with trusted host access. There is no email or SSO
recovery flow.

## Create and run

1. Select an authorized project and workspace. Project-wide authoring is available
   where the current membership permits it. Choose a concrete workspace before a
   run starts.
2. Choose **Create workflow**, name the draft and use the **uploaded artifact
   review** template. The YAML editor accepts the workflow-v2 contract. **Validate**
   shows screened server diagnostics by field, step and location; it does not save.
   Add a reason and **Save draft**. **Publish revision** is a separate authorized
   action. Published revision content and digest do not change when a draft changes.
3. Select a published revision and upload supported UTF-8 infrastructure files.
   The initial preflight supports one artifact set and two steps: uploaded intake
   followed by shared analysis. The aggregate limit is 8 MiB and 32 files;
   [preflight](preflight.md) lists the server's screening and admission rules.
   Enter bounded JSON scalar inputs and a reason, then **Start preflight**. A
   draft or unsupported revision cannot start. The server rechecks all permission,
   policy, revision and artifact rules before admission.
4. Open **Runs** for scoped history. Run detail shows the recorded state, server
   ordered attempts, available timestamps, screened bounded logs, artifact output
   digests, evidence limitations and a permanent briefing link. Step start/finish
   and individual log times are not supplied by the current API and are labeled
   unavailable. Snapshot, input and artifact digests describe distinct facts.

Uploaded evidence has unverified repository provenance and is advisory only. The
run's report relation supplies an optional link back from `/reports/{id}` only
after the exact run, report and project relation is checked. The report remains
schema v2 with its usual verdict, evidence and permanent URL. A successful
analysis does not approve or deploy anything.

## Availability and recovery

Execution off prevents new starts while permitted draft management and history
reads continue. A denied scope shows a generic unavailable state. A stale draft
version reloads server state and requires review and validation before another
consequential action. During connection loss, a nonsecret same-scope YAML edit
remains on screen; changes are disabled until the account and scope are verified.
If a mutation response is uncertain, check durable workflow or run history before
making another request. No browser action automatically retries a mutation.

Approval inboxes, runner enrollment, collection and external handoff controls
belong to later stories. The supported UI here makes no apply or deployment claim.

[Implementation proof and screenshots](../verification/infra-automation/16-7/results.md)
record the composed browser journeys at 1440px and 760px.
