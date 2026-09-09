import { lazy, Suspense, useState, useEffect, useRef } from 'react';
import { APIClient, WebSocketClient, Job, AgentEvent, CreateJobParams } from './api';
import { ViewState } from './types';
import { Sidebar } from './components/Sidebar';
import { TopNav } from './components/TopNav';
import { ChatView } from './components/ChatView';
import { Toasts, toast } from './components/Toast';
import { Cpu, X } from 'lucide-react';
import { motion } from 'motion/react';

const ContentView = lazy(() => import('./ContentView').then(({ ContentView }) => ({ default: ContentView })));

export default function App() {
  const [view, setView]               = useState<ViewState>('chat');
  const [jobs, setJobs]               = useState<Job[]>([]);
  const [currentJob, setCurrentJob]   = useState<Job | null>(null);
  const [events, setEvents]           = useState<AgentEvent[]>([]);
  const [topicError, setTopicError]   = useState<{ reason: string; category?: string; suggested_topic?: string } | null>(null);
  const wsClientRef                   = useRef<WebSocketClient>(new WebSocketClient());

  // Lifted configurations
  const [tone, setTone]               = useState<string>('professional');
  const [sections, setSections]       = useState<number>(3);
  const [numImages, setNumImages]     = useState<number>(2);
  const [keywordsInput, setKeywordsInput] = useState<string>('');
  const [selectedModel, setSelectedModel] = useState<string>('gpt-5-mini');
  const [imageModel, setImageModel]   = useState<string>('dall-e-3');
  const [imageSize, setImageSize]     = useState<string>('1024x1024');
  const [imageQuality, setImageQuality] = useState<string>('standard');
  const [imageStyle, setImageStyle]   = useState<string>('vivid');
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState<boolean>(false);

  const navTo = (v: ViewState) => setView(v);

  const fetchJobsList = async () => {
    try {
      const fetched = await APIClient.fetchJobs();
      setJobs(fetched);
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

  // Poll jobs every 15s and clean up the websocket on unmount.
  useEffect(() => {
    fetchJobsList();
    const interval = setInterval(fetchJobsList, 15000);
    return () => {
      clearInterval(interval);
      wsClientRef.current.disconnect();
    };
  }, []);

  // Escape closes the settings dialog.
  useEffect(() => {
    if (!isSettingsOpen) return;
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape') setIsSettingsOpen(false); };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isSettingsOpen]);

  const loadJob = async (jobId: string) => {
    try {
      const [job, historicalEvents] = await Promise.all([
        APIClient.getJob(jobId),
        APIClient.getJobEvents(jobId),
      ]);
      setCurrentJob(job);
      setEvents(historicalEvents || []);

      const ws = wsClientRef.current;
      ws.disconnect();
      ws.connect(jobId, (event) => {
        setEvents(prev => {
          const isDupe = prev.some(
            e => e.agent_name === event.agent_name
              && e.message === event.message
              && Math.abs(e.timestamp - event.timestamp) < 0.01
          );
          if (isDupe) return prev;
          return [...prev, event];
        });
        // Refresh currentJob whenever the backend signals a state transition.
        if (['completed', 'error', 'plan_ready', 'plan_revised', 'plan_approved'].includes(event.status)) {
          APIClient.getJob(jobId).then(setCurrentJob).catch(console.error);
        }
      });
    } catch (e) {
      toast.fromError(e, 'Could not open that job. Check the backend is running.');
    }
  };

  // Re-dial the WebSocket when a secondary task (video/podcast/social) is triggered
  // from ContentView after the main pipeline's WS has already closed. We clear the
  // events list so only the new task's events are displayed.
  const reconnectWS = (jobId: string) => {
    setEvents([]);
    const ws = wsClientRef.current;
    ws.disconnect();
    ws.connect(jobId, (event) => {
      setEvents(prev => {
        // De-dupe replayed events by (agent + message + ~timestamp).
        const isDupe = prev.some(
          e => e.agent_name === event.agent_name
            && e.message === event.message
            && Math.abs(e.timestamp - event.timestamp) < 0.01
        );
        if (isDupe) return prev;
        return [...prev, event];
      });
      if (event.agent_name === 'system' && (event.status === 'completed' || event.status === 'error')) {
        APIClient.getJob(jobId).then(setCurrentJob).catch(console.error);
      }
    });
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
      setEvents([]);
      fetchJobsList();
      const ws = wsClientRef.current;
      ws.disconnect();
      ws.connect(newJob.id, (event) => {
        setEvents(prev => [...prev, event]);
        if (['completed','error','plan_ready','plan_revised','plan_approved'].includes(event.status)) {
          APIClient.getJob(newJob.id).then(setCurrentJob).catch(console.error);
        }
      });
    } catch (e: any) {
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
      const ws = wsClientRef.current;
      ws.disconnect();
      ws.connect(jobId, (event) => {
        setEvents(prev => [...prev, event]);
        if (['completed','error','plan_ready','plan_revised','plan_approved'].includes(event.status)) {
          APIClient.getJob(jobId).then(setCurrentJob).catch(console.error);
          fetchJobsList();  // Keep sidebar in sync
        }
      });
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
        navTo={navTo}
        jobs={jobs}
        currentJob={currentJob}
        loadJob={(id) => { setIsMobileSidebarOpen(false); loadJob(id); }}
        startNewJob={() => { setIsMobileSidebarOpen(false); startNewJob(); }}
        onDeleteJob={handleDeleteJob}
        onResumeJob={handleResumeJob}
        isMobileOpen={isMobileSidebarOpen}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
      />
      <div className="flex-1 md:ml-[260px] flex flex-col h-dvh relative">
        <TopNav view={view} onToggleMobileSidebar={() => setIsMobileSidebarOpen(prev => !prev)} />
        {view === 'chat' && (
          <ChatView
            navTo={navTo}
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
            setNumImages={setNumImages}
            keywordsInput={keywordsInput}
            setKeywordsInput={setKeywordsInput}
            selectedModel={selectedModel}
            openSettings={() => setIsSettingsOpen(true)}
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

      {isSettingsOpen && (
        <div
          className="fixed inset-0 bg-base-950/80 backdrop-blur-md flex items-center justify-center z-[100] flex-col p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="settings-dialog-title"
          onClick={(e) => { if (e.target === e.currentTarget) setIsSettingsOpen(false); }}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="glass-panel w-full max-w-md rounded-2xl p-6 relative overflow-hidden border border-white/10"
          >
            {/* Header */}
            <div className="flex justify-between items-center mb-5 pb-3 border-b border-white/10">
              <div className="flex items-center gap-2">
                <Cpu className="w-[18px] h-[18px] text-accent-400" aria-hidden="true" />
                <h3 id="settings-dialog-title" className="text-md font-bold text-base-100">Model Selector</h3>
              </div>
              <button
                onClick={() => setIsSettingsOpen(false)}
                aria-label="Close model selector"
                className="p-1 rounded-lg text-base-500 hover:text-base-100 hover:bg-white/5 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Model Selection */}
            <div className="space-y-4">
              <div>
                <label className="text-[10px] font-bold text-base-400 uppercase tracking-wider mb-1.5 block">Default Foundation LLM</label>
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="w-full bg-base-900 border border-white/8 rounded-xl px-3 py-2.5 text-sm text-base-100 focus:outline-none focus:border-accent-500/40 transition-colors"
                >
                  {/* OpenAI only: the agent layer builds a ChatOpenAI client
                      (Graph/agents/utils.py → get_llm), so a Claude or Gemini
                      model id here would be sent to the OpenAI API and fail.
                      Gemini is still used for podcast/TTS audio, which is wired
                      separately and not affected by this selector. */}
                  <optgroup label="OpenAI Models" className="bg-base-900 text-base-100">
                    <option value="gpt-5-mini">GPT-5 Mini (Default - Fast & High Quality)</option>
                    <option value="gpt-4o-mini">GPT-4o-mini (Fast & Cheap)</option>
                    <option value="gpt-4o">GPT-4o (Premium Quality)</option>
                  </optgroup>
                </select>
                <p className="text-[11px] text-base-500 mt-1.5 leading-relaxed">
                  Sets the model used by the parallel section writers. Planning, QA, and
                  evaluation use the server-configured default (<code className="text-base-400">LLM_QUALITY_MODEL</code>).
                </p>
              </div>

              {/* OpenAI Image Generation Settings */}
              <div className="pt-3 border-t border-white/10 space-y-3">
                <div>
                  <label className="text-[10px] font-bold text-base-400 uppercase tracking-wider mb-1.5 block">OpenAI Image Model</label>
                  <select
                    value={imageModel}
                    onChange={(e) => setImageModel(e.target.value)}
                    className="w-full bg-base-900 border border-white/8 rounded-xl px-3 py-2 text-sm text-base-100 focus:outline-none focus:border-accent-500/40 transition-colors"
                  >
                    <option value="dall-e-3">DALL-E 3 (Premium Quality - HD / Vivid)</option>
                    <option value="dall-e-2">DALL-E 2 (Standard Quality)</option>
                  </select>
                </div>

                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="text-[10px] font-bold text-base-400 uppercase tracking-wider mb-1 block">Size</label>
                    <select
                      value={imageSize}
                      onChange={(e) => setImageSize(e.target.value)}
                      className="w-full bg-base-900 border border-white/8 rounded-xl px-2 py-1.5 text-xs text-base-100 focus:outline-none focus:border-accent-500/40 transition-colors"
                    >
                      <option value="1024x1024">Square (1:1)</option>
                      <option value="1792x1024">Landscape (16:9)</option>
                      <option value="1024x1792">Portrait (9:16)</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-[10px] font-bold text-base-400 uppercase tracking-wider mb-1 block">Quality</label>
                    <select
                      value={imageQuality}
                      disabled={imageModel !== 'dall-e-3'}
                      onChange={(e) => setImageQuality(e.target.value)}
                      className="w-full bg-base-900 border border-white/8 rounded-xl px-2 py-1.5 text-xs text-base-100 focus:outline-none focus:border-accent-500/40 transition-colors disabled:opacity-40"
                    >
                      <option value="standard">Standard</option>
                      <option value="hd">HD</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-[10px] font-bold text-base-400 uppercase tracking-wider mb-1 block">Style</label>
                    <select
                      value={imageStyle}
                      disabled={imageModel !== 'dall-e-3'}
                      onChange={(e) => setImageStyle(e.target.value)}
                      className="w-full bg-base-900 border border-white/8 rounded-xl px-2 py-1.5 text-xs text-base-100 focus:outline-none focus:border-accent-500/40 transition-colors disabled:opacity-40"
                    >
                      <option value="vivid">Vivid</option>
                      <option value="natural">Natural</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="mt-6 pt-4 border-t border-white/10 flex justify-end">
              <button
                onClick={() => setIsSettingsOpen(false)}
                className="btn-primary px-5 py-2 rounded-xl text-sm font-semibold"
              >
                Save Configurations
              </button>
            </div>
          </motion.div>
        </div>
      )}

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
