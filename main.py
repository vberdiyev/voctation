import os
import re
import logging
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/voctation.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI()

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
MODELS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

logger.info("VocTation started - directories initialized")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("Warning: GEMINI_API_KEY not found in environment")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

whisper_model = None

def load_whisper_model():
    global whisper_model
    if whisper_model is None:
        model_path = MODELS_DIR / "whisper-small"
        if model_path.exists():
            print(f"Loading Whisper model from local directory: {model_path}")
            whisper_model = WhisperModel(str(model_path), device="cpu", compute_type="int8")
        else:
            cache_path = Path.home() / ".cache" / "huggingface" / "hub" / "models--Systran--faster-whisper-small" / "snapshots" / "536b0662742c02347bc0e980a01041f333bce120"
            if cache_path.exists():
                print(f"Loading Whisper model from cache: {cache_path}")
                whisper_model = WhisperModel(str(cache_path), device="cpu", compute_type="int8")
            else:
                print(f"Loading Whisper model 'small' (will download if needed)...")
                whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
    return whisper_model


class TranscribeRequest(BaseModel):
    filename: str


class SummarizeRequest(BaseModel):
    transcript_file: str
    template: str


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/audio-files")
async def get_audio_files():
    files = []
    if AUDIO_DIR.exists():
        files = sorted([f.name for f in AUDIO_DIR.iterdir() if f.is_file()])
    return JSONResponse(content=files)


@app.get("/api/prompt-templates")
async def get_prompt_templates():
    templates = []
    if PROMPTS_DIR.exists():
        templates = sorted([f.name for f in PROMPTS_DIR.iterdir() if f.is_file() and f.suffix == ".md"])
    return JSONResponse(content=templates)


@app.post("/api/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")

        ext = Path(file.filename).suffix
        if not ext:
            ext = ".wav"

        now = datetime.now()
        filename = f"{now.strftime('%Y-%m-%d_%H-%M')}{ext}"

        file_path = AUDIO_DIR / filename

        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(f"Audio uploaded: {filename} ({len(content) / 1024 / 1024:.2f} MB)")
        return JSONResponse(content={"filename": filename, "status": "success"})
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/transcribe")
async def transcribe_audio(request: TranscribeRequest):
    try:
        audio_path = AUDIO_DIR / request.filename
        if not audio_path.exists():
            logger.warning(f"Transcribe requested for missing file: {request.filename}")
            raise HTTPException(status_code=404, detail="Audio file not found")

        logger.info(f"Starting transcription: {request.filename}")
        model = load_whisper_model()

        segments, info = model.transcribe(str(audio_path), language="ru", beam_size=5)

        text_parts = []
        for segment in segments:
            text_parts.append(segment.text)

        text = " ".join(text_parts).strip()

        transcript_filename = Path(request.filename).stem + ".md"
        transcript_path = TRANSCRIPTS_DIR / transcript_filename

        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(text)

        logger.info(f"Transcription completed: {transcript_filename} ({len(text)} chars)")
        return JSONResponse(content={
            "transcript_file": transcript_filename,
            "text": text,
            "status": "success"
        })

    except Exception as e:
        logger.error(f"Transcription failed for {request.filename}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/summarize")
async def summarize_transcript(request: SummarizeRequest):
    try:
        if not GEMINI_API_KEY:
            logger.error("Summarize attempted without GEMINI_API_KEY configured")
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")

        transcript_path = TRANSCRIPTS_DIR / request.transcript_file
        if not transcript_path.exists():
            logger.warning(f"Summarize requested for missing transcript: {request.transcript_file}")
            raise HTTPException(status_code=404, detail="Transcript file not found")

        template_path = PROMPTS_DIR / request.template
        if not template_path.exists():
            logger.warning(f"Summarize requested for missing template: {request.template}")
            raise HTTPException(status_code=404, detail="Template file not found")

        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript_text = f.read()

        with open(template_path, "r", encoding="utf-8") as f:
            template_text = f.read()

        logger.info(f"Starting summarization: {request.transcript_file} with template {request.template}")
        model = genai.GenerativeModel("gemini-3.5-flash")

        prompt = f"{template_text}\n\nTranscript:\n{transcript_text}"

        response = model.generate_content(prompt)
        generated_text = response.text

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

    except Exception as e:
        logger.error(f"Summarization failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    logger.info("=" * 60)
    logger.info("VocTation server starting on http://127.0.0.1:8000")
    logger.info("=" * 60)
    uvicorn.run(app, host="127.0.0.1", port=8000)
