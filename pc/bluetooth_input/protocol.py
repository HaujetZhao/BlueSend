"""协议常量：与 web/src/logic/protocol.js 保持一致。"""

from uuid import UUID

SERVICE_UUID = UUID("7d9f0001-3c4e-4b6a-9f2e-1a2b3c4d5e6f")
# 上行：手机写入，电脑接收。
UPLINK_UUID = UUID("7d9f0002-3c4e-4b6a-9f2e-1a2b3c4d5e6f")
# 下行：电脑通知，手机接收。
DOWNLINK_UUID = UUID("7d9f0003-3c4e-4b6a-9f2e-1a2b3c4d5e6f")

# 下行通知单包上限。Android 的 GATT 客户端栈会静默丢弃 value.len 大于
# GATT_MAX_ATTR_LEN（512 字节）的通知，而 Windows 报告的 max_notification_size
# 是 MTU-3（实测 514）。不夹紧的话，长消息的整分片会在手机侧丢光，
# 只剩末尾的短分片，帧永远拼不完整。
DOWNLINK_CHUNK_LIMIT = 512


def downlink_chunk_size(reported: int) -> int:
    return min(reported, DOWNLINK_CHUNK_LIMIT)
