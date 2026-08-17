# 🤖 AI 日报网站 · 完整重建 Prompt（Master Rebuild Prompt）

> **用途**：把本文件（连同 `daily_reports.py`、`build_archive.py`、`.github/workflows/daily-report.yml` 三个实现文件）喂给任何 AI 助手（Hermes / Claude / ChatGPT），它就能从零重建一个功能一致、可自动运行的 AI 日报网站。
>
> **版本**：v5.0（2026-08-17）· 7 板块体系 + 云端自动发布 + 阅读习惯跟踪

---

## 一、角色设定

你是一名资深全栈工程师 + AI 产品经理。你要根据以下规格，重建一个「AI 日报档案网站」。网站面向**小个体户、想用 AI 赚钱的普通人**，内容聚焦：AI 前沿情报、AI 落地应用、AI 赚钱案例。**稳定性是最高优先级**——网站必须每天自动更新，不能有一天更、有一天没更。

---

## 二、网站规格

### 2.1 基本信息
- 站点名：**AI 日报档案**
- 部署形态：纯静态站（GitHub Pages），数据与页面分离
- 技术栈：Python 3 生成脚本 + 原生 HTML/CSS/JS（无框架、无构建工具、无外部依赖）

### 2.2 七板块体系（核心）
| 板块 | 类型 key | 颜色 | 频率 | 文件名规则 |
|:-----|:-----|:-----|:-----|:-----|
| 💰 赚钱案例 | `money` | 暖棕 `#b07d3e` | 每日 | `AI赚钱日报_详细版_YYYYMMDD.md` |
| 🔧 应用场景 | `apps` | 蓝 `#4a7fb5` | 每日 | `AI应用场景日报_详细版_YYYYMMDD.md` |
| 📡 前沿情报 | `frontier` | 灰绿 `#5d7b6f` | 每日 | `AI前沿情报日报_详细版_YYYYMMDD.md` |
| 🎯 机会雷达 | `radar` | 醒目红 `#c0392b` | 每日 | `AI机会雷达_详细版_YYYYMMDD.md` |
| 🏭 行业深潜 | `industry` | 紫 `#8e44ad` | 每周一 | `AI行业深潜_详细版_YYYYMMDD.md` |
| ⚠️ 避坑指南 | `pitfall` | 橙 `#e67e22` | 每周三 | `AI避坑指南_详细版_YYYYMMDD.md` |
| 🧰 工具箱 | `toolbox` | 青绿 `#16a085` | 每周二、四 | `AI工具箱_详细版_YYYYMMDD.md` |

- 前端用 emoji + 名称做类型徽章（如 `💰 赚钱案例`、`🎯 机会雷达`），CSS 类名为 `.type-badge.{key}`
- 每日 4 份（赚钱/应用/前沿/机会雷达）+ 每周轮换 3 种（行业深潜周一、避坑周三、工具箱周二四）
- 周刊排班逻辑：Python `weekday()` 0=周一 ... 6=周日，`days` 字段控制

### 2.3 视觉风格
- 米色底护眼（`#f7f1e5` 系），无深色模式按钮（已删除）
- 类型徽章必须有背景色（`.type-badge.apps` 曾因缺 CSS 白字白底不可见——注意每个 type 都要有）
- 卡片左侧 4px 类型色边框

---

## 三、数据模型（markdown 源文件）

### 3.1 文件命名
`AI{类型名}_详细版_{YYYYMMDD}.md`（7 板块各自的命名见 2.2 表）

### 3.2 类型识别（classify 函数）
按文件名关键词判断：
- `赚钱`/`案例` → money
- `应用` → apps
- `前沿` → frontier
- `机会` → radar
- `行业` → industry
- `避坑` → pitfall
- `工具` → toolbox
- **扫描必须用 `*.md` 全匹配 + 关键词过滤**（不能只匹配 `*日报*`，否则机会雷达/行业深潜等新板块扫不到——这是已踩过的坑）

### 3.3 内容结构要求（生成 prompt 核心）
每份日报生成时要求 AI：
1. 每个案例/趋势**必须附真实来源链接**（官网/权威媒体域名），**禁止编造 URL**，不确定写官方主页域名
2. 文末必须含「信息来源」小节：`- [来源名称](https://链接)`
3. 各板块固定结构（见 `daily_reports.py` 的 REPORT_SPECS，含赚钱/应用/前沿/机会雷达/行业深潜/避坑/工具箱 7 份完整提示词）

---

## 四、生成器脚本规格（build_archive.py）

### 4.1 职责
扫描 `reports/*.md` → 解析（日期 + 类型 + 内容）→ 生成 `index.html`（内嵌 CSS/JS）+ `data.js`（`window.REPORTS = [...]`）

### 4.2 网页功能清单（全部必须实现）
1. **桌面小格子日历**（左侧边栏，Flomo 风格）：按月显示，有日报的日期着色（按类型颜色），金色边框=今天，蓝色描边+放大=选中
2. **手机折叠列表**（≤640px 自动切换）：按月折叠，默认全折叠，显示 `2026年8月 (3篇)`
3. **类型筛选**：顶部 7 个类型按钮；点选→显示所有日期该类型；再点→取消；点日期格→清除类型筛选防空白
4. **搜索**：按钮/回车触发；中文逐字模糊匹配（`近期AI工具` 匹配 `近期 AI 工具`，正则 `chars.join('\\s*')`）；`<mark>` 黄色高亮；自动滚动到首个匹配
5. **h2 折叠**：点标题隐藏/展开内容，▾ 箭头
6. **卡片目录**：每份日报顶部自动生成 h2 跳转链接
7. **信息来源折叠框**：h2 含"信息来源"→ 统计后续链接数，>3 条自动包 `.source-scroll`（max-height:130px, overflow-y:auto, 圆角边框），加"▾ 展开全部（N 条）"按钮
8. **分析层高亮**：h2 含关键词（具体做法/国内可复制/赚钱逻辑/收入情况/一句话建议/可复用/操作技巧/落地路径/怎么做/可行性/变现/成本/门槛）→ 金色左边框 + 暖色渐变底
9. **未读红点**：localStorage `lastVisitDate`，新日期右上角红点
10. **阅读习惯三合一**（localStorage，不清缓存持续记忆）：
    - 滚动联动：视口中心卡片 → 对应类型按钮加 active 高亮
    - 停留排序：每 2s 累计当前板块时长（`aiBoardTime`），同日多板块按时长降序渲染
    - 位置记忆：记录 `aiLastPos`（date+scrollY），**仅当天有效**恢复位置
11. **滚动回顶**：切换日期/类型后 `scrollTo(0,0)`

### 4.3 数据排序
- 默认：日期倒序（最新在前），同一天内按阅读习惯时长降序
- 每个日期显示当天全部类型的日报卡片

---

## 五、日报自动生成器规格（daily_reports.py）

### 5.1 核心逻辑
```
读取 DEEPSEEK_API_KEY（云端=环境变量，本地=~/.hermes/.env）
today = 北京时间（必须显式 UTC+8，不能用服务器本地时间——云端 UTC 会错一天）
遍历 REPORT_SPECS（7 份）：
  有 days 字段的按星期几跳过（周刊排班）
  当日文件已存在 → 跳过（防重复）
  调 DeepSeek API（流式 stream=true，超时 1500s，重试 2 次，max_tokens 6000）
  写文件 → sleep(5) 防限流
跑 build_archive.py → git add -A → commit → pull --rebase → push
```

### 5.2 API 配置
- URL: `https://api.deepseek.com/chat/completions`
- Model: `deepseek-chat`（实测映射 `deepseek-v4-flash`，价格 2 元/百万输出 tokens）
- 流式解析：读 `data:` 行，`[DONE]` 结束，累计 `delta.content`

### 5.3 git 推送（双环境兼容）
- 云端（`GITHUB_ACTIONS=true`）：配 `github-actions[bot]` 身份 + `x-access-token` 换 remote
- **顺序必须：add -A → commit → pull --rebase → push**（先 pull 会因工作区未暂存改动报错）
- 路径用 `ARCHIVE_DIR` 环境变量覆盖（云端=workspace，本地=桌面路径）

---

## 六、自动发布方案（GitHub Actions）

### 6.1 workflow 文件
`.github/workflows/daily-report.yml`：
- **3 个 cron 多点兜底**（GitHub schedule 有延迟，实测晚 10 小时）：
  - `0 16 * * *`（UTC）= 北京 0:00 主触发
  - `30 17 * * *`（UTC）= 北京 1:30 兜底 1
  - `0 19 * * *`（UTC）= 北京 3:00 兜底 2
- `workflow_dispatch` 手动触发
- `permissions: contents: write`（才能 push）
- `timeout-minutes: 300`（生成 4 份日报需 2-3 小时）
- env: `DEEPSEEK_API_KEY`（secrets）、`ARCHIVE_DIR=github.workspace`、`TZ=Asia/Shanghai`

### 6.2 为什么凌晨生成
生成 4 份日报要 2-3 小时 → 0:00 开始 → 3:00 完成 → **7:00 前必上线**（用户硬性要求，不接受模糊时间）

### 6.3 密钥
GitHub Secret 名**必须精确**：`DEEPSEEK_API_KEY`（全大写+下划线）。指导用户创建时必须先给确切名字，否则用户自起名 → 工作流秒失败

### 6.4 已废弃方案（不要用）
- ❌ Hermes cron：Hermes 关闭时不触发；DeepSeek 非流式 API 超 600s idle 限制
- ❌ 本地 launchd：与云端双跑必 git 冲突（已停用，仅存档）

---

## 七、已知坑清单（重建时务必避开）

1. **时区**：脚本必须用北京时间 `now_beijing()`（UTC+8 显式），云端服务器 UTC 会导致日期错一天
2. **GitHub Actions schedule 延迟**：多点 cron 兜底 + 脚本 `path.exists()` 跳过逻辑防重复
3. **GitHub Pages CDN 缓存 10 分钟**：验证加 `?v=xxx` 参数
4. **macOS 中文文件名编码 bug**：git checkout 可能产生"字节数字乱码"空文件，build 前清理 0 字节文件；扫描用 `*.md` + 关键词过滤
5. **force push 前必须核对**：`git fetch && git log origin/main --oneline -3` 对比本地包含远程全部内容，用 `--force-with-lease`；翻车时 `git reflog` 找回
6. **短链服务（tinyurl）国内被墙**：来源链接**一律用原链接**，不用短链（用户拍板：不为缩短链接牺牲稳定性）
7. **来源链接打不开 ≠ 链接坏**：多为海外站被墙，先让用户开代理；403=反爬、404=真失效、超时=墙或慢
8. **GitHub Secret 命名**：必须精确 `DEEPSEEK_API_KEY`
9. **分析层/来源框的 DOM 查找**：`h2.nextElementSibling` 循环跳过非 section-body 兄弟节点
10. **类型徽章 CSS**：每个 type 都要有 `.type-badge.{key}` 背景色

---

## 八、自检清单（重建后必须验证）

1. `python3 build_archive.py` 无错误，`node --check` JS 语法通过
2. 浏览器实测（file:// + 线上双端）：
   - 日历小格子着色 / 手机折叠列表
   - 7 个类型按钮筛选 + 取消
   - 搜索高亮 + 自动滚动
   - h2 折叠 / 信息来源折叠框（>3 条包装，≤3 条不包装）
   - 阅读习惯三合一（滚动联动/停留排序/位置记忆）
   - console 无 JS 错误
3. `python3 daily_reports.py` 手动跑通全流程（生成→build→push）
4. `curl` GitHub Actions API 确认 schedule 触发
5. `git fetch && git log origin/main --oneline -3` 确认 `github-actions[bot]` 提交在远程
6. 验收口径：**"明早 7:00 打开网站看有没有当天日报"**

---

## 九、用户协作偏好（必读）

- **动手前先复述理解**：复杂需求必须先说"我理解的三件事"→ 方案表 → 确认点 → 问"什么时候执行"，用户说执行再动手
- **改完必自检再交付**，不能只推代码
- **命名/配置给精确值**（Secret 名、路径、API key），不能假定用户按常识命名
- **稳定性第一**：可能挑战稳定性的功能先讲清风险让用户拍板；解决不了的问题直接退回原方案
- 用户称呼：**黄哥**；回复用简体中文

---

## 十、部署清单（首次上线）

1. 建 GitHub 仓库 `huangge-adventure`，启用 Pages（main 分支 root）
2. 上传：`build_archive.py`、`daily_reports.py`、`.github/workflows/daily-report.yml`、`index.html`、`data.js`、`reports/*.md`（全部进 git，`.gitignore` 只忽略日志/缓存）
3. GitHub Settings → Secrets → Actions → 新建 `DEEPSEEK_API_KEY`（精确命名）
4. 手动触发一次 workflow 验证（Actions 页面 Run workflow）
5. 验证线上：https://dawei198909.github.io/huangge-adventure/

---

*本 Prompt 由 Hermes Agent 于 2026-08-17 整理。配套实现文件：`daily_reports.py`（生成器）、`build_archive.py`（网页构建）、`.github/workflows/daily-report.yml`（云端调度）。*
