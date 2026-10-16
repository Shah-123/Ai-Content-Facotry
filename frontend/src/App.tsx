import { lazy, Suspense, useState, useEffect, useRef } from 'react';
import { APIClient, WebSocketClient, Job, AgentEvent, CreateJobParams } from './api';
import { appendUniqueEvent, collectFreshCompletions, orderWriterSections } from './events';
import { ViewState } from './types';
import { Sidebar } from './components/Sidebar';
import { TopNav } from './components/TopNav';
import { ChatView } from './components/ChatView';
import { Toasts, toast } from './components/Toast';
import { ChevronDown, Cpu, X } from 'lucide-react';
import { motion } from 'motion/react';

/** Backend statuses that mean the job record changed and should be re-fetched. */
const WS_REFRESH_STATUSES = ['completed', 'error', 'plan_ready', 'plan_revised', 'plan_approved', 'draft_ready'];

const ContentView = lazy(() => import('./ContentView').then(({ ContentView }) => ({ default: ContentView })));

export default function App() {
  const [view, setView]               = useState<ViewState>('chat');
  const [jobs, setJobs]               = useState<Job[]>([]);
  const [currentJob, setCurrentJob]   = useState<Job | null>(null);
  const [events, setEvents]           = useState<AgentEvent[]>([]);
  const [topicError, setTopicError]   = useState<{ reason: string; category?: string; suggested_topic?: string } | null>(null);
  // Bell notifications: jobs that finished while this session was open.
  const [notifications, setNotifications] = useState<Job[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const seenDoneRef                   = useRef<Set<string> | null>(null);
  const wsClientRef                   = useRef<WebSocketClient>(new WebSocketClient());

  // Lifted configurations
  const [tone, setTone]               = useState<string>('professional');
  const [sections, setSections]       = useState<number>(3);
  const [numImages, setNumImages]     = useState<number>(2);
  const [keywordsInput, setKeywordsInput] = useState<string>('');
  const [selectedModel, setSelectedModel] = useState<string>('gpt-5-mini');
  const [imageModel, setImageModel]   = useState<string>('gpt-image-1-mini');
  const [imageSize, setImageSize]     = useState<string>('1024x1024');
  const [imageQuality, setImageQuality] = useState<string>('standard');
  const [imageStyle, setImageStyle]   = useState<string>('vivid');
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState<boolean>(false);
  // Desktop sidebar collapse, remembered across sessions.
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(
    () => localStorage.getItem('sidebar-collapsed') === '1'
  );
  useEffect(() => {
    localStorage.setItem('sidebar-collapsed', isSidebarCollapsed ? '1' : '0');
  }, [isSidebarCollapsed]);

  const navTo = (v: ViewState) => setView(v);

  const fetchJobsList = async () => {
    try {
      const fetched = await APIClient.fetchJobs();
      setJobs(fetched);
      // Anything that completes after the first fetch is news worth ringing the
      // bell for; jobs already finished when the app opened only seed the
      // baseline. Reached from both the 15s poll and the WS status refresh, so
      // a finished blog lands in the bell within a tick of the backend saying so.
      const done = collectFreshCompletions(seenDoneRef.current, fetched);
      seenDoneRef.current = done.seen;
      if (done.fresh.length) {
        setNotifications(prev => [...done.fresh, ...prev].slice(0, 10));
        setUnreadCount(n => n + done.fresh.length);
      }
      // If the currently-open job changed status server-side (e.g. transitioned
      // to awaiting_approval while WS was disconnected), re-pull the full record
      // so currentJob.plan becomes available for the HITL PlanEditor.
      setCurrentJob(prev => {
        if (!prev) return prev;
        const fresh = fetched.find(j => j.id === prev.id);
        if (fresh && (fresh.status !== prev.status || (!prev.plan && fresh.status === 'awaiting_approval'))) {
          APIClient.getJob(prev.id).then(setCurrentJob).catch(console.error);
        }
        return prev;
      });
    } catch (e) {
      // Background poll — log only. Toasting every 15s while the backend is
      // down would bury the screen; the visible failures below are the ones
      // the user actually triggered.
      console.error('Failed to fetch jobs:', e);
    }
  };

  // One WebSocket wiring for every caller. The de-dupe is load-bearing: the
  // backend replays a job's whole event history on each connect (see
  // api/routes/websocket.py) and WebSocketClient retries an unclean drop up to
  // five times, so without it one network hiccup mid-run renders every agent
  // event twice. This used to be four near-identical copies and two of them had
  // drifted without the guard.
  const connectWS = (jobId: string) => {
    const ws = wsClientRef.current;
    ws.disconnect();
    ws.connect(jobId, (event) => {
      setEvents(prev => orderWriterSections(appendUniqueEvent(prev, event)));
      // Refresh whenever the backend signals a state transition, so the job
      // record (plan, final content, usage) and the sidebar badge stay current.
      if (WS_REFRESH_STATUSES.includes(event.status)) {
        APIClient.getJob(jobId).then(setCurrentJob).catch(console.error);
        fetchJobsList();
      }
    });
  };

  // Poll jobs every 15s while the tab is visible (a background tab has no one
  // to show the sidebar to), catch up the moment it is shown again, and clean
  // up the websocket on unmount.
  useEffect(() => {
    fetchJobsList();
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') fetchJobsList();
    }, 15000);
    const onVisible = () => {
      if (document.visibilityState === 'visible') fetchJobsList();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
      wsClientRef.current.disconnect();
    };
  }, []);

  // Native <dialog> modal: showModal() traps focus and close() returns it to
  // the opener. Escape closes it natively and onClose syncs the state back.
  const settingsDialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = settingsDialogRef.current;
    if (!d) return;
    if (isSettingsOpen && !d.open) d.showModal();
    else if (!isSettingsOpen && d.open) d.close();
  }, [isSettingsOpen]);

  // Escape closes the mobile drawer (the settings dialog handles its own).
  useEffect(() => {
    if (!isMobileSidebarOpen || isSettingsOpen) return;
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape') setIsMobileSidebarOpen(false); };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isMobileSidebarOpen, isSettingsOpen]);

  const loadJob = async (jobId: string) => {
    try {
      const [job, historicalEvents] = await Promise.all([
        APIClient.getJob(jobId),
        APIClient.getJobEvents(jobId),
      ]);
      setCurrentJob(job);
      // Replay the persisted history through the same reducer the live WS feed
      // uses. Setting it in bulk skipped appendUniqueEvent, so a reopened job
      // rendered every saved "Rendering video... N%" tick as its own row while
      // the same ticks arriving live collapsed to one.
      setEvents(orderWriterSections((historicalEvents || []).reduce(appendUniqueEvent, [] as AgentEvent[])));

      connectWS(jobId);
    } catch (e) {
      toast.fromError(e, 'Could not open that job. Check the backend is running.');
    }
  };

  // Re-dial the WebSocket when a secondary task (video/podcast/social) is triggered
  // from ContentView after the main pipeline's WS has already closed. We clear the
  // events list so only the new task's events are displayed.
  const reconnectWS = (jobId: string) => {
    setEvents([]);
    connectWS(jobId);
  };

  const refreshCurrentJob = async (jobId: string) => {
    try {
      const job = await APIClient.getJob(jobId);
      setCurrentJob(job);
    } catch (e) {
      toast.fromError(e, 'Could not refresh this job.');
    }
  };

  const handleCreateJob = async (params: CreateJobParams) => {
    setTopicError(null);
    setEvents([]);
    // Flip the screen to the pipeline view NOW. POST /api/jobs blocks on the
    // Topic Guard LLM call (seconds) before it returns a job, so waiting for
    // the response leaves the user staring at a dead hero screen after Enter.
    // Rolled back in catch() if the topic is rejected.
    setCurrentJob({
      id: '',
      topic: params.topic,
      tone: params.tone ?? tone,
      sections: params.sections ?? sections,
      status: 'pending',
      created_at: new Date().toISOString(),
    });
    try {
      const payload = {
        selected_model: selectedModel,
        image_model: imageModel,
        image_size: imageSize,
        image_quality: imageQuality,
        image_style: imageStyle,
        ...params
      };
      const newJob = await APIClient.createJob(payload);
      setCurrentJob(newJob);
      fetchJobsList();
      connectWS(newJob.id);
    } catch (e: any) {
      setCurrentJob(null);   // roll back the optimistic job
      if (e?.code === 'topic_rejected') {
        setTopicError({
          reason: e.reason || 'Topic was rejected.',
          category: e.category,
          suggested_topic: e.suggested_topic || '',
        });
      } else {
        console.error('Failed to create job:', e);
        setTopicError({ reason: 'Could not start the job. Please try again.' });
      }
    }
  };

  const handleApprovePlan = async (jobId: string) => {
    try { await APIClient.approvePlan(jobId); refreshCurrentJob(jobId); }
    catch(e) { toast.fromError(e, 'Could not approve the plan. The job may have timed out — try resuming it.'); }
  };

  const handleRevisePlan = async (jobId: string, feedback: string) => {
    try { await APIClient.revisePlan(jobId, feedback); refreshCurrentJob(jobId); }
    catch(e) { toast.fromError(e, 'Could not submit your plan feedback.'); }
  };

  const handleUpdatePlan = async (jobId: string, plan: any) => {
    try { await APIClient.updatePlan(jobId, plan); refreshCurrentJob(jobId); }
    catch(e) { toast.fromError(e, 'Could not save your outline edits.'); }
  };

  const handleResumeJob = async (jobId: string) => {
    try {
      setEvents([]);  // Clear old events so only resumed pipeline events show
      await APIClient.resumeJob(jobId);
      refreshCurrentJob(jobId);
      fetchJobsList();  // Update sidebar status badge (Fail → Active)
      connectWS(jobId);
    } catch (e) {
      toast.fromError(e, 'Could not resume this job.');
    }
  };

  const startNewJob = () => {
    setCurrentJob(null);
    setEvents([]);
    setTopicError(null);
    navTo('chat');
  };

  const handleDeleteJob = async (jobId: string) => {
    if (!window.confirm("Are you sure you want to delete this job and all of its generated assets?")) {
      return;
    }
    try {
      await APIClient.deleteJob(jobId);
      await fetchJobsList();
      if (currentJob?.id === jobId) {
        startNewJob();
      }
      toast.success('Job and its generated assets were deleted.');
    } catch (e) {
      toast.fromError(e, 'Could not delete the job.');
    }
  };

  return (
    <div className="min-h-dvh flex overflow-hidden antialiased relative noise-bg ambient-bg">
      <Sidebar
        view={view}
        navTo={(v) => { setIsMobileSidebarOpen(false); navTo(v); }}
        jobs={jobs}
        currentJob={currentJob}
        loadJob={(id) => { setIsMobileSidebarOpen(false); loadJob(id); }}
        startNewJob={() => { setIsMobileSidebarOpen(false); startNewJob(); }}
        onDeleteJob={handleDeleteJob}
        onResumeJob={handleResumeJob}
        isMobileOpen={isMobileSidebarOpen}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={() => setIsSidebarCollapsed(prev => !prev)}
        onRefreshJobs={fetchJobsList}
        selectedModel={selectedModel}
        onOpenSettings={() => { setIsMobileSidebarOpen(false); setIsSettingsOpen(true); }}
        tone={tone}
        setTone={setTone}
        sections={sections}
        setSections={setSections}
        numImages={numImages}
        setNumImages={setNumImages}
        keywordsInput={keywordsInput}
        setKeywordsInput={setKeywordsInput}
      />
      <div className={`flex-1 min-w-0 flex flex-col h-dvh relative transition-[margin] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] ${isSidebarCollapsed ? 'lg:ml-[72px]' : 'lg:ml-[260px]'}`}>
        <TopNav
          view={view}
          onToggleMobileSidebar={() => setIsMobileSidebarOpen(prev => !prev)}
          isMobileSidebarOpen={isMobileSidebarOpen}
          notifications={notifications}
          unread={unreadCount}
          onOpenNotifications={() => setUnreadCount(0)}
          onSelectNotification={(id) => { loadJob(id); navTo('content'); }}
        />
        {view === 'chat' && (
          <ChatView
            currentJob={currentJob}
            events={events}
            topicError={topicError}
            clearTopicError={() => setTopicError(null)}
            handleCreateJob={handleCreateJob}
            handleApprovePlan={handleApprovePlan}
            handleRevisePlan={handleRevisePlan}
            handleUpdatePlan={handleUpdatePlan}
            handleResumeJob={handleResumeJob}
            tone={tone}
            setTone={setTone}
            sections={sections}
            setSections={setSections}
            numImages={numImages}
            keywordsInput={keywordsInput}
            setKeywordsInput={setKeywordsInput}
            selectedModel={selectedModel}
          />
        )}
        {view === 'content' && (
          <Suspense fallback={<ViewLoadingLabel label="Loading studio…" />}>
            <ContentView
              navTo={navTo}
              currentJob={currentJob}
              refreshJob={() => currentJob && refreshCurrentJob(currentJob.id)}
              events={events}
              reconnectWS={reconnectWS}
              onDeleteJob={handleDeleteJob}
            />
          </Suspense>
        )}
      </div>

      <dialog
        ref={settingsDialogRef}
        aria-labelledby="settings-dialog-title"
        onClose={() => setIsSettingsOpen(false)}
        onClick={(e) => { if (e.target === e.currentTarget) setIsSettingsOpen(false); }}
        className="m-0 h-dvh max-h-none w-screen max-w-none overflow-y-auto bg-transparent p-4 text-inherit open:grid place-items-center backdrop:bg-black/60 backdrop:backdrop-blur-sm [:root[data-theme=light]_&]:backdrop:bg-[rgba(10,10,12,0.35)]"
      >
        {isSettingsOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
            className="surface-raised relative w-full max-w-md max-h-[calc(100dvh-2rem)] overflow-y-auto rounded-2xl p-6 shadow-[var(--elev-3)]"
          >
            {/* Header */}
            <div className="flex items-center justify-between pb-4 mb-5 border-b border-line">
              <div className="flex items-center gap-2">
                <Cpu className="size-4 text-base-400" aria-hidden="true" />
                <h3 id="settings-dialog-title" className="text-heading">Model selector</h3>
              </div>
              <button
                onClick={() => setIsSettingsOpen(false)}
                aria-label="Close"
                title="Close"
                className="btn btn-ghost btn-icon btn-sm"
              >
                <X aria-hidden="true" />
              </button>
            </div>

            {/* Model Selection */}
            <div className="space-y-4">
              <div>
                <label htmlFor="settings-model" className="field-label">Default model</label>
                <div className="select-wrap">
                  <select
                    id="settings-model"
                    value={selectedModel}
                    onChange={(e) => setSelectedModel(e.target.value)}
                    className="field"
                  >
                    {/* OpenAI only: the agent layer builds a ChatOpenAI client
                        (Graph/agents/utils.py → get_llm), so a Claude or Gemini
                        model id here would be sent to the OpenAI API and fail. */}
                    <optgroup label="OpenAI models">
                      <option value="gpt-5-mini">GPT-5 Mini (Default - Fast & High Quality)</option>
                      <option value="gpt-4o-mini">GPT-4o-mini (Fast & Cheap)</option>
                      <option value="gpt-4o">GPT-4o (Premium Quality)</option>
                    </optgroup>
                  </select>
                  <ChevronDown aria-hidden="true" />
                </div>
                <p className="text-xs text-base-500 mt-1.5 leading-relaxed">
                  Sets the model used by the parallel section writers. Planning, QA, and
                  evaluation use the server-configured default (<code className="text-base-400">LLM_QUALITY_MODEL</code>).
                </p>
              </div>

              {/* OpenAI Image Generation Settings */}
              <div className="pt-4 border-t border-line space-y-4">
                <div>
                  <label htmlFor="settings-image-model" className="field-label">Image model</label>
                  <div className="select-wrap">
                    <select
                      id="settings-image-model"
                      value={imageModel}
                      onChange={(e) => setImageModel(e.target.value)}
                      className="field"
                    >
                      <option value="gpt-image-1-mini">GPT Image 1 Mini (Fast &amp; Affordable)</option>
                      <option value="dall-e-3">DALL-E 3 (Premium Quality - HD / Vivid)</option>
                      <option value="dall-e-2">DALL-E 2 (Standard Quality)</option>
                    </select>
                    <ChevronDown aria-hidden="true" />
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  <div className="col-span-2 sm:col-span-1">
                    <label htmlFor="settings-image-size" className="field-label">Size</label>
                    <div className="select-wrap">
                      <select
                        id="settings-image-size"
                        value={imageSize}
                        onChange={(e) => setImageSize(e.target.value)}
                        className="field"
                      >
                        <option value="1024x1024">Square (1:1)</option>
                        <option value="1792x1024">Landscape (16:9)</option>
                        <option value="1024x1792">Portrait (9:16)</option>
                      </select>
                      <ChevronDown aria-hidden="true" />
                    </div>
                  </div>

                  <div>
                    <label htmlFor="settings-image-quality" className="field-label">Quality</label>
                    <div className="select-wrap">
                      <select
                        id="settings-image-quality"
                        value={imageQuality}
                        disabled={imageModel === 'dall-e-2'}
                        onChange={(e) => setImageQuality(e.target.value)}
                        className="field"
                      >
                        <option value="standard">Standard</option>
                        <option value="hd">HD</option>
                      </select>
                      <ChevronDown aria-hidden="true" />
                    </div>
                  </div>

                  <div>
                    <label htmlFor="settings-image-style" className="field-label">Style</label>
                    <div className="select-wrap">
                      <select
                        id="settings-image-style"
                        value={imageStyle}
                        disabled={imageModel !== 'dall-e-3'}
                        onChange={(e) => setImageStyle(e.target.value)}
                        className="field"
                      >
                        <option value="vivid">Vivid</option>
                        <option value="natural">Natural</option>
                      </select>
                      <ChevronDown aria-hidden="true" />
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="mt-6 pt-4 border-t border-line flex justify-end">
              <button
                onClick={() => setIsSettingsOpen(false)}
                className="btn btn-primary"
              >
                Save configurations
              </button>
            </div>
          </motion.div>
        )}
      </dialog>

      <Toasts />
    </div>
  );
}

function ViewLoadingLabel({ label }: { label: string }) {
  return (
    <div className="flex flex-1 items-center justify-center text-sm font-medium text-base-400">
      {label}
    </div>
  );
}
