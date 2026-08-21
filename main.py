import os
import re
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from pydantic import BaseModel
from dotenv import load_dotenv
import google.generativeai as genai
from faster_whisper import WhisperModel

load_dotenv()

# Initialize directories BEFORE configuring logging
BASE_DIR = Path(__file__).parent
USER_DATA_DIR = BASE_DIR / "user-data"
AUDIO_DIR = USER_DATA_DIR / "audio"
TRANSCRIPTS_DIR = USER_DATA_DIR / "transcripts"
OUTLINES_DIR = USER_DATA_DIR / "outlines"
PROMPTS_DIR = USER_DATA_DIR / "prompts"
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"

AUDIO_DIR.mkdir(parents=True, exist_ok=True)
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
OUTLINES_DIR.mkdir(parents=True, exist_ok=True)
PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Configure logging AFTER directory creation
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOGS_DIR / 'voctation.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI()

logger.info("VocTation started - directories initialized")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma"}
ALLOWED_TEXT_EXTENSIONS = {".md", ".txt"}

if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY not found in environment")
else:
    genai.configure(api_key=GEMINI_API_KEY)

whisper_model = None


def validate_path(base_dir: Path, filename: str) -> Path:
    """Validate and sanitize file path to prevent path traversal attacks."""
    if not filename or ".." in filename or filename.startswith("/") or filename.startswith("\\"):
        raise HTTPException(status_code=400, detail="Invalid filename")

    sanitized = Path(filename).name
    full_path = (base_dir / sanitized).resolve()

    if not full_path.is_relative_to(base_dir.resolve()):
        raise HTTPException(status_code=400, detail="Path traversal detected")

    return full_path


def load_whisper_model():
    """Load Whisper model using standard cache configuration."""
    global whisper_model
    if whisper_model is None:
        logger.info("Loading Whisper 'small' model...")

        # Check if model exists in HuggingFace cache
        hf_cache = Path.home() / ".cache" / "huggingface" / "hub" / "models--Systran--faster-whisper-small"

        if hf_cache.exists():
            # Find the snapshot directory
            snapshot_dir = hf_cache / "snapshots"
            if snapshot_dir.exists():
                snapshots = list(snapshot_dir.iterdir())
                if snapshots:
                    model_path = snapshots[0]
                    logger.info(f"Loading Whisper model from local cache: {model_path}")
                    try:
                        whisper_model = WhisperModel(
                            str(model_path),
                            device="cpu",
                            compute_type="int8",
                            local_files_only=True
                        )
                        logger.info("Whisper model loaded successfully from local cache")
                        return whisper_model
                    except Exception as e:
                        logger.warning(f"Failed to load from local cache path: {e}")

        # Fallback: try to load/download with model name
        try:
            logger.info("Attempting to load/download Whisper model (may download ~500MB on first run)...")
            whisper_model = WhisperModel(
                "small",
                device="cpu",
                compute_type="int8"
            )
            logger.info("Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise HTTPException(
                status_code=503,
                detail="Whisper model not available. Please check internet connection or model cache."
            )

    return whisper_model


class TranscribeRequest(BaseModel):
    filename: str


class SummarizeRequest(BaseModel):
    transcript_file: str
    template: str


class DirectTextRequest(BaseModel):
    text: str
    template: str


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/audio-files")
async def get_audio_files():
    files = []
    if AUDIO_DIR.exists():
        files = sorted([
            f.name for f in AUDIO_DIR.iterdir()
            if f.is_file() and f.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS
        ])
    return JSONResponse(content=files)


@app.get("/api/prompt-templates")
async def get_prompt_templates():
    templates = []
    if PROMPTS_DIR.exists():
        templates = sorted([
            f.name for f in PROMPTS_DIR.iterdir()
            if f.is_file() and f.suffix == ".md"
        ])
    return JSONResponse(content=templates)


@app.post("/api/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")

        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_AUDIO_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_AUDIO_EXTENSIONS)}"
            )

        now = datetime.now()
        filename = f"{now.strftime('%Y-%m-%d_%H-%M-%S')}{ext}"
        file_path = AUDIO_DIR / filename

        # Stream file to disk in chunks to avoid OOM
        chunk_size = 1024 * 1024  # 1MB chunks
        total_size = 0

        with open(file_path, "wb") as f:
            while chunk := await file.read(chunk_size):
                f.write(chunk)
                total_size += len(chunk)

        logger.info(f"Audio uploaded: {filename} ({total_size / 1024 / 1024:.2f} MB)")
        return JSONResponse(content={"filename": filename, "status": "success"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/upload-transcript")
async def upload_transcript(file: UploadFile = File(...)):
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")

        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_TEXT_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail="Only .md or .txt files are allowed"
            )

        now = datetime.now()
        base_name = Path(file.filename).stem
        filename = f"{base_name}_{now.strftime('%Y-%m-%d_%H-%M-%S')}.md"
        file_path = TRANSCRIPTS_DIR / filename

        content = await file.read()
        text = content.decode('utf-8')

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)

        logger.info(f"Transcript uploaded: {filename} ({len(text)} chars)")
        return JSONResponse(content={
            "filename": filename,
            "text": text,
            "status": "success"
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transcript upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def transcribe_audio_sync(audio_path: Path) -> str:
    """Synchronous transcription function to avoid blocking async event loop."""
    model = load_whisper_model()
    segments, info = model.transcribe(str(audio_path), language="ru", beam_size=5)

    text_parts = [segment.text for segment in segments]
    return " ".join(text_parts).strip()


@app.post("/api/transcribe")
def transcribe_audio(request: TranscribeRequest):
    """Changed to sync def so FastAPI runs it in threadpool."""
    try:
        audio_path = validate_path(AUDIO_DIR, request.filename)

        if not audio_path.exists():
            logger.warning(f"Transcribe requested for missing file: {request.filename}")
            raise HTTPException(status_code=404, detail="Audio file not found")

        logger.info(f"Starting transcription: {request.filename}")
        text = transcribe_audio_sync(audio_path)

        transcript_filename = audio_path.stem + ".md"
        transcript_path = TRANSCRIPTS_DIR / transcript_filename

        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(text)

        logger.info(f"Transcription completed: {transcript_filename} ({len(text)} chars)")
        return JSONResponse(content={
            "transcript_file": transcript_filename,
            "text": text,
            "status": "success"
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transcription failed for {request.filename}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def generate_summary_sync(prompt: str) -> str:
    """Synchronous Gemini API call to avoid blocking async event loop."""
    # Use the correct model name format for Gemini API (without 'models/' prefix)
    # Valid model names: gemini-pro, gemini-1.5-pro, gemini-1.5-flash, gemini-2.0-flash-exp
    model_name = GEMINI_MODEL

    # Map to simpler model names that work with the API
    model_mapping = {
        "gemini-1.5-flash-latest": "gemini-1.5-flash",
        "gemini-1.5-pro-latest": "gemini-1.5-pro",
        "gemini-flash": "gemini-1.5-flash"
    }

    if model_name in model_mapping:
        model_name = model_mapping[model_name]

    logger.info(f"Using Gemini model: {model_name}")
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(prompt)
    return response.text


@app.post("/api/summarize")
def summarize_transcript(request: SummarizeRequest):
    """Changed to sync def so FastAPI runs it in threadpool."""
    try:
        if not GEMINI_API_KEY:
            logger.error("Summarize attempted without GEMINI_API_KEY configured")
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")

        transcript_path = validate_path(TRANSCRIPTS_DIR, request.transcript_file)
        template_path = validate_path(PROMPTS_DIR, request.template)

        if not transcript_path.exists():
            logger.warning(f"Summarize requested for missing transcript: {request.transcript_file}")
            raise HTTPException(status_code=404, detail="Transcript file not found")

        if not template_path.exists():
            logger.warning(f"Summarize requested for missing template: {request.template}")
            raise HTTPException(status_code=404, detail="Template file not found")

        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript_text = f.read()

        with open(template_path, "r", encoding="utf-8") as f:
            template_text = f.read()

        logger.info(f"Starting summarization: {request.transcript_file} with template {request.template}")

        prompt = f"{template_text}\n\nTranscript:\n{transcript_text}"
        generated_text = generate_summary_sync(prompt)

        filename_match = re.search(r'FILENAME:\s*\[?([A-Za-z0-9_\s]+)\]?', generated_text)
        if filename_match:
            suggested_name = filename_match.group(1).strip().replace(" ", "_")
            generated_text = re.sub(r'\n*FILENAME:.*$', '', generated_text, flags=re.MULTILINE).strip()
        else:
            suggested_name = "Untitled"

        now = datetime.now()
        outline_filename = f"{suggested_name}_{now.strftime('%Y-%m-%d')}.md"
        outline_path = OUTLINES_DIR / outline_filename

        counter = 1
        while outline_path.exists():
            outline_filename = f"{suggested_name}_{now.strftime('%Y-%m-%d')}_{counter}.md"
            outline_path = OUTLINES_DIR / outline_filename
            counter += 1

        with open(outline_path, "w", encoding="utf-8") as f:
            f.write(generated_text)

        logger.info(f"Summarization completed: {outline_filename} ({len(generated_text)} chars)")
        return JSONResponse(content={
            "outline_file": outline_filename,
            "content": generated_text,
            "status": "success"
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Summarization failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/summarize-direct")
def summarize_direct_text(request: DirectTextRequest):
    """Changed to sync def so FastAPI runs it in threadpool."""
    try:
        if not GEMINI_API_KEY:
            logger.error("Summarize attempted without GEMINI_API_KEY configured")
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")

        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Text content is required")

        template_path = validate_path(PROMPTS_DIR, request.template)
        if not template_path.exists():
            logger.warning(f"Summarize requested for missing template: {request.template}")
            raise HTTPException(status_code=404, detail="Template file not found")

        with open(template_path, "r", encoding="utf-8") as f:
            template_text = f.read()

        logger.info(f"Starting direct text summarization with template {request.template} ({len(request.text)} chars)")

        prompt = f"{template_text}\n\nTranscript:\n{request.text}"
        generated_text = generate_summary_sync(prompt)

        filename_match = re.search(r'FILENAME:\s*\[?([A-Za-z0-9_\s]+)\]?', generated_text)
        if filename_match:
            suggested_name = filename_match.group(1).strip().replace(" ", "_")
            generated_text = re.sub(r'\n*FILENAME:.*$', '', generated_text, flags=re.MULTILINE).strip()
        else:
            suggested_name = "Untitled"

        now = datetime.now()
        outline_filename = f"{suggested_name}_{now.strftime('%Y-%m-%d')}.md"
        outline_path = OUTLINES_DIR / outline_filename

        counter = 1
        while outline_path.exists():
            outline_filename = f"{suggested_name}_{now.strftime('%Y-%m-%d')}_{counter}.md"
            outline_path = OUTLINES_DIR / outline_filename
            counter += 1

        with open(outline_path, "w", encoding="utf-8") as f:
            f.write(generated_text)

        # Save the original text to transcripts folder
        transcript_filename = f"{suggested_name}_{now.strftime('%Y-%m-%d')}.md"
        transcript_path = TRANSCRIPTS_DIR / transcript_filename
        counter = 1
        while transcript_path.exists():
            transcript_filename = f"{suggested_name}_{now.strftime('%Y-%m-%d')}_{counter}.md"
            transcript_path = TRANSCRIPTS_DIR / transcript_filename
            counter += 1

        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(request.text)

        logger.info(f"Direct text summarization completed: {outline_filename} ({len(generated_text)} chars)")
        return JSONResponse(content={
            "outline_file": outline_filename,
            "transcript_file": transcript_filename,
            "content": generated_text,
            "text": request.text,
            "status": "success"
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Direct text summarization failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    logger.info("=" * 60)
    logger.info("VocTation server starting on http://127.0.0.1:8000")
    logger.info(f"Using Gemini model: {GEMINI_MODEL}")
    logger.info("=" * 60)
    uvicorn.run(app, host="127.0.0.1", port=8000)
