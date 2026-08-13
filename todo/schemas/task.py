from pydantic import BaseModel
from typing import Optional

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = "pending"
    level: Optional[str] = "beginner"

class CourseCreate(TaskBase):
    pass

class CourseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[float] = None

class CourseResponse(TaskBase):
    id: int

    class Config:
        from_attributes = True