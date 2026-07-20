import React, { useState, useRef, useEffect } from 'react';
import { motion } from 'motion/react';
import { Download, Play, Pause, Volume2, VolumeX, CheckCircle2 } from 'lucide-react';
import { APIClient, Job } from '../api';

// Pre-computed waveform heights — varied to look like a real audio fingerprint
const BAR_HEIGHTS = [
  22, 38, 55, 72, 88, 62, 45, 78, 92, 58,
  40, 68, 84, 50, 35, 72, 90, 60, 42, 76,
  88, 52, 38, 66, 80, 48, 30, 70, 86, 54,
  44, 74, 92, 62, 36, 80, 95, 58, 40, 68,
];

// Animation durations per bar (deterministic — no Math.random in render)
const BAR_DURATIONS = [
  0.45, 0.60, 0.50, 0.70, 0.42, 0.55, 0.65, 0.48, 0.58, 0.40,
  0.72, 0.50, 0.44, 0.62, 0.56, 0.40, 0.70, 0.52, 0.60, 0.46,
  0.55, 0.65, 0.42, 0.70, 0.50, 0.60, 0.44, 0.55, 0.68, 0.48,
  0.58, 0.40, 0.72, 0.52, 0.44, 0.62, 0.56, 0.42, 0.68, 0.50,
];

interface PodcastPlayerProps {
  currentJob: Job;
}

function formatTime(seconds: number): string {
  if (!seconds || isNaN(seconds) || !isFinite(seconds)) return '00:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
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

  // Keep duration in sync after metadata loads
  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    if (el.readyState >= 1 && el.duration && isFinite(el.duration)) {
      setDuration(el.duration);
    }
  }, []);

  return (
    <div className="max-w-3xl mx-auto">
      {/* ── Header ── */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h2 className="text-2xl font-bold text-base-50 tracking-tight">Podcast Generation</h2>
            <span className="flex items-center gap-1.5 text-[11px] font-semibold text-emerald-400 bg-emerald-400/10 border border-emerald-400/25 px-2.5 py-1 rounded-full">
              <CheckCircle2 className="w-3 h-3" />
              Ready
            </span>
          </div>
          <p className="text-sm text-base-400">Transform your blog into an engaging audio experience</p>
        </div>

        {/* Duration + format metadata */}
        <div className="text-right shrink-0 ml-6">
          {duration > 0 && (
            <p className="text-lg font-semibold text-base-50 tabular-nums">
              {formatTime(duration)} <span className="text-sm font-normal text-base-400">min</span>
            </p>
          )}
          <p className="text-sm text-base-400 mt-0.5">{fileType} · Audio</p>
        </div>
      </div>

      {/* ── Player Card ──
          Uses CSS custom properties so the card bg, button, and bars all
          adapt automatically when `data-theme` toggles on <html>.
          See index.css → .podcast-player-card for the light-mode overrides.
      ── */}
      <div className="podcast-player-card rounded-2xl p-7 border border-white/6 shadow-[0_24px_64px_rgba(0,0,0,0.4)] relative overflow-hidden">
        {/* Ambient accent glow — uses the theme accent colour */}
        <div
          className="absolute -top-8 -right-8 w-40 h-40 rounded-full pointer-events-none"
          style={{ background: 'radial-gradient(circle, var(--color-accent-glow) 0%, transparent 70%)' }}
        />

        {/* Episode title */}
        <h3 className="text-sm font-semibold text-base-100 mb-6 truncate pr-4">
          {currentJob.topic} — Episode Transcript
        </h3>

        {/* Controls row */}
        <div className="flex items-center gap-5">
          {/* ── Play / Pause button — uses accent CSS vars ── */}
          <motion.button
            onClick={togglePlay}
            whileTap={{ scale: 0.93 }}
            className="podcast-play-btn w-14 h-14 rounded-full flex items-center justify-center shrink-0 transition-shadow duration-200"
            style={{
              /* Shadow intensity changes when playing */
              boxShadow: isPlaying
                ? '0 0 0 4px var(--podcast-play-ring), 0 0 36px var(--podcast-play-glow-strong)'
                : '0 0 24px var(--podcast-play-glow)',
            }}
            aria-label={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying
              ? <Pause className="w-5 h-5 text-white" />
              : <Play className="w-5 h-5 text-white ml-0.5" />
            }
          </motion.button>

          {/* ── Waveform + time ── */}
          <div className="flex-1 min-w-0">
            {/* Bars */}
            <div
              ref={waveformRef}
              className="flex items-end gap-[3px] h-12 cursor-pointer select-none"
              onClick={handleWaveformClick}
              role="progressbar"
              aria-valuenow={Math.round(progress * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              {BAR_HEIGHTS.map((h, i) => {
                const barFraction = i / BAR_HEIGHTS.length;
                const isPast = barFraction < progress;

                return (
                  <motion.div
                    key={i}
                    className="flex-1 rounded-sm"
                    style={{
                      height: `${h}%`,
                      originY: 1,
                      /* Active bars use the theme accent; inactive use a neutral tint */
                      backgroundColor: isPast
                        ? 'var(--color-accent-500)'
                        : 'var(--podcast-bar-inactive)',
                      transition: 'background-color 0.15s ease',
                    }}
                    animate={
                      isPlaying && isPast
                        ? { scaleY: [1, 1 + (h / 150), 0.65, 1.15, 0.85, 1] }
                        : { scaleY: 1 }
                    }
                    transition={{
                      duration: BAR_DURATIONS[i],
                      repeat: Infinity,
                      ease: 'easeInOut',
                      delay: (i % 8) * 0.06,
                    }}
                  />
                );
              })}
            </div>

            {/* Time labels */}
            <div className="flex justify-between text-[11px] font-mono text-base-500 mt-2 tabular-nums">
              <span>{formatTime(currentTime)}</span>
              <span>{formatTime(duration)}</span>
            </div>
          </div>

          {/* ── Mute / Unmute ── */}
          <button
            onClick={toggleMute}
            className="text-base-500 hover:text-base-200 transition-colors shrink-0 p-1"
            aria-label={isMuted ? 'Unmute' : 'Mute'}
          >
            {isMuted
              ? <VolumeX className="w-5 h-5" />
              : <Volume2 className="w-5 h-5" />
            }
          </button>
        </div>

        {/* Host label */}
        <p className="text-[11px] text-base-600 mt-5 truncate">{hostLabel}</p>
      </div>

      {/* ── Download button — inherits btn-primary which already themes ── */}
      <div className="flex justify-end mt-5">
        <a
          href={fileUrl}
          download
          target="_blank"
          rel="noreferrer"
          className="btn-primary px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2"
        >
          <Download className="w-4 h-4" />
          Download {fileType}
        </a>
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
