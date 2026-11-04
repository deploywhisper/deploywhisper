import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "../components/ui";
import { useIdentity } from "./IdentitySession";

export function AccountSessionFields({ returnTo, loginAvailable = true }: { returnTo: string; loginAvailable?: boolean }) {
  const identity = useIdentity();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const errorSummary = useRef<HTMLParagraphElement>(null);
  useEffect(() => { setPassword(""); }, [identity.epoch]);
  useEffect(() => {
    // Only a local submit failure moves focus; background session checks do not.
    if (message) errorSummary.current?.focus();
  }, [message]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!loginAvailable || identity.loading || submitting) return;
    setMessage(null);
    setSubmitting(true);
    const submittedPassword = password;
    setPassword("");
    try { await identity.signIn(username, submittedPassword); navigate(returnTo, { replace: true }); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Sign-in failed. Try again."); }
    finally { setPassword(""); setSubmitting(false); }
  }
  async function signOut() {
    setMessage(null);
    try { await identity.signOut(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Sign-out was not confirmed."); }
  }
  return <div className="dw-phase6-form">
        {identity.loading && <p role="status">Checking account access…</p>}
        {(message || identity.error) && <p className="dw-phase6-note dw-phase6-warning" ref={errorSummary} tabIndex={-1} role="alert">{message || identity.error}</p>}
        {identity.principal && <div>
          <p>{identity.status === "unavailable" ? "Last verified account: " : "Signed in as "}<strong>{identity.principal.username}</strong>.</p>
          <p>Project permissions are checked separately for every operation.</p>
          {identity.status === "unavailable" ? <div>
            <p className="dw-phase6-note dw-phase6-warning">Current access is unverified. Verify access again or sign in before making changes or signing out.</p>
            <Button disabled={identity.loading || submitting} onClick={() => { void identity.refresh(); }}>Verify access again</Button>
          </div> : identity.csrfToken ? <Button disabled={identity.loading || submitting} onClick={() => { void signOut(); }}>Sign out</Button>
            : <p className="dw-phase6-note dw-phase6-warning">Your session was restored for reading. Sign in again to save changes, publish, start a preflight or sign out.</p>}
          <p><Link to={returnTo}>Continue to permitted workspace</Link></p>
        </div>}
        {(!identity.principal || !identity.csrfToken || identity.status === "unavailable") && <form className="dw-phase6-form" onSubmit={(event) => { void submit(event); }}>
          <label className="dw-field" htmlFor="account-username"><span>Username</span><input autoCapitalize="none" autoComplete="username" disabled={!loginAvailable || identity.loading || submitting} id="account-username" maxLength={128} onChange={(event) => setUsername(event.target.value)} required value={username} /></label>
          <label className="dw-field" htmlFor="account-password"><span>Password</span><input autoComplete="current-password" disabled={!loginAvailable || identity.loading || submitting} id="account-password" maxLength={1024} onChange={(event) => setPassword(event.target.value)} required type="password" value={password} /></label>
          <div><Button disabled={!loginAvailable || identity.loading || submitting} type="submit" variant="primary-gradient">{submitting ? "Signing in…" : "Sign in"}</Button></div>
        </form>}
      </div>;
}
