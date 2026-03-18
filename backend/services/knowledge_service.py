"""知识库 CRUD 服务。"""

from __future__ import annotations

import uuid
from datetime import datetime

from backend.db.database import get_db
from backend.db.models import KnowledgeDocument, KnowledgeTreeNode


def get_tree() -> list[KnowledgeTreeNode]:
    """查询知识库树并组装层级结构。"""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM knowledge_files ORDER BY sort_order, name").fetchall()

    nodes_by_path: dict[str, dict[str, object]] = {}
    for row in rows:
        node = dict(row)
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
    """返回知识库文件路径列表。"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT path FROM knowledge_files WHERE node_type='file' ORDER BY sort_order, name"
        ).fetchall()
    return [str(row["path"]) for row in rows]


def get_document(path: str) -> KnowledgeDocument | None:
    """查询知识库文档。"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT path, content, updated_at FROM knowledge_files WHERE path=? AND node_type='file'",
            (path,),
        ).fetchone()
    return KnowledgeDocument.model_validate(dict(row)) if row is not None else None


def save_document(path: str, content: str) -> KnowledgeDocument | None:
    """保存知识库文档内容。"""
    now = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE knowledge_files SET content=?, updated_at=? WHERE path=? AND node_type='file'",
            (content, now, path),
        )
        if cursor.rowcount == 0:
            return None
        row = conn.execute(
            "SELECT path, content, updated_at FROM knowledge_files WHERE path=? AND node_type='file'",
            (path,),
        ).fetchone()
    return KnowledgeDocument.model_validate(dict(row)) if row is not None else None


def create_document(parent_path: str, name: str) -> KnowledgeDocument:
    """创建知识库文档。"""
    now = datetime.now().isoformat()
    path = f"{parent_path}/{name}" if parent_path else name
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO knowledge_files (
                id,
                name,
                path,
                node_type,
                parent_path,
                content,
                created_at,
                updated_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (str(uuid.uuid4()), name, path, "file", parent_path or None, "", now, now),
        )
    return KnowledgeDocument(path=path, content="", updated_at=now)


def delete_document(path: str) -> bool:
    """删除知识库文档。"""
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM knowledge_files WHERE path=?", (path,))
    return cursor.rowcount > 0
