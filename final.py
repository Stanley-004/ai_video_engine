import streamlit as st
import requests
import re
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

# =========================================================
# CONFIGURATION
# =========================================================
st.set_page_config(
    page_title="Script to Video Studio",
    page_icon="🎬",
    layout="wide"
)

VIDEO_API_URL = "https://pixabay.com/api/videos/"
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# FFmpeg location found on this computer, plus normal PATH lookup.
KNOWN_FFMPEG_PATHS = [
    Path(r"C:\Program Files\KMPlayer 64X\LAVFilters64\ffmpeg.exe"),
    Path(r"C:\Program Files\WinGet\Packages"),
]


# =========================================================
# HELPERS
# =========================================================
def split_scenes(text):
    """Treat each sentence as one video scene."""
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text.strip())
        if sentence.strip()
    ]


def scene_query(sentence, max_words=8):
    """Make a short search phrase for one scene."""
    cleaned = re.sub(r"[^\w\s-]", "", sentence)
    return " ".join(cleaned.split()[:max_words])


def find_ffmpeg():
    """Find FFmpeg from PATH or known Windows locations."""
    found = shutil.which("ffmpeg")
    if found:
        return found

    for path in KNOWN_FFMPEG_PATHS:
        if path.is_file():
            return str(path)

    # Search WinGet folders only if the direct known path did not work.
    winget_root = Path(r"C:\Program Files\WinGet\Packages")
    if winget_root.exists():
        try:
            for path in winget_root.rglob("ffmpeg.exe"):
                if path.is_file():
                    return str(path)
        except OSError:
            pass

    return None


def search_videos(api_key, query, count):
    response = requests.get(
        VIDEO_API_URL,
        params={
            "key": api_key,
            "q": query,
            "per_page": count,
            "safesearch": "true",
            "order": "popular",
        },
        timeout=30,
    )

    if response.status_code == 429:
        raise RuntimeError(
            "The search API rate limit was reached. Wait and try again."
        )

    response.raise_for_status()
    return response.json().get("hits", [])


def choose_video_url(item):
    """Select an available downloadable video file."""
    video_sizes = item.get("videos", {})
    for size in ("medium", "small", "large", "tiny"):
        url = video_sizes.get(size, {}).get("url")
        if url:
            return url
    return None


def download_file(url, destination):
    response = requests.get(url, timeout=60, stream=True)
    response.raise_for_status()

    with open(destination, "wb") as output:
        for chunk in response.iter_content(chunk_size=1024 * 256):
            if chunk:
                output.write(chunk)

    return destination


def run_ffmpeg(args):
    """Run FFmpeg and show a useful error if processing fails."""
    result = subprocess.run(args, capture_output=True, text=True)

    if result.returncode != 0:
        details = (result.stderr or result.stdout or "Unknown FFmpeg error")[-3000:]
        raise RuntimeError(details)

    return result


def normalize_clip(ffmpeg, input_path, output_path, width, height, seconds):
    """Convert one clip to a consistent MP4 format for concatenation."""
    base_args = [
        ffmpeg, "-y", "-i", str(input_path),
        "-t", str(seconds),
        "-vf",
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps=30",
        "-an",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
    ]

    # Prefer H.264. If this FFmpeg build lacks libx264, try MPEG-4 Part 2.
    try:
        run_ffmpeg(base_args + [
            "-c:v", "libx264", "-preset", "veryfast", str(output_path)
        ])
    except RuntimeError as first_error:
        if "unknown encoder" not in str(first_error).lower() and \
           "encoder not found" not in str(first_error).lower() and \
           "libx264" not in str(first_error).lower():
            raise

        run_ffmpeg(base_args + [
            "-c:v", "mpeg4", "-q:v", "5", str(output_path)
        ])


def create_video(clip_paths, output_path, aspect_ratio, seconds_per_scene):
    """Normalize and merge all scene clips into one MP4."""
    ffmpeg = find_ffmpeg()

    if not ffmpeg:
        raise RuntimeError(
            "FFmpeg was not found. Install FFmpeg or add it to Windows PATH."
        )

    if not clip_paths:
        raise RuntimeError("There are no downloaded clips to merge.")

    width, height = {
        "16:9 (YouTube)": (1280, 720),
        "9:16 (Reels/Shorts)": (720, 1280),
        "1:1 (Square)": (720, 720),
    }[aspect_ratio]

    with tempfile.TemporaryDirectory() as temp_dir:
        normalized_paths = []

        for index, clip in enumerate(clip_paths, start=1):
            normalized = Path(temp_dir) / f"scene_{index:03d}.mp4"
            normalize_clip(
                ffmpeg, clip, normalized, width, height, seconds_per_scene
            )
            normalized_paths.append(normalized)

        concat_file = Path(temp_dir) / "concat.txt"
        with open(concat_file, "w", encoding="utf-8") as file:
            for clip in normalized_paths:
                # FFmpeg concat file paths use forward slashes.
                safe_path = str(clip.resolve()).replace("\\", "/")
                file.write(f"file '{safe_path}'\n")

        # Re-encode the combined result for compatibility across FFmpeg builds.
        run_ffmpeg([
            ffmpeg, "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c:v", "mpeg4", "-q:v", "5",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ])


def attach_voiceover(video_path, audio_path, output_path):
    """Add uploaded narration audio to the completed video."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("FFmpeg was not found.")

    run_ffmpeg([
        ffmpeg, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ])


def make_srt(scenes, seconds_per_scene):
    """Create simple scene subtitles using fixed durations."""
    def timestamp(seconds):
        whole = int(seconds)
        milliseconds = int(round((seconds - whole) * 1000))
        hours = whole // 3600
        minutes = (whole % 3600) // 60
        secs = whole % 60
        return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"

    lines = []
    for index, scene in enumerate(scenes, start=1):
        start = (index - 1) * seconds_per_scene
        end = index * seconds_per_scene
        lines.extend([
            str(index),
            f"{timestamp(start)} --> {timestamp(end)}",
            scene,
            "",
        ])

    return "\n".join(lines)


# =========================================================
# STREAMLIT INTERFACE
# =========================================================
st.title("🎬 Script-to-Video Studio")
st.write(
    "Enter a narration script, find matching stock clips, and merge the "
    "selected clips into one MP4 video."
)

ffmpeg_path = find_ffmpeg()
if ffmpeg_path:
    st.success(f"Video processing tool found: {ffmpeg_path}")
else:
    st.warning(
        "FFmpeg was not found. Install it or add its folder to Windows PATH."
    )

with st.sidebar:
    st.header("Video settings")
    api_key = st.text_input("Video search API key", type="password")
    results_per_scene = st.slider("Search candidates per scene", 1, 5, 3)
    seconds_per_scene = st.slider("Seconds per scene", 2, 10, 4)
    aspect_ratio = st.selectbox(
        "Output format",
        ["16:9 (YouTube)", "9:16 (Reels/Shorts)", "1:1 (Square)"],
    )
    voiceover_file = st.file_uploader(
        "Optional narration audio",
        type=["mp3", "wav", "m4a", "aac", "ogg"],
    )
    st.caption("Use your own API key. Keep it private.")

default_script = (
    "Artificial intelligence is changing the world. "
    "Businesses use technology to solve problems. "
    "People are learning new skills online. "
    "Innovation creates new opportunities."
)

script = st.text_area(
    "📝 Enter your narration script",
    value=default_script,
    height=180,
    placeholder="Write or paste your narration here...",
)

if st.button("🎬 Find clips and create final MP4", type="primary"):
    if not api_key.strip():
        st.error("Enter your video search API key in the sidebar.")
        st.stop()

    if not script.strip():
        st.error("Please enter a script.")
        st.stop()

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        st.error(
            "FFmpeg could not be found. Check the installation and restart PyCharm."
        )
        st.stop()

    scenes = split_scenes(script)
    if not scenes:
        st.error("No scenes were found in the script.")
        st.stop()

    work_dir = Path(tempfile.mkdtemp(prefix="script_video_"))
    downloaded_clips = []
    manifest = []
    used_ids = set()
    progress = st.progress(0, text="Searching for video clips...")

    try:
        for index, scene in enumerate(scenes, start=1):
            query = scene_query(scene)
            st.write(f"**Scene {index}/{len(scenes)}:** {scene}")

            candidates = search_videos(
                api_key.strip(), query, results_per_scene
            ) if query else []

            chosen = None
            for candidate in candidates:
                if candidate.get("id") not in used_ids and choose_video_url(candidate):
                    chosen = candidate
                    break

            # If all returned candidates were previously used, reuse one if necessary.
            if chosen is None:
                for candidate in candidates:
                    if choose_video_url(candidate):
                        chosen = candidate
                        break

            if chosen is None:
                raise RuntimeError(
                    f"No downloadable clip was found for scene {index} "
                    f"('{query}'). Try a shorter or more specific sentence."
                )

            clip_path = work_dir / f"clip_{index:03d}.mp4"
            with st.spinner(f"Downloading clip for scene {index}..."):
                download_file(choose_video_url(chosen), clip_path)

            used_ids.add(chosen.get("id"))
            downloaded_clips.append(clip_path)

            manifest.append({
                "scene_number": index,
                "narration": scene,
                "search_query": query,
                "selected_video_id": chosen.get("id"),
                "tags": chosen.get("tags"),
                "source_page": chosen.get("pageURL"),
                "contributor": chosen.get("user"),
                "source": "Stock video provider",
            })

            progress.progress(
                index / len(scenes),
                text=f"Downloaded clips for {index} of {len(scenes)} scenes",
            )

        raw_output = OUTPUT_DIR / "video_without_voiceover.mp4"
        final_output = OUTPUT_DIR / "final_video.mp4"

        with st.spinner("Merging scene clips into final video..."):
            create_video(
                downloaded_clips, raw_output, aspect_ratio, seconds_per_scene
            )

        if voiceover_file is not None:
            audio_path = work_dir / f"voiceover{Path(voiceover_file.name).suffix}"
            audio_path.write_bytes(voiceover_file.getvalue())

            with st.spinner("Adding your narration audio..."):
                attach_voiceover(raw_output, audio_path, final_output)
        else:
            shutil.copy2(raw_output, final_output)

        scene_plan_path = OUTPUT_DIR / "scene_plan.json"
        subtitle_path = OUTPUT_DIR / "subtitles.srt"

        scene_plan_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        subtitle_path.write_text(
            make_srt(scenes, seconds_per_scene),
            encoding="utf-8",
        )

        st.session_state["final_video_path"] = str(final_output.resolve())
        st.session_state["scene_plan_path"] = str(scene_plan_path.resolve())
        st.session_state["subtitle_path"] = str(subtitle_path.resolve())
        st.success("Your video has been created successfully!")

    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        st.error(
            f"The video search service returned HTTP {status}. "
            "Check your API key and request limits."
        )
    except requests.exceptions.RequestException as exc:
        st.error(f"Network or download error: {exc}")
    except (RuntimeError, OSError, ValueError) as exc:
        st.error(f"Could not create the video: {exc}")
    finally:
        progress.empty()
        shutil.rmtree(work_dir, ignore_errors=True)


# =========================================================
# SHOW AND DOWNLOAD THE COMPLETED OUTPUT
# =========================================================
final_path = st.session_state.get("final_video_path")

if final_path and Path(final_path).exists():
    st.divider()
    st.subheader("✅ Final video")
    st.video(final_path)

    st.download_button(
        "⬇️ Download final_video.mp4",
        data=Path(final_path).read_bytes(),
        file_name="final_video.mp4",
        mime="video/mp4",
    )

    subtitle_path = st.session_state.get("subtitle_path")
    if subtitle_path and Path(subtitle_path).exists():
        st.download_button(
            "⬇️ Download subtitles (.srt)",
            data=Path(subtitle_path).read_bytes(),
            file_name="subtitles.srt",
            mime="application/x-subrip",
        )

    scene_plan_path = st.session_state.get("scene_plan_path")
    if scene_plan_path and Path(scene_plan_path).exists():
        st.download_button(
            "⬇️ Download scene plan (.json)",
            data=Path(scene_plan_path).read_bytes(),
            file_name="scene_plan.json",
            mime="application/json",
        )

st.caption(
    "Check each source page and its license terms before publishing. "
    "Subtitles use fixed scene timings and may need editing. "
    "Without an uploaded voiceover, the output video is silent."
)
