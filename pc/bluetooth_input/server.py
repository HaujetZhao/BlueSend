"""Windows 侧 BLE GATT Server：手机网页通过 Web Bluetooth 连上来，双向收发 JSON 消息。"""

import asyncio
import hashlib
import json
import logging
import time

import keyboard
from winrt.windows.devices.bluetooth import BluetoothError
from winrt.windows.devices.bluetooth.genericattributeprofile import (
    GattCharacteristicProperties,
    GattCommunicationStatus,
    GattLocalCharacteristicParameters,
    GattProtectionLevel,
    GattServiceProvider,
    GattServiceProviderAdvertisingParameters,
    GattSessionStatus,
    GattWriteOption,
)
from winrt.windows.storage.streams import DataWriter

from .clipboard import get_clipboard_text, set_clipboard_text
from .config import load_upload_folder, load_wm_char_apps
from .frame_codec import Decoder, FrameError, UplinkAssembler, encode
from .protocol import (
    DOWNLINK_UUID,
    SERVICE_UUID,
    UPLINK_UUID,
    bench_payload,
    downlink_chunk_size,
)
from .text_input import type_text
from .upload_server import start_upload_server

logger = logging.getLogger("ble")

HEARTBEAT_SECONDS = 3
FALLBACK_NOTIFICATION_SIZE = 20


def to_buffer(data: bytes):
    writer = DataWriter()
    writer.write_bytes(data)
    return writer.detach_buffer()


async def serve() -> None:
    decoder = Decoder()
    wm_char_apps = load_wm_char_apps()

    service_result = await GattServiceProvider.create_async(SERVICE_UUID)
    if service_result.error != BluetoothError.SUCCESS:
        logger.error("创建 GATT 服务失败：%s（蓝牙是否已开启？）", service_result.error)
        raise SystemExit(1)
    provider = service_result.service_provider
    logger.info("服务已创建 %s", SERVICE_UUID)

    # 上行声明 WRITE | WRITE_WITHOUT_RESPONSE：手机端中间分片用无响应写连续入队
    # （停等只有约 8 KB/s，无响应约 63 KB/s），最后一片用带响应写拿送达确认。
    # 顺序不靠 ATT 保证，靠网页端逐片 await 的提交纪律（实测 517 片零乱序，
    # 测速哈希作金丝雀，见坑 14）。
    uplink_params = GattLocalCharacteristicParameters()
    uplink_params.characteristic_properties = (
        GattCharacteristicProperties.WRITE
        | GattCharacteristicProperties.WRITE_WITHOUT_RESPONSE
    )
    uplink_params.write_protection_level = GattProtectionLevel.PLAIN
    uplink_result = await provider.service.create_characteristic_async(
        UPLINK_UUID, uplink_params
    )
    if uplink_result.error != BluetoothError.SUCCESS:
        logger.error("创建上行特征值失败：%s（蓝牙是否已开启？）", uplink_result.error)
        raise SystemExit(1)
    uplink = uplink_result.characteristic
    logger.info("上行特征值已创建 %s（手机写入）", UPLINK_UUID)

    downlink_params = GattLocalCharacteristicParameters()
    downlink_params.characteristic_properties = GattCharacteristicProperties.NOTIFY
    downlink_result = await provider.service.create_characteristic_async(
        DOWNLINK_UUID, downlink_params
    )
    if downlink_result.error != BluetoothError.SUCCESS:
        logger.error("创建下行特征值失败：%s（蓝牙是否已开启？）", downlink_result.error)
        raise SystemExit(1)
    downlink = downlink_result.characteristic
    logger.info("下行特征值已创建 %s（电脑通知）", DOWNLINK_UUID)

    # 文件上传走局域网 HTTP：蓝牙只负责把入口 URL 送到手机。入口地址随 net
    # 消息在每次订阅变化时下发（连接作用域，同 mtu）。
    uploads = start_upload_server(load_upload_folder())
    logger.info("文件上传入口：%s", "、".join(uploads.urls()) or "没有可用的局域网地址")

    loop = asyncio.get_running_loop()
    incoming: asyncio.Queue[bytes] = asyncio.Queue()
    send_lock = asyncio.Lock()
    notification_size = FALLBACK_NOTIFICATION_SIZE
    # 上行分片先经重组（剥 4 字节序号、按序还原）再进解码队列：写回调跑在
    # WinRT 线程池上，并发回调投递的字节顺序会颠倒。
    assembler = UplinkAssembler(
        lambda data: loop.call_soon_threadsafe(incoming.put_nowait, data)
    )

    def on_write_requested(sender, args) -> None:
        """这条回调跑在 WinRT 自己的线程上。

        请求必须在这条线程上同步取到并完成：deferral / respond 都有线程亲和性，
        跨线程完成会让 ATT 事务在 30 秒后超时，整条链路随之断开。
        取到字节后只把数据投递给 asyncio 线程，业务处理留在那边做。
        """
        request = None
        try:
            request = args.get_request_async().get()
            data = bytes(request.value)
            # 无响应写没有 ATT 事务，respond 会抛错，跳过；带响应写必须在这条
            # 线程上同步应答，否则 30 秒后整条链路断开（见坑 2）。
            if request.option == GattWriteOption.WRITE_WITH_RESPONSE:
                request.respond()
            request = None
            assembler.feed(data)
        except Exception:
            logger.exception("处理写入请求失败")
            # 取到请求却没应答，Windows 会一直等这次 ATT 事务，30 秒后整条链路断开。
            if request is not None:
                try:
                    request.respond()
                except Exception:
                    logger.exception("补发 ATT 响应失败")

    uplink.add_write_requested(on_write_requested)

    def on_max_notification_size_changed(client, _args) -> None:
        nonlocal notification_size
        notification_size = downlink_chunk_size(client.max_notification_size)
        logger.info("通知分片上限：%d 字节", notification_size)
        # 上行的写 PDU 与下行的通知 PDU 都是「操作码 1＋句柄 2＋值」，单片上限
        # 同为 MTU-3，所以这个数直接就是手机的上行线包上限。MTU 是外部事实，
        # 不能两边各写死 512：换台只协商出 247 甚至 23 的适配器，写满 512 会硬失败。
        size = notification_size
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(notify({"t": "mtu", "up": size}))
        )

    watched: set[str] = set()

    def on_session_status_changed(session, _args) -> None:
        state = "已连接" if session.session_status == GattSessionStatus.ACTIVE else "已断开"
        logger.info("链路状态：%s", state)

    def on_subscribed_changed(sender, args) -> None:
        clients = list(downlink.subscribed_clients)
        logger.info("订阅变化：当前 %d 个订阅客户端", len(clients))
        # 订阅变化只发生在连接边界。上行字节流是连接作用域的，旧连接写了一半
        # 的帧不能带进新连接，否则长度前缀会被读成任意值，解码器永久失步。
        # 重组器同样按连接清零（自带锁，直接调即可）。
        assembler.reset()
        loop.call_soon_threadsafe(decoder.reset)
        # 订阅清零，会话对象随之作废；下一轮订阅是全新对象，必须重新挂监听。
        if not clients:
            watched.clear()
        for client in clients:
            # 去重键取 .id（字符串）。不能用 str(device_id)：pywinrt 没给
            # BluetoothDeviceId 定义 __str__，拿到的是包装对象的内存地址，
            # 同一台设备两次取值的结果并不相等。
            key = client.session.device_id.id
            if key not in watched:
                watched.add(key)
                client.add_max_notification_size_changed(
                    on_max_notification_size_changed
                )
                client.session.add_session_status_changed(on_session_status_changed)
            # 上行上限是连接作用域的：网页端每条连接都把它复位成 ATT 最小值，
            # 所以每次订阅变化都要重新下发，不能按设备去重——漏一次，手机端
            # 就整条连接按 20 字节切。
            on_max_notification_size_changed(client, None)
        if clients:
            # 上传入口同样是连接作用域的。地址在重新连接时现算一次，电脑换了
            # 网络也能拿到新地址。
            loop.call_soon_threadsafe(
                lambda: asyncio.create_task(
                    notify({"t": "net", "hosts": uploads.urls()})
                )
            )

    downlink.add_subscribed_clients_changed(on_subscribed_changed)

    async def notify(message: dict) -> bool:
        """发出消息，返回它是否被完整送达至少一个订阅客户端。"""
        data = encode(json.dumps(message, ensure_ascii=False))
        delivered = False
        failed = False
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
                            "通知发送失败：%s（协议错误 %s，已发 %d 字节），中止剩余分片",
                            result.status,
                            result.protocol_error,
                            result.bytes_sent,
                        )
                        failed = True
                    else:
                        delivered = True
                # 中间少了一片的字节流没法补救，继续发只会把对端带得更偏。
                if failed:
                    return False
        return delivered and not failed

    async def bench_downlink() -> None:
        """发一条 256 KB 的下行测速消息。

        这里量不出空中耗时：notify_value_async 返回时只是把数据交给了 Windows
        的发送队列（实测 256 KB 入队只用 0.4 秒，而手机真收完要 2.7 秒），
        所以速率由手机按收到的字节自己算。

        载荷每次随机，并随 benchend 带上它的 SHA-256：手机用收到的内容重算、
        比对，分片一旦被调换或重复就能发现——固定载荷换两片照样是合法 JSON。
        """
        payload = bench_payload()
        digest = hashlib.sha256(payload.encode()).hexdigest()
        started = time.perf_counter()
        if not await notify({"t": "benchdata", "v": payload}):
            logger.warning("下行测速未发出")
            return
        logger.info(
            "下行测速：%d 字节已入队，耗时 %.1f 秒（空中耗时以手机端为准）",
            len(payload), time.perf_counter() - started,
        )
        await notify({
            "t": "benchend",
            "bytes": len(payload),
            "chunk": notification_size,
            "sha256": digest,
        })

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
            # 长文本会阻塞事件循环、憋住心跳；命中兼容名单时改投 WM_CHAR（见 text_input）。
            await asyncio.to_thread(
                type_text, message.get("v", ""), wm_char_apps
            )
        elif kind == "key":
            keyboard.send(message.get("v", ""))
        elif kind == "clip":
            text = message.get("v", "")
            logger.info("收到剪贴板推送 %d 字", len(text))
            if not set_clipboard_text(text):
                logger.warning("写入系统剪贴板失败")
        elif kind == "pull":
            text = get_clipboard_text()
            if text is None:
                # 读失败不等于剪贴板为空：发 clip 会清掉手机端已有的内容。
                logger.warning("读取系统剪贴板失败")
                await notify({"t": "notice", "v": "读取电脑剪贴板失败，请稍后重试"})
            else:
                logger.info("拉取系统剪贴板 %d 字", len(text))
                await notify({"t": "clip", "v": text})
        elif kind == "benchup":
            # 消息自带 sha256，重算比对：无响应写的分片若被调换，帧仍合法、
            # 长度也对，只有内容哈希能发现。失败用 notice 顶到手机事件行。
            payload = message.get("v", "")
            actual = hashlib.sha256(payload.encode()).hexdigest()
            if actual == message.get("sha256"):
                logger.info("上行测速：收到 %d 字节，校验通过", len(payload))
            else:
                logger.warning(
                    "上行测速：校验失败，收到 %s 应为 %s",
                    actual[:8], str(message.get("sha256"))[:8],
                )
                await notify({"t": "notice", "v": "上行测速校验失败：分片内容与发出不一致"})
        elif kind == "benchdown":
            await bench_downlink()
        elif kind == "ping":
            await notify({"t": "pong"})
        elif kind == "log":
            logger.info("[网页] %s", message.get("v", ""))
        else:
            logger.warning("未知消息类型 %r", kind)

    async def read_loop() -> None:
        while True:
            try:
                payloads = decoder.feed(await incoming.get())
            except FrameError as err:
                # 字节流已经对不上帧格式，继续解析只会越错越远；丢掉缓冲，
                # 等下一个连接边界重建（对端写失败也会断开重连）。
                decoder.reset()
                logger.warning("上行字节流异常，已丢弃缓冲：%s", err)
                continue
            for payload in payloads:
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
        uploads.stop()
        logger.info("停止广播")
