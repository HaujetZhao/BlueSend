import asyncio
import sys
import uuid
import winrt.windows.devices.bluetooth.genericattributeprofile as wdbg
import winrt.windows.storage.streams as wss
import keyboard

# 全局的 event loop，用于在外部线程回调触发时向主线程派发协程
main_loop = None

# 全局强引用活动的蓝牙会话，用以在 Python 侧维持生命周期，以便监听断开事件
monitored_sessions = {}

# 定义广播服务 UUID 和特征值 UUID（必须与手机网页端一致）
SERVICE_UUID = uuid.UUID("a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d")
CHAR_UUID = uuid.UUID("12345678-1234-5678-1234-567812345678")

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
        print(f"[+] 手机蓝牙已连上 (设备: {mac_address})")
        
        def on_status_changed(sender, args):
            if args.status == wdbg.GattSessionStatus.CLOSED:
                mac_address = clean_device_id(sender.device_id)
                print(f"[-] 手机蓝牙已断开 (设备: {mac_address})")
                monitored_sessions.pop(raw_id, None)
                try:
                    sender.close()
                except:
                    pass
                    
        try:
            session.add_session_status_changed(on_status_changed)
            monitored_sessions[raw_id] = session
        except Exception as e:
            print(f"[-] 监听会话状态失败: {e}")

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
            print(f"[-] 获取 args.session 异常: {se}")

        # 异步获取写入请求数据
        request = await args.get_request_async()
        buf = request.value
        
        # 使用 DataReader 读取 buffer 字节流
        reader = wss.DataReader.from_buffer(buf)
        length = reader.unconsumed_buffer_length
        data_bytes = bytearray(length)
        reader.read_bytes(data_bytes)
        
        # 解码数据为文本
        text = data_bytes.decode('utf-8').strip()
        if text:
            # 协议解析：T:文本，K:特殊按键控制，或默认文本兼容
            if text.startswith("T:"):
                content = text[2:]
                keyboard.write(content)
            elif text.startswith("K:"):
                key_name = text[2:]
                if key_name == "connect":
                    # 握手连接包，仅用于建立 session 与触发控制台连接日志，直接忽略
                    pass
                else:
                    try:
                        keyboard.send(key_name)
                    except Exception as ex:
                        print(f"[-] 按键触发失败 ({key_name}): {ex}")
            else:
                keyboard.write(text)
            
    except Exception as e:
        print(f"[-] 接收数据处理失败: {e}")
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
    global main_loop
    main_loop = asyncio.get_running_loop()
    
    print("=== Windows BLE GATT 网页蓝牙接收服务端 ===")
    
    try:
        # 1. 初始化本地 GATT 服务提供者
        provider_result = await wdbg.GattServiceProvider.create_async(SERVICE_UUID)
        if provider_result.error != 0:
            print(f"[-] 无法初始化 BLE 服务。错误码: {provider_result.error}")
            return
            
        provider = provider_result.service_provider
        
        # 2. 设置特征值属性为可写入 (带响应 / 不带响应)
        parameters = wdbg.GattLocalCharacteristicParameters()
        parameters.characteristic_properties = (
            wdbg.GattCharacteristicProperties.WRITE |
            wdbg.GattCharacteristicProperties.WRITE_WITHOUT_RESPONSE
        )
        
        # 3. 创建本地 GATT 特征值
        char_result = await provider.service.create_characteristic_async(CHAR_UUID, parameters)
        if char_result.characteristic is None:
            print("[-] 创建特征值失败。")
            return
            
        characteristic = char_result.characteristic
        
        # 4. 注册事件监听函数
        characteristic.add_write_requested(on_write_requested)
        print("[+] 成功注册蓝牙写入事件回调")
        
        # 5. 启动 BLE 广播 (带显式的可连接/可发现参数)
        adv_parameters = wdbg.GattServiceProviderAdvertisingParameters()
        adv_parameters.is_connectable = True
        adv_parameters.is_discoverable = True
        provider.start_advertising_with_parameters(adv_parameters)
        print("[+] 蓝牙低功耗 (BLE) 广播服务已成功启动！")
        print(f"   服务 (Service) UUID: {SERVICE_UUID}")
        print(f"   特征 (Characteristic) UUID: {CHAR_UUID}")
        print("\n电脑正处于 BLE 广播状态，可被手机网页扫描连接。")
        
    except Exception as e:
        print(f"[-] 服务启动异常: {e}")
        return

    # 维持主线程协程运行
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n[!] 收到退出指令，正在关闭 BLE 服务...")
    finally:
        try:
            provider.stop_advertising()
        except:
            pass
        print("=== BLE 服务已安全关闭 ===")

if __name__ == "__main__":
    asyncio.run(main())
