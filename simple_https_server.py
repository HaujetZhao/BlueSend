import http.server
import ssl
import socket
import logging
from rich.logging import RichHandler

# 配置 Rich 日志系统
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False, show_time=True)]
)
logger = logging.getLogger("server")

def get_local_ip():
    """获取本机局域网 IP 地址"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

class LoggingHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """自定义 Handler，仅提供静态网页承载服务，并静默常规的 HTTP 请求日志"""
    
    def log_message(self, format, *args):
        """静默默认 the HTTP 请求访问日志"""
        pass

def main():
    port = 8443
    server_address = ('0.0.0.0', port)
    
    httpd = http.server.HTTPServer(server_address, LoggingHTTPRequestHandler)
    
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        ssl_context.load_cert_chain(certfile='static/cert.pem', keyfile='static/key.pem')
    except Exception as e:
        logger.error("[-] 加载证书失败！请确保 static/cert.pem 和 static/key.pem 存在。")
        logger.error(f"    错误详情: {e}")
        return

    httpd.socket = ssl_context.wrap_socket(httpd.socket, server_side=True)
    
    local_ip = get_local_ip()
    logger.info("=== 极简 纯静态 HTTPS 本地网页服务端 ===")
    logger.info(f"[+] 正在运行在端口: {port}")
    logger.info(f"[+] 本地访问地址: https://localhost:{port}")
    logger.info(f"[+] 手机访问地址: https://{local_ip}:{port}")
    logger.info("说明：此服务器仅用于加载网页端，所有数据同步与命令下达完全走蓝牙双向通道。\n")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("[!] 正在关闭 HTTPS 服务端...")
        httpd.server_close()
        logger.info("[+] 已安全退出。")

if __name__ == "__main__":
    main()
