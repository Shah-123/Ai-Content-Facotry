import { useState, useRef, useEffect } from 'react';
import {
  Bot, Trash2, GripVertical, Pencil, PlusSquare
} from 'lucide-react';

interface EditableTask {
  id: number;
  title: string;
  goal: string;
  bullets: string[];
  target_words: number;
  tags: string[];
}

interface PlanEditorProps {
  plan: any;
  jobId: string;
  onApprove: () => void;
  onRevise: (feedback: string) => void;
  onUpdatePlan: (plan: any) => void;
}

export function PlanEditor({ plan, onApprove, onRevise, onUpdatePlan }: PlanEditorProps) {
  const [editedTitle, setEditedTitle]       = useState(plan.blog_title || '');
  // Passed straight back to the server unchanged — the outline editor exposes
  // no control for either, so these are plain reads, not editable state.
  const editedTone     = plan.tone     || 'professional';
  const editedAudience = plan.audience || 'general';
  const [tasks, setTasks] = useState<EditableTask[]>(() =>
    (plan.tasks || []).map((t: any, i: number) => ({
      id: i,
      title:        t.title        || '',
      goal:         t.goal         || '',
      bullets:      t.bullets      || [],
      target_words: t.target_words || 350,
      tags:         t.tags         || [],
    }))
  );
  const [feedback, setFeedback]               = useState('');
  const [isEdited, setIsEdited]               = useState(false);
  const [expandedSection, setExpandedSection] = useState<number | null>(null);
  const [pendingFocusIdx, setPendingFocusIdx] = useState<number | null>(null);
  const titleRefs = useRef<Record<number, HTMLInputElement | null>>({});

  // Focus + scroll the newly added section's title input after it mounts.
  useEffect(() => {
    if (pendingFocusIdx === null) return;
    const el = titleRefs.current[pendingFocusIdx];
    if (el) {
      el.focus();
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    setPendingFocusIdx(null);
  }, [pendingFocusIdx, tasks.length]);

  const markEdited = () => setIsEdited(true);

  const updateTask = (idx: number, field: keyof EditableTask, value: any) => {
    setTasks(prev => prev.map((t, i) => i === idx ? { ...t, [field]: value } : t));
    markEdited();
  };

  const removeTask = (idx: number) => {
    if (tasks.length <= 1) return; // keep at least 1 section
    setTasks(prev => prev.filter((_, i) => i !== idx).map((t, i) => ({ ...t, id: i })));
    markEdited();
  };

  const addTask = () => {
    setTasks(prev => {
      const newIdx = prev.length;
      setExpandedSection(newIdx);
      setPendingFocusIdx(newIdx);
      return [...prev, {
        id: newIdx,
        title:        '',
        goal:         '',
        bullets:      [],
        target_words: 350,
        tags:         [],
      }];
    });
    markEdited();
  };

  const handleSaveAndApprove = () => {
    onUpdatePlan({
      blog_title: editedTitle,
      tone:       editedTone,
      audience:   editedAudience,
      tasks: tasks.map((t) => ({
        title:        t.title,
        goal:         t.goal,
        bullets:      t.bullets,
        target_words: t.target_words,
        tags:         t.tags,
      })),
    });
  };

  return (
    <div className="self-start max-w-3xl flex gap-3.5 w-full mt-2">
      <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0 bg-signal-warning-dim border border-signal-warning/15">
        <Bot className="w-4 h-4 text-signal-warning animate-bounce" />
      </div>
      <div className="glass-panel p-6 rounded-2xl rounded-tl-sm flex-1 border border-signal-warning/15">
        <h3 className="text-lg font-bold text-signal-warning mb-1">Plan Ready for Approval</h3>
        <p className="text-sm text-base-300 mb-4.5">Edit the outline below, add or remove sections, then approve.</p>

        {/* Blog Title */}
        <div className="bg-base-950/40 p-4.5 rounded-2xl border border-white/5 mb-4.5 focus-within:border-accent-500/25 transition-all duration-300">
          <label className="text-[10px] font-bold text-base-400 uppercase tracking-widest mb-1.5 block">Blog Title</label>
          <input
            type="text"
            className="w-full bg-base-900/60 border border-white/6 rounded-xl px-3.5 py-2.5 text-sm text-base-100 font-medium focus:outline-none focus:border-accent-500/40 transition-all focus:shadow-[0_0_10px_var(--color-accent-glow)]"
            value={editedTitle}
            onChange={e => { setEditedTitle(e.target.value); markEdited(); }}
          />
        </div>

        {/* Sections */}
        <div className="space-y-3.5 mb-5">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] font-bold text-base-400 uppercase tracking-widest">Sections ({tasks.length})</span>
          </div>

          {tasks.map((task, idx) => (
            <div key={idx} className="bg-base-950/30 rounded-xl border border-white/6 overflow-hidden group transition-all duration-200 hover:border-white/12 hover:bg-base-950/40">
              {/* Section Header — always visible */}
              <div className="flex items-center gap-3 px-4 py-3">
                <GripVertical className="w-3.5 h-3.5 text-base-500 shrink-0" />
                <span className="flex items-center justify-center w-5 h-5 rounded-full bg-accent-500/10 text-accent-400 text-[10px] font-bold shrink-0">
                  {idx + 1}
                </span>
                <input
                  ref={el => { titleRefs.current[idx] = el; }}
                  type="text"
                  className="flex-1 bg-transparent border-none text-sm text-base-100 font-bold focus:ring-0 focus:outline-none placeholder:text-base-600"
                  placeholder="Section title..."
                  value={task.title}
                  onChange={e => updateTask(idx, 'title', e.target.value)}
                />
                <button
                  onClick={() => setExpandedSection(expandedSection === idx ? null : idx)}
                  className="p-1.5 rounded-lg text-base-400 hover:text-accent-400 hover:bg-white/4 transition-all"
                  title="Edit details"
                >
                  <Pencil className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => removeTask(idx)}
                  disabled={tasks.length <= 1}
                  className={`p-1.5 rounded-lg transition-all ${tasks.length <= 1 ? 'text-base-700 cursor-not-allowed' : 'text-base-400 hover:text-signal-error hover:bg-signal-error-dim'}`}
                  title="Remove section"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Expanded Details */}
              {expandedSection === idx && (
                <div className="px-4 pb-4.5 pt-1.5 border-t border-white/4 space-y-4">
                  <div>
                    <label className="text-[10px] font-bold text-base-400 uppercase tracking-widest mb-1.5 block">Goal</label>
                    <input
                      type="text"
                      className="w-full bg-base-900/60 border border-white/6 rounded-lg px-3.5 py-2.5 text-sm text-base-200 focus:outline-none focus:border-accent-500/40 transition-colors"
                      placeholder="What should the reader learn from this section?"
                      value={task.goal}
                      onChange={e => updateTask(idx, 'goal', e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="text-[10px] font-bold text-base-400 uppercase tracking-widest mb-1.5 block">Key Points (one per line)</label>
                    <textarea
                      className="w-full bg-base-900/60 border border-white/6 rounded-lg px-3.5 py-2.5 text-sm text-base-200 focus:outline-none focus:border-accent-500/40 transition-colors resize-none h-24"
                      placeholder="Enter key points, one per line..."
                      value={task.bullets.join('\n')}
                      onChange={e => updateTask(idx, 'bullets', e.target.value.split('\n').filter((b: string) => b.trim()))}
                    />
                  </div>
                  <div className="flex gap-3">
                    <div className="flex-1">
                      <label className="text-[10px] font-bold text-base-400 uppercase tracking-widest mb-1.5 block">Target Words</label>
                      <input
                        type="number"
                        className="w-full bg-base-900/60 border border-white/6 rounded-lg px-3.5 py-2.5 text-sm text-base-200 focus:outline-none focus:border-accent-500/40 transition-colors"
                        value={task.target_words}
                        min={100}
                        max={1000}
                        onChange={e => {
                          const raw = e.target.value;
                          const parsed = raw === '' ? 0 : parseInt(raw, 10);
                          updateTask(idx, 'target_words', isNaN(parsed) ? 0 : parsed);
                        }}
                        onBlur={e => {
                          const parsed = parseInt(e.target.value, 10);
                          const safe = isNaN(parsed) ? 350 : Math.min(1000, Math.max(100, parsed));
                          updateTask(idx, 'target_words', safe);
                        }}
                      />
                    </div>
                    <div className="flex-1">
                      <label className="text-[10px] font-bold text-base-400 uppercase tracking-widest mb-1.5 block">SEO Tags (comma-sep)</label>
                      <input
                        type="text"
                        className="w-full bg-base-900/60 border border-white/6 rounded-lg px-3.5 py-2.5 text-sm text-base-200 focus:outline-none focus:border-accent-500/40 transition-colors"
                        placeholder="tag1, tag2"
                        value={task.tags.join(', ')}
                        onChange={e => updateTask(idx, 'tags', e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean))}
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* Add Section Button */}
          <button
            onClick={addTask}
            className="w-full py-3 rounded-xl border border-dashed border-white/10 text-base-400 hover:text-accent-400 hover:border-accent-500/35 hover:bg-accent-500/5 transition-all flex items-center justify-center gap-2 text-sm font-semibold"
          >
            <PlusSquare className="w-4 h-4" />
            Add Section
          </button>
        </div>

        {/* AI Revision Feedback */}
        <div className="mb-5">
          <textarea
            className="w-full bg-base-900/60 border border-white/6 rounded-xl p-3.5 text-sm text-base-100 focus:outline-none focus:border-accent-500/40 focus:shadow-[0_0_10px_var(--color-accent-glow)] transition-all duration-200 resize-none h-20 placeholder:text-base-500"
            placeholder="Or describe changes and let AI revise the plan..."
            value={feedback}
            onChange={e => setFeedback(e.target.value)}
          />
        </div>

        {/* Action Buttons */}
        <div className="flex gap-3.5 justify-end flex-wrap">
          {feedback.trim().length > 0 && (
            <button
              onClick={() => { onRevise(feedback); setFeedback(''); }}
              className="px-4.5 py-2.5 bg-base-800 hover:bg-base-750 text-base-200 rounded-xl text-sm font-semibold transition-all border border-white/6 hover:border-white/10 shadow-sm"
            >
              Revise with AI
            </button>
          )}
          {isEdited && (
            <button
              onClick={handleSaveAndApprove}
              className="px-5 py-2.5 bg-accent-500/10 hover:bg-accent-500/20 text-accent-400 border border-accent-500/20 rounded-xl text-sm font-bold transition-all flex items-center gap-2"
            >
              <Pencil className="w-3.5 h-3.5" />
              Save Edits & Generate
            </button>
          )}
          <button
            onClick={onApprove}
            className="btn-primary px-5 py-2.5 rounded-xl text-sm font-bold shadow-md hover:shadow-lg transition-all"
          >
            {isEdited ? 'Approve Original' : 'Approve & Generate'}
          </button>
        </div>
      </div>
    </div>
  );
}
