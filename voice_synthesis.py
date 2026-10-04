
import asyncio
import os
import shutil
import subprocess
import threading
import time
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
    "ryan_neural": VoicePersona(
        "ryan_neural", "Ryan · Deep US English", "en-US-RyanNeural"
    ),
    "aria_neural": VoicePersona(
        "aria_neural", "Aria · Clear US English", "en-US-AriaNeural"
    ),
    "christopher_neural": VoicePersona(
        "christopher_neural", "Christopher · Narration",
        "en-US-ChristopherNeural"
    ),
    "guy_neural": VoicePersona(
        "guy_neural", "Guy · Energetic US English", "en-US-GuyNeural"
    ),
    "jenny_neural": VoicePersona(
        "jenny_neural", "Jenny · Bright US English", "en-US-JennyNeural"
    ),
    "uk_sonia": VoicePersona(
        "uk_sonia", "Sonia · British English", "en-GB-SoniaNeural"
    ),
}


class VoiceSynthesisManager:
    def __init__(self, config: Optional[GlobalConfig] = None):
        self.cfg = config or global_config

    def generate_narration(
        self,
        text_script: str,
        primary_speaker_key="ryan_neural",
        output_wav_path="output_speech.mp3",
        output_format=None,
    ) -> str:
        if not text_script or not text_script.strip():
            raise VoiceSynthesisError(
                "Please enter a narration script."
            )

        try:
            import edge_tts
        except ImportError as exc:
            raise VoiceSynthesisError(
                "edge-tts is missing. Add edge-tts to requirements.txt."
            ) from exc

        text = text_script.strip()
        output_path = os.path.abspath(output_wav_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        fmt = (
            output_format
            or ("mp3" if output_path.lower().endswith(".mp3") else "wav")
        ).lower()

        if fmt not in ("mp3", "wav"):
            raise VoiceSynthesisError(
                "Unsupported output format. Use MP3 or WAV."
            )

        temp_mp3 = (
            output_path
            if fmt == "mp3"
            else output_path + ".tmp.mp3"
        )

        selected = BUILTIN_SPEAKERS.get(
            primary_speaker_key,
            BUILTIN_SPEAKERS["ryan_neural"],
        )

        # Retry the selected voice, then try a few alternatives.
        voices_to_try = [
            selected.voice_id,
            "en-US-AriaNeural",
            "en-US-JennyNeural",
            "en-US-GuyNeural",
        ]

        # Preserve order while removing duplicate voices.
        voices_to_try = list(dict.fromkeys(voices_to_try))
        errors = []

        async def synthesize_with_retries(voice_id):
            last_error = None

            for attempt in range(3):
                try:
                    # Remove partial output left by a failed attempt.
                    if os.path.exists(temp_mp3):
                        os.remove(temp_mp3)

                    communicate = edge_tts.Communicate(
                        text,
                        voice_id,
                    )
                    await communicate.save(temp_mp3)

                    if (
                        not os.path.isfile(temp_mp3)
                        or os.path.getsize(temp_mp3) < 100
                    ):
                        raise RuntimeError(
                            "The speech service returned an empty "
                            "or unusually small audio file."
                        )

                    return

                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "TTS attempt %s failed for %s: %s",
                        attempt + 1,
                        voice_id,
                        exc,
                    )

                    if attempt < 2:
                        await asyncio.sleep(1 + attempt * 2)

            raise RuntimeError(
                f"Voice {voice_id} failed after 3 attempts: "
                f"{last_error}"
            )

        async def synthesize():
            for voice_id in voices_to_try:
                try:
                    await synthesize_with_retries(voice_id)
                    if voice_id != selected.voice_id:
                        logger.warning(
                            "Using fallback voice: %s", voice_id
                        )
                    return voice_id
                except Exception as exc:
                    errors.append(str(exc))

            raise VoiceSynthesisError(
                "Speech generation failed for all available voices.\n"
                + "\n".join(errors[-4:])
                + "\nCheck the deployment logs, internet access, "
                  "and whether the speech service is available."
            )

        # Run safely even if the caller already has an event loop.
        result = {}
        failure = {}

        def run_async():
            try:
                result["voice"] = asyncio.run(synthesize())
            except Exception as exc:
                failure["error"] = exc

        thread = threading.Thread(target=run_async)
        thread.start()
        thread.join()

        if "error" in failure:
            if os.path.exists(temp_mp3):
                try:
                    os.remove(temp_mp3)
                except OSError:
                    pass

            exc = failure["error"]
            if isinstance(exc, VoiceSynthesisError):
                raise exc
            raise VoiceSynthesisError(str(exc)) from exc

        if fmt == "wav":
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise VoiceSynthesisError(
                    "FFmpeg is not installed. Install FFmpeg or "
                    "choose MP3 output."
                )

            command = [
                ffmpeg,
                "-y",
                "-i", temp_mp3,
                "-vn",
                "-ar", "44100",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                output_path,
            ]

            try:
                conversion = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except subprocess.TimeoutExpired as exc:
                raise VoiceSynthesisError(
                    "Audio conversion timed out."
                ) from exc

            if conversion.returncode != 0:
                raise VoiceSynthesisError(
                    "FFmpeg could not convert the narration:\n"
                    + conversion.stderr[-1500:]
                )

            try:
                os.remove(temp_mp3)
            except OSError:
                pass

        if (
            not os.path.isfile(output_path)
            or os.path.getsize(output_path) == 0
        ):
            raise VoiceSynthesisError(
                "Narration finished without producing a valid output file."
            )

        logger.info(
            "Narration created successfully using %s: %s",
            result.get("voice", selected.voice_id),
            output_path,
        )
        return output_path

    @staticmethod
    def estimate_speaking_duration(text, words_per_minute=150):
        words = len((text or "").split())
        if not words:
            return 0.0
        return max(
            1.0,
            words * 60.0 / max(1, words_per_minute),
        )
