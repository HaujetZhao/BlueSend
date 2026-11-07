# 局域网传文件：蓝牙下发入口，网页上传

## 目的

手机往电脑传大文件。蓝牙的吞吐不够（无响应写约 63 KB/s），所以只让它干最擅长的事——**把电脑局域网入口的地址送到手机**；真正的数据走 WiFi 上的 HTTP。

老痛点是手机不知道电脑 IP、还得手输。这里由电脑主动下发带 token 的完整 URL，手机上点一下按钮就能打开上传页。

## 为什么不让主页面直接传

在线版页面跑在 GitHub Pages 的 HTTPS 下，电脑端服务是 HTTP。HTTPS 页面里的 `fetch` / XHR / WebSocket 去连 HTTP 地址属于混合内容，浏览器直接拦截（局域网 IP 不在 localhost 白名单里）。

所以主页面只做一件事：`window.open` 打开电脑托管的**独立上传页**（顶层导航不受混合内容限制），文件上传全部在那个页面里完成。代价是上传页与主页面不同源、互不通信——按需求，传输结果不回流到蓝牙，上传页自己显示进度即可。

## 架构

```text
手机主页面 (https://haujetzhao.github.io/Bluetooth-Input/)
  │  BLE：net 消息下发 hosts（含 token 的完整 URL）
  │  点击「发送文件」→ window.open(hosts[i])
  ▼
电脑端 Python 进程
  ├── BLE GATT Server（不变）
  └── HTTP 上传服务（新增，0.0.0.0:<端口>，后台线程）
        ├── GET  /?t=<token>      返回上传页 upload_page.html
        └── POST /upload?t=<token> 请求头 X-Filename，body 为文件原始字节

手机上传页 (http://<电脑IP>:<端口>/?t=<token>)
  └── XHR 顺序 POST 多个文件，本地显示进度
```

## 协议新增

仅一条下行消息，无上行新增，无回执：

| `t` | 字段 | 含义 |
|---|---|---|
| `net` | `hosts`：字符串数组 | 上传入口候选 URL，按默认路由网卡优先排序，每个都含 token |

- 在每次订阅变化（连接边界）时下发，与 `mtu` 同一时机；连接作用域，不缓存。
- 电脑没有任何可用局域网 IPv4 时下发空数组，手机端按钮保持禁用。

## 电脑端

### HTTP 服务（`pc/bluetooth_input/upload_server.py`）

标准库 `http.server.ThreadingHTTPServer`，daemon 线程，随主进程退出。启动参数：

- 端口：固定 `UPLOAD_PORT = 8377`（放 `protocol.py`）；绑定失败（端口被占）回退到系统分配的临时端口。实际端口以下发的 URL 为准。
- token：`secrets.token_urlsafe(16)`，进程启动时生成一次。

路由：

- `GET /?t=<token>`：token 不匹配回 403；匹配返回 `upload_page.html`，`Content-Type: text/html; charset=utf-8`。
- `POST /upload?t=<token>`：
  - token 不匹配回 403。
  - 必须带 `Content-Length`，否则回 411（上传页发 File 作为 body，浏览器一定带长度）。
  - `X-Filename` 为 `encodeURIComponent` 后的文件名，服务端 `unquote` 解码。
  - 按 `Content-Length` 以 64 KB 为块流式读取并写盘，任何大小的文件都不进内存。
  - 成功回 `200` + JSON `{"ok": true, "name": "<最终文件名>"}`；失败回 4xx/5xx + JSON `{"ok": false, "error": "…"}`。
- 其他路径/方法回 404/405。

### 落盘

- 目标目录用 pywin32 的已知文件夹 `FOLDERID_Downloads`（系统「下载」文件夹，尊重用户迁移过目录的情况）：
  `win32com.shell.shell.SHGetKnownFolderPath(shellcon.FOLDERID_Downloads, 0, None)`（已实测可用）。
- 文件名处理：`unquote` → 只取 basename → 剔除 Windows 非法字符 `<>:"/\|?*` 与控制字符 → 去首尾空格和点 → 空则用 `file`。路径穿越就此不可能。
- 重名：`名字 (1).ext`、`名字 (2).ext` 递增；用 `open(path, "xb")` 独占创建来**预留**最终文件名，避免并发上传撞名。
- 写入：先写同目录下 `tempfile.NamedTemporaryFile(prefix=".bt-upload-", suffix=".part", delete=False)`，完整收完后 `os.replace` 到预留路径；中断或异常时删除 `.part` 与预留的空文件。
- 日志：
  - 开始：`收到文件 xxx.pdf（5.2 MB）`
  - 完成：`已保存 C:\...\Downloads\xxx.pdf`
  - 失败：原因（长度不足、IO 错误等）

### 候选地址（`lan_hosts`）

用已依赖的 `psutil.net_if_addrs()` + `net_if_stats()`：

1. 取状态 `isup` 的网卡上的 `AF_INET` 地址；
2. 排除回环、`169.254.x.x`（link-local）和 `0.0.0.0`；
3. 把默认路由出站地址（UDP socket `connect(("8.8.8.8", 80))` 后看 `getsockname()`，不真正发包）排到第一位，其余保持枚举顺序。

多网卡仍可能猜错，由手机端轮换兜底。

## 手机端

### BLE 客户端

- `#dispatch` 增加 `net` 分支：把 `hosts` 交给 `onNet` 回调。断线时清空（连接边界语义）。
- `useBle` 透传 `onNet`。

### 页面

- 操作区新增一颗整行药丸按钮「发送文件」，样式沿用 `btn-pull` / `btn-push` 一族的形状与配色。
- 未连接、或收到 `net` 之前禁用。
- 点击时取 `hosts[index % hosts.length]`，**在点击回调里同步** `window.open(url, '_blank')`（异步调用会被弹窗拦截）；事件行显示 `已打开上传页（入口 1/2）`。
- 每次点击索引递增，即多网卡猜错时换下一个地址重试。收到新的 `net` 时索引归零。
- `window.open` 返回 `null` 时事件行提示「浏览器拦截了新标签页」。

## 上传页（`pc/bluetooth_input/upload_page.html`）

- 自包含单文件，无外部资源，深色样式与主页面观感接近，纯中文。
- 「选择文件」（`<input type="file" multiple>`）→ 选中即开始，按选择顺序**逐个**上传。
- 每个文件一行：文件名、大小、进度条、状态（等待中 / 上传中 xx% / 完成 / 失败原因）。
- 用 `XMLHttpRequest` 而非 `fetch`：只有前者有 `upload.onprogress`。
- 传完后页面显示「全部完成」，不自动关闭，由用户关闭。
- 不做拖拽、不做断点续传。

## 边界情况

| 情况 | 处理 |
|---|---|
| 电脑多个网卡，首个地址不可达 | 主页面每次点击轮换下一个候选 |
| Windows 防火墙拦截入站 | 首次运行会弹「允许访问网络」；拒绝则手机打不开，日志与文档写明 |
| 8377 被占用 | 自动改用临时端口，URL 随 `net` 下发 |
| 传输中断（关页、断网） | 服务端读到的字节少于 `Content-Length`，删 `.part` 与预留文件，记日志 |
| 同名文件 | `名字 (1).ext` 递增 |
| 电脑端重启 | 端口可能变、token 必变；手机重连后收到新 `net`，旧上传页随即 403/失效，属预期 |
| 页面被浏览器弹窗拦截 | 事件行提示 |
| 手机连的不是同一局域网 | 候选地址全部打不开，属网络环境问题，日志无异常 |

## 测试

`pc/tests/test_upload_server.py`：

- 文件名清洗：路径穿越（`../../x`）、Windows 非法字符、空名、中文名。
- 重名递增与独占预留。
- token 校验：错误 token 403；`GET /` 返回 HTML。
- 端到端：在 `127.0.0.1:0` 起真实 server，POST 一段二进制，断言落盘内容一致、大小正确、`.part` 已清理；断言缺失 `Content-Length` 回 411。

手动验收：

- 真机打开在线版，连上蓝牙，点「发送文件」能打开上传页。
- 传单文件、多文件、中文名文件、大于 1 GB 的文件。
- 多网卡环境点击轮换可用。
- 关闭上传页中断传输后，下载文件夹里没有 `.part` 残留。

前端无新增单测；`npm test` 不变。

## 文档同步

- `protocol.md`：新增 `net` 消息与文件上传入口一节。
- `AGENTS.md`：代码地图补两个新文件，启动说明补防火墙与端口，踩坑一节补混合内容限制。
