export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`brand-lockup ${compact ? "brand-lockup--compact" : ""}`} aria-label="Aegis">
      <svg className="brand-mark" viewBox="0 0 64 64" role="img" aria-hidden="true">
        <path d="M9 51 23.5 18.5c1.3-3 3.6-4.5 7-4.5H53" fill="none" stroke="currentColor" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M23.5 35H33l8 16h13V38H45" fill="none" stroke="currentColor" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M54 12h4" fill="none" stroke="#f6c453" strokeWidth="4" strokeLinecap="round" />
      </svg>
      {!compact && (
        <span>
          <strong>AEGIS</strong>
          <small>LOCAL EXECUTIVE AI</small>
        </span>
      )}
    </div>
  );
}
