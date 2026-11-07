"""电脑端入口：配置日志、抢单实例锁，然后启动 GATT Server。"""

import asyncio
import logging
import subprocess
import sys

from rich.console import Console

from core.logging_setup import setup_logging
from core.paths import APP_DIR, FROZEN
from core.server import serve
from core.single_instance import acquire as acquire_instance_lock
from core.single_instance import release as release_instance_lock

logger = logging.getLogger("ble")

INSTANCE_LOCK_NAME = "BlueSend.GattServer"


def print_banner() -> None:
    console = Console()
    console.print()
    console.rule("[bold #4f7cff]BlueSend 电脑端[/]")
    console.print()
    console.print(
        "手机浏览器打开：[cyan underline]https://haujetzhao.github.io/BlueSend/[/]"
    )
    console.print()
    console.print("  1. 点左上角的连接状态药丸，选中本机")
    console.print("  2. 同一页面只开一个标签页，多开会互抢设备")
    console.print()
    console.print(f"日志目录：[cyan underline]{APP_DIR / 'logs'}[/]")
    console.print()


def launch_command() -> list[str]:
    """重启时用的命令行。冻结后 argv[0] 就是 exe 本身，不能再传一遍。"""
    if FROZEN:
        return [sys.executable, *sys.argv[1:]]
    return [sys.executable, *sys.argv]


def main() -> None:
    setup_logging(APP_DIR / "logs")
    # 多实例会各自注册同一个 Service UUID、互相挤掉广播，症状极难认（坑 8），
    # 所以抢不到锁就先退出，别去碰 BLE。
    if not acquire_instance_lock(INSTANCE_LOCK_NAME):
        program = "BlueSend.exe" if FROZEN else "main.py"
        pattern = "BlueSend%" if FROZEN else "python%"
        logger.error("已有另一个 %s 在运行，本进程退出。", program)
        logger.error(
            '查看现存实例：Get-CimInstance Win32_Process -Filter "Name like '
            f"'{pattern}'\" | Select-Object ProcessId,CommandLine"
        )
        sys.exit(1)
    print_banner()

    restart = False
    try:
        restart = asyncio.run(serve())
    except KeyboardInterrupt:
        pass

    if restart:
        logger.info("重启程序")
        release_instance_lock()
        subprocess.Popen(launch_command())
    else:
        logger.info("退出")


if __name__ == "__main__":
    main()
