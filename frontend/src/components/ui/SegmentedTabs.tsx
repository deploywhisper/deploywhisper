export type SegmentedTab = {
  id: string;
  label: string;
  count?: number;
};

export function SegmentedTabs({
  tabs,
  activeId,
  onChange,
  label = "Sections",
  idPrefix,
}: {
  tabs: SegmentedTab[];
  activeId: string;
  onChange?: (id: string) => void;
  label?: string;
  idPrefix?: string;
}) {
  return (
    <div aria-label={label} className="dw-tabs" role="tablist">
      {tabs.map((tab) => {
        const active = tab.id === activeId;
        return (
          <button
            key={tab.id}
            aria-selected={active}
            aria-controls={idPrefix ? `${idPrefix}-panel-${tab.id}` : undefined}
            id={idPrefix ? `${idPrefix}-tab-${tab.id}` : undefined}
            tabIndex={idPrefix ? (active ? 0 : -1) : undefined}
            className={`dw-tab${active ? " dw-tab-active" : ""}`}
            onClick={() => onChange?.(tab.id)}
            onKeyDown={idPrefix ? (event) => {
              const current = tabs.findIndex((item) => item.id === tab.id);
              const next = event.key === "ArrowRight" ? (current + 1) % tabs.length : event.key === "ArrowLeft" ? (current + tabs.length - 1) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : -1;
              if (next < 0) return;
              event.preventDefault(); onChange?.(tabs[next].id);
              const button = event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next];
              button?.focus();
            } : undefined}
            role="tab"
            type="button"
          >
            {tab.label}
            {typeof tab.count === "number" && <span className="dw-tab-count">{tab.count}</span>}
          </button>
        );
      })}
    </div>
  );
}
