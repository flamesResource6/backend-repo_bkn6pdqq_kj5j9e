import os
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Chatroom, Message, MessageCreate

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Utility to convert ObjectId to str recursively

def serialize_doc(doc):
    if not doc:
        return doc
    d = {**doc}
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    # convert any ObjectIds inside
    for k, v in list(d.items()):
        if isinstance(v, ObjectId):
            d[k] = str(v)
    return d


@app.get("/")
def read_root():
    return {"message": "Chat API running"}


# Chatrooms REST endpoints

@app.post("/api/rooms")
def create_room(room: Chatroom):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    room_id = create_document("chatroom", room)
    doc = db["chatroom"].find_one({"_id": ObjectId(room_id)})
    return serialize_doc(doc)


@app.get("/api/rooms")
def list_rooms():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    docs = get_documents("chatroom")
    return [serialize_doc(d) for d in docs]


@app.get("/api/rooms/{room_id}/messages")
def list_messages(room_id: str, limit: Optional[int] = 50):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    try:
        filter_q = {"room_id": room_id}
        cur = db["message"].find(filter_q).sort("created_at", 1)
        if limit:
            cur = cur.limit(limit)
        return [serialize_doc(d) for d in cur]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/rooms/{room_id}/messages")
def post_message(room_id: str, payload: MessageCreate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    # ensure room_id matches
    data = payload.model_dump()
    data["room_id"] = room_id
    msg_id = create_document("message", data)
    doc = db["message"].find_one({"_id": ObjectId(msg_id)})
    # broadcast to room via websocket manager
    WebSocketManager.broadcast_to_room(room_id, serialize_doc(doc))
    return serialize_doc(doc)


# Simple in-process websocket manager for real-time fan-out
class WebSocketManager:
    rooms: dict = {}  # room_id -> set[WebSocket]

    @classmethod
    async def connect(cls, room_id: str, websocket: WebSocket):
        await websocket.accept()
        if room_id not in cls.rooms:
            cls.rooms[room_id] = set()
        cls.rooms[room_id].add(websocket)

    @classmethod
    def remove(cls, room_id: str, websocket: WebSocket):
        if room_id in cls.rooms and websocket in cls.rooms[room_id]:
            cls.rooms[room_id].remove(websocket)
            if not cls.rooms[room_id]:
                del cls.rooms[room_id]

    @classmethod
    async def send_to_room(cls, room_id: str, message: dict):
        if room_id not in cls.rooms:
            return
        dead = []
        for ws in list(cls.rooms[room_id]):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            cls.rooms[room_id].discard(ws)

    @classmethod
    def broadcast_to_room(cls, room_id: str, message: dict):
        # Schedule send on all websockets; since FastAPI default loop, use background
        import asyncio
        asyncio.create_task(cls.send_to_room(room_id, message))


@app.websocket("/ws/rooms/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    try:
        await WebSocketManager.connect(room_id, websocket)
        while True:
            data = await websocket.receive_json()
            # Expecting { sender, content }
            msg = Message(room_id=room_id, sender=data.get("sender", "Anon"), content=data.get("content", ""))
            # persist and echo
            msg_id = create_document("message", msg)
            doc = db["message"].find_one({"_id": ObjectId(msg_id)})
            await WebSocketManager.send_to_room(room_id, serialize_doc(doc))
    except WebSocketDisconnect:
        WebSocketManager.remove(room_id, websocket)
    except Exception:
        WebSocketManager.remove(room_id, websocket)


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            collections = db.list_collection_names()
            response["collections"] = collections[:10]
            response["database"] = "✅ Connected & Working"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
