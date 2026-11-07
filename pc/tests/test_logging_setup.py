import logging
import re

from logging_setup import MillisecondFormatter


def test_file_time_has_milliseconds_and_no_date():
    record = logging.LogRecord("ble", logging.INFO, "", 0, "消息", None, None)
    record.created = 1_700_000_000.5

    stamp = MillisecondFormatter("%(asctime)s").format(record)

    assert re.fullmatch(r"\d{2}:\d{2}:\d{2}\.500", stamp)
