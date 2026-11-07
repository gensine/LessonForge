"""YouTube research module.

Uses YouTube Data API v3 to find videos and youtube-transcript-api to pull
transcripts. LLM scores each video for relevance based on title + transcript.
"""

import logging
from typing import Optional

import httpx
from pydantic import BaseModel, Field

from backend.config import settings
from backend.schemas import Source, SourceType

logger = logging.getLogger(__name__)


# ── Pydantic models for LLM video scoring ────────────────────────────────

class VideoRelevance(BaseModel):
    """LLM-generated relevance assessment for a single video."""
    relevance_score: float = Field(ge=0.0, le=1.0)
    why_relevant: str


class VideoRelevanceList(BaseModel):
    """Batch of video relevance scores."""
    videos: list[VideoRelevance]


# ── YouTube Data API search ──────────────────────────────────────────────

async def search_youtube(queries: list[str], max_results_per_query: int = 4) -> list[dict]:
    """Search YouTube using the Data API v3.

    Args:
        queries: YouTube search queries.
        max_results_per_query: Max results per query.

    Returns:
        List of dicts with video_id, title, channel, description, duration.
    """
    if not settings.youtube_api_key:
        logger.warning("No YouTube API key configured; skipping YouTube search.")
        return []

    all_results = []
    seen_ids = set()

    for query in queries:
        try:
            # Step 1: Search for videos
            async with httpx.AsyncClient(timeout=15.0) as client:
                search_response = await client.get(
                    "https://www.googleapis.com/youtube/v3/search",
                    params={
                        "key": settings.youtube_api_key,
                        "q": query,
                        "part": "snippet",
                        "type": "video",
                        "maxResults": max_results_per_query,
                        "order": "relevance",
                        "videoEmbeddable": "true",
                    },
                )
                search_response.raise_for_status()
                search_data = search_response.json()

            video_ids = []
            video_snippets = {}

            for item in search_data.get("items", []):
                vid_id = item.get("id", {}).get("videoId", "")
                if vid_id and vid_id not in seen_ids:
                    seen_ids.add(vid_id)
                    video_ids.append(vid_id)
                    snippet = item.get("snippet", {})
                    video_snippets[vid_id] = {
                        "title": snippet.get("title", ""),
                        "channel": snippet.get("channelTitle", ""),
                        "description": snippet.get("description", "")[:300],
                    }

            if not video_ids:
                continue

            # Step 2: Get video details (duration)
            async with httpx.AsyncClient(timeout=15.0) as client:
                details_response = await client.get(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={
                        "key": settings.youtube_api_key,
                        "id": ",".join(video_ids),
                        "part": "contentDetails,statistics",
                    },
                )
                details_response.raise_for_status()
                details_data = details_response.json()

            for item in details_data.get("items", []):
                vid_id = item.get("id", "")
                duration_iso = item.get("contentDetails", {}).get("duration", "PT0S")
                duration_minutes = _parse_iso_duration(duration_iso)

                if vid_id in video_snippets:
                    all_results.append({
                        "video_id": vid_id,
                        "title": video_snippets[vid_id]["title"],
                        "channel": video_snippets[vid_id]["channel"],
                        "description": video_snippets[vid_id]["description"],
                        "duration_minutes": duration_minutes,
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                    })

            logger.info(f"YouTube search '{query}': {len(video_ids)} results")

        except Exception as e:
            logger.error(f"YouTube search failed for '{query}': {e}")
            continue

    logger.info(f"Total unique YouTube results: {len(all_results)}")
    return all_results


# ── Transcript extraction ─────────────────────────────────────────────────

def get_transcript(video_id: str, max_chars: int = 3000) -> Optional[str]:
    """Pull transcript for a YouTube video.

    Args:
        video_id: YouTube video ID.
        max_chars: Maximum characters of transcript to return.

    Returns:
        Transcript text or None if unavailable.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        # youtube-transcript-api v1.2+ uses YouTubeTranscriptApi().fetch(video_id)
        # while older versions used YouTubeTranscriptApi.get_transcript(video_id)
        if hasattr(YouTubeTranscriptApi, "get_transcript"):
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            full_text = " ".join(entry["text"] for entry in transcript_list)
        else:
            api_instance = YouTubeTranscriptApi()
            transcript_obj = api_instance.fetch(video_id)
            snippets = getattr(transcript_obj, "snippets", [])
            full_text = " ".join(getattr(entry, "text", "") for entry in snippets)

        return full_text[:max_chars] if full_text else None

    except Exception as e:
        logger.warning(f"Transcript unavailable for video {video_id}: {e}")
        return None


# ── LLM-based video relevance scoring ────────────────────────────────────

def score_videos(
    videos: list[dict],
    objective: str,
    max_video_minutes: float = 10.0,
) -> list[Source]:
    """Score and filter videos for relevance using the LLM.

    Args:
        videos: Raw video dicts from search.
        objective: Lesson learning objective.
        max_video_minutes: Max total video time to fit in 45-min lesson.

    Returns:
        Top 2-3 relevant videos as Source objects.
    """
    if not videos:
        return []

    from backend.llm import generate

    prompt_path = settings.prompts_dir / "video_scorer.md"
    system_prompt = prompt_path.read_text() if prompt_path.exists() else ""

    # Fetch transcripts and build description
    videos_desc = ""
    for i, vid in enumerate(videos):
        transcript = get_transcript(vid["video_id"])
        vid["transcript_excerpt"] = transcript or ""

        transcript_info = f"Transcript excerpt: {transcript[:500]}" if transcript else "Transcript: unavailable"

        videos_desc += (
            f"\n--- Video {i+1} ---\n"
            f"Title: {vid['title']}\n"
            f"Channel: {vid['channel']}\n"
            f"Duration: {vid['duration_minutes']:.1f} minutes\n"
            f"Description: {vid['description']}\n"
            f"{transcript_info}\n"
        )

    prompt = (
        f"Lesson objective: {objective}\n\n"
        f"Evaluate each of the following {len(videos)} YouTube videos for relevance.\n"
        f"Return exactly {len(videos)} relevance scores in the same order.\n"
        f"{videos_desc}"
    )

    try:
        result = generate(prompt, VideoRelevanceList, system_prompt=system_prompt, temperature=0.1)

        scored_videos = []
        for i, vid in enumerate(videos):
            if i < len(result.videos):
                score_data = result.videos[i]
                relevance = score_data.relevance_score
                why = score_data.why_relevant
            else:
                relevance = 0.3
                why = "Scoring unavailable"

            scored_videos.append((vid, relevance, why))

        # Sort by relevance, pick top videos that fit within budget
        scored_videos.sort(key=lambda x: x[1], reverse=True)

        selected = []
        total_minutes = 0.0

        for vid, relevance, why in scored_videos:
            if relevance < 0.4:
                continue  # Skip low-relevance videos

            if total_minutes + vid["duration_minutes"] > max_video_minutes:
                # Check if we can fit it
                if total_minutes > 0:
                    continue

            source = Source(
                id=f"V{len(selected)+1}",
                type=SourceType.VIDEO,
                title=vid["title"],
                url=vid["url"],
                channel=vid["channel"],
                duration_minutes=vid["duration_minutes"],
                relevance_score=relevance,
                why_relevant=why,
                snippet=vid["description"],
                extracted_text=vid.get("transcript_excerpt", "")[:2000],
                reliability_score=0.7,
                reliability_reason="YouTube video — relevance verified via transcript",
            )
            selected.append(source)
            total_minutes += vid["duration_minutes"]

            if len(selected) >= 3:
                break

        logger.info(
            f"Selected {len(selected)} videos "
            f"(total {total_minutes:.1f} min) from {len(videos)} candidates"
        )
        return selected

    except Exception as e:
        logger.error(f"Video scoring failed: {e}")
        # Fallback: return top 2 by duration (shorter preferred)
        videos.sort(key=lambda v: v["duration_minutes"])
        fallback = []
        for vid in videos[:2]:
            source = Source(
                id=f"V{len(fallback)+1}",
                type=SourceType.VIDEO,
                title=vid["title"],
                url=vid["url"],
                channel=vid["channel"],
                duration_minutes=vid["duration_minutes"],
                relevance_score=0.5,
                why_relevant="Auto-selected (scoring unavailable)",
                snippet=vid["description"],
                reliability_score=0.5,
                reliability_reason="YouTube video — relevance not verified",
            )
            fallback.append(source)
        return fallback


# ── Helpers ───────────────────────────────────────────────────────────────

def _parse_iso_duration(iso_duration: str) -> float:
    """Parse ISO 8601 duration (PT#H#M#S) to minutes.

    Examples:
        PT1H2M30S → 62.5
        PT5M → 5.0
        PT30S → 0.5
    """
    import re

    hours = 0
    minutes = 0
    seconds = 0

    h_match = re.search(r"(\d+)H", iso_duration)
    m_match = re.search(r"(\d+)M", iso_duration)
    s_match = re.search(r"(\d+)S", iso_duration)

    if h_match:
        hours = int(h_match.group(1))
    if m_match:
        minutes = int(m_match.group(1))
    if s_match:
        seconds = int(s_match.group(1))

    return hours * 60 + minutes + seconds / 60

