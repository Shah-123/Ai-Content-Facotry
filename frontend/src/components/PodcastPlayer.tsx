import React, { useState, useRef, useEffect } from 'react';
import { Download, Play, Pause, Volume2, VolumeX } from 'lucide-react';
import { APIClient, Job } from '../api';

// Pre-computed waveform heights — varied to look like a real audio fingerprint
const BAR_HEIGHTS = [
  22, 38, 55, 72, 88, 62, 45, 78, 92, 58,
  40, 68, 84, 50, 35, 72, 90, 60, 42, 76,
  88, 52, 38, 66, 80, 48, 30, 70, 86, 54,
  44, 74, 92, 62, 36, 80, 95, 58, 40, 68,
];

interface PodcastPlayerProps {
  currentJob: Job;
}

function formatTime(seconds: number): string {
  if (!seconds || isNaN(seconds) || !isFinite(seconds)) return '0:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function PodcastPlayer({ currentJob }: PodcastPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const waveformRef = useRef<HTMLDivElement>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isMuted, setIsMuted] = useState(false);

  const isWav = currentJob.podcast_file?.endsWith('.wav');
  const fileType = isWav ? 'WAV' : 'MP3';
  const fileUrl = APIClient.getFileUrl(currentJob.id, currentJob.podcast_file!);
  const progress = duration > 0 ? currentTime / duration : 0;

  const hostLabel = isWav
    ? 'AI Hosted 2-Speaker Podcast (Puck & Aoede)'
    : 'AI Hosted Podcast';

  // ── Audio event handlers ──────────────────────────────────────────────────
  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play().catch(() => {});
    }
  };

  const toggleMute = () => {
    if (!audioRef.current) return;
    audioRef.current.muted = !isMuted;
    setIsMuted(v => !v);
  };

  // Seek on waveform click
  const handleWaveformClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!audioRef.current || !duration || !waveformRef.current) return;
    const rect = waveformRef.current.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    audioRef.current.currentTime = ratio * duration;
  };

  // Keyboard seek (APG slider): arrows 5 s, PageUp/Down 30 s, Home/End jump.
  const SEEK_STEP: Record<string, number> = { ArrowRight: 5, ArrowUp: 5, ArrowLeft: -5, ArrowDown: -5, PageUp: 30, PageDown: -30 };
  const handleWaveformKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const step = SEEK_STEP[e.key];
    if (step === undefined && e.key !== 'Home' && e.key !== 'End') return;
    e.preventDefault();
    const el = audioRef.current;
    if (!el || !duration) return;
    el.currentTime = e.key === 'Home' ? 0 : e.key === 'End' ? duration
      : Math.max(0, Math.min(duration, el.currentTime + step));
  };

  // Keep duration in sync after metadata loads
  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    if (el.readyState >= 1 && el.duration && isFinite(el.duration)) {
      setDuration(el.duration);
    }
  }, []);

  return (
    <div className="mx-auto max-w-3xl">
      <div className="card p-6">
        {/* Title + metadata */}
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h3 className="text-heading text-base-50 truncate">{currentJob.topic}</h3>
            <p className="mt-1 text-ui text-base-400 truncate">{hostLabel}</p>
          </div>
          <p className="shrink-0 font-mono text-xs text-base-500 tabular-nums">
            {fileType}{duration > 0 ? ` · ${formatTime(duration)}` : ''}
          </p>
        </div>

        {/* Controls row */}
        <div className="mt-6 flex items-center gap-4">
          <button
            type="button"
            onClick={togglePlay}
            className="grid size-12 shrink-0 place-items-center rounded-full bg-accent-500 text-on-accent shadow-[inset_0_1px_0_rgba(255,255,255,.25)] hover:bg-[color-mix(in_oklab,var(--color-accent-500),white_12%)] transition-colors"
            aria-label={isPlaying ? 'Pause' : 'Play'}
          >
            <Pause aria-hidden="true" className={`size-5 [grid-area:1/1] transition-opacity duration-120 ${isPlaying ? 'opacity-100' : 'opacity-0'}`} />
            <Play aria-hidden="true" className={`size-5 ml-0.5 [grid-area:1/1] transition-opacity duration-120 ${isPlaying ? 'opacity-0' : 'opacity-100'}`} />
          </button>

          {/* Waveform (static) + time */}
          <div className="flex-1 min-w-0">
            <div
              ref={waveformRef}
              className="relative flex h-12 items-center justify-between gap-0.5 cursor-pointer select-none rounded-sm"
              onClick={handleWaveformClick}
              onKeyDown={handleWaveformKeyDown}
              role="slider"
              tabIndex={0}
              aria-disabled={!duration}
              aria-label="Seek"
              aria-valuemin={0}
              aria-valuemax={Math.round(duration)}
              aria-valuenow={Math.round(currentTime)}
              aria-valuetext={`${formatTime(currentTime)} of ${formatTime(duration)}`}
            >
              {BAR_HEIGHTS.map((h, i) => (
                <span
                  key={i}
                  className={`w-0.5 rounded-full ${i / BAR_HEIGHTS.length < progress ? 'bg-indicator' : 'bg-line-strong'}`}
                  style={{ height: `${h}%` }}
                />
              ))}
              {duration > 0 && (
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-y-0 w-px bg-base-50"
                  style={{ left: `${progress * 100}%` }}
                />
              )}
            </div>

            <p className="mt-2 font-mono text-xs text-base-400 tabular-nums">
              {formatTime(currentTime)} / {formatTime(duration)}
            </p>
          </div>

          <button
            type="button"
            onClick={toggleMute}
            className="btn btn-ghost btn-icon btn-sm shrink-0"
            aria-label={isMuted ? 'Unmute' : 'Mute'}
            title={isMuted ? 'Unmute' : 'Mute'}
          >
            {isMuted ? <VolumeX /> : <Volume2 />}
          </button>
        </div>

        <div className="mt-6 flex justify-end border-t border-line pt-4">
          <a href={fileUrl} download target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">
            <Download />
            Download {fileType}
          </a>
        </div>
      </div>

      {/* ── Hidden audio element ── */}
      <audio
        ref={audioRef}
        src={fileUrl}
        preload="metadata"
        onTimeUpdate={() => audioRef.current && setCurrentTime(audioRef.current.currentTime)}
        onLoadedMetadata={() => audioRef.current && setDuration(audioRef.current.duration)}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onEnded={() => { setIsPlaying(false); setCurrentTime(0); }}
      />
    </div>
  );
}
