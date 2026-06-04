const SERVICE_UUID = "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d";
const CHAR_UUID = "12345678-1234-5678-1234-567812345678";

let gattServer = null;
let writeCharacteristic = null;
let connectedDevice = null;       // 授权设备句柄
let reconnectTimer = null;        // 重连定时器句柄
let connectionStartTime = 0;      // 记录连接建立的时间戳
let isComposing = false;          // 中文拼音组合输入状态
let pullBuffer = "";              // 全局拉取接收缓冲区

const statusBadge = document.getElementById("status");
const connectBtn = document.getElementById("connect-btn");
const textInput = document.getElementById("text-input");
const btnGroup = document.getElementById("btn-group");
const sendBtn = document.getElementById("send-btn");
const instantSwitch = document.getElementById("instant-switch");

const sleep = ms => new Promise(r => setTimeout(r, ms));

// 发送日志到 PC 端（通过蓝牙通道）
async function sendLog(type, message, errorDetail = null) {
  let logMsg = message;
  if (errorDetail) {
    logMsg += " | " + (errorDetail.stack || errorDetail.toString());
  }
  console.log(`[${type}] ${logMsg}`);
  if (writeCharacteristic) {
    try {
      const encoder = new TextEncoder();
      const dataBytes = encoder.encode(`L:${type}:${logMsg}`);
      await writeCharacteristic.writeValueWithoutResponse(dataBytes);
    } catch (e) {
      console.error("蓝牙日志上报失败", e);
    }
  }
}

// 状态卡片状态控制
function updateState(state) {
  statusBadge.className = "status-badge " + state;
  
  // 保持输入框永远处于启用状态 (enabled)，绝对不禁用，以彻底防止手机软键盘弹缩
  textInput.disabled = false;
  
  if (state === "connected") {
    statusBadge.textContent = "已连接";
    connectBtn.style.display = "block";
    connectBtn.disabled = false;
    sendBtn.disabled = false;
    textInput.placeholder = instantSwitch.checked ? "已启用即时输入，打字实时发到电脑..." : "输入完毕后，点击发送按钮投递...";
    textInput.focus();
  } else if (state === "connecting") {
    statusBadge.textContent = "连接中";
    connectBtn.disabled = true;
    textInput.placeholder = "正在重新连接，请稍候...";
  } else {
    statusBadge.textContent = "未连接";
    connectBtn.style.display = "block";
    connectBtn.disabled = false;
    sendBtn.disabled = true;
    textInput.placeholder = "蓝牙已断开，正在后台重连，您可以继续在此处打字...";
  }
}

// 蓝牙搜索连接
async function handleConnect() {
  if (!navigator.bluetooth) {
    await sendLog("ERROR", "浏览器不支持 Web Bluetooth API");
    alert("您的浏览器不支持 Web Bluetooth，或未在 HTTPS 协议下打开此页面。");
    return;
  }

  // 主动连接前清理旧的自动重连
  stopReconnect();
  connectedDevice = null;

  updateState("connecting");
  await sendLog("INFO", "开启蓝牙设备搜索面板...");

  try {
    const device = await navigator.bluetooth.requestDevice({
      acceptAllDevices: true,
      optionalServices: [SERVICE_UUID]
    });

    await sendLog("INFO", `[设备选择成功] 名称: ${device.name || "未知"} | ID: ${device.id}`);
    
    // 保存已授权设备
    connectedDevice = device;
    device.addEventListener('gattserverdisconnected', onDisconnected);

    await connectToGatt(device);

  } catch (error) {
    await sendLog("ERROR", `连接被取消或失败: ${error.message}`, error);
    updateState("disconnected");
  }
}

// 处理接收到的特征通知
async function handleNotifications(event) {
  const value = event.target.value;
  const decoder = new TextDecoder();
  const text = decoder.decode(value);
  
  if (text.startsWith("R:pull:start")) {
    pullBuffer = "";
  } else if (text.startsWith("R:pull:data:")) {
    pullBuffer += text.slice(12);
  } else if (text.startsWith("R:pull:end")) {
    textInput.value = pullBuffer;
    textInput.focus();
    try {
      const blob = new Blob([pullBuffer], { type: "text/plain" });
      const clipboardItem = new ClipboardItem({ "text/plain": blob });
      await navigator.clipboard.write([clipboardItem]);
      await sendLog("INFO", "拉取电脑剪贴板成功，已同步至手机剪贴板");
    } catch (err) {
      try {
        await navigator.clipboard.writeText(pullBuffer);
        await sendLog("INFO", "拉取电脑剪贴板成功，已通过 writeText 写入手机剪贴板");
      } catch (innerErr) {
        await sendLog("WARNING", "剪贴板拉取成功并展示，但同步至手机剪贴板失败（浏览器权限限制）: " + innerErr.message);
      }
    }
  }
}

// 执行底层的 GATT 连接与特征绑定
async function connectToGatt(device) {
  try {
    await sendLog("INFO", "开始发起 GATT 物理连接...");
    gattServer = await device.gatt.connect();
    
    await sendLog("INFO", "GATT 已连上，查询主服务 (Service)...");
    const service = await gattServer.getPrimaryService(SERVICE_UUID);
    
    await sendLog("INFO", "Service 已就绪，获取特征值 (Characteristic)...");
    writeCharacteristic = await service.getCharacteristic(CHAR_UUID);
    
    // 订阅特征通知以实现双向接收
    await writeCharacteristic.startNotifications();
    writeCharacteristic.addEventListener('characteristicvaluechanged', handleNotifications);
    await sendLog("INFO", "已成功订阅蓝牙特征通知，实现双向通信。");
    
    // 发送连接就绪指令，用于通知服务端显示连接日志并建立 session
    try {
      await sendPayload("K", "connect");
    } catch (e) {
      console.warn("发送连接就绪指令失败", e);
    }
    
    await sendLog("INFO", "蓝牙通道连接成功，处于就绪状态！");
    
    // 记录连接成功的时间戳
    connectionStartTime = Date.now();
    
    updateState("connected");
    stopReconnect();      // 连接成功后清除重连循环
  } catch (error) {
    updateState("disconnected");
    throw error;
  }
}

// 蓝牙静默断连回调 (无任何弹窗)
async function onDisconnected() {
  // 统计本次连接的时间跨度
  let durationStr = "未知";
  if (connectionStartTime > 0) {
    const duration = ((Date.now() - connectionStartTime) / 1000).toFixed(1);
    durationStr = `${duration} 秒`;
  }
  
  await sendLog("WARNING", `蓝牙物理断开。本次持续连接时间: ${durationStr}。进入后台 2 秒静默重连...`);
  
  gattServer = null;
  writeCharacteristic = null;
  updateState("disconnected");
  
  // 开启静默重连
  startReconnect();
}

// 循环尝试自动重连
async function startReconnect() {
  if (!connectedDevice) return;
  if (reconnectTimer) return;

  // 1. 立马进行一次重连尝试
  await sendLog("INFO", "自动重连尝试中 (首次即时重连)...");
  try {
    updateState("connecting");
    await connectToGatt(connectedDevice);
    return; // 如果首次即时重连成功，直接返回，不启动定时器
  } catch (e) {
    await sendLog("WARNING", "首次即时重连未成功，转入2秒循环重连: " + e.message);
    updateState("disconnected");
  }

  // 2. 如果首次即时重连失败，才开启每 2 秒一次的循环尝试
  reconnectTimer = setInterval(async () => {
    if (!connectedDevice) {
      stopReconnect();
      return;
    }
    if (gattServer && gattServer.connected) {
      stopReconnect();
      return;
    }

    await sendLog("INFO", "自动重连尝试中...");
    try {
      updateState("connecting");
      await connectToGatt(connectedDevice);
    } catch (e) {
      await sendLog("WARNING", "自动重连尝试未成功，2秒后继续: " + e.message);
      updateState("disconnected");
    }
  }, 2000);
}

// 停止重连定时器
function stopReconnect() {
  if (reconnectTimer) {
    clearInterval(reconnectTimer);
    reconnectTimer = null;
  }
}

// 监听浏览器切前台/唤醒事件（解决休眠后台唤醒后的快速连接）
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    sendLog("INFO", "网页唤醒，检查蓝牙连接状态...");
    if (connectedDevice && (!gattServer || !gattServer.connected)) {
      sendLog("INFO", "检测到连接失效，立即尝试主动重连");
      stopReconnect();
      startReconnect();
    }
  }
});

// 数据协议分发 (T: 文本, K: 控制按键)
async function sendPayload(prefix, content) {
  if (!writeCharacteristic) return;
  try {
    const encoder = new TextEncoder();
    const dataBytes = encoder.encode(`${prefix}:${content}`);
    await writeCharacteristic.writeValueWithoutResponse(dataBytes);
  } catch (error) {
    console.error("发送失败:", error);
    await sendLog("ERROR", `数据发送故障: ${error.message}`, error);
  }
}

// 经典模式：整段发送
async function sendText() {
  const text = textInput.value;
  if (!text.trim()) return;
  if (!writeCharacteristic) {
    alert("蓝牙未连接！");
    return;
  }
  
  try {
    await sendPayload("T", text + "\n");
    textInput.value = "";
    textInput.focus();
  } catch (error) {
    alert("发送失败: " + error.message);
  }
}

// 经典模式：清空输入
function clearInput() {
  textInput.value = "";
  textInput.focus();
}

// 即时输入与经典模式界面切换
function toggleInstantMode() {
  const isInstant = instantSwitch.checked;
  if (isInstant) {
    btnGroup.style.display = "none";
    textInput.style.height = "80px";
    if (gattServer && gattServer.connected) {
      textInput.placeholder = "已启用即时输入，打字实时发到电脑...";
    }
  } else {
    btnGroup.style.display = "flex";
    textInput.style.height = "120px";
    if (gattServer && gattServer.connected) {
      textInput.placeholder = "输入完毕后，点击发送按钮投递...";
    }
  }
  textInput.value = "";
  textInput.focus();
}

// 即时模式事件绑定
textInput.addEventListener("compositionstart", () => {
  isComposing = true;
});

textInput.addEventListener("compositionend", async (event) => {
  isComposing = false;
  if (!instantSwitch.checked) return;
  
  if (event.data && writeCharacteristic) {
    await sendPayload("T", event.data);
  }
  textInput.value = "";
});

textInput.addEventListener("input", async (event) => {
  if (!instantSwitch.checked) return;
  if (isComposing) return;

  if (event.inputType === "insertText") {
    if (event.data && writeCharacteristic) {
      await sendPayload("T", event.data);
    }
    textInput.value = "";
  } else if (event.inputType === "deleteContentBackward") {
    if (writeCharacteristic) {
      await sendPayload("K", "backspace");
    }
    textInput.value = "";
  }
});

textInput.addEventListener("paste", async (event) => {
  if (!instantSwitch.checked) return;
  event.preventDefault();
  
  const pastedData = (event.clipboardData || window.clipboardData).getData("text");
  if (pastedData && writeCharacteristic) {
    await sendPayload("T", pastedData);
  }
  textInput.value = "";
});

textInput.addEventListener("keydown", async (event) => {
  if (!instantSwitch.checked) {
    if (event.ctrlKey && event.key === 'Enter') {
      event.preventDefault();
      sendText();
    }
    return;
  }

  if (event.key === "Enter") {
    event.preventDefault();
    if (writeCharacteristic) {
      await sendPayload("K", "enter");
    }
    textInput.value = "";
  } else if (event.key === "Backspace" && textInput.value === "") {
    event.preventDefault();
    if (writeCharacteristic) {
      await sendPayload("K", "backspace");
    }
  }
});

// 剪贴板拉取（通过蓝牙）
async function getClipboardFromServer() {
  if (!writeCharacteristic) {
    alert("蓝牙未连接！");
    return;
  }
  try {
    await sendPayload("C", "pull:request");
    await sendLog("INFO", "已通过蓝牙发送剪贴板拉取请求");
  } catch (err) {
    console.error("剪贴板拉取失败:", err);
    await sendLog("ERROR", "剪贴板拉取失败", err);
  }
}

// 剪贴板推送（通过蓝牙）
async function sendClipboardToServer() {
  if (!writeCharacteristic) {
    alert("蓝牙未连接！");
    return;
  }
  try {
    const text = await navigator.clipboard.readText();
    if (!text) {
      alert("手机剪贴板为空！");
      return;
    }
    
    await sendLog("INFO", `开始通过蓝牙推送剪贴板，总长度: ${text.length}`);
    await sendPayload("C", "push:start");
    await sleep(15);
    
    const chunkSize = 200;
    for (let i = 0; i < text.length; i += chunkSize) {
      const chunk = text.substring(i, i + chunkSize);
      await sendPayload("C", `push:data:${chunk}`);
      await sleep(15);
    }
    
    await sendPayload("C", "push:end");
    await sendLog("INFO", "剪贴板数据通过蓝牙推送完毕");
  } catch (err) {
    console.error("剪贴板推送失败:", err);
    await sendLog("ERROR", "剪贴板推送失败", err);
  }
}
