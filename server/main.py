"""电脑端入口：配置日志、抢单实例锁，然后启动 GATT Server。"""

import asyncio
import logging
import sys
from pathlib import Path

from core.logging_setup import setup_logging
from core.server import serve
from core.single_instance import acquire as acquire_instance_lock

logger = logging.getLogger("ble")

INSTANCE_LOCK_NAME = "BlueSend.GattServer"


def main() -> None:
    setup_logging(Path(__file__).parent / "logs")
    # 多实例会各自注册同一个 Service UUID、互相挤掉广播，症状极难认（坑 8），
    # 所以抢不到锁就先退出，别去碰 BLE。
    if not acquire_instance_lock(INSTANCE_LOCK_NAME):
        logger.error("已有另一个 main.py 在运行，本进程退出。")
        logger.error(
            '查看现存实例：Get-CimInstance Win32_Process -Filter "Name like '
            "'python%'\" | Select-Object ProcessId,CommandLine"
        )
        sys.exit(1)
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        logger.info("退出")


if __name__ == "__main__":
    main()
