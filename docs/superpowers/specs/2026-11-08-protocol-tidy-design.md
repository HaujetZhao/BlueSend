# 协议整理：版本语义分离与文档重排

日期：2026-11-08
状态：待实施

## 背景

`protocol.md` 同时承载 BLE 传输、消息表、连接行为、HTTP 上传和测速方法论，结构上混在一起；`hello` 目前只携带应用版本号，任何一端发版都会让手机端提示「版本不一致」，即使两端仍然互通。

## 目标

1. 把「协议是否兼容」和「应用版本是否相同」分开表达：只有不兼容时才提醒更新。
2. 按传输层、消息、连接生命周期重新组织 `protocol.md`，HTTP 上传独立成节。
3. 不改变任何既有的线格式与传输行为。

## 范围

改：

- `server/core/protocol.py`：新增 `PROTOCOL_VERSION` 常量。
- `web/src/logic/protocol.js`：新增同名常量。
- `server/core/server.py`：`hello` 消息附带 `proto`。
- `web/src/logic/ble-client.js`：按 `proto` 判断兼容性。
- `protocol.md`：整体重排。
- `AGENTS.md`：协议速查同步一句。
- `server/pyproject.toml`、`web/package.json`、`web/package-lock.json`、`server/uv.lock`：版本升到 `0.3.1`（非破坏性变更）。

不改：

- 上行片头（消息 ID + 片序号）与下行裸字节流的分片方式。
- 下行增加片头——留待以后需要检测下行丢片时再做。
- 手机端帧长上限——本次不补。

## 版本语义

### 常量

- `PROTOCOL_VERSION = 1`，两端各自维护，值必须相等。
- 递增条件：帧格式、切片头、消息语义发生不兼容变化。新增可选字段、新增消息类型不算。
- 应用版本仍由 `pyproject.toml` / `package.json` 提供，只用于显示与诊断。

### hello 消息

```json
{"t": "hello", "version": "0.3.1", "proto": 1}
```

- `version`：电脑端应用版本，字符串。
- `proto`：协议版本，整数；缺失时按 `1` 处理（0.3.0 即当前协议，不应误报）。

### 手机端行为

- `message.proto ?? 1 !== PROTOCOL_VERSION`：在事件行提示「协议不兼容：电脑端协议 vN，网页协议 vM，请刷新网页或更新电脑端」。
- 应用版本不一致：不提示。

## 文档结构

```text
# BLE 通信协议
## 概念               角色、安全上下文
## GATT 属性          UUID 表、属性即契约、CCCD
## 传输层             帧格式、上行切片、下行切片、顺序与可靠性
## 消息               手机 → 电脑、电脑 → 手机
## 连接生命周期       订阅、心跳、看门狗、重连、版本协商
## 测速
## 文件上传（HTTP）   token、路由、落点规则、混合内容与 LNA
```

文件上传保留在同一份文档，作为独立章节，不拆文件。

## 验证

- 服务端 `uv run pytest` 全通过。
- 前端 `npm test` 全通过。
- `npm run build` 成功，产物中存在 `proto` 比较逻辑。
- 手工检查 `protocol.md` 的交叉引用与消息表完整性。

## 风险

低。线格式不变，仅新增可选字段；旧电脑端缺 `proto` 时按 `1` 处理，不误报。
