import http.client
import json
import time
import urllib.error
import urllib.request
from urllib.parse import quote

import pytest

from core.upload_server import (
    UploadService,
    reserve_path,
    sanitize_filename,
)


@pytest.fixture
def service(tmp_path):
    server = UploadService(
        {"desktop": tmp_path / "desktop", "downloads": tmp_path / "downloads"}, 0
    )
    yield server
    server.stop()


def post_file(
    port: int, token: str, filename: str, body: bytes, target: str | None = "downloads"
):
    headers = {"X-Filename": quote(filename)}
    if target is not None:
        headers["X-Target"] = target
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(
            "POST",
            f"/upload?t={token}",
            body=body,
            headers=headers,
        )
        return connection.getresponse()
    finally:
        connection.close()


def test_sanitize_filename_strips_paths_and_illegal_chars():
    assert sanitize_filename("../../evil.txt") == "evil.txt"
    assert sanitize_filename(r"C:\Users\x\a.txt") == "a.txt"
    assert sanitize_filename('a<b>c:d"e|f?g*.txt') == "abcdefg.txt"
    assert sanitize_filename("   ") == "file"


def test_sanitize_filename_escapes_reserved_device_names():
    assert sanitize_filename("CON") == "_CON"
    assert sanitize_filename("CON.txt") == "_CON.txt"
    assert sanitize_filename("NUL.log") == "_NUL.log"
    assert sanitize_filename("COM1") == "_COM1"
    assert sanitize_filename("LPT9.txt") == "_LPT9.txt"
    # 设备名后的空格与点在 Windows 眼里无意义。
    assert sanitize_filename("CON .txt") == "_CON .txt"
    assert sanitize_filename("CONSOLE.txt") == "CONSOLE.txt"


def test_reserve_path_increments_on_conflict(tmp_path):
    first = reserve_path(tmp_path, "报告.pdf")
    second = reserve_path(tmp_path, "报告.pdf")
    third = reserve_path(tmp_path, "报告.pdf")

    assert first.name == "报告.pdf"
    assert second.name == "报告 (1).pdf"
    assert third.name == "报告 (2).pdf"
    assert all(path.exists() for path in (first, second, third))


def test_get_returns_page_with_token(service):
    url = f"http://127.0.0.1:{service.port}/?t={service.token}"
    with urllib.request.urlopen(url, timeout=5) as response:
        assert response.status == 200
        assert "发送文件到电脑".encode() in response.read()


def test_ping_returns_204(service):
    url = f"http://127.0.0.1:{service.port}/ping?t={service.token}"
    with urllib.request.urlopen(url, timeout=5) as response:
        assert response.status == 204
        assert response.read() == b""


@pytest.mark.parametrize("token", ["wrong", "%E4%B8%AD", "%FF"])
def test_get_rejects_wrong_token(service, token):
    url = f"http://127.0.0.1:{service.port}/?t={token}"
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(url, timeout=5)
    assert error.value.code == 403


def test_post_writes_file_and_dedupes(service, tmp_path):
    downloads = tmp_path / "downloads"
    payload = bytes(range(256)) * 1024
    response = post_file(service.port, service.token, "照片 01.jpg", payload)
    assert response.status == 200
    saved = json.loads(response.read())
    assert saved == {"ok": True, "name": "照片 01.jpg"}
    assert (downloads / "照片 01.jpg").read_bytes() == payload

    response = post_file(service.port, service.token, "照片 01.jpg", b"again")
    assert json.loads(response.read())["name"] == "照片 01 (1).jpg"
    assert (downloads / "照片 01 (1).jpg").read_bytes() == b"again"
    assert list(downloads.glob(".bt-upload-*")) == []


def test_post_saves_reserved_device_name(service, tmp_path):
    downloads = tmp_path / "downloads"
    response = post_file(service.port, service.token, "CON.txt", b"data")
    assert response.status == 200
    assert json.loads(response.read())["name"] == "_CON.txt"
    assert (downloads / "_CON.txt").read_bytes() == b"data"


def test_post_reports_reserve_failure(service, tmp_path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "taken.bin").mkdir()
    response = post_file(service.port, service.token, "taken.bin", b"data")
    assert response.status == 500
    assert json.loads(response.read())["ok"] is False
    assert (downloads / "taken.bin").is_dir()


def test_post_routes_to_desktop_and_downloads(service, tmp_path):
    desktop = tmp_path / "desktop"
    downloads = tmp_path / "downloads"

    response = post_file(
        service.port, service.token, "a.txt", b"desktop", target="desktop"
    )
    assert response.status == 200
    response = post_file(
        service.port, service.token, "a.txt", b"downloads", target="downloads"
    )
    assert response.status == 200

    assert (desktop / "a.txt").read_bytes() == b"desktop"
    assert (downloads / "a.txt").read_bytes() == b"downloads"


def test_post_creates_target_folder(service, tmp_path):
    downloads = tmp_path / "downloads"
    assert not downloads.exists()

    response = post_file(service.port, service.token, "a.txt", b"x")

    assert response.status == 200
    assert (downloads / "a.txt").read_bytes() == b"x"


def test_post_requires_target(service, tmp_path):
    response = post_file(service.port, service.token, "a.txt", b"x", target=None)
    assert response.status == 400
    assert json.loads(response.read())["ok"] is False
    assert not (tmp_path / "desktop").exists()
    assert not (tmp_path / "downloads").exists()


def test_post_rejects_unknown_target(service, tmp_path):
    response = post_file(
        service.port, service.token, "a.txt", b"x", target="../../etc"
    )
    assert response.status == 400
    assert json.loads(response.read())["ok"] is False
    assert not (tmp_path / "desktop").exists()
    assert not (tmp_path / "downloads").exists()


def test_post_rejects_wrong_token(service, tmp_path):
    response = post_file(service.port, "wrong", "a.txt", b"x")
    assert response.status == 403
    assert not (tmp_path / "desktop").exists()
    assert not (tmp_path / "downloads").exists()


def test_post_requires_content_length(service, tmp_path):
    connection = http.client.HTTPConnection("127.0.0.1", service.port, timeout=5)
    try:
        connection.putrequest("POST", f"/upload?t={service.token}")
        connection.putheader("X-Filename", "a.txt")
        connection.putheader("X-Target", "downloads")
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == 411
    finally:
        connection.close()
    assert not (tmp_path / "desktop").exists()
    assert not (tmp_path / "downloads").exists()


def test_interrupted_upload_leaves_nothing(service, tmp_path):
    downloads = tmp_path / "downloads"
    connection = http.client.HTTPConnection("127.0.0.1", service.port, timeout=5)
    connection.putrequest("POST", f"/upload?t={service.token}")
    connection.putheader("X-Filename", "half.bin")
    connection.putheader("X-Target", "downloads")
    connection.putheader("Content-Length", "1024")
    connection.endheaders()
    connection.send(b"only a few bytes")

    # 服务端已建好目标目录、占位文件与 .part，正阻塞等剩余字节。先确认它们
    # 真的存在，否则下面的「清空」断言可能什么都没验证到。
    deadline = time.monotonic() + 2
    while (
        not (downloads.exists() and any(downloads.iterdir()))
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    assert downloads.exists() and any(downloads.iterdir())

    connection.close()

    deadline = time.monotonic() + 2
    while any(downloads.iterdir()) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert list(downloads.iterdir()) == []
