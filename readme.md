# Bluetooth Input

通过低功耗蓝牙 (BLE)，用手机给电脑打字。

**无需安装任何手机 App** — 手机浏览器打开网页即可连接。

> [!NOTE]
> 手机和电脑**不需要在同一网络下**，所有数据通过 BLE 蓝牙物理通道直传。

## 功能

- **即时输入** — 手机打字实时出现在电脑光标处，就像用物理键盘一样
- **经典发送** — 输入整段文字后一次性发送
- **剪贴板同步** — 手机与电脑之间双向推送/拉取剪贴板内容
- **自动重连** — 蓝牙断开后后台静默重连，无需手动干预

## 使用方法

### 1. 电脑端启动服务

安装依赖：

```powershell
pip install -r requirements.txt
```

开启 BLE 广播服务：

```powershell
python bt_ble_receiver.py
```


### 2. 手机端连接

手机浏览器打开 **https://haujetzhao.github.io/Bluetooth-Input/** ，点击「扫描连接」选中你的电脑即可。

## 手机浏览器要求

- **Android**：Chrome、Edge 等 Chromium 内核浏览器
- **iOS**：需使用 [Bluefy](https://apps.apple.com/cn/app/bluefy-web-ble-browser/id1492828568) 等支持 Web Bluetooth 的浏览器

## 本地开发

如需本地托管网页（而非 GitHub Pages），可运行内置 HTTPS 服务器：

```powershell
python simple_https_server.py
# 手机访问 https://<电脑IP>:8443
```
