"""协议常量：与 web/src/logic/protocol.js 保持一致。"""

import base64
import secrets
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


# 测速载荷大小：每次测速固定 256 KB。与 web/src/logic/protocol.js 保持一致。
BENCH_BYTES = 256 * 1024

# 文件上传服务的首选端口；被占用时回退到系统临时端口，实际端口随 net 消息下发。
UPLOAD_PORT = 8377


def bench_payload() -> str:
    """每次随机生成测速载荷。

    不能用重复模式：换两片之后仍是合法 JSON、内容长度也一样，根本验不出来。
    base64 是纯 ASCII，JSON 编码不产生转义，字符数即字节数；262144 能被 3 整除，
    编码不带补位符，长度正好是 BENCH_BYTES。
    """
    return base64.b64encode(secrets.token_bytes(BENCH_BYTES // 4 * 3)).decode()
