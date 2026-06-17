import logoUrl from "../assets/deploywhisper-logo.png";

export function AppBrand() {
  return (
    <div className="dw-brand">
      <img className="dw-brand-logo" src={logoUrl} alt="DeployWhisper" />
    </div>
  );
}
