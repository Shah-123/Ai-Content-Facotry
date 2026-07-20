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
  const [editedTone, setEditedTone]         = useState(plan.tone       || 'professional');
  const [editedAudience, setEditedAudience] = useState(plan.audience   || 'general');
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
    <div className="self-start max-w-3xl flex gap-3 w-full mt-2">
      <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0 bg-signal-warning-dim">
        <Bot className="w-4 h-4 text-signal-warning" />
      </div>
      <div className="glass-panel p-6 rounded-2xl rounded-tl-sm flex-1 border border-signal-warning/20">
        <h3 className="text-lg font-bold text-signal-warning mb-1">Plan Ready for Approval</h3>
        <p className="text-sm text-base-300 mb-4">Edit the outline below, add or remove sections, then approve.</p>

        {/* Blog Title */}
        <div className="bg-base-900 p-4 rounded-xl border border-white/4 mb-4">
          <label className="text-[10px] font-semibold text-base-500 uppercase tracking-wider mb-1.5 block">Blog Title</label>
          <input
            type="text"
            className="w-full bg-base-800 border border-white/6 rounded-lg px-3 py-2 text-sm text-base-100 font-medium focus:outline-none focus:border-accent-500/40 transition-colors"
            value={editedTitle}
            onChange={e => { setEditedTitle(e.target.value); markEdited(); }}
          />
        </div>

        {/* Sections */}
        <div className="space-y-2 mb-4">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] font-semibold text-base-500 uppercase tracking-wider">Sections ({tasks.length})</span>
          </div>

          {tasks.map((task, idx) => (
            <div key={idx} className="bg-base-900 rounded-xl border border-white/6 overflow-hidden group transition-all duration-200 hover:border-white/10">
              {/* Section Header — always visible */}
              <div className="flex items-center gap-2 px-4 py-3">
                <GripVertical className="w-3.5 h-3.5 text-base-600 shrink-0" />
                <span className="text-accent-500 text-xs font-bold shrink-0 w-5">{idx + 1}</span>
                <input
                  ref={el => { titleRefs.current[idx] = el; }}
                  type="text"
                  className="flex-1 bg-transparent border-none text-sm text-base-100 font-medium focus:outline-none placeholder:text-base-500"
                  placeholder="Section title..."
                  value={task.title}
                  onChange={e => updateTask(idx, 'title', e.target.value)}
                />
                <button
                  onClick={() => setExpandedSection(expandedSection === idx ? null : idx)}
                  className="p-1.5 rounded-lg text-base-500 hover:text-accent-400 hover:bg-white/4 transition-all"
                  title="Edit details"
                >
                  <Pencil className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => removeTask(idx)}
                  disabled={tasks.length <= 1}
                  className={`p-1.5 rounded-lg transition-all ${tasks.length <= 1 ? 'text-base-700 cursor-not-allowed' : 'text-base-500 hover:text-signal-error hover:bg-signal-error-dim'}`}
                  title="Remove section"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Expanded Details */}
              {expandedSection === idx && (
                <div className="px-4 pb-4 pt-1 border-t border-white/4 space-y-3">
                  <div>
                    <label className="text-[10px] font-semibold text-base-500 uppercase tracking-wider mb-1 block">Goal</label>
                    <input
                      type="text"
                      className="w-full bg-base-800 border border-white/6 rounded-lg px-3 py-2 text-sm text-base-300 focus:outline-none focus:border-accent-500/40 transition-colors"
                      placeholder="What should the reader learn from this section?"
                      value={task.goal}
                      onChange={e => updateTask(idx, 'goal', e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="text-[10px] font-semibold text-base-500 uppercase tracking-wider mb-1 block">Key Points (one per line)</label>
                    <textarea
                      className="w-full bg-base-800 border border-white/6 rounded-lg px-3 py-2 text-sm text-base-300 focus:outline-none focus:border-accent-500/40 transition-colors resize-none h-20"
                      placeholder="Enter key points, one per line..."
                      value={task.bullets.join('\n')}
                      onChange={e => updateTask(idx, 'bullets', e.target.value.split('\n').filter((b: string) => b.trim()))}
                    />
                  </div>
                  <div className="flex gap-3">
                    <div className="flex-1">
                      <label className="text-[10px] font-semibold text-base-500 uppercase tracking-wider mb-1 block">Target Words</label>
                      <input
                        type="number"
                        className="w-full bg-base-800 border border-white/6 rounded-lg px-3 py-2 text-sm text-base-300 focus:outline-none focus:border-accent-500/40 transition-colors"
                        value={task.target_words}
                        min={100}
                        max={1000}
                        onChange={e => {
                          // Allow free typing — store raw numeric value (or 0 while empty)
                          // so the user can clear the field and type a new number.
                          const raw = e.target.value;
                          const parsed = raw === '' ? 0 : parseInt(raw, 10);
                          updateTask(idx, 'target_words', isNaN(parsed) ? 0 : parsed);
                        }}
                        onBlur={e => {
                          // Clamp only when the user leaves the field.
                          const parsed = parseInt(e.target.value, 10);
                          const safe = isNaN(parsed) ? 350 : Math.min(1000, Math.max(100, parsed));
                          updateTask(idx, 'target_words', safe);
                        }}
                      />
                    </div>
                    <div className="flex-1">
                      <label className="text-[10px] font-semibold text-base-500 uppercase tracking-wider mb-1 block">SEO Tags (comma-sep)</label>
                      <input
                        type="text"
                        className="w-full bg-base-800 border border-white/6 rounded-lg px-3 py-2 text-sm text-base-300 focus:outline-none focus:border-accent-500/40 transition-colors"
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
            className="w-full py-2.5 rounded-xl border border-dashed border-white/8 text-base-400 hover:text-accent-400 hover:border-accent-500/30 hover:bg-accent-500/5 transition-all flex items-center justify-center gap-2 text-sm"
          >
            <PlusSquare className="w-4 h-4" />
            Add Section
          </button>
        </div>

        {/* AI Revision Feedback */}
        <div className="mb-4">
          <textarea
            className="w-full bg-base-800 border border-white/6 rounded-xl p-3 text-sm text-base-100 focus:outline-none focus:border-accent-500/40 resize-none h-16 placeholder:text-base-500"
            placeholder="Or describe changes and let AI revise the plan..."
            value={feedback}
            onChange={e => setFeedback(e.target.value)}
          />
        </div>

        {/* Action Buttons */}
        <div className="flex gap-2 justify-end flex-wrap">
          {feedback.trim().length > 0 && (
            <button
              onClick={() => { onRevise(feedback); setFeedback(''); }}
              className="px-4 py-2 bg-base-700 hover:bg-base-600 text-base-200 rounded-xl text-sm font-semibold transition-colors border border-white/6"
            >
              Revise with AI
            </button>
          )}
          {isEdited && (
            <button
              onClick={handleSaveAndApprove}
              className="px-5 py-2 bg-accent-500/20 hover:bg-accent-500/30 text-accent-400 border border-accent-500/30 rounded-xl text-sm font-semibold transition-colors flex items-center gap-1.5"
            >
              <Pencil className="w-3.5 h-3.5" />
              Save Edits & Generate
            </button>
          )}
          <button
            onClick={onApprove}
            className="px-5 py-2 bg-signal-success/20 hover:bg-signal-success/30 text-signal-success border border-signal-success/30 rounded-xl text-sm font-semibold transition-colors"
          >
            {isEdited ? 'Approve Original' : 'Approve & Generate'}
          </button>
        </div>
      </div>
    </div>
  );
}
