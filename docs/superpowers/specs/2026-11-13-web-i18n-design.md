# 网页端中英双语设计

日期：2026-11-13
状态：已实施（2026-11-13）

## 一、目标

手机端网页支持中文与英文显示。始终跟随浏览器语言；页脚提供临时切换入口，但不持久化，刷新后回到系统语言。这次只做主页面，不涉及电脑端托管的上传页。

## 二、语言决定

- 每次加载只看 `navigator.languages`：其中第一个以 `zh` 开头的语言判为中文，其余一律英文。
- 手动切换只改当前会话的语言，不写 localStorage；刷新后重新按系统语言决定。
- 切换语言时同步：

- `document.documentElement.lang`：中文 `zh-CN`，英文 `en`；
- `document.title`：用 `app.title` 词条重新渲染。

## 三、技术选型

使用 `vue-i18n@11`（legacy: false，组合式 API）。

- `web/src/locales/zh.js`、`web/src/locales/en.js`：平铺嵌套字典，两份键集合必须一致。
- `web/src/logic/i18n.js`：语言检测、创建并导出 `i18n` 实例、`setLocale()` 与文档语言同步。
- `web/src/main.js`：`createApp(App).use(i18n).mount('#app')`。
- `App.vue`：`useI18n({ useScope: 'global' })` 取 `t` 与 `locale`。
- `ble-client.js` 是纯 JS，`import { i18n }` 后经 `i18n.global.t()` 取词；取词发生在事件发生时，切换语言立即生效。

## 四、翻译范围

翻译：

- 状态药丸：未连接 / 连接中 / 已连接，以及 aria-label；
- 输入框四种 placeholder；
- 即时发送开关标签、清空、发送、拉取/推送剪贴板、上行/下行测速、发送文件；
- 事件行：连接、断开、积压溢出、剪贴板结果、测速进度与结果、上传入口探测；
- `alert()` 提示；
- 版本不兼容 modal 的标题、正文与按钮；
- 版本更新提示；
- 语言切换按钮的文案与 aria-label。

不翻译：

- 电脑端下发的 `notice`（如剪贴板被占用、上行消息超时等）——文案在电脑端生成，翻译它需要两端同步改协议。
- 发往电脑端日志的文本：连接探针「已连接（第 N 次）」、断开诊断「第 N 次断开：…」。界面显示用翻译文案，写入电脑端日志的仍是中文常量，保证电脑端日志始终单一语言。两处文案会不同，代码里加注释说明。
- 控制台 `console.*` 诊断日志。
- 上传页、PWA manifest、`index.html` 里的静态 title 与 lang（启动后由 JS 覆盖 title 与 lang）。

## 五、切换入口

放在页脚：弱化的小号文字按钮在上，GitHub 仓库链接在下。按钮显示**当前语言名**（中文界面显示「中文」，英文界面显示「English」），点击切换到另一种语言；aria-label 为「切换语言」/「Switch language」。

顶部栏保持原样，只留状态药丸与即时发送开关。

样式沿用页脚仓库链接的配色与透明度：默认 0.6 不透明度，悬停提到 1。

## 六、测速结果行

`bench.js` 中的 `describeBench` 删除，结果行改由 `App.vue` 用 `t('bench.result', {...})` 拼装，方向名用 `t('bench.up') / t('bench.down')`。插值参数一律先转成字符串，避免 vue-i18n 对数字做本地化分组（`1,234`）导致结果行口径不一致。

`bench.test.js` 中「结果行含速率与单包大小」用例随之删除；新增 `web/src/logic/locales.test.js`，递归比对中英两份字典的键集合，防止漏翻。

## 七、验收

- `npm test` 通过（新增键一致性用例，现有编解码用例不受影响）。
- `npm run build` 编译通过。
- 客观核对：首次打开按系统语言、切换后 `html lang` / `document.title` / 各界面文案一起变、刷新后回到系统语言。
- 界面观感（页脚两行顺序、英文换行、药丸与开关对齐）由用户在手机上判断。
