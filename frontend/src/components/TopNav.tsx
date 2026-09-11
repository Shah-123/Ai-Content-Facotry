import { useEffect, useState } from 'react';
import { Bell, Menu, Sun, Moon, CheckCircle2 } from 'lucide-react';
import { Job } from '../api';
import { ViewState } from '../types';
import { useTheme } from '../hooks/useTheme';

interface TopNavProps {
  view: ViewState;
  onToggleMobileSidebar?: () => void;
  /** Jobs that finished during this session, newest first. */
  notifications: Job[];
  unread: number;
  onOpenNotifications: () => void;
  onSelectNotification: (jobId: string) => void;
}

export function TopNav({
  view, onToggleMobileSidebar,
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

  return (
    <nav className="sticky top-0 w-full z-40 bg-base-950/80 backdrop-blur-2xl flex justify-between items-center px-6 md:px-8 py-3 border-b border-white/6 h-14 shrink-0 shadow-sm transition-colors">
      <div className="flex items-center gap-4">
        <span className="text-base font-extrabold text-gradient-amber tracking-tight block md:hidden">AI Content Factory</span>
        <div className="hidden md:flex items-center gap-2">
          <div className="px-2.5 py-1 rounded-full bg-accent-500/10 border border-accent-500/20 text-accent-400 text-[10px] font-bold uppercase tracking-wider flex items-center gap-1.5 shadow-sm">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-400 status-pulse"></span>
            Multi-Agent Engine Active
          </div>
        </div>
        {view === 'content' && (
          <span className="hidden md:inline-flex px-3 py-1.5 rounded-xl text-accent-400 bg-accent-500/10 border border-accent-500/20 font-bold text-xs">
            Studio View
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={toggleTheme}
          className="p-2 rounded-xl text-base-400 hover:text-accent-400 hover:bg-white/5 transition-all"
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          aria-label="Toggle theme"
        >
          {theme === 'dark'
            ? <Sun className="w-4.5 h-4.5" />
            : <Moon className="w-4.5 h-4.5" />}
        </button>

        <div className="relative">
          <button
            onClick={toggleBell}
            className="relative p-2 rounded-xl text-base-400 hover:text-accent-400 hover:bg-white/5 transition-all"
            title={unread > 0 ? `${unread} finished blog${unread > 1 ? 's' : ''}` : 'Notifications'}
            aria-label={unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'}
            aria-expanded={isBellOpen}
          >
            <Bell className="w-4.5 h-4.5" />
            {unread > 0 && (
              <span className="absolute top-1.5 right-1.5 min-w-[15px] h-[15px] px-1 rounded-full bg-emerald-500 text-[9px] font-bold text-base-950 leading-[15px] text-center ring-2 ring-base-950">
                {unread > 9 ? '9+' : unread}
              </span>
            )}
          </button>

          {isBellOpen && (
            <>
              {/* click-away catcher */}
              <div className="fixed inset-0 z-40" onClick={() => setIsBellOpen(false)} />
              <div className="absolute right-0 mt-2 w-72 z-50 glass-panel rounded-xl border border-white/10 p-1.5 shadow-xl">
                <p className="px-2.5 py-1.5 text-[10px] font-bold text-base-400 uppercase tracking-wider">Notifications</p>
                {notifications.length === 0 ? (
                  <p className="px-2.5 pb-3 pt-1 text-xs text-base-500">
                    Nothing yet. Finished blogs show up here.
                  </p>
                ) : notifications.map(job => (
                  <button
                    key={job.id}
                    onClick={() => { setIsBellOpen(false); onSelectNotification(job.id); }}
                    className="w-full flex items-start gap-2.5 text-left px-2.5 py-2 rounded-lg hover:bg-white/5 transition-colors"
                  >
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" aria-hidden="true" />
                    <span className="min-w-0">
                      <span className="block text-xs font-semibold text-base-100 truncate">{job.topic}</span>
                      <span className="block text-[11px] text-base-500">Blog ready — open studio draft</span>
                    </span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        <button onClick={onToggleMobileSidebar} className="md:hidden p-2 rounded-xl text-base-400 hover:text-accent-400 hover:bg-white/5" aria-label="Open menu"><Menu className="w-5 h-5" /></button>
        <div className="w-8 h-8 rounded-xl aurora-chip flex items-center justify-center ml-1 text-[11px] font-bold shadow-sm" title="Current user">SE</div>
      </div>
    </nav>
  );
}
