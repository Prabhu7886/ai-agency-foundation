export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`brand-lockup ${compact ? "brand-lockup--compact" : ""}`} aria-label="Aegis">
      <svg className="brand-mark" viewBox="0 0 64 64" role="img" aria-hidden="true">
        <path d="M32 4 55 14v16c0 14-8.7 24.6-23 30C17.7 54.6 9 44 9 30V14L32 4Z" fill="none" stroke="currentColor" strokeWidth="3.5" />
        <path d="m18 44 14-30 14 30-7.4-5.2L32 25l-6.6 13.8L18 44Z" fill="currentColor" />
        <circle cx="32" cy="37" r="5.5" fill="#080d16" stroke="#f6c453" strokeWidth="2.5" />
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
