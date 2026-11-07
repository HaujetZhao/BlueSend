import logging
import os
import re

from bluetooth_input.logging_setup import MillisecondFormatter, prune_logs


def test_file_time_has_milliseconds_and_no_date():
    record = logging.LogRecord("ble", logging.INFO, "", 0, "消息", None, None)
    record.created = 1_700_000_000.5

    stamp = MillisecondFormatter("%(asctime)s").format(record)

    assert re.fullmatch(r"\d{2}:\d{2}:\d{2}\.500", stamp)


def test_prune_logs_keeps_newest_and_leaves_other_files(tmp_path):
    for index in range(5):
        path = tmp_path / f"ble-20260101-00000{index}.log"
        path.write_text("日志", encoding="utf-8")
        # 明确拉开修改时间，避免同一秒内创建导致顺序不确定。
        os.utime(path, (1_700_000_000 + index, 1_700_000_000 + index))
    other = tmp_path / "other.log"
    other.write_text("不是本程序生成的日志", encoding="utf-8")

    prune_logs(tmp_path, keep=2)

    remaining = sorted(path.name for path in tmp_path.glob("ble-*.log"))
    assert remaining == ["ble-20260101-000003.log", "ble-20260101-000004.log"]
    assert other.exists()
