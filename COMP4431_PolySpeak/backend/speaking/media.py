import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import time

from .avatar import AvatarRenderer
from .speech import SpeechService


class MediaManager:
    def __init__(self, folder: Path, speech: SpeechService, renderer: AvatarRenderer):
        folder.mkdir(parents=True, exist_ok=True)
        self.folder = folder
        self.speech = speech
        self.renderer = renderer
        self.jobs: dict[str, dict] = {}
        self.tasks: set[asyncio.Task] = set()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="avatar-render")

    def submit(self, text: str, language: str):
        job_id = hashlib.sha256((language + "|" + self.renderer.cache_key + "|" + text).encode()).hexdigest()[:32]
        target = self.folder / f"{job_id}.mp4"
        if job_id in self.jobs and self.jobs[job_id]["status"] in ("queued", "speech", "rendering", "ready"):
            return self.jobs[job_id].copy()
        if target.exists() and target.stat().st_size > 1000:
            self.jobs[job_id] = {"id": job_id, "status": "ready", "progress": 100, "video_url": f"/media/{job_id}.mp4", "cached": True}
        else:
            self.jobs[job_id] = {"id": job_id, "status": "queued", "progress": 0}
            task = asyncio.create_task(self.generate(job_id, text, language))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        return self.jobs[job_id].copy()

    async def generate(self, job_id: str, text: str, language: str):
        job = self.jobs[job_id]
        start = time.perf_counter()
        audio = self.folder / f"{job_id}.audio"
        target = self.folder / f"{job_id}.mp4"
        try:
            job["status"] = "speech"
            job["tts_provider"] = await self.speech.synthesize(text, language, audio)
            job["audio_url"] = f"/media/{job_id}.audio"
            job["status"] = "rendering"
            loop = asyncio.get_running_loop()
            def update(value):
                loop.call_soon_threadsafe(job.update, {"progress": value})
            result = await loop.run_in_executor(self.executor, self.renderer.render, audio, target, update)
            job.update(result)
            job.update(status="ready", progress=100, video_url=f"/media/{job_id}.mp4", generation_seconds=round(time.perf_counter()-start, 2))
        except Exception as exc:
            job.update(status="failed", error=str(exc)[:400])
            target.unlink(missing_ok=True)

