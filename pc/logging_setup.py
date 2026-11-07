"""日志配置：控制台用 rich 上色，文件精确到毫秒。

日志文件名已经带了日期，所以行内不再写日期：控制台精确到秒，文件精确到毫秒。
"""

import logging
from datetime import datetime
from pathlib import Path

from rich.logging import RichHandler


LOG_FILES_TO_KEEP = 30


def prune_logs(log_dir: Path, keep: int = LOG_FILES_TO_KEEP) -> None:
    """按修改时间保留最新的 keep 个 ble-*.log，其余删除。

    按数量而不是按天数：这是自用工具，启动频率低、单次日志也不大，
    按数量更直观，不会出现「按天清完只剩几个文件」或「长期一个文件没攒满」的错觉。
    只清理本程序生成的 ble-*.log，目录里的其他文件一概不碰。
    """
    logs = sorted(
        log_dir.glob("ble-*.log"), key=lambda path: path.stat().st_mtime, reverse=True
    )
    for stale in logs[keep:]:
        stale.unlink()


class MillisecondFormatter(logging.Formatter):
    """文件格式补到毫秒；strftime 没有这个精度。"""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        time = datetime.fromtimestamp(record.created)
        return f"{time:%H:%M:%S}.{time.microsecond // 1000:03d}"


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    console = RichHandler(show_path=False, rich_tracebacks=True, log_time_format="%H:%M:%S")
    # RichHandler 渲染时优先取 formatter.datefmt，两边都设才不会回落到默认的「日期 + 时间」。
    console.setFormatter(logging.Formatter("%(message)s", datefmt="%H:%M:%S"))

    log_file = logging.FileHandler(log_dir / f"ble-{stamp}.log", encoding="utf-8")
    log_file.setFormatter(MillisecondFormatter("%(asctime)s %(levelname)s %(message)s"))
    prune_logs(log_dir)

    logging.basicConfig(level=logging.INFO, handlers=[console, log_file])
