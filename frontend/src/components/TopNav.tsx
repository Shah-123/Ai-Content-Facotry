import { Bell, Menu, Sun, Moon } from 'lucide-react';
import { ViewState } from '../types';
import { useTheme } from '../hooks/useTheme';

export function TopNav({ view, onToggleMobileSidebar }: { view: ViewState; onToggleMobileSidebar?: () => void }) {
  const { theme, toggleTheme } = useTheme();
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
        <span
          className="p-2 rounded-xl text-base-500"
          title="Job updates appear in the Studio activity feed"
          aria-label="Job activity feed"
        >
          <Bell className="w-4.5 h-4.5" />
        </span>
        <button onClick={onToggleMobileSidebar} className="md:hidden p-2 rounded-xl text-base-400 hover:text-accent-400 hover:bg-white/5" aria-label="Open menu"><Menu className="w-5 h-5" /></button>
        <div className="w-8 h-8 rounded-xl aurora-chip flex items-center justify-center ml-1 text-[11px] font-bold shadow-sm" title="Current user">SE</div>
      </div>
    </nav>
  );
}
