"""给手机加载网页用的极简 HTTPS 静态服务。

Web Bluetooth 要求安全上下文，所以必须走 HTTPS；自签证书需要在手机上手动信任一次。
只负责把构建产物 dist/ 交出去，通信全部走蓝牙通道。

用法：
    npm run build
    uv run --project pc python serve_web.py
"""

import http.server
import logging
import socket
import ssl
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
CERTS = ROOT / "certs"
PORT = 8443

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("web")


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    finally:
        sock.close()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def log_message(self, format, *args) -> None:
        pass


def main() -> None:
    if not DIST.is_dir():
        raise SystemExit("dist/ 不存在，请先运行 npm run build")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(CERTS / "cert.pem", CERTS / "key.pem")

    httpd = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

    logger.info("手机访问：https://%s:%d", local_ip(), PORT)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
