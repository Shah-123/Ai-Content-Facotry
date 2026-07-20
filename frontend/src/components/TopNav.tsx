import { Bell, Settings, Menu, Search, Sun, Moon } from 'lucide-react';
import { ViewState } from '../types';
import { useTheme } from '../hooks/useTheme';

export function TopNav({ view }: { view: ViewState }) {
  const { theme, toggleTheme } = useTheme();
  return (
    <nav className="sticky top-0 w-full z-40 bg-base-950/60 backdrop-blur-xl flex justify-between items-center px-6 md:px-8 py-3 border-b border-white/4 h-14 shrink-0">
      <div className="flex items-center gap-4">
        <span className="text-lg font-bold text-gradient-amber tracking-tight block md:hidden">AI Content Factory</span>
        {view === 'content' && (
          <div className="hidden md:flex gap-1 text-sm">
            <button className="px-3 py-1.5 rounded-lg text-accent-400 bg-accent-500/10 font-semibold text-[13px]">Studio</button>
            <button className="px-3 py-1.5 rounded-lg text-base-400 hover:text-base-200 hover:bg-white/3 transition-all text-[13px]">Library</button>
          </div>
        )}
      </div>
      <div className="flex items-center gap-2">
        {view === 'content' && (
          <div className="hidden md:flex relative group mr-2">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-base-500 group-focus-within:text-accent-400 transition-colors" />
            <input
              type="text"
              placeholder="Search content..."
              className="bg-base-800 border border-white/6 rounded-xl pl-9 pr-4 py-1.5 text-sm text-base-100 focus:outline-none focus:border-accent-500/40 transition-all w-56 placeholder:text-base-500"
            />
          </div>
        )}
        <button
          onClick={toggleTheme}
          className="p-2 rounded-xl text-base-400 hover:text-accent-400 hover:bg-white/3 transition-all"
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          aria-label="Toggle theme"
        >
          {theme === 'dark'
            ? <Sun  className="w-[18px] h-[18px]" />
            : <Moon className="w-[18px] h-[18px]" />}
        </button>
        <button className="p-2 rounded-xl text-base-400 hover:text-accent-400 hover:bg-white/3 transition-all"><Bell     className="w-[18px] h-[18px]" /></button>
        <button className="p-2 rounded-xl text-base-400 hover:text-accent-400 hover:bg-white/3 transition-all hidden md:flex"><Settings className="w-[18px] h-[18px]" /></button>
        <button className="md:hidden p-2 rounded-xl text-base-400"><Menu className="w-[18px] h-[18px]" /></button>
        <div className="w-8 h-8 rounded-xl aurora-chip flex items-center justify-center ml-1 cursor-pointer text-[11px] font-bold">SE</div>
      </div>
    </nav>
  );
}
