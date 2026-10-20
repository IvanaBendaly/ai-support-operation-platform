"""Administrative retrieval preview; support workflows call RetrievalService directly."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from northstar.retrieval.api import administrator
from northstar.retrieval.search import RetrievalResult, RetrievalService

router = APIRouter(
    prefix="/api/admin/retrieval", tags=["Retrieval"], dependencies=[Depends(administrator)]
)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)


@router.post("/search", response_model=RetrievalResult)
def search(body: SearchRequest, request: Request):
    return RetrievalService(
        request.app.state.sessions, request.app.state.settings.retrieval
    ).search(body.query)


@router.post("/index")
def rebuild(request: Request):
    return RetrievalService(
        request.app.state.sessions, request.app.state.settings.retrieval
    ).synchronize(force=True)
