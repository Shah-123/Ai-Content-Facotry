import { useEffect, useRef, useState } from 'react';
import { APIClient, AgentEvent, Job } from '../api';
import { toast } from '../components/Toast';

export type JobAction = 'qa' | 'podcast' | 'video' | 'social' | 'images' | 'deepeval';

type UseJobActionsArgs = {
  currentJob: Job | null;
  events: AgentEvent[];
  refreshJob: () => void;
  reconnectWS?: (jobId: string) => void;
};

const agentForTask = (task: JobAction) => (task === 'social' ? 'campaign' : task);

export function useJobActions({ currentJob, events, refreshJob, reconnectWS }: UseJobActionsArgs) {
  const [triggering, setTriggering] = useState<Record<string, boolean>>({});
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isTaskRunning = (startAgentName: string) => {
    const triggerKey = startAgentName === 'campaign' ? 'social' : startAgentName;
    if (triggering[triggerKey]) return true;

    const lastStartIdx = findLastStart(events, startAgentName);
    if (lastStartIdx === -1) return false;

    return !events.slice(lastStartIdx + 1).some(event =>
      event.status === 'completed' || event.status === 'error'
    );
  };

  const getLastTaskError = (startAgentName: string) => {
    const lastStartIdx = findLastStart(events, startAgentName);
    if (lastStartIdx === -1) return null;
    return events.slice(lastStartIdx + 1).find(event => event.status === 'error')?.message ?? null;
  };

  const getCurrentRunEvents = (task: JobAction) => {
    const startAgentName = agentForTask(task);
    const lastStartIdx = findLastStart(events, startAgentName);
    const runEvents = lastStartIdx === -1 ? events : events.slice(lastStartIdx);

    return runEvents.filter(event => {
      if (task === 'video') return event.agent_name === 'video';
      if (task === 'podcast') return event.agent_name === 'podcast' || event.agent_name === 'podcast_generator';
      if (task === 'social') return event.agent_name === 'campaign' || event.agent_name === 'campaign_generator';
      return task === 'images' && event.agent_name === 'images';
    });
  };

  useEffect(() => {
    if (!currentJob) return;

    setTriggering(previous => {
      const next = { ...previous };
      let changed = false;
      if (previous.social && (currentJob.social_linkedin || currentJob.social_twitter)) { next.social = false; changed = true; }
      if (previous.video && currentJob.video_file) { next.video = false; changed = true; }
      if (previous.podcast && currentJob.podcast_file) { next.podcast = false; changed = true; }
      if (previous.qa && currentJob.qa_score != null) { next.qa = false; changed = true; }
      if (previous.images && currentJob.final_content) { next.images = false; changed = true; }
      if (previous.deepeval && currentJob.deepeval_scores) { next.deepeval = false; changed = true; }
      return changed ? next : previous;
    });
  }, [currentJob]);

  useEffect(() => {
    const imagesCompleted = isTaskComplete(events, 'images');
    if (imagesCompleted && triggering.images) {
      setTriggering(previous => ({ ...previous, images: false }));
    }
  }, [events, triggering.images]);

  useEffect(() => {
    if (Object.values(triggering).some(Boolean) || !pollRef.current) return;
    clearInterval(pollRef.current);
    pollRef.current = null;
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, [triggering]);

  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
  }, []);

  const handleTrigger = async (task: JobAction) => {
    if (!currentJob) return;
    setTriggering(previous => ({ ...previous, [task]: true }));

    try {
      reconnectWS?.(currentJob.id);
      await triggerTask(task, currentJob.id);

      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(refreshJob, 3000);

      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      const safetyMs = task === 'podcast' ? 15 * 60 * 1000 : 5 * 60 * 1000;
      timeoutRef.current = setTimeout(() => {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
        setTriggering(previous => ({ ...previous, [task]: false }));
      }, safetyMs);
    } catch (error) {
      toast.fromError(error, `Could not start the ${task} task.`);
      setTriggering(previous => ({ ...previous, [task]: false }));
    }
  };

  return { triggering, getCurrentRunEvents, getLastTaskError, handleTrigger, isTaskRunning };
}

function findLastStart(events: AgentEvent[], agentName: string) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (events[index].agent_name === agentName && events[index].status === 'started') return index;
  }
  return -1;
}

function isTaskComplete(events: AgentEvent[], agentName: string) {
  const lastStartIdx = findLastStart(events, agentName);
  return lastStartIdx !== -1 && events.slice(lastStartIdx + 1).some(event => event.status === 'completed');
}

function triggerTask(task: JobAction, jobId: string) {
  switch (task) {
    case 'qa': return APIClient.triggerQA(jobId);
    case 'podcast': return APIClient.triggerPodcast(jobId);
    case 'video': return APIClient.triggerVideo(jobId);
    case 'social': return APIClient.triggerSocial(jobId);
    case 'images': return APIClient.triggerImages(jobId);
    case 'deepeval': return APIClient.runDeepEval(jobId);
  }
}
