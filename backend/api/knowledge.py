from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from backend.api.response import fail, ok
from backend.services.knowledge_service import (
    create_document,
    delete_document,
    get_document,
    get_file_list,
    get_tree,
    save_document,
)


router = APIRouter(tags=["knowledge"])


class SaveDocBody(BaseModel):
    path: str
    content: str


class CreateDocBody(BaseModel):
    parentPath: str
    name: str


class DeleteDocBody(BaseModel):
    path: str


@router.get("/knowledge/tree")
async def api_tree() -> dict[str, Any]:
    tree = get_tree()
    return ok([node.model_dump() for node in tree])


@router.get("/knowledge/files")
async def api_file_list() -> dict[str, Any]:
    return ok(get_file_list())


@router.get("/knowledge/document")
async def api_get_doc(path: str = Query(...)) -> dict[str, Any]:
    document = get_document(path)
    if document is None:
        return fail("文件不存在")
    return ok(document.model_dump())


@router.put("/knowledge/document")
async def api_save_doc(body: SaveDocBody) -> dict[str, Any]:
    document = save_document(body.path, body.content)
    if document is None:
        return fail("文件不存在")
    return ok(document.model_dump())


@router.post("/knowledge/document")
async def api_create_doc(body: CreateDocBody) -> dict[str, Any]:
    document = create_document(body.parentPath, body.name)
    return ok(document.model_dump())


@router.delete("/knowledge/document")
async def api_delete_doc(body: DeleteDocBody) -> dict[str, Any]:
    if not delete_document(body.path):
        return fail("文件不存在")
    return ok({"path": body.path})
