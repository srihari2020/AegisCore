import subprocess
from pathlib import Path
from pypdf import PdfReader
import docx
import ollama

def resolve_wsl_path(raw_path: str) -> Path:
    clean = raw_path.strip().strip('"').strip("'")
    if len(clean) >= 2 and clean[1] == ":":
        drive = clean[0].lower()
        rest = clean[2:].replace("\\", "/").lstrip("/")
        return Path(f"/mnt/{drive}/{rest}")
    return Path(clean).expanduser()

class MediaReader:
    def __init__(self, vision_model: str = "qwen2.5vl:3b"):
        self.vision_model = vision_model
        self._whisper = None

    def read_document(self, file_path: str, max_chars: int = 12000) -> str:
        path = resolve_wsl_path(file_path)
        if not path.exists():
            return f"FILE_NOT_FOUND: {path}"

        ext = path.suffix.lower()
        try:
            if ext == ".pdf":
                reader = PdfReader(str(path))
                pages = [f"--- Page {i+1} ---\n{p.extract_text() or ''}" for i, p in enumerate(reader.pages[:30])]
                text = "\n".join(pages)
            elif ext == ".docx":
                doc = docx.Document(str(path))
                text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            else:
                text = path.read_text(encoding="utf-8", errors="ignore")

            trimmed = text[:max_chars]
            suffix = f"\n...[truncated {len(text) - max_chars} chars]" if len(text) > max_chars else ""
            return f"DOCUMENT [{path.name}] ({len(text)} chars):\n{trimmed}{suffix}"
        except Exception as e:
            return f"DOC_READ_ERROR [{path.name}]: {e}"

    def _get_whisper(self):
        if self._whisper is None:
            from faster_whisper import WhisperModel
            # Runs on CPU in ~450MB RAM so 8GB VRAM stays dedicated to LLM + VLM
            self._whisper = WhisperModel("base.en", device="cpu", compute_type="int8")
        return self._whisper

    def watch_video(self, video_path: str, question: str = "Summarize the video contents and visuals.") -> str:
        path = resolve_wsl_path(video_path)
        if not path.exists():
            return f"VIDEO_NOT_FOUND: {path}"

        work_dir = Path("/tmp/aegiscore_video")
        work_dir.mkdir(parents=True, exist_ok=True)
        for old in work_dir.glob("*"):
            old.unlink()

        wav_path = work_dir / "audio.wav"
        # 1. Extract mono 16kHz audio for fast Whisper transcription
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(path), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(wav_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        transcript = ""
        if wav_path.exists() and wav_path.stat().st_size > 1000:
            try:
                model = self._get_whisper()
                segments, _ = model.transcribe(str(wav_path), beam_size=1)
                transcript = " ".join(seg.text.strip() for seg in segments)
            except Exception as e:
                transcript = f"[Audio transcription skipped: {e}]"

        # 2. Extract up to 4 evenly spaced keyframes for visual understanding
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(path), "-vf", "fps=1/10,scale=960:-1", "-frames:v", "4", str(work_dir / "frame_%02d.jpg")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        frames = sorted(str(p) for p in work_dir.glob("frame_*.jpg"))

        visual_notes = ""
        if frames:
            try:
                resp = ollama.chat(
                    model=self.vision_model,
                    messages=[{
                        "role": "user",
                        "content": f"Analyze these keyframes from video '{path.name}'. User question: {question}",
                        "images": frames,
                    }],
                    keep_alive=-1,
                    options={"temperature": 0, "num_predict": 220},
                )
                visual_notes = resp.message.content.strip()
            except Exception as e:
                visual_notes = f"[Visual frame analysis skipped: {e}]"

        return (
            f"VIDEO_ANALYSIS [{path.name}]:\n"
            f"- Audio Transcript: {transcript[:4000] or 'No speech detected'}\n"
            f"- Visual Summary: {visual_notes or 'No frames extracted'}"
        )
