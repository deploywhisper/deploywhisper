import { Link } from "react-router-dom";
import { LocalAccountSection } from "./LocalAccountSection";
import { Phase6Shell } from "./Phase6Shell";
import "./phase6.css";
import "./account-access.css";

export { AccountSessionFields } from "./AccountSessionFields";
export function AccountAccessContent() {
  return <div className="dw-dashboard-wrap dw-phase6-content dw-account-access">
    <div className="dw-phase6-heading"><div><h1>Account access</h1><p>Use your named local account to access permitted project workflows.</p></div><Link to="/settings">Back to Settings</Link></div>
    <LocalAccountSection />
  </div>;
}

export function AccountAccessScreen() {
  return <Phase6Shell active="settings">{() => <AccountAccessContent />}</Phase6Shell>;
}
