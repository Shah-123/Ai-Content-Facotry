const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`;
const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || `ws://${window.location.hostname}:8000`;

export type SourceMode = 'closed_book' | 'hybrid' | 'auto_topic';


export interface CreateJobParams {
  topic: string;
  tone?: string;
  sections?: number;
  // SEO keywords the writer should weave into the post. The form accepts
  // a comma-separated string; we split client-side before sending.
  keywords?: string[];
  generate_podcast?: boolean;
  generate_video?: boolean;
  generate_campaign?: boolean;
  // Document upload (optional)
  upload_id?: string;
  source_mode?: SourceMode;
}

export interface UploadResult {
  upload_id: string;
  filename: string;
  format: string;
  bytes: number;
  pages: number;
  chunks: number;
  chunks_processed: number;
  evidence_count: number;
  truncated: boolean;
  derived_topic: string;
  preview: string;
}

export interface Job {
  id: string;
  topic: string;
  tone: string;
  sections: number;
  status: 'pending' | 'running' | 'awaiting_approval' | 'completed' | 'failed';
  created_at: string;
  completed_at?: string;
  blog_folder?: string;
  qa_score?: number;
  qa_verdict?: string;
  blog_evaluator_score?: number;
  geval_scores?: {
    coherence: { score: number; reasoning: string };
    relevance: { score: number; reasoning: string };
    accuracy: { score: number; reasoning: string };
    tone_alignment: { score: number; reasoning: string };
    overall_score: number;
  };
  // Official deepeval G-Eval (Liu et al. 2023). Scores on 0.0–1.0 scale.
  deepeval_scores?: {
    coherence: { score: number | null; reasoning: string };
    relevance: { score: number | null; reasoning: string };
    accuracy: { score: number | null; reasoning: string };
    tone_alignment: { score: number | null; reasoning: string };
    overall_score: number;
  };
  blog_file?: string;
  blog_html_file?: string;
  podcast_file?: string;
  video_file?: string;
  plan?: any;
  error_message?: string;
  word_count?: number;
  final_content?: string;
  social_linkedin?: string;
  social_twitter?: string;
}

export interface AgentEvent {
  job_id: string;
  agent_name: string;
  status: 'started' | 'working' | 'completed' | 'error' | 'plan_ready' | 'plan_revised' | 'plan_approved';
  message: string;
  timestamp: number;
  metrics?: Record<string, any>;
  type?: string; // used for internal ping/keepalive
}

export class APIClient {
  static async fetchJobs(): Promise<Job[]> {
    const res = await fetch(`${API_BASE_URL}/api/jobs`);
    if (!res.ok) throw new Error('Failed to fetch jobs');
    return res.json();
  }

  static async uploadDocument(file: File): Promise<UploadResult> {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${API_BASE_URL}/api/uploads`, {
      method: 'POST',
      body: form,
    });
    if (!res.ok) {
      let detail: any = null;
      try { detail = (await res.json())?.detail; } catch { /* ignore */ }
      const err: any = new Error(detail?.reason || 'Upload failed.');
      err.code = detail?.error || 'upload_failed';
      err.detail = detail;
      throw err;
    }
    return res.json();
  }

  static async createJob(params: CreateJobParams): Promise<Job> {
    const res = await fetch(`${API_BASE_URL}/api/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) {
      // Try to surface the backend's structured rejection (e.g. Topic Guard).
      let detail: any = null;
      try { detail = (await res.json())?.detail; } catch { /* ignore */ }
      if (detail && typeof detail === 'object' && detail.error === 'topic_rejected') {
        const err: any = new Error(detail.reason || 'Topic was rejected.');
        err.code = 'topic_rejected';
        err.category = detail.category;
        err.reason = detail.reason;
        err.suggested_topic = detail.suggested_topic;
        throw err;
      }
      throw new Error('Failed to create job');
    }
    return res.json();
  }

  static async getJob(id: string): Promise<Job> {
    const res = await fetch(`${API_BASE_URL}/api/jobs/${id}`);
    if (!res.ok) throw new Error('Failed to get job');
    return res.json();
  }

  static async deleteJob(id: string): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/api/jobs/${id}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error('Failed to delete job');
  }

  static async approvePlan(id: string): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/api/jobs/${id}/approve-plan`);
    if (!res.ok) throw new Error('Failed to approve plan');
  }

  static async revisePlan(id: string, feedback: string): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/api/jobs/${id}/revise-plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feedback }),
    });
    if (!res.ok) throw new Error('Failed to revise plan');
  }

  static async updatePlan(id: string, plan: {
    blog_title: string;
    tone: string;
    audience: string;
    tasks: Array<{ title: string; goal: string; bullets: string[]; target_words: number; tags: string[] }>;
  }): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/api/jobs/${id}/update-plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(plan),
    });
    if (!res.ok) throw new Error('Failed to update plan');
  }

  static async triggerImages(id: string): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/api/jobs/${id}/generate-images`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to trigger images');
  }

  static async triggerVideo(id: string): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/api/jobs/${id}/generate-video`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to trigger video');
  }

  static async triggerPodcast(id: string): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/api/jobs/${id}/generate-podcast`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to trigger podcast');
  }

  static async triggerSocial(id: string): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/api/jobs/${id}/generate-social`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to trigger social');
  }

  static async triggerQA(id: string): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/api/jobs/${id}/run-qa`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to trigger QA');
  }

  static async runDeepEval(id: string): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/api/jobs/${id}/run-deepeval`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to trigger deepeval academic audit');
  }

  static getFileUrl(jobId: string, filename: string): string {
    return `${API_BASE_URL}/api/files/${jobId}/${filename}`;
  }
}

export class WebSocketClient {
  private ws: WebSocket | null = null;

  connect(jobId: string, onMessage: (event: AgentEvent) => void, onDisconnect?: () => void) {
    if (this.ws) {
      this.ws.close();
    }

    this.ws = new WebSocket(`${WS_BASE_URL}/ws/${jobId}`);

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'ping') return; // Ignore keepalive pings
        onMessage(data as AgentEvent);
      } catch (err) {
        console.error('Failed to parse WebSocket message', err);
      }
    };

    this.ws.onerror = (err) => {
      console.error('WebSocket error:', err);
    };

    this.ws.onclose = () => {
      console.log(`WebSocket disconnected for job ${jobId}`);
      if (onDisconnect) onDisconnect();
    };
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}
