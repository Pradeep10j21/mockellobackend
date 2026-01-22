from fastapi import APIRouter, UploadFile, File, HTTPException
import os
import shutil
import urllib.request
import json
import requests

router = APIRouter(
    prefix="/ai-interviewer",
    tags=["ai-interviewer"]
)

import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Pool of keys from environment
AI_API_KEYS = os.getenv("AI_API_KEYS", "") or GROQ_API_KEY
keys = [k.strip() for k in AI_API_KEYS.split(",") if k.strip()]

def get_rotated_key():
    if not keys: return GROQ_API_KEY
    return random.choice(keys)

@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    print(f"[Backend] Received audio file: {file.filename}, Content-Type: {file.content_type}")
    
    file_id = str(uuid.uuid4())
    debug_filename = f"temp_audio_{file_id}_{file.filename}"
    
    try:
        with open(debug_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        file_size = os.path.getsize(debug_filename)
        if file_size == 0:
            if os.path.exists(debug_filename):
                os.remove(debug_filename)
            raise HTTPException(status_code=400, detail="Empty audio file received")

        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        
        def call_groq():
            api_key = get_rotated_key()
            with open(debug_filename, "rb") as f:
                files = {'file': (file.filename, f, file.content_type)}
                data = {
                    'model': 'whisper-large-v3',
                    'language': 'en',
                    'response_format': 'json'
                }
                headers = {'Authorization': f'Bearer {api_key}'}
                return requests.post(url, headers=headers, files=files, data=data)

        print("[Backend] Sending request to Groq...")
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(executor, call_groq)
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"Groq API Error: {response.text}")
        
        result = response.json()
        return {"text": result.get('text', '')}

    except Exception as e:
        print(f"[Backend] Transcription error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(debug_filename):
            try:
                os.remove(debug_filename)
            except:
                pass

@router.post("/chat")
async def chat_completion(payload: dict):
    url = "https://api.groq.com/openai/v1/chat/completions"
    model = payload.get("model", "llama-3.3-70b-versatile")
    
    try:
        def call_chat():
            api_key = get_rotated_key()
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            groq_payload = {
                "model": model,
                "messages": payload.get("messages", []),
                "temperature": payload.get("temperature", 0.7),
                "max_tokens": payload.get("max_tokens", 1024),
            }
            return requests.post(url, headers=headers, json=groq_payload)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(executor, call_chat)
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"Groq API Error: {response.text}")
            
        return response.json()

    except Exception as e:
        print(f"[Backend] Chat Exception: {e}")
        raise HTTPException(status_code=500, detail=str(e))


