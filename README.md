# AI Script-to-Video Engine

A Streamlit prototype that turns a text script into scene-by-scene B-roll searches, previews candidate clips, and can merge selected stock-video clips into a final MP4.

## Features
- Splits narration into sentence-based scenes.
- Searches a stock-video API for each scene.
- Displays candidate clips and source-page links.
- Downloads one candidate clip per scene and merges clips into `final_video.mp4`.
- Supports 16:9 landscape, 9:16 portrait, and 1:1 square output.
- Optionally adds an uploaded narration audio file.
- Exports an SRT subtitle file and a JSON scene plan.

## Project files
- `app.py` — **run this first** to preview candidate/selected videos for each scene.
- `final.py` — **run this next** to create and display the final merged MP4 based on the text script.
- `api.txt` — API configuration/helper file, if included in your project. Keep any API key private. If the app asks for the key in the sidebar, enter it there instead.
- `requirements.txt` — Python dependencies, if included.

If your filenames differ, use the actual names in your project. The preview app and final-video app are separate runs.

## Requirements
- Python 3.10 or newer recommended.
- A Pixabay API key.
- FFmpeg installed and accessible to the app.
- Internet connection.

## Setup in PyCharm (Windows)
Open the project folder in PyCharm and open the Terminal.

Install the dependencies in one command:

```powershell
python -m pip install streamlit requests
```

If a `requirements.txt` is present, you can instead use:

```powershell
python -m pip install -r requirements.txt
```

### FFmpeg
The final-video app uses FFmpeg to process and merge clips. Check it with:

```powershell
ffmpeg -version
```

If the command is not recognized, install FFmpeg and make sure its executable is on Windows `PATH`, then restart PyCharm. The app may also be configured to use a known local FFmpeg path.

## API key setup
The app uses the Pixabay Video API endpoint:

`https://pixabay.com/api/videos/`

Use your own API key. Do **not** commit API keys to GitHub or include them in this README.

Depending on your version:
- If the Streamlit sidebar has an API-key field, enter the key there.
- If your project uses `api.py` for configuration, keep any private key in a local-only configuration file and exclude it from Git.

If a key has been exposed, rotate it in your Pixabay account settings and use the replacement key.

## Run the application

### 1. Preview videos first
Run:

```powershell
python -m streamlit run app.py
```

Paste your script and click the search button. The app splits the script into scenes and displays candidate videos so you can inspect them before generating the full video.

### 2. Create the final merged video
Stop the first app with `Ctrl+C`, then run:

```powershell
python -m streamlit run script_to_video_app.py
```

Enter the API key if requested, paste your script, select the aspect ratio and scene duration, optionally upload a voiceover, and click **Find clips and create final MP4**. The app searches for one clip per scene, downloads the selected clips, and merges them into the final MP4.

If you upload a voiceover, it is added to the output. Without a voiceover upload, the output video is silent.

## Output files
The final-video app saves these in the `output/` folder:
- `final_video.mp4` — final merged video.
- `video_without_voiceover.mp4` — merged clips before optional narration is added.
- `subtitles.srt` — basic subtitles with fixed scene timings.
- `scene_plan.json` — scene text, search query, selected video IDs, tags, and source links.

The final MP4 is also shown in Streamlit and can be downloaded there.

## Limitations
- Search phrases use the first few words of each sentence; the app does not yet use a dedicated visual AI model to verify clip relevance.
- Subtitle timing is based on fixed scene durations and may need manual adjustment.
- Without an uploaded voiceover, the final MP4 is silent.
- FFmpeg codecs vary by installation. If processing fails, install a full FFmpeg build and confirm `ffmpeg -version` works.
- Check each source page and applicable license terms before publishing.

## Suggested `.gitignore`
Exclude local secrets, virtual environments, downloaded clips, generated videos, and caches:

```gitignore
.venv/
__pycache__/
.env
.streamlit/secrets.toml
.pixabay_cache/
downloaded_clips/
output/
```

If `api.py` contains a hardcoded API key, do not commit it. Prefer moving the key to environment variables or Streamlit secrets and excluding the local secret file from Git.
