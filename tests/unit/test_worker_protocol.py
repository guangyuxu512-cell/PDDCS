from __future__ import annotations

import pickle

from backend.workers.protocol import StartShop, WorkerHeartbeat


def test_worker_protocol_messages_are_pickleable() -> None:
    command = StartShop("shop-1", proxy="http://127.0.0.1:7890")
    heartbeat = WorkerHeartbeat(worker_id=2, shop_count=3, memory_mb=128.5)

    restored_command = pickle.loads(pickle.dumps(command))
    restored_heartbeat = pickle.loads(pickle.dumps(heartbeat))

    assert restored_command == command
    assert restored_heartbeat == heartbeat
