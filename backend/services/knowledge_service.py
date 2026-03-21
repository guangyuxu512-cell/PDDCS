"""知识库 CRUD 服务。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select

from backend.db.database import get_sync_session
from backend.db.models import KnowledgeDocument, KnowledgeTreeNode
from backend.db.orm import KnowledgeFileTable, orm_object_to_dict


def get_tree() -> list[KnowledgeTreeNode]:
    with get_sync_session() as session:
        rows = session.scalars(
            select(KnowledgeFileTable).order_by(KnowledgeFileTable.sort_order, KnowledgeFileTable.name)
        ).all()

    nodes_by_path: dict[str, dict[str, object]] = {}
    for row in rows:
        node = orm_object_to_dict(row)
        node["children"] = [] if node["node_type"] == "folder" else None
        nodes_by_path[str(node["path"])] = node

    roots: list[dict[str, object]] = []
    for node in nodes_by_path.values():
        parent_path = node.get("parent_path")
        if parent_path and parent_path in nodes_by_path:
            parent_node = nodes_by_path[str(parent_path)]
            if parent_node["children"] is not None:
                parent_node["children"].append(node)
        else:
            roots.append(node)

    return [KnowledgeTreeNode.model_validate(root) for root in roots]


def get_file_list() -> list[str]:
    with get_sync_session() as session:
        rows = session.scalars(
            select(KnowledgeFileTable.path)
            .where(KnowledgeFileTable.node_type == "file")
            .order_by(KnowledgeFileTable.sort_order, KnowledgeFileTable.name)
        ).all()
        return [str(row) for row in rows]


def get_document(path: str) -> KnowledgeDocument | None:
    with get_sync_session() as session:
        row = session.scalar(
            select(KnowledgeFileTable).where(
                KnowledgeFileTable.path == path,
                KnowledgeFileTable.node_type == "file",
            )
        )
        if row is None:
            return None
        return KnowledgeDocument(path=row.path, content=row.content, updated_at=row.updated_at)


def save_document(path: str, content: str) -> KnowledgeDocument | None:
    now = datetime.now().isoformat()
    with get_sync_session() as session:
        row = session.scalar(
            select(KnowledgeFileTable).where(
                KnowledgeFileTable.path == path,
                KnowledgeFileTable.node_type == "file",
            )
        )
        if row is None:
            return None
        row.content = content
        row.updated_at = now
        session.flush()
        return KnowledgeDocument(path=row.path, content=row.content, updated_at=row.updated_at)


def create_document(parent_path: str, name: str) -> KnowledgeDocument:
    now = datetime.now().isoformat()
    path = f"{parent_path}/{name}" if parent_path else name
    with get_sync_session() as session:
        row = KnowledgeFileTable(
            id=str(uuid.uuid4()),
            name=name,
            path=path,
            node_type="file",
            parent_path=parent_path or None,
            content="",
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    return KnowledgeDocument(path=path, content="", updated_at=now)


def delete_document(path: str) -> bool:
    with get_sync_session() as session:
        row = session.scalar(select(KnowledgeFileTable).where(KnowledgeFileTable.path == path))
        if row is None:
            return False
        session.delete(row)
        return True
