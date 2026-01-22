from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict
import os
from backend.database import get_database
from datetime import datetime
from groq import Groq
import json
from backend.models import GDResult

import random
import asyncio
from concurrent.futures import ThreadPoolExecutor


class EvaluationRequest(BaseModel):
    sessionId: str
    roomId: str
    peerId: str


class EvaluationResponse(BaseModel):
    scores: Dict[str, float]
    feedback: str
    strengths: List[str]
    improvements: List[str]

# Provided API Key for Evaluation
AI_API_KEYS = os.getenv("AI_API_KEYS", "") or os.getenv("GROQ_API_KEY", "")
keys = [k.strip() for k in AI_API_KEYS.split(",") if k.strip()]

executor = ThreadPoolExecutor(max_workers=10)

router = APIRouter(prefix="/gd-evaluation", tags=["GD Evaluation"])

def get_rotated_key():
    if not keys: return os.getenv("GROQ_API_KEY")
    return random.choice(keys)

@router.post("/evaluate", response_model=EvaluationResponse)
async def evaluate_participant(req: EvaluationRequest):
    database = get_database()
    
    transcripts = list(database["transcripts"].find({
        "sessionId": req.sessionId,
        "roomId": req.roomId
    }).sort("timestamp", 1))
    
    if not transcripts:
        raise HTTPException(status_code=404, detail="No transcripts found for this session.")

    conversation_text = ""
    participant_speech = []
    
    for t in transcripts:
        speaker = t["speakerId"]
        text = t["text"]
        prefix = "Student"
        if speaker == req.peerId:
            prefix = "TARGET_STUDENT"
            participant_speech.append(text)
        elif speaker.startswith("ai-"):
            prefix = "AI_Participant"
        conversation_text += f"{prefix}: {text}\n"

    if not participant_speech:
         return EvaluationResponse(
             scores={"Participation": 0, "Creativity": 0, "Communication": 0, "Leadership": 0},
             feedback="You did not speak during the session.",
             strengths=[],
             improvements=["Speak up to be heard!"]
         )

    def run_eval():
        api_key = get_rotated_key()
        client = Groq(api_key=api_key)
        
        prompt = f"""
        Evaluate 'TARGET_STUDENT' performance (0-10) in this GD.
        Categories: Participation, Uniqueness, Creativity, Choice of Words, Leadership, Listening.
        Conversation:
        {conversation_text}
        Return pure JSON: {{ "scores": {{...}}, "feedback": "...", "strengths": [...], "improvements": [...] }}
        """
        
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "Return only JSON."},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        return json.loads(completion.choices[0].message.content)

    try:
        loop = asyncio.get_event_loop()
        result_json = await loop.run_in_executor(executor, run_eval)
        
        student_email = "unknown@student.com" 
        participant = database["participants"].find_one({"peerId": req.peerId, "sessionId": req.sessionId})
        if participant and "email" in participant:
            student_email = participant["email"]
        
        gd_result_entry = GDResult(
            student_email=student_email,
            session_id=req.sessionId,
            scores=result_json.get("scores", {}),
            feedback=result_json.get("feedback", "Analysis complete."),
            strengths=result_json.get("strengths", []),
            improvements=result_json.get("improvements", [])
        )
        database["gd_results"].insert_one(gd_result_entry.model_dump())

        return EvaluationResponse(
            scores=result_json.get("scores", {}),
            feedback=result_json.get("feedback", "Analysis complete."),
            strengths=result_json.get("strengths", []),
            improvements=result_json.get("improvements", [])
        )

    except Exception as e:
        print(f"Evaluation Error: {e}")
        raise HTTPException(status_code=500, detail="AI Evaluation Failed")

