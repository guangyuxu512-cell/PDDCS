"""适配器抽象基类，所有平台适配器实现此接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RawMessage:
    """从平台抓取到的原始消息。"""

    session_id: str
    buyer_id: str
    buyer_name: str
    content: str
    sender: str
    timestamp: str
    dedup_key: str


@dataclass
class SessionInfo:
    """会话基本信息。"""

    session_id: str
    buyer_id: str
    buyer_name: str
    last_message: str = ""
    unread: bool = False


class BaseAdapter(ABC):
    """平台适配器抽象基类。"""

    @abstractmethod
    async def navigate_to_chat(self) -> None:
        """导航到客服聊天页面。"""

    @abstractmethod
    async def get_session_list(self) -> list[SessionInfo]:
        """获取左侧会话列表。"""

    @abstractmethod
    async def switch_to_session(self, session_id: str) -> None:
        """切换到指定会话。"""

    @abstractmethod
    async def fetch_messages(self, session_id: str) -> list[RawMessage]:
        """抓取当前会话的消息列表。"""

    @abstractmethod
    async def send_message(self, session_id: str, text: str) -> bool:
        """向当前会话发送消息。"""

    @abstractmethod
    async def trigger_escalation(self, session_id: str, target_agent: str) -> bool:
        """RPA 操作：点击转人工按钮，转给指定客服。"""
