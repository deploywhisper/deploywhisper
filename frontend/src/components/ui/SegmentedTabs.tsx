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
}: {
  tabs: SegmentedTab[];
  activeId: string;
  onChange?: (id: string) => void;
  label?: string;
}) {
  return (
    <div aria-label={label} className="dw-tabs" role="tablist">
      {tabs.map((tab) => {
        const active = tab.id === activeId;
        return (
          <button
            key={tab.id}
            aria-selected={active}
            className={`dw-tab${active ? " dw-tab-active" : ""}`}
            onClick={() => onChange?.(tab.id)}
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
