from backend.services.script_generator import generate_topic_script
import random
import uuid
import time
from datetime import datetime
from backend.constants import GD_TOPICS
from backend.database import db
from backend.gd_schemas import ParticipantRole, ParticipantModel, RoomModel, TranscriptEntry
from .ai_agent import process_ai_turn

from concurrent.futures import ThreadPoolExecutor

# Parallel executor for script generation
executor = ThreadPoolExecutor(max_workers=10)

def process_single_room(group, sessionId, database):
    """ Helper to process a single room's creation in parallel. """
    try:
        human_count = len(group)
        ai_needed = 5 - human_count
        
        room_id = str(uuid.uuid4())
        room_participants = []
        
        # Add Humans
        for human in group:
            room_participants.append(human["peerId"])
            database["participants"].update_one(
                {"_id": human["_id"]},
                {"$set": {"roomId": room_id}}
            )
            
        # Add AI
        for _ in range(ai_needed):
            ai_peer_id = f"ai-{uuid.uuid4()}"
            ai_participant = ParticipantModel(
                participantId=str(uuid.uuid4()),
                sessionId=sessionId,
                peerId=ai_peer_id,
                role=ParticipantRole.AI,
                name=f"AI Student", 
                roomId=room_id
            )
            database["participants"].insert_one(ai_participant.model_dump())
            room_participants.append(ai_peer_id)
            
        # Select Random Topic & Generate Script
        topic = random.choice(GD_TOPICS)
        print(f"[Allocation] Room {room_id}: Generating script for topic '{topic}'...")
        script = generate_topic_script(topic)
        
        # Create Room
        room = RoomModel(
            roomId=room_id,
            sessionId=sessionId,
            participants=room_participants,
            aiCount=ai_needed,
            topic=topic,
            script=script,
            current_script_index=0
        )
        database["rooms"].insert_one(room.model_dump())
        
        # Trigger Initial Greeting
        if ai_needed > 0:
            first_ai = room_participants[len(group)]
            greeting_text = f"Hello everyone! The topic is {topic}. "
            database["transcripts"].insert_one(TranscriptEntry(
                sessionId=sessionId,
                roomId=room_id,
                speakerId=first_ai,
                text=greeting_text,
                timestamp=datetime.utcnow()
            ).model_dump())
            
            # Start the AI turn logic
            process_ai_turn(room_id)

        print(f"[Allocation] Completed Room {room_id}")
        return room_id

    except Exception as e:
        print(f"Error processing room: {e}")
        return None

def allocate_rooms(sessionId: str):
    database = db.get_db()
    
    try:
        waiting_humans = list(database["participants"].find({
            "sessionId": sessionId,
            "roomId": None,
            "role": ParticipantRole.HUMAN.value
        }))
        
        if not waiting_humans:
            return {"message": "No waiting participants to allocate"}
        
        print(f"[Allocation] Starting parallel allocation for {len(waiting_humans)} humans")

        groups = [waiting_humans[i:i+5] for i in range(0, len(waiting_humans), 5)]
        
        # Run room processing in parallel
        futures = []
        for group in groups:
            futures.append(executor.submit(process_single_room, group, sessionId, database))
            
        results = [f.result() for f in futures]
        created_count = len([r for r in results if r is not None])

        return {"message": "Allocation complete", "rooms_created": created_count}

    except Exception as e:
        print(f"CRITICAL ERROR in allocate_rooms: {e}")
        return {"error": str(e)}

