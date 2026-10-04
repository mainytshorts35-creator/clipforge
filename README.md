# ClipForge Studio — free Viewmax-inspired Shorts workflow

A Streamlit project for a personal, no-paid-API-key workflow: source video → AI narration → timed captions → vertical MP4 export.

## Run locally (Windows)

1. Install Python 3.10 or newer.
2. Install FFmpeg and ensure `ffmpeg` is on PATH.
3. Open a terminal in this folder and run:

   ```bash
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   streamlit run app.py
   ```

## Deploy to GitHub + Streamlit Community Cloud

1. Upload all files in this folder to the root of your GitHub repository.
2. In Streamlit Community Cloud, choose that repository and set the main file to `app.py`.
3. Keep `packages.txt` and `requirements.txt` at the repository root.

## Notes

- Edge TTS does not need an OpenAI or ElevenLabs API key, but it does need internet access.
- Faster-Whisper downloads a model the first time captions are generated. The `base` model is configured for CPU.
- Caption masking covers the bottom region; it cannot reconstruct the image behind existing burned-in captions.
- YouTube URL downloading can fail for age-restricted, private, region-blocked, or otherwise unavailable videos. Respect copyright and platform terms.
- Long videos can exceed free hosting memory or execution limits. Trim clips before rendering.
