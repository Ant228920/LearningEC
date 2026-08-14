from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.session import get_db
from schemas.task import TaskCreate, TaskUpdate, TaskResponse
from repository.task import TaskRepository

router = APIRouter()

def get_task_repo(db: Session = Depends(get_db)) -> TaskRepository:
    return TaskRepository(db)


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    task_in: TaskCreate,
    repo: TaskRepository = Depends(get_task_repo)
):
    return repo.create(task_in=task_in)


@router.get("/", response_model=list[TaskResponse])
def get_tasks(
    status: str | None = None,
    repo: TaskRepository = Depends(get_task_repo)
):
    return repo.get_all(status=status)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: int,
    repo: TaskRepository = Depends(get_task_repo)
):
    task = repo.get_by_id(task_id=task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Завдання не знайдено"
        )
    return task


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    task_update: TaskUpdate,
    repo: TaskRepository = Depends(get_task_repo)
):
    updated_task = repo.update(task_id=task_id, task_update=task_update)
    if not updated_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Завдання не знайдено"
        )
    return updated_task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    repo: TaskRepository = Depends(get_task_repo)
):
    is_deleted = repo.delete(task_id=task_id)
    if not is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Завдання не знайдено"
        )
    return None