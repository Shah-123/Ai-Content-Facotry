import os
import sys
import json
import shutil
import tempfile
from pathlib import Path

# Add parent directory to sys.path so we can import from backend
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from db import create_job, get_job, update_job, delete_job
from api import get_job_healed

def test_media_healing():
    print("--- Starting Media Healing Test ---")
    
    # 1. Create a temporary directory structure for the mock blog
    temp_dir = tempfile.mkdtemp()
    blog_folder = Path(temp_dir)
    print(f"Created temp blog folder: {blog_folder}")
    
    # Create subfolders
    (blog_folder / "audio").mkdir(parents=True, exist_ok=True)
    (blog_folder / "video").mkdir(parents=True, exist_ok=True)
    (blog_folder / "metadata").mkdir(parents=True, exist_ok=True)
    
    # Write a starting metadata.json
    meta_path = blog_folder / "metadata" / "metadata.json"
    initial_meta = {
        "topic": "Test Topic",
        "file_paths": {
            "blog": "content/blog.md",
            "podcast": str(blog_folder / "audio" / "podcast.wav"),
            "video": str(blog_folder / "video" / "short.mp4")
        }
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(initial_meta, f, indent=2)
        
    # Create the job in SQLite
    job = create_job("Test Topic", tone="professional")
    job_id = job["id"]
    print(f"Created test job ID: {job_id}")
    
    # Update job with folders and invalid file references (files don't exist yet)
    update_job(
        job_id,
        blog_folder=str(blog_folder),
        blog_file="content/blog.md",
        podcast_file="audio/podcast.wav",
        video_file="video/short.mp4"
    )
    
    # Fetch job directly from DB (should still have the invalid paths)
    direct_job = get_job(job_id)
    assert direct_job["podcast_file"] == "audio/podcast.wav"
    assert direct_job["video_file"] == "video/short.mp4"
    print("Assertion 1 Passed: Direct DB query returns raw paths before healing.")
    
    # Fetch job healed (files don't exist yet, should clear DB and metadata.json)
    healed_job = get_job_healed(job_id)
    assert healed_job["podcast_file"] is None
    assert healed_job["video_file"] is None
    print("Assertion 2 Passed: get_job_healed cleared non-existent paths from DB.")
    
    # Verify metadata.json was updated
    with open(meta_path, "r", encoding="utf-8") as f:
        updated_meta = json.load(f)
    assert updated_meta["file_paths"]["podcast"] is None
    assert updated_meta["file_paths"]["video"] is None
    print("Assertion 3 Passed: metadata.json paths were surgically cleared.")
    
    # 2. Write empty (0-byte) files and set DB paths again
    podcast_file = blog_folder / "audio" / "podcast.wav"
    video_file = blog_folder / "video" / "short.mp4"
    podcast_file.touch()
    video_file.touch()
    
    assert podcast_file.stat().st_size == 0
    assert video_file.stat().st_size == 0
    
    # Re-register path in DB & metadata
    update_job(job_id, podcast_file="audio/podcast.wav", video_file="video/short.mp4")
    updated_meta["file_paths"]["podcast"] = str(podcast_file)
    updated_meta["file_paths"]["video"] = str(video_file)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(updated_meta, f, indent=2)
        
    # Fetch healed (0-byte files should still be cleared)
    healed_job2 = get_job_healed(job_id)
    assert healed_job2["podcast_file"] is None
    assert healed_job2["video_file"] is None
    print("Assertion 4 Passed: get_job_healed cleared empty (0-byte) files.")
    
    # 3. Write non-empty files (size > 0)
    with open(podcast_file, "w") as f:
        f.write("mock audio data")
    with open(video_file, "w") as f:
        f.write("mock video data")
        
    assert podcast_file.stat().st_size > 0
    assert video_file.stat().st_size > 0
    
    # Re-register paths in DB & metadata
    update_job(job_id, podcast_file="audio/podcast.wav", video_file="video/short.mp4")
    updated_meta["file_paths"]["podcast"] = str(podcast_file)
    updated_meta["file_paths"]["video"] = str(video_file)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(updated_meta, f, indent=2)
        
    # Fetch healed (valid files should be preserved)
    healed_job3 = get_job_healed(job_id)
    assert healed_job3["podcast_file"] == "audio/podcast.wav"
    assert healed_job3["video_file"] == "video/short.mp4"
    print("Assertion 5 Passed: get_job_healed preserved valid non-empty files.")
    
    # Verify metadata.json was preserved
    with open(meta_path, "r", encoding="utf-8") as f:
        final_meta = json.load(f)
    assert final_meta["file_paths"]["podcast"] == str(podcast_file)
    assert final_meta["file_paths"]["video"] == str(video_file)
    print("Assertion 6 Passed: metadata.json paths preserved for valid files.")
    
    # Clean up test DB row and temp folder
    delete_job(job_id)
    shutil.rmtree(temp_dir)
    print("Test clean-up complete.")
    print("=== All Media Healing Tests Passed Successfully! ===")

if __name__ == "__main__":
    test_media_healing()
