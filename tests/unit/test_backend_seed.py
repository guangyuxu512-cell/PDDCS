from __future__ import annotations

import json
import runpy
from contextlib import closing
from pathlib import Path

import pytest

from backend.db import database


def _cleanup_database_files(db_path: Path) -> None:
    for path in (db_path, Path(f"{db_path}-shm"), Path(f"{db_path}-wal")):
        path.unlink(missing_ok=True)


@pytest.fixture()
def isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_dir = tmp_path / "data"
    db_path = db_dir / "seed.db"
    monkeypatch.setattr(database, "DB_DIR", db_dir)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    _cleanup_database_files(db_path)
    yield db_path
    _cleanup_database_files(db_path)


def test_seed_module_inserts_expected_records(isolated_database: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runpy.run_module("backend.db.seed", run_name="__main__")
    output = capsys.readouterr().out

    assert "✅ 种子数据插入完成" in output

    with closing(database.get_connection()) as conn:
        shops = conn.execute("SELECT * FROM shops ORDER BY name").fetchall()
        configs = conn.execute("SELECT * FROM shop_configs ORDER BY shop_id").fetchall()
        sessions = conn.execute("SELECT * FROM sessions ORDER BY buyer_name").fetchall()
        messages = conn.execute(
            "SELECT sender, content FROM messages ORDER BY created_at ASC"
        ).fetchall()
        knowledge_files = conn.execute(
            "SELECT name, path, node_type, parent_path, content FROM knowledge_files ORDER BY sort_order, path"
        ).fetchall()

    assert len(shops) == 2
    assert shops[0]["name"] == "测试抖店"
    assert shops[1]["name"] == "测试拼多多店铺"
    assert shops[1]["is_online"] == 1
    assert shops[1]["ai_enabled"] == 1
    assert shops[1]["cookie_valid"] == 1
    assert shops[1]["today_served_count"] == 35
    assert shops[1]["last_active_at"] != ""

    assert len(configs) == 2
    config_by_human = {row["human_agent_name"]: row for row in configs}
    assert json.loads(config_by_human["客服小王"]["knowledge_paths"]) == ["退款话术.md"]
    assert json.loads(config_by_human["客服小王"]["escalation_rules"]) == [
        {"id": "r1", "type": "keyword", "value": "退款,投诉"}
    ]
    assert config_by_human["客服小王"]["use_global_knowledge"] == 1
    assert any(row["human_agent_name"] == "" for row in configs)

    assert [(row["buyer_name"], row["status"]) for row in sessions] == [
        ("买家张三", "ai_processing"),
        ("买家李四", "escalated"),
        ("买家王五", "closed"),
    ]
    assert [(row["sender"], row["content"]) for row in messages] == [
        ("buyer", "你好，我买的东西还没发货"),
        ("ai", "亲，帮您查一下订单状态，请稍等~"),
        ("buyer", "好的谢谢"),
        ("ai", "亲，您的订单已经发出，预计明天到达哦~"),
    ]
    assert [(row["name"], row["node_type"], row["parent_path"]) for row in knowledge_files] == [
        ("售后话术", "folder", None),
        ("退款话术.md", "file", "售后话术"),
        ("物流话术.md", "file", "售后话术"),
    ]
    assert knowledge_files[1]["content"].startswith("# 退款话术")
    assert knowledge_files[2]["content"].startswith("# 物流话术")


def test_seed_module_is_idempotent_when_run_twice(isolated_database: Path) -> None:
    runpy.run_module("backend.db.seed", run_name="__main__")
    runpy.run_module("backend.db.seed", run_name="__main__")

    with closing(database.get_connection()) as conn:
        shop_count = conn.execute("SELECT COUNT(*) FROM shops").fetchone()[0]
        config_count = conn.execute("SELECT COUNT(*) FROM shop_configs").fetchone()[0]
        session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        message_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        knowledge_count = conn.execute("SELECT COUNT(*) FROM knowledge_files").fetchone()[0]

    assert shop_count == 2
    assert config_count == 2
    assert session_count == 3
    assert message_count == 4
    assert knowledge_count == 3
