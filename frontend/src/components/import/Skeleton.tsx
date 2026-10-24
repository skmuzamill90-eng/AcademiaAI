/** Placeholder blocks shown while data loads. Purely visual; announced once via the parent's aria-busy. */
export function Skeleton({ height = 16, width = '100%' }: { height?: number; width?: number | string }) {
  return <span className="skeleton" style={{ height, width }} aria-hidden="true" />
}

export function PanelSkeleton({ rows = 5, label }: { rows?: number; label: string }) {
  return (
    <div className="skeleton-stack" role="status" aria-busy="true" aria-label={label}>
      <Skeleton height={20} width="40%" />
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} height={36} />)}
    </div>
  )
}
