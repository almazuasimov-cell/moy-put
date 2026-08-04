"""STT service: local faster-whisper transcription."""
import io
import tempfile
import subprocess
import logging
from faster_whisper import WhisperModel

logger = logging.getLogger("voice-diary")

# Lazy-loaded model (tiny, ~75 MB, fast on CPU)
_model = None
MODEL_SIZE = "base"
MODEL_DEVICE = "cpu"
MODEL_COMPUTE = "int8"


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        logger.info(f"Loading faster-whisper model '{MODEL_SIZE}'...")
        _model = WhisperModel(MODEL_SIZE, device=MODEL_DEVICE, compute_type=MODEL_COMPUTE)
        logger.info("faster-whisper model loaded")
    return _model


def _convert_to_wav(audio_bytes: bytes, filename: str = "audio.ogg") -> bytes:
    """Convert any audio format to 16kHz mono WAV using ffmpeg."""
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "ogg"
    with tempfile.NamedTemporaryFile(suffix=f".{suffix}", delete=True) as infile:
        infile.write(audio_bytes)
        infile.flush()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as outfile:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", infile.name,
                    "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
                    outfile.name,
                ],
                capture_output=True,
                timeout=30,
                check=True,
            )
            outfile.seek(0)
            return outfile.read()


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.ogg", language: str = "ru") -> str:
    """Transcribe audio bytes to text using local faster-whisper."""
    wav_bytes = _convert_to_wav(audio_bytes, filename)
    model = _get_model()

    # Write WAV to temp file for faster-whisper
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
        f.write(wav_bytes)
        f.flush()
        segments, info = model.transcribe(
            f.name, language=language,
            beam_size=5,
            vad_filter=True,
            temperature=0.0,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        text = " ".join(seg.text for seg in segments)

    logger.info(f"Transcription done: {len(text)} chars, language={info.language}")
    return text.strip()
