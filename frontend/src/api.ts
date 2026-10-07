export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`;
const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || `ws://${window.location.hostname}:8000`;

// Optional shared secret. Only needed when the backend has API_KEY set in .env
// (see Agents_backend/api/auth.py); empty by default so local dev is unchanged.
const API_KEY = import.meta.env.VITE_API_KEY || '';

/** Append the key as a query param — for URLs the browser fetches itself
 *  (WebSocket, <img src>, download links) and so cannot attach a header to. */
export const withApiKey = (url: string): string =>
  API_KEY ? `${url}${url.includes('?') ? '&' : '?'}api_key=${encodeURIComponent(API_KEY)}` : url;

// ── Signed-in user ─────────────────────────────────────────────────────────
// The session is an HttpOnly cookie set by Agents_backend/api/users.py on
// login: page scripts can't read it, and the browser sends it on its own with
// <img>/<video> src, export downloads and the progress WebSocket — none of
// which can carry an Authorization header.
//
// Earlier builds kept a bearer token in localStorage. It is still a live
// credential for up to a week, so drop it.
try { localStorage.removeItem('auth-token'); } catch { /* storage blocked */ }

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  created_at?: string;
}

export const auth = {
  /** Whoever the last successful auth call resolved to. Set by APIClient so
   *  components (the TopNav avatar) can read it without a second round-trip. */
  user: null as AuthUser | null,
  /** Clear the session cookie server-side and start over at the login screen. */
  async signOut() {
    await apiFetch(`${API_BASE_URL}/api/auth/logout`, { method: 'POST' }).catch(() => undefined);
    this.user = null;
    window.location.reload();
  },
};

/** fetch() with the session cookie and, when configured, the API key.
 *  X-Requested-With is the backend's CSRF check for cookie-authed writes: a
 *  foreign page can't add a custom header without passing CORS. */
const apiFetch = (url: string, init: RequestInit = {}): Promise<Response> => {
  const headers: Record<string, string> = {
    'X-Requested-With': 'fetch',
    ...(init.headers as Record<string, string>),
  };
  if (API_KEY) headers['X-API-Key'] = API_KEY;
  return fetch(url, { ...init, headers, credentials: 'include' });
};

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
  generate_images?: boolean;
  num_images?: number;
  // Document upload (optional)
  upload_id?: string;
  source_mode?: SourceMode;
  selected_model?: string;
  image_model?: string;
  image_size?: string;
  image_quality?: string;
  image_style?: string;
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
  image_files?: string[];
  image_model?: string;
  image_size?: string;
  image_quality?: string;
  image_style?: string;
  plan?: any;
  error_message?: string;
  word_count?: number;
  final_content?: string;
  social_linkedin?: string;
  social_twitter?: string;
  /** Measured token usage and estimated cost for the run, recorded by
   *  Agents_backend/usage.py. Absent on jobs that never finished and on jobs
   *  that completed before instrumentation existed — treat absence as
   *  "not measured", never as zero. Covers chat completions only; embedding
   *  calls are excluded. Cost is an estimate from published list prices. */
  usage?: {
    total: {
      calls: number;
      input_tokens: number;
      output_tokens: number;
      total_tokens: number;
      cost_usd: number;
    };
    by_model: Record<string, {
      calls: number;
      input_tokens: number;
      output_tokens: number;
      total_tokens: number;
      cost_usd: number;
    }>;
    priced: boolean;
  };
}

export interface AgentEvent {
  job_id: string;
  agent_name: string;
  status: 'started' | 'working' | 'completed' | 'error' | 'plan_ready' | 'plan_revised' | 'plan_approved' | 'draft_ready';
  message: string;
  timestamp: number;
  metrics?: Record<string, any>;
  type?: string; // used for internal ping/keepalive
}

export class APIClient {
  /** Shared by login and signup — both return `{token, user}` or a 4xx detail. */
  private static async authPost(path: string, body: object): Promise<AuthUser> {
    const res = await apiFetch(`${API_BASE_URL}/api/auth/${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || 'Something went wrong. Try again.');
    auth.user = data.user;   // the session itself arrived as a cookie
    return data.user;
  }

  static signUp(email: string, password: string, name: string): Promise<AuthUser> {
    return APIClient.authPost('signup', { email, password, name });
  }

  static logIn(email: string, password: string): Promise<AuthUser> {
    return APIClient.authPost('login', { email, password });
  }

  /** The signed-in user, or null when the token is missing/expired/invalid. */
  static async me(): Promise<AuthUser | null> {
    const res = await apiFetch(`${API_BASE_URL}/api/auth/me`);
    if (!res.ok) return null;   // no session cookie, or it expired
    auth.user = await res.json();
    return auth.user;
  }

  static async fetchJobs(): Promise<Job[]> {
    const res = await apiFetch(`${API_BASE_URL}/api/jobs`);
    if (!res.ok) throw new Error('Failed to fetch jobs');
    return res.json();
  }

  static async uploadDocument(file: File): Promise<UploadResult> {
    const form = new FormData();
    form.append('file', file);
    const res = await apiFetch(`${API_BASE_URL}/api/uploads`, {
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
    const res = await apiFetch(`${API_BASE_URL}/api/jobs`, {
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
    const res = await apiFetch(`${API_BASE_URL}/api/jobs/${id}`);
    if (!res.ok) throw new Error('Failed to get job');
    return res.json();
  }

  static async getJobEvents(id: string): Promise<AgentEvent[]> {
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/jobs/${id}/events`);
      if (!res.ok) return [];
      const data = await res.json();
      return data.events || [];
    } catch {
      return [];
    }
  }

  static async deleteJob(id: string): Promise<void> {
    const res = await apiFetch(`${API_BASE_URL}/api/jobs/${id}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error('Failed to delete job');
  }

  static async approvePlan(id: string): Promise<void> {
    const res = await apiFetch(`${API_BASE_URL}/api/jobs/${id}/approve-plan`);
    if (!res.ok) throw new Error('Failed to approve plan');
  }

  static async revisePlan(id: string, feedback: string): Promise<void> {
    const res = await apiFetch(`${API_BASE_URL}/api/jobs/${id}/revise-plan`, {
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
    const res = await apiFetch(`${API_BASE_URL}/api/jobs/${id}/update-plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(plan),
    });
    if (!res.ok) throw new Error('Failed to update plan');
  }

  /** Save the edited article so exports and re-run media tasks use it. */
  static async saveBlog(id: string, content: string): Promise<void> {
    const res = await apiFetch(`${API_BASE_URL}/api/jobs/${id}/blog`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
    if (!res.ok) {
      const detail = (await res.json().catch(() => null))?.detail;
      throw new Error(typeof detail === 'string' ? detail : 'Failed to save article');
    }
  }

  static async triggerImages(id: string): Promise<void> {
    const res = await apiFetch(`${API_BASE_URL}/api/jobs/${id}/generate-images`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to trigger images');
  }

  static async triggerVideo(id: string): Promise<void> {
    const res = await apiFetch(`${API_BASE_URL}/api/jobs/${id}/generate-video`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to trigger video');
  }

  static async triggerPodcast(id: string): Promise<void> {
    const res = await apiFetch(`${API_BASE_URL}/api/jobs/${id}/generate-podcast`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to trigger podcast');
  }

  static async triggerSocial(id: string): Promise<void> {
    const res = await apiFetch(`${API_BASE_URL}/api/jobs/${id}/generate-social`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to trigger social');
  }

  static async triggerQA(id: string): Promise<void> {
    const res = await apiFetch(`${API_BASE_URL}/api/jobs/${id}/run-qa`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to trigger QA');
  }

  static async runDeepEval(id: string): Promise<void> {
    const res = await apiFetch(`${API_BASE_URL}/api/jobs/${id}/run-deepeval`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to trigger deepeval academic audit');
  }

  static async resumeJob(id: string): Promise<void> {
    const res = await apiFetch(`${API_BASE_URL}/api/jobs/${id}/resume`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to resume job');
  }

  static getFileUrl(jobId: string, filename: string): string {
    return withApiKey(`${API_BASE_URL}/api/files/${jobId}/${filename}`);
  }

  static getExportUrl(jobId: string, format: 'pdf' | 'docx' | 'html'): string {
    return withApiKey(`${API_BASE_URL}/api/jobs/${jobId}/export/${format}`);
  }
}

export class WebSocketClient {
  private ws: (WebSocket & { isClosedByClient?: boolean }) | null = null;
  private currentJobId: string | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectTimer: any = null;

  connect(jobId: string, onMessage: (event: AgentEvent) => void, onDisconnect?: () => void) {
    // If a socket is already open or opening, mark it as intentionally closed before closing
    if (this.ws) {
      this.ws.isClosedByClient = true;
      this.ws.close();
      this.ws = null;
    }
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    this.currentJobId = jobId;
    const socket = new WebSocket(withApiKey(`${WS_BASE_URL}/ws/${jobId}`)) as (WebSocket & { isClosedByClient?: boolean });
    socket.isClosedByClient = false;
    this.ws = socket;

    socket.onopen = () => {
      this.reconnectAttempts = 0;
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'ping') return; // Ignore keepalive pings
        onMessage(data as AgentEvent);
      } catch (err) {
        console.error('Failed to parse WebSocket message', err);
      }
    };

    socket.onerror = (err) => {
      console.error('WebSocket error:', err);
    };

    socket.onclose = (event: CloseEvent) => {
      console.log(`WebSocket disconnected for job ${jobId} (code=${event.code})`);
      if (onDisconnect) onDisconnect();

      // Only attempt reconnection if socket was dropped unexpectedly (NOT clean close 1000/1001)
      const isCleanClose = event.wasClean || event.code === 1000 || event.code === 1001;

      if (!socket.isClosedByClient && !isCleanClose && this.ws === socket && this.reconnectAttempts < this.maxReconnectAttempts) {
        const delay = Math.pow(2, this.reconnectAttempts) * 1000;
        console.log(`Attempting WebSocket reconnection in ${delay}ms for job ${jobId}...`);
        this.reconnectTimer = setTimeout(() => {
          this.reconnectAttempts++;
          if (this.currentJobId === jobId) {
            this.connect(jobId, onMessage, onDisconnect);
          }
        }, delay);
      }
    };
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.isClosedByClient = true;
      this.ws.close();
      this.ws = null;
    }
    this.currentJobId = null;
  }
}
