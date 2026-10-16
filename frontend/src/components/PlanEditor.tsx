import { useState, useRef, useEffect } from 'react';
import { Pencil, Plus, Trash2 } from 'lucide-react';

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
  const titleRefs = useRef<Record<number, HTMLTextAreaElement | null>>({});

  // Focus + scroll the newly added section's title input after it mounts.
  useEffect(() => {
    if (pendingFocusIdx === null) return;
    const el = titleRefs.current[pendingFocusIdx];
    if (el) {
      el.focus();
      el.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' });
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
    <div className="w-full">
      <div className="mb-4">
        <h2 className="font-serif text-title-sm text-base-50">Review the outline</h2>
        <p className="mt-1 text-ui text-base-400">
          {tasks.length} sections · edit titles inline or ask the AI to revise
        </p>
      </div>

      {/* Blog title */}
      <label htmlFor="plan-title" className="field-label">Title</label>
      <input
        id="plan-title"
        type="text"
        className="field field-lg font-medium"
        value={editedTitle}
        onChange={e => { setEditedTitle(e.target.value); markEdited(); }}
      />

      {/* Sections */}
      <p className="mt-6 mb-2 text-xs font-medium text-base-500">Sections</p>
      <div className="card overflow-hidden divide-y divide-line">
        {tasks.map((task, idx) => (
          <div key={idx} className="group">
            {/* Section header — always visible */}
            <div className="flex items-start gap-3 px-3 py-2.5 hover:bg-hover focus-within:bg-hover transition-colors">
              <span className="w-5 pt-0.5 font-mono text-xs text-base-500 tabular-nums">
                {idx + 1}
              </span>
              <textarea
                ref={el => { titleRefs.current[idx] = el; }}
                rows={1}
                aria-label={`Section ${idx + 1} title`}
                className="flex-1 -mx-1.5 min-h-5 resize-none rounded-sm bg-transparent px-1.5 text-base md:text-ui font-medium leading-5 text-base-100 whitespace-pre-wrap break-words placeholder:text-base-500 focus:text-base-50 [field-sizing:content]"
                placeholder="Section title"
                value={task.title}
                // A title stays one line, as it was with the old <input>.
                onKeyDown={e => { if (e.key === 'Enter') e.preventDefault(); }}
                onChange={e => updateTask(idx, 'title', e.target.value.replace(/\r?\n/g, ' '))}
              />
              <div className="-my-1 flex gap-0.5 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100 transition-opacity">
                <button
                  onClick={() => setExpandedSection(expandedSection === idx ? null : idx)}
                  className="btn btn-ghost btn-icon btn-sm"
                  aria-label={`Edit section ${idx + 1}`}
                  aria-expanded={expandedSection === idx}
                  title="Edit details"
                >
                  <Pencil aria-hidden="true" />
                </button>
                <button
                  onClick={() => removeTask(idx)}
                  disabled={tasks.length <= 1}
                  className="btn btn-danger btn-icon btn-sm"
                  aria-label={`Delete section ${idx + 1}`}
                  title="Remove section"
                >
                  <Trash2 aria-hidden="true" />
                </button>
              </div>
            </div>

            {/* Expanded details */}
            {expandedSection === idx && (
              <div className="grid gap-3 px-3 pb-3 pl-11">
                <div>
                  <label htmlFor={`plan-${idx}-goal`} className="field-label">Goal</label>
                  <input
                    id={`plan-${idx}-goal`}
                    type="text"
                    className="field"
                    placeholder="What should the reader learn from this section?"
                    value={task.goal}
                    onChange={e => updateTask(idx, 'goal', e.target.value)}
                  />
                </div>
                <div>
                  <label htmlFor={`plan-${idx}-bullets`} className="field-label">Key points (one per line)</label>
                  <textarea
                    id={`plan-${idx}-bullets`}
                    rows={4}
                    className="field"
                    placeholder="Enter key points, one per line"
                    value={task.bullets.join('\n')}
                    onChange={e => updateTask(idx, 'bullets', e.target.value.split('\n').filter((b: string) => b.trim()))}
                  />
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label htmlFor={`plan-${idx}-words`} className="field-label">Target words</label>
                    <input
                      id={`plan-${idx}-words`}
                      type="number"
                      className="field"
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
                  <div>
                    <label htmlFor={`plan-${idx}-tags`} className="field-label">SEO tags</label>
                    <input
                      id={`plan-${idx}-tags`}
                      type="text"
                      className="field"
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
      </div>

      <button onClick={addTask} className="mt-2 btn btn-ghost btn-sm">
        <Plus aria-hidden="true" />
        Add section
      </button>

      {/* AI revision feedback */}
      <div className="mt-6">
        <label htmlFor="plan-feedback" className="field-label">Ask the AI to revise</label>
        <textarea
          id="plan-feedback"
          className="field"
          placeholder="e.g. Merge sections 3 and 4, add a pricing comparison"
          value={feedback}
          onChange={e => setFeedback(e.target.value)}
        />
      </div>

      {/* Sticky action footer: approve stays reachable without scrolling */}
      <div className="sticky bottom-0 z-10 -mx-4 px-4 md:mx-0 md:px-0 mt-6 py-3 bg-canvas border-t border-line flex flex-wrap items-center justify-end gap-2">
        {feedback.trim().length > 0 && (
          <button
            onClick={() => { onRevise(feedback); setFeedback(''); }}
            className="btn btn-ghost"
          >
            Revise with AI
          </button>
        )}
        {isEdited && (
          <button onClick={handleSaveAndApprove} className="btn btn-secondary">
            <Pencil aria-hidden="true" />
            Save edits &amp; generate
          </button>
        )}
        <button onClick={onApprove} className="btn btn-primary">
          {isEdited ? 'Approve original' : 'Approve & generate'}
        </button>
      </div>
    </div>
  );
}
