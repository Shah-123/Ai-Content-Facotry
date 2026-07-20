import { useState, useEffect, useRef } from 'react';
import { APIClient, WebSocketClient, Job, AgentEvent, CreateJobParams } from './api';
import { ContentView } from './ContentView';
import { ViewState } from './types';
import { Sidebar } from './components/Sidebar';
import { TopNav } from './components/TopNav';
import { ChatView } from './components/ChatView';
import { Settings, X } from 'lucide-react';
import { motion } from 'motion/react';

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
  const [keywordsInput, setKeywordsInput] = useState<string>('');
  const [selectedModel, setSelectedModel] = useState<string>('gpt-4o-mini');
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);

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

  const loadJob = async (jobId: string) => {
    try {
      const job = await APIClient.getJob(jobId);
      setCurrentJob(job);
      setEvents([]);
      const ws = wsClientRef.current;
      ws.disconnect();
      ws.connect(jobId, (event) => {
        setEvents(prev => [...prev, event]);
        // Refresh currentJob whenever the backend signals a state transition.
        // 'plan_ready' is critical so the HITL PlanEditor renders the outline.
        if (['completed', 'error', 'plan_ready', 'plan_revised', 'plan_approved'].includes(event.status)) {
          APIClient.getJob(jobId).then(setCurrentJob).catch(console.error);
        }
      });
    } catch (e) {
      console.error('Failed to load job:', e);
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
      console.error('Failed to refresh:', e);
    }
  };

  const handleCreateJob = async (params: CreateJobParams) => {
    setTopicError(null);
    try {
      const newJob = await APIClient.createJob(params);
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
    catch(e) { console.error('Approve failed:', e); }
  };

  const handleRevisePlan = async (jobId: string, feedback: string) => {
    try { await APIClient.revisePlan(jobId, feedback); refreshCurrentJob(jobId); }
    catch(e) { console.error('Revise failed:', e); }
  };

  const handleUpdatePlan = async (jobId: string, plan: any) => {
    try { await APIClient.updatePlan(jobId, plan); refreshCurrentJob(jobId); }
    catch(e) { console.error('Update plan failed:', e); }
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
    } catch (e) {
      console.error('Failed to delete job:', e);
      alert('Failed to delete job.');
    }
  };

  return (
    <div className="min-h-dvh flex overflow-hidden antialiased relative noise-bg ambient-bg">
      <Sidebar
        view={view}
        navTo={navTo}
        jobs={jobs}
        currentJob={currentJob}
        loadJob={loadJob}
        startNewJob={startNewJob}
        onDeleteJob={handleDeleteJob}
        tone={tone}
        setTone={setTone}
        sections={sections}
        setSections={setSections}
        keywordsInput={keywordsInput}
        setKeywordsInput={setKeywordsInput}
        openSettings={() => setIsSettingsOpen(true)}
      />
      <div className="flex-1 md:ml-[260px] flex flex-col h-dvh relative">
        <TopNav view={view} />
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
            tone={tone}
            setTone={setTone}
            sections={sections}
            setSections={setSections}
            keywordsInput={keywordsInput}
            setKeywordsInput={setKeywordsInput}
            selectedModel={selectedModel}
          />
        )}
        {view === 'content' && (
          <ContentView
            navTo={navTo}
            currentJob={currentJob}
            refreshJob={() => currentJob && refreshCurrentJob(currentJob.id)}
            events={events}
            reconnectWS={reconnectWS}
            onDeleteJob={handleDeleteJob}
          />
        )}
      </div>

      {isSettingsOpen && (
        <div className="fixed inset-0 bg-base-950/80 backdrop-blur-md flex items-center justify-center z-[100] flex-col p-4">
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="glass-panel w-full max-w-md rounded-2xl p-6 relative overflow-hidden border border-white/10"
          >
            {/* Header */}
            <div className="flex justify-between items-center mb-5 pb-3 border-b border-white/10">
              <div className="flex items-center gap-2">
                <Settings className="w-[18px] h-[18px] text-accent-400" />
                <h3 className="text-md font-bold text-base-100">System Settings</h3>
              </div>
              <button
                onClick={() => setIsSettingsOpen(false)}
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
                  <optgroup label="OpenAI Models" className="bg-base-900 text-base-100">
                    <option value="gpt-4o-mini">GPT-4o-mini (Default - Fast & Cheap)</option>
                    <option value="gpt-4o">GPT-4o (Premium Quality)</option>
                  </optgroup>
                  <optgroup label="Google Gemini Models" className="bg-base-900 text-base-100">
                    <option value="gemini-2.5-flash">Gemini 2.5 Flash (Native Audio/Speed)</option>
                    <option value="gemini-2.5-pro">Gemini 2.5 Pro (Deep Research)</option>
                  </optgroup>
                  <optgroup label="Anthropic Claude Models" className="bg-base-900 text-base-100">
                    <option value="claude-3-5-sonnet">Claude 3.5 Sonnet (Advanced Writing)</option>
                    <option value="claude-3-5-haiku">Claude 3.5 Haiku (Fast Logic)</option>
                  </optgroup>
                </select>
                <p className="text-[11px] text-base-500 mt-1.5 leading-relaxed">
                  Select which primary cognitive foundation model handles RAG searches, section writing, editing, and quality analysis.
                </p>
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
    </div>
  );
}
