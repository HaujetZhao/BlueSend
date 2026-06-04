import time
import serial
import serial.tools.list_ports
import keyboard

def get_bluetooth_port():
    """自动获取系统中的蓝牙虚拟串口"""
    ports = list(serial.tools.list_ports.comports())
    # 优先寻找描述里包含“蓝牙”或“bluetooth”的串口
    bt_ports = [p.device for p in ports if "bluetooth" in p.description.lower() or "蓝牙" in p.description]
    if bt_ports:
        return bt_ports[0]
    # 如果没找到显式的蓝牙串口，但有可用串口，则默认使用第一个
    return ports[0].device if ports else None

def main():
    port = get_bluetooth_port()
    if not port:
        print("未检测到任何 COM 端口。请确保手机与电脑已配对，且蓝牙已开启。")
        return
        
    print(f"正在监听蓝牙端口: {port} ... (请在手机端连接电脑并发送文字)")
    
    try:
        # 打开串口，设置 timeout=1 以便能响应 Ctrl+C
        ser = serial.Serial(port, 115200, timeout=1)
        buffer = bytearray()
        
        while True:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                buffer.extend(data)
                
                # 寻找换行符并提取完整的文本行
                while b'\n' in buffer:
                    idx = buffer.index(b'\n')
                    line = buffer[:idx]
                    buffer = buffer[idx + 1:]
                    
                    text = line.decode('utf-8').strip()
                        
                    if text:
                        print(f"收到并输入: {text}")
                        # 模拟键盘自动写入到当前光标处
                        keyboard.write(text)
            else:
                time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n程序已被用户手动终止。")
    except Exception as e:
        print(f"运行出错: {e}")

if __name__ == "__main__":
    main()
