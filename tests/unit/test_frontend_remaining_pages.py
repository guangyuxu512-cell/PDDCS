from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"


def validate_required_substrings(content: str, required_substrings: list[str], label: str) -> None:
    missing = [item for item in required_substrings if item not in content]
    if missing:
        raise ValueError(f"{label} 缺少关键内容: {', '.join(missing)}")


def validate_forbidden_substrings(content: str, forbidden_substrings: list[str], label: str) -> None:
    existing = [item for item in forbidden_substrings if item in content]
    if existing:
        raise ValueError(f"{label} 不应包含: {', '.join(existing)}")


def test_remaining_business_page_files_exist() -> None:
    expected_files = {
      "src/views/ChatMonitor.vue",
      "src/views/KnowledgeBase.vue",
      "src/views/Settings.vue",
      "src/types/chat.ts",
      "src/types/knowledge.ts",
      "src/types/settings.ts",
      "src/api/chat.ts",
      "src/api/knowledge.ts",
      "src/api/settings.ts",
      "src/mock/chat.ts",
      "src/mock/knowledge.ts",
      "src/mock/settings.ts",
    }

    existing = {
        str(path.relative_to(FRONTEND_DIR)).replace("\\", "/")
        for path in FRONTEND_DIR.rglob("*")
        if path.is_file()
    }
    assert expected_files.issubset(existing)


def test_remaining_business_pages_contracts() -> None:
    chat_type = (FRONTEND_DIR / "src" / "types" / "chat.ts").read_text(encoding="utf-8")
    knowledge_type = (FRONTEND_DIR / "src" / "types" / "knowledge.ts").read_text(encoding="utf-8")
    settings_type = (FRONTEND_DIR / "src" / "types" / "settings.ts").read_text(encoding="utf-8")
    chat_api = (FRONTEND_DIR / "src" / "api" / "chat.ts").read_text(encoding="utf-8")
    knowledge_api = (FRONTEND_DIR / "src" / "api" / "knowledge.ts").read_text(encoding="utf-8")
    settings_api = (FRONTEND_DIR / "src" / "api" / "settings.ts").read_text(encoding="utf-8")
    chat_mock = (FRONTEND_DIR / "src" / "mock" / "chat.ts").read_text(encoding="utf-8")
    knowledge_mock = (FRONTEND_DIR / "src" / "mock" / "knowledge.ts").read_text(encoding="utf-8")
    settings_mock = (FRONTEND_DIR / "src" / "mock" / "settings.ts").read_text(encoding="utf-8")
    mock_index = (FRONTEND_DIR / "src" / "mock" / "index.ts").read_text(encoding="utf-8")
    chat_view = (FRONTEND_DIR / "src" / "views" / "ChatMonitor.vue").read_text(encoding="utf-8")
    knowledge_view = (FRONTEND_DIR / "src" / "views" / "KnowledgeBase.vue").read_text(encoding="utf-8")
    settings_view = (FRONTEND_DIR / "src" / "views" / "Settings.vue").read_text(encoding="utf-8")

    validate_required_substrings(
        chat_type,
        [
            "export type ChatSessionStatus = 'ai_processing' | 'escalated' | 'closed';",
            "export type ChatMessageSender = 'buyer' | 'ai' | 'human';",
            "export interface ChatSession",
            "messages: ChatMessage[];",
        ],
        "types/chat.ts",
    )
    validate_required_substrings(
        knowledge_type,
        [
            "export type KnowledgeNodeType = 'folder' | 'file';",
            "export interface KnowledgeTreeNode",
            "export interface KnowledgeDocument",
        ],
        "types/knowledge.ts",
    )
    validate_required_substrings(
        settings_type,
        [
            "export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';",
            "export interface SystemSettings",
            "defaultKeywords: string[];",
            "maxShops: number;",
        ],
        "types/settings.ts",
    )
    validate_required_substrings(
        chat_api,
        [
            "fetchChatSessions",
            "takeoverChatSession",
            "request.get<ApiResponse<ChatSession[]>>('/chat/sessions')",
            "request.post<ApiResponse<ChatSession>>(`/chat/sessions/${sessionId}/takeover`)",
        ],
        "api/chat.ts",
    )
    validate_required_substrings(
        knowledge_api,
        [
            "fetchKnowledgeTree",
            "fetchKnowledgeDocument",
            "saveKnowledgeDocument",
            "createKnowledgeDocument",
            "deleteKnowledgeDocument",
            "request.get<ApiResponse<KnowledgeTreeNode[]>>('/knowledge/tree')",
            "request.put<ApiResponse<KnowledgeDocument>>('/knowledge/document'",
        ],
        "api/knowledge.ts",
    )
    validate_required_substrings(
        settings_api,
        [
            "fetchSettings",
            "saveSettings",
            "request.get<ApiResponse<SystemSettings>>('/settings')",
            "request.put<ApiResponse<SystemSettings>>('/settings', settings)",
        ],
        "api/settings.ts",
    )
    validate_required_substrings(
        chat_mock,
        [
            "url: '/api/chat/sessions'",
            "url: '/api/chat/sessions/:id/takeover'",
            "status: 'ai_processing'",
            "status: 'escalated'",
            "status: 'closed'",
        ],
        "mock/chat.ts",
    )
    validate_required_substrings(
        knowledge_mock,
        [
            "url: '/api/knowledge/tree'",
            "url: '/api/knowledge/document'",
            "method: 'get'",
            "method: 'put'",
            "method: 'post'",
            "method: 'delete'",
        ],
        "mock/knowledge.ts",
    )
    validate_required_substrings(
        settings_mock,
        [
            "url: '/api/settings'",
            "method: 'get'",
            "method: 'put'",
            "defaultKeywords",
            "maxShops: 10",
        ],
        "mock/settings.ts",
    )
    validate_required_substrings(
        mock_index,
        ["import './chat';", "import './knowledge';", "import './settings';"],
        "mock/index.ts",
    )
    validate_required_substrings(
        chat_view,
        [
            "<el-select v-model=\"shopFilter\"",
            "<el-select v-model=\"statusFilter\"",
            "<el-scrollbar class=\"chat-monitor__session-scroll\">",
            "接管此会话",
            "fetchChatSessions",
            "takeoverChatSession",
            "chat-monitor__message--buyer",
            "chat-monitor__message--ai",
        ],
        "views/ChatMonitor.vue",
    )
    validate_required_substrings(
        knowledge_view,
        [
            "<el-tree",
            "新增文件",
            "删除文件",
            "Markdown 文件",
            "fetchKnowledgeTree",
            "saveKnowledgeDocument",
            "createKnowledgeDocument",
            "deleteKnowledgeDocument",
            "最后保存时间",
        ],
        "views/KnowledgeBase.vue",
    )
    validate_required_substrings(
        settings_view,
        [
            "全局 LLM 配置",
            "全局转人工默认规则",
            "系统配置",
            "el-input-number",
            "默认关键词列表",
            "fetchSettings",
            "saveSettings",
            ">保存<",
        ],
        "views/Settings.vue",
    )
    validate_forbidden_substrings(
        chat_view + knowledge_view + settings_view,
        [
            "预留实时会话列表、消息气泡和状态筛选区域。",
            "预留 Markdown 编辑器和版本管理区，Step 1 只验证页面挂载。",
            "预留系统配置、通知渠道和全局开关管理区域。",
        ],
        "remaining views",
    )


def test_remaining_pages_validation_helpers_raise() -> None:
    with pytest.raises(ValueError):
        validate_required_substrings("partial", ["missing"], "sample")

    with pytest.raises(ValueError):
        validate_forbidden_substrings("contains bad", ["bad"], "sample")
