import type { RunOrigin } from "../api/infraAutomation";

const channelLabels: Record<RunOrigin["kind"], string> = {
  manual: "Manual", cli: "CLI channel", webhook: "Signed webhook", pull_request: "Signed PR request",
};
const principalLabels: Record<RunOrigin["principal_type"], string> = {
  human: "Human", service: "Service", agent: "Agent",
};

export function RunOriginSummary({ origin }: { origin: RunOrigin | null | undefined }) {
  if (!origin) return <span className="dw-muted">Not recorded</span>;
  return <span title={`Authenticated principal ID: ${origin.principal_id}`}>{channelLabels[origin.kind]} · {principalLabels[origin.principal_type]}</span>;
}

export function RunOriginDetails({ origin }: { origin: RunOrigin | null | undefined }) {
  return <section aria-label="Request origin">
    <h3>Request origin</h3>
    {!origin ? <p className="dw-muted">Request origin was not recorded for this run.</p> : <>
      <dl className="dw-automation-facts">
        <dt>Channel</dt><dd>{channelLabels[origin.kind]}</dd>
        <dt>Authenticated principal type</dt><dd>{principalLabels[origin.principal_type]}</dd>
        <dt>Authenticated principal ID</dt><dd><code>{origin.principal_id}</code></dd>
        {origin.key_id && <><dt>Signing key ID</dt><dd><code>{origin.key_id}</code></dd></>}
        {origin.pr_ref && <><dt>Declared PR reference</dt><dd><code>{origin.pr_ref}</code></dd></>}
      </dl>
      <p className="dw-muted">This records the request channel and authenticated principal. It does not establish collected provenance or approval; later decisions retain their own attribution.</p>
      {origin.kind === "cli" && <p className="dw-muted">The CLI channel identifies the API entrypoint, not a particular executable.</p>}
      {origin.sources.length ? <div className="dw-automation-table-wrap" role="region" aria-label="Requested source pins" tabIndex={0}>
        <table><caption>Requested source pins</caption><thead><tr><th scope="col">Step</th><th scope="col">Source kind</th><th scope="col">Repository</th><th scope="col">Immutable commit</th><th scope="col">Profile digest</th></tr></thead>
          <tbody>{origin.sources.map((source) => <tr key={source.step_id}>
            <th scope="row">{source.step_id}</th><td>{source.kind === "uploaded" ? "Uploaded evidence" : "Requested collection"}</td>
            <td>{source.kind === "collected" ? source.repository_id : "Unavailable"}</td>
            <td>{source.kind === "collected" ? <code className="dw-automation-output">{source.commit_sha}</code> : "Unavailable"}</td>
            <td>{source.kind === "collected" ? <code className="dw-automation-output">{source.profile_digest}</code> : "Unavailable"}</td>
          </tr>)}</tbody>
        </table>
      </div> : <p className="dw-muted">No source pins were recorded.</p>}
    </>}
  </section>;
}
