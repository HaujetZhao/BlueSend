import asyncio
import sys
import uuid
import ctypes
from ctypes import wintypes
import winrt.windows.devices.bluetooth.genericattributeprofile as wdbg
import winrt.windows.storage.streams as wss
import keyboard
import logging
from rich.logging import RichHandler

# 全局变量
main_loop = None
characteristic_obj = None
push_buffer = []
monitored_sessions = {}

# 配置 Rich 日志系统
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False, show_time=True)]
)
logger = logging.getLogger("ble_receiver")

# 定义广播服务 UUID 和特征值 UUID（必须与手机网页端一致）
SERVICE_UUID = uuid.UUID("a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d")
CHAR_UUID = uuid.UUID("12345678-1234-5678-1234-567812345678")

# ======================================================================
# Win32 剪贴板读写函数（纯 Python 实现，零依赖）
# ======================================================================
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL

def get_clipboard_text():
    if not user32.OpenClipboard(None):
        return ""
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            text = ctypes.wstring_at(ptr)
            return text
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()

def set_clipboard_text(text):
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        text_bytes = (text + '\0').encode('utf-16le')
        size = len(text_bytes)
        
        h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not h_global:
            return False
            
        ptr = kernel32.GlobalLock(h_global)
        if not ptr:
            kernel32.GlobalFree(h_global)
            return False
            
        try:
            ctypes.memmove(ptr, text_bytes, size)
        finally:
            kernel32.GlobalUnlock(h_global)
            
        if not user32.SetClipboardData(CF_UNICODETEXT, h_global):
            kernel32.GlobalFree(h_global)
            return False
        return True
    finally:
        user32.CloseClipboard()

# ======================================================================
# 蓝牙连接状态管理
# ======================================================================
def clean_device_id(device_id_obj):
    """提取设备 ID 中的美观 MAC 地址，去掉冗长的前缀"""
    if not device_id_obj:
        return "未知设备"
    try:
        raw_id = device_id_obj.id
        cleaned = raw_id.replace("BluetoothLE#BluetoothLE", "")
        if "-" in cleaned:
            return cleaned.split("-")[-1].upper()
        return cleaned.upper()
    except:
        return str(device_id_obj)

def monitor_session(session):
    """监控蓝牙会话状态，以在控制台打印连接和断开日志"""
    if not session:
        return
    device_id_obj = session.device_id
    raw_id = device_id_obj.id if device_id_obj else "unknown"
    if raw_id not in monitored_sessions:
        mac_address = clean_device_id(device_id_obj)
        logger.info(f"[+] 手机蓝牙已连上 (设备: {mac_address})")
        
        def on_status_changed(sender, args):
            if args.status == wdbg.GattSessionStatus.CLOSED:
                mac_address = clean_device_id(sender.device_id)
                logger.info(f"[-] 手机蓝牙已断开 (设备: {mac_address})")
                monitored_sessions.pop(raw_id, None)
                try:
                    sender.close()
                except:
                    pass
                    
        try:
            session.add_session_status_changed(on_status_changed)
            monitored_sessions[raw_id] = session
        except Exception as e:
            logger.error(f"[-] 监听会话状态失败: {e}", exc_info=True)

# ======================================================================
# 蓝牙特征通知与数据写入处理
# ======================================================================
async def send_notification(text):
    """通过 GATT Notification 向已连接的网页端推送数据"""
    global characteristic_obj
    if not characteristic_obj:
        return
    try:
        data_bytes = text.encode('utf-8')
        writer = wss.DataWriter()
        writer.write_bytes(data_bytes)
        buf = writer.detach_buffer()
        await characteristic_obj.notify_value_async(buf)
    except Exception as ex:
        logger.error(f"[-] 发送蓝牙通知失败: {ex}")

async def handle_write_async(args, deferral):
    """在 asyncio 主循环中安全处理写入逻辑"""
    request = None
    try:
        # 在主线程中安全提取并监控会话状态
        try:
            session = args.session
            if session:
                monitor_session(session)
        except Exception as se:
            logger.error(f"[-] 获取 args.session 异常: {se}")

        # 异步获取写入请求数据
        request = await args.get_request_async()
        buf = request.value
        
        # 使用 DataReader 读取 buffer 字节流
        reader = wss.DataReader.from_buffer(buf)
        length = reader.unconsumed_buffer_length
        data_bytes = bytearray(length)
        reader.read_bytes(data_bytes)
        
        # 解码数据为文本
        text = data_bytes.decode('utf-8')
        if text:
            # 协议解析：T:文本，K:特殊按键，C:指令，L:手机端日志，或默认兼容文本
            if text.startswith("T:"):
                content = text[2:]
                keyboard.write(content)
            elif text.startswith("K:"):
                key_name = text[2:]
                if key_name != "connect":
                    try:
                        keyboard.send(key_name)
                    except Exception as ex:
                        logger.error(f"[-] 按键触发失败 ({key_name}): {ex}")
            elif text.startswith("C:push:start"):
                global push_buffer
                push_buffer = []
                logger.info("📋 [蓝牙推送] 开始接收剪贴板分包数据...")
            elif text.startswith("C:push:data:"):
                chunk = text[12:]
                push_buffer.append(chunk)
            elif text.startswith("C:push:end"):
                full_text = "".join(push_buffer)
                if set_clipboard_text(full_text):
                    logger.info(f"📋 [系统剪贴板] 推送成功 (来自蓝牙)，内容长度: {len(full_text)}")
                else:
                    logger.warning("📋 [系统剪贴板] 推送失败 (来自蓝牙)")
            elif text.startswith("C:pull:request"):
                content = get_clipboard_text()
                logger.info(f"📋 [系统剪贴板] 收到拉取请求，准备通过蓝牙发送剪贴板内容 (长度: {len(content)})")
                await send_notification("R:pull:start")
                chunk_size = 200
                for i in range(0, len(content), chunk_size):
                    chunk = content[i:i+chunk_size]
                    await send_notification(f"R:pull:data:{chunk}")
                    await asyncio.sleep(0.015)
                await send_notification("R:pull:end")
                logger.info("📋 [系统剪贴板] 蓝牙数据发送完成。")
            elif text.startswith("L:"):
                parts = text.split(":", 2)
                if len(parts) >= 3:
                    log_level = parts[1].upper()
                    msg = parts[2]
                    if log_level == "ERROR":
                        logger.error(f"🚨 [手机网页 ERROR] {msg}")
                    elif log_level == "WARNING":
                        logger.warning(f"⚠️ [手机网页 WARNING] {msg}")
                    else:
                        logger.info(f"📱 [手机网页 {log_level}] {msg}")
            else:
                keyboard.write(text)
            
    except Exception as e:
        logger.error(f"[-] 接收数据处理失败: {e}", exc_info=True)
    finally:
        # 无论处理是否异常，对于带 Response 的请求进行安全应答
        if request and request.option == wdbg.GattWriteOption.WRITE_WITH_RESPONSE:
            try:
                request.respond()
            except:
                pass
        # 通知底层 WinRT 异步操作已完成
        deferral.complete()

def on_write_requested(sender, args):
    """WinRT 蓝牙服务后台线程的 Write 事件回调"""
    # 申请延迟完成令牌，以进行跨线程的异步处理
    deferral = args.get_deferral()
    if main_loop:
        # 安全派发到主 event loop 执行
        asyncio.run_coroutine_threadsafe(handle_write_async(args, deferral), main_loop)
    else:
        deferral.complete()

async def main():
    global main_loop, characteristic_obj
    main_loop = asyncio.get_running_loop()
    
    logger.info("=== Windows BLE GATT 网页蓝牙接收服务端 ===")
    
    try:
        # 1. 初始化本地 GATT 服务提供者
        provider_result = await wdbg.GattServiceProvider.create_async(SERVICE_UUID)
        if provider_result.error != 0:
            logger.error(f"[-] 无法初始化 BLE 服务。错误码: {provider_result.error}")
            return
            
        provider = provider_result.service_provider
        
        # 2. 设置特征值属性为可写入与支持通知
        parameters = wdbg.GattLocalCharacteristicParameters()
        parameters.characteristic_properties = (
            wdbg.GattCharacteristicProperties.WRITE |
            wdbg.GattCharacteristicProperties.WRITE_WITHOUT_RESPONSE |
            wdbg.GattCharacteristicProperties.NOTIFY
        )
        
        # 3. 创建本地 GATT 特征值
        char_result = await provider.service.create_characteristic_async(CHAR_UUID, parameters)
        if char_result.characteristic is None:
            logger.error("[-] 创建特征值失败。")
            return
            
        characteristic = char_result.characteristic
        characteristic_obj = characteristic
        
        # 4. 注册事件监听函数
        characteristic.add_write_requested(on_write_requested)
        logger.info("[+] 成功注册蓝牙写入事件回调")
        
        # 5. 启动 BLE 广播 (带显式的可连接/可发现参数)
        adv_parameters = wdbg.GattServiceProviderAdvertisingParameters()
        adv_parameters.is_connectable = True
        adv_parameters.is_discoverable = True
        provider.start_advertising_with_parameters(adv_parameters)
        logger.info("[+] 蓝牙低功耗 (BLE) 广播服务已成功启动！")
        logger.info(f"   服务 (Service) UUID: {SERVICE_UUID}")
        logger.info(f"   特征 (Characteristic) UUID: {CHAR_UUID}")
        logger.info("电脑正处于 BLE 广播状态，可被手机网页扫描连接。")
        
    except Exception as e:
        logger.error(f"[-] 服务启动异常: {e}", exc_info=True)
        return

    # 维持主线程协程运行
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("[!] 收到退出指令，正在关闭 BLE 服务...")
    finally:
        try:
            provider.stop_advertising()
        except:
            pass
        logger.info("=== BLE 服务已安全关闭 ===")

if __name__ == "__main__":
    asyncio.run(main())
