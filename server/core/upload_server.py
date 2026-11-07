"""局域网文件上传服务：电脑托管一个页面，手机浏览器打开后把文件 POST 回来。

为什么不让主页面直接传：主页面在 GitHub Pages 的 HTTPS 下，直接请求 HTTP 的
局域网地址会被浏览器按混合内容拦截。让电脑托管一个页面、由主页面用顶层导航
打开它，就不受这个限制（顶层导航不是混合内容）。

本服务与蓝牙无关，只依赖下发的 URL 里带的 token：同一局域网里的其他设备即使
知道端口，没有 token 也打不开页面、传不了文件。
"""

import json
import logging
import os
import re
import secrets
import socket
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import psutil
from win32com.shell import shell, shellcon

from .protocol import UPLOAD_PORT

logger = logging.getLogger("ble")

PAGE_PATH = Path(__file__).with_name("upload_page.html")
READ_BLOCK = 64 * 1024
# 上传页由我们托管，文件名经 encodeURIComponent 后放在请求头里。
INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Windows 把 CON.txt、COM1.log 这类名字当设备名，打开会失败或写进控制台。
RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def known_folder(folder_id) -> Path:
    """Windows 已知文件夹的绝对路径。不写死盘符，用户把目录迁到别的盘也对。"""
    return Path(shell.SHGetKnownFolderPath(folder_id, 0, None))


def target_dirs(folder: str) -> dict[str, Path]:
    """上传落点：桌面／下载文件夹下的同名子文件夹，子文件夹名来自配置。"""
    return {
        "desktop": known_folder(shellcon.FOLDERID_Desktop) / folder,
        "downloads": known_folder(shellcon.FOLDERID_Downloads) / folder,
    }


def sanitize_filename(raw: str) -> str:
    """把对端给的名字变成目标目录下的一个安全文件名。

    先按两种分隔符取 basename，路径穿越就无从谈起；再剔除 Windows 非法字符；
    设备名加下划线前缀——带扩展名的 `CON.txt` 同样会被 Windows 当成设备。
    """
    name = re.split(r"[\\/]", raw)[-1]
    name = INVALID_CHARS.sub("", name).strip(" .")
    if not name:
        return "file"
    # 设备名后面的空格与点在 Windows 眼里无意义，`CON .txt` 也算 CON。
    if name.split(".")[0].rstrip(" .").upper() in RESERVED_NAMES:
        name = "_" + name
    return name


def discard(path: Path) -> None:
    """清理中途产物。清理失败不能盖住真正的错误，只记一条日志。"""
    try:
        path.unlink(missing_ok=True)
    except OSError as err:
        logger.warning("清理 %s 失败：%s", path, err)


def reserve_path(directory: Path, name: str) -> Path:
    """用一个空的占位文件把最终文件名占住，返回独占的路径。

    先占位再改名，避免两个并发上传同时选中同一个名字、后者覆盖前者。
    """
    stem, suffix = os.path.splitext(name)
    candidate = directory / name
    index = 0
    while True:
        try:
            candidate.open("xb").close()
            return candidate
        except FileExistsError:
            index += 1
            candidate = directory / f"{stem} ({index}){suffix}"


def _default_route_ip() -> str | None:
    """默认路由对应的本机地址。UDP connect 只看路由表，不真正发包。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def lan_hosts() -> list[str]:
    """本机所有可作为入口的 IPv4 地址，默认路由所在网卡排第一。

    虚拟网卡（VMware、Hyper-V 等）无法可靠识别，只能排序：猜错了由手机端
    点击轮换下一个候选兜底。
    """
    stats = psutil.net_if_stats()
    hosts: list[str] = []
    for interface, addresses in psutil.net_if_addrs().items():
        # 两份快照之间网卡可能消失（VPN 拨号），取不到就当它不存在。
        stat = stats.get(interface)
        if stat is None or not stat.isup:
            continue
        for address in addresses:
            if address.family != socket.AF_INET:
                continue
            ip = address.address
            if ip.startswith("127.") or ip.startswith("169.254.") or ip == "0.0.0.0":
                continue
            if ip not in hosts:
                hosts.append(ip)
    default = _default_route_ip()
    if default in hosts:
        hosts.remove(default)
        hosts.insert(0, default)
    return hosts


def _make_handler(
    targets: dict[str, Path], token: str
) -> type[BaseHTTPRequestHandler]:
    class UploadHandler(BaseHTTPRequestHandler):
        # 一次读阻塞超过 5 分钟就放弃，别让线程无限挂在一个死连接上。
        timeout = 300

        def log_message(self, fmt: str, *args) -> None:
            # 默认请求行里带着 URL 的 query，也就带着 token，不该写进常规日志。
            logger.debug("上传服务 %s：%s", self.address_string(), fmt % args)

        def _authorized(self) -> bool:
            query = parse_qs(urlparse(self.path).query)
            # compare_digest 对非 ASCII 的 str 会抛 TypeError；统一按字节比较。
            given = query.get("t", [""])[0].encode("utf-8")
            return secrets.compare_digest(given, token.encode("utf-8"))

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path not in ("/", "/ping"):
                self.send_error(404)
                return
            if not self._authorized():
                self.send_error(403)
                return
            if path == "/ping":
                # 手机主页面用它探测这个入口是否可达，不需要任何内容。
                self.send_response(204)
                self.end_headers()
                return
            body = PAGE_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/upload":
                self.send_error(404)
                return
            if not self._authorized():
                self.send_error(403)
                return
            # 落点只认这张表，外部输入不能拼进路径；不合法就到此为止，不碰磁盘。
            target = self.headers.get("X-Target")
            if target not in targets:
                self._send_json(400, {"ok": False, "error": "保存位置非法"})
                return
            directory = targets[target]
            raw_name = self.headers.get("X-Filename")
            if raw_name is None:
                self._send_json(400, {"ok": False, "error": "缺少 X-Filename"})
                return
            length = self.headers.get("Content-Length")
            if length is None:
                # 上传页把 File 当 body 发，浏览器一定带长度；没有就不猜。
                self._send_json(411, {"ok": False, "error": "需要 Content-Length"})
                return
            try:
                remaining = int(length)
            except ValueError:
                self._send_json(400, {"ok": False, "error": "Content-Length 非法"})
                return
            if remaining < 0:
                self._send_json(400, {"ok": False, "error": "Content-Length 非法"})
                return

            name = sanitize_filename(unquote(raw_name))
            # 预留文件名也可能失败：目录里已有同名目录、路径超长、权限不足。
            # 这些和传输中断一样，都得给客户端一个 500，而不是直接断连接。
            final = None
            temporary = None
            try:
                # 建目录失败和写盘失败走同一条 500 路径，不会直接断连接。
                directory.mkdir(parents=True, exist_ok=True)
                final = reserve_path(directory, name)
                logger.info(
                    "收到文件 %s → %s（%.1f MB）",
                    name, directory.name, remaining / 1024 / 1024,
                )
                temporary = tempfile.NamedTemporaryFile(
                    prefix=".bt-upload-", suffix=".part", dir=directory, delete=False
                )
                with temporary:
                    while remaining:
                        block = self.rfile.read(min(READ_BLOCK, remaining))
                        if not block:
                            raise ConnectionError("连接提前结束")
                        temporary.write(block)
                        remaining -= len(block)
                os.replace(temporary.name, final)
            except Exception as err:
                if temporary is not None:
                    discard(Path(temporary.name))
                if final is not None:
                    discard(final)
                logger.warning("接收文件失败：%s（%s）", name, err)
                try:
                    self._send_json(500, {"ok": False, "error": str(err)})
                except OSError:
                    # 发送方已经关掉页面，没有连接可以回应了。
                    pass
                return
            logger.info("已保存 %s", final)
            self._send_json(200, {"ok": True, "name": final.name})

    return UploadHandler


class UploadService:
    """后台线程里跑的上传服务。生命周期跟随主进程。"""

    def __init__(self, targets: dict[str, Path], port: int) -> None:
        self.token = secrets.token_urlsafe(16)
        handler = _make_handler(targets, self.token)
        try:
            self._server = ThreadingHTTPServer(("0.0.0.0", port), handler)
        except OSError:
            logger.warning("端口 %d 不可用，改用系统临时端口", port)
            self._server = ThreadingHTTPServer(("0.0.0.0", 0), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="upload-http",
            daemon=True,
        )
        self._thread.start()

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    def urls(self) -> list[str]:
        """下发用的完整入口 URL，每个都带 token。"""
        return [
            f"http://{host}:{self.port}/?t={self.token}" for host in lan_hosts()
        ]

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


def start_upload_server(folder: str, port: int = UPLOAD_PORT) -> UploadService:
    return UploadService(target_dirs(folder), port)
