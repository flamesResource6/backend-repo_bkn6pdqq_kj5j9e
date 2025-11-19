"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional

# Chat application schemas

class Chatroom(BaseModel):
    """
    Chat rooms collection schema
    Collection name: "chatroom"
    """
    name: str = Field(..., description="Room display name")
    description: Optional[str] = Field(None, description="Short description of the room")
    # creator, avatar etc. could be added later

class Message(BaseModel):
    """
    Messages collection schema
    Collection name: "message"
    """
    room_id: str = Field(..., description="ID of the room this message belongs to")
    sender: str = Field(..., description="Display name of the sender")
    content: str = Field(..., description="Message text content")
    # attachments, reactions, etc. could be added later

class MessageCreate(BaseModel):
    """
    Incoming payload for creating a message via REST or WebSocket client
    room_id comes from the path/connection context, so it is excluded here
    """
    sender: str = Field(..., description="Display name of the sender")
    content: str = Field(..., description="Message text content")

# Example schemas kept for reference (not used by the app right now)
class User(BaseModel):
    name: str
    email: str
    address: str
    age: Optional[int] = None
    is_active: bool = True

class Product(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    category: str
    in_stock: bool = True
