
import streamlit as st
import requests
import re
import json
import os
import time
import hashlib
from urllib.parse import quote_plus

# =========================================================
# CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="AI Script to B-Roll Finder",
    page_icon="🎬",
    layout="wide"
)

PIXABAY_API_URL = "https://pixabay.com/api/videos/"
CACHE_FOLDER = ".pixabay_cache"
CACHE_SECONDS = 24 * 60 * 60

os.makedirs(CACHE_FOLDER, exist_ok=True)

# =========================================================
# STYLING
# =========================================================

st.title("🎬 AI Script-to-B-Roll Video Finder")
st.write(
    "Paste your narration script. The app divides it into scenes "
    "and searches Pixabay for matching stock videos."
)

st.info(
    "This prototype finds and previews B-roll clips. "
    "It does not yet combine them into a final MP4 video."
)

# =========================================================
# SCENE PLANNER
# =========================================================

def split_into_scenes(script):
    """Split a script into sentence-based scenes."""
    script = script.strip()

    if not script:
        return []

    sentences = re.split(r'(?<=[.!?])\s+', script)

    return [
        sentence.strip()
        for sentence in sentences
        if sentence.strip()
    ]


def make_search_query(sentence):
    """Create a simple search phrase from a scene."""
    sentence = re.sub(r"[^\w\s-]", "", sentence)
    words = sentence.split()

    # Keep the main phrase short enough for useful searching.
    return " ".join(words[:8])


# =========================================================
# CACHED PIXABAY API SEARCH
# =========================================================

def search_pixabay(api_key, query, per_page=3):
    """
    Search Pixabay videos.
    Cache successful responses locally for 24 hours.
    """

    cache_key = hashlib.sha256(
        f"{query.lower()}|{per_page}".encode("utf-8")
    ).hexdigest()

    cache_file = os.path.join(
        CACHE_FOLDER, cache_key + ".json"
    )

    # Reuse cached response if it is less than 24 hours old.
    if os.path.exists(cache_file):
        age = time.time() - os.path.getmtime(cache_file)

        if age < CACHE_SECONDS:
            try:
                with open(cache_file, "r", encoding="utf-8") as file:
                    return json.load(file)
            except (OSError, json.JSONDecodeError):
                pass

    params = {
        "key": api_key,
        "q": query,
        "per_page": per_page,
        "safesearch": "true",
        "order": "popular"
    }

    try:
        response = requests.get(
            PIXABAY_API_URL,
            params=params,
            timeout=20
        )

        if response.status_code == 429:
            st.warning(
                "Pixabay rate limit reached. Please wait before searching again."
            )
            return []

        response.raise_for_status()
        data = response.json()
        videos = data.get("hits", [])

        # Cache the response for 24 hours.
        try:
            with open(cache_file, "w", encoding="utf-8") as file:
                json.dump(videos, file)
        except OSError:
            pass

        return videos

    except requests.exceptions.Timeout:
        st.error("Pixabay took too long to respond. Try again.")
    except requests.exceptions.HTTPError as error:
        if error.response is not None:
            st.error(
                f"Pixabay returned HTTP {error.response.status_code}. "
                "Check your API key and request limits."
            )
        else:
            st.error("Pixabay returned an HTTP error.")
    except requests.exceptions.RequestException:
        st.error(
            "Could not connect to Pixabay. Check your internet connection."
        )
    except ValueError:
        st.error("Pixabay returned an invalid response.")

    return []


# =========================================================
# VIDEO RESULT DISPLAY
# =========================================================

def show_video_result(video, scene_number):
    """Display one video with preview and source information."""

    tags = video.get("tags", "Pixabay video")
    page_url = video.get("pageURL", "https://pixabay.com/videos/")
    video_files = video.get("videos", {})

    # Prefer a medium-sized file, then fall back to other sizes.
    video_url = None

    for size in ["medium", "small", "large", "tiny"]:
        file_info = video_files.get(size, {})
        if file_info.get("url"):
            video_url = file_info["url"]
            break

    with st.container(border=True):
        st.markdown(f"**Scene {scene_number} — {tags}**")

        if video_url:
            st.video(video_url)
        else:
            st.write("Preview is unavailable for this result.")

        st.write(
            f"**Duration:** {video.get('duration', 'Unknown')} seconds"
        )

        st.write(
            f"**Resolution:** "
            f"{video.get('width', '?')} × {video.get('height', '?')}"
        )

        st.markdown(f"[View original on Pixabay]({page_url})")

        st.caption("Video source: Pixabay")


# =========================================================
# USER INPUT
# =========================================================

st.subheader("1. Enter your Pixabay API key")

api_key = st.text_input(
    "API key",
    type="password",
    help="Enter your own key from https://pixabay.com/api/docs/"
)

st.caption(
    "Keep your API key private. Do not commit it to a public repository."
)

st.subheader("2. Paste your video script")

default_script = (
    "Artificial intelligence is changing the world. "
    "Businesses use AI to analyse data and make better decisions. "
    "Students use technology to learn new skills. "
    "The future will bring new opportunities."
)

script = st.text_area(
    "Narration script",
    value=default_script,
    height=180,
    placeholder="Paste your narration here..."
)

number_of_results = st.slider(
    "Videos to retrieve per scene",
    min_value=1,
    max_value=5,
    value=3
)

# =========================================================
# SEARCH
# =========================================================

if st.button("🔎 Find Relevant B-Roll Videos", type="primary"):

    if not api_key.strip():
        st.error("Please enter your Pixabay API key.")
        st.stop()

    if not script.strip():
        st.error("Please enter a script first.")
        st.stop()

    scenes = split_into_scenes(script)

    if not scenes:
        st.error("No scenes could be extracted from the script.")
        st.stop()

    st.session_state["scenes"] = scenes
    st.session_state["scene_queries"] = [
        make_search_query(scene) for scene in scenes
    ]
    st.session_state["api_key"] = api_key.strip()
    st.session_state["number_of_results"] = number_of_results
    st.session_state["search_requested"] = True

# =========================================================
# DISPLAY SCENES AND SEARCH RESULTS
# =========================================================

if st.session_state.get("search_requested", False):

    scenes = st.session_state["scenes"]
    queries = st.session_state["scene_queries"]
    saved_key = st.session_state["api_key"]
    result_count = st.session_state["number_of_results"]

    st.divider()
    st.subheader("3. Scene-by-scene B-roll results")

    progress = st.progress(0)
    status = st.empty()

    manifest = []

    for index, scene in enumerate(scenes):
        scene_number = index + 1
        query = queries[index]

        status.write(
            f"Searching scene {scene_number} of {len(scenes)}: {query}"
        )

        st.markdown(f"### Scene {scene_number}")
        st.write(f"**Narration:** {scene}")
        st.write(f"**Search phrase:** `{query}`")

        if query:
            videos = search_pixabay(
                saved_key,
                query,
                per_page=result_count
            )
        else:
            videos = []

        scene_manifest = {
            "scene_number": scene_number,
            "narration": scene,
            "search_query": query,
            "source": "Pixabay",
            "videos": []
        }

        if videos:
            columns = st.columns(min(len(videos), 3))

            for video_index, video in enumerate(videos):
                with columns[video_index % len(columns)]:
                    show_video_result(video, scene_number)

                scene_manifest["videos"].append({
                    "id": video.get("id"),
                    "tags": video.get("tags"),
                    "duration_seconds": video.get("duration"),
                    "page_url": video.get("pageURL"),
                    "user": video.get("user"),
                    "source": "Pixabay"
                })
        else:
            st.warning("No videos found for this scene.")

            search_url = (
                "https://pixabay.com/videos/search/"
                + quote_plus(query)
                + "/"
            )
            st.markdown(
                f"[Search this scene directly on Pixabay]({search_url})"
            )

        google_url = (
            "https://www.google.com/search?q="
            + quote_plus(query + " stock video B-roll")
        )
        st.markdown(
            f"[Also search Google for this scene]({google_url})"
        )

        manifest.append(scene_manifest)

        st.divider()
        progress.progress(scene_number / len(scenes))

    status.success("Scene search completed.")

    st.subheader("4. Export scene plan")

    manifest_json = json.dumps(
        manifest,
        indent=2,
        ensure_ascii=False
    )

    st.download_button(
        label="⬇️ Download scene plan (JSON)",
        data=manifest_json,
        file_name="broll_scene_plan.json",
        mime="application/json"
    )

    st.caption(
        "Before publishing, check the source page and applicable "
        "license terms for each selected clip. Search results alone "
        "do not guarantee that a clip is suitable for every use."
    )

    st.success(
        "Pixabay attribution: video search results are sourced from Pixabay."
    )
