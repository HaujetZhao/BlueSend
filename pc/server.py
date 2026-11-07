"""Windows 侧 BLE GATT Server：手机网页通过 Web Bluetooth 连上来，双向收发 JSON 消息。"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import keyboard
from winrt.windows.devices.bluetooth.genericattributeprofile import (
    GattCharacteristicProperties,
    GattCommunicationStatus,
    GattLocalCharacteristicParameters,
    GattProtectionLevel,
    GattServiceProvider,
    GattServiceProviderAdvertisingParameters,
    GattSessionStatus,
)
from winrt.windows.storage.streams import DataWriter

from clipboard import get_clipboard_text, set_clipboard_text
from frame_codec import Decoder, encode
from protocol import DOWNLINK_UUID, SERVICE_UUID, UPLINK_UUID, downlink_chunk_size

logger = logging.getLogger("ble")

HEARTBEAT_SECONDS = 3
FALLBACK_NOTIFICATION_SIZE = 20


def setup_logging() -> None:
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_dir / f"ble-{stamp}.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def to_buffer(data: bytes):
    writer = DataWriter()
    writer.write_bytes(data)
    return writer.detach_buffer()


async def main() -> None:
    decoder = Decoder()

    provider = (await GattServiceProvider.create_async(SERVICE_UUID)).service_provider
    logger.info("服务已创建 %s", SERVICE_UUID)

    # 上行只声明 WRITE：无响应写没有顺序保证，会让长文本的分片颠倒。
    # 不把 WRITE_WITHOUT_RESPONSE 写进属性，客户端想用也无从下手。
    uplink_params = GattLocalCharacteristicParameters()
    uplink_params.characteristic_properties = GattCharacteristicProperties.WRITE
    uplink_params.write_protection_level = GattProtectionLevel.PLAIN
    uplink = (
        await provider.service.create_characteristic_async(UPLINK_UUID, uplink_params)
    ).characteristic
    logger.info("上行特征值已创建 %s（手机写入）", UPLINK_UUID)

    downlink_params = GattLocalCharacteristicParameters()
    downlink_params.characteristic_properties = GattCharacteristicProperties.NOTIFY
    downlink = (
        await provider.service.create_characteristic_async(DOWNLINK_UUID, downlink_params)
    ).characteristic
    logger.info("下行特征值已创建 %s（电脑通知）", DOWNLINK_UUID)

    loop = asyncio.get_running_loop()
    incoming: asyncio.Queue[bytes] = asyncio.Queue()
    send_lock = asyncio.Lock()
    notification_size = FALLBACK_NOTIFICATION_SIZE

    def on_write_requested(sender, args) -> None:
        """这条回调跑在 WinRT 自己的线程上。

        请求必须在这条线程上同步取到并完成：deferral / respond 都有线程亲和性，
        跨线程完成会让 ATT 事务在 30 秒后超时，整条链路随之断开。
        取到字节后只把数据投递给 asyncio 线程，业务处理留在那边做。
        """
        try:
            request = args.get_request_async().get()
            data = bytes(request.value)
            # 上行只声明了 WRITE，写请求必然是带响应的，直接应答即可。
            request.respond()
        except Exception:
            logger.exception("处理写入请求失败")
            return
        loop.call_soon_threadsafe(incoming.put_nowait, data)

    uplink.add_write_requested(on_write_requested)

    def on_max_notification_size_changed(client, _args) -> None:
        nonlocal notification_size
        notification_size = downlink_chunk_size(client.max_notification_size)
        logger.info("通知分片上限：%d 字节", notification_size)

    watched: set[str] = set()

    def on_session_status_changed(session, _args) -> None:
        state = "已连接" if session.session_status == GattSessionStatus.ACTIVE else "已断开"
        logger.info("链路状态：%s", state)

    def on_subscribed_changed(sender, args) -> None:
        clients = list(downlink.subscribed_clients)
        logger.info("订阅变化：当前 %d 个订阅客户端", len(clients))
        for client in clients:
            key = str(client.session.device_id)
            if key in watched:
                continue
            watched.add(key)
            client.add_max_notification_size_changed(on_max_notification_size_changed)
            client.session.add_session_status_changed(on_session_status_changed)
            on_max_notification_size_changed(client, None)

    downlink.add_subscribed_clients_changed(on_subscribed_changed)

    async def notify(message: dict) -> bool:
        """发出消息，返回是否至少有一个订阅客户端收到了。"""
        data = encode(json.dumps(message, ensure_ascii=False))
        delivered = False
        async with send_lock:
            # 取一份快照：发送途中订阅变化可能改写 notification_size，
            # 步长与切片长度必须用同一个值，否则会漏字节。
            size = notification_size
            for i in range(0, len(data), size):
                # 没人订阅时这里返回空列表，不会报错——所以必须逐条检查结果
                results = await downlink.notify_value_async(
                    to_buffer(data[i:i + size])
                )
                for result in results:
                    if result.status != GattCommunicationStatus.SUCCESS:
                        logger.warning(
                            "通知发送失败：%s（协议错误 %s，已发 %d 字节）",
                            result.status,
                            result.protocol_error,
                            result.bytes_sent,
                        )
                    else:
                        delivered = True
        return delivered

    async def heartbeat_loop() -> None:
        alive = None
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            try:
                delivered = await notify({"t": "hb"})
            except Exception:
                logger.exception("心跳发送失败")
                continue
            if delivered != alive:
                alive = delivered
                logger.info("心跳投递：%s", "正常" if delivered else "没有订阅客户端")

    async def handle(message: dict) -> None:
        kind = message.get("t")
        if kind == "text":
            keyboard.write(message.get("v", ""))
        elif kind == "key":
            keyboard.send(message.get("v", ""))
        elif kind == "clip":
            text = message.get("v", "")
            logger.info("收到剪贴板推送 %d 字", len(text))
            if not set_clipboard_text(text):
                logger.warning("写入系统剪贴板失败")
        elif kind == "pull":
            text = get_clipboard_text()
            logger.info("拉取系统剪贴板 %d 字", len(text))
            await notify({"t": "clip", "v": text})
        elif kind == "ping":
            await notify({"t": "pong"})
        elif kind == "log":
            logger.info("[网页] %s", message.get("v", ""))
        else:
            logger.warning("未知消息类型 %r", kind)

    async def read_loop() -> None:
        while True:
            for payload in decoder.feed(await incoming.get()):
                logger.info("收到消息 %s", payload[:200])
                # 收到的是链路对端（可能是任意一台设备）发来的字节，坏消息不该拖垮整个服务
                try:
                    await handle(json.loads(payload))
                except Exception:
                    logger.exception("处理消息失败：%s", payload[:200])

    def on_advertisement_status_changed(sender, _args) -> None:
        # start_advertising 是异步生效的，读一次 provider.advertisement_status 会拿到旧值（Aborted），
        # 只有状态变更事件里的才是真实结果。
        logger.info("广播状态：%s", sender.advertisement_status)

    provider.add_advertisement_status_changed(on_advertisement_status_changed)

    advertising = GattServiceProviderAdvertisingParameters()
    advertising.is_connectable = True
    advertising.is_discoverable = True
    provider.start_advertising(advertising)

    heartbeat = asyncio.create_task(heartbeat_loop())
    try:
        await read_loop()
    finally:
        heartbeat.cancel()
        provider.stop_advertising()
        logger.info("停止广播")


if __name__ == "__main__":
    setup_logging()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("退出")
