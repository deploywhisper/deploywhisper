export function SkeletonLine({ width = "100%" }: { width?: number | string }) {
  return <div aria-hidden="true" className="dw-skeleton dw-skeleton-line" style={{ width }} />;
}

export function SkeletonCard() {
  return (
    <div aria-label="Loading card" className="dw-skeleton-card" role="status">
      <div className="dw-skeleton-row">
        <div className="dw-skeleton" style={{ height: 32, width: 32 }} />
        <div style={{ flex: 1 }}>
          <SkeletonLine width="42%" />
          <div style={{ height: 10 }} />
          <SkeletonLine width="78%" />
        </div>
      </div>
      <div style={{ height: 18 }} />
      <SkeletonLine width="94%" />
      <div style={{ height: 10 }} />
      <SkeletonLine width="64%" />
    </div>
  );
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div aria-label="Loading table" className="dw-skeleton-table" role="status">
      <div className="dw-skeleton-table-header">
        {Array.from({ length: 5 }, (_, index) => (
          <SkeletonLine key={index} />
        ))}
      </div>
      {Array.from({ length: rows }, (_, row) => (
        <div className="dw-skeleton-table-row" key={row}>
          {Array.from({ length: 5 }, (_, index) => (
            <SkeletonLine key={index} width={index === 0 ? "86%" : "62%"} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonReportHeader() {
  return (
    <div aria-label="Loading report header" className="dw-skeleton-report-header" role="status">
      <div className="dw-skeleton-report-main">
        <div className="dw-skeleton" style={{ height: 36, width: 36 }} />
        <div className="dw-skeleton" style={{ borderRadius: 999, height: 62, width: 62 }} />
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", gap: 8 }}>
            <SkeletonLine width={82} />
            <SkeletonLine width={64} />
            <SkeletonLine width={118} />
          </div>
          <div style={{ height: 10 }} />
          <SkeletonLine width="60%" />
          <div style={{ height: 8 }} />
          <SkeletonLine width="44%" />
        </div>
      </div>
    </div>
  );
}
