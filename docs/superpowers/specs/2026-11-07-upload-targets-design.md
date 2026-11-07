# 上传落点：桌面 / 下载 两个预置目标

## 目的

上传页现在只能往系统「下载」文件夹的根目录扔文件，传得多了会把下载目录打乱。加两个目标按钮——「桌面」「下载」——各自落到对应文件夹下的一个子文件夹里，传过来的文件自成一处。子文件夹名不写死，放在 `config.toml` 里配。

## 范围

- 只改上传页与服务端，动 BLE 协议、不动主页面。
- 两个目标固定，不做自定义目标列表。
- 不记忆上次选择，每次进页面默认「下载」。

## 配置

`pc/bluetooth_input/config.toml` 增加一节：

```toml
[upload]
folder = "手机传输"
```

`pc/bluetooth_input/config.py` 增加 `load_upload_folder() -> str`，写法与现有 `load_wm_char_apps()` 一致：直接索引，没有默认值，配错就在启动时抛异常，不做兜底。

## 落点解析

两个目标的基目录仍由 Windows 已知文件夹给出，不写绝对路径——用户把「下载」迁到 D 盘也照样对：

```python
def known_folder(folder_id) -> Path:
    return Path(shell.SHGetKnownFolderPath(folder_id, 0, None))

def target_dirs(folder: str) -> dict[str, Path]:
    return {
        "desktop": known_folder(shellcon.FOLDERID_Desktop) / folder,
        "downloads": known_folder(shellcon.FOLDERID_Downloads) / folder,
    }
```

`UploadService` 不再接收单个 `Path`，改接收这张 `dict[str, Path]`——纯数据，测试直接构造即可，不必 mock Windows API。`start_upload_server(folder, port)` 负责把配置与已知文件夹拼成这张表。

## 请求携带目标

`POST /upload` 增加请求头 `X-Target`，值只认 `desktop` / `downloads`：

- 缺失或不在表里回 400，不进入任何磁盘逻辑。
- 命中后对目标目录 `mkdir(parents=True, exist_ok=True)`，放在现有 try 内——建目录失败和写盘失败走同一条 500 路径，不会直接断连接。
- 日志带上落点：`收到文件 x.jpg → 手机传输`。

token 校验位置不变，仍是最前面。

`folder` 是用户自己配置里的值，不受外部输入影响，按项目约定不做校验。配成空串就会把文件放在桌面／下载根目录，那是配置者的选择。

## 上传页

`pc/bluetooth_input/upload_page.html` 标题下面加两个按钮，默认选中「下载」：

```html
<div class="targets">
  <button class="target" data-target="desktop">桌面</button>
  <button class="target" data-target="downloads">下载</button>
</div>
```

- 样式沿用现有胶囊形，选中态用 `--primary-color`。
- 上传时带 `X-Target` 头。
- 切换只影响尚未开始的文件：`target` 在 `upload()` 开始时读取，已经在传的那条请求头早已发出，不受影响。
- 提示文案从「文件会保存到电脑的『下载』文件夹」改为「文件会保存到电脑上你选的位置」。

## 测试

`pc/tests/test_upload_server.py`：

- fixture 改为直接构造 `UploadService({"desktop": tmp_path / "desktop", "downloads": tmp_path / "downloads"}, 0)`。
- `post_file` 增加 `target` 参数，默认 `downloads`。
- 新增：两个 target 落到两个不同目录；「手机传输」子目录第一次上传时被创建；`X-Target` 缺失回 400；`X-Target` 非法回 400 且目录里什么都没落。

## 文档同步

- `protocol.md`：「文件上传入口」一节补 `X-Target` 与两个落点。
- `AGENTS.md`：代码地图里 `config.toml` 的说明从「上屏兼容名单」扩成「上屏兼容名单、上传落点」。
- `readme.md`：如提到保存位置，一并改。

## 不做

- 不做自定义目标列表、不做记忆上次选择、不做目录浏览。
- 不动 `net` 消息与主页面。上传页仍是自包含单文件。
