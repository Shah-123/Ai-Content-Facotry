import React from 'react';
import {
  Podcast, Share2, Download, CheckCircle, Clock, Settings,
  RefreshCw, CheckCircle2, Copy, UserRoundCog, Image as ImageIcon
} from 'lucide-react';
import { APIClient, Job } from './api';

type ViewState = 'chat' | 'content' | 'media';

export function MediaView({ navTo, currentJob }: { navTo: (v: ViewState) => void, currentJob: Job | null }) {
  return (
    <main className="flex-1 flex flex-col h-full overflow-y-auto px-6 md:px-12 pb-24 relative pt-4">
      <header className="mb-8 md:mb-10 border-b border-white/[0.04] pb-4 fade-in">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-6">
          <div>
            <h2 className="text-2xl font-bold text-base-50 tracking-tight mb-1.5 flex items-center gap-3">
              <Podcast className="text-accent-400 w-7 h-7" /> Media Generation
            </h2>
            <p className="text-base-400 text-sm font-medium flex items-center gap-2">
              <span className="text-accent-400">Project:</span> {currentJob?.topic || 'No topic selected'}
            </p>
          </div>
          <span className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold flex items-center gap-1.5 border ${currentJob?.status === 'completed' ? 'bg-signal-success-dim text-signal-success border-signal-success/20' : 'bg-accent-glow text-accent-400 border-accent-500/20'}`}>
            {currentJob?.status === 'running' || currentJob?.status === 'pending' || currentJob?.status === 'awaiting_approval' ? (
              <><RefreshCw className="w-3 h-3 animate-spin" /> Processing...</>
            ) : currentJob?.status === 'completed' ? (
              <><CheckCircle2 className="w-3 h-3" /> Completed</>
            ) : currentJob?.status === 'failed' ? (
              <><Settings className="w-3 h-3" /> Failed</>
            ) : 'Idle'}
          </span>
        </div>
        <div className="flex gap-2 text-sm font-medium overflow-x-auto pb-2">
          <button onClick={() => navTo('content')} className="px-3 py-1.5 rounded-lg text-base-400 hover:text-base-200 hover:bg-white/[0.03] transition-all text-[13px]">Blog</button>
          <button className="px-3 py-1.5 rounded-lg text-accent-400 bg-accent-500/10 font-semibold text-[13px] flex items-center gap-1.5">
            Podcast {currentJob?.podcast_file && <CheckCircle2 className="w-3.5 h-3.5 text-signal-success" />}
          </button>
          <button className="px-3 py-1.5 rounded-lg text-base-400 hover:text-base-200 hover:bg-white/[0.03] transition-all text-[13px] flex items-center gap-1.5">
            Video {currentJob?.video_file ? <CheckCircle2 className="w-3.5 h-3.5 text-signal-success" /> : <span className="w-1.5 h-1.5 rounded-full bg-accent-500 status-pulse"></span>}
          </button>
          <button className="px-3 py-1.5 rounded-lg text-base-400 hover:text-base-200 hover:bg-white/[0.03] transition-all text-[13px]">Images</button>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] xl:grid-cols-[1fr_320px] gap-10 items-start stagger">
        <div className="flex flex-col gap-10">
          {/* PODCAST */}
          <section className="glass-panel p-6 md:p-8 rounded-2xl relative overflow-hidden group">
            <div className="absolute -top-10 -right-10 w-40 h-40 bg-accent-500/5 rounded-full blur-3xl group-hover:bg-accent-500/10 transition-all duration-700"></div>
            <div className="flex justify-between items-start mb-6 relative z-10">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <h3 className="text-xl font-bold text-base-50">Podcast Generation</h3>
                  <span className={`px-2 py-0.5 rounded-lg text-[11px] font-semibold flex items-center gap-1 ${currentJob?.podcast_file ? 'bg-signal-success-dim text-signal-success border border-signal-success/20' : 'bg-base-800 text-base-400 border border-white/[0.04]'}`}>
                    {currentJob?.podcast_file ? <CheckCircle className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
                    {currentJob?.podcast_file ? 'Ready' : 'Pending'}
                  </span>
                </div>
                <p className="text-base-400 text-sm">Transform your blog into an engaging audio experience</p>
              </div>
            </div>
            {currentJob?.podcast_file ? (
              <div className="bg-base-900 border border-white/[0.04] rounded-xl p-4 md:p-6 relative z-10">
                <h4 className="text-sm font-medium text-accent-400 mb-4">{currentJob.topic} — Podcast</h4>
                <audio controls className="w-full">
                  <source 
                    src={APIClient.getFileUrl(currentJob.id, currentJob.podcast_file)} 
                    type={currentJob.podcast_file.endsWith('.wav') ? 'audio/wav' : 'audio/mpeg'} 
                  />
                </audio>
              </div>
            ) : (
              <div className="bg-base-900 border border-dashed border-white/[0.06] rounded-xl p-8 flex items-center justify-center relative z-10">
                <p className="text-base-500 text-sm">Audio will appear here once generated...</p>
              </div>
            )}
            <div className="mt-6 flex flex-col md:flex-row justify-between items-start md:items-end gap-4 relative z-10">
              <div className="text-xs text-base-500 flex items-center gap-2">
                <UserRoundCog className="w-4 h-4" /> 
                {currentJob?.podcast_file?.endsWith('.wav') 
                  ? 'Voice: Puck & Aoede (2-Speaker) · Gemini Audio' 
                  : 'Voice: alloy · OpenAI TTS'}
              </div>
              {currentJob?.podcast_file && (
                <a href={APIClient.getFileUrl(currentJob.id, currentJob.podcast_file)} download target="_blank" rel="noreferrer"
                  className="btn-primary px-5 py-2 rounded-xl text-sm font-semibold flex items-center gap-2">
                  <Download className="w-4 h-4" /> 
                  {currentJob.podcast_file.endsWith('.wav') ? 'Download WAV' : 'Download MP3'}
                </a>
              )}
            </div>
          </section>

          {/* VIDEO */}
          <section className="glass-panel p-6 md:p-8 rounded-2xl">
            <div className="flex flex-wrap justify-between items-center gap-4 mb-6">
              <div className="flex items-center gap-3">
                <h3 className="text-xl font-bold text-base-50">Video Generation</h3>
                <span className={`px-2 py-0.5 rounded-lg text-[11px] font-semibold flex items-center gap-1 ${currentJob?.video_file ? 'bg-signal-success-dim text-signal-success border border-signal-success/20' : 'bg-accent-glow text-accent-400 border border-accent-500/20'}`}>
                  {currentJob?.video_file ? <CheckCircle className="w-3 h-3" /> : <Settings className="w-3 h-3 animate-spin" />}
                  {currentJob?.video_file ? 'Ready' : (currentJob?.status === 'running' ? 'Generating...' : 'Pending')}
                </span>
              </div>
            </div>
            {currentJob?.video_file ? (
              <div className="bg-black rounded-xl overflow-hidden aspect-video border border-white/[0.06]">
                <video src={APIClient.getFileUrl(currentJob.id, currentJob.video_file)} controls className="w-full h-full object-contain"></video>
              </div>
            ) : currentJob?.status === 'running' ? (
              <div className="space-y-3 pt-4 border-t border-white/[0.04]">
                <div className="flex items-center gap-3 opacity-50"><CheckCircle className="text-accent-400 w-4 h-4" /><span className="text-sm text-base-300 line-through">Script generation</span></div>
                <div className="flex items-center gap-3 bg-base-800 p-3 rounded-xl border border-white/[0.04]"><RefreshCw className="text-accent-400 w-4 h-4 animate-spin" /><span className="text-sm font-semibold text-accent-400">Compiling video...</span></div>
              </div>
            ) : (
              <div className="bg-base-900 border border-dashed border-white/[0.06] rounded-xl p-8 flex items-center justify-center">
                <p className="text-base-500 text-sm">Video will appear here once generated...</p>
              </div>
            )}
            {currentJob?.video_file && (
              <div className="mt-6 flex justify-end border-t border-white/[0.04] pt-5">
                <a href={APIClient.getFileUrl(currentJob.id, currentJob.video_file)} download target="_blank" rel="noreferrer"
                  className="btn-primary px-5 py-2 rounded-xl text-sm font-semibold flex items-center gap-2">
                  <Download className="w-4 h-4" /> Download MP4
                </a>
              </div>
            )}
          </section>

          {/* IMAGES */}
          <section>
            <h3 className="text-xl font-bold text-base-50 mb-4 flex items-center gap-2"><ImageIcon className="w-5 h-5 text-accent-400" /> Generated Images</h3>
            <div className="text-sm text-base-400 bg-base-850 p-4 rounded-xl border border-white/[0.04]">
              Images are stored in the project folder and embedded in the Draft viewer.
            </div>
          </section>
        </div>

        {/* SOCIAL */}
        <aside className="lg:sticky lg:top-8 flex flex-col gap-4 pb-12">
          <div className="flex items-center gap-2 mb-1"><Share2 className="w-5 h-5 text-base-100" /><h3 className="text-base font-bold text-base-100 tracking-tight">Social Media</h3></div>
          <div className="glass-pill p-5 rounded-xl border-l-2 border-l-blue-500 hover:bg-white/[0.03] transition-colors">
            <div className="flex items-center gap-2 text-sm font-semibold text-base-100 mb-3">
              <svg className="w-4 h-4 fill-current text-[#0a66c2]" viewBox="0 0 24 24"><path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"></path></svg>
              LinkedIn Post
            </div>
            <p className="text-xs text-base-400 leading-relaxed mb-4 whitespace-pre-wrap">{currentJob?.social_linkedin || "LinkedIn post will be generated..."}</p>
            {currentJob?.social_linkedin && (
              <button onClick={() => navigator.clipboard.writeText(currentJob.social_linkedin!)}
                className="w-full py-2 bg-white/[0.03] hover:bg-white/[0.06] rounded-xl text-xs font-medium text-base-200 flex items-center justify-center gap-2 border border-white/[0.06] transition-colors group">
                <Copy className="w-3.5 h-3.5 group-hover:scale-110 transition-transform" /> Copy Text
              </button>
            )}
          </div>
          <div className="glass-pill p-5 rounded-xl border-l-2 border-l-base-400 hover:bg-white/[0.03] transition-colors">
            <div className="flex items-center gap-2 text-sm font-semibold text-base-100 mb-3">
              <svg className="w-4 h-4 fill-current text-base-200" viewBox="0 0 24 24"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.008 4.09H5.078z"></path></svg>
              X Post / Tweet
            </div>
            <p className="text-xs text-base-400 leading-relaxed mb-4 whitespace-pre-wrap">{currentJob?.social_twitter || "X post will be generated..."}</p>
            {currentJob?.social_twitter && (
              <button onClick={() => navigator.clipboard.writeText(currentJob.social_twitter!)}
                className="w-full py-2 bg-white/[0.03] hover:bg-white/[0.06] rounded-xl text-xs font-medium text-base-200 flex items-center justify-center gap-2 border border-white/[0.06] transition-colors group">
                <Copy className="w-3.5 h-3.5 group-hover:scale-110 transition-transform" /> Copy Post
              </button>
            )}
          </div>
        </aside>
      </div>
    </main>
  );
}
