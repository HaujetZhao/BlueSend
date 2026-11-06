// 与 pc/server.py 对齐：帧格式是 [4 字节大端长度][UTF-8 JSON]，一条消息可能横跨多次写入/通知。
const SERVICE_UUID = "7d9f0001-3c4e-4b6a-9f2e-1a2b3c4d5e6f";
const CHAR_UUID = "7d9f0002-3c4e-4b6a-9f2e-1a2b3c4d5e6f";

const HEARTBEAT_TIMEOUT_MS = 9000; // 服务端每 3 秒一次心跳，三个周期没动静就判定链路已死
const FALLBACK_WRITE_CHUNK = 180;  // 拿不到协商后的写入上限时使用，覆盖 4.2 默认 MTU
const RECONNECT_INTERVAL_MS = 2000;

const statusBadge = document.getElementById("status");
const connectBtn = document.getElementById("connect-btn");
const textInput = document.getElementById("text-input");
const btnGroup = document.getElementById("btn-group");
const sendBtn = document.getElementById("send-btn");
const instantSwitch = document.getElementById("instant-switch");
const eventLog = document.getElementById("event-log");

let device = null;             // 用户授权过的设备，重连时复用
let characteristic = null;
let writeChain = Promise.resolve(); // 串行化写入：同一条消息的多个分片不能被别的消息插队
let rxBuffer = new Uint8Array(0);
let heartbeatTimer = null;
let reconnectTimer = null;
let composing = false;
let connectedAt = 0;
let dropCount = 0;
let reconnectFailures = 0;
let pendingLogs = []; // 断线期间的事件，重连成功后补发给电脑端

// ---------- 事件记录 ----------

function note(text) {
  console.info(text);
  eventLog.textContent = text;
  if (characteristic) {
    send({ t: "log", v: text });
  } else {
    pendingLogs.push(text);
  }
}

function flushPendingLogs() {
  for (const text of pendingLogs.splice(0)) send({ t: "log", v: text });
}

// ---------- 帧编解码 ----------

function encodeFrame(message) {
  const body = new TextEncoder().encode(JSON.stringify(message));
  const frame = new Uint8Array(4 + body.length);
  new DataView(frame.buffer).setUint32(0, body.length, false);
  frame.set(body, 4);
  return frame;
}

// ---------- 写入 ----------

function writeChunkSize() {
  // 部分 Chrome 版本会暴露协商后的上限；拿不到就用保守值
  return characteristic.maxWriteWithResponseSize || FALLBACK_WRITE_CHUNK;
}

async function writeFrame(frame) {
  const size = writeChunkSize();
  for (let i = 0; i < frame.length; i += size) {
    // 有响应写由 ATT 保证先后顺序，这正是旧版 writeValueWithoutResponse 分片乱序的根源
    await characteristic.writeValueWithResponse(frame.subarray(i, i + size));
  }
}

function send(message) {
  if (!characteristic) return false;
  const frame = encodeFrame(message);
  writeChain = writeChain
    .then(() => writeFrame(frame))
    .catch((err) => {
      console.error("发送失败", message.t, err);
      handleDrop("写入失败：" + err.message);
    });
  return true;
}

// ---------- 读取 ----------

function onNotify(event) {
  const view = event.target.value;
  const chunk = new Uint8Array(view.buffer, view.byteOffset, view.byteLength);
  const merged = new Uint8Array(rxBuffer.length + chunk.length);
  merged.set(rxBuffer);
  merged.set(chunk, rxBuffer.length);
  rxBuffer = merged;

  for (;;) {
    if (rxBuffer.length < 4) return;
    const length = new DataView(rxBuffer.buffer, rxBuffer.byteOffset, 4).getUint32(0, false);
    if (rxBuffer.length < 4 + length) return;
    const body = new TextDecoder().decode(rxBuffer.subarray(4, 4 + length));
    rxBuffer = rxBuffer.slice(4 + length);
    dispatch(JSON.parse(body));
  }
}

function dispatch(message) {
  console.debug("收到", message.t);
  noteAlive();
  switch (message.t) {
    case "hb":
    case "pong":
      break;
    case "clip":
      applyPulledClipboard(message.v);
      break;
    default:
      console.warn("未知消息", message);
  }
}

async function applyPulledClipboard(text) {
  textInput.value = text;
  textInput.focus();
  try {
    await navigator.clipboard.writeText(text);
    console.info("已写入手机剪贴板");
  } catch (err) {
    // 浏览器权限限制，内容已经显示在输入框里，不影响使用
    console.warn("写入手机剪贴板失败", err);
  }
}

// ---------- 连接与看门狗 ----------

function noteAlive() {
  clearTimeout(heartbeatTimer);
  heartbeatTimer = setTimeout(() => handleDrop("心跳超时"), HEARTBEAT_TIMEOUT_MS);
}

function handleDrop(reason) {
  if (!characteristic) return; // 一次断开只记一笔
  const lasted = connectedAt ? ((Date.now() - connectedAt) / 1000).toFixed(1) : "未知";
  connectedAt = 0;
  dropCount += 1;
  clearTimeout(heartbeatTimer);
  characteristic = null;
  rxBuffer = new Uint8Array(0);
  writeChain = Promise.resolve();
  // 链路已经没了，这条只在页面上显示、进本地控制台，重连后再补发给电脑
  note(`第 ${dropCount} 次断开：${reason}，上一段连接存活 ${lasted} 秒`);
  updateState("disconnected");
  scheduleReconnect();
}

async function connect() {
  try {
    updateState("connecting");
    const server = await device.gatt.connect();
    const service = await server.getPrimaryService(SERVICE_UUID);
    characteristic = await service.getCharacteristic(CHAR_UUID);
    await characteristic.startNotifications();
    characteristic.addEventListener("characteristicvaluechanged", onNotify);
    rxBuffer = new Uint8Array(0);
    writeChain = Promise.resolve();
    noteAlive();
    stopReconnect();
    connectedAt = Date.now();
    note(`已连接（第 ${dropCount + 1} 段）`);
    flushPendingLogs();
    updateState("connected");
  } catch (err) {
    console.warn("连接失败", err);
    characteristic = null;
    updateState("disconnected");
    throw err;
  }
}

async function requestDevice() {
  if (!navigator.bluetooth) {
    alert("浏览器不支持 Web Bluetooth，或页面不在 HTTPS 下打开。");
    return;
  }
  stopReconnect();
  device = null;
  updateState("connecting");
  try {
    device = await navigator.bluetooth.requestDevice({
      filters: [{ services: [SERVICE_UUID] }],
      optionalServices: [SERVICE_UUID],
    });
    device.addEventListener("gattserverdisconnected", () => handleDrop("物理断开"));
    await connect();
  } catch (err) {
    console.warn("选择设备失败", err);
    updateState("disconnected");
  }
}

function scheduleReconnect() {
  if (!device || reconnectTimer) return;
  reconnectTimer = setInterval(() => {
    if (!device) {
      stopReconnect();
      return;
    }
    connect()
      .then(() => {
        reconnectFailures = 0;
      })
      .catch((err) => {
        reconnectFailures += 1;
        // 每 2 秒试一次，全记会刷屏，只记第一次和之后每 10 次
        if (reconnectFailures === 1 || reconnectFailures % 10 === 0) {
          note(`重连失败 ${reconnectFailures} 次：${err.message}`);
        }
      });
  }, RECONNECT_INTERVAL_MS);
}

function stopReconnect() {
  clearInterval(reconnectTimer);
  reconnectTimer = null;
}

document.addEventListener("visibilitychange", () => {
  // 页面回到前台时蓝牙可能已经被系统掐掉，主动检查一次
  if (document.visibilityState === "visible" && device && !characteristic) {
    connect().catch(() => {});
  }
});

// ---------- 界面状态 ----------

function updateState(state) {
  statusBadge.className = "status-badge " + state;
  textInput.disabled = false; // 输入框始终可用，避免软键盘反复收缩
  if (state === "connected") {
    statusBadge.textContent = "已连接";
    connectBtn.textContent = "重新连接";
    connectBtn.disabled = false;
    sendBtn.disabled = false;
    textInput.placeholder = instantSwitch.checked
      ? "已启用即时输入，打字实时发到电脑…"
      : "输入完毕后，点击发送按钮投递…";
    textInput.focus();
  } else if (state === "connecting") {
    statusBadge.textContent = "连接中";
    connectBtn.disabled = true;
    textInput.placeholder = "正在重新连接，请稍候…";
  } else {
    statusBadge.textContent = "未连接";
    connectBtn.disabled = false;
    sendBtn.disabled = true;
    textInput.placeholder = "蓝牙已断开，正在后台重连，可以继续在此处打字…";
  }
}

// ---------- 文本投递 ----------

function sendText() {
  const text = textInput.value;
  if (!text.trim()) return;
  send({ t: "text", v: text + "\n" });
  textInput.value = "";
  textInput.focus();
}

function clearInput() {
  textInput.value = "";
  textInput.focus();
}

function toggleInstantMode() {
  const instant = instantSwitch.checked;
  btnGroup.style.display = instant ? "none" : "flex";
  textInput.style.height = instant ? "80px" : "120px";
  textInput.placeholder = instant
    ? "已启用即时输入，打字实时发到电脑…"
    : "输入完毕后，点击发送按钮投递…";
  textInput.value = "";
  textInput.focus();
}

// ---------- 即时输入 ----------

textInput.addEventListener("compositionstart", () => {
  composing = true;
});

textInput.addEventListener("compositionend", (event) => {
  composing = false;
  if (!instantSwitch.checked) return;
  if (event.data) send({ t: "text", v: event.data });
  textInput.value = "";
  textInput.focus();
});

textInput.addEventListener("input", (event) => {
  if (!instantSwitch.checked || composing) return;
  if (event.inputType === "insertText") {
    if (event.data) send({ t: "text", v: event.data });
    textInput.value = "";
  } else if (event.inputType === "deleteContentBackward") {
    send({ t: "key", v: "backspace" });
    textInput.value = "";
  }
});

textInput.addEventListener("paste", (event) => {
  if (!instantSwitch.checked) return;
  event.preventDefault();
  const text = (event.clipboardData || window.clipboardData).getData("text");
  if (text) send({ t: "text", v: text });
  textInput.value = "";
  textInput.focus();
});

textInput.addEventListener("keydown", (event) => {
  if (!instantSwitch.checked) {
    if (event.ctrlKey && event.key === "Enter") {
      event.preventDefault();
      sendText();
    }
    return;
  }
  if (event.key === "Enter") {
    event.preventDefault();
    send({ t: "key", v: "enter" });
    textInput.value = "";
    textInput.focus(); // 保留焦点，否则软键盘会收起
  } else if (event.key === "Backspace" && textInput.value === "") {
    event.preventDefault();
    send({ t: "key", v: "backspace" });
  }
});

// ---------- 剪贴板 ----------

function pullClipboard() {
  if (!send({ t: "pull" })) alert("蓝牙未连接！");
}

async function pushClipboard() {
  if (!characteristic) {
    alert("蓝牙未连接！");
    return;
  }
  let text;
  try {
    text = await navigator.clipboard.readText();
  } catch (err) {
    alert("读取手机剪贴板被浏览器拒绝：" + err.message);
    return;
  }
  if (!text) {
    alert("手机剪贴板为空！");
    return;
  }
  send({ t: "clip", v: text });
}

connectBtn.addEventListener("click", requestDevice);

// 同一个页面开多个标签页时，每个标签页都是一路独立的 Web Bluetooth 客户端，
// 会互相抢同一台设备（表现为 GATT Error Unknown、刚连就断）。开页时就提醒。
const tabChannel = new BroadcastChannel("ble-tab");
tabChannel.onmessage = (event) => {
  if (event.data === "ping") {
    tabChannel.postMessage("here");
  } else {
    note("检测到另一个标签页也开着本页面，请只保留一个再连接");
  }
};
tabChannel.postMessage("ping");
// 输入框从一开始就可用：禁用/启用会让软键盘反复弹缩
textInput.disabled = false;
