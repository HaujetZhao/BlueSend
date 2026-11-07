"""日志配置：控制台用 rich 上色，文件精确到毫秒。

日志文件名已经带了日期，所以行内不再写日期：控制台精确到秒，文件精确到毫秒。
"""

import logging
from datetime import datetime
from pathlib import Path

from rich.logging import RichHandler


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

    logging.basicConfig(level=logging.INFO, handlers=[console, log_file])
