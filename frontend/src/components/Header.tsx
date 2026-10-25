interface HeaderProps {
  theme: 'light' | 'dark'
  onToggleTheme: () => void
}

export function Logo() {
  return (
    <svg className="logo" viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <ellipse cx="16" cy="16" rx="13" ry="6.5" transform="rotate(-25 16 16)" stroke="currentColor" strokeWidth="2" opacity="0.55" />
      <circle cx="16" cy="16" r="5" fill="currentColor" />
      <circle cx="27" cy="10.8" r="2.4" className="logo-moon" />
    </svg>
  )
}

export function Header({ theme, onToggleTheme }: HeaderProps) {
  return (
    <header className="header">
      <div className="brand">
        <Logo />
        <div>
          <h1 className="brand-name">ORBIT</h1>
          <p className="brand-tagline">Personal file assistant</p>
        </div>
      </div>
      <div className="header-actions">
        <span className="pill pill-safe" title="ORBIT never changes your files in this milestone">
          <span className="dot" /> Read-only
        </span>
        <button
          className="icon-button"
          onClick={onToggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
        >
          {theme === 'dark' ? (
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
              <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
            </svg>
          )}
        </button>
      </div>
    </header>
  )
}
