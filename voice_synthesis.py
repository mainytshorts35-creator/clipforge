import asyncio
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Dict, Optional
from config import GlobalConfig, global_config, get_logger

logger = get_logger("ClipForge.VoiceSynthesis")

class VoiceSynthesisError(Exception):
    """Raised when narration generation or conversion fails."""

@dataclass
class VoicePersona:
    key: str
    display_name: str
    voice_id: str
    sample_rate: int = 44100

BUILTIN_SPEAKERS: Dict[str, VoicePersona] = {
    "ryan_neural": VoicePersona("ryan_neural", "Ryan · Deep US English", "en-US-RyanNeural"),
    "aria_neural": VoicePersona("aria_neural", "Aria · Clear US English", "en-US-AriaNeural"),
    "christopher_neural": VoicePersona("christopher_neural", "Christopher · Narration", "en-US-ChristopherNeural"),
    "guy_neural": VoicePersona("guy_neural", "Guy · Energetic US English", "en-US-GuyNeural"),
    "jenny_neural": VoicePersona("jenny_neural", "Jenny · Bright US English", "en-US-JennyNeural"),
    "uk_sonia": VoicePersona("uk_sonia", "Sonia · British English", "en-GB-SoniaNeural"),
}

class VoiceSynthesisManager:
    def __init__(self, config: Optional[GlobalConfig] = None):
        self.cfg = config or global_config

    def generate_narration(self, text_script: str, primary_speaker_key="ryan_neural",
                           output_wav_path="output_speech.mp3", output_format=None) -> str:
        if not text_script or not text_script.strip():
            raise VoiceSynthesisError("Please enter a narration script.")
        try:
            import edge_tts
        except ImportError as exc:
            raise VoiceSynthesisError("edge-tts is missing. Add edge-tts to requirements.txt.") from exc

        output_format = output_format or ("mp3" if str(output_wav_path).lower().endswith(".mp3") else "wav")
        persona = BUILTIN_SPEAKERS.get(primary_speaker_key, BUILTIN_SPEAKERS["ryan_neural"])
        output_path = os.path.abspath(output_wav_path)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        temp_mp3 = output_path if output_format == "mp3" else output_path + ".tmp.mp3"

        async def synthesize():
            communicate = edge_tts.Communicate(text_script.strip(), persona.voice_id)
            await communicate.save(temp_mp3)

        try:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(synthesize())
            else:
                # Streamlit normally has no active loop; this fallback avoids nested-loop errors.
                import threading
                errors = []
                def runner():
                    try: asyncio.run(synthesize())
                    except Exception as e: errors.append(e)
                thread = threading.Thread(target=runner, daemon=True)
                thread.start(); thread.join()
                if errors: raise errors[0]

            if output_format != "mp3":
                ffmpeg = shutil.which("ffmpeg")
                if not ffmpeg:
                    raise VoiceSynthesisError("FFmpeg is required to convert generated speech to WAV.")
                result = subprocess.run([ffmpeg, "-y", "-i", temp_mp3, "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", output_path],
                                        capture_output=True, text=True)
                if result.returncode:
                    raise VoiceSynthesisError(result.stderr[-1200:])
                if os.path.exists(temp_mp3): os.remove(temp_mp3)
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise VoiceSynthesisError("The speech provider returned an empty audio file.")
            return output_path
        except VoiceSynthesisError:
            raise
        except Exception as exc:
            if temp_mp3 != output_path and os.path.exists(temp_mp3):
                try: os.remove(temp_mp3)
                except OSError: pass
            raise VoiceSynthesisError(f"Speech generation failed: {exc}") from exc

    @staticmethod
    def estimate_speaking_duration(text, words_per_minute=150):
        words = len((text or "").split())
        return max(1.0, words * 60.0 / max(1, words_per_minute)) if words else 0.0
