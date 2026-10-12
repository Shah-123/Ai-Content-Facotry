import { useEffect, useRef, useState } from 'react';
import { Bell, Menu, Sun, Moon, LogOut } from 'lucide-react';
import { Job, AuthUser, auth } from '../api';
import { ViewState } from '../types';
import { useTheme } from '../hooks/useTheme';

interface TopNavProps {
  view: ViewState;
  onToggleMobileSidebar?: () => void;
  isMobileSidebarOpen?: boolean;
  /** Jobs that finished during this session, newest first. */
  notifications: Job[];
  unread: number;
  onOpenNotifications: () => void;
  onSelectNotification: (jobId: string) => void;
}

export function TopNav({
  view, onToggleMobileSidebar, isMobileSidebarOpen,
  notifications, unread, onOpenNotifications, onSelectNotification,
}: TopNavProps) {
  const { theme, toggleTheme } = useTheme();
  const [isBellOpen, setIsBellOpen] = useState(false);

  const toggleBell = () => {
    setIsBellOpen(open => {
      if (!open) onOpenNotifications();   // opening clears the unread dot
      return !open;
    });
  };

  // Escape closes the notification popover, same as the settings dialog.
  useEffect(() => {
    if (!isBellOpen) return;
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape') setIsBellOpen(false); };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isBellOpen]);

  const themeLabel = theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';

  return (
    <nav className="sticky top-0 z-40 flex h-14 shrink-0 items-center gap-3 border-b border-line bg-canvas/80 backdrop-blur-md px-4 md:px-6">
      <button onClick={onToggleMobileSidebar} className="btn btn-ghost btn-icon lg:hidden" aria-label="Open menu" title="Open menu" aria-expanded={!!isMobileSidebarOpen} aria-controls="app-sidebar">
        <Menu aria-hidden="true" />
      </button>
      <span className="text-ui font-semibold text-base-50 lg:hidden">AI Content Factory</span>
      <span className="hidden lg:block text-ui font-medium text-base-100">
        {view === 'content' ? 'Studio' : 'Dashboard'}
      </span>

      <div className="ml-auto flex items-center gap-1">
        <button
          onClick={toggleTheme}
          className="btn btn-ghost btn-icon"
          title={themeLabel}
          aria-label={themeLabel}
        >
          {theme === 'dark' ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
        </button>

        <div className="relative">
          <button
            onClick={toggleBell}
            className="btn btn-ghost btn-icon relative"
            title={unread > 0 ? `${unread} finished blog${unread > 1 ? 's' : ''}` : 'Notifications'}
            aria-label={unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'}
            aria-expanded={isBellOpen}
          >
            <Bell aria-hidden="true" />
            {unread > 0 && (
              <span className="absolute -top-0.5 -right-0.5 min-w-4 h-4 px-1 grid place-items-center rounded-full bg-accent-500 text-on-accent font-mono text-label">
                {unread > 9 ? '9+' : unread}
              </span>
            )}
          </button>

          {isBellOpen && (
            <>
              {/* click-away catcher */}
              <div className="fixed inset-0 z-40" onClick={() => setIsBellOpen(false)} />
              <div className="absolute right-0 top-full mt-1.5 z-50 surface-raised w-80 max-sm:fixed max-sm:inset-x-4 max-sm:top-14 max-sm:w-auto p-1">
                <p className="px-2.5 py-1.5 text-xs font-medium text-base-500">Notifications</p>
                {notifications.length === 0 ? (
                  <p className="px-2.5 pb-3 pt-1 text-xs text-base-500">
                    Nothing yet. Finished blogs show up here.
                  </p>
                ) : notifications.map(job => (
                  <button
                    key={job.id}
                    onClick={() => { setIsBellOpen(false); onSelectNotification(job.id); }}
                    className="menu-item h-auto items-start py-2 transition-colors"
                  >
                    <span className="dot dot-success mt-1.5" aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium text-base-100">{job.topic}</span>
                      <span className="block text-xs text-base-500">Blog ready — open studio draft</span>
                    </span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        <UserMenu />
      </div>
    </nav>
  );
}

/** Avatar chip → who is signed in, and the way out. The chip used to be a
 *  hardcoded "SE" placeholder. */
function UserMenu() {
  const [isOpen, setIsOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  // Escape closes the menu and hands focus back to the avatar ("Sign out"
  // unmounts, so focus would otherwise drop to <body>).
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setIsOpen(false); btnRef.current?.focus(); }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen]);
  // AuthGate resolved this before App ever mounted — no second request.
  const user: AuthUser | null = auth.user;

  const label = user?.name || user?.email || '';
  const initials = label
    ? label.split(/[\s@.]+/).filter(Boolean).slice(0, 2).map(p => p[0]).join('').toUpperCase()
    : '·';

  return (
    <div
      className="relative ml-1"
      onBlur={(e) => {
        // Ignore a null relatedTarget (mouse click without focus, alt-tab).
        const n = e.relatedTarget as Node | null;
        if (n && !e.currentTarget.contains(n)) setIsOpen(false);
      }}
    >
      <button
        ref={btnRef}
        onClick={() => setIsOpen(open => !open)}
        className="grid size-8 [@media(pointer:coarse)]:size-10 place-items-center rounded-full bg-base-800 ring-1 ring-line-strong text-xs font-medium text-base-200"
        title={label || 'Account'}
        aria-label="Account menu"
        aria-expanded={isOpen}
      >
        {initials}
      </button>
      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 top-full mt-1.5 z-50 surface-raised w-56 p-1">
            <p className="px-2.5 pt-1.5 text-ui font-medium text-base-100 truncate">{user?.name || 'Signed in'}</p>
            <p className="px-2.5 pb-1.5 text-xs text-base-500 truncate">{user?.email}</p>
            <div className="my-1 h-px bg-line" />
            <button
              onClick={() => auth.signOut()}
              className="menu-item transition-colors"
            >
              <LogOut aria-hidden="true" />
              Sign out
            </button>
          </div>
        </>
      )}
    </div>
  );
}
